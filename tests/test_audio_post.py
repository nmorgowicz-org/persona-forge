from __future__ import annotations

import unittest

import numpy as np

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


class CompressTests(unittest.TestCase):
    def test_empty_input_returns_empty(self) -> None:
        result = compress(np.zeros(0, dtype=np.float32), 24000)
        self.assertEqual(result.size, 0)

    def test_reduces_peak_of_loud_signal(self) -> None:
        sr = 24000
        loud = _sine(220.0, 0.5, sr, amplitude=0.95)
        compressed = compress(loud, sr, threshold_db=-24.0, ratio=4.0)
        self.assertLess(np.max(np.abs(compressed)), np.max(np.abs(loud)))

    def test_leaves_quiet_signal_below_threshold_essentially_unchanged(self) -> None:
        sr = 24000
        quiet = _sine(220.0, 0.5, sr, amplitude=0.01)
        compressed = compress(quiet, sr, threshold_db=-24.0, ratio=4.0)
        np.testing.assert_allclose(compressed, quiet, atol=1e-3)


class NormalizeRmsTests(unittest.TestCase):
    def test_scales_to_target_rms(self) -> None:
        sr = 24000
        x = _sine(220.0, 0.5, sr, amplitude=0.1)
        target_dbfs = -20.0
        normalized = normalize_rms(x, target_dbfs)
        achieved_dbfs = 20.0 * np.log10(np.sqrt(np.mean(np.square(normalized))))
        self.assertAlmostEqual(achieved_dbfs, target_dbfs, places=1)

    def test_silence_is_a_noop(self) -> None:
        silence = np.zeros(1000, dtype=np.float32)
        result = normalize_rms(silence, -20.0)
        np.testing.assert_array_equal(result, silence)

    def test_empty_input_returns_empty(self) -> None:
        result = normalize_rms(np.zeros(0, dtype=np.float32), -20.0)
        self.assertEqual(result.size, 0)


class LimitPeakTests(unittest.TestCase):
    def test_scales_down_peak_above_ceiling(self) -> None:
        x = np.array([0.0, 0.5, -0.99, 0.2], dtype=np.float32)
        limited = limit_peak(x, ceiling_db=-1.0)
        ceiling = 10.0 ** (-1.0 / 20.0)
        self.assertLessEqual(np.max(np.abs(limited)), ceiling + 1e-6)

    def test_never_scales_up(self) -> None:
        x = np.array([0.0, 0.05, -0.02], dtype=np.float32)
        limited = limit_peak(x, ceiling_db=-1.0)
        np.testing.assert_array_equal(limited, x)


class CrossfadeConcatTests(unittest.TestCase):
    def test_output_length_accounts_for_overlap(self) -> None:
        sr = 24000
        seg_a = _sine(220.0, 0.3, sr)
        seg_b = _sine(330.0, 0.3, sr)
        crossfade_ms = 50.0
        result = crossfade_concat([seg_a, seg_b], sr, crossfade_ms=crossfade_ms)
        fade_len = int(sr * crossfade_ms / 1000.0)
        self.assertEqual(result.size, seg_a.size + seg_b.size - fade_len)

    def test_single_segment_passthrough(self) -> None:
        sr = 24000
        seg = _sine(220.0, 0.3, sr)
        result = crossfade_concat([seg], sr)
        np.testing.assert_array_equal(result, seg)

    def test_empty_list_returns_empty(self) -> None:
        result = crossfade_concat([], 24000)
        self.assertEqual(result.size, 0)

    def test_three_segments_join_without_dropping_the_middle(self) -> None:
        sr = 24000
        segs = [_sine(f, 0.2, sr) for f in (220.0, 330.0, 440.0)]
        result = crossfade_concat(segs, sr, crossfade_ms=50.0)
        fade_len = int(sr * 50.0 / 1000.0)
        expected_len = sum(s.size for s in segs) - 2 * fade_len
        self.assertEqual(result.size, expected_len)


