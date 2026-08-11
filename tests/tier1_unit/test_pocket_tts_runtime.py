"""Test pocket_tts_runtime — load/unload, voice_state resolution, cache invalidation.

pocket_tts_runtime.py imports `from pocket_tts import TTSModel` at module scope, but the
real `pocket-tts` PyPI package isn't installed in the dev/test environment (it's only
pulled in the Docker image). We install a fake `pocket_tts` module into sys.modules before
importing persona_forge.pocket_tts_runtime so the module under test can be exercised without
the real dependency.
"""

from __future__ import annotations

import os
import sys
import types
from typing import Any

import pytest

pytestmark = pytest.mark.requires_torch


class FakeTTSModel:
    """Stand-in for pocket_tts.TTSModel that records how it was constructed."""

    last_load_kwargs: dict[str, Any] | None = None
    fail_on_audio_prompt: set[str]

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.sample_rate = 24000
        self.fail_on_audio_prompt = set()

    @classmethod
    def load_model(cls, **kwargs: Any) -> "FakeTTSModel":
        cls.last_load_kwargs = kwargs
        return cls(**kwargs)

    def get_state_for_audio_prompt(self, path: str) -> dict[str, Any]:
        if path in self.fail_on_audio_prompt:
            raise RuntimeError(
                "We could not download the weights for the model with voice cloning"
            )
        return {"ref_path": path}

    def generate_audio(self, voice_state: dict[str, Any], text: str) -> torch.Tensor:
        torch = pytest.importorskip("torch")
        return torch.ones(2000)  # ~1 frame at 24kHz/12fps

    def export_model_state(self, state: dict[str, Any], path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(state.get("ref_path", "")))

    def import_model_state(self, path: str) -> dict[str, Any]:
        with open(path, encoding="utf-8") as f:
            return {"imported_ref_path": f.read()}


@pytest.fixture
def pocket_tts_runtime(monkeypatch):
    """Import (or reuse) persona_forge.pocket_tts_runtime with a fake `pocket_tts` backing it,
    and reset all of its module-level state before and after each test.
    """
    fake_module = types.ModuleType("pocket_tts")
    fake_module.TTSModel = FakeTTSModel
    monkeypatch.setitem(sys.modules, "pocket_tts", fake_module)

    sys.modules.pop("persona_forge.pocket_tts_runtime", None)
    from persona_forge import pocket_tts_runtime as rt

    rt.unload_pocket_tts()
    rt.pocket_tts_cloning_available = False
    rt.pocket_tts_cloning_status_message = ""
    rt.pocket_tts_frames_after_eos = 4

    yield rt

    rt.unload_pocket_tts()


class TestLoadPocketTtsModel:
    def test_forwards_core_kwargs(self, pocket_tts_runtime):
        rt = pocket_tts_runtime
        rt.load_pocket_tts_model(
            language="english", temp=1.2, lsd_decode_steps=5, eos_threshold=-4.0
        )
        assert FakeTTSModel.last_load_kwargs == {
            "language": "english",
            "temp": 1.2,
            "lsd_decode_steps": 5,
            "eos_threshold": -4.0,
            "quantize": False,
        }

    def test_forwards_noise_clamp_when_set(self, pocket_tts_runtime):
        rt = pocket_tts_runtime
        rt.load_pocket_tts_model(
            language="english",
            temp=1.2,
            lsd_decode_steps=5,
            eos_threshold=-4.0,
            noise_clamp=0.3,
        )
        assert FakeTTSModel.last_load_kwargs["noise_clamp"] == 0.3

    def test_omits_noise_clamp_when_none(self, pocket_tts_runtime):
        """Regression: noise_clamp used to be accepted but never passed to TTSModel.load_model."""
        rt = pocket_tts_runtime
        rt.load_pocket_tts_model(
            language="english", temp=1.2, lsd_decode_steps=5, eos_threshold=-4.0, noise_clamp=None
        )
        assert "noise_clamp" not in FakeTTSModel.last_load_kwargs

    def test_sets_global_model_handle(self, pocket_tts_runtime):
        rt = pocket_tts_runtime
        model = rt.load_pocket_tts_model(
            language="english", temp=1.2, lsd_decode_steps=5, eos_threshold=-4.0
        )
        assert rt.pocket_tts_model is model

    def test_frames_after_eos_defaults_to_four(self, pocket_tts_runtime):
        rt = pocket_tts_runtime
        rt.load_pocket_tts_model(
            language="english", temp=1.2, lsd_decode_steps=5, eos_threshold=-4.0
        )
        assert rt.pocket_tts_frames_after_eos == 4

    def test_frames_after_eos_custom_value(self, pocket_tts_runtime):
        rt = pocket_tts_runtime
        rt.load_pocket_tts_model(
            language="english",
            temp=1.2,
            lsd_decode_steps=5,
            eos_threshold=-4.0,
            frames_after_eos=8,
        )
        assert rt.pocket_tts_frames_after_eos == 8


