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
from pathlib import Path
from typing import Any

import pytest

from persona_forge.pocket_artifact_resolver import (
    KYUTAI_WITHOUT_CLONING_REPO,
    KYUTAI_WITHOUT_CLONING_REVISION,
    PocketArtifactError,
    SourceAttempt,
)

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
    rt.pocket_tts_provenance = {}
    rt.pocket_tts_artifact_dir = None

    yield rt

    rt.unload_pocket_tts()


class TestLoadPocketTtsModel:
    # Legacy-path (non-English) loads still forward plain language kwargs; the
    # English load goes through artifact resolution (see TestResolvedArtifactLoading).

    def test_forwards_core_kwargs(self, pocket_tts_runtime):
        rt = pocket_tts_runtime
        rt.load_pocket_tts_model(
            language="french_24l", temp=1.2, sampler_decode_steps=5, eos_threshold=-4.0
        )
        assert FakeTTSModel.last_load_kwargs == {
            "language": "french_24l",
            "temp": 1.2,
            "sampler_decode_steps": 5,
            "eos_threshold": -4.0,
            "quantize": False,
        }

    def test_forwards_noise_clamp_when_set(self, pocket_tts_runtime):
        rt = pocket_tts_runtime
        rt.load_pocket_tts_model(
            language="french_24l",
            temp=1.2,
            sampler_decode_steps=5,
            eos_threshold=-4.0,
            noise_clamp=0.3,
        )
        assert FakeTTSModel.last_load_kwargs["noise_clamp"] == 0.3

    def test_omits_noise_clamp_when_none(self, pocket_tts_runtime):
        """Regression: noise_clamp used to be accepted but never passed to TTSModel.load_model."""
        rt = pocket_tts_runtime
        rt.load_pocket_tts_model(
            language="french_24l", temp=1.2, sampler_decode_steps=5, eos_threshold=-4.0, noise_clamp=None
        )
        assert "noise_clamp" not in FakeTTSModel.last_load_kwargs

    def test_sets_global_model_handle(self, pocket_tts_runtime):
        rt = pocket_tts_runtime
        model = rt.load_pocket_tts_model(
            language="french_24l", temp=1.2, sampler_decode_steps=5, eos_threshold=-4.0
        )
        assert rt.pocket_tts_model is model

    def test_frames_after_eos_defaults_to_eight(self, pocket_tts_runtime):
        rt = pocket_tts_runtime
        rt.load_pocket_tts_model(
            language="french_24l", temp=1.2, sampler_decode_steps=5, eos_threshold=-4.0
        )
        assert rt.pocket_tts_frames_after_eos == 8

    def test_frames_after_eos_custom_value(self, pocket_tts_runtime):
        rt = pocket_tts_runtime
        rt.load_pocket_tts_model(
            language="french_24l",
            temp=1.2,
            sampler_decode_steps=5,
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


class TestTrimPostEosTail:
    """Regression coverage for the end-of-sentence clipping bug (docs/plans/20260812-*).

    A global relative threshold (3% of the whole clip's peak frame energy) let one loud
    early burst mask a genuinely quiet closing burst, causing real trailing speech to be
    trimmed away. The fix combines an absolute floor with a trailing-window relative term.
    """

    def _two_burst_waveform(self, torch, sr):
        frame_samples = round(sr / 12.5)
        loud = torch.ones(frame_samples * 4) * 0.9
        silence_gap = torch.zeros(frame_samples * 6)
        quiet = torch.ones(frame_samples * 4) * 0.05
        return torch.cat([loud, silence_gap, quiet])

    def test_quiet_closing_burst_survives_a_loud_earlier_burst(self, pocket_tts_runtime):
        torch = pytest.importorskip("torch")
        rt = pocket_tts_runtime
        sr = 24000
        audio = self._two_burst_waveform(torch, sr)

        trimmed = rt._trim_post_eos_tail(audio, sr, frames_after_eos=8)

        frame_samples = round(sr / 12.5)
        quiet_burst_end_sample = len(audio)
        # The quiet closing burst must not have been trimmed away.
        assert len(trimmed) >= quiet_burst_end_sample - frame_samples

    def test_still_trims_true_trailing_silence(self, pocket_tts_runtime):
        torch = pytest.importorskip("torch")
        rt = pocket_tts_runtime
        sr = 24000
        frame_samples = round(sr / 12.5)
        speech = torch.ones(frame_samples * 4) * 0.9
        trailing_silence = torch.zeros(frame_samples * 20)
        audio = torch.cat([speech, trailing_silence])

        trimmed = rt._trim_post_eos_tail(audio, sr, frames_after_eos=8)

        assert len(trimmed) < len(audio)


class TestUnloadPocketTts:
    def test_clears_model_and_cache(self, pocket_tts_runtime):
        rt = pocket_tts_runtime
        rt.load_pocket_tts_model(
            language="french_24l", temp=1.2, sampler_decode_steps=5, eos_threshold=-4.0
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
            language="french_24l", temp=1.2, sampler_decode_steps=5, eos_threshold=-4.0
        )
        rt.pocket_tts_voice_state_cache["vd_abc123"] = {"ref_path": "x.wav"}

        rt.load_pocket_tts_model(
            language="spanish_24l", temp=1.0, sampler_decode_steps=3, eos_threshold=-3.0
        )

        assert rt.pocket_tts_voice_state_cache == {}


# ---------------------------------------------------------------------------
# English load via resolved artifacts (pocket_tts-ungated Track A)
# ---------------------------------------------------------------------------


class StubResolveResult:
    """Mimics the fields of ResolutionResult that the runtime consumes."""

    def __init__(
        self,
        path,
        source_name: str = "lunahr",
        repo_id: str = "lunahr/pocket-tts-ungated",
        revision: str = "d03cd734",
        sha256: str = "4" * 64,
        from_cache: bool = False,
    ) -> None:
        self.path = Path(path)
        self.source_name = source_name
        self.repo_id = repo_id
        self.revision = revision
        self.sha256 = sha256
        self.from_cache = from_cache


def _stub_error(key: str, kind: str, source_name: str = "lunahr") -> PocketArtifactError:
    return PocketArtifactError(key, [SourceAttempt(source_name, kind)])


def install_stub_resolver(rt, monkeypatch, plans: dict, calls: list) -> None:
    """Patch rt.PocketArtifactResolver with a stub driven by ``plans``.

    ``plans`` maps artifact key -> StubResolveResult (return) or Exception (raise).
    ``calls`` records ``(key, allowed_sources)`` per resolve() call.
    """

    class StubResolver:
        def __init__(self, artifact_dir, token: str | None = None, catalog=None, fetch=None) -> None:
            pass

        def resolve(self, key: str, allowed_sources=None):
            calls.append((key, None if allowed_sources is None else tuple(allowed_sources)))
            plan = plans[key]
            if isinstance(plan, BaseException):
                raise plan
            return plan

    monkeypatch.setattr(rt, "PocketArtifactResolver", StubResolver)


NONCLONING_SOURCE = ("kyutai_without_cloning", "kyutai/pocket-tts-without-voice-cloning", "d29db79")


class TestResolvedArtifactLoading:
    """English loads must resolve pinned artifacts and use a project-owned config."""

    CLONE_SHA = "47" + "0" * 62
    NONCLONE_SHA = "be" + "0" * 62

    def _ready_plans(self, tmp_path) -> dict:
        clone = tmp_path / "model_cloning.safetensors"
        nonclone = tmp_path / "model_noncloning.safetensors"
        tokenizer = tmp_path / "tokenizer.model"
        for p in (clone, nonclone, tokenizer):
            p.write_bytes(b"stub-bytes")
        return {
            "model_cloning_english": StubResolveResult(clone, sha256=self.CLONE_SHA),
            "model_noncloning_english": StubResolveResult(
                nonclone, *NONCLONING_SOURCE, sha256=self.NONCLONE_SHA
            ),
            "tokenizer_english": StubResolveResult(tokenizer, *NONCLONING_SOURCE),
        }

    def test_english_load_uses_resolved_config_and_records_provenance(
        self, pocket_tts_runtime, tmp_path, monkeypatch
    ):
        rt = pocket_tts_runtime
        calls: list = []
        plans = self._ready_plans(tmp_path)
        install_stub_resolver(rt, monkeypatch, plans, calls)

        model = rt.load_pocket_tts_model(
            language="english",
            temp=1.2,
            sampler_decode_steps=5,
            eos_threshold=-4.0,
            model_source="auto",
            artifact_dir=tmp_path,
        )

        kwargs = FakeTTSModel.last_load_kwargs
        assert kwargs is not None
        assert "language" not in kwargs
        assert kwargs["config"] == str(tmp_path / "config" / "english-pf.yaml")
        assert kwargs["temp"] == 1.2
        assert kwargs["sampler_decode_steps"] == 5
        assert kwargs["eos_threshold"] == -4.0
        assert kwargs["quantize"] is False

        prov = rt.pocket_tts_provenance
        assert prov["model_source"] == "lunahr"
        assert prov["model_source_requested"] == "auto"
        assert prov["model_repo"] == "lunahr/pocket-tts-ungated"
        assert prov["model_sha256"] == self.CLONE_SHA
        assert prov["model_verified"] is True
        assert prov["cloning_available"] is True
        assert prov["cloning_status"] == "ready"
        assert prov["message"] == ""
        assert rt.pocket_tts_artifact_dir == str(tmp_path)
        # Ready mode must not disable the package's voice-cloning capability.
        assert getattr(model, "has_voice_cloning", True) is not False

        config_text = (tmp_path / "config" / "english-pf.yaml").read_text(encoding="utf-8")
        assert f'weights_path: "{plans["model_cloning_english"].path}"' in config_text
        assert f"tokenizer_path: \"{plans['tokenizer_english'].path}\"" in config_text

    def test_cloning_failure_degrades_to_builtin_only_in_auto(self, pocket_tts_runtime, tmp_path, monkeypatch):
        rt = pocket_tts_runtime
        calls: list = []
        plans = self._ready_plans(tmp_path)
        plans["model_cloning_english"] = _stub_error("model_cloning_english", "auth_required")
        install_stub_resolver(rt, monkeypatch, plans, calls)

        model = rt.load_pocket_tts_model(
            language="english",
            temp=1.2,
            sampler_decode_steps=5,
            eos_threshold=-4.0,
            model_source="auto",
            artifact_dir=tmp_path,
        )

        prov = rt.pocket_tts_provenance
        assert prov["model_source"] == "kyutai_without_cloning"
        assert prov["model_sha256"] == self.NONCLONE_SHA
        assert prov["cloning_available"] is False
        assert prov["cloning_status"] == "degraded"
        assert prov["message"] != ""
        assert model.has_voice_cloning is False
        assert rt.pocket_tts_cloning_available is False
        assert rt.pocket_tts_cloning_status_message == prov["message"]

        config_text = (tmp_path / "config" / "english-pf.yaml").read_text(encoding="utf-8")
        assert f'weights_path: "{plans["model_noncloning_english"].path}"' in config_text

    def test_degraded_load_keeps_provenance_message_on_ref_audio_failure(
        self, pocket_tts_runtime, tmp_path, monkeypatch
    ):
        rt = pocket_tts_runtime
        calls: list = []
        plans = self._ready_plans(tmp_path)
        plans["model_cloning_english"] = _stub_error("model_cloning_english", "auth_required")
        install_stub_resolver(rt, monkeypatch, plans, calls)

        model = rt.load_pocket_tts_model(
            language="english",
            temp=1.2,
            sampler_decode_steps=5,
            eos_threshold=-4.0,
            model_source="auto",
            artifact_dir=tmp_path,
        )
        provenance_message = rt.pocket_tts_provenance["message"]
        assert provenance_message

        ref = tmp_path / "ref.wav"
        ref.write_bytes(b"RIFF....")
        model.fail_on_audio_prompt.add(str(ref))

        assert rt.build_default_voice_state(model, str(ref)) is None
        # The load-time provenance message must survive, not be replaced by the
        # generic gated-terms fallback.
        assert rt.pocket_tts_cloning_status_message == provenance_message
        assert rt.pocket_tts_cloning_available is False

    def test_integrity_failure_reports_integrity_error(self, pocket_tts_runtime, tmp_path, monkeypatch):
        rt = pocket_tts_runtime
        calls: list = []
        plans = self._ready_plans(tmp_path)
        plans["model_cloning_english"] = _stub_error("model_cloning_english", "integrity_mismatch")
        install_stub_resolver(rt, monkeypatch, plans, calls)

        rt.load_pocket_tts_model(
            language="english",
            temp=1.2,
            sampler_decode_steps=5,
            eos_threshold=-4.0,
            model_source="auto",
            artifact_dir=tmp_path,
        )

        prov = rt.pocket_tts_provenance
        assert prov["cloning_status"] == "integrity_error"
        assert prov["cloning_available"] is False
        assert "integrity" in prov["message"].lower()
        assert rt.pocket_tts_model.has_voice_cloning is False

    def test_lunahr_mode_fails_closed_without_degradation(self, pocket_tts_runtime, tmp_path, monkeypatch):
        rt = pocket_tts_runtime
        calls: list = []
        plans = self._ready_plans(tmp_path)
        plans["model_cloning_english"] = _stub_error("model_cloning_english", "network_error")
        install_stub_resolver(rt, monkeypatch, plans, calls)

        with pytest.raises(RuntimeError, match="requires the voice-cloning model"):
            rt.load_pocket_tts_model(
                language="english",
                temp=1.2,
                sampler_decode_steps=5,
                eos_threshold=-4.0,
                model_source="lunahr",
                artifact_dir=tmp_path,
            )
        # No non-cloning fallback may be attempted in lunahr mode.
        assert all(key != "model_noncloning_english" for key, _ in calls)

    def test_local_mode_fails_closed_on_empty_cache(self, pocket_tts_runtime, tmp_path, monkeypatch):
        rt = pocket_tts_runtime
        calls: list = []
        plans = {
            "model_cloning_english": PocketArtifactError("model_cloning_english", []),
            "tokenizer_english": PocketArtifactError("tokenizer_english", []),
        }
        install_stub_resolver(rt, monkeypatch, plans, calls)

        with pytest.raises(RuntimeError, match="requires the voice-cloning model"):
            rt.load_pocket_tts_model(
                language="english",
                temp=1.2,
                sampler_decode_steps=5,
                eos_threshold=-4.0,
                model_source="local",
                artifact_dir=tmp_path,
            )

    def test_local_mode_loads_from_cache_only(self, pocket_tts_runtime, tmp_path, monkeypatch):
        rt = pocket_tts_runtime
        calls: list = []
        plans = self._ready_plans(tmp_path)
        plans["model_cloning_english"] = StubResolveResult(
            plans["model_cloning_english"].path, sha256=self.CLONE_SHA, from_cache=True
        )
        install_stub_resolver(rt, monkeypatch, plans, calls)

        rt.load_pocket_tts_model(
            language="english",
            temp=1.2,
            sampler_decode_steps=5,
            eos_threshold=-4.0,
            model_source="local",
            artifact_dir=tmp_path,
        )

        # local mode resolves strictly against the cache (empty allowed-sources tuple),
        # including the dormant non-cloning fallback entry (network-free).
        assert ("model_cloning_english", ()) in calls
        assert ("tokenizer_english", ()) in calls
        assert ("model_noncloning_english", ()) in calls
        assert rt.pocket_tts_provenance["voice_allowed_sources"] == []

    def test_invalid_model_source_rejected(self, pocket_tts_runtime):
        rt = pocket_tts_runtime
        with pytest.raises(ValueError, match="POCKET_TTS_MODEL_SOURCE"):
            rt.load_pocket_tts_model(
                language="english",
                temp=1.2,
                sampler_decode_steps=5,
                eos_threshold=-4.0,
                model_source="bogus",
            )

    def test_tokenizer_falls_back_to_public_hf_pin(self, pocket_tts_runtime, tmp_path, monkeypatch):
        rt = pocket_tts_runtime
        calls: list = []
        plans = self._ready_plans(tmp_path)
        plans["tokenizer_english"] = _stub_error("tokenizer_english", "network_error")
        install_stub_resolver(rt, monkeypatch, plans, calls)

        rt.load_pocket_tts_model(
            language="english",
            temp=1.2,
            sampler_decode_steps=5,
            eos_threshold=-4.0,
            model_source="auto",
            artifact_dir=tmp_path,
        )

        config_text = (tmp_path / "config" / "english-pf.yaml").read_text(encoding="utf-8")
        expected_pin = (
            f"tokenizer_path: \"hf://{KYUTAI_WITHOUT_CLONING_REPO}"
            f"/languages/english/tokenizer.model@{KYUTAI_WITHOUT_CLONING_REVISION}\""
        )
        assert expected_pin in config_text

    def test_non_english_load_skips_artifact_resolution(self, pocket_tts_runtime, tmp_path, monkeypatch):
        rt = pocket_tts_runtime
        calls: list = []
        plans = self._ready_plans(tmp_path)
        install_stub_resolver(rt, monkeypatch, plans, calls)

        rt.load_pocket_tts_model(
            language="french_24l", temp=1.0, sampler_decode_steps=3, eos_threshold=-3.0
        )

        assert calls == []
        prov = rt.pocket_tts_provenance
        assert prov["model_source"] is None
        assert prov["model_verified"] is False
        assert prov["cloning_status"] == "unavailable"
        assert rt.pocket_tts_artifact_dir is None
        kwargs = FakeTTSModel.last_load_kwargs
        assert kwargs is not None
        assert kwargs["language"] == "french_24l"

    def test_builtin_voice_resolves_to_verified_local_file(
        self, pocket_tts_runtime, tmp_path, monkeypatch
    ):
        rt = pocket_tts_runtime
        calls: list = []
        plans = self._ready_plans(tmp_path)
        voice_file = tmp_path / "alba.safetensors"
        voice_file.write_bytes(b"stub-bytes")
        plans["voice_embed_english_alba"] = StubResolveResult(voice_file)
        install_stub_resolver(rt, monkeypatch, plans, calls)

        model = rt.load_pocket_tts_model(
            language="english",
            temp=1.2,
            sampler_decode_steps=5,
            eos_threshold=-4.0,
            model_source="auto",
            artifact_dir=tmp_path,
        )
        state_cache = tmp_path / "state_cache"
        state_cache.mkdir()
        monkeypatch.setattr(rt, "STATE_CACHE_DIR", state_cache)

        # "pocket:" prefix is normalized; the pinned name resolves to the
        # verified local .safetensors (not the bare voice name).
        state = rt.get_pocket_tts_voice_state(model, "pocket:alba", None, None)

        assert state == {"ref_path": str(voice_file)}
        assert ("voice_embed_english_alba", None) in calls
        assert rt.pocket_tts_voice_state_cache["alba"] == state

    def test_builtin_voice_resolution_failure_raises(self, pocket_tts_runtime, tmp_path, monkeypatch):
        rt = pocket_tts_runtime
        calls: list = []
        plans = self._ready_plans(tmp_path)
        plans["voice_embed_english_alba"] = _stub_error(
            "voice_embed_english_alba", "integrity_mismatch", source_name="cache"
        )
        install_stub_resolver(rt, monkeypatch, plans, calls)

        model = rt.load_pocket_tts_model(
            language="english",
            temp=1.2,
            sampler_decode_steps=5,
            eos_threshold=-4.0,
            model_source="auto",
            artifact_dir=tmp_path,
        )
        state_cache = tmp_path / "state_cache"
        state_cache.mkdir()
        monkeypatch.setattr(rt, "STATE_CACHE_DIR", state_cache)

        with pytest.raises(RuntimeError, match="Could not resolve built-in voice 'alba'"):
            rt.get_pocket_tts_voice_state(model, "alba", None, None)