class StitchSegmentsTests(unittest.TestCase):
    def test_uneven_segment_levels_end_up_close_after_stitching(self) -> None:
        sr = 24000
        quiet = _sine(220.0, 0.4, sr, amplitude=0.05)
        loud = _sine(220.0, 0.4, sr, amplitude=0.9)
        final = stitch_segments([quiet, loud], sr)
        # Split roughly at the midpoint and compare per-half RMS - stitching should have
        # pulled the two halves much closer together than the ~25x raw amplitude gap.
        mid = final.size // 2
        first_rms = np.sqrt(np.mean(np.square(final[:mid])) + 1e-9)
        second_rms = np.sqrt(np.mean(np.square(final[mid:])) + 1e-9)
        ratio = max(first_rms, second_rms) / max(min(first_rms, second_rms), 1e-9)
        self.assertLess(ratio, 2.0)

    def test_final_output_respects_ceiling(self) -> None:
        sr = 24000
        segs = [_sine(220.0, 0.3, sr, amplitude=0.99), _sine(440.0, 0.3, sr, amplitude=0.99)]
        final = stitch_segments(segs, sr, final_ceiling_db=-1.0)
        ceiling = 10.0 ** (-1.0 / 20.0)
        self.assertLessEqual(np.max(np.abs(final)), ceiling + 1e-6)

    def test_single_segment_still_produces_output(self) -> None:
        sr = 24000
        seg = _sine(220.0, 0.3, sr)
        final = stitch_segments([seg], sr)
        self.assertGreater(final.size, 0)


class TrimTests(unittest.TestCase):
    def test_trims_head_and_tail(self) -> None:
        sr = 24000
        seg = _sine(220.0, 1.0, sr)
        trimmed = trim(seg, sr, start_ms=100.0, end_ms=200.0)
        expected = seg.size - int(sr * 0.1) - int(sr * 0.2)
        self.assertEqual(trimmed.size, expected)

    def test_zero_trim_is_noop_length(self) -> None:
        sr = 24000
        seg = _sine(220.0, 0.3, sr)
        trimmed = trim(seg, sr)
        self.assertEqual(trimmed.size, seg.size)

    def test_empty_input_returns_empty(self) -> None:
        result = trim(np.zeros(0, dtype=np.float32), 24000, start_ms=50.0)
        self.assertEqual(result.size, 0)

    def test_never_goes_negative_length(self) -> None:
        sr = 24000
        seg = _sine(220.0, 0.05, sr)
        trimmed = trim(seg, sr, start_ms=1000.0, end_ms=1000.0)
        self.assertGreaterEqual(trimmed.size, 1)


class ApplyFadesTests(unittest.TestCase):
    def test_fade_in_starts_near_zero(self) -> None:
        sr = 24000
        seg = _sine(220.0, 0.5, sr, amplitude=0.8)
        faded = apply_fades(seg, sr, fade_in_ms=100.0)
        self.assertLess(abs(faded[0]), abs(seg[0]) + 1e-6)
        self.assertAlmostEqual(faded[0], 0.0, places=2)

    def test_fade_out_ends_near_zero(self) -> None:
        sr = 24000
        seg = _sine(220.0, 0.5, sr, amplitude=0.8)
        faded = apply_fades(seg, sr, fade_out_ms=100.0)
        self.assertAlmostEqual(faded[-1], 0.0, places=2)

    def test_no_fades_is_noop(self) -> None:
        sr = 24000
        seg = _sine(220.0, 0.3, sr)
        faded = apply_fades(seg, sr)
        np.testing.assert_array_equal(faded, seg)

    def test_empty_input_returns_empty(self) -> None:
        result = apply_fades(np.zeros(0, dtype=np.float32), 24000, fade_in_ms=50.0)
        self.assertEqual(result.size, 0)


