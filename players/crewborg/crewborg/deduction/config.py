"""Configuration boundary for the parallel deduction implementation."""

from __future__ import annotations

import os
from collections.abc import Mapping

from crewborg.envflags import truthy

FEATURE_ENV = "CREWBORG_DEDUCTION_HISTORY"


def enabled(env: Mapping[str, str] | None = None) -> bool:
    return truthy(FEATURE_ENV, env)


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
Overrides = dict[str, float | bool | int]


GATE_PRESETS: dict[str, Overrides] = {
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
    # Keeps `loose`'s margin relaxation but ejects ONLY on structural certainty.
    #
    # Measured on 60 LEAGUE episodes (2026-07-26), which is the first data we have
    # from a mixed roster -- every earlier A/B ran six copies of this policy as the
    # crew, so the social evidence channel was talking to itself. Against real
    # opponents that channel collapses:
    #     structural      9/9  = 100%
    #     non-structural  5/19 =  26%   (random voting is ~29%)
    # and it is 70% of the ejects `loose` produces, so `loose` as shipped is mostly
    # casting near-random votes. No probability threshold rescues it -- the posterior
    # inside that class averages 0.786 when right and 0.798 when wrong -- so the cut
    # has to be by evidence class.
    #
    # NOTE this is STRICTER than the shipped gate, which also allowed
    # accusation-backed ejects with >=2 independent sources.
    "structural-only": {
        "base_margin": 1e-3,
        "require_structural": True,
    },
}


TRUST_ENV = "CREWBORG_SPEAKER_TRUST"

# Per-speaker tempering of the claim/vote channels (see inference._speaker_trust).
# Deliberately a SEPARATE env var from CREWBORG_DECISION_GATE: trust changes the
# posterior, the gate changes what we do with it, and bundling them would make an
# A/B uninterpretable. Values are "<prior>" or "<prior>:<k>".
TRUST_PRESETS: dict[str, Overrides] = {
    "off": {},
    "on": {"speaker_trust": True, "speaker_trust_prior": 0.25, "speaker_trust_k": 2.0},
    "mild": {"speaker_trust": True, "speaker_trust_prior": 0.50, "speaker_trust_k": 2.0},
}


KILL_WINDOW_ENV = "CREWBORG_KILL_WINDOW"

# How a witnessed body transition names its killer (see inference._witnessed_actions).
# A THIRD separate env var, for the same reason trust and the gate are separate: this
# changes which structural facts exist, trust changes how social evidence is weighed,
# and the gate changes what is done with the result. Bundling any two makes an A/B
# uninterpretable.
#
# `margin` is the soundness fix: the sim resolves a kill between rendered frames, so an
# exact 20px test claims precision the observation stream does not have. Measured
# failure in xreq_51754f1f/ereq_ff5a9fdd -- the true killer's last sampled distance was
# 23.0px (outside) while a bystander sat at 16.3px (inside), so the rule pinned a
# CREWMATE with p=1.0 and eliminated the true assignment from the hypothesis space.
#
# `at_least_one` is the recovery: once the margin makes such a transition ambiguous, the
# observation would otherwise be discarded. Emitting it as a hard "at least one of
# these" constraint keeps it, and it is sound by construction.
KILL_WINDOW_PRESETS: dict[str, Overrides] = {
    "off": {},
    # The fix alone: stop claiming a unique actor at the boundary. Costs coverage --
    # some currently-correct pins become ambiguous and are dropped.
    "margin": {"kill_range_margin": 6},
    # Lever #1 alone, at the shipped exact radius: recovers the 2+-actor transitions
    # that are discarded today (98 per 100 games) without touching the pin test.
    "at-least-one": {"ambiguous_kill_constraints": True},
    # Both: the margin makes boundary cases ambiguous, at_least_one keeps them as a
    # true disjunction instead of dropping them. This is the intended end state.
    "both": {"kill_range_margin": 6, "ambiguous_kill_constraints": True},
}


# Independent lever families that both feed `InferenceConfig`. Separate env vars on
# purpose (an A/B must move one thing); listed together only so resolution is one loop.
INFERENCE_FAMILIES: tuple[tuple[str, dict[str, Overrides]], ...] = (
    (TRUST_ENV, TRUST_PRESETS),
    (KILL_WINDOW_ENV, KILL_WINDOW_PRESETS),
)


def _preset(presets: dict[str, Overrides], env_var: str,
            env: Mapping[str, str] | None) -> Overrides:
    """The named preset, or `{}` — so a typo degrades to shipped, never to something else."""

    source = os.environ if env is None else env
    return dict(presets.get(source.get(env_var, "").strip().lower(), {}))


def inference_overrides(
    env: Mapping[str, str] | None = None,
) -> Overrides:
    """`InferenceConfig` field overrides from the selected presets.

    Merges the independent preset families (speaker trust, kill window). Unset or
    unrecognised values yield no overrides, so the shipped posterior is exactly
    unchanged unless someone opts in.
    """

    overrides: Overrides = {}
    for env_var, presets in INFERENCE_FAMILIES:
        overrides.update(_preset(presets, env_var, env))
    return overrides


def gate_overrides(env: Mapping[str, str] | None = None) -> Overrides:
    """Return `DecisionConfig` field overrides for the selected preset.

    An unknown or unset value yields no overrides, so a typo degrades to the
    shipped gate rather than to something unintended.
    """

    return _preset(GATE_PRESETS, GATE_ENV, env)
