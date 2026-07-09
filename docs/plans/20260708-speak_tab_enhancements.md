# Speak Tab Enhancements — Implementation Plan

Date: 2026-07-08
Status: Draft

Single-page, implementation-focused plan.
No vague UX language. If something is future-only, it is explicitly marked as such.

References:
- frontend/src/pages/SpeakPage.tsx
- frontend/src/components/VoiceSelector.tsx
- frontend/src/components/AudioPlayer.tsx
- frontend/src/store.ts
- frontend/src/lib/api.ts
- src/qwen3_tts/app.py (endpoints)
- src/qwen3_tts/model.py (TTS_BACKEND, reconfig_in_progress, _run_generate, ETA/frames)
- src/qwen3_tts/pocket_tts_runtime.py (voices, built-in)
- src/qwen3_tts/voice_library.py

─────────────────────────────────────────────────────────────
1) Current state (short, specific)
─────────────────────────────────────────────────────────────

What exists:

- SpeakPage:
  - Single-card layout: textarea, controls row, progress, error, audio.
  - Textarea bound to store.text; 2000-char guidance with >1500 warning.
  - Controls row: VoiceSelector, Language dropdown (English/Chinese), Tone dropdown (TONE_OPTIONS), seed input, Generate button.
  - Uses /generate/async + polling via /generate/progress + /generate/cancel:
    - startPoll(jobId) in SpeakPage: 400ms poll interval.
    - On completed: fetches audio from /generate/job/{id}/audio?response_format=mp3.
    - Captures X-Seed header; shows "Lock this seed".
  - Has initial ETA (estimateInitialEta) based on word count — static, rough, not accurate.
  - Progress UI: progress bar (progress_pct), eta_seconds (formatEta), elapsed_seconds.
  - modelLoaded guards the Generate button.

- VoiceSelector:
  - Uses /voices via listVoices().
  - Currently:
    - "Default voice" option.
    - All voices in a single flat list.
    - If voice.source === 'mounted_ref_audio', shows a "Mounted" badge.
  - No grouping, no built-in voices section, no search.

- AudioPlayer:
  - Hidden audio element + play/pause + Waveform visualization.
  - Tracks progress, duration.
  - No download, no loop, no playback speed, no seek.

- store.ts:
  - speakAudioUrl, speakIsGenerating, speakError, speakJobId, speakJobProgress, speakLastSeed, speakAudioBlob.
  - healthBackend, swapInProgress, reconfigInProgress, runtimeTtsBackend are tracked (via /health polling).
  - modelLoaded from /health.

- Backend wiring:
  - /health:
    - Returns model_loaded, service_started, backend, model, pocket_tts.* etc.
    - Already used by store poller.
  - /generate, /generate/async, /v1/audio/speech:
    - Accept text, language, voice_id, instruct, seed.
    - model.py/_run_generate already:
      - Ignores instruct on Base:
        - For both PyTorch/OpenVINO and Pocket TTS backends, instruct is logged and not used for Base voice-clone.
      - Handles Pocket TTS separately with voice_state resolution.
  - /generate/progress:
    - Returns job state via model.get_job_progress: frames_generated, expected_total_frames, progress_pct, elapsed_seconds, eta_seconds, message.
    - ETA is already live (moving average), not static.
  - Pocket TTS:
    - pocket_tts_runtime.py exposes load_pocket_tts_model, generate_pocket_tts, etc.
    - Built-in voices (alba, vera, etc.) are not yet wired into /voices or SpeakPage.

What is missing or underused:

- SpeakPage:
  - Layout is monolithic and unstructured (single card, 466 lines).
  - No runtime status indication.
  - No connection to reconfigInProgress / swapInProgress beyond disabling Generate.
  - Initial ETA based on word count is misleading; should rely more on job progress or backend hints.
  - No reuse prompt.
  - No advanced diagnostics toggle.

- VoiceSelector:
  - No grouping by source.
  - No built-in (Pocket TTS) voices exposed.

- AudioPlayer:
  - Missing: download, loop, playback speed.

- Backend:
  - No style_preset.
  - No built-in voice listing endpoint.
  - No RTF/audio_seconds fields in job progress (must be added for better ETA UX).

─────────────────────────────────────────────────────────────
2) Speak tab layout plan (concrete zones)
─────────────────────────────────────────────────────────────

The SpeakPage will be refactored into 5 zones, implemented as local components within SpeakPage, not new route pages.

Zone A: Header + runtime status

Purpose:
- Let user know which runtime is active and whether it is loading/reloading.

Behavior:
- Read from store:
  - healthBackend (openvino, pytorch, pocket_tts)
  - modelLoaded
  - reconfigInProgress
  - swapInProgress
