# Changelog

## 2026-07-22 - Isolation-triggered pursuit escape

- Broadened self-preservation from solver-confirmed suspects to any continuous
  12-tick one-on-one exposure within 64 pixels. The initial response is a soft
  move toward a fresh witness.
- Added a 96-pixel pursuit confirmation window. A companion that remains close
  for another 12 ticks upgrades escape to a latch that ends only when a third
  player is physically nearby.
- A single fresh witness is now a valid destination; clustered witnesses remain
  preferred. Solver probabilities only filter destinations and accelerate
  response to known threats, and proximity never becomes deduction evidence.
- Added explicit activation, pursuit-upgrade, and termination trace events and
  metrics for hosted analysis.
- The 200/arm hosted test rejects this broad trigger. On per-slot operational
  games, murders rose 36.2% -> 57.5%, all-task completion fell 60.3% -> 37.3%,
  and crew wins fell 31.0% -> 15.7%. Full telemetry showed 629/717 escape
  targets were crew; the controller repeatedly treated a reached witness as the
  next threat and increased one-on-one time with impostors. Do not promote.
- Repaired the XP artifact downloader after API drift hid policy telemetry.
  XP results, owned logs, and owned player artifacts now use the current
  ownership-scoped episode-request routes. Also established that negative score
  is not an operational-failure test; use result timeout fields.

## 2026-07-22 - Self-preservation movement

- Added a default-off `SelfPreservationMode` that consumes the append-only
  joint posterior without writing derived movement choices back into deduction.
  A living crew player leaves a fresh one-on-one encounter only when the sole
  companion is pinned or has `P(imposter) >= 0.75`, and a fresh cluster of at
  least two non-suspect living players provides a destination.
- Added bounded group-aware task selection behind its own flag. It prefers a
  task supported by a fresh two-player cluster only within 160 pixels of the
  nearest task's direct travel cost, then preserves the existing task behavior.
- Escape decisions hold for at most 72 ticks and end as soon as a witness
  arrives, the threat leaves, or the destination becomes stale. Posterior
  refresh is limited to one solve per 72 ticks while actually one-on-one.
- Local validation: 66 focused tests and the full 595-test current-SDK suite
  pass (13 skipped); touched-file Ruff and `git diff --check` are clean. The
  amd64 image completed Gate 1 with both defenses and stick mode enabled,
  without a freeze, inference error, or connection failure.
- Completed a same-image rotated-crew-seat 100/arm hosted A/B. Subject-clean
  murders moved 60.7% -> 55.1% (`p=0.45`) with unchanged task completion, while
  exact replay showed less one-on-one exposure and fewer killer-only murders.
  The stricter whole-roster-clean subset reversed the murder delta, so the
  candidate remains evaluation-only.
- Group-supported task starts and first-victim frequency were effectively flat.
  The next test should isolate suspect escape with group tasking disabled and
  add observable activation telemetry before any threshold tuning.

## 2026-07-20 - Correlated deduction evaluation and ballot gate

Before implementation:

- Repair the synthetic generator so one actor's chat and ballot can express the
  same persistent belief, and several actors can share a correlated false
  belief. Re-run 1,000 games before trusting cheap solver screens.
- Let ballots update the joint posterior, but do not let a ballot pile alone
  authorize an eject without an accusation, direct pin, or structurally forced
  assignment.
- Turn repeated warehouse and synthetic analysis into documented scripts, then
  test narrower ballot weights and correlation discounts on identical histories.

After implementation:

- Synthetic actors now retain beliefs across meetings, usually vote from those
  beliefs, and sometimes adopt a shared crowd target. On seed 7, 1,000 final
  histories now produce 84.6% vote precision at 64.2% coverage instead of the
  implausibly easy 94.9% at 49.4% coverage.
- The decision layer requires an active accusation for a nonstructural eject.
  On 93 clean hosted candidate meetings this removes three vote-only errors and
  no correct selection, moving 14/18 to 14/15 (93.3%).
- Added a 3,000-meeting synthetic audit, generic inference-config overrides,
  detailed old/new decision comparison, and a reproducible analysis guide.
  Lower ballot weights and stronger repeat decay slightly improved synthetic
  precision only by dropping many more correct votes; stronger decay also
  regressed hosted-history replay from 14/15 to 8/9 and is rejected.
