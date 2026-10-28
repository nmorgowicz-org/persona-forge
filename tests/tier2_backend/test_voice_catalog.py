import json

import pytest

from persona_forge import provisioned_engines, voice_catalog


def test_every_generated_engine_has_a_bundled_list():
    for engine_id in voice_catalog.GENERATED_ENGINES:
        voices = voice_catalog.bundled_voices(engine_id)
        assert voices, engine_id
        assert all(set(entry) == {"name", "language"} for entry in voices)
        names = [entry["name"] for entry in voices]
        assert len(names) == len(set(names)), f"{engine_id} lists a voice twice"


def test_pocket_lite_voices_come_from_its_worker():
    names = [entry["name"] for entry in voice_catalog.bundled_voices("pocket-lite")]
    assert len(names) == 21 and "alba" in names


def test_an_unknown_engine_has_no_bundled_voices():
    assert voice_catalog.bundled_voices("nope") == []


def test_a_missing_or_broken_file_means_no_voices(monkeypatch, tmp_path):
    broken = tmp_path / "catalog.json"
    broken.write_text("{not json")
    monkeypatch.setattr(voice_catalog, "CATALOG_FILE", broken)
    voice_catalog._load.cache_clear()
    try:
        assert voice_catalog.bundled_voices("kokoro") == []
        monkeypatch.setattr(voice_catalog, "CATALOG_FILE", tmp_path / "absent.json")
        voice_catalog._load.cache_clear()
        assert voice_catalog.bundled_voices("kokoro") == []
    finally:
        voice_catalog._load.cache_clear()


@pytest.mark.parametrize("engine_id", voice_catalog.GENERATED_ENGINES + ("pocket-lite",))
def test_the_bundled_list_matches_an_installed_pack(engine_id):
    """Staleness guard: when the engine is installed here, its real voices must equal the bundle."""
    provisioned = provisioned_engines.get(engine_id)
    if provisioned is None or not provisioned.engine.is_installed():
        pytest.skip(f"{engine_id} is not installed on this machine")
    assert voice_catalog.installed_voices(provisioned) == voice_catalog.bundled_voices(engine_id), (
        "regenerate with: python -m persona_forge.voice_catalog"
    )


def test_refresh_keeps_an_engine_that_is_not_installed(monkeypatch, tmp_path):
    target = tmp_path / "out.json"

    class _Gone:
        def is_installed(self):
            return False

    class _Entry:
        engine = _Gone()

    monkeypatch.setattr(provisioned_engines, "get", lambda engine_id: _Entry())
    before = voice_catalog.refresh(target)

    assert before == json.loads(voice_catalog.CATALOG_FILE.read_text())
    assert json.loads(target.read_text()) == before
    voice_catalog._load.cache_clear()
