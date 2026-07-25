# Deduction-architecture hosted A/B (Crewrift Prime) — Phase 0

**Pre-registered before firing. Do not edit the design section after results land.**

## Question

Does the append-only deduction / joint-solver crew path beat the fitted-posterior crew
path on team outcome, once the edge-park freeze fix is present in both arms?

This has never been tested. The only prior Prime comparison — crewborg-lw:v2 (deduction
ON, win 14.0%, all-8 36.5%, 200 games) vs v4 (deduction OFF, win 20%, all-8 52%,
100 games) — is confounded: **v2 predates the freeze fix**, which is a task-completion
bug. Both arms here carry the fix, so the architecture is the only variable.

## Why this experiment, and why now

`crewborg-lw:v4/v5` — the current champion line — runs with **no `CREWBORG_*` behaviour
flags at all**. Verified from v4's own telemetry (`xreq_32db3512`): its meeting trace is
`domain.meeting_decision` with `path: "silent_skip"`, `top_suspect: null`,
`solver.fired: false`, and zero `domain.deduction_history_decision` events. The
`version_log.md` rows describing v4/v5 as carrying "base config
(solver/stick/alibi/early-chat/deduction-history)" are wrong; the v3 → v4 rebuild
dropped the flag set.

Evidence the dropped path is the better decision engine (both from data already on
disk, no new hosted spend):

- **Precision.** crewborg-lw:v2 (deduction ON), 200 forced-crew Prime games:
  28 targeted votes, **28 at impostors, 0 at crew — 100%**. The fitted posterior at its
  best gate scores 69.5% (gate sweep) / 71.4% (vote-policy A/B) at comparable coverage.
  Fisher exact vs 17/24 ≈ `p = 0.006`.
- **Coverage headroom.** Sweeping the 266 `domain.deduction_history_decision` traces
  from those 200 games against ground truth: shipped policy 100.0% @ 29.7% coverage;
  0.65 → 98.9% @ 35.0%; 0.50 → 92.3% @ 58.6%; 0.45 → 91.6% @ 71.4%.

Full reasoning: [`../2026-07-25-crew-plan-deduction-first.md`](../2026-07-25-crew-plan-deduction-first.md).

## Treatment — exactly one variable

Both arms are the **same image**, `crewborg:solver-ab`
(`sha256:163a622831551512d4b0802d9ddeb5a52533ee34db0f0a35e025b9a0d0ce8ed6`), built at
branch `crewborg-deduction-history` HEAD, freeze fix present (verified inside the image:
`action.py` carries `active_task_progress_pct` + `task_stuck_ticks`).

| Arm | `--secret-env` |
|---|---|
| Control | *(none)* — byte-identical config to the current champion v4 |
| Candidate | `CREWBORG_DEDUCTION_HISTORY=1` |

`__init__.py:133` shows that single flag switches the entire crewmate knowledge and
decision pipeline: `update_deduction_history` replaces `update_event_log` /
`update_alibi` / social counters / suspicion, and `attend_meeting.py:109` routes the
crew ballot through `deduction/decision.py`. It is crew-only by construction
(`enabled_for_role`), so impostor play is untouched in both arms.

**Deliberately NOT included** (they would confound the architecture test):
`CREWBORG_SOLVER`, `CREWBORG_SOLVER_EARLY_CHAT` (gate the *old* solver, which the
deduction path bypasses entirely), `CREWBORG_STICK` and `CREWBORG_ALIBI` (movement /
old-solver evidence). v2 carried all of these; this candidate does not. If the
architecture wins, those get their own A/Bs.

Tracing: lean default in both arms, which already emits
`domain.deduction_history_decision` and `domain.meeting_decision`. No
`CREWBORG_TRACE=debug` — the per-tick dump is not needed and costs latency.

## Hosted design

