"""test_api_async_lifecycle.py — async job lifecycle via HTTP.

Tier 3: black-box HTTP tests against fake_model_server.
"""

from __future__ import annotations

import time

import httpx

TEST_TEXT = "This is an async test prompt."


def _wait_until(base_url: str, condition, *, timeout: float = 3.0, interval: float = 0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return False


def test_create_progress_completed_audio(base_url: str):
    # 1. Create async job.
    r = httpx.post(
        f"{base_url}/generate/async",
        json={"text": TEST_TEXT},
        timeout=5,
    )
    assert r.status_code == 200
    job_id = r.json()["job_id"]

    # 2. Check initial status is running or completed.
    r = httpx.get(f"{base_url}/generate/progress", params={"job_id": job_id}, timeout=3)
    assert r.status_code == 200
    prog = r.json()
    assert prog["job_id"] == job_id
    assert prog["status"] in ("running", "completed")

    # 3. Wait until completed.
    def is_completed():
        r2 = httpx.get(
            f"{base_url}/generate/progress",
            params={"job_id": job_id},
            timeout=2,
        )
        if r2.status_code != 200:
            return False
        return r2.json().get("status") == "completed"

    assert _wait_until(base_url, is_completed, timeout=2.0)

    # 4. Confirm audio_available is true.
    r = httpx.get(
        f"{base_url}/generate/progress",
        params={"job_id": job_id},
        timeout=2,
    )
    assert r.json().get("audio_available") is True

    # 5. Fetch audio.
    r = httpx.get(
        f"{base_url}/generate/job/{job_id}/audio",
        timeout=5,
    )
    assert r.status_code == 200
    ct = (r.headers.get("content-type") or "").lower()
    assert "audio" in ct


def test_cancel_before_completion(base_url: str):
    r = httpx.post(
        f"{base_url}/generate/async",
        json={"text": TEST_TEXT},
        timeout=5,
    )
    assert r.status_code == 200
    job_id = r.json()["job_id"]

    # Attempt cancel; if job is already completed, cancel fails with 404 which is OK
    # because fake_model_server completes quickly. We just validate the cancel contract.
    r = httpx.post(
        f"{base_url}/generate/cancel",
        params={"job_id": job_id},
        timeout=3,
    )
    # Either cancelled (200) or not-running (404) — both valid for the fake.
    assert r.status_code in (200, 404)


def test_unknown_job_404(base_url: str):
    # Progress for non-existent job.
    r = httpx.get(
        f"{base_url}/generate/progress",
        params={"job_id": "nonexistent-id"},
        timeout=2,
    )
    assert r.status_code == 404

    # Audio for non-existent job.
    r = httpx.get(
        f"{base_url}/generate/job/nonexistent-id/audio",
        timeout=2,
    )
    assert r.status_code == 404

    # Cancel for non-existent job.
    r = httpx.post(
        f"{base_url}/generate/cancel",
        params={"job_id": "nonexistent-id"},
        timeout=2,
    )
    assert r.status_code == 404
