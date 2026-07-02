from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(SRC / "export"))

from qwen3_tts.transformers_compat import repair_rotary_buffers

try:
    import torch

    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False


class _Rotary:
    rope_type = "default"

    def __init__(self, initializer):
        self.config = SimpleNamespace(rope_theta=10_000.0, head_dim=128)
        self.rope_init_fn = initializer
        self.inv_freq = torch.full((64,), 65_504.0)
        self.original_inv_freq = self.inv_freq
        self.attention_scaling = 99.0


class _Root:
    def __init__(self, rotary):
        self.rotary = rotary

    def named_modules(self):
        return iter((("", self), ("talker.model.rotary_emb", self.rotary)))


def _default_initializer(config, device):
    dim = config.head_dim
    inv_freq = 1.0 / (
        config.rope_theta ** (torch.arange(0, dim, 2, dtype=torch.float32, device=device) / dim)
    )
    return inv_freq, 1.0


@unittest.skipUnless(_TORCH_AVAILABLE, "torch not installed")
class RopeRepairTests(unittest.TestCase):
    def test_repair_rotary_buffers_replaces_finite_uninitialized_extrema(self):
        rotary = _Rotary(_default_initializer)

        report = repair_rotary_buffers(_Root(rotary), torch)

        self.assertEqual(len(report), 1)
        entry = report[0]
        self.assertEqual(entry["module"], "talker.model.rotary_emb")
        self.assertEqual(entry["rope_type"], "default")
        self.assertEqual(entry["length"], 64)
        self.assertAlmostEqual(entry["min"], 1.1547819844801563e-4, places=9)
        self.assertEqual(entry["max"], 1.0)
        self.assertTrue(torch.equal(rotary.inv_freq, rotary.original_inv_freq))
        self.assertNotEqual(rotary.inv_freq.data_ptr(), rotary.original_inv_freq.data_ptr())
        self.assertTrue(torch.all(rotary.inv_freq[:-1] > rotary.inv_freq[1:]))
        self.assertEqual(rotary.attention_scaling, 1.0)

    def test_repair_rotary_buffers_rejects_non_monotonic_default_values(self):
        def invalid_initializer(config, device):
            del config
            return torch.tensor([1.0, 0.5, 0.75], device=device), 1.0

        with self.assertRaisesRegex(RuntimeError, "not strictly decreasing"):
            repair_rotary_buffers(_Root(_Rotary(invalid_initializer)), torch)


if __name__ == "__main__":
    unittest.main()
