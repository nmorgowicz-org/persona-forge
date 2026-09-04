# Persona Forge — Agent Guide

## Agent Operational Guidelines

To ensure code integrity and prevent accidental deletions:
- **Post-Edit Diffing**: Run `git diff` after non-trivial edits to verify exactly what changed.
- **Precise Anchoring**: Insert new code above or below existing blocks rather than replacing function signatures.
- **Context Verification**: Re-read the surrounding block before editing to ensure the `oldString` is unique and non-destructive.
- **Verification**: Always run provided lint/typecheck commands after implementation.

## Shell command policy

- `rtk` may be used for routine commands when its compressed output remains complete and
  trustworthy for the task.
- Switch to the raw command whenever compression hides, truncates, rewrites, or otherwise
  complicates evidence needed for debugging, validation, exact-text review, or handoff.
- If an `rtk`-wrapped command produces ambiguous or problematic output, rerun it raw before
  drawing conclusions or making changes.

## How to use this guide

- This is your single source of truth for working in this repo. `docs/README.md` is the full doc map.
- When implementing or modifying features, treat `docs/plans/` as authoritative and binding.
  Do not silently relax stack choices, runtime constraints, or memory rules to "simplify"—
  only propose alternatives explicitly.
- Read before changing:
  - Runtime invariants, memory rules, LOW_RAM_MODE → `docs/agent-reference/RUNTIME_AND_MEMORY.md`
  - Export system behavior and fragility → `docs/agent-reference/EXPORT_SYSTEM.md`
  - Transformers 5 compatibility hacks → `docs/agent-reference/TRANSFORMERS_COMPAT.md`
  - VoiceDesign model + frontend → `docs/architecture/VOICE_DESIGN.md`
  - Local validation commands → `docs/dev/validation_checks.md`
  - HTTP endpoints → `docs/api/HTTP_API_REFERENCE.md`
  - Environment variables → `docs/ENV_REFERENCE.md` (accelerator-family vars are in
    `docs/architecture/ACCELERATOR_FAMILIES.md`, not yet in ENV_REFERENCE)
  - Test tiers → `docs/TEST_STRATEGY.md`

If a change conflicts with any of these, stop and propose alternatives explicitly.

## Quick orientation

```
src/persona_forge/     Flask app, model runtime, config, Pocket-TTS/OpenVINO/PyTorch runtimes, OmniVoice engine, libraries
src/export/            OpenVINO export/quantization, parity tests, benchmark tooling
frontend/              React 19 + Vite 8 + Tailwind 4 SPA (built in frontend-build stage, served at /)
scripts/               entrypoint.sh (container entrypoint), export.py, dev-deploy.sh, validate_repo.py, download_model.py
tests/                 tier1_unit/  tier2_backend/  tier3_api_integration/  ui/ (Playwright E2E + capture harness)
requirements/          requirements-{runtime,openvino,export,pocket-tts}.txt
Dockerfile             Single image (frontend-build stage + runtime); ENTRYPOINT=entrypoint.sh, default CMD = gunicorn
compose.yml            Services: persona-forge (serving) + export (profile `export`, one-time IR export) — one image
```

`PYTHONPATH=/app/src:/app/src/export` — both `persona_forge.*` and export modules are importable inside the container.

**Native install (no Docker).** `[tool.uv] package = true`; `uv sync --locked` installs `persona_forge`
into `.venv` (editable, via Hatchling) and exposes the `persona-forge` console script
(`doctor`/`setup`/`build-ui`/`serve` — `src/persona_forge/cli.py`). `src/export` is not packaged and stays
`PYTHONPATH`-only tooling — keep `PYTHONPATH=src:src/export` for anything importing export modules (e.g.
running the full test suite). Docker remains the reproducible deployment/export path; this does not change
`Dockerfile`/`compose.yml`/`entrypoint.sh`. Details: `docs/plans/20260829-no_more_docker_architecture.md`.

**Product.** Open-source voice cloning and voice design studio: voice cloning, Qwen VoiceDesign,
accent design and audition via OmniVoice, Stitch Studio (segment timeline assembly), prosody
variants/adjustment, segments and voice libraries, projects, and an OpenAI-compatible API.
Overview: `docs/architecture/SYSTEM_OVERVIEW.md`; data model: `docs/architecture/STUDIO_LIBRARIES.md`.

