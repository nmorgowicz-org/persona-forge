# Voice Lifecycle, Library Architecture & Diagnostics — Implementation Plan

Date: 2026-07-14
Status: Approved direction, not yet implemented
Branch: `feature/voice-style-foundation`

## How to use this document

This document is self-contained. It captures a set of product/UX decisions made in a
planning conversation on 2026-07-14, plus enough file/function-level detail that a
fresh engineer or agent with zero prior context can pick up any single numbered
section and implement it without needing to re-derive the reasoning. Sections are
mostly independent of each other and can be built/shipped in any order except where
a dependency is called out explicitly.

Related: `docs/plans/20260709-app_roadmap_backlog.md` §4.3 (segment feature tagging,
summarized in full here too) and §8 (Waveform & Audio-Editing UX, superseded/extended
by §1 below).

---

## 1. Waveform: retire the simple two-lane preview deck

**Decision**: Always render `AlignmentCompare` in place of the simple two-lane
preview deck. Do not build a second migration path that teaches the simple deck to
reuse `WaveformLane`/`TimeRuler` — just stop using the simple deck.

### Current state
- `frontend/src/pages/VoiceLibraryPage.tsx` has a `previewAudio` block (~line 1145
  in earlier reads of this file, subject to drift — search for `previewAudio` and the
  `opacity-40 grayscale` ORIGINAL block) that renders two independent, non-time-aligned
  waveform lanes for quick before/after listening.
- Separately, `frontend/src/components/waveform/AlignmentCompare.tsx` already
  implements a full shared-axis A/B compare view: `WaveformLane` canvases on a common
  `TimeRuler`, boundary/`RegionEditor` markers, word-text labels from
  `alignBoundaries`, hover readouts, a transport bar with drag-to-loop scrubbing, and
  repeat/close controls (all confirmed already built and committed, per
  `docs/plans/20260709-app_roadmap_backlog.md` §8 and the `majestic-growing-owl` plan
  which is fully merged).
- Today `AlignmentCompare` is only shown when there is an active alignment plan
  (Precise-mode prosody adjustment in progress). The simple deck is what's shown the
  rest of the time (plain preview/playback with no plan data), which is why the user
  called it "terrible ui/ux" — two different waveform experiences depending on
  context, with the simpler one being visually worse.

### Implementation path
1. In `VoiceLibraryPage.tsx`, replace the `previewAudio` simple-deck JSX block with a
   render of `AlignmentCompare`, always, whenever there is audio to preview (original
   voice audio, a prosody variant, a stitched result, etc.) — not just when a
   Precise-mode alignment plan exists.
2. `AlignmentCompare` needs to gracefully handle the "no plan" case: when
   `alignBoundaries`/`previewAudio.plan` are empty or absent, it should render just
   the two audio lanes on the shared time axis (still valuable — legible original vs.
   adjusted comparison) with the `RegionEditor` boundary-marker overlay and
   word-label layer simply not rendered (empty array in, no markers out — this
   should already be closer to a no-op than a new code path, since the overlay logic
   already maps over a boundary list).
3. Where only a single audio source exists (no "adjusted"/"variant" counterpart to
   compare against — e.g. previewing a freshly-uploaded reference before any edits),
   render `AlignmentCompare` with a single lane rather than two, or pass the same
   audio as both lanes — confirm actual behavior needed by testing the "upload new
   reference, preview immediately" flow once implemented, since this edge case wasn't
   explicitly discussed and needs the smallest reasonable adaptation of
   `AlignmentCompare` rather than a parallel single-lane component.
4. Delete the simple two-lane deck's now-dead JSX/state (opacity-40/grayscale
   original block, its own play/pause state if independent from `AlignmentCompare`'s)
   once `AlignmentCompare` fully replaces it — do not leave both code paths around
   "just in case."

### Verification
- `npm run build` in `frontend/`.
- Manually preview: (a) a plain reference voice with no edits, (b) a voice with an
  active Precise-mode alignment plan, (c) a prosody variant, (d) a freshly stitched
  OmniVoice result. Confirm a single consistent waveform UI renders in all four
  cases, with boundary markers/word labels appearing only when plan data exists.

---

## 2. Prosody variant lifecycle, API defaults, and the mounted-reference-voice UX

This is the largest section. It covers four things that are tightly related in the
UI (they all live around the "PROSODY VARIANTS" pill and the voice-card "..." menu in
`VoiceLibraryPage.tsx`) but can be implemented as separate, sequenced changes.

