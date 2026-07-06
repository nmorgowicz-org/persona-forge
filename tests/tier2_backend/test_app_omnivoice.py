"""Test OmniVoice audition, stitch, save, segments."""

import shutil
import tempfile
from pathlib import Path

import numpy as np
import pytest
from unittest.mock import patch


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
class TestOmniVoiceStitch:

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
