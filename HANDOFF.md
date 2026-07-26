# crewborg crew-improvement — handoff (2026-07-25)

> ⚠️ **SUPERSEDED 2026-07-26 — do not act on the plan in this file.** Its central
> framing ("improve the fitted posterior via suspicion_lab") targets code that is
> **dead for crewmates**: `CREWBORG_DEDUCTION_HISTORY=1` clears `belief.suspicion` and
> routes the crew ballot through `deduction/`. Two of its factual claims are also
> wrong — crewborg-lw v4/v5 carry **no** `CREWBORG_*` flags (so v6–v12 all measured the
> fitted path, not the solver), and "voting is posterior-capped, 0.9 is optimal" is true
> only of that fitted posterior, which measures **AUC 0.355 — worse than random**. The
> deduction path scores 0.83 and won its hosted A/B (team win 28% → 49%, `p=0.0035`).
> Read [`players/crewborg/docs/2026-07-25-crew-plan-deduction-first.md`](players/crewborg/docs/2026-07-25-crew-plan-deduction-first.md)
> instead. The sections below on the freeze fix, the six failed movement experiments,
> and the infra gotchas remain accurate and useful.


Worktree: `coworld-crewrift/.claude/worktrees/crewborg-deduction-history`, branch
`crewborg-deduction-history`. Analysis tooling lives in a SEPARATE standalone git
repo: `/home/exedev/projects/softmax/crewrift-analysis` (read its README first).

## Mission
Improve crewborg's **crewmate** results on **Crewrift Prime** (`crewrift_prime:0.4.69`,
coworld `cow_0ba5e866`, league champion path). Loop = build → local smoke → hosted XP
A/B → analyze → report. Human submits to the league (Gate 2); we only upload (inert).

