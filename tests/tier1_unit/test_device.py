"""Test persona_forge.device.resolve_device (Phase A4, D9 axis a)."""

from __future__ import annotations

import warnings

import pytest

from persona_forge import device as device_mod
from persona_forge.device import apply_fp64_emulation_env, resolve_device, xpu_needs_fp64_emulation


class TestResolveDevice:
    def test_no_accelerator_falls_back_to_cpu(self, monkeypatch):
        monkeypatch.setattr(device_mod, "_cuda_available", lambda: False)
        monkeypatch.setattr(device_mod, "_xpu_available", lambda: False)
        monkeypatch.setattr(device_mod, "_mps_available", lambda: False)
        assert resolve_device({}) == "cpu"

    def test_auto_detect_prefers_cuda_over_xpu_and_mps(self, monkeypatch):
        monkeypatch.setattr(device_mod, "_cuda_available", lambda: True)
        monkeypatch.setattr(device_mod, "_xpu_available", lambda: True)
        monkeypatch.setattr(device_mod, "_mps_available", lambda: True)
        assert resolve_device({}) == "cuda"

    def test_auto_detect_prefers_xpu_over_mps(self, monkeypatch):
        monkeypatch.setattr(device_mod, "_cuda_available", lambda: False)
        monkeypatch.setattr(device_mod, "_xpu_available", lambda: True)
        monkeypatch.setattr(device_mod, "_mps_available", lambda: True)
        assert resolve_device({}) == "xpu"

    def test_explicit_tts_device_wins(self, monkeypatch):
        monkeypatch.setattr(device_mod, "_cuda_available", lambda: True)
        assert resolve_device({"TTS_DEVICE": "cpu"}) == "cpu"

    def test_legacy_device_var_used_as_fallback(self, monkeypatch):
        monkeypatch.setattr(device_mod, "_cuda_available", lambda: False)
        monkeypatch.setattr(device_mod, "_xpu_available", lambda: False)
        monkeypatch.setattr(device_mod, "_mps_available", lambda: True)
        assert resolve_device({"DEVICE": "mps"}) == "mps"

    def test_forced_unavailable_device_warns_and_falls_back_to_cpu(self, monkeypatch):
        monkeypatch.setattr(device_mod, "_cuda_available", lambda: False)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = resolve_device({"TTS_DEVICE": "cuda"})
        assert result == "cpu"
        assert any("not available" in str(w.message) for w in caught)

    def test_unrecognized_device_warns_and_auto_detects(self, monkeypatch):
        monkeypatch.setattr(device_mod, "_cuda_available", lambda: False)
        monkeypatch.setattr(device_mod, "_xpu_available", lambda: False)
        monkeypatch.setattr(device_mod, "_mps_available", lambda: False)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = resolve_device({"TTS_DEVICE": "rocm"})
        assert result == "cpu"
        assert any("Unrecognized" in str(w.message) for w in caught)


class TestXpuFp64Emulation:
    def test_no_xpu_is_false(self, monkeypatch):
        monkeypatch.setattr(device_mod, "_xpu_available", lambda: False)
        assert xpu_needs_fp64_emulation() is False

    @pytest.mark.requires_torch
    def test_xpu_with_native_fp64_is_false(self, monkeypatch):
        monkeypatch.setattr(device_mod, "_xpu_available", lambda: True)
        fake_props = type("Props", (), {"has_fp64": True})()
        fake_torch = type(
            "FakeTorchXpu",
            (),
            {"get_device_properties": staticmethod(lambda i: fake_props)},
        )()
        monkeypatch.setattr("torch.xpu", fake_torch, raising=False)
        assert xpu_needs_fp64_emulation() is False

    @pytest.mark.requires_torch
    def test_xpu_without_native_fp64_is_true(self, monkeypatch):
        monkeypatch.setattr(device_mod, "_xpu_available", lambda: True)
        fake_props = type("Props", (), {"has_fp64": False})()
        fake_torch = type(
            "FakeTorchXpu",
            (),
            {"get_device_properties": staticmethod(lambda i: fake_props)},
        )()
        monkeypatch.setattr("torch.xpu", fake_torch, raising=False)
        assert xpu_needs_fp64_emulation() is True

    def test_apply_fp64_emulation_env_sets_all_three(self):
        environ: dict[str, str] = {}
        apply_fp64_emulation_env(environ)
        assert environ == {
            "NEOReadDebugKeys": "1",
            "OverrideDefaultFP64Settings": "1",
            "IGC_EnableDPEmulation": "1",
        }

    def test_apply_fp64_emulation_env_never_clobbers_explicit(self):
        environ = {"NEOReadDebugKeys": "0"}
        apply_fp64_emulation_env(environ)
        assert environ["NEOReadDebugKeys"] == "0"
        assert environ["OverrideDefaultFP64Settings"] == "1"
