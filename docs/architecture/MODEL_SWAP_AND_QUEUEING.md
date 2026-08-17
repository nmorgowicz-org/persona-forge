# Model Swap and Queueing

This document describes how model loading, swapping, and request queueing are implemented in the Persona Forge service. It is normative: changes to swap or queueing behavior must respect these rules.

The one-model-at-a-time invariant

- The service loads exactly one model into memory at any moment.
- “Model” means:
  - Base checkpoint (voice-clone generation),
  - VoiceDesign checkpoint (descriptive voice creation),
  - or OmniVoice checkpoint (accent/tone audition).
- All three are independent HF models with different sizes and runtimes; loading two at once on a typical 15 GiB host risks OOM or heavy swap.
- model.py’s module-level globals (model, ov_runtime, voice_clone_prompt, active_profile) are written for a single resident model. No design choice may rely on multiple models being concurrently loaded.

Three “slots”

There are three logical model roles:

1) Base:
   - Primary voice-clone model used by /generate, /v1/audio/speech, /generate/stream.
   - Loaded at startup via BASE_PROFILE.
   - Always the “default”; all generation endpoints expect it.

2) VoiceDesign:
   - Separate checkpoint, loaded via VOICE_DESIGN_PROFILE.
   - Used only by POST /voice_design to generate a voice from a textual description.
   - Loaded by voice_design.run_voice_design_request inside model.executor.

3) OmniVoice:
   - Third-party checkpoint (k2-fsa/OmniVoice), managed by omnivoice_engine.py.
   - Used only by POST /omnivoice/audition jobs.
   - Does NOT go through model.load_model() or OVTalkerRuntime; its lifecycle is
     local to omnivoice_engine, but it registers with model.register_foreign_engine()
     so idle-unload and Base swap-back know how to unload it.

Swap protocol

All load/unload operations must:

- Run inside model.executor:
  - A single-threaded ThreadPoolExecutor(max_workers=1).
  - Guarantees no inference or other swap is running concurrently.
- Be idempotent where possible:
  - force_unload safely no-ops when model is None.
  - unload_foreign_models safely iterates registered engines.

Sequence for a Base or VoiceDesign swap (e.g. into VoiceDesign):

1) Ensure no other swap is in progress:
   - app.py endpoints check voice_design.swap_in_progress() and
     omnivoice_engine.swap_in_progress().
2) Inside model.executor:
   - unload_foreign_models(): tells OmniVoice (and future engines) to unload.
   - force_unload():
     - sets model = None, voice_clone_prompt = None, ov_runtime = None.
     - gc.collect() x2 + malloc_trim(0) to return freed heap.
   - load_model(profile):
     - sets environment vars (OV_MODEL_DIR, stateful models, etc.).
     - validates OV metadata if TTS_BACKEND=openvino.
     - loads the checkpoint; repairs RoPE buffers.
     - applies transformers compat patches.
     - installs OVTalkerRuntime if openvino.
     - rebuilds voice_clone_prompt if required.

Sequence for an OmniVoice swap:

1) run_omnivoice_job sets _swap_in_progress = True.
2) Inside model.executor:
   - model.force_unload() unloads Base or VoiceDesign.
3) Loads OmniVoice from_pretrained directly.
4) Performs per-segment, per-candidate generation.
5) Leaves OmniVoice loaded unless an error occurs.

How swap_in_progress guards endpoints

- voice_design.swap_in_progress():
  - True while run_voice_design_request is mid-swap.
  - Causes:
    - POST /voice_design → 503 “VoiceDesign swap already in progress”
    - POST /omnivoice/audition → 503 “Another swap already in progress”
    - POST /runtime/config → 503
- omnivoice_engine.swap_in_progress():
  - True while run_omnivoice_job is mid-swap.
  - Causes:
    - POST /omnivoice/audition → 503 “Another swap already in progress”
    - GET /health: exposes swap_in_progress for the frontend banner.
- model.reconfig_in_progress():
  - True while apply_runtime_config is doing a live reload.
  - Blocks generation-ready endpoints.

Which endpoints 503, queue, or block

- /generate, /v1/audio/speech:
  - Use _generation_ready() → service_started && !reconfig_in_progress().
  - Do NOT fail during swap_in_progress; instead submit to model.executor
    and block (with 480s timeout) until the swap completes and _ensure_base_loaded
    restores Base, then their work runs.
- /generate/stream:
  - Uses _ready() → stricter than _generation_ready: also considers swap_in_progress.
  - Returns 503 if swap_in_progress() or reconfig_in_progress() is True.
- /voice_design:
  - 503 if voice_design.swap_in_progress() is True (another VoiceDesign swap is in flight).
  - Submits run_voice_design_request via model.executor with 300s timeout.
- /omnivoice/audition:
  - 503 if either swap_in_progress is True.
  - If model._service_started:
    - Runs immediately (submits to model.executor).
  - Else:
    - Job is created with status "queued".
    - Enqueued into _OV_AUDITION_QUEUE.
    - Dispatcher thread is spawned (if not already running) to wait for service_started, then dispatch.
