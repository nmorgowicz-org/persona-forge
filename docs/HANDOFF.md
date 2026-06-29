# Handoff — streaming vocoder implementation (2026-06-29)

Self-contained brief for the next agent. Deeper detail lives in `OPENVINO_IMPLEMENTATION.md` (design +
milestones) and `OPENVINO_RESULTS.md` (every measured number). Memory file:
`validate-openvino-plan-status.md`.

## Where we are

PR #64 was user-tested and merged; `main` is released as v0.12.0 at `9bf0848`. Active branch
**`feat/streaming-vocoder`** was rebased onto that commit. Streaming foundation commit **`4bc18d9`**
adds `OpenVinoVocoderRuntime.iter_decode_chunks`, makes batch decode consume it, and adds model-free
boundary/parity tests. All 39 unit tests, repository validation, Compose validation, and diff checks pass.

No TTFB improvement exists yet. Qwen generation still returns the entire code sequence before calling
the vocoder. The iterator only establishes one shared, tested decode seam for future batch and streaming
paths. No CPU-headroom measurement, endpoint, pipelining, target-host parity, or listening test has run.

## Immediate next steps, in priority order

1. **Run CPU-headroom Step 0 on `dockermisc1` for 0.6B and 1.7B.** Separate autoregressive generation
   from vocoder utilization. If all eight CPUs are saturated, explicitly reject overlap deliverable B
   and continue only with streaming-output deliverable A.
2. **Trace the stock talker loop where each complete 16-codebook frame is appended.** Add an opt-in
   callback/queue adapter that emits complete frame blocks while preserving the stock terminal return.
   Do not fork or replace the sampling loop without bounded generated-code parity.
3. **Accumulate 300 frames and decode through the shared chunk seam.** Preserve exactly 25 frames of
   left context. The current iterator accepts a completed tensor; incremental state/flush behavior still
   needs design. A final partial block must match batch output exactly.
4. **Only after producer parity, add `/generate/stream`.** Keep `/generate` and `/infer` unchanged.
   Define PCM/container framing and mid-stream failure semantics before emitting bytes.
5. Run target-host concatenation SNR, seam listening, TTFB, serialized-concurrency, batch regression,
   and fresh-process PyTorch rollback gates. Store audio and raw profiles outside Git.

## How to run benchmarks on the box (copy-paste ready)

