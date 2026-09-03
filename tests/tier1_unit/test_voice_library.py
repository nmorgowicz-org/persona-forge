"""Test voice_library CRUD, path traversal, ordering."""

from __future__ import annotations

import io
import json

import numpy as np
import pytest
import soundfile as sf

from persona_forge import voice_library


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


def _paused_sine_wav_bytes(pause_seconds: float, sr: int = 24000) -> bytes:
    t = np.linspace(0.0, 1.0, sr, endpoint=False, dtype=np.float32)
    tone = (0.05 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)
    wav = np.concatenate([tone, np.zeros(int(sr * pause_seconds), dtype=np.float32), tone])
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

    def test_backfills_missing_metrics_without_changing_audio(self):
        saved = voice_library.save_voice(
            _sine_wav_bytes(), description="legacy", sample_text="hello there friend", language="English"
        )
        meta_path = voice_library.VOICE_LIBRARY_DIR / saved["voice_id"] / "meta.json"
        meta = json.loads(meta_path.read_text())
        meta["metrics"] = None
        meta_path.write_text(json.dumps(meta))
        before = voice_library.get_voice_wav_bytes(saved["voice_id"])

        listed = voice_library.list_voices()

        assert isinstance(listed[0]["metrics"], dict)
        assert voice_library.get_voice_wav_bytes(saved["voice_id"]) == before


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

    def test_duplicate_copies_audio_and_clears_default_flags(self):
        saved = voice_library.save_voice(
            _sine_wav_bytes(), description="original", sample_text="hello there friend", language="English"
        )
        source_meta_path = voice_library.VOICE_LIBRARY_DIR / saved["voice_id"] / "meta.json"
        source_meta = json.loads(source_meta_path.read_text())
        source_meta["is_default"] = True
        source_meta["api_active"] = True
        source_meta_path.write_text(json.dumps(source_meta))

        duplicate = voice_library.duplicate_voice(saved["voice_id"])

        assert duplicate is not None
        assert duplicate["voice_id"] != saved["voice_id"]
        assert duplicate["duplicated_from"] == saved["voice_id"]
        assert duplicate["description"] == "original (copy)"
        assert "is_default" not in duplicate
        assert "api_active" not in duplicate
        assert voice_library.get_voice_wav_bytes(duplicate["voice_id"]) == voice_library.get_voice_wav_bytes(saved["voice_id"])

    def test_duplicate_unknown_returns_none(self):
        assert voice_library.duplicate_voice("vd_000000000000") is None


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

    def test_audio_rewrite_can_be_undone(self):
        saved = voice_library.save_voice(
            _sine_wav_bytes(amplitude=0.05), description="desc", sample_text="hello there friend", language="English"
        )
        original = voice_library.get_voice_wav_bytes(saved["voice_id"])
        voice_library.normalize_reference(saved["voice_id"])
        assert voice_library.get_voice(saved["voice_id"])["undo_available"] is True

        restored = voice_library.undo_reference_edit(saved["voice_id"])

        assert restored is not None
        assert voice_library.get_voice_wav_bytes(saved["voice_id"]) == original
        assert restored["undo_available"] is False


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


class TestAdjustReferencePauses:
    @pytest.mark.parametrize(
        ("pace_multiplier", "initial_pause"),
        [(0.375, 0.8), (4.0, 0.1)],
    )
    def test_adjusts_a_single_unmatched_pause(self, pace_multiplier, initial_pause):
        saved = voice_library.save_voice(
            _paused_sine_wav_bytes(initial_pause),
            description="desc",
            sample_text="hello there friend",
            language="English",
        )
        before, sr = sf.read(io.BytesIO(voice_library.get_voice_wav_bytes(saved["voice_id"])), dtype="float32")
        before_gap = next(
            gap for gap in voice_library.detect_pause_intervals(before, sr)
            if gap[0] > 0 and gap[1] < before.size / sr
        )

        updated = voice_library.adjust_reference_pauses(
            saved["voice_id"], style_preset="Neutral", pace_multiplier=pace_multiplier
        )
        after, _ = sf.read(io.BytesIO(voice_library.get_voice_wav_bytes(saved["voice_id"])), dtype="float32")

        assert updated is not None
        after_gap = next(
            gap for gap in voice_library.detect_pause_intervals(after, sr)
            if gap[0] > 0 and gap[1] < after.size / sr
        )
        before_gap_ms = (before_gap[1] - before_gap[0]) * 1000
        after_gap_ms = (after_gap[1] - after_gap[0]) * 1000
        assert after_gap_ms == pytest.approx(before_gap_ms * pace_multiplier, abs=15)
        if pace_multiplier < 1.0:
            assert after.size < before.size
            assert after_gap[1] - after_gap[0] < before_gap[1] - before_gap[0]
        else:
            assert after.size > before.size
            assert after_gap[1] - after_gap[0] > before_gap[1] - before_gap[0]

    def test_unknown_voice_returns_none(self):
        assert voice_library.adjust_reference_pauses("vd_000000000000") is None


