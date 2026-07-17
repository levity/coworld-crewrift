"""Social-deduction solver (env-gated: CREWBORG_SOLVER).

Models what the OTHER players assert via meeting chat and finds the imposter-assignment
most consistent with all the accusations. crewborg (self) is crew, so among the votable
players there are (at most) 2 imposters -> enumerate C(n,2) hypotheses and Bayesian-update
each per accusation: a CREW speaker tends to accuse a real imposter; an IMPOSTER speaker
deflects onto crew. Convergence (many accusers of X) and bifurcation (mutual accusations)
fall out for free. Reuses crewborg's spaCy accusation parser (chat_read/_chat_nlp).

Returns the color to vote+accuse iff its marginal P(imposter) clears CREWBORG_SOLVER_P and
clearly leads the field; else None (fall back to crewborg's normal behavior). Never raises.

v2 fuses crewborg's OWN hard observations into the enumeration:
- pins: players we directly witnessed killing/venting (P(imposter)=100% in field data,
  36/36) — hypotheses that exclude them are impossible, which turns every claim BY the
  pinned player into a near-certain deflection and sharpens partner inference;
- clears: players whose task completions we watched (field P(imposter) 15% vs 36% base)
  down-weight hypotheses containing them by CLEAR_LR.
It also exposes a veto (CREWBORG_SOLVER_VETO): crewborg's own would-vote target is
dropped when the fused marginal says the crowd evidence doesn't support it — offline,
would-votes at marginal >=0.65 were 89% imposters vs 29-53% below.
"""
from __future__ import annotations
import os, math
from itertools import combinations
from typing import Any

from crewborg.strategy.meeting import chat_nlp
from crewborg.strategy.meeting.chat_read import _accused_for
from crewborg.strategy.suspicion import witnessed_imposters

# mild, deliberately conservative likelihoods (tunable / fittable later)
P_HIT, P_MISS = 0.55, 0.12      # crew accuses imposter vs crew
P_DEFL, P_COVER = 0.45, 0.03    # imposter accuses crew vs (never) a teammate
CLEAR_LR = 0.31                 # odds factor for a watched-task player being imposter


def enabled() -> bool:
    return os.environ.get("CREWBORG_SOLVER", "").strip().lower() in {"1", "true", "yes", "on"}


def veto_enabled() -> bool:
    return os.environ.get("CREWBORG_SOLVER_VETO", "").strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _threshold() -> float:
    return _env_float("CREWBORG_SOLVER_P", 0.65)


def _margin() -> float:
    return _env_float("CREWBORG_SOLVER_MARGIN", 0.10)  # gap between the imposter pair and the 3rd player


def _veto_keep() -> float:
    return _env_float("CREWBORG_SOLVER_VETO_P", 0.65)


def _accusation_claims(belief: Any, votable: set[str]) -> list[tuple[str, str]] | None:
    nlp = chat_nlp.get_model()
    if nlp is None:  # spaCy not ready -> no chat signal (deliberately no keyword fallback)
        return None
    cache: dict[str, set[str]] = {}
    claims: list[tuple[str, str]] = []
    for ev in getattr(belief, "chat_log", []) or []:
        speaker = ev.speaker_color
        accused = _accused_for(ev.text or "", votable | ({speaker} if speaker else set()), nlp, cache)
        for target in accused:
            if target in votable and target != speaker:
                claims.append((speaker, target))
    return claims


def solve_marginals(
    votable: list[str],
    claims: list[tuple[str, str]],
    pins: frozenset[str] | set[str] = frozenset(),
    clears: frozenset[str] | set[str] = frozenset(),
) -> dict[str, float]:
    hyps = [frozenset(c) for c in combinations(votable, 2)]
    if pins:
        pinned = [h for h in hyps if set(pins) <= h] if len(pins) <= 2 else [h for h in hyps if h <= set(pins)]
        if pinned:  # inconsistent pins (shouldn't happen) -> fall back to the full space
            hyps = pinned
    logw = {h: sum(math.log(CLEAR_LR) for c in clears if c in h) for h in hyps}
    for speaker, target in claims:
        for h in hyps:
            s_imp = speaker in h
            t_imp = target in h
            p = (P_COVER if t_imp else P_DEFL) if s_imp else (P_HIT if t_imp else P_MISS)
            logw[h] += math.log(max(p, 1e-6))
    m = max(logw.values())
    ws = {h: math.exp(logw[h] - m) for h in hyps}
    tot = sum(ws.values()) or 1.0
    return {o: sum(w for h, w in ws.items() if o in h) / tot for o in votable}


def solver_report(belief: Any) -> dict:
    """Full diagnostics for one meeting: {fired, pick, top_p, second_p, n_claims, n_accusers}.
    ``pick`` is non-None only when the top marginal clears the threshold AND clearly leads."""
    out = {"fired": False, "pick": None, "top_p": None, "second_p": None, "n_claims": 0,
           "n_accusers": 0, "pins": [], "clears": [], "marginals": None, "vetoed": None}
    try:
        if not (enabled() or veto_enabled()):
            return out
        votable = list(getattr(belief, "suspicion", {}).keys())
        if len(votable) < 3:
            return out
        self_color = getattr(belief, "self_color", None)
        pins = {c for c in witnessed_imposters(belief) if c in votable and c != self_color}
        roster = getattr(belief, "roster", {}) or {}
        clears = {
            c for c in votable
            if c not in pins and getattr(roster.get(c), "tasks_completed_watched", 0) > 0
        }
        out["pins"] = sorted(pins)
        out["clears"] = sorted(clears)
        claims = _accusation_claims(belief, set(votable))
        if not claims:
            return out
        out["n_claims"] = len(claims)
        out["n_accusers"] = len({sp for sp, _ in claims})
        marg = solve_marginals(votable, claims, pins=pins, clears=clears)
        out["marginals"] = {c: round(p, 3) for c, p in marg.items()}
        ranked = sorted(marg.items(), key=lambda kv: -kv[1])
        out["top_p"] = round(ranked[0][1], 3)
        out["second_p"] = round(ranked[1][1], 3) if len(ranked) > 1 else 0.0
        # There are 2 imposters, so the top TWO marginals are both expected to be high
        # (they carry the mass: marginals sum to the imposter count). Gating on the #1-vs-#2
        # gap would make us abstain exactly when we've correctly nailed the pair. The
        # meaningful separation is the gap AFTER the pair — top-1 vs the 3rd-ranked player
        # (the leading crewmate). pick = top-1 (a witnessed-kill pin, if any, sits at 1.0
        # here and is the best possible vote).
        third = ranked[2][1] if len(ranked) > 2 else 0.0
        if enabled() and ranked[0][1] >= _threshold() and (ranked[0][1] - third) >= _margin():
            out["fired"] = True
            out["pick"] = ranked[0][0]
    except Exception:
        pass
    return out


def solver_pick(belief: Any) -> str | None:
    """The color to vote+accuse if the logic-table strongly implicates one, else None."""
    return solver_report(belief).get("pick")


def solver_vetoes(report: dict, target: str | None) -> bool:
    """True when crewborg's own would-vote ``target`` should be dropped: the fused
    marginal exists (there was chat signal) and sits below the keep bar, and the target
    is not hard-witnessed. Offline: kept votes 89% imposters, dropped ones 29-53%."""
    try:
        if not veto_enabled() or target is None:
            return False
        if target in (report.get("pins") or ()):
            return False
        marginals = report.get("marginals")
        if not marginals or target not in marginals:
            return False  # no chat signal -> leave crewborg's behavior unchanged
        return marginals[target] < _veto_keep()
    except Exception:
        return False
