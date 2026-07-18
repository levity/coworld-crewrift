# Changelog

## 2026-07-18 - Timing-matched solver confirmation

- Reused the exact timing-matched artifacts for a fresh 100/arm confirmation:
  deferred solver-off control `xreq_2b8f99aa` completed 37/100 crew wins and
  solver-on candidate `xreq_95153fe2` completed 50/100 (+13.0pp, `p=0.064`).
  All three fresh matched runs favor the solver; cumulatively it is 119/228
  wins versus 92/228 controls (+11.8pp, stratified `p=0.011`, common odds
  ratio 1.62).
- The event audit found 100/100 hash-complete control replays and 98/100
  hash-complete candidate replays. The two candidate warnings correspond to
  anomalous `-100` subject scores despite completed episode metadata and
  observable play, so the official result retains them. Excluding them only as
  a sensitivity analysis gives 50/98 candidate wins versus 37/100
  (`+14.0pp`, `p=0.047`).
- On the 98 hash-complete candidate histories, subject player votes were 26/34
  correct versus 28/28 in control. This confirmation did not replicate the
  earlier precision gain. However, impostor ejections increased 9 -> 14 while
  crew ejections stayed at 18, matching the solver's intended team-level
  mechanism.
- The current public-evidence solver made 21/25 correct decisive picks on the
  clean candidate histories and 11/12 on control. Across all nine retained
  arms it is 162/181 (89.5%).
- Tested a new discount for byte-identical, same-tick accusations from
  different speakers. Every setting retained all 19 pooled errors while
  removing 4-10 correct picks, so the gameplay change was discarded.
- Updated `tools/analyze_solver_history.py` to exclude hash-failed traces
  automatically. The unchanged correlation-aware solver is now the promotion
  candidate; league submission remains gated on explicit approval.

## 2026-07-18 - Timing-matched solver replication

- Ran 64 episodes per arm from the exact image at `4f55b2f`, holding the
  subject's meeting-entry fallback and deadline vote timing constant. Control
  `xreq_5d19f6f9` completed 31/64 crew wins; solver candidate
  `xreq_358f2c2f` completed 35/64 (+6.25pp, `p=0.48`). Both arms' median
  subject vote offset was exactly 1,164 ticks.
- The solver increased player votes 18 -> 28 and correct player votes 16 -> 26
  while wrong votes stayed at 2 (precision 88.9% -> 92.9%). Impostor ejections
  rose 12 -> 15; crew ejections rose 7 -> 9.
- Across this replication and the preceding concurrent A/B, solver arms are
  69/128 crew wins versus 55/128 controls (+10.9pp, `p=0.080`) and 43/50
  versus 27/32 correct player votes. The repeated mechanism is higher useful
  vote recall at stable precision.
- Expanded all 128 public replays with the version-matched `0.1.59` binary:
  128/128 accepted, zero trace warnings, 7,209,030 events. The public-evidence
  solver made 33/36 correct decisive picks across the two new histories.
- Rejected exact-template source grouping, non-vote grounding requirements, and
  a lower threshold conditioned on public vote support. They removed useful
  correct consensus or added lower-precision picks.
- Extended `tools/analyze_solver_history.py --details` with the live top
  candidate plus current and persistent vote support for abstention analysis.
  Next: reuse the timing-matched artifacts for a 100/arm confirmatory A/B rather
  than overfit another rule to two false votes.

## 2026-07-18 - Correlation solver hosted A/B and timing-matched replication

- Completed a fresh concurrent 64/arm fixed-roster A/B on Crewrift `0.1.59`.
  The solver-off control won 24/64 crew games (37.5%); the correlation-aware
  solver won 34/64 (53.1%), a directional +15.6pp (`p=0.076`). The subject made
  11/14 correct player votes in control and 17/22 with the solver, so the gain
  came from greater voting recall at approximately flat precision.
