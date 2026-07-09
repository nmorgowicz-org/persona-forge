# Manipulating a Voice

Date: 2026-07-06
Status: Authoritative analysis — latest research incorporated.

This doc is the single, technical reference for what is realistically controllable about a
voice's prosody, energy, accent, and style across the models in our stack.

Scope:
- Accent
- Energy (calm vs. energetic)
- Speed / pacing
- Prosody style (natural, tight, expressive, soft, emotional)
- Style "presets" (named configurations selectable by users)

We assume familiarity with the runtime (model.py, OpenVINO adapters, VoiceDesign/OmniVoice
swap, Pocket TTS integration). This doc does not re-explain plumbing.

─────────────────────────────────────────────────────────────────────
1. Executive summary
─────────────────────────────────────────────────────────────────────

- No model in our stack provides a stable, independent numeric knob for energy, emotion,
  accent, or speed on an existing cloned voice.
- Prosody is overwhelmingly reference-audio driven: whatever the reference clip sounds like
  is what you get.
- Qwen3-TTS VoiceDesign is the strongest instruction-driven tool: it supports natural-language
  control of accent, emotion, energy, pace, and demographics during voice creation, and can
  perform target-speaker editing (change energy/pace while preserving identity). It has been
  formally evaluated on InstructTTSEval and significantly outperforms GPT-4o-mini-tts while
  remaining competitive with Gemini.
- Qwen3-TTS Base (1.7B/0.6B) is not instruction-tuned for style control and has no explicit
  instruct field for arbitrary reference editing; ChatML system/user messages can softly nudge
  energy/emotion/style in an emergent, non-guaranteed way.
- OmniVoice offers discrete accent labels, a speed parameter, a duration parameter, and
  Chinese dialect support — useful for accent/speed tuning at reference generation time.
  Its style vocabulary is limited (only "whisper" is officially supported; other style phrases
  rely on emergent behavior and cannot be relied on).
- Pocket TTS is pure reference cloning with no style or accent control; best as a fast
  inference engine for pre-styled references. It ships with a built-in set of reference
  voices (alba, vera, anna, jean, marius, etc.) that can be exposed as out-of-the-box
  options in a speak tab.
- The only realistic "prosody presets" are:
  - (A) Multiple style-tuned reference clips per voice, selected at runtime.
  - (B) Fixed VoiceDesign instruction templates that produce style-specific references
    off-line and are validated empirically.
- Global knobs (temperature, EOS, etc.) can modulate "feel" subtly but are not semantic style
  controls and should not be treated as such.

─────────────────────────────────────────────────────────────────────
2. Qwen3-TTS family (Base, VoiceDesign, CustomVoice)
─────────────────────────────────────────────────────────────────────

2.1 1.7B-Base (zero-shot cloning)

Role:
- Primary voice-clone engine. Given reference audio, it copies that voice and reads any text
  in that voice.

Prosody control:
- Primarily reference-audio driven. The model's prosody (pacing, expressiveness, energy, accent)
  is inherited from the reference clip. This is the dominant factor.
- ChatML instruction control exists but is NOT stable:
  - System/user messages can include style hints (e.g. "speak calmly", "be energetic")
    and can modulate energy, style, and emotion to some degree.
  - The effect is soft, emergent, probabilistic, and content-dependent. It is not modular
    and will not consistently reproduce the same result across different scripts.
  - There is no guaranteed mapping from instruction to prosody.
- There is no dedicated `instruct` parameter that the Base checkpoint interprets. The existing
  `instruct` field in app.py is for forward-compat; currently a no-op.

What it CANNOT do:
- Change accent independently of reference.
- Provide independent speed control.
- Provide stable numeric knobs for energy, emotion, or style.

Practical conclusion:
- Base is excellent for identity + prosody cloning from a reference.
- Any manipulation of energy, speed, accent, or emotion must happen upstream via:
  - Choosing a different reference clip, or
  - Using a style-tuned reference generated with VoiceDesign/OmniVoice.

2.2 1.7B-VoiceDesign (instruction-based voice creation and target-speaker editing)

Role:
- Generate a new voice identity from a natural-language description; OR, given a reference
  speaker, preserve identity while modifying selected attributes via natural-language
  instructions (this is "target-speaker editing").

Prosody control:
- Strong instruction-prompt driven control:
  - Gender, age, accent, emotion, speed/pace are all respondable via prompts:
    "energetic", "angry", "calm", "broadcast announcer", "warm storyteller", etc.
  - Natural language control works; no fixed tag vocabulary.
- Demonstrates high alignment on benchmarked styles:
  - 85 APS (Auto Prosody Score) on ZH, 82 on EN for style alignment with prompts.
