# crewborg working context

**What this is.** The live, high-signal state of *what we're working on right now* with crewborg —
the minimal set of cross-session facts worth carrying into the next session. Read it on startup to
resume; **update it as you learn** (keep it tight — prune anything no longer load-bearing). **Clear
and reseed it when we pivot** to a whole new direction, keeping only the new objective.

This is *not* a log or archive: finished work lives in git history / the

---

## Current update (2026-07-20, append-only deduction)

Active branch/worktree: `crewborg-deduction-history` at
`.claude/worktrees/crewborg-deduction-history`, rebased on current
`origin/master`. The main worktree is clean. This is a new default-off code
path, not a rewrite of the legacy solver in place.

`CREWBORG_DEDUCTION_HISTORY=1` now collects a frozen append-only stream of
personal world observations, exact public text/votes, meetings, deaths, and
task-count changes. Pure functions rederive witnessed actions, relational
kill-window constraints, role-conditioned claims, every fixed-size impostor
assignment, its complete contribution audit, marginals, and a parity-aware
meeting decision. The pipeline is explicitly staged as raw history -> derived
evidence -> viable assignment table -> scored posterior -> board policy. With
the flag on for crew, runtime skips the legacy player event log, alibi/social
accumulators, and suspicion model; crew meetings bypass both the LLM and old
solver. Impostors retain the complete legacy evidence, movement, and meeting
path. The default path is unchanged.

Cheap validation exists at `tools/evaluate_deduction.py`. Seed 7 over 1,000
synthetic histories gives 94.9% vote precision at 49.4% coverage and no
murder-clear violations. Six retained public warehouse sets cover 770 crew
meetings while the subject was alive; the new decision spends 73 votes and gets
63 correct (86.3%).
Historical replay intentionally omits unavailable first-person frames.
Sampling found and fixed one unsound parse: “saw X near the vent” is proximity,
not witnessed vent use. On the richest 181-eligible-meeting set this removed
one wrong vote and moved precision 73.3% -> 78.6%.

Pre-host hardening adds full factor-table telemetry, history/evidence counts,
solve latency, posterior calibration, and a threshold sweep. Across all six
sets, default threshold decisions are 63/73 correct; 0.70/0.85 is 47/54 and
0.60/0.75 is 90/109, so behavior remains unchanged. Compact slotted world
values reduced a dense 20,000-frame benchmark from 140 MB to 79 MB RSS; solve
time was 81 ms.

The fixed amd64 image passed an activated Gate 1 over two sequential scenario
games: eight meetings, zero vote/connect/disconnect timeouts, no inference
errors, complete factor-table artifacts, and 1-77 ms final solves with 48 ticks
remaining. The smoke caught and then verified the fix for one unsound detector:
walking onto a visible vent is no longer treated as emerging from it.

The first matched 100/arm hosted test is complete. Candidate crew wins were
37/100 versus 42/100 control (`p=0.563`), but the treatment fails the stronger
precommitted behavioral screen: clean subject ballots were 21 impostor / 3 crew
/ 69 skip versus 25 / 0 / 44, so precision fell 100% -> 87.5% and non-skip
coverage retained only 71.2% of control. Do not promote or submit it.

The early mechanism was sound in this sample: all ten direct accusations,
three public accusations, and one clear spoken at tick 241 were correct. The
late public solve caused the visible errors. Same-history replay on 93 clean
candidate meetings gives legacy 16/17 versus new 14/18; three new errors were
just two-source ballot piles with no accusation against the target. Requiring
at least one active accusation would retain all 14 correct selections and
remove those three errors. Next: implement that narrow decision gate, validate
across every retained warehouse, and make synthetic histories model correlated
and persistent false beliefs before considering another hosted run. Full
result: `docs/experiments/2026-07-20-deduction-history-hosted-handoff.md`.

## Current update (2026-07-20, source-backed commitment)

Inert `crewborg-solver-commit:v1`
(`c2fe8244-fb51-4ddb-912c-1a0b0155d457`) carries a four-change meeting bundle:
P=0.65 two-source early speech, stable tick-360 commitment, source-backed
deadline fallback, and logically forced source-free conclusions. Retained
history was 22/22 at ticks 240/360 and 42/42 at the final public solve;
production validation is 556 passed / 13 skipped and Gate 1 clean.

