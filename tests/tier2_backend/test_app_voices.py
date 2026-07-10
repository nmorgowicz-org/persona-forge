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

    def test_list_built_in_pocket_voices(self, client):
        resp = client.get("/voices/built-in")
        assert resp.status_code == 200
        data = resp.get_json()
        voices = data["voices"]
        assert len(voices) == 30
        vera = next(v for v in voices if v["voice_id"] == "pocket:vera")
        assert vera["builtin_voice"] == "vera"
        assert vera["backend"] == "pocket_tts"
        assert vera["language"] == "English"
        assert vera["language_code"] == "en"
        assert vera["category"] == "conversation"
        estelle = next(v for v in voices if v["voice_id"] == "pocket:estelle")
        assert estelle["language"] == "French"
        assert estelle["category"] == "multilingual"

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

    def test_normalize_voice_ok(self, client, app_module):
        with patch.object(
            app_module.voice_library,
            "normalize_reference",
            return_value={"voice_id": "vd_aabbccddeeff"},
        ):
            resp = client.post("/voices/vd_aabbccddeeff/normalize")
        assert resp.status_code == 200
        assert resp.get_json()["voice_id"] == "vd_aabbccddeeff"

    def test_normalize_voice_not_found(self, client, app_module):
        with patch.object(app_module.voice_library, "normalize_reference", return_value=None):
            resp = client.post("/voices/vd_doesnotexist/normalize")
        assert resp.status_code == 404

    def test_trim_silence_voice_ok(self, client, app_module):
        with patch.object(
            app_module.voice_library,
            "trim_reference_silence",
            return_value={"voice_id": "vd_aabbccddeeff"},
        ):
            resp = client.post("/voices/vd_aabbccddeeff/trim-silence")
        assert resp.status_code == 200
        assert resp.get_json()["voice_id"] == "vd_aabbccddeeff"

    def test_trim_silence_voice_not_found(self, client, app_module):
        with patch.object(app_module.voice_library, "trim_reference_silence", return_value=None):
            resp = client.post("/voices/vd_doesnotexist/trim-silence")
        assert resp.status_code == 404

    def test_set_default_variant_ok(self, client, app_module):
        with patch.object(
            app_module.voice_library,
            "set_default_variant",
            return_value={"voice_id": "vd_aabbccddeeff", "is_default": True},
        ):
            resp = client.post("/voices/vd_aabbccddeeff/set-default")
        assert resp.status_code == 200
        assert resp.get_json()["is_default"] is True

    def test_set_default_variant_not_found(self, client, app_module):
        with patch.object(app_module.voice_library, "set_default_variant", return_value=None):
            resp = client.post("/voices/vd_doesnotexist/set-default")
        assert resp.status_code == 404

    def test_path_traversal_rejected(self, client, app_module):
        with patch.object(app_module.voice_library, "get_voice", return_value=None):
            resp = client.get("/voices/../../etc/passwd")
        assert resp.status_code in (404, 400, 405)

    def test_builtin_voice_requires_pocket_backend(self, client, app_module, rt, monkeypatch):
        monkeypatch.setattr(rt, "tts_backend", "openvino")
        resp = client.post("/generate/async", json={"text": "hello", "builtin_voice": "vera"})
        assert resp.status_code == 400
        assert "TTS_BACKEND=pocket_tts" in resp.get_json()["error"]

    def test_builtin_voice_routes_to_pocket_voice_id(self, client, app_module, rt, monkeypatch):
        monkeypatch.setattr(rt, "tts_backend", "pocket_tts")
        rt.generate_calls.clear()

        resp = client.post("/generate", json={"text": "hello", "builtin_voice": "vera"})

        assert resp.status_code == 200
        assert rt.generate_calls[-1]["kwargs"]["voice_id"] == "pocket:vera"
