"""Co-presence alibi tests (strategy/alibi.py). Default-OFF; sound-over-complete."""

from __future__ import annotations

from crewborg.strategy.alibi import alibi_clears, update_alibi
from crewborg.types import Belief, PlayerRecord


def _belief(self_color: str = "pink") -> Belief:
    b = Belief()
    b.self_color = self_color
    return b


def _rec(color: str) -> PlayerRecord:
    return PlayerRecord(color=color)


def _see(belief: Belief, tick: int, alive: list[str]) -> None:
    """Advance to ``tick`` with exactly ``alive`` visible-and-alive this frame, then fold."""
    belief.last_tick = tick
    for color in alive:
        rec = belief.roster.setdefault(color, _rec(color))
        rec.last_seen_tick = tick
        if rec.life_status != "dead":
            rec.life_status = "alive"
    update_alibi(belief)


def _kill(belief: Belief, color: str, death_learned_tick: int) -> None:
    """Mark ``color`` dead, preserving its last alive-sighting tick (as perception does)."""
    rec = belief.roster.setdefault(color, _rec(color))
    rec.life_status = "dead"
    rec.death_seen_tick = death_learned_tick


def test_disabled_by_default_is_a_noop(monkeypatch) -> None:
    monkeypatch.delenv("CREWBORG_ALIBI", raising=False)
    b = _belief()
    for t in range(1, 10):
        _see(b, t, ["red", "blue", "green"])
    _kill(b, "green", 9)
    _see(b, 9, ["red", "blue"])
    assert b.alibi_state == {}
    assert alibi_clears(b) == set()


def test_continuous_co_presence_clears_the_witness(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_ALIBI", "1")
    b = _belief()
    # blue is in view the whole time; green (victim) last seen alive at t=5; red only joins at t=6.
    for t in range(1, 6):
        _see(b, t, ["blue", "green"])
    for t in range(6, 8):
        _see(b, t, ["blue", "red"])  # green now off-view (being killed), red appears
    _kill(b, "green", 8)
    _see(b, 8, ["blue", "red"])  # we find the body while blue (and red) are with us
    cleared = alibi_clears(b)
    assert "blue" in cleared          # continuously with us since before green's last sighting
    assert "red" not in cleared       # only joined at t=6, after green (t=5) — no alibi
    assert "green" not in cleared     # the victim itself is never "cleared"


def test_a_gap_in_line_of_sight_breaks_the_alibi(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_ALIBI", "1")
    b = _belief()
    _see(b, 1, ["blue", "green"])
    # blue disappears for a long gap (> grace) across the death window, then returns.
    for t in range(2, 8):
        _see(b, t, ["green"] if t <= 5 else [])
    _kill(b, "green", 8)
    _see(b, 8, ["blue"])  # blue reappears only now
    assert "blue" not in alibi_clears(b)  # its visible-run restarted at t=8, after the window


def test_clears_persist_after_being_granted(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_ALIBI", "1")
    b = _belief()
    for t in range(1, 6):
        _see(b, t, ["blue", "green"])
    _kill(b, "green", 6)
    _see(b, 6, ["blue"])
    assert "blue" in alibi_clears(b)
    # A later frame where blue is out of view does not revoke the earned alibi.
    _see(b, 40, [])
    assert "blue" in alibi_clears(b)