- Preserved relational hidden-kill “anti-alibis”: an assignment is excluded
  when none of its living members was outside the continuously co-present
  group. Earlier ejections now correctly remove players from later possible-
  killer sets. This constrains pairs, not individual roles; with two impostors,
  staying with at least two other players is where it first excludes a pair.

## 2026-07-20 - Append-only deduction hosted result

- Completed the same-image 100/arm forced-crew A/B: candidate wins were 37/100
  versus 42/100 control (`p=0.563`). The candidate is not promotable because
  subject ballots regressed from 25/25 to 21/24 correct, added three crew
  ballots, and retained only 71.2% of control non-skip coverage.
- Verified the intended timing in public replay. Tick-241 output was 13/13
  correct accusations plus one correct clear; the two spoken false accusations
  appeared only at tick 1153. Hosted factor logs were unavailable.
- Replayed both solvers on the same 93 clean candidate meetings: legacy was
  16/17 and the new path 14/18. A requirement for at least one explicit
  accusation removes three vote-only errors without removing a correct new-path
  selection; threshold increases remove correct picks first.
- Added compact `evaluate_deduction.py --details` output and automatic exclusion
  of trace-warning episodes. Fixed `build_expand_replay.sh` to retain the
  compile-time source/resource tree required by the generated binary at runtime.
- Identified a synthetic-evaluation distribution gap: independent chat and
  ballot draws omit the correlated, persistent false beliefs behind hosted
  crowd errors.

## 2026-07-20 - Deduction experiment hardening

Before implementation:

- Preserve the raw-history concept while making the successive semantic,
  assignment, scoring, posterior, and policy layers explicit and independently
  callable.
- Keep the prior impostor policy completely intact, add enough hosted telemetry
  to rescore every assignment factor, measure realistic history cost before
  changing representation, and check posterior/threshold calibration locally.

After implementation:

- Added `derive_evidence`, `build_assignment_table`, `score_assignments`, and
  `decide_from_inference`; `infer` and `decide` are compatibility compositions.
  Final traces include the full assignment factor table, history/evidence
  counts, solve latency, and deadline state.
- Scoped the feature to crewmates. Impostors now retain the complete legacy
  evidence, suspicion, movement, and meeting paths when the flag is present.
- Replaced nested Pydantic world values with frozen slotted values. A dense
  20,000-frame benchmark moved from 140 MB to 79 MB RSS and from 0.81s to 0.35s
  construction; inference took 81 ms.
- Added warehouse calibration buckets and threshold sensitivity. Across 770
  retained meetings, defaults remain the best precision/coverage compromise:
  63/73 correct versus 47/54 at 0.70/0.85 and 90/109 at 0.60/0.75.
- An activated local meeting smoke caught an unsound vent transition: walking
  onto an empty visible vent was treated as emerging. Emergence now requires
  absence from the complete preceding player frame, with a regression test.
- The fixed amd64 image completed two sequential activated scenario games with
  eight meetings, zero vote/connect/disconnect timeouts, no inference errors,
  full factor-table artifacts, and final solve latency of 1-77 ms at the
  48-tick backstop.
- Final validation: 575 passed / 13 skipped, changed-file Ruff clean, and
  `git diff --check` clean.

## 2026-07-20 - Parallel append-only deduction path

Before implementation:

- Build a new, default-off path in an isolated worktree. Its complete solver
  input is a frozen game specification plus an append-only stream of personal
  semantic observations, exact utterances, public votes, meetings, and deaths.
- Make evidence extraction, joint role inference, and the vote decision pure
  functions. Never consume the old suspicion scalar or a previous solver
  conclusion, and retain enough input to reinterpret every contribution.
- Preserve useful reasoning nuances from prior work without treating that
  implementation as authoritative: role-conditioned sources, relational
  per-kill alibis, source-target deduplication, cross-meeting persistence,
  correlation discounts, killed-player clears, and ejection uncertainty.
- Add a single switch that bypasses both old evidence paths, a synthetic
  generator for thousands of cheap cases, and a historical warehouse adapter
  that does not invent missing private observations.

After implementation:

