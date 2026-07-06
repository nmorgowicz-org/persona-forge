# COMPLETED (infrastructure implemented; CI integration pending): E2E and Screenshotting for qwen3-tts-openvino

> Audience: a fresh AI agent with zero prior context. This doc fully specifies how to set up
> E2E tests, visual captures, and artifact workflows for this project. Do not silently relax
> constraints or stack choices without proposing alternatives explicitly.

## 0. Orientation

This is qwen3-tts-openvino:
- CPU-only Docker image (Linux AMD64).
- Flask + Gunicorn, single worker, single model in memory, port 8318.
- OpenVINO-accelerated Qwen3-TTS; PyTorch for glue and rollback.
- Optional web frontend served from same Flask process (FRONTEND_ENABLED).

We already have:
- Unit/integration tests in tests/ (no model weights). Notably, `tests/test_app_api.py`
  substitutes a fake `qwen3_tts.model` module (via `sys.modules`) before importing
  `qwen3_tts.app`, so the real Flask app object runs with no model loaded and instant fake
  responses. This is the pattern §3 below reuses for E2E.
- Two CI workflows: `ci.yml` (`validate` job, `arc-general` runner, no Docker — lint + unit
  tests, runs on every PR) and `image.yml` (`build` job, `arc-general-docker` runner, gated by
  the `ready-to-test` PR label, `linux/amd64` only — builds and smoke-tests the container
  image). Path filtering in this repo is done with the workflow's native
  `on.pull_request.paths:` key (see `image.yml` lines 3-13). **This repo does not use
  `dorny/paths-filter`; do not introduce it.**
- A similar stack in ../llama-monitor that uses:
  - Playwright for E2E.
  - Puppeteer + capture.mjs for screenshots/GIFs.

We have adopted a comparable, but adapted, approach here. This doc:
- Reuses proven patterns from llama-monitor.
- Adapts them to:
  - A containerized Python/Flask service.
  - A VoiceDesign-heavy UI.
  - Our existing CI constraints (no heavy Docker-in-Docker; limited RAM).
  - The fact that local dev is on macOS Apple Silicon, but the container is Linux AMD64 only.

If anything conflicts with AGENTS.md or docs/dev/architecture/voice_design.md, treat this as additive unless explicitly contradicted.

## 1. Goals

- Provide:
  - A reliable, maintainable E2E test suite (Playwright) that:
    - Validates the frontend and critical API flows.
    - Runs quickly in CI, only when relevant changes occur.
    - Uses a mock profile (no real model) by default.
  - A visual capture system (Puppeteer) that:
    - Generates structured screenshots and optional GIFs for:
      - Local UI/UX review.
      - Selective promotion into docs/screenshots for README and reference.
- Constraints:
  - No changes to the backend architecture.
  - No extra services beyond what is required.
  - Fully documented so any AI agent can implement or extend without guessing.

## 2. Stack and structure

- E2E tests:
  - Tool: Playwright (Chromium only).
  - Location: tests/ui/ (sibling to src/, scripts/, frontend/).
  - Minimal package.json dedicated to Playwright and helpers.
- Screenshot/GIF capture:
  - Tool: Puppeteer (same tests/ui/ directory).
  - Central harness: tests/ui/capture.mjs.
  - Scenarios defined in capture.mjs and possibly scenario helpers.
- Artifacts:
  - docs/screenshots/
    - Approved, curated screenshots used in README/docs.
  - docs/screenshots/artifacts/
    - Auto-captured screenshots/GIFs; gitignored; subject to manual curation.

If you introduce any new tooling, it must:
- Be installable via npm inside tests/ui/.
- Not impact the Python stack, Docker image, or backend runtime.

## 3. Environment, runtime, and the fake-model test server

**CI, and routine local E2E/capture work, cannot run the real model.** Real weights are
multiple GiB (gated by an HF token), real inference needs real CPU time, and nothing in this
repo's existing CI ever loads real weights today — `image.yml`'s smoke test only imports modules
and asserts config resolution, it never runs generation (see `image.yml` line 118). E2E tests
follow the same rule.

