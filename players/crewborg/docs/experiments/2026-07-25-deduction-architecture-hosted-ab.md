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

## Result

*(pending — both arms running)*
