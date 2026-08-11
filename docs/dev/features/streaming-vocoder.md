# Plan — streaming / pipelined vocoder decode

Branch: `feat/streaming-vocoder`. Status: **deliverable A works on the real 0.6B model and now has
an experimental HTTP transport; release gates remain open.** Self-contained brief for a fresh agent.
Design context: `../architecture/OPENVINO_IMPLEMENTATION.md` § "Milestone 1.5" and § "Streaming vocoder delivery".
Measured numbers: `../benchmarks/OPENVINO_RESULTS.md`.

> `main` is released as v0.12.0 at `9bf0848`. This track is independent of the already-merged
> stateful-KV feature. Do not change cache behavior while finishing streaming.

## Implementation progress / resume point

Verified on 2026-06-30 after rebasing onto released `main` commit `9bf0848`; corrected runtime/test
commit: `8f6b862`:

- `OpenVinoVocoderRuntime.iter_decode_chunks(codes)` now exposes the existing 300-frame / 25-frame
  left-context boundary as an iterator of cropped float32 PCM chunks.
- `_decode_codes_tensor` consumes that iterator, so the existing batch API and waveform assembly use
  the same path that future streaming transport will use.
- Code normalization no longer imports Torch just to recognize a tensor; Torch-like inputs and numpy
  inputs share the same `[frames, quantizers]` validation.
- `tests/test_ov_vocoder_runtime.py` covers empty, single-chunk, exact-boundary, multi-chunk, chunk-size,
  and wrong-quantizer cases. Concatenated iterator output equals batch output exactly in the deterministic
  model-free harness.
- `StreamingVocoderSession` hooks the **outer** `Qwen3TTSTalkerForConditionalGeneration.forward` result,
  where `hidden_states[-1]` is the completed `[batch, 16]` codec frame. It preserves the inspected forward
  signature, ignores prefill (`codec_ids=None`), skips EOS, and always restores the method.
- Voice-clone reference codes are prepended before every prefix decode. This is required for waveform
  parity because stock `generate_voice_clone` decodes reference + generated codes and then cuts the
  reference samples.
- Prefix decode occurs only when total reference + generated frames cross 300, 600, ... and once for the
  final partial prefix. The abandoned local implementation decoded every prefix after frame 300 and hooked
  the inner transformer hidden state; both errors are now removed.
- `/infer_stream` and public `/generate/stream` emit headerless mono `f32le` PCM using HTTP chunked transfer.
  Existing `/infer` and `/generate` remain batch WAV/MP3 paths. Mid-stream failure semantics are an abrupt
  connection close; clients must treat partial PCM explicitly.
- The streaming path reuses its final decoded prefix when upstream calls `speech_tokenizer.decode`, avoiding
  a duplicate terminal vocoder pass.
- Model-free session + iterator tests pass. Public proxy tests pass inside `runtime-v0.12.0`.
- Real 0.6B short parity: 23 generated frames, max_abs 0, SNR infinite. Terminal-decode reuse also passed:
  24 frames, max_abs 0, SNR infinite, 14.62 s total.
- Real 0.6B paragraph: 160 reference + 194 generated frames, boundaries `300,354`, two emitted chunks,
  first audio 39.34 s versus 90.84 s terminal completion, max_abs 0, SNR infinite.
- 0.6B container CPU during that paragraph averaged ~500% on 8 vCPUs (432–546%). This shows aggregate
  headroom but is not yet the phase-separated go/no-go result for concurrent vocoder overlap.
- The persisted 1.7B INT4/BF16 profile is now exercised with capacity-768 stateful main, explicit
  predictor, and FP32 vocoder. Paragraph streaming crossed boundaries 300/333, delivered first audio
  at 50.95 s, completed at 81.06 s with final-prefix reuse, and matched batch PCM exactly. Aggregate
  CPU averaged ~470% of 800%; per-core/phase separation and human seam listening remain open.

Still open before release:

1. Run a baked-image test of `/generate/stream` on the first official release image that includes the
   streaming runtime (completed for `runtime-v0.13.0`; 0.6B INT8 profile on dockermisc1: HTTP 200,
   headers correct, short and paragraph tests pass, internal parity max_abs=0).
2. Repeat the paragraph gate with terminal-decode reuse enabled and record baseline batch wall time using
   identical seeds. The existing 90.84 s diagnostic intentionally included a duplicate stock decode.