class TestVariantSubIds:
    """Lineage-preserving vd_<parent_hex>.<slug> sub-IDs (§1/§2/§3 of the prosody-variants
    redesign): validation stays a strict path-traversal-safe allowlist, a dotted ID resolves
    straight to its saved take regardless of current.wav, and save/promote are independent."""

    def _save(self):
        return voice_library.save_voice(
            _paused_sine_wav_bytes(0.8),
            description="desc",
            sample_text="hello there friend",
            language="English",
        )

    @pytest.mark.parametrize(
        "candidate",
        [
            "vd_abcdef012345.clean-1x",
            "vd_abcdef012345.Clean-1x",  # uppercase not allowed
            "vd_abcdef012345..clean-1x",  # nested dot
            "vd_abcdef012345/../etc",
            "vd_abcdef012345.../../etc",
            "vd_abcdef012345.-leading-dash",
            "vd_abcdef012345.",
            "vd_abcdef012345",
        ],
    )
    def test_dotted_id_validation_allowlist(self, candidate):
        expected = candidate in ("vd_abcdef012345.clean-1x", "vd_abcdef012345")
        assert voice_library._is_valid_voice_id(candidate) is expected

    def test_parse_voice_id_splits_parent_and_slug(self):
        assert voice_library.parse_voice_id("vd_abcdef012345.clean-1x") == (
            "vd_abcdef012345",
            "clean-1x",
        )
        assert voice_library.parse_voice_id("vd_abcdef012345") == ("vd_abcdef012345", None)

    def test_dotted_id_resolves_to_saved_variant_regardless_of_promotion(self):
        voice_id = self._save()["voice_id"]
        saved = voice_library.save_prosody_variant(voice_id, style_preset="Neutral", pace_multiplier=2.0)
        assert saved is not None
        variant_id = saved["variant_id"]
        variant_filename = voice_library._load_variants_meta(voice_id)[saved["variant_slug"]]["filename"]

        # Promote a *different* variant to active — the dotted sub-ID must still resolve to
        # its own saved take, not whatever current.wav points at.
        other_saved = voice_library.save_prosody_variant(voice_id, style_preset="Storyteller", pace_multiplier=0.5)
        assert other_saved is not None
        other_filename = voice_library._load_variants_meta(voice_id)[other_saved["variant_slug"]]["filename"]
        assert other_filename != variant_filename
        assert voice_library.set_active_variant(voice_id, other_filename) is True

        variant_meta = voice_library.get_voice(variant_id)
        assert variant_meta is not None
        assert variant_meta["parent_voice_id"] == voice_id
        assert variant_meta["voice_id"] == variant_id
        assert variant_meta["undo_available"] is False

        active_wav = voice_library.get_voice_wav_bytes(voice_id)
        variant_wav = voice_library.get_voice_wav_bytes(variant_id)
        assert active_wav != variant_wav

    def test_unknown_slug_returns_none(self):
        voice_id = self._save()["voice_id"]
        assert voice_library.get_voice(f"{voice_id}.does-not-exist") is None


