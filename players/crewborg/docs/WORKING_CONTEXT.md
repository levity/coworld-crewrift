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
single variable against the previous champion.

**Standing, measured over 243 league episodes (2026-07-26 22:08 → 2026-07-27 05:12, all
v20):** rank 10/18, and on raw win rate exactly the field mean in both roles — crew 26.3 %
(50/190) against a field 26.3 %, imposter 73.6 % (39/53) against a field 73.7 %.

Two things that came out of that and should shape what gets worked on:

- **Crew win rate does not separate policies in this league.** Pooled over 1,969 crew
  seats and 12 policies, χ² = 9.3 on 11 dof, p = 0.59; between-policy sd is 0pp after
  removing binomial noise, and it replicates on a disjoint 111-episode sample (p = 0.87).
  `notsus`, which does no deduction at all, sits at 27.3 %. A crew seat is 1 of 6 on a
  shared-outcome team, so this says the league cannot *see* crew differences at this
  sample — not that crew skill is worthless. But every recent lever has been crew-side.
- **Imposter looked heterogeneous and does not survive scrutiny.** p = 0.011 across 11
  policies, but that rests entirely on one 24-seat outlier; drop `shrike` and p = 0.18,
  restrict to the five best-sampled policies and p = 0.60. Treat the imposter table as
  unresolved, not as a ranking.

**Uploaded baseline: `crewborg-lw:v21`** (`fd9c08cf-f329-4404-a7cc-00f8fc988664`) — v20's
config plus `CREWBORG_KILL_ANCHOR=sprite`. **Uploaded, not submitted.** It is a bug fix,
so per `~/projects/softmax/improvement-loop.md` step 5 it was folded into the baseline without spending
a hosted A/B. The next A/B is **v21 vs v21 + the next strategy lever**, so both arms carry
the fix and it is not a variable.

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
| `CREWBORG_KILL_ANCHOR` | `off` `sprite` | Imposter strike range measured from our own decoded sprite instead of the camera point (the two differ by a fixed `(-2,-6)`). **Hosted A/B, 100 v 100 imposter-pinned:** mechanism fixed (wasted strike ticks/ep 5.7 → 0.8, p = 0.001) but outcomes did not improve (win 85.0 % → 76.0 %, p = 0.108; kills/ep 1.60 → 1.53, p = 0.492; ejections 15 % → 20 %). Shipped in v21 as a correctness fix, **not** as an improvement |

Retained rejected experiments (`GROUP_TASKING`, `WITNESS_TASKING`, `POST_TASK_ESCORT`,
`POST_TASK_LOITER`, `SELF_PRESERVATION`, `STICK`) stay off — `docs/TODO.md` holds the
retention rationale and the bar for reactivating one.

## Active branch

**`lawrence`** — the personal main line, tracking `levity/lawrence`. It is `origin/master`
plus our 82 commits; we have no write access to `origin/master`, so rebase onto it rather
than merging, and push only to `levity`.

```bash
git fetch origin && git rebase origin/master && git push levity lawrence
```

## Open threads

1. **Coverage is the crew bottleneck, not precision.** Hosted `xreq_51754f1f`: 11 player
   ballots against 81 skips (12%), all 11 correct; `oracle_ghost_coverage_gain` is +51pp.
   The headroom is in *acting*, not in ranking.
2. **A false witness pin can name a crewmate at p=1.0** and eliminate the true assignment
   from the hypothesis space for the rest of that game. `CREWBORG_KILL_WINDOW` addresses
   the direct channel; the pin path itself still assumes every live player was decoded.
   `docs/TODO.md` has the measurement and the remaining work.
