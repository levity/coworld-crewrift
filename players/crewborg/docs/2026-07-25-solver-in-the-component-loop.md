# Adapting the deduction solver to a component-level improvement loop (2026-07-25)

Companion to [`2026-07-25-crew-plan-deduction-first.md`](./2026-07-25-crew-plan-deduction-first.md).
That plan asks *"solver or fitted posterior, and how do we fit the solver?"* — and answers it well.
This note asks the next question: **what does the solver look like as an instrument in a loop that
promotes on component metrics rather than win rate**, and what has to change for it to serve that
role.

It contains one new measurement, run against the 200 prime-gt policy artifacts already on disk,
which changes the priority order in that plan's Phase 2.

---

## 0. TL;DR

1. **The solver is not currently behaving as a solver.** 91 % of its ejects (72 / 79) fire on
   `personally witnessed impostor action` — a direct pin from `_witnessed_actions`, which needs no
   joint enumeration at all. The whole role-conditioned likelihood machinery, and all 22 hand-set
   `InferenceConfig` constants, account for **7 of 79 ejects**.
2. **Two of its three private-observation channels never fire in the field.** Across 200 games:
   vent pins **0**, alibi structural constraints **0** (427 evaluations, all rejected for
   `no player was continuously co-present`). The `direct` channel is 100 % kill-witness.
3. **The claim parser drops 81 % of utterances** (1153 ignored vs 265 parsed), and **864 skip votes
   are discarded as evidence-free** — in a game whose tally rule makes the skip bloc decisive.
4. Consequently the plan's Phase 2a (refit the 22 constants) has a **hard ceiling of ~9 % of
   decisions**. The coverage is in the pin channel, and the pin channel is missing its best
   Crewrift-specific detector.
5. The solver's *architecture* — a frozen `DeductionHistory` + a pure `infer()` — is exactly the
   right shape for the loop. It needs one structural addition (a **three-mode history builder**) to
   become the fair oracle, and four scoped evidence-channel changes.

---

## 1. The measurement

Reproducible with the new tool (no warehouse, no replay expansion, no duckdb — the policy artifact
already carries the decision *and* its full evidence audit):

```sh
python players/crewborg/tools/audit_decision_traces.py \
  ~/.claude/jobs/ba2ec2e2/tmp/prime-gt-wh_episodes
```

200 Prime games, forced-crew subject seat, 266 decision traces.

**Ejects by evidence class**

| class | n | at-imposter | precision | share of ejects |
|---|---:|---:|---:|---:|
| `structural` (pin / all-assignments) | 72 | 72 | 100.0 % | **91.1 %** |
| `accusation-backed` (the joint solve) | 7 | 7 | 100.0 % | 8.9 % |
| **total** | **79** | **79** | **100.0 %** | coverage 29.7 % |

**Active evidence by channel** — `vote` 1078, `claim` 265, `direct` 79. So the social channels carry
**94 % of the evidence volume and 9 % of the decisions.**

**Ignored evidence — why channels never fire** (the actionable half)

| n | channel: reason |
|---:|---|
| 1153 | `utterance`: no recognized deduction claim |
| 864 | `vote`: skip vote has no target likelihood |
| 427 | `alibi`: no player was continuously co-present |
| 95 | `vote`: own derived vote is not new evidence |
| 79 | `alibi`: kill was directly witnessed *(correct suppression)* |
| 26 | `alibi`: no bounded off-screen kill window |
| 25 | `direct`: body transition has 0 or 2 possible nearby actors |

**Skip reasons** — `posterior below parity-aware threshold` 160, `ballot evidence lacks accusation or
structural support` 115, `leading set is not separated` 96, `insufficient independent or structural
support` 31. **Zero** skips cite `no deduction evidence`: the solver is never starved of input. It is
**evidence-rich and discrimination-poor**.

### 1.1 Why the alibi channel is dead, and why that is a rules finding not a bug

`_derive_kill_constraints` excludes a player from being the killer only if they were
`_close_to_self` in **every** frame of a gapless window spanning the kill. That is the Among Us
"buddy alibi": in a game with generous vision and a large shared room, continuous co-presence is
common. Crewrift gives every player a **128 × 128 px viewport with raycast occlusion on a
1235 × 659 map** — about 1.6 % of the map — so continuous co-presence across a whole kill window is
close to unobtainable. 427 evaluations, 0 constraints, is what that predicts.

This is the single most valuable structural-evidence channel in the design (it *excludes*
assignments rather than nudging a likelihood), and it is disabled by an assumption imported from a
different game. The fix is not to delete it but to weaken "continuous" into "co-present for a
sufficient fraction, with the gaps bounded by walk-time reachability" — i.e. replace an all-frames
predicate with a **reachability** predicate.

### 1.2 Why the vent pin never fires

`_witnessed_actions` pins a venter only when the *vent rectangle itself* is continuously rendered
across two consecutive ticks and a player appears in / vanishes from it. With a 64 px sight radius
that conjunction is rare, and Crewrift has **no in-vent state at all** (`sim.nim:tryVent` is a pure
teleport), so there is no dwell time to catch. 0 firings in 200 games.

