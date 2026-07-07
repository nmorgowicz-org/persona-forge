# Pocket TTS Hotswap Integration Plan

Date: 2026-07-07
Status: Draft — ready for implementation by an AI agent with zero external context.

## 1. Objective

Integrate Pocket TTS (kyutai-labs/pocket-tts, ~100M params, CPU-only) as a fourth
hotswappable TTS backend in this repository, selectable from:

- The RuntimeConfigPage UI (existing dropdown)
- POST /runtime/config
- TTS_BACKEND env var

Hotswap must use the existing infrastructure: the codebase already supports live backend
switching (openvino <-> pytorch) via force_unload + load_model; we will plug Pocket TTS
into that same mechanism.

High-level behavior:

- When TTS_BACKEND=pocket_tts:
  - Unload current model (force_unload)
  - Load Pocket TTS's TTSModel into the global model handle
  - Use Pocket TTS voice_state mechanism (from REF_AUDIO or per-voice WAV) for voice cloning
  - Route /generate, /v1/audio/speech, and async endpoints through Pocket TTS
- When switching away from pocket_tts:
  - Unload Pocket TTS model
  - Reload the requested backend (openvino/pytorch) as normal
- No co-loading: one model at a time (same policy as today).

## 2. Design Principles and Constraints

From AGENTS.md and existing architecture:

- One image, one process, one model at a time.
- Gunicorn: -w 1, never --preload, never more than one worker.
- All inference serialized via executor = ThreadPoolExecutor(max_workers=1).
- Preserve /generate, /v1/audio/speech, /health, MP3/WAV output contracts.
- Keep TTS_BACKEND=pytorch as rollback path.
- 503 during reconfig; after first load, idle-unloaded requests block in executor and reload.
- No CUDA. Torch CPU-only.
- Do not change existing OpenVINO, VoiceDesign, or OmniVoice behavior unless necessary.

Pocket TTS specifics:

- Official API:
  - from pocket_tts import TTSModel
  - TTSModel.load_model(language="english", temp=0.7, lsd_decode_steps=1, ...)
  - voice_state = model.get_state_for_audio_prompt("path/to/ref.wav")
  - audio = model.generate_audio(voice_state, "text")
  - or model.generate_audio_stream(voice_state, "text") for streaming chunks
- Outputs: 24kHz mono PCM (torch 1D tensor).
- Small enough that we can swap it in/out without changing mem limits.
- It uses PyTorch CPU (same torch stack). No OpenVINO needed for Pocket TTS.

## 3. Impact Summary (by layer)

Each section below is self-contained. An agent can implement step by step in this order.

### 3.1. New file: Pocket TTS runtime adapter

Create: src/qwen3_tts/pocket_tts_runtime.py

Responsibilities:

- Load Pocket TTS model
- Build voice states from reference audio
- Provide generation entry points compatible with model._run_generate
- Provide helpers to health_state, runtime_config, and cleanup

Implementation details:

- Module-level globals:
  - pocket_tts_model: TTSModel | None = None
  - pocket_tts_default_voice_state: dict | None = None
  - pocket_tts_voice_state_cache: dict[str, dict] = {}

- Function: load_pocket_tts_model(language: str, **kwargs)
  - From pocket_tts import TTSModel
  - pocket_tts_model = TTSModel.load_model(language=language, **kwargs)
  - Return pocket_tts_model

- Function: build_default_voice_state(model: TTSModel, ref_audio_path: str)
  - If not ref_audio_path or not os.path.exists(ref_audio_path): return None
  - Return model.get_state_for_audio_prompt(ref_audio_path)

