# Correlation-aware solver offline gate

## Objective

Reduce confidently wrong social-solver votes caused by correlated claims while
preserving the solver's episode-wide, multi-meeting constraint aggregation.
The gate replays public chat and votes through the production parser and solver;
it does not reconstruct private witness pins, watched-task clears, or fitted
suspicion priors.

## Retained data

- Original solver A/B warehouse: 125 subject episodes across the solver-off and
  solver-on arms.
- Predicate-aware hosted screen warehouse: 64 subject episodes.
- Combined: 189 episodes and 362 eligible subject meetings.
- All histories use the same fixed roster, crew subject in slot 0, and impostors
  in slots 6-7.

## Selected model

1. Keep the strongest source/stance/target claim in a meeting at full weight.
2. Weight additional sources making the same claim in that meeting by
   `same_target_decay ** rank`, with `same_target_decay=0.8`.
3. Preserve later-meeting accumulation. Existing same-source claim repeats and
   newly added same-voter/target repeats decay by `0.7`.
4. When exactly one original source supplies all accusation claims for a
   decisive target, remove that source's claims, relays, and votes and recompute
   the joint posterior. Fire only if the target remains the top live marginal.
5. Witnessed pins and genuinely multi-source constraints do not require that
   counterfactual.

The counterfactual costs at most one additional solve over 21 joint hypotheses
in the standard seven-opponent, two-impostor game.

## Result

| Retained history | Before | Correlation-aware | Precision change |
| --- | ---: | ---: | ---: |
| Solver-off A/B history | 30/34 (88.2%) | 28/29 (96.6%) | +8.3pp |
| Solver-on A/B history | 27/32 (84.4%) | 24/29 (82.8%) | -1.6pp |
| Predicate-aware v3 history | 18/24 (75.0%) | 17/21 (81.0%) | +6.0pp |
| **Pooled** | **75/90 (83.3%)** | **69/79 (87.3%)** | **+4.0pp** |

Wrong decisive picks fell 15 -> 10. Correct picks fell 75 -> 69, so the
candidate retained 92.0% of correct solver decisions and 87.8% of all decisions.
At runtime, solver abstention falls back to the existing deterministic vote path,
whose historical precision was higher than the solver's; lower solver coverage
therefore does not imply an automatic skip.

## Rejected variants

- `same_target_decay <= 0.45`: suppressed correct cyan consensus without removing
  the remaining green errors.
- Hard claim/vote deduplication: removed useful public-vote evidence and reduced
  parser-screen precision.
- Same-target vote-bloc decay: public vote outcomes carried most of the correct
  cyan signal; discounting them reduced both precision and coverage.
- Full leave-one-actor-out robustness or `ROBUST_P >= 0.4`: lost substantially
  more correct picks than wrong picks.
- Threshold-only and the existing veto remain rejected by the prior screen.

## Decision

The effect is modest and one retained history slips, so this is not submission
evidence. It is strong enough for a fresh matched 64/arm hosted A/B using
same-source solver-off and solver-on artifacts, the prior fixed crew roster, and
full telemetry. Primary mechanism metrics are actual player-vote precision,
wrong votes, solver versus fallback path, and crew/impostor ejections; crew wins
remain the outcome metric.
