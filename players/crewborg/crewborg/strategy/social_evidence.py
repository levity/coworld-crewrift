"""Social evidence: cumulative meeting-public counters.

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
Counters are cumulative for the whole episode (evidence never resets at meetings)
and live on ``PlayerRecord``; ``suspicion._fitted_features`` reads them.
"""

from __future__ import annotations

import re

from crewborg.types import (
    Belief,
    ChatEvent,
    SocialClaim,
    SolverClaimProvenance,
    SolverClaimStance,
    SolverEvidenceKind,
)

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
DIRECT_OBSERVATION_CUE = re.compile(
    r"\b(?:sus(?:picious)?|vent(?:ed|ing|s)?|kill(?:ed|ing|s)?|body|"
    r"follow(?:ed|ing|s)?|tail(?:ed|ing|s)?|fak(?:e|ed|ing)|lie|lied|lying)\b",
    re.IGNORECASE,
)
# NOTE the `?` on the kill suffix. It used to be `kill(?:ed|ing|s)`, requiring an
# inflection, which combined with `direct_observation_pattern`'s mandatory "i|we"
# subject to drop the SUBJECT-DROPPED BARE INFINITIVE entirely: "saw pink kill
# orange" matched no branch and parsed to nothing. Measured over 115 league
# episodes that is the single largest parser-gap template, and a witnessed kill is
# the strongest evidence the solver can get. Every other inflection already worked
# ("pink killed orange", "pink kills orange", "I saw pink kill orange"), which is
# why it stayed invisible. The victim stays excluded via `_target_is_victim`, whose
# own pattern already spells the verb `kill(?:ed)?`.
ACCUSE_PREDICATE = (
    r"sus(?:picious)?|imposter|impostor|threat|lying|liar|deflecting|"
    r"vent(?:ed|ing|s)?|kill(?:ed|ing|s)?|fak(?:e|ed|ing)|"
    r"follow(?:ed|ing|s)?|tail(?:ed|ing|s)?"
)
SOURCE_TARGET_VERB = (
    r"saw|sus(?:pect(?:s|ed|ing)?)?|accus(?:e[sd]?|ed|ing)|"
    r"(?:is\s+)?push(?:es|ed|ing)|call(?:s|ed|ing)|vot(?:e[sd]?|ed|ing)"
)
EVIDENCE_STRENGTH: dict[SolverEvidenceKind, int] = {
    "bare": 0,
    "vote": 1,
    "sighting": 2,
    "body": 3,
    "vent": 4,
}

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
    """Extract predicate-aware relational claims without depending on spaCy.

    Colors are a closed vocabulary, but their grammatical role still matters:
    in ``Yellow saw cyan vent``, yellow is the attributed source and cyan is the
    target. Ambiguous color mentions are omitted rather than guessed.
    """

    if not colors or not event.text:
        return []
    canonical = {color.lower(): color for color in colors}
    alternation = "|".join(
        sorted((re.escape(color) for color in canonical), key=len, reverse=True)
    )
    color_token = rf"(?:{alternation})"
    color_pattern = re.compile(rf"\b({alternation})\b", re.IGNORECASE)
    source_target_pattern = re.compile(
        rf"(?P<sources>\b{color_token}\b"
        rf"(?:\s*(?:,|and)\s*\b{color_token}\b)*)"
        rf"\s+(?:(?:also|both)\s+)?(?:{SOURCE_TARGET_VERB})\s+"
        rf"(?P<target>{color_token})\b",
        re.IGNORECASE,
    )
    source_pronoun_pattern = re.compile(
        rf"\b(?P<source>{color_token})\b\s+"
        rf"(?:(?:also|both)\s+)?"
        rf"(?:sus(?:pect(?:s|ed|ing)?)?|accus(?:e[sd]?|ed|ing)|"
        rf"(?:is\s+)?push(?:es|ed|ing))\s+me\b",
        re.IGNORECASE,
    )
    direct_observation_pattern = re.compile(
        rf"\b(?:i|we)\s+(?:also\s+)?saw\s+(?P<target>{color_token})\b"
        rf"(?P<detail>.{{0,64}})",
        re.IGNORECASE,
    )
    accused_subject_pattern = re.compile(
        rf"\b(?P<target>{color_token})\b\s+"
        rf"(?:(?:is|looks?|seems?|was|were|keeps?)\s+)?"
        rf"(?:(?:the|most|clear|strongest|confirmed)\s+)*"
        rf"(?:{ACCUSE_PREDICATE})\b",
        re.IGNORECASE,
    )
    vote_target_pattern = re.compile(
        rf"\b(?:vote|voting)\s+(?:for\s+)?(?P<target>{color_token})\b",
        re.IGNORECASE,
    )
    crowd_target_pattern = re.compile(
        rf"\b(?:multiple|several|two|three|\d+)\s+players?\s+"
        rf"(?:sus(?:pect)?|flag(?:ged)?|vot(?:e|ed|ing))\s+"
        rf"(?P<target>{color_token})\b",
        re.IGNORECASE,
    )
    attributed_overrides = _pronoun_attributions(
        event.text,
        canonical=canonical,
        color_token=color_token,
    )
    claims: dict[tuple[str | None, tuple[str, ...], SolverClaimStance], SocialClaim] = {}

    def add_claim(
        *,
        source: str | None,
        targets: tuple[str, ...],
        stance: SolverClaimStance,
        clause: str,
        provenance: SolverClaimProvenance,
    ) -> None:
        targets = tuple(dict.fromkeys(targets))
        if not targets or source in targets:
            return
        evidence_kind = _evidence_kind(clause)
        claim = _claim(
            event,
            meeting_id,
            targets,
            stance,
            evidence_kind,
            source_color=source,
            provenance=provenance,
        )
        key = (source, targets, stance)
        previous = claims.get(key)
        if previous is None or EVIDENCE_STRENGTH[evidence_kind] > EVIDENCE_STRENGTH[
            previous.evidence_kind
        ]:
            claims[key] = claim

    for raw_clause in CLAUSE_SPLIT.split(event.text):
        clause = raw_clause.strip()
        if not clause:
            continue
        named: list[str] = []
        for match in color_pattern.finditer(clause):
            color = canonical[match.group(1).lower()]
            if color not in named:
                named.append(color)
        if not named:
            continue

        defended = [color for color in named if _target_defended(clause, color)]
        for target in defended:
            add_claim(
                source=event.speaker_color,
                targets=(target,),
                stance="defend",
                clause=clause,
                provenance="direct",
            )

        eligible = [
            color for color in named if color not in defended and not _target_is_victim(clause, color)
        ]
        if len(eligible) > 1 and DISJUNCTION_HINT.search(clause) and SOLVER_ACCUSE_HINT.search(
            clause
        ):
            add_claim(
                source=event.speaker_color,
                targets=tuple(sorted(eligible)),
                stance="at_least_one",
                clause=clause,
                provenance="direct",
            )
            continue

        attributed_sources: set[str] = set()
        attributed_targets: set[str] = set()
        for match in source_pronoun_pattern.finditer(clause):
            source = canonical[match.group("source").lower()]
            attributed_sources.add(source)
            if event.speaker_color is not None:
                add_claim(
                    source=source,
                    targets=(event.speaker_color,),
                    stance="accuse",
                    clause=clause,
                    provenance="direct" if source == event.speaker_color else "relayed",
                )

        for match in source_target_pattern.finditer(clause):
            target = canonical[match.group("target").lower()]
            if target in defended or _target_is_victim(clause, target):
                continue
            attributed_targets.add(target)
            for source_match in color_pattern.finditer(match.group("sources")):
                source = canonical[source_match.group(1).lower()]
                attributed_sources.add(source)
                add_claim(
                    source=source,
                    targets=(target,),
                    stance="accuse",
                    clause=clause,
                    provenance="direct" if source == event.speaker_color else "relayed",
                )

        for match in direct_observation_pattern.finditer(clause):
            target = canonical[match.group("target").lower()]
            if (
                target in defended
                or _target_is_victim(clause, target)
                or not DIRECT_OBSERVATION_CUE.search(match.group("detail"))
            ):
                continue
            add_claim(
                source=event.speaker_color,
                targets=(target,),
                stance="accuse",
                clause=clause,
                provenance="direct",
            )

        for match in accused_subject_pattern.finditer(clause):
            target = canonical[match.group("target").lower()]
            if (
                target in attributed_sources
                or target in defended
                or _target_is_victim(clause, target)
            ):
                continue
            sources = attributed_overrides.get(target)
            if sources:
                for source in sources:
                    add_claim(
                        source=source,
                        targets=(target,),
                        stance="accuse",
                        clause=clause,
                        provenance="direct" if source == event.speaker_color else "relayed",
                    )
            else:
                add_claim(
                    source=event.speaker_color,
                    targets=(target,),
                    stance="accuse",
                    clause=clause,
                    provenance="direct",
                )

        for match in vote_target_pattern.finditer(clause):
            target = canonical[match.group("target").lower()]
            if (
                target not in attributed_targets
                and target not in defended
                and not _target_is_victim(clause, target)
            ):
                add_claim(
                    source=event.speaker_color,
                    targets=(target,),
                    stance="accuse",
                    clause=clause,
                    provenance="direct",
                )

        for match in crowd_target_pattern.finditer(clause):
            target = canonical[match.group("target").lower()]
            if target not in defended and not _target_is_victim(clause, target):
                add_claim(
                    source=event.speaker_color,
                    targets=(target,),
                    stance="accuse",
                    clause=clause,
                    provenance="relayed",
                )
    return list(claims.values())


