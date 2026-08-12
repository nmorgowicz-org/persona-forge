"""Test audio_diagnostics.diagnose_take heuristics."""

from __future__ import annotations

from persona_forge.audio_diagnostics import diagnose_take


class TestDiagnoseTake:
    def test_no_signal_returns_empty(self):
        assert diagnose_take({}) == []
        assert diagnose_take({"error": "analysis failed: boom"}) == []

    def test_clean_take_has_no_diagnoses(self):
        metrics = {
            "peak_dbfs": -6.0,
            "duration_seconds": 3.0,
            "triage": {"speech_rate_cv": 0.4},
        }
        assert diagnose_take(metrics, guidance_scale=2.5) == []

    def test_clipping_detected_from_true_peak(self):
        metrics = {"true_peak_dbfs": -0.2, "peak_dbfs": -3.0, "duration_seconds": 1.0}
        diagnoses = diagnose_take(metrics)
        assert len(diagnoses) == 1
        assert diagnoses[0].id == "clipping"
        assert diagnoses[0].kb_entry_id == "clipping"
        assert diagnoses[0].severity == "warning"

    def test_flat_cadence_detected_when_long_enough_and_low_variance(self):
        metrics = {
            "peak_dbfs": -6.0,
            "duration_seconds": 2.0,
            "triage": {"speech_rate_cv": 0.05},
        }
        diagnoses = diagnose_take(metrics)
        assert [d.id for d in diagnoses] == ["robotic-cadence"]

    def test_flat_cadence_suppressed_for_short_takes(self):
        metrics = {
            "peak_dbfs": -6.0,
            "duration_seconds": 0.5,
            "triage": {"speech_rate_cv": 0.05},
        }
        assert diagnose_take(metrics) == []

    def test_accent_drift_requires_long_take_and_low_guidance(self):
        metrics = {"peak_dbfs": -6.0, "duration_seconds": 7.0}
        assert diagnose_take(metrics, guidance_scale=1.5)[0].id == "accent-drift"
        assert diagnose_take(metrics, guidance_scale=2.0) == []
        assert diagnose_take(metrics, guidance_scale=None) == []

    def test_multiple_diagnoses_can_coexist(self):
        metrics = {
            "true_peak_dbfs": -0.1,
            "duration_seconds": 8.0,
            "triage": {"speech_rate_cv": 0.02},
        }
        diagnoses = diagnose_take(metrics, guidance_scale=1.0)
        ids = {d.id for d in diagnoses}
        assert ids == {"clipping", "robotic-cadence", "accent-drift"}

    def test_to_dict_includes_all_fields(self):
        metrics = {"true_peak_dbfs": -0.1, "duration_seconds": 1.0}
        [diagnosis] = diagnose_take(metrics)
        assert diagnosis.to_dict() == {
            "id": "clipping",
            "severity": "warning",
            "message": diagnosis.message,
            "kb_entry_id": "clipping",
        }
