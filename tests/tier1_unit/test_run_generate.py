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
import threading
import types
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

pytestmark = pytest.mark.requires_torch

_MODEL_PY = Path(__file__).resolve().parents[2] / "src" / "qwen3_tts" / "model.py"


@pytest.fixture
def model_module(monkeypatch, tmp_path):
    fake_qwen_tts = types.ModuleType("qwen_tts")

    class _FakeInnerModel:
        tts_model_type = "base"

        def named_modules(self):
            return []

    class _FakeOuterModel:
        def __init__(self):
            self.model = _FakeInnerModel()

        def named_modules(self):
            return []

    class _FakeQwen3TTSModel:
        def __init__(self):
            self.model = _FakeOuterModel()

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
    class _NoStartThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

        def join(self, timeout=None):
            pass

    real_thread = threading.Thread
    monkeypatch.setattr(threading, "Thread", _NoStartThread)

    spec = importlib.util.spec_from_file_location("_model_under_test", _MODEL_PY)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(threading, "Thread", real_thread)

    yield m


class _FakeGeneratingModel:
    """Stand-in for the loaded Qwen3TTSModel: only generate_voice_clone is exercised."""

    def generate_voice_clone(self, *, text, language, voice_clone_prompt, **gen_kwargs):
        wav = np.ones(2400, dtype=np.float32)  # 0.1s @ 24kHz, above silence threshold
        return [wav], 24000


class _FakeAudioTensor:
    def __init__(self, wav):
        self._wav = wav

    def cpu(self):
        return self

    def numpy(self):
        return self._wav


