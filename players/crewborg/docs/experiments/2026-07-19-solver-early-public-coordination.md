# Early public-solver coordination

## Hypothesis

The confirmed solver often reaches an accurate conclusion but communicates it
at tick 1,152, after the fixed-roster crew have cast their first ballots around
tick 300. A public-evidence-only solve at tick 240 can redirect those ballots
without sacrificing the final solver's full evidence window.

## Design

Run the production parser and correlation-aware solver at meeting tick 240.
For this early chat only, exclude private suspicion priors, witnessed-impostor
pins, and watched-task clears. This keeps hosted inference identical to the
public replay gate.

Select the chat gate on the six correlation, timing, and confirmation arms.
Hold out both guidance experiments and the fresh crowd-cap A/B.

The utterance may fire once per meeting and must not stage a vote. The ordinary
tick-1,152 solver still recomputes the final ballot from all public and private
evidence.

Separately, react whenever another player casts a ballot against crewborg's
known-crewmate identity. That defense is logically certain, not solver-fitted,
and also leaves the final ballot untouched. Five of the 22 crew ejections in
the fresh A/B targeted the subject itself.

## Offline result

At tick 240, the ordinary decisive region contains 109/116 correct picks on the
six selection arms. Requiring a top marginal of at least `0.76` and two distinct
attributed sources in the current meeting retains 29/29.

The pre-registered gate also retains 29/29 on the four historical guidance
holdouts plus the fresh 200-game crowd-cap A/B. Pooled precision is therefore
58/58 across 1,584 eligible meetings.

This is a precision and timing gate, not an outcome estimate. Hosted evaluation
must show that the chat path fires, does not increase crew-target ballots or
crew ejections, and does not reduce useful impostor ejections.

## Implementation and local gate

The feature is disabled by default and enabled by
`CREWBORG_SOLVER_EARLY_CHAT=1`. At tick 240 it computes a public-only report,
latches the attempt whether or not the gate opens, and sends at most one line
citing two attributed sources. It does not set a tentative vote or mark the
final accusation as sent. The ordinary tick-1,152 path recomputes with all
available public and private evidence.

The same flag also enables one self-defense response after a public ballot
against crewborg's known-crewmate identity. The response asks the field not to
pile and to skip; it never stages a counter-vote. If it consumes the chat
opportunity at or after tick 240, the calibrated early solve is suppressed.

The exact implementation reproduces the pre-registered 29/29 selection and
29/29 held-out targets. Validation:

- 68 focused meeting, solver, and parser tests passed.
- The production-image suite passed with 526 tests and 13 skips.
- Changed-file Ruff and `git diff --check` passed.
- Local `scn_vote_basic` Gate 1 exited cleanly with valid result and replay
  artifacts and zero vote, connect, or disconnect timeouts.

The local scenario has a short meeting clock and therefore exercises the
deadline path rather than tick 240. Focused tests and exact history replay
cover the timed early branch. Hosted evaluation must confirm runtime
`solver_early_chat` and `solver_self_defense` events before interpreting any
scoreboard delta.