3. **The imposter's bottleneck is ACQUISITION, not the strike.** Measured over the
   kill-anchor A/B (200 imposter-pinned episodes, `xreq_f9db8da2` / `xreq_a76aa9d5`),
   the kill-ready time budget is:

   **Report this per episode, not pooled over ticks.** The episode is the independent
   unit, and a handful of very long games hold so many kill-ready ticks that the pooled
   share disagrees with the typical game — pooled says 75–80 % blind, per-episode says
   43–47 %. Both are below, per-episode first:

   | share of kill-ready time | v20 | v21 | (pooled v20 / v21) |
   |---|---|---|---|
   | no live victim visible | 42.7 % | 46.7 % | 79.4 % / 75.4 % |
   | visible, out of range | 28.2 % | 30.8 % | 12.0 % / 14.9 % |
   | in range, witness gate blocks | 11.8 % | 15.2 % | 5.6 % / 8.8 % |
   | holding a kill intent | 17.3 % | 7.3 % | 2.9 % / 0.9 % |
   | ready ticks per kill | 184 | 188 | |

   So the budget is roughly **45 % blind, 30 % closing, 13 % witness-gated, 12 %
   striking**. Acquisition is the largest single bucket but it is not three quarters of
   the problem, and "visible but cannot kill yet" (closing + witness ≈ 43 %) is just as
   large. Only the striking row separates the arms (p < 0.001); every other row is well
   inside noise at n=100 per arm.

   The blind time is an **information** failure rather than a positioning one: 92–95 % of
   blind ticks have no sighting of any live crewmate newer than the 120-tick tracking
   window, mean sighting age 447 ticks, mean distance to the last-known position 218 px.
   **That killed the cheapest candidate for free** — extending the pre-ready beeline
   (`CREWBORG_RECON_WINDOW`) cannot help when there is nothing fresh to beeline toward.

   (This supersedes the earlier "target visible ~43 % of ready ticks, 4× rivals" figure,
   which is not what the trace shows.)

   Search already scores rooms by expected crew occupancy — `modes/search.py:_pick_room`,
   not the "random nearby task room" the older docs described — and every weight is
   env-overridable (`CREWBORG_PICKROOM_W_*`). Occupancy is informative but diffuse:
   reacquisition `distance_error` median 34 px, 68.4 % within 100 px, but median
   `top_probability` 0.003 (and reacquisitions are selection-biased toward looking in
   roughly the right place).

   **Room choice is not the binding constraint — tested and null.** `xreq_e8a28175`
   (v22, default weights) vs `xreq_4fff13b2` (v23, `W_OCCUPANCY` 3.0→5.0,
   `W_UNVISITED` 2.5→1.0), identical image, 100 v 100 imposter-pinned, arms verified
   from `imposter_overrides.pickroom`. Victim-visible share 53.9 % → 54.6 % (+0.6 pp,
   p = 0.899); imposter win 77.0 % → 80.0 % (p = 0.606); kills/ep 1.67 both; ejections
   29.0 % → 24.0 % (p = 0.423, guard fine). Weighting believed-crew rooms harder does
   not find more people. What is left on this line is the occupancy tracker itself
   (median `top_probability` 0.003), or attacking the ~30 % "visible but out of range"
   bucket instead.

4. **Blind time is a survivorship artifact, not a defect. Ejection is what costs games.**
   Blind kill-ready time per episode is median **5 ticks**, mean 124, and 63 % of episodes
   have under 50; the worst 10 % of episodes hold 62 % of it. Split the 100 v22 episodes
   into quartiles by blind time and the direction is the opposite of intuition:

   | quartile | blind ticks | win | kills/ep | **ejected** | our Playing ticks |
   |---|---|---|---|---|---|
   | q1 | 0–1 | **44 %** | 1.00 | **68 %** | 753 |
   | q2 | 1–4 | 96 % | 1.88 | 20 % | 1221 |
   | q3 | 5–120 | 88 % | 1.84 | 20 % | 1228 |
   | q4 | 146–1749 | 80 % | 1.96 | 8 % | 1860 |

   Blind time only accumulates while the seat is alive. q1 has none because the crew
   ejected us early. **Do not optimise blind time** — optimise not being ejected.

5. **The ~30 % "visible but out of range" time is correct behaviour. Leave it alone.**
   Over 2,734 such ticks we are in Hunt with a move command 98.7 % of the time, never
   idle. Of 107 approach runs (≥6 ticks): 73.8 % close ≥4 px, 22.4 % stall, 3.7 % fall
   back; median run starts 47 px out, lasts 17 ticks and closes 19.4 px, and 81.3 % end
   near kill range. At ~3 px/tick that is the right physics. A witness does not block
   movement, only the strike, so it is not a cause here.

6. **The imposter is on cooldown 87 % of its playing time, and does nothing to blend.**
   Per episode: 1,265 ticks in Playing, of which **1,106 on cooldown** and only 160
   kill-ready. Cooldown splits Search 75.2 % / Recon 18.4 % / Evade 6.3 % / crewmate
   tasking **0.03 %** (35 ticks across 100 episodes). Positioning during cooldown is
   already good — a crew member is in view 66.7 % of it, and it is within 80 px of a task
   station 91.2 % of the time. **Imitation is entirely absent.** Pretend mode (follow /
   recover / wander / fake-task) was deleted 2026-06-24; `rule_based.py` records the
   deletion but **no rationale survives in git history, CHANGELOG.md or TODO.md** — find
   out why before re-adding it. Note the constraint: an imposter *cannot* do a real task
   (`sim.nim` routes its A press to `tryKill`), so faking can only be positional — stand
   in a task rect, motionless, for a believable time.

7. **Activity appears to cost ejections, and that constrains every acquisition lever.**
   The kill-anchor fix removed ~5 wasted standing-still ticks per episode and our
   ejection rate went 15 % → 20 % while imposter win went 85.0 % → 76.0 %. Neither is
   significant at n=100 (p = 0.35 and 0.108) so this is a hypothesis, not a result — but
   it points the same way as the recorded `BE_DUMB` arm, where searching ~97 % of ticks
   tripled ejections (14 % → 40 %) for only +10 % kills. Any "seek crew harder" lever
   must carry ejection rate as an explicit guard, not just kills. Threads 4 and 6 together
   make **ejection the next objective**, and restoring some form of blending the most
   obvious untested lever.

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
