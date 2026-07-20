# Append-only deduction history

`CREWBORG_DEDUCTION_HISTORY=1` enables a parallel crewmate deduction path. It
replaces both the legacy per-player suspicion scalar and
`strategy/meeting/solver.py` for evidence collection and meeting decisions.
The flag is off by default.

The old implementation and experiment notes remain useful sources of
hypotheses and edge cases. They are not dependencies or ground truth. The new
path independently validates each retained idea against a smaller data model,
focused tests, synthetic histories, and historical public replay.

## Boundary

Runtime code has one impure responsibility: append exact observations to
`belief.deduction_events`. Everything after that boundary is pure:

```text
DeductionHistory
  -> derive_evidence(history)
       -> parsed claims + ballots + direct facts + kill constraints
  -> build_assignment_table(history, evidence)
       -> complete viable/excluded role assignments
  -> score_assignments(table)
       -> factor contributions + normalized joint posterior
  -> decide_from_inference(history, posterior, live_targets)
       -> parity-aware eject/skip decision + explanation
```

`infer()` and `decide()` remain convenience wrappers around those explicit
stages. No stage accepts `Belief`, a suspicion value, a previous solver result,
or a cached conclusion. Rerunning after a parser or likelihood change
reinterprets the complete original input. A likelihood-only sweep can reuse an
assignment table; evidence-weight or correlation changes rerun the cheap
derivation stage from exact history.

For a crewmate with the flag enabled, the runtime:

- continues ordinary perception and agent-location tracking;
- appends the new history;
- clears `belief.suspicion` and `belief.believed_imposters`;
- does not run the legacy player event log, alibi accumulator, social counters,
  or suspicion model; and
- routes crew meetings around both the meeting LLM and old solver.

The flag is deliberately role-scoped. Impostors retain the complete legacy
event, suspicion, movement, and meeting path, which prevents a crew-solver
experiment from changing both role policies. The unflagged path is unchanged.

## Retained inputs

`deduction/model.py` defines the frozen history:

| Input | Retained data |
|---|---|
| `GameSpec` | original player colors, self color and known role, known impostor teammates when applicable, impostor count |
| `WorldObserved` | tick, self position, visible players and bodies, fully visible vent regions and their occupants |
| `TaskCounterObserved` | task count only when it changes |
| `UtteranceObserved` | exact text, speaker, meeting, and observation tick |
| `VoteObserved` | voter, target or skip, meeting, and observation tick |
| `MeetingObserved` | meeting identity, caller, and body/button kind |
| `DeathObserved` | color, learned tick, body/census/ejection source, and body position when available |

The ledger stores observations, not `SocialClaim`, `KillAlibi`, witnessed-action
pins, or player suspicion. Those are conclusions and are rebuilt each solve.
Continuous world frames are retained because absence and co-presence are
meaningful only across an unbroken observation window.

## Inference

`deduction/inference.py` enumerates every fixed-size impostor assignment over
the original roster. For a known crewmate, self is absent from that table.

Structural facts remove assignments:

- a body/census death removes the murdered player; an ejection does not reveal
  role and remains in the role table;
- a unique adjacent actor when a player becomes a body pins that actor;
- a player absent from the preceding complete player frame who appears inside a
  vent visible on both frames, or disappears from such a vent, is pinned; and
- continuous close co-presence for one hidden kill excludes only an assignment
  in which no eligible member could have made that kill. It never clears one
  player globally.

Public text is reparsed on every solve. Claims are role-conditioned inside each
hypothesis, so an assignment that makes the speaker an impostor expects
deflection and partner protection rather than treating the statement as
crew-authored evidence. Claims deduplicate by meeting/source/stance/target.
Repeated relations across meetings and additional same-meeting sources receive
diminishing weight. Relays retain both the current speaker and attributed
source. Ballots are weaker evidence and repeated voter-target pairs decay.

