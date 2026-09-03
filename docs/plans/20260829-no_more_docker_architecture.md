# Native Persona Forge — Architecture Contract

**Status:** Binding design for `20260829-no_more_docker_requirement.md`  
**Source baseline:** `986667730d1ef4e79db973b3c40dd6538c58e405`  
**Execution plan:** `docs/plans/20260829-no_more_docker_requirement.md`

## 1. Goal

Persona Forge must support three delivery surfaces without weakening the existing container:

1. A source checkout managed by uv.
2. An installable Python wheel/sdist with the browser UI included.
3. Optional platform archives containing a small native launcher, bundled uv, the wheel, locked
   dependency manifests, release metadata, and checksums.

Docker remains the reproducible deployment/export path. It is no longer the only supported way to
run the product.

The supported full-Studio checkout flow is:

```bash
uv sync --locked
uv run --frozen persona-forge setup
uv run --frozen persona-forge serve
```

`uv run --frozen persona-forge serve` must also work without `setup`; when no packaged or checkout
UI exists it must emit a prominent API-only warning rather than silently implying that the Studio
is present. `persona-forge setup --no-ui` is the explicit API-only setup path.

## 2. Support contract

| Host | Default product path | Optional acceleration | Status required before release |
|---|---|---|---|
| macOS Apple Silicon | Pocket-TTS on CPU; full UI | Torch MPS for engines that actually support it | Native setup, ready health, and generation smoke |
| Linux x86-64 | Pocket-TTS on CPU; full UI | CUDA, Intel XPU, and ROCm extras | CPU validated via container parity (9C) and CI; CUDA/XPU only where hardware-tested; ROCm experimental |
| Windows x86-64 | Pocket-TTS on CPU; Waitress; full UI | CUDA Torch for supported Torch consumers | Native setup, ready health, generation smoke, clean shutdown |
| Linux ARM64 | Package/launcher resolution | Target-dependent | Experimental until native runtime evidence exists |

Important distinctions:

- Pocket-TTS is CPU-only. A generic Torch device of `mps`, `cuda`, or `xpu` is not proof that the
  active Pocket-TTS backend uses that device.
- `GPU_FAMILY` remains the Torch-wheel/install axis: `cpu`, `cuda`, `rocm`, or `intel-xpu`.
  Do not add `mps`; macOS uses the default wheel family and `device.py` may independently resolve
  the runtime device to `mps`.
- Qwen3-TTS and OpenVINO are not supported on Windows by this work. Do not document or test an
  unsupported combination as a degraded success.
- ROCm resolution is useful evidence, but it is not runtime support without AMD hardware.

## 3. Product defaults and readiness

Compose already sets `TTS_BACKEND=pocket_tts`, but source fallbacks still select Qwen
PyTorch/OpenVINO. Define one shared source-level `DEFAULT_TTS_BACKEND = "pocket_tts"` and use it at
every unset/blank default and reset/revert site. Preserve startup authority exactly: locked runtime
environment > persisted `runtime.json` > plain environment > product default. Direct Gunicorn and
the supported console path must agree, while an explicit operator value still wins.

Readiness means all of the following, not merely HTTP 200:

- `/health` parses as JSON.
- `service_started` is `true`.
- `status` is `ok` or the narrowly documented healthy/degraded state for the exercised feature.
- `backend` equals the expected backend.
- A bounded generation request succeeds on real-runtime gates.

`status=error` fails immediately. Startup polling must have a deadline, capture logs on failure,
and always terminate processes it starts.

## 4. Filesystem contract

Use stdlib `pathlib`; do not add a direct platformdirs dependency merely for this refactor. Every
resolver accepts an environment mapping and injectable platform/home inputs for unit tests. No
resolver performs I/O at import time.

`PERSONA_FORGE_HOME` is the new application-state root override. Defaults are:

- Linux: `$XDG_DATA_HOME/persona-forge`, else `~/.local/share/persona-forge`.
- macOS: `~/Library/Application Support/persona-forge`.
- Windows: `%LOCALAPPDATA%/persona-forge`, else `~/AppData/Local/persona-forge`.

An explicit filesystem root is rejected. `~` is expanded. Empty path variables mean “unset” except
where an existing API gives empty a distinct meaning.

Required resolver interfaces:

```python
app_data_root(...) -> Path
model_cache_dir(...) -> Path
pocket_tts_artifact_dir(...) -> Path
ov_root(...) -> Path
voice_library_dir(...) -> Path
segment_library_dir(...) -> Path
runtime_data_dir(...) -> Path
reference_audio_path(...) -> Path
hf_token_file(...) -> Path
ov_cache_dir(...) -> Path | None
describe_paths(...) -> dict[str, str | None]
ensure_writable_dirs(...) -> list[Path]
```