- Expanded all 128 public replays without trace warnings. The offline solver
  made 15/15 correct picks on the control history and 13/15 on the candidate
  history. One candidate miss was supported only by public votes, with no
  accusation source; decisive reports now require an accusation source unless
  the target is directly witnessed.
- Replayed five retained hosted histories (317 episodes, 567 eligible meetings)
  after that gate. Decisive social-only precision is 97/108 (89.8%), versus
  97/109 (89.0%) before it; no correct pick was removed.
- Rejected source-accusation breadth normalization, duplicated-template actor
  clustering, stronger or flatter claim-language weights, fallback redirection,
  lower/higher posterior thresholds, alternate role likelihoods, and alternate
  public-vote weights. None improved the pooled precision/coverage frontier.
- Added off-by-default `CREWBORG_SOLVER_DEFER` for the next experiment's
  solver-off timing control. It freezes the same meeting-entry legacy target
  and submits it at the same deadline as the solver arm, isolating joint
  inference from the first A/B's 13-tick versus 1,164-tick timing difference.

## 2026-07-18 - Correlation-aware solver offline gate

- Reverted the unverified bootstrap-phase fallback and its tests. The retained
  solver histories had no affected subject episodes, so the unrelated defensive
  change is no longer carried by this branch.
- Added diminishing returns for additional source/stance/target claims within
  one meeting (`same_target_decay=0.8`) and for the same voter-target pair across
  later meetings (`vote_repeat_decay=0.7`). The first claim and each later
  meeting still contribute at full target-consensus weight.
- Added a single-source counterfactual gate: when one original source supplies
  all accusation claims behind a decisive pick, remove that source's claims,
  relays, and votes and require the target to remain the top joint hypothesis.
  Multi-source constraints and witnessed pins bypass this extra gate.
- Extended `tools/analyze_solver_history.py --details` with per-decision support,
  pre-counterfactual picks, and robustness diagnostics.
- Replayed all three retained arms (189 episodes, 362 eligible meetings).
  Social-only decisive-pick precision improved from 75/90 (83.3%) to 69/79
  (87.3%): wrong picks fell 15 -> 10 while 69/75 correct picks were retained.
  Per history: 30/34 -> 28/29, 27/32 -> 24/29, and 18/24 -> 17/21.
- Rejected aggressive consensus decay, claim/vote deduplication, same-meeting
  vote-bloc decay, and a positive jackknife posterior floor: each lost more
  correct coverage than wrong picks on retained history.
- Removed the full leave-one-actor-out implementation after the audit showed
  that only the sole supporting claim source was load-bearing. The final gate
  performs at most one extra small joint solve.

## 2026-07-18 - Predicate-aware hosted screen

- Uploaded the predicate-aware solver as `crewborg-solver-ab:v3` with solver on,
  veto off, and full telemetry, then ran 64 fixed-roster crew episodes in
  `xreq_e0bbd63f`.
- Completed 64/64 with zero operational failures. Against the historical
  solver-off control, crew wins were 25.0% vs 28.1% (unresolved, `p=0.69`).
- Recovered player-vote precision from the broken solver's 57.9% to 77.3%;
  wrong votes fell 16 to 5, wrong yellow votes fell 13 to 0, and team ejections
  normalized from 17 crew / 14 impostors to 10 crew / 16 impostors.
- Built a 64/64 hash-complete replay warehouse after correcting a local artifact
  packaging mismatch (raw replay bytes mislabeled as zlib).
- Diagnosed the remaining social-solver errors as correlated false consensus:
  two wrong green picks had posterior 0.899 and 0.952. A higher threshold would
  remove lower-confidence correct picks first, while the current veto would
  discard 13 correct fallback votes to remove 3 wrong ones.
- Kept the solver opt-in and unsubmitted. Next: add diminishing returns for
  same-target evidence within a meeting, validate on both replay histories, and
  only then run a fresh concurrent A/B.

## 2026-07-17 - Predicate-aware claim parsing

