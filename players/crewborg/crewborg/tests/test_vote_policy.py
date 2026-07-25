"""State-aware crew vote policy (env CREWBORG_VOTE_POLICY).

These assert the opt-in policy in ``strategy/meeting/vote_policy.py`` and its wiring
into ``suspicion.top_suspect``'s fitted crew branch: flag off is byte-identical to the
fitted 0.9 bar; flag on adds must-eject, corroborated pile-on, and a 0.75 comfortable
bar. The imposter path is never reached here (crew branch only) and self is never voted.
"""

from __future__ import annotations

import pytest

from crewborg.perception.entities import VoteCandidate, VotingState
from crewborg.strategy import suspicion as suspicion_module
from crewborg.strategy.meeting import vote_policy
from crewborg.strategy.meeting.vote_policy import (
    corroborated_pileon_target,
    crew_vote_target,
    must_eject,
)
from crewborg.strategy.suspicion import top_suspect
from crewborg.types import Belief, PlayerEvent, PlayerRecord, SocialClaim


def _roster(alive: list[str], dead: list[str] | None = None, killers: set[str] | None = None):
    killers = killers or set()
    records: dict[str, PlayerRecord] = {}
    for color in alive:
        events = (
            [PlayerEvent(kind="kill", start_tick=1, end_tick=1, target_color="grey")]
            if color in killers
            else []
        )
        records[color] = PlayerRecord(color=color, life_status="alive", events=events)
    for color in dead or []:
        events = (
            [PlayerEvent(kind="kill", start_tick=1, end_tick=1, target_color="grey")]
            if color in killers
            else []
        )
        records[color] = PlayerRecord(color=color, life_status="dead", events=events)
    return records


def _voting(alive: list[str], self_color: str) -> VotingState:
    candidates = tuple(
        VoteCandidate(slot=i, color=color, alive=True) for i, color in enumerate(alive)
    )
    return VotingState(self_marker_color=self_color, candidates=candidates)


def _belief(
    *,
    suspicion: dict[str, float],
    alive: list[str],
    dead: list[str] | None = None,
    killers: set[str] | None = None,
    imposter_count: int = 2,
    claims: list[SocialClaim] | None = None,
    self_color: str = "red",
) -> Belief:
    belief = Belief(self_role="crewmate", self_color=self_color, imposter_count=imposter_count)
    belief.roster = _roster(alive, dead, killers)
    belief.voting = _voting(alive, self_color)
    belief.suspicion = dict(suspicion)
    belief.social_claims = list(claims or [])
    belief.phase_start_tick = 0
    return belief


def _accuse(speaker: str, target: str, evidence_kind: str) -> SocialClaim:
    return SocialClaim(
        meeting_id=0,
        tick=10,
        speaker_color=speaker,
        targets=(target,),
        stance="accuse",
        evidence_kind=evidence_kind,
        text=f"{target} sus",
    )


@pytest.fixture()
def _fitted():
    """Pin a non-None fitted-weights sentinel so top_suspect takes the crew branch."""

    saved = suspicion_module._WEIGHTS
    suspicion_module.set_weights({"schema": "test", "coefficients": {}})
    yield
    suspicion_module.set_weights(saved)


@pytest.fixture(autouse=True)
def _flag_off_by_default(monkeypatch):
    monkeypatch.delenv(vote_policy.FEATURE_ENV, raising=False)


# --- flag gating --------------------------------------------------------------


def test_flag_off_by_default() -> None:
    assert vote_policy.vote_policy_enabled() is False


def test_flag_off_leaves_top_suspect_at_the_fitted_bar(_fitted, monkeypatch) -> None:
    monkeypatch.delenv(vote_policy.FEATURE_ENV, raising=False)
    # A clear leader short of near-certainty: the fitted 0.9 bar skips it.
    belief = _belief(suspicion={"blue": 0.78, "green": 0.3}, alive=["red", "blue", "green"])
    assert top_suspect(belief) is None
    # Near-certainty still votes, unchanged.
    belief.suspicion = {"blue": 0.95, "green": 0.3}
    assert top_suspect(belief) == "blue"


def test_flag_on_delegates_to_the_policy(_fitted, monkeypatch) -> None:
    monkeypatch.setenv(vote_policy.FEATURE_ENV, "1")
    # Same clear leader the fitted bar skipped now clears the 0.75 comfortable bar.
    belief = _belief(suspicion={"blue": 0.78, "green": 0.3}, alive=["red", "blue", "green"])
    assert top_suspect(belief) == "blue"


# --- must-eject ---------------------------------------------------------------


