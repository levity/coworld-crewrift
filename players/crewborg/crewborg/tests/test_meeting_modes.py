"""Attend Meeting / Report Body / Accuse mode tests (design §7.1)."""

from __future__ import annotations

import crewborg.modes.attend_meeting as attend_meeting

from crewborg.action import BTN_A, BTN_DOWN, resolve_action
from crewborg.modes import AccuseMode, AttendMeetingMode, ReportBodyMode
from crewborg.perception.entities import VoteCandidate, VoteDot, VotingState
from crewborg.strategy.meeting import MeetingDecision, MeetingLLMResult
from crewborg.types import ActionState, Belief, BodyEntry, ChatEvent, PlayerEvent, PlayerRecord


class _FakeMeetingClient:
    enabled = True
    disabled_reason = None

    def __init__(self, decisions: list[MeetingDecision], *, timeout_seconds: float | None = None) -> None:
        self.decisions = list(decisions)
        self.timeout_seconds = timeout_seconds
        self.calls: list[tuple[str, dict]] = []

    def decide(self, context: dict, *, trigger: str) -> MeetingLLMResult:
        self.calls.append((trigger, context))
        return MeetingLLMResult(
            decision=self.decisions.pop(0),
            model="fake-haiku",
            latency_ms=1.5,
        )


def _meeting_belief(*, tick: int = 0, start_tick: int = 0) -> Belief:
    belief = Belief(phase="Voting", phase_start_tick=start_tick, last_tick=tick, total_player_count=2)
    belief.voting = VotingState(
        timer_present=True,
        self_marker_color="blue",
        candidates=(
            VoteCandidate(slot=0, color="red", alive=True),
            VoteCandidate(slot=1, color="blue", alive=True),
        ),
        cursor_slot=0,
    )
    belief.roster["red"] = PlayerRecord(color="red", life_status="alive", last_seen_tick=1)
    belief.roster["blue"] = PlayerRecord(color="blue", life_status="alive", last_seen_tick=1)
    belief.suspicion = {"red": 0.95}
    return belief


def test_attend_meeting_accuses_a_clear_suspect_then_votes_them() -> None:
    mode = AttendMeetingMode()
    belief = Belief(phase="Voting")
    belief.roster["red"] = PlayerRecord(
        color="red", life_status="alive", events=[PlayerEvent(kind="vent_use", start_tick=4, end_tick=4)]
    )
    belief.suspicion = {"red": 0.95, "blue": 0.2}  # red a clear leading suspect

    chat = mode.decide(belief, ActionState())
    assert chat.kind == "chat" and chat.text == "red sus: saw them vent"  # accuse, citing evidence

    vote = mode.decide(belief, ActionState())
    assert vote.kind == "vote" and vote.target_color == "red"  # votes whom it accused
    assert mode.decide(belief, ActionState()).kind == "vote"


def test_meeting_never_votes_self_even_if_self_is_top_suspect() -> None:
    # The crew-loss bug: our own colour saturated suspicion and we voted ourself out.
    mode = AttendMeetingMode()
    belief = Belief(phase="Voting", self_role="crewmate", self_color="red")
    belief.voting = VotingState(
        timer_present=True, self_marker_color="red",
        candidates=(VoteCandidate(slot=0, color="red", alive=True), VoteCandidate(slot=1, color="blue", alive=True)),
    )
    belief.suspicion = {"red": 0.99}  # self forced as the only/top suspect

    intent = mode.decide(belief, ActionState())
    assert intent.kind == "vote" and intent.target_color is None  # skip — never red (self)


def test_attend_meeting_stays_silent_and_skips_a_flat_field() -> None:
    mode = AttendMeetingMode()
    belief = Belief(phase="Voting")
    belief.suspicion = {"red": 0.4, "blue": 0.2}  # no clear leader — flat/low field

    intent = mode.decide(belief, ActionState())
    assert intent.kind == "vote" and intent.target_color is None  # silent skip, no chat opener


