# Pocket TTS Integration

What it is:

- A third backend (alongside pytorch and openvino) for speech synthesis.
- Selected via TTS_BACKEND=pocket_tts.
- Based on kyutai/pocket-tts (kyutai-labs), an autoregressive, neural codec-based TTS model with voice cloning via a Mimi encoder.
- Provides:
  - Voice cloning from a single reference audio file.
  - Prosodically rich, natural-sounding speech.
  - 24 kHz output.

What it is NOT:

- Not a drop-in replacement for Qwen3-TTS: different model family, different prosody behavior.
- Not exposed via OpenVINO acceleration.
- Not intended for fine-grained per-request style switching in the current design.

Core files:

- src/qwen3_tts/pocket_tts_runtime.py:
  - Loads Pocket TTS models.
  - Builds voice_state from reference audio.
  - Wraps generate_audio with post-EOS trimming.
  - Handles unload / hotswap.
- src/qwen3_tts/model.py:
  - Integrates Pocket TTS as a backend choice.
  - Wires /generate and /v1/audio/speech into Pocket TTS when TTS_BACKEND=pocket_tts.
  - Manages reload behavior for Pocket TTS-specific knobs.
- src/qwen3_tts/app.py:
  - Exposes endpoints; does not change shape for Pocket TTS.
  - Same /generate, /v1/audio/speech, /health; behavior is controlled by backend + env.

High-level behavior:

- On startup with TTS_BACKEND=pocket_tts:
  - load_pocket_tts_model(...) is called (model.py, Pocket TTS branch).
  - Uses POCKET_TTS_LANGUAGE, POCKET_TTS_TEMP, POCKET_TTS_LSD_DECODE_STEPS, POCKET_TTS_EOS_THRESHOLD, POCKET_TTS_QUANTIZE, POCKET_TTS_NOISE_CLAMP, POCKET_TTS_FRAMES_AFTER_EOS.
  - Builds a default voice_state from REF_AUDIO via build_default_voice_state(...).
  - This default voice_state becomes the "mounted reference voice."
- On each generation:
  - The selected voice_state is resolved (default or voice_library voice).
  - generate_pocket_tts(model, voice_state, text) is called.
  - Output is post-processed with an energy-based tail trim using frames_after_eos.
- Pocket TTS registers as a foreign engine so:
  - Idle unload and Base/Engine swap logic treat it consistently.
  - Only one heavy model is resident at a time.

1. Prosody Conditioning (Critical)

Prosody in Pocket TTS is emergent, not explicit.

Key principles:

- Primary driver: the reference audio.
  - The model extracts a voice_state from the reference audio using Mimi:
    - This encodes timbre, accent, baseline speaking style, and prosodic tendencies.
  - Any pacing, breathiness, hesitation, or "character" you hear in the output is mostly inherited from that reference, not from the prompt text.
- No secondary prosody layer:
  - There is no SSML, no pause tokens, no breath tokens, no explicit emphasis.
  - You cannot say "insert a 400 ms pause after this sentence."
- Prosody emerges from three factors (in order of influence):
  - 1) voice_state (dominant)
  - 2) generation parameters (secondary, global knobs)
  - 3) silence trimming behavior (tertiary but highly visible)

Implications:

- Longer, natural reference clips:
  - More breathing room.
  - Slightly slower, more conversational pacing.
  - Occasional hesitations/fillers are more likely.
- Short, tightly edited reference clips:
  - E.g., generated from OmniVoice/VoiceDesign.
  - Tighter pacing, fewer pauses, more "studio" feel.
- Overly energetic or heavily compressed segments:
  - Output will match: faster, more rushed prosody.
- The model cannot:
  - Add a specific pause at a chosen position.
  - Guarantee uniform pacing across very different segment sources.

If prosody is "off," the first place to look is:

- The reference audio selection and processing.
- Then EOS/pause-related knobs (EOS_THRESHOLD, FRAMES_AFTER_EOS, silence trim).

2. Runtime Controls and Their Prosodic Effect

All knobs are backend-global and applied at model load time, unless noted.
Changing most requires a reload (hotswap or restart).

- POCKET_TTS_TEMP
  - Controls sampling randomness.
  - Higher:
    - More prosodic variation.
    - Livelier speech.
    - More risk of artifacts if too high.
  - Lower:
    - Cleaner, more monotone.
    - More stable.
  - Practical range: 0.4–1.5.
  - Global; requires reload.

- POCKET_TTS_LSD_DECODE_STEPS
  - Number of per-frame refinement steps.
  - 1–2:
    - Flatter, cleaner, "studio" feel.
  - 3–5:
    - More natural transitions, richer prosody.
  - 6+:
    - Diminishing returns.
    - Risk of over-prosody and increased latency.
  - Global; requires reload.

