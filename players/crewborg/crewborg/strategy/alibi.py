"""Co-presence alibis (opt-in, default OFF).

The mirror of witnessing a kill. When a crewmate is found dead, the killer must be
someone who was **not** in our view at the time of the kill — so every player we had
*continuously in sight across the victim's death window* is exonerated. Those players
become soft CLEARs the joint meeting solver can consume, exactly like watched-task
clears (design §10 / ``strategy/meeting/solver.py``).

This is deliberately **modular and self-contained**:

- Default OFF; gated by ``CREWBORG_ALIBI``. When off, :func:`update_alibi` is a no-op and
  :func:`alibi_clears` returns an empty set, so baseline behaviour is byte-identical.
- All state lives in one loosely-typed ``belief.alibi_state`` dict this module owns — no
  new typed fields, no import cycle with ``types``.
- It reads only what perception already records (roster sightings + deaths). It works with
  the current (passive) movement; a stay-with-group positioning mode simply enlarges the
  co-visible set and thus the number of alibis produced.

Soundness over coverage: an alibi is granted only when we had the player in an *unbroken*
line of sight from before the victim was last seen alive through the moment we learn of the
death. That misses many true alibis (we can only clear players still in view when the body
turns up) but never fabricates one, so the CLEAR evidence stays trustworthy.
"""

from __future__ import annotations

import os
from typing import Any

# Bridge a line-of-sight run across a gap this small (occlusion / a few dropped frames);
# a longer gap breaks continuity and restarts the visible-run. Matches the event log's
# EVENT_MERGE_GRACE_TICKS intent.
VISIBLE_GRACE_TICKS = 3


def enabled() -> bool:
    return os.environ.get("CREWBORG_ALIBI", "0") not in ("", "0", "false", "False")


def _state(belief: Any) -> dict[str, Any]:
    st = getattr(belief, "alibi_state", None)
    if not st:
        st = {
            "visible_since": {},  # color -> first tick of the current unbroken visible run
            "last_seen": {},      # color -> last tick we saw them (for gap detection)
            "processed_deaths": set(),  # victim colors already turned into alibis
            "cleared": set(),     # colors exonerated by a co-presence alibi
        }
        belief.alibi_state = st
    return st


def update_alibi(belief: Any) -> None:
    """Fold this tick's sightings into visible-runs and mint alibis for fresh deaths.

    Composed into the fast loop after ``update_event_log``; a no-op unless enabled.
    """

    if not enabled():
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
    for color, record in roster.items():
        if color == self_color:
            continue
        if getattr(record, "last_seen_tick", None) == tick and getattr(record, "life_status", None) != "dead":
            visible_now.add(color)
            prev = last_seen.get(color)
            if prev is None or tick - prev > VISIBLE_GRACE_TICKS:
                visible_since[color] = tick  # (re)start the run
            last_seen[color] = tick

    # 2) Mint alibis for any newly-learned death. The killer acted at some instant in
    #    ``[victim.last_seen_alive, death_learned]``; anyone we held in continuous sight
    #    spanning that whole window could not have done it.
    for color, record in roster.items():
        if getattr(record, "life_status", None) != "dead":
            continue
        if color in st["processed_deaths"]:
            continue
        st["processed_deaths"].add(color)
        window_start = getattr(record, "last_seen_tick", None)  # last time WE saw the victim alive
        if window_start is None:
            continue
        for other in visible_now:
            if other == color:
                continue
            since = visible_since.get(other)
            if since is not None and since <= window_start:
                st["cleared"].add(other)


def alibi_clears(belief: Any) -> set[str]:
    """Colors exonerated by a co-presence alibi (empty unless enabled)."""

    if not enabled():
        return set()
    st = getattr(belief, "alibi_state", None)
    if not st:
        return set()
    return set(st.get("cleared", ()))
