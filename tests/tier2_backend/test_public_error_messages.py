"""Client-facing error text must not carry OS or network detail (CodeQL py/stack-trace-exposure)."""

from __future__ import annotations

import pytest

from persona_forge import engine_packs


def test_remove_failure_hides_the_os_error(tmp_path, monkeypatch):
    pack = tmp_path / "kokoro"
    pack.mkdir()
    monkeypatch.setattr(engine_packs, "find_pack_dir", lambda engine_id, root=None: pack)

    def boom(_path):
        raise OSError("[Errno 13] Permission denied: '/secret/path'")

    monkeypatch.setattr(engine_packs.shutil, "rmtree", boom)

    with pytest.raises(engine_packs.PackInstallError) as caught:
        engine_packs.remove_pack("kokoro", root=tmp_path)

    assert "/secret/path" not in caught.value.public_message
    assert "Permission denied" not in caught.value.public_message
    assert "/secret/path" in str(caught.value)  # the full detail stays available to the log


def test_invalid_manifest_json_is_reported_without_parser_detail(tmp_path):
    (tmp_path / engine_packs.MANIFEST_FILENAME).write_text("{not json")

    with pytest.raises(engine_packs.PackManifestError) as caught:
        engine_packs.load_manifest(tmp_path)

    assert caught.value.public_message == "invalid JSON"
