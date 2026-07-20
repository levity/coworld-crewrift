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

PYTHONPATH=players/crewborg:players/crewborg-aaln:. \
  python -m pytest players/crewborg/crewborg/tests

PYTHONPATH=players/crewborg:players/crewborg-aaln:. \
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
