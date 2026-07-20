# Persistent solver A/B result

## Design

- Control: `crewborg-solver-ab:v1`, `CREWBORG_SOLVER=0`
- Candidate: `crewborg-solver-ab:v2`, `CREWBORG_SOLVER=1`
- Shared: source `434bcd2`, veto off, full telemetry, fixed Prime roster,
  crew slot 0, and exactly two impostors in slots 6-7
- Hosted requests: control `xreq_d9be498e-9bc6-4e82-a615-41a6a92e006f`;
  candidate `xreq_3dbe49cb-224c-45c8-a8c0-4e3cb63c2b49`
- 64 episodes per arm; all 128 completed with no operational failures

## Result

The candidate did not improve crew win rate:

| Metric | Control | Solver | Delta |
| --- | ---: | ---: | ---: |
| Crew wins | 18/64 (28.1%) | 13/64 (20.3%) | -7.8pp |
| Player-vote precision | 20/21 (95.2%) | 22/38 (57.9%) | -37.3pp |
| Impostors ejected | 19 | 14 | -5 |
| Crew ejected | 11 | 17 | +6 |
| Tasks completed (available replays) | 439/62 (7.08/ep) | 443/63 (7.03/ep) | -0.05/ep |

The win-rate difference is unresolved at this size: two-proportion `p=0.30`,
95% CI for the candidate-minus-control delta `[-22.6pp, +7.0pp]`. It is evidence
against enabling the solver as implemented, not proof that aggregation cannot
work.

The requested timing change worked exactly: median subject vote time moved from
13 ticks after Voting began to 1,161 ticks, leaving roughly 39 of the 1,200
meeting ticks.

Mechanism counts use 125/128 hash-complete replays. Three replays were absent
when the warehouse input was assembled; authoritative win counts above use all
128 episode records.

## Diagnosis

The solver increased vote volume but lost the control's calibrated abstention.
The dominant wrong target was yellow (`crewborg:v107`): 13 of the candidate's
16 incorrect player votes.

Claim extraction is the clearest upstream defect. `parse_social_claims` treats
every named non-victim in an accusatory clause as an accusation target. For
example:

```text
Yellow saw cyan at a vent.
```

currently yields:

```text
accuse yellow (vent)
accuse cyan (vent)
```

Across the replay corpus, the parser emitted 69 false yellow-target accusations
in the candidate arm. It confuses witnesses, reporters, quoted accusers, and
grammatical subjects with the player being accused. Waiting for the full meeting
then gives these bad relational facts time to contaminate both the solver ledger
and the legacy suspicion fallback.

## Next iteration

Make claim extraction predicate- and provenance-aware before retuning solver
likelihoods:

1. Represent the attributed source separately from the current speaker and the
   accused target.
2. Parse `X saw Y vent/kill` as source `X` accusing target `Y`; never accuse `X`
   merely because it appears in the clause.
3. Mark relayed/hearsay claims and discount duplicate relays of the same
   source-target fact.
4. If the corrected solver does not clear its decision gate, skip or retain a
   pre-meeting legacy decision rather than recomputing the fallback from
   untrusted late-meeting chatter.
5. Replay the captured chats offline to measure claim precision and
   counterfactual vote precision, then rerun the same hosted A/B.

Implemented and validated offline in
`docs/experiments/2026-07-17-claim-parser-offline.md`; no second hosted A/B has
been run yet.
