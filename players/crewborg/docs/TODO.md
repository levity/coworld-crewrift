# crewborg — deferred tasks

Tasks intentionally **parked to handle later** — work you (or the human) decided not to do *now* but
don't want to lose. This is the player's backlog.

**Why this file matters.** Optimization throws off side-quests: a refactor you noticed but shouldn't
chase mid-experiment, a cross-cutting fix that's out of scope for the current change, a follow-up an
eval revealed. Without a parking lot they're either lost or they derail the current thread. This file
keeps them recoverable so a future session can pick them up with the context intact.

## How to use it

- **Check `Open` at the start of focused work** — it's the standing backlog.
- **Add an item whenever you defer something mid-session.** Write *what* the task is, *why* it was
  deferred, and **enough context that a future agent can act on it without this conversation** (the
  files involved, the constraint, the reference implementation to copy). Date it.
- **Move an item to `Done` when it's complete** with a one-line outcome (and note any nuance vs the
  original ask). Prune `Done` periodically — it's a short record, not an archive (finished work lives
  in git history and the [version log](../crewborg/version_log.md)).

Keep entries scoped and actionable. A vague "improve the imposter" is not a parked task; "factor the
post-kill re-approach into a dedicated state spanning Evade→Search (see imposter-play.md)" is.

## What does NOT go here

