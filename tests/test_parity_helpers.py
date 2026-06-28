import unittest

from parity_contract import require_output_head


class TransformerParityTests(unittest.TestCase):
    def test_missing_output_heads_fail_closed(self):
        with self.assertRaisesRegex(RuntimeError, "cannot be skipped"):
            require_output_head([], 0)

    def test_missing_predictor_head_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "missing output head 1"):
            require_output_head([object()], 1)


if __name__ == "__main__":
    unittest.main()
