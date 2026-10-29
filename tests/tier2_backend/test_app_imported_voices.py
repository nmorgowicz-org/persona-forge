"""HTTP surface of imported prepared voices: upload, list, serve as built-ins, remove."""

from __future__ import annotations

import io

import pytest

from persona_forge import imported_voices, phonon_engine, speech_engines
from persona_forge.kitten2_engine import InvalidVoice
from tests.tier2_backend.test_imported_voices import GOOD, build


class StubAdapter:
    def __init__(self):
        self.error = None
        self.imports: list[tuple[str, str]] = []
        self.forgotten: list[str] = []

    def import_voice(self, slug, path, sha256=None):
        if self.error is not None:
            raise self.error
        self.imports.append((slug, str(path)))

    def forget_imported(self, slug):
        self.forgotten.append(slug)


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("IMPORTED_VOICES_DIR", str(tmp_path / "imported"))
    adapter = StubAdapter()
    monkeypatch.setitem(speech_engines.ADAPTERS, "phonon-31m", adapter)
    monkeypatch.setattr(phonon_engine, "is_installed", lambda root=None: True)
    monkeypatch.setattr(phonon_engine, "list_presets", lambda root=None: ["Easton", "Zoey"])
    monkeypatch.setattr(imported_voices, "_is_installed", lambda engine_id: True)
    monkeypatch.setattr(imported_voices, "_engine_revision", lambda engine_id: "rev-1")
    monkeypatch.setattr(imported_voices, "_catalog_names", lambda engine_id: {"Easton", "Zoey"})
    return adapter


def _upload(client, *, data=GOOD, filename="zoey.safetensors", name="Zoey copy", engine="phonon-31m"):
    return client.post(
        f"/engines/{engine}/imported-voices",
        data={"name": name, "file": (io.BytesIO(data), filename)},
        content_type="multipart/form-data",
    )


def test_uploading_a_valid_voice_returns_its_record_and_serves_it(client, env):
    response = _upload(client)

    assert response.status_code == 201
    record = response.get_json()["voice"]
    assert record["voice_id"] == "phonon:imported-zoey-copy"
    assert record["source_filename"] == "zoey.safetensors" and len(record["sha256"]) == 64
    assert record["engine_revision"] == "rev-1" and record["imported_at"]
    assert env.imports and env.imports[0][0] == "imported-zoey-copy"


def test_the_imported_voice_is_listed_with_its_provenance(client, env):
    _upload(client)

    listed = client.get("/engines/phonon-31m/imported-voices").get_json()["voices"]

    assert [v["voice_id"] for v in listed] == ["phonon:imported-zoey-copy"]
    assert listed[0]["source_filename"] == "zoey.safetensors"


def test_the_builtin_catalog_shows_imports_next_to_presets_and_says_who_can_import(client, env):
    _upload(client)

    full = client.get("/voices/built-in?engines=all").get_json()

    imported = next(v for v in full["voices"] if v["voice_id"] == "phonon:imported-zoey-copy")
    assert imported["imported"] is True and imported["engine"] == "phonon-31m"
    assert imported["display_name"] == "Zoey copy" and imported["installed"] is True
    assert imported["provenance"]["source_filename"] == "zoey.safetensors"
    preset = next(v for v in full["voices"] if v["voice_id"] == "phonon:Zoey")
    assert not preset.get("imported")
    capable = {e["id"]: e["import_prepared_voice"] for e in full["engines"]}
    assert capable["phonon-31m"] is True
    assert capable["kitten2"] is False and capable["kokoro"] is False and capable["pocket-lite"] is False
    summary = next(e for e in full["engines"] if e["id"] == "phonon-31m")
    assert summary["voices"] == 3  # two presets and the import


def test_the_openai_voice_list_includes_the_import(client, env):
    _upload(client)

    data = client.get("/v1/audio/voices?language=all").get_json()["data"]

    entry = next(v for v in data if v["voice_id"] == "phonon:imported-zoey-copy")
    assert entry["engine"] == "phonon-31m" and entry["kind"] == "preset" and entry["servable"] is True