The binding precedence/meaning is:

| Resolver | Existing/new runtime inputs, highest precedence first | Local default |
|---|---|---|
| app root | `PERSONA_FORGE_HOME` | platform state root above |
| model cache | `MODEL_CACHE_DIR`, `HF_HUB_CACHE`, `MODEL_CACHE_CONTAINER_PATH`, `MODEL_CACHE_PATH`, `HF_HOME/hub` | `<root>/models/huggingface/hub` |
| Pocket artifacts | `POCKET_TTS_ARTIFACT_DIR` | `<model cache>/pocket-tts` |
| OpenVINO root | `OV_DATA_DIR` | `<root>/ov` |
| voice library | `VOICE_LIBRARY_DIR` | `<root>/voices` |
| segment library | `SEGMENT_LIBRARY_DIR` | `<root>/segments` |
| runtime persistence | `DATA_DIR`, `VOICE_LIBRARY_DIR`, `VOICE_LIBRARY_PATH_CONTAINER` | voice library |
| reference audio | `REF_AUDIO` | `<root>/reference.wav` |
| token file | `HF_TOKEN_FILE` | `<root>/.hf_token` |
| OV cache | `OV_CACHE_DIR` | `<OV root>/cache`; explicit empty means disabled/`None` |

Host-side Compose variables (`MODEL_CACHE_PATH`, `OV_DATA_PATH`, `REF_AUDIO_PATH`,
`VOICE_LIBRARY_PATH`, and `SEGMENT_LIBRARY_PATH`) must not be confused with container-side runtime
variables. Docker must explicitly retain these runtime paths:

```text
MODEL_CACHE_CONTAINER_PATH=/root/.cache/huggingface/hub
OV_DATA_DIR=/ov
VOICE_LIBRARY_DIR=/voices
SEGMENT_LIBRARY_DIR=/segments
REF_AUDIO=/voice/reference.wav
HF_TOKEN_FILE=/app/.hf_token
OV_CACHE_DIR=/ov/cache
```

`doctor` never creates paths. `setup` and `serve` may create writable directories. The runtime
writability health field must probe `runtime_data_dir()`, because that is where `runtime.json` is
actually persisted.

## 5. CLI and process bootstrap

The wheel exposes `persona-forge = persona_forge.cli:main` with these commands: `doctor`, `setup`, `build-ui`, and `serve`.

- `doctor [--json]`: read-only platform, dependency, path, wheel-family, runtime-device, active
  backend, effective-backend-device, UI, and patch diagnostics. Probe failures are data, not crashes.
- `setup [--no-ui]`: create state directories, build the checkout UI when needed,
  verify optional compatibility patches, and fail with actionable prerequisites. It does not invoke
  `uv sync` or guess/install accelerator extras.