- Separated the current chat speaker from the attributed claim source and marked
  relayed assertions explicitly.
- Replaced the all-mentioned-colors accusation heuristic with predicate-target
  extraction for direct observations, compact `X sus Y` syntax, attributed
  witnesses, pronouns, votes, defenses, and disjunctions.
- Deduplicated relays by original source-target relation, discounted their
  weight, and conditioned them on both the attributed source and current speaker
  so suspected impostors cannot launder trust through another player.
- Preserved the legacy fallback target at meeting entry so late chat cannot
  mutate both the joint solver and its fallback.
- Added `tools/analyze_solver_history.py` and replayed 125 hosted histories before
  another upload. On solver-arm history, social-only pick precision improved
  from 73.0% to 84.4%, false picks fell 10 to 5, and yellow picks fell 5 to 1.
- Verified 40 focused solver/meeting tests, the full suite (`511 passed, 13
  skipped`), changed-file Ruff, and `git diff --check`.

## 2026-07-17 - Persistent solver plan

Before implementation:

- Preserve structured social claims and meeting outcomes across the full game instead of solving from only the current meeting's chat buffer.
- Deduplicate repeated claims by meeting, speaker, stance, and target set so one player cannot amplify a claim by repeating it.
- Enumerate joint impostor assignments over the original roster, including dead players, and aggregate role-conditioned evidence from every recorded meeting.
- Weight claims by evidence provenance and repeated-source decay, use the joint posterior to discount or reinterpret claims from likely impostors, and include public voting behavior as weaker evidence.
- Keep witnessed kills and watched task completions as hard or near-hard constraints while using existing suspicion only as a tempered prior to avoid overwhelming the joint evidence.
- Delay the solver decision until the meeting deadline backstop so most of each meeting is available for utterance collection, while retaining enough time to send the vote.
- Add focused parser, persistence, inference, timing, and regression tests before recording the implemented result below.

## 2026-07-17 - Persistent solver implemented

After implementation:

- Added episode-persistent `SocialClaim` and `MeetingRecord` belief state. Claims preserve speaker, target set, stance, meeting, raw text, and evidence provenance; meetings preserve caller, attributed votes, and ejection.
- Added deterministic parsing for accusations, defenses, kill victims, evidence type, and explicit "either A or B" constraints without depending on spaCy readiness.
- Replaced the current-meeting `C(n, 2)` accusation tally with fixed-size joint hypotheses over the original roster, including dead players. The posterior now aggregates claims and public votes across meetings, applies direct-observation pins and watched-task clears, and reports both marginals and the five strongest joint assignments.
- Made source reliability role-conditioned inside each hypothesis. Existing suspicion enters only as a tempered prior, so claims from likely impostors are interpreted through deflection and partner-cover likelihoods instead of being trusted like crew claims.
- Deduplicated equivalent speaker/stance/target claims within each meeting, selected the strongest provenance when duplicates disagree, and applied configurable decay when the same relation recurs in later meetings.
- Weighted bare, body, vent, sighting, reporter, claimed-vote, and public-vote evidence separately through environment-configurable `SolverConfig` fields.
- Changed deterministic solver timing from a fixed 192-tick window to the learned 48-tick deadline backstop. A standard 1200-tick meeting now collects 1152 ticks before solving and still has time to send chat and drive the vote cursor.
- Tightened the decisive-vote gate so symmetric fields do not produce an alphabetical pick: the top live marginal must separate from the first player outside the available impostor slots.
- Fixed the pre-existing navbake test failure by narrowly remapping the committed asset's two legacy `crewrift.crewborg.*` pickle module paths to the current package paths.
- Verified with Ruff, `git diff --check`, 67 focused meeting/belief tests, and the full crewborg suite (`501 passed, 13 skipped`). A solver-enabled local `scn_vote_basic` Gate-1 smoke connected all eight players, completed three meetings with zero vote timeouts, produced solver diagnostics at the learned deadline, wrote a replay, and exited cleanly.
