#!/usr/bin/env python3
"""Replay recorded imposter strike decisions under both ``CREWBORG_KILL_ANCHOR`` arms.

**The defect.** ``belief.self_world`` is camera-derived
(``perception/resolve.py``: ``camera_x + SELF_OFFSET_X``); every *other* player's
``world_x/world_y`` comes from the sprite decoder. Hosted decoding puts our own
player record a stable ``(SELF_RECORD_DX, SELF_RECORD_DY) = (-2, -6)`` from the
camera point — ``types.py`` already relies on that to work out which sprite is us.
The kill-range test in ``action.py:_resolve_kill`` and ``modes/hunt.py`` compares
``self_world`` against a victim's sprite position, i.e. **two different anchors**,
biasing every range test by 6.3px.

That matters because ``_resolve_kill`` emits *only* an A-press edge when it believes
it is in range — no movement bits. Believing we are in range when we are not means
standing still and pressing A forever while the victim is out of reach.

**What this measures**, per kill-intent tick in a batch of episode artifacts:
the distance to the committed victim under each anchor, whether the strike landed,
and how much strike time each anchor would have spent out of the sim's KillRange
(``sim.nim`` KillRange = 20 ⇒ dist² ≤ 400).

Ground truth is the sim's own verdict: a strike that did not land within 2 ticks was
out of range. The arm that agrees with that verdict is the correct anchor.

Usage:
    python tools/kill_anchor_counterfactual.py <episodes_dir>

``<episodes_dir>`` holds one directory per episode with
``artifacts/policy_artifact_0.zip`` (as written by
``skills/coworld-episode-artifacts/scripts/fetch_artifacts.py``). Plain ``python`` —
no warehouse, expander or duckdb.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from math import sqrt
from pathlib import Path

# Mirrors crewborg.types; duplicated so the tool runs without importing the player.
SELF_RECORD_DX = -2
SELF_RECORD_DY = -6
KILL_RANGE = 20.0

# A strike is credited to a landing seen on the same tick or the next two.
LAND_WINDOW = (0, 1, 2)


def _strike_frames(zip_path: Path):
    """Yield (tick, self_xy, own_sprite_xy, victim_xy) for each kill-intent tick.

    ``viewer_frame`` is used rather than ``decision_snapshot`` because it carries the
    per-player ``teammate`` flag and the full roster, so our own sprite can be found
    without assuming a seat→colour convention.
    """
    landed: set[int] = set()
    frames: list[tuple[int, tuple[int, int], tuple[int, int], tuple[int, int]]] = []
    with zipfile.ZipFile(zip_path) as z:
        if "telemetry.jsonl" not in z.namelist():
            return [], landed
        with z.open("telemetry.jsonl") as fh:
            for line in fh:
                line = line.strip()
                if not line.startswith(b"{"):
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                event, tick = rec.get("event"), rec.get("tick")
                if event == "domain.kill_landed":
                    landed.add(tick)
                    continue
                if event != "domain.viewer_frame":
                    continue
                data = rec["data"]
                self_pt = data.get("self") or {}
                if self_pt.get("x") is None:
                    continue
                intent = data.get("intent") or {}
                if intent.get("kind") != "kill":
                    continue
                target_color = intent.get("target_color")
                players = {p["color"]: p for p in data.get("players") or []}
                target = players.get(target_color)
                if target is None or target.get("x") is None:
                    continue
                sx, sy = self_pt["x"], self_pt["y"]
                own = next(
                    (
                        p
                        for p in players.values()
                        if p.get("teammate")
                        and p.get("x") == sx + SELF_RECORD_DX
                        and p.get("y") == sy + SELF_RECORD_DY
                    ),
                    None,
                )
                if own is None:
                    continue
                frames.append((tick, (sx, sy), (own["x"], own["y"]), (target["x"], target["y"])))
    return frames, landed


def _dist(a, b) -> float:
    return sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def _pct(num: int, den: int) -> str:
    return f"{100.0 * num / den:.1f}%" if den else "n/a"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("episodes", type=Path, help="directory of fetched episode dirs")
    args = ap.parse_args()

    n_ep = 0
    landed_off: list[float] = []
    landed_sprite: list[float] = []
    wasted_off: list[float] = []
    wasted_sprite: list[float] = []

    for ep in sorted(args.episodes.iterdir()):
        zip_path = ep / "artifacts" / "policy_artifact_0.zip"
        if not zip_path.exists():
            continue
        frames, landed = _strike_frames(zip_path)
        if not frames:
            continue
        n_ep += 1
        for tick, self_xy, own_xy, victim_xy in frames:
            hit = any(tick + k in landed for k in LAND_WINDOW)
            (landed_off if hit else wasted_off).append(_dist(self_xy, victim_xy))
            (landed_sprite if hit else wasted_sprite).append(_dist(own_xy, victim_xy))

    n_land, n_waste = len(landed_off), len(wasted_off)
    print(f"episodes with imposter strike frames : {n_ep}")
    print(f"kill-intent ticks                    : {n_land + n_waste}")
    print(f"  landed                             : {n_land}")
    print(f"  did not land (wasted)              : {n_waste}")
    print()
    print("Does the anchor agree with the sim about being in range?")
    print(f"  {'anchor':<10}{'wasted ticks judged OUT of range':>36}{'landed judged IN range':>26}")
    for name, waste, land in (
        ("off", wasted_off, landed_off),
        ("sprite", wasted_sprite, landed_sprite),
    ):
        out_of_range = sum(1 for d in waste if d > KILL_RANGE)
        in_range = sum(1 for d in land if d <= KILL_RANGE)
        print(f"  {name:<10}{f'{out_of_range}/{len(waste)} ({_pct(out_of_range, len(waste))})':>36}"
              f"{f'{in_range}/{len(land)} ({_pct(in_range, len(land))})':>26}")
    print()
    print("  Higher is better in BOTH columns. The left column is the win: strike ticks the")
    print("  anchor correctly refuses, which under `sprite` become navigation (closing) instead")
    print("  of standing still pressing A. The right column is the guard: landed kills the")
    print("  anchor would still have allowed at that instant.")
    print()
    print("  Note the `off` left-column figure is tautological — `off` IS the shipped gate, so")
    print("  every recorded strike tick was in range by its own measure. It is shown to make")
    print("  that explicit, not as evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
