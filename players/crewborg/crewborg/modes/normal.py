"""Normal mode: the default crewmate stance — complete assigned tasks (design §7.1).

Targeting is driven off the **live task-signal set** (``visible_task_indices`` — the
arrows + bubbles, which together mark exactly the incomplete assigned tasks): pick
the nearest **reachable** signalled task, emit ``complete_task(T)`` until it's done,
then move to the next. When **no** task signal remains, every task is done, so head
back to the spawn / start room rather than standing still.

**Completion detection.** The authoritative signal is the **bubble disappearing**
(``T`` leaving the signal set while we are inside its rect). But a bubble can also
blink out for a tick from occlusion (an imposter overlapping us) or a screen-edge —
so we *gate* it on the progress bar: ``T`` is concluded done only if we recently saw
its progress reach ``COMPLETION_PROGRESS_PCT`` (≈ done). A bubble vanishing without
that progress is treated as a flicker — we keep holding the same task. Progress is
only a gate, never the trigger (so we never stop the hold early at, say, 98%); and
because targeting uses the live signals, a falsely-concluded task that is still
signalled is simply re-targeted (self-healing).

Two stall guards (design §5):

- *Reachability* — prefer tasks the nav graph can actually route to, so we don't
  fixate on an unreachable station (the action layer holds still on no path).
- *Arrows-disabled sweep* — when ``showTaskArrows`` is off, off-screen tasks emit
  no signals, so the signal set can be empty at spawn even with tasks to do. Rather
  than head home immediately, sweep the baked stations to discover assigned ones.
"""

from __future__ import annotations

import math
import os

from crewborg.map.types import Room, TaskStation
from crewborg.strategy.commander.bias import commander_of, room_crew_count
from crewborg.types import ActionState, Belief, Intent
from players.player_sdk import EmptyModeParams, Mode

# A bubble leaving the signal set counts as completion only if progress recently
# reached at least this — otherwise it's treated as a flicker/occlusion.
COMPLETION_PROGRESS_PCT = 90
SWEEP_ARRIVE_RADIUS = 24  # within this of a station center ⇒ count it as checked
GROUP_TASK_RADIUS_SQ = 120**2
GROUP_TASK_FIX_TICKS = 48
DEFAULT_GROUP_TASK_MAX_DETOUR = 160
# Post-task loiter-with-group (CREWBORG_POST_TASK_LOITER): a crewmate that has
# finished all its own tasks is worth more holding with the pack than wandering
# home alone -- diagnostics show ~half of subject murders happen after the subject
# finished its tasks, and ~3/4 of murders are isolated (no witness). Two live
# crewmates within this radius count as a cluster; once this close to its anchor,
# hold still to keep line of sight rather than re-approach.
GROUP_LOITER_RADIUS_SQ = 120**2
GROUP_LOITER_HOLD_SQ = 72**2
GROUP_LOITER_FIX_TICKS = 96


