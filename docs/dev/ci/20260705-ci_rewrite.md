# CI Rewrite — Scorch-Earth Plan (IMPLEMENTED)

Date: 2026-07-05 → 2026-07-06
Branch: ci-rewrite-scorch-earth
Status: implemented; this doc moved to docs/dev/ci/ as reference.
PR: #104

This is a self-contained specification for completely rewriting the repository's
test suite and CI configuration. A future AI agent must be able to execute this
plan using only this document, the current codebase, and the AGENTS.md rules.

No external conversation history is required.

If you cannot execute a step because of ambiguity, propose a minimal alternative
in this document before changing behavior.

## 1. Goals

- Build a fast, reliable, regression-focused test suite and CI that:
  - Catches real bugs in API contracts, backend logic, and UI flows.
  - Never loads real models, OpenVINO IR, or Docker in CI.
  - Is easy to extend for new features.
- Eliminate duplication, fragility, and inconsistency across:
  - Multiple hand-rolled fake model modules.
  - unittest vs pytest mixing.
  - 700-line monolithic test files.
  - Busy-wait polling loops in async-job tests.
- Provide a clear tier structure:
  - Tier 1: pure unit (no app, no heavy mocking).
  - Tier 2: backend (Flask + model layer, fake internals).
  - Tier 3: API integration (black-box, fake server).
  - UI E2E: Playwright (fake, fake-but-realistic).

All tests must be executable on:
- Python 3.13
- A small dev dependency set (Flask, pytest, numpy, soundfile, etc.)
- No GPU, no OpenVINO runtime, no HF weights, no Docker.

## 2. Non-Goals

These are explicitly NOT part of this plan:

- Introducing real-model tests into CI (Tier 3/4 parity, latency, RSS).
  - Those remain manual on docker-agent.
- Changing the production behavior of model.py, app.py, OpenVINO adapters.
  - We adapt tests to reality, not reality to tests.
- Modifying frontend behavior or APIs.
  - We are wiring tests to the existing architecture.

## 3. Constraints

Derived from AGENTS.md and codebase:

- One image, one process. Gunicorn: `-w 1 -k gthread --threads 4`.
- Single worker holds model, serializes via ThreadPoolExecutor(max_workers=1).
- TTS_BACKEND can be "pytorch" or "openvino".
- Startup: HTTP 503 until `_service_started` is set; after that, no 503 even if idle-unloaded.
- OpenVINO compiled-model cache path: `/ov/cache` (default).
- 0.6B and 1.7B are the only MODEL_SIZE presets; resolve_model_repo maps them.
- LOW_RAM_MODE enables malloc_trim and idle unload.
- Frontend: React + Vite + Tailwind + Zustand, served from Flask.

These invariants are what our tests must protect.

## 4. Current Problems

(Used as justification and as a checklist: each item should be fixed by the rewrite.)

- Mixed test frameworks:
  - Most tests use unittest.
  - test_prompt_diagnostics.py relies on pytest `tmp_path` fixture but is run
    with `python -m unittest discover`.
- Duplicated fake_model modules:
  - Inline in:
    - tests/test_app_api.py
    - tests/test_voice_design.py
    - tests/test_omnivoice_engine.py
    - tests/ui/fixtures/fake_model_server.py
  - Any change to model.py's public shape can break all of them independently.
- One massive file:
  - tests/test_app_api.py: 688 lines, 36 tests, covers all endpoints, Omnivoice, async jobs, voice design, etc.
- Fragile patterns:
  - Many busy-wait polling loops: `for _ in range(100): time.sleep(0.01)`
  - Inline lambdas repeated 3-4 times as fake_run_omnivoice_job.
  - sys.modules manipulation scattered in many files.
- Critical invariants untested:
  - Startup 503 / _service_started gating.
  - Idle unload and reload.
  - Backend mismatch failures (openvino requested but IR missing).
  - Stateful KV contamination across requests.
  - Concurrency / executor behavior.
  - LOW_RAM_MODE / malloc_trim interactions.
- UI E2E gaps:
  - Only happy-path tests:
    - No OmniVoice flow coverage.
    - No Stitch Studio page.
    - No error/503/busy/cancel UX.
- No central configuration:
  - No conftest.py, no shared fixtures, no markers.
  - New contributors must reconstruct PYTHONPATH and commands from CI YAML.

## 5. High-Level Design

We will:

- Migrate all Python tests from unittest to pytest.
- Introduce conftest.py with:
  - Markers.
  - Shared fixtures.
  - PYTHONPATH helpers.
- Build a canonical fake runtime (FakeModelRuntime) in tests/fixtures/fake_runtime.py.
  - This is THE single fake model module used by:
    - All Python tests.
    - UI E2E fake_model_server.
- Split tests into clearly named modules, each focused on 1 area.
- Enrich fake_model_server with:
  - Small delays.
  - Configurable error profiles.
  - OmniVoice simulation.
