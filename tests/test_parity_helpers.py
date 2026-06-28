import importlib.util
import unittest
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).resolve().parents[1] / "test_transformer_parity.py"
SPEC = importlib.util.spec_from_file_location("transformer_parity_tool", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
PARITY_TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PARITY_TOOL)


class TransformerParityTests(unittest.TestCase):
    def test_missing_output_heads_fail_closed(self):
        hidden = np.zeros((1, 1, 4), dtype=np.float32)

        with self.assertRaisesRegex(RuntimeError, "cannot be skipped"):
            PARITY_TOOL._project_last_hidden([], hidden, 0)

    def test_missing_predictor_head_fails_closed(self):
        hidden = np.zeros((1, 1, 4), dtype=np.float32)

        with self.assertRaisesRegex(RuntimeError, "missing output head 1"):
            PARITY_TOOL._project_last_hidden([object()], hidden, 1)


if __name__ == "__main__":
    unittest.main()