class NormalMode(Mode[Belief, ActionState, Intent]):
    name = "normal"
    params_type = EmptyModeParams

    def __init__(self, params=None) -> None:
        super().__init__(params)
        self._target: int | None = None
        self._target_reason = "completing assigned task"
        self._max_progress: int = 0  # peak progress seen for the current target
        self._target_progress_started = False
        self._swept: set[int] = set()

    def decide(self, belief: Belief, action_state: ActionState) -> Intent:
        del action_state
        tasks = belief.map.tasks if belief.map is not None else ()

        self._update_target(belief, tasks)
        if self._target is not None:
            return Intent(
                kind="complete_task",
                task_index=self._target,
                reason=self._target_reason,
            )

        hard_position = _hard_target_room_intent(belief)
        if hard_position is not None:
            return hard_position

        sweep = self._sweep_intent(belief, tasks)
        if sweep is not None:
            return sweep
        loiter = _post_task_loiter(belief)
        if loiter is not None:
            return loiter
        return _return_to_start(belief)

    def _update_target(self, belief: Belief, tasks: tuple[TaskStation, ...]) -> None:
        """Conclude/keep the current target, then pick a new one off the live signals."""

        signals = belief.visible_task_indices
        target = self._target
        if target is not None and target < len(tasks):
            on_station = _inside(tasks[target], belief.self_world_x, belief.self_world_y)
            if on_station and belief.active_task_progress_pct is not None:
                self._target_progress_started = True
                self._max_progress = max(self._max_progress, belief.active_task_progress_pct)
            if target not in signals:
                # Bubble gone: a real completion only if progress reached ~done.
                # Otherwise it's a flicker/occlusion — keep holding the same task.
                if self._max_progress >= COMPLETION_PROGRESS_PCT:
                    belief.completed_task_indices.add(target)
                    self._target = None
                    self._target_progress_started = False
            # if still signalled, keep the current target (avoids thrashing).

        if (
            self._target is not None
            and self._target in signals
            and not self._target_progress_started
            and _truthy_env("CREWBORG_GROUP_TASKING")
        ):
            self._revalidate_group_target(belief, tasks, signals)

        if self._target is None:
            self._target = self._pick_target(belief, tasks, signals)
            self._max_progress = 0
            self._target_progress_started = False

    def _revalidate_group_target(
        self,
        belief: Belief,
        tasks: tuple[TaskStation, ...],
        signals: set[int],
    ) -> None:
        """Refresh a group-biased target while traveling, never during task progress."""

        current_reason = self._target_reason
        proposed = self._pick_target(belief, tasks, signals)
        proposed_reason = self._target_reason
        current_is_grouped = current_reason.startswith("group-aware tasking:")
        proposed_is_grouped = proposed_reason.startswith("group-aware tasking:")
        if current_is_grouped or proposed_is_grouped:
            self._target = proposed
            self._max_progress = 0
            return
        self._target_reason = current_reason

    def _pick_target(self, belief: Belief, tasks: tuple[TaskStation, ...], signals: set[int]) -> int | None:
        # The live signal set is the authoritative list of remaining tasks; a task
        # still signalled is still to do (even if we earlier mis-concluded it done).
        self._target_reason = "completing assigned task"
        candidates = [index for index in signals if index < len(tasks)]
        if not candidates:
            return None

        # Prefer tasks with a baked reachable anchor; fall back to all if none have
        # one (rare — the action layer then holds still rather than wall-drive).
        if belief.nav is not None:
            reachable = [i for i in candidates if belief.nav.task_anchor(i) is not None]
            if reachable:
                candidates = reachable

        cmd = commander_of(belief)
        if cmd is not None:
            if cmd.target_task in candidates:
                return cmd.target_task
            if cmd.target_room is not None:
                target_room_candidates = [i for i in candidates if _task_room(belief, tasks[i]) == cmd.target_room]
                if target_room_candidates:
                    candidates = target_room_candidates
                elif cmd.strength == "hard" and _room_exists(belief, cmd.target_room):
                    return None

        self_xy = _self_xy(belief)
        if self_xy is None:
            return min(candidates)
        if cmd is not None and cmd.posture != "neutral":
            return min(candidates, key=lambda i: _posture_key(belief, tasks[i], cmd.posture, self_xy, i))
        grouped = _group_task_candidate(belief, tasks, candidates, self_xy)
        if grouped is not None:
            self._target_reason = "group-aware tasking: completing supported assigned task"
            return grouped
        return min(candidates, key=lambda i: _dist2(self_xy, _nav_point(belief, tasks[i], i)))

    def _sweep_intent(self, belief: Belief, tasks: tuple[TaskStation, ...]) -> Intent | None:
        """Sweep baked stations to discover assigned tasks (arrows-disabled, §5)."""

        # Only sweep before any task signal has arrived, while the crew still has
        # tasks to do, and once we know where we are.
        if belief.assigned_task_indices or not tasks or belief.crew_tasks_remaining == 0:
            return None
        self_xy = _self_xy(belief)
        if self_xy is None:
            return None

        # Mark stations we have reached as checked.
        for index, task in enumerate(tasks):
            if _dist2(self_xy, _center(task)) <= SWEEP_ARRIVE_RADIUS**2:
                self._swept.add(index)

        remaining = [i for i in range(len(tasks)) if i not in self._swept]
        if not remaining:
            return None  # checked every station and found no assigned tasks
        nearest = min(remaining, key=lambda i: _dist2(self_xy, _nav_point(belief, tasks[i], i)))
        return Intent(kind="navigate_to", point=_nav_point(belief, tasks[nearest], nearest), reason="sweeping for tasks")


