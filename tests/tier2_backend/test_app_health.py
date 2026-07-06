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
