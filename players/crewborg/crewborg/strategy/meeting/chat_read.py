"""Read meeting chat for *who is being accused* (design §10.5).

The imposter's reactive bandwagon (§10.4) wants to know which crewmates other players
are sussing in chat, to pile on before it hardens into a vote. Free-form chat makes
this hard, but the target vocabulary is a **closed set of colors**, which we exploit:

1. **Keyword pre-gate** (cheap) — a message is only worth parsing if it names a color
   *and* carries a sus cue. Most chatter is filtered out here.
2. **Dependency-parse negation scope** (spaCy, `chat_nlp`) — the real value. A crude
   "is a negation word present?" guard mishandles ``"red isn't sus"`` vs
   ``"red is sus not blue"``; a dependency parse tracks which clause the negation
   governs, handles contrastive negation, the victim-vs-suspect flip
   (``"when red died"`` ⇒ red is the victim), and defense phrasings.

If the model is disabled or still loading (`chat_nlp.get_model()` is ``None``), there
is **no** chat signal — we deliberately do *not* fall back to crude keyword matching
(its false positives are exactly what this layer exists to avoid); the bandwagon then
rests on the reliable vote tally alone.
"""

from __future__ import annotations

from typing import Any

from crewborg.strategy.meeting import chat_nlp
from crewborg.types import Belief

# Cues that an utterance is an accusation. Closed, tunable; inflections included so we
# can match on the lowercase token without depending on the lemmatizer.
SUS_WORDS = frozenset({
    "sus", "suspicious", "vent", "vented", "venting", "vents", "kill", "killed", "kills",
    "body", "dead", "died", "vote", "votes", "voting", "imp", "imposter", "impostor",
    "fake", "faking", "faked", "follow", "following", "followed", "lying", "lie", "lied",
    "did", "saw", "report",
})
# Negation cues — checked against the dependency tree, not bare presence.
NEG_WORDS = frozenset({"not", "n't", "no", "never", "isnt", "dont", "doesnt", "cant", "aint"})
# Defense/clearing cues that govern a color's clause flip it to "not accused".
DEFENSE_WORDS = frozenset({"innocent", "clear", "cleared", "vouch", "trust", "safe", "good", "sure", "with"})
# A victim cue adjacent to a color marks it as the *victim*, not the suspect.
#
# "killed" deliberately does NOT belong here — kill reports name TWO colors and this
# is a ±2-token proximity test, so it cannot tell them apart. It used to hold
# "killed", which broke kill reports in both directions at once: "saw red kill green"
# returned {red, green} (the victim accused, because the bare infinitive "kill" was
# absent from this set) while "red killed green" returned {} (BOTH colors sit within
# two tokens of "killed", so both were suppressed and the strongest evidence in the
# game produced no signal at all). Kill roles are now resolved by `_kill_roles`.
VICTIM_WORDS = frozenset({"died", "dead", "body"})
KILL_LEMMAS = frozenset({"kill", "murder", "stab"})
# Surface forms as well as lemmas, because the lemma cannot be trusted here: in
# "red kills green" en_core_web_sm tags `kills` PROPN with lemma "kills", so a
# lemma-only test silently misses the present tense. Same root cause as the parse
# failures — this vocabulary is out of the model's domain.
KILL_FORMS = frozenset({
    "kill", "kills", "killed", "killing",
    "murder", "murders", "murdered", "murdering",
    "stab", "stabs", "stabbed", "stabbing",
})


def chat_accusers(belief: Belief, *, cache: dict[str, set[str]] | None = None) -> dict[str, int]:
    """Per non-teammate color, the count of *distinct other speakers* who accused them
    in chat. Empty when the NLP model isn't available. ``cache`` (caller-owned, reset
    each meeting) memoizes per-message parses so we don't re-parse every tick."""

    nlp = chat_nlp.get_model()
    if nlp is None:
        return {}

    colors = set(belief.roster)
    self_color = belief.voting.self_marker_color
    cache = cache if cache is not None else {}

    by_color: dict[str, set[str | None]] = {}
    for event in belief.chat_log:
        if event.speaker_color is not None and event.speaker_color == self_color:
            continue  # our own chat isn't a signal to bandwagon on
        for color in _accused_for(event.text, colors, nlp, cache):
            by_color.setdefault(color, set()).add(event.speaker_color)

    return {
        color: len(speakers)
        for color, speakers in by_color.items()
        if color not in belief.teammate_colors and color != self_color
    }


