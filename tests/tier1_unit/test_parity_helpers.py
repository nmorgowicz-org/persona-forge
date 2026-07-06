"""Test parity_contract 'fail-closed' behavior."""

from __future__ import annotations

import pytest

from parity_contract import require_output_head


class TestRequireOutputHead:
    def test_missing_output_heads_fail_closed(self):
        with pytest.raises(RuntimeError, match="cannot be skipped"):
            require_output_head([], 0)

    def test_missing_predictor_head_fails_closed(self):
        with pytest.raises(RuntimeError, match="missing output head 1"):
            require_output_head([object()], 1)

    def test_returns_head_when_present(self):
        heads = [object(), object()]
        assert require_output_head(heads, 0) is heads[0]
        assert require_output_head(heads, 1) is heads[1]
