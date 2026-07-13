# Persona Forge — Technical Roadmap & App Specification

Date: 2026-07-13
Status: Active Engineering Specification. This document serves as both a product roadmap and a technical guide for transitioning Persona Forge from a voice-design prototype into a production-grade application.

---

## 1. System Invariants & Constraints
Every roadmap item must adhere to these hard constraints to avoid system instability on the target hardware (dockermisc1).

- **The One-Model Invariant**: Only one large model may be resident in VRAM at any time. The system operates in `LOW_RAM_MODE=1` with a single gunicorn worker. Any feature that requires switching backends (OpenVINO -> Pocket TTS -> OmniVoice) must trigger a full unload of the previous model.
- **Memory Floor (M9)**: Live serving already operates near the M9 memory floor. All new persistence layers must be disk-backed (SQLite/JSON). In-memory caches for history or projects are strictly prohibited.
- **The Executor Bottleneck**: All generation and design operations serialize through `model.executor`. New long-running features (e.g., Long-form generation) must implement an asynchronous job queue with progress tracking and cancellation to avoid blocking the request thread.
- **Dual-Audience UX**: The interface must simultaneously serve the "Beginner" (guided, teachable, tooltip-heavy) and the "Expert" (transparent mechanisms, raw parameter access, high-density data).

---

## 2. Theme 1: Persistence & Project Layer (P0)

**Vision**: Transform the app from an ephemeral "render-and-download" tool into a durable workspace where users can manage scripts, iterate on takes, and archive their best work.

### 2.1 Generation History & Recents (P0)
- **Status**: Not Implemented (Reference history exists).
- **Current State**: `src/qwen3_tts/voice_library.py` tracks history for *voice reference edits* (snapshots), but the actual *audio renders* are not persisted.
- **Technical Implementation Path**: 
  - Implement a SQLite database to store `RenderJob` records.
  - **Schema Requirements**: Store input text, selected voice/variant ID, seed, generation parameters, backend used, output metrics (RTF, duration), and a filesystem path to the resulting `.wav`/`.mp3`.
  - **Retention Policy**: Implement a size-based or count-based TTL to prevent disk bloat.
- **Why**: Enables "Regenerate with same settings," allowing users to tweak a single parameter (like seed or speed) without re-typing the script.

### 2.2 Projects & Script Grouping (P1)
- **Status**: Not Implemented.
- **Technical Implementation Path**: 
  - Create a `Project` entity that groups a body of text (the "Script") with multiple "Takes" (different voice/style attempts).
  - This entity should feed directly into the "Long-form" and "Stitch Studio" workflows.
- **Why**: Production work involves a single script with multiple iterations; grouping these prevents the "recents" list from becoming a chaotic stream of unrelated fragments.

### 2.3 Output Profiles (P1)
- **Status**: Partial (Model profiles exist).
- **Current State**: `src/qwen3_tts/model.py` uses `ModelProfile` for backend configurations and IR paths.
- **Technical Implementation Path**: 
  - Implement `ExportProfile` presets. These are not model configs, but post-processing chains.
  - **Parameters**: Target loudness (e.g., -16 LUFS), format (MP3/WAV/FLAC), and a "polish" preset (e.g., high-pass filter, normalization).
- **Why**: Ensures consistent audio quality across a project regardless of the backend used.

---

## 3. Theme 2: Real-Usage Generation Features (P0)

**Vision**: Provide the tools necessary for professional narration, moving beyond short-form samples to full-length audio production.

### 3.1 Pronunciation Lexicon (P0)
- **Status**: Not Implemented.
- **Technical Implementation Path**: 
  - Implement a user-configurable dictionary for names, brands, and acronyms.
  - **Mechanism**: A text-normalization pre-pass that replaces "lexicon keys" with "phonetic respellings" before the text hits the TTS engine.
  - **Accent Awareness**: Lexical entries should be scorable to an accent (e.g., a word pronounced differently in AU vs GB).
- **Why**: This is the #1 quality lever for professional work; without it, the user is forced to manually misspell words to get the correct pronunciation.

### 3.2 Long-Form / Document Mode (P1)
- **Status**: Partial (Stitching and Analysis exist).
- **Current State**: `audio_post.stitch_segments` handles the final merge. `audio_style.analyze_reference` provides the critical feedback loop for prosody and speech rate.
- **Technical Implementation Path**: 
  - **Pipeline**: Text Input -> Sentence/Paragraph Segmentation -> Job Queue -> Per-chunk Generation -> Stitching.
  - **The "Surgical Retry" Workflow**: The UI must allow the user to identify a single "bad" chunk in a 10-minute render and regenerate only that segment without re-rendering the whole document.
- **Why**: Large renders are prone to occasional "glitches." A full re-render is a waste of time and compute.

### 3.3 Best-Take Gallery (P1)
- **Status**: Not Implemented.
- **Technical Implementation Path**: 
  - Expand the generation UI to support "Batch Generation" (N seeds at once).
  - Implement a "Candidate Gallery" where the user can audition multiple versions of the same line and "Keep" the best one.
- **Why**: TTS is stochastic. The best delivery often happens on the 3rd or 4th try.

