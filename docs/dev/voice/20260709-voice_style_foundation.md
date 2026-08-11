# Voice Style Foundation and Speak Page Plan

Date: 2026-07-09
Status: Proposed authoritative successor to:

- `docs/plans/20260706-manipulating_a_voice.md`
- `docs/plans/20260708-speak_tab_enhancements.md`
- `docs/plans/20260708-tts_audio_style_pipeline.md`

This document is the foundation for making voice delivery more controllable in
this app. It covers what is actually possible, what is not currently supported,
how to build a practical style pipeline, and how the Speak page should expose it.

## Codebase grounding (read this first)

This plan is written against the current repo. An implementing agent must build
on what already exists rather than create parallel modules. Key existing pieces:

| Concern | Existing code | Reuse / extend, do not replace |
| --- | --- | --- |
| Audio DSP primitives | `src/persona_forge/audio_post.py` | Already ships `compress`, `normalize_rms` (RMS/dBFS), `limit_peak`, `trim`, `apply_fades`, `concat_with_padding`, `crossfade_concat`, `analyze_take`, `stitch_segments`. Already imported by `omnivoice_engine.py`. The new `audio_style.py` must call into this, not re-implement DSP. |
| Voice storage | `src/persona_forge/voice_library.py` | Flat `voice_id` model with per-voice `meta.json`. Extend `meta.json` additively (family/variant/metrics); keep flat behavior working. |
| OmniVoice knobs | `src/persona_forge/omnivoice_engine.py` | `speed`, `durations` (per-segment), `guidance_scale`, `num_step`, `postprocess_output`, `seed` are real and clamped (`MIN_SPEED`/`MAX_SPEED`). |
| Pocket TTS | `src/persona_forge/pocket_tts_runtime.py` | `model.get_state_for_audio_prompt(x)` accepts a named preset (`"alba"`), a local wav path, or an `hf://kyutai/tts-voices/...` path (verified `pocket-tts==2.1.0`); caches voice states. Built-in voices need no custom downloader — see Workflow D. |
| Speak page | `frontend/src/pages/SpeakPage.tsx` | Contains `estimateInitialEta` (~line 43) — the fake pre-generation ETA that Phase 1 removes. |

### Resolved DSP-dependency & loudness decisions (2026-07-09)

These were the two design decisions that gate Phase 4. **Both are now decided —
implement to these, do not re-open them.**

**What is already installed** (so it is *not* a "new" dependency): `librosa`
(pinned in `requirements/requirements-runtime.txt`) and therefore `scipy` +
`numba`; plus `torchaudio` and `faster-whisper`. These provide VAD/onset/pause
detection, resampling, `scipy.signal` filtering (EQ), pitch-preserving
time-stretch (`librosa.effects.time_stretch`), and ASR transcripts.

1. **Dependency policy — APPROVED: add `pyloudnorm`; reuse existing libs.**
   - Add exactly one new dependency, **`pyloudnorm`** (pure-Python; its only dep,
     `scipy`, is already present), to `requirements/requirements-runtime.txt`
     during Phase 4. It provides true integrated **LUFS** + true-peak.
   - Reference **metrics**, **EQ**, **pause-shaping**, and **time-stretch** use
     the already-installed `librosa`/`scipy` — no further dependencies.
   - **The locked "no new DSP dependency" rule still binds `audio_post.py`'s
     stitch path** — keep it numpy-only. The scope of that decision is the hot
     stitch pipeline, not offline reference authoring. The **new
     `audio_style.py` and `analyze_reference` may freely use
     `librosa`/`scipy`/`pyloudnorm`**, because they run on already-generated
     audio and short reference clips, not inside the stitch loop.

2. **Loudness metric — DECIDED: true LUFS.** Because `pyloudnorm` is approved,
   normalize toward integrated **LUFS** and cap **true-peak** (via `pyloudnorm`
   measurement + `audio_post.limit_peak`). All UI badges show real LUFS/dBTP
   (e.g. `-20.4 LUFS`, `-1.2 dBTP`) — they are now honest. Keep `rms_dbfs` /
   `peak_dbfs` in the metrics dict too (cheap, useful for quick checks), but the
   headline loudness label is LUFS.

## Bottom line

The observation that started this investigation is real and expected:

- A slow, pause-heavy reference such as the "Welcome to Rosie's" clip makes
  Pocket TTS and other cloning models produce slower, pause-heavier speech.
- A stitched reference made from faster OmniVoice segments produces tighter,
  faster delivery.

That behavior is not a bug. In this class of TTS systems, reference audio is not
just a speaker identity sample. It also carries pace, pause structure, energy,
accent cues, microphone quality, and sometimes emotional posture. Pocket TTS
documents this explicitly by recommending sample cleanup because the sample's
audio quality is reproduced. Qwen3-TTS Base and OmniVoice cloning behave the
same way in practice.

The best product strategy is therefore not to promise independent numeric
controls like `energy=0.7` or `pause_strength=0.4`. The durable approach is:

1. Build style-specific reference variants.
2. Preserve those variants as first-class voice assets.
3. Add lightweight post-processing only for small final polish.
4. Redesign Speak around choosing engine, voice, delivery variant, and output
   polish honestly.

## External evidence checked

Checked on 2026-07-09:

- Qwen3-TTS Hugging Face model card:
  - 1.7B VoiceDesign is documented as description-driven voice generation.
  - 1.7B/0.6B CustomVoice supports instruction control over 9 built-in speakers.
  - 1.7B/0.6B Base is documented as rapid voice clone from user audio.
  - The official reusable workflow is "Voice Design then Clone": synthesize a
    styled short reference with VoiceDesign, then feed that reference into Base.
  - Source: https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base
- Qwen3-TTS technical report:
  - Qwen3-TTS supports voice cloning and description-based control, and reports
    InstructTTSEval / long-speech evaluations.
  - This does not mean every released checkpoint exposes the same control API.
  - Source: https://arxiv.org/abs/2601.15621
- OmniVoice documentation:
  - Voice Design accepts comma-separated speaker attributes: gender, age, pitch,
    style, accent, dialect.
  - The documented style category is `whisper`.
  - English accent choices include American, British, Australian, Canadian,
    Indian, Chinese, Korean, Japanese, Portuguese, and Russian.
  - `speed` and `duration` are documented generation parameters; `duration`
    overrides `speed`.
  - Source: https://github.com/k2-fsa/OmniVoice
  - Source: https://raw.githubusercontent.com/k2-fsa/OmniVoice/master/docs/voice-design.md
  - Source: https://raw.githubusercontent.com/k2-fsa/OmniVoice/master/docs/generation-parameters.md
- Pocket TTS documentation:
  - It supports a small voice catalog, arbitrary wav files for voice cloning,
    and reusable exported voice states.
  - The model card says processing a voice sample is slow and recommends keeping
    model and voice states in memory.
  - It currently lists unsupported pause control in the text input.
  - Source: https://huggingface.co/kyutai/pocket-tts
