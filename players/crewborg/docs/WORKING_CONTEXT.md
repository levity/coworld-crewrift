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

**Current experiment branch (2026-07-18):** `worktree-crewborg-solver-deferred` carries an
opt-in persistent joint-hypothesis meeting solver. Its first matched hosted A/B regressed
crew win 28.1% -> 20.3% and player-vote precision 95.2% -> 57.9% because the parser
treated attributed witnesses as targets. The predicate-aware v3 screen recovered to
25.0% crew wins and 77.3% vote precision; wrong votes fell 16 -> 5, wrong yellow votes
13 -> 0, and crew/impostor ejections normalized from 17/14 to 10/16. It still did not
beat the historical solver-off control (28.1% wins, 95.2% precision), and the 64-game
win delta is unresolved. The correlation-aware candidate then completed a fresh
concurrent 64/arm A/B: crew wins rose from 24/64 (37.5%) to 34/64 (53.1%), a
directional +15.6pp (`p=0.076`). Player-vote precision was flat
(78.6% -> 77.3%), while correct subject votes increased 11 -> 17 and impostor
ejections 11 -> 14 with crew ejections unchanged at 7. This is promising but
confounded by vote timing: control voted at median tick 13 and candidate at tick
1,164. The next candidate rejects vote-only solver picks and adds off-by-default
`CREWBORG_SOLVER_DEFER` so a solver-off control can freeze the same entry target
and act at the same deadline. Across five retained histories, the vote-only gate
improves public-evidence precision 97/109 -> 97/108 without losing a correct
pick. Do not submit or enable the solver by default before a timing-matched
replication. Results:
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
2. **Run a timing-matched solver attribution A/B.** The first correlation-aware
   A/B was +15.6pp crew wins but changed both inference and vote timing. Build one
   exact-source image after the vote-only support gate; run solver-on against
   solver-off plus `CREWBORG_SOLVER_DEFER=1`, 64 fixed-roster crew episodes per
   arm. Both arms must vote near the deadline. Judge actual vote precision,
   player-vote recall, ejections, and crew wins, then expand both public replay
   sets. The live private-artifact endpoints currently return 403 for this
   credential, so do not promise exact runtime solver/fallback attribution.
3. **Imposter 2nd-kill conversion**: sits kill-ready with a target visible ~43% of ready ticks
   (4× rivals) yet converts no faster — the long-standing hesitancy lever.
