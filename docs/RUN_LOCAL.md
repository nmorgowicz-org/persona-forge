# Running Persona Forge natively (no Docker)

This document is for running Persona Forge directly on your machine — a source checkout, an
installed wheel, or a downloaded launcher archive — with no container involved. It's an
alternative deployment path to [HOW_TO_RUN.md](HOW_TO_RUN.md), not a replacement; Docker remains
the reproducible, most-tested deployment path (see "Docker vs. native" below). For migrating an
existing Docker deployment's data over, see [MIGRATION.md](MIGRATION.md).

> **Hardware validation status:** the native setup below is exercised by CI on Linux (fake-model
> test lanes) and has real end-to-end validation on Apple Silicon / Intel iGPU per
> [architecture/ACCELERATOR_FAMILIES.md](architecture/ACCELERATOR_FAMILIES.md)'s validation-status
> table. Broader OS/hardware combinations (Windows+NVIDIA, additional Linux+GPU configurations)
> are staged for verification but not yet confirmed on real hardware — treat native support on an
> unlisted combination as best-effort until this note is updated.

## Three ways to get it running

### 1. Source checkout (`uv`) — for development or a git-managed install

```bash
git clone <this repo> && cd persona-forge
uv sync                    # installs the main runtime set (OmniVoice, Pocket-TTS, torch, etc.)
uv run persona-forge doctor         # read-only environment diagnostics
uv run persona-forge setup          # create state directories (idempotent)
uv run persona-forge build-ui       # build the frontend from source (skip for --no-ui / API-only)
uv run persona-forge serve
```

This is the same environment covered in depth in
[dev/LOCAL_SETUP.md](dev/LOCAL_SETUP.md) (accelerator extras, the Qwen3-TTS opt-in engine,
compat patches, etc.) — that document is written for iterating on the code; this one is written
for just running it.

### 2. Installed wheel/sdist — for a pip/pipx-style install with no repo checkout

```bash
pip install persona-forge   # or: pipx install persona-forge
persona-forge doctor
persona-forge setup --no-ui        # or drop --no-ui once a frontend build is available to bundle
persona-forge serve
```

The `persona-forge` console entry point (`persona_forge.cli:main`) is declared in
`pyproject.toml`'s `[project.scripts]`. The published wheel targets Python `>=3.13,<3.14`
(`pyproject.toml`'s `requires-python`) — install into a matching interpreter.

### 3. Launcher archive — for a host with no Python/uv preinstalled

Download the platform-matching `persona-forge-bootstrap-<os>-<arch>` archive from a GitHub
Release (see the launcher release workflow, Phase 7), extract it, and run:

```bash
./persona-forge-launcher doctor
./persona-forge-launcher setup
./persona-forge-launcher serve
```

The launcher is a small native binary that provisions an application-managed Python environment
(using the pinned `uv` binary bundled in the same archive) and installs the bundled wheel into
it — it does not itself contain the ML stack. Model weights and accelerator wheels are still
downloaded separately on first use.

On macOS, Gatekeeper may quarantine executables extracted from a browser download. After
verifying the release checksum, run this from the extracted archive directory if the launcher is
blocked:

```bash
xattr -dr com.apple.quarantine .
```

Only run this in the directory created for the verified Persona Forge archive.

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

Native accelerator wheels are opt-in extras at install time (`uv sync --extra cuda12` /
`cuda13` / `xpu` / `rocm`), rather than the container's first-boot runtime install — see
[architecture/ACCELERATOR_FAMILIES.md](architecture/ACCELERATOR_FAMILIES.md), "Native install."
A plain `uv sync` (no extra) already covers macOS Apple Silicon (cpu+mps) and Linux+NVIDIA
(bundled CUDA wheel) without any extra.

## Docker vs. native

Both are supported; pick based on what you need:

| | Docker | Native |
|---|---|---|
| Reproducibility | Highest — pinned image, isolated from host Python/OS | Depends on host Python/OS/toolchain state |
| Setup friction | Needs Docker/Compose installed | Needs `uv` (or nothing, with the launcher archive) |
| Isolation from host | Full (container namespace, own filesystem) | None — runs as a normal host process |
| Accelerator install | First-boot into a persisted volume, one image for all families | Extras resolved at `uv sync` time, one venv per family |
| Best for | Servers, shared hosts, anything needing a reproducible artifact | Local development, single-user desktop/laptop installs, hosts where Docker itself isn't available or wanted |

**Don't run both against the same port at once.** Both default to port 8318; if a Docker
container and a native `serve` are started on the same host without one of them overriding
`--port`/`PERSONA_FORGE_PORT`, the second one to start will either fail to bind or silently shadow
the first, depending on your platform's socket behavior. Pick one, or give the second an explicit
`--port`.
