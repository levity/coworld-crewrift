# Speak-clears hosted A/B

## Treatment

Source `cdd7688` added a default-off meeting-start line that published up to
two players with `tasks_completed_watched > 0`. It was uploaded inertly as
`crewborg-solver-stick-alibi:v4`
(`af8623ba-4233-4b8d-8802-7e7d0a21028c`) with the exact v3 solver, stick,
alibi, early-chat, and telemetry configuration plus
`CREWBORG_SPEAK_CLEARS=1`. It has not been submitted.

The intended premise was that a one-step global task-count decrement, coincident
with exactly one visible player's long task-site dwell, identified that player
as the completer. The hosted run tests both whether that premise holds and
whether publishing the inferred clear changes team behavior.

## Hosted design

Two fresh 100-game requests used Crewrift 0.1.59, the same fixed roster,
subject crew at slot 0, and fixed impostors at purple slot 6 and cyan slot 7.
Only the subject version differed.

- Control v3: `xreq_9c53f4dc-751b-4038-97a5-fa0e158e2ff6`
- Candidate v4: `xreq_53791cf1-21cf-4623-a325-b41d6a27e6bd`

Both completed 100/100 without hosted failures. The hash-complete warehouses
contain 5,237,820 control and 5,291,666 candidate events.

## Outcome

Authoritative XP score rows give:

| Metric | Control v3 | Candidate v4 | Change |
| --- | ---: | ---: | ---: |
| Crew wins | 47/100 | 47/100 | 0.0pp |
| Mean subject score | 53.73 | 53.66 | -0.07 |
| Mean score in losses | 5.79 | 5.74 | -0.06 |
| Subject completed tasks | 767 | 759 | -8 |
| Subject standing penalties | 94 | 93 | -1 |

Fisher exact `p=1.0`; the Newcombe 95% interval for the win difference is
approximately -13.6 to +13.6 points. There is no outcome signal.

Meeting behavior moved favorably but cannot be attributed across two fresh
unpaired histories:

| Meeting metric | Control v3 | Candidate v4 |
| --- | ---: | ---: |
| Voting phases | 146 | 148 |
| Subject votes: impostor / crew | 21 / 11 | 23 / 9 |
| Crew-team votes: impostor / crew | 210 / 101 | 239 / 109 |
| Impostor / crew ejections | 9 / 10 | 16 / 11 |

## Mechanism audit

The candidate emitted 65 clear lines in 65 meetings across 43 games, always at
meeting age one tick. Those lines contained 88 target mentions:

| Target role | Mentions |
| --- | ---: |
| Fixed impostor | 47 |
| Crew | 41 |

Cyan, a fixed impostor, was named 44 times; purple, the other fixed impostor,
was named three times. Twenty-nine games publicly cleared at least one
impostor. Other crew mostly overrode these statements: in the same meetings
they cast 39 votes at the cleared impostors versus three at cleared crew and
ejected two cleared impostors.

An exact reconstruction of the runtime detector over candidate objective
replays explains the failure:

| Inferred runtime credits | Count |
| --- | ---: |
| Total | 550 |
| Correct player attribution | 158 |
| Wrong player attribution | 392 |
| Credited to an impostor | 258 |
| Games with any wrong credit | 90/100 |
| Games crediting an impostor | 70/100 |

The 71.3% attribution error is structural. The client exposes the global
`crew_tasks_remaining` count and other players' positions, but not another
player's active task or completion. An impostor can dwell at a task site while
an unseen crewmate completes elsewhere; the global decrement is then falsely
assigned to the visible impostor.

The offline fitted feature did not validate this runtime approximation.
`suspicion_lab/tools/features.py` directly checks the replay ground truth:
`completion.slot == suspect`. That is why the training rows contained zero
impostor completions. Runtime task-site coincidence and offline completer
identity are different observables.

## Warehouse reliability audit

This run also exposed three analysis-contract errors:

1. XP `results` and policy-log routes can be unavailable while `episode.json`
   and replay are complete. The downloader's documented best-effort artifacts
   were nevertheless treated as completeness requirements, causing three
   identical retries.
2. The warehouse wrapper silently ignored replay-complete episode directories
   without `results.json`, even though authoritative slot-aligned XP scores and
   forced roles were present in `episode.json`.
3. Raw XP reward scores are not a per-player win predicate. A `+100`
   WinReward identifies the winning role; penalized teammates may finish below
   100 and still win.

The corrected downloader retries only a missing requested replay and writes
`artifact_status.json` for optional failures. The warehouse wrapper validates
contiguous participant slots, exact score-policy alignment, and forced roles
before staging a minimal transport result. A WinReward-sized score assigns the
win to that entire role; no such score means no winner. It never changes
downloaded artifacts. The warehouse worker fills synthesized task and kill
dimension values from objective replay events.

## Decision

Reject v4 and do not submit it. Remove public task-clear emission and stop
using the inferred completion as a private solver clear. Keep the fitted-model
field at zero for schema compatibility until the observation protocol exposes
a direct per-player completion signal. The v3 artifact remains the hosted
baseline.