- Kyutai Pocket TTS public demo and docs:
  - The Kyutai TTS page exposes a Pocket TTS dropdown with labeled out-of-box
    voices such as conversation, reading, and multilingual entries.
  - The Pocket TTS docs list a larger built-in catalog: `alba`, `anna`,
    `azelma`, `bill_boerst`, `caro_davy`, `charles`, `cosette`, `eponine`,
    `eve`, `fantine`, `george`, `jane`, `jean`, `javert`, `marius`, `mary`,
    `michael`, `paul`, `peter_yearsley`, `stuart_bell`, `vera`, plus
    multilingual voices such as `estelle`, `giovanni`, `juergen`, `lola`, and
    `rafael`.
  - The voice repository includes multiple source datasets and license classes,
    including CC BY, CC0, and non-commercial sources. We must preserve source and
    license metadata in the UI.
  - Source: https://kyutai.org/tts/
  - Source: https://kyutai-labs.github.io/pocket-tts/
  - Source: https://huggingface.co/kyutai/tts-voices

## Corrections to the previous analysis

The older `20260706-manipulating_a_voice.md` is directionally right about
reference-driven prosody, but it overstates two things.

First, "target-speaker editing" for arbitrary uploaded references should not be
treated as a supported Qwen3-TTS public capability in our app. The official,
documented workflow is not "take any speaker and edit only their pace/emotion."
It is:

1. Use VoiceDesign to generate a short reference with the desired voice and
   delivery.
2. Feed that short reference into Base as the reusable clone prompt.

Second, Qwen3-TTS Base should not be treated as instruction-controllable in this
repo. Our Base path accepts `instruct` only for forward compatibility and logs or
ignores it. Do not wire style chips to hidden prompt injection until controlled
tests prove the deployed checkpoint and runtime respond consistently.

## Capability matrix

| Engine | Strength | Real controls | Not reliable |
| --- | --- | --- | --- |
| Qwen3-TTS Base | Best reusable clone engine in this app | Reference audio, seed, generation kwargs where supported by the package/runtime | Independent accent, energy, pause, style, or emotion controls |
| Qwen3-TTS VoiceDesign | Best way to create styled reusable references | Natural-language voice description while generating the reference clip | Editing an arbitrary existing speaker without identity drift |
| Qwen3-TTS CustomVoice | Instruction control over built-in speakers | `speaker`, `language`, `instruct` for the 9 shipped voices | User-uploaded / arbitrary speaker cloning |
| OmniVoice | Accent and pace reference generation | `instruct` attributes, `speed`, `duration`, prompt preprocessing/postprocessing | Free-form delivery style beyond the closed attribute vocabulary |
| Pocket TTS | Fast lightweight cloning and built-in voices | Reference voice state, built-in voice catalog, decode/runtime knobs | Style, accent, pause, or emotion control at generation time |

## Product model

Do not present "style" as magic per-generation emotional control. Present it as
a delivery pipeline with three layers:

1. Voice identity
   - The conceptual voice or speaker.
   - Examples: "Rosie", "Aussie assistant", "Marius", "Default mounted voice".

2. Delivery variant
   - A saved reference variant for that voice.
   - Examples: "Natural", "Calm", "Energetic", "Broadcast", "Storyteller".
   - This is the most important layer because cloning models actually follow it.

3. Output polish
   - Deterministic audio finishing after generation.
   - Examples: loudness normalization, mild compression, small pause shaping,
     small time-stretch.
   - This can improve usability but cannot turn one performance into a different
     acting performance.

## Style taxonomy

Start with five stable delivery variants:

| Variant | Reference target | Output polish target |
| --- | --- | --- |
| Natural | Conversational, neutral, modest pauses | LUFS normalization only |
| Calm | Slower, steadier, gentle energy, more room around punctuation | Mild slow stretch, pause +5-10%, warm EQ |
| Energetic | Brighter, tighter, more forward, fewer pauses | Mild fast stretch, pause -5-10%, light compression |
| Broadcast | Clear, projected, controlled, compact pauses | Presence EQ, compression, de-ess, pause -10% |
| Storyteller | Warm, expressive, narrational, deliberate pauses | Warm EQ, gentle compression, pause +5-15% |

`Ultra-clean` should be an output polish mode, not a personality style. It means
minimal flavor, stricter silence cleanup, and stable loudness for comparisons or
batch work.

## Reference generation workflows

### Workflow A: Qwen VoiceDesign reference

Use when the user wants a new designed voice, not necessarily an exact clone of
an existing uploaded speaker.

1. User chooses traits in VoiceDesign:
   - accent / language
   - demographics
   - register
   - texture / timbre
   - persona
   - delivery variant
2. Generate 8-12 second sample text with VoiceDesign.
3. Save the result as a voice-library reference.
4. Build/cache a Base `voice_clone_prompt` for that reference.
5. Use Base for normal Speak generation.

This is the official Qwen-compatible durable path.

### Workflow B: OmniVoice accent and tempo reference

Use when accent and pacing matter more than arbitrary emotional acting.

1. Compose OmniVoice `instruct` from its closed vocabulary.
2. Use documented accent tags for English output, especially `australian accent`
   for the user's Aussie use case.
3. Use `speed` and `duration` to generate multiple candidate references:
   - Natural: `speed=1.0`
   - Calm: `speed=0.85-0.95` or slightly longer `duration`
   - Energetic: `speed=1.08-1.18` or slightly shorter `duration`
4. Audition multiple short clips.
5. Save the best clips as delivery variants for the same conceptual voice.

This is the most practical path for Aussie accented voices today because Qwen
VoiceDesign may describe an Aussie-flavored voice, but OmniVoice has explicit
Australian accent support.

### Workflow C: Manual reference import

Use for user-supplied or externally generated voices.

1. Preserve the original uploaded reference unchanged.
2. Create a normalized derived reference for cloning:
   - mono
   - 24 kHz
   - trimmed leading/trailing silence
   - no heavy EQ or formant-changing processing
   - loudness normalized gently
3. Record reference metadata:
   - source kind: upload / VoiceDesign / OmniVoice / Pocket built-in / external
   - transcript
   - estimated duration
   - speaking-rate metrics
   - pause metrics
   - optional ASR confidence / transcript match
4. Let the user mark the imported reference as Natural, Calm, Energetic, etc.

Do not automatically claim an imported clip is a delivery variant. Measure and
label it based on actual audio.

### Workflow D: Pocket TTS built-in voices

Use for fast "ready to speak" voices.

> **Mechanism — verified against `pocket-tts==2.1.0` (2026-07-09).**
> `TTSModel.get_state_for_audio_prompt(x)` accepts **three** input kinds, so no
> custom download layer is needed:
> - a **named preset** string, e.g. `"alba"` (the package resolves it);
> - a **local wav path**, e.g. `"./ref.wav"`;
> - a **`hf://` path** into the voices repo, e.g.
>   `"hf://kyutai/tts-voices/expresso/ex03-ex01_happy_001_channel1_334s.wav"`.
>
> There are **26 documented named presets** (from the pocket-tts docs). English:
> `alba`, `anna`, `azelma`, `bill_boerst`, `caro_davy`, `charles`, `cosette`,
> `eponine`, `eve`, `fantine`, `george`, `jane`, `jean`, `javert`, `marius`,
> `mary`, `michael`, `paul`, `peter_yearsley`, `stuart_bell`, `vera`.
> Multilingual: `giovanni` (it), `lola` (es), `juergen` (de), `rafael` (pt),
> `estelle` (fr). Any other voice is reached via its
> `hf://kyutai/tts-voices/...` path. This is exactly the "symbolic name OR
> concrete asset" handling the voice model already anticipates.
>
> **`vera` is the priority voice for this plan's Australian-accent thesis** — a
> natural female Aussie-sounding voice (backed by `vctk/p229_023_enhanced.wav`,
> **CC BY 4.0** — commercially usable). Keep it in the curated default set.

