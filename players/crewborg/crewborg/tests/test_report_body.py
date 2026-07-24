"""Report Body robustness tests: margin, reposition, and stuck-timeout fallback.

Regression cover for the Prime replay where a ~7px body-localization error left the
policy pressing report at the 20px range boundary (server-rejected) for ~545 ticks
until an imposter killed it. The fix (design §12): press only well inside range,
escalate to point-blank on repeated failure, and time out to tasking rather than
freeze. See ``crewborg.action._resolve_report`` and ``ReportBodyMode``.
"""

from __future__ import annotations

from crewborg.action import (
    BTN_A,
    BTN_UP,
    REPORT_REPOSITION_TICKS,
    resolve_action,
)
from crewborg.map.types import MapData, MapPoint, MapRect
from crewborg.modes.report_body import REPORT_TIMEOUT_TICKS, ReportBodyMode
from crewborg.types import ActionState, Belief, BodyEntry, Intent


def _belief_with_body(self_xy: tuple[int, int], body_xy: tuple[int, int], *, map_data=None) -> Belief:
    belief = Belief(self_world_x=self_xy[0], self_world_y=self_xy[1], visible_body_ids={2003}, map=map_data)
    belief.bodies[2003] = BodyEntry(
        object_id=2003, color="green", world_x=body_xy[0], world_y=body_xy[1], first_seen_tick=1
    )
    return belief


def _empty_map() -> MapData:
    # No tasks: normal tasking falls through to "return to start", i.e. movement.
    return MapData(
        width=400, height=400, tasks=(), vents=(), rooms=(),
        button=MapRect(x=0, y=0, w=4, h=4), home=MapPoint(x=10, y=10),
    )


# (a) Keeps approaching until inside the margin instead of pressing from the boundary.
def test_report_approaches_when_inside_range_but_outside_margin() -> None:
    # 15px away: inside the 20px ReportRange (old code pressed here) but outside the
    # 12px press margin — so we must still navigate closer, not press from the lip.
    belief = _belief_with_body((100, 115), (100, 100))
    command = resolve_action(Intent(kind="report", target_id=2003), belief, ActionState())
    assert command.held_mask == BTN_UP  # driving toward the body, not pressing


def test_report_presses_once_comfortably_inside_margin() -> None:
    # 8px away: well inside the margin ⇒ the common fast-report path is untouched.
    belief = _belief_with_body((100, 108), (100, 100))
    command = resolve_action(Intent(kind="report", target_id=2003), belief, ActionState())
    assert command.held_mask == BTN_A  # fresh press


# (b) After the stuck threshold it repositions (drives point-blank onto the body).
def test_report_repositions_after_repeated_failed_presses() -> None:
    # 10px away: inside the margin, so we press — but suppose the server keeps rejecting
    # (true range boundary). After REPORT_REPOSITION_TICKS the margin tightens to
    # point-blank and we drive the last pixels onto the body instead of holding still.
    belief = _belief_with_body((100, 110), (100, 100))
    action_state = ActionState()
    intent = Intent(kind="report", target_id=2003)

    for _ in range(REPORT_REPOSITION_TICKS):
        assert resolve_action(intent, belief, action_state).held_mask in (BTN_A, 0)  # still pressing
    # The next tick crosses the threshold: escalate to closing the remaining gap.
    assert resolve_action(intent, belief, action_state).held_mask == BTN_UP


# (c) After the timeout it falls back to normal tasking (never freezes to death).
def test_report_body_times_out_to_tasking() -> None:
    belief = _belief_with_body((100, 110), (100, 100), map_data=_empty_map())
    mode = ReportBodyMode()

    # Before the timeout: ordinary report intent.
    assert mode.decide(belief, ActionState()).kind == "report"

    # At the timeout: give up on the body and resume normal behaviour (movement toward
    # the start room here), rather than pressing report at a spot the server rejects.
    timed_out = mode.decide(belief, ActionState(report_ticks=REPORT_TIMEOUT_TICKS))
    assert timed_out.kind != "report"
    assert timed_out.kind == "navigate_to"


def test_report_body_give_up_is_sticky_no_oscillation() -> None:
    # Once abandoned, the mode keeps tasking even after report_ticks resets (the action
    # layer zeroes it when the intent changes) — so it doesn't flip report/task/report.
    belief = _belief_with_body((100, 110), (100, 100), map_data=_empty_map())
    mode = ReportBodyMode()
    assert mode.decide(belief, ActionState(report_ticks=REPORT_TIMEOUT_TICKS)).kind == "navigate_to"
    assert mode.decide(belief, ActionState(report_ticks=0)).kind == "navigate_to"


def test_report_body_reattempts_a_different_body() -> None:
    # A newly-nearest body is a fresh attempt: abandoning one body doesn't poison others.
    belief = _belief_with_body((100, 110), (100, 100), map_data=_empty_map())
    mode = ReportBodyMode()
    assert mode.decide(belief, ActionState(report_ticks=REPORT_TIMEOUT_TICKS)).kind == "navigate_to"

    belief.bodies[2007] = BodyEntry(object_id=2007, color="red", world_x=100, world_y=112, first_seen_tick=1)
    belief.visible_body_ids.add(2007)  # now the nearest body
    intent = mode.decide(belief, ActionState(report_ticks=0))
    assert intent.kind == "report" and intent.target_id == 2007