- Added `deduction/model.py`, `collector.py`, `inference.py`, and `decision.py`.
  Runtime history contains observations only; witnessed kills/vents, alibis,
  parsed claims, pair exclusions, marginals, and vote decisions are rebuilt.
- `CREWBORG_DEDUCTION_HISTORY=1` skips the legacy event/social/suspicion fold,
  clears legacy scalar outputs, and routes crew meetings around the LLM and old
  solver. The final solve uses the 48-tick deadline after a provisional
  tick-240 communication pass.
- Added parity-aware vote thresholds, full evidence/pair audit, killed-player
  hard clears, ejection role uncertainty, exact utterance retention, and
  guards against unary “with me” clears and “near a vent” vent accusations.
- Added seeded synthetic and JSONL/warehouse replay evaluation. Seed 7 over
  1,000 synthetic histories produced 94.9% vote precision at 49.4% coverage
  with zero murder-clear violations. Six usable retained warehouse sets cover
  770 meetings while crewborg was alive and produced 63/73 correct
  counterfactual eject decisions (86.3% precision).
- Added focused coverage for persistence, deduplication, direct-action
  re-derivation, alibi constraints, death sources, runtime collection, legacy
  bypass, deadline behavior, known-role constraints, and non-monotonic parity
  policy. Final validation: 571 passed / 13 skipped, changed-file Ruff clean,
  and `git diff --check` clean.

## 2026-07-20 - Source-backed meeting commitment

Before implementation:

- Preserve a precise tick-240 public conclusion as an explicit provisional
  target. Re-solve at tick 360 and commit the ballot early only when the same
  target remains decisive and supported by at least two independent sources.
- Lower the early public threshold from 0.76 to the standard 0.65 solver bar
  while retaining the two-source requirement. Retained history found 22/22
  correct tick-240 opportunities at that gate versus 10/10 at the old gate.
- At the deadline, do not let an opaque private posterior turn a still-decisive,
  source-backed public conclusion into a skip. Prefer a fused private pick, then
  a fresh source-backed public pick, then the frozen meeting-entry fallback.
- Tighten no-source conclusions: structural evidence may unlock a ballot only
  when the candidate appears in every hypothesis surviving the structural
  facts alone, not merely when those facts amplify soft votes past a threshold.
- Validate the exact policy against retained histories before upload, then run
  a fresh fixed-roster crew A/B and measure activation, subject vote precision,
  vote timing, and impostor/crew ejections.

After implementation:

- Added a retained tick-240 public target and a tick-360 stability re-solve,
  lowered the two-source public gate to 0.65, added a source-backed public
  deadline fallback behind fused evidence, and required structural facts alone
  to force every source-free conclusion.
- Retained-history validation found 22/22 tick-240 targets stable and correct
  at tick 360. Final public replay produced 42/42 correct source-backed picks
  and no source-free guesses. The production image passed 556 tests with 13
  skips, Ruff, and local Gate 1.
- Uploaded inert `crewborg-solver-commit:v1`
  (`c2fe8244-fb51-4ddb-912c-1a0b0155d457`) with full telemetry. Its fresh
  matched 100/arm run completed without operational failures.
- Hosted wins were 35/100 candidate versus 45/100 control (`Fisher p=0.194`).
  Subject ballots moved 25 impostors / 3 crew / 66 skips to 29 / 8 / 50;
  crew-voter ballots moved 264 impostors / 90 crew / 216 skips to
  230 / 118 / 206. Candidate histories also had worse public claim precision
  and eight more subject kills.
- The early path activated five times, always against an impostor; all eight
  wrong candidate crew ballots occurred at the deadline. No source-free pick
  fired and no deadline public-fallback chat was confirmed. Five precise early
  activations cannot explain the ten-game aggregate deficit.
- Do not promote the bundled treatment. Split early voting and deadline
  fallback into separately flagged experiments and give public-only aggression
  an explicit board-state risk budget. Details:
  `docs/experiments/2026-07-20-source-backed-meeting-commitment.md`.

## 2026-07-20 - Auditable per-kill pair evidence

Before implementation:

- Preserve every sound hidden-kill alibi as an immutable event with victim,
  observation tick, possible death window, co-present players, and the players
  who could still have performed that kill. Do not replace or merge earlier
  events when later facts arrive.
