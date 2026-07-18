# Commitment-aware solver offline gate

## Question

Can public commitment distinguish useful accusations from unsupported social
noise without broadly suppressing consensus?

The current solver models accusation claims and public ballots, but it does not
condition a claim's weight on whether its attributed source participated in the
ballot. This test uses only information visible before crewborg's standard
1,152-tick decision cutoff.

## Retained evidence

Nine hosted arms provide 643 hash-complete subject episodes and 1,101 eligible
meetings. Pairing each source-target accusation with that source's public ballot
at the cutoff gives:

| Source ballot state | Correct target | Wrong target | Precision |
| --- | ---: | ---: | ---: |
| Voted for claimed target | 852 | 201 | 80.9% |
| Voted for another target | 21 | 19 | 52.5% |
| Explicitly skipped | 208 | 152 | 57.8% |
| No visible ballot | 83 | 93 | 47.2% |

Vote order also shows correlated bandwagoning: first votes for a target are
63.0% correct; second votes are 55.1%; third votes are 50.0%; fourth-or-later
votes are 38.5%. A blanket same-target vote discount had already failed the
offline gate, so this iteration tests source participation rather than vote
rank.

These histories use a fixed role-pinned roster. Speaker style and policy
identity are therefore confounded with role and are not safe features. The
selected signal is limited to a general public action: whether the attributed
source has cast any visible ballot.

## Variants

The sweep independently varied:

- weight of ballots without a matching source claim;
- weight of accusations followed by a different ballot;
- weight of accusations followed by an explicit skip; and
- weight of accusations whose source had no visible ballot.

Only the last dimension improved the pooled precision/coverage frontier.
Discounting unsupported ballots, explicit skips, or contradictory ballots
removed useful correct decisions.

## Selected model

`SolverConfig.no_ballot_claim_decay=0.30` applies to accusation and
at-least-one claims when the attributed source is absent from the current
meeting's public ballot map. Any explicit ballot state, including skip or a
different target, preserves the prior claim weight. Defenses are unchanged.

| Metric | Confirmed solver | Commitment-aware |
| --- | ---: | ---: |
| Correct decisive picks | 162 | 154 |
| Wrong decisive picks | 19 | 14 |
| Precision | 89.5% | 91.7% |
| Eligible-meeting coverage | 16.4% | 15.3% |

The candidate retains 95.1% of correct picks and removes 26.3% of errors. On
the latest hash-complete candidate history it remains 21/25, so the pooled gain
does not come from fitting away that batch's decisions.

## Hosted test

Run a fresh 100/arm fixed-roster A/B:

- baseline: exact confirmed timing candidate, solver on and veto off;
- candidate: commitment-aware source, solver on and veto off;
- both: same 1,152-tick solve cutoff, source-frozen fallback, telemetry, crew
  slot 0, and impostors slots 6-7.

Primary mechanism metrics are decisive solver precision/coverage, actual
subject player-vote precision, and crew/impostor ejections. Crew win rate is the
outcome metric.
