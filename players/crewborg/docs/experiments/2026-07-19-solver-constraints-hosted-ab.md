# Constraint-aware solver composition hosted A/B

## Treatment

The candidate changes three interactions on top of the corrected combined
stick/alibi v2 artifact:

1. Living crew using stick mode stop collecting `tailing_self`, because their
   own group-seeking policy induced the proximity.
2. Source-removal robustness preserves all structural evidence and applies the
   correlated-crowd ceiling to a separate social-only solve.
3. A no-accuser conclusion may fire only when removing structural constraints
   makes that conclusion cease to clear the normal probability and margin
   gates.

The source is `de63cbd`. Full validation passed with 548 tests and 13 skips,
changed-file Ruff and `git diff --check` clean, and a successful local Gate 1.
It was uploaded inertly as `crewborg-solver-stick-alibi:v3`, immutable version
`aa0415e5-a4ba-4bcd-a673-2212a0866eb5`. It has not been submitted.

## Hosted design

Two fresh 100-game requests used Coworld Crewrift 0.1.59, the same exact
seven opponents, fixed subject crew at slot 0, and fixed impostors at slots 6
and 7. The only policy-version difference was subject v2 versus v3.

- Control v2: `xreq_0b8775fe-d8a1-4214-bd7d-170a552048ec`
- Candidate v3: `xreq_51edfbcf-d415-453f-ae10-2e9b1d58317a`

Both requests completed 100/100 with no request failures.

## Outcome

Authoritative experience-request score rows give:

| Metric | Control v2 | Candidate v3 | Change |
| --- | ---: | ---: | ---: |
| Crew wins | 32/100 | 48/100 | +16.0pp |
| Mean score | 38.67 | 54.81 | +16.14 |
| Mean score in losses | 6.09 | 5.92 | -0.17 |
| Negative-score games | 3 | 4 | +1 |
| Completed tasks | 751 | 759 | +8 |
| Standing-still penalties | 84 | 78 | -6 |

The win difference has two-sided Fisher exact `p=0.030`; the Newcombe 95%
interval is approximately +2.4 to +28.8 points. The flat loss score and task
and penalty counts argue against trading routine crew contribution for votes.
This is one unpaired random batch, so the interval describes sampling
uncertainty, not attribution among the three bundled changes.

## Objective meeting behavior

Both replay warehouses are complete and hash-clean:

- Control: 5,898,803 events across 100/100 replays.
- Candidate: 5,214,811 events across 100/100 replays.

| Meeting metric | Control v2 | Candidate v3 |
| --- | ---: | ---: |
| Voting phases | 164 | 145 |
| Subject ballots | 111 | 105 |
| Subject player votes: impostor / crew | 24 / 3 | 52 / 8 |
| Subject player-vote precision | 88.9% | 86.7% |
| Crew-team player ballots: impostor / crew | 196 / 139 | 230 / 92 |
| Impostor / crew ejections | 6 / 21 | 15 / 12 |
| Subject joined impostor / crew ejections | 0 / 1 | 9 / 1 |
| Tick-241 solver lines | 3 | 6 |

All nine tick-241 targets across both arms were impostors. Candidate subject
precision is statistically indistinguishable from control (Fisher `p=1.0`);
the change is useful vote coverage, not better conditional precision. The
candidate cast player votes on 57.1% of its ballots versus 24.3% control and
cast a correct player vote on 49.5% versus 21.6% (`p<0.001` for both
comparisons). Team player-vote precision moved from 58.5% to 71.4%
(`p=0.0006`), and the impostor share of ejections moved from 22.2% to 55.6%
(`p=0.024`).

Stick-tail suppression activated exactly: subject chat cited "they were
tailing me" 11 times in control and zero times in candidate. Those 11 control
citations all named the fixed cyan impostor, so this batch does not establish
that suppressing the logically endogenous feature helped outcomes.

## Old-versus-new solver counterfactual

The production public-history analyzer replayed both warehouses through source
`38771ef` (v2) and `de63cbd` (v3) at the final decision cutoff. This holds each
history fixed and isolates public solver selection:

| History | v2 solver | v3 solver | Added by v3 |
| --- | ---: | ---: | ---: |
| Control histories | 10/11 correct | 10/12 correct | 0/1 correct |
| Candidate histories | 12/12 correct | 22/22 correct | 10/10 correct |

Of the ten added correct candidate picks, four had no accusation source and
required killed-player hard clears; six had one source and were rescued by
measuring the crowd ceiling without structural constraints. Runtime crewborg
cast a correct player vote in each of those ten meetings, sometimes choosing
the other real impostor after private evidence was added. The sole added wrong
control opportunity did not become a subject player vote.

This counterfactual shows that the two solver-composition fixes activated in
the intended way. It also shows that candidate histories were unusually
favorable: even v2 found 12/12 public picks there versus 10/11 in control.
Therefore the full +16-point outcome difference must not be assigned to the
source change.

## Residual risk and decision

All eight candidate wrong votes targeted pink or yellow crew. Six carried the
generic solver line `multiple players flagged them`; two had no subject chat.
The public-only reconstruction selected no wrong candidate targets, so private
priors or private constraints changed these decisions. This supports the open
task to give the joint solver a residual prior that excludes evidence already
scored structurally.

Retain v3 as the best combined artifact. The constraint changes passed both
local correctness and hosted mechanism gates, and the outcome result is
positive, but one fresh batch and a bundled treatment are insufficient for a
league submission. No submission was made.

## Warehouse reliability note

Hosted results and logs were unavailable, while replay bytes were returned
already decompressed under the historical `replay.json.z` filename. Minimal
results files were reconstructed from authoritative XP scores and fixed roles;
all behavioral counts come from objective replays. The 0.1.59 expander
(`1cbd4de4`, tag `0.1.59`) completed every replay without a hash warning.

The warehouse wrapper now detects replay encoding from content, smoke-tests
the chosen expander before the batch, prints representative extraction
failures, and exits nonzero for failed or hash-incomplete episodes. Four
focused wrapper tests and Ruff pass.