- Recompute the complete impostor-assignment table from the raw claim, vote,
  direct-observation, and alibi ledgers. Correlation handling may change an
  item's scoring weight, but must not delete its underlying record.
- Replace the current alibi-only hard exclusion with a conservative per-kill
  likelihood. A pair with one continuously co-present member remains possible
  but is less likely; a pair whose surviving members were all co-present for
  the same kill is impossible.
- Expose stable evidence identities and per-hypothesis score contributions so
  a conclusion can be traced and reevaluated. Keep public spoken clears out of
  this treatment: first establish that the private pair posterior is calibrated.
- Gate on focused soundness and recomputation tests plus retained-history
  reachability and correctness. Upload inertly and run a fresh fixed-roster
  hosted comparison only if those checks show a real, correctly directed
  mechanism.

After implementation:

- Added immutable `KillAlibi` records and retained every usable hidden-kill
  observation in an append-only ledger. The solver now recomputes all pair
  hypotheses from raw evidence and exposes stable evidence IDs, exclusion
  reasons, and per-pair contributions whose sum reproduces each log weight.
- Retained-history reconstruction falsified the planned soft likelihood.
  Continuously rendered killers could be 61-68 pixels away while killing
  behind the observer's sight boundary, so screen visibility was not physical
  co-presence. A 28-pixel continuous-distance bound removed those violations,
  but two of three retained close observations were the non-killing impostor:
  "not this killer" is not evidence of crew when impostors specialize.
- Disabled singleton alibi weighting in production (`alibi_weight=0`). A kill
  event now has only its assumption-free consequence: exclude an assignment
  when it has no member who was both eligible to kill and not continuously
  co-present. A singleton event alone remains non-decisive, but can combine with
  an independent member-ineligibility fact. Events remain in the audit trail
  and never become lossy player-level clears.
- The exact uploaded image passed 551 tests with 13 skips and Gate 1. After the
  post-run possible-killer combination fix, latest source passes 552 tests with
  13 skips; focused solver/alibi tests passed 51/51. The complete pair audit
  added about 2 ms on a synthetic 20-claim solve.
- Fresh fixed-roster hosted comparison completed 200/200 without failures:
  28-pixel close co-presence won 47/100 crew games versus 42/100 for legacy
  screen visibility (`Fisher p=0.569`). Subject kill-death rate was 52% in both
  arms; player-vote precision was 28/28 versus 27/28.
- Full-tick reconstruction found only singleton alibi events in either deployed
  arm, so neither arm excluded a pair or changed the posterior through this
  channel. The five-point win difference is therefore outcome noise, not a
  treatment effect. Keep the ledger and audit infrastructure; do not promote
  either alibi gate as a gameplay gain.
- Fixed two event-warehouse streaming drift bugs exposed by the run: child
  downloaders now reuse the selected Python environment, and incremental builds
  preflight replay encodings before calling the current `build_request` API.
  The resulting warehouse contains 200/200 episodes, 10,479,375 events, zero
  failed extractions, and zero trace warnings.

## 2026-07-19 - Speak witnessed task clears

Before implementation:

- Add a default-off `CREWBORG_SPEAK_CLEARS` collaboration module that lets a
  living crewmate publish up to two watched real-task clears near meeting
  start. Keep the line chat-only and leave solver thresholds and ballots
  unchanged.
- Use an existing-parser-compatible sentence whose targets become direct
  `defend` claims with `sighting` evidence. Verify the parser contract in tests
  rather than assuming natural-language wording.
- Do not verbalize per-kill co-presence as a player clear. With two impostors it
  is only a relational assignment exclusion and requires a separate public
  claim representation.
- Conservative objective-replay reconstruction finds watched-task broadcast
  opportunities before the first meeting in 77-84% of the fresh constraint
  A/B games. Validate actual runtime activation locally, then compare the
  exact v3 artifact against the flag-on candidate in a fresh hosted run.

After implementation:

- Added the isolated `strategy/meeting/collaboration.py` policy and wired one
  chat-only attempt into each meeting. It ranks living watched-task clears by
  witnessed completion count, publishes at most two, and never stages a vote.
