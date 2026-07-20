"""Stay-with-group mode tests (modes/stick.py). Default-OFF; never interrupts tasking."""

from __future__ import annotations

from crewborg.modes.stick import StickMode, enabled
from crewborg.types import ActionState, Belief, Intent, PlayerRecord


def _belief(self_xy=(100, 100), self_color="pink") -> Belief:
    b = Belief()
    b.self_color = self_color
    b.self_world_x, b.self_world_y = self_xy
    b.last_tick = 10
    return b


def _crew(belief: Belief, color: str, xy, tick: int = 10, alive: bool = True) -> None:
    r = PlayerRecord(color=color)
    r.world_x, r.world_y = xy
    r.last_seen_tick = tick
    r.life_status = "alive" if alive else "dead"
    belief.roster[color] = r


class _StubNormal:
    def __init__(self, intent: Intent) -> None:
        self._intent = intent

    def decide(self, belief, action_state):
        return self._intent


def test_enabled_reads_env(monkeypatch) -> None:
    monkeypatch.delenv("CREWBORG_STICK", raising=False)
    assert enabled() is False
    monkeypatch.setenv("CREWBORG_STICK", "1")
    assert enabled() is True


def test_passes_through_active_tasking(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_STICK", "1")
    m = StickMode()
    m._normal = _StubNormal(Intent(kind="complete_task", task_index=2, reason="completing assigned task"))
    b = _belief()
    _crew(b, "red", (500, 500))
    out = m.decide(b, ActionState())
    assert out.kind == "complete_task" and out.task_index == 2  # never interrupted for sticking


def test_substitutes_stick_when_normal_is_idle() -> None:
    m = StickMode()
    m._normal = _StubNormal(Intent(kind="idle", reason="no incomplete tasks remain"))
    b = _belief(self_xy=(100, 100))
    _crew(b, "red", (500, 500))
    _crew(b, "blue", (520, 510))  # clusters with red
    _crew(b, "green", (2000, 2000))  # loner
    out = m.decide(b, ActionState())
    assert out.kind == "navigate_to"
    assert out.point in ((500, 500), (520, 510))  # heads for the crowd, not the loner


def test_holds_when_already_with_the_group() -> None:
    m = StickMode()
    m._normal = _StubNormal(Intent(kind="idle", reason="no incomplete tasks remain"))
    b = _belief(self_xy=(505, 505))  # right next to the cluster
    _crew(b, "red", (500, 500))
    _crew(b, "blue", (520, 510))
    out = m.decide(b, ActionState())
    assert out.kind == "idle" and "stick" in (out.reason or "")


def test_falls_back_to_normal_when_no_live_crew() -> None:
    fallback = Intent(kind="navigate_to", point=(0, 0), reason="tasks done: returning to the start room")
    m = StickMode()
    m._normal = _StubNormal(fallback)
    b = _belief()
    _crew(b, "red", (500, 500), alive=False)  # only a corpse
    out = m.decide(b, ActionState())
    assert out is fallback  # nothing to stick to → keep Normal's decision


def test_falls_back_when_only_one_player_is_nearby() -> None:
    fallback = Intent(
        kind="navigate_to",
        point=(0, 0),
        reason="tasks done: returning to the start room",
    )
    m = StickMode()
    m._normal = _StubNormal(fallback)
    b = _belief()
    _crew(b, "red", (110, 110))

    assert m.decide(b, ActionState()) is fallback


def test_does_not_hold_when_cluster_positions_are_stale() -> None:
    fallback = Intent(
        kind="navigate_to",
        point=(0, 0),
        reason="tasks done: returning to the start room",
    )
    m = StickMode()
    m._normal = _StubNormal(fallback)
    b = _belief(self_xy=(505, 505))
    b.last_tick = 200
    _crew(b, "red", (500, 500), tick=10)
    _crew(b, "blue", (520, 510), tick=10)

    assert m.decide(b, ActionState()) is fallback