**TTS backends.** `TTS_BACKEND` (canonical values `pytorch` / `openvino` / `pocket_tts`;
`pocket-tts` is normalized in `config.py`):
- `pocket_tts` — the product default. Self-contained, CPU-only, no IR export needed.
  See `docs/architecture/pocket_tts_integration.md`.
- `openvino` — Intel CPU acceleration for Qwen3-TTS (Base, VoiceDesign, custom voices);
  needs a one-time IR export via the compose `export` service.
- `pytorch` — baseline/fallback for Qwen3-TTS.

**OmniVoice (k2-fsa/OmniVoice) is NOT a TTS backend.** It is a separate voice-designer
subsystem (accent candidates, audition, Stitch Studio). See `docs/architecture/OMNIVOICE_REFERENCE.md`.

**Accelerator families (Phase A6).** `GPU_FAMILY` (default `auto`) resolves
`cpu`/`intel-xpu`/`cuda`/`rocm` via torch-independent PCI/device probes; the entrypoint does a
first-boot per-family torch install into the persisted `/opt/accel-venv` volume. intel-xpu is
validated on hardware; cuda/rocm are unvalidated. Details: `docs/architecture/ACCELERATOR_FAMILIES.md`.

**One image, two behaviors.** `scripts/entrypoint.sh` is the container ENTRYPOINT; it applies
`LOW_RAM_MODE` tuning and accelerator-family setup before exec-ing the CMD. The serving container
runs the image's default CMD (gunicorn). The export service overrides CMD with `python scripts/export.py`.

**Gunicorn constraints.** Always `-w 1 -k gthread --threads 4`. Never `--preload`. Never more than
one worker. The single worker holds the model and serializes all inference through a
`concurrent.futures.ThreadPoolExecutor(max_workers=1)` to prevent concurrent model access.

**Model size and capacity.** `MODEL_SIZE` (0.6B or 1.7B; 1.7B recommended) is mapped in
`model_config.py` to the checkpoint and IR paths. K/V capacity is env-driven:
`TTS_MAX_SPEECH_SECONDS` (default 300s) → capacity = round(seconds × 12 Hz) → capacity-keyed IR
paths (`/ov/<size>/main_stateful_cap{N}.xml`); changing it requires a re-export. VoiceDesign is
separate: `VOICE_DESIGN_MODEL_SIZE` (1.7B), `VOICE_DESIGN_MAX_SPEECH_SECONDS` (default 30s →
cap 360), IR under `/ov/<size>-voicedesign/`. Quantization: 0.6B ships INT8 main + INT8 stateful
predictor (cap 32 file); 1.7B ships INT4 asymmetric (group 32) main + INT8 explicit (non-stateful)
predictor. Details: `docs/agent-reference/RUNTIME_AND_MEMORY.md`, `src/persona_forge/presets.py`.

## Current state

- Single image ships serving and export tooling. CI publishes it as `ghcr.io/nmorgowicz-org/persona-forge:<sha>`.
- `pocket_tts` is the product default; `openvino`/`pytorch` run the Qwen3-TTS engines (opt-in).
  `TTS_BACKEND=pytorch` is the tested rollback baseline.
- OpenVINO accelerates both Qwen3-TTS transformer cores and the FP32 vocoder.
- Both size profiles land at ~5.4–6.9 GiB steady serving RSS on the validated host. Export needs up to 13 GiB.
- `LOW_RAM_MODE=1` (compose default) enables glibc malloc tuning + idle unload. Python calls `malloc_trim(0)`
  after idle unload. LD_PRELOAD allocator replacement (jemalloc, tcmalloc) is incompatible with OpenVINO
  `compile_model()` under transformers 5.x — both caused SIGABRT/SIGSEGV. `libjemalloc2` remains in the image for reference.
- OV compiled kernel cache at `/ov/cache` (default) eliminates ~60–120s recompilation on every restart.
- Full model export, parity, and performance benchmarks run on `docker-agent`, not on ARC runners.

## Architecture invariants

