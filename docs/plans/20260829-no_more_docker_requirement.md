# Native Persona Forge — Execution Plan

> This is the lower-tier-model execution document. The binding decisions live in
> `docs/plans/20260829-no_more_docker_architecture.md`. Read that document completely before each
> phase. If this plan and the architecture contract disagree, stop and repair the documents; do not
> choose one silently.

**Baseline:** `986667730d1ef4e79db973b3c40dd6538c58e405`  
**Target:** supported native checkout, wheel/sdist, full Studio, optional thin-launcher archives,
and unchanged Docker deployment/export behavior.

## Worker protocol

This section is mandatory for every phase, including fresh chat contexts.

1. Work on a feature branch, never directly on `main`.
2. Execute exactly one phase per context and one dependency-ordered commit per phase.
3. Read every phase reference before editing. Re-read the exact target block immediately before an
   edit. Use `apply_patch` for source/doc edits.
4. Start with the named failing test. Do not add an API that is absent from the architecture
   contract merely because it seems convenient.
5. Use `rtk` for routine commands. If compression obscures evidence, rerun that command raw as the
   repository guide permits and retain the full output.
6. Gates are fail-closed. Do not use `tail`, discard stderr, append `|| echo`, accept a skipped UI,
   or convert `RESOLVE_FAIL` into a successful phase.
7. Never delete the shared `.venv`. Use `tempfile.TemporaryDirectory`, `mktemp -d`, or a PowerShell
   temporary directory and clean up only the validated temporary path.
8. After every non-trivial edit:

   ```bash
   rtk git diff
   rtk git diff --check
   ```

9. Run the targeted tests, then `rtk python scripts/validate_repo.py`. A phase is incomplete until
   both pass.
10. Record commands, exit codes, source SHA, and output/log paths. Hardware gates cannot be marked
    passed from resolution, fake-runtime, cross-build, or historical evidence.

## Common verification commands

Use these exact canonical lanes when a phase says “common verification”:

```bash
rtk python scripts/validate_repo.py
rtk git diff --check
rtk npm run --prefix frontend check
rtk docker compose config --quiet
rtk proxy env PYTHONPATH=src:src/export uv run --frozen python -m pytest \
  -m "not slow and not requires_torch and not requires_model_weights and not requires_openvino_ir" \
  -n auto --tb=short \
  tests/tier1_unit tests/tier2_backend tests/tier3_api_integration
```

If dependency metadata changed, run `rtk uv lock`, review the complete lock diff, then require
`rtk uv lock --check`. Never let `uv run` silently repair a stale lock during a gate.

---

## Phase 0 — Documentation discovery, branch, and reproducible baseline

### Objective

Freeze the current contracts before implementation and repair the known stale root-project version
in `uv.lock` without hiding unrelated changes.

### References to read completely

- Architecture contract named above.
- `docs/README.md`, `docs/dev/validation_checks.md`, and `docs/TEST_STRATEGY.md`.
- `docs/agent-reference/RUNTIME_AND_MEMORY.md`.
- `docs/architecture/ACCELERATOR_FAMILIES.md`.
- `docs/dev/LOCAL_SETUP.md` and `docs/dev/INTERNAL_OPERATIONS.md`.
- Installed uv 0.12 help for `sync`, `lock`, `build`, `venv`, `pip install`, `pip sync`, and
  `--python-platform`.
- Official Hatch documentation for src-layout wheels, sdist inclusion, and wheel force-inclusion.
  Record the exact supported configuration before Phase 3; do not invent Hatch keys.

### Allowed APIs discovered from current source

- `config.normalize_backend`, `_setdefault`, and `apply_preset_env`.
- `gpu_family.resolve_gpu_family(environ, probes)` and `describe_accelerator(environ, probes)`.
- `device.resolve_device(environ)`; runtime order is CUDA, XPU, MPS, CPU.
- `/health` JSON from `model.health_state()`; HTTP 200 alone is not readiness.
- `runtime_store` atomic `mkstemp` + `os.replace` persistence pattern.
- Existing Flask static routes in `app.py`.
- stdlib `argparse`, `pathlib`, `importlib.resources`, `subprocess.Popen`, `os.execvpe`,
  `tempfile`, `urllib.request`, `json`, and `time.monotonic`.

### Tasks

1. Create a branch such as `feat/native-persona-forge` from the intended source commit.
2. Confirm the only initial workspace files are the two plan documents or explicitly inventory
   other user changes and avoid them.
3. Run `rtk uv lock --check` before any sync. At the stated baseline it is expected to fail because
   `pyproject.toml` is `1.2.2` while `uv.lock` records root project `1.2.0`.
4. Run `rtk uv lock`, inspect `rtk git diff -- uv.lock`, and stop if changes exceed the understood
   root-project metadata refresh unless separately explained.
