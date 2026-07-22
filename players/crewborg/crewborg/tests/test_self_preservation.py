"""Role-agnostic self-preservation repulsion tests."""

from __future__ import annotations

import numpy as np

from crewborg.action import BTN_A, BTN_LEFT, resolve_action
from crewborg.modes.self_preservation import SelfPreservationMode, enabled
from crewborg.nav import NavGraph
from crewborg.types import ActionState, Belief, Intent, PlayerRecord


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


def _player(belief: Belief, color: str, xy: tuple[int, int], *, tick: int | None = None) -> None:
    belief.roster[color] = PlayerRecord(
        color=color,
        world_x=xy[0],
        world_y=xy[1],
        last_seen_tick=belief.last_tick if tick is None else tick,
        life_status="alive",
    )


def _enable(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_SELF_PRESERVATION", "1")
    monkeypatch.setenv("CREWBORG_DEDUCTION_HISTORY", "1")


def test_enabled_reads_separate_flag_and_requires_deduction_history(monkeypatch) -> None:
    monkeypatch.delenv("CREWBORG_SELF_PRESERVATION", raising=False)
    monkeypatch.setenv("CREWBORG_DEDUCTION_HISTORY", "1")
    assert enabled() is False

    monkeypatch.setenv("CREWBORG_SELF_PRESERVATION", "1")
    assert enabled() is True

    monkeypatch.delenv("CREWBORG_DEDUCTION_HISTORY", raising=False)
    assert enabled() is False


def test_one_nearby_player_immediately_preempts_tasking(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (120, 100))
    mode = SelfPreservationMode()
    mode._normal.decide = lambda *_args: Intent(  # type: ignore[method-assign]
        kind="complete_task", task_index=4, reason="task"
    )

    intent = mode.decide(belief, ActionState())

    assert intent.kind == "navigate_to"
    assert intent.point == (4, 100)
    assert intent.target_color == "red"
    assert intent.reason.startswith("self preservation (repulsion)")


def test_repulsion_cancels_an_in_progress_task(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (120, 100))
    task_intent = Intent(kind="complete_task", task_index=4, reason="task")
    action_state = ActionState(current_intent=task_intent, held_mask=BTN_A)

    intent = SelfPreservationMode().decide(belief, action_state)
    command = resolve_action(intent, belief, action_state)

    assert action_state.current_intent == intent
    assert command.held_mask == BTN_LEFT
    assert command.held_mask & BTN_A == 0


def test_repulsion_needs_no_witness_destination(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (120, 100))
    _player(belief, "blue", (500, 500), tick=-100)

    intent = SelfPreservationMode().decide(belief, ActionState())

    assert intent.kind == "navigate_to"
    assert intent.target_color == "red"


def test_goal_recomputes_as_both_players_move(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (120, 100))
    mode = SelfPreservationMode()
    first = mode.decide(belief, ActionState())

    belief.last_tick += 1
    belief.self_world_x = 90
    belief.roster["red"].world_x = 110
    belief.roster["red"].last_seen_tick = belief.last_tick
    second = mode.decide(belief, ActionState())

    assert first.point == (4, 100)
    assert second.point == (-6, 100)
    assert first.point != second.point


def test_zero_nearby_players_ends_repulsion(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (120, 100))
    mode = SelfPreservationMode()
    assert "self preservation" in mode.decide(belief, ActionState()).reason

    belief.last_tick += 1
    belief.roster["red"].last_seen_tick = belief.last_tick
    belief.roster["red"].world_x = 300
    intent = mode.decide(belief, ActionState())

    assert "self preservation" not in intent.reason


def test_second_nearby_player_ends_repulsion(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (120, 100))
    mode = SelfPreservationMode()
    mode.decide(belief, ActionState())

    belief.last_tick += 1
    belief.roster["red"].last_seen_tick = belief.last_tick
    _player(belief, "blue", (125, 100))
    intent = mode.decide(belief, ActionState())

    assert "self preservation" not in intent.reason


def test_only_currently_visible_players_count(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (120, 100), tick=9)

    intent = SelfPreservationMode().decide(belief, ActionState())

    assert "self preservation" not in intent.reason


def test_self_sprite_is_not_a_second_player(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "pink", (101, 100))
    _player(belief, "red", (120, 100))

    intent = SelfPreservationMode().decide(belief, ActionState())

    assert intent.target_color == "red"


def test_continuous_repulsion_becomes_pursuit_for_telemetry_only(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (120, 100))
    mode = SelfPreservationMode()
    first = mode.decide(belief, ActionState())

    belief.last_tick = 22
    belief.roster["red"].last_seen_tick = 22
    later = mode.decide(belief, ActionState())

    assert "(repulsion)" in first.reason
    assert "(pursuit)" in later.reason
    assert first.point == later.point


def test_new_companion_resets_pursuit_duration(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (120, 100))
    mode = SelfPreservationMode()
    mode.decide(belief, ActionState())
    belief.last_tick = 30
    belief.roster["red"].last_seen_tick = 29
    _player(belief, "blue", (120, 100))

    intent = mode.decide(belief, ActionState())

    assert intent.target_color == "blue"
    assert "(repulsion)" in intent.reason
    assert "continuous_ticks=0" in intent.reason


def test_nav_goal_uses_reachable_cells_away_from_companion(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    belief.self_world_x = 55
    belief.self_world_y = 55
    _player(belief, "red", (75, 55))
    start = (5, 5)
    away = (5, 4)
    toward = (5, 6)
    belief.nav = NavGraph(
        walkability=np.ones((100, 100), dtype=bool),
        cell_size=10,
        rows=10,
        cols=10,
        node_point={start: (55, 55), away: (45, 55), toward: (65, 55)},
        adjacency={start: [(away, 10.0), (toward, 10.0)], away: [(start, 10.0)], toward: [(start, 10.0)]},
        reachable={start, away, toward},
    )

    intent = SelfPreservationMode().decide(belief, ActionState())

    assert intent.point == (45, 55)


def test_overlapping_player_still_produces_nonzero_goal(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (100, 100))

    intent = SelfPreservationMode().decide(belief, ActionState())

    assert intent.point != (100, 100)
