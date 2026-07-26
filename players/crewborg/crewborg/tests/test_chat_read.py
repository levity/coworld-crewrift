"""Meeting chat-NLP: dependency-parse accusation detection + the lifecycle flag."""

from __future__ import annotations

import pytest

from crewborg.modes import AttendMeetingMode
from crewborg.perception.entities import VoteCandidate, VotingState
from crewborg import nlp as chat_nlp
from crewborg.strategy.meeting import chat_read
from crewborg.types import ActionState, Belief, ChatEvent, PlayerRecord

_COLORS = ("red", "blue", "green", "yellow", "orange", "purple")


@pytest.fixture(scope="module")
def nlp_model():
    """Load the real model once and inject it (bypassing the async loader)."""

    import spacy

    model = spacy.load("en_core_web_sm", disable=["ner"])
    saved = chat_nlp._model
    chat_nlp._model = model
    yield model
    chat_nlp._model = saved


def _belief_with_chat(messages, *, self_color="orange", teammates=()) -> Belief:
    belief = Belief(self_role="imposter", teammate_colors=set(teammates))
    belief.voting = VotingState(self_marker_color=self_color)
    for color in _COLORS:
        belief.roster[color] = PlayerRecord(color=color, life_status="alive")
    belief.chat_log = [ChatEvent(tick=i, speaker_color=s, text=t) for i, (s, t) in enumerate(messages)]
    return belief


# --- lifecycle / flag -------------------------------------------------------


