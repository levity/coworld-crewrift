"""State-aware CREW vote policy (env ``CREWBORG_VOTE_POLICY``, OFF by default).

The fitted crew vote (``suspicion.top_suspect``) is deliberately passive: it casts
a ballot only at calibrated near-certainty (``WEIGHTS_VOTE_PROBABILITY`` = 0.9) with
the clear-leader rule disabled, so it skips ~88% of votes. A hosted gate sweep proved
that simply *lowering* that global bar loses — our fitted posterior is noisy at
mid-confidence, so cheap votes eject crewmates (64% wrong at gate 0.5). So this policy
does NOT lower the bar globally. Instead it ports the rival ``crewborg-aaln`` policy's
state-aware vote, whose extra votes come from **social consensus** (safer than our
solo posterior) and a **parity-aware** bar. It is gated behind ``CREWBORG_VOTE_POLICY``
so control=off / candidate=on is a clean A/B; with the flag off, ``top_suspect`` is
byte-identical to today.

CREW only — the imposter vote is never touched (``top_suspect`` reaches here only on
its fitted crewmate branch). In priority (``crew_vote_target``):

1. **Must-eject** (:func:`must_eject`): when the alive crew is one death from parity
   with the imposters, a skip hands them the game on the next kill, so the confidence
   bar drops toward 0 — vote the top living suspect (desperate but necessary).
2. **Corroborated pile-on** (:func:`corroborated_pileon_target`): vote a non-self
   target carrying a corroborated accusation — >=2 distinct, EVIDENCE-BACKED (not a
   bare "X sus"), non-confirmed-imposter accusers — even below the 0.9 bar. These
   extra votes ride the crowd's evidence, not our noisy solo posterior.
3. **Comfortable bar** (0.75 vs the tight 0.9): below must-eject / pile-on, accept a
   clear leader over a non-flat field at 0.75, reusing the disabled-on-the-fitted-path
   clear-leader / lead-margin rule (``VOTE_LEAD_MIN_P`` / ``VOTE_LEAD_MARGIN``).

A truly flat field still skips (outside must-eject), and self is never voted.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from crewborg.strategy.suspicion import (
    VOTE_LEAD_MARGIN,
    VOTE_LEAD_MIN_P,
    WEIGHTS_VOTE_PROBABILITY,
    _imposter_count,
    witnessed_imposters,
)
from crewborg.types import Belief

FEATURE_ENV = "CREWBORG_VOTE_POLICY"
_TRUTHY = {"1", "true", "yes", "on"}

# Comfortable evidence bar (posterior P(imposter)) for a clear leader over a non-flat
# field — the crew can absorb a mistake here, so accept below near-certainty. The tight
# bar stays the fitted ``WEIGHTS_VOTE_PROBABILITY`` (0.9).
COMFORTABLE_VOTE_PROBABILITY = 0.75

# A corroborated pile-on needs at least this many distinct, evidence-backed accusers.
PILEON_MIN_ACCUSERS = 2

# Accusations tagged "bare" are unsupported "<color> sus" assertions — never
# pile-on-worthy; every other kind is tied to evidence (body / vent / sighting / vote).
_BARE_EVIDENCE_KIND = "bare"


def vote_policy_enabled(env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return source.get(FEATURE_ENV, "").strip().lower() in _TRUTHY


# --- game-state counts (crew estimate) ----------------------------------------


def imposters_remaining(belief: Belief) -> int:
    """The imposter budget still at large: K minus confirmed imposters now dead.

    A crewmate cannot see the imposter roster, so "confirmed" is the witnessed
    kill/vent set (:func:`witnessed_imposters`) — the only imposters the crew knows
    for sure — restricted to those the census now lists dead.
    """

    confirmed_dead = sum(
        1
        for color in witnessed_imposters(belief)
        if (record := belief.roster.get(color)) is not None and record.life_status == "dead"
    )
    return max(0, _imposter_count(belief) - confirmed_dead)


def alive_count(belief: Belief) -> int:
    """Players currently alive, including self (known reliably during a meeting)."""

    alive = {color for color, record in belief.roster.items() if record.life_status == "alive"}
    self_color = belief.self_color or belief.voting.self_marker_color
    if self_color is not None and belief.self_role != "dead":
        alive.add(self_color)
    return len(alive)


def must_eject(belief: Belief) -> bool:
    """True when skipping loses: the next kill would reach (or pass) parity.

    With ``I`` imposters and ``C`` crew alive, the imposters win at ``I >= C``; a
    skipped vote lets them kill once more, so at ``C - I <= 1`` the crew must eject
    its best read now.
    """

    imps = imposters_remaining(belief)
    if imps <= 0:
        return False
    crew = alive_count(belief) - imps
    return crew - imps <= 1


# --- the crew vote ------------------------------------------------------------


def crew_vote_target(belief: Belief) -> str | None:
    """The state-aware crew vote target, or ``None`` to skip. See module docstring."""

    self_color = belief.self_color or belief.voting.self_marker_color
    ranked = sorted(
        ((color, p) for color, p in belief.suspicion.items() if color != self_color),
        key=lambda kv: kv[1],
        reverse=True,
    )

    # 1. Must-eject: one death from parity — any read beats a skip (even a flat field).
    if must_eject(belief):
        alive = _alive_candidate_colors(belief)
        living = [color for color, _ in ranked if not alive or color in alive]
        return living[0] if living else None

    # 2. Corroborated pile-on: ride the crowd's evidence below the tight bar.
    pileon = corroborated_pileon_target(belief)
    if pileon is not None:
        return pileon

    if not ranked:
        return None
    color, p = ranked[0]

    # 3. Comfortable bar (0.75) for a clear leader over a non-flat field.
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    clear_leader = p >= VOTE_LEAD_MIN_P and (p - runner_up) >= VOTE_LEAD_MARGIN
    if clear_leader and p >= COMFORTABLE_VOTE_PROBABILITY:
        return color

    # 4. Tight bar (unchanged fitted near-certainty).
    if p >= WEIGHTS_VOTE_PROBABILITY:
        return color
    return None


def corroborated_pileon_target(belief: Belief) -> str | None:
    """The leading target this meeting carrying a corroborated evidence-backed pile-on.

    A target qualifies when at least :data:`PILEON_MIN_ACCUSERS` distinct speakers —
    none of them us, none a confirmed (witnessed) imposter — accused it this meeting
    with an EVIDENCE-BACKED accusation (``evidence_kind`` other than ``"bare"``). Bare
    unsupported "<color> sus" assertions never recruit our vote — that is the disinfo
    channel. The target must be alive and not us. Ties break toward more accusers, then
    our own higher posterior.
    """

    meeting_id = belief.phase_start_tick
    self_color = belief.self_color or belief.voting.self_marker_color
    confirmed = witnessed_imposters(belief)
    alive = _alive_candidate_colors(belief)

    accusers_by_target: dict[str, set[str]] = {}
    for claim in belief.social_claims:
        if claim.meeting_id != meeting_id or claim.stance != "accuse":
            continue
        if claim.evidence_kind == _BARE_EVIDENCE_KIND:
            continue  # a bare "X sus" assertion is not evidence-backed
        speaker = claim.speaker_color
        if speaker is None or speaker == self_color or speaker in confirmed:
            continue
        for target in claim.targets:
            if target == self_color:
                continue
            if alive and target not in alive:
                continue
            accusers_by_target.setdefault(target, set()).add(speaker)

    candidates = [
        (len(accusers), belief.suspicion.get(target, 0.0), target)
        for target, accusers in accusers_by_target.items()
        if len(accusers) >= PILEON_MIN_ACCUSERS
    ]
    if not candidates:
        return None
    return max(candidates)[2]


# --- helpers ------------------------------------------------------------------


def _alive_candidate_colors(belief: Belief) -> set[str]:
    """Colors legal to vote by aliveness — candidate grid first, roster fallback.

    Empty only before any alive information exists; callers treat empty as "no
    constraint" so the policy still works in belief-only unit tests.
    """

    from_grid = {candidate.color for candidate in belief.voting.candidates if candidate.alive}
    if from_grid:
        return from_grid
    return {color for color, record in belief.roster.items() if record.life_status == "alive"}
