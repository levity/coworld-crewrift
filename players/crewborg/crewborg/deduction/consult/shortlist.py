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

from pydantic import BaseModel, ConfigDict, Field, field_validator

from crewborg.deduction.consult.base import SKIP, BaseConsult, ConsultOutcome
from crewborg.deduction.consult.view import Candidate, ConsultView

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

    @field_validator("chat", mode="before")
    @classmethod
    def _clip_chat(cls, value: Any) -> Any:
        """TRUNCATE an over-long chat line; never reject the answer over it.

        `chat` is flavour -- one line the crewmate says before voting. `pick` and
        `confidence` are the decision. Enforcing the length as a hard schema bound meant a
        model that wrote 170 characters had its entire impostor call thrown away, and
        `run_consult`'s never-raises contract turned that into a silent fallback to the
        solver. Measured over 2,147 real meetings on 2026-08-01: 503 (23%) were lost this
        way, and the rate rose with board difficulty -- 59% in the low-posterior buckets,
        where a hedged answer runs long and where we most needed the data. Losing the
        hardest cases preferentially is the worst possible way to lose a quarter of them.

        The prompt still asks for <=160 (memory/shortlist.md), and the schema still
        advertises maxLength; this only decides what to do when the model ignores both.
        """

        if isinstance(value, str) and len(value) > CHAT_MAX_CHARS:
            return value[:CHAT_MAX_CHARS]
        return value


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
        # Withhold the solver's answer entirely -- see `payload`. Off by default because
        # the shipped consult is meant to REORDER the solver's list, which needs the list.
        # On, it measures whether the model has any independent signal, which is a
        # question the sighted arm structurally cannot answer.
        "blind": False,
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

    def candidates(self, view: ConsultView) -> tuple[Candidate, ...]:
        """The shortlist, in ONE place because `payload` and `apply` must not disagree.

        They did once -- `payload` dropped `murder_cleared` inline and `apply` did not, so
        a model naming a player it was never offered was admitted. Any future filter goes
        here for the same reason.

        DO NOT ADD A `max_gap` THAT PRUNES BY MARGINAL. It was tried on 2026-08-01 and is
        a nonstarter. Dropping candidates more than 0.15 behind the leader removes a
        genuine decoy on 36% of boards, but it also DESTROYS THE ONLY IMPOSTOR on 183 of
        2,183 addressed meetings (8.4%): the impostor is pruned and no survivor is one, so
        the meeting is unwinnable by construction and every answer on it is wrong.

        The deeper objection is that it prunes by the solver's own `p` -- inside an
        experiment whose whole purpose is to test whether that `p` can be trusted on these
        boards. Trusting the ranking to decide who deserves consideration bakes the
        solver's error into the question, and the consult exists to SUPPORT the solver,
        not to propagate its mistakes. A decoy makes the task harder; pruning makes it
        impossible. Harder is acceptable, impossible is not.
        """

        return view.top(int(self.param("k")))

    def payload(self, view: ConsultView) -> dict[str, Any]:
        shortlist = self.candidates(view)
        names = {c.color for c in shortlist}
        if self.param("blind"):
            # THE SOLVER'S ANSWER IS DISCLOSED FIVE WAYS, so blinding must remove all of
            # them. Deleting `solver_would_vote` alone changes nothing: `shortlist` is
            # rank-ordered AND prints `p`, `solver_conclusion` restates the target and its
            # probability, and `joint_hypotheses` is p-ordered with the argmax first. A
            # model that names element zero reproduces the solver exactly.
            #
            # This is the arm that answers whether the model contributes anything at all.
            # Measured sighted (2026-08-01, 2147 meetings): 92-100% agreement, 20
            # discordant pairs in 597, McNemar p=1.000 -- i.e. the output was a function
            # of an input we left in the payload, and no prompt change is measurable until
            # that channel is cut. Alphabetical order, no probabilities, no solver.
            candidates = sorted(names)
            return {
                "task": "pick_impostor_from_shortlist",
                "you_are": view.self_color,
                "your_role": view.self_role,
                "game_log": view.game_log(),
                "allowed_picks": candidates,
            }
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
        shortlist = {c.color for c in self.candidates(view)}
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
