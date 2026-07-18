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

Pending.
