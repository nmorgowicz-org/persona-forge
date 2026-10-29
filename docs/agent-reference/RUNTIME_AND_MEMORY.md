# Runtime Invariants and Memory — Agent Reference

> For AI agents and contributors: these are non-negotiable constraints. Violating them causes OOM,
> silent corruption, or hanging processes. If a change conflicts with these, stop and propose
> alternatives explicitly.

## 1. One model in memory at a time (web-worker process)

- `model.py` globals (`model`, `voice_clone_prompt`, `ov_runtime`, etc.) assume exactly one loaded checkpoint
  **in the web-worker process**.
- No multi-tenant or multi-model abstraction exists inside that process.
- Any new endpoint that runs model code in the web worker must:
  - Reuse these globals.
  - Use the existing executor.
  - Never load a second model into the web worker.
- Pack engines (§6) are the only sanctioned way to run another model, and only as a child process.

## 2. Single worker, single executor

- Gunicorn: `-w 1 -k gthread --threads 4`. Never more than 1 worker. Never `--preload`.
- Inference is serialized via `ThreadPoolExecutor(max_workers=1)`.
- All expensive work the web worker does itself (generation, swap, idle unload, per-request voice cloning) must run
  through this executor. Pack-engine work is the one exception and is defined in §6.
- Never create your own thread pool for model work; it will race and OOM.
- The executor is a plain `ThreadPoolExecutor(max_workers=1)` (`model.py`): there is **no priority mechanism**.
  Work submitted to it is first-come, first-served, so a long job delays every later one. Anything that must not
  delay speech requests (for example Compare auto-check, §6) therefore stays out of the executor instead of
  asking for a lower priority.
- These invariants hold regardless of launch surface: `persona-forge serve` (native, POSIX) runs
  the same single-worker Gunicorn command; on Windows it execs single-worker Waitress instead
  (no Gunicorn/`fork()` support there). `bootstrap.apply_env_defaults` applies the same
  LOW_RAM_MODE/malloc-tuning env defaults natively that `scripts/entrypoint.sh` applies in the
  container, so the two surfaces don't drift.

## 3. LOW_RAM_MODE behavior

- When set (`LOW_RAM_MODE=1`):
  - Tunes glibc malloc: `MALLOC_MMAP_THRESHOLD_=65536`, `MALLOC_ARENA_MAX=1`.
  - Sets `IDLE_UNLOAD_SECONDS` default (30 min). On unload, Python calls `malloc_trim(0)`.
  - LD_PRELOAD allocator replacement (jemalloc, tcmalloc) is INCOMPATIBLE with OpenVINO `compile_model()` under transformers 5.x — both caused SIGABRT/SIGSEGV. `libjemalloc2` remains in the image for reference only.

## 4. OPENVINO_RELEASE_TORCH and OPENVINO_KEEP_CODEC_ENCODER

- `OPENVINO_RELEASE_TORCH=1`:
  - Releases PyTorch transformer layers after OV install; one-way, irreversible.
  - Must stay enabled in 1.7B profiles; turning it off can blow memory.
- `OPENVINO_KEEP_CODEC_ENCODER`:
  - Default is 1 (keeps the ~0.3 GiB PyTorch codec encoder resident after startup).
  - Must stay 1 for per-request voice cloning and VoiceDesign's "capture → clone" handoff, since `create_voice_clone_prompt()` requires the encoder. Set to 0 only for single-voice deployments (e.g. Hermes) that never need any `voice_id` besides the startup default, to shave ~0.3 GiB.
  - If 0 and a `voice_id` is requested, return a clear error; do not let it fail with an opaque AttributeError.

## 5. Memory budgets

- 1.7B profiles:
  - Steady serving RSS: ~5.4–6.9 GiB on the validated host.
  - Export needs up to 13 GiB.
- Never run export and serve simultaneously on a 15 GiB host — it will OOM.

## 6. Pack engines (child processes beside the backend)

Optional speech engines (`kitten2`, `phonon-31m`, `kokoro`, `pocket-lite`) are *packs*: they run in their own
process and never load a model into the web worker. Everything below was checked against the code named in
brackets; the product-level design and decisions are in
[`docs/archive/multi-engine-speech/20261023-kokoro_phonon_kittentts2.md`](../archive/multi-engine-speech/20261023-kokoro_phonon_kittentts2.md) §4.3-§4.6.

### 6.1 Ownership and isolation

- The parent owns **one managed adapter per pack engine** and each adapter owns **at most one child process**.
  Adapters are built lazily and cached by id (`speech_engines.get_adapter`, `ADAPTERS`); the child is spawned on
  the first request, explicit Prepare or Re-check, not at app start (`pack_preset_engine.py`, `kitten2_engine.py`).
- The child is a `PackProcess` (`pack_process.py`): newline-delimited JSON over stdin/stdout, **one request in
  flight per worker** (a lock), a `ping` health check at start, a per-request timeout that kills the worker, and a
  kill when a stream is closed early. The command is an argument list, never a shell string, and the environment
  is a copy of the parent's plus the engine's own variables.
- Pack engines run **beside** the active backend. `model.py` never references the engine registry or the
  adapters, so a backend swap, `force_unload()` or `IDLE_UNLOAD_SECONDS` does not touch a pack worker, and a pack
  worker never unloads the backend. `POST /v1/audio/speech` serves a pack engine without switching `TTS_BACKEND`
  (`app.py`: `serving_engine`).
- Dependencies live outside the app: Kitten 2, Phonon and Kokoro each have a private virtualenv created by their
  provisioner; Pocket Lite runs on the application's own interpreter (`pocket_lite_engine.pack_python`). Only the
  provisioner mints the "verified" stamp.