- Rewrite Playwright E2E tests to use richer fake_model_server and cover:
  - OmniVoice flow.
  - Stitch Studio.
  - Async generate + cancel.
  - Error/busy UX.

Everything remains fake and fast in CI.

## 6. Directory Structure (Target)

After rewrite, tests/ must look like this:

tests/
  conftest.py

  fixtures/
    fake_runtime.py
    fake_openvino.py
    fake_omnivoice.py
    fake_whisper.py

  tier1_unit/
    test_audio_post.py
    test_model_config.py
    test_presets.py
    test_config.py
    test_voice_library.py
    test_segment_library.py
    test_ov_talker_runtime.py
    test_ov_vocoder_runtime.py
    test_streaming_vocoder.py
    test_asr_check_text.py
    test_export_utils.py
    test_prompt_diagnostics.py
    test_validate_repo.py
    test_parity_helpers.py
    test_dump_audio.py

  tier2_backend/
    test_app_health.py
    test_app_generate.py
    test_app_generate_async.py
    test_app_voice_design.py
    test_app_omnivoice.py
    test_app_voices.py
    test_app_runtime_config.py
    test_model_lifecycle.py
    test_voice_design_swap.py
    test_omnivoice_engine_logic.py

  tier3_api_integration/
    test_api_smoke.py
    test_api_async_lifecycle.py
    test_api_openai_compat.py
    test_api_omnivoice_endpoints.py

  ui/
    fixtures/
      fake_model_server.py
    playwright.config.js
    core/
      basic.spec.js
    generate/
      generate.spec.js
      async_cancel.spec.js
    voice-design/
      voice-design-qwen.spec.js
      voice-design-omnivoice.spec.js
    voice-library/
      voices.spec.js
    stitch-studio/
      stitch-studio.spec.js
    runtime/
      runtime-config.spec.js
    performance/
      performance.spec.js

Rules:

- All Python tests use pytest. No unittest. No `python -m unittest discover`.
- No test file may define its own fake_model module inline.
  All must import FakeModelRuntime (or derived helpers) from fixtures.
- Tests that need PyTorch or OpenVINO:
  - Must be wrapped with `@pytest.mark.skipif` or `@pytest.mark.slow`.
  - Must run with `--co` to verify they can be collected in CI.

## 7. Core Infrastructure

### 7.1 conftest.py

Path: tests/conftest.py

Responsibilities:

- Set PYTHONPATH so src/ and src/export/ are importable.
- Define markers:
  - @pytest.mark.unit
  - @pytest.mark.integration
  - @pytest.mark.slow (for torch- or OpenVINO-dependent tests)
- Provide basic fixtures:
  - tmp_env: temporary environment dictionary.
  - monkeypatch-based helpers for env-sensitive modules.

Implementation details:

- At import time:
  - import sys, os
  - Insert "/app/src" and "/app/src/export"-style paths:
    - In CI and local dev, use:
      - str(Path(__file__).resolve().parent.parent / "src")
      - str(Path(__file__).resolve().parent.parent / "src" / "export")
    - Prepend to sys.path if not already present.
- pytest_configure:
  - Add markers.
- No model imports. No heavy dependencies.

### 7.2 FakeModelRuntime

Path: tests/fixtures/fake_runtime.py

This is the central artifact. Every other test and fake server imports from here.

Design rules:

- Minimal: only what is needed for the Flask app, model.py, voice_design.py,
  omnivoice_engine.py, and voice_library.py to function.
- No threads by default. Async-job behavior is synchronous but hookable.
- All controllable behaviors via constructor kwargs.
- Provide an `install()` method that monkeypatches `sys.modules["persona_forge.model"]`
  and related symbols.

Public interface (minimum):

