"""Runtime adapter from perception/belief into the append-only deduction stream."""

from __future__ import annotations

from typing import TYPE_CHECKING

from crewborg.deduction.model import (
    DeathObserved,
    DeductionEvent,
    DeductionHistory,
    GameSpec,
    MeetingObserved,
    ObservedBody,
    ObservedPlayer,
    ObservedVent,
    TaskCounterObserved,
    UtteranceObserved,
    VoteObserved,
    WorldObserved,
)
from crewborg.perception.entities import SKIP_VOTE_TARGET
from crewborg.strategy.occupancy import (
    players_in_rect,
    rect_visible,
)

if TYPE_CHECKING:
    from crewborg.types import Belief, Percept


def update_deduction_history(belief: "Belief", percept: "Percept") -> None:
    """Append every newly observed solver-relevant fact exactly once."""

    resolved = percept.resolved
    if (
        belief.phase == "Playing"
        and resolved.camera_ready
        and resolved.self_world_x is not None
        and resolved.self_world_y is not None
    ):
        current_frame = (
            belief.recent_frames[-1]
            if belief.recent_frames and belief.recent_frames[-1].tick == percept.tick
            else None
        )
        _append(
            belief,
            WorldObserved(
                event_id=f"world:{percept.tick}",
                tick=percept.tick,
                self_xy=(resolved.self_world_x, resolved.self_world_y),
                players=tuple(
                    ObservedPlayer(color=p.color, x=p.world_x, y=p.world_y)
                    for p in sorted(
                        resolved.visible_players, key=lambda item: item.color
                    )
                ),
                bodies=tuple(
                    ObservedBody(color=b.color, x=b.world_x, y=b.world_y)
                    for b in sorted(
                        resolved.visible_bodies, key=lambda item: item.color
                    )
                ),
                visible_vents=tuple(
                    ObservedVent(
                        index=index,
                        occupants=tuple(
                            sorted(
                                players_in_rect(
                                    current_frame,
                                    vent.x,
                                    vent.y,
                                    vent.w,
                                    vent.h,
                                    margin=3,
                                )
                            )
                        ),
                    )
                    for index, vent in enumerate(
                        belief.map.vents if belief.map is not None else ()
                    )
                    if current_frame is not None
                    and rect_visible(
                        current_frame,
                        vent.x,
                        vent.y,
                        vent.w,
                        vent.h,
                        margin=3,
                    )
                ),
            ),
        )

    if resolved.crew_tasks_remaining is not None:
        previous = next(
            (
                event.remaining
                for event in reversed(belief.deduction_events)
                if isinstance(event, TaskCounterObserved)
            ),
            None,
        )
        if previous != resolved.crew_tasks_remaining:
            _append(
                belief,
                TaskCounterObserved(
                    event_id=f"task_counter:{percept.tick}:{resolved.crew_tasks_remaining}",
                    tick=percept.tick,
                    remaining=resolved.crew_tasks_remaining,
                ),
            )

    if belief.phase == "Voting":
        meeting_id = belief.phase_start_tick
        _append(
            belief,
            MeetingObserved(
                event_id=f"meeting:{meeting_id}",
                tick=meeting_id,
                meeting_id=meeting_id,
                caller=belief.meeting_caller_color,
                call_kind=_call_kind(belief.meeting_call_kind),
            ),
        )
        for event in belief.chat_log:
            _append(
                belief,
                UtteranceObserved(
                    event_id=(
                        f"utterance:{meeting_id}:{event.tick}:"
                        f"{event.speaker_color}:{event.text}"
                    ),
                    tick=event.tick,
                    meeting_id=meeting_id,
                    speaker=event.speaker_color,
                    text=event.text,
                ),
            )
        slots = {
            candidate.slot: candidate.color for candidate in belief.voting.candidates
        }
        for dot in belief.voting.dots:
            voter = slots.get(dot.voter)
            if voter is None:
                continue
            target = None if dot.target == SKIP_VOTE_TARGET else slots.get(dot.target)
            _append(
                belief,
                VoteObserved(
                    event_id=f"vote:{meeting_id}:{voter}",
                    tick=percept.tick,
                    meeting_id=meeting_id,
                    voter=voter,
                    target=target,
                ),
            )

    for color, record in belief.roster.items():
        if (
            record.life_status != "dead"
            or record.death_seen_tick is None
            or record.death_source is None
        ):
            continue
        _append(
            belief,
            DeathObserved(
                event_id=(
                    f"death:{color}:{record.death_seen_tick}:{record.death_source}"
                ),
                tick=record.death_seen_tick,
                color=color,
                source=record.death_source,
                body_xy=record.body_xy,
            ),
        )


def history_from_belief(belief: "Belief") -> DeductionHistory | None:
    self_color = belief.self_color or belief.voting.self_marker_color
    if (
        self_color is None
        or belief.self_role not in {"crewmate", "imposter"}
        or not belief.roster
    ):
        return None
    players = tuple(sorted(set(belief.roster) | {self_color}))
    count = belief.imposter_count
    if count is None:
        total = max(belief.total_player_count, len(players))
        count = 0 if total < 5 else max(0, min((total - 3) // 2, total - 1))
    return DeductionHistory(
        game=GameSpec(
            players=players,
            self_color=self_color,
            self_role=belief.self_role,
            imposter_count=count,
            known_imposters=tuple(
                sorted(
                    belief.teammate_colors | {self_color}
                    if belief.self_role == "imposter"
                    else ()
                )
            ),
        ),
        events=tuple(belief.deduction_events),
    )


def _append(belief: "Belief", event: DeductionEvent) -> None:
    if isinstance(event, WorldObserved):
        if event.tick in belief.deduction_world_ticks:
            return
        belief.deduction_world_ticks.add(event.tick)
        belief.deduction_events.append(event)
        return
    if event.event_id in belief.deduction_event_ids:
        return
    belief.deduction_event_ids.add(event.event_id)
    belief.deduction_events.append(event)


def _call_kind(value: str | None) -> str | None:
    return value if value in {"body", "button", "unknown"} else None