- /omnivoice/* (segments, stitch, save, progress):
  - /omnivoice/audition/progress is read-only: returns job state.
  - /omnivoice/segments, /omnivoice/stitch, /omnivoice/save operate on stored audio;
    they do not block on the model, so no 503 for swap.

Lazy swap-back to Base

Behavior:

- When a design engine (VoiceDesign or OmniVoice) finishes its request, it:
  - Leaves itself loaded (to avoid repeated swap costs).
- The next /generate or /v1/audio/speech that needs Base calls _ensure_base_loaded()
  inside model.executor:
  - If Base is already the active_profile and no foreign model is loaded: no-op.
  - Otherwise:
    - unload_foreign_models(): unloads OmniVoice.
    - force_unload(): unloads VoiceDesign or leftover OV runtime.
    - load_model(BASE_PROFILE): restores Base.
- Rationale:
  - Most common usage pattern is: user runs /generate repeatedly; design is occasional.
  - Keeping Base resident avoids reload latency for normal speech.

Audition job queue

Purpose:

- Ensure OmniVoice audition jobs don’t race with model load/unload and can
  tolerate startup cold-starts.

Data structures:

- _OV_AUDITION_JOBS: dict[job_id -> job dict]
  - status: "queued" | "running" | "completed" | "failed"
  - total_segments
  - segments_completed: list of {segment_index, text, candidates}
  - current_segment_index
  - message
  - created_at
  - _params: tuple of all generation params.
- _OV_AUDITION_QUEUE: list[job_id]
  - FIFO queue of jobs waiting for service_started.
- _OV_AUDITION_JOBS_LOCK, _OV_AUDITION_QUEUE_LOCK, _OV_AUDITION_DISPATCH_IN_PROGRESS.

Lifecycle:

1) Job creation (POST /omnivoice/audition):
   - If model._service_started:
     - status = "running", runs immediately (submit to model.executor).
   - Else:
     - status = "queued"; job_id appended to _OV_AUDITION_QUEUE.
     - If !dispatch_in_progress, start daemon thread _dispatch_audition_jobs.

2) Dispatcher thread (_dispatch_audition_jobs):
   - Acquires queue lock; checks dispatch_in_progress; sets it True.
   - While queue not empty:
     - Pop next job_id from _OV_AUDITION_QUEUE (FIFO).
     - If job missing, skip.
     - Call _ensure_service_started(timeout_seconds=900):
       - Blocks until model._service_started or timeout.
       - On timeout: job status → "failed", message: “Service did not become ready in time.”
     - Mark job status → "running".
     - Spawn daemon thread to submit run_omnivoice_job to model.executor with 1800s timeout.
   - Finally: set dispatch_in_progress = False.
   - Only one dispatcher thread runs at a time.

3) Frontend polling:
   - GET /omnivoice/audition/progress?job_id=...
   - Returns job.status, segments_completed, eta, etc.
   - Frontend loops at 1–3s intervals; no SSE or WebSockets.
   - The /omnivoice/audition/progress handler also evicts old jobs (TTL 600s, max 50 jobs).

Rules for changes

Non-negotiable:

- Single worker:
  - Gunicorn: -w 1 -k gthread --threads 4 (never more than one worker).
  - No adding a second inference executor or multi-worker model sharing.
- Single shared executor:
  - model.executor is the only queue for inference and swap.
  - All load_model, force_unload, unload_foreign_models, run_voice_design_request,
    run_omnivoice_job, _run_generate must be submitted through model.executor.
- No shared InferRequests:
  - OpenVINO InferRequests must never be shared across threads or requests.
  - One InferRequest per model/core is created at load time and reused.
- Swaps only in executor:
  - A swap cannot run “off-thread” or in parallel with another swap or inference.
- 503 vs queue behavior:
  - /generate and /v1/audio/speech must not 503 solely because of a swap_in_progress;
    they must queue on the executor.
  - Design/audition endpoints are allowed to 503 on conflicting swaps.
- _ensure_base_loaded must be lazy:
  - Don’t swap back eagerly after every non-Base job; only when Base is needed or
    another engine takes over.

Common pitfalls

- Deadlock from nested locks:
  - app.py uses multiple locks: _OV_AUDITION_JOBS_LOCK, _OV_AUDITION_QUEUE_LOCK.
  - Never acquire a second lock while holding another; never call blocking
    model.executor.submit inside a held lock.
- Concurrent swaps:
  - If two endpoints both attempt a swap (e.g., /voice_design + /omnivoice/audition)
    they must serialize via model.executor. The swap_in_progress() checks avoid
    starting a second one from the HTTP layer, but if you remove those checks, you
    must ensure only one swap task is queued.
- Race: generation vs swap:
  - If you bypass model.executor for model loads/unloads, you risk:
    - _run_generate reading a partially-unloaded model.
    - Overwriting ov_runtime while another token is mid-decode.
- Idle-unload vs in-flight work:
  - _idle_watcher submits _do_unload to model.executor.
  - _do_unload must respect IDLE_UNLOAD_SECONDS and not unload if a request
    is active; otherwise a mid-generate request can see its model vanish.
- OmniVoice job after failure:
  - If run_omnivoice_job fails, it unloads OmniVoice but does not auto-reload Base.
  - The next /generate reloads Base lazily via _ensure_base_loaded(). Any code
    assuming Base is immediately available after an OmniVoice failure is wrong.
