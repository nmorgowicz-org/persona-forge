# Post-Merge Initiatives — Comprehensive Plan (Authoritative Specification)

| Field | Value |
|---|---|
| Created | 2026-07-20 |
| Purpose | Single source of truth for three post-`feature/voice-style-foundation` initiatives |
| Companion | [`20260720-post_merge_initiatives_execution.md`](./20260720-post_merge_initiatives_execution.md) (execution router — do not implement from it alone) |
| Intended reader | An implementing agent (Sonnet sub-agent or local Qwen3.6-27B) briefed on one phase at a time |
| Supersedes | `20260715-capture_screenshot_harness.md` and `20260715-guided_experience_teaching_layer.md` (both folded in here; delete after this lands) |
| Status | Ready for implementation. Not started. |

> **How to read this document.** This is the *authoritative specification*: requirements,
> source-code detail, decisions, invariants, and exact gates live here. The companion doc is a
> low-context *router* — it tells an agent which section to read for the active phase and tracks
> completion, but it deliberately does not duplicate this content. Work one phase at a time. Do
> not start a phase until its dependencies' gates are green (see §5). Every gate carries a
> **taxonomy tag** (§4.3) telling you who can close it and whether it spends frontier quota.

---

## 1. Purpose & scope

Three initiatives, bundled because they share one execution model (phased briefs handed to a
local 27B or a Sonnet sub-agent) and because Initiative A underpins Initiative B:

- **Initiative A — uv local-dev migration (§6).** Replace the drift-prone, hand-assembled local
  `.venv` with a reproducible `uv`-managed environment (`pyproject.toml` + `uv.lock`). Motivated
  by a concrete failure found during planning: the local venv was missing `gunicorn` (declared
  in `requirements/requirements-runtime.txt`) because it had been built from the lighter root
  `requirements-dev.txt` and then hand-patched with the model deps. A lockfile eliminates that
  class of drift. **Container stays canonical** — this does not migrate the Docker build.

- **Initiative B — real-model capture harness (§7).** A local-only, real-model screenshot + GIF
  capture tier for the UI, modeled on `../llama-monitor/tests/ui/capture.mjs`, so any UI surface
  can be captured on demand for review. Additive to the existing fake-model CI tier. Its
  real-model tier needs a working runtime venv — which Initiative A provides (though it also runs
  on the current hand-assembled venv).

- **Initiative C — guided experience / teaching layer (§8).** The "teach the user *why*" layer:
  plain-language metric tooltips, one shared progressive-disclosure seam, an in-app
  glossary/troubleshooting KB, automated take diagnostics, and a persona-creation wizard.
  Frontend-heavy, independent of A and B.

**Ordering (see §5 for the full index):** A → B for the venv dependency; C is independent and may
run in parallel with either. Within A, A1→A2→A3 are ordered; A4 (runtime device seam) and A5
(accelerator wheels) are opt-in extensions that depend only on A2 and can be deferred or skipped.
Within B, B1→B7 are strictly ordered. Within C, C1/C2 are independent; C3→C4→C5 are ordered.

## 2. Research baseline (current-state facts — verified 2026-07-20)

Every fact below was checked against the working tree on 2026-07-20. Re-verify drift-prone facts
per §4.4 before relying on them; prefer the cited file/line over this summary if they disagree.

### 2.1 Dependency & environment layout

- **No `pyproject.toml`, no `uv.lock` exist yet** (greenfield uv adoption). `uv 0.11.16` **is**
  installed (`/opt/homebrew/bin/uv`). Python is **3.13** (venv `3.13.13`; CI pins `3.13`).
- Dependency manifests today:
  - Root `requirements-dev.txt` — the **light** dev/CI set: `Flask==3.1.3`, `httpx==0.28.1`,
    `numpy==2.4.6`, `pytest==9.1.1`, `pytest-xdist==3.8.0`, `PyYAML==6.0.3`, `requests==2.34.2`,
    `soundfile==0.14.0`, `librosa`, `pyloudnorm`. This is what **CI installs**
    (`.github/workflows/ci.yml:37`, `ci-ui.yml:41`) and what powers the fake-model server + unit
    tests. **No torch, no gunicorn, no transformers.**
  - `requirements/requirements-runtime.txt` — the **real backend** set: `flask==3.1.3`,
    **`gunicorn==26.0.0`**, `soundfile==0.14.0`, `accelerate`, `einops`, `librosa`,
    `onnxruntime`, `sox`, `transformers==5.12.1`, `pydub`, `pyloudnorm`, `faster-whisper`.
    A header comment explains the transformers situation (see §2.2).
  - `requirements/requirements-openvino.txt` — `openvino==2026.2.1`.
  - `requirements/requirements-export.txt` — `-r requirements-openvino.txt` + `nncf==3.2.0`.
  - `requirements/requirements-pocket-tts.txt` — `pocket-tts==2.1.0`.
- **torch/torchaudio are NOT in any requirements file.** They are installed by the Dockerfile
  (lines 34–36) from the PyTorch CPU wheel index: `torch==2.12.1`, `torchaudio==2.11.0`,
  `--index-url https://download.pytorch.org/whl/cpu`. The container is `linux/amd64`.
- **Local torch is already `2.12.1`, arm64, with MPS available** (`torch.backends.mps.is_available()
  == True`). So on this Apple-Silicon Mac the *default PyPI* torch wheel is the right one — the
  CPU-index pin is a container-only concern.
- Frontend E2E deps live in `tests/ui/package.json`: `@playwright/test`, **`puppeteer`** (already
  present). `ffmpeg 8.1.2` is installed as a **system** binary at `/opt/homebrew/bin/ffmpeg`
  (in the container it comes from `apt-get install ffmpeg`, Dockerfile:28). A system binary
  cannot live in a Python manifest.

### 2.2 Backend runtime facts

- **Entry point:** production is `gunicorn qwen3_tts.app:app` (Dockerfile:103). `src/qwen3_tts/app.py`
  also has a `__main__` block running the Flask dev server on hardcoded port 8318 (`app.py:2713-2714`).
- **Model loads at import time.** `src/qwen3_tts/model.py:669` runs
  `threading.Thread(target=_load_model_background, daemon=True, name="model-loader").start()` at
  module import. So merely importing `qwen3_tts.app` (which imports `model`) starts the background
  load — no explicit load call is needed. This is why the capture harness can spawn the Flask dev
  server and simply poll `/health` until ready.
- **Health:** `GET /health`; `health_state()` at `src/qwen3_tts/model.py:747` returns
  `model_loaded`, `service_started`, and on failure `error` / `_startup_error`. Readiness for the
  capture harness = `model_loaded: true`, **not** a bare HTTP 200.
- **The transformers/qwen-tts pin conflict (critical for Initiative A):** `qwen-tts==0.1.1`
  hard-pins `transformers==4.57.3`, but the app requires `transformers==5.12.1` (the
  requirements-runtime.txt comment cites CVE-2026-1839). The Dockerfile resolves this by
  installing `qwen-tts==0.1.1 --no-deps` (bypassing its pin) and separately listing its real
  transitive deps in requirements-runtime.txt (accelerate, einops, librosa, onnxruntime, sox,
  transformers). **OmniVoice** is installed `--no-deps` from a **pinned git commit**:
  `git+https://github.com/k2-fsa/OmniVoice.git@398b6113` (Dockerfile:39; the comment explains it's
  past 0.1.5 for `pad_duration`/`fade_duration` support; swap back to `omnivoice==0.1.5` once a
  PyPI release carries that commit). Its declared deps already match the runtime pins, so `--no-deps`
  is safe; `pydub` is the one genuinely new dep it needs (already in requirements-runtime.txt).
- **Verified real HTTP routes** (from `@app.<verb>` decorators in `src/qwen3_tts/app.py`, checked
  2026-07-20 — re-verify, do not hardcode from memory): `POST /voice_design`, `GET /voices`,
  `GET /voices/<id>`, `POST /voices/<id>/duplicate`, `POST /voices/<id>/set-active-variant`,
  `GET /voices/<id>/variants`, `POST /voices/<id>/project`, `POST /omnivoice/audition`,
  `GET /omnivoice/segments`, `POST /omnivoice/segments`, `POST /omnivoice/segments/<id>/project`,
  `POST /projects`, `POST /omnivoice/save`, `GET /health`.

### 2.3 Capture-harness facts

- `tests/ui/capture.mjs` (~180 lines) uses **puppeteer** (not Playwright), imports
  `startFakeServer` from `./run-server.mjs`, writes to `docs/screenshots/artifacts/<feature>/` via
  `outPath(feature, filename)`, holds scenarios in a `SCENARIOS` object, parses flags in
  `parseArgs` (`--scenario`, `--list-scenarios`, `--no-attach`, `--target`).
- `tests/ui/run-server.mjs` exports `startFakeServer({ port })` → `{ child, url, port,
  waitUntilHealthy, stop }`. Contains `resolvePython()` (venv resolution), the env block
  (`PYTHONPATH` = repoRoot + `src` + `src/export`, `VOICE_LIBRARY_DIR`, `FRONTEND_DIST_DIR`), a
  `waitUntilHealthy` poll loop, `stop()` with signal handlers, and an `import.meta.url` direct-run
  block. The fake server is `tests/ui/fixtures/fake_model_server.py` (uses
  `werkzeug.serving.make_server`).
- GIF port source: `../llama-monitor/tests/ui/capture.mjs` (~4407 lines) — functions
  `captureFrames`, `framesToGif` (two-pass ffmpeg `palettegen`/`paletteuse`), `cleanupFrames`.
- **Real host data dirs (privacy target): `./data/voices`, `./data/segments`** (bind-mounted in
  `compose.yml`). The harness must never touch them.
- `frontend/src/components/waveform/AlignmentCompare.tsx` has **zero** `data-testid`s.
  `omnivoice-result` testid already exists in `frontend/src/components/OmniVoicePanel.tsx:2407`.
- Library schema lives in `src/qwen3_tts/voice_library.py` (`save_voice`, variant funcs,
  `list_voices`, `duplicated_from`) and `src/qwen3_tts/segment_library.py` (`save_segment` /
  `list_segments`, layout `<SEGMENT_LIBRARY_DIR>/<id>/{clip.wav,meta.json}`, fields
  `project_id`/`project_name`/`feature_tags`/`tags`). `VoiceLibraryPage.tsx` `getSourceBadges`
  reads the fork-badge fields.

### 2.4 Guided-experience facts

- State store `frontend/src/store.ts` — plain **zustand** (`import { create } from 'zustand'`).
  Persistence is manual via `frontend/src/lib/theme.ts` (`loadStoredTheme`, `applyTheme`) called
  from `store.ts` — **there is no zustand `persist` middleware**; follow that same localStorage
  pattern for any new persisted setting. `Page` union and app state shape are in `store.ts`.
- Global shell/nav/toggles: `frontend/src/components/AppShell.tsx`.
- Metrics already computed backend-side: `src/qwen3_tts/audio_style.py` → `analyze_reference()`
  (line ~83) returns `speech_rate_proxy`, `pause_ratio`, `median_pause_ms`, `longest_pause_ms`,
  `pause_count`, `duration`.
- Existing pacing-warning + regen-cost UI: `frontend/src/components/OmniVoice/SegmentRackRow.tsx`.
- Content-map precedent to imitate for tooltips/glossary: `frontend/src/lib/accentBank.ts` →
  `FEATURE_INFO` (a `{ key: { label, description } }` map, consumed in `OmniVoicePanel.tsx`).

## 3. Decision register (frozen — do not reopen without a new user instruction)

- **D1 — Local spawn uses the Flask dev server, not gunicorn.** Rationale: works even on an
  incomplete venv, cross-platform (gunicorn is not Windows-friendly), zero worker config, port
  trivially controllable via `-c`. gunicorn remains the production/container server and is present
  once Initiative A installs the runtime set — but the harness does not depend on it. (§2.2, §7 B1)
- **D2 — The default lock is universal (macOS + linux) via a torch *override*, not an index
  split.** OmniVoice's git `pyproject.toml` declares a `pytorch-cuda` (`cu128`) index for torch on
  `linux`/`win32`; because OmniVoice is a **git source**, uv honors that metadata, so any competing
  `pytorch-cpu` index collides ("conflicting indexes for torch") and `uv lock` fails. **The fix
  (validated 2026-07-20 on macOS *and* on a real linux VM):** pin torch/torchaudio via
  `[tool.uv] override-dependencies = ["torch==2.12.1", "torchaudio==2.11.0", ...]`. An override
  *strips OmniVoice's per-package index association*, so torch resolves from default PyPI on both
  platforms — arm64 (cpu+mps) on macOS, and the CUDA-enabled-but-CPU-capable wheel on linux.
  `environments = ["sys_platform == 'darwin'", "sys_platform == 'linux'"]`. Proof: macOS lock =
  120 pkgs green; linux (dockermisc1, Ubuntu 26.04, no GPU) = 124 pkgs, `uv sync` installs,
  `torch 2.12.1+cu130` imports with `cuda.is_available()==False` and runs on CPU, OmniVoice imports
  OK. **Caveat:** the linux install is ~5.5 GB (the unused NVIDIA libs); a *slim* CPU build is an
  advanced/deferred path (D9). The container Dockerfile stays canonical, non-uv (D3). (§2.1, §6 A1)
- **D3 — The container Dockerfile stays canonical and is NOT migrated to uv in this work.** uv is
  adopted for *local dev* only. A future container-uv migration is out of scope here. (§1)
- **D4 — CI is not broken by Initiative A.** CI installs `requirements-dev.txt`; that file stays
  authoritative for CI. The uv `dev` group must stay in sync with it (or, later and optionally,
  CI migrates to uv — deferred, not in this plan). (§2.1, §6 A3)
- **D5 — `override-dependencies` does double duty.** `[tool.uv] override-dependencies =
  ["transformers==5.12.1", "torch==2.12.1", "torchaudio==2.11.0"]`: the `transformers` entry
  defeats qwen-tts's hard `4.57.3` pin (uv has no per-package `--no-deps`, so qwen-tts's real
  transitive deps are also declared explicitly in `[project.dependencies]`); the `torch`/
  `torchaudio` entries strip OmniVoice's cu128 index association (D2). OmniVoice is a pinned-git
  source. **Proven end-to-end (2026-07-20):** lock carries `transformers==5.12.1` + torch/
  torchaudio from PyPI (no cu128 collision), and a real `uv sync` on linux installs and imports.
  (§2.2, §6 A1)
- **D6 — Capture harness is additive and local-only.** It never runs in CI, never weakens the
  fake-model tier, never touches real data dirs. (§4.1, §4.2, §7)
- **D7 — Progressive disclosure never unmounts power-user controls.** Guided mode only
  collapses/hides behind "Show advanced." One shared seam, not per-panel. (§8 C2)
- **D8 — Instructional copy lives in data/markdown files, not inline JSX**, so it is reviewable
  and a `[decide-once]` gate rather than a code change. (§4.3, §8 C1/C3)
