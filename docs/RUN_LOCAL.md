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

## Recommended path: the release launcher

For most users who do not want Docker, download the platform launcher archive from the
[Persona Forge releases](https://github.com/nmorgowicz-org/persona-forge/releases). Each archive
contains the native launcher, Python 3.13-compatible application wheel, target-specific
hash-locked requirements, a pinned `uv` binary, and a manifest. It does not contain the large ML
dependency wheels or model weights.

The launcher is the native install and startup helper. It creates a per-user, versioned Python
environment on first use, installs the bundled wheel and requirements, and reuses that environment
on later runs. No preinstalled Python, `uv`, Node.js, administrator access, or repository checkout
is required. Internet access is required on the first run to download Python and Python packages,
and on the first server start to download model assets. Even `doctor` performs the initial
environment bootstrap; after bootstrap, `doctor` itself is read-only.

### Supported release archives

| Operating system | Release asset | Notes |
|---|---|---|
| Linux x86-64 | `persona-forge-bootstrap-linux-x86_64.tar.gz` | Intel/AMD 64-bit Linux |
| macOS Apple Silicon | `persona-forge-bootstrap-macos-aarch64.tar.gz` | M-series Macs |
| Windows x86-64 | `persona-forge-bootstrap-windows-x86_64.zip` | 64-bit Intel/AMD Windows |

There are currently no launcher archives for Linux ARM64, Intel Macs, or Windows ARM64. The
launcher uses the default native dependency set; explicit CUDA, ROCm, Intel XPU, or Qwen3-TTS
extras require the source-checkout path described below.

### Download, verify, and run on Linux

Replace `1.4.7` below with the release version you want to install.

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

Open <http://127.0.0.1:8318> after the server starts. Stop it with `Ctrl-C`.

### Download, verify, and run on Apple Silicon macOS

Use the same flow with the macOS archive. The `xattr` command is needed only when macOS
quarantines the launcher extracted from a browser download.

```bash
VERSION=1.4.7
ARCHIVE=persona-forge-bootstrap-macos-aarch64.tar.gz
BASE_URL="https://github.com/nmorgowicz-org/persona-forge/releases/download/persona-forge-v${VERSION}"
mkdir -p "persona-forge-${VERSION}" && cd "persona-forge-${VERSION}"
curl -fL -o checksums.json "${BASE_URL}/checksums.json"
curl -fL -o "${ARCHIVE}" "${BASE_URL}/${ARCHIVE}"
EXPECTED=$(awk -F'"' -v name="${ARCHIVE}" '{for (i = 1; i <= NF; i++) if ($i == name) {print $(i + 2); exit}}' checksums.json)
ACTUAL=$(shasum -a 256 "${ARCHIVE}" | awk '{print $1}')
[ -n "${EXPECTED}" ] && [ "${ACTUAL}" = "${EXPECTED}" ] || { echo "checksum verification failed" >&2; exit 1; }
tar -xzf "${ARCHIVE}"
chmod +x persona-forge-launcher
xattr -dr com.apple.quarantine .  # only in this verified archive directory
./persona-forge-launcher doctor --json
./persona-forge-launcher setup
./persona-forge-launcher serve
```

Open <http://127.0.0.1:8318> after the server starts. Stop it with `Ctrl-C`.

### Download, verify, and run on Windows

Run this in Windows PowerShell. Replace `1.4.7` with the release version you want.

```powershell
$version = '1.4.7'
$archive = 'persona-forge-bootstrap-windows-x86_64.zip'
$baseUrl = "https://github.com/nmorgowicz-org/persona-forge/releases/download/persona-forge-v$version"
$installDir = Join-Path (Get-Location) "persona-forge-$version"
New-Item -ItemType Directory -Path $installDir -Force | Out-Null
Set-Location $installDir
Invoke-WebRequest -Uri "$baseUrl/checksums.json" -OutFile .\checksums.json
Invoke-WebRequest -Uri "$baseUrl/$archive" -OutFile ".\$archive"
$checksums = Get-Content .\checksums.json -Raw | ConvertFrom-Json
$expected = $checksums.checksums.PSObject.Properties[$archive].Value
$actual = (Get-FileHash ".\$archive" -Algorithm SHA256).Hash.ToLowerInvariant()
if ([string]::IsNullOrEmpty($expected) -or $actual -ne $expected) { throw 'checksum verification failed' }
Expand-Archive -LiteralPath ".\$archive" -DestinationPath . -Force
.\persona-forge-launcher.exe doctor --json
.\persona-forge-launcher.exe setup
.\persona-forge-launcher.exe serve
```

Open <http://127.0.0.1:8318> after the server starts. Stop it with `Ctrl-C`.

### Updating a launcher installation

Download and verify the newer release archive in a new directory, then run its launcher. The
launcher keeps application data and installed environments under the user data root, so voices,
cached models, and settings are reused. It provisions the new application version alongside the
old one and switches the `current` marker only after a successful install. The `uv` version is
updated by downloading the newer release archive; users do not need to update `uv` separately.
Keep the previous archive if you want a simple rollback.

The launcher is intentionally a single executable rather than a separate shell or batch wrapper:
it performs the same verified setup flow on every supported OS and avoids shell-policy,
quoting, and executable-bit differences.

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

### Release wheel — for users who already manage Python

The project currently attaches the wheel to GitHub Releases; it is not published to PyPI. Use a
Python 3.13 interpreter (`>=3.13,<3.14`) and install the wheel from the release page. The wheel
already contains the built web UI, so no Node.js installation or frontend build is needed.

On macOS/Linux:

```bash
VERSION=1.4.7
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install "https://github.com/nmorgowicz-org/persona-forge/releases/download/persona-forge-v${VERSION}/persona_forge-${VERSION}-py3-none-any.whl"
persona-forge doctor
persona-forge setup --no-ui
persona-forge serve
```

On Windows PowerShell:

```powershell
$version = '1.4.7'
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install "https://github.com/nmorgowicz-org/persona-forge/releases/download/persona-forge-v$version/persona_forge-$version-py3-none-any.whl"
.\.venv\Scripts\persona-forge.exe doctor
.\.venv\Scripts\persona-forge.exe setup --no-ui
.\.venv\Scripts\persona-forge.exe serve
```

The wheel's dependencies are resolved from package indexes during installation. For a fully
managed install with the target requirements and bundled `uv`, use the launcher path above.

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
