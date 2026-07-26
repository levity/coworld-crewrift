---
name: build-and-upload
description: "Use to build the crewborg image and upload it as a new policy version — the routine, inert, every-iteration action that gives you a runnable artifact to smoke-test and evaluate. Triggers: 'build crewborg', 'upload a new version', 'rebuild and re-upload', 'ship a version for testing', 'upload with the LLM on'. Uploading enters NO competition; submitting to a league is the separate coworld-policy-lifecycle (submit & monitor) skill."
---

# Build & Upload — a new crewborg version

The routine, every-iteration action: **build** the crewborg image and **upload** it as a **new
version**, so you have a runnable artifact to smoke-test (`coworld-local-run`) and measure
(`coworld-experience-requests`). **Uploading is inert** — it registers a version and enters no
competition, so do it freely. (Entering a version into a live league is the gated, rare
**`coworld-policy-lifecycle`** / submit & monitor skill.)

**Announce at start:** "Building crewborg `linux/amd64` and uploading it as a new (inert) version."

## Step 1 — Build `linux/amd64`

```bash
docker build --platform linux/amd64 -f crewborg/coworld/Dockerfile -t crewborg:dev players/crewborg
```

- **amd64 is mandatory** — the cluster + local runner hard-fail on arm64 (build `--platform
  linux/amd64` on Apple Silicon). A running **Docker daemon** is required.
- Equivalent: the `tools/` build script (pins the SDK + game ref centrally).

## Step 2 — Upload as a new version

```bash
uv run coworld upload-policy crewborg:dev --name crewborg \
  --run python --run -m --run crewborg.coworld.policy_player
# -> "Upload complete: crewborg:v<N>"   (a NEW version; INERT, not competing)
```

- **`--name crewborg`** (required) is the **stable policy name** the version history hangs off —
  re-uploading the same name **auto-increments `vN`**.
- **`--run` must launch crewborg's entrypoint** (`crewborg.coworld.policy_player`). Omit it and a
  reference/default player runs — **the quietest failure**: the version uploads fine but a *different*
  policy actually plays. (Needed because the image can carry multiple roles.)
- The client `docker save`s + pushes the image, so a **Docker daemon** is required.

### LLM (Bedrock) upload recipe — *only* if shipping the meeting LLM / commander

crewborg plays **fully deterministically by default**; its LLM layers are **opt-in**. To ship them:

```bash
uv run coworld upload-policy crewborg:dev --name crewborg \
  --run python --run -m --run crewborg.coworld.policy_player \
  --use-bedrock [--bedrock-model <model-id>] \
  --secret-env CREWBORG_LLM_MEETINGS=1 [--secret-env CREWBORG_LLM_COMMANDER=1]
```

- **`--use-bedrock`** sets `USE_BEDROCK=true`; in a hosted episode crewborg routes through the per-pod
  sidecar (it gates on the injected `AWS_ENDPOINT_URL_BEDROCK_RUNTIME`, not on `USE_BEDROCK`). See
  the [Bedrock section](../../docs/reference/coworld-platform.md#bedrock--in-pod-llm).
- crewborg's own toggles are **env vars**, injected with **`--secret-env`**: `CREWBORG_LLM_MEETINGS=1`
  (meeting chat/votes), `CREWBORG_LLM_COMMANDER=1` (gameplay commander) — both **off** by default.
  Full toggle list (model, tokens, temperature, timeout, trace) is the env-var table in
  [`crewborg/README.md`](../../crewborg/README.md).
- **After the eval, confirm the LLM actually fired** — check the telemetry artifact for
  `domain.meeting_llm_decision` (vs `_fallback`); a silent fall-back to deterministic play is the
  common trap. See the Bedrock debugging table in `coworld-platform.md`.

## Step 3 — Provenance (NOT optional, and not by hand)

**Upload with the wrapper. It records the row from the same arguments it uploads with, so
the log cannot disagree with reality:**

```bash
uv run python skills/build-and-upload/scripts/upload_and_log.py \
    --image crewborg:my-build --name crewborg-lw \
    --purpose kill-window-league --note "what this version is for, one line" \
    --secret-env CREWBORG_DEDUCTION_HISTORY=1 --secret-env CREWBORG_KILL_WINDOW=both
```

It refuses without `--purpose` and `--note`, adds `CREWBORG_METRICS=1` /
`CREWBORG_TRACE_GROUPS=all` (standing preference), puts the behaviour config in `--tag`s
*and* in [`version_log.md`](../../crewborg/version_log.md), and stamps the commit, branch
and image digest. `--dry-run` shows the command and the row without touching anything.

**Why this is mechanical rather than advised.** This step used to say "record `vN → its
change`" and "use `--tag` for private bookkeeping". On 2026-07-26 `crewborg-lw:v18` was
uploaded with **no tags and no log row**, was submitted, and became league champion — and
we then could not answer *what config our own champion runs*. `--secret-env` values are
not readable back from any API route (by design), and league episodes carry no policy
artifacts at all, so both the recorded and the observable paths were gone. Recovering it
took a fresh 6-episode hosted probe plus forensics on the decision weights. Advisory wording did
not survive contact; the wrapper is the fix.

**Then verify what the platform actually stored** — never trust the log alone (best
practice: verify a champion's config from a fetched trace, never from the version log):

```bash
uv run python skills/build-and-upload/scripts/versions.py --name crewborg-lw   # vN + UUID + created_at
```

**League play cannot explain a version — only an experience request can.** League/
tournament episodes return `results: false` with no logs and no `policy_artifacts`
(measured 2026-07-26 on two-minute-old episodes and again on fresh ones: not expiry, not
lag — that route does not carry them). If a version might ever need explaining, the
record you write at upload IS the record; the fallback is firing your own experience
request and reading its traces. (When you do fetch, avoid `fetch.sh` — its `--no-logs`
also suppresses policy artifacts.)

## Then what

1. **Gate-1 smoke** the new version — `coworld-local-run`.
2. **Measure it** vs the field — `coworld-experience-requests`.
3. **Only when demonstrably better + the human approves** — submit it (the gated
   `coworld-policy-lifecycle` / submit & monitor skill).

## Notes

- **`resolve-and-upload` is NOT this flow** — that's a Coworld/*game* upload wrapper, not a policy one.
- Auth: `softmax login`. Full flags + routes + the LLM env recipe: [`references/cli.md`](references/cli.md).
- The "upload freely, submit rarely" discipline is in [`../../docs/best_practices.md`](../../docs/best_practices.md).
