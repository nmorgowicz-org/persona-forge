"""Test presets: capacity math, path separation, VoiceDesign preset."""

from __future__ import annotations

import pytest

from qwen3_tts.config import apply_preset_env
from qwen3_tts.presets import (
    capacity_for_seconds,
    get_preset,
    get_voice_design_preset,
    seconds_for_capacity,
)


class TestPresetsEnv:
    def test_06b_stateful_main_and_predictor(self):
        environ = {"MODEL_SIZE": "0.6b"}
        apply_preset_env(environ)
        assert environ["OV_MAIN_COMPRESSION"] == "int8"
        assert environ["OV_PREDICTOR_COMPRESSION"] == "int8"
        assert environ["OPENVINO_MAIN_STATEFUL_MODEL"] == "/ov/0.6B/main_stateful_cap768.xml"
        assert environ["OPENVINO_PREDICTOR_STATEFUL_MODEL"] == "/ov/0.6B/predictor_stateful_cap32.xml"
        assert environ["TTS_MAX_SPEECH_SECONDS"] == "64.0"

    def test_17b_int4_main_explicit_predictor(self):
        environ = {"MODEL_SIZE": "1.7B"}
        apply_preset_env(environ)
        assert environ["OV_MAIN_COMPRESSION"] == "int4"
        assert environ["OV_PREDICTOR_COMPRESSION"] == "int8"
        assert "OPENVINO_PREDICTOR_STATEFUL_MODEL" not in environ

    def test_expert_override(self):
        environ = {"MODEL_SIZE": "0.6B", "OV_MAIN_COMPRESSION": "fp32"}
        apply_preset_env(environ)
        assert environ["OV_MAIN_COMPRESSION"] == "fp32"

    def test_max_speech_seconds_env_override(self):
        environ = {"MODEL_SIZE": "1.7B", "TTS_MAX_SPEECH_SECONDS": "20"}
        apply_preset_env(environ)
        assert environ["OPENVINO_MAIN_STATEFUL_MODEL"] == "/ov/1.7B/main_stateful_cap240.xml"
        assert environ["TTS_MAX_SPEECH_SECONDS"] == "20"


class TestCapacityMath:
    def test_12hz_frame_rate(self):
        assert capacity_for_seconds(64) == 768
        assert capacity_for_seconds(20) == 240
        assert seconds_for_capacity(768) == 64.0

    def test_non_positive_raises(self):
        with pytest.raises(ValueError):
            capacity_for_seconds(0)


class TestGetPreset:
    def test_default_17b(self):
        preset = get_preset("1.7B")
        assert preset["stateful_capacity"] == 768
        assert preset["main_stateful_model"] == "/ov/1.7B/main_stateful_cap768.xml"

    def test_override_capacity_no_collision(self):
        default_preset = get_preset("1.7B")
        short_preset = get_preset("1.7B", max_speech_seconds=15)
        assert default_preset["main_stateful_model"] != short_preset["main_stateful_model"]
        assert short_preset["stateful_capacity"] == 180


class TestVoiceDesignPreset:
    def test_own_ir_tree(self):
        preset = get_voice_design_preset("1.7B")
        assert preset["model_repo"] == "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
        assert preset["ov_model_dir"] == "/ov/1.7B-voicedesign/ir"
        assert preset["vocoder_dir"] == "/ov/1.7B-voicedesign/vocoder"
        assert preset["stateful_capacity"] == 360
        assert preset["main_stateful_model"] == "/ov/1.7B-voicedesign/main_stateful_cap360.xml"

    def test_no_collision_with_base(self):
        base = get_preset("1.7B", max_speech_seconds=20)
        voice_design = get_voice_design_preset("1.7B")
        assert base["main_stateful_model"] != voice_design["main_stateful_model"]
        assert base["ov_model_dir"] != voice_design["ov_model_dir"]

    def test_default_int4(self):
        assert get_voice_design_preset("1.7B")["main_compression"] == "int4"

    def test_main_compression_override(self):
        assert get_voice_design_preset("1.7B", main_compression="int8")["main_compression"] == "int8"

    def test_rejects_unsupported_compression(self):
        with pytest.raises(ValueError):
            get_voice_design_preset("1.7B", main_compression="fp32")
