# Test Strategy

You-changed-X → run-Y reference for persona-forge.

This is the single, unambiguous mapping from code changes to the tests you must run and the gates that must pass.

Non-negotiable:

- Fail-closed: if a test is flaky or unclear, it FAILS. Never relax a threshold to make a run pass.
- Parity gates are not "nice to have." If model output or export behavior changed, you must run them.
- All commands assume the repo root as working directory unless stated otherwise.

## 1. Quick-reference: you changed X → run Y

### 1.1 Model runtime / generation (model.py, generation, sampling, cache logic)

Affected:
- src/persona_forge/model.py
- src/persona_forge/model_config.py
- src/persona_forge/generation.py (or similar generation/sampling code)
- Cache/position/mask logic

Run:
- python scripts/validate_repo.py
- pytest tests/ -k "model" -v
- pytest tests/test_app_api.py -v   # /generate round-trips
- If K/V cache, stateful, or position IDs touched:
  - pytest tests/test_ov_talker_runtime.py -v
  - Any parity-related unit tests (search for "cache" in tests/).
- If generation behavior changed (sampling, logits, seeds):
  - Must run Tier 3 parity on docker-agent (see §3).

### 1.2 OpenVINO adapters and runtime (ov_talker, ov_predictor, ov_vocoder, stateful cache)

Affected:
- src/persona_forge/ov_talker_runtime.py
- src/persona_forge/ov_predictor_runtime.py
- src/persona_forge/ov_vocoder_runtime.py
- src/export/ov_stateful_cache.py
- Any stateful/explicit cache wiring

Run:
- python scripts/validate_repo.py
- pytest tests/test_ov_talker_runtime.py -v
- pytest tests/test_ov_vocoder_runtime.py -v
- pytest tests/test_export_openvino.py -v
- Any parity-related unit tests.
- If you changed cache, stateful models, or IR construction:
  - Must run Tier 3 parity on docker-agent (see §3).

### 1.3 Export / quantization / IR build (src/export/*)

Affected:
- src/export/*.py (export_openvino, ov_export_wrappers, parity_contract, etc.)
- Any export metadata or compression strategy

Run:
- python scripts/validate_repo.py
- pytest tests/test_export_openvino.py -v
- pytest tests/test_parity_helpers.py -v
- pytest tests/test_streaming_vocoder.py -v
- If export graph changed:
  - Rebuild container image.
  - Must run Tier 3 (FP32 parity) and Tier 4 (quality + perf) on docker-agent (see §3-4).

### 1.4 Queueing / model swap / serving (app.py, runtime behavior)

Affected:
- src/persona_forge/app.py
- /generate, /v1/audio/speech, /health, /runtime/config
- Queueing, model swap, idle-unload, backend switching
- /voice_design, /omnivoice endpoints

Run:
- python scripts/validate_repo.py
- pytest tests/test_app_api.py -v
- docker compose config --quiet   # ensure no compose regressions
- If you changed /health or /runtime/config:
  - Verify frontend health-status and swap banners visually.
- If you changed model-swap or queueing:
  - Manually exercise swap flow in UI and via curl.
  - Confirm:
    - 503 behavior during cold startup only
    - swap_in_progress flag propagation
    - No race conditions between concurrent requests.

### 1.5 OmniVoice engine

Affected:
- src/persona_forge/omnivoice_*.py
- /omnivoice/* endpoints (audition, progress, segments, stitch, save)

Run:
- python scripts/validate_repo.py
- pytest tests/test_omnivoice_engine.py -v
- pytest tests/test_app_api.py -v -k "omnivoice"
- If segment library or stitch changed:
  - pytest tests/test_segment_library.py -v
- If audio post-processing (trimming, normalization) changed:
  - pytest tests/test_audio_post.py -v
- End-to-end on docker-agent:
  - Run a short OmniVoice audition + lock-in + stitch + save in UI.

### 1.6 Frontend-only changes (frontend/)

Affected:
- frontend/src/*, frontend/package.json, etc.
- No backend or model changes.

Run:
- python scripts/validate_repo.py
- In frontend/:
  - npm run lint
  - npm run build
- Visual checks (use your judgment):
  - If SpeakPage affected: generate speech and confirm basic flow.
  - If VoiceDesignPage affected: preview → save → verify in VoiceLibraryPage.
  - If OmniVoicePanel or StitchTimeline affected: run an audition → lock-in → stitch → save.
- If you change API client (api.ts) or store.ts types without touching backend:
  - Verify no mismatches: confirm endpoints, field names, and types match app.py responses.

If your change touches both frontend and backend, run the applicable backend tests too.

### 1.7 Container / Docker / Compose / deps

Affected:
- Dockerfile, compose.yml, entrypoint.sh, requirements/*
- Build, CI workflows

Run:
- python scripts/validate_repo.py
- docker compose config --quiet
- If deps changed:
  - Rebuild image.
  - Apply ready-to-test label and verify CI import smoke tests.
- If Gunicorn config, entrypoint, or LOW_RAM_MODE changed:
  - Manual smoke test in container: confirm:
    - single worker, correct thread count
    - health endpoint
    - idle-unload and reload behavior

## 2. Standard commands (run these first, always)

For any PR, at minimum:

- python scripts/validate_repo.py
- docker compose config --quiet   # requires REF_AUDIO_PATH, REF_TEXT env vars set
- pytest tests/ -v

Typical pytest filters (useful subsets):

- Model and runtime:
  - pytest tests/test_ov_talker_runtime.py tests/test_model_config.py -v
- Export:
  - pytest tests/test_export_openvino.py tests/test_parity_helpers.py -v
- API and endpoints:
  - pytest tests/test_app_api.py -v
- Voice design and voice library:
  - pytest tests/test_voice_design.py tests/test_voice_library.py -v
- OmniVoice:
  - pytest tests/test_omnivoice_engine.py tests/test_segment_library.py -v
- Audio post-processing:
  - pytest tests/test_audio_post.py -v
- Presets and repo validation:
  - pytest tests/test_presets.py tests/test_validate_repo.py -v

## 3. Parity gates (Tier 3)

Trigger when:

- model.py, OpenVINO adapters, or export pipelines changed
- cache, stateful models, or quantization strategy changed
- any code affecting numerical results or IR structure is modified

Run on docker-agent only.

High-level steps:

1. Baseline:
   - Generate with PyTorch backend (TTS_BACKEND=pytorch, do_sample=False).
2. FP32 OpenVINO:
   - Compare same inputs with OpenVINO FP32:
     - main prefill logits
     - several decode steps with growing cache
     - predictor prefill and all codebook steps
3. Quantized (INT8/INT4):
   - Compare final outputs; check accuracy, greedy-code agreement.
4. Full sequence:
   - Compare full generated code sequences end-to-end.
5. Record:
   - max/mean absolute error
   - top-1 agreement
   - top-k overlap
   - cache shapes
   - first divergent step (if any)

Fail-closed:

- If any step fails or cannot be run, the change is blocked until fixed.
- Never lower thresholds or ignore errors to get a green run.

## 4. Quality and performance (Tier 4)

Run for any change that touches:

- model runtime
- OpenVINO adapters
- quantization
- vocoder
- export
- memory / idle unload behavior

Run on docker-agent only.

Record:

- Audio duration
- End-to-end latency
- RTF
- Warm median/p95 latency
- Container peak RSS
- Host RAM/swap behavior
- Listening notes for voice quality

Use existing benchmark prompts from source control.

Fail-closed:

- If latency, RSS, or quality regresses meaningfully vs. last known baseline, treat as a real failure; explain or revert.