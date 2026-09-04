"""Test the native filesystem contract (docs/plans/20260829-no_more_docker_architecture.md §4).

Every resolver must be pure (no I/O, no fallback to real os.environ/Path.home() unless the
test deliberately omits an override) — these tests pass explicit environ dicts and platform/
home overrides throughout rather than mutating process state.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from persona_forge import paths


LINUX_HOME = Path("/home/nick")
MAC_HOME = Path("/Users/nick")
WIN_HOME = Path("C:/Users/nick")


class TestAppDataRoot:
    def test_explicit_root_wins_on_every_platform(self):
        environ = {"PERSONA_FORGE_HOME": "/srv/persona-forge"}
        for plat in ("linux", "darwin", "win32"):
            assert paths.app_data_root(environ, platform=plat, home=LINUX_HOME) == Path(
                "/srv/persona-forge"
            )

    def test_rejects_filesystem_root(self):
        with pytest.raises(ValueError, match="filesystem root"):
            paths.app_data_root({"PERSONA_FORGE_HOME": "/"}, platform="linux", home=LINUX_HOME)

    def test_expands_tilde(self):
        result = paths.app_data_root(
            {"PERSONA_FORGE_HOME": "~/custom-state"}, platform="linux", home=LINUX_HOME
        )
        assert result == LINUX_HOME / "custom-state"

    def test_linux_xdg_data_home(self):
        environ = {"XDG_DATA_HOME": "/home/nick/.xdg-data"}
        result = paths.app_data_root(environ, platform="linux", home=LINUX_HOME)
        assert result == Path("/home/nick/.xdg-data/persona-forge")

    def test_linux_default_no_xdg(self):
        result = paths.app_data_root({}, platform="linux", home=LINUX_HOME)
        assert result == LINUX_HOME / ".local" / "share" / "persona-forge"

    def test_macos_default(self):
        result = paths.app_data_root({}, platform="darwin", home=MAC_HOME)
        assert result == MAC_HOME / "Library" / "Application Support" / "persona-forge"

    def test_windows_local_appdata(self):
        environ = {"LOCALAPPDATA": "C:/Users/nick/AppData/Local"}
        result = paths.app_data_root(environ, platform="win32", home=WIN_HOME)
        assert result == Path("C:/Users/nick/AppData/Local/persona-forge")

    def test_windows_default_no_localappdata(self):
        result = paths.app_data_root({}, platform="win32", home=WIN_HOME)
        assert result == WIN_HOME / "AppData" / "Local" / "persona-forge"

    def test_never_reads_real_environ_or_home(self, monkeypatch):
        monkeypatch.setenv("PERSONA_FORGE_HOME", "/should-not-be-used")
        monkeypatch.setenv("XDG_DATA_HOME", "/should-not-be-used-either")
        result = paths.app_data_root({}, platform="linux", home=LINUX_HOME)
        assert result == LINUX_HOME / ".local" / "share" / "persona-forge"


ROOT = Path("/state/persona-forge")


class TestModelCacheDir:
    def test_default(self):
        assert paths.model_cache_dir({}, root=ROOT) == ROOT / "models" / "huggingface" / "hub"

    @pytest.mark.parametrize(
        "key", ["MODEL_CACHE_DIR", "HF_HUB_CACHE", "MODEL_CACHE_CONTAINER_PATH", "MODEL_CACHE_PATH"]
    )
    def test_each_alias(self, key):
        environ = {key: f"/custom/{key}"}
        assert paths.model_cache_dir(environ, root=ROOT) == Path(f"/custom/{key}")

    def test_precedence_order(self):
        environ = {
            "MODEL_CACHE_DIR": "/a",
            "HF_HUB_CACHE": "/b",
            "MODEL_CACHE_CONTAINER_PATH": "/c",
            "MODEL_CACHE_PATH": "/d",
        }
        assert paths.model_cache_dir(environ, root=ROOT) == Path("/a")

    def test_hf_home_fallback_before_local_default(self):
        environ = {"HF_HOME": "/hf-home"}
        assert paths.model_cache_dir(environ, root=ROOT) == Path("/hf-home/hub")

    def test_injected_mapping_ignores_real_environ(self, monkeypatch):
        monkeypatch.setenv("MODEL_CACHE_DIR", "/should-not-leak")
        assert paths.model_cache_dir({}, root=ROOT) == ROOT / "models" / "huggingface" / "hub"


class TestPocketTtsArtifactDir:
    def test_default_under_model_cache(self):
        model_cache = Path("/state/models/hub")
        assert paths.pocket_tts_artifact_dir({}, model_cache=model_cache) == model_cache / "pocket-tts"

    def test_explicit_override(self):
        environ = {"POCKET_TTS_ARTIFACT_DIR": "/custom/pocket"}
        assert paths.pocket_tts_artifact_dir(environ, model_cache=Path("/ignored")) == Path(
            "/custom/pocket"
        )

    def test_blank_falls_through_to_default(self):
        environ = {"POCKET_TTS_ARTIFACT_DIR": ""}
        model_cache = Path("/state/models/hub")
        assert paths.pocket_tts_artifact_dir(environ, model_cache=model_cache) == model_cache / "pocket-tts"


class TestOvRoot:
    def test_default(self):
        assert paths.ov_root({}, root=ROOT) == ROOT / "ov"

    def test_override(self):
        assert paths.ov_root({"OV_DATA_DIR": "/ov-elsewhere"}, root=ROOT) == Path("/ov-elsewhere")

    def test_container_default_matches_docker(self):
        assert paths.ov_root({"OV_DATA_DIR": "/ov"}, root=ROOT) == Path("/ov")


class TestVoiceLibraryDir:
    def test_default(self):
        assert paths.voice_library_dir({}, root=ROOT) == ROOT / "voices"

    def test_override(self):
        assert paths.voice_library_dir({"VOICE_LIBRARY_DIR": "/voices"}, root=ROOT) == Path("/voices")


class TestSegmentLibraryDir:
    def test_default(self):
        assert paths.segment_library_dir({}, root=ROOT) == ROOT / "segments"

    def test_override(self):
        assert paths.segment_library_dir({"SEGMENT_LIBRARY_DIR": "/segments"}, root=ROOT) == Path(
            "/segments"
        )


class TestRuntimeDataDir:
    def test_default_is_voice_library(self):
        voice_lib = Path("/state/voices")
        assert paths.runtime_data_dir({}, voice_library=voice_lib) == voice_lib

    def test_data_dir_wins_over_everything(self):
        environ = {
            "DATA_DIR": "/data",
            "VOICE_LIBRARY_DIR": "/voices",
            "VOICE_LIBRARY_PATH_CONTAINER": "/voices-legacy",
        }
        assert paths.runtime_data_dir(environ, voice_library=Path("/ignored")) == Path("/data")

    def test_voice_library_dir_wins_over_legacy_container_alias(self):
        environ = {"VOICE_LIBRARY_DIR": "/voices", "VOICE_LIBRARY_PATH_CONTAINER": "/voices-legacy"}
        assert paths.runtime_data_dir(environ, voice_library=Path("/ignored")) == Path("/voices")

    def test_legacy_container_alias_used_when_nothing_else_set(self):
        environ = {"VOICE_LIBRARY_PATH_CONTAINER": "/voices-legacy"}
        assert paths.runtime_data_dir(environ, voice_library=Path("/ignored")) == Path("/voices-legacy")


class TestReferenceAudioPath:
    def test_default(self):
        assert paths.reference_audio_path({}, root=ROOT) == ROOT / "reference.wav"

    def test_container_default_matches_docker(self):
        assert paths.reference_audio_path({"REF_AUDIO": "/voice/reference.wav"}, root=ROOT) == Path(
            "/voice/reference.wav"
        )


class TestHfTokenFile:
    def test_default(self):
        assert paths.hf_token_file({}, root=ROOT) == ROOT / ".hf_token"

    def test_container_default_matches_docker(self):
        assert paths.hf_token_file({"HF_TOKEN_FILE": "/app/.hf_token"}, root=ROOT) == Path(
            "/app/.hf_token"
        )


class TestOvCacheDir:
    def test_unset_defaults_under_ov_root(self):
        ov_data_root = Path("/state/ov")
        assert paths.ov_cache_dir({}, ov_data_root=ov_data_root) == ov_data_root / "cache"

    def test_explicit_blank_disables(self):
        assert paths.ov_cache_dir({"OV_CACHE_DIR": ""}, ov_data_root=Path("/state/ov")) is None

    def test_explicit_blank_with_whitespace_disables(self):
        assert paths.ov_cache_dir({"OV_CACHE_DIR": "   "}, ov_data_root=Path("/state/ov")) is None

    def test_explicit_value_wins(self):
        environ = {"OV_CACHE_DIR": "/custom/ov-cache"}
        assert paths.ov_cache_dir(environ, ov_data_root=Path("/state/ov")) == Path("/custom/ov-cache")

    def test_container_default_matches_docker(self):
        environ = {"OV_CACHE_DIR": "/ov/cache"}
        assert paths.ov_cache_dir(environ, ov_data_root=Path("/ov")) == Path("/ov/cache")


class TestDescribePaths:
    def test_disabled_cache_serializes_as_json_null(self):
        environ = {"PERSONA_FORGE_HOME": "/state", "OV_CACHE_DIR": ""}
        result = paths.describe_paths(environ, platform="linux", home=LINUX_HOME)
        assert result["ov_cache_dir"] is None

    def test_all_keys_present_and_stringified(self):
        environ = {"PERSONA_FORGE_HOME": "/state"}
        result = paths.describe_paths(environ, platform="linux", home=LINUX_HOME)
        expected_keys = {
            "app_data_root",
            "model_cache_dir",
            "pocket_tts_artifact_dir",
            "ov_root",
            "voice_library_dir",
            "segment_library_dir",
            "runtime_data_dir",
            "reference_audio_path",
            "hf_token_file",
            "ov_cache_dir",
        }
        assert set(result) == expected_keys
        for key, value in result.items():
            if key == "ov_cache_dir":
                continue
            assert isinstance(value, str)

    def test_never_touches_filesystem(self, tmp_path):
        # A path that does not exist must not raise or get created.
        missing_root = tmp_path / "does-not-exist-yet"
        environ = {"PERSONA_FORGE_HOME": str(missing_root)}
        paths.describe_paths(environ, platform="linux", home=LINUX_HOME)
        assert not missing_root.exists()

    def test_docker_container_paths_reproduced_exactly(self):
        """The exact env vars Docker sets must resolve to the exact container paths."""
        environ = {
            "MODEL_CACHE_CONTAINER_PATH": "/root/.cache/huggingface/hub",
            "OV_DATA_DIR": "/ov",
            "VOICE_LIBRARY_DIR": "/voices",
            "SEGMENT_LIBRARY_DIR": "/segments",
            "REF_AUDIO": "/voice/reference.wav",
            "HF_TOKEN_FILE": "/app/.hf_token",
            "OV_CACHE_DIR": "/ov/cache",
        }
        result = paths.describe_paths(environ, platform="linux", home=LINUX_HOME)
        assert result["model_cache_dir"] == "/root/.cache/huggingface/hub"
        assert result["ov_root"] == "/ov"
        assert result["voice_library_dir"] == "/voices"
        assert result["segment_library_dir"] == "/segments"
        assert result["reference_audio_path"] == "/voice/reference.wav"
        assert result["hf_token_file"] == "/app/.hf_token"
        assert result["ov_cache_dir"] == "/ov/cache"


class TestEnsureWritableDirs:
    def test_creates_state_dirs_not_files(self, tmp_path):
        environ = {"PERSONA_FORGE_HOME": str(tmp_path / "root")}
        created = paths.ensure_writable_dirs(environ, platform="linux", home=LINUX_HOME)
        for directory in created:
            assert directory.is_dir()
        ref_audio = paths.reference_audio_path(environ, platform="linux", home=LINUX_HOME)
        token_file = paths.hf_token_file(environ, platform="linux", home=LINUX_HOME)
        assert not ref_audio.exists()
        assert not token_file.exists()

    def test_disabled_ov_cache_not_created(self, tmp_path):
        environ = {"PERSONA_FORGE_HOME": str(tmp_path / "root"), "OV_CACHE_DIR": ""}
        created = paths.ensure_writable_dirs(environ, platform="linux", home=LINUX_HOME)
        ov_root = paths.ov_root(environ, platform="linux", home=LINUX_HOME)
        assert not (ov_root / "cache").exists()
        assert ov_root in created

    def test_deduplicates_shared_dirs(self, tmp_path):
        # runtime_data_dir defaults to voice_library_dir; must not be created/mkdir'd twice
        # (mkdir with exist_ok=True wouldn't fail, but the dedup contract is still worth pinning).
        environ = {"PERSONA_FORGE_HOME": str(tmp_path / "root")}
        created = paths.ensure_writable_dirs(environ, platform="linux", home=LINUX_HOME)
        assert len(created) == len(set(created))
