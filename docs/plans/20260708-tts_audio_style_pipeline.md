# TTS Audio Style Pipeline — Technical Blueprint

Date: 2026-07-08
Status: Draft

Single, low-latency, post-generation style pipeline that works over any TTS output (Qwen3-TTS Base or Pocket TTS). No model changes; style is implemented as:
- Reference preprocessing (for cloning)
- Generation-time knobs
- Post-processing recipes

Style is orthogonal and composable: each style is a fixed recipe of knobs + processing steps.

Constraints:
- Must be CPU-only friendly (OpenVINO runtime on 10–15 GiB box).
- Must be fast: < 200 ms additional processing per second of audio.
- Must be model-agnostic: work with Qwen3-TTS, Pocket TTS, and future models.
- Must not break latency or quality significantly.

Tools:
- SoX (EQ, compression, de-essing, noise gate, time-stretch)
- FFmpeg (final encode; optionally replace SoX)
- librosa (analysis, time-stretch, basic processing)
- pyloudnorm (EBU R128 loudness normalization)
- soundfile (I/O)

─────────────────────────────────────────────────────────────

1. Reference audio preprocessing (before cloning)

Purpose: normalize and clean the reference clip so cloning models (Qwen3-TTS Base, Pocket TTS) capture a stable timbre/prosody.

Only applies when:
- User uploads a reference audio.
- Voice is saved to /voices via voice_library (VoiceDesign/OmniVoice/Manual).

Input assumptions:
- 3–15 seconds speech.
- Any sample rate; we normalize to 24 kHz (TTS standard).
- Must not alter timbre (no heavy EQ or pitch shift).
- Must be reversible: never delete the original.

Steps (applied when saving a voice):
- Format:
  - Convert to mono, 24 kHz, 16-bit PCM with soundfile or FFmpeg.
- Trim:
  - Hard-trim silence at start/end.
  - Keep only continuous speech with no major pauses.
- Loudness:
  - Normalize to -23 LUFS (EBU R128) short-term with pyloudnorm.
  - True peak limit: -1.5 dBTP.
- Optional (when needed):
  - Light spectral denoise with SoX (only if noise floor is loud).
  - Soft de-ess (1–2 dB cut at 6–8 kHz) if sibilants are extreme.

Output:
- Single clean segment stored as reference.wav inside /voices/{voice_id}/.

Notes:
- Do not pre-apply heavy styles to references; we keep styles orthogonal (post-generation), not baked into the reference.

─────────────────────────────────────────────────────────────

2. Generation-time knobs (in /generate)

These knobs adjust how the TTS model behaves before post-processing.

Design:
- Keep them as optional fields in /generate, /v1/audio/speech, /generate/async.
- Styles will be high-level presets that map to these knobs.
- For now, most knobs are no-ops for Base (instruct is ignored); we wire them so they’re ready for later.

Knobs (initial set):
- temperature:
  - Range: 0.5–1.3
  - Effect:
    - Lower (0.5–0.7): calmer, more monotone.
    - Higher (0.9–1.3): more dynamic, more expressive, slightly less stable.
  - Current: not exposed to /generate; to be wired where applicable.
- max_new_tokens / max_audio_duration (safety caps):
  - Existing in _run_generate; we may tune per-style later:
    - Tighter for “Ultra-clean”/“Broadcast” (shorter, compact).
    - More room for “Storyteller”/“Calm”.
- instruct:
  - Currently forwarded to the model:
    - Base: ignored (logged).
    - Pocket TTS: ignored today, could be wired.
  - For styles: we may use fixed prefixes:
    - e.g., "Speak calmly and clearly."
    - But only once the model actually responds to instructions.

For our stack, the honest approach:
- At first, styles are primarily post-processing.
- We reserve these knobs for future integration with VoiceDesign/OmniVoice or Pocket TTS if they start supporting instruction-style control.

─────────────────────────────────────────────────────────────

3. Post-processing

All post-processing is applied to the raw TTS waveform.
Must be:
- Deterministic
- Fast
- Non-destructive: never mutate source audio

Processing blocks:

A) Loudness and dynamics
- Always (for all styles):
  - Normalize to -23 LUFS (short-term) with pyloudnorm.
  - True peak limit at -1.5 dBTP.
- Optionally (per style):
  - Light compression (SoX) for “broadcast” or “energetic” styles:
    - Ratio: 1.8–2.5:1
    - Threshold: -30 dBFS
    - Soft knee
  - Rationale: smooth peaks; make TTS sound more professional.

B) EQ (tone shaping)
- Use SoX or a small biquad chain.
- Typical ops:
  - High-pass: 70–80 Hz (remove rumble).
  - Subtle low-mid boost (150–300 Hz) for warmth.
  - Slight presence boost (2–5 kHz) for clarity.
  - De-ess: small cut at 6–9 kHz for harsh styles.
- Keep it conservative; model identity > artificial EQ.

C) Time-stretch (speed control)
- If speed_target != 1.0:
  - Use librosa.effects.time_stretch(rate) or SoX `tempo`.
  - Speed ranges:
    - 0.85x–0.95x: slower, “calm,” more deliberate.
    - 1.00x: neutral.
    - 1.05x–1.15x: faster, “energetic.”
- Keep changes subtle to avoid chipmunk or muddy artifacts.
- Must be tested per model (Qwen3-TTS vs Pocket TTS) to see how it affects perceived naturalness.

D) Pause shaping
- Detect pauses using energy threshold on the waveform (librosa or custom).
- Adjust:
  - For broadcast/energetic:
    - Slightly shorten internal micro-pauses (e.g., 10–20%).
  - For storyteller/calm:
    - Slightly lengthen pauses (e.g., 10–20%).
