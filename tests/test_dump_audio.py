import unittest

from dump_audio import _RssSampler


class RssSamplerTests(unittest.TestCase):
    def test_reports_generation_and_phase_peaks(self):
        values = iter((100.0, 120.0, 180.0, 160.0, 150.0))
        sampler = _RssSampler(60_000, rss_reader=lambda: next(values, 150.0))

        with sampler:
            sampler.snapshot()
            with sampler.phase("vocoder"):
                sampler.snapshot()

        report = sampler.report()
        self.assertEqual(report["generation_peak_rss_mib"], 180.0)
        self.assertEqual(report["phase_peak_rss_mib"]["generation_glue"], 150.0)
        self.assertEqual(report["phase_peak_rss_mib"]["vocoder"], 180.0)

    def test_rejects_non_positive_interval(self):
        with self.assertRaisesRegex(ValueError, "must be positive"):
            _RssSampler(0)


if __name__ == "__main__":
    unittest.main()
