#!/usr/bin/env python3
"""Offline counterfactual for the kill-window change, on recorded hosted histories.

Rebuilds each crew seat's DeductionHistory from its retained telemetry and re-runs
`infer()` under each preset, scoring pins against ground truth from results.json.

This is the free test the 2026-07-26 plan note asks for: it buys no hosted games and
measures the specific signals the change targets --
  * are pins SOUND (does a pinned actor turn out to be an impostor)?
  * does the truth survive in the hypothesis space?
  * what coverage is paid for it?
Living seats only where it matters is not applicable here: pins are derived from
observations made while alive, and we score the derivation, not the ballot.

LIMITATION, stated up front: the retained ledger itself is not emitted in telemetry,
so world frames are reconstructed from the per-tick `domain.decision_snapshot` stream
(which requires CREWBORG_TRACE_GROUPS=all at upload). That reproduces visible players,
bodies and self position -- everything `_witnessed_actions` reads -- but not vents, so
vent pins are absent from this replay. It scores the direct/kill channel only, which is
the channel this change touches.

Usage:
    python tools/kill_window_counterfactual.py <dir of fetched episode artifacts>
"""
from __future__ import annotations

import collections
import glob
import json
import os
import sys
import zipfile

from crewborg.deduction.config import KILL_WINDOW_PRESETS
from crewborg.deduction.inference import InferenceConfig, infer
from crewborg.deduction.model import (
    DeductionHistory,
    GameSpec,
    ObservedBody,
    ObservedPlayer,
    WorldObserved,
)
from crewborg.game_rules import effective_imposter_count

COLORS = ["red", "blue", "green", "pink", "orange", "yellow", "purple", "cyan"]

# Derived from the shipped table, never hand-copied: if the default margin ever moves,
# a copy here would silently keep measuring the old one -- the exact drift this tool
# exists to catch.
PRESETS = {
    (name if name != "off" else "shipped (exact radius)"): InferenceConfig(**overrides)
    for name, overrides in KILL_WINDOW_PRESETS.items()
}


def world_frames(zip_path):
    """Reconstruct WorldObserved frames from the seat's per-tick decision snapshots."""
    frames = []
    with zipfile.ZipFile(zip_path) as zf:
        for n in zf.namelist():
            if not n.endswith("telemetry.jsonl"):
                continue
            for raw in zf.open(n):
                if b'"domain.decision_snapshot"' not in raw:
                    continue
                d = json.loads(raw)
                tick = d.get("tick")
                data = d.get("data") or {}
                me = data.get("self")
                if tick is None or not me:          # null during meetings
                    continue
                players = tuple(
                    ObservedPlayer(color=p["color"], x=p["xy"][0], y=p["xy"][1])
                    for p in (data.get("visible_players") or [])
                    if p.get("life_status") != "dead"
                )
                bodies = tuple(
                    ObservedBody(color=b["color"], x=b["xy"][0], y=b["xy"][1])
                    for b in (data.get("visible_bodies") or [])
                )
                frames.append(WorldObserved(
                    event_id=f"world:{tick}", tick=tick,
                    self_xy=(me["x"], me["y"]), players=players, bodies=bodies))
    frames.sort(key=lambda f: f.tick)
    return frames


def main(root):
    stats = {k: collections.Counter() for k in PRESETS}
    seats = 0
    for res_path in sorted(glob.glob(os.path.join(root, "*", "results.json"))):
        ep = os.path.dirname(res_path)
        with open(res_path) as fh:
            res = json.load(fh)
        if sum(res["connect_timeout"]) or sum(res["disconnect_timeout"]):
            continue
        imps = {COLORS[i] for i, v in enumerate(res["imposter"]) if v}
        for s in (1, 2, 3, 4):                       # crewborg crew seats
            z = os.path.join(ep, "artifacts", f"policy_artifact_{s}.zip")
            if not os.path.exists(z):
                continue
            me = COLORS[s]
            frames = world_frames(z)
            if not frames:
                continue
            seats += 1
            hist = DeductionHistory(
                game=GameSpec(players=tuple(COLORS), self_color=me,
                              self_role="crewmate",
                              imposter_count=effective_imposter_count(len(COLORS))),
                events=tuple(frames))
            for name, cfg in PRESETS.items():
                r = infer(hist, config=cfg)
                c = stats[name]
                for p in r.pins:
                    c["pins"] += 1
                    c["pins_correct"] += (p in imps)
                # did the true assignment survive the structural table?
                if r.hypotheses:
                    c["seats_with_hyps"] += 1
                    c["truth_survives"] += any(set(h.imposters) == imps
                                               for h in r.hypotheses)
                c["constraints"] += sum(
                    1 for e in r.evidence
                    if e.channel == "direct" and e.stance == "at_least_one"
                    and e.status == "active")
    print(f"crew seats replayed: {seats}\n")
    hdr = f"{'preset':22} {'pins':>5} {'correct':>8} {'sound%':>7} {'alo':>5} {'truth kept':>11}"
    print(hdr); print("-" * len(hdr))
    for name, c in stats.items():
        pins, ok = c["pins"], c["pins_correct"]
        pct = f"{100*ok/pins:.0f}%" if pins else "n/a"
        tk = f"{c['truth_survives']}/{c['seats_with_hyps']}"
        print(f"{name:22} {pins:>5} {ok:>8} {pct:>7} {c['constraints']:>5} {tk:>11}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
