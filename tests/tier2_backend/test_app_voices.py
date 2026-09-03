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

    def test_duplicate_voice_ok(self, client, app_module):
        with patch.object(
            app_module.voice_library,
            "duplicate_voice",
            return_value={"voice_id": "vd_112233445566", "duplicated_from": "vd_aabbccddeeff"},
        ):
            resp = client.post("/voices/vd_aabbccddeeff/duplicate")
        assert resp.status_code == 201
        assert resp.get_json()["duplicated_from"] == "vd_aabbccddeeff"

    def test_duplicate_voice_not_found(self, client, app_module):
        with patch.object(app_module.voice_library, "duplicate_voice", return_value=None):
            resp = client.post("/voices/vd_doesnotexist/duplicate")
        assert resp.status_code == 404

    def test_analyze_voice_ok(self, client, app_module):
        with patch.object(app_module.voice_library, "analyze_reference", return_value={"voice_id": "vd_aabbccddeeff", "metrics": {"duration_seconds": 1.0}}):
            resp = client.post("/voices/vd_aabbccddeeff/analyze")
        assert resp.status_code == 200
        assert resp.get_json()["metrics"]["duration_seconds"] == 1.0

    def test_undo_reference_edit_ok(self, client, app_module):
        with patch.object(app_module.voice_library, "undo_reference_edit", return_value={"voice_id": "vd_aabbccddeeff", "undo_available": False}):
            resp = client.post("/voices/vd_aabbccddeeff/undo-reference-edit")
        assert resp.status_code == 200
        assert resp.get_json()["undo_available"] is False

    def test_undo_reference_edit_without_history(self, client, app_module):
        with patch.object(app_module.voice_library, "undo_reference_edit", return_value=None):
            resp = client.post("/voices/vd_aabbccddeeff/undo-reference-edit")
        assert resp.status_code == 409

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

    def test_activate_voice_for_qwen_api_default(self, client, app_module, tmp_path):
        wav_path = tmp_path / "reference.wav"
        wav_path.write_bytes(b"wav")
        meta = {
            "voice_id": "vd_aabbccddeeff",
            "wav_path": str(wav_path),
            "sample_text": "Hello from the saved voice.",
        }
        with patch.object(app_module.voice_library, "get_voice", return_value=meta), patch.object(
            app_module.model._rt,
            "activate_default_voice_from_library",
            create=True,
        ) as activate:
            resp = client.post("/voices/vd_aabbccddeeff/activate")
        assert resp.status_code == 200
        assert resp.get_json()["api_active"] is True
        activate.assert_called_once_with("vd_aabbccddeeff")

    def test_activate_qwen_voice_requires_transcript(self, client, app_module):
        with patch.object(
            app_module.voice_library,
            "get_voice",
            return_value={"voice_id": "vd_aabbccddeeff", "sample_text": ""},
        ), patch.object(
            app_module.model._rt,
            "activate_default_voice_from_library",
            create=True,
        ) as activate:
            resp = client.post("/voices/vd_aabbccddeeff/activate")
        assert resp.status_code == 400
        assert "Generate a transcript with Whisper" in resp.get_json()["error"]
        activate.assert_not_called()

    def test_transcribe_voice_persists_whisper_result(self, client, app_module, tmp_path):
        wav_path = tmp_path / "reference.wav"
        wav_path.write_bytes(b"wav")
        with patch.object(
            app_module.voice_library,
            "get_voice",
            return_value={"voice_id": "vd_aabbccddeeff", "wav_path": str(wav_path)},
        ), patch.object(
            app_module,
            "transcribe_reference_audio",
            return_value={
                "ok": True,
                "severity": "ok",
                "whisper_transcript": "Hello from Whisper.",
                "match_score": 1.0,
            },
        ), patch.object(
            app_module.voice_library,
            "update_voice",
            return_value={"voice_id": "vd_aabbccddeeff", "sample_text": "Hello from Whisper."},
        ) as update:
            resp = client.post("/voices/vd_aabbccddeeff/transcribe")
        assert resp.status_code == 200
        update.assert_called_once_with(
            "vd_aabbccddeeff",
            sample_text="Hello from Whisper.",
            sample_text_source="whisper",
            asr={
                "ok": True,
                "severity": "ok",
                "whisper_transcript": "Hello from Whisper.",
                "match_score": 1.0,
            },
        )

    def test_get_variants_lists_original_plus_saved_variants(self, client, app_module, tmp_path):
        voice_dir = tmp_path / "vd_aabbccddeeff"
        voice_dir.mkdir(parents=True)
        (voice_dir / "original.wav").write_bytes(b"orig")
        (voice_dir / "prosody_clean-1x.wav").write_bytes(b"var")
        (voice_dir / "variants.json").write_text(
            '{"clean-1x": {"filename": "prosody_clean-1x.wav", "label": "Neutral 1.0x", '
            '"created_at": 1.0, "source": "preset"}}'
        )
        with patch.object(app_module.voice_library, "VOICE_LIBRARY_DIR", tmp_path):
            resp = client.get("/voices/vd_aabbccddeeff/variants")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["entries"][0] == {
            "id": "vd_aabbccddeeff",
            "filename": "original.wav",
            "label": "Original",
            "is_original": True,
        }
        assert body["entries"][1]["id"] == "vd_aabbccddeeff.clean-1x"
        assert body["active_filename"] == "original.wav"
        assert body["active_variant"] is None

    def test_get_variants_not_found(self, client, app_module, tmp_path):
        with patch.object(app_module.voice_library, "VOICE_LIBRARY_DIR", tmp_path):
            resp = client.get("/voices/vd_000000000000/variants")
        assert resp.status_code == 404

    def test_save_prosody_variant_ok_does_not_promote(self, client, app_module):
        with patch.object(
            app_module.voice_library,
            "save_prosody_variant",
            return_value={
                "voice_id": "vd_aabbccddeeff",
                "variant_id": "vd_aabbccddeeff.neutral-2x",
                "variant_slug": "neutral-2x",
            },
        ) as mocked:
            resp = client.post(
                "/voices/vd_aabbccddeeff/prosody-variants",
                json={"style_preset": "Neutral", "pace_multiplier": 2.0},
            )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["variant_id"] == "vd_aabbccddeeff.neutral-2x"
        mocked.assert_called_once()
        _args, kwargs = mocked.call_args
        assert kwargs["style_preset"] == "Neutral"
        assert kwargs["pace_multiplier"] == 2.0

    def test_get_variant_metrics_ok(self, client, app_module):
        with patch.object(
            app_module.voice_library,
            "compute_variant_metrics",
            return_value={"metrics": {"duration_seconds": 1.0}, "quality_score": 90.0, "quality_warnings": []},
        ) as mocked:
            resp = client.get("/voices/vd_aabbccddeeff/variants/original.wav/metrics")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["metrics"]["duration_seconds"] == 1.0
        mocked.assert_called_once_with("vd_aabbccddeeff", "original.wav")

    def test_get_variant_metrics_not_found(self, client, app_module):
        with patch.object(app_module.voice_library, "compute_variant_metrics", return_value=None):
            resp = client.get("/voices/vd_doesnotexist/variants/original.wav/metrics")
        assert resp.status_code == 404

    def test_save_prosody_variant_not_found(self, client, app_module):
        with patch.object(app_module.voice_library, "save_prosody_variant", return_value=None):
            resp = client.post("/voices/vd_doesnotexist/prosody-variants", json={})
        assert resp.status_code == 404

    def test_save_prosody_variant_rejects_bad_pace(self, client, app_module):
        resp = client.post(
            "/voices/vd_aabbccddeeff/prosody-variants",
            json={"pace_multiplier": "not-a-number"},
        )
        assert resp.status_code == 400

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
