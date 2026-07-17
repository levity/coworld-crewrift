# Changelog

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
