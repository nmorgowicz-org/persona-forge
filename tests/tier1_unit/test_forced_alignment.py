"""Phase 2 gate: forced-alignment engine deterministic logic.

The 302 MB ONNX model is not present in CI, so these tests inject a synthetic
emitter (raw CTC logits) and exercise every deterministic piece the gate calls
out: normalized offsets + word/punctuation ownership, repeated-word handling,
confidence-based divergence, and cache identity + invalidation. The real model
path is covered by the Phase 0 spike evidence.
"""

from __future__ import annotations

import numpy as np
import pytest

import qwen3_tts.forced_alignment as fa

SR = 16000
HIGH = 8.0  # logit favoring a character
FRAMES_PER_CHAR = 4
GAP_FRAMES = 3


def _schedule(words, diverge=frozenset()):
    """Build a per-frame character-id plan: each word's chars laid out in order
    with a blank gap between words. Diverged words emit blanks instead of their
    chars, so the forced path through them scores poorly."""
    plan: list[int] = []
    for wi, word in enumerate(words):
        for ch in word:
            cid = fa.VOCAB.get(ch, fa.VOCAB["<unk>"])
            emit = fa.BLANK if wi in diverge else cid
            plan.extend([emit] * FRAMES_PER_CHAR)
        if wi < len(words) - 1:
            plan.extend([fa.BLANK] * GAP_FRAMES)
    return plan


def _emitter_for(transcript, diverge=frozenset()):
    words = [t["word"] for t in fa.normalize_transcript(transcript)]
    plan = _schedule(words, diverge)
    t_count = len(plan)

    def emit(_wav16k):
        logits = np.zeros((t_count, 31), dtype=np.float32)
        for t, cid in enumerate(plan):
            logits[t, cid] = HIGH
        return logits

    # A wav whose 16 kHz length matches the frame plan keeps seconds sensible.
    wav = np.zeros(t_count * 320, dtype=np.float32)
    return emit, wav


def test_boundaries_are_monotonic_and_ownership_deterministic():
    transcript = "Hello there. How are you?"
    emit, wav = _emitter_for(transcript)
    a = fa.align(wav, SR, transcript, emit=emit)
    b = fa.align(wav, SR, transcript, emit=emit)

    assert [x.to_dict() for x in a] == [x.to_dict() for x in b]  # deterministic
    assert [x.text for x in a] == ["hello", "there", "how", "are", "you"]
    # Boundaries are ordered and non-overlapping.
    for prev, nxt in zip(a, a[1:]):
        assert prev.end <= nxt.start + 1e-6
        assert prev.end >= prev.start
    # "there" owns the interior period → sentence_split; terminal "?" does not.
    kinds = {x.text: x.kind for x in a}
    assert kinds["there"] == "sentence_split"
    assert kinds["you"] == "word"


def test_repeated_words_align_to_distinct_ranges():
    transcript = "go go go"
    emit, wav = _emitter_for(transcript)
    a = fa.align(wav, SR, transcript, emit=emit)
    assert [x.text for x in a] == ["go", "go", "go"]
    starts = [x.start for x in a]
    assert starts == sorted(starts)
    assert len(set((x.start, x.end) for x in a)) == 3  # three distinct spans


def test_divergence_marks_low_confidence_words_uncertain():
    transcript = "alpha bravo charlie delta"
    # "bravo" (index 1) diverges: audio there does not match the transcript.
    emit, wav = _emitter_for(transcript, diverge={1})
    a = fa.align(wav, SR, transcript, emit=emit)
    by_word = {x.text: x for x in a}
    assert by_word["bravo"].kind == "uncertain"
    assert by_word["bravo"].score < fa.CONF_MIN
    assert by_word["alpha"].kind == "word"
    assert by_word["alpha"].score >= fa.CONF_MIN


def test_abbreviation_and_decimal_do_not_own_sentence_end():
    transcript = "Dr. Smith paid 3.5 now. He left."
    emit, wav = _emitter_for(transcript)
    a = fa.align(wav, SR, transcript, emit=emit)
    kinds = {x.text: x.kind for x in a}
    assert kinds["dr"] == "word"       # abbreviation, not a boundary
    assert kinds["now"] == "sentence_split"  # the real interior period
    assert kinds["left"] == "word"     # terminal period, not interior


def test_empty_transcript_yields_no_boundaries():
    emit, wav = _emitter_for("hello")
    assert fa.align(wav, SR, "", emit=emit) == []
    assert fa.align(wav, SR, "   ", emit=emit) == []


# --- Cache identity ---------------------------------------------------------

def test_cache_identity_covers_all_fields_and_invalidates():
    ident = fa.cache_identity(fa.sha256_text("audio"), fa.sha256_text("hello world."))
    assert set(fa.IDENTITY_KEYS) <= set(ident)
    assert ident["model_revision"] == fa.MODEL_REVISION
    assert fa.identity_matches(ident, ident)

    # Changing the transcript invalidates.
    other = fa.cache_identity(ident["audio_sha256"], fa.sha256_text("hello world!!"))
    assert not fa.identity_matches(ident, other)
    # Changing the audio invalidates.
    other2 = fa.cache_identity(fa.sha256_text("audio2"), ident["transcript_sha256"])
    assert not fa.identity_matches(ident, other2)
    # A stale schema/revision invalidates.
    stale = dict(ident, schema_version=ident["schema_version"] + 1)
    assert not fa.identity_matches(stale, ident)
    assert not fa.identity_matches(None, ident)


def test_hashing_is_stable_and_distinct():
    assert fa.sha256_text("abc") == fa.sha256_text("abc")
    assert fa.sha256_text("abc") != fa.sha256_text("abcd")
    assert fa.sha256_bytes(b"\x00\x01") == fa.sha256_bytes(b"\x00\x01")


def test_build_alignment_record_roundtrips_json():
    import json

    emit, wav = _emitter_for("hello there. bye now.")
    boundaries = fa.align(wav, SR, "hello there. bye now.", emit=emit)
    ident = fa.cache_identity(fa.sha256_text("a"), fa.sha256_text("hello there. bye now."))
    record = fa.build_alignment_record(boundaries, ident)
    json.dumps(record, allow_nan=False)
    assert record["boundaries"][0]["text"] == "hello"
    assert record["engine"] == fa.ENGINE_ID


def test_preprocess_resamples_to_target_rate():
    wav = np.sin(np.linspace(0, 20, 24000, dtype=np.float32))
    out = fa.preprocess(wav, 24000)
    assert abs(out.size - 16000) <= 2  # 24k -> 16k
    assert abs(float(out.mean())) < 1e-3  # normalized
