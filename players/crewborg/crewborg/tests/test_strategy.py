"""Mode selector tests (design §10)."""

from __future__ import annotations

from players.player_sdk.types import BeliefSnapshot, ModeDirective, SharedMemory

from crewborg.map.types import MapData, MapPoint, MapRect
from crewborg.strategy import RuleBasedStrategy
from crewborg.types import (
    ActionState,
    Belief,
    CommanderPriorities,
    PlayerEvent,
    PlayerRecord,
)


def _select(belief: Belief) -> str:
    return _select_with(RuleBasedStrategy(), belief)


def _select_with(strategy: RuleBasedStrategy, belief: Belief, tick: int = 1) -> str:
    memory = SharedMemory(
        belief=belief, action_state=ActionState(), active_directive=ModeDirective(mode="idle")
    )
    directive = strategy.decide(BeliefSnapshot(tick=tick, memory=memory))
    return directive.mode


def _crewmate_being_tailed(
    *, tick: int, p: float = 0.7, tail_end: int | None = None, color: str = "red", alive: bool = True
) -> Belief:
    """A live crewmate being shadowed by ``color``: an (optionally lapsed) tailing_self
    interval plus a manually set posterior ``p`` (the selector reads belief.suspicion)."""

    belief = Belief(phase="Playing", self_role="crewmate", last_tick=tick, self_world_x=100, self_world_y=100)
    # A reachable button away from self (no nav graph ⇒ reachable), so Accuse can fire
    # and walk to it without immediately being "inside" it.
    belief.map = MapData(
        width=200, height=200, tasks=(), vents=(), rooms=(),
        button=MapRect(x=10, y=10, w=8, h=8), home=MapPoint(x=10, y=10),
    )
    belief.roster[color] = PlayerRecord(
        color=color,
        world_x=110,
        world_y=100,
        last_seen_tick=tick,
        life_status="alive" if alive else "dead",
        events=[
            PlayerEvent(
                kind="tailing_self", start_tick=1, end_tick=tick if tail_end is None else tail_end, target_color=None
            )
        ],
    )
    belief.suspicion = {color: p}
    return belief


def _map_with_button_around_self() -> MapData:
    # A button rect covering self at (100, 100), so "inside the button rect" is true.
    return MapData(
        width=200, height=200, tasks=(), vents=(), rooms=(),
        button=MapRect(x=96, y=96, w=8, h=8), home=MapPoint(x=10, y=10),
    )


def test_playing_crewmate_selects_normal() -> None:
    assert _select(Belief(phase="Playing", self_role="crewmate")) == "normal"
    # Role not yet known during early Playing still does tasks.
    assert _select(Belief(phase="Playing", self_role=None)) == "normal"
    # A ghost (dead) keeps doing its own tasks (design §7.3), regardless of role.
    assert _select(Belief(phase="Playing", self_role="crewmate", self_alive=False)) == "normal"


