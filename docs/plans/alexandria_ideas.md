# Alexandria Integration Plan — Hermes-Focused

> What this doc is:
> A focused, realistic integration plan for Qwen3-TTS OpenVINO,
> optimized for agent use (Hermes-style) instead of audiobooks.
>
> Hard constraints:
> - CPU-only, Intel, OpenVINO. No GPU, no CUDA, no torch.compile.
> - 1.7B quantized models run at ~8 GiB (INT4 + bf16 glue).
> - One container, one port, one primary model in memory at a time.
> - Everything additive and backward-compatible.

## 1. Consumer and Scope

- Primary consumer: Hermes (or similar OpenAI-compatible TTS client).
- Usage pattern:
  - Streamed, low-latency speech.
  - Per-utterance tone/instruct in the future.
  - Occasional "design a new voice from text" flows.

We intentionally drop:
- Audiobook-centric workflows (M4B, Audacity, large scripts).
- Persona auto-casting and LLM-driven script annotation as first-class.
- Heavy web UIs or Gradio integration.

We keep:
- Clean OpenAI-compatible endpoints.
- Instruct/tone support.
- Reproducibility (seed).
- Flexible language handling.
- Voice Design as a top-priority, first-class feature.

## 2. Model Landscape (qwen_tts 0.1.1)

qwen_tts 0.1.1 exposes three public generation methods:

| Method | Model | Purpose | Notes |
|---|---|---|---|
| `generate_voice_clone()` | Base | Zero-shot voice cloning from reference audio | No instruct |
| `generate_voice_design()` | VoiceDesign | Create a voice from natural-language description | instruct required |
| `generate_custom_voice()` | CustomVoice | Built-in speakers with instruct control | 0.6B disables instruct |

Key facts:
- Base:
  - Used for voice cloning (reference audio → voice_clone_prompt → generate_voice_clone).
  - No real instruct/tone control; instruct tokens are not trained.
- VoiceDesign:
  - Same 1.7B-class architecture as Base 1.7B.
  - Accepts instruct: natural-language voice description.
  - Output: generated audio of that described voice speaking some text.
  - We use this as: design → capture reference → clone.
- CustomVoice:
  - 9 built-in speakers with instruct.
  - Not useful for external voices.

Important:
- Instruct/tone is not a generic superpower of Base.
  It is semantic only on CustomVoice (1.7B) and VoiceDesign.
- For Hermes, we:
  - Use Base for cloned voices.
  - Use VoiceDesign (via model swap) to create new voices from text.
  - Reserve instruct support for future CustomVoice or advanced flows.

## 3. Voice Design (Primary New Capability)

Goal:
- One container.
- Lazy, on-demand VoiceDesign support.
- Easy for agents and humans.

Architecture:
- Export VoiceDesign transformer cores exactly like Base:
  - Same export tooling (same wrapper, same compression: INT4 + bf16 glue).
  - Separate IR set under a distinct directory (e.g., /ov/1.7B-voicedesign).
- Single container runtime:
  - Always-on Base 1.7B.
  - On demand:
    - Block requests (readiness → 503).
    - Unload Base IR + model.
    - Load quantized VoiceDesign IR + model.
    - Call `generate_voice_design()` for description + sample text.
    - Capture generated reference WAV.
    - Unload VoiceDesign.
    - Reload Base.
    - Restore readiness.

UX:
- New endpoint: POST /voice_design:
  - JSON:
    {
      "description": "Warm baritone, calm and even, subtle gravel.",
      "sample_text": "Hello, this is my voice.",
      "language": "English"
    }
  - Response:
    - WAV or base64-encoded reference audio.
    - Optionally include "voice_id" for caching.
- That WAV is then:
  - Used by the same tool (Hermes, agent, or other client) as:
    - `ref_audio` in a per-request voice clone call, or
    - Persisted as a named voice (if they want to).

Design rules:
- This is an occasional, heavier operation:
  - Slower than normal inference.
  - Model-swap latency expected.
- No separate containers.
- Keep it simple: description + sample_text → reference WAV.

## 4. Instruct / Tone Control

Goal:
- Expose instruct fields now, even if Hermes doesn’t use them yet.
- Enable future instruct-aware tools without re-architecting.

Implementation:
- Extend `/v1/audio/speech` and `/generate`:
  - Optional: "instruct": "calm, slightly breathless"
- Behavior:
  - If instruct is provided:
    - If current model is CustomVoice (1.7B), use instruct_ids via `generate_custom_voice()`.
    - If Base, log and ignore instruct (or document it as no-op).
- Keep instruct as a plain string:
  - Document safe patterns.
  - No schema; flexible.

Why:
- Future Hermes versions or other clients can use instruct.
- Zero overhead if no instruct is provided.
- Clear and additive.

