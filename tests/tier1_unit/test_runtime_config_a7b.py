"""Phase A7b local-verifiable gates: state shape (source/locked/restart_required per
key) and reset behavior (drops file for unlocked keys, keeps locked, reverts env) on a
temp DATA_DIR.

Each case runs in a subprocess (same rationale as test_runtime_store.py's
test_failed_reload_does_not_persist): persona_forge.model spawns a real background
self-load thread at import time, so importing it in-process would leak global state
into other tests regardless of restore bookkeeping.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Every case spawns a subprocess that imports persona_forge.model, which does a
# real `import torch` at module level.
pytestmark = pytest.mark.requires_torch

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
from persona_forge import model

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
from persona_forge import model

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
from persona_forge import model

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
from persona_forge import model

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


def test_pocket_sourcing_update_does_not_reload_other_backend(tmp_path):
    # "requires reload" is printed only inside the force_unload() branch, so its
    # absence proves the active PyTorch model was not unloaded.
    script = """
import os
from persona_forge import model

assert model.TTS_BACKEND == "pytorch", model.TTS_BACKEND
state = model.apply_runtime_config({"POCKET_TTS_MODEL_SOURCE": "lunahr"}, persist=False)
# Pocket live keys are hidden while another backend is active, but the value
# must still be staged for a future pocket load.
assert "POCKET_TTS_MODEL_SOURCE" not in state["live"]
assert os.environ.get("POCKET_TTS_MODEL_SOURCE") == "lunahr", "value must be staged"
print("DONE")
"""
    result = _run(script, {"DATA_DIR": str(tmp_path), "TTS_BACKEND": "pytorch"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "DONE" in result.stdout
    assert "requires reload" not in result.stdout, result.stdout


def test_preview_pocket_sourcing_reload_scoped_to_active_backend(tmp_path):
    script = """
from persona_forge import model

pytorch_preview = model.preview_runtime_config({"POCKET_TTS_MODEL_SOURCE": "official"})
assert pytorch_preview["reload_required"] is False, pytorch_preview

model.TTS_BACKEND = "pocket_tts"
pocket_preview = model.preview_runtime_config({"POCKET_TTS_MODEL_SOURCE": "official"})
assert pocket_preview["reload_required"] is True, pocket_preview
print("OK")
"""
    result = _run(script, {"DATA_DIR": str(tmp_path), "TTS_BACKEND": "pytorch"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_invalid_pocket_source_rejected_before_unload(tmp_path):
    script = """
import os
from persona_forge import model

model.TTS_BACKEND = "pocket_tts"
try:
    model.apply_runtime_config({"POCKET_TTS_MODEL_SOURCE": "bogus"}, persist=False)
except ValueError as e:
    assert "POCKET_TTS_MODEL_SOURCE" in str(e), e
    print("REJECTED")
else:
    raise AssertionError("expected ValueError for invalid source")

assert model.TTS_BACKEND == "pocket_tts"
assert "POCKET_TTS_MODEL_SOURCE" not in os.environ, "rejected value must not be staged"
"""
    result = _run(script, {"DATA_DIR": str(tmp_path), "TTS_BACKEND": "pytorch"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "REJECTED" in result.stdout
    assert "requires reload" not in result.stdout, result.stdout