def test_attend_meeting_stays_idle_after_vote_confirmation() -> None:
    mode = AttendMeetingMode()
    belief = Belief(phase="Voting")  # no suspicion ⇒ silent skip, the vote is the first decision
    belief.voting = VotingState(skip_cursor_present=True)
    action_state = ActionState()

    vote = mode.decide(belief, action_state)
    command = resolve_action(vote, belief, action_state)
    assert command.held_mask == BTN_A and action_state.vote_confirmed

    idle = mode.decide(belief, action_state)
    resolve_action(idle, belief, action_state)  # intent change resets action_state.vote_confirmed
    assert mode.decide(belief, action_state).kind == "idle"


def test_attend_meeting_llm_sends_multiple_chats_after_new_chat_and_cooldown() -> None:
    client = _FakeMeetingClient(
        [
            MeetingDecision(action="send_chat", chat_text="red, where were you?", vote_target="red"),
            MeetingDecision(action="send_chat", chat_text="that route does not clear red"),
        ]
    )
    mode = AttendMeetingMode(llm_client=client)

    first = mode.decide(_meeting_belief(tick=0), ActionState())
    assert first.kind == "chat"
    assert first.text == "red, where were you?"

    belief = _meeting_belief(tick=101)
    belief.chat_log = [ChatEvent(tick=20, speaker_color="red", text="i was nav")]
    second = mode.decide(belief, ActionState())
    assert second.kind == "chat"
    assert second.text == "that route does not clear red"
    assert [trigger for trigger, _ in client.calls] == ["meeting_start", "new_chat"]


def test_attend_meeting_llm_tentative_vote_auto_submits_near_deadline() -> None:
    client = _FakeMeetingClient([MeetingDecision(action="set_tentative_vote", vote_target="red")])
    mode = AttendMeetingMode(llm_client=client)

    assert mode.decide(_meeting_belief(tick=0), ActionState()).kind == "idle"

    vote = mode.decide(_meeting_belief(tick=193), ActionState())
    assert vote.kind == "vote"
    assert vote.target_color == "red"


def test_attend_meeting_uses_advertised_vote_deadline() -> None:
    client = _FakeMeetingClient([MeetingDecision(action="set_tentative_vote", vote_target="red")])
    mode = AttendMeetingMode(llm_client=client)
    belief = _meeting_belief(tick=0)
    belief.vote_timer_ticks = 1200

    assert mode.decide(belief, ActionState()).kind == "idle"

    belief = _meeting_belief(tick=1151)
    belief.vote_timer_ticks = 1200
    assert mode.decide(belief, ActionState()).kind == "idle"

    belief = _meeting_belief(tick=1152)
    belief.vote_timer_ticks = 1200
    vote = mode.decide(belief, ActionState())
    assert vote.kind == "vote"
    assert vote.target_color == "red"


def test_solver_uses_most_of_the_advertised_vote_deadline(monkeypatch) -> None:
    monkeypatch.setattr(attend_meeting, "solver_enabled", lambda: True)
    monkeypatch.setattr(attend_meeting, "solver_veto_enabled", lambda: False)
    monkeypatch.setattr(
        attend_meeting,
        "solver_report",
        lambda belief: {"pick": "red", "marginals": {"red": 0.9}},
    )
    monkeypatch.setattr(attend_meeting, "build_accusation", lambda belief, target: f"{target} sus")

    mode = AttendMeetingMode()
    belief = _meeting_belief(tick=1151)
    belief.self_role = "crewmate"
    belief.vote_timer_ticks = 1200
    assert mode.decide(belief, ActionState()).kind == "idle"

    belief.last_tick = 1152
    chat = mode.decide(belief, ActionState())
    assert chat.kind == "chat"
    assert chat.text == "red sus"

    belief.last_tick = 1153
    vote = mode.decide(belief, ActionState())
    assert vote.kind == "vote"
    assert vote.target_color == "red"


