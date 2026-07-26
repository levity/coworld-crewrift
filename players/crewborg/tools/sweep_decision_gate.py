#!/usr/bin/env python3
"""Sweep DecisionConfig's gate against recorded deduction decisions.

The shipped deduction crew path votes at 100 % precision but only ~14.5 % coverage,
with a posterior AUC around 0.81. That combination — a usable ranking that is rarely
acted on — is what you would expect from a gate set too conservatively. This asks,
without changing any policy code, whether some other setting of the gate trades a
little precision for materially more coverage.

It is read-only with respect to `crewborg/deduction/`. It imports `DecisionConfig`
so the defaults cannot drift from the policy, but it does not modify the deduction
path, and nothing here touches the legacy fitted-posterior code.

WHAT IT REPLAYS, AND WHAT IT APPROXIMATES

Each `domain.deduction_history_decision` record carries the posterior and the gate's
own arithmetic, so most of `decide_from_inference` can be replayed exactly:

* `inference.marginals` — full, one entry per non-self player. Self colour is
  recovered as the single colour absent from it.
* `structural`, `sources` — computed at runtime over the FULL hypothesis set and
  then serialised, so they are trustworthy.
* `required_probability` — tells us which parity branch fired at runtime (base,
  forced-vote, or dangerous-wrong-eject), which we re-apply with new constants.

Two honest approximations:

1. `inference.hypotheses` is truncated to 5 by `as_trace`, so parity risk cannot be
   recomputed from scratch. We infer the branch from `required_probability` instead
   of re-deriving it; sweeping `parity_risk_cutoff` itself is therefore out of scope.
2. `has_accusation` (a claim-channel accusation naming the target) is not serialised
   separately. We use `sources` as its proxy, which is what the eject path already
   requires alongside it. This can only make the support gate look *more* permissive,
   so reported coverage is an upper bound on that axis.

Liveness at the decision tick is reconstructed from `domain.player_died` across all
seats in the episode, so dead players are excluded from the ranking exactly as
`_live_targets` would.

    python tools/sweep_decision_gate.py <episodes_dir> [--json out.json]

<episodes_dir> is fetched episodes WITH policy artifacts (no `--no-logs`).
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crewborg.deduction.decision import DecisionConfig  # noqa: E402

SLOT_COLORS = ("red", "blue", "green", "pink", "orange", "yellow", "purple", "cyan")
DEFAULTS = DecisionConfig()
IMPOSTER_COUNT = 2


def load_decisions(root: Path) -> list[dict[str, Any]]:
    """One row per living-seat decision, with everything the gate needs."""

    rows: list[dict[str, Any]] = []
    for ep in sorted(p for p in root.iterdir() if p.is_dir()):
        results = ep / "results.json"
        if not results.is_file():
            continue
        try:
            payload = json.loads(results.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        truth = {
            SLOT_COLORS[i]
            for i, v in enumerate(payload.get("imposter") or [])
            if v and i < len(SLOT_COLORS)
        }
        if not truth:
            continue

        archives = sorted((ep / "artifacts").glob("*.zip"))
        per_seat: list[list[dict]] = []
        deaths: dict[str, int] = {}
        for archive in archives:
            try:
                raw = zipfile.ZipFile(archive).read("telemetry.jsonl")
            except (OSError, KeyError, zipfile.BadZipFile):
                continue
            lines = []
            for line in raw.decode("utf8", "ignore").splitlines():
                if not line.strip():
                    continue
                try:
                    lines.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            for record in lines:
                if record.get("event") == "domain.player_died":
                    data = record.get("data") or {}
                    color, tick = data.get("color"), data.get("death_tick")
                    if color and tick is not None:
                        deaths[color] = min(deaths.get(color, 1 << 30), tick)
            per_seat.append(lines)

        for lines in per_seat:
            for record in lines:
                if record.get("event") != "domain.deduction_history_decision":
                    continue
                decision = (record.get("data") or {}).get("decision") or {}
                inference = decision.get("inference") or {}
                marginals = inference.get("marginals")
                if not isinstance(marginals, dict) or not marginals:
                    continue
                missing = [c for c in SLOT_COLORS if c not in marginals]
                self_color = missing[0] if len(missing) == 1 else None
                tick = record.get("tick") or 0
                # A ghost's decision never reaches the ballot box; scoring it would
                # flatter the gate with near-omniscient information.
                if self_color is not None and deaths.get(self_color, 1 << 30) < tick:
                    continue
                live = {
                    color: float(p)
                    for color, p in marginals.items()
                    if deaths.get(color, 1 << 30) >= tick
                }
                if not live:
                    continue
                rows.append({
                    "live": live,
                    "truth": truth,
                    "structural": bool(decision.get("structural")),
                    "sources": len(decision.get("sources") or []),
                    "required_runtime": float(decision.get("required_probability") or 0.0),
                    "action": decision.get("action"),
                    "target": decision.get("target"),
                })
    return rows


def _required(row: dict[str, Any], cfg: DecisionConfig) -> float:
    """Re-apply whichever parity branch fired at runtime, with new constants."""
    runtime = row["required_runtime"]
    if abs(runtime - DEFAULTS.forced_vote_probability) < 1e-9:
        return cfg.forced_vote_probability
    if abs(runtime - DEFAULTS.dangerous_wrong_eject_probability) < 1e-9:
        return cfg.dangerous_wrong_eject_probability
    return cfg.base_probability


def evaluate(rows: list[dict[str, Any]], cfg: DecisionConfig) -> dict[str, Any]:
    ejects = hits = 0
    for row in rows:
        ranked = sorted(row["live"].items(), key=lambda kv: (-kv[1], kv[0]))
        target, probability = ranked[0]
        outside = ranked[IMPOSTER_COUNT][1] if len(ranked) > IMPOSTER_COUNT else 0.0
        margin = probability - outside
        support = (row["structural"] or not cfg.require_support
               or row["sources"] >= cfg.min_independent_sources)
        if (
            support
            and probability >= _required(row, cfg)
            and margin >= cfg.base_margin
        ):
            ejects += 1
            hits += target in row["truth"]
    return {
        "decisions": len(rows),
        "ejects": ejects,
        "coverage_pct": round(100.0 * ejects / len(rows), 1) if rows else 0.0,
        "precision_pct": round(100.0 * hits / ejects, 1) if ejects else None,
        "correct": hits,
        "wrong": ejects - hits,
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("episodes", type=Path)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    rows = load_decisions(args.episodes)
    if not rows:
        raise SystemExit(f"no living-seat decisions found under {args.episodes}")

    base = evaluate(rows, DEFAULTS)
    print(f"living-seat decisions: {base['decisions']}")
    print(
        f"shipped gate (p>={DEFAULTS.base_probability}, margin>={DEFAULTS.base_margin}): "
        f"coverage {base['coverage_pct']}%  precision {base['precision_pct']}%  "
        f"({base['correct']} right / {base['wrong']} wrong)\n"
    )

    grid: list[dict[str, Any]] = []
    # `min_sources` is swept too: with the shipped value the support gate
    # (structural OR enough independent sources) turns out to bind before the
    # probability/margin thresholds ever do, so sweeping p alone says nothing.
    # min_sources=0 removes the support requirement entirely and shows what the
    # posterior alone can buy.
    print(f"{'minsrc':>7s} {'p_base':>7s} {'margin':>7s} {'cover%':>7s} {'prec%':>7s} {'right':>6s} {'wrong':>6s}")
    for s in (2, 1, 0):
        for p in (0.65, 0.55, 0.50, 0.45, 0.40, 0.35):
            for m in (0.10, 0.02, 0.0):
                cfg = DecisionConfig(
                    base_probability=p, base_margin=m, min_independent_sources=s
                )
                r = evaluate(rows, cfg)
                r["base_probability"], r["base_margin"] = p, m
                r["min_independent_sources"] = s
                grid.append(r)
                shipped = (
                    p == DEFAULTS.base_probability
                    and m == DEFAULTS.base_margin
                    and s == DEFAULTS.min_independent_sources
                )
                prec = "  --" if r["precision_pct"] is None else f"{r['precision_pct']:6.1f}"
                print(f"{s:7d} {p:7.2f} {m:7.2f} {r['coverage_pct']:7.1f} {prec} "
                      f"{r['correct']:6d} {r['wrong']:6d}"
                      + ("  <- shipped" if shipped else ""))

    if args.json:
        args.json.write_text(json.dumps({"shipped": base, "grid": grid}, indent=2))
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
