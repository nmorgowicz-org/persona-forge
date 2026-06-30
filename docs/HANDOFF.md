# Handoff — streaming vocoder (2026-06-30)

This is the active resume document for `feat/streaming-vocoder`. Read
`PLAN_STREAMING_VOCODER.md`, the "Streaming vocoder delivery" section of
`OPENVINO_IMPLEMENTATION.md`, the top of `OPENVINO_RESULTS.md`, and `HOW_TO_RUN.md` before editing
runtime code or starting a target container.

## Source and artifact provenance

- Base/released main: `9bf0848` (`v0.12.0`).
- Branch: `feat/streaming-vocoder`; corrected streaming runtime/test commit `8f6b862`; BF16 serving
  loader fix `68e58b2`. Use `git log -5` and `git status --short --branch` before resuming.
- Target test image: `runtime-v0.12.0`, digest
  `sha256:214eb114859e71d36ff19175d40c332124dfc0249dd6df27034101f7694e687b`.
- Target tests mounted branch files over `/app`; no image containing this branch has been built.
- Model: `Qwen/Qwen3-TTS-12Hz-0.6B-Base` at revision
  `5d83992436eae1d760afd27aff78a71d676296fc`.
- Explicit IR metadata file SHA-256:
  `abec65a5d2f2dcf07382d707513cb2a9f5c2a4c5872728069b169d9601e3da7f`;
  metadata `source_hash=dd8e1a75b4ef2174`; OpenVINO 2026.2.1.
- Runtime graphs: capacity-768 stateful main, capacity-32 stateful predictor, FP32 OpenVINO
  vocoder, 6 threads, 8 GiB cgroup. The test log labeled stateful core compression from runtime
  selection metadata; the selected filenames were the validated `*_stateful_int8_*` artifacts.
- Production `qwen3-tts` was stopped during the earlier streaming target runs. At the latest
  2026-06-30 inspection it was running again as image `docker-qwen3-tts`, default FP32 PyTorch path,
  7 GiB limit, ~3.3 GiB idle. It was not stopped for the BF16 follow-up; no second model was started.

## What is implemented

1. `ov_vocoder_runtime.py`
   - `iter_decode_chunks(codes)` is the single 300-frame / 25-left-context decode seam.
   - Batch decode consumes the iterator.
   - `sample_rate` exposes the patched decode contract to the streaming transport.
2. `streaming_vocoder.py`
   - Hooks the **outer** talker forward, preserving its inspected signature.
   - Captures complete 16-codebook frames from `result.hidden_states[-1]`.
   - Ignores prefill, skips EOS, includes voice-clone reference codes, and supports batch size 1.
   - Decodes only at new 300-frame total-prefix boundaries and one final partial boundary.
   - Emits only new generated samples and validates exactly 1920 samples per codec frame.
   - Restores the patched forward on success or failure and suppresses a final flush after failure.
3. `app_worker.py`
   - `/stream_internal` is the same-generation parity/timing harness.
   - `/infer_stream` queues headerless mono `f32le` PCM into an HTTP chunked response.
   - The streaming path reuses its final decoded prefix when upstream calls
     `speech_tokenizer.decode`; this avoids a duplicate terminal vocoder inference.
   - Streaming returns 503 when the FP32 OpenVINO vocoder is unavailable.
   - Existing `/infer` behavior is unchanged.
4. `app_api.py`
   - `/generate/stream` proxies the worker stream and forwards the PCM contract headers.
   - Existing `/generate` and `/health` behavior is unchanged.
5. `Dockerfile`
   - Copies `streaming_vocoder.py` into runtime/exporter images.
6. Tests
   - `tests/test_streaming_vocoder.py` covers reference context, exact boundaries, final partial,
     EOS, forward signature/restoration, malformed shapes, and failed generation.
   - `tests/test_ov_vocoder_runtime.py` covers iterator/batch parity and chunk sizes.
   - `tests/test_app_api.py` covers public proxy streaming and request validation.
