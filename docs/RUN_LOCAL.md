# Running Persona Forge locally

The **desktop app is the recommended install** for a local interactive experience. Download the
macOS DMG or Windows NSIS installer, or the Linux x86-64 AppImage preview, from
[GitHub Releases](https://github.com/nmorgowicz-org/persona-forge/releases). The Windows
installer is unsigned and may trigger SmartScreen or Smart App Control; Linux is a preview and
GNOME may require the AppIndicator extension for the tray icon. See the
[desktop app guide](architecture/DESKTOP_APP.md) for installation details, Settings, updates,
and troubleshooting.

This guide covers headless native installs and development. For a headless service on any
supported OS, the container remains the recommended path; see [HOW_TO_RUN.md](HOW_TO_RUN.md).
For migrating an existing Docker deployment's data, see [MIGRATION.md](MIGRATION.md).
The native CLI requires Python `>=3.13,<3.14` (the desktop app bundles its own runtime).


> **Hardware validation status:** the desktop app's automatic GPU acceleration is validated on
> macOS Apple Silicon (MPS), Windows+NVIDIA (CUDA 13/12), Linux+NVIDIA (CUDA 13/12), Linux+Intel
> iGPU (XPU), and Linux+AMD (ROCm). The desktop app falls back to CPU inference with a notice when
> the detected accelerator is unavailable. Headless native installs (CLI, container) are exercised
> by CI on Linux (fake-model test lanes) and have real end-to-end validation on Apple Silicon /
> Intel iGPU per [architecture/ACCELERATOR_FAMILIES.md](architecture/ACCELERATOR_FAMILIES.md)'s
> validation-status table.

## Headless native installation

### Linux x86-64 CLI launcher archive

The Linux CLI archive is for headless native installs. It includes the native launcher, app wheel,
target-specific hash-locked requirements, a pinned `uv` binary, and a manifest. It does not
contain the large ML dependency wheels or model weights. Internet access is required on first use
to download Python and Python packages, and on the first server start to download model assets.

```bash
VERSION=1.4.7
ARCHIVE=persona-forge-bootstrap-linux-x86_64.tar.gz
BASE_URL="https://github.com/nmorgowicz-org/persona-forge/releases/download/persona-forge-v${VERSION}"
mkdir -p "persona-forge-${VERSION}" && cd "persona-forge-${VERSION}"
curl -fL -o checksums.json "${BASE_URL}/checksums.json"
curl -fL -o "${ARCHIVE}" "${BASE_URL}/${ARCHIVE}"
EXPECTED=$(awk -F'"' -v name="${ARCHIVE}" '{for (i = 1; i <= NF; i++) if ($i == name) {print $(i + 2); exit}}' checksums.json)
ACTUAL=$(sha256sum "${ARCHIVE}" | awk '{print $1}')
[ -n "${EXPECTED}" ] && [ "${ACTUAL}" = "${EXPECTED}" ] || { echo "checksum verification failed" >&2; exit 1; }
tar -xzf "${ARCHIVE}"
chmod +x persona-forge-launcher
./persona-forge-launcher doctor --json
./persona-forge-launcher setup
./persona-forge-launcher serve
```

Open <http://127.0.0.1:8318> after the server starts. Stop it with `Ctrl-C`. Replace `1.4.7`
with the release version you want.

### Headless native install on macOS or Windows

The macOS and Windows CLI launcher archives are no longer distributed. Use the release wheel
with `uv` instead:

```bash
uv tool install persona-forge
uvx persona-forge serve
```

Install a Python 3.13-compatible `uv` first if needed. The server defaults to port 8318; stop it
with `Ctrl-C`.

## Desktop app

The desktop app is the recommended local install and manages its server in a native window. See
[DESKTOP_APP.md](architecture/DESKTOP_APP.md) for the full desktop contract and troubleshooting.

## Other native installation paths

### Source checkout (`uv`) — for development or a git-managed install

This path is useful when you need explicit accelerator extras, Qwen3-TTS/OpenVINO, or source
development. Install `uv` first using the instructions at <https://docs.astral.sh/uv/getting-started/>
and install Node.js/npm if you want to build the UI from source.

```bash
git clone https://github.com/nmorgowicz-org/persona-forge.git
cd persona-forge
uv sync --locked
uv run persona-forge doctor
uv run persona-forge setup       # builds the UI; requires Node.js/npm
uv run persona-forge serve
```

For an API-only source install, use `uv run persona-forge setup --no-ui`. This is the same
environment covered in depth in [dev/LOCAL_SETUP.md](dev/LOCAL_SETUP.md).

### Release wheel — headless macOS or Windows

For headless use without Docker on macOS or Windows, install the release wheel with `uv`. The
wheel includes the built web UI; no Node.js or frontend build is needed. Install a
Python 3.13-compatible `uv` first:

```bash
uv tool install persona-forge
uvx persona-forge serve
```

The server listens on port 8318 by default. Stop it with `Ctrl-C`. The Linux CLI archive remains
available for headless Linux installs; the desktop app is the recommended local install on each
platform.


## The CLI surface

All three paths above expose the same four subcommands (`src/persona_forge/cli.py`):

- `persona-forge doctor [--json]` — read-only environment diagnostics: Python/torch/accelerator
  probes, resolved state-directory paths, no side effects.
- `persona-forge setup [--no-ui] [--apply-qwen-patches]` — creates the state directories
  (idempotent). `--apply-qwen-patches` applies the `qwen_tts`/`transformers` compatibility
  patches (`persona_forge.compat_patch`) if `qwen_tts` is installed; without the flag, `setup`
  only reports patch status and is a no-op when `qwen_tts` isn't installed.
- `persona-forge build-ui [--force]` — builds the frontend from source into a `dist/` directory
  next to the checkout.
- `persona-forge serve [--host 127.0.0.1] [--port <PERSONA_FORGE_PORT env, default 8318>]` — runs
  the WSGI server. `serve` applies the same low-level runtime env defaults
  (`bootstrap.apply_env_defaults`) that `scripts/entrypoint.sh` applies inside the container —
  `LOW_RAM_MODE` idle-unload timing, Linux glibc malloc tuning, Intel NEO fp64-emulation env vars
  — so the two surfaces agree on every default. It warns (non-blocking) if no frontend `dist/`
  exists, and warns (non-blocking) if the target host:port is already in use.

## Where native state lives

With no Docker bind mounts to anchor paths, the native install resolves every state directory
from a platform-appropriate application-data root (`persona_forge/paths.py`), unless you
override it:

| Path | Default (native) | Override |
|---|---|---|
| App data root | Linux: `$XDG_DATA_HOME/persona-forge` or `~/.local/share/persona-forge`; macOS: `~/.config/persona-forge`; Windows: `%LOCALAPPDATA%/persona-forge` | `PERSONA_FORGE_HOME` |
| Model cache | `<app data root>/models/huggingface/hub` | `MODEL_CACHE_DIR` (or `HF_HUB_CACHE` / `HF_HOME`) |
| Pocket-TTS artifacts | `<model cache>/pocket-tts` | `POCKET_TTS_ARTIFACT_DIR` |
| OpenVINO IR + cache | `<app data root>/ov` (+ `/cache`) | `OV_DATA_DIR` (+ `OV_CACHE_DIR`) |
| Voice library | `<app data root>/voices` | `VOICE_LIBRARY_DIR` |
| Segment library | `<app data root>/segments` | `SEGMENT_LIBRARY_DIR` |

`persona-forge doctor --json` reports every resolved path under `paths` — run it any time you
need the exact directories in use on your machine. See [MIGRATION.md](MIGRATION.md) for the full
Docker-container-path-to-native-path mapping and for copying an existing deployment's data over.

## Accelerators

The desktop app provisions the matching PyTorch accelerator automatically on first launch and
after each update — no user action needed. It detects the GPU family (NVIDIA CUDA 12/13, Intel
XPU, AMD ROCm, or CPU) and installs the correct wheel into a versioned environment. See
[architecture/DESKTOP_APP.md](architecture/DESKTOP_APP.md), "GPU acceleration," for the settings
and fallback behavior.

For source installs and headless native installs outside the desktop app, accelerator wheels are
opt-in extras at install time (`uv sync --extra cuda12` / `cuda13` / `xpu` / `rocm`), rather than
the container's first-boot runtime install — see
[architecture/ACCELERATOR_FAMILIES.md](architecture/ACCELERATOR_FAMILIES.md), "Native install."

## Docker vs. native

Both are supported; pick based on what you need:

| | Docker | Native |
|---|---|---|
| Reproducibility | Highest — pinned image, isolated from host Python/OS | Depends on host Python/OS/toolchain state |
| Setup friction | Needs Docker/Compose installed | Desktop app needs no separate Python setup; headless Linux archive bundles launcher tooling; source development needs `uv` |
| Isolation from host | Full (container namespace, own filesystem) | None — runs as a normal host process |
| Accelerator install | First-boot into a persisted volume, one image for all families | Desktop app auto-provisions the matching PyTorch wheel; headless extras resolved at `uv sync` time |
| Best for | Headless servers, shared hosts, anything needing a reproducible artifact | Local interactive use (desktop app), Linux headless installs, or development |

**Avoid starting the desktop app and a CLI/container server on the same port.** Docker and the
CLI default to 8318; the desktop app automatically selects and remembers a port from 8318–8348.
If the selected port is already serving Persona Forge, the desktop app refuses to attach or start
a second server. Change the port in desktop Settings or stop the other server first.