class TestRunGenerateSuccessPath:
    def _configure_model(self, monkeypatch, m):
        monkeypatch.setattr(m, "model", _FakeGeneratingModel())
        monkeypatch.setattr(m, "active_profile", m.BASE_PROFILE)
        monkeypatch.setattr(m, "voice_clone_prompt", "fake-voice-clone-prompt")
        monkeypatch.setattr(m, "_any_foreign_loaded", lambda: False)

    @pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
    def test_default_path_does_not_touch_unset_watchdog(self, monkeypatch, model_module):
        """Non-TTS_DIAG (_use_timeout=False) path must not reference an unbound watchdog.

        Regression test for the UnboundLocalError: _watchdog_stop/_watchdog were only
        assigned inside `if _use_timeout:`, but referenced unconditionally afterward.
        """
        m = model_module

        self._configure_model(monkeypatch, m)
        assert os.path.exists("/tmp/tts_diag") is False

        wav, sr, job_id = m._run_generate("hello there", "English")

        assert sr == 24000
        assert len(wav) > 0
        assert job_id is not None

        with m._active_jobs_lock:
            job = m._active_jobs.get(job_id)
        assert job is not None
        assert job.status == "completed"
        assert job.style_preset == "default"
        assert job.postprocess_applied is True
        assert job.metadata["applied_steps"] == ["normalize_lufs", "limit_peak"]

    def test_postprocess_false_preserves_trim_only_pcm(self, monkeypatch, model_module):
        m = model_module
        self._configure_model(monkeypatch, m)
        expected = m._trim_silence(np.ones(2400, dtype=np.float32), 24000)

        wav, _sr, job_id = m._run_generate("hello there", "English", postprocess=False)

        assert np.array_equal(wav, expected)
        with m._active_jobs_lock:
            job = m._active_jobs[job_id]
        assert job.style_preset is None
        assert job.postprocess_applied is False
        assert job.metadata.get("applied_steps") is None

    def test_unflagged_generation_never_calls_prosody_repair(
        self, monkeypatch, model_module
    ):
        m = model_module
        self._configure_model(monkeypatch, m)
        from qwen3_tts import prosody_repair

        def unexpected(*args, **kwargs):
            raise AssertionError("unflagged generation invoked repair")

        monkeypatch.setattr(prosody_repair, "repair_segment_audio", unexpected)
        _wav, _sr, job_id = m._run_generate("First. Second.", "English", postprocess=False)

        with m._active_jobs_lock:
            metadata = m._active_jobs[job_id].metadata["prosody_repair"]
        assert metadata["requested"] is False
        assert metadata["outcome"] == "not_requested"

    def test_flagged_generation_uses_shared_repair_engine(
        self, monkeypatch, model_module
    ):
        m = model_module
        self._configure_model(monkeypatch, m)
        from qwen3_tts import prosody_repair

        calls = []

        def repaired(wav, sr, transcript, **kwargs):
            calls.append((wav.copy(), sr, transcript, kwargs))
            plan = [{"cut_sample": 1200, "insert_ms": 100.0, "origin": "alignment"}]
            return np.concatenate([wav, np.ones(100, dtype=np.float32)]), plan, {
                "resolved_mode": "precise",
                "fallback": None,
            }

        monkeypatch.setattr(prosody_repair, "repair_segment_audio", repaired)
        wav, _sr, job_id = m._run_generate(
            "First. Second.",
            "English",
            prosody_repair=True,
            postprocess=False,
        )

        assert len(calls) == 1
        assert calls[0][2] == "First. Second."
        assert calls[0][3]["mode"] == "auto"
        assert isinstance(calls[0][3]["cancel_event"], type(threading.Event()))
        assert wav.size == 2500
        with m._active_jobs_lock:
            job = m._active_jobs[job_id]
        assert job.metadata["prosody_repair"]["outcome"] == "repaired"
        assert job.metadata["prosody_repair"]["boundary_count"] == 1
        assert job.metadata["applied_steps"] == ["prosody_repair"]

    def test_repair_failure_returns_original_audio(self, monkeypatch, model_module):
        m = model_module
        self._configure_model(monkeypatch, m)
        from qwen3_tts import prosody_repair

        monkeypatch.setattr(
            prosody_repair,
            "repair_segment_audio",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("aligner failed")),
        )
        expected = m._trim_silence(np.ones(2400, dtype=np.float32), 24000)
        wav, _sr, job_id = m._run_generate(
            "First. Second.",
            "English",
            prosody_repair=True,
            postprocess=False,
        )

        np.testing.assert_array_equal(wav, expected)
        with m._active_jobs_lock:
            metadata = m._active_jobs[job_id].metadata["prosody_repair"]
        assert metadata["outcome"] == "failed"
        assert metadata["error"] == "aligner failed"

    def test_repair_budget_abort_returns_original_audio(self, monkeypatch, model_module):
        m = model_module
        self._configure_model(monkeypatch, m)
        from qwen3_tts import prosody_repair

        release = threading.Event()

        def slow_repair(wav, sr, transcript, **kwargs):
            release.wait(timeout=1.0)
            return wav, [], {"resolved_mode": "precise", "fallback": "cancelled"}

        monkeypatch.setattr(prosody_repair, "repair_segment_audio", slow_repair)
        monkeypatch.setenv("GENERATION_REPAIR_BUDGET_SECONDS", "0.01")
        expected = m._trim_silence(np.ones(2400, dtype=np.float32), 24000)
        started = m.time.monotonic()
        wav, _sr, job_id = m._run_generate(
            "First. Second.",
            "English",
            prosody_repair=True,
            postprocess=False,
        )
        elapsed = m.time.monotonic() - started
        release.set()

        assert elapsed < 0.25
        np.testing.assert_array_equal(wav, expected)
        with m._active_jobs_lock:
            metadata = m._active_jobs[job_id].metadata["prosody_repair"]
        assert metadata["outcome"] == "budget_fallback"
        assert metadata["duration_seconds"] >= 0.01

    def test_default_dsp_kill_switch_does_not_disable_explicit_style(
        self, monkeypatch, model_module
    ):
        m = model_module
        self._configure_model(monkeypatch, m)
        monkeypatch.setenv("TTS_DEFAULT_DSP", "off")

        _wav, _sr, default_job_id = m._run_generate("hello", "English")
        _wav, _sr, explicit_job_id = m._run_generate(
            "hello", "English", style_preset="Neutral"
        )

        with m._active_jobs_lock:
            default_job = m._active_jobs[default_job_id]
            explicit_job = m._active_jobs[explicit_job_id]
        assert default_job.style_preset is None
        assert default_job.postprocess_applied is False
        assert explicit_job.style_preset == "Neutral"
        assert explicit_job.postprocess_applied is True

    def test_pocket_primary_runtime_applies_default_and_honors_bypass(
        self, monkeypatch, model_module
    ):
        m = model_module
        self._configure_model(monkeypatch, m)
        monkeypatch.setattr(m, "TTS_BACKEND", "pocket_tts")
        t = np.linspace(0.0, 3.0, 72000, endpoint=False, dtype=np.float32)
        source = (0.05 * np.sin(2 * np.pi * 180.0 * t)).astype(np.float32)
        fake_runtime = types.ModuleType("qwen3_tts.pocket_tts_runtime")
        fake_runtime.get_pocket_tts_voice_state = lambda *args, **kwargs: "voice-state"
        fake_runtime.generate_pocket_tts = lambda *args, **kwargs: (
            _FakeAudioTensor(source.copy()),
            24000,
        )
        monkeypatch.setitem(sys.modules, "qwen3_tts.pocket_tts_runtime", fake_runtime)
        # Fix isolation: monkeypatch the attribute on the package to prevent leak
        # Only if the package is actually imported and we can set the attribute
        import qwen3_tts
        setattr(qwen3_tts, "pocket_tts_runtime", fake_runtime)

        polished, _sr, polished_job_id = m._run_generate("hello", "English")
        bypassed, _sr, bypassed_job_id = m._run_generate(
            "hello", "English", postprocess=False
        )

        expected_trimmed = m._trim_silence(source, 24000)
        assert not np.array_equal(polished, expected_trimmed)
        assert np.array_equal(bypassed, expected_trimmed)
        with m._active_jobs_lock:
            polished_job = m._active_jobs[polished_job_id]
            bypassed_job = m._active_jobs[bypassed_job_id]
        assert polished_job.style_preset == "default"
        assert polished_job.postprocess_applied is True
        assert polished_job.metadata["applied_steps"] == ["normalize_lufs", "limit_peak"]
        assert bypassed_job.style_preset is None
        assert bypassed_job.postprocess_applied is False
