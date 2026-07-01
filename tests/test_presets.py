from __future__ import annotations

import unittest

from qwen3_tts.config import apply_preset_env


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


if __name__ == "__main__":
    unittest.main()
