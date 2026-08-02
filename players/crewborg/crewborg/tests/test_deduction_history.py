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


def _accusation_history(count: int):
    """`count` distinct speakers independently naming red, in one meeting."""

    speakers = ("blue", "yellow", "green", "pink", "purple", "orange")[:count]
    return _history(
        *(_utterance(101 + i, s, "red vented") for i, s in enumerate(speakers)),
        players=PLAYERS + ("orange", "cyan"),
    )


_EIGHT_LIVE = tuple(
    color for color in PLAYERS + ("orange", "cyan") if color != "white"
)


def test_independent_accusers_can_drive_a_vote() -> None:
    """The independence mechanism, isolated from how hard social evidence is damped.

    `social_weight` is pinned here rather than inherited: it is a temperature fitted to
    league calibration and is expected to move, and letting it leak in would turn a
    refit into three silent test failures that look like a broken mechanism.
    """

    decision = decide(
        _accusation_history(3),
        live_targets=_EIGHT_LIVE,
        inference_config=InferenceConfig(social_weight=1.0),
    )

    assert decision.action == "eject"
    assert decision.target == "red"
    assert decision.sources == ("blue", "green", "yellow")


def test_fitted_social_weight_needs_the_lower_bar_to_act_on_chat_alone() -> None:
    """What the fitted damping actually costs, pinned so a refit has to face it.

    At the fitted weight three independent accusations land between the champion's bar
    (`loose+p40`, base 0.40) and the default 0.65. So chat-only ejects survive only
    because the bar was repriced: the two constants are COUPLED, and moving either one
    alone changes whether social evidence can ever act by itself.

    The weight is asserted to lie in the fitted PLATEAU rather than to equal one value.
    Calibration cannot separate points inside [0.275, 0.450] -- the binomial standard
    error on a bin is about as large as the differences between them -- so pinning an
    exact constant would fail on every legitimate refit while catching nothing real.
    """

    from crewborg.deduction.decision import DecisionConfig

    history = _accusation_history(3)
    fitted = InferenceConfig()
    assert 0.275 <= fitted.social_weight <= 0.450, (
        f"{fitted.social_weight} is outside the calibrated plateau; refit before shipping"
    )

    shipped_bar = decide(history, live_targets=_EIGHT_LIVE)
    champion_bar = decide(
        history,
        live_targets=_EIGHT_LIVE,
        decision_config=DecisionConfig(
            base_probability=0.40, base_margin=1e-3, require_support=False
        ),
    )

    assert 0.40 < shipped_bar.probability < 0.65, shipped_bar.probability
    assert shipped_bar.action == "skip"
    assert champion_bar.action == "eject"
    assert champion_bar.target == "red"


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
    # Undamped on purpose: the point is that the SUPPORT rule refuses this pile even
    # when the posterior is over the bar. Under the fitted `social_weight` the pile
    # would fall short of the bar too, and the test would pass without exercising the
    # rule it is named for.
    decision = decide(
        _history(*events, players=eight_players),
        live_targets=tuple(color for color in eight_players if color != "white"),
        inference_config=InferenceConfig(social_weight=1.0),
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
    # This is a wiring test -- that the meeting mode routes through the history posterior
    # instead of legacy suspicion. Pin the temperature so it keeps testing the wiring
    # when the fitted value moves.
    monkeypatch.setenv("CREWBORG_SOCIAL_WEIGHT", "1.0")
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
    # The social weight and the kill window compose without colliding.
    mixed = inference_overrides(
        {"CREWBORG_KILL_WINDOW": "margin", "CREWBORG_SOCIAL_WEIGHT": "0.5"}
    )
    assert mixed["kill_range_margin"] == 6 and mixed["social_weight"] == 0.5


@pytest.mark.parametrize(
    ("family", "presets"),
    [
        ("gate", "GATE_PRESETS"),
        ("kill_window", "KILL_WINDOW_PRESETS"),
        ("ejection_liveness", "EJECTION_LIVENESS_PRESETS"),
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
    # These tests are about the consult SEAM, not about how hard social evidence is
    # damped. `social_weight` is a temperature fitted to league calibration and is
    # expected to move; at the fitted value the three accusations below sit under the
    # bar, so the branch would skip and every assertion about the final vote would fail
    # for a reason that has nothing to do with the consult.
    monkeypatch.setenv("CREWBORG_SOCIAL_WEIGHT", "1.0")
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


def _view(
    pairs,
    *,
    action="eject",
    target=None,
    pins=(),
    self_color="blue",
    timeline=(),
    cleared=(),
    legal=None,
):
    """`legal` defaults to everyone -- pass it to bury a player the posterior still likes."""

    return ConsultView(
        self_color=self_color,
        candidates=tuple(
            Candidate(c, p, murder_cleared=c in cleared, pinned=c in pins)
            for c, p in pairs
        ),
        joint_hypotheses=(),
        deterministic={"action": action, "target": target, "probability": max(p for _c, p in pairs)},
        timeline=tuple(timeline),
        legal_targets=(
            tuple(sorted(c for c, _p in pairs)) if legal is None else tuple(legal)
        ),
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


# --- liveness: a consult may never be shown a corpse ---------------------------------
#
# The failure these pin down is not hypothetical. `ranked` used to sort the solver's whole
# marginal vector, which spans the dead, and an EJECTED player keeps their probability
# because ejection reveals no role. Over 6,829 league meetings (2026-08-01) that put a
# dead player on the shipped three-name shortlist in 15.3% of consult-eligible meetings,
# at the TOP of it in 7.9%, and in 92-97% of meetings once an impostor had been ejected --
# the ejected impostor is precisely the player the evidence points at hardest.


def _ejected_view():
    """`red` was voted out last meeting and the posterior still likes them for it."""

    return _view(
        [("red", 0.62), ("green", 0.44), ("pink", 0.31)],
        target="green",
        timeline=(GameEvent(400, "death", actor="red", detail="ejection"),),
        legal=("green", "pink"),
    )


def test_ranked_excludes_the_dead_however_suspicious() -> None:
    view = _ejected_view()
    assert [c.color for c in view.ranked] == ["green", "pink"]
    assert "red" not in {c.color for c in view.top(3)}
    # The full vector is still there for a consult that wants it -- only the votable
    # projection is filtered.
    assert "red" in {c.color for c in view.candidates}


def test_shortlist_never_offers_an_ejected_player_as_a_pick() -> None:
    consult = ShortlistConsult({})
    view = _ejected_view()
    assert "red" not in consult.payload(view)["allowed_picks"]
    outcome = consult.apply(ShortlistResponse(pick="red", confidence=0.99), view)
    assert outcome.vote == "green" and not outcome.followed_llm
    assert outcome.fields["declined"] == "pick_off_shortlist"


def test_the_contested_band_is_measured_on_the_top_LIVE_candidate() -> None:
    """A dead leader used to push the board out of the band and silence the consult.

    `red` at 0.62 is inside 0.35-0.65 and would have been the top of `ranked`, so the
    band test passed for the wrong reason. With `red` buried the question the consult
    actually faces is green-vs-pink at 0.44, which is squarely the coin-flip band this
    experiment exists for.
    """

    assert ShortlistConsult({}).applies(_ejected_view()) is None
    # And a board whose only LIVE candidate is one player is not a reordering problem.
    solo = _view(
        [("red", 0.62), ("green", 0.44)],
        target="green",
        timeline=(GameEvent(400, "death", actor="red", detail="ejection"),),
        legal=("green",),
    )
    assert ShortlistConsult({}).applies(solo) == "fewer than two live candidates"


def test_offline_rows_bury_an_ejected_player_that_still_has_probability() -> None:
    """The parity guarantee, on the case that broke it.

    `p > 0` was the old offline liveness rule. A murdered player is zeroed by
    `murder_clears` and so read as dead, but an ejected one keeps their mass and read as
    ALIVE -- so the scorer accepted a vote for a corpse that a pod would have thrown away
    as an illegal target, and `pick in imposters` then scored it CORRECT.
    """

    row = {
        "marginals": {"red": 0.62, "green": 0.44, "pink": 0.31, "cyan": 0.0},
        "murder_clears": ["cyan"],
        "roster": ["blue", "red", "green", "pink", "cyan"],
        "self_color": "blue",
        "tick": 900,
        "timeline": [
            {"tick": 400, "kind": "death", "actor": "red", "detail": "ejection"},
            {"tick": 500, "kind": "death", "actor": "cyan", "detail": "body"},
            # After the decision tick, so it has not happened yet.
            {"tick": 950, "kind": "death", "actor": "pink", "detail": "body"},
        ],
        "action": "eject",
        "target": "green",
    }
    view = ConsultView.from_row(row)
    assert view.legal_targets == ("green", "pink")
    assert not view.is_legal("red") and not view.is_legal("cyan")
    assert view.is_legal("pink")
    assert [c.color for c in view.ranked] == ["green", "pink"]


def test_payload_and_apply_read_the_same_shortlist() -> None:
    """They diverged: `payload` dropped `murder_cleared`, `apply` did not.

    A model could therefore name a player it was never shown and be obeyed. Both now go
    through `_shortlist`, so the offered set and the accepted set cannot drift.
    """

    consult = ShortlistConsult({"k": "3"})
    view = _view(
        [("red", 0.48), ("green", 0.41), ("pink", 0.30)], target="red", cleared=("pink",)
    )
    assert "pink" not in consult.payload(view)["allowed_picks"]
    outcome = consult.apply(ShortlistResponse(pick="pink", confidence=0.99), view)
    assert outcome.fields["declined"] == "pick_off_shortlist"


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


def _eject(color: str, tick: int) -> DeathObserved:
    return DeathObserved(
        event_id=f"eject:{color}", tick=tick, color=color, source="ejection"
    )


def test_ejection_liveness_is_on_by_default() -> None:
    """Default-on since 2026-07-30: scoring an already-won game is simply wrong.

    Every other preset family degrades to shipped behaviour when unset. This one
    degrades to ON, deliberately -- it is a soundness property of the game rather than
    a variant of the solver.
    """

    history = _history(_eject("red", 10), _eject("blue", 20))
    shipped = derive_evidence(history)
    assert shipped.ejected == frozenset({"red", "blue"})

    table = build_assignment_table(history, shipped)
    reasons = [r for item in table.excluded for r in item.reasons]
    assert any(r == "all_imposters_ejected" for r in reasons)


def test_ejection_liveness_off_restores_the_old_posterior() -> None:
    """`=off` must reach the byte-identical pre-2026-07-30 path, with no rebuild."""

    history = _history(_eject("red", 10), _eject("blue", 20))
    config = InferenceConfig(ejection_liveness=False)
    shipped = derive_evidence(history, config=config)
    assert shipped.ejected == frozenset()

    table = build_assignment_table(history, shipped)
    reasons = [r for item in table.excluded for r in item.reasons]
    assert not any(r == "all_imposters_ejected" for r in reasons)
    assert table.eligible == build_assignment_table(
        _history(), derive_evidence(_history(), config=config)
    ).eligible


def test_ejection_liveness_excludes_a_fully_ejected_pair() -> None:
    """If both hypothesised impostors were voted out, the crew would already have won."""

    config = InferenceConfig(ejection_liveness=True)
    history = _history(_eject("red", 10), _eject("blue", 20))
    evidence = derive_evidence(history, config=config)
    assert evidence.ejected == frozenset({"red", "blue"})

    table = build_assignment_table(history, evidence)
    excluded = {item.imposters: item.reasons for item in table.excluded}
    assert ("red", "blue") in excluded
    assert "all_imposters_ejected" in excluded[("red", "blue")]
    # It removes exactly that one assignment and nothing else.
    assert [
        pair for pair, reasons in excluded.items()
        if "all_imposters_ejected" in reasons
    ] == [("red", "blue")]
    assert ("red", "blue") not in set(table.eligible)


def test_one_ejection_alone_proves_nothing() -> None:
    """SOUNDNESS. The engine reveals no role on ejection, so a single ejection is
    not evidence about that player. Only the whole impostor set being gone is."""

    config = InferenceConfig(ejection_liveness=True)
    history = _history(_eject("red", 10))
    table = build_assignment_table(history, derive_evidence(history, config=config))

    reasons = [r for item in table.excluded for r in item.reasons]
    assert not any(r == "all_imposters_ejected" for r in reasons)
    # `red` is still a live suspect in every pair that contains it.
    assert any("red" in pair for pair in table.eligible)


def test_ejection_liveness_never_empties_the_hypothesis_space() -> None:
    """It only ever removes assignments, so it must not be able to remove them all."""

    config = InferenceConfig(ejection_liveness=True)
    history = _history(*[_eject(color, 10 + i) for i, color in enumerate(PLAYERS[1:])])
    table = build_assignment_table(history, derive_evidence(history, config=config))
    # Every candidate ejected is degenerate and cannot happen in a live game, but the
    # solver must degrade to an error rather than to a silently confident posterior.
    result = score_assignments(table, config=config)
    assert not table.eligible
    assert table.error is not None
    assert all(value == 0.0 for _color, value in result.marginals)


def test_ejection_liveness_preset_is_its_own_env_var() -> None:
    """A fourth independent family, so an A/B still moves one thing."""

    from crewborg.deduction.config import inference_overrides

    assert inference_overrides({"CREWBORG_EJECTION_LIVENESS": "on"}) == {
        "ejection_liveness": True
    }
    # `off` is now an explicit override rather than an absence, because the field
    # defaults to True. A typo still yields no override -- which for this family means
    # it lands on ON, unlike every other family where it lands on shipped behaviour.
    assert inference_overrides({"CREWBORG_EJECTION_LIVENESS": "off"}) == {
        "ejection_liveness": False
    }
    assert inference_overrides({"CREWBORG_EJECTION_LIVENESS": "typo"}) == {}
    assert InferenceConfig().ejection_liveness is True
    mixed = inference_overrides(
        {"CREWBORG_EJECTION_LIVENESS": "on", "CREWBORG_KILL_WINDOW": "both"}
    )
    assert mixed["ejection_liveness"] is True and mixed["kill_range_margin"] == 6


def test_recorded_trace_re_scores_to_the_recorded_posterior() -> None:
    """Re-scoring a trace from its own serialised evidence must reproduce its marginals.

    This is what makes an offline claim falsifiable: `crewrift-analysis` fits and sweeps
    `social_weight` by rebuilding recorded decisions rather than replaying episodes, and
    that is only sound while this holds. `evidence[].weight` is recorded PRE-weighting, so
    the rebuild multiplies by `config.social_weight` -- a config constant, which is why it
    needs nothing serialised beyond the audit.
    """

    import itertools
    import math

    config = InferenceConfig()
    rng = random.Random(20260728)
    checked = 0
    for _ in range(40):
        game = generate_game(rng)
        result = infer(game.history, config=config)
        trace = result.as_trace()
        if trace.get("error") or not trace["marginals"]:
            continue
        excluded = {frozenset(x["imposters"]) for x in trace["excluded"]}
        players = sorted(trace["marginals"])

        log_w: dict[frozenset[str], float] = {}
        for pair in itertools.combinations(players, 2):
            hyp = frozenset(pair)
            if hyp in excluded:
                continue
            total = 0.0
            for ev in trace["evidence"]:
                if ev["status"] != "active" or not ev["source"] or not ev["targets"]:
                    continue
                weight = ev["weight"] * config.social_weight
                if weight <= 0.0:
                    continue
                if ev["channel"] == "vote":
                    like = _vote_likelihood(hyp, ev["source"], ev["targets"][0], config)
                elif ev["channel"] == "claim":
                    like = _claim_likelihood(
                        hyp, ev["source"], tuple(ev["targets"]), ev["stance"], config
                    )
                else:
                    continue
                total += weight * math.log(max(like, 1e-9))
            log_w[hyp] = total
        if not log_w:
            continue
        hi = max(log_w.values())
        weights = {h: math.exp(v - hi) for h, v in log_w.items()}
        z = sum(weights.values())
        rebuilt: dict[str, float] = {}
        for hyp, weight in weights.items():
            for color in hyp:
                rebuilt[color] = rebuilt.get(color, 0.0) + weight / z

        for color, recorded in trace["marginals"].items():
            assert rebuilt.get(color, 0.0) == pytest.approx(recorded, abs=0.02), (
                f"re-score diverged on {color}: "
                f"{rebuilt.get(color, 0.0):.4f} vs recorded {recorded:.4f}"
            )
        checked += 1
    assert checked >= 20, f"only {checked} games produced a scorable posterior"


def _claim_likelihood(hyp, source, targets, stance, cfg) -> float:
    """Mirrors `_actor_claim_probability`; duplicated so the test is a real check."""

    actor_imp = source in hyp
    target_imp = any(t in hyp for t in targets)
    if stance in {"accuse", "at_least_one"}:
        if actor_imp:
            return cfg.imp_accuse_partner if target_imp else cfg.imp_accuse_crew
        return cfg.crew_accuse_hit if target_imp else cfg.crew_accuse_miss
    if actor_imp:
        return cfg.imp_defend_partner if target_imp else cfg.imp_defend_crew
    return cfg.crew_defend_imp if target_imp else cfg.crew_defend_crew


def _vote_likelihood(hyp, voter, target, cfg) -> float:
    voter_imp = voter in hyp
    target_imp = target in hyp
    if voter_imp:
        return cfg.imp_vote_partner if target_imp else cfg.imp_vote_crew
    return cfg.crew_vote_imp if target_imp else cfg.crew_vote_crew


# --- Lever #2: the skip-vote likelihood -------------------------------------------


def _ballot(event_id: str, voter: str, target: str | None, meeting_id: int = 0):
    return VoteObserved(
        event_id=event_id, tick=10, meeting_id=meeting_id, voter=voter, target=target
    )


def test_skip_ballot_is_discarded_unless_the_lever_is_on() -> None:
    """Default off: the shipped posterior must be exactly unchanged."""

    evidence = derive_evidence(_history(_ballot("v1", "red", None)))

    assert not evidence.votes
    [entry] = [a for a in evidence.audit if a.evidence_id == "vote:v1"]
    assert entry.status == "ignored"
    assert entry.reason == "skip vote has no target likelihood"


def test_skip_ballot_becomes_evidence_about_the_voter() -> None:
    evidence = derive_evidence(
        _history(_ballot("v1", "red", None)),
        config=InferenceConfig(skip_vote_likelihood=True),
    )

    [vote] = evidence.votes
    assert vote.voter == "red" and vote.target is None
    [entry] = [a for a in evidence.audit if a.evidence_id == "vote:v1"]
    assert entry.status == "active"
    assert entry.targets == (), "a skip names nobody"


def test_skipping_is_evidence_the_voter_is_CREW() -> None:
    """P(skip|crew)=0.50 against P(skip|impostor)=0.24, so a skip lowers suspicion."""

    history = _history(_ballot("v1", "red", None))
    before = infer(history)
    after = infer(history, config=InferenceConfig(skip_vote_likelihood=True))

    def mass(result) -> float:
        return sum(h.probability for h in result.hypotheses if "red" in h.imposters)

    assert mass(after) < mass(before), "a skip must make the voter LESS suspicious"


def test_our_own_skip_is_still_not_evidence() -> None:
    """`white` is the seat itself; its own ballot tells it nothing it did not know."""

    evidence = derive_evidence(
        _history(_ballot("v1", "white", None)),
        config=InferenceConfig(skip_vote_likelihood=True),
    )

    assert not evidence.votes
    [entry] = [a for a in evidence.audit if a.evidence_id == "vote:v1"]
    assert entry.reason == "own derived vote is not new evidence"


def test_repeated_skips_decay_like_repeated_targets() -> None:
    """A habitual skipper is one habit, not N independent observations."""

    evidence = derive_evidence(
        _history(
            _ballot("v1", "red", None, meeting_id=0),
            _ballot("v2", "red", None, meeting_id=1),
        ),
        config=InferenceConfig(skip_vote_likelihood=True),
    )

    first, second = sorted(evidence.votes, key=lambda v: v.evidence_id)
    assert second.weight < first.weight


def test_social_weight_sharpens_without_reordering() -> None:
    """The defining property: it is a TEMPERATURE, not a re-ranking.

    `log_weight` sums claims and votes only -- structural evidence acts by removing
    pairs from `eligible`, never by adding to the sum -- so one scalar over every social
    contribution scales every hypothesis's log weight equally. The softmax then sharpens
    or flattens while the ORDER is untouched. This is why the knob moves coverage far
    more than precision, and it is the reason it can be fitted to calibration alone.
    """

    history = _history(
        _utterance(1, "red", "blue sus", meeting_id=0),
        _ballot("v1", "green", "blue", meeting_id=0),
        _ballot("v2", "pink", "cyan", meeting_id=0),
    )
    low = infer(history, config=InferenceConfig(social_weight=0.13))
    high = infer(history, config=InferenceConfig(social_weight=1.0))

    order_low = [h.imposters for h in low.hypotheses]
    order_high = [h.imposters for h in high.hypotheses]
    assert order_low == order_high, "a temperature change must not reorder hypotheses"
    assert max(h.probability for h in high.hypotheses) > max(
        h.probability for h in low.hypotheses
    ), "the larger weight must be the sharper posterior"


def test_social_weight_zero_leaves_the_posterior_flat() -> None:
    """0.0 means 'ignore social evidence', and must be exactly uniform.

    The structural layer still runs -- eligibility is unaffected -- so this is the clean
    baseline for asking what our ejects are worth on hard constraints alone.
    """

    result = infer(
        _history(
            _utterance(1, "red", "blue sus", meeting_id=0),
            _ballot("v1", "green", "blue", meeting_id=0),
        ),
        config=InferenceConfig(social_weight=0.0),
    )

    probabilities = {round(h.probability, 9) for h in result.hypotheses}
    assert len(probabilities) == 1, "no social evidence can distinguish the hypotheses"


def test_social_weight_env_rejects_out_of_range_and_junk() -> None:
    """An unusable value must degrade to the shipped default, never to a clamp.

    Clamping would silently run an arm nobody chose, and this scalar sets how sharp the
    entire posterior is -- so a typo would quietly change every decision.
    """

    from crewborg.deduction.config import inference_overrides

    assert inference_overrides({"CREWBORG_SOCIAL_WEIGHT": "0.13"}) == {
        "social_weight": 0.13
    }
    assert inference_overrides({"CREWBORG_SOCIAL_WEIGHT": "0"}) == {"social_weight": 0.0}
    for junk in ("", "  ", "abc", "-0.5", "99", "1e9", "nan"):
        assert inference_overrides({"CREWBORG_SOCIAL_WEIGHT": junk}) == {}, junk


def test_lower_bar_presets_keep_the_override_ordering() -> None:
    """The three bar constants must stay ordered, or a branch inverts its own purpose.

    `decide` overrides the bar with ABSOLUTE values:
        skip_loss >= cutoff      -> forced_vote_probability
        wrong_eject_loss > 0     -> dangerous_wrong_eject_probability
    `forced_vote_probability` exists to make us vote MORE readily when skipping is what
    loses the game. Lowering `base_probability` past it turns that branch into a bar
    RAISE -- which is exactly what a Gate 1 smoke caught at base 0.40 against the
    shipped 0.51. So every lower-bar preset has to carry it down too.
    """

    from crewborg.deduction.config import gate_overrides
    from crewborg.deduction.decision import DecisionConfig

    shipped = DecisionConfig()
    assert shipped.forced_vote_probability < shipped.base_probability
    assert shipped.base_probability < shipped.dangerous_wrong_eject_probability

    for preset, bar in (("loose+p40", 0.40), ("loose+p30", 0.30),
                        ("loose+bayes", 0.30)):
        got = gate_overrides({"CREWBORG_DECISION_GATE": preset})
        cfg = DecisionConfig(**got)
        assert cfg.base_probability == bar
        assert cfg.forced_vote_probability < cfg.base_probability, preset
        assert cfg.base_probability < cfg.dangerous_wrong_eject_probability, preset
        # Nothing outside the three bar constants moves: this is ONE lever.
        loose = gate_overrides({"CREWBORG_DECISION_GATE": "loose"})
        extra = {k: v for k, v in got.items()
                 if k not in ("base_probability", "forced_vote_probability",
                              "dangerous_wrong_eject_probability")}
        assert extra == loose


def test_forced_vote_constant_is_inert_but_must_not_invert() -> None:
    """Measured over 5279 league decisions, `forced_vote_probability` changes nothing.

    0.04, 0.21 and 0.40 give bit-identical coverage, precision and value at base 0.30,
    because the branch fires on 5.9% of decisions and never binds. It is kept below
    `base` anyway: an inverted branch is a latent bug the moment someone moves `base`,
    which is exactly how a Gate 1 smoke caught it at 0.40 against the shipped 0.51.
    """

    from crewborg.deduction.config import gate_overrides
    from crewborg.deduction.decision import DecisionConfig

    for preset in ("loose+p40", "loose+p30", "loose+bayes"):
        cfg = DecisionConfig(**gate_overrides({"CREWBORG_DECISION_GATE": preset}))
        assert cfg.forced_vote_probability < cfg.base_probability, preset

# --- CREWBORG_VOTE_COMMIT: when the ballot is cast --------------------------
#
# The shipped path holds the vote to the 48-tick backstop, tick ~1152 of 1200.
# Measured over 17,648 league meetings, that is after every other seat has voted:
# `vote_aft` is zero in 100% of our ballots, so nothing can follow our dot, while
# five league policies demonstrably do follow the visible board and all commit by
# tick ~315. `on-pin` moves an eject forward to the early solve that already runs
# at tick 240. See `deduction/config.py::VOTE_COMMIT_PRESETS`.


def _early_meeting_belief(events: tuple) -> Belief:
    """A belief past the early-solve tick (240) but far from the backstop."""

    belief = _meeting_belief_with_history(events)
    belief.last_tick = belief.phase_start_tick + 400   # remaining 800, age 400
    return belief


def test_vote_commit_defaults_to_backstop_and_holds_the_vote(monkeypatch) -> None:
    """Unset, the early solve still only talks -- the unflagged path is unchanged."""

    monkeypatch.setenv("CREWBORG_DEDUCTION_HISTORY", "1")
    monkeypatch.setenv("CREWBORG_SOCIAL_WEIGHT", "1.0")
    monkeypatch.delenv("CREWBORG_VOTE_COMMIT", raising=False)
    belief = _early_meeting_belief((
        _utterance(101, "blue", "red vented"),
        _utterance(102, "yellow", "red vented"),
        _utterance(103, "green", "red vented"),
    ))
    mode = AttendMeetingMode()
    mode.emit = EventEmitter(ListTraceSink(), ListMetricsSink())

    first = mode.decide(belief, ActionState())
    second = mode.decide(belief, ActionState())

    assert first.kind == "chat"
    # Still 752 ticks from the backstop, so shipped behaviour waits.
    assert second.kind == "idle"


def test_vote_commit_on_pin_submits_at_the_early_solve(monkeypatch) -> None:
    """`on-pin` casts the ballot right after the early accusation goes out."""

    monkeypatch.setenv("CREWBORG_DEDUCTION_HISTORY", "1")
    monkeypatch.setenv("CREWBORG_SOCIAL_WEIGHT", "1.0")
    monkeypatch.setenv("CREWBORG_VOTE_COMMIT", "on-pin")
    belief = _early_meeting_belief((
        _utterance(101, "blue", "red vented"),
        _utterance(102, "yellow", "red vented"),
        _utterance(103, "green", "red vented"),
    ))
    mode = AttendMeetingMode()
    sink = ListTraceSink()
    mode.emit = EventEmitter(sink, ListMetricsSink())

    chat = mode.decide(belief, ActionState())
    vote = mode.decide(belief, ActionState())

    assert chat.kind == "chat"
    assert vote.kind == "vote"
    assert vote.target_color == "red"
    # It must still emit a decision record, or every downstream audit reads the
    # treatment arm as having made no decisions at all.
    [trace] = [
        event for event in sink.events
        if event.name == "domain.deduction_history_decision"
    ]
    assert trace.data["committed_early"] is True
    assert trace.data["remaining_ticks"] == 800


def test_vote_commit_on_pin_never_commits_a_skip_early(monkeypatch) -> None:
    """A declined early solve falls through to the backstop, unchanged.

    This is what makes the lever one-directional: it can move an eject forward in
    time but can never turn a considered skip into an early one, so the skip path
    is byte-identical to shipped.
    """

    monkeypatch.setenv("CREWBORG_DEDUCTION_HISTORY", "1")
    monkeypatch.setenv("CREWBORG_VOTE_COMMIT", "on-pin")
    belief = _early_meeting_belief(())        # no evidence -> nothing to eject
    mode = AttendMeetingMode()
    mode.emit = EventEmitter(ListTraceSink(), ListMetricsSink())

    for _ in range(3):
        intent = mode.decide(belief, ActionState())
        assert intent.kind != "vote"


def test_vote_commit_preset_degrades_to_backstop() -> None:
    """A typo must land on shipped behaviour, like every other preset family."""

    from crewborg.deduction.config import vote_commit

    assert vote_commit({}) == "backstop"
    assert vote_commit({"CREWBORG_VOTE_COMMIT": "on-pin"}) == "on-pin"
    assert vote_commit({"CREWBORG_VOTE_COMMIT": "ON-PIN"}) == "on-pin"
    assert vote_commit({"CREWBORG_VOTE_COMMIT": "asap"}) == "backstop"
    assert vote_commit({"CREWBORG_VOTE_COMMIT": ""}) == "backstop"