- Two nested autoregressive transformer paths (Qwen3-TTS): 28-layer main talker (codebook 1), 5-layer code predictor (codebooks 2–16). Both must be accelerated.
- Keep prompt construction, embeddings, sampling, and lightweight glue in PyTorch.
- Export main and predictor transformer cores separately; validate K/V cache before introducing stateful models.
- Reuse persistent `InferRequest` objects; never create one per token or per request.
- Preserve the talker object's embeddings, projections, codebook heads, config, dtype, and device behavior.
- Preserve the HTTP API surface and its compatibility — core: `/generate`, `/v1/audio/speech`,
  `/health`, MP3/WAV output, serialized inference. Full inventory: `docs/api/HTTP_API_REFERENCE.md`.
- Keep `TTS_BACKEND=pytorch` as an explicit rollback path.
- Return HTTP 503 during initial startup (before `_service_started` is set). After first successful load,
  idle-unloaded requests block in the executor and reload transparently — do not 503 them.
- Studio libraries: the strict ID regexes (`vd_`/`seg_`/`proj_` + 12 hex) are the path-traversal defense
  for IDs that flow into filesystem paths. Data model: `docs/architecture/STUDIO_LIBRARIES.md`.

## Model and secret safety

Never commit to Git or bake into the image:
- HF model weights or cache directories
- Generated OpenVINO IR (`.xml`/`.bin`) or ONNX models
- Reference voice audio or generated speech
- HF tokens, GitHub tokens, PEM keys, `.env` files, or deployment credentials

Persistent host paths on `docker-agent`:
```text
/var/data/autopirate/persona-forge/model      ← HF cache (MODEL_CACHE_PATH)
/var/data/autopirate/persona-forge/openvino   ← OpenVINO IR  (OV_DATA_PATH)
```

## Dependency rules

- The OpenVINO stack (OpenVINO, NNCF, Transformers, Python) moves together; pin all of them.
  Pin authority: `requirements/requirements-*.txt` (image) and `pyproject.toml`/`uv.lock`
  (local dev). Do not copy version numbers into docs or plan files.
- `qwen-tts` is installed `--no-deps` because it hard-pins an older transformers.
  `requirements/requirements-runtime.txt` supplies the current transformers (including the
  CVE-2026-1839 fix); all other qwen-tts runtime deps are listed explicitly there.
  Re-verify export wrappers and the parity gate after any transformers bump.
- Install CPU-only Torch before `qwen-tts` to prevent CUDA library pulls.
- Do not update one OpenVINO-stack dependency in isolation without rebuilding the image and rerunning export parity.
- Optimum Intel is intentionally absent: the custom talker has no registered exporter in `TasksManager`.
  Use `openvino.convert_model` + `nncf.compress_weights` directly.
- Do not pass datasets, AWQ, GPTQ, LoRA correction, or sensitivity selection to NNCF
  `compress_weights`; the API rejects them. Do not substitute W8A8 `nncf.quantize`
  (caused ~23 dB SNR regression at M6).
- Renovate tracks pip requirements, Docker base images, and GitHub Actions. OpenVINO, Qwen-TTS,
  and PyTorch CPU-stack updates must not auto-merge.

## Build and CI

- `arc-general`: validation, labels, and release automation.
- `arc-general-docker`: native Linux AMD64 image builds.
- CI builds one image per run — no matrix. Smoke test imports all export and serving modules.
- Image build runs on PRs with `ready-to-test` label. Tag pushes (`persona-forge-v*`) publish to GHCR.
- `main` pushes alone do not build or publish.
- `buildcache` and `latest` are protected from cleanup. Keep at least 5 older versions for rollback.
- Production Compose must pin the SHA tag or digest; never `latest`.

GHCR pulls on `docker-agent` need a `read:packages` token. Pass via `docker login --password-stdin` only; never echo or embed in Compose.

## Development (docker-agent)

The team runs three docker LXC boxes; Persona Forge lives on the **docker-agent** box (SSH alias
`docker-agent`). Compose dir: `~/docker/docker-agent/`. The codified loop is `scripts/dev-deploy.sh`
(run on docker-agent from `~/projects/persona-forge`: `[branch] [--image] [--no-restart]` — builds the
frontend and `compose up -d` with the dev override that bind-mounts source). Operational details:
`docs/dev/INTERNAL_OPERATIONS.md`.

