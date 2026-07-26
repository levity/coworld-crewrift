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
That mapping is a convention, not a guarantee — the engine allows a config to assign
colours per slot — so ``collect`` checks each episode's posteriors against it and
reports violations rather than silently mislabelling.

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

# Crewrift Prime assigns colours by slot, stably across every episode we have run.
COLORS = ("red", "blue", "green", "pink", "orange", "yellow", "purple", "cyan")

EPS = 1e-6
BOOTSTRAP_DRAWS = 400


def _rows_from_artifact(raw: str):
    """Yield (decision_tick, {color: p}, acted_target) for one seat's telemetry."""
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
            yield (tick, posterior, data.get("would_vote"))
        elif name.endswith("deduction_history_decision"):
            dec = data.get("decision") or {}
            marginals = (dec.get("inference") or {}).get("marginals") or {}
            posterior = {c: float(p) for c, p in marginals.items()}
            target = dec.get("target") if dec.get("action") == "eject" else None
            yield (tick, posterior, target)


def _brier(pairs) -> float:
    total = 0.0
    n = 0
    for p, y in pairs:
        total += (p - y) ** 2
        n += 1
    return total / n if n else float("nan")


def _auc(scored: list[tuple[float, int]]) -> float | None:
    """Mann-Whitney U via midranks: ties get half credit, in O(n log n)."""
    n_pos = sum(y for _, y in scored)
    n_neg = len(scored) - n_pos
    if not n_pos or not n_neg:
        return None
    ordered = sorted(scored, key=lambda pair: pair[0])
    positive_rank_sum = 0.0
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and ordered[j + 1][0] == ordered[i][0]:
            j += 1
        midrank = (i + j) / 2 + 1  # 1-based, averaged across the tie group
        positive_rank_sum += midrank * sum(y for _, y in ordered[i : j + 1])
        i = j + 1
    return (positive_rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def collect(root: str):
    """Return per-decision records for one arm, plus any colour-map violations."""
    records = []
    violations = []
    for ep_dir in sorted(glob.glob(os.path.join(root, "*"))):
        results_path = os.path.join(ep_dir, "results.json")
        if not os.path.exists(results_path):
            continue  # an episode is a directory with a results.json, per the viewer convention
        with open(results_path) as fh:
            results = json.load(fh)
        imposters = {COLORS[i] for i, v in enumerate(results.get("imposter", ())) if v}
        if not imposters:
            continue
        episode = os.path.basename(ep_dir)
        for zpath in sorted(glob.glob(os.path.join(ep_dir, "artifacts", "*.zip"))):
            with zipfile.ZipFile(zpath) as zf:
                try:
                    raw = zf.read("telemetry.jsonl").decode("utf-8", "ignore")
                except KeyError:
                    continue
            seat = os.path.basename(zpath).rsplit("_", 1)[1].split(".")[0]
            self_color = COLORS[int(seat)] if seat.isdigit() and int(seat) < len(COLORS) else None
            for tick, posterior, target in _rows_from_artifact(raw):
                # Both paths already omit the observer itself. If one ever appears,
                # the slot->colour convention has broken and every label in this
                # episode is suspect — surface it instead of scoring it.
                if self_color in posterior:
                    violations.append(f"{episode} seat {seat}: scored itself ({self_color})")
                    continue
                unknown = set(posterior) - set(COLORS)
                if unknown:
                    violations.append(f"{episode} seat {seat}: colours off the map {sorted(unknown)}")
                    continue
                if not posterior:
                    continue
                records.append(
                    {
                        "episode": episode,
                        "seat": seat,
                        "tick": tick,
                        "posterior": posterior,
                        "target": target,
                        "imposters": imposters,
                    }
                )
    return records, violations


def score(records: list[dict]) -> dict:
    """Discrimination, calibration and decision metrics over per-player rows."""
    if not records:
        return {"decisions": 0, "player_rows": 0, "episodes": 0}

    rows: list[tuple[float, int]] = []
    # The bootstrap resamples whole episodes, and Brier over a concatenation is just
    # sum(sse) / sum(n) — so per-episode aggregates are all it needs, not the rows.
    per_episode: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
    top1 = acted = correct = 0
    for rec in records:
        scored = [(p, 1 if c in rec["imposters"] else 0) for c, p in rec["posterior"].items()]
        rows.extend(scored)
        bucket = per_episode[rec["episode"]]
        for p, y in scored:
            bucket[0] += (p - y) ** 2
            bucket[1] += 1
        best = max(rec["posterior"], key=rec["posterior"].get)
        top1 += 1 if best in rec["imposters"] else 0
        if rec["target"]:
            acted += 1
            correct += 1 if rec["target"] in rec["imposters"] else 0

    logloss = -sum(
        math.log(max(p, EPS)) if y else math.log(max(1 - p, EPS)) for p, y in rows
    ) / len(rows)

    episodes = list(per_episode)
    rng = random.Random(7)
    boots = []
    for _ in range(BOOTSTRAP_DRAWS):
        sse = 0.0
        n = 0
        for _ in episodes:
            drawn = per_episode[rng.choice(episodes)]
            sse += drawn[0]
            n += drawn[1]
        if n:
            boots.append(sse / n)
    boots.sort()
    lo = boots[int(0.025 * len(boots))] if boots else float("nan")
    hi = boots[int(0.975 * len(boots))] if boots else float("nan")

    buckets = defaultdict(lambda: [0, 0])
    for p, y in rows:
        edge = min(int(p * 10), 9)
        buckets[edge][0] += 1
        buckets[edge][1] += y

    return {
        "decisions": len(records),
        "player_rows": len(rows),
        "episodes": len(episodes),
        "base_rate": sum(y for _, y in rows) / len(rows),
        "brier": _brier(rows),
        "brier_ci": [lo, hi],
        "logloss": logloss,
        "auc": _auc(rows),
        "top1_accuracy": top1 / len(records),
        "acted": acted,
        "act_rate": acted / len(records),
        "act_precision": correct / acted if acted else float("nan"),
        "calibration": {
            f"{e / 10:.1f}-{(e + 1) / 10:.1f}": {"n": n, "actual": (k / n if n else None)}
            for e, (n, k) in sorted(buckets.items())
        },
    }


def _report(label: str, result: dict, violations: list[str]) -> None:
    print(f"== {label}")
    if not result["decisions"]:
        print("   no decisions found (fetched with --no-logs, so no policy artifacts?)\n")
        return
    print(
        f"   decisions={result['decisions']}  player_rows={result['player_rows']}"
        f"  episodes={result['episodes']}  base_rate={result['base_rate']:.3f}"
    )
    print(
        f"   Brier={result['brier']:.4f} (95% CI {result['brier_ci'][0]:.4f}"
        f"-{result['brier_ci'][1]:.4f})   logloss={result['logloss']:.4f}"
    )
    auc = "-" if result["auc"] is None else f"{result['auc']:.4f}"
    print(f"   AUC={auc}   top1={result['top1_accuracy']:.1%} (n={result['decisions']})")
    print(
        f"   acted={result['acted']} ({result['act_rate']:.1%} of decisions)"
        f"  act_precision={result['act_precision']:.1%}"
    )
    print("   calibration  bucket        n   actual")
    for bucket, cell in result["calibration"].items():
        actual = "-" if cell["actual"] is None else f"{cell['actual']:.3f}"
        print(f"                {bucket:>10} {cell['n']:6d}   {actual}")
    if violations:
        print(f"   !! {len(violations)} slot->colour violations, rows dropped; first few:")
        for line in violations[:3]:
            print(f"      {line}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dirs", nargs="+", help="fetched-episode directories, one per arm")
    parser.add_argument("--json", help="write the full report here")
    args = parser.parse_args()

    report = {}
    for d in args.dirs:
        label = os.path.basename(d.rstrip("/"))
        records, violations = collect(d)
        result = score(records)
        if violations:
            result["colour_map_violations"] = violations
        report[label] = result
        _report(label, result, violations)

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(report, fh, indent=1)
        print(f"wrote {args.json}")


if __name__ == "__main__":
    main()
