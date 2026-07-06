"""Test audio_post DSP helpers — pure numpy, no app, no Docker."""

from __future__ import annotations

import numpy as np
import pytest

from qwen3_tts.audio_post import (
    analyze_take,
    apply_fades,
    compress,
    concat_with_padding,
    crossfade_concat,
    limit_peak,
    normalize_rms,
    stitch_segments,
    trim,
)


def _sine(freq: float, duration: float, sr: int, amplitude: float = 0.5) -> np.ndarray:
    t = np.linspace(0.0, duration, int(sr * duration), endpoint=False, dtype=np.float32)
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


class TestCompress:
    def test_empty_input(self):
        result = compress(np.zeros(0, dtype=np.float32), 24000)
        assert result.size == 0

    def test_reduces_peak_of_loud_signal(self):
        loud = _sine(220.0, 0.5, 24000, amplitude=0.95)
        compressed = compress(loud, 24000, threshold_db=-24.0, ratio=4.0)
        assert np.max(np.abs(compressed)) < np.max(np.abs(loud))

    def test_quiet_signal_unchanged(self):
        quiet = _sine(220.0, 0.5, 24000, amplitude=0.01)
        compressed = compress(quiet, 24000, threshold_db=-24.0, ratio=4.0)
        np.testing.assert_allclose(compressed, quiet, atol=1e-3)


class TestNormalizeRms:
    def test_scales_to_target_rms(self):
        x = _sine(220.0, 0.5, 24000, amplitude=0.1)
        normalized = normalize_rms(x, -20.0)
        achieved_dbfs = 20.0 * np.log10(np.sqrt(np.mean(np.square(normalized))))
        assert pytest.approx(-20.0, abs=1.0) == achieved_dbfs

    def test_silence_noop(self):
        silence = np.zeros(1000, dtype=np.float32)
        result = normalize_rms(silence, -20.0)
        np.testing.assert_array_equal(result, silence)

    def test_empty(self):
        result = normalize_rms(np.zeros(0, dtype=np.float32), -20.0)
        assert result.size == 0


class TestLimitPeak:
    def test_scales_down_peak_above_ceiling(self):
        x = np.array([0.0, 0.5, -0.99, 0.2], dtype=np.float32)
        limited = limit_peak(x, ceiling_db=-1.0)
        ceiling = 10.0 ** (-1.0 / 20.0)
        assert np.max(np.abs(limited)) <= ceiling + 1e-6

    def test_never_scales_up(self):
        x = np.array([0.0, 0.05, -0.02], dtype=np.float32)
        limited = limit_peak(x, ceiling_db=-1.0)
        np.testing.assert_array_equal(limited, x)


class TestCrossfadeConcat:
    def test_output_length_accounts_for_overlap(self):
        sr = 24000
        seg_a = _sine(220.0, 0.3, sr)
        seg_b = _sine(330.0, 0.3, sr)
        crossfade_ms = 50.0
        result = crossfade_concat([seg_a, seg_b], sr, crossfade_ms=crossfade_ms)
        fade_len = int(sr * crossfade_ms / 1000.0)
        assert result.size == seg_a.size + seg_b.size - fade_len

    def test_single_segment_passthrough(self):
        seg = _sine(220.0, 0.3, 24000)
        result = crossfade_concat([seg], 24000)
        np.testing.assert_array_equal(result, seg)

    def test_empty_list(self):
        result = crossfade_concat([], 24000)
        assert result.size == 0

    def test_three_segments_no_middle_drop(self):
        sr = 24000
        segs = [_sine(f, 0.2, sr) for f in (220.0, 330.0, 440.0)]
        result = crossfade_concat(segs, sr, crossfade_ms=50.0)
        fade_len = int(sr * 50.0 / 1000.0)
        expected_len = sum(s.size for s in segs) - 2 * fade_len
        assert result.size == expected_len


class TestStitchSegments:
    def test_uneven_levels_equalized(self):
        sr = 24000
        quiet = _sine(220.0, 0.4, sr, amplitude=0.05)
        loud = _sine(220.0, 0.4, sr, amplitude=0.9)
        final = stitch_segments([quiet, loud], sr)
        mid = final.size // 2
        first_rms = np.sqrt(np.mean(np.square(final[:mid])) + 1e-9)
        second_rms = np.sqrt(np.mean(np.square(final[mid:])) + 1e-9)
        ratio = max(first_rms, second_rms) / max(min(first_rms, second_rms), 1e-9)
        assert ratio < 2.0

    def test_ceiling_respected(self):
        sr = 24000
        segs = [_sine(220.0, 0.3, sr, amplitude=0.99), _sine(440.0, 0.3, sr, amplitude=0.99)]
        final = stitch_segments(segs, sr, final_ceiling_db=-1.0)
        ceiling = 10.0 ** (-1.0 / 20.0)
        assert np.max(np.abs(final)) <= ceiling + 1e-6

    def test_single_segment(self):
        seg = _sine(220.0, 0.3, 24000)
        assert stitch_segments([seg], 24000).size > 0


class TestTrim:
    def test_trims_head_and_tail(self):
        sr = 24000
        seg = _sine(220.0, 1.0, sr)
        trimmed = trim(seg, sr, start_ms=100.0, end_ms=200.0)
        expected = seg.size - int(sr * 0.1) - int(sr * 0.2)
        assert trimmed.size == expected

    def test_zero_trim_noop(self):
        seg = _sine(220.0, 0.3, 24000)
        trimmed = trim(seg, 24000)
        assert trimmed.size == seg.size

    def test_empty_input(self):
        result = trim(np.zeros(0, dtype=np.float32), 24000, start_ms=50.0)
        assert result.size == 0

    def test_never_negative_length(self):
        sr = 24000
        seg = _sine(220.0, 0.05, sr)
        trimmed = trim(seg, sr, start_ms=1000.0, end_ms=1000.0)
        assert trimmed.size >= 1


class TestApplyFades:
    def test_fade_in_starts_near_zero(self):
        seg = _sine(220.0, 0.5, 24000, amplitude=0.8)
        faded = apply_fades(seg, 24000, fade_in_ms=100.0)
        assert abs(faded[0]) < abs(seg[0]) + 1e-6
        assert pytest.approx(faded[0], abs=1e-2) == 0.0

    def test_fade_out_ends_near_zero(self):
        seg = _sine(220.0, 0.5, 24000, amplitude=0.8)
        faded = apply_fades(seg, 24000, fade_out_ms=100.0)
        assert pytest.approx(faded[-1], abs=1e-2) == 0.0

    def test_no_fades_noop(self):
        seg = _sine(220.0, 0.3, 24000)
        faded = apply_fades(seg, 24000)
        np.testing.assert_array_equal(faded, seg)

    def test_empty_input(self):
        result = apply_fades(np.zeros(0, dtype=np.float32), 24000, fade_in_ms=50.0)
        assert result.size == 0


class TestConcatWithPadding:
    def test_no_padding_matches_crossfade_length(self):
        sr = 24000
        segs = [_sine(220.0, 0.3, sr), _sine(330.0, 0.3, sr)]
        padded = concat_with_padding(segs, sr, crossfade_ms=50.0)
        crossfaded = crossfade_concat(segs, sr, crossfade_ms=50.0)
        assert padded.size == crossfaded.size

    def test_padding_inserts_extra_length(self):
        sr = 24000
        segs = [_sine(220.0, 0.3, sr), _sine(330.0, 0.3, sr)]
        result = concat_with_padding(segs, sr, padding_ms=[150.0])
        assert result.size > segs[0].size + segs[1].size

    def test_mismatched_padding_raises(self):
        segs = [_sine(220.0, 0.2, 24000) for _ in range(3)]
        with pytest.raises(ValueError):
            concat_with_padding(segs, 24000, padding_ms=[10.0])

    def test_single_segment_passthrough(self):
        seg = _sine(220.0, 0.3, 24000)
        result = concat_with_padding([seg], 24000)
        np.testing.assert_array_equal(result, seg)


class TestStitchSegmentsExtended:
    def test_default_kwargs_unchanged(self):
        sr = 24000
        segs = [_sine(220.0, 0.3, sr, amplitude=0.3), _sine(330.0, 0.3, sr, amplitude=0.6)]
        original = stitch_segments(segs, sr)
        with_defaults = stitch_segments(
            segs, sr, padding_ms=None, trims=None, fades=None, compress_params=None
        )
        np.testing.assert_array_equal(original, with_defaults)

    def test_padding_extends_output(self):
        sr = 24000
        segs = [_sine(220.0, 0.3, sr), _sine(330.0, 0.3, sr)]
        assert stitch_segments(segs, sr, padding_ms=[200.0]).size > stitch_segments(segs, sr).size

    def test_trims_reduce_output(self):
        sr = 24000
        segs = [_sine(220.0, 0.5, sr), _sine(330.0, 0.5, sr)]
        trimmed = stitch_segments(segs, sr, trims=[(100.0, 0.0), (0.0, 100.0)])
        assert trimmed.size < stitch_segments(segs, sr).size


class TestAnalyzeTake:
    def test_empty_flagged(self):
        flagged, reason = analyze_take(np.zeros(0, dtype=np.float32), 24000)
        assert flagged
        assert reason == "empty"

    def test_silence_flagged(self):
        flagged, reason = analyze_take(np.zeros(24000 * 2, dtype=np.float32), 24000)
        assert flagged
        assert reason == "near-silent"

    def test_pure_tone_drone_flagged(self):
        tone = _sine(220.0, 2.0, 24000, amplitude=0.6)
        flagged, reason = analyze_take(tone, 24000)
        assert flagged
        assert reason == "tonal/drone-like"

    def test_broadband_noise_ok(self):
        rng = np.random.default_rng(0)
        noise = (rng.standard_normal(24000 * 2) * 0.2).astype(np.float32)
        flagged, reason = analyze_take(noise, 24000)
        assert not flagged
        assert reason == "ok"
