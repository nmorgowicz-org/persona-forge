"""Server-side UI preferences (contract D17 / §6.11): ``ui_preferences.json`` next to
``runtime.json``, allowlisted keys, validated values, atomic writes."""

import json
import warnings

import pytest

from persona_forge import ui_preferences_store


@pytest.fixture
def prefs_json(tmp_path):
    return tmp_path / "ui_preferences.json"


def test_load_missing_file_returns_empty(tmp_path):
    assert ui_preferences_store.load(path=tmp_path / "does_not_exist.json") == {}


def test_load_corrupt_file_warns_and_returns_empty(prefs_json):
    prefs_json.write_text("{not valid json")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        loaded = ui_preferences_store.load(path=prefs_json)

    assert loaded == {}
    assert any("corrupt" in str(w.message) for w in caught)


def test_load_malformed_shape_warns_and_returns_empty(prefs_json):
    prefs_json.write_text(json.dumps({"schema_version": 1, "values": ["theme"]}))

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        loaded = ui_preferences_store.load(path=prefs_json)

    assert loaded == {}
    assert any("unexpected shape" in str(w.message) for w in caught)


def test_unknown_key_rejected_and_file_unchanged(prefs_json):
    ui_preferences_store.merge_and_save({"theme": "teal"}, path=prefs_json)
    before = prefs_json.read_bytes()

    with pytest.raises(ValueError, match=r"^fontSize: "):
        ui_preferences_store.merge_and_save({"theme": "rose", "fontSize": "large"}, path=prefs_json)

    assert prefs_json.read_bytes() == before


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("voiceLibrary.analysisExpanded", "yes"),
        ("voiceLibrary.analysisExpanded", 1),
        ("theme", 7),
        ("voiceLibrary.tab", "projects"),
        ("updates.dismissedVersion", None),
    ],
)
def test_wrong_type_or_value_rejected(prefs_json, key, value):
    with pytest.raises(ValueError, match=rf"^{key}: "):
        ui_preferences_store.merge_and_save({key: value}, path=prefs_json)

    assert not prefs_json.exists()


@pytest.mark.parametrize(
    ("key", "limit"),
    [
        ("theme", 32),
        ("experienceLevel", 32),
        ("voiceLibrary.layout", 32),
        ("updates.dismissedVersion", 64),
    ],
)
def test_over_length_string_rejected(prefs_json, key, limit):
    assert ui_preferences_store.merge_and_save({key: "x" * limit}, path=prefs_json) == {key: "x" * limit}

    with pytest.raises(ValueError, match=rf"^{key}: "):
        ui_preferences_store.merge_and_save({key: "x" * (limit + 1)}, path=prefs_json)

    assert ui_preferences_store.load(path=prefs_json) == {key: "x" * limit}


def test_merge_keeps_untouched_keys(prefs_json):
    ui_preferences_store.merge_and_save(
        {"theme": "teal", "voiceLibrary.tab": "segments"}, path=prefs_json
    )

    merged = ui_preferences_store.merge_and_save(
        {"voiceLibrary.analysisExpanded": False, "theme": "amber"}, path=prefs_json
    )

    expected = {
        "theme": "amber",
        "voiceLibrary.tab": "segments",
        "voiceLibrary.analysisExpanded": False,
    }
    assert merged == expected
    assert ui_preferences_store.load(path=prefs_json) == expected


def test_round_trip_all_keys(prefs_json):
    values = {
        "theme": "rose",
        "experienceLevel": "expert",
        "voiceLibrary.tab": "voices",
        "voiceLibrary.layout": "grid-3",
        "voiceLibrary.analysisExpanded": True,
        "updates.dismissedVersion": "2.3.0",
    }
    assert set(values) == set(ui_preferences_store.ALLOWED_KEYS)

    ui_preferences_store.merge_and_save(values, path=prefs_json)

    assert ui_preferences_store.load(path=prefs_json) == values
    assert json.loads(prefs_json.read_text()) == {"schema_version": 1, "values": values}


def test_default_path_is_next_to_runtime_json(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    ui_preferences_store.merge_and_save({"theme": "teal"})

    assert json.loads((tmp_path / "ui_preferences.json").read_text())["values"] == {"theme": "teal"}
    assert ui_preferences_store.load() == {"theme": "teal"}
