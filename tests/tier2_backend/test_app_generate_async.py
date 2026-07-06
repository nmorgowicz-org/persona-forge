"""Test async generation lifecycle."""

import pytest


@pytest.mark.integration
class TestGenerateAsync:

    def test_create_then_completed_then_audio(self, client, rt):
        # With async_jobs_complete_immediately=True (default), jobs finish instantly.
        resp = client.post(
            "/generate/async",
            json={"text": "hello"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        job_id = body["job_id"]
        assert job_id

        prog = rt.wait_for_job_completion(job_id)
        assert prog["status"] == "completed"

        audio = client.get(f"/generate/job/{job_id}/audio")
        assert audio.status_code == 200
        assert "audio" in audio.content_type

    def test_cancel_running_job(self, client, rt):
        # Temporarily disable immediate completion so the job stays "running".
        orig = rt.async_jobs_complete_immediately
        rt.async_jobs_complete_immediately = False

        try:
            resp = client.post(
                "/generate/async",
                json={"text": "a very long text here"},
            )
            assert resp.status_code == 200
            job_id = resp.get_json()["job_id"]

            # Job should be in "running" state.
            job = rt._active_jobs.get(job_id)
            assert job is not None
            assert job.status == "running"

            cancel = client.post(f"/generate/cancel?job_id={job_id}")
            assert cancel.status_code == 200
            assert cancel.get_json()["cancelled"] is True

            job = rt._active_jobs.get(job_id)
            assert job.status == "cancelled"
        finally:
            rt.async_jobs_complete_immediately = orig

    def test_unknown_job_404_progress(self, client):
        resp = client.get("/generate/progress?job_id=nope")
        assert resp.status_code == 404

    def test_unknown_job_404_cancel(self, client):
        resp = client.post("/generate/cancel?job_id=nope")
        assert resp.status_code == 404

    def test_unknown_job_404_audio(self, client):
        resp = client.get("/generate/job/nope/audio")
        assert resp.status_code == 404
