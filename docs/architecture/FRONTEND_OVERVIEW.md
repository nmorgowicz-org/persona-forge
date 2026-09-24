# Frontend Overview

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

- PersonaWizardPage (wizard)
- SpeakPage (speak)
- VoiceDesignPage (voice-design)
- VoiceLibraryPage (voice-library)
- VoiceEditPage (voice-edit)
- StitchStudioPage (stitch-studio)
- IntegrationsPage (integrations)
- RuntimeConfigPage (runtime)

### SpeakPage

Primary purpose: generate speech using an existing voice.

Key behaviors:

- Text input (textarea).
- Voice selector (VoiceSelector) backed by /voices, labelled `VOICE`.
- Language selection, labelled `LANGUAGE`.
- `POST-PROCESSING` — the control that reads "Off" when idle, labelled for what it does rather
  than for its current value. It selects the polish preset applied to the rendered audio after
  generation, and is passed to the backend as `instruct`.
- Optional random seed input.
- On "Generate":
  - POST /generate with text, voice_id, language, instruct (polish preset), seed.
  - Progress is polled and shown on a determinate `role="progressbar"` with `aria-valuenow`
    (percentage, ETA, live RTF where the backend reports them), and completion is announced in
    the app's single live region.
  - On success: render audio via AudioPlayer, display seed, offer "Lock this seed."
- Disabled when:
  - text is empty
  - isGenerating is true
  - the service has not started yet (`serviceStarted` from /health). Before the first
    successful load the whole shell is replaced by the cold-boot `StartupState`; afterwards an
    idle-unloaded model reloads transparently and the request simply takes longer.

### VoiceDesignPage

Primary purpose: design a new voice using either:

- Qwen (VoiceDesignPanel)
- OmniVoice (OmniVoicePanel)

Key behaviors:

- EngineSelector toggles between qwen / omnivoice.
- Default engine is always **OmniVoice**: voice design is a design-time concern, not a serving
  concern, so it is not coupled to `TTS_BACKEND` (`pocket_tts` stays the default for
  cloning/serving). A user's explicit choice persists for the session.
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

### VoiceEditPage

Primary purpose: create, preview, save, and promote prosody variants for one saved voice.

Key behaviors:

- Selects only saved voice-library entries; it does not create voices or expose Pocket built-ins.
- Reuses the prosody preview, variant-save, and activation endpoints already used by Voice Library.
- A Stitch Studio save can deep-link directly here. The one-shot target is consumed only after the saved voice has been selected.

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
  - Save as reference voice → POST /omnivoice/save with stitch_plan; plain saving does not activate the API default.
  - “Adjust prosody” opens Voice Edit with the saved voice preselected.

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
   - Sets ovSavedVoiceId in store; StitchStudioPage displays confirmation, optional API activation outcome, and an Adjust prosody handoff.

### 3.5 Voice Edit

1. Choose a saved voice; a Stitch Studio deep link chooses it automatically.
2. The `AlignmentCompare` A/B strip mounts as soon as a voice is selected — with no preview yet
   it renders the ORIGINAL lane alone (waveform, transport, word labels), so the workspace is a
   waveform surface from the start rather than a bare form.
3. Preview an adjustment: the ADJUSTED lane appears below ORIGINAL, with cut markers and the
   manufactured-pause band, on one shared time ruler.
4. Save the take as a non-active variant, then promote it explicitly when ready.
5. Voice Library and Voice Edit read the same persisted variant list.

## 4. Controls reference

How the instrument controls behave, and where the rules come from. The gesture grammar is
one implementation (`hooks/useDragScrubValue.ts`); the knob and fader
(`components/ui/knob.tsx`, `components/ui/fader.tsx`) are the same engine with `axis: 'y'`.
Anything not listed here has no hidden gesture.

### Numeric controls (knob, fader, stepper, slider field)

| Gesture | Behaviour |
| --- | --- |
| Drag | Changes the value. Horizontal on fields and steppers, vertical on knobs and faders. |
| Shift + drag | Fine adjust — the same travel covers a fifth of the range. |
| Wheel over the control | One `step`. Shift makes it a tenth of a step. |
| Double-click the control's row or label | Resets to that control's own default (trim/fade → 0, deck speed → 1.0 s, a gap → its punctuation-suggested value, DSP → the plan-start value). Not the value itself: a single click there opens the typed editor. |
| Click the value | Type it. The grammar accepts a bare number, `ms`, `s` (scaled by 1000), `×`, and a trailing unit such as `dBFS`; `Enter` commits, `Escape` cancels. |
| Arrow keys | One `step`; Shift makes it ten steps. The control is a single tab stop — the `−`/`+` buttons sit outside the tab order. |
| Keyboard | Knobs and faders expose `role="slider"` with `aria-valuenow` and `aria-valuetext` (`"−18.0 dBFS"`), so a screen reader reads the unit, not the raw number. |

