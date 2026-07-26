"""Pure append-only deduction tests."""

from __future__ import annotations

import random

import pytest

from crewborg.deduction.collector import update_deduction_history
from crewborg.deduction.config import enabled_for_role
from crewborg.deduction.decision import decide, decide_from_inference
from crewborg.deduction.inference import (
    build_assignment_table,
    derive_evidence,
    infer,
    score_assignments,
)
from crewborg.deduction.model import (
    DeathObserved,
    DeductionHistory,
    GameSpec,
    ObservedBody,
    ObservedPlayer,
    ObservedVent,
    UtteranceObserved,
    VoteObserved,
    WorldObserved,
)
from crewborg.deduction.synthetic import SyntheticBehavior, generate_game
from crewborg.modes import AttendMeetingMode
from crewborg.perception.entities import (
    ChatLine,
    CensusEntry,
    ResolvedScene,
    VoteCandidate,
    VotingState,
)
from crewborg.types import (
    ActionState,
    Belief,
    Percept,
    PlayerRecord,
    update_belief,
)
from players.player_sdk import EventEmitter, ListMetricsSink, ListTraceSink

PLAYERS = ("white", "red", "blue", "yellow", "green", "purple")


def _history(*events, players: tuple[str, ...] = PLAYERS) -> DeductionHistory:
    return DeductionHistory(
        game=GameSpec(
            players=players,
            self_color="white",
            self_role="crewmate",
            imposter_count=2,
        ),
        events=tuple(events),
    )


def _utterance(
    tick: int,
    speaker: str,
    text: str,
    *,
    meeting_id: int = 100,
) -> UtteranceObserved:
    return UtteranceObserved(
        event_id=f"chat:{meeting_id}:{tick}:{speaker}:{text}",
        tick=tick,
        meeting_id=meeting_id,
        speaker=speaker,
        text=text,
    )


def _world(
    tick: int,
    colors: tuple[str, ...],
) -> WorldObserved:
    return WorldObserved(
        event_id=f"world:{tick}",
        tick=tick,
        self_xy=(0, 0),
        players=tuple(
            ObservedPlayer(
                color=color,
                x=10 if color in {"blue", "yellow"} else 100,
                y=0,
            )
            for color in colors
        ),
    )


def test_murdered_player_is_impossible_but_ejected_player_is_not() -> None:
    murder = infer(
        _history(
            DeathObserved(
                event_id="death:red",
                tick=50,
                color="red",
                source="body",
            )
        )
    )
    ejection = infer(
        _history(
            DeathObserved(
                event_id="eject:red",
                tick=50,
                color="red",
                source="ejection",
            )
        )
    )

    assert murder.marginal("red") == 0.0
    assert ejection.marginal("red") == pytest.approx(0.4)
    assert all("red" not in item.imposters for item in murder.hypotheses)
    assert any("red" in item.imposters for item in ejection.hypotheses)


def test_explicit_pipeline_matches_compatibility_wrapper() -> None:
    history = _history(
        _utterance(101, "blue", "red vented"),
        _utterance(102, "yellow", "red vented"),
    )

    evidence = derive_evidence(history)
    table = build_assignment_table(history, evidence)
    result = score_assignments(table)

    assert result == infer(history)
    assert decide_from_inference(history, result) == decide(history)
    factor_trace = result.as_factor_trace()
    assert len(factor_trace["hypotheses"]) == len(result.hypotheses)
    assert factor_trace["hypotheses"][0]["factors"]


def test_compact_world_values_round_trip_through_history() -> None:
    history = _history(
        WorldObserved(
            event_id="world:1",
            tick=1,
            self_xy=(5, 6),
            players=(ObservedPlayer(color="red", x=7, y=8),),
            bodies=(ObservedBody(color="blue", x=9, y=10),),
            visible_vents=(ObservedVent(index=2, occupants=("yellow",)),),
        )
    )

    restored = DeductionHistory.model_validate(history.model_dump())

    assert restored == history
    assert restored.events[0].players[0].color == "red"


