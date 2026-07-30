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


LLM_ENV = "CREWBORG_DEDUCTION_LLM"


def llm_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Is an LLM consult the final step of the deduction branch?

    OFF (default, and on any unrecognised value): the branch is exactly what it is
    today -- solve at the auto-submit backstop, vote the result. ON: the same solve runs
    earlier (see below), and the named consult from `deduction.consult` gets the last
    word on the vote. Which consult, and with what parameters, is the value of this env
    var; see `deduction/consult/__init__.py`.

    THE COST OF TURNING IT ON, STATED. An LLM call may only START while enough of the
    meeting remains for it to finish before the 48-tick auto-submit backstop -- with the
    default 3s timeout that floor is 132 ticks. So when this is on, the deduction solve
    and the vote both move from 48 ticks remaining to ~132, giving up roughly 84 ticks
    (~3.5s) of late chat. That is a real loss for the deterministic half: the solver
    normally consumes 1152 of 1200 ticks of utterances before deciding. It is the price
    of having the LLM see the solve at all, and it is why this is not on by default.
    """

    from crewborg.deduction.consult import resolve_consult

    return resolve_consult(env) is not None


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
    # FALSIFIED 2026-07-28 -- DO NOT A/B THIS. Kept only so the retired arm stays
    # readable; it is not a live question.
    #
    # The case for it rested on 60 league episodes: structural 9/9 = 100%,
    # non-structural 5/19 = 26% (random ~29%), non-structural = 70% of `loose`'s
    # ejects. Re-measured on 254 league episodes / 192 crew seats / 563 live
    # decisions (`crewrift-analysis/crew_decision_audit.py`), that does not hold:
    #     structural      49/49 = 100%   (59.8% of ejects)
    #     non-structural  21/33 =  64%   (40.2% of ejects)
    # Non-structural is well above random, and it is 40% of our ejects rather than
    # 70%. So this preset trades away 40% of our coverage to move precision
    # 85.4% -> 100%, and coverage -- not precision -- is the scarce quantity: we
    # name a player in 14.6% of live crew decisions, last in the league by a wide
    # margin. It is the wrong direction on the binding constraint.
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
    # `on` plus accuracy: shrink each speaker's tau toward whether their accusations
    # matched `murder_clears` (a murdered player is crew, so that accuser was wrong) or
    # a later `pin` (that accuser was right). In-episode ground truth needing no reveal;
    # ejections reveal nothing, the engine prints only "WAS KILLED".
    #
    # Same family as `on`, so it stays ONE env var and an A/B still moves one thing.
    # It shrinks toward the selectivity estimate rather than a flat prior, so with no
    # outcome evidence it is exactly `on`.
    #
    # MEASURED NULL 2026-07-29 -- built and evaluated, do not ship without new evidence.
    # Over 563 live league decisions (`crewrift-analysis/eval_outcome_trust.py`):
    #     top-1     0.460 -> 0.451
    #     AUC       0.626 -> 0.626
    #     coverage  0.172 -> 0.167
    #     precision 0.897 -> 0.915
    # It is NOT sparsity: the adjustment fires in 31.3% of decisions (murder_clears
    # present in 56.5%, pins in 11.5%). The mechanism works; it just does not help.
    #
    # The motivating read was also wrong, and is corrected here rather than only in
    # chat: top-1 accuracy falls with `decision.sources` (60.7% at one, 16.7% at six),
    # but that is the support CITED for a decision, not how many players spoke. Against
    # the real distinct-speaker count accuracy RISES (1 -> 0.381, 5+ -> 0.483), so the
    # social channel does not degrade as more players weigh in.
    "outcome": {
        "speaker_trust": True,
        "speaker_trust_prior": 0.25,
        "speaker_trust_k": 2.0,
        "speaker_outcome_trust": True,
    },
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


EJECTION_LIVENESS_ENV = "CREWBORG_EJECTION_LIVENESS"

# Whether "the game is still running" is used as evidence (see
# `inference.build_assignment_table`). A FOURTH separate env var, for the same reason
# the others are separate.
#
# This is a CORRECTNESS fix, not a strategy knob: an impostor can only leave the game
# by ejection, so a hypothesis whose whole impostor set has already been voted out is
# impossible -- the crew would have won. The solver scores those hypotheses today.
# It only ever removes assignments, so it cannot manufacture a confident wrong answer.
#
# ON by default since 2026-07-30. It was introduced default-off so the unflagged path
# stayed byte-identical while it was unproven; it is kept as a flag only so `=off`
# restores the old posterior without a rebuild. Note the asymmetry with every other
# preset family here: for those, an unset or misspelt value degrades to shipped
# behaviour, whereas for this one it degrades to ON -- which is correct, because "the
# crew has already won" is not a variant of the solver, it is the solver being right.
#
# Measured offline over 563 live league decisions
# (`crewrift-analysis/ejection_liveness_counterfactual.py`, 254 episodes): reaches 1.8%
# of decisions, because only 2.7% see >=2 prior ejections. Where it reaches, top-1 flips
# to the truth 4 times and away 0 times, and 5 skips clear the eject bar, all 5 correct.
# Net coverage 14.6% -> 15.5%, precision 85.4% -> 86.2%. Do NOT buy a hosted A/B for
# this -- a +0.9pp coverage move is an order of magnitude below what n=100 can resolve.
EJECTION_LIVENESS_PRESETS: dict[str, Overrides] = {
    "off": {"ejection_liveness": False},
    "on": {"ejection_liveness": True},
}


# Independent lever families that all feed `InferenceConfig`. Separate env vars on
# purpose (an A/B must move one thing); listed together only so resolution is one loop.
INFERENCE_FAMILIES: tuple[tuple[str, dict[str, Overrides]], ...] = (
    (TRUST_ENV, TRUST_PRESETS),
    (KILL_WINDOW_ENV, KILL_WINDOW_PRESETS),
    (EJECTION_LIVENESS_ENV, EJECTION_LIVENESS_PRESETS),
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