- Render:
  - Title "Speak" with a subtle badge:
    - "Runtime: OpenVINO" / "Pocket TTS" / "PyTorch"
    - Badge is a link to Runtime page (setPage('runtime')).
  - If modelLoaded is false but serviceStarted is true:
    - "Model idle-unloaded; will load on next generation."
  - If reconfigInProgress or swapInProgress:
    - Small hint: "Reloading runtime…"
- No backend dropdown here. Runtime config remains on the Runtime page.

Implementation:
- New internal component: SpeakHeader.
- Uses existing store state; no backend changes.

Zone B: Text input

Purpose:
- Text entry with accurate guidance and improved ETA.

Behavior:
- Use existing textarea bound to store.text.
- Keep char counter (2000 limit) and >1500 warning.
- Remove the static word-count ETA function estimateInitialEta:
  - It's inaccurate and confuses users.
- Replace with:
  - When text non-empty and not generating:
    - Subtle hint: "Estimated time depends on length and current load; a live ETA appears once generation starts."
- Keep it minimal.

Implementation:
- Refactor into SpeakTextArea (local to SpeakPage).
- Delete estimateInitialEta.

Zone C: Voice selection

Purpose:
- Unified voice selector with grouping and future-ready structure.

Behavior:
- Upgrade VoiceSelector:
  - Group voices into:
    - "Mounted reference" (voice.source === 'mounted_ref_audio')
    - "Your voices" (library voices, excluding mounted)
    - "Built-in/reference voices" (Pocket TTS built-in, when backend == pocket_tts)
  - Keep existing behavior:
    - Default voice entry
    - Mounted badge for mounted_ref_audio
  - Use VoiceMeta.source, plus a new optional VoiceMeta.source_type for future tagging.

- For Pocket TTS built-in voices:
  - Add endpoint (see Section 3):
    - /health already contains pocket_tts info; extend it or add a small /voices/built-in.
  - Expose these voices:
    - Only when backend == pocket_tts (via healthBackend).
    - Use a new builtin_voice parameter on /generate endpoints.

Implementation:
- Backend: /voices/built-in or extend /health.
- Frontend:
  - Modify VoiceSelector to accept and render grouped options.
  - Use a combobox or Select with group headers + optional search input.

Zone D: Style / delivery chips

Purpose:
- Provide a controlled, model-aware way to tweak delivery style.
- Be honest: on Base (Qwen3-TTS / Pocket TTS), these are best-effort, not identity controls.

Current reality:
- TONE_OPTIONS from voiceDesignChips.ts is currently used in SpeakPage as a dropdown.
- Tooltip says "Tone currently has no effect on the base voice-clone model."
- model.py/_run_generate:
  - For Base:
    - Logs instruct and does not use it.
  - For Pocket TTS:
    - Also ignores instruct currently; generation is pure TTSModel.generate_audio(voice_state, text).

Plan:
- Replace Tone dropdown with style chips:
  - Neutral (default)
  - Calm
  - Energetic
  - Broadcast
  - Storyteller
  - Ultra-clean (for narration / voiceover)
- Mark them as "Experimental" with a note:
  - "Adjusts how the line is delivered. Effects depend on the model and voice."

Implementation (initial, Phase 2):

- Frontend:
  - Render horizontal chips instead of Tone dropdown.
  - Store selection in store (speakStylePreset).
  - Send it as style_preset to /generate/async.

- Backend:
  - Add style_preset parameter to /generate, /generate/async, /v1/audio/speech.
  - In _run_generate:
    - For Base (PyTorch/OpenVINO):
      - Currently instruct is ignored.
      - For now: accept style_preset but:
        - Do NOT invent behavior.
        - Map it to a soft instruct prefix only after validation in a later change, or leave as a no-op logged hint.
        - Mark in docs/plans as future.
    - For Pocket TTS:
      - Accept style_preset but:
        - Do not lie: current generate_pocket_tts(voice_state, text) has no tone.
        - Optionally log: "[generate] style_preset=calm (Pocket TTS; no-op until wired)".
  - Ensure existing instruct, voice_id, and seed behavior is untouched.

Future (Phase 4):
- When VoiceDesign/OmniVoice support style-specific prompting:
  - Map each style to:
    - A short instruct prompt (e.g. "Speak in a calm, steady tone").
    - Or per-voice style reference clip.
  - Only after controlled tests confirm identity preservation.

Zone E: Generate + progress + playback

Purpose:
- Unified generation, progress, and playback area.

Behavior:
- Use existing async + polling wiring.
- Generate button:
  - Keep same disable logic: disabled if no text, generating, or !modelLoaded.
  - No extra guards for reconfigInProgress; requests queue via executor.

