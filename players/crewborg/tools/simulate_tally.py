#!/usr/bin/env python3
"""Would a looser meeting gate actually EJECT anyone, or just cast more votes?

Coverage is measured in *decisions*. Crewrift ejects on `votes(X) > skips + timeouts`,
so more targeted ballots need not produce more ejections — Phase 0 already showed a
large win-rate move with ejection-driven wins completely unchanged (3 vs 3). This
re-runs each meeting's tally with the subject seats' ballots replaced by what a given
`DecisionConfig` would have cast, and counts the ejections that result.

    uv run python tools/simulate_tally.py --warehouse WH --telemetry EPISODES

FIRST-ORDER ONLY — state this wherever the number is quoted. The simulation holds the
impostors' ballots, every death, and the whole board fixed at what actually happened.
Real play is interactive: ejecting someone at meeting 2 changes who is alive at
meeting 3, what the impostors do, and which bodies appear. So this estimates the
*immediate* tally effect of the gate, not the downstream game. It is an argument for
or against spending hosted games, not a substitute for them.

Ballots are matched to meetings by tick: each `vote_cast` and each recorded decision
is assigned to the most recent `vote_called_button` / `vote_called_body`.
"""

from __future__ import annotations

import argparse
import bisect
import collections
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb  # noqa: E402

from crewborg.deduction.decision import DecisionConfig  # noqa: E402

SLOT_COLORS = ("red", "blue", "green", "pink", "orange", "yellow", "purple", "cyan")
IMPOSTER_COUNT = 2
DEFAULTS = DecisionConfig()


def _required(runtime: float, cfg: DecisionConfig) -> float:
    if abs(runtime - DEFAULTS.forced_vote_probability) < 1e-9:
        return cfg.forced_vote_probability
    if abs(runtime - DEFAULTS.dangerous_wrong_eject_probability) < 1e-9:
        return cfg.dangerous_wrong_eject_probability
    return cfg.base_probability


def decide(row: dict[str, Any], cfg: DecisionConfig) -> str | None:
    """Target this seat would vote under `cfg`, or None for skip."""
    ranked = sorted(row["live"].items(), key=lambda kv: (-kv[1], kv[0]))
    if not ranked:
        return None
    target, probability = ranked[0]
    outside = ranked[IMPOSTER_COUNT][1] if len(ranked) > IMPOSTER_COUNT else 0.0
    support = (row["structural"] or not cfg.require_support
               or row["sources"] >= cfg.min_independent_sources)
    if (
        support
        and probability >= _required(row["required_runtime"], cfg)
        and (probability - outside) >= cfg.base_margin
    ):
        return target
    return None


