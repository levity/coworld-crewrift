"""Shared imposter victim-selection and witness logic (design §7.2, §10).

Hunt commits to a *victim* and stalks it, striking only when the kill would go
**unwitnessed**. This module is the single source of truth for: which crewmate to
commit to (``select_victim`` — the most-isolated visible straggler, easiest to
finish off unseen), whether a kill on a given target is currently unwitnessed
(``unwitnessed``), and whether any victim is visible or trackable right now.

The witness bar is not fixed: the longer the imposter has been *able* to kill
without doing so, the more it relaxes (``kill_urgency_ticks``), so a cautious
imposter that never finds a clean opening still escalates rather than stalling
forever (design §10 "act with urgency").

The bar has two halves (2026-07-29): the original proximity ring around the victim,
and an all-clear window requiring that nobody but the victim and our teammates has
been *visible to us* for a continuous run of ticks. The second exists because the
first was measurably wrong — see the note on ``CLEAR_WINDOW_TICKS``. Set
``CREWBORG_WITNESS_GATE=proximity`` to restore the ring-only behaviour for an A/B
control arm.
"""

from __future__ import annotations

import os

from crewborg.nav import plan_route
from crewborg.types import Belief, PlayerRecord

# Clearance (world px) required around a target at zero urgency: no other crewmate
# may be within this distance for the kill to count as unwitnessed.
BASE_ISOLATION_RADIUS = 48

# At zero urgency, another crewmate seen within this many ticks still counts as a
# potential witness; the window shrinks with urgency so stale sightings stop vetoing.
WITNESS_WINDOW_TICKS = 72

# Ticks of being able-to-kill-without-killing at which the witness bar reaches zero —
# i.e. the imposter will strike any victim regardless of witnesses (~10s at 24 Hz).
URGENCY_FULL_TICKS = 240

# --- The all-clear window (2026-07-29) ---------------------------------------------
#
# WHY THIS EXISTS. The proximity test below asks "is another crewmate within 48px of
# the victim", which is a PROXY for "could anyone see this kill" — and it is wrong
# about a third of the time. Measured over 89 matched league episodes
# (`crewrift-analysis/kill_visibility.py`, ground truth = `player_visible_interval`
# with visibility_basis="rendered_view", i.e. what the sim actually drew):
#
#   * 31.6% of our SEEN kills had nobody inside the 48px ring — we certified them
#     unwitnessed and were wrong;
#   * rendered visibility is 98.4% SYMMETRIC (n=38,831), so "who can see me" is
#     "who can I see" — a fact the percept hands us every tick;
#   * 97.6% of our seen kills (40/41) had the observer RENDERED TO US at the kill
#     tick. We were looking straight at the witness and struck anyway.
#
# So the information was always there and the gate threw it away. This window is the
# fix: a kill counts as unwitnessed only when nobody except the victim and our own
# teammates has been visible to us for a CONTINUOUS run of ticks. Continuity is free —
# ``last_seen_tick`` is the most recent tick we rendered that player, so requiring
# every live non-teammate to be staler than the window IS "clear for the whole window".
#
# SIZING. 72 ticks (~3s at 24 Hz), matching WITNESS_WINDOW_TICKS. Calibrated against
# the solitude measurement (median 80t since a third party shared our room at kill
# time, 42% of kills 120t-clear), so roughly half of today's kill opportunities still
# pass at zero urgency rather than the gate stalling us out. Env-tunable so an A/B can
# sweep it without a rebuild.
CLEAR_WINDOW_TICKS = 72

# `visibility` (default) = the fix above. `proximity` = the shipped 48px-only gate,
# kept so an A/B has a clean control arm.
WITNESS_GATE_MODES = ("visibility", "proximity")

# A non-teammate seen within this many ticks is still "trackable" — Search can
# follow it to its last-known position even while it is briefly out of view.
TRACK_WINDOW_TICKS = 120

