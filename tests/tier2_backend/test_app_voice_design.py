"""Test /voice_design endpoints."""

import numpy as np
import pytest
from unittest.mock import patch


@pytest.mark.integration
class TestVoiceDesignCreate:

    def test_happy_path(self, client, app_module):
        def fake_vd(description, sample_text, language, seed):
            return np.zeros(240, dtype=np.float32), 24000, seed or 123

        with patch.object(
            app_module.voice_design, "run_voice_design_request", fake_vd
        ):
            resp = client.post(
                "/voice_design",
                json={
                    "description": "calm narrator",
                    "sample_text": "hello there",
                },
            )

        assert resp.status_code == 200
        body = resp.get_json()
        assert "preview_id" in body
        assert len(body["preview_id"]) > 8
        assert "audio_base64" in body

    def test_requires_description(self, client):
        resp = client.post(
            "/voice_design",
            json={"sample_text": "hello"},
        )
        assert resp.status_code == 400

    def test_requires_sample_text(self, client):
        resp = client.post(
            "/voice_design",
            json={"description": "x"},
        )
        assert resp.status_code == 400

    def test_rejects_non_integer_seed(self, client):
        resp = client.post(
            "/voice_design",
            json={
                "description": "x",
                "sample_text": "hello",
                "seed": "abc",
            },
        )
        assert resp.status_code == 400

    def test_rejects_too_long_sample_text(self, client):
        long_text = " ".join(["word"] * 100)
        resp = client.post(
            "/voice_design",
            json={"description": "x", "sample_text": long_text},
        )
        assert resp.status_code == 400

    def test_503_when_swap_in_progress(self, client, app_module):
        orig = app_module.voice_design._swap_in_progress
        app_module.voice_design._swap_in_progress = True
        try:
            resp = client.post(
                "/voice_design",
                json={"description": "x", "sample_text": "hello"},
            )
            assert resp.status_code == 503
        finally:
            app_module.voice_design._swap_in_progress = orig


@pytest.mark.integration
class TestVoiceDesignSave:

    def test_save_preview(self, client, app_module):
        def fake_vd(desc, sample, lang, seed):
            return np.zeros(240, dtype=np.float32), 24000, 42

        with patch.object(
            app_module.voice_design, "run_voice_design_request", fake_vd
        ):
            vd = client.post(
                "/voice_design",
                json={"description": "x", "sample_text": "hello"},
            )
        preview_id = vd.get_json()["preview_id"]

        saved = {}

        def fake_save(wav_bytes, **kw):
            saved.update(kw)
            return {"voice_id": "vd_aabbccddeeff"}

        with patch.object(app_module.voice_library, "save_voice", fake_save):
            resp = client.post(f"/voice_design/preview/{preview_id}/save")

        assert resp.status_code == 200
        assert resp.get_json()["voice_id"] == "vd_aabbccddeeff"

    def test_save_unknown_preview(self, client):
        resp = client.post("/voice_design/preview/nope/save")
        assert resp.status_code in (400, 404)


@pytest.mark.integration
class TestVoiceDesignProgress:

    def test_progress_returns_json(self, client, app_module):
        with patch.object(
            app_module.voice_design,
            "get_progress",
            return_value={"phase": "idle"},
        ):
            resp = client.get("/voice_design/progress")
        assert resp.status_code == 200
        assert "phase" in resp.get_json()
