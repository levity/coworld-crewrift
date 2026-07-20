# Correlation-aware solver hosted A/B

## Design

- Solver-off control: `crewborg-solver-correlation-control:v1`
  (`bf01aeb1-8630-4153-8f8c-22491d13b0f5`)
- Solver-on candidate: `crewborg-solver-correlation:v1`
  (`475af19e-8e80-49a6-8406-631b4dbe6893`)
- Requests: control `xreq_3b3b35a1-1824-4a64-b9d6-e64f203bec40`;
  candidate `xreq_3e4d5f38-c792-44b9-a4b9-38879c0edc8a`
- Both arms used the exact image at source `69d6986`, Crewrift `0.1.59`, the
  fixed prior solver-evaluation roster, crewborg in crew slot 0, and impostors
  in slots 6-7. Only `CREWBORG_SOLVER` differed.
- Both requests completed 64/64 episodes with zero operational failures.

## Result

| Metric | Solver off | Solver on | Change |
| --- | ---: | ---: | ---: |
| Crew wins | 24/64 (37.5%) | 34/64 (53.1%) | +15.6pp |
| Subject correct player votes | 11 | 17 | +6 |
| Subject wrong player votes | 3 | 5 | +2 |
| Subject player-vote precision | 78.6% | 77.3% | -1.3pp |
| Subject player votes | 14 | 22 | +8 |
| Impostors ejected | 11 | 14 | +3 |
| Crew ejected | 7 | 7 | 0 |
| Eligible meetings | 99 | 110 | +11 |
| Median subject vote offset | 13 ticks | 1,164 ticks | +1,151 |

The win-rate difference has a two-proportion normal approximation `p=0.076`.
It is promising directional evidence, not a resolved effect. The mechanism is
increased recall at essentially unchanged precision: six additional correct
votes, two additional wrong votes, three additional impostor ejections, and no
increase in crew ejections.

## Replay audit

All 128 public replays expanded with complete traces and no warnings:

- Control: 64 episodes, 3,759,451 events.
- Candidate: 64 episodes, 3,471,427 events.
- Current public-evidence solver: control 15/15 correct decisive picks;
  candidate 13/15.

The two candidate-history errors were:

1. A vote-only orange posterior with no supporting accusation.
2. A green posterior supported by persistent false claims from three apparent
   sources, including two agents emitting the same generated accusation.

The first is a model-contract error: public voting can corroborate a claim but
should not manufacture an accusation target by itself. Requiring at least one
accusation source removes that miss and no correct pick across all five retained
histories. Pooled decisive precision becomes 97/108 (89.8%).

The second is not cleanly separable by the retained public features. Exact
template decay, actor clustering, source breadth budgets, stronger robustness,
and language-weight flattening all removed more correct picks than errors.
Threshold, role-likelihood, and public-vote-weight sweeps likewise left the
current defaults on the best observed precision/coverage frontier.

The live job artifacts became inaccessible (`403`, current credential is not a
softmax team member), so the audit cannot reconstruct private suspicion priors,
witness pins, watched-task clears, or the exact runtime solver path. Public
replays and authoritative episode scores remain available.

## Confound and next test

The first A/B changed both inference and timing. Solver-off crewborg voted at a
median 13 ticks, while solver-on crewborg waited until 1,164 ticks. The fallback
target was frozen at meeting entry, but vote timing can still alter the public
meeting dynamics.

The next A/B therefore uses one new exact-source image with:

- control: `CREWBORG_SOLVER=0 CREWBORG_SOLVER_DEFER=1`
- candidate: `CREWBORG_SOLVER=1 CREWBORG_SOLVER_DEFER=0`

Both arms freeze the legacy fallback at meeting entry and act at the deadline.
Only the candidate may replace it with the joint solver. This is an attribution
test; `CREWBORG_SOLVER_DEFER` remains off by default and is not presented as a
production improvement.

## Timing-matched replication

- Control request: `xreq_5d19f6f9-bfc0-4276-932c-aa7ac796e33f`
- Candidate request: `xreq_358f2c2f-5438-4603-9e63-889aae160b81`
- 64/64 episodes completed in each arm with zero failures.
- Both arms used the exact image at `4f55b2f`; only the upload-time solver and
  deferral flags differed.

| Metric | Deferred solver off | Solver on | Change |
| --- | ---: | ---: | ---: |
| Crew wins | 31/64 (48.4%) | 35/64 (54.7%) | +6.25pp |
| Subject correct player votes | 16 | 26 | +10 |
| Subject wrong player votes | 2 | 2 | 0 |
| Subject player-vote precision | 88.9% | 92.9% | +4.0pp |
| Subject player votes | 18 | 28 | +10 |
| Impostors ejected | 12 | 15 | +3 |
| Crew ejected | 7 | 9 | +2 |
| Eligible meetings | 110 | 107 | -3 |
| Median subject vote offset | 1,164 ticks | 1,164 ticks | 0 |

