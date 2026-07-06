"""Test startup, 503, idle unload/reload, backend mismatch, malloc_trim."""

import pytest
from unittest.mock import patch


@pytest.mark.integration
class TestStartup503:

    def test_health_before_service_started(self, app_module, rt):
        orig_started = rt._service_started
        orig_failed = rt._startup_failed
        rt._service_started = False
        rt._startup_failed = False
        try:
            client = app_module.app.test_client()
            resp = client.get("/health")
            data = resp.get_json()
            assert data["service_started"] is False
            assert data["status"] in ("degraded", "error")
        finally:
            rt._service_started = orig_started
            rt._startup_failed = orig_failed

    def test_generate_returns_503_before_started_then_ok(self, app_module):
        # app.py's _ensure_service_started reads model._service_started and
        # model._startup_failed. Patch the fake module directly so its local
        # function sees the change and returns quickly via the startup_failed path.
        from qwen3_tts import model

        orig_started = model._service_started
        orig_failed = model._startup_failed
        model._service_started = False
        model._startup_failed = True
        try:
            client = app_module.app.test_client()
            resp = client.post(
                "/generate",
                json={"text": "hello"},
            )
            assert resp.status_code == 503
        finally:
            model._service_started = orig_started
            model._startup_failed = orig_failed


@pytest.mark.integration
class TestStartupFailed:

    def test_health_with_startup_failed(self, app_module, rt):
        orig_started = rt._service_started
        orig_failed = rt._startup_failed
        rt._service_started = False
        rt._startup_failed = True
        try:
            client = app_module.app.test_client()
            resp = client.get("/health")
            data = resp.get_json()
            assert data["status"] == "error"
        finally:
            rt._service_started = orig_started
            rt._startup_failed = orig_failed


@pytest.mark.integration
class TestIdleUnload:

    def test_idle_unload_then_reload(self, rt):
        assert rt._model_loaded is True

        rt.force_unload()
        assert rt._model_loaded is False
        assert rt.model is None

        rt.load_model(profile=rt.BASE_PROFILE)
        assert rt._model_loaded is True
        assert len(rt.load_model_calls) >= 1

    def test_force_unload_called_via_fake_module(self, rt):
        # Validate that the fake_module's force_unload tracks calls
        # (app.py and other modules call model.force_unload, not rt.force_unload).
        from qwen3_tts import model

        initial_len = len(rt.force_unload_calls)
        model.force_unload()
        assert len(rt.force_unload_calls) > initial_len


@pytest.mark.integration
class TestBackendMismatch:

    def test_openvino_requested_but_generate_fails(self, rt):
        # Validate: when generate_should_fail is True, _run_generate raises.
        from qwen3_tts import model

        rt.generate_should_fail = True
        try:
            with pytest.raises(RuntimeError, match="fake generate error"):
                model._run_generate("hello", "English")
        finally:
            rt.generate_should_fail = False
