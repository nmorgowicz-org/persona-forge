# M4 Next Steps: Detailed Implementation Plan

Derived from subagent analysis of current codebase (v0.6.2, 2026-06-28).

Purpose: capture enough implementation detail that a future agent can pick up any step without re-analyzing the codebase from scratch.

## Priority Order

1. Cut per-frame glue overhead
2. Wire vocoder IR
3. Add sampled-audio quality check
4. Investigate frame-160 divergence
5. 1.7B feasibility and planning

## Step 1: Cut Per-Frame Glue Overhead

### Problem

- `_OVCore.run()` (ov_talker_runtime.py) does excessive per-step allocation:
  - Converts all K/V tensors from DynamicCache → numpy via `to_legacy_cache()` → `_to_numpy()` each step.
  - For main: 28 layers → 56 K/V tensors → 56 numpy allocs per decode step.
  - For predictor: 5 layers → 10 K/V tensors → 10 numpy allocs per decode step.
  - Predictor runs up to 15 decode steps/frame → ~150 numpy allocs for K/V inputs alone.
  - OV outputs: uses `np.array(get_output_tensor(i).data, copy=True)` → another 57 allocs (main) / 11 (predictor) per step.
  - All K/V reconstructed via `DynamicCache.from_legacy_cache()` each step.
- Not huge in bytes, but CPU-bound autoregressive decode under a 2x latency gate cannot afford this overhead.

### Solution

Replace DynamicCache round-trip with persistent numpy K/V buffers and minimal torch intermediaries.

Key changes in ov_talker_runtime.py:

1. In `_OVCore.__init__`:
   - Allocate K/V buffers once:
     - `kv_buf[L][2]`: numpy[float32], shape [batch, kv_heads, max_seq, head_dim], C-contiguous.
   - Allocate output buffer:
     - `out_hidden_buf`: [batch, 1, hidden] (decode) / [batch, max_seq, hidden] (prefill).
   - Track `cache_len` (int).

2. Prefill path:
   - Reset `cache_len = 0`.
   - Run infer (no K/V inputs).
   - After infer, use `np.copyto` from OV output tensors directly into `kv_buf` slices.
   - Update `cache_len` = new sequence length.
   - Build a DynamicCache from `torch.from_numpy` views over `kv_buf[:, :, :cache_len, :]` only for the required Transformers interface.

3. Decode path:
   - Build K/V inputs by slicing `kv_buf[:, :, :cache_len, :]` (views, no alloc).
   - Run infer.
   - Write new K/V into `kv_buf` in place via `np.copyto`.
   - Update `cache_len`.
   - Build DynamicCache from views.

4. Small inputs:
   - Avoid `ascontiguousarray` when `.numpy()` is already contiguous.
   - Reuse small buffers for `cache_position`, `position_ids` where feasible.

5. Reset:
   - On new request/frame, set `cache_len = 0`; no need to clear buffers.

Impact:
- Zero per-step numpy allocations for K/V.
- Zero per-step numpy allocations for outputs.
- No torch tensor involvement for K/V beyond minimal `from_numpy` views.
- For predictor 15×/frame, savings are large.
- Correct: same numerical values, same shapes, same layer ordering.

Risks:
- Must keep `cache_len` perfectly in sync with cache_position; re-run parity to confirm.
- Must size `max_seq` conservatively (e.g., 2048) to avoid silent truncation.
- Must not change concurrency model: single-worker ensures no aliasing across requests.
- If parallelism is added later, each request needs its own `_OVCore` with its own buffers.

### Files to change

- `ov_talker_runtime.py`: `_OVCore.__init__`, `_OVCore.run()` (both prefill/decode).

## Step 2: Wire the Vocoder IR

### Problem

- `speech_tokenizer.decode()` runs in PyTorch (Qwen3TTSTokenizerV2Decoder.chunked_decode), ~29% of end-to-end latency.
- FP32 vocoder IR exists and passed parity (SNR 46.4 dB). INT8 rejected.
- Runtime still calls PyTorch; OpenVINO path only covers transformer cores.