- Kept the feature default-off and limited it to living players whose own role
  is known to be crewmate. The emitted one- and two-target forms parse as
  direct `defend` claims with `sighting` evidence and preserve source identity.
- Repeats the objective fact in later meetings so teammates without persistent
  transcripts can still consume it. The existing solver handles correlated
  repeats with cross-meeting decay.
- Verified the production-image full suite (`554 passed, 13 skipped`), four
  focused parser/selection tests, two meeting-mode integration tests, Ruff,
  and `git diff --check`.

Hosted outcome and correction:

- The fresh 100/arm hosted test tied at 47 crew wins in each arm. Candidate v4
  emitted 65 lines with 88 clear mentions, 47 of which named fixed impostors.
- Exact replay reconstruction found 392/550 inferred completer attributions
  wrong, including 258 credits to impostors. The live client exposes only a
  global task decrement; it cannot identify which other player completed.
- Rejected inert v4 and removed the public emission path. Runtime now leaves
  the fitted model's `tasks_completed_watched` compatibility field at zero and
  supplies no task clear to the joint solver.
- Fixed XP artifact handling uncovered during analysis: optional results/log
  absence no longer causes repeated downloads; replay-complete XP episodes can
  stage validated slot-aligned result dimensions; and a WinReward identifies
  the winning role rather than each teammate independently.

## 2026-07-19 - Constraint-aware solver composition

- Disabled `tailing_self` collection for living crewmates while
  `CREWBORG_STICK=1`. Deliberately following a group is then policy-induced
  proximity, not evidence that the group is following crewborg. Imposter
  collection is unchanged.
- Bundled every solver input into immutable `SolverEvidence`, so counterfactual
  solves cannot silently omit independent channels such as per-kill alibis.
- Source-removal robustness now preserves structural facts and private
  evidence. Its crowd-pile cap is computed separately from public social
  evidence alone.
- Allowed a solver conclusion without a named accuser when a witnessed pin,
  hard clear, watched-task clear, or per-kill alibi is demonstrably necessary
  for that conclusion to clear the probability and margin gates. The solver
  still rejects vote-only consensus and does not let a non-constraining fact
  unlock it.
- Added diagnostics for the social-only crowd posterior and the
  without-constraints counterfactual, plus regression tests for stick-role
  isolation, alibi preservation, decisive constraints, and the vote-only
  guard.
- Production validation passed with 548 tests and 13 skips; changed-file Ruff
  and `git diff --check` passed.
- Deferred splitting the fitted suspicion prior by evidence channel. Chat and
  vote observations currently enter both the scalar fitted posterior and the
  solver's structured likelihoods; fixing that requires a non-overlapping
  residual solver prior with replay validation, not another local gate in this
  patch.
- Built and Gate-1 validated source `de63cbd`, then uploaded it inertly as
  `crewborg-solver-stick-alibi:v3`
  (`aa0415e5-a4ba-4bcd-a673-2212a0866eb5`) with stick, alibi, death-aware early
  solver, metrics, and all trace groups enabled.
- A fresh exact-roster 100/arm hosted A/B completed without failures. Crew
  wins moved 32 -> 48 (Fisher `p=0.030`, Newcombe 95% interval +2.4 to
  +28.8pp); mean loss score stayed flat at 6.09 -> 5.92.
- Subject votes moved from 24 impostors / 3 crew to 52 / 8 at unchanged
  conditional precision. Team impostor / crew ballots moved 196 / 139 to
  230 / 92, and impostor / crew ejections moved 6 / 21 to 15 / 12.
- Holding each public history fixed, v2 -> v3 solver replay added 10/10 correct
  picks in candidate histories: four constraint-only killed-player deductions
  and six single-source deductions rescued by the social-only crowd cap. It
  added one wrong, uncast opportunity in control history. This verifies both
  solver paths but also shows favorable candidate evidence, so the full
  outcome delta is not attributable to the bundled treatment.
- Hardened `skills/crewrift-event-warehouse/scripts/build_warehouse.py` after
  two avoidable workflow failures. It now detects raw versus zlib replay bytes,
  preflights one replay per Coworld version through the supplied expander,
  surfaces extraction messages, and exits nonzero on failures or hash
  warnings. Updated the default replay ref to verified 0.1.59 (`1cbd4de4`);
  four focused tests and Ruff pass.

