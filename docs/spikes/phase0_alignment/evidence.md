# Phase 0 Evidence: Forced Alignment Spike

This document preserves the results of the Phase 0 feasibility spike for the Prosody Re-Architecture.

## 1. Objective
Validate the use of an ONNX-exported MMS CTC forced-aligner for high-precision linguistic boundary detection on Apple Silicon (ARM64) and Intel (x86-64) without a PyTorch runtime dependency.

## 2. Implementation Details
- **Model:** MMS-300M CTC Forced-Aligner (INT8 quantized ONNX).
- **Revision:** `2100fb247d8e43962eef24491597fbeb8b469531`
- **License:** CC-BY-NC-4.0
- **Runtime:** `onnxruntime` with `CPUExecutionProvider` (Baseline).
- **Input:** `input_values` (Normalized PCM 16kHz).
- **Output:** `logits` (31 classes + synthetic `<star>` emission class for divergence).

## 3. Performance Benchmarks (Apple Silicon)
Initial spike run, measured on a 2.96-second excerpt:
- **Session Load:** 0.27 s
- **Inference:** 0.18 s
- **Total Latency:** 0.46 s
- **Footprint:** Low RSS; fully unloadable via `onnxruntime` session drop.

### 3.1 Independent reproduction (2026-07-12)
Re-run on the **full** reference clip to confirm the numbers and close the accuracy gate
against a real, unedited voice-library master rather than an excerpt.

- **Clip:** `/voices/vd_32eb29256158/reference.wav` (Aussie-Female; the "screenshot clip"),
  11.16 s, 24 kHz mono PCM16. Full transcript aligned (40 words, 5 sentences).
- **Runtime (`onnxruntime` 1.27.0, `CPUExecutionProvider`, no torch):** load 0.34 s,
  inference 0.71 s, **total 1.14 s**; 557 emission frames @ 20.04 ms stride.
- **Footprint:** peak RSS ~1.0 GB during inference with the 302 MB INT8 model; releases on
  session drop.

## 4. Accuracy & Findings
- **Blended failure mode, confirmed objectively.** At every true sentence gap (after
  *"arvo." / "know." / "water." / "later."*) the inter-word energy floor is **−169 dB**
  (true silence). At the target *"…no worries. **We'll** sort…"* boundary the floor only
  reaches **−33 dB** — there is *no* silent gap. This is precisely the case the energy-based
  path (`detect_pause_intervals`, `top_db=30`) cannot see.
- **Alignment resolves the gapless split.** The aligner places `worries` end at **7.794 s**
  and `we'll` start at **7.834 s**, straddling the blended seam that has no silence handle.
- **Accuracy vs. objective truth (±50 ms gate).** For a gapless boundary no silence exists to
  hand-mark, and the Voice Library waveform exposes no timeline to measure against, so the
  only well-defined truth reference is the acoustic **energy minimum** of the seam. That
  minimum sits at **7.830 s** (−34 dB, 2.5 ms-hop RMS). The aligned split brackets it within
  **−36 ms / +4 ms** — inside the ±50 ms gate. (A subjective listening hand-mark is deferred
  to the Phase 3 gate, which already mandates a listening + click-detection test.)
- **Divergence Handling:** The `<star>` token correctly captures divergence between audio and
  transcript.
- **Package Compatibility:** Verified that the normalization and Viterbi logic from
  `ctc-forced-aligner` can be implemented using only `numpy` and `scipy`, avoiding the
  `llvmlite` / `torch` dependency issues found in the PyPI package.

## 5. Assets
The spike code and model artifacts are preserved in `docs/spikes/phase0_alignment/`.
- `spike_main.py`: The standalone alignment implementation.
- `model_assets/`: The INT8 ONNX model artifact.
