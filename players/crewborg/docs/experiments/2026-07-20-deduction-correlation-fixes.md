# Deduction correlation fixes and synthetic audit

## Objective

Follow up the first append-only deduction hosted test without another upload.
The hosted candidate's three avoidable errors were public-ballot piles with no
accusation against the selected target, while the old synthetic generator drew
chat and ballots independently and could not reproduce persistent crowd errors.

## Changes

- A synthetic actor now retains a latent target across meetings. Its chat and
  ballot usually express that same belief, and other actors can adopt one crew
  member's crowd target. Impostors may join a false crew pile but do not pile
  onto their partner through this mechanism.
- Public ballots remain likelihood factors in the joint assignment posterior.
  A nonstructural eject now additionally requires at least one active
  accusation against the target. Direct pins and targets present in every
  surviving assignment remain sufficient without public accusation.
- Hidden-kill constraints now exclude every previously dead player, including
  ejections, from the possible perpetrator set for a later murder.
- Added deterministic all-meeting synthetic auditing, typed inference-config
  counterfactuals, and a detailed legacy/new meeting-decision comparison tool.
  The workflow is documented in `docs/reference/deduction-analysis.md`.

## Same-history hosted replay

The clean candidate warehouse has 93 eligible meetings:

| Policy | Correct / selections | Precision | Coverage |
| --- | ---: | ---: | ---: |
| append-only before accusation gate | 14 / 18 | 77.8% | 19.4% |
| append-only after accusation gate | 14 / 15 | 93.3% | 16.1% |
| legacy public solver | 16 / 17 | 94.1% | 18.3% |

The gate removes exactly three wrong vote-only selections and no correct one.
On 69 clean control meetings, the append-only result remains 3/4.

## One-thousand-game audit

Seed 7 generated 1,000 games and three snapshots per game. The production
final-history summary is 84.6% vote precision at 64.2% coverage, 76.8% top-
target accuracy, 43.8% top-pair accuracy, and zero murder-clear violations.
The old independent generator reported 94.9% precision at 49.4% coverage.

Across all 3,000 meeting snapshots:

| Variant | Correct / selections | Precision | Coverage |
| --- | ---: | ---: | ---: |
| production default | 1,252 / 1,524 | 82.2% | 50.8% |
| ballot weight 0.20 | 967 / 1,175 | 82.3% | 39.2% |
| ballots removed | 572 / 688 | 83.1% | 22.9% |
| stronger repeat decay | 1,073 / 1,290 | 83.2% | 43.0% |

The alternatives improve precision by at most one point while discarding far
more correct selections than errors. Stronger repeat decay also regresses the
candidate hosted replay from 14/15 at 16.1% coverage to 8/9 at 9.7% coverage.
It and the ballot-weight changes are rejected.

Claim-count and posterior gates show the same tradeoff. Requiring two accusing
sources retains 94.4% of correct selections but removes 70 correct votes to
remove 25 errors. Requiring `P>=0.80` reaches 86.2% precision but retains only
62.9% of correct votes. High claim breadth is not uniformly safe: five-source
selections are only 79.0% correct in this crowd-capable generator.

## Anti-alibi semantics

For each bounded hidden-kill window, the solver records continuously co-present
players and the living players eligible to have killed. A role assignment is
excluded when none of its members could have been outside the co-present set.
Thus, if crewborg stayed with A and B, pair `{A,B}` is impossible; at least one
impostor was among the living, out-of-group players. This is a constraint on
the pair, not an individual clear for A or B. With only one companion and two
impostors, every assignment containing that companion can still have an
outside partner, so no pair is excluded. `StickMode` already seeks and holds a
cluster of at least two other live players.

## Verdict

Keep the accusation-backed decision gate, the correlated generator, and the
ejection-aware anti-alibi correction. Do not change the production likelihood
weights from this audit. The remaining sampled errors contain coordinated false
testimony from several actors; simple repeat decay, source-count gates, and
global ballot discounts cannot distinguish it without sacrificing substantial
correct coverage. The next plausible solver experiment is an explicit shared-
crowd latent factor calibrated on held-out hosted histories.
