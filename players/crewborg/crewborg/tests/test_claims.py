"""The one claim parser both roles read chat through (`strategy.claims`).

This module replaced three separate implementations, so its contract is now the
contract for the crew solver, the imposter bandwagon, and the roster counters at
once. Everything those three used to assert independently belongs here.
"""

from __future__ import annotations

import pytest

from crewborg import nlp as chat_nlp
from crewborg.strategy.claims import normalize, parse_claims

COLORS = {"red", "blue", "green", "yellow", "orange", "pink", "purple", "cyan"}


@pytest.fixture(scope="module", autouse=True)
def _model():
    import spacy

    saved = chat_nlp._model
    chat_nlp._model = spacy.load("en_core_web_sm", disable=["ner"])
    yield chat_nlp._model
    chat_nlp._model = saved


def _claims(text: str, speaker: str = "green"):
    return parse_claims(
        text, speaker_color=speaker, colors=COLORS, meeting_id=0, tick=1
    )


def _accused(text: str, speaker: str = "green") -> set[str]:
    return {
        t
        for c in _claims(text, speaker)
        if c.stance in ("accuse", "at_least_one")
        for t in c.targets
    }


# --- no model means no claims, distinctly from "nothing asserted" ---------------


def test_without_a_model_there_are_no_claims() -> None:
    saved = chat_nlp._model
    chat_nlp._model = None
    try:
        assert _claims("red sus") == []
    finally:
        chat_nlp._model = saved


def test_a_miss_while_the_model_loads_is_not_cached_forever() -> None:
    """The model loads in a background thread, so early chat can arrive before it.

    Parses are memoized, so if a pre-load miss were cached the utterance would stay
    unread for the whole episode even once the model came up -- the first meeting's
    chat, silently blank. Readiness must be checked before the cache, not after.
    """

    text = "purple sus: lurking on a vent"
    saved = chat_nlp._model
    chat_nlp._model = None
    try:
        assert _claims(text) == []
    finally:
        chat_nlp._model = saved
    assert _accused(text) == {"purple"}


# --- normalization is the thing that makes the parser work ----------------------


def test_normalize_restores_a_dropped_subject() -> None:
    assert normalize("saw pink kill orange").startswith("I saw")


def test_normalize_gives_a_colon_label_a_copula() -> None:
    assert "is suspicious" in normalize("red sus: they were tailing me")


def test_normalize_expands_game_slang() -> None:
    assert "suspicious" in normalize("red is sus")
    assert "impostor" in normalize("red is the imposter")


# --- accusations ----------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "red sus",
        "red is sus",
        "red looks suspicious",
        "vote red",
        "I vote for red",
        "red vented",
        "red was following people",
        "red sus: they were tailing me",
        "red sus: lurking on a vent. vote red",
    ],
)
def test_plain_accusations(text: str) -> None:
    assert _accused(text) == {"red"}, _claims(text)


@pytest.mark.parametrize(
    "text",
    ["no read, skipping", "skip", "gg everyone nice game", "i was in nav"],
)
def test_contentless_lines_assert_nothing(text: str) -> None:
    assert _claims(text) == []


def test_a_bare_sighting_is_not_an_accusation() -> None:
    # Seeing someone is an alibi, not a charge. Only seeing them DO something is.
    assert _accused("I saw red in nav") == set()
    assert _accused("I saw red venting") == {"red"}


# --- negation -------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["red is not sus", "red isn't sus", "red didn't kill green", "red is not venting"],
)
def test_negation_suppresses_the_accusation(text: str) -> None:
    assert "red" not in _accused(text), _claims(text)


# --- kill reports ---------------------------------------------------------------
#
# Both predecessors got this wrong, in opposite directions, and neither noticed:
# the regex parser dropped "saw pink kill orange" entirely because its predicate
# demanded an inflected kill verb, while the spaCy bandwagon parser accused the
# VICTIM (its victim-word list had "killed" but not "kill") or, when both colors
# fell inside its ±2-token window, accused nobody at all.


