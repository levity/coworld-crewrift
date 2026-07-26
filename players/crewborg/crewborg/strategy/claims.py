"""The single claim parser. Both roles read the same chat, so they read it here.

Until now there were THREE implementations of "what does this utterance assert",
all fed the same meeting chat, all drifting apart:

  * ``social_evidence.parse_social_claims``  regex templates -> crew solver
  * ``meeting.chat_read._extract``          spaCy, coarse    -> imposter bandwagon
  * ``social_evidence._count_chat_stances`` keyword hints    -> suspicion counters

They disagreed, and each carried its own bugs. A single afternoon turned up the
same class of mistake -- an inflection list that forgot a form -- independently in
two of them: the regex path spelled the kill verb ``kill(?:ed|ing|s)`` and so
dropped "saw pink kill orange" entirely, while ``chat_read`` put "killed" in its
victim words but not "kill" and so accused the victim, or (when both colors fell
inside its proximity window) accused nobody at all.

This module is the replacement, and the other two are now projections over it:
``chat_read.chat_accusers`` counts distinct sources per accused target, and the
roster counters read stance directly.

WHY spaCy AND NOT REGEX. Today's league opponents emit templated strings -- 71% of
observed lines come from templates recurring three or more times, and 30% are the
single string "no read, skipping" -- so regex looks adequate when measured against
today's field. It is not a bet worth keeping. Opponents are already appearing with
LLM-driven meeting policies whose speech is free-form, and a pattern list only ever
covers what someone remembered to write down.

THE THING THAT MAKES spaCy WORK HERE IS NORMALIZATION, NOT CONFIGURATION.
``en_core_web_sm`` is trained on OntoNotes news/web text. League chat is
subject-dropped fragments in which every color word is an ordinary English
ADJECTIVE and "sus" is out of vocabulary. Measured on the raw string:

    saw pink kill orange
      pink   ADJ    amod       head=kill
      kill   VERB   compound   head=orange
      orange PROPN  dobj       head=saw     <- the VICTIM, as object of "saw"

It reads "pink kill" as a compound noun and makes the victim the thing seen.
Restore the dropped subject and it is correct:

    I saw pink kill orange
      kill   VERB   ccomp      head=saw
      orange PROPN  dobj       head=kill

Forcing the color tokens to PROPN does NOT fix this on its own -- the stock
``attribute_ruler`` runs AFTER the parser, so it relabels without re-parsing. We do
both: repair the text into grammatical English first, and put the POS override
before the parser in the pipeline.

The normalizer is deliberately general linguistic repair -- restore a dropped
subject, expand game slang to real words, split comma-spliced clauses -- and not a
list of the templates we happen to see today. That distinction is the whole point
of the change.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from crewborg import nlp as chat_nlp

# The claim vocabulary lives here, with the only code that produces it.
ClaimStance = Literal["accuse", "defend", "at_least_one"]
EvidenceKind = Literal["bare", "body", "vent", "sighting", "vote"]
ClaimProvenance = Literal["direct", "relayed"]


class SocialClaim(BaseModel):
    """One relational assertion parsed out of a single public utterance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    meeting_id: int
    tick: int
    speaker_color: str | None
    targets: tuple[str, ...]
    stance: ClaimStance
    # The player the assertion is attributed to. Differs from the speaker for
    # relays such as "Yellow saw cyan vent."
    source_color: str | None = None
    provenance: ClaimProvenance = "direct"
    evidence_kind: EvidenceKind = "bare"
    text: str

# --- vocabulary ---------------------------------------------------------------
# Surface forms as well as lemmas throughout, because the lemma cannot be trusted
# on this vocabulary: in "red kills green" the tagger calls `kills` a PROPN with
# lemma "kills", so a lemma-only test silently misses the present tense.