### 2.0 Background / existing mechanics (read this first)

**Filesystem model** (`src/qwen3_tts/voice_library.py`): no database. Each voice is a
directory `VOICE_LIBRARY_DIR / <voice_id> / {original.wav, current.wav, meta.json,
.history/}`. `voice_id` format is `vd_<12-hex>` (`_VOICE_ID_RE`).

**`current.wav` is the single resolution point.** `get_voice()` resolves
`current.wav → original.wav → legacy reference.wav`. This is what every consumer —
API generation, the UI preview, everything — actually reads. This is also therefore
the natural lever for "promote a variant to be what generation actually uses."

**Variants already exist and are already switchable.** `create_prosody_variant()`
writes a new `prosody_*.wav` file into the voice dir. `set_active_variant(voice_id,
variant_filename)` (in `voice_library.py`, already implemented) swaps the
`current.wav` symlink to point at a chosen `prosody_*.wav`, or back to `original.wav`
when `variant_filename=None`. The frontend "PROSODY VARIANTS" pill is already
clickable and already calls this via `setActiveVoiceVariant` in
`frontend/src/lib/api.ts`. `GET /voices/<voice_id>/variants` (app.py) lists the
`prosody_*.wav` files and resolves which one is active by reading the `current.wav`
symlink target.

**Bug: cache invalidation is missing on variant activation.** `app.py` has a helper
`_invalidate_voice_clone_state(voice_id)` that calls both
`model.invalidate_voice_clone_prompt(voice_id)` and
`pocket_tts_runtime.invalidate_voice_state(voice_id)`. It is called from
`voices_undo_reference_edit`, `voices_delete`, and other mutation endpoints — **but
not from `voices_set_active_variant`** (the endpoint backing
`POST /voices/<voice_id>/set-active-variant`). This means swapping which variant is
"active" today can silently keep serving/cloning from the previously-cached voice
state until something else happens to invalidate it. **This must be fixed as part of
any variant-promotion feature**: add the `_invalidate_voice_clone_state(voice_id)`
call to `voices_set_active_variant` in `app.py` (~line 575), matching the pattern
used by the other four mutation endpoints.

**Single global API default already exists and is the confirmed target model.**
`ACTIVE_DEFAULT_FILE = VOICE_LIBRARY_DIR / ".active_default"` persists exactly one
`voice_id` (`get_active_default_voice_id()` / `set_default_voice_state_from_library()`
in `pocket_tts_runtime.py`). `build_default_voice_state()` runs at boot and prefers
this persisted default over the raw `REF_AUDIO_PATH` env var if set.
`voices_activate` (`POST /voices/<voice_id>/activate`, app.py ~line 612) is the
existing endpoint that sets this — it requires `TTS_BACKEND == pocket_tts` and calls
`set_default_voice_state_from_library` on `model.executor` (avoiding races with an
in-flight generation).

User confirmation (explicit, do not revisit without new input): **one single global
default voice is sufficient** for requests that omit `voice_id` — their primary use
case is a Hermes agent hitting the plain OpenAI-compatible endpoint with no extra
params, so this single-default path is exactly right and does not need to become a
multi-default or profile-based system.

**What the user does want improved: explicit-`voice_id` request handling.** The app
already has fast runtime-reload capability for cloning (it can load/rebuild a voice
state for an arbitrary `voice_id` on the fly — see `get_pocket_tts_voice_state()` in
`pocket_tts_runtime.py`, whose resolution chain is: (1) no `voice_id` →
`default_voice_state`; (2) in-memory `pocket_tts_voice_state_cache` dict keyed by
`voice_id`; (3) on-disk `.safetensors` cache with an mtime-based staleness check
against `wav_path`/`meta.json`; (4) built-in preset or `hf://` path; (5) library
lookup via `voice_library.get_voice`). The user wants this path to be *reliable* when
an API consumer passes an explicit `voice_id` — i.e., no new "multiple named
defaults" feature, just make sure the existing per-request `voice_id` resolution +
cache correctly picks up variant promotions and reference edits without stale-cache
surprises. Concretely this means:
- The cache-invalidation fix above (2.0) is the main correctness fix needed here —
  once `set_active_variant` invalidates state properly, an explicit-`voice_id`
  request immediately picks up the newly-promoted variant on its next call (existing
  on-disk/in-memory cache staleness logic already handles the rest via mtime checks).
