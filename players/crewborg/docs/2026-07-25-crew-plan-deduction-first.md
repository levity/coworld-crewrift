# Crew improvement plan — solver-first, suspicion_lab as the lab (2026-07-25)

Supersedes the direction in the worktree's `HANDOFF.md`. Read the **Corrections**
section before acting on anything in that file.

---

## 0. Corrections to HANDOFF.md (all verified this session)

`HANDOFF.md` is accurate about the freeze fix, the six failed movement experiments,
and the infra gotchas. Its **central framing is wrong**, and one factual claim about
the shipped champion is wrong. Both errors point the next iteration at dead code.

### 0.1 There are two crewmate architectures, and the champion runs the weaker one

| | Path A — fitted posterior | Path B — solver / deduction history |
|---|---|---|
| Code | `strategy/suspicion.py` (`_fitted_features`, `_fitted_log_odds`, `top_suspect`) | `deduction/` (+ older `strategy/meeting/solver.py`) |
| Model | per-player L1 logistic, `logit = intercept + Σw·x` | joint enumeration of every fixed-size impostor assignment, role-conditioned likelihoods, structural exclusions, parity-aware decision |
| Trained by | `suspicion_lab/` → `data/suspicion_weights.json` | **nothing — 22 hand-set constants in `InferenceConfig`/`SolverConfig`** |
| Enabled by | default | `CREWBORG_DEDUCTION_HISTORY=1` (crew-only), `CREWBORG_SOLVER=1` |
| Votes at | ~13 ticks into Voting | ~1153 ticks (deadline backstop), speaks at +241 |

When `CREWBORG_DEDUCTION_HISTORY=1`, `modes/attend_meeting.py:109` short-circuits the
entire Path A crew flow, and `belief.suspicion` is cleared for crew. The two paths do
not compose for crewmates; only the *old* `strategy/meeting/solver.py` consumes the
fitted posterior, as a tempered prior (`prior_strength=0.20`).

**The claim that crewborg-lw's base config includes deduction-history is true for
v2/v3 and false for v4 onward.** Verified empirically: 12 episodes fetched from the
escort A/B control arm (`xreq_32db3512`, crewborg-lw:v4) show slot-0 voting at
**+10…+15 ticks** with `"<color> sus: they were tailing me"` chat at +1 — the Path A
deterministic accuse-and-vote signature. crewborg-lw:v2 traces show +1153…+1161 and
`"X and Y both point to Z. vote Z"` at +241 — Path B. Confirmed directly from v4's own
telemetry: its meeting trace is `domain.meeting_decision` with
`path: "silent_skip"`, `top_suspect: null`, **`solver.fired: false`**, and **zero**
`domain.deduction_history_decision` events. v4 was uploaded with **no `CREWBORG_*`
behaviour flags at all** (lean default tracing). Somewhere in the v3 → v4 rebuild
(`crewborg:escort-v2`) the whole `--secret-env` set was dropped, taking the branch's
namesake architecture with it. `version_log.md` still describes v4/v5 as carrying
"base config".

*(Correction to an earlier draft of this doc: v4/v5 do still emit telemetry. The
empty `policy_artifacts: []` seen at first was an artifact of fetching with
`--no-logs`, which also suppresses the policy-artifact download — not of the upload.)*

This also *resolves* the apparent contradiction in HANDOFF: the vote-gate sweep and the
aaln vote-policy port really did move behaviour, because v4+ genuinely runs Path A.

### 0.2 "The posterior is the blocker, and 0.9 is optimal" is true of Path A only

Measured on Crewrift Prime, forced-crew, subject seat:

| | Path A (crewborg-lw v4/v5, gate 0.9) | Path B (crewborg-lw v2) |
|---|---|---|
| targeted votes | ~12% of ballots | 28 / 202 ballots (13.9%) |
| **at-impostor precision** | **69.5%** (gate sweep, 200 games) / 71.4% (vote-policy A/B) | **28 / 28 = 100%** (200 games) |

Same game, same field, same coverage, wildly different precision. Fisher exact on
28/28 vs 17/24 ≈ `p = 0.006`. The "better-calibrated posterior" that HANDOFF says we
need before we can vote more **already exists on this branch** and has already been
run on Prime.

