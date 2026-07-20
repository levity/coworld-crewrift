#!/usr/bin/env python3
"""One-shot: point at a set of Crewrift episodes -> a built event warehouse.

Wraps the three steps so you don't run them by hand:
  (optional) fetch episodes  ->  build report_request.json  ->  run `crewrift-event-warehouse build`

The vendored warehouse lives at ``players/crewborg/tools/event-warehouse/`` and is run via uv, so
no global install is needed. It also surfaces the **#1 failure** up front: replay/sim version skew,
which shows up as `trace_warning` episodes and sparse output (see the SKILL.md "version coupling").

Usage:
    # episodes already downloaded WITH replays (coworld-episode-artifacts, no --no-replay):
    build_warehouse.py --episodes /tmp/eps --out warehouse/ --expand-replay /tmp/expand-42fed21

    # or fetch first — any mix, all repeatable, so you can SPAN rounds / XP requests and cherry-pick:
    build_warehouse.py --xreq xreq_A --xreq xreq_B --out warehouse/ --expand-replay <bin>     # span 2 XPs
    build_warehouse.py --round round_1 --round round_2 --out warehouse/ --expand-replay <bin> # span 2 rounds
    build_warehouse.py --episode <uuid1> --episode ereq_xyz --xreq xreq_A --out wh/ --expand-replay <bin>
    build_warehouse.py --policy crewborg -n 200 --out warehouse/ --expand-replay <bin>

`--expand-replay` must be a version-matched `expand_replay` binary built from THIS repo's
`tools/expand_replay.nim` at the arena's deployed commit — else every replay hash-fails and you get
metadata-only rows. Omit it only if `crewrift-expand-replay` is already on PATH and correct.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import zlib
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[5]  # players/crewborg/skills/crewrift-event-warehouse/scripts -> repo root
WH_DIR = REPO / "players/crewborg/tools/event-warehouse/crewrift-event-warehouse"
FETCH = REPO / "players/crewborg/skills/coworld-episode-artifacts/scripts/fetch_artifacts.py"


def players_of(episode: dict) -> list[dict]:
    """[{slot, player_id, display_name}] — handles league (policy_results) + XP (participants)."""
    out: list[dict] = []
    for pr in episode.get("policy_results") or []:
        pol = pr.get("policy") or {}
        out.append({"slot": pr["position"], "player_id": pol.get("id"), "display_name": pol.get("name")})
    if not out:
        for pt in episode.get("participants") or []:
            out.append({"slot": pt["position"], "player_id": pt.get("policy_version_id"),
                        "display_name": pt.get("label") or pt.get("policy_name")})
    return out


def find_episode_dirs(root: Path) -> list[Path]:
    return [d for d in sorted(root.iterdir())
            if d.is_dir() and (d / "episode.json").exists() and (d / "results.json").exists()
            and (d / "replay.json.z").exists()]


def replay_encoding(path: Path) -> str:
    """Return the reporter encoding for a downloaded replay, based on its bytes.

    The Observatory replay route sometimes returns an already-decompressed
    ``CREWRIFT`` bitreplay while the artifact downloader retains the historical
    ``replay.json.z`` filename. The filename therefore cannot define the wire
    encoding.
    """
    header = path.read_bytes()[:8]
    if header == b"CREWRIFT":
        return "identity"
    if len(header) >= 2 and header[0] & 0x0F == 8 and (header[0] << 8 | header[1]) % 31 == 0:
        return "zlib"
    raise ValueError(
        f"{path}: replay is neither raw CREWRIFT data nor a recognizable zlib stream "
        f"(first bytes: {header.hex()})"
    )


def raw_replay_bytes(path: Path, encoding: str) -> bytes:
    payload = path.read_bytes()
    if encoding == "zlib":
        payload = zlib.decompress(payload)
    if not payload.startswith(b"CREWRIFT"):
        raise ValueError(f"{path}: decoded replay does not start with CREWRIFT")
    return payload


def preflight(dirs: list[Path], expand_replay: Path | None) -> dict[Path, str]:
    """Validate local artifacts and smoke-test the expander before a batch build."""
    encodings: dict[Path, str] = {}
    representatives: dict[str, tuple[Path, str]] = {}
    for ep in dirs:
        json.loads((ep / "episode.json").read_text())
        json.loads((ep / "results.json").read_text())
        replay = ep / "replay.json.z"
        encoding = replay_encoding(replay)
        raw_replay_bytes(replay, encoding)
        encodings[ep] = encoding

        meta = json.loads((ep / "episode.json").read_text())
        version = str(meta.get("coworld_version") or "unknown")
        representatives.setdefault(version, (replay, encoding))

    counts = Counter(encodings.values())
    versions = ", ".join(sorted(representatives))
    print(f"  preflight: replay encodings {dict(sorted(counts.items()))}; coworld versions: {versions}")

    if expand_replay is None:
        print("  preflight: expander smoke test skipped (using CREWRIFT_EXPAND_REPLAY/PATH)")
        return encodings
    if not expand_replay.is_file():
        raise ValueError(f"--expand-replay is not a file: {expand_replay}")

    for version, (replay, encoding) in sorted(representatives.items()):
        raw = raw_replay_bytes(replay, encoding)
        with tempfile.NamedTemporaryFile(suffix=".bitreplay") as tmp:
            tmp.write(raw)
            tmp.flush()
            proc = subprocess.run(
                [str(expand_replay), "--format", "jsonl", "--snapshot-every", "120", tmp.name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=120,
                check=False,
            )
        if proc.returncode:
            detail = proc.stderr.strip().splitlines()
            suffix = f": {detail[-1]}" if detail else ""
            raise RuntimeError(
                f"expand_replay preflight failed for coworld {version} "
                f"(exit {proc.returncode}){suffix}"
            )
        print(f"  preflight: expander completed a coworld {version} replay")
    return encodings


def build_request(dirs: list[Path], out_dir: Path, encodings: dict[Path, str]) -> Path:
    episodes, seen = [], set()
    for ep in dirs:
        meta = json.loads((ep / "episode.json").read_text())
        eid = meta.get("id") or ep.name
        if eid in seen:
            continue
        seen.add(eid)
        episodes.append({
            "episode_request_id": eid, "status": "success",
            "manifest": {"ereq_id": eid, "status": "success", "include": ["results", "replay"],
                         "files": {"results": "results.json", "replay": "replay.json.z"}},
            "artifacts": {
                "results": {"uri": (ep / "results.json").as_uri(), "media_type": "application/json"},
                "replay": {"uri": (ep / "replay.json.z").as_uri(),
                           "media_type": "application/octet-stream", "encoding": encodings[ep]},
            },
            "players": players_of(meta),
        })
    out_dir.mkdir(parents=True, exist_ok=True)
    req_path = out_dir / "report_request.json"
    req_path.write_text(json.dumps(
        {"type": "report_request", "request_id": "crewborg_warehouse",
         "report_uri": (out_dir / "REPORT_PLACEHOLDER.zip").as_uri(), "episodes": episodes}, indent=2))
    print(f"  report_request.json: {len(episodes)} episodes")
    return req_path


def _fetch_one(dest: Path, flags: list[str]) -> None:
    print(f"  fetching ({' '.join(flags)}) -> {dest}")
    # fetch_artifacts needs the Coworld SDK env — inherit the caller's cwd / uv project.
    subprocess.run(["uv", "run", "python", str(FETCH), "--out", str(dest), *flags], check=True)


def fetch_sources(args: argparse.Namespace, dest: Path) -> Path:
    """Fetch every requested source into one dir (idempotent + de-duped) — spans rounds / XP requests.

    fetch_artifacts' selectors are mutually exclusive per call, so we invoke it once per source and
    let it de-dupe into the shared dir. `--episode` ids may be bare league uuids OR `ereq_…` ids
    (routed to the right selector), so you can cherry-pick arbitrary episodes across many rounds/XPs.
    """
    dest.mkdir(parents=True, exist_ok=True)
    for x in args.xreq:
        _fetch_one(dest, ["--xreq", x])
    for r in args.round:
        _fetch_one(dest, ["--round", r])
    ereqs = [e for e in args.episode if e.startswith("ereq_")]
    uuids = [e for e in args.episode if not e.startswith("ereq_")]
    if ereqs:
        _fetch_one(dest, [f for e in ereqs for f in ("--ereq", e)])
    if uuids:
        _fetch_one(dest, [f for e in uuids for f in ("--episode", e)])
    if args.policy:
        _fetch_one(dest, ["--policy", args.policy, "-n", str(args.num)])
    return dest


def summarize(out: Path) -> int:
    manifest = json.loads((out / "manifest.json").read_text())
    warned = sum(1 for e in manifest.get("episodes", []) if e.get("trace_warning"))
    failed = [e for e in manifest.get("episodes", []) if e.get("status") == "failed"]
    print("\n=== warehouse manifest ===")
    for k in ("episodes_total", "episodes_ok", "episodes_cached", "episodes_skipped",
              "episodes_failed", "events_written", "distinct_policies"):
        print(f"  {k}: {manifest.get(k)}")
    print(f"  event_keys: {', '.join(manifest.get('event_keys', []))}")
    if failed:
        print(f"\n  ERROR: {len(failed)} episodes failed extraction. First failures:")
        for episode in failed[:5]:
            print(f"    {episode.get('episode_id')}: {episode.get('message')}")
    if warned:
        print(f"\n  ⚠️  {warned}/{manifest.get('episodes_total')} episodes have trace_warning "
              f"(replay/sim VERSION SKEW). Output is sparse for these — rebuild --expand-replay from "
              f"the arena's deployed crewrift commit. See the SKILL.md.")
    elif not failed:
        print("\n  ✓ no trace_warning episodes — the expand_replay binary matches the replays.")
    return 1 if failed or warned else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--episodes", type=Path, help="Dir of already-fetched episode dirs (with replay.json.z).")
    ap.add_argument("--episode", action="append", default=[], metavar="ID",
                    help="An episode id to fetch — a bare league uuid OR an ereq_… id. Repeatable; "
                         "cherry-pick / span arbitrary episodes across rounds and experience requests.")
    ap.add_argument("--xreq", action="append", default=[], metavar="xreq_…",
                    help="Fetch all of an experience request's episodes. Repeatable (span XP requests).")
    ap.add_argument("--round", action="append", default=[], metavar="round_…",
                    help="Fetch all of a league round's episodes. Repeatable (span rounds).")
    ap.add_argument("--policy", help="Fetch a policy's recent league episodes.")
    ap.add_argument("-n", "--num", type=int, default=100, help="Episode cap for --policy (default 100).")
    ap.add_argument("--out", type=Path, required=True, help="Warehouse output directory.")
    ap.add_argument("--expand-replay", type=Path, help="Version-matched expand_replay binary (CREWRIFT_EXPAND_REPLAY).")
    ap.add_argument("--workers", type=int, help="Parallel build workers (default: CPU count).")
    args = ap.parse_args()

    if args.episodes:
        ep_root = args.episodes
    elif args.episode or args.xreq or args.round or args.policy:
        ep_root = fetch_sources(args, args.out.parent / (args.out.name + "_episodes"))
    else:
        ap.error("give --episodes <dir>, or any mix of --episode/--xreq/--round/--policy to fetch (all repeatable).")

    dirs = find_episode_dirs(ep_root)
    if not dirs:
        raise SystemExit(f"No complete episode dirs (episode.json+results.json+replay.json.z) under {ep_root}. "
                         f"Did you fetch WITH replays (omit --no-replay)?")
    print(f"build_warehouse: {len(dirs)} episodes -> {args.out}")
    encodings = preflight(dirs, args.expand_replay)
    req = build_request(dirs, args.out.parent / (args.out.name + "_input"), encodings)

    env = dict(os.environ)
    if args.expand_replay:
        env["CREWRIFT_EXPAND_REPLAY"] = str(args.expand_replay)
    cmd = ["uv", "run", "crewrift-event-warehouse", "build", "--input", str(req), "--out", str(args.out)]
    if args.workers:
        cmd += ["--workers", str(args.workers)]
    print(f"  building (uv run in {WH_DIR.name}) …")
    subprocess.run(cmd, cwd=WH_DIR, env=env, check=True)
    return summarize(args.out)


if __name__ == "__main__":
    raise SystemExit(main())
