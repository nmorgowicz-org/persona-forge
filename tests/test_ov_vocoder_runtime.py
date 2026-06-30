import unittest

import numpy as np

from qwen3_tts.openvino.vocoder import OpenVinoVocoderRuntime


class VocoderChunkIteratorTests(unittest.TestCase):
    def setUp(self):
        self.runtime = OpenVinoVocoderRuntime.__new__(OpenVinoVocoderRuntime)
        self.runtime._num_quantizers = 2
        self.runtime._total_upsample = 2

        def fake_run_ir(codes):
            return np.repeat(codes[:, 0].astype(np.float32), 2)

        self.runtime._run_ir = fake_run_ir

    def test_concatenated_chunks_preserve_batch_output(self):
        for frames in (1, 300, 301, 625):
            with self.subTest(frames=frames):
                codes = np.arange(frames * 2, dtype=np.int64).reshape(frames, 2)
                chunks = list(self.runtime.iter_decode_chunks(codes))
                streamed = np.concatenate(chunks)
                batch = self.runtime._decode_codes_tensor(codes)

                np.testing.assert_array_equal(streamed, batch)
                self.assertEqual(streamed.size, frames * 2)

    def test_yields_at_existing_300_frame_boundaries(self):
        codes = np.zeros((625, 2), dtype=np.int64)

        chunks = list(self.runtime.iter_decode_chunks(codes))

        self.assertEqual([chunk.size for chunk in chunks], [600, 600, 50])

    def test_empty_codes_yield_no_chunks_and_decode_empty(self):
        codes = np.empty((0, 2), dtype=np.int64)

        self.assertEqual(list(self.runtime.iter_decode_chunks(codes)), [])
        np.testing.assert_array_equal(
            self.runtime._decode_codes_tensor(codes), np.array([], dtype=np.float32)
        )

    def test_rejects_wrong_quantizer_count(self):
        with self.assertRaisesRegex(RuntimeError, "unexpected codes shape"):
            list(self.runtime.iter_decode_chunks(np.zeros((10, 3), dtype=np.int64)))


if __name__ == "__main__":
    unittest.main()