- POCKET_TTS_EOS_THRESHOLD
  - Log-prob threshold controlling when generation stops.
  - Most important knob for "too many pauses" vs "too clipped."
  - Very negative (e.g., -4.0 to -5.0):
    - Longer tails.
    - More trailing pauses/breathing.
  - Less negative (e.g., -2.5 to -3.0):
    - Tighter endings.
    - Fewer trailing pauses.
    - Risk of mid-sentence cuts if too high.
  - Global; requires reload.

- POCKET_TTS_FRAMES_AFTER_EOS
  - Extra frames kept after the last likely-speech frame.
  - Implemented via energy-based post-EOS trim in pocket_tts_runtime.py:_trim_post_eos_tail.
  - 0–1:
    - Very tight; risk of clipping consonants.
  - 3–5:
    - Natural tail.
  - 6+:
    - Longer trailing breath/silence.
  - Per-call safe: this can be exposed as a future per-request tuning parameter without reloading the model.

- POCKET_TTS_NOISE_CLAMP
  - Limits per-step noise magnitude; wired into TTSModel.load_model.
  - Lower (0.1–0.4):
    - Calmer, more stable, "cleaner."
  - Higher/None:
    - More prosodic variation.
    - Occasional breathing artifacts.
  - Global; requires reload.

- SILENCE_TRIM and SILENCE_TRIM_PAD_MS
  - Global silence-trim controls (shared with other backends).
  - Strongly affect perceived pacing:
    - Aggressive: tight, minimal dead air.
    - Gentle: more natural breathing and sentence-space.
  - Any change to these will alter how Pocket TTS output is perceived.

3. Style Presets (Recommended)

These are operational guidelines, not official API values.
They combine knobs into consistent styles for different use cases.

- Natural (Recommended default)
  - temp: 1.0–1.1
  - lsd_decode_steps: 3–4
  - eos_threshold: -3.8
  - frames_after_eos: 3
  - noise_clamp: 0.4–0.6
  - Use case: general narration, default behavior.

- Compact
  - temp: 0.7–0.8
  - lsd_decode_steps: 2–3
  - eos_threshold: -2.5 to -3.0
  - frames_after_eos: 0–1
  - noise_clamp: 0.2–0.3
  - Use case: dense info, tool readouts, minimal pauses.

- Expressive
  - temp: 1.3–1.5
  - lsd_decode_steps: 5–6
  - eos_threshold: -4.5 to -5.0
  - frames_after_eos: 5–7
  - noise_clamp: none or high
  - Use case: storytelling, character speech.
  - Risk: artifacts if temp > 1.5.

- Soft/Calm
  - temp: 0.6–0.8
  - lsd_decode_steps: 4–5
  - eos_threshold: -4.5 to -5.0
  - frames_after_eos: 4–6
  - noise_clamp: 0.1–0.3
  - Use case: gentle narration, wellness, instructions.

- Energetic
  - temp: 1.2–1.4
  - lsd_decode_steps: 2–3
  - eos_threshold: -2.5 to -3.0
  - frames_after_eos: 1–2
  - noise_clamp: 0.5–0.7
  - Use case: hype, alerts, sports commentary.

- Ultra-clean (Dev/Batch)
  - temp: 0.4–0.5
  - lsd_decode_steps: 2
  - eos_threshold: -2.5
  - frames_after_eos: 0–1
  - noise_clamp: 0.1
  - Use case: maximum fidelity, minimal flavor, batch comparison.

4. Per-Request vs Global Tuning (Constraints)

Current reality:

- The following are global, set at model load time:
  - POCKET_TTS_TEMP
  - POCKET_TTS_LSD_DECODE_STEPS
  - POCKET_TTS_EOS_THRESHOLD
  - POCKET_TTS_NOISE_CLAMP
- Changing any of them requires:
  - A reload of the Pocket TTS model (hotswap via model.py reload path), which is slow.
- frames_after_eos is per-call:
  - Safe to adjust per-request (pocket_tts_runtime uses it at generation time).

Implications:

- "Styles" are effectively global configurations:
  - Set via environment or the RuntimeConfig page.
  - Not intended as per-request overrides in the current design.

To support true per-request style switching, one of the following would be needed:

- Wrap Pocket TTS's inner generate loop so parameters are injected per-call (intrusive).
- Maintain multiple model instances in memory (expensive).
- Allow frequent reloads (slow, not suitable for latency-sensitive workloads).

For now, pick a style at deploy time, not at request time.

5. Segment/Clip Construction Considerations

When building composite voices from OmniVoice/VoiceDesign segments, Pocket TTS prosody constraints matter.

Observations:

- Different segments can encode different pacing and breathing profiles.
- Concatenated segments may introduce:
  - Double pauses between segments.
  - Inconsistent energy levels.

Mitigations:

