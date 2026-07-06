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