7. Serving load configuration
   - `app_worker.py` now honors `OPENVINO_TORCH_DTYPE` and
     `OPENVINO_LOW_CPU_MEM_USAGE`, using the same resolver as `bench_common.py`.
   - `/health` reports `torch_dtype` and `low_cpu_mem_usage`.
   - This closes a reproducibility gap: M9 measured BF16 through the benchmark loader, while the
     serving worker still hard-coded FP32 before commit `68e58b2`.

## Chosen model profiles

- **0.6B:** INT8 asymmetric main/predictor; stateful main capacity 768; stateful predictor capacity
  32; BF16 PyTorch glue; early Torch-layer release; FP32 OV vocoder. Set both per-core compression
  selectors to `int8`. Use 10G/11G for unrestricted paragraph production; 7–8 GiB is only a
  bounded/test option.
- **1.7B:** INT4 asymmetric group-32 layers; stateful main capacity 768; BF16 PyTorch glue; early
  Torch-layer release; FP32 OV vocoder; 10G/11G production limit. The persistent target currently has no 1.7B stateful
  predictor graph, so leave `OPENVINO_PREDICTOR_STATEFUL_MODEL` unset and use the explicit INT4
  predictor. The measured stateful-predictor saving was only ~60 MiB.

## Why the local-model implementation needed correction

Keep this as an architectural guardrail, not as history to re-litigate:

- `talker.model.forward` returns the main transformer hidden state. It does **not** return the
  16-codebook codec frame. The correct seam is outer `talker.forward`.
- Stock voice cloning prepends reference codes before decode and removes their samples afterward.
  Streaming only generated codes cannot match batch audio.
- A prefix must be decoded once at each new 300-frame boundary. Decoding frames 300, 301, 302, ...
  is quadratic duplicate work.
- The final stock `speech_tokenizer.decode` would duplicate vocoder work. The transport path now
  flushes/reuses the session's final prefix while preserving upstream return structure.
- Do not expose generation tuning fields through public `/infer`; they remain internal diagnostics.

## Validation completed

Repository/model-free commands:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest \
  tests.test_model_config tests.test_streaming_vocoder \
  tests.test_ov_vocoder_runtime tests.test_ov_talker_runtime -v
python -m py_compile app_api.py app_worker.py model_config.py bench_common.py \
  streaming_vocoder.py ov_vocoder_runtime.py
