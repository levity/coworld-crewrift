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

The warehouse streamed during execution with two replay workers and completed
all 200 episodes, 10,876,510 events, and zero extraction warnings.

## Result

Reject the candidate. All 100 subjects in each arm were operational, so no
failure filter changes the comparison.

| metric | control | candidate | delta |
| --- | ---: | ---: | ---: |
| murdered | 48 (48%) | 60 (60%) | +12pp |
| first victim | 18 (18%) | 23 (23%) | +5pp |
| crew win | 47 (47%) | 34 (34%) | -13pp |
| mean score | 52.03 | 39.45 | -12.58 |
| mean completed tasks | 7.08 | 6.70 | -0.38 |
| all eight tasks | 79 (79%) | 61 (61%) | **-18pp** |
| abandoned task attempts | 26 | 449 | +423 |
| team kills | 297 | 325 | +28 |

The murder delta is unresolved at this sample size (Fisher `p=0.118`, Wald 95%
interval -1.5 to +25.5 points), but every important outcome moved adversely.
Full-task completion is significantly worse (`p=0.0084`); wins are also adverse
(`p=0.084`).

The precommitted mechanism gates fail decisively. The candidate started 1,591
escape sessions in 99 games. Threats were 1,146 crew (72.0%) and 445 impostors
(28.0%), exactly the roster base rate rather than a discriminative pursuit
signal. Of 78,165 escape ticks, only 1,601 (2.0%) had a currently visible
witness; the remaining 76,564 used blind repulsion. All 60 candidate murders
happened while self-preservation was the immediately preceding intent.

| living Playing ticks within 64px | control | candidate |
| --- | ---: | ---: |
| nobody nearby | 52.25% | 37.62% |
| exactly one nearby | 20.99% | 45.31% |
| at least two nearby | 26.76% | 17.07% |
| sole nearby impostor | 8.34% | 27.25% |
| sole nearby crew | 12.65% | 18.07% |

Witness seeking therefore did the opposite of its goal: it reduced group time
and more than tripled sole-impostor exposure. A counterfactual audit of the
candidate's retained observations found that a third living player had been
seen within the last 30/60/120/180/300 ticks on only
7.8%/11.9%/19.0%/24.2%/31.8% of escape ticks. Relaxing `currently visible` to a
bounded recent fix would still leave blind fallback dominant; an unbounded fix
would recreate the stale-destination failure.

The union self filter also left two self targets. In both cases two colors
occupied the exact geometric self anchor while the cached `self_color` was not
the true hosted color; selecting one geometric candidate left the other
eligible. The follow-up excludes every record matching the self sprite rather
than selecting a single match.

## Decision

Stop threshold-tuning reactive proximity flight. Equal-speed movement cannot
open a gap from a killer already in range, and role-neutral flight mostly
separates the player from crew. The local safety fix removes blind fallback:
after 12 ticks it may move only when a current third-player destination exists;
otherwise normal behavior continues. The next survival experiment should test
proactive group-supported task selection by itself, with self-preservation off.