@pytest.mark.parametrize(
    "text",
    [
        "saw pink kill orange",
        "i saw pink kill orange",
        "pink killed orange",
        "pink kills orange",
        "pink was killing orange",
        "saw pink kill orange, vote pink",
    ],
)
def test_a_kill_report_accuses_the_killer(text: str) -> None:
    assert "pink" in _accused(text), _claims(text)


@pytest.mark.parametrize(
    "text",
    [
        "saw pink kill orange",
        "i saw pink kill orange",
        "pink killed orange",
        "pink kills orange",
    ],
)
def test_a_kill_report_never_accuses_the_victim(text: str) -> None:
    assert "orange" not in _accused(text), _claims(text)


def test_a_passive_kill_report_inverts_the_roles() -> None:
    accused = _accused("orange was killed by pink")
    assert "pink" in accused and "orange" not in accused, accused


# --- attribution: source is not always the speaker ------------------------------
#
# The solver keeps `source_color` separate from `speaker_color` so a relay is
# credited to whoever is being quoted -- and per-speaker trust tempers evidence by
# `source`, so losing this would silently mis-weight every relayed claim.


@pytest.mark.parametrize(
    "text",
    ["yellow saw cyan vent", "yellow saw cyan venting", "yellow saw cyan kill red"],
)
def test_a_relay_is_attributed_to_the_quoted_player(text: str) -> None:
    claims = [c for c in _claims(text) if c.stance == "accuse"]
    assert claims, text
    assert claims[0].source_color == "yellow"
    assert claims[0].speaker_color == "green"
    assert claims[0].provenance == "relayed"
    assert claims[0].targets == ("cyan",)


def test_a_first_person_report_is_attributed_to_the_speaker() -> None:
    claim = next(c for c in _claims("I saw cyan venting") if c.stance == "accuse")
    assert claim.source_color == "green" and claim.provenance == "direct"


def test_a_claim_never_targets_its_own_source() -> None:
    assert _claims("red sus", speaker="red") == []


# --- defenses and disjunctions ---------------------------------------------------


def test_a_defense_is_not_an_accusation() -> None:
    claims = _claims("red is clear, was with me")
    assert [c.stance for c in claims] == ["defend"]
    assert claims[0].targets == ("red",)


def test_either_or_becomes_one_at_least_one_claim() -> None:
    claims = _claims("either red or blue is the impostor")
    assert [c.stance for c in claims] == ["at_least_one"]
    assert set(claims[0].targets) == {"red", "blue"}


def test_two_separate_accusations_stay_separate() -> None:
    claims = _claims("red sus, blue also sus")
    assert {c.targets[0] for c in claims} == {"red", "blue"}
    assert all(c.stance == "accuse" for c in claims)


# --- evidence kind ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("red vented", "vent"),
        ("saw pink kill orange", "body"),
        ("red was following me", "sighting"),
        ("vote red", "vote"),
        ("red sus", "bare"),
    ],
)
def test_evidence_kind_grades_the_claim(text: str, kind: str) -> None:
    claims = [c for c in _claims(text) if c.stance == "accuse"]
    assert claims and claims[0].evidence_kind == kind, claims


# --- multi-sentence input --------------------------------------------------------
#
# `_kill_roles` and the perception fallback both read tokens by POSITION. `token.i`
# is doc-absolute while a sentence Span slices span-relative, so mixing them reads
# the wrong side of the verb in the first sentence and raises IndexError on every
# later one. Single-sentence fixtures cannot catch it; real chat is multi-sentence.


def test_kill_roles_are_correct_in_a_later_sentence() -> None:
    text = "Orange reported fast. Who was near the body? saw pink kill orange"
    accused = _accused(text)
    assert "pink" in accused and "orange" not in accused, _claims(text)


def test_a_relay_in_a_later_sentence_keeps_its_source() -> None:
    text = "Blue is dead. Who found the body? yellow saw cyan vent"
    claim = next(
        c for c in _claims(text) if c.stance == "accuse" and c.targets == ("cyan",)
    )
    assert claim.source_color == "yellow" and claim.provenance == "relayed"


def test_long_multi_sentence_chat_does_not_raise() -> None:
    text = (
        "Pink called body on orange. Pink was near the kill. Cyan also near kill. "
        "Who else saw orange die? Red, blue, green were following people. vote pink"
    )
    assert _claims(text) is not None