KILL_FORMS = frozenset({
    "kill", "kills", "killed", "killing",
    "murder", "murders", "murdered", "murdering",
    "stab", "stabs", "stabbed", "stabbing",
})
# Predicates that make their SUBJECT the suspect ("<C> is sus", "<C> vented").
SUS_PREDICATES = frozenset({
    "sus", "suspicious", "imposter", "impostor", "imp", "threat", "shady",
    "lying", "liar", "lied", "lie", "faking", "fake", "faked", "deflecting",
    "guilty",
})
ACTION_VERBS = frozenset({
    "vent", "vents", "vented", "venting", "lurk", "lurks", "lurked", "lurking",
    "follow", "follows", "followed", "following", "tail", "tails", "tailed",
    "tailing", "fake", "fakes", "faked", "faking", "deflect", "deflects",
    "deflecting", "push", "pushes", "pushed", "pushing", "lie", "lied", "lying",
})
# "X saw Y ..." attributes the claim to X rather than to whoever is speaking.
PERCEPTION_VERBS = frozenset({
    "see", "saw", "seen", "watch", "watched", "catch", "caught", "spot",
    "spotted", "notice", "noticed",
})
VOTE_FORMS = frozenset({"vote", "votes", "voted", "voting"})
FIRST_PERSON = frozenset({"i", "we"})
# A bare sighting is not an accusation -- "I saw yellow in nav" is an alibi, not a
# charge. One of these has to be in scope for a perception report to accuse.
OBSERVATION_CUES = frozenset({
    "sus", "suspicious", "vent", "vents", "vented", "venting", "lurk", "lurking",
    "body", "bodies", "dead", "died", "corpse",
    "follow", "follows", "followed", "following",
    "tail", "tails", "tailed", "tailing",
    "fake", "faked", "faking", "lie", "lied", "lying",
}) | KILL_FORMS
DEFEND_CUES = frozenset({
    "clear", "cleared", "clears", "safe", "innocent", "vouch", "vouching",
    "trust", "credible",
})
# A color adjacent to one of these is the victim of the event, not its author.
VICTIM_CUES = frozenset({"die", "died", "dies", "dead", "body", "bodies", "corpse"})
NEG_WORDS = frozenset({
    "not", "n't", "no", "never", "isnt", "dont", "doesnt", "didnt", "cant", "aint",
})
DISJUNCTION = frozenset({"either", "or"})

# Cue -> evidence strength, mirroring the solver's weight table.
_KIND_CUES: tuple[tuple[EvidenceKind, frozenset[str]], ...] = (
    ("vent", frozenset({"vent", "vents", "vented", "venting"})),
    ("body", KILL_FORMS | frozenset({"body", "bodies", "dead", "died", "report",
                                     "reported", "corpse"})),
    ("sighting", PERCEPTION_VERBS | frozenset({
        "follow", "follows", "followed", "following",
        "tail", "tails", "tailed", "tailing",
    })),
    ("vote", VOTE_FORMS),
)


# --- normalization ------------------------------------------------------------

_SLANG = (
    (re.compile(r"\bsus\b(?!\w)", re.I), "suspicious"),
    (re.compile(r"\bimp\b(?!\w)", re.I), "impostor"),
    (re.compile(r"\bimposter\b", re.I), "impostor"),
)
# "<C> sus: <reasons>" -- a label followed by a colon-introduced reason list.
_LABEL_COLON = re.compile(r"\b(\w+)\s+sus\s*:", re.I)
# A finite verb opening a sentence with no subject.
_DROPPED_SAW = re.compile(r"(^|(?<=[.;!?])\s*)(saw|seen|caught|spotted)\b", re.I)
_DROPPED_VOTE = re.compile(r"(^|(?<=[.,;!?])\s*)(vote|voting)\s+(?=\w)", re.I)
# Comma-spliced clause lists: each item wants its own root to parse.
_CLAUSE_SPLICE = re.compile(
    r",\s*(?=(they|he|she|it|lurking|next to|followed|following|I saw|I vote)\b)",
    re.I,
)


