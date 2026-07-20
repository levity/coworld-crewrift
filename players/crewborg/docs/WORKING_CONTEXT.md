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

**Current experiment branch (2026-07-17):** `worktree-crewborg-solver-deferred` carries an
opt-in persistent joint-hypothesis meeting solver. Its first matched hosted A/B regressed
crew win 28.1% -> 20.3% and player-vote precision 95.2% -> 57.9% because the parser
treated attributed witnesses as targets. The predicate-aware fix is implemented and has
cleared the 125-replay offline gate: on solver-arm history, social-only counterfactual
pick precision moved 73.0% -> 84.4%, false picks 10 -> 5, and yellow picks 5 -> 1.
Full suite: 511 passed, 13 skipped. It is ready for a new matched hosted A/B, but remains
opt-in and must not be submitted or enabled by default first. Results:
`docs/experiments/2026-07-17-solver-ab-result.md` and
`docs/experiments/2026-07-17-claim-parser-offline.md`.

## ▶ Open threads (2026-07-17)

1. **Crew vote rate is evidence-limited, not gate-limited.** Crew votes only at fitted P≥0.9
   (`CREWBORG_WEIGHTS_VOTE_P`, `strategy/suspicion.py`); live posteriors cross it in only ~23% of
   meetings (median max-posterior at meeting ≈ 0.67) since the game's 0.4.28/29 update. Precision is
   the best in the field (67% vote-hit-imposter) but volume is ~1/3 of top rivals. The lever is
   warming evidence accumulation, not lowering the threshold (0.8 is the only defensible sweep value).
2. **Persistent solver needs a second matched hosted A/B.** Predicate/provenance parsing,
   relay discounting, original-source deduplication, and the meeting-entry fallback snapshot
   pass the offline gate. Reuse the original fixed roster and 64/arm design; require crew win
   improvement and preserved vote precision before enabling or submitting.
3. **Slot-4 role-limbo**: a crew seat at slot 4 can miss the CREWMATE reveal text entirely →
   `self_role=None` forever → frozen, 0 task attempts (~15% of crew games). Needs a bounded
   fallback-to-crew escape in `types.py` (keep the positive latch as primary).
4. **Imposter 2nd-kill conversion**: sits kill-ready with a target visible ~43% of ready ticks
   (4× rivals) yet converts no faster — the long-standing hesitancy lever.
