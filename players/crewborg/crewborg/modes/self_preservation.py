"""Role-agnostic local repulsion from one-on-one exposure.

This is risk control, not deduction. Exactly one currently visible living player
inside the risk radius preempts tasking and produces a fresh reachable goal away
from that player. The intent ends immediately when the radius contains nobody or
at least two other players.
"""

from __future__ import annotations

import math
import os

from crewborg.deduction.config import enabled as deduction_history_enabled
from crewborg.modes.normal import NormalMode
from crewborg.modes.stick import StickMode, enabled as stick_enabled
from crewborg.types import ActionState, Belief, Intent, PlayerRecord
from players.player_sdk import Mode

RISK_RADIUS_SQ = 64**2
REPULSION_DISTANCE = 96
PURSUIT_TRACE_TICKS = 12
NAV_SEARCH_HOPS = 3


def enabled() -> bool:
    return _truthy_env("CREWBORG_SELF_PRESERVATION") and deduction_history_enabled()


class SelfPreservationMode(Mode[Belief, ActionState, Intent]):
    name = "self_preservation"

    def __init__(self, params=None) -> None:
        super().__init__(params)
        self._normal = NormalMode()
        self._stick = StickMode()
        self._companion: str | None = None
        self._repelling_since: int | None = None

    def decide(self, belief: Belief, action_state: ActionState) -> Intent:
        repulsion = self._repulsion_intent(belief)
        if repulsion is not None:
            return repulsion
        if stick_enabled():
            return self._stick.decide(belief, action_state)
        return self._normal.decide(belief, action_state)

    def _repulsion_intent(self, belief: Belief) -> Intent | None:
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
            self._repelling_since = belief.last_tick

        assert self._repelling_since is not None
        duration = max(0, belief.last_tick - self._repelling_since)
        stage = "pursuit" if duration >= PURSUIT_TRACE_TICKS else "repulsion"
        goal = _repulsion_goal(belief, companion)
        return Intent(
            kind="navigate_to",
            point=goal,
            target_color=companion.color,
            reason=(
                f"self preservation ({stage}): move away from sole nearby player "
                f"{companion.color}; continuous_ticks={duration}"
            ),
        )

    def _clear(self) -> None:
        self._companion = None
        self._repelling_since = None


def _current_nearby(belief: Belief) -> list[PlayerRecord]:
    self_xy = (belief.self_world_x, belief.self_world_y)
    assert self_xy[0] is not None and self_xy[1] is not None
    return sorted(
        (
            record
            for record in belief.roster.values()
            if record.color != belief.self_color
            and record.life_status == "alive"
            and record.last_seen_tick == belief.last_tick
            and _d2(self_xy, (record.world_x, record.world_y)) <= RISK_RADIUS_SQ
        ),
        key=lambda record: record.color,
    )


def _repulsion_goal(belief: Belief, companion: PlayerRecord) -> tuple[int, int]:
    self_xy = (belief.self_world_x, belief.self_world_y)
    assert self_xy[0] is not None and self_xy[1] is not None
    other_xy = (companion.world_x, companion.world_y)

    if belief.nav is None:
        return _direct_goal(self_xy, other_xy, companion.color)

    start = belief.nav.nearest_reachable_node(*self_xy)
    if start is None:
        return _direct_goal(self_xy, other_xy, companion.color)

    candidates = _nearby_nav_cells(belief, start)
    if not candidates:
        return _direct_goal(self_xy, other_xy, companion.color)
    best = max(
        candidates,
        key=lambda cell: (
            _d2(belief.nav.node_point[cell], other_xy),
            _d2(belief.nav.node_point[cell], self_xy),
            -cell[0],
            -cell[1],
        ),
    )
    return belief.nav.node_point[best]


def _nearby_nav_cells(belief: Belief, start: tuple[int, int]) -> set[tuple[int, int]]:
    assert belief.nav is not None
    seen = {start}
    frontier = {start}
    for _ in range(NAV_SEARCH_HOPS):
        next_frontier = {
            neighbour
            for cell in frontier
            for neighbour, _cost in belief.nav.adjacency.get(cell, ())
            if neighbour in belief.nav.reachable and neighbour not in seen
        }
        if not next_frontier:
            break
        seen.update(next_frontier)
        frontier = next_frontier
    seen.discard(start)
    return seen


def _direct_goal(
    self_xy: tuple[int, int],
    other_xy: tuple[int, int],
    companion_color: str,
) -> tuple[int, int]:
    dx = self_xy[0] - other_xy[0]
    dy = self_xy[1] - other_xy[1]
    length = math.hypot(dx, dy)
    if length == 0:
        # Stable across processes; unlike hash(), this does not depend on hash seed.
        dx = 1 if sum(map(ord, companion_color)) % 2 == 0 else -1
        dy = 0
        length = 1
    return (
        round(self_xy[0] + REPULSION_DISTANCE * dx / length),
        round(self_xy[1] + REPULSION_DISTANCE * dy / length),
    )


def _d2(a: tuple[int | None, int | None], b: tuple[int, int]) -> int:
    assert a[0] is not None and a[1] is not None
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}
