"""Victim-selection + witness logic tests (design §7.2, §10)."""

from __future__ import annotations

from crewborg.strategy.opportunity import (
    CLEAR_WINDOW_TICKS,
    DEFAULT_KILL_COOLDOWN_TICKS,
    TRACK_WINDOW_TICKS,
    URGENCY_FULL_TICKS,
    clear_window_ticks,
    has_trackable_victim,
    has_visible_victim,
    kill_urgency_ticks,
    select_victim,
    ticks_until_kill_ready,
    unwitnessed,
)
from crewborg.types import Belief, PlayerRecord


def test_ticks_until_kill_ready() -> None:
    # Ready now ⇒ 0.
    assert ticks_until_kill_ready(Belief(self_kill_ready=True)) == 0
    # No cooldown start observed yet ⇒ assume a full cooldown remains (don't pre-position).
    assert ticks_until_kill_ready(Belief(self_kill_ready=False)) == DEFAULT_KILL_COOLDOWN_TICKS
    # Mid-cooldown with a learned duration: start 100 + estimate 900 − now 700 = 300 left.
    b = Belief(self_kill_ready=False, last_tick=700, kill_cooldown_start_tick=100, kill_cooldown_estimate=900)
    assert ticks_until_kill_ready(b) == 300
    # Past the estimate (overdue) clamps to 0, never negative.
    b2 = Belief(self_kill_ready=False, last_tick=1200, kill_cooldown_start_tick=100, kill_cooldown_estimate=900)
    assert ticks_until_kill_ready(b2) == 0
    # No learned estimate falls back to the default duration.
    b3 = Belief(self_kill_ready=False, last_tick=100, kill_cooldown_start_tick=0)
    assert ticks_until_kill_ready(b3) == DEFAULT_KILL_COOLDOWN_TICKS - 100


def _crew(belief: Belief, object_id: int, xy: tuple[int, int], color: str, tick: int) -> None:
    belief.roster[color] = PlayerRecord(
        object_id=object_id,
        color=color,
        facing="left",
        world_x=xy[0],
        world_y=xy[1],
        last_seen_tick=tick,
        life_status="alive",
    )


# --- urgency ----------------------------------------------------------------


def test_kill_urgency_is_zero_until_kill_ready() -> None:
    assert kill_urgency_ticks(Belief(last_tick=100)) == 0
    assert kill_urgency_ticks(Belief(last_tick=100, self_kill_ready=True)) == 0  # since-tick unknown
    assert kill_urgency_ticks(Belief(last_tick=100, self_kill_ready=True, kill_ready_since_tick=70)) == 30


# --- has_trackable_victim (selector gate) -----------------------------------


def test_trackable_when_a_crewmate_was_seen_recently() -> None:
    belief = Belief(last_tick=200)
    _crew(belief, 1, (50, 50), "green", 200 - (TRACK_WINDOW_TICKS - 1))  # within the window
    assert has_trackable_victim(belief)


def test_not_trackable_when_only_stale_or_teammates() -> None:
    belief = Belief(last_tick=500, teammate_colors={"red"})
    _crew(belief, 1, (50, 50), "green", 500 - (TRACK_WINDOW_TICKS + 50))  # too stale
    _crew(belief, 2, (60, 50), "red", 500)  # a teammate, never a victim
    assert not has_trackable_victim(belief)


def test_visible_victim_requires_current_tick_visibility() -> None:
    belief = Belief(last_tick=200)
    _crew(belief, 1, (50, 50), "green", 199)
    assert not has_visible_victim(belief)
    belief.roster["green"].last_seen_tick = 200
    assert has_visible_victim(belief)


# --- select_victim ----------------------------------------------------------


def test_select_victim_needs_a_self_position() -> None:
    belief = Belief(last_tick=5)
    _crew(belief, 1, (50, 50), "green", 5)
    assert select_victim(belief) is None


def test_select_victim_takes_a_lone_visible_crewmate() -> None:
    belief = Belief(self_world_x=0, self_world_y=0, last_tick=5)
    _crew(belief, 1, (50, 50), "green", 5)
    v = select_victim(belief)
    assert v is not None and v.object_id == 1


