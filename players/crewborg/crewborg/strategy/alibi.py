"""Co-presence alibis (opt-in, default OFF).

The mirror of witnessing a kill. When a crewmate is *killed* somewhere we could not see,
the killer is an impostor who was **not** in our view at the time — so the killer lies in
the set of players we could *not* continuously see across the victim's death window.

Crucially, with two impostors this does **not** clear any individual player: someone we had
in sight during a kill only proves they were not *that* killer; they could still be the
second, non-killing impostor. The one sound player-level consequence is a **pair
exclusion** — an impostor hypothesis is impossible iff *every* impostor in it was in our
continuous sight during the *same* kill (then that kill had no possible perpetrator). So we
publish, per kill, the set of co-present (alibied-for-that-kill) players and let the joint
solver drop any hypothesis fully contained in one of those sets. A lone alibi excludes
nothing.

Modular + default OFF (``CREWBORG_ALIBI``): all logic and state live here (one
``belief.alibi_state`` dict this module owns); :func:`alibi_sets` returns ``[]`` when off,
so the solver's behaviour is byte-identical. Sound-over-complete: a player is counted as
alibied for a kill only across an *unbroken* line of sight spanning the victim's
``[last-seen-alive, death-learned]`` window, so the exclusions never fire wrongly.
"""

from __future__ import annotations

import os
from typing import Any

# Logical exclusions require stricter evidence than movement tracking: any unseen
# frame breaks co-presence. Consecutive sightings differ by one tick, so a larger
# delta restarts the run.
MAX_UNSEEN_TICKS = 0

# A body/census learned immediately after the victim leaves view may be an observed
# (possibly ambiguous) kill. Require a real off-screen window before inferring that
# the killer had to be elsewhere.
VICTIM_ABSENCE_TICKS = 3

# Deaths we treat as kills (a hidden impostor did it). Ejections are public votes, not
# kills, so they carry no "killer was out of view" inference.
_KILL_SOURCES = ("body", "census")


def enabled() -> bool:
    return os.environ.get("CREWBORG_ALIBI", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _state(belief: Any) -> dict[str, Any]:
    st = getattr(belief, "alibi_state", None)
    if not st:
        st = {
            "visible_since": {},        # color -> first tick of the current unbroken visible run
            "last_seen": {},            # color -> last tick we saw them (for gap detection)
            "last_playing_tick": None,  # last tick on which a hidden kill was possible
            "processed_deaths": set(),  # victim colors already turned into an alibi set
            "sets": [],                 # list[list[str]]: per-kill co-present (alibied) players
        }
        belief.alibi_state = st
    return st


def update_alibi(belief: Any) -> None:
    """Fold this tick's sightings into visible-runs and record an alibi set per fresh kill.

    Composed into the fast loop after ``update_event_log``; a no-op unless enabled.
    """

    if (
        not enabled()
        or getattr(belief, "self_role", None) != "crewmate"
        or not getattr(belief, "self_alive", True)
    ):
        return

    tick = getattr(belief, "last_tick", None)
    if tick is None:
        return
    self_color = getattr(belief, "self_color", None)
    roster = getattr(belief, "roster", {}) or {}
    st = _state(belief)
    visible_since = st["visible_since"]
    last_seen = st["last_seen"]

    # 1) Maintain each other player's current unbroken line-of-sight run.
    visible_now: set[str] = set()
    if (
        getattr(belief, "phase", None) == "Playing"
        and getattr(belief, "camera_ready", False)
    ):
        st["last_playing_tick"] = tick
        for color, record in roster.items():
            if color == self_color:
                continue
            if (
                getattr(record, "last_seen_tick", None) == tick
                and getattr(record, "life_status", None) != "dead"
            ):
                visible_now.add(color)
                prev = last_seen.get(color)
                if prev is None or tick - prev > MAX_UNSEEN_TICKS + 1:
                    visible_since[color] = tick  # (re)start the run
                last_seen[color] = tick

    # A census is rendered after play has stopped. Close its possible kill window
    # at the last Playing tick, not at the sprite-less meeting frame.
    window_end = st.get("last_playing_tick")
    visible_at_window_end = {
        color
        for color, seen_tick in last_seen.items()
        if window_end is not None
        and window_end - seen_tick <= MAX_UNSEEN_TICKS
        and getattr(roster.get(color), "life_status", None) != "dead"
    }
    if visible_now:
        visible_at_window_end = visible_now

    # 2) On a newly-learned KILL, record who we held in continuous sight across the whole
    #    death window: they are alibied for *this* kill (they were with us, not killing).
    for color, record in roster.items():
        if getattr(record, "life_status", None) != "dead":
            continue
        if color in st["processed_deaths"]:
            continue
        st["processed_deaths"].add(color)
        if getattr(record, "death_source", None) not in _KILL_SOURCES:
            continue  # ejection etc. — no hidden killer to reason about
        window_start = getattr(record, "last_seen_tick", None)  # last time WE saw the victim alive
        if window_start is None:
            continue
        witnessed = any(
            event.kind == "kill" and event.target_color == color
            for other_record in roster.values()
            for event in getattr(other_record, "events", ())
        )
        if witnessed:
            continue
        # If the victim was still in (or only just dropped from) our rendered view
        # when the kill window closed, the killer may also be one of the players we
        # can see. In that case co-presence is not an alibi at all.
        if window_end is None or window_end - window_start <= VICTIM_ABSENCE_TICKS:
            continue
        alibied = [
            other
            for other in visible_at_window_end
            if other != color and visible_since.get(other, tick) <= window_start
        ]
        if alibied:
            st["sets"].append(alibied)


def alibi_sets(belief: Any) -> list[frozenset[str]]:
    """Per-kill co-present sets (empty unless enabled).

    Each set is the players who were provably not the killer of one specific victim. The
    solver excludes any impostor hypothesis contained in one of these sets (all its
    impostors alibied for the same kill ⇒ that kill had no perpetrator).
    """

    if not enabled():
        return []
    st = getattr(belief, "alibi_state", None)
    if not st:
        return []
    return [frozenset(group) for group in st.get("sets", ()) if group]
