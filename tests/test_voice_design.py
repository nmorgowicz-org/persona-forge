from __future__ import annotations

import sys
import types
import unittest

import numpy as np


calls: list[object] = []


class _FakeInner:
    def __init__(self, tts_model_type: str) -> None:
        self.tts_model_type = tts_model_type


class _FakeWrapped:
    def __init__(self, tts_model_type: str) -> None:
        self.model = _FakeInner(tts_model_type)
        self.fail_generate = False

    def generate_voice_design(self, *, text: str, language: str, instruct: str):
        if self.fail_generate:
            raise RuntimeError("boom")
        return [np.zeros(480, dtype=np.float32)], 24000


fake_model = types.ModuleType("qwen3_tts.model")
fake_model.BASE_PROFILE = "BASE"
fake_model.VOICE_DESIGN_PROFILE = "VOICE_DESIGN"
fake_model.model = None
fake_model._trim_silence = lambda wav, sr: wav


def _force_unload() -> None:
    calls.append("force_unload")
    fake_model.model = None


def _load_model(profile) -> None:
    calls.append(("load_model", profile))
    tts_model_type = "voice_design" if profile == "VOICE_DESIGN" else "base"
    wrapped = _FakeWrapped(tts_model_type)
    wrapped.fail_generate = getattr(fake_model, "_fail_generate", False)
    fake_model.model = wrapped


fake_model.force_unload = _force_unload
fake_model.load_model = _load_model
sys.modules["qwen3_tts.model"] = fake_model

from qwen3_tts import voice_design  # noqa: E402

# qwen3_tts.voice_design may already be imported (and its `model` name already bound to a
# different test module's fake) by the time this file runs under `unittest discover` — test
# module import order is not guaranteed, so rebind explicitly rather than relying on
# sys.modules["qwen3_tts.model"] being set before voice_design's own import runs.
voice_design.model = fake_model


class VoiceDesignSwapTests(unittest.TestCase):
    def setUp(self) -> None:
        calls.clear()
        fake_model._fail_generate = False
        fake_model.model = None
        voice_design._swap_in_progress = False

    def test_happy_path_swaps_to_voice_design_and_back_to_base(self) -> None:
        wav, sr = voice_design.run_voice_design_request("a description", "hello there", "English")

        self.assertEqual(sr, 24000)
        self.assertEqual(len(wav), 480)
        self.assertEqual(
            calls,
            [
                "force_unload",
                ("load_model", "VOICE_DESIGN"),
                "force_unload",
                ("load_model", "BASE"),
            ],
        )
        self.assertFalse(voice_design.swap_in_progress())
        self.assertIsInstance(fake_model.model, _FakeWrapped)
        self.assertEqual(fake_model.model.model.tts_model_type, "base")

    def test_generation_failure_still_restores_base_model(self) -> None:
        fake_model._fail_generate = True

        with self.assertRaises(RuntimeError):
            voice_design.run_voice_design_request("a description", "hello there", "English")

        self.assertEqual(
            calls,
            [
                "force_unload",
                ("load_model", "VOICE_DESIGN"),
                "force_unload",
                ("load_model", "BASE"),
            ],
        )
        self.assertFalse(voice_design.swap_in_progress())
        self.assertEqual(fake_model.model.model.tts_model_type, "base")

    def test_validate_sample_text_rejects_long_sample(self) -> None:
        long_text = " ".join(["word"] * (voice_design.MAX_SAMPLE_TEXT_WORDS + 5))

        with self.assertRaises(ValueError):
            voice_design.validate_sample_text(long_text)

    def test_validate_sample_text_accepts_short_sample(self) -> None:
        voice_design.validate_sample_text("A short reference sample.")


if __name__ == "__main__":
    unittest.main()
