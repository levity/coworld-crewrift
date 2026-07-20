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
crew slot 0, and fixed imposters at slots 6-7. Results pending.