The fresh exact-roster 100/arm hosted run completed without ops failures but
was directionally adverse: 35 crew wins versus 45 control (`Fisher p=0.194`).
Candidate/control subject ballots were 29/8 versus 25/3 impostor/crew;
crew-voter ballots were 230/118 versus 264/90. Candidate histories had weaker
raw public claim precision (65.7% versus 72.0%), fewer impostor ejections
(23 versus 28), more crew ejections (15 versus 13), and more subject kills
(58 versus 50 on 98 clean replays per arm).

The only clearly activated new mechanism was precise: five tick-366-370
ballots, all against impostors, with two target ejections. All eight candidate
crew ballots occurred at the deadline. No source-free candidate fired and no
deadline public-fallback line was confirmed. The bundle therefore cannot be
promoted, but the ten-game deficit cannot be assigned to the five observed
early commitments either.

Next: split the aggression budget. Give early commitment its own default-off
flag and test it against the same lower-threshold speech policy; test deadline
public fallback separately with activation telemetry. Before adding a parity
gate, validate Crewrift-specific survivor states: a generic skip-on-seven rule
would have blocked one correct five-vote impostor ejection in this sample.
Details:
`docs/experiments/2026-07-20-source-backed-meeting-commitment.md`.

## Current update (2026-07-20)

The joint solver now has the durable representation requested for iterative
evidence work: every usable hidden-kill observation is an immutable
`KillAlibi`, raw ledgers remain append-only, every impostor pair is recomputed
from those ledgers, and the result exposes stable evidence IDs plus
contributions and exclusion reasons for audit. Production-image validation is
551 passed / 13 skipped and Gate 1 is clean; latest source, including the
post-run possible-killer combination fix, is 552 passed / 13 skipped.

The planned soft alibi weight was rejected before enablement. Retained history
showed screen-visible actual killers 61-68 pixels from crewborg, and at the
sounder 28-pixel bound two of three observed players were the non-killing actual
impostor. "Not this killer" is not evidence of crew when an impostor partner
stays with the group. Production `alibi_weight` is therefore zero; only a pair
with no eligible, non-co-present perpetrator is excluded. Current eligibility
is broad, so this usually means every member was close for the same kill.

Fresh fixed-roster hosted evaluation completed 200/200 clean:
`crewborg-pair-audit-close:v1` won 47/100 crew games versus 42/100 for
`crewborg-pair-audit-visible:v1` (`Fisher p=0.569`). Both arms were killed in
52/100 games. Player-vote precision was 28/28 close and 27/28 visible. The
10.48-million-event warehouse has zero extraction failures and zero trace
warnings. Full-tick mechanism reconstruction found only singleton events and
zero pair exclusions in both arms, so neither treatment changed a posterior;
the five-point outcome difference is noise. Details:
`docs/experiments/2026-07-20-solver-pair-audit-alibi.md`.

Keep the ledger/audit infrastructure and 28-pixel physical definition. The next
promising solver evidence channel is map-aware kill-window reachability: retain
the victim's possible path and every player's reachable region, then exclude a
pair only when neither member could have intersected the victim. This combines
independent relational constraints without turning a non-killing impostor into
a player clear.

The same run repaired two warehouse streaming drift bugs: downloaders now reuse
the selected Python environment and incremental builds pass preflighted replay
encodings to the current `build_request` API. On this 2-vCPU VM, three workers
are suitable for download-heavy streaming, but sustained full-tick replay
expansion should use two.

## Current update (2026-07-19)

The current best combined artifact is inert
`crewborg-solver-stick-alibi:v3`
(`aa0415e5-a4ba-4bcd-a673-2212a0866eb5`) at source `de63cbd`. Living crew no
longer collect self-tail suspicion while deliberately using stick mode.
Solver counterfactuals carry one immutable evidence bundle; the
correlated-crowd cap is a separate social-only solve; and a structural
constraint may support a no-accuser conclusion only when it is demonstrably
necessary. Vote-only consensus remains rejected. Production validation is
548 passed / 13 skipped and local Gate 1 is clean.

