"""Test /runtime/config GET and POST."""

import pytest


@pytest.mark.integration
class TestRuntimeConfigGet:

    def test_get_known_keys(self, client):
        resp = client.get("/runtime/config")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "live" in data
        live = data["live"]
        assert "TTS_BACKEND" in live
        assert "IDLE_UNLOAD_SECONDS" in live

    def test_pocket_tts_cloning_capability_does_not_require_default_voice(
        self, client, rt
    ):
        orig_backend = rt.tts_backend
        orig_live_backend = rt.live_config["TTS_BACKEND"]
        orig_provenance = rt.pocket_provenance
        orig_default_state = rt.pocket_default_voice_state
        rt.tts_backend = "pocket_tts"
        rt.live_config["TTS_BACKEND"] = "pocket_tts"
        rt.pocket_provenance = {
            "cloning_available": True,
            "cloning_status": "ready",
            "message": "",
        }
        rt.pocket_default_voice_state = None
        try:
            resp = client.get("/runtime/config")
            assert resp.status_code == 200
            live = resp.get_json()["live"]
            assert live["pocket_tts_voice_cloning_available"] is True
            assert live["pocket_tts_voice_cloning_message"] == ""
        finally:
            rt.tts_backend = orig_backend
            rt.live_config["TTS_BACKEND"] = orig_live_backend
            rt.pocket_provenance = orig_provenance
            rt.pocket_default_voice_state = orig_default_state

    def test_get_not_live_section(self, client):
        resp = client.get("/runtime/config")
        data = resp.get_json()
        assert "not_live" in data
        assert "reconfig_in_progress" in data


@pytest.mark.integration
class TestRuntimeConfigPost:

    def test_post_apply_idle_unload(self, client, rt):
        resp = client.post(
            "/runtime/config",
            json={"IDLE_UNLOAD_SECONDS": 60},
        )
        assert resp.status_code == 200
        assert rt.live_config["IDLE_UNLOAD_SECONDS"] == 60

    def test_post_apply_backend(self, client, rt):
        resp = client.post(
            "/runtime/config",
            json={"TTS_BACKEND": "pytorch"},
        )
        assert resp.status_code == 200
        assert rt.live_config["TTS_BACKEND"] == "pytorch"

    def test_reject_unknown_key(self, client):
        resp = client.post(
            "/runtime/config",
            json={"NOT_A_KEY": 1},
        )
        assert resp.status_code == 400