**Wheel nudging is opt-in per control, and deliberately absent on the timeline.** The gap
control lives inside the timeline's horizontal scroll container, where a wheel gesture belongs
to scrolling; it was excluded in A-1 and the CP1 review confirmed the exclusion.

### Keyboard

| Keys | Action | Scope |
| --- | --- | --- |
| `Cmd/Ctrl+K` | Open the command palette | Global |
| `?` | Show the keymap | Global |
| `Space` | Play / pause the arrangement | Stitch Studio |
| `←` / `→` | Move the playhead, or the selected clip | Stitch Studio |
| `Shift+←` / `Shift+→` | Finer step | Stitch Studio |
| `↑` / `↓` | Move the selected clip in the arrangement | Stitch Studio |
| `Delete` / `Backspace` | Remove the selected clip | Stitch Studio |
| `Cmd/Ctrl+Z` | Undo one plan change (a gesture is one entry) | Stitch Studio |
| `Shift+Cmd/Ctrl+Z` | Redo | Stitch Studio |
| Click the ruler | Seek | Stitch Studio |
| `Ctrl/Cmd` + wheel over the timeline | Zoom, anchored on the pointer | Stitch Studio |

The palette and the `?` keymap both read one registry (`hooks/useGlobalShortcuts.ts`), so a
binding cannot be documented in one place and dispatched from another. Dispatch is
innermost-first, so a page can shadow a global binding, and the editable-target guard lives in
the dispatcher rather than in each surface.

### Metering

- **Level meter** (`components/audio/LevelMeter.tsx`): −60…0 dBFS with the standard ticks,
  instant attack, 20 dB/1.5 s fall, 1.5 s peak hold. Drawn per animation frame from the media
  clock, with `aria-valuenow` written from the same value it draws. Reduced motion keeps the
  true level and drops only the ballistic travel.
- **Clip stats**: peak, RMS and integrated loudness (ITU-R BS.1770-4, K-weighting with 400 ms
  gated blocks) computed off-thread by the STFT worker. The clip LED latches on a sample peak
  at or above −0.1 dBFS and clears on click.
- **Readouts are figures with units**: every one is tabular (`.readout`, Geist Mono with
  `tabular-nums`) and always carries its unit, so a changing value cannot reflow the text
  around it and `520` is never read as seconds. Time and level readouts are asserted as a
  class of thing by `tests/ui/core/readouts.spec.js`, not as a list of testids.

### Async feedback

One live region (`components/ui/announcer.tsx`, `role="status"`, mounted for the app's life and
cleared on a timer) carries generation, save, promote and copy confirmations. Progress is
determinate wherever the backend measures it (`components/ui/progress.tsx` on radix `Progress`);
empty surfaces render `components/ui/empty-state.tsx` with exactly one next action; the cold
boot gets `StartupState.tsx` instead of a bare spinner.

## 5. Global state and key stores (store.ts)

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

## 6. Swap / status handling

The frontend must not block or mislead the user when:

- the base model is loading (cold boot)
- a VoiceDesign swap is occurring (model swap_in_progress)

Key components:

- StartupState (cold boot): while `/health` has answered and reports that the service has never
  started, the shell is replaced by the startup state — the Signal Crucible mark over the dimmed
  startup field with a stepped load readout and `data-testid="startup-state"`. It is gated on
  `healthChecked`, not on `serviceStarted` alone: before the first answer, "not started" and "not
  asked yet" are the same state, and treating them alike flashed the splash on every page load.
  A startup failure (`healthStatus === 'error'`) resolves to the error banner instead.

- HealthStatusBanner:
  - Visible while a *later* model load is in flight (`loading_message`) on any page, and for
    REF_TEXT warnings on Speak. It no longer carries the cold boot — StartupState does.
  - Shows a spinner and `loading_message` from /health, or a persistent error bar when the
    health status is `error`.
  - Hides as soon as the load reports complete.
  - Does not show on the OmniVoice panel because OmniVoice loads independently.

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

## 7. Frontend build and container integration (summary)

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
  - Dev server proxies /health, /generate, /v1, /voice_design, /voices, /runtime to <http://localhost:8318>.
  - base: './' so all assets resolve relative for container serving.
