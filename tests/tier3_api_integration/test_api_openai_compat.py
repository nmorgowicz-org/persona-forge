"""test_api_openai_compat.py — OpenAI-compatible endpoint validation.

Tier 3: black-box HTTP tests against fake_model_server.
"""

from __future__ import annotations

import httpx

TEST_INPUT = "Hello from the OpenAI-compatible endpoint."


def test_openai_speech_minimal_request(base_url: str):
    r = httpx.post(
        f"{base_url}/v1/audio/speech",
        json={"input": TEST_INPUT},
        timeout=10,
    )
    assert r.status_code == 200
    ct = (r.headers.get("content-type") or "").lower()
    assert "audio" in ct
    assert len(r.content) > 100


def test_openai_speech_accepts_ignored_fields(base_url: str):
    """OpenAI clients often send extra fields; they must not cause a 400."""
    r = httpx.post(
        f"{base_url}/v1/audio/speech",
        json={
            "model": "tts-1",
            "voice": "alloy",
            "input": TEST_INPUT,
            "speed": 1.0,
        },
        timeout=10,
    )
    assert r.status_code == 200
    assert "audio" in (r.headers.get("content-type") or "").lower()


def test_openai_speech_missing_input(base_url: str):
    r = httpx.post(
        f"{base_url}/v1/audio/speech",
        json={"model": "tts-1"},
        timeout=5,
    )
    assert r.status_code == 400
    err = r.json()["error"]
    assert "input" in err.get("message", "").lower()


def test_openai_speech_format_mp3(base_url: str):
    r = httpx.post(
        f"{base_url}/v1/audio/speech",
        json={"input": TEST_INPUT, "response_format": "mp3"},
        timeout=10,
    )
    assert r.status_code == 200
    assert "audio/mpeg" in (r.headers.get("content-type") or "").lower()


def test_openai_speech_format_wav(base_url: str):
    r = httpx.post(
        f"{base_url}/v1/audio/speech",
        json={"input": TEST_INPUT, "response_format": "wav"},
        timeout=10,
    )
    assert r.status_code == 200
    assert "audio/wav" in (r.headers.get("content-type") or "").lower()


def test_openai_speech_includes_seed_header(base_url: str):
    r = httpx.post(
        f"{base_url}/v1/audio/speech",
        json={"input": TEST_INPUT},
        timeout=10,
    )
    assert r.status_code == 200
    assert r.headers.get("x-seed") is not None, "Response must include X-Seed header"