- Progress:
  - Use /generate/progress with richer fields (see Section 3).
  - Remove static ETA language; show:
    - "Generating… ETA 12s · 3s / ~18s of audio"
  - Use backend-provided:
    - audio_seconds_generated
    - live_rtf_estimate
  - Still show progress bar and elapsed seconds.

- Playback (AudioPlayer):
  - Enlarge player area.
  - Add:
    - Download button (MP3/WAV).
    - Loop toggle.
    - Playback speed (0.75x, 1x, 1.25x, 1.5x) via HTMLAudioElement.playbackRate.
  - Add "Reuse prompt":
    - Reuses current text + voiceId + stylePreset.
    - Phase 1: simply restores the last-used configuration via localStorage; Phase 2: real prompt history (future).

- Advanced toggle:
  - At bottom of Zone E, hidden by default.
  - When enabled (speakAdvancedOpen):
    - Show:
      - Backend (from healthBackend).
      - Model (from /health.model).
      - RTF of last completed job.
      - Duration of generated audio.
  - No noise by default.

─────────────────────────────────────────────────────────────
3) Backend changes (concrete, no fluff)
─────────────────────────────────────────────────────────────

3.1 style_preset parameter

- Endpoints:
  - /generate, /generate/async, /v1/audio/speech
- Change:
  - Accept optional style_preset (string):
    - Allowed: "neutral", "calm", "energetic", "broadcast", "storyteller", "ultra_clean"
    - Default: "neutral"
- model.py/_run_generate:
  - For Base (PyTorch/OpenVINO):
    - For now, do nothing (or log).
    - Do not overwrite instruct or inject prompts until validated.
  - For Pocket TTS:
    - For now, log and ignore.
    - No temp/style wiring yet — keep behavior unchanged.
- Existing instruct, voice_id, seed must remain untouched.

3.2 builtin_voice parameter (Pocket TTS)

- For selecting Pocket TTS built-in voices (alba, vera, etc.):
- Endpoints:
  - /generate, /generate/async, /v1/audio/speech
- Behavior:
  - New optional field: builtin_voice: string
  - If provided and TTS_BACKEND == "pocket_tts":
    - Use it to select the Pocket TTS built-in voice, either:
      - Via a predefined mapping (voice_id -> built-in config)
      - Or by using a reference clip if we have one.
  - If provided and backend != "pocket_tts":
    - Ignore and log (or reject with 400 to keep it explicit).
- Implementation detail:
  - Extend pocket_tts_runtime with:
    - A list of known built-in voice configs.
    - A function get_built_in_voice_state(model, builtin_voice).
  - If not implemented yet, wire as a no-op / validation gate, not silently swallowed.

3.3 /voices/built-in (or /health.pocket_tts_builtin_voices)

- Option A (recommended): /voices/built-in
  - Returns a list of built-in/reference voices for Pocket TTS.
  - Each voice:
    - voice_id: "pocket_tts:alba", etc.
    - description: short human label.
    - language: "en" (or appropriate).
    - source_type: "builtin"
  - Only returned when:
    - TTS_BACKEND == "pocket_tts"
    - OR Pocket TTS runtime is loaded (for future: use across backends via reference clips).
- Option B (smaller change, later):
  - Extend /health.pocket_tts with:
    - builtin_voices: list of { voice_id, description, language }
  - For now, Option B is acceptable to avoid new endpoint if it complicates things.
- Choose based on how we want to expose them.

3.4 Richer job progress for Speak tab

- Extend /generate/progress (via model.get_job_progress):
  - Add:
    - audio_seconds_generated: (frames_generated * 0.08)
    - live_rtf_estimate: elapsed_seconds / max(1, audio_seconds_generated)
  - These are derived, cheap to compute, and align with _run_generate logging.
- The frontend will use these to show accurate audio progress and ETA without static heuristics.

─────────────────────────────────────────────────────────────
4) Frontend changes (specific, file-aware)
─────────────────────────────────────────────────────────────

4.1 SpeakPage.tsx

- Refactor layout into internal sections/components:
  - SpeakHeader (Zone A)
  - SpeakTextArea (Zone B)
  - VoiceSelector + style chips (Zone C + D)
  - Generate button + progress + result (Zone E)
- Integrate:
  - Zone A: runtime badge from healthBackend + modelLoaded/reconfigInProgress hints.
  - Zone B: remove estimateInitialEta; keep char count and long-text warning.
  - Zone C: use upgraded VoiceSelector with grouping.
  - Zone D: replace Tone dropdown with style chips.
  - Zone E:
    - Use new progress format: "Xs / ~Ys of audio · ETA Zs" based on audio_seconds_generated.
    - Enlarge AudioPlayer.
    - Add Advanced toggle at bottom.

4.2 VoiceSelector.tsx

