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
    #
    # PRECISION IS THE WRONG OBJECTIVE HERE, and reading these presets on precision is
    # what previously ruled this one out ("51.5% coverage at 60.0% precision"). The
    # quantity that matters is delivered CORRECT ejects net of the crewmates a wrong
    # eject removes -- and those two are not equally valuable. Measured over 443 league
    # episodes by reconstructing ejections from the ballots
    # (`crewrift-analysis/eject_value.py`), crew win rate is:
    #
    #     impostors ejected ->    0        1        2
    #     0 crewmates ejected   21.2%    64.5%    94.3%
    #     1                      3.3%    53.8%    88.2%
    #     2                      1.3%    47.1%
    #
    # An ejected impostor is worth about +43 pp; each crewmate lost costs about -9 pp.
    # The logistic fit gives log-odds(crew win) = -1.62 + 2.39*imp - 0.88*crew, so a
    # wrong eject costs |0.88/2.39| = 0.37 of what a right one gains.
    #
    # At that exchange rate, scoring the gate curve on net value rather than precision
    # (`crewrift-analysis/crew_gate_curve.py`, 1012 live league decisions) inverts the
    # old conclusion. Correct ejects delivered per decision, net of 0.37x the wrong ones:
    #
    #     bar 0.65 (shipped)  coverage 0.118  precision 0.916  net 0.104
    #     bar 0.40            coverage 0.505  precision 0.566  net 0.205
    #     bar 0.30            coverage 0.930  precision 0.481  net 0.270
    #
    # So this is the wrong-objective correction, not a new mechanism. It is a STRATEGY
    # change -- only games settle it -- but unlike most of our levers the predicted
    # effect is large enough for a hosted A/B to resolve.
    # THE THREE CONSTANTS MOVE TOGETHER, because `decide` overrides the bar with
    # ABSOLUTE values, not offsets:
    #
    #     required = base_probability
    #     if skip_loss >= parity_risk_cutoff: required = forced_vote_probability
    #     elif wrong_eject_loss > 0:          required = dangerous_wrong_eject_probability
    #
    # `forced_vote_probability` exists to make us vote MORE readily when skipping is
    # what loses the game, and at the shipped base of 0.65 its 0.51 does exactly that.
    # Lowering base alone to 0.40 would leave 0.51 above it and invert the branch into a
    # bar RAISE. So it moves down with base, keeping the shipped 0.14 gap below it.
    # `dangerous_wrong_eject_probability` stays at 0.80: that branch fires when a wrong
    # eject is what loses the game, and its caution is an absolute risk statement rather
    # than something that should loosen because the base moved.
    #
    # Measured over 663 recorded league decisions, the overrides govern 28 % of them
    # (0.80 in 22.0 %, 0.51 in 5.9 %), so this is not a footnote -- the lever reaches
    # roughly the 78 % that are not in the dangerous-wrong-eject class.
    # All three bars scaled PROPORTIONALLY from the shipped 0.65/0.51/0.80, preserving
    # their ratios (x0.785 and x1.231). That keeps each branch's meaning intact --
    # `forced_vote` below base, `dangerous` above it -- with one number to reason about.
    #
    # WHY 0.40 AND NOT THE MEASURED OPTIMUM OF 0.30. The value model says 0.30 (see
    # `loose+bayes`), but it gets there at 0.489 precision, i.e. most of our named votes
    # would eject a CREWMATE. That is net-positive only while the measured exchange rate
    # of 0.37 holds, and that rate is observational. Keeping precision above a coin flip
    # makes the change robust to it being wrong:
    #
    #     bar 0.30  precision 0.489  -> net at cost 1.0 = 0.928 * (2*0.489-1) = -0.020
    #     bar 0.40  precision ~0.57  -> net at cost 1.0 = 0.45  * (2*0.57 -1) = +0.063
    #
    # So 0.40 stays positive under ANY cost ratio up to 1.0, while 0.30 needs the ratio
    # to be below ~0.9 to pay at all. Giving up some measured value to stop depending on
    # the least certain number in the derivation.
    "loose+p40": {
        "base_margin": 1e-3,
        "require_support": False,
        "base_probability": 0.40,
        "forced_vote_probability": 0.31,
        "dangerous_wrong_eject_probability": 0.49,
    },
    # The offline optimum at the measured 0.37 exchange rate. Deliberately listed as a
    # separate arm rather than folded into the one above: it takes coverage to 0.930,
    # which is a behaviour change of a different order (roughly Eva-00's posture -- the
    # league's best crew contributor at +4.4 pp matched, naming on every ballot at 63%
    # precision). Offline it beats bar 0.40, but the gate curve is a ranking calculation
    # on recorded histories and cannot see that ejecting more people changes every later
    # meeting, so prefer 0.40 as the first arm and come here only if it pays.
    "loose+p30": {
        "base_margin": 1e-3,
        "require_support": False,
        "base_probability": 0.30,
        "forced_vote_probability": 0.21,
    },
    # All three bar constants set to the value-maximising bar implied by the measured
    # eject exchange rate, rather than tuned by hand. Vote iff p*gain > (1-p)*cost, so
    # required = cost/(gain+cost); pivotality cancels, because being one of ~6 voters
    # scales gain and cost equally.
    #
    #   base 0.30       the modal state (0 ejections, 84% of our decisions) has
    #                   gain +0.433 / cost 0.179 -> 0.292.
    #   dangerous 0.31  `wrong_eject_loss > 0` fires on 22% of decisions with median
    #                   loss 0.430, so cost there is 0.416*0.212 + 0.584*0.179 = 0.193
    #                   -> 0.308. Note how SMALL that premium is: the trigger barely
    #                   selects for extra danger, because the state a wrong eject drops
    #                   you into is already near-worthless (V = 0.033). The shipped 0.80
    #                   is ~2.6x too high, and blocking that 22% costs more than the
    #                   base bar does.
    #   forced 0.21     kept below base so the branch cannot invert. Measured INERT --
    #                   0.04, 0.21 and 0.40 give bit-identical results, because it fires
    #                   on 5.9% of decisions and never binds.
    #
    # Offline over 5279 live league decisions (crew_gate_curve.py --gate-grid): coverage
    # 0.159 -> 0.930, precision 0.840 -> 0.467, value +0.0507 -> +0.1042 win points per
    # decision, CIs [.0457,.0558] against [.0929,.1158]. That is 2.06x the shipped gate
    # and the largest crew effect we have measured.
    "loose+bayes": {
        "base_margin": 1e-3,
        "require_support": False,
        "base_probability": 0.30,
        "forced_vote_probability": 0.21,
        "dangerous_wrong_eject_probability": 0.31,
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


SOCIAL_WEIGHT_ENV = "CREWBORG_SOCIAL_WEIGHT"

# Bound on `InferenceConfig.social_weight`, read from the env as a bare float so a fit
# can sweep it continuously. Out-of-range or unparseable values are ignored rather than
# clamped: a clamp silently runs an arm nobody asked for, and this scalar sets how
# sharp the whole posterior is.
SOCIAL_WEIGHT_MAX = 4.0


def social_weight_override(env: Mapping[str, str] | None = None) -> Overrides:
    """`social_weight` from the env, or `{}` if unset, unparseable or out of range."""

    source = os.environ if env is None else env
    raw = source.get(SOCIAL_WEIGHT_ENV, "").strip()
    if not raw:
        return {}
    try:
        value = float(raw)
    except ValueError:
        return {}
    if not 0.0 <= value <= SOCIAL_WEIGHT_MAX:
        return {}
    return {"social_weight": value}


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
# `inference.build_assignment_table`). Its own env var, for the same reason the others
# have theirs: an A/B must move one thing.
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


SKIP_VOTE_ENV = "CREWBORG_SKIP_VOTE"

# Whether a SKIP ballot is scored as evidence about the voter. Its own env var: this
# changes what evidence EXISTS, which is a different question from how heavily the social
# channel is weighed (`CREWBORG_SOCIAL_WEIGHT`) or what is done with the result (the gate).
#
# The measured field rates are P(skip|crew) = 0.500 against P(skip|impostor) = 0.240
# over 8227 league ballots -- see `InferenceConfig.skip_vote_likelihood` for the
# measurement and for why the weight is shrunk rather than taken at face value.
SKIP_VOTE_PRESETS: dict[str, Overrides] = {
    "off": {},
    # Shrunk to half the targeted-ballot weight, because four of the ten policies with
    # enough ballots to measure run flat or inverted and we cannot see a voter's policy.
    "on": {"skip_vote_likelihood": True},
    # The measured rates at full targeted-ballot weight. Strictly more aggressive; use
    # it only to bracket how much of any effect is the weight rather than the signal.
    "strong": {"skip_vote_likelihood": True, "skip_vote_weight": 0.35},
}


# Independent lever families that all feed `InferenceConfig`. Separate env vars on
# purpose (an A/B must move one thing); listed together only so resolution is one loop.
INFERENCE_FAMILIES: tuple[tuple[str, dict[str, Overrides]], ...] = (
    (KILL_WINDOW_ENV, KILL_WINDOW_PRESETS),
    (EJECTION_LIVENESS_ENV, EJECTION_LIVENESS_PRESETS),
    (SKIP_VOTE_ENV, SKIP_VOTE_PRESETS),
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

    Merges the independent preset families (kill window, skip vote) and the
    continuously-valued social weight. Unset or unrecognised values yield no overrides,
    so the shipped posterior is exactly unchanged unless someone opts in.
    """

    overrides: Overrides = {}
    for env_var, presets in INFERENCE_FAMILIES:
        overrides.update(_preset(presets, env_var, env))
    overrides.update(social_weight_override(env))
    return overrides


def gate_overrides(env: Mapping[str, str] | None = None) -> Overrides:
    """Return `DecisionConfig` field overrides for the selected preset.

    An unknown or unset value yields no overrides, so a typo degrades to the
    shipped gate rather than to something unintended.
    """

    return _preset(GATE_PRESETS, GATE_ENV, env)


VOTE_COMMIT_ENV = "CREWBORG_VOTE_COMMIT"

# WHEN the crew ballot is cast, which is a different question from what it says.
#
# Shipped behaviour holds the vote until the 48-tick auto-submit backstop -- tick
# ~1152 of a 1200-tick vote timer -- for the stated reason of "consuming the most chat
# possible" (`modes/attend_meeting.py`). Measured 2026-08-01 over 17,648 league
# meetings (`crewrift-analysis/pin_conviction.py`), that reason does not survive:
#
#   * 98.6% of all meeting chat has already landed by tick 300, and 99.8% by 1152, so
#     the wait buys 1.2% more transcript;
#   * our ballot does not respond to chat anyway (placebo-controlled conditional
#     logit: gap -0.24, z = -0.3) nor to the vote board (+0.02);
#   * and it costs the entire audience. FIVE league policies demonstrably follow the
#     visible vote board -- softmaxwell +0.88 (z = 14.6), crewborg-aaln +0.65,
#     daf-actinf +0.48, notsus +0.37, hunter-relhalpha +0.16, all placebo-clean --
#     and every one of them commits by tick ~315. `vote_aft` is zero in 100% of our
#     ballots: nothing has ever voted after us, in any meeting we have ever played.
#
# `on-pin` submits as soon as the EARLY solve (already run at
# `DEDUCTION_EARLY_CHAT_TICKS` = 240, today only to decide what to say) names a
# target. A skip is NOT committed early: the full solve still runs at the backstop, so
# this can only ever move an eject forward, never remove one.
#
# Sizing, simulated over the real ballots and the real plurality rule: our named
# target's ejection 23.0% -> 27.7%, impostors 18.8% -> 22.6% (+3.8 pp), crewmates
# 4.2% -> 5.1% (+0.9 pp) -- about +0.7 pp of crew win at current coverage, and it
# scales with coverage. The transfer assumption is stated in `pin_conviction.commit`:
# the follow-gaps come from ordinary mid-meeting boards, not from a lone early dot.
# `on-pin@<tick>` moves the early solve as well as the commit. THE TICK IS THE
# WHOLE LEVER, and 240 is the wrong value for it.
#
# `on-pin` at the shipped 240 was A/B'd (v34 vs v35, 100+100, diverse roster) and
# LOST: it fired on 98% of named ballots and the guards held, but by tick 240 the
# live field has already voted. Measured on that A/B's own episodes, crew seats
# still to vote per meeting:
#
#     tick    0     15     30     60    100    240
#     seats 3.01   2.07   1.68   0.93   0.22   0.16
#
# and the transcript is 84.1% spoken by tick 15 against 86.5% by 240 -- so the
# 240-tick wait buys 2.4 points of chat and costs 13x the audience.
#
# Truncated re-solve over 589 league decisions (`tick_commit_guard.py`), against
# the full-audit rebuild: at tick 15 the solver picks the same target on 91.7% of
# shared ejects, reaches 73% of them (the rest still fire at the backstop, so none
# are lost), and precision RISES 63.7% -> 76.7% because the early-decidable ejects
# are the confident ones. Net delivered value is flat. Tick 30 is marginally the
# best net at somewhat less audience.
#
# NOT structural-only. That was the first design and it is dead: of 117 ejects the
# policy flags `structural`, only 9 have a unique eligible pair under structure
# alone -- the social channel breaks the tie on the rest -- so a structural-only
# gate would fire ~9 times per 400 episodes.
VOTE_COMMIT_TICKS: dict[str, int] = {
    "on-pin": 240,       # the A/B'd arm; kept so the losing configuration is nameable
    "on-pin@60": 60,
    "on-pin@30": 30,
    "on-pin@15": 15,
}


def vote_commit(env: Mapping[str, str] | None = None) -> str:
    """When to cast the crew ballot: `backstop` (shipped) or an `on-pin[@tick]`.

    An unset or misspelt value degrades to `backstop`, i.e. to shipped behaviour,
    which is the same rule every other preset family here follows.
    """

    source = os.environ if env is None else env
    raw = source.get(VOTE_COMMIT_ENV, "").strip().lower()
    return raw if raw in VOTE_COMMIT_TICKS else "backstop"


def vote_commit_tick(env: Mapping[str, str] | None = None) -> int | None:
    """The meeting age at which the early solve runs, or None under `backstop`.

    `None` means the caller keeps the shipped constant and never commits early.
    """

    return VOTE_COMMIT_TICKS.get(vote_commit(env))
