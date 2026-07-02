from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from qwen3_tts import voice_library


class VoiceLibraryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp())
        self._orig_dir = voice_library.VOICE_LIBRARY_DIR
        voice_library.VOICE_LIBRARY_DIR = self._tmpdir

    def tearDown(self) -> None:
        voice_library.VOICE_LIBRARY_DIR = self._orig_dir
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_save_voice_persists_wav_and_metadata(self) -> None:
        meta = voice_library.save_voice(
            b"RIFF....", description="a calm narrator", sample_text="hello there", language="English"
        )

        self.assertTrue(meta["voice_id"].startswith("vd_"))
        self.assertEqual(meta["description"], "a calm narrator")
        self.assertEqual(meta["sample_text"], "hello there")
        self.assertEqual(meta["language"], "English")
        self.assertTrue((self._tmpdir / meta["voice_id"] / "reference.wav").is_file())
        self.assertTrue((self._tmpdir / meta["voice_id"] / "meta.json").is_file())

    def test_get_voice_round_trips_saved_metadata(self) -> None:
        saved = voice_library.save_voice(
            b"RIFF....", description="desc", sample_text="text", language="English"
        )

        fetched = voice_library.get_voice(saved["voice_id"])

        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched["voice_id"], saved["voice_id"])
        self.assertEqual(fetched["wav_path"], str(self._tmpdir / saved["voice_id"] / "reference.wav"))

    def test_get_voice_returns_none_for_unknown_id(self) -> None:
        self.assertIsNone(voice_library.get_voice("vd_000000000000"))

    def test_get_voice_rejects_path_traversal_attempts(self) -> None:
        self.assertIsNone(voice_library.get_voice("../../etc/passwd"))
        self.assertIsNone(voice_library.get_voice("vd_..%2f..%2fetc"))

    def test_get_voice_wav_bytes_returns_saved_bytes(self) -> None:
        saved = voice_library.save_voice(
            b"RIFF-payload", description="desc", sample_text="text", language="English"
        )

        self.assertEqual(voice_library.get_voice_wav_bytes(saved["voice_id"]), b"RIFF-payload")

    def test_list_voices_returns_newest_first(self) -> None:
        first = voice_library.save_voice(
            b"a", description="first", sample_text="text", language="English"
        )
        first_meta_path = self._tmpdir / first["voice_id"] / "meta.json"
        # Force a distinguishable created_at ordering without depending on wall-clock timing.
        import json

        data = json.loads(first_meta_path.read_text())
        data["created_at"] = 1.0
        first_meta_path.write_text(json.dumps(data))

        second = voice_library.save_voice(
            b"b", description="second", sample_text="text", language="English"
        )
        second_meta_path = self._tmpdir / second["voice_id"] / "meta.json"
        data = json.loads(second_meta_path.read_text())
        data["created_at"] = 2.0
        second_meta_path.write_text(json.dumps(data))

        voices = voice_library.list_voices()

        self.assertEqual([v["voice_id"] for v in voices], [second["voice_id"], first["voice_id"]])

    def test_list_voices_returns_empty_list_when_directory_missing(self) -> None:
        voice_library.VOICE_LIBRARY_DIR = self._tmpdir / "does-not-exist"

        self.assertEqual(voice_library.list_voices(), [])


if __name__ == "__main__":
    unittest.main()