- Function: get_pocket_tts_voice_state(
      model: TTSModel,
      voice_id: str | None,
      default_voice_state: dict | None,
      ref_audio_path: str,
  ):
  - If voice_id is None:
      - Use default_voice_state.
  - If voice_id is set:
      - If in pocket_tts_voice_state_cache: return cached.
      - Else:
        - Import qwen3_tts.voice_library
        - meta = voice_library.get_voice(voice_id)
        - wav_path = meta["wav_path"]
        - voice_state = model.get_state_for_audio_prompt(wav_path)
        - pocket_tts_voice_state_cache[voice_id] = voice_state
  - If no valid voice_state: raise RuntimeError

- Function: generate_pocket_tts(
      model: TTSModel,
      voice_state,
      text: str,
  ) -> tuple[torch.Tensor, int]:
  - audio = model.generate_audio(voice_state, text)
  - Return (audio, model.sample_rate)

- Function: unload_pocket_tts()
  - pocket_tts_model = None
  - pocket_tts_default_voice_state = None
  - pocket_tts_voice_state_cache.clear()

- Design:
  - This module must not import heavy qwen_tts or OpenVINO symbols.
  - It may import from qwen3_tts (voice_library, config) using the same PYTHONPATH.

### 3.2. model.py: Allow "pocket_tts" as a backend

File: src/qwen3_tts/model.py

All changes are localized. Do not alter Qwen3TTSModel load path unless TTS_BACKEND is pocket_tts.

3.2.1. Backend validation (two locations)

- In load_model(profile):
  - Current (line 296–297):
    - if TTS_BACKEND not in ("pytorch", "openvino"):
        raise RuntimeError(...)
  - Change to:
    - if TTS_BACKEND not in ("pytorch", "openvino", "pocket_tts"):
        raise RuntimeError(...)

- In apply_runtime_config(updates):
  - Current (line 707–708):
    - if backend not in ("pytorch", "openvino"):
        raise ValueError(...)
  - Change to:
    - if backend not in ("pytorch", "openvino", "pocket_tts"):
        raise ValueError(...)

3.2.2. load_model: Add pocket_tts branch

In load_model(profile), before the existing Qwen3TTSModel.from_pretrained call (around
line 337), add:

- If TTS_BACKEND == "pocket_tts":
  - Do NOT call Qwen3TTSModel.from_pretrained.
  - Do NOT install OVTalkerRuntime.
  - Use pocket_tts_runtime to load.

Concrete changes (conceptual, to be inserted as a guarded block):

- At top of file (near other imports, no need to be eager):

  - When TTS_BACKEND == "pocket_tts", imports are done lazily.

- Inside load_model(profile), after backend validation:

  - If TTS_BACKEND == "pocket_tts":

    - from qwen3_tts import pocket_tts_runtime
    - language = (os.getenv("POCKET_TTS_LANGUAGE") or "english").strip() or "english"
    - temp = float(os.getenv("POCKET_TTS_TEMP", "0.7"))
    - lsd_steps = int(os.getenv("POCKET_TTS_LSD_DECODE_STEPS", "1"))
    - eos_threshold = float(os.getenv("POCKET_TTS_EOS_THRESHOLD", "-4.0"))

    - pocket_tts_runtime.load_pocket_tts_model(
        language=language,
        temp=temp,
        lsd_decode_steps=lsd_steps,
        eos_threshold=eos_threshold,
      )

    - Set model = pocket_tts_runtime.pocket_tts_model  (reuse the same global "model"
      variable so _ensure_base_loaded and _run_generate see it).

    - Build default voice_state using profile.ref_audio:
        - voice_clone_prompt = pocket_tts_runtime.build_default_voice_state(
            model,
            profile.ref_audio,
          )
      (reuse the same global "voice_clone_prompt" name, but it now holds a Pocket TTS
       voice_state dict instead of a Qwen3-TTS voice_clone_prompt. _run_generate will
       treat it generically.)

    - active_profile = profile
    - _service_started = True
    - _model_loaded = True

    - Skip all Qwen3-specific steps: rotary repair, patches, OpenVINO, ref-text validation,
      etc.

    - Log: "[app_worker] Pocket TTS loaded and ready".

  - Elif TTS_BACKEND in ("pytorch", "openvino"):
    - Existing Qwen3TTSModel path (unchanged).

