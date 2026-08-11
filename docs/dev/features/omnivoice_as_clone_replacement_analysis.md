# OmniVoice as a replacement for the Base-model cloning pipeline: analysis

> This is a completed technical analysis: we compared OmniVoice's built-in voice-cloning capability
> against the existing Base-model zero-shot cloning pipeline and concluded that OmniVoice should
> not be used as a replacement. The result is "don't build it."
>
> Prerequisites (same assumptions as the original comparison):
> - `docs/dev/architecture/voice_design.md` (§2, Base-model cloning constraints)
> - `docs/dev/integration/omnivoice_integration.md` (§1, §1a, §2, OmniVoice behavior and latency)
> - `docs/dev/features/persona_forge_studio.md` (§0, swap discipline)

## 0. Purpose

We compared two cloning paths:

- Base-model cloning (current production): `create_voice_clone_prompt` → `generate_voice_clone`,
  wired to `/generate`, `/v1/audio/speech`, and `/generate/stream`.
- OmniVoice cloning: `OmniVoice.generate(text, ref_audio, ref_text, ...)` using the same runtime
  that Persona Forge already uses for voice-design.

Goal: decide whether OmniVoice cloning could plausibly replace the Base-model cloning pipeline.
Licensing was explicitly deferred by request; we treated this as a pure technical comparison of
quality, latency, and integration cost.

## 1. What we compared

| | Base-model cloning (current) | OmniVoice cloning (candidate) |
|---|---|---|
| Entry point | `create_voice_clone_prompt` → `generate_voice_clone`, wired in `src/persona_forge/model.py:712-745`. | `OmniVoice.generate(text, ref_audio, ref_text)` — same callable Persona Forge uses, never invoked with `ref_audio`/`ref_text` here. |
| Runtime | OpenVINO IR (talker + predictor cores) + FP32 OpenVINO vocoder; PyTorch only for glue. Exported, quantized, tuned for this repo's CPU target. | Plain PyTorch (`omnivoice==0.1.5`), CPU-only. No OpenVINO export path exists or is documented. Architecture (diffusion-style decode head) is incompatible with this repo's exporter without from-scratch work. |
| Integration | Production default for the life of the repo. | Voice-design mode (`instruct=`) is implemented and shipped. Cloning mode (`ref_audio`/`ref_text`) is never called; zero hands-on results. |

We confirmed: the OmniVoice cloning mode is currently wired only in theory. The swap-in/swap-out
harness is reusable, but no actual cloning inference has been run.

## 2. Quality

No hands-on, side-by-side comparison was performed. That is the single largest gap, and the
principal reason this analysis concludes "don't build it" instead of proposing a migration.

Based on available evidence:

- OmniVoice's own docs describe cloning as its "most stable mode." If true, it would plausibly
  reduce the high broken-output rates seen in voice-design mode.
- However, OmniVoice's backbone is a 0.6B Qwen3 LLM with a diffusion-style decode head, while the
  Base model is a purpose-built, production-validated 1.7B (or 0.6B) Qwen3-TTS checkpoint whose
  sole job is zero-shot cloning. There is no a priori reason to expect the smaller, general-purpose
  model to outperform the already-specialized pipeline.
- Voice-design testing (Persona Forge) exposed real instability (drone, silence, truncation)
  intrinsic to the decode head and numerical behavior. These are properties of the architecture,
  so there is no reason to assume cloning mode is fully immune.

We concluded: the realistic best case for OmniVoice is "comparable," and that is optimistic.
The only way to settle this would be a controlled bake-off, but the latency findings (§3)
strongly discourage investing in one.

## 3. Latency / throughput

We already have measured numbers on this hardware that settle this question.

- Base/OpenVINO (current): RTF ≈ 1.35–1.40x on dockermisc1 (1.7B-INT4 at 1.35x, 0.6B-INT8 at
  ~1.40x). Measured on the same box, used as the basis for production SLAs.
- OmniVoice (voice-design, plain PyTorch CPU, same hardware): RTF ≈ 12.2
  (43.1s compute for 3.52s audio; 39.6s cold load separate).
- Cloning-mode RTF was never measured, but it shares the same decode head and architecture as
  voice-design. There is no architectural basis to expect an order-of-magnitude drop.
  We treated ≈12x as the working assumption for cloning mode.

This yields roughly 9x slower than the current Base/OpenVINO pipeline.

The only plausible latency remedy is an externally maintained CPU-quantized port (`omnivoice.cpp`,
GGUF/Q8_0), which has not been built, tuned, or tested here. Even in the best case, it's not a
credible near-term win versus the already-optimized Base path.

Memory is not the issue: OmniVoice's voice-design job peaked at 2.80 GB RSS, consistent with
its on-demand-swap usage. Not a blocker; latency is the disqualifying factor.

We concluded: on RTF alone, OmniVoice cloning is not competitive and not a close comparison.

## 4. Integration cost

- Base-model cloning: already running; zero incremental cost.
- OmniVoice cloning: the heavy lifting is done — swap logic, executor serialization, load path.
  Wiring in a cloning call is mechanically straightforward:
  - New job function mirroring `run_omnivoice_job` calling `generate` with `ref_audio`/`ref_text`.
  - Existing voice library provides reference audio + transcript in the exact shape OmniVoice needs.
  - New endpoint or mode flag on `/omnivoice/audition`.
- However, lowering integration cost does not fix the ~9x latency gap or the quality uncertainty.
  "Cheap to wire" does not justify "worth wiring" for a regression on the production path.

We judged: integration is feasible but irrelevant — it doesn't change the core tradeoff.

## 5. Conclusion

We decided: do not use OmniVoice cloning as a replacement for Base-model cloning.

Three reasons converge:

1. Latency: ~9x slower on the exact target hardware, with no available OpenVINO/quantization path
   to close the gap.
2. Quality: no evidence of superiority, and strong structural reason to expect it's not (smaller,
   general-purpose model vs. dedicated, already-production-validated Base).
3. Strategic fit: swapping the production path for a slower, PyTorch-only, unquantized alternative
   would undermine the single differentiator this repo exists to optimize.

For narrow or experimental use (e.g., fallback for problematic clips), OmniVoice cloning is fine
to probe, but only as a small, explicitly-scoped experiment — not as a replacement.

## 6. Open questions and their disposition

Listed for completeness; none of them, as-is, invalidates the conclusion.

1. Real quality bake-off (same clip, same text, several seeds, blind listen).
   - Disposition: still open, but not needed. A latency-unaware bake-off is not worth the investment
     unless the latency story changes.
2. Cloning-mode RTF measured on dockermisc1.
   - Disposition: still open, but not needed. Architecture implies same decode cost as design mode;
     only a dramatic (and implausible) drop would change anything.
3. `omnivoice.cpp` (GGUF/Q8_0) benchmarked on dockermisc1.
   - Disposition: open, external dependency. If it emerges with a credible, maintained port that
     closes most of the ~9x gap, this conclusion should be revisited.
4. License resolution (CC-BY-NC constraint).
   - Disposition: deferred, unchanged. Even if all above became favorable, this still blocks
     commercial use unless addressed.
