"""Role-agnostic self-preservation repulsion tests."""

from __future__ import annotations

from crewborg.action import BTN_A, BTN_RIGHT, resolve_action
from crewborg.modes.self_preservation import SelfPreservationMode, enabled
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


def _trigger(mode: SelfPreservationMode, belief: Belief) -> Intent:
    mode.decide(belief, ActionState())
    belief.last_tick += 12
    for record in belief.roster.values():
        if record.last_seen_tick == belief.last_tick - 12:
            record.last_seen_tick = belief.last_tick
    return mode.decide(belief, ActionState())


def test_enabled_reads_separate_flag_and_requires_deduction_history(monkeypatch) -> None:
    monkeypatch.delenv("CREWBORG_SELF_PRESERVATION", raising=False)
    monkeypatch.setenv("CREWBORG_DEDUCTION_HISTORY", "1")
    assert enabled() is False

    monkeypatch.setenv("CREWBORG_SELF_PRESERVATION", "1")
    assert enabled() is True

    monkeypatch.delenv("CREWBORG_DEDUCTION_HISTORY", raising=False)
    assert enabled() is False


def test_one_nearby_player_waits_for_continuous_exposure(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (120, 100))
    _player(belief, "blue", (180, 100))
    mode = SelfPreservationMode()
    mode._normal.decide = lambda *_args: Intent(  # type: ignore[method-assign]
        kind="complete_task", task_index=4, reason="task"
    )

    first = mode.decide(belief, ActionState())
    intent = _trigger(mode, belief)

    assert first.kind == "complete_task"
    assert intent.kind == "navigate_to"
    assert intent.point == (180, 100)
    assert intent.target_color == "red"
    assert intent.reason.startswith("self preservation (pursuit)")


def test_witness_seeking_cancels_an_in_progress_task(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (120, 100))
    _player(belief, "blue", (180, 100))
    task_intent = Intent(kind="complete_task", task_index=4, reason="task")
    action_state = ActionState(current_intent=task_intent, held_mask=BTN_A)

    mode = SelfPreservationMode()
    mode.decide(belief, action_state)
    belief.last_tick += 12
    belief.roster["red"].last_seen_tick = belief.last_tick
    belief.roster["blue"].last_seen_tick = belief.last_tick
    intent = mode.decide(belief, action_state)
    command = resolve_action(intent, belief, action_state)

    assert action_state.current_intent == intent
    assert command.held_mask == BTN_RIGHT
    assert command.held_mask & BTN_A == 0


def test_exposure_without_a_current_witness_does_not_interrupt_work(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (120, 100))
    _player(belief, "blue", (500, 500), tick=-100)

    mode = SelfPreservationMode()
    mode._normal.decide = lambda *_args: Intent(  # type: ignore[method-assign]
        kind="complete_task", task_index=4, reason="task"
    )
    intent = _trigger(mode, belief)

    assert intent.kind == "complete_task"
    assert "self preservation" not in intent.reason


def test_trigger_moves_toward_nearest_visible_witness(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (120, 100))
    _player(belief, "blue", (180, 100))

    intent = _trigger(SelfPreservationMode(), belief)

    assert intent.point == (180, 100)
    assert intent.target_color == "red"
    assert "toward witness blue" in intent.reason


def test_goal_recomputes_as_both_players_move(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (120, 100))
    _player(belief, "blue", (180, 100))
    mode = SelfPreservationMode()
    first = _trigger(mode, belief)

    belief.last_tick += 1
    belief.self_world_x = 90
    belief.roster["red"].world_x = 110
    belief.roster["red"].last_seen_tick = belief.last_tick
    belief.roster["blue"].world_x = 170
    belief.roster["blue"].last_seen_tick = belief.last_tick
    second = mode.decide(belief, ActionState())

    assert first.point == (180, 100)
    assert second.point == (170, 100)
    assert first.point != second.point


def test_zero_nearby_players_ends_witness_seeking(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (120, 100))
    _player(belief, "blue", (180, 100))
    mode = SelfPreservationMode()
    assert "self preservation" in _trigger(mode, belief).reason

    belief.last_tick += 1
    belief.roster["red"].last_seen_tick = belief.last_tick
    belief.roster["red"].world_x = 300
    intent = mode.decide(belief, ActionState())

    assert "self preservation" not in intent.reason


def test_second_nearby_player_ends_witness_seeking(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (120, 100))
    _player(belief, "green", (180, 100))
    mode = SelfPreservationMode()
    _trigger(mode, belief)

    belief.last_tick += 1
    belief.roster["red"].last_seen_tick = belief.last_tick
    _player(belief, "blue", (125, 100))
    intent = mode.decide(belief, ActionState())

    assert "self preservation" not in intent.reason


def test_only_currently_visible_players_count(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (120, 100), tick=9)

    intent = _trigger(SelfPreservationMode(), belief)

    assert "self preservation" not in intent.reason


def test_self_sprite_is_not_a_second_player(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "pink", (101, 100))
    _player(belief, "red", (120, 100))
    _player(belief, "green", (180, 100))

    intent = _trigger(SelfPreservationMode(), belief)

    assert intent.target_color == "red"


def test_geometric_self_record_is_excluded_when_self_color_is_wrong(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    belief.self_color = "blue"
    _player(belief, "pink", (98, 94))  # hosted self-record offset
    _player(belief, "red", (120, 100))
    _player(belief, "green", (180, 100))

    intent = _trigger(SelfPreservationMode(), belief)

    assert intent.target_color == "red"
    assert intent.reason.startswith("self preservation (pursuit)")


def test_overlapping_self_color_and_geometric_candidate_are_both_excluded(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    belief.self_color = "yellow"
    _player(belief, "blue", (98, 94))
    _player(belief, "pink", (98, 94))
    _player(belief, "red", (120, 100))
    _player(belief, "green", (180, 100))

    intent = _trigger(SelfPreservationMode(), belief)

    assert intent.target_color == "red"


def test_continuous_exposure_triggers_at_twelve_ticks(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (120, 100))
    _player(belief, "blue", (180, 100))
    mode = SelfPreservationMode()
    first = mode.decide(belief, ActionState())

    belief.last_tick = 22
    belief.roster["red"].last_seen_tick = 22
    belief.roster["blue"].last_seen_tick = 22
    later = mode.decide(belief, ActionState())

    assert "self preservation" not in first.reason
    assert "(pursuit)" in later.reason


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

    assert "self preservation" not in intent.reason
