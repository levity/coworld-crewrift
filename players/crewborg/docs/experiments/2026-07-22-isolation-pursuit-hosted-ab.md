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
impostors.

## Result

Reject the candidate. The generic 12-tick isolation trigger substantially and
significantly increased deaths, task churn, and losses.

The first analysis pass incorrectly used `score >= 0` as an operational filter.
That is not valid in Crewrift: ordinary gameplay penalties can produce a negative
score (one clean example scored -17 after completing two tasks). The tables below
use the game result's per-slot `connect_timeout` and `disconnect_timeout` fields.

| Subject-operational games | control | candidate | delta |
| --- | ---: | ---: | ---: |
| games | 174 | 153 | |
| murdered | 63 (36.2%) | 88 (57.5%) | **+21.3pp** |
| first victim | 21 (12.1%) | 31 (20.3%) | +8.2pp |
| crew win | 54 (31.0%) | 24 (15.7%) | **-15.3pp** |
| mean completed tasks | 5.40 | 4.77 | -0.63 |
| all eight tasks | 105 (60.3%) | 57 (37.3%) | **-23.1pp** |
| mean task attempts abandoned | 0.20 | 1.57 | +1.37 |
| mean ballots | 0.65 | 0.61 | -0.04 |

The murder delta has a 95% Wald interval of +10.7 to +31.9 percentage points
(risk ratio 1.59, Fisher exact p=0.00015). Full-task completion and crew wins
also regressed significantly (p=0.000039 and p=0.0012 respectively).

The whole-roster-operational sensitivity set is 127 control and 121 candidate
games. It gives the same answer: murders 49.6% -> 72.7% (+23.1pp,
p=0.00025), wins 42.5% -> 19.8%, mean tasks 7.33 -> 6.03, and all-eight-task
completion 81.9% -> 47.1%. Total impostor kills rose from 2.97 to 3.50 per game,
so the controller did not merely redirect kills from the subject to teammates.

## Full-telemetry mechanism

The original downloader used obsolete job-level routes and mislabeled 403/404
responses as unavailable telemetry. After switching to the current owned
`/v2/episode-requests/...` routes, all 121 fully operational candidate games had
their policy trace. Across them:

- 120/121 games entered isolation avoidance and 116 upgraded to pursuit;
- 717 escape sessions fired (5.93/game), including 476 pursuit upgrades;
- the upgrade delay was the configured 12 ticks at the median;
- **629/717 threats (87.7%) were crew and only 88 (12.3%) impostors**;
- only 23/88 eventual killers had ever been an escape threat before the murder,
  and only 21 were the most recent threat;
- 24 murders happened while an escape session was active;
- session duration was median 26 ticks, mean 141, and p90 386;
- 485 sessions ended when a witness arrived, 153 ended while the threat was
  still close without a witness (usually destination loss), 50 at a phase
  boundary, 24 at the subject's death, and only 5 because the threat separated.

Objective 64-pixel replay geometry confirms that movement went in the wrong
direction. Pooled Playing time one-on-one with an impostor rose 8.96% -> 12.29%
(per-game mean 12.22% -> 19.28%). Any-player one-on-one time rose 22.06% ->
24.43%. At 71/88 candidate murders only the killer was nearby, versus 43/63
control murders (80.7% vs 68.3%). Full-roster games contained 240 abandoned
candidate task attempts versus 35 control attempts.

The controller's state machine explains the churn. Reaching one witness clears
the current escape. That witness is then the sole nearby player, so after 12
ticks the policy labels the witness as the next threat and flees again. More
fundamentally, sustained proximity preferentially selected crewmates, while
missing most killers. It is not a usable broad danger signal in this field.

Candidate and control used the same image, but candidate had more subject
connect timeouts (47/200 vs 26/200). The feature does not execute before the
initial connection, so this likely reflects hosted imbalance rather than the
movement policy. Filtering subject timeouts and, separately, every roster
timeout leaves the gameplay conclusion unchanged.

## Decision

Do not promote or iterate thresholds on this generic trigger. Return to the
suspect-gated controller or disable self-preservation while mining pre-murder
trajectories for a real pursuit feature. Future movement must not abandon an
active task merely because a companion remains nearby, and a reached witness
must become a temporary safety anchor rather than the next inferred threat.
