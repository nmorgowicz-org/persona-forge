import unittest

import numpy as np

from qwen3_tts.openvino.talker import _stateful_generation_steps, _to_numpy


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


if __name__ == "__main__":
    unittest.main()
