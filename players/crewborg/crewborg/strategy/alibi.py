"""Append-only co-presence evidence for hidden kills (opt-in, default OFF).

The mirror of witnessing a kill. When a crewmate is *killed* somewhere we could not see,
the killer is an impostor who was **not** in our view at the time — so the killer lies in
the set of players we could *not* continuously see across the victim's death window.

Crucially, with two impostors this does **not** clear any individual player:
someone we had in sight during a kill only proves they were not *that* killer;
they could still be the second, non-killing impostor. We retain the complete
observation per kill and let the joint solver score it against every assignment.
The solver retains partial observations for audit, but uses only their
assumption-free consequence: an assignment is impossible if it has no member
who was both eligible to kill and not continuously co-present.

Modular + default OFF (``CREWBORG_ALIBI``): all logic and state live here (one
``belief.alibi_state`` dict this module owns); :func:`alibi_events` returns
``[]`` when off, so the solver's behaviour is byte-identical. Sound-over-complete:
a player is counted as alibied for a kill only across an *unbroken* line of
sight spanning the victim's ``[last-seen-alive, death-learned]`` window.
"""

from __future__ import annotations

import os
from typing import Any

from crewborg.types import KillAlibi

# "Rendered on the same screen" is not co-presence: retained replays contain
# killers visible 61-68 px away while killing a victim behind the observer's
# line-of-sight boundary. Require the fitted model's kill-range-plus-8 close
# bound on every frame.
COPRESENCE_DIST_SQ = 28**2

# Logical exclusions require strict continuity: any non-close frame breaks
# co-presence. Consecutive close sightings differ by one tick, so a larger delta
# restarts the run.
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


def _copresence_dist_sq() -> int | None:
    """Configured close bound; non-positive preserves the legacy visibility control."""

    try:
        distance = float(os.environ.get("CREWBORG_ALIBI_MAX_DIST", "28"))
    except ValueError:
        distance = 28.0
    if distance <= 0:
        return None
    if distance == 28:
        return COPRESENCE_DIST_SQ
    return round(distance * distance)


def _state(belief: Any) -> dict[str, Any]:
    st = getattr(belief, "alibi_state", None)
    if not st:
        st = {
            "close_since": {},          # color -> first tick of the current close run
            "last_close": {},           # color -> last close tick (for gap detection)
            "last_playing_tick": None,  # last tick on which a hidden kill was possible
            "processed_deaths": set(),  # victim colors already considered
            "events": [],               # append-only list[KillAlibi]
        }
        belief.alibi_state = st
    else:
        # State can survive a hot reload during local development. Add new keys
        # without rewriting or discarding any records owned by an earlier build.
        st.setdefault("processed_deaths", set())
        st.setdefault("events", [])
        st.setdefault("close_since", {})
        st.setdefault("last_close", {})
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
    if (
        self_color is None
        or getattr(belief, "self_world_x", None) is None
        or getattr(belief, "self_world_y", None) is None
    ):
        return
    roster = getattr(belief, "roster", {}) or {}
    st = _state(belief)
    close_since = st["close_since"]
    last_close = st["last_close"]
    distance_limit_sq = _copresence_dist_sq()

    # 1) Maintain each other player's current unbroken close-presence run.
    close_now: set[str] = set()
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
                dx = record.world_x - belief.self_world_x
                dy = record.world_y - belief.self_world_y
                if (
                    distance_limit_sq is None
                    or dx * dx + dy * dy <= distance_limit_sq
                ):
                    close_now.add(color)
                    prev = last_close.get(color)
                    if prev is None or tick - prev > MAX_UNSEEN_TICKS + 1:
                        close_since[color] = tick
                    last_close[color] = tick

    # A census is rendered after play has stopped. Close its possible kill window
    # at the last Playing tick, not at the sprite-less meeting frame.
    window_end = st.get("last_playing_tick")
    close_at_window_end = {
        color
        for color, seen_tick in last_close.items()
        if window_end is not None
        and window_end - seen_tick <= MAX_UNSEEN_TICKS
        and getattr(roster.get(color), "life_status", None) != "dead"
    }
    if close_now:
        close_at_window_end = close_now

    # 2) On a newly-learned KILL, record who we held in continuous sight across the whole
    #    death window: they are alibied for *this* kill (they were with us, not killing).
    # Multiple deaths may be learned in one census with no public ordering. A
    # newly discovered victim could have made an earlier kill before dying, so
    # only colors known dead before this observation are ineligible for every
    # fresh event.
    previously_dead = set(st["processed_deaths"])
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
            for other in close_at_window_end
            if other != color and close_since.get(other, tick) <= window_start
        ]
        if alibied:
            possible_killers = sorted(
                other
                for other, other_record in roster.items()
                if other not in {self_color, color}
                and (
                    getattr(other_record, "life_status", "unknown") != "dead"
                    or other not in previously_dead
                )
            )
            st["events"].append(
                KillAlibi(
                    observer_color=self_color,
                    victim_color=color,
                    death_source=record.death_source,
                    death_seen_tick=getattr(record, "death_seen_tick", None) or tick,
                    window_start_tick=window_start,
                    window_end_tick=window_end,
                    alibied_colors=tuple(sorted(alibied)),
                    possible_killers=tuple(possible_killers),
                )
            )


def alibi_events(belief: Any) -> list[KillAlibi]:
    """Return the complete immutable per-kill ledger (empty unless enabled)."""

    if not enabled():
        return []
    st = getattr(belief, "alibi_state", None)
    if not st:
        return []
    return [
        event if isinstance(event, KillAlibi) else KillAlibi.model_validate(event)
        for event in st.get("events", ())
    ]


def alibi_sets(belief: Any) -> list[frozenset[str]]:
    """Compatibility view of per-kill co-present colors (empty unless enabled).

    New inference must use :func:`alibi_events`; this view intentionally omits
    victim, timing, and alive-candidate context.
    """

    return [frozenset(event.alibied_colors) for event in alibi_events(belief)]
