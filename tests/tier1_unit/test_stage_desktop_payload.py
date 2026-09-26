"""Test scripts/stage_desktop_payload.py: the Phase 3 desktop payload stager.

Same subprocess-fake convention as test_package_launcher_archive.py (never invokes real `uv`).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import scripts.package_launcher_archive as pla
import scripts.stage_desktop_payload as sdp


def _fake_uv_pip_compile_ok(cmd, capture_output=True, text=True, env=None):
    out_path = Path(cmd[cmd.index("-o") + 1])
    out_path.write_text("persona-forge==2.1.4\n", encoding="utf-8")
    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


@pytest.fixture
def inputs(tmp_path: Path) -> dict[str, Path]:
    uv_bin = tmp_path / "uv"
    uv_bin.write_bytes(b"fake-uv-binary")
    wheel = tmp_path / "persona_forge-2.1.4-py3-none-any.whl"
    wheel.write_bytes(b"fake-wheel-bytes")
    return {"uv": uv_bin, "wheel": wheel}


def test_missing_wheel_fails_closed(tmp_path: Path, inputs: dict[str, Path]) -> None:
    code = sdp.main(
        [
            "--target", "x86_64-unknown-linux-gnu",
            "--version", "2.1.4",
            "--wheel", str(tmp_path / "missing.whl"),
            "--uv-binary", str(inputs["uv"]),
            "--uv-version", "0.12.9",
            "--out-root", str(tmp_path / "desktop"),
        ]
    )
    assert code == 1


def test_missing_uv_binary_fails_closed(tmp_path: Path, inputs: dict[str, Path]) -> None:
    code = sdp.main(
        [
            "--target", "x86_64-unknown-linux-gnu",
            "--version", "2.1.4",
            "--wheel", str(inputs["wheel"]),
            "--uv-binary", str(tmp_path / "missing-uv"),
            "--uv-version", "0.12.9",
            "--out-root", str(tmp_path / "desktop"),
        ]
    )
    assert code == 1


@pytest.mark.parametrize(
    "target,uv_suffix",
    [
        ("aarch64-apple-darwin", ""),
        ("x86_64-pc-windows-msvc", ".exe"),
        ("x86_64-unknown-linux-gnu", ""),
    ],
)
def test_stages_real_payload_with_expected_members(
    tmp_path: Path, inputs: dict[str, Path], monkeypatch: pytest.MonkeyPatch, target: str, uv_suffix: str
) -> None:
    monkeypatch.setattr(sdp.pla.subprocess, "run", _fake_uv_pip_compile_ok)
    out_root = tmp_path / "desktop"

    code = sdp.main(
        [
            "--target", target,
            "--version", "2.1.4",
            "--wheel", str(inputs["wheel"]),
            "--uv-binary", str(inputs["uv"]),
            "--uv-version", "0.12.9",
            "--out-root", str(out_root),
        ]
    )
    assert code == 0

    payload_dir = out_root / "payload"
    binaries_dir = out_root / "binaries"
    assert (payload_dir / inputs["wheel"].name).is_file()
    assert (payload_dir / f"requirements-{target}.txt").is_file()
    uv_name = f"uv-{target}{uv_suffix}"
    assert (binaries_dir / uv_name).is_file()

    manifest = json.loads((payload_dir / "manifest.json").read_text())
    assert manifest["schema_version"] == 1
    assert manifest["version"] == "2.1.4"
    assert manifest["target"] == target
    assert manifest["wheel"]["sha256"] == pla.sha256_file(payload_dir / inputs["wheel"].name)
    assert manifest["uv"]["sha256"] == pla.sha256_file(binaries_dir / uv_name)
    assert manifest["uv"]["sha256"] != sdp.FAKE_SHA256


def test_fake_never_invokes_uv_pip_compile(tmp_path: Path, inputs: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*a, **k):
        raise AssertionError("--fake must never invoke uv pip compile")

    monkeypatch.setattr(sdp.pla.subprocess, "run", _boom)
    out_root = tmp_path / "desktop"

    code = sdp.main(
        [
            "--target", "x86_64-unknown-linux-gnu",
            "--version", "2.1.4",
            "--wheel", str(tmp_path / "does-not-need-to-exist.whl"),
            "--uv-binary", str(tmp_path / "does-not-need-to-exist-uv"),
            "--uv-version", "0.12.9",
            "--out-root", str(out_root),
            "--fake",
        ]
    )
    assert code == 0

    manifest = json.loads((out_root / "payload" / "manifest.json").read_text())
    assert manifest["wheel"]["sha256"] == sdp.FAKE_SHA256
    assert manifest["uv"]["sha256"] == sdp.FAKE_SHA256
    assert manifest["requirements_sha256"] == sdp.FAKE_SHA256
    # --fake still writes real (placeholder) files at the documented paths, so the desktop
    # crate's resource-dir wiring can be exercised in CI without a real wheel/uv/network.
    assert (out_root / "payload" / "does-not-need-to-exist.whl").is_file()
    assert (out_root / "binaries" / "uv-x86_64-unknown-linux-gnu").is_file()


def test_desktop_targets_reuses_package_launcher_archive_python_platform_values() -> None:
    assert sdp.DESKTOP_TARGETS["aarch64-apple-darwin"] == pla.TARGETS["aarch64-apple-darwin"][2]
    assert sdp.DESKTOP_TARGETS["x86_64-unknown-linux-gnu"] == pla.TARGETS["x86_64-unknown-linux-gnu"][2]
    # MSVC maps to the same --python-platform value as the existing GNU entry (no new TARGETS key).
    assert sdp.DESKTOP_TARGETS["x86_64-pc-windows-msvc"] == pla.TARGETS["x86_64-pc-windows-gnu"][2]
    assert "x86_64-pc-windows-msvc" not in pla.TARGETS
