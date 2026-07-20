# Crew collaboration: speak witnessed task clears

## Direction

Crewborg already detects watched real-task completions, parses source-attributed
defenses, and fuses them in the joint solver. The missing link is emission:
crewborg talks about suspects but never publishes its strongest exculpatory
fact for teammates to use.

The broader collaboration design also proposed publishing co-presence alibis.
That cannot use an ordinary `blue clear` sentence. With two impostors,
co-presence for one kill proves only that blue was not that killer; blue may
still be the non-killing partner. Publishing it soundly requires a per-kill
relational claim and source-reliability model. Keep that separate.

## First treatment

Add one default-off flag, `CREWBORG_SPEAK_CLEARS=1`.

- A living known crewmate may send one meeting-start line naming up to two
  living players for whom it observed a real task completion.
- Use the terse deterministic form
  `blue clear and green clear: saw tasks complete`. The production parser
  reads each target as a direct `defend` claim with `sighting` provenance.
- The line is chat-only. It does not stage a vote, lower a solver threshold,
  alter parity policy, or publish co-presence alibis.
- Default-off behavior remains unchanged. Impostors and dead/unknown-role
  players cannot use the path.
- Repeat the fact in later meetings so external policies that do not persist
  transcripts can still consume it; the joint solver's existing cross-meeting
  repeat decay prevents independent-evidence multiplication.

## Reachability

A conservative objective-replay reconstruction requires the subject to see
another crew player's full final 56 task ticks and the completion:

| Fresh constraint A/B history | Watched completions | Games with any | Before first meeting |
| --- | ---: | ---: | ---: |
| Control v2 | 338 | 92/100 | 280 in 84 games |
| Candidate v3 | 335 | 91/100 | 250 in 77 games |

The runtime detector additionally requires an unambiguous one-step HUD task
decrement, so actual emission may be lower. The feature should nevertheless be
common enough for a 100-game hosted mechanism test.

## Evaluation

Compare constraint-aware v3 control against the same source plus
`CREWBORG_SPEAK_CLEARS=1`, with all other flags and the exact fixed roster held
constant.

Primary mechanism checks:

- actual clear lines and parsed target correctness;
- target ballot/ejection rates for players crewborg cleared;
- crew-team impostor/crew ballots and ejections;
- subject vote precision and coverage;
- crew wins and non-win score.

Do not add a parity gate in this treatment. It would confound whether sharing
trusted information helps the team.

## Hosted result

The premise failed. Candidate v4 tied v3 at 47/100 wins, but 47 of 88 public
clear mentions named a fixed impostor. Exact runtime-detector reconstruction
found only 158/550 player attributions correct and 258 credits assigned to
impostors. The client exposes a global task decrement, not another player's
completion identity, so task-site coincidence cannot support an individual
clear.

The candidate is rejected and its source path removed. The same unsound signal
was also removed as a private solver clear; the fitted schema field remains
present but stays zero. Full analysis:
`2026-07-19-speak-clears-hosted-ab.md`.
