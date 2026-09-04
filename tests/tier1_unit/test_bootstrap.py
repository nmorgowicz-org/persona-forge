"""Test persona_forge.bootstrap: native process env defaults (Phase 2 Task 4)."""

from __future__ import annotations

from persona_forge.bootstrap import apply_env_defaults
from persona_forge.config import DEFAULT_TTS_BACKEND


class TestApplyEnvDefaultsBackend:
    def test_sets_default_backend_when_unset(self):
        environ: dict[str, str] = {}
        apply_env_defaults(environ, platform="darwin")
        assert environ["TTS_BACKEND"] == DEFAULT_TTS_BACKEND == "pocket_tts"

    def test_explicit_backend_wins(self):
        environ = {"TTS_BACKEND": "openvino"}
        apply_env_defaults(environ, platform="darwin")
        assert environ["TTS_BACKEND"] == "openvino"


class TestApplyEnvDefaultsLowRam:
    def test_low_ram_off_sets_nothing(self):
        environ: dict[str, str] = {}
        apply_env_defaults(environ, platform="linux")
        assert "IDLE_UNLOAD_SECONDS" not in environ
        assert "MALLOC_MMAP_THRESHOLD_" not in environ
        assert "MALLOC_ARENA_MAX" not in environ

    def test_low_ram_on_linux_sets_idle_unload_and_malloc(self):
        environ = {"LOW_RAM_MODE": "1"}
        apply_env_defaults(environ, platform="linux")
        assert environ["IDLE_UNLOAD_SECONDS"] == "1800"
        assert environ["MALLOC_MMAP_THRESHOLD_"] == "65536"
        assert environ["MALLOC_ARENA_MAX"] == "1"

    def test_low_ram_on_macos_sets_idle_unload_but_not_malloc(self):
        environ = {"LOW_RAM_MODE": "1"}
        apply_env_defaults(environ, platform="darwin")
        assert environ["IDLE_UNLOAD_SECONDS"] == "1800"
        assert "MALLOC_MMAP_THRESHOLD_" not in environ
        assert "MALLOC_ARENA_MAX" not in environ

    def test_low_ram_on_windows_sets_idle_unload_but_not_malloc(self):
        environ = {"LOW_RAM_MODE": "1"}
        apply_env_defaults(environ, platform="win32")
        assert environ["IDLE_UNLOAD_SECONDS"] == "1800"
        assert "MALLOC_MMAP_THRESHOLD_" not in environ
        assert "MALLOC_ARENA_MAX" not in environ

    def test_operator_values_never_overwritten(self):
        environ = {
            "LOW_RAM_MODE": "1",
            "IDLE_UNLOAD_SECONDS": "60",
            "MALLOC_MMAP_THRESHOLD_": "999",
            "MALLOC_ARENA_MAX": "4",
        }
        apply_env_defaults(environ, platform="linux")
        assert environ["IDLE_UNLOAD_SECONDS"] == "60"
        assert environ["MALLOC_MMAP_THRESHOLD_"] == "999"
        assert environ["MALLOC_ARENA_MAX"] == "4"


class TestApplyEnvDefaultsIntelNeo:
    def test_intel_xpu_sets_neo_vars(self, monkeypatch):
        monkeypatch.setattr(
            "persona_forge.bootstrap.resolve_gpu_family",
            lambda environ: "intel-xpu",
        )
        environ: dict[str, str] = {}
        apply_env_defaults(environ, platform="linux")
        assert environ["NEOReadDebugKeys"] == "1"
        assert environ["OverrideDefaultFP64Settings"] == "1"
        assert environ["IGC_EnableDPEmulation"] == "1"
        assert environ["OPENVINO_DEVICE"] == "GPU"

    def test_non_intel_family_sets_no_neo_vars(self, monkeypatch):
        monkeypatch.setattr(
            "persona_forge.bootstrap.resolve_gpu_family",
            lambda environ: "cpu",
        )
        environ: dict[str, str] = {}
        apply_env_defaults(environ, platform="linux")
        assert "NEOReadDebugKeys" not in environ
        assert "OverrideDefaultFP64Settings" not in environ
        assert "IGC_EnableDPEmulation" not in environ
        assert "OPENVINO_DEVICE" not in environ

    def test_operator_neo_values_never_overwritten(self, monkeypatch):
        monkeypatch.setattr(
            "persona_forge.bootstrap.resolve_gpu_family",
            lambda environ: "intel-xpu",
        )
        environ = {"OPENVINO_DEVICE": "CPU"}
        apply_env_defaults(environ, platform="linux")
        assert environ["OPENVINO_DEVICE"] == "CPU"

    def test_never_sets_ld_preload(self, monkeypatch):
        monkeypatch.setattr(
            "persona_forge.bootstrap.resolve_gpu_family",
            lambda environ: "intel-xpu",
        )
        environ: dict[str, str] = {"LOW_RAM_MODE": "1"}
        apply_env_defaults(environ, platform="linux")
        assert "LD_PRELOAD" not in environ
