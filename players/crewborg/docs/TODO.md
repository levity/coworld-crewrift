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

### Test sustained pursuit as solver evidence (2026-07-22)

The memoryless repulsion controller records continuous one-on-one exposure and
labels it `pursuit` after 12 ticks for telemetry only. Use hosted traces to test
whether duration, closing velocity, distance band, and persistence after route
changes distinguish impostors from crewmates. Only add an immutable pursuit
event and solver weight if the signal generalizes out of sample. Ordinary
proximity or the fact that crewborg fled must never create suspicion.

### Add map-aware possible-killer constraints to the pair ledger (2026-07-20)

Per-kill close co-presence is sound but too sparse to exclude pairs by itself,
and a singleton cannot be weighted toward crew because non-killing impostors
often stay with the group. Extend `KillAlibi` or add a sibling immutable event
that retains the victim's last-known position/time, its reachable map region,
and each player's tracked reachable region over the death window. Exclude a
pair only when neither member could have intersected the victim. Keep the raw
geometry and timing in the audit trail; any derived possible-killer set must be
recomputable when tracking assumptions change. Validate reachability against
known replay killers before permitting solver impact.

### Give the solver a prior that excludes evidence it scores structurally (2026-07-19)

`belief.suspicion` is a useful legacy posterior for field behavior and meeting
fallbacks, but its fitted features include chat accusations and attributed
votes. The joint solver then uses that scalar as a prior while also scoring the
same observations as structured claims and meeting records. Expose a residual
prior that excludes every channel modeled explicitly by the solver, including
claims, ballots, witnessed pins, task clears, death clears, and alibis; physical
features such as witnessed kills are not automatically non-overlapping. Leave
the full posterior intact for existing consumers. Audit pick changes against
retained or newly generated replay history before enabling it.

## Done

### Consume joint posterior in self-preservation movement (2026-07-22)

Added a separately gated movement consumer that leaves high-confidence
one-on-one threats for a fresh witness group, plus independently gated bounded
group-aware tasking. Neither defense writes conclusions back into deduction;
hosted effectiveness still requires a rotated-seat comparison.
