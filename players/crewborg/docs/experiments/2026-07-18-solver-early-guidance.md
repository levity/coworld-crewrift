# Early solver guidance

## Hypothesis

The confirmed solver usually waits until tick 1,152 to calculate, speak, and
vote. That preserves evidence quality but leaves too little time for other
players to incorporate its conclusion. A one-shot conclusion at tick 1,000 can
improve team coordination if it is restricted to a higher-precision region and
does not commit crewborg's own final ballot.

## Pre-implementation experiment

Instrument: replay the seven hash-complete retained solver warehouses at
multiple meeting cutoffs using the production parser and public-evidence
solver. Measure pick precision, source breadth, and visible ballot support.

If true:

- a useful set of decisive picks exists at tick 1,000;
- a conservative gate can exclude every retained false pick;
- the final tick-1,152 recomputation remains independent.

If false:

- early precision is materially worse or useful coverage collapses;
- proposed safety signals remove correct picks before errors;
- the implementation is abandoned before upload.

Decision rule: implement only if the chosen early region has no retained false
picks and at least ten correct opportunities. In a fresh hosted A/B, retain the
candidate only if its guidance trace fires, impostor ejections increase, crew
ejections do not increase, and the crew-win result is not adverse.

## Offline result

Across 858 eligible meetings:

| Cutoff | Ordinary decisive picks | `P>=0.80`, 2+ sources, <=2 ballots |
| --- | ---: | ---: |
| 960 | 101/112 (90.2%) | 20/21 (95.2%) |
| 1,000 | 101/114 (88.6%) | 20/20 (100.0%) |
| 1,050 | 101/114 (88.6%) | 20/21 (95.2%) |
| 1,152 | 110/123 (89.4%) | 20/21 (95.2%) |

The one-shot tick-1,000 gate passes. Re-evaluating on later ticks would admit
an overconfident false consensus, so the attempt must latch even when it does
not speak.

The implemented `guidance_pick` helper reproduces 20/20 across the seven
retained warehouses, including 7/7 on the held-out confirmation candidate
history. Focused and production-image test suites pass. The early report is
traced separately, does not set a tentative ballot, and the normal deadline
path recomputes from the later ledger.

## Crew-ejection safety check

A proposed counter-message against a low-marginal crowd leader was rejected.
At cutoffs 480-960, a two-ballot leader with solver marginal at or below 0.40
was crew in only 39-40% of retained cases. At tick 1,000, three-ballot leaders
below that marginal were crew in 16/17 cases, but the ballots were already
immutable and most remaining players already skipped. That signal is
diagnostic, not an actionable rescue mechanism at the current timing.

## Hosted result

### v1: invalid mechanism test

Matched requests `xreq_38e74ea5-52e1-47e9-8a1a-a7e073a7f535`
(confirmed-solver control) and
`xreq_9c27aa0e-8c3d-4e4e-8c9f-59ade2638939` (guidance v1) completed 100/100
episodes with zero failures. Control won 37 crew games and candidate won 40
(`+3pp`, Fisher `p=0.77`; Newcombe 95% difference interval approximately
`[-15.8pp, +21.6pp]`).

All 200 public replays expanded with complete hashes and no trace warnings.
Guidance fired zero times in 160 candidate meetings. Crew ejections were 19
control versus 24 candidate; impostor ejections were tied 12-12. Because the
mechanism did not fire, none of those outcome differences estimate guidance's
effect.

The runtime used the safe 240-tick fallback clock in the relevant path.
`min(200, timer // 6)` therefore produced a 40-tick guidance window, but final
auto-submit starts with 48 ticks remaining. The early branch was unreachable.
This escaped the unit test because it supplied the advertised 1,200-tick
timer.

Public-history replay at the intended tick-1,000 cutoff finds one 1/1 correct
strict-gate opportunity in control and four 4/4 in candidate. A v2 repair will
remove only the proportional cap, add fallback-clock reachability coverage,
and repeat the hosted mechanism test.

### v2: rejected mechanism

Fresh matched requests
`xreq_af54157d-242c-404d-906a-aa50d40c4111` (confirmed-solver control) and
`xreq_55ee44df-7f95-4444-95d5-1197a2969db0` (guidance v2) completed 100/100
episodes with zero failures. Control won 46 crew games and candidate won 37
(`-9pp`, Fisher `p=0.25`; approximate Newcombe 95% difference interval
`[-27.6pp, +10.2pp]`).

All 200 public replays expanded with complete hashes and no trace warnings.
Guidance again fired zero times in 158 candidate meetings. The candidate's
subject votes targeted impostors 24 times and crew 9 times, versus 35 and 6 in
control; subject skips were 89 versus 74. Across every crew player, crew-target
ballots were tied 132-132. Candidate ejections were 16 crew and 8 impostors,
versus 17 crew and 20 impostors in control.

Public replay at the intended cutoff contains one 1/1 correct candidate
opportunity, but runtime contains neither a fired guidance line nor a guidance
trace. The bounded timing repair therefore did not make the mechanism
observable in hosted play. Because no treatment occurred in either 100-game
candidate arm, neither scoreboard result estimates guidance's effect.

The guidance runtime, configuration, and tests were removed. The uploaded v1
and v2 artifacts remain inert and were never submitted.
