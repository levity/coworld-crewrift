"""Registry of deduction LLM consults, selected by one env var.

    CREWBORG_DEDUCTION_LLM=off            (or unset)  -- deterministic branch, unchanged
    CREWBORG_DEDUCTION_LLM=shortlist                  -- run that consult with its defaults
    CREWBORG_DEDUCTION_LLM=shortlist:k=4,min_confidence=0.7

One env var holding a name, with the presets in code, is the same shape as
`CREWBORG_DECISION_GATE` and `CREWBORG_SPEAKER_TRUST` next door -- deliberately, so an A/B
ships ONE image and the arms differ only by `--secret-env`. The `:key=value` suffix
extends that to per-consult tunables, so sweeping a threshold does not need a rebuild
either.

`1`/`true`/`on` are accepted for the historical toggle spelling and resolve to
`DEFAULT_CONSULT`.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from crewborg.deduction.consult.base import (
    PROMPT_DIR_ENV,
    BaseConsult,
    Consult,
    ConsultOutcome,
    response_schema,
)
from crewborg.deduction.consult.runner import TRACE_EVENT, run_consult
from crewborg.deduction.consult.shortlist import ShortlistConsult
from crewborg.deduction.consult.view import (
    SKIP,
    Candidate,
    ConsultView,
    GameEvent,
    Utterance,
)

CONSULT_ENV = "CREWBORG_DEDUCTION_LLM"
DEFAULT_CONSULT = "shortlist"

REGISTRY: dict[str, type[BaseConsult]] = {
    ShortlistConsult.name: ShortlistConsult,
}

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"", "0", "false", "no", "off"}


def parse_spec(spec: str) -> tuple[str, dict[str, str]]:
    """Split `name:key=value,key=value` into its parts."""

    name, _, tail = spec.strip().partition(":")
    params: dict[str, str] = {}
    for chunk in tail.split(","):
        key, sep, value = chunk.partition("=")
        if sep and key.strip():
            params[key.strip()] = value.strip()
    return name.strip().lower(), params


def resolve_consult(env: Mapping[str, str] | None = None) -> BaseConsult | None:
    """The configured consult, or None for the unchanged deterministic branch.

    An unknown name resolves to None rather than to a default. A typo must degrade to the
    shipped behaviour, never to a different experiment than the one the arm names -- an
    A/B that silently ran something else is worse than one that ran nothing.
    """

    source = os.environ if env is None else env
    raw = (source.get(CONSULT_ENV) or "").strip()
    if raw.lower() in _FALSY:
        return None
    name, params = parse_spec(raw)
    if name in _TRUTHY:
        name = DEFAULT_CONSULT
    factory = REGISTRY.get(name)
    return None if factory is None else factory(params)


__all__ = [
    "CONSULT_ENV",
    "DEFAULT_CONSULT",
    "PROMPT_DIR_ENV",
    "REGISTRY",
    "SKIP",
    "TRACE_EVENT",
    "BaseConsult",
    "Candidate",
    "Consult",
    "ConsultOutcome",
    "ConsultView",
    "GameEvent",
    "Utterance",
    "parse_spec",
    "resolve_consult",
    "response_schema",
    "run_consult",
]
