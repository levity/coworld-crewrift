# Self-Preservation Movement

## Purpose

Reduce avoidable crew murders without contaminating deduction. The movement
policy consumes a current, pure joint-solver result but never appends movement
choices, targets, or inferred conclusions to the deduction history.

The motivating v2 300-game crew screen found that the subject was murdered in
172/300 games (57.3%), versus 49.2% across the six crew seats. At 65.1% of its
murders, only the killer was nearby. The fixed slot/color experiment cannot
prove that movement caused this gap, but it makes one-on-one exposure a testable
mechanism.

## Two Complementary Defenses

### 1. Isolation and pursuit escape

When all of the following hold, temporarily leave the one-on-one encounter:

- the agent is a living crewmate and `CREWBORG_SELF_PRESERVATION=1`;
- exactly one other living player has remained within 64 pixels for 12 ticks,
  with no current witness; and
- at least one other living player has a recently observed location.

The destination is a recently observed witness, preferring a larger cluster,
not an arbitrary direction away from the companion. If the companion falls
outside a 96-pixel pursuit radius, soft avoidance ends. If the companion stays
within that radius for another 12 ticks after avoidance starts, the encounter
is classified as pursuit. Pursuit escape remains latched until a non-threat
player is physically within the 64-pixel witness radius; temporary loss of the
threat or a stale destination does not resume tasking.

The joint posterior is used to avoid known threats as destinations and still
permits immediate escape from a pinned or high-confidence suspect. Proximity is
not solver evidence and never changes impostor probabilities. False alarms are
acceptable here because the response is movement toward witnesses, not an
accusation or ballot.

### 2. Group-aware tasking

When no player is a justified individual threat, task selection may prefer a
nearby incomplete task with recently observed group support, subject to a bounded
additional travel cost. It must fall back to the existing nearest reachable task
when there is no fresh group-supported option.

This handles unknown-risk isolation. It is distinct from suspect escape because
70 of the 172 observed murders were the first crew kill: a high-confidence
suspect-only controller cannot address those cases.

## Boundaries

- The solver remains a pure function of `DeductionHistory`.
- Derived movement state may cache a result or a short-lived route commitment,
  but is not solver evidence and is not lossily substituted for the history.
- Do not re-enable `tailing_self` under stick mode, feed escape behavior back
  into deduction, or treat a solo companion as an alibi.
- Preserve task completion as a hard objective; safety is a bounded bias, not
  permission to idle.
- Keep each defense independently environment-gated and traceable.

## Validation

1. Unit-test every gate, stale-target fallback, and hysteresis exit.
2. Gate 1 locally: ensure the mode connects, moves, and cannot freeze.
3. Upload with full telemetry and verify trace activation in hosted replays.
4. Use a matched hosted A/B with seat/color rotation. Measure murders, kills
   with only the killer nearby, task completion, score, and crew wins. Do not
   attribute the original fixed-slot gap to this policy without that control.
