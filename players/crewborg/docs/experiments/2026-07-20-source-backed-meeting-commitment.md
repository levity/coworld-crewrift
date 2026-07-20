# Source-backed meeting commitment

## Question

Can crewborg convert precise public conclusions into timely coordination instead
of speaking at tick 240 and then skipping at the deadline?

The treatment bundled four related changes:

1. Lower the tick-240 public gate from 0.76 to 0.65 while retaining two
   attributed non-self sources.
2. Retain that provisional target, re-solve at tick 360, and submit only when
   the same target still passes.
3. When the fused deadline solver is silent, fall back to a fresh
   source-backed public conclusion before the frozen meeting-entry target.
4. Permit a source-free structural conclusion only when the candidate appears
   in every assignment surviving structural facts alone.

This bundle tests the overall policy, not the contribution of each component.

## Offline gate

Across three retained 100-game fixed-roster samples, the current tick-240 gate
found 22 opportunities. All 22 targeted an impostor, and all 22 still selected
the same target at tick 360. At the final solve, all 42 selected public targets
were source-backed and correct. The stricter structural gate removed the two
prior source-free guesses.

The production image passed 556 tests with 13 skips, Ruff, and local Gate 1.
It was uploaded inertly as `crewborg-solver-commit:v1`, immutable policy
version `c2fe8244-fb51-4ddb-912c-1a0b0155d457`. Before commit, the two
behavioral source files were hash-checked against the uploaded image:
`attend_meeting.py` matched at `406c05f605b42633...` and `solver.py` at
`3593039f74c2d65a...`. Repo documentation changed after the image build, but
the policy behavior did not.

## Hosted design

Fresh matched requests used 100 forced-crew games per arm, the same fixed
roster, slots, roles, target build, solver/stick/alibi flags, and full
telemetry. Only slot 0 differed:

- Control `crewborg-pair-audit-close:v1`:
  `xreq_a8b7043e-fbd5-4aed-9e38-f6209c445415`.
- Candidate `crewborg-solver-commit:v1`:
  `xreq_6ed928f8-aacc-4df1-b963-4b3336a4da19`.

Both requests completed 100/100 with no operational failures. The objective
warehouse contains 10,955,291 events across all 200 episodes with zero failed
extractions. Four late hash warnings were balanced two per arm; behavioral
totals below exclude those four sparse timelines. Authoritative XP outcome
totals use all 200 games.

## Outcome

Candidate crew wins were 35/100 versus 45/100 control, a -10 point difference
that is not statistically resolved (two-sided Fisher `p=0.194`; Newcombe 95%
interval approximately -23.0 to +3.5 points).

| Metric | Candidate | Control |
| --- | ---: | ---: |
| Crew wins | 35/100 | 45/100 |
| Mean subject score | 41.32 | 51.80 |
| Mean subject tasks | 7.54 | 7.59 |
| Subject killed, clean replays | 58/98 | 50/98 |
| Subject ejected, clean replays | 3/98 | 4/98 |
| Impostors ejected, clean replays | 23 | 28 |
| Crew ejected, clean replays | 15 | 13 |

Subject ballots moved from 25 impostors / 3 crew / 66 skips in control to
29 / 8 / 50 in the candidate. Across all crew voters, targets moved from
264 impostors / 90 crew / 216 skips to 230 / 118 / 206. The candidate's
fresh social histories were less favorable: raw accusation-target precision
was 65.7% versus 72.0% in control, and the replayed final public solver selected
7/9 impostors versus 11/12.

## Mechanism

The early mechanism was sparse and precise:

- Five candidate ballots landed at meeting age 366-370 rather than the
  1,152-tick deadline.
- All five targeted the fixed impostor in slot 6.
- They occurred in three games; two of the five meetings ejected that target.
- All eight candidate crew ballots occurred at age 1,157-1,159. Early
  commitment therefore did not cast the observed wrong ballots.
- Replaying the public solver at ticks 240 and 360 found all five provisional
  candidate targets stable and correct. Two new tick-360 conclusions that had
  not existed at tick 240 were wrong, but the stability guard correctly
  prevented committing them.

No source-free final candidate fired. Objective chat contains no confirmed
deadline line in the public-fallback format, so this run does not establish
that the new deadline fallback activated. XP jobs did not expose policy logs,
which prevents a trace-level count of silent fallback attempts.

The early-commit games won two of three, but that selected sample is too small
for an outcome claim. More importantly, five correct early ballots cannot
mechanistically explain a ten-game aggregate deficit. The larger differences
in subject deaths, public-evidence quality, team ballots, and ejections show
that the two arms received materially different game histories despite the
matched roster.

## Verdict

Do not promote the four-change bundle from this run. The aggregate result is
directionally adverse, while the only clearly activated new mechanism was
5/5 correct and too sparse to estimate an outcome effect.

The reviewer correctly identified that all four changes spend one unbudgeted
aggression budget: more public-only decisions, earlier, at weaker evidence.
Target stability is not a proof of correctness because a correlated false
consensus can also remain stable. This sample did not exhibit that failure,
but it does not remove the structural risk.

The next test should isolate the components. Put early ballot commitment behind
its own flag, default it off outside the experiment, and compare it against the
same lower-threshold speech policy. Add a board-state risk gate only after
validating Crewrift-specific survivor/impostor states; a generic Among Us
parity heuristic would have blocked one of this run's correct five-vote
impostor ejections at seven alive. Test the deadline public fallback separately
with explicit activation telemetry before combining it with early commitment.