### 0.3 Path B has large untapped coverage headroom — measurable for free

Extracted all 266 `domain.deduction_history_decision` traces from the 200 prime-gt
policy artifacts already on disk (`ba2ec2e2/tmp/prime-gt-wh_episodes`) and swept the
top-marginal bar against ground-truth roles from `results.json` (slot→colour is fixed:
`red blue green pink orange yellow purple cyan`):

| top-marginal bar | ejects | at-imp | at-crew | precision | coverage |
|---|---:|---:|---:|---:|---:|
| shipped policy (0.65/0.80 + gates) | 79 | 79 | 0 | **100.0%** | 29.7% |
| 0.80 | 78 | 78 | 0 | 100.0% | 29.3% |
| 0.65 | 93 | 92 | 1 | 98.9% | 35.0% |
| 0.55 | 122 | 116 | 6 | 95.1% | 45.9% |
| **0.50** | 156 | 144 | 12 | **92.3%** | **58.6%** |
| 0.45 | 190 | 174 | 16 | 91.6% | 71.4% |
| 0.40 | 248 | 202 | 46 | 81.5% | 93.2% |

Path B can roughly **double its vote volume and still be ~92% precise** — far above
Path A's 69.5% at a quarter of the coverage. "Vote more" is the wrong move for Path A
and the right move for Path B.

*Caveats, stated honestly:* these are single-observer decisions, not team ejections;
the sweep uses the raw top marginal and ignores the margin / `min_independent_sources`
/ structural gates (which cost 14 ejects at 0.65); and it is counterfactual — an
ejection changes every later meeting. It is an offline ranking-quality gate, not a
win-rate estimate.

### 0.4 The one thing that genuinely favours Path A

crewborg-lw v2 (Path B) scored **win 14.0%, all-8 tasks 36.5%** over 200 prime-gt
games; v4 (Path A) scored **win 20%, all-8 52%** over 100 escort-A/B games on a
near-identical Prime roster. But **v2 predates the edge-park freeze fix**, which is
precisely a task-completion bug. The comparison is confounded by the largest known
defect in the codebase. The missing experiment — Path B *on the freeze-fix image* —
has never been run. That is Phase 0.

---

## 1. Answering the question: does suspicion_lab suit us?

**Its model does not. Its method and infrastructure do, almost perfectly.**

- suspicion_lab produces exactly one artifact: `suspicion_weights.json`, the
  coefficients of Path A's per-player logistic. Under Path B that file is inert for
  crew. Refitting it — HANDOFF's plan steps 1–4 — cannot change a single crewmate
  vote while deduction-history is on. Under Path A it can, but Path A is the 69.5%
  engine we should be leaving behind.
- Everything *around* the model is what we actually lack: a scraped labelled corpus,
  observer-exact visibility clipping, ground-truth role joins, game-grouped CV,
  decision-level evaluation against always-skip, the "fit runtime-traced features,
  never offline reconstructions" lesson, and the discipline of a vendored,
  schema-versioned weights artifact.
- Meanwhile Path B's 22 likelihood constants (`crew_accuse_hit = 0.58`,
  `imp_accuse_partner = 0.08`, `crew_vote_imp = 0.48`, …) are **hand-guessed**, and
  every one of them is a directly countable conditional probability over a labelled
  corpus. `alibi_weight` is hard-zeroed with the comment "unless a future calibrated
  model explicitly opts in" — that calibration is exactly what suspicion_lab's
  machinery produces.

So, of the four options:

| Option | Verdict |
|---|---|
| Keep the solver, also keep refitting suspicion_lab's logistic for crew | No — the refit is inert under Path B. Pure churn. |
| Abandon the solver, use suspicion_lab as designed | No — that trades a measured 100%-precision engine for a 70% one. |
| Abandon suspicion_lab | No — we'd be throwing away the only corpus/eval infrastructure we have. |
| **Secret third option — recommended** | **Make the solver the crew brain; retarget suspicion_lab from "fit the logistic" to "be the solver's lab": the same corpus and eval discipline, fitting `InferenceConfig`/`DecisionConfig` instead of `suspicion_weights.json`.** |

