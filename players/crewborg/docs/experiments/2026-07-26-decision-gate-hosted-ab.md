# Decision-gate hosted A/B (Crewrift Prime)

**Pre-registered before firing. Do not edit the design section after results land.**

## Question

The deduction crew path votes at 100 % precision but ~15 % coverage, and across 100
Prime games it produced **zero ejections**. Two gate constants introduced with the
deduction path on 2026-07-20 — and never validated in isolation — appear to be what
blocks it. Does correcting them convert the posterior into ejections in play?

## What is measured, and what is not

All offline, on 476 living-seat decisions from 100 Prime games
(`tools/sweep_decision_gate.py`, `tools/simulate_tally.py`).

**The two constants are jointly binding.** On a 50/50 episode-level held-out split,
relaxing either alone changes nothing at all:

| setting | held-out coverage | right | wrong |
|---|---:|---:|---:|
| shipped | 16.0 % | 33 | 0 |
| margin floor → ε only | 16.0 % | 33 | 0 |
| support dropped only | 16.0 % | 33 | 0 |
| **both (`loose`)** | **21.8 %** | 45 | 0 |
| both + `base_probability` → 0.40 | 30.6 % | 63 | 0 |

So the pair is the smallest interpretable unit; splitting it into two A/Bs would
measure nothing twice.

**Why these two.** `min_independent_sources=2` requires attributed *social* sources;
498 of 739 decisions have zero, and only 44 (6.0 %) ever reach the bar, because the
claim parser drops ~81 % of utterances. `base_margin=0.10` compares rank 1 against
rank 3 — a flat-posterior test. Measured, margin == 0 is 55 % accurate while *any*
positive margin was 100 % accurate across 203 decisions, so the floor is lowered to an
epsilon rather than removed.

**Ejection estimate (first-order).** Re-running each meeting's tally with subject
ballots replaced, holding impostor ballots and deaths fixed:

| configuration | eject impostor | eject crew | no ejection |
|---|---:|---:|---:|
| actual (recorded) | 0 | 0 | 122 |
| shipped gate, simulated | 0 | 0 | 122 |
| **`loose`** | **13** | 0 | 109 |
| `loose+p40` | 23 | 0 | 99 |

The simulated shipped gate reproduces the recorded 0/0/122 exactly, which is the
validity check on the simulation. **This is first-order only** — real play is
interactive, so treat 13 as an estimate of the immediate tally effect, not a
prediction.

**Not established.** 0 wrong in 45 held-out ejects bounds the error rate at ~6.5 %
(95 %), not 0 %. Both halves of the split face the same `crewborg-aaln` impostors, so
nothing here speaks to the league field.

## Treatment — exactly one variable

Same image both arms, both with `CREWBORG_DEDUCTION_HISTORY=1`:

| Arm | `--secret-env` |
|---|---|
| Control | `CREWBORG_DEDUCTION_HISTORY=1` |
| Candidate | `CREWBORG_DEDUCTION_HISTORY=1` + `CREWBORG_DECISION_GATE=loose` |

`loose` sets `base_margin=1e-3` and `require_support=False`. It deliberately does
**not** touch `base_probability` (that is the separate `loose+p40` preset) or any
parity constant. An unrecognised value degrades to the shipped gate. The legacy
fitted-posterior path is untouched.

Control is re-uploaded from this image rather than reusing an older version, because
this image carries new code — reusing an older pvid would put code *and* flag in the
same comparison.

**Gate 1 (passed).** Verified inside the built image that the preset changes exactly
the two intended fields and nothing else. A 2-episode self-play run was
**inconclusive** for behaviour (18 vs 12 decisions, every eject `structural`, which is
the path this change does not touch) and is recorded as inconclusive, not as support.

## Hosted design

- Target `crewrift_prime`, `cow_0ba5e866-1c00-4e14-9ced-3c7d2296153b`.
- **Homogeneous roster**, identical to the Phase-0 A/B: 6× subject at slots 0–5 forced
  **crew**, 2× `crewborg-aaln` (`4e65356f-9a2c-4e6b-af27-bdb43515547b`) at slots 6–7
  forced **imposter**.
- 100 episodes per arm. Not seed-paired.

## Pre-registered analysis

**Primary (mechanism).** Landed targeted-vote coverage from replay `vote_cast`.
Predicted up, ~15 % → ~22 %. If it does not move, the flag did not take effect in play
and nothing else is interpretable.

**Co-primary guard.** Landed vote precision. **A drop below 90 % blocks promotion**
regardless of everything else.

