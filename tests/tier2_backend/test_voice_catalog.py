import json

import pytest

from persona_forge import provisioned_engines, voice_catalog


def test_every_generated_engine_has_a_bundled_list():
    for engine_id in voice_catalog.GENERATED_ENGINES:
        voices = voice_catalog.bundled_voices(engine_id)
        assert voices, engine_id
        assert all({"name", "language"} <= set(entry) for entry in voices)
        names = [entry["name"] for entry in voices]
        assert len(names) == len(set(names)), f"{engine_id} lists a voice twice"


def test_pocket_lite_voices_come_from_its_worker():
    names = [entry["name"] for entry in voice_catalog.bundled_voices("pocket-lite")]
    assert len(names) == 21 and "alba" in names


def test_the_bundled_pocket_lite_list_matches_the_worker_without_an_install():
    assert voice_catalog.generate("pocket-lite") == voice_catalog.bundled_voices("pocket-lite")


def test_gender_comes_from_a_name_only_when_the_name_says_so():
    assert voice_catalog.gender_from_name("NewsAnchorFemale") == "female"
    assert voice_catalog.gender_from_name("GrandpaStory") == "male"
    assert voice_catalog.gender_from_name("Bella") is None
    assert voice_catalog.gender_from_name("FemaleAndMaleDuet") is None
    assert voice_catalog.split_camel("CalmHostageNegotiator") == "Calm Hostage Negotiator"


def _tone(path, hertz, seconds=2.0, rate=16000):
    import numpy as np
    import soundfile

    t = np.arange(int(rate * seconds)) / rate
    wave = np.sin(2 * np.pi * hertz * t) + np.sin(4 * np.pi * hertz * t) / 2 + np.sin(6 * np.pi * hertz * t) / 3
    soundfile.write(str(path), (0.15 * wave).astype("float32"), rate)


def test_a_low_pitch_clip_is_estimated_male_and_a_high_one_female(tmp_path):
    pytest.importorskip("librosa")
    _tone(tmp_path / "low.wav", 110)
    _tone(tmp_path / "high.wav", 220)
    assert voice_catalog.estimate_gender(tmp_path / "low.wav") == "male"
    assert voice_catalog.estimate_gender(tmp_path / "high.wav") == "female"


def test_silence_is_not_given_a_gender(tmp_path):
    pytest.importorskip("librosa")
    import numpy as np
    import soundfile

    soundfile.write(str(tmp_path / "quiet.wav"), np.zeros(16000, dtype="float32"), 16000)
    assert voice_catalog.estimate_gender(tmp_path / "quiet.wav") is None


def test_every_entry_says_how_far_its_gender_can_be_trusted():
    for engine_id in voice_catalog.GENERATED_ENGINES:
        for entry in voice_catalog.bundled_voices(engine_id):
            assert bool(entry.get("gender")) == bool(entry.get("gender_source")), entry
            assert entry.get("gender_source", "upstream") in {"upstream", "name", "estimated"}
    kitten = voice_catalog.bundled_voices("kitten2")
    assert {entry.get("gender_source") for entry in kitten} <= {"name", "estimated", None}


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


@pytest.mark.parametrize("engine_id", voice_catalog.GENERATED_ENGINES)
def test_the_bundled_list_matches_an_installed_pack(engine_id):
    """Staleness guard: when the engine is installed here, its real voices must equal the bundle."""
    provisioned = provisioned_engines.get(engine_id)
    if provisioned is None or not provisioned.engine.is_installed():
        pytest.skip(f"{engine_id} is not installed on this machine")
    assert voice_catalog.generate(engine_id) == voice_catalog.bundled_voices(engine_id), (
        "regenerate with: python -m persona_forge.voice_catalog"
    )
    reported = voice_catalog.installed_voices(provisioned)
    assert [entry["name"] for entry in reported] == [e["name"] for e in voice_catalog.bundled_voices(engine_id)]


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


def test_kitten_voices_named_for_a_language_are_not_english():
    from persona_forge import kitten2_engine

    assert kitten2_engine.language_from_name("KoreanNewsAnchor") == "ko"
    assert kitten2_engine.language_from_name("Bella") is None
    assert kitten2_engine.preset_language("IndonesianTourGuide") == "id"
    assert kitten2_engine.preset_language("Bella") == "en"
    languages = {entry["name"]: entry["language"] for entry in voice_catalog.bundled_voices("kitten2")}
    assert languages["PolishNewsAnchor"] == "pl" and languages["NewsAnchorFemale"] == "en"
