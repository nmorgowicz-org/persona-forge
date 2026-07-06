"""Test segment_library CRUD, path traversal, ordering."""

from __future__ import annotations

import pytest

from qwen3_tts import segment_library


@pytest.fixture(autouse=True)
def tmp_seg_dir(tmp_path, monkeypatch):
    segment_library.SEGMENT_LIBRARY_DIR = tmp_path
    yield tmp_path


class TestSaveGet:
    def test_save_persists_wav_and_metadata(self):
        meta = segment_library.save_segment(
            b"RIFF....",
            text="G'day, how are you?",
            instruct="female, young adult, high pitch, australian accent",
            engine="omnivoice",
            sample_rate=24000,
            accent_id="au",
        )
        assert meta["segment_id"].startswith("seg_")
        assert meta["tags"] == ["female", "young adult", "high pitch", "australian accent"]
        assert meta["accent_id"] == "au"

    def test_get_round_trips(self):
        saved = segment_library.save_segment(
            b"RIFF....", text="hi", instruct="female", engine="omnivoice", sample_rate=24000
        )
        fetched = segment_library.get_segment(saved["segment_id"])
        assert fetched is not None
        assert fetched["segment_id"] == saved["segment_id"]

    def test_get_unknown(self):
        assert segment_library.get_segment("seg_000000000000") is None


class TestPathTraversal:
    def test_dotdot_rejected(self):
        assert segment_library.get_segment("../../etc/passwd") is None
        assert segment_library.get_segment("seg_..%2f..%2fetc") is None

    def test_delete_dotdot_rejected(self):
        assert segment_library.delete_segment("../../etc") is False


class TestWavBytes:
    def test_returns_written_bytes(self):
        saved = segment_library.save_segment(
            b"RIFF-payload", text="hi", instruct="female", engine="omnivoice", sample_rate=24000
        )
        assert segment_library.get_segment_wav_bytes(saved["segment_id"]) == b"RIFF-payload"

    def test_unknown_returns_none(self):
        assert segment_library.get_segment_wav_bytes("seg_000000000000") is None


class TestDelete:
    def test_removes_directory(self):
        saved = segment_library.save_segment(
            b"RIFF....", text="hi", instruct="female", engine="omnivoice", sample_rate=24000
        )
        assert segment_library.delete_segment(saved["segment_id"]) is True
        assert not (segment_library.SEGMENT_LIBRARY_DIR / saved["segment_id"]).exists()
        assert segment_library.delete_segment(saved["segment_id"]) is False


class TestList:
    def test_newest_first(self):
        first = segment_library.save_segment(
            b"1", text="one", instruct="female", engine="omnivoice", sample_rate=24000
        )
        second = segment_library.save_segment(
            b"2", text="two", instruct="male", engine="omnivoice", sample_rate=24000
        )
        listed = segment_library.list_segments()
        assert [m["segment_id"] for m in listed] == [second["segment_id"], first["segment_id"]]

    def test_skips_corrupt_meta(self):
        bad_dir = segment_library.SEGMENT_LIBRARY_DIR / "seg_deadbeef0000"
        bad_dir.mkdir()
        (bad_dir / "meta.json").write_text("not json")
        assert segment_library.list_segments() == []

    def test_empty_when_missing(self):
        segment_library.SEGMENT_LIBRARY_DIR = segment_library.SEGMENT_LIBRARY_DIR / "does-not-exist"
        assert segment_library.list_segments() == []


class TestExtraMetadata:
    def test_persists_all_extra_fields(self):
        meta = segment_library.save_segment(
            b"RIFF....",
            text="hi",
            instruct="female",
            engine="omnivoice",
            sample_rate=24000,
            accent_id="au",
            language="english",
            seed=42,
            num_step=32,
            speed=1.1,
            guidance_scale=2.5,
            diverse_candidates=True,
            postprocess_output=False,
            duration_target=2.4,
            candidate_id="cand_abc",
            job_id="job_xyz",
            whisper_transcript="hi there",
            match_score=0.94,
            duration_sec=2.37,
        )
        assert meta["language"] == "english"
        assert meta["seed"] == 42
        assert meta["num_step"] == 32
        assert meta["speed"] == 1.1
        assert meta["guidance_scale"] == 2.5
        assert meta["diverse_candidates"] is True
        assert meta["postprocess_output"] is False
        assert meta["duration_target"] == 2.4
        assert meta["candidate_id"] == "cand_abc"
        assert meta["job_id"] == "job_xyz"
        assert meta["whisper_transcript"] == "hi there"
        assert meta["match_score"] == 0.94
        assert meta["duration_sec"] == 2.37