1. Register built-in voices as source-labeled assets. Each stores the exact
   `get_state_for_audio_prompt` argument (preset name or `hf://` path) plus a
   license (see below). No files are copied into the repo.
2. Seed the curated default list with the eight named presets first (they need
   no path), then add a small set of `hf://` voices for variety/coverage.
3. Preserve human labels (gender / use-case) where the source documents them,
   e.g. `Alba (reading/character)`, `Fantine (reading)`, `Marius (reading)`.
   **Multilingual coverage** comes from `hf://` folders (e.g. `cml-tts/fr/` for
   French); do not assume undocumented named presets exist for other languages.

**Licensing — REQUIRED, licenses vary by voice (verified 2026-07-09):**
`kyutai/tts-voices` mixes licenses per folder — `voice-donations/` and
`voice-zero/` are **CC0**; `vctk/`, `cml-tts/fr/`, `alba-mackenna/` are
**CC BY 4.0**; `expresso/` and `ears/` are **CC BY-NC 4.0 (non-commercial
only)**; `unmute-prod-website` is **mixed per file**. Store the license on each
voice asset, surface it in the UI, and **default the curated catalog to CC0 /
CC BY voices**; gate or clearly badge non-commercial voices so they are never
presented as unrestricted for production use.
4. Do not treat Kyutai TTS 1.6B demo emotion voices as Pocket TTS style controls.
   The Kyutai page has a separate "Kyutai TTS 1.6B" area with labels such as
   `Sarcastic (US, f.)`, `Angry`, `Calming`, and `Narration`. Those are not the
   same as Pocket TTS generation-time emotion controls, and they should not be
   shown as Pocket TTS style chips unless we have local files and license-safe
   voice-state support for them.
5. Cache each selected voice state in memory or export it to safetensors for fast
   reload. The Pocket TTS docs explicitly recommend this because processing a
   prompt audio file is relatively slow.
6. Treat built-ins as fixed reference voices with known delivery, not adjustable
   personas. If a built-in says "reading", expect reading-like pacing; if it says
   "conversation", expect conversational pacing.

## Reference audio quality rules

For cloning quality, reference preprocessing matters more than post-processing.

Keep:

- 3-15 seconds of clean speech.
- A reference transcript matching the audio.
- One continuous delivery style per clip.
- Natural speech level, no clipping, no music/noise bed.
- Pauses that reflect the delivery you want the clone to inherit.

Avoid:

- Stitching clips with inconsistent ambience or emotional delivery unless the
  target voice is meant to inherit that instability.
- Long dead air at the start/end.
- Strong compression/EQ before cloning.
- Time-stretching a reference aggressively before cloning.
- Overly long clips; OmniVoice recommends 3-10 seconds, and long references can
  slow inference or reduce stability.

## Audio analysis metrics to add

Every saved reference variant should have cheap metadata. This lets the UI make
honest claims and helps compare variants.

Required metrics:

- `duration_seconds`
- `sample_rate`
- `lufs_integrated` or equivalent loudness estimate
- `peak_dbfs`
- `speech_rate_proxy`
  - words per second using known transcript
  - fallback: voiced frames per second if transcript unavailable
- `pause_count`
- `pause_total_seconds`
- `pause_ratio`
- `median_pause_ms`
- `longest_pause_ms`
- `source_model`
- `source_prompt`
- `source_generation_params`

Recommended implementation:

- Use Python audio tooling already compatible with the container.
- Keep this in `voice_library.py` or a helper module under `src/persona_forge`.
- Store metrics in each voice `meta.json`.
- Never discard the original uploaded reference.

## Post-processing pipeline

Post-processing is useful but must stay conservative. The goal is finishing, not
acting.

Apply after raw TTS generation and after the app's existing silence trim:

1. Loudness normalization
   - Normalize toward a target such as -20 to -23 LUFS (measured with
     `pyloudnorm`; see resolved decisions above).
   - Keep true peak below about -1.5 dBTP (`pyloudnorm` true-peak +
     `audio_post.limit_peak`).

2. EQ (`scipy.signal` biquad; already installed)
   - High-pass around 70-80 Hz.
   - Small presence boost for Broadcast/Energetic.
   - Small warmth boost for Calm/Storyteller.

3. Dynamics
   - None or light compression for Natural (`audio_post.compress`).
   - Light compression for Energetic/Broadcast.
   - Avoid pumping; TTS output is often already level.

4. Time-stretch (pitch-preserving; `librosa.effects.time_stretch`, already
   installed) — **ships in Phase 4 v1** (decided 2026-07-09).
   - Keep subtle. Calm uses -3% to -8%; Energetic uses +3% to +8%.
   - Do not exceed +/-10% without explicit listening approval (hard guardrail).
   - Preserve pitch — never use naive resampling (which shifts pitch/timbre).

5. Pause shaping
   - Detect silences by energy threshold.
   - Modify only internal pauses above a minimum threshold.
   - Calm/Storyteller: lengthen selected pauses by 5-15%.
   - Energetic/Broadcast: shorten selected pauses by 5-15%.
   - Do not remove punctuation-like pauses completely.

Post-processing must be optional per request and recorded in job metadata.

## Generation-time knobs

Only expose knobs that the active backend truly honors.

Qwen3-TTS Base:

- `voice_id` / `voice_clone_prompt`: real.
- `seed`: real if the runtime path uses it.
- `instruct`: accepted in API for compatibility, but no-op in this app until
  proven otherwise.
- `style_preset`: should select a saved reference variant and/or post-processing
  recipe, not prompt injection.

Qwen3-TTS VoiceDesign:

- `instruct`: real for generating a reference clip.
- `language`: real.
- `sample_text`: real and important because prosody in the reference text affects
  the later clone.

OmniVoice:

- `instruct`: real but closed vocabulary.
- `speed`: real.
- `duration`: real and overrides speed.
- `postprocess_output`: relevant when exact duration matters.

Pocket TTS:

- `voice_state`: real.
- built-in voice name or prompt wav: real.
- exported voice state: real and recommended for performance.
- `temp`, EOS, decode-step knobs: runtime-feel / quality knobs, not semantic
  style controls.
- pauses in input text are explicitly not supported at the model-card level
  today.

## Backend architecture

### Voice library model

Evolve the voice library from "flat voice list" to "voice families with variants"
without breaking existing `voice_id` behavior.

Minimal metadata shape:

```json
{
  "voice_id": "vd_abc123",
  "family_id": "family_rosie",
  "display_name": "Rosie",
  "variant_name": "Calm",
  "variant_kind": "calm",
  "source": "omnivoice",
  "source_model": "k2-fsa/OmniVoice",
  "sample_text": "Welcome to Rosie's...",
  "reference_wav": "reference.wav",
  "original_reference_wav": "original.wav",
  "metrics": {
    "duration_seconds": 9.8,
    "pause_ratio": 0.18,
    "median_pause_ms": 420,
    "words_per_second": 2.4
  },
  "processing": {
    "reference_preprocess": ["mono_24khz", "trim_edges", "loudness_normalize"],
    "speak_postprocess_default": "default"
  }
}
```

