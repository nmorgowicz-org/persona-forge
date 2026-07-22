"""Phase A7b local-verifiable gates: state shape (source/locked/restart_required per
key) and reset behavior (drops file for unlocked keys, keeps locked, reverts env) on a
temp DATA_DIR.

Each case runs in a subprocess (same rationale as test_runtime_store.py's
test_failed_reload_does_not_persist): qwen3_tts.model spawns a real background
self-load thread at import time, so importing it in-process would leak global state
into other tests regardless of restore bookkeeping.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(script: str, env_extra: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
        env={
            **os.environ,
            "PYTHONPATH": f"{_REPO_ROOT / 'src'}:{_REPO_ROOT}",
            **env_extra,
        },
    )


def test_state_shape_reports_source_locked_restart_required(tmp_path):
    script = """
import json
from qwen3_tts import model

state = model.runtime_config_state()
meta = state["live_metadata"]

assert "SILENCE_TRIM" in meta
assert set(meta["SILENCE_TRIM"]) == {"value", "source", "locked", "restart_required"}
assert meta["SILENCE_TRIM"]["source"] in ("file", "env", "default")
assert meta["SILENCE_TRIM"]["locked"] is False

assert "GPU_FAMILY" in state["restart_required"]
assert set(state["restart_required"]["GPU_FAMILY"]) == {"value", "reason"}

print("OK")
"""
    result = _run(script, {"DATA_DIR": str(tmp_path)})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_state_shape_marks_locked_key(tmp_path):
    script = """
from qwen3_tts import model

state = model.runtime_config_state()
assert state["live_metadata"]["TTS_BACKEND"]["locked"] is True
print("OK")
"""
    result = _run(script, {"DATA_DIR": str(tmp_path), "RUNTIME_LOCKED_KEYS": "TTS_BACKEND"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_reset_drops_unlocked_keeps_locked_and_reverts_env(tmp_path):
    runtime_json = tmp_path / "runtime.json"
    runtime_json.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "values": {"SILENCE_TRIM": "0", "TTS_BACKEND": "openvino"},
            }
        )
    )

    script = f"""
import json
from pathlib import Path
from qwen3_tts import model

state = model.reset_runtime_config()

assert state["live"]["SILENCE_TRIM"] is True, state["live"]["SILENCE_TRIM"]
assert state["live"]["TTS_BACKEND"] == "openvino", state["live"]["TTS_BACKEND"]

persisted = json.loads(Path({str(runtime_json)!r}).read_text())["values"]
assert persisted == {{"TTS_BACKEND": "openvino"}}, persisted
print("OK")
"""
    result = _run(
        script,
        {
            "DATA_DIR": str(tmp_path),
            "RUNTIME_LOCKED_KEYS": "TTS_BACKEND",
            "SILENCE_TRIM": "0",
            "TTS_BACKEND": "openvino",
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_preview_runtime_config_does_not_mutate(tmp_path):
    runtime_json = tmp_path / "runtime.json"
    script = f"""
from pathlib import Path
from qwen3_tts import model

before = model.runtime_config_state()["live"]["SILENCE_TRIM"]
preview = model.preview_runtime_config({{"SILENCE_TRIM": False}})

assert preview["dry_run"] is True
assert preview["would_apply"] == {{"SILENCE_TRIM": False}}
assert preview["would_skip_locked"] == []
assert preview["predicted_live"]["SILENCE_TRIM"] is False

after = model.runtime_config_state()["live"]["SILENCE_TRIM"]
assert after == before, "preview must not mutate live state"
assert not Path({str(runtime_json)!r}).exists(), "preview must not write runtime.json"
print("OK")
"""
    result = _run(script, {"DATA_DIR": str(tmp_path)})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout
