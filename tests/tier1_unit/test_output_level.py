"""Serving-layer loudness normalisation (plan §4.6 item 4)."""

from __future__ import annotations

import numpy as np
import pytest

from persona_forge import output_level

SR = 24000


def _tone(rms: float, seconds: float = 1.0, freq: float = 220.0, dtype: type = np.float32) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    # A sine's RMS is amplitude / sqrt(2).
    return (rms * np.sqrt(2.0) * np.sin(2 * np.pi * freq * t)).astype(dtype)


def _rms_db(x: np.ndarray) -> float:
    return 20 * np.log10(np.sqrt(np.mean(np.square(x.astype(np.float64)))))


@pytest.mark.parametrize("rms", [0.02, 0.09, 0.2])
def test_tones_of_any_level_land_on_the_target(rms):
    result = output_level.normalize(_tone(rms), SR)

    assert result.applied is True
    assert _rms_db(result.audio) == pytest.approx(output_level.TARGET_RMS_DBFS, abs=0.1)


def test_a_loud_and_a_quiet_source_end_within_a_decibel_of_each_other():
    quiet = output_level.normalize(_tone(0.09), SR).audio  # Pocket-like
    loud = output_level.normalize(_tone(0.2), SR).audio  # Kitten-2-like

    assert abs(_rms_db(quiet) - _rms_db(loud)) < 1.0


def test_gain_is_reported_in_decibels():
    result = output_level.normalize(_tone(0.2), SR)

    assert result.gain_db == pytest.approx(output_level.TARGET_RMS_DBFS - _rms_db(_tone(0.2)), abs=0.05)


@pytest.mark.parametrize("shape", [0, 1, 7])
def test_silent_or_empty_audio_is_returned_untouched(shape):
    silent = np.zeros(shape, dtype=np.float32)

    result = output_level.normalize(silent, SR)

    assert result.applied is False
    assert result.gain_db == 0.0
    assert np.array_equal(result.audio, silent)
    assert np.isfinite(result.audio).all()


def test_near_silent_noise_is_not_amplified_into_audibility():
    hiss = _tone(1e-5)  # about -100 dBFS

    result = output_level.normalize(hiss, SR)

    assert result.applied is False
    assert np.array_equal(result.audio, hiss)


def test_non_finite_samples_do_not_blow_up():
    bad = _tone(0.1)
    bad[10] = np.nan
    bad[20] = np.inf

    result = output_level.normalize(bad, SR)

    assert np.isfinite(result.audio).all()
    assert np.abs(result.audio).max() <= 1.0


def test_boost_is_capped_so_a_very_quiet_clip_is_not_inflated_to_the_target():
    quiet = _tone(0.003)  # -50 dBFS, above the silence floor

    result = output_level.normalize(quiet, SR)

    assert result.applied is True
    assert result.gain_db == pytest.approx(output_level.MAX_BOOST_DB)
    assert _rms_db(result.audio) < output_level.TARGET_RMS_DBFS


def test_peaky_audio_is_limited_below_the_ceiling_without_hard_clipping():
    audio = _tone(0.03)
    audio[5000] = 0.9  # a click that the target gain would push far past full scale

    result = output_level.normalize(audio, SR)

    ceiling = 10 ** (output_level.PEAK_CEILING_DBFS / 20)
    assert np.abs(result.audio).max() <= ceiling + 1e-6
    # No run of samples glued to the ceiling (that would be hard clipping).
    assert np.count_nonzero(np.abs(result.audio) >= ceiling - 1e-6) <= 2


def test_loud_input_that_already_clips_comes_out_inside_the_ceiling():
    clipped = np.clip(_tone(0.6), -1.0, 1.0)

    result = output_level.normalize(clipped, SR)

    assert np.abs(result.audio).max() <= 10 ** (output_level.PEAK_CEILING_DBFS / 20) + 1e-6


def test_samples_below_the_knee_are_scaled_linearly():
    audio = _tone(0.05)

    result = output_level.normalize(audio, SR)

    gain = 10 ** (result.gain_db / 20)
    assert np.allclose(result.audio, audio * gain, atol=1e-6)


def test_pauses_do_not_drag_the_measured_level_down():
    speech = _tone(0.1, seconds=1.0)
    padded = np.concatenate([np.zeros(SR * 2, dtype=np.float32), speech, np.zeros(SR * 2, dtype=np.float32)])

    bare = output_level.normalize(speech, SR)
    with_pauses = output_level.normalize(padded, SR)

    assert with_pauses.gain_db == pytest.approx(bare.gain_db, abs=0.1)


def test_int16_input_is_accepted_and_returned_as_float():
    audio = (_tone(0.2) * 32767).astype(np.int16)

    result = output_level.normalize(audio, SR)

    assert result.audio.dtype == np.float32
    assert _rms_db(result.audio) == pytest.approx(output_level.TARGET_RMS_DBFS, abs=0.2)


def test_float64_input_does_not_change_dtype_semantics():
    result = output_level.normalize(_tone(0.1, dtype=np.float64), SR)

    assert result.audio.dtype == np.float32


def test_input_array_is_not_modified_in_place():
    audio = _tone(0.1)
    before = audio.copy()

    output_level.normalize(audio, SR)

    assert np.array_equal(audio, before)


def test_clip_shorter_than_one_gate_frame_is_still_measured():
    short = _tone(0.1, seconds=0.005)

    result = output_level.normalize(short, SR)

    assert result.applied is True
    assert _rms_db(result.audio) == pytest.approx(output_level.TARGET_RMS_DBFS, abs=0.2)


@pytest.mark.parametrize("value", [None, "", "1", "true", "on", "yes", "garbage"])
def test_enabled_by_default_and_for_truthy_values(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("TTS_NORMALIZE_LOUDNESS", raising=False)
    else:
        monkeypatch.setenv("TTS_NORMALIZE_LOUDNESS", value)

    assert output_level.enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "no", "off", " off "])
def test_env_opt_out(monkeypatch, value):
    monkeypatch.setenv("TTS_NORMALIZE_LOUDNESS", value)

    assert output_level.enabled() is False


def test_request_field_overrides_the_environment_default(monkeypatch):
    monkeypatch.delenv("TTS_NORMALIZE_LOUDNESS", raising=False)
    assert output_level.resolve_enabled(False) is False
    assert output_level.resolve_enabled(None) is True

    monkeypatch.setenv("TTS_NORMALIZE_LOUDNESS", "0")
    assert output_level.resolve_enabled(None) is False
    assert output_level.resolve_enabled(True) is True


def test_disabled_normalize_returns_audio_unchanged():
    audio = _tone(0.2)

    result = output_level.normalize(audio, SR, enabled=False)

    assert result.applied is False
    assert result.audio is audio
