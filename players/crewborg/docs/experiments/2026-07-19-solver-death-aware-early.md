# Death-aware persistent early solve

## Hypothesis

The first early-chat candidate was precise but fired only three times in 100
hosted games because two supporting sources had to repeat their accusation in
the current meeting. Retained conclusions should remain usable in later
meetings, but the posterior must first incorporate the strongest fact revealed
between meetings: a player killed by an impostor was crew.

## Implementation

Hidden-kill victims learned from a body or the meeting census are hard-cleared
from the fixed-size joint impostor assignments. This does more than remove a
dead ballot target: it redistributes impostor mass and re-evaluates every old
speaker and claim under the smaller hypothesis space. Publicly ejected players
remain in the space because the game does not reveal their role.

The tick-240 pass recomputes after the current census and early utterances. It
requires `P>=0.76` and two distinct external attributed sources accumulated
across any meeting. Crewborg's own earlier chat is excluded from solver
evidence, preventing a prior derived line from amplifying itself. The early
line remains chat-only; the final deadline solve and ballot are still
recomputed independently.

## Offline gate

`tools/analyze_solver_history.py --decision-offset 240 --early-chat` replays
the production parser, kill/ejection provenance, hard constraints, source gate,
and solver over 12 retained hosted arms.

The threshold sweep rejected a proposed lower `0.65` gate:

| Minimum posterior | Correct / total | Distinct games |
| --- | ---: | ---: |
| 0.65 | 82 / 88 | 62 |
| 0.70 | 68 / 71 | 48 |
| 0.74 | 50 / 51 | 32 |
| **0.76** | **42 / 42** | **29** |

The retained `0.76` gate exposes 10/10 correct opportunities in the latest
200-game hosted history, compared with three actual lines from the old
current-meeting-only source gate. This is a precision/coverage gate, not an
outcome estimate; a fresh matched hosted A/B must confirm activation and team
ballot effects.

## Uploaded artifact and hosted test

Full production validation passed with 526 tests and 13 skips. The amd64 image
also completed the local Gate-1 episode cleanly with eight player logs, valid
results, and a replay.

Uploaded inert as `crewborg-solver-death-aware-early:v1`, immutable version
`594b8c5a-ac7d-45ff-9cc5-8b43bc69af2a`, from source `50a2ddb` and image
`sha256:4f795a8b1db65b34921adc26b34c46a6e8ae4314e70f9db4949e67e1120011c7`.
The upload enables the solver, early chat, full metrics, and all trace groups.
It has not been submitted to a league.

Fresh matched 100-game requests compare the prior early-public artifact against
this candidate with the same pinned roster and forced crew seat:

- Control: `xreq_a18d790d-a260-4125-90a6-cc791d51fb45`
- Candidate: `xreq_1ce942aa-8b2f-4a02-b04a-d79406b9db3b`

## Hosted result

Both requests completed 100/100 episodes with no failures. Crew wins were
42/100 control and 43/100 candidate (`p=1.0`), so this batch does not establish
an outcome lift.

The intended mechanism did activate. Actual tick-241 coordination lines rose
from 2 in control to 5 in the candidate; all five candidate targets were real
impostors, and crewborg's eventual ballot stayed on that target in all five
meetings. Four replay-reconstructed candidate lines used two or three killed
players as hard clears and evidence from two or three meetings; two had no
current-meeting ballot support at the early decision.

Team behavior moved in the intended direction:

| Metric | Control | Candidate |
| --- | ---: | ---: |
| Crew ballots targeting impostors | 189 | 222 |
| Crew ballots targeting crew | 127 | 102 |
| Impostor ejections | 9 | 15 |
| Crew ejections | 17 | 14 |

These are episode-clustered, unmatched behavioral counts rather than
independent trials. The defensible conclusion is that death-aware persistent
chat is reachable and precise; the 1-point win difference remains unresolved.
