# Persona Forge — App Roadmap & Backlog

Date: 2026-07-09
Status: Proposed backlog. Sequenced to run **after** the
`feature/voice-style-foundation` branch (`docs/plans/20260709-voice_style_foundation.md`)
lands. This doc is the single home for cross-cutting product ideas — audio and
non-audio — so nothing gets lost while the voice-style work is in flight.

This is a **menu, not a commitment.** Items are prioritized and scoped so any
one can be picked up independently. Effort is a rough T-shirt size, not a
promise.

---

## Guiding constraints (apply to every item)

These are the invariants the whole app already lives under; every roadmap item
must respect them (see `AGENTS.md`, `docs/agent-reference/RUNTIME_AND_MEMORY.md`):

- **One model resident at a time.** dockermisc1 runs `LOW_RAM_MODE=1`, one
  gunicorn worker (`-w 1 -k gthread`), and swaps backends (OpenVINO / PyTorch /
  Pocket TTS / VoiceDesign / OmniVoice). Do not add anything that forces two
  large models resident together.
- **Memory headroom is scarce.** Live serving already runs a few GiB over the M9
  floor. Any new persistence/state must be lightweight (SQLite / JSON on disk,
  not in-RAM caches).
- **Single-worker queue.** Generation, VoiceDesign, and OmniVoice all serialize
  through `model.executor`. New long operations must go through the same job
  queue with progress + cancel, not block the request thread.
- **UI honesty + dual-audience UX** (from the voice-style plan) apply app-wide:
  label the real mechanism, progressive disclosure, tooltip every jargon term,
  keyboard + screen-reader operable, shared design tokens/components.

---

## Priority legend

- **P0** — highest leverage; do first after the current branch.
- **P1** — strong value; schedule soon.
- **P2** — polish / nice-to-have / longer horizon.

---

## Theme 1 — Persistence & project layer  (P0)

Today generation is ephemeral: render, download, gone. Adding durable state is
the single biggest step toward a "real app" feel.

- **Generation history / recents (P0, M).** Persist every render with text,
  voice/variant, seed, generation params, backend, output metrics, and the audio
  (or a path to it). Enables replay, re-download, and **"regenerate with same
  settings."** Store in SQLite on disk; cap retention (N most recent or a size
  budget) to protect the memory/disk footprint.
- **Projects / scripts (P1, L).** Group a body of text + its takes (a podcast
  episode, an audiobook chapter, a set of UI prompts). Feeds Stitch Studio and
  long-form mode directly.
- **Output profiles (P1, S).** Named export presets combining format + loudness
  target + polish preset (e.g. "Broadcast MP3 @ -16 LUFS"). One-click consistent
  exports.
- **Favorites / tags / search (P2, S).** Across voices, variants, and history.

---

## Theme 2 — Real-usage generation features  (P0)

The things that bite the moment someone does actual production work.

- **Pronunciation lexicon (P0, M).** Per-user dictionary for names, brands,
  acronyms — phoneme or "sounds-like" respelling. For any narration workload
  this is the #1 quality lever, and the app has none today. Make it
  **accent-aware** (see Theme 3): a lexical entry can be scoped to an accent, and
  the accent "lexical tells" become a starter vocabulary.
  - Applies at generation time (text normalization pre-pass) for backends that
    accept normalized text; document which backends honor it.
- **Long-form / document mode (P1, L).** Paste a long script; auto-chunk by
  sentence/paragraph, generate per chunk, stitch, and **retry a single bad
  chunk** without re-rendering the whole thing. Machinery mostly exists
  (OmniVoice sentence segmentation + `audio_post.stitch_segments`); this is the
  orchestration + UI around it. Must run through the job queue with per-chunk
  progress.
- **Best-take gallery (P1, M).** Generate N seeds/candidates at once, audition,
  keep the best. Generalize OmniVoice's existing candidate concept to the Speak
  surface. Respect single-worker serialization (queue the N takes).
