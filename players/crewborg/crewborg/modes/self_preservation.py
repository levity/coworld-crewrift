"""Crew safety: early safe-distance separation from a lone follower.

RETAINED REJECTED EXPERIMENT -- default-off, on the chopping block (docs/TODO.md),
kept deliberately. Its hosted A/B was clearly negative (wins 50% -> 30%, all-8
tasks 89% -> 60%), so this is the strongest null of the six retained behaviours
and the least likely to come back. But that verdict, like the others, was read off
team win rate over 100 games, and this behaviour's actual claim is about survival
GEOMETRY -- separation maintained from a lone follower -- which the eval never
measured directly. Kept as a reference implementation of the productive-retreat
design (steer to a real task that widens the gap, rather than blind flight) and as
a candidate for re-measurement under the finer test regime. See the retention note
in modes/normal.py for the full reasoning. Reactivation needs a pre-registered
mechanism hypothesis, not a hunch.

Gated by ``CREWBORG_SELF_PRESERVATION`` (and deduction history). On top of
ordinary task completion -- including group-tasking cohesion, which is env-gated
inside :class:`NormalMode` and stays on in this mode -- this adds one behavior:
when exactly one other player has stayed within ``SAFE_RADIUS`` (deliberately
LARGER than the 64px danger radius) for ``REACTION_TICKS`` continuous ticks, and
no second player is nearby to form a group, retreat *productively* by steering to
the nearest remaining reachable task whose anchor increases our separation from
that lone follower.

Why a larger radius and a task-based retreat. Crew and impostors move at
identical speed (one global ``maxSpeed`` in the sim, no role modifier), so once a
killer is already adjacent no equal-speed flight can open a gap -- and a crewmate
fleeing from a standstill even loses the acceleration ramp. Reacting earlier, at
``SAFE_RADIUS`` and before the follower is in kill range, preserves a margin the
killer has to spend its own ramp to close. Routing the retreat through a real
task keeps the win condition moving and follows reachable nav anchors, so it
never abandons a task or drives into a wall -- the failure modes of the earlier
blind-repulsion and witness-seeking designs. If the lone player is crew it simply
will not follow, so the separation is free; if it is an impostor, we get a head
start. When no remaining task increases separation we keep tasking normally
rather than fleeing blindly.
"""

from __future__ import annotations

import os

from crewborg.deduction.config import enabled as deduction_history_enabled
from crewborg.modes.imposter_common import dist2, task_point
from crewborg.modes.normal import NormalMode
from crewborg.types import (
    SELF_RECORD_DX,
    SELF_RECORD_DY,
    SELF_SPRITE_MATCH_SQ,
    ActionState,
    Belief,
    Intent,
    PlayerRecord,
)
from players.player_sdk import Mode

# React while a single companion sits within this radius. Larger than the 64px
# danger radius on purpose: opening distance before the follower reaches kill
# range is the only way equal-speed movement can keep a killer off us.
SAFE_RADIUS_SQ = 96**2
# Continuous ticks one-on-one before acting, so a crewmate merely passing through
# does not trigger a retreat.
REACTION_TICKS = 12


def enabled() -> bool:
    return _truthy_env("CREWBORG_SELF_PRESERVATION") and deduction_history_enabled()


class SelfPreservationMode(Mode[Belief, ActionState, Intent]):
    name = "self_preservation"

    def __init__(self, params=None) -> None:
        super().__init__(params)
        self._normal = NormalMode()
        self._companion: str | None = None
        self._since_tick: int | None = None
        self._retreat_target: int | None = None

    def decide(self, belief: Belief, action_state: ActionState) -> Intent:
        retreat = self._safe_distance_intent(belief)
        if retreat is not None:
            return retreat
        return self._normal.decide(belief, action_state)

    def _safe_distance_intent(self, belief: Belief) -> Intent | None:
        if (
            not enabled()
            or belief.self_role != "crewmate"
            or not belief.self_alive
            or belief.self_world_x is None
            or belief.self_world_y is None
        ):
            self._clear()
            return None

        nearby = _current_nearby(belief)
        if len(nearby) != 1:
            self._clear()
            return None

        companion = nearby[0]
        if companion.color != self._companion:
            self._companion = companion.color
            self._since_tick = belief.last_tick
            self._retreat_target = None

        assert self._since_tick is not None
        if belief.last_tick - self._since_tick < REACTION_TICKS:
            return None

        return self._retreat_intent(belief, companion)

    def _retreat_intent(self, belief: Belief, companion: PlayerRecord) -> Intent | None:
        """Steer to the nearest remaining reachable task that opens the gap."""

        if belief.map is None:
            return None
        self_xy = (belief.self_world_x, belief.self_world_y)
        threat = (companion.world_x, companion.world_y)
        current_gap = dist2(threat, self_xy)

        def opens_gap(index: int) -> bool:
            if index not in belief.visible_task_indices or index >= len(belief.map.tasks):
                return False
            # Skip tasks the nav graph cannot route to (holding still there opens
            # no distance); before the graph exists, task_point falls back to center.
            if belief.nav is not None and belief.nav.task_anchor(index) is None:
                return False
            return dist2(threat, task_point(belief, index)) > current_gap

        # Hold the chosen retreat task while it still opens the gap, so a moving
        # follower cannot make us oscillate between stations (NormalMode latches
        # its own target for the same reason).
        if self._retreat_target is None or not opens_gap(self._retreat_target):
            candidates = [
                (dist2(self_xy, task_point(belief, index)), index)
                for index in belief.visible_task_indices
                if opens_gap(index)
            ]
            self._retreat_target = min(candidates)[1] if candidates else None

        if self._retreat_target is None:
            return None
        duration = belief.last_tick - self._since_tick
        return Intent(
            kind="complete_task",
            task_index=self._retreat_target,
            target_color=companion.color,
            reason=(
                f"self preservation (safe distance): task {self._retreat_target} away from sole "
                f"nearby {companion.color}; continuous_ticks={duration}"
            ),
        )

    def _clear(self) -> None:
        self._companion = None
        self._since_tick = None
        self._retreat_target = None


def _current_nearby(belief: Belief) -> list[PlayerRecord]:
    """Other live players seen this tick within ``SAFE_RADIUS``, self excluded."""

    self_xy = (belief.self_world_x, belief.self_world_y)
    return [
        record
        for record in belief.roster.values()
        if record.color != belief.self_color
        and not _matches_self_sprite(record, belief, self_xy)
        and record.life_status == "alive"
        and record.last_seen_tick == belief.last_tick
        and dist2(self_xy, (record.world_x, record.world_y)) <= SAFE_RADIUS_SQ
    ]


def _matches_self_sprite(
    record: PlayerRecord,
    belief: Belief,
    self_xy: tuple[int, int],
) -> bool:
    expected = (self_xy[0] + SELF_RECORD_DX, self_xy[1] + SELF_RECORD_DY)
    return (
        record.last_seen_tick == belief.last_tick
        and dist2(expected, (record.world_x, record.world_y)) <= SELF_SPRITE_MATCH_SQ
    )


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}
