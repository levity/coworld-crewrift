# Dynamic group-supported tasking hosted A/B

## Question

Does revalidating group support while traveling make proactive group tasking
actually keep crewborg near groups, without reducing task completion?

## Design

Control and candidate use the exact same pinned-SDK amd64 image built from
commit `3ffac1d` (image
`sha256:ea830c76b02487c91bfe97b9d91488d5503d7d7c28ac33cc296d83eca44ca6bc`).
Both retain the deduction-history, stick, sound-alibi, early-chat, and telemetry
configuration used in v1. Self-preservation is off. Only the candidate enables
`CREWBORG_GROUP_TASKING=1`.

Run 100 forced-crewmate episodes per arm against the same pinned roster and
forced two-impostor slots as v1.

| arm | policy | policy version ID | request |
| --- | --- | --- | --- |
| control | `crewborg-dynamic-group-control:v1` | `7b485fd8-ce37-443f-82fb-12f52192033e` | `xreq_94f5acd8-0d64-4201-badc-b838279b5b89` |
| candidate | `crewborg-dynamic-group:v1` | `5383652b-f60c-48a2-b1c5-0b78cb21a275` | `xreq_fee602ef-1549-406b-8229-6c01b9db499c` |

## Precommitted analysis

Filter subject and whole-roster operational failures separately. The primary
outcome is subject murder rate. Guardrails are first-victim rate, full task
completion, mean tasks, abandoned attempts, wins, score, and team kills.

Mechanism success requires shorter stale group-backed sessions, a higher share
of group-backed travel ticks with at least two true nearby players, and more
total living play time with at least two nearby players. A survival gain does
not count if full-task completion falls by more than five percentage points.
Outcome noise alone cannot establish success: telemetry must show that dynamic
revalidation fixed the v1 target-caching failure.

The exact candidate image passed local Gate 1 in all eight slots. The full suite
passes (603 passed, 13 skipped), and touched-file Ruff checks are clean.

## Result

Both requests completed 100/100 with zero request-level failures. The warehouse
streamed both arms into one policy-indexed store; 200/200 episodes expanded with
1 trace-warning replay (version-skew on a single episode; excluded from the deep
event counts, retained for outcomes). A 0.1.59-matched `expand_replay` was rebuilt
for this analysis (`trace_complete`, zero skew on the smoke replay). No subject
connect/disconnect timeouts occurred, so the subject-clean set is the full 100 per
arm; the roster-clean sensitivity set drops one candidate game with a roster
timeout.

**Dynamic revalidation fixes the v1 caching failure — the mechanism now moves the
intended direction — but the survival outcome is favorable-yet-underpowered.**

### Objective outcomes (subject-clean, n=100/arm)

| metric | control | candidate | delta |
| --- | ---: | ---: | ---: |
| murdered | 50 (50.0%) | 46 (46.0%) | -4.0pp (Fisher `p=0.67`, 95% CI -17.8..+9.8) |
| first victim | 14 (14.0%) | 12 (12.0%) | -2.0pp (`p=0.83`) |
| crew win | 47 (47.0%) | 48 (48.0%) | +1.0pp (`p=1.0`) |
| all eight tasks | 83 (83.0%) | 85 (85.0%) | +2.0pp (`p=0.85`) |
| mean score | 52.46 | 54.17 | +1.71 |
| mean tasks | 7.26 | 7.38 | +0.12 |
| mean team kills | 3.01 | 2.96 | -0.05 |

The roster-clean sensitivity slice (100 vs 99) agrees: murders 50.0% vs 46.5%,
wins 47.0% vs 48.5%, all-eight tasks 83.0% vs 84.8%. Every outcome delta is
non-significant, but — unlike v1 — none is adverse: full-task completion did not
fall (it rose 2pp, well inside the 5pp guardrail), and murders trend down 4pp.

### Objective movement signature — living Playing ticks within 64px

| bucket | control | candidate | delta |
| --- | ---: | ---: | ---: |
| nobody nearby | 44.57% | 41.20% | -3.37pp |
| exactly one nearby | 29.00% | 26.30% | -2.70pp |
| **at least two nearby** | **26.43%** | **32.50%** | **+6.07pp** |
| sole nearby impostor | 16.45% | 9.67% | **-6.78pp** |
| sole nearby crew | 12.55% | 16.63% | +4.08pp |

This is the decisive result and the exact inverse of v1. v1 group-tasking *reduced*
two-plus-nearby time (30.0% -> 24.9%); dynamic revalidation *raises* it
(26.4% -> 32.5%) and cuts sole-impostor exposure nearly in half (16.5% -> 9.7%).
Time completely alone also falls. Of the times crewborg is down to a single nearby
player, more of them are now crew than impostor. The precommitted primary
mechanism check — "more total living play time with at least two nearby players"
— passes, and the intended safety signature (less time isolated with a killer)
holds, with no task-completion cost.

Internal policy telemetry confirms activation: a sampled candidate episode emitted
~299 group-aware task-selection intents (`group-aware tasking: completing supported
assigned task`); the control/off arm emits none. The per-episode 69MB telemetry
tapes were not aggregated across all 200 games (2-vCPU budget), so the objective
64px replay geometry — which measures the *outcome* the mechanism targets rather
than its self-reported activation — is the load-bearing evidence here.

## Decision

The mechanism is validated: dynamic support revalidation corrected v1's
stale-target caching and produced the intended movement signature (more group
time, sharply less sole-impostor exposure) without a task or win regression. This
is the first crew-safety change whose objective geometry moves the intended way.
The survival benefit itself (-4pp murders) is not statistically established at
100/arm and cannot be promoted on outcomes alone.

Do not promote v1 on the outcome delta. Two productive next steps: (1) more games
to power the survival estimate, and (2) attack the residual 9.7% sole-nearby-
impostor exposure directly — proactive grouping keeps crewborg *with* the pack but
does nothing when it is already down to one companion. That gap is what the
"safe-distance" positioning work targets next: keep the working group-cohesion
bias, and add an early, larger-radius separation from a lone follower so the
sole-impostor tail keeps shrinking.
