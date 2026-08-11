"""Test OmniVoice engine retry, flags, clamping, and param omission."""

import sys
import types
import pytest
import numpy as np

from tests.fixtures.fake_omnivoice import FakeOmniVoiceModel


def _sine(freq: float, duration: float, sr: int, amplitude: float = 0.6) -> np.ndarray:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _noise(duration: float, sr: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(int(sr * duration)) * 0.2).astype(np.float32)


def _prepare_engine(model_draws, sr=24000):
    """Shared helper to install FakeOmniVoiceModel and patch engine deps."""
    fake_model_holder = {"model": model_draws}

    fake_omnivoice = types.ModuleType("omnivoice")
    fake_omnivoice.OmniVoice = types.SimpleNamespace(
        from_pretrained=lambda *a, **k: fake_model_holder["model"]
    )
    sys.modules["omnivoice"] = fake_omnivoice

    from persona_forge import omnivoice_engine as eng

    patcher1 = pytest.importorskip(
        "unittest.mock", reason="mock needed"
    ).patch.object(
        eng, "has_speech", lambda wav, sr: (True, "stub", -1.0)
    )
    patcher2 = pytest.importorskip(
        "unittest.mock", reason="mock needed"
    ).patch.object(
        eng, "compute_transcript_match_score", lambda ref, hyp: 1.0
    )
    patcher1.start()
    patcher2.start()

    return eng, fake_model_holder, (patcher1, patcher2)


@pytest.mark.slow
@pytest.mark.integration
class TestOmniVoiceRetry:

    def test_first_draw_drone_retried_once(self):
        sr = 24000
        model = FakeOmniVoiceModel(
            draws=[
                _sine(220.0, 1.0, sr),
                _noise(1.0, sr),
            ],
            sr=sr,
        )

        eng, holder, (p1, p2) = _prepare_engine(model)
        try:
            results = eng.run_omnivoice_job(
                segments=["hello there"],
                instruct="female, young adult, moderate pitch",
                candidates_per_segment=1,
            )

            assert len(results) == 1
            assert len(results[0]) == 1
            wav, out_sr, flagged, reason, transcript, match_score = results[0][0]
            assert not flagged
            assert reason == "ok"
            assert len(model.calls) == 2
        finally:
            p1.stop()
            p2.stop()

    def test_all_flagged_returned_not_raised(self):
        sr = 24000
        model = FakeOmniVoiceModel(
            draws=[
                _sine(220.0, 1.0, sr),
                _sine(220.0, 1.0, sr),
                _sine(220.0, 1.0, sr),
            ],
            sr=sr,
        )

        eng, holder, (p1, p2) = _prepare_engine(model)
        try:
            results = eng.run_omnivoice_job(
                segments=["hello there"],
                instruct="female, young adult, moderate pitch",
                candidates_per_segment=1,
            )

            _, _, flagged, reason, _, _ = results[0][0]
            assert flagged is True
            assert "tonal" in reason.lower() or "drone" in reason.lower()
            assert len(model.calls) == 3
        finally:
            p1.stop()
            p2.stop()


@pytest.mark.slow
@pytest.mark.integration
class TestOmniVoiceParams:

    def test_num_step_clamped(self):
        sr = 24000
        model = FakeOmniVoiceModel(draws=[_noise(1.0, sr)], sr=sr)

        eng, holder, (p1, p2) = _prepare_engine(model)
        try:
            eng.run_omnivoice_job(
                segments=["hello there"],
                instruct="female",
                candidates_per_segment=1,
                num_step=999,
                durations=[3.5],
                speed=0.1,
            )

            call_kwargs = model.calls[0]
            assert call_kwargs["num_step"] == eng.MAX_NUM_STEP
            assert call_kwargs["duration"] == 3.5
            assert call_kwargs["speed"] == eng.MIN_SPEED
        finally:
            p1.stop()
            p2.stop()

    def test_omitted_params_not_passed(self):
        sr = 24000
        model = FakeOmniVoiceModel(draws=[_noise(1.0, sr)], sr=sr)

        eng, holder, (p1, p2) = _prepare_engine(model)
        try:
            eng.run_omnivoice_job(
                segments=["hello there"],
                instruct="female",
                candidates_per_segment=1,
            )

            call_kwargs = model.calls[0]
            assert "num_step" not in call_kwargs
            assert "duration" not in call_kwargs
            assert "speed" not in call_kwargs
        finally:
            p1.stop()
            p2.stop()
