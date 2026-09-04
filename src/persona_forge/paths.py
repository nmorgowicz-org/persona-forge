"""Native filesystem contract (docs/plans/20260829-no_more_docker_architecture.md §4).

Every resolver here is a pure function: it accepts an injectable ``environ`` mapping plus
optional ``platform``/``home`` inputs, performs no filesystem I/O, and never falls back to the
real ``os.environ``/``Path.home()`` unless the caller lets the default argument do so. Docker
keeps working unchanged because ``compose.yml``/``Dockerfile`` set the container-side env vars
(``VOICE_LIBRARY_DIR=/voices`` etc.) that these resolvers already treat as highest-precedence
overrides — a native install with none of those vars set is the only path that reaches the
platform-state-root defaults below.

Only :func:`ensure_writable_dirs` performs I/O (directory creation); every other function is
side-effect-free. ``doctor`` must only ever call the pure resolvers/``describe_paths``.
"""

from __future__ import annotations

import os
import sys
from collections.abc import MutableMapping
from pathlib import Path

Environ = MutableMapping[str, str]


def _clean(environ: Environ, key: str) -> str:
    """Return ``environ[key]`` stripped, or "" if unset/blank.

    Blank means "unset" for every resolver here except :func:`ov_cache_dir`, which must
    distinguish "unset" from "explicitly blank" (blank means disabled) — see its docstring.
    """
    return environ.get(key, "").strip()