Notes:

- The global `model` is used both by Qwen3TTSModel (as model.model.talker etc.) and
  conceptually by Pocket TTS as the TTSModel instance. _run_generate will be updated
  to inspect TTS_BACKEND and use the correct path.

3.2.3. force_unload: Clean up Pocket TTS on unload

In force_unload() (around line 159):

- After setting model = None, voice_clone_prompt = None, ov_runtime = None, add:

  - from qwen3_tts import pocket_tts_runtime
  - pocket_tts_runtime.unload_pocket_tts()

Ensure this is safe when Pocket TTS is not loaded (it is; unload is idempotent).

3.2.4. _run_generate: Route to Pocket TTS

File: src/qwen3_tts/model.py, function _run_generate (starts ~line 1028).

Currently:

- Calls:
  - _ensure_base_loaded()
  - get_voice_clone_prompt(voice_id)
  - model.generate_voice_clone(...)

We must not break Qwen3TTS behavior while adding Pocket TTS path.

Change:

- After _ensure_base_loaded() and model check, branch on TTS_BACKEND:

  - If TTS_BACKEND == "pocket_tts":
    - from qwen3_tts import pocket_tts_runtime
    - voice_state = pocket_tts_runtime.get_pocket_tts_voice_state(
          model,
          voice_id=voice_id,
          default_voice_state=voice_clone_prompt,
          ref_audio_path=REF_AUDIO,
        )
    - (audio_tensor, sr) = pocket_tts_runtime.generate_pocket_tts(model, voice_state, text)
    - wav = _trim_silence(audio_tensor.cpu().numpy().ravel(), sr)
    - Set job frames_generated based on audio length / 80ms if desired, or approximate.
    - Do NOT call model.generate_voice_clone.
    - Skip logits_processor and max_new_tokens logic (Pocket TTS does its own internal decoding).
    - Still:
      - Respect job tracking (job.status, cancel_event) by polling job.cancel_event before/after.
      - Apply same logging format: "[generate] done elapsed=... audio=... RTF=...".
    - Return (wav, sr, job_id)

  - If TTS_BACKEND in ("pytorch", "openvino"):
    - Existing path (no changes).

Important:

- _ProgressLogitsProcessor is specific to Qwen3-TTS's transformers loop. Pocket TTS
  does not accept transformers-style logits processors. Do not inject it when
  TTS_BACKEND == "pocket_tts".

3.2.5. _ensure_base_loaded and model swap

No changes needed:

- _ensure_base_loaded() already:
  - Checks if model is loaded with BASE_PROFILE
  - If not, calls unload_foreign_models(), force_unload(), load_model(BASE_PROFILE)
- When TTS_BACKEND == "pocket_tts", BASE_PROFILE still determines whether we use Pocket TTS
  for /generate.

3.2.6. health_state: Pocket TTS metadata

File: src/qwen3_tts/model.py, function health_state() (~line 533).

Currently it adds openvino metadata when TTS_BACKEND == "openvino".

Add:

- When TTS_BACKEND == "pocket_tts":
  - base["pocket_tts"] = {
      "backend": "pocket_tts",
      "model": "pocket_tts",
      "language": os.getenv("POCKET_TTS_LANGUAGE", "english"),
      "runtime_wired": True,
    }

Ensure:

- base["backend"] already reflects TTS_BACKEND (it does).

3.2.7. runtime_config_state: Expose Pocket TTS knobs as live fields

File: src/qwen3_tts/model.py, function runtime_config_state() (~line 647).

Goal: Make Pocket TTS generation parameters tunable via /runtime/config while
TTS_BACKEND=pocket_tts, without requiring container restart.

New live keys (added when TTS_BACKEND == "pocket_tts"):

