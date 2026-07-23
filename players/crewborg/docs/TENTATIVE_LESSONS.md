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

### Sustained proximity selected allies, not killers
Evidence: In the 200/arm aggressive self-preservation A/B, full candidate
telemetry recorded 717 escape sessions: 629 threats were crew and only 88 were
impostors. Only 23/88 eventual killers ever triggered. Reaching one witness
then made that witness the next sole companion and restarted flight. Murders
rose 36.2% -> 57.5%, one-on-one imposter exposure rose, and task attempts
churned. Do not treat generic proximity stability as danger evidence.

### Separate local repulsion from named-threat escape
Evidence: Before 71/88 candidate murders the killer was the sole player within
64 pixels, but crewborg was actually moving under escape in only 8. It kept
tasking in 46 and sat at a cached near-zero-length escape goal in 15. The tested
destination/latch controller therefore did not test the simpler rule “move away
while exactly one player is nearby.” Evaluate that separately as role-agnostic
risk control, with no destination requirement or stale target. The local
follow-up recomputes a reachable away goal from current geometry each tick and
treats 12-tick pursuit as telemetry, not evidence.

### Verify self identity in hosted geometry consumers
Evidence: `SELF_SPRITE_MATCH_SQ=4**2` assumes the decoded self record equals
`self_world`, but 20 sampled hosted games and murder-time traces show a stable
record offset of `(-2,-6)` (distance 6.32). Memoryless repulsion therefore
targeted the camera-locked self sprite in 2,123/5,549 stage starts/upgrades and
182/187 operational games. Unit tests with a pre-filled correct `self_color`
and Gate 1 did not exercise this integration failure.

### A nearby witness is not usually the double-kill failure here
Evidence: Double kills occurred in 29/121 candidate games and included crewborg
in 10/88 murders, but none killed another player within 64 pixels of crewborg on
the same tick. In the sampled event the other kill was against a separate pair
across the map. Do not infer local witness removal from same-tick global kills.

### Crewrift score sign is not an operational-health signal
Evidence: A clean no-timeout candidate game completed two tasks but scored -17
from gameplay penalties. Filtering `score >= 0` discarded valid bad games and
changed denominators. Use per-slot `connect_timeout` and `disconnect_timeout`
from `results.json`; separately report a whole-roster-timeout sensitivity set.

### Optional artifact absence can be a downloader regression
Evidence: XP player telemetry was declared unavailable because the downloader
used obsolete `/jobs/...` routes and swallowed their 403/404 responses. The
current owned `/v2/episode-requests/{ereq}/{policy_version}/...` route returned
the expected ZIP, including all self-preservation edge events.

### Post-task grouping does not prevent active-task isolation
Evidence: In the v2 300-game crew screen, crewborg was murdered in 172 games;
112 deaths occurred with only the eventual killer nearby, and 70 were the
first crew kill. A stick-after-tasks policy cannot address isolation while
tasks remain, while a suspect-only escape cannot address unknown first-kill
risk. Keep reactive high-confidence escape and bounded group-aware tasking as
separately gated mechanisms, and use seat-rotated evaluation before attributing
the fixed-slot death gap to either one.

### A joint posterior still needs semantically valid decision support
Evidence: In the append-only hosted A/B, three of four fresh public-solver
errors treated two ballots as independent support even though no utterance
accused the chosen target. Requiring one active accusation retained all 14
correct candidate-history selections while removing those three errors.

### Synthetic social evidence must share latent beliefs
Evidence: Independent synthetic chat and ballot draws predicted 94.9% vote
precision at 49.4% coverage; fresh hosted public history produced 77.8% at
19.4%. Hosted errors were persistent or shared false piles, a dependency the
generator could not express. After adding persistent actor beliefs, matching
chat/ballots, and crowd adoption, the 1,000-game screen fell to a more
discriminating 84.6% precision at 64.2% final-history coverage.

### An assignment clear is not necessarily a player clear
Evidence: Continuous co-presence with A and B during a hidden kill excludes
the joint assignment `{A,B}` because one living impostor had to be outside the
group. It does not clear A or B individually: either can be the non-killing
partner of someone outside. With two impostors, this constraint first removes
a pair when crewborg stays with at least two other players.

### Synthetic precision gains must retain correct votes and survive hosted replay
Evidence: Stronger repeat decay improved the 3,000-meeting synthetic audit from
82.2% to 83.2% precision, but dropped 179 correct selections while removing
only 55 errors. On the held-out hosted candidate history it regressed 14/15 to
8/9. Do not promote an abstention-driven synthetic gain without both checks.

### Reject incomplete replay traces before meeting evaluation
Evidence: One candidate expansion stopped at tick 5060 on a hash failure. The
new evaluator initially counted its two partial meetings, including a correct
selection, while the legacy analyzer excluded it. Explicit trace-warning
filtering restored the same 93-meeting denominator.

### Store observations once and derive conclusions on replay
Evidence: The first append-only collector stored both world frames and
`DirectActionObserved` conclusions. That duplicated information and froze the
current detector. Recording visible vent occupancy and body/player frames
instead lets every witnessed-action pin be rederived after detector changes.

### Measure Python object shape before replacing readable identities
Evidence: A dense 20,000-frame history used about 140 MB RSS with nested
Pydantic observation values. Frozen slotted values reduced it to 79 MB and cut
construction from 0.81s to 0.35s while preserving readable color names and JSON
round trips. Integer enums would have targeted the smaller identity field.

### Treat hand-built posterior values as calibration hypotheses
Evidence: Six non-overlapping warehouses produced monotonic eject calibration
in aggregate (85.3%, 88.0%, 90.0% across increasing decisive buckets), but one
batch was non-monotonic and the sample sizes were small. Threshold sweeps are
useful screens, not proof that a stated 0.90 is literally a 90% probability.

### Geometric vent occupancy is not vent use
Evidence: In an activated local meeting smoke, Orange hard-pinned crewmate Cyan
when Cyan merely walked onto an empty visible vent. Requiring an emerging actor
to have been absent from the entire preceding visible-player frame retained the
actual Red vent pin and removed the Cyan false positive.

### Public replay adapters must represent missing channels as absent evidence
Evidence: Three older warehouses lacked `chat` or `died` partitions. Treating
those optional partitions as mandatory crashed DuckDB; treating them as empty
produced explicit zero-opportunity results without inventing facts.

### Eligibility needs redundant death signals
Evidence: The warehouse's `died` partition omitted some known kill victims, so
the first narrative sample let a killed subject act in a later meeting. Unioning
`kill.victim_slot` into the death census removed 98 impossible subject meetings
from one 279-meeting reconstruction.

### Proximity language is not action evidence
Evidence: “I saw Pink near the vent earlier but also doing tasks” became a
witnessed-vent accusation and contributed to a wrong Pink eject. Rejecting the
near-vent interpretation while retaining the raw utterance removed one wrong
decision on 181 eligible meetings, improving vote precision 73.3% -> 78.6%.

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

### Measure a movement intervention at its implemented geometry
Evidence: The self-preservation controller uses a 44-pixel nearby radius, while the warehouse's
standard proximity intervals use 32 pixels. Exact per-tick reconstruction found the candidate spent
less time one-on-one and died with only the killer nearby 35/49 times versus 40/51 control. Reusing
the narrower interval would test a different condition. The outcome improvement was nonsignificant
and reversed under a strict whole-roster-clean filter, so mechanism movement is evidence of
activation direction, not proof of survival benefit.