### Solution

Create a new vocoder runtime and integrate into OpenVinoTalkerRuntime.

New file: `ov_vocoder_runtime.py`

Class: `OpenVinoVocoderRuntime(talker, vocoder_cfg)`:

- In `__init__`:
  - Load vocoder IR from `vocoder_cfg["model_path"]` via `openvino.Core().compile_model()`.
  - Validate input/output layers match expected names and (B, C, 325).
  - Optionally run a short parity probe: synthetic codes → compare OV vs PyTorch → abort if SNR < 40 dB.

- In `decode(codes)`:
  - Map codes → (B, C, 325) using the same logic as at export.
  - Use existing vocoder mapping layers from `speech_tokenizer` in PyTorch; only decoder body is OpenVINO.
  - Handle:
    - Exact 325 frames: direct inference.
    - < 325 frames: pad identically to how chunked_decode/padding works in the vocoder.
    - > 325 frames: chunk into 325-frame blocks with same stride/overlap, run each via OpenVINO, concatenate waveforms.
  - Return waveform in same shape/dtype as PyTorch decode.
  - Wrap in try/except → fall back to PyTorch on failure.

Integration in `ov_talker_runtime.py`:

- In `OpenVinoTalkerRuntime.__init__`:
  - If `ov_config["vocoder"]["enabled"]`:
    - self.vocoder_runtime = OpenVinoVocoderRuntime(...)
  - Else:
    - self.vocoder_runtime = None

- Add `generate_waveform_from_codes(codes)`:
  - If vocoder_runtime: return vocoder_runtime.decode(codes)
  - Else: return self.talker.speech_tokenizer.decode(codes)

- In `generate_codes_and_final_hidden(...)`:
  - After codes generated, call `self.generate_waveform_from_codes(codes)` instead of direct PyTorch call.

Integration in `app_worker.py`:

- When using ov_talker_runtime, rely on it to produce waveform via OpenVINO vocoder or fallback.
- Keep pure PyTorch path unchanged.

### Config and compose

In `ov_runtime_config.py`:

- Add:
  - `OPENVINO_VOCODER_ENABLED` (bool)
  - `OPENVINO_VOCODER_DIR` (path)
  - `OPENVINO_VOCODER_DEVICE` (default CPU)
  - `OPENVINO_VOCODER_COMPRESSION` (fp32 only)

- Extend `ov_config()` with a `"vocoder"` dict containing those.

In `compose.example.yml`:

- Add example env vars:
  - `OPENVINO_VOCODER_ENABLED=1`
  - `OPENVINO_VOCODER_DIR=/openvino/vocoder`
- Add volume mount:
  - `/var/data/autopirate/qwen3-tts/openvino/vocoder:/openvino/vocoder:ro`

Dockerfile:
- No need to bake in IR; ensure mounted path is accessible.

### Risks

- Must replicate `chunked_decode` exactly (chunk_size, left_context, padding/chunking logic).
- Interface compatibility: IR input name/shape must be validated at load time.
- Memory: adding vocoder IR increases RSS; enable via explicit config.
- Concurrency: use either one InferRequest per request or a simple lock around vocoder inference.

### Files to create/modify

- Create: `ov_vocoder_runtime.py`
- Modify: `ov_talker_runtime.py`, `app_worker.py`, `ov_runtime_config.py`, `compose.example.yml`

## Step 3: Add Sampled-Audio Quality Check

### Problem

- Greedy decoding fails: both FP32 and INT8 OV diverge from PyTorch at frame 160.
- The doc says: "Greedy is a debug signal, not the quality verdict."
- Need a non-greedy, production-sampling quality check for the ship decision.

### Solution

Add `--mode sampled-quality` to `test_ov_generation.py`.

Design:

- For each iteration i (e.g., 10):
  - Set `torch.manual_seed(base_seed + i)`.
  - PyTorch: run `generate_voice_clone` with do_sample=True, same config.
  - Set same seed.
  - Install OV runtime.
  - OV: run `generate_voice_clone` with do_sample=True, same config.
  - Compute metrics between PyTorch and OV outputs.

