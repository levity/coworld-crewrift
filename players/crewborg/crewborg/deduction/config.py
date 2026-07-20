"""Configuration boundary for the parallel deduction implementation."""

from __future__ import annotations

import os
from collections.abc import Mapping

FEATURE_ENV = "CREWBORG_DEDUCTION_HISTORY"
_TRUTHY = {"1", "true", "yes", "on"}


def enabled(env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return source.get(FEATURE_ENV, "").strip().lower() in _TRUTHY


def enabled_for_role(
    role: str | None,
    env: Mapping[str, str] | None = None,
) -> bool:
    """Keep the experiment crew-only so the legacy impostor policy is intact."""

    return role == "crewmate" and enabled(env)
