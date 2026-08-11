from __future__ import annotations

import tempfile
from typing import Any

import os
import sys
from pathlib import Path

import pytest

# Ensure VOICE_LIBRARY_DIR and SEGMENT_LIBRARY_DIR are set before
# any persona_forge module imports, so they don't fall back to "/segments"
# (which can be on a read-only root filesystem).
if "VOICE_LIBRARY_DIR" not in os.environ:
    os.environ["VOICE_LIBRARY_DIR"] = tempfile.mkdtemp(
        prefix="persona-forge-test-voices-"
    )
if "SEGMENT_LIBRARY_DIR" not in os.environ:
    os.environ["SEGMENT_LIBRARY_DIR"] = tempfile.mkdtemp(
        prefix="qwen3-tts-test-segments-"
    )

_root = Path(__file__).resolve().parent.parent
_src = str(_root / "src")
_export = str(_root / "src" / "export")

for _p in (_src, _export):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "unit: fast unit test, no app, no heavy mocking",
    )
    config.addinivalue_line(
        "markers",
        "integration: integration test involving the app or HTTP",
    )
    config.addinivalue_line(
        "markers",
        "slow: test that depends on torch/openvino or is otherwise slow",
    )
    config.addinivalue_line(
        "markers",
        "fake_only: CI-safe test that uses fakes and does not require Torch, model weights, or OpenVINO IR",
    )
    config.addinivalue_line(
        "markers",
        "requires_torch: test imports or exercises real Torch-backed production code",
    )
    config.addinivalue_line(
        "markers",
        "requires_model_weights: test requires downloaded model weights",
    )
    config.addinivalue_line(
        "markers",
        "requires_openvino_ir: test requires exported OpenVINO IR artifacts",
    )


@pytest.fixture
def tmp_env(monkeypatch):
    """
    Dict-like helper that sets/unsets env vars via monkeypatch.

    Usage:
        env = tmp_env
        env["TZ"] = "UTC"
        env["UNSET_ME"] = None
    """

    class _Env:
        def __init__(self):
            self._set = {}
            self._unset = set()

        def __setitem__(self, name, value):
            if value is None:
                self._unset.add(name)
                monkeypatch.delenv(name, raising=False)
            else:
                self._set[name] = value
                monkeypatch.setenv(name, value)

        def __getitem__(self, name):
            return os.getenv(name)

        def __contains__(self, name):
            return name in self._set

        def items(self):
            return list(self._set.items())

    return _Env()


@pytest.fixture
def clean_test_env(monkeypatch):
    """
    Ensures common project env vars are unset, then returns tmp_env-style helper.
    """

    _controlled = {
        "TTS_BACKEND",
        "MODEL_SIZE",
        "MODEL_REPO",
        "MODEL_REVISION",
        "OV_MODEL_DIR",
        "OV_CACHE_DIR",
        "LOW_RAM_MODE",
        "HF_TOKEN",
        "TTS_MAX_SPEECH_SECONDS",
    }

    for name in _controlled:
        monkeypatch.delenv(name, raising=False)

    class _Env:
        def __init__(self):
            self._set = {}
            self._unset = set()

        def __setitem__(self, name, value):
            if value is None:
                self._unset.add(name)
                monkeypatch.delenv(name, raising=False)
            else:
                self._set[name] = value
                monkeypatch.setenv(name, value)

        def __getitem__(self, name):
            return os.getenv(name)

        def __contains__(self, name):
            return name in self._set

        def items(self):
            return list(self._set.items())

    return _Env()
