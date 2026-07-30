"""Attend Meeting mode: conversational chat plus deadline-safe voting."""

from __future__ import annotations

import math
from collections import Counter
from time import perf_counter
from typing import Any

from players.player_sdk import EmptyModeParams, Mode

from crewborg import nlp as chat_nlp
from crewborg.deduction.collector import history_from_belief
from crewborg.deduction.config import enabled_for_role as deduction_history_enabled
from crewborg.deduction.config import gate_overrides, inference_overrides
from crewborg.deduction.consult import ConsultView, resolve_consult, run_consult
from crewborg.deduction.decision import DecisionConfig
from crewborg.deduction.decision import MeetingDecision as DeductionMeetingDecision
from crewborg.deduction.decision import decide as decide_from_history
from crewborg.deduction.inference import InferenceConfig
from crewborg.deduction.model import DeductionHistory
from crewborg.strategy.meeting import (
    CHAT_MAX_CHARS,
    VOTE_SKIP,
    MeetingDecision,
    MeetingDecisionValidationError,
    MeetingLLMClient,
    build_meeting_llm_client_from_env,
    chat_read,
    sanitize_chat,
    serialize_meeting_context,
    valid_vote_targets,
    validate_meeting_decision,
)
from crewborg.strategy.meeting.accusation import build_accusation, fabricate_accusation
from crewborg.strategy.meeting.context import (
    CHAT_COOLDOWN_TICKS,
    effective_vote_timer_ticks,
)
from crewborg.strategy.meeting.imposter import (
    bandwagon_target,
    parity_closing_vote_target,
    votes_against,
)
from crewborg.strategy.suspicion import chat_suspect, top_suspect
from crewborg.types import ActionState, Belief, ChatEvent, Intent

LLM_MIN_CALL_INTERVAL_TICKS = 12
DEADLINE_LLM_REMAINING_TICKS = 96
AUTO_SUBMIT_REMAINING_TICKS = 48
MEETING_TICKS_PER_SECOND = 24
LLM_TIMEOUT_MARGIN_TICKS = LLM_MIN_CALL_INTERVAL_TICKS
DEFAULT_LLM_TIMEOUT_SECONDS = 3.0
DEDUCTION_EARLY_CHAT_TICKS = 240


