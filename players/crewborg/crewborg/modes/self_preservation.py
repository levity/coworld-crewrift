"""Reactive crew escape from sustained one-on-one exposure.

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

RISK_RADIUS_SQ = 64**2
PURSUIT_RADIUS_SQ = 96**2
GROUP_RADIUS_SQ = 120**2
GROUP_FIX_TICKS = 48
POSTERIOR_REFRESH_TICKS = 72
SOFT_TRIGGER_TICKS = 12
PURSUIT_CONFIRM_TICKS = 12
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
class _WitnessDestination:
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
        self._encounter: str | None = None
        self._encounter_since: int | None = None
        self._threat: str | None = None
        self._excluded_colors: set[str] = set()
        self._group_colors: tuple[str, ...] = ()
        self._destination: tuple[int, int] | None = None
        self._soft_since: int | None = None
        self._hard_escape = False

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

        nearby = _current_nearby(belief, radius_sq=RISK_RADIUS_SQ)
        if self._threat is not None:
            witnesses = [record for record in nearby if record.color != self._threat]
            if witnesses:
                self._clear_escape()
                return None

            if not self._hard_escape:
                pursuers = _current_nearby(belief, radius_sq=PURSUIT_RADIUS_SQ)
                threat_is_pursuing = any(
                    record.color == self._threat for record in pursuers
                )
                if not threat_is_pursuing:
                    self._clear_escape()
                    return None
                assert self._soft_since is not None
                if belief.last_tick - self._soft_since >= PURSUIT_CONFIRM_TICKS:
                    self._hard_escape = True

            destination = self._refresh_destination(belief)
            if destination is None:
                self._clear_escape()
                return None
            return self._intent(
                destination,
                threat=self._threat,
                probability=(
                    self._inference.marginal(self._threat)
                    if self._inference is not None
                    else 0.0
                ),
                hard=self._hard_escape,
            )

        if len(nearby) != 1:
            self._clear_encounter()
            return None

        companion = nearby[0].color
        if companion != self._encounter:
            self._encounter = companion
            self._encounter_since = belief.last_tick

        result = self._current_inference(belief)
        probability = result.marginal(companion) if result is not None else 0.0
        high_confidence = (
            result is not None
            and result.error is None
            and (
                companion in result.pins
                or probability >= _threat_probability()
            )
        )
        assert self._encounter_since is not None
        exposure_ticks = belief.last_tick - self._encounter_since
        if not high_confidence and exposure_ticks < SOFT_TRIGGER_TICKS:
            return None

        excluded = {companion}
        if result is not None and result.error is None:
            excluded |= {
                color
                for color, marginal in result.marginals
                if marginal >= _threat_probability()
            } | set(result.pins)
        destination = _best_witness_destination(belief, excluded=excluded)
        if destination is None:
            return None

        self._threat = companion
        self._excluded_colors = excluded
        self._group_colors = destination.colors
        self._destination = destination.point
        self._soft_since = belief.last_tick
        self._hard_escape = high_confidence
        return self._intent(
            destination.point,
            threat=companion,
            probability=probability,
            hard=self._hard_escape,
        )

    def _refresh_destination(self, belief: Belief) -> tuple[int, int] | None:
        destination = _destination_for_colors(belief, self._group_colors)
        if destination is None:
            destination = _best_witness_destination(
                belief,
                excluded=self._excluded_colors,
            )
        if destination is not None:
            self._group_colors = destination.colors
            self._destination = destination.point
        return self._destination

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
        hard: bool,
    ) -> Intent:
        return Intent(
            kind="navigate_to",
            point=point,
            target_color=threat,
            reason=(
                f"self preservation ({'pursuit' if hard else 'isolation'}): "
                "leave one-on-one threat "
                f"{threat} at P(imposter)={probability:.3f} for witnesses"
            ),
        )

    def _clear_escape(self) -> None:
        self._threat = None
        self._excluded_colors.clear()
        self._group_colors = ()
        self._destination = None
        self._soft_since = None
        self._hard_escape = False
        self._clear_encounter()

    def _clear_encounter(self) -> None:
        self._encounter = None
        self._encounter_since = None


def _current_nearby(
    belief: Belief,
    *,
    radius_sq: int,
) -> list[PlayerRecord]:
    self_xy = (belief.self_world_x, belief.self_world_y)
    assert self_xy[0] is not None and self_xy[1] is not None
    return sorted(
        (
            record
            for record in belief.roster.values()
            if record.color != belief.self_color
            and record.life_status == "alive"
            and record.last_seen_tick == belief.last_tick
            and _d2(self_xy, (record.world_x, record.world_y)) <= radius_sq
        ),
        key=lambda record: record.color,
    )


def _best_witness_destination(
    belief: Belief,
    *,
    excluded: set[str],
) -> _WitnessDestination | None:
    records = [
        record
        for record in belief.roster.values()
        if record.color != belief.self_color
        and record.color not in excluded
        and record.life_status == "alive"
        and 0 <= belief.last_tick - record.last_seen_tick <= GROUP_FIX_TICKS
    ]
    if not records:
        return None
    self_xy = (belief.self_world_x, belief.self_world_y)
    assert self_xy[0] is not None and self_xy[1] is not None
    clusters = [
        (
            anchor,
            tuple(
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
            ),
        )
        for anchor in records
    ]
    anchor, cluster = min(
        clusters,
        key=lambda item: (
            -len(item[1]),
            _d2(self_xy, (item[0].world_x, item[0].world_y)),
            item[0].color,
        ),
    )
    return _WitnessDestination(
        point=(anchor.world_x, anchor.world_y),
        colors=tuple(record.color for record in cluster),
    )


def _destination_for_colors(
    belief: Belief,
    colors: tuple[str, ...],
) -> _WitnessDestination | None:
    records = tuple(
        belief.roster[color]
        for color in colors
        if color in belief.roster
        and belief.roster[color].life_status == "alive"
        and 0 <= belief.last_tick - belief.roster[color].last_seen_tick <= GROUP_FIX_TICKS
    )
    if not records:
        return None
    self_xy = (belief.self_world_x, belief.self_world_y)
    assert self_xy[0] is not None and self_xy[1] is not None
    anchor = min(
        records,
        key=lambda record: (
            _d2(self_xy, (record.world_x, record.world_y)),
            record.color,
        ),
    )
    return _WitnessDestination(
        point=(anchor.world_x, anchor.world_y),
        colors=colors,
    )


def _d2(a: tuple[int | None, int | None], b: tuple[int, int]) -> int:
    assert a[0] is not None and a[1] is not None
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}
