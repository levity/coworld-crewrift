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

### What happened immediately before candidate murders

The failed controller is narrower than an immediate memoryless repulsion rule.
On the tick before the 88 candidate murders, the killer was the sole other live
player within 64 pixels in 71 cases. In those 71 cases crewborg was:

- actually moving under self-preservation in only 8;
- emitting self-preservation but stopped within 10 pixels of its cached
  destination in 15;
- completing a task in 46;
- reporting in 1 and idle in 1.

The stopped cases expose a concrete destination bug: hard escape retains the
last destination when no fresh witness destination exists. After reaching that
point, it can keep returning a zero-length navigation goal while the threat
remains close. Conversely, an escape does not start at all when no player was
seen recently enough to supply a destination. Across all deaths the killer was
continuously rendered-visible for at least 12 ticks in 84/88 cases, so most of
the 46 tasking cases were not surprise attacks; the missing destination blocked
response. Only 40/88 killers spent fewer than 12 consecutive ticks inside the
actual 20-pixel kill range, including 37 that entered kill range for at most
three ticks before striking.

An immediate rule that simply moves away while exactly one player is within 64
pixels would therefore have recognized 71/88 lethal situations at the last
pre-kill tick, compared with 17/88 where the implemented named-threat escape was
aimed at the killer and only 8/88 where it was still producing movement. This
counterfactual has materially better coverage, but replay cannot establish
survival after changing the path; it needs its own isolated A/B.

Distance alone remains a weak role classifier. In fully operational control
games, the sole nearby player was an impostor on only 38.8% of sole-player ticks
at the true 20-pixel kill range, 43.1% around 28--56 pixels, and 40.6% at 64
pixels. For continuous 12-tick same-player bouts, the impostor share was 37--39%
by bout and 40--44% weighted by duration. Crewmates commonly remain within
literal kill range because they share tasks, corridors, and explicit group
policies. Derived chase intervals were more discriminating (75% impostor in the
control arm) but sparse: they covered only 22/88 candidate killers at death.

Double kills are real but not the main explanation. Fully operational candidate
games had simultaneous two-kill ticks in 29/121 games (24.0%), versus 19/127
(15.0%) control games. The subject was one victim of a double kill in 10/88
candidate murders and 10/63 control murders. None of the candidate subject's
nearby 64-pixel witnesses was the other same-tick victim; the sampled double
kill involved two separate pairs elsewhere on the map.

Candidate and control used the same image, but candidate had more subject
connect timeouts (47/200 vs 26/200). The feature does not execute before the
initial connection, so this likely reflects hosted imbalance rather than the
movement policy. Filtering subject timeouts and, separately, every roster
timeout leaves the gameplay conclusion unchanged.

## Decision

Do not promote or iterate thresholds on this named-threat/destination
controller. Return to the suspect-gated controller, or separately test a pure
memoryless repulsion rule that needs no destination, never retains a stale
target, and ends immediately at zero or two-plus nearby players. Treat that as
risk control rather than impostor evidence: most activations will still be
against crew and can interrupt tasks. In parallel, mine closing/chase features
for a higher-precision escape accelerator. A reached witness must become a
temporary safety anchor rather than the next inferred threat.
