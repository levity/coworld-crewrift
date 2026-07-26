"""Who is being accused in meeting chat — a projection over `strategy.claims`.

The imposter's reactive bandwagon (§10.4) wants to know which crewmates other
players are sussing, so it can pile on before that hardens into a vote. It needs
far less than the solver does: not who attributed what to whom, just how much heat
each color is taking.

So this file no longer parses anything. It used to carry its own spaCy extractor,
which drifted from the crew-side parser and grew its own bugs — most sharply, kill
reports were broken in both directions at once ("saw red kill green" accused the
victim; "red killed green" accused nobody, because both colors fell inside a
±2-token proximity window around "killed", so a witnessed kill produced no signal
at all). One parser now serves both roles; this is the imposter's view of it.
"""

from __future__ import annotations

from crewborg import nlp as chat_nlp
from crewborg.strategy.claims import parse_claims
from crewborg.types import Belief


def chat_accusers(belief: Belief, *, cache: dict[str, set[str]] | None = None) -> dict[str, int]:
    """Per non-teammate color, the count of *distinct other speakers* accusing them.

    Empty when the NLP model isn't available — the bandwagon then rests on the vote
    tally alone, which is the deliberate behaviour: a crude keyword fallback's false
    positives are exactly what the parser exists to avoid. `cache` is accepted for
    call-site compatibility and is unused; `strategy.claims` memoizes parses itself,
    which is what the per-meeting cache was for.
    """

    if chat_nlp.get_model() is None:
        return {}

    colors = set(belief.roster)
    self_color = belief.voting.self_marker_color

    by_color: dict[str, set[str | None]] = {}
    for event in belief.chat_log:
        if event.speaker_color is not None and event.speaker_color == self_color:
            continue  # our own chat isn't a signal to bandwagon on
        for claim in parse_claims(
            event.text,
            speaker_color=event.speaker_color,
            colors=colors,
            meeting_id=0,
            tick=event.tick,
        ):
            if claim.stance != "accuse":
                continue
            for target in claim.targets:
                # Credit the SPEAKER, not the attributed source: the bandwagon is
                # counting how many people are talking, not how many were cited.
                by_color.setdefault(target, set()).add(event.speaker_color)

    return {
        color: len(speakers)
        for color, speakers in by_color.items()
        if color not in belief.teammate_colors and color != self_color
    }