## 2026-07-19 - Stick-with-group plus per-kill alibis

Before integration:

- Review the opt-in `crew-stick-alibi` branch as a modular layer on top of the
  death-aware early solver. Keep both tactics default-off and enable them
  together only in the combined hosted candidate.
- Preserve own-task completion as the movement priority. After own tasks are
  done, seek a real group rather than returning to spawn so crewborg can deny
  isolated kill windows and maintain useful co-presence evidence.
- Represent an alibi per kill, never as a permanent per-player clear. With two
  impostors, seeing one player during a kill proves only that they were not
  that killer; a joint assignment is impossible only when every impostor in it
  was co-present during the same kill.
- Review phase transitions, stale position handling, known-impostor pins, and
  idle escapes before hosting.

After integration and review:

- Kept the branch's modular structure: `modes/stick.py` owns group positioning,
  `strategy/alibi.py` owns co-presence state, and the solver consumes only
  per-kill sets. `CREWBORG_STICK` and `CREWBORG_ALIBI` independently disable
  their modules.
- Fixed the pinned-impostor exclusion. A known impostor who was co-present for
  a kill stays in that kill's alibi group; this correctly forces their partner
  outside the group instead of preserving an impossible pair.
- Fixed census reachability. Meeting frames have no live-world sprites, so
  census-discovered deaths now close their visibility interval at the last
  camera-ready Playing tick.
- Limited alibi tracking to living known crewmates and exposed the per-kill
  groups in solver diagnostics.
- Fixed stick liveness and targeting: require a recent cluster of at least two
  other living players, expire 96-tick-old fixes, and idle only while two
  cluster members are currently visible. A dispersed, stale, or departed group
  immediately falls back to Normal movement.
- Uploaded and hosted the combined v1 candidate in a fresh 100/arm comparison.
  Crew wins moved 41 -> 47 (`p=0.476`), post-task ticks with two or more visible
  players moved 31.8% -> 39.7%, impostor ejections moved 11 -> 19, and crew
  ejections stayed at 14. Tasks, standing-still penalties, and subject survival
  did not regress.
- Exact kill-tick replay exposed a remaining soundness bug: the visibility
  grace could bridge the killer's brief departure, and a kill rendered in view
  could label the killer co-present. V1 is therefore superseded and must not be
  submitted.
- Made alibi visibility strictly consecutive, reject witnessed kills, and
  require the victim to be absent beyond the three-tick ambiguity window.
  Corrected replay reachability is sparse: one usable two-player group in 100
  candidate games.
- Full corrected production validation passed with 543 tests and 13 skips;
  changed-file Ruff and `git diff --check` passed.
- Built and Gate-1 validated corrected source `38771ef`, then uploaded it
  inertly as `crewborg-solver-stick-alibi:v2`
  (`13bfb03f-d0ea-435c-b772-865db0e9a6d6`) with both tactics and full
  telemetry enabled.
- The fresh corrected replication completed 37/94 ops-filtered crew wins
  control versus 41/100 candidate (`p=0.884`). Pooled with the first batch,
  the combined tactic is 78/194 control versus 88/200 candidate, a
  directionally consistent but unresolved +3.8 points (`p=0.476`).
- Candidate non-win score improved from 4.63 to 6.47 in the replication.
  Together with the first batch's exact grouping, task, penalty, and death
  analysis, this supports retaining stick without claiming a proven outcome
  lift. Sound alibi constraints remain too sparse for data-backed tuning.

## 2026-07-19 - Death-aware persistent early solve

Before implementation:

- The first hosted early-public A/B completed 100/100 episodes per arm with no
  request failures. Its tick-240 line fired three times; every target was an
  impostor and every target was ejected. Team crew-target ballots and crew
  ejections moved down directionally, but crew wins were 40/100 candidate
  versus 44/100 control (`p=0.67`), so the outcome effect is unresolved.
- The current solver excludes dead players only from the live ballot ranking.
  It still assigns impostor probability to players killed between meetings,
  wasting fixed impostor mass and failing to reinterpret old claims through the
  now-certain crew role of each kill victim.
- Add killed players (`body` or newly-dead meeting `census`) as hard crew
  constraints on the full joint hypothesis space. Preserve ejected players in
  the hypotheses because an ejection does not reveal their role.
