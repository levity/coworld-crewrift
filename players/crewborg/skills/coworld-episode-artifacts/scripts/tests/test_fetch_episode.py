"""Artifact-route regression tests for both hosted episode populations."""
from __future__ import annotations

import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fetch_artifacts import EpisodeRef, fetch_episode


class FakeClient:
    def __init__(self) -> None:
        self.paths: list[str] = []

    def get_json(self, path: str, **params: object) -> object:
        del params
        self.paths.append(path)
        assert path == "/v2/episode-requests/ereq_test/policy-artifacts"
        return [{
            "position": 2,
            "policy_version_id": "policy-version",
            "policy_name": "crewborg-test",
            "has_log": True,
            "has_artifact": True,
        }]

    def get_text_or_none(self, path: str) -> str | None:
        self.paths.append(path)
        values = {
            "/v2/episode-requests/ereq_test/artifacts/results": '{"scores":[1]}',
            "/v2/episode-requests/ereq_test/policy-version/policy-logs/2": "policy log",
        }
        return values.get(path)

    def get_bytes_or_none(self, path: str) -> bytes | None:
        self.paths.append(path)
        values = {
            "/v2/episode-requests/ereq_test/artifacts/replay": zlib.compress(b"replay"),
            "/v2/episode-requests/ereq_test/policy-version/policy-artifact/2": b"zip",
        }
        return values.get(path)


def test_xp_fetch_uses_owned_episode_request_routes(tmp_path: Path) -> None:
    client = FakeClient()
    ref = EpisodeRef(
        ref_id="ereq_test",
        created_at="2026-07-22T00:00:00Z",
        job_id="job-id-must-not-be-used",
        replay_url=None,
        label="completed",
        record={"id": "ereq_test"},
    )

    summary = fetch_episode(
        client, ref, tmp_path, want_replay=True, want_results=True, want_logs=True
    )

    assert summary["results"] is True
    assert summary["replay"] is True
    assert summary["logs"] == ["policy_agent_2.log"]
    assert summary["policy_artifacts"] == [2]
    assert (tmp_path / "results.json").read_text() == '{"scores":[1]}'
    assert (tmp_path / "replay.json").read_bytes() == b"replay"
    assert (tmp_path / "logs/policy_agent_2.log").read_text() == "policy log"
    assert (tmp_path / "artifacts/policy_artifact_2.zip").read_bytes() == b"zip"
    assert not any(path.startswith("/jobs/") for path in client.paths)
