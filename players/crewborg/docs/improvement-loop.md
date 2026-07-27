# The improvement loop — a runnable checklist

One pass: get data → find the weakness → propose three fixes → build one → prove it
locally → prove it hosted → ship or discard. Follow it in order; each step says what
"done" looks like so you can tell whether to continue.

Read [`WORKING_CONTEXT.md`](WORKING_CONTEXT.md) first for the current champion, its
configuration, and the open threads. Read [`best_practices.md`](best_practices.md) for the
measurement disciplines these steps assume.

---

## 0. Environment

```bash
export CREWBORG_WT=/path/to/this/worktree      # env.sh REFUSES to guess; it will error out
cd /home/exedev/projects/softmax/crewrift-analysis && source ./env.sh
```

`crewrift-analysis` is a **separate repo** holding the analysis tooling: the signals panel
(`crew_play_signals.py`), `normalize_selfplay.py`, `ab_analysis.py`, `selfplay.sh`, and
`env.sh`, which exports `$CREWBORG_VENV`, `$FETCH_TOOL`, `$XP_TOOL`, `$WH_PROJ`. Read its
README before using them.

**Done when:** `env.sh` prints the worktree it took tooling from, and `$CREWBORG_VENV/coworld` runs.

## 1. Get data you can actually analyse

**League standings tell you rank; league episodes tell you nothing about behaviour.**
League/tournament episodes carry `results: false`, no logs and no `policy_artifacts`. The
only league signal is `episode.json -> policy_results` (per-seat policy, version, reward).

```bash
# Standing and champion status
uv run python skills/coworld-policy-lifecycle/scripts/policy_lifecycle.py monitor --name crewborg-lw
# League rewards (rank/score context only)
"$CREWBORG_VENV/python" "$FETCH_TOOL" --policy crewborg-lw --version <N> -n 30 --no-replay -o <dir>
```

For anything behavioural — beliefs, votes, solves — **fire your own experience request**
(`coworld-experience-requests`) and read its traces. Pin roles when you need both roles
guaranteed; rotate seats (`slot: -1`) when you want an unbiased win rate. Uploads already
carry `CREWBORG_METRICS=1 CREWBORG_TRACE_GROUPS=all`, so the traces are complete.

**Done when:** you have episode dirs containing `artifacts/policy_artifact_*.zip`.

## 2. Score it

| question | tool |
|---|---|
| Per-seat signals, 22 of them, `dec`/`obs` tagged | `crewrift-analysis/crew_play_signals.py` (**the panel**) |
| Belief quality: Brier, log loss, AUC, calibration | `tools/decision_quality.py` |
| Fast batch overview + heat map | `crewrift-survey` skill |
| Free local games into the same panel | `crewrift-analysis/normalize_selfplay.py` |
| Deep event queries | `crewrift-event-warehouse` skill |

**Two filters, always.** Drop episodes with `connect_timeout`/`disconnect_timeout` (ops
failures, not strategy). Restrict decision-level rates to **living seats** — a dead seat
still emits `deduction_history_decision` with `action="eject"` and those never become
ballots (26 of 37 in one 16-episode batch). Use the seat's own `domain.player_died`;
`decision_snapshot.self` is null during every Voting phase and is not a liveness signal.

**Done when:** you can state, per role, what the policy did and how good its beliefs were.

## 3. Diagnose, then propose three

Turn signals into a few *mechanistic* hypotheses pinned to code (`crewrift-diagnose`).
Write **three** candidate improvements, each with: the mechanism, the file it touches, the
pre-registered signal that must move, and the guard that must not regress.

Rank by **cost to falsify**, not by hoped-for size. Prefer a change you can test offline
for free over one that needs games.

**Done when:** three options are written down and one is chosen, with the reason.

## 4. Build it

- One component per change, so the next measurement is attributable.
- Tunable knobs go in config, not logic: add a preset family in `deduction/config.py`
  behind its **own** env var. One var per lever — an A/B must move one thing.
- **Default off.** The unflagged path must stay byte-identical.

**Done when:** `uv run --group dev pytest` is green with zero skips, touched-file
`ruff check` is clean, and `git diff --check` passes.

## 5. Prove it offline first — it is free

Re-run the change over recorded histories before buying games; the gate is the
pre-registered signal from step 3 moving, with the guard holding. Existing examples:
`tools/kill_window_counterfactual.py`, `tools/sweep_speaker_trust.py`,
`tools/evaluate_deduction.py`, `tools/sweep_decision_gate.py`.

**Done when:** the target signal moved and the guard held, or the idea is dropped here at
zero cost.

### Is this a bug fix or a strategy change?

Ask it here, because the answer decides whether steps 8's hosted A/B is worth buying.