Existing callers can continue sending `voice_id`. New UI can group by
`family_id` and variant fields.

### Endpoint additions

Add these as backward-compatible optional fields:

- `/generate`
- `/generate/async`
- `/v1/audio/speech`

Request fields:

- `voice_id`: existing.
- `voice_variant_id`: optional alias for a `voice_id`; useful once UI groups
  variants.
- `style_preset`: optional output polish recipe.
- `postprocess`: optional boolean or object.
- `builtin_voice`: Pocket TTS only; explicit built-in selection.

Response / job metadata:

- `voice_id`
- `voice_family_id`
- `variant_kind`
- `style_preset`
- `postprocess_applied`
- `audio_seconds`
- `rtf`
- `frames_generated`
- `seed`

Progress endpoint additions:

- `audio_seconds_generated = frames_generated * 0.08` for Qwen 12.5 Hz frame
  timing.
- `live_rtf_estimate = elapsed_seconds / max(1, audio_seconds_generated)`.
- Keep existing fields optional-compatible.

### Built-in Pocket voices

Prefer one route:

- `GET /voices/built-in`

Return:

```json
{
  "voices": [
    {
      "voice_id": "pocket:alba",
      "backend": "pocket_tts",
      "display_name": "Alba",
      "source": "kyutai/tts-voices",
      "license": "see_source",
      "requires_backend": "pocket_tts"
    }
  ]
}
```

Do not blend built-in voices into user-created voices without a source label.

Catalog guidance:

- Keep a small curated default list for Speak so the dropdown is useful. All of
  these are named presets (no path needed):
  - `vera` - **female, natural Aussie-sounding — priority voice for this plan**
    (vctk/p229, CC BY 4.0)
  - `jane` - female conversation
  - `anna` - female conversation
  - `fantine` - female reading
  - `alba` - reading / character-acted source
  - `marius` - male reading
  - `jean` - male reading
- Keep an "All Pocket voices" expander/search: the remaining named presets (26
  total — see Workflow D) plus `hf://kyutai/tts-voices` paths for the fuller
  catalog (incl. multilingual folders like `cml-tts/fr/`).
- Store the exact `get_state_for_audio_prompt` argument (preset name or `hf://`
  path) on each asset.
- Store per-voice license/source from `kyutai/tts-voices` and surface it; do not
  assume every voice is commercially usable (CC0 / CC BY / CC BY-NC mix — see
  Workflow D). Cache resolved states with `export_model_state()` /
  `import_model_state()` (`.safetensors`) to avoid repeated slow prompt
  processing.
- If we add TTS 1.6B emotion-labeled voices later, keep them under a separate
  source family, not Pocket TTS built-ins.

### Post-processing implementation

Add a small module:

- `src/persona_forge/audio_style.py`

This module is a thin **orchestration layer over the existing
`src/persona_forge/audio_post.py`** — it defines named presets and reference-metric
extraction, but delegates all low-level DSP (compression, normalization, peak
limiting, fades, trimming) to `audio_post.py`. Do not duplicate those
primitives. Any metric or effect that `audio_post.py` cannot express with its
current numpy-only toolkit is gated on the DSP-dependency decision in "Codebase
grounding" above.

Responsibilities:

- `analyze_reference(wav, sr, transcript=None) -> dict` — reference metrics.
  Reuse `audio_post` helpers for cheap stats; use `librosa` for pause/onset
  detection, `pyloudnorm` for LUFS, and the whisper transcript (when available)
  for `words_per_second`. Per the resolved decisions above, these libs are
  approved for `audio_style.py`.
- `preprocess_reference(input_path, output_path) -> metadata` — mono/24kHz/trim/
  gentle normalize using `audio_post` primitives; never overwrites the original.
- `apply_style_preset(wav, sr, preset, options=None) -> (wav, sr, metadata)` —
  maps a named polish preset to `audio_post` calls and records what was applied.

Implementation constraints:

- No long subprocess chains in request path.
- Use already-installed libs (`librosa`/`scipy`) plus the one approved new dep
  (`pyloudnorm`). Add `pyloudnorm` to `requirements/requirements-runtime.txt` in
  Phase 4; no SoX/FFmpeg — do not introduce subprocess-based DSP.
- `audio_post.py` stays numpy-only (locked stitch-path decision); the richer
  libs live in `audio_style.py`.
- Fail open for post-processing: if finishing fails, return raw generated audio
  with a warning in metadata rather than failing generation.
- Fail closed for reference preprocessing when saving a new voice, because bad
  references poison future generations.

## Speak page redesign

The Speak page should be the place to use saved voices and variants. It should
not try to duplicate VoiceDesign or OmniVoice authoring.

### Layout

Use five compact zones:

1. Header / runtime status
   - Runtime badge: OpenVINO, PyTorch, Pocket TTS.
   - Idle-unloaded or reloading state.
   - Link to Runtime page.

2. Text editor
   - Large text area.
   - Character/word count.
   - No fake pre-generation ETA.
   - Live ETA only once `/generate/progress` has backend data.

3. Voice and variant selection
   - Group by:
     - Mounted reference
     - Your voices
     - Built-in voices
   - Inside "Your voices", group variants under the conceptual voice.
   - Show source badges: VoiceDesign, OmniVoice, Upload, Pocket.
   - Show small metrics only when useful:
     - "Calm - slower pauses"
     - "Energetic - faster delivery"

4. Delivery / polish controls
   - Delivery variant is a voice selection concern.
   - Output polish is a small segmented control:
     - Off / Neutral / Broadcast / Clean
   - If `style_preset` has no real effect for active backend, do not show it as
     active. Show disabled tooltip or hide it.

5. Generate / progress / result
   - Async generation as today.
   - Backend progress label from real progress fields.
   - Audio player with:
     - download
     - loop
     - playback rate
     - seed lock
     - compact diagnostics toggle

### UI honesty rules

- Do not label chips "Calm" or "Energetic" if they only send a no-op field.
- If a style is implemented by post-processing only, label it "Output polish".
- If a style is implemented by a saved reference variant, label it as a variant.
- If VoiceDesign/OmniVoice will generate a new variant, take the user to the
  authoring flow instead of silently generating a hidden reference in Speak.

## Dual-audience UX and design system (non-negotiable)

The premium visuals below are only half the mandate. The product must satisfy
**two audiences at once**, and every UI task in this plan is judged against both:

- **The DAW/audio-engineer user** gets real, precise, pro-grade controls
  (LUFS/true-peak meters, EQ, compression, crossfades, region editing, numeric
  fields, keyboard nudging) that behave the way they expect from a VST.
- **The beginner** can accomplish the same goals without knowing any of that
  vocabulary, guided by presets, plain-language labels, tooltips, and inline
  help — never blocked by jargon, never shown a wall of knobs.

This is achieved through **progressive disclosure, not a dumbed-down mode.**

### Progressive disclosure model

- **Simple by default.** Every audio surface opens in a clean state: pick a
  voice/variant, pick a named preset (Natural/Calm/Broadcast/…), generate. No
  raw DSP is visible until asked for.
