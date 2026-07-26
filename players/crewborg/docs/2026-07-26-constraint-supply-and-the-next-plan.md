# The solver is starved, not broken — and a revised plan (2026-07-26)

Supersedes the ranking in
[`2026-07-25-solver-in-the-component-loop.md`](./2026-07-25-solver-in-the-component-loop.md) §4.
Everything here is measured on data already on disk; no hosted games were bought.

## 0. The one-line finding

The joint solver contributes **0 of 244 ejects** not because its enumeration is wrong,
but because **every channel that could hand it a structural constraint is discarded
before it gets there.** It runs on pins alone — and pins decide the vote by themselves,
so the enumerator is decorative. Fix the constraint *supply* and the machinery we
already paid for starts earning.

## 1. What the discard log actually says

`deduction_audit.py` over the Phase-0 candidate arm (100 games, 739 decisions). Ignored
evidence, by reason:

| n | channel: reason | recoverable? |
|---:|---|---|
| 2526 | `vote: skip vote has no target likelihood` | **yes** — needs a likelihood, not a rule |
| 1858 | `utterance: no recognized deduction claim` | partly — parser coverage |
| 1188 | `alibi: no player was continuously co-present` | **yes** — relax to bounded-gap reachability |
| 258 | `alibi: kill was directly witnessed` | no (correctly redundant) |
| 146 | `vote: own derived vote is not new evidence` | no (correct) |
| 141 | `alibi: no bounded off-screen kill window` | no |
| 98 | `direct: body transition has 2 possible nearby actors` | **yes — and this is the new one** |
| 39 | `direct: body transition has 0 possible nearby actors` | no (killer never visible) |

## 2. The missed direction: partial identification is thrown away

`inference.py:894`:

```python
actors = {...}                      # players within kill range of the new body
if len(actors) != 1:
    audit.append(EvidenceAudit(..., status="ignored",
        reason=f"body transition has {len(actors)} possible nearby actors"))
    continue                        # <-- the whole observation is dropped
actor = next(iter(actors))
pins.add(actor)
```

When exactly one player is in kill range of a fresh body, we get a pin. When **two** are,
we currently learn *nothing* — and the audit record does not even name the two candidates
(its `targets` field holds the victim). The information is destroyed at source.

But "a body appeared and only A and B were in kill range" is a sound, proof-strength
statement: **at least one of {A, B} is an impostor.** That is precisely the input a joint
enumerator exists to consume.

**Size of the opportunity** (distinct observations, not repeated decisions):

| | per 100 games | per game |
|---|---:|---:|
| witness pins (1 nearby actor) | 154 | 1.54 |
| **discarded ambiguous (≥2 actors)** | **54** | **0.54** |

So **26 % of all body-transition observations are discarded.** 39 of 100 games contain at
least one; 14 contain two or more.

**Strength of one constraint.** From a seat's view of an 8-player, 2-impostor game there
are C(7,2) = 21 hypotheses. "At least one of {A,B}" eliminates those where neither is an
impostor — C(5,2) = 10 — leaving 11. **One observation prunes ~52 % of the space**, and
two overlapping ones usually pin it outright.

**Cost.** The `at_least_one` stance already exists (`inference.py:29`), but only as a
*soft claim* likelihood scored through `_actor_claim_probability` — i.e. weighted by
whether the *speaker* is lying. An observed ambiguous kill is not a claim; it is an
observation and deserves a **hard** constraint that removes hypotheses outright, like
`pins` do. That is a small, well-scoped change to the enumerator plus emitting the
candidate set instead of dropping it.

## 3. Belief quality, measured for the first time

The panel previously scored only *actions*. It now scores *beliefs*, from the posterior
the policy actually held (living seats only):

| | hosted Phase-0 candidate | self-play |
|---|---:|---:|
| `posterior_auc` | 0.800 | 0.857 |
| `posterior_brier` | 0.200 | 0.142 |
| base rate | 28.6 % | 28.6 % |

AUC 0.80 with 100 %-precision votes means the policy is **well-ranked but severely
under-committed**: it converts only the top of a decent ordering into action. That is
consistent with coverage of 14.5 % and with `oracle_ghost_coverage_gain = +51 pp` — a
near-omniscient seat targets 51 points more often. The headroom is in *acting*, not in
*ranking*.

## 4. Revised ranking

The old §4 order was built before we knew the solver was starved. Revised:

| # | change | why it moved | cost |
|---|---|---|---|
| **1** | **Hard `at_least_one` from ambiguous body transitions** | *(new)* Acts on the `direct` channel, which already drives 100 % of ejects at 100 % precision. Recovers 26 % of that channel's observations. Machinery half-exists. | small |
| **2** | Skip-vote likelihood | Still the largest single discard (2526). Unchanged. | small |
| **3** | Reachability alibi (replace continuous co-presence) | Still 1188 discards; also unblocks `fair` mode. Unchanged. | medium |
| 4 | Three-mode history builder (`fair` oracle) | Still the routing instrument. Partly stood in for by the ghost bracket now shipped. | large |
| 5 | Vent position-discontinuity pin | Was #1. **Demoted**: still 0 fires, and #1 above is cheaper and acts on the same channel. | medium |
| 6 | Wire `TaskCounterObserved` | Unchanged. | small |
| 7 | Refit the 22 constants | **Demoted further.** Phase-0 showed the joint solve drives 0 ejects in the clean arm, so the constants govern nothing until 1–3 land. | small |

The decision-layer item from §4 stands and is now evidenced: 21 of control's 30 crew
ejections were *1 crew vote + 2 impostor votes*.

## 5. Plan

**Phase A — instrument (done).** `crew_play_signals.py`: 22 own-seat signals, each tagged
`dec`/`obs`; `normalize_selfplay.py` so free local games feed the same panel. Validated
end-to-end on hosted and self-play.

**Phase B — constraint supply (free, offline).** Items 1–3, one at a time, each gated on
the panel moving the *specific* signal it targets before anything else is considered:

| change | pre-registered signal that must move | guard |
|---|---|---|
| hard `at_least_one` | structural constraints > 0/game; `posterior_auc` up | `vote_precision` stays 100 % |
| skip-vote likelihood | `posterior_auc` up on held-out meetings | precision holds |
| reachability alibi | active alibi constraints > 0/game | precision holds |

**Phase C — hosted, once.** Only after B moves offline signals. And per §6 of the
companion note: **buy meetings, not games** — the `scn_meetings` shape yields several
times the decisions per hosted tick.

## 6. Two operational lessons worth keeping

- **Never run local self-play beside a warehouse build on this box.** At load ~19 the
  agents miss connection deadlines; the log shows `player disconnected` /
  `disconnect timeout` / `draw: time limit reached`, and the replay then fails the
  expander hash check. The episodes look fine on disk and are worthless. Diagnosed the
  hard way here — the first three smoke-test games were all invalid.
- **Impostor seats are not always 6–7.** Hosted crew-screen A/Bs pin them there; local
  self-play shuffles (observed 2–3). A `slot >= 6` shortcut silently mis-scores every
  vote. Read roles per episode.
