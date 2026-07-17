"""Persistent meeting-ledger and joint social-deduction solver tests."""

from __future__ import annotations

from crewborg.perception.entities import VoteCandidate, VoteDot, VotingState
from crewborg.strategy.meeting.solver import SolverConfig, solve_hypotheses, solver_report
from crewborg.strategy.social_evidence import parse_social_claims, update_social_evidence
from crewborg.types import Belief, ChatEvent, MeetingRecord, PlayerRecord, SocialClaim


def _claim(
    meeting_id: int,
    speaker: str,
    targets: tuple[str, ...],
    *,
    stance: str = "accuse",
    evidence: str = "body",
    tick: int | None = None,
) -> SocialClaim:
    return SocialClaim(
        meeting_id=meeting_id,
        tick=meeting_id if tick is None else tick,
        speaker_color=speaker,
        targets=targets,
        stance=stance,
        evidence_kind=evidence,
        text="test claim",
    )


def test_parser_preserves_compound_stances_and_disjunctions() -> None:
    event = ChatEvent(
        tick=40,
        speaker_color="green",
        text="red is clear, either blue or yellow is imposter",
    )

    claims = parse_social_claims(
        event,
        meeting_id=10,
        colors={"red", "blue", "green", "yellow"},
    )

    assert [(claim.stance, claim.targets) for claim in claims] == [
        ("defend", ("red",)),
        ("at_least_one", ("blue", "yellow")),
    ]


def test_parser_does_not_accuse_the_named_kill_victim() -> None:
    event = ChatEvent(tick=40, speaker_color="green", text="i saw blue kill red")

    claims = parse_social_claims(
        event,
        meeting_id=10,
        colors={"red", "blue", "green"},
    )

    assert [(claim.stance, claim.targets) for claim in claims] == [("accuse", ("blue",))]


def test_parser_handles_with_me_and_ignores_neutral_body_report() -> None:
    defense = ChatEvent(tick=40, speaker_color="green", text="red was with me")
    report = ChatEvent(tick=41, speaker_color="green", text="blue reported the body")
    colors = {"red", "blue", "green"}

    assert [
        (claim.stance, claim.targets)
        for claim in parse_social_claims(defense, meeting_id=10, colors=colors)
    ] == [("defend", ("red",))]
    assert parse_social_claims(report, meeting_id=10, colors=colors) == []


def test_claims_and_vote_records_persist_across_meetings() -> None:
    belief = Belief(phase="Voting", phase_start_tick=10, self_color="red")
    for color in ("red", "blue", "green"):
        belief.roster[color] = PlayerRecord(color=color, life_status="alive")
    belief.chat_log = [ChatEvent(tick=12, speaker_color="blue", text="green sus")]
    belief.voting = VotingState(
        candidates=(
            VoteCandidate(slot=0, color="red", alive=True),
            VoteCandidate(slot=1, color="blue", alive=True),
            VoteCandidate(slot=2, color="green", alive=True),
        ),
        dots=(VoteDot(voter=1, target=2),),
    )

    update_social_evidence(belief)
    update_social_evidence(belief)
    belief.phase_start_tick = 100
    belief.chat_log = [ChatEvent(tick=102, speaker_color="blue", text="green sus again")]
    update_social_evidence(belief)

    assert len(belief.social_claims) == 2
    assert [claim.meeting_id for claim in belief.social_claims] == [10, 100]
    assert [meeting.meeting_id for meeting in belief.meeting_history] == [10, 100]
    assert belief.meeting_history[0].votes == {"blue": "green"}


def test_late_rendered_vote_result_chat_keeps_the_meeting_id() -> None:
    belief = Belief(
        phase="VoteResult",
        phase_start_tick=50,
        meeting_history=[MeetingRecord(meeting_id=10)],
    )
    for color in ("blue", "green"):
        belief.roster[color] = PlayerRecord(color=color, life_status="alive")
    belief.chat_log = [ChatEvent(tick=49, speaker_color="blue", text="green sus")]

    update_social_evidence(belief)

    assert belief.social_claims[0].meeting_id == 10