PYTHONDONTWRITEBYTECODE=1 python scripts/validate_repo.py
git diff --check
```

Result: 22 targeted tests passed; compile, repository validation, and diff check passed. Full local
discovery cannot import `tests/test_app_api.py` because this Mac lacks Flask. The four app-API tests
passed inside the cached `runtime-v0.12.0` image.

Target results:

- Short parity: 160 reference + 23 generated frames; final boundary 183; max_abs 0; SNR infinite.
- Short with terminal decode reuse: 160 + 24; boundary 184; 14.616 s; max_abs 0; SNR infinite.
- Final smoke from committed `8f6b862`, including terminal-code fail-closed validation: 160 + 32;
  boundary 192; 22.347 s total; max_abs 0; SNR infinite.
- Paragraph (`bench_common.PROMPTS["paragraph"]`, `max_new_tokens=400`): 160 + 194; boundaries
  300 and 354; two chunks; first audio 39.341 s; terminal 90.840 s; max_abs 0; SNR infinite.
  The 90.840 s diagnostic deliberately retained the duplicate stock decode and is not the final
  production latency number.
- Worker `/infer_stream`: live HTTP chunked response, `f32le`, 24 kHz mono; short request delivered
  184,320 bytes with curl start-transfer 14.675 s and total 14.675 s.
- Paragraph CPU: 45 aggregate samples, 431.92–546.49%, mean 499.89% of 800%; approximate
  pre-first-audio mean 514.85%, post-first-audio mean 487.92%. This is not phase-separated.
- Paragraph RSS: about 5.97 → 6.33 GiB inside the 8 GiB test cgroup.
- Chosen 0.6B profile after BF16 loader fix: health reported BF16/low-memory loading, main
  stateful-int8 capacity 768, predictor stateful-int8 capacity 32, FP32 OV vocoder. Short parity:
  48 frames, boundary 208, 20.110 s, max_abs 0, infinite SNR; ~4.95 GiB post-request RSS.
- Chosen persisted 1.7B profile: BF16, INT4 g32, stateful main capacity 768, explicit predictor,
  FP32 OV vocoder. Short parity: 42 frames, boundary 202, 23.651 s, max_abs 0, infinite SNR.
- 1.7B paragraph with final-prefix reuse: 173 frames, boundaries 300/333, first audio 50.945 s,
   total 81.061 s, max_abs 0, infinite SNR, aggregate CPU mean 469.94%. Fresh cgroup peak
   8,350,515,200 bytes (~7.78 GiB), no max/OOM/swap events.
- **Memory decision:** 8 GiB is a functional validation minimum with only ~2.8% headroom. Use
   10G memory / 11G memory+swap for unrestricted production 0.6B paragraphs or 1.7B serving.

v0.13.0 baked-image streaming validation (2026-06-30, dockermisc1):

- Image: `runtime-v0.13.0` contains streaming runtime and BF16 loader fix.
- 0.6B INT8 stateful, 10 GiB cgroup:
  - Short phrase streaming: 130560 bytes (5.44 s audio), first_byte=30.31 s, total=30.31 s
    (under 300 frames; audio emitted as burst at completion)
  - Paragraph streaming: 2465280 bytes (25.68 s audio), first_byte=59.98 s, total=161.45 s
    (101.5 s head start on audio delivery)
  - Internal parity: max_abs=0, SNR=inf, reuse_streamed_decode=true
  - Streaming headers correct: f32le, 24kHz, 1ch, connection-close semantics

Non-Git diagnostics on `dockermisc1`:

```text
/tmp/stream_long.wav
/tmp/stream_long_headers.txt
/tmp/stream_cpu.txt
/tmp/stream_reuse.wav
/tmp/stream_reuse_headers.txt
/tmp/infer_stream.f32
/tmp/profile_06_{health,stream}*
/tmp/profile_17_{health,stream,paragraph,reuse,cpu}*
/tmp/ov-streaming-review/
```

No new streaming-seam listening verdict has been recorded. The 1.7B exact-parity candidate is also
copied to `/private/tmp/profile_17_reuse.wav`; listen around 11.2 seconds.

## Exact next tasks, in order

### Task 1 — finish a baked-image/public-proxy smoke test

STATUS: COMPLETE (2026-06-30)

- Baked image: `ghcr.io/nmorgowicz-org/qwen3-tts-openvino:runtime-v0.13.0`
- Profile: 0.6B INT8 stateful (cap-768 main, cap-32 predictor), BF16 glue, FP32 OV vocoder
- Deployed on `dockermisc1` per HOW_TO_RUN.md (no mounted source)
- Results:
  - `/health` ok; worker openvino; `torch_dtype=bfloat16`; `stateful_main=true`, `stateful_predictor=true`
  - Batch WAV: HTTP 200, 43742 bytes
  - Short streaming: HTTP 200, 130560 bytes, headers match contract (f32le, 24kHz, 1ch, connection-close)
  - Paragraph streaming: HTTP 200, 2465280 bytes (25.68 s audio), first_byte=59.98 s, total=161.45 s
    (101.5 s ahead of completion)
  - Internal parity: max_abs=0, SNR=inf, decode reuse=true (14 gen frames, 160 ref frames)
- Existing `/health` remains ready.

### Task 2 — produce an identical-seed latency comparison

1. Add an internal-only seed control to the benchmark harness, not to public `/infer`.
2. Run one warm-up plus at least three measured paragraph requests for:
   - normal batch decode;
   - synchronous streaming with final-prefix reuse.
3. Use identical seeds/text/stateful graphs and record generation frames, audio seconds, first-byte
   time, total wall time, vocoder time, median, p95, RSS, and swap delta.
4. Acceptance: stream/batch generated codes and final PCM agree; streaming does not regress median
   total wall time beyond noise. Update `OPENVINO_RESULTS.md` with raw artifact paths.

### Task 3 — complete the overlap go/no-go measurement

1. Instrument explicit phase labels around autoregressive generation and vocoder inference.
2. Sample **per-core** CPU at 1 s or faster for both 0.6B and 1.7B. Aggregate `docker stats` is not
   enough to approve overlap.
3. Record host load, available RAM, swap, model/IR provenance, and thread settings.
4. Decision:
   - if generation consistently leaves cores idle, prototype a dedicated vocoder request/thread and
     explicit thread split;
   - if generation saturates the host or overlap regresses wall time, stop deliverable B and ship only A.

### Task 4 — quality and transport failure gates

1. Convert saved `f32le` outside Git for listening; compare streamed concatenation against batch at
   the 300-frame seam. Exact sample parity passed, but listening is still required.
2. Test client disconnect before first audio and after first chunk. The producer must finish or abort
   without wedging the single executor; subsequent `/infer` must succeed.
3. Test generation failure before bytes and after a chunk. Confirm documented connection-close
   semantics and no method hook remains installed.
4. Test batch → stream → batch and stream → batch sequences. Confirm serialized access and byte-valid
   batch WAV/MP3 responses.

### Task 5 — model/rollback gates

1. Under a maintenance window, validate commit `68e58b2` for both chosen profiles: health must report
   BF16/low-memory loading, backend provenance must match the expected stateful/precision choices,
   and startup/generation must remain within 8 GiB.
2. Repeat producer parity and transport on 1.7B INT4, capacity-768 stateful main, **explicit INT4
   predictor**, and FP32 vocoder. Run one 300-frame-boundary listening check and phase-separated CPU
   profile; do not repeat the completed INT4-vs-INT8 selection campaign.
3. Start a fresh process with `TTS_BACKEND=pytorch`; verify `/generate`, WAV, MP3, and health. Streaming
   should return 503 because no OV vocoder is active. This is the rollback contract, not a fallback
   streaming implementation.
4. Run Compose validation and both runtime/exporter import smoke tests after the Dockerfile change.

### Task 6 — final documentation and PR

1. Update this handoff, `PLAN_STREAMING_VOCODER.md`, `OPENVINO_IMPLEMENTATION.md`,
   `OPENVINO_RESULTS.md`, `HOW_TO_RUN.md`, and README with final measured status.
2. Keep raw PCM, WAVs, profiles, IR, and model files outside Git.
3. Use a `feat(runtime): ...` PR title and an override block with one Conventional Commit per line,
   for example:

   ```text
   BEGIN_COMMIT_OVERRIDE
   feat(runtime): stream OpenVINO vocoder PCM during generation

   test(runtime): validate streaming code and transport parity

   docs(runtime): record streaming vocoder results and rollback gates
   END_COMMIT_OVERRIDE
   ```

## Artifact paths and host safety

- 0.6B explicit:
  `/var/data/autopirate/qwen3-tts/openvino/qwen-tts-0.1.1_0.6b_5d83992436ea_ov-2026.2.1/`
- 0.6B stateful: same basename plus `_stateful/`.
- 0.6B FP32 vocoder: same basename plus `_vocoder/`.
- 1.7B INT4:
  `/var/data/autopirate/qwen3-tts/openvino/qwen-tts-0.1.1_1.7b_fd4b25438912_ov-2026.2.1_int4g32/`
- 1.7B capacity-768 stateful main:
  `..._int4g32_stateful_spike/main_stateful_int4_cap768.xml`.
- 1.7B FP32 vocoder: corresponding `_vocoder/` directory.
- No persistent 1.7B stateful predictor XML was present at the latest inspection.
- Reference WAV: `/var/data/autopirate/qwen3-tts/voice/voice_A.wav`.

Never run two large model jobs concurrently. Never blanket-stop, kill, or prune Docker. Touch only
the named temporary/qwen service. Keep `litellm`, `litellm-postgres`, `headroom-proxy`, and every
unrelated container untouched.
