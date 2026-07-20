# Predicate-aware solver hosted screen

## Design

- Candidate: `crewborg-solver-ab:v3`, source `4b0c94c`
- Runtime: `CREWBORG_SOLVER=1`, `CREWBORG_SOLVER_VETO=0`, full telemetry
- Hosted request: `xreq_e0bbd63f-0d80-42e6-abba-1eb3265c9196`
- Historical control: solver-off v1 request
  `xreq_d9be498e-9bc6-4e82-a615-41a6a92e006f`
- Historical broken-parser solver: v2 request
  `xreq_3dbe49cb-224c-45c8-a8c0-4e3cb63c2b49`
- All arms used Crewrift Prime 0.4.65, the same pinned eight-policy roster,
  crew subject in slot 0, and impostors in slots 6-7.
- The v3 request completed 64/64 episodes with zero operational failures.

This was a candidate-only screen against one-day-old controls, not a concurrent
randomized A/B. It is useful for mechanism and directional checks, but a
submission decision would still require a fresh matched control.

## Result

| Metric | Control v1 | Broken solver v2 | Fixed solver v3 |
| --- | ---: | ---: | ---: |
| Crew wins | 18/64 (28.1%) | 13/64 (20.3%) | 16/64 (25.0%) |
| Player-vote precision | 20/21 (95.2%) | 22/38 (57.9%) | 17/22 (77.3%) |
| Wrong player votes | 1 | 16 | 5 |
| Wrong votes at yellow | 0 | 13 | 0 |
| Impostors ejected | 19 | 14 | 16 |
| Crew ejected | 11 | 17 | 10 |
| Subject tasks completed | 439/62 (7.08/ep) | 443/63 (7.03/ep) | 474/64 (7.41/ep) |
| Team kills | 231/62 (3.73/ep) | 233/63 (3.70/ep) | 234/64 (3.66/ep) |
| Median subject vote offset | 13 ticks | 1,161 ticks | 1,164 ticks |

The parser fix recovered much of the broken solver's behavior, but did not beat
the historical control on wins:

- v3 minus control: -3.1pp, two-proportion `p=0.69`, approximate 95% CI
  `[-18.4pp, +12.2pp]`.
- v3 minus broken solver: +4.7pp, `p=0.53`, approximate 95% CI
  `[-9.8pp, +19.2pp]`.

At 64 episodes these win differences are unresolved. The mechanism changes are
large enough to be useful: wrong votes fell 16 to 5, the yellow bug disappeared,
and crew/impostor ejections returned close to control.

## Replay mechanism

The v3 warehouse contains all 64 hash-complete replays and 3,611,422 expanded
events. Replaying its public evidence through the current parser/solver yielded:

- 200 accusation targets, 143 targeting actual impostors (71.5%)
- 119 eligible subject meetings
- 24 social-only solver picks (20.2% coverage)
- 18/24 correct social-only picks (75.0% precision)
- false parsed targets: green 15, yellow 14, red 11, orange 8, pink 6, blue 3

Actual v3 wrong votes were three at green and two at blue. None targeted yellow.
An offline public-evidence decomposition of the 22 actual player votes found:

- 6 votes matched a decisive social-only solver pick: 4 correct, 2 wrong.
- 16 followed the meeting-entry target after the social-only solver abstained:
  13 correct, 3 wrong.

This decomposition omits private perception and suspicion priors, so it is a
path diagnostic rather than an exact reconstruction of the runtime report.

The two social-solver misses were confidently wrong green picks (`P=0.899` and
`P=0.952`). Multiple speakers independently repeated or relayed the same false
read, and the solver multiplied them as stronger evidence than warranted. The
three abstention-side misses had low public marginals for the chosen fallback
target (`P=0.206`, `0.282`, and `0.329`).

## What not to do

- Do not merely raise `CREWBORG_SOLVER_P`. The two wrong social picks were more
  confident than four correct social picks (`P=0.746` to `0.794`), so a higher
  threshold preferentially removes correct decisions.
- Do not simply enable the existing veto at its default `0.65`. On this history
  it would reject all 16 inferred fallback votes: 13 correct and only 3 wrong.
- Do not submit or enable the solver by default. The hosted screen improved the
  broken implementation, but did not establish an advantage over control.

## Next iteration

The most promising change is correlation-aware evidence aggregation:

1. Keep full weight for witnessed pins, watched-task clears, and the first
   independent source-target claim.
2. Apply diminishing returns to additional same-target claims within one
   meeting, even when they come from different speakers. These bots share
   observations, templates, relays, and bandwagons, so their errors are not
   conditionally independent.
3. Preserve cross-meeting accumulation, but decay repeated target consensus
   unless a later meeting adds a new direct observation or a public outcome.
4. Calibrate the diminishing-return curve on both hosted histories and require
   it to remove the two confident green errors without losing the four correct
   social picks.
5. Only after that offline gate clears, run a fresh concurrent 64/arm A/B.

## Artifact note

The Observatory episode records contained authoritative per-policy scores, but
the job results-artifact endpoint returned unavailable for all v3 episodes. The
replay fetcher also saved raw `CREWRIFT` replay bytes under the `.z` filename.
For local analysis, minimal results files were reconstructed from the episode
records' scores and fixed role configuration, and the unchanged raw replay
bytes were wrapped in zlib before warehouse ingestion. The version-matched
0.4.65 expander then processed 64/64 replays with no hash warnings.