def test_select_victim_requires_a_visible_crewmate() -> None:
    belief = Belief(self_world_x=0, self_world_y=0, last_tick=50)
    _crew(belief, 1, (50, 50), "green", 20)
    assert select_victim(belief) is None


def test_select_victim_ignores_too_stale_crewmates() -> None:
    belief = Belief(self_world_x=0, self_world_y=0, last_tick=500)
    _crew(belief, 1, (50, 50), "green", 20)
    assert select_victim(belief) is None


def test_select_victim_prefers_the_isolated_straggler() -> None:
    # Two clustered crewmates and one straggler far from everyone ⇒ pick the straggler
    # (easiest to finish off unwitnessed), even though it's farther from us.
    belief = Belief(self_world_x=0, self_world_y=0, last_tick=5)
    _crew(belief, 1, (40, 0), "green", 5)  # clustered pair...
    _crew(belief, 2, (50, 0), "blue", 5)  # ...10px apart
    _crew(belief, 3, (300, 0), "white", 5)  # the straggler, far from the others
    v = select_victim(belief)
    assert v is not None and v.object_id == 3


def test_select_victim_prefers_unclaimed_target_when_teammate_is_closer() -> None:
    belief = Belief(self_world_x=0, self_world_y=0, last_tick=5, teammate_colors={"pink"})
    _crew(belief, 1, (100, 0), "green", 5)
    _crew(belief, 2, (0, 100), "blue", 5)
    _crew(belief, 3, (96, 0), "pink", 5)  # teammate is already closer to green

    v = select_victim(belief)
    assert v is not None and v.color == "blue"


def test_select_victim_still_takes_claimed_target_if_it_is_the_only_option() -> None:
    belief = Belief(self_world_x=0, self_world_y=0, last_tick=5, teammate_colors={"pink"})
    _crew(belief, 1, (100, 0), "green", 5)
    _crew(belief, 2, (96, 0), "pink", 5)  # teammate is closer, but there is no other victim

    v = select_victim(belief)
    assert v is not None and v.color == "green"


# --- unwitnessed ------------------------------------------------------------


def test_unwitnessed_true_for_a_lone_target() -> None:
    belief = Belief(self_world_x=0, self_world_y=0, last_tick=5)
    _crew(belief, 1, (50, 50), "green", 5)
    assert unwitnessed(belief, belief.roster["green"])


def test_unwitnessed_false_with_a_recent_nearby_witness() -> None:
    belief = Belief(self_world_x=0, self_world_y=0, last_tick=5)
    _crew(belief, 1, (50, 50), "green", 5)
    _crew(belief, 2, (60, 50), "blue", 5)  # 10px away, seen now ⇒ witness
    assert not unwitnessed(belief, belief.roster["green"])


def test_unwitnessed_ignores_a_stale_witness() -> None:
    belief = Belief(self_world_x=0, self_world_y=0, last_tick=500)
    _crew(belief, 1, (50, 50), "green", 500)
    _crew(belief, 2, (60, 50), "blue", 100)  # last seen 400 ticks ago ⇒ ignored
    assert unwitnessed(belief, belief.roster["green"])


def test_full_urgency_strikes_through_a_witness() -> None:
    belief = Belief(
        self_world_x=0, self_world_y=0, last_tick=URGENCY_FULL_TICKS,
        self_kill_ready=True, kill_ready_since_tick=0,
    )
    _crew(belief, 1, (50, 50), "green", URGENCY_FULL_TICKS)
    _crew(belief, 2, (60, 50), "blue", URGENCY_FULL_TICKS)  # witness ignored at full urgency
    assert unwitnessed(belief, belief.roster["green"])


# --- the all-clear window (2026-07-29) --------------------------------------
#
# The defect it fixes, measured: 31.6% of our seen kills had nobody inside the 48px
# ring, and 97.6% of those seen kills had the observer rendered to us at the kill
# tick. A crewmate we can plainly see, standing past the ring, must veto the kill.


