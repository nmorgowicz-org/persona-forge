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
- **D10 — OmniVoice on the Intel iGPU IS an in-scope goal (Persona Forge accent design), but via
  torch-xpu, not OpenVINO — investigation deferred to a future session (quota).** User's actual
  target: run **OmniVoice accent design on the Iris Xe iGPU** (base cloning is fine on pocket-tts /
  CPU). Two routes:
  - **OpenVINO conversion of OmniVoice — rejected as the path.** IR conversion is per-architecture;
    the Qwen3-TTS OpenVINO work is **not reusable**, and OmniVoice's flow-matching/diffusion design
    would be a Stable-Diffusion-pipeline-scale port (multiple submodels + a Python sampling loop).
  - **torch-xpu / Intel Extension for PyTorch — the promising path.** Keeps the OmniVoice model
    as-is and moves it to `device="xpu"` (the A4 `TTS_DEVICE=xpu` seam). Far less work than a port.
    **Open questions to resolve next session (all `[escalate→device]`, need the real iGPU):** (1) does
    Iris Xe support the ops OmniVoice calls under IPEX/xpu, and at what dtype; (2) can an xpu torch
    wheel resolve past OmniVoice's cu128 git-source (same install-layer problem as D9 → the
    OmniVoice-source escape hatch, or an `xpu` extra); (3) perf vs CPU on this iGPU. plexxie already
    has `intel-opencl-icd` + `intel-level-zero-gpu` + `/dev/dri`; a temporary iGPU LXC (or plexxie)
    can host the validation.
  - Separately, the Qwen3-TTS `openvino` backend + `OPENVINO_DEVICE=GPU` (A4) remains the *easy*
    iGPU win for the base model, and pre-shipping the Qwen3-TTS IRs would fix the "export was too
    hard" pain. (§6 A4/A5) **← resume here next session.**

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
- Line hints drift. Prefer the named function/heading over the number; re-grep if a hint looks
  stale (e.g. `grep -n "def analyze_reference" src/qwen3_tts/audio_style.py`).
- Before relying on a route list, testid count, or schema, re-verify it against the live source
  (the facts in §2 were true 2026-07-20).
- `npm run build` in `frontend/` must pass at the end of every frontend-touching phase.

## 5. Dependency & sequencing index

| Phase | Initiative | Deliverable (one line) | Depends on |
|---|---|---|---|
| A1 | uv | `pyproject.toml` + uv sources/overrides authored from existing manifests | — |
| A2 | uv | `uv sync` reproduces a working real-model venv; tests green | A1 |
| A3 | uv | dev docs updated; B1 precondition rewired to `uv sync`; CI untouched | A2 |
| A4 | uv | runtime device seams: `TTS_DEVICE` (torch) + `OPENVINO_DEVICE` (iGPU), auto-detect+force | A2 |
| A5 | uv | accelerator install guide (docs) + deferred slim/ROCm/XPU + iGPU-via-OpenVINO note | A2 |
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
| Intel iGPU | `uv sync` + `TTS_BACKEND=openvino` + `OPENVINO_DEVICE=GPU` (A4) | Qwen3-TTS on the iGPU; needs `intel-opencl-icd` + `intel-level-zero-gpu` + `/dev/dri` passthrough. **Qwen3-TTS backend only; OmniVoice stays CPU (D10)** |

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
| A1 | not started | | |
| A2 | not started | | |
| A3 | not started | | |
| A4 | not started | | |
| A5 | not started | | |
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