- **Regenerate one line (P1, M).** Re-render a single sentence inside a finished
  long output and splice it back. Pairs with the Stitch region-editing already
  planned in the voice-style branch.
- **Text markup / SSML-lite (P2, M).** Where a backend supports it, allow
  emphasis / pause hints in the text. Gated on real backend support — do not fake
  it (Pocket has no pause tags today; be honest per backend).

---

## Theme 3 — Accent Workbench: a first-class voice-design aid  (P0)

**Vision:** promote the accent feature system from a buried OmniVoice helper into
a **first-class surface that actively drives voice design.** Today the knowledge
lives in code comments and a hint panel; it should be a workbench where a user
*learns what an accent is made of, chooses the features they want to hit,
assembles a hero reference that provably covers them, auditions it, and saves it
as a voice variant* — all in one guided flow. This is the connective tissue of
the whole voice-design pipeline (VoiceDesign / OmniVoice → reference variant →
clone), and it serves both audiences: the beginner is taught "what makes an
Australian voice sound Australian and how to get one," while the expert targets
specific lexical-set features directly.

The infrastructure to build on is **already strong** — `frontend/src/lib/accentBank.ts`
has a Wells' lexical-set taxonomy (`AccentFeature`: GOAT, FACE, MOUTH_PRICE,
BATH_TRAP, RHOTICITY, NURSE, INTONATION, LEXICAL_TELL), plain-language
`FEATURE_INFO` descriptions, per-sentence feature tagging (`ShowcaseSentence`),
and a feature-diverse `buildHeroTake`. The gaps: this knowledge is
**under-surfaced in the UI, under-populated beyond Australian, and not framed as
a product surface of its own.** This theme closes all three. It is also the
audio-side of the pronunciation-lexicon idea (Theme 2).

**Make it a real surface.** Give it a dedicated home (an "Accent Workbench" tab
or a first-class panel inside the voice-design flow) rather than a chip strip
inside OmniVoice. It should be reachable when designing *any* accented voice, and
its output (a hero reference + its feature coverage) flows straight into the
voice-variant model from the voice-style-foundation plan. Consider moving the
accent bank + taxonomy to a shared, possibly server-backed source of truth so it
can inform generation, metrics, and docs — not just one React panel.

### 3a. Surface what already exists (P0, M) — no new data needed

- **"Accent DNA" panel.** For the selected accent, show its feature chips
  (GOAT/FACE/RHOTICITY/…), each expandable to its `FEATURE_INFO` description in
  plain language. Turn the taxonomy we already wrote into a visible, teachable
  panel instead of code comments.
- **Hero-take coverage map.** When `buildHeroTake` assembles a reference, show a
  checklist of which of the 8 features the take covers and which it misses
  ("This take doesn't exercise RHOTICITY — add a sentence"). Makes the greedy
  assembly transparent and gives beginners a reason for each sentence.
