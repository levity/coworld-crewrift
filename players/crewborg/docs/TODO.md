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