The fresh exact-roster 100/arm v2-v3 A/B completed without failures: crew wins
were 48/100 v3 versus 32/100 v2 (Fisher `p=0.030`, Newcombe interval +2.4 to
+28.8pp). Subject impostor / crew votes moved 24 / 3 -> 52 / 8, team ballots
196 / 139 -> 230 / 92, and impostor / crew ejections 6 / 21 -> 15 / 12. Mean
loss score stayed flat. On fixed public histories, v3 adds 10/10 correct
candidate-arm picks over v2, comprising four constraint-only hard-clear
deductions and six source-supported deductions rescued by the social-only cap.
It adds one wrong but uncast control opportunity. Candidate histories were
also more favorable, so do not assign the full win delta to the bundled
treatment. Details:
`docs/experiments/2026-07-19-solver-constraints-hosted-ab.md`.

The crew collaboration / speaking-clears iteration is rejected. Inert v4
(`af8623ba-4233-4b8d-8802-7e7d0a21028c`) tied v3 at 47/100 wins in a fresh
exact-roster A/B, but 47/88 public clear mentions named fixed impostors.
Reconstructing the runtime detector found 392/550 inferred completers wrong,
including 258 credits to impostors. Offline fitting used the replay's true
completer identity; runtime saw only task-site dwell plus a global decrement.
The emission path has been removed, the fitted compatibility field is now held
at zero, and the joint solver no longer consumes it as a clear. Details:
`docs/experiments/2026-07-19-speak-clears-hosted-ab.md`.

The artifact downloader and warehouse wrapper were also corrected after this
run exposed false completeness assumptions. Optional results/log routes no
longer trigger repeated downloads; replay-complete XP episodes can stage a
minimal dimension only after exact participant/score/role alignment. Team wins
come from the WinReward role rather than a per-player score threshold; no
WinReward means no winner. Synthesized task/kill dimension values come from
objective replay events.

The persistent correlation-aware solver now hard-clears hidden-kill victims,
reinterprets episode-persistent claims under that posterior, excludes self-chat
echoes, and may publish a fresh public solve at tick 240 when `P>=0.76` and two
external sources support it across meetings. Its fresh 100/arm test was 43
crew wins versus 42 control; all five candidate early lines targeted real
impostors, while team impostor ballots/ejections increased and crew
ballots/ejections decreased. The outcome lift is unresolved, but the mechanism
is active and precise.

The prior combined candidate is inert upload
`crewborg-solver-stick-alibi:v2`
(`13bfb03f-d0ea-435c-b772-865db0e9a6d6`) at source `38771ef`. Stick mode acts
only after own tasks and increased post-task 2+ player visibility from 31.8%
to 39.7% without task, idle-penalty, or survival regression. Alibi constraints
are per kill and sound after strict-visibility, witnessed-kill, and victim-
absence guards, but are very sparse.

Two combined hosted batches are directionally positive but unresolved:
ops-filtered wins total 88/200 candidate versus 78/194 control (+3.8pp,
`p=0.476`). The corrected replication alone was 41/100 versus 37/94
(`p=0.884`) and improved mean non-win score 4.63 -> 6.47. Retain v2 for
further evaluation; do not submit without explicit approval, and do not tune
the sparse alibi path without a discriminating mechanism test.

## 🎯 Current state (seeded at the 2026-07-01 sync — the v82 code line)

**This package now carries the code that is Crewrift Prime CHAMPION as `crewborg:v82`** (2026-07-01):
- **Imposter idle-freeze fixes** — RECON never idles/stalls (abandons reached-stale targets, falls back
  to expected-crew seek; recon gated to the pre-kill-ready window); SEARCH is a 5-state FSM
  (PICK_ROOM/GO_TO_ROOM/SEARCH_ROOM/WATCH/FOLLOW) with a scored, env-tunable PICK_ROOM
  (`CREWBORG_PICKROOM_W_*`). Measured: idle-while-ready 0.68 → 0.10, freezes ≥1k ticks 23 → 1,
  kills 1.18 → 1.91/game across the fix line.
- **Role-latch fix** — role latches from the RoleReveal TEXT (`IMPS`/`CREWMATE`), never from reveal
  icons (crew reveals also render the 9500+ icon range; the icon latch made crew play as imposters —
  0 tasks, silent skip-votes, no chat). If you fork this code, do not widen that latch.
- League telemetry: upload with `CREWBORG_METRICS=1 CREWBORG_TRACE_GROUPS=all` (see
  user_preferences.md); league artifacts are EPHEMERAL (~one round) — harvest promptly.

