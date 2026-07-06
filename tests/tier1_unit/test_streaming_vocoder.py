"""Test StreamingVocoderSession without a real model."""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from qwen3_tts.streaming import StreamingVocoderSession
from types import SimpleNamespace


def _base_forward(codec_ids=None, marker=None):
    """Module-level callable so identity tests are stable."""
    return SimpleNamespace(hidden_states=((), codec_ids), marker=marker)


class FakeTalker:
    def __init__(self):
        self.forward = _base_forward


@pytest.fixture
def session_env():
    talker = FakeTalker()
    decode_lengths = []
    chunks = []

    def decode(codes):
        decode_lengths.append(codes.shape[0])
        return np.repeat(codes[:, 0].astype(np.float32), 2)

    def make_session(**kwargs):
        return StreamingVocoderSession(
            talker,
            decode,
            chunks.append,
            chunk_frames=3,
            samples_per_frame=2,
            **kwargs,
        )

    def codes(*vals):
        result = np.zeros((len(vals), 16), dtype=np.int64)
        result[:, 0] = vals
        return result

    return talker, decode_lengths, chunks, make_session, codes


class TestHooksForward:
    def test_hooks_and_restores(self, session_env):
        talker, _, chunks, make_session, codes = session_env
        original = talker.forward
        original_sig = inspect.signature(original)

        with make_session() as session:
            assert inspect.signature(talker.forward) == original_sig
            talker.forward(None)
            result = talker.forward(codes(7), marker="kept")
            assert result.marker == "kept"
            assert session.generated_frames == 1

        assert talker.forward is original
        np.testing.assert_array_equal(np.concatenate(chunks), [7.0, 7.0])


class TestBoundaries:
    def test_decodes_only_new_boundaries(self, session_env):
        talker, decode_lengths, _, make_session, codes = session_env
        reference = codes(90)
        with make_session(reference_codes=reference):
            for v in range(1, 6):
                talker.forward(codes(v))
        assert decode_lengths == [3, 6]


class TestFinalFlush:
    def test_final_partial_flushed_once(self, session_env):
        talker, decode_lengths, chunks, make_session, codes = session_env
        with make_session(reference_codes=codes(90)):
            for v in (1, 2, 3):
                talker.forward(codes(v))
        assert decode_lengths == [3, 4]
        np.testing.assert_array_equal(
            np.concatenate(chunks),
            np.repeat(np.array([1, 2, 3], dtype=np.float32), 2),
        )


class TestEOS:
    def test_eos_frame_not_decoded(self, session_env):
        talker, decode_lengths, chunks, make_session, codes = session_env
        with make_session(eos_token_id=999):
            talker.forward(codes(1, 999))
        assert decode_lengths == [1]
        np.testing.assert_array_equal(np.concatenate(chunks), [1.0, 1.0])


class TestFailure:
    def test_restore_on_failure(self, session_env):
        talker, decode_lengths, chunks, make_session, _ = session_env
        original = talker.forward
        with pytest.raises(RuntimeError, match="generation failed"):
            with make_session():
                talker.forward(np.zeros((1, 16), dtype=np.int64))
                raise RuntimeError("generation failed")
        assert talker.forward is original
        assert decode_lengths == []
        assert chunks == []


class TestShape:
    def test_rejects_wrong_codebook_shape(self, session_env):
        talker, _, chunks, _, _ = session_env
        bad = np.zeros((1, 15), dtype=np.int64)
        with pytest.raises(ValueError, match="16"):
            StreamingVocoderSession(
                talker,
                lambda x: x,
                chunks.append,
                reference_codes=bad,
            )
