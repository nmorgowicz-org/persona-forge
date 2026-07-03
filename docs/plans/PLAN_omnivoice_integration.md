# Plan: OmniVoice as an accent-fidelity escalation path for VoiceDesign

> Audience: a fresh AI coding agent with **zero prior context** on this repo. Read
> `docs/plans/PLAN_voice_design.md` first — this doc assumes you already understand that
> architecture (lazy model-swap, single executor, voice library, chip-based frontend) and only
> explains what's *different* for OmniVoice.

## 0. Why this doc exists

Qwen3-TTS VoiceDesign (the model this repo already ships) reliably produces **American-accented
English regardless of prompt wording** for regional English accents (Australian confirmed broken
via hands-on testing on dockermisc1, 2026-07-03 — see repo memory
`voicedesign-accent-investigation.md`). Foreign-language accents (French, Chinese, etc.) work
better. An INT8-vs-INT4 main-core quantization test is in flight as one hypothesis; this doc
covers a second, independent option: swapping in a different, purpose-built voice-design model —
**OmniVoice** (`k2-fsa/OmniVoice`) — for the accent-control step specifically, while keeping this
repo's proven Base-model zero-shot cloning path unchanged.

**Bottom line up front (updated 2026-07-03 with hands-on results — see §1a):** OmniVoice's
Australian-accent claim is **confirmed, not just documented** — nick ran it locally on an M5 Max
(MPS) via `pip install omnivoice` and, with the right reference sentence design, got repeatedly
clean, genuinely-Australian-sounding output. It is **not production-grade out of the box**: raw
output has a real garbage/broken-audio failure rate (~50% on fp16/MPS, ~25% on fp32/MPS) that is
about numerical stability, not accent quality, plus a category-ordering footgun in the instruct
API and a specific word-truncation bug. All of this is fixable with a generate-and-pick workflow
and careful reference-sentence curation (§1a, §5a) — but it means "wire it in" is real engineering,
not a one-line model swap. The official PyPI package also runs (undocumented) on plain CPU with no
code changes — see §2a — which may make the `omnivoice.cpp` GGUF port unnecessary. The license is
still the main blocker to resolve before shipping: **weights are CC-BY-NC**, which conflicts with
this becoming a paid/commercial Hermes feature and needs an explicit decision. Nick's repo is
personal-with-eventual-FOSS-goal (not currently under a strict commercial license), so this is a
"decide consciously, document the exception" problem rather than a hard blocker — but it must not
be silently ignored if/when this ships as part of a commercial Hermes offering.

## 1. What OmniVoice is

- **Project:** `k2-fsa/OmniVoice` — open-source zero-shot TTS with voice cloning + text-only
  "voice design" (no reference audio needed), from the k2-fsa org (maintainers of k2/icefall/
  sherpa, a known speech-processing group, not an anonymous drop). Code: Apache 2.0. **Model
  weights: CC-BY-NC**, because training data includes Emilia, which itself carries non-commercial
  terms — the model card states this explicitly and prohibits "unauthorized voice cloning, voice
  impersonation, fraud, scams, other illegal or unethical activities."
  (Sources: https://github.com/k2-fsa/OmniVoice , https://huggingface.co/k2-fsa/OmniVoice)
- **Architecture:** ~0.6B parameters total. Backbone is `Qwen/Qwen3-0.6B-Base` fine-tuned into a
  TTS model, described as a "diffusion language model-style architecture" — i.e. it's a
  Qwen3-0.6B LLM backbone driving a non-autoregressive multi-codebook diffusion-style decode head,
  not a from-scratch transformer. It reuses the *same* Qwen3 tokenizer/text-understanding stack
  this repo's own Base/VoiceDesign models are built on, which is a meaningfully different (and
  smaller) proposition than the LTX-2.3 comparison — LTX's accent win came from pairing a big
  (22B) generation model with a genuinely strong instruction-following text encoder
  (Gemma-3-12B). OmniVoice's text understanding is a 0.6B LLM, closer in class to Qwen3-TTS
  VoiceDesign's own text path than to LTX's. This is the single biggest reason to treat its accent
  claims as *plausible but unproven*, not a guaranteed fix (see §4).
