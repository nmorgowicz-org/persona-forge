"""Test scripts/inspect_release_artifacts.py: the Phase 6 fail-closed wheel/sdist inspector."""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts.inspect_release_artifacts import (
    _find,
    _forbidden_present,
    _required_missing,
    _sdist_members,
    _sha256,
    _wheel_members,
    main,
)


def _make_wheel(path: Path, members: list[str]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for member in members:
            zf.writestr(member, "content")


def _make_sdist(path: Path, root: str, members: list[str]) -> None:
    with tarfile.open(path, "w:gz") as tf:
        for member in members:
            import io

            data = b"content"
            info = tarfile.TarInfo(name=f"{root}/{member}")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))


WHEEL_REQUIRED = [
    "persona_forge/cli.py",
    "persona_forge/bootstrap.py",
    "persona_forge/paths.py",
    "persona_forge/frontend.py",
    "persona_forge/config.py",
    "persona_forge/gpu_family.py",
    "persona_forge/device.py",
    "persona_forge/compat_patch.py",
    "persona_forge/static/index.html",
    "*.dist-info/METADATA",
]
SDIST_REQUIRED = [
    "pyproject.toml",
    "hatch_build.py",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/index.html",
    "frontend/src/main.tsx",
    "src/persona_forge/cli.py",
]


class TestSha256:
    def test_matches_known_digest(self, tmp_path):
        path = tmp_path / "f.txt"
        path.write_bytes(b"hello world")
        assert _sha256(path) == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"


class TestMembers:
    def test_wheel_members_lists_zip_namelist(self, tmp_path):
        wheel = tmp_path / "pkg.whl"
        _make_wheel(wheel, ["a/b.py", "c.txt"])
        assert set(_wheel_members(wheel)) == {"a/b.py", "c.txt"}

    def test_sdist_members_strips_archive_root(self, tmp_path):
        sdist = tmp_path / "pkg.tar.gz"
        _make_sdist(sdist, "persona_forge-1.3.0", ["pyproject.toml", "src/a.py"])
        assert set(_sdist_members(sdist)) == {"pyproject.toml", "src/a.py"}


class TestFind:
    def test_finds_unique_match(self, tmp_path):
        whl = tmp_path / "pkg.whl"
        whl.touch()
        assert _find([whl, tmp_path / "pkg.tar.gz"], ".whl") == whl

    def test_raises_when_not_exactly_one(self, tmp_path):
        with pytest.raises(SystemExit):
            _find([tmp_path / "a.whl", tmp_path / "b.whl"], ".whl")
        with pytest.raises(SystemExit):
            _find([], ".whl")


class TestRequiredMissing:
    def test_exact_and_prefix_and_glob_matches_satisfy(self):
        members = ["persona_forge/cli.py", "abc.dist-info/METADATA", "persona_forge/static/index.html"]
        required = ["persona_forge/cli.py", "*.dist-info/METADATA", "persona_forge/static/index.html"]
        assert _required_missing(members, required) == []

    def test_missing_member_is_reported(self):
        assert _required_missing(["a.py"], ["b.py"]) == ["b.py"]

    def test_missing_glob_is_reported(self):
        assert _required_missing(["a.py"], ["*.dist-info/METADATA"]) == ["*.dist-info/METADATA"]


class TestForbiddenPresent:
    @pytest.mark.parametrize(
        "member",
        [
            "persona_forge/model.bin",
            "persona_forge/ir/model.xml",
            "voice.safetensors",
            "checkpoint.pt",
            "checkpoint.pth",
            "checkpoint.ckpt",
            "sample.wav",
            "sample.mp3",
            "model.onnx",
        ],
    )
    def test_flags_binary_artifact_suffixes(self, member):
        assert _forbidden_present([member], "wheel") == [member]

    def test_flags_hf_token_case_insensitively(self):
        assert _forbidden_present(["config/HF_TOKEN"], "wheel") == ["config/HF_TOKEN"]

    def test_flags_node_modules(self):
        assert _forbidden_present(["frontend/node_modules/x.js"], "sdist") == ["frontend/node_modules/x.js"]

    def test_flags_dotenv(self):
        assert _forbidden_present([".env"], "wheel") == [".env"]
        assert _forbidden_present(["app/.env"], "wheel") == ["app/.env"]

    def test_wheel_bans_uv_lock_tests_and_export_but_sdist_allows_them(self):
        members = ["uv.lock", "tests/test_x.py", "src/export/foo.py"]
        assert _forbidden_present(members, "wheel") == members
        assert _forbidden_present(members, "sdist") == []

    def test_sdist_bans_frontend_dist_and_baked_static_but_wheel_requires_static(self):
        members = ["frontend/dist/index.html", "src/persona_forge/static/index.html"]
        assert _forbidden_present(members, "sdist") == members
        # The wheel legitimately ships the baked static UI - only sdist bans it.
        assert _forbidden_present(["src/persona_forge/static/index.html"], "wheel") == []

    def test_clean_members_pass(self):
        assert _forbidden_present(["persona_forge/cli.py", "pyproject.toml"], "wheel") == []


class TestMainEndToEnd:
    def _build_clean_artifacts(self, dist_dir: Path) -> None:
        dist_dir.mkdir(parents=True, exist_ok=True)
        wheel_members = WHEEL_REQUIRED[:-1] + ["persona_forge-1.3.0.dist-info/METADATA"]
        _make_wheel(dist_dir / "persona_forge-1.3.0-py3-none-any.whl", wheel_members)
        _make_sdist(dist_dir / "persona_forge-1.3.0.tar.gz", "persona_forge-1.3.0", SDIST_REQUIRED)

    def test_passes_on_clean_artifacts(self, tmp_path, capsys):
        dist_dir = tmp_path / "dist"
        self._build_clean_artifacts(dist_dir)

        rc = main(["--dist-dir", str(dist_dir)])

        assert rc == 0
        out = capsys.readouterr().out
        assert '"status": "pass"' in out

    def test_fails_when_dist_dir_missing(self, tmp_path):
        assert main(["--dist-dir", str(tmp_path / "nope")]) == 1

    def test_fails_when_artifacts_missing(self, tmp_path):
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        assert main(["--dist-dir", str(dist_dir)]) == 1

    def test_fails_and_reports_violation_when_wheel_carries_forbidden_member(self, tmp_path, capsys):
        dist_dir = tmp_path / "dist"
        self._build_clean_artifacts(dist_dir)
        # Rebuild the wheel with a forbidden member mixed in.
        wheel_members = WHEEL_REQUIRED[:-1] + ["persona_forge-1.3.0.dist-info/METADATA", "tests/test_x.py"]
        _make_wheel(dist_dir / "persona_forge-1.3.0-py3-none-any.whl", wheel_members)

        rc = main(["--dist-dir", str(dist_dir)])

        assert rc == 1
        out = capsys.readouterr().out
        assert "tests/test_x.py" in out

    def test_writes_receipt_file(self, tmp_path):
        dist_dir = tmp_path / "dist"
        self._build_clean_artifacts(dist_dir)
        receipt_path = tmp_path / "receipt.json"

        main(["--dist-dir", str(dist_dir), "--receipt-out", str(receipt_path)])

        assert receipt_path.is_file()
        assert '"status"' in receipt_path.read_text()