- Audit other mutation paths that change what `current.wav` points at (variant
  promotion, reference edits, undo) to confirm each one triggers the same
  invalidation helper — `voices_undo_reference_edit` and `voices_delete` already do;
  `voices_set_active_variant` is the one gap identified so far. Re-check
  `apply_reference_edits`/`normalize_reference`/`trim_reference_silence`/
  `adjust_reference_pauses` call sites in `app.py` for the same gap while doing this
  audit, since they all mutate `original.wav` via `_rewrite_reference_wav()`.

### 2.1 "Promote variant to API reference" — answering the user's direct question

> "if we promote the variant to be the main api reference voice, how does that look?
> if we want to have options to specify a voice id that the api can use to swap, how
> does that work with variants?"

**Answer / design**: Variants never get their own `voice_id`. A variant is promoted
by making it the thing `current.wav` points to *within the same voice_id* — this is
exactly what `set_active_variant()` already does. So:
- "Promote this variant to be used for the API" = call
  `set_active_variant(voice_id, variant_filename)` (making it `current.wav` for that
  voice_id) **and**, if this voice_id is also the persisted global default
  (`get_active_default_voice_id() == voice_id`), the existing default-voice-state
  cache should also be rebuilt/invalidated so the global default path picks up the
  change immediately — same underlying fix as 2.0.
- An API consumer specifying an explicit `voice_id` always transparently gets
  whichever variant is currently "active" for that `voice_id`, because `get_voice()`
  always resolves through `current.wav`. There is no separate "variant id" the API
  needs to know about — this is the point of the resolution-chain design and requires
  no new API surface. The only technical debt was the missing cache invalidation
  (2.0), not a missing capability.
- New UI action needed: a "Promote to API reference" button per variant (in addition
  to the existing implicit "click the pill to set active" interaction) that makes the
  promotion explicit and, when the voice is also the global default, shows a
  confirmation ("This will change what the live API default sounds like immediately").
  This satisfies the user's ask to make variant-promotion "simple" and first-class
  rather than "buried in that prosody variant section."

### 2.2 Making variants first-class (not buried) + repurposing "Duplicate voice"

**Current state**: the voice-card "..." menu already has a "Duplicate voice" /
"clone voice" action, but the user correctly identifies it as currently useless — it
just makes a second identical `voice_id`, which provides no lifecycle value once
variants are properly supported (a variant already covers "I want another version of
this voice's audio without losing the original").

**Decision (user-confirmed)**: repurpose this action into **"Fork to independent
voice_id"** — i.e., take the *currently active variant* (or a specifically chosen
one) of a voice and materialize it as a brand-new, independent `voice_id` with its own
lifecycle, history, and (if applicable) its own eligibility to be set as the API
default or referenced directly by API consumers who want a stable, separately-
addressable identity. This is the "escape hatch" for when a variant has proven itself
and the user wants it to graduate out of being "just an option under the original
voice" into its own first-class voice.

