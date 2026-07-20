# Stick-with-group and per-kill alibis

## Hypothesis

After its own tasks are complete, crewborg can contribute more by staying with
a real group than by returning to spawn. Co-presence may both deny isolated
kill windows and constrain the joint meeting solver when a kill occurs
elsewhere.

## Modular design

The tactics remain independently opt-in:

- `CREWBORG_STICK=1` selects `StickMode` only for a living known crewmate.
  `NormalMode` still owns and completes every task. Only its post-task
  return-to-start/idle result may be replaced.
- `CREWBORG_ALIBI=1` records one co-present set per hidden kill. It never adds a
  permanent player clear. The solver excludes an impostor assignment only when
  all members were continuously visible through the same victim's possible
  death window.

The combined hosted artifact will carry both flags on top of the death-aware
persistent early solver, while the matched control will be the same solver
artifact with both tactics absent.

## Review fixes

The branch review found and corrected three material issues:

1. A known-impostor pin was removed from alibi groups. This was backwards: if
   the pinned impostor was co-present, their partner must be outside that same
   group. Pins now remain in the joint exclusion.
2. Census-discovered deaths were processed on a sprite-less meeting frame and
   could never produce an alibi. Their interval now ends at the last
   camera-ready Playing tick.
3. Stick mode could stop beside one stale position indefinitely. It now
   requires a recent two-player cluster, expires fixes after 96 ticks, and
   idles only while two members are visible on the current tick. Otherwise it
   falls back to Normal movement.

Alibi tracking is limited to living known crewmates, and solver reports expose
the exact per-kill groups for hosted mechanism verification.

## Local gate

- 75 focused alibi, stick, solver, and strategy tests passed.
- The complete production suite passed with 541 tests and 13 skips.
- Changed-file Ruff and `git diff --check` passed.

The amd64 image passed the local liveness smoke with valid results, replay, and
all eight player logs. It was uploaded inertly as
`crewborg-solver-stick-alibi:v1`, immutable version
`900dd8a4-7c52-468d-9dc6-53ff7d27734a`, from source `7f0382f` and image
`sha256:ae7eb0c762db068913f9d049ecb3f05c96cccc054549d3ebec7899c401e0c31b`.
It has not been submitted to a league.

## Hosted result

Fresh 100-game forced-crew requests completed without failures:

- Control, death-aware early solver:
  `xreq_7f508567-1c7c-4984-a33c-5f9d6e254bdd`
- Candidate, early solver plus stick and alibi:
  `xreq_fed7ee5f-d5ff-4201-8590-59c1ae174db3`

Crew wins were 41/100 control and 47/100 candidate, a directional +6 points
that remains noisy (`p=0.476`). The non-win score component was essentially
flat (697 control, 701 candidate), and the candidate completed 767 tasks versus
766, incurred 66 standing-still penalties versus 69, and died in 2 games
versus 3. This rules out a broad task, idle-penalty, or survival regression.

Stick mode changed the intended objective behavior after all eight tasks:

| Post-task visibility | Control | Candidate |
| --- | ---: | ---: |
| Alive Playing ticks with 2+ players visible | 31.8% | 39.7% |
| Mean visible players per alive Playing tick | 0.997 | 1.052 |
| Median per-game 2+ visible fraction | 6.7% | 15.0% |

Team impostor-target ballots rose 202 -> 288, crew-target ballots rose
99 -> 122 because the candidate arm had substantially more total ballots
(301 -> 410), impostor ejections rose 11 -> 19, and crew ejections stayed 14.

## Soundness follow-up

Exact kill-tick reconstruction found that v1's alibi evidence was not sound.
The three-tick visibility bridge could hide the killer's brief departure to
perform a kill, and a victim killed while still rendered could cause the
visible killer to be labeled co-present. The v1 hosted result therefore
supports stick behavior but cannot validate alibi constraints.

The correction makes co-presence strictly consecutive, rejects deaths with a
witnessed-kill event, and requires the victim to have been out of view for more
than three ticks before the kill window closes. Replay reconstruction estimates
only one usable two-player alibi group in 100 v1 candidate games after applying
these sound guards, so alibi is a sparse secondary signal. Full corrected
validation passes 543 tests with 13 skips.

## Corrected v2 replication

The corrected source at `38771ef` built as
`sha256:bf3408d9f2fc1881158dfafddf0147daec02b670e142429fa05dc896f0319abb`.
The production suite passed with 543 tests and 13 skips, and Gate 1 completed
cleanly with results, replay, and all eight player logs. The image was uploaded
inertly as `crewborg-solver-stick-alibi:v2`, immutable version
`13bfb03f-d0ea-435c-b772-865db0e9a6d6`. It has not been submitted.

A fresh replication used the same pinned roster and forced roles:

- Control, death-aware early solver:
  `xreq_ed4bf40f-643f-496e-b7a1-edaba0bb37e5`
- Candidate, corrected early solver plus stick and alibi:
  `xreq_5e0a4bf8-7c32-4166-8d04-cfc15d43033b`

Both requests completed 100/100 episodes without request failures. Six control
episodes returned all-seat `-100` operational outcomes and were excluded. The
valid result was 37/94 control versus 41/100 candidate, +1.6 percentage points
(`p=0.884`; Newcombe 95% interval approximately -12.0 to +15.1 points).
Candidate non-win score averaged 6.47 versus 4.63 control, so the corrected
policy did not trade task contribution or idle penalties for its small win
direction.

Across the original and corrected batches, ops-filtered wins are 78/194 control
and 88/200 candidate, +3.8 points (`p=0.476`; approximate 95% interval -5.9 to
+13.4 points). This is directionally consistent but unresolved. The first
batch's exact replay analysis already establishes that stick mode increases
post-task grouping without a task, penalty, or survival regression. Corrected
alibi evidence is too sparse to optimize from these samples. Retain the
corrected combined candidate for further evaluation; do not tune alibi
thresholds or add suspicion-based group exclusions without a new discriminating
mechanism test.