### Rapid Debugging (Preferred for UI/small fixes)
1. Sync specific files: `scp frontend/src/components/AppShell.tsx nick@docker-agent:~/projects/persona-forge/frontend/src/components/AppShell.tsx`
2. Build frontend: `ssh docker-agent "cd ~/projects/persona-forge/frontend && npm run build"`
3. Restart the container: `ssh docker-agent "docker compose -f ~/docker/docker-agent/docker-compose.yml -f ~/docker/docker-agent/docker-compose.persona-forge-dev.yml restart persona-forge"`

### Permanent Changes
1. Commit and push changes to the working branch.
2. Sync the codebase: `ssh docker-agent "cd ~/projects/persona-forge && git pull origin <branch>"`
3. Build frontend (if applicable): `ssh docker-agent "cd ~/projects/persona-forge/frontend && npm run build"`
4. Restart the container (or run `scripts/dev-deploy.sh`).

The dev compose file (`~/docker/docker-agent/docker-compose.persona-forge-dev.yml`) enables bind-mounts for source code synchronization.

## Required validation

Repository-only changes:
```bash
python scripts/validate_repo.py
docker compose config --quiet   # REF_AUDIO_PATH and REF_TEXT are optional
git diff --check
```

Container or dependency changes: apply `ready-to-test` to trigger the image build and import smoke test on `arc-general-docker`. Do this only after local validation passes.

Model execution changes (Qwen3-TTS/OpenVINO path) also require the staged gates from `docs/archive/openvino/OPENVINO_IMPLEMENTATION.md`:
1. PyTorch baseline/profile
2. FP32 OpenVINO tensor, token, position, and cache parity
3. INT8 accuracy and greedy-code agreement
4. Voice quality listening checks
5. Warm median/p95 latency, RTF, and peak RSS on `docker-agent`
6. PyTorch rollback verification

## Test tiers

`tests/` has four directories: `tier1_unit/` (repo/unit, no model), `tier2_backend/` (container, no
weights), `tier3_api_integration/` (HTTP API), and `ui/` (Playwright E2E + screenshot capture
harness — `tests/ui/README.md`). Canonical tier definitions, the changed-X→run-Y quick reference,
and the parity gates live in `docs/TEST_STRATEGY.md` — consult it before running tests.

## Troubleshooting

### CPU Torch/Torchaudio unresolvable
Inspect the CPU wheel index directly. Keep TORCH_VERSION and TORCHAUDIO_VERSION as independent Dockerfile ARGs. After changing a pin, rebuild and smoke-test.

### Export expects input_ids
The generation path supplies `inputs_embeds`. Wrappers must expose embeddings as the primary input. An `input_ids`-only IR is incompatible with the current generator.

### Output matches prefill but diverges during decode
Check in order: K/V layer/key/value ordering; cache sequence length; `cache_position`, attention mask, position IDs; main vs. predictor reset scope; predictor codebook embedding and output head. Log the first divergent step before inspecting audio.

### Stateful generation repeats or contaminates requests
- Main state resets once per utterance; predictor state resets once per audio frame.
- Never share an `InferRequest` across concurrent requests.
- Never create a new request per token.
- Use `query_state()` in tests to confirm reset length.

### OpenVINO loaded but RAM stays high
The hybrid implementation keeps both PyTorch and OpenVINO weights resident. RSS drops only after unused PyTorch layers are released. Measure after GC; allocator retention can hide freed tensors. Do not delete the talker object — embeddings, projections, and codebook heads are still needed.

### INT8 runs but not faster
Confirm both cores use OpenVINO; confirm IR weights are compressed; check MatMul activation quantization; benchmark group sizes 0/32/64; profile main vs. predictor; check for per-token array copies; verify host isn't swapping.

### Export killed / VM swaps heavily
Stop `persona-forge` before exporting (13G export + 10G serve = OOM on 15 GiB host). Never load a second model inside the existing container. Keep IR on the persistent OV volume.

### ARC job queued
Confirm `arc-general` or `arc-general-docker` label; confirm ARC GitHub App is installed; check scale set, ephemeral pod, and listener logs.