def test_solver_deduplicates_pairs_within_meeting_but_aggregates_later_meetings() -> None:
    players = ["red", "blue", "green", "yellow"]
    claims = [
        _claim(10, "green", ("red",), tick=11),
        _claim(10, "green", ("red",), evidence="vent", tick=12),
        _claim(20, "green", ("red",), tick=21),
    ]

    result = solve_hypotheses(
        players,
        2,
        claims,
        config=SolverConfig(prior_strength=0.0),
    )

    assert result["n_claims"] == 2
    assert result["marginals"]["red"] > result["marginals"]["blue"]


def test_suspected_speaker_claim_is_interpreted_as_deflection() -> None:
    players = ["red", "blue", "green", "yellow"]
    claims = [_claim(10, "red", ("blue",))]
    config = SolverConfig(prior_strength=1.0)

    trusted = solve_hypotheses(
        players,
        2,
        claims,
        priors={"red": 0.05},
        config=config,
    )
    suspected = solve_hypotheses(
        players,
        2,
        claims,
        priors={"red": 0.95},
        config=config,
    )

    assert suspected["marginals"]["red"] > trusted["marginals"]["red"]
    assert suspected["marginals"]["blue"] < trusted["marginals"]["blue"]


def test_solver_combines_disjunction_and_later_claim_into_decisive_constraint() -> None:
    players = ["red", "blue", "green", "yellow", "pink", "orange"]
    claims = [
        _claim(10, "green", ("red", "blue"), stance="at_least_one"),
        _claim(20, "yellow", ("red",)),
        _claim(30, "pink", ("red",)),
        _claim(40, "orange", ("red",)),
    ]

    result = solve_hypotheses(
        players,
        2,
        claims,
        config=SolverConfig(prior_strength=0.0, repeat_decay=1.0),
    )

    assert result["marginals"]["red"] > 0.8
    assert result["hypotheses"][0]["imposters"] == ["blue", "red"]


def test_report_keeps_dead_players_in_global_hypotheses(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_SOLVER", "1")
    belief = Belief(
        self_role="crewmate",
        self_color="white",
        total_player_count=6,
        imposter_count=2,
    )
    for color in ("white", "red", "blue", "green", "yellow", "pink"):
        belief.roster[color] = PlayerRecord(
            color=color,
            life_status="dead" if color == "red" else "alive",
        )
    belief.suspicion = {color: 0.4 for color in ("blue", "green", "yellow", "pink")}
    belief.social_claims = [
        _claim(10, "green", ("red",)),
        _claim(20, "yellow", ("blue",)),
        _claim(30, "pink", ("red",)),
    ]

    report = solver_report(belief)

    assert "red" in report["marginals"]
    assert any("red" in hypothesis["imposters"] for hypothesis in report["hypotheses"])


def test_report_does_not_pick_from_a_symmetric_three_way_field(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_SOLVER", "1")
    belief = Belief(
        self_role="crewmate",
        self_color="white",
        total_player_count=4,
        imposter_count=2,
    )
    for color in ("white", "red", "blue", "green"):
        belief.roster[color] = PlayerRecord(color=color, life_status="alive")
    belief.social_claims = [
        _claim(10, "red", ("blue",)),
        _claim(10, "blue", ("green",)),
        _claim(10, "green", ("red",)),
    ]

    report = solver_report(belief)

    assert set(report["marginals"].values()) == {0.667}
    assert report["pick"] is None


def test_public_votes_from_trusted_speakers_are_weaker_relational_evidence() -> None:
    players = ["red", "blue", "green", "yellow"]
    meetings = [MeetingRecord(meeting_id=10, votes={"green": "red", "yellow": "red"})]

    result = solve_hypotheses(
        players,
        2,
        [],
        meetings,
        priors={"green": 0.05, "yellow": 0.05},
        config=SolverConfig(prior_strength=1.0),
    )

    assert result["n_votes"] == 2
    assert result["marginals"]["red"] > result["marginals"]["green"]
    assert result["marginals"]["red"] > result["marginals"]["yellow"]