### 3.1 Fake-model test server (required, no production code changes)

Rather than adding a mock mode to `qwen3_tts/app.py` or `model.py` (an env-var-gated branch in
production code that must never accidentally activate in a real deployment), reuse the pattern
`tests/test_app_api.py` already uses and has already been reviewed: **substitute a fake
`qwen3_tts.model` module via `sys.modules` before importing `qwen3_tts.app`**, then run the real
Flask app object as a real HTTP server. No request-level mocking happens in the browser or in
Playwright — every request is real HTTP against a real Flask process; only the model layer
underneath it is fake. This means:

- Zero changes to `app.py` or `model.py`. No new env var, no new code path that could leak into
  production.
- No model weights loaded, no OpenVINO, no heavy memory use — this can run as a plain Python
  process anywhere, including natively on an arm64 Mac (no Docker, no `linux/amd64` constraint).
- Fast and deterministic: fake responses return instantly.

`tests/ui/fixtures/fake_model_server.py`:

- Registers a fake module at `sys.modules["qwen3_tts.model"]` exposing `model`,
  `voice_clone_prompt`, a real `ThreadPoolExecutor(max_workers=1)` (so swap/generate calls still
  serialize realistically), `health_state()`, `_run_generate`, `_run_generate_with_streaming`,
  and `_apply_optional_seed` — same shape as the fake used in `tests/test_app_api.py` — all
  returning small deterministic fake audio (e.g. silence or a sine tone) with no delay.
- Also fakes whatever `qwen3_tts.voice_design`/`qwen3_tts.voice_library` need so
  `POST /voice_design` returns a synthetic `voice_id` instantly, using a temp directory instead
  of a real `VOICE_LIBRARY_DIR` so runs don't depend on or pollute real state.
- After the fakes are installed, imports `qwen3_tts.app` and runs it with Flask's built-in dev
  server (Gunicorn's `-w 1`/`--preload` constraints are a real-deployment concern, not relevant
  to a single-process test double).
- Reads `FRONTEND_DIST_DIR` the same way the real app does — point it at `frontend/dist` after
  `vite build`; leave `FRONTEND_ENABLED` at its default.