- Recompute the public posterior at tick 240 after the meeting census and any
  early current-meeting chat. Let the coordination gate use independent,
  non-self attributed sources accumulated across all meetings, rather than
  requiring both sources to repeat themselves in the current meeting.
- Retain the chat-only invariant: the early line never stages a ballot, and the
  deadline solver still recomputes from the final evidence window.
- Replay the exact production implementation over retained hosted history,
  measure target precision and coverage after the death constraints, then
  build, smoke, upload inertly, and run a fresh matched hosted A/B.

After implementation:

- Added hidden-kill victims as hard crew constraints in the joint hypothesis
  enumeration. Their marginals become zero, fixed impostor mass redistributes
  across the surviving possibilities, and old claims are reinterpreted under
  the victims' now-certain crew roles. Ejected players remain unconstrained.
- Excluded crewborg's own prior chat from solver evidence so a derived
  accusation cannot return in a later meeting as an independent source.
- Changed the tick-240 source gate from two current-meeting sources to two
  distinct non-self sources accumulated across the episode. The report still
  recomputes at tick 240, so the new meeting census and any early utterances
  update the line that is actually sent.
- Extended `tools/analyze_solver_history.py` with exact decision offsets,
  replay kill/ejection provenance, and early-chat reporting.
- Replayed 12 retained hosted arms at tick 240. Lowering the confidence gate to
  `0.65` admitted six false targets (`82/88`); retaining `0.76` produced
  `42/42` correct targets across 29 games. On the latest 200-game A/B alone it
  exposes 10/10 opportunities, versus three lines from the old current-meeting
  source gate.
- Focused solver/meeting validation passed (`55 passed`), changed-file Ruff and
  `git diff --check` passed. Full image validation and hosted evaluation follow.
- The fresh 100/arm hosted test finished 42 -> 43 crew wins (`p=1.0`). The
  mechanism was precise and more active: candidate tick-241 lines fired five
  times, all at real impostors; team impostor-target ballots moved 189 -> 222,
  crew-target ballots 127 -> 102, impostor ejections 9 -> 15, and crew
  ejections 17 -> 14.

## 2026-07-19 - Early public-solver coordination

Before implementation:

- The fresh crowd-cap A/B improved the subject's already-high vote precision
  from 24 impostors / 1 crew to 25 / 0, but team ejections moved from 18
  impostors / 8 crew to 16 / 14. The subject did not vote for any of the 14
  ejected crew; this iteration targets coordination rather than ballot safety.
- Replay transcripts show the structural timing gap: fixed-roster crew commonly
  cast their first ballots about 300 ticks into a meeting, while crewborg's
  accurate solver accusation arrives at tick 1,152 after those votes are final.
- Add one optional, chat-only solve at tick 240. It must use public claims and
  ballots only, excluding private suspicion, witnessed pins, and task clears,
  so the hosted path exactly matches the replay-calibrated mechanism.
- On the six correlation/timing/confirmation selection arms, require
  `P(imposter) >= 0.76` and at least two attributed sources in the current
  meeting. That region contains 29/29 correct targets.
- Hold out both guidance experiments and the fresh 200-game crowd-cap A/B. The
  selected gate is 29/29 there as well, for 58/58 pooled early targets. The
  early line does not stage or alter the final tick-1,152 ballot.
- Also react to any public ballot against crewborg's known-crewmate identity
  with a truthful self-defense line. Five of the 22 fresh crew ejections hit
  the subject itself; this branch uses role certainty rather than a fitted
  posterior and likewise does not stage a ballot.

After implementation:

- Added `CREWBORG_SOLVER_EARLY_CHAT=1`, with a one-shot public-only solve at
  tick 240. The early path excludes private suspicion, witnessed-impostor pins,
  and watched-task clears; requires `P(imposter) >= 0.76` and two current-meeting
  sources; and sends chat without staging or changing a ballot.
- Added one truthful self-defense response when another player publicly votes
  against crewborg's known-crewmate identity. It asks the field to skip, does
  not counter-vote, and cannot replace the ordinary tick-1,152 solve.
- The exact implemented early gate reproduces 29/29 correct targets on the six
  selection arms and 29/29 on the held-out guidance plus crowd-cap arms.