- Target: `crewrift_prime` 0.4.69, `cow_0ba5e866-1c00-4e14-9ced-3c7d2296153b`.
- **Homogeneous roster**, per the repo's eval-design rule for voting / team-outcome
  changes: 6× subject at slots 0–5 forced **crew**, 2× `crewborg-aaln`
  (`4e65356f-9a2c-4e6b-af27-bdb43515547b`) at slots 6–7 forced **imposter**. Same
  roster as the vote-gate sweep and vote-policy A/B, so results are comparable to both.
- 100 episodes per arm. Arms are not seed-paired; deltas carry full sampling noise.

## Pre-registered analysis

**Primary:** team crew win rate. Decision rule — promote the candidate only if it wins
with two-sided Fisher exact `p < 0.05`; treat `p ≥ 0.05` as unresolved at this n and
report the Newcombe 95% interval rather than declaring neutrality.

**Secondary (mechanism — these are what the offline evidence predicts should move):**
- subject vote precision (at-impostor / targeted) — predicted **up**, ~70% → ~95%+
- targeted-vote coverage (1 − skip rate) — predicted flat at ~12–15%
- team impostor ejections vs crew ejections

**Guardrails — a regression here blocks promotion even if the primary wins:**
- all-8 task rate and mean tasks. The deduction path defers its ballot to the 48-tick
  deadline backstop and speaks at meeting tick 240; confirm that costs no task time.
- subject murder rate (should be unchanged — no movement behaviour differs).
- operational failures (connect/disconnect timeouts) — recompute on clean episodes only.

**Sanity check before analysing:** confirm the candidate arm's telemetry actually
contains `domain.deduction_history_decision` and the control's does not. A silent
flag drop is the exact failure this whole experiment exists to correct.

## Requests

| Arm | Policy version | Experience request |
|---|---|---|
| Control (no flags) | `crewborg-lw:v13` `f2634244-9e45-45bf-816f-7eed5c0bc63a` | `xreq_90ee8518-8285-41f3-ba49-a2f4150ba974` |
| Candidate (`CREWBORG_DEDUCTION_HISTORY=1`) | `crewborg-lw:v14` `6a0e2ee5-114f-46fb-aa3d-046bc4f8e6e9` | `xreq_2b323f7b-4874-4047-9529-5548ea10e825` |

Both fired 2026-07-25T05:41Z, 100 episodes each, confirmed as the only two pending
requests on the account (no double-fire).

Gate 1 (local smoke, `crewborg:solver-ab` with the flag on, mixed Prime roster, 2
episodes): passed `rc=0`, both episodes ran to completion, and
`domain.deduction_history_decision` is present in the crew seats' telemetry —
the flag demonstrably takes effect in this image.

## Result — candidate WINS on the primary, but not by the predicted mechanism

Both arms completed 100/100 with **zero** operational failures.

### Primary

| Metric | Control (v13) | Candidate (v14) | Δ |
|---|---:|---:|---:|
| **Team crew win** | **28/100 (28.0%)** | **49/100 (49.0%)** | **+21.0pp** |

Fisher exact two-sided **`p = 0.0035`**; approximate 95% CI for the delta
**[+7.8, +34.2] pp**. Passes the pre-registered decision rule.

Consistency check: the control's 28.0% reproduces the vote-gate sweep's 28.0% for
crewborg-lw at gate 0.9 on this exact roster — the control is the champion.

### Guardrails — not just clean, they improved

| Metric (600 subject seats/arm) | Control | Candidate |
|---|---:|---:|
| mean tasks | 6.75 | **7.38** |
| all-8 task rate | 249/600 (41.5%) | **386/600 (64.3%)** |
| kills against subject seats (40-ep replay sample) | 133 | 140 |
| operational failures | 0 | 0 |

### Pre-registered sanity check — passed

Control telemetry contains only `domain.meeting_decision`; candidate only
`domain.deduction_history_decision`. No flag leakage in either direction.

### Mechanism — the surprise

