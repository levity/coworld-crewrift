"""Experiment #1: break near-ties among the candidates the posterior already isolated.

WHY THIS QUESTION AND NOT "WHO ARE THE IMPOSTORS". Measured over 500 v29 league meetings:
when the posterior's argmax is wrong, the true impostor is rank-2 62.8% of the time and
inside the top three 87% of the time. So the model is not being asked to find a suspect --
it is being asked to reorder a list that already contains the answer ~87% of the time.
That ceiling is what makes the task well-posed: a wrong pick is a wrong pick among three
named players with the transcript in hand, not a hallucination out of ten.

WHERE THE GAIN WOULD COME FROM. 259 of those 500 meetings have a top marginal in the
0.35-0.65 band, and inside that band the argmax is right 50.2% -- a coin flip. Above and
below it the posterior is already good and should be left alone. So this consult
deliberately declines to ask when the board is not contested (`min_p`/`max_p`), which
also means most meetings cost no tokens and no latency.

WHAT IT MAY NOT DO. It may not introduce a target the solver never considered, and it may
not turn a skip into an eject unless `allow_promote` is on. Those are separate hypotheses
about what the LLM is for, and bundling them in would make the A/B unreadable.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from crewborg.deduction.consult.base import SKIP, BaseConsult, ConsultOutcome
from crewborg.deduction.consult.view import ConsultView

CHAT_MAX_CHARS = 160


class ShortlistResponse(BaseModel):
    """The only shape the model may answer in.

    `pick` is ALWAYS a best guess and may never be `skip`. That is a correction from the
    first pilot, where 18 of 20 answers were `pick="skip", confidence=0.5`: offering skip
    as a pick asks the model to decide WHETHER to act, which is `apply`'s job, and on a
    board selected for being a coin flip the honest answer to that question is always
    "don't". Splitting the two -- the model reports a belief, the caller sets the bar --
    also means one paid run yields the whole `min_confidence` sweep offline, because
    re-thresholding a recorded confidence costs nothing.

    `evidence` must quote the transcript or the structural facts. Not decoration: an
    unfalsifiable pick and a well-grounded one are indistinguishable from the vote alone,
    and scoring needs to separate "right for a reason" from "right by luck".
    """

    model_config = ConfigDict(extra="forbid")

    pick: str = Field(description="the most likely impostor among the shortlisted colors")
    confidence: float = Field(ge=0.0, le=1.0, description="P(pick is an impostor)")
    evidence: list[str] = Field(default_factory=list, max_length=4)
    reason: str = ""
    chat: str | None = Field(default=None, max_length=CHAT_MAX_CHARS)


class ShortlistConsult(BaseConsult):
    name = "shortlist"
    Response = ShortlistResponse
    defaults: ClassVar[dict[str, Any]] = {
        # How many candidates go on the shortlist. 3 covers 87% of the recoverable cases;
        # widening it trades that ceiling against a harder choice.
        "k": 3,
        # Only consult inside the contested band -- outside it the posterior is already
        # right often enough that a departure is expected to lose.
        "min_p": 0.35,
        "max_p": 0.65,
        # Below this the model's own stated uncertainty is treated as no answer.
        #
        # 0.7 rather than 0.6, and the difference is the whole experiment. Measured over
        # 259 contested v29 meetings with haiku-4-5, the model's confidence is not a
        # gradient -- it is a detector. Everything it reports at or below ~0.6 lands at
        # 41-55% correct, indistinguishable from the 50.2% argmax that needs no LLM at
        # all; at 0.7+ it lands at 87-94%. There is no useful middle.
        #
        # Weighted by this codebase's OWN break-even for ejecting (`base_probability`
        # 0.65, so a wrong eject costs 0.65 where a right one gains 0.35), the bands
        # score:  >=0.5 -31.5,  >=0.6 -6.2,  >=0.7 +2.6. Only the top band pays, and it
        # fires on ~7% of contested meetings. A 0.6 gate buys volume at a quality below
        # the bar the solver already refuses to cross, which is not a bargain.
        #
        # The 0.7 band held at 17/18 and 14/16 across a substantial prompt rewrite,
        # which is the reason to believe it at all -- but n=18 is n=18. Its Wilson
        # interval is roughly 65-97%, so this is a signal to size up, not a result.
        "min_confidence": 0.7,
        # May a `skip` become an eject?
        #
        # This started as False on the reasoning that the experiment is about WHICH and
        # not WHETHER. That reasoning does not survive the data. Measured over the 500
        # v29 meetings (`crewrift-analysis/consult_score.py --dry-run`): inside the
        # contested band the solver votes in 15 of 259 meetings -- 5.8%. With promotion
        # off there are 15 meetings in which this consult can possibly do anything, so
        # the arm would be a no-op that still costs a submission.
        #
        # BE CLEAR ABOUT WHAT TURNING IT ON IS. It is a coverage bet, and coverage bets
        # in this codebase have failed before: the 2026-07-27 vote-gate sweep lowered the
        # threshold and precision collapsed. The difference is the mechanism -- that
        # swept a scalar on the fitted posterior, this substitutes judgment on a board
        # where the argmax is 50.2% and an impostor is on the shortlist 93.4% of the
        # time. It is a real question, not a settled one, which is why it is a parameter
        # and why the offline paired score has to clear the 50.2% bar before it ships.
        "allow_promote": True,
    }

    def applies(self, view: ConsultView) -> str | None:
        """Return a reason to skip the call, or None to proceed."""

        ranked = view.ranked
        if len(ranked) < 2:
            return "fewer than two live candidates"
        top = ranked[0]
        if top.pinned:
            return "top candidate is structurally pinned"
        if not (self.param("min_p") <= top.p <= self.param("max_p")):
            return f"top marginal {top.p:.2f} outside contested band"
        return None

    def payload(self, view: ConsultView) -> dict[str, Any]:
        shortlist = [c for c in view.top(int(self.param("k"))) if not c.murder_cleared]
        names = {c.color for c in shortlist}
        return {
            "task": "pick_impostor_from_shortlist",
            "you_are": view.self_color,
            "your_role": view.self_role,
            # The whole game in order, across every meeting -- not just this meeting's
            # chat. An accusation means something different on its third repetition, or
            # coming from someone who voted the opposite way last round, and none of that
            # is visible in a single meeting's transcript.
            "game_log": view.game_log(),
            "shortlist": [c.to_json() for c in shortlist],
            "joint_hypotheses": [
                {"imposters": list(pair), "p": round(p, 4)}
                for pair, p in view.joint_hypotheses
                if names & set(pair)
            ],
            "solver_conclusion": dict(view.deterministic),
            "solver_would_vote": view.deterministic_vote,
            "allowed_picks": sorted(names),
        }

    def apply(self, response: BaseModel, view: ConsultView) -> ConsultOutcome:
        assert isinstance(response, ShortlistResponse)
        shortlist = {c.color for c in view.top(int(self.param("k")))}
        pick = (response.pick or "").strip().lower()
        deterministic = view.deterministic_vote

        def keep(why: str) -> ConsultOutcome:
            return ConsultOutcome(
                vote=deterministic,
                chat=None,
                followed_llm=False,
                fields={"declined": why, "pick": pick, "confidence": response.confidence},
            )

        if pick not in shortlist:
            return keep("pick_off_shortlist")
        if not view.is_legal(pick):
            return keep("pick_not_a_legal_target")
        if response.confidence < float(self.param("min_confidence")):
            return keep("below_min_confidence")
        if deterministic == SKIP and not self.param("allow_promote"):
            return keep("would_promote_skip_to_eject")

        return ConsultOutcome(
            vote=pick,
            chat=(response.chat or None),
            followed_llm=True,
            fields={
                "pick": pick,
                "confidence": response.confidence,
                "evidence": response.evidence[:4],
                "reason": response.reason[:200],
                "departure": _departure(deterministic, pick),
            },
        )


def _departure(deterministic: str, pick: str) -> str:
    if deterministic == pick:
        return "agreed"
    if deterministic == SKIP:
        return "skip_to_eject"
    if pick == SKIP:
        return "eject_to_skip"
    return "retarget"
