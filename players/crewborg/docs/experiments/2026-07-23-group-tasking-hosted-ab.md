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
| control | `crewborg-group-tasking-control:v1` (`4613d91e-24a1-49ab-a203-a340e76fc524`) | pending |
| candidate | `crewborg-group-tasking:v1` (`8b3ba7d1-48c4-4b72-a5d4-b0594f3ee829`) | pending |

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

The exact candidate image passed local Gate 1 in all eight slots. Results are
pending.