- `ssh nick@dockermisc1`. Prod `qwen3-tts` is currently **stopped** (user doesn't care). **NEVER**
  blanket `docker kill`/`prune` — it took down `litellm*`/`headroom-proxy` once. Touch only `qwen3-tts`.
  See `dockermisc1-ops` memory.
- **Never run two `--memory 13g` jobs at once** — 15 GiB box + litellm/headroom = OOM.
- IR dirs under `/var/data/autopirate/qwen3-tts/openvino/`:
  - 0.6B explicit INT8: `qwen-tts-0.1.1_0.6b_5d83992436ea_ov-2026.2.1`
  - 0.6B stateful artifacts/reports: the same name plus `_stateful`; raw RSS, parity, speed JSON,
    and generated WAVs remain there outside Git. Source metadata SHA-256 is
    `abec65a5d2f2dcf07382d707513cb2a9f5c2a4c5872728069b169d9601e3da7f`.
  - 0.6B FP32 vocoder: the explicit directory name plus `_vocoder`.
  - INT8: `qwen-tts-0.1.1_1.7b_fd4b25438912_ov-2026.2.1`
  - INT4: `qwen-tts-0.1.1_1.7b_fd4b25438912_ov-2026.2.1_int4g32` (no vocoder inside)
  - FP32 vocoder: `qwen-tts-0.1.1_1.7b_fd4b25438912_ov-2026.2.1_vocoder` (set `OPENVINO_VOCODER_DIR` to
    this for both INT8 and INT4; the INT8 dir's own `vocoder_decoder_int8.xml` is unused — INT8 vocoder
    was rejected at 16 dB).
- Image used for all M9 measurements: `exporter-v0.10.0` at
  `sha256:5189f9bd604c4f4e187175691b7375e9b6f3fd449d91ca73ec78911beaebcb49`, with the (now-merged) M9
  runtime files **mounted over `/app/`** — they are on `main` but **not yet baked into a v0.11.0 image**
  (step 1). The cap-768 bf16 run script + log on the box: `/tmp/ov-m9/run_bf16_cap768.sh`,
  `bf16_cap768.log`. Ref WAV: `/var/data/autopirate/qwen3-tts/voice/voice_A.wav`.
- The speed-bench driver is `/tmp/ov-bench/speed_1.7b.sh` on the box (and `bench_speed.py` in the repo).
  Memory harness is `dump_audio.py --ov-only` (3-checkpoint RSS). Parity/quality harness is
  `test_ov_generation.py` (`--mode sampled-quality`); its coupled greedy block OOMs at 1.7B, so use
  `bench_speed.py` for latency.
- The M9 branch extends `dump_audio.py` with a generation-only RSS sampler. Run with
  `--rss-profile /ov_output/m9_rss_1.7b_int4.json --rss-sample-ms 50`; the JSON labels every sample
  as `transformer` or `vocoder` and reports per-phase peaks. Store the JSON outside Git and compare
  its generation-only peak with the lifetime RSS report.
- Stateful spike dir:
  `qwen-tts-0.1.1_1.7b_fd4b25438912_ov-2026.2.1_int4g32_stateful_spike/`. Use
  `main_stateful_int4_v2.xml`; `main_stateful_parity.json` is bit-exact. Raw profiles are
  `m9_rss_core_1.7b_int4.json` (explicit) and `m9_rss_stateful_main.json` (stateful).
  Original metadata SHA-256 is `ca8f50be8ff4be280248f4ec9c7767ec91f3244e20ef9bcd58042a410344ea2e`;
  stateful XML SHA-256 is `a46b03178576bf0f30fb8b37945b872833e3f25098b83921af82215b91349de5`.

## Hard-won gotchas (don't relearn these)

- M7 weight-release must scope to each core's `.layers` only — freeing `embed_tokens` breaks the glue
  (`talker.get_text_embeddings()` → `'weight' must be 2-D`).
- INT4 graphs are still named `*_int8.xml`; the runtime loads them via `--compression int8`. The dir
  suffix `_int4g<grp>` is the only precision marker.
- 1.7B holds full PyTorch model + OV graphs at once in the coupled harness → measure one backend per
  process (that's why `bench_speed.py` exists).
- transformers is hard-pinned 4.57.3 by qwen-tts==0.1.1; export wrappers depend on its DynamicCache
  `.layers`/`to_legacy_cache` API. Do not bump it. A static-`kv_length` bug in 4.57.3 is dodged by
  `CoreCacheWrapper._build_causal_mask` prebuilding a 4D additive mask — preserve this under any
  stateful rewrite.
- OpenVINO `MakeStateful` rejects dynamic state shapes. Do not retry it. The working design uses
  static-capacity Variables plus dynamic prefix Slice and cache-position ScatterUpdate/Assign.
- Predictor stateful IR has five base inputs; `generation_steps` is retained at index 4. Live nested
  generation may omit it, so `_OVStatefulCore` must preserve the explicit runtime's int64-zero default.
- 0.6B cap-32 predictor is deliberate: its per-frame cache is reset and the validated path is a
  2-token prefill plus 14 decode calls. Main capacity remains 768.
- `ru_maxrss` includes model load and OV compilation; it is not a generation-only metric. Always pair
  it with the sampled generation timeline. The stateful run proved startup is now the lifetime peak.
- RTF here is overhead-dominated (test utterances ~2.6 s), so compare absolute median seconds across
  precisions, not RTF.

## What is explicitly DONE (don't redo)

M0 baseline; M1.5/M2 export+parity; M3 INT8 characterization; M4 runtime+vocoder wiring; M6 (0.6B INT8
shipped, all recovery rejected); 1.7B INT8+INT4 export; M7 weight-release; M8 INT4 memory+quality;
M1.7B-A speed gate; M9: attribution, static state primitive, main INT4 graph rewrite/compile,
bit-exact explicit-vs-stateful main parity, end-to-end memory run, early release before compile,
stateful predictor wiring and listening check, capacity tuning (768/1024 validated),
M9 gates (capacity, warm latency, listening, concurrency, rollback, FP32-vs-PyTorch 0.6B and 1.7B
parity); M9 bf16 serving load + capacity-768 + silence-trim + capacity-tuning docs. **M9 CLOSED and
shipped in v0.11.0** (lifetime peak 7,715 / idle 7,485 MiB at 8G). On this branch, 0.6B stateful
main+predictor transform, runtime input handling, INT8 bit-exact parity, FP32 PyTorch parity,
byte-identical end-to-end quality, short/long RSS, and five-run warm latency are complete. Remaining:
merge/publish, promote IR artifacts, and baked-image smoke test.
