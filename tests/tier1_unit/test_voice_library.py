"""Test voice_library CRUD, path traversal, ordering."""

from __future__ import annotations

import io
import json

import numpy as np
import pytest
import soundfile as sf

from qwen3_tts import voice_library


@pytest.fixture(autouse=True)
def tmp_voice_dir(tmp_path, monkeypatch):
    voice_library.VOICE_LIBRARY_DIR = tmp_path
    yield tmp_path


def _clipped_sine_wav_bytes(sr: int = 24000, duration: float = 4.0) -> bytes:
    t = np.linspace(0.0, duration, int(sr * duration), endpoint=False, dtype=np.float32)
    tone = (0.99 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, tone, sr, format="WAV", subtype="FLOAT")
    return buf.getvalue()


def _sine_wav_bytes(sr: int = 24000, duration: float = 4.0, amplitude: float = 0.05, lead_silence: float = 0.5) -> bytes:
    t = np.linspace(0.0, duration, int(sr * duration), endpoint=False, dtype=np.float32)
    tone = (amplitude * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)
    silence = np.zeros(int(sr * lead_silence), dtype=np.float32)
    wav = np.concatenate([silence, tone, silence])
    buf = io.BytesIO()
    sf.write(buf, wav, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


class TestSaveGet:
    def test_save_voice_persists_wav_and_metadata(self):
        meta = voice_library.save_voice(
            b"RIFF....", description="a calm narrator", sample_text="hello there", language="English"
        )
        assert meta["voice_id"].startswith("vd_")
        assert meta["description"] == "a calm narrator"
        assert meta["sample_text"] == "hello there"
        assert meta["language"] == "English"

    def test_get_voice_round_trips(self):
        saved = voice_library.save_voice(
            b"RIFF....", description="desc", sample_text="text", language="English"
        )
        fetched = voice_library.get_voice(saved["voice_id"])
        assert fetched is not None
        assert fetched["voice_id"] == saved["voice_id"]

    def test_get_voice_unknown(self):
        assert voice_library.get_voice("vd_000000000000") is None

    def test_quality_warnings_mark_voice_for_review(self, monkeypatch):
        monkeypatch.setattr(
            voice_library,
            "calculate_quality_score",
            lambda *_args, **_kwargs: (72.0, ["Long leading silence"], {"pause_ratio": 0.4}),
        )

        meta = voice_library.save_voice(
            b"RIFF....", description="desc", sample_text="text", language="English"
        )

        assert meta["needs_review"] is True

    def test_clipping_reference_is_auto_fixed_and_saved(self):
        meta = voice_library.save_voice(
            _clipped_sine_wav_bytes(),
            description="desc",
            sample_text="hello there friend",
            language="English",
        )

        assert meta["auto_fixed"] is True
        assert not voice_library._has_clipping_failure(
            meta["quality_warnings"], meta["metrics"]
        )

    def test_clipping_reference_still_failing_after_fix_raises(self, monkeypatch):
        monkeypatch.setattr(
            voice_library,
            "calculate_quality_score",
            lambda *_args, **_kwargs: (10.0, ["clipping detected"], {"peak_dbfs": 0.0}),
        )

        with pytest.raises(ValueError, match="clipping"):
            voice_library.save_voice(
                _clipped_sine_wav_bytes(),
                description="desc",
                sample_text="hello there friend",
                language="English",
            )


class TestPathTraversal:
    def test_rejects_dotdot(self):
        assert voice_library.get_voice("../../etc/passwd") is None

    def test_rejects_encoded_dotdot(self):
        assert voice_library.get_voice("vd_..%2f..%2fetc") is None


class TestWavBytes:
    def test_returns_saved_bytes(self):
        saved = voice_library.save_voice(
            b"RIFF-payload", description="desc", sample_text="text", language="English"
        )
        assert voice_library.get_voice_wav_bytes(saved["voice_id"]) == b"RIFF-payload"

    def test_unknown_returns_none(self):
        assert voice_library.get_voice_wav_bytes("vd_000000000000") is None


class TestListVoices:
    def test_newest_first(self):
        first = voice_library.save_voice(
            b"a", description="first", sample_text="text", language="English"
        )
        meta_path = voice_library.VOICE_LIBRARY_DIR / first["voice_id"] / "meta.json"
        data = json.loads(meta_path.read_text())
        data["created_at"] = 1.0
        meta_path.write_text(json.dumps(data))

        second = voice_library.save_voice(
            b"b", description="second", sample_text="text", language="English"
        )
        meta_path2 = voice_library.VOICE_LIBRARY_DIR / second["voice_id"] / "meta.json"
        data2 = json.loads(meta_path2.read_text())
        data2["created_at"] = 2.0
        meta_path2.write_text(json.dumps(data2))

        voices = voice_library.list_voices()
        assert [v["voice_id"] for v in voices] == [second["voice_id"], first["voice_id"]]

    def test_empty_when_missing(self):
        voice_library.VOICE_LIBRARY_DIR = voice_library.VOICE_LIBRARY_DIR / "nonexistent"
        assert voice_library.list_voices() == []


class TestUpdateDelete:
    def test_update_sample_text(self):
        saved = voice_library.save_voice(
            b"a", description="desc", sample_text="old", language="English"
        )
        updated = voice_library.update_voice(saved["voice_id"], sample_text="new text")
        assert updated is not None
        assert updated["sample_text"] == "new text"

    def test_delete_removes_directory(self):
        saved = voice_library.save_voice(
            b"a", description="desc", sample_text="text", language="English"
        )
        assert voice_library.delete_voice(saved["voice_id"]) is True
        assert not (voice_library.VOICE_LIBRARY_DIR / saved["voice_id"]).exists()

    def test_delete_nonexistent(self):
        assert voice_library.delete_voice("vd_000000000000") is False


class TestNormalizeReference:
    def test_normalizes_loudness_in_place(self):
        saved = voice_library.save_voice(
            _sine_wav_bytes(amplitude=0.05), description="desc", sample_text="hello there friend", language="English"
        )
        before = voice_library.get_voice_wav_bytes(saved["voice_id"])
        updated = voice_library.normalize_reference(saved["voice_id"])
        after = voice_library.get_voice_wav_bytes(saved["voice_id"])

        assert updated is not None
        assert after != before
        wav, sr = sf.read(io.BytesIO(after), dtype="float32")
        assert np.max(np.abs(wav)) > 0.05

    def test_unknown_voice_returns_none(self):
        assert voice_library.normalize_reference("vd_000000000000") is None


class TestTrimReferenceSilence:
    def test_trims_leading_and_trailing_silence(self):
        saved = voice_library.save_voice(
            _sine_wav_bytes(lead_silence=1.0), description="desc", sample_text="hello there friend", language="English"
        )
        before = voice_library.get_voice_wav_bytes(saved["voice_id"])
        updated = voice_library.trim_reference_silence(saved["voice_id"])
        after = voice_library.get_voice_wav_bytes(saved["voice_id"])

        before_wav, _ = sf.read(io.BytesIO(before), dtype="float32")
        after_wav, _ = sf.read(io.BytesIO(after), dtype="float32")

        assert updated is not None
        assert after_wav.size < before_wav.size

    def test_unknown_voice_returns_none(self):
        assert voice_library.trim_reference_silence("vd_000000000000") is None


class TestSetDefaultVariant:
    def test_marks_default_and_unmarks_siblings(self):
        first = voice_library.save_voice(
            b"a", description="desc", sample_text="text", language="English", family_id="fam1"
        )
        second = voice_library.create_voice_variant(first["voice_id"], "loud", "style")
        assert second is not None

        updated_second = voice_library.set_default_variant(second["voice_id"])
        assert updated_second["is_default"] is True

        refreshed_first = voice_library.get_voice(first["voice_id"])
        assert refreshed_first.get("is_default", False) is False

        updated_first = voice_library.set_default_variant(first["voice_id"])
        assert updated_first["is_default"] is True
        refreshed_second = voice_library.get_voice(second["voice_id"])
        assert refreshed_second.get("is_default", False) is False

    def test_voice_without_family_id_is_its_own_family(self):
        saved = voice_library.save_voice(
            b"a", description="desc", sample_text="text", language="English"
        )
        updated = voice_library.set_default_variant(saved["voice_id"])
        assert updated["is_default"] is True

    def test_unknown_voice_returns_none(self):
        assert voice_library.set_default_variant("vd_000000000000") is None
