"""Test _RssSampler correctness for benchmark tooling (no heavy deps)."""

from __future__ import annotations

import pytest

from dump_audio import _RssSampler


class TestRssSampler:
    def test_reports_generation_and_phase_peaks(self):
        values = iter((100.0, 120.0, 180.0, 160.0, 150.0))
        sampler = _RssSampler(60_000, rss_reader=lambda: next(values, 150.0))

        with sampler:
            sampler.snapshot()
            with sampler.phase("vocoder"):
                sampler.snapshot()

        report = sampler.report()
        assert report["generation_peak_rss_mib"] == 180.0
        assert report["phase_peak_rss_mib"]["generation_glue"] == 150.0
        assert report["phase_peak_rss_mib"]["vocoder"] == 180.0

    def test_maxrss_delta_catches_transient_the_sampler_misses(self):
        maxrss_values = iter((1000.0, 3500.0, 3500.0))
        sampler = _RssSampler(
            60_000,
            rss_reader=lambda: 100.0,
            maxrss_reader=lambda: next(maxrss_values, 3500.0),
        )

        with sampler:
            with sampler.phase("vocoder"):
                sampler.snapshot()

        report = sampler.report()
        assert report["phase_peak_rss_mib"]["vocoder"] == 100.0
        assert report["phase_maxrss_delta_mib"]["vocoder"] == 2500.0
        assert report["lifetime_maxrss_mib"] == 3500.0

    def test_rejects_non_positive_interval(self):
        with pytest.raises(ValueError, match="must be positive"):
            _RssSampler(0)
