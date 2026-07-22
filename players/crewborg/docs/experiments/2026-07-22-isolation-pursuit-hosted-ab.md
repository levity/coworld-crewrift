# Isolation-triggered pursuit escape hosted A/B

## Question

Does starting avoidance after 12 ticks of unwitnessed one-on-one proximity, then
latching escape when the companion continues pursuit, materially reduce the
subject's murder rate without materially reducing task completion?

## Design

Build the control and candidate from one committed amd64 image. Both arms enable
deduction history, stick mode, sound alibis, early public coordination, and full
telemetry. Leave group-aware task selection off in both arms. Enable
`CREWBORG_SELF_PRESERVATION=1` only for the candidate so this test isolates the
complete escape controller from ordinary stick/task movement.

Run 200 forced-crewmate episodes per arm with the same exact pinned roster. Rotate
the six crew policies through crew slots 0--5 while retaining the same two pinned
impostor policies at slots 6--7. Create both requests back-to-back.

## Precommitted analysis

Filter subject and whole-roster operational failures separately. The primary
outcome is subject murder rate. The co-primary mechanism checks are:

- fraction of candidate games entering soft avoidance and pursuit escape;
- time spent one-on-one with any player and with an impostor within 64 pixels;
- murders with only the killer nearby;
- time from soft activation and pursuit upgrade to a witness, murder, meeting,
  or game end; and
- first-victim rate, task starts, completed tasks, and abandoned task attempts.

Also report crew wins, score, ballots, and whether fewer subject murders merely
shift kills to teammates. Treat win rate as secondary. The mechanism passes if
the controller demonstrably activates, substantially reduces unsafe isolation,
and does not materially reduce eight-task completion. A death-rate claim needs
an effect size and interval/test, not direction alone.

## Requests and results

Both arms use commit `2f37fa8` and image
`sha256:e8a76b13d779e64a41dfe73a85c85b0c7ce898639de5c01cd8646085dda6db1f`.
The API permits at most 100 episodes per request, so each 200-game arm is split
into two same-window replicates:

| Arm | Policy | Requests |
| --- | --- | --- |
| control | `crewborg-isolation-pursuit-control:v1` (`e3d77eda-72fb-4c3e-9159-44b1f6c57abe`) | `xreq_9d25c2a3-72d9-42de-917c-67520d0f8891`, `xreq_7fe3dc8a-6899-496b-8b94-2460f8aa3682` |
| candidate | `crewborg-isolation-pursuit:v1` (`7263c864-742b-42a5-b84c-ac5e55176a12`) | `xreq_3ee34344-dabe-4efe-abee-4e44cbe59771`, `xreq_da3f3a14-e5d3-487f-af96-76f2c9faadff` |

Live-schema validation passed. Readback confirmed Crewrift 0.1.59, the exact
eight policy versions, six rotating crew seats, and the two intended pinned
impostors. Results pending.
