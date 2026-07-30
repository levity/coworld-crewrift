"""The one call path every consult shares. Nothing here is experiment-specific.

The contract this enforces, so no consult has to restate it:

  * A consult NEVER costs availability. Client disabled, no time on the clock, timeout,
    malformed JSON, schema violation, a bug inside `apply` -- every one of them returns
    `consult.fallback(view, reason)`, which is the deterministic vote. Nothing raises out
    of `run_consult`.
  * Every run emits exactly one `deduction_consult` trace, with the same fields regardless
    of which experiment ran: which consult, whether it was consulted at all and why not,
    the model's raw answer, the outcome, and the departure from the solver. That is what
    makes a new consult measurable the day it is written instead of after someone
    remembers to add tracing for it.
  * The consult decides WHETHER to ask (`applies`), so a well-targeted experiment costs
    nothing on boards it has no opinion about.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from time import perf_counter
from typing import Any

from crewborg.deduction.consult.base import PROMPT_DIR_ENV, BaseConsult, ConsultOutcome
from crewborg.deduction.consult.view import ConsultView

TRACE_EVENT = "deduction_consult"

Emit = Callable[[str, dict], None]


def run_consult(
    consult: BaseConsult,
    view: ConsultView,
    *,
    client: Any,
    emit: Emit | None = None,
    prompt_dir: str | None = None,
    env: Mapping[str, str] | None = None,
    can_start: Callable[[], bool] | None = None,
) -> ConsultOutcome:
    """Run one consult and return an outcome. Never raises."""

    env = os.environ if env is None else env
    prompt_dir = prompt_dir or env.get(PROMPT_DIR_ENV) or None
    trace: dict[str, Any] = {"consult": consult.name, "params": dict(consult.params)}

    def done(outcome: ConsultOutcome, **extra: Any) -> ConsultOutcome:
        trace.update(extra)
        trace["vote"] = outcome.vote
        trace["followed_llm"] = outcome.followed_llm
        trace["deterministic_vote"] = view.deterministic_vote
        trace["fields"] = dict(outcome.fields)
        if emit is not None:
            try:
                emit(TRACE_EVENT, trace)
            except Exception:  # noqa: BLE001,S110 - tracing must never break a decision
                pass
        return outcome

    if not getattr(client, "enabled", False):
        reason = getattr(client, "disabled_reason", None) or "client disabled"
        return done(consult.fallback(view, "client_disabled"), consulted=False, why=reason)

    if can_start is not None and not can_start():
        return done(consult.fallback(view, "no_time"), consulted=False, why="no_time_on_clock")

    try:
        skip_reason = consult.applies(view) if hasattr(consult, "applies") else None
    except Exception as exc:  # noqa: BLE001 - the never-raises contract
        skip_reason = f"applies_raised: {exc!r}"
    if skip_reason:
        return done(consult.fallback(view, "not_applicable"), consulted=False, why=skip_reason)

    try:
        payload = consult.payload(view)
    except Exception as exc:  # noqa: BLE001 - the never-raises contract
        return done(consult.fallback(view, "payload_failed"), consulted=False, why=repr(exc))

    started = perf_counter()
    try:
        result = client.structured(
            system=consult.system_prompt(prompt_dir),
            payload=payload,
            response_model=consult.Response,
            trigger=f"deduction_consult:{consult.name}",
        )
    except Exception as exc:  # noqa: BLE001 - the never-raises contract
        return done(
            consult.fallback(view, "call_failed"),
            consulted=True,
            why=repr(exc),
            latency_ms=round((perf_counter() - started) * 1000, 1),
        )

    latency_ms = round((perf_counter() - started) * 1000, 1)
    trace["latency_ms"] = latency_ms
    trace["model"] = getattr(result, "model", None)
    trace["usage"] = getattr(result, "usage", None)
    if getattr(result, "raw_response", None):
        trace["raw_response"] = result.raw_response
    try:
        trace["response"] = result.value.model_dump()
    except Exception:  # noqa: BLE001 - the never-raises contract
        trace["response"] = None

    try:
        outcome = consult.apply(result.value, view)
    except Exception as exc:  # noqa: BLE001 - the never-raises contract
        return done(consult.fallback(view, "apply_failed"), consulted=True, why=repr(exc))

    # Last line of defence: `apply` is experiment code and may be wrong. An illegal target
    # would be silently coerced by the vote path into something we did not choose, so it
    # is caught here where it is still attributable to the consult.
    if not view.is_legal(outcome.vote):
        return done(
            consult.fallback(view, "illegal_vote"),
            consulted=True,
            why=f"consult returned illegal vote {outcome.vote!r}",
        )
    return done(outcome, consulted=True)