def load_telemetry(root: Path) -> dict[tuple[str, int], list[dict[str, Any]]]:
    """(episode_id, seat) -> decisions, each tagged with its tick."""
    out: dict[tuple[str, int], list[dict[str, Any]]] = collections.defaultdict(list)
    for ep in sorted(p for p in root.iterdir() if p.is_dir()):
        meta, results = ep / "episode.json", ep / "results.json"
        if not (meta.is_file() and results.is_file()):
            continue
        eid = json.loads(meta.read_text()).get("id")
        payload = json.loads(results.read_text())
        truth = {
            SLOT_COLORS[i] for i, v in enumerate(payload.get("imposter") or []) if v
        }
        deaths: dict[str, int] = {}
        seats: list[list[dict]] = []
        for archive in sorted((ep / "artifacts").glob("*.zip")):
            try:
                raw = zipfile.ZipFile(archive).read("telemetry.jsonl")
            except (OSError, KeyError, zipfile.BadZipFile):
                continue
            lines = []
            for line in raw.decode("utf8", "ignore").splitlines():
                if line.strip():
                    try:
                        lines.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            for r in lines:
                if r.get("event") == "domain.player_died":
                    d = r.get("data") or {}
                    if d.get("color") and d.get("death_tick") is not None:
                        deaths[d["color"]] = min(
                            deaths.get(d["color"], 1 << 30), d["death_tick"]
                        )
            seats.append(lines)
        for lines in seats:
            for r in lines:
                if r.get("event") != "domain.deduction_history_decision":
                    continue
                dec = (r.get("data") or {}).get("decision") or {}
                inf = dec.get("inference") or {}
                marg = inf.get("marginals")
                if not isinstance(marg, dict) or not marg:
                    continue
                missing = [c for c in SLOT_COLORS if c not in marg]
                if len(missing) != 1:
                    continue
                self_color = missing[0]
                tick = r.get("tick") or 0
                if deaths.get(self_color, 1 << 30) < tick:
                    continue  # ghost: never reaches the ballot box
                out[(eid, SLOT_COLORS.index(self_color))].append({
                    "tick": tick,
                    "truth": truth,
                    "live": {
                        c: float(p) for c, p in marg.items()
                        if deaths.get(c, 1 << 30) >= tick
                    },
                    "structural": bool(dec.get("structural")),
                    "sources": len(dec.get("sources") or []),
                    "required_runtime": float(dec.get("required_probability") or 0.0),
                })
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--warehouse", required=True)
    ap.add_argument("--telemetry", type=Path, required=True)
    args = ap.parse_args()

    con = duckdb.connect()
    con.execute("SET enable_progress_bar=false")
    con.execute("SET memory_limit='2GB'")
    con.execute(
        "CREATE VIEW events AS SELECT * FROM "
        f"read_parquet('{args.warehouse}/events/**/*.parquet', hive_partitioning=true)"
    )
    skew = {r[0] for r in con.execute(
        "SELECT DISTINCT episode_id FROM events WHERE key='trace_warning'").fetchall()}
    imposters = collections.defaultdict(set)
    for eid, slot in con.execute(
            "SELECT DISTINCT episode_id, slot FROM events WHERE role='imposter'").fetchall():
        imposters[eid].add(slot)
    starts = collections.defaultdict(list)
    for eid, ts in con.execute(
            "SELECT episode_id, ts FROM events WHERE key IN "
            "('vote_called_button','vote_called_body') ORDER BY 1,2").fetchall():
        starts[eid].append(ts)

    # Real ballots, grouped into meetings.
    ballots: dict[tuple[str, int], dict[int, str | None]] = collections.defaultdict(dict)
    for eid, ts, slot, val in con.execute(
            "SELECT episode_id, ts, slot, value FROM events WHERE key='vote_cast'").fetchall():
        if eid in skew:
            continue
        st = starts.get(eid) or [0]
        mi = max(bisect.bisect_right(st, ts) - 1, 0)
        d = json.loads(val)
        tgt = d.get("target_slot")
        ballots[(eid, mi)][slot] = None if tgt is None else SLOT_COLORS[int(tgt)]

    telemetry = load_telemetry(args.telemetry)

    def tally(eid: str, mi: int, cfg: DecisionConfig | None) -> tuple[str, str | None]:
        """Return (outcome, ejected_color) for one meeting under `cfg` (None = actual)."""
        cast = dict(ballots[(eid, mi)])
        if cfg is not None:
            st = starts.get(eid) or [0]
            for (e2, seat), rows in telemetry.items():
                if e2 != eid or seat not in cast:
                    continue
                for row in rows:
                    if max(bisect.bisect_right(st, row["tick"]) - 1, 0) == mi:
                        cast[seat] = decide(row, cfg)
                        break
        counts = collections.Counter(v for v in cast.values() if v is not None)
        skips = sum(1 for v in cast.values() if v is None)
        if not counts:
            return "no ejection", None
        top, n = counts.most_common(1)[0]
        if sum(1 for _t, c in counts.items() if c == n) > 1 or n <= skips:
            return "no ejection", None
        imp = {SLOT_COLORS[s] for s in imposters.get(eid, ())}
        return ("EJECT imposter" if top in imp else "EJECT CREW"), top

    configs = {
        "actual (recorded)": None,
        "shipped gate": DEFAULTS,
        "margin->eps + no support": DecisionConfig(
            base_probability=0.65, base_margin=0.001, min_independent_sources=0),
        "  ...and p->0.40": DecisionConfig(
            base_probability=0.40, base_margin=0.001, min_independent_sources=0),
    }
    meetings = sorted(ballots)
    print(f"meetings simulated: {len(meetings)}\n")
    print(f"{'configuration':28s} {'eject imposter':>15s} {'EJECT CREW':>12s} {'no ejection':>12s}")
    for name, cfg in configs.items():
        c = collections.Counter(tally(e, m, cfg)[0] for e, m in meetings)
        print(f"{name:28s} {c['EJECT imposter']:15d} {c['EJECT CREW']:12d} {c['no ejection']:12d}")
    print("\nFIRST-ORDER: impostor ballots, deaths and the rest of the board are held at")
    print("what actually happened. Real play is interactive; treat as an estimate of the")
    print("immediate tally effect, not a prediction of game outcomes.")


if __name__ == "__main__":
    main()
