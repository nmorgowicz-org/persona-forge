# Plan: Could OmniVoice's own cloning replace the Base-model cloning pipeline? (comparison, not a build plan)

> Audience: a fresh AI coding agent with **zero prior context** on this repo. Read
> `docs/plans/PLAN_voice_design.md` (§2 for the Base-model cloning constraints),
> `docs/plans/PLAN_omnivoice_integration.md` (§1, §1a, §2 for what OmniVoice is and its
> reliability/latency numbers), and `docs/plans/PLAN_persona_forge_studio.md` (§0 for how
> OmniVoice is already wired into this container's swap discipline) before this doc — it assumes
> you already understand both pipelines and only adds the side-by-side comparison between them.

## 0. Why this doc exists, and what's explicitly out of scope

Nick asked, after the OmniVoice voice-*design* work (Persona Forge) was built: could OmniVoice's
own **voice-cloning** capability (`ref_audio`/`ref_text` → `generate()`) replace this repo's
existing Base-model zero-shot cloning pipeline (`create_voice_clone_prompt` → `generate_voice_clone`,
the mechanism behind `/generate`, `/v1/audio/speech`, and `POST /voices/import`-style flows)?

**Licensing is explicitly out of scope for this doc, by nick's instruction** ("i dont care about
licensing. i need to understand comparison."). `PLAN_omnivoice_integration.md` §4 item 6 and §6
item 5 already flag that OmniVoice's weights are CC-BY-NC and that a license decision is required
before any commercial use — that finding is not repeated or re-litigated here. This doc is a pure
technical comparison: quality, latency, and integration cost. If the technical answer here is ever
acted on, the licensing question from the other doc still has to be resolved first.

**This is a comparison doc, not a build plan.** The conclusion (§5) is "don't build this," so there
is no implementation section — if a future finding overturns that conclusion, a real build plan
would need to be written separately, mirroring `PLAN_persona_forge_studio.md`'s structure.

## 1. What's actually being compared

| | Base-model cloning (this repo, production today) | OmniVoice cloning |
|---|---|---|
| Entry point | `model.create_voice_clone_prompt(ref_audio, ref_text)` → cached `voice_clone_prompt` → `model.generate_voice_clone(...)`. Wired via `get_voice_clone_prompt(voice_id)` (`src/qwen3_tts/model.py:712-745`), used by `/generate`, `/v1/audio/speech`, `/generate/stream`. | `OmniVoice.generate(text, ref_audio=..., ref_text=..., ...)` — same `generate()` signature Persona Forge already calls with `instruct=` instead. `voice_clone_prompt` is also an accepted kwarg upstream (precomputed prompt, analogous to this repo's own caching idea) but unused/untested here. |
| Runtime | OpenVINO IR (talker + predictor cores) + FP32 OpenVINO vocoder, PyTorch only for glue (`PLAN_voice_design.md` §0). Fully exported, quantized, and tuned for this repo's CPU target — see `[[validate-openvino-plan-status]]` memory: 0.6B ships INT8 ≈1.40x, 1.7B-INT4 validated ≈1.35x (real-time factor; i.e. ~1.35-1.40 seconds of compute per second of audio, near-real-time on dockermisc1's CPU). | Plain PyTorch (`omnivoice==0.1.5`), CPU device. **No OpenVINO export path exists or is documented anywhere for OmniVoice** (`PLAN_omnivoice_integration.md` §2 — the diffusion-style decode head is architecturally too different from `qwen_tts`'s Base/VoiceDesign checkpoints for this repo's exporter to reuse). This is not a "not done yet," it's a "would be a from-scratch export project against an undocumented, non-`qwen_tts` architecture." |
| Current integration state | Fully built, production default, has been for the life of this repo. | Voice-*design* mode (`instruct=`) is fully built and shipped (Persona Forge). Voice-*cloning* mode (`ref_audio=`/`ref_text=`) has **never been called** anywhere in this repo — `run_omnivoice_job` (`src/qwen3_tts/omnivoice_engine.py`) only ever passes `instruct`, never `ref_audio`/`ref_text`. Zero hands-on data exists on this repo's OmniVoice cloning output at all. |

## 2. Quality

**No hands-on comparison exists — this is the single biggest gap, and the main reason this doc's
answer is "don't build it" rather than "here's the migration plan."** Everything below is upstream
documentation plus indirect inference from the voice-*design* testing already done in
`PLAN_omnivoice_integration.md` §1a; none of it is a direct clone-quality test.

- OmniVoice's own docs describe voice cloning as **"the most stable mode"** of the model —
  i.e., upstream's own position is that cloning is more reliable than the instruct/voice-design
  path this repo already exercised. If that holds, OmniVoice cloning would plausibly have a lower
  broken-output rate than the ~25% (fp32) / ~50% (fp16) seen for voice-design mode in §1a testing.
  This is a reasonable prior, not a confirmed number for cloning specifically.
- OmniVoice's backbone is a **0.6B Qwen3 LLM** driving a diffusion-style multi-codebook decode
  head. This repo's Base model (the thing already doing production cloning) is the **1.7B**
  (or 0.6B, depending on `MODEL_SIZE`) Qwen3-TTS checkpoint, purpose-built and already validated
  for exactly this job (zero-shot cloning is Base's *only* job — `PLAN_voice_design.md` §2 point
  5: `generate_voice_clone()` requires a Base checkpoint, no instruct support, single-purpose).
  There is no a priori reason to expect a smaller, more general-purpose diffusion model to clone
  *better* than a model that is already specialized for this exact task and already in production
  with known-good quality. The realistic best case is "comparable," not "better," and that's
  optimistic given the size/specialization gap.
- OmniVoice's own voice-design testing (§1a) surfaced real, non-accent-related instability
  (drone/silence/truncation artifacts unrelated to the instruct content) — those are properties of
  the *decode head and numerical stability*, not the instruct grammar specifically, so there's no
  strong reason to assume cloning mode is immune to the same failure class, even if it's rarer.
- **What would actually answer this**: a real generate-N-and-listen bake-off — same reference
  clip, same sample text, run through both `model.generate_voice_clone()` (Base/OpenVINO) and
  `OmniVoice.generate(ref_audio=, ref_text=)` (plain PyTorch), several seeds each, human listening
  comparison. Not done. This is the concrete next step if this comparison is ever revisited (§6).

## 3. Latency / throughput

This is where the comparison is least ambiguous, and mostly settled by numbers this repo already
has on hand:

- **Base/OpenVINO (production today): RTF ≈ 1.35-1.40x on dockermisc1's actual hardware**
  (`[[validate-openvino-plan-status]]` memory — 1.7B-INT4 validated at 1.35x, 0.6B-INT8 ships at
  ~1.40x). This is near-real-time, already measured on the exact box this would need to run on,
  and is the number the whole production Hermes-consumer path (`hermes-tts-consumer.md`) depends
  on today.
- **OmniVoice (plain PyTorch, CPU, same hardware): RTF ≈ 12.2**, measured for voice-*design* mode
  specifically on dockermisc1 (`PLAN_omnivoice_integration.md` §2, "dockermisc1-actual-hardware
  result" — 43.1s generate for 3.52s audio, plus 39.6s cold load). Voice-cloning mode was never
  benchmarked separately, but it runs through the same decode head/architecture as voice-design —
  there's no architectural reason to expect an order-of-magnitude difference between the two modes'
  raw compute cost. **Treat ≈12x RTF as the working assumption for cloning mode too, until measured.**
  That is roughly **9x slower than the Base/OpenVINO pipeline already in production.**
- The unbenchmarked `omnivoice.cpp` GGUF/Q8_0 CPU port (`PLAN_omnivoice_integration.md` §2, §6
  item 6) is the only plausible way to close that gap, and nobody has built or run it against this
  repo's hardware. Even in the best case it would be closing a gap against a runtime this repo has
  already spent real optimization effort on (quantization, IR export, thread/env tuning) — a
  brand-new, externally-maintained C++ port starting from zero tuning work on this specific box is
  not a credible near-term latency win.
- **Memory**: OmniVoice's voice-design job was confirmed to peak at 2.80 GB RSS during generation
  (`PLAN_persona_forge_studio.md` §0) — "fine, no memory optimization needed" for its existing
  on-demand-swap usage pattern. That number is for the *design* job specifically and hasn't been
  re-measured for cloning, but there's no reason to expect cloning mode to be dramatically larger
  (same loaded checkpoint, same decode head, likely similar batch/step count). Not a blocker either
  way — latency, not memory, is the disqualifying factor here.

**Conclusion: on RTF alone, OmniVoice cloning is not competitive with the already-shipped
Base/OpenVINO pipeline on this hardware — it's not close.** A ~9x latency regression on the
*production, already-optimized* cloning path is not something a quality edge (itself unverified,
per §2) would plausibly justify.

## 4. Integration cost

- **Base-model cloning: zero incremental cost — it's the thing already running.** No new code,
  no new dependency, no new swap logic. This is the baseline being compared against, not a
  candidate needing to justify its build cost.
- **OmniVoice cloning: real but bounded incremental engineering, on top of a decent existing
  foundation.** Because Persona Forge already built the hard parts —
  `src/qwen3_tts/omnivoice_engine.py`'s swap-in/swap-out discipline
  (`model.register_foreign_engine`, `model.force_unload()`), the single-executor serialization
  constraint, and the `OmniVoice.from_pretrained(...)` load path — wiring in a *cloning* call would
  reuse essentially all of that plumbing. The actual new work would be:
  1. A new job function (mirroring `run_omnivoice_job`, likely `run_omnivoice_clone_job`) that
     calls `OmniVoice.generate(text=..., ref_audio=..., ref_text=...)` instead of
     `instruct=...`, with the same `analyze_take`/`has_speech` no-speech/drone gating already built
     for the design path (`src/qwen3_tts/omnivoice_engine.py` — this part is genuinely reusable
     as-is).
  2. A way to get a reference clip's audio bytes to the OmniVoice process — this repo's existing
     voice library (`voice_library.get_voice(voice_id)["wav_path"]`, used identically by Base's own
     `get_voice_clone_prompt`) already has exactly the reference-audio-plus-transcript shape
     OmniVoice's `ref_audio`/`ref_text` needs — no new storage concept required.
  3. A new endpoint or a mode flag on the existing `/omnivoice/audition` route.
- **What integration cost does *not* fix**: none of the above touches §3's ~9x latency gap or §2's
  unverified quality question. Cheap-to-wire is not the same as worth-wiring — the swap harness
  being reusable lowers the cost of *finding out* whether OmniVoice cloning is good, but doesn't
  change whether it should replace the production path once measured.

## 5. Recommendation

**Do not build this as a replacement for Base-model cloning.** Three independent reasons converge:

1. **Latency**: ~9x slower on the exact hardware this would need to run on (§3), with no
   OpenVINO/quantization path available to close that gap (unlike every other model this repo
   serves).
2. **Quality**: no evidence it's better, and good a priori reason (smaller, more general-purpose
   backbone vs. this repo's already-specialized, already-production-validated Base cloning path,
   §2) to expect it's not.
3. **What it would actually be trading away**: the Base/OpenVINO pipeline is this repo's core
   differentiator — CPU-only, near-real-time, already tuned. Swapping the production cloning path
   for a ~9x-slower, PyTorch-only, unquantized alternative would be a regression on the one thing
   this repo is specifically built to do well, in exchange for an unverified and architecturally
   unlikely quality upside.

**If there's still interest in OmniVoice cloning for a *narrower* reason** — e.g., as a fallback
for reference clips Base handles poorly, or purely as a research curiosity — that's a much smaller,
explicitly-scoped ask than "replace the production path," and would start with the §2 bake-off
(next section), not a build plan.

## 6. What would change this conclusion

Concrete, falsifiable open questions — if these come back differently than assumed above, revisit:

1. **A real quality bake-off** (§2): same reference clip + sample text through both pipelines,
   several seeds each, blind human listening comparison. This is the single most important missing
   data point — everything else in this doc is latency math and documentation, not measured output
   quality.
2. **Cloning-mode-specific RTF measurement on dockermisc1** — §3 assumes cloning mode costs
   roughly the same as design mode (~RTF 12) because it's the same decode head, but this has never
   actually been measured. If cloning mode turns out meaningfully cheaper than design mode (e.g. if
   it uses fewer diffusion steps by default), the gap in §3 could be smaller than stated.
3. **`omnivoice.cpp` (GGUF/Q8_0) benchmarked on dockermisc1** (`PLAN_omnivoice_integration.md` §6
   item 6, still open) — if a CPU-quantized port closes most of the ~9x gap, the latency argument
   in §5 weakens substantially and this doc's recommendation should be revisited.
4. **License resolution** (explicitly deferred, not answered, here — see §0) — even if 1-3 above
   flip favorably, `PLAN_omnivoice_integration.md` §4 item 6 / §6 item 5's CC-BY-NC question still
   has to be resolved before this could ship in any commercial-facing path.
