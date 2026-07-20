from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("stream_eval_script", SCRIPTS / "stream_eval.py")
assert SPEC is not None and SPEC.loader is not None
STREAM = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STREAM)


def test_run_build_preflights_replay_encodings(monkeypatch, tmp_path: Path) -> None:
    episode = tmp_path / "episode"
    output = tmp_path / "warehouse"
    expander = tmp_path / "expand_replay"
    request = tmp_path / "input" / "report_request.json"
    calls = []

    def fake_preflight(episodes, binary):
        calls.append(("preflight", episodes, binary))
        return {episode: "identity"}

    def fake_build_request(episodes, input_dir, encodings):
        calls.append(("build_request", episodes, input_dir, encodings))
        return request

    def fake_run(command, **kwargs):
        calls.append(("run", command, kwargs))

    monkeypatch.setattr(STREAM, "preflight", fake_preflight)
    monkeypatch.setattr(STREAM, "build_request", fake_build_request)
    monkeypatch.setattr(STREAM.subprocess, "run", fake_run)

    STREAM.run_build([episode], output, expander, workers=3)

    assert calls[0] == ("preflight", [episode], expander)
    assert calls[1] == (
        "build_request",
        [episode],
        tmp_path / "warehouse_input",
        {episode: "identity"},
    )
    assert calls[2][1][-2:] == ["--workers", "3"]
    assert calls[2][2]["env"]["CREWRIFT_EXPAND_REPLAY"] == str(expander)
