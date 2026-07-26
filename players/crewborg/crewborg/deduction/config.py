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
# Measured offline over 476 living-seat decisions from 100 Prime games
# (`tools/sweep_decision_gate.py`), validated on a 50/50 episode-level held-out split.
# Untested against the league field -- both halves face the same crewborg-aaln.
GATE_PRESETS: dict[str, dict[str, float | int]] = {
    "shipped": {},
    # The minimal interpretable unit: margin and support are JOINTLY binding --
    # held-out, relaxing either alone moves coverage 16.0% -> 16.0% (nothing), and
    # both together give 16.0% -> 21.8% with 45 right / 0 wrong. The margin floor is
    # lowered to an epsilon rather than removed: margin == 0 means a flat posterior
    # and only 55% top-1 accuracy, while ANY positive margin measured 100% across 203
    # decisions. base_probability is deliberately NOT touched here.
    "loose": {
        "base_margin": 1e-3,
        "require_support": False,
    },
    # Adds the probability threshold on top. A separate question; kept apart so the
    # two are never bundled into one A/B.
    "loose+p40": {
        "base_margin": 1e-3,
        "require_support": False,
        "base_probability": 0.40,
    },
}


def gate_overrides(env: Mapping[str, str] | None = None) -> dict[str, float | int]:
    """Return `DecisionConfig` field overrides for the selected preset.

    An unknown or unset value yields no overrides, so a typo degrades to the
    shipped gate rather than to something unintended.
    """

    source = os.environ if env is None else env
    return dict(GATE_PRESETS.get(source.get(GATE_ENV, "").strip().lower(), {}))