3. Run phase-separated per-core CPU profiling for 0.6B and 1.7B. Do not implement overlap from aggregate
   `docker stats` alone.
4. Run a boundary listening A/B using the saved two-chunk paragraph PCM converted outside Git. Exact sample
   parity strongly de-risks seams but does not replace listening.
5. Verify serialized batch-after-stream, stream-after-batch, client disconnect cleanup, timeout behavior,
   and a fresh-process `TTS_BACKEND=pytorch` rollback. Streaming correctly returns 503 without OV vocoder.
6. Decide whether the raw PCM contract is sufficient for release or whether a documented client helper is
   required. Do not label raw bytes as WAV.

## Read this first: what is and isn't true about the vocoder

The vocoder is **already chunked.** `Qwen3TTSTokenizerV2Decoder.chunked_decode` runs a Python loop with
`chunk_size=300, left_context_size=25` and calls the per-chunk `Decoder.forward` graph (exported as a
fixed `[1, 16, 325]` IR: 300 chunk frames + 25 left-context, right-padded). It is a 114M-param conv/GAN,
**no KV cache, no autoregression**. Two consequences that reshape this plan:

- **There is NO meaningful memory win here.** M9 measured the vocoder at **~6–12 MiB** of peak — the
  per-chunk buffer is already bounded. *Do not pursue this as a footprint lever; that prize is already
  banked.* (Earlier handoff notes that framed streaming as "capping the single-shot decode buffer" were
  wrong — there is no single-shot decode; it's already a chunk loop.)
- The lever that remains is **latency / UX**, via two distinct (separable) deliverables below.

## The two deliverables (separable — ship either)

### A. Streaming output — time-to-first-audio (implemented, release gates open)
The batch flow remains **generate all audio codes → run `chunked_decode` → return complete WAV/MP3**.
The opt-in path decodes and emits when reference + generated codes reach each 300-frame boundary.
The validated prompt has 160 reference frames, so its first boundary requires 140 generated frames
(~11.7 s of audio), not 300 generated frames. The paragraph run delivered first audio 51.5 s before
terminal completion. This is a TTFB/UX win; vocoder work still runs synchronously with generation.

### B. Pipelined overlap — wall-clock latency (the uncertain win)
Run vocoder chunk N's decode **concurrently** with the talker generating chunk N+1's codes, so the
~29% vocoder wall time hides under generation time instead of adding to it.

**Honest caveat — finish measuring before building.** This box is **8 vCPU and CPU-bound.** Overlapping two
compute-bound stages only reduces wall time if generation leaves **idle cores** the vocoder can use. The
autoregressive talker loop (each token depends on the previous; the predictor runs ~15 *sequential*
forwards per frame) plausibly *does* leave headroom — sequential dependencies often underuse a wide CPU.
Aggregate 0.6B paragraph utilization averaged ~500% of 800%, which is encouraging but is not a
phase-separated result. If generation saturates all 8 cores, pipelining just time-slices
and yields ~0 wall-clock gain (you'd still get deliverable A's TTFB benefit). **Gate B on a measurement,
not a hope.**

## Step 0 — the go/no-go measurement for deliverable B (partially complete)

Before writing any pipeline code, answer: *is there CPU headroom during talker generation?*
- Run a normal 1.7B (and 0.6B) generation and sample per-core utilization (e.g. `mpstat -P ALL 1`,
  or `psutil.cpu_percent(percpu=True)` inside the worker) across the autoregressive loop, separated
  from the vocoder phase.
- **If mean utilization during generation is well below 100% × ncores** → headroom exists → deliverable
  B is worth building. **If it's pegged near saturation** → skip B, ship only A (streaming TTFB), and
  record the negative result in `../benchmarks/OPENVINO_RESULTS.md`.

## Design (reuse, don't re-export)

- **No graph change.** The per-chunk `[1, 16, 325]` IR is exactly the streaming unit. Reuse it as-is.
- **Reuse `chunked_decode`'s seam handling.** The `left_context_size=25` overlap is what prevents
  conv-receptive-field seam artifacts at chunk boundaries. Any streaming/pipeline loop **must carry the
  same left context** between chunks. Do not reinvent the windowing — lift the existing crop/overlap math
  (the stock loop already crops `actual_frames * 1920` and applies the left-context crop). Re-validate
  bit-parity of the streamed concatenation vs. the one-shot `chunked_decode` output (should be ~0 error,
  since it's the same graph + same chunks).
- **Producer/consumer for B.** A bounded queue between the generation loop (producer of code chunks) and
  a vocoder worker thread (consumer). The OV vocoder `InferRequest` is single-threaded per request;
  give the vocoder its own `InferRequest` so it doesn't contend with the talker cores' requests. Tune
  OV thread counts so the two stages split cores deliberately rather than both grabbing all 8.
- **Streaming transport for A.** `/generate/stream` proxies `/infer_stream` using HTTP chunked transfer.
  The payload is headerless mono float32 little-endian PCM; headers declare `f32le`, 24 kHz, and one
  channel. **Keep the existing batch endpoints unchanged.** A mid-stream error closes the connection
  because raw PCM has no control frame. Do not label these bytes as WAV.

## Steps

0. **CPU-headroom measurement — partial.** Aggregate 0.6B and 1.7B data exists; per-core phase
   separation remains before deciding whether B is in scope.
1. **Pull the chunk boundary out of `chunked_decode` — complete.** The generation loop can hand
   completed code chunks (with left context) to the vocoder incrementally, instead of one terminal call.
   Verify streamed-concat output is bit-parity with the current one-shot path.
2. **Deliverable A — implemented, not release-complete.** `/generate/stream` exists and batch endpoints
   are untouched. Target producer/worker transport parity passed; baked-image, live public proxy,
   listening, disconnect, concurrency, and rollback gates remain.
3. **Deliverable B — overlap** (only if step 0 showed headroom). Producer/consumer thread + dedicated
   vocoder `InferRequest` + OV thread split. Measure warm **end-to-end** wall time vs. serial baseline.
4. **Quality/parity gate.** Listening A/B of streamed vs. batch output — confirm **no seam artifacts**
   at chunk boundaries (this is the main quality risk). Re-confirm FP32 SNR ≥ 40 dB still holds on the
   concatenated waveform.
5. **Concurrency + rollback.** The service is single-worker/serialized — confirm streaming doesn't break
   that invariant. Confirm batch endpoints + `TTS_BACKEND=pytorch` rollback are untouched.

## Risks / guardrails

- **Seam artifacts** are the #1 quality risk — preserve the stock left-context overlap exactly; gate on a
  listening A/B.
- **Thread contention** on 8 cores can erase deliverable B's win — that's why step 0 gates it. Split OV
  threads between stages explicitly; don't let both default to all cores.
- **Streaming error semantics:** a mid-stream generation failure closes the connection after any bytes
  already sent. Clients must explicitly discard or retain truncated raw PCM; batch remains atomic.
- **Box hygiene (carried):** never blanket `docker kill`/`prune` (took down `litellm*`/`headroom-proxy`);
  touch only `persona-forge`. Never two `--memory 13g` jobs at once. One backend per process for benchmarks.
- **Don't re-litigate INT8 vocoder** — rejected at 16.3 dB (M1.5). This track keeps the FP32 IR.

## Decision gate

- **Ship A (streaming TTFB)** if it cuts time-to-first-audio with no seam artifacts — high-confidence,
  recommend pursuing regardless of B.
- **Ship B (overlap)** only if step 0 showed CPU headroom *and* measured warm end-to-end improves with
  no regression. If the box is saturated, record the null result and stop — A still stands alone.
- This is the **last material optimization frontier** in the project (the only untouched ~29%). After
  this, the OpenVINO backend is feature-complete across both sizes.

## Logging and telemetry (from validation runs, recommended)

From actual validation runs on dockermisc1, these gaps were observed. Recommended but not blockers:

- No container logs during streaming for:
  - start of streaming request;
  - chunk boundary crossings;
  - total frames, chunks, elapsed time;
  - whether terminal-decode reuse was used;
  - restoration of talker.forward.
- Internal parity headers (X-Streaming-*) are visible but not logged to container logs. For production
  monitoring, log:
  - "streaming started: text_len=N"
  - "streaming chunk emitted at boundary {total_frames}"
  - "streaming completed: {frames} gen, {chunks} chunks, {elapsed}s"
  - "streaming reused final decode" or "streaming final decode not reused"
- For debugging:
  - log when StreamingVocoderSession hooks talker.forward
  - log when it restores it (success or failure)
  - log when it skips a chunk (no ready frames)
- "Setting pad_token_id" warning from Transformers appears once per streaming request; harmless but
  confusing; consider filtering in production logs.