def test_solver_commits_public_target_when_tick_360_resolve_agrees(
    monkeypatch,
) -> None:
    monkeypatch.setattr(attend_meeting, "solver_enabled", lambda: True)
    monkeypatch.setattr(attend_meeting, "solver_veto_enabled", lambda: False)
    monkeypatch.setattr(attend_meeting, "solver_early_chat_enabled", lambda: True)
    monkeypatch.setattr(attend_meeting, "solver_early_chat_offset_ticks", lambda: 240)
    monkeypatch.setattr(attend_meeting, "solver_early_vote_offset_ticks", lambda: 360)
    monkeypatch.setattr(
        attend_meeting,
        "public_solver_report",
        lambda belief: {"pick": "red", "top_p": 0.8},
    )
    monkeypatch.setattr(
        attend_meeting,
        "solver_persistent_target_sources",
        lambda belief, report: ["green", "yellow"],
    )
    monkeypatch.setattr(
        attend_meeting,
        "solver_early_chat_pick",
        lambda report, supporting_sources: report["pick"],
    )
    mode = AttendMeetingMode()
    belief = _meeting_belief(tick=239)
    belief.self_role = "crewmate"
    belief.vote_timer_ticks = 1200
    assert mode.decide(belief, ActionState()).kind == "idle"

    belief.last_tick = 240
    early = mode.decide(belief, ActionState())
    assert early.kind == "chat"
    assert early.text == "green and yellow called red sus. vote red"

    belief.last_tick = 359
    assert mode.decide(belief, ActionState()).kind == "idle"

    belief.last_tick = 360
    vote = mode.decide(belief, ActionState())
    assert vote.kind == "vote"
    assert vote.target_color == "red"


def test_solver_does_not_commit_early_when_tick_360_target_changes(
    monkeypatch,
) -> None:
    reports = iter(
        [
            {"pick": "red", "top_p": 0.8},
            {"pick": "green", "top_p": 0.8},
        ]
    )
    monkeypatch.setattr(attend_meeting, "solver_enabled", lambda: True)
    monkeypatch.setattr(attend_meeting, "solver_veto_enabled", lambda: False)
    monkeypatch.setattr(attend_meeting, "solver_early_chat_enabled", lambda: True)
    monkeypatch.setattr(attend_meeting, "solver_early_chat_offset_ticks", lambda: 240)
    monkeypatch.setattr(attend_meeting, "solver_early_vote_offset_ticks", lambda: 360)
    monkeypatch.setattr(
        attend_meeting,
        "public_solver_report",
        lambda belief: next(reports),
    )
    monkeypatch.setattr(
        attend_meeting,
        "solver_persistent_target_sources",
        lambda belief, report: ["blue", "yellow"],
    )
    monkeypatch.setattr(
        attend_meeting,
        "solver_early_chat_pick",
        lambda report, supporting_sources: report["pick"],
    )

    mode = AttendMeetingMode()
    belief = _meeting_belief(tick=240)
    belief.self_role = "crewmate"
    belief.vote_timer_ticks = 1200
    assert mode.decide(belief, ActionState()).kind == "chat"

    belief.last_tick = 360
    assert mode.decide(belief, ActionState()).kind == "idle"

    belief.last_tick = 500
    assert mode.decide(belief, ActionState()).kind == "idle"


def test_solver_uses_source_backed_public_pick_when_private_solve_is_silent(
    monkeypatch,
) -> None:
    monkeypatch.setattr(attend_meeting, "solver_enabled", lambda: True)
    monkeypatch.setattr(attend_meeting, "solver_veto_enabled", lambda: False)
    monkeypatch.setattr(
        attend_meeting,
        "solver_report",
        lambda belief: {"pick": None, "marginals": {"red": 0.4}},
    )
    monkeypatch.setattr(
        attend_meeting,
        "public_solver_report",
        lambda belief: {
            "pick": "red",
            "candidate_sources": ["green"],
            "top_p": 0.72,
        },
    )
    monkeypatch.setattr(
        attend_meeting,
        "solver_public_source_backed_pick",
        lambda report: report["pick"],
    )
    monkeypatch.setattr(
        attend_meeting,
        "solver_persistent_target_sources",
        lambda belief, report: ["green"],
    )

    mode = AttendMeetingMode()
    belief = _meeting_belief(tick=1152)
    belief.self_role = "crewmate"
    belief.vote_timer_ticks = 1200

    chat = mode.decide(belief, ActionState())
    assert chat.kind == "chat"
    assert chat.text == "green called red sus. vote red"

    belief.last_tick = 1153
    vote = mode.decide(belief, ActionState())
    assert vote.kind == "vote"
    assert vote.target_color == "red"


