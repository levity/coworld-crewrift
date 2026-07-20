# crewborg tentative lessons — session buffer

This is THIS SESSION's lesson buffer. Write candidate lessons here **as you go** — eagerly and
noisily; most will be noise and that's fine. At the next session start, the rotation hook archives
this file automatically to [`lessons_archive/`](lessons_archive/) and creates a fresh one — nothing
you write here is lost, and nothing carries over by hand.

**Lifecycle.** Per-session buffer → automatic archive (SessionStart hook,
`../tools/rotate_lessons.sh`) → periodic human+agent review (the `/lessons-review` skill) that
clusters RECURRING lessons across archived sessions and graduates the keepers into
[`best_practices.md`](best_practices.md). **Recurrence across independent session buffers — not
in-session hit counts — is the graduation signal.** A Stop hook (`../tools/lessons_stop_nudge.sh`)
nudges once per session if substantive work ends with this buffer untouched.

**Entry format.** `### <lesson, one line>` then `Evidence:` (what you observed, concrete) and an
optional `Status:` note. Terse. One lesson per `###`.

---

### Preserve relational evidence before reducing it to per-player counters
Evidence: The fitted social counters persisted across meetings but discarded speaker-target
edges, meeting identity, disjunctions, and source provenance, making joint constraints
unrecoverable. A parallel structured ledger restored those capabilities without disturbing
the fitted model.

### Deadline deferral can suppress chat in homogeneous self-play
Evidence: In the solver-enabled `scn_vote_basic` smoke, all crewborg seats waited until the
same 48-tick backstop, so their accusations were simultaneous and unavailable to that
meeting's own solve. Mixed-field evaluation is required to measure the intended benefit from
other policies' earlier utterances.

### Vendored pickle assets need narrow module-path compatibility
Evidence: The committed navbake remained structurally valid but referenced two pre-package-move
`crewrift.crewborg.*` modules. An exact unpickler alias restored it; broad import aliases or
rebaking unrelated data were unnecessary.

### Closed-vocabulary NLP still needs grammatical roles
Evidence: Treating every color near an accusation cue as a target made `Yellow saw cyan vent`
accuse both players. Predicate-aware source/target extraction halved false targets in 125 hosted
replays and reduced social-only false solver picks from 10 to 5 on solver-arm history.

### Relayed evidence has two trust surfaces
Evidence: A relay can be false because the attributed source lied or because the current speaker
fabricated the attribution. Conditioning likelihood on both actors prevents a suspected impostor
from laundering a claim through a named trusted player; original-source dedup prevents repeated
relays from amplifying it.

### Public-history replay is a useful solver gate, not an outcome estimate
Evidence: Reconstructing 243 meetings through the real parser/solver exposed pick precision and
coverage before another hosted run, but the warehouse cannot reproduce private witness pins,
task clears, or fitted suspicion priors. Use it to reject parser/inference regressions, then use a
matched hosted A/B for crew-win judgment.

### Correlation controls need a coverage constraint and per-history audit
Evidence: Aggressive same-target decay, claim/vote deduplication, and vote-bloc decay looked
mechanistically plausible but either reduced precision or achieved it by abstaining. A mild
same-meeting claim decay plus repeated-vote decay and a sole-source counterfactual improved pooled
precision 83.3% -> 87.3% while retaining 92% of correct picks; checking each retained history
prevented a pooled gain from hiding a local regression.

### A retrospective feature must reproduce as an active held-out discriminator
Evidence: Missing-ballot accusation sources were only 47.2% correct in retained histories, and a
0.30 discount improved replay precision from 89.5% to 91.7%. On 200 fresh hash-complete replays,
however, decay 0.30 versus 1.0 changed zero decisive public solver picks, while the uploaded arm
lost 32/100 versus 47/100. The feature was removed despite its retrospective frontier gain.