- **Per-sentence "why" hint.** Each showcase sentence already carries a `note`
  and `features[]`; render them inline (e.g. hover: "GOAT vowel in
  going/home/show + the 'mate' lexical tell") so the user learns as they pick.

### 3b. Per-accent profiles (P1, M) — small schema addition

Extend `AccentBankEntry` with a structured `profile`:

```ts
interface AccentProfile {
  summary: string            // what makes this accent, in one or two plain sentences
  strongestTells: AccentFeature[]  // ranked — e.g. AU: [RHOTICITY, FACE, MOUTH_PRICE] before GOAT
  contrastsWith: { accentId: string; note: string }[] // e.g. vs GB: "MOUTH/PRICE + lexical tells matter more than GOAT"
  pitfalls?: string          // where the model tends to drift for this accent (empirical)
}
```

Much of this content already exists as comments in `accentBank.ts` (e.g. the
AU-vs-GB note that MOUTH/PRICE + lexical tells beat GOAT) — promote it from
comments to structured, displayed data. Surface it as an info drawer per accent.

### 3c. Per-feature audio A/B (P2, M) — needs curated audio

Once real preview audio is committed (the pending curation pass —
`previewAudioUrl` is null by design until human-listened), let users hear a
minimal contrast for a feature (e.g. "today" in AU vs General American) so the
abstract description becomes audible. Directly serves the dual-audience UX
mandate (teach the beginner, respect the expert).

### 3d. Expand accents — engine reality, and how to be dynamic anyway (P1, L)

This is the big content lift, and it hinges on a hard engine constraint that
must shape the whole design.

#### What the engines can actually do (verified 2026-07-09)

- **OmniVoice is the only native accent lever in this app.** Its `instruct`
  accent vocabulary is a **closed 10-item English list** (verified against
  `k2-fsa/OmniVoice/docs/voice-design.md`): `american`, `british`, `australian`,
  `canadian`, `indian`, `chinese`, `korean`, `japanese`, `portuguese`,
  `russian` — "only effective when the synthesis text is in English." Plus 12
  Chinese **dialects** (河南话, 陕西话, 四川话, 贵州话, 云南话, 桂林话, 济南话,
  石家庄话, 甘肃话, 宁夏话, 青岛话, 东北话) that only apply to Chinese text (this
  app doesn't offer Chinese generation yet). The app's `ACCENTS` list already
  matches the 10 English options exactly.
- **OmniVoice accent is unreliable single-shot.** The docs warn "some attribute
  combinations may not work well — the model may ignore certain attributes," and
  the repo's own `voicedesign-accent-investigation` reached the same conclusion.
  The mitigation already in use is **per-segment generation with candidates**,
  not one long instruct call.
- **Qwen3-TTS has no reliable accent control.** Base is not
  instruction-controllable in this repo, and VoiceDesign's free-text description
  cannot dependably produce AU/regional English accents from text (see
  `voicedesign-accent-investigation`). Do **not** offer Qwen accent chips.
- **Therefore: OmniVoice's 10 accents are the ceiling for *generated* accent.**
  Scottish, Irish, Welsh, NZ, South African, Southern/regional US, etc. **cannot
  be produced by instruct at all.**

#### The strategy: decouple accent *definition* from accent *production*

This is what makes the Accent Workbench "dynamic and flexible" despite a
10-item engine ceiling. Split the system into two layers:

1. **Definition layer (engine-agnostic, unlimited).** The lexical-set taxonomy,
   `AccentProfile`, feature-tagged showcase sentences, and coverage map describe
   *any* accent — including ones no engine can synthesize. This layer is pure
   knowledge + hero-script authoring, and it works for Scottish or Boston or NZ
   exactly as well as for Australian. It is the flexible part.
2. **Production layer (engine-bound, swappable).** How the hero reference audio
   for that accent actually gets *made*. Route by what's possible:
   - **Route A — OmniVoice instruct** for the 10 supported accents: generate the
     hero take per-segment with candidates, guided by the definition layer's
     feature-covering sentences. Most reliable path for those 10.
   - **Route B — reference clone** for everything else (and for higher fidelity
     on the 10): obtain a hero reference clip *in the target accent* from any
     source — a licensed/consented real sample, a user upload, or a
     `kyutai/tts-voices` `hf://` voice that already carries the accent (e.g.
     `vera` for female Aussie) — then clone it with Base or Pocket. **The accent
     comes from the reference audio, not from instruct.** The Workbench's job
     here is to (a) tell the user which lexical features a good reference must
     exercise and (b) verify (via `analyze_reference` + the coverage map / ASR)
     that a candidate reference actually exposes them.
   - **Route C — honest "unsupported via generation" state:** when an accent has
     no instruct support and no reference on hand, the Workbench says so and
     guides the user to supply/clone a reference (Route B) rather than pretending
     a chip will do it.

   Store the chosen route on each accent entry so the UI shows *how* an accent is
   produced, never implying instruct can do more than 10.

#### Data & taxonomy work

- Each accent entry (any route) needs: an optional `instruct` string (Route A
  only), feature-tagged showcase sentences, an `AccentProfile`, a `productionRoute`
  (`omnivoice_instruct` | `reference_clone` | `unsupported`), and eventually
  human-curated preview audio.
- Grow `AccentFeature` only as real accents demand finer distinctions — likely
  additions for non-AU/GB accents: KIT/DRESS/START/THOUGHT vowels,
  TH-fronting/stopping, L-vocalization, yod-dropping, T-flapping/glottalization,
  the cot–caught merger. Keep the enum minimal until a target accent needs a
  split, and add a one-sentence `FEATURE_INFO` description for each new value.
- **Curation discipline:** per the locked decision, preview audio is
  repo-committed and human-picked, not build-time generated. Budget listening
  time; don't ship placeholder audio.
- Suggested expansion order: finish the **10 OmniVoice-supported** accents first
  (Route A, best ROI), then add high-demand **reference-clone** accents (Route B)
  starting with ones you can source clean references for.

### 3f. Pocket-TTS hero-clip design — spacing & prosody are the product (P1, M)

Pocket TTS is fast, lightweight, and near-zero CPU, which makes it the ideal
*production* engine — but it **faithfully inherits the reference's spacing,
pauses, energy, and prosody**, so for Pocket the hero clip *is* the deliverable.
The Accent Workbench must be able to produce Pocket-optimized hero references:

- **Design the clip for the target delivery, not just the accent.** Pause
  structure and rhythm in the reference reproduce in every future generation —
  so a hero clip must embody the exact pacing/prosody you want (calm vs tight,
  deliberate vs conversational), authored, not accidental.
- **Prefer clean single-take delivery** for Pocket references. Stitched clips
  with inconsistent ambience/energy transfer that inconsistency into the clone
  (the `audio_post.stitch_segments` internal-dynamics problem). If stitching is
  unavoidable, normalize per-segment loudness and match room tone first.
- **Best pipeline: OmniVoice authors, Pocket produces.** Use OmniVoice (which can
  do the accent + `speed`/`durations` prosody control) to generate a
  feature-covering, prosody-controlled hero take, save it as a hero **reference
  variant** (voice-style-foundation plan), then let **Pocket clone it** for fast
  production. This chains Workflow B → Workflow D from the voice-style plan and
  gives you accent + intended delivery at Pocket's speed.
- **Workbench affordances for Pocket:** target 10–15s hero length (already the
  `HERO_TARGET` window), surface the pause map + feature-coverage map so the user
  can see both prosody and accent coverage before committing, and expose the
  `speed`/`durations` controls when the hero is OmniVoice-authored so spacing is
  deliberate. Verify the saved reference's `analyze_reference` metrics (pause
  ratio, median pause, words/sec) match the intended delivery before it becomes a
  Pocket clone source.

### 3e. Cross-link to the lexicon (P1, S)

The `LEXICAL_TELL` words ("arvo", "togs", "mate") already *are* a per-accent
vocabulary. Expose them as a per-accent word list, and let the pronunciation
lexicon (Theme 2) import/scope entries by accent. One idea feeds the other.

---

## Theme 4 — Integration & API hardening  (P1, security-relevant)

`/v1/audio/speech` is consumed by hermes-agent over the network, and there's an
`IntegrationsPage`, but the endpoints are currently open.

- **AuthN + rate limiting + input caps (P0 if network-exposed, M).** No API key,
  no rate limit, and the **mutating `/runtime/config` route has no auth gate**
  (deliberate historically, but a real exposure if reachable beyond localhost).
  Add an API-key gate on generation + config routes, per-key rate limiting, and a
  request/text size cap. Treat as P0 the moment the service is reachable off-box.
- **In-app API docs (P1, S).** OpenAPI/Swagger on the Integrations page with
  copy-paste `curl` / Python / OpenAI-SDK snippets. Makes the OpenAI-compatible
  endpoint self-serve.
- **OpenAI-route completeness (P1, S).** Confirm/extend `response_format`
  (mp3/opus/flac/wav) and `speed` passthrough; expose per-key usage counts.
- **Streaming for in-UI playback (P2, M).** Progressive playback of long
  generations in the browser (distinct from the network streaming path that has
  no external consumer — see the `hermes-tts-consumer` note; don't rebuild that).

---

## Theme 5 — Observability & ops  (P1, ties to known RAM pain)

The app already measures `_process_rss_mib()` in `model.py` but never shows it.

- **Status dashboard (P1, M).** Active backend, model loaded/idle-unloaded state,
  live RSS vs. the M9 floor, queue depth, rolling RTF, recent errors. Directly
  serves the one-model / LOW_RAM reality you operate the box under.
- **Actionable error surfacing (P1, S).** OOM and model-load failures should say
  what happened and the next step, not surface a stack trace.
- **Diagnostics bundle (P2, S).** One-click export of recent logs + config +
  timings for debugging on dockermisc1 without SSH spelunking.
- **Model warm/cold indicator + preload button (P2, S).** Make the JIT/warm-cache
  behavior visible (see `ov-jit-cache-behavior`) so a cold first-run isn't
  mistaken for a hang.

---

## Theme 6 — App-wide UX polish  (P1/P2)

- **Command palette (⌘K) (P1, M).** Jump to any voice/page/action. High
  power-user payoff, near-zero risk.
- **Job-complete notifications (P1, S).** In-app toast + optional browser
  notification when a long generation finishes, so the user isn't babysitting the
  tab.
- **Persistent preferences (P1, S).** Remember last-used voice/preset/backend,
  density/Pro-mode, theme.
- **Onboarding / first-run tour (P2, M).** Especially for the dual-audience goal
  — teach the beginner the happy path once.
- **Responsive / mobile pass (P2, M).** Most pages assume desktop.
- **Design tokens + shared component library (P1, M).** The cohesion spine from
  the voice-style plan's dual-audience section — do it once, app-wide, so every
  page reads as one 2026 app.

---

## Theme 7 — Trust, safety & provenance  (P2)

- **Provenance metadata on exports (P2, S).** Embed model/voice/timestamp (and
  optionally a C2PA-style manifest) in exported audio. A 2026 "enterprise-ready"
  signal for AI-generated voice; cheap to attach.
- **Optional inaudible watermark (P2, M).** For traceability of generated audio.
- **Content length / abuse caps (P1, S).** Pairs with API rate limiting; protects
  the single-worker queue from a runaway request.

---

## Suggested sequencing (after the voice-style branch)

1. **Generation history** (Theme 1) + **pronunciation lexicon** (Theme 2) — the
   two biggest everyday-usefulness multipliers.
2. **Auth + rate limit + input caps** (Theme 4) — closes a real exposure; do
   immediately if the service is network-reachable.
3. **Accent DNA surfacing** (Theme 3a) — high value, no new data, reuses what's
   already built.
4. **Status dashboard** (Theme 5) + **design tokens/shared components** (Theme 6)
   — operational safety + cohesion.
5. **Long-form mode, best-take gallery, accent expansion** — the larger content/
   feature lifts, once the foundation above is in place.

---

## Explicitly out of scope / handle with care

- **Two large models resident at once** — never; it breaks the LOW_RAM/one-model
  invariant.
- **Rebuilding the network streaming path for an external consumer** — there is
  no consumer for it (see `hermes-tts-consumer`); in-UI progressive playback is a
  different, allowed thing.
- **Heavy in-RAM caches** for history/projects — use on-disk storage.
- **Offering accents OmniVoice's closed instruct vocabulary can't actually do** —
  be honest; route to VoiceDesign or mark unsupported.
- **Build-time-generated placeholder accent preview audio** — the locked decision
  is human-curated, repo-committed audio only.