class TestBuildDefaultVoiceState:
    def test_none_ref_audio_path(self, pocket_tts_runtime):
        rt = pocket_tts_runtime
        model = FakeTTSModel()
        assert rt.build_default_voice_state(model, None) is None

    def test_missing_file(self, pocket_tts_runtime, tmp_path):
        rt = pocket_tts_runtime
        model = FakeTTSModel()
        missing = str(tmp_path / "nope.wav")
        assert rt.build_default_voice_state(model, missing) is None

    def test_success_sets_cloning_available(self, pocket_tts_runtime, tmp_path):
        rt = pocket_tts_runtime
        ref = tmp_path / "ref.wav"
        ref.write_bytes(b"RIFF....")
        model = FakeTTSModel()
        state = rt.build_default_voice_state(model, str(ref))
        assert state == {"ref_path": str(ref)}
        assert rt.pocket_tts_cloning_available is True
        assert rt.pocket_tts_cloning_status_message == ""

    def test_gated_model_failure_sets_status_message(self, pocket_tts_runtime, tmp_path):
        rt = pocket_tts_runtime
        ref = tmp_path / "ref.wav"
        ref.write_bytes(b"RIFF....")
        model = FakeTTSModel()
        model.fail_on_audio_prompt.add(str(ref))
        state = rt.build_default_voice_state(model, str(ref))
        assert state is None
        assert rt.pocket_tts_cloning_available is False
        assert "huggingface.co/kyutai/pocket-tts" in rt.pocket_tts_cloning_status_message


class TestGetPocketTtsVoiceState:
    def test_uses_default_when_no_voice_id(self, pocket_tts_runtime):
        rt = pocket_tts_runtime
        model = FakeTTSModel()
        default_state = {"ref_path": "default.wav"}
        result = rt.get_pocket_tts_voice_state(model, None, default_state, None)
        assert result is default_state

    def test_raises_when_no_default_and_no_ref_audio(self, pocket_tts_runtime):
        rt = pocket_tts_runtime
        model = FakeTTSModel()
        with pytest.raises(RuntimeError, match="Voice cloning model not available"):
            rt.get_pocket_tts_voice_state(model, None, None, None)

    def test_library_voice_gets_cached(self, pocket_tts_runtime, tmp_path, monkeypatch):
        rt = pocket_tts_runtime
        model = FakeTTSModel()
        wav = tmp_path / "reference.wav"
        wav.write_bytes(b"RIFF....")

        from persona_forge import voice_library

        monkeypatch.setattr(
            voice_library, "get_voice", lambda vid: {"voice_id": vid, "wav_path": str(wav)}
        )

        result = rt.get_pocket_tts_voice_state(model, "vd_abc123", None, None)
        assert result == {"ref_path": str(wav)}
        assert rt.pocket_tts_voice_state_cache["vd_abc123"] == result

    def test_unknown_voice_id_raises(self, pocket_tts_runtime, monkeypatch):
        rt = pocket_tts_runtime
        model = FakeTTSModel()

        from persona_forge import voice_library

        monkeypatch.setattr(voice_library, "get_voice", lambda vid: None)

        with pytest.raises(ValueError, match=r"voice_id .* not found in voice_library"):
            rt.get_pocket_tts_voice_state(model, "vd_missing", None, None)