def _claim(
    event: ChatEvent,
    meeting_id: int,
    targets: tuple[str, ...],
    stance: SolverClaimStance,
    evidence_kind: SolverEvidenceKind,
    *,
    source_color: str | None,
    provenance: SolverClaimProvenance,
) -> SocialClaim:
    return SocialClaim(
        meeting_id=meeting_id,
        tick=event.tick,
        speaker_color=event.speaker_color,
        source_color=source_color,
        provenance=provenance,
        targets=targets,
        stance=stance,
        evidence_kind=evidence_kind,
        text=event.text,
    )


def _pronoun_attributions(
    text: str,
    *,
    canonical: dict[str, str],
    color_token: str,
) -> dict[str, tuple[str, ...]]:
    """Resolve ``Red vented. Yellow saw it`` without treating yellow as a target."""

    pattern = re.compile(
        rf"\b(?P<target>{color_token})\b\s+"
        rf"(?:vent(?:ed|ing|s)?|kill(?:ed|ing|s)|fak(?:e|ed|ing))\b"
        rf"[^.!?]*[.!?]\s*"
        rf"(?P<source>{color_token})\b\s+(?:also\s+)?saw\s+it\b",
        re.IGNORECASE,
    )
    sources: dict[str, list[str]] = {}
    for match in pattern.finditer(text):
        target = canonical[match.group("target").lower()]
        source = canonical[match.group("source").lower()]
        if source != target and source not in sources.setdefault(target, []):
            sources[target].append(source)
    return {target: tuple(items) for target, items in sources.items()}


def _target_defended(clause: str, color: str) -> bool:
    escaped = re.escape(color)
    return bool(
        re.search(
            rf"\b{escaped}\b.{{0,16}}\b(?:clear(?:ed)?(?!\s+threat)|safe|innocent|"
            rf"not sus|wasn'?t|with me|looks credible|makes sense)\b|"
            rf"\b(?:vouch(?:ing)?\s+for|trust)\b.{{0,12}}\b{escaped}\b",
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