class FakeModelRuntime:
    # Basic flags
    _service_started: bool
    _model_loaded: bool
    startup_failed: bool
    tts_backend: str

    # Call tracking (for assertions)
    load_model_calls: List[Dict[str, Any]]
    force_unload_calls: List[Dict[str, Any]]
    generate_calls: List[Dict[str, Any]]

    # Async job tracking
    jobs: Dict[str, Dict[str, Any]]

    # Configurable behaviors
    generate_should_fail: bool
    generate_error_code: int
    generate_delay_ms: int
    swap_in_progress: bool
    initial_service_started: bool  # whether startup 503 should be simulated

    # Methods:
    def install(self, overrides: Dict[str, Any] | None = None):
        # - Ensure sys.modules has persona_forge.model.
        # - Attach all attributes from this instance as module attributes
        #   so that persona_forge.app.model.<attr> and model.<fn> work.
        # - Apply any 'overrides' onto the fake module object.

    def health_state(self) -> Dict[str, Any]:
        # Returns a dict mirroring real health:
        # {
        #   "status": "ok" if (_service_started and _model_loaded) else "degraded",
        #   "service_started": self._service_started,
        #   "model_loaded": self._model_loaded,
        #   "startup_failed": self.startup_failed,
        #   "backend": self.tts_backend,
        # }

    def apply_runtime_config(self, updates: Dict[str, Any]):
        # Accept and apply known keys:
        # - TTS_BACKEND
        # - IDLE_UNLOAD_SECONDS
        # - OPENVINO_RELEASE_TORCH, etc.
        # Log calls; update internal state.

    def resolve_seed(self, seed: Any) -> int:
        # Implement same rules as real resolve_seed:
        # - None -> deterministic random int in [0, 2^31-1]
        # - int in range -> as-is
        # - else -> clamp or raise in a deterministic way.

    def _run_generate(self, text: str, voice_id: str | None,
                      format: str, seed: int, **kwargs) -> Tuple[bytes, int]:
        # Generate a tiny silent WAV:
        # - Optional delay: generate_delay_ms
        # - If generate_should_fail:
        #     raise an error matching generate_error_code.
        # Append call to generate_calls.

    def _run_generate_with_streaming(self, text, voice_id, seed,
                                      on_audio_chunk, **kw):
        # Simulate streaming by calling on_audio_chunk 2-3 times
        # with fake PCM bytes, then once with is_final=True.

    def _create_job(self, text, voice_id, format, seed, **kw) -> str:
        # Create an in-memory async job:
        # - job_id = simple UUID or "job-<N>"
        # - status = "running"
        # - store in self.jobs
        # - If generate_delay_ms > 0: simulate completion synchronously
        #   or immediately mark "completed" with fake audio bytes.
        return job_id

    def get_job_progress(self, job_id: str) -> Dict[str, Any]:
        # Return {status, message, progress_pct, started, finished}
        # If missing, return {"status": "not_found"}.

    def cancel_job(self, job_id: str) -> bool:
        # Set status="cancelled" if "running".

    def wait_for_job_completion(self, job_id: str, timeout: float = 2.0) -> Dict:
        # Utility for tests:
        # - In the fake, jobs complete instantly; return job data.
        # - In a future async variant, loop with sleep up to timeout.

Additionally, expose module-level convenience:

def get_fake_runtime(**kwargs) -> FakeModelRuntime:
    # Create and install.
    rt = FakeModelRuntime(**kwargs)
    rt.install()
    return rt

### 7.3 Fake OpenVINO

Path: tests/fixtures/fake_openvino.py

Used by:
- test_ov_talker_runtime.py
- test_ov_vocoder_runtime.py
- Any test where we call openvino-related helpers without the real runtime.

Minimum interface:

class FakeCore:
    def read_model(self, model_path):
        return FakeOVModel()

    def compile_model(self, model, device=None, config=None):
        return FakeCompiledModel(model)

class FakeOVModel:
    inputs: List[FakeInput]
    outputs: List[FakeOutput]

class FakeCompiledModel:
    def create_infer_request(self):
        return FakeInferRequest()

class FakeInferRequest:
    def set_input(self, tensor, port_id=None):
        ...
    def infer(self):
        # Return fake tensor(s) consistent with output shapes.
    def get_tensor(self, port_id):
        ...

These fakes never implement real inference. They exist only to validate:
- That our code constructs the correct graph shapes.
- That infer-request lifecycles are correct (no per-token recreate, etc.).
- That stateful helpers (capacity, reset, etc.) behave properly.

### 7.4 Fake OmniVoice

Path: tests/fixtures/fake_omnivoice.py

Used by:
- test_omnivoice_engine_logic.py
- fake_model_server (for OmniVoice UI E2E)

Interface:

class FakeOmniVoiceModel:
    def __init__(self,
                 script: List[Dict] | None = None,
                 always_drone: bool = False,
                 fail_on: int | None = None):
        # 'script' is a queue of draw outcomes consumed in order.
        # Each item: {audio: bytes-like or np array, drone: bool, fail: bool}

    def generate(self, segment, instruct, ...) -> Dict:
        # Pop from script or return a default synthetic audio block.
        # Optionally flag as drone.

Expose:

def create_fake_omnivoice(script=None, **kw) -> FakeOmniVoiceModel:
    ...

### 7.5 Fake Whisper

Path: tests/fixtures/fake_whisper.py

Used by:
- test_asr_check_text.py

Interface:

class FakeWhisperModel:
    def transcribe(self, audio, language=None, **kw):
        return {"segments": [{"text": "This is a fake transcript."}]}

Used only for verifying normalization, matching, and validation logic.

## 8. Tier 1: Unit Tests

Criteria:

- No Flask app.
- No HTTP server.
- Directly call functions under test.
- Either:
  - Pure logic (no mocks), or
  - Lightweight mocks/fixturing via FakeModelRuntime or similar.

Run:

- Fast (< 5 seconds total).
- All in CI.
- No Docker, no models, no OpenVINO IR.

### 8.1 test_audio_post.py

File: tests/tier1_unit/test_audio_post.py

