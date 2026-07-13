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
