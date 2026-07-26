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

*(filled in at fire time)*

## Result

*(pending)*
