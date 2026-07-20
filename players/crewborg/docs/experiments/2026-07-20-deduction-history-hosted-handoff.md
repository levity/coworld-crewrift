# Append-only deduction history hosted A/B handoff

## Objective

Run the first hosted test of the complete append-only deduction path. Compare it
with the best retained legacy meeting configuration from the same source image,
not with a stale uploaded policy.

The treatment is the architecture switch itself:

- control: legacy suspicion, social/alibi ledgers, and persistent meeting solver;
- candidate: raw append-only observations, pure derived evidence, complete joint
  assignment scoring, and parity-aware board policy.

Stick positioning remains enabled in both arms. The candidate deliberately
ignores the legacy alibi and meeting-solver flags after
`CREWBORG_DEDUCTION_HISTORY=1` selects the replacement crew path. Impostor
behavior is identical between the two uploads, although the hosted subject is
forced to crew for this first test.

## Frozen source and validation

Build both policies from branch `crewborg-deduction-history`. At handoff, the
validated source commit is `9c80b98` (`feat(crewborg): add append-only
deduction history`). This document is committed on top without changing player
behavior.

Before upload:

```sh
git status --short
git rev-parse HEAD

PYTHONPATH=players/crewborg:. \
  python -m pytest players/crewborg/crewborg/tests

PYTHONPATH=players/crewborg:. \
  python players/crewborg/tools/evaluate_deduction.py --games 1000 --seed 7
```

The last activated amd64 Gate 1 completed two sequential games and eight
meetings without a timeout or inference error. Repeat Gate 1 only if source or
runtime configuration changes after this handoff.

## Build and upload

Build one image. Upload that exact image twice under distinct policy names so
both arms are reconstructible and can run concurrently:

```sh
docker build --platform linux/amd64 \
  -f players/crewborg/crewborg/coworld/Dockerfile \
  -t crewborg:deduction-history-ab players/crewborg
```

The common behavior configuration reproduces the retained constraint-aware
solver, early public coordination, stick positioning, and sound alibi
collection. Full telemetry is mandatory.

```sh
COMMON_FLAGS=(
  --run python --run -m --run crewborg.coworld.policy_player
  --secret-env CREWBORG_SOLVER=1
  --secret-env CREWBORG_SOLVER_VETO=0
  --secret-env CREWBORG_SOLVER_DEFER=0
  --secret-env CREWBORG_SOLVER_EARLY_CHAT=1
  --secret-env CREWBORG_STICK=1
  --secret-env CREWBORG_ALIBI=1
  --secret-env CREWBORG_METRICS=1
  --secret-env CREWBORG_TRACE_GROUPS=all
)

uv run coworld upload-policy crewborg:deduction-history-ab \
  --name crewborg-deduction-history-control "${COMMON_FLAGS[@]}"

uv run coworld upload-policy crewborg:deduction-history-ab \
  --name crewborg-deduction-history "${COMMON_FLAGS[@]}" \
  --secret-env CREWBORG_DEDUCTION_HISTORY=1
```

Record both immutable policy UUIDs, image digest, source commit, and complete
runtime configuration in `crewborg/version_log.md` immediately after upload.
Do not submit either policy to a league.

## Matched request

Use 100 forced-crew episodes per arm for continuity with the retained solver
experiments. Pin the complete roster and roles. Start from
`2026-07-20-source-backed-commitment-control.json`, changing only:

- slot 0 control policy to `crewborg-deduction-history-control:v1`;
- slot 0 candidate policy to `crewborg-deduction-history:v1`; and
- each request's notes.

Keep the established roster:

| Slot | Policy | Role |
| ---: | --- | --- |
| 0 | control or candidate | crew |
| 1 | `crewborg-aaln:v25` | crew |
| 2 | `notsus:v130` | crew |
| 3 | `jordan-crewborg-aaln:v1` | crew |
| 4 | `crewrift-prime-notsus-richard:v4` | crew |
| 5 | `crewborg:v107` | crew |
| 6 | `daveey-prime-notsus:v2` | imposter |
| 7 | `softmaxwell-crewborg:v34` | imposter |

The existing target is
`cow_52d06063-dfa8-45fc-9533-a5365a71a04d`. Confirm it and every policy
version against the live API before posting; identifiers and available
versions may drift.

```sh
S=players/crewborg/skills/coworld-experience-requests/scripts/experience_request.py

uv run python "$S" create /tmp/deduction-control.json --check-schema
uv run python "$S" create /tmp/deduction-candidate.json --check-schema

# Post back-to-back in the same window.
uv run python "$S" create /tmp/deduction-control.json
uv run python "$S" create /tmp/deduction-candidate.json
```