### Timed branches must be reachable under every supported clock fallback
Evidence: Early guidance used `min(200, timer // 6)`. Hosted perception retained the 240-tick safe
fallback, shrinking the window to 40 ticks while auto-submit started at 48. A 100-game candidate
arm therefore emitted zero guidance lines despite passing unit and replay gates. Test timing
features with missing advertised configuration, not only the standard 1,200-tick value.

### Counterfactual strength can reveal correlated crowd evidence
Evidence: Among single-source decisive picks, removing the source left every correct selection-arm
target at P=0.321-0.371 but every false target at P=0.419-0.509. A P<=0.39 cap retained 6/6 correct
and rejected 8/8 false picks on four later held-out arms. A conclusion that stays too strong without
its named source is being sustained by the ballot pile, not independently corroborated.

### Offline opportunity does not prove a timed runtime branch executes
Evidence: Both 100-game guidance candidates emitted zero guidance lines even though public replay
found correct strict-gate opportunities at the intended cutoff. Require a runtime attempt/fired
trace in a local scenario before spending another hosted batch on a timed interaction feature.

### Individual vote precision can hide a team coordination failure
Evidence: The crowd-cap candidate cast 25 impostor votes and zero crew votes, yet its team ejected
14 crew versus 8 in control. Transcript audit showed crewborg supported none of those 14 ejections:
other crew commonly voted near tick 300, long before its accurate tick-1,152 solver message.

### Decompose crew ejections by subject agency
Evidence: In the fresh crowd-cap A/B, five of 22 crew ejections targeted the subject, while none of
the candidate's 14 crew ejections had its ballot support. Subject wrong votes, subject
self-ejections, and total team crew ejections measure distinct failure mechanisms.

### Replay-calibrated public interaction must exclude private features
Evidence: A hosted early accusation is auditable from public replay only if its live solve omits
private suspicion priors, witnessed-impostor pins, and watched-task clears. The public-only helper
kept the exact implemented tick-240 gate at 29/29 on selection and 29/29 on held-out histories.

### Similar-looking offline and runtime features need an identity-level equivalence check
Evidence: Offline `tasks_completed_watched` used the replay's true completer slot and had zero
impostor examples, while runtime substituted the only visible long task-site dwell at a global
task decrement. Exact hosted reconstruction found 392/550 attributions wrong and 258 credited to
impostors. Visibility clipping did not make the target identity observable.

### Optional artifact absence is not episode incompleteness
Evidence: Current XP episodes had complete authoritative metadata and replays while separate
results and policy-log routes were unavailable. Requiring optional artifacts caused three
identical retries and silently excluded all episodes from the warehouse wrapper. Completeness must
track the requested replay; optional route status should be recorded separately.

### A reward threshold identifies the winning team, not each teammate
Evidence: Crewrift pays `+100` to every member of the winning role, but per-player penalties can
leave a winning teammate below 100. XP score fallback must infer one winning role from an
unambiguous WinReward-sized score and apply that result team-wide, not use `score >= 100` as each
player's win flag. If no role has that reward, preserve action scores but mark no winners.

### Hard facts should update both assignments and source reliability
Evidence: Hidden-kill victims now leave every joint impostor hypothesis, which also makes their
episode-persistent claims come from known crew under the role-conditioned likelihood. Five hosted
tick-241 conclusions all targeted real impostors; four reconstructed lines used deaths and evidence
from multiple meetings, including two with no current-meeting ballot support.

### A sound relational constraint can be too sparse to optimize
Evidence: Co-presence during one kill soundly excludes an impostor pair, not either player alone.
After strict continuity, witnessed-kill, and victim-absence guards, replay reconstruction found only
one usable two-player alibi group in 100 candidate games. Keep the sound hook, but do not tune it
from outcome noise.

### Screen visibility is not physical co-presence
Evidence: Retained replay reconstruction found actual killers continuously rendered 61-68 pixels
from crewborg while killing a victim behind the observer's sight boundary. A physical inference
must use world distance and continuity, not merely membership in the rendered viewport.

