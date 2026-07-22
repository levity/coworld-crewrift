"""Reactive crew escape from a high-confidence one-on-one threat.

This mode is a consumer of the append-only deduction history. It caches derived
posterior results briefly for runtime cost, but never writes a conclusion or a
movement choice back into the solver ledger.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from crewborg.deduction.collector import history_from_belief
from crewborg.deduction.config import enabled as deduction_history_enabled
from crewborg.deduction.inference import InferenceResult, infer
from crewborg.modes.normal import NormalMode
from crewborg.modes.stick import StickMode, enabled as stick_enabled
from crewborg.types import ActionState, Belief, Intent, PlayerRecord
from players.player_sdk import Mode

RISK_RADIUS_SQ = 44**2
GROUP_RADIUS_SQ = 120**2
GROUP_FIX_TICKS = 48
POSTERIOR_REFRESH_TICKS = 72
ESCAPE_COMMIT_TICKS = 72
DEFAULT_THREAT_PROBABILITY = 0.75


def enabled() -> bool:
    return (
        _truthy_env("CREWBORG_SELF_PRESERVATION")
        and deduction_history_enabled()
    )


def _threat_probability() -> float:
    raw = os.environ.get("CREWBORG_SELF_PRESERVATION_P", "").strip()
    try:
        value = float(raw) if raw else DEFAULT_THREAT_PROBABILITY
    except ValueError:
        return DEFAULT_THREAT_PROBABILITY
    return value if 0.0 < value < 1.0 else DEFAULT_THREAT_PROBABILITY


@dataclass(frozen=True)
class _GroupDestination:
    point: tuple[int, int]
    colors: tuple[str, ...]


class SelfPreservationMode(Mode[Belief, ActionState, Intent]):
    name = "self_preservation"

    def __init__(self, params=None) -> None:
        super().__init__(params)
        self._normal = NormalMode()
        self._stick = StickMode()
        self._last_solve_tick: int | None = None
        self._inference: InferenceResult | None = None
        self._threat: str | None = None
        self._group_colors: tuple[str, ...] = ()
        self._escape_until = 0

    def decide(self, belief: Belief, action_state: ActionState) -> Intent:
        escape = self._escape_intent(belief)
        if escape is not None:
            return escape
        if stick_enabled():
            return self._stick.decide(belief, action_state)
        return self._normal.decide(belief, action_state)

    def _escape_intent(self, belief: Belief) -> Intent | None:
        if not enabled() or belief.self_role != "crewmate" or not belief.self_alive:
            self._clear_escape()
            return None
        if belief.self_world_x is None or belief.self_world_y is None:
            self._clear_escape()
            return None

        nearby = _current_nearby(belief)
        if self._threat is not None:
            if (
                belief.last_tick >= self._escape_until
                or len(nearby) != 1
                or nearby[0].color != self._threat
            ):
                self._clear_escape()
                return None
            else:
                destination = _destination_for_colors(
                    belief,
                    self._group_colors,
                )
                if destination is None:
                    self._clear_escape()
                    return None
                else:
                    return self._intent(
                        destination.point,
                        threat=self._threat,
                        probability=(
                            self._inference.marginal(self._threat)
                            if self._inference is not None
                            else 0.0
                        ),
                    )

        if len(nearby) != 1:
            return None
        result = self._current_inference(belief)
        if result is None or result.error is not None:
            return None

        companion = nearby[0].color
        probability = result.marginal(companion)
        if companion not in result.pins and probability < _threat_probability():
            return None

        excluded = {
            color
            for color, marginal in result.marginals
            if marginal >= _threat_probability()
        } | set(result.pins)
        destination = _best_group_destination(belief, excluded=excluded)
        if destination is None:
            return None

        self._threat = companion
        self._group_colors = destination.colors
        self._escape_until = belief.last_tick + ESCAPE_COMMIT_TICKS
        return self._intent(
            destination.point,
            threat=companion,
            probability=probability,
        )

    def _current_inference(self, belief: Belief) -> InferenceResult | None:
        if (
            self._last_solve_tick is not None
            and belief.last_tick >= self._last_solve_tick
            and belief.last_tick - self._last_solve_tick < POSTERIOR_REFRESH_TICKS
        ):
            return self._inference
        history = history_from_belief(belief)
        self._last_solve_tick = belief.last_tick
        self._inference = infer(history) if history is not None else None
        return self._inference

    def _intent(
        self,
        point: tuple[int, int],
        *,
        threat: str,
        probability: float,
    ) -> Intent:
        return Intent(
            kind="navigate_to",
            point=point,
            target_color=threat,
            reason=(
                "self preservation: leave one-on-one threat "
                f"{threat} at P(imposter)={probability:.3f} for witnesses"
            ),
        )

    def _clear_escape(self) -> None:
        self._threat = None
        self._group_colors = ()
        self._escape_until = 0


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


def _best_group_destination(
    belief: Belief,
    *,
    excluded: set[str],
) -> _GroupDestination | None:
    records = [
        record
        for record in belief.roster.values()
        if record.color != belief.self_color
        and record.color not in excluded
        and record.life_status == "alive"
        and 0 <= belief.last_tick - record.last_seen_tick <= GROUP_FIX_TICKS
    ]
    if len(records) < 2:
        return None
    self_xy = (belief.self_world_x, belief.self_world_y)
    assert self_xy[0] is not None and self_xy[1] is not None
    clusters = []
    for anchor in records:
        cluster = tuple(
            sorted(
                (
                    other
                    for other in records
                    if _d2(
                        (anchor.world_x, anchor.world_y),
                        (other.world_x, other.world_y),
                    )
                    <= GROUP_RADIUS_SQ
                ),
                key=lambda record: record.color,
            )
        )
        if len(cluster) >= 2:
            clusters.append((anchor, cluster))
    if not clusters:
        return None
    anchor, cluster = min(
        clusters,
        key=lambda item: (
            -len(item[1]),
            _d2(self_xy, (item[0].world_x, item[0].world_y)),
            item[0].color,
        ),
    )
    return _GroupDestination(
        point=(anchor.world_x, anchor.world_y),
        colors=tuple(record.color for record in cluster),
    )


def _destination_for_colors(
    belief: Belief,
    colors: tuple[str, ...],
) -> _GroupDestination | None:
    records = tuple(
        belief.roster[color]
        for color in colors
        if color in belief.roster
        and belief.roster[color].life_status == "alive"
        and 0 <= belief.last_tick - belief.roster[color].last_seen_tick <= GROUP_FIX_TICKS
    )
    if len(records) < 2:
        return None
    self_xy = (belief.self_world_x, belief.self_world_y)
    assert self_xy[0] is not None and self_xy[1] is not None
    anchors = [
        record
        for record in records
        if sum(
            _d2(
                (record.world_x, record.world_y),
                (other.world_x, other.world_y),
            )
            <= GROUP_RADIUS_SQ
            for other in records
        )
        >= 2
    ]
    if not anchors:
        return None
    anchor = min(
        anchors,
        key=lambda record: (
            _d2(self_xy, (record.world_x, record.world_y)),
            record.color,
        ),
    )
    return _GroupDestination(
        point=(anchor.world_x, anchor.world_y),
        colors=colors,
    )


def _d2(a: tuple[int | None, int | None], b: tuple[int, int]) -> int:
    assert a[0] is not None and a[1] is not None
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}