- **D9 — Accelerator support has two orthogonal axes, kept separate.** (a) *Runtime device* —
  which device an installed build runs on — is auto-detected with an env override (A4:
  `TTS_DEVICE` for the pytorch backend `cpu`/`cuda`/`mps`/`xpu`; `OPENVINO_DEVICE` for the
  openvino backend `CPU`/`GPU`/`AUTO`). (b) *Install build* — which torch wheel lands on disk —
  is handled by the Option-C default lock (D2): a plain `uv sync` gives arm64 cpu+mps on macOS and
  a CPU-capable/CUDA-auto wheel on linux, so **CPU (all platforms) and NVIDIA both work with zero
  config**. **CPU is first-class** (the founding goal); **MLX is out of scope** (separate
  framework, not a torch backend — Apple accel is `mps`). **Validated negative result
  (2026-07-20, real linux):** uv's own `UV_TORCH_BACKEND` selector does **not** reliably help here
  — OmniVoice's explicit cu128 git-source *dominates* it (`UV_TORCH_BACKEND=cpu` still resolved
  `torch 2.11.0+cu128`). So a **slim** CPU build (no NVIDIA libs; the default linux venv is
  ~5.5 GB) and the ROCm/XPU wheels are an **advanced, deferred path** — reachable only by patching
  OmniVoice's source (mirroring the container's pip `--no-deps`) or an extras+cu128-absorber setup,
  and not worth the maintenance now. Documented, not built (A5). (§2.1, §6 A4/A5)
  **Addendum (user, 2026-07-22, D15):** a *third*, engine-internal axis exists once qwen-tts is
  opt-in (D14) — **which Qwen3-TTS execution mode** (`pytorch` vs `openvino`) a user gets when they
  opt into that engine without an explicit `TTS_BACKEND`. This must also auto-detect, not hardcode
  `pytorch` — **but only select `openvino` if a valid IR export already exists** on disk
  (`OV_MODEL_DIR`/`main_stateful_model` present); OpenVINO export is a slow, deliberate, disk-heavy
  step (`scripts/export.py`) that must never be auto-triggered at request/import time. New **Phase
  A4b**, sequenced right after A4 (needs `resolve_device()`) and before A5 (whose docs describe this
  auto behavior instead of a manual `TTS_BACKEND=openvino` instruction). (§6 A4b)
- **D10 — OmniVoice on the Intel iGPU IS an in-scope goal (Persona Forge accent design), but via
  torch-xpu, not OpenVINO — investigation deferred to a future session (quota).** User's actual
  target: run **OmniVoice accent design on the Iris Xe iGPU** (base cloning is fine on pocket-tts /
  CPU). Two routes:
  - **OpenVINO conversion of OmniVoice — rejected as the path.** IR conversion is per-architecture;
    the Qwen3-TTS OpenVINO work is **not reusable**, and OmniVoice's flow-matching/diffusion design
    would be a Stable-Diffusion-pipeline-scale port (multiple submodels + a Python sampling loop).
  - **torch-xpu / Intel Extension for PyTorch — the promising path.** Keeps the OmniVoice model
    as-is and moves it to `device="xpu"` (the A4 `TTS_DEVICE=xpu` seam). Far less work than a port.
    **✅ VALIDATED 2026-07-21 on plexxie (Iris Xe / Raptor Lake `8086:a7a0`): OmniVoice generates
    end-to-end on the iGPU, ~2.4× faster than the box's CPU (RTF 5.36 vs 12.74 @ 4 vCPU).** Answers
    to the three questions: (1) all OmniVoice ops run on **torch 2.8.0+xpu** (2.8 == OmniVoice's own
    pin) — once fp64 emulation is enabled (root-cause fix below); (2) install is `--no-deps` on top
    of torch-xpu, exactly like the Dockerfile, so cu128 is sidestepped; (3) perf is ~2.4× CPU even
    carrying the emulation tax. **Full findings + the single-image productionization design → §6
    Phase A6.**
  - Separately, the Qwen3-TTS `openvino` backend + `OPENVINO_DEVICE=GPU` (A4) remains the *easy*
    iGPU win for the base model, and pre-shipping the Qwen3-TTS IRs would fix the "export was too
    hard" pain. (§6 A4/A5) **OmniVoice-on-iGPU is now VALIDATED end-to-end — see §6 Phase A6.**
- **D11 — Runtime config is persisted app-side and layers over container env with a "lock" model
  (user, 2026-07-21).** Goal: **as bare a container as possible** (ideally just the data volume +
  `/dev/dri`), with performance/runtime tuning **elevated into the app**, persisted to the data dir,
  and re-applied on start. Today `apply_runtime_config` mutates `os.environ` in-process only and is
  **lost on restart** (§2.2); `apply_preset_env` derives low-level OV vars via `setdefault` (expert
  env wins). The new model: a persisted `runtime.json` (data dir) is read at startup and **wins by
  default** over image defaults, but the UI **surfaces which keys are pinned by an explicit container
  env** and lets an operator mark specific keys **env-locked** (ops/IaC escape hatch). Precedence:
  `env-locked container var` > `persisted runtime.json` > `image/compose default (setdefault seed)`.
  The app also **coaches** container-level settings it cannot self-apply (device passthrough,
  `GPU_FAMILY` when auto-detect is wrong). Reconciles the A6.4 "env-first" framing with the
  minimal-container goal: `GPU_FAMILY=auto` + persisted overrides mean the common user sets nothing.
  Built in **Phase A7**; the premium UX for it dovetails with Initiative C. (§2.2, §6 A6/A7, §8)