- **Advanced drawers.** Pro controls (EQ curve, compression ratio, LUFS target,
  time-stretch %, region inspector numeric fields) live behind a clearly labeled
  "Advanced" disclosure on each surface — present, one click away, never in the
  beginner's face.
- **Presets are the beginner on-ramp AND the pro starting point.** A named
  preset sets all the advanced values; the pro can open Advanced and fine-tune
  from there. The two views always stay in sync (changing a preset updates the
  advanced values; editing advanced values marks the preset "Custom").
- Optional per-user **density/"Pro mode"** preference that defaults advanced
  drawers open — remembered, not required.

### Self-explanatory by construction

- **Every control has a plain-language label and a tooltip.** Any term an
  audio engineer takes for granted but a beginner won't — LUFS, dBTP, true-peak,
  crossfade, compression ratio/threshold, high-pass, `guidance_scale`,
  `num_step`, voice state — carries a one-sentence "what this does / when to use
  it" tooltip in everyday language.
- **Promote a single shared help affordance.** An `InfoIcon`-style component
  already exists under `frontend/src/components/OmniVoice/InfoIcon.tsx`; promote
  it to a shared component and use it consistently for every jargon term.
- **A small glossary** (hover-card or a help panel) defines the recurring audio
  terms once, linked from the tooltips.
- **Guided empty/first-run states.** Empty Speak, empty Library, empty Stitch,
  and the first generation each show a short "here's what to do" affordance
  instead of a blank canvas — with a one-click sample/example where useful.
- **Honest, human microcopy** everywhere (this reinforces the UI honesty rules
  above): labels describe the real effect, tooltips set expectations, and any
  control that's a no-op on the active backend is disabled with a tooltip
  explaining why.

### Shared design system (the cohesion spine)

To read as one modern 2026 app rather than a set of pages, all audio surfaces
draw from one system, not per-page styling:

- **Design tokens** — a single source for color, spacing, type scale, radii,
  elevation/shadow, blur/glass, and motion timing. Every component consumes
  tokens; no ad-hoc hex values or magic numbers.
- **Shared components only** — the `AudioDeck`/`MiniAudioDeck`/`WaveformLane`/
  `LevelMeter`/`AudioStatsStrip`/`InfoIcon` set (below) is used everywhere;
  surfaces compose these rather than reinventing players, meters, or waveforms.
- **Consistent interaction grammar** — the same gestures mean the same thing on
  every surface (click-to-seek, drag handles, hover readouts, Advanced
  disclosure, preset chips).

### Accessibility (WCAG-minded, required)

- **Keyboard**: every control operable without a mouse; visible focus rings;
  logical tab order; arrow-key nudging in editors (with a fine-nudge modifier).
- **Screen readers**: canvas/SVG waveforms and meters are decorative visuals, so
  pair them with real ARIA labels / text equivalents (duration, position, level,
  LUFS) — never let critical state exist only as pixels.
- **Contrast**: meet WCAG AA for text and essential UI against both light and
  dark themes; the cyan/magenta/amber accents are for audio signal, not for
  conveying text meaning alone.
- **Motion**: honor `prefers-reduced-motion` (disable idle/entrance animation,
  keep functional playhead/progress). Never rely on animation to convey state.

### Definition of done for any UI surface in this plan

A surface is complete only when: it opens in a simple state a beginner can use;
its pro controls exist behind Advanced; every jargon term has a tooltip; it
composes the shared audio components and tokens; it is fully keyboard- and
screen-reader-operable; it honors reduced-motion; and it looks identical in
grammar to the other surfaces. Verify these in the Playwright pass, not just the
visuals.

## Premium audio UI direction

The frontend should lean into a modern audio-tool / premium VST visual language,
but stay usable as an operational TTS app. The goal is "high-end studio utility,"
not a decorative music-player skin.

This visual system applies everywhere audio is created, selected, edited, or
played:

- Speak result deck
- Voice Library and voice variant browser
- VoiceDesign previews
- OmniVoice segment rack and take previews
- Stitch Studio / timeline editor
- reference import / analysis screens
- audio post-processing controls

Runtime and settings pages can remain quieter operational screens, but any audio
preview or audio metric shown there should still use the same waveform, meter,
badge, and analysis components.

Current state:

- `AudioPlayer.tsx` is intentionally compact: play/pause button, decoded peaks,
  progress, duration-aware waveform.
- `Waveform.tsx` already has a strong base:
  - cool cyan-to-magenta bar color ramp
  - amber playhead
  - subtle DAW-style grid / center line
  - Framer Motion bar entrance / idle animation
- `StitchTimeline.tsx` has useful clip waveform lanes and trim/fade concepts,
  but those visuals are not yet part of a coherent shared audio design system.

Recommended visual system:

### Audio surface hierarchy

Create reusable audio display components so Speak, VoiceDesign, OmniVoice, and
Stitch Timeline all share one premium vocabulary.

- `AudioDeck`
  - full result player for Speak
  - includes transport, waveform, meters, duration, seed, download, loop, speed
- `MiniAudioDeck`
  - compact preview player for voice cards, variants, and generated takes
- `WaveformLane`
  - shared waveform renderer for clips, generated audio, and references
- `LevelMeter`
  - VU / peak meter for playback and analysis
- `SpectralAccent`
  - optional low-resolution spectrogram strip for premium "audio workbench" feel
- `AudioStatsStrip`
  - LUFS, peak, duration, RTF, pause ratio, words/sec

Do not keep reimplementing waveform rendering in separate components. The
existing `Waveform.tsx` should become the canonical waveform renderer, with
variants for full, compact, and timeline modes.

### Waveform upgrades

Improve the existing waveform without making it noisy:

- Add a glassy recessed track:
  - inner shadow
  - faint top highlight
  - subtle bottom vignette
  - low-contrast grid lines
- Add a "played" overlay that feels like an illuminated meter lane:
  - current cyan/magenta bar colors can stay
  - unplayed bars should be desaturated and lower-alpha
  - played bars can get restrained glow only at higher peaks
- Add peak hold markers:
  - tiny horizontal ticks on loud bars
  - useful for broadcast/clean polish work
- Add pause markers:
  - vertical amber or slate markers at detected long pauses
  - visible only when analysis metadata exists
  - this directly supports the central product problem: comparing reference
    pause structure
- Add selection regions:
  - shaded intro/outro trim zones for references
  - selected region for "use this as clone reference"
- Add loop region visuals:
  - bracket handles if loop is enabled
  - no extra text required
- Add hover readout:
  - time under cursor
  - optional amplitude/segment label in advanced mode
- Add click-to-seek:
  - predictable and required for a premium player

Rendering guidance:

- Keep SVG/HTML bars for simple short waveforms.
- Use `<canvas>` for large waveforms, spectrograms, or timeline lanes with many
  clips to avoid DOM cost.
- Cache decoded peaks by blob hash or voice/audio id so switching tabs does not
  re-decode the same audio repeatedly.

### Meters and analyzers

Add studio-style meters where they carry information.

Speak result:

- stereo-looking dual mono meter even though output is mono:
  - left/right mirrored meter reads familiar and premium
  - label it as output level only in advanced details if needed
- peak + RMS display:
  - fast peak bar
  - slower RMS fill
  - tiny peak-hold line
- LUFS / peak badges in the advanced strip after analysis:
  - `-20.4 LUFS`
  - `-1.2 dBTP`
  - `RTF 5.8`