5. Run the common verification block. Record the fake-lane passed count.
6. Query configured GitHub runner labels and document which are:
   - Linux native (`arc-general`, `arc-general-docker`).
   - Linux cross-build (`arc-llama-monitor`).
   - Actual target-native Windows and macOS runners.
   Do not assume the cross runner is target-native.
7. Record a Phase 0 allowed-API note in the PR/work log, including exact Hatch syntax selected.

### Gate 0

```bash
rtk uv lock --check
rtk uv sync --locked
rtk python scripts/validate_repo.py
rtk git diff --check
rtk npm run --prefix frontend check
rtk docker compose config --quiet
```

All pass. Commit only the intentional lock refresh if it was needed:

```text
chore(build): refresh root package metadata in uv lock
```

---

## Phase 1 — Complete path contract and Docker defaults

### Objective

Make every native mutable path user-writable while preserving old aliases, empty sentinels, and
exact container mount targets in the same commit.

### Files

- Create `src/persona_forge/paths.py`.
- Create `tests/tier1_unit/test_paths.py` and a Compose-path contract test.
- Modify `config.py`, `presets.py`, `model.py`, `model_config.py`, `runtime_store.py`,
  `voice_library.py`, `segment_library.py`, `pocket_tts_runtime.py`, and
  `openvino/runtime_config.py`.
- Modify `Dockerfile` and `compose.yml` only for explicit container runtime paths.

### Required interfaces

Copy the signatures and precedence table from the architecture contract. Add `MODEL_CACHE_DIR` as
the new canonical model-cache variable while retaining `HF_HUB_CACHE`, `MODEL_CACHE_CONTAINER_PATH`,
and `MODEL_CACHE_PATH` aliases. The exact precedence is:

```text
MODEL_CACHE_DIR > HF_HUB_CACHE > MODEL_CACHE_CONTAINER_PATH > MODEL_CACHE_PATH
> HF_HOME/hub > <app root>/models/huggingface/hub
```

Before importing Hugging Face/Torch consumers, native bootstrap sets `HF_HUB_CACHE` from the
resolved cache only when it is absent.

`ov_cache_dir()` is special: absent `OV_CACHE_DIR` returns `<ov root>/cache`; present-but-empty
returns `None`. Do not route it through a helper that collapses blank and absent.

### Tests first

Parametrize tests for:

- Explicit root, filesystem-root rejection, `~` expansion, Linux XDG, macOS Application Support,
  and Windows LOCALAPPDATA.
- Every canonical input and legacy alias with exact precedence.
- Injected mappings that prove no fallback to global `os.environ`.
- Blank/unset behavior, especially `OV_CACHE_DIR=""`.
- `runtime_data_dir`: `DATA_DIR > VOICE_LIBRARY_DIR > VOICE_LIBRARY_PATH_CONTAINER > local voice`.
- Base, VoiceDesign, and fixed 0.6B predictor IR paths.
- Pocket artifacts and model health using the resolved model cache.
- `doctor`-style description representing disabled cache as JSON null.
- Exact effective Compose container paths, parsed from `docker compose config` rather than regexed
  from YAML.

### Implementation requirements

1. Resolver functions are pure. No mkdir or file read at import time.
2. Route every consumer listed in the architecture contract; do not merely replace module constants.
3. Probe runtime-config writability at `runtime_data_dir()`, not app root.
4. Add Docker defaults for `/ov`, `/voices`, `/segments`, `/voice/reference.wav`, token, cache, and
   model cache. Host-side Compose interpolation names remain unchanged.
5. Give the export service `OV_DATA_DIR=/ov` while retaining `OV_OUTPUT_ROOT=/ov`.
6. Do not touch the first-boot accelerator installer.

### Gate 1

```bash
rtk proxy env PYTHONPATH=src:src/export uv run --frozen python -m pytest \
  tests/tier1_unit/test_paths.py -v
rtk docker compose config --quiet
rtk python scripts/validate_repo.py
rtk git diff --check
```

The parsed Compose test must assert every exact container path. No live container is required yet.

Commit:

```text
feat(paths): add native state paths without changing container mounts
```

### Known follow-up (tracked, fix in Phase 2 Task 0)

Discovered while wiring `model.py`'s remaining consumers: `presets.py`'s `get_preset()` and
`get_voice_design_preset()` call `paths.ov_root()`/`paths.ov_cache_dir()` with no `environ`
argument, so they always read the real process `os.environ` — unlike `config.apply_preset_env()`,
`model_config.py`, and every other Phase 1 consumer, which accept an injectable `environ` mapping
per the pure-resolver contract in the architecture doc §4. `config.apply_preset_env(environ)`
receives an injectable `environ` but cannot actually thread it into the preset's IR path
resolution, so a caller who injects `environ` (as `tests/tier1_unit/test_config.py` and
`test_presets.py` do) sees Base/VoiceDesign IR paths computed from real `os.environ` instead of
the mapping they passed in. Both existing tests were patched to `monkeypatch.setenv("OV_DATA_DIR",
"/ov")` as a workaround rather than left broken — that workaround should be removed once the fix
below lands. Not fixed in Phase 1 because it is a signature change to `presets.py`'s public API
(`get_preset`, `get_voice_design_preset`, and their private `_ir_paths`/`_predictor_stateful_model`/
`_voice_design_ir_paths` helpers) rather than a mechanical call-site swap, and Phase 1 was scoped to
routing existing call sites through already-defined resolvers.