class ConcatWithPaddingTests(unittest.TestCase):
    def test_no_padding_matches_crossfade_concat_length(self) -> None:
        sr = 24000
        segs = [_sine(220.0, 0.3, sr), _sine(330.0, 0.3, sr)]
        padded = concat_with_padding(segs, sr, crossfade_ms=50.0)
        crossfaded = crossfade_concat(segs, sr, crossfade_ms=50.0)
        self.assertEqual(padded.size, crossfaded.size)

    def test_padding_inserts_extra_length(self) -> None:
        sr = 24000
        segs = [_sine(220.0, 0.3, sr), _sine(330.0, 0.3, sr)]
        pad_ms = 150.0
        result = concat_with_padding(segs, sr, padding_ms=[pad_ms])
        self.assertGreater(result.size, segs[0].size + segs[1].size)

    def test_mismatched_padding_length_raises(self) -> None:
        sr = 24000
        segs = [_sine(220.0, 0.2, sr) for _ in range(3)]
        with self.assertRaises(ValueError):
            concat_with_padding(segs, sr, padding_ms=[10.0])

    def test_single_segment_passthrough(self) -> None:
        sr = 24000
        seg = _sine(220.0, 0.3, sr)
        result = concat_with_padding([seg], sr)
        np.testing.assert_array_equal(result, seg)


class StitchSegmentsExtendedTests(unittest.TestCase):
    def test_default_kwargs_match_original_behavior(self) -> None:
        sr = 24000
        segs = [_sine(220.0, 0.3, sr, amplitude=0.3), _sine(330.0, 0.3, sr, amplitude=0.6)]
        original = stitch_segments(segs, sr)
        with_defaults = stitch_segments(
            segs, sr, padding_ms=None, trims=None, fades=None, compress_params=None
        )
        np.testing.assert_array_equal(original, with_defaults)

    def test_padding_ms_extends_output(self) -> None:
        sr = 24000
        segs = [_sine(220.0, 0.3, sr), _sine(330.0, 0.3, sr)]
        no_pad = stitch_segments(segs, sr)
        with_pad = stitch_segments(segs, sr, padding_ms=[200.0])
        self.assertGreater(with_pad.size, no_pad.size)

    def test_trims_reduce_output(self) -> None:
        sr = 24000
        segs = [_sine(220.0, 0.5, sr), _sine(330.0, 0.5, sr)]
        untrimmed = stitch_segments(segs, sr)
        trimmed = stitch_segments(segs, sr, trims=[(100.0, 0.0), (0.0, 100.0)])
        self.assertLess(trimmed.size, untrimmed.size)


class AnalyzeTakeTests(unittest.TestCase):
    def test_empty_audio_is_flagged(self) -> None:
        flagged, reason = analyze_take(np.zeros(0, dtype=np.float32), 24000)
        self.assertTrue(flagged)
        self.assertEqual(reason, "empty")

    def test_silence_is_flagged(self) -> None:
        sr = 24000
        flagged, reason = analyze_take(np.zeros(sr * 2, dtype=np.float32), sr)
        self.assertTrue(flagged)
        self.assertEqual(reason, "near-silent")

    def test_sustained_pure_tone_is_flagged_as_drone(self) -> None:
        # A pure sine held for a couple seconds is exactly the narrowband, near-zero-variance
        # spectral-flatness signature the drone heuristic targets — this is the failure mode
        # from nick's report (2026-07-03: candidates that are "just dead air/drones/sfx").
        sr = 24000
        tone = _sine(220.0, 2.0, sr, amplitude=0.6)
        flagged, reason = analyze_take(tone, sr)
        self.assertTrue(flagged)
        self.assertEqual(reason, "tonal/drone-like")

    def test_broadband_noise_is_not_flagged(self) -> None:
        # White noise has high, frame-to-frame-varying spectral flatness — the opposite
        # signature from a drone — so it's a reasonable stand-in for "not obviously broken"
        # audio given the test suite has no real speech samples available.
        sr = 24000
        rng = np.random.default_rng(0)
        noise = (rng.standard_normal(sr * 2) * 0.2).astype(np.float32)
        flagged, reason = analyze_take(noise, sr)
        self.assertFalse(flagged)
        self.assertEqual(reason, "ok")


if __name__ == "__main__":
    unittest.main()
