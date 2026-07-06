"""test_api_smoke.py — basic smoke tests against live HTTP endpoints.

Tier 3: black-box, no internal mocking. Runs against fake_model_server.
"""

from __future__ import annotations

import httpx

TEST_TEXT = "Hello world."


def test_health(base_url: str):
    r = httpx.get(f"{base_url}/health", timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ("ok", "degraded")
    assert "backend" in data


def test_root_returns_html(base_url: str):
    """GET / must respond with HTML (200 if frontend built, 404 otherwise)."""
    r = httpx.get(base_url, timeout=5)
    assert r.status_code in (200, 404)
    ct = (r.headers.get("content-type") or "").lower()
    assert "text/html" in ct


def test_generate_minimal(base_url: str):
    r = httpx.post(
        f"{base_url}/generate",
        json={"text": TEST_TEXT},
        timeout=10,
    )
    assert r.status_code == 200
    # Verify it is audio, not JSON.
    ct = (r.headers.get("content-type") or "").lower()
    assert "audio" in ct
    assert len(r.content) > 100


def test_generate_explicit_format(base_url: str):
    for fmt in ("mp3", "wav"):
        r = httpx.post(
            f"{base_url}/generate",
            json={"text": TEST_TEXT, "response_format": fmt},
            timeout=10,
        )
        assert r.status_code == 200
        ct = (r.headers.get("content-type") or "").lower()
        assert "audio" in ct


def test_generate_missing_text(base_url: str):
    r = httpx.post(
        f"{base_url}/generate",
        json={"language": "English"},
        timeout=5,
    )
    assert r.status_code == 400
    assert "text is required" in r.json().get("error", "")


def test_openai_speech_minimal(base_url: str):
    r = httpx.post(
        f"{base_url}/v1/audio/speech",
        json={"input": TEST_TEXT},
        timeout=10,
    )
    assert r.status_code == 200
    ct = (r.headers.get("content-type") or "").lower()
    assert "audio" in ct
    assert len(r.content) > 100
