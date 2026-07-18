"""Replay a hosted event warehouse through the current social-claim solver.

This is an offline regression gate, not a game-result estimator. It measures
which roles the parser targets and what the social-only solver would pick at the
standard deadline, without reconstructing private perception or suspicion priors.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import duckdb

from crewborg.perception.entities import VoteCandidate, VotingState
from crewborg.strategy.meeting.solver import solver_report
from crewborg.strategy.social_evidence import parse_social_claims
from crewborg.types import Belief, ChatEvent, MeetingRecord, PlayerRecord

VOTE_DECISION_OFFSET_TICKS = 1152
COLOR_RE = re.compile(r"^([a-z]+)\(", re.IGNORECASE)


def _events(warehouse: Path, key: str) -> str:
    return str(warehouse / "events" / f"key={key}" / "*.parquet")


def _color(label: str | None) -> str | None:
    match = COLOR_RE.match(label or "")
    return match.group(1).lower() if match else None


def _json_value(raw: str) -> dict[str, Any]:
    return json.loads(raw)


def analyze(warehouse: Path, *, include_details: bool = False) -> dict[str, Any]:
    os.environ["CREWBORG_SOLVER"] = "1"
    os.environ["CREWBORG_SOLVER_VETO"] = "0"
    con = duckdb.connect()

    player_rows = con.execute(
        f"SELECT episode_id, slot, policy_version, role "
        f"FROM read_parquet('{warehouse}/episode_players.parquet')"
    ).fetchall()
    identities = {
        (episode_id, slot): {"policy_version": policy_version, "role": role}
        for episode_id, slot, policy_version, role in player_rows
    }
    episodes = sorted({episode_id for episode_id, _, _, _ in player_rows})

    color_rows = con.execute(
        f"SELECT episode_id, slot, value FROM read_parquet('{_events(warehouse, 'player_joined')}')"
    ).fetchall()
    colors: dict[str, dict[int, str]] = defaultdict(dict)
    for episode_id, slot, raw in color_rows:
        color = _color(_json_value(raw)["label"])
        if color is not None:
            colors[episode_id][slot] = color

    def rows_for(key: str) -> dict[str, list[tuple[Any, ...]]]:
        rows = con.execute(
            f"SELECT episode_id, ts, slot, value "
            f"FROM read_parquet('{_events(warehouse, key)}') ORDER BY episode_id, ts, slot"
        ).fetchall()
        grouped: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
        for row in rows:
            grouped[row[0]].append(row)
        return grouped

    phase_rows = rows_for("phase")
    chat_rows = rows_for("chat")
    vote_rows = rows_for("vote_cast")
    died_rows = rows_for("died")

    by_arm: dict[str, dict[str, Any]] = {}
    for episode_id in episodes:
        slot_colors = colors.get(episode_id, {})
        if len(slot_colors) < 2 or (episode_id, 0) not in identities:
            continue
        arm = identities[(episode_id, 0)]["policy_version"]
        stats = by_arm.setdefault(
            arm,
            {
                "episodes": 0,
                "chat_lines": 0,
                "claim_lines": 0,
                "raw_claims": 0,
                "accusation_targets": 0,
                "correct_accusation_targets": 0,
                "relayed_claims": 0,
                "false_targets": Counter(),
                "eligible_meetings": 0,
                "solver_picks": 0,
                "correct_solver_picks": 0,
                "solver_targets": Counter(),
            },
        )
        stats["episodes"] += 1
        if include_details:
            stats.setdefault("decisions", [])
        imposter_colors = {
            color
            for slot, color in slot_colors.items()
            if identities.get((episode_id, slot), {}).get("role") == "imposter"
        }
        subject_color = slot_colors[0]
        roster_colors = set(slot_colors.values())
        claims = []
        meetings: list[MeetingRecord] = []

        voting_starts = [
            ts
            for _, ts, _, raw in phase_rows.get(episode_id, ())
            if _json_value(raw).get("phase") == "Voting"
        ]
        phase_changes = [ts for _, ts, _, _ in phase_rows.get(episode_id, ())]
        for meeting_id in voting_starts:
            end = min((ts for ts in phase_changes if ts > meeting_id), default=10**18)
            cutoff = min(end, meeting_id + VOTE_DECISION_OFFSET_TICKS)
            meeting_chats = [
                row
                for row in chat_rows.get(episode_id, ())
                if meeting_id <= row[1] < cutoff
            ]
            for _, ts, slot, raw in meeting_chats:
                text = _json_value(raw).get("text") or ""
                speaker = slot_colors.get(slot)
                parsed = parse_social_claims(
                    ChatEvent(tick=ts, speaker_color=speaker, text=text),
                    meeting_id=meeting_id,
                    colors=roster_colors,
                )
                stats["chat_lines"] += 1
                if parsed:
                    stats["claim_lines"] += 1
                stats["raw_claims"] += len(parsed)
                stats["relayed_claims"] += sum(
                    getattr(claim, "provenance", "direct") == "relayed"
                    for claim in parsed
                )
                for claim in parsed:
                    if claim.stance not in {"accuse", "at_least_one"}:
                        continue
                    for target in claim.targets:
                        stats["accusation_targets"] += 1
                        if target in imposter_colors:
                            stats["correct_accusation_targets"] += 1
                        else:
                            stats["false_targets"][target] += 1
                claims.extend(parsed)

            votes: dict[str, str | None] = {}
            for _, ts, slot, raw in vote_rows.get(episode_id, ()):
                if not (meeting_id <= ts < cutoff):
                    continue
                payload = _json_value(raw)
                voter = slot_colors.get(slot)
                if voter is None:
                    continue
                target_slot = payload.get("target_slot")
                votes[voter] = (
                    slot_colors.get(target_slot) if target_slot is not None else None
                )
            meetings.append(MeetingRecord(meeting_id=meeting_id, votes=votes))

            dead_slots = {
                slot for _, ts, slot, _ in died_rows.get(episode_id, ()) if ts < cutoff
            }
            if 0 in dead_slots:
                continue
            stats["eligible_meetings"] += 1
            belief = Belief(
                self_color=subject_color,
                self_role="crewmate",
                total_player_count=len(slot_colors),
                imposter_count=len(imposter_colors),
                social_claims=list(claims),
                meeting_history=list(meetings),
            )
            for slot, color in slot_colors.items():
                belief.roster[color] = PlayerRecord(
                    color=color,
                    life_status="dead" if slot in dead_slots else "alive",
                )
            belief.voting = VotingState(
                candidates=tuple(
                    VoteCandidate(slot=slot, color=color, alive=slot not in dead_slots)
                    for slot, color in sorted(slot_colors.items())
                ),
                self_marker_color=subject_color,
            )
            report = solver_report(belief)
            pick = report.get("pick")
            if pick is not None:
                stats["solver_picks"] += 1
                stats["solver_targets"][pick] += 1
                if pick in imposter_colors:
                    stats["correct_solver_picks"] += 1
            if include_details:
                candidate = report.get("pre_robust_pick") or report.get("top_candidate")
                candidate_sources = {
                    claim.source_color or claim.speaker_color
                    for claim in claims
                    if candidate is not None
                    and claim.stance in {"accuse", "at_least_one"}
                    and candidate in claim.targets
                }
                current_vote_support = sum(
                    target == candidate for target in votes.values()
                )
                persistent_vote_support = sum(
                    target == candidate
                    for recorded_meeting in meetings
                    for target in recorded_meeting.votes.values()
                )
                actual_vote = None
                for _, ts, slot, raw in vote_rows.get(episode_id, ()):
                    if slot != 0 or not (meeting_id <= ts < end):
                        continue
                    target_slot = _json_value(raw).get("target_slot")
                    actual_vote = (
                        slot_colors.get(target_slot)
                        if target_slot is not None
                        else None
                    )
                    break
                stats["decisions"].append(
                    {
                        "episode_id": episode_id,
                        "meeting_id": meeting_id,
                        "pick": candidate,
                        "selected": pick is not None,
                        "correct": (
                            candidate in imposter_colors
                            if candidate is not None
                            else None
                        ),
                        "actual_vote": actual_vote,
                        "actual_vote_correct": (
                            actual_vote in imposter_colors
                            if actual_vote is not None
                            else None
                        ),
                        "candidate_sources": sorted(
                            source
                            for source in candidate_sources
                            if source is not None
                        ),
                        "current_vote_support": current_vote_support,
                        "persistent_vote_support": persistent_vote_support,
                        "imposters": sorted(imposter_colors),
                        "report": report,
                        "support": [
                            {
                                "meeting_id": claim.meeting_id,
                                "tick": claim.tick,
                                "speaker": claim.speaker_color,
                                "source": claim.source_color,
                                "provenance": claim.provenance,
                                "stance": claim.stance,
                                "targets": claim.targets,
                                "evidence": claim.evidence_kind,
                                "text": claim.text,
                            }
                            for claim in claims
                            if candidate is not None and candidate in claim.targets
                        ],
                    }
                )

    for stats in by_arm.values():
        target_count = stats["accusation_targets"]
        pick_count = stats["solver_picks"]
        meeting_count = stats["eligible_meetings"]
        stats["claim_target_precision"] = (
            stats["correct_accusation_targets"] / target_count if target_count else None
        )
        stats["solver_pick_precision"] = (
            stats["correct_solver_picks"] / pick_count if pick_count else None
        )
        stats["solver_pick_coverage"] = (
            pick_count / meeting_count if meeting_count else None
        )
        stats["false_targets"] = dict(stats["false_targets"].most_common())
        stats["solver_targets"] = dict(stats["solver_targets"].most_common())
    return by_arm


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("warehouse", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    result = analyze(args.warehouse, include_details=args.details)
    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.out is not None:
        args.out.write_text(payload + "\n")
    print(payload)


if __name__ == "__main__":
    main()