**Secondary.** Impostor ejections per game — predicted up from ~0 toward ~0.13.
Crew ejections — predicted to stay at 0. Crew win rate with Fisher exact, treated as a
**guard, not a promotion criterion**: this is powered for coverage, not for a win-rate
delta.

**Guardrails.** Crew tasks/game and all-8 rate; impostor kills/game; operational
timeouts.

**Panel.** `crew_play_signals.py` over both arms, reading `vote_coverage`,
`vote_precision`, `posterior_auc` and `skip_with_pin_rate` first.

## Requests

Fired 2026-07-26. Both from image `crewborg:gate-ab2`; confirmed each queued 100
episodes with 0 failed immediately after creation (no double-fire).

| Arm | Policy version | `policy_version_id` | Experience request |
|---|---|---|---|
| Control | `crewborg-lw:v16` | `6a7444c3-1aa6-42de-8c56-786408d263d2` | `xreq_20c0564c-a5f2-49d0-a22e-424f7dd3575c` |
| Candidate (`CREWBORG_DECISION_GATE=loose`) | `crewborg-lw:v17` | `20cd2cc0-2aac-4270-afdf-5c603e28fe0a` | `xreq_94b472f6-4a0d-468b-84ea-1c108175e9c7` |

`crewborg-lw:v15` was uploaded earlier from a superseded image and is **not** used by
either arm.

## Result

Both arms drained 100/100, 0 failed, 0 operational timeouts, 0 vote timeouts.
Warehouse 200/200 ok, **0 trace_warning**.

**The pre-registered primary did NOT hit.** Landed targeted-vote coverage moved
14.2 % -> 16.6 % against a predicted ~22 %; Fisher `p = 0.308`. The offline held-out
estimate (21.8 %) overshot what the change produced in play.

**The co-primary guard passed.** Landed vote precision 100.0 % -> 98.9 % (91/92, one
wrong eject), far above the 90 % block. `p = 1.000`.

**The secondary is where the effect landed.**

| | control | candidate | test |
|---|---:|---:|---|
| meetings | 130 | 141 | — |
| **impostor ejections** | **2** | **14** | Fisher **`p = 0.0036`** |
| crew ejections | 0 | 0 | — |
| crew win | 47 % | 62 % | `p = 0.047`, +15.0 pp [+1.4, +28.6] |
| win by ejection / maxTicks | 1 % | 6 % | — |
| crew tasks/game (of 48) | 44.11 | 45.23 | — |
| impostor kills/game | 3.42 | 3.29 | — |

This is the first time the ejection channel has moved in any of these experiments;
Phase 0 was 3 vs 3, unchanged. Win rate was pre-registered as a **guard, not a
promotion criterion**, and at `p = 0.047` with n=100 it should not carry the decision —
but unlike Phase 0 it is now accompanied by the mechanism moving.

**The flag demonstrably took effect.** Evidence-class mix went from 99.3 % structural
(control: 270 structural, 2 accusation-backed) to 82.8 % (candidate: 227 structural,
36 accusation-backed, 11 unsupported) — 47 non-structural ejects versus 2.

### Methodological result worth keeping

The **tally simulation predicted 13 impostor ejections per 100 games; the actual was
14.** The coverage estimate, by contrast, overshot by roughly 3x. On this one
comparison the tally simulation was the better-calibrated instrument and it is also
the cheaper one. Worth re-testing next time rather than assuming.

### Panel (28 signals, both arms)

Notable movements, none of which the gate touches directly:

- `parity_vote_shift` **9.5 -> 40.6 pp**. The candidate now shifts its targeted-vote
  rate sharply as the board tightens. Read as a side effect: dropping the support
  requirement lets the existing parity logic express itself, rather than a designed win.
- `died_while_isolated` 36.3 % -> 28.3 %, `isolation_exposure` 115.4 -> 96.2. The gate
  touches no movement code, so this is almost certainly downstream of removing
  impostors earlier.
- `posterior_auc` 0.801 -> 0.780. The inference machinery is unchanged; treat as
  game-trajectory drift, not a belief-quality regression.

### Verdict

The change did what it was designed to do, through a smaller coverage shift than
predicted and a much larger conversion into ejections. Guardrails clean. **Promote the
`loose` preset within the deduction path.**

Not established: everything here is forced-crew on one pinned roster against
`crewborg-aaln`. Impostor play is untested, and the league runs a different coworld
(`cow_191cc191`) than these tests (`cow_0ba5e866`).