The win difference is unresolved (`p=0.48`, approximate 95% CI
`[-11.0pp, +23.5pp]`), but the timing confound is removed and the mechanism
replicates more strongly: the candidate made ten additional player votes and
all ten were correct.

The two timing-matched candidate histories expanded 128/128 with zero trace
warnings (7,209,030 events). Replaying public chat and votes through the current
solver produced 15/16 correct decisive picks on control history and 18/20 on
candidate history.

One actual candidate error at yellow matched a public-evidence solver error:
blue and pink emitted the exact same generated vote claim on the same tick.
Treating identical utterances as one source group removes it, but across all
seven histories it removes 12 correct picks for two errors. Requiring a
non-vote accusation to ground a target is worse, removing 25 correct picks.
A conditional threshold reduction to `P=0.60` adds only 22/33 correct picks;
requiring two current public votes yields 16/26. All are rejected.

Across both fresh A/Bs, solver arms won 69/128 crew games versus 55/128
controls (+10.9pp, `p=0.080`, approximate 95% CI `[-1.2pp, +23.1pp]`).
Subject player-vote precision is 43/50 (86.0%) versus 27/32 (84.4%), with 18
additional correct votes and four additional wrong votes. The most defensible
next experiment is a larger timing-matched confirmation of the unchanged
solver, not another rule fitted to the sparse errors.

## 100/arm confirmation

- Control request: `xreq_2b8f99aa-aee5-4911-9634-15fa81736fe1`
- Candidate request: `xreq_95153fe2-d463-45c5-8db2-4069d9b30359`
- Both reused the exact uploaded versions and configuration from the
  timing-matched replication. Each request completed 100/100 episodes with no
  request-level failures.

| Metric | Deferred solver off | Solver on | Change |
| --- | ---: | ---: | ---: |
| Official crew wins | 37/100 (37.0%) | 50/100 (50.0%) | +13.0pp |
| Subject correct player votes | 28 | 26 | -2 |
| Subject wrong player votes | 0 | 8 | +8 |
| Subject player-vote precision | 100.0% | 76.5% | -23.5pp |
| Subject player votes | 28 | 34 | +6 |
| Impostors ejected | 9 | 14 | +5 |
| Crew ejected | 18 | 18 | 0 |
| Hash-complete voting phases | 159 | 158 | -1 |
| Median subject vote offset | 1,163 ticks | 1,163 ticks | 0 |

The official win difference is directional (`p=0.064`, approximate 95% CI
`[-0.6pp, +26.6pp]`). Two candidate episodes have anomalous subject scores of
`-100`: both are marked completed with no episode/policy error and contain
ordinary subject actions, but their public replay hash fails. The official
analysis retains them. As a declared trace-completeness sensitivity check,
excluding those two gives 50/98 candidate wins versus 37/100 control
(`+14.0pp`, `p=0.047`, approximate 95% CI `[+0.3pp, +27.7pp]`).

The control warehouse contains 5,436,336 events across 100/100 complete
replays. The candidate warehouse contains 5,162,156 events across the 98
hash-complete replays; the two warning episodes are excluded from behavioral
counts. Unlike the prior replication, subject-vote precision did not improve
(`p=0.006`, Fisher exact). Seven of the eight wrong candidate votes were
meeting-entry fallback votes under the public-evidence reconstruction; only one
matched a decisive solver pick. Runtime private priors and clears are
unavailable, so this attribution is suggestive rather than exact.

The team-level mechanism remains favorable: the candidate ejected five more
impostors with no additional crew ejections. The public-evidence solver made
21/25 correct decisive picks on clean candidate history and 11/12 on control.
Across all nine retained arms, the current solver makes 162/181 correct
decisive picks (89.5%).

All three fresh matched A/Bs favor the solver:

| Run | Control wins | Candidate wins | Change |
| --- | ---: | ---: | ---: |
| Concurrent screen | 24/64 | 34/64 | +15.6pp |
| Timing-matched replication | 31/64 | 35/64 | +6.25pp |
| Timing-matched confirmation | 37/100 | 50/100 | +13.0pp |
| **Pooled** | **92/228 (40.4%)** | **119/228 (52.2%)** | **+11.8pp** |

The stratified common-effect test gives `p=0.011` and a common odds ratio of
1.62. The pooled normal-approximation 95% interval for the absolute win effect
is `[+2.8pp, +20.9pp]`.

One post-confirmation hypothesis discounted byte-identical accusations emitted
by different speakers on the same tick. It was narrowly motivated by two known
generated-consensus errors, but failed the full retained-history gate: decay
values from 0.75 through 0 removed 4-10 correct picks and no wrong picks. The
change was removed.

## Decision

The unchanged correlation-aware solver is demonstrably better on crew wins.
Its value appears at team level through more impostor ejections, while
individual vote precision is noisy and should not be presented as an
established gain. Further rule fitting to the sparse public errors is more
likely to remove useful recall than improve the frontier. Promote the exact
timing-matched candidate behavior; keep veto off. League submission remains a
separate, explicitly approved action.