- **Voice design API:** free-text `instruct` string built from a fixed attribute grammar, one
  value per category, categories freely combined:
  - gender: male / female
  - age: child, teenager, young adult, middle-aged, elderly
  - pitch: very low, low, moderate, high, very high
  - style: whisper (only style value documented)
  - **English accent: american, british, australian, canadian, indian, chinese, korean,
    japanese, portuguese, russian**
  - Chinese dialect (separate list, only applies to Chinese text)
  Example: `instruct="female, young adult, high pitch, australian accent"`. Case-insensitive,
  comma-separated, English/Chinese comma auto-normalized. English accents only apply to English
  text; docs explicitly caution results are less stable outside the Chinese/English training data,
  and that voice cloning (not voice design) is "the most stable mode" — i.e. even OmniVoice's own
  docs flag voice-design/accent-control as the *less* battle-tested feature.
  (Source: https://github.com/k2-fsa/OmniVoice/blob/master/docs/voice-design.md)
  - **Confirmed via source (`omnivoice/utils/voice_design.py`, 2026-07-03): this is a strictly
    validated closed vocabulary, not free-text description.** `generate()` splits the instruct
    string on commas and raises `ValueError` (with a difflib fuzzy-match suggestion) on any item
    not in the exact tag list above — there is no tolerance for synonyms, adjectives, or invented
    descriptors. Concretely: **there is no "warm," "sweet," "light," "gentle," "breathy," or
    "husky" tag** — `style` has exactly one value (`whisper`). Any UI/UX built on this needs to
    expose the *actual* fixed tag set (gender/age/pitch/whisper/accent) as selectable options, not
    a free-text or natural-language "describe the voice" box — the latter will just error out on
    anything outside this list. Perceived warmth/sweetness in generated samples is emergent from
    pitch setting + random seed draw, not a controllable instruct dimension — tune it via
    generate-N-at-a-given-pitch-and-pick, same pattern as accent-quality selection, not via wording.
- **Other features not relevant here but worth knowing about:** cross-lingual voice cloning,
  Whisper-based auto-transcription for reference audio, non-verbal tags (`[laughter]`),
  pinyin/phoneme pronunciation correction, tunable diffusion step count (`num_step`) and duration
  controls, RTF claimed as low as 0.025 on the reference (presumably GPU) setup.
- **Loading pattern (verified against the real installed package, not just docs):**
  `pip install omnivoice`. `from omnivoice import OmniVoice; model =
  OmniVoice.from_pretrained("k2-fsa/OmniVoice", dtype=torch.float32).to(device)` — there is no
  `device_map` kwarg on `from_pretrained`; move the model with `.to("mps")` / `.to("cpu")` /
  `.to("cuda")` after loading, same as any `nn.Module`. Real `generate()` signature (via
  `inspect.signature`, `omnivoice==0.1.5`): `generate(text, language=None, ref_text=None,
  ref_audio=None, voice_clone_prompt=None, instruct=None, duration=None, speed=None,
  generation_config=None, **kwargs) -> list[np.ndarray]` (24 kHz output). A CLI (`omnivoice-infer`)
  also exists per upstream docs but was not exercised here.

## 1a. Hands-on results (nick, 2026-07-03, `omnivoice==0.1.5`, M5 Max MacBook Pro, MPS)

This section supersedes the "unverified" framing in §4 wherever it overlaps — these are real runs
against this repo's actual failing accent case (Australian English), not speculation.

- **The Australian accent capability is real**, not just a documented-but-broken attribute like
  Qwen3-TTS VoiceDesign's. With the right reference sentence (see below), OmniVoice repeatedly
  produced output nick judged genuinely Australian-accented — first confirmed case in this whole
  investigation of a small, non-Gemma-12B-class model actually pulling this off from text alone.
- **Category order in `instruct` is load-bearing and undocumented.** `instruct="australian accent,
  female, young adult, high pitch"` (accent listed first) produced pure noise/drone artifacts, no
  exception raised. `instruct="female, young adult, high pitch, australian accent"` (accent last,
  matching every doc example) worked. Always keep the documented order: gender, age, pitch, style,
  accent last.
- **Raw reliability is poor before any prompt/text tuning — this is a numerical-stability problem,
  not (only) an accent-quality problem.** With `dtype=torch.float16` on MPS, ~50% of takes (11
  generations, same instruct+text, varying only the RNG seed) came back as outright broken audio —
  drone/SFX artifacts, silence, or truncated duration. Switching to `dtype=torch.float32` on MPS
  cut that to ~25% (2/8 broken) — meaningfully more stable, and the failure signature (duration
  outliers, crunched/bitcrushed audio) matches a classic fp16-on-MPS instability pattern for
  diffusion-style decoders. **Recommendation: always use fp32 on MPS for this model; fp16's
  ~2x-broken rate makes it unusable as-is.** CPU/CUDA fp16 stability was not tested — don't assume
  the same fix applies there without checking.
- **A specific, repeatable truncation bug**: sentences opening with "G'day!" reliably had the
  opening word dropped or reduced to just "day" across both fp16 and fp32 takes. Avoiding that
  specific opening word entirely (any other opening phrasing) eliminated the bug in every
  follow-up batch — looks like a narrow weakness handling that specific token/exclamation, not a
  general quality problem.
- **Sentence *content and pacing* is a bigger lever on perceived accent strength than the instruct
  string.** A batch of 8 short one-liners targeting the Australian "GOAT vowel" (the "nyeh-ow"
  diphthong in no/go/know/so/home/phone/closed — one of the most recognizable AU-vs-US accent
  markers) got 8/8 clean, accent-present takes once (a) the "G'day!" opening was avoided and (b)
  pitch was set to `moderate` rather than `high` (nick's preferred register across two separate
  rounds — `high pitch` trended tinnier). Within that batch, **rapid repetition of the target word
  failed** (`"No, no, no, no. What do you know?"` — too fast to enunciate the vowel shift
  properly); the two best results embedded the vowel in a natural, moderately-stressed mid/end-
  sentence position (`"...it's closed, you know."`, `"...till the show's over."`) rather than
  isolating or front-loading it. **Conclusion: reference-sentence design (word choice AND
  placement AND pacing) is a first-class problem for any accent this gets used for, not an
  afterthought** — see §5a below.
- **Reference-length hero clips work too, not just short one-liners.** Qwen3-TTS's own cloning
  guidance recommends ~10-15s reference audio+text. Two ~11-13s candidate sentences built around
  the same GOAT-vowel-placement principle (blended with AU idiom/delivery markers — "arvo",
  "reckon", "she'll be right", "no worries", "no drama" — for register/delivery variety beyond
  just the accent) generated cleanly at `fp32`/`moderate pitch` across 3 seeds each with no
  duration anomalies. This is the shape of clip that would actually get fed into
  `POST /voices/import` (§3) as a real cloning reference, not the short showcase lines.
- **Not yet tested**: CUDA, plain CPU on x86 (see §2a for a plain-CPU MPS-vs-CPU comparison that is
  *not* dockermisc1's exact hardware), determinism/seed reproducibility beyond "same seed number
  passed to `torch.manual_seed` before `generate()`", and any accent besides Australian (British
  sounded good in one earlier single-sample spot check; Indian was inconclusive — quieter output,
  not clearly silent, not re-tested with the fp32/moderate-pitch/sentence-design fixes above).

## 2. CPU feasibility for dockermisc1

dockermisc1: 8 vCPU (Intel i7-1360P, AVX2 + AVX-VNNI, no AVX-512), 15 GiB RAM (swap already under
real pressure — see repo memory `serving-memory-footprint.md`), shared with several other
containers that must not be starved (`dockermisc1-shared-host-caution.md`).

- The official `k2-fsa/OmniVoice` PyPI/GitHub package's *documented* device targets are CUDA, Apple
  Silicon (MPS), and Intel Arc GPU (XPU) — CPU is not documented. **But it was tested hands-on
  (2026-07-03, `omnivoice==0.1.5`, M5 Max) and the plain package runs on `device="cpu"` with zero
  code changes** — `model.to("cpu")` after `from_pretrained(..., dtype=torch.float32)` works,
  generates correct-sounding audio, no exceptions. Measured on the M5 Max's CPU cores (not
  dockermisc1's — see caveat below): RTF ≈ 2.0 (a 3.64s clip took 7.4s to generate) vs RTF ≈ 0.39
  on the same machine's MPS. **This means the `omnivoice.cpp` GGUF route below may not be
  necessary at all — try the plain `pip install omnivoice` package on dockermisc1's actual CPU
  first**, since it needs zero extra tooling if it works. Important caveat: an M5 Max's CPU cores
  are a different, faster architecture than dockermisc1's Intel i7-1360P mobile cores — this RTF
  number does not transfer directly, it only proves the code path is CPU-portable at all.
- There is also a community C++ port, **`ServeurpersoCom/omnivoice.cpp`**, explicitly advertising a
  `buildcpu.sh` CPU-only build path alongside CUDA/ROCm/Metal/Vulkan, with a Q8_0 GGUF
  quantization of the "612M parameter Qwen3 backbone" (the codec/tokenizer component stays F32).
  It documents both voice cloning *and* voice design (attribute-keyword based) as supported
  features. This is the credible path to running OmniVoice on this repo's hardware — **not** the
  official PyPI package as-is.
  (Source: https://github.com/ServeurpersoCom/omnivoice.cpp)
- What's *not* documented anywhere found in this research: AVX-512-specific requirements (this
  repo's exporter deliberately avoids AVX-512-only kernels — dockermisc1 doesn't have it, so this
  matters), concrete RAM footprint in GB, or any CPU-only RTF/latency benchmark numbers. This is a
  real gap — do not commit deployment effort before running it.
- **No OpenVINO export path exists or is documented anywhere for OmniVoice.** This repo's whole
  pattern (PyTorch → ONNX → OpenVINO IR, `src/export/export_openvino.py`) is specific to the
  `qwen_tts` package's Qwen3-TTS architecture; OmniVoice's diffusion-style decode head is a
  different enough architecture that reusing that exporter is not realistic without significant
  new work, and nothing upstream suggests anyone has done an OpenVINO port. The `omnivoice.cpp`
  GGUF/llama.cpp-style path is the only credible CPU story right now, and it is a **separate
  runtime and toolchain from this repo's OpenVINO-only design** — it does not slot into
  `src/qwen3_tts/openvino/` at all.

**Feasibility verdict: plausible as a separate, occasional-use CPU process, not plausible as a
third "profile" inside the existing OpenVINO runtime.** Concretely, `omnivoice.cpp` at Q8_0 is a
~0.6-1 GB weight footprint class model — small enough in principle to coexist briefly with the
resident Qwen3-TTS Base model on a 15 GiB box for an occasional, short voice-design call, *if* it
is invoked as a short-lived separate process/container rather than a third resident service. But
this is an estimate, not a measurement — nobody has run `omnivoice.cpp` on this hardware. Treat
"it'll fit" as an assumption to verify in §6, not a conclusion.

**dockermisc1-actual-hardware result (2026-07-03, plain `pip install omnivoice`, `dtype=torch.
float32`, throwaway `python:3.11-slim` container, `device="cpu"`): RTF ≈ 12.2** (43.1s generate
for 3.52s audio; 39.6s cold model load on top). This is the number that matters — the M5-Max CPU
figure above (RTF≈2.0) does **not** transfer; dockermisc1's real RTF is ~6x worse than that and
~31x worse than M5-Max MPS. **This changes the feasibility verdict materially**: combined with the
~25% broken-output rate requiring generate-N-and-pick, producing one usable clip could cost
10-15+ minutes of CPU time on dockermisc1. That rules out any interactive/live "audition this
accent" UX step on this hardware via the plain PyPI package — it would only be workable as a slow,
explicitly-async background job (submit → wait minutes → notify), and even then competes for CPU
with the resident Qwen3-TTS Base service on a shared, already-constrained 15 GiB box. This makes
the still-unbenchmarked `omnivoice.cpp` GGUF/Q8_0 path (which was already the recommended CPU
route in principle) more important, not less — the plain PyTorch package's CPU performance is not
a viable fallback on this specific hardware, despite being code-path-portable.

## 3. Recommended integration architecture

Given §2, do **not** attempt to fold OmniVoice into `model.py`'s `ModelProfile`/lazy-swap
mechanism the way VoiceDesign was integrated (`PLAN_voice_design.md` §4.2). That mechanism assumes
one OpenVINO runtime, one executor, one `qwen_tts` package API surface (`generate_voice_clone` /
`generate_voice_design` / `generate_custom_voice`). OmniVoice is a structurally different model,
different runtime (llama.cpp-style GGUF, not OpenVINO IR), different Python package, with no
export story into this repo's IR pipeline.

**Recommended option: a separate, on-demand OmniVoice service, called only for the voice-design
step, whose *output* (a WAV) is handed to this repo's existing, proven Base-model zero-shot
cloning path — exactly the same handoff shape `/voice_design` already uses today, just with a
different voice-design engine behind it.**

```
┌────────────────────────────┐        ┌─────────────────────────────────────┐
│ omnivoice-design (separate │        │ qwen3-tts container (unchanged Base  │
│ container/process, started │  WAV   │ model always resident; VoiceDesign   │
│ on demand, stopped after)  │───────▶│ swap path unchanged, both still work)│
│ omnivoice.cpp CPU build,   │        │                                       │
│ Q8_0 GGUF                  │        │ POST /voices/import (NEW, small) —   │
└────────────────────────────┘        │ takes a WAV + sample_text, stores it │
                                       │ into the existing voice library      │
                                       │ (§7 of PLAN_voice_design.md) exactly │
                                       │ like a /voice_design response does,  │
                                       │ so it's immediately usable as        │
                                       │ voice_id in /v1/audio/speech         │
                                       └─────────────────────────────────────┘
```

Why this shape, specifically:

1. **It never touches the executor, the OpenVINO runtime, or `model.py`.** Zero risk to the
   production Hermes path (`/v1/audio/speech` with no `voice_id`) or to the already-working
   Qwen3-TTS VoiceDesign swap. This matters a lot given how carefully those constraints were
   respected building the existing feature (`PLAN_voice_design.md` §2).
2. **It reuses, rather than duplicates, the voice library and cloning pipeline.** OmniVoice's job
   ends at "produce a WAV that sounds like what the user described." Getting that WAV into
   Hermes's hands as a usable `voice_id` is a solved problem already (§4.4 of
   `PLAN_voice_design.md`) — don't rebuild it.