## 5. Streaming (Refinements)

Current state:
- /generate/stream is real streaming:
  - F32LE PCM, chunked as vocoder completes 300-frame batches (~156 ms each).
  - TTFB under 1s for typical utterances.
- No framing, no SSE, no backpressure.
- Hermes (and similar agents) can already start playback before generation finishes.

We need three focused improvements:
1) Lightweight SSE wrapper
2) Segment and request boundaries
3) Backpressure / queue safety

All changes are additive and preserve the existing raw PCM endpoint.

1) SSE wrapper

Add an optional "stream_mode": "sse" to /generate/stream.

When stream_mode="sse":
- Content-Type: text/event-stream
- Use standard SSE framing for structured consumption.

Events:
- start:
  - id, model, backend (openvino/pytorch), seed (if used).
  - audio_params: format, sample_rate, channels.
- audio:
  - base64-encoded PCM chunk (same underlying stream as raw).
- end:
  - final metadata:
    - duration_ms, tokens_generated, steps_main, steps_predictor, backend, seed_used.

Behavior:
- The producer thread writes both:
  - PCM bytes into the queue (shared infrastructure).
  - SSE events derived from those same PCM bytes.
- Client can:
  - Use raw PCM for minimal latency, or
  - Use SSE for safe framing, metadata, and tooling integration.

2) Segment and request boundaries

For simple single-utterance flows (Hermes):
- start/end are enough.

For future multi-utterance / batch streaming:
- Introduce segment events:
  - segment_start: { segment_index, text, language }
  - segment_end: { segment_index, duration_ms }
- Allow an agent to:
  - Start playing segment N, and know when segment N+1 begins.
  - Avoid treating the whole stream as one monolithic audio.

Implementation note:
- Don't bake in heavy batch semantics yet.
- The events should be extensible and JSON-based, so Hermes or a companion script can parse them cleanly.

3) Backpressure and queue safety

Current risk:
- Unbounded Queue:
  - If Hermes or another client stalls, queue grows.
  - On a constrained KVM, that’s unnecessary pressure.

Fix:
- Use a bounded Queue with:
  - maxsize tuned to a safe memory ceiling (e.g., 20–40 chunks).
- On overflow:
  - Producer blocks briefly (soft throttle).
  - If block time exceeds a small timeout (e.g., 1–2s), abort:
    - Close stream.
    - Optionally mark as dropped or partial via SSE "error" event.

Goal:
- No silent memory explosion.
- Reasonable behavior under slow or stuck consumers.
- Still fast and low-latency when clients are well-behaved.

Keep it simple:
- Raw mode: unchanged.
- SSE mode: additive, opt-in.
- Backpressure: always-on, internal, invisible to a healthy client.

## 6. Seed and Reproducibility

We already have `_apply_optional_seed(seed)` wired only to internal endpoints.

Change:
- Add public "seed" field:
  - /v1/audio/speech
  - /generate
  - /generate/stream
- Behavior:
  - When seed is provided:
    - Call `_apply_optional_seed(seed)` before generation.
  - Document:
    - "Deterministic across calls on the same image and config;
       not guaranteed across updates."

Notes:
- For now, using global RNG is fine for our single-worker design.
- If we go multi-worker or long-running with heavy concurrency,
  we migrate to per-request torch.Generator.

## 7. Per-Segment Language (Future-Ready)

We already support a global language field per request.

Future:
- When batch or script endpoints are used (for longer interactions),
  each segment should allow its own "language".
- This is simple to implement when needed; we just:
  - Per-segment override: language -> merged into generate call.

Not urgent:
- For now, Hermes primarily sends single-utterance requests.

## 8. Public API Summary

Public endpoints (Hermes-friendly):

- POST /v1/audio/speech:
  - Input: { text, language?, instruct?, seed?, response_format? }
  - Behavior:
    - Uses Base 1.7B, generate_voice_clone().
    - If instruct provided and model supports it, include instruct_ids.
- POST /generate:
  - Input: same as /v1/audio/speech but agent-centric.
- POST /generate/stream:
  - Input: same + stream_mode? (default "raw", optional "sse").
- POST /voice_design:
  - Input: { description, sample_text, language? }
  - Behavior:
    - Lazy model swap.
    - Returns reference WAV.

Internal/development endpoints:
- /health
- /stream_internal, /batch_internal (unchanged, for parity/benchmarks).

## 9. LoRA (Later; Not Urgent)

LoRA is:
- Interesting if:
  - Zero-shot cloning isn’t good enough for a specific voice.
- Not needed now because:
  - We already support:
    - Strong zero-shot cloning.
    - VoiceDesign → clone → reuse.
