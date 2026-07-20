# Deduction-history v2 300-episode crew screen

## Question

Measure the current append-only deduction policy at enough volume to estimate
its forced-crew behavior precisely. This is not an A/B and cannot establish a
causal game-win improvement over v1 or the legacy policy.

## Candidate

`crewborg-deduction-history:v2` is policy version
`07342cb8-2b6c-48cc-8aaa-897d0f6a17f6`, built from clean commit `4bcfb90` and
image `sha256:ddea00b7924db22daa9fd14d51e6fc528aef0bcffa4f56c111132138eb3120d2`.
It enables `CREWBORG_DEDUCTION_HISTORY=1`, stick mode, sound alibi collection,
and full telemetry. Gate 1 passed locally on Crewrift 0.1.59.

## Design

The platform caps an experience request at 100 episodes, so this consists of
three independent 100-episode requests. Each uses the exact fixed roster and
forced roles from the v1 hosted A/B: v2 at crew slot 0; `crewborg-aaln:v25`,
`notsus:v130`, `jordan-crewborg-aaln:v1`,
`crewrift-prime-notsus-richard:v4`, and `crewborg:v107` as crew; and
`daveey-prime-notsus:v2` plus `softmaxwell-crewborg:v34` as imposters.

The direct Crewrift 0.1.59 target is
`cow_52d06063-dfa8-45fc-9533-a5365a71a04d`. The reusable request body is
`2026-07-20-deduction-history-v2-300-crew-request.json`.

## Analysis plan

Pool only complete, operation-clean episodes after reporting each cohort’s
separate completion and failure counts. Report crew wins, score, tasks, deaths,
ejections, subject ballot precision and coverage, team impostor/crew ejections,
meeting timing, and solver activation. Stream replays into one warehouse at two
full-tick expansion workers, then inspect public-history deduction decisions and
sample all wrong subject crew ballots before proposing another policy change.

## Requests and result

| Cohort | Request |
| ---: | --- |
| 1 | `xreq_a988d08a-edd1-453b-938a-d4879399e602` |
| 2 | `xreq_1bdc51c6-c37e-4ba3-bab7-c70968193fbd` |
| 3 | `xreq_2434d4aa-c76a-4750-a03d-0ae33aec1e06` |

All three read back with 100 episodes, the exact eight policy versions, v2 at
crew slot 0, and fixed imposters at slots 6-7.

## Result

All three cohorts completed: 300/300 episodes. The replay warehouse contains
15,591,580 events; all 300 replays expanded with the Coworld 0.1.59 expander,
with zero extraction failures and zero `trace_warning` episodes. The service
did not expose separate results or policy-log artifacts, so the warehouse
synthesized outcome dimensions from each replay. This supports outcome, chat,
ballot, timing, and public-history analysis, but cannot prove a private runtime
activation record.

### Hosted outcomes

| Measure | Result |
| --- | ---: |
| Subject crew wins | 145 / 300 (48.3%; exact 95% CI 42.6%--54.2%) |
| Mean subject score / tasks | 55.03 / 7.59 |
| Subject completed all 8 tasks | 260 / 300 (86.7%) |
| Subject killed / ejected | 172 / 4 games |
| Subject non-skip ballots | 46: 43 impostor, 3 crew (93.5% precision) |
| Subject skip ballots | 212 |
| Subject ballot timing | median 1,160 ticks after meeting start |
| All crew non-skip ballots | 540 impostor, 281 crew (65.8% precision) |
| Actual ejections | 38 impostors, 34 crew |

The subject was alive at the standard late-decision point in 258 meetings. It
cast one ballot in each: 46 non-skip (17.8% coverage) and 212 skips. Its 95%
exact interval for non-skip ballot precision is wide despite the encouraging
point estimate: 82.1%--98.6%.

Survival remains materially connected to outcome: crew won 83/124 games
(66.9%) where the subject survived, versus 62/176 (35.2%) where it was killed
or ejected. Four games ended before it completed a task; this is not the old
slot-4 reveal freeze, because this screen placed the subject at slot 0.

### Public-history replay

Replaying only public chat, ballots, deaths, and meetings through tick 1,152
produced 258 point-in-time decisions. The public solver selected 18 ejects:
15 impostors and 3 crew (83.3% precision; 7.0% coverage). Its leading marginal
was an impostor in 143/258 meetings (55.4%), while its exact top imposter pair
was correct in 37/258 (14.3%). These are not runtime ballot metrics: the live
policy also has private observations, alibi/stick inputs, and may make a
different decision.

All three public-solver errors were crowd-supported crew targets. Two match
actual subject crew ballots: an imposter's vote or apparent agreement was
combined with a crew accusation against Blue or Yellow. The third actual crew
ballot was a false personal `saw orange kill or vent` accusation, which the
public replay does not independently select. This is useful diagnosis, not a
license to lower thresholds: the public-only solver remains vulnerable when a
real crew accusation is amplified by an imposter ballot.

The 75/90 offline threshold would have reduced public choices to 12, with 11
correct (91.7%), but this is only six fewer retrospective choices and is not a
pre-registered or causal improvement. Do not change the production threshold
from this screen alone.

### Interpretation

This is a solid operational screen for v2: it ran cleanly at volume and the
actual subject ballots were highly precise. It is not an A/B, so do not claim
that its 48.3% crew win rate improves on the older 100-game v1 sample. The
most actionable next investigation is an offline, history-preserving reliability
feature for public sources: distinguish independent crew corroboration from a
claim boosted by a suspected imposter's ballot, then replay it against this
300-game warehouse before any new upload.