3. **It matches the honest capacity story.** Running two heavyweight inference stacks
   (OpenVINO Qwen3-TTS + a GGUF OmniVoice) resident at once on a 15 GiB box that already has swap
   pressure is not something to attempt casually. On-demand/short-lived keeps the two processes'
   peak memory windows from overlapping for long, and keeps the blast radius on
   "shared-host caution" (other unrelated containers on dockermisc1) small.
4. It also sidesteps the CC-BY-NC weight license question living *inside* this repo's own served
   model tree — OmniVoice stays an external, clearly-separated component that a deployer can
   choose to enable or not, rather than baked into the qwen3-tts-openvino image's default IR set.

**Only a `/voices/import` endpoint needs to be added to this repo** (accepts a WAV + a
`sample_text` string that is exactly what's spoken in the WAV, same constraint the existing
`/voice_design` → voice-library handoff already relies on — see `PLAN_voice_design.md` §4.4 point
1 for why `ref_text = sample_text` is correct there). This is deliberately the *smallest possible*
change to this repo — everything else (running OmniVoice, converting its output to a WAV,
calling `/voices/import`) is orchestration that can live outside this repo entirely (a small
script, or a step in whatever frontend/backend glue calls both services), which also keeps the
CC-BY-NC-licensed component fully decoupled from this repo's own release artifacts.

