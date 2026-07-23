# Delayed witness-seeking hosted A/B

## Question

Does waiting for 12 continuous one-on-one ticks and then moving toward a
currently visible third player avoid the survival and tasking regressions caused
by immediate blind repulsion?

## Design

Control and candidate use the exact same pinned-SDK amd64 image from behavior
commit `3246b44`. Both enable deduction history, stick, sound alibis, early chat,
and full telemetry; group tasking is off. Only the candidate enables
`CREWBORG_SELF_PRESERVATION=1`.

Run 100 forced-crewmate episodes per arm with the same fully pinned roster and
roles as the preceding repulsion experiments. Requests were created eight
seconds apart in the same window.

| Arm | Policy | Request |
| --- | --- | --- |
| control | `crewborg-witness-seeking-control:v1` (`8fbe70cc-8b89-449c-ad5a-314a4233ee76`) | `xreq_5d4227ae-1b2f-469f-b18a-178973d58277` |
| candidate | `crewborg-witness-seeking:v1` (`e9a65f8d-f87d-48c9-84ea-e6702795abee`) | `xreq_e50efe44-0d6e-476a-ac49-3ffe64469a1e` |

## Precommitted analysis

Filter subject and whole-roster operational failures separately using result
timeout fields. The primary outcome is subject murder rate. Guardrails are full
task completion, mean tasks, abandoned attempts, wins, score, and team kills.

Mechanism success requires:

- materially fewer movement activations and task interruptions than immediate
  repulsion;
- telemetry confirming the 12-tick trigger and witness-directed destination;
- zero self-target events after union self exclusion;
- increased time with at least two nearby players; and
- reduced, not increased, time with a sole nearby impostor.

The warehouse streams during execution with two replay workers. Results are
pending.