**Current experiment branch (2026-07-18):** `worktree-crewborg-solver-deferred` carries the
correlation-aware persistent joint-hypothesis meeting solver. Three fresh matched
A/Bs now all favor it: 34/64 vs 24/64, 35/64 vs 31/64, and a 100/arm
confirmation at 50/100 vs 37/100. Cumulatively, solver arms are 119/228 crew
wins versus 92/228 controls (+11.8pp, stratified `p=0.011`, common OR 1.62).
The confirmation held median subject vote timing at 1,163 ticks in both arms and
increased impostor ejections 9 -> 14 with crew ejections flat at 18. It did not
replicate the earlier individual precision gain: player votes were 26/34
correct versus 28/28 control. Across all nine retained arms, however, the
confirmed public-evidence solver is 162/181 on decisive picks (89.5%).
A commitment-aware iteration initially improved retained-history precision to
154/168 (91.7%), but failed its fresh 100/arm hosted test: 32 crew wins versus
47 for the confirmed solver (`p=0.030`). Its mechanism did not reproduce:
candidate player-vote precision stayed flat, impostor ejections increased, and
decay 0.30 versus 1.0 changed zero decisive public-evidence picks across all
200 fresh hash-complete replays. The discount has therefore been removed. The
confirmed correlation-aware solver remains the promotion target. Do not submit
either version to the league without explicit human approval. Results:
`docs/experiments/2026-07-17-solver-ab-result.md` and
`docs/experiments/2026-07-17-claim-parser-offline.md`, plus the v3 hosted screen:
`docs/experiments/2026-07-18-solver-parser-hosted-screen.md` and the correlation gate:
`docs/experiments/2026-07-18-solver-correlation-offline.md`, and hosted A/B:
`docs/experiments/2026-07-18-solver-correlation-hosted-ab.md`, plus the next
offline gates: `docs/experiments/2026-07-18-solver-commitment-offline.md`,
`docs/experiments/2026-07-18-solver-early-guidance.md`,
`docs/experiments/2026-07-18-solver-single-source-crowd-cap.md`, and
`docs/experiments/2026-07-19-solver-early-public-coordination.md`. Early
guidance is rejected and removed after both 100-game candidate arms emitted
zero guidance lines; their outcome differences are not treatment effects.

The single-source crowd cap has completed its fresh 100/arm screen. Subject
ballots improved from 24 impostors / 1 crew to 25 / 0 and replay confirmed that
the cap removed two fresh false picks, but crew ejections increased 8 -> 14
while impostor ejections decreased 18 -> 16. Wins were 39/100 candidate versus
35/100 control (`p=0.66`). The subject did not vote for any of the 14 ejected
crew, so the active problem is team coordination rather than subject ballot
precision.

The current candidate adds feature-flagged early public coordination. At tick
240 it may share a public-only solver target when `P>=0.76` and two attributed
current-meeting sources agree; the selected gate is 29/29 on six selection
arms and 29/29 on held-out guidance plus crowd-cap history. It also truthfully
defends crewborg's known-crewmate identity after a public self-vote. Neither
path stages a ballot, and the full solver still recomputes at tick 1,152. Local
validation is complete and inert upload `crewborg-solver-early-public:v1`
(`9e7990ba-93be-49fa-9aaa-de28b2a53052`) carries source `d272500`. Run a fresh
matched 100/arm A/B, requiring runtime activation and measuring subject
complicity, subject self-ejections, team crew ballots/ejections, and impostor
ejections.

## ▶ Open threads (2026-07-18)

1. **Crew vote rate is evidence-limited, not gate-limited.** Crew votes only at fitted P≥0.9
   (`CREWBORG_WEIGHTS_VOTE_P`, `strategy/suspicion.py`); live posteriors cross it in only ~23% of
   meetings (median max-posterior at meeting ≈ 0.67) since the game's 0.4.28/29 update. Precision is
   the best in the field (67% vote-hit-imposter) but volume is ~1/3 of top rivals. The lever is
   warming evidence accumulation, not lowering the threshold (0.8 is the only defensible sweep value).
2. **Source commitment rejected.** No-visible-ballot claims looked weak in
   retained data, but discounting them did not change any fresh public solver
   pick and the hosted arm lost 32/100 versus 47/100. Do not revive this signal
   without a causal feature that reproduces on held-out histories.
3. **Imposter 2nd-kill conversion**: sits kill-ready with a target visible ~43% of ready ticks
   (4× rivals) yet converts no faster — the long-standing hesitancy lever.
