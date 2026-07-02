from __future__ import annotations

import unittest

from qwen3_tts.config import apply_preset_env
from qwen3_tts.presets import (
    capacity_for_seconds,
    get_preset,
    get_voice_design_preset,
    seconds_for_capacity,
)


class PresetTests(unittest.TestCase):
    def test_06b_uses_validated_stateful_main_and_predictor(self) -> None:
        environ = {"MODEL_SIZE": "0.6b"}

        apply_preset_env(environ)

        self.assertEqual(environ["OV_MAIN_COMPRESSION"], "int8")
        self.assertEqual(environ["OV_PREDICTOR_COMPRESSION"], "int8")
        self.assertEqual(environ["OPENVINO_MAIN_STATEFUL_MODEL"], "/ov/0.6B/main_stateful_cap768.xml")
        self.assertEqual(
            environ["OPENVINO_PREDICTOR_STATEFUL_MODEL"],
            "/ov/0.6B/predictor_stateful_cap32.xml",
        )
        self.assertEqual(environ["TTS_MAX_SPEECH_SECONDS"], "64.0")

    def test_17b_uses_int4_main_and_explicit_predictor(self) -> None:
        environ = {"MODEL_SIZE": "1.7B"}

        apply_preset_env(environ)

        self.assertEqual(environ["OV_MAIN_COMPRESSION"], "int4")
        self.assertEqual(environ["OV_PREDICTOR_COMPRESSION"], "int8")
        self.assertNotIn("OPENVINO_PREDICTOR_STATEFUL_MODEL", environ)

    def test_explicit_expert_override_wins(self) -> None:
        environ = {"MODEL_SIZE": "0.6B", "OV_MAIN_COMPRESSION": "fp32"}

        apply_preset_env(environ)

        self.assertEqual(environ["OV_MAIN_COMPRESSION"], "fp32")

    def test_max_speech_seconds_env_overrides_default_capacity(self) -> None:
        environ = {"MODEL_SIZE": "1.7B", "TTS_MAX_SPEECH_SECONDS": "20"}

        apply_preset_env(environ)

        self.assertEqual(environ["OPENVINO_MAIN_STATEFUL_MODEL"], "/ov/1.7B/main_stateful_cap240.xml")
        self.assertEqual(environ["TTS_MAX_SPEECH_SECONDS"], "20")

    def test_max_speech_seconds_explicit_override_wins(self) -> None:
        environ = {"MODEL_SIZE": "1.7B", "TTS_MAX_SPEECH_SECONDS": "20"}

        apply_preset_env(environ)

        # setdefault semantics: an explicitly-set value is never overwritten.
        self.assertEqual(environ["TTS_MAX_SPEECH_SECONDS"], "20")

    def test_capacity_for_seconds_matches_12hz_frame_rate(self) -> None:
        self.assertEqual(capacity_for_seconds(64), 768)
        self.assertEqual(capacity_for_seconds(20), 240)
        self.assertEqual(seconds_for_capacity(768), 64.0)

    def test_capacity_for_seconds_rejects_non_positive(self) -> None:
        with self.assertRaises(ValueError):
            capacity_for_seconds(0)

    def test_get_preset_default_is_unchanged_from_before_the_knob_existed(self) -> None:
        preset = get_preset("1.7B")

        self.assertEqual(preset["stateful_capacity"], 768)
        self.assertEqual(preset["main_stateful_model"], "/ov/1.7B/main_stateful_cap768.xml")

    def test_get_preset_override_is_capacity_keyed_so_paths_never_collide(self) -> None:
        default_preset = get_preset("1.7B")
        short_preset = get_preset("1.7B", max_speech_seconds=15)

        self.assertNotEqual(
            default_preset["main_stateful_model"], short_preset["main_stateful_model"]
        )
        self.assertEqual(short_preset["stateful_capacity"], 180)

    def test_voice_design_preset_uses_its_own_ir_tree(self) -> None:
        preset = get_voice_design_preset("1.7B")

        self.assertEqual(preset["model_repo"], "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign")
        self.assertEqual(preset["ov_model_dir"], "/ov/1.7B-voicedesign/ir")
        self.assertEqual(preset["vocoder_dir"], "/ov/1.7B-voicedesign/vocoder")
        # 20s default keeps capacity well below the Base preset's 64s (768-frame) default.
        self.assertEqual(preset["stateful_capacity"], 240)
        self.assertEqual(
            preset["main_stateful_model"], "/ov/1.7B-voicedesign/main_stateful_cap240.xml"
        )

    def test_voice_design_preset_never_collides_with_base_preset_paths(self) -> None:
        base = get_preset("1.7B", max_speech_seconds=20)
        voice_design = get_voice_design_preset("1.7B")

        self.assertNotEqual(base["main_stateful_model"], voice_design["main_stateful_model"])
        self.assertNotEqual(base["ov_model_dir"], voice_design["ov_model_dir"])


if __name__ == "__main__":
    unittest.main()
