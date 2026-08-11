"""Test vocoder runtime chunking logic."""

from __future__ import annotations

import numpy as np
import pytest

from persona_forge.openvino.vocoder import OpenVinoVocoderRuntime


@pytest.fixture
def fake_vocoder():
    runtime = OpenVinoVocoderRuntime.__new__(OpenVinoVocoderRuntime)
    runtime._num_quantizers = 2
    runtime._total_upsample = 2

    def fake_run_ir(codes):
        return np.repeat(codes[:, 0].astype(np.float32), 2)

    runtime._run_ir = fake_run_ir
    return runtime


class TestIterDecodeChunks:
    def test_concatenated_chunks_preserve_batch(self, fake_vocoder):
        runtime = fake_vocoder
        for frames in (1, 300, 301, 625):
            codes = np.arange(frames * 2, dtype=np.int64).reshape(frames, 2)
            chunks = list(runtime.iter_decode_chunks(codes))
            streamed = np.concatenate(chunks)
            batch = runtime._decode_codes_tensor(codes)
            np.testing.assert_array_equal(streamed, batch)
            assert streamed.size == frames * 2

    def test_yields_at_300_frame_boundaries(self, fake_vocoder):
        codes = np.zeros((625, 2), dtype=np.int64)
        chunks = list(fake_vocoder.iter_decode_chunks(codes))
        assert [chunk.size for chunk in chunks] == [600, 600, 50]

    def test_empty_codes(self, fake_vocoder):
        codes = np.empty((0, 2), dtype=np.int64)
        assert list(fake_vocoder.iter_decode_chunks(codes)) == []
        np.testing.assert_array_equal(
            fake_vocoder._decode_codes_tensor(codes),
            np.array([], dtype=np.float32),
        )

    def test_wrong_quantizer_count(self, fake_vocoder):
        with pytest.raises(RuntimeError, match="unexpected codes shape"):
            list(fake_vocoder.iter_decode_chunks(np.zeros((10, 3), dtype=np.int64)))
