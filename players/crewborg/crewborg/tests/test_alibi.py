"""Co-presence alibi tests (strategy/alibi.py + solver pair-exclusion).

With two impostors an alibi never *clears* a player: co-presence at one kill only proves
they were not that killer (they could be the second, non-killing impostor). The sound
consequence is a per-kill co-present SET that excludes a hypothesis only when *all* its
impostors were alibied for the same kill.
"""

from __future__ import annotations

from crewborg.strategy.alibi import alibi_sets, update_alibi
from crewborg.strategy.meeting.solver import solve_hypotheses
from crewborg.types import Belief, PlayerEvent, PlayerRecord


def _belief(self_color: str = "pink") -> Belief:
    b = Belief(phase="Playing", self_role="crewmate", camera_ready=True)
    b.self_color = self_color
    return b


def _see(belief: Belief, tick: int, alive: list[str]) -> None:
    belief.last_tick = tick
    for color in alive:
        rec = belief.roster.setdefault(color, PlayerRecord(color=color))
        rec.last_seen_tick = tick
        if rec.life_status != "dead":
            rec.life_status = "alive"
    update_alibi(belief)


def _die(belief: Belief, color: str, source: str, death_learned_tick: int) -> None:
    rec = belief.roster.setdefault(color, PlayerRecord(color=color))
    rec.life_status = "dead"
    rec.death_source = source  # "body"/"census" = killed; "ejection" = voted out
    rec.death_seen_tick = death_learned_tick


def test_disabled_by_default_returns_no_sets(monkeypatch) -> None:
    monkeypatch.delenv("CREWBORG_ALIBI", raising=False)
    b = _belief()
    for t in range(1, 8):
        _see(b, t, ["red", "blue", "green"])
    _die(b, "green", "body", 8)
    _see(b, 8, ["red", "blue"])
    assert b.alibi_state == {}
    assert alibi_sets(b) == []


def test_kill_records_the_co_present_set(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_ALIBI", "1")
    b = _belief()
    # blue+cyan are with us throughout; green (victim) last seen alive at t=4; red joins at t=5.
    for t in range(1, 5):
        _see(b, t, ["blue", "cyan", "green"])
    for t in range(5, 8):
        _see(b, t, ["blue", "cyan", "red"])
    _die(b, "green", "body", 8)
    _see(b, 8, ["blue", "cyan", "red"])
    sets = alibi_sets(b)
    assert sets == [frozenset({"blue", "cyan"})]  # red joined after t=4, green is the victim


def test_visible_victim_yields_no_co_presence_alibi(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_ALIBI", "1")
    b = _belief()
    for t in range(1, 6):
        _see(b, t, ["blue", "cyan", "green"])
    _die(b, "green", "body", 6)
    _see(b, 6, ["blue", "cyan"])

    assert alibi_sets(b) == []


def test_witnessed_kill_yields_no_co_presence_alibi(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_ALIBI", "1")
    b = _belief()
    for t in range(1, 3):
        _see(b, t, ["blue", "cyan", "green"])
    b.roster["blue"].events.append(
        PlayerEvent(kind="kill", start_tick=3, end_tick=3, target_color="green")
    )
    for t in range(3, 7):
        _see(b, t, ["blue", "cyan"])
    _die(b, "green", "body", 7)
    _see(b, 7, ["blue", "cyan"])

    assert alibi_sets(b) == []


def test_ejection_is_not_a_kill_and_yields_no_alibi(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_ALIBI", "1")
    b = _belief()
    for t in range(1, 6):
        _see(b, t, ["blue", "cyan", "green"])
    _die(b, "green", "ejection", 6)  # voted out, not killed — no hidden perpetrator
    _see(b, 6, ["blue", "cyan"])
    assert alibi_sets(b) == []


def test_census_kill_closes_visibility_at_last_playing_tick(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_ALIBI", "1")
    b = _belief()
    for t in range(1, 2):
        _see(b, t, ["blue", "cyan", "green"])
    for t in range(2, 6):
        _see(b, t, ["blue", "cyan"])
    _die(b, "green", "census", 20)
    b.phase = "Voting"
    b.last_tick = 20
    update_alibi(b)

    assert alibi_sets(b) == [frozenset({"blue", "cyan"})]


def test_a_gap_in_sight_drops_that_player_from_the_set(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_ALIBI", "1")
    b = _belief()
    _see(b, 1, ["blue", "cyan", "green"])
    for t in range(2, 6):  # cyan vanishes for a long gap across the window
        _see(b, t, ["blue"])
    _die(b, "green", "body", 6)
    _see(b, 6, ["blue", "cyan"])  # cyan only reappears now
    assert alibi_sets(b) == [frozenset({"blue"})]  # cyan's sight run restarted after the window


def test_pair_is_excluded_but_a_single_alibi_clears_no_one() -> None:
    players = ["red", "blue", "green", "yellow"]
    base = solve_hypotheses(players, 2, [])
    with_alibi = solve_hypotheses(players, 2, [], alibi_groups=[{"red", "blue"}])
    # The {red, blue} pair is impossible (both alibied for one kill) → red's marginal drops...
    assert with_alibi["marginals"]["red"] < base["marginals"]["red"]
    # ...but red is NOT cleared: it can still be the impostor paired with green/yellow.
    assert with_alibi["marginals"]["red"] > 0.0
    assert frozenset({"red", "blue"}) not in {frozenset(h["imposters"]) for h in with_alibi["hypotheses"]}


def test_pinned_impostor_still_forces_partner_outside_the_alibi_group() -> None:
    out = solve_hypotheses(
        ["red", "blue", "green", "yellow"],
        2,
        [],
        pins={"red"},
        alibi_groups=[{"red", "blue", "green"}],
    )

    assert {
        tuple(hypothesis["imposters"]) for hypothesis in out["hypotheses"]
    } == {("red", "yellow")}


def test_alibi_never_empties_the_hypothesis_space() -> None:
    players = ["red", "blue"]
    # An alibi group covering the only possible pair must be distrusted, not abstained on.
    out = solve_hypotheses(players, 2, [], alibi_groups=[{"red", "blue"}])
    assert out["marginals"]  # still returns a usable posterior
