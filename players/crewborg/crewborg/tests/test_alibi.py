"""Co-presence alibi tests (strategy/alibi.py + joint pair scoring).

With two impostors an alibi never *clears* a player: co-presence at one kill only proves
they were not that killer (they could be the second, non-killing impostor). The sound
event is retained and audited against every pair. Production excludes a pair only when
none of its alive members could have made that kill; tests of the optional soft scorer
use a non-default weight explicitly.
"""

from __future__ import annotations

import pytest

from crewborg.strategy.alibi import alibi_events, alibi_sets, update_alibi
from crewborg.strategy.meeting.solver import SolverConfig, solve_hypotheses
from crewborg.types import Belief, KillAlibi, PlayerEvent, PlayerRecord


def _belief(self_color: str = "pink") -> Belief:
    b = Belief(phase="Playing", self_role="crewmate", camera_ready=True)
    b.self_color = self_color
    b.self_world_x = 100
    b.self_world_y = 100
    return b


def _see(
    belief: Belief,
    tick: int,
    alive: list[str],
    *,
    positions: dict[str, tuple[int, int]] | None = None,
) -> None:
    belief.last_tick = tick
    for index, color in enumerate(alive):
        rec = belief.roster.setdefault(color, PlayerRecord(color=color))
        rec.world_x, rec.world_y = (positions or {}).get(color, (101 + index, 101))
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
    assert alibi_events(b) == [
        KillAlibi(
            observer_color="pink",
            victim_color="green",
            death_source="body",
            death_seen_tick=8,
            window_start_tick=4,
            window_end_tick=8,
            alibied_colors=("blue", "cyan"),
            possible_killers=("blue", "cyan", "red"),
        )
    ]


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