A **bug fix** is a change where the code was not doing what it was written to do, the
cause is mechanical, and the offline replay shows the defect directly rather than
inferring it from an outcome. `CREWBORG_KILL_ANCHOR` is the pattern: the kill-range test
compared two different anchors for our own position, and the replay showed 99.7 % of
17,984 non-landing strike ticks were out of range once measured consistently. Nothing
about that needs a win rate to confirm — there is no version of the game where measuring
a distance from the wrong point is correct.

A **strategy change** is a change where the code already did what it was written to do
and you are arguing the intent should be different — a threshold, a target-selection
rule, a new behaviour. That is a claim about the game, and only games can settle it.

**Do not spend a hosted A/B to re-establish that the defect is real.** That part is
settled by the offline replay, and win rate is a one-bit-per-game measure that cannot
resolve below roughly +15pp at n=100.

**But do run one cheap outcome check before the fix becomes the baseline** — because a
bug fix changes *behaviour in the field*, and that is a separate question from whether
the arithmetic was wrong. `CREWBORG_KILL_ANCHOR` is the cautionary case as well as the
worked example. The mechanism moved exactly as designed (wasted strike ticks/episode
5.7 → 0.8, p = 0.001, and 93 % of the control's wasted ticks were genuinely out of
range against 0 % of the candidate's) — and the outcome did **not** improve: imposter
win 85.0 % → 76.0 % (p = 0.108), kills/episode 1.60 → 1.53 (p = 0.492), our ejection
rate 15 % → 20 %. Neither outcome number is significant at n = 100, so the fix is not
established as harmful; what is established is that it bought nothing, and that the
broken behaviour had a *second* effect nobody had modelled — standing still mashing A
was accidentally acting as camouflage.

The lesson generalises: **"the code was wrong" does not imply "the code was worse."**
A defect that has been in play for a while is load-bearing in ways the diff does not
show. Fix it, but measure the fix's behavioural consequence before building on top of it.

The thing genuinely not worth buying is a *large* A/B, or an A/B whose question is "was
the defect real". One matched run at n≈100 per arm, read on the mechanism with outcomes
as guards, is enough to catch a fix that quietly changes how the policy is perceived.

Then A/B the *next* strategy change **on top of the fix**: baseline = bug fix, treatment
= bug fix + change. Both arms carry the fix, so it is not a variable, and the comparison
answers the question you actually have.

The trap this avoids: A/B-ing bugfix-vs-broken. It will usually "win", and the number it
produces is a measure of how broken the old arm was, not of anything you can build on.

## 6. Gate 1 — local smoke

```bash
uv run python skills/build-and-upload/scripts/upload_and_log.py --dry-run ...   # check the command
./tools/build/build_player.sh --tag crewborg:<label>
# then a local episode with the SHIPPING env, not defaults
```

Run the smoke with the exact env you intend to upload, and read the traces back: a Gate-1
on default config validates behaviour you are not shipping. Confirm from
`domain.crew_brain_config` that the arm resolved as intended, and that the new mechanism
actually fired.

**Done when:** clean connect/play/exit, zero connect/disconnect/vote timeouts, and the
traced config matches the intended arm.

## 7. Upload

```bash
uv run python skills/build-and-upload/scripts/upload_and_log.py \
    --image crewborg:<label> --name crewborg-lw \
    --purpose <what-this-is-for> --note "one line" \
    --secret-env ... --secret-env ...
```

Uploading is inert and ungated. The wrapper tags the version and writes its
`version_log.md` row; commit that row.

**Done when:** `versions.py --name crewborg-lw` shows the new `vN` and its tags round-trip.

## 8. Measure hosted — strategy changes only

**Skip this step for a bug fix** (see step 5). Upload it, fold it into the baseline, and
come back here when you have a strategy change to test on top of it.

Matched and fresh (`crewrift-ab`), decomposed **by role**, ops-filtered. Homogeneous
rosters are the sensitive detector; a mixed 4-2-2 is the realistic confirmer and carries
about two-thirds of the treatment. Nothing is promoted on a homogeneous result alone.

Both arms carry every bug fix shipped since the last A/B — the treatment is the one
strategy lever under test and nothing else.

**Done when:** the pre-registered primary and guard both have a verdict.

## 9. Ship, or take another tack

**Gate 2 is the human's call** — submission is public and effectively irreversible. Bring
the verdict and ask; do not submit on your own initiative.

```bash
uv run coworld submit crewborg-lw:vN --league <id> --auto-champion lineage
```

Re-resolve the league id live (`coworld leagues`). `lineage` replaces only our own prior
champion. Then watch it qualify (`policy_lifecycle.py monitor --name crewborg-lw`).

If it did not show promise: record the null in `CHANGELOG.md` with the mechanism data,
update `WORKING_CONTEXT.md`, and return to step 3 with the next option — a null that is
explained is worth more than one that is merely recorded.
