# Early safe-distance separation hosted A/B

## Question

On top of the validated group-tasking cohesion base, does an *early* safe-distance
retreat -- steering to the nearest remaining reachable task that increases
separation whenever one other player has lingered within 96px -- reduce the
subject's murder rate and residual sole-impostor exposure without harming task
completion?

## Motivation

Three prior reactive-flight experiments (self-preservation, isolation-pursuit,
witness-seeking) all failed: the sole-nearby player is ~60-72% crew, so
role-neutral flight separated the subject from crew and *into* isolation, and
equal move speed means an already-adjacent killer cannot be outrun. The dynamic
group-tasking A/B (2026-07-23) then validated proactive cohesion: keeping crewborg
near clusters raised two-plus-nearby time 26.4% -> 32.5% and cut sole-impostor
exposure 16.5% -> 9.7% with no task cost. This experiment attacks that residual
9.7% directly, but avoids every prior failure mode:

- **React earlier, at 96px** (larger than the 64px danger radius), so the margin
  exists *before* the follower is in kill range -- the only regime where
  equal-speed movement can keep a killer off, since it must spend its own
  acceleration ramp to close.
- **Retreat through a real task**, never a blind repulsion vector: the subject
  steers to the nearest remaining reachable task whose anchor is farther from the
  follower, so it never abandons the win condition or drives into a wall (the
  witness-seeking and blind-repulsion failures). A latched retreat target avoids
  station oscillation when the follower moves.
- **Only when truly one-on-one**: if a second player is within 96px the subject is
  already in a group and does not retreat (cohesion handles it).

If the lone follower is crew it will not chase, so the separation is free; if it
is an impostor, the subject has a head start.

## Design

Control and candidate are the same amd64 image (built from the safe-distance
rework on branch `crewborg-deduction-history`). The shared base enables the
retained solver, early public coordination, stick (tailing-self suppression only;
StickMode movement is retired), sound alibis, deduction history, group-tasking
cohesion, and full telemetry. Only the candidate adds
`CREWBORG_SELF_PRESERVATION=1`.

Run 100 forced-crewmate episodes per arm with the same pinned roster and forced
two-impostor slots as the group-tasking experiments.

Image `crewborg:safe-distance-v1`, ID
`sha256:3ec04710fe0e5ba6ab66479459e415bcf99abb516a65e244a69dacd93b20b5fd`.

| arm | policy | policy version ID | request |
| --- | --- | --- | --- |
| control | `crewborg-safe-distance-control:v1` | `23dc3e57-e5da-46fb-af90-07a59c9333d1` | `xreq_a383bbe6-f7ea-46aa-9304-c15c84364af1` |
| candidate | `crewborg-safe-distance:v1` | `63bc0cd8-cc80-4216-8b9e-37ac3ce52b0d` | `xreq_3cba1a52-05a4-4942-854c-4b8929cb4200` |

## Precommitted analysis

Filter subject and whole-roster operational failures separately using the result
timeout fields. The primary outcome is subject murder rate; report an effect size
and interval/test, not direction alone. Guardrails: first-victim rate, full task
completion, mean tasks, wins, score, and team kills. A survival gain does not
count if full-task completion falls by more than five percentage points.

Mechanism success requires, from objective 64px replay geometry: reduced
sole-nearby-impostor time versus control, without a fall in two-plus-nearby time
(the retreat must not undo cohesion). Telemetry must show the safe-distance stage
activating (the `self preservation (safe distance)` intent), or outcome
differences are treated as noise.

## Result

**Reject the candidate.** Both requests completed 100/100. The warehouse expanded
200/200 episodes (1 version-skewed replay excluded from deep events, retained for
outcomes); no subject connect/disconnect timeouts, so the subject-clean set is the
full 100 control / 99 candidate (one candidate game dropped for a roster timeout).

Even reframed as an early, productive, task-based retreat, safe distance
reproduced the reactive-flight failure and hurt every important outcome.

### Objective outcomes (subject-clean; control n=100, candidate n=99)

| metric | control | candidate | delta |
| --- | ---: | ---: | ---: |
| murdered | 46 (46.0%) | 52 (52.5%) | +6.5pp (Fisher `p=0.40`, 95% CI -7.3..+20.4) |
| first victim | 22 (22.0%) | 21 (21.2%) | -0.8pp (`p=1.0`) |
| crew win | 50 (50.0%) | 30 (30.3%) | **-19.7pp (`p=0.006`)** |
| all eight tasks | 89 (89.0%) | 59 (59.6%) | **-29.4pp (`p<0.001`)** |
| mean score | 57.01 | 34.03 | -22.98 |
| mean tasks | 7.67 | 6.65 | -1.02 |
| mean team kills | 2.95 | 3.23 | +0.28 |

The whole-roster-clean sensitivity slice (100 vs 98) agrees: wins 50.0% -> 30.6%
(`p=0.006`), all-eight 89.0% -> 60.2% (`p<0.001`), murders 46.0% -> 53.1%. The
murder rise is not individually significant, but full-task completion and wins
collapse decisively, and the precommitted guardrail (no more than a 5pp fall in
full-task completion) is failed by ~29pp.

### The mechanism did the opposite of its goal -- living Playing ticks within 64px

| bucket | control | candidate | delta |
| --- | ---: | ---: | ---: |
| nobody nearby | 53.43% | 51.22% | -2.21pp |
| exactly one nearby | 30.86% | 32.19% | +1.33pp |
| at least two nearby | 15.70% | 16.59% | +0.89pp |
| **sole nearby impostor** | 12.52% | 17.18% | **+4.66pp** |
| sole nearby crew | 18.35% | 15.01% | -3.34pp |

Sole-impostor exposure *rose* (the retreat was meant to cut it), while two-plus
time barely moved. The safe-distance stage activated heavily -- sampled candidate
games emitted 1,027 and 1,941 `self preservation (safe distance)` intents -- so
this is the flag's effect, not noise.

### Why it failed

The retreat steers to the nearest *reachable task that increases separation* from
the follower. In practice the separating task is usually a distant one, so a
triggered subject spends long stretches traveling across the map -- doing fewer
tasks (all-eight -29pp, mean tasks -1.0) and, worse, sitting alone *in transit*,
where an impostor catches it (sole-impostor +4.7pp, murders +6.5pp). The task
latch stopped oscillation between retreat targets but not the core problem: any
follower-triggered redirection pulls the subject off efficient nearest-task work
and into isolated travel. This is the same failure as blind repulsion and
witness-seeking -- a role-neutral proximity trigger fires mostly on crew, and
moving in response separates the subject from its safe crowd. The larger 96px
radius made it fire *earlier and more often*, amplifying the cost.

## Decision

Reject; do not promote or iterate thresholds on follower-triggered retreat. This
is now the fourth reactive-movement design (immediate repulsion, isolation
pursuit, witness-seeking, and this early task-based safe distance) to fail for the
same structural reason: distance-to-one-player is not a usable danger signal
(~60-72% crew), and any movement response to it separates the subject from crew.
Equal move speed also means the physics never favored flight. The productive-retreat
reframe removed the wall-driving and blind-vector problems but not the core one,
and the earlier/larger trigger made it worse.

The validated direction stands: **proactive group-tasking cohesion** (dynamic
revalidation, 2026-07-23) is the only crew-safety change whose objective geometry
moved the intended way, and it did so without a task cost. Future survival work
should stay proactive -- improving where the subject *chooses to be* before an
encounter -- rather than reacting to proximity after it. Retire
`CREWBORG_SELF_PRESERVATION`; keep group-tasking as the crew-safety base.
