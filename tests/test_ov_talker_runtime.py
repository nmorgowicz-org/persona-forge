import unittest

import numpy as np
import torch

from qwen3_tts.openvino.talker import (
    _cache_position_or_default,
    _dynamic_cache_from_kv,
    _dynamic_cache_kv,
    _stateful_generation_steps,
    _to_numpy,
)


class StatefulPredictorInputTests(unittest.TestCase):
    def test_defaults_missing_predictor_generation_steps_to_zero(self):
        result = _stateful_generation_steps(None, True)

        np.testing.assert_array_equal(result, np.zeros(1, dtype=np.int64))

    def test_preserves_supplied_predictor_generation_steps(self):
        supplied = np.array([7], dtype=np.int64)

        self.assertIs(_stateful_generation_steps(supplied, True), supplied)

    def test_main_core_does_not_gain_predictor_input(self):
        self.assertIsNone(_stateful_generation_steps(None, False))

    def test_numpy_inputs_are_accepted_at_runtime_seam(self):
        supplied = np.array([1], dtype=np.int32)

        result = _to_numpy(supplied, np.int64)

        self.assertEqual(result.dtype, np.int64)
        np.testing.assert_array_equal(result, np.array([1], dtype=np.int64))


class CachePositionCompatibilityTests(unittest.TestCase):
    def test_preserves_transformers_cache_position(self):
        supplied = torch.tensor([7], dtype=torch.long)

        result = _cache_position_or_default(supplied, prior=3, seq=1, device=supplied.device)

        self.assertIs(result, supplied)

    def test_derives_prefill_positions_when_transformers_omits_them(self):
        result = _cache_position_or_default(None, prior=0, seq=3, device=torch.device("cpu"))

        torch.testing.assert_close(result, torch.tensor([0, 1, 2], dtype=torch.long))

    def test_derives_decode_position_from_outer_cache_length(self):
        result = _cache_position_or_default(None, prior=17, seq=1, device=torch.device("cpu"))

        torch.testing.assert_close(result, torch.tensor([17], dtype=torch.long))


class DynamicCacheCompatibilityTests(unittest.TestCase):
    def test_round_trips_kv_with_installed_transformers(self):
        key = torch.zeros(1, 2, 3, 4)
        value = torch.ones(1, 2, 3, 4)

        cache = _dynamic_cache_from_kv([(key, value)])
        pairs = _dynamic_cache_kv(cache)

        self.assertEqual(cache.get_seq_length(), 3)
        torch.testing.assert_close(pairs[0][0], key)
        torch.testing.assert_close(pairs[0][1], value)


if __name__ == "__main__":
    unittest.main()
