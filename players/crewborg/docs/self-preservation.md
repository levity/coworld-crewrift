# Self-Preservation Movement

## Purpose

Reduce avoidable crew murders without contaminating deduction. Survival movement
is deliberately separate from the joint posterior and never appends its choices
or targets to deduction history.

The motivating v2 300-game crew screen found that the subject was murdered in
172/300 games (57.3%), versus 49.2% across the six crew seats. At 65.1% of its
murders, only the killer was nearby. The fixed slot/color experiment cannot
prove that movement caused this gap, but it makes one-on-one exposure a testable
mechanism.

Three hosted experiments found that broad reactive flight is harmful. Immediate
repulsion, delayed pursuit, and delayed witness-seeking all increased murders,
task interruption, or both. Equal-speed movement does not open a gap after a
killer is in range, while role-neutral triggers mostly target ordinary crew.

## Two Independent Defenses

### 1. Current-witness-only movement

Tasking is preempted only while all of the following hold:

- the agent is a living crewmate and both `CREWBORG_DEDUCTION_HISTORY=1` and
  `CREWBORG_SELF_PRESERVATION=1` are enabled;
- exactly one other living player has remained currently visible within 64
  pixels for 12 continuous ticks; and
- a third living player is currently visible and supplies a recomputed
  destination.

If there is no current witness, normal or stick behavior continues. There is no
blind repulsion and no retained destination. Movement ends immediately when the
risk radius contains zero or at least two other players, or when the witness is
no longer current.

Continuous exposure is traced as `pursuit`, but that label is telemetry only.
Proximity and flight never change impostor probabilities.

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
- The witness goal is derived again from current geometry every tick. It must
  not retain a destination after the geometry changes.
- Do not re-enable `tailing_self` under stick mode, feed escape behavior back
  into deduction, or treat a solo companion as an alibi.
- Witness seeking may interrupt an in-progress task. The action layer resets
  partial task progress when movement begins; tasking resumes through the normal
  policy as soon as its gates clear.
- Keep each defense independently environment-gated and traceable.

## Validation

1. Unit-test every gate, dynamic goal update, navigation fallback, and exit.
2. Gate 1 locally: ensure the mode connects, moves, and cannot freeze.
3. Upload with full telemetry and verify trace activation in hosted replays.
4. Use a matched hosted A/B with seat/color rotation. Measure murders, kills
   with only the killer nearby, task completion, score, and crew wins. Do not
   attribute the original fixed-slot gap to this policy without that control.
