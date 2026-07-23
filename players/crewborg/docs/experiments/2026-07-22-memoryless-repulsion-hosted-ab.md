# Memoryless repulsion hosted A/B

## Question

Does immediate, destination-free repulsion from the sole current player within
64 pixels reduce crewborg's murder rate without an unacceptable loss of task
completion or crew wins?

## Design

Control and candidate are uploaded from commit `eadfa07` and the identical amd64
image. Both enable the v2 deduction-history solver, stick, sound alibis, early
chat, and full telemetry; group tasking remains off. Only the candidate enables
`CREWBORG_SELF_PRESERVATION=1`.

Run 200 forced-crewmate episodes per arm in two 100-game replicates. Rotate the
six crew policies across crew slots 0--5 and pin the same two impostor policies
to slots 6--7. Create all four requests in the same window.

## Precommitted analysis

Filter subject and whole-roster operational failures separately using result
connect/disconnect timeout fields. The primary outcome is subject murder rate.
Report a confidence interval and Fisher test for its delta. Guardrails are full
task completion, mean tasks, crew wins, first-victim rate, abandoned attempts,
score, and total team deaths.

Use replay geometry and candidate telemetry to verify the mechanism:

- activation/session counts and time in repulsion or pursuit;
- actual movement while the sole nearby player is an eventual killer;
- murders with the killer as sole player inside 64 pixels;
- the subject's action immediately before each murder;
- whether any repulsion intent is stopped at a reached goal while one-on-one;
- task interruptions and whether danger is displaced to teammates; and
- whether duration or closing behavior separates impostors from crewmates well
  enough to justify a later pursuit-evidence experiment.

## Requests and results

Pending.