Reference/variant cards:

- Tiny meter sparkline or "voice fingerprint":
  - pause ratio
  - speaking rate
  - loudness
- Do not animate meters on every card constantly. Animate only while previewing
  that specific item.

Post-processing panel:

- Use VST-style controls, but keep them domain-specific:
  - segmented controls for style/polish mode
  - sliders for intensity, speed stretch, pause shaping
  - small gain-style meter for output level
  - toggles for limiter / normalize / de-ess
- Use knobs sparingly. Knobs look audio-native, but are worse for precise mouse
  control in a web app unless implemented carefully. Prefer horizontal sliders
  for numeric settings.

### Spectrogram and "voice fingerprint" visuals

Add a low-resolution spectrogram only where it adds premium value:

- reference detail drawer
- generated result advanced mode
- compare two variants view

Do not make spectrograms always visible in the main Speak form. They are rich but
can become visual clutter.

Useful fingerprint views:

- Pause map:
  - timeline with speech blocks and silence gaps
  - this is the most important analysis visual for the user's pacing problem
- Rate curve:
  - words/sec or voiced-energy proxy over time
- Loudness envelope:
  - RMS envelope over waveform
- Delivery badges:
  - `slower pauses`
  - `tight delivery`
  - `reading source`
  - `conversation source`

### Voice and variant cards

Make voice selection feel like browsing a premium preset library.

Each voice family row:

- display name
- source badge: VoiceDesign, OmniVoice, Upload, Pocket
- small waveform/fingerprint preview of the selected/default variant
- variant count
- last-used or favorite marker

Each variant item:

- variant name: Natural, Calm, Energetic, Broadcast, Storyteller
- source/use-case label:
  - `Pocket: conversation`
  - `Pocket: reading`
  - `OmniVoice: australian accent`
  - `VoiceDesign: designed reference`
- metrics chips:
  - duration
  - words/sec
  - pause ratio
- inline mini play button
- active variant highlighted with a thin luminous edge, not a heavy filled card

Avoid nesting cards inside cards. Use rows, bands, and compact panels.

### Speak page premium result deck

The generated result should feel like a finished audio module.

Recommended layout:

- left: transport cluster
  - play/pause
  - stop/restart
  - loop
- center: large waveform lane with pause markers and playhead
- right: compact meter column
  - peak/RMS meter
  - duration
  - RTF
- lower rail:
  - download
  - playback speed
  - seed lock
  - advanced drawer

State visuals:

- Idle:
  - quiet recessed waveform placeholder
  - no fake activity
- Generating:
  - animated scanning lane / skeleton waveform
  - progress should be tied to backend frames when available
  - avoid random "music visualizer" animations that imply real audio exists
- Completed:
  - real waveform
  - real duration
  - real seed
  - real meters once decoded
- Failed:
  - waveform lane dims
  - error state appears below or above, not over the waveform

### Stitch timeline polish

The stitch timeline can become the most VST-like surface:

- Clips should look like DAW regions:
  - waveform fill
  - trim overlays
  - fade handles
  - clip title in top rail
  - source badge
- Add snap/grid affordances:
  - second markers
  - optional beat-like grid is not relevant; use time grid only
- Add transition visuals:
  - crossfade overlap shown as diagonal gradients
  - silence insert shown as a thin gap block
- Add per-clip meters only when previewing a clip.
- Show the final stitched waveform after render as a master lane.

### Where audio engineering controls live

Audio engineering should be split by job:

1. Speak
   - Fast generation and playback.
   - Only simple output polish controls:
     - Off / Clean / Broadcast / Warm
     - playback speed
     - download format
   - No detailed waveform surgery here.

2. Voice Library
   - Reference management and analysis.
   - Shows metrics and fingerprints:
     - pause ratio
     - speaking rate
     - loudness
     - peak level
   - Lets users compare variants and choose defaults.
   - Allows safe reference-level actions:
     - normalize reference
     - trim leading/trailing silence
     - mark variant kind
     - export/cache Pocket voice state

3. VoiceDesign / OmniVoice authoring
   - Generates candidate references.
   - Uses mini decks and take comparison.
   - Lets users save selected takes as voice variants.
   - Should not become the full audio editor.

4. Stitch Studio
   - The main audio-engineering workspace.
   - This is where detailed non-destructive edits live:
     - region selection
     - insert silence
     - trim
     - fades and crossfades
     - clip gain
     - gain automation
     - pause shaping
     - de-click / de-pop style fixes where feasible
     - master polish chain

If a user clicks "edit audio" from Speak or Library, route to Stitch Studio with
the selected audio already loaded. Do not overload the primary Speak page.

### Region-based waveform editing

Yes, region-level editing should be a first-class goal. It is the right place to
solve problems such as a stitched OmniVoice voice where one segment has a hard
sound, an awkward pause, or mismatched loudness.

Model:

- Keep edits non-destructive.
- Store an edit decision list rather than rewriting the source audio immediately.
- Render a new final WAV/MP3 only when previewing/exporting the stitch.
- Preserve the original segment audio.

Suggested edit model:

```json
{
  "clip_id": "seg_001",
  "edits": [
    {
      "type": "gain",
      "start_ms": 1240,
      "end_ms": 1510,
      "gain_db": -3.5,
      "fade_in_ms": 15,
      "fade_out_ms": 35
    },
    {
      "type": "insert_silence",
      "at_ms": 2230,
      "duration_ms": 180
    },
    {
      "type": "fade",
      "start_ms": 0,
      "end_ms": 80,
      "curve": "equal_power"
    }
  ]
}
```

MVP region edits:

- Select region on waveform.
- Adjust clip gain for selected region.
- Insert silence before/after selected region.
- Delete or mute selected region.
- Add fade in / fade out to selected region.
- Split clip at selection boundaries.
- Drag clip boundaries and fade handles.

Next edits:

- Pause shaping:
  - select a silence
  - lengthen or shorten it
  - normalize selected pause lengths across a stitched voice
- Hard-sound reduction:
  - selected-region gain dip
  - short attack/release envelope
  - optional de-ess preset for sibilance
  - optional plosive low-cut for thumps
- Region EQ:
  - high-pass selected region
  - presence reduction for harsh consonants
  - warmth boost for thin segments
- Crossfade between adjacent clips.
- Match loudness between clips.

Advanced / later:

- Spectral repair-style editing.
- True de-reverb or source separation.
- Formant/pitch correction.
- Automatic "make this segment sound like the others" matching.

Those advanced items are possible only with more DSP/model work and should not be
promised in the first implementation.

UI interactions:

- Drag across waveform to create a time selection.
- Selection shows handles at both ends.
- Floating compact toolbar appears near the selection:
  - gain
  - silence
  - fade
  - split
  - mute
  - more
- Inspector panel shows precise numeric fields:
  - start
  - end
  - duration
  - gain dB
  - fade times
- Keyboard affordances:
  - delete mutes/removes selected region depending current mode
  - arrow keys nudge selection
  - modifier key for fine nudge
- All edits are undoable.

Rendering:

- Region edits apply per clip before the master chain.
- Master polish applies after clips are stitched.
- Waveform preview should show the effective edited audio:
  - gain dips visually lower the waveform
  - inserted silence appears as a gap block
  - fades show diagonal overlays
  - muted regions show dimmed waveform