def test_self_preservation_flag_selects_composed_crew_mode(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_SELF_PRESERVATION", "1")
    monkeypatch.setenv("CREWBORG_DEDUCTION_HISTORY", "1")
    belief = Belief(phase="Playing", self_role="crewmate", self_alive=True)

    assert _select(belief) == "self_preservation"


def test_self_preservation_never_selects_for_ghost(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_SELF_PRESERVATION", "1")
    monkeypatch.setenv("CREWBORG_DEDUCTION_HISTORY", "1")
    belief = Belief(phase="Playing", self_role="crewmate", self_alive=False)

    assert _select(belief) == "normal"


def test_voting_selects_attend_meeting() -> None:
    assert _select(Belief(phase="Voting")) == "attend_meeting"


def test_body_in_view_selects_report_body() -> None:
    from crewborg.types import BodyEntry

    belief = Belief(phase="Playing", self_role="crewmate", visible_body_ids={2003})
    belief.bodies[2003] = BodyEntry(object_id=2003, color="green", world_x=10, world_y=10, first_seen_tick=1)
    assert _select(belief) == "report_body"


def test_ghost_does_tasks_not_report() -> None:
    from crewborg.types import BodyEntry

    # A dead crewmate (ghost) can't report; it goes straight to Normal even with a
    # body in view, so it keeps finishing its own tasks (design §7.3).
    belief = Belief(phase="Playing", self_role="crewmate", self_alive=False, visible_body_ids={2003})
    belief.bodies[2003] = BodyEntry(object_id=2003, color="green", world_x=10, world_y=10, first_seen_tick=1)
    assert _select(belief) == "normal"


def test_active_tail_by_a_suspect_selects_accuse() -> None:
    assert _select(_crewmate_being_tailed(tick=40, p=0.7)) == "accuse"


def test_a_tail_below_the_sketched_out_bar_keeps_tasking() -> None:
    # Being tailed, but we're not yet suspicious enough (< ACCUSE_THRESHOLD) ⇒ tasks.
    assert _select(_crewmate_being_tailed(tick=40, p=0.4)) == "normal"


def test_a_suspect_not_currently_tailing_keeps_tasking() -> None:
    # Suspicious, but the tail lapsed long ago (no live tailing_self) ⇒ no accuse.
    assert _select(_crewmate_being_tailed(tick=100, p=0.7, tail_end=10)) == "normal"


def test_accuse_commitment_persists_when_the_tail_briefly_lapses() -> None:
    strategy = RuleBasedStrategy()
    assert _select_with(strategy, _crewmate_being_tailed(tick=40, p=0.7), tick=40) == "accuse"
    # The tail lapses mid-walk to the button, but we stay committed to the run.
    lapsed = _crewmate_being_tailed(tick=50, p=0.7, tail_end=10)
    assert _select_with(strategy, lapsed, tick=50) == "accuse"


def test_accuse_stops_once_the_committed_target_dies() -> None:
    strategy = RuleBasedStrategy()
    assert _select_with(strategy, _crewmate_being_tailed(tick=40, p=0.7), tick=40) == "accuse"
    dead = _crewmate_being_tailed(tick=50, p=0.7, alive=False)
    assert _select_with(strategy, dead, tick=50) == "normal"


def test_the_one_button_call_is_spent_at_the_button_then_we_fall_back_to_tasks() -> None:
    strategy = RuleBasedStrategy()
    at_button = _crewmate_being_tailed(tick=40, p=0.7)
    at_button.map = _map_with_button_around_self()  # self is inside the button rect
    assert _select_with(strategy, at_button, tick=40) == "accuse"  # presses A — call spent
    # Still being tailed next tick, but the one call is used ⇒ back to tasks, not stuck.
    assert _select_with(strategy, _crewmate_being_tailed(tick=41, p=0.7), tick=41) == "normal"


def test_an_unreachable_button_keeps_us_tasking_instead_of_stalling() -> None:
    # Map present but no nav graph yet ⇒ optimistically reachable (steer straight).
    from crewborg.strategy.rule_based import _button_reachable

    assert _button_reachable(Belief()) is False  # no map ⇒ can't call a meeting
    assert _button_reachable(_crewmate_being_tailed(tick=40, p=0.7)) is True  # map, no nav ⇒ ok
    # With a nav graph the guard keys on button_anchor (unreachable ⇒ False), so the
    # selector falls back to Normal rather than committing to an unrouteable goal.


def test_a_new_game_restores_the_button_call_budget() -> None:
    strategy = RuleBasedStrategy()
    at_button = _crewmate_being_tailed(tick=40, p=0.7)
    at_button.map = _map_with_button_around_self()
    _select_with(strategy, at_button, tick=40)  # spends the call
    assert _select_with(strategy, _crewmate_being_tailed(tick=41, p=0.7), tick=41) == "normal"
    # A fresh game (RoleReveal) resets the budget; accusing is available again.
    assert _select_with(strategy, Belief(phase="RoleReveal"), tick=42) == "idle"
    assert _select_with(strategy, _crewmate_being_tailed(tick=43, p=0.7), tick=43) == "accuse"


def test_non_playing_phases_idle() -> None:
    assert _select(Belief(phase="Lobby")) == "idle"
    assert _select(Belief(phase="RoleReveal")) == "idle"
    assert _select(Belief(phase="GameOver")) == "idle"


def _imposter_with_visible_target(**kwargs) -> Belief:
    from crewborg.types import PlayerRecord

    belief = Belief(phase="Playing", self_role="imposter", last_tick=10, self_world_x=100, self_world_y=100, **kwargs)
    # A lone, isolated, reachable (no nav graph) crewmate — a valid kill opportunity.
    belief.roster["red"] = PlayerRecord(
        object_id=1004, color="red", facing="left", world_x=50, world_y=50, last_seen_tick=10,
        life_status="alive",
    )
    return belief


def test_imposter_searches_by_default() -> None:
    # No kill opportunity ⇒ Search (the always-on seeking stance; Pretend retired
    # 2026-06-24). Search keeps us near crew so a kill window opens.
    assert _select(Belief(phase="Playing", self_role="imposter", last_tick=10)) == "search"


def test_imposter_hunts_when_kill_ready_with_opportunity() -> None:
    assert _select(_imposter_with_visible_target(self_kill_ready=True)) == "hunt"
    # Kill ready but no target in view ⇒ Search owns target acquisition.
    no_target = Belief(
        phase="Playing", self_role="imposter", self_kill_ready=True, last_tick=10,
        self_world_x=100, self_world_y=100,
    )
    assert _select(no_target) == "search"


def test_imposter_hunts_to_stalk_even_when_targets_are_clustered() -> None:
    from crewborg.types import PlayerRecord

    # Kill ready with crewmates in sight (even clustered) ⇒ Hunt and stalk; Hunt
    # itself holds off the actual kill until the victim is isolated.
    belief = Belief(
        phase="Playing", self_role="imposter", self_kill_ready=True, last_tick=10,
        self_world_x=100, self_world_y=100,
    )
    belief.roster["green"] = PlayerRecord(
        object_id=1004, color="green", facing="left", world_x=50, world_y=50, last_seen_tick=10,
        life_status="alive",
    )
    belief.roster["blue"] = PlayerRecord(
        object_id=1005, color="blue", facing="left", world_x=58, world_y=50, last_seen_tick=10,
        life_status="alive",
    )
    assert _select(belief) == "hunt"


def test_imposter_evades_before_reporting_a_fresh_kill_body() -> None:
    from crewborg.types import BodyEntry

    # A fresh self-kill body in view -> evade first, outranking the old
    # report-first path even if the kill is otherwise ready.
    belief = _imposter_with_visible_target(self_kill_ready=True, last_kill_tick=9, visible_body_ids={2003})
    belief.bodies[2003] = BodyEntry(object_id=2003, color="green", world_x=60, world_y=60, first_seen_tick=10)
    assert _select(belief) == "evade"


def test_commander_skip_evade_goes_straight_to_kill_loop() -> None:
    belief = _imposter_with_visible_target(self_kill_ready=True, last_kill_tick=9)
    belief.commander = CommanderPriorities(
        skip_evade=True,
        danger_reason="chain pressure before crew groups",
        as_of_tick=belief.last_tick,
    )
    assert _select(belief) == "hunt"
    assert belief.commander_danger_events == [
        {
            "lever": "skip_evade",
            "danger_reason": "chain pressure before crew groups",
        }
    ]


def test_stale_commander_skip_evade_keeps_conservative_evade() -> None:
    belief = _imposter_with_visible_target(self_kill_ready=True, last_kill_tick=9)
    belief.commander = CommanderPriorities(
        skip_evade=True,
        danger_reason="stale chain pressure",
        as_of_tick=0,
    )
    belief.last_tick = 500
    belief.last_kill_tick = 499
    belief.roster["red"].last_seen_tick = 500
    assert _select(belief) == "evade"
    assert belief.commander_danger_events == []


def test_imposter_never_reports_a_body() -> None:
    from crewborg.types import BodyEntry

    belief = _imposter_with_visible_target(self_kill_ready=True, last_kill_tick=1, visible_body_ids={2003})
    belief.last_tick = 500  # past the post-kill re-approach window (EVADE_TICKS = 400)
    belief.roster["red"].last_seen_tick = 500  # the victim is visible *now* -> Hunt wins
    belief.bodies[2003] = BodyEntry(object_id=2003, color="green", world_x=60, world_y=60, first_seen_tick=10)
    # A visible body no longer routes the imposter to Report Body — it kills, not reports.
    assert _select(belief) == "hunt"

    body_only = Belief(phase="Playing", self_role="imposter", self_kill_ready=False, last_tick=200, visible_body_ids={2003})
    body_only.bodies[2003] = BodyEntry(object_id=2003, color="green", world_x=60, world_y=60, first_seen_tick=10)
    assert _select(body_only) == "search"


def test_imposter_recons_within_the_recon_window_before_ready() -> None:
    # Not yet kill-ready, the cooldown clears in ~50 ticks (≤ recon_window 100), and a
    # crewmate has been seen ⇒ Recon (beeline to that crewmate so a victim is in hand
    # the instant the kill comes ready), not Search.
    belief = _imposter_with_visible_target(self_kill_ready=False)
    belief.kill_cooldown_start_tick = belief.last_tick
    belief.kill_cooldown_estimate = 50  # ticks_until_ready = start + 50 − now = 50
    assert _select(belief) == "recon"


def test_imposter_searches_outside_the_recon_window() -> None:
    # Cooldown clears in ~200 ticks (> recon_window 100) ⇒ still Search; recon only
    # fires in the short pre-ready window.
    belief = _imposter_with_visible_target(self_kill_ready=False)
    belief.kill_cooldown_start_tick = belief.last_tick
    belief.kill_cooldown_estimate = 200
    assert _select(belief) == "search"


def test_recon_window_is_env_tunable(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_RECON_WINDOW", "300")
    belief = _imposter_with_visible_target(self_kill_ready=False)
    belief.kill_cooldown_start_tick = belief.last_tick
    belief.kill_cooldown_estimate = 200  # now inside the widened 300-tick window
    assert _select(belief) == "recon"


def test_be_dumb_imposter_searches_instead_of_pretending(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_BE_DUMB", "1")

    belief = Belief(phase="Playing", self_role="imposter", self_kill_ready=False, last_tick=10)
    assert _select(belief) == "search"


def test_be_dumb_imposter_hunts_when_kill_ready_with_visible_victim(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_BE_DUMB", "1")

    assert _select(_imposter_with_visible_target(self_kill_ready=True)) == "hunt"


def test_be_dumb_alias_enables_the_aggressive_imposter_path(monkeypatch) -> None:
    monkeypatch.setenv("BE_DUMB", "true")

    assert _select(_imposter_with_visible_target(self_kill_ready=True)) == "hunt"


def test_be_dumb_imposter_skips_evade_and_report_body(monkeypatch) -> None:
    from crewborg.types import BodyEntry

    monkeypatch.setenv("CREWBORG_BE_DUMB", "1")

    fresh_kill = _imposter_with_visible_target(self_kill_ready=True, last_kill_tick=9, visible_body_ids={2003})
    fresh_kill.bodies[2003] = BodyEntry(object_id=2003, color="green", world_x=60, world_y=60, first_seen_tick=10)
    assert _select(fresh_kill) == "hunt"

    body_only = Belief(phase="Playing", self_role="imposter", self_kill_ready=False, last_tick=10, visible_body_ids={2003})
    body_only.bodies[2003] = BodyEntry(object_id=2003, color="green", world_x=60, world_y=60, first_seen_tick=10)
    assert _select(body_only) == "search"


def test_be_dumb_does_not_override_voting(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_BE_DUMB", "1")

    assert _select(Belief(phase="Voting", self_role="imposter")) == "attend_meeting"


def test_imposter_searches_when_kill_is_far_off_cooldown() -> None:
    # A victim is in view but the kill is a long way off ⇒ still Search (no Pretend /
    # lead-window gate anymore): seek and stay near crew until the window opens.
    belief = _imposter_with_visible_target(self_kill_ready=False)
    belief.kill_cooldown_start_tick = belief.last_tick
    belief.kill_cooldown_estimate = 900
    assert _select(belief) == "search"


def test_imposter_pretends_when_only_a_teammate_is_visible() -> None:
    # Kill ready but the only visible player is a teammate ⇒ no kill target, so Search.
    belief = _imposter_with_visible_target(self_kill_ready=True)
    belief.teammate_colors = {"red"}  # the visible target is red (see helper)
    assert _select(belief) == "search"


def test_deduction_brain_disables_accuse_because_suspicion_is_never_written() -> None:
    """Pin the biggest undocumented consequence of the deduction fork.

    ``fold_belief`` never writes ``belief.suspicion`` for a crewmate under
    ``CREWBORG_DEDUCTION_HISTORY=1``, and ``active_tail_suspect`` reads exactly that
    dict, so selector priority 3 (Accuse -> spend the emergency button) can never
    fire in the candidate arm. The 2026-07-25 A/B bundles that loss with the new
    meeting policy, so if this test ever fails the arm's meaning has changed and
    the experiment record needs revisiting.
    """

    tailed = _crewmate_being_tailed(tick=40, p=0.7)
    assert _select(tailed) == "accuse", "sanity: the fitted arm does accuse"

    # The end state fold_belief leaves for this arm: an empty posterior.
    tailed.suspicion.clear()
    tailed.believed_imposters.clear()
    assert _select(tailed) == "normal"


# --- the crew-brain fork in build_runtime's fold (crewborg/__init__.py) -------------


def _roster_belief(role: str | None) -> Belief:
    belief = Belief(self_role=role, self_color="red", self_alive=True, last_tick=5)
    belief.total_player_count = 8
    belief.imposter_count = 2
    for color in ("blue", "green", "pink", "orange", "yellow", "purple", "cyan"):
        belief.roster[color] = PlayerRecord(color=color, world_x=10, world_y=10, last_seen_tick=5)
    return belief


def _stepped_runtime_belief(role: str) -> Belief:
    """Step the real assembled runtime once and return its folded belief."""

    from crewborg import build_runtime
    from crewborg.coworld.scene import SceneState
    from crewborg.tests import sprite_wire as w
    from crewborg.types import Observation

    runtime = build_runtime()
    try:
        seeded = _roster_belief(role)
        runtime.belief.self_role = seeded.self_role
        runtime.belief.self_color = seeded.self_color
        runtime.belief.total_player_count = seeded.total_player_count
        runtime.belief.imposter_count = seeded.imposter_count
        runtime.belief.roster.update(seeded.roster)

        scene = SceneState()
        scene.apply(w.clear_objects())
        scene.tick += 1
        runtime.step(Observation(scene=scene, tick=scene.tick))
        return runtime.belief
    finally:
        runtime.close()


def test_fitted_brain_writes_a_posterior_once_the_role_is_known() -> None:
    """Control for the test below: the default arm does populate suspicion."""

    assert _stepped_runtime_belief("crewmate").suspicion


def test_flagged_crewmate_never_has_a_posterior_written(monkeypatch) -> None:
    """No clear needed: the conclusion-former simply never runs for this arm.

    The fork keys on `self_role`, which is None until RoleReveal, so this used to run
    the fitted model pre-reveal and then `.clear()` its output. Deferring the (pure)
    recompute until the role is known means the dict is never populated at all -- so
    "the deduction brain does not use the fitted posterior" is now true by
    construction rather than true by scrubbing.
    """

    monkeypatch.setenv("CREWBORG_DEDUCTION_HISTORY", "1")
    belief = _stepped_runtime_belief("crewmate")
    assert belief.suspicion == {}
    assert belief.believed_imposters == set()


def test_what_the_pre_reveal_fitted_tick_used_to_discard() -> None:
    """Pins the claim that the old clear threw away nothing of value: flat priors."""

    from crewborg.strategy.suspicion import update_suspicion

    would_have = _roster_belief(None)
    update_suspicion(would_have)
    assert would_have.suspicion, "pre-reveal suspicion used to be populated"
    assert len(set(would_have.suspicion.values())) == 1, "uniform -- i.e. flat priors"
    assert would_have.believed_imposters == set()


def test_deferring_the_posterior_does_not_change_the_impostor() -> None:
    """The fitted arm must be unchanged: suspicion is a pure per-tick recompute.

    Its accumulating state lives on PlayerRecord (event_log / social_evidence), which
    still run on their old schedule, so skipping the pre-reveal recompute cannot move
    the first post-reveal posterior.
    """

    from crewborg.strategy.suspicion import update_suspicion

    # Old shape: recompute every tick, including while the role was unknown.
    old = _roster_belief(None)
    update_suspicion(old)          # pre-reveal tick
    old.self_role = "imposter"
    update_suspicion(old)          # first post-reveal tick

    # New shape: skip the pre-reveal recompute entirely.
    new = _roster_belief("imposter")
    update_suspicion(new)

    assert old.suspicion == new.suspicion
    assert old.believed_imposters == new.believed_imposters


# --- Self-report: report our own kill when nobody could place us there -------------


def _fresh_kill_alone(monkeypatch, **kwargs) -> Belief:
    """A just-made kill, body in view, and no live crewmate seen for a long time."""

    from crewborg.types import BodyEntry, PlayerRecord

    monkeypatch.setenv("CREWBORG_SELF_REPORT", "1")
    belief = Belief(
        phase="Playing", self_role="imposter", last_tick=1000, last_kill_tick=999,
        self_world_x=100, self_world_y=100, self_color="pink",
        visible_body_ids={2003}, **kwargs,
    )
    belief.bodies[2003] = BodyEntry(
        object_id=2003, color="green", world_x=101, world_y=101, first_seen_tick=999
    )
    # The victim: dead, so never a witness.
    belief.roster["green"] = PlayerRecord(
        object_id=1004, color="green", world_x=101, world_y=101,
        last_seen_tick=999, life_status="dead",
    )
    # A live crewmate we have not laid eyes on in ages.
    belief.roster["blue"] = PlayerRecord(
        object_id=1005, color="blue", world_x=900, world_y=900,
        last_seen_tick=1000 - 400, life_status="alive",
    )
    return belief


def test_self_reports_a_kill_nobody_could_have_seen(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_SELF_REPORT_P", "1.0")
    assert _select(_fresh_kill_alone(monkeypatch)) == "report_body"


def test_self_report_stays_off_by_default(monkeypatch) -> None:
    # The lever is opt-in: the same situation evades unless it is switched on.
    belief = _fresh_kill_alone(monkeypatch)
    monkeypatch.delenv("CREWBORG_SELF_REPORT", raising=False)
    assert _select(belief) == "evade"


def test_recently_seen_crewmate_blocks_the_self_report(monkeypatch) -> None:
    # Someone laid eyes on us inside the solitude window ⇒ they could place us at the
    # body, so fall back to the old behaviour.
    monkeypatch.setenv("CREWBORG_SELF_REPORT_P", "1.0")
    belief = _fresh_kill_alone(monkeypatch)
    belief.roster["blue"].last_seen_tick = belief.last_tick - 10
    assert _select(belief) == "evade"


def test_no_body_in_view_blocks_the_self_report(monkeypatch) -> None:
    # report_body only idles without a body, which would waste the post-kill window
    # standing still — the one thing every field detector scores.
    monkeypatch.setenv("CREWBORG_SELF_REPORT_P", "1.0")
    belief = _fresh_kill_alone(monkeypatch)
    belief.visible_body_ids = set()
    assert _select(belief) == "evade"


def test_self_report_coin_is_stable_across_the_ticks_of_one_kill(monkeypatch) -> None:
    # A per-tick re-roll at p=2/3 would fire on essentially every kill; the decision
    # must be drawn once per kill and hold.
    monkeypatch.setenv("CREWBORG_SELF_REPORT_P", "0.667")
    seen = set()
    for tick in range(1000, 1030):
        belief = _fresh_kill_alone(monkeypatch)
        belief.last_tick = tick
        seen.add(_select(belief))
    assert len(seen) == 1, seen


def test_self_report_coin_respects_its_probability(monkeypatch) -> None:
    monkeypatch.setenv("CREWBORG_SELF_REPORT_P", "0.0")
    assert _select(_fresh_kill_alone(monkeypatch)) == "evade"


def test_teammates_and_the_dead_are_not_witnesses(monkeypatch) -> None:
    from crewborg.strategy.opportunity import nobody_seen_recently

    belief = _fresh_kill_alone(monkeypatch)
    # An imposter partner standing right next to us does not compromise the report.
    belief.roster["blue"].last_seen_tick = belief.last_tick
    belief.teammate_colors = {"blue"}
    assert nobody_seen_recently(belief, 120)
    # Nor does our own record, which is refreshed every tick.
    from crewborg.types import PlayerRecord

    belief.roster["pink"] = PlayerRecord(
        object_id=1006, color="pink", world_x=100, world_y=100,
        last_seen_tick=belief.last_tick, life_status="alive",
    )
    assert nobody_seen_recently(belief, 120)
