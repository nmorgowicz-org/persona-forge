from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
for p in (SRC, SRC / "export"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from persona_forge.transformers_compat import repair_rotary_buffers

torch = None
pytestmark = [pytest.mark.requires_torch, pytest.mark.slow]


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


@pytest.mark.slow
class TestRopeRepair:
    def test_repair_rotary_buffers_replaces_finite_uninitialized_extrema(self):
        global torch
        torch = pytest.importorskip("torch")
        rotary = _Rotary(_default_initializer)
        report = repair_rotary_buffers(_Root(rotary), torch)

        assert len(report) == 1
        entry = report[0]
        assert entry["module"] == "talker.model.rotary_emb"
        assert entry["rope_type"] == "default"
        assert entry["length"] == 64
        assert pytest.approx(1.1547819844801563e-4, rel=1e-6) == entry["min"]
        assert entry["max"] == 1.0
        assert torch.equal(rotary.inv_freq, rotary.original_inv_freq)
        assert rotary.inv_freq.data_ptr() != rotary.original_inv_freq.data_ptr()
        assert torch.all(rotary.inv_freq[:-1] > rotary.inv_freq[1:]).item()
        assert rotary.attention_scaling == 1.0

    def test_repair_rotary_buffers_rejects_non_monotonic_default_values(self):
        global torch
        torch = pytest.importorskip("torch")
        def invalid_initializer(config, device):
            del config
            return torch.tensor([1.0, 0.5, 0.75], device=device), 1.0

        with pytest.raises(RuntimeError, match="not strictly decreasing"):
            repair_rotary_buffers(_Root(_Rotary(invalid_initializer)), torch)
