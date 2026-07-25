#!/usr/bin/env python3
"""Per-decision crew play-quality metrics from fetched hosted episodes.

Win rate is one bit per game: a 100-game arm buys 100 bits, which is why our A/Bs
keep landing "unresolved". This scores the *belief* instead of the outcome. Every
meeting yields one (observer, suspect) row per live player, so the same 100 games
buy thousands of labelled observations — and they measure whether a crewmate is
playing well individually, whether or not the team converts it into a win.

It reads whichever posterior an arm emits, so the two crew architectures are
directly comparable:

* fitted-posterior path -> ``domain.suspicion_snapshot`` ``ranking[].p``
* deduction/solver path -> ``domain.deduction_history_decision``
  ``decision.inference.marginals``

Ground truth comes from ``results.json["imposter"]`` via the fixed slot->colour map.

Usage:
    python tools/decision_quality.py <episodes_dir> [<episodes_dir> ...] [--json out.json]

Each <episodes_dir> is a directory of fetched episodes (``fetch_artifacts.py``
WITHOUT ``--no-logs``, so the policy artifacts are present).
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import random
import zipfile
from collections import defaultdict

# Crewrift Prime assigns colours by slot, stably across episodes.
COLORS = ("red", "blue", "green", "pink", "orange", "yellow", "purple", "cyan")

EPS = 1e-6


def _rows_from_artifact(raw: str, imposters: set[str]):
    """Yield (kind, decision_id, {color: p}, acted_target) for one seat's telemetry."""
    for n, line in enumerate(raw.splitlines()):
        if "suspicion_snapshot" not in line and "deduction_history_decision" not in line:
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        name = ev.get("name") or ev.get("event") or ""
        data = ev.get("data") or {}
        tick = ev.get("tick", n)
        if name.endswith("suspicion_snapshot"):
            posterior = {
                e["color"]: float(e["p"])
                for e in data.get("ranking", ())
                if e.get("color") and e.get("p") is not None
            }
            yield ("fitted", tick, posterior, data.get("would_vote"))
        elif name.endswith("deduction_history_decision"):
            dec = data.get("decision") or {}
            marg = (dec.get("inference") or {}).get("marginals") or {}
            posterior = {c: float(p) for c, p in marg.items()}
            target = dec.get("target") if dec.get("action") == "eject" else None
            yield ("deduction", tick, posterior, target)


def _auc(scored: list[tuple[float, int]]) -> float | None:
    """Rank-based AUC over (p, label) pairs; ties get half credit."""
    pos = [p for p, y in scored if y == 1]
    neg = [p for p, y in scored if y == 0]
    if not pos or not neg:
        return None
    wins = 0.0
    for a in pos:
        for b in neg:
            wins += 1.0 if a > b else 0.5 if a == b else 0.0
    return wins / (len(pos) * len(neg))


def collect(root: str):
    """Return per-decision records for one arm."""
    records = []
    for ep_dir in sorted(glob.glob(os.path.join(root, "*ereq*"))):
        results_path = os.path.join(ep_dir, "results.json")
        if not os.path.exists(results_path):
            continue
        with open(results_path) as fh:
            results = json.load(fh)
        imposters = {COLORS[i] for i, v in enumerate(results.get("imposter", ())) if v}
        if not imposters:
            continue
        episode = os.path.basename(ep_dir)
        for zpath in sorted(glob.glob(os.path.join(ep_dir, "artifacts", "*.zip"))):
            try:
                raw = zipfile.ZipFile(zpath).read("telemetry.jsonl").decode("utf-8", "ignore")
            except (KeyError, OSError, zipfile.BadZipFile):
                continue
            seat = os.path.basename(zpath).rsplit("_", 1)[1].split(".")[0]
            self_color = COLORS[int(seat)] if seat.isdigit() and int(seat) < len(COLORS) else None
            for kind, tick, posterior, target in _rows_from_artifact(raw, imposters):
                # The observer never scores itself; keep the row set comparable
                # across arms (the fitted path omits self, the solver may not).
                posterior = {c: p for c, p in posterior.items() if c != self_color}
                if not posterior:
                    continue
                records.append(
                    {
                        "episode": episode,
                        "seat": seat,
                        "tick": tick,
                        "kind": kind,
                        "posterior": posterior,
                        "target": target,
                        "imposters": imposters,
                    }
                )
    return records


