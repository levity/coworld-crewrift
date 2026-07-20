"""Persistent joint-hypothesis social-deduction solver.

The solver is opt-in (``CREWBORG_SOLVER``). It enumerates every fixed-size
impostor assignment over the original roster, including dead players, then scores
each assignment against episode-persistent claims and public meeting votes.
Speaker reliability is role-conditioned inside the hypothesis: a likely crew
speaker is expected to identify impostors, while a likely impostor is expected to
deflect onto crew and avoid accusing a partner.

Repeated lines from the same attributed source about the same target collapse
within a meeting. Relays collapse by their original source and receive less
weight than direct assertions. Repetition across later meetings still contributes,
with configurable decay. Evidence wording, body reporters, direct observations,
and a tempered copy of crewborg's existing suspicion posterior provide additional
provenance.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Iterable

from crewborg.strategy.suspicion import witnessed_imposters
from crewborg.types import MeetingRecord, SocialClaim


@dataclass(frozen=True)
class SolverConfig:
    crew_accuse_hit: float = 0.58
    crew_accuse_miss: float = 0.15
    imp_accuse_crew: float = 0.42
    imp_accuse_partner: float = 0.08
    crew_defend_crew: float = 0.50
    crew_defend_imp: float = 0.08
    imp_defend_crew: float = 0.16
    imp_defend_partner: float = 0.34
    crew_vote_imp: float = 0.48
    crew_vote_crew: float = 0.18
    imp_vote_crew: float = 0.38
    imp_vote_partner: float = 0.08
    clear_lr: float = 0.31
    prior_strength: float = 0.20
    repeat_decay: float = 0.70
    vote_weight: float = 0.35
    reporter_weight: float = 1.15
    bare_weight: float = 0.25
    body_weight: float = 1.00
    vent_weight: float = 1.10
    sighting_weight: float = 0.85
    claimed_vote_weight: float = 0.50
    relay_weight: float = 0.45


@dataclass(frozen=True)
class WeightedClaim:
    claim: SocialClaim
    weight: float


def enabled() -> bool:
    return os.environ.get("CREWBORG_SOLVER", "").strip().lower() in {"1", "true", "yes", "on"}


def veto_enabled() -> bool:
    return os.environ.get("CREWBORG_SOLVER_VETO", "").strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _config() -> SolverConfig:
    defaults = SolverConfig()
    values = {
        field: _env_float(f"CREWBORG_SOLVER_{field.upper()}", getattr(defaults, field))
        for field in SolverConfig.__dataclass_fields__
    }
    return SolverConfig(**values)


def _threshold() -> float:
    return _env_float("CREWBORG_SOLVER_P", 0.65)


def _margin() -> float:
    return _env_float("CREWBORG_SOLVER_MARGIN", 0.10)


def _veto_keep() -> float:
    return _env_float("CREWBORG_SOLVER_VETO_P", 0.65)


def _imposter_count(belief: Any) -> int:
    configured = getattr(belief, "imposter_count", None)
    if configured is not None:
        return configured
    total = getattr(belief, "total_player_count", 0)
    return 0 if total < 5 else max(0, min((total - 3) // 2, total - 1))


def _evidence_weight(claim: SocialClaim, config: SolverConfig) -> float:
    return {
        "bare": config.bare_weight,
        "body": config.body_weight,
        "vent": config.vent_weight,
        "sighting": config.sighting_weight,
        "vote": config.claimed_vote_weight,
    }.get(claim.evidence_kind, config.bare_weight)


def _weighted_claims(
    claims: Iterable[SocialClaim],
    meetings: Iterable[MeetingRecord],
    players: set[str],
    config: SolverConfig,
) -> list[WeightedClaim]:
    """Deduplicate per meeting/original-source/target and decay later repeats."""

    reporters = {
        meeting.meeting_id: meeting.caller_color
        for meeting in meetings
        if meeting.call_kind == "body"
    }
    best: dict[tuple[int, str, str, tuple[str, ...]], tuple[SocialClaim, float]] = {}
    for claim in claims:
        source = claim.source_color or claim.speaker_color
        targets = tuple(sorted(set(claim.targets)))
        if source not in players or not targets or source in targets:
            continue
        if any(target not in players for target in targets):
            continue
        weight = _evidence_weight(claim, config)
        if claim.provenance == "relayed":
            weight *= config.relay_weight
        if (
            claim.provenance == "direct"
            and reporters.get(claim.meeting_id) == source
            and claim.speaker_color == source
        ):
            weight *= config.reporter_weight
        key = (claim.meeting_id, source, claim.stance, targets)
        previous = best.get(key)
        if previous is None or weight > previous[1]:
            best[key] = (
                claim.model_copy(update={"source_color": source, "targets": targets}),
                weight,
            )

    repeated: dict[tuple[str, str, tuple[str, ...]], int] = {}
    weighted: list[WeightedClaim] = []
    for claim, base_weight in sorted(best.values(), key=lambda item: (item[0].meeting_id, item[0].tick)):
        identity = (claim.source_color or claim.speaker_color or "", claim.stance, claim.targets)
        repeat_index = repeated.get(identity, 0)
        repeated[identity] = repeat_index + 1
        weighted.append(
            WeightedClaim(
                claim=claim,
                weight=base_weight * (config.repeat_decay ** repeat_index),
            )
        )
    return weighted


def _actor_claim_probability(
    hypothesis: frozenset[str],
    actor: str | None,
    claim: SocialClaim,
    config: SolverConfig,
) -> float:
    actor_is_imp = actor in hypothesis
    target_is_imp = any(target in hypothesis for target in claim.targets)
    if claim.stance in {"accuse", "at_least_one"}:
        if actor_is_imp:
            return config.imp_accuse_partner if target_is_imp else config.imp_accuse_crew
        return config.crew_accuse_hit if target_is_imp else config.crew_accuse_miss
    if actor_is_imp:
        return config.imp_defend_partner if target_is_imp else config.imp_defend_crew
    return config.crew_defend_imp if target_is_imp else config.crew_defend_crew


def _claim_probability(hypothesis: frozenset[str], claim: SocialClaim, config: SolverConfig) -> float:
    source = claim.source_color or claim.speaker_color
    probability = _actor_claim_probability(hypothesis, source, claim, config)
    if (
        claim.provenance == "relayed"
        and claim.speaker_color is not None
        and claim.speaker_color != source
    ):
        # A relay can be false because the attributed source lied or because the
        # current speaker fabricated the attribution. Require both actors to be
        # plausible under the hypothesis instead of laundering trust through a
        # named crewmate.
        speaker_probability = _actor_claim_probability(
            hypothesis,
            claim.speaker_color,
            claim,
            config,
        )
        probability = math.sqrt(probability * speaker_probability)
    return probability


def _vote_probability(
    hypothesis: frozenset[str],
    voter: str,
    target: str,
    config: SolverConfig,
) -> float:
    voter_is_imp = voter in hypothesis
    target_is_imp = target in hypothesis
    if voter_is_imp:
        return config.imp_vote_partner if target_is_imp else config.imp_vote_crew
    return config.crew_vote_imp if target_is_imp else config.crew_vote_crew


def _logit(probability: float) -> float:
    probability = min(max(probability, 0.01), 0.99)
    return math.log(probability / (1.0 - probability))


def solve_hypotheses(
    players: list[str],
    imposter_count: int,
    claims: Iterable[SocialClaim],
    meetings: Iterable[MeetingRecord] = (),
    *,
    pins: frozenset[str] | set[str] = frozenset(),
    clears: frozenset[str] | set[str] = frozenset(),
    priors: dict[str, float] | None = None,
    config: SolverConfig | None = None,
) -> dict[str, Any]:
    """Return normalized joint hypotheses, marginals, and evidence counts."""

    config = config or _config()
    players = list(dict.fromkeys(players))
    player_set = set(players)
    if imposter_count <= 0 or imposter_count > len(players):
        return {"marginals": {}, "hypotheses": [], "n_claims": 0, "n_votes": 0}

    hypotheses = [
        frozenset(combo)
        for combo in combinations(players, imposter_count)
        if set(pins) <= set(combo)
    ]
    if not hypotheses:
        return {"marginals": {}, "hypotheses": [], "n_claims": 0, "n_votes": 0}

    meeting_list = list(meetings)
    weighted_claims = _weighted_claims(claims, meeting_list, player_set, config)
    public_votes = [
        (voter, target)
        for meeting in meeting_list
        for voter, target in meeting.votes.items()
        if voter in player_set and target in player_set and voter != target
    ]
    base_probability = imposter_count / len(players)
    log_weights: dict[frozenset[str], float] = {}
    for hypothesis in hypotheses:
        log_weight = sum(
            math.log(max(config.clear_lr, 1e-6))
            for color in clears
            if color in hypothesis
        )
        for color, probability in (priors or {}).items():
            if color in hypothesis and color in player_set:
                log_weight += config.prior_strength * (
                    _logit(probability) - _logit(base_probability)
                )
        for weighted in weighted_claims:
            probability = _claim_probability(hypothesis, weighted.claim, config)
            log_weight += weighted.weight * math.log(max(probability, 1e-6))
        for voter, target in public_votes:
            probability = _vote_probability(hypothesis, voter, target, config)
            log_weight += config.vote_weight * math.log(max(probability, 1e-6))
        log_weights[hypothesis] = log_weight

    maximum = max(log_weights.values())
    unnormalized = {
        hypothesis: math.exp(log_weight - maximum)
        for hypothesis, log_weight in log_weights.items()
    }
    total = sum(unnormalized.values()) or 1.0
    probabilities = {
        hypothesis: weight / total
        for hypothesis, weight in unnormalized.items()
    }
    marginals = {
        player: sum(probability for hypothesis, probability in probabilities.items() if player in hypothesis)
        for player in players
    }
    ranked_hypotheses = sorted(probabilities.items(), key=lambda item: -item[1])
    return {
        "marginals": marginals,
        "hypotheses": [
            {"imposters": sorted(hypothesis), "p": probability}
            for hypothesis, probability in ranked_hypotheses
        ],
        "n_claims": len(weighted_claims),
        "n_votes": len(public_votes),
    }


def solve_marginals(
    votable: list[str],
    claims: list[tuple[str, str]],
    pins: frozenset[str] | set[str] = frozenset(),
    clears: frozenset[str] | set[str] = frozenset(),
) -> dict[str, float]:
    """Compatibility wrapper for the original pair-claim solver API."""

    structured = [
        SocialClaim(
            meeting_id=0,
            tick=index,
            speaker_color=speaker,
            targets=(target,),
            stance="accuse",
            evidence_kind="body",
            text=f"{target} accused",
        )
        for index, (speaker, target) in enumerate(claims)
    ]
    result = solve_hypotheses(
        votable,
        min(2, len(votable)),
        structured,
        pins=pins,
        clears=clears,
        config=SolverConfig(prior_strength=0.0, repeat_decay=1.0),
    )
    return result["marginals"]


def _live_vote_targets(belief: Any, players: set[str]) -> list[str]:
    candidates = [
        candidate.color
        for candidate in getattr(getattr(belief, "voting", None), "candidates", ())
        if candidate.alive and candidate.color in players and candidate.color != belief.self_color
    ]
    if candidates:
        return candidates
    return [
        color
        for color, record in (getattr(belief, "roster", {}) or {}).items()
        if color in players
        and color != getattr(belief, "self_color", None)
        and getattr(record, "life_status", "unknown") != "dead"
    ]


def solver_report(belief: Any) -> dict[str, Any]:
    """Build serializable diagnostics and, when decisive, a live vote target."""

    out: dict[str, Any] = {
        "fired": False,
        "pick": None,
        "top_p": None,
        "second_p": None,
        "n_claims": 0,
        "n_raw_claims": 0,
        "n_accusers": 0,
        "n_votes": 0,
        "n_meetings": 0,
        "pins": [],
        "clears": [],
        "marginals": None,
        "hypotheses": [],
        "vetoed": None,
        "error": None,
    }
    try:
        if not (enabled() or veto_enabled()):
            return out
        self_color = getattr(belief, "self_color", None)
        roster = getattr(belief, "roster", {}) or {}
        players = [color for color in roster if color != self_color]
        imposter_count = _imposter_count(belief)
        if len(players) < 2 or imposter_count <= 0:
            return out

        player_set = set(players)
        pins = witnessed_imposters(belief) & player_set
        clears = {
            color
            for color, record in roster.items()
            if color in player_set
            and color not in pins
            and getattr(record, "tasks_completed_watched", 0) > 0
        }
        claims = list(getattr(belief, "social_claims", ()) or ())
        meetings = list(getattr(belief, "meeting_history", ()) or ())
        priors = {
            color: probability
            for color, probability in (getattr(belief, "suspicion", {}) or {}).items()
            if color in player_set
        }
        result = solve_hypotheses(
            players,
            imposter_count,
            claims,
            meetings,
            pins=pins,
            clears=clears,
            priors=priors,
        )
        marginals = result["marginals"]
        if not marginals:
            return out

        out.update(
            n_claims=result["n_claims"],
            n_raw_claims=len(claims),
            n_accusers=len(
                {
                    claim.source_color or claim.speaker_color
                    for claim in claims
                    if (claim.source_color or claim.speaker_color) in player_set
                }
            ),
            n_votes=result["n_votes"],
            n_meetings=len(meetings),
            pins=sorted(pins),
            clears=sorted(clears),
            marginals={color: round(probability, 3) for color, probability in marginals.items()},
            hypotheses=[
                {"imposters": item["imposters"], "p": round(item["p"], 4)}
                for item in result["hypotheses"][:5]
            ],
        )

        live = _live_vote_targets(belief, player_set)
        ranked = sorted(
            ((color, marginals[color]) for color in live if color in marginals),
            key=lambda item: (-item[1], item[0]),
        )
        if not ranked:
            return out
        out["top_p"] = round(ranked[0][1], 3)
        out["second_p"] = round(ranked[1][1], 3) if len(ranked) > 1 else 0.0

        threshold = _threshold()
        competitor = ranked[imposter_count][1] if len(ranked) > imposter_count else 0.0
        has_relational_evidence = bool(result["n_claims"] or result["n_votes"] or pins)
        if (
            enabled()
            and has_relational_evidence
            and ranked[0][1] >= threshold
            and ranked[0][1] - competitor >= _margin()
        ):
            out["fired"] = True
            out["pick"] = ranked[0][0]
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def solver_pick(belief: Any) -> str | None:
    return solver_report(belief).get("pick")


def solver_vetoes(report: dict[str, Any], target: str | None) -> bool:
    """Whether joint social evidence is strong enough to reject a base-policy vote."""

    try:
        if not veto_enabled() or target is None:
            return False
        if target in (report.get("pins") or ()):
            return False
        marginals = report.get("marginals")
        if not marginals or target not in marginals:
            return False
        return marginals[target] < _veto_keep()
    except Exception:
        return False
