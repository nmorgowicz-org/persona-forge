"""Phase A7a local-verifiable gates: save/load round-trip, corrupt-file handling,
env-locked precedence, and failed-reload-does-not-persist."""

import json
import os
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

from persona_forge import runtime_store

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def runtime_json(tmp_path):
    return tmp_path / "runtime.json"


def test_save_then_load_round_trips(runtime_json):
    values = {"SILENCE_TRIM": "0", "POCKET_TTS_TEMP": "1.5"}
    runtime_store.save_persisted_config(values, path=runtime_json)

    loaded = runtime_store.load_persisted_config(path=runtime_json)

    assert loaded == values


def test_load_missing_file_returns_empty(tmp_path):
    missing = tmp_path / "does_not_exist.json"

    assert runtime_store.load_persisted_config(path=missing) == {}


def test_load_corrupt_file_warns_and_ignores(runtime_json):
    runtime_json.write_text("{not valid json")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        loaded = runtime_store.load_persisted_config(path=runtime_json)

    assert loaded == {}
    assert any("corrupt" in str(w.message) for w in caught)


def test_load_malformed_shape_warns_and_ignores(runtime_json):
    runtime_json.write_text(json.dumps({"schema_version": 1, "values": "not-a-dict"}))

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        loaded = runtime_store.load_persisted_config(path=runtime_json)

    assert loaded == {}
    assert any("unexpected shape" in str(w.message) for w in caught)


def test_locked_keys_from_csv():
    environ = {"RUNTIME_LOCKED_KEYS": "TTS_BACKEND, MODEL_DTYPE"}

    assert runtime_store.locked_keys(environ) == {"TTS_BACKEND", "MODEL_DTYPE"}


def test_locked_keys_from_per_key_flag():
    environ = {"RUNTIME_LOCK_TTS_BACKEND": "1"}

    assert runtime_store.is_locked("TTS_BACKEND", environ)
    assert not runtime_store.is_locked("MODEL_DTYPE", environ)


def test_apply_persisted_config_overrides_unlocked_env(monkeypatch, runtime_json):
    monkeypatch.setattr(runtime_store, "_runtime_json_path", lambda: runtime_json)
    runtime_store.save_persisted_config({"SILENCE_TRIM": "0"}, path=runtime_json)

    environ = {"SILENCE_TRIM": "1"}
    applied = runtime_store.apply_persisted_config(environ)

    assert environ["SILENCE_TRIM"] == "0"
    assert applied == {"SILENCE_TRIM": "0"}


def test_apply_persisted_config_skips_locked_keys(monkeypatch, runtime_json):
    monkeypatch.setattr(runtime_store, "_runtime_json_path", lambda: runtime_json)
    runtime_store.save_persisted_config({"TTS_BACKEND": "openvino"}, path=runtime_json)

    environ = {"TTS_BACKEND": "pocket_tts", "RUNTIME_LOCKED_KEYS": "TTS_BACKEND"}
    applied = runtime_store.apply_persisted_config(environ)

    assert environ["TTS_BACKEND"] == "pocket_tts"
    assert applied == {}


@pytest.mark.requires_torch
def test_failed_reload_does_not_persist(tmp_path):
    """apply_runtime_config's persist step is unreachable when the reload raises,
    since it sits after the existing try/finally block completes.

    Runs in a subprocess: persona_forge.model spawns a real background self-load thread
    at import time, which other tests' fake-runtime installs into sys.modules with no
    teardown; importing the real module in-process here would leak that thread's
    global state into later tests regardless of any restore bookkeeping.
    """
    marker = tmp_path / "persist_called.marker"
    script = f"""
import sys
sys.path.insert(0, {str(_REPO_ROOT / "src")!r})
sys.path.insert(0, {str(_REPO_ROOT)!r})

from persona_forge import model
from persona_forge import runtime_store

model.force_unload = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
runtime_store.save_persisted_config = lambda values, path=None: open({str(marker)!r}, "w").write("called")

try:
    model.apply_runtime_config({{"MODEL_DTYPE": "float16"}})
except RuntimeError:
    pass
else:
    raise SystemExit("expected RuntimeError from force_unload")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PYTHONPATH": f"{_REPO_ROOT / 'src'}:{_REPO_ROOT}"},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert not marker.exists()
