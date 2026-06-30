from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qwen3_tts.model_config import configure_hf_token, resolve_model_repo, resolve_torch_load_config


class ModelConfigTests(unittest.TestCase):
    def test_defaults_to_small_base_model(self) -> None:
        self.assertEqual(
            resolve_model_repo({}),
            "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        )

    def test_selects_large_base_model(self) -> None:
        self.assertEqual(
            resolve_model_repo({"MODEL_SIZE": "1.7b"}),
            "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        )

    def test_model_repo_overrides_preset(self) -> None:
        self.assertEqual(
            resolve_model_repo({"MODEL_SIZE": "invalid", "MODEL_REPO": "org/model"}),
            "org/model",
        )

    def test_rejects_unknown_size(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Unsupported MODEL_SIZE"):
            resolve_model_repo({"MODEL_SIZE": "7B"})

    def test_resolves_bf16_serving_load(self) -> None:
        torch_module = type(
            "FakeTorch",
            (),
            {"float32": object(), "bfloat16": object(), "float16": object()},
        )

        dtype, name, low_memory = resolve_torch_load_config(
            torch_module,
            {
                "OPENVINO_TORCH_DTYPE": "bf16",
                "OPENVINO_LOW_CPU_MEM_USAGE": "1",
            },
        )

        self.assertIs(dtype, torch_module.bfloat16)
        self.assertEqual(name, "bfloat16")
        self.assertTrue(low_memory)

    def test_rejects_unknown_torch_dtype(self) -> None:
        torch_module = type(
            "FakeTorch",
            (),
            {"float32": object(), "bfloat16": object(), "float16": object()},
        )

        with self.assertRaisesRegex(ValueError, "OPENVINO_TORCH_DTYPE"):
            resolve_torch_load_config(
                torch_module,
                {"OPENVINO_TORCH_DTYPE": "int8"},
            )

    def test_loads_token_from_secret_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            token_file = Path(directory) / "hf_token"
            token_file.write_text("test-token\n", encoding="utf-8")
            environ = {"HF_TOKEN_FILE": str(token_file)}
            configure_hf_token(environ)
            self.assertEqual(environ["HF_TOKEN"], "test-token")

    def test_direct_token_takes_precedence(self) -> None:
        environ = {"HF_TOKEN": "direct", "HF_TOKEN_FILE": "/missing"}
        configure_hf_token(environ)
        self.assertEqual(environ["HF_TOKEN"], "direct")


if __name__ == "__main__":
    unittest.main()
