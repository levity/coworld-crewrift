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

Both arms drained 100/100, 0 failed, 0 connect/disconnect timeouts. The pre-registered
roster was verified in **all 200 episodes** (subject forced crew at seats 0–5,
`crewborg-aaln` forced imposter at 6–7; imposter seats were `(6,7)` in every episode, so
the seat shuffle the warehouse model warns about did not occur here). Subject-clean and
roster-clean filters therefore coincide. Warehouse: 200/200 ok, 1 `trace_warning`
episode, excluded from all event-derived numbers below.

**Sanity check — PASSED.** The flag took effect and was not silently dropped:

| arm | `deduction_history_decision` | `meeting_decision` | `accuse` mode entries | button calls |
|---|---:|---:|---:|---:|
| Control | 0 | 1974 | 495 | 197 |
| Candidate | 739 | 0 | **0** | **0** |

### Primary — candidate wins the pre-registered rule

| metric | control | candidate | delta [95 % CI] | Fisher p |
|---|---:|---:|---:|---:|
| **crew win rate** | 28 % | 49 % | **+21.0 pp** [+7.8, +34.2] | **0.0035** |

### Secondary (mechanism) — both predictions confirmed

Measured on **ballots that actually landed**, agreeing across three independent sources
(policy telemetry, `results.json` counters, and replay `vote_cast` events):

| metric | prediction | control | candidate | outcome |
|---|---|---:|---:|---|
| subject vote precision | up, ~70 % → ~95 %+ | **80.0 %** (200/250) | **100.0 %** (68/68) | confirmed, `p = 1.4e-06` |
| targeted-vote coverage | flat, ~12–15 % | 18.7 % | 14.5 % | confirmed (flat/slightly down) |
| imposter vs crew ejections | — | 2 imposter / **30 crew** | 0 / **0** | see below |

### How the win actually happened

Every point of the gain is the **48-task win**; ejection-driven wins are identical:

| win type | control | candidate | delta | Fisher p |
|---|---:|---:|---:|---:|
| win by 48 tasks | 25 % | 46 % | **+21.0 pp** | 0.0030 |
| win by ejection / maxTicks | 3 % | 3 % | 0.0 pp | 1.000 |

The link between the two is that **ghosts cannot do tasks** — `applyInput` sends any
non-alive player to `applyGhostMovement` and returns before the task block. So losing a
crewmate who still has tasks makes 48/48 unreachable. Confirmed:

> Of the 27 control episodes containing a crew ejection, **0 reached the 48-task win**;
> of the 73 without, 25 did (34 %). `p = 1.5e-04`.

Control ejected 30 crewmates and 2 imposters. The candidate ejected **nobody**. All 30
wrong ejections needed imposter votes — 21 of them were exactly *1 crew vote + 2 imposter
votes*, so a single misled crewmate was the swing that let the imposter pair remove a
crewmate. Control's 20 % vote error rate is what supplied that swing vote.

### Is it the architecture, or the confound?

**The design's "exactly one variable" claim is false.** `fold_belief` also runs
`belief.suspicion.clear()`, and `AccuseMode` — the only emergency-button trigger — fires
on `active_tail_suspect(belief)`, which reads exactly that. So the flag silently disables
button-calling: 495 accuse entries → 0, 197 button meetings → 0. Body reports are
untouched (132 → 122), which luckily leaves a **like-for-like comparison**:

| body-report meetings only | control | candidate | Fisher p |
|---|---:|---:|---:|
| meetings | 132 | 122 | — |
| crew ejected | 13 (**9.8 %**) | 0 (**0.0 %**) | **2.0e-04** |

Holding meeting type and count essentially constant, the deduction path still eliminates
crew ejections. **So the architecture does real work — but it is defensive, not
offensive.** It caught no more imposters (0 imposter ejections vs control's 2); what it
did was stop handing the imposters a swing vote.

Separately, the confound is itself a finding: control's **197 button meetings produced 17
crew ejections and 0 imposter ejections.** As currently triggered, the emergency button is
purely harmful — and Prime's `buttonResetsKillCooldowns = false` means a button meeting
also regroups everyone at spawn with imposter cooldowns still hot, where a body report
(`VoteCalledBody → true`) sets them back to the full 500 ticks.

### Mechanisms tested and rejected

- **"Meetings destroy task progress."** `applyVoteResult` does reset every player's
  position, `activeTask`, and `taskProgress`. But within-arm this predicts nothing: on
  ejection-free episodes, more meetings correlate with *more* tasks (control ρ = +0.32,
  `p = 0.006`; candidate ρ = +0.39, `p = 7e-05`). Rejected.
- **"Control wastes crew time walking to the button."** Task engagement is flat: 32.2 %
  of alive-Playing frames on-task in control vs 32.9 % in candidate. Rejected as a major
  term. What does differ is total crew alive-time (+6.5 % in candidate) — survival, not
  diligence.

### Guardrails — all clean

| guardrail | control | candidate | verdict |
|---|---:|---:|---|
| all-6-seats task completion | 25 % | 46 % | improved |
| crew tasks / game (of 48) | 40.51 | 44.31 | improved (`p = 2e-05`) |
| imposter kills / game | 3.37 | 3.43 | unchanged (`p = 0.41`) |
| connect/disconnect timeouts | 0 | 0 | clean |

### Two observations for the improvement loop

**Evidence classes.** `deduction_audit.py` over the candidate arm: 244 eject decisions,
**100 % structural witness pins, 0 from the joint solve.** In the earlier v2 baseline the
split was 91 / 9. With deduction-history alone, the joint enumeration and all 22
`InferenceConfig` constants contributed **zero** ejects — every one was
`personally witnessed impostor action`. This tightens the companion note's conclusion.

**Ghost decisions are free labelled data.** The candidate emits 244 targeted decisions but
only 68–71 land. Splitting by whether the deciding seat was alive (self-colour recovered
as the one colour absent from the decision's `marginals`, joined to the episode death map):
alive 71 targeted / 71 at imposter; **ghost 173 targeted / 173 at imposter — all
discarded.** Dead crewmates keep solving with perfect vision and are right every time.
That is ~173 extra ground-truth-labelled decisions per 100 games at zero hosted cost,
usable to fit and validate the inference layer. (Control's ghosts silent-skip, which is
why its decided and landed counts agree at 250.)

### Verdict

- **Promote the candidate.** It wins the primary (`p = 0.0035`), every guardrail improves
  or holds, and its decision layer is strictly better (80 % → 100 % precision, 30 → 0 crew
  ejections).
- **Record the mechanism honestly.** The architecture's value here is *defensive* — it
  stops the crew supplying the swing vote — not that it catches more imposters. The
  eject-driven win count did not move at all.
- **The architecture question is only partly answered.** The flag changed two things. The
  body-meeting comparison isolates a real architecture effect, but the button suppression
  rode along and is worth its own change.

### Recommended follow-ups

1. **Suppress `AccuseMode` in the control line** (one flag, no architecture change) —
   197 button meetings bought 0 imposter ejections and 17 crew ejections. Cheapest
   expected win on the board, and it cleanly separates the two variables.
2. **Re-enable meeting-calling on the deduction posterior.** The candidate now has a
   100 %-precision decision layer and almost no meetings to use it in (1.22/game, 68
   landed targeted votes per 100 games). Gate the button on a *structural pin* rather than
   the deleted suspicion model.
3. **Harvest ghost decisions** as an offline evaluation corpus before buying more games.