**Explicitly rejected option:** folding OmniVoice into the lazy-swap `ModelProfile` pattern inside
this container. Rejected because there is no OpenVINO export path, no shared package API with
`qwen_tts`, and no verified CPU performance data — forcing that fit now would mean committing to
unknowns on all three axes at once, in the same container that carries the production Hermes
traffic.

## 4. Usability assumptions — updated 2026-07-03 with hands-on results (§1a)

1. **CONFIRMED (was unverified): OmniVoice's `australian` accent attribute can produce genuinely
   Australian-sounding output**, not just American-with-a-label — the first confirmed case in this
   investigation of a small (non-Gemma-12B-class) model actually doing this from text alone. This
   is *conditional*, not unconditional: it required fp32 (not the docs' fp16 examples), moderate
   (not high) pitch, and — most importantly — careful reference-sentence design (§1a, §5a). Naive
   use of the documented `instruct` example with arbitrary text is not guaranteed to reproduce
   this; see item 3 below.
2. **Downgraded from "unverified" to "partially refuted": the 0.6B Qwen3 backbone being 20x+
   smaller than LTX-2.3's Gemma-3-12B encoder does NOT mean it fails outright** — it does produce
   the accent, just less reliably and with more sensitivity to exact prompt/sentence phrasing than
   a larger encoder would presumably need. Treat backbone size as a "how much sentence-design work
   you'll need to do to get consistent results" cost, not a hard pass/fail gate.
3. **NEW finding, not anticipated in the original doc: raw output reliability (independent of
   accent correctness) is the bigger practical problem.** ~25-50% of takes (depending on fp16 vs
   fp32) come back as outright broken audio — drone artifacts, silence, truncated duration — for
   reasons unrelated to accent quality (see §1a). Any integration must assume single-shot
   generation is not good enough and budget for a generate-N-and-reject-broken step.
4. **Still unverified: CPU (`omnivoice.cpp` Q8_0, or the plain package on CPU — §2a) inference
   quality/reliability matches the fp32/MPS results above.** Quantization (GGUF) and even plain
   CPU fp32 execution could independently reintroduce the fp16-style instability seen on MPS, or
   behave differently. Do not assume the MPS findings transfer to dockermisc1 without a real test
   there.
5. **Still unverified: actual CPU latency/RTF on dockermisc1's specific hardware.** §2a's CPU
   numbers are from an M5 Max, a different and likely faster CPU architecture than dockermisc1's
   Intel i7-1360P mobile cores. Treat dockermisc1 latency as unknown until measured there directly.
6. **Assumed but not confirmed: the CC-BY-NC weight license is compatible with an occasional,
   internal, non-redistributed use** (design a voice for a user's own AI agent, keep the resulting
   WAV, never redistribute the OmniVoice model itself). This is a plausible reading but is **not a
   substitute for an actual license review** before this ships in any commercial Hermes-adjacent
   product path — flag to a human, do not decide unilaterally in code. Nick's stated intent is this
   repo is personal-with-eventual-FOSS-goal, so this is lower urgency than for an already-commercial
   product, but still needs a conscious decision before any paid Hermes tier depends on it.

## 5. UX workflow: escalation path for users unhappy with native VoiceDesign results

Context: this repo's downstream consumer is Hermes — an AI-agent/companion voice product, not
audiobook narration (`hermes-tts-consumer.md`). Users are designing *one* voice for their agent,
then living with it; the existing chip-based VoiceDesign panel (`PLAN_voice_design.md` §8.3,
`frontend/src/lib/voiceDesignChips.ts`) is fast, free, already built, and works well for
persona/timbre/register — the specific failure mode is regional English accents.

Proposed flow, **explicit and visible, never a silent engine swap** (this repeats the existing
plan's own principle — `PLAN_voice_design.md` §3: "Model-swap cost is real and must be visible to
the caller"):

1. **Default path (unchanged):** user works the existing chip-based `/voice_design` panel —
   accent, demographics, register, texture, persona chips → composed description → preview → "Use
   this voice" → `voice_id` in the voice library, usable immediately via `/v1/audio/speech`.
2. **Accent dissatisfaction signal:** after previewing a VoiceDesign result, if the user's accent
   chip was Tier-1 non-US (AU/UK/IE — see `voiceDesignChips.ts` `ACCENTS`) or a Tier-2
   "Experimental" chip, and the user explicitly indicates the accent isn't right (a "Doesn't sound
   right? Try enhanced accent design" affordance next to the preview player, not an automatic
   retry), surface an explicit escalation card. Do not auto-retry through OmniVoice on the user's
   behalf without them opting in — it costs real time (§2 latency is unverified but assume "not
   instant") and, per §4 item 5, may carry licensing implications worth being transparent about
   ("this uses a different, non-commercially-licensed model for this step — output stays yours,
   internal use only").
3. **Escalation card, two options, both terminate at the same place (a `voice_id` in the library):**
   - **(a) "Try enhanced accent design" (OmniVoice path, if deployed per §3):** re-collects the
     same accent/demographics/register/persona chip selections already made (don't make the user
     re-enter everything), maps them onto OmniVoice's stricter fixed-category grammar (§1 — this
     needs a small chip→OmniVoice-instruct mapping table, analogous to
     `composeDescription()` in `voiceDesignChips.ts` but targeting OmniVoice's vocabulary, which is
     narrower — e.g. no free-text texture chips, only its documented pitch/style enum), calls the
     separate OmniVoice service, gets a WAV back, plays it inline for comparison against the
     original attempt, and on accept calls the new `/voices/import` endpoint (§3) to add it to the
     voice library exactly like a normal VoiceDesign capture — same `GET /voices` listing, same
     `voice_id` semantics, same downstream `/v1/audio/speech` usage. Frontend surfaces this as a
     visibly slower, clearly-labeled "enhanced accent design" step, not a variant of the fast path
     — reuse the swap-in-progress-style banner pattern already built for the Qwen3-TTS VoiceDesign
     swap (`PLAN_voice_design.md` §3, §11 frontend checklist) so the user isn't left guessing why
     it's slower.
   - **(b) "Provide a reference clip instead":** guide the user to record or upload a short (3-15s)
     real clip of the accent/persona they want and clone it directly via the existing, always-
     reliable Base-model zero-shot cloning path (no voice-design model involved at all — this is
     the same mechanism `/v1/audio/speech` + `voice_id` already uses, just with a user-supplied
     reference instead of a VoiceDesign-generated one). This is the **fallback that requires zero
     new engineering** and should be offered even before OmniVoice is integrated, since it uses
     capability this repo already has today.
4. **Reproducibility:** `torch.manual_seed(N)` called before `model.generate()` does affect output
   (verified hands-on — same instruct+text+seed reliably reproduces the same audio duration, and
   informally the same character, across reruns), so store the seed the same way
   `/voice_design` already does. Note duration was observed to track *text* deterministically (not
   seed) in one batch — seed appears to affect fine acoustic detail/reliability more than gross
   timing. Store whatever generation parameters were used (accent/gender/age/pitch instruct
   string, seed, dtype, `engine="omnivoice"`) in the voice's `meta.json` for provenance.

## 5a. Curated per-accent reference-sentence bank — required, not optional (added 2026-07-03)

This is the single most important UX-workflow finding from §1a's hands-on testing, and changes
step 3(a) above from "call OmniVoice with a chip-derived instruct string and arbitrary/user-typed
sample text" to a **fixed, hand-curated library of reference sentences per accent**:

- **Why:** §1a showed sentence *content, word placement, and pacing* has as much or more effect on
  perceived accent strength as the instruct string itself. A rapid-fire word-repetition sentence
  failed even with a correct instruct string and the right dtype/pitch settings; a sentence
  embedding the same target vowel naturally in a stressed mid/end-sentence position succeeded
  consistently. This is not something an end user typing arbitrary sample text (as the existing
  `/voice_design` flow allows) can be expected to get right — it requires the kind of phonetic
  sentence-design work done in §1a's GOAT-vowel batch.
- **What this means concretely:** for each accent OmniVoice-path offers (starting with Australian,
  the only one validated so far — see §1a's "not yet tested" list for others), ship a small,
  hand-picked set of 2-4 reference sentences (~10-15s each, matching Qwen3-TTS's own recommended
  clone-reference length) specifically designed to showcase that accent's most recognizable
  phonetic markers, verified by an actual human listen-through before being added to the bank
  (exactly the process used in §1a — build candidates, generate several seeds, listen, keep only
  the ones that land). This is real, ongoing content-curation work, not a one-time engineering
  task — treat it the same as the existing `voiceDesignChips.ts` persona-linked sample texts
  (`PLAN_voice_design.md` §8.3), which already establishes the pattern of curated-not-freeform
  sample text tied to a design choice.
- **UX implication:** step 3(a)'s escalation card should present the user with a **choice of
  curated reference sentences to preview/audition** (not a free-text box) once an accent is
  selected, exactly mirroring how `voiceDesignChips.ts` already ties persona chips to curated
  sample texts. The user picks (or the flow auto-generates several candidates from the bank and
  lets them pick) the take that sounds best, and *that* WAV — not a single blind generation — is
  what gets sent to `/voices/import`.
- **Starting bank (Australian, fp32/moderate-pitch, validated 2026-07-03):**
  - `"...it's closed, you know."` and `"...till the show's over."` context sentences scored best
    for the GOAT-vowel marker specifically (see full text in repo memory
    `voicedesign-accent-investigation.md`).
  - Avoid: sentences opening with "G'day!" (confirmed truncation bug, §1a), rapid word repetition.
- **Hero-length (10-15s) single-shot generation — tried and REJECTED (2026-07-03):** built two
  ~11-13s candidate sentences combining GOAT-vowel placement with AU idiom/delivery markers
  (arvo, reckon, she'll be right, no worries, no drama), generated as one sentence per take. All 6
  takes (2 sentences x 3 seeds) came back broken (droning, quiet/muted, or muddy) — a stark
  regression from the short single-focus GOAT-vowel sentences (`g5`/`g6`/`g7`), which were reliably
  clean. Sentence length/complexity is itself a reliability lever for the 0.6B backbone, separate
  from wording quality — long combined sentences should not be generated in a single shot. Files
  kept for reference only, not as bank content: `audio/omnivoice_au_hero_a_coast_seed*.wav` /
  `omnivoice_au_hero_b_footy_seed*.wav`.
  - **Revised approach for reference-length (10-15s) clips**: generate several independent short,
    validated bank sentences (each individually high-hit-rate, as `g5`-class sentences were), then
    concatenate the clean takes into one reference WAV, rather than asking the model for one long
    sentence. This keeps per-sentence reliability high while still hitting Qwen3-TTS's recommended
    10-15s clone-reference length. Not yet built/tested — next step if this path is pursued
    further.
  - **CONFIRMED WORKING (2026-07-03)**: tested the stitching approach directly — 5 multi-sentence
    (2-3 sentence) passages, each sentence generated via a *separate* `generate()` call (no manual
    seed set, letting each draw its own), concatenated client-side with a 350ms silence gap. All 5
    came back with consistent duration/RMS (9.1-11.5s, no silent/broken segments) — a clean result
    where the equivalent single-shot long-sentence generation had failed 5/5 (droning/empty/
    bitcrushed). This is now the validated approach for 10-15s reference clips: **generate short,
    stitch, don't ask for long generations in one call.**
    Files: `audio/omnivoice_au_stitch_opt1_roadtrip.wav` through `opt5_oldroad.wav`.
  - **New finding from listening to the stitched results**: even with all-clean segments, nick
    noted audible tone/delivery drift *between* segments within the same stitched clip (register,
    warmth varying seed-to-seed within one passage) — expected, since each segment is an
    independent draw. **UX implication**: the reference-sentence-bank flow needs **per-segment
    cherry-picking**, not just per-passage generate-and-pick. Concretely: for a multi-sentence
    reference clip, generate 2-3 candidate takes *per sentence slot*, let the user preview and swap
    out just the weak segment and re-roll it independently, then stitch the final picked set —
    cheaper than re-rolling the whole passage, and directly addresses the drift observed here. Not
    yet built.
  - **Tone/warmth is not an instruct-string lever (2026-07-03 finding, see §1's vocabulary note)**:
    nick asked how to get a "warmer/sweeter/lighter" sounding voice via wording — confirmed via
    source (`voice_design.py`) that the instruct vocabulary is closed and strictly validated
    (`ValueError` on any unrecognized item), with no warmth/sweetness/breathiness tags at all —
    `style` has only `whisper`. Perceived warmth is emergent from `pitch` setting + random seed,
    not describable in words. **UX implication**: don't build a free-text "describe the tone you
    want" box for OmniVoice specifically — expose the real fixed tag set (gender/age/pitch/
    whisper/accent) as selectable chips, and let generate-N-and-pick (now at per-segment
    granularity, per the point above) be the actual mechanism for landing on a "warm" or "sweet"
    result, rather than promising word-level tone control the model doesn't have.

## 6. Open questions / required before committing engineering time

Updated 2026-07-03 — items 1-3 below are now **answered**, including on dockermisc1's real
hardware (§2). Item 3's answer is the most important update: it changes the overall feasibility
verdict from "plausible, needs measurement" to "not viable via the plain package on this
hardware."

1. ~~Does OmniVoice produce genuinely Australian-accented output?~~ **Answered: yes, confirmed by
   nick hands-on (§1a), conditional on fp32 dtype, moderate pitch, and curated sentence design
   (§5a).** Still open: does a *second*, independent listener agree (only one person has evaluated
   these samples so far)?
2. ~~Does the plain `pip install omnivoice` package run on dockermisc1's CPU?~~ **Answered: yes,
   runs with zero code changes** (Intel i7-1360P, AVX2 + AVX-VNNI, no AVX-512; throwaway
   `python:3.11-slim` container, `dtype=torch.float32`, `device="cpu"`).
3. ~~What is actual peak RSS and wall-clock latency on dockermisc1's specific hardware?~~
   **Answered: RTF ≈ 12.2** (43.1s generate for 3.52s audio; 39.6s cold model load). This is ~6x
   worse than the M5-Max CPU figure (RTF≈2.0) and ~31x worse than M5-Max MPS (RTF≈0.39) — the
   Mac numbers do not transfer to this hardware at all. **This changes the feasibility verdict**:
   combined with the ~25% (fp32) broken-output rate requiring generate-N-and-pick, one usable clip
   could cost 10-15+ minutes of dockermisc1 CPU time. Not viable as an interactive/live "audition
   accents" UX step on this hardware via the plain PyPI package. Peak RSS was not separately
   measured (the `--memory=6g` container limit was never hit, so it's under 6 GiB, but no tighter
   number was captured) — lower priority now that latency alone rules out the interactive path.
4. **Does the ~25% (fp32) / ~50% (fp16) broken-output rate observed on MPS (§1a) reproduce on
   dockermisc1's CPU**, or is it MPS-specific? Not yet isolated — only one CPU take was generated
   (it succeeded), not a multi-seed batch. Lower priority now that #3's latency finding already
   rules out interactive use regardless of the exact reliability rate.
5. **License review**: does CC-BY-NC weight licensing block using OmniVoice output inside a paid
   or otherwise commercial Hermes product, even for internal-only, non-redistributed use? Get an
   actual answer (legal/human judgment call) before shipping the §5 UX flow, not after. Lower
   urgency while this repo stays personal/pre-FOSS, but must be resolved before any commercial
   Hermes tier depends on this path.
6. **Given #3: is `omnivoice.cpp` (GGUF/Q8_0, quantized) worth benchmarking on dockermisc1 before
   giving up on local CPU hosting entirely?** The plain PyTorch package's CPU performance is
   clearly not viable interactively; a quantized llama.cpp-style port could plausibly close much
   of that 12x gap, but this is unverified — nobody has built/run it. This is now the live
   question, superseding the original "try plain package first" framing in the old item 2.
7. If §6.6 also fails or is judged not worth the engineering investment: the fallback in §5.3(b)
   (user-supplied reference clip cloning) already works today and needs no further research —
   consider shipping *that* alone as the accent-dissatisfaction escalation path, and treating
   OmniVoice (in any form) as an offline/background-only capability at best, not a live UX
   feature, rather than investing further engineering here.
