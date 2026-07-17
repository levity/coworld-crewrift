"""Social evidence: cumulative meeting-public + watched-completion counters.

Maintains the per-player counters behind the fitted suspicion model's "public"
features (design: ``suspicion_lab/README.md`` §5/§10; offline mirror:
``suspicion_lab/tools/features.py`` — keep definitions aligned):

- **Chat stances** — each meeting chat line reduces to ``(speaker, stance, target)``
  with ``stance ∈ {accuses, defends}`` via the same templated-chat heuristics the
  offline extractor uses; bumps ``accusations_made`` on the speaker and
  ``times_accused`` / ``times_defended`` on the target. Unparseable lines are
  dropped, never guessed at.
- **Vote tallies** — the voting UI's dots attribute every vote (voter slot →
  target slot); at meeting end they are committed once into ``votes_cast`` /
  ``votes_skipped`` / ``voted_against_me`` / ``vote_agreed_with_me``.
- **Watched real-task completion** — the strongest exculpatory cue (imposters
  cannot complete tasks). Detected when the global ``crew_tasks_remaining`` HUD
  counter decrements by exactly one while exactly one visible, living player is
  finishing a near-full task-site dwell. A fake task hold (Pretend) never
  decrements the counter, so it can't trigger this. Stricter than the offline
  truth (completion-while-visible): we must watch most of the dwell — the
  undercount only pulls posteriors toward the prior, never past it.

Counters are cumulative for the whole episode (evidence never resets at meetings)
and live on ``PlayerRecord``; ``suspicion._fitted_features`` reads them.
"""

from __future__ import annotations

import re

from crewborg.types import (
    Belief,
    ChatEvent,
    MeetingRecord,
    SocialClaim,
    SolverClaimStance,
    SolverEvidenceKind,
)

# A real task completion requires TaskCompleteTicks (72) of standing at the site.
# We credit a watched completion only if we observed most of that dwell — slack
# for sampling jitter and the event log's merge grace.
TASK_COMPLETE_TICKS = 72
WATCHED_DWELL_MIN_TICKS = 56
# The dwell interval must still be "live" at the decrement tick (within the event
# log's merge grace) to be the completing dwell.
DWELL_END_GRACE_TICKS = 4

# Offline-mirrored stance heuristics (features.py ACCUSE_HINT / DEFEND_HINT).
ACCUSE_HINT = re.compile(r"\bsus\b|\bvote\b|\bsaw (?:them|him|her|it)\b", re.IGNORECASE)
DEFEND_HINT = re.compile(r"\bclear(?:ed)?\b|\bsafe\b|\binnocent\b|\bnot sus\b|\bwasn'?t\b", re.IGNORECASE)
SOLVER_ACCUSE_HINT = re.compile(
    r"\bsus(?:picious)?\b|\bvote\b|\bimp(?:oster|ostor)?\b|\bvent(?:ed|ing|s)?\b|"
    r"\bkill(?:ed|ing|s)?\b|\bfak(?:e|ed|ing)\b|\b(?:lie|lied|lying)\b|"
    r"\bfollow(?:ed|ing)?\b|\bsaw\b",
    re.IGNORECASE,
)
CLAUSE_SPLIT = re.compile(r"[,.;!?]|\bbut\b", re.IGNORECASE)
DISJUNCTION_HINT = re.compile(r"\beither\b|\bor\b|\bone of\b", re.IGNORECASE)

SKIP_VOTE_TARGET = -2  # perception.entities.VoteDot sentinel


def update_social_evidence(belief: Belief) -> None:
    """Fold this tick's public/social observations into the roster counters.

    Runs in the fast loop after ``update_event_log`` (it reads the task-dwell
    intervals that logger maintains) and before ``update_suspicion``.
    """

    _record_solver_claims(belief)
    _track_solver_meeting(belief)
    _count_chat_stances(belief)
    _track_meeting_votes(belief)
    _bank_meeting_caller(belief)
    _detect_watched_completions(belief)


# --- chat stances -------------------------------------------------------------


def _color_pattern(belief: Belief) -> re.Pattern | None:
    colors = [c for c in belief.roster if c]
    if not colors:
        return None
    alternation = "|".join(sorted((re.escape(c) for c in colors), key=len, reverse=True))
    return re.compile(rf"\b({alternation})\b", re.IGNORECASE)


def parse_social_claims(
    event: ChatEvent,
    *,
    meeting_id: int,
    colors: set[str],
) -> list[SocialClaim]:
    """Extract conservative relational claims without depending on spaCy readiness."""

    if not colors or not event.text:
        return []
    canonical = {color.lower(): color for color in colors}
    alternation = "|".join(
        sorted((re.escape(color) for color in canonical), key=len, reverse=True)
    )
    color_pattern = re.compile(rf"\b({alternation})\b", re.IGNORECASE)
    claims: list[SocialClaim] = []
    for raw_clause in CLAUSE_SPLIT.split(event.text):
        clause = raw_clause.strip()
        if not clause:
            continue
        named = []
        for match in color_pattern.finditer(clause):
            color = canonical[match.group(1).lower()]
            if color != event.speaker_color and color not in named:
                named.append(color)
        if not named:
            continue

        defended = [color for color in named if _target_defended(clause, color)]
        for target in defended:
            claims.append(
                _claim(event, meeting_id, (target,), "defend", _evidence_kind(clause))
            )

        accused = [
            color
            for color in named
            if color not in defended and not _target_is_victim(clause, color)
        ]
        if not accused or not SOLVER_ACCUSE_HINT.search(clause):
            continue
        if len(accused) > 1 and DISJUNCTION_HINT.search(clause):
            claims.append(
                _claim(
                    event,
                    meeting_id,
                    tuple(sorted(accused)),
                    "at_least_one",
                    _evidence_kind(clause),
                )
            )
        else:
            claims.extend(
                _claim(event, meeting_id, (target,), "accuse", _evidence_kind(clause))
                for target in accused
            )
    return claims


