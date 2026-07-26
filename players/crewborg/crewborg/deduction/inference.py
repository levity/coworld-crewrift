"""Pure inference over an immutable deduction history.

The solver never consumes ``Belief`` or a previously derived suspicion score.
Every call reparses the retained utterances and rebuilds the complete table of
possible impostor assignments, which keeps parser and likelihood changes
replayable.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from itertools import combinations
from typing import Literal

from crewborg.deduction.model import (
    DeathObserved,
    DeductionHistory,
    MeetingObserved,
    UtteranceObserved,
    VoteObserved,
    WorldObserved,
)
from crewborg.game_rules import COPRESENCE_DISTANCE_SQ, KILL_RANGE_SQ
from crewborg.strategy.claims import ClaimStance, parse_claims

EvidenceStatus = Literal["active", "ignored"]

VICTIM_ABSENCE_TICKS = 3
_WITH_ME = re.compile(r"\bwith\s+me\b", re.IGNORECASE)


@dataclass(frozen=True)
class InferenceConfig:
    """Likelihoods and correlation discounts for derived public evidence."""

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
    repeat_decay: float = 0.70
    same_target_decay: float = 0.80
    vote_repeat_decay: float = 0.70
    # Per-speaker tempering (see `_speaker_trust`). OFF by default: with
    # speaker_trust=False every weight keeps its shipped value exactly.
    speaker_trust: bool = False
    speaker_trust_prior: float = 0.25
    speaker_trust_k: float = 2.0
    vote_weight: float = 0.35
    reporter_weight: float = 1.15
    bare_weight: float = 0.25
    body_weight: float = 1.00
    vent_weight: float = 1.10
    sighting_weight: float = 0.85
    claimed_vote_weight: float = 0.50
    relay_weight: float = 0.45
    kill_range_sq: int = KILL_RANGE_SQ


@dataclass(frozen=True)
class EvidenceAudit:
    evidence_id: str
    event_id: str
    channel: str
    status: EvidenceStatus
    reason: str
    source: str | None = None
    targets: tuple[str, ...] = ()
    stance: ClaimStance | None = None
    weight: float = 0.0


@dataclass(frozen=True)
class Contribution:
    evidence_id: str
    channel: str
    likelihood: float
    weight: float
    delta: float


@dataclass(frozen=True)
class PairPosterior:
    imposters: tuple[str, ...]
    probability: float
    log_weight: float
    contributions: tuple[Contribution, ...]


@dataclass(frozen=True)
class ExcludedPair:
    imposters: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class InferenceResult:
    """Complete derived result, including enough detail to audit every pair."""

    marginals: tuple[tuple[str, float], ...]
    hypotheses: tuple[PairPosterior, ...]
    excluded: tuple[ExcludedPair, ...]
    evidence: tuple[EvidenceAudit, ...]
    pins: tuple[str, ...]
    murder_clears: tuple[str, ...]
    error: str | None = None

    def marginal(self, color: str) -> float:
        return dict(self.marginals).get(color, 0.0)

    def as_trace(self, *, max_hypotheses: int = 5) -> dict[str, object]:
        return {
            "marginals": {
                color: round(probability, 4) for color, probability in self.marginals
            },
            "hypotheses": [
                {
                    "imposters": list(item.imposters),
                    "p": round(item.probability, 5),
                    "contributions": [
                        {
                            "evidence_id": contribution.evidence_id,
                            "channel": contribution.channel,
                            "delta": round(contribution.delta, 6),
                        }
                        for contribution in item.contributions
                    ],
                }
                for item in self.hypotheses[:max_hypotheses]
            ],
            "excluded": [
                {"imposters": list(item.imposters), "reasons": list(item.reasons)}
                for item in self.excluded
            ],
            "pins": list(self.pins),
            "murder_clears": list(self.murder_clears),
            "evidence": [
                {
                    "evidence_id": item.evidence_id,
                    "event_id": item.event_id,
                    "channel": item.channel,
                    "status": item.status,
                    "reason": item.reason,
                    "source": item.source,
                    "targets": list(item.targets),
                    "stance": item.stance,
                    "weight": round(item.weight, 4),
                }
                for item in self.evidence
            ],
            "error": self.error,
        }

    def as_factor_trace(self) -> dict[str, object]:
        """Serialize every assignment factor for offline weight sweeps."""

        return {
            "hypotheses": [
                {
                    "imposters": list(item.imposters),
                    "p": round(item.probability, 8),
                    "log_weight": round(item.log_weight, 8),
                    "factors": [
                        {
                            "evidence_id": contribution.evidence_id,
                            "channel": contribution.channel,
                            "likelihood": round(contribution.likelihood, 8),
                            "weight": round(contribution.weight, 8),
                        }
                        for contribution in item.contributions
                    ],
                }
                for item in self.hypotheses
            ],
            "excluded": [
                {"imposters": list(item.imposters), "reasons": list(item.reasons)}
                for item in self.excluded
            ],
            "error": self.error,
        }


@dataclass(frozen=True)
class DerivedClaim:
    """One parsed, deduplicated, and correlation-adjusted public claim."""

    evidence_id: str
    event_id: str
    meeting_id: int
    tick: int
    speaker: str
    source: str
    targets: tuple[str, ...]
    stance: ClaimStance
    provenance: Literal["direct", "relayed"]
    weight: float


@dataclass(frozen=True)
class DerivedVote:
    """One public ballot factor retained across meetings."""

    evidence_id: str
    event_id: str
    meeting_id: int
    voter: str
    target: str
    weight: float


@dataclass(frozen=True)
class DerivedKillConstraint:
    """A relational constraint for one bounded hidden-kill window."""

    evidence_id: str
    event_id: str
    victim: str
    alibied: frozenset[str]
    possible_killers: frozenset[str]


@dataclass(frozen=True)
class DerivedEvidence:
    """Layer 1: semantic and structural features rebuilt from raw history."""

    candidates: tuple[str, ...]
    claims: tuple[DerivedClaim, ...]
    votes: tuple[DerivedVote, ...]
    kill_constraints: tuple[DerivedKillConstraint, ...]
    pins: frozenset[str]
    murder_clears: frozenset[str]
    audit: tuple[EvidenceAudit, ...]


@dataclass(frozen=True)
class AssignmentTable:
    """Layer 2: structurally viable fixed-size impostor assignments."""

    candidates: tuple[str, ...]
    eligible: tuple[tuple[str, ...], ...]
    excluded: tuple[ExcludedPair, ...]
    evidence: DerivedEvidence
    error: str | None = None


def infer(
    history: DeductionHistory,
    *,
    config: InferenceConfig | None = None,
) -> InferenceResult:
    """Run the complete derivation -> assignment -> scoring pipeline."""

    resolved = config or InferenceConfig()
    evidence = derive_evidence(history, config=resolved)
    table = build_assignment_table(history, evidence)
    return score_assignments(table, config=resolved)


def derive_evidence(
    history: DeductionHistory,
    *,
    config: InferenceConfig | None = None,
) -> DerivedEvidence:
    """Layer 1: rebuild meaningful evidence from the raw append-only stream."""

    config = config or InferenceConfig()
    players = tuple(dict.fromkeys(history.game.players))
    self_color = history.game.self_color
    candidates = tuple(
        color
        for color in players
        if not (history.game.self_role == "crewmate" and color == self_color)
    )
    player_set = set(players)
    claims, claim_audit = _claims(history, player_set, config)
    votes, vote_audit = _votes(history, player_set, config)
    pins, direct_audit, witnessed_victims = _witnessed_actions(
        history,
        config=config,
    )
    pins.update(color for color in history.game.known_imposters if color in player_set)
    murder_clears = {
        event.color
        for event in history.events
        if isinstance(event, DeathObserved)
        and event.source in {"body", "census"}
        and event.color in player_set
    }
    # A witnessed action is the more specific observation if perception ever
    # produces a contradictory census label.
    murder_clears -= pins
    kill_constraints, alibi_audit = _kill_constraints(
        history,
        candidates=set(candidates),
        witnessed_victims=witnessed_victims,
    )
    return DerivedEvidence(
        candidates=candidates,
        claims=tuple(claims),
        votes=tuple(votes),
        kill_constraints=tuple(kill_constraints),
        pins=frozenset(pins),
        murder_clears=frozenset(murder_clears),
        audit=tuple(claim_audit + vote_audit + direct_audit + alibi_audit),
    )


def build_assignment_table(
    history: DeductionHistory,
    evidence: DerivedEvidence,
) -> AssignmentTable:
    """Layer 2: apply hard facts to the complete assignment table."""

    imposter_count = history.game.imposter_count
    if imposter_count <= 0 or imposter_count > len(evidence.candidates):
        return AssignmentTable(
            candidates=evidence.candidates,
            eligible=(),
            excluded=(),
            evidence=evidence,
            error=(
                f"invalid imposter count {imposter_count} for "
                f"{len(evidence.candidates)} candidates"
            ),
        )

    all_pairs = [
        tuple(combo) for combo in combinations(evidence.candidates, imposter_count)
    ]
    eligible: list[tuple[str, ...]] = []
    excluded: list[ExcludedPair] = []
    for pair in all_pairs:
        hypothesis = frozenset(pair)
        reasons: list[str] = []
        for color in sorted(evidence.pins - hypothesis):
            reasons.append(f"missing_pin:{color}")
        for color in sorted(hypothesis & evidence.murder_clears):
            reasons.append(f"murder_clear:{color}")
        for constraint in evidence.kill_constraints:
            eligible_impostors = hypothesis & constraint.possible_killers
            if not eligible_impostors - constraint.alibied:
                reasons.append(f"no_possible_killer:{constraint.evidence_id}")
        if reasons:
            excluded.append(ExcludedPair(pair, tuple(reasons)))
        else:
            eligible.append(pair)
    return AssignmentTable(
        candidates=evidence.candidates,
        eligible=tuple(eligible),
        excluded=tuple(excluded),
        evidence=evidence,
        error=(
            "structural evidence excludes every role assignment"
            if not eligible
            else None
        ),
    )


def score_assignments(
    table: AssignmentTable,
    *,
    config: InferenceConfig | None = None,
) -> InferenceResult:
    """Layers 3-4: score assignment factors and normalize the joint posterior."""

    config = config or InferenceConfig()
    evidence = table.evidence
    if table.error is not None:
        return InferenceResult(
            marginals=tuple((color, 0.0) for color in table.candidates),
            hypotheses=(),
            excluded=table.excluded,
            evidence=evidence.audit,
            pins=tuple(sorted(evidence.pins)),
            murder_clears=tuple(sorted(evidence.murder_clears)),
            error=table.error,
        )

    trust = _speaker_trust(evidence, config)
    log_weights: dict[tuple[str, ...], float] = {}
    contribution_table: dict[tuple[str, ...], tuple[Contribution, ...]] = {}
    for pair in table.eligible:
        hypothesis = frozenset(pair)
        contributions: list[Contribution] = []
        log_weight = 0.0
        for claim in evidence.claims:
            likelihood = _claim_probability(hypothesis, claim, config)
            weight = claim.weight * trust.get(claim.source, 1.0)
            delta = weight * math.log(max(likelihood, 1e-9))
            contributions.append(
                Contribution(
                    evidence_id=claim.evidence_id,
                    channel="claim",
                    likelihood=likelihood,
                    weight=weight,
                    delta=delta,
                )
            )
            log_weight += delta
        for vote in evidence.votes:
            likelihood = _vote_probability(hypothesis, vote, config)
            weight = vote.weight * trust.get(vote.voter, 1.0)
            delta = weight * math.log(max(likelihood, 1e-9))
            contributions.append(
                Contribution(
                    evidence_id=vote.evidence_id,
                    channel="vote",
                    likelihood=likelihood,
                    weight=weight,
                    delta=delta,
                )
            )
            log_weight += delta
        log_weights[pair] = log_weight
        contribution_table[pair] = tuple(contributions)

    maximum = max(log_weights.values())
    unnormalized = {
        pair: math.exp(log_weight - maximum) for pair, log_weight in log_weights.items()
    }
    total = sum(unnormalized.values())
    probabilities = {pair: weight / total for pair, weight in unnormalized.items()}
    ranked = tuple(
        PairPosterior(
            imposters=pair,
            probability=probability,
            log_weight=log_weights[pair],
            contributions=contribution_table[pair],
        )
        for pair, probability in sorted(
            probabilities.items(),
            key=lambda item: (-item[1], item[0]),
        )
    )
    marginals = tuple(
        (
            color,
            sum(
                probability
                for pair, probability in probabilities.items()
                if color in pair
            ),
        )
        for color in table.candidates
    )
    return InferenceResult(
        marginals=marginals,
        hypotheses=ranked,
        excluded=table.excluded,
        evidence=evidence.audit,
        pins=tuple(sorted(evidence.pins)),
        murder_clears=tuple(sorted(evidence.murder_clears)),
    )


def _claims(
    history: DeductionHistory,
    players: set[str],
    config: InferenceConfig,
) -> tuple[list[DerivedClaim], list[EvidenceAudit]]:
    reporters = {
        event.meeting_id: event.caller
        for event in history.events
        if isinstance(event, MeetingObserved) and event.call_kind == "body"
    }
    candidates: list[DerivedClaim] = []
    audit: list[EvidenceAudit] = []
    for event in history.events:
        if not isinstance(event, UtteranceObserved):
            continue
        if event.speaker is None:
            audit.append(
                EvidenceAudit(
                    evidence_id=f"utterance:{event.event_id}",
                    event_id=event.event_id,
                    channel="utterance",
                    status="ignored",
                    reason="unattributed speaker",
                )
            )
            continue
        if event.speaker == history.game.self_color:
            audit.append(
                EvidenceAudit(
                    evidence_id=f"utterance:{event.event_id}",
                    event_id=event.event_id,
                    channel="utterance",
                    status="ignored",
                    reason="own derived speech is not new evidence",
                    source=event.speaker,
                )
            )
            continue
        parsed = parse_claims(
            event.text,
            speaker_color=event.speaker,
            colors=players,
            meeting_id=event.meeting_id,
            tick=event.tick,
        )
        if not parsed:
            audit.append(
                EvidenceAudit(
                    evidence_id=f"utterance:{event.event_id}",
                    event_id=event.event_id,
                    channel="utterance",
                    status="ignored",
                    reason="no recognized deduction claim",
                    source=event.speaker,
                )
            )
            continue
        for index, claim in enumerate(parsed):
            evidence_id = f"claim:{event.event_id}:{index}"
            source = claim.source_color or claim.speaker_color
            targets = tuple(sorted(set(claim.targets)))
            reason = _claim_rejection_reason(
                event=event,
                source=source,
                targets=targets,
                players=players,
                stance=claim.stance,
            )
            if reason is not None:
                audit.append(
                    EvidenceAudit(
                        evidence_id=evidence_id,
                        event_id=event.event_id,
                        channel="claim",
                        status="ignored",
                        reason=reason,
                        source=source,
                        targets=targets,
                        stance=claim.stance,
                    )
                )
                continue
            weight = {
                "bare": config.bare_weight,
                "body": config.body_weight,
                "vent": config.vent_weight,
                "sighting": config.sighting_weight,
                "vote": config.claimed_vote_weight,
            }[claim.evidence_kind]
            if claim.provenance == "relayed":
                weight *= config.relay_weight
            if (
                claim.provenance == "direct"
                and reporters.get(event.meeting_id) == source
                and event.speaker == source
            ):
                weight *= config.reporter_weight
            candidates.append(
                DerivedClaim(
                    evidence_id=evidence_id,
                    event_id=event.event_id,
                    meeting_id=event.meeting_id,
                    tick=event.tick,
                    speaker=event.speaker,
                    source=source or "",
                    targets=targets,
                    stance=claim.stance,
                    provenance=claim.provenance,
                    weight=weight,
                )
            )

    best: dict[tuple[int, str, str, tuple[str, ...]], DerivedClaim] = {}
    for claim in candidates:
        key = (claim.meeting_id, claim.source, claim.stance, claim.targets)
        previous = best.get(key)
        if previous is None or claim.weight > previous.weight:
            if previous is not None:
                audit.append(_duplicate_claim_audit(previous, claim.evidence_id))
            best[key] = claim
        else:
            audit.append(_duplicate_claim_audit(claim, previous.evidence_id))

    repeated: dict[tuple[str, str, tuple[str, ...]], int] = {}
    same_target: dict[tuple[int, str, tuple[str, ...]], int] = {}
    weighted: list[DerivedClaim] = []
    for claim in sorted(
        best.values(),
        key=lambda item: (
            item.meeting_id,
            item.stance,
            item.targets,
            -item.weight,
            item.tick,
            item.source,
        ),
    ):
        repeated_key = (claim.source, claim.stance, claim.targets)
        repeat_index = repeated.get(repeated_key, 0)
        repeated[repeated_key] = repeat_index + 1
        target_key = (claim.meeting_id, claim.stance, claim.targets)
        target_index = same_target.get(target_key, 0)
        same_target[target_key] = target_index + 1
        final = replace(
            claim,
            weight=(
                claim.weight
                * config.repeat_decay**repeat_index
                * config.same_target_decay**target_index
            ),
        )
        weighted.append(final)
        audit.append(
            EvidenceAudit(
                evidence_id=final.evidence_id,
                event_id=final.event_id,
                channel="claim",
                status="active",
                reason="role-conditioned claim likelihood",
                source=final.source,
                targets=final.targets,
                stance=final.stance,
                weight=final.weight,
            )
        )
    return weighted, audit


def _claim_rejection_reason(
    *,
    event: UtteranceObserved,
    source: str | None,
    targets: tuple[str, ...],
    players: set[str],
    stance: str,
) -> str | None:
    if source not in players:
        return "claim source is not a player"
    if not targets or any(target not in players for target in targets):
        return "claim target is not a player"
    if source in targets:
        return "self-directed claim"
    if stance == "defend" and _WITH_ME.search(event.text):
        return "co-presence is not a unary player clear"
    if stance == "accuse" and any(
        re.search(
            rf"\bsaw\s+{re.escape(target)}\s+near\s+(?:the\s+)?vent\b",
            event.text,
            re.IGNORECASE,
        )
        for target in targets
    ):
        return "proximity to a vent is not witnessed vent use"
    return None


def _duplicate_claim_audit(
    claim: DerivedClaim,
    kept_id: str,
) -> EvidenceAudit:
    return EvidenceAudit(
        evidence_id=claim.evidence_id,
        event_id=claim.event_id,
        channel="claim",
        status="ignored",
        reason=f"duplicate source-target claim; kept {kept_id}",
        source=claim.source,
        targets=claim.targets,
        stance=claim.stance,
    )


def _votes(
    history: DeductionHistory,
    players: set[str],
    config: InferenceConfig,
) -> tuple[list[DerivedVote], list[EvidenceAudit]]:
    repeated: dict[tuple[str, str], int] = {}
    votes: list[DerivedVote] = []
    audit: list[EvidenceAudit] = []
    for event in sorted(
        (item for item in history.events if isinstance(item, VoteObserved)),
        key=lambda item: (item.meeting_id, item.tick, item.voter),
    ):
        evidence_id = f"vote:{event.event_id}"
        if event.voter == history.game.self_color:
            reason = "own derived vote is not new evidence"
        elif event.target is None:
            reason = "skip vote has no target likelihood"
        elif event.voter not in players or event.target not in players:
            reason = "vote actor or target is not a player"
        elif event.voter == event.target:
            reason = "self vote is not modeled"
        else:
            reason = ""
        if reason:
            audit.append(
                EvidenceAudit(
                    evidence_id=evidence_id,
                    event_id=event.event_id,
                    channel="vote",
                    status="ignored",
                    reason=reason,
                    source=event.voter,
                    targets=() if event.target is None else (event.target,),
                )
            )
            continue
        assert event.target is not None
        key = (event.voter, event.target)
        repeat_index = repeated.get(key, 0)
        repeated[key] = repeat_index + 1
        vote = DerivedVote(
            evidence_id=evidence_id,
            event_id=event.event_id,
            meeting_id=event.meeting_id,
            voter=event.voter,
            target=event.target,
            weight=config.vote_weight * config.vote_repeat_decay**repeat_index,
        )
        votes.append(vote)
        audit.append(
            EvidenceAudit(
                evidence_id=evidence_id,
                event_id=event.event_id,
                channel="vote",
                status="active",
                reason="role-conditioned ballot likelihood",
                source=event.voter,
                targets=(event.target,),
                weight=vote.weight,
            )
        )
    return votes, audit


def _kill_constraints(
    history: DeductionHistory,
    *,
    candidates: set[str],
    witnessed_victims: set[str],
) -> tuple[list[DerivedKillConstraint], list[EvidenceAudit]]:
    worlds = [event for event in history.events if isinstance(event, WorldObserved)]
    constraints: list[DerivedKillConstraint] = []
    audit: list[EvidenceAudit] = []
    all_deaths = [
        event for event in history.events if isinstance(event, DeathObserved)
    ]
    deaths = [
        event
        for event in all_deaths
        if event.source in {"body", "census"}
    ]
    for death in deaths:
        evidence_id = f"alibi:{death.event_id}"
        if death.color in witnessed_victims:
            audit.append(
                EvidenceAudit(
                    evidence_id=evidence_id,
                    event_id=death.event_id,
                    channel="alibi",
                    status="ignored",
                    reason="kill was directly witnessed",
                    targets=(death.color,),
                )
            )
            continue
        last_victim_frame = next(
            (
                frame
                for frame in reversed(worlds)
                if frame.tick <= death.tick
                and any(player.color == death.color for player in frame.players)
            ),
            None,
        )
        end_frame = next(
            (frame for frame in reversed(worlds) if frame.tick <= death.tick),
            None,
        )
        if (
            last_victim_frame is None
            or end_frame is None
            or end_frame.tick - last_victim_frame.tick <= VICTIM_ABSENCE_TICKS
        ):
            audit.append(
                EvidenceAudit(
                    evidence_id=evidence_id,
                    event_id=death.event_id,
                    channel="alibi",
                    status="ignored",
                    reason="no bounded off-screen kill window",
                    targets=(death.color,),
                )
            )
            continue
        window = [
            frame
            for frame in worlds
            if last_victim_frame.tick <= frame.tick <= end_frame.tick
        ]
        expected_ticks = end_frame.tick - last_victim_frame.tick + 1
        if len(window) != expected_ticks:
            audit.append(
                EvidenceAudit(
                    evidence_id=evidence_id,
                    event_id=death.event_id,
                    channel="alibi",
                    status="ignored",
                    reason="camera history has a gap inside the kill window",
                    targets=(death.color,),
                )
            )
            continue
        alibied = {
            color
            for color in candidates - {death.color}
            if all(_close_to_self(frame, color) for frame in window)
        }
        if not alibied:
            audit.append(
                EvidenceAudit(
                    evidence_id=evidence_id,
                    event_id=death.event_id,
                    channel="alibi",
                    status="ignored",
                    reason="no player was continuously co-present",
                    targets=(death.color,),
                )
            )
            continue
        previously_dead = {
            other.color for other in all_deaths if other.tick < end_frame.tick
        }
        possible_killers = candidates - {death.color} - previously_dead
        constraint = DerivedKillConstraint(
            evidence_id=evidence_id,
            event_id=death.event_id,
            victim=death.color,
            alibied=frozenset(alibied),
            possible_killers=frozenset(possible_killers),
        )
        constraints.append(constraint)
        audit.append(
            EvidenceAudit(
                evidence_id=evidence_id,
                event_id=death.event_id,
                channel="alibi",
                status="active",
                reason="at least one eligible impostor was outside continuous co-presence",
                targets=tuple(sorted(alibied)),
                weight=1.0,
            )
        )
    return constraints, audit


def _witnessed_actions(
    history: DeductionHistory,
    *,
    config: InferenceConfig,
) -> tuple[set[str], list[EvidenceAudit], set[str]]:
    """Derive direct-action pins without storing conclusions in history."""

    worlds = sorted(
        (event for event in history.events if isinstance(event, WorldObserved)),
        key=lambda event: event.tick,
    )
    pins: set[str] = set()
    witnessed_victims: set[str] = set()
    audit: list[EvidenceAudit] = []
    for previous, current in zip(worlds, worlds[1:]):
        if current.tick != previous.tick + 1:
            continue
        previous_players = {
            player.color: (player.x, player.y) for player in previous.players
        }
        current_players = {player.color for player in current.players}
        new_bodies = {body.color for body in current.bodies} - {
            body.color for body in previous.bodies
        }
        for victim in sorted(new_bodies):
            victim_xy = previous_players.get(victim)
            if victim_xy is None:
                continue
            actors = {
                color
                for color, position in previous_players.items()
                if color not in {victim, history.game.self_color}
                and _distance_sq(position, victim_xy) <= config.kill_range_sq
            }
            evidence_id = f"direct:kill:{current.event_id}:{victim}"
            if len(actors) != 1:
                audit.append(
                    EvidenceAudit(
                        evidence_id=evidence_id,
                        event_id=current.event_id,
                        channel="direct",
                        status="ignored",
                        reason=(
                            f"body transition has {len(actors)} possible nearby actors"
                        ),
                        targets=(victim,),
                    )
                )
                continue
            actor = next(iter(actors))
            pins.add(actor)
            witnessed_victims.add(victim)
            audit.append(
                EvidenceAudit(
                    evidence_id=evidence_id,
                    event_id=current.event_id,
                    channel="direct",
                    status="active",
                    reason=f"unique actor adjacent when {victim} became a body",
                    source=history.game.self_color,
                    targets=(actor, victim),
                    weight=1.0,
                )
            )

        previous_vents = {
            vent.index: set(vent.occupants) for vent in previous.visible_vents
        }
        current_vents = {
            vent.index: set(vent.occupants) for vent in current.visible_vents
        }
        venters: set[str] = set()
        for index in previous_vents.keys() & current_vents.keys():
            venters.update(current_vents[index] - previous_players.keys())
            venters.update(
                color for color in previous_vents[index] if color not in current_players
            )
        for actor in sorted(venters - {history.game.self_color}):
            pins.add(actor)
            audit.append(
                EvidenceAudit(
                    evidence_id=f"direct:vent:{current.event_id}:{actor}",
                    event_id=current.event_id,
                    channel="direct",
                    status="active",
                    reason="player appeared from or disappeared into a continuously visible vent",
                    source=history.game.self_color,
                    targets=(actor,),
                    weight=1.0,
                )
            )
    return pins, audit, witnessed_victims


def _distance_sq(
    first: tuple[int, int],
    second: tuple[int, int],
) -> int:
    dx = first[0] - second[0]
    dy = first[1] - second[1]
    return dx * dx + dy * dy


def _close_to_self(frame: WorldObserved, color: str) -> bool:
    player = next(
        (candidate for candidate in frame.players if candidate.color == color),
        None,
    )
    if player is None:
        return False
    dx = player.x - frame.self_xy[0]
    dy = player.y - frame.self_xy[1]
    return dx * dx + dy * dy <= COPRESENCE_DISTANCE_SQ


def _speaker_trust(
    evidence: DerivedEvidence, config: InferenceConfig
) -> dict[str, float]:
    """Per-speaker tempering factor in [0, 1]; empty (=1.0 everywhere) when disabled.

    WHY. Every likelihood here is keyed to ROLE only -- `crew_accuse_hit=0.58` vs
    `crew_accuse_miss=0.15` says any crewmate accuses a real impostor ~4x more often
    than an innocent. That held in every A/B we ran, because all six crew seats were
    this same policy. It is false in league play: some policies target on 100% of
    their ballots, so their true ratio is 1.0 and we read pure noise as 4:1 evidence.
    Measured over 60 league episodes, non-structural ejects were 5/19 correct against
    ~29% for random voting.

    HOW. `tau` is estimated from how SELECTIVELY a speaker votes, which needs no
    ground truth and is observable for everyone at every meeting. It is applied as
    tempering (`weight *= tau`) rather than by rewriting the likelihoods: tau=0
    exactly reproduces "ignore this speaker", it is monotone, and it cannot
    manufacture a confidently wrong posterior the way mis-set likelihoods can.

    THE PRIOR IS THE LOAD-BEARING PART. A seat gets ~2.5 meetings per episode and has
    seen each other player vote exactly ONCE by its first decision, so the estimate is
    coarse when it matters most. Measured at that first meeting, the shipped posterior
    is a coin flip (AUC 0.514) and every non-structural eject it casts is wrong (0/5).
    The fix is not a faster estimator but a lower starting point: shrinking toward
    `speaker_trust_prior` means strangers are discounted until they demonstrate
    selectivity. The shipped model is effectively tau=1 -- maximum trust in strangers
    at the moment it has least basis for it.

    When the platform exposes which policy occupies each seat, `speaker_trust_prior`
    becomes a per-policy prior carried across games and nothing else here changes.
    """

    if not config.speaker_trust:
        return {}
    ballots: dict[str, list[int]] = {}
    for vote in evidence.votes:
        seen = ballots.setdefault(vote.voter, [0, 0])
        seen[0] += 1
        if vote.target:
            seen[1] += 1
    prior, k = config.speaker_trust_prior, config.speaker_trust_k
    out: dict[str, float] = {}
    for speaker, (n, targeted) in ballots.items():
        raw = 1.0 - (targeted / n if n else 0.0)
        out[speaker] = (n * raw + k * prior) / (n + k)
    return out


def _claim_probability(
    hypothesis: frozenset[str],
    claim: DerivedClaim,
    config: InferenceConfig,
) -> float:
    probability = _actor_claim_probability(
        hypothesis,
        claim.source,
        claim.targets,
        claim.stance,
        config,
    )
    if claim.provenance == "relayed" and claim.speaker != claim.source:
        speaker_probability = _actor_claim_probability(
            hypothesis,
            claim.speaker,
            claim.targets,
            claim.stance,
            config,
        )
        probability = math.sqrt(probability * speaker_probability)
    return probability


def _actor_claim_probability(
    hypothesis: frozenset[str],
    actor: str,
    targets: tuple[str, ...],
    stance: ClaimStance,
    config: InferenceConfig,
) -> float:
    actor_is_imp = actor in hypothesis
    target_is_imp = any(target in hypothesis for target in targets)
    if stance in {"accuse", "at_least_one"}:
        if actor_is_imp:
            return (
                config.imp_accuse_partner if target_is_imp else config.imp_accuse_crew
            )
        return config.crew_accuse_hit if target_is_imp else config.crew_accuse_miss
    if actor_is_imp:
        return config.imp_defend_partner if target_is_imp else config.imp_defend_crew
    return config.crew_defend_imp if target_is_imp else config.crew_defend_crew


def _vote_probability(
    hypothesis: frozenset[str],
    vote: DerivedVote,
    config: InferenceConfig,
) -> float:
    voter_is_imp = vote.voter in hypothesis
    target_is_imp = vote.target in hypothesis
    if voter_is_imp:
        return config.imp_vote_partner if target_is_imp else config.imp_vote_crew
    return config.crew_vote_imp if target_is_imp else config.crew_vote_crew