The Crewrift-native detector is different and much cheaper: **a position discontinuity**. If the same
colour is observed at `p` at tick `t` and at `q` at tick `t + Δ` with
`dist(p, q) > MaxSpeed · Δ / MotionScale`, that player teleported, and only imposters can vent. It
needs no line of sight on a vent, works at any range, and works retrospectively across a gap in
observation as long as both endpoints were seen. It produces the same proof-strength pin that
already drives 91 % of ejects at 100 % precision.

---

## 2. What the solver already gives the loop

The architecture is genuinely well-suited, and most of the credit belongs to two decisions made
early:

- **`DeductionHistory` is a frozen event stream, and `infer()` is pure.** The docstring says it
  outright: *"inference always accepts a frozen `DeductionHistory` and can therefore be rerun after
  parser, likelihood, or decision-policy changes."* Plus `.through(tick)` for time-clipping. That is
  precisely the interface an offline oracle needs.
- **`EvidenceAudit` records `status` / `reason` / `weight` / `targets` per item, and it is
  serialised into the hosted trace.** The measurement in §1 needed no new instrumentation — it read
  artifacts that already existed. That is the "observability is something you build" discipline
  paying off, and it is why the diagnosis above cost zero hosted games.

Existing tooling maps onto the loop's stages almost one-for-one:

| Loop stage | Already exists on this branch |
|---|---|
| Instrument | `EvidenceAudit` in the hosted trace; `domain.deduction_history_decision` |
| Scorecard (belief + vote metrics) | `evaluate_deduction.py` — threshold grid, calibration buckets, ground-truth join |
| Zero-cost drill | `synthetic.py` + `analyze_deduction_synthetic.py` — a *generator* tier below config-only drills |
| Decision-level A/B | `compare_deduction_decisions.py`, joined on `(episode_id, meeting_id)` |
| Anti-churn contract | the plan doc's Phase 3 (offline gate, one change per A/B, held-out splits, kill criteria) |

## 3. The one structural change: a three-mode history builder

Today there are **two** history builders that disagree about what the agent knows:

- `deduction/collector.py` (runtime) emits the rich private stream: `WorldObserved` every Playing
  tick, `TaskCounterObserved` on change, meetings, utterances, votes, deaths.
- `evaluate_deduction.py:_evaluate_warehouse` (offline) emits **public events only** — meetings,
  utterances, votes, deaths. No `WorldObserved`, no `TaskCounterObserved`.

So the offline harness scores a *strictly information-poorer* agent than the one that plays. Its own
docs flag this (*"public-history comparison excludes private witness pins, watched actions"*), but
the consequence is under-appreciated: **the offline harness structurally cannot see the channel that
drives 91 % of real ejects.** Every threshold sweep run through it is a sweep over the 9 % tail.

The fix is to make history construction a **pluggable view** with three modes, all feeding the same
`infer()`:

| mode | event stream | what the score means |
|---|---|---|
| `replayed` | the policy's own logged `DeductionHistory` from telemetry | what the policy actually believed — the baseline |
| **`fair`** | rebuilt from the replay warehouse with **observer clipping**: `player_visible_interval` + `player_state` → synthesised `WorldObserved` frames for exactly the ticks and entities *this seat could have seen*, plus the real task counter | **the fair oracle** — the best posterior obtainable from the information this seat actually had |
| `omniscient` | all `player_state` for all players, unclipped | the ceiling, and the labelling engine for likelihood mining |

That yields a **three-way decomposition** of the loss, which is sharper than the two-way one the
component-loop design assumes:

```
  replayed  →  fair        collection loss   (evidence was visible; the collector missed or garbled it)
  fair      →  omniscient  information limit (nothing to fix in inference — go stand somewhere better)
  within fair: infer() vs a counting bound   inference loss    (the likelihoods are wrong)
```

Each arrow routes to a different team of fixes, and today all three are conflated into "the posterior
isn't good enough".

**Buildability check — one real cost.** `fair` mode needs `WorldObserved` frames, and both private
channels have *consecutive-tick* preconditions (`current.tick == previous.tick + 1` for the kill pin;
a gapless window for the alibi). Warehouse `player_visible_interval` / `player_state` only exist when
`snapshot_every > 0`, and at coarse snapshots those predicates fail outright. So `fair` mode requires
**full-tick expansion** — which `stream_eval.py --workers 2` already supports, at known cost — *or*
the reachability relaxation from §1.1, which removes the gapless requirement anyway. Doing §1.1 first
makes `fair` mode cheap. That ordering matters.

## 4. The adaptation, ranked

Every item is offline-gated: it must move a pre-registered metric on **held-out games** before it
earns a hosted A/B. Costs are hosted-game costs; all offline work runs on data already on disk.

