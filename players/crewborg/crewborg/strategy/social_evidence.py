"""Social evidence: cumulative meeting-public counters.

Maintains the per-player counters behind the fitted suspicion model's "public"
features (design: ``suspicion_lab/README.md`` §5/§10; offline mirror:
``suspicion_lab/tools/features.py`` — keep definitions aligned):

- **Chat stances** — each meeting chat line reduces to ``(speaker, stance, target)``
  via ``strategy.claims``, the one parser both roles share; bumps
  ``accusations_made`` on the speaker and ``times_accused`` / ``times_defended`` on
  the target. Unparseable lines are dropped, never guessed at.
- **Vote tallies** — the voting UI's dots attribute every vote (voter slot →
  target slot); at meeting end they are committed once into ``votes_cast`` /
  ``votes_skipped`` / ``voted_against_me`` / ``vote_agreed_with_me``.
Counters are cumulative for the whole episode (evidence never resets at meetings)
and live on ``PlayerRecord``; ``suspicion._fitted_features`` reads them.
"""

from __future__ import annotations

from crewborg.strategy.claims import parse_claims
from crewborg.types import Belief

SKIP_VOTE_TARGET = -2  # perception.entities.VoteDot sentinel


def update_social_evidence(belief: Belief) -> None:
    """Fold this tick's public/social observations into the roster counters.

    Runs in the fast loop after ``update_event_log`` (it reads the task-dwell
    intervals that logger maintains) and before ``update_suspicion``.
    """

    _count_chat_stances(belief)
    _track_meeting_votes(belief)
    _bank_meeting_caller(belief)


# --- chat stances -------------------------------------------------------------


def _count_chat_stances(belief: Belief) -> None:
    """Bump the roster counters from parsed claims.

    This used to run its own ACCUSE_HINT / DEFEND_HINT keyword match -- a third
    reading of the same chat, alongside the crew solver's regex parser and the
    imposter bandwagon's spaCy one, each with its own idea of what an accusation
    is. They are one parser now (``strategy.claims``) and this is a projection of
    it: stance ``accuse`` credits the speaker and debits the target, ``defend``
    credits the target.

    Parses are memoized in ``strategy.claims``, which matters here specifically --
    this runs every tick over the whole chat log.
    """

    if not belief.chat_log:
        return
    colors = set(belief.roster)
    if not colors:
        return
    for event in belief.chat_log:
        key = (event.tick, event.speaker_color, event.text)
        if key in belief.social_counted_chats:
            continue
        belief.social_counted_chats.add(key)
        speaker = belief.roster.get(event.speaker_color)
        for claim in parse_claims(
            event.text,
            speaker_color=event.speaker_color,
            colors=colors,
            meeting_id=0,
            tick=event.tick,
        ):
            for name in claim.targets:
                if name == event.speaker_color:
                    continue
                target = belief.roster.get(name)
                if claim.stance == "defend":
                    if target is not None:
                        target.times_defended += 1
                else:
                    if speaker is not None:
                        speaker.accusations_made += 1
                    if target is not None:
                        target.times_accused += 1


# --- vote tallies ---------------------------------------------------------------


def _track_meeting_votes(belief: Belief) -> None:
    """Stage the voting UI's dots while the meeting runs; commit once when it ends."""

    voting = belief.voting
    if voting.dots and voting.candidates:
        # Stage (overwrite) — dots are cumulative within a meeting, and the meeting
        # is identified by when its Voting phase opened.
        belief.social_staged_votes = {(d.voter, d.target) for d in voting.dots}
        belief.social_staged_slots = {c.slot: c.color for c in voting.candidates}
        belief.social_staged_meeting_tick = belief.phase_start_tick if belief.phase == "Voting" else (
            belief.social_staged_meeting_tick or belief.phase_start_tick
        )
        return

    # No dots on screen: if a staged meeting is pending and the meeting is over,
    # commit it exactly once.
    if not belief.social_staged_votes or belief.phase == "Voting":
        return
    if belief.social_staged_meeting_tick == belief.social_banked_meeting_tick:
        belief.social_staged_votes = set()
        return

    slots = belief.social_staged_slots
    my_target: int | None = None
    my_slot: int | None = None
    for slot, color in slots.items():
        if color == belief.self_color:
            my_slot = slot
            break
    for voter, target in belief.social_staged_votes:
        if voter == my_slot:
            my_target = target
            break
    for voter, target in belief.social_staged_votes:
        if voter == my_slot:
            continue
        record = belief.roster.get(slots.get(voter, ""))
        if record is None:
            continue
        if target == SKIP_VOTE_TARGET:
            record.votes_skipped += 1
            continue
        record.votes_cast += 1
        if slots.get(target) == belief.self_color:
            record.voted_against_me += 1
        if my_target is not None and my_target != SKIP_VOTE_TARGET and target == my_target:
            record.vote_agreed_with_me += 1

    belief.social_banked_meeting_tick = belief.social_staged_meeting_tick
    belief.social_staged_votes = set()
    belief.social_staged_slots = {}


# --- meeting caller (the MeetingCall interstitial, game 4b9297d) -------------------


def _bank_meeting_caller(belief: Belief) -> None:
    """Credit the meeting caller once per interstitial sighting.

    ``update_belief`` latches (caller, kind, seen_tick) while the interstitial is
    up and clears it when play resumes; the seen-tick is the dedup key. Reporting
    a body and pressing the button are separate (both exculpatory-leaning) cues.
    """

    if belief.meeting_caller_color is None or belief.meeting_call_seen_tick is None:
        return
    if belief.social_caller_banked_tick == belief.meeting_call_seen_tick:
        return
    record = belief.roster.get(belief.meeting_caller_color)
    if record is None:
        return  # "Someone"/unknown display name — not a roster color; ignore
    if belief.meeting_call_kind == "body":
        record.reported_bodies += 1
    elif belief.meeting_call_kind == "button":
        record.button_calls_made += 1
    belief.social_caller_banked_tick = belief.meeting_call_seen_tick
