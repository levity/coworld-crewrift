# crewborg crew-improvement — handoff (2026-07-26)

Worktree: `coworld-crewrift/.claude/worktrees/crewborg-deduction-history`, branch
`crewborg-deduction-history` (55 commits ahead of `origin/master`, unpushed).
Analysis tooling is a SEPARATE standalone repo:
`/home/exedev/projects/softmax/crewrift-analysis` — read its README first.

## Mission

Improve crewborg's **crewmate** results on **Crewrift Prime** (`crewrift_prime` 0.4.69,
coworld `cow_0ba5e866`). Loop: build → local smoke → hosted A/B → analyze → report.
Uploading a policy version is inert and ungated; **league submission is the human's
call**. Everything in the `crewborg-lw` line is currently inert and unsubmitted.

## The one thing to know

crewborg has two crewmate brains, and **the good one is now the direction**:

| | fitted posterior | deduction / solver |
|---|---|---|
| code | `strategy/suspicion.py` | `deduction/` |
| trained by | `suspicion_lab/` → `data/suspicion_weights.json` | nothing yet — 22 hand-set constants in `InferenceConfig` |
| gate | default | `CREWBORG_DEDUCTION_HISTORY=1` (crew-only) |
| **AUC** | **0.355 — worse than random** | **0.83** |
| votes at | ~13 ticks into Voting | ~1153 (deadline backstop) |

They do not compose for crew: under the flag a crewmate never has `belief.suspicion`
written at all, and the ballot routes through `deduction/decision.py`. The fitted posterior is **still live for the impostor
role** (deflection targeting via `top_suspect`), so do not delete it.

**Hosted A/B (homogeneous roster, 6 subject crew + 2 aaln impostors, 100/arm):** team
win **28% → 49%**, Fisher `p=0.0035`, with mean tasks 6.75 → 7.38 and all-8 41.5% →
64.3%. Confirmed on a mixed 4-2-2 roster: win 16% → 26% (`p=0.118`, unresolved at
n=100 as pre-registered), but decision quality **identical** (AUC 0.832 → 0.834) — so
the homogeneous roster did not flatter it.

**The mechanism was not the predicted one.** Vote precision did improve (84.5% →
100%), but the candidate ejects *fewer* impostors in absolute terms. The win comes from
task throughput: the fitted path pressed the emergency button **80 times in 40 games**
(Accuse mode firing on a worse-than-random posterior), abandoning tasks each time. The
deduction path clears `believed_imposters`, so Accuse can never fire — 0 button calls.
Kills are unchanged, so this is not a survival effect.

## Immediate next action

**Decompose that win.** The +21pp bundles two changes: near-perfect ballots, and Accuse
being silently disabled. The mechanism data says the second is doing most of the work,
and it has a one-flag test: run the **fitted path with Accuse disabled** (raise
`ACCUSE_THRESHOLD` above 1.0, or gate `active_tail_suspect`). If most of the gain
survives on the old architecture, a one-line change captures the bulk of it and the
architecture has to justify itself on precision alone. **Not yet run.**

Then `players/crewborg/docs/2026-07-25-crew-plan-deduction-first.md` is the standing
plan: fit the solver's 22 hand-set likelihood constants from the labelled corpus (free
— the data is already on disk), using `suspicion_lab` as the fitting/eval harness
rather than as the model.

## State of the tree

- **Shipped, default-on:** the edge-park freeze fix (`action.py`). A ~4px
  self-localization error parked the agent 1px outside the task rect, where it mashed A
  forever. Validated hosted: 0/200 pathological stalls.
- **Promotion candidate:** `crewborg-lw:v14` (`6a0e2ee5`), image `crewborg:solver-ab`,
  `CREWBORG_DEDUCTION_HISTORY=1` and nothing else. Its control `v13` (`f2634244`, no
  flags) reproduces the old champion exactly.
- **Removed 2026-07-26:** the legacy crew-side solver overlay —
  `strategy/meeting/solver.py`, `strategy/alibi.py`, `vote_policy.py`, the
  `MeetingRecord` / `meeting_history` / `social_claims` ledger, `modes/_deprecated/`,
  and their tests. ~4,400 lines, all superseded by `deduction/`.
- **Claim parsing:** `crewborg/strategy/claims.py` is the single spaCy claim parser, used
  by BOTH roles — which is why it is not under `deduction/` (crew-only).
  `strategy/social_evidence.py` holds only the fitted model's public counters. The claim
  types live in `strategy/claims.py` beside their producer.
- **Retained rejected experiments (~700 lines, all default-off):** `POST_TASK_ESCORT`,
  `POST_TASK_LOITER`, `GROUP_TASKING`, `WITNESS_TASKING`, `SELF_PRESERVATION`, `STICK`.
  Kept **deliberately** — see the retention note above `GROUP_TASK_RADIUS_SQ` in
  `modes/normal.py` and the entry in `docs/TODO.md`. Their nulls were all read off win
  rate, which is too coarse to see the claims they actually make.

## Hard-won lessons — do not re-derive

