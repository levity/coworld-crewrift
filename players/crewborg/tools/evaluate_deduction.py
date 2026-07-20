#!/usr/bin/env python3
"""Evaluate deduction from synthetic games or labeled history JSONL."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from crewborg.deduction.decision import (
    DecisionConfig,
    decide,
    decide_from_inference,
)
from crewborg.deduction.inference import infer
from crewborg.deduction.model import (
    DeathObserved,
    DeductionHistory,
    GameSpec,
    MeetingObserved,
    UtteranceObserved,
    VoteObserved,
)
from crewborg.deduction.synthetic import evaluate_synthetic

DECISION_OFFSET_TICKS = 1152
COLOR_RE = re.compile(r"^([a-z]+)\(", re.IGNORECASE)
CALIBRATION_EDGES = (0.0, 0.5, 0.65, 0.8, 0.9, 1.0000001)
THRESHOLD_GRID = (
    ("55/70", 0.55, 0.70),
    ("60/75", 0.60, 0.75),
    ("65/80", 0.65, 0.80),
    ("70/85", 0.70, 0.85),
    ("75/90", 0.75, 0.90),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--history-jsonl",
        type=Path,
        help=(
            "JSONL rows with history=<DeductionHistory>, imposters=[colors], "
            "and optional live_targets=[colors]"
        ),
    )
    parser.add_argument(
        "--warehouse",
        type=Path,
        help="Existing Crewrift event-warehouse directory",
    )
    parser.add_argument(
        "--decision-offset",
        type=int,
        default=DECISION_OFFSET_TICKS,
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=0,
        help="Include up to N diverse meeting narratives in warehouse output",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="Include one compact decision row per eligible meeting",
    )
    args = parser.parse_args()
    if args.history_jsonl is not None and args.warehouse is not None:
        parser.error("choose only one of --history-jsonl and --warehouse")
    if args.warehouse is not None:
        print(
            json.dumps(
                _evaluate_warehouse(
                    args.warehouse,
                    decision_offset=args.decision_offset,
                    sample_count=max(0, args.samples),
                    include_details=args.details,
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return
    if args.history_jsonl is None:
        print(
            json.dumps(
                evaluate_synthetic(args.games, seed=args.seed).as_dict(),
                indent=2,
                sort_keys=True,
            )
        )
        return
    print(
        json.dumps(
            _evaluate_jsonl(args.history_jsonl),
            indent=2,
            sort_keys=True,
        )
    )


def _evaluate_jsonl(path: Path) -> dict[str, int | float]:
    games = 0
    top_correct = 0
    votes = 0
    correct_votes = 0
    pair_top = 0
    for line_number, raw in enumerate(path.read_text().splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
            history = DeductionHistory.model_validate(row["history"])
            truth = set(row["imposters"])
        except Exception as exc:
            raise ValueError(
                f"{path}:{line_number}: invalid history row: {exc}"
            ) from exc
        live = tuple(row.get("live_targets") or ())
        result = infer(history)
        ranked = sorted(
            (
                (color, result.marginal(color))
                for color in (live or tuple(dict(result.marginals)))
            ),
            key=lambda item: (-item[1], item[0]),
        )
        games += 1
        top_correct += bool(ranked and ranked[0][0] in truth)
        pair_top += bool(
            result.hypotheses and set(result.hypotheses[0].imposters) == truth
        )
        decision = decide(
            history,
            live_targets=live or None,
        )
        if decision.action == "eject" and decision.target is not None:
            votes += 1
            correct_votes += decision.target in truth
    return {
        "games": games,
        "top_target_accuracy": round(top_correct / max(games, 1), 4),
        "true_pair_top_accuracy": round(pair_top / max(games, 1), 4),
        "vote_coverage": round(votes / max(games, 1), 4),
        "vote_precision": round(correct_votes / max(votes, 1), 4),
    }


def _evaluate_warehouse(
    warehouse: Path,
    *,
    decision_offset: int,
    sample_count: int,
    include_details: bool = False,
) -> dict[str, Any]:
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError(
            "warehouse evaluation requires duckdb; use the event-warehouse venv"
        ) from exc

    con = duckdb.connect()
    player_rows = con.execute(
        "SELECT episode_id, slot, policy_version, role "
        f"FROM read_parquet('{warehouse}/episode_players.parquet')"
    ).fetchall()
    identities = {
        (episode_id, slot): {
            "policy_version": policy_version,
            "role": role,
        }
        for episode_id, slot, policy_version, role in player_rows
    }
    color_rows = con.execute(
        "SELECT episode_id, slot, value "
        f"FROM read_parquet('{_event_glob(warehouse, 'player_joined')}')"
    ).fetchall()
    colors: dict[str, dict[int, str]] = defaultdict(dict)
    for episode_id, slot, raw in color_rows:
        label = _json_value(raw).get("label") or ""
        match = COLOR_RE.match(label)
        if match is not None:
            colors[episode_id][slot] = match.group(1).lower()

    phase_rows = _rows_for(con, warehouse, "phase")
    chat_rows = _rows_for(con, warehouse, "chat")
    vote_rows = _rows_for(con, warehouse, "vote_cast")
    kill_rows = _rows_for(con, warehouse, "kill")
    died_rows = _rows_for(con, warehouse, "died")
    totals: dict[str, int] = defaultdict(int)
    errors: dict[str, int] = defaultdict(int)
    samples_by_category: dict[str, dict[str, Any]] = {}
    top_calibration: dict[str, dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    vote_calibration: dict[str, dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    threshold_results: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    decisions: list[dict[str, Any]] = []
    excluded_trace_episodes = _trace_warning_episodes(con, warehouse)

    for episode_id, slot_colors in colors.items():
        if episode_id in excluded_trace_episodes:
            continue
        subject = identities.get((episode_id, 0))
        if subject is None or subject["role"] not in {"crew", "crewmate"}:
            continue
        truth = {
            color
            for slot, color in slot_colors.items()
            if identities.get((episode_id, slot), {}).get("role") == "imposter"
        }
        if not truth:
            continue
        self_color = slot_colors.get(0)
        if self_color is None:
            continue
        players = tuple(color for _, color in sorted(slot_colors.items()))
        history_events = []
        recorded_deaths: set[str] = set()
        voting_starts = [
            int(ts)
            for _, ts, _, raw in phase_rows.get(episode_id, ())
            if _json_value(raw).get("phase") == "Voting"
        ]
        phase_changes = [int(ts) for _, ts, _, _ in phase_rows.get(episode_id, ())]
        for meeting_id in voting_starts:
            end = min(
                (tick for tick in phase_changes if tick > meeting_id),
                default=10**18,
            )
            cutoff = min(end, meeting_id + decision_offset)
            history_events.append(
                MeetingObserved(
                    event_id=f"{episode_id}:meeting:{meeting_id}",
                    tick=meeting_id,
                    meeting_id=meeting_id,
                    call_kind="unknown",
                )
            )
            kill_ticks_by_slot = {}
            for _, ts, _, raw in kill_rows.get(episode_id, ()):
                if ts >= cutoff:
                    continue
                victim_slot = _json_value(raw).get("victim_slot")
                if victim_slot is not None:
                    kill_ticks_by_slot[victim_slot] = int(ts)
            killed_slots = set(kill_ticks_by_slot)
            for _, ts, dead_slot, _ in died_rows.get(episode_id, ()):
                if ts >= cutoff:
                    continue
                color = slot_colors.get(dead_slot)
                if color is None or color in recorded_deaths:
                    continue
                recorded_deaths.add(color)
                history_events.append(
                    DeathObserved(
                        event_id=f"{episode_id}:death:{color}:{int(ts)}",
                        tick=int(ts),
                        color=color,
                        source=("census" if dead_slot in killed_slots else "ejection"),
                    )
                )
            for killed_slot, kill_tick in sorted(kill_ticks_by_slot.items()):
                color = slot_colors.get(killed_slot)
                if color is None or color in recorded_deaths:
                    continue
                recorded_deaths.add(color)
                history_events.append(
                    DeathObserved(
                        event_id=f"{episode_id}:death:{color}:{kill_tick}",
                        tick=kill_tick,
                        color=color,
                        source="census",
                    )
                )
            meeting_chats = []
            for _, ts, speaker_slot, raw in chat_rows.get(episode_id, ()):
                if not (meeting_id <= ts < cutoff):
                    continue
                event = UtteranceObserved(
                    event_id=(
                        f"{episode_id}:chat:{meeting_id}:{int(ts)}:{speaker_slot}"
                    ),
                    tick=int(ts),
                    meeting_id=meeting_id,
                    speaker=slot_colors.get(speaker_slot),
                    text=_json_value(raw).get("text") or "",
                )
                history_events.append(event)
                meeting_chats.append(event)
            meeting_votes = []
            for _, ts, voter_slot, raw in vote_rows.get(episode_id, ()):
                if not (meeting_id <= ts < cutoff):
                    continue
                target_slot = _json_value(raw).get("target_slot")
                event = VoteObserved(
                    event_id=(f"{episode_id}:vote:{meeting_id}:{voter_slot}"),
                    tick=int(ts),
                    meeting_id=meeting_id,
                    voter=slot_colors.get(voter_slot, ""),
                    target=slot_colors.get(target_slot),
                )
                history_events.append(event)
                meeting_votes.append(event)
            history = DeductionHistory(
                game=GameSpec(
                    players=players,
                    self_color=self_color,
                    self_role="crewmate",
                    imposter_count=len(truth),
                ),
                events=tuple(
                    sorted(
                        history_events,
                        key=lambda event: (event.tick, event.event_id),
                    )
                ),
            )
            dead = {
                event.color
                for event in history.events
                if isinstance(event, DeathObserved)
            }
            if self_color in dead:
                continue
            live = tuple(
                color for color in players if color != self_color and color not in dead
            )
            result = infer(history)
            decision = decide_from_inference(
                history,
                result,
                live_targets=live,
            )
            totals["meetings"] += 1
            if result.error is not None:
                errors[result.error] += 1
            ranked = sorted(
                ((color, result.marginal(color)) for color in live),
                key=lambda item: (-item[1], item[0]),
            )
            totals["top_correct"] += bool(ranked and ranked[0][0] in truth)
            if ranked:
                _add_calibration(
                    top_calibration,
                    probability=ranked[0][1],
                    correct=ranked[0][0] in truth,
                )
            totals["pair_top"] += bool(
                result.hypotheses and set(result.hypotheses[0].imposters) == truth
            )
            totals["votes"] += decision.action == "eject"
            totals["correct_votes"] += (
                decision.action == "eject" and decision.target in truth
            )
            if include_details:
                decisions.append(
                    _decision_detail(
                        episode_id=episode_id,
                        meeting_id=meeting_id,
                        truth=truth,
                        live=live,
                        ranked=ranked,
                        result=result,
                        decision=decision,
                    )
                )
            if decision.action == "eject":
                _add_calibration(
                    vote_calibration,
                    probability=decision.probability,
                    correct=decision.target in truth,
                )
            for label, base_probability, dangerous_probability in THRESHOLD_GRID:
                alternative = decide_from_inference(
                    history,
                    result,
                    live_targets=live,
                    decision_config=DecisionConfig(
                        base_probability=base_probability,
                        dangerous_wrong_eject_probability=dangerous_probability,
                    ),
                )
                threshold_results[label]["votes"] += (
                    alternative.action == "eject"
                )
                threshold_results[label]["correct"] += (
                    alternative.action == "eject"
                    and alternative.target in truth
                )
            totals["chat_events"] += sum(
                isinstance(event, UtteranceObserved) for event in history.events
            )
            totals["vote_events"] += sum(
                isinstance(event, VoteObserved) for event in history.events
            )
            if decision.action == "eject":
                category = (
                    "correct_eject" if decision.target in truth else "wrong_eject"
                )
            elif ranked and ranked[0][0] in truth:
                category = "correct_top_skip"
            else:
                category = "other_skip"
            if sample_count and category not in samples_by_category:
                samples_by_category[category] = _sample_snapshot(
                    episode_id=episode_id,
                    meeting_id=meeting_id,
                    self_color=self_color,
                    truth=truth,
                    chats=meeting_chats,
                    votes=meeting_votes,
                    kills=[
                        {
                            "tick": int(ts),
                            "killer": slot_colors.get(killer_slot),
                            "victim": slot_colors.get(
                                _json_value(raw).get("victim_slot")
                            ),
                        }
                        for _, ts, killer_slot, raw in kill_rows.get(
                            episode_id,
                            (),
                        )
                        if ts < cutoff
                    ],
                    decision=decision,
                    ranked=ranked,
                )

    meetings = totals["meetings"]
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
        "vote_coverage": round(totals["votes"] / max(meetings, 1), 4),
        "vote_precision": round(
            totals["correct_votes"] / max(totals["votes"], 1),
            4,
        ),
        "chat_events": totals["chat_events"],
        "vote_events": totals["vote_events"],
        "top_calibration": _calibration_rows(top_calibration),
        "vote_calibration": _calibration_rows(vote_calibration),
        "threshold_sensitivity": {
            label: {
                "votes": values["votes"],
                "correct": values["correct"],
                "coverage": round(values["votes"] / max(meetings, 1), 4),
                "precision": round(
                    values["correct"] / max(values["votes"], 1),
                    4,
                ),
            }
            for label, values in threshold_results.items()
        },
        "errors": {error: count for error, count in errors.items() if count},
        "excluded_trace_episodes": sorted(excluded_trace_episodes),
    }
    if sample_count:
        preferred = (
            "correct_eject",
            "wrong_eject",
            "correct_top_skip",
            "other_skip",
        )
        output["samples"] = [
            samples_by_category[category]
            for category in preferred
            if category in samples_by_category
        ][:sample_count]
    if include_details:
        output["decisions"] = decisions
    return output


def _trace_warning_episodes(con: Any, warehouse: Path) -> set[str]:
    warning_dir = warehouse / "events" / "key=trace_warning"
    if not any(warning_dir.glob("*.parquet")):
        return set()
    return {
        episode_id
        for (episode_id,) in con.execute(
            "SELECT DISTINCT episode_id "
            f"FROM read_parquet('{_event_glob(warehouse, 'trace_warning')}')"
        ).fetchall()
    }


def _decision_detail(
    *,
    episode_id: str,
    meeting_id: int,
    truth: set[str],
    live: tuple[str, ...],
    ranked: list[tuple[str, float]],
    result: Any,
    decision: Any,
) -> dict[str, Any]:
    top_target, top_probability = ranked[0] if ranked else (None, 0.0)
    return {
        "episode_id": episode_id,
        "meeting_id": meeting_id,
        "imposters": sorted(truth),
        "live_targets": list(live),
        "top_target": top_target,
        "top_probability": round(top_probability, 6),
        "top_correct": top_target in truth,
        "marginals": {
            color: round(probability, 6) for color, probability in result.marginals
        },
        "true_pair_top": bool(
            result.hypotheses and set(result.hypotheses[0].imposters) == truth
        ),
        "action": decision.action,
        "target": decision.target,
        "correct": (
            decision.target in truth if decision.action == "eject" else None
        ),
        "probability": round(decision.probability, 6),
        "required_probability": round(decision.required_probability, 6),
        "margin": round(decision.margin, 6),
        "sources": list(decision.sources),
        "structural": decision.structural,
        "reason": decision.reason,
        "active_evidence": [
            {
                "channel": evidence.channel,
                "source": evidence.source,
                "targets": list(evidence.targets),
                "stance": evidence.stance,
                "weight": round(evidence.weight, 6),
            }
            for evidence in result.evidence
            if evidence.status == "active"
        ],
    }


def _sample_snapshot(
    *,
    episode_id: str,
    meeting_id: int,
    self_color: str,
    truth: set[str],
    chats: list[UtteranceObserved],
    votes: list[VoteObserved],
    kills: list[dict[str, Any]],
    decision: Any,
    ranked: list[tuple[str, float]],
) -> dict[str, Any]:
    active = [
        {
            "channel": evidence.channel,
            "source": evidence.source,
            "targets": list(evidence.targets),
            "stance": evidence.stance,
            "weight": round(evidence.weight, 3),
        }
        for evidence in decision.inference.evidence
        if evidence.status == "active"
    ]
    return {
        "episode_id": episode_id,
        "meeting_id": meeting_id,
        "self_color": self_color,
        "imposters": sorted(truth),
        "kills_before_decision": kills,
        "utterances": [
            {
                "tick": event.tick,
                "speaker": event.speaker,
                "text": event.text,
            }
            for event in chats
        ],
        "votes": [
            {
                "tick": event.tick,
                "voter": event.voter,
                "target": event.target,
            }
            for event in votes
        ],
        "top_marginals": [
            [color, round(probability, 4)] for color, probability in ranked[:4]
        ],
        "decision": {
            "action": decision.action,
            "target": decision.target,
            "probability": round(decision.probability, 4),
            "required_probability": round(
                decision.required_probability,
                4,
            ),
            "margin": round(decision.margin, 4),
            "sources": list(decision.sources),
            "structural": decision.structural,
            "reason": decision.reason,
        },
        "active_evidence": active,
    }


def _event_glob(warehouse: Path, key: str) -> str:
    return str(warehouse / "events" / f"key={key}" / "*.parquet")


def _add_calibration(
    buckets: dict[str, dict[str, float]],
    *,
    probability: float,
    correct: bool,
) -> None:
    for lower, upper in zip(CALIBRATION_EDGES, CALIBRATION_EDGES[1:]):
        if lower <= probability < upper:
            label = f"{lower:.2f}-{min(upper, 1.0):.2f}"
            buckets[label]["count"] += 1
            buckets[label]["correct"] += int(correct)
            buckets[label]["probability_sum"] += probability
            return


def _calibration_rows(
    buckets: dict[str, dict[str, float]],
) -> list[dict[str, int | float | str]]:
    rows = []
    for label, values in sorted(buckets.items()):
        count = int(values["count"])
        rows.append(
            {
                "bucket": label,
                "count": count,
                "mean_probability": round(
                    values["probability_sum"] / max(count, 1),
                    4,
                ),
                "accuracy": round(values["correct"] / max(count, 1), 4),
            }
        )
    return rows


def _rows_for(con: Any, warehouse: Path, key: str) -> dict[str, list[tuple[Any, ...]]]:
    if not list((warehouse / "events" / f"key={key}").glob("*.parquet")):
        return {}
    rows = con.execute(
        "SELECT episode_id, ts, slot, value "
        f"FROM read_parquet('{_event_glob(warehouse, key)}') "
        "ORDER BY episode_id, ts, slot"
    ).fetchall()
    grouped: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    for row in rows:
        grouped[row[0]].append(row)
    return grouped


def _json_value(raw: str) -> dict[str, Any]:
    return json.loads(raw)


if __name__ == "__main__":
    main()
