"""Reactive self-preservation mode tests."""

from __future__ import annotations

from crewborg.deduction.inference import InferenceResult
from crewborg.modes.self_preservation import SelfPreservationMode, enabled
from crewborg.types import ActionState, Belief, PlayerRecord


def _belief() -> Belief:
    return Belief(
        phase="Playing",
        self_role="crewmate",
        self_color="pink",
        self_world_x=100,
        self_world_y=100,
        self_alive=True,
        last_tick=10,
        total_player_count=5,
        imposter_count=1,
    )


def _player(
    belief: Belief,
    color: str,
    xy: tuple[int, int],
    *,
    tick: int | None = None,
) -> None:
    belief.roster[color] = PlayerRecord(
        color=color,
        world_x=xy[0],
        world_y=xy[1],
        last_seen_tick=belief.last_tick if tick is None else tick,
        life_status="alive",
    )


def _result(
    marginals: dict[str, float],
    *,
    pins: tuple[str, ...] = (),
) -> InferenceResult:
    return InferenceResult(
        marginals=tuple(marginals.items()),
        hypotheses=(),
        excluded=(),
        evidence=(),
        pins=pins,
        murder_clears=(),
    )


def _risky_belief() -> Belief:
    belief = _belief()
    _player(belief, "red", (120, 100))
    _player(belief, "blue", (500, 500))
    _player(belief, "green", (520, 500))
    return belief


def test_enabled_reads_separate_flag(monkeypatch) -> None:
    monkeypatch.delenv("CREWBORG_SELF_PRESERVATION", raising=False)
    monkeypatch.setenv("CREWBORG_DEDUCTION_HISTORY", "1")
    assert enabled() is False
    monkeypatch.setenv("CREWBORG_SELF_PRESERVATION", "1")
    assert enabled() is True


def test_enabled_requires_deduction_history(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_SELF_PRESERVATION", "1")
    monkeypatch.delenv("CREWBORG_DEDUCTION_HISTORY", raising=False)

    assert enabled() is False


def test_high_posterior_one_on_one_routes_to_two_player_group(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_SELF_PRESERVATION", "1")
    monkeypatch.setenv("CREWBORG_DEDUCTION_HISTORY", "1")
    monkeypatch.setattr(
        "crewborg.modes.self_preservation.infer",
        lambda history: _result({"red": 0.82, "blue": 0.09, "green": 0.09}),
    )
    intent = SelfPreservationMode().decide(_risky_belief(), ActionState())

    assert intent.kind == "navigate_to"
    assert intent.point in {(500, 500), (520, 500)}
    assert intent.target_color == "red"
    assert "P(imposter)=0.820" in intent.reason


def test_structural_pin_routes_even_below_probability_bar(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_SELF_PRESERVATION", "1")
    monkeypatch.setenv("CREWBORG_DEDUCTION_HISTORY", "1")
    monkeypatch.setattr(
        "crewborg.modes.self_preservation.infer",
        lambda history: _result(
            {"red": 0.4, "blue": 0.3, "green": 0.3},
            pins=("red",),
        ),
    )
    intent = SelfPreservationMode().decide(_risky_belief(), ActionState())

    assert intent.kind == "navigate_to"
    assert intent.target_color == "red"


def test_weak_one_on_one_suspicion_keeps_tasking(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_SELF_PRESERVATION", "1")
    monkeypatch.setenv("CREWBORG_DEDUCTION_HISTORY", "1")
    monkeypatch.setattr(
        "crewborg.modes.self_preservation.infer",
        lambda history: _result({"red": 0.5, "blue": 0.25, "green": 0.25}),
    )
    intent = SelfPreservationMode().decide(_risky_belief(), ActionState())

    assert "self preservation" not in intent.reason


def test_current_witness_prevents_escape(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_SELF_PRESERVATION", "1")
    monkeypatch.setenv("CREWBORG_DEDUCTION_HISTORY", "1")
    monkeypatch.setattr(
        "crewborg.modes.self_preservation.infer",
        lambda history: _result({"red": 0.9, "blue": 0.05, "green": 0.05}),
    )
    belief = _risky_belief()
    _player(belief, "blue", (125, 100))

    intent = SelfPreservationMode().decide(belief, ActionState())

    assert "self preservation" not in intent.reason


def test_no_fresh_two_player_destination_keeps_tasking(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_SELF_PRESERVATION", "1")
    monkeypatch.setenv("CREWBORG_DEDUCTION_HISTORY", "1")
    monkeypatch.setattr(
        "crewborg.modes.self_preservation.infer",
        lambda history: _result({"red": 0.9, "blue": 0.05, "green": 0.05}),
    )
    belief = _risky_belief()
    belief.roster["blue"].last_seen_tick = -100
    belief.roster["green"].last_seen_tick = -100

    intent = SelfPreservationMode().decide(belief, ActionState())

    assert "self preservation" not in intent.reason


def test_commitment_ends_when_a_witness_arrives(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_SELF_PRESERVATION", "1")
    monkeypatch.setenv("CREWBORG_DEDUCTION_HISTORY", "1")
    monkeypatch.setattr(
        "crewborg.modes.self_preservation.infer",
        lambda history: _result({"red": 0.82, "blue": 0.09, "green": 0.09}),
    )
    mode = SelfPreservationMode()
    belief = _risky_belief()
    assert "self preservation" in mode.decide(belief, ActionState()).reason

    belief.last_tick = 11
    belief.roster["red"].last_seen_tick = 11
    belief.roster["red"].world_x = 121
    assert "self preservation" in mode.decide(belief, ActionState()).reason

    belief.last_tick = 12
    belief.roster["red"].last_seen_tick = 12
    _player(belief, "blue", (125, 100))
    intent = mode.decide(belief, ActionState())

    assert "self preservation" not in intent.reason


def test_commitment_expiry_produces_a_fallback_tick(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_SELF_PRESERVATION", "1")
    monkeypatch.setenv("CREWBORG_DEDUCTION_HISTORY", "1")
    monkeypatch.setattr(
        "crewborg.modes.self_preservation.infer",
        lambda history: _result({"red": 0.82, "blue": 0.09, "green": 0.09}),
    )
    mode = SelfPreservationMode()
    belief = _risky_belief()
    assert "self preservation" in mode.decide(belief, ActionState()).reason

    belief.last_tick = 82
    for record in belief.roster.values():
        record.last_seen_tick = 82
    intent = mode.decide(belief, ActionState())

    assert "self preservation" not in intent.reason


def test_commitment_ends_when_destination_sightings_expire(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_SELF_PRESERVATION", "1")
    monkeypatch.setenv("CREWBORG_DEDUCTION_HISTORY", "1")
    monkeypatch.setattr(
        "crewborg.modes.self_preservation.infer",
        lambda history: _result({"red": 0.82, "blue": 0.09, "green": 0.09}),
    )
    mode = SelfPreservationMode()
    belief = _risky_belief()
    assert "self preservation" in mode.decide(belief, ActionState()).reason

    belief.last_tick = 60
    belief.roster["red"].last_seen_tick = 60
    intent = mode.decide(belief, ActionState())

    assert "self preservation" not in intent.reason