Purpose:
- Validate all DSP functions in src/persona_forge/audio_post.py.
- Prevent regressions that silently degrade audio quality.

Tests (at minimum):

- compress:
  - reduces dynamic range; saturates peaks.
- normalize_rms:
  - scales to target RMS; identity if already at target.
- limit_peak:
  - clips at threshold.
- crossfade_concat:
  - length, crossfade continuity (no clicks).
- concat_with_padding:
  - insert silence between segments.
- stitch_segments:
  - end-to-end behavior; handles empty list gracefully.
- trim:
  - trims silence at start and end.
- apply_fades:
  - applies fade in/out.
- analyze_take:
  - detects:
    - empty audio
    - near-silent audio
    - drone-like content (low energy variance).

Implementation notes:

- Generate synthetic inputs:
  - sine waves, noise, constant-value arrays.
- No mocks.

### 8.2 test_model_config.py

File: tests/tier1_unit/test_model_config.py

Purpose:
- Ensure resolve_model_repo, resolve_voice_design_model_repo,
  configure_hf_token, resolve_torch_load_config behave deterministically.

Tests:

- resolve_model_repo:
  - 0.6B -> ends with 0.6B-Base
  - 1.7B -> ends with 1.7B-Base
  - custom MODEL_REPO/MODEL_REVISION
  - invalid MODEL_SIZE raises ValueError
- resolve_voice_design_model_repo:
  - returns distinct repo from Base.
- configure_hf_token:
  - precedence: HF_TOKEN env > file path > None.
- resolve_torch_load_config:
  - maps MODEL_SIZE to dtype and low_memory.

Implementation notes:

- No torch required:
  - Fake only what is needed (e.g., `type("FakeTorch", ...)`)
  - Or use pytest.importorskip if torch is optional.

### 8.3 test_presets.py

File: tests/tier1_unit/test_presets.py

Purpose:
- Validate preset selection, capacity math, and path separation.

Tests:

- get_preset for 0.6B and 1.7B.
- capacity_for_seconds / seconds_for_capacity.
- VoiceDesign preset:
  - Different IR base path
  - Different compression mode
  - No collision with Base

No mocks. Pure logic.

### 8.4 test_config.py

File: tests/tier1_unit/test_config.py

Purpose:
- Test apply_preset_env behavior for MODEL_SIZE and TTS_MAX_SPEECH_SECONDS.

Tests:

- apply_preset_env for each MODEL_SIZE.
- Explicit overrides (expert users).
- Interaction between TTS_MAX_SPEECH_SECONDS and preset.

Use a temporary environment (monkeypatch) to avoid polluting host.

### 8.5 test_voice_library.py

File: tests/tier1_unit/test_voice_library.py

Purpose:
- Filesystem CRUD, path traversal, ordering.

Tests:

- save_voice + get_voice.
- list_voices:
  - ordering.
  - empty directory.
- update_voice.
- delete_voice.
- path traversal rejection.
- corrupt JSON handling.

Implementation:

- Use pytest tmp_path.
- Real filesystem, real functions.

### 8.6 test_segment_library.py

File: tests/tier1_unit/test_segment_library.py

Purpose:
- Same as voice_library, for segment_library.

Tests:

- CRUD.
- Metadata persistence.
- Path traversal.
- Listing order.
- Corrupt entries.

### 8.7 test_ov_talker_runtime.py

File: tests/tier1_unit/test_ov_talker_runtime.py

Purpose:
- Test helpers inside src/persona_forge/openvino/talker.py that are safe to unit-test
  without a real OpenVINO runtime.

Tests:

- _stateful_generation_steps (main vs predictor).
- _to_numpy for numpy/torch interop.
- _cache_position_or_default.
- _dynamic_cache_from_kv.

Use:
- fake_openvino fixtures where needed.
- @pytest.mark.slow + importorskip for torch-dependent tests.

### 8.8 test_ov_vocoder_runtime.py

File: tests/tier1_unit/test_ov_vocoder_runtime.py

Purpose:
- Validate chunking behavior of vocoder runtime.

Tests:

- iter_decode_chunks:
  - batch preservation.
  - boundary behavior.
- Empty input handling.
- Wrong quantizer count rejection.

Use OpenVinoVocoderRuntime.__new__ and monkeypatch _run_ir.

### 8.9 test_streaming_vocoder.py

File: tests/tier1_unit/test_streaming_vocoder.py

Purpose:
- Validate StreamingVocoderSession behavior: hooks, flushes, EOS handling.

Tests:

- Hook forward and restore.
- Decode incrementally at 300-frame boundaries.
- Final prefix flush.
- Exclude EOS frame.
- Restore forward on failure.
- Reject wrong codebook shape.

Fake talker only.

### 8.10 test_asr_check_text.py

File: tests/tier1_unit/test_asr_check_text.py

Purpose:
- Text normalization, matching, reference validation (no real ASR).