- We may:
  - Bake a LoRA into the export later:
    - Wrap talker with adapter at export time.
    - Resulting OpenVINO IR "includes" that voice.

For now:
- Keep it simple: no LoRA, no PEFT wiring unless proven necessary.

## 10. Frontend / UX Architecture (2026-Style, Premium, Optional)

Goal:
- A single, high-quality, modern web UI that:
  - Feels like a premium 2026 AI tool, not a demo.
  - Showcases:
    - Real-time streaming
    - VoiceDesign
    - Tone/instruct
    - Reproducibility (seed)
- Thin, focused, and API-driven:
  - All intelligence stays in the backend.
  - Frontend is an elegant client, not a second app.

This section is intentionally opinionated and concrete.

1) High-level principles

- Single page, zero friction.
- Keyboard-first, mouse-friendly.
- Calm, focused UI:
  - Dark theme by default.
  - Minimal chrome, large interactive areas.
  - Micro-animations for status, not decoration.
- Everything flows from typing → hearing:
  - Text input is central.
  - Audio waveform and playback are always visible.
  - VoiceDesign and settings are one click away, not separate pages.

2) Stack choice (concise)

Recommended stack:
- Framework: Next.js 15 (App Router, Server/Client components).
- Language: TypeScript.
- Styling: Tailwind + a refined design system.
- Animation: Framer Motion (small, purposeful, not overdone).
- Audio:
  - Web Audio API (AudioContext) for low-latency streaming.
  - Custom waveform visualization using a Canvas component.
- State:
  - Use React Server Components for layout + metadata.
  - Use a lightweight client store (Zustand or similar) for audio playback, queue, and settings.
- Runtime:
  - Thin containerized frontend, or standalone deploy (Vercel, Cloudflare, or same KVM via Nginx).

Why this stack:
- Fast to build.
- Excellent DX.
- Perfect for a single-page, API-driven tool with real-time audio.
- Easy to extend later (auth, multi-user, usage tracking).

3) Core UI layout

Single main view with three zones:

Left: Context and voice control
- VoiceDesign panel:
  - Text prompt for voice description.
  - Sample text input.
  - Buttons: "Design voice", "Preview".
- Cloning panel:
  - Drag-and-drop or file picker for reference audio.
  - Transcript input.
  - "Use this voice".
- Quick presets (optional):
  - Curated voice presets for exploration.

Center: Main workspace
- Large text editor area:
  - Enter or paste text.
  - Optional: simple inline cues like /whispered, /calm, etc. mapped to instruct tokens.
- Controls:
  - Primary: "Generate".
  - Secondary: "Generate (streaming)".
- Live waveform:
  - Shows real-time waveform as audio streams in.
  - Playback scrubber; smooth, minimal, premium feel.

Right: History and reproducibility
- Scrollable history of generations:
  - Each entry:
    - Snippet of text
    - Voice (name / id)
    - Seed (if used)
    - Playback button
    - "Reuse prompt" / "Copy JSON" / "Export WAV"
- One-click reproducibility:
  - Re-run with same seed + params.

4) Streaming experience

This is a key UX differentiator.

Design:
- On "Generate (streaming)":
  - Frontend opens:
    - Either:
      - A raw PCM stream and decodes in Web Audio, or
      - An SSE stream and handles events client-side.
  - Behavior:
    - Waveform begins drawing immediately.
    - Subtle status line: “Generating…”, then “Streaming segment 1/1”.
    - User hears audio before the full utterance is done.
- No loading spinners; show flow, not waiting.
- For longer text:
  - Show segment boundaries:
    - Small markers on waveform.
    - Tooltip with segment text.

5) VoiceDesign UX

Make designing voices feel magical.

Flow:
- User:
  - Types: “Warm baritone, calm, slight gravel.”
  - Types: “Hello, this is my voice.”
  - Clicks "Design voice".
- UI:
  - Shows a quick state indicator.
  - Streams or loads the generated reference.
  - Plays it automatically in a clean waveform strip.
- Actions:
  - "Use this voice" → stored as active voice.
  - "Tweak" → pre-filled description; user adjusts, regenerates.
  - "Save" → saves to a local library (IndexedDB + optional server sync).

Important:
- Make this feel like a feature, not a lab tool.

6) Instruct/tone UX

Subtle but powerful.

Options:
- Inline syntax:
  - Example:
    - "Okay, let me think about this." (calm, thoughtful)
    - "You didn't tell me that." (sharp, a bit surprised)
- Or a tone selector (compact):
  - [Neutral] [Calm] [Excited] [Whispered] [Tense]
  - Internally mapped to instruct templates.

Rules:
- Keep it optional and unobtrusive.
- Never block the core "type → speak" loop.

7) Reproducibility and sharing

To make it feel "pro-grade":