- Add:
  - Grouping:
    - "Mounted reference" (source === 'mounted_ref_audio')
    - "Your voices"
    - "Built-in voices" (when Pocket TTS is active)
  - Optional search input.
  - Optional sample playback per voice (if sample available).
- Keep:
  - Existing default voice and Mounted badge behavior.

4.3 AudioPlayer.tsx

- Add:
  - Download button (uses existing blob or src).
  - Loop toggle (sets audio.loop).
  - Speed control (0.75x, 1x, 1.25x, 1.5x) via playbackRate.
- Keep:
  - Existing waveform, progress, play/pause, auto-play behavior.

4.4 store.ts

- Add minimal fields:
  - speakStylePreset: string (default: "neutral")
  - speakAdvancedOpen: boolean (default: false)
- Do not add speakBackendInfo:
  - We already have healthBackend, runtimeTtsBackend, modelLoaded, swapInProgress, reconfigInProgress.
- Ensure:
  - GenerateJobProgress type includes new fields:
    - audio_seconds_generated?: number
    - live_rtf_estimate?: number

4.5 api.ts

- Extend generateAsync:
  - Add:
    - style_preset: from speakStylePreset
    - builtin_voice: from Pocket TTS built-in selection
- Extend GenerateJobProgress interface:
  - Add:
    - audio_seconds_generated?: number
    - live_rtf_estimate?: number

─────────────────────────────────────────────────────────────
5) Phased implementation plan

Phase 1 (Low risk, UX polish)

Goal:
- Improve SpeakPage structure and UX without changing generation behavior.

Tasks:

- Frontend:
  - Refactor SpeakPage into:
    - SpeakHeader (runtime badge from /health).
    - SpeakTextArea.
    - SpeakControls (VoiceSelector + Language + Style + Generate).
    - SpeakProgress.
    - SpeakResult (AudioPlayer + seed + reuse).
  - Remove estimateInitialEta; replace with neutral message ("Live ETA appears once generation starts.").
  - Use /generate/progress audio_seconds_generated (when available) for progress label.
  - Upgrade AudioPlayer:
    - Add download, loop, playback speed.
  - Add Advanced toggle in SpeakResult:
    - Show backend, model, RTF, duration on last job.
  - Minor: improve spacing, remove redundant fluff.

- Backend:
  - In model.get_job_progress:
    - Add:
      - audio_seconds_generated
      - live_rtf_estimate

Constraints:
- No new required fields.
- No behavior changes for /generate, /generate/async, /v1/audio/speech.

Phase 2 (Built-in voices + style chips)

Goal:
- Introduce Pocket TTS built-in voices and style_preset with best-effort mapping.

Tasks:

- Backend:
  - Add /voices/built-in or /health.pocket_tts_builtin_voices:
    - Expose Pocket TTS built-in voices.
  - Add builtin_voice parameter to:
    - /generate
    - /generate/async
    - /v1/audio/speech
  - Add style_preset parameter to same endpoints.
  - Update _run_generate:
    - Accept style_preset and builtin_voice.
    - For Base: log style_preset, do nothing (or best-effort instruct prefix later).
    - For Pocket TTS: map builtin_voice if implemented; log style_preset.

- Frontend:
  - Extend VoiceSelector:
    - Show "Built-in voices" group when Pocket TTS active.
  - Add style chips to SpeakPage:
    - Neutral, Calm, Energetic, Broadcast, Storyteller, Ultra-clean
    - Label them as "Experimental"
  - Wire style_preset into generateAsync calls.

Constraints:
- Must not break existing instruct, voice_id, seed behavior.
- If style_preset is not wired into real model behavior yet, do not market it.

Phase 3 (Advanced and diagnostics)

Goal:
- Provide advanced diagnostics for power users without visual noise.

Tasks:

- Backend:
  - Ensure /generate/progress always includes:
    - audio_seconds_generated
    - live_rtf_estimate
  - Optionally:
    - Add RTF and duration into job metadata after completion (so SpeakPage can show "last job" stats).

- Frontend:
  - Enhance Advanced toggle:
    - Show backend, model, RTF, durations only when expanded.
  - Add "Reuse prompt":
    - Phase 3: store last-used text + voiceId + stylePreset in localStorage and allow one-click restore.

Phase 4 (Future-only)

Do NOT implement unless explicitly requested and validated.

- Per-voice style profiles:
  - Dedicated tone/style presets tied to specific voices, using style-tuned reference clips.

- Model-specific tone control:
  - For VoiceDesign/OmniVoice:
    - Map style_preset to real instruct or dedicated model behavior.
    - Requires testing: identity preservation, prosody, no drift.

- Structured prompt presets:
  - A small library of reusable prompt templates (scripts, readouts, announcements) that auto-fill SpeakPage text.
