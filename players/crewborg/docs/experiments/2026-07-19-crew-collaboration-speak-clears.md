# Crew collaboration: speak &amp; fuse your clears

High-level design note. No code yet — this records the direction and the first
spike so the reasoning survives a context reset.

## Motivation — crewborg plays like *naive* crew

Competitive Among Us crew win by **clearing innocents and pooling observations**,
not by accusing. The dominant pro-vs-naive skill gap is that strong players
focus on clearing players innocent and running process-of-elimination over the
*combined* pool of everyone's sightings; weak players reason solo and shout
suspects. The single highest uplift-per-unit-of-chat-bandwidth tactic is
broadcasting co-location alibis so the crew builds clear-clusters and isolates
the residual suspect.

crewborg today does the opposite:

- By default a crewmate emits an **accusation** naming its top suspect
  (`strategy/meeting/attend_meeting.py:141-180`, `strategy/accusation.py`) and
  **never speaks a clear or an alibi**. It *computes* co-presence alibis
  (`strategy/alibi.py`) and self-watched clears (`strategy/meeting/solver.py:635-645`)
  and then discards them privately. That is textbook accusation-first naive play.
- A teammate's strongest report cannot make a listener act. If A witnesses red
  vent (A's own `vent_use` event → near-certain), A can only *say* "red sus".
  In B's world that line is downgraded to a weak `times_accused += 1` scalar, or
  at best a decayed probabilistic claim. The near-certainty floor is reserved
  strictly for the bot's own eyes (`strategy/suspicion.py:528-537`). Reported
  sightings never enter B's event log or base posterior.
- The content-aware fusion engine **already exists and already runs every tick**:
  `strategy/social_evidence.parse_social_claims` folds inbound chat (including
  relays like "yellow saw cyan vent") into `belief.social_claims`, and the joint
  solver already fuses claims + votes + alibi + pins. But it is **quarantined
  behind `CREWBORG_SOLVER` (default off), confined to the vote pick only, never
  writes base belief, and is never shown to the meeting LLM.**

So this is not a greenfield "build collective reasoning" project. The fusion
machinery is built but unplugged, and the emit side is impoverished (accusations
only, no clears). That makes the ROI unusually high: we are completing and
unlocking existing code, not writing a reasoner from scratch.

## Principle

Turn six isolated reasoners into one collective detective:

1. Each crew bot **emits its 1-2 hardest observations as terse structured chat**.
2. Every bot **folds all emitted facts into a shared clear/suspect set** via
   elimination.
3. Votes are **gated on a parity-aware confidence floor with convergence** on a
   single target.

The meeting transcript *is* the shared memory; no out-of-band channel is needed
(and none exists — one websocket per instance, no IPC).

## Leverage ranking (meta leverage × implementation effort)

| Move | Leverage | Effort | Notes |
|---|---|---|---|
| Speak clears/alibis + fuse them | highest (best uplift/bandwidth) | low-med | Emit vocabulary already parseable; alibi/clear already computed. Attacks the 3-crew/2-imp parity-stall loss directly. |
| Un-quarantine the existing solver (default-on; feed marginals to vote/LLM) | high | low | Machinery already runs each tick; wire the output. |
| Propagate strong *relayed* catches (vent/kill) to gameplay / near-certainty | high (hard convicts) | med | Lets a listener avoid/hard-vote on a teammate's witnessed vent. |
| Parity-aware vote convergence (default-skip under floor, converge on one target) | high | low (pure policy) | Near-zero bandwidth; prevents self-inflicted wrong-eject losses toward 2v2. |
| Structured broadcast primitive (rich claim vocabulary) | high | high | Stable serialize/parse contract; defer. |

## Proposed first spike — "Speak &amp; fuse your clears"

One flag (`CREWBORG_SPEAK_CLEARS`, default-off, byte-identical when off — same
house style as `CREWBORG_ALIBI` / `CREWBORG_SOLVER` / `CREWBORG_STICK`).
Deterministic (LLM off), so it A/Bs cleanly against every prior experiment.

1. **Emit** — when a crewmate holds a hard clear (self-watched task/visual
   completion of another player) or a co-presence alibi, verbalize it as a terse
   line the *existing* parser already ingests as a `defend` / `at_least_one`
   sighting claim: `w/ blue Elec all round`, `cleared pink, watched task`. This
   is the only genuinely new code, and it is the substantive change: it converts
   crewborg from accusation-first to elimination-first by giving voice to facts
   it already computes.
2. **Fuse** — use the already-built joint solver as the ingestion engine. A
   relayed clear becomes another instance's exclusion set, exactly like
   `alibi_groups` today. Six crew now triangulate a shrinking suspect pool
   instead of each shouting one suspect.
3. **Guardrail** — add the parity-aware convergence gate so shared clears
   translate into converging on the residual suspect rather than overvoting. A
   wrong eject moves the crew toward 2v2 parity for free, so raise the conviction
   threshold as player count drops and default to skip under the floor.

**Why clears first:** highest meta-leverage at lowest effort, and clears are the
*safe* class to start with — a bad shared clear mildly widens the suspect pool,
whereas a bad shared convict directly risks parity. Clean A/B target: the
3-crew/2-imp parity-stall loss bucket.

## Cheap precursor probe (optional)

Before adding the emit side, flip `CREWBORG_SOLVER` on in an A/B to confirm
claim-fusion moves win-rate *at all* with today's thin, accusation-only claim
stream. If it barely moves, that is positive evidence that the bottleneck is
emit quality (the impoverished claim stream) — which is exactly what the spike
fixes.

## Measurement

All-crewborg lobbies, LLM off (consistent with every prior experiment). Primary
metric: crew win-rate. Watch the 3-crew/2-imp parity-stall loss bucket
specifically. Keep the flag off by default so control runs are byte-identical.
