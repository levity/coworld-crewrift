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

Pending.
