"""Crewrift's own rules — the facts both crew brains have to agree about.

``KILL_RANGE_SQ``, ``VENT_RANGE_SQ`` and ``effective_imposter_count`` are properties
of the *game*: they change only when the deployed game changes (pinned in
``tools/build/versions.env``). ``COPRESENCE_DISTANCE_SQ`` and ``VENT_WALK_MARGIN`` are
**perception tolerances derived from** a game rule (kill range, and max travel per
tick), so they can move when decoding changes even though the game has not.

They live here, once, because two copies of a game rule is how the two crew brains
silently stop describing the same game.

Nothing here imports from ``crewborg``, so either brain can depend on it without
depending on the other.
"""

from __future__ import annotations

# Kill fires within KillRange = 20px (dist² ≤ 400); vent within VentRange = 16px
# (dist² ≤ 256). Verified against ``src/crewrift/sim.nim``.
KILL_RANGE_SQ = 400
VENT_RANGE_SQ = 256

# The co-presence gate: kill range + 8px of decoding slack. Used by the fitted
# model's ``copresence_killrange_samples`` feature and by the deduction path's
# hidden-kill constraints, which must mean the same thing by the same number.
COPRESENCE_DISTANCE_SQ = 28**2

# Max distance a player can walk in one tick (MaxSpeed/MotionScale = 704/256 ≈
# 2.75, rounded up): a player materialising inside a vent from beyond this vented.
VENT_WALK_MARGIN = 3


def effective_imposter_count(total_players: int) -> int:
    """The game's ``effectiveImposterCount`` for a roster of ``total_players``.

    Fewer than five players is a degenerate lobby with no imposter. Above that the
    count grows one per two extra players. Mirrors ``design.md`` §10.1 and
    ``docs/suspicion.md`` §2 ("The prior — combinatorics"). §2 also states a
    ``[0, P-1]`` clamp; it is unreachable for ``P >= 5``, so it is deliberately not
    re-implemented here.
    """

    if total_players < 5:
        return 0
    return (total_players - 3) // 2
