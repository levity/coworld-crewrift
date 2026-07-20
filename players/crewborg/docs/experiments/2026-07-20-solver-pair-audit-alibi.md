# Auditable per-kill evidence in the pair solver

## Question

Can sound co-presence observations improve the persistent impostor-pair
posterior without turning partial evidence into an unsound permanent clear?

The current solver already enumerates every fixed-size impostor assignment and
rescored retained claims and votes at each meeting. Its alibi input is weaker:
the observation is reduced to an anonymous set and only eliminates a pair when
both members were continuously visible during the same hidden kill. Seeing one
member of a candidate pair has no effect, and repeated observations cannot
accumulate unless one happens to contain the whole pair.

## Treatment

Keep an append-only `KillAlibi` event for each usable hidden kill:

- observer and victim;
- when the death was learned;
- the victim's possible death window;
- every continuously co-present player;
- the alive players who could have performed the kill.

On every solve, replay those events over every possible impostor assignment.
For one event, compare the number of assignment members who could have killed
and were not co-present with the number who were alive and eligible before the
co-presence observation. A pair with one alibied member receives a conservative
negative log contribution. A pair with no possible perpetrator is excluded.
Independent kills accumulate; no event is overwritten.

The solve result will expose stable evidence IDs and the contribution made to
each surviving hypothesis. Raw claims, meeting records, and kill alibis remain
the source of truth. Deduplication and correlation discounts are scoring views,
not destructive compression.

This iteration changes only the private posterior. It does not publish player
clears. Low marginal probability may eventually support a spoken clear, but
that requires its own calibrated gate after this evidence channel is measured.

## Falsifiable gates

Implementation is viable only if:

1. Unit tests show that one alibied member lowers every pair containing that
   player, repeated distinct kills accumulate, and a pair with no possible
   killer is excluded.
2. Adding or retracting a later hard fact and resolving from the same raw
   ledger reproduces the corresponding posterior without stale compressed
   state.
3. Every scored contribution names its raw source, and the contributions sum
   to each hypothesis's log weight.
4. Conservative reconstruction over retained hosted histories finds enough
   sound singleton events to alter decisions, and changes are correctly
   directed against the fixed ground-truth impostor pair.

If retained histories show no changed decisions, mostly wrong-direction
movement, or only the already-supported whole-pair exclusions, do not spend a
hosted A/B on this treatment. If the gates pass, build and smoke-test the image,
upload it inertly with full telemetry, then compare it with the exact current
artifact on a fresh fixed roster.

## Implementation pivot

The append-only ledger and pair-contribution audit passed their focused gates,
but the planned soft likelihood did not.

Across 400 unique retained hosted games, a conservative reconstruction found
19 screen-visible member events in 12 games. Two actual killers remained
continuously rendered 61-68 pixels from the observer while killing a victim
behind the observer's line-of-sight boundary. Screen visibility therefore does
not establish co-presence. Requiring continuous distance at most 28 pixels
removed the actual-killer violations.

The narrower observation still did not imply crew. At 28 pixels, retained
history produced three member events in three games: zero members were the
killer, but two were the other actual impostor. This is consistent with
impostor specialization: one kills while the partner deliberately remains with
crew. The proposed singleton likelihood would confidently push the posterior in
the wrong direction.

Production therefore keeps `alibi_weight=0`. Every raw event and its
counterfactual likelihood remain visible in the audit, but inference uses only
the assumption-free relational consequence: a pair is impossible if no member
was both eligible to kill and outside the continuously co-present set. With the
current broad eligibility list this reduces to both members being co-present;
the generalized form can combine future reachability constraints without a
soft player clear.

## Validation

- Focused alibi and meeting-solver suite: 50 passed.
- Exact production image: 551 passed, 13 skipped.
- Gate 1 completed with valid results, replay, and eight player logs.
- Synthetic 20-claim, three-meeting solve: about 2 ms; complete 21-pair audit
  about 117 KB before routine telemetry was limited to the top five pairs.
- Built source image:
  `sha256:be9f2fc3379d7c49713b688e2042e15172a34f228a0f56ab98deceb82cf29515`.

## Hosted comparison

Both arms used the same fixed roster, forced crew slot 0, solver/stick/alibi
flags, and audit code. Only the physical observation gate differed:

- Legacy screen-visible control
  `crewborg-pair-audit-visible:v1`,
  `xreq_b979ee18-e55f-4a8c-93e2-85388c20627f`.
- Continuous 28-pixel candidate
  `crewborg-pair-audit-close:v1`,
  `xreq_b726b232-262e-4753-8a72-b861bd5be197`.

Both requests completed 100/100 with no operational failures. Candidate crew
wins were 47/100 versus 42/100 control, a +5 point difference that is not
significant (`Fisher p=0.569`). Candidate/control subject metrics were:

| Metric | 28px | Visible |
| --- | ---: | ---: |
| Mean score | 54.29 | 48.63 |
| Mean tasks | 7.82 | 7.76 |
| Killed by impostor | 52/100 | 52/100 |
| Ejected | 5/100 | 2/100 |
| Player votes on impostors | 28 | 27 |
| Player votes on crew | 0 | 1 |
| Skip votes | 61 | 76 |

The objective warehouse contains all 200 episodes and 10,479,375 events with
zero extraction failures or trace warnings. Reconstructing the runtime
continuity and distance gates found two close singleton events in the candidate
histories and no pair-sized close event. The visible control histories had
three visible singleton events and no pair-sized event. Since singleton weight
was zero, neither deployed arm excluded a pair or changed a posterior through
the alibi channel. Policy logs were unavailable on the hosted XP jobs, but the
full-tick reconstruction covers the exact behavioral gate.

## Verdict

Do not attribute the five-point outcome difference to the treatment and do not
promote either gate as a gameplay improvement. Keep the append-only evidence
ledger, full pair audit, and 28-pixel definition as the sound representation.

The next useful physical constraint is not another singleton clear weight. Add
map-aware reachability to each kill event: retain the victim's possible path and
each player's tracked reachable region, then exclude a pair only when neither
member could have intersected the victim during the death window. This can
combine a singleton co-presence fact with an independent impossible-travel fact
without pretending the non-killing impostor is crew.