- **D12 — OpenVINO is being demoted from default to opt-in; a post-plan rebrand to "Persona
  Forge" is on the horizon (user, 2026-07-22).** After this plan lands, the project/code/container
  rename to **Persona Forge** reflects where development time has actually gone (OmniVoice +
  pocket-tts, not the OpenVINO path). OpenVINO stays supported as a speed option for Intel-CPU-only
  users, but **`presets.py`'s hardcoded `"backend": "openvino"` default (all three presets, lines
  ~49/61/95) is stale intent, not a decision to preserve.** Do not re-entrench it in A4/A6/A7 work.
  The rebrand itself and the default-backend swap are **out of scope for this plan** (do not action
  them here) but any phase touching backend selection (A4, A6a/c/d, A7a-d) must not assume
  `openvino` is or should remain the default — prefer auto-detected/backend-agnostic framing
  (ties into D9's device-axis auto-detect). Discovered while validating A2 locally: a plain `python
  -c "from qwen3_tts.app import app"` on this Mac resolved `TTS_BACKEND=openvino` (via
  `apply_preset_env`'s preset default) and failed on a missing OV IR — expected given the
  stale default, not a uv-migration bug. (§2.2, `config.py::apply_preset_env`, `presets.py`)
- **D13 — Documentation is a per-phase deliverable, not a dedicated phase (user, 2026-07-22).**
  Every phase (A/B/C, not just A3/A5/B7/C3) must add/update docs where its change makes existing
  docs stale or a new capability undocumented: new/updated markdown under `docs/`, and the root
  `README.md` when the change affects what a user sees getting started (e.g. a default-backend
  change, a new setup step). This augments §4.4 (task budget) — doc updates count toward a phase's
  diff, not a separate task. (§4 Global rules)
- **D14 — pocket-tts + OmniVoice are main (always-installed) deps; `qwen-tts` is the opt-in one
  (user, 2026-07-22).** Sharpens D12: Persona Forge's two real levers — OmniVoice (accent design)
  and pocket-tts (cloning/generation) — must be installed by a bare `uv sync`, no group/extra flag.
  Qwen3-TTS (`qwen-tts`, plus `einops`/`onnxruntime`/`sox`, its exclusive transitive deps) moves to
  `[project.optional-dependencies] qwen-tts`, installed via `uv sync --extra qwen-tts`. Shared
  transitive deps (`torch`, `torchaudio`, `transformers`, `accelerate`, `librosa` — needed by
  OmniVoice too) **stay main**, not just qwen-tts's. **Consequence:** `model.py`'s
  `from qwen_tts import Qwen3TTSModel` must be a **lazy import inside the pytorch/openvino load
  branch**, not a module-level import — a bare `uv sync` (pocket_tts-only) must import
  `qwen3_tts.app` cleanly. Implemented + validated 2026-07-22 (A1 re-lock: `pocket-tts` resolves
  main, `qwen-tts`/`sox` drop out of a plain `uv sync`; 343/343 tier1_unit green; app import proven
  in a pocket_tts-only venv). (§6 A1)
- **D15 — `PRESETS["backend"]`'s fallback must stay `pytorch`/`openvino` only — never
  `pocket_tts` (user, 2026-07-22).** `PRESETS` (`presets.py`) is keyed by `model_repo` pointing at a
  Qwen3-TTS checkpoint; `pocket_tts` is a wholly separate engine/checkpoint and cannot run it. The
  actual product default (`TTS_BACKEND=pocket_tts`) is set **explicitly** in `.env.example`, which
  wins over the preset fallback via `config.py`'s explicit-wins `setdefault` rule — the two facts
  don't conflict. This sets up **A4b**: today the preset fallback is hardcoded to `"pytorch"`; A4b
  replaces that hardcode with an auto-detect between `pytorch` and `openvino` (§6 A4b). (§6 A1, A4b)

## 4. Global execution rules & invariants

### 4.1 Privacy / isolation (Initiative B)

The capture harness must **never** point at, read from, or copy `./data/voices` or `./data/segments`.
It runs only against disposable temp dirs seeded from small, checked-in, **synthetic** fixtures
(§7 B2). No real personal audio ever enters a screenshot or a commit. Before committing fixture
data, diff it against the B2 spec and confirm every clip was synthetically generated.

### 4.2 Additive / no-CI (Initiative B) and no-CI-break (Initiative A)

- Do not weaken the fake-model tier (`run-server.mjs`, the Playwright config,
  `fixtures/fake_model_server.py`) or its CI usage. If a shared file changes, `npm run test:ci`
  in `tests/ui/` must still pass.
- The capture tier adds **no** workflow file — it never runs in CI.
- Initiative A must not break CI: `requirements-dev.txt` stays the CI install source (D4).

### 4.3 Gate taxonomy (four buckets — every hard gate is tagged with exactly one)

Implementation is expected to run ~90% on a local finetuned model (Qwen3.6-27B) with ~10%
escalation to a frontier model (Sonnet/Claude). Each gate is tagged so the local model knows who
closes it and whether it costs frontier quota:

| Tag | Who decides | Frontier quota? |
|---|---|---|
| `[local-verifiable]` | the local model self-runs an exact command with a machine-decidable PASS condition | no |
| `[decide-once]` | Nick settles it once (copy strings, disclosure boundaries, wizard questions, thresholds); then it becomes `[local-verifiable]` with the value inlined | no |
| `[escalate→device]` | needs the real Mac / real model / a human eyeball: model-load runs, HF-gated downloads, visual UI acceptance, GIF quality | no (real hardware, not quota) |
| `[escalate→frontier]` | genuine reasoning/design judgment the local model cannot do | **yes — the only bucket that spends quota** |

Prefer `[local-verifiable]`. Route model-dependent runs and visual acceptance to `[escalate→device]`.
Reserve `[escalate→frontier]` for the few reasoning judgments. A `[decide-once]` gate, once
decided, is treated as `[local-verifiable]` with its value inlined — do not reopen it.

### 4.4 Context management & drift

- Hand an implementing agent **one phase section**, not the whole plan. Each phase below is
  self-contained: preconditions, exact reads (with file/line hints), steps, invariants, gate.
- **Task budget: target 60–80k tokens per agent task** (instructions + the code the phase makes it
  read + the work/diff + gate runs — summed). The llama-monitor experience showed 100–150k was too
  conservative once those three were added together for the local 27B. Phases that would exceed this
  are decomposed into **letter-suffixed sub-phases** (A6a, A7b, …), each individually shippable with
  its own gate. If a sub-phase's Read-first set plus expected diff would still blow past ~80k, split
  it further before handing it off — a bounded file set and a bounded diff are the sizing levers.
- Line hints drift. Prefer the named function/heading over the number; re-grep if a hint looks
  stale (e.g. `grep -n "def analyze_reference" src/qwen3_tts/audio_style.py`).
- Before relying on a route list, testid count, or schema, re-verify it against the live source
  (the facts in §2 were true 2026-07-20).
- `npm run build` in `frontend/` must pass at the end of every frontend-touching phase.

### 4.5 Documentation is per-phase, not a dedicated phase (D13)

Before closing any phase's gate, check whether the change makes an existing doc stale or leaves a
new capability undocumented, and fix it in the same phase: `docs/dev/**`, `docs/HOW_TO_RUN.md`,
`docs/ENV_REFERENCE.md`, or the root `README.md` (only when the change affects what a user sees
getting started — a new default, a new setup step, a new prerequisite binary). This is not optional
busywork reserved for A3/A5/B7/C3 — those phases cover *setup-flow* docs specifically; every other
phase still owns its own docs. Doc edits count toward the phase's diff/task budget (§4.4), not a
separate task.

## 5. Dependency & sequencing index

| Phase | Initiative | Deliverable (one line) | Depends on |
|---|---|---|---|
| A1 | uv | `pyproject.toml` + uv sources/overrides authored from existing manifests | — |
| A2 | uv | `uv sync` reproduces a working real-model venv; tests green | A1 |
| A3 | uv | dev docs updated; B1 precondition rewired to `uv sync`; CI untouched | A2 |
| A4 | uv | runtime device seams: `TTS_DEVICE` (torch) + `OPENVINO_DEVICE` (iGPU), auto-detect+force | A2 |
| A4b | uv | Qwen3-TTS engine-mode auto-select: `pytorch` vs `openvino`, IR-presence-gated (D15) | A4 |
| A5 | uv | accelerator install guide (docs) + deferred slim/ROCm/XPU + iGPU-via-OpenVINO note | A2, A4b |
| A6 | accel | OmniVoice-on-iGPU **validated** (findings/design; §6 A6.1–A6.4) — reference, not a task | — |
| A6a | accel | OmniVoice device seam + auto fp64-emu env | A4 |
| A6b | accel | honest `OMP_NUM_THREADS=4` CPU baseline + dtype re-confirm (measurement) | A6a (device) |
| A6c | accel | `gpu_family.py` family detection + `describe_accelerator()` | — |
| A6d | accel | accel-aware entrypoint: family resolution + per-family runtime env | A6a, A6c |
| A6e | accel | first-boot per-family torch install into a named volume | A6d |
| A6f | accel | base-image system-lib layering + `/dev/dri` compose docs + A5 reconcile | A6d |
| A6g | accel | int8 PTQ exploration (deferred follow-up) | A6b |
| A7a | runtime-cfg | persistence backend: `runtime.json` + startup layering (D11) | — |
| A7b | runtime-cfg | API: per-key source/lock/restart_required + reset/dry-run | A7a |
| A7c | runtime-cfg | container coach: markdown copy + card | A6c, A7b |
| A7d | runtime-cfg | premium Runtime control surface (UX; may split A7d/A7e) | A7b, A6c, (C1/C2) |
| B1 | capture | `run-real-server.mjs` spawns real backend (Flask dev server) on temp dirs | (A2 preferred, works on current venv) |
| B2 | capture | synthetic fixtures + `seedCaptureFixtures()` | B1 |
| B3 | capture | `capture.mjs --real`; one existing scenario runs real | B1, B2 |
| B4 | capture | `lib/gif.mjs`; one trivial GIF proven | B3 |
| B5 | capture | demand-driven `data-testid`s | B3 |
| B6 | capture | scenario catalog (one scenario per agent) | B3, B4, B5 |
| B7 | capture | `tests/ui/README.md` coverage + verified workflow | B6 |
| C1 | guided | metric tooltips (shared `MetricExplainer`) | — |
| C2 | guided | progressive disclosure seam | — (parallel with C1) |
| C3 | guided | glossary + troubleshooting KB | C1 (link target) |
| C4 | guided | automated take diagnostics | C3 |
| C5 | guided | persona wizard | C2 |

---

## 6. Initiative A — uv local-dev migration

### Phase A1 — Author `pyproject.toml` + uv configuration

**Mission:** express the existing pip manifests as a single `uv`-managed `pyproject.toml` +
`uv.lock` that resolves **universally for macOS + linux** (D2), handling the OmniVoice cu128
git-source problem and the transformers pin via `override-dependencies` (D5). This shape is
**validated end-to-end** (macOS lock 120 pkgs; linux `uv sync` installs + imports, 2026-07-20).

**Preconditions** `[local-verifiable]`:
```bash
cd /Users/nick/SCRIPTS/CLAUDE/qwen3-tts-openvino
uv --version                       # expect: uv 0.11.x present
test ! -f pyproject.toml && echo "greenfield OK"   # expect: greenfield OK (none yet)
```

**Read first (source of truth for the dep set):**
- `requirements/requirements-runtime.txt` — the default runtime deps + the transformers comment.
- `requirements-dev.txt` — the `dev` group set (must stay CI-compatible, D4).
- `requirements/requirements-openvino.txt`, `requirements-export.txt`,
  `requirements-pocket-tts.txt` — the optional groups.
- `Dockerfile` lines 15–45 — torch/torchaudio versions + index, the `--no-deps` install order,
  and the OmniVoice git rev `398b6113`.
- §2.1, §2.2, D2, D5 above.

**Do this:**
1. Create `pyproject.toml` with `[project]` (`name`, `version`, `requires-python = ">=3.13,<3.14"`).
   (Cap below 3.14: a bare `>=3.13` let the probe pick the system 3.14 interpreter, which the
   backend is not built against — the container is 3.13.)
2. `[project.dependencies]` = the runtime set from `requirements-runtime.txt` **including
   `gunicorn==26.0.0`** and `transformers==5.12.1`, plus `qwen-tts==0.1.1` and `omnivoice`, plus
   `torch==2.12.1` / `torchaudio==2.11.0`.
3. `[dependency-groups]` (PEP 735) — `dev` mirroring `requirements-dev.txt` **exactly** (D4);
   `openvino`, `export` (openvino + `nncf==3.2.0`), `pocket-tts` (`pocket-tts==2.1.0`).
4. `[tool.uv.sources]`:
   - `omnivoice = { git = "https://github.com/k2-fsa/OmniVoice.git", rev = "398b6113" }`.
   - **Do NOT add any `pytorch-cpu`/`pytorch-cuda` index or source for torch.** OmniVoice's git
     `pyproject` declares a `cu128` index for torch on linux/win; because it's a git source uv
     honors it, and any competing torch index makes `uv lock` fail with "conflicting indexes for
     torch". The `override-dependencies` in step 5 handles it instead (D2/D5).
5. `[tool.uv]`:
   ```toml
   [tool.uv]
   environments = ["sys_platform == 'darwin'", "sys_platform == 'linux'"]
   override-dependencies = ["transformers==5.12.1", "torch==2.12.1", "torchaudio==2.11.0"]
   ```
   - `override-dependencies` does double duty (D5): `transformers` beats qwen-tts's `4.57.3` pin,
     and `torch`/`torchaudio` **strip OmniVoice's cu128 index association** so torch resolves from
     default PyPI on both platforms (arm64 cpu+mps on macOS; CUDA-enabled-but-CPU-capable wheel on
     linux). This is what makes the universal (darwin+linux) lock resolve — validated on real
     hardware 2026-07-20.
   - qwen-tts's other transitive deps (accelerate/einops/librosa/onnxruntime/sox) stay explicit in
     `[project.dependencies]` (uv has no per-package `--no-deps`; mirrors the Docker `--no-deps`
     set).
6. Run `uv lock -p 3.13` and inspect: torch/torchaudio from `pypi.org/simple` (no `cu128`),
   `transformers==5.12.1`, OmniVoice at rev `398b6113`. (Reference: macOS 120 pkgs, linux 124 pkgs,
   both green.)

**Invariants:** do not change `requirements-dev.txt` (CI depends on it, D4); do not touch the
Dockerfile (D3); the `dev` group must equal `requirements-dev.txt`'s contents.

**Gate — done when ALL pass:**
```bash
cd /Users/nick/SCRIPTS/CLAUDE/qwen3-tts-openvino
uv lock -p 3.13                                    # [local-verifiable] resolves, writes uv.lock
grep -q '5.12.1' uv.lock && echo "transformers pin OK"    # [local-verifiable]
grep -q '398b6113' uv.lock && echo "omnivoice pin OK"     # [local-verifiable]
! grep -q 'cu128' uv.lock && echo "no cuda index OK"      # [local-verifiable] guards the D2 trap
```
The resolver approach is fully de-risked (macOS + real-linux, 2026-07-20) — no open
`[escalate→frontier]`. If a sub-agent's `uv lock` reintroduces a `cu128` conflict, the cause is
almost always a stray torch index/source or a missing torch entry in `override-dependencies`
(see D2). The **arm64 wheel install + model load on macOS** is the remaining `[escalate→device]`
(A2 gate); the linux install path is already proven.

**Completion proof:** `pyproject.toml` + `uv.lock` committed; lock has the transformers+torch
overrides, no `cu128`, and the OmniVoice git rev; `requirements-dev.txt` and `Dockerfile` unchanged
(`git diff` shows neither).

### Phase A2 — Prove `uv sync` reproduces a working real-model venv

**Mission:** confirm a fresh `uv sync` produces an environment that loads the real model and
passes the test suite — the whole point of the migration. (Note: `uv sync` + torch/torchaudio/
transformers/omnivoice imports are **already proven on real linux**, dockermisc1, 2026-07-20 —
124 pkgs, runs on CPU. This phase re-confirms on the operator's machine and adds the pytest +
model-load checks.)

**Preconditions** `[local-verifiable]`:
```bash
cd /Users/nick/SCRIPTS/CLAUDE/qwen3-tts-openvino
test -f uv.lock && echo "A1 OK"
```

**Read first:** §2.2 (import-time model load, health), the memory-learned pytest invocation
(`PYTHONPATH=src:. … pytest`).

**Do this:**
1. `uv sync --group dev` (or the group set needed to both run the app and the tests). If OmniVoice
   / gated checkpoints need `HF_TOKEN`, use the operator's shell env only.
2. Confirm the synced env has the previously-missing pieces and loads the model.

**Invariants:** do not delete the existing `.venv` until the uv env is proven (keep a fallback).

**Gate — done when ALL pass:**
```bash
cd /Users/nick/SCRIPTS/CLAUDE/qwen3-tts-openvino
uv run python -c "import gunicorn, torch, transformers; print('runtime deps OK', torch.__version__)"   # [local-verifiable]
uv run python -c "import torch; print('mps', torch.backends.mps.is_available())"                       # [escalate→device] expect mps True on this Mac
uv run python -c "from qwen3_tts.app import app; print('app import OK')"                                # [escalate→device] heavy import, must succeed
PYTHONPATH=src:. uv run pytest tests/ -q -k "audio_style or voice_library" 2>&1 | tail -15             # [local-verifiable] subset green
```
A full real-backend spawn + `/health` `model_loaded: true` under the uv env is `[escalate→device]`
(model load, minutes on cold cache).

**Completion proof:** `uv run` imports gunicorn+torch+transformers and the app; the pytest subset
passes; model loads (device gate) — recorded in the companion ledger.

### Phase A3 — Docs + rewire capture prerequisite; keep CI intact

**Mission:** document the uv-based local setup and point the capture harness (and any dev doc) at
`uv sync`, without touching CI.

**Preconditions** `[local-verifiable]`:
```bash
cd /Users/nick/SCRIPTS/CLAUDE/qwen3-tts-openvino
uv run python -c "from qwen3_tts.app import app" >/dev/null 2>&1 && echo "A2 OK"
```

**Do this:**
1. Add/adjust a local-dev-setup doc (e.g. a `## Local development (uv)` section in the repo
   README or a `docs/dev/LOCAL_SETUP.md`): `uv sync --group dev` for fast work; the full group set
   + `HF_TOKEN` note for real-model work; `brew install ffmpeg` as a system prerequisite for
   Initiative B; the fact that the container build is separate (D3).
2. Where §7 B1's precondition mentions the venv, note that `uv sync` is now the canonical way to
   populate it (both the current `.venv` and a uv-managed env work; uv is preferred/reproducible).
3. Leave `.github/workflows/*.yml` and `requirements-dev.txt` unchanged (D4).

**Invariants:** no CI workflow edits; no `requirements-dev.txt` edits.

**Gate — done when ALL pass:**
```bash
cd /Users/nick/SCRIPTS/CLAUDE/qwen3-tts-openvino
git diff --name-only | grep -E '\.github/workflows/|requirements-dev.txt' && echo "CI TOUCHED (FAIL)" || echo "CI intact OK"   # [local-verifiable] expect: CI intact OK
grep -rniq "uv sync" docs/ README.md 2>/dev/null && echo "setup doc OK"   # [local-verifiable]
```
A genuinely-clean-checkout reproduction (`rm -rf .venv && uv sync && model loads`) is
`[escalate→device]`.

**Completion proof:** setup doc references `uv sync`; `git diff` shows no CI/requirements-dev
changes; a from-scratch `uv sync` (device gate) yields a working real-model env.

---

### Phase A4 — Runtime device seams (`TTS_DEVICE` + `OPENVINO_DEVICE`)

**Mission:** auto-detect the best runtime device, with an env override, for each backend — no
dependency change, works on an already-installed build. This is axis (a) of D9. Two selectors:
`TTS_DEVICE` for the pytorch backend (`cpu`/`cuda`/`mps`/`xpu`) and `OPENVINO_DEVICE` for the
openvino backend (`CPU`/`GPU`/`AUTO` — the **Intel iGPU knob**, D10).

**Read first (current seams):**
- `src/qwen3_tts/model.py:46` — `DEVICE = os.getenv("DEVICE", "cpu")`, fed to `device_map=DEVICE`
  (~483) and reported in `health_state()` (~774, ~956). Canonicalize + add auto-detect here.
- `src/qwen3_tts/omnivoice_engine.py:296` — `OmniVoice.from_pretrained(..., dtype=torch.float32)`:
  **no device arg today**, CPU-only. Add device/dtype iff the installed API accepts it.
- `src/qwen3_tts/model.py` ~790/797 — the OpenVINO path **hardcodes `"device": "CPU"`**. This
  phase makes it selectable so the Qwen3-TTS OV backend can target an Intel iGPU (D10).
- §3 D9, D10.

**Do this:**
1. `qwen3_tts/device.py: resolve_device()` — default **auto-detect** (`cuda` if available, else
   `xpu`, else `mps`, else `cpu`); `TTS_DEVICE` (fallback legacy `DEVICE`) forces a specific one.
   Return the device + a sensible dtype (float32 on cpu/mps). If a *forced* device is unavailable,
   **log a warning** — never silently downgrade without saying so.
2. Route `model.py`'s `DEVICE` through the helper (cpu path behaves identically).
3. Wire OmniVoice at `omnivoice_engine.py:296`: pass the resolved device **iff** the installed
   `from_pretrained` signature accepts it (verify the `398b6113` API); else stay CPU **with a
   warning log** and record that OmniVoice is CPU-only (expected per D9/D10).
4. OpenVINO device: replace the hardcoded `"CPU"` (~790/797) with `os.getenv("OPENVINO_DEVICE",
   "AUTO")` fed to the OV core. Values `CPU`/`GPU`/`AUTO`; `GPU` targets the Intel iGPU. This is
   **Qwen3-TTS-backend only** — OmniVoice has no OpenVINO path (D10).
5. `/health` reports the resolved device per active backend.

**Invariants:** no dependency/version change (never touches `pyproject.toml`). **Behavior note:**
the no-env default changes from always-`cpu` to *best-available* — on a CPU-only box that is still
`cpu` (no functional change); on a GPU box it now uses the GPU (intended). Operators wanting a
pinned CPU (e.g. the canonical container, D3) set `TTS_DEVICE=cpu` / `OPENVINO_DEVICE=CPU`.

**Gate — done when ALL pass:**
```bash
cd /Users/nick/SCRIPTS/CLAUDE/qwen3-tts-openvino
python -c "from qwen3_tts.device import resolve_device; print(resolve_device())"   # [local-verifiable] 'cpu' on a no-GPU box
TTS_DEVICE=cpu python -c "from qwen3_tts.device import resolve_device; assert resolve_device()=='cpu'"   # [local-verifiable]
grep -q 'OPENVINO_DEVICE' src/qwen3_tts/*.py && grep -q 'TTS_DEVICE' src/qwen3_tts/*.py && echo "both seams wired OK"   # [local-verifiable]
```
- `TTS_DEVICE=mps` load+generate on this Mac → `[escalate→device]`.
- OmniVoice `from_pretrained` device-kwarg support at `398b6113` → `[escalate→device]`.
- `OPENVINO_DEVICE=GPU` enumerating + running on a real Intel iGPU (a future iGPU LXC; plexxie
  already has `intel-opencl-icd` + `intel-level-zero-gpu`) → `[escalate→device]`, deferred.

**Completion proof:** auto-detect default works; both env overrides work; `/health` shows the
per-backend device; the OV `OPENVINO_DEVICE` seam is wired (iGPU run itself deferred to a device
gate); no `pyproject.toml` diff.

### Phase A4b — Qwen3-TTS engine-mode auto-selection (`pytorch` vs `openvino`)

**Mission:** when a user opts into the Qwen3-TTS engine (`qwen-tts` extra installed) without an
explicit `TTS_BACKEND`, auto-select `pytorch` or `openvino` instead of the current hardcoded
`pytorch` fallback in `PRESETS["backend"]` — but **only** select `openvino` if a valid IR export
already exists on disk. This is D9's addendum axis (D15); does not touch the overall product
default (`TTS_BACKEND=pocket_tts`, set explicitly in `.env.example`, which still wins per
`config.py`'s explicit-wins rule — this phase only changes the *preset fallback* used when someone
sets `MODEL_SIZE`/opts into Qwen3-TTS without picking a backend).

**Read first:**
- `src/qwen3_tts/presets.py` — `PRESETS["0.6B"/"1.7B"]["backend"]`, currently hardcoded `"pytorch"`
  (D15); `_ir_paths()` computes the exact `main_stateful_model` path a real export would write to.
- `src/qwen3_tts/config.py::apply_preset_env` — where `preset["backend"]` feeds `TTS_BACKEND` via
  `_setdefault` (explicit-wins).
- §3 D9 addendum, D15; §6 A4 (`resolve_device()` — this phase runs after it, no new device logic).

**Do this:**
1. Add an IR-presence check (e.g. `qwen3_tts/presets.py::has_valid_export(preset) -> bool` —
   checks `main_stateful_model` file exists, and `predictor_stateful_model` if the preset declares
   one) that reads the filesystem, not env, so it reflects the real export state.
2. In `apply_preset_env`, replace the hardcoded `preset["backend"]` fallback with: `"openvino"` if
   `has_valid_export(preset)` else `"pytorch"` — only when `TTS_BACKEND` is not already set upstream
   (still `.env.example`'s `pocket_tts` in the product default path; explicit env always wins).
3. **Never** trigger `scripts/export.py` from this code path — export stays a deliberate, separate,
   opt-in operation (compose profile / manual script run).
4. `/health` (or equivalent) reports whether the fallback picked `openvino` because an export was
   found, so a user isn't surprised by which mode is active.
5. Docs (D13): update A5's accelerator guide (and `docs/dev/LOCAL_SETUP.md`/`docs/ENV_REFERENCE.md`
   if their current wording implies a manual-only `TTS_BACKEND=openvino` selection) to describe the
   auto-detect-if-exported behavior.

**Invariants:** no `pyproject.toml` change; never auto-runs export; never overrides an explicit
`TTS_BACKEND` (including the `.env.example` product default of `pocket_tts`); CPU-only/no-export
hosts see identical behavior to today (`pytorch` fallback).

**Gate — done when ALL pass:**
```bash
cd /Users/nick/SCRIPTS/CLAUDE/qwen3-tts-openvino
PYTHONPATH=src:. uv run python -c "
from qwen3_tts.config import apply_preset_env
environ = {'MODEL_SIZE': '1.7B'}
apply_preset_env(environ)
assert environ['TTS_BACKEND'] == 'pytorch'  # no IR on disk -> pytorch fallback
print('no-export fallback OK')
"   # [local-verifiable]
PYTHONPATH=src:. uv run pytest tests/tier1_unit/test_config.py -q   # [local-verifiable]
```
- Fallback correctly flips to `openvino` against a real exported IR (needs an actual export run) →
  `[escalate→device]`.

**Completion proof:** no-export hosts still fall back to `pytorch`; a real export flips the fallback
to `openvino`; explicit `TTS_BACKEND` (including `.env.example`'s `pocket_tts`) always wins; docs
updated; no `pyproject.toml` diff; `tests/tier1_unit/test_config.py` green.

### Phase A5 — Accelerator install guide + deferred paths (docs, not code)

**Mission:** document how a user installs natively for their accelerator, given the *validated*
constraints (D2/D9/D10), and record what's deliberately deferred. This is axis (b) of D9 — but the
A1 default lock already **is** the install story for the common cases, so this phase is mostly a
docs deliverable + a decision record, **not** an extras matrix (that approach is deferred, D9).

**Read first:** §3 D2, D9, D10; §6 A1; the validated findings below.

**What works out of the box — document this matrix (all validated 2026-07-20 unless noted):**
| Target | Command | Result |
|---|---|---|
| macOS (Apple Silicon) | `uv sync` | arm64 **cpu+mps**; runtime auto-detects mps (A4) |
| linux + NVIDIA | `uv sync` | CUDA-enabled wheel; runtime auto-detects **cuda** (A4) |
| linux CPU-only | `uv sync` | works, runs on **cpu** — but ~**5.5 GB** venv (unused NVIDIA libs) |
| Intel iGPU | `uv sync --extra qwen-tts`, export once, `OPENVINO_DEVICE=GPU` (A4) — backend auto-selects `openvino` once the export exists (A4b) | Qwen3-TTS on the iGPU; needs `intel-opencl-icd` + `intel-level-zero-gpu` + `/dev/dri` passthrough. **Qwen3-TTS backend only; OmniVoice stays CPU (D10)** |

**Deferred / advanced — record, do NOT build:**
- **Slim CPU (no NVIDIA), ROCm, Intel XPU torch wheels.** Blocked by OmniVoice's cu128 git-source
  *dominating* uv resolution — validated: `UV_TORCH_BACKEND=cpu` still resolved `torch 2.11.0+cu128`
  on real linux. Reachable only by (a) pointing `[tool.uv.sources] omnivoice` at a fork/checkout
  with its `[tool.uv]` index block stripped (mirrors the container's pip `--no-deps`), then
  declaring torch from the desired index; or (b) an extras + `conflicts` + cu128-absorber setup.
  Both add real maintenance — defer until there's demand (e.g. a genuinely disk-constrained CPU LXC).
- **OmniVoice on OpenVINO / iGPU:** out of scope (D10) — a separate SD-pipeline-scale conversion.

**Do this:**
1. Add a "Native install & accelerators" section to the dev-setup doc: the out-of-box matrix above,
   the exact `uv sync` commands, the **5.5 GB linux caveat**, and the Intel-iGPU-via-OpenVINO note
   (backend + env + system runtime + passthrough).
2. In the same doc, record the deferred paths + the OmniVoice-source escape hatch, so a future
   contributor has the map.
3. **No `pyproject.toml` changes** — the A1 default lock is the whole install story; do NOT add an
   extras matrix.

**Invariants:** no Dockerfile/`requirements-dev.txt` change (D3/D4); no new pyproject extras
(deferred, D9); CPU stays first-class (D9).

**Gate — done when ALL pass:**
```bash
cd /Users/nick/SCRIPTS/CLAUDE/qwen3-tts-openvino
grep -riq "5.5 GB\|OPENVINO_DEVICE\|accelerator" docs/ && echo "accel guide present"   # [local-verifiable]
test -z "$(git diff --name-only -- pyproject.toml)" && echo "no pyproject churn OK"     # [local-verifiable]
```
Intel-iGPU OpenVINO enumeration (`OPENVINO_DEVICE=GPU` on a real iGPU box) → `[escalate→device]`,
deferred (plexxie has the compute runtime for a future validation).

**Completion proof:** dev doc carries the accelerator matrix + 5.5 GB caveat + iGPU/OpenVINO note +
deferred-path map; no pyproject extras added; no CI/Dockerfile diff.

---

### Phase A6 — OmniVoice iGPU acceleration (VALIDATED) + unified accelerator packaging

**Status: end-to-end validated on real hardware 2026-07-21** (plexxie: Ubuntu 22.04 LXC on Proxmox,
Intel Iris Xe / Raptor Lake `8086:a7a0`, 96 EU, `/dev/dri` passthrough, 8 GB RAM). This phase records
what works and specifies the productization the user requires. This is axis-(a)+(b) of D9 converging
for the OmniVoice/xpu case (D10).

#### A6.1 — What was proven (repro recipe)

The **working stack** (native venv, no container yet):
1. Level-Zero **loader**: `libze1` (from `oneapi-src/level-zero` GitHub `.deb`; **not** in Ubuntu
   repos). Provides `libze_loader.so.1` which torch's xpu runtime dlopens.
2. **torch 2.8.0+xpu + torchaudio 2.8.0+xpu** from `https://download.pytorch.org/whl/xpu`. Version
   matters: **2.13+xpu FAILS** (its oneDNN 2026 needs a newer driver than shipped → "could not make
   an engine with allocator" on GEMM); **2.8 and 2.6 work** for compute. 2.8.0 is also OmniVoice's own
   pin (`constraint-dependencies = torch==2.8.0`), so no version tug-of-war.
3. Intel **compute runtime** on the host/LXC: `intel-opencl-icd`, `libze-intel-gpu1` (the L0 GPU
   driver; new name — replaces `intel-level-zero-gpu`), `libigc2`, `libigdgmm12`. On plexxie these
   were upgraded to the current build (opencl **25.18.33578**, libigc2 **2.11.12**) via Intel's apt
   repo (`repositories.intel.com/gpu/ubuntu jammy unified`); **Plex's `intel-media-va-driver` is a
   different package and was untouched** (verified via `apt-get install -s`). NOTE: the upgrade turned
   out NOT to be what fixed generation (fp64 emulation was) — but a current runtime is clean and
   recommended anyway.
4. OmniVoice installed `--no-deps` on top of torch-xpu (mirrors the Dockerfile), plus runtime deps
   (`transformers==5.12.1`, accelerate, einops, librosa, soundfile, pydub, pyloudnorm). The `--no-deps`
   is what keeps cu128 out of the resolution (D9 escape hatch, no fork needed).

Load + device move is trivial (the **A4 seam**): `OmniVoice.from_pretrained("k2-fsa/OmniVoice",
dtype=…)` returns an `nn.Module`; a single `m.to("xpu")` moves the whole model (submodules registered
via `_modules`). `instruct` is a **controlled vocabulary** (comma-separated), not prose — valid English
items: american/australian/british/canadian/chinese/indian/japanese/korean/portuguese/russian accent,
male/female, child/teenager/young adult/middle-aged/elderly, {very }low/moderate/high pitch, whisper.

#### A6.2 — Root-cause blocker + THE FIX (must be reproduced in any deployment)

Generation initially failed with an opaque `RuntimeError: UR error` deep in the forward. Isolated to:
**this Xe-LP iGPU has NO native fp64** (`torch.xpu.get_device_properties(0).has_fp64 == False`), and
torch/oneAPI **int↔float conversion (cast) kernels require fp64**, so the kernel module won't build →
UR error. (Confirmed by op-isolation: int/float *arithmetic* works; *every* dtype cast — int64→int32,
int→float, etc. — fails together. Falsified: not a torch-version issue [2.13/2.8/2.6 all fail casts],
not the IGC version [upgrading to libigc2 2.11 didn't fix it].)

**THE FIX — enable NEO's fp64 software emulation via three env vars:**
```
NEOReadDebugKeys=1
OverrideDefaultFP64Settings=1
IGC_EnableDPEmulation=1
```
**CRITICAL GOTCHA:** `OverrideDefaultFP64Settings=1` is a NEO *debug key* that NEO **ignores unless
`NEOReadDebugKeys=1` is also set.** With all three, `has_fp64` reports True, casts pass, and OmniVoice
generates. These vars MUST be present in the service's runtime environment on any fp64-less Intel GPU
(all Xe-LP iGPUs; Arc discretes have native fp64 and won't need them). The `zebin minor version 53 >
decoder 39` log lines are harmless warnings.

#### A6.3 — Perf (why it's worth it)

Same box, ~3.9 s of audio, `num_step=32`:

| config | warm-up (1-time compile) | timed | RTF |
| --- | --- | --- | --- |
| **iGPU fp32 + fp64-emu** | ~349 s | 21.0 s | **5.36** |
| CPU fp32 (4 vCPU, `OMP_NUM_THREADS=16`, oversubscribed) | — | 50.2 s | 12.74 (superseded, see below) |

→ **iGPU ~2.4× faster than this box's CPU** on the original (oversubscribed) number. The ~349 s
warm-up is a **per-process cold-compile** — a resident service loads once and amortizes it (persist
the SYCL cache to speed cold starts: `SYCL_CACHE_PERSISTENT=1`).

**A6b — honest CPU baseline (redone 2026-07-22, `OMP_NUM_THREADS=4`, plexxie, same
text/instruct/steps as above):** RTF **9.86** (warm) / **10.68** (timed). Re-ran the iGPU fp32 pick
under the same clean-box conditions for an apples-to-apples pair: **5.07** (vs. the original 5.26 —
consistent). **Corrected ratio: iGPU ~2.1× faster than the honest CPU baseline** (down from the
2.4× estimate, which used an oversubscribed CPU run). Note: the first attempt at this re-measurement
came back *worse* than the original (RTF 17.73) — root-caused to a stray, unrelated `casterr.py`
process from a prior session that had been hung/deadlocked on plexxie for ~18h, pegging one core;
killed before re-measuring. bf16 in the same re-run session hit the same known harness OOM (LXC
cgroup limit, 3 sequential model loads on 8 GB) documented below — expected, not a regression.

**dtype ladder A/B (done — fp32 wins):** seeded (seed 42) iGPU runs, same text/instruct/steps:

| dtype | RTF | note |
| --- | --- | --- |
| **fp32** | **5.26** | fastest **and** the quality baseline → **the pick** |
| bf16 | 6.49 | *slower* than fp32 — no benefit |
| fp16 | — | inconclusive: test-harness OOM (3 sequential model loads on 8 GB; XPU allocs not freed between dtypes). Likely runnable in a clean process, but the pattern below says it won't beat fp32 anyway |

**Why lower precision doesn't help on this iGPU:** it's launch/memory-bound at these sizes (raw
benchmark: fp16≈fp32 GFLOP/s), and the **fp64-emulation cast tax is incurred regardless of dtype** —
lower precision just adds *more* conversion traffic. So **ship fp32** on Xe-LP. (On an Arc discrete
with native fp64, revisit — no emulation tax there, and fp16 could win.) Seeded wavs for ear-check:
`audio/omni_xpu_{fp32,bf16}_seed42.wav` (+ `omni_{xpu,cpu}_fp32.wav`). **Eval criterion (user):**
OmniVoice outputs are *segment candidates* for the downstream stitch-studio (VST-level DSP —
normalize/compress/EQ/fx), so tonal/level deltas are **recoverable → not disqualifying**; only
**artifacts** disqualify. int8 (PTQ, not a dtype flip) is a follow-up if ever needed — but given fp32
is already fastest, low priority.

**A6g — int8 PTQ feasibility probe (done 2026-07-22, plexxie) — verdict: no-go, not worth
pursuing.** Probed `torch.ao.quantization.quantize_dynamic` (weight-only int8) on a `Linear(4096,
4096)` on xpu: it runs without error, but `torch.backends.quantized.supported_engines` lists no
xpu-targeting engine (`qnnpack`/`onednn`/`x86`/`fbgemm` only) — there's no dedicated int8 GEMM kernel
for this backend, so it's quantized weight storage with compute still effectively fp32-equivalent via
on-the-fly dequant. Measured: fp32 linear 2.77 ms vs. qint8 linear 2.55 ms (~8%, within noise for a
memory/launch-bound op — consistent with the A6.3 finding above). A real int8 win would need
IPEX-level or OpenVINO-int8-style kernels — out of scope for this deferred/low-priority item. No
further PTQ work planned unless the underlying torch-xpu tooling changes.

#### A6.4 — Productization requirement: ONE image, auto-or-specify GPU family (user directive)

**Hard requirement (user, 2026-07-21): do NOT ship two containers.** One image; the user either
lets it **auto-detect** their accelerator family or **explicitly specifies** it (cpu / cuda / rocm /
intel-xpu), and gets the right functionality — **including running in an LXC with an iGPU** (the
user's own case: `/dev/dri` passthrough + the fp64-emu env). This spans both D9 axes:

- **Runtime axis (a) — device selection.** Already the A4 design: `resolve_device()` auto-detects
  (`cuda > xpu > mps > cpu`) with a `TTS_DEVICE` override, plus **family-specific runtime env** the
  entrypoint must set — for Intel fp64-less GPUs, the three NEO emu vars above; for the Qwen3-TTS OV
  backend, `OPENVINO_DEVICE`. Cheap, and works on an already-installed build.
- **Install axis (b) — which torch wheel.** The real packaging problem: torch **cpu / cu12x / rocm /
  xpu are different, mutually exclusive wheels** (+ different system libs: CUDA vs ROCm vs Intel
  compute-runtime). "One image, any family" therefore needs a strategy — three candidates:
  - **(i) Build-time family arg.** Single `Dockerfile` with `ARG ACCEL={auto,cpu,cuda,rocm,xpu}`
    selecting the torch index + apt libs. *One Dockerfile, but still N image tags* — arguably violates
    "one image." Cheapest to build/maintain; good stopgap.
  - **(ii) Runtime install-on-first-boot.** Ship a thin CPU base; the **entrypoint detects the GPU
    family** (`lspci`/vendor, or `GPU_FAMILY` env override) and `pip install`s the matching torch
    variant into a **named volume** on first start, then sets the family env. Truly one image; cost =
    slow first boot + needs network at runtime (or a bundled wheel cache). **Recommended default** —
    it directly satisfies "auto or specify, one artifact," and the iGPU-LXC path is just
    `GPU_FAMILY=intel-xpu` → installs torch-xpu + sets the emu vars.
  - **(iii) Fat multi-venv image.** Bake cpu+cuda+xpu(+rocm) torch into separate venvs; entrypoint
    picks the venv by detected/`GPU_FAMILY`. One artifact, instant switch, **no runtime network** —
    but very large (~15–20 GB) and rebuilds on every torch bump. Reserve for an offline/air-gapped
    variant.
  - System libs (Intel compute-runtime; the `libze1` loader; `/dev/dri`+`render` group; CUDA/ROCm
    userspace) must be present for the chosen family. For (ii)/(iii) the Intel + CUDA + ROCm userspace
    can be layered in the base image (they don't conflict) so only the torch wheel varies at runtime.

**Recommended shape:** entrypoint-driven family resolution (approach **ii**), `GPU_FAMILY=auto`
default with explicit override; auto-detect maps Intel iGPU → `intel-xpu` and sets the three NEO emu
vars automatically when `has_fp64==False`; CPU is always the safe fallback (D9 CPU-first-class). This
keeps the CPU/canonical Dockerfile (D3) intact and adds an accel-aware entrypoint rather than a fork.

#### A6.4a — Detection model (capability vs presence; torch-independent family selection)

Auto-discovery is **two separate probes**, and the distinction is load-bearing:

- **Capability probe — "can I run on it right now?"** Decides the actual *runtime device* (A4).
  `torch.<accel>.is_available()` **plus** the device node being present and openable
  (`/dev/dri/renderD128` for Intel/ROCm, `/dev/nvidia*` for CUDA).
- **Presence probe — "does the host have hardware I could use if it were mapped?"** Drives the A7c
  **coach**, and survives *without* passthrough: the **CPU model** (`/proc/cpuinfo`) and the **PCI
  vendor/device in sysfs/`lspci`** (`8086` Intel, `10de` NVIDIA, `1002` AMD).

The gap between them is where coaching lives: **presence=true, capability=false → "you have the
hardware but haven't mapped it; here's the compose snippet."**

**The container chicken-and-egg (why probe ordering matters).** Inside the CPU-base image,
`torch.cuda/xpu.is_available()` is **always False** — not because there's no GPU, but because the CPU
torch wheel has no CUDA/XPU support compiled in, and A6e only installs the accel wheel *after* the
family is chosen. Therefore **family selection (which wheel to install) must NOT depend on torch.** It
runs off the torch-independent presence signals; `torch.<accel>.is_available()` is a **post-install
confirmation**, never the selector. Ordering:

1. **Entrypoint (A6d)** resolves family via torch-independent probes: `GPU_FAMILY` override → else
   device-node + PCI-vendor presence → else `cpu`.
2. **A6e** installs the matching wheel into the volume.
3. **Post-install**, `torch.<accel>.is_available()` + `resolve_device()` (A4) confirm and pick the
   device; a *forced* family whose device won't init **warns and falls back to cpu** (never silent).

**Per environment:**
- **Native (bare metal / GPU VM):** no mapping step. Accel-capable wheel + host driver present →
  `is_available()` True → `resolve_device()` picks the GPU immediately; the coach stays quiet
  (presence and capability agree). The whole mapping dance is **container-only**.
- **Container + iGPU (best inference case):** CPU model *and* the `8086` GPU PCI device in sysfs are
  usually visible **even when `/dev/dri` is unmapped** (sysfs is the host's). PCI present +
  `/dev/dri/renderD128` absent → high-confidence coach: map `/dev/dri` + `render` group +
  `GPU_FAMILY=intel-xpu`.
- **Container + CUDA/ROCm:** defaults to `cpu` until passthrough is set up (`--gpus all` /
  nvidia-container-runtime; `/dev/kfd`+`/dev/dri` for ROCm). Without it there are no device nodes and
  no injected driver libs, so capability is false and torch **cannot** confirm — the only presence
  hint is the PCI vendor (`10de`/`1002`) in sysfs, which lets the coach say "host shows an NVIDIA/AMD
  GPU; add the runtime + passthrough + `GPU_FAMILY=cuda`/`rocm`." You cannot borrow a host GPU the
  runtime didn't inject.

#### A6.5 — Implementation sub-phases (packaging → single-image, auto-or-specify GPU family)

These are the ordered, **task-sized** phases that realize the A6.4 design, each sized to the §4.4
budget (~60–80k). **A6a depends on A4** (`resolve_device`); A6c→A6f build the single-image entrypoint
in sequence; A6b/A6g are independent (measurement / deferred research). The canonical CPU Dockerfile
(D3) stays intact throughout — this adds an accel-aware entrypoint, never a fork.

##### Phase A6a — OmniVoice device seam + auto fp64-emu env `[code]`
**Mission:** move the OmniVoice model onto the resolved device and, when that device is an fp64-less
Intel xpu, set the three NEO emulation vars automatically **before load**; CPU fallback with a warning.
Runtime axis (a) for OmniVoice specifically, on top of A4.
**Read first:** `omnivoice_engine.py:296` (from_pretrained `dtype=float32`, no device) + `:298`
(generate); `qwen3_tts/device.py::resolve_device()` (A4); A6.2 (the three vars + `NEOReadDebugKeys`
gate); D10, D11.
**Do this:**
1. `device.py::xpu_needs_fp64_emulation()` — `torch.xpu.get_device_properties(...).has_fp64 == False`,
   guarded by xpu availability (import-safe on non-xpu).
2. `device.py::apply_fp64_emulation_env(environ=os.environ)` — `setdefault`s `NEOReadDebugKeys=1`,
   `OverrideDefaultFP64Settings=1`, `IGC_EnableDPEmulation=1`. Idempotent; **must run before any xpu
   context/alloc** (i.e. before OmniVoice `from_pretrained`).
3. At `omnivoice_engine.py:296`: resolve device; if xpu+needs-emu, call the emu helper first; then
   `.to(device)` (or `device=` kwarg iff the `398b6113` API accepts it — the A4 finding). CPU fallback
   **logs a warning**, never silent.
4. Report the resolved OmniVoice device in health/omnivoice status.
**Invariants:** no dep change; CPU path byte-identical; emu vars only for fp64-less xpu; `setdefault`
never clobbers an explicitly-set emu var.
**Gate:**
- `python -c "from qwen3_tts.device import xpu_needs_fp64_emulation, apply_fp64_emulation_env"` — imports `[local-verifiable]`
- no-xpu box: `resolve_device()`→`cpu`, no emu vars set `[local-verifiable]`
- unit: `apply_fp64_emulation_env({})` sets all 3 keys incl. `NEOReadDebugKeys` `[local-verifiable]`
- plexxie iGPU load+generate with auto-emu (no manual `export`) `[escalate→device]`

**Completion proof:** helpers importable; CPU path unchanged; unit green; plexxie generates without a manual emu `export`.

##### Phase A6b — Honest CPU baseline + dtype re-confirm (measurement) `[measure]`
**Mission:** replace the oversubscribed RTF 12.74 (ran `OMP_NUM_THREADS=16` on a 4-vCPU LXC) with an
honest `OMP_NUM_THREADS=4` baseline and re-confirm the fp32 pick; correct the A6.3 ratio.
**Read first:** A6.3 table; the A6.5 env-footprint note (plexxie gen scripts `/root/*.py`).
**Do this:** on plexxie, rerun CPU baseline at `OMP_NUM_THREADS=4` (same seed/text), re-confirm fp32 vs
bf16 seeded pair, update A6.3 with the corrected iGPU:CPU multiplier.
**Invariants:** measurement only, no code; plexxie is the device.
**Gate:** entirely `[escalate→device]`. **Completion proof:** A6.3 shows the `OMP=4` CPU RTF + honest ratio; seed/text recorded.

##### Phase A6c — GPU-family detection module `[code]`
**Mission:** a pure module resolving the accelerator **family** (`cpu`/`cuda`/`rocm`/`intel-xpu`) from
`GPU_FAMILY` override else torch-independent auto-probe (per **A6.4a**), plus a `has_fp64` probe and a
presence-vs-capability split for the coach. Consumed by the entrypoint (A6d) and the app (A7). Family
(which wheel) is distinct from device (runtime target, A4).
**Read first:** **A6.4a (detection model — read this first)**; A6.4 install-axis; D9, D11;
`device.py::resolve_device()` (keep family≠device clear).
**Do this:**
1. `qwen3_tts/gpu_family.py::resolve_gpu_family(environ, probes) -> 'cpu'|'cuda'|'rocm'|'intel-xpu'`.
   `GPU_FAMILY` = `auto|cpu|cuda|rocm|intel-xpu`; `auto` = `cuda>rocm>intel-xpu>cpu` via **injectable
   probes** (unit-testable without hardware).
2. **Family-selection probes are torch-INDEPENDENT** (A6.4a chicken-and-egg — the CPU-base wheel makes
   `torch.<accel>.is_available()` False even on a passed-through GPU): device nodes (`/dev/nvidia*`,
   `/dev/dri/renderD128`) + PCI vendor (`10de`/`1002`/`8086`+Xe) via `/sys`/`lspci` + CPU model. All
   guarded so import is safe on any platform. `torch.<accel>.is_available()` is only a **post-install
   confirmation** probe, never the selector.
3. `describe_accelerator() -> {family, device, has_fp64, emu_active, present, capable}` — `present`
   (host hardware seen) vs `capable` (usable now) is exactly the A7c coach trigger (present ∧ ¬capable
   → "map it"). Also feeds health + the A7 panel.
**Invariants:** pure (no installs, no env mutation); import-safe everywhere; family≠device; **family
selection never depends on `torch.<accel>.is_available()`** (A6.4a).
**Gate:**
- unit table drives all 5 branches via mocked probes `[local-verifiable]`
- `GPU_FAMILY=cpu` forces `cpu` regardless of probes `[local-verifiable]`
- unit: **PCI-present + device-node-absent** yields `present=True, capable=False` (the A7c trigger),
  and family selection ignores `torch.<accel>.is_available()` `[local-verifiable]`
- real detection on plexxie → `intel-xpu`, `has_fp64=False` `[escalate→device]`

**Completion proof:** module + unit table green; forced override works; plexxie detects `intel-xpu`/`has_fp64=False`.

##### Phase A6d — Accel-aware entrypoint: family resolution + runtime env `[infra]`
**Mission:** an entrypoint that resolves the family (A6c), applies the **per-family runtime env**
(Intel NEO emu vars when fp64-less via the A6a helper; `OPENVINO_DEVICE`; CUDA/ROCm visibility), then
`exec`s the existing server CMD — **assuming the correct torch wheel is already present** (install is
A6e). Approach (ii) skeleton.
**Read first:** `Dockerfile` (ENTRYPOINT/CMD, gunicorn); A6.4 (ii); A6a emu helper; A6c family module; D3, D9, D11.
**Do this:**
1. `docker/entrypoint.sh` (or py): resolve family, export per-family env, log family+device, `exec`
   the current CMD. CPU exports nothing new.
2. Wire `Dockerfile` `ENTRYPOINT` to it; `CMD` unchanged.
3. `GPU_FAMILY=auto` default; explicit override honored.
**Invariants:** canonical Dockerfile stays (D3); CPU image identical to today when `GPU_FAMILY` unset/→cpu; **no torch install here** (A6e).
**Gate:**
- dry-run/echo mode, `GPU_FAMILY=cpu`: execs server, sets no emu vars `[local-verifiable]`
- dry-run, `GPU_FAMILY=intel-xpu` (mocked family): exports the 3 emu vars + `OPENVINO_DEVICE` `[local-verifiable]`
- container build boots to healthy on cpu `[escalate→device]`

**Completion proof:** entrypoint script; cpu dry-run sets nothing; xpu dry-run sets emu+OV env; cpu container boots healthy.

##### Phase A6e — First-boot torch install-on-demand (per family, into a named volume) `[infra]`
**Mission:** on first boot, if the resolved family's torch wheel isn't in the persisted accel venv,
install it (torch **2.8.0+xpu** for `intel-xpu` + OmniVoice `--no-deps`, per A6.1; cuda/rocm/cpu
variants) into a named volume and reuse it thereafter. Truly one image; cost = slow first boot +
runtime network (or a bundled wheel cache).
**Read first:** A6.4 (ii); A6.1 repro recipe (torch 2.8.0+xpu + torchaudio + OmniVoice `--no-deps @398b6113`); `Dockerfile` pip flow; D3, D11.
**Do this:**
1. Entrypoint step **before** A6d env/exec: resolve family → check a per-family marker in a named
   volume (e.g. `/opt/accel-venv`); if absent, `pip install` the family torch (+torchaudio), then
   OmniVoice `--no-deps` on top (mirrors the Dockerfile), write the marker.
2. Point the server's Python at the volume venv when populated; `GPU_FAMILY=cpu` uses the **baked** CPU
   torch (no install).
3. Optional bundled wheel-cache dir to avoid runtime network (documented, off by default).
**Invariants:** cpu needs no install; install idempotent (marker); a **failed install must not leave a
marker**; OmniVoice pin/rev matches A6.1.
**Gate:**
- cpu family: no-install path, boots on baked torch (marker/log assert) `[local-verifiable]`
- idempotency: second boot with marker present skips install `[local-verifiable]`
- intel-xpu first boot on plexxie populates the volume + OmniVoice generates `[escalate→device]`

**Completion proof (done 2026-07-22):** implemented in `scripts/entrypoint.sh` — resolves
`ACCEL_VENV_DIR` (default `/opt/accel-venv`), installs the per-family torch (+torchaudio) and
OmniVoice `--no-deps @398b6113` into `$ACCEL_VENV_DIR/<family>/site-packages` only when
`.installed` is absent, then prepends that dir to `PYTHONPATH`; `set -e` means a failed `pip
install` exits before the marker is written (invariant satisfied by construction, not a separate
check). Verified locally with `GPU_FAMILY` forced + a mocked `ACCEL_VENV_DIR`: **cpu family
installs nothing** (no `$ACCEL_VENV_DIR` contents created) and **intel-xpu with a pre-seeded
marker skips the pip install** (logs "cached torch install found, skipping install"). torch/index
values match the A6.1-proven recipe exactly for `intel-xpu` (`torch==2.8.0`+torchaudio from
`download.pytorch.org/whl/xpu`); `cuda`/`rocm` index URLs and versions are **plausible but
unvalidated** (override via `ACCEL_TORCH_INDEX_URL`/`ACCEL_TORCH_VERSION` if wrong when a CUDA/ROCm
box becomes available). The `[escalate→device]` gate — **a real container first-boot on plexxie's
iGPU** — could not be run: plexxie has no Docker installed (see plexxie-hardware-test-host memory).
Not a gap in the *install recipe* itself (that's the same one A6.1 already proved end-to-end in a
native venv on this exact hardware) — only the container-wrapper script's marker/PYTHONPATH logic
is unverified on real xpu hardware specifically. Flagging as a known, expected limitation rather
than a silent pass; revisit if/when Docker is ever set up on plexxie.

##### Phase A6f — Base-image system-lib layering + passthrough docs/compose `[infra+docs]`
**Mission:** layer the non-conflicting userspace libs (Intel compute-runtime + `libze1`; CUDA/ROCm
userspace) into the base image so **only the torch wheel varies at runtime** (A6.4 note); document
`/dev/dri` + render-group + `GPU_FAMILY` in a compose example; reconcile the A5 matrix.
**Read first:** A6.1 (`libze1`, Intel compute-runtime apt); A6.4 system-libs bullet; Phase A5 matrix
(the "OmniVoice stays CPU (D10)" row); compose file; D3, D11.
**Do this:**
1. Layer Intel compute-runtime + `libze1` (+ optionally CUDA/ROCm userspace — they coexist) into the
   base image; note the size cost.
2. Compose example: `/dev/dri` devices + render group + `GPU_FAMILY` + the data volume (ties to A7's
   minimal-container goal).
3. Update the A5 matrix row: **OmniVoice runs on the Intel iGPU via torch-xpu + fp64 emu** (distinct
   from the rejected OmniVoice→OpenVINO port); keep the OpenVINO-backend iGPU note for the base model.
**Invariants:** canonical CPU Dockerfile still builds/runs when `GPU_FAMILY=cpu`; no CI change; A5 stays docs.
**Gate:**
- `docker compose config` parses the example (`/dev/dri` + `GPU_FAMILY`) `[local-verifiable]`
- A5 matrix corrected, grep confirms `[local-verifiable]`
- base image builds with the layered libs `[escalate→device]`

**Completion proof (done 2026-07-22):** `Dockerfile` gained a build-arg-gated
(`INSTALL_ACCEL_SYSLIBS=0` default) layer for Intel compute-runtime + Level-Zero via Intel's
official GPU apt repo (`repositories.intel.com/gpu/ubuntu jammy unified` — same package/version
set proven on plexxie in A6.1); default-off keeps the canonical CPU build byte-for-byte unchanged
(D3), confirmed by a real local rebuild that succeeded identically. `compose.yml` documents the
full opt-in path: commented `build.args.INSTALL_ACCEL_SYSLIBS`, `/dev/dri` + `group_add` (render
group) device passthrough, a live (uncommented, default `auto`) `GPU_FAMILY` env var, and a new
named volume `accel-venv:/opt/accel-venv` for A6e's first-boot install persistence.
`docker compose config` parses the whole file cleanly (verified: `GPU_FAMILY: auto` and the
`accel-venv` volume both resolve correctly in the rendered config). `docs/dev/LOCAL_SETUP.md`'s
Intel-iGPU matrix row is corrected — it no longer says "OmniVoice stays CPU (D10)" (stale,
pre-A6) and now states OmniVoice runs on the same iGPU via torch-xpu, distinct from the
OpenVINO/Qwen3-TTS path. The one **`[escalate→device]`** gate — a real accel-lib image build
verified against actual Intel iGPU hardware — was **not** run: pulling Debian trixie's own apt
archive confirmed (via `apt-cache search`) it carries none of these packages, so this relies on
Intel's apt repo, which has historically targeted Ubuntu, not Debian; compatibility is plausible
but genuinely unverified until built + exercised on real hardware (plexxie has no Docker, so
this can't happen there yet either). Documented as a known, flagged gap rather than a silent
pass.

##### Phase A6g — int8 PTQ exploration (deferred follow-up) `[research]`
**Mission:** only if bf16/fp16 didn't buy headroom (they didn't) and memory pressure demands it —
explore int8 PTQ for OmniVoice on Xe-LP. Low priority; fp32 is already fastest.
**Read first:** A6.3 verdict; the DSP-vs-artifact eval criterion (artifacts disqualify, tonal/level
diffs don't); D11.
**Do this:** scope a PTQ probe (which submodules quantize cleanly; artifact check); do **not** integrate
without an A/B pass.
**Gate:** `[escalate→frontier]` (is it worth it?) + `[escalate→device]` (the probe). **Completion proof:** a written go/no-go with measured artifact + RTF deltas.

**Env footprint left on plexxie** (restorable; daily backups): `/root/xpu28` venv (torch 2.8+xpu +
OmniVoice), `libze1` loader, upgraded Intel compute-runtime (apt), OmniVoice checkpoint in HF cache,
probe/gen scripts under `/root/*.py`, output wavs `/root/omni_*.wav`. Full detail in the
`omnivoice-igpu-goal` memory.

### Phase A7 — Persisted runtime config + layered precedence + container coach (premium Runtime page)

**Goal (user, 2026-07-21):** shrink the container's required config to near-zero (data volume +
`/dev/dri`), **elevate performance/runtime tuning into the app**, persist it to the data dir, and
re-apply it on start — with a premium, guided UX. Implements **D11**.

**Current state (verified):**
- `RuntimeConfigPage.tsx` + `GET/POST /runtime/config` → `model.apply_runtime_config()` already let a
  user hot-change backend / dtype / silence-trim etc. with a **live in-process model reload**.
- **Gap:** `apply_runtime_config` writes `os.environ` **in-process only — not to disk** — so every
  change is lost on restart and reverts to compose/`.env`. `config.py::apply_preset_env` seeds
  low-level OV vars via `setdefault` (explicit env wins).

**Precedence model (D11):** `env-locked container var` > `persisted runtime.json` > `image default`.
On startup the app reads `runtime.json` and layers it **over** the image/compose defaults, **except**
keys an operator has marked env-locked (or that arrive as an explicitly-flagged container override).

**Implementation sub-phases** (task-sized per §4.4). A7a→A7b are pure backend and depend on **nothing
new** — do them first, immediately useful for native runs. A7c/A7d are frontend and build on A6c
(`describe_accelerator`) + Initiative C's C1/C2 seams; schedule after A6c and alongside C1/C2.

##### Phase A7a — Persistence backend (runtime.json + startup layering) `[code]`
**Mission:** persist runtime config to `${DATA_DIR}/runtime.json` and layer it over image defaults at
startup (D11 precedence: `env-locked > file > default`), keeping `apply_preset_env`'s `setdefault`
seam underneath.
**Read first:** `config.py::apply_preset_env` (setdefault seam + "call once before torch/OV import"
ordering); `model.py::apply_runtime_config` (:968, mutates `os.environ` in-process) + `runtime_config_state` (:896);
`app.py` `/runtime/config` GET/POST (~2096); D11.
**Do this:**
1. `qwen3_tts/runtime_store.py`: `load_persisted_config()` / `save_persisted_config()` on
   `${DATA_DIR}/runtime.json` — atomic temp+rename, schema-versioned, unknown keys ignored, a corrupt
   file **warns and is ignored** (never crashes boot).
2. `apply_persisted_config(environ)` runs **after** `apply_preset_env`, **before** torch/OV import
   (same import-time site `model.py` uses), layering file values **over** the setdefault seed,
   **skipping env-locked keys**.
3. Env-lock registry: `RUNTIME_LOCKED_KEYS` (csv) and/or `RUNTIME_LOCK_<KEY>=1`; `is_locked(key)` helper.
4. `apply_runtime_config` gains `persist=True`: on a **successful** reload, write through to
   `runtime.json`; a **failed reload must not persist**.
**Invariants:** setdefault expert seam preserved; corrupt/missing file never crashes; cpu default
behavior unchanged with no `runtime.json`; reuse the existing voices/segments data root.
**Gate:**
- unit: save→load round-trips; corrupt file → ignored+warn `[local-verifiable]`
- unit: env-locked key not overridden by file `[local-verifiable]`
- unit: failed reload does not persist `[local-verifiable]`
- integration: POST a backend change, restart the process, value survives `[escalate→device]`

**Completion proof:** `qwen3_tts/runtime_store.py` implements `load_persisted_config()`/
`save_persisted_config()` (atomic temp+`os.replace`, schema-versioned `{"schema_version": 1,
"values": {...}}`, corrupt/malformed files warn-and-ignore rather than crash), `locked_keys()`/
`is_locked()` (`RUNTIME_LOCKED_KEYS` csv + `RUNTIME_LOCK_<KEY>=1`), and `apply_persisted_config()`,
wired into `model.py` immediately after `apply_thread_env()` and before `import torch`.
`apply_runtime_config()` gained `persist: bool = True`, writing through to `runtime.json` only after
the existing try/finally block completes without raising (mirrors A6e's "failed op never leaves
evidence" pattern by construction, not an extra check). `DATA_DIR` defaults to
`VOICE_LIBRARY_DIR`/`VOICE_LIBRARY_PATH_CONTAINER` (falling back to `/voices`) so no new compose
volume is required. Unit suite (`tests/tier1_unit/test_runtime_store.py`, 10 cases) covers all three
`[local-verifiable]` gates: save→load round-trip, corrupt/malformed file → ignored+warn, env-locked
key not overridden by file, and failed-reload-does-not-persist (the last one runs in a subprocess —
`qwen3_tts.model` spawns a real background self-load thread at import time, which would otherwise
leak into other tests' shared `sys.modules` state if imported in-process). Full suite (506 tests)
passes clean, run 3x to rule out flakiness. The `[escalate→device]` restart-survival gate turned out
to be locally verifiable (it's process-restart persistence, not GPU-specific): confirmed manually
that a value written by one process (`save_persisted_config`) is read back correctly by a completely
fresh `python` process importing `qwen3_tts.model`, via `os.environ` after `apply_persisted_config`
runs at import time.

##### Phase A7b — API surface: source/lock/restart metadata + reset/dry-run `[code]`
**Mission:** report per-key provenance so the UI can render it, and add reset + dry-run.
**Read first:** `model.py::runtime_config_state` (:896); `app.py` `/runtime/config` (~2096);
`frontend/src/lib/api.ts` `RuntimeConfigState` + `getRuntimeConfig`/`updateRuntimeConfig` (~1162–1207); A7a store; D11.
**Do this:**
1. `runtime_config_state()` returns, per exposed key: `{value, source: file|env|default, locked,
   restart_required}` — `restart_required` flags entrypoint-only keys (`GPU_FAMILY`, torch wheel, `/dev/dri`).
2. `POST /runtime/config/reset` (drop `runtime.json` → revert) + a `dry_run` preview on POST.
3. Update `api.ts` types (no UX yet).
**Invariants:** existing POST live-reload contract unchanged; additive fields only; no UX change here.
**Gate:**
- state returns `source`/`locked`/`restart_required` per key `[local-verifiable]`
- reset drops file + reverts (integration on a temp `DATA_DIR`) `[local-verifiable]`
- `npm run build` typechecks the new `api.ts` shape `[local-verifiable]`

**Completion proof:** `model.py::runtime_config_state()` now returns `live_metadata` (additive dict,
per exposed `LIVE_RUNTIME_KEYS` key: `{value, source: file|env|default, locked, restart_required}`,
`source` computed from a fresh `load_persisted_config()` read vs. `os.environ`) and a top-level
`restart_required` dict (currently `GPU_FAMILY` only, entrypoint-only). `preview_runtime_config(updates)`
added as a pure dry-run (no `os.environ`/global/file mutation) returning
`{dry_run, would_apply, would_skip_locked, reload_required, predicted_live}`; wired into
`POST /runtime/config` via a `dry_run` body flag (checked before the executor-serialized mutation
path, so no concurrency guard needed for previews). `reset_runtime_config()` added: drops
`runtime.json` entries for unlocked keys (keeping locked keys' persisted values, since a lock is an
explicit operator override that should survive a reset), removes those unlocked keys from
`os.environ` so the existing `os.getenv(key, <default>)` fallbacks take over, triggers the same
reload logic as `apply_runtime_config` when a reverted key needs it, and re-persists only the locked
subset; wired to new `POST /runtime/config/reset` with the same concurrency guard
(`reconfig_in_progress`/`swap_in_progress`) as the existing POST. `frontend/src/lib/api.ts`'s
`RuntimeConfigState` interface extended additively with optional `live_metadata`/`restart_required`
fields (existing `live`/`read_only`/`not_live` shapes untouched — no consumer changes needed), plus a
new `RuntimeConfigPreview` type, `previewRuntimeConfig()`, and `resetRuntimeConfig()` client
functions. All three gates verified locally: (1) `tests/tier1_unit/test_runtime_config_a7b.py` (4
new cases, subprocess-isolated per the A7a precedent since real `model.py` self-loads a background
thread at import time) confirms `live_metadata`/`restart_required` shape and per-key
`source`/`locked` values, including a `RUNTIME_LOCKED_KEYS`-locked case; (2) a reset case on a temp
`DATA_DIR` confirms locked keys survive in `runtime.json` while unlocked keys are dropped and their
live values revert to hardcoded defaults; (3) a dry-run case confirms `preview_runtime_config`
touches neither live state nor `runtime.json`. Full suite green 3x consecutively (510 passed each
run, no flakiness). `npx tsc --noEmit` in `frontend/` compiles clean with the new types.

##### Phase A7c — Container coach: copy + card `[decide-once]+frontend`
**Mission:** surface the container-level settings the app **can't** self-apply (device passthrough,
`GPU_FAMILY` override, data volume) as an in-app coach card with copy-paste compose snippets + re-detect.
**The card's trigger is the A6.4a present∧¬capable gap** — host hardware seen but not usable yet.
**Read first:** **A6.4a (detection model — the present vs capable split drives this card)**; A6.4
packaging knobs; A6c `describe_accelerator` (`present`/`capable`/family/device); D8 (copy in markdown),
D11; `RuntimeConfigPage.tsx`.
**Do this:**
1. Markdown coach copy (`frontend/src/content/help/…` per D8): per family, what to add to
   compose/`docker run` — Intel iGPU `/dev/dri`+`render` group, NVIDIA `--gpus all`+nvidia-runtime,
   ROCm `/dev/kfd`+`/dev/dri` — when to override `GPU_FAMILY`.
2. Coach card in `RuntimeConfigPage`, shown when `describe_accelerator()` reports **`present ∧
   ¬capable`** (or a forced family that fell back to cpu), rendering the family-specific snippet + a
   re-detect button. Stays quiet on native/already-mapped (present ∧ capable agree).
**Invariants:** copy lives in markdown (D8); card shows only what the app can't self-apply, and only on
the present∧¬capable gap (never on native where it'd be noise); no power-user control unmounted.
**Gate:**
- build + card renders the snippet from markdown `[local-verifiable]`
- coach copy strings `[decide-once]`
- reads-clearly in a real iGPU-LXC scenario `[escalate→device]`

**Completion proof:** Fixed a real gap in `gpu_family.py::describe_accelerator()` — it computed the
actually-detected vendor via `_detect_best(probes)` but discarded it, returning only the
override-aware `family` (which reads `"cpu"` in the present∧¬capable case even when a real GPU is
present). Added `detected_family` as an additive dict field so the coach can pick the right
per-vendor snippet; covered by 2 new/extended cases in `test_gpu_family.py`
(`test_present_true_capable_false_is_the_coach_trigger` extended,
`test_detected_family_differs_from_family_under_forced_override` added) — 14 passed (was 13).
Wired `describe_accelerator()`'s output into `model.py::runtime_config_state()` as an additive
`accelerator` field (import-safe, pure). Added three D8-compliant markdown coach-copy files under
`frontend/src/content/help/` (`accelerator-cuda.md`, `accelerator-rocm.md`,
`accelerator-intel-xpu.md`) with per-family compose/`docker run` snippets and a re-detect
instruction. Built `AcceleratorCoachCard.tsx` — a dependency-free `MarkdownLite` renderer (no new
npm markdown package, per the project's anti-over-engineering stance) plus the card itself, which
renders only when `present ∧ ¬capable ∧ detected_family !== 'cpu'` and stays quiet otherwise
(dismissed/no-hardware/already-mapped/bare-cpu). Wired into `RuntimeConfigPage.tsx` with a
"Re-detect" button that re-calls the existing `refresh()`/`getRuntimeConfig()` flow. Extended
`api.ts`'s `RuntimeConfigState` with the additive `accelerator` field. Verified: `npx tsc --noEmit`
clean; `npm run build` succeeds; full backend suite green (511 passed); manual dev-server check —
Flask (port 8318) + Vite (port 5183, proxying `/runtime` to Flask) both started, `curl
/runtime/config` confirmed the `accelerator` field shape, and a Puppeteer screenshot of
`RuntimeConfigPage` (via system Chrome, no console/pageerror output) confirmed the page renders
correctly with the coach card correctly absent on this no-GPU dev Mac (`present: false`). The
`reads-clearly in a real iGPU-LXC scenario [escalate→device]` gate requires plexxie hardware and is
deferred to a future on-device check, consistent with how A7a's device-gated gate was handled.

##### Phase A7d — Premium Runtime control surface (UX) `[frontend]`
**Mission:** reframe `RuntimeConfigPage` as the premium control surface — per-key source/lock badges,
live-vs-restart affordances, detected-accelerator panel, Basic/Expert disclosure (D7 never-unmount).
*If the Read-first + diff approaches ~80k, split into A7d (badges + live/restart + lock-disable) and
A7e (accelerator panel + Basic/Expert disclosure).*
**Read first:** `RuntimeConfigPage.tsx` (current `apply()`/draft/diff); A7b state fields; A6c
`describe_accelerator`; Initiative C C1 (`MetricExplainer`) + C2 (`Disclose` seam) if landed; D7, D8, D11.
**Do this:**
1. Add per-key badges (file / env-locked / default) from A7b `source`/`locked`; **disable + explain**
   env-locked keys (the existing draft/diff stays).
2. "Applies live" vs "Needs restart" affordance from `restart_required`.
3. Detected-accelerator panel (family, device, fp64-emu state) from `describe_accelerator`.
4. Basic surfaces high-impact knobs; Expert reveals full env via the C2 `Disclose` seam (reuse if
   present; else a local disclosure that never unmounts). Tooltips reuse C1.
**Invariants:** no power-user control removed (D7); works even if C1/C2 haven't landed (graceful local
fallback); build passes.
**Gate:**
- build + badges/panel/disclosure greps `[local-verifiable]`
- disclosure boundary + which knobs are "Basic" `[decide-once]`
- env-locked disables + never-unmount + accelerator panel in-browser `[escalate→device]`

**Completion proof:** Initiative C's `MetricExplainer`/`Disclose` seam (C1/C2) was not landed at the
time of this phase (confirmed via grep — no matches for either symbol under `frontend/src/`), so
per the invariant this used a local disclosure fallback: a `KeyBadges` helper renders per-key
`source`/`env-locked`/`applies live`|`needs restart` badges from A7b's `live_metadata`, and each
live-adjustable input is `disabled` (with an explanatory `title`) when its `locked` flag is set.
A "Show advanced"/"Hide advanced" toggle (`expertMode` state) reveals these badges plus the two
lower-impact silence-trim fine-tuning fields (threshold, pad) and a new fp64/emulation detail on
the accelerator panel — implemented via a CSS `hidden` class toggle, never a conditional unmount,
satisfying D7. Basic/Expert boundary (decide-once): Backend, Idle unload, OV quant group size,
Model dtype, and the Silence trim on/off toggle stay in Basic (high-impact, always visible);
per-key provenance badges, fp64/emulation detail, and the two silence-trim fine-tuning fields are
Expert-only. Added an always-visible "Detected accelerator" panel (family/device/capable, plus
has_fp64/fp64_emulation under Expert) sourced from `describe_accelerator()` — distinct from the
A7c coach card, which only appears on the present∧¬capable gap. Added a "Requires container
restart" panel surfacing the top-level `restart_required` dict (e.g. `GPU_FAMILY`), gated behind
Expert. Verified: `npx tsc --noEmit` clean; `npm run build` succeeds; full backend suite green
(388 tier1 unit tests, unaffected since this was a frontend-only change); Puppeteer screenshots
(via system Chrome) of both Basic and Expert states with no console/pageerror output, confirming
badges, lock-disabling, the accelerator panel, and the restart-required panel all render correctly
on this no-GPU dev Mac. The `env-locked disables + never-unmount + accelerator panel in-browser
[escalate→device]` gate's env-locked-disable behavior was exercised via code review (the `disabled`
prop is wired to `live_metadata[key].locked` for every live field) but not against a real
env-locked container; full confirmation is deferred to plexxie, consistent with how A7a/A7c's
device-gated gates were handled.

This closes out Initiative A (A1–A7d). Per the standing batching instruction, ledger status tables
in this plan (§9) and the execution companion (§4/§5) are updated together now that all of
Initiative A is complete.

Do **not** commit the plan doc without user OK.

## 7. Initiative B — real-model capture harness

> Extends `docs/dev/resolved/E2E_AND_SCREENSHOTTING.md` (whose fake-model tier stays as-is). All
> B phases inherit §4.1 (privacy), §4.2 (additive/no-CI). Model-load and visual-acceptance gates
> are `[escalate→device]`; pure-code gates are `[local-verifiable]`.

### Phase B1 — Real-server spawn mode

**Mission:** add `tests/ui/run-real-server.mjs` that spawns the real backend (Flask dev server,
D1) on disposable temp dirs and blocks until `model_loaded: true` — zero manual steps.

**Preconditions** `[local-verifiable]`:
```bash
cd /Users/nick/SCRIPTS/CLAUDE/qwen3-tts-openvino
test -f tests/ui/run-server.mjs && echo "run-server OK"
# The app must import (this is what we spawn — NOT gunicorn, D1):
PYTHONPATH=src:.:src/export uv run python -c "from qwen3_tts.app import app; print('app import OK')" 2>&1 | tail -1
```
(If Initiative A isn't done, substitute `.venv/bin/python` for `uv run python`.)

**Read first:** `tests/ui/run-server.mjs` (the `startFakeServer` twin: `resolvePython()`, env
block, `waitUntilHealthy`, `stop()`, `import.meta.url` block); §2.2 (import-time loader at
`model.py:669`, health fields at `model.py:747`); D1.

**Do this:**
1. Factor `resolvePython()` out of `run-server.mjs` into `tests/ui/lib/python.mjs`; import it back
   into `run-server.mjs`. Change nothing else about `run-server.mjs`'s contract.
2. Create `tests/ui/run-real-server.mjs` exporting
   `startRealServer({ port, voiceLibraryDir, segmentLibraryDir, modelSize='0.6B', device='cpu', timeoutMs=120000 })`
   → `{ child, url, port, waitUntilHealthy, stop }`.
   - Default the dirs to `mkdtempSync(join(tmpdir(),'qwen3-tts-capture-voices-'))` /
     `...-segments-'`. **Never** `./data/voices` / `./data/segments` (§4.1).
   - Spawn the Flask dev server (D1):
     `<python> -c "from qwen3_tts.app import app; app.run(host='127.0.0.1', port=<port>, threaded=True)"`,
     `stdio: 'inherit'`. Importing the app auto-starts the background loader (`model.py:669`).
   - Env (only these on top of `process.env`): `PYTHONPATH` = repoRoot`:`src`:`src/export;
     `TTS_BACKEND=pytorch`; `DEVICE=<device>`; `MODEL_SIZE=<modelSize>`; `VOICE_LIBRARY_DIR`/`SEGMENT_LIBRARY_DIR`
     = temp dirs; `FRONTEND_DIST_DIR=<repoRoot>/frontend/dist`; `FRONTEND_ENABLED=1`;
     `IDLE_UNLOAD_SECONDS=0`. Pass `HF_TOKEN` only if `process.env.HF_TOKEN` is set.
3. `waitUntilHealthy(timeoutMs)` polls `GET /health` every ~500ms until `model_loaded === true`;
   on timeout throw an error **including the last `/health` body** (surfaces gated-download /
   `_startup_error`), default 120000ms.
4. `stop()` = SIGTERM then SIGKILL after ~3s; wire `process.on('exit'/'SIGINT'/'SIGTERM')`.
5. Direct-run block: optional port from `argv[2]`, call `startRealServer`, `await
   waitUntilHealthy()`, **print the URL and the two temp dir paths**, run until Ctrl-C.

**Invariants:** spawned dirs are temp, never real data dirs; `run-server.mjs` contract + fake/CI
path unchanged; Flask dev server (D1), no gunicorn/waitress dependency, no new entrypoint.

**Gate:**
```bash
cd /Users/nick/SCRIPTS/CLAUDE/qwen3-tts-openvino
node tests/ui/run-real-server.mjs 8893
#   [escalate→device] prints "healthy at http://127.0.0.1:8893" + two temp dir paths.
#   VISUALLY CONFIRM both printed dirs are under $TMPDIR, NOT .../data/voices|segments (privacy gate).
# second shell:
curl -s http://127.0.0.1:8893/health | grep -q '"model_loaded": *true' && echo "MODEL LOADED OK"   # [escalate→device]
node tests/ui/run-server.mjs 8894   # [local-verifiable] fake tier still healthy; Ctrl-C both.
```

**Completion proof:** `lib/python.mjs`, `run-real-server.mjs`, small `run-server.mjs` import edit;
device gate shows MODEL LOADED + temp paths; observed first-load time recorded.

### Phase B2 — Fixture data + seeding

**Mission:** small **synthetic, checked-in** fixtures + `seedCaptureFixtures()` copying them into
temp dirs at spawn — realistic library state, never real data (§4.1).

**Preconditions** `[local-verifiable]`: `test -f tests/ui/run-real-server.mjs && echo "B1 OK"`.

**Read first (derive schema from source, never memory):** `src/qwen3_tts/voice_library.py`
(`save_voice`, variant funcs, `list_voices`, `duplicated_from`); `src/qwen3_tts/segment_library.py`
(`save_segment`/`list_segments`, `{clip.wav,meta.json}` layout, `project_id`/`project_name`/
`feature_tags`/`tags`); §2.2 verified routes; `VoiceLibraryPage.tsx` `getSourceBadges`.

**Do this:**
- *Part A* — one-time generator `tests/ui/fixtures/generate-capture-fixtures.mjs` (manual, NOT
  called by `capture.mjs`; top comment says so): spawn a real server on a throwaway temp dir,
  drive the real API to create the **minimum** set — one base voice with two variants (2nd
  promoted active), one duplicated voice with `duplicated_from`, 2–3 segments sharing a
  `project_id`/`project_name` + 1–2 without, 2–3 segments with distinct `feature_tags`/`tags`; all
  generation text generic/impersonal; copy the dirs into `tests/ui/fixtures/capture-data/{voices,segments}/`;
  run once; commit.
- *Part B* — `seedCaptureFixtures(voiceLibraryDir, segmentLibraryDir)` (in `run-real-server.mjs`
  or `tests/ui/lib/seed.mjs`) copies `capture-data/*` into the temp dirs; called from
  `startRealServer()` after temp dirs exist and **before** spawning the server. Only ever copies
  FROM committed fixtures.

**Invariants:** `capture-data/` only synthetic (Part A output); never copy from real dirs; small
(low hundreds of KB); schema derived from Python source.

**Gate:**
```bash
cd /Users/nick/SCRIPTS/CLAUDE/qwen3-tts-openvino
ls tests/ui/fixtures/capture-data/voices tests/ui/fixtures/capture-data/segments   # [local-verifiable]
du -sk tests/ui/fixtures/capture-data                                              # [local-verifiable] low hundreds of KB
node tests/ui/run-real-server.mjs 8895 & sleep-until-healthy; \
  curl -s http://127.0.0.1:8895/voices; curl -s http://127.0.0.1:8895/omnivoice/segments   # [escalate→device] counts match fixtures
```
Fixture **privacy review** (every clip synthetic) is `[decide-once]` — confirmed once at generation.

**Completion proof:** committed fixture counts; total KB; endpoint counts match; privacy confirmed.

### Phase B3 — `capture.mjs` real-mode wiring

**Mission:** add `--real` and prove one existing scenario runs real end-to-end in one command.

**Preconditions** `[local-verifiable]`: `test -f tests/ui/run-real-server.mjs` and
`ls tests/ui/fixtures/capture-data/voices` both succeed.

**Read first:** `tests/ui/capture.mjs` (whole file); `run-real-server.mjs` `startRealServer`.

**Do this:** extend `parseArgs` with `--real` (mutually exclusive with `--target`),
`--model-size <0.6B|1.7B>` (default `0.6B`), `--device <cpu|mps>` (default `cpu`); in `main()`
branch to `startRealServer(...)` when `args.real` (generous ~120s wait); keep the fake path
byte-for-byte unchanged; change no existing scenario (prove with `scenarioHome`).

**Invariants:** fake path unchanged/verified; real mode fully automated; do not touch
`run-server.mjs` or `fake_model_server.py`.

**Gate:**
```bash
cd /Users/nick/SCRIPTS/CLAUDE/qwen3-tts-openvino
node tests/ui/capture.mjs --scenario scenarioHome            # [local-verifiable] fake path writes core/home.png
node tests/ui/capture.mjs --real --scenario scenarioHome     # [escalate→device] real spawn→seed→capture→teardown
ls -la docs/screenshots/artifacts/core/home.png              # [local-verifiable] recent, non-zero
```

**Completion proof:** `parseArgs`/`main()` diff; both runs pass; real-run wall-clock recorded.

### Phase B4 — GIF capture helpers

**Mission:** port `captureFrames`/`framesToGif`/`cleanupFrames` into `tests/ui/lib/gif.mjs`; prove
one trivial GIF renders and cleans up.

**Preconditions** `[local-verifiable]`: `which ffmpeg` → `/opt/homebrew/bin/ffmpeg`;
`test -f ../llama-monitor/tests/ui/capture.mjs`.

**Read first (actual bodies, not memory):** `../llama-monitor/tests/ui/capture.mjs` — find with
`grep -n "captureFrames\|framesToGif\|cleanupFrames" ../llama-monitor/tests/ui/capture.mjs`;
`tests/ui/capture.mjs` for `outPath`/`ARTIFACTS_DIR`.

**Do this:** create `tests/ui/lib/gif.mjs` with the three exports (frames → temp `frames/` dir,
final `.gif` via `outPath`); invoke ffmpeg with `execFileSync`/`spawn` **argument arrays** (never
a shell string); don't wire into scenarios yet.

**Invariants:** no npm ffmpeg dep (system binary); array-args only; `frames/` cleaned up.

**Gate:** write throwaway `tests/ui/lib/_gif_smoke.mjs` (fake home page, ~1s capture, gif, cleanup):
```bash
cd /Users/nick/SCRIPTS/CLAUDE/qwen3-tts-openvino
node tests/ui/lib/_gif_smoke.mjs                                                        # [local-verifiable]
find docs/screenshots/artifacts -name '*.gif' -exec file {} \; | grep -i "GIF image data" | head -1   # [local-verifiable]
find docs/screenshots/artifacts tests/ui -type d -name frames                          # [local-verifiable] expect no output
rm tests/ui/lib/_gif_smoke.mjs
```

**Completion proof:** `lib/gif.mjs` with three exports; a valid GIF; cleanup confirmed; smoke removed.

### Phase B5 — `data-testid` additions (demand-driven)

**Mission:** add stable testids only where a B6 scenario needs them — no blanket sweep, no build
breakage. May be executed lazily inside B6.

**Preconditions** `[local-verifiable]`:
```bash
grep -c "data-testid" frontend/src/components/waveform/AlignmentCompare.tsx   # 0 as of 2026-07-20
grep -rn "omnivoice-result" frontend/src/components/OmniVoicePanel.tsx        # exists; don't re-add
```

**Read first (fresh):** `AlignmentCompare.tsx` (zero testids); `VoiceLibraryPage.tsx` (variant
list + promote button, fork badge via `VoiceSourceBadges`/`getSourceBadges`, project grouping).

**Do this — add ONLY what a scenario needs, names:** `alignment-compare` (root),
`alignment-lane-original` / `alignment-lane-adjusted`, `alignment-pause-handle`,
`voice-variant-row` / `voice-variant-promote`, `voice-fork-badge`, `voice-project-group`. Reuse a
better existing selector if present and note the deviation. Each id in the actual component file.

**Invariants:** don't remove/rename existing testids; `npm run build` passes after each addition.

**Gate:**
```bash
cd /Users/nick/SCRIPTS/CLAUDE/qwen3-tts-openvino/frontend && npm run build   # [local-verifiable] exit 0
grep -n 'data-testid="alignment-compare"' src/components/waveform/AlignmentCompare.tsx   # [local-verifiable]
```

**Completion proof:** testids + file/line; build pass; which scenario each served.

### Phase B6 — Scenario catalog build-out

**Mission:** grow real-tier coverage so every significant surface is capturable on demand. **One
scenario per change/agent** — do not attempt the catalog in one PR.

**Preconditions** `[local-verifiable]`: `node tests/ui/capture.mjs --real --scenario scenarioHome`
succeeds (B3); `test -f tests/ui/lib/gif.mjs` for GIF scenarios (B4).

**Read first:** `tests/ui/capture.mjs` `SCENARIOS` shape; `tests/ui/lib/gif.mjs` for GIFs.

**Pattern (adding one scenario):** add `async scenario<Name>({ page, baseURL })` modeled on the
existing ones; **wait on real UI state** (`page.waitForSelector`), never a fixed `sleep`
(real-tier waits are generous — model swap latency between Base/OmniVoice scenarios is expected);
add any missing testid per B5 in the same change; `screenshot(...)` or a GIF via B4; register it
in the categorized `--list-scenarios`.

**Catalog (adjust + document here if a feature differs from this description):**
- *Voice Library:* `scenarioVoiceVariantList`, `scenarioVoicePromoteVariant` (before/after — also
  regression visibility for the promotion-refresh fix), `scenarioVoiceForkBadge`,
  `scenarioVoiceMountedWarning` (only if a mounted-ref fixture is feasible — confirm `isMountedRef`
  in `VoiceLibraryPage.tsx`).
- *Prosody:* `scenarioAlignmentCompare` (build now — UI review, not a demo);
  `scenarioAlignmentCompareGif` (**hold** until the trough-biased safe-cut fix lands — current
  alignment makes a poor GIF).
- *Stitch Studio:* `scenarioSegmentLibraryBrowse`, `scenarioStitchAssembly`.
- *Accent Design / OmniVoice:* `scenarioOmniVoiceAudition` (`omnivoice-result` exists),
  `scenarioOmniVoiceAuditionGif` (~3s live), `scenarioPersonaForgeCandidates` (only if a
  multi-candidate grid renders — confirm first), `scenarioAccentProjectGrouping`.
- *Wizard GIF (highest value):* `scenarioDesignToStitchWizardGif` — pick text → instruct/accent →
  OmniVoice generate → lock as segment → stitch into a voice; single continuous GIF.

**Invariants:** real waits only; each scenario standalone; registered in `--list-scenarios`; never
weaken the fake tier.

**Gate (per scenario):**
```bash
node tests/ui/capture.mjs --real --scenario <name>                 # [escalate→device] produces artifact
ls -la docs/screenshots/artifacts/<feature>/                       # [local-verifiable] non-zero
node tests/ui/capture.mjs --list-scenarios | grep <name>           # [local-verifiable] registered
```
Which scenarios are worth building / whether a described feature exists is `[escalate→frontier]`
only where judgment is needed; the rest is device/local.

**Completion proof (phase):** `--list-scenarios` spans Voice Library, Prosody, Stitch Studio,
Accent Design/OmniVoice, GIFs (minus deferred `scenarioAlignmentCompareGif`).

### Phase B7 — Coverage doc + operator workflow

**Mission:** make the tool discoverable — a coverage list + a proven point-and-shoot loop.

**Preconditions** `[local-verifiable]`: `node tests/ui/capture.mjs --list-scenarios` returns the
categorized catalog.

**Do this:** add `tests/ui/README.md` listing every scenario (one line each, categorized, mirroring
llama-monitor's `printUsage()`); document the loop: change frontend → `npm run build` → `node
tests/ui/capture.mjs --real --scenario <name>` → inspect `docs/screenshots/artifacts/<feature>/`.

**Gate:** `test -f tests/ui/README.md && echo "readme OK"` `[local-verifiable]`; then a **dry run**
`[escalate→device]`: make a trivial visual tweak, rebuild, re-capture the covering scenario,
confirm the screenshot reflects it, `git checkout -- <file>`.

**Completion proof:** README coverage list; dry-run screenshot showed the tweak.

**B risks:** gated model downloads (B1's readiness error must surface `_startup_error`);
first-run latency (minutes cold — timeouts generous/configurable); never weaken the fake/CI tier;
never commit real personal data (diff `capture-data/` before commit).

---

## 8. Initiative C — guided experience / teaching layer

> Frontend-heavy; independent of A/B. Content/copy decisions are `[decide-once]` (D8); build/wiring
> is `[local-verifiable]`; visual acceptance is `[escalate→device]`. Global invariants: never
> unmount power-user controls (D7); one shared mechanism per concern; centralized terminology;
> copy in data/markdown; `npm run build` passes each phase.

### Phase C1 — Contextual tooltips & plain-language metric surfacing

**Mission:** surface already-computed metrics in plain language at the point of decision, via one
shared content map + a reusable `(?)` explainer. Cheapest slice; good first pickup.

**Preconditions** `[local-verifiable]`:
```bash
grep -n "speech_rate_proxy\|pause_ratio\|median_pause_ms" src/qwen3_tts/audio_style.py
test -f frontend/src/components/OmniVoice/SegmentRackRow.tsx && echo "segmentrack OK"
```

**Read first:** `src/qwen3_tts/audio_style.py` `analyze_reference()` (~line 83, the metric keys);
`SegmentRackRow.tsx` (existing pacing warning + regen cost — extend, don't replace);
`frontend/src/lib/accentBank.ts` `FEATURE_INFO` (shape to imitate).

**Do this:**
1. Create `frontend/src/lib/metricExplainers.ts` exporting
   `METRIC_EXPLAINERS: Record<string, { label; plain; termId? }>` keyed by metric key. `plain` =
   1–2 plain sentences (the **copy is `[decide-once]`**). `termId` forward-links to a C3 glossary
   entry (harmless if C3 not built).
2. Create `frontend/src/components/MetricExplainer.tsx` (or `useMetricExplainer` hook) rendering a
   `(?)` affordance that opens the plain text. One component, not per-call-site chrome.
3. Wire it into the **existing** warning/estimate surfaces in `SegmentRackRow.tsx`.

**Invariants:** one content map, one explainer; no per-component tooltip reimpl; don't change
backend metrics; copy in the data file.

**Gate:**
```bash
cd /Users/nick/SCRIPTS/CLAUDE/qwen3-tts-openvino/frontend && npm run build                       # [local-verifiable]
test -f ../frontend/src/lib/metricExplainers.ts 2>/dev/null || test -f src/lib/metricExplainers.ts && echo "map OK"   # [local-verifiable]
grep -rn "MetricExplainer\|useMetricExplainer" src/components/OmniVoice/SegmentRackRow.tsx        # [local-verifiable]
```
Tooltip reads clearly at the point of decision = `[escalate→device]` (visual).

**Completion proof:** content-map keys; explainer name; wiring; build pass; a screenshot/description.

### Phase C2 — Progressive disclosure mode (Basic / Expert)

**Mission:** one shared, persisted mechanism to hide/show advanced controls consistently. Never a
per-panel simplification (D7).

**Preconditions** `[local-verifiable]`:
```bash
grep -n "loadStoredTheme\|applyTheme" frontend/src/store.ts
test -f frontend/src/components/AppShell.tsx && echo "appshell OK"
```

**Read first:** `store.ts` (zustand `create`, theme persistence via `lib/theme.ts`); `lib/theme.ts`
(the localStorage helper pattern to copy); `AppShell.tsx` (toggle location).

**Do this:**
1. Add `uiExperienceLevel: 'guided' | 'expert'` to the store, persisted via the **same helper
   pattern** as `theme` (new small lib mirroring `lib/theme.ts`); default `'guided'`.
2. Toggle in `AppShell.tsx`; persist on change.
3. One shared `<Disclose level="expert">` wrapper (or `useExperienceLevel()` hook): guided mode
   **collapses/hides behind "Show advanced," never unmounts** (D7); expert renders inline. The
   disclosure boundary (which controls are "advanced") is `[decide-once]`.
4. Wrap advanced controls in Voice Design + OmniVoice first (Stitch Studio / Accent Workbench
   follow the same seam). No second mechanism.

**Invariants:** one disclosure mechanism; never unmount (D7); setting persists; power users reach
everything in one click.

**Gate:**
```bash
cd /Users/nick/SCRIPTS/CLAUDE/qwen3-tts-openvino/frontend && npm run build   # [local-verifiable]
grep -n "uiExperienceLevel" src/store.ts                                     # [local-verifiable]
grep -rn "Disclose\|useExperienceLevel" src/components/ | head               # [local-verifiable] single seam
```
Toggle/persist/never-unmount behavior verified in-browser = `[escalate→device]`.

**Completion proof:** store field + persistence helper; `<Disclose>` name + panels; build; the
never-unmount + persistence confirmation.

### Phase C3 — In-app glossary + troubleshooting KB

**Mission:** a searchable in-app reference (glossary + troubleshooting) markdown-driven and
deep-linkable, so C1 tooltips and C4 chips link into it instead of re-explaining inline.

**Preconditions** `[local-verifiable]`: `grep -n "FEATURE_INFO" frontend/src/lib/accentBank.ts`
(the content-model precedent). C1's `metricExplainers.ts` ideally present (its `termId`s are the
glossary keys).

**Read first:** `accentBank.ts` `FEATURE_INFO`; `metricExplainers.ts` (C1) `termId` fields;
roadmap §7.1 command-palette note (optional) — `⌘K → "Help: <topic>"` entry point.

**Do this:**
1. Content as markdown, e.g. `frontend/src/content/help/*.md` — one file per glossary term / per
   troubleshooting entry, each with a stable term-ID (frontmatter or filename). **Copy is
   `[decide-once]`.**
2. Render in a slide-over panel reachable anywhere (help button in `AppShell.tsx`, ideally the
   `⌘K` palette); search/filter over titles.
3. Deep-linkable by term-ID (C1 tooltip → glossary entry; C4 chip → troubleshooting entry).
4. Seed the minimum set: terms referenced by C1's map + the four troubleshooting entries
   (clipping, robotic cadence, accent drift, stitching artifacts).

**Invariants:** markdown content (reviewable); one term-ID scheme shared with C1/C4; a term defined
once.

**Gate:**
```bash
cd /Users/nick/SCRIPTS/CLAUDE/qwen3-tts-openvino/frontend && npm run build   # [local-verifiable]
ls src/content/help/*.md                                                     # [local-verifiable]
```
Panel opens, search works, a C1 deep-link lands on the entry = `[escalate→device]`.

**Completion proof:** term-ID scheme; entries created; how the panel opens; deep-link demo; build.

### Phase C4 — Automated take diagnostics

**Mission:** detect known failure signatures from already-computed metrics and surface inline,
actionable chips at the point of failure, each linking to a C3 KB entry.

**Preconditions** `[local-verifiable]`: `grep -n "def analyze_reference" src/qwen3_tts/audio_style.py`;
`ls frontend/src/content/help/*.md` (C3 link targets).

**Read first:** `audio_style.py` `analyze_reference()` (metric keys to threshold); the
`/omnivoice/audition` + generation route response shape in `app.py` (where `Diagnosis[]` attaches);
C3 term-ID scheme.

**Do this:**
1. Backend `diagnose_take(metrics, audio_stats) -> list[Diagnosis]` (in `audio_style.py` or new
   `audio_diagnostics.py`): flag clipping (peak/RMS), unnatural pacing (`speech_rate_proxy`),
   long dead-air (`longest_pause_ms`), excessive pauses (`pause_count`), optional accent-coverage
   gaps. `Diagnosis = { id, severity, message, kbEntryId }`. **Thresholds are `[decide-once]`,
   kept as documented constants in one place.**
2. Attach `Diagnosis[]` to audition/generation responses.
3. Render inline chips near the affected take, each linking to its C3 entry; reuse existing chip
   styling.

**Invariants:** derive only from already-computed metrics (no new heavy analysis); each chip links
a real C3 term-ID; thresholds in one place.

**Gate:**
```bash
cd /Users/nick/SCRIPTS/CLAUDE/qwen3-tts-openvino
PYTHONPATH=src:. uv run pytest tests/ -q -k "diagnos or audio_style" 2>&1 | tail -20   # [local-verifiable] add a diagnose_take unit test
cd frontend && npm run build                                                           # [local-verifiable]
```
A known-bad take surfaces the right chip + link in-browser = `[escalate→device]`.

**Completion proof:** `diagnose_take` location + patterns + thresholds; attach point; chip UI;
unit-test result; build.

### Phase C5 — Guided persona-creation wizard

**Mission:** a goal-oriented on-ramp that maps a few plain answers to a starting config and lands
the user in the **existing expert surfaces** with sane defaults — never a parallel engine, never a
dead end.

**Preconditions** `[local-verifiable]`:
```bash
grep -n "uiExperienceLevel\|Disclose" frontend/src/store.ts frontend/src/components/*.tsx 2>/dev/null | head   # C2 seam exists
```
C2 must be green (clean hand-off into the disclosure-managed expert surface).

**Read first:** `store.ts` (`Page` union + navigation, to route into voice-design/OmniVoice with
pre-filled config); the Accent Workbench Route A/B/C logic (roadmap §4.1 — reuse, don't
duplicate); `OmniVoicePanel.tsx` / the Voice Design panel (target config shape).

**Do this:**
1. New on-ramp — `frontend/src/pages/PersonaWizardPage.tsx` or a modal sequence — a handful of
   plain questions (use case, target accent/region, energy/formality). **Question set + copy are
   `[decide-once]`.**
2. Map answers → a starting Voice Design / OmniVoice config, then **navigate into the existing
   expert panel** with defaults applied. No parallel generator.
3. Accent step routes **through** the existing Route A/B/C logic (reuse).
4. "Skip wizard, go to full editor" one click away at **every** step.

**Invariants:** on-ramp not replacement (always hands off to the real surface); reuse Route A/B/C;
skip-to-editor always present; no duplicated generation logic.

**Gate:**
```bash
cd /Users/nick/SCRIPTS/CLAUDE/qwen3-tts-openvino/frontend && npm run build   # [local-verifiable]
test -f src/pages/PersonaWizardPage.tsx && echo "wizard OK"                   # [local-verifiable] (or the modal component)
```
End-to-end run lands in the real panel with defaults + all advanced controls present (collapsed
per C2), skip works at each step = `[escalate→device]`.

**Completion proof:** entry point; question→config mapping; hand-off; skip confirmation; build.

---

## 9. Completion ledger (mirror in the companion; update as phases verify)

| Phase | State | Verified by | Evidence |
|---|---|---|---|
| A1 | verified | agent (local) | `uv.lock` + `[tool.uv]` env markers + D14 extra wiring; 343/343 tier1 green |
| A2 | verified | agent (local) | `uv run` imports succeed; pytest subset green |
| A3 | verified | agent (local) | setup doc references `uv sync`; no CI/requirements-dev diff |
| A4 | verified | agent (local) | `resolve_device()` in `device.py`; auto-default + env override; OV seam wired |
| A4b | verified | agent (local) | `has_valid_export()` in `presets.py`; no-export→pytorch, explicit `TTS_BACKEND` wins |
| A5 | verified | agent (local) | dev doc matrix + deferred-path map (`docs/ENV_REFERENCE.md`) |
| A6 (findings/design) | validated | user (plexxie) | RTF 5.26 xpu vs 12.74 cpu; audio/omni_*.wav |
| A6a | verified | agent (local) + plexxie | `device.py` fp64-emu helpers; plexxie generated without manual export |
| A6b | verified | user (plexxie) | A6.3 OMP=4 CPU RTF + honest ratio recorded |
| A6c | verified | agent (local) + plexxie | `gpu_family.py`; unit table green (14/14); plexxie detected intel-xpu |
| A6d | verified | agent (local) | `scripts/entrypoint.sh` resolves family via `resolve_gpu_family()`, exports per-family env |
| A6e | verified | agent (local) | entrypoint first-boot torch install into named volume, marker-gated |
| A6f | verified | agent (local) | `compose.yml` `/dev/dri` + `GPU_FAMILY` example; A5 matrix reconciled |
| A6g | deferred | | int8 PTQ exploration explicitly deferred, not pursued |
| A7a | verified | agent (local) | `runtime_store.py`; round-trip/corrupt-ignore/lock/no-persist-on-failure units green |
| A7b | verified | agent (local) | `live_metadata`/`restart_required`/`preview_runtime_config`/`reset_runtime_config`; 3x full-suite green (510 passed); `tsc --noEmit` clean |
| A7c | verified | agent (local) | `describe_accelerator()` `detected_family` fix; `AcceleratorCoachCard`; build + Puppeteer screenshot, no console errors |
| A7d | verified | agent (local) | per-key badges/lock-disable, accelerator panel, Expert disclosure (never-unmount); build + Puppeteer screenshots (Basic/Expert), no console errors |
| B1 | not started | | |
| B2 | not started | | |
| B3 | not started | | |
| B4 | not started | | |
| B5 | not started | | |
| B6 | not started | | |
| B7 | not started | | |
| C1 | not started | | |
| C2 | not started | | |
| C3 | not started | | |
| C4 | not started | | |
| C5 | not started | | |
