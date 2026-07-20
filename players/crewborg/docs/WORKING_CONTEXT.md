# crewborg working context

**What this is.** The live, high-signal state of *what we're working on right now* with crewborg —
the minimal set of cross-session facts worth carrying into the next session. Read it on startup to
resume; **update it as you learn** (keep it tight — prune anything no longer load-bearing). **Clear
and reseed it when we pivot** to a whole new direction, keeping only the new objective.

This is *not* a log or archive: finished work lives in git history / the

---

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
