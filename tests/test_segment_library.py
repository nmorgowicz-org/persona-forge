from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from qwen3_tts import segment_library


class SegmentLibraryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp())
        self._orig_dir = segment_library.SEGMENT_LIBRARY_DIR
        segment_library.SEGMENT_LIBRARY_DIR = self._tmpdir

    def tearDown(self) -> None:
        segment_library.SEGMENT_LIBRARY_DIR = self._orig_dir
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_save_segment_persists_wav_and_metadata_with_parsed_tags(self) -> None:
        meta = segment_library.save_segment(
            b"RIFF....",
            text="G'day, how are you?",
            instruct="female, young adult, high pitch, australian accent",
            engine="omnivoice",
            sample_rate=24000,
            accent_id="au",
        )

        self.assertTrue(meta["segment_id"].startswith("seg_"))
        self.assertEqual(meta["tags"], ["female", "young adult", "high pitch", "australian accent"])
        self.assertEqual(meta["accent_id"], "au")
        self.assertTrue((self._tmpdir / meta["segment_id"] / "clip.wav").is_file())
        self.assertTrue((self._tmpdir / meta["segment_id"] / "meta.json").is_file())

    def test_get_segment_round_trips_saved_metadata(self) -> None:
        saved = segment_library.save_segment(
            b"RIFF....", text="hi", instruct="female", engine="omnivoice", sample_rate=24000
        )

        fetched = segment_library.get_segment(saved["segment_id"])

        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched["segment_id"], saved["segment_id"])
        self.assertEqual(fetched["wav_path"], str(self._tmpdir / saved["segment_id"] / "clip.wav"))

    def test_get_segment_returns_none_for_unknown_id(self) -> None:
        self.assertIsNone(segment_library.get_segment("seg_000000000000"))

    def test_get_segment_rejects_path_traversal_attempts(self) -> None:
        self.assertIsNone(segment_library.get_segment("../../etc/passwd"))
        self.assertIsNone(segment_library.get_segment("seg_..%2f..%2fetc"))

    def test_get_segment_wav_bytes_returns_written_bytes(self) -> None:
        saved = segment_library.save_segment(
            b"RIFF-payload", text="hi", instruct="female", engine="omnivoice", sample_rate=24000
        )

        self.assertEqual(segment_library.get_segment_wav_bytes(saved["segment_id"]), b"RIFF-payload")

    def test_get_segment_wav_bytes_returns_none_for_unknown_id(self) -> None:
        self.assertIsNone(segment_library.get_segment_wav_bytes("seg_000000000000"))

    def test_delete_segment_removes_directory_and_reports_result(self) -> None:
        saved = segment_library.save_segment(
            b"RIFF....", text="hi", instruct="female", engine="omnivoice", sample_rate=24000
        )

        self.assertTrue(segment_library.delete_segment(saved["segment_id"]))
        self.assertFalse((self._tmpdir / saved["segment_id"]).exists())
        self.assertFalse(segment_library.delete_segment(saved["segment_id"]))

    def test_delete_segment_rejects_path_traversal_attempts(self) -> None:
        self.assertFalse(segment_library.delete_segment("../../etc"))

    def test_list_segments_returns_newest_first(self) -> None:
        first = segment_library.save_segment(
            b"1", text="one", instruct="female", engine="omnivoice", sample_rate=24000
        )
        first_dir = self._tmpdir / first["segment_id"]
        (first_dir / "meta.json").write_text(
            (first_dir / "meta.json").read_text().replace(
                str(first["created_at"]), str(first["created_at"] - 1000)
            )
        )
        second = segment_library.save_segment(
            b"2", text="two", instruct="male", engine="omnivoice", sample_rate=24000
        )

        listed = segment_library.list_segments()

        self.assertEqual([m["segment_id"] for m in listed], [second["segment_id"], first["segment_id"]])

    def test_list_segments_skips_corrupt_entries(self) -> None:
        bad_dir = self._tmpdir / "seg_deadbeef0000"
        bad_dir.mkdir(parents=True)
        (bad_dir / "meta.json").write_text("not json")

        self.assertEqual(segment_library.list_segments(), [])

    def test_list_segments_empty_when_dir_missing(self) -> None:
        segment_library.SEGMENT_LIBRARY_DIR = self._tmpdir / "does-not-exist"

        self.assertEqual(segment_library.list_segments(), [])
