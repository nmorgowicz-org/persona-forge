"""Test GET/POST /ui/preferences (contract D17 / §6.11)."""

import json

import pytest


@pytest.fixture(autouse=True)
def _isolated_store(monkeypatch, tmp_path):
    # runtime_data_dir() honours DATA_DIR first; each test gets its own empty store.
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path / "ui_preferences.json"


@pytest.mark.integration
class TestUiPreferences:

    def test_get_empty_store(self, client):
        resp = client.get("/ui/preferences")

        assert resp.status_code == 200
        assert resp.get_json() == {"values": {}}

    def test_post_then_get(self, client, _isolated_store):
        first = client.post("/ui/preferences", json={"values": {"theme": "teal"}})
        assert first.status_code == 200
        assert first.get_json() == {"values": {"theme": "teal"}}

        second = client.post(
            "/ui/preferences",
            json={"values": {"voiceLibrary.analysisExpanded": False}},
        )
        assert second.status_code == 200
        merged = {"theme": "teal", "voiceLibrary.analysisExpanded": False}
        assert second.get_json() == {"values": merged}

        resp = client.get("/ui/preferences")
        assert resp.status_code == 200
        assert resp.get_json() == {"values": merged}
        assert json.loads(_isolated_store.read_text())["values"] == merged

    def test_unknown_key_is_400_and_not_saved(self, client):
        client.post("/ui/preferences", json={"values": {"theme": "teal"}})

        resp = client.post(
            "/ui/preferences", json={"values": {"theme": "rose", "fontSize": "large"}}
        )

        assert resp.status_code == 400
        assert resp.get_json()["error"].startswith("fontSize: ")
        assert client.get("/ui/preferences").get_json() == {"values": {"theme": "teal"}}

    @pytest.mark.parametrize(
        "body",
        [b"not json", b'{"theme": "teal"}', b'{"values": ["theme"]}'],
        ids=["invalid-json", "missing-values", "values-not-object"],
    )
    def test_malformed_body_is_400(self, client, body):
        resp = client.post("/ui/preferences", data=body, content_type="application/json")

        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_oversize_body_is_413(self, client, _isolated_store):
        body = json.dumps({"values": {"theme": "x" * (16 * 1024)}})

        resp = client.post("/ui/preferences", data=body, content_type="application/json")

        assert resp.status_code == 413
        assert "error" in resp.get_json()
        assert not _isolated_store.exists()

    def test_works_while_model_not_loaded(self, app_module, rt):
        orig_started = rt._service_started
        orig_loaded = rt._model_loaded
        rt._service_started = False
        rt._model_loaded = False
        try:
            client = app_module.app.test_client()

            posted = client.post("/ui/preferences", json={"values": {"theme": "amber"}})
            fetched = client.get("/ui/preferences")

            assert posted.status_code == 200
            assert fetched.status_code == 200
            assert fetched.get_json() == {"values": {"theme": "amber"}}
        finally:
            rt._service_started = orig_started
            rt._model_loaded = orig_loaded