- POCKET_TTS_TEMP: float, default 0.7
- POCKET_TTS_LSD_DECODE_STEPS: int, default 1
- POCKET_TTS_EOS_THRESHOLD: float, default -4.0
- POCKET_TTS_NOISE_CLAMP: float | null, default null
- POCKET_TTS_FRAMES_AFTER_EOS: int | null, default null

Behavior:

- In runtime_config_state():
  - If TTS_BACKEND == "pocket_tts":
    - Include these keys in the "live" dict:
      - Read current values from os.environ (with defaults) or module-level vars.
  - If TTS_BACKEND != "pocket_tts":
    - Either omit them or mark them in a "not_live" section; omit is preferred.

- In apply_runtime_config(updates):
  - Add these keys to LIVE_RUNTIME_KEYS (conditionally: safe to always allow).
  - If any of them change:
    - When TTS_BACKEND == "pocket_tts":
      - Treat as needing reload:
        - force_unload()
        - load_model(active_profile) (it will pick up new env vars / knobs)
        - _voice_clone_prompt_cache.clear()
    - When TTS_BACKEND != "pocket_tts":
      - Silently store them for when Pocket TTS is loaded next, no reload.

In load_model (pocket_tts branch):

- Read these from os.environ:
  - POCKET_TTS_TEMP
  - POCKET_TTS_LSD_DECODE_STEPS
  - POCKET_TTS_EOS_THRESHOLD
  - POCKET_TTS_NOISE_CLAMP
  - POCKET_TTS_FRAMES_AFTER_EOS
- Pass them into load_pocket_tts_model or as session-level parameters
  (Pocket TTS bakes some into the model instance at load_model).
- Where Pocket TTS does not support live changes (e.g., temp may be per-request
  in some APIs), we:
  - Either adjust via /runtime/config + reload
  - Or, if Pocket TTS allows per-request overrides, we store and apply them in
    generate_pocket_tts instead of reloading.

Design choice:

- For initial implementation: use reload for any change.
- Pocket TTS is small/fast to load, so brief reload is acceptable.
- Later, if Pocket TTS API allows per-request control, switch to no-reload
  for those keys.

### 3.3. Dockerfile: Add pocket-tts dependency

File: Dockerfile

After existing OpenVINO+export install (around line 81–82), add:

- Create requirements/requirements-pocket-tts.txt with content:
  - pocket-tts==2.1.0   (pin the latest stable; confirm with AGENTS when implementing)

- In Dockerfile after line 82:

  - RUN python -m pip install -r requirements/requirements-pocket-tts.txt

Constraints:

- Must use same CPU-only Torch:
  - The existing Dockerfile installs torch CPU first.
  - pocket-tts depends on PyTorch >= 2.5. Our torch==2.12.1+cpu satisfies this.
  - pocket-tts install should not pull CUDA wheels (ensure using the CPU index or confirm).
  - If pocket-tts tries to install a GPU torch, we may need:
    - --constraint or --no-deps + explicit torch pins.
    - Validate during image build.

No other Dockerfile changes are required.

### 3.4. Frontend: Add Pocket TTS + knobs to RuntimeConfigPage

File: frontend/src/pages/RuntimeConfigPage.tsx

Backend dropdown:

- Current: openvino, pytorch
- Add:
  - <SelectItem value="pocket_tts">pocket_tts (small, fast, experimental)</SelectItem>

Conditional Pocket TTS knobs:

- When draft.TTS_BACKEND === "pocket_tts", show an additional collapsible section
  titled something like "Pocket TTS generation tuning" with:
  - A brief note at the top:
    - "These settings affect how Pocket TTS generates audio. Changing them will briefly
      reload the model. Use the Speak tab to compare quality after each change."

  - Temperature:
    - type="number", step=0.1, min=0.1, max=2.0
    - default 0.7
    - bound to draft.POCKET_TTS_TEMP
    - Tooltip/hint:
      - "Controls expressiveness vs stability. Lower (0.3–0.5) = more consistent, safer
        but monotone. Higher (0.9–1.2) = more natural variation but risk of artifacts."
      - "Test: generate the same sentence with 0.4 vs 1.0 and compare."

  - LSD decode steps:
    - type="number", min=1, max=10
    - default 1
    - bound to draft.POCKET_TTS_LSD_DECODE_STEPS
    - Tooltip/hint:
      - "Number of refinement steps per audio frame. More steps = higher quality, slower.
        Pocket TTS is fast, so 2–5 is a reasonable range for testing."
      - "Test: compare 1 vs 3 vs 5 on a longer sentence for clarity and smoothness."

  - EOS threshold:
    - type="number", step=0.1, min=-10, max=0
    - default -4.0
    - bound to draft.POCKET_TTS_EOS_THRESHOLD
    - Tooltip/hint:
      - "Controls when generation decides it is done. Smaller (more negative) = longer
        audio, but may include extra tail noise. Less negative (e.g. -2.5) = earlier stop,
        risk of cutting off last word."
      - "Test: use -3.0 and -5.0; check for early cutoff vs trailing noise."

  - Noise clamp (optional):
    - type="number", step=0.1, min=0.1, max=10
    - default empty/None
    - bound to draft.POCKET_TTS_NOISE_CLAMP (null when empty)
    - Tooltip/hint:
      - "Caps the magnitude of injected noise during generation. Leaving it empty is
        recommended. Lower values can reduce harsh artifacts but may make speech flatter.
        Use only if you hear obvious noise issues."
      - "Test: if default sounds noisy, try 1.0–2.0 and compare."

  - Frames after EOS (optional):
    - type="number", min=0
    - default empty/None
    - bound to draft.POCKET_TTS_FRAMES_AFTER_EOS (null when empty)
    - Tooltip/hint:
      - "Number of 80ms frames to keep after end-of-speech. Useful to reduce abrupt cut
        off. Leave empty to auto-calculate based on text length. Increase only if speech
        sounds cut too early."
      - "Test: if the last word is clipped, try 2–4."

- When changing any of these while backend is pocket_tts:
  - Same "apply" behavior: sends to /runtime/config, triggers a brief reload.
  - Show the existing "Reconfiguration in progress" banner while reloading.

UX note:

- If TTS_BACKEND is not "pocket_tts", hide these fields to keep UI clean.

Do NOT:

- Change SpeakPage, VoiceLibraryPage, or IntegrationsPage behavior.
  The same endpoints are used, same voice selection; backend change is transparent.

### 3.5. Frontend api.ts: Add Pocket TTS knobs to RuntimeConfigState

File: frontend/src/lib/api.ts

Update RuntimeConfigState.live to include:

- TTS_BACKEND: string  (existing; now may be "pocket_tts")
- POCKET_TTS_TEMP: number | undefined
- POCKET_TTS_LSD_DECODE_STEPS: number | undefined
- POCKET_TTS_EOS_THRESHOLD: number | undefined
- POCKET_TTS_NOISE_CLAMP: number | null | undefined
- POCKET_TTS_FRAMES_AFTER_EOS: number | null | undefined

Behavior:

- These are only meaningful when live.TTS_BACKEND === "pocket_tts".
- updateRuntimeConfig will send changed fields as part of the same partial object.
- Keep the backend selector and Pocket TTS knobs as part of the existing draft/apply pattern.

### 3.6. Async, cancel, and streaming endpoints

3.6.1. /generate/async, /generate/progress

- /generate/async currently calls model._run_generate via the executor.
- Because _run_generate will now route to Pocket TTS when TTS_BACKEND == "pocket_tts",
  these endpoints automatically support Pocket TTS without changes.
- Job progress tracking:
  - For Pocket TTS, frames_generated is not incrementally tracked via logits processor.
  - Options:
    - Set frames_generated = estimated_frames before generation
    - Set it from audio length after generation
    - For now: set frames_generated = job.expected_total_frames before generation to
      provide non-zero progress.

