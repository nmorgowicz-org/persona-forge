"""Test scripts/package_launcher_archive.py: the Phase 7 launcher-archive assembler.

Archive assembly tests fake resolution; the standalone-requirements regression uses
real uv against isolated local wheel indexes, with no network or accelerator hardware.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import replace
from importlib.metadata import distributions
from pathlib import Path

import pytest

import scripts.package_launcher_archive as pla


def _fake_uv_pip_compile_ok(cmd, capture_output=True, text=True, env=None):
    out_path = Path(cmd[cmd.index("-o") + 1])
    out_path.write_text("persona-forge==1.3.0\n", encoding="utf-8")
    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


def _fake_uv_pip_compile_fails(cmd, capture_output=True, text=True, env=None):
    return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="no solution found")


@pytest.fixture
def inputs(tmp_path: Path) -> dict[str, Path]:
    launcher = tmp_path / "persona-forge-launcher"
    launcher.write_bytes(b"stub-launcher")
    uv_bin = tmp_path / "uv"
    uv_bin.write_bytes(b"stub-uv")
    wheel = tmp_path / "persona_forge-1.3.0-py3-none-any.whl"
    wheel.write_bytes(b"stub-wheel")
    return {"launcher": launcher, "uv": uv_bin, "wheel": wheel}


def test_missing_launcher_binary_fails_closed(tmp_path: Path, inputs: dict[str, Path]) -> None:
    code = pla.main(
        [
            "--target", "x86_64-unknown-linux-gnu",
            "--version", "1.3.0",
            "--launcher-binary", str(tmp_path / "does-not-exist"),
            "--uv-binary", str(inputs["uv"]),
            "--uv-version", "0.12.9",
            "--wheel", str(inputs["wheel"]),
            "--out-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 1


def test_missing_wheel_fails_closed(tmp_path: Path, inputs: dict[str, Path]) -> None:
    code = pla.main(
        [
            "--target", "x86_64-unknown-linux-gnu",
            "--version", "1.3.0",
            "--launcher-binary", str(inputs["launcher"]),
            "--uv-binary", str(inputs["uv"]),
            "--uv-version", "0.12.9",
            "--wheel", str(tmp_path / "does-not-exist.whl"),
            "--out-dir", str(tmp_path / "out"),
        ]
    )
    assert code == 1


def test_uv_pip_compile_failure_raises(tmp_path: Path, inputs: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pla.subprocess, "run", _fake_uv_pip_compile_fails)
    with pytest.raises(SystemExit):
        pla.main(
            [
                "--target", "x86_64-unknown-linux-gnu",
                "--version", "1.3.0",
                "--launcher-binary", str(inputs["launcher"]),
                "--uv-binary", str(inputs["uv"]),
                "--uv-version", "0.12.9",
                "--wheel", str(inputs["wheel"]),
                "--out-dir", str(tmp_path / "out"),
            ]
        )


@pytest.mark.parametrize(
    "target,expected_launcher,expected_uv,archive_suffix",
    [
        ("x86_64-unknown-linux-gnu", "persona-forge-launcher", "uv", ".tar.gz"),
        ("x86_64-pc-windows-gnu", "persona-forge-launcher.exe", "uv.exe", ".zip"),
    ],
)
def test_builds_archive_with_expected_members(
    tmp_path: Path,
    inputs: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    expected_launcher: str,
    expected_uv: str,
    archive_suffix: str,
) -> None:
    monkeypatch.setattr(pla.subprocess, "run", _fake_uv_pip_compile_ok)
    out_dir = tmp_path / "out"

    code = pla.main(
        [
            "--target", target,
            "--version", "1.3.0",
            "--launcher-binary", str(inputs["launcher"]),
            "--uv-binary", str(inputs["uv"]),
            "--uv-version", "0.12.9",
            "--wheel", str(inputs["wheel"]),
            "--out-dir", str(out_dir),
        ]
    )
    assert code == 0

    asset_stem = pla.TARGETS[target][0]
    archive_path = out_dir / f"persona-forge-bootstrap-{asset_stem}{archive_suffix}"
    assert archive_path.is_file()

    if archive_suffix == ".zip":
        with zipfile.ZipFile(archive_path) as zf:
            names = set(zf.namelist())
            manifest = json.loads(zf.read("manifest.json"))
    else:
        with tarfile.open(archive_path, "r:gz") as tf:
            names = {m.name for m in tf.getmembers()}
            manifest_fh = tf.extractfile("manifest.json")
            assert manifest_fh is not None
            manifest = json.loads(manifest_fh.read())

    assert expected_launcher in names
    assert expected_uv in names
    assert inputs["wheel"].name in names
    assert f"requirements-{target}.txt" in names
    assert "README.txt" in names

    assert manifest["schema_version"] == 1
    assert manifest["app"] == "persona-forge"
    assert manifest["version"] == "1.3.0"
    assert manifest["target"] == target
    assert manifest["wheel"]["file"] == inputs["wheel"].name
    assert manifest["uv"]["file"] == expected_uv
    assert manifest["uv"]["version"] == "0.12.9"
    assert manifest["requirements_file"] == f"requirements-{target}.txt"


def test_staging_dir_is_cleaned_up_on_success(tmp_path: Path, inputs: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pla.subprocess, "run", _fake_uv_pip_compile_ok)
    out_dir = tmp_path / "out"

    pla.main(
        [
            "--target", "x86_64-unknown-linux-gnu",
            "--version", "1.3.0",
            "--launcher-binary", str(inputs["launcher"]),
            "--uv-binary", str(inputs["uv"]),
            "--uv-version", "0.12.9",
            "--wheel", str(inputs["wheel"]),
            "--out-dir", str(out_dir),
        ]
    )

    assert not (out_dir / ".staging-x86_64-unknown-linux-gnu").exists()


def _write_index_wheel(index: Path, name: str, version: str, dependencies: tuple[str, ...] = ()) -> None:
    """Create a real, installable pure-Python wheel and its Simple API package page."""
    package_dir = index / name
    package_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{name.replace('-', '_')}-{version}"
    wheel_path = package_dir / f"{stem}-py3-none-any.whl"
    dist_info = f"{stem}.dist-info"
    metadata = (
        f"Metadata-Version: 2.3\nName: {name}\nVersion: {version}\n"
        + "".join(f"Requires-Dist: {dependency}\n" for dependency in dependencies)
        + "\n"
    )
    files = {
        f"{dist_info}/METADATA": metadata.encode(),
        f"{dist_info}/WHEEL": (
            b"Wheel-Version: 1.0\nGenerator: packaging-regression\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
        ),
    }
    record = []
    with zipfile.ZipFile(wheel_path, "w") as wheel:
        for filename, data in files.items():
            wheel.writestr(filename, data)
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            record.append(f"{filename},sha256={digest},{len(data)}\n")
        record.append(f"{dist_info}/RECORD,,\n")
        wheel.writestr(f"{dist_info}/RECORD", "".join(record))
    page = package_dir / "index.html"
    existing = page.read_text(encoding="utf-8") if page.exists() else ""
    page.write_text(existing + f'<a href="{wheel_path.name}">{wheel_path.name}</a>\n', encoding="utf-8")


@pytest.mark.parametrize("extra", [None, "cuda12", "cuda13", "xpu", "rocm"])
def test_export_syncs_selected_wheel_sources_outside_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extra: str | None
) -> None:
    uv = os.environ.get("UV_BINARY") or shutil.which("uv")
    if uv is None:
        pytest.skip("real uv is required for the offline packaging-consumer regression")
    from persona_forge.accelerator_manifest import ACCELERATOR_PINS

    project = tmp_path / "project"
    project.mkdir()
    default_index = tmp_path / "default-index"
    _write_index_wheel(default_index, "torch", "1.0+default")
    _write_index_wheel(default_index, "torchaudio", "1.0+default", ("coredep==2.0",))
    _write_index_wheel(default_index, "coredep", "2.0")
    accelerator_indexes = []
    optional_dependencies = []
    sources: dict[str, list[str]] = {}
    for family, pin in tuple(ACCELERATOR_PINS.items()):
        index = tmp_path / family
        packages = ("torch", "torchaudio", *pin.extra_pins)
        for package in packages:
            _write_index_wheel(index, package, f"1.0+{family}", ("coredep==2.0",))
            sources.setdefault(package, []).append(f'{{ index = "{family}", extra = "{family}" }}')
        # A global accelerator index would shadow the required default-index version.
        _write_index_wheel(index, "coredep", "1.0")
        accelerator_indexes.append(
            f'[[tool.uv.index]]\nname = "{family}"\nurl = "{index.as_uri()}"\nexplicit = true\n'
        )
        optional_dependencies.append(f'{family} = {json.dumps([f"{package}==1.0" for package in packages])}\n')
        monkeypatch.setitem(ACCELERATOR_PINS, family, replace(pin, index_url=index.as_uri()))
    (project / "pyproject.toml").write_text(
        '[project]\nname = "fixture"\nversion = "1.0"\nrequires-python = ">=3.13"\n'
        'dependencies = ["torch==1.0", "torchaudio==1.0", "coredep==2.0"]\n'
        "[project.optional-dependencies]\n"
        + "".join(optional_dependencies)
        + "\n[tool.uv]\nconflicts = [["
        + ", ".join(f'{{ extra = "{family}" }}' for family in ACCELERATOR_PINS)
        + "]]\n"
        + "\n[tool.uv.sources]\n"
        + "".join(f"{package} = [{', '.join(entries)}]\n" for package, entries in sources.items())
        + "\n"
        + "".join(accelerator_indexes),
        encoding="utf-8",
    )
    monkeypatch.chdir(project)
    monkeypatch.setenv("UV_DEFAULT_INDEX", default_index.as_uri())
    monkeypatch.setenv("UV_OFFLINE", "true")
    monkeypatch.setenv("UV_PYTHON_DOWNLOADS", "never")
    monkeypatch.delenv("UV_NO_CONFIG", raising=False)
    requirements = tmp_path / "requirements.txt"
    pla.export_requirements("x86_64-pc-windows-msvc", requirements, uv_path=uv, extra=extra)

    consumer = tmp_path / "consumer"
    consumer.mkdir()
    installed = consumer / "installed"
    env = os.environ.copy()
    env["UV_NO_CONFIG"] = "true"
    result = subprocess.run(
        [uv, "pip", "sync", str(requirements), "--target", str(installed), "--python", sys.executable, "--require-hashes"],
        cwd=consumer,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    installed_versions = {dist.metadata["Name"]: dist.version for dist in distributions(path=[str(installed)])}
    expected = {"torch": f"1.0+{extra or 'default'}", "torchaudio": f"1.0+{extra or 'default'}", "coredep": "2.0"}
    if extra is not None:
        expected.update({package: f"1.0+{extra}" for package in ACCELERATOR_PINS[extra].extra_pins})
    assert installed_versions == expected
