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


GATE_ENV = "CREWBORG_DECISION_GATE"

# Named settings for `DecisionConfig`, so an A/B ships ONE image and the arms differ
# only by `--secret-env`. Keeping the presets here rather than in `decision.py` keeps
# the gate's arithmetic free of environment lookups.
#
# "loose": measured offline over 476 living-seat decisions from 100 Prime games
# (`tools/sweep_decision_gate.py`). Sweeping `base_probability` alone changes almost
# nothing (coverage 14.9% -> 16.8%) because the SUPPORT gate binds first; relaxing
# support to one source and dropping the margin floor is what opens coverage. On a
# 50/50 episode-level held-out split: coverage 16.0% -> 30.6%, 63 ejects, 0 wrong
# (95% upper bound on the error rate 4.8%). Untested against the league field.
GATE_PRESETS: dict[str, dict[str, float | int]] = {
    "shipped": {},
    "loose": {
        "base_probability": 0.40,
        "base_margin": 0.0,
        "min_independent_sources": 1,
    },
}


def gate_overrides(env: Mapping[str, str] | None = None) -> dict[str, float | int]:
    """Return `DecisionConfig` field overrides for the selected preset.

    An unknown or unset value yields no overrides, so a typo degrades to the
    shipped gate rather than to something unintended.
    """

    source = os.environ if env is None else env
    return dict(GATE_PRESETS.get(source.get(GATE_ENV, "").strip().lower(), {}))