# If a fellow imposter was seen closer than us to a victim within this radius, treat
# that victim as "claimed" and prefer another target when one exists.
TEAMMATE_CLAIM_RADIUS = 80

# The kill cooldown fallback before HUD measurement: Crewrift Prime (0.3.9, our
# target league) uses 500 ticks; regular Crewrift (0.1.58) uses 800. We still learn
# the true value from the HUD once a cooldown runs to ready.
DEFAULT_KILL_COOLDOWN_TICKS = 500

# Enter Search this many ticks before the kill comes off cooldown. Search finds
# and follows a victim; Hunt only activates once the kill is ready and a victim is
# visible. Raised from 100 → 250 (half the 500-tick cooldown): we want to be already
# shadowing an isolated victim when the kill comes ready, so the cooldown window
# converts to a kill ASAP — a partner's kill→report can reset our cooldown, so banking
# our own kill quickly is the only lever on our side (see tentative lessons). 250
# deliberately stops short of "search the whole cooldown": the BE_DUMB ceiling arm
# (search ~97% of ticks) tripled our ejection rate (14%→40%) for only +10% kills, so we
# keep a Pretend window for cover.
SEARCH_LEAD_TICKS = 250

# Backwards-compatible name for docs/tests that still refer to the old Hunt lead
# term. New code should use SEARCH_LEAD_TICKS.
HUNT_LEAD_TICKS = SEARCH_LEAD_TICKS


def kill_urgency_ticks(belief: Belief) -> int:
    """How long we have been able to kill without doing so (0 if not kill-ready)."""

    if not belief.self_kill_ready or belief.kill_ready_since_tick is None:
        return 0
    return max(0, belief.last_tick - belief.kill_ready_since_tick)


def ticks_until_kill_ready(belief: Belief) -> int:
    """Estimated ticks until the kill becomes available (0 if ready now).

    The HUD is binary (ready / cooldown, no countdown), so this reconstructs the
    countdown from the tracked cooldown start (`kill_cooldown_start_tick`) plus the
    learned duration (`kill_cooldown_estimate`, falling back to the game default
    before anything has been measured). With no cooldown start observed yet it
        assumes a full cooldown remains, so callers won't enter Search on no
        information.
    """

    if belief.self_kill_ready:
        return 0
    if belief.kill_cooldown_start_tick is None:
        return DEFAULT_KILL_COOLDOWN_TICKS
    duration = belief.kill_cooldown_estimate or DEFAULT_KILL_COOLDOWN_TICKS
    return max(0, belief.kill_cooldown_start_tick + duration - belief.last_tick)


def has_trackable_victim(belief: Belief) -> bool:
    """Whether any non-teammate has been seen recently enough for Search to follow.

    Kept as a useful readout; Hunt itself requires current visibility.
    """

    return any(
        entry.color not in belief.teammate_colors
        and entry.life_status != "dead"
        and belief.last_tick - entry.last_seen_tick <= TRACK_WINDOW_TICKS
        for entry in belief.roster.values()
    )


def visible_victims(belief: Belief) -> list[PlayerRecord]:
    """Live non-teammates visible on the current tick."""

    return [
        entry
        for entry in belief.roster.values()
        if entry.color not in belief.teammate_colors
        and entry.life_status != "dead"
        and entry.last_seen_tick == belief.last_tick
    ]


def has_visible_victim(belief: Belief) -> bool:
    """Whether a live non-teammate crewmate is visible right now."""

    return bool(visible_victims(belief))