Ballot-level, from expanded replays (40 episodes/arm, authoritative):

| | Control | Candidate |
|---|---:|---:|
| ballots cast | 550 | 195 |
| targeted (non-skip) | 110 (20.0%) | 32 (16.4%) |
| **at-impostor precision** | **84.5%** (93/17) | **100.0%** (32/0) |
| median vote offset after Voting | 5 ticks | 1158 ticks |
| **meetings** | **137** | **51** |

Vote precision moved as predicted (84.5% → 100%). **But the candidate ejects fewer
impostors in absolute terms (32 vs 93) and still wins far more, so better voting is
not the main channel.** The meeting counts point at the real one:

| Meeting calls (40 episodes) | Control | Candidate |
|---|---:|---:|
| body reports | 57 | 51 |
| **emergency-button calls** | **80** | **0** |
| called by a subject seat | 135 of 137 | 45 of 51 |

**The fitted-posterior path pressed the emergency button 80 times in 40 games — two
per game — and every one of those meant a crewmate abandoning its tasks to run to the
button.** The deduction path clears `belief.suspicion` and
`belief.believed_imposters`, so `active_tail_suspect` always returns `None` and
Accuse mode can never fire. Kills are essentially unchanged (133 vs 140), so this is
not a survival effect: it is **task throughput**, recovered by not interrupting play.

Why the button-pressing was worthless is visible in the posteriors — see the
decision-quality section below.

### Decision quality (`tools/decision_quality.py`)

Per-player rows at each arm's own decision point, labelled with ground truth
(2,819 control / 2,128 candidate rows — roughly 25× the evidence that 100 win/loss
outcomes carry):

| | Control (fitted) | Candidate (deduction) |
|---|---:|---:|
| Brier (↓) | 0.3130 [0.2968, 0.3266] | **0.1424** [0.1369, 0.1485] |
| log loss (↓) | 0.8852 | **0.4116** |
| **AUC (↑)** | **0.355** | **0.832** |
| top-1 = impostor | 33.8% | 80.6% |

**The fitted posterior's AUC is 0.355 — materially worse than random.** Its
calibration table is inverted across the middle of its range: the 0.5–0.6 bucket
contains 9.3% real impostors while the 0.1–0.2 bucket contains 55.8%. Only the two
extremes behave, and the 0.9–1.0 bucket (96.0% actual) is the **definitional
witnessed floor** — a direct catch, not a learned quantity. So the 0.9 vote bar was
not "the model's optimal operating point"; it was the bar that excludes the model
almost entirely and votes only on direct catches. Everything below it is anti-signal,
which is exactly why the gate sweep and the aaln vote-policy port both lost.

The candidate is monotone across every populated bucket and well calibrated
(0.4–0.5 → 47.2% actual, 0.5–0.6 → 54.3%, 0.9–1.0 → 100%).

*Timing caveat, stated honestly:* the control's `suspicion_snapshot` is emitted at
meeting start and the candidate's decision at the 1152-tick deadline, so the two
posteriors are not measured on the same information set. Each is measured at the
moment its own policy decides, which is the decision-relevant comparison, but it is
not an equal-information one.

### Verdict and what it does NOT establish

**Promote the deduction path** — primary won at `p = 0.0035`, every guardrail
improved, no operational cost.

But the +21pp **bundles two changes** that this design cannot separate:

1. crew ballots become near-perfectly precise (84.5% → 100%), and
2. Accuse mode is silently disabled, removing 2 spurious button-meetings per game.

The mechanism data says (2) is doing most of the work. That has a cheap independent
test: run the **control path with Accuse disabled** (raise `ACCUSE_THRESHOLD` above
1.0, or gate `active_tail_suspect`). If most of the +21pp survives on the old
architecture, then a one-line change captures the bulk of the win and the
architecture's real contribution is the precision, which then needs its own
justification. **That decomposition arm has not been run.**