def _accused_for(text: str, colors: set[str], nlp: Any, cache: dict[str, set[str]]) -> set[str]:
    if text in cache:
        return cache[text]
    accused = _extract(nlp, text, colors) if _gate(text, colors) else set()
    cache[text] = accused
    return accused


def _gate(text: str, colors: set[str]) -> bool:
    """Cheap filter: the message names a color and carries a sus cue — else skip spaCy."""

    tokens = set(text.lower().replace(",", " ").split())
    return bool(tokens & colors) and bool(tokens & SUS_WORDS)


def _kill_roles(doc: Any, colors: set[str]) -> tuple[set[str], set[str]]:
    """``(killers, victims)`` read off ``<killer> kill(s|ed|ing) <victim>`` word order.

    Word order rather than dependency labels, deliberately. ``en_core_web_sm`` is
    trained on news/web English and mis-parses the subject-dropped form that
    dominates league chat: in ``saw red kill green`` it attaches *green* as ``dobj``
    of **saw** and reads "red kill" as a compound noun, so the dependency answer is
    simply wrong. Restore the dropped subject (``I saw red kill green``) and it
    parses correctly — but we do not get to rewrite what opponents type. Linear
    order is reliable for English SVO here and degrades gracefully when a color is
    missing on either side.
    """

    killers: set[str] = set()
    victims: set[str] = set()
    for tok in doc:
        if tok.lemma_.lower() not in KILL_LEMMAS and tok.lower_ not in KILL_FORMS:
            continue
        left = [t.lower_ for t in doc[: tok.i] if t.lower_ in colors]
        right = [t.lower_ for t in doc[tok.i + 1 :] if t.lower_ in colors]
        # "green was killed (by red)" inverts the roles.
        if any(child.dep_ == "auxpass" for child in tok.children):
            left, right = right, left
        if left:
            killers.add(left[-1])   # nearest color before the verb
        if right:
            victims.add(right[0])   # nearest color after it
    return killers, victims


def _extract(nlp: Any, text: str, colors: set[str]) -> set[str]:
    """The colors this message *accuses*, with dependency-based negation scope.

    For each color token: gather its clause (the head-chain's subtrees); it's accused
    iff that clause carries a sus cue, the color isn't a victim, and the clause isn't
    negated/defended. Being named as a killer is itself the cue, and outranks the
    victim tests — otherwise a witnessed kill, the strongest evidence available,
    reads as no evidence.
    """

    doc = nlp(text)
    killers, victims = _kill_roles(doc, colors)
    accused: set[str] = set()
    for tok in doc:
        low = tok.lower_
        if low not in colors:
            continue
        is_killer = low in killers
        chain = _head_chain(tok)
        clause = {t for c in chain for t in c.subtree}
        if not is_killer:
            # The victim of a reported kill is the one player the sentence clears.
            if low in victims:
                continue
            if not any(t.lower_ in SUS_WORDS for t in clause):
                continue
            if any(t.lower_ in VICTIM_WORDS and abs(t.i - tok.i) <= 2 for t in doc):
                continue
        if not _negated(doc, chain, clause):
            accused.add(low)
    return accused


def _head_chain(tok: Any, depth: int = 6) -> list[Any]:
    chain = [tok]
    head = tok
    for _ in range(depth):
        if head.head == head:
            break
        head = head.head
        chain.append(head)
    return chain


def _negated(doc: Any, chain: list[Any], clause: set[Any]) -> bool:
    chainset = set(chain)
    return (
        any(child.dep_ == "neg" for c in chain for child in c.children)
        or any(t.lower_ in NEG_WORDS and t.head in chainset for t in doc)
        or any(t.lower_ in DEFENSE_WORDS and (t.head in chainset or t in clause) for t in doc)
    )
