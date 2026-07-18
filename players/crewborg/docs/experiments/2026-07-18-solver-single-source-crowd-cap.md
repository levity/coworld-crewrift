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