Verify the readback has 100 episodes, the exact eight policy versions, slot 0
as crew, and slots 6-7 as impostors. For each request over 16 episodes, start
the XP dashboard and give the human its local URL as required by
`docs/user_preferences.md`.

## Stream artifacts and warehouse

Determine the deployed Crewrift version from the first completed episode and
build the matching replay expander:

```sh
players/crewborg/tools/build_expand_replay.sh \
  --ref <coworld-version> --out /tmp/expand-<coworld-version>
```

Start one crash-safe stream per arm immediately after obtaining the request
IDs:

```sh
S=players/crewborg/skills/crewrift-event-warehouse/scripts/stream_eval.py

uv run python "$S" --xreq <control-xreq> \
  --out /tmp/deduction-history-control-wh \
  --expand-replay /tmp/expand-<coworld-version> --workers 2

uv run python "$S" --xreq <candidate-xreq> \
  --out /tmp/deduction-history-candidate-wh \
  --expand-replay /tmp/expand-<coworld-version> --workers 2
```

Do not run both full-tick expansion processes concurrently on the current
2-vCPU VM. It is fine to let artifact downloads overlap, but serialize or
otherwise coordinate the CPU-heavy warehouse builds. Check load, RAM, swap,
failure count, and `trace_warning` count before increasing workers.

## Precommitted analysis

### Operational and activation gates

The candidate is invalid as a mechanism test if any of these fail:

1. The two requests are not exact roster/role matches.
2. Candidate meetings do not use `domain.deduction_history_early` and
   `domain.deduction_history_decision` whenever slot 0 is living crew and has
   enough meeting time.
3. A candidate meeting falls through to the LLM, legacy solver, or legacy
   suspicion vote.
4. Inference fails, misses the 48-tick backstop, or causes vote/connect/
   disconnect timeouts.
5. A body/census murder victim retains nonzero impostor probability or becomes
   a vote target.
6. Factor telemetry cannot reconcile each assignment's factors with its logged
   weight and normalized posterior.

Hosted XP has not consistently exposed policy-log artifacts in earlier runs.
Check this as soon as the first candidate episode completes. If logs are
absent, public replay can establish chat, ballot, timing, death, and outcome
behavior, but not private-factor activation. Report that observability limit
explicitly rather than treating missing traces as zero activations.

### Primary behavioral measures

Ops-filter connect/disconnect failures before behavioral comparison. Report:

- subject ballots against impostors, crew, and skip;
- subject ballot precision and non-skip coverage;
- subject ballot timing within each meeting;
- team impostor and crew ballots and ejections;
- correct and incorrect early accusations and spoken clears;
- subject deaths, ejections, tasks, score, and crew wins;
- inference latency, history size, evidence count, and assignment-table size;
- posterior calibration by probability bucket; and
- decision reasons split by ordinary, parity-danger, parity-edge, and skip.

The treatment passes the first hosted screen only if it is operationally clean,
casts no murder-victim or structurally impossible votes, does not increase the
number of subject crew ballots, and retains at least 75% of the control's
non-skip ballot coverage. Subject impostor-vote precision should be no worse
than control. Crew wins and team ejections are important secondary outcomes,
but 100 games per arm are not sufficient to promote or reject the architecture
from win rate alone.

### Same-history counterfactual

Outcome arms receive different game histories even with a matched roster.
Therefore also compare both policies at each eligible meeting on the same
public history:

1. Reconstruct exact public utterances, votes, deaths, meeting callers, and
   live targets from each arm's warehouse.
2. Run `tools/analyze_solver_history.py` for the legacy public solver and
   `tools/evaluate_deduction.py --warehouse ...` for the new public-only path.
3. Join by episode and meeting and score both point-in-time targets against the
   fixed true impostors.
4. Inspect every disagreement, especially wrong ejects near parity, correlated
   crowd piles, post-death target changes, and abstentions where one policy had
   decisive evidence.

This counterfactual does not recreate the candidate's private world
observations. Where factor telemetry exists, rescore its logged assignment
table locally and retain the complete contribution audit for later weight
sweeps.

## Closeout

Write policy UUIDs, request IDs, warehouse locations, operational exclusions,
all precommitted measures, point-in-time disagreements, and the verdict back
into this document. Update `WORKING_CONTEXT.md`, `TENTATIVE_LESSONS.md`,
`CHANGELOG.md`, and `crewborg/version_log.md`, then commit before proposing the
next gameplay change.

