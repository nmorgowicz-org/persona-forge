"""Engine pack manifests and local verification (Phase C3)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from persona_forge import engine_packs


def _payload(**overrides):
    payload = {
        "id": "kokoro-pack",
        "engine_id": "kokoro",
        "version": "0.4.1",
        "label": "Kokoro 82M",
        "description": "CPU TTS",
        "runtime": "python-onnx",
        "requirements": ["kokoro-onnx==0.4.1"],
        "artifacts": [{"path": "model.onnx", "sha256": "0" * 64, "size": 3}],
    }
    payload.update(overrides)
    return payload


def _write_pack(root: Path, payload: dict, files: dict[str, bytes]) -> Path:
    pack_dir = root / payload["id"]
    pack_dir.mkdir(parents=True)
    (pack_dir / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    for name, data in files.items():
        (pack_dir / name).write_bytes(data)
    return pack_dir


def test_parse_manifest_accepts_valid_payload():
    manifest = engine_packs.parse_manifest(_payload())

    assert manifest.id == "kokoro-pack"
    assert manifest.engine_id == "kokoro"
    assert manifest.artifacts[0].path == "model.onnx"
    assert manifest.requirements == ("kokoro-onnx==0.4.1",)


@pytest.mark.parametrize("path", ["../outside.bin", "/etc/passwd", "nested/../../out.bin"])
def test_artifact_paths_must_stay_inside_the_pack(path):
    with pytest.raises(engine_packs.PackManifestError):
        engine_packs.parse_manifest(
            _payload(artifacts=[{"path": path, "sha256": "0" * 64, "size": 1}])
        )


def test_manifest_rejects_bad_sha_and_size():
    with pytest.raises(engine_packs.PackManifestError):
        engine_packs.parse_manifest(
            _payload(artifacts=[{"path": "m.bin", "sha256": "nope", "size": 1}])
        )
    with pytest.raises(engine_packs.PackManifestError):
        engine_packs.parse_manifest(
            _payload(artifacts=[{"path": "m.bin", "sha256": "0" * 64, "size": -1}])
        )


def test_verification_accepts_matching_artifact(tmp_path):
    data = b"abc"
    payload = _payload(
        artifacts=[
            {"path": "model.onnx", "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        ]
    )
    pack_dir = _write_pack(tmp_path, payload, {"model.onnx": data})

    status = engine_packs.inspect_pack(pack_dir, verify=True)

    assert status.status == "verified"
    assert status.verified is True
    assert status.artifacts_present == 1
    assert status.disk_bytes == 3
    assert (pack_dir / engine_packs.VERIFIED_FILENAME).is_file()


def test_verification_rejects_tampered_artifact(tmp_path):
    data = b"abc"
    payload = _payload(
        artifacts=[
            {"path": "model.onnx", "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        ]
    )
    pack_dir = _write_pack(tmp_path, payload, {"model.onnx": data})
    engine_packs.inspect_pack(pack_dir, verify=True)
    (pack_dir / "model.onnx").write_bytes(b"abd")

    status = engine_packs.inspect_pack(pack_dir, verify=True)

    assert status.verified is False
    assert status.status == "invalid"
    assert any("hash mismatch" in error for error in status.errors)


def test_missing_artifact_is_not_installed(tmp_path):
    payload = _payload()
    pack_dir = _write_pack(tmp_path, payload, {})

    status = engine_packs.inspect_pack(pack_dir)

    assert status.status == "not-installed"
    assert status.artifacts_present == 0


def test_discover_skips_directories_without_manifest(tmp_path):
    _write_pack(tmp_path, _payload(), {})
    (tmp_path / "loose-dir").mkdir()

    packs = engine_packs.discover_packs(tmp_path)

    assert [pack.pack.id for pack in packs] == ["kokoro-pack"]


def test_install_from_file_source(tmp_path):
    data = b"model-bytes"
    source = tmp_path / "source.bin"
    source.write_bytes(data)
    payload = _payload(
        engine_id="installed-engine",
        artifacts=[
            {
                "path": "model.onnx",
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
                "source": source.as_uri(),
            }
        ],
    )
    packs_root = tmp_path / "packs"
    pack_dir = _write_pack(packs_root, payload, {})

    status = engine_packs.install_pack("installed-engine", packs_root, allow_file=True)

    assert status.status == "verified"
    assert (pack_dir / "model.onnx").read_bytes() == data
    assert not (pack_dir / "model.onnx.part").exists()


def test_install_rejects_hash_mismatch(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"actual-bytes")
    payload = _payload(
        engine_id="bad-engine",
        artifacts=[
            {
                "path": "model.onnx",
                "sha256": hashlib.sha256(b"expected-bytes").hexdigest(),
                "size": len(b"actual-bytes"),
                "source": source.as_uri(),
            }
        ],
    )
    packs_root = tmp_path / "packs"
    pack_dir = _write_pack(packs_root, payload, {})

    with pytest.raises(engine_packs.PackInstallError):
        engine_packs.install_pack("bad-engine", packs_root, allow_file=True)

    assert not (pack_dir / "model.onnx").exists()
    assert not (pack_dir / "model.onnx.part").exists()


def test_install_rejects_file_sources_when_disabled(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"data")
    payload = _payload(
        engine_id="file-engine",
        artifacts=[
            {
                "path": "model.onnx",
                "sha256": hashlib.sha256(b"data").hexdigest(),
                "size": 4,
                "source": source.as_uri(),
            }
        ],
    )
    packs_root = tmp_path / "packs"
    _write_pack(packs_root, payload, {})

    with pytest.raises(engine_packs.PackInstallError):
        engine_packs.install_pack("file-engine", packs_root, allow_file=False)


def test_remove_pack_deletes_directory(tmp_path):
    pack_dir = _write_pack(tmp_path, _payload(engine_id="removable"), {})

    assert engine_packs.remove_pack("removable", tmp_path) is True
    assert not pack_dir.exists()
    assert engine_packs.remove_pack("removable", tmp_path) is False


def test_engine_cards_include_the_builtin_engine(tmp_path):
    cards = {card["id"]: card for card in engine_packs.engine_cards("pocket_tts", tmp_path)}

    assert cards["pocket-tts"]["kind"] == "builtin"
    assert cards["pocket-tts"]["state"]["status"] == "built-in"
    assert cards["pocket-tts"]["active"] is True


def test_pack_for_registered_engine_merges_into_its_card(tmp_path):
    payload = _payload(engine_id="pocket-tts")
    _write_pack(tmp_path, payload, {})

    cards = {card["id"]: card for card in engine_packs.engine_cards("pocket_tts", tmp_path)}

    assert cards["pocket-tts"]["kind"] == "builtin+pack"
    assert cards["pocket-tts"]["state"]["status"] == "not-installed"
    assert cards["pocket-tts"]["version"] == "0.4.1"
