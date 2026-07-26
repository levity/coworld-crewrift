#!/usr/bin/env python3
"""Upload a policy version AND record its provenance, as one step.

WHY THIS EXISTS. On 2026-07-26 we could not answer "what config is our own league
champion running". `crewborg-lw:v18` was submitted, became champion, and:

  * `version_log.md` had no row for it (the log stopped at v14),
  * the upload carried no `--tag` (v16/v17 had `purpose`/`arm`; v18 had none),
  * `--secret-env` values are NOT readable back from any API route -- by design, and
  * league/tournament episodes carry NO policy artifacts (measured: `results: false`,
    zero artifacts, on episodes two minutes old), so there were no traces to fall back
    on either -- only an experience request you fire yourself produces them.

Recovering it took a fresh 6-episode hosted probe and forensics on decision weights
(vote weights were the shipped products scaled by exactly 1/6 and 1/8, which is the
signature of `CREWBORG_SPEAKER_TRUST=on`). That is an absurd cost for a fact we had at
upload time and simply did not write down.

The skill already *said* to record and tag. Advisory wording did not survive contact,
so this script makes it mechanical: it refuses to upload without a purpose and a note,
it puts the config in the tags where the API will hand it back, and it appends the
version-log row itself from the same arguments it uploaded with -- so the log cannot
disagree with the upload.

    uv run python upload_and_log.py --image crewborg:brainsep3 --name crewborg-lw \\
        --purpose kill-window-league --note "margin+at_least_one on, first league run" \\
        --secret-env CREWBORG_DEDUCTION_HISTORY=1 \\
        --secret-env CREWBORG_DECISION_GATE=loose \\
        --secret-env CREWBORG_SPEAKER_TRUST=on \\
        --secret-env CREWBORG_KILL_WINDOW=both

`--dry-run` prints the exact command and the row it would append, and touches nothing.
"""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

# Telemetry that every upload gets (user_preferences.md, James, 2026-07-01): massive
# logs beat re-uploading and re-running an experience request to get them.
ALWAYS_ENV = ("CREWBORG_METRICS=1", "CREWBORG_TRACE_GROUPS=all")
RUN_ARGV = ("python", "-m", "crewborg.coworld.policy_player")
VERSION_LOG = Path(__file__).resolve().parents[3] / "crewborg" / "version_log.md"


def git(*args: str) -> str:
    # Provenance is best-effort: a missing git or a detached worktree must not block an
    # upload, it just leaves "unknown" in the row where a commit would be.
    try:
        return subprocess.run(("git", *args), capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def image_digest(image: str) -> str:
    out = subprocess.run(("docker", "image", "inspect", image, "--format", "{{.Id}}"),
                         capture_output=True, text=True, check=False)
    return out.stdout.strip() or "unknown"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", required=True, help="local docker image tag to upload")
    ap.add_argument("--name", default="crewborg-lw", help="policy name (default crewborg-lw)")
    ap.add_argument("--purpose", required=True,
                    help="what this version is FOR, e.g. kill-window-league. Becomes a tag.")
    ap.add_argument("--arm", help="control|candidate, when this is one arm of an A/B. Becomes a tag.")
    ap.add_argument("--note", required=True, help="one line for the version log")
    ap.add_argument("--secret-env", action="append", default=[], metavar="K=V",
                    help="repeatable. The behaviour config. Recorded verbatim in the log.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    bad = [e for e in args.secret_env if "=" not in e]
    if bad:
        ap.error(f"--secret-env must be KEY=VALUE: {bad}")

    env = list(args.secret_env) + [e for e in ALWAYS_ENV
                                   if e.split("=")[0] not in
                                   {x.split("=")[0] for x in args.secret_env}]
    commit = git("rev-parse", "--short", "HEAD")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    digest = image_digest(args.image)

    # Config in the TAGS as well as the log: tags come back from the API, so a future
    # reader can recover the arm without a hosted probe even if the repo is not to hand.
    tags = [f"purpose={args.purpose}", f"commit={commit}", f"branch={branch}"]
    if args.arm:
        tags.append(f"arm={args.arm}")
    for e in args.secret_env:                      # behaviour flags only, not telemetry
        k, v = e.split("=", 1)
        tags.append(f"env.{k}={v}")

    cmd = ["coworld", "upload-policy", args.image, "--name", args.name]
    for part in RUN_ARGV:
        cmd += ["--run", part]
    for e in env:
        cmd += ["--secret-env", e]
    for t in tags:
        cmd += ["--tag", t]

    row = (
        f"| **`{args.name}:vNEXT`** | _(fill from upload output)_ | "
        f"{dt.datetime.now(dt.UTC).strftime('%Y-%m-%dT%H:%MZ')} | "
        f"branch `{branch}` @ `{commit}`; image `{args.image}` (`{digest[:19]}…`) | "
        f"**{', '.join(f'`{e}`' for e in args.secret_env) or 'no behaviour env'}** "
        f"(+ `{'`, `'.join(ALWAYS_ENV)}`) | {args.note} |"
    )

    print("COMMAND:\n  " + " ".join(cmd) + "\n")
    print("VERSION-LOG ROW:\n  " + row + "\n")
    if args.dry_run:
        print("--dry-run: nothing uploaded, nothing written.")
        return 0

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        print("\nUPLOAD FAILED — version log NOT touched.", file=sys.stderr)
        return proc.returncode

    version = ""
    for line in proc.stdout.splitlines():
        if "Upload complete:" in line:
            version = line.split("Upload complete:")[-1].strip()
    if version:
        row = row.replace(f"{args.name}:vNEXT", version)

    text = VERSION_LOG.read_text()
    marker = "| --- | --- | --- | --- | --- | --- |\n"
    if marker not in text:
        print("\nWARNING: could not find the version-log table header; append this row "
              "by hand:\n" + row, file=sys.stderr)
        return 0
    VERSION_LOG.write_text(text.replace(marker, marker + row + "\n", 1))
    print(f"\nRecorded {version or 'the new version'} in {VERSION_LOG}")
    print("Commit that row with the code it describes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