- Keep total drift under 10% so timing doesn’t go off.

E) Final encode
- MP3 192 kbps default (for compatibility).
- Optional WebM-Opus at 128 kbps for streaming endpoints.

Latency constraints:
- On 10–15 GiB box:
  - Must keep total pipeline (post-gen) under 200 ms per 10 seconds of audio.
  - Avoid heavy offline-style convolution or giant IRs.

─────────────────────────────────────────────────────────────

4. Concrete style recipes

Each style is an explicit recipe: knobs + post-processing.

4.1. Neutral (default)
- Generation:
  - temperature: default
  - instruct: none
- Post-processing:
  - Loudness: -23 LUFS; -1.5 dBTP
  - EQ: light high-pass at 70 Hz
  - Time-stretch: 1.0x
  - Compression: none
- Use case: baseline, natural, no flavor.

4.2. Calm
- Generation:
  - temperature: 0.6–0.8 (if wired)
  - instruct: "Speak calmly and clearly." (future use)
- Post-processing:
  - Time-stretch: 0.90x–0.95x
  - EQ: gentle low-mid boost (180–250 Hz, +1.5 dB)
  - Dynamics: very light compression (1.5:1, -35 dBFS)
  - Pauses: +10% length
- Use case: soft narration, instructions, wellness.

4.3. Energetic
- Generation:
  - temperature: 1.0–1.2 (if wired)
  - instruct: "Speak energetically." (future use)
- Post-processing:
  - Time-stretch: 1.05x–1.10x
  - EQ: mild presence boost (3–4 kHz, +1.5 dB)
  - Compression: moderate (2:1, -30 dBFS)
  - Pauses: -10% length
- Use case: hype, alerts, upbeat narration.

4.4. Broadcast
- Generation:
  - temperature: 0.9–1.0
  - instruct: "In a clear, professional broadcast style." (future)
- Post-processing:
  - Time-stretch: 1.0x
  - EQ:
    - High-pass 80 Hz
    - Slight warmth (200 Hz, +1 dB)
    - Slight presence (3.5 kHz, +1.5 dB)
  - Compression: 2.5:1, -28 dBFS
  - De-ess: 7–8 kHz, -1 dB
  - Pauses: -10% length
- Use case: authoritative, crisp, news-style delivery.

4.5. Storyteller
- Generation:
  - temperature: 1.0–1.1
  - instruct: "As if telling a story, warm and expressive." (future)
- Post-processing:
  - Time-stretch: 0.95x–1.0x
  - EQ:
    - Warm boost (200–300 Hz, +1.5–2 dB)
    - Mild presence (2.5 kHz, +1 dB)
  - Dynamics: gentle compression (1.8:1, -32 dBFS)
  - Pauses: +10–15% length
- Use case: narrative, audiobook-style.

4.6. Ultra-clean
- Generation:
  - temperature: 0.4–0.5
  - instruct: none
- Post-processing:
  - Time-stretch: 1.0x
  - EQ: flat, only HPF 80 Hz
  - Compression: very light (1.4:1, -38 dBFS)
  - Aggressive noise gate and pause cleanup
- Use case: batch work, comparison, dubbing, minimal flavor.

Note:
- Initial implementation:
  - For Base: only post-processing steps are real.
  - For Pocket TTS: post-processing plus (later) instruct/temperature if runtime allows.
- We must validate each style empirically on real outputs; some parameters may need adjustment.

─────────────────────────────────────────────────────────────

5. Integration into our stack

5.1. Endpoint wiring

- Extend:
  - /generate
  - /generate/async
  - /v1/audio/speech
- Add:
  - Optional style_preset field (same set as in the Speak tab).
- Behavior:
  - If style_preset is recognized:
    - Apply the corresponding recipe in _run_generate (after silence trimming).
  - If unknown:
    - Ignore silently (backward-compatible).

5.2. Implementation in _run_generate (model.py)

- After:
  - model.generate_voice_clone or Pocket TTS generation
  - _trim_silence
- If style_preset is set:
  - Call apply_style_preset(wav, sr, style_preset):
    - Dispatches to SoX/librosa/pyloudnorm.
    - Returns processed wav, sr.
- Keep it:
  - Non-blocking (still runs in the same executor).
  - Fast and robust; no heavy subprocess chains.

5.3. Speak tab (frontend)

- Style chips in SpeakPage:
  - Map to style_preset.
- Backend:
  - Initially:
    - Only the post-processing steps are effective.
  - Later:
    - Wire temperature/instruct where applicable.
- UX:
  - Mark styles as “Experimental” until validated.

─────────────────────────────────────────────────────────────

6. Known gaps / needs research

These are explicitly not assumptions; they must be validated.

- Time-stretch limits:
  - Test ±3%, ±5%, ±8% for both Base and Pocket TTS.
  - Check for:
    - Formant distortion
    - Robustness with different voices
- Post-processing impact on emotion:
  - Listen tests for:
    - “Broadcast” vs “Storyteller” vs “Neutral”
  - Adjust parameters empirically (EQ/compression/pauses).
- Latency:
  - Profile each style on dockermisc1:
    - For 10s of audio: how many ms extra for each style?
  - Enforce budget or reduce complexity.
- Short prompts (2–4s):
  - Ensure styles don’t over-process tiny clips.
  - Some (Storyteller, Broadcast) rely on longer context; test safety.
- Long prompts (3–10 minutes):
  - Ensure no cumulative artifacts.
  - Check stability of loudness/EQ over long durations.
- Inline vs worker:
  - Decide:
    - Inline in Flask (simpler).
    - Or small internal worker for audio processing (better latency separation).
