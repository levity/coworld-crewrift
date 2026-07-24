"""Report Body mode: report a body in view (design §7.1, §12).

Active while a body is currently visible. It emits ``report`` for the nearest
visible body; the action layer navigates to it and presses A in range. When the
report opens a meeting (``phase`` becomes ``Voting``) the selector switches to
Attend Meeting, so this mode yields automatically. Report policy default
(design §12) = always report a visible body; suspicion-aware reporting is later.

**Robustness (Prime replay fix).** Small body-localization error can leave us
believing we are in range while the server's true range rejects the press. The
action layer keeps a margin and drives point-blank on repeated failure
(``action.py``); here we cap how long we chase a single body: after
``REPORT_TIMEOUT_TICKS`` of dead presses we abandon it and resume normal tasking
rather than freeze in place until an imposter arrives. A body abandoned this way
is re-attempted the next time report_body activates (a fresh view / position).
"""

from __future__ import annotations

from players.player_sdk import EmptyModeParams, Mode

from crewborg.modes.normal import NormalMode
from crewborg.types import ActionState, Belief, Intent

# Consecutive report ticks without a meeting opening before we give up on a body and
# resume tasking (``action_state.report_ticks``; see action.py). Long enough that the
# common navigate-then-press succeeds untouched, short enough we never freeze to death.
REPORT_TIMEOUT_TICKS = 120


class ReportBodyMode(Mode[Belief, ActionState, Intent]):
    name = "report_body"
    params_type = EmptyModeParams

    def __init__(self, params: EmptyModeParams | None = None) -> None:
        super().__init__(params)
        self._target: int | None = None
        self._abandoned: int | None = None  # body given up on this activation
        self._fallback = NormalMode()  # resume-tasking behaviour on timeout

    def decide(self, belief: Belief, action_state: ActionState) -> Intent:
        candidates = [bid for bid in belief.visible_body_ids if bid in belief.bodies]
        if not candidates:
            return Intent(kind="idle", reason="no body in view")
        if belief.self_world_x is None or belief.self_world_y is None:
            target = min(candidates)
        else:
            self_xy = (belief.self_world_x, belief.self_world_y)
            target = min(candidates, key=lambda b: _dist2(self_xy, _body_xy(belief, b)))
        if target != self._target:
            self._target = target
            self._abandoned = None  # a different body ⇒ a fresh report attempt
        # Give up on a body we cannot get in range for and task instead of freezing;
        # the give-up is sticky so we don't oscillate report/task every tick.
        if self._abandoned == target or action_state.report_ticks >= REPORT_TIMEOUT_TICKS:
            self._abandoned = target
            return self._fallback.decide(belief, action_state)
        return Intent(kind="report", target_id=target, reason="reporting visible body")


def _body_xy(belief: Belief, body_id: int) -> tuple[int, int]:
    body = belief.bodies[body_id]
    return body.world_x, body.world_y


def _dist2(a: tuple[int, int], b: tuple[int, int]) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