def test_same_census_victim_remains_a_possible_earlier_killer(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_ALIBI", "1")
    b = _belief()
    _see(b, 1, ["blue", "cyan", "green", "red"])
    for t in range(2, 6):
        _see(b, t, ["blue", "cyan"])
    _die(b, "green", "census", 20)
    _die(b, "red", "census", 20)
    b.phase = "Voting"
    b.last_tick = 20
    update_alibi(b)

    events = alibi_events(b)
    assert len(events) == 2
    green_event = next(event for event in events if event.victim_color == "green")
    red_event = next(event for event in events if event.victim_color == "red")
    assert "red" in green_event.possible_killers
    assert "green" in red_event.possible_killers


def test_a_gap_in_sight_drops_that_player_from_the_set(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_ALIBI", "1")
    b = _belief()
    _see(b, 1, ["blue", "cyan", "green"])
    for t in range(2, 6):  # cyan vanishes for a long gap across the window
        _see(b, t, ["blue"])
    _die(b, "green", "body", 6)
    _see(b, 6, ["blue", "cyan"])  # cyan only reappears now
    assert alibi_sets(b) == [frozenset({"blue"})]  # cyan's sight run restarted after the window


def test_visible_but_not_physically_close_player_gets_no_alibi(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_ALIBI", "1")
    b = _belief()
    for t in range(1, 5):
        _see(b, t, ["blue", "green"], positions={"blue": (170, 100)})
    for t in range(5, 9):
        _see(b, t, ["blue"], positions={"blue": (170, 100)})
    _die(b, "green", "body", 9)
    _see(b, 9, ["blue"], positions={"blue": (170, 100)})

    assert alibi_events(b) == []


def test_nonpositive_distance_preserves_legacy_visibility_control(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_ALIBI", "1")
    monkeypatch.setenv("CREWBORG_ALIBI_MAX_DIST", "0")
    b = _belief()
    for t in range(1, 5):
        _see(b, t, ["blue", "green"], positions={"blue": (170, 100)})
    for t in range(5, 9):
        _see(b, t, ["blue"], positions={"blue": (170, 100)})
    _die(b, "green", "body", 9)
    _see(b, 9, ["blue"], positions={"blue": (170, 100)})

    assert alibi_sets(b) == [frozenset({"blue"})]


def test_pair_is_excluded_but_a_single_alibi_clears_no_one() -> None:
    players = ["red", "blue", "green", "yellow"]
    base = solve_hypotheses(players, 2, [])
    with_alibi = solve_hypotheses(players, 2, [], alibi_groups=[{"red", "blue"}])
    # The {red, blue} pair is impossible (both alibied for one kill) → red's marginal drops...
    assert with_alibi["marginals"]["red"] < base["marginals"]["red"]
    # ...but red is NOT cleared: it can still be the impostor paired with green/yellow.
    assert with_alibi["marginals"]["red"] > 0.0
    assert frozenset({"red", "blue"}) not in {frozenset(h["imposters"]) for h in with_alibi["hypotheses"]}


def _alibi(
    victim: str,
    tick: int,
    alibied: tuple[str, ...],
    possible_killers: tuple[str, ...] = ("red", "blue", "green", "yellow"),
) -> KillAlibi:
    return KillAlibi(
        observer_color="pink",
        victim_color=victim,
        death_source="census",
        death_seen_tick=tick,
        window_start_tick=tick - 10,
        window_end_tick=tick - 1,
        alibied_colors=alibied,
        possible_killers=possible_killers,
    )


def test_singleton_alibi_softly_weakens_every_pair_containing_that_player() -> None:
    players = ["red", "blue", "green", "yellow"]
    base = solve_hypotheses(players, 2, [])
    out = solve_hypotheses(
        players,
        2,
        [],
        alibis=[_alibi("cyan", 20, ("red",))],
        config=SolverConfig(alibi_weight=0.5),
    )

    assert out["marginals"]["red"] < base["marginals"]["red"]
    assert out["marginals"]["red"] > 0.0
    assert out["marginals"]["blue"] > base["marginals"]["blue"]


def test_distinct_kill_alibis_accumulate_without_compressing_events() -> None:
    players = ["red", "blue", "green", "yellow"]
    one = solve_hypotheses(
        players,
        2,
        [],
        alibis=[_alibi("cyan", 20, ("red",))],
        config=SolverConfig(alibi_weight=0.5),
    )
    two = solve_hypotheses(
        players,
        2,
        [],
        alibis=[
            _alibi("cyan", 20, ("red",)),
            _alibi("orange", 40, ("red",)),
        ],
        config=SolverConfig(alibi_weight=0.5),
    )

    assert two["marginals"]["red"] < one["marginals"]["red"]
    assert two["n_alibis"] == 2
    red_blue = next(
        audit
        for audit in two["pair_audit"]
        if audit["imposters"] == ["blue", "red"]
    )
    assert [
        item["evidence_id"]
        for item in red_blue["contributions"]
        if item["channel"] == "alibi"
    ] == [
        "alibi:pink:cyan:20:10:19",
        "alibi:pink:orange:40:30:39",
    ]


def test_single_alibi_does_not_exclude_pair_when_partner_could_kill() -> None:
    out = solve_hypotheses(
        ["red", "blue", "green", "yellow"],
        2,
        [],
        alibis=[_alibi("cyan", 20, ("red",))],
    )

    assert ("blue", "red") in {
        tuple(hypothesis["imposters"]) for hypothesis in out["hypotheses"]
    }


def test_alibi_combines_with_partner_ineligibility_to_exclude_pair() -> None:
    out = solve_hypotheses(
        ["red", "blue", "green", "yellow"],
        2,
        [],
        alibis=[
            _alibi(
                "cyan",
                20,
                ("red",),
                possible_killers=("red", "green", "yellow"),
            )
        ],
    )

    assert ("blue", "red") not in {
        tuple(hypothesis["imposters"]) for hypothesis in out["hypotheses"]
    }
    audit = next(
        item for item in out["pair_audit"] if item["imposters"] == ["blue", "red"]
    )
    assert audit["exclusion_reasons"] == ["alibi:pink:cyan:20:10:19"]


def test_pair_audit_sums_to_log_weight_and_recomputes_from_raw_events() -> None:
    event = _alibi("cyan", 20, ("red",))
    first = solve_hypotheses(
        ["red", "blue", "green", "yellow"],
        2,
        [],
        alibis=[event],
        config=SolverConfig(alibi_weight=0.5),
    )
    constrained = solve_hypotheses(
        ["red", "blue", "green", "yellow"],
        2,
        [],
        alibis=[event],
        hard_clears={"green"},
        config=SolverConfig(alibi_weight=0.5),
    )
    replayed = solve_hypotheses(
        ["red", "blue", "green", "yellow"],
        2,
        [],
        alibis=[event],
        config=SolverConfig(alibi_weight=0.5),
    )

    for audit in first["pair_audit"]:
        if audit["eligible"]:
            assert sum(
                item["delta"] for item in audit["contributions"]
            ) == pytest.approx(audit["log_weight"])
    assert constrained["marginals"] != first["marginals"]
    assert replayed["marginals"] == first["marginals"]


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