def test_feature_flag_is_crew_only(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_DEDUCTION_HISTORY", "1")

    assert enabled_for_role("crewmate")
    assert not enabled_for_role("imposter")
    assert not enabled_for_role(None)


def test_personally_witnessed_action_pins_actor() -> None:
    before = WorldObserved(
        event_id="world:20",
        tick=20,
        self_xy=(100, 100),
        players=(
            ObservedPlayer(color="red", x=10, y=0),
            ObservedPlayer(color="blue", x=0, y=0),
        ),
    )
    after = WorldObserved(
        event_id="world:21",
        tick=21,
        self_xy=(100, 100),
        players=(ObservedPlayer(color="red", x=10, y=0),),
        bodies=(ObservedBody(color="blue", x=0, y=0),),
    )
    result = infer(
        _history(
            before,
            after,
        )
    )

    assert result.marginal("red") == pytest.approx(1.0)
    assert all("red" in item.imposters for item in result.hypotheses)


def test_known_imposter_team_is_a_static_role_constraint() -> None:
    history = DeductionHistory(
        game=GameSpec(
            players=PLAYERS,
            self_color="white",
            self_role="imposter",
            imposter_count=2,
            known_imposters=("white", "red"),
        ),
    )

    result = infer(history)

    assert result.hypotheses[0].imposters == ("white", "red")
    assert result.hypotheses[0].probability == pytest.approx(1.0)


def test_visible_vent_transition_is_rederived_as_a_pin() -> None:
    before = WorldObserved(
        event_id="world:20",
        tick=20,
        self_xy=(100, 100),
        visible_vents=(ObservedVent(index=0),),
    )
    after = WorldObserved(
        event_id="world:21",
        tick=21,
        self_xy=(100, 100),
        players=(ObservedPlayer(color="red", x=10, y=0),),
        visible_vents=(ObservedVent(index=0, occupants=("red",)),),
    )

    result = infer(_history(before, after))

    assert result.marginal("red") == pytest.approx(1.0)
    assert any(
        item.channel == "direct"
        and item.status == "active"
        and item.targets == ("red",)
        for item in result.evidence
    )


def test_walking_onto_a_visible_vent_is_not_a_pin() -> None:
    before = WorldObserved(
        event_id="world:20",
        tick=20,
        self_xy=(100, 100),
        players=(ObservedPlayer(color="red", x=12, y=0),),
        visible_vents=(ObservedVent(index=0),),
    )
    after = WorldObserved(
        event_id="world:21",
        tick=21,
        self_xy=(100, 100),
        players=(ObservedPlayer(color="red", x=10, y=0),),
        visible_vents=(ObservedVent(index=0, occupants=("red",)),),
    )

    result = infer(_history(before, after))

    assert result.marginal("red") == pytest.approx(0.4)
    assert not any(item.channel == "direct" for item in result.evidence)


def test_same_source_target_claim_is_deduplicated_with_audit() -> None:
    one = infer(_history(_utterance(101, "blue", "red vented")))
    repeated = infer(
        _history(
            _utterance(101, "blue", "red vented"),
            _utterance(102, "blue", "vote red, red vented"),
        )
    )

    assert repeated.marginal("red") == pytest.approx(one.marginal("red"))
    assert any(
        item.status == "ignored" and "duplicate source-target" in item.reason
        for item in repeated.evidence
    )


def test_claims_persist_across_meetings_with_repeat_discount() -> None:
    first = infer(_history(_utterance(101, "blue", "red vented")))
    later = infer(
        _history(
            _utterance(101, "blue", "red vented"),
            _utterance(301, "blue", "red vented", meeting_id=300),
        )
    )

    assert later.marginal("red") > first.marginal("red")
    active = [
        item
        for item in later.evidence
        if item.channel == "claim" and item.status == "active"
    ]
    assert len(active) == 2
    assert active[1].weight < active[0].weight


def test_with_me_statement_is_not_lossily_promoted_to_player_clear() -> None:
    result = infer(
        _history(_utterance(101, "blue", "yellow was with me, yellow clear"))
    )

    assert result.marginal("yellow") == pytest.approx(0.4)
    assert any(
        item.status == "ignored"
        and item.reason == "co-presence is not a unary player clear"
        for item in result.evidence
    )


def test_near_a_vent_statement_is_not_promoted_to_witnessed_vent_use() -> None:
    result = infer(
        _history(
            _utterance(
                101,
                "blue",
                "I saw yellow near the vent earlier but also doing tasks.",
            )
        )
    )

    assert result.marginal("yellow") == pytest.approx(0.4)
    assert any(
        item.status == "ignored"
        and item.reason == "proximity to a vent is not witnessed vent use"
        for item in result.evidence
    )


def test_synthetic_ballots_usually_share_the_speakers_latent_belief() -> None:
    game = generate_game(
        random.Random(7),
        behavior=SyntheticBehavior(
            meetings=2,
            speak_probability=1.0,
            kill_between_meetings_probability=0.0,
            vote_follows_belief_probability=1.0,
        ),
    )
    claims = derive_evidence(game.history).claims
    claims_by_actor = {
        (claim.meeting_id, claim.speaker): claim.targets[0] for claim in claims
    }

    for event in game.history.events:
        if isinstance(event, VoteObserved):
            assert event.target == claims_by_actor[(event.meeting_id, event.voter)]


def test_synthetic_beliefs_can_persist_across_meetings() -> None:
    game = generate_game(
        random.Random(11),
        behavior=SyntheticBehavior(
            meetings=3,
            speak_probability=0.0,
            kill_between_meetings_probability=0.0,
            belief_persistence=1.0,
            crowd_belief_probability=0.0,
            vote_follows_belief_probability=1.0,
        ),
    )
    votes_by_actor: dict[str, set[str | None]] = {}
    for event in game.history.events:
        if isinstance(event, VoteObserved):
            votes_by_actor.setdefault(event.voter, set()).add(event.target)

    assert votes_by_actor
    assert all(len(targets) == 1 for targets in votes_by_actor.values())


def test_synthetic_crew_can_adopt_one_shared_crowd_belief() -> None:
    game = generate_game(
        random.Random(13),
        behavior=SyntheticBehavior(
            meetings=1,
            speak_probability=0.0,
            crowd_belief_probability=1.0,
            crew_crowd_adoption_probability=1.0,
            imp_crowd_adoption_probability=0.0,
            vote_follows_belief_probability=1.0,
        ),
    )
    crew_voters = set(game.history.game.players) - set(game.imposters) - {
        game.history.game.self_color
    }
    crew_targets = [
        event.target
        for event in game.history.events
        if isinstance(event, VoteObserved) and event.voter in crew_voters
    ]

    assert max(crew_targets.count(target) for target in set(crew_targets)) >= (
        len(crew_targets) - 1
    )


def test_copresence_excludes_pairs_without_an_eligible_outside_killer() -> None:
    frames = [
        _world(0, ("red", "blue", "yellow")),
        *[_world(tick, ("blue", "yellow")) for tick in range(1, 6)],
    ]
    result = infer(
        _history(
            DeathObserved(
                event_id="eject:purple",
                tick=-1,
                color="purple",
                source="ejection",
            ),
            *frames,
            DeathObserved(
                event_id="death:red",
                tick=5,
                color="red",
                source="census",
            ),
        )
    )

    excluded = {item.imposters: item.reasons for item in result.excluded}
    assert any(
        reason.startswith("no_possible_killer:alibi:death:red")
        for reason in excluded[("blue", "yellow")]
    )
    assert any(
        reason.startswith("no_possible_killer:alibi:death:red")
        for reason in excluded[("blue", "purple")]
    )
    assert ("blue", "green") not in excluded
    assert result.marginal("blue") > 0.0
    assert result.marginal("yellow") > 0.0


def test_independent_accusers_can_drive_a_vote() -> None:
    eight_players = PLAYERS + ("orange", "cyan")
    history = _history(
        _utterance(101, "blue", "red vented"),
        _utterance(102, "yellow", "red vented"),
        _utterance(103, "green", "red vented"),
        players=eight_players,
    )
    decision = decide(
        history,
        live_targets=tuple(color for color in eight_players if color != "white"),
    )

    assert decision.action == "eject"
    assert decision.target == "red"
    assert decision.sources == ("blue", "green", "yellow")


def test_single_public_source_does_not_spend_a_vote() -> None:
    decision = decide(
        _history(_utterance(101, "blue", "red vented")),
        live_targets=("red", "blue", "yellow", "green", "purple"),
    )

    assert decision.action == "skip"
    assert "insufficient independent" in decision.reason


def test_ballot_pile_without_an_accusation_does_not_spend_a_vote() -> None:
    eight_players = PLAYERS + ("orange", "cyan")
    events = []
    for meeting_id in (100, 1100, 2100):
        for index, voter in enumerate(
            ("blue", "yellow", "green", "purple", "orange")
        ):
            events.append(
                VoteObserved(
                    event_id=f"vote:{meeting_id}:{voter}",
                    tick=meeting_id + 800 + index,
                    meeting_id=meeting_id,
                    voter=voter,
                    target="red",
                )
            )
    decision = decide(
        _history(*events, players=eight_players),
        live_targets=tuple(color for color in eight_players if color != "white"),
    )

    assert decision.probability > decision.required_probability
    assert decision.action == "skip"
    assert "lacks accusation" in decision.reason


def test_parity_threshold_is_high_midgame_and_lower_at_forced_vote_edge() -> None:
    evidence = (
        _utterance(101, "blue", "red vented"),
        _utterance(102, "yellow", "red vented"),
    )
    midgame = decide(
        _history(*evidence),
        live_targets=("red", "blue", "yellow", "green", "purple"),
    )
    edge = decide(
        _history(
            *evidence,
            DeathObserved(
                event_id="death:purple",
                tick=50,
                color="purple",
                source="body",
            ),
        ),
        live_targets=("red", "blue", "yellow", "green"),
    )

    assert midgame.required_probability == pytest.approx(0.8)
    assert edge.skip_loss_probability == pytest.approx(1.0)
    assert edge.required_probability == pytest.approx(0.51)


def test_runtime_collector_keeps_exact_chat_and_death_once() -> None:
    belief = Belief(
        self_color="white",
        self_role="crewmate",
        phase="Playing",
    )
    for color in PLAYERS:
        belief.roster[color] = PlayerRecord(color=color, life_status="alive")
    voting = VotingState(
        timer_present=True,
        self_marker_color="white",
        candidates=tuple(
            VoteCandidate(slot=index, color=color, alive=color != "purple")
            for index, color in enumerate(PLAYERS)
        ),
    )
    resolved = ResolvedScene(
        tick=100,
        camera_ready=True,
        camera_x=0,
        camera_y=0,
        self_world_x=0,
        self_world_y=0,
        voting=voting,
        chat_lines=(ChatLine(speaker_color="blue", text="Yellow was with me."),),
        census=tuple(
            CensusEntry(color=color, alive=color != "purple") for color in PLAYERS
        ),
    )
    percept = Percept(tick=100, messages_applied=1, resolved=resolved)

    update_belief(belief, percept)
    update_deduction_history(belief, percept)
    update_deduction_history(belief, percept)

    utterances = [
        event
        for event in belief.deduction_events
        if isinstance(event, UtteranceObserved)
    ]
    deaths = [
        event for event in belief.deduction_events if isinstance(event, DeathObserved)
    ]
    assert len(utterances) == 1
    assert utterances[0].text == "Yellow was with me."
    assert len(deaths) == 1
    assert deaths[0].color == "purple"
    assert deaths[0].source == "census"


def _meeting_belief_with_history(events: tuple) -> Belief:
    players = PLAYERS + ("orange", "cyan")
    belief = Belief(
        self_color="white",
        self_role="crewmate",
        phase="Voting",
        phase_start_tick=100,
        last_tick=1252,
        vote_timer_ticks=1200,
        imposter_count=2,
    )
    belief.roster = {
        color: PlayerRecord(color=color, life_status="alive") for color in players
    }
    belief.voting = VotingState(
        timer_present=True,
        self_marker_color="white",
        candidates=tuple(
            VoteCandidate(slot=index, color=color, alive=True)
            for index, color in enumerate(players)
        ),
    )
    belief.deduction_events = list(events)
    belief.deduction_event_ids = {event.event_id for event in events}
    return belief


def test_meeting_switch_bypasses_legacy_suspicion_and_uses_history(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CREWBORG_DEDUCTION_HISTORY", "1")
    events = (
        _utterance(101, "blue", "red vented"),
        _utterance(102, "yellow", "red vented"),
        _utterance(103, "green", "red vented"),
    )
    belief = _meeting_belief_with_history(events)
    belief.suspicion = {"purple": 0.999}
    mode = AttendMeetingMode()
    sink = ListTraceSink()
    mode.emit = EventEmitter(sink, ListMetricsSink())

    chat = mode.decide(belief, ActionState())
    vote = mode.decide(belief, ActionState())

    assert chat.kind == "chat"
    assert chat.text is not None and "red" in chat.text
    assert vote.kind == "vote"
    assert vote.target_color == "red"
    [trace] = [
        event
        for event in sink.events
        if event.name == "domain.deduction_history_decision"
    ]
    assert trace.data["history_event_counts"] == {"utterance": 3}
    assert trace.data["remaining_ticks"] == 48
    assert trace.data["solve_ms"] >= 0
    assert trace.data["factor_table"]["hypotheses"]


def test_meeting_switch_never_falls_back_to_legacy_suspicion(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_DEDUCTION_HISTORY", "1")
    belief = _meeting_belief_with_history(())
    belief.suspicion = {"red": 0.999}

    vote = AttendMeetingMode().decide(belief, ActionState())

    assert vote.kind == "vote"
    assert vote.target_color is None


def test_gate_presets_select_decision_config_fields() -> None:
    """CREWBORG_DECISION_GATE picks a DecisionConfig preset, and only that."""

    from crewborg.deduction.config import gate_overrides
    from crewborg.deduction.decision import DecisionConfig

    assert gate_overrides({}) == {}
    shipped = DecisionConfig(**gate_overrides({}))
    assert shipped == DecisionConfig()

    loose = DecisionConfig(**gate_overrides({"CREWBORG_DECISION_GATE": "loose"}))
    # margin and support are the jointly-binding pair; the probability threshold is
    # deliberately NOT part of this preset.
    assert loose.base_margin == 1e-3
    assert loose.require_support is False
    assert loose.base_probability == shipped.base_probability
    # The parity machinery must not move with the gate preset.
    assert loose.parity_risk_cutoff == shipped.parity_risk_cutoff
    assert loose.forced_vote_probability == shipped.forced_vote_probability
    assert (
        loose.dangerous_wrong_eject_probability
        == shipped.dangerous_wrong_eject_probability
    )

    p40 = DecisionConfig(**gate_overrides({"CREWBORG_DECISION_GATE": "loose+p40"}))
    assert p40.base_probability == 0.40
    assert p40.require_support is False


def test_margin_floor_is_epsilon_not_zero() -> None:
    """A flat posterior (margin == 0) must still be refused under the loose preset."""

    from crewborg.deduction.config import gate_overrides
    from crewborg.deduction.decision import DecisionConfig

    loose = DecisionConfig(**gate_overrides({"CREWBORG_DECISION_GATE": "loose"}))
    assert loose.base_margin > 0.0, "margin==0 is 55% accurate; it must not pass"


def test_unknown_gate_preset_degrades_to_shipped() -> None:
    """A typo must not silently produce a third, unintended configuration."""

    from crewborg.deduction.config import gate_overrides
    from crewborg.deduction.decision import DecisionConfig

    assert gate_overrides({"CREWBORG_DECISION_GATE": "lose"}) == {}
    assert DecisionConfig(**gate_overrides({"CREWBORG_DECISION_GATE": ""})) == DecisionConfig()


def test_require_support_false_still_respects_margin_and_probability() -> None:
    """Dropping support must not turn the gate into "always eject"."""

    from crewborg.deduction.decision import DecisionConfig

    cfg = DecisionConfig(require_support=False)
    assert cfg.base_probability == 0.65
    assert cfg.base_margin == 0.10