class AttendMeetingMode(Mode[Belief, ActionState, Intent]):
    name = "attend_meeting"
    params_type = EmptyModeParams

    def __init__(self, params=None, *, llm_client: MeetingLLMClient | None = None) -> None:
        super().__init__(params)
        self._llm_client = llm_client if llm_client is not None else build_meeting_llm_client_from_env()
        self._meeting_id: int | None = None
        self._deterministic_chatted = False
        self._disabled_traced = False
        self._sent_chat_texts: set[str] = set()
        self._pending_chat_text: str | None = None
        self._last_chat_tick: int | None = None
        self._last_llm_call_tick: int | None = None
        self._last_external_chat_signature: tuple[tuple[int, str | None, str], ...] = ()
        self._last_cooldown_prompt_chat_tick: int | None = None
        self._deadline_prompted = False
        self._tentative_vote: str | None = None
        self._active_vote_target: str | None = None
        self._active_vote_reason: str = ""
        self._vote_submitted = False
        self._chat_parse_cache: dict[str, set[str]] = {}
        self._decision_traced = False
        self._deduction_early_chat_attempted = False
        self._deduction_finalized = False
        # The meeting's history, rebuilt only when the ledger actually grows.
        # `history_from_belief` revalidates every retained event through pydantic
        # (~6 ms at 10k events, ~26 ms at 20k, against a 41.7 ms tick budget) and
        # `decide` runs on EVERY voting tick while solving only twice.
        self._history: DeductionHistory | None = None
        self._history_key: tuple | None = None
        # Resolve both env-selected presets once, here at the runtime boundary, so the
        # pure inference and decision stages never read the environment. They are
        # deliberately separate vars: CREWBORG_SPEAKER_TRUST changes the posterior,
        # CREWBORG_DECISION_GATE changes what we do with it, and bundling them would
        # make an A/B uninterpretable (see deduction/config.py).
        self._decision_config = DecisionConfig(**gate_overrides())
        self._inference_config = InferenceConfig(**inference_overrides())

    def is_legal(self, belief: Belief) -> bool:
        return belief.phase == "Voting"

    def decide(self, belief: Belief, action_state: ActionState) -> Intent:
        self._reset_for_meeting_if_needed(belief)
        if action_state.vote_confirmed:
            self._vote_submitted = True
            self._active_vote_target = None
            self._active_vote_reason = ""
        if self._vote_submitted:
            return Intent(kind="idle", reason="vote already confirmed")
        if self._active_vote_target is not None:
            return self._vote_intent(self._active_vote_target, reason=self._active_vote_reason)

        if deduction_history_enabled(belief.self_role):
            return self._decide_from_deduction_history(belief)

        if not self._llm_client.enabled:
            return self._decide_deterministic(belief, trace_disabled=True)

        if self._should_auto_submit(belief):
            return self._submit_vote_intent(belief, reason="meeting deadline: auto-submit tentative vote")

        if self._pending_chat_text is not None and self._chat_cooldown_ready(belief):
            return self._send_chat_intent(belief, self._pending_chat_text, reason="sending pending LLM chat")

        trigger = self._next_llm_trigger(belief)
        if trigger is None:
            return Intent(kind="idle", reason="waiting during meeting")

        context = serialize_meeting_context(
            belief,
            trigger=trigger,
            tentative_vote=self._tentative_vote,
            sent_chat_texts=self._sent_chat_texts,
            last_chat_tick=self._last_chat_tick,
        )
        self.emit.event("meeting_context_serialized", {"trigger": trigger, "context": context})
        result = self._call_llm(context, trigger=trigger)
        if result is None:
            return self._decide_after_llm_failure(belief, trigger)
        decision = self._validate_decision(belief, result.decision)
        if decision is None:
            return self._decide_after_llm_failure(belief, trigger)
        self._trace_decision(trigger, decision, result)
        return self._apply_decision(belief, decision)

    # --- deduction brain (CREWBORG_DEDUCTION_HISTORY, crew only) -----------

    def _current_history(self, belief: Belief) -> DeductionHistory | None:
        """This meeting's frozen history, rebuilt only when the ledger grows."""

        # Key on EVERYTHING `history_from_belief` reads, not just the ledger length:
        # the roster can still grow from the voting panel during a quiet meeting, and
        # a count-only key would freeze a too-small `GameSpec.players` for the whole
        # meeting -- which the old per-tick rebuild picked up.
        key = (
            len(belief.deduction_events),
            len(belief.roster),
            belief.imposter_count,
            belief.total_player_count,
            belief.self_color or belief.voting.self_marker_color,
        )
        if self._history is None or key != self._history_key:
            self._history = history_from_belief(belief)
            self._history_key = key
        return self._history

    def _decide_from_deduction_history(self, belief: Belief) -> Intent:
        """Use only the append-only history, waiting until the deadline to vote."""

        history = self._current_history(belief)
        if history is None:
            if self._should_auto_submit(belief):
                self._tentative_vote = VOTE_SKIP
                return self._submit_vote_intent(
                    belief,
                    reason="deduction history unavailable at deadline",
                )
            return Intent(kind="idle", reason="waiting for deduction history")

        live_targets = tuple(sorted(valid_vote_targets(belief)))
        meeting_age = belief.last_tick - belief.phase_start_tick
        if (
            not self._deduction_early_chat_attempted
            and meeting_age >= DEDUCTION_EARLY_CHAT_TICKS
        ):
            self._deduction_early_chat_attempted = True
            solve_started = perf_counter()
            early = decide_from_history(
                history,
                live_targets=live_targets,
                inference_config=self._inference_config,
                decision_config=self._decision_config,
            )
            solve_ms = (perf_counter() - solve_started) * 1000
            self.emit.event(
                "deduction_history_early",
                self._deduction_trace(
                    belief,
                    history,
                    early,
                    solve_ms=solve_ms,
                    include_factor_table=False,
                ),
            )
            text = self._deduction_chat(
                early,
                live_targets=live_targets,
                allow_clear=True,
            )
            if text is not None and self._chat_cooldown_ready(belief):
                return self._send_chat_intent(
                    belief,
                    text,
                    reason="sharing early append-only deduction",
                )

        # WHEN TO FINALISE. Off: at the 48-tick auto-submit backstop, consuming the most
        # chat possible. On: earlier, because an LLM call may only start while it can
        # still finish before that backstop -- so the solve moves forward to leave room
        # for the consult that reads it. See `deduction.config.llm_enabled` for the cost.
        llm_last = self._deduction_llm_active()
        finalize_at = (
            self._deduction_llm_trigger_remaining()
            if llm_last
            else AUTO_SUBMIT_REMAINING_TICKS
        )
        if self._remaining_ticks(belief) > finalize_at and not self._should_auto_submit(belief):
            return Intent(
                kind="idle",
                reason="gathering complete meeting transcript before deduction",
            )
        if self._deduction_finalized:
            if not self._should_auto_submit(belief):
                # Finalised early for the consult; hold the staged vote until the
                # backstop rather than voting ahead of the deterministic schedule.
                return Intent(kind="idle", reason="deduction decided; holding until backstop")
            return self._submit_vote_intent(
                belief,
                reason="append-only deduction vote",
            )

        solve_started = perf_counter()
        final = decide_from_history(
            history,
            live_targets=live_targets,
            inference_config=self._inference_config,
            decision_config=self._decision_config,
        )
        solve_ms = (perf_counter() - solve_started) * 1000
        self._deduction_finalized = True
        deterministic_vote = (
            final.target
            if final.action == "eject" and final.target is not None
            else VOTE_SKIP
        )
        self._tentative_vote = deterministic_vote
        self.emit.event(
            "deduction_history_decision",
            self._deduction_trace(
                belief,
                history,
                final,
                solve_ms=solve_ms,
                include_factor_table=True,
            ),
        )
        text = self._deduction_chat(
            final,
            live_targets=live_targets,
            allow_clear=False,
        )

        # THE LAST STEP OF THE BRANCH, when the toggle is on. The LLM sees the deduction
        # posterior and the conclusion it produced, and casts the final vote -- it may
        # confirm or depart from the solver. Every downgrade lands back on
        # `deterministic_vote`: the client disabled, no time to start, a raised call, an
        # invalid decision. So "on" can only ever change the vote via a decision that
        # passed the same validator the LLM path has always used.
        if llm_last:
            self._tentative_vote, llm_text = self._deduction_llm_vote(
                belief,
                final,
                history=history,
                deterministic_vote=deterministic_vote,
            )
            if llm_text:
                text = llm_text
        if (
            text is not None
            and text not in self._sent_chat_texts
            and self._chat_cooldown_ready(belief)
        ):
            return self._send_chat_intent(
                belief,
                text,
                reason="sharing final append-only deduction",
            )
        return self._submit_vote_intent(
            belief,
            reason=f"append-only deduction: {final.reason}",
        )

    def _deduction_llm_active(self) -> bool:
        return resolve_consult() is not None and self._llm_client.enabled

    def _deduction_llm_trigger_remaining(self) -> int:
        """Finalise as late as the deadline math allows, plus a second of slack.

        `_can_start_llm_call` is a strict `remaining > floor`, so triggering AT the floor
        could never start a call. The slack is a full second rather than one margin
        because the window is otherwise only `LLM_TIMEOUT_MARGIN_TICKS` wide: if the mode
        is not called for a few ticks -- scheduling lag, a slow perception frame -- the
        remaining count steps straight past a narrow window and the consult is skipped
        with nothing but a fallback trace to show for it. A second of slack costs ~12
        extra ticks of unread chat and makes the trigger robust to that.
        """

        return self._latest_safe_llm_start_remaining_ticks() + MEETING_TICKS_PER_SECOND

    def _deduction_llm_vote(
        self,
        belief: Belief,
        decision: DeductionMeetingDecision,
        *,
        history: DeductionHistory,
        deterministic_vote: str,
    ) -> tuple[str, str | None]:
        """Hand the solved board to the configured consult and take its vote.

        Returns `(vote, chat_text_or_None)`. This method holds NO experiment logic: which
        consult runs, what it is shown, what shape its answer must take and when its
        answer is accepted all live in `deduction/consult/`. That is deliberate -- the
        next idea for what the LLM is for should be a new module there and an env value,
        not an edit to the meeting mode.

        Never raises; `run_consult` returns the deterministic vote on every failure path,
        so the branch degrades to exactly its toggle-off behaviour.
        """

        consult = resolve_consult()
        if consult is None:
            return deterministic_vote, None
        view = ConsultView.from_deduction(
            decision,
            history=history,
            legal_targets=valid_vote_targets(belief),
            meeting_id=belief.phase_start_tick,
            tick=belief.last_tick,
        )
        outcome = run_consult(
            consult,
            view,
            client=self._llm_client,
            emit=self.emit.event,
            can_start=lambda: self._can_start_llm_call(belief),
        )
        chat = sanitize_chat(outcome.chat) or None
        if chat is not None and chat in self._sent_chat_texts:
            chat = None
        return outcome.vote, chat

    def _deduction_trace(
        self,
        belief: Belief,
        history: DeductionHistory,
        decision: DeductionMeetingDecision,
        *,
        solve_ms: float,
        include_factor_table: bool,
    ) -> dict[str, Any]:
        history_counts = Counter(event.kind for event in history.events)
        active_counts = Counter(
            evidence.channel
            for evidence in decision.inference.evidence
            if evidence.status == "active"
        )
        payload: dict[str, Any] = {
            "meeting_age_ticks": belief.last_tick - belief.phase_start_tick,
            "remaining_ticks": self._remaining_ticks(belief),
            "solve_ms": round(solve_ms, 3),
            "history_event_count": len(history.events),
            "history_event_counts": dict(sorted(history_counts.items())),
            "active_evidence_counts": dict(sorted(active_counts.items())),
            "decision": decision.as_trace(),
        }
        if include_factor_table:
            payload["factor_table"] = decision.inference.as_factor_trace()
        return payload

    def _deduction_chat(
        self,
        decision: DeductionMeetingDecision,
        *,
        live_targets: tuple[str, ...],
        allow_clear: bool,
    ) -> str | None:
        target = decision.target
        if decision.action == "eject" and target is not None:
            if target in decision.inference.pins:
                return f"saw {target} kill or vent. vote {target}"
            if decision.structural:
                return f"{target} is forced by the remaining pairs. vote {target}"
            sources = " and ".join(decision.sources[:2])
            if sources:
                return f"{sources} both point to {target}. vote {target}"
            return f"combined evidence points to {target}. vote {target}"
        if not allow_clear or decision.inference.error is not None:
            return None
        active_evidence = any(
            item.status == "active"
            for item in decision.inference.evidence
        )
        if not active_evidence:
            return None
        live_marginals = [
            (color, probability)
            for color, probability in decision.inference.marginals
            if color in live_targets
            and color not in decision.inference.murder_clears
        ]
        if not live_marginals:
            return None
        clear, probability = min(live_marginals, key=lambda item: (item[1], item[0]))
        if probability > 0.10:
            return None
        return f"{clear} looks clear from the combined evidence"

    # --- deterministic fallback (fitted posterior; used when the LLM is off) ---

    def _decide_deterministic(self, belief: Belief, *, trace_disabled: bool) -> Intent:
        """No default-firing chat; chat and vote are always coupled (accuse exactly who
        we vote — the anti-tell). The two roles diverge here (design §10.4)."""

        if trace_disabled and not self._disabled_traced:
            self._disabled_traced = True
            self.emit.event(
                "meeting_llm_fallback",
                {"reason": "llm_disabled", "detail": self._llm_client.disabled_reason},
            )
        if belief.self_role == "imposter":
            return self._decide_imposter(belief)
        return self._decide_crewmate(belief)

    def _decide_crewmate(self, belief: Belief) -> Intent:
        """Accuse + vote a clear leading suspect; else SHARE a read on a softer suspect
        (chat only, no vote) rather than going silent — vote restraint is unchanged."""

        if not self._deterministic_chatted:
            self._deterministic_chatted = True
            target = top_suspect(belief)  # the clear leading suspect, or None (flat field)
            if target is not None:
                self._tentative_vote = target  # couple the vote to whoever we accuse
                accusation = build_accusation(belief, target)
                if accusation is not None:
                    self._trace_meeting_decision(belief, role="crewmate", path="accuse", target=target)
                    return self._send_chat_intent(belief, accusation, reason="accusing clear suspect")
                self._trace_meeting_decision(belief, role="crewmate", path="vote_no_chat", target=target)
            else:
                # No clear suspect to VOTE — but voice an evidence-cited read instead of
                # going silent (chat only; we still skip the vote on a thin field).
                soft = chat_suspect(belief)
                read = build_accusation(belief, soft) if soft is not None else None
                if read is not None:
                    self._trace_meeting_decision(belief, role="crewmate", path="share_read", target=soft)
                    return self._send_chat_intent(belief, read, reason="sharing read (no vote)")
                self._trace_meeting_decision(belief, role="crewmate", path="silent_skip", target=None)
        return self._submit_vote_intent(belief, reason="deterministic meeting vote")

    def _decide_imposter(self, belief: Belief) -> Intent:
        """Deflect onto crewmates, never teammates. Prefer a **real** accusation against
        a non-teammate who genuinely looks sus; otherwise wait and **bandwagon** onto a
        crewmate others are sussing/voting, with *fabricated* (safe) evidence in the
        identical format; if nobody takes heat, skip at the deadline."""

        # Already accused someone ⇒ stay coupled: vote exactly them.
        if self._deterministic_chatted and self._tentative_vote is not None:
            return self._submit_vote_intent(belief, reason="imposter: vote whom we accused")

        # 1. Proactive deflection — a non-teammate with strong, real citable evidence.
        target = top_suspect(belief)
        if target is not None:
            accusation = build_accusation(belief, target)
            if accusation is not None:
                self._tentative_vote = target
                self._deterministic_chatted = True
                self._trace_meeting_decision(belief, role="imposter", path="proactive", target=target)
                return self._send_chat_intent(belief, accusation, reason="imposter deflect: real evidence")

        # 2. Reactive bandwagon — a crewmate already taking heat (votes + chat).
        accusers = self._chat_accusers(belief)
        bandwagon = bandwagon_target(belief, accusers)
        if bandwagon is not None:
            self._tentative_vote = bandwagon
            self._deterministic_chatted = True
            fabricated = fabricate_accusation(belief, bandwagon)
            self._trace_meeting_decision(
                belief, role="imposter", path="bandwagon", target=bandwagon,
                fabricated=fabricated is not None, accusers=accusers,
            )
            if fabricated is not None:
                return self._send_chat_intent(belief, fabricated, reason="imposter bandwagon: fabricated")
            return self._submit_vote_intent(belief, reason="imposter bandwagon vote")

        # 3. Parity-closing push — one removal from a win and no crewmate is taking
        #    heat on their own, so MANUFACTURE the pile instead of skipping it away
        #    (the dominant imposter loss is stalling at 3-crew/2-imp; design §10.4).
        parity_target = parity_closing_vote_target(belief, accusers)
        if parity_target is not None:
            self._tentative_vote = parity_target
            self._deterministic_chatted = True
            fabricated = fabricate_accusation(belief, parity_target)
            self._trace_meeting_decision(
                belief, role="imposter", path="parity_push", target=parity_target,
                fabricated=fabricated is not None, accusers=accusers,
            )
            if fabricated is not None:
                return self._send_chat_intent(belief, fabricated, reason="imposter parity push: fabricated")
            return self._submit_vote_intent(belief, reason="imposter parity push vote")

        # 4. No one to deflect onto yet — wait, then skip at the deadline.
        if self._should_auto_submit(belief):
            self._trace_meeting_decision(belief, role="imposter", path="skip", target=None, accusers=accusers)
            return self._submit_vote_intent(belief, reason="imposter deadline: no deflection, skip")
        return Intent(kind="idle", reason="imposter waiting for a crewmate to take heat")

    def _trace_meeting_decision(
        self,
        belief: Belief,
        *,
        role: str,
        path: str,
        target: str | None,
        fabricated: bool = False,
        accusers: dict[str, int] | None = None,
    ) -> None:
        """One structured record of the deterministic meeting decision, fired once when
        we commit. The headline diagnostic for the new meeting modes: which path
        (accuse / silent_skip · proactive / bandwagon / skip), the target, real vs
        fabricated, and — for an imposter — the heat that drove it (vote tally + chat
        accusers) and the chat-NLP state, so a replay explains *why* it did what it did."""

        if self._decision_traced:
            return
        self._decision_traced = True
        data: dict[str, Any] = {
            "role": role,
            "path": path,
            "target": target,
            "fabricated": fabricated,
            "top_suspect": top_suspect(belief),
        }
        if role == "imposter":
            data["votes"] = votes_against(belief)
            data["chat_accusers"] = accusers if accusers is not None else {}
            data["nlp"] = chat_nlp.state()
        self.emit.event("meeting_decision", data)
        self.emit.counter("meeting_decision", tags={"role": role, "path": path})

    def _chat_accusers(self, belief: Belief) -> dict[str, int]:
        """Per-color count of *other players* who have accused them in chat — the
        additive bandwagon signal (empty when the chat-NLP model is off / still
        loading). The per-meeting cache avoids re-parsing the same messages each tick."""

        return chat_read.chat_accusers(belief, cache=self._chat_parse_cache)

    # --- LLM call cadence -------------------------------------------------

    def _next_llm_trigger(self, belief: Belief) -> str | None:
        tick = belief.last_tick
        if self._last_llm_call_tick is not None and tick - self._last_llm_call_tick < LLM_MIN_CALL_INTERVAL_TICKS:
            return None
        if not self._can_start_llm_call(belief):
            return None
        if self._deadline_prompted:
            return None
        if self._last_llm_call_tick is None:
            return "meeting_start"

        if self._remaining_ticks(belief) <= self._deadline_prompt_remaining_ticks():
            return "deadline"

        signature = self._external_chat_signature(belief)
        if signature != self._last_external_chat_signature:
            return "new_chat"

        if (
            self._last_chat_tick is not None
            and self._chat_cooldown_ready(belief)
            and self._last_cooldown_prompt_chat_tick != self._last_chat_tick
        ):
            return "chat_cooldown_ready"

        return None

    def _call_llm(self, context: dict[str, Any], *, trigger: str) -> Any | None:
        self._last_llm_call_tick = int(context["meeting"]["tick"])
        self._last_external_chat_signature = tuple(
            (event["tick"], event["speaker_color"], event["text"])
            for event in context["chat"]["messages"]
            if not event["self"]
        )
        if trigger == "deadline":
            self._deadline_prompted = True
        if trigger == "chat_cooldown_ready":
            self._last_cooldown_prompt_chat_tick = self._last_chat_tick
        try:
            result = self._llm_client.decide(context, trigger=trigger)
        except Exception as exc:
            self.emit.event(
                "meeting_llm_fallback",
                {"reason": "llm_call_failed", "trigger": trigger, "error": repr(exc)},
            )
            return None
        self.emit.histogram("meeting_llm.latency_ms", result.latency_ms, tags={"model": result.model, "trigger": trigger})
        return result

    def _validate_decision(self, belief: Belief, decision: MeetingDecision) -> MeetingDecision | None:
        try:
            return validate_meeting_decision(
                decision,
                alive_vote_targets=valid_vote_targets(belief),
                current_tentative=self._tentative_vote,
                fallback_vote=self._fallback_vote_target(belief),
            )
        except MeetingDecisionValidationError as exc:
            self.emit.event(
                "meeting_llm_fallback",
                {"reason": "invalid_meeting_decision", "error": str(exc), "decision": decision.model_dump(mode="json")},
            )
            return None

    def _trace_decision(self, trigger: str, decision: MeetingDecision, result: Any) -> None:
        self.emit.event(
            "meeting_llm_decision",
            {
                "trigger": trigger,
                "model": result.model,
                "latency_ms": round(result.latency_ms, 2),
                "usage": result.usage,
                "decision": decision.model_dump(mode="json"),
            },
        )
        if result.raw_request is not None or result.raw_response is not None:
            self.emit.event(
                "meeting_llm_debug",
                {"request": result.raw_request, "response": result.raw_response},
            )

    # --- decision application --------------------------------------------

    def _apply_decision(self, belief: Belief, decision: MeetingDecision) -> Intent:
        if decision.vote_target is not None:
            self._tentative_vote = decision.vote_target
            self.emit.event(
                "meeting_tentative_vote",
                {"target": self._tentative_vote, "reason": decision.reason, "confidence": decision.confidence},
            )

        if decision.action == "send_chat":
            assert decision.chat_text is not None
            if decision.chat_text in self._sent_chat_texts:
                self.emit.event("meeting_llm_fallback", {"reason": "duplicate_chat_suppressed", "text": decision.chat_text})
                return Intent(kind="idle", reason="duplicate LLM chat suppressed")
            if self._chat_cooldown_ready(belief):
                return self._send_chat_intent(belief, decision.chat_text, reason=decision.reason or "LLM meeting chat")
            self._pending_chat_text = decision.chat_text[:CHAT_MAX_CHARS]
            self.emit.event(
                "meeting_llm_fallback",
                {"reason": "chat_cooldown_pending", "text": self._pending_chat_text},
            )
            return Intent(kind="idle", reason="waiting for chat cooldown")

        if decision.action == "submit_vote":
            return self._submit_vote_intent(belief, reason=decision.reason or "LLM submitted vote")

        if decision.action == "set_tentative_vote":
            return Intent(kind="idle", reason=decision.reason or "LLM set tentative vote")

        return Intent(kind="idle", reason=decision.reason or "LLM waits")

    def _send_chat_intent(self, belief: Belief, text: str, *, reason: str) -> Intent:
        self._pending_chat_text = None
        self._sent_chat_texts.add(text)
        self._last_chat_tick = belief.last_tick
        self.emit.event("meeting_chat_selected", {"text": text, "reason": reason})
        return Intent(kind="chat", text=text, reason=reason)

    def _submit_vote_intent(self, belief: Belief, *, reason: str) -> Intent:
        vote_target = self._resolved_vote_target(belief)
        # Hard guard: the agent can never vote itself out, whatever suspicion says.
        self_color = belief.self_color or belief.voting.self_marker_color
        if self_color is not None and vote_target == self_color:
            vote_target = VOTE_SKIP
        self._active_vote_target = vote_target
        self._active_vote_reason = reason
        self.emit.event("meeting_vote_selected", {"target": vote_target, "reason": reason})
        return self._vote_intent(vote_target, reason=reason)

    def _vote_intent(self, vote_target: str, *, reason: str) -> Intent:
        if vote_target == VOTE_SKIP:
            return Intent(kind="vote", reason=reason)
        return Intent(kind="vote", target_color=vote_target, reason=reason)

    def _decide_after_llm_failure(self, belief: Belief, trigger: str) -> Intent:
        if trigger == "deadline":
            return self._submit_vote_intent(belief, reason=f"LLM fallback after {trigger}")
        if trigger == "meeting_start":
            return self._decide_deterministic(belief, trace_disabled=False)
        return Intent(kind="idle", reason=f"LLM fallback after {trigger}")

    # --- state helpers ----------------------------------------------------

    def _reset_for_meeting_if_needed(self, belief: Belief) -> None:
        meeting_id = belief.phase_start_tick
        if meeting_id == self._meeting_id:
            return
        self._meeting_id = meeting_id
        self._deterministic_chatted = False
        self._disabled_traced = False
        self._sent_chat_texts.clear()
        self._pending_chat_text = None
        self._last_chat_tick = None
        self._last_llm_call_tick = None
        self._last_external_chat_signature = self._external_chat_signature(belief)
        self._last_cooldown_prompt_chat_tick = None
        self._deadline_prompted = False
        self._tentative_vote = None
        self._active_vote_target = None
        self._active_vote_reason = ""
        self._vote_submitted = False
        self._chat_parse_cache = {}
        self._decision_traced = False
        self._deduction_early_chat_attempted = False
        self._deduction_finalized = False
        self._history = None
        self._history_key = None

    def _external_chat_signature(self, belief: Belief) -> tuple[tuple[int, str | None, str], ...]:
        self_color = belief.voting.self_marker_color
        return tuple(
            (event.tick, event.speaker_color, event.text)
            for event in belief.chat_log
            if self._is_external_chat(event, self_color)
        )

    def _is_external_chat(self, event: ChatEvent, self_color: str | None) -> bool:
        if event.speaker_color is not None and event.speaker_color == self_color:
            return False
        return event.text not in self._sent_chat_texts

    def _chat_cooldown_ready(self, belief: Belief) -> bool:
        return self._last_chat_tick is None or belief.last_tick - self._last_chat_tick >= CHAT_COOLDOWN_TICKS

    def _remaining_ticks(self, belief: Belief) -> int:
        timer = effective_vote_timer_ticks(belief)
        return max(0, timer - max(0, belief.last_tick - belief.phase_start_tick))

    def _should_auto_submit(self, belief: Belief) -> bool:
        return not self._vote_submitted and self._remaining_ticks(belief) <= AUTO_SUBMIT_REMAINING_TICKS

    def _can_start_llm_call(self, belief: Belief) -> bool:
        return self._remaining_ticks(belief) > self._latest_safe_llm_start_remaining_ticks()

    def _deadline_prompt_remaining_ticks(self) -> int:
        return max(DEADLINE_LLM_REMAINING_TICKS, self._latest_safe_llm_start_remaining_ticks() + 1)

    def _latest_safe_llm_start_remaining_ticks(self) -> int:
        timeout_ticks = math.ceil(self._llm_timeout_seconds() * MEETING_TICKS_PER_SECOND)
        return AUTO_SUBMIT_REMAINING_TICKS + timeout_ticks + LLM_TIMEOUT_MARGIN_TICKS

    def _llm_timeout_seconds(self) -> float:
        value = getattr(self._llm_client, "timeout_seconds", DEFAULT_LLM_TIMEOUT_SECONDS)
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return DEFAULT_LLM_TIMEOUT_SECONDS

    def _resolved_vote_target(self, belief: Belief) -> str:
        tentative = self._tentative_vote
        if tentative is not None and (tentative == VOTE_SKIP or tentative in valid_vote_targets(belief)):
            return tentative
        return self._fallback_vote_target(belief)

    def _fallback_vote_target(self, belief: Belief) -> str:
        # Under the deduction brain there is nothing to fall back ON: `belief.suspicion`
        # is empty by construction, and the only caller reaching here has already
        # rejected `_tentative_vote`. Skipping is the whole fallback.
        if deduction_history_enabled(belief.self_role):
            return VOTE_SKIP
        return top_suspect(belief) or VOTE_SKIP
