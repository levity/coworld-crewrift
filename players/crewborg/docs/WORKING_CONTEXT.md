# crewborg working context

**What this is.** The live, high-signal state of *what we're working on right now* — the
minimal set of cross-session facts worth carrying into the next session. Read it on
startup to resume; **update it as you learn**, and prune anything no longer load-bearing.
**Clear and reseed it when we pivot**, keeping only the new objective.

**This is not a log.** Finished work lives in `CHANGELOG.md`, per-experiment detail in
`docs/experiments/`, uploaded versions in `crewborg/version_log.md`. Do not accumulate
"prior update" or "superseded" sections here.

---

## League

**Champion: `crewborg-lw:v20`** (`9a30196e-93c5-4bba-a661-b27d6b49aa33`, submission
`sub_3178148f`, membership `lpm_9d8f1b5e`, `--auto-champion lineage`).

```
CREWBORG_DEDUCTION_HISTORY=1  CREWBORG_DECISION_GATE=loose
CREWBORG_SPEAKER_TRUST=on     CREWBORG_KILL_WINDOW=both
```

v20 is v18's configuration plus `CREWBORG_KILL_WINDOW=both`, so the kill window is the
single variable against the previous champion. It had played no rounds at submission time;
the standing shown against its membership is a line-level figure shared with v17 and v18,
not a v20 result.

**Watch coverage, not precision.** The kill window's known cost is 3 pins out of 29 in the
offline replay, and pins drive essentially all ejects. If ejects/game fall materially
against v18, `margin` alone (without `at-least-one`) is the fallback.

## The two crew brains

| | fitted posterior | deduction |
|---|---|---|
| code | `strategy/suspicion.py` (+ `suspicion_lab/`) | `deduction/` |
| gate | default | `CREWBORG_DEDUCTION_HISTORY=1`, crew only |
| AUC | 0.355 | 0.83 |

They do not compose for crew: under the flag a crewmate never has `belief.suspicion`
written, and the ballot routes through `deduction/decision.py`. The fitted posterior stays
live for the **impostor** role (deflection targeting via `top_suspect`) — do not delete it.

An empty `suspicion` also disables **Accuse** (so the emergency button is never spent),
escort suspect-avoidance, and the deterministic vote fallback. See the `fold_belief`
docstring in `crewborg/__init__.py`.

## Levers

All default off. One env var per lever, so an A/B moves one thing.

| lever | presets | evidence |
|---|---|---|
| `CREWBORG_DECISION_GATE` | `shipped` `loose` `loose+p40` `structural-only` | `loose` is live; its A/B primary missed (coverage 14.2% → 16.6% against ~22% predicted) |
| `CREWBORG_SPEAKER_TRUST` | `off` `on` `mild` | `on` is live; tempers claim/vote weight by how selectively a speaker votes |
| `CREWBORG_KILL_WINDOW` | `off` `margin` `at-least-one` `both` | `both` is live. Offline over 64 seats: pins 28/29 → 26/26 sound, truth kept 63/64 → 64/64, 14 observations recovered, 3 pins lost |

Retained rejected experiments (`GROUP_TASKING`, `WITNESS_TASKING`, `POST_TASK_ESCORT`,
`POST_TASK_LOITER`, `SELF_PRESERVATION`, `STICK`) stay off — `docs/TODO.md` holds the
retention rationale and the bar for reactivating one.

## Active branch

`crewborg-brain-separation`, on top of `crew-signals-v2`. Unpushed.

## Open threads

1. **Coverage is the crew bottleneck, not precision.** Hosted `xreq_51754f1f`: 11 player
   ballots against 81 skips (12%), all 11 correct; `oracle_ghost_coverage_gain` is +51pp.
   The headroom is in *acting*, not in ranking.
2. **A false witness pin can name a crewmate at p=1.0** and eliminate the true assignment
   from the hypothesis space for the rest of that game. `CREWBORG_KILL_WINDOW` addresses
   the direct channel; the pin path itself still assumes every live player was decoded.
   `docs/TODO.md` has the measurement and the remaining work.
3. **Impostor 2nd-kill conversion.** Sits kill-ready with a target visible ~43% of ready
   ticks (4× rivals) yet converts no faster — the long-standing hesitancy lever.

## Measurement gotchas

- **Ghost seats keep solving.** A dead crewmate still emits `deduction_history_decision`
  with `action="eject"`, and those never become ballots: over 16 hosted episodes, 26 of 37
  eject decisions came from dead seats. Filter on liveness (the seat's own
  `domain.player_died`) before quoting any decision-level rate. `decision_snapshot.self` is
  null during *every* Voting phase and is not a liveness signal.
- **League episodes carry no results and no policy artifacts.** The only league signal is
  `episode.json -> policy_results`. To see behaviour, fire your own experience request.
- **Win rate is one bit per game.** At n=100 it cannot resolve below roughly +15pp. Prefer
  `tools/decision_quality.py`, which scores the belief against ground truth.