Metrics per iteration:

- Codes:
  - `overall_codebook_match_rate`: fraction of (frame, codebook) positions where tokens match.
  - Per-codebook match rates.
- Waveform:
  - `waveform_snr_db`: SNR between waveforms.
  - `rms_energy_pt`, `rms_energy_ov`.
- Duration:
  - `duration_pt`, `duration_ov`.
- Token diversity:
  - Entropy per codebook.

Aggregated across iterations:

- `median_waveform_snr_db`
- `mean_overall_codebook_match_rate`
- `mean_duration_ratio`
- `mean_energy_ratio`
- `min_per_codebook_match_rate`
- Per-codebook mean match rates

Acceptance criteria (conservative, red-flag filters):

For 5+ iterations, same prompt, same voice:

- `median_waveform_snr_db >= 15 dB`
- `mean_overall_codebook_match_rate >= 0.70`
- `min_per_codebook_match_rate >= 0.55`
- `mean_duration_ratio` in [0.85, 1.15]
- `mean_energy_ratio` in [0.7, 1.4]

All must pass for "green"; listening tests still mandatory.

Integration:

- argparse:
  - `--mode`: {greedy, sampled-quality, all}
  - `--sampled-iters`: default=10
  - `--strict-greedy`: optional, keeps existing greedy as hard gate

- Output:
  - Same `ov_generation_report.json`; add `"sampled_quality"` key.
  - Greedy results marked as debug-only; not the ship gate.

### Files to modify

- `test_ov_generation.py`

## Step 4: Investigate Frame-160 Divergence

### Hypotheses

Ranked by plausibility:

1. (High) Accumulated floating-point drift → argmax flip.
   - Each autoregressive step uses prior K/V from OV, not bitwise-identical to PyTorch.
   - Over ~160 steps (plus 15×/frame predictor), differences accumulate.
   - At frame 160, logits for two codes cross in argmax priority; single flip cascades.
   - Both FP32 and INT8 share same base drift → same divergence frame.

2. (Medium) Causal mask / cache_position seam mismatch.
   - OV wrapper builds 4D mask from `cache_position` and `attention_mask.shape[-1]`.
   - PyTorch uses `create_causal_mask` with `text_position_ids` including rope_deltas.
   - In TTS audio path (all 1s, no padding), masks should be identical, but a subtle difference could cause a small attention error that only becomes argmax-critical at frame 160.

3. (Low-medium) mRoPE axis / rope_deltas seam.
   - mRoPE is done in PyTorch using FCG's position_ids (with rope_deltas).
   - OV IR sees `position_ids[0]` via wrapper for causal mask; RoPE itself is in the traced graph.
   - If rope_deltas and cache_position create a mismatch between RoPE "positions" and attention "positions", this could affect attention behavior.

### Debugging Plan

1. Add logits-parity logging mode to `test_ov_generation.py`:
   - For first N frames (e.g., 170), capture first-codebook logits (from `codec_head`) at each frame for both PyTorch and OV greedy.
   - Compute per-step max_abs_diff, mean_abs_diff, cosine_sim.
   - Track argmax(pt) vs argmax(ov).
   - The first step where argmax differs is the argmax-flip frame.

2. Sparse cache comparison:
   - Log K/V cache slices for one/two layers (e.g., layer 0, 14) every 10 frames.
   - Compare to corresponding PyTorch values.

3. Validate attention_mask and cache_position:
   - Log `inputs_embeds.shape[1]`, `prior`, `position_ids`, `cache_position`, `attention_mask` in `_OVCore.run()` for short run.
   - Compare with PyTorch.

4. If argmax-flip matches frame-160 and drift grows smoothly:
   - Treat as known inherent FP32 drift.
   - Correct acceptance gate: sampled-audio quality, not greedy code identity.

5. If non-smooth anomaly or sudden step in logits difference:
   - Dig into causal mask / mRoPE hypotheses.

### Files to modify

