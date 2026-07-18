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
win delta is unresolved. Do not submit or enable it. The next offline iteration should
discount correlated same-target claims within a meeting; threshold-only and naive veto
changes are counterproductive on the captured history. Full suite before upload:
511 passed, 13 skipped. Results:
`docs/experiments/2026-07-17-solver-ab-result.md` and
`docs/experiments/2026-07-17-claim-parser-offline.md`, plus the v3 hosted screen:
`docs/experiments/2026-07-18-solver-parser-hosted-screen.md`.

## ▶ Open threads (2026-07-18)

1. **Crew vote rate is evidence-limited, not gate-limited.** Crew votes only at fitted P≥0.9
   (`CREWBORG_WEIGHTS_VOTE_P`, `strategy/suspicion.py`); live posteriors cross it in only ~23% of
   meetings (median max-posterior at meeting ≈ 0.67) since the game's 0.4.28/29 update. Precision is
   the best in the field (67% vote-hit-imposter) but volume is ~1/3 of top rivals. The lever is
   warming evidence accumulation, not lowering the threshold (0.8 is the only defensible sweep value).
2. **Persistent solver needs correlation-aware aggregation before another A/B.** The parser
   fix removed the yellow-target bug, but different speakers' correlated false reads can still
   multiply into confidently wrong posteriors (`P=0.899` and `0.952` in the v3 screen).
   Add within-meeting diminishing returns for repeated same-target evidence while preserving
   direct pins and cross-meeting accumulation. Raising the pick threshold removes lower-P
   correct picks first; enabling the current veto would drop 13 correct fallback votes to
   remove 3 wrong ones. Re-run both histories offline, then use a fresh 64/arm A/B.
3. **Historical slot-4 freeze claim is unverified; defensive local fix is parked.**
   A v82 note summarized a now-missing `/tmp/v81_fp_wh` as showing ~15% zero-task
   crew seats, reportedly concentrated in slot 4, but retained data has no affected
   episode IDs or auditable denominator. The solver subject had 0/189 zero-attempt
   episodes in slot 0 and fixed `crewborg:v107` had 0/189 in slot 5, so this did not
   affect the solver results; neither position tests the slot-4 claim. Commit `cba7885`
   adds a conservative phase-only escape and passed 517 tests plus local Gate-1, but
   it is not uploaded. Reproduce unchanged v82 in slot 4 before spending more work or
   uploading the candidate.
4. **Imposter 2nd-kill conversion**: sits kill-ready with a target visible ~43% of ready ticks
   (4× rivals) yet converts no faster — the long-standing hesitancy lever.
