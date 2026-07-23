"""Safe-distance separation from a lone follower (crew self-preservation)."""

from __future__ import annotations

from crewborg.map.types import MapData, MapPoint, MapRect, TaskStation
from crewborg.modes.self_preservation import SelfPreservationMode, enabled
from crewborg.types import ActionState, Belief, Intent, PlayerRecord


def _map() -> MapData:
    # Two tasks either side of the subject at (100, 100): one toward the usual
    # follower position (~x=150) and one away from it.
    return MapData(
        width=1000,
        height=1000,
        tasks=(
            TaskStation(name="toward", x=190, y=90, w=20, h=20),  # center (200, 100)
            TaskStation(name="away", x=10, y=90, w=20, h=20),  # center (20, 100)
        ),
        vents=(),
        rooms=(),
        button=MapRect(x=0, y=0, w=8, h=8),
        home=MapPoint(x=0, y=0),
    )


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
        map=_map(),
        assigned_task_indices={0, 1},
        visible_task_indices={0, 1},
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
    """Run one tick, advance past the reaction window, refresh sightings, run again."""

    mode.decide(belief, ActionState())
    belief.last_tick += 12
    for record in belief.roster.values():
        if record.life_status == "alive":
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


def test_lone_follower_waits_for_continuous_exposure(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (150, 100))  # 50px away, within SAFE_RADIUS

    first = SelfPreservationMode().decide(belief, ActionState())

    assert "self preservation" not in first.reason


def test_retreat_picks_task_that_increases_separation(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (150, 100))

    intent = _trigger(SelfPreservationMode(), belief)

    assert intent.kind == "complete_task"
    assert intent.task_index == 1  # the "away" task
    assert intent.target_color == "red"
    assert intent.reason.startswith("self preservation (safe distance)")


def test_reacts_beyond_the_64px_danger_radius(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    # 80px away: outside the old 64px danger radius, inside the 96px safe radius.
    _player(belief, "red", (100, 180))

    intent = _trigger(SelfPreservationMode(), belief)

    assert intent.kind == "complete_task"
    assert intent.task_index == 1
    assert intent.reason.startswith("self preservation (safe distance)")


def test_no_separating_task_keeps_normal_tasking(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    belief.visible_task_indices = {0}  # only the task toward the follower remains
    _player(belief, "red", (150, 100))

    intent = _trigger(SelfPreservationMode(), belief)

    assert "self preservation" not in intent.reason


def test_second_nearby_player_suppresses_retreat(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (150, 100))  # 50px
    _player(belief, "green", (100, 160))  # 60px — a second nearby => a group

    intent = _trigger(SelfPreservationMode(), belief)

    assert "self preservation" not in intent.reason


def test_follower_leaving_ends_retreat(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (150, 100))
    mode = SelfPreservationMode()
    assert "self preservation" in _trigger(mode, belief).reason

    belief.last_tick += 1
    belief.roster["red"].world_x = 500  # walked far away
    belief.roster["red"].last_seen_tick = belief.last_tick
    intent = mode.decide(belief, ActionState())

    assert "self preservation" not in intent.reason


def test_only_currently_visible_players_count(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (150, 100), tick=9)  # last seen a tick ago, not now

    intent = _trigger(SelfPreservationMode(), belief)

    assert "self preservation" not in intent.reason


def test_self_sprite_is_not_a_follower(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "pink", (98, 94))  # our own self record at the sprite offset
    _player(belief, "red", (150, 100))

    intent = _trigger(SelfPreservationMode(), belief)

    assert intent.target_color == "red"


def test_geometric_self_record_excluded_when_self_color_is_wrong(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    belief.self_color = "blue"  # a stale/incorrect cached self color
    _player(belief, "pink", (98, 94))  # sits on the self sprite anchor
    _player(belief, "red", (150, 100))

    intent = _trigger(SelfPreservationMode(), belief)

    assert intent.target_color == "red"
    assert intent.reason.startswith("self preservation (safe distance)")


def test_overlapping_self_color_and_geometric_candidate_both_excluded(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    belief.self_color = "yellow"
    _player(belief, "blue", (98, 94))  # geometric self anchor
    _player(belief, "pink", (98, 94))  # same spot, different color
    _player(belief, "red", (150, 100))

    intent = _trigger(SelfPreservationMode(), belief)

    assert intent.target_color == "red"


def test_new_follower_resets_the_reaction_timer(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    _player(belief, "red", (150, 100))
    mode = SelfPreservationMode()
    mode.decide(belief, ActionState())

    belief.last_tick = 30
    belief.roster["red"].last_seen_tick = 29  # red gone this tick
    _player(belief, "blue", (150, 100))  # a different lone follower, just arrived

    intent = mode.decide(belief, ActionState())

    assert "self preservation" not in intent.reason


def test_retreat_target_latches_while_it_still_opens_the_gap(monkeypatch) -> None:
    _enable(monkeypatch)
    belief = _belief()
    belief.map = MapData(
        width=1000,
        height=1000,
        tasks=(
            TaskStation(name="A", x=50, y=90, w=20, h=20),  # center (60, 100)
            TaskStation(name="B", x=90, y=30, w=20, h=20),  # center (100, 40)
        ),
        vents=(),
        rooms=(),
        button=MapRect(x=0, y=0, w=8, h=8),
        home=MapPoint(x=0, y=0),
    )
    belief.visible_task_indices = {0, 1}
    _player(belief, "red", (150, 100))
    mode = SelfPreservationMode()

    first = _trigger(mode, belief)
    assert first.task_index == 0  # A is the nearest separating task

    # We advance toward A, so B is now far nearer to us -- but A still opens the
    # gap, so the latch must keep A rather than flip to B.
    belief.last_tick += 1
    belief.self_world_y = 50
    belief.roster["red"].last_seen_tick = belief.last_tick
    second = mode.decide(belief, ActionState())

    assert second.task_index == 0


def test_disabled_flag_delegates_to_normal(monkeypatch) -> None:
    monkeypatch.delenv("CREWBORG_SELF_PRESERVATION", raising=False)
    monkeypatch.setenv("CREWBORG_DEDUCTION_HISTORY", "1")
    belief = _belief()
    _player(belief, "red", (150, 100))

    intent = _trigger(SelfPreservationMode(), belief)

    assert "self preservation" not in intent.reason
