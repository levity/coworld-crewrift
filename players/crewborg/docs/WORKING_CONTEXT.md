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
opt-in persistent joint-hypothesis meeting solver. The matched hosted A/B is complete:
`crewborg-solver-ab:v1` (off) vs `v2` (on), 64/arm, fixed roster, subject crew, two
impostors, and 0 ops failures. **Do not enable or submit v2:** crew win moved 28.1% ->
20.3% (p=0.30; statistically unresolved), while player-vote precision fell
95.2% -> 57.9%.
Meeting deferral worked (median vote at 1,161/1,200 ticks), but bad late claims drove
more crew ejections. Full result: `docs/experiments/2026-07-17-solver-ab-result.md`.

## ▶ Open threads (2026-07-17)

1. **Crew vote rate is evidence-limited, not gate-limited.** Crew votes only at fitted P≥0.9
   (`CREWBORG_WEIGHTS_VOTE_P`, `strategy/suspicion.py`); live posteriors cross it in only ~23% of
   meetings (median max-posterior at meeting ≈ 0.67) since the game's 0.4.28/29 update. Precision is
   the best in the field (67% vote-hit-imposter) but volume is ~1/3 of top rivals. The lever is
   warming evidence accumulation, not lowering the threshold (0.8 is the only defensible sweep value).
2. **Persistent solver needs predicate- and provenance-aware claim parsing.** The present
   all-mentioned-colors heuristic turns `Yellow saw cyan vent` into accusations against both
   yellow and cyan; 13/16 wrong solver-arm votes targeted yellow. Represent attributed source
   separately from current speaker and target, discount hearsay/relays, and do not let an
   undecided late solver fall back to legacy suspicion newly contaminated by the same chatter.
3. **Slot-4 role-limbo**: a crew seat at slot 4 can miss the CREWMATE reveal text entirely →
   `self_role=None` forever → frozen, 0 task attempts (~15% of crew games). Needs a bounded
   fallback-to-crew escape in `types.py` (keep the positive latch as primary).
4. **Imposter 2nd-kill conversion**: sits kill-ready with a target visible ~43% of ready ticks
   (4× rivals) yet converts no faster — the long-standing hesitancy lever.
