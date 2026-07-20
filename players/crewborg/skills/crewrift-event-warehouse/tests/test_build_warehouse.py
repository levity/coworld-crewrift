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