## The single most important framing (read this)
crewborg's suspicion model is a **fitted "baby neural network"**: `posterior logit =
intercept + Σ w·x` over a runtime feature vector (`crewborg/strategy/suspicion.py`
`_fitted_features`), weights vendored in `crewborg/data/suspicion_weights.json`, **learned
by the `suspicion_lab/` pipeline** (the hand model is a deprecated fallback). To improve
the posterior you **add/clean features in our solver AND re-learn weights via
suspicion_lab** — do NOT hand-weight (fights the architecture) and do NOT reject
suspicion_lab (it IS the training half of our own solver). Use it judiciously (see plan).

## Current state of the branch
- **SHIPPED / default-ON — the edge-park freeze fix** (`2525752`, `action.py`
  `_resolve_complete_task`): the multi-hundred-tick "frozen crewmate" bug. Root cause: a
  ~4px self-localization error + the ARRIVE_RADIUS=4 nav threshold park the agent 1px
  outside the exclusive task-rect bound, so it mashes A forever without the sim
  activating the task. Fix gates the A-hold on the ground-truth progress bar and nudges
  to the rect center. **Validated locally (loss→win) and hosted (0/200 games with
  pathological stall).** This is the real win so far; base the next champion on it.
- **All other session features are FLAG-GATED OFF (inert) — rejected/neutral experiments:**
  - `CREWBORG_POST_TASK_ESCORT` (normal.py) — post-task escort. Hosted A/B: **NEUTRAL**.
  - `CREWBORG_VOTE_POLICY` (suspicion.py + strategy/meeting/vote_policy.py) — state-aware
    crew vote policy ported from aaln. Hosted A/B: **REGRESSED** (win 31%→12%; it voted
    more but precision collapsed 71%→39% — our POSTERIOR can't support more voting).
  - `CREWBORG_WITNESS_TASKING` (normal.py) — witness-while-tasking survival. Hosted A/B:
    **CATASTROPHIC** (all-8 48%→7.8%, win→0%). Partly a homogeneous-roster herding
    artifact, but survival-via-movement is a dead end (see learnings).
- Also present from before: `CREWBORG_POST_TASK_LOITER`, `CREWBORG_GROUP_TASKING` (both off).

## Hard-won learnings (don't re-derive these)
1. **crewborg-lw is ALREADY the best crewmate in the field.** In the same 200 games,
   crew murder rate: crewborg-lw 50.5% < notsus 62% < crewborg-aaln 63%; all-8 tasks:
   crewborg-lw 51% > aaln/notsus 37%. The low ~20% *team* win is dominated by weak FILLER
   teammates + strong impostors, NOT our policy. **Do NOT switch to crewborg-aaln** — it's
   a downgrade on survival AND tasks (it's a parallel fork on a different SDK, hand-weighted).
2. **Voting is posterior-capped.** Our crew votes skip 88% at 0.9 (100%-ish precise) — and
   that 0.9 bar is ~optimal. A gate sweep (0.9/0.7/0.5) and the aaln vote-policy port BOTH
   lost because our fitted posterior is near-random below 0.9 (at gate 0.5, 64% of targeted
   votes eject CREWMATES). Can't fix voting with a knob or policy — needs a better POSTERIOR.
3. **WHY aaln votes well and we don't** (the actionable insight): aaln CONDITIONS its social
   features where we LUMP them. Our 3 counters (`accusations_made`/`times_accused`/
   `times_defended` in `strategy/social_evidence.py`) mix the noise of bare "X sus"
   accusations (measured 0/185 at naming a real impostor) with real evidence-backed signal,
   so the logistic can't separate them. aaln: bare-sus EXCULPATES the target + incriminates
   the speaker; accusation BY a confirmed impostor inverts; crowd = ≥2 distinct
   evidence-backed non-confirmed accusers; plus a game-state/margin prior. (aaln source:
   `players/crewborg-aaln/players/crewrift/crewborg/strategy/suspicion.py` + `vote_policy.py`.)
4. **Survival-via-movement is a dead end (6 failures):** reactive repulsion/isolation-
   pursuit/witness-seeking/safe-distance, post-task escort, witness-tasking. 78% of our crew
   die truly isolated, 85% pre-task, in peripheral TASK rooms (Storage Deck/Med Bay/Science
   Bay 1.6–1.9× enriched; the Bridge hub is SAFEST at 0.2×). Clustering doesn't help — even
   fully clustered, murder went UP; "safety in numbers" doesn't deter these impostors, and
   equal crew/impostor speed means no escape. Stop trying to fix survival with movement.
   (Death analysis script: `crewrift-analysis/lw_death_analysis.py`.)
5. **Eval-design rule:** use a HOMOGENEOUS crew roster (6× subject crew + 2 aaln impostors)
   for VOTING/team-outcome changes; use a MIXED roster (1 subject + diverse crew) for
   COHESION/survival changes — a homogeneous crew of a cohesion behavior mutually herds into
   a task-doing-nothing huddle.
6. **suspicion_lab train/serve gap:** naive OFFLINE refits "churned versions without moving
   outcomes" because offline-reconstructed features diverge from runtime. Use the
   RUNTIME-TRACE path (`build_dataset_runtime.py` + `CREWBORG_TRACE_SUSPICION_FEATURES=1`),
   which reads crewborg's own traced feature vectors — no divergence, no duplicate feature code.

## THE PLAN (agreed direction) — improve the posterior
1. **Feature engineering in OUR solver (free, do first):** in `strategy/suspicion.py`
   `_fitted_features` + upstream `strategy/social_evidence.py`, split the lumped social
   counters by evidence_kind (`social_evidence.py` `_evidence_kind`) and speaker status
   (accused/defended BY a confirmed impostor → signed; use `witnessed_imposters()`), add a
   corroboration count (≥2 distinct evidence-backed non-confirmed accusers), and a
   game-state/margin term (imposters_remaining / alive_count). Keep the existing witnessed
   kill/vent/tail features (identical to aaln — not the problem).
2. **Re-learn weights via suspicion_lab's RUNTIME-TRACE path** (our training loop):
   trace-enabled build → few hundred hosted trace episodes → `build_dataset_runtime.py` →
   `fit.py --features runtime` → `eval.py`. **Skip** the offline `build_dataset.py`/
   `features.py` path (train/serve gap + duplicate feature code). **Cap ALL parallelism at
   ≤2 workers** (this VM is 7GB/2-vCPU; `--workers 8` OOM'd and stalled the box).
3. **Validate gate:** held-out AUC must rise AND decision-level vote precision must not
   regress, else don't ship (respects the "refits didn't move outcomes" history).
4. **Ship + hosted A/B** (new posterior vs current, homogeneous roster).

**OPEN DECISION for the human:** the runtime-trace corpus needs a few hundred hosted TRACE
episodes to capture feature vectors (our existing 800 games weren't traced) — that hosted
capture is the one real cost. Step 1 (features) is free groundwork; checkpoint before the
corpus capture.

## Infra gotchas (will bite you)
- **VM is 7GB / 2 vCPU.** NEVER run `--workers 8` (replay expanders ~0.35GB each). Cap ≤2.
- **Background jobs have a ~5-min runtime cap** — long work (xp_wait + fetch + build) gets
  killed mid-run. STAGE it: separate bg jobs for fetch / build / analyze. `build.py`
  checkpoints per batch (resumable); `fetch.sh` is idempotent.
- **softmax.com had Cloudflare 504s on uploads/creates (2026-07-25)** — transient; often the
  write actually SUCCEEDED server-side despite the 504 (check `coworld xp-request list`
  before re-firing to avoid duplicates; there is NO cancel/delete for an xreq).
- Tooling env: `source crewrift-analysis/env.sh` (defines `xp_py`/`wh_py` runners + puts
  `coworld` on PATH — don't drop its `export PATH` line). `coworld` needs env.sh sourced.
- `fetch_artifacts -n` defaults to 10 and caps the TOTAL across multiple `--xreq` — fetch
  each arm separately (use `crewrift-analysis/fetch.sh`). Use `xp_fire.sh` to create (its
  output prepends a WARNING line that breaks naive JSON parsing → caused a double-fire).

## Pointers
- Memory (durable findings): `~/.claude/projects/-home-exedev-projects-softmax/memory/`
  (see `crewborg-task-edge-freeze`, `crewborg-vote-gate-sweep-result`,
  `crewborg-vote-policy-rejected`, `crewborg-witness-tasking-rejected`,
  `crewborg-escort-ab-result`, `crewborg-targets-crewrift-prime`).
- Experiment docs: `players/crewborg/crewborg/version_log.md` (v4–v12 map) and
  `players/crewborg/docs/experiments/2026-07-2[3-5]-*.md`, `docs/TENTATIVE_LESSONS.md`.
- Uploaded crewborg-lw versions (all inert): v4 ded9bc9b (freeze-fix base, no flag),
  v5 f9fddccf (escort), v6 099e5f44 / v7 a2355e72 (vote gate 0.7/0.5), v8 a332c7d8 (vote-
  policy off) / v9 80b307b6 (on), v10 c782210c (witness off) / v12 248d02b0 (on).
- Built warehouses on disk (may be cleaned): `$CLAUDE_JOB_DIR/tmp/*-wh` and the Prime
  expander `crewrift-analysis/bin/expand-prime`.

## Immediate next action
Confirm worktree/branch home (this branch has 9 inert-experiment + freeze-fix commits), then
start PLAN step 1 (feature engineering in suspicion.py/social_evidence.py — no hosted cost).
