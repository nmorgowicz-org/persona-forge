# Plan — streaming / pipelined vocoder decode

Branch: `feat/streaming-vocoder`. Status: **implementation started; chunk iterator foundation built,
CPU headroom and live streaming not measured.** Self-contained
brief for a fresh agent. Design context: `OPENVINO_IMPLEMENTATION.md` § "Milestone 1.5" (vocoder export)
and § "Milestone 4" (runtime). Numbers: `OPENVINO_RESULTS.md`.

> **v0.11.1 is already shipped.** This is a NEW, independent track — it must stand on its own and not
> assume any in-flight integration work. Do not couple it to the 0.6B footprint branch.

## Implementation progress / resume point

Completed after rebasing onto released `main` commit `9bf0848`:

- `OpenVinoVocoderRuntime.iter_decode_chunks(codes)` now exposes the existing 300-frame / 25-frame
  left-context boundary as an iterator of cropped float32 PCM chunks.
- `_decode_codes_tensor` consumes that iterator, so the existing batch API and waveform assembly use
  the same path that future streaming transport will use.
- Code normalization no longer imports Torch just to recognize a tensor; Torch-like inputs and numpy
  inputs share the same `[frames, quantizers]` validation.
- `tests/test_ov_vocoder_runtime.py` covers empty, single-chunk, exact-boundary, multi-chunk, chunk-size,
  and wrong-quantizer cases. Concatenated iterator output equals batch output exactly in the deterministic
  model-free harness.

**Important limitation:** this does not yet improve TTFB. The current Qwen generation call returns audio
codes only after the complete autoregressive sequence, then calls `speech_tokenizer.decode`. The next
implementation step is to locate/instrument the talker generation loop and emit each completed 300-frame
code block to a callback/queue without changing the existing terminal return structure. Do not add a
`/generate/stream` endpoint until that producer seam can deliver codes before generation completes.

Next actions, in order:

1. Run Step 0 CPU utilization on both 0.6B and 1.7B; record whether overlap deliverable B is viable.
2. Trace the exact point where each full 16-codebook audio frame is appended in the stock talker loop.
3. Add an opt-in callback/iterator adapter there and feed completed 300-frame blocks into
   `iter_decode_chunks`-equivalent incremental state. Preserve terminal batch output for all existing APIs.
4. Only then add transport and TTFB timing. The 300-frame threshold means first audio cannot arrive
   before roughly 24 seconds of generated audio unless a smaller vocoder chunk is separately parity-gated.

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

### A. Streaming output — time-to-first-audio (the certain win)
Today the flow is **generate all audio codes → then run `chunked_decode` over the whole sequence →
return one complete WAV/MP3.** Streaming means: as soon as the talker has produced enough codes for one
vocoder chunk (300 frames ≈ 24 s of audio @ 12 Hz / 1920 samples-per-frame), decode that chunk and
**emit its waveform immediately**, then continue. The user hears audio long before generation finishes.
This is a **TTFB / UX win that does not depend on any CPU-headroom assumption** — it's reordering, not
parallelism. It is the higher-confidence half of this track.

### B. Pipelined overlap — wall-clock latency (the uncertain win)
Run vocoder chunk N's decode **concurrently** with the talker generating chunk N+1's codes, so the
~29% vocoder wall time hides under generation time instead of adding to it.

**Honest caveat — measure before building.** This box is **8 vCPU and CPU-bound.** Overlapping two
compute-bound stages only reduces wall time if generation leaves **idle cores** the vocoder can use. The
autoregressive talker loop (each token depends on the previous; the predictor runs ~15 *sequential*
forwards per frame) plausibly *does* leave headroom — sequential dependencies often underuse a wide CPU
— but this is **unproven here**. If generation already saturates all 8 cores, pipelining just time-slices
and yields ~0 wall-clock gain (you'd still get deliverable A's TTFB benefit). **Gate B on a measurement,
not a hope.**

## Step 0 — the go/no-go measurement for deliverable B (do this FIRST)

Before writing any pipeline code, answer: *is there CPU headroom during talker generation?*
- Run a normal 1.7B (and 0.6B) generation and sample per-core utilization (e.g. `mpstat -P ALL 1`,
  or `psutil.cpu_percent(percpu=True)` inside the worker) across the autoregressive loop, separated
  from the vocoder phase.
- **If mean utilization during generation is well below 100% × ncores** → headroom exists → deliverable
  B is worth building. **If it's pegged near saturation** → skip B, ship only A (streaming TTFB), and
  record the negative result in `OPENVINO_RESULTS.md`.

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
- **Streaming transport for A.** The current `/generate` / `/infer` contract returns a *complete* audio
  body. Streaming needs a chunked-transfer or websocket variant (e.g. `/generate/stream` returning
  `audio/wav` as a chunked response, or raw PCM frames). **Keep the existing batch endpoints unchanged**
  (rollback + back-compat); add streaming as a new endpoint. Note: streaming WAV needs a header written
  up front with an unknown length — emit a streaming-friendly container (raw PCM or chunked WAV with a
  placeholder size) and document the client contract.

## Steps

0. **CPU-headroom measurement** (above) → decide whether B is in scope.
1. **Pull the chunk boundary out of `chunked_decode`** into the runtime so the generation loop can hand
   completed code chunks (with left context) to the vocoder incrementally, instead of one terminal call.
   Verify streamed-concat output is bit-parity with the current one-shot path.
2. **Deliverable A — streaming endpoint.** Add `/generate/stream` (batch endpoints untouched). Emit each
   chunk's PCM as it's decoded. Measure **time-to-first-audio** vs. current end-to-end.
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
- **Streaming error semantics:** a mid-stream generation failure has already emitted partial audio —
  define the client contract for truncated streams (the batch path can still fail atomically).
- **Box hygiene (carried):** never blanket `docker kill`/`prune` (took down `litellm*`/`headroom-proxy`);
  touch only `qwen3-tts`. Never two `--memory 13g` jobs at once. One backend per process for benchmarks.
- **Don't re-litigate INT8 vocoder** — rejected at 16.3 dB (M1.5). This track keeps the FP32 IR.

## Decision gate

- **Ship A (streaming TTFB)** if it cuts time-to-first-audio with no seam artifacts — high-confidence,
  recommend pursuing regardless of B.
- **Ship B (overlap)** only if step 0 showed CPU headroom *and* measured warm end-to-end improves with
  no regression. If the box is saturated, record the null result and stop — A still stands alone.
- This is the **last material optimization frontier** in the project (the only untouched ~29%). After
  this, the OpenVINO backend is feature-complete across both sizes.