Implementation:
- `voice_library.py` already has `duplicate_voice()` (read in full in the prior
  session) — audit it to confirm it duplicates `original.wav`/`current.wav` faithfully;
  if it currently only duplicates `original.wav` and ignores which variant is active,
  it needs to duplicate from the *resolved* `current.wav` target (i.e., the actual
  currently-active audio, whether that's `original.wav` or a `prosody_*.wav`) so that
  forking a variant produces a new voice whose `original.wav`/`current.wav` reflect
  that variant's audio, not the pre-variant original.
- Rename the action/button label from "Duplicate voice" to "Fork to independent
  voice_id" in `VoiceLibraryPage.tsx`, and update its icon/description text to
  reflect the new semantics (this is a UI-first change; the underlying
  `duplicate_voice()` call may need the audit above but likely does not need a new
  endpoint).
- Add the variant-lifecycle actions per variant in the "PROSODY VARIANTS" pill /
  expanded list: **Preview**, **Promote to API reference** (2.1), **Fork to
  independent voice_id** (this section), **Delete variant**. Today only "click to
  set active" exists; Preview/Delete/Fork are net-new per-variant UI affordances.

### 2.3 Mounted reference voice lifecycle & UX

**Background**: `vd_000000000001` ("Mounted reference (Default)") is created by
`ensure_mounted_ref_voice()` in `voice_library.py`. Its `original.wav` is a
**symlink** to the actual container-mounted `REF_AUDIO_PATH` file, which is often
mounted `:ro` (read-only) by the deployment (see `dockermisc1-dev-deploy.md` memory
for the dev container's compose/bind-mount setup). `current.wav` symlinks to
`original.wav`.

**The problem**: `_rewrite_reference_wav()` — used by `normalize_reference()`,
`trim_reference_silence()`, and `apply_reference_edits()` — does
`sf.write(voice_dir / "original.wav", ...)` directly. Since `original.wav` is a
symlink to a possibly-`:ro` host file, in-place edits on the mounted reference risk
failing outright (permission denied writing through a read-only-mounted symlink
target) or behaving surprisingly (e.g. if the write follows the symlink vs. replaces
it, which differs by OS/filesystem). The user's own words: this voice "is usually
mounted in the container as `:ro` and it will usually need work on it to function
properly" (their concrete example: the LTX 2.3 reference voice needs prosody/silence-
trim work but they don't want to touch/lose the source).

**Current UI mitigation (exists but insufficient)**: `VoiceLibraryPage.tsx`'s
`VoiceCard` component has a `preserveOriginal` checkbox state ("Edit audio
operations on a copy"), used by `mutationVoiceId()`/`runMutation()`/
`openAudioEditor()` — when checked, edits route through `onDuplicate()` first. This
is optional and easy to miss, and is not specifically enforced or explained for the
mounted reference voice.

**Decision (user-confirmed)**: improve the UX to be "more flexible and have more
instructions for the user" around this specific case — do not silently force a
behavior, but make it impossible to miss and easy to do correctly. Concrete
implementation:
1. Detect when the voice being edited is the mounted reference
   (`voice_id == "vd_000000000001"`, or more robustly, check whether `original.wav`
   is a symlink pointing outside the voice library directory tree — this generalizes
   to any future mounted/read-only reference, not just the one hardcoded ID).
2. When editing (normalize/trim/pause-adjust) a voice matching that condition:
   - Default the "Edit on a copy" checkbox to **checked** rather than unchecked, and
     make it visually distinct (e.g. a small inline note: "This voice is backed by a
     mounted, read-only file — edits will be made on a new copy so the source stays
     intact") rather than a generic checkbox with no context.
   - If the user explicitly unchecks it and attempts to write in place, either (a)
     block it with an explanatory error before attempting the write (preferred —
     avoids surfacing a raw filesystem permission error), or (b) attempt the write
     and catch the resulting I/O error with a clear message pointing at the
     "edit on a copy" option, if detecting read-only-ness ahead of time proves
     unreliable across deployment environments.
3. Because this ties directly into §4 (Voice Library reorganization) — the user
   explicitly wants "mounted reference voice (or that copy) → variants" handled
   within the same hierarchical model as the standard OmniVoice → segments → stitched
   → variants flow — the copy produced by this flow should be tagged/grouped in a way
   that's discoverable as "derived from the mounted reference," not just an anonymous
   duplicate. See §4 below for the concrete metadata field.

### Verification for §2
- Unit/manual: promote a variant via the new "Promote to API reference" action on a
  non-default voice, confirm `current.wav` symlink target changes and a subsequent
  generation request with that explicit `voice_id` immediately uses the new audio
  (no stale-cache lag) — this specifically exercises the 2.0 fix.
- Manual: fork a variant to an independent `voice_id`, confirm the new voice's
  `original.wav`/`current.wav` reflect the forked variant's audio (not the pre-variant
  original), and that it can independently be set as the global API default via the
  existing `voices_activate` endpoint.
- Manual: attempt an in-place edit (normalize/trim) on the mounted reference voice
  with "edit on a copy" unchecked; confirm either a clear pre-flight block or a clear
  error message, never a raw stack trace or silent corruption/no-op.
- `PYTHONPATH=src python -m py_compile src/qwen3_tts/app.py src/qwen3_tts/voice_library.py`.

---

## 3. Segment accent-lexicon feature tagging

Full detail now lives in `docs/plans/20260709-app_roadmap_backlog.md` §4.3 (inserted
2026-07-14) — summarized here for self-containedness:

- **Option A (build now)**: persist the matched showcase-sentence's
  `features: AccentFeature[]` array (from `frontend/src/lib/accentBank.ts`) as a new
  `feature_tags` field in the segment's `meta.json`, threaded through
  `POST /omnivoice/segments` and `segment_library.save_segment()`
  (`src/qwen3_tts/segment_library.py`).
- **Option B (explicit follow-up)**: a lexical-set text classifier for arbitrary,
  free-typed sentences (not just curated showcase sentences), enabling the user's
  stated goal of "a full featured, easy to use, easy to execute accented voice design
  flow, with many options on each of the ways that sentences can hit those different
  sounds." Scope this as a distinct follow-up project once Option A's plumbing is in
  place, since the classifier's output needs the `feature_tags` field to exist first.

---

## 4. Voice Library reorganization at scale ("Accent Design Projects")

**Problem (user-quantified, not speculative)**: designing a single accent involves
4–6 segments per timbre and 4–6 segments per age grouping, multiplied across
multiple accents and the resulting stitched voices and their variants. The current
flat Voice Library + a single "Saved segments" grid section (already present in
`VoiceLibraryPage.tsx`, ~lines 1985–2040 in earlier reads — grid, search via
`segSearch`/`filteredSegments`, empty-state CTA into Voice Design/OmniVoice) does not
scale to this volume. The user was explicit that this is not a "wait and see" —
architectural work is needed now.

**Decision**: Option A — introduce a hierarchical **"Accent Design Project"**
grouping concept, covering both:
1. The typical design flow: OmniVoice → segments → stitched voice → variants.
2. Non-standard flows, explicitly required by the user: the mounted reference voice
   (or a copy/fork of it) → variants, and any other voice that didn't originate from
   an OmniVoice/segment pipeline.

### Design

- **New concept: Project.** A lightweight grouping entity — likely a directory or a
  small metadata record (`meta.json`) under a new `PROJECT_LIBRARY_DIR`, or simply a
  `project_id`/`project_name` field stamped onto existing entities (segments, voices)
  rather than a new physical storage location — the simplest implementation is
  probably the latter: add an optional `project_id` (and human-readable
  `project_name`) field to segment `meta.json` and voice `meta.json` alike, plus a
  small `projects.json` index file (or one small file per project) listing project
  name/description/created_at and the `voice_id`s/`segment_id`s currently tagged with
  it. Avoid inventing a database — stay consistent with the filesystem-backed model
  already used throughout `voice_library.py`/`segment_library.py`.
- **Standard flow tagging**: when a user starts an OmniVoice accent-design session
  (or explicitly creates a "Project" first), every segment saved during that session
  gets the session's `project_id`. When those segments are stitched into a voice
  (`/omnivoice/save` → `voice_library.save_voice()`), the resulting voice inherits the
  same `project_id`. Any variant or fork created from that voice also inherits it
  (variants live under the same `voice_id` already, so no extra propagation needed
  there; forks — §2.2 — should carry `project_id` forward explicitly since they get a
  new `voice_id`).
- **Non-standard flow tagging**: the mounted reference voice and any voice not
  created via OmniVoice (uploaded references, manually cloned voices) should still be
  assignable to a project — either automatically (e.g. a copy made via the "edit on a
  copy" flow in §2.3 inherits the source voice's `project_id` if it has one, or gets
  prompted to create/pick one) or manually via a "Move to project" action in the
  voice-card "..." menu. This satisfies the explicit requirement to handle
  "mounted reference voice (or that copy) → variants" inside the same hierarchy, not
  just the OmniVoice pipeline.
- **UI**: the Voice Library page gains a project-grouped view — collapsible sections
  per project (plus an "Ungrouped" section for anything with no `project_id`), each
  showing its voices and, nested or cross-linked, the segments that fed into it. The
  existing flat grid/search remains available as a flattened "All voices" view/filter
  for users who don't want the grouped view, rather than replacing search entirely.
- **Segments view**: the existing "Saved segments" section becomes project-scoped
  too — segments filter/group by `project_id` alongside the voices, rather than
  living in one large ungrouped list regardless of which accent-design effort they
  belong to.

### Implementation path (incremental, in order)
1. Add `project_id`/`project_name` fields to `segment_library.save_segment()` and
   `voice_library.save_voice()` (optional, default `None`/"Ungrouped" for backward
   compatibility with existing data — no migration required, just treat missing
   field as ungrouped).
2. Add a minimal project index (`projects.json` or similar) and CRUD endpoints:
   create project, list projects, rename project, assign/reassign a voice or segment
   to a project.
3. Update `/omnivoice/save`, `/omnivoice/segments` (POST), and the fork/duplicate
   paths (§2.2) to propagate `project_id` per the rules above.
4. Frontend: add a project-grouped rendering mode to `VoiceLibraryPage.tsx` for both
   the voices grid and the "Saved segments" section, plus a lightweight "create
   project" / "move to project" affordance.

### Verification
- Manual: run a full OmniVoice accent-design session inside a newly created project,
  confirm all saved segments and the final stitched voice share the same
  `project_id`.
- Manual: fork the mounted reference voice (or make an "edit on a copy" copy per
  §2.3), assign it to a project manually, confirm it displays correctly in the
  grouped view.
- Confirm voices/segments saved before this change (no `project_id` field) still
  display correctly under "Ungrouped" with no errors.

---

## 5. Post-Stitch-Studio prosody workflow

**Decision (user-confirmed, Option A only for now)**: after a successful
`/omnivoice/save` (stitch), deep-link the user directly into the Adjust Prosody
popover/flow for the newly created voice, rather than leaving them to navigate back
to the Voice Library and find it manually.

**Explicitly deferred**: live prosody preview *inside* Stitch Studio before saving
(Option B) — the user wants this deferred to a later, full UI/UX/capability pass on
Stitch Studio as a whole, not bolted on now.

### Implementation path
- In the Stitch Studio save-success handler (wherever `/omnivoice/save`'s response is
  handled client-side), after the new `voice_id` is returned, navigate to the Voice
  Library page with that voice pre-selected and the Adjust Prosody popover already
  open (reuse whatever state/props already open that popover from a normal voice-card
  click — this should not require new popover logic, just triggering the existing
  open-state programmatically on navigation/mount).

### Verification
- Manual: complete a stitch in Stitch Studio, confirm the app lands on the Voice
  Library with the new voice's Adjust Prosody popover already open, ready for
  immediate adjustment.

---

## 6. "Use in Speak" crash — root-caused to first-call-after-load; fix implemented

**Status: implemented** (2026-07-14) — a second round of container logs sharpened
the diagnosis from "unknown, needs logging" to a specific, actionable pattern, and a
mitigation + supporting diagnostics have been built. Original status/history
retained below for context; skip to "What was implemented" for the current state.

### What we know from two rounds of captured container logs
Round 1 (cold boot):
```
[pocket_tts] Loading model — language='english', temp=1.2, lsd_decode_steps=5, eos_threshold=-4.0, quantize=False, noise_clamp=None
[pocket_tts] frames_after_eos set to 4
[pocket_tts] Model loaded and ready.
[pocket_tts] Persisted active default 'vd_d69f5330ead7' has no reference.wav; ignoring.
[pocket_tts] Building default voice_state from '/voice/reference.wav'
[pocket_tts] Default voice_state built successfully.
[app_worker] Pocket TTS loaded and ready
[app_worker] Registered mounted reference as voice vd_000000000001
[generate] batch  lang='English'  chars=4  job=f13186e6c3264c58a99815b0fb9f2261
[generate] batch  lang='English'  chars=4  job=b6d42c00650442a4b2e209fb5f0dc7c4
```
Round 2 (idle-unload + reload, captured later the same day):
```
[generate] batch  lang='English'  chars=4  job=f13186e6c3264c58a99815b0fb9f2261
[generate] batch  lang='English'  chars=4  job=b6d42c00650442a4b2e209fb5f0dc7c4
[generate] batch  lang='English'  chars=38  job=fa14623749a241a4ab3946695753550e
[generate] done   elapsed=1.3s  audio=2.3s  RTF=0.57x
[generate] batch  lang='English'  chars=4  job=048b16f40bd64410a77d226e936706e5
[generate] done   elapsed=0.6s  audio=0.7s  RTF=0.78x
[app_worker] Idle timeout reached; unloading model to free RAM...
[pocket_tts] Unloading Pocket TTS model and clearing cache...
[pocket_tts] Unloaded.
[app_worker] Swapping back to Base for generation request...
[app_worker] Resolved TTS_BACKEND='pocket_tts' (profile='base', model_size=1.7B)
[pocket_tts] Loading model — language='english', ...
[pocket_tts] Model loaded and ready.
[pocket_tts] Persisted active default 'vd_d69f5330ead7' has no reference.wav; ignoring.
[pocket_tts] Building default voice_state from '/voice/reference.wav'
[pocket_tts] Default voice_state built successfully.
[app_worker] Pocket TTS loaded and ready
[app_worker] Registered mounted reference as voice vd_000000000001
[generate] batch  lang='English'  chars=18  job=1009ef4e408142fbaa921ae3d9a0cf71
```
(cuts off there — the user confirmed this request also failed.)

**The pattern across both rounds**: every observed failure is **the first
`[generate] batch` call immediately following a model (re)load** — never a
subsequent call against an already-loaded model. Round 1: the first two calls after
cold boot fail; the third succeeds, and everything after succeeds. Round 2: several
calls succeed on the already-warm model, idle-unload fires, the model reloads, and
the very next call (the first one on the reloaded model) fails again. This rules out
text length (chars=4 succeeds plenty of times elsewhere) and rules out a specific
`voice_id` (both the mounted reference and another reference voice failed on their
respective "first call") as the driver.

**Why this points at a first-inference-only cost, not a race or wrong-voice bug**:
- The generation executor is a single-worker `ThreadPoolExecutor(max_workers=1)`
  (`src/qwen3_tts/model.py:133`) — model load and every generate call are strictly
  serialized on one thread, so this is not a race between "model finished loading"
  and "first request arrived."
- `load_model()`'s pocket_tts branch (`src/qwen3_tts/model.py`, ~lines 410–460) loads
  the model and builds the *default voice_state* (`get_state_for_audio_prompt`, which
  only encodes a conditioning prompt — it does not run the model's actual generation/
  decode path), then immediately prints "Pocket TTS loaded and ready." **The real
  first forward-pass through the model only ever happens on whatever the first live
  request turns out to be.** If Pocket TTS (or its underlying torch/ONNX stack) has a
  one-time cost on its first real generation — lazy kernel/graph compilation, a
  first-run buffer/arena allocation spike — that cost lands on the first user request
  every single time the model is loaded or reloaded. In a memory-constrained
  container, a first-call allocation spike landing on top of the model's already-
  resident memory is a very plausible trigger for a native OOM kill or abort, which
  would explain the complete silence in logs: no Python exception is raised because
  the process/worker dies at a lower level than Python's `try/except` in
  `_run_generate` can catch.
- The absence of `traceback.print_exc()` output specifically (the pocket_tts branch
  of `_run_generate`, `src/qwen3_tts/model.py` ~lines 1520–1580, already wraps
  `generate_pocket_tts()` in a `try/except` that prints a traceback on any catchable
  Python exception) reinforces that this is not a normal Python-level error.

**The "Persisted active default has no reference.wav" line** (separate, secondary
issue, also present in both rounds): `ACTIVE_DEFAULT_FILE` still held
`vd_d69f5330ead7` — the user confirmed this matches a voice they deleted a day or two
prior. `build_default_voice_state()` looks this up on every load, fails to resolve
it, and silently falls back to `/voice/reference.wav` — correctly avoiding a crash,
but repeating the same silent fallback on every future load/reload forever since
nothing ever cleared the stale pointer.

### What was implemented
1. **Warm-up generation at load time** (`src/qwen3_tts/pocket_tts_runtime.py`, new
   `warm_up_pocket_tts(model, voice_state)`; wired into
   `src/qwen3_tts/model.py`'s pocket_tts branch of `load_model()`, immediately after
   `build_default_voice_state()`). Runs one throwaway generation ("Warming up.")
   against the default voice_state, synchronously, on the same serialized executor
   thread that performs the load — so whatever one-time first-call cost exists is
   paid and logged at load/reload time (`[pocket_tts] Warming up model with a
   throwaway generation...` / `[pocket_tts] Warm-up complete (Xs).`) instead of
   silently consuming a real user's first "Use in Speak" click. If cloning is
   unavailable (no voice_state to warm up with) it's a quiet no-op. If the warm-up
   generation itself fails, it's caught, logged loudly with a traceback
   (`[pocket_tts] Warm-up generation failed after Xs: ...`), and does **not** block
   boot — surfacing the failure at load time, attributable to load, is strictly more
   useful than the same failure silently eating a live request.
   - **Tradeoff to be aware of**: this adds roughly one generation's worth of latency
     to every model load and every idle-unload → reload cycle. Given loads are
     infrequent relative to requests, this was judged an acceptable cost for turning a
     silent, unattributable production failure into a visible, attributable boot-time
     one.
2. **Voice-state resolution-path logging** (`get_pocket_tts_voice_state` in
   `pocket_tts_runtime.py`): every return path now logs
   `[pocket_tts] voice_state resolution: <resolved_id> (<path>)` where `<path>` is one
   of: `default (in-memory)`, `default (rebuilt from ref_audio_path)`,
   `<voice_id> (in-memory cache)`, `<voice_id> (disk cache import)`,
   `<voice_id> (built-in preset, rebuilt)`, `<voice_id> (library, rebuilt from wav)`.
   The `[generate] batch` line itself now also includes `voice_id=...` (previously
   omitted, making it impossible to tell from logs alone which voice a given
   generate call was even for). Together these make any future recurrence
   immediately show which voice and which resolution branch was involved, rather
   than requiring inference from timing alone.
3. **Stale `ACTIVE_DEFAULT_FILE` self-heal** (`build_default_voice_state` in
   `pocket_tts_runtime.py`): when the persisted active-default `voice_id` has no
   resolvable `reference.wav`, the file is now deleted (`ACTIVE_DEFAULT_FILE.unlink
   (missing_ok=True)`) instead of being silently re-ignored on every future load. The
   log line was also reworded to say the voice was "likely deleted" and that the
   stale default is being cleared, matching what actually happened in this case.
   - **Not yet done** (noted here as a deliberate scope cut, not an oversight): no
     user-visible UI warning was added for this case — it's still only visible in
     container logs. If this recurs and a UI-level warning becomes worth the
     engineering cost, it should surface on the Voice Library page (e.g. a banner:
     "API default voice could not be loaded and was reset — please re-select a
     default").
4. **Not implemented / explicit follow-up**: process/worker-level crash detection
   (distinguishing a native OOM-kill/abort from a hung request at the process-
   supervision layer, e.g. surfacing container restart-count/exit-code alongside a
   job's `failed` status) was scoped in the original diagnosis but not built in this
   pass — the warm-up fix (#1) was judged higher-leverage since it addresses the
   *trigger* (first-call cost) directly, whereas process-level crash detection would
   only have made the *symptom* more visible without reducing how often it fires.
   Revisit if the warm-up mitigation doesn't fully resolve the crash in practice.

### Verification
- `PYTHONPATH=src python -m py_compile src/qwen3_tts/model.py
  src/qwen3_tts/pocket_tts_runtime.py` — passes.
- **Still needed (live container)**: rebuild and deploy, then exercise the original
  repro path (cold boot → immediately "Use in Speak" on a short word; separately,
  let idle-unload fire then immediately "Use in Speak" again) and confirm generation
  now succeeds where it previously crashed. Watch for the new
  `[pocket_tts] Warming up model...` / `Warm-up complete` lines at every load/reload,
  and confirm the stale-default line no longer repeats across multiple
  loads/reloads within the same deployment (it should only appear once, right before
  the file is cleared).
- If the crash still recurs after this fix, the new `voice_id=...` and `voice_state
  resolution: ...` log lines should make the next round of logs immediately more
  diagnostic than the previous two rounds were.

### 6.1 Follow-up: "Use in Speak" didn't guarantee the picked voice was actually used

**Status: implemented** (2026-07-14). After the fixes above landed, further review
surfaced that they addressed a real but narrower problem (the silent first-call-
after-load crash) and missed the actual functional gap the user was most concerned
about: clicking "Use in Speak" on a specific voice did not *guarantee* that voice's
state was what generation used — it navigated to Speak and set the shared `voiceId`
(which the dropdown already read from, so display was fine), but left both "is this
voice's state actually resolvable" and "is the runtime even loaded" undiscovered
until the user's own Generate click, which is exactly when a cold-load + first-time
voice-state-build could compound and fail.

**Fix**: a new `POST /voices/<voice_id>/warm` endpoint (`src/qwen3_tts/app.py`) runs
on the same serialized `model.executor` used by generation: it calls
`model._ensure_base_loaded()` (bounces the runtime back from an idle-unloaded state
if needed) and then `pocket_tts_runtime.get_pocket_tts_voice_state(...)` for that
specific `voice_id`, forcing it to resolve/build and populate the in-memory cache
immediately. `VoiceLibraryPage.tsx`'s "Use in Speak" handler (now `useInSpeak`) sets
`voiceId`, navigates to Speak, and fires this warm call in the background,
surfacing an error banner if the voice can't be resolved. `SpeakPage.tsx`'s own
voice dropdown (`handleVoiceChange`) does the same on every direct selection, so the
guarantee holds regardless of which UI surface picked the voice. This is additive to
(not a replacement for) the warm-up-at-load-time fix in §6 above — that one pays a
one-time cost per model load; this one pays a one-time cost per voice selection.

---

## Outstanding item not covered by this plan

`frontend/src/pages/VoiceLibraryPage.tsx` has an uncommitted, unpushed diff (10
insertions / 4 deletions as of 2026-07-13) fixing the Adjust Prosody popover's
flip/collision behavior and the voice-card hover-lift interaction. This predates the
work in this document and should be committed and pushed on its own (unrelated to
the plan above) before or independently of starting any of the sections here — it
was not committed yet only because it hadn't been explicitly confirmed with the user,
not because of any issue with the fix itself.