- Use aggressive per-segment tail trimming for middle segments:
  - e.g., frames_after_eos=0 for all but the last segment.
- Normalize energy across segments.
- Apply short crossfades (10–30 ms) at segment boundaries.
- Trim leading/trailing silence from source reference audio before building voice_state.

When prosody feels "off" for a multi-segment voice:

- First inspect:
  - The reference segments.
  - Their lengths and boundaries.
  - The trim configuration between segments.
- Then adjust:
  - EOS_THRESHOLD and FRAMES_AFTER_EOS if the entire output is too paused or too clipped.

6. Integration Notes

How Pocket TTS is integrated:

- backend=pocket_tts:
  - Dedicated runtime in pocket_tts_runtime.py.
  - Wired through model.py as a first-class TTS_BACKEND.
- Mounted reference audio:
  - REF_AUDIO is used as the "Default voice."
  - Auto-registered in the voice library as a named mounted reference voice.
- Per-voice cloning:
  - Voices in the voice library and the mounted reference all use the same generate_audio path; only the reference audio differs.
  - pocket_tts_runtime.get_pocket_tts_voice_state resolves the correct voice_state per voice_id.

Endpoints:

- /generate, /v1/audio/speech, /health:
  - No new Pocket TTS–specific endpoint shapes.
  - Pocket TTS is a drop-in backend selection behind the same interface.

Future considerations:

- frames_after_eos is a candidate for a per-request tuning option (e.g., "tighter" / "natural" / "breathing") because it is safe and cheap to change.
- Built-in demo/reference voices may be added later for:
  - Speak page presets.
  - OpenAI-style endpoint demo voices.
- That work is out of scope for now; this doc exists to keep prosody and integration behavior consistent.

7. Design Constraints (from the original integration plan)

These are the invariants the Pocket TTS integration was built to preserve. They are not
Pocket TTS-specific — they're the repo's existing hotswap/serving architecture — but the
integration must not violate them:

- One image, one process, one model resident at a time. No co-loading Pocket TTS alongside
  Qwen3TTSModel/OpenVINO.
- Gunicorn stays `-w 1 -k gthread --threads 4`, never `--preload`, never more than one worker.
- All inference stays serialized through the single-worker `ThreadPoolExecutor(max_workers=1)`.
- `/generate`, `/v1/audio/speech`, `/generate/async`, `/health` keep their existing request/response
  contracts — Pocket TTS is a backend selection behind those interfaces, not a new API shape.
- `TTS_BACKEND=pytorch` and `TTS_BACKEND=openvino` rollback paths remain fully functional.
- No CUDA; torch stays CPU-only. Verified empirically: installing `pocket-tts==2.1.0` on top of
  the pinned CPU torch wheel (`torch==2.12.1`, `--index-url https://download.pytorch.org/whl/cpu`)
  does not upgrade or replace torch, since pocket-tts only declares `torch>=2.5.0` and pip's
  resolver leaves an already-satisfied floor constraint alone.
- Voice-state caching (`pocket_tts_voice_state_cache` in pocket_tts_runtime.py) must be
  invalidated when a cached voice is deleted from the voice library — `app.py`'s
  `DELETE /voices/<voice_id>` calls `pocket_tts_runtime.invalidate_voice_state(voice_id)`
  (alongside the equivalent `model.invalidate_voice_clone_prompt` for the Qwen3 cache) so a
  deleted voice can't keep generating from a stale cached state.

8. Manual Validation Checklist

On a CPU host with enough RAM (dockermisc1 or equivalent):

- Build the image with the pocket-tts dependency and confirm `python -c "from pocket_tts import
  TTSModel"` succeeds, and that torch remains CPU-only (no CUDA wheel pulled in).
- With REF_AUDIO/REF_TEXT set, start with `TTS_BACKEND=pocket_tts`:
  - Health reports `backend=pocket_tts`, `model_loaded=true`.
  - `POST /generate` with small text produces reasonable, fast, 24 kHz audio.
- Switch backends via the UI or `/runtime/config` in both directions (openvino <-> pocket_tts
  <-> pytorch) and confirm each unload/reload completes and generation works afterward.
- Generate with a specific `voice_id` and confirm it clones that voice library entry, not the
  default/mounted reference.
- Delete a voice that was just used for generation, then confirm a follow-up request for that
  same `voice_id` fails cleanly (no stale cached voice_state) instead of silently succeeding.
- Confirm Pocket TTS RSS is materially lower than the 1.7B OpenVINO/PyTorch backends.
- Confirm `/generate/stream` returns 503 under `TTS_BACKEND=pocket_tts` (streaming is explicitly
  out of scope for this integration — see "What it is NOT" above).
- Confirm no regressions in the openvino/pytorch backends, and that VoiceDesign/OmniVoice
  (which manage their own model swap) still work.
