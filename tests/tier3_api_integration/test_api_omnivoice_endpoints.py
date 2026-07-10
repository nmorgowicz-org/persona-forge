"""test_api_omnivoice_endpoints.py — OmniVoice flow and segments CRUD via HTTP.

Tier 3: black-box HTTP tests against fake_model_server.
"""

from __future__ import annotations

import time

import httpx

TEST_SEGMENTS = ["G'day mate.", "How's it going?"]
TEST_INSTRUCT = "female, young adult, moderate pitch"


def _wait_audition_completed(base_url: str, job_id: str, timeout: float = 3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = httpx.get(
            f"{base_url}/omnivoice/audition/progress",
            params={"job_id": job_id},
            timeout=2,
        )
        if r.status_code == 200:
            status = r.json().get("status")
            if status == "completed":
                return r.json()
        time.sleep(0.05)
    # Fallback: return last seen response
    return r.json() if r.status_code == 200 else None


def test_omnivoice_audition_returns_job_id(base_url: str):
    r = httpx.post(
        f"{base_url}/omnivoice/audition",
        json={
            "segments": TEST_SEGMENTS,
            "instruct": TEST_INSTRUCT,
        },
        timeout=5,
    )
    assert r.status_code == 200
    data = r.json()
    assert "job_id" in data
    assert data["total_segments"] == len(TEST_SEGMENTS)


def test_omnivoice_audition_progress(base_url: str):
    # Start job.
    r = httpx.post(
        f"{base_url}/omnivoice/audition",
        json={
            "segments": TEST_SEGMENTS,
            "instruct": TEST_INSTRUCT,
        },
        timeout=5,
    )
    job_id = r.json()["job_id"]

    # Poll progress until completed.
    prog = _wait_audition_completed(base_url, job_id)
    assert prog is not None, "Timed out waiting for audition to complete"
    assert prog["status"] == "completed"
    assert prog["total_segments"] == 2
    assert len(prog["segments_completed"]) == 2


def test_omnivoice_audition_missing_segments(base_url: str):
    r = httpx.post(
        f"{base_url}/omnivoice/audition",
        json={"instruct": TEST_INSTRUCT},
        timeout=3,
    )
    assert r.status_code == 400


def test_omnivoice_audition_missing_instruct(base_url: str):
    r = httpx.post(
        f"{base_url}/omnivoice/audition",
        json={"segments": TEST_SEGMENTS},
        timeout=3,
    )
    assert r.status_code == 400


def test_omnivoice_select_candidates_then_stitch(base_url: str):
    # Start audition job.
    r = httpx.post(
        f"{base_url}/omnivoice/audition",
        json={
            "segments": TEST_SEGMENTS,
            "instruct": TEST_INSTRUCT,
        },
        timeout=5,
    )
    job_id = r.json()["job_id"]

    # Wait for completion and collect candidate IDs.
    prog = _wait_audition_completed(base_url, job_id)
    assert prog["status"] == "completed"
    candidate_ids = []
    for seg in prog["segments_completed"]:
        for c in seg["candidates"]:
            candidate_ids.append(c["candidate_id"])

    assert len(candidate_ids) >= 1

    # Stitch with selected candidates.
    r = httpx.post(
        f"{base_url}/omnivoice/stitch",
        json={"selections": candidate_ids},
        timeout=5,
    )
    assert r.status_code == 200
    ct = (r.headers.get("content-type") or "").lower()
    assert "audio" in ct


def test_omnivoice_save(base_url: str):
    # Start audition job.
    r = httpx.post(
        f"{base_url}/omnivoice/audition",
        json={
            "segments": TEST_SEGMENTS,
            "instruct": TEST_INSTRUCT,
        },
        timeout=5,
    )
    job_id = r.json()["job_id"]
    prog = _wait_audition_completed(base_url, job_id)
    assert prog["status"] == "completed"

    # Pick first candidate from first segment.
    cand_id = prog["segments_completed"][0]["candidates"][0]["candidate_id"]

    r = httpx.post(
        f"{base_url}/omnivoice/save",
        json={
            "selections": [cand_id],
            "instruct": TEST_INSTRUCT,
            "segments": TEST_SEGMENTS[:1],
        },
        timeout=30,
    )
    assert r.status_code == 200
    data = r.json()
    assert "voice_id" in data
    assert "audio_base64" in data


def test_omnivoice_save_missing_instruct(base_url: str):
    r = httpx.post(
        f"{base_url}/omnivoice/save",
        json={"selections": ["any"], "segments": TEST_SEGMENTS[:1]},
        timeout=3,
    )
    assert r.status_code == 400


def test_omnivoice_segments_crud(base_url: str):
    # 1. Create segment from audition candidate.
    r = httpx.post(
        f"{base_url}/omnivoice/audition",
        json={
            "segments": ["Hello there."],
            "instruct": TEST_INSTRUCT,
        },
        timeout=5,
    )
    job_id = r.json()["job_id"]
    prog = _wait_audition_completed(base_url, job_id)
    cand_id = prog["segments_completed"][0]["candidates"][0]["candidate_id"]

    # Create segment.
    r = httpx.post(
        f"{base_url}/omnivoice/segments",
        json={
            "candidate_id": cand_id,
            "text": "Hello there.",
            "instruct": TEST_INSTRUCT,
        },
        timeout=5,
    )
    assert r.status_code == 200
    seg = r.json()
    segment_id = seg["segment_id"]
    assert "audio_base64" in seg

    # List segments includes it.
    r = httpx.get(f"{base_url}/omnivoice/segments", timeout=3)
    assert r.status_code == 200
    seg_list = [s["segment_id"] for s in r.json()["segments"]]
    assert segment_id in seg_list

    # Get segment audio.
    r = httpx.get(f"{base_url}/omnivoice/segments/{segment_id}/audio", timeout=3)
    assert r.status_code == 200
    assert "audio" in (r.headers.get("content-type") or "").lower()

    # Delete segment.
    r = httpx.delete(f"{base_url}/omnivoice/segments/{segment_id}", timeout=3)
    assert r.status_code == 200
    assert r.json().get("deleted") is True

    # Delete again -> 404.
    r = httpx.delete(f"{base_url}/omnivoice/segments/{segment_id}", timeout=3)
    assert r.status_code == 404


def test_omnivoice_segments_unknown_candidate(base_url: str):
    r = httpx.post(
        f"{base_url}/omnivoice/segments",
        json={
            "candidate_id": "not-a-real-id",
            "text": "Hello there.",
            "instruct": TEST_INSTRUCT,
        },
        timeout=3,
    )
    assert r.status_code == 400


def test_omnivoice_stitch_unknown_selections(base_url: str):
    r = httpx.post(
        f"{base_url}/omnivoice/stitch",
        json={"selections": ["not-a-real-id"]},
        timeout=3,
    )
    assert r.status_code == 400
