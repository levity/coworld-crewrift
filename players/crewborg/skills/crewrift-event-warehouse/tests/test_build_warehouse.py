from __future__ import annotations

import importlib.util
import json
import zlib
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "build_warehouse.py"
SPEC = importlib.util.spec_from_file_location("build_warehouse_script", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


def test_replay_encoding_uses_content_not_suffix(tmp_path: Path) -> None:
    raw = b"CREWRIFT" + b"\x00" * 32
    misleading = tmp_path / "replay.json.z"
    misleading.write_bytes(raw)
    assert BUILD.replay_encoding(misleading) == "identity"

    misleading.write_bytes(zlib.compress(raw))
    assert BUILD.replay_encoding(misleading) == "zlib"
    assert BUILD.raw_replay_bytes(misleading, "zlib") == raw


def test_replay_encoding_rejects_unknown_bytes(tmp_path: Path) -> None:
    replay = tmp_path / "replay.json.z"
    replay.write_bytes(b"not-a-replay")
    with pytest.raises(ValueError, match="neither raw CREWRIFT"):
        BUILD.replay_encoding(replay)


def _xp_episode() -> dict:
    return {
        "id": "ereq_test",
        "coworld_version": "0.1.59",
        "participants": [
            {
                "position": 0,
                "policy_version_id": "pv_crew",
                "policy_name": "crew-policy",
                "player_name": "Crew",
            },
            {
                "position": 1,
                "policy_version_id": "pv_imp",
                "policy_name": "imp-policy",
                "player_name": "Imp",
            },
        ],
        "scores": [
            {"policy_version_id": "pv_crew", "score": 108.0},
            {"policy_version_id": "pv_imp", "score": 99.0},
        ],
        "game_config": {"slots": [{"role": "crew"}, {"role": "imposter"}]},
    }


def test_synthesize_results_from_aligned_xp_episode() -> None:
    results = BUILD.synthesize_results(_xp_episode())
    assert results["names"] == ["Crew", "Imp"]
    assert results["scores"] == [108.0, 99.0]
    assert results["win"] == [True, False]
    assert results["crew"] == [1, 0]
    assert results["imposter"] == [0, 1]


def test_synthesize_results_rejects_score_slot_mismatch() -> None:
    episode = _xp_episode()
    episode["scores"].reverse()
    with pytest.raises(ValueError, match="do not align slot-for-slot"):
        BUILD.synthesize_results(episode)


def test_synthesize_results_applies_win_to_the_whole_role() -> None:
    episode = _xp_episode()
    episode["participants"].insert(
        1,
        {
            "position": 1,
            "policy_version_id": "pv_crew_penalized",
            "policy_name": "crew-policy",
            "player_name": "Penalized Crew",
        },
    )
    episode["participants"][2]["position"] = 2
    episode["scores"].insert(
        1, {"policy_version_id": "pv_crew_penalized", "score": 98.0}
    )
    episode["game_config"]["slots"].insert(1, {"role": "crew"})

    results = BUILD.synthesize_results(episode)
    assert results["win"] == [True, True, False]


def test_synthesize_results_marks_no_winreward_episode_as_no_winner() -> None:
    episode = _xp_episode()
    episode["scores"][0]["score"] = 8.0
    assert BUILD.synthesize_results(episode)["win"] == [False, False]


def test_build_request_stages_missing_results_artifact(tmp_path: Path) -> None:
    episode_dir = tmp_path / "episodes" / "episode"
    episode_dir.mkdir(parents=True)
    (episode_dir / "episode.json").write_text(json.dumps(_xp_episode()))
    (episode_dir / "replay.json.z").write_bytes(b"CREWRIFT")

    assert BUILD.find_episode_dirs(episode_dir.parent) == [episode_dir]
    request = BUILD.build_request([episode_dir], tmp_path / "input", {episode_dir: "identity"})
    body = json.loads(request.read_text())
    results_uri = body["episodes"][0]["artifacts"]["results"]["uri"]
    staged = Path(results_uri.removeprefix("file://"))
    assert staged.exists()
    assert json.loads(staged.read_text())["win"] == [True, False]


def test_summarize_fails_on_extraction_failure(tmp_path: Path) -> None:
    manifest = {
        "episodes_total": 1,
        "episodes_ok": 0,
        "episodes_cached": 0,
        "episodes_skipped": 0,
        "episodes_failed": 1,
        "events_written": 0,
        "distinct_policies": 0,
        "event_keys": [],
        "episodes": [{
            "episode_id": "ereq_test",
            "status": "failed",
            "trace_warning": False,
            "message": "incorrect header check",
        }],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    assert BUILD.summarize(tmp_path) == 1


def test_summarize_succeeds_only_for_complete_build(tmp_path: Path) -> None:
    manifest = {
        "episodes_total": 1,
        "episodes_ok": 1,
        "episodes_cached": 0,
        "episodes_skipped": 0,
        "episodes_failed": 0,
        "events_written": 10,
        "distinct_policies": 1,
        "event_keys": ["trace_complete"],
        "episodes": [{
            "episode_id": "ereq_test",
            "status": "ok",
            "trace_warning": False,
        }],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    assert BUILD.summarize(tmp_path) == 0
