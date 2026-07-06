"""Test /voices CRUD at HTTP layer."""

import pytest
from unittest.mock import patch


@pytest.mark.integration
class TestVoices:

    def test_list_voices(self, client, app_module):
        with patch.object(
            app_module.voice_library,
            "list_voices",
            return_value=[{"voice_id": "vd_aabbccddeeff"}],
        ):
            resp = client.get("/voices")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["voices"]) == 1
        assert data["voices"][0]["voice_id"] == "vd_aabbccddeeff"

    def test_get_voice_found(self, client, app_module):
        with patch.object(
            app_module.voice_library,
            "get_voice",
            return_value={"voice_id": "vd_aabbccddeeff"},
        ), patch.object(
            app_module.voice_library,
            "get_voice_wav_bytes",
            return_value=b"wavdata",
        ):
            resp = client.get("/voices/vd_aabbccddeeff")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["voice_id"] == "vd_aabbccddeeff"
        assert "audio_base64" in body
        assert "wav_path" not in body

    def test_get_voice_not_found(self, client, app_module):
        with patch.object(app_module.voice_library, "get_voice", return_value=None):
            resp = client.get("/voices/vd_doesnotexist")
        assert resp.status_code == 404

    def test_delete_voice_ok(self, client, app_module):
        with patch.object(
            app_module.voice_library, "delete_voice", return_value=True
        ):
            resp = client.delete("/voices/vd_aabbccddeeff")
        assert resp.status_code == 200
        assert resp.get_json()["deleted"] == "vd_aabbccddeeff"

    def test_delete_voice_not_found(self, client, app_module):
        with patch.object(
            app_module.voice_library, "delete_voice", return_value=False
        ):
            resp = client.delete("/voices/vd_doesnotexist")
        assert resp.status_code == 404

    def test_update_voice_sample_text(self, client, app_module):
        with patch.object(
            app_module.voice_library,
            "update_voice",
            return_value={"voice_id": "vd_aabbccddeeff", "sample_text": "new text"},
        ):
            resp = client.patch(
                "/voices/vd_aabbccddeeff",
                json={"sample_text": "new text"},
            )
        assert resp.status_code == 200

    def test_update_voice_requires_sample_text(self, client):
        resp = client.patch("/voices/vd_aabbccddeeff", json={})
        assert resp.status_code == 400

    def test_path_traversal_rejected(self, client, app_module):
        with patch.object(app_module.voice_library, "get_voice", return_value=None):
            resp = client.get("/voices/../../etc/passwd")
        assert resp.status_code in (404, 400, 405)
