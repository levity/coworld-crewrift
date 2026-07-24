# Post-task escort hosted A/B (Crewrift Prime)

Target: crewrift_prime v0.4.69 (cow_0ba5e866). 100 forced-crewmate episodes/arm.
Roster (pinned, identical across arms): crewborg-lw @slot0 forced CREW; slots1-4
crewborg-aaln (4e65356f); slots5-7 notsus (48df5a11); impostors @slots 4 (aaln) & 7
(notsus). Replicates the prime-gt field. Only slot-0 subject version differs.

- Control  (escort OFF): crewborg-lw:v4 ded9bc9b  xreq_32db3512-c7a1-48ac-b725-1f897394c5e5
- Candidate (escort ON): crewborg-lw:v5 f9fddccf  xreq_bd9bd91b-0dbe-4692-9b7c-ea101381aee3

Both images = crewborg:escort-v2 (freeze fix baked). Candidate adds
CREWBORG_POST_TASK_ESCORT=1 via --secret-env; control carries the same env minus that
flag (isolates escort exactly). Freeze fix present in BOTH.

## Precommitted analysis
Primary: subject murder rate, esp. post-own-task-completion murders (escort targets the
finished-crew isolation window). Guardrails (must not regress): full-task completion,
mean tasks, wins, first-victim, score. Mechanism check from 64px replay geometry:
finished-crew time-with-2+-nearby should rise / sole-nearby-impostor time should fall.
Escort is a NO-OP until a crewmate finishes all 8 tasks, so expect a small overall
effect; look specifically at the post-task-done slice. Recompute on clean episodes
(drop connect/disconnect ops-fails). n=100/arm is a direction+geometry pass, likely
underpowered for the murder delta alone.
## Result — post-task escort hosted A/B (Crewrift Prime, 100/arm, 0 ops-fails)

**Verdict: escort is NEUTRAL on survival at n=100 — do NOT promote it alone.** The
freeze fix (in BOTH arms) is separately validated: pathological stall 0.01 in both,
0/200 games >=30% stall — the edge-park freeze is gone on Prime too.

Primary (subject-clean, n=100/arm; arms are NOT seed-paired, so deltas carry full
sampling noise):
- subject murdered 50% -> 51% (+1pp, p=1.0) — no change
- crew win 20% -> 23% (+3pp, p=0.73); all-8 tasks 52% -> 50% (-2pp) — flat, no task cost
- first victim 9% -> 16-17% (+8pp, p=0.14) — adverse-looking but escort is POST-task and
  cannot affect who dies FIRST (a first-victim died early, pre-task); attributed to noise.

Mechanism signal (the one real move):
- Of murdered subjects, **isolated kills 84.0% -> 72.5% (-11.5pp)** — escort made kills
  less isolated (more witnessed), its intended effect. Geometry agrees weakly: sole-
  impostor 9.24% -> 8.16%, sole-crew 17.5% -> 19.7%. But 2+-nearby did NOT rise
  (23.4% -> 22.1%), so cohesion didn't strengthen into real clusters.

Why it can't move the outcome HERE: **43% of subjects are killed BEFORE finishing tasks**
(42-44/100), isolated 78% of the time — and escort only acts AFTER all 8 tasks are done.
Only ~7-8 murdered subjects/arm were in escort's window. The dominant crew failure on
this Prime field (crewborg-aaln + notsus, 2 imps) is dying MID-TASK, upstream of escort.

Next: attack the mid-task isolation death — keep crew together WHILE tasking (the
validated group-cohesion direction), not just after. Escort is defensible (no harm, less
isolated kills) but targets too small a slice to justify promotion on its own.