- `build-ui [--force]`: reproducible `npm ci`, check, and build with a package-lock hash stamp.
- `serve [--host HOST] [--port PORT]`: apply native bootstrap, default Pocket-TTS,
  warn on API-only mode, then replace the CLI process with the platform WSGI server. Always uses exactly 4 threads;
  auto-detection is not used because container environments can misreport core counts (e.g., LXC exposing the host's
  physical CPU count rather than the container's cgroup allocation).

POSIX uses exactly `gunicorn -w 1 -k gthread --threads 4 --timeout 300`, never preload. Windows uses Waitress
with four threads. The timeout prevents hung workers from blocking the process indefinitely. Use a process-replacement API so PID/signal behavior is not changed by an
unnecessary parent process.

Native bootstrap may set LOW_RAM_MODE's portable idle-unload default everywhere and glibc malloc
variables only on Linux. It must never set `LD_PRELOAD`. Intel NEO variables use `setdefault` and
must be applied before importing Torch/OpenVINO or creating an XPU context.

The container shell entrypoint remains a separate launcher. Shared values are guarded by tests and
a small Python accelerator manifest; do not replace the working container lifecycle with CLI
subprocess nesting.

## 5a. Packaging transition

The current `pyproject.toml` has `[tool.uv] package = false` and no `[build-system]` table at all.
`package = true` alone is not sufficient — uv is a resolver/installer, not a build backend, so
`uv build` has nothing to invoke without one. Phase 2 must add both:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Hatchling is the concrete choice because the wheel must embed the built frontend (`frontend/dist`),
which is git-ignored build output living outside `src/persona_forge`. Hatchling's wheel-target
`artifacts` option is designed for exactly this — including VCS-ignored files, unaffected by
`exclude` — so the wheel target uses `artifacts = ["src/persona_forge/static/**"]` (or the actual
path the build step copies `frontend/dist` into) rather than relying on `packages` alone. The sdist
target needs no equivalent override: `frontend/` sources and lockfiles are already tracked in git,
so Hatchling's default VCS-respecting sdist inclusion picks them up without an explicit `include`.

This is a significant developer workflow transition: existing `uv sync` workflows will need to
install the local package instead of running directly from source. This change happens in Phase 2
and is documented there.

## 6. Frontend and Python artifacts

`FRONTEND_DIST_DIR` remains the highest-precedence expert override. Otherwise the app checks:

1. UI files packaged inside `persona_forge`.
2. `frontend/dist` in a source checkout.
3. API-only mode with an explicit warning.

Building Python release artifacts always runs `npm ci`, the frontend check, and the frontend build
first. The wheel includes the resulting files; the sdist includes the sources and lockfiles needed
to reproduce them. Artifact tests inspect archive members and install the wheel non-editably in an
isolated environment. An editable `uv sync` path is not accepted as wheel proof.

## 7. Dependencies and optional engines

The default install remains Pocket-TTS + OmniVoice and is patch-free, not “minimal.” Keep `pydub`
and `audioop-lts`; they are OmniVoice/Python-3.13 runtime dependencies.

Supported install combinations are explicit:

| Capability | Command shape |
|---|---|
| Default | `uv sync --locked` |
| CUDA 12/13, XPU, ROCm | `uv sync --locked --extra <doctor recommendation>` |
| Qwen PyTorch | default/accelerator sync plus `--extra qwen-tts`, then `persona-forge setup` |
| Qwen OpenVINO | `--extra qwen-tts --group openvino`, then patch verification and an existing IR |
| Export | Qwen extra plus export group; real export stays on docker-agent |

uv extras choose native-environment wheels. Docker continues to install its CPU wheel at build time
and a persisted per-family wheel at first boot. Repair that installer, retain
`ACCEL_TORCH_INDEX_URL`/`ACCEL_TORCH_VERSION`, add an independently overridable torchaudio pin, and
test it against the same manifest used by doctor and pyproject validation.

PyTorch index inventories and CUDA-driver compatibility are live facts. A checked-in mapping is
accepted only with a dated machine-readable verification receipt. Unsupported target/extra pairs
must fail resolution rather than install nothing silently.

Verified 2026-08-29 against `download.pytorch.org/whl/<index>/torch/`, torch 2.13.0, cp313:

- `cuda12` extra: both `cu126` and `cu129` carry matching cp313 wheels. Pin the extra to `cu126` —
  the older point release has the wider driver-floor compatibility that "CUDA floors" (Task 4)
  exists to protect — and expose `cu129` only through the existing `ACCEL_TORCH_INDEX_URL`
  escape hatch, not as a second extra. Do not treat `cu129` as unsupported; it is a valid,
  verified index, just not the default.
- `cuda13` extra: both `cu130` and `cu132` carry matching cp313 wheels. Same policy — pin to
  `cu130`, leave `cu132` reachable via the escape hatch.
- `rocm` extra: the real ceiling is `rocm6.4`, which is the *only* stable ROCm index carrying cp313
  wheels (torch 2.8.0/2.9.0/2.9.1, both cp313 and cp313t). `rocm6.2` and `rocm6.3` have no cp313
  wheels at all — the current container default of `rocm6.2` (`entrypoint.sh`,
  `ACCELERATOR_FAMILIES.md`, `ENV_REFERENCE.md`) is stale and will fail resolution/install outright
  on a cp313 environment; Phase 4 Task 7 ("fix stale container defaults") must bump this to
  `rocm6.4` with torch pinned to `2.9.1`. ROCm7.x cp313 wheels exist only on the nightly index and
  are out of scope per the plan's non-goals (no real ROCm support without hardware, and nightly
  wheels are not a reproducible pin).
- The Phase 4 resolution gates (`docs/plans/20260829-no_more_docker_requirement.md`) must exercise
  `--extra cuda12` alongside `--extra cuda13`; testing only `cuda13` leaves the `cuda12` floor
  unverified.

## 8. Compatibility patching

There is one idempotent Python patch implementation used by both local setup and Docker build. Each
transformation reports exactly one of `applied`, `already_applied`, or `failed`; zero-match and
multi-match states fail. Verification covers every current Docker transformation, not four sample
substrings. A disposable-venv gate proves first application, second-run idempotency, qwen import,
and a hardware-free construction/import smoke.

## 9. CI, native testing, and launcher artifacts

CI has separate responsibilities:

- Existing fake CI remains fast and requirements-driven.
- Portable-package CI checks uv lock freshness, target resolution, semantic path/CLI tests,
  frontend build, wheel/sdist contents, isolated wheel install, and a fake-runtime server.
- Native macOS and Windows runners prove target runtime behavior. A Linux cross runner cannot
  substitute for native Torch, MPS, Waitress, filesystem, and audio tests.
- Real CUDA/XPU/model gates run only on the named hardware and produce receipts.

The existing `arc-llama-monitor` cross-build runner and Local LLM Foundry release workflow are the
patterns for optional launchers, but that scale set is repository-scoped to Local LLM Foundry and
cannot simply be named by Persona Forge. Provision a Persona Forge-scoped scale set (provisional
name `arc-persona-forge-release`) through a separate runner-infrastructure change, pin its image by
immutable tag/digest, and reconcile the runner workflow's stale osxcross preflight tag with the tag
actually used by its Dockerfile before trusting it. Do not freeze Torch/OmniVoice into a giant
PyInstaller binary. Build a small Rust launcher and package it with:

```text
persona-forge-launcher[.exe]
uv[.exe]
persona_forge-<version>-py3-none-any.whl
requirements-<target>.txt
manifest.json
README.txt
```

The launcher creates an application-managed Python 3.13 environment, uses bundled uv to sync the
hash-locked target manifest, installs the local wheel without dependency re-resolution, and execs
the Python CLI. Models and accelerator wheels are downloaded separately; tokens are never logged.

Release archives follow Local LLM Foundry's fail-closed asset contract: exact names, archive-member
validation, `checksums.json`, SHA-256 coverage for every asset, short-lived intermediate artifacts,
and no signing claim unless signing is actually configured and verified. Cross-built artifacts
still require target-native smoke tests before release.

## 10. Evidence, safety, and rollback

Every implementation phase is one dependency-ordered commit and records exact commands/results.
Gates never use `tail`, discard stderr, convert failure into an echo success, delete `.venv`, or
accept `DEFERRED` as completion. Temporary environments use `mktemp -d`/PowerShell temporary paths.

Production docker-agent changes require an explicit approval checkpoint. Use the canonical
`docker-agent` SSH alias and project/Compose paths from `docs/dev/INTERNAL_OPERATIONS.md`; do not mix
root and nick-owned homes. Never touch unrelated containers.

Rollback is the previous immutable container image or reverting the implementation commits in
reverse dependency order. Reverting an early phase alone while retaining dependent later phases is
not supported.

The final handoff records source SHA, image tag/digest, model revision and IR metadata hash or N/A,
all validation commands/results, platform and hardware receipts, artifact/checksum locations, known
divergences, and whether rollback was tested.

## 11. Non-goals

- Removing Docker or moving real OpenVINO export off docker-agent.
- Claiming Pocket-TTS uses MPS/CUDA/XPU.
- Windows Qwen/OpenVINO support.
- Real ROCm support without hardware.
- Bundling model weights, generated audio, tokens, or IR into Git/release artifacts.
- A monolithic PyInstaller/Nuitka distribution.

## Appendix A — Baseline source map

These anchors describe the stated baseline and are the copy/reference points for the execution
plan. Re-search symbols after any earlier phase moves them.

| Contract | Baseline source |
|---|---|
| Backend preset/default application | `src/persona_forge/config.py:37-66`; `model.py:22-54,1243` |
| Runtime persistence precedence/atomic write | `runtime_store.py:21-28,62-78,81-112` |
| Health shape/readiness state | `app.py:229-259`; `model.py:771-801`; `test_app_health.py` |
| Frontend fallback/static routes | `app.py:105-130`; `scripts/dev_ui.sh:20-23` |
| Pocket/model cache container literals | `pocket_tts_runtime.py:103-107`; `model.py:721-741,961-963` |
| OV cache empty sentinel | `openvino/runtime_config.py:53-70`; `docs/ENV_REFERENCE.md` OV cache row |
| Family/device separation | `gpu_family.py:27-169`; `device.py:15-77` |
| Container CPU wheel and WSGI command | `Dockerfile:61-69,132-134` |
| First-boot accelerator install/env | `scripts/entrypoint.sh:6-90` |
| Container mounts and health override | `compose.yml:99-116` |
| Packaging baseline | `pyproject.toml:1-70` |
| Canonical validations | `docs/dev/validation_checks.md`; `docs/TEST_STRATEGY.md` |
| Package/image CI patterns | `.github/workflows/ci.yml`; `.github/workflows/image.yml` |
| Cross-build/release contract patterns | `../local-llm-foundry/.github/workflows/release.yml`; `../local-llm-foundry/scripts/validate-release-contract.mjs` |
