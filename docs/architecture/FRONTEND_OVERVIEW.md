# FRONTEND_OVERVIEW

Architecture and usage overview of the persona-forge frontend.

This is the reference for how the UI is structured, how it talks to the backend, how global state flows, and how it reacts to model-load / swap status.

## 1. Stack summary

- Framework: React 19 + TypeScript + Vite.
- Routing: Single-page shell (AppShell + simple page state); no separate router library.
- State management: zustand (useAppStore).
- Styling:
  - Tailwind CSS 4 + class-variance-authority + tailwind-merge.
  - shadcn-style component primitives (radix-ui-based).
- Motion: framer-motion for transitions, AnimatePresence.
- Icons: lucide-react.

The frontend is built into a static dist/ directory and served by the Flask app at "/" (FRONTEND_ENABLED path). No separate web server is used in production.

Build and integration:

- Dockerfile stage: frontend-build.
  - FROM node image.
  - COPY frontend/ → npm install → npm run build → dist/.
- Final image:
  - COPY --from=frontend-build /frontend/dist frontend/dist
  - Flask serves files from frontend/dist in production.
- Dev:
  - npm run dev with Vite dev server.
  - Vite proxies API calls (/health, /generate, /v1, etc.) to Flask on :8318.

## 2. Pages and their purpose

Routing is stateless: App.tsx switches between pages based on useAppStore((s) => s.page). Pages:

- SpeakPage (speak)
- VoiceDesignPage (voice-design)
- VoiceLibraryPage (voice-library)
- StitchStudioPage (stitch-studio)
- IntegrationsPage (integrations)
- RuntimeConfigPage (runtime)

### SpeakPage

Primary purpose: generate speech using an existing voice.

Key behaviors:
- Text input (textarea).
- Voice selector (VoiceSelector) backed by /voices.
- Language selection (English/Chinese).
- Tone selection (currently informational; forwarded for CustomVoice compatibility).
- Optional random seed input.
- On "Generate":
  - POST /generate with text, voice_id, language, instruct (tone), seed.
  - On success: render audio via AudioPlayer, display seed, offer "Lock this seed."
- Disabled when:
  - text is empty
  - isGenerating is true
  - modelLoaded is false (uses store.modelLoaded from /health polling).

### VoiceDesignPage

Primary purpose: design a new voice using either:
- Qwen (VoiceDesignPanel)
- OmniVoice (OmniVoicePanel)

Key behaviors:
- EngineSelector toggles between qwen / omnivoice.
- On mount:
  - If an EditingVoice is set in store (from VoiceLibraryPage "Edit"), consumes it once into the panel, then clears from store.
- Qwen panel (VoiceDesignPanel):
  - Chips for gender, age, register, textures, personas.
  - Sample text editor.
  - Language and seed input.
  - Preview → save → onVoiceCreated: sets voiceId, refreshes voices, switches to SpeakPage.
- OmniVoice panel (OmniVoicePanel):
  - Accent, voice traits, advanced knobs (steps, speed, guidance, etc.).
  - Script text → segmentation → audition candidates → lock-in → stitch → save as a reference voice.
  - After save, stays on page (multiple save iterations expected).

### VoiceLibraryPage

Primary purpose: browse, manage, and reuse saved voices and OmniVoice segments.

Key behaviors:
- Lists:
  - Saved voices (VoiceCard):
    - Shows description, reference text (editable), auto-plays reference audio.
    - Buttons:
      - Use in Speak: sets voiceId and navigates to SpeakPage.
      - Sparkle (Design from this voice):
        - Only for voices with chip selections.
        - Sets EditingVoice, navigates to VoiceDesignPage (qwen) so you can tweak and fork.
      - Layers (Reopen in Stitch Studio):
        - Only if the voice has a persisted stitch_plan with clips.
        - Rebuilds the Stitch Studio timeline from the saved plan.
      - Pencil: edit reference text inline.
      - Trash: delete voice.
  - Saved segments:
    - List of locked-in OmniVoice segments.
    - Search/filter by text or tags.
    - Each segment:
      - ClipPlayerUrl plays the audio.
      - "Insert into stitch editor" navigates to OmniVoice StitchTimeline and inserts clip.

### StitchStudioPage

Primary purpose: assemble reference voices from saved segments and existing voices, without needing an OmniVoice audition first.

