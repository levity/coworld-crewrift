"""Immutable inputs for deduction.

The event stream records observations, not conclusions. Runtime code may cache
derived results, but inference always accepts a frozen ``DeductionHistory`` and
can therefore be rerun after parser, likelihood, or decision-policy changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class GameSpec(BaseModel):
    """Static facts and rules known to one player."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    players: tuple[str, ...]
    self_color: str
    self_role: Literal["crewmate", "imposter"]
    imposter_count: int
    known_imposters: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ObservedPlayer:
    color: str
    x: int
    y: int


@dataclass(frozen=True, slots=True)
class ObservedBody:
    color: str
    x: int
    y: int


@dataclass(frozen=True, slots=True)
class ObservedVent:
    """A fully visible vent region and the players rendered inside it."""

    index: int
    occupants: tuple[str, ...] = ()


class WorldObserved(BaseModel):
    """One semantic camera observation during live play."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["world"] = "world"
    event_id: str
    tick: int
    self_xy: tuple[int, int]
    players: tuple[ObservedPlayer, ...] = ()
    bodies: tuple[ObservedBody, ...] = ()
    visible_vents: tuple[ObservedVent, ...] = ()


class UtteranceObserved(BaseModel):
    """Exact public text, retained so future parsers can reinterpret it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["utterance"] = "utterance"
    event_id: str
    tick: int
    meeting_id: int
    speaker: str | None
    text: str


class VoteObserved(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["vote"] = "vote"
    event_id: str
    tick: int
    meeting_id: int
    voter: str
    target: str | None


class MeetingObserved(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["meeting"] = "meeting"
    event_id: str
    tick: int
    meeting_id: int
    caller: str | None = None
    call_kind: Literal["body", "button", "unknown"] | None = None


class DeathObserved(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["death"] = "death"
    event_id: str
    tick: int
    color: str
    source: Literal["body", "census", "ejection"]
    body_xy: tuple[int, int] | None = None


class TaskCounterObserved(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["task_counter"] = "task_counter"
    event_id: str
    tick: int
    remaining: int


DeductionEvent = Annotated[
    WorldObserved
    | UtteranceObserved
    | VoteObserved
    | MeetingObserved
    | DeathObserved
    | TaskCounterObserved,
    Field(discriminator="kind"),
]


class DeductionHistory(BaseModel):
    """Frozen, complete input to every deduction function."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    game: GameSpec
    events: tuple[DeductionEvent, ...] = ()

    def through(self, tick: int) -> "DeductionHistory":
        return self.model_copy(
            update={
                "events": tuple(event for event in self.events if event.tick <= tick)
            }
        )
