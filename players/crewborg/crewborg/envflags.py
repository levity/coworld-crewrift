"""The env-var boundary: one place that decides what "on" means.

Every crewborg feature is gated by a ``CREWBORG_*`` environment variable, because
an A/B ships ONE image and the arms differ only by ``--secret-env`` (see
``docs/best_practices.md``). Four modules had grown their own copy of the same
three-line truthiness check; a flag that is "on" in one module and "off" in
another is an experiment that measures nothing.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

TRUTHY = frozenset({"1", "true", "yes", "on"})


def truthy(name: str, env: Mapping[str, str] | None = None) -> bool:
    """Whether ``name`` is set to any accepted spelling of true."""

    source = os.environ if env is None else env
    return source.get(name, "").strip().lower() in TRUTHY


def int_flag(name: str, default: int, *, minimum: int = 0) -> int:
    """``name`` as an int, clamped at ``minimum``; ``default`` if unset or unparsable."""

    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default
