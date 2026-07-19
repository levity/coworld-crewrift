# Single-source crowd-pile cap

## Hypothesis

The confirmed solver's remaining false decisive picks are concentrated in
nominally single-source conclusions that remain highly probable when that
source is removed. Those picks are not corroborated independent claims; they
are sustained by correlated public ballots and are disproportionately likely
to target crew.

## Design

Use the production parser and solver at the standard tick-1,152 cutoff. Select
the cap only on the six correlation, timing, and confirmation arms. Hold out
both arms from each of the two later guidance experiments.

Apply the cap only when exactly one attributed accusation source supports the
candidate. Preserve the existing requirement that the target remain the leader
after removing that actor's claims and ballots. Reject the pick if the
source-removed marginal exceeds the selected cap.

Success requires removing false picks in the held-out histories without losing
correct picks. This is an offline mechanism gate, not a crew-win estimate.

## Offline result

On the six selection arms, the source-removed marginal separated every
single-source decisive pick:

| Outcome | Picks | Source-removed marginal |
| --- | ---: | --- |
| Correct | 11 | `0.321` to `0.371` |
| False | 3 | `0.419` to `0.509` |

The selected upper cap is `0.39`.

On the four held-out guidance arms:

| Outcome | Picks | Retained by `P<=0.39` |
| --- | ---: | ---: |
| Correct | 6 | 6 |
| False | 8 | 0 |

Across all ten arms, the existing solver makes 167/191 correct decisive picks
(87.4%). The cap retains all 167 correct picks and removes 11 of 24 false picks,
for 167/180 (92.8%) precision. It changes only single-source decisions; every
multi-source pick and all meeting timing remain unchanged.

The held-out separation is narrow: the highest correct marginal is `0.388` and
the lowest false marginal is `0.400`. Hosted evaluation must therefore verify
both that the gate fires and that reduced wrong subject votes do not cost
useful impostor ejections.

## Hosted result

Fresh matched requests ran 100 games per arm against the same pinned roster.
The control was `crewborg-solver-timing-candidate:v1`
(`xreq_f5242562-4b12-4466-9ddd-4b84bb6ba711`); the candidate was
`crewborg-solver-crowd-cap:v1`
(`xreq_3da4e8ee-3c47-4578-953d-03ab4510db23`). Both completed without request
failures or subject connect, disconnect, or vote timeouts.

| Metric | Control | Crowd cap |
| --- | ---: | ---: |
| Crew wins | 35/100 | 39/100 |
| Subject votes: impostor / crew / skip | 24 / 1 / 75 | 25 / 0 / 75 |
| Team ballots: impostor / crew | 247 / 83 | 209 / 111 |
| Ejections: impostor / crew | 18 / 8 | 16 / 14 |

The crew-win delta is +4 points with Fisher `p=0.66` and an approximate
95% interval of -9.4 to +17.4 points. It is not outcome evidence.

The direct mechanism did reproduce. On candidate history the cap removed two
false public-solver picks, changing 16/18 to 16/16. On control history it
removed one correct pick, changing 32/33 to 31/32. The candidate's own ballot
therefore became slightly safer, but its teammates produced more crew-target
ballots and crew ejections. Transcript audit found that the subject did not
vote for any of the 14 candidate-arm crew ejections.

Retain the cap as a narrow subject-ballot safeguard because it actively removed
fresh false picks and the hosted outcome was not adverse. It does not solve the
larger coordination problem. Most fixed-roster crew ballots arrive around tick
300, while the final solver message arrives at tick 1,152 after those ballots
are immutable.
