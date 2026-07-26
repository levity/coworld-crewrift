"""Pure meeting policy over a joint deduction result."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from crewborg.deduction.inference import (
    InferenceConfig,
    InferenceResult,
    infer,
)
from crewborg.deduction.model import DeathObserved, DeductionHistory

DecisionAction = Literal["eject", "skip"]


@dataclass(frozen=True)
class DecisionConfig:
    base_probability: float = 0.65
    base_margin: float = 0.10
    dangerous_wrong_eject_probability: float = 0.80
    forced_vote_probability: float = 0.51
    parity_risk_cutoff: float = 0.80
    min_independent_sources: int = 2
    # The accusation/source requirement below is reachable in ~6% of decisions
    # (measured: 498/739 have zero attributed sources), because "sources" are social
    # and the claim parser drops ~81% of utterances. Set False to gate on the
    # posterior alone; `structural` still short-circuits either way.
    require_support: bool = True
    # Eject ONLY when the target is structurally implied (a personal witness pin, or
    # present in every surviving role assignment). Measured over 60 league episodes,
    # 2026-07-26: structural ejects were 9/9 correct, non-structural 5/19 (26.3%) --
    # at or below the 28.6% you get voting at random.
    #
    # This is a class gate rather than a threshold because the posterior is NOT
    # informative inside the non-structural class: mean probability 0.786 when right
    # vs 0.798 when wrong. Raising `base_probability` there only cuts volume at
    # random, so there is no threshold to tune.
    #
    # The cause is roster composition. Non-structural targets rest on the social
    # channel (other players' claims and votes), and the A/B that validated that
    # channel ran a homogeneous roster where all six crew seats were this same
    # policy. In league play five of six crewmates are foreign policies whose
    # utterances this parser mostly cannot read and whose votes are near-random.
    require_structural: bool = False


@dataclass(frozen=True)
class MeetingDecision:
    action: DecisionAction
    target: str | None
    probability: float
    required_probability: float
    margin: float
    sources: tuple[str, ...]
    structural: bool
    skip_loss_probability: float
    wrong_eject_loss_probability: float
    reason: str
    inference: InferenceResult

    def as_trace(self) -> dict[str, object]:
        return {
            "action": self.action,
            "target": self.target,
            "probability": round(self.probability, 4),
            "required_probability": round(self.required_probability, 4),
            "margin": round(self.margin, 4),
            "sources": list(self.sources),
            "structural": self.structural,
            "skip_loss_probability": round(self.skip_loss_probability, 4),
            "wrong_eject_loss_probability": round(
                self.wrong_eject_loss_probability,
                4,
            ),
            "reason": self.reason,
            "inference": self.inference.as_trace(),
        }


def decide(
    history: DeductionHistory,
    *,
    live_targets: tuple[str, ...] | None = None,
    inference_config: InferenceConfig | None = None,
    decision_config: DecisionConfig | None = None,
) -> MeetingDecision:
    """Infer and choose a vote without mutable or legacy conclusions."""

    result = infer(history, config=inference_config)
    return decide_from_inference(
        history,
        result,
        live_targets=live_targets,
        decision_config=decision_config,
    )


def decide_from_inference(
    history: DeductionHistory,
    result: InferenceResult,
    *,
    live_targets: tuple[str, ...] | None = None,
    decision_config: DecisionConfig | None = None,
) -> MeetingDecision:
    """Layer 5: apply a tunable board policy to one fixed posterior.

    The config is always the caller's; this stage never reads the environment. The
    runtime resolves the preset once, at the mode boundary
    (``modes/attend_meeting.py``), so an offline sweep cannot inherit one from the shell.
    """

    policy = decision_config or DecisionConfig()
    live = (
        tuple(dict.fromkeys(live_targets))
        if live_targets is not None
        else _live_targets(history)
    )
    live = tuple(
        color
        for color in live
        if color != history.game.self_color
        and any(color == candidate for candidate, _ in result.marginals)
    )
    ranked = sorted(
        ((color, result.marginal(color)) for color in live),
        key=lambda item: (-item[1], item[0]),
    )
    if result.error is not None or not ranked:
        return _skip(
            result,
            reason=result.error or "no live vote targets",
            required_probability=policy.base_probability,
        )

    target, probability = ranked[0]
    outside_top_k = (
        ranked[history.game.imposter_count][1]
        if len(ranked) > history.game.imposter_count
        else 0.0
    )
    margin = probability - outside_top_k
    skip_loss, wrong_eject_loss = _parity_risks(
        history,
        result,
        target=target,
        live=live,
    )
    required = policy.base_probability
    if skip_loss >= policy.parity_risk_cutoff:
        required = policy.forced_vote_probability
    elif wrong_eject_loss > 0.0:
        required = policy.dangerous_wrong_eject_probability

    sources = tuple(
        sorted(
            {
                evidence.source
                for evidence in result.evidence
                if evidence.status == "active"
                and evidence.source is not None
                and evidence.source != history.game.self_color
                and target in evidence.targets
                and (
                    evidence.channel == "vote"
                    or evidence.stance in {"accuse", "at_least_one"}
                )
            }
        )
    )
    structural = target in result.pins or (
        bool(result.hypotheses)
        and all(target in hypothesis.imposters for hypothesis in result.hypotheses)
    )
    has_accusation = any(
        evidence.status == "active"
        and evidence.channel == "claim"
        and evidence.stance in {"accuse", "at_least_one"}
        and target in evidence.targets
        for evidence in result.evidence
    )
    has_support = (
        structural
        or not policy.require_support
        or (has_accusation and len(sources) >= policy.min_independent_sources)
    ) and (structural or not policy.require_structural)
    has_evidence = bool(
        result.pins
        or result.murder_clears
        or any(item.status == "active" for item in result.evidence)
    )
    if (
        has_evidence
        and has_support
        and probability >= required
        and margin >= policy.base_margin
    ):
        if target in result.pins:
            reason = "personally witnessed impostor action"
        elif structural:
            reason = "target appears in every surviving role assignment"
        else:
            reason = "accusation-backed public sources support the joint solve"
        return MeetingDecision(
            action="eject",
            target=target,
            probability=probability,
            required_probability=required,
            margin=margin,
            sources=sources,
            structural=structural,
            skip_loss_probability=skip_loss,
            wrong_eject_loss_probability=wrong_eject_loss,
            reason=reason,
            inference=result,
        )

    reason_parts: list[str] = []
    if not has_evidence:
        reason_parts.append("no deduction evidence")
    if not structural and policy.require_structural:
        reason_parts.append("target is not structurally implied")
    elif not structural and not has_accusation:
        reason_parts.append("ballot evidence lacks accusation or structural support")
    elif not has_support:
        reason_parts.append("insufficient independent or structural support")
    if probability < required:
        reason_parts.append("posterior below parity-aware threshold")
    if margin < policy.base_margin:
        reason_parts.append("leading set is not separated")
    return MeetingDecision(
        action="skip",
        target=None,
        probability=probability,
        required_probability=required,
        margin=margin,
        sources=sources,
        structural=structural,
        skip_loss_probability=skip_loss,
        wrong_eject_loss_probability=wrong_eject_loss,
        reason="; ".join(reason_parts) or "vote not justified",
        inference=result,
    )


def _skip(
    inference: InferenceResult,
    *,
    reason: str,
    required_probability: float,
) -> MeetingDecision:
    return MeetingDecision(
        action="skip",
        target=None,
        probability=0.0,
        required_probability=required_probability,
        margin=0.0,
        sources=(),
        structural=False,
        skip_loss_probability=0.0,
        wrong_eject_loss_probability=0.0,
        reason=reason,
        inference=inference,
    )


def _live_targets(history: DeductionHistory) -> tuple[str, ...]:
    dead = {event.color for event in history.events if isinstance(event, DeathObserved)}
    return tuple(
        color
        for color in history.game.players
        if color not in dead and color != history.game.self_color
    )


def _parity_risks(
    history: DeductionHistory,
    inference: InferenceResult,
    *,
    target: str,
    live: tuple[str, ...],
) -> tuple[float, float]:
    alive = frozenset(live) | {history.game.self_color}
    skip_loss = 0.0
    wrong_eject_loss = 0.0
    for hypothesis in inference.hypotheses:
        alive_impostors = len(alive & set(hypothesis.imposters))
        alive_crew = len(alive) - alive_impostors
        if alive_impostors >= max(0, alive_crew - 1):
            skip_loss += hypothesis.probability
        if (
            target not in hypothesis.imposters
            # Wrong eject removes one crew, then the ordinary next kill removes
            # another before crew can correct the silent error.
            and alive_impostors >= max(0, alive_crew - 2)
        ):
            wrong_eject_loss += hypothesis.probability
    return min(skip_loss, 1.0), min(wrong_eject_loss, 1.0)