def test_must_eject_fires_one_from_parity() -> None:
    # 5 alive, K=2 → crew 3 / imp 2 → crew - imp == 1.
    belief = _belief(
        suspicion={"blue": 0.28, "green": 0.27, "pink": 0.26, "orange": 0.25},
        alive=["red", "blue", "green", "pink", "orange"],
        imposter_count=2,
    )
    assert must_eject(belief) is True
    # A flat field still votes the top living read here — a skip loses outright.
    assert crew_vote_target(belief) == "blue"


def test_must_eject_false_with_a_comfortable_margin() -> None:
    belief = _belief(
        suspicion={"blue": 0.28, "green": 0.27},
        alive=["red", "blue", "green", "pink", "orange", "cyan", "lime", "brown"],
        imposter_count=2,
    )
    assert must_eject(belief) is False
    # Flat field, comfortable margin → skip rather than eject at random.
    assert crew_vote_target(belief) is None


def test_confirmed_dead_imposter_relaxes_parity() -> None:
    # 5 alive but one witnessed imposter already dead → budget 1, crew 4 / imp 1.
    belief = _belief(
        suspicion={"blue": 0.28, "green": 0.27, "pink": 0.26, "orange": 0.25},
        alive=["red", "blue", "green", "pink", "orange"],
        dead=["grey"],
        killers={"grey"},
        imposter_count=2,
    )
    assert must_eject(belief) is False


# --- corroborated pile-on -----------------------------------------------------


def test_pileon_fires_on_two_evidence_backed_accusers() -> None:
    belief = _belief(
        suspicion={"blue": 0.4, "green": 0.3},
        alive=["red", "blue", "green", "pink", "orange", "cyan", "lime", "brown"],
        claims=[_accuse("green", "blue", "body"), _accuse("pink", "blue", "sighting")],
    )
    assert corroborated_pileon_target(belief) == "blue"
    # Below the 0.9 bar (blue is 0.4) the pile-on still recruits our vote.
    assert crew_vote_target(belief) == "blue"


def test_pileon_ignores_a_bare_sus_accusation() -> None:
    belief = _belief(
        suspicion={"blue": 0.4, "green": 0.3},
        alive=["red", "blue", "green", "pink", "orange", "cyan", "lime", "brown"],
        claims=[_accuse("green", "blue", "bare"), _accuse("pink", "blue", "bare")],
    )
    assert corroborated_pileon_target(belief) is None
    assert crew_vote_target(belief) is None


def test_pileon_needs_two_distinct_accusers() -> None:
    belief = _belief(
        suspicion={"blue": 0.4, "green": 0.3},
        alive=["red", "blue", "green", "pink", "orange", "cyan", "lime", "brown"],
        claims=[_accuse("green", "blue", "body")],
    )
    assert corroborated_pileon_target(belief) is None


def test_pileon_excludes_a_confirmed_imposter_accuser() -> None:
    # green is a witnessed killer → not a trusted accuser → only pink corroborates.
    belief = _belief(
        suspicion={"blue": 0.4, "green": 0.99},
        alive=["red", "blue", "green", "pink", "orange", "cyan", "lime", "brown"],
        killers={"green"},
        claims=[_accuse("green", "blue", "body"), _accuse("pink", "blue", "sighting")],
    )
    assert corroborated_pileon_target(belief) is None


# --- comfortable bar ----------------------------------------------------------


def test_comfortable_bar_votes_a_clear_leader() -> None:
    belief = _belief(
        suspicion={"blue": 0.78, "green": 0.3},
        alive=["red", "blue", "green", "pink", "orange", "cyan", "lime", "brown"],
    )
    assert crew_vote_target(belief) == "blue"


def test_comfortable_bar_skips_a_flat_field() -> None:
    belief = _belief(
        suspicion={"blue": 0.6, "green": 0.55, "pink": 0.5},
        alive=["red", "blue", "green", "pink", "orange", "cyan", "lime", "brown"],
    )
    assert crew_vote_target(belief) is None


# --- self guard ---------------------------------------------------------------


def test_self_is_never_voted() -> None:
    # Self forced highest and self carries two evidence-backed accusers.
    belief = _belief(
        suspicion={"red": 0.99, "blue": 0.2},
        alive=["red", "blue", "green", "pink", "orange", "cyan", "lime", "brown"],
        claims=[_accuse("green", "red", "body"), _accuse("pink", "red", "sighting")],
        self_color="red",
    )
    assert corroborated_pileon_target(belief) is None  # never pile onto self
    assert crew_vote_target(belief) != "red"
    assert crew_vote_target(belief) is None  # blue 0.2 clears no bar
