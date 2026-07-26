# Group-tasking cohesion on Crewrift PRIME hosted A/B

The **first correctly-targeted** crewborg experiment: it runs against Crewrift
Prime (`crewrift_prime:0.4.69`, `cow_0ba5e866`, league `league_a12f5172`) — the
game the champion actually competes on — after discovering the prior 2026-07-23
batch mis-targeted plain `crewrift:0.1.59`.

## Question

Does group-tasking cohesion (`CREWBORG_GROUP_TASKING=1`) improve the subject's
crew outcomes on Prime versus the same build without it? (Re-validating the one
direction that looked good on the wrong game, now on the right one.)

## Design

Same image (`crewborg:post-task-loiter-v1`, HEAD `a239e27`), two versions of the
standardized policy line `crewborg-lw`, differing only by the group-tasking flag.
Shared base: retained solver, early coordination, stick/tailing-self suppression,
sound alibis, deduction history, full telemetry. Subject forced crew; the other
seven seats are the **league's official filler policies**
(`4e65356f…`, `48df5a11…`) with the two impostor seats forced. 100 episodes/arm.

| arm | policy | group-tasking | request |
| --- | --- | --- | --- |
| control | `crewborg-lw:v2` | off | `xreq_f3436dee-6b09-4bb9-a5bb-86f8e98c1308` |
| candidate | `crewborg-lw:v3` | on | `xreq_e352cc35-7b8f-4c6b-bd3b-a8474bb0acc4` |

## Precommitted analysis

Primary competitive outcome (from `results.json`, no expander needed): subject
crew **win rate** and **mean score**, with an effect size + test; guardrail: full
task completion. Secondary (needs the Prime warehouse): murder rate + 64px
geometry (does group-tasking raise 2+-nearby time / cut sole-impostor exposure on
Prime as it appeared to on plain crewrift?). Filter subject/roster operational
failures via the result timeout fields.

Prime replay expander: built from coworld-crewrift `c83d9be` (master), verified
`trace_complete` on a real 0.4.69 replay. Analysis via `crewrift-analysis`
(`ab.sh` + `diagnose.py`), warehouse via the adaptive `build.py`.

Note: Prime scoring differs from plain crewrift (win ≠ +100; `killCooldownTicks`
500 vs 800); interpret outcomes on Prime's own scale, and do not compare absolute
numbers to the mis-targeted plain-crewrift experiments.

## Result

Both arms 100/100 completed, 0 failed, 0 trace-skew. Arms labeled by source xreq
(both share the `crewborg-lw` name, differing by version).

**Group-tasking cohesion shows no benefit on Prime, and did not reproduce the
mis-targeted plain-crewrift signature.** Subject-clean (n=100/arm; roster-clean is
identical — no operational failures):

| metric | control (GT off) | candidate (GT on) | delta |
| --- | ---: | ---: | ---: |
| murdered | 54% | 55% | +1.0pp (p=1.0) |
| first victim | 18% | 14% | -4.0pp (p=0.56) |
| crew win | 14% | 14% | 0.0pp (p=1.0) |
| all eight tasks | 35% | 38% | +3.0pp (p=0.77) |
| mean tasks | 6.14 | 6.51 | +0.37 |
| mean team kills | 3.80 | 3.70 | -0.10 |

64px geometry moved slightly the WRONG way: 2+-nearby 26.4% -> 25.7%,
sole-impostor 11.1% -> 12.0% — the inverse of the (wrong-game) plain-crewrift
result (there: 2+-nearby +6pp, sole-impostor -7pp). The one "validated" direction
does not hold on the correct game.

### Two load-bearing caveats

1. **Confounded by a report-freeze bug** in the base config (both arms): crewborg
   can get stuck pressing report at a body it mislocalizes by ~7px (stranded ~1px
   outside the 20px report range), freezing until killed — see the
   `report_body` robustness fix. This adds deaths/noise to both arms.
2. **Crew win rate is only 14% on Prime** (vs the plain-crewrift experiments'
   ~47%). Prime is a harder, different game (killCooldown 500, scenario config),
   and crewborg is currently a weak crew there. Fixing base robustness and
   re-establishing a working Prime baseline is the priority before mechanism A/Bs.

Do not read anything into group-tasking on Prime from this; the base policy needs
to work first. This experiment's real value: it confirmed the mis-targeted
learnings do not transfer, and (via the replay) surfaced the report-freeze bug.