Tests:

- _normalize_for_match.
- compute_transcript_match_score.
- validate_reference_text with fake_whisper.
- Edge cases:
  - empty text
  - very short
  - very long
  - mismatched transcript

### 8.11 test_export_utils.py

File: tests/tier1_unit/test_export_utils.py

Purpose:
- Test utility helpers from export module:
  - _example_inputs shape logic.
  - _versioned_dirname.
  - _source_hash.
  - _compress mode selection.
  - _export_provenance.
  - _resolved_model_revision.

Use:
- SimpleNamespace and mocks for tokenizer/model objects.
- No real OpenVINO or torch weights.

### 8.12 test_prompt_diagnostics.py

File: tests/tier1_unit/test_prompt_diagnostics.py

Purpose:
- Test reference_codes, dump_reference_prompt, dump_talker_parameter_manifest.

Use:
- pytest tmp_path properly.
- For torch-dependent parts: skipif or importorskip.

### 8.13 test_validate_repo.py

File: tests/tier1_unit/test_validate_repo.py

Purpose:
- Conventional Commit override parser.

Tests:

- Accept single-type entries.
- Reject composite headers.
- Accept no-blank-line variant.
- Ignore bodies without override block.

### 8.14 test_parity_helpers.py

File: tests/tier1_unit/test_parity_helpers.py

Purpose:
- ensure parity gates "fail closed."

Tests:

- require_output_head fails when head is missing.

### 8.15 test_dump_audio.py

File: tests/tier1_unit/test_dump_audio.py

Purpose:
- Validate _RssSampler correctness for benchmark tooling.

Tests:

- Reports generation peak RSS.
- Detects maxrss delta gaps.
- Rejects non-positive interval.

## 9. Tier 2: Backend Tests

Criteria:

- Import Flask app and backend modules.
- Use FakeModelRuntime (never hand-roll fake_model).
- Validate invariants in startup, swap, async jobs, concurrency, and config.
- No HTTP daemon; use app.test_client().

Run:

- Fast (< 10 seconds total).
- All in CI.

### 9.1 test_app_health.py

File: tests/tier2_backend/test_app_health.py

Purpose:
- Ensure /health behaves correctly in startup, running, and failure states.

Tests:

- Normal:
  - _service_started=True, _model_loaded=True -> 200, status="ok".
- Not started:
  - _service_started=False -> 503.
- Startup failed:
  - startup_failed=True -> 503 with message hint.

Use:

- @pytest.fixture:
  - app_client_with_state(service_started=True/False, model_loaded=True/False).

### 9.2 test_app_generate.py

File: tests/tier2_backend/test_app_generate.py

Purpose:
- Validate /generate and /v1/audio/speech behavior, input validation,
  error handling, and streaming behavior.

Tests:

- /generate:
  - Success:
    - 200 with audio (wav/mp3).
    - Correct Content-Type.
    - Uses seed if provided.
  - Missing text:
    - 400/422 with appropriate error.
  - Invalid format:
    - returns known error.
  - Too-long text:
    - returns capacity-related error.
- /v1/audio/speech:
  - OpenAI envelope, fields, and formats.
- /stream (if applicable):
  - Chunked PCM.
  - Correct headers.

Use:

- FakeModelRuntime with generate_delay_ms=0.
- For "too-long", tweak capacity_for_seconds in preset or pass large text and ensure app-level validation still triggers.

### 9.3 test_app_generate_async.py

File: tests/tier2_backend/test_app_generate_async.py

Purpose:
- Validate async job lifecycle:
  - POST /generate/async
  - GET /generate/progress
  - POST /generate/cancel
  - GET /generate/job/<id>/audio

Tests:

- Create job -> running -> completed -> audio fetch.
- Cancel job -> job shows cancelled.
- Unknown job ID -> 404.

Implementation details:

- No polling loops.
- FakeModelRuntime._create_job completes synchronously.
- Use FakeModelRuntime.wait_for_job_completion(job_id) in tests.

### 9.4 test_app_voice_design.py

File: tests/tier2_backend/test_app_voice_design.py

Purpose:
- Validate /voice_design, /voice_design/preview/<id>/save,
  /voice_design/progress, and their interaction with swap/busy.

Tests:

- Happy path:
  - /voice_design returns a preview with audio.
- Swap-in-progress:
  - set swap_in_progress=True -> concurrent /generate -> 503.
- Invalid sample text:
  - too long or empty -> 4xx.
- Seeds:
  - seed propagation.

Use:

- FakeModelRuntime + patch for voice_design.run_voice_design_request.

### 9.5 test_app_omnivoice.py

File: tests/tier2_backend/test_app_omnivoice.py

Purpose:
- Validate all OmniVoice endpoints:
  - /omnivoice/audition
  - /omnivoice/audition/progress
  - /omnivoice/stitch
  - /omnivoice/save
  - /omnivoice/segments, /omnivoice/segments/<id>/audio, DELETE
  - /omnivoice/progress

