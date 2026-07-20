#!/usr/bin/env python3
"""Join legacy and append-only solver decisions on identical meeting histories."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("legacy_json", type=Path)
    parser.add_argument("deduction_json", type=Path)
    args = parser.parse_args()

    legacy = json.loads(args.legacy_json.read_text())
    if len(legacy) != 1:
        parser.error(
            "legacy JSON must contain exactly one policy arm; analyze each arm separately"
        )
    legacy_decisions = next(iter(legacy.values())).get("decisions")
    deduction_decisions = json.loads(args.deduction_json.read_text()).get(
        "decisions"
    )
    if legacy_decisions is None or deduction_decisions is None:
        parser.error("both inputs require detailed decision output")
    print(
        json.dumps(
            compare(legacy_decisions, deduction_decisions),
            indent=2,
            sort_keys=True,
        )
    )


def compare(
    legacy_decisions: list[dict[str, Any]],
    deduction_decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    legacy = {_key(row): row for row in legacy_decisions}
    deduction = {_key(row): row for row in deduction_decisions}
    shared = sorted(legacy.keys() & deduction.keys())
    disagreements = []
    for key in shared:
        old = legacy[key]
        new = deduction[key]
        old_selected = bool(old["selected"])
        new_selected = new["action"] == "eject"
        old_target = old["pick"] if old_selected else None
        new_target = new["target"] if new_selected else None
        if old_selected == new_selected and old_target == new_target:
            continue
        disagreements.append(
            {
                "episode_id": key[0],
                "meeting_id": key[1],
                "imposters": old["imposters"],
                "legacy": {
                    "selected": old_selected,
                    "target": old_target,
                    "correct": (
                        old_target in old["imposters"] if old_selected else None
                    ),
                    "top_probability": old["report"].get("top_p"),
                },
                "deduction": {
                    "selected": new_selected,
                    "target": new_target,
                    "correct": new.get("correct"),
                    "probability": new["probability"],
                    "required_probability": new["required_probability"],
                    "sources": new["sources"],
                    "reason": new["reason"],
                },
            }
        )
    return {
        "meetings": {
            "legacy": len(legacy),
            "deduction": len(deduction),
            "shared": len(shared),
            "legacy_only": len(legacy.keys() - deduction.keys()),
            "deduction_only": len(deduction.keys() - legacy.keys()),
        },
        "legacy": _legacy_summary(legacy_decisions),
        "deduction": _deduction_summary(deduction_decisions),
        "disagreements": disagreements,
    }


def _key(row: dict[str, Any]) -> tuple[str, int]:
    return row["episode_id"], int(row["meeting_id"])


def _legacy_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    selected = [row for row in rows if row["selected"]]
    correct = sum(row["pick"] in row["imposters"] for row in selected)
    return _summary(len(rows), len(selected), correct)


def _deduction_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    selected = [row for row in rows if row["action"] == "eject"]
    correct = sum(row["correct"] is True for row in selected)
    return _summary(len(rows), len(selected), correct)


def _summary(meetings: int, votes: int, correct: int) -> dict[str, Any]:
    return {
        "votes": votes,
        "correct": correct,
        "coverage": round(votes / max(meetings, 1), 4),
        "precision": round(correct / max(votes, 1), 4),
    }


if __name__ == "__main__":
    main()
