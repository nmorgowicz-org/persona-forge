"""Phase 3 Tests-first: `uv build` output shape (Task 5/6).

Builds real artifacts via `uv build` (this is what actually exercises hatch_build.py — there is
no way to unit-test a Hatch build hook in isolation) into a scratch directory, then inspects the
wheel and sdist member lists. Marked slow: it shells out to npm (ci/check/build) and uv, so it's
excluded from the default fast run.
"""

from __future__ import annotations

import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_FORBIDDEN_SUBSTRINGS = (
    ".onnx",
    ".safetensors",
    "openvino_model",
    ".wav",
    "hf_token",
)


def _is_forbidden_env_file(name: str) -> bool:
    basename = name.rsplit("/", 1)[-1]
    return basename == ".env" or (basename.startswith(".env.") and "example" not in basename and "sample" not in basename)


@pytest.mark.slow
class TestBuildArtifacts:
    @pytest.fixture(scope="class")
    @classmethod
    def built_dist_dir(cls, tmp_path_factory):
        uv = shutil.which("uv")
        assert uv is not None, "uv not found on PATH"
        out_dir = tmp_path_factory.mktemp("dist")
        result = subprocess.run(
            [uv, "build", "--out-dir", str(out_dir)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return out_dir

    @staticmethod
    def _wheel_path(dist_dir: Path) -> Path:
        wheels = sorted(dist_dir.glob("*.whl"))
        assert wheels, list(dist_dir.iterdir())
        return wheels[0]

    @staticmethod
    def _sdist_path(dist_dir: Path) -> Path:
        sdists = sorted(dist_dir.glob("*.tar.gz"))
        assert sdists, list(dist_dir.iterdir())
        return sdists[0]

    def test_wheel_contains_built_ui_and_no_forbidden_files(self, built_dist_dir):
        with zipfile.ZipFile(self._wheel_path(built_dist_dir)) as wheel:
            names = wheel.namelist()
        static_members = [n for n in names if "persona_forge/static/" in n]
        assert any(n.endswith("static/index.html") for n in static_members), static_members
        assert any("static/assets/" in n for n in static_members), static_members
        hits = [n for n in names if any(f in n.lower() for f in _FORBIDDEN_SUBSTRINGS) or _is_forbidden_env_file(n)]
        assert hits == []

    def test_sdist_contains_frontend_sources_and_lockfile_not_built_dist(self, built_dist_dir):
        with tarfile.open(self._sdist_path(built_dist_dir)) as sdist:
            names = sdist.getnames()
        assert any(n.endswith("frontend/package-lock.json") for n in names), names
        assert any(n.endswith("frontend/package.json") for n in names), names
        assert any(n.endswith("frontend/src/main.tsx") or "/frontend/src/" in n for n in names), names
        assert not any("/frontend/dist/" in n for n in names), [n for n in names if "/frontend/dist/" in n]
        hits = [n for n in names if any(f in n.lower() for f in _FORBIDDEN_SUBSTRINGS) or _is_forbidden_env_file(n)]
        assert hits == []
