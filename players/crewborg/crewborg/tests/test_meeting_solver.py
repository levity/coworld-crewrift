"""Persistent meeting-ledger and joint social-deduction solver tests."""

from __future__ import annotations

from crewborg.perception.entities import VoteCandidate, VoteDot, VotingState
from crewborg.strategy.meeting.solver import (
    SolverConfig,
    early_chat_pick,
    persistent_target_sources,
    public_solver_report,
    solve_hypotheses,
    solver_report,
)
from crewborg.strategy.social_evidence import (
    parse_social_claims,
    update_social_evidence,
)
from crewborg.types import (
    Belief,
    ChatEvent,
    MeetingRecord,
    PlayerEvent,
    PlayerRecord,
    SocialClaim,
)


def _claim(
    meeting_id: int,
    speaker: str,
    targets: tuple[str, ...],
    *,
    stance: str = "accuse",
    evidence: str = "body",
    tick: int | None = None,
    source: str | None = None,
    provenance: str = "direct",
) -> SocialClaim:
    return SocialClaim(
        meeting_id=meeting_id,
        tick=meeting_id if tick is None else tick,
        speaker_color=speaker,
        source_color=source,
        provenance=provenance,
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

    assert [(claim.stance, claim.targets) for claim in claims] == [
        ("accuse", ("blue",))
    ]


def test_parser_handles_with_me_and_ignores_neutral_body_report() -> None:
    defense = ChatEvent(tick=40, speaker_color="green", text="red was with me")
    report = ChatEvent(tick=41, speaker_color="green", text="blue reported the body")
    colors = {"red", "blue", "green"}

    assert [
        (claim.stance, claim.targets)
        for claim in parse_social_claims(defense, meeting_id=10, colors=colors)
    ] == [("defend", ("red",))]
    assert parse_social_claims(report, meeting_id=10, colors=colors) == []


def test_parser_separates_attributed_witness_from_accusation_target() -> None:
    event = ChatEvent(
        tick=40,
        speaker_color="purple",
        text="Yellow saw cyan at a vent. Red and yellow, where were you near green?",
    )

    claims = parse_social_claims(
        event,
        meeting_id=10,
        colors={"red", "green", "yellow", "cyan", "purple"},
    )

    assert [
        (claim.speaker_color, claim.source_color, claim.provenance, claim.targets)
        for claim in claims
    ] == [("purple", "yellow", "relayed", ("cyan",))]


def test_parser_resolves_saw_it_to_the_attributed_source() -> None:
    event = ChatEvent(
        tick=40,
        speaker_color="purple",
        text="Red vented. Yellow saw it. Red is the clear threat here.",
    )

    claims = parse_social_claims(
        event,
        meeting_id=10,
        colors={"red", "yellow", "purple"},
    )

    assert [
        (claim.source_color, claim.provenance, claim.targets, claim.evidence_kind)
        for claim in claims
    ] == [("yellow", "relayed", ("red",), "vent")]


def test_parser_ignores_dead_reporter_and_location_mentions() -> None:
    event = ChatEvent(
        tick=40,
        speaker_color="yellow",
        text=(
            "Orange is dead. Red reported. "
            "Cyan, pink, purple all near Bridge need to pin down movements."
        ),
    )

    assert (
        parse_social_claims(
            event,
            meeting_id=10,
            colors={"red", "orange", "yellow", "cyan", "pink", "purple"},
        )
        == []
    )


def test_parser_preserves_multiple_attributed_sources_for_one_target() -> None:
    event = ChatEvent(
        tick=40,
        speaker_color="purple",
        text="Red and yellow both called cyan out. Pink and yellow voting cyan.",
    )

    claims = parse_social_claims(
        event,
        meeting_id=10,
        colors={"red", "yellow", "pink", "cyan", "purple"},
    )

    assert {
        (claim.source_color, claim.provenance, claim.targets) for claim in claims
    } == {
        ("red", "relayed", ("cyan",)),
        ("yellow", "relayed", ("cyan",)),
        ("pink", "relayed", ("cyan",)),
    }


def test_parser_does_not_turn_accuser_into_target_in_compact_sus_syntax() -> None:
    event = ChatEvent(
        tick=40,
        speaker_color="purple",
        text="Yellow sus orange for venting. Who else saw orange near vents?",
    )

    claims = parse_social_claims(
        event,
        meeting_id=10,
        colors={"yellow", "orange", "purple"},
    )

    assert [
        (claim.source_color, claim.provenance, claim.targets) for claim in claims
    ] == [("yellow", "relayed", ("orange",))]


def test_parser_resolves_transitive_me_to_the_current_speaker() -> None:
    event = ChatEvent(
        tick=40,
        speaker_color="purple",
        text="Yellow sus me for following. Who was near pink?",
    )

    claims = parse_social_claims(
        event,
        meeting_id=10,
        colors={"yellow", "pink", "purple"},
    )

    assert [
        (claim.source_color, claim.provenance, claim.targets) for claim in claims
    ] == [("yellow", "relayed", ("purple",))]


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
    belief.chat_log = [
        ChatEvent(tick=102, speaker_color="blue", text="green sus again")
    ]
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


def test_solver_deduplicates_pairs_within_meeting_but_aggregates_later_meetings() -> (
    None
):
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


def test_solver_discounts_same_target_consensus_within_one_meeting() -> None:
    players = ["red", "blue", "green", "yellow", "pink"]
    same_meeting = [
        _claim(10, speaker, ("red",)) for speaker in ("green", "yellow", "pink")
    ]
    separate_meetings = [
        _claim(meeting, speaker, ("red",))
        for meeting, speaker in zip((10, 20, 30), ("green", "yellow", "pink"))
    ]
    config = SolverConfig(prior_strength=0.0, repeat_decay=1.0, same_target_decay=0.4)

    one = solve_hypotheses(
        players,
        2,
        [_claim(10, "green", ("red",))],
        config=config,
    )
    correlated = solve_hypotheses(players, 2, same_meeting, config=config)
    independent = solve_hypotheses(players, 2, separate_meetings, config=config)

    assert one["marginals"]["red"] < correlated["marginals"]["red"]
    assert correlated["marginals"]["red"] < independent["marginals"]["red"]


def test_solver_gives_full_consensus_weight_to_strongest_claim_regardless_of_order() -> (
    None
):
    players = ["red", "blue", "green", "yellow"]
    claims = [
        _claim(10, "green", ("red",), evidence="bare", tick=11),
        _claim(10, "yellow", ("red",), evidence="vent", tick=12),
    ]
    config = SolverConfig(prior_strength=0.0, same_target_decay=0.0)

    forward = solve_hypotheses(players, 2, claims, config=config)
    reversed_result = solve_hypotheses(
        players, 2, list(reversed(claims)), config=config
    )
    strongest_only = solve_hypotheses(players, 2, [claims[1]], config=config)

    assert forward["marginals"] == reversed_result["marginals"]
    assert forward["marginals"] == strongest_only["marginals"]


def test_solver_deduplicates_relays_by_attributed_source_and_discounts_them() -> None:
    players = ["red", "blue", "green", "yellow"]
    relays = [
        _claim(
            10,
            speaker,
            ("red",),
            source="green",
            provenance="relayed",
        )
        for speaker in ("blue", "yellow")
    ]

    relayed = solve_hypotheses(
        players,
        2,
        relays,
        config=SolverConfig(prior_strength=0.0),
    )
    direct = solve_hypotheses(
        players,
        2,
        [_claim(10, "green", ("red",), source="green")],
        config=SolverConfig(prior_strength=0.0),
    )

    assert relayed["n_claims"] == 1
    assert relayed["marginals"]["red"] < direct["marginals"]["red"]


def test_suspected_relaying_speaker_cannot_launder_trust_through_named_source() -> None:
    players = ["red", "blue", "green", "yellow"]
    claims = [
        _claim(
            10,
            "blue",
            ("red",),
            source="green",
            provenance="relayed",
        )
    ]
    config = SolverConfig(prior_strength=1.0)

    trusted_speaker = solve_hypotheses(
        players,
        2,
        claims,
        priors={"blue": 0.05, "green": 0.05},
        config=config,
    )
    suspected_speaker = solve_hypotheses(
        players,
        2,
        claims,
        priors={"blue": 0.95, "green": 0.05},
        config=config,
    )

    assert suspected_speaker["marginals"]["blue"] > trusted_speaker["marginals"]["blue"]
    assert suspected_speaker["marginals"]["red"] < trusted_speaker["marginals"]["red"]


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


def test_report_requires_single_source_pick_to_survive_source_removal(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CREWBORG_SOLVER", "1")
    monkeypatch.setenv("CREWBORG_SOLVER_ROBUST_P", "0")
    belief = Belief(
        self_role="crewmate",
        self_color="white",
        total_player_count=6,
        imposter_count=2,
    )
    for color in ("white", "red", "blue", "green", "yellow", "pink"):
        belief.roster[color] = PlayerRecord(color=color, life_status="alive")
    belief.social_claims = [
        _claim(meeting, "green", ("red",), evidence="vent") for meeting in (10, 20, 30)
    ]

    report = solver_report(belief)

    assert report["pre_robust_pick"] == "red"
    assert report["robust_required"] is True
    assert report["pick"] is None


def test_report_rejects_single_source_pick_sustained_by_a_ballot_pile(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CREWBORG_SOLVER", "1")
    monkeypatch.setenv("CREWBORG_SOLVER_P", "0.4")
    monkeypatch.setenv("CREWBORG_SOLVER_MARGIN", "0")
    belief = Belief(
        self_role="crewmate",
        self_color="white",
        total_player_count=6,
        imposter_count=2,
    )
    for color in ("white", "red", "blue", "green", "yellow", "pink"):
        belief.roster[color] = PlayerRecord(color=color, life_status="alive")
    belief.social_claims = [_claim(10, "green", ("red",), evidence="vent")]
    belief.meeting_history = [
        MeetingRecord(
            meeting_id=10,
            votes={"blue": "red", "yellow": "red", "pink": "red"},
        )
    ]

    report = solver_report(belief)

    assert report["pre_robust_pick"] == "red"
    assert report["robust_required"] is True
    assert report["robust_min_p"] > 0.39
    assert report["pick"] is None


def test_single_source_crowd_cap_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_SOLVER", "1")
    monkeypatch.setenv("CREWBORG_SOLVER_P", "0.4")
    monkeypatch.setenv("CREWBORG_SOLVER_MARGIN", "0")
    monkeypatch.setenv("CREWBORG_SOLVER_ROBUST_MAX_P", "-1")
    belief = Belief(
        self_role="crewmate",
        self_color="white",
        total_player_count=6,
        imposter_count=2,
    )
    for color in ("white", "red", "blue", "green", "yellow", "pink"):
        belief.roster[color] = PlayerRecord(color=color, life_status="alive")
    belief.social_claims = [_claim(10, "green", ("red",), evidence="vent")]
    belief.meeting_history = [
        MeetingRecord(
            meeting_id=10,
            votes={"blue": "red", "yellow": "red", "pink": "red"},
        )
    ]

    report = solver_report(belief)

    assert report["robust_min_p"] > 0.39
    assert report["pick"] == "red"


def test_report_accepts_decisive_multi_source_consensus(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_SOLVER", "1")
    belief = Belief(
        self_role="crewmate",
        self_color="white",
        total_player_count=6,
        imposter_count=2,
    )
    for color in ("white", "red", "blue", "green", "yellow", "pink"):
        belief.roster[color] = PlayerRecord(color=color, life_status="alive")
    belief.social_claims = [
        _claim(10, source, ("red",), evidence="vent")
        for source in ("green", "yellow", "pink")
    ]

    report = solver_report(belief)

    assert report["robust_required"] is False
    assert report["pick"] == "red"


def test_public_report_excludes_private_pins_clears_and_priors(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_SOLVER", "1")
    belief = Belief(
        self_role="crewmate",
        self_color="white",
        total_player_count=6,
        imposter_count=2,
    )
    for color in ("white", "red", "blue", "green", "yellow", "pink"):
        belief.roster[color] = PlayerRecord(color=color, life_status="alive")
    belief.roster["blue"].tasks_completed_watched = 1
    belief.roster["red"].events = [
        PlayerEvent(kind="vent_use", start_tick=4, end_tick=4)
    ]
    belief.suspicion = {"red": 0.99, "blue": 0.01}
    belief.social_claims = [
        _claim(10, source, ("blue",), evidence="vent")
        for source in ("green", "yellow", "pink")
    ]

    private = solver_report(belief)
    public = public_solver_report(belief)

    assert private["pins"] == ["red"]
    assert private["clears"] == ["blue"]
    assert public["pins"] == []
    assert public["clears"] == []
    assert public["pick"] == "blue"


def test_early_chat_requires_two_persistent_sources_at_selected_threshold(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CREWBORG_SOLVER_EARLY_CHAT_P", "0.76")
    monkeypatch.setenv("CREWBORG_SOLVER_EARLY_CHAT_MIN_SOURCES", "2")
    report = {"pick": "red", "top_p": 0.76}

    assert early_chat_pick(report, supporting_sources=["green"]) is None
    assert early_chat_pick(
        report,
        supporting_sources=["green", "yellow"],
    ) == "red"
    assert early_chat_pick(
        {"pick": "red", "top_p": 0.759},
        supporting_sources=["green", "yellow"],
    ) is None


def test_persistent_sources_span_meetings_and_exclude_self_output() -> None:
    belief = Belief(phase="Voting", phase_start_tick=20, self_color="pink")
    belief.social_claims = [
        _claim(10, "green", ("red",)),
        _claim(20, "yellow", ("red",)),
        _claim(20, "pink", ("red",)),
    ]

    assert persistent_target_sources(belief, {"pick": "red"}) == [
        "green",
        "yellow",
    ]


def test_report_does_not_fire_from_vote_only_consensus(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_SOLVER", "1")
    monkeypatch.setenv("CREWBORG_SOLVER_P", "0.4")
    monkeypatch.setenv("CREWBORG_SOLVER_MARGIN", "0")
    belief = Belief(
        self_role="crewmate",
        self_color="white",
        total_player_count=6,
        imposter_count=2,
    )
    for color in ("white", "red", "blue", "green", "yellow", "pink"):
        belief.roster[color] = PlayerRecord(color=color, life_status="alive")
    belief.meeting_history = [
        MeetingRecord(
            meeting_id=meeting,
            votes={"green": "red", "yellow": "red", "pink": "red"},
        )
        for meeting in (10, 20, 30)
    ]

    report = solver_report(belief)

    assert report["pre_robust_pick"] == "red"
    assert report["candidate_sources"] == []
    assert report["pick"] is None


def test_report_hard_clears_kill_victims_but_keeps_ejections_unknown(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CREWBORG_SOLVER", "1")
    belief = Belief(
        self_role="crewmate",
        self_color="white",
        total_player_count=6,
        imposter_count=2,
    )
    for color in ("white", "red", "blue", "green", "yellow", "pink"):
        belief.roster[color] = PlayerRecord(color=color, life_status="alive")
    belief.roster["red"].life_status = "dead"
    belief.roster["red"].death_source = "census"
    belief.roster["blue"].life_status = "dead"
    belief.roster["blue"].death_source = "ejection"
    belief.suspicion = {color: 0.4 for color in ("blue", "green", "yellow", "pink")}
    belief.social_claims = [
        _claim(10, "green", ("red",)),
        _claim(20, "yellow", ("blue",)),
        _claim(30, "pink", ("red",)),
    ]

    report = solver_report(belief)

    assert report["hard_clears"] == ["red"]
    assert report["marginals"]["red"] == 0.0
    assert all(
        "red" not in hypothesis["imposters"] for hypothesis in report["hypotheses"]
    )
    assert any(
        "blue" in hypothesis["imposters"] for hypothesis in report["hypotheses"]
    )


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


def test_solver_decays_repeated_voter_target_pairs_across_meetings() -> None:
    players = ["red", "blue", "green", "yellow", "pink"]
    repeated = [
        MeetingRecord(meeting_id=10, votes={"green": "red"}),
        MeetingRecord(meeting_id=20, votes={"green": "red"}),
    ]
    independent = [
        MeetingRecord(meeting_id=10, votes={"green": "red"}),
        MeetingRecord(meeting_id=20, votes={"yellow": "red"}),
    ]
    config = SolverConfig(prior_strength=0.0, vote_repeat_decay=0.25)

    repeated_result = solve_hypotheses(
        players,
        2,
        [],
        repeated,
        config=config,
    )
    independent_result = solve_hypotheses(
        players,
        2,
        [],
        independent,
        config=config,
    )

    assert repeated_result["marginals"]["red"] < independent_result["marginals"]["red"]
