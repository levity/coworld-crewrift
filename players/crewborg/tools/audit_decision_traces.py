#!/usr/bin/env python3
"""Audit hosted ``domain.deduction_history_decision`` traces against ground truth.

Reads a directory of fetched episode dirs (each with ``results.json`` and
``artifacts/*.zip`` containing ``telemetry.jsonl``) and answers the questions the
threshold sweep in ``evaluate_deduction.py`` cannot:

* **which evidence class actually drives ejects** (structural pin vs accusation-backed
  joint solve), with precision per class;
* **which evidence channels ever fire**, and for the ones that do not, *the reason they
  were ignored* — the fastest way to find a channel whose preconditions are unsatisfiable
  in this game.

No warehouse, no replay expansion, no duckdb: the policy artifact already carries the
decision and its full evidence audit. Ground-truth roles come from ``results.json``'s
``imposter`` column joined to the fixed slot->colour map.

    python players/crewborg/tools/audit_decision_traces.py <episodes-dir>
    python players/crewborg/tools/audit_decision_traces.py <episodes-dir> --json
"""

from __future__ import annotations

import argparse
import collections
import json
import zipfile
from pathlib import Path
from typing import Any, Iterator

# Crewrift assigns colours to slots in this fixed order (sim.nim slot config).
SLOT_COLORS = (
    "red",
    "blue",
    "green",
    "pink",
    "orange",
    "yellow",
    "purple",
    "cyan",
)
DECISION_EVENT = "domain.deduction_history_decision"


def iter_decisions(root: Path) -> Iterator[tuple[dict[str, Any], set[str], str]]:
    """Yield ``(decision, imposter_colors, episode_name)`` for every decision trace."""

    for episode in sorted(p for p in root.iterdir() if p.is_dir()):
        results = episode / "results.json"
        if not results.is_file():
            continue
        try:
            payload = json.loads(results.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        flags = payload.get("imposter") or []
        truth = {
            SLOT_COLORS[index]
            for index, value in enumerate(flags)
            if value and index < len(SLOT_COLORS)
        }
        if not truth:
            continue
        for archive in sorted((episode / "artifacts").glob("*.zip")):
            try:
                text = zipfile.ZipFile(archive).read("telemetry.jsonl")
            except (OSError, KeyError, zipfile.BadZipFile):
                continue
            for line in text.decode("utf8", "ignore").splitlines():
                if DECISION_EVENT not in line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                data = record.get("data") or {}
                decision = data.get("decision")
                if not isinstance(decision, dict):
                    decision = data
                if isinstance(decision, dict) and "action" in decision:
                    yield decision, truth, episode.name


def evidence_class(decision: dict[str, Any]) -> str:
    if decision.get("structural"):
        return "structural"
    return "accusation-backed" if decision.get("sources") else "unsupported"


def audit(root: Path) -> dict[str, Any]:
    decisions = list(iter_decisions(root))
    ejects = [item for item in decisions if item[0].get("action") == "eject"]
    skips = [item for item in decisions if item[0].get("action") == "skip"]

    per_class_total: collections.Counter[str] = collections.Counter()
    per_class_hits: collections.Counter[str] = collections.Counter()
    for decision, truth, _ in ejects:
        name = evidence_class(decision)
        per_class_total[name] += 1
        if decision.get("target") in truth:
            per_class_hits[name] += 1

    active: collections.Counter[str] = collections.Counter()
    ignored: collections.Counter[str] = collections.Counter()
    for decision, _, _ in decisions:
        inference = decision.get("inference") or {}
        for item in inference.get("evidence") or []:
            if not isinstance(item, dict):
                continue
            channel = item.get("channel") or "?"
            if item.get("status") == "active":
                active[channel] += 1
            elif item.get("status") == "ignored":
                reason = (item.get("reason") or "").split(" when ")[0][:70]
                ignored[f"{channel}: {reason}"] += 1

    skip_reasons: collections.Counter[str] = collections.Counter()
    for decision, _, _ in skips:
        for part in (decision.get("reason") or "").split("; "):
            if part:
                skip_reasons[part] += 1

    return {
        "decisions": len(decisions),
        "ejects": len(ejects),
        "skips": len(skips),
        "coverage_pct": round(100.0 * len(ejects) / len(decisions), 1) if decisions else 0.0,
        "eject_classes": {
            name: {
                "n": per_class_total[name],
                "at_imposter": per_class_hits[name],
                "precision_pct": round(
                    100.0 * per_class_hits[name] / per_class_total[name], 1
                ),
                "share_pct": round(100.0 * per_class_total[name] / len(ejects), 1),
            }
            for name in sorted(per_class_total)
        },
        "active_evidence": dict(active.most_common()),
        "ignored_evidence": dict(ignored.most_common(20)),
        "skip_reasons": dict(skip_reasons.most_common()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episodes", type=Path, help="directory of fetched episode dirs")
    parser.add_argument("--json", action="store_true", help="emit raw JSON")
    args = parser.parse_args()

    report = audit(args.episodes)
    if args.json:
        print(json.dumps(report, indent=2))
        return

    print(
        f"decisions={report['decisions']}  ejects={report['ejects']}  "
        f"skips={report['skips']}  coverage={report['coverage_pct']}%\n"
    )
    print("EJECTS by evidence class")
    for name, row in report["eject_classes"].items():
        print(
            f"  {name:18s} n={row['n']:4d}  at-imposter={row['at_imposter']:4d}  "
            f"precision={row['precision_pct']:5.1f}%  share={row['share_pct']:5.1f}%"
        )
    print("\nACTIVE evidence by channel")
    for channel, count in report["active_evidence"].items():
        print(f"  {count:7d}  {channel}")
    print("\nIGNORED evidence (why a channel never fires)")
    for reason, count in report["ignored_evidence"].items():
        print(f"  {count:7d}  {reason}")
    print("\nSKIP reasons")
    for reason, count in report["skip_reasons"].items():
        print(f"  {count:7d}  {reason}")


if __name__ == "__main__":
    main()