## Hosted result

Both arms completed 100/100 forced-crew episodes on Crewrift 0.1.59 with the
exact pinned roster and no XP request failures:

| Arm | Policy UUID | Request |
| --- | --- | --- |
| candidate | `0d337bd5-0586-45b5-a574-61bff862eae9` | `xreq_79223776-244a-48bf-a97e-714890b03ba4` |
| control | `7a700652-3279-42a0-a619-098c94fad5cc` | `xreq_0de29f24-339b-41d5-a759-8a7af7181d65` |

The arms used the same image, `sha256:61011068b0e358fbfe5b27d087f2313210bbf98b5ba65a6c8717b36d89173def`,
built from `7295db0` with behavior frozen at `9c80b98`. Hosted policy logs and
separate result artifacts were unavailable. Public replay establishes chat,
ballot, timing, death, task, score, and outcome behavior, but cannot reconcile
the private factor table or measure solve latency. One candidate replay,
`ereq_ae5b86aa-75fd-4614-a218-1d10f97ac4b3`, stopped expansion on a tick-5060
hash failure. Its authoritative win remains in outcome counts; its episode is
excluded from event-derived behavior.

### Outcomes and observed behavior

Candidate crew wins were 37/100 versus 42/100 control (difference -5 points,
two-sided Fisher `p=0.563`). Mean subject score was 43.78 versus 48.63 and mean
tasks were 7.65 versus 7.68. Candidate/control subject outcomes were 51/56
killed, 5/3 ejected, and 44/41 surviving.

On clean public traces, subject ballots were:

| Arm | impostor | crew | skip | non-skip precision | coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| candidate | 21 | 3 | 69 | 87.5% | 25.8% |
| control | 25 | 0 | 44 | 100% | 36.2% |

Candidate coverage retained 71.2% of control, below the precommitted 75% floor,
and candidate crew ballots increased from zero to three. Team crew ballots were
229 impostor / 109 crew / 270 skip in the clean candidate traces and 182 / 94 /
252 in control. Candidate games ejected 16 impostors and 23 crew; control
ejected 10 and 15. The higher ejection volume did not improve team ejection
precision (41.0% versus 40.0%).

The candidate emitted 18 subject lines at exactly the intended offsets. At
tick 241 it made ten witnessed-action accusations, three public accusations,
and one clear; all 14 statements were correct. At tick 1153 it made four public
accusations, two correct and two wrong. Every ballot arrived at the deadline,
with median non-skip offsets 1160.5 ticks candidate and 1163 control. Public
replay therefore confirms activation and timing, but not the unavailable
private factor telemetry.

### Same-history solver comparison

After excluding the hash-failed episode, both analyzers covered the same 93
candidate meetings. The legacy public solver selected 17 targets and got 16
correct (94.1%); the new public-only policy selected 18 and got 14 correct
(77.8%). They shared 13 selections (12 correct, one wrong). The new path dropped
four correct legacy selections and added five selections, only two correct. On
the 69 control-history meetings, legacy selected 1/1 correctly and the new path
selected 3/4 correctly.

Three of the four candidate-history new-solver errors had no accusation against
the selected target: two public ballots alone satisfied the generic
"independent sources" gate. Requiring at least one active accusation in addition
to posterior support removes those three errors and no correct selection on
these histories, moving 14/18 to 14/15. The remaining wrong Green pick had two
explicit crew accusations and a five-source ballot pile; it is not removable
by that narrow gate. Raising posterior thresholds is counterproductive here:
the candidate default is 14/18, while 0.70/0.85 is 9/13 and 0.75/0.90 is 7/11.

The cheap synthetic distribution was also too favorable: its pre-upload result
was 94.9% precision at 49.4% coverage, versus 77.8% and 19.4% on fresh public
history. Synthetic speakers choose chat and ballot targets independently and
do not form persistent or shared false beliefs, so it omits exactly the
correlated pile-ons that produced hosted errors.

## Verdict and next step

Do not promote or submit this candidate. The win-rate difference is unresolved,
but the treatment independently fails the precommitted ballot-precision,
crew-ballot, and coverage gates. Preserve the successful early/direct path.
Before another hosted run, require explicit accusation or structural/direct
support for a public eject while still allowing ballots to adjust the joint
posterior. Validate that gate on every retained warehouse and add correlated,
persistent latent beliefs to the synthetic generator so future cheap screens
stress the observed failure mode.