- Formally evaluated on InstructTTSEval:
  - Significantly outperforms GPT-4o-mini-tts on instruction-following quality.
  - Competitive with Gemini on the same benchmark.
- Capable (softly, emergently) of changing:
  - Energy: "more excited", "calmer"
  - Pacing: "speak faster", "slow down"
  - Style: "calm professional", "announcer-like", "warm storyteller"

Target-speaker editing:
- Given an existing reference + instruction, can alter energy/pace/emotion while
  largely preserving the original identity.
- This is a key capability for generating style-tuned reference variants.

Important caveats:
- Not deterministic knobs; still language-model-style instruction following. Effects are
  probabilistic and content-dependent.
- Base model (pure cloning) currently has NO explicit instruct field for arbitrary reference
  editing. Target-speaker editing is a VoiceDesign capability, not available via the Base
  model's standard clone path.
- CustomVoice supports instruction control, but only for its 9 built-in speakers.
- For arbitrary user-uploaded references, "target-speaker editing" is more experimental:
  we rely on model-level behavior (via VoiceDesign or CustomVoice pipelines), not a clean
  API we control today.

Limitations:
- Not a drop-in replacement for Base:
  - It is more specialized and slower; not designed as the day-to-day cloning workhorse.
  - Its outputs are meant to be:
    - Reference clips fed to Base for cloning, or
    - Final audio when the voice itself is being designed.
- No stable numeric knobs: instruction effects are probabilistic.
- Long-form drift is possible: extended speech may not maintain the instructed style.

Practical conclusion:
- Best-in-class for:
  - Creating style-specific reference clips ("calm professional", "energetic presenter").
  - Generating accent-varied references for a base identity.
  - Target-speaker editing: adjusting energy/emotion on an existing voice.
- Not for:
  - Per-utterance style switching; the reference is static once baked.

2.3 1.7B-CustomVoice / 0.6B-CustomVoice

Role:
- Instruction-based emotion/style control on 9 built-in voices. No external cloning.

Prosody control:
- Built-in voices can be modulated via instructions (e.g. "speak warmly", "speak angrily").
- Fixed speaker set: cannot accept arbitrary reference audio.

Limitations:
- No external voice cloning.
- Instruction control is limited to the 9 built-in speakers.
- Not general-purpose for our use case.

2.4 Key limitations across the Qwen3-TTS family

- No stable numeric sliders for energy, rate, emotion, or accent.
- Instruction effects are probabilistic and content-dependent.
- Long-form prosody drift: extended speech may not maintain a requested style or energy.
- No clean separation between identity and prosody: changing one tends to affect the other.
- For arbitrary user-uploaded references, "target-speaker editing" is experimental and not
  exposed as a stable, controlled API today.

─────────────────────────────────────────────────────────────────────
3. OmniVoice (accent, speed, duration, and style)
─────────────────────────────────────────────────────────────────────

Role:
- Accent design, speed tuning, duration control, and per-segment audition. Generates candidate
  clips that can be cherry-picked into reusable reference voices.

Voice design (instruct):
- Supports accents via instruct for English text:
  - american, british, australian, canadian, indian, chinese, korean,
    japanese, portuguese, russian accents
- Chinese dialects supported for Chinese text (e.g. 东北话, 四川话).
- Style vocabulary is LIMITED:
  - Only "whisper" is officially supported as a style token.
  - Phrases like "calm professional", "excited coach", etc. are NOT in the defined token set.
    They may be partially respected via emergent behavior, but cannot be relied on.
- Formatting: comma-separated attributes, e.g. "female, young adult, australian accent".

Speed and duration:
- speed: >1.0 faster, <1.0 slower (0.5–2.5 range). Changes pacing without changing timbre.
- duration: explicitly sets the expected duration of output for a given input. Useful for:
  - "calm/slow" variants (longer duration)
  - "energetic/compact" variants (shorter duration)
- These are viable tools for constructing reference clips with different prosodic styles
  from the same base voice, without fundamentally changing its timbre.

Prosody control:
- Primarily reference-audio driven: identity via speaker embedding, prosody influenced by
  reference audio.
- Instruction-following exists ("speak excitedly", etc.) but is underpowered and inconsistent
  compared to Qwen3-TTS VoiceDesign.

Non-verbal tokens:
- Tokens like [laughter], [sigh] exist but are unreliable.

Limitations:
- No continuous energy/emotion control; no stable style presets.
- Closed instruct vocabulary: must follow exact category order; unknown tags raise ValueError.
- For emotional variation, the recommended approach is segment-level:
  - Use different emotional reference clips per segment.