### GHCR build cache fails
Use the `:buildcache` reference with `mode=min,ignore-error=true`. Cache failure must not invalidate an otherwise successful build.

## Agent handoff requirements

Every handoff must state:
- Source commit and image tag/digest
- Model revision and IR metadata hash
- Completed milestones and remaining release gates
- Exact validation commands and results
- Benchmark prompts and runtime settings (FP32/INT8, explicit/stateful cache)
- Known divergences, first failing step, and non-Git artifact locations
- Rollback procedure and whether it was tested

## Production VM safety (docker-agent)

- One of three shared live docker LXC boxes — prefer read-only inspection unless the user explicitly authorizes changes.
- Stop only `persona-forge` during export; never touch unrelated containers (`litellm*`, `headroom-proxy`, `crowdsec`, `hermes-*`, `*arr`, `searxng`).
- Never run two large model jobs at once (export + serve will OOM a 15 GiB box).
- Record host load, available RAM, and swap alongside performance results.
- On failure, restore the previous immutable image or switch to `TTS_BACKEND=pytorch`.
- Port 8318 has no auth or TLS; keep it on a trusted network or behind an authenticated reverse proxy.

## Commit and PR conventions

Use Conventional Commits (`feat`, `fix`, `perf`, `refactor`, `test`, `docs`, `build`, `ci`, `chore`, `revert`). Use squash merge.

**PR titles are the squash-merge commit messages consumed by Release Please.** They must be valid Conventional Commits or Release Please will fail to parse the release.

Requirements:
- Must start with `type:` or `type(scope):` — no leading spaces, no emoji unless requested, no markdown in the title.
- Must not contain prefixes, extra characters, or malformed type tokens.
- Release Please uses a standard Conventional Commits parser (release-type: simple); ensure the title parses cleanly.

So user-facing changes need a `feat:` or `fix:` title.

**Version bump rules** (squash-merge, one PR = one evaluated commit):
- `feat:` in PR title → minor
- `fix:` in PR title → patch
- `feat!:` in PR title OR `BREAKING CHANGE:` footer in PR body → major
  - Example: `feat(runtime)!: drop legacy /v1/generate endpoint`
  - Or include at the bottom of the PR body: `BREAKING CHANGE: legacy /v1/generate endpoint removed, use /v1/audio/speech`

**Forcing an exact version:** add a `Release-As: X.Y.Z` trailer to a merged commit message to force
that exact version regardless of commit type — this is checked before any breaking/feat
heuristics, so it's the reliable way to land a specific version (e.g. `Release-As: 1.0.0`).

**Scopes** are free-form — choose one that matches the change area, e.g.
`(model)`, `(openvino)`, `(export)`, `(runtime)`, `(frontend)`, `(docker)`, `(deps)`, `(ci)`,
`(docs)`, `(test)`. A scope, if present, must match `^[a-z0-9][a-z0-9._/-]*$` — enforced by
`scripts/validate_repo.py`. Omit only if obvious.

Every implementation PR body must include a Release Please override block using this exact format:

- Each line is one Conventional Commit entry.
- Format: `type(scope): description`
- Do not prefix entries with Markdown bullets. Release Please parses the block as a
  commit message, so a leading `- ` makes the entry invalid.

Example:

```text
BEGIN_COMMIT_OVERRIDE
fix(model): correct seed max from 2^63-1 to 2^32-1

docs: restore advanced env var detail in .env.example and HOW_TO_RUN.md
END_COMMIT_OVERRIDE
```

One Conventional Commit line per entry; separate multiple entries with a blank line; one
supported type per entry; no composite headers. Release Please version PRs are exempt.
Keep model artifacts and benchmark audio out of PRs.


<!-- headroom:memory-instructions -->
## Memory

Use the `headroom_memory` MCP server for persistent cross-session knowledge.

**Before** answering questions about prior decisions, conventions, project context,
architecture, user preferences, org info, codenames, debugging history, or anything
from past sessions — call `memory_search` first.

**After** making durable decisions, discovering conventions, or learning important
facts — call `memory_save` to persist them for future sessions.

Memory is your first source of truth for anything not visible in the current conversation.