Exact utterances remain in history when their current interpretation is
ignored. Two explicit soundness guards are:

- “X was with me” is not compressed into a unary clear; and
- “I saw X near the vent” is not promoted to witnessed vent use.

Every active or ignored derived item has a stable evidence ID and reason. Every
surviving assignment carries the individual log-likelihood contributions, and
every removed assignment lists its structural exclusions.

The final hosted trace includes every surviving assignment's factor IDs,
likelihoods, and weights, not only the winning assignment. It also records
history counts by event kind, active evidence counts by channel, solve latency,
and remaining meeting time. That is sufficient to rescore the observed factor
table locally without asking the hosted game to run again.

## Decision policy

`deduction/decision.py` is separate from inference. A strong posterior does not
automatically spend a vote.

The ordinary eject bar is `P >= 0.65`, with at least `0.10` separation from the
best candidate outside the available impostor slots. A target also needs either
a structural proof or at least two independent public actors supporting it.
The risk bar is board-aware:

- where a wrong eject creates a one-kill loss but a skip does not, require
  `P >= 0.80`;
- at the edge where one kill after a skip reaches parity anyway, lower the bar
  to `P >= 0.51`; and
- otherwise use the ordinary bar.

At meeting tick 240, a decisive result may be shared as provisional chat; a
very low live marginal may be shared as a soft clear. No ballot is committed
there. The final decision is rebuilt from the full history at the 48-tick
deadline backstop, after most utterances and ballots are available.

## Cheap evaluation

The production functions can be evaluated without the game engine:

```sh
# Seeded semantic histories
PYTHONPATH=players/crewborg:players/crewborg-aaln:. \
  python players/crewborg/tools/evaluate_deduction.py --games 1000 --seed 7

# Existing public event warehouse
PYTHONPATH=players/crewborg:players/crewborg-aaln:. \
  python players/crewborg/tools/evaluate_deduction.py \
  --warehouse /tmp/source-backed-commitment-ab-wh --samples 3

# Labeled exact histories
PYTHONPATH=players/crewborg:players/crewborg-aaln:. \
  python players/crewborg/tools/evaluate_deduction.py \
  --history-jsonl histories.jsonl
```

JSONL rows contain `history` as a serialized `DeductionHistory`, the true
`imposters`, and optional `live_targets`.

Synthetic evaluation checks invariants and cheap policy sensitivity; it is not
a game-result estimate. Historical warehouse replay uses exact public chat,
votes, deaths, and roles, but older warehouses do not contain the new
first-person world stream. It therefore leaves private witness and co-presence
channels absent rather than reconstructing them from privileged replay state.

Warehouse output includes posterior calibration buckets and a fixed
base/danger threshold sweep. Across the six current, non-overlapping retained
batches, the default thresholds make 63/73 correct eject decisions (86.3%).
Raising the thresholds to 0.70/0.85 makes 47/54 correct (87.0%); lowering them
to 0.60/0.75 makes 90/109 correct (82.6%). This supports keeping the current
policy for the first hosted test rather than fitting a threshold to reused
games.

Twenty thousand dense world frames with seven visible players benchmark at
about 79 MB maximum RSS and 81 ms for inference on this VM. Frozen slotted
player/body/vent values reduced the same benchmark from about 140 MB and cut
construction time from 0.81 seconds to 0.35 seconds. Readable color identities
remain strings; integer enums would add a mapping boundary while targeting a
smaller cost.

## Current limits

- The natural-language parser is deterministic and deliberately incomplete.
  Unrecognized text is retained for later parser versions.
- Task-counter changes have no actor identity and never clear a player.
- Body-location contradictions and map-reachability kill windows are not yet
  extracted.
- The new deduction path is crewmate-only. Impostors intentionally remain on
  the complete legacy policy.
- Thresholds and likelihoods have offline evidence, not a hosted A/B for this
  complete parallel path. The feature remains off by default.
