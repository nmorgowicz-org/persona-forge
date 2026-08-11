"""Test talker.py helpers safe to unit-test without a real OV runtime."""

from __future__ import annotations

import numpy as np
import pytest

from persona_forge.openvino.talker import (
    _cache_position_or_default,
    _dynamic_cache_from_kv,
    _dynamic_cache_kv,
    _stateful_generation_steps,
    _to_numpy,
)

pytestmark = pytest.mark.requires_torch


class TestStatefulGenerationSteps:
    def test_defaults_missing_predictor_to_zero(self):
        result = _stateful_generation_steps(None, True)
        np.testing.assert_array_equal(result, np.zeros(1, dtype=np.int64))

    def test_preserves_supplied_predictor_steps(self):
        supplied = np.array([7], dtype=np.int64)
        assert _stateful_generation_steps(supplied, True) is supplied

    def test_main_does_not_get_predictor_input(self):
        assert _stateful_generation_steps(None, False) is None


class TestToNumpy:
    def test_numpy_inputs_accepted(self):
        supplied = np.array([1], dtype=np.int32)
        result = _to_numpy(supplied, np.int64)
        assert result.dtype == np.int64
        np.testing.assert_array_equal(result, np.array([1], dtype=np.int64))

    def test_torch_tensor_to_numpy(self):
        pytest.importorskip("torch")
        import torch
        t = torch.tensor([1, 2, 3], dtype=torch.float32)
        result = _to_numpy(t, np.float32)
        np.testing.assert_array_equal(result, np.array([1, 2, 3], dtype=np.float32))

    @pytest.mark.slow
    def test_bfloat16_upcast(self):
        pytest.importorskip("torch")
        import torch
        t = torch.tensor([1.0, 2.0], dtype=torch.bfloat16)
        result = _to_numpy(t, np.float32)
        assert result.dtype == np.float32
        np.testing.assert_array_equal(result, np.array([1.0, 2.0], dtype=np.float32))


class TestCachePositionOrDefault:
    def test_preserves_transformers_cache_position(self):
        import torch
        supplied = torch.tensor([7], dtype=torch.long)
        result = _cache_position_or_default(
            supplied, prior=3, seq=1, device=supplied.device
        )
        assert result is supplied

    def test_derives_prefill_positions(self):
        import torch
        result = _cache_position_or_default(
            None, prior=0, seq=3, device=torch.device("cpu")
        )
        torch.testing.assert_close(result, torch.tensor([0, 1, 2], dtype=torch.long))

    def test_derives_decode_position(self):
        import torch
        result = _cache_position_or_default(
            None, prior=17, seq=1, device=torch.device("cpu")
        )
        torch.testing.assert_close(result, torch.tensor([17], dtype=torch.long))


class TestDynamicCache:
    def test_round_trip_kv(self):
        import torch
        key = torch.zeros(1, 2, 3, 4)
        value = torch.ones(1, 2, 3, 4)
        cache = _dynamic_cache_from_kv([(key, value)])
        pairs = _dynamic_cache_kv(cache)
        assert cache.get_seq_length() == 3
        torch.testing.assert_close(pairs[0][0], key)
        torch.testing.assert_close(pairs[0][1], value)