class TestInvalidateVoiceState:
    def test_removes_cached_entry(self, pocket_tts_runtime):
        """Regression: deleting a voice used to leave its voice_state servable from cache."""
        rt = pocket_tts_runtime
        rt.pocket_tts_voice_state_cache["vd_abc123"] = {"ref_path": "whatever.wav"}

        rt.invalidate_voice_state("vd_abc123")

        assert "vd_abc123" not in rt.pocket_tts_voice_state_cache

    def test_unknown_voice_id_is_a_noop(self, pocket_tts_runtime):
        rt = pocket_tts_runtime
        rt.invalidate_voice_state("vd_never_cached")  # must not raise

    def test_deleted_voice_cannot_be_regenerated_from_cache(self, pocket_tts_runtime, tmp_path, monkeypatch):
        rt = pocket_tts_runtime
        model = FakeTTSModel()
        wav = tmp_path / "reference.wav"
        wav.write_bytes(b"RIFF....")

        from persona_forge import voice_library

        monkeypatch.setattr(
            voice_library, "get_voice", lambda vid: {"voice_id": vid, "wav_path": str(wav)}
        )
        rt.get_pocket_tts_voice_state(model, "vd_abc123", None, None)
        assert "vd_abc123" in rt.pocket_tts_voice_state_cache

        # Simulate deletion: library no longer knows about the voice, cache is invalidated.
        monkeypatch.setattr(voice_library, "get_voice", lambda vid: None)
        rt.invalidate_voice_state("vd_abc123")

        with pytest.raises(ValueError, match=r"voice_id .* not found in voice_library"):
            rt.get_pocket_tts_voice_state(model, "vd_abc123", None, None)

    def test_updated_voice_rebuilds_stale_disk_cache(self, pocket_tts_runtime, tmp_path, monkeypatch):
        rt = pocket_tts_runtime
        model = FakeTTSModel()
        voice_dir = tmp_path / "vd_abc123"
        voice_dir.mkdir()
        wav = voice_dir / "reference.wav"
        wav.write_bytes(b"RIFF....")
        meta_path = voice_dir / "meta.json"
        meta_path.write_text("{}", encoding="utf-8")

        from persona_forge import voice_library

        monkeypatch.setattr(voice_library, "VOICE_LIBRARY_DIR", tmp_path)
        monkeypatch.setattr(rt, "VOICE_LIBRARY_DIR", tmp_path)
        monkeypatch.setattr(rt, "STATE_CACHE_DIR", tmp_path / ".state_cache")
        rt.STATE_CACHE_DIR.mkdir()
        monkeypatch.setattr(
            voice_library, "get_voice", lambda vid: {"voice_id": vid, "wav_path": str(wav)}
        )

        cache_path = rt._state_cache_path("vd_abc123")
        cache_path.write_text("old-reference.wav", encoding="utf-8")
        old_time = wav.stat().st_mtime - 10
        os.utime(cache_path, (old_time, old_time))

        result = rt.get_pocket_tts_voice_state(model, "vd_abc123", None, None)

        assert result == {"ref_path": str(wav)}
        assert rt.pocket_tts_voice_state_cache["vd_abc123"] == result


class TestGeneratePocketTts:
    def test_generates_audio_tuple(self, pocket_tts_runtime):
        torch = pytest.importorskip("torch")
        rt = pocket_tts_runtime
        model = FakeTTSModel()
        audio, sr = rt.generate_pocket_tts(model, {"ref_path": "x.wav"}, "hello world")
        assert isinstance(audio, torch.Tensor)
        assert sr == 24000

    def test_raises_without_model(self, pocket_tts_runtime):
        rt = pocket_tts_runtime
        with pytest.raises(RuntimeError, match="Model is not loaded"):
            rt.generate_pocket_tts(None, {"ref_path": "x.wav"}, "hello")

    def test_raises_without_voice_state(self, pocket_tts_runtime):
        rt = pocket_tts_runtime
        model = FakeTTSModel()
        with pytest.raises(RuntimeError, match="voice_state is missing"):
            rt.generate_pocket_tts(model, {}, "hello")

    def test_raises_on_empty_text(self, pocket_tts_runtime):
        rt = pocket_tts_runtime
        model = FakeTTSModel()
        with pytest.raises(ValueError, match="Input text is empty"):
            rt.generate_pocket_tts(model, {"ref_path": "x.wav"}, "")


class TestUnloadPocketTts:
    def test_clears_model_and_cache(self, pocket_tts_runtime):
        rt = pocket_tts_runtime
        rt.load_pocket_tts_model(
            language="english", temp=1.2, lsd_decode_steps=5, eos_threshold=-4.0
        )
        rt.pocket_tts_voice_state_cache["vd_abc123"] = {"ref_path": "x.wav"}
        rt.pocket_tts_default_voice_state = {"ref_path": "default.wav"}

        rt.unload_pocket_tts()

        assert rt.pocket_tts_model is None
        assert rt.pocket_tts_default_voice_state is None
        assert rt.pocket_tts_voice_state_cache == {}

    def test_reload_clears_previous_cache(self, pocket_tts_runtime):
        """load_pocket_tts_model always unloads first, so no stale state survives a hotswap."""
        rt = pocket_tts_runtime
        rt.load_pocket_tts_model(
            language="english", temp=1.2, lsd_decode_steps=5, eos_threshold=-4.0
        )
        rt.pocket_tts_voice_state_cache["vd_abc123"] = {"ref_path": "x.wav"}

        rt.load_pocket_tts_model(
            language="french_24l", temp=1.0, lsd_decode_steps=3, eos_threshold=-3.0
        )

        assert rt.pocket_tts_voice_state_cache == {}