---

## Phase 2 — Installable package, native bootstrap, and CLI

### Objective

Produce an installable console script with read-only diagnostics, explicit setup, correct product
default, and platform WSGI selection without importing the model in CLI diagnostics.

### Files

- Modify `pyproject.toml` and `uv.lock`.
- Modify `presets.py` (Task 0) and its callers `config.py`, `model.py`.
- Modify `tests/tier1_unit/test_config.py`, `test_presets.py` (Task 0: drop the `OV_DATA_DIR`
  `monkeypatch.setenv` workaround once `environ` threads through for real).
- Create `src/persona_forge/bootstrap.py` and `src/persona_forge/cli.py`.
- Create `tests/tier1_unit/test_bootstrap.py`, `test_cli.py`, and a reusable readiness harness under
  `tests/helpers/` or `scripts/`.
- Extend fake runtime health fields when production output changes.

### Tasks

0. **Close the Phase 1 environ-injection gap (see Phase 1's "Known follow-up"):** give
   `get_preset()`, `get_voice_design_preset()`, and their private `_ir_paths`/
   `_predictor_stateful_model`/`_voice_design_ir_paths` helpers an `environ: MutableMapping[str,
   str] = os.environ` parameter (matching every other Phase 1 resolver/consumer) and thread it
   into their `paths.ov_root()`/`paths.ov_cache_dir()` calls instead of relying on the implicit
   real-`os.environ` default. Thread the same `environ` through from `config.apply_preset_env()`,
   which already receives one but currently drops it before calling `get_preset()`. Update
   `test_config.py::test_06b_sets_expected_vars` and every `TestPresetsEnv`/`TestGetPreset`/
   `TestVoiceDesignPreset` case in `test_presets.py` to pass `OV_DATA_DIR` via the injected
   `environ` dict directly, and delete the `monkeypatch.setenv`/autouse-fixture workaround added in
   Phase 1. This is prerequisite groundwork for this phase's CLI/bootstrap work below, which must
   not leak into or read from the real process environment during tests.
1. **Packaging transition:** Change `pyproject.toml` from `[tool.uv] package = false` to
   `package = true` with console entry point `persona-forge = persona_forge.cli:main`.
   This changes the developer workflow from direct source execution to local package
   installation. Update AGENTS.md and developer docs accordingly.
2. Configure the documented Hatch src-layout build and console entry point. Package only
   `src/persona_forge`; `src/export` remains separate tooling.
3. Mark Gunicorn POSIX-only and add pinned Waitress for Windows.
4. Implement native bootstrap:
   - `LOW_RAM_MODE` portable idle-unload default on every OS.
   - glibc malloc variables only on Linux.
   - never `LD_PRELOAD`.
   - Intel NEO values with `setdefault`, before heavyweight imports.
   - cache environment and writable-directory creation only when the caller requests it.
5. Implement commands exactly as specified by the architecture:
   - `doctor` is read-only, survives missing/broken Torch, and emits stable JSON.
   - `setup` creates directories and is idempotent; UI work is completed in Phase 3.
   - Use one shared source-level `DEFAULT_TTS_BACKEND = "pocket_tts"` at every unset/blank fallback
     and reset/revert site in `config.py`/`model.py`, preserving locked env > runtime.json > plain
     env > default precedence.
   - `serve` calls write-capable bootstrap and uses process replacement for the server.
6. `_server_command()` enforces one Gunicorn worker, gthread, four threads, timeout 300, no preload;
   Windows selects Waitress with four threads.
7. Do not change Docker CMD or nest the container server under another long-lived Python process.
8. Add a model-free spawned-process acceptance fixture using the existing fake-runtime injection
   pattern. It must start the installed console command with a clean environment, poll JSON through
   the shared readiness harness, prove the effective default is Pocket-TTS, and cleanly stop the
   exact child. This is structural evidence only; Phase 9 supplies real Pocket-TTS evidence.

### Tests first

- `get_preset()`/`get_voice_design_preset()` given an injected `environ` dict with `OV_DATA_DIR`
  set resolve IR paths under that value, never the real `os.environ`'s (Task 0).
- `config.apply_preset_env(environ)` with an injected `environ` produces the same IR paths as
  calling `get_preset()` directly with that same `environ` (Task 0).
- Importing only `persona_forge.cli` in an isolated subprocess leaves `torch`, OpenVINO,
  Transformers, and `persona_forge.model` absent from `sys.modules`.
- No tautological `or True` assertions.
- `doctor --json` against a nonexistent root leaves the root nonexistent.
- `setup --no-ui` creates only documented directories and a second run is a no-op.
- Operator LOW_RAM/NEO values are never overwritten.
- macOS/Windows receive no glibc variables.
- `serve` defaults to Pocket-TTS but preserves explicit backend values.
- `serve` detects port conflicts and warns before binding.
- Exact POSIX/Windows server argv and process-replacement call.
- Broken accelerator probes become diagnostic fields, not CLI crashes.
- The fake spawned server reaches `status=ok`, `service_started=true`, expected backend, no active
  swap/reconfiguration, and fails immediately on an injected startup error.

### Packaging gate

Create a cross-platform Python test using `TemporaryDirectory` that:

1. Runs `uv build` to a temporary output directory.
2. Requires exactly one wheel and one sdist.
3. Creates a temporary Python 3.13 environment.
4. Installs the wheel non-editably and runs its installed `persona-forge --help` and
   `persona-forge doctor --json` from outside the checkout.

Do not assert that editable source files live inside `.venv`.

### Gate 2

Gate 2 = Packaging gate + pytest commands.

```bash
# Packaging gate — must pass before pytest
PYTHONPATH=src uv run uv build --out-dir /tmp/build-pf-$(date +%s)
pip install --quiet --target /tmp/build-pf-venv-$(date +%s) /tmp/build-pf-$(date +%s)/*.whl
python -m persona_forge doctor --json | python -c "import json,sys; json.load(sys.stdin)"

rtk proxy env PYTHONPATH=src:src/export uv run --frozen python -m pytest \
  tests/tier1_unit/test_bootstrap.py tests/tier1_unit/test_cli.py \
  tests/tier1_unit/test_config.py tests/tier1_unit/test_presets.py -v
rtk uv lock --check
rtk python scripts/validate_repo.py
rtk git diff --check
```

Commit:

```text
feat(cli): add native doctor setup and serve commands
```

---

## Phase 3 — Full Studio from checkout and packaged wheel

### Objective

Make the full frontend mandatory for the advertised Studio flow and include it in distributable
Python artifacts.

### Files

- Modify `app.py`, `cli.py`, and the Hatch build configuration.
- Add focused frontend-resolution and wheel-content tests.
- Add a deterministic Python artifact build script if CI needs orchestration.

### Tasks

1. Build the frontend exactly as the existing Dockerfile does (`npm ci`, `npm run check`, `npm run build`) before any Python packaging or `uv sync` — this guarantees the wheel contains the built UI.
2. Implement frontend precedence: `FRONTEND_DIST_DIR` > package-local built UI > checkout
   `frontend/dist` > API-only.
3. `build-ui` runs `npm ci`, canonical frontend check, and build. Store a package-lock hash stamp;
   skip only when the stamp and required output are current. `--force` rebuilds.
4. `setup` builds a missing/stale checkout UI unless `--no-ui`. A source Studio setup fails if Node
   or npm is absent; it does not call this success.
5. Artifact builds always run npm CI/check/build first and force-include the resulting dist using
   the exact Hatch API verified in Phase 0.
6. The sdist contains frontend sources and lockfile. The wheel contains package-local HTML/assets.
7. `serve` clearly reports API-only mode. Full-Studio gates set `FRONTEND_ENABLED=1` and require UI.

### Tests first

- Override/package/checkout/API-only resolution order.
- Missing npm is a setup failure, while `setup --no-ui` succeeds.
- Stamp hit and forced rebuild behavior with subprocess mocked.
- Installed wheel started outside the checkout serves `/`, a hashed `/assets/*`, and `/health`.
- Archive inspection rejects missing UI and forbidden weights, IR, audio, tokens, or `.env` files.

### Gate 3

```bash
rtk npm run --prefix frontend check
rtk npm run --prefix frontend build
rtk proxy env PYTHONPATH=src:src/export uv run --frozen python -m pytest \
  tests/tier1_unit/test_cli.py tests/tier2_backend -v
rtk uv build
rtk python scripts/validate_repo.py
rtk git diff --check
```

No `UI_BUILD_SKIPPED` result is acceptable.

Commit:

```text
feat(packaging): include the Studio in native Python artifacts
```

---

## Phase 4 — Accelerator discovery and native uv extras

### Objective

Add reproducible native accelerator selection without deleting or bypassing the container's
per-family first-boot installer.

### Files

- Modify `gpu_family.py`, `pyproject.toml`, `uv.lock`, `entrypoint.sh`, active accelerator docs,
  and ENV reference.
- Create `src/persona_forge/accelerator_manifest.py`.
- Create pure detector/mapping tests and `scripts/verify_torch_wheel_matrix.py`.
- Extend validator tests to enforce manifest/pyproject/entrypoint parity.

### Tasks

1. Preserve wheel family values `cpu/cuda/rocm/intel-xpu`. Do not add MPS.
2. Add successful `nvidia-smi` execution/version parsing for Windows/Linux. Presence of the binary
   without successful output is not a capable driver.
3. Keep generic Torch runtime device separate from active-backend effective device in doctor JSON.
4. Put pinned Torch/torchaudio versions, family indexes, CUDA floors, and extra names in one Python
   manifest. Validate static pyproject entries against it. Per the architecture doc's verified
   2026-08-29 index check: `cuda12` pins to `cu126` and `cuda13` pins to `cu130` (both are the
   wider-driver-floor point release within their major line; `cu129`/`cu132` are valid but stay
   escape-hatch-only via `ACCEL_TORCH_INDEX_URL`, not separate extras). `rocm` pins to index
   `rocm6.4` with `torch==2.9.1` — `rocm6.2`/`rocm6.3` have no cp313 wheels at all and must not be
   the manifest default.
5. Add mutually exclusive, platform-marked uv extras and explicit indexes using uv 0.12's
   documented syntax. Linux-only extras must not silently resolve on Windows/macOS.
6. Retain the container install block and its `ACCEL_TORCH_INDEX_URL`/
   `ACCEL_TORCH_VERSION` escape hatches. Add `ACCEL_TORCHAUDIO_VERSION`; if absent, preserve the
   old custom-version compatibility rule and otherwise use the manifest pin.
7. Fix stale container defaults/indexes instead of deleting the installer. Keep the persisted
   marker and install-failure semantics.
8. The live verifier checks exact cp313 target artifacts, hashes/index URLs, and writes a dated JSON
   receipt outside Git. A network failure is not proof of absence; rerun with approved network
   access and retain raw evidence.

### Resolution gates

Use current uv target names and `--locked --dry-run`:

```bash
rtk uv sync --locked --dry-run --python-platform x86_64-pc-windows-msvc --extra cuda12
rtk uv sync --locked --dry-run --python-platform x86_64-pc-windows-msvc --extra cuda13
rtk uv sync --locked --dry-run --python-platform x86_64-unknown-linux-gnu --extra cuda12
rtk uv sync --locked --dry-run --python-platform x86_64-unknown-linux-gnu --extra xpu
rtk uv sync --locked --dry-run --python-platform x86_64-unknown-linux-gnu --extra rocm
rtk uv sync --locked --dry-run --python-platform aarch64-apple-darwin
```

Add negative tests for XPU/ROCm on Windows/macOS and mutual-extra conflicts. Resolution is metadata
evidence only.

### Gate 4

Gate 4 = Resolution gates + pytest commands.

```bash
# Resolution gates — must pass before pytest
uv sync --locked --dry-run --extra cuda12 --python-platform x86_64-pc-windows-msvc
uv sync --locked --dry-run --extra cuda13 --python-platform x86_64-pc-windows-msvc
uv sync --locked --dry-run --extra xpu --python-platform x86_64-pc-windows-msvc
uv sync --locked --dry-run --extra rocm --python-platform x86_64-pc-windows-msvc

rtk proxy env PYTHONPATH=src:src/export uv run --frozen python -m pytest \
  tests/tier1_unit/test_gpu_family.py tests/tier1_unit/test_accelerator_manifest.py -v
rtk uv lock --check
rtk bash -n scripts/entrypoint.sh
rtk python scripts/validate_repo.py
rtk git diff --check
```

Commit:

```text
feat(accelerator): add native wheel recommendations and preserve container installs
```

---

## Phase 5 — One verified Qwen compatibility implementation

### Objective

Replace duplicated, silently best-effort site-package surgery with one exhaustive, idempotent
implementation used by setup and Docker.

### Files

- Create `src/persona_forge/compat_patch.py` and focused tests.
- Reduce `scripts/patch_local_compat.py` to a compatibility wrapper.
- Modify Dockerfile to run the same module after dependency installation.

### Tasks

1. Address existing `src/persona_forge/transformers_compat.py`: determine whether it is superseded
   by the new unified patch system or how it interacts with it. Use this rule: **remove if
   `compat_patch.py` covers all its transformations; otherwise document the remaining gap** and
   preserve it in the unified system.
2. Inventory every current Docker/script transformation. Each patch has an exact expected original
   match count and exact verified result.
3. Return structured statuses: `applied`, `already_applied`, `failed`. Zero/multiple unexpected
   matches fail.
4. Make second-run output byte-identical; specifically prevent duplicate rope-function insertion.
5. `setup` runs verification only when qwen is installed and applies patches only with explicit
   setup intent. Default installs are clean no-ops.
6. Test supported combinations explicitly:
   - Default, no qwen/openvino.
   - Qwen PyTorch.
   - Qwen + OpenVINO group.
   - Unsupported Windows Qwen/OpenVINO reports a clear diagnostic.
7. Do not remove `pydub` or `audioop-lts` in this plan.

### Disposable-environment gate

In a temporary uv environment install the qwen extra, apply once, verify, apply twice, compare
hashes, import qwen, and run a hardware-free construction/import smoke. Do not patch the shared
development environment as evidence.

### Gate 5

Gate 5 = Disposable-environment gate + pytest commands.

```bash
# Disposable-environment gate — must pass before pytest
mktemp -d && cd $(mktemp -d)
uv venv .venv && source .venv/bin/activate
pip install qwen3-tts[transformers]
python -c "from persona_forge.compat_patch import apply_qwen_patches, verify_qwen_patches; print(apply_qwen_patches())"
python -c "from persona_forge.compat_patch import verify_qwen_patches; print(verify_qwen_patches())"

rtk proxy env PYTHONPATH=src:src/export uv run --frozen python -m pytest \
  tests/tier1_unit/test_compat_patch.py -v
rtk python scripts/validate_repo.py
rtk git diff --check
```

Commit:

```text
fix(qwen): make compatibility patching exhaustive and idempotent
```

---

## Phase 6 — Portable-package CI and native runners

### Objective

Turn one-time manual claims into regression protection while keeping fake, resolution, cross-build,
native-runtime, image, and model/IR evidence distinct.

### Cross-repository prerequisite

Use the actual labels inventoried in Phase 0. If native macOS/Windows labels do not exist, add them
through a separate, explicitly scoped runner-infrastructure change in `../llama-monitor-runner`.
Do not silently edit the sibling repo from the Persona Forge implementation branch. The existing
`arc-llama-monitor` scale set is repository-scoped to Local LLM Foundry and cannot be used directly.
Create a Persona Forge-scoped scale set with an immutable runner-image tag/digest. First reconcile
the runner workflow preflight's `darwin25.1` osxcross tag with the Dockerfile's actual `darwin25.5`
base. The new Linux cross runner is suitable for resolution and Rust cross-builds, not native Python
runtime proof.

### Workflow tasks

1. Preserve current fake CI on `arc-general`.
2. Add portable-package jobs for Linux and actual native macOS/Windows:
   - `uv lock --check` and `uv sync --locked`.
   - semantic path/bootstrap/CLI tests.
   - mandatory npm CI/check/build.
   - wheel/sdist build and member inspection.
   - non-editable installed console script from outside checkout.
   - read-only doctor.
   - fake-runtime semantic readiness and clean shutdown.
3. Add target-resolution jobs with `--python-platform`; do not install foreign wheels.
4. Include `pyproject.toml`, `uv.lock`, packaging, entrypoint, and frontend build inputs in workflow
   path filters.
5. Preserve `ready-to-test` image build/import smoke on `arc-general-docker`.
6. Upload full logs and machine-readable receipts on failure and success.
7. Pin every new action by full commit SHA, matching existing workflow policy.

### Gate 6

- Local workflow/validator tests pass.
- A PR run shows green fake, package, frontend, and target-resolution jobs.
- Native jobs identify their real OS; a cross runner cannot satisfy them.
- Apply `ready-to-test` only after local gates pass; record image/import-smoke URL and result.

Commit:

```text
ci(packaging): validate native Python artifacts across platforms
```

---

## Phase 7 — Optional thin native launcher and release artifacts

### Objective

Reuse the Local LLM Foundry runner/release pattern for convenient platform archives without
freezing the Python ML stack into a monolithic executable. This phase is downstream of the green
wheel/full-Studio path and does not block declaring that core native path supported. If launcher
archives are released, every gate in this phase becomes mandatory for those artifacts.

### References

- `../local-llm-foundry/.github/workflows/release.yml`.
- `../local-llm-foundry/scripts/build-single-target.sh`.
- `../local-llm-foundry/scripts/validate-release-contract.mjs`.
- `../llama-monitor-runner/Dockerfile` and ARC deployment docs.

### Files and artifacts

- Add the small Rust bootstrap as the in-repository `launcher/` project. Moving it to a separate
  repository is a later architecture change and is not a worker decision in this plan.
- Add persona-specific build/preflight/release-contract scripts and workflow.
- Produce:
  - Linux x86-64 archive.
  - Windows x86-64 zip.
  - macOS ARM64 tarball.
  - Linux ARM64 only as experimental until native runtime evidence exists.

Each archive contains exactly the architecture-contract payload: launcher, pinned uv binary,
wheel, hash-locked target requirements, manifest, and README.

Build targets are `x86_64-unknown-linux-musl`, `aarch64-unknown-linux-musl`,
`x86_64-pc-windows-gnu`, and `aarch64-apple-darwin`. Add musl targets/preflight to the Persona
Forge release runner rather than creating a new high glibc floor for a tiny launcher.

### Launcher behavior

1. Validate its bundle manifest before mutation.
2. Create a versioned app-managed Python 3.13 environment under the state root.
3. Use bundled uv to create the venv and `uv pip sync` the target hash-locked requirements.
4. Install the bundled wheel with `--no-deps`, verify its hash, and exec its CLI.
5. Pass `doctor/setup/serve` arguments through. Do not log tokens or environment secrets.
6. Models and accelerator wheels remain separate downloads; no weights/IR/audio ship in archives.
7. Updates are explicit and atomic. A failed update keeps the previous environment launchable.
8. Before bundling uv, verify its redistribution license and the official checksum source. Fetch
   the pinned target binary during the build, verify SHA-256, and never use `curl | sh`.

### Release contract

Copy the Foundry pattern, changing only asset names/schema:

- Exact archive members; missing/extra required files fail.
- `checksums.json` covers every released file with SHA-256 and exact version.
- `manifest.json` includes source SHA, wheel/lock hashes, Python constraint, platform, support tier,
  and whether code signing was verified.
- Intermediate artifacts use short retention.
- No signed/notarized claim unless secrets and verification are configured.
- Cross-build success is not native runtime success.

For tag `persona-forge-vX.Y.Z`, the exact release set is:

```text
persona_forge-X.Y.Z-py3-none-any.whl
persona_forge-X.Y.Z.tar.gz
persona-forge-bootstrap-linux-x86_64.tar.gz
persona-forge-bootstrap-linux-aarch64.tar.gz
persona-forge-bootstrap-windows-x86_64.zip
persona-forge-bootstrap-macos-aarch64.tar.gz
checksums.json
```

The validator checks the tag against `pyproject.toml`, exact asset membership, wheel version and
console metadata, packaged UI, archive member lists, launcher-reported source/version, and exact
checksum-key equality. Its self-test creates real ZIP/tar fixtures and covers missing, extra, and
checksum-mismatch cases.

### Gate 7

- Preflight proves every cross tool and pinned uv input exists.
- Release-contract self-tests include positive, missing-member, extra-member, and checksum mismatch.
- Every archive runs `launcher doctor --json` on its target-native runner.
- Windows/macOS processes are retained and terminated in `finally` during serve smoke.
- Checksums and non-Git receipt paths are recorded.

Commit:

```text
feat(launcher): add verified cross-platform native bootstrap archives
```

---

## Phase 8 — Active documentation and semantic validation

### Objective

Update every active authority and prevent future drift. Do not edit archive history merely to make
a broad grep green.

### Migration documentation

Add a Docker-to-native migration guide in `docs/MIGRATION.md`:
- Environment variable mapping (Docker vs native variables)
- Path changes and model cache migration steps
- Pros/cons of each approach
- Port conflict warnings (both can't use 8318 simultaneously)

### Required documentation updates

- `README.md`, `docs/README.md`, `docs/HOW_TO_RUN.md`, and new/updated `docs/RUN_LOCAL.md`.
- `docs/ENV_REFERENCE.md` and `.env.example` with host-vs-runtime variable mapping.
- `docs/dev/LOCAL_SETUP.md`, `validation_checks.md`, and `INTERNAL_OPERATIONS.md`.
- `docs/TEST_STRATEGY.md` changed-X mapping.
- `docs/architecture/ACCELERATOR_FAMILIES.md` with separate native/container mechanisms.
- `docs/agent-reference/RUNTIME_AND_MEMORY.md` only where launch behavior genuinely changes.
- Dockerfile opening comment.

### Validator tasks

Add semantic validator/tests for:

- Console entry point and supported Python bound.
- Exact Docker container path defaults and one-worker command.
- Accelerator manifest/extra/index parity.
- Active docs not advertising stale container pins/indexes.
- Active docs not claiming Docker is required/canonical-only, unset backend selects Qwen/OpenVINO,
  or the advanced HOW_TO_RUN default is OpenVINO. Archive history is excluded deliberately.
- Workflow inputs/path filters for package-affecting files.
- Required artifact/checksum contract.
- Host-side and runtime-side environment names not being conflated.

Use allowlists for intentional Docker/archive literals. Do not use a weak regex scan as the primary
Windows or path proof.

### Gate 8

Run common verification plus focused validator tests, `rtk uv lock --check`, wheel/archive
inspection, and all green CI receipts. Documentation claims must be no stronger than the completed
hardware gates in Phase 9.

Commit:

```text
docs(setup): document native container and launcher workflows
```

---

## Phase 9 — Real-host, container, rollback, and release gates

### Shared readiness harness

Use one checked-in harness based on `subprocess.Popen`, `time.monotonic`, `urllib.request`, and a
retained log. It must:

1. Fail if the child exits, JSON is malformed after the deadline, `status=error`, backend differs,
   or the deadline expires.
2. Accept readiness only when `service_started=true`, expected backend is active, and no swap or
   reconfiguration is underway.
3. Record `model_loaded` without requiring it forever; idle unload may make it false later.
4. Terminate, wait, then kill only on timeout in `finally`.

### Gate 9A — macOS Apple Silicon

From a clean temporary environment and source SHA:

- Locked sync, installed CLI, setup, packaged UI, doctor JSON.
- Pocket-TTS reaches semantic readiness and completes a deterministic generation smoke.
- Record generic Torch MPS availability separately; do not say Pocket used MPS.
- Wheel target-native doctor/serve smoke. If launcher archives are being released, also smoke the
launcher archive.

### Gate 9B — Windows x86-64 + NVIDIA

Use PowerShell with `Start-Process -PassThru` inside `try/finally`:

- Default Pocket-TTS/Waitress full-Studio readiness and generation smoke.
- Driver probe recommends the validated CUDA extra.
- After locked CUDA sync, record Torch/torchaudio local versions and
  `torch.cuda.is_available()`/device name.
- Do not claim Qwen/OpenVINO Windows support.
- Stop the process on every path and retain logs/health JSON.

### Gate 9C — docker-agent container parity and Intel XPU

Before any mutation, request explicit approval because docker-agent is shared production
infrastructure. Use the canonical `docker-agent` SSH alias and paths from INTERNAL_OPERATIONS; do
not log in as root while operating a nick-owned checkout.

1. Record load, free RAM, swap, current immutable image, and rollback command.
2. Build/pull the exact branch image through the documented workflow. Inspect effective Compose
   image configuration and `docker inspect`; `scripts/dev-deploy.sh --image` alone is not proof the
   running service uses that image.
3. Touch only `persona-forge`. Never touch unrelated containers.
4. Poll semantic readiness, run a generation smoke, and print `paths.describe_paths()` inside the
   container. Exact legacy mount targets must remain.
5. For XPU, separately record family detection, installed wheel/source, `torch.xpu.is_available()`,
   effective device, fp64-emulation state, and an actual supported model/OmniVoice smoke.
6. Record the Compose 120-second start period separately from Dockerfile's image-level 10-minute
   healthcheck setting.
7. Restore the previous immutable image and prove readiness. Then restore the candidate if release
   testing continues. Record that rollback was tested.

### Gate 9D — Qwen/OpenVINO

On docker-agent only, follow the archived OpenVINO staged gates when model execution changed:
baseline, FP32 tensor/token/cache parity, quantized accuracy, listening, warm median/p95/RTF/RSS,
and PyTorch rollback. Record model revision, IR metadata hash, capacity, compression, explicit or
stateful cache mode, prompt, seed, and non-Git artifacts. If this implementation did not change
model execution, mark these fields N/A with evidence rather than rerunning export unnecessarily.

### Hardware receipt schema

Every receipt includes source/dirty state, lock and artifact SHA-256, OS/architecture/Python/uv,
Torch/torchaudio/driver/device data, doctor JSON, complete health JSON, backend/effective device,
model/IR metadata, prompt/settings, latency/RSS where applicable, exact commands and exit codes,
failure/first divergence, artifact paths, and rollback result.

No Phase 9 row may remain `DEFERRED` when its platform is claimed supported.

---

## Phase 10 — Final PR and handoff

### Final verification

Run the common verification block, real Torch lane when dependency/bootstrap behavior changed,
`rtk uv lock --check`, isolated wheel/sdist tests, launcher release-contract tests, and confirm all
required CI/hardware receipts refer to the final source SHA.

Review the complete diff; ensure no weights, IR, audio, tokens, PEM files, `.env`, local receipts,
or generated caches are tracked.

### PR metadata

Suggested title:

```text
feat(runtime): support native Persona Forge setup and serving
```

Required body block, without Markdown bullets inside it:

```text
BEGIN_COMMIT_OVERRIDE
feat(paths): add native state paths without changing container mounts

feat(cli): add native setup doctor and serve commands

feat(packaging): distribute the Studio and platform launcher metadata

feat(accelerator): add native wheel selection without removing container installs

fix(qwen): make compatibility patching exhaustive and idempotent

ci(packaging): validate native packages and target resolution

docs(setup): document native container and launcher workflows
END_COMMIT_OVERRIDE
```

Apply `ready-to-test` only after local validation is green and container inputs are final.

### Required handoff

```text
Source commit and dirty state:
Wheel/sdist/launcher names and SHA-256:
Container image tag and digest:
Model revision:
IR metadata hash or N/A:
Completed milestones:
Remaining release gates:
Exact validation commands and results:
Native target/hardware receipts:
Benchmark prompts and runtime settings:
Known divergences and first failing step:
Non-Git artifact locations:
Rollback procedure:
Rollback tested:
```

### Rollback

Use the previous immutable image/archive or revert the contiguous implementation commits in reverse
dependency order. Never revert an early paths/package commit while retaining later commits that
import its APIs.