Tests:

- audition -> candidates generated -> select -> stitch -> save.
- segments:
  - CRUD + path traversal safety.

Use:

- fake_omnivoice + FakeModelRuntime.

### 9.6 test_app_voices.py

File: tests/tier2_backend/test_app_voices.py

Purpose:
- Validate /voices endpoints (CRUD) at the HTTP layer.

Tests:

- list, create, get, update, delete.
- path traversal rejection.
- sample text update.

### 9.7 test_app_runtime_config.py

File: tests/tier2_backend/test_app_runtime_config.py

Purpose:
- Validate /runtime/config (GET and POST).

Tests:

- GET returns known keys and types.
- POST applies:
  - TTS_BACKEND.
  - IDLE_UNLOAD_SECONDS.
  - OPENVINO_RELEASE_TORCH.
- Reject unknown keys.

Use:

- FakeModelRuntime.apply_runtime_config to confirm calls.

### 9.8 test_model_lifecycle.py (NEW)

File: tests/tier2_backend/test_model_lifecycle.py

Purpose:
- Protect critical runtime invariants that are frequently broken by changes.

Tests (key):

- Startup 503:
  - With FakeModelRuntime(initial_service_started=False):
    - /health returns 503.
    - After simulating startup (set _service_started=True), /health OK.
- Startup failed:
  - With startup_failed=True:
    - /health returns 503 with error info.
- Idle unload:
  - Model loaded; idle-unload triggered -> _model_loaded=False.
  - New request reloads (simulate in test).
  - Verify load_model called.
- Backend mismatch:
  - TTS_BACKEND=openvino, but IR missing:
    - Confirm startup_failed behavior.
- LOW_RAM_MODE / malloc_trim:
  - Mock libc malloc_trim or the Python trim function.
  - Confirm it's called after unload.

Use:

- Carefully patch only what is required.
- Do not import real model.py.

### 9.9 test_voice_design_swap.py

File: tests/tier2_backend/test_voice_design_swap.py

Purpose:
- Validate that VoiceDesign swaps profiles correctly and handles failures.

Tests:

- On success:
  - Unload Base, load VOICE_DESIGN_PROFILE.
  - Base not restored automatically.
- On generation failure:
  - VoiceDesign unloaded; Base NOT restored (by design).
- Sample text validation:
  - reject too long.
  - accept valid.

### 9.10 test_omnivoice_engine_logic.py

File: tests/tier2_backend/test_omnivoice_engine_logic.py

Purpose:
- Test retry-once logic, parameter clamping, and progress behavior.

Tests:

- First draw is drone:
  - engine retries once; second draw is used.
- All attempts are flagged:
  - returned as flagged, not raised.
- Parameter clamping:
  - num_step, durations, speed.
- Optional params:
  - omit if not provided.

Use:

- fake_omnivoice + carefully patched imports.

## 10. Tier 3: API Integration Tests

Criteria:

- Treat Flask app as a black-box server.
- Run via real HTTP (not test_client).
- Use FakeModelRuntime via fake_model_server (same as UI).
- Validate response headers, shapes, and error handling from an external client perspective.

Run:

- Slightly slower; keep minimal (3-5 files, 20-40 tests).
- All in CI.

### 10.1 test_api_smoke.py

File: tests/tier3_api_integration/test_api_smoke.py

Purpose:
- Ensure core endpoints behave correctly when accessed over HTTP.

Tests:

- GET /health -> 200.
- GET / -> 200 with HTML.
- POST /generate with minimal payload -> 200 and audio.
- POST /v1/audio/speech -> 200 and audio.

Use:

- Start fake_model_server in a thread.
- Use httpx or requests.
- Teardown: stop server.

### 10.2 test_api_async_lifecycle.py

File: tests/tier3_api_integration/test_api_async_lifecycle.py

Purpose:
- Validate the async job lifecycle via HTTP.

Tests:

- create -> progress (running) -> progress (completed) -> fetch audio.
- cancel before completion.
- Unknown job -> 404.

### 10.3 test_api_openai_compat.py

File: tests/tier3_api_integration/test_api_openai_compat.py

Purpose:
- Ensure the OpenAI-compatible endpoint is stable.

Tests:

- Minimal request.
- Fields present in response JSON.
- Error on missing text.

### 10.4 test_api_omnivoice_endpoints.py

File: tests/tier3_api_integration/test_api_omnivoice_endpoints.py

Purpose:
- Validate OmniVoice endpoint contracts.

Tests:

- audition -> progress -> select -> stitch -> save.
- segments CRUD.

Use enriched fake_model_server in "omnivoice" mode.

## 11. UI / E2E Tests (Playwright)

Criteria:

- No real model.
- No Docker.
- Same fake_model_server, enriched with delays and error profiles.
- Run in CI (ci-ui.yml).

fake_model_server enhancements:

- Use FakeModelRuntime instead of custom stub.
- Add:
  - generate_delay_ms: 200-600ms to allow loading states to render.
  - OmniVoice fake:
    - Fake audition, candidates, takes, stitch.
  - Error profiles via env:
    - TEST_PROFILE=error_on_generate: /generate returns 500.
    - TEST_PROFILE=busy: swap_in_progress True.
    - TEST_PROFILE=slow_async: async jobs take 3-5 seconds.

Tests (final set):

- core/basic.spec.js:
  - Health check via fetch.
  - Home page loads.
  - Sidebar navigation works.

- generate/generate.spec.js:
  - Happy path:
    - Type text -> generate -> audio player visible.
  - Empty text:
    - Generate button disabled.
  - Error path (via TEST_PROFILE=error_on_generate):
    - Generate -> error banner visible.

- generate/async_cancel.spec.js:
  - Start async generation.
  - See progress bar.
  - Click cancel.
  - Confirm cancelled state.

- voice-design/voice-design-qwen.spec.js:
  - Qwen mode:
    - Fill description + sample text.
    - Generate.
    - Wait for result.
    - Save to library.
    - Navigate to library -> voice card visible.

- voice-design/voice-design-omnivoice.spec.js:
  - Switch engine to OmniVoice.
  - Fill segments + instruct.
  - Audition.
  - Select takes.
  - Stitch.
  - Save.
  - Verify library card.

- voice-library/voices.spec.js:
  - View voices.
  - Inline-edit reference text.
  - Delete a voice.
  - Confirm empty state text when none.

- stitch-studio/stitch-studio.spec.js:
  - Load existing segments.
  - Arrange order.
  - Trigger stitch.
  - Confirm stitched audio.

- runtime/runtime-config.spec.js:
  - Open runtime page.
  - Toggle a known knob.
  - Confirm API call and persisted value.

- performance/performance.spec.js:
  - Page interactive within 5s.
  - Navigate all pages, no console errors.

Playwright config:

- chromium-only.
- sequential.
- 30s timeout, retries=2 in CI.
- Uses QWEN3_TTS_UI_URL or local fake server.

## 12. Dependencies and Tooling

requirements-dev.txt (target):

Include:

- pytest
- pytest-xdist
- httpx (or requests; pick one and stick with it)
- Flask (already)
- numpy (already)
- PyYAML (already)
- soundfile (already)
- (optional) time-machine (if testing timing or expiry)

Remove:

- All unittest-specific fluff (there is none currently).

pytest configuration:

Either in pyproject.toml or pytest.ini:

- Test paths: tests/
- Markers: unit, integration, slow
- Addopts:
  - --tb=short
  - -ra
- Pythonpath:
  - src
  - src/export

## 13. CI Changes

### 13.1 ci.yml

Changes:

- Replace:
  - `python -m unittest discover -s tests -v`
  with:
  - `python -m pytest -m "not slow" -n auto --tb=short`
- Ensure PYTHONPATH is set:
  - PYTHONPATH=src:src/export

Add a step:

- Lint + type-check (if applicable):
  - flake8 or ruff or whatever is already in the repo.

Keep:

- validate_repo.py run.
- git diff --check.
- Renovate config validator.

### 13.2 image.yml

No fundamental changes required.

Optional (nice-to-have):

- Run a small import + pytest --co check inside the container:
  - Confirm test modules are importable.

### 13.3 ci-ui.yml

Changes:

- No heavy changes needed; structure is already correct.
- Optionally:
  - Use environment variables for TEST_PROFILE in targeted runs.

## 14. Migration Strategy

This rewrite should be done in 2-4 PRs to keep risk manageable.

### Phase 1 — Infrastructure and pytest migration

Goal:

- Introduce pytest, conftest.py, FakeModelRuntime.
- Migrate all existing tests to pytest without changing coverage.
- Remove unittest discover from CI.

Steps:

