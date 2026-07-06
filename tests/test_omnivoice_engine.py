from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

import numpy as np


def _sine(freq: float, duration: float, sr: int, amplitude: float = 0.6) -> np.ndarray:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _noise(duration: float, sr: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(int(sr * duration)) * 0.2).astype(np.float32)


class FakeOmniVoiceModel:
    """Stands in for the real `omnivoice.OmniVoice` checkpoint. `draws` is consumed one
    array per `generate()` call, in order, so a test can script "first draw is a drone,
    second draw is clean" to exercise the retry-once-on-flag path in run_omnivoice_job."""

    def __init__(self, draws: list[np.ndarray], sr: int):
        self.draws = list(draws)
        self.sr = sr
        self.calls: list[dict] = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return [self.draws.pop(0)]


class RunOmnivoiceJobTests(unittest.TestCase):
    def setUp(self):
        # omnivoice_engine does `import torch; from omnivoice import OmniVoice` inline inside
        # run_omnivoice_job, and `from qwen3_tts import model` at module scope — none of
        # torch/omnivoice/qwen_tts (model.py's own real dependency) are installed in the test
        # environment. Faking qwen3_tts.model wholesale via sys.modules is this repo's
        # established pattern for exercising app/engine logic without the real model stack
        # (see tests/test_app_api.py's `fake_model` setup) — mirrored here rather than
        # invented fresh.
        import qwen3_tts as _qwen3_tts_pkg

        self._pkg = _qwen3_tts_pkg
        self._sub_names = ("model", "omnivoice_engine")
        self._mod_names = ("torch", "omnivoice", "qwen3_tts.model", "qwen3_tts.omnivoice_engine")
        self._orig_modules = {name: sys.modules.get(name) for name in self._mod_names}
        self._orig_pkg_attrs = {
            name: getattr(_qwen3_tts_pkg, name, None) for name in self._sub_names
        }

        fake_torch = types.ModuleType("torch")
        fake_torch.float32 = "float32"
        sys.modules["torch"] = fake_torch

        self.fake_model_holder: dict[str, FakeOmniVoiceModel] = {}

        def _from_pretrained(*args, **kwargs):
            return self.fake_model_holder["model"]

        fake_omnivoice = types.ModuleType("omnivoice")
        fake_omnivoice.OmniVoice = types.SimpleNamespace(from_pretrained=_from_pretrained)
        sys.modules["omnivoice"] = fake_omnivoice

        fake_model_module = types.ModuleType("qwen3_tts.model")
        fake_model_module._touch_last_request = lambda: None
        fake_model_module.force_unload = lambda: None
        fake_model_module._apply_optional_seed = lambda seed: None
        fake_model_module._trim_silence = lambda wav, sr: wav
        fake_model_module.register_foreign_engine = lambda is_loaded, unload: None

        # `from qwen3_tts import model` (both here and inside omnivoice_engine.py) resolves via
        # `hasattr(qwen3_tts_pkg, "model")` *before* ever consulting sys.modules — so once any
        # earlier test (e.g. test_app_api.py's own module-scope fake) has set that package
        # attribute once, merely reassigning sys.modules["qwen3_tts.model"] is silently ignored
        # by later `from qwen3_tts import model` statements, AND a stale cached
        # `qwen3_tts.omnivoice_engine` attribute means popping sys.modules alone doesn't force a
        # reimport either. Must set sys.modules *and* delete/reset the package attribute for
        # both names so a fresh `from qwen3_tts import omnivoice_engine` below actually rebinds
        # against our fakes.
        sys.modules["qwen3_tts.model"] = fake_model_module
        _qwen3_tts_pkg.model = fake_model_module
        sys.modules.pop("qwen3_tts.omnivoice_engine", None)
        if hasattr(_qwen3_tts_pkg, "omnivoice_engine"):
            delattr(_qwen3_tts_pkg, "omnivoice_engine")

    def tearDown(self):
        for name, orig in self._orig_pkg_attrs.items():
            if orig is None:
                if hasattr(self._pkg, name):
                    delattr(self._pkg, name)
            else:
                setattr(self._pkg, name, orig)
        for name, orig in self._orig_modules.items():
            if orig is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = orig

    def _import_engine(self):
        """Import omnivoice_engine (fresh, per setUp's module faking above) and stub out its
        Whisper no-speech gate — asr_check.has_speech lazily imports faster-whisper, which
        isn't installed in this test environment, and real transcription has no place in a
        unit test anyway. Tests that care about the drone/silence heuristic exercise
        analyze_take directly (tests/test_audio_post.py); here the stub always reports
        "speech found" so it never interferes with the analyze_take-driven assertions."""
        from qwen3_tts import omnivoice_engine

        patcher1 = patch.object(omnivoice_engine, "has_speech", lambda wav, sr: (True, "stub", -1.0))
        patcher2 = patch.object(omnivoice_engine, "compute_transcript_match_score", lambda ref, hyp: 1.0)
        patcher1.start()
        patcher2.start()
        self.addCleanup(patcher1.stop)
        self.addCleanup(patcher2.stop)
        return omnivoice_engine

    def test_flagged_first_draw_is_retried_once_then_succeeds(self):
        omnivoice_engine = self._import_engine()

        sr = omnivoice_engine.OMNIVOICE_SAMPLE_RATE
        self.fake_model_holder["model"] = FakeOmniVoiceModel(
            draws=[_sine(220.0, 1.0, sr), _noise(1.0, sr)], sr=sr
        )

        results = omnivoice_engine.run_omnivoice_job(
            segments=["hello there"],
            instruct="female, young adult, moderate pitch",
            candidates_per_segment=1,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(len(results[0]), 1)
        wav, out_sr, flagged, reason, transcript, match_score = results[0][0]
        self.assertEqual(out_sr, sr)
        self.assertFalse(flagged)
        self.assertEqual(reason, "ok")
        self.assertEqual(len(self.fake_model_holder["model"].calls), 2)

    def test_still_flagged_after_max_attempts_is_returned_not_raised(self):
        omnivoice_engine = self._import_engine()

        sr = omnivoice_engine.OMNIVOICE_SAMPLE_RATE
        self.fake_model_holder["model"] = FakeOmniVoiceModel(
            draws=[
                _sine(220.0, 1.0, sr),
                _sine(220.0, 1.0, sr),
                _sine(220.0, 1.0, sr),
            ],
            sr=sr,
        )

        results = omnivoice_engine.run_omnivoice_job(
            segments=["hello there"],
            instruct="female, young adult, moderate pitch",
            candidates_per_segment=1,
        )

        _, _, flagged, reason, transcript, match_score = results[0][0]
        self.assertTrue(flagged)
        self.assertEqual(reason, "tonal/drone-like")
        self.assertEqual(len(self.fake_model_holder["model"].calls), 3)

    def test_num_step_duration_speed_are_forwarded_and_clamped(self):
        omnivoice_engine = self._import_engine()

        sr = omnivoice_engine.OMNIVOICE_SAMPLE_RATE
        self.fake_model_holder["model"] = FakeOmniVoiceModel(draws=[_noise(1.0, sr)], sr=sr)

        omnivoice_engine.run_omnivoice_job(
            segments=["hello there"],
            instruct="female, young adult, moderate pitch",
            candidates_per_segment=1,
            num_step=999,  # above MAX_NUM_STEP, must clamp
            durations=[3.5],
            speed=0.1,  # below MIN_SPEED, must clamp
        )

        call_kwargs = self.fake_model_holder["model"].calls[0]
        self.assertEqual(call_kwargs["num_step"], omnivoice_engine.MAX_NUM_STEP)
        self.assertEqual(call_kwargs["duration"], 3.5)
        self.assertEqual(call_kwargs["speed"], omnivoice_engine.MIN_SPEED)

    def test_omitted_params_are_not_passed_to_generate(self):
        omnivoice_engine = self._import_engine()

        sr = omnivoice_engine.OMNIVOICE_SAMPLE_RATE
        self.fake_model_holder["model"] = FakeOmniVoiceModel(draws=[_noise(1.0, sr)], sr=sr)

        omnivoice_engine.run_omnivoice_job(
            segments=["hello there"],
            instruct="female, young adult, moderate pitch",
            candidates_per_segment=1,
        )

        call_kwargs = self.fake_model_holder["model"].calls[0]
        self.assertNotIn("num_step", call_kwargs)
        self.assertNotIn("duration", call_kwargs)
        self.assertNotIn("speed", call_kwargs)


if __name__ == "__main__":
    unittest.main()
