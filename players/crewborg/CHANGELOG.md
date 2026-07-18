# Changelog

## 2026-07-18 - Early solver guidance plan

Before implementation:

- Recompute the correlation-aware solver once at meeting tick 1,000, after
  five-sixths of the 1,200-tick discussion window but with about 200 ticks left
  for other players to react.
- Speak without committing the ballot only when the public solve is decisive,
  `P(imposter) >= 0.80`, at least two independent attributed sources support
  the target, and at most two public ballots already target them.
- Keep collecting utterances after the guidance line and recompute the actual
  vote at the existing 1,152-tick deadline. Do not let the early result freeze
  or lower the final vote gate.
- Gate locally on all retained replay warehouses. At tick 1,000 the proposed
  guidance region contains 20/20 correct public-evidence picks, compared with
  101/114 (88.6%) for the ordinary solver region.
- Reject an early crowd-rescue rule: before tick 1,000 the solver does not
  reliably identify false crowd leaders, while by tick 1,000 three-ballot
  piles are usually already immutable.
- In the hosted A/B, require guidance trace evidence and judge both sides of
  the team outcome: increase impostor ejections without increasing crew
  ejections. A win-rate change without the intended mechanism is not enough.

After implementation:

- Added a one-shot guidance attempt at tick 1,000 for standard meetings. The
  attempt latches whether or not it speaks, so evidence arriving after the
  calibrated cutoff cannot open a new early-chat path.
- Added environment-backed gates for cutoff, posterior, independent source
  count, and existing ballot support. The guidance line cites two attributed
  sources and does not set a tentative vote or mark the final accusation sent.
- Preserved the final tick-1,152 solve and coupled accusation/vote. A focused
  test changes the solver pick between the early and final calls and verifies
  that the ballot follows the recomputed target.
- Replayed the production helper at tick 1,000 across seven retained
  hash-complete warehouses: guidance fires on 20/20 correct targets, including
  7/7 in the held-out confirmation candidate history.
- Verified 50 focused meeting tests, the production-image full suite (`521
  passed, 13 skipped`), Ruff, and `git diff --check`.

Hosted v1 diagnosis and v2 repair plan, before repair:

- A fresh 100/arm hosted A/B completed without operational failures. The
  confirmed-solver control won 37/100 crew games and guidance v1 won 40/100
  (`+3pp`, `p=0.77`), but the guidance template appeared in zero of 160
  candidate meetings.
- Team ejections moved in the wrong direction but without an active mechanism:
  crew ejections were 19 control versus 24 candidate, while impostor ejections
  were tied 12-12. Treat these differences as run variance, not guidance impact.
- Root cause: hosted perception can retain the safe 240-tick fallback clock.
  The proportional cap reduced the guidance window to 40 ticks, inside the
  48-tick auto-submit window, making the guidance branch unreachable.
- Repair only that timing contradiction: use the configured 200-tick window
  directly, retain the final 48-tick backstop and every precision gate, add a
  fallback-clock reachability regression, and replay the fresh hosted history.
- The fresh public history contains 5/5 correct strict-gate opportunities at
  the intended tick-1,000 cutoff across the two arms. Upload v2 only after the
  production-image suite and a fallback-clock smoke pass.

After v2 repair:

- Removed the proportional `timer // 6` cap. The configured 200-tick guidance
  window now remains outside the 48-tick auto-submit backstop even when hosted
  perception retains the safe 240-tick fallback clock.
- Added a regression that leaves `vote_timer_ticks` unknown and verifies the
  strict guidance chat fires with 200 fallback ticks remaining.
- Verified 64 focused meeting/solver/parser tests, the production-image full
  suite (`522 passed, 13 skipped`), Ruff, and `git diff --check`.
- Replayed the two fresh v1 arms at the intended cutoff through the production
  parser and repaired gate: 5/5 guidance opportunities target impostors. This
  is a coverage/precision gate, not an outcome estimate.

## 2026-07-18 - Commitment-aware solver offline gate

- Found that the solver preserved accusation weight even when the attributed
  source had not cast any visible ballot by the decision cutoff. Across all
  retained histories, accusation targets were 80.9% correct when source and
  ballot matched but only 47.2% correct when the source had no visible ballot.
- Tested `SolverConfig.no_ballot_claim_decay=0.30`, limited to accusation
  claims whose attributed source was absent from that meeting's public ballot
  map. Explicit skips, votes for another target, and all actual ballots kept
  their existing weights.
- Replayed nine retained arms: decisive public-evidence precision improved from
  162/181 (89.5%) to 154/168 (91.7%). The rule removed 5/19 errors while
  retaining 154/162 correct picks; coverage changed 16.4% -> 15.3%.
- Rejected unsupported-ballot decay and discounts for explicit skips or
  contradictory ballots. Each lost more useful correct decisions.
- Built exact image `sha256:ad221fff...`, uploaded inert
  `crewborg-solver-commitment:v1`, and ran a fresh 100/arm matched A/B:
  control `xreq_7b514e90` won 47/100 crew games; candidate `xreq_28dbdfa0`
  won 32/100 (-15.0pp, `p=0.030`). Both requests had zero request failures.
- Expanded all 200 public replays with complete hashes. Candidate subject
  player votes were 24/30 correct versus 17/21 control, and candidate impostor
  ejections increased 6 -> 15 while crew ejections increased 10 -> 14.
  Replaying both decay settings changed zero decisive picks on either fresh
  arm (control 7/9; candidate 13/13).
- Rejected and removed the no-ballot discount: its retained-history precision
  gain did not reproduce as an active mechanism, and its hosted outcome was
  adverse. The confirmed correlation-aware solver remains the promotion
  target.

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
