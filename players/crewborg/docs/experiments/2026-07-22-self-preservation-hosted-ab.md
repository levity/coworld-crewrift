# Self-preservation movement hosted A/B

## Question

Does conservative suspect escape plus bounded group-aware task selection reduce
the subject's murders and one-on-one killer exposure without harming task
completion, voting, or crew outcomes?

## Design

The control and candidate are uploads of the same amd64 image built from clean
commit `390f7d4`, digest
`sha256:e283bb2cea46b5639b78bcfecb4df5d8548b6b0c6e45cf809ac1af0688007c6c`.
Both enable deduction history, stick mode, sound alibi collection, early public
coordination, and full telemetry. Only the candidate enables
`CREWBORG_SELF_PRESERVATION=1` and `CREWBORG_GROUP_TASKING=1`.

Each arm has 100 forced-crew episodes with an exact matched roster. The six crew
policies round-robin through crew slots 0--5 while the same two imposter policies
remain pinned at slots 6--7. This rotates the subject's crew seat/color while
keeping its role and opponents fixed.

## Precommitted analysis

Filter operational failures first. Report subject deaths and ejections, crew
wins, score, task completion, ballot precision/coverage, murder timing, and
seat-stratified outcomes. From full-tick replay, compare:

- murders where only the killer was near the subject;
- time isolated with one player, split by that player's posterior risk;
- escape and group-task activation, commitment completion, and stale fallback;
- distance and time to the selected safe group;
- tasks abandoned or delayed during safety behavior; and
- whether escape changes the next kill victim rather than preventing a kill.

Treat crew win rate as secondary at 100 games per arm. The mechanism passes only
if the candidate activates without inference/route failures and reduces unsafe
one-on-one exposure without a material task-completion regression.

## Requests and results

| Arm | Policy | Request |
| --- | --- | --- |
| control | `crewborg-self-preservation-control:v1` (`fe2a22e2-d090-4e5b-a801-24d99550c91b`) | `xreq_06cf809d-ab90-4281-98d4-286bb269636a` |
| candidate | `crewborg-self-preservation:v1` (`bc9ce95f-1b36-4f51-906b-90a7a5c2ee2d`) | `xreq_d8a1c559-d991-467c-b1de-997821eed280` |

Both requests completed 100/100 with the intended crew-slot rotation and no
request-level failures. Separate results, policy logs, and policy artifacts were
unavailable. The Crewrift 0.1.59 warehouse synthesized results from objective
replay. Candidate expansion was complete and hash-clean. One control replay
hash-failed at tick 10,186 and is excluded.

Fifteen trace-clean control subject appearances and eleven candidate appearances
had `-100` connect-timeout scores. The primary comparison excludes those subject
failures. A stricter sensitivity analysis excludes every game where any roster
member had a negative score.

### Subject-clean result

| Measure | Control | Candidate | Change |
| --- | ---: | ---: | ---: |
| Eligible games | 84 | 89 | -- |
| Crew wins | 40 (47.6%) | 40 (44.9%) | -2.7pp (`p=0.72`) |
| Murdered | 51 (60.7%) | 49 (55.1%) | -5.6pp (`p=0.45`) |
| Ejected | 1 | 3 | +2 |
| First victim | 20 (23.8%) | 22 (24.7%) | +0.9pp |
| Murdered after surviving to first meeting | 18/49 (36.7%) | 16/51 (31.4%) | -5.4pp (`p=0.57`) |
| Mean score | 55.29 | 52.71 | -2.58 (`p=0.74`) |
| Mean tasks | 7.86 | 7.89 | +0.03 (`p=0.65`) |
| Completed all 8 tasks | 76 (90.5%) | 81 (91.0%) | +0.5pp |
| Subject ballots: imposter / crew / skip | 17 / 1 / 51 | 11 / 0 / 63 | -- |

The total number of murders remained 2.96 versus 3.03 per eligible game. This
does not show that the treatment prevented team deaths rather than changing who
was exposed.

### Full-tick movement mechanism

The analysis used exact per-tick positions and the implementation's 44-pixel
nearby radius, not the warehouse's narrower 32-pixel interval default.

| Measure | Control | Candidate | Change |
| --- | ---: | ---: | ---: |
| Mean per-game time with exactly one nearby player | 28.37% | 26.87% | -1.50pp |
| Mean per-game time with a sole nearby imposter | 13.51% | 12.43% | -1.08pp |
| Aggregate time with 2+ nearby players | 16.51% | 19.04% | +2.53pp |
| Murders with only the killer within 44px | 40/51 (78.4%) | 35/49 (71.4%) | -7.0pp (`p=0.42`) |
| Mean nearby players at murder | 1.22 | 1.39 | +0.17 |
| Task starts with a current clustered pair nearby | 289/686 (42.1%) | 308/720 (42.8%) | +0.7pp |
| Abandoned task attempts | 25 | 17 | -8 |

This is the intended movement signature: less one-on-one exposure, more group
time, and fewer deaths where no witness was present. First-victim frequency did
not improve, while post-first-meeting murders moved down slightly. That pattern
is compatible with solver-informed escape helping only after evidence exists,
but missing private traces mean exact escape activations, cached posteriors,
commitment exits, and group-task selections cannot be proven from replay.

### Sensitivity and verdict

The stricter whole-roster-clean subsets contain only 61 control and 65 candidate
games. There, murders are 34/61 (55.7%) versus 37/65 (56.9%), and wins are 29/61
(47.5%) versus 25/65 (38.5%). Those deltas are also nonsignificant, but their
reversal means the primary death improvement is not robust to the operational
filter.

Do not submit or promote v1. The treatment is operationally live at scale and
has a promising movement signature without a task regression, but it has not
established a survival or win improvement. The next clean test should isolate
suspect escape by leaving `CREWBORG_GROUP_TASKING` off. Group-supported task
starts and first-victim frequency barely moved, so the bundled group-task bias
has not justified its share of the experiment. Use a lower-failure roster or a
larger batch, and add an observable escape activation counter before changing
the posterior threshold.
