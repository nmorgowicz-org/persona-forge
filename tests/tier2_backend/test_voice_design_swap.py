"""Test VoiceDesign swap behavior between Base and VOICE_DESIGN_PROFILE."""

import types
import pytest


@pytest.mark.integration
class TestVoiceDesignSwap:

    def test_swap_to_voice_design_stays_loaded(self, app_module, rt):
        vd = app_module.voice_design
        vd._swap_in_progress = False

        from qwen3_tts import model

        # voice_design.py calls model.load_model(model.VOICE_DESIGN_PROFILE)
        # where model.VOICE_DESIGN_PROFILE is the real ModelProfile object.
        # We patch load_model to simulate loading the VoiceDesign checkpoint.
        original_load = model.load_model

        def fake_load_model(profile):
            # If profile is the VOICE_DESIGN_PROFILE (real ModelProfile or string),
            # set tts_model_type accordingly.
            is_vd = (
                (hasattr(profile, "name") and profile.name == "voice_design")
                or str(profile) in ("VOICE_DESIGN", "voice_design")
            )
            rt._model_loaded = True
            rt.active_profile = "VOICE_DESIGN" if is_vd else "BASE"
            rt.model = types.SimpleNamespace(
                model=types.SimpleNamespace(
                    tts_model_type="voice_design" if is_vd else "base"
                ),
                generate_voice_design=lambda **kw: (
                    [types.SimpleNamespace()], 24000
                ),
            )

        model.load_model = fake_load_model

        try:
            wav, sr, resolved_seed = vd.run_voice_design_request(
                description="calm narrator",
                sample_text="hello there",
                language="English",
                seed=42,
            )

            assert rt._model_loaded is True
            assert vd.swap_in_progress() is False
        finally:
            model.load_model = original_load

    def test_failure_unloads_without_restore(self, app_module, rt):
        vd = app_module.voice_design
        vd._swap_in_progress = False

        from qwen3_tts import model
        original_force_unload = model.force_unload
        original_load_model = model.load_model

        def failing_load_model(profile):
            is_vd = (
                (hasattr(profile, "name") and profile.name == "voice_design")
                or str(profile) in ("VOICE_DESIGN", "voice_design")
            )
            rt._model_loaded = True
            rt.model = types.SimpleNamespace(
                model=types.SimpleNamespace(
                    tts_model_type="voice_design" if is_vd else "base"
                ),
                generate_voice_design=lambda *a, **kw: (_raise_boom(),),
            )

        def _raise_boom():
            raise RuntimeError("boom")

        model.load_model = failing_load_model

        try:
            with pytest.raises(RuntimeError, match="boom"):
                vd.run_voice_design_request(
                    description="x",
                    sample_text="hello",
                    language="English",
                )

            # On failure, VoiceDesign is unloaded; Base is NOT restored (by design).
            assert rt._model_loaded is False
            assert rt.model is None
            assert vd.swap_in_progress() is False
        finally:
            model.force_unload = original_force_unload
            model.load_model = original_load_model

    def test_validate_sample_text_accepts_short(self, app_module):
        app_module.voice_design.validate_sample_text("A short reference sample.")

    def test_validate_sample_text_rejects_long(self, app_module):
        long_text = " ".join(["word"] * 200)
        with pytest.raises(ValueError, match="too long"):
            app_module.voice_design.validate_sample_text(long_text)