Practical conclusion:
- Best-in-class for:
  - Accent presets and accent-varied references.
  - Speed-tuned references ("normal", "fast", "slow").
  - Duration-tuned references ("calm/slow" vs "energetic/compact").
  - Per-segment emotional variation using distinct emotional reference clips.
- Not for:
  - Fine-grained emotional styling via natural language prompts.
  - Direct replacement for Base's zero-shot cloning.

─────────────────────────────────────────────────────────────────────
4. Pocket TTS (~100M, CPU-only)
─────────────────────────────────────────────────────────────────────

Role:
- Lightweight, fast backend for cloning-style TTS on CPU. Pure reference-audio driven.

Prosody control:
- Fully reference-audio driven: inherits style, pacing, and accent from the reference clip.
- No instruction tuning, no style tags, no emotion or accent knobs.

What it cannot do:
- Change accent beyond what's in the reference.
- Directly control energy, style, or emotion at generation time.
- Adjust speed independently.

Available knobs:
- `temp`: sampling temperature — affects variability, not systematic style.
- `lsd_decode_steps`: quality/refinement; higher = better fidelity, slower.
- `eos_threshold`: when to end; can avoid clipped or drawn-out endings.
- `frames_after_eos`: extra tail after EOS; affects "breathed" vs "clean cut" feel.
- These are global "feel" tuners: subtle adjustments only, not semantic style controls.

Built-in reference voices:
- Pocket TTS ships with a curated set of reference voices on Hugging Face
  (kyutai/tts-voices): alba, vera, anna, jean, marius, cosette, and others.
- Some voices are VCTK-based (conversational and reading tones).
- Some have specific tonal qualities (e.g. cosette has a "confused tone"; some are donation-style).
- Some are accented (e.g. vera has an Australian flavor).
- To expose "out-of-the-box" voices in our speak tab:
  - Integrate a curated subset (VCTK/Common Voice-safe) into the dropdown.
  - Call Pocket TTS using its `get_state_for_audio_prompt("vera")`-style APIs.
- Important:
  - Licensing per voice must be respected (VCTK, Common Voice, etc.).
  - Running both Qwen3-TTS and Pocket TTS side-by-side increases memory usage; we need
    a clean architecture (separate process or dual endpoint).

Practical conclusion:
- Treat Pocket TTS as:
  - A pure cloning engine for user-uploaded references.
  - A fast inference engine for pre-styled references generated by Qwen3-TTS or OmniVoice.
  - A source of ready-to-use reference voices (alba, vera, etc.) for the speak tab.

─────────────────────────────────────────────────────────────────────
5. General autoregressive / flow-matching TTS landscape
─────────────────────────────────────────────────────────────────────

Current generation of autoregressive / flow-matching TTS models (including Qwen3-TTS,
OmniVoice, Pocket TTS) share common constraints:

- Prosody emerges from:
  - Reference audio (dominant factor)
  - Instruction prompts (soft, unreliable control)
  - Acoustic codebooks that entangle identity, prosody, language, and emotion
- No standardized, modular "prosody knobs" exist.
- Changes to energy, pace, or emotion typically shift other dimensions:
  - Increasing energy may shift accent, timbre, or perceived identity.
- Flow-matching decoders (e.g. Qwen3-TTS-25Hz) focus on reconstruction quality, not on
  exposing fine-grained prosody controls.
- "Style transfer" without identity drift is not yet reliable.

─────────────────────────────────────────────────────────────────────
6. Our "prosody presets" idea: what is realistic?
─────────────────────────────────────────────────────────────────────

By "presets," we mean named configurations (e.g. "calm/natural", "energetic/broadcast",
"tight/assistant", "soft/intimate") selectable by users without deep tuning.

Pure numeric knobs (e.g. energy=0.8, intimacy=0.5) are unrealistic:
- No model in our stack exposes these dimensions independently.
- Any mapping would be brittle and model-specific.
- Guaranteed instruction-based toggles are also unrealistic; even VoiceDesign's control is
  probabilistic and cannot be relied on as a stable API.

Realistic approaches:

(A) Style-tuned reference libraries:
- Pre-generate style-tuned reference clips using VoiceDesign or OmniVoice:
  - "calm professional", "energetic broadcaster", "tight assistant", etc.
- Use OmniVoice accent labels and speed/duration parameters to create
  accent-varied and pacing-varied references (e.g. Australian accent + slow pace).
- At runtime, select the desired reference; this is the only reliable way to get
  materially different energy or style.