def _post_task_loiter(belief: Belief) -> Intent | None:
    """Opt-in: a finished crewmate holds with the pack instead of wandering home.

    Gated by ``CREWBORG_POST_TASK_LOITER`` and reached only when Normal has no task
    left to do. Biases toward the densest cluster of recently-seen live crewmates
    (safety in numbers denies kill windows) and holds still once inside it. Off ⇒
    behaviour is byte-identical to the old return-to-start path.
    """

    if (
        not _truthy_env("CREWBORG_POST_TASK_LOITER")
        or not belief.self_alive
        or belief.self_role != "crewmate"
    ):
        return None
    self_xy = _self_xy(belief)
    if self_xy is None:
        return None
    tick = belief.last_tick
    live = [
        record
        for record in belief.roster.values()
        if record.color != belief.self_color
        and record.life_status == "alive"
        and 0 <= tick - record.last_seen_tick <= GROUP_LOITER_FIX_TICKS
    ]
    if len(live) < 2:
        return None

    def neighbours(record) -> list:
        here = (record.world_x, record.world_y)
        return [
            other
            for other in live
            if other is not record
            and _dist2(here, (other.world_x, other.world_y)) <= GROUP_LOITER_RADIUS_SQ
        ]

    # Densest cluster: keep the winner's neighbour list from the same pass rather
    # than recomputing it for the anchor.
    anchor, anchor_neighbours = max(
        ((record, neighbours(record)) for record in live),
        key=lambda pair: len(pair[1]),
    )
    cluster = [anchor, *anchor_neighbours]
    if len(cluster) < 2:
        return None
    target = (anchor.world_x, anchor.world_y)
    visible_now = sum(record.last_seen_tick == tick for record in cluster)
    if _dist2(self_xy, target) <= GROUP_LOITER_HOLD_SQ and visible_now >= 2:
        return Intent(kind="loiter", reason="post-task loiter: holding with the group")
    return Intent(kind="navigate_to", point=target, reason="post-task loiter: regrouping with crew")


def _return_to_start(belief: Belief) -> Intent:
    """All assigned tasks done — head back to the spawn / start room instead of
    standing still (which strands a finished crewmate and earns stuck penalties)."""

    if belief.map is None:
        return Intent(kind="idle", reason="no incomplete tasks remain")
    goal = (belief.map.home.x, belief.map.home.y)
    if belief.nav is not None:
        cell = belief.nav.nearest_reachable_node(*goal)
        if cell is not None:
            goal = belief.nav.node_point[cell]
    return Intent(kind="navigate_to", point=goal, reason="tasks done: returning to the start room")


def _hard_target_room_intent(belief: Belief) -> Intent | None:
    cmd = commander_of(belief)
    if cmd is None or cmd.strength != "hard" or cmd.target_room is None or belief.map is None:
        return None
    room = _room_exists(belief, cmd.target_room)
    if room is None:
        return None
    goal = (room.center.x, room.center.y)
    if belief.nav is not None:
        cell = belief.nav.nearest_reachable_node(*goal)
        if cell is not None:
            goal = belief.nav.node_point[cell]
    return Intent(kind="navigate_to", point=goal, reason=f"commander: positioning in {room.name}")


