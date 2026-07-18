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