class TestSaveVsPromoteSplit:
    """save_prosody_variant (bake-only) must never change what's served; promoting via
    set_active_variant/adjust_reference_pauses is a separate, explicit step."""

    def _save(self):
        return voice_library.save_voice(
            _paused_sine_wav_bytes(0.8),
            description="desc",
            sample_text="hello there friend",
            language="English",
        )

    def test_save_prosody_variant_does_not_change_served_audio(self):
        voice_id = self._save()["voice_id"]
        before = voice_library.get_voice_wav_bytes(voice_id)

        saved = voice_library.save_prosody_variant(voice_id, style_preset="Neutral", pace_multiplier=2.0)
        assert saved is not None
        assert saved["variant_id"].startswith(f"{voice_id}.")

        after = voice_library.get_voice_wav_bytes(voice_id)
        assert after == before  # unchanged — save-only, no promotion

    def test_adjust_reference_pauses_still_saves_and_promotes_atomically(self):
        voice_id = self._save()["voice_id"]
        before = voice_library.get_voice_wav_bytes(voice_id)

        updated = voice_library.adjust_reference_pauses(voice_id, style_preset="Neutral", pace_multiplier=2.0)
        assert updated is not None

        after = voice_library.get_voice_wav_bytes(voice_id)
        assert after != before  # promoted — current.wav now serves the new variant


class TestVariantMetricsNonPersisting:
    """compute_variant_metrics must never mutate the parent's meta.json, unlike analyze_reference."""

    def _save(self):
        return voice_library.save_voice(
            _paused_sine_wav_bytes(0.8),
            description="desc",
            sample_text="hello there friend",
            language="English",
        )

    def test_does_not_persist_metrics_to_parent_meta(self):
        voice_id = self._save()["voice_id"]
        meta_path = voice_library._voice_dir(voice_id) / "meta.json"
        before = meta_path.read_text(encoding="utf-8")

        result = voice_library.compute_variant_metrics(voice_id, "original.wav")
        assert result is not None
        assert "metrics" in result and "quality_score" in result

        assert meta_path.read_text(encoding="utf-8") == before

    def test_computes_metrics_for_saved_variant_file(self):
        voice_id = self._save()["voice_id"]
        saved = voice_library.save_prosody_variant(voice_id, style_preset="Neutral", pace_multiplier=2.0)
        assert saved is not None
        variant_filename = voice_library._load_variants_meta(voice_id)[saved["variant_slug"]]["filename"]

        result = voice_library.compute_variant_metrics(voice_id, variant_filename)
        assert result is not None
        assert "metrics" in result

    def test_unknown_voice_returns_none(self):
        assert voice_library.compute_variant_metrics("vd_000000000000", "original.wav") is None

    def test_rejects_disallowed_filename(self):
        voice_id = self._save()["voice_id"]
        assert voice_library.compute_variant_metrics(voice_id, "../meta.json") is None


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
def test_ensure_mounted_ref_voice_replaces_changed_mount_and_resets_current(tmp_path):
    # Keep the simulated mounted file outside the library root so the read-only
    # mount detector sees the same topology as a container bind mount.
    voice_library.VOICE_LIBRARY_DIR = tmp_path / "library"
    ref_audio = tmp_path / "reference.wav"
    ref_audio.write_bytes(_sine_wav_bytes(amplitude=0.05))

    voice_id = voice_library.ensure_mounted_ref_voice(
        str(ref_audio), sample_text="first transcript", asr={"severity": "ok"}
    )
    assert voice_id == voice_library.MOUNTED_REF_VOICE_ID

    voice_dir = voice_library._voice_dir(voice_id)
    stale_variant = voice_dir / "prosody_stale.wav"
    stale_variant.write_bytes(_sine_wav_bytes(amplitude=0.01))
    (voice_dir / "current.wav").unlink()
    (voice_dir / "current.wav").symlink_to(stale_variant)

    ref_audio.write_bytes(_sine_wav_bytes(amplitude=0.15, lead_silence=0.0))
    voice_library.ensure_mounted_ref_voice(
        str(ref_audio), sample_text="second transcript", asr={"severity": "warn"}
    )

    assert (voice_dir / "original.wav").resolve() == ref_audio.resolve()
    assert (voice_dir / "current.wav").resolve() == ref_audio.resolve()
    meta = json.loads((voice_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["sample_text"] == "second transcript"
    assert meta["asr"]["severity"] == "warn"
    assert voice_library.is_mounted_or_readonly_reference(voice_id)
