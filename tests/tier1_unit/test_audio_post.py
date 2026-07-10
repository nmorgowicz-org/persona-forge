"""Test audio_post DSP helpers — pure numpy, no app, no Docker."""

from __future__ import annotations

import numpy as np
import pytest

from qwen3_tts.audio_post import (
    analyze_take,
    apply_fades,
    apply_region_edits,
    apply_region_envelope,
    apply_region_fade,
    compress,
    concat_with_padding,
    crossfade_concat,
    insert_silence,
    limit_peak,
    normalize_rms,
    remove_range,
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

    def test_edits_none_matches_no_edits(self):
        sr = 24000
        segs = [_sine(220.0, 0.3, sr), _sine(330.0, 0.3, sr)]
        no_edits_kwarg = stitch_segments(segs, sr)
        empty_edits = stitch_segments(segs, sr, edits=[[], []])
        np.testing.assert_array_equal(no_edits_kwarg, empty_edits)

    def test_delete_edit_shrinks_a_segment(self):
        sr = 24000
        segs = [_sine(220.0, 0.5, sr), _sine(330.0, 0.5, sr)]
        edits = [[{"type": "delete", "start_ms": 0.0, "end_ms": 200.0}], []]
        result = stitch_segments(segs, sr, edits=edits)
        assert result.size < stitch_segments(segs, sr).size

    def test_insert_silence_edit_extends_a_segment(self):
        sr = 24000
        segs = [_sine(220.0, 0.3, sr), _sine(330.0, 0.3, sr)]
        edits = [[{"type": "insert_silence", "at_ms": 100.0, "duration_ms": 200.0}], []]
        result = stitch_segments(segs, sr, edits=edits)
        assert result.size > stitch_segments(segs, sr).size


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


class TestRegionEnvelope:
    def test_gain_blends_at_edges_and_flat_in_middle(self):
        sr = 1000
        x = np.ones(1000, dtype=np.float32)
        y = apply_region_envelope(x, sr, 200, 400, target_gain=0.5, fade_in_ms=50, fade_out_ms=50)
        assert y[199] == 1.0
        assert abs(y[300] - 0.5) < 1e-6
        assert abs(y[500] - 1.0) < 1e-6

    def test_mute_zeroes_flat_region(self):
        sr = 1000
        x = np.ones(1000, dtype=np.float32)
        y = apply_region_envelope(x, sr, 200, 400, target_gain=0.0)
        assert np.allclose(y[200:400], 0.0)
        assert np.allclose(y[:200], 1.0)
        assert np.allclose(y[400:], 1.0)

    def test_no_op_when_end_before_start(self):
        sr = 1000
        x = np.ones(1000, dtype=np.float32)
        y = apply_region_envelope(x, sr, 400, 200, target_gain=0.0)
        assert np.allclose(y, 1.0)


class TestRegionFade:
    def test_ramps_to_silence_at_region_edges(self):
        sr = 1000
        x = np.ones(1000, dtype=np.float32)
        y = apply_region_fade(x, sr, 200, 400, fade_in_ms=50, fade_out_ms=50)
        assert abs(y[200]) < 1e-6
        assert abs(y[300] - 1.0) < 1e-6
        assert abs(y[399]) < 0.05
        assert np.allclose(y[:200], 1.0)
        assert np.allclose(y[400:], 1.0)


class TestRemoveRange:
    def test_deletes_samples(self):
        sr = 1000
        x = np.arange(1000, dtype=np.float32)
        y = remove_range(x, sr, 200, 300)
        assert y.size == 900
        assert y[199] == 199
        assert y[200] == 300

    def test_clamps_out_of_range(self):
        sr = 1000
        x = np.ones(1000, dtype=np.float32)
        y = remove_range(x, sr, -100, 5000)
        assert y.size == 0


class TestInsertSilence:
    def test_inserts_zeros_at_position(self):
        sr = 1000
        x = np.ones(1000, dtype=np.float32)
        y = insert_silence(x, sr, 200, 100)
        assert y.size == 1100
        assert np.allclose(y[200:300], 0.0)
        assert np.allclose(y[:200], 1.0)
        assert np.allclose(y[300:], 1.0)

    def test_zero_duration_is_no_op(self):
        sr = 1000
        x = np.ones(1000, dtype=np.float32)
        y = insert_silence(x, sr, 200, 0)
        assert y.size == 1000


class TestApplyRegionEdits:
    def test_no_edits_returns_unchanged(self):
        sr = 1000
        x = np.ones(1000, dtype=np.float32)
        y = apply_region_edits(x, sr, [])
        assert np.array_equal(y, x)

    def test_composes_gain_delete_and_insert(self):
        sr = 1000
        x = np.ones(1000, dtype=np.float32)
        edits = [
            {"type": "gain", "start_ms": 0, "end_ms": 200, "gain_db": -6.0, "fade_in_ms": 0, "fade_out_ms": 0},
            {"type": "delete", "start_ms": 800, "end_ms": 1000},
            {"type": "insert_silence", "at_ms": 400, "duration_ms": 50},
        ]
        y = apply_region_edits(x, sr, edits)
        # 1000 - 200 (deleted) + 50 (inserted) = 850
        assert y.size == 850
        expected_gain = 10.0 ** (-6.0 / 20.0)
        assert abs(y[100] - expected_gain) < 1e-6

    def test_multiple_deletes_apply_longest_offset_first(self):
        sr = 1000
        x = np.arange(1000, dtype=np.float32)
        edits = [
            {"type": "delete", "start_ms": 100, "end_ms": 200},
            {"type": "delete", "start_ms": 500, "end_ms": 600},
        ]
        y = apply_region_edits(x, sr, edits)
        assert y.size == 800
        assert y[99] == 99
        assert y[100] == 200

    def test_multiple_inserts_apply_in_ascending_order_with_running_offset(self):
        sr = 1000
        x = np.ones(1000, dtype=np.float32)
        edits = [
            {"type": "insert_silence", "at_ms": 100, "duration_ms": 50},
            {"type": "insert_silence", "at_ms": 200, "duration_ms": 50},
        ]
        y = apply_region_edits(x, sr, edits)
        assert y.size == 1100
        # second insert's at_ms=200 lands at sample 250 because the first insert
        # (50 samples at position 100) shifts everything after it by a running offset
        assert np.allclose(y[100:150], 0.0)
        assert np.allclose(y[150:250], 1.0)
        assert np.allclose(y[250:300], 0.0)
