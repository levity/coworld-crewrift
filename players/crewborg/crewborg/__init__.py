"""Crewborg — a Player-SDK agent that plays Crewrift.

``build_runtime`` assembles the ``AgentRuntime`` from crewborg's six type
parameters, three pure functions, modes, and the rule-based strategy. See
``design.md`` for the full architecture and ``AGENTS.md`` for orientation.
"""

from __future__ import annotations

import os
from typing import Protocol

from crewborg.agent_tracking import update_agent_tracking
from crewborg.action import resolve_action
from crewborg.deduction.collector import update_deduction_history
from crewborg.deduction.config import enabled_for_role as deduction_history_enabled
from crewborg.events import CrewborgEventTracer
from crewborg.map import MapData, load_croatoan_map
from crewborg.modes import (
    AccuseMode,
    AttendMeetingMode,
    EvadeMode,
    HuntMode,
    IdleMode,
    NormalMode,
    ReconMode,
    ReportBodyMode,
    SearchMode,
    SelfPreservationMode,
)
from crewborg.strategy import (
    RuleBasedStrategy,
    update_event_log,
    update_social_evidence,
    update_suspicion,
)
from crewborg.strategy.commander.llm import build_commander_client_from_env, commander_feature_enabled
from crewborg.strategy.commander.strategy import CommanderStrategy, apply_commander_inferences
from crewborg.strategy.commander.trace import CommanderTrace
from crewborg.strategy.commander.worker import CommanderWorker
from crewborg import nlp as chat_nlp
from crewborg.types import (
    ActionState,
    Belief,
    Command,
    Intent,
    Observation,
    Percept,
    perceive,
    update_belief,
)
from players.player_sdk import (
    AgentRuntime,
    MetricsSink,
    ModeDirective,
    ModeRegistry,
    SynchronousStrategyRunner,
    TraceSink,
)

__all__ = ["build_runtime"]


class _CloseableStrategy(Protocol):
    def close(self) -> None: ...


class CloseAwareSynchronousStrategyRunner(SynchronousStrategyRunner[Belief, ActionState]):
    """Sync runner that also closes the wrapped strategy if it owns resources."""

    def __init__(self, strategy: _CloseableStrategy, **kwargs) -> None:
        super().__init__(strategy, **kwargs)
        self._closeable_strategy = strategy

    def close(self) -> None:
        self._closeable_strategy.close()
        super().close()


