# Predicate-aware claim parser offline gate

## Scope

This gate replays the persistent-solver A/B warehouse through the old and new
claim pipelines before another hosted evaluation:

- 125 hash-complete hosted replays: 62 control and 63 solver-arm episodes
- 243 meetings in which the subject was alive at the decision point
- all chat and public votes observed through tick 1,152 of each 1,200-tick meeting
- episode-persistent claims and meeting records
- fixed hosted color/role truth from `player_joined` and `episode_players`

The repeatable gate is `tools/analyze_solver_history.py`. The old result came
from running it against image `crewborg:solver-persistent`; the new result uses
the working tree. This is a social-only counterfactual: private perception,
witness pins, task clears, and fitted suspicion priors cannot be reconstructed
from the public event warehouse. It measures parser/solver regression, not
expected hosted win rate.

## Result

### Solver-arm history

| Metric | Old | Predicate-aware | Delta |
| --- | ---: | ---: | ---: |
| Accusation targets emitted | 441 | 214 | -51.5% |
| False-role targets | 173 | 81 | -53.2% |
| Yellow false targets | 61 | 29 | -52.5% |
| Claim target truth rate | 268/441 (60.8%) | 133/214 (62.1%) | +1.4pp |
| Social-only solver picks | 37/116 (31.9% coverage) | 32/116 (27.6%) | -4.3pp |
| Correct solver picks | 27/37 (73.0%) | 27/32 (84.4%) | +11.4pp |
| False solver picks | 10 | 5 | -50.0% |
| Solver picks targeting yellow | 5 | 1 | -80.0% |

### Both arms

| Metric | Old | Predicate-aware | Delta |
| --- | ---: | ---: | ---: |
| Accusation targets emitted | 1,013 | 511 | -49.6% |
| False-role targets | 330 | 153 | -53.6% |
| Claim target truth rate | 683/1,013 (67.4%) | 358/511 (70.1%) | +2.7pp |
| Social-only solver picks | 79/243 (32.5% coverage) | 66/243 (27.2%) | -5.3pp |
| Correct solver picks | 63/79 (79.7%) | 57/66 (86.4%) | +6.6pp |
| False solver picks | 16 | 9 | -43.8% |

The new parser deliberately emits fewer claims. Raw target truth rate moves less
than false-target count because the corpus contains genuine incorrect reads and
impostor lies; those are valid parses even when their targets are crew. The
decision-level result is the useful gate: the corrected solver retains all 27
correct picks on solver-arm history while removing five of ten false picks.

## Changes validated

- `Yellow saw cyan vent` records yellow as the attributed source and cyan as the
  only target.
- `Red vented. Yellow saw it` resolves the pronoun attribution to yellow.
- `Yellow sus orange` and `Yellow sus me` preserve yellow as source rather than
  treating yellow as a target.
- Neutral body reports, victims, questions, and location lists do not become
  accusations merely because they name colors near a cue.
- Relays are marked, discounted, and deduplicated by original source-target
  relation. Their likelihood is conditioned on both the attributed source and
  the current speaker, so a suspected impostor cannot launder a fabricated
  attribution through a trusted player.
- If the late solver abstains, legacy fallback uses the target captured when the
  meeting opened; late chat cannot independently contaminate both paths.

## Gate decision

The implementation clears the offline gate and is suitable for a new matched
hosted A/B. It remains opt-in and should not be submitted or enabled by default
until that hosted result improves crew win rate and preserves vote precision.