Key behaviors:
- Shares the same store-backed stitch plan as the OmniVoice flow (ovStitchPlanClips, etc.), so switching between StitchStudioPage and OmniVoice's editor keeps your timeline.
- Steps:
  - Name the new voice.
  - Use StitchEditorInline to:
    - Insert segments from the segment library.
    - Insert saved voices from the voice library.
    - Reorder clips, adjust trim/fade, gaps.
    - Live preview with renderStitchPlan.
  - Save as reference voice → POST /omnivoice/save with stitch_plan.

### IntegrationsPage

Primary purpose: show how to call this service from other tools (Hermes, OpenAI SDK).

Key behaviors:
- Shows base model status via /health.
- Provides copyable:
  - curl example for POST /v1/audio/speech.
  - Python example using the OpenAI SDK.
- Displays list of available voice IDs.

### RuntimeConfigPage

Primary purpose: live-tweak certain container settings without a restart.

Key behaviors:
- GET /runtime/config to load RuntimeConfigState.
- Live-adjustable:
  - TTS_BACKEND (openvino / pytorch / pocket_tts) — triggers model reload.
  - IDLE_UNLOAD_SECONDS
  - OV_DYNAMIC_QUANT_GROUP_SIZE — triggers model reload.
  - SILENCE_TRIM toggle
  - SILENCE_TRIM_THRESH
  - SILENCE_TRIM_PAD_MS
- Read-only info:
  - Mounts, ref_audio, hf_token, device, torch_dtype.
- Not live (require rebuild / re-export):
  - TTS_MAX_SPEECH_SECONDS, MODEL_SIZE, compression.
- Only sends changed keys; avoids unnecessary reloads.

## 3. Key flows

### 3.1 Text-to-speech via SpeakPage

1. User:
   - Selects a voice (or leaves empty for base).
   - Types text.
   - Optionally picks tone/seed.
2. SpeakPage:
   - Disables button if modelLoaded is false.
3. On click:
   - Calls generateSpeech() (POST /generate).
   - Sets isGenerating = true, displays spinner.
4. On success:
   - Updates audioUrl, audioBlob, lastSeed.
5. On error:
   - Shows error text inline.

If the model is idle-unloaded but service_started is true:
- The backend will reload transparently; SpeakPage just sees a longer latency (no special UI).

### 3.2 VoiceDesign (Qwen engine)

1. User:
   - Opens VoiceDesignPage.
   - Selects traits via chips or writes a manual description.
   - Adjusts sample text, language, seed.
2. On preview:
   - Calls createVoiceDesign() (POST /voice_design).
   - Sets vdIsGenerating = true → starts polling /voice_design/progress.
3. On completion:
   - Stops polling, sets preview audio.
4. On save:
   - Calls saveVoiceDesign(previewId) (POST /voice_design/preview/{id}/save).
   - On success:
     - Sets vdSavedVoiceId.
     - Notifies VoiceDesignPage which:
       - Sets voiceId.
       - Refreshes voices.
       - Navigates to SpeakPage.

### 3.3 OmniVoice audition flow

High-level path: accent → segments → audition → lock-in → stitch → save.

1. User:
   - Opens VoiceDesignPage, selects "OmniVoice."
   - Sets accent, voice traits, advanced knobs.
   - Enters script text.
2. Audition:
   - OmniVoicePanel splits script into segments and calls:
     - auditionOmniVoiceStreaming() (POST /omnivoice/audition).
   - Sets ovIsAuditioning = true → polls /omnivoice/progress.
   - Shows per-segment candidates; user listens via ClipPlayer.
3. Lock-in:
   - For each segment, user picks a take.
   - OmniVoicePanel calls lockInOmniVoiceSegment() (POST /omnivoice/segments) to persist the chosen take into the segment library.
4. Stitch:
   - OmniVoicePanel opens StitchEditorPanel (modal) with:
     - Clips initialized from locked-in segments.
     - StitchTimeline: drag-and-drop reorder, trims, fades, gaps, DSP controls.
     - Live preview via renderStitchPlan.
5. Save:
   - OmniVoicePanel calls saveOmniVoice() (POST /omnivoice/save) with:
     - instruct, segments, accent_id.
     - stitchPlan (with clips, padding, DSP).
   - On success: sets ovSavedVoiceId, notifies VoiceDesignPage to refresh voices.

### 3.4 Stitch Studio editing and save

From StitchStudioPage:

1. User:
   - Names the new voice.
   - Inserts segments/voices into timeline via LibraryPickerButton.
2. Edits:
   - Reorder clips (drag or arrows).
   - Adjust per-clip trims, fades.
   - Adjust gaps and DSP settings.
   - Live preview continuously updates (debounced).