def build_runtime(
    *,
    trace_sink: TraceSink | None = None,
    metrics_sink: MetricsSink | None = None,
    map_data: MapData | None = None,
) -> AgentRuntime[Observation, Percept, Belief, ActionState, Intent, Command]:
    """Assemble the crewborg ``AgentRuntime``.

    The inner loop runs ``perceive -> update_belief (+ agent tracking + event log
    + suspicion) -> mode.decide -> resolve_action`` each tick; the rule-based
    strategy publishes mode directives via ``SynchronousStrategyRunner``. The
    per-agent location tracker, per-player event log (design §5.2), and suspicion
    scoring (§10.1) are folded into belief right after perception so the strategy
    snapshot sees current search and ``believed_imposters`` state. The static map
    is baked once here (design §6) — ``map_data`` overrides the vendored
    ``croatoan`` bake (tests).
    Registers all modes: idle / normal / attend_meeting / report_body / accuse
    (crewmate) and evade / pretend / search / hunt (imposter). A ``CrewborgEventTracer``
    is wired as the runtime's ``on_step_complete`` hook so crewborg emits its
    ``domain.*`` trace events through the configured sinks (design §11): the
    phase / sighting / objective / kill / vote outcomes *and* the knowledge layer
    behind them (per-player event log + suspicion posteriors, with a
    ``suspicion_snapshot`` each meeting). ``CREWBORG_TRACE=debug`` adds the full
    per-tick dump; ``CREWBORG_TRACE_GROUPS`` / ``CREWBORG_TRACE_INCLUDE`` can
    target narrower event families without full debug volume.
    """

    # Kick off the spaCy chat-NLP model load in the background now (gated by
    # CREWBORG_CHAT_NLP), so the ~1.5-2s load overlaps the pre-game idle phases and is
    # ready before the first meeting — never on the gameplay hot path (design §10.5).
    chat_nlp.ensure_loading()

    registry: ModeRegistry[Belief, ActionState, Intent] = ModeRegistry()
    registry.register(IdleMode)
    registry.register(NormalMode)
    registry.register(AttendMeetingMode)
    registry.register(ReportBodyMode)
    registry.register(AccuseMode)
    registry.register(EvadeMode)
    registry.register(HuntMode)
    registry.register(ReconMode)
    registry.register(SearchMode)
    registry.register(SelfPreservationMode)

    if map_data is None:
        map_data = load_croatoan_map()

    def fold_belief(belief: Belief, percept: Percept) -> None:
        """Fold perception into exactly ONE of crewborg's two crew brains.

        This is the only place the choice is made, and it is exclusive: a crewmate
        runs the append-only deduction path or the fitted-posterior path, never both.

        **What choosing the deduction brain also turns off.** `belief.suspicion` and
        `belief.believed_imposters` stay empty, and they are the input to three shipped
        crewmate behaviours, so all three go inert:

        1. **Accuse** (`modes/accuse.py`, selector priority 3) can never fire — no
           suspect ever crosses `ACCUSE_THRESHOLD`, so the emergency button is never
           spent. This is a large behavioural difference, not a bookkeeping detail: in
           the 2026-07-25 A/B the fitted arm pressed the button 80 times in 40 games and
           abandoned a task each time, and disabling that is the leading explanation for
           the +21pp win (`docs/experiments/2026-07-25-deduction-architecture-hosted-ab.md`).
        2. **Escort suspect-avoidance** (`modes/normal.py:_suspect_points`) sees no
           suspects, so the retained escort/witness experiments stop steering clear.
        3. **The deterministic meeting fallback** has no `top_suspect` to fall back to,
           which is why `_fallback_vote_target` just skips.

        Keeping these coupled is deliberate for now — one flag, one arm — but it means
        the A/B measures the architecture AND the loss of Accuse together. Decomposing
        that is the standing next step in `HANDOFF.md`.

        **Why the conclusion stage waits for the role.** The fork keys on
        `belief.self_role`, which is `None` until the RoleReveal interstitial renders
        `IMPS`/`CREWMATE` — so the pre-reveal ticks cannot know which brain they belong
        to. The split below is by *kind of work* rather than by tick:

        - `update_event_log` / `update_social_evidence` **accumulate observations** onto
          `PlayerRecord` (proximity, dwell, `seen_ticks`, chat stances, ballots). The
          impostor's fitted `observed_samples` feature depends on these running from
          tick 0, so they keep exactly their old schedule.
        - `update_suspicion` is the only **conclusion-former** (the posterior and
          `believed_imposters`), and it is a *pure recompute* from those accumulators
          every tick — it holds no state of its own. So deferring it until the role is
          known costs nothing: the first post-reveal posterior is rebuilt identically.

        That deferral is what lets a flagged crewmate simply never have a suspicion dict
        written.
        """

        update_belief(belief, percept)
        update_agent_tracking(belief)
        if deduction_history_enabled(belief.self_role):
            update_deduction_history(belief, percept)
        else:
            update_event_log(belief)
            update_social_evidence(belief)
            # Nothing reads the posterior before the role is known (the selector idles
            # outside Playing/Voting), and it is a pure recompute, so waiting is free.
            if belief.self_role is not None:
                update_suspicion(belief)

    commander_trace = CommanderTrace()
    feature_on = commander_feature_enabled(dict(os.environ))
    commander_strategy = CommanderStrategy(
        RuleBasedStrategy(),
        CommanderWorker(build_commander_client_from_env, trace=commander_trace),
        feature_enabled=feature_on,
    )

    return AgentRuntime(
        belief=Belief(map=map_data),
        action_state=ActionState(),
        perceive=perceive,
        update_belief=fold_belief,
        resolve_action=resolve_action,
        mode_registry=registry,
        default_directive=ModeDirective(mode="idle", source="default", reason="default idle"),
        strategy_runner=CloseAwareSynchronousStrategyRunner(
            commander_strategy,
            trace_sink=trace_sink,
            metrics_sink=metrics_sink,
        ),
        apply_inferences=apply_commander_inferences,
        on_step_complete=CrewborgEventTracer(commander_trace=commander_trace),
        trace_sink=trace_sink,
        metrics_sink=metrics_sink,
    )