def test_solver_early_chat_attempt_does_not_retry_after_calibrated_tick(
    monkeypatch,
) -> None:
    calls: list[int] = []
    monkeypatch.setattr(attend_meeting, "solver_enabled", lambda: True)
    monkeypatch.setattr(attend_meeting, "solver_veto_enabled", lambda: False)
    monkeypatch.setattr(attend_meeting, "solver_early_chat_enabled", lambda: True)
    monkeypatch.setattr(attend_meeting, "solver_early_chat_offset_ticks", lambda: 240)
    monkeypatch.setattr(
        attend_meeting,
        "public_solver_report",
        lambda belief: calls.append(belief.last_tick) or {"pick": None},
    )
    monkeypatch.setattr(
        attend_meeting,
        "solver_persistent_target_sources",
        lambda belief, report: [],
    )
    monkeypatch.setattr(
        attend_meeting,
        "solver_early_chat_pick",
        lambda report, supporting_sources: None,
    )

    mode = AttendMeetingMode()
    belief = _meeting_belief(tick=240)
    belief.self_role = "crewmate"
    belief.vote_timer_ticks = 1200
    assert mode.decide(belief, ActionState()).kind == "idle"

    belief.last_tick = 300
    assert mode.decide(belief, ActionState()).kind == "idle"
    assert calls == [240]


def test_solver_truthfully_defends_self_without_staging_vote(monkeypatch) -> None:
    monkeypatch.setattr(attend_meeting, "solver_enabled", lambda: True)
    monkeypatch.setattr(attend_meeting, "solver_veto_enabled", lambda: False)
    monkeypatch.setattr(attend_meeting, "solver_early_chat_enabled", lambda: True)
    monkeypatch.setattr(attend_meeting, "solver_early_chat_offset_ticks", lambda: 240)

    mode = AttendMeetingMode()
    belief = _meeting_belief(tick=300)
    belief.self_role = "crewmate"
    belief.self_color = "blue"
    belief.vote_timer_ticks = 1200
    belief.voting = belief.voting.model_copy(
        update={"dots": (VoteDot(voter=0, target=1),)}
    )

    defense = mode.decide(belief, ActionState())

    assert defense.kind == "chat"
    assert defense.text == "blue is not sus. don't pile me without evidence; skip."

    belief.last_tick = 301
    assert mode.decide(belief, ActionState()).kind == "idle"


def test_solver_off_timing_control_defers_the_frozen_legacy_vote(monkeypatch) -> None:
    monkeypatch.setattr(attend_meeting, "solver_enabled", lambda: False)
    monkeypatch.setattr(attend_meeting, "solver_veto_enabled", lambda: False)
    monkeypatch.setattr(attend_meeting, "solver_defer_enabled", lambda: True)
    monkeypatch.setattr(attend_meeting, "solver_report", lambda belief: {"pick": None})
    monkeypatch.setattr(
        attend_meeting,
        "top_suspect",
        lambda belief: "red" if belief.last_tick == 0 else None,
    )
    monkeypatch.setattr(attend_meeting, "build_accusation", lambda belief, target: f"{target} sus")

    mode = AttendMeetingMode()
    belief = _meeting_belief(tick=0)
    belief.self_role = "crewmate"
    belief.vote_timer_ticks = 1200
    assert mode.decide(belief, ActionState()).kind == "idle"

    belief.last_tick = 1152
    chat = mode.decide(belief, ActionState())
    assert chat.kind == "chat"
    assert chat.text == "red sus"

    belief.last_tick = 1153
    vote = mode.decide(belief, ActionState())
    assert vote.kind == "vote"
    assert vote.target_color == "red"