def normalize(text: str) -> str:
    """Repair chat fragments into something the parser was trained to handle.

    General repairs only: expand slang to real words, restore an elided subject,
    give a colon-introduced label a copula, split comma splices. Nothing here keys
    on a template we have observed -- that is the difference between fixing the
    input and hard-coding the field.
    """

    out = _LABEL_COLON.sub(r"\1 is suspicious.", text)
    out = _DROPPED_SAW.sub(r"\1I \2", out)
    out = _DROPPED_VOTE.sub(r"\1I vote for ", out)
    for pattern, replacement in _SLANG:
        out = pattern.sub(replacement, out)
    out = _CLAUSE_SPLICE.sub(". ", out)
    return re.sub(r"\s{2,}", " ", out).strip()


# --- parsing ------------------------------------------------------------------


def _pipeline(model: Any) -> Any:
    """Attach the color->PROPN override BEFORE the parser, once per model.

    Order matters and is the reason the stock `attribute_ruler` is not enough: it
    sits after the parser, so it can relabel tokens but cannot change the tree.
    """

    if model is None or model.has_pipe("crewborg_color_propn"):
        return model
    from spacy.language import Language

    if not Language.has_factory("crewborg_color_propn"):

        @Language.component("crewborg_color_propn")
        def _force(doc):  # pragma: no cover - exercised through parse_claims
            for token in doc:
                if token.lower_ in _color_registry:
                    token.pos_ = "PROPN"
                    token.tag_ = "NNP"
            return doc

    model.add_pipe("crewborg_color_propn", before="parser")
    return model


# Colors are a closed vocabulary but not a constant: the roster is per-episode, and
# the pipeline component needs them at parse time.
_color_registry: frozenset[str] = frozenset()


def _head_chain(token: Any, depth: int = 6) -> list[Any]:
    chain = [token]
    head = token
    for _ in range(depth):
        if head.head is head:
            break
        head = head.head
        chain.append(head)
    return chain


def _negated(chain: list[Any]) -> bool:
    chainset = set(chain)
    return any(
        child.dep_ == "neg" or child.lower_ in NEG_WORDS
        for node in chain
        for child in node.children
    ) or any(node.lower_ in NEG_WORDS for node in chainset)


def _kill_roles(doc: Any, colors: frozenset[str]) -> tuple[set[str], set[str]]:
    """``(killers, victims)`` from ``<killer> kill(s|ed|ing) <victim>`` word order.

    Word order rather than dependency labels, because the subject-dropped form
    mis-parses (see the module docstring) and order survives that. ``auxpass``
    inverts the roles for "green was killed by red".
    """

    killers: set[str] = set()
    victims: set[str] = set()
    # Materialise the tokens and index into THAT. `doc` here is usually a sentence
    # Span, whose slicing is span-relative, while `token.i` is doc-absolute -- mixing
    # them silently reads the wrong side of the verb on the first sentence and raises
    # on every later one.
    tokens = list(doc)
    for index, token in enumerate(tokens):
        if token.lower_ not in KILL_FORMS and token.lemma_.lower() not in KILL_FORMS:
            continue
        left = [t.lower_ for t in tokens[:index] if t.lower_ in colors]
        right = [t.lower_ for t in tokens[index + 1 :] if t.lower_ in colors]
        if any(child.dep_ == "auxpass" for child in token.children):
            left, right = right, left
        if left:
            killers.add(left[-1])
        if right:
            victims.add(right[0])
    return killers, victims


def _victims(doc: Any, colors: frozenset[str]) -> set[str]:
    """Colors the sentence marks as the casualty rather than the culprit."""

    _, victims = _kill_roles(doc, colors)
    for token in doc:
        if token.lower_ not in colors:
            continue
        head = token.head
        if head.lower_ in VICTIM_CUES or head.lemma_.lower() in VICTIM_CUES:
            victims.add(token.lower_)
        # "orange's body", "body of orange"
        if any(child.lower_ in VICTIM_CUES for child in head.children):
            if token.dep_ in ("poss", "pobj", "nsubj", "nsubjpass"):
                victims.add(token.lower_)
    return victims