def select_victim(belief: Belief) -> PlayerRecord | None:
    """The crewmate to commit to hunting: the most-isolated reachable visible
    crewmate (a straggler — easiest to finish off unwitnessed), tie-broken by
    nearest to us. ``None`` when no non-teammate is visible/reachable."""

    self_xy = _self_xy(belief)
    if self_xy is None:
        return None
    crew = visible_victims(belief)
    if not crew:
        return None
    candidates = crew
    if belief.nav is not None:
        candidates = [t for t in crew if plan_route(belief.nav, self_xy, (t.world_x, t.world_y))]
        if not candidates:
            return None
    unclaimed = [target for target in candidates if not _claimed_by_teammate(target, belief, self_xy)]
    if unclaimed:
        candidates = unclaimed
    # Prefer the most isolated (largest gap to its nearest other crewmate), then nearest.
    return max(candidates, key=lambda t: (_isolation(t, belief), -_dist2(self_xy, (t.world_x, t.world_y))))


def clear_window_ticks() -> int:
    """The all-clear window, env-overridable via ``CREWBORG_CLEAR_WINDOW``."""

    raw = os.environ.get("CREWBORG_CLEAR_WINDOW")
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    return CLEAR_WINDOW_TICKS


def witness_gate_mode() -> str:
    """``visibility`` (default) or ``proximity`` (the shipped control arm)."""

    mode = (os.environ.get("CREWBORG_WITNESS_GATE") or "").strip().lower()
    return mode if mode in WITNESS_GATE_MODES else "visibility"


def unwitnessed(belief: Belief, target: PlayerRecord) -> bool:
    """Whether killing ``target`` now would go unseen, at the current urgency level.

    Two tests, both relaxed by urgency so a perpetually-shadowed imposter still
    escalates rather than stalling forever (design §10):

    1. nobody within the isolation ring of the victim (the shipped proximity proxy);
    2. nobody but the victim and our teammates VISIBLE to us for a continuous
       ``clear_window_ticks()`` — the actual question, see the note on the constant.

    Both must pass. They are not redundant: (1) catches a crewmate who is close but
    occluded from us, (2) catches the one we can plainly see standing past the ring.
    """

    frac = min(1.0, kill_urgency_ticks(belief) / URGENCY_FULL_TICKS)
    radius_sq = (BASE_ISOLATION_RADIUS * (1.0 - frac)) ** 2
    window = int(WITNESS_WINDOW_TICKS * (1.0 - frac))
    if not _is_unwitnessed(target, belief, radius_sq, window):
        return False
    if witness_gate_mode() == "proximity":
        return True
    clear = int(clear_window_ticks() * (1.0 - frac))
    if clear <= 0:
        return True  # full urgency ⇒ no requirement, matching the proximity arm
    return _nobody_else_visible_since(target, belief, clear)


def _nobody_else_visible_since(target: PlayerRecord, belief: Belief, window: int) -> bool:
    """Whether no live non-teammate except ``target`` was rendered to us for ``window``.

    ``last_seen_tick`` is the most recent tick that player was in our view, so
    "staler than the window" for every one of them means the window was clear
    throughout — the continuity is implied, no extra state needed.

    Exclusions: the victim (we must see it to kill it, so it can never be the
    disqualifying sighting), our fellow imposters, the dead, and ourselves — our own
    record refreshes every tick and would make this permanently false.
    """

    for other in belief.roster.values():
        if other.color in (target.color, belief.self_color):
            continue
        if other.color in belief.teammate_colors:
            continue
        if other.life_status == "dead":
            continue
        if belief.last_tick - other.last_seen_tick <= window:
            return False
    return True


def _isolation(target: PlayerRecord, belief: Belief) -> float:
    """Distance² to the nearest *other* live non-teammate — higher means more isolated."""

    target_xy = (target.world_x, target.world_y)
    gaps = [
        _dist2(target_xy, (o.world_x, o.world_y))
        for o in belief.roster.values()
        if o.color != target.color and o.color not in belief.teammate_colors and o.life_status != "dead"
    ]
    return min(gaps) if gaps else float("inf")