3.6.2. /generate/stream

- Today: requires OpenVINO vocoder (line ~1505–1570 in app.py):
  - If vocoder_runtime is None or not enabled -> 503.
- For Pocket TTS, Pocket TTS supports generate_audio_stream().
- Option A (recommended for v1):
  - Leave streaming OpenVINO-only.
  - For pocket_tts backend, /generate/stream returns 503 until streaming is wired.
  - This is acceptable and safer.
- Option B (later):
  - If TTS_BACKEND == "pocket_tts", wire generate_audio_stream into a streaming response.
  - This is out of scope for initial integration.

3.6.3. Cancel behavior

- Pocket TTS does not accept external cancel hooks into its internal loop.
- For v1:
  - Keep the job cancel_event in _run_generate for Pocket TTS.
  - Before starting Pocket TTS generation, check cancel_event.
  - For longer texts, optionally wrap generate_audio in a cancellable thread:
    - If job.cancel_event is set, mark status = "cancelled".
    - But Pocket TTS will likely finish before cancel is noticed (it's fast).
- This is an improvement over nothing and keeps the async/cancel path consistent.

### 3.7. Voice library and per-request voice cloning

The existing voice library (src/qwen3_tts/voice_library.py) stores per-voice:

- wav_path (reference audio)
- sample_text

For Pocket TTS:

- On load (load_model when TTS_BACKEND=pocket_tts):
  - Use REF_AUDIO (from profile.ref_audio) to build default voice_state.
- On /generate with voice_id:
  - get_pocket_tts_voice_state uses the same voice_library.get_voice(voice_id)
    to read wav_path, then calls get_state_for_audio_prompt(wav_path).
  - Cache voice_state in pocket_tts_voice_state_cache.

Notes:

- Pocket TTS's get_state_for_audio_prompt can also take:
  - A .safetensors file
  - A URL
- Future improvement: allow exporting voice library entries to .safetensors for Pocket TTS
  (using pocket_tts.export_model_state) to speed up per-voice load. Out of scope.

### 3.8. REF_TEXT and ASR validation

- Today, for Qwen3-TTS:
  - REF_TEXT is validated via Whisper ASR against REF_AUDIO.
  - Mismatch can cause bad generation.
- Pocket TTS does not consume REF_TEXT (it clones from the audio, not text).
- For TTS_BACKEND=pocket_tts:
  - Skip the Whisper validation (it's expensive and not needed).
  - Still log: "[app_worker] Pocket TTS ignoring REF_TEXT; clones from REF_AUDIO only."

Implementation:

- In load_model, in the pocket_tts branch, do NOT call validate_reference_text.
- Optionally set _ref_text_validation_result to indicate "skipped for Pocket TTS".

### 3.9. Environment variables (new, recommended)

Document these in the plan; do not make them required.

New env vars (read by pocket_tts_runtime and load_model):

- TTS_BACKEND:
  - Existing: "openvino" | "pytorch"
  - New: "pocket_tts"

- POCKET_TTS_LANGUAGE:
  - Description: Language config for Pocket TTS (e.g., "english", "french_24l").
  - Default: "english"

- POCKET_TTS_TEMP:
  - Description: Sampling temperature.
  - Default: "0.7"

- POCKET_TTS_LSD_DECODE_STEPS:
  - Description: Generation steps.
  - Default: "1"

- POCKET_TTS_EOS_THRESHOLD:
  - Description: EOS threshold.
  - Default: "-4.0"

- POCKET_TTS_QUANTIZE:
  - Description: Enable int8 quantization (0/1).
  - Default: "0"

If/when these become runtime-adjustable, they can be wired into /runtime/config later.

### 3.10. AGENTS.md updates (documentary)

After implementation, update AGENTS.md to mention:

- "pocket_tts" as a valid TTS_BACKEND.
- "Pocket TTS" as a small, CPU-optimized alternative model for experimental use.
- New env vars (POCKET_TTS_*) if added.

No architecture invariants need to change:

- Still one image, one process, one model at a time.
- Gunicorn and executor constraints unchanged.

## 4. Implementation Order (for an AI agent)

This sequence minimizes risk and keeps changes focused.

Step 1: Add dependency
- Create requirements/requirements-pocket-tts.txt.
- Update Dockerfile to install pocket-tts.
- Build image and confirm import: python -c "from pocket_tts import TTSModel; print('ok')".

Step 2: Create pocket_tts_runtime.py
- Implement load, unload, generate_pocket_tts, get_pocket_tts_voice_state.
- Use existing PYTHONPATH, same style as other modules.

Step 3: model.py backend validation
- Update both TTS_BACKEND checks (load_model, apply_runtime_config).
- Add "pocket_tts" to allowed values.

Step 4: model.py load_model
- Add pocket_tts branch before Qwen3TTSModel.from_pretrained.
- Wire load_pocket_tts_model, build_default_voice_state.

Step 5: model.py force_unload
- Call pocket_tts_runtime.unload_pocket_tts() unconditionally on unload.

Step 6: model.py _run_generate
- Add TTS_BACKEND == "pocket_tts" branch.
- Use generate_pocket_tts instead of model.generate_voice_clone.
- Keep job tracking, logging, and error handling consistent.
- Skip logits_processor, TTS_DIAG, and max_new_tokens logic for pocket_tts.

Step 7: model.py health_state
- Add pocket_tts metadata block when TTS_BACKEND == "pocket_tts".

Step 8: Frontend
- Add pocket_tts SelectItem to RuntimeConfigPage.tsx.
- Verify backend dropdown sends "pocket_tts" value.

Step 9: Basic tests
- Ensure:
  - GET /runtime/config includes "pocket_tts" as a valid TTS_BACKEND value.
  - POST /runtime/config with {"TTS_BACKEND": "pocket_tts"}:
    - 200, reconfig_in_progress briefly true, then backend="pocket_tts" and service_started true.
- No changes to existing unit tests required if we only extend, never break.

## 5. Validation Checklist

On dockermisc1 or equivalent 15 GiB host:

- Build image with pocket-tts dependency:
  - python -c "from pocket_tts import TTSModel"
  - Confirm torch is CPU-only.

- With REF_AUDIO/REF_TEXT set:

  - Start with TTS_BACKEND=pocket_tts (env var):
    - Health: backend=pocket_tts, model_loaded=true.
    - POST /generate with small text; listen to output.
    - Confirm audio is reasonable (fast, 24kHz).

  - Switch from UI or /runtime/config:
    - openvino -> pocket_tts:
      - Confirm model unloads, Pocket TTS loads, generation works.
    - pocket_tts -> pytorch:
      - Confirm Qwen3TTSModel loads, generation works.
    - pocket_tts -> openvino:
      - Confirm OpenVINO runtime loads, generation works.

  - Use different voice_id:
    - Confirm it clones the selected voice library entry.

  - Confirm memory:
    - Pocket TTS RSS should be much lower than 1.7B OpenVINO or PyTorch backends.

  - Streaming:
    - /generate/stream with pocket_tts -> 503 (for now) is acceptable.

- Confirm:
  - No regressions in existing openvino/pytorch backends.
  - VoiceDesign and OmniVoice still work (they do their own swap).

## 6. Things explicitly NOT changed (to avoid drift)

- Gunicorn config (still -w 1 -k gthread --threads 4, never --preload).
- One-model-at-a-time policy (swap, never co-load).
- /generate, /v1/audio/speech, /generate/async contracts (same JSON in, same audio out).
- OpenVINO runtime, export, quantization pipelines.
- VoiceDesign and OmniVoice engines (only touch if necessary).
- Existing unit and integration tests (only extend).