def _evidence_kind(text: str) -> EvidenceKind:
    lowered = set(re.findall(r"[a-z']+", text.lower()))
    for kind, cues in _KIND_CUES:
        if lowered & cues:
            return kind
    return "bare"


def _defended(doc: Any, colors: frozenset[str]) -> set[str]:
    out: set[str] = set()
    for token in doc:
        if token.lower_ not in colors:
            continue
        chain = _head_chain(token)
        clause = {t for node in chain for t in node.subtree}
        if any(t.lower_ in DEFEND_CUES or t.lemma_.lower() in DEFEND_CUES
               for t in clause):
            out.add(token.lower_)
        # "was with me" is co-presence; the solver decides what to do with it.
        if any(t.lower_ == "with" for t in clause) and any(
            t.lower_ == "me" for t in clause
        ):
            out.add(token.lower_)
    return out


def _accusations(
    doc: Any,
    colors: frozenset[str],
    speaker: str | None,
) -> list[tuple[str | None, str, ClaimProvenance]]:
    """``(source, target, provenance)`` for every accusation in the sentence."""

    killers, _ = _kill_roles(doc, colors)
    victims = _victims(doc, colors)
    found: list[tuple[str | None, str, ClaimProvenance]] = []
    attributed: set[str] = set()
    # Span-relative, for the same reason `_kill_roles` materialises its tokens.
    tokens = list(doc)
    position = {token: index for index, token in enumerate(tokens)}

    # Perception reports. "<C> saw <D> venting" attributes the claim to C rather
    # than to whoever is relaying it -- which is the whole reason the solver wants a
    # `source` distinct from `speaker_color`, and what per-speaker trust keys on.
    # "I saw <D> venting" is the same shape with the speaker as source.
    for token in doc:
        if token.lower_ not in PERCEPTION_VERBS and token.lemma_.lower() not in PERCEPTION_VERBS:
            continue
        if _negated(_head_chain(token)):
            continue
        subjects = [
            child for child in token.children if child.dep_ in ("nsubj", "nsubjpass")
        ]
        color_subjects = [s.lower_ for s in subjects if s.lower_ in colors]
        first_person = any(s.lower_ in FIRST_PERSON for s in subjects)
        # Word-order fallback, for the same reason `_kill_roles` uses one: the tagger
        # frequently makes a leading color an `amod` of the verb rather than its
        # subject ("yellow saw cyan kill red" -> yellow/amod), because these words
        # are ordinary English adjectives. The token immediately before a perception
        # verb is its subject in every construction we see.
        index = position.get(token, 0)
        if not color_subjects and not first_person and index > 0:
            previous = tokens[index - 1]
            if previous.lower_ in colors:
                color_subjects = [previous.lower_]
            elif previous.lower_ in FIRST_PERSON:
                first_person = True
        if color_subjects:
            source: str | None = color_subjects[0]
        elif first_person:
            source = speaker
        else:
            continue
        scope = set(token.subtree)
        # Seeing someone is not accusing them; seeing them DO something is.
        if not any(
            t.lower_ in OBSERVATION_CUES or t.lemma_.lower() in OBSERVATION_CUES
            for t in scope
        ):
            continue
        seen = {
            t.lower_
            for t in scope
            if t.lower_ in colors and t.lower_ != source and t.lower_ not in victims
        }
        for target in sorted(seen):
            attributed.add(target)
            found.append((source, target, "relayed" if source != speaker else "direct"))

    for token in doc:
        low = token.lower_
        if low not in colors or low in victims or low in attributed:
            continue
        chain = _head_chain(token)
        if _negated(chain):
            continue
        head = token.head
        siblings = list(head.children)
        is_suspect = (
            # "<C> is suspicious" / "<C> looks sus"
            (token.dep_ in ("nsubj", "nsubjpass")
             and any(s.lower_ in SUS_PREDICATES or s.lemma_.lower() in SUS_PREDICATES
                     for s in siblings))
            # "<C> suspicious" with no copula, and "the suspicious <C>"
            or (head.lower_ in SUS_PREDICATES or head.lemma_.lower() in SUS_PREDICATES)
            # "<C> vented", "<C> was following people"
            or (head.lower_ in ACTION_VERBS or head.lemma_.lower() in ACTION_VERBS)
            # "vote <C>" / "I vote for <C>"
            or (head.lower_ in VOTE_FORMS or head.lemma_.lower() in VOTE_FORMS)
            or (head.lower_ == "for" and (head.head.lower_ in VOTE_FORMS
                                          or head.head.lemma_.lower() in VOTE_FORMS))
            or low in killers
        )
        if is_suspect:
            found.append((speaker, low, "direct"))
    return found


