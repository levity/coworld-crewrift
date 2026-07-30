"""Pure append-only deduction tests."""

from __future__ import annotations

import random
from typing import ClassVar

import pytest
from players.player_sdk import EventEmitter, ListMetricsSink, ListTraceSink
from pydantic import BaseModel, ConfigDict, ValidationError

from crewborg.deduction.collector import update_deduction_history
from crewborg.deduction.config import enabled_for_role
from crewborg.deduction.consult import REGISTRY as CONSULT_REGISTRY
from crewborg.deduction.consult import TRACE_EVENT as CONSULT_TRACE_EVENT
from crewborg.deduction.consult import (
    BaseConsult,
    Candidate,
    ConsultOutcome,
    ConsultView,
    GameEvent,
    parse_spec,
)
from crewborg.deduction.consult.shortlist import ShortlistConsult, ShortlistResponse
from crewborg.deduction.decision import decide, decide_from_inference
from crewborg.deduction.inference import (
    InferenceConfig,
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
    CensusEntry,
    ChatLine,
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


# --- witnessed-kill window: the margin, and at_least_one ---------------------------
#
# Regression cover for the hosted failure in xreq_51754f1f / ereq_ff5a9fdd frame 2111,
# reproduced to the pixel: the true killer's last sampled position was 23.0px from the
# victim (just outside the 20px KillRange) while an innocent bystander sat at 16.3px
# (just inside), so the shipped rule found "exactly one actor" and pinned a CREWMATE
# with p=1.0 -- eliminating the true assignment from the hypothesis space entirely.


def _boundary_kill_frames() -> tuple[WorldObserved, WorldObserved]:
    """The real geometry: victim `yellow`, true killer `red` @23.0px, bystander `blue` @16.3px."""

    before = WorldObserved(
        event_id="world:2110",
        tick=2110,
        self_xy=(500, 500),
        players=(
            ObservedPlayer(color="yellow", x=289, y=295),   # victim
            ObservedPlayer(color="blue", x=305, y=292),     # bystander: d=16.3px
            ObservedPlayer(color="red", x=270, y=282),      # true killer: d=23.0px
        ),
    )
    after = WorldObserved(
        event_id="world:2111",
        tick=2111,
        self_xy=(500, 500),
        players=(
            ObservedPlayer(color="blue", x=302, y=294),
            ObservedPlayer(color="red", x=270, y=283),
        ),
        bodies=(ObservedBody(color="yellow", x=286, y=295),),
    )
    return before, after


def test_exact_kill_radius_pins_the_wrong_player_at_the_boundary() -> None:
    """Documents the shipped behaviour this fix exists for (margin off = unchanged)."""

    result = infer(_history(*_boundary_kill_frames()))

    assert result.pins == ("blue",), "shipped rule names the bystander"
    assert result.marginal("blue") == pytest.approx(1.0)
    # The damage is not a wrong vote, it is a wrong SPACE: the truth is gone.
    assert all("blue" in h.imposters for h in result.hypotheses)
    assert not any({"red", "purple"} == set(h.imposters) for h in result.hypotheses)


def test_margin_makes_the_boundary_kill_ambiguous_instead_of_wrong() -> None:
    """A motion tolerance removes the false certainty. No pin is better than a wrong one."""

    result = infer(
        _history(*_boundary_kill_frames()),
        config=InferenceConfig(kill_range_margin=6),
    )

    assert "blue" not in result.pins
    assert result.marginal("blue") < 1.0
    # Without at_least_one the observation is simply dropped, so nothing is excluded
    # on its account -- but the true assignment is reachable again.
    assert any({"red"} <= set(h.imposters) for h in result.hypotheses)


def test_at_least_one_widens_the_disjunction_by_whoever_was_not_decoded() -> None:
    """A frame lists only DECODED players, so the disjunction must include the rest.

    These frames show 3 of 6 players, so `green`/`purple` could equally have been
    standing there. Narrowing the constraint to the two visible candidates would be
    unsound -- and a wrong disjunction is worse than a wrong pin, because it can empty
    the assignment table and silently kill every later solve in the game.
    """

    result = infer(
        _history(*_boundary_kill_frames()),
        config=InferenceConfig(kill_range_margin=6, ambiguous_kill_constraints=True),
    )

    assert "blue" not in result.pins
    assert result.hypotheses, "the table must not be emptied"
    # Undecoded live players stay reachable rather than being excluded.
    assert any("green" in h.imposters for h in result.hypotheses)
    assert any("red" in h.imposters for h in result.hypotheses)


def test_at_least_one_bites_when_the_frame_accounts_for_everyone() -> None:
    """With every live player decoded, the disjunction is informative."""

    before, after = _boundary_kill_frames()
    # Park the remaining roster far away, so they are accounted for but out of range.
    extras = tuple(
        ObservedPlayer(color=c, x=900, y=900) for c in ("green", "purple")
    )
    before = before.model_copy(update={"players": before.players + extras})
    after = after.model_copy(update={"players": after.players + extras})

    result = infer(
        _history(before, after),
        config=InferenceConfig(kill_range_margin=6, ambiguous_kill_constraints=True),
    )

    assert "blue" not in result.pins
    assert result.hypotheses
    # Now only the two in-range candidates can satisfy it.
    for h in result.hypotheses:
        assert {"blue", "red"} & set(h.imposters), h.imposters
    assert any("red" in h.imposters for h in result.hypotheses)


def test_at_least_one_alone_does_not_fire_at_the_boundary() -> None:
    """Lever #1 without the margin cannot help here: only ONE actor is in exact range."""

    result = infer(
        _history(*_boundary_kill_frames()),
        config=InferenceConfig(ambiguous_kill_constraints=True),
    )

    assert result.pins == ("blue",), "still a unique actor at the exact radius"


def test_kill_window_presets_are_separate_from_the_other_arms() -> None:
    """Three independent env vars, so an A/B moves one thing at a time."""

    from crewborg.deduction.config import inference_overrides

    assert inference_overrides({}) == {}
    both = inference_overrides({"CREWBORG_KILL_WINDOW": "both"})
    assert both == {"kill_range_margin": 6, "ambiguous_kill_constraints": True}
    assert inference_overrides({"CREWBORG_KILL_WINDOW": "typo"}) == {}
    # Trust and kill-window compose without colliding.
    mixed = inference_overrides(
        {"CREWBORG_KILL_WINDOW": "margin", "CREWBORG_SPEAKER_TRUST": "on"}
    )
    assert mixed["kill_range_margin"] == 6 and mixed["speaker_trust"] is True


@pytest.mark.parametrize(
    ("family", "presets"),
    [
        ("gate", "GATE_PRESETS"),
        ("trust", "TRUST_PRESETS"),
        ("kill_window", "KILL_WINDOW_PRESETS"),
    ],
)
def test_every_preset_actually_constructs_its_config(family, presets) -> None:
    """A typo'd FIELD name must fail here, not inside a hosted arm you just launched.

    Presets are splatted into frozen dataclasses (`DecisionConfig(**gate_overrides())`,
    `InferenceConfig(**inference_overrides())`) in `AttendMeetingMode.__init__`, so a
    bad key raises TypeError at mode construction -- mid-episode, after the upload.
    """

    from crewborg.deduction import config as cfg
    from crewborg.deduction.decision import DecisionConfig

    target = DecisionConfig if family == "gate" else InferenceConfig
    for overrides in getattr(cfg, presets).values():
        target(**overrides)  # must not raise


def test_inference_lever_families_do_not_collide() -> None:
    """The two families merge with `.update()`, so overlapping keys would silently win."""

    from crewborg.deduction.config import INFERENCE_FAMILIES

    seen: dict[str, str] = {}
    for env_var, presets in INFERENCE_FAMILIES:
        for overrides in presets.values():
            for key in overrides:
                assert key not in seen or seen[key] == env_var, (
                    f"{key} is set by both {seen.get(key)} and {env_var}"
                )
                seen[key] = env_var


# --- the LLM consult seam at the end of the deduction branch ------------------------
#
# `CREWBORG_DEDUCTION_LLM=<consult>` puts one named experiment at the end of the branch.
# What is under test here is mostly the SEAM, not any one experiment: the guarantees the
# runner owns on every consult's behalf (fall back to the solver on any failure, never
# emit an illegal vote, always leave one uniform trace) are what let the next idea be a
# new module plus an env value rather than an edit to this mode.
#
# So the framework tests below drive a deliberately trivial consult defined in the test
# file. If a future consult needs more than `payload`/`Response`/`apply` to express
# itself, one of these tests is where that should first become awkward.


class _StubLLM:
    """Minimal client: records the structured call, returns a canned response."""

    def __init__(self, response=None, *, enabled=True, raises=False):
        self.enabled = enabled
        self.disabled_reason = None if enabled else "stub disabled"
        self.timeout_seconds = 3.0
        self._response = response
        self._raises = raises
        self.calls: list[dict] = []

    def structured(self, *, system, payload, response_model, trigger, max_tokens=None):
        self.calls.append(
            {"system": system, "payload": payload, "model": response_model, "trigger": trigger}
        )
        if self._raises:
            raise RuntimeError("bedrock exploded")
        from types import SimpleNamespace

        return SimpleNamespace(
            value=self._response, model="stub", latency_ms=1.0, usage={},
            raw_request=None, raw_response=None,
        )


class _EchoResponse(BaseModel):
    """A test consult's response shape -- the whole surface an experiment declares."""

    model_config = ConfigDict(extra="forbid")

    vote: str
    say: str | None = None


class _EchoConsult(BaseConsult):
    name = "echo-test"
    Response = _EchoResponse
    defaults: ClassVar[dict] = {"veto": False, "floor": 0.0}

    def applies(self, view):
        if self.param("veto"):
            return "vetoed by params"
        if view.ranked and view.ranked[0].p < float(self.param("floor")):
            return "below floor"
        return None

    def payload(self, view):
        return {"candidates": [c.to_json() for c in view.ranked], "solver": dict(view.deterministic)}

    def apply(self, response, view):
        return ConsultOutcome(
            vote=response.vote, chat=response.say, followed_llm=True, fields={"echo": True}
        )


def _run_deduction_branch(monkeypatch, *, llm=None, spec="echo-test", events=None):
    """Drive the branch to its final vote, returning (intents, trace_sink, belief)."""

    monkeypatch.setitem(CONSULT_REGISTRY, _EchoConsult.name, _EchoConsult)
    monkeypatch.setenv("CREWBORG_DEDUCTION_HISTORY", "1")
    monkeypatch.setenv("CREWBORG_DEDUCTION_LLM", spec)
    if events is None:
        events = (
            _utterance(101, "blue", "red vented"),
            _utterance(102, "yellow", "red vented"),
            _utterance(103, "green", "red vented"),
        )
    belief = _meeting_belief_with_history(events)
    belief.suspicion = {"purple": 0.999}  # the anti-signal; must never reach the LLM
    mode = AttendMeetingMode(llm_client=llm) if llm is not None else AttendMeetingMode()
    sink = ListTraceSink()
    mode.emit = EventEmitter(sink, ListMetricsSink())

    intents = []
    # phase_start 100, timer 1200 -> remaining = 1200 - (tick - 100).
    # 1140 = 160 remaining (before the consult trigger), 1160 = 140 (inside the window,
    # and still startable), 1252 = 48 (the auto-submit backstop).
    for tick in (1140, 1160, 1252, 1252):
        belief.last_tick = tick
        intents.append(mode.decide(belief, ActionState()))
    return intents, sink, belief


def _consult_traces(sink):
    return [e for e in sink.events if e.name == f"domain.{CONSULT_TRACE_EVENT}"]


def test_deduction_consult_off_is_the_unchanged_branch(monkeypatch) -> None:
    intents, sink, _ = _run_deduction_branch(monkeypatch, llm=_StubLLM(), spec="off")
    votes = [i for i in intents if i.kind == "vote"]
    assert votes and votes[-1].target_color == "red"
    assert not _consult_traces(sink)


def test_unknown_consult_name_degrades_to_the_shipped_branch(monkeypatch) -> None:
    # A typo in `--secret-env` must run NOTHING, not silently run a different experiment
    # than the arm is named after.
    intents, sink, _ = _run_deduction_branch(
        monkeypatch, llm=_StubLLM(_EchoResponse(vote="green")), spec="shortlst"
    )
    votes = [i for i in intents if i.kind == "vote"]
    assert votes and votes[-1].target_color == "red"
    assert not _consult_traces(sink)


def test_consult_casts_the_final_vote(monkeypatch) -> None:
    llm = _StubLLM(_EchoResponse(vote="green"))
    intents, sink, _ = _run_deduction_branch(monkeypatch, llm=llm)
    votes = [i for i in intents if i.kind == "vote"]
    assert votes and votes[-1].target_color == "green"  # departed from the solver's "red"
    [trace] = _consult_traces(sink)
    assert trace.data["consult"] == "echo-test"
    assert trace.data["consulted"] is True
    assert trace.data["deterministic_vote"] == "red"
    assert trace.data["vote"] == "green"
    assert trace.data["followed_llm"] is True


def test_consult_payload_carries_the_deduction_posterior_not_the_fitted_one(monkeypatch) -> None:
    llm = _StubLLM(_EchoResponse(vote="red"))
    _run_deduction_branch(monkeypatch, llm=llm)
    assert llm.calls, "the consult never reached the client"
    call = llm.calls[-1]
    assert call["model"] is _EchoResponse
    assert call["trigger"] == "deduction_consult:echo-test"
    # belief.suspicion put purple at 0.999 -- the fitted posterior measured AUC 0.355 and
    # must not reach the model alongside the deduction posterior.
    ranked = {row["color"]: row["p"] for row in call["payload"]["candidates"]}
    assert ranked.get("purple") != 0.999
    assert "red" in ranked
    assert call["payload"]["solver"]["action"] in {"eject", "skip"}


def test_consult_call_failure_falls_back_to_the_solver(monkeypatch) -> None:
    llm = _StubLLM(_EchoResponse(vote="green"), raises=True)
    intents, sink, _ = _run_deduction_branch(monkeypatch, llm=llm)
    votes = [i for i in intents if i.kind == "vote"]
    assert votes and votes[-1].target_color == "red"
    [trace] = _consult_traces(sink)
    assert trace.data["fields"]["fallback"] == "call_failed"
    assert trace.data["followed_llm"] is False


def test_consult_illegal_vote_falls_back_to_the_solver(monkeypatch) -> None:
    # `apply` is experiment code and may be wrong; the runner is the backstop, so a bad
    # consult can lose its own effect but can never cast a vote we did not choose.
    llm = _StubLLM(_EchoResponse(vote="chartreuse"))
    intents, sink, _ = _run_deduction_branch(monkeypatch, llm=llm)
    votes = [i for i in intents if i.kind == "vote"]
    assert votes and votes[-1].target_color == "red"
    [trace] = _consult_traces(sink)
    assert trace.data["fields"]["fallback"] == "illegal_vote"


def test_disabled_client_is_the_unchanged_branch(monkeypatch) -> None:
    llm = _StubLLM(_EchoResponse(vote="green"), enabled=False)
    intents, sink, _ = _run_deduction_branch(monkeypatch, llm=llm)
    votes = [i for i in intents if i.kind == "vote"]
    assert votes and votes[-1].target_color == "red"
    assert not llm.calls
    assert not _consult_traces(sink)


def test_consult_params_come_from_the_env_spec(monkeypatch) -> None:
    # `name:key=value` is how a threshold sweep ships one image; a consult that declines
    # must cost no call at all.
    llm = _StubLLM(_EchoResponse(vote="green"))
    intents, sink, _ = _run_deduction_branch(monkeypatch, llm=llm, spec="echo-test:veto=1")
    votes = [i for i in intents if i.kind == "vote"]
    assert votes and votes[-1].target_color == "red"
    assert not llm.calls
    [trace] = _consult_traces(sink)
    assert trace.data["consulted"] is False
    assert trace.data["why"] == "vetoed by params"


def test_consult_can_convert_a_skip_into_a_vote(monkeypatch) -> None:
    # The abstention case: no evidence at all, so the solver skips. This is the ~83%
    # of decisions where added coverage has to come from, if it comes from anywhere.
    llm = _StubLLM(_EchoResponse(vote="green"))
    intents, sink, _ = _run_deduction_branch(monkeypatch, llm=llm, events=())
    votes = [i for i in intents if i.kind == "vote"]
    assert votes and votes[-1].target_color == "green"
    [trace] = _consult_traces(sink)
    assert trace.data["deterministic_vote"] == "skip"
    assert trace.data["vote"] == "green"


# --- the shortlist consult itself ---------------------------------------------------
#
# Pure, no belief and no mode: a `ConsultView` is constructible by hand, which is the
# same property that lets the offline scorer replay league meetings through the shipped
# payload and `apply`.


def _view(pairs, *, action="eject", target=None, pins=(), self_color="blue", timeline=()):
    return ConsultView(
        self_color=self_color,
        candidates=tuple(
            Candidate(c, p, murder_cleared=False, pinned=c in pins) for c, p in pairs
        ),
        joint_hypotheses=(),
        deterministic={"action": action, "target": target, "probability": max(p for _c, p in pairs)},
        timeline=tuple(timeline),
        legal_targets=tuple(sorted(c for c, _p in pairs)),
        roster=tuple(sorted(c for c, _p in pairs)),
    )


def test_shortlist_only_fires_inside_the_contested_band() -> None:
    consult = ShortlistConsult({})
    # Confident board: the posterior is already right often enough to be left alone.
    assert consult.applies(_view([("red", 0.88), ("green", 0.06)], target="red"))
    # Flat board: nothing to reorder either.
    assert consult.applies(_view([("red", 0.20), ("green", 0.18)], target=None, action="skip"))
    # Contested: this is the 50.2%-accurate band the experiment exists for.
    assert consult.applies(_view([("red", 0.48), ("green", 0.41)], target="red")) is None


def test_shortlist_declines_when_the_top_candidate_is_pinned() -> None:
    consult = ShortlistConsult({})
    view = _view([("red", 0.55), ("green", 0.30)], target="red", pins=("red",))
    assert consult.applies(view) == "top candidate is structurally pinned"


def test_shortlist_rejects_a_pick_off_the_shortlist() -> None:
    consult = ShortlistConsult({"k": "2"})
    view = _view([("red", 0.48), ("green", 0.41), ("pink", 0.09)], target="red")
    outcome = consult.apply(
        ShortlistResponse(pick="pink", confidence=0.99), view
    )
    assert outcome.vote == "red" and not outcome.followed_llm
    assert outcome.fields["declined"] == "pick_off_shortlist"


def test_shortlist_rejects_a_low_confidence_pick() -> None:
    consult = ShortlistConsult({"min_confidence": "0.6"})
    view = _view([("red", 0.48), ("green", 0.41)], target="red")
    outcome = consult.apply(ShortlistResponse(pick="green", confidence=0.4), view)
    assert outcome.vote == "red" and outcome.fields["declined"] == "below_min_confidence"


def test_promotion_is_one_parameter_in_both_directions() -> None:
    # Inside the contested band the solver votes in 5.8% of meetings, so with promotion
    # off this consult is a near-no-op -- hence the default. Both arms must remain one
    # env change apart, because whether the coverage bet pays is not yet decided.
    view = _view([("red", 0.48), ("green", 0.41)], action="skip", target=None)
    answer = ShortlistResponse(pick="red", confidence=0.9)
    loose = ShortlistConsult({}).apply(answer, view)
    assert loose.vote == "red" and loose.fields["departure"] == "skip_to_eject"
    strict = ShortlistConsult({"allow_promote": "0"}).apply(answer, view)
    assert strict.vote == "skip"
    assert strict.fields["declined"] == "would_promote_skip_to_eject"


def test_shortlist_retarget_is_recorded_as_such() -> None:
    view = _view([("red", 0.48), ("green", 0.41)], target="red")
    outcome = ShortlistConsult({}).apply(
        ShortlistResponse(pick="green", confidence=0.8, evidence=["green misplaced the body"]), view
    )
    assert outcome.vote == "green" and outcome.followed_llm
    assert outcome.fields["departure"] == "retarget"


def test_response_schema_forbids_invented_fields() -> None:
    # The contract sent to the model is the response model's own JSON Schema, so a field
    # the parser would ignore is a validation error rather than a silent drop.
    with pytest.raises(ValidationError):
        ShortlistResponse(pick="red", confidence=0.9, certainty=1.0)
    with pytest.raises(ValidationError):
        ShortlistResponse(pick="red", confidence=1.4)
    assert "pick" in ShortlistResponse.model_json_schema()["properties"]


def test_consult_spec_parsing() -> None:
    assert parse_spec("shortlist") == ("shortlist", {})
    assert parse_spec("shortlist:k=4,min_confidence=0.7") == (
        "shortlist", {"k": "4", "min_confidence": "0.7"}
    )
    assert ShortlistConsult({"k": "4"}).param("k") == 4
    assert ShortlistConsult({"nonsense": "1"}).params == ShortlistConsult({}).params


# --- the game log ---------------------------------------------------------------------
#
# This is the bulk of what the model reads, so its failure modes are prompt bugs rather
# than crashes. The one already caught in review: the CURRENT meeting was being narrated
# as "ENDED -- nobody was ejected" directly above "this is the vote you are advising",
# which tells the model the decision it is being asked for has already been taken.


def _log_view(timeline, *, tick=2000, self_color="blue"):
    return ConsultView(
        self_color=self_color,
        candidates=(Candidate("red", 0.5),),
        joint_hypotheses=(),
        deterministic={"action": "skip", "target": None},
        timeline=tuple(timeline),
        legal_targets=("red",),
        roster=("blue", "green", "red"),
        imposter_count=1,
        tick=tick,
    )


def _closed_meeting():
    return [
        GameEvent(400, "meeting", actor="blue", detail="body", meeting_id=1),
        GameEvent(400, "death", actor="green", detail="body"),
        GameEvent(420, "utterance", actor="red", text="I was in Med Bay", meeting_id=1),
        GameEvent(470, "vote", actor="blue", target="red", meeting_id=1),
        GameEvent(470, "vote", actor="red", target="skip", meeting_id=1),
        GameEvent(480, "death", actor="red", detail="ejection"),
    ]


def test_game_log_narrates_a_finished_meeting_and_its_outcome() -> None:
    log = "\n".join(_log_view(_closed_meeting()).game_log())
    assert "GAME START. 3 players" in log and "You are blue (crewmate)." in log
    assert "MEETING 1 called by blue (a body was reported)" in log
    assert "BODY FOUND: green is dead" in log
    assert 'red: "I was in Med Bay"' in log
    assert "meeting 1 VOTES  blue->red | red->skip" in log
    assert "MEETING 1 ENDED -- red was ejected" in log


def test_game_log_never_narrates_the_current_meeting_as_ended() -> None:
    timeline = [
        *_closed_meeting(),
        GameEvent(1900, "meeting", actor="green", detail="button", meeting_id=2),
        GameEvent(1910, "vote", actor="blue", target="skip", meeting_id=2),
    ]
    log = "\n".join(_log_view(timeline).game_log())
    assert "MEETING 2 IS IN PROGRESS RIGHT NOW" in log
    assert "MEETING 2 ENDED" not in log
    assert "meeting 2 votes so far: blue->skip" in log
    # the earlier meeting still closes normally
    assert "MEETING 1 ENDED -- red was ejected" in log


def test_game_log_distinguishes_how_each_death_became_known() -> None:
    timeline = [
        GameEvent(300, "death", actor="green", detail="body"),
        GameEvent(900, "death", actor="red", detail="census"),
    ]
    log = "\n".join(_log_view(timeline).game_log())
    assert "BODY FOUND: green is dead" in log
    assert "NOTED DEAD: red (missing at roll call)" in log


def test_offline_row_and_live_history_agree_on_the_timeline() -> None:
    # The parity guarantee: a consult scored offline must be reading what a pod builds.
    history = _history(
        _utterance(101, "blue", "red vented", meeting_id=1),
        DeathObserved(event_id="d1", tick=150, color="green", source="body"),
    )
    live = ConsultView.from_deduction(
        decide(history), history=history, legal_targets=("red",), tick=200
    )
    replayed = ConsultView.from_row({
        "marginals": dict(live.ranked and [(c.color, c.p) for c in live.candidates]),
        "timeline": [e.to_json() for e in live.timeline],
        "roster": list(live.roster),
        "self_color": live.self_color,
        "imposter_count": live.imposter_count,
        "tick": live.tick,
        "action": live.deterministic["action"],
        "target": live.deterministic["target"],
    })
    assert replayed.timeline == live.timeline
    assert replayed.game_log() == live.game_log()
