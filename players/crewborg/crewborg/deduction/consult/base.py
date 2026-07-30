"""What a consult is, and the three knobs an experiment is allowed to turn.

A *consult* is one hypothesis about what an LLM is FOR at the end of the deduction
branch. `shortlist` says it is for breaking near-ties the posterior has already isolated.
The next one might say it is for reading the transcript for claims the parser dropped, or
for deciding whether to vote at all. Those are different questions and they should be
different consults -- not one prompt file that slowly accretes every idea we have had.

An experiment declares exactly three things:

    payload(view)  -> dict        WHAT DATA the model sees. A subset/reshaping of the
                                  `ConsultView`; never a new source of truth.
    Response       -> BaseModel   WHAT SHAPE the answer must take. Pydantic, and its JSON
                                  Schema is sent to the model, so "constrain the output"
                                  is one class definition rather than prose in a prompt.
    apply(r, view) -> Outcome     HOW WE PROCESS IT. Thresholds, veto rules, whether a
                                  low-confidence answer falls back to the solver.

Everything else -- transport, timeout, schema injection, validation, tracing, the
fallback-on-any-failure contract -- is `runner.py` and is shared. That split is the point:
iterating on the idea means editing one small module plus a markdown file, and never
touching `attend_meeting.py`.

The system prompt lives on disk (`memory/<name>.md`) for the same reason the meeting
prompts do: prompt language is the fastest-moving part of the experiment and should not
require a code change or a rebuild to edit.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel

from crewborg.deduction.consult.view import SKIP, ConsultView

PROMPT_DIR_ENV = "CREWBORG_CONSULT_PROMPT_DIR"


@dataclass(frozen=True)
class ConsultOutcome:
    """What the consult decided, plus whatever it wants on the record.

    `vote` is always a legal target or `skip` -- the runner enforces that before this is
    returned, so callers never have to re-validate. `fields` is free-form and lands in the
    trace: put the experiment's own quantities here (confidence, which rule fired, how far
    it moved from the solver) so a new consult is measurable without new trace code.
    """

    vote: str
    chat: str | None = None
    followed_llm: bool = False
    fields: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class Consult(Protocol):
    """One LLM experiment inside the deduction branch."""

    name: str
    Response: type[BaseModel]

    def payload(self, view: ConsultView) -> dict[str, Any]:
        """The data half of the prompt. Must be JSON-serialisable."""

    def apply(self, response: BaseModel, view: ConsultView) -> ConsultOutcome:
        """Turn a validated response into a vote. Must not raise on hostile input."""


class BaseConsult:
    """Shared plumbing: parameter parsing and prompt loading.

    Subclasses set `name`, `Response`, `defaults`, and implement `payload`/`apply`.
    """

    name: str = "base"
    Response: type[BaseModel]
    #: Tunables the env string may override, e.g. `CREWBORG_DEDUCTION_LLM=shortlist:k=4`.
    #: Keeping thresholds here rather than as literals means a sweep is a `--secret-env`
    #: change and ships the same image, which is how every other lever in this codebase
    #: is A/B'd (see `deduction/config.py` presets).
    defaults: ClassVar[Mapping[str, Any]] = {}

    def __init__(self, params: Mapping[str, Any] | None = None) -> None:
        merged = dict(self.defaults)
        for key, raw in (params or {}).items():
            if key in merged:
                merged[key] = _coerce(raw, merged[key])
        self.params = merged

    def param(self, key: str) -> Any:
        return self.params.get(key)

    def system_prompt(self, prompt_dir: str | None = None) -> str:
        return _load_prompt(self.name, prompt_dir)

    # Subclasses override.
    def payload(self, view: ConsultView) -> dict[str, Any]:  # pragma: no cover - abstract
        raise NotImplementedError

    def apply(self, response: BaseModel, view: ConsultView) -> ConsultOutcome:  # pragma: no cover
        raise NotImplementedError

    def fallback(self, view: ConsultView, reason: str) -> ConsultOutcome:
        """The outcome when the model is unavailable, slow, or unusable.

        Always the deterministic vote: a consult may only ever ADD judgment, never
        subtract availability. The runner calls this on every failure path.
        """

        return ConsultOutcome(
            vote=view.deterministic_vote,
            chat=None,
            followed_llm=False,
            fields={"fallback": reason},
        )


def response_schema(model: type[BaseModel]) -> dict[str, Any]:
    """The JSON Schema to send, with our own notes stripped out.

    Pydantic promotes a model's CLASS DOCSTRING into the schema's top-level
    `description`. Those docstrings are written for whoever maintains the consult -- the
    first version of `ShortlistResponse` explained which earlier pilot had failed and
    how -- and shipping them means telling the model how its predecessor went wrong,
    inside the instruction to answer. FIELD descriptions are kept: those are written for
    the model and are the right place to say what a field means.
    """

    schema = model.model_json_schema()
    schema.pop("description", None)
    schema.pop("title", None)
    return schema


def _coerce(raw: Any, template: Any) -> Any:
    """Parse an env-string parameter into the type of its default."""

    if isinstance(template, bool):
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}
    for caster in (int, float) if isinstance(template, (int, float)) else ():
        if isinstance(template, int) and caster is float:
            continue
        try:
            return caster(raw)
        except (TypeError, ValueError):
            return template
    return raw


@lru_cache(maxsize=32)
def _load_prompt(name: str, prompt_dir: str | None) -> str:
    root = Path(prompt_dir) if prompt_dir else Path(__file__).with_name("memory")
    try:
        text = (root / f"{name}.md").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return text


__all__ = [
    "PROMPT_DIR_ENV",
    "SKIP",
    "BaseConsult",
    "Consult",
    "ConsultOutcome",
    "ConsultView",
    "response_schema",
]