- The §5 memory figures describe the web worker only. A loaded pack worker adds its own memory on top (Kitten 2:
  about 2 GB while loaded, per `docs/api/HTTP_API_REFERENCE.md`).

### 6.2 What serializes pack work (and what does not)

- Pack synthesis and PCM streaming run on the **calling gunicorn/waitress request thread**, not on
  `model.executor`. Concurrent requests to one engine serialize on that adapter's `RLock` and on the worker's
  one-request-in-flight lock; requests to different engines, or to the active backend, can run at the same time.
  Each waiting request occupies one of the process's request threads (`--threads 4` under Gunicorn, §2).
- Explicit **Prepare** is the exception: `voice_prepare.py` submits it to `model.executor`, and the adapter lock
  then serializes it with synthesis. Lazy first-use preparation runs inside the request under the same adapter
  lock and the same validation and cache.
- Pack load, warm-up, idle unload and Re-check run on their own short-lived daemon/timer threads
  (`<engine>-load`, `<engine>-recheck`, `threading.Timer`) and call only the child process. They do not call model
  code in the web worker, so they are not "model work" for the thread-pool rule in §2.
- There is **no second request scheduler** and no queue of pack requests: a request that meets a loading engine
  waits briefly, then gets a retryable 503 (§6.4) instead of queueing.
- There are **no always-on sidecars.** A pack worker exists only between its first use and its idle unload (or a
  crash/kill); nothing is started at boot.

### 6.3 Threads and idle unload

- Native compute threads are allowed in a child, but must be sized explicitly where the default was measured to
  oversubscribe. The Kokoro worker pins ONNX Runtime to `max(1, min(4, os.cpu_count()))` intra-op threads and one
  inter-op thread (`kokoro_worker.py`; its header records RTF 1.4-1.7 by default against 0.64-0.70 pinned on an
  Intel i7-1360P). No other pack worker sets a thread count in code.
- **Idle unload is per engine.** `engine_lifecycle.IdleUnloader` resolves, on every call, an explicit argument,
  then the engine's env var (`KITTEN2_IDLE_UNLOAD_S`, `PHONON_IDLE_UNLOAD_S`, `KOKORO_IDLE_UNLOAD_S`,
  `POCKET_LITE_IDLE_UNLOAD_S`), then the pack manifest field `idle_unload_after`, then the engine default
  (`0` = never). The manifest value is validated as a finite number `>= 0` (`engine_packs.py`) and written by each
  installer: 1800 s for Kitten 2 (a reload re-pays the compile), 600 s for Phonon, Kokoro and Pocket Lite. The
  timer is re-armed after each use. When it fires the adapter closes the child and the state returns to `idle`; the
  next request reloads it. The Phonon/Kokoro/Pocket Lite base adapter skips the unload while a stream is in flight
  (`pack_preset_engine.py`). Unloading does not use `model.executor`.
- The backend's own idle unload is separate: `IDLE_UNLOAD_SECONDS` (§3), run through the executor.

### 6.4 Engine states and the `engine_warming` 503

- Every pack adapter reports one of `idle`, `loading`, `warming`, `ready`, `error` (`engine_lifecycle.LoadTracker`).
  `idle` means installed and not resident (also after an idle unload); `ready` means the worker can serve now.
  `warming` exists only for a worker that answers `load` with `warmup_pending` (Kitten 2's compile; estimate 35 s).
  `GET /engines` returns it as `load_status` with `elapsed_s`, `estimated_s`, `idle_unload_after` and
  `idle_unload_source`.
- A request to an engine that is not ready claims the load (exactly one caller wins; concurrent requests share it),
  waits at most `ENGINE_WARM_WAIT_S` (default 5, `0` never waits, read on every request), then answers
  **`503` with `Retry-After` and error code `engine_warming`**. The load continues in the background. A pack that is
  not installed, or whose load failed, answers 503 without `Retry-After` and without that code
  (`engine_lifecycle.warm_wait_s`, `app._engine_warming_error`).
- An explicit Prepare cannot be retried by a client, so it keeps waiting for a cold engine for up to 600 s and stops
  early when cancelled (`engine_lifecycle.wait_until_ready`).

### 6.5 Compare auto-check

- Auto-check (`compare_autocheck.py`) is not an engine and never enters `model.executor` (there is no priority
  mechanism, §2). It runs on the request thread under a non-blocking lock: one check at a time, a second gets
  `429 busy`.
- Its two models (faster-whisper `tiny.en`, WavLM-SV) are loaded **on demand, from disk only**
  (`local_files_only=True`), and released `AUTOCHECK_IDLE_UNLOAD_SECONDS` (default 120, `0` keeps them) after the
  last check. It reuses the app's already-loaded Whisper when there is one and leaves that instance alone. Whisper
  is capped at two CPU threads. It still shares CPU with speech (the plan records about 16% slower concurrent Pocket
  requests in a worst-case loop).
- The only download is the explicit `POST /compare/auto-check/install`.

### 6.6 Rules for changes

- Do not add a pack path that calls `model.executor` for synthesis or loads a pack's model into the web worker.
- Do not add a pack that starts at boot, or a second scheduler or queue for speech requests.
- A new pack adapter reuses `LoadTracker` and `IdleUnloader`, writes `idle_unload_after` in its manifest and keeps
  load failures as `error` state with a message; it does not raise a retryable error for a failed load.
- Synthesis must never trigger transcription or a download: both are explicit user actions.