def _claim(
    event: ChatEvent,
    meeting_id: int,
    targets: tuple[str, ...],
    stance: SolverClaimStance,
    evidence_kind: SolverEvidenceKind,
) -> SocialClaim:
    return SocialClaim(
        meeting_id=meeting_id,
        tick=event.tick,
        speaker_color=event.speaker_color,
        targets=targets,
        stance=stance,
        evidence_kind=evidence_kind,
        text=event.text,
    )


def _target_defended(clause: str, color: str) -> bool:
    escaped = re.escape(color)
    return bool(
        re.search(
            rf"\b{escaped}\b.{{0,20}}\b(?:clear(?:ed)?|safe|innocent|not sus|wasn'?t|with me|was with)\b|"
            rf"\b(?:vouch|trust|with|not)\b.{{0,20}}\b{escaped}\b",
            clause,
            re.IGNORECASE,
        )
    )


def _target_is_victim(clause: str, color: str) -> bool:
    escaped = re.escape(color)
    return bool(
        re.search(
            rf"\b{escaped}\b.{{0,8}}\b(?:died|dead)\b|"
            rf"\b(?:kill(?:ed)?|body of)\b.{{0,8}}\b{escaped}\b",
            clause,
            re.IGNORECASE,
        )
    )


def _evidence_kind(clause: str) -> SolverEvidenceKind:
    lowered = clause.lower()
    if "vent" in lowered:
        return "vent"
    if re.search(r"\b(?:kill|killed|dead|died|body|report)\b", lowered):
        return "body"
    if re.search(r"\b(?:saw|follow|following|followed)\b", lowered):
        return "sighting"
    if re.search(r"\bvote\b", lowered):
        return "vote"
    return "bare"


def _record_solver_claims(belief: Belief) -> None:
    colors = set(belief.roster)
    meeting_id = belief.phase_start_tick
    if belief.phase != "Voting" and belief.meeting_history:
        meeting_id = belief.meeting_history[-1].meeting_id
    for event in belief.chat_log:
        key = (event.tick, event.speaker_color, event.text)
        if key in belief.solver_counted_chats:
            continue
        belief.solver_counted_chats.add(key)
        belief.social_claims.extend(
            parse_social_claims(event, meeting_id=meeting_id, colors=colors)
        )


def _count_chat_stances(belief: Belief) -> None:
    if not belief.chat_log:
        return
    pattern = _color_pattern(belief)
    if pattern is None:
        return
    for event in belief.chat_log:
        key = (event.tick, event.speaker_color, event.text)
        if key in belief.social_counted_chats:
            continue
        belief.social_counted_chats.add(key)
        named = [m.group(1).lower() for m in pattern.finditer(event.text or "")]
        named = [c for c in named if c != event.speaker_color]
        if not named:
            continue
        if DEFEND_HINT.search(event.text):
            stance = "defends"
        elif ACCUSE_HINT.search(event.text):
            stance = "accuses"
        else:
            continue
        target = belief.roster.get(named[0])
        speaker = belief.roster.get(event.speaker_color)
        if stance == "accuses":
            if speaker is not None:
                speaker.accusations_made += 1
            if target is not None:
                target.times_accused += 1
        elif target is not None:
            target.times_defended += 1


# --- vote tallies ---------------------------------------------------------------


def _track_solver_meeting(belief: Belief) -> None:
    """Upsert the current meeting's public metadata and latest attributed tally."""

    if belief.phase != "Voting":
        return
    meeting_id = belief.phase_start_tick
    meeting = next(
        (record for record in reversed(belief.meeting_history) if record.meeting_id == meeting_id),
        None,
    )
    if meeting is None:
        meeting = MeetingRecord(
            meeting_id=meeting_id,
            caller_color=belief.meeting_caller_color,
            call_kind=belief.meeting_call_kind,
        )
        belief.meeting_history.append(meeting)
    else:
        meeting.caller_color = meeting.caller_color or belief.meeting_caller_color
        meeting.call_kind = meeting.call_kind or belief.meeting_call_kind

    slots = {candidate.slot: candidate.color for candidate in belief.voting.candidates}
    if slots and belief.voting.dots:
        meeting.votes = {
            slots[vote.voter]: None if vote.target == SKIP_VOTE_TARGET else slots.get(vote.target)
            for vote in belief.voting.dots
            if vote.voter in slots
        }


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


# --- watched real-task completion -------------------------------------------------


def _detect_watched_completions(belief: Belief) -> None:
    remaining = belief.crew_tasks_remaining
    prev = belief.social_prev_tasks_remaining
    belief.social_prev_tasks_remaining = remaining
    if remaining is None or prev is None:
        return
    if remaining != prev - 1:
        return  # no decrement, or an ambiguous multi-completion tick

    tick = belief.last_tick
    candidates = []
    for color, record in belief.roster.items():
        if color == belief.self_color or record.life_status == "dead":
            continue
        if record.last_seen_tick != tick:
            continue  # must be watching them right now
        for event in reversed(record.events):
            if event.kind != "task":
                continue
            if tick - event.end_tick <= DWELL_END_GRACE_TICKS and event.duration_ticks >= WATCHED_DWELL_MIN_TICKS:
                candidates.append(record)
            break  # only the most recent task dwell can be the completing one
    if len(candidates) == 1:
        candidates[0].tasks_completed_watched += 1