def test_an_imported_voice_can_be_the_api_default(client, env, monkeypatch, tmp_path):
    from persona_forge import voice_library

    monkeypatch.setattr(voice_library, "VOICE_LIBRARY_DIR", tmp_path / "voices")
    monkeypatch.setattr(voice_library, "ACTIVE_DEFAULT_FILE", tmp_path / "voices" / ".active_default")
    monkeypatch.setattr(voice_library, "API_DEFAULT_FILE", tmp_path / "voices" / ".api_default.json")
    (tmp_path / "voices").mkdir()
    _upload(client)

    response = client.put(
        "/api-default", json={"engine": "phonon-31m", "voice": "phonon:imported-zoey-copy"}
    )

    assert response.status_code == 200, response.get_data(as_text=True)


def test_removing_an_import_deletes_it_and_it_stops_being_offered(client, env):
    _upload(client)

    response = client.delete("/engines/phonon-31m/imported-voices/imported-zoey-copy")

    assert response.status_code == 200 and response.get_json()["removed"] == "imported-zoey-copy"
    assert env.forgotten == ["imported-zoey-copy"]
    assert client.get("/engines/phonon-31m/imported-voices").get_json()["voices"] == []
    ids = {v["voice_id"] for v in client.get("/voices/built-in?engines=all").get_json()["voices"]}
    assert "phonon:imported-zoey-copy" not in ids


def test_removing_something_that_is_not_there_is_404_and_a_bad_slug_is_400(client, env):
    assert client.delete("/engines/phonon-31m/imported-voices/imported-nope").status_code == 404
    assert client.delete("/engines/phonon-31m/imported-voices/Zoey").status_code == 400


@pytest.mark.parametrize(
    ("kwargs", "status", "code"),
    [
        ({"data": b"\x80\x04 pickled"}, 422, "invalid_voice_file"),
        ({"data": build(shape=(1, 512, 64))}, 422, "invalid_voice_file"),
        ({"filename": "voice.pkl"}, 400, "bad_extension"),
        ({"filename": "../../etc/voice.safetensors"}, 400, "invalid_filename"),
        ({"name": ""}, 400, "invalid_name"),
        ({"name": "../x"}, 400, "invalid_name"),
        ({"engine": "kitten2"}, 400, "import_unsupported"),
        ({"engine": "kokoro"}, 400, "import_unsupported"),
        ({"engine": "nope"}, 404, "unknown_engine"),
    ],
)
def test_bad_uploads_are_refused_with_a_stable_code(client, env, kwargs, status, code):
    response = _upload(client, **kwargs)

    assert response.status_code == status and response.get_json()["code"] == code
    assert env.imports == []


def test_an_oversized_upload_is_413(client, env):
    response = _upload(client, data=GOOD + b"\x00" * imported_voices.MAX_FILE_BYTES)

    assert response.status_code == 413 and response.get_json()["code"] == "file_too_large"


def test_a_request_without_a_file_is_a_400(client, env):
    response = client.post(
        "/engines/phonon-31m/imported-voices", data={"name": "x"}, content_type="multipart/form-data"
    )

    assert response.status_code == 400 and response.get_json()["code"] == "missing_file"


def test_a_voice_the_engine_rejects_is_a_422_that_keeps_nothing(client, env):
    env.error = InvalidVoice("Phonon could not read this voice file: nope")

    response = _upload(client)

    assert response.status_code == 422 and response.get_json()["code"] == "engine_rejected"
    assert "could not read" in response.get_json()["error"]
    assert client.get("/engines/phonon-31m/imported-voices").get_json()["voices"] == []


def test_importing_the_same_name_twice_is_a_409(client, env):
    _upload(client)

    assert _upload(client).status_code == 409