def test_disabled_flag_turns_chat_nlp_off(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_CHAT_NLP", "0")
    assert chat_nlp.is_enabled() is False
    monkeypatch.setenv("CREWBORG_CHAT_NLP", "1")
    assert chat_nlp.is_enabled() is True


def test_no_model_means_no_chat_signal() -> None:
    # Without a loaded model (disabled / still loading), there is no chat signal at all.
    saved = chat_nlp._model
    chat_nlp._model = None
    try:
        belief = _belief_with_chat([("blue", "red sus")])
        assert chat_read.chat_accusers(belief) == {}
    finally:
        chat_nlp._model = saved


# --- accusation detection ---------------------------------------------------


def test_a_plain_accusation_is_detected(nlp_model) -> None:
    assert chat_read.chat_accusers(_belief_with_chat([("blue", "red sus")])) == {"red": 1}


def test_negated_accusation_is_not_counted(nlp_model) -> None:
    assert chat_read.chat_accusers(_belief_with_chat([("blue", "red isn't sus")])) == {}
    assert chat_read.chat_accusers(_belief_with_chat([("blue", "i don't think red did it")])) == {}


def test_a_teammate_is_never_counted_as_accused(nlp_model) -> None:
    belief = _belief_with_chat([("blue", "red sus")], teammates=["red"])
    assert chat_read.chat_accusers(belief) == {}


def test_our_own_chat_is_ignored(nlp_model) -> None:
    # self (orange) accusing red is not a bandwagon signal for us.
    assert chat_read.chat_accusers(_belief_with_chat([("orange", "red sus")])) == {}


def test_distinct_accusers_are_counted(nlp_model) -> None:
    belief = _belief_with_chat([("blue", "red sus"), ("green", "vote red")])
    assert chat_read.chat_accusers(belief) == {"red": 2}


def test_the_same_speaker_counts_once(nlp_model) -> None:
    belief = _belief_with_chat([("blue", "red sus"), ("blue", "red vented for sure")])
    assert chat_read.chat_accusers(belief) == {"red": 1}


def test_non_accusation_chatter_is_filtered_by_the_gate(nlp_model) -> None:
    # No color + sus-cue ⇒ the keyword gate skips it before spaCy.
    assert chat_read.chat_accusers(_belief_with_chat([("blue", "gg everyone nice game")])) == {}


# --- the victim of a reported kill is never the suspect ----------------------
#
# VICTIM_WORDS carried the past tense "killed" but not the bare infinitive "kill",
# so "saw red kill green" left green failing the victim test while "kill" and "saw"
# both sat in SUS_WORDS and supplied a cue for its clause. green -- the one player
# the sentence exonerates -- was returned as a suspect and fed the bandwagon.
# "saw <killer> kill <victim>" is the single most common kill report in league
# chat, so this was not an edge case.


def test_the_victim_of_a_kill_report_is_not_accused(nlp_model) -> None:
    belief = _belief_with_chat([("blue", "saw red kill green")])
    assert chat_read.chat_accusers(belief) == {"red": 1}


def test_victim_is_not_accused_across_kill_inflections(nlp_model) -> None:
    for text in (
        "saw red kill green",
        "i saw red kill green",
        "red killed green",
        "red kills green",
        "red is killing green",
    ):
        accused = chat_read.chat_accusers(_belief_with_chat([("blue", text)]))
        assert "green" not in accused, f"victim accused in {text!r}: {accused}"


def test_the_killer_is_still_accused(nlp_model) -> None:
    # Guard the fix against over-correction: suppressing the victim must not
    # suppress the killer too, or kill reports stop being a signal at all.
    # "red killed green" returned {} before the fix -- both colors sat within two
    # tokens of "killed", so the proximity test ate the killer as well.
    for text in ("saw red kill green", "red killed green"):
        assert "red" in chat_read.chat_accusers(_belief_with_chat([("blue", text)])), text


def test_passive_kill_report_inverts_the_roles(nlp_model) -> None:
    accused = chat_read.chat_accusers(_belief_with_chat([("blue", "green was killed by red")]))
    assert "green" not in accused, accused
    assert "red" in accused, accused


def test_a_negated_kill_report_accuses_nobody(nlp_model) -> None:
    # Being named as a killer overrides the victim tests, but must NOT override
    # negation scope, or "red didn't kill green" becomes an accusation.
    assert chat_read.chat_accusers(_belief_with_chat([("blue", "red didn't kill green")])) == {}


# --- end-to-end: chat suss drives the imposter bandwagon --------------------


def test_imposter_bandwagons_on_chat_suss_alone(nlp_model) -> None:
    mode = AttendMeetingMode()
    belief = Belief(phase="Voting", self_role="imposter", teammate_colors={"green"})
    belief.voting = VotingState(
        timer_present=True, self_marker_color="orange",
        candidates=(VoteCandidate(slot=0, color="red", alive=True), VoteCandidate(slot=1, color="blue", alive=True)),
    )
    belief.roster["red"] = PlayerRecord(color="red", life_status="alive")
    belief.chat_log = [  # no votes cast yet — only chat heat on red
        ChatEvent(tick=1, speaker_color="yellow", text="red sus"),
        ChatEvent(tick=2, speaker_color="purple", text="vote red"),
    ]
    chat = mode.decide(belief, ActionState())
    assert chat.kind == "chat" and chat.text.startswith("red sus:")  # piled on via chat alone


# --- async loader -----------------------------------------------------------


def test_ensure_loading_loads_the_model_in_the_background() -> None:
    saved = (chat_nlp._model, chat_nlp._thread, chat_nlp._failed)
    chat_nlp._model = chat_nlp._thread = None
    chat_nlp._failed = False
    try:
        chat_nlp.ensure_loading()
        assert chat_nlp._thread is not None
        chat_nlp._thread.join(timeout=30)
        assert chat_nlp.get_model() is not None  # loaded off the hot path
    finally:
        chat_nlp._model, chat_nlp._thread, chat_nlp._failed = saved


def test_ensure_loading_is_a_noop_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_CHAT_NLP", "0")
    saved = (chat_nlp._model, chat_nlp._thread, chat_nlp._failed)
    chat_nlp._model = chat_nlp._thread = None
    chat_nlp._failed = False
    try:
        chat_nlp.ensure_loading()
        assert chat_nlp._thread is None and chat_nlp.get_model() is None
    finally:
        chat_nlp._model, chat_nlp._thread, chat_nlp._failed = saved