(B) Controlled accent/speed via OmniVoice:
- For composite targets like "Aussie calm professional":
  - Use OmniVoice: "female, young adult, australian accent" + slower speed / longer duration.
  - Use Qwen3-TTS VoiceDesign with instruct prompts for energy, pacing, role
    ("calm professional") — not a strict accent knob, but useful for style.
- Record short clips from those generated outputs.
- Use them as reference audio in Pocket TTS / Qwen3-TTS Base / OmniVoice for stable,
  style-tuned voices.

(C) Fixed instruction templates:
- Define stable VoiceDesign prompts for each desired style.
- Use them to generate references offline.
- Validate each style empirically; require listening tests.

─────────────────────────────────────────────────────────────────────
7. How we might manipulate a voice in our stack (concrete)
─────────────────────────────────────────────────────────────────────

7.1 Doable now (no model changes, implementation only)

1. Style-tuned reference library via VoiceDesign

   - For each "designed" voice, generate 4–6 reference variants using VoiceDesign with
     style-specific instructions:
       - "warm and calm storyteller"
       - "confident and energetic broadcaster"
       - "tight and professional assistant"
       - "soft and intimate"
       - (optional) "authoritative and urgent"
   - Store them under the same conceptual voice:
       - "Voice A — calm", "Voice A — energetic", etc.
   - At generation time, select the desired variant.
   - No model or runtime changes needed; leverages existing VoiceDesign and cloning.
   - This is the single most effective way to provide "prosody presets."

2. OmniVoice accents + speed/duration presets

   - Use OmniVoice to generate:
     - Accent-specific references (Aussie, British, Indian, etc.)
     - Speed-tuned references:
       - speed=1.1–1.3 → "fast/energetic" variant
       - speed=0.7–0.9 → "slow/calm" variant
     - Duration-tuned references:
       - Longer duration → "calm/slow" prosodic style
       - Shorter duration → "energetic/compact" style
   - Feed these into Base or Pocket TTS as reference audio.
   - Only requires frontend UX changes; backend logic already exists.

3. Pocket TTS as pure cloning engine + built-in voices

   - Treat Pocket TTS as a fast inference layer for pre-styled references.
   - Generate references using Qwen3-TTS / OmniVoice; clone into Pocket TTS for
     low-latency serving.
   - Expose a safe subset of its built-in voices (VCTK/Common Voice-safe) via a
     speak tab dropdown using get_state_for_audio_prompt.

4. Global "tight/expressive" tuning via temperature

   - Expose a runtime "style" field (enum or slider):
       - Conservative: temp ≈ 0.3–0.4
       - Normal: temp ≈ 0.7
       - Expressive: temp ≈ 1.0–1.2
   - Affects all models uniformly as a "feel" knob.
   - Implement as per-request param in /generate or /v1/audio/speech.

7.2 Needs non-trivial work

5. Per-request instruction control

   - Integrate Qwen3-TTS ChatML-style instruct prompts so users can say
     "speak more energetically" or "be calmer."
   - Challenges:
       - Behavior is probabilistic and content-dependent.
       - Style changes may affect identity; must monitor for drift.
       - Requires evaluation across many prompts and references.
       - Must validate: identity preserved, prosody shifts as intended, no accent drift.
   - This would be the closest thing to a "per-utterance style modulator" but is not
     guaranteed to be stable.

6. Multi-model architecture

   - Run Pocket TTS and Qwen3-TTS in a coordinated way:
     - Different endpoints, shared speak tab.
     - Pocket TTS for low-latency inference and built-in voices.
     - Qwen3-TTS for advanced cloning and VoiceDesign.
   - Must manage memory: running both in the same process is risky on constrained hosts.

7.3 Not realistically doable (with current models)

- Stable numeric knobs (energy, intimacy, urgency, clarity) with predictable, independent
  effects.
- Perfect style transfer without any identity change.
- Guaranteed "same voice but just X% more energetic" across arbitrary texts.
- Guaranteed "calm vs energetic" behavior across arbitrary scripts using only text instructions.
- Fine speed control on Base or Pocket TTS beyond what's achievable via reference audio.

─────────────────────────────────────────────────────────────────────
8. Next steps
─────────────────────────────────────────────────────────────────────

- Define 4–6 recommended "styles" as:
  - Fixed VoiceDesign instruction templates for each.
  - Concrete reference-audio generation flows (which model, which parameters).
- Build a small library of exemplar references for each style.
- Validate on:
  - Consistency across segments (no drift).
  - Preservation of identity (style changes don't morph the voice).
  - Acceptable latency and memory.
- Select a safe subset of Pocket TTS built-in voices (alba, vera, etc.) for the speak tab.
- Document approved styles as first-class options in our system, with clear expectations:
  - These are "pre-styled references", not independent knobs.

(End of file)