def _first(environ: Environ, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _clean(environ, key)
        if value:
            return value
    return ""


def _expand(value: str, home: Path) -> Path:
    """Expand a leading ``~`` against the injected ``home`` — never the real ``$HOME``.

    ``Path.expanduser()`` reads the process's actual home directory, which would defeat the
    injectable-``home``-for-tests contract every resolver here promises.
    """
    if value == "~":
        return home
    if value.startswith("~/") or value.startswith("~\\"):
        return home / value[2:]
    return Path(value)


def app_data_root(
    environ: Environ = os.environ,
    *,
    platform: str = sys.platform,
    home: Path | None = None,
) -> Path:
    """Resolve the application-state root: ``PERSONA_FORGE_HOME`` else the platform default.

    Linux: ``$XDG_DATA_HOME/persona-forge`` else ``~/.local/share/persona-forge``.
    macOS: ``~/.config/persona-forge`` (a homedir dotfile, matching Linux/Windows rather than
    the platform's ``~/Library/Application Support`` bundle convention, for cross-platform
    parity).
    Windows: ``%LOCALAPPDATA%/persona-forge`` else ``~/AppData/Local/persona-forge``.
    """
    home = home if home is not None else Path.home()
    override = _clean(environ, "PERSONA_FORGE_HOME")
    if override:
        root = _expand(override, home)
    elif platform.startswith("win"):
        local_appdata = _clean(environ, "LOCALAPPDATA")
        base = Path(local_appdata) if local_appdata else home / "AppData" / "Local"
        root = base / "persona-forge"
    elif platform == "darwin":
        root = home / ".config" / "persona-forge"
    else:
        xdg = _clean(environ, "XDG_DATA_HOME")
        base = Path(xdg) if xdg else home / ".local" / "share"
        root = base / "persona-forge"

    if str(root) == root.anchor:
        raise ValueError(f"PERSONA_FORGE_HOME must not resolve to a filesystem root: {root}")
    return root


def model_cache_dir(
    environ: Environ = os.environ,
    *,
    root: Path | None = None,
    platform: str = sys.platform,
    home: Path | None = None,
) -> Path:
    """``MODEL_CACHE_DIR`` > ``HF_HUB_CACHE`` > ``MODEL_CACHE_CONTAINER_PATH`` >
    ``MODEL_CACHE_PATH`` > ``HF_HOME/hub`` > ``<root>/models/huggingface/hub``."""
    home = home if home is not None else Path.home()
    value = _first(
        environ, ("MODEL_CACHE_DIR", "HF_HUB_CACHE", "MODEL_CACHE_CONTAINER_PATH", "MODEL_CACHE_PATH")
    )
    if value:
        return _expand(value, home)
    hf_home = _clean(environ, "HF_HOME")
    if hf_home:
        return _expand(hf_home, home) / "hub"
    root = root if root is not None else app_data_root(environ, platform=platform, home=home)
    return root / "models" / "huggingface" / "hub"


def pocket_tts_artifact_dir(
    environ: Environ = os.environ,
    *,
    model_cache: Path | None = None,
    root: Path | None = None,
    platform: str = sys.platform,
    home: Path | None = None,
) -> Path:
    """``POCKET_TTS_ARTIFACT_DIR`` else ``<model cache>/pocket-tts``."""
    home = home if home is not None else Path.home()
    value = _clean(environ, "POCKET_TTS_ARTIFACT_DIR")
    if value:
        return _expand(value, home)
    model_cache = (
        model_cache
        if model_cache is not None
        else model_cache_dir(environ, root=root, platform=platform, home=home)
    )
    return model_cache / "pocket-tts"


def ov_root(
    environ: Environ = os.environ,
    *,
    root: Path | None = None,
    platform: str = sys.platform,
    home: Path | None = None,
) -> Path:
    """``OV_DATA_DIR`` else ``<root>/ov``."""
    home = home if home is not None else Path.home()
    value = _clean(environ, "OV_DATA_DIR")
    if value:
        return _expand(value, home)
    root = root if root is not None else app_data_root(environ, platform=platform, home=home)
    return root / "ov"


def voice_library_dir(
    environ: Environ = os.environ,
    *,
    root: Path | None = None,
    platform: str = sys.platform,
    home: Path | None = None,
) -> Path:
    """``VOICE_LIBRARY_DIR`` else ``<root>/voices``."""
    home = home if home is not None else Path.home()
    value = _clean(environ, "VOICE_LIBRARY_DIR")
    if value:
        return _expand(value, home)
    root = root if root is not None else app_data_root(environ, platform=platform, home=home)
    return root / "voices"


def segment_library_dir(
    environ: Environ = os.environ,
    *,
    root: Path | None = None,
    platform: str = sys.platform,
    home: Path | None = None,
) -> Path:
    """``SEGMENT_LIBRARY_DIR`` else ``<root>/segments``."""
    home = home if home is not None else Path.home()
    value = _clean(environ, "SEGMENT_LIBRARY_DIR")
    if value:
        return _expand(value, home)
    root = root if root is not None else app_data_root(environ, platform=platform, home=home)
    return root / "segments"


def runtime_data_dir(
    environ: Environ = os.environ,
    *,
    voice_library: Path | None = None,
    root: Path | None = None,
    platform: str = sys.platform,
    home: Path | None = None,
) -> Path:
    """``DATA_DIR`` > ``VOICE_LIBRARY_DIR`` > ``VOICE_LIBRARY_PATH_CONTAINER`` else the voice
    library dir (``runtime.json`` rides along on the voice-library mount by default — this is
    where ``runtime_store.py`` actually persists it, and where the writability health check
    must probe)."""
    home = home if home is not None else Path.home()
    value = _first(environ, ("DATA_DIR", "VOICE_LIBRARY_DIR", "VOICE_LIBRARY_PATH_CONTAINER"))
    if value:
        return _expand(value, home)
    voice_library = (
        voice_library
        if voice_library is not None
        else voice_library_dir(environ, root=root, platform=platform, home=home)
    )
    return voice_library


def reference_audio_path(
    environ: Environ = os.environ,
    *,
    root: Path | None = None,
    platform: str = sys.platform,
    home: Path | None = None,
) -> Path:
    """``REF_AUDIO`` else ``<root>/reference.wav``."""
    home = home if home is not None else Path.home()
    value = _clean(environ, "REF_AUDIO")
    if value:
        return _expand(value, home)
    root = root if root is not None else app_data_root(environ, platform=platform, home=home)
    return root / "reference.wav"


def hf_token_file(
    environ: Environ = os.environ,
    *,
    root: Path | None = None,
    platform: str = sys.platform,
    home: Path | None = None,
) -> Path:
    """``HF_TOKEN_FILE`` else ``<root>/.hf_token``."""
    home = home if home is not None else Path.home()
    value = _clean(environ, "HF_TOKEN_FILE")
    if value:
        return _expand(value, home)
    root = root if root is not None else app_data_root(environ, platform=platform, home=home)
    return root / ".hf_token"


def ov_cache_dir(
    environ: Environ = os.environ,
    *,
    ov_data_root: Path | None = None,
    root: Path | None = None,
    platform: str = sys.platform,
    home: Path | None = None,
) -> Path | None:
    """``OV_CACHE_DIR`` else ``<OV root>/cache``.

    Unlike every other resolver, a *present-but-blank* ``OV_CACHE_DIR`` is not "unset" — it
    means the OpenVINO compile cache is explicitly disabled (``None``), matching the existing
    ``openvino/runtime_config.py`` behavior. An absent ``OV_CACHE_DIR`` still falls through to
    the default path.
    """
    home = home if home is not None else Path.home()
    if "OV_CACHE_DIR" in environ:
        value = environ["OV_CACHE_DIR"].strip()
        return _expand(value, home) if value else None
    ov_data_root = (
        ov_data_root
        if ov_data_root is not None
        else ov_root(environ, root=root, platform=platform, home=home)
    )
    return ov_data_root / "cache"


def describe_paths(
    environ: Environ = os.environ,
    *,
    platform: str = sys.platform,
    home: Path | None = None,
) -> dict[str, str | None]:
    """Read-only snapshot of every resolved path, for ``persona-forge doctor``.

    Never creates anything — pair with :func:`ensure_writable_dirs` when directories must
    actually exist (``setup``/``serve``).
    """
    home = home if home is not None else Path.home()
    root = app_data_root(environ, platform=platform, home=home)
    model_cache = model_cache_dir(environ, root=root, home=home)
    voice_lib = voice_library_dir(environ, root=root, home=home)
    ov = ov_root(environ, root=root, home=home)
    cache = ov_cache_dir(environ, ov_data_root=ov, home=home)
    return {
        "app_data_root": str(root),
        "model_cache_dir": str(model_cache),
        "pocket_tts_artifact_dir": str(
            pocket_tts_artifact_dir(environ, model_cache=model_cache, home=home)
        ),
        "ov_root": str(ov),
        "voice_library_dir": str(voice_lib),
        "segment_library_dir": str(segment_library_dir(environ, root=root, home=home)),
        "runtime_data_dir": str(runtime_data_dir(environ, voice_library=voice_lib, home=home)),
        "reference_audio_path": str(reference_audio_path(environ, root=root, home=home)),
        "hf_token_file": str(hf_token_file(environ, root=root, home=home)),
        "ov_cache_dir": str(cache) if cache is not None else None,
    }


def ensure_writable_dirs(
    environ: Environ = os.environ,
    *,
    platform: str = sys.platform,
    home: Path | None = None,
) -> list[Path]:
    """Create every state directory (not files, not a disabled OV cache) and return them.

    Only ``setup``/``serve`` call this; ``doctor`` stays read-only per the architecture
    contract. Reference audio and the HF token file are files, not directories, and are
    deliberately excluded — nothing here should create a placeholder file in their place.
    """
    home = home if home is not None else Path.home()
    root = app_data_root(environ, platform=platform, home=home)
    model_cache = model_cache_dir(environ, root=root, home=home)
    voice_lib = voice_library_dir(environ, root=root, home=home)
    ov = ov_root(environ, root=root, home=home)
    cache = ov_cache_dir(environ, ov_data_root=ov, home=home)

    dirs = [
        root,
        model_cache,
        pocket_tts_artifact_dir(environ, model_cache=model_cache, home=home),
        ov,
        voice_lib,
        segment_library_dir(environ, root=root, home=home),
        runtime_data_dir(environ, voice_library=voice_lib, home=home),
    ]
    if cache is not None:
        dirs.append(cache)

    created: list[Path] = []
    seen: set[Path] = set()
    for directory in dirs:
        if directory in seen:
            continue
        seen.add(directory)
        directory.mkdir(parents=True, exist_ok=True)
        created.append(directory)
    return created
