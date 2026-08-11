"""Test config.apply_preset_env for preset and override behavior."""

from __future__ import annotations

from persona_forge.config import apply_preset_env


class TestApplyPresetEnv:
    def test_06b_sets_expected_vars(self):
        environ = {"MODEL_SIZE": "0.6b"}
        preset = apply_preset_env(environ)
        # pytorch, not pocket_tts: this preset is Qwen3-TTS-specific (model_repo points at a
        # Qwen3-TTS checkpoint), which pocket_tts (a separate engine) cannot run. The product
        # default of TTS_BACKEND=pocket_tts comes from .env.example setting it explicitly,
        # which wins over this preset fallback (see config.py's explicit-wins rule).
        assert environ["TTS_BACKEND"] == "pytorch"
        assert environ["OV_MODEL_DIR"] == "/ov/0.6B/ir"
        assert environ["OPENVINO_VOCODER_ENABLED"] == "1"

    def test_17b_sets_expected_vars(self):
        environ = {"MODEL_SIZE": "1.7B"}
        preset = apply_preset_env(environ)
        assert environ["TTS_BACKEND"] == "pytorch"
        assert environ["OV_MAIN_COMPRESSION"] == "int4"

    def test_explicit_tts_backend_openvino_still_works(self):
        environ = {"MODEL_SIZE": "1.7B", "TTS_BACKEND": "openvino"}
        apply_preset_env(environ)
        assert environ["TTS_BACKEND"] == "openvino"
        assert environ["OV_MAIN_COMPRESSION"] == "int4"

    def test_explicit_tts_backend_wins(self):
        environ = {"MODEL_SIZE": "1.7B", "TTS_BACKEND": "pytorch"}
        apply_preset_env(environ)
        assert environ["TTS_BACKEND"] == "pytorch"

    def test_hyphenated_pocket_backend_is_canonicalized(self):
        environ = {"MODEL_SIZE": "1.7B", "TTS_BACKEND": " pocket-tts "}
        apply_preset_env(environ)
        assert environ["TTS_BACKEND"] == "pocket_tts"

    def test_explicit_ov_var_wins(self):
        environ = {"MODEL_SIZE": "0.6B", "OPENVINO_MAIN_STATEFUL_MODEL": "/custom/path.xml"}
        apply_preset_env(environ)
        assert environ["OPENVINO_MAIN_STATEFUL_MODEL"] == "/custom/path.xml"

    def test_tts_max_speech_seconds_override(self):
        environ = {"MODEL_SIZE": "1.7B", "TTS_MAX_SPEECH_SECONDS": "20"}
        preset = apply_preset_env(environ)
        assert preset["max_speech_seconds"] == 20.0
        assert environ["TTS_MAX_SPEECH_SECONDS"] == "20"

    def test_preset_max_speech_seconds_when_not_set(self):
        environ = {"MODEL_SIZE": "0.6B"}
        apply_preset_env(environ)
        assert environ["TTS_MAX_SPEECH_SECONDS"] == "64.0"