Path A keeps its job — it still drives **impostor** deflection targeting, where it is
never short-circuited. If we later want the perceptual posterior back inside crew
reasoning, it re-enters as *one more evidence channel with a measured weight* in the
solver, not as a competing decision-maker.

---

## 2. The plan

### Phase 0 — Reinstate and de-risk (1 hosted A/B, ~1 day)

The cheapest highest-information experiment in the backlog. If Path B doesn't beat
Path A end-to-end once the freeze bug is gone, the rest of this plan needs rethinking.

- **0a.** Correct `version_log.md` (v4/v5 do **not** carry the base flag set) and this
  branch's `HANDOFF.md`.
- **0b.** Build from the freeze-fix HEAD; upload two versions off the **same image**:
  - control = current champion config (Path A, no deduction flag)
  - candidate = `CREWBORG_DEDUCTION_HISTORY=1 CREWBORG_SOLVER=1 CREWBORG_SOLVER_EARLY_CHAT=1 CREWBORG_STICK=1 CREWBORG_ALIBI=1`
  - **both with full telemetry.** Non-negotiable from here on (§3, invariant 6).
- **0c.** Homogeneous roster (6× subject crew + 2× crewborg-aaln impostors), 100/arm,
  per the repo's own eval-design rule — this is a voting/team-outcome change, so team
  ejections must be in scope.
- **Pre-registered:** primary = team win rate. Secondary = subject vote precision and
  coverage, team impostor vs crew ejections. **Guardrail (must not regress):** all-8
  task rate and mean tasks — Path B defers its ballot to the deadline backstop, so
  confirm that costs nothing in tasks.

### Phase 1 — Pick the operating point (offline first, then 1 A/B)

- Extend `tools/evaluate_deduction.py` to consume the hosted **decision-trace corpus**
  as a first-class input (the ad-hoc extraction in §0.3 becomes a supported path).
  It already has the threshold grid and calibration buckets.
- Sweep the real `DecisionConfig` — `base_probability`, `base_margin`,
  `dangerous_wrong_eject_probability`, `forced_vote_probability`,
  `min_independent_sources` — **with the source and structural gates applied**, not
  just the raw marginal.
- Choose by expected net value, with the crew-eject penalty **derived from parity
  math** (a wrong eject moves the board toward parity; a miss does not), not guessed.
- Ship one gate change, one A/B. Do not bundle it with Phase 0.

### Phase 2 — Features from human ideas × automated analysis

Two feeder streams, one ranked backlog, one item implemented per cycle.

**2a. Automated cue mining (free — the corpus is already on disk).**
Over expanded replays with ground-truth roles, at the (observer, suspect, meeting)
grain, measure the empirical log-likelihood-ratio and confidence interval of every
candidate cue. suspicion_lab's `features.py` catalogue is the template; the *output*
is solver channel log-LRs, not logistic coefficients. Rank by
`|log LR| × frequency`, discard anything not runtime-admissible.

The first deliverable is the one with the best effort/return ratio in the whole plan:
**replace all 22 hand-set numbers in `InferenceConfig` with measured values.** Each is
a plain conditional frequency —

