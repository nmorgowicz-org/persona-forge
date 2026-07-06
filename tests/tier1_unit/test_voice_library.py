"""Test voice_library CRUD, path traversal, ordering."""

from __future__ import annotations

import json

import pytest

from qwen3_tts import voice_library


@pytest.fixture(autouse=True)
def tmp_voice_dir(tmp_path, monkeypatch):
    voice_library.VOICE_LIBRARY_DIR = tmp_path
    yield tmp_path


class TestSaveGet:
    def test_save_voice_persists_wav_and_metadata(self):
        meta = voice_library.save_voice(
            b"RIFF....", description="a calm narrator", sample_text="hello there", language="English"
        )
        assert meta["voice_id"].startswith("vd_")
        assert meta["description"] == "a calm narrator"
        assert meta["sample_text"] == "hello there"
        assert meta["language"] == "English"

    def test_get_voice_round_trips(self):
        saved = voice_library.save_voice(
            b"RIFF....", description="desc", sample_text="text", language="English"
        )
        fetched = voice_library.get_voice(saved["voice_id"])
        assert fetched is not None
        assert fetched["voice_id"] == saved["voice_id"]

    def test_get_voice_unknown(self):
        assert voice_library.get_voice("vd_000000000000") is None


class TestPathTraversal:
    def test_rejects_dotdot(self):
        assert voice_library.get_voice("../../etc/passwd") is None

    def test_rejects_encoded_dotdot(self):
        assert voice_library.get_voice("vd_..%2f..%2fetc") is None


class TestWavBytes:
    def test_returns_saved_bytes(self):
        saved = voice_library.save_voice(
            b"RIFF-payload", description="desc", sample_text="text", language="English"
        )
        assert voice_library.get_voice_wav_bytes(saved["voice_id"]) == b"RIFF-payload"

    def test_unknown_returns_none(self):
        assert voice_library.get_voice_wav_bytes("vd_000000000000") is None


class TestListVoices:
    def test_newest_first(self):
        first = voice_library.save_voice(
            b"a", description="first", sample_text="text", language="English"
        )
        meta_path = voice_library.VOICE_LIBRARY_DIR / first["voice_id"] / "meta.json"
        data = json.loads(meta_path.read_text())
        data["created_at"] = 1.0
        meta_path.write_text(json.dumps(data))

        second = voice_library.save_voice(
            b"b", description="second", sample_text="text", language="English"
        )
        meta_path2 = voice_library.VOICE_LIBRARY_DIR / second["voice_id"] / "meta.json"
        data2 = json.loads(meta_path2.read_text())
        data2["created_at"] = 2.0
        meta_path2.write_text(json.dumps(data2))

        voices = voice_library.list_voices()
        assert [v["voice_id"] for v in voices] == [second["voice_id"], first["voice_id"]]

    def test_empty_when_missing(self):
        voice_library.VOICE_LIBRARY_DIR = voice_library.VOICE_LIBRARY_DIR / "nonexistent"
        assert voice_library.list_voices() == []


class TestUpdateDelete:
    def test_update_sample_text(self):
        saved = voice_library.save_voice(
            b"a", description="desc", sample_text="old", language="English"
        )
        updated = voice_library.update_voice(saved["voice_id"], sample_text="new text")
        assert updated is not None
        assert updated["sample_text"] == "new text"

    def test_delete_removes_directory(self):
        saved = voice_library.save_voice(
            b"a", description="desc", sample_text="text", language="English"
        )
        assert voice_library.delete_voice(saved["voice_id"]) is True
        assert not (voice_library.VOICE_LIBRARY_DIR / saved["voice_id"]).exists()

    def test_delete_nonexistent(self):
        assert voice_library.delete_voice("vd_000000000000") is False
