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
current public-evidence solver is 162/181 on decisive picks (89.5%). Exact
template grouping, same-tick template decay, non-vote grounding, conditional
threshold reductions, and other correlation/weight variants all lose useful
coverage without removing enough errors. The unchanged timing-matched candidate
is the promotion target with veto off. Do not submit it to the league without
explicit human approval. Results:
`docs/experiments/2026-07-17-solver-ab-result.md` and
`docs/experiments/2026-07-17-claim-parser-offline.md`, plus the v3 hosted screen:
`docs/experiments/2026-07-18-solver-parser-hosted-screen.md` and the correlation gate:
`docs/experiments/2026-07-18-solver-correlation-offline.md`, and hosted A/B:
`docs/experiments/2026-07-18-solver-correlation-hosted-ab.md`.

## ▶ Open threads (2026-07-18)

1. **Crew vote rate is evidence-limited, not gate-limited.** Crew votes only at fitted P≥0.9
   (`CREWBORG_WEIGHTS_VOTE_P`, `strategy/suspicion.py`); live posteriors cross it in only ~23% of
   meetings (median max-posterior at meeting ≈ 0.67) since the game's 0.4.28/29 update. Precision is
   the best in the field (67% vote-hit-imposter) but volume is ~1/3 of top rivals. The lever is
   warming evidence accumulation, not lowering the threshold (0.8 is the only defensible sweep value).
2. **Promote the confirmed solver, pending approval.** The three-run crew-win
   effect is resolved (`p=0.011`) and the exact candidate artifact is already
   uploaded. Keep `CREWBORG_SOLVER=1`, veto off, and deadline timing unchanged.
   Individual vote precision remains a monitoring metric, not a claimed gain.
3. **Imposter 2nd-kill conversion**: sits kill-ready with a target visible ~43% of ready ticks
   (4× rivals) yet converts no faster — the long-standing hesitancy lever.