def test_visible_bystander_past_the_ring_vetoes_the_kill() -> None:
    # blue is 200px from the victim — far outside BASE_ISOLATION_RADIUS, so the
    # proximity half passes — but we are looking right at it. This is the case the
    # shipped gate got wrong.
    belief = Belief(self_world_x=0, self_world_y=0, last_tick=500)
    _crew(belief, 1, (50, 50), "green", 500)
    _crew(belief, 2, (250, 50), "blue", 500)
    assert not unwitnessed(belief, belief.roster["green"])


def test_the_victim_is_never_its_own_witness() -> None:
    # We must see the victim to kill it, so its own visibility cannot disqualify.
    belief = Belief(self_world_x=0, self_world_y=0, last_tick=500)
    _crew(belief, 1, (50, 50), "green", 500)
    assert unwitnessed(belief, belief.roster["green"])


def test_teammate_and_dead_players_are_not_witnesses() -> None:
    belief = Belief(self_world_x=0, self_world_y=0, last_tick=500, teammate_colors={"pink"})
    _crew(belief, 1, (50, 50), "green", 500)
    _crew(belief, 2, (250, 50), "pink", 500)   # fellow imposter, in view
    _crew(belief, 3, (260, 50), "white", 500)  # in view, but...
    belief.roster["white"].life_status = "dead"
    assert unwitnessed(belief, belief.roster["green"])


def test_bystander_seen_just_inside_the_window_still_vetoes() -> None:
    belief = Belief(self_world_x=0, self_world_y=0, last_tick=500)
    _crew(belief, 1, (50, 50), "green", 500)
    _crew(belief, 2, (250, 50), "blue", 500 - CLEAR_WINDOW_TICKS)  # exactly at the edge
    assert not unwitnessed(belief, belief.roster["green"])


def test_bystander_stale_past_the_window_does_not_veto() -> None:
    belief = Belief(self_world_x=0, self_world_y=0, last_tick=500)
    _crew(belief, 1, (50, 50), "green", 500)
    _crew(belief, 2, (250, 50), "blue", 500 - CLEAR_WINDOW_TICKS - 1)
    assert unwitnessed(belief, belief.roster["green"])


def test_ourselves_never_count_as_a_witness() -> None:
    # Our own record refreshes every tick; leaving it in would veto every kill.
    belief = Belief(self_world_x=0, self_world_y=0, last_tick=500, self_color="red")
    _crew(belief, 1, (50, 50), "green", 500)
    _crew(belief, 2, (0, 0), "red", 500)
    assert unwitnessed(belief, belief.roster["green"])


def test_proximity_mode_restores_the_shipped_gate(monkeypatch) -> None:
    # The A/B control arm: the visible bystander past the ring no longer vetoes.
    monkeypatch.setenv("CREWBORG_WITNESS_GATE", "proximity")
    belief = Belief(self_world_x=0, self_world_y=0, last_tick=500)
    _crew(belief, 1, (50, 50), "green", 500)
    _crew(belief, 2, (250, 50), "blue", 500)
    assert unwitnessed(belief, belief.roster["green"])


def test_clear_window_is_env_tunable(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_CLEAR_WINDOW", "10")
    assert clear_window_ticks() == 10
    belief = Belief(self_world_x=0, self_world_y=0, last_tick=500)
    _crew(belief, 1, (50, 50), "green", 500)
    _crew(belief, 2, (250, 50), "blue", 480)  # 20 ticks stale ⇒ outside a 10-tick window
    assert unwitnessed(belief, belief.roster["green"])


def test_full_urgency_still_strikes_through_a_visible_bystander() -> None:
    # The escape valve must survive the new half, or a shadowed imposter stalls forever.
    belief = Belief(
        self_world_x=0, self_world_y=0, last_tick=URGENCY_FULL_TICKS,
        self_kill_ready=True, kill_ready_since_tick=0,
    )
    _crew(belief, 1, (50, 50), "green", URGENCY_FULL_TICKS)
    _crew(belief, 2, (250, 50), "blue", URGENCY_FULL_TICKS)
    assert unwitnessed(belief, belief.roster["green"])