| # | Change | Why it is ranked here | Offline gate |
|---|---|---|---|
| **1** | **Position-discontinuity vent pin** in `_witnessed_actions` | Adds a proof-strength detector to the channel that already drives 91 % of ejects at 100 % precision; the existing vent pin fires 0 times in 200 games | pin count on held-out games; precision must stay 100 % |
| **2** | **Reachability alibi** — replace continuous co-presence with bounded-gap walk-time reachability | Recovers the only *structural exclusion* channel; 427 evaluations currently yield 0 constraints | active-constraint rate > 0 and assignment-space reduction, at unchanged precision |
| **3** | **Skip-vote likelihood** — count `P(skip \| crew)` vs `P(skip \| imposter)` from the corpus | 864 discarded observations; skips are the majority action, and Crewrift's tally (`votes > skips + timeouts`) makes the skip bloc decisive, so refusing to convict is a real signal | AUC of the posterior on held-out meetings |
| **4** | **Three-mode history builder** (§3) | The instrument that tells us whether items 5–6 are worth doing at all | the three-way gap decomposition itself |
| **5** | **Wire `TaskCounterObserved` into inference** | Collected today, consumed nowhere — textbook "capability exists ≠ capability is used". A watched ≥72-tick station hold with no counter decrement is the game's only self-clearing signal (measured 15 % imposter vs 36 % base) | measured log-LR with CI on the corpus; ship only if the interval excludes 0 |
| **6** | **Fit the 22 `InferenceConfig` constants** (the plan's Phase 2a) | Still worth doing, and still free — but it is now known to be **bounded by the ~9 % of ejects the social channel drives**, so it should not be first | held-out joint likelihood |
| **7** | **Parser coverage** — 1153 / 1418 utterances unparsed (81 %) | Feeds item 6's ceiling; measure what fraction of unparsed lines carry role signal before extending | share of unparsed lines with recoverable signal |

Two further changes to the **decision** layer, which the component loop cares about independently of
inference quality:

- **Model pivotality, not unilateral ejection.** `decide_from_inference` chooses "eject X" vs "skip"
  as though its own ballot decided the meeting. The real rule is `votes(X) > skips + timeouts`, ties
  lose, and abstentions count with skip — so a lone crew vote is almost never decisive, while a vote
  that joins an existing pile often is. The `sources` field already counts *other* players'
  supporting ballots and accusations; the missing quantity is `P(the team ejects X | I vote X)`.
- **Put the clock and the task counter in the loss model.** `_parity_risks` scores only parity. In
  Crewrift crew also win at `maxTicks` (a real win, not a draw) and at 48 tasks, so **skipping is
  cheaper than pure parity math implies**, and it gets cheaper as the clock runs down and the counter
  falls. `TaskCounterObserved` already carries the second term. Concretely this should *raise*
  `base_probability` late in a game the crew is winning on the clock — the opposite of the Among Us
  intuition that late meetings demand a vote.

## 5. Two corrections to the companion plan

Both are consequences of §1, not disagreements about method.

**5.1 Phase 2a is not the best free win — it is the third one.** The plan calls replacing the 22
hand-set constants *"the one with the best effort/return ratio in the whole plan"*. It is free and
worth doing, but it can only touch the 7 / 79 ejects the social channel drives. Items 1–3 above are
also free offline, and they act on the 91 %. Reorder.

**5.2 The 100 % precision figure needs one more caveat than the plan gives it.** The plan correctly
flags that the coverage sweep is counterfactual and reuses its evaluation set. Add: **the precision
is a property of the pin channel, not of the solver's calibration.** 72 / 79 ejects are "I watched
you kill someone". A threshold sweep that lowers the bar to 0.50 for 58.6 % coverage is buying that
extra coverage almost entirely from the *unvalidated* social channel — so the sweep's implied
precision at the lower bar should not be read as inheriting the pin channel's track record. Split the
coverage curve by evidence class before choosing an operating point.

One thing the plan is right about that this note reinforces: **Phase 0 (Path B on the freeze-fix
image) should still run first.** Nothing above changes the fact that the architecture comparison is
confounded by the largest known defect in the codebase, and none of items 1–7 are worth tuning on top
of an architecture we have not confirmed end-to-end.

## 6. What to buy, when you buy hosted games

The solver's evaluation unit is **meetings, not games**: 200 games produced 266 decisions, ~1.3 per
game. Every threshold, likelihood, and calibration question is meeting-limited. The `scn_meetings`
drill shape — `buttonCalls` raised, `maxTicks` short, config-only — turns the same hosted spend into
several times the decision count. Buy meetings.

---

## Appendix — reproducing §1

```sh
# the corpus used here (200 prime-gt episodes with policy artifacts)
python players/crewborg/tools/audit_decision_traces.py \
  ~/.claude/jobs/ba2ec2e2/tmp/prime-gt-wh_episodes

# machine-readable
python players/crewborg/tools/audit_decision_traces.py <episodes-dir> --json
```

The tool needs only `results.json` (for the `imposter` column → ground-truth roles via the fixed
slot→colour map `red blue green pink orange yellow purple cyan`) and
`artifacts/*.zip::telemetry.jsonl` (for `domain.deduction_history_decision`). It deliberately does
**not** need a warehouse, an `expand_replay` build, or duckdb, so it stays usable when the expander
is version-skewed.