- Verified 68 focused meeting/parser tests, the production-image suite (`526
  passed, 13 skipped`), changed-file Ruff, `git diff --check`, and a local
  `scn_vote_basic` Gate 1 with a valid result/replay and zero vote,
  connect, or disconnect timeouts. The short smoke timer exercises the
  deadline path; unit and replay tests cover the tick-240 branch.

## 2026-07-18 - Single-source crowd-pile cap

Before implementation:

- Retire the early-guidance gameplay path after two 100/arm hosted tests emitted
  zero guidance lines. Preserve both uploads and outcomes as rejected experiment
  history; do not interpret either scoreboard difference as a treatment effect.
- Target the confirmed solver's wrong crew votes without changing its global
  posterior threshold or multi-source decisions. Reuse the existing
  leave-one-source solve only when exactly one attributed accusation source
  supports the candidate.
- On six pre-guidance arms, reject a single-source pick when its marginal stays
  above `0.39` after removing that source. All 11 correct single-source picks
  fall at or below `0.371`; all three false picks remain at or above `0.419`.
- Hold out the four fresh guidance arms from threshold selection. The
  pre-registered `0.39` cap retains all 6 correct single-source picks and rejects
  all 8 false picks there. Across all ten arms it would remove 11/24 false
  decisive picks while retaining 167/167 correct picks.
- Keep the existing lower counterfactual gate: the target must still be the
  leading candidate after source removal. The new upper cap rejects only the
  opposite failure mode, where a nominally single-source conclusion is actually
  sustained by a correlated public ballot pile.

After implementation:

- Removed the rejected early-guidance runtime, configuration, and tests. The
  confirmed deadline solve and persistent evidence ledger are unchanged.
- Added `CREWBORG_SOLVER_ROBUST_MAX_P=0.39` to the existing single-source
  counterfactual. Values below zero disable the upper cap independently of the
  existing lower bound.
- Replayed the exact production image across all ten hash-complete retained
  arms. The implemented gate reproduces 167/180 correct decisive picks (92.8%),
  removing 11 false picks and zero correct picks from the 167/191 baseline.
- Verified 62 focused meeting/parser tests, the production-image suite (520
  passed, 13 skipped), changed-file Ruff, and `git diff --check`.

Hosted result:

- Fresh matched 100-game arms completed without request or subject operational
  failures. The confirmed solver control `xreq_f5242562` won 35 games and the
  crowd-cap candidate `xreq_3da4e8ee` won 39 (`+4pp`, Fisher `p=0.66`).
- Subject ballots improved from 24 impostors / 1 crew / 75 skips to 25 / 0 /
  75. Production replay showed the cap actively removed two false candidate
  picks; applying it retrospectively to control removed one correct pick.
- The team-level crew-kill result did not improve: crew ejections increased
  8 -> 14, impostor ejections decreased 18 -> 16, and crew-target ballots
  increased 83 -> 111. The subject did not vote for any of the 14 ejected crew.
- Keep the cap as a direct ballot-precision safeguard, but do not attribute the
  noisy win delta to it or treat it as a solution to team coordination. The
  next iteration must speak before the fixed field's roughly tick-300 ballot
  wave and separately measure subject complicity, subject self-ejections, and
  total crew ejections.

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

Hosted v2 result and rejection:

- Fresh matched requests completed 100/100 with zero failures. The confirmed
  solver control `xreq_af54157d` won 46 crew games and guidance v2
  `xreq_55ee44df` won 37 (`-9pp`, Fisher `p=0.25`).
- Guidance again emitted zero lines in 158 candidate meetings. Candidate public
  replay votes hit impostors 24 times and crew 9 times, versus 35 and 6 for
  control. All crew players cast exactly 132 crew-target ballots in each arm.
- Candidate ejections were 16 crew and 8 impostors, versus 17 crew and 20
  impostors in control. With no treatment activation, these differences are run
  variance and do not estimate guidance.
- Public replay still exposes one 1/1 correct strict-gate opportunity in the
  candidate history. The discrepancy between replay cutoff and runtime remained
  unresolved after the bounded timing repair, so guidance was rejected and
  removed rather than spending another hosted run on timing guesses.

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
