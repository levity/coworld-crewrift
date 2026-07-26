# Post-task loiter-with-group hosted A/B

> ⚠️ **Wrong target — results not valid for Crewrift Prime.** This experiment ran
> Experience Requests against plain `crewrift:0.1.59` (`cow_52d06063`), NOT the Crewrift
> **Prime** coworld the crewborg champion actually competes on (`crewrift_prime`, live
> `cow_0ba5e866`, resolve via `coworld leagues league_a12f5172 --json`). Prime is the same
> sim engine but a forked coworld with different scenario params + opponents, so treat the
> geometry/murder numbers below as suspect until re-measured on Prime.


## Question

Does a finished crewmate holding with the pack -- instead of returning to spawn
alone -- reduce murders and isolation, given that ~half of subject deaths happen
after the subject has finished its own tasks?

## Motivation (from diagnosis, not a guess)

`crewrift-analysis/diagnose.py` on the validated group-tasking base
(`crewborg-dynamic-group`, 100 games) found:

- **48% of subject murders happen AFTER the subject finished all 8 tasks** --
  finished crew wandering home alone. Group-tasking cohesion only biases task
  selection *while tasks remain*; once done, `NormalMode` returns to spawn alone,
  so this window is uncovered.
- **76% of murders are isolated kills** (only the killer within 64px, no witness)
  -- being with a group is the confirmed lever (an impostor rarely kills with a
  witness present).
- Sole-impostor exposure peaks mid-game, when crew finish tasks and start
  wandering.

Post-task loiter targets exactly that uncovered ~half of deaths.

## Design

Control and candidate are the same amd64 image
(`crewborg:post-task-loiter-v1`, ID
`sha256:07d4bdebb7e15791e6d6a7e9a3cec991dcdc0982f4d29caa58f010cc270ab01e`),
built from the finished-crew-cohesion commit on branch
`crewborg-deduction-history`. Both share the validated cohesion base (retained
solver, early coordination, stick/tailing-self suppression, sound alibis,
deduction history, group-tasking, full telemetry). Only the candidate adds
`CREWBORG_POST_TASK_LOITER=1`: once a living crewmate has no task left, it holds
with / drifts toward the densest cluster of recently-seen live crew instead of
returning to spawn.

Run 100 forced-crewmate episodes per arm with the same pinned roster and forced
two-impostor slots as the group-tasking experiments.

| arm | policy | policy version ID | request |
| --- | --- | --- | --- |
| control | `crewborg-post-task-loiter-control:v1` | `7d143b09-bd37-4355-9942-d516441c2ee1` | `xreq_14e61b74-68c4-4461-9e82-9f54db102f7c` |
| candidate | `crewborg-post-task-loiter:v1` | `ef7e63ff-9680-48a7-9c69-f20395f74957` | `xreq_7e1e2122-1b3f-4527-a204-48aa491b15d8` |

## Precommitted analysis

Filter subject and whole-roster operational failures separately using the result
timeout fields. Primary outcome: subject murder rate, with an effect size and
interval/test. Guardrails: first-victim rate, full task completion, mean tasks,
wins, score, team kills. A survival gain does not count if full-task completion
falls by more than five percentage points.

Mechanism success requires, from objective 64px replay geometry: less
sole-impostor exposure and more two-plus-nearby time, **concentrated in the
post-task window** (the diagnostic split above should move for the candidate).
The loiter intent (`post-task loiter`) must activate, or outcome differences are
treated as noise. Because loiter only fires once tasks are done, first-victim
rate should be roughly unchanged; the effect, if any, is on later deaths.

Analysis is run with `crewrift-analysis/ab_analysis.py` (outcomes + geometry) and
`diagnose.py` (post-task split), warehouse built with the adaptive `build.py`.

## Result

Pending.
