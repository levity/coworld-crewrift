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

### 1. Suspect escape

When all of the following hold, temporarily leave the one-on-one encounter:

- the agent is a living crewmate and `CREWBORG_SELF_PRESERVATION=1`;
- exactly one other living player is currently nearby, with no current witness;
- that companion has a sufficiently high marginal in the current joint
  posterior, or is structurally pinned; and
- a recently observed destination contains at least two other living players.

The destination is that group, not an arbitrary direction away from the
companion. The controller holds its choice briefly and exits when a witness is
present, the threat is no longer nearby, the destination becomes stale, or the
commitment expires. This prevents task/flee oscillation and avoids navigating
toward old sightings.

The posterior threshold must be conservative. A nearby player is not evidence
of impostor status, and a single companion is not a safe witness. The movement
controller must not use a legacy scalar suspicion when the deduction-history
path is enabled.

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
- Do not flee from every nearby player, re-enable `tailing_self` under stick
  mode, or treat a solo companion as an alibi.
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
