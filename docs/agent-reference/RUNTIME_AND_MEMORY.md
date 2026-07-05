# Runtime Invariants and Memory — Agent Reference

> For AI agents and contributors: these are non-negotiable constraints. Violating them causes OOM,
> silent corruption, or hanging processes. If a change conflicts with these, stop and propose
> alternatives explicitly.

## 1. One model in memory at a time

- `model.py` globals (`model`, `voice_clone_prompt`, `ov_runtime`, etc.) assume exactly one loaded checkpoint.
- No multi-tenant or multi-model abstraction exists.
- Any new endpoint must:
  - Reuse these globals.
  - Use the existing executor.
  - Never load a second model.

## 2. Single worker, single executor

- Gunicorn: `-w 1 -k gthread --threads 4`. Never more than 1 worker. Never `--preload`.
- Inference is serialized via `ThreadPoolExecutor(max_workers=1)`.
- All expensive work (generation, swap, idle unload, per-request voice cloning) must run through this executor.
- Never create your own thread pool for model work; it will race and OOM.

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