- Add pytest + tools to requirements-dev.txt.
- Create conftest.py and fixtures/*.py.
- For each existing test file:
  - Port from unittest to pytest.
  - Replace inline fake_model with FakeModelRuntime.
  - Move to tier1_unit, tier2_backend, or tier3_api_integration.
- Fix test_prompt_diagnostics.py to use pytest properly.
- Update ci.yml:
  - Run pytest instead of unittest discover.
- Ensure:
  - All tests pass before proceeding to Phase 2.

### Phase 2 — Tier 2: backend tests and new invariants

Goal:

- Add tests for invariants not covered yet.
- Break test_app_api.py into focused files.

Steps:

- Create tier2_backend/ directory.
- Implement:
  - test_app_health.py
  - test_app_generate.py
  - test_app_generate_async.py
  - test_app_voice_design.py
  - test_app_omnivoice.py
  - test_app_voices.py
  - test_app_runtime_config.py
  - test_model_lifecycle.py
  - test_voice_design_swap.py
  - test_omnivoice_engine_logic.py
- Ensure no file exceeds 200 lines without justification.

### Phase 3 — Tier 3: API integration tests

Goal:

- Add black-box HTTP tests.

Steps:

- Use fake_model_server as an actual HTTP server.
- Write tests in tier3_api_integration/.
- Add to CI.

### Phase 4 — UI E2E rewrite

Goal:

- Enrich fake_model_server.
- Extend Playwright tests.

Steps:

- Enrich fake_model_server.py:
  - Use FakeModelRuntime.
  - Add delays and error profiles.
  - Add OmniVoice simulation.
- Add:
  - async_cancel.spec.js
  - voice-design-omnivoice.spec.js
  - stitch-studio.spec.js
  - runtime-config.spec.js
- Keep all tests fast and stable.

## 15. Verification Criteria

After this rewrite is complete, all of the following must be true:

- In CI (ci.yml):
  - `python -m pytest -m "not slow" -n auto` passes.
  - No use of unittest discover.
  - No heavy dependencies installed.
  - All tests finish in under 3 minutes.

- In CI (ci-ui.yml):
  - Playwright E2E tests pass against fake_model_server.
  - No real models, no Docker.

- In the codebase:
  - No inline fake_model modules in test files.
  - No mixed unittest/pytest.
  - No busy-wait polling loops in async tests.
  - All tests import FakeModelRuntime (or derived fixtures) from tests/fixtures/fake_runtime.py.

- Coverage:
  - Startup 503 tested.
  - Idle unload / reload tested.
  - Backend mismatch failure tested.
  - OmniVoice audition/stitch/save flow tested (both backend and UI).
  - Stitch Studio page has at least a basic test.
  - Async job cancel UX is tested in UI.

If any of these criteria cannot be met, the agent should:
- Note the missing item at the top of this document.
- Explain the reason.
- Propose a minimal fix.

## 16. Implementation Notes for AI Agents

- Treat AGENTS.md as the binding runtime/architecture reference.
  Read it before modifying behavior-critical tests.
- Do not alter production code to make tests easier unless:
  - The change is purely refactor-safe (e.g., factoring a helper).
- When in doubt:
  - Prefer smaller, focused tests over one large file.
  - Prefer explicit assertions with descriptive messages over opaque checks.
- All Python code:
  - Use typing where reasonable.
  - No comments unless explaining non-obvious logic.
- Commits:
  - Conventional Commits, scopes: (ci), (test), (deps).
  - Each phase in its own branch/PR.
  - Include Release Please override:
    - test: describe changes.

## FINAL STATUS (2026-07-06)

What was completed:

- Migrated all tests from unittest to pytest; removed 18 legacy tests/test_*.py.
- Implemented canonical FakeModelRuntime as the single fake for all tests.
- Created fixtures: FakeOpenVINO, FakeOmniVoice, FakeWhisper.
- Built three test tiers (fake, no models, no Docker):
  - tier1_unit: 148 tests.
  - tier2_backend: 66 tests (Flask + backend logic).
  - tier3_api_integration: 25 tests (black-box HTTP).
- Wired CI:
  - ci.yml uses pytest -m "not slow" -n auto on three tier directories.
  - ci-ui.yml runs Playwright E2E against fake_model_server started in its own step.
- E2E (stable subset):
  - core/basic.spec.js
  - generate/generate.spec.js
  - voice-design/voice-design-qwen.spec.js
  - voice-library/voices.spec.js
  - runtime/runtime-config.spec.js
  - performance/performance.spec.js

Runtime notes:

- OmniVoice engine tests (test_omnivoice_engine_logic.py) marked slow (require torch).
- Rope repair tests (test_export_rope_repair.py) marked slow.

Open items (intentional, to be implemented in follow-up work):

- Re-add async_cancel E2E:
  - Start async generation, confirm progress bar, click Stop, confirm cancelled.
  - Requires: stable data-testid on SpeakPage progress bar and Stop button.

- Re-add stitch-studio E2E:
  - Load Stitch Studio, enter name, insert segments, trigger stitch.
  - Requires: data-testid on Stitch Studio page header and controls.

- Re-add voice-design-omnivoice E2E:
  - Switch engine to OmniVoice, fill segments/instruct, audition, select takes, stitch, save.
  - Requires: specific selectors for "Segment rack" and take buttons to be unique and stable.

- Add data-testid hooks (frontend):
  - speak-progress-bar
  - speak-stop-button
  - stitch-studio-title or similar unique heading
  - stitch-studio-insert-button, stitch-studio-save-button
  - segment-rack-area, segment-take-button
  - (Any others needed for stable E2E selectors.)

- Harden test_app_api / backend tests:
  - Mark as "stable"; no further changes unless app.py/voice_design.py/omnivoice_engine.py change.

If you cannot execute a step because of ambiguity, propose a minimal alternative
in this document before changing behavior.

End of plan.
