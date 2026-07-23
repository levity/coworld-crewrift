"""Role-agnostic witness seeking after sustained one-on-one exposure.

This is risk control, not deduction. Twelve continuous ticks with exactly one
currently visible living player inside the risk radius permit movement toward a
currently visible witness. Without a witness, normal behavior continues; hosted
evidence showed that blind repulsion was actively harmful. The intent ends immediately
when the radius contains nobody or at least two other players.
"""

from __future__ import annotations

import os

from crewborg.deduction.config import enabled as deduction_history_enabled
from crewborg.modes.normal import NormalMode
from crewborg.modes.stick import StickMode, enabled as stick_enabled
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

RISK_RADIUS_SQ = 64**2
REACTION_TICKS = 12


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
        if duration < REACTION_TICKS:
            return None

        witness = _nearest_current_witness(belief, companion)
        if witness is None:
            return None
        return Intent(
            kind="navigate_to",
            point=(witness.world_x, witness.world_y),
            target_color=companion.color,
            reason=(
                f"self preservation (pursuit): move toward witness {witness.color}; sole nearby player "
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
            and not _matches_self_sprite(record, belief, self_xy)
            and record.life_status == "alive"
            and record.last_seen_tick == belief.last_tick
            and _d2(self_xy, (record.world_x, record.world_y)) <= RISK_RADIUS_SQ
        ),
        key=lambda record: record.color,
    )


def _nearest_current_witness(
    belief: Belief,
    companion: PlayerRecord,
) -> PlayerRecord | None:
    self_xy = (belief.self_world_x, belief.self_world_y)
    assert self_xy[0] is not None and self_xy[1] is not None
    candidates = [
        record
        for record in belief.roster.values()
        if record is not companion
        and record.color != belief.self_color
        and not _matches_self_sprite(record, belief, self_xy)
        and record.life_status == "alive"
        and record.last_seen_tick == belief.last_tick
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda record: (
            _d2(self_xy, (record.world_x, record.world_y)),
            record.color,
        ),
    )


def _matches_self_sprite(
    record: PlayerRecord,
    belief: Belief,
    self_xy: tuple[int, int],
) -> bool:
    expected = (self_xy[0] + SELF_RECORD_DX, self_xy[1] + SELF_RECORD_DY)
    return (
        record.last_seen_tick == belief.last_tick
        and _d2(expected, (record.world_x, record.world_y)) <= SELF_SPRITE_MATCH_SQ
    )


def _d2(a: tuple[int | None, int | None], b: tuple[int, int]) -> int:
    assert a[0] is not None and a[1] is not None
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}