def test_solver_abstention_uses_meeting_entry_legacy_target(monkeypatch) -> None:
    monkeypatch.setattr(attend_meeting, "solver_enabled", lambda: True)
    monkeypatch.setattr(attend_meeting, "solver_veto_enabled", lambda: False)
    monkeypatch.setattr(attend_meeting, "solver_report", lambda belief: {"pick": None})
    monkeypatch.setattr(
        attend_meeting,
        "top_suspect",
        lambda belief: "red" if belief.last_tick == 0 else None,
    )
    monkeypatch.setattr(attend_meeting, "build_accusation", lambda belief, target: f"{target} sus")

    mode = AttendMeetingMode()
    belief = _meeting_belief(tick=0)
    belief.self_role = "crewmate"
    belief.vote_timer_ticks = 1200
    assert mode.decide(belief, ActionState()).kind == "idle"

    belief.last_tick = 1152
    chat = mode.decide(belief, ActionState())
    assert chat.kind == "chat"
    assert chat.text == "red sus"


def test_solver_gather_window_yields_to_a_short_vote_deadline(monkeypatch) -> None:
    monkeypatch.setattr(attend_meeting, "solver_enabled", lambda: True)
    monkeypatch.setattr(attend_meeting, "solver_veto_enabled", lambda: False)
    monkeypatch.setattr(attend_meeting, "solver_report", lambda belief: {"pick": "red"})
    monkeypatch.setattr(attend_meeting, "build_accusation", lambda belief, target: f"{target} sus")

    mode = AttendMeetingMode()
    belief = _meeting_belief(tick=71)
    belief.self_role = "crewmate"
    belief.vote_timer_ticks = 120
    assert mode.decide(belief, ActionState()).kind == "idle"

    belief.last_tick = 72
    assert mode.decide(belief, ActionState()).kind == "chat"

    belief.last_tick = 73
    vote = mode.decide(belief, ActionState())
    assert vote.kind == "vote"
    assert vote.target_color == "red"


def test_attend_meeting_llm_can_submit_vote_early() -> None:
    client = _FakeMeetingClient([MeetingDecision(action="submit_vote", vote_target="red")])
    mode = AttendMeetingMode(llm_client=client)

    vote = mode.decide(_meeting_belief(tick=0), ActionState())
    assert vote.kind == "vote"
    assert vote.target_color == "red"


def test_attend_meeting_llm_low_confidence_submit_still_votes() -> None:
    client = _FakeMeetingClient([MeetingDecision(action="submit_vote", vote_target="red", confidence=0.01)])
    mode = AttendMeetingMode(llm_client=client)

    vote = mode.decide(_meeting_belief(tick=0), ActionState())

    assert vote.kind == "vote"
    assert vote.target_color == "red"


def test_attend_meeting_llm_self_target_never_votes_self() -> None:
    client = _FakeMeetingClient([MeetingDecision(action="submit_vote", vote_target="blue")])
    mode = AttendMeetingMode(llm_client=client)
    belief = _meeting_belief(tick=0)
    belief.suspicion = {}

    vote = mode.decide(belief, ActionState())

    assert vote.kind == "vote"
    assert vote.target_color is None


def test_attend_meeting_llm_submitted_vote_persists_until_confirmed() -> None:
    client = _FakeMeetingClient([MeetingDecision(action="submit_vote", vote_target="red")])
    mode = AttendMeetingMode(llm_client=client)
    belief = _meeting_belief(tick=0)
    action_state = ActionState()

    vote = mode.decide(belief, action_state)
    assert vote.kind == "vote" and vote.target_color == "red"
    command = resolve_action(vote, belief, action_state)
    assert command.held_mask == BTN_A and action_state.vote_confirmed

    idle = mode.decide(belief, action_state)
    resolve_action(idle, belief, action_state)
    assert mode.decide(belief, action_state).kind == "idle"
    assert len(client.calls) == 1