### 3.4 Text Markup & SSML-Lite (P2)
- **Status**: Not Implemented.
- **Technical Implementation Path**: 
  - Implement a limited set of markup tags (e.g., `<pause time="1.0s"/>`, `<emphasis>`) that are translated into backend-specific controls.
  - **Honesty Constraint**: Only offer tags that the active backend actually supports.

---

## 4. Theme 3: Accent Workbench (P0)

**Vision**: Transform accent control from a hidden helper into a first-class design surface.

### 4.1 The Two-Layer Strategy
To overcome the hard limits of the TTS engines, the Workbench decouples *Definition* from *Production*.

1. **Definition Layer (Engine-Agnostic)**: Uses the lexical-set taxonomy in `frontend/src/lib/accentBank.ts` to describe any accent via features like RHOTICITY or GOAT vowels.
2. **Production Layer (Engine-Bound)**: Determines how the audio is actually created:
   - **Route A (OmniVoice Instruct)**: For the 10 supported English accents. Use the "Hero-take" assembly to generate a high-coverage reference.
   - **Route B (Reference Clone)**: For unsupported accents. Use a real audio sample (user upload or HF voice) as a reference for Pocket-TTS/Base.
   - **Route C (Unsupported)**: Explicitly mark the accent as "generation-unsupported," guiding the user toward Route B.

### 4.2 Implementation Details
- **Accent DNA Panel (Partial)**: Transition `FEATURE_INFO` from code comments/tooltips into a visible, teachable panel.
- **Hero-Take Coverage Map (Partial)**: Use the `buildHeroTake` logic to show a real-time checklist of the 8 core features.
- **Pocket-TTS Hero-Clip Design (Partial)**: 
  - **Constraint**: Pocket TTS faithfully inherits the prosody (spacing/energy) of the reference.
  - **Technical Verification**: The system already implements a robust analysis suite in `src/qwen3_tts/audio_style.py` via `analyze_reference()`. This calculates:
    - **Pause Ratio**: `pause_total_seconds / duration`
    - **Speech Rate Proxy**: Words-per-second (when transcript is present) or voiced-frame ratio.
    - **Pause Metrics**: Median and longest pause durations in ms.
  - **Requirement**: The Workbench must use these metrics to verify that a generated hero take matches the "Target Delivery" (e.g., "Calm" vs "Energetic") before it is committed as a variant.

---

## 5. Theme 4: Integration & API Hardening (P1)

**Vision**: Secure the application for network exposure and provide a professional developer experience.

### 5.1 AuthN & Rate Limiting (P0)
- **Status**: Not Implemented.
- **Technical Implementation Path**: 
  - Implement an API-key gate on `/v1/audio/speech` and `/runtime/config`.
  - Add a middleware layer in `src/qwen3_tts/app.py` for per-key rate limiting and request size caps.

### 5.2 OpenAI-Route Completeness (Partial)
- **Status**: Core bridge functional in `app.py`.
- **Technical Implementation Path**: 
  - Extend `response_format` to support `opus` and `flac` via `audio_post.py`.
  - Implement per-key usage tracking to monitor token spend.

### 5.3 In-UI Streaming (Partial)
- **Status**: `/generate/stream` provides raw PCM.
- **Technical Implementation Path**: Implement a frontend "Progressive Player" that buffers the PCM stream.

---

## 6. Theme 5: Observability & Ops (P1)

**Vision**: Provide real-time visibility into the resource-constrained environment of the M9 floor.

### 6.1 Status Dashboard (Partial)
- **Status**: Backend data exists; UI missing.
- **Technical Implementation Path**: 
  - Create a dedicated dashboard surfacing data from `/health` and `model._process_rss_mib()`.
  - **Metrics**: Live RSS vs. M9 Floor, Queue Depth, Rolling RTF, and Model Load State (Warm/Cold).

### 6.2 Actionable Error Surfacing (Partial)
- **Status**: Partial implementation in `/v1/audio/speech`.
- **Technical Implementation Path**: 
  - Replace raw `Exception` strings in `app.py` with a structured error system (e.g., `error_code`, `user_message`, `recovery_step`).

---

## 7. Theme 6 & 7: UX Polish & Trust (P1/P2)

**Vision**: Establish the "2026 App" feel through cohesive design and transparent AI provenance.

### 7.1 UX Cohesion (P1)
- **Command Palette (⌘K)**: Implement a global jump-to action.
- **Design Tokens**: Move beyond raw Tailwind to a formal shared component library.
- **Job Notifications**: Implement a toast system for long-running generations.

### 7.2 Trust & Provenance (P2)
- **Provenance Metadata**: Embed model ID, voice ID, and timestamp into exported audio files.
- **Watermarking**: Implement an optional inaudible watermark.
- **Abuse Caps**: Implement strict content-length limits to protect the single-worker queue.

---

## 8. Suggested Sequencing (Post-Foundation)

1. **Security Hardening**: Auth + Rate Limiting (Theme 4).
2. **The "App" Leap**: Generation History (Theme 1) + Pronunciation Lexicon (Theme 2).
3. **The Workbench**: Accent DNA Surfacing (Theme 3).
4. **Ops Safety**: Status Dashboard (Theme 5).
5. **Production Scale**: Long-form Orchestration (Theme 2).