def score(records: list[dict]) -> dict:
    """Discrimination, calibration and decision metrics over per-player rows."""
    rows: list[tuple[float, int]] = []
    per_episode: dict[str, list[tuple[float, int]]] = defaultdict(list)
    top1 = top1_n = 0
    acted = correct = 0
    kinds = defaultdict(int)
    for rec in records:
        kinds[rec["kind"]] += 1
        scored = [(p, 1 if c in rec["imposters"] else 0) for c, p in rec["posterior"].items()]
        rows.extend(scored)
        per_episode[rec["episode"]].extend(scored)
        if scored:
            best = max(rec["posterior"], key=rec["posterior"].get)
            top1_n += 1
            top1 += 1 if best in rec["imposters"] else 0
        if rec["target"]:
            acted += 1
            correct += 1 if rec["target"] in rec["imposters"] else 0

    brier = sum((p - y) ** 2 for p, y in rows) / len(rows) if rows else float("nan")
    logloss = (
        -sum(
            math.log(max(p, EPS)) if y else math.log(max(1 - p, EPS))
            for p, y in rows
        )
        / len(rows)
        if rows
        else float("nan")
    )

    # Cluster bootstrap by episode — seats inside one game share its impostors,
    # so treating rows as independent would understate the interval badly.
    episodes = list(per_episode)
    rng = random.Random(7)
    boots = []
    for _ in range(400):
        sample: list[tuple[float, int]] = []
        for _ in episodes:
            sample.extend(per_episode[rng.choice(episodes)])
        if sample:
            boots.append(sum((p - y) ** 2 for p, y in sample) / len(sample))
    boots.sort()
    lo = boots[int(0.025 * len(boots))] if boots else float("nan")
    hi = boots[int(0.975 * len(boots))] if boots else float("nan")

    buckets = defaultdict(lambda: [0, 0])
    for p, y in rows:
        edge = min(int(p * 10), 9)
        buckets[edge][0] += 1
        buckets[edge][1] += y

    return {
        "kinds": dict(kinds),
        "decisions": len(records),
        "player_rows": len(rows),
        "episodes": len(episodes),
        "base_rate": sum(y for _, y in rows) / len(rows) if rows else float("nan"),
        "brier": brier,
        "brier_ci": [lo, hi],
        "logloss": logloss,
        "auc": _auc(rows),
        "top1_accuracy": top1 / top1_n if top1_n else float("nan"),
        "top1_n": top1_n,
        "acted": acted,
        "act_rate": acted / len(records) if records else float("nan"),
        "act_precision": correct / acted if acted else float("nan"),
        "calibration": {
            f"{e/10:.1f}-{(e+1)/10:.1f}": {"n": n, "actual": (k / n if n else None)}
            for e, (n, k) in sorted(buckets.items())
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dirs", nargs="+", help="fetched-episode directories, one per arm")
    parser.add_argument("--json", help="write the full report here")
    args = parser.parse_args()

    report = {}
    for d in args.dirs:
        label = os.path.basename(d.rstrip("/"))
        result = score(collect(d))
        report[label] = result
        print(f"== {label}  {result['kinds']}")
        print(
            f"   decisions={result['decisions']}  player_rows={result['player_rows']}"
            f"  episodes={result['episodes']}  base_rate={result['base_rate']:.3f}"
        )
        print(
            f"   Brier={result['brier']:.4f} (95% CI {result['brier_ci'][0]:.4f}"
            f"-{result['brier_ci'][1]:.4f})   logloss={result['logloss']:.4f}"
        )
        auc = result["auc"]
        print(
            f"   AUC={auc:.4f}" % () if auc is None else f"   AUC={auc:.4f}"
            f"   top1={result['top1_accuracy']:.1%} (n={result['top1_n']})"
        )
        print(
            f"   acted={result['acted']} ({result['act_rate']:.1%} of decisions)"
            f"  act_precision={result['act_precision']:.1%}"
        )
        print("   calibration  bucket        n   actual")
        for bucket, cell in result["calibration"].items():
            actual = "-" if cell["actual"] is None else f"{cell['actual']:.3f}"
            print(f"                {bucket:>10} {cell['n']:6d}   {actual}")
        print()

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(report, fh, indent=1, default=str)
        print(f"wrote {args.json}")


if __name__ == "__main__":
    main()