- Every generation stores:
  - seed
  - model/backend info
  - instruct
  - voice id or reference
- Sharing:
  - Each entry has:
    - "Copy as OpenAI JSON"
    - "Export WAV"
    - "Share link" (if you add a tiny share endpoint later).

For Hermes-style users:
- A "Developer" tab:
  - Shows raw request JSON.
  - Lets you tweak temperature, top_p, etc.
  - Copies cURL / OpenAI SDK snippet.

8) Deployment

Two sensible options:

- Option A (simple):
  - Frontend runs in a second container on same KVM.
  - Exposed via:
    - Nginx reverse proxy:
      - / → frontend
      - /api/* → TTS backend
  - Tight integration, low overhead.

- Option B (modern, external):
  - Deploy frontend to Vercel / similar.
  - TTS backend is an external API.
  - Keeps UI upgrades independent of runtime.
  - Easier to expose demos safely.

For early versions, A is fine; for public, use B.

9) What "2026 premium" actually means here

To avoid vague design talk, this stack should deliver:
- Sub-200ms perceived latency for UI actions.
- Fluid, GPU-accelerated animations (where useful).
- Dark-first, refined typography (Inter/Geist or similar).
- Keyboard shortcuts:
  - Ctrl+Enter / Cmd+Enter → Generate
  - Space → play/pause
  - Alt+Arrow → navigate history
- Offline resilience:
  - Graceful states for backend down.
  - Local queue for history and presets.
- No clutter:
  - No sidebars full of options.
  - No heavy settings modals.
  - Just: text, voice, generate.

10) VoiceDesign: Prompt Engineering and Guardrails

Based on Alexandria’s VOICE_REFERENCE.md and empirical tests with VoiceDesign, we should not treat “voice description” as a free-form text field. Unstructured prompts create unstable or unusable voices.

We should expose structured, safe patterns and make it hard to do it wrong.

Core empirical rules (from Alexandria tests):

- Anatomy-first wins:
  - Descriptions with concrete acoustic targets (register, timbre, texture) produce stable, consistent voices.
- Formula that works:
  - [register] + [2-3 texture/timbre descriptors] + [tonal character adjectives]
  - Example:
    - "Deep male baritone, rich chest resonance, warm smooth timbre, hint of gravelly texture."
- Keep description purely acoustic:
  - Use description for identity.
  - Use instruct for emotion, delivery, pacing.
- Mixing acoustic + behavioral = unstable:
  - Example failure: "bright" + "youthful energy" → emotional chaos, wild swings.
- Control terms → consistent voices:
  - "silky", "even", "precise", "firm", "rounded", "grounded", "crystalline".
- Female voices tend more consistent than male.

We translate these into UX, not just documentation.

10.1) Structured Voice Design Prompt Assistant

In the UI (Left panel: VoiceDesign), provide:

- Register selector:
  - Chips: [Bass] [Baritone] [Tenor] [Alto] [Mezzo-Soprano] [Soprano]
- 2-3 texture/timbre chips (safe, tested terms):
  - Examples:
    - [Silky] [Even] [Warm] [Rich] [Dark] [Authoritative] [Slight gravel] [Soft rounded]
- A small “character” chip set (tonal adjectives only, no delivery):
  - [Calm] [Gentle] [Firm] [Cool] [Mysterious]

Behavior:
- UI composes a single description string from selections.
- User can:
  - Use the composed description, or
  - Switch to “Advanced” and edit it as text.
- Disallow/flag known unstable combos:
  - Example: if user includes both "bright" + energy terms → show a warning: “This combination tends to destabilize the voice. Consider removing energy-related words from the description and using them in instruct instead.”

This is a killer feature:
- Users get great, stable voices without knowing the model’s quirks.
- Feels like a premium AI product, not a raw model interface.

10.2) Instruct/Tone UX (Separation of Concerns)

Use instruct for emotional and delivery control, not identity.

UI:
- Provide a “Tone” control under the main editor:
  - Chips or dropdown with proven patterns:
    - [Neutral] [Calm, thoughtful] [Warm and amused] [Tense, whispered] [Softly excited] [Frustrated, clipped]
- Internally map these to instruct strings.
- Explain briefly:
  - “Voice: defines what it sounds like.
     Tone: defines how it delivers this line.”

This directly reflects Alexandria’s findings:
- Description = instrument.
- Instruct = performance.

10.3) Developer / API Integration

For API clients (like Hermes), we should:
- Expose the same structured fields as optional:
  - description
  - instruct
- Document:
  - The formula (register + texture + tone)
  - Known unstable combos (acoustic + behavioral mixing).
- Example prompts:
  - Provide 6-10 canonical examples that are tested and safe.

Goal:
- A developer doesn’t need to read 3 pages of lexicon to get a decent voice.
