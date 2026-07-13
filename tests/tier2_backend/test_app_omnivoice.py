"""Test OmniVoice audition, stitch, save, segments."""

import shutil
import tempfile
import io
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from unittest.mock import patch

from qwen3_tts.forced_alignment import Boundary


def _seed_audition_candidates(client, app_module):
    """Helper: run audition and return job_id."""
    # Ensure swap_in_progress is False before running.
    app_module.omnivoice_engine._swap_in_progress = False

    def fake_run_omnivoice_job(segments, instruct, language, candidates_per_segment, seed,
                               **kw):
        on_candidate_complete = kw.get("on_candidate_complete")
        for seg_idx, text in enumerate(segments):
            for cand_idx in range(candidates_per_segment):
                wav = np.zeros(240, dtype=np.float32)
                candidate = (wav, 24000, False, "ok", "", None)
                if on_candidate_complete is not None:
                    on_candidate_complete(seg_idx, cand_idx, text, candidate)

    with patch.object(
        app_module.omnivoice_engine, "run_omnivoice_job", fake_run_omnivoice_job
    ):
        aud = client.post(
            "/omnivoice/audition",
            json={
                "segments": ["hello"],
                "instruct": "female, young adult",
            },
        )

    job_id = aud.get_json()["job_id"]
    assert aud.status_code == 200
    return job_id


@pytest.mark.integration
class TestOmniVoiceAudition:

    def test_audition_basic(self, client, app_module):
        job_id = _seed_audition_candidates(client, app_module)
        assert job_id

    def test_audition_requires_segments(self, client):
        resp = client.post(
            "/omnivoice/audition",
            json={"instruct": "female"},
        )
        assert resp.status_code == 400

    def test_audition_requires_instruct(self, client):
        resp = client.post(
            "/omnivoice/audition",
            json={"segments": ["hello"]},
        )
        assert resp.status_code == 400

    def test_audition_503_swap_in_progress(self, client, app_module):
        orig = app_module.omnivoice_engine._swap_in_progress
        app_module.omnivoice_engine._swap_in_progress = True
        try:
            resp = client.post(
                "/omnivoice/audition",
                json={"segments": ["hello"], "instruct": "female"},
            )
            assert resp.status_code == 503
        finally:
            app_module.omnivoice_engine._swap_in_progress = orig


@pytest.mark.integration
def test_alignment_performance_endpoint_exposes_budget(client):
    response = client.get("/alignment/performance")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["budget_seconds"] > 0
    assert payload["sample_count"] >= 0
    assert isinstance(payload["within_budget"], bool)


@pytest.mark.integration
class TestOmniVoiceStitch:

    def test_pacing_targets_uses_shared_storyteller_targets(self, client):
        resp = client.post(
            "/omnivoice/stitch/pacing-targets",
            json={
                "transcripts": ["First.", "Wait…", "Last."],
                "style_preset": "Storyteller",
            },
        )
        assert resp.status_code == 200
        assert resp.get_json()["padding_ms"] == [1000.0, 1500.0]

    def test_pacing_targets_rejects_bad_transcripts(self, client):
        resp = client.post(
            "/omnivoice/stitch/pacing-targets", json={"transcripts": "not-a-list"}
        )
        assert resp.status_code == 400

    def test_stitch_plan_repairs_each_enabled_segment_before_join(self, app_module):
        candidate_id = "phase4-candidate"
        source = np.ones(240, dtype=np.float32) * 0.1
        repaired = np.concatenate([source[:120], np.zeros(120, dtype=np.float32), source[120:]])
        app_module._omnivoice_candidates[candidate_id] = (source, 24000)
        try:
            with patch.object(
                app_module.prosody_repair,
                "repair_segment_audio",
                return_value=(repaired, [{"insert_ms": 5.0}], {"resolved_mode": "precise"}),
            ) as repair:
                resolved = app_module._resolve_stitch_plan(
                    {
                        "clips": [
                            {
                                "candidate_id": candidate_id,
                                "text": "First. Second.",
                                "prosody_mode": "auto",
                            }
                        ],
                        "style_preset": "Storyteller",
                    }
                )
            assert resolved is not None
            selected, _kwargs = resolved
            np.testing.assert_array_equal(selected[0][0], repaired)
            repair.assert_called_once()
            assert repair.call_args.kwargs["mode"] == "auto"
            assert repair.call_args.kwargs["style_preset"] == "Storyteller"
        finally:
            app_module._omnivoice_candidates.pop(candidate_id, None)

    def test_blended_segment_is_repaired_in_stitched_audio(self, client, app_module):
        candidate_id = "phase4-gate"
        sr = 24000
        time_axis = np.arange(sr * 2, dtype=np.float32) / sr
        source = (0.2 * np.sin(2 * np.pi * 110 * time_axis)).astype(np.float32)
        app_module._omnivoice_candidates[candidate_id] = (source, sr)
        boundaries = [
            Boundary("first", 0.1, 0.8, 0.99, "sentence_split"),
            Boundary("second", 0.8, 1.8, 0.99, "word"),
        ]
        try:
            with patch.object(
                app_module.prosody_repair.forced_alignment,
                "align",
                return_value=boundaries,
            ):
                response = client.post(
                    "/omnivoice/stitch",
                    json={
                        "stitch_plan": {
                            "clips": [
                                {
                                    "candidate_id": candidate_id,
                                    "text": "First. Second.",
                                    "prosody_mode": "precise",
                                }
                            ],
                            "style_preset": "Storyteller",
                        }
                    },
                )
            assert response.status_code == 200
            stitched, stitched_sr = sf.read(io.BytesIO(response.data), dtype="float32")
            assert stitched_sr == sr
            assert stitched.size == source.size + sr  # Storyteller sentence target = 1 s.
        finally:
            app_module._omnivoice_candidates.pop(candidate_id, None)

    def test_stitch_rejects_empty_selections(self, client):
        resp = client.post("/omnivoice/stitch", json={})
        assert resp.status_code == 400

    def test_stitch_rejects_unknown_candidate(self, client):
        resp = client.post(
            "/omnivoice/stitch",
            json={"selections": ["nope"]},
        )
        assert resp.status_code == 400


@pytest.mark.integration
class TestOmniVoiceSave:

    def test_save_requires_instruct(self, client):
        resp = client.post(
            "/omnivoice/save",
            json={"selections": ["x"], "segments": ["hello"]},
        )
        assert resp.status_code == 400

    def test_save_requires_segments(self, client):
        resp = client.post(
            "/omnivoice/save",
            json={"selections": ["x"], "instruct": "female"},
        )
        assert resp.status_code == 400


@pytest.mark.integration
class TestOmniVoiceSegments:

    def test_segments_crud(self, client, app_module):
        tmpdir = tempfile.mkdtemp()
        try:
            with patch.object(
                app_module.segment_library, "SEGMENT_LIBRARY_DIR", Path(tmpdir)
            ):
                # First audition to seed candidates.
                job_id = _seed_audition_candidates(client, app_module)

                # Clear swap_in_progress so second audition doesn't 503.
                app_module.omnivoice_engine._swap_in_progress = False

                with patch.object(
                    app_module.omnivoice_engine, "run_omnivoice_job",
                    lambda *a, **k: None
                ):
                    aud = client.post(
                        "/omnivoice/audition",
                        json={
                            "segments": ["G'day"],
                            "instruct": "female, young adult",
                        },
                    )
                assert aud.status_code == 200

                resp = client.get("/omnivoice/segments")
                assert resp.status_code == 200
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
