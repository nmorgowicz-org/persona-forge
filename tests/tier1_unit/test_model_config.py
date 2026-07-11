"""Test model_config helpers — no heavy model loading."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from qwen3_tts.model_config import (
    configure_hf_token,
    resolve_model_repo,
    resolve_torch_load_config,
    resolve_voice_design_model_repo,
)


class TestResolveModelRepo:
    def test_defaults_to_17b_base(self):
        assert resolve_model_repo({}) == "Qwen/Qwen3-TTS-12Hz-1.7B-Base"

    def test_selects_17b_base(self):
        assert resolve_model_repo({"MODEL_SIZE": "1.7b"}) == "Qwen/Qwen3-TTS-12Hz-1.7B-Base"

    def test_model_repo_override(self):
        assert resolve_model_repo({"MODEL_SIZE": "invalid", "MODEL_REPO": "org/model"}) == "org/model"

    def test_rejects_unknown_size(self):
        with pytest.raises(RuntimeError, match="Unsupported MODEL_SIZE"):
            resolve_model_repo({"MODEL_SIZE": "7B"})


class TestResolveVoiceDesignModelRepo:
    def test_defaults_to_17b_voicedesign(self):
        assert resolve_voice_design_model_repo({}) == "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"

    def test_override(self):
        assert resolve_voice_design_model_repo(
            {"VOICE_DESIGN_MODEL_SIZE": "invalid", "VOICE_DESIGN_MODEL_REPO": "org/vd"}
        ) == "org/vd"

    def test_unknown_size(self):
        with pytest.raises(RuntimeError, match="Unsupported VOICE_DESIGN_MODEL_SIZE"):
            resolve_voice_design_model_repo({"VOICE_DESIGN_MODEL_SIZE": "0.6B"})


class TestResolveTorchLoadConfig:
    def test_bf16_low_mem(self):
        torch_module = type(
            "FakeTorch",
            (),
            {"float32": object(), "bfloat16": object(), "float16": object()},
        )
        dtype, name, low_memory = resolve_torch_load_config(
            torch_module,
            {"OPENVINO_TORCH_DTYPE": "bf16", "OPENVINO_LOW_CPU_MEM_USAGE": "1"},
        )
        assert dtype is torch_module.bfloat16
        assert name == "bfloat16"
        assert low_memory is True

    def test_pytorch_backend_forces_fp32_after_openvino_swap(self):
        torch_module = type(
            "FakeTorch",
            (),
            {"float32": object(), "bfloat16": object(), "float16": object()},
        )
        dtype, name, low_memory = resolve_torch_load_config(
            torch_module,
            {"OPENVINO_TORCH_DTYPE": "bf16", "OPENVINO_LOW_CPU_MEM_USAGE": "1"},
            backend="pytorch",
        )
        assert dtype is torch_module.float32
        assert name == "float32"
        assert low_memory is True

    def test_rejects_unknown_dtype(self):
        torch_module = type(
            "FakeTorch",
            (),
            {"float32": object(), "bfloat16": object(), "float16": object()},
        )
        with pytest.raises(ValueError, match="MODEL_DTYPE"):
            resolve_torch_load_config(
                torch_module,
                {"MODEL_DTYPE": "int8"},
            )


class TestConfigureHfToken:
    def test_loads_from_secret_file(self, tmp_path: Path):
        token_file = tmp_path / "hf_token"
        token_file.write_text("test-token\n", encoding="utf-8")
        environ = {"HF_TOKEN_FILE": str(token_file)}
        configure_hf_token(environ)
        assert environ["HF_TOKEN"] == "test-token"

    def test_direct_token_takes_precedence(self):
        environ = {"HF_TOKEN": "direct", "HF_TOKEN_FILE": "/missing"}
        configure_hf_token(environ)
        assert environ["HF_TOKEN"] == "direct"

    def test_missing_file_no_raise(self):
        """Missing HF_TOKEN_FILE is silently ignored; HF_TOKEN stays unset."""
        environ = {"HF_TOKEN_FILE": "/does-not-exist-hf-token-file"}
        configure_hf_token(environ)
        assert "HF_TOKEN" not in environ

    def test_empty_file_no_raise(self, tmp_path: Path):
        """Empty HF_TOKEN_FILE is silently ignored; HF_TOKEN stays unset."""
        token_file = tmp_path / "empty_token"
        token_file.write_text("   \n", encoding="utf-8")
        environ = {"HF_TOKEN_FILE": str(token_file)}
        configure_hf_token(environ)
        assert "HF_TOKEN" not in environ