def test_attend_meeting_llm_submitted_vote_keeps_driving_cursor_until_confirmed() -> None:
    client = _FakeMeetingClient([MeetingDecision(action="submit_vote", vote_target="blue")])
    mode = AttendMeetingMode(llm_client=client)
    belief = _meeting_belief(tick=0)
    belief.voting = belief.voting.model_copy(update={"self_marker_color": "green"})
    action_state = ActionState()

    vote = mode.decide(belief, action_state)
    assert vote.kind == "vote" and vote.target_color == "blue"
    command = resolve_action(vote, belief, action_state)
    assert command.held_mask == BTN_DOWN and not action_state.vote_confirmed

    belief.voting = belief.voting.model_copy(update={"cursor_slot": 1})
    vote = mode.decide(belief, action_state)
    assert vote.kind == "vote" and vote.target_color == "blue"
    command = resolve_action(vote, belief, action_state)
    assert command.held_mask == BTN_A and action_state.vote_confirmed
    assert len(client.calls) == 1


def test_attend_meeting_invalid_llm_decision_falls_back_to_the_deterministic_accusation() -> None:
    client = _FakeMeetingClient([MeetingDecision(action="send_chat", chat_text="vote green", vote_target="green")])
    mode = AttendMeetingMode(llm_client=client)
    belief = _meeting_belief(tick=0)  # suspicion {"red": 0.95} ⇒ red the clear suspect
    belief.roster["red"].events.append(PlayerEvent(kind="vent_use", start_tick=2, end_tick=2))

    intent = mode.decide(belief, ActionState())
    assert intent.kind == "chat"
    assert intent.text == "red sus: saw them vent"  # fell back to the deterministic accusation


def test_attend_meeting_deadline_prompt_wins_over_late_chat() -> None:
    client = _FakeMeetingClient([MeetingDecision(action="wait"), MeetingDecision(action="wait")])
    mode = AttendMeetingMode(llm_client=client)

    assert mode.decide(_meeting_belief(tick=0), ActionState()).kind == "idle"
    belief = _meeting_belief(tick=107)
    belief.chat_log = [ChatEvent(tick=100, speaker_color="red", text="blue sus")]

    assert mode.decide(belief, ActionState()).kind == "idle"
    assert [trigger for trigger, _ in client.calls] == ["meeting_start", "deadline"]


def test_attend_meeting_late_chat_in_danger_window_does_not_call_llm() -> None:
    client = _FakeMeetingClient(
        [MeetingDecision(action="wait"), MeetingDecision(action="send_chat", chat_text="too late")]
    )
    mode = AttendMeetingMode(llm_client=client)

    assert mode.decide(_meeting_belief(tick=0), ActionState()).kind == "idle"
    belief = _meeting_belief(tick=108)
    belief.chat_log = [ChatEvent(tick=100, speaker_color="red", text="blue sus")]

    assert mode.decide(belief, ActionState()).kind == "idle"
    assert [trigger for trigger, _ in client.calls] == ["meeting_start"]


def test_report_body_targets_nearest_visible_body() -> None:
    belief = Belief(self_world_x=100, self_world_y=100, visible_body_ids={2001, 2005})
    belief.bodies[2001] = BodyEntry(object_id=2001, color="red", world_x=400, world_y=400, first_seen_tick=1)
    belief.bodies[2005] = BodyEntry(object_id=2005, color="blue", world_x=110, world_y=100, first_seen_tick=1)
    intent = ReportBodyMode().decide(belief, ActionState())
    assert intent.kind == "report" and intent.target_id == 2005  # the nearer body


def test_report_body_idles_with_no_body_in_view() -> None:
    assert ReportBodyMode().decide(Belief(), ActionState()).kind == "idle"


def test_accuse_mode_calls_a_meeting_naming_the_active_tail() -> None:
    belief = Belief(self_world_x=100, self_world_y=100, last_tick=40)
    belief.roster["red"] = PlayerRecord(
        color="red", world_x=120, world_y=100, last_seen_tick=40, life_status="alive",
        events=[PlayerEvent(kind="tailing_self", start_tick=1, end_tick=40, target_color=None)],
    )
    belief.suspicion = {"red": 0.7}  # over the sketched-out bar
    intent = AccuseMode().decide(belief, ActionState())
    assert intent.kind == "call_meeting" and intent.target_color == "red"