- **The current objective / live state** → [`WORKING_CONTEXT.md`](WORKING_CONTEXT.md) (TODO is *parked*
  work; working context is what you're doing *now*).
- **Candidate learnings** → [`TENTATIVE_LESSONS.md`](TENTATIVE_LESSONS.md).
- **Standing human preferences** → [`user_preferences.md`](user_preferences.md).

> (The player's top-level `AGENTS.md` / `README.md` will point here once they exist.)

## Open

### Retained rejected experiments — chopping block, but held on purpose (2026-07-26)

Six default-off behaviours (~700 lines) survive from the survival-via-movement
direction. All were measured neutral-to-negative and none support the deduction
path, so they are formally removal candidates — **and are being kept deliberately**,
by explicit decision, not oversight. Each site carries an inline retention note; the
canonical version is the block above `GROUP_TASK_RADIUS_SQ` in `modes/normal.py`.

| Flag | Where | Lines | Recorded verdict |
|---|---|---|---|
| `CREWBORG_POST_TASK_ESCORT` | `modes/normal.py` | — | neutral |
| `CREWBORG_POST_TASK_LOITER` | `modes/normal.py` | — | neutral |
| `CREWBORG_GROUP_TASKING` | `modes/normal.py` | — | neutral |
| `CREWBORG_WITNESS_TASKING` | `modes/normal.py` | +510 (all four) | catastrophic |
| `CREWBORG_SELF_PRESERVATION` | `modes/self_preservation.py` + `modes/__init__.py`, `strategy/rule_based.py` | +177 | rejected (win 50%→30%) |
| `CREWBORG_STICK` | `strategy/event_log.py` | +16 | superseded |

**Why they stay.** Every verdict above rests on team win rate over ~100 games — one
bit per game, underpowered below roughly +15pp, so most of those "neutral" results
mean the instrument could not see the effect rather than that there was none. Two
later findings undercut them further: scoring the belief instead of the outcome turns
100 games into thousands of labelled rows (`tools/decision_quality.py`), and the one
large win we did find came from an unpredicted mechanism (spurious emergency
meetings) rather than the thing under test. These behaviours make claims about
survival geometry, witness coverage and evidence yield that the original evals never
measured at all. A finer-grained test regime is in progress; they stay reactivatable
under it and legible as a record of what was tried and how it was bounded.

**Conditions for acting on this entry.** Reactivate only with a pre-registered
mechanism hypothesis measured on something sharper than win rate. Delete only once
the finer regime has actually run and still finds nothing — a null under the coarse
metric is not sufficient grounds, which is the whole point of this entry.

Note `CREWBORG_SELF_PRESERVATION` is not fully dormant: `strategy/rule_based.py`
wires it in as selector step 4 and calls `self_preservation_enabled()` every tick for
every crewmate. Its gate is `CREWBORG_SELF_PRESERVATION and deduction_history_enabled()`,
so it was built to layer on top of the deduction path.

### ~~Retire the now write-only meeting ledger~~ — DONE (2026-07-26, `29b1e42`)

`MeetingRecord`, `Belief.meeting_history`, `Belief.social_claims`,
`solver_counted_chats` and `_track_solver_meeting` are all gone; grep confirms no
readers remain. The proposed `Belief.last_meeting_id` scalar turned out to be
unnecessary: `_track_meeting_votes` already carries the previous meeting's tick in
`social_staged_meeting_tick`, and `_count_chat_stances` keys on
`(tick, speaker, text)` and never needed a meeting id at all. Kept here only as the
record that the write-only ledger question is closed.

### Deferred by the 2026-07-26 `/simplify` pass — measurement-tool duplication

Left undone **on purpose**: these are the instruments the optimisation loop is
measured with, and rewriting them without the warehouse data on hand risks
silently changing a number rather than a behaviour. Each wants its own change with
a before/after on the same episodes.

1. **One hosted-decision loader.** `tools/decision_quality.py`, `sweep_decision_gate.py`
   and `simulate_tally.py` each walk `<ep>/results.json` + `artifacts/*.zip` +
   `telemetry.jsonl` and each define their own slot→colour tuple; the two sweep tools
   additionally re-derive `_required()` and the whole eject gate. **The forks drop
   production's `has_accusation` and `has_evidence` conditions**, so a preset promoted
   on sweep evidence was scored by a gate that is not the shipped gate. (For the
   currently shipped `loose` preset `require_support=False` collapses the difference,
   so the headline arm is unaffected.) Extract `load_decision_rows(root)` plus a single
   gate function, or better, rebuild an `InferenceResult` from the recorded
   `factor_table` and call `decide_from_inference` itself.
2. **`_evaluate_warehouse` is one 338-line function** (`tools/evaluate_deduction.py:180`)
   doing reconstruction, scoring, calibration and sampling in one nested loop, which is
   why the reconstruction is not reusable and (1) exists.
3. **Four copies of the same four metrics** (`top_target_accuracy`,
   `true_pair_top_accuracy`, `vote_coverage`, `vote_precision`) across
   `deduction/synthetic.py`, `evaluate_deduction.py` (twice) and
   `analyze_deduction_synthetic.py` — and they already differ subtly: `_evaluate_jsonl`
   counts games where the others count meetings. These numbers get quoted against each
   other in experiment records.
4. **Cheap offline wins, measured:** `synthetic.py:214` and `evaluate_deduction.py:150`
   call `infer()` then `decide()`, and `decide()` re-runs `infer()` — exactly 2× the
   dominant cost, paid 1000× by the documented `--games 1000` command; use
   `decide_from_inference`. `sweep_decision_gate.py` re-sorts every row's marginals for
   each of 55 grid points though the ranking is config-independent (~54× redundant).
   `analyze_deduction_synthetic.py` rebuilds `_meeting_snapshots` inside the variant
   loop (4× redundant).
5. **Warehouse accessors already shipped** by `crewrift_event_warehouse.suss`:
   `evaluate_deduction.py:648 _event_glob` is byte-identical to `suss._events_glob`, and
   its colour-map / slot-identity queries duplicate `suss.episode_color_maps` and
   `suss.slot_identity`.

### IMPLEMENTED (default-off): kill-window margin + at_least_one — 2026-07-26

`CREWBORG_KILL_WINDOW` presets `margin` / `at-least-one` / `both`
(`deduction/config.py`). A third env var, separate from `CREWBORG_SPEAKER_TRUST` and
`CREWBORG_DECISION_GATE`, so an A/B still moves one thing at a time.

Offline counterfactual on the 64 crew seats of `xreq_51754f1f`
(`tools/kill_window_counterfactual.py`, no hosted games bought):

| preset | pins | sound | `at_least_one` constraints | truth kept in space |
|---|---:|---:|---:|---:|
| shipped (exact 20px) | 29 | 28/29 (97%) | 0 | 63/64 |
| `margin` (6px) | 26 | **26/26 (100%)** | 0 | **64/64** |
| `at-least-one` only | 29 | 28/29 (97%) | 9 | 63/64 |
| **`both`** | 26 | **26/26 (100%)** | **14** | **64/64** |

Reading, with the sample size stated honestly: the margin removes the one unsound pin
and restores the one seat whose hypothesis space had lost the truth — so the soundness
and truth-kept gains each rest on **n=1** and are directional, not established. The
costs and the recovery are better evidenced: it drops **3 pins** (two of which were
correct), and `at_least_one` recovers **14** observations that are discarded today.
`at-least-one` alone leaves pins untouched, confirming it cannot fix the boundary case
on its own.

Pre-registered signals before any hosted arm (plan note Phase B): pins/game sound rate
must not fall, `at_least_one` constraints > 0/game, and live ballot precision must hold
at 100%. Note the coverage risk is real — pins drive ~100% of ejects, and this trades 3
of them for soundness.

### The bug this fixes: a false witness pin (2026-07-26)

Found by the hosted sanity XP `xreq_51754f1f`. **Diagnosed: this is a kill-range
boundary / sub-tick timing effect, NOT occlusion.** Not a regression either --
`_witnessed_actions` is byte-identical to `crew-signals-v2` and the relocated constants
are numerically unchanged (400 / 784).

**What happened** (episode `ereq_ff5a9fdd`, true impostors `red` + `cyan`). At world
frame 2111 the `pink` seat observed its own death and recorded
`direct | unique actor adjacent when pink became a body -> pins {blue}`, where `blue`
is a crewmate. The real killer was `red`, whose own telemetry shows
`kill_attempted @2110` and `kill_landed @2111` -- the exact frame.

`red` was **fully visible in both frames** (2110 and 2111); nothing was occluded or
off-camera. The geometry, using the production rule's previous-frame positions:

| actor | distance to victim's previous position | vs 20px KillRange |
|---|---|---|
| blue (crewmate) | 16.3px (d²=265) | inside |
| red (true killer) | 23.0px (d²=530) | **3px outside** |

So the rule found exactly one in-range actor and pinned the wrong one. The victim was
walking *toward* the killer at ~3px/tick (x: 300→297→295→292→289→body@286), so between
the last rendered frame and the sim instant of the kill the gap closed under 20px. The
rule compares frame-sampled positions against an exact threshold, and one tick of motion
spans the entire decision boundary.

**Impact in this run: none.** The pin was made at the moment of the seat's own death, so
both resulting ejects were cast as a ghost and never became ballots (see the ghost trap
below). But a live witness standing where `pink` stood would have produced the same pin.

**Fix direction, and it is already on the roadmap.** The unique-actor test needs a motion
tolerance, because "unique within exactly 20px at a sampled frame" is not sound. Measured
against this case: a 3px margin (one tick of `MaxSpeed/MotionScale ≈ 2.75`) still misses
it by one unit (d²=530 vs threshold 529); 4px or more makes it ambiguous. Two ticks (~6px)
is the defensible choice, since both parties can be closing.

**The margin and lever #1 are complementary, and the margin is the load-bearing one.**
`at_least_one` (lever #1 in `docs/2026-07-26-constraint-supply-and-the-next-plan.md`)
fires only when >=2 actors are in range -- here exactly ONE was, so on its own it would
never have triggered and this pin would still be cast. The margin is what makes the
observation ambiguous; `at_least_one` is what stops the (now ambiguous) observation from
being discarded. Measured on this episode's real hypothesis space, after murder clears
left 10 candidates:

| treatment | survivors | truth `{red,cyan}` survives? |
|---|---|---|
| today: pin `{blue}` | 4 | **no -- eliminated** |
| margin only (observation dropped) | 10 | yes, but the kill teaches nothing |
| margin + `at_least_one{blue,red}` | 7 | yes, prunes 30% soundly |

**Severity is worse than "a wrong vote".** A false pin does not add noise, it REMOVES
THE TRUTH from the hypothesis space: `{red,cyan}` was not among the four survivors, so
from frame 2111 that seat could never reach the right answer again. The actual killer
`red` finished at marginal **0.028** -- rated nearly innocent, because the kill that
should have implicated it was consumed by a pin naming someone else.

This is why `structural-only` (which trusts pins absolutely and removes the accusation
corroboration that might otherwise object) wants the margin landed first.

### MEASUREMENT TRAP: ghost seats keep solving, and inflate any decision-level metric

A dead crewborg seat still runs the deduction solve every meeting and still emits
`domain.deduction_history_decision` with `action="eject"`. Those decisions are never
cast -- a ghost cannot vote -- but they look identical in telemetry.

Measured over `xreq_51754f1f` (16 episodes, crewborg crew seats):

| | count |
|---|---|
| eject **decisions** in telemetry | 37 |
| of those, made **after the seat's own death** | **26 (70%)** |
| eject decisions from **live** seats | 11 |
| player-ballots actually cast (`results.json.vote_players`) | **11 — reconciles exactly** |

All **three** wrong ejects in this batch were ghost decisions. Live ballot precision was
**11/11**. Reading the decision stream without a liveness filter reports 34/37 and three
failures that never happened.

`tools/decision_quality.py` and the signals panel already restrict *belief* metrics to
living seats; the same filter has to be applied to *decision* and *eject* counts. The
cheapest reliable liveness signal is the seat's own `domain.player_died` event for its
own colour (note `self` is null in `decision_snapshot` during **every** Voting phase,
dead or alive, so it is NOT a liveness signal).

### Deferred by the same pass — correctness-adjacent, needs a decision not a cleanup

These change behaviour, so they are **not** cleanup. Each is stated with the evidence
that makes it suspicious.

- **`ActionState.report_ticks` counts the wrong thing.** It is documented and
  implemented as "consecutive ticks the report *intent* has been resolved", so it
  increments while merely walking to the body, but both consumers treat it as *failed
  presses*: `REPORT_REPOSITION_TICKS=24` tightens the press margin and
  `REPORT_TIMEOUT_TICKS=120` abandons the body. A body across the map takes well over
  120 ticks to walk to, so it can be abandoned before a single press — the opposite of
  the edge-park freeze this was added to fix. Increment inside the in-range press
  branch instead.
- **`DEDUCTION_EARLY_CHAT_TICKS = 240` is an absolute age** in the same branch that
  learned the meeting length from GameInfo. Hosted advertises `VOTE TIMER 1200T`, but
  the no-GameInfo fallback is 240 and auto-submit fires at 48 remaining (age 192), so on
  any server without the interstitial the documented tick-240 provisional-chat channel
  **never fires**. Express it in `_remaining_ticks` terms like
  `DEADLINE_LLM_REMAINING_TICKS`, or as a fraction of `effective_vote_timer_ticks`.
- **Intent `reason` prose is load-bearing.** `modes/normal.py:_revalidate_group_target`
  branches on `current_reason.startswith("group-aware tasking:")` and `events.py`
  classifies the self-preservation stage by `intent.reason.startswith("self preservation
  (safe distance)")`. Editing a human-readable string for clarity silently changes
  behaviour in one place and drops a metric in the other. `Intent` should carry a
  structured tag alongside the prose.
- **Three `NormalMode` instances.** `modes/report_body.py` and
  `modes/self_preservation.py` each construct their own private `NormalMode()`
  delegate, so tasking latches (`_target`, `_max_progress`, `_swept`) live on shadow
  objects, and with `CREWBORG_SELF_PRESERVATION=1` the *registered* `NormalMode` is
  never selected at all. Delegates are also never wired by the registry, so they get no
  `emit` and no `on_enter` — latent today because `NormalMode` emits nothing.
- **Restoring Accuse under the deduction brain.** See `docs/deduction-history.md`
  "What the flag also switches off". Decomposing the 2026-07-25 A/B needs the fitted
  arm with Accuse disabled, which is the one-flag test `HANDOFF.md` already names.
- **`tasks_completed_watched` train/serve skew.** The fitted weights were trained with
  a real value for this feature (the strongest single weight at -10.8) but it is served
  as a hardcoded `0.0`, because the runtime detector that produced it was removed after
  replay showed 392/550 inferred completers were wrong. A zeroed strong-negative
  feature is a candidate explanation for that path's measured AUC of 0.355 and is worth
  checking before any further work on the fitted model.

### Deferred by the same pass — one measured hot-path item left alone

`deduction/inference.py:_witnessed_actions` is ~83 ms of a ~113 ms solve at 20k
frames: it rebuilds each frame's player/body/vent maps twice (every frame is built
once as `current` and again as `previous`) and calls `sorted()` on two
almost-always-empty sets per frame. A single forward pass carrying the previous
frame's maps measured **31 ms vs 83 ms**. Not done here because it is the most
correctness-sensitive function in the new brain and deserves its own change with the
synthetic and warehouse suites re-run, not a ride-along in a cleanup pass.

### Test sustained pursuit as solver evidence (2026-07-22)

The memoryless repulsion controller records continuous one-on-one exposure and
labels it `pursuit` after 12 ticks for telemetry only. Use hosted traces to test
whether duration, closing velocity, distance band, and persistence after route
changes distinguish impostors from crewmates. Only add an immutable pursuit
event and likelihood weight if the signal generalizes out of sample. Ordinary
proximity or the fact that crewborg fled must never create suspicion.
(Retargeted 2026-07-25: the destination is `deduction/inference.py`'s evidence
derivation; the legacy `strategy/meeting/solver.py` no longer exists.)

### Add map-aware possible-killer constraints to the pair ledger (2026-07-20)

Per-kill close co-presence is sound but too sparse to exclude pairs by itself,
and a singleton cannot be weighted toward crew because non-killing impostors
often stay with the group. Extend `KillAlibi` or add a sibling immutable event
that retains the victim's last-known position/time, its reachable map region,
and each player's tracked reachable region over the death window. Exclude a
pair only when neither member could have intersected the victim. Keep the raw
geometry and timing in the audit trail; any derived possible-killer set must be
recomputable when tracking assumptions change. Validate reachability against
known replay killers before permitting any impact on the posterior.
(Retargeted 2026-07-25: build this in `deduction/inference.py` — `docs/deduction-history.md`
already lists "map-reachability kill windows" as a known gap. The legacy `KillAlibi`
type named above was deleted with the old solver; use the deduction ledger's own
co-presence events.)

## Done

### Deleted the legacy crew-side solver overlay (2026-07-25)

Done. Removed `strategy/meeting/solver.py` (1,261), `strategy/alibi.py` (242), their two
test files, `tools/analyze_solver_history.py`, the nine solver tests in
`test_meeting_modes.py`, all call sites in `modes/attend_meeting.py` / `__init__.py`,
the now-orphaned `KillAlibi` type and `Belief.alibi_state`, and the `CREWBORG_SOLVER*`
/ `CREWBORG_ALIBI` rows in `crewborg/README.md`. Superseded by `deduction/`, which won
the Phase-0 A/B. Suite: 549 passed / 13 skipped, with the same 15 environment-only
failures (missing `pytest-asyncio`, `spacy`) as before the change.

Nuance vs the original ask: `Belief.social_claims` / `meeting_history` /
`solver_counted_chats` were **kept** — `strategy/meeting/vote_policy.py` still reads
`social_claims`. They are dead weight if that experiment is also retired.
`strategy/suspicion.py` was kept as planned (impostor deflection needs it).

### Consume joint posterior in self-preservation movement (2026-07-22)

Added a separately gated movement consumer that leaves high-confidence
one-on-one threats for a fresh witness group, plus independently gated bounded
group-aware tasking. Neither defense writes conclusions back into deduction;
hosted effectiveness still requires a rotated-seat comparison.