This makes Stitch Studio the "audio engineering" home while keeping Speak fast
and Library organized.

### Motion and interaction

Use motion like an audio instrument, not a marketing page.

Good motion:

- bar entrance when waveform first decodes
- playhead glide
- meter decay
- subtle active glow while playing
- smooth trim/fade handle movement
- small pressed states on transport controls

Avoid:

- large bouncing panels
- decorative background blobs
- animated elements unrelated to real audio state
- continuous movement when nothing is playing/generating

Respect reduced motion:

- disable waveform entrance staggering
- disable idle pulsing
- keep playhead and progress movement because they communicate state

### Visual palette

The current cyan/magenta/amber meter palette is good for the audio surfaces
because it reads like plugin metering and avoids making the whole app one hue.

Keep:

- cyan/teal for normal signal
- magenta/rose only for hot peaks or expressive accent
- amber for playhead/cursor/selection
- neutral dark graphite for panel chrome

Avoid:

- making the whole page purple-blue
- heavy gradients as section backgrounds
- glowing every control
- bright colors on non-audio controls

### Technical implementation plan

Add visual polish in phases:

1. Shared waveform renderer
   - Promote `Waveform.tsx` to support modes:
     - `compact`
     - `deck`
     - `timeline`
   - Add click-to-seek.
   - Add optional pause markers.
   - Add optional trim/selection regions.

2. Result deck
   - Upgrade `AudioPlayer.tsx` into `AudioDeck`.
   - Add download, loop, playback speed, stop/restart.
   - Add peak/RMS meter driven by Web Audio during playback.

3. Voice preset visuals
   - Add `MiniAudioDeck` for voice cards and variants.
   - Add metrics chips from reference analysis.
   - Add source/use-case badges.

4. Analysis visuals
   - Add pause map and loudness envelope.
   - Add low-resolution spectrogram only in advanced drawers.

5. Timeline polish
   - Reuse `WaveformLane` in `StitchTimeline.tsx`.
   - Add DAW-region styling, fade handles, transition visuals.

Verification:

- Use Playwright screenshots for desktop and mobile.
- Verify text does not overlap inside buttons/cards.
- Verify canvas/SVG waveform is nonblank after audio decode.
- Verify generated state, completed state, failed state, and no-audio state.
- Verify `prefers-reduced-motion` behavior.
- Verify large/long audio does not create thousands of DOM nodes.

## Cross-cutting refinements (folded in 2026-07-09)

Four refinements that cut across the sections above. Each says exactly what to
build and which existing section/phase it modifies, so it can be implemented
without re-deriving context.

### R1. Reference quality gate on save (modifies Phase 2 + Workflow C)

A bad reference silently poisons every future clone made from it, so saving one
must run a quality check first — not just passive preprocessing.

- **When:** on every reference save/import (VoiceDesign save, OmniVoice hero save,
  and manual upload — Workflow C), before the reference is written to the library
  and before any Base/Pocket clone prompt is built from it.
- **What:** run `analyze_reference` (see "Audio analysis metrics") and compute a
  0–100 **reference quality score** from cheap, explainable checks:
  - clipping / true-peak over ceiling → hard fail
  - duration outside ~3–15s (OmniVoice ideal 3–10s) → warn (too short) / warn
    (too long, slower + less stable)
  - excessive leading/trailing or internal silence (high `pause_ratio`) → warn
  - low SNR / noise floor estimate → warn
  - very low or very high speaking rate vs the target variant → info
- **Behavior:** hard-fail conditions (clipping) **block** save with a clear,
  plain-language reason and a one-click "auto-fix" where possible (trim edges,
  normalize, peak-limit via `audio_post`). Warn conditions allow save but surface
  a badge on the voice ("needs review", reusing the existing `needs_review`
  meta flag pattern in `voice_library.py`). Store the score + failed checks in
  `meta.json`.
- **Why it matters:** this is the cheapest possible guardrail against the single
  worst failure mode (garbage reference → all downstream generations degraded),
  and it directly reinforces the UI-honesty ethos: the library never claims a
  reference is good when the metrics say otherwise.

### R2. Variant A/B compare as a first-class feature (modifies Speak/Library UI + Validation suite)

The whole thesis is "different reference variants produce materially different
delivery." Users — and the validation suite — need to *hear* that directly.

- **Surface:** a compare mode (in Voice Library, and reachable from Speak's voice
  picker) that loads two variants of the same family side by side.
- **Behavior:** render the same text with both variants; play them
  back-to-back or with **synced transport** (one play button drives both,
  aligned to start). Show both waveforms stacked with a shared time axis, each
  with its pause markers, plus an `AudioStatsStrip` diff (duration, words/sec,
  pause ratio, LUFS) highlighting the deltas.
- **Reuse:** compose the shared `WaveformLane` / `AudioStatsStrip` / `MiniAudioDeck`
  components; do not build a bespoke player. This subsumes the "compare two
  variants view" mention in the premium-UI section — promote it from a
  spectrogram detail to a real tool.
- **Ties to validation:** this is the operator's instrument for the pass criterion
  "variant references produce materially different pacing before post-processing."
  A/B compare should be the screen used to sign that off.

### R3. Single pause-detection source of truth (architectural invariant)

Pause information appears in three places — `analyze_reference` metrics
(`pause_count`, `pause_ratio`, `median_pause_ms`), the waveform **pause markers**,
and the polish pipeline's **pause-shaping** step. These must all use **one**
pause-detection implementation.

- **Rule:** implement pause detection once (energy-threshold + minimum-gap, in
  `audio_style.py`, reusing `audio_post` primitives) and have every consumer call
  it. The frontend waveform markers must be driven by the **same** detected pause
  boundaries the backend computed (ship them in the analysis payload), not a
  separate client-side heuristic.
- **Why:** if the waveform draws a pause tick where the metric says there's no
  pause — or pause-shaping lengthens a gap the UI never marked — the tool
  contradicts itself and users stop trusting it. Define the pause threshold and
  minimum-gap as shared named constants and document them once.

### R4. "Why this label" transparency (modifies UI honesty rules + result deck)

Every honesty claim should be inspectable, which also teaches the beginner
(dual-audience mandate).

