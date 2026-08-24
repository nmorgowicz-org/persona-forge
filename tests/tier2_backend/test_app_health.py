"""Test /health in startup, running, and failure states."""

import pytest


@pytest.mark.integration
class TestAppHealth:

    def test_health_ok_normal(self, client):
        resp = client.get("/health")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "ok"
        assert data["service_started"] is True
        assert data["model_loaded"] is True

    def test_health_not_started_still_200(self, app_module, rt):
        orig_started = rt._service_started
        orig_loaded = rt._model_loaded
        rt._service_started = False
        rt._model_loaded = False
        try:
            resp = app_module.app.test_client().get("/health")
            data = resp.get_json()
            assert resp.status_code == 200
            assert data["service_started"] is False
            assert data["status"] in ("degraded", "error")
            # app.py adds loading_message when _service_started is False
            assert data.get("loading_message") == "Loading model…"
        finally:
            rt._service_started = orig_started
            rt._model_loaded = orig_loaded

    def test_health_503_startup_failed(self, app_module, rt):
        orig_started = rt._service_started
        orig_failed = rt._startup_failed
        rt._service_started = False
        rt._startup_failed = True
        try:
            resp = app_module.app.test_client().get("/health")
            data = resp.get_json()
            assert data["status"] == "error"
            assert data["service_started"] is False
        finally:
            rt._service_started = orig_started
            rt._startup_failed = orig_failed

    def test_health_swap_in_progress(self, app_module):
        orig = app_module.voice_design._swap_in_progress
        app_module.voice_design._swap_in_progress = True
        try:
            resp = app_module.app.test_client().get("/health")
            data = resp.get_json()
            assert data["swap_in_progress"] is True
        finally:
            app_module.voice_design._swap_in_progress = orig

    def test_health_base_load_in_progress_message(self, app_module, rt):
        orig = rt._base_load_in_progress
        rt._base_load_in_progress = True
        try:
            resp = app_module.app.test_client().get("/health")
            data = resp.get_json()
            assert data["base_load_in_progress"] is True
            assert data.get("loading_message") == "Loading model…"
        finally:
            rt._base_load_in_progress = orig

    def test_health_omnivoice_loading_message(self, app_module):
        orig = app_module.omnivoice_engine.swap_in_progress
        app_module.omnivoice_engine.swap_in_progress = lambda: True
        try:
            resp = app_module.app.test_client().get("/health")
            data = resp.get_json()
            assert data["swap_in_progress"] is True
            assert data.get("loading_message") == "Loading OmniVoice…"
        finally:
            app_module.omnivoice_engine.swap_in_progress = orig

    def test_health_pocket_tts_provenance(self, app_module, rt):
        orig_backend = rt.tts_backend
        orig_prov = rt.pocket_provenance
        orig_lang = rt.pocket_language
        orig_default_state = rt.pocket_default_voice_state
        rt.tts_backend = "pocket_tts"
        rt.pocket_language = "english"
        rt.pocket_default_voice_state = None
        rt.pocket_provenance = {
            "engine": "torch",
            "model_source": "lunahr",
            "model_revision": "d03cd734",
            "model_sha256": "47" + "0" * 62,
            "model_verified": True,
            "cloning_available": True,
            "cloning_status": "ready",
            "message": "",
        }
        try:
            resp = app_module.app.test_client().get("/health")
            data = resp.get_json()
            block = data["pocket_tts"]
            assert resp.status_code == 200
            assert block["backend"] == "pocket_tts"
            assert block["language"] == "english"
            assert block["pocket_engine"] == "torch"
            assert block["pocket_model_source"] == "lunahr"
            assert block["pocket_model_revision"] == "d03cd734"
            assert block["pocket_model_sha256"] == "47" + "0" * 62
            assert block["pocket_model_verified"] is True
            assert block["pocket_cloning_available"] is True
            assert block["pocket_cloning_status"] == "ready"
            # Ready model with no REF_AUDIO must not warn about the HF token.
            assert "message" not in block
        finally:
            rt.tts_backend = orig_backend
            rt.pocket_provenance = orig_prov
            rt.pocket_language = orig_lang
            rt.pocket_default_voice_state = orig_default_state

    def test_health_pocket_tts_degraded_message(self, app_module, rt):
        orig_backend = rt.tts_backend
        orig_prov = rt.pocket_provenance
        rt.tts_backend = "pocket_tts"
        rt.pocket_provenance = {
            "engine": "torch",
            "model_source": "kyutai_without_cloning",
            "model_revision": "d29db79",
            "model_sha256": "be" + "0" * 62,
            "model_verified": True,
            "cloning_available": False,
            "cloning_status": "degraded",
            "message": (
                "Voice cloning model could not be downloaded; running with built-in "
                "voices only. Set an HF_TOKEN (for the official kyutai source) or "
                "restore network access to enable cloning."
            ),
        }
        try:
            resp = app_module.app.test_client().get("/health")
            block = resp.get_json()["pocket_tts"]
            assert block["pocket_model_source"] == "kyutai_without_cloning"
            assert block["pocket_cloning_available"] is False
            assert block["pocket_cloning_status"] == "degraded"
            assert block["message"].startswith("Voice cloning model could not be downloaded")
        finally:
            rt.tts_backend = orig_backend
            rt.pocket_provenance = orig_prov

    def test_health_startup_failed_message(self, app_module, rt):
        orig_started = rt._service_started
        orig_failed = rt._startup_failed
        orig_error = rt._startup_error
        # A real startup failure sets _startup_failed and _startup_error together
        # (model.py load path), so mirror that here.
        rt._service_started = False
        rt._startup_failed = True
        rt._startup_error = "fake startup error"
        try:
            resp = app_module.app.test_client().get("/health")
            data = resp.get_json()
            assert data["status"] == "error"
            assert data.get("loading_message") == "Model failed to load"
            assert data.get("error") == "fake startup error"
        finally:
            rt._service_started = orig_started
            rt._startup_failed = orig_failed
            rt._startup_error = orig_error