1. **Win rate is a poor instrument.** One bit per game; at n=100 it cannot resolve
   anything below roughly +15pp, so several "neutral" verdicts are probably just
   underpowered. Prefer `tools/decision_quality.py`: it scores the *belief* against
   ground truth and turns 100 games into thousands of labelled rows (Brier, log loss,
   AUC, calibration, cluster-bootstrapped by episode). Both crew paths already emit
   per-player posteriors under default tracing — no special upload env needed.
2. **Survival-via-movement is a dead end (6 failures).** Reactive repulsion,
   isolation-pursuit, witness-seeking, safe-distance, post-task escort,
   witness-tasking. 78% of crew die truly isolated, 85% pre-task, in peripheral task
   rooms. Clustering did not help — even fully clustered, murder went *up*. Crew and
   impostors share one `maxSpeed`, so no equal-speed flight can open a gap.
3. **Eval-design rule.** The homogeneous roster (6 subject + 2 aaln impostors) is the
   sensitive detector for voting/team-outcome changes; the mixed 4-2-2 (4 subject + 2
   aaln crew + 2 aaln impostors) is the realistic confirmer. Nothing is promoted on a
   homogeneous result alone. 4-2-2 carries ~2/3 of the treatment, so expect deltas
   about a third smaller.
4. **Verify a champion's config from a fetched trace, never from the version log.**
   This is exactly how `crewborg-lw:v4` silently dropped every behaviour flag: the
   escort A/B's "control = no env" arm quietly became the baseline for v6–v12, and the
   log row was written by copying the previous row's prose. Every experiment after that
   measured the fitted path while the log claimed otherwise.
5. **A skipped test is a defect.** `crewborg/tests/conftest.py` fails the run on an
   unexpected skip. If behaviour is retired, delete its tests — git history keeps the
   contract.

## How to work here

```sh
cd players/crewborg
uv run --group dev pytest                  # 558 passed, 0 skipped — keep it that way
uv run --group dev ruff check <files>

source /home/exedev/projects/softmax/crewrift-analysis/env.sh   # xp_py / wh_py / coworld
docker build --platform linux/amd64 -f crewborg/coworld/Dockerfile -t crewborg:dev .
coworld upload-policy crewborg:dev --name crewborg-lw --run python --run -m \
  --run crewborg.coworld.policy_player --secret-env CREWBORG_DEDUCTION_HISTORY=1
```

Gate-1 local smoke (mixed Prime roster, 2 episodes):
`EXTRA_ENV="CREWBORG_DEDUCTION_HISTORY=1" crewrift-analysis/selfplay.sh <label> <image> 2 <outdir>`
— `selfplay.sh` passes **no** base flags, so anything you want on must go in `EXTRA_ENV`.

## Infra gotchas — these will bite you

- **VM is 7GB / 2 vCPU.** Never `--workers 8` (replay expanders ~0.35GB each). Cap ≤2.
- **`crewrift-analysis/fetch.sh` passes `--no-logs`, which also suppresses policy
  artifacts.** An empty `policy_artifacts: []` therefore means *your fetch flag*, not a
  version that lacks telemetry. Re-fetch without it when you need traces.
- **League/tournament episodes carry results, per-agent logs and our own policy
  artifacts**, the same set an experience request gives you. They are served by the
  `/v2/episode-requests/...` routes after resolving `tags.job_id` through
  `/v2/episode-requests/by-job/{job_id}`, which `fetch_artifacts.py` does for you.
  The `/jobs/{job_id}/...` routes are Softmax-team-only and answer **403** — a
  best-effort GET turns that into a silent "artifact unavailable", so never read that
  message as evidence an artifact does not exist. Check the status code.
- **`xp_py` / `wh_py` are shell functions**, so `timeout xp_py …` fails with "command
  not found". Call them directly, or wrap the inner python.
- `fetch_artifacts -n` defaults to 10 and caps the TOTAL across multiple `--xreq` —
  fetch each arm separately.
- **There is no cancel or delete for an experience request.** `xp_fire.sh` prints only
  the id (the underlying tool prepends a WARNING line that breaks naive JSON parsing —
  that caused a double-fire once). Check `coworld xp-request list` before re-firing.
- softmax.com throws intermittent Cloudflare 504s on uploads/creates; the write often
  **succeeded** server-side anyway. Verify before retrying.
- Slot→colour on Prime is fixed: `red blue green pink orange yellow purple cyan`, and
  `results.json["imposter"]` is by slot — that is how ground truth joins to traces.

## Pointers

- Standing plan: `players/crewborg/docs/2026-07-25-crew-plan-deduction-first.md`
- This A/B: `players/crewborg/docs/experiments/2026-07-25-deduction-architecture-hosted-ab.md`
- Backlog + retained-experiment policy: `players/crewborg/docs/TODO.md`
- Version → config map: `players/crewborg/crewborg/version_log.md`
- Durable findings: `~/.claude/projects/-home-exedev-projects-softmax/memory/`
- Runtime model reference: `players/crewborg/crewborg/docs/deduction-history.md` and
  `.../docs/suspicion.md`
