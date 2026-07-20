"""Persistent joint-hypothesis social-deduction solver.

The solver is opt-in (``CREWBORG_SOLVER``). It enumerates every fixed-size
impostor assignment over the original roster, including dead players, then scores
each assignment against episode-persistent claims and public meeting votes.
Speaker reliability is role-conditioned inside the hypothesis: a likely crew
speaker is expected to identify impostors, while a likely impostor is expected to
deflect onto crew and avoid accusing a partner.

Repeated lines from the same attributed source about the same target collapse
within a meeting. Relays collapse by their original source and receive less
weight than direct assertions. Additional speakers making the same claim within
one meeting receive diminishing weight because relays and bandwagons are
correlated, while later meetings still contribute independently. Repetition by
the same source or voter-target pair across later meetings has a separate
configurable decay. Evidence wording, body reporters, direct observations, and a
tempered copy of crewborg's existing suspicion posterior provide additional
provenance.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, replace
from itertools import combinations
from typing import Any, Iterable

from crewborg.strategy.alibi import alibi_events, alibi_sets
from crewborg.strategy.suspicion import witnessed_imposters
from crewborg.types import KillAlibi, MeetingRecord, SocialClaim


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
    same_target_decay: float = 0.80
    vote_repeat_decay: float = 0.70
    vote_weight: float = 0.35
    reporter_weight: float = 1.15
    bare_weight: float = 0.25
    body_weight: float = 1.00
    vent_weight: float = 1.10
    sighting_weight: float = 0.85
    claimed_vote_weight: float = 0.50
    relay_weight: float = 0.45
    # Retained histories show strong killer specialization: the non-killing
    # impostor often stays with crew. Keep soft "not this killer" evidence inert
    # unless a future calibrated model explicitly opts in.
    alibi_weight: float = 0.0


@dataclass(frozen=True)
class WeightedClaim:
    claim: SocialClaim
    weight: float


@dataclass(frozen=True)
class WeightedVote:
    meeting_id: int
    voter: str
    target: str
    weight: float


@dataclass(frozen=True)
class SolverEvidence:
    """All evidence channels supplied to one joint solve."""

    claims: tuple[SocialClaim, ...] = ()
    meetings: tuple[MeetingRecord, ...] = ()
    pins: frozenset[str] = frozenset()
    hard_clears: frozenset[str] = frozenset()
    clears: frozenset[str] = frozenset()
    alibis: tuple[KillAlibi, ...] = ()
    # Compatibility for callers/tests that predate the complete KillAlibi
    # ledger. Runtime inference supplies ``alibis`` instead.
    alibi_groups: tuple[frozenset[str], ...] = ()
    priors: tuple[tuple[str, float], ...] = ()


def enabled() -> bool:
    return os.environ.get("CREWBORG_SOLVER", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def veto_enabled() -> bool:
    return os.environ.get("CREWBORG_SOLVER_VETO", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def defer_enabled() -> bool:
    """Whether to delay the legacy crew vote for a solver timing control."""

    return os.environ.get("CREWBORG_SOLVER_DEFER", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def early_chat_enabled() -> bool:
    return os.environ.get("CREWBORG_SOLVER_EARLY_CHAT", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
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


def _robust_threshold() -> float:
    return _env_float("CREWBORG_SOLVER_ROBUST_P", 0.0)


def _robust_max_threshold() -> float:
    return _env_float("CREWBORG_SOLVER_ROBUST_MAX_P", 0.39)


def _veto_keep() -> float:
    return _env_float("CREWBORG_SOLVER_VETO_P", 0.65)


def early_chat_offset_ticks() -> int:
    return max(0, _env_int("CREWBORG_SOLVER_EARLY_CHAT_TICKS", 240))


def early_vote_offset_ticks() -> int:
    return max(0, _env_int("CREWBORG_SOLVER_EARLY_VOTE_TICKS", 360))


def early_chat_pick(
    report: dict[str, Any],
    *,
    supporting_sources: list[str],
) -> str | None:
    """Return a replay-calibrated public solve suitable for early chat."""

    target = report.get("pick")
    if target is None:
        return None
    if (report.get("top_p") or 0.0) < _env_float(
        "CREWBORG_SOLVER_EARLY_CHAT_P", 0.65
    ):
        return None
    min_sources = max(
        1,
        _env_int("CREWBORG_SOLVER_EARLY_CHAT_MIN_SOURCES", 2),
    )
    if len(supporting_sources) < min_sources:
        return None
    return target


def public_source_backed_pick(report: dict[str, Any]) -> str | None:
    """Return a decisive public target that has an attributed accusation source."""

    target = report.get("pick")
    if target is None or not report.get("candidate_sources"):
        return None
    return target


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
    """Deduplicate source claims and discount correlated same-meeting consensus."""

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

    ordered = sorted(
        best.values(),
        key=lambda item: (
            item[0].meeting_id,
            item[0].stance,
            item[0].targets,
            -item[1],
            item[0].tick,
            item[0].source_color or item[0].speaker_color or "",
        ),
    )
    repeated: dict[tuple[str, str, tuple[str, ...]], int] = {}
    same_target: dict[tuple[int, str, tuple[str, ...]], int] = {}
    weighted: list[WeightedClaim] = []
    for claim, base_weight in ordered:
        identity = (
            claim.source_color or claim.speaker_color or "",
            claim.stance,
            claim.targets,
        )
        repeat_index = repeated.get(identity, 0)
        repeated[identity] = repeat_index + 1
        target_identity = (claim.meeting_id, claim.stance, claim.targets)
        target_index = same_target.get(target_identity, 0)
        same_target[target_identity] = target_index + 1
        weighted.append(
            WeightedClaim(
                claim=claim,
                weight=(
                    base_weight
                    * (config.repeat_decay**repeat_index)
                    * (config.same_target_decay**target_index)
                ),
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
            return (
                config.imp_accuse_partner if target_is_imp else config.imp_accuse_crew
            )
        return config.crew_accuse_hit if target_is_imp else config.crew_accuse_miss
    if actor_is_imp:
        return config.imp_defend_partner if target_is_imp else config.imp_defend_crew
    return config.crew_defend_imp if target_is_imp else config.crew_defend_crew


def _claim_probability(
    hypothesis: frozenset[str], claim: SocialClaim, config: SolverConfig
) -> float:
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


def _weighted_votes(
    meetings: Iterable[MeetingRecord],
    players: set[str],
    config: SolverConfig,
) -> list[WeightedVote]:
    """Decay repeated voter-target pairs across meetings."""

    repeated: dict[tuple[str, str], int] = {}
    weighted_votes: list[WeightedVote] = []
    for meeting in sorted(meetings, key=lambda item: item.meeting_id):
        for voter, target in sorted(meeting.votes.items()):
            if voter not in players or target not in players or voter == target:
                continue
            identity = (voter, target)
            repeat_index = repeated.get(identity, 0)
            repeated[identity] = repeat_index + 1
            weight = config.vote_weight * (config.vote_repeat_decay**repeat_index)
            if weight <= 0:
                continue
            weighted_votes.append(
                WeightedVote(
                    meeting_id=meeting.meeting_id,
                    voter=voter,
                    target=target,
                    weight=weight,
                )
            )
    return weighted_votes


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
    hard_clears: frozenset[str] | set[str] = frozenset(),
    clears: frozenset[str] | set[str] = frozenset(),
    alibis: Iterable[KillAlibi] = (),
    alibi_groups: Iterable[frozenset[str] | set[str]] = (),
    priors: dict[str, float] | None = None,
    config: SolverConfig | None = None,
) -> dict[str, Any]:
    """Return normalized joint hypotheses and an auditable contribution table.

    Each ``KillAlibi`` is evaluated against assignment members who were alive
    and able to perform that kill. Production uses only the hard consequence:
    an assignment with no possible perpetrator is excluded. The optional soft
    weight remains zero by default because "not this killer" did not calibrate
    as evidence of crew. ``alibi_groups`` is a compatibility input lacking
    timing/alive context and assumes every player was eligible for its synthetic
    kill.
    """

    config = config or _config()
    players = list(dict.fromkeys(players))
    player_set = set(players)

    def _empty(pair_audit: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        return {
            "marginals": {},
            "hypotheses": [],
            "n_claims": 0,
            "n_votes": 0,
            "n_alibis": 0,
            "pair_audit": pair_audit or [],
            "distrusted_alibis": [],
        }

    if imposter_count <= 0 or imposter_count > len(players):
        return _empty()

    alibi_list = list(alibis)
    for index, group in enumerate(alibi_groups):
        colors = tuple(sorted(set(group) & player_set))
        if not colors:
            continue
        alibi_list.append(
            KillAlibi(
                observer_color="legacy",
                victim_color=f"legacy-{index}",
                death_source="census",
                death_seen_tick=-(index + 1),
                window_start_tick=-(index + 1),
                window_end_tick=-(index + 1),
                alibied_colors=colors,
                possible_killers=tuple(players),
            )
        )

    def _alibi_id(event: KillAlibi) -> str:
        return (
            f"alibi:{event.observer_color}:{event.victim_color}:"
            f"{event.death_seen_tick}:{event.window_start_tick}:{event.window_end_tick}"
        )

    pinned = set(pins)
    cleared = set(hard_clears)
    all_hypotheses = [
        frozenset(combo) for combo in combinations(players, imposter_count)
    ]
    exclusion_reasons: dict[frozenset[str], list[str]] = {
        hypothesis: [] for hypothesis in all_hypotheses
    }
    hypotheses: list[frozenset[str]] = []
    for hypothesis in all_hypotheses:
        if not pinned <= hypothesis:
            exclusion_reasons[hypothesis].append("missing_pin")
        if hypothesis & cleared:
            exclusion_reasons[hypothesis].append("hard_clear")
        if not exclusion_reasons[hypothesis]:
            hypotheses.append(hypothesis)
    if not hypotheses:
        return _empty(
            [
                {
                    "imposters": sorted(hypothesis),
                    "eligible": False,
                    "exclusion_reasons": exclusion_reasons[hypothesis],
                    "log_weight": None,
                    "contributions": [],
                }
                for hypothesis in all_hypotheses
            ]
        )

    impossible_by_alibi: dict[frozenset[str], list[str]] = {}
    for hypothesis in hypotheses:
        reasons = []
        for event in alibi_list:
            eligible_impostors = hypothesis & set(event.possible_killers)
            possible_perpetrators = eligible_impostors - set(event.alibied_colors)
            # The only assumption-free consequence is relational: an assignment
            # is impossible when none of its eligible members could have made
            # this kill. A singleton alibi alone is not a player clear, but it
            # can combine with an independent ineligibility constraint.
            if not possible_perpetrators:
                reasons.append(_alibi_id(event))
        if reasons:
            impossible_by_alibi[hypothesis] = reasons

    # A sound kill observation cannot disprove every structurally possible
    # assignment. If the ledger appears to do so, retain it for diagnostics but
    # ignore the entire alibi channel for this solve.
    surviving = [
        hypothesis
        for hypothesis in hypotheses
        if hypothesis not in impossible_by_alibi
    ]
    distrusted_alibis: list[str] = []
    if surviving:
        hypotheses = surviving
        for hypothesis, reasons in impossible_by_alibi.items():
            exclusion_reasons[hypothesis].extend(reasons)
    elif alibi_list:
        distrusted_alibis = [_alibi_id(event) for event in alibi_list]
        alibi_list = []

    meeting_list = list(meetings)
    weighted_claims = _weighted_claims(claims, meeting_list, player_set, config)
    weighted_votes = _weighted_votes(
        meeting_list,
        player_set,
        config,
    )
    base_probability = imposter_count / len(players)
    log_weights: dict[frozenset[str], float] = {}
    contributions: dict[frozenset[str], list[dict[str, Any]]] = {}
    for hypothesis in hypotheses:
        log_weight = 0.0
        hypothesis_contributions: list[dict[str, Any]] = []

        def _record(
            evidence_id: str,
            channel: str,
            delta: float,
            *,
            likelihood: float | None = None,
            weight: float | None = None,
        ) -> None:
            nonlocal log_weight
            log_weight += delta
            item: dict[str, Any] = {
                "evidence_id": evidence_id,
                "channel": channel,
                "delta": delta,
            }
            if likelihood is not None:
                item["likelihood"] = likelihood
            if weight is not None:
                item["weight"] = weight
            hypothesis_contributions.append(item)

        for color in sorted(clears):
            if color in hypothesis:
                likelihood = max(config.clear_lr, 1e-6)
                _record(
                    f"clear:{color}",
                    "clear",
                    math.log(likelihood),
                    likelihood=likelihood,
                    weight=1.0,
                )
        for color, probability in (priors or {}).items():
            if color in hypothesis and color in player_set:
                delta = config.prior_strength * (
                    _logit(probability) - _logit(base_probability)
                )
                _record(
                    f"prior:{color}",
                    "prior",
                    delta,
                    likelihood=probability,
                    weight=config.prior_strength,
                )
        for weighted in weighted_claims:
            probability = _claim_probability(hypothesis, weighted.claim, config)
            delta = weighted.weight * math.log(max(probability, 1e-6))
            claim = weighted.claim
            source = claim.source_color or claim.speaker_color or "unknown"
            targets = ",".join(claim.targets)
            _record(
                (
                    f"claim:{claim.meeting_id}:{claim.tick}:{source}:"
                    f"{claim.stance}:{targets}"
                ),
                "claim",
                delta,
                likelihood=probability,
                weight=weighted.weight,
            )
        for weighted in weighted_votes:
            probability = _vote_probability(
                hypothesis,
                weighted.voter,
                weighted.target,
                config,
            )
            delta = weighted.weight * math.log(max(probability, 1e-6))
            _record(
                (
                    f"vote:{weighted.meeting_id}:{weighted.voter}:"
                    f"{weighted.target}"
                ),
                "vote",
                delta,
                likelihood=probability,
                weight=weighted.weight,
            )
        for event in alibi_list:
            eligible_impostors = hypothesis & set(event.possible_killers)
            possible_perpetrators = eligible_impostors - set(event.alibied_colors)
            likelihood = (
                len(possible_perpetrators) / len(eligible_impostors)
                if eligible_impostors
                else 0.0
            )
            delta = (
                config.alibi_weight * math.log(likelihood)
                if config.alibi_weight > 0.0 and likelihood > 0.0
                else 0.0
            )
            _record(
                _alibi_id(event),
                "alibi",
                delta,
                likelihood=likelihood,
                weight=config.alibi_weight,
            )
        log_weights[hypothesis] = log_weight
        contributions[hypothesis] = hypothesis_contributions

    maximum = max(log_weights.values())
    unnormalized = {
        hypothesis: math.exp(log_weight - maximum)
        for hypothesis, log_weight in log_weights.items()
    }
    total = sum(unnormalized.values()) or 1.0
    probabilities = {
        hypothesis: weight / total for hypothesis, weight in unnormalized.items()
    }
    marginals = {
        player: sum(
            probability
            for hypothesis, probability in probabilities.items()
            if player in hypothesis
        )
        for player in players
    }
    ranked_hypotheses = sorted(probabilities.items(), key=lambda item: -item[1])
    pair_audit = []
    for hypothesis in all_hypotheses:
        eligible = hypothesis in log_weights
        pair_audit.append(
            {
                "imposters": sorted(hypothesis),
                "eligible": eligible,
                "exclusion_reasons": exclusion_reasons[hypothesis],
                "log_weight": log_weights.get(hypothesis),
                "contributions": contributions.get(hypothesis, []),
            }
        )
    return {
        "marginals": marginals,
        "hypotheses": [
            {"imposters": sorted(hypothesis), "p": probability}
            for hypothesis, probability in ranked_hypotheses
        ],
        "n_claims": len(weighted_claims),
        "n_votes": len(weighted_votes),
        "n_alibis": len(alibi_list),
        "pair_audit": pair_audit,
        "distrusted_alibis": distrusted_alibis,
    }


def _solve_evidence(
    players: list[str],
    imposter_count: int,
    evidence: SolverEvidence,
) -> dict[str, Any]:
    """Solve one immutable evidence bundle without dropping a channel at call sites."""

    return solve_hypotheses(
        players,
        imposter_count,
        evidence.claims,
        evidence.meetings,
        pins=evidence.pins,
        hard_clears=evidence.hard_clears,
        clears=evidence.clears,
        alibis=evidence.alibis,
        alibi_groups=evidence.alibi_groups,
        priors=dict(evidence.priors),
    )


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
        if candidate.alive
        and candidate.color in players
        and candidate.color != belief.self_color
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


def _without_actor(
    *,
    actor: str,
    candidate: str,
    players: list[str],
    live: list[str],
    imposter_count: int,
    evidence: SolverEvidence,
) -> dict[str, Any]:
    """Measure how much of a single-source pick survives source removal."""

    filtered_claims = [
        claim
        for claim in evidence.claims
        if actor
        not in {
            claim.source_color or claim.speaker_color,
            claim.speaker_color,
        }
    ]
    filtered_meetings = [
        meeting.model_copy(
            update={
                "votes": {
                    voter: target
                    for voter, target in meeting.votes.items()
                    if voter != actor
                }
            }
        )
        for meeting in evidence.meetings
    ]
    filtered = replace(
        evidence,
        claims=tuple(filtered_claims),
        meetings=tuple(filtered_meetings),
    )
    result = _solve_evidence(players, imposter_count, filtered)
    marginals = result["marginals"]
    ranked = sorted(
        ((color, marginals[color]) for color in live if color in marginals),
        key=lambda item: (-item[1], item[0]),
    )
    candidate_p = marginals.get(candidate, 0.0)
    top = ranked[0][0] if ranked else None
    competitor = ranked[imposter_count][1] if len(ranked) > imposter_count else 0.0
    margin = candidate_p - competitor

    # The upper cap protects against correlated social consensus, not independent
    # physical facts. Measure it with the actor removed and structural/private
    # channels absent, while the survival check above preserves every other fact.
    crowd_only = replace(
        filtered,
        pins=frozenset(),
        hard_clears=frozenset(),
        clears=frozenset(),
        alibis=(),
        alibi_groups=(),
        priors=(),
    )
    crowd_result = _solve_evidence(players, imposter_count, crowd_only)
    crowd_p = crowd_result["marginals"].get(candidate, 0.0)
    min_threshold = _robust_threshold()
    max_threshold = _robust_max_threshold()
    survives_removal = min_threshold < 0 or (
        top == candidate and candidate_p >= min_threshold and margin >= 0.0
    )
    crowd_is_bounded = max_threshold < 0 or crowd_p <= max_threshold
    return {
        "passed": survives_removal and crowd_is_bounded,
        "min_p": candidate_p,
        "min_margin": margin,
        "crowd_p": crowd_p,
        "weakest_actor": actor,
    }


def _constraint_decisive(
    *,
    candidate: str,
    players: list[str],
    live: list[str],
    imposter_count: int,
    evidence: SolverEvidence,
) -> dict[str, Any]:
    """Whether structural facts are necessary for this candidate to be decisive."""

    structural_channels = [
        name
        for name, present in (
            ("pins", bool(evidence.pins)),
            ("hard_clears", bool(evidence.hard_clears)),
            ("clears", bool(evidence.clears)),
            ("alibis", bool(evidence.alibis or evidence.alibi_groups)),
        )
        if present
    ]
    if not structural_channels:
        return {
            "passed": False,
            "channels": [],
            "without_p": None,
            "without_margin": None,
            "without_top": None,
        }

    without_constraints = replace(
        evidence,
        pins=frozenset(),
        hard_clears=frozenset(),
        clears=frozenset(),
        alibis=(),
        alibi_groups=(),
    )
    result = _solve_evidence(players, imposter_count, without_constraints)
    marginals = result["marginals"]
    ranked = sorted(
        ((color, marginals[color]) for color in live if color in marginals),
        key=lambda item: (-item[1], item[0]),
    )
    without_top = ranked[0][0] if ranked else None
    without_p = marginals.get(candidate, 0.0)
    competitor = ranked[imposter_count][1] if len(ranked) > imposter_count else 0.0
    without_margin = without_p - competitor
    still_decisive = (
        without_top == candidate
        and without_p >= _threshold()
        and without_margin >= _margin()
    )
    return {
        "passed": not still_decisive,
        "channels": structural_channels,
        "without_p": without_p,
        "without_margin": without_margin,
        "without_top": without_top,
    }


def _constraint_forces_candidate(
    *,
    candidate: str,
    players: list[str],
    imposter_count: int,
    evidence: SolverEvidence,
) -> dict[str, Any]:
    """Whether hard structural facts put the candidate in every surviving assignment."""

    structural_only = replace(
        evidence,
        claims=(),
        meetings=(),
        # ``clears`` are weighted evidence, not logical exclusions.
        clears=frozenset(),
        priors=(),
    )
    result = _solve_evidence(players, imposter_count, structural_only)
    hypotheses = result["hypotheses"]
    return {
        "passed": bool(hypotheses)
        and all(candidate in hypothesis["imposters"] for hypothesis in hypotheses),
        "n_hypotheses": len(hypotheses),
    }


def _solver_report(belief: Any, *, public_only: bool) -> dict[str, Any]:
    """Build serializable diagnostics and, when decisive, a live vote target."""

    out: dict[str, Any] = {
        "fired": False,
        "pick": None,
        "top_p": None,
        "second_p": None,
        "n_claims": 0,
        "n_raw_claims": 0,
        "n_self_claims_ignored": 0,
        "n_accusers": 0,
        "n_votes": 0,
        "n_alibis": 0,
        "n_meetings": 0,
        "pins": [],
        "hard_clears": [],
        "clears": [],
        "alibi_groups": [],
        "alibi_events": [],
        "distrusted_alibis": [],
        "hypothesis_audit": [],
        "excluded_hypotheses": [],
        "marginals": None,
        "hypotheses": [],
        "top_candidate": None,
        "pre_robust_pick": None,
        "candidate_sources": [],
        "robust_required": False,
        "robust_min_p": None,
        "robust_min_margin": None,
        "robust_crowd_p": None,
        "robust_weakest_actor": None,
        "constraint_decisive": False,
        "constraint_forced": False,
        "structural_hypotheses": None,
        "constraint_channels": [],
        "without_constraints_p": None,
        "without_constraints_margin": None,
        "without_constraints_top": None,
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
        pins = set() if public_only else witnessed_imposters(belief) & player_set
        clears: set[str] = set()
        # Co-presence observations are per kill, never player clears. The solver
        # retains partial events for audit and excludes only an assignment whose
        # entire impostor set was close for the same hidden kill.
        complete_alibis = (
            []
            if public_only
            else [
                event.model_copy(
                    update={
                        "alibied_colors": tuple(
                            sorted(set(event.alibied_colors) & player_set)
                        ),
                        "possible_killers": tuple(
                            sorted(set(event.possible_killers) & player_set)
                        ),
                    }
                )
                for event in alibi_events(belief)
            ]
        )
        # Compatibility for tests and hot-reloaded state from the set-only
        # implementation. Fresh runtime state always uses complete events.
        legacy_alibis = (
            []
            if public_only or complete_alibis
            else [group & player_set for group in alibi_sets(belief)]
        )
        raw_claims = list(getattr(belief, "social_claims", ()) or ())
        # Our own prior solver/chat output is derived from evidence already in this
        # ledger. Re-ingesting it would turn one conclusion into a new independent
        # source on later meetings.
        claims = [
            claim for claim in raw_claims if claim.speaker_color != self_color
        ]
        meetings = list(getattr(belief, "meeting_history", ()) or ())
        hard_clears = {
            color
            for color, record in roster.items()
            if color in player_set
            and getattr(record, "life_status", "unknown") == "dead"
            and getattr(record, "death_source", None) in {"body", "census"}
        }
        # A direct witnessed kill is stronger than a contradictory death label.
        # This guard keeps a perception conflict from emptying the hypothesis space.
        hard_clears -= pins
        priors = (
            {}
            if public_only
            else {
                color: probability
                for color, probability in (
                    getattr(belief, "suspicion", {}) or {}
                ).items()
                if color in player_set
            }
        )
        evidence = SolverEvidence(
            claims=tuple(claims),
            meetings=tuple(meetings),
            pins=frozenset(pins),
            hard_clears=frozenset(hard_clears),
            clears=frozenset(clears),
            alibis=tuple(complete_alibis),
            alibi_groups=tuple(frozenset(group) for group in legacy_alibis),
            priors=tuple(sorted(priors.items())),
        )
        result = _solve_evidence(players, imposter_count, evidence)
        marginals = result["marginals"]
        if not marginals:
            return out
        pair_audit = {
            tuple(item["imposters"]): item for item in result["pair_audit"]
        }
        top_pair_audit = [
            pair_audit[tuple(hypothesis["imposters"])]
            for hypothesis in result["hypotheses"][:5]
        ]

        out.update(
            n_claims=result["n_claims"],
            n_raw_claims=len(raw_claims),
            n_self_claims_ignored=len(raw_claims) - len(claims),
            n_accusers=len(
                {
                    claim.source_color or claim.speaker_color
                    for claim in claims
                    if (claim.source_color or claim.speaker_color) in player_set
                }
            ),
            n_votes=result["n_votes"],
            n_alibis=result["n_alibis"],
            n_meetings=len(meetings),
            pins=sorted(pins),
            hard_clears=sorted(hard_clears),
            clears=sorted(clears),
            alibi_groups=[
                sorted(event.alibied_colors) for event in complete_alibis
            ]
            or [sorted(group) for group in legacy_alibis],
            alibi_events=[
                event.model_dump(mode="json") for event in complete_alibis
            ],
            distrusted_alibis=result["distrusted_alibis"],
            marginals={
                color: round(probability, 3) for color, probability in marginals.items()
            },
            hypotheses=[
                {"imposters": item["imposters"], "p": round(item["p"], 4)}
                for item in result["hypotheses"][:5]
            ],
            hypothesis_audit=[
                {
                    **item,
                    "log_weight": round(item["log_weight"], 6)
                    if item["log_weight"] is not None
                    else None,
                    "contributions": [
                        {
                            **contribution,
                            "delta": round(contribution["delta"], 6),
                        }
                        for contribution in item["contributions"]
                    ],
                }
                for item in top_pair_audit
            ],
            excluded_hypotheses=[
                {
                    "imposters": item["imposters"],
                    "reasons": item["exclusion_reasons"],
                }
                for item in result["pair_audit"]
                if not item["eligible"]
            ],
        )

        live = _live_vote_targets(belief, player_set)
        ranked = sorted(
            ((color, marginals[color]) for color in live if color in marginals),
            key=lambda item: (-item[1], item[0]),
        )
        if not ranked:
            return out
        out["top_candidate"] = ranked[0][0]
        out["top_p"] = round(ranked[0][1], 3)
        out["second_p"] = round(ranked[1][1], 3) if len(ranked) > 1 else 0.0

        threshold = _threshold()
        competitor = ranked[imposter_count][1] if len(ranked) > imposter_count else 0.0
        has_decision_evidence = bool(
            result["n_claims"]
            or result["n_votes"]
            or pins
            or hard_clears
            or clears
            or complete_alibis
            or legacy_alibis
        )
        if (
            enabled()
            and has_decision_evidence
            and ranked[0][1] >= threshold
            and ranked[0][1] - competitor >= _margin()
        ):
            candidate = ranked[0][0]
            out["pre_robust_pick"] = candidate
            candidate_sources = {
                claim.source_color or claim.speaker_color
                for claim in claims
                if claim.stance in {"accuse", "at_least_one"}
                and candidate in claim.targets
                and (claim.source_color or claim.speaker_color) in player_set
            }
            out["candidate_sources"] = sorted(candidate_sources)
            constraint_support = _constraint_decisive(
                candidate=candidate,
                players=players,
                live=live,
                imposter_count=imposter_count,
                evidence=evidence,
            )
            forced_support = _constraint_forces_candidate(
                candidate=candidate,
                players=players,
                imposter_count=imposter_count,
                evidence=evidence,
            )
            out.update(
                constraint_decisive=constraint_support["passed"],
                constraint_forced=forced_support["passed"],
                structural_hypotheses=forced_support["n_hypotheses"],
                constraint_channels=constraint_support["channels"],
                without_constraints_p=round(constraint_support["without_p"], 3)
                if constraint_support["without_p"] is not None
                else None,
                without_constraints_margin=round(
                    constraint_support["without_margin"], 3
                )
                if constraint_support["without_margin"] is not None
                else None,
                without_constraints_top=constraint_support["without_top"],
            )
            robustness_required = len(candidate_sources) == 1
            out["robust_required"] = robustness_required
            robustness: dict[str, Any] | None = None
            if robustness_required:
                robustness = _without_actor(
                    actor=next(iter(candidate_sources)),
                    candidate=candidate,
                    players=players,
                    live=live,
                    imposter_count=imposter_count,
                    evidence=evidence,
                )
                out.update(
                    robust_min_p=round(robustness["min_p"], 3),
                    robust_min_margin=round(robustness["min_margin"], 3),
                    robust_crowd_p=round(robustness["crowd_p"], 3),
                    robust_weakest_actor=robustness["weakest_actor"],
                )
            source_supported = bool(candidate_sources) and (
                not robustness_required
                or (robustness is not None and robustness["passed"])
            )
            constraint_only_supported = (
                not candidate_sources and forced_support["passed"]
            )
            if candidate in pins or source_supported or constraint_only_supported:
                out["fired"] = True
                out["pick"] = candidate
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def solver_report(belief: Any) -> dict[str, Any]:
    return _solver_report(belief, public_only=False)


def public_solver_report(belief: Any) -> dict[str, Any]:
    """Solve from replay-visible claims and ballots, excluding private evidence."""

    return _solver_report(belief, public_only=True)


def persistent_target_sources(belief: Any, report: dict[str, Any]) -> list[str]:
    """Independent external sources supporting the pick across all meetings."""

    target = report.get("pick")
    if target is None:
        return []
    self_color = getattr(belief, "self_color", None)
    sources = {
        claim.source_color or claim.speaker_color
        for claim in (getattr(belief, "social_claims", ()) or ())
        if claim.speaker_color != self_color
        and claim.stance in {"accuse", "at_least_one"}
        and target in claim.targets
        and (claim.source_color or claim.speaker_color) not in {None, self_color}
    }
    return sorted(sources)


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