- `test_ov_generation.py` (logits-parity mode)
- `ov_talker_runtime.py` (temporary logging in `_OVCore.run`)

## Step 5: 1.7B Feasibility (INT8-Only)

### Memory Budget (INT8-Only)

INT8 weight sizes:

- 1.7B main: ~1.7 GiB
- Code predictor: ~35 MiB
- Vocoder (FP32 only): ~456 MiB
- Embeddings/projections/heads (PyTorch): ~150-250 MiB
- Total INT8 weights: ~2.3-2.5 GiB

Estimated peak RSS (serving runtime):

- OpenVINO compiled models (INT8 + buffers): 2.5-3.5 GiB (1.7B) + 150-250 MiB (predictor)
- Vocoder (FP32 IR or PyTorch): ~700-900 MiB
- PyTorch embeddings, projections, heads, caches: ~300-500 MiB
- OpenVINO runtime, numpy buffers, K/V cache: ~500-800 MiB
- Application, Flask, serialization, Python runtime: ~300-500 MiB
- Steady-state: 4.3-6.1 GiB
- Worst-case (long utterances, fragmentation): 5.5-6.5 GiB

Feasible only if:

- INT8 is used.
- PyTorch transformer layers are selectively released after OV compiles.
- Vocoder IR is wired (PyTorch vocoder is heavier on memory).
- Peak RSS under real loads confirmed ≤ 5.6 GiB (20% headroom under 7 GiB).

### Required Code Changes

- `export_openvino.py`:
  - Already size-agnostic (shapes from config).
  - Use `--compression int8` for 1.7B production.
  - (Optional) add metadata hint `"int8_required": true` for 1.7B.

- `ov_talker_runtime.py`:
  - Add startup assertion: if 1.7B and compression != "int8", abort.
  - Ensure no redundant FP32 weight buffer.

- `app_worker.py`:
  - Add 1.7B startup guard (INT8 required).
  - Integrate selective memory release: delete references to PyTorch main and predictor transformer layers after OV compiles; call gc.collect(), optionally malloc_trim.
  - Health endpoint surface: compression for 1.7B, measured peak RSS.

- `compose.example.yml`:
  - Add 1.7B-ready example with:
    - `MODEL_SIZE: 1.7B`
    - `TTS_BACKEND: openvino`
    - INT8-specific OV_MODEL_DIR
  - Either keep 7 GiB (if validated) or document higher recommended limit.

### Export, Parity, and Performance Gates (1.7B)

- Export:
  - INT8-only; IR must compile on dockermisc1 CPU without OOM.
  - metadata.main_dims/predictor_dims must match 1.7B config.

- FP32 parity (dev only):
  - On unconstrained environment: both transformer cores: SNR ≥ 60 dB.
  - Vocoder: SNR ≥ 40 dB.

- INT8 quality:
  - Bounded generated-code agreement.
  - Listening tests with production sampling.

- Performance:
  - Gate 5 for 1.7B: warm median improvement ≥ 1.5x.
  - 5-run warm median/p95 for short/paragraph prompts.
  - No per-token graph compilation; reused InferRequests.
  - Main reset per utterance; predictor reset per frame.

- Memory:
  - Cold start under container limit.
  - Warm inference peak RSS under 6.5 GiB (prefer under 5.6 GiB).
  - Long utterance: same.

- Rollback:
  - `TTS_BACKEND=pytorch` must work for fallback.

### Risks

- OOM during bring-up: transient PyTorch+OV coexistence may exceed 7 GiB; must unload PyTorch layers promptly.
- Predictor latency: 15 sequential steps/frame remains dominant; INT8 and stateful model (M5) are key levers.
- Memory headroom: 7 GiB is tight; selective PyTorch unloading is mandatory.
- INT8 quality: larger models are more robust but not proven; must run listening tests.

### Prerequisites

- Vocoder IR wired into runtime (Step 2).
- Per-frame glue overhead cut (Step 1).
- Sampled-audio quality check in place (Step 3).
- Frame-160 divergence diagnosed (Step 4).
