from persona_forge import ui_preferences_store


def _set(monkeypatch, tmp_path, value):
    monkeypatch.setattr(ui_preferences_store, "_ui_preferences_path", lambda: tmp_path / "p.json")
    ui_preferences_store.merge_and_save({"api.enforceLanguage": value})


def test_helper_reads_languages(app_module):
    assert app_module._voice_language_code(None) == "en"
    assert app_module._voice_language_code("pocket:vera") == "en"
    assert app_module._voice_language_code("kokoro:ff_siwis") == "fr"


def test_off_by_default_serves_non_english(app_module, monkeypatch, tmp_path):
    monkeypatch.setattr(ui_preferences_store, "_ui_preferences_path", lambda: tmp_path / "p.json")
    assert app_module._language_enforcement_error("kokoro:ff_siwis", "French") is None


def test_on_blocks_non_english_voice_and_language(app_module, monkeypatch, tmp_path):
    _set(monkeypatch, tmp_path, True)
    voice_error = app_module._language_enforcement_error("kokoro:ff_siwis", "English")
    assert voice_error and "not English" in voice_error and "Integrations" in voice_error
    assert app_module._language_enforcement_error("kokoro:af_heart", "French")
    assert app_module._language_enforcement_error("kokoro:af_heart", "English") is None
    assert app_module._language_enforcement_error(None, "english") is None


def test_http_returns_400_with_the_reason(client, monkeypatch, tmp_path):
    _set(monkeypatch, tmp_path, True)
    voice = client.post(
        "/v1/audio/speech", json={"model": "kokoro", "input": "bonjour", "voice": "kokoro:ff_siwis"}
    )
    assert voice.status_code == 400
    assert "not English" in voice.get_json()["error"]["message"]
    language = client.post(
        "/v1/audio/speech",
        json={"model": "pocket-tts", "input": "x", "voice": "pocket:vera", "language": "French"},
    )
    assert language.status_code == 400
    assert "Language 'French'" in language.get_json()["error"]["message"]