def _room_exists(belief: Belief, name: str) -> Room | None:
    if belief.map is None:
        return None
    return next((room for room in belief.map.rooms if room.name == name), None)


def _inside(task: TaskStation, x: int | None, y: int | None) -> bool:
    if x is None or y is None:
        return False
    return task.x <= x < task.x + task.w and task.y <= y < task.y + task.h


def _center(task: TaskStation) -> tuple[int, int]:
    return task.center.x, task.center.y


def _nav_point(belief: Belief, task: TaskStation, index: int) -> tuple[int, int]:
    """The station's baked reachable anchor, or its center before the graph exists."""

    if belief.nav is not None:
        anchor = belief.nav.task_anchor(index)
        if anchor is not None:
            return anchor
    return task.center.x, task.center.y


def _task_room(belief: Belief, task: TaskStation) -> str | None:
    if belief.map is None:
        return None
    x, y = task.center.x, task.center.y
    room = next((room for room in belief.map.rooms if room.x <= x < room.x + room.w and room.y <= y < room.y + room.h), None)
    return room.name if room is not None else None


def _posture_key(
    belief: Belief,
    task: TaskStation,
    posture: str,
    self_xy: tuple[int, int],
    index: int,
) -> tuple[int, int]:
    room = _task_room(belief, task)
    crew_count = room_crew_count(belief, room) if room is not None else 0
    posture_score = -crew_count if posture == "stick" else crew_count
    return posture_score, _dist2(self_xy, _nav_point(belief, task, index))


def _self_xy(belief: Belief) -> tuple[int, int] | None:
    if belief.self_world_x is None or belief.self_world_y is None:
        return None
    return belief.self_world_x, belief.self_world_y


def _dist2(a: tuple[int, int], b: tuple[int, int]) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _group_task_candidate(
    belief: Belief,
    tasks: tuple[TaskStation, ...],
    candidates: list[int],
    self_xy: tuple[int, int],
) -> int | None:
    if not _truthy_env("CREWBORG_GROUP_TASKING"):
        return None
    nearest = min(
        candidates,
        key=lambda index: _dist2(self_xy, _nav_point(belief, tasks[index], index)),
    )
    nearest_distance = math.isqrt(
        _dist2(self_xy, _nav_point(belief, tasks[nearest], nearest))
    )
    max_distance = nearest_distance + _group_task_max_detour()
    supported = []
    for index in candidates:
        point = _nav_point(belief, tasks[index], index)
        distance = math.isqrt(_dist2(self_xy, point))
        supporters = [
            record
            for record in belief.roster.values()
            if record.color != belief.self_color
            and record.life_status == "alive"
            and 0 <= belief.last_tick - record.last_seen_tick <= GROUP_TASK_FIX_TICKS
            and _dist2(point, (record.world_x, record.world_y))
            <= GROUP_TASK_RADIUS_SQ
        ]
        support = max(
            (
                sum(
                    _dist2(
                        (anchor.world_x, anchor.world_y),
                        (other.world_x, other.world_y),
                    )
                    <= GROUP_TASK_RADIUS_SQ
                    for other in supporters
                )
                for anchor in supporters
            ),
            default=0,
        )
        if support >= 2 and distance <= max_distance:
            supported.append((index, support, distance))
    if not supported:
        return None
    return min(supported, key=lambda item: (-item[1], item[2], item[0]))[0]


def _group_task_max_detour() -> int:
    raw = os.environ.get("CREWBORG_GROUP_TASK_MAX_DETOUR", "").strip()
    try:
        value = int(raw) if raw else DEFAULT_GROUP_TASK_MAX_DETOUR
    except ValueError:
        return DEFAULT_GROUP_TASK_MAX_DETOUR
    return max(0, value)


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}