3. Save:
   - Calls saveOmniVoice with:
     - instruct = name.
     - segments = clip texts.
     - stitchPlan = serialized plan.
   - Sets ovSavedVoiceId in store; StitchStudioPage displays confirmation.

## 4. Global state and key stores (store.ts)

The frontend uses a single zustand store (useAppStore).

### Core fields

- page: current page
- theme: light/dark theme
- modelLoaded: boolean from /health
- serviceStarted: boolean from /health; once true, stays true
- loadingMessage: from /health
- text, voiceId, voices: SpeakPage-related state
- audioUrl, isGenerating, error: generation-related state
- editingVoice: voice queued for editing from VoiceLibraryPage
- designEngine: 'qwen' | 'omnivoice' (selected on VoiceDesignPage)
- activityStatus: shared activity/status info

### VoiceDesign (Qwen)

- vdSelections: chip selections (gender, age, register, textures, personas)
- vdManualDescription
- vdSampleText, vdSampleTextTouched, vdLanguage, vdSeedInput
- vdIsGenerating, vdProgress, vdError
- vdPreviewAudioUrl, vdPreviewBlob, vdPreviewId, vdPreviewSeed
- vdSavedVoiceId, vdIsSaving

### OmniVoice

- ovSelections: accent and voice traits
- ovCandidatesPerSegment, ovShowAdvanced, ovNumStepInput, ovDurationInput, ovSpeedInput, ovGuidanceScaleInput
- ovScriptText
- ovSegmentRack: per-segment candidates and selected take
- ovIsAuditioning, ovIsLockingIn, ovIsStitching, ovIsSaving, ovError
- ovProgress: progress from /omnivoice/progress
- ovCurrentJobId, ovJobStatus, ovJobSegmentsCompleted, etc. (streaming job tracking)
- ovStitchedUrl, ovStitchedBlob, ovSavedVoiceId
- ovLibrary, ovLibraryFilter, ovIsLibraryOpen, ovLibrarySelection: segment library UI
- ovAutoplayTakes

### Stitch editor

- ovStitchPlanClips: timeline clips
- ovStitchPlanPaddingMs: gaps between clips
- ovStitchPlanDsp: global DSP settings
- ovStitchEditorOpen
- ovStitchPreviewUrl, ovStitchPreviewBlob, ovIsRenderingPreview

Key behaviors:

- /health polling:
  - Runs in store.ts:
    - 1s interval until service_started is true.
    - After service_started, polls stop (cold-boot is the only case where waiting is meaningful).
  - Keeps modelLoaded and serviceStarted in sync.
- VoiceDesign polling:
  - Subscribes to vdIsGenerating; when true, polls /voice_design/progress every 700ms.
- OmniVoice polling:
  - Subscribes to ovIsAuditioning; when true, polls /omnivoice/progress every 700ms.

## 5. Swap / status handling

The frontend must not block or mislead the user when:

- the base model is loading (cold boot)
- a VoiceDesign swap is occurring (model swap_in_progress)

Key components:

- HealthStatusBanner:
  - Visible only when:
    - serviceStarted is false (true cold boot), and
    - current page needs the base model (SpeakPage, or VoiceDesignPage with Qwen engine).
  - Shows spinner and loading_message from /health.
  - Hides as soon as serviceStarted becomes true.
  - Does not show on OmniVoice panel because OmniVoice loads independently.

- useSwapStatus():
  - Polls /health every 2.5s (with exponential backoff on failures).
  - Reads swap_in_progress from health.
  - Used by SwapBanner on VoiceDesignPage:
    - If swapping:
      - Shows "Loading Voice Design model — Speak and Integrations will be briefly busy."

- Swap semantics:
  - During swap_in_progress:
    - /generate, /v1/audio/speech, etc. return 503.
    - UI components using these endpoints will see transient errors.
    - SpeakPage button already reflects model_loaded.
    - VoiceDesignPage uses SwapBanner to explain that this is expected.

## 6. Frontend build and container integration (summary)

- The frontend lives under frontend/.
- Build:
  - npm run build (tsc -b + vite build).
  - Output: frontend/dist.
- Container:
  - Dockerfile:
    - Multi-stage:
      - frontend-build: npm install → npm run build.
      - final:
        - COPY --from=frontend-build /frontend/dist frontend/dist.
        - Flask app serves those files at "/" when FRONTEND_ENABLED is set.
- Vite config:
  - Uses @ path alias for frontend/src.
  - Dev server proxies /health, /generate, /v1, /voice_design, /voices, /runtime to http://localhost:8318.
  - base: './' so all assets resolve relative for container serving.