- **What:** any variant label (Natural/Calm/…) and any output-polish label
  (Neutral/Broadcast/…) is clickable to reveal exactly what it did — for a
  variant: its source (VoiceDesign/OmniVoice/upload), instruct/params, and
  measured metrics; for polish: the ordered list of applied steps (the
  `applied_steps` metadata from `audio_style.apply_polish`, e.g. "LUFS normalize
  → high-pass 75 Hz → −4% time-stretch → pause +8%").
- **Where:** an "advanced drawer" on the Speak result deck, and a popover on
  variant chips in the picker. Plain-language, one line per step, with the
  jargon-term tooltips from the dual-audience section.
- **Why:** it makes "variant vs polish vs no-op" concrete instead of a marketing
  word, closes the loop on the UI-honesty rules, and turns the pipeline into a
  teaching surface.

## Implementation phases

### Phase 1: Speak UX cleanup and progress truth

No generation behavior changes.

Tasks:

- Refactor `SpeakPage.tsx` into local sections.
- Remove static `estimateInitialEta`.
- Add richer `GenerateJobProgress` fields:
  - `audio_seconds_generated`
  - `live_rtf_estimate`
- Upgrade `AudioPlayer`:
  - download
  - loop
  - playback speed
- Add advanced diagnostics toggle.

Validation:

- `python scripts/validate_repo.py`
- frontend build/test command used in this repo
- manual browser check for OpenVINO/PyTorch/Pocket status rendering

### Phase 2: Voice variants in the library

Make style references first-class.

Tasks:

- Extend voice `meta.json` with family/variant/source/metrics fields.
- Add reference analysis on save.
- Keep old flat `voice_id` behavior working.
- Update `/voices` response with optional grouping metadata.
- Update `VoiceSelector` to group variants.

Validation:

- Existing voices still list and generate.
- New VoiceDesign and OmniVoice saved references appear under correct family.
- Uploaded reference preserves original file and derived normalized file.

### Phase 3: Pocket built-in voices

Expose built-in Pocket voices safely. Mechanism is verified (see Workflow D):
`get_state_for_audio_prompt` takes a named preset, a local wav path, or an
`hf://kyutai/tts-voices/...` path — no custom downloader is required.

Tasks:

- Add `GET /voices/built-in`.
- Add `builtin_voice` request handling for Pocket TTS — the value is the preset
  name or `hf://` path passed straight to `get_state_for_audio_prompt`.
- Cache built-in voice states in memory; optionally persist with
  `export_model_state()` / `import_model_state()` (`.safetensors`).
- Seed the catalog with the 26 named presets (see Workflow D), surfacing `vera`
  as the priority female Aussie voice, then add a curated set of `hf://` voices
  (prefer CC0 / CC BY folders).
- Add source and per-voice license metadata for each built-in voice.
- Add UI grouping:
  - Pocket built-ins: conversation
  - Pocket built-ins: reading
  - Pocket built-ins: multilingual
  - Pocket built-ins: other / unknown
- Do not expose this control when backend is not Pocket TTS unless there is a
  deliberate cross-backend reference conversion path.

Validation:

- Built-in voice generates through Pocket TTS.
- Non-Pocket backend rejects or hides `builtin_voice`.
- Voice-state caching avoids repeated slow prompt processing.
- Demo labels match Kyutai's public naming where possible.
- Non-commercial voices are not presented as safe for unrestricted production
  use.

### Phase 4: Output polish

Add conservative deterministic finishing.

Tasks:

- Add `pyloudnorm` to `requirements/requirements-runtime.txt` (the one approved
  new dependency; see resolved decisions). Confirm it imports in the container.
- Implement `audio_style.py` as a thin layer over `audio_post.py`, using
  `librosa`/`scipy`/`pyloudnorm` for LUFS, EQ, and pitch-preserving time-stretch.
- Implement Neutral/Clean/Broadcast polish first (loudness + EQ + dynamics).
- Add Calm/Energetic (incl. pause-shaping and pitch-preserving time-stretch,
  ±3–8%, guardrail ±10%) and Storyteller after a first listening pass.
- Add applied-step metadata to completed jobs.

Validation:

- Measure added latency on dockermisc1 (note first-call `librosa`/`numba` JIT
  warmup separately from steady-state):
  - 3 second audio
  - 10 second audio
  - 60 second audio
- Confirm LUFS/true-peak targets are actually hit (measure output with
  `pyloudnorm`) and that true-peak stays under the ceiling.
- Confirm time-stretch preserves pitch (no timbre shift) within ±8%.
- Listen A/B for at least:
  - Qwen Base reference
  - Pocket TTS reference
  - OmniVoice-generated Aussie reference
- Confirm artifacts are not worse than raw output.

### Phase 5: Style authoring workflows

Connect Speak to VoiceDesign/OmniVoice without hiding the machinery.

Tasks:

- Add "Create variant" action from a voice family.
- For Aussie accents, route to OmniVoice by default.
- For new Qwen-designed personas, route to VoiceDesign.
- Save generated references as variants.

Validation:

- User can create Natural/Calm/Energetic variants for the same conceptual voice.
- Speak can select and generate from each variant.
- Metrics show expected pause/speed differences.

## Validation suite for "we know it works"

Do not ship broad style claims until this matrix passes.

Test text:

- Short greeting with comma and period.
- Multi-sentence paragraph with punctuation.
- Long paragraph with clauses and quote-like phrasing.
- The actual "Welcome to Rosie's" script.
- An Aussie-accent target prompt.

References:

- Original "Welcome to Rosie's" reference.
- OmniVoice stitched reference.
- OmniVoice Aussie Natural.
- OmniVoice Aussie Calm.
- OmniVoice Aussie Energetic.
- One VoiceDesign-created reference.
- One Pocket built-in.

Measurements:

- Generated audio duration.
- Reference vs output words/sec.
- Pause ratio.
- Median and longest pauses.
- RTF / latency.
- Peak RSS if backend changes.

Listening notes:

- Accent retained?
- Identity retained?
- Pace materially changed?
- Pauses match intended variant?
- Any artifacts from post-processing?
- Does longer text drift?

Pass criteria:

- Variant references produce materially different pacing before post-processing.
- Output polish improves presentation without creating obvious artifacts.
- The UI labels match what the backend actually did.
- No new model memory behavior violates the one-model-at-a-time constraint.

## Workarounds and alternatives

If the fully integrated path is too expensive:

- Keep style creation offline:
  - Generate reference variants manually with OmniVoice or VoiceDesign.
  - Import them into the voice library.
  - Speak only selects saved variants.

- Prefer OmniVoice for accented reference authoring:
  - Especially for Australian accent.
  - Use Qwen Base or Pocket TTS only after the reference sounds right.

- Use punctuation/text authoring as a weak lever:
  - Shorter sentences and fewer commas can tighten delivery.
  - Ellipses and line breaks can encourage pauses, but model behavior varies.
  - Pocket TTS explicitly does not support silence tags today.

- Use Pocket TTS only for low-latency playback:
  - Do not expect it to solve style control.
  - Feed it the best reference variant you can make.

- Consider external commercial TTS only if strict directed acting is required:
  - If the product requirement becomes "same speaker, guaranteed adjustable
    emotion/pacing/accent every utterance," current local models are not a
    reliable match.

## Non-goals

- Numeric independent sliders for accent, emotion, energy, and pause strength.
- Guaranteed same-speaker style transfer for arbitrary uploaded voices.
- Hidden prompt injection into Base as the main style mechanism.
- Running VoiceDesign, Base, OmniVoice, and Pocket TTS all resident together on
  dockermisc1.
- Treating post-processing as a substitute for a good reference.

## Immediate recommendation

Build in this order:

1. Phase 1 Speak cleanup and truthful progress.
2. Phase 2 voice-family / variant metadata.
3. Generate and save a small test library:
   - Rosie original
   - Rosie OmniVoice stitched
   - Aussie Natural
   - Aussie Calm
   - Aussie Energetic
4. Import a curated Pocket TTS built-in set:
   - Vera conversation
   - Jane conversation
   - Fantine reading
   - Marius reading
   - Jean conversation
5. Validate actual pause/speed inheritance through Pocket TTS and Qwen Base.
6. Only then wire output polish styles.

This gets the project to a solid foundation fastest: the main behavioral lever is
the reference, the UI exposes that honestly, and every extra processing layer is
measured before it becomes a promise.
