from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace

import numpy as np

from streaming_vocoder import StreamingVocoderSession


class _FakeTalker:
    def forward(self, codec_ids=None, marker=None):
        return SimpleNamespace(hidden_states=((), codec_ids), marker=marker)


class StreamingVocoderSessionTests(unittest.TestCase):
    def setUp(self):
        self.talker = _FakeTalker()
        self.decode_lengths = []
        self.chunks = []

    def decode(self, codes):
        self.decode_lengths.append(codes.shape[0])
        return np.repeat(codes[:, 0].astype(np.float32), 2)

    @staticmethod
    def codes(*first_codebook_values):
        result = np.zeros((len(first_codebook_values), 16), dtype=np.int64)
        result[:, 0] = first_codebook_values
        return result

    def session(self, **kwargs):
        return StreamingVocoderSession(
            self.talker,
            self.decode,
            self.chunks.append,
            chunk_frames=3,
            samples_per_frame=2,
            **kwargs,
        )

    def test_hooks_outer_forward_and_restores_it(self):
        original = self.talker.forward
        original_signature = inspect.signature(original)

        with self.session() as session:
            self.assertEqual(inspect.signature(self.talker.forward), original_signature)
            self.talker.forward(None)  # prefill
            result = self.talker.forward(self.codes(7), marker="kept")
            self.assertEqual(result.marker, "kept")
            self.assertEqual(session.generated_frames, 1)

        self.assertEqual(self.talker.forward, original)
        np.testing.assert_array_equal(np.concatenate(self.chunks), [7.0, 7.0])

    def test_decodes_only_new_boundaries_and_includes_reference_codes(self):
        reference = self.codes(90)
        with self.session(reference_codes=reference) as session:
            for value in range(1, 6):
                self.talker.forward(self.codes(value))

        self.assertEqual(self.decode_lengths, [3, 6])
        self.assertEqual(session.decode_boundaries, (3, 6))
        self.assertEqual(session.reference_frames, 1)
        self.assertEqual(session.total_frames, 6)
        self.assertTrue(session.matches_codes(self.codes(90, 1, 2, 3, 4, 5)))
        self.assertFalse(session.matches_codes(self.codes(90, 1)))
        np.testing.assert_array_equal(
            np.concatenate(self.chunks),
            np.repeat(np.arange(1, 6, dtype=np.float32), 2),
        )

    def test_final_partial_prefix_is_flushed_once(self):
        with self.session(reference_codes=self.codes(90)):
            for value in (1, 2, 3):
                self.talker.forward(self.codes(value))

        self.assertEqual(self.decode_lengths, [3, 4])
        np.testing.assert_array_equal(
            np.concatenate(self.chunks),
            np.repeat(np.array([1, 2, 3], dtype=np.float32), 2),
        )

    def test_eos_frame_is_not_decoded(self):
        with self.session(eos_token_id=999):
            self.talker.forward(self.codes(1, 999))

        self.assertEqual(self.decode_lengths, [1])
        np.testing.assert_array_equal(np.concatenate(self.chunks), [1.0, 1.0])

    def test_generation_failure_restores_forward_without_partial_flush(self):
        original = self.talker.forward
        with self.assertRaisesRegex(RuntimeError, "generation failed"):
            with self.session():
                self.talker.forward(self.codes(1))
                raise RuntimeError("generation failed")

        self.assertEqual(self.talker.forward, original)
        self.assertEqual(self.decode_lengths, [])
        self.assertEqual(self.chunks, [])

    def test_rejects_wrong_codebook_shape(self):
        with self.assertRaisesRegex(ValueError, "frames, 16"):
            with self.session():
                self.talker.forward(np.zeros((1, 15), dtype=np.int64))


if __name__ == "__main__":
    unittest.main()
