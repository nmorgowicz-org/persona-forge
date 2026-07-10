"""Regression test for _run_generate's default (non-TTS_DIAG) success path.

qwen3_tts.model imports `from qwen_tts import Qwen3TTSModel` at module scope, but the real
`qwen-tts` package pulls in librosa which isn't installed in the dev/test environment. We
install a fake `qwen_tts` module into sys.modules before importing qwen3_tts.model so the
module under test can be exercised without the real dependency (same pattern as
test_pocket_tts_runtime.py's fake `pocket_tts` module).

This exists because tier2_backend fully replaces qwen3_tts.model with FakeModelRuntime
before importing qwen3_tts.app, so nothing in that tier ever calls the real _run_generate.
That's exactly how a regression like the _watchdog_stop UnboundLocalError (fixed here) went
undetected: every test exercising _run_generate's success path was hitting a hand-written
fake, not this function's actual watchdog/timeout bookkeeping.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("torch")
np = pytest.importorskip("numpy")

_MODEL_PY = Path(__file__).resolve().parents[2] / "src" / "qwen3_tts" / "model.py"


@pytest.fixture
def model_module(monkeypatch, tmp_path):
    fake_qwen_tts = types.ModuleType("qwen_tts")

    class _FakeQwen3TTSModel:
        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            return cls()

    fake_qwen_tts.Qwen3TTSModel = _FakeQwen3TTSModel
    monkeypatch.setitem(sys.modules, "qwen_tts", fake_qwen_tts)

    monkeypatch.setenv("REF_TEXT", "hello world")
    monkeypatch.setenv("VOICE_LIBRARY_DIR", str(tmp_path / "voices"))
    monkeypatch.setenv("SEGMENT_LIBRARY_DIR", str(tmp_path / "segments"))
    monkeypatch.setenv("TTS_BACKEND", "pytorch")
    monkeypatch.delenv("TTS_DIAG", raising=False)

    # Load model.py under a private module name (rather than "qwen3_tts.model") so this
    # test is hermetic regardless of what other test files have already done to the shared
    # sys.modules["qwen3_tts.model"]/"qwen3_tts" package cache (e.g. tier2_backend/conftest.py
    # permanently replaces sys.modules["qwen3_tts.model"] with FakeModelRuntime at collection
    # time). model.py has no relative imports, so executing it under an unrelated name is safe.
    spec = importlib.util.spec_from_file_location("_model_under_test", _MODEL_PY)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    yield m


class _FakeGeneratingModel:
    """Stand-in for the loaded Qwen3TTSModel: only generate_voice_clone is exercised."""

    def generate_voice_clone(self, *, text, language, voice_clone_prompt, **gen_kwargs):
        wav = np.ones(2400, dtype=np.float32)  # 0.1s @ 24kHz, above silence threshold
        return [wav], 24000


class TestRunGenerateSuccessPath:
    @pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
    def test_default_path_does_not_touch_unset_watchdog(self, monkeypatch, model_module):
        """Non-TTS_DIAG (_use_timeout=False) path must not reference an unbound watchdog.

        Regression test for the UnboundLocalError: _watchdog_stop/_watchdog were only
        assigned inside `if _use_timeout:`, but referenced unconditionally afterward.
        """
        m = model_module

        monkeypatch.setattr(m, "model", _FakeGeneratingModel())
        monkeypatch.setattr(m, "active_profile", m.BASE_PROFILE)
        monkeypatch.setattr(m, "voice_clone_prompt", "fake-voice-clone-prompt")
        monkeypatch.setattr(m, "_any_foreign_loaded", lambda: False)
        assert os.path.exists("/tmp/tts_diag") is False

        wav, sr, job_id = m._run_generate("hello there", "English")

        assert sr == 24000
        assert len(wav) > 0
        assert job_id is not None

        with m._active_jobs_lock:
            job = m._active_jobs.get(job_id)
        assert job is not None
        assert job.status == "completed"