def _is_unwitnessed(target: PlayerRecord, belief: Belief, radius_sq: float, window: int) -> bool:
    """Whether no live non-teammate crewmate is close enough (and recent enough) to see the kill."""

    target_xy = (target.world_x, target.world_y)
    for other in belief.roster.values():
        if other.color == target.color or other.color in belief.teammate_colors:
            continue  # the victim itself and fellow imposters are never witnesses
        if other.life_status == "dead":
            continue  # a dead crewmate cannot witness the kill
        if belief.last_tick - other.last_seen_tick > window:
            continue  # last seen too long ago to credibly still be watching
        if _dist2(target_xy, (other.world_x, other.world_y)) <= radius_sq:
            return False
    return True


def nobody_seen_recently(belief: Belief, window: int) -> bool:
    """Whether no live non-teammate crewmate has been in view for ``window`` ticks.

    The pure-recency sibling of :func:`_is_unwitnessed`: no distance term, because
    the question is not "could someone see this spot" but "is there anyone who
    could later place us here at all". Used to decide whether self-reporting our
    own kill is safe (``strategy/rule_based.py``) — if nobody has laid eyes on us
    for long enough, no crewmate holds a recent sighting to contradict the report.

    Same exclusions as the witness check, plus ourselves: our own record sits in
    the roster and is refreshed every tick, so leaving it in would make this
    permanently false. The victim needs no special case — the body marks them
    dead, and the dead are excluded.
    """

    for other in belief.roster.values():
        if other.color == belief.self_color or other.color in belief.teammate_colors:
            continue
        if other.life_status == "dead":
            continue
        if belief.last_tick - other.last_seen_tick <= window:
            return False
    return True


def _claimed_by_teammate(target: PlayerRecord, belief: Belief, self_xy: tuple[int, int]) -> bool:
    target_xy = (target.world_x, target.world_y)
    self_dist = _dist2(self_xy, target_xy)
    for teammate in belief.roster.values():
        if teammate.color not in belief.teammate_colors:
            continue
        if teammate.life_status == "dead":
            continue
        if belief.last_tick - teammate.last_seen_tick > TRACK_WINDOW_TICKS:
            continue
        teammate_dist = _dist2((teammate.world_x, teammate.world_y), target_xy)
        if teammate_dist < self_dist and teammate_dist <= TEAMMATE_CLAIM_RADIUS**2:
            return True
    return False


# --- Recon (pre-position on a crewmate just before the kill comes off cooldown) ----
#
# Diagnosis (2026-06-25 warehouse head-to-head vs crewborg-aaln): at the moment our
# cooldown comes off we have a crewmate in view only ~53% of the time (Aaron: 83%) —
# we drift away from crew we saw earlier in the cooldown cycle. Recon closes that gap:
# inside RECON_WINDOW ticks of ready, beeline to the most-recently-seen crewmate so the
# instant we can kill, a victim is in hand and Hunt fires immediately.

# Ticks-before-ready at which to start recon. Deliberately short for now (a long window
# = Aaron-style overextension that gets caught); env-tunable so we can sweep it.
RECON_WINDOW_TICKS = 100


def recon_window() -> int:
    """The recon trigger window (ticks before kill-ready), env-overridable via
    ``CREWBORG_RECON_WINDOW`` so it can be swept without a rebuild."""

    raw = os.environ.get("CREWBORG_RECON_WINDOW")
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    return RECON_WINDOW_TICKS


def most_recent_victim(belief: Belief) -> PlayerRecord | None:
    """The most-recently-seen live non-teammate crewmate — the target to close on
    during recon (its ``world_x/y`` is the live position when visible, else last-known).
    ``None`` when no crewmate has been seen at all."""

    crew = [
        entry
        for entry in belief.roster.values()
        if entry.color not in belief.teammate_colors and entry.life_status != "dead"
    ]
    if not crew:
        return None
    return max(crew, key=lambda entry: entry.last_seen_tick)


def _self_xy(belief: Belief) -> tuple[int, int] | None:
    if belief.self_world_x is None or belief.self_world_y is None:
        return None
    return belief.self_world_x, belief.self_world_y


def _dist2(a: tuple[int, int], b: tuple[int, int]) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