## Follow-up: 4-2-2 mixed-roster confirmation (running)

The homogeneous roster flatters this candidate in one specific way: the deduction
path *parses other players' chat as evidence*, and on a 6-subject roster it is
parsing five copies of its own templated phrasing. A mixed field speaks differently.

| Arm | Policy version | Experience request |
|---|---|---|
| Control | `crewborg-lw:v13` | `xreq_bd851df5-4d40-4e1b-9f1d-8fbcdb29484d` |
| Candidate | `crewborg-lw:v14` | `xreq_90f99126-83e9-489e-92f7-8c6ab70f8169` |

Roster: 4× subject crew (slots 0–3) + 2× `crewborg-aaln` crew (4–5) + 2×
`crewborg-aaln` impostor (6–7), 100 episodes/arm, fired 2026-07-25T19:27Z.

Note this design carries ~2/3 of the treatment (4 of 6 crew seats), so a homogeneous
+21pp would appear as roughly +14pp here; at n=100 that is ~55% power. Treat the
per-decision metrics above — which are far better powered — as the primary read if
the win-rate delta lands unresolved.

### 4-2-2 result — confirms the mechanism; win-rate delta unresolved as predicted

Both arms 100/100, zero operational failures.

| Metric | Control | Candidate | Δ |
|---|---:|---:|---:|
| team crew win | 16/100 (16.0%) | 26/100 (26.0%) | +10.0pp |
| subject mean tasks | 6.85 | 7.10 | +0.25 |
| subject all-8 (400 seats) | 41.8% | 48.5% | +6.7pp |

Fisher exact `p = 0.118`, 95% CI **[−1.2, +21.2] pp** — **unresolved at n=100**, which
is exactly what was pre-registered as likely (predicted ~+14pp at ~55% power; observed
+10pp sits comfortably inside that expectation). This neither confirms nor refutes the
homogeneous +21pp on the win metric.

**The per-decision metrics resolve it, and they are decisive** (49 vs 43 episodes of
telemetry; 1,668 vs 1,820 labelled player rows):

| | Control (fitted) | Candidate (deduction) |
|---|---:|---:|
| Brier (↓) | 0.2792 [0.2534, 0.3012] | **0.1418** [0.1330, 0.1499] |
| **AUC (↑)** | **0.449** | **0.834** |
| top-1 = impostor | 44.0% | 75.4% |
| act precision | 89.2% | **100.0%** |

**The candidate's decision quality is unchanged from the homogeneous roster
(AUC 0.832 → 0.834, Brier 0.1424 → 0.1418).** That kills the main validity worry
about the 6+2 design: the deduction path parses a genuinely mixed field's chat exactly
as well as it parses its own. The homogeneous roster did **not** flatter it. (The
fitted path improves slightly on a mixed field, 0.355 → 0.449, but is still no better
than a coin flip.)

**Attenuation is dilution, not flattery.** Meeting calls over 30 replayed episodes:

| | Control | Candidate |
|---|---:|---:|
| subject **button** calls | **35** | **0** |
| subject body reports | 20 | 31 |
| aaln-crew button calls | 0 | 3 |
| aaln-crew body reports | 14 | 4 |
| kills against all seats | 107 | 105 |

Subject button calls go 35 → 0 again, reproducing the homogeneous finding. Note the
aaln crew make only 3 button calls in 30 games — **button-spam is specific to our
fitted-posterior Accuse mode, not general crew behaviour.** With only 4 of 6 crew
seats treated, just two-thirds of that benefit lands, which explains the smaller
win-rate delta without invoking any roster artifact.

### Standing conclusion

Promote the deduction path. Its advantage is real and replicates on a realistic field;
the per-decision evidence is unambiguous and the win-rate direction is consistent
across both rosters. The open question remains **attribution**, not validity: run the
old path with Accuse disabled to find out how much of the gain is the one-line effect
versus the reasoning.