### "Not this killer" is not a probabilistic player clear
Evidence: At a sound 28-pixel continuous-distance bound, two of three retained alibi members were
the non-killing actual impostor. Impostor partners can divide labor, with one killing while the
other stays conspicuously with crew. Preserve the per-kill relational fact, but give singleton
observations zero crew likelihood unless a calibrated latent-killer model justifies otherwise.

### A complete audit can be useful even when its new channel is inactive
Evidence: The fresh 200-game alibi comparison produced no pair-sized event in either arm, so its
five-point win difference was not a treatment effect. The append-only kill ledger, stable evidence
IDs, complete pair table, and additive contribution trace remain useful because future facts can be
rescored without reconstructing or destructively compressing old conclusions.

### Size replay expansion to the VM before launching it
Evidence: This VM has 2 vCPUs and 7.2 GiB RAM. Two simultaneous 16-worker warehouse builds exhausted
the machine and forced a reboot. Inspect CPU and available memory first; on this VM run one warehouse
at a time. Measurement on 2026-07-20 found three workers useful for download-heavy streaming but
sustained full-tick expansion saturated both CPUs and pushed load above 3; use two for expansion.

### A counterfactual should remove exactly the evidence channel it tests
Evidence: The sole-source robustness solve removed an actor but accidentally omitted per-kill
alibis, making independent physical constraints disappear with social evidence. Passing one
immutable evidence bundle through every solve preserves unrelated facts; the correlated-crowd cap
then needs its own explicitly social-only counterfactual rather than overloading source removal.

### Compare old and new policy logic on each hosted history before attributing an A/B
Evidence: Constraint-aware v3 won 48/100 versus v2 32/100, but the new public solver found 22/22
decisive picks in candidate history and only 10/12 in control history. Replaying v2 on those same
histories showed 12/12 and 10/11: v3 genuinely added 10/10 correct candidate opportunities, while
the candidate batch also contained much cleaner evidence. The fixed-history counterfactual
separates mechanism activation from random between-arm opportunity.

### Artifact encoding is a property of bytes, not a filename
Evidence: The hosted replay route returned raw `CREWRIFT` bytes under `replay.json.z`, and the
warehouse wrapper declared zlib from the suffix, failing all 100 episodes. This condition was
already recorded in an earlier experiment. Inspect magic bytes, validate decoded replay magic,
smoke-test the expander, and make failed/hash-incomplete manifests fail the wrapper before querying.

### Streaming orchestration must preserve its selected environment and dependency API
Evidence: `stream_eval.py` discarded its working Python environment by hardcoding a nested
`uv run`, then called `build_request` without the replay-encoding argument added by the wrapper.
The failures occurred before data extraction and looked like warehouse unreliability. Child
processes now reuse `sys.executable`, and each incremental build preflights and passes encodings.

### Budget correlated aggression changes separately
Evidence: Lowering the public threshold, committing earlier, adding a public deadline fallback, and
tightening source-free deductions were individually defensible but bundled into one A/B. The arm
lost 35/100 versus 45/100 while only early commitment clearly activated: five early ballots, all
correct. The run could not estimate the inactive fallback or attribute the outcome among components.

### Stability filters changing conclusions but does not prove a stable one
Evidence: In the fresh commitment arm, all five tick-240 targets that remained selected at tick 360
were correct, while two conclusions that first appeared by tick 360 were wrong and did not commit.
The delay was useful here, but a correlated false consensus can also remain stable; retain source
and crowd-robustness requirements and add a board-state risk budget before widening coverage.

### Commit behavioral source before building a hosted artifact
Evidence: `crewborg-solver-commit:v1` and its two predecessors were uploaded from dirty worktrees,
so their version rows initially pointed only to a parent commit plus an image digest. A later commit
can preserve identical behavior, but committing first makes the build input reviewable and directly
reconstructible before hosted evidence depends on it.
