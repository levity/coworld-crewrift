"""Stay-with-group crew positioning (opt-in, default OFF).

The loss decomposition showed crew lose a task-completion race that is ended by imposter
kills (96% of losses had both imposters killing freely). Kills happen to isolated crew, so
a crewmate who has *finished its own tasks* is worth more loitering with the pack than
wandering alone: it denies kill windows (an imposter won't kill in front of a witness) and
maximises the co-visible set that :mod:`crewborg.strategy.alibi` turns into exonerations.

Design (merge-friendly, default OFF):

- Gated by ``CREWBORG_STICK``; dispatched from the crew path only when enabled. Off ⇒ this
  mode is never selected and behaviour is byte-identical to baseline.
- **Never sacrifices our own tasks.** ``StickMode`` composes ``NormalMode`` and passes its
  intent straight through while it is actively tasking; it only substitutes a regroup
  intent when Normal would otherwise idle or head back to the start room (i.e. our task
  list is done). So the shared task bar — the actual win condition — is never slowed.
- Biases toward the densest cluster of live crewmates (safety in numbers), and holds still
  once inside it to keep an unbroken line of sight (which is what earns alibis).
"""

from __future__ import annotations

import os

from crewborg.modes.normal import NormalMode
from crewborg.types import ActionState, Belief, Intent
from players.player_sdk import Mode

# Two live crewmates within this distance count as clustered — the anchor is whoever has
# the most neighbours (the crowd). ~room scale.
GROUP_RADIUS_SQ = 120**2
# Once this close to the crowd anchor, hold position instead of re-approaching, so our
# line of sight to the group stays unbroken (alibi continuity) without jitter.
HOLD_RADIUS_SQ = 72**2


def enabled() -> bool:
    return os.environ.get("CREWBORG_STICK", "0") not in ("", "0", "false", "False")


def _d2(a: tuple[int, int], b: tuple[int, int]) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


class StickMode(Mode[Belief, ActionState, Intent]):
    name = "stick"

    def __init__(self, params=None) -> None:
        super().__init__(params)
        self._normal = NormalMode()

    def decide(self, belief: Belief, action_state: ActionState) -> Intent:
        intent = self._normal.decide(belief, action_state)
        # Only override the "nothing left to do" outcomes; never interrupt real task work.
        done = intent.kind == "idle" or (
            intent.kind == "navigate_to" and "returning to the start" in (intent.reason or "")
        )
        if not done:
            return intent
        stick = self._stick_intent(belief)
        return stick if stick is not None else intent

    def _stick_intent(self, belief: Belief) -> Intent | None:
        if belief.self_world_x is None or belief.self_world_y is None:
            return None
        self_xy = (belief.self_world_x, belief.self_world_y)
        self_color = getattr(belief, "self_color", None)
        live = [
            r
            for r in belief.roster.values()
            if r.color != self_color
            and r.life_status != "dead"
            and r.last_seen_tick > 0  # has a real position fix
        ]
        if not live:
            return None

        def neighbours(record) -> int:
            here = (record.world_x, record.world_y)
            return sum(
                1
                for other in live
                if other is not record and _d2(here, (other.world_x, other.world_y)) <= GROUP_RADIUS_SQ
            )

        anchor = max(live, key=neighbours)
        target = (anchor.world_x, anchor.world_y)
        if _d2(self_xy, target) <= HOLD_RADIUS_SQ:
            return Intent(kind="idle", reason="stick: holding with the group")
        return Intent(kind="navigate_to", point=target, reason="stick: regrouping with crew")
