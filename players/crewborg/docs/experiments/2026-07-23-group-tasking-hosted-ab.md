# Proactive group-supported tasking hosted A/B

## Question

Can choosing a slightly farther assigned task near a recently observed cluster
increase group time and reduce murders without sacrificing task completion?

## Design

Control and candidate use the exact same pinned-SDK amd64 image built from
commit `e29bcb0` (image `sha256:8840dda7682a885054a27660e610b9eb021ad3123c901e1ec6833f7b6b9b5603`).
Both enable deduction history, stick, sound alibis, early chat, and full
telemetry. Self-preservation is off in both arms. Only the candidate enables
`CREWBORG_GROUP_TASKING=1`; its existing maximum detour remains 160 pixels.

Run 100 forced-crewmate episodes per arm with the same pinned roster and forced
two-impostor slots as the witness-seeking experiment.

| Arm | Policy | Request |
| --- | --- | --- |
| control | `crewborg-group-tasking-control:v1` (`4613d91e-24a1-49ab-a203-a340e76fc524`) | `xreq_2ec87a6e-81fd-4b21-ba8f-c511413acadd` |
| candidate | `crewborg-group-tasking:v1` (`8b3ba7d1-48c4-4b72-a5d4-b0594f3ee829`) | `xreq_df2dcefb-f6aa-414b-8b9d-0b4ed127af7e` |

## Precommitted analysis

Filter subject and whole-roster operational failures separately using result
timeout fields. The primary outcome is subject murder rate. Guardrails are
first-victim rate, full task completion, mean tasks, abandoned attempts, wins,
score, and team kills.

Mechanism success requires telemetry-confirmed group-aware task selections,
more living play time with at least two nearby players, and less time alone or
with a sole impostor. A survival improvement does not count if full-task
completion falls by more than five percentage points. If the mechanism barely
activates, outcome differences are not attributed to the flag.

The exact candidate image passed local Gate 1 in all eight slots. The warehouse
completed all 200 episodes, 10,278,093 events, and zero extraction warnings.

## Result

The flag is safe but ineffective. Each arm had one subject operational failure;
the subject-clean comparison is:

| metric | control (n=99) | candidate (n=99) | delta |
| --- | ---: | ---: | ---: |
| murdered | 52 (52.5%) | 53 (53.5%) | +1.0pp |
| first victim | 22 (22.2%) | 25 (25.3%) | +3.0pp |
| crew win | 42 (42.4%) | 44 (44.4%) | +2.0pp |
| mean score | 48.90 | 50.36 | +1.46 |
| mean completed tasks | 7.39 | 7.41 | +0.02 |
| all eight tasks | 86 (86.9%) | 85 (85.9%) | -1.0pp |
| abandoned task attempts (all games) | 28 | 27 | -1 |
| team kills | 302 | 300 | -2 |

Murder (`p=1.0`), first-victim (`p=0.739`), win (`p=0.886`), and full-task
(`p=1.0`) differences are noise. The whole-roster-operational sensitivity slice
agrees: murders are 52/97 versus 53/98.

The mechanism moved in the wrong direction:

| living Playing ticks within 64px | control | candidate |
| --- | ---: | ---: |
| nobody nearby | 42.48% | 52.51% |
| exactly one nearby | 27.55% | 22.62% |
| at least two nearby | 29.97% | 24.87% |
| sole nearby impostor | 14.63% | 12.00% |
| sole nearby crew | 12.92% | 10.62% |

Telemetry confirms the flag was active in 94 games: 142 group-aware task
sessions covered 46,718 decision ticks. A group of at least two true others was
nearby at 117/142 session starts (82.4%), but on only 9,988/46,718 active ticks
(21.4%). Every active tick retained `complete_task` for the initially selected
station. `NormalMode` chooses a supported task only when `_target` is empty,
then caches it until completion; it never asks whether support moved away.

## Decision

Do not promote v1 or attribute its neutral outcomes to successful grouping. The
straightforward next iteration is dynamic support revalidation: while traveling
and before task progress starts, periodically recompute the supported task and
switch to a newly supported station or the ordinary nearest task when support
expires. Never retarget after task progress begins. This tests the intended
mechanism without waiting idle or sacrificing an in-progress task.

Implemented locally after this result. `NormalMode` now revalidates on every
travel tick only while either the current or proposed target is group-backed;
ordinary nearest-task targeting retains its previous stability. The first
observed task-progress value latches the target through later perception
flicker. The full suite passes (603 passed, 13 skipped), with touched-file Ruff
and diff checks clean.
