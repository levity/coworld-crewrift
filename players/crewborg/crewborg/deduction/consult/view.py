"""The neutral evidence bundle every consult reads from.

WHY THIS TYPE EXISTS AT ALL. The expensive part of an LLM experiment is not writing the
prompt -- it is discovering, a night of league play later, that the prompt was scored on
different evidence than the agent will actually hold. So no consult is allowed to touch
`Belief` or `deduction.decision.MeetingDecision` directly. Every consult reads a
`ConsultView`, and a `ConsultView` can be built two ways:

    * `from_deduction(...)` -- in the agent, from the live belief and the solver's result.
    * `from_row(...)`       -- offline, from one row of the telemetry-derived meeting
                               bundle (`crewrift-analysis/deduction_llm_offline.py`).

Both produce the same fields, so a consult scored offline is running on exactly what it
will see in a pod. That is the whole reason this is a dataclass of primitives and not a
convenience wrapper: it has to round-trip through JSON without losing anything a prompt
might depend on.

It is also deliberately WIDER than any one experiment needs. `shortlist` looks at three
candidates and the transcript; a future consult may want the joint hypotheses, the pins,
or the solver's stated reason. Adding a field here is cheap and breaks nothing; changing
a consult's payload to reach past the view is what we are preventing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

SKIP = "skip"


@dataclass(frozen=True)
class Candidate:
    """One live player as the posterior sees them."""

    color: str
    p: float
    pinned: bool = False
    murder_cleared: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "color": self.color,
            "p": round(self.p, 4),
            "pinned": self.pinned,
            "cleared_by_murder": self.murder_cleared,
        }


@dataclass(frozen=True)
class Utterance:
    tick: int
    speaker: str
    text: str

    def to_json(self) -> dict[str, Any]:
        return {"tick": self.tick, "speaker": self.speaker, "text": self.text}


@dataclass(frozen=True)
class GameEvent:
    """One significant thing that happened, in game order.

    The five kinds mirror `deduction.model`'s observation types, minus `world` (a
    per-frame position dump, far too voluminous and low-level to narrate). A consult
    that wants positions should ask for them explicitly rather than have every prompt
    carry 1200 ticks of coordinates.
    """

    tick: int
    kind: str  # meeting | utterance | vote | death | task_progress
    actor: str | None = None  # speaker, voter, caller, or the deceased
    target: str | None = None  # a vote's target ("skip" when abstaining)
    text: str | None = None
    meeting_id: int | None = None
    detail: str | None = None  # call kind, death source, tasks remaining

    def to_json(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass(frozen=True)
class ConsultView:
    """Everything a consult may look at, in one JSON-round-trippable object."""

    self_color: str | None
    candidates: tuple[Candidate, ...]
    joint_hypotheses: tuple[tuple[tuple[str, ...], float], ...]
    deterministic: Mapping[str, Any]
    timeline: tuple[GameEvent, ...]
    legal_targets: tuple[str, ...]
    roster: tuple[str, ...] = ()
    imposter_count: int = 2
    self_role: str = "crewmate"
    meeting_id: int | None = None
    tick: int | None = None

    @property
    def transcript(self) -> tuple[Utterance, ...]:
        return tuple(
            Utterance(e.tick, e.actor or "?", e.text or "")
            for e in self.timeline
            if e.kind == "utterance"
        )

    # --- what the deterministic half concluded ----------------------------------

    @property
    def deterministic_vote(self) -> str:
        target = self.deterministic.get("target")
        if self.deterministic.get("action") == "eject" and target:
            return str(target)
        return SKIP

    @property
    def ranked(self) -> tuple[Candidate, ...]:
        return tuple(sorted(self.candidates, key=lambda c: c.p, reverse=True))

    def top(self, k: int) -> tuple[Candidate, ...]:
        return self.ranked[: max(1, k)]

    def is_legal(self, target: str | None) -> bool:
        return bool(target) and (target == SKIP or target in self.legal_targets)

    def game_log(self) -> list[str]:
        """The timeline as a compact chronological narrative, one line per beat.

        Prose rather than JSON on purpose. A model reads "MEETING 2 ENDED -- nobody
        ejected (4 skip / 2 red)" more reliably than the same fact spread across a vote
        array and a death record, and it costs a third of the tokens. Votes are folded
        into one line per meeting and the outcome is stated explicitly, because "what
        happened at the end of the meeting" is exactly the beat that a raw event stream
        leaves the reader to infer.

        Everything here is PUBLIC information -- meetings, what was said in them, the
        vote tally, who was ejected, and who is known dead. Private observations (which
        bodies we personally walked past, who we saw where) are the solver's business and
        are already summarised in the posterior.
        """

        lines: list[str] = []
        if self.roster:
            lines.append(
                f"t=0     GAME START. {len(self.roster)} players: {', '.join(self.roster)}. "
                f"{self.imposter_count} of them are impostors."
            )
            if self.self_color:
                lines.append(f"        You are {self.self_color} ({self.self_role}).")

        pending_votes: dict[int, list[str]] = {}
        open_meeting: int | None = None

        def flush(meeting: int | None, ejected: str | None, tick: int) -> None:
            if meeting is None:
                return
            votes = pending_votes.pop(meeting, [])
            if votes:
                lines.append(f"t={tick:<5} meeting {meeting} VOTES  " + " | ".join(votes))
            outcome = f"{ejected} was ejected" if ejected else "nobody was ejected"
            lines.append(f"t={tick:<5} MEETING {meeting} ENDED -- {outcome}")

        for event in self.timeline:
            if event.kind == "meeting":
                flush(open_meeting, None, event.tick)
                how = {"body": "a body was reported", "button": "emergency button, no body"}.get(
                    event.detail or "", "unknown trigger"
                )
                open_meeting = event.meeting_id
                caller = event.actor or "someone"
                lines.append(f"t={event.tick:<5} MEETING {open_meeting} called by {caller} ({how})")
            elif event.kind == "utterance":
                who = event.actor or "?"
                lines.append(f"t={event.tick:<5}   {who}: \"{event.text}\"")
            elif event.kind == "vote":
                pending_votes.setdefault(event.meeting_id or 0, []).append(
                    f"{event.actor}->{event.target or SKIP}"
                )
            elif event.kind == "death":
                if event.detail == "ejection":
                    flush(open_meeting, event.actor, event.tick)
                    open_meeting = None
                elif event.detail == "body":
                    lines.append(f"t={event.tick:<5} BODY FOUND: {event.actor} is dead")
                else:
                    lines.append(f"t={event.tick:<5} NOTED DEAD: {event.actor} (missing at roll call)")
            elif event.kind == "task_progress":
                lines.append(f"t={event.tick:<5} crew tasks remaining: {event.detail}")

        # The last meeting in the timeline is the one we are IN. It has not ended and must
        # not be narrated as though it had -- writing "MEETING 3 ENDED -- nobody was
        # ejected" immediately above "this is the vote you are advising" tells the model
        # the decision it is being asked for has already been taken.
        now = self.tick or 0
        for voter in pending_votes.pop(open_meeting, []) if open_meeting is not None else []:
            lines.append(f"t={now:<5} meeting {open_meeting} votes so far: {voter}")
        lines.append(
            f"t={now:<5} >>> MEETING {open_meeting or '?'} IS IN PROGRESS RIGHT NOW. "
            "This is the vote you are advising. <<<"
        )
        return lines

    def to_json(self) -> dict[str, Any]:
        return {
            "self_color": self.self_color,
            "meeting_id": self.meeting_id,
            "tick": self.tick,
            "candidates": [c.to_json() for c in self.ranked],
            "joint_hypotheses": [
                {"imposters": list(pair), "p": round(p, 4)}
                for pair, p in self.joint_hypotheses
            ],
            "deterministic_decision": dict(self.deterministic),
            "legal_targets": list(self.legal_targets),
            "transcript": [u.to_json() for u in self.transcript],
        }

    # --- construction -----------------------------------------------------------

    @classmethod
    def from_deduction(
        cls,
        decision: Any,
        *,
        history: Any,
        legal_targets: Sequence[str],
        meeting_id: int | None = None,
        tick: int | None = None,
        max_hypotheses: int = 5,
        max_events: int = 400,
    ) -> ConsultView:
        """Build from a live `MeetingDecision` plus the `DeductionHistory` behind it.

        The history is the right source for the timeline rather than `belief.chat_log`:
        chat_log holds only the CURRENT meeting's utterances, while the history spans the
        whole episode and carries the meetings, votes and deaths that give those
        utterances their meaning. It is also already role-filtered to what this agent
        legitimately observed.
        """

        inference = getattr(decision, "inference", None)
        marginals = tuple(getattr(inference, "marginals", ()) or ())
        pins = set(getattr(inference, "pins", ()) or ())
        clears = set(getattr(inference, "murder_clears", ()) or ())
        hypotheses = tuple(getattr(inference, "hypotheses", ()) or ())[:max_hypotheses]
        game = getattr(history, "game", None)
        return cls(
            self_color=getattr(game, "self_color", None),
            candidates=tuple(
                Candidate(color, float(p), color in pins, color in clears)
                for color, p in marginals
            ),
            joint_hypotheses=tuple(
                (tuple(item.imposters), float(item.probability)) for item in hypotheses
            ),
            deterministic=_deterministic_fields(decision),
            timeline=_timeline_from_history(history, max_events=max_events),
            legal_targets=tuple(sorted(legal_targets)),
            roster=tuple(getattr(game, "players", ()) or ()),
            imposter_count=int(getattr(game, "imposter_count", 2) or 2),
            self_role=str(getattr(game, "self_role", "crewmate") or "crewmate"),
            meeting_id=meeting_id,
            tick=tick,
        )

    @classmethod
    def from_row(cls, row: Mapping[str, Any], *, self_color: str | None = None) -> ConsultView:
        """Build from one offline meeting row, so scoring runs the shipped payload.

        The row shape is what `deduction_llm_offline.py` writes: `marginals` as a
        colour->p mapping, `pins`, `murder_clears`, `hypotheses`, the solver's
        action/target/probability/required_probability/reason, and a `transcript`.
        """

        marginals = dict(row.get("marginals") or {})
        pins = set(row.get("pins") or ())
        clears = set(row.get("murder_clears") or ())
        hypotheses = []
        for item in row.get("hypotheses") or ():
            if isinstance(item, Mapping):
                pair = tuple(item.get("imposters") or ())
                hypotheses.append((pair, float(item.get("p") or 0.0)))
        self_color = self_color or row.get("self_color")
        live = tuple(sorted(c for c, p in marginals.items() if p > 0 and c != self_color))
        return cls(
            self_color=self_color,
            candidates=tuple(
                Candidate(color, float(p), color in pins, color in clears)
                for color, p in marginals.items()
            ),
            joint_hypotheses=tuple(hypotheses),
            deterministic={
                "action": row.get("action"),
                "target": row.get("target"),
                "probability": row.get("probability"),
                "required_probability": row.get("required_probability"),
                "reason": row.get("reason"),
            },
            timeline=tuple(
                GameEvent(
                    tick=int(e.get("tick") or 0),
                    kind=str(e.get("kind") or "utterance"),
                    actor=e.get("actor"),
                    target=e.get("target"),
                    text=e.get("text"),
                    meeting_id=e.get("meeting_id"),
                    detail=e.get("detail"),
                )
                for e in row.get("timeline") or ()
            ),
            legal_targets=live,
            roster=tuple(row.get("roster") or ()),
            imposter_count=int(row.get("imposter_count") or 2),
            meeting_id=row.get("meeting_id"),
            tick=row.get("tick"),
        )


def _timeline_from_history(history: Any, *, max_events: int) -> tuple[GameEvent, ...]:
    """Project a `DeductionHistory` onto the public narrative.

    `world` events are dropped: they are per-frame position dumps, thousands per episode,
    and the posterior already encodes what they imply. What survives is the beats a
    player would remember -- meetings and why they were called, who said what, how
    everyone voted, and who died.
    """

    out: list[GameEvent] = []
    for event in getattr(history, "events", ()) or ():
        kind = getattr(event, "kind", None)
        tick = int(getattr(event, "tick", 0) or 0)
        if kind == "meeting":
            out.append(GameEvent(tick, "meeting", actor=getattr(event, "caller", None),
                                 meeting_id=getattr(event, "meeting_id", None),
                                 detail=getattr(event, "call_kind", None)))
        elif kind == "utterance":
            out.append(GameEvent(tick, "utterance", actor=getattr(event, "speaker", None),
                                 text=getattr(event, "text", None),
                                 meeting_id=getattr(event, "meeting_id", None)))
        elif kind == "vote":
            out.append(GameEvent(tick, "vote", actor=getattr(event, "voter", None),
                                 target=getattr(event, "target", None) or SKIP,
                                 meeting_id=getattr(event, "meeting_id", None)))
        elif kind == "death":
            out.append(GameEvent(tick, "death", actor=getattr(event, "color", None),
                                 detail=getattr(event, "source", None)))
        elif kind == "task_counter":
            out.append(GameEvent(tick, "task_progress",
                                 detail=str(getattr(event, "remaining", ""))))
    return tuple(out[-max_events:])


def _deterministic_fields(decision: Any) -> dict[str, Any]:
    return {
        "action": getattr(decision, "action", None),
        "target": getattr(decision, "target", None),
        "probability": _round(getattr(decision, "probability", None)),
        "required_probability": _round(getattr(decision, "required_probability", None)),
        "margin": _round(getattr(decision, "margin", None)),
        "structural": getattr(decision, "structural", None),
        "sources": list(getattr(decision, "sources", ()) or ()),
        "reason": getattr(decision, "reason", None),
    }


def _round(value: Any) -> float | None:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None
