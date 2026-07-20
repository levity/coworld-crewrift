# Crew strategy principles

High-level principles from competitive Among Us research, plus the local
evidence that confirmed or falsified each. Reference doc, not a plan. Each
principle names the code that does or does not implement it.

## 1. Parity-awareness (two-sided)

Impostors win when `impostors >= crew`. With 2 impostors that is **2 crew left**.
A wrong eject removes a crew body *and* leaves both impostors alive, so it
closes the gap twice as fast as a skip does.

| State | Wrong eject → | Consequence |
| --- | --- | --- |
| 6c/2i | 5c/2i | Cheap, recoverable |
| 5c/2i | 4c/2i | Recoverable |
| 4c/2i | 3c/2i | One kill from losing |
| 3c/2i | 2c/2i | Loses on the spot |

The threshold for ejecting should therefore be **a function of alive counts**,
not a constant. Critically it is **not monotonic**: at 3c/2i skipping also
loses (one kill reaches parity anyway), so the bar rises through the midgame
where a wrong eject is uniquely expensive, then falls again at the edge where
passive play is a guaranteed loss and a 65% shot beats certain death. Crews
lose games by reflexively skipping just as they lose them by overvoting.

The real question is not "is P above 0.65" but "given crew/impostor counts,
expected kills before the next meeting, and task-bar progress, does ejecting at
confidence P beat skipping."

**Ejections are unconfirmed, which makes a wrong eject strictly worse than the
generic Among Us analysis assumes.** Crewrift Prime is "confirm ejects: OFF"
(see §7). With confirmation, a wrong eject at least buys information — the crew
learns the pool did not shrink and re-bases. Here it buys *nothing*: you lose a
body, step toward parity, and no belief is corrected. The error is silent and
uncompensated, so the eject bar should sit higher than external guides suggest.

**Status in code:** absent for crew. `base_probability = imposter_count /
len(players)` (`strategy/meeting/solver.py:539`) conditions the *belief* on the
roster, which is not the same thing — the *decision thresholds*
(`CREWBORG_SOLVER_P`, the two-source rule, the tick-360 stability check) are
static constants that never reference alive counts. Note the asymmetry:
`parity_closing_vote_target` exists and is used on the **impostor** path only
(`modes/attend_meeting.py:416-427`, `path="parity_push"`). crewborg understands
the parity boundary well enough to exploit it offensively and not at all
defensively.

## 2. Clear innocents; don't hunt impostors

The dominant pro-vs-naive skill gap. Winning crew shrink the suspect pool by
hard-clearing innocents and let elimination isolate the residue. Naive crew
accuse. crewborg is accusation-first by default: it emits a prose accusation
naming its top suspect (`modes/attend_meeting.py:141-180`,
`strategy/accusation.py`) and has no vocabulary for clearing anyone.

## 3. Hard evidence and soft evidence are different kinds

**Hard** (near-certain, worth spending a vote on): witnessed vent or kill,
continuous co-presence across a kill window, a body's location/timing
contradicting a claimed position, a common-task contradiction.
**Soft** (shifts suspicion, never sole vote driver): self-report patterns,
task-panel dwell times, task-bar timing, stack ambiguity.

Conflating them is how crews talk themselves into wrong ejects. The codebase
gets this right in one place worth preserving: `_constraint_forces_candidate`
requires a source-free pick to appear in *every* hypothesis surviving the hard
structural facts alone, and explicitly excludes weighted `clears` as logical
exclusions.

## 4. Pool observations; the transcript is the shared memory

Crew instances share nothing out-of-band (one websocket each, no IPC). All
collaboration must survive a round trip through public chat. The upside is that
every hard deduction above fits in ≤160 chars, so the bandwidth cost of
broadcasting the one or two most load-bearing facts is trivial relative to the
inference it unlocks in five other agents.

crewborg already *parses* inbound chat into structured claims every tick
(`strategy/social_evidence.parse_social_claims` → `belief.social_claims`), and
the joint solver already fuses claims + votes + alibi + pins. That machinery is
gated behind `CREWBORG_SOLVER`, confined to the vote, and never writes base
belief.

## 5. Converge votes; ties save impostors

With 2 impostors, split crew votes let a tie preserve both. Convergence on a
single highest-confidence target is a pure policy property costing no
bandwidth. Tournament scoring encodes the same incentive: +1 correct vote,
−1 wrong vote, 0 abstain.

## 6. Only build on evidence the client actually exposes

Hard-won locally, and the principle that governs the rest. A "watched task
clear" is a textbook hard clear in human play and is **unavailable here**: the
client exposes only a *global task decrement*, not completer identity.

Evidence: `crewborg-solver-stick-alibi:v4` (`CREWBORG_SPEAK_CLEARS=1`) A/B tied
47–47 (`p=1.0`); exact reconstruction found **392/550 inferred player
completions wrong, 258 credited to impostors**, and 47 of 88 emitted target
mentions named actual impostors. Broadcasting inferred clears fed the crew
poison. Rejected; the private task-clear input was removed too.

Related: co-presence alibis currently fire almost never —
`crewborg-pair-audit-close:v1` reconstruction found two singleton events and
**zero pair exclusions**, and screen-visibility is an unsound proxy for physical
co-presence (retained histories show screen-visible actual killers at 61-68
pixels). A principle that is sound in theory can be inert or actively wrong at
the observation layer. Verify the sensor before building inference on it.

## 7. Death carries information; ejection does not

Two facts from the simulator source, both certain and both free:

**Ejections reveal nothing.** `VoteResult` renders exactly one sprite — the
ejected player's ordinary icon (`global.nim:1683`
`addProtocolVoteResultActorSprites` → `playerIconSpriteId`, built only from
color and join order). `applyVoteResult` (`sim.nim:3624`) flips `alive=false`,
clears bodies and chat, teleports everyone home. No role is broadcast anywhere.
Contrast the start-of-game `RoleReveal` icons (`9500+`), which *do* encode role.
So an ejected player **must remain a live impostor hypothesis**.

**Killed players are provably crew.** `tryKill` skips any candidate with
`role == Imposter` (`sim.nim:2924`), so impostors cannot be killed. Any death
with `death_source in ("body", "census")` is therefore a *logically certain*
crew clear — the strongest evidence class in the game, requiring no observation
skill, only noticing how someone died.

**Status in code — half right.** The solver correctly keeps ejected players in
the hypothesis space: it enumerates assignments "over the original roster,
including dead players" (`strategy/meeting/solver.py:3-4`), and builds its
player list with no alive filter (`solver.py:628`). Dead players are excluded
only from *vote candidates* (`solver.py:512-523`), which is right — you can only
vote for the living.

But it never reads `death_source`; grep finds zero uses in `solver.py`. So the
kill-clear is unused. Concretely: 8 players minus self = 7, `C(7,2)` = 21
hypotheses. After two kills, two of those seven are provably crew, so the sound
space is `C(5,2)` = 10. **The solver carries 11 logically impossible hypotheses
— over half the space — excluded by a fact already sitting in
`belief.roster[color].death_source`** (`strategy/alibi.py` already reads exactly
this field, `_KILL_SOURCES = ("body", "census")`).

This is the mirror image of the §6 failure: task clears were *unsound evidence
being used*; kill clears are *sound evidence going unused*. It is also the rare
candidate that passes §6 cleanly — observable, already tracked, and certain
rather than inferred.
