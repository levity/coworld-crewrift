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

The API permits at most 100 episodes per request, so each 200-game arm uses two
same-window replicates:

| Arm | Policy | Requests |
| --- | --- | --- |
| control | `crewborg-memoryless-repulsion-control:v1` (`2ca653b1-470d-4f8a-9014-750bbf4c382c`) | `xreq_6edc735c-b9a5-42bd-8b24-1e1822ec966d`, `xreq_9d411b60-f099-477b-923b-d7925b0388e2` |
| candidate | `crewborg-memoryless-repulsion:v1` (`d35b9ece-fc67-4e7a-b8fa-adeb2647d467`) | `xreq_3aa1cbe4-72c4-4ba6-ae47-d0d486af0229`, `xreq_13edb340-6622-4f71-888c-79d96c275ff2` |

Live-schema validation passed. Readback identified Crewrift 0.1.59 and 100
episodes in every request.

## Result

Reject this build. It significantly increased murders and sharply reduced task
completion and wins, but a self-identity bug contaminated nearly every candidate
game, so this run does not isolate repulsion from real other players.

| Subject-operational games | control | candidate | delta |
| --- | ---: | ---: | ---: |
| games | 181 | 187 | |
| murdered | 87 (48.1%) | 112 (59.9%) | **+11.8pp** |
| first victim | 29 (16.0%) | 40 (21.4%) | +5.4pp |
| crew win | 83 (45.9%) | 43 (23.0%) | **-22.9pp** |
| mean completed tasks | 7.04 | 5.34 | -1.70 |
| all eight tasks | 142 (78.5%) | 65 (34.8%) | **-43.7pp** |
| abandoned task attempts | 48 | 171 | +123 |
| mean score | 51.68 | 26.46 | -25.22 |

The murder delta has a 95% Wald interval of +1.7 to +21.9 percentage
points (Fisher exact `p=0.028`). Crew wins (`p=0.0000038`) and full-task
completion (`p=1.3e-17`) also regressed. The whole-roster-operational subset
agrees: murders 87/174 (50.0%) -> 112/183 (61.2%), wins 47.7% -> 23.5%, and
full tasks 81.6% -> 35.5%. Total impostor kills rose from 517 (2.86 per
subject-clean game) to 611 (3.27), so deaths were not merely displaced.

### Self-identity contamination

Full candidate telemetry was available for 195/200 games. Of 5,549 traced
repulsion or pursuit stage starts, 2,123 (38.3%) targeted crewborg's own true
color, 2,031 targeted another crewmate, and 1,395 targeted an impostor. Self
targeting occurred at every rotated seat (30--60% of stage starts by seat) and
in 182/187 subject-operational candidate games.

The cause is concrete. `update_belief` assumes the self sprite decodes within
4 pixels of `self_world`, but hosted telemetry shows the true self record at the
stable offset `(-2, -6)`, distance 6.32 pixels. The match therefore commonly
fails and `belief.self_color` remains missing or wrong. `SelfPreservationMode`
then uses only `record.color != belief.self_color` to exclude self. It interprets
the camera-locked self sprite as a pursuer that can never be escaped.

Immediately before the 112 candidate murders, the final intent was repulsion in
46 games, `complete_task` in 63, idle in two, and report in one. In 41/63 task
cases, telemetry showed the visible killer was the sole true non-self player
inside 64 pixels. A misidentified self sprite made the controller count two
players and decline to preempt the task. This is an implementation failure, not
evidence that the specified gate correctly chose to keep tasking.

Dynamic goals substantially reduced but did not eliminate stopped flight: 7/46
pre-murder repulsion goals were within 10 pixels, and six emitted no directional
input. The previous build had 15 stale-goal cases among 71 sole-killer deaths.

### Positioning effect

On whole-roster-operational replay ticks, candidate positioning moved away from
safety rather than toward it:

| Playing-time geometry | control | candidate |
| --- | ---: | ---: |
| no other player within 64 | 46.3% | 55.7% |
| exactly one other within 64 | 29.4% | 32.7% |
| at least two others within 64 | 24.3% | 11.7% |
| sole nearby player is impostor | 13.6% | 22.0% |
| sole nearby player is crew | 15.8% | 10.7% |

This is consistent with flight from the self sprite and from 2,031 real crew
targets breaking groups. It warns that pure separation is not equivalent to
reaching safety, but the self-target contamination is too pervasive to estimate
the clean rule's effect from a post-hoc subset: only five operational candidate
games had telemetry and no self-target event.

The warehouse contains 400 episodes and 20.4 million events. Extraction had
zero hard failures; one candidate replay had a trace warning and is excluded
from geometry only. Results use timeout fields, not score sign.

## Decision

Do not promote this version. Correct self identity first and add a hard
geometric self-record exclusion to this safety-critical consumer. Re-run the
same A/B before changing the 64-pixel rule. The corrected experiment should
also distinguish mere separation from reaching a third player; this run shows
that increasing fully-alone time is not a safety success.

## Corrected v2 rerun (2026-07-23)

Commit `61b1327` fixes self identity at the hosted `(-2,-6)` anchor and adds an
independent geometric self-record exclusion. The full suite passes (601 passed,
13 skipped), and the exact activated image passed local Gate 1 in all eight
slots. Control and candidate v2 were uploaded from the same committed image;
only the candidate enables self-preservation.

The rerun repeats the pinned roster and 200 games per arm in four 100-game
requests:

| Arm | Policy | Requests |
| --- | --- | --- |
| control | `crewborg-memoryless-repulsion-control:v2` (`98d4b40f-97aa-42f5-99cc-14b9acc18dff`) | `xreq_a47eec45-f5ac-4aa3-815d-8ebf25f7f2aa`, `xreq_de16d4e1-a502-434e-8330-77f6308fcbed` |
| candidate | `crewborg-memoryless-repulsion:v2` (`caf92954-bdc4-464f-bec7-a14443c5119f`) | `xreq_bac575e6-88bc-4714-8342-a6bd4336e9fa`, `xreq_8d38befc-5a31-4b10-bdbc-473f7d7bd912` |

The first correctness gate remains zero repulsion or pursuit events targeting
the subject's true self color. Outcome and mechanism results are pending.
