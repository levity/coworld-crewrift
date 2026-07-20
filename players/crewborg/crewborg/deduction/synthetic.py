"""Seeded synthetic histories for cheap solver-policy evaluation.

This is not a simulator substitute. It generates semantic observations and raw
meeting text from an independent behavioral model, then evaluates the exact
production parser, inference, and decision functions.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from crewborg.deduction.decision import DecisionConfig, decide
from crewborg.deduction.inference import InferenceConfig, infer
from crewborg.deduction.model import (
    DeathObserved,
    DeductionHistory,
    GameSpec,
    MeetingObserved,
    UtteranceObserved,
    VoteObserved,
)

DEFAULT_COLORS = (
    "white",
    "red",
    "blue",
    "yellow",
    "green",
    "purple",
    "orange",
    "cyan",
)


@dataclass(frozen=True)
class SyntheticBehavior:
    meetings: int = 3
    speak_probability: float = 0.60
    crew_accusation_accuracy: float = 0.62
    imp_accuses_crew_probability: float = 0.78
    crew_vote_accuracy: float = 0.56
    imp_votes_crew_probability: float = 0.84
    kill_between_meetings_probability: float = 0.75


@dataclass(frozen=True)
class SyntheticGame:
    history: DeductionHistory
    imposters: tuple[str, ...]
    live_targets: tuple[str, ...]


@dataclass(frozen=True)
class SyntheticEvaluation:
    games: int
    top_target_accuracy: float
    vote_precision: float
    vote_coverage: float
    true_pair_top_accuracy: float
    mean_true_pair_probability: float
    murder_clear_failures: int

    def as_dict(self) -> dict[str, int | float]:
        return {
            "games": self.games,
            "top_target_accuracy": round(self.top_target_accuracy, 4),
            "vote_precision": round(self.vote_precision, 4),
            "vote_coverage": round(self.vote_coverage, 4),
            "true_pair_top_accuracy": round(self.true_pair_top_accuracy, 4),
            "mean_true_pair_probability": round(
                self.mean_true_pair_probability,
                4,
            ),
            "murder_clear_failures": self.murder_clear_failures,
        }


def generate_game(
    rng: random.Random,
    *,
    behavior: SyntheticBehavior | None = None,
    colors: tuple[str, ...] = DEFAULT_COLORS,
) -> SyntheticGame:
    behavior = behavior or SyntheticBehavior()
    self_color = colors[0]
    imposters = tuple(sorted(rng.sample(list(colors[1:]), 2)))
    alive = set(colors)
    events = []
    event_index = 0

    for meeting_index in range(behavior.meetings):
        if meeting_index and rng.random() < behavior.kill_between_meetings_probability:
            victims = sorted(alive - set(imposters) - {self_color})
            if victims:
                victim = rng.choice(victims)
                alive.remove(victim)
                event_index += 1
                events.append(
                    DeathObserved(
                        event_id=f"synthetic:{event_index}:death:{victim}",
                        tick=meeting_index * 1000 - 10,
                        color=victim,
                        source=rng.choice(("body", "census")),
                    )
                )

        meeting_id = meeting_index * 1000
        event_index += 1
        events.append(
            MeetingObserved(
                event_id=f"synthetic:{event_index}:meeting",
                tick=meeting_id,
                meeting_id=meeting_id,
                caller=rng.choice(sorted(alive)),
                call_kind=rng.choice(("body", "button")),
            )
        )
        for speaker in sorted(alive - {self_color}):
            if rng.random() >= behavior.speak_probability:
                continue
            target = _accusation_target(
                rng,
                actor=speaker,
                alive=alive,
                imposters=set(imposters),
                crew_accuracy=behavior.crew_accusation_accuracy,
                imp_targets_crew=behavior.imp_accuses_crew_probability,
            )
            if target is None:
                continue
            event_index += 1
            events.append(
                UtteranceObserved(
                    event_id=f"synthetic:{event_index}:chat",
                    tick=meeting_id + 100 + event_index,
                    meeting_id=meeting_id,
                    speaker=speaker,
                    text=rng.choice(
                        (
                            f"{target} sus",
                            f"vote {target}",
                            f"{target} looks suspicious",
                            f"I saw {target} near the body",
                        )
                    ),
                )
            )

        for voter in sorted(alive - {self_color}):
            target = _accusation_target(
                rng,
                actor=voter,
                alive=alive,
                imposters=set(imposters),
                crew_accuracy=behavior.crew_vote_accuracy,
                imp_targets_crew=behavior.imp_votes_crew_probability,
            )
            event_index += 1
            events.append(
                VoteObserved(
                    event_id=f"synthetic:{event_index}:vote",
                    tick=meeting_id + 800 + event_index,
                    meeting_id=meeting_id,
                    voter=voter,
                    target=target,
                )
            )

    history = DeductionHistory(
        game=GameSpec(
            players=colors,
            self_color=self_color,
            self_role="crewmate",
            imposter_count=2,
        ),
        events=tuple(sorted(events, key=lambda event: (event.tick, event.event_id))),
    )
    return SyntheticGame(
        history=history,
        imposters=imposters,
        live_targets=tuple(
            color for color in colors if color in alive and color != self_color
        ),
    )


def evaluate_synthetic(
    games: int,
    *,
    seed: int,
    behavior: SyntheticBehavior | None = None,
    inference_config: InferenceConfig | None = None,
    decision_config: DecisionConfig | None = None,
) -> SyntheticEvaluation:
    rng = random.Random(seed)
    top_correct = 0
    votes = 0
    correct_votes = 0
    top_pairs = 0
    pair_probability = 0.0
    murder_clear_failures = 0
    for _ in range(games):
        game = generate_game(rng, behavior=behavior)
        result = infer(game.history, config=inference_config)
        live_ranked = sorted(
            ((color, result.marginal(color)) for color in game.live_targets),
            key=lambda item: (-item[1], item[0]),
        )
        if live_ranked and live_ranked[0][0] in game.imposters:
            top_correct += 1
        if result.hypotheses:
            if set(result.hypotheses[0].imposters) == set(game.imposters):
                top_pairs += 1
            pair_probability += next(
                (
                    hypothesis.probability
                    for hypothesis in result.hypotheses
                    if set(hypothesis.imposters) == set(game.imposters)
                ),
                0.0,
            )
        murdered = {
            event.color
            for event in game.history.events
            if isinstance(event, DeathObserved) and event.source in {"body", "census"}
        }
        murder_clear_failures += sum(result.marginal(color) > 0.0 for color in murdered)
        decision = decide(
            game.history,
            live_targets=game.live_targets,
            inference_config=inference_config,
            decision_config=decision_config,
        )
        if decision.action == "eject" and decision.target is not None:
            votes += 1
            correct_votes += decision.target in game.imposters

    denominator = max(games, 1)
    return SyntheticEvaluation(
        games=games,
        top_target_accuracy=top_correct / denominator,
        vote_precision=correct_votes / max(votes, 1),
        vote_coverage=votes / denominator,
        true_pair_top_accuracy=top_pairs / denominator,
        mean_true_pair_probability=pair_probability / denominator,
        murder_clear_failures=murder_clear_failures,
    )


def _accusation_target(
    rng: random.Random,
    *,
    actor: str,
    alive: set[str],
    imposters: set[str],
    crew_accuracy: float,
    imp_targets_crew: float,
) -> str | None:
    available = alive - {actor}
    if not available:
        return None
    actor_is_imp = actor in imposters
    if actor_is_imp:
        targets_crew = rng.random() < imp_targets_crew
        desired = available - imposters if targets_crew else available & imposters
    else:
        targets_impostor = rng.random() < crew_accuracy
        desired = available & imposters if targets_impostor else available - imposters
    if not desired:
        desired = available
    return rng.choice(sorted(desired))
