#!/usr/bin/env python3
"""Audit deduction decisions on one deterministic set of synthetic histories."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from dataclasses import asdict
from typing import Any

from crewborg.deduction.decision import decide_from_inference
from crewborg.deduction.inference import InferenceConfig, infer
from crewborg.deduction.model import (
    DeathObserved,
    DeductionHistory,
    MeetingObserved,
    UtteranceObserved,
    VoteObserved,
)
from crewborg.deduction.synthetic import SyntheticBehavior, generate_game


VARIANTS = {
    "default": InferenceConfig(),
    "lower_vote_weight": InferenceConfig(vote_weight=0.20),
    "no_public_votes": InferenceConfig(vote_weight=0.0),
    "stronger_repeat_decay": InferenceConfig(
        repeat_decay=0.40,
        same_target_decay=0.55,
        vote_repeat_decay=0.40,
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--samples",
        type=int,
        default=5,
        help="Maximum wrong default decisions to include as compact timelines",
    )
    args = parser.parse_args()

    behavior = SyntheticBehavior()
    rng = random.Random(args.seed)
    games = [generate_game(rng, behavior=behavior) for _ in range(args.games)]
    output = {
        "games": args.games,
        "seed": args.seed,
        "behavior": asdict(behavior),
        "variants": {},
    }
    for name, config in VARIANTS.items():
        output["variants"][name] = _evaluate(
            games,
            config=config,
            sample_count=max(0, args.samples) if name == "default" else 0,
        )
    print(json.dumps(output, indent=2, sort_keys=True))


def _evaluate(
    games: list[Any],
    *,
    config: InferenceConfig,
    sample_count: int,
) -> dict[str, Any]:
    totals: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    wrong_profiles: Counter[tuple[int, int, str]] = Counter()
    selection_profiles: Counter[tuple[bool, int, int, str, str]] = Counter()
    samples = []
    for game_index, game in enumerate(games):
        totals["games"] += 1
        for meeting_id, history, live_targets in _meeting_snapshots(game):
            result = infer(history, config=config)
            decision = decide_from_inference(
                history,
                result,
                live_targets=live_targets,
            )
            ranked = sorted(
                (
                    (color, result.marginal(color))
                    for color in live_targets
                ),
                key=lambda item: (-item[1], item[0]),
            )
            totals["meetings"] += 1
            totals["top_correct"] += bool(
                ranked and ranked[0][0] in game.imposters
            )
            totals["pair_top"] += bool(
                result.hypotheses
                and set(result.hypotheses[0].imposters) == set(game.imposters)
            )
            reasons[decision.reason] += 1
            if decision.action != "eject" or decision.target is None:
                continue
            totals["votes"] += 1
            correct = decision.target in game.imposters
            totals["correct_votes"] += correct
            claim_sources, vote_sources = _target_sources(decision)
            threshold = f"{decision.required_probability:.2f}"
            probability_bucket = _probability_bucket(decision.probability)
            selection_profiles[
                (
                    correct,
                    len(claim_sources),
                    len(vote_sources),
                    threshold,
                    probability_bucket,
                )
            ] += 1
            if correct:
                continue
            wrong_profiles[(len(claim_sources), len(vote_sources), threshold)] += 1
            if len(samples) < sample_count:
                samples.append(
                    _wrong_sample(
                        game_index=game_index,
                        meeting_id=meeting_id,
                        history=history,
                        imposters=game.imposters,
                        decision=decision,
                        claim_sources=claim_sources,
                        vote_sources=vote_sources,
                        ranked=ranked,
                    )
                )

    meetings = totals["meetings"]
    votes = totals["votes"]
    output = {
        "meetings": meetings,
        "top_target_accuracy": round(
            totals["top_correct"] / max(meetings, 1),
            4,
        ),
        "true_pair_top_accuracy": round(
            totals["pair_top"] / max(meetings, 1),
            4,
        ),
        "vote_coverage": round(votes / max(meetings, 1), 4),
        "vote_precision": round(
            totals["correct_votes"] / max(votes, 1),
            4,
        ),
        "votes": votes,
        "correct_votes": totals["correct_votes"],
        "decision_reasons": dict(reasons.most_common()),
        "selection_profiles": [
            {
                "correct": correct,
                "claim_sources": claim_sources,
                "vote_sources": vote_sources,
                "required_probability": threshold,
                "probability_bucket": probability_bucket,
                "count": count,
            }
            for (
                correct,
                claim_sources,
                vote_sources,
                threshold,
                probability_bucket,
            ), count in sorted(selection_profiles.items())
        ],
        "wrong_vote_profiles": [
            {
                "claim_sources": claim_sources,
                "vote_sources": vote_sources,
                "required_probability": threshold,
                "count": count,
            }
            for (claim_sources, vote_sources, threshold), count in sorted(
                wrong_profiles.items()
            )
        ],
    }
    if sample_count:
        output["wrong_samples"] = samples
    return output


def _probability_bucket(probability: float) -> str:
    if probability < 0.70:
        return "0.65-0.70"
    if probability < 0.80:
        return "0.70-0.80"
    if probability < 0.90:
        return "0.80-0.90"
    return "0.90-1.00"


def _meeting_snapshots(
    game: Any,
) -> list[tuple[int, DeductionHistory, tuple[str, ...]]]:
    meeting_ids = sorted(
        event.meeting_id
        for event in game.history.events
        if isinstance(event, MeetingObserved)
    )
    snapshots = []
    for meeting_id in meeting_ids:
        events = tuple(
            event
            for event in game.history.events
            if (
                isinstance(event, DeathObserved) and event.tick <= meeting_id
            )
            or getattr(event, "meeting_id", meeting_id + 1) <= meeting_id
        )
        dead = {
            event.color for event in events if isinstance(event, DeathObserved)
        }
        live_targets = tuple(
            color
            for color in game.history.game.players
            if color != game.history.game.self_color and color not in dead
        )
        snapshots.append(
            (
                meeting_id,
                game.history.model_copy(update={"events": events}),
                live_targets,
            )
        )
    return snapshots


def _target_sources(decision: Any) -> tuple[set[str], set[str]]:
    claim_sources = set()
    vote_sources = set()
    for evidence in decision.inference.evidence:
        if (
            evidence.status != "active"
            or evidence.source is None
            or decision.target not in evidence.targets
        ):
            continue
        if evidence.channel == "claim" and evidence.stance in {
            "accuse",
            "at_least_one",
        }:
            claim_sources.add(evidence.source)
        elif evidence.channel == "vote":
            vote_sources.add(evidence.source)
    return claim_sources, vote_sources


def _wrong_sample(
    *,
    game_index: int,
    meeting_id: int,
    history: DeductionHistory,
    imposters: tuple[str, ...],
    decision: Any,
    claim_sources: set[str],
    vote_sources: set[str],
    ranked: list[tuple[str, float]],
) -> dict[str, Any]:
    timeline = []
    for event in history.events:
        if isinstance(event, UtteranceObserved):
            timeline.append(
                {
                    "tick": event.tick,
                    "kind": "chat",
                    "actor": event.speaker,
                    "text": event.text,
                }
            )
        elif isinstance(event, VoteObserved):
            timeline.append(
                {
                    "tick": event.tick,
                    "kind": "vote",
                    "actor": event.voter,
                    "target": event.target,
                }
            )
    return {
        "game_index": game_index,
        "meeting_id": meeting_id,
        "imposters": list(imposters),
        "target": decision.target,
        "probability": round(decision.probability, 4),
        "required_probability": round(decision.required_probability, 4),
        "margin": round(decision.margin, 4),
        "claim_sources": sorted(claim_sources),
        "vote_sources": sorted(vote_sources),
        "top_marginals": [
            [color, round(probability, 4)] for color, probability in ranked[:4]
        ],
        "timeline": timeline,
    }


if __name__ == "__main__":
    main()