- `crew_accuse_hit` = P(a crew speaker's accusation names a real impostor)
- `imp_accuse_partner` = P(an impostor accuses their own partner)
- `crew_vote_imp`, `imp_vote_crew`, `crew_defend_imp`, … = the same over ballots
- the decay/weight parameters (`repeat_decay`, `relay_weight`, `bare_weight`, …) by
  maximising labelled joint likelihood over the corpus

Zero hosted cost, and it converts the solver's core from guesswork to measurement.

**2b. Human hypotheses (structured intake).** Each idea is written as a falsifiable
mechanism pinned to code, *with the offline signal that must move before it earns a
hosted A/B*. Seeds, taken from the deduction path's own stated limits:

- **Structural evidence is the highest-value class** because it excludes assignments
  outright rather than nudging a likelihood. Two are listed as not-yet-extracted:
  body-location contradictions, and map-reachability kill windows. Both are pure
  additions to `derive_evidence` / `build_assignment_table`.
- **Parser coverage.** The claim parser is "deterministic and deliberately
  incomplete." Measure the unparsed-utterance rate on the corpus and what fraction of
  unparsed lines carry role signal, then extend only where the signal is.
- **Task-counter events never clear anyone.** With reachability plus visibility this
  may become sound — and it is the cue suspicion_lab found strongest offline
  (`tasks_completed_watched`, −10.9) but had to zero at runtime.
- **`alibi_weight = 0.0`.** Phase 2a produces the calibration its comment asks for.

Score the merged backlog by `measured effect size × (1 / implementation cost) ×
runtime admissibility`. Top item only.

### Phase 3 — Iterate without churning

The anti-churn contract. Most of this the repo already does well; the failures came
from skipping one of these, not from lacking them.

1. **Offline gate before every hosted spend.** A change must move a pre-registered
   offline metric on **held-out** games (grouped by game, never by row) to earn an A/B.
2. **One change per A/B.** Flag-gated, default-off until it wins.
3. **Pre-register the analysis** — primary metric, n, decision rule — before looking.
4. **Never re-tune on the games you measured on.** The deduction docs already flag
   this risk ("rather than fitting a threshold to reused games"); make the held-out
   split mechanical.
5. **Kill criteria.** A direction with two mechanism-level failures is closed.
   Survival-via-movement should have been closed after three attempts, not six.
6. **Champion invariants.** Every uploaded champion carries full telemetry, and its
   `version_log.md` row records the *actual* `--secret-env` line, **verified from a
   fetched trace before the row is written.** This single check would have caught the
   v3 → v4 architecture drop the day it happened.
7. **Do not touch `_fitted_features` for crew** while Path B is the crew brain. It is
   dead code on that path; editing it is churn by construction. (This explicitly
   cancels HANDOFF's plan steps 1–4.)

### Phase 4 — What happens to suspicion_lab, concretely

- **Keep verbatim:** `scrape_corpus.py`, `expand_corpus.py`, `replay_parse.py` — the
  corpus layer is model-agnostic and is the asset.
- **Add `fit_solver.py`:** labelled counting / MLE for `InferenceConfig`, emitting a
  vendored, schema-versioned `data/deduction_likelihoods.json` on the same pattern as
  `suspicion_weights.json`, with the same "loader never raises, falls back to the
  hand constants" contract.
- **Add solver eval:** fold the decision-trace corpus into `evaluate_deduction.py`
  (Phase 1) rather than building a second harness.
- **Retire for crew:** the offline `build_dataset.py` → `fit.py --features runtime`
  path. Keep `build_dataset_runtime.py` in case the *impostor* posterior is ever
  refit.
- **Leave `nightly_refit.sh` disabled** until it targets the solver artifact —
  re-enabling it now would nightly-churn a champion nobody uses.

---

## 3. Immediate next action

Phase 0b/0c: build the freeze-fix image, upload the two versions with telemetry, fire
the homogeneous 100/arm A/B. Everything in Phase 1 and Phase 2a is free and can run
against data already on disk while that A/B is in flight.

**Open decision for the human:** Phase 0 spends 200 hosted games to test an
architecture switch rather than a new idea. The alternative order — do the free Phase
2a likelihood fit first and A/B the fitted solver in one shot — saves one A/B but
confounds "solver vs no solver" with "fitted vs hand constants". Recommend paying for
the clean attribution.

## Appendix — how the §0.2–0.3 numbers were produced

```sh
# Path A signature (12 episodes, escort A/B control arm)
crewrift-analysis/fetch.sh <out> xreq_32db3512-c7a1-48ac-b725-1f897394c5e5   # FETCH_N=12
crewrift-analysis/bin/expand-prime --format jsonl --snapshot-every 480 <ep>/replay.json

# Path B precision (200 prime-gt games; expand only the 26 with a targeted vote)
#   join vote_cast.target_slot -> player_state.role

# Path B coverage curve (no expansion needed)
unzip -p <ep>/artifacts/policy_artifact_*.zip telemetry.jsonl \
  | grep -F domain.deduction_history_decision
#   join decision.inference.marginals -> results.json["imposter"] via the fixed
#   slot->colour map: red blue green pink orange yellow purple cyan
```

Test suite on this worktree at the time of writing: **611 passed, 13 skipped**; the
15 failures + 8 errors are environment-only (`pytest-asyncio` missing for
`test_bridge.py`, `spacy` missing for `test_chat_read.py`). No deduction, solver, or
suspicion test fails.