- Listens on `QWEN3_TTS_TEST_PORT` (default `8319` — deliberately different from the real
  service's `8318` so this can coexist with a real instance if one happens to be running), and
  prints a ready marker once `/health` would return 200.

This is what both Playwright (`webServer` block, §4.3) and `capture.mjs` (default mode, §5) run
against day to day, on any machine, with no dockermisc1 involvement at all.

### 3.2 What still needs dockermisc1

Real-model behavior (real audio, a real multi-second swap-in-progress state, real waveform
capture) is validated separately and only on dockermisc1 — see §7. Routine E2E/UI work never
needs it.

## 4. E2E test design (Playwright)

### 4.1 Scope

Implemented:
- Basic health and startup:
  - /health endpoint returns 200.
  - Frontend page loads; essential UI elements present.
- Core generation:
  - Enter text → Generate → verify:
    - Request is sent.
    - Audio playback element appears.
    - No UI-level error.
- VoiceDesign panel:
  - Preset selection.
  - Chip interactions.
  - Generate & save voice → success/feedback.
- Voice library:
  - List voices.
  - Select a voice → Generate.
- Error flows:
  - Empty text → button disabled.
  - Model busy / swap-in-progress → graceful UX (no silent crash).

### 4.2 Playwright configuration

tests/ui/playwright.config.js:

Requirements:
- Browser: chromium only.
- Parallelism:
  - fullyParallel: false.
  - workers: 1 in CI (sequential to avoid port/instance races).
- Timeouts:
  - Slightly higher than default (e.g., 20–30s).
- Reports:
  - screenshot: "only-on-failure".
  - trace: "on-first-retry".
  - Use HTML reporter on failure only.
- baseURL:
  - From:
    - QWEN3_TTS_UI_URL (explicit, for pointing at a real instance per §7), or
    - 127.0.0.1:8319 as fallback (the fake-server test port from §3.1, not the real
      service's 8318).
- Integration:
  - Use the `webServer` block, pointed at `run-server.mjs` (see 4.3).

### 4.3 How to run the service for E2E

tests/ui/run-server.mjs:
- Responsibilities:
  - Spawn `fixtures/fake_model_server.py` (§3.1) as a child process, with `PYTHONPATH=src` set.
  - Wait until `/health` returns 200.
  - Cleanly shut down (SIGTERM the child) on exit/signal.
- Must:
  - Log PID/port.
  - Never hardcode secrets (none are needed — the fake server doesn't touch any real
    credentials or model repo).

CI runs `npm run test:ci` in `tests/ui/` with no `QWEN3_TTS_UI_URL` set — Playwright's
`webServer` block spawns `run-server.mjs` itself and tears it down after the run. No Docker
image is built or pulled for this job at all (see §6).

### 4.4 Directory and test organization

Under tests/ui/:

- package.json:
  - Scripts:
    - "test": "playwright test"
    - "test:ci": "playwright test --reporter=list --workers=1 --retries=2"
- Directories:
  - tests/ui/core/
    - basic.spec.js: health, initial load, critical UI elements.
  - tests/ui/generate/
    - generate.spec.js: basic generation, error handling.
  - tests/ui/voice-design/
    - voice-design.spec.js: VoiceDesign panel interactions.
  - tests/ui/voice-library/
    - voices.spec.js: listing and selecting voices.
  - tests/ui/performance/
    - performance.spec.js: simple load-time / bundle checks.

Rules:
- Prefer stable selectors (data-testid where possible; semantic structure where not).
- Do not deeply introspect internal JS modules like llama-monitor's tests sometimes do.
- Tests should be understandable and resilient to internal refactors.

## 5. Visual capture and screenshots (Puppeteer)

### 5.1 Goals

Provide a scenario-driven harness to capture:
- Baseline screenshots for:
  - UI layout.
  - VoiceDesign panel.
  - Generation UI with audio.
- Optional GIFs for:
  - Short interaction sequences.
- Output:
  - docs/screenshots/artifacts/ (auto, gitignored).
  - Selected images promoted to docs/screenshots/ (committed) for README/docs.

### 5.2 Core design (capture.mjs)

tests/ui/capture.mjs:

Patterns (from llama-monitor, adapted):
- Uses Puppeteer to:
  - By default, spawn the same fake-model server as Playwright (§3.1) via `run-server.mjs`, on
    `SCREENSHOT_PORT` (default `8892`, kept distinct from both the real service's 8318 and the
    Playwright test port 8319 so all three can run concurrently without colliding).
  - Optionally target a different, already-running instance instead via `--target <url>` — this
    is how §7's real-model capture against dockermisc1 is invoked.
  - Navigate and interact deterministically.
- Scenarios:
  - Defined as named functions in a SCENARIOS map.
  - Each scenario:
    - Performs a fixed sequence of interactions.
    - Takes screenshots and/or frames into docs/screenshots/artifacts/.
- Invocation:
  - node tests/ui/capture.mjs --scenario <name>
  - Flags:
    - --list-scenarios
    - --no-attach
    - (Optional: --close-up, --inference-only if relevant)

Mandatory:
- Must run scenarios sequentially, not in parallel.
- Must never embed secrets or model weights into artifacts.

### 5.3 Example scenarios

Include:
- scenarioHealth:
  - Open /health; confirm status; screenshot.
- scenarioHome:
  - Load main UI; wait for modules-ready; screenshot overall layout.
- scenarioGenerate:
  - Enter short text; Generate; wait for audio element; screenshot.
- scenarioVoiceDesignPanel:
  - Open VoiceDesign panel; select preset; screenshot chips.
- scenarioVoiceDesignGenerate:
  - Generate & save voice; capture success state.
- scenarioVoicesList:
  - Show voices list; screenshot.
- scenarioMotionStates (future):
  - Capture swap-in-progress or loading states (with controlled interactions).

Each scenario:
- Uses deterministic steps.
- Avoids randomization and time-dependent text in UI.

### 5.4 Promotion workflow

Artifacts flow:
- Auto: docs/screenshots/artifacts/* is gitignored.
- Human:
  - Pick best images.
  - Copy to docs/screenshots/<feature>/<filename>.
  - Optionally update README.md, HOW_TO_RUN.md, or docs with those images.
- Rule:
  - Never commit all artifacts.
  - Only commit curated, high-quality images explicitly chosen by the operator.

## 6. CI integration

### 6.1 General constraints

- Because this job runs the fake-model server (§3.1) — pure Python, no weights, no Docker — it
  is cheap and fast, unlike the real `image.yml` build. It does not need the `ready-to-test`
  label gate or the `arc-general-docker` runner that gate exists for; it can simply run on every
  relevant PR the same way `ci.yml`'s existing `validate` job does.
- Keep it deterministic and fast; no real model in CI, ever.

### 6.2 Workflow shape (not yet implemented)

The CI workflow for E2E has NOT been created yet. The intended design is documented here for
reference; a later change will implement it.

GitHub Actions path filters are per-workflow-file (the `on.pull_request.paths:` key), not
per-job — so this cannot just be a new job bolted onto `ci.yml` without either affecting
`validate`'s trigger (which currently runs on every PR, unfiltered) or duplicating the filter
per-job with a manual diffing step. It should follow the same pattern `image.yml` already uses
for exactly this reason: **a separate workflow file**, e.g. `.github/workflows/ci-ui.yml`, with
its own path filter:

```yaml
on:
  pull_request:
    paths:
      - frontend/**
      - tests/ui/**
      - src/qwen3_tts/**
  workflow_dispatch:
```

Job:
- `runs-on: arc-general` (no Docker involved).
- Steps: checkout; `actions/setup-python` (3.13) + `actions/setup-node` (24), matching the
  versions pinned in `ci.yml`; `pip install -r requirements-dev.txt`; `npm ci` in `frontend/`
  and `tests/ui/`; `npm run build` in `frontend/` (produces `dist/` for the fake server to
  serve); cache `~/.cache/ms-playwright`; `npm run test:ci` in `tests/ui/` (no
  `QWEN3_TTS_UI_URL` needed — Playwright's `webServer` block spawns `run-server.mjs`, which
  spawns the fake-model server, itself).
- On failure: upload the Playwright HTML report as a short-retention artifact (e.g. 1 day).

Screenshots:
- `capture.mjs` runs locally only, never in CI.
- Playwright's own auto-screenshots (on failure only) are CI artifacts, never committed to the
  repo.

## 7. Real-model E2E and screenshots on dockermisc1 (manual only)

Not a CI gate, not part of routine local dev — this is a deliberate, occasional, manual tier for
when someone actually wants to see/hear real generation (real audio, a real multi-second
swap-in-progress state, a real waveform) rather than the fake server's instant silent responses.

Constraint: the container is `linux/amd64` only; a Mac dev box (this project's dev box is
Apple Silicon / arm64) cannot run it at usable speed even under emulation. dockermisc1
(`x86_64`) is the only place the real model runs.

Procedure:
1. On dockermisc1: confirm the `qwen3-tts` container is up (`docker compose up -d qwen3-tts`
   from the repo checkout there); confirm nothing else heavy (export, a second model) is running
   at the same time — RAM is limited (`docs/agent-reference/RUNTIME_AND_MEMORY.md`).
2. From the Mac, open an SSH tunnel to it:
   ```
   ssh -L 8318:127.0.0.1:8318 <user>@dockermisc1 -N -f
   ```
3. Run Playwright against it directly (`QWEN3_TTS_UI_URL=http://127.0.0.1:8318 npm run test
   --workspace tests/ui`, bypassing the fake-server `webServer` block), or run
   `capture.mjs --target http://127.0.0.1:8318` for real-audio screenshots/GIFs.
4. Afterward: close the tunnel; stop the dockermisc1 container again if it isn't otherwise
   needed for other work, per this host's shared-use conventions (don't leave scoped test
   containers running, don't touch other services on that host).

Never run export and serving concurrently on dockermisc1 (memory), and never leave the real
service down longer than the task needs.

## 8. Git, artifacts, and .gitignore

Status: partially implemented; needs a final .gitignore pass.

Intended entries (confirm or add as needed):
- docs/screenshots/artifacts/
- tests/ui/playwright-report/
- Any large logs or generated data.

In repo:
- docs/screenshots/ contains only approved, curated images.

Note: ensure these exclusions are present; treat this as pending if not yet verified in the
current .gitignore.

This aligns with the existing project philosophy:
- Keep Git lightweight.
- Keep docs/screenshots/ as the canonical "showcase" set.
- Use artifacts/ as the raw staging area.

## 9. Implementation checklist (for agents)

Use this as a pass/fail checklist when validating E2E and screenshotting. Completed items are
checked; incomplete items are flagged.

- [x] Fake-model test server (§3.1), no production code changes:
  - [x] `tests/ui/fixtures/fake_model_server.py` substitutes `sys.modules["qwen3_tts.model"]`
        before importing `qwen3_tts.app` (same pattern as `tests/test_app_api.py`).
  - [x] Serves the built frontend (`FRONTEND_DIST_DIR` pointed at `frontend/dist`).
  - [x] /health returns 200.
  - [x] /generate, /voice_design, /voices return deterministic fake responses instantly.
  - [x] No real model loaded; runs as a plain Python process, no Docker required.

- [x] tests/ui/ created:
  - [x] package.json with Playwright and Puppeteer.
  - [x] playwright.config.js with chromium-only, sequential workers, timeouts, reports.
  - [x] run-server.mjs to start/stop the fake-model server for tests.
  - [x] Organized tests:
    - [x] core/basic.spec.js (health, load).
    - [x] generate/generate.spec.js (generation flow, basic errors).
    - [x] voice-design/voice-design.spec.js (panel + generate).
    - [x] voice-library/voices.spec.js (list/select).
    - [x] performance/performance.spec.js (optional, basic checks).

- [x] Screenshot harness:
  - [x] tests/ui/capture.mjs with scenario-driven design.
  - [x] Deterministic scenarios (health, home, generate, VoiceDesign, voices).
  - [ ] docs/screenshots/artifacts/ is populated and reliably gitignored (pending confirmation).

- [ ] CI integration (INCOMPLETE — not yet wired into GitHub Actions):
  - [ ] `.github/workflows/ci-ui.yml` (separate file, own path filter — no
        `dorny/paths-filter`), `runs-on: arc-general`, no Docker.
    - [ ] Path filter: frontend/**, tests/ui/**, src/qwen3_tts/**.
    - [ ] Builds frontend, starts the fake-model server via Playwright's `webServer`, runs
          Playwright.
    - [ ] On failure: uploads playwright-report as artifact (short retention).
  - [x] Screenshots (capture.mjs) remain local-only (by design, not in CI).

- [x] Manual dockermisc1 procedure (§7) documented:
  - [x] SSH tunnel command.
  - [x] Running Playwright/capture.mjs against the real instance via `--target`/`QWEN3_TTS_UI_URL`.
  - [x] Teardown (stop container, close tunnel).

- [x] General:
  - [x] No backend or Docker image changes beyond what's needed for tests.
  - [x] No new auth/multi-tenancy introduced.
  - [x] All scripts are documented and self-contained for future agents.
