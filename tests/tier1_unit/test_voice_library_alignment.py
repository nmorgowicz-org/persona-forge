"""Phase 2 gate: voice_library alignment cache — compute, persist, invalidate."""

from __future__ import annotations

import io
import json

import numpy as np
import pytest
import soundfile as sf

from qwen3_tts import forced_alignment as fa
from qwen3_tts import voice_library


@pytest.fixture(autouse=True)
def tmp_voice_dir(tmp_path, monkeypatch):
    voice_library.VOICE_LIBRARY_DIR = tmp_path
    yield tmp_path


def _wav_bytes(sr=24000, seconds=3.0):
    t = np.linspace(0.0, seconds, int(sr * seconds), endpoint=False, dtype=np.float32)
    tone = (0.05 * np.sin(2 * np.pi * 180.0 * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, tone, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


class _CountingEmitter:
    """Emits per-frame character logits for the transcript; counts invocations."""

    def __init__(self, transcript):
        self.calls = 0
        words = [t["word"] for t in fa.normalize_transcript(transcript)]
        plan = []
        for wi, word in enumerate(words):
            for ch in word:
                plan.extend([fa.VOCAB.get(ch, fa.VOCAB["<unk>"])] * 4)
            if wi < len(words) - 1:
                plan.extend([fa.BLANK] * 3)
        self._plan = plan

    def __call__(self, _wav16k):
        self.calls += 1
        logits = np.zeros((len(self._plan), 31), dtype=np.float32)
        for t, cid in enumerate(self._plan):
            logits[t, cid] = 8.0
        return logits


def _save(sample_text="Hello there. How are you?"):
    meta = voice_library.save_voice(
        _wav_bytes(), description="d", sample_text=sample_text, language="English"
    )
    return meta["voice_id"]


def _meta_alignment(voice_id):
    meta = voice_library.get_voice(voice_id)
    return meta.get("alignment")


def test_computes_persists_and_hits_cache():
    text = "Hello there. How are you?"
    vid = _save(text)
    emit = _CountingEmitter(text)

    first = voice_library.get_or_compute_alignment(vid, emit=emit)
    assert first is not None
    assert emit.calls == 1
    assert first["model_revision"] == fa.MODEL_REVISION
    assert [b["text"] for b in first["boundaries"]] == ["hello", "there", "how", "are", "you"]
    # Persisted to meta.json.
    assert _meta_alignment(vid) is not None

    # Second call is a cache hit — emitter not invoked again.
    second = voice_library.get_or_compute_alignment(vid, emit=emit)
    assert emit.calls == 1
    assert second == first


def test_transcript_edit_invalidates_cache():
    vid = _save("Hello there. How are you?")
    emit1 = _CountingEmitter("Hello there. How are you?")
    voice_library.get_or_compute_alignment(vid, emit=emit1)
    assert emit1.calls == 1

    # Editing the transcript must invalidate even though audio is unchanged.
    voice_library.update_voice(vid, sample_text="Totally different words here now.")
    emit2 = _CountingEmitter("Totally different words here now.")
    record = voice_library.get_or_compute_alignment(vid, emit=emit2)
    assert emit2.calls == 1
    assert record["transcript_sha256"] == fa.sha256_text("Totally different words here now.")
    assert [b["text"] for b in record["boundaries"]][0] == "totally"


def test_force_recomputes():
    text = "Hello there. Bye now."
    vid = _save(text)
    emit = _CountingEmitter(text)
    voice_library.get_or_compute_alignment(vid, emit=emit)
    voice_library.get_or_compute_alignment(vid, emit=emit, force=True)
    assert emit.calls == 2


def test_missing_transcript_raises():
    meta = voice_library.save_voice(_wav_bytes(), description="d", sample_text="", language="English")
    with pytest.raises(ValueError):
        voice_library.get_or_compute_alignment(meta["voice_id"], emit=_CountingEmitter("x"))


def test_unknown_voice_returns_none():
    assert voice_library.get_or_compute_alignment("vd_000000000000", emit=_CountingEmitter("x")) is None


def test_cancel_before_compute_returns_none():
    import threading

    vid = _save("Hello there. Bye now.")
    cancel = threading.Event()
    cancel.set()
    emit = _CountingEmitter("Hello there. Bye now.")
    result = voice_library.get_or_compute_alignment(vid, emit=emit, cancel=cancel)
    assert result is None
    assert emit.calls == 0  # cancelled before running the model


# --- Phase 3: alignment-directed surgical pauses -----------------------------

class TestBuildAlignmentPauseEdits:
    def test_maps_sentence_and_clause_owners(self):
        boundaries = [
            {"text": "hi", "start": 0.0, "end": 0.4, "kind": "sentence_split", "owns_clause": False},
            {"text": "yes", "start": 0.4, "end": 0.8, "kind": "word", "owns_clause": True},
            {"text": "no", "start": 0.95, "end": 1.2, "kind": "word", "owns_clause": False},
        ]
        edits = voice_library.build_alignment_pause_edits(boundaries, "Storyteller", 1.0, 0.0)
        # sentence_split → sentence_end (1000ms); clause owner → comma (500ms); plain word skipped.
        assert [e["target_ms"] for e in edits] == [1000.0, 500.0]
        assert edits[0]["at_ms"] == 400.0  # word-end of the sentence owner

    def test_existing_gap_is_measured_from_next_word(self):
        boundaries = [
            {"text": "a", "start": 0.0, "end": 0.4, "kind": "sentence_split", "owns_clause": False},
            {"text": "b", "start": 0.55, "end": 0.9, "kind": "word", "owns_clause": False},
        ]
        edits = voice_library.build_alignment_pause_edits(boundaries, "Neutral", 1.0, 0.0)
        assert edits[0]["existing_ms"] == pytest.approx(150.0, abs=1e-6)

    def test_uncertain_boundaries_are_skipped(self):
        boundaries = [
            {"text": "x", "start": 0.0, "end": 0.4, "kind": "uncertain", "owns_clause": True},
        ]
        assert voice_library.build_alignment_pause_edits(boundaries, "Neutral", 1.0, 0.0) == []

    def test_pace_and_offset_applied(self):
        boundaries = [
            {"text": "a", "start": 0.0, "end": 0.4, "kind": "sentence_split", "owns_clause": False},
        ]
        edits = voice_library.build_alignment_pause_edits(boundaries, "Neutral", 2.0, 100.0)
        # Neutral sentence_end = 500ms → 500*2 + 100 = 1100ms.
        assert edits[0]["target_ms"] == pytest.approx(1100.0)


class TestAlignmentDirectedWav:
    def test_precise_inserts_pauses_and_persists_alignment(self):
        text = "Hello there. How are you?"
        vid = _save(text)
        emit = _CountingEmitter(text)
        base = voice_library.get_prosody_adjusted_wav(vid, "Storyteller", 1.0, 0.0, "natural")
        assert base is not None
        base_len = base[0].size

        result = voice_library.get_alignment_directed_wav(
            vid, "Storyteller", 1.0, 0.0, mode="precise", emit=emit
        )
        assert result is not None
        adjusted, sr = result
        # "there." owns the interior sentence boundary → a Storyteller 1000ms pause is inserted.
        assert adjusted.size > base_len
        # Alignment was cached to meta.json as a side effect.
        assert _meta_alignment(vid) is not None

        preview = voice_library.get_prosody_adjusted_wav(
            vid, "Storyteller", 1.0, 0.0, "precise", return_plan=True
        )
        assert preview is not None
        preview_wav, preview_sr, plan = preview
        assert plan
        assert plan[0]["origin"] == "alignment"
        assert plan[0]["insert_ms"] > 0
        assert plan[0]["cut_sample"] < preview_wav.size

        # The saved variant reuses the same cached alignment and canonical renderer.
        variant = voice_library.create_prosody_variant(
            vid, "Storyteller", 1.0, 0.0, mode="precise"
        )
        assert variant is not None
        saved, saved_sr = sf.read(voice_library._voice_dir(vid) / variant, dtype="float32")
        preview_buf = io.BytesIO()
        sf.write(preview_buf, preview_wav, preview_sr, format="WAV", subtype="PCM_16")
        preview_buf.seek(0)
        encoded_preview, encoded_sr = sf.read(preview_buf, dtype="float32")
        assert saved_sr == encoded_sr
        assert np.array_equal(saved, encoded_preview)

    def test_no_transcript_returns_none(self):
        meta = voice_library.save_voice(
            _wav_bytes(), description="d", sample_text="", language="English"
        )
        assert voice_library.get_alignment_directed_wav(
            meta["voice_id"], "Storyteller", 1.0, 0.0, mode="precise"
        ) is None

    def test_get_prosody_adjusted_falls_back_when_alignment_unavailable(self):
        # No transcript → alignment-directed yields None; precise must still return audio
        # via the energy path (never worse than status quo).
        meta = voice_library.save_voice(
            _wav_bytes(), description="d", sample_text="", language="English"
        )
        result = voice_library.get_prosody_adjusted_wav(
            meta["voice_id"], "Neutral", 1.0, 0.0, "precise"
        )
        assert result is not None


class TestVadDirectedWav:
    """Plan §5.5 step 3: alignment-free surgical insertion via proportional punctuation
    placement + VAD-safe anti-click cut."""

    def test_places_pause_at_proportional_punctuation(self):
        wav = np.asarray(
            0.1 * np.sin(2 * np.pi * 180.0 * np.linspace(0, 2, 2 * 24000, endpoint=False)),
            dtype=np.float32,
        )
        edits = voice_library.build_vad_pause_edits(
            wav, 24000, "Hello there. How are you?", "Storyteller", 1.0, 0.0
        )
        assert len(edits) == 1  # one interior period
        assert edits[0]["target_ms"] == 1000.0  # Storyteller sentence_end
        assert 0.0 < edits[0]["at_ms"] < 2000.0

    def test_terminal_punctuation_is_ignored(self):
        wav = np.zeros(24000, dtype=np.float32)
        # Only a terminal period — no downstream audio to segment.
        assert voice_library.build_vad_pause_edits(wav, 24000, "Just one sentence.", "Neutral", 1.0) == []

    def test_precise_inserts_without_alignment(self):
        # A voice whose transcript has an interior boundary but no cached/real alignment.
        vid = _save("Hello there. How are you?")
        result = voice_library.get_vad_directed_wav(vid, "Storyteller", 1.0, 0.0, mode="precise")
        assert result is not None
        adjusted, sr = result
        assert adjusted.size > 0

    def test_no_interior_punctuation_returns_none(self):
        vid = _save("Just one sentence with no interior break")
        assert voice_library.get_vad_directed_wav(vid, "Storyteller", 1.0, 0.0, mode="precise") is None
