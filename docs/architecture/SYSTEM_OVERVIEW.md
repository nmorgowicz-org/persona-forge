# System Overview

One-paragraph summary:

This system is a single-process, single-image TTS service for running voice-clone speech synthesis on Intel CPUs with OpenVINO acceleration. Its core capabilities are: (1) reference-based voice cloning via a Qwen3-TTS Base checkpoint; (2) programmatic voice creation from a text description using a VoiceDesign checkpoint; (3) accent/tone design and multi-segment auditioning via a separate OmniVoice checkpoint; and (4) segment-level editing (stitching, trimming, loudness, compression) so individual takes can be assembled into a reusable reference voice. Only one model is resident in memory at any time; swaps between Base, VoiceDesign, and OmniVoice are serialized and guarded. The service is wrapped in a Flask API with an optional React frontend (Persona Forge Studio) served from the same container.

High-level component diagram:

    +-------------------------------------------------------+
    |                     Container (1 image)               |
    |                                                       |
    |  +----------+    +----------------+    +------------+  |
    |  | Flask    |    | Model runtime  |    | OpenVINO   |  |
    |  | app.py   |----| model.py       |----| adapters   |  |
    |  +----------+    +----------------+    +------------+  |
    |       |                  |                      |       |
    |       |                  +----------------------+       |
    |       |                         |                      |
    |       v                         v                      |
    |  +----------+    +----------------+    +------------+  |
    |  | Frontend |    | voice_design   |    | Omnivoice  |  |
    |  | (SPA)    |    | (swap mgmt)    |    | engine     |  |
    |  +----------+    +----------------+    +------------+  |
    |       |                                           |    |
    |       |      +----------------+    +-------------+|    |
    |       +----->| voice_library  |    | segment_lib ||    |
    |              +----------------+    +-------------+|    |
    |                         |                |        |    |
    |                         +----------------+        |    |
    +-------------------------------------------------------+
                   |
            /export, /generate, /v1/audio/speech,
            /omnivoice/*, /voices, etc.

Key components:

- Flask app (src/persona_forge/app.py):
  - Single Gunicorn worker, -w 1 -k gthread --threads 4.
  - Provides all REST endpoints and optional SPA.
  - Never spawns a second inference worker; all heavy operations are submitted through model.executor.

- Model runtime (src/persona_forge/model.py):
  - Owns the single shared ThreadPoolExecutor(max_workers=1) that serializes all inference and swaps.
  - Manages loading/unloading Base and VoiceDesign checkpoints, idle unload, and Base-priority swap-back via _ensure_base_loaded().
  - Forwards to OpenVINO adapters when TTS_BACKEND=openvino.

- OpenVINO adapters (src/persona_forge/openvino/):
  - OVTalkerRuntime swaps the two transformer core forwards (main talker, code predictor) for OpenVINO IRs.
  - Uses persistent InferRequest objects; no per-token / per-request creation.
  - FP32 vocoder acceleration is wired via vocoder_runtime if an OV vocoder is exported.

- VoiceDesign engine (src/persona_forge/voice_design.py):
  - Swaps to a second checkpoint (VoiceDesign) to synthesize a sample from a textual description.
  - Leaves VoiceDesign loaded after success; next /generate reloads Base lazily.

- OmniVoice engine (src/persona_forge/omnivoice_engine.py):
  - Swaps in the OmniVoice checkpoint (k2-fsa/OmniVoice) to generate multiple candidates per segment.
  - Left loaded after success; unloaded only when Base is required, another engine is swapped in, or idle-unload fires.

- Frontend (frontend/):
  - React SPA served from /app/frontend/dist (build via npm).
  - Persona Forge Studio (VoiceDesign + OmniVoice accent design + stitch editor).
  - Auto-disables if FRONTEND_ENABLED=0 or dist directory is missing; app remains a pure API service.

- Voice library (src/persona_forge/voice_library.py):
  - Persists reference voices as WAV+JSON on disk (VOICE_LIBRARY_PATH_CONTAINER).
  - Used by /generate, /v1/audio/speech, and Persona Forge.

- Segment library (src/persona_forge/segment_library.py):
  - Persists individual OmniVoice audition candidates that were “locked in.”
  - Used by the stitch editor to mix takes across sessions.

Core request flows

1) Primary TTS: /generate and /v1/audio/speech

   - Guard: _generation_ready() → service_started && !reconfig_in_progress().
     During a swap, does NOT return 503; instead the request is queued behind
     the swap on model.executor so it runs once Base is restored.
   - Submit model._run_generate via model.executor.
   - _run_generate:
     - calls _ensure_base_loaded() if Base is not currently active.
     - resolves voice_clone_prompt (startup default or voice_id-based prompt).
     - runs model.generate_voice_clone (PyTorch or OpenVINO-accelerated).
     - trims leading/trailing silence.
   - /generate returns MP3/WAV; /v1/audio/speech returns OpenAI-style envelope.
   - /generate/stream uses an incremental vocoder path for PCM streaming.

2) VoiceDesign (Persona Forge → “Design a voice”):

   - POST /voice_design with {description, sample_text, language, seed?}
   - Swaps Base → VoiceDesign in model.executor:
     - unload_foreign_models()
     - force_unload()
     - load_model(VOICE_DESIGN_PROFILE)
   - Calls generate_voice_design(description as instruct).
   - Leaves VoiceDesign loaded.
   - Frontend polls GET /voice_design/progress while in flight.

3) OmniVoice audition:

   - POST /omnivoice/audition with {segments[], instruct, language, candidates_per_segment, ...}.
   - If model._service_started: runs immediately.
     If not: job gets status "queued"; dispatcher waits on service_started,
     then dispatches FIFO via model.executor.
   - Inside run_omnivoice_job:
     - Swaps Base → OmniVoice (in model.executor).
     - For each segment x candidate:
       - Generates audio.
       - Runs analyze_take + transcript match.
       - Callback updates job state per-candidate; frontend polls:
         GET /omnivoice/audition/progress?job_id=...
   - Leaves OmniVoice loaded.
   - Candidates are ephemeral (in-memory _omnivoice_candidates) until locked in.

4) Segment lock-in and stitch:

   - POST /omnivoice/segments:
     - Takes a candidate_id, text, instruct.
     - Persists that candidate as a segment in segment_library (on disk).
   - GET /omnivoice/segments lists segments.
   - POST /omnivoice/stitch:
     - Accepts segment_ids, candidate_ids, or voice_ids.
     - Applies optional stitch_plan (trims, fades, padding, crossfade, compression).
     - Returns stitched WAV without touching model; pure numpy post-processing.
   - POST /omnivoice/save:
     - Same as stitch, but persists result into voice_library as a reference voice.
     - The saved voice becomes usable anywhere (Speak page, /generate, /v1/audio/speech).

One-model-at-a-time rule

- The service holds exactly one primary model in memory:
  - Base (for cloning), VoiceDesign (for descriptive voice creation), or
    OmniVoice (for accent/tone audition).
- Rationale:
  - Each model is several gigabytes; co-residency on a 15 GiB host causes OOM or swap thrash.
  - model.py’s globals (model, ov_runtime, voice_clone_prompt, etc.) assume a single active checkpoint.
- Behavior:
  - Any transition between engines unloads the current model before loading the next.
  - All load/unload operations run inside model.executor so no inference can race the swap.
  - /generate and /v1/audio/speech rely on _ensure_base_loaded() to lazily restore Base
    if another engine is resident.

Volume layout

- Model cache:
  - Environment: MODEL_CACHE_PATH / MODEL_CACHE_CONTAINER_PATH.
  - Typical: /root/.cache/huggingface/hub.
  - Holds HF checkpoint files and downloaded weights.
  - Mounted so containers avoid re-downloading.

- OpenVINO IR/cache:
  - IR directory: OV_MODEL_DIR (e.g. /openvino/ir).
  - Kernel cache: /ov/cache (OV compile_model cache).
  - Both mounted persistently; kernel cache alone saves 60–120s per restart.

- Voice library:
  - Path: VOICE_LIBRARY_PATH_CONTAINER (default /voices).
  - Contains:
    - voices/<voice_id>/meta.json
    - voices/<voice_id>/reference.wav
  - Read/written by voice_library module and used by both the Speak page and Persona Forge.

- Segment library:
  - Path: SEGMENT_LIBRARY_PATH_CONTAINER (default /segments).
  - Contains:
    - segments/<segment_id>/meta.json
    - segments/<segment_id>/audio.wav
  - Written by segment_library when candidates are locked in via /omnivoice/segments.
  - Used by the stitch editor to mix across sessions.

Where to look next

- OPENVINO_IMPLEMENTATION.md:
  - How OpenVINO acceleration works end-to-end; IR export, quantization,
    stateful vs explicit cache, vocoder wiring, memory profile.
- TRANSFORMERS_COMPAT.md:
  - Required patches for running on top of transformers 5.x and qwen-tts.
- RUNTIME_AND_MEMORY.md:
  - LOW_RAM_MODE, malloc tuning, idle-unload, RSS policy.
- EXPORT_SYSTEM.md:
  - How the export tooling validates, compresses, and tags IRs.
- voice_design.md:
  - Frontend architecture, security posture, runtime config panel,
    Persona Forge Studio workflows.