def _parse(text: str, speaker: str | None, colors: frozenset[str]):
    """Stance tuples for one utterance. The caller guarantees a loaded model."""

    global _color_registry

    model = chat_nlp.get_model()
    _color_registry = colors
    model = _pipeline(model)
    doc = model(normalize(text))

    out: list[tuple[ClaimStance, str | None, tuple[str, ...],
                    EvidenceKind, ClaimProvenance]] = []
    for sent in doc.sents:
        named = [t.lower_ for t in sent if t.lower_ in colors]
        if not named:
            continue
        kind = _evidence_kind(sent.text)
        defended = _defended(sent, colors)
        for target in sorted(defended):
            out.append(("defend", speaker, (target,), kind, "direct"))

        # "either red or blue" -- a disjunction over survivors, not two accusations.
        candidates = sorted({
            c for c in dict.fromkeys(named)
            if c not in defended and c not in _victims(sent, colors)
        })
        if (
            len(candidates) > 1
            and any(t.lower_ in DISJUNCTION for t in sent)
            and any(t.lower_ in SUS_PREDICATES or t.lower_ in ACTION_VERBS
                    or t.lower_ in KILL_FORMS for t in sent)
        ):
            out.append(("at_least_one", speaker, tuple(candidates), kind, "direct"))
            continue

        for source, target, provenance in _accusations(sent, colors, speaker):
            if target in defended:
                continue
            out.append(("accuse", source, (target,), kind, provenance))
    return out


@lru_cache(maxsize=512)
def _parse_cached(text: str, speaker: str | None, colors: frozenset[str]):
    return _parse(text, speaker, colors)


def parse_claims(
    text: str,
    *,
    speaker_color: str | None,
    colors: set[str] | frozenset[str],
    meeting_id: int,
    tick: int,
) -> list[SocialClaim]:
    """Every assertion this utterance makes, as solver-shaped claims.

    Returns ``[]`` both when the line asserts nothing and when the model is not
    loaded; use ``crewborg.nlp.state()`` to tell those apart. Results are cached
    per (text, speaker, roster) because the roster counters run in the fast loop
    and would otherwise re-parse the whole chat log every tick.
    """

    if not text or not colors:
        return []
    # Check readiness BEFORE the cache, never after. The model loads in a background
    # thread, so early-meeting chat can arrive while it is still None -- and caching
    # that as "asserts nothing" would freeze the miss in place, leaving those lines
    # permanently unread for the rest of the episode even once the model is up.
    if chat_nlp.get_model() is None:
        return []
    parsed = _parse_cached(text, speaker_color, frozenset(c.lower() for c in colors))
    if not parsed:
        return []

    canonical = {c.lower(): c for c in colors}
    claims: dict[tuple, SocialClaim] = {}
    for stance, source, targets, kind, provenance in parsed:
        resolved = tuple(dict.fromkeys(canonical[t] for t in targets if t in canonical))
        source_color = canonical.get((source or "").lower(), source)
        if not resolved or source_color in resolved:
            continue
        key = (source_color, resolved, stance)
        if key in claims:
            continue
        claims[key] = SocialClaim(
            meeting_id=meeting_id,
            tick=tick,
            speaker_color=speaker_color,
            source_color=source_color,
            provenance=provenance,
            targets=resolved,
            stance=stance,
            evidence_kind=kind,
            text=text,
        )
    return list(claims.values())
