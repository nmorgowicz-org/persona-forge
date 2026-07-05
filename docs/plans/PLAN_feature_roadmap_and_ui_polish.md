# Plan: Feature roadmap (6 items) + UI/UX polish pass

> Audience: a fresh AI coding agent with **zero prior context** on this repo. Read
> `docs/plans/PLAN_persona_forge_studio.md` and `docs/plans/PLAN_voice_design.md` first — this doc
> assumes OmniVoice/Stitch Studio, the segment library, and the chip-based VoiceDesign flow already
> exist and work as described there. This doc scopes six forward-looking features nick asked for
> after using the shipped stitch editor + reference-text-edit + reopen-in-stitch-studio work, plus
> a UI/UX styling audit requested in the same message. Nothing here is started yet except item 7
> (the `/health` polling fix, already shipped separately, see git log — unrelated to this doc).

## 0. Why this doc exists / how to use it

Nick asked, verbatim: *"can you think of any other useful features, capabilities, concepts, etc
that we could consider for our app? are we missing anything important?"* — followed by explicit
enthusiastic buy-in on all six ideas offered, plus: *"can you scope these out into a comprehensive
plan? and in the plan also determine if there are any other modern/premium ui/ux improvements we
can do to elevate our styling and add that in as well?"*

This is a **roadmap**, not a single PR. Each numbered feature below is independently shippable and
ordered roughly by effort-to-value ratio (cheapest/highest-value first), not by numbering from the
original brainstorm. The UI/UX section (§8) is similarly a menu, not a mandate — nick should pick
what's worth doing, not treat it as a required redesign.

**Hard constraints inherited from existing plans (do not violate):**
- VoiceDesign (chip flow) has **no accent chip** — regional/non-US English accent control doesn't
  work reliably on this checkpoint via VoiceDesign; OmniVoice/Stitch Studio is the only
  accent-capable path. Any new UI (multi-speaker mode, presets) must not reintroduce an accent
  control on the chip flow. See `voiceDesignChips.ts` composeDescription() docstring.
- `candidate_id`-only refs (ephemeral in-memory audition cache) can **never** be recovered after
  server restart/eviction — already a known risk surfaced in `PLAN_stitch_editor.md` and the
  reopen-in-stitch-studio feature. Any new feature touching stitch plans or segment refs must keep
  treating `segment_id`/`voice_id` as the only durable refs.
- Swap-in-progress state must stay honestly surfaced, never hidden behind a bare spinner
  (`PLAN_voice_design.md` §3). Any new long-running batch feature (multi-speaker render) must reuse
  the existing swap-banner/progress pattern, not invent a silent wait.

---

## 1. Voice library hygiene at scale

**Problem:** `voice_library.py`'s meta.json schema is
`{voice_id, description, sample_text, language, seed, selections, created_at}` — no `tags`, no
`accent_id`, no controlled gender/language vocabulary. `language` is a free string. Segments
already have `tags`/`accent_id` (`SegmentMeta` in `api.ts`) and `VoiceLibraryPage.tsx` already has
a working search box for segments (`segSearch`, filters text+tags) — **voices have no equivalent**,
which is the most visible inconsistency in the app today as the library grows past a handful of
entries. There's also no bulk-delete and no export/import of the whole library (single-item
`GET/POST/PATCH/DELETE /voices/<id>` only).

**Backend (`src/qwen3_tts/voice_library.py`, `src/qwen3_tts/app.py`):**
- Add `tags: list[str]` to voice meta.json (default `[]`), settable via the existing
  `update_voice()` path — extend it to accept an optional `tags` kwarg alongside `sample_text`, and
  extend the `PATCH /voices/<voice_id>` route/body to accept `tags` optionally (don't require it).
- Derive an implicit "accent" facet for filtering by reading `selections.accent_id` (OmniVoice
  voices) — no new field needed, just expose it read-only via the existing `list_voices()` output
  (already returns the full meta dict, `selections` included).
- New route `POST /voices/bulk_delete` — body `{voice_ids: string[]}`, loops `delete_voice()`,
  returns `{deleted: string[], not_found: string[]}`. Keep it a single request, not N deletes from
  the client, so a slow network doesn't leave a bulk action half-applied without the user knowing
  which ones landed.
- New route `GET /voices/export` — streams a zip (or a single JSON manifest + reference-wav files)
  of the entire voice library for backup. `POST /voices/import` accepts the same shape and
  re-creates voice directories, skipping (not overwriting) any `voice_id` that already exists —
  report skipped/created counts. This is filesystem-backed the same way segment/voice libraries
  already are, no new storage technology.

**Frontend (`frontend/src/pages/VoiceLibraryPage.tsx`):**
- Add a voice-level search/filter bar mirroring the existing segment search (`segSearch` pattern),
  filtering on `description`, `sample_text`, and the new `tags`.
- Add a tag editor inline on `VoiceCard` (reuse the same click-to-edit pattern already built for
  `sample_text` in this session — same component, same commit-on-blur/Enter UX).
- Add multi-select: a checkbox per `VoiceCard` (only visible once "Select" mode is toggled, to
  avoid cluttering the default view), a batch toolbar with "Delete selected" and "Export selected."
  This is net-new UI in this codebase — no existing bulk-select pattern to copy — and it's also
  exactly the row-based batch interaction multi-speaker script mode (§3) will want for
  "assign voice per line," so building it well here pays off twice.
- "Export library" / "Import library" buttons near the page header, hitting the new routes above.

**Verification:** `python3 -m py_compile` the backend files; `curl` the new routes directly against
a running dev container before wiring the frontend; `npx tsc --noEmit && npm run build` for the
frontend; manual test: tag a few voices, filter by tag, bulk-select-delete, export then re-import
into a fresh library dir and confirm round-trip fidelity (best effort, low risk since this only
touches the library, not generation).

---

## 2. Free transcript export (SRT/VTT)

**Problem:** every stitched voice/segment already carries per-clip text and precise timing
(`stitch_plan.clips[]` has `trim_start_ms`/`trim_end_ms`, and each segment has `duration_sec`) — but
there's no way to get a subtitle file out of a finished render. This is close to free: no new audio
processing, just a serializer over data that already exists.

**Backend (`src/qwen3_tts/app.py`, new small module e.g. `src/qwen3_tts/subtitle_export.py`):**
- Add a pure function `build_subtitle_cues(stitch_plan, segments_by_id) -> list[Cue]` where `Cue =
  {start_ms, end_ms, text}`. Compute cumulative timeline offsets by walking `stitch_plan.clips[]` in
  order, applying each clip's actual (trimmed) duration plus the gap padding/crossfade between
  clips (reuse the same duration math `audio_post.stitch_segments`/`concat_with_padding` already
  does server-side, don't reimplement it — factor the offset bookkeeping out of that function if
  it's not already a separable step).
- `srt_from_cues(cues) -> str` and `vtt_from_cues(cues) -> str` — trivial format serializers
  (`HH:MM:SS,mmm --> HH:MM:SS,mmm` for SRT, `HH:MM:SS.mmm --> ...` for VTT), no external dependency
  needed for something this small.
- New route `GET /voices/<voice_id>/subtitles?format=srt|vtt` — reads `selections.stitch_plan`
  (already persisted), resolves each clip's segment/voice text + duration, returns the file with
  the right `Content-Type`/`Content-Disposition` for direct download. If a voice has no
  `stitch_plan` (raw VoiceDesign/chip voice, single clip), just return a single cue spanning the
  whole `sample_text` — one code path handles both cases.

**Frontend:** a "Download subtitles" button on `VoiceCard` (only shown when the export would
produce more than one cue, i.e. `stitch_plan.clips.length > 1` — a single-cue file for a bare
VoiceDesign voice is not useful and would just be clutter) with a small format picker (SRT/VTT).

**Verification:** unit-testable in isolation (pure functions, no model/audio dependency) — add a
test file if `tests/` has a place for it; otherwise a quick manual `curl` against a real stitched
voice, diff the cue timings against the stitch plan's own trim/padding values by hand for one
example to confirm the offset math is right.

---

## 3. Multi-speaker script mode

**Problem:** the app can build any number of individual voices but has no concept of a *dialogue* —
today, narrating a multi-character script means manually running `/generate` once per line and
concatenating the output yourself outside the app.

**Scope (v1, deliberately conservative):** a new page/panel that accepts a pasted script in a
simple line-oriented format (`Speaker: line text`), lets the user map each detected speaker name to
a saved voice from the library (reusing `VoiceCard`'s voice-picker affordance, or a simple
dropdown-per-speaker), and then batch-renders each line through the existing `/generate` endpoint
(one call per line, sequential — **not** a new bulk-generation endpoint in v1; the existing
single-shot `/generate` already accepts `voice_id`, so no backend change is required for the
generation step itself), finally concatenating the resulting clips with the existing
`audio_post.stitch_segments`/padding logic (reuse, don't reimplement) into one downloadable file.

**Backend:**
- v1 needs **no new generation route** — reuse `/generate` in a loop from the frontend, same as
  today's individual-line workflow, just orchestrated.
- One new route: `POST /scripts/render` — body `{lines: [{voiceId, text}], paddingMs?: number}`.
  Server-side loop calling the same generation path internally (avoids N round-trips + N
  cold-model-swap risks if voices differ in engine — see below), then stitches with
  `audio_post.concat_with_padding`, returns one file. This also naturally produces the "batch job
  with progress" UX the swap-banner/progress patterns already support (reuse the same job-polling
  pattern `omnivoice_engine`'s audition jobs use — `job_id` + `/progress` polling — rather than
  inventing a third polling shape).
- **Important constraint to flag, not solve in v1:** if different lines use voices that require
  different underlying engines (e.g. one `voice_id` was VoiceDesign-cloned vs. OmniVoice-cloned),
  each line generation may still route through the same single "Base" model + reference-audio
  conditioning regardless of origin engine (confirm this against `app.py`'s `/generate` handler
  before assuming) — there should be no swap-per-line if that's already true, but this needs to be
  explicitly checked against the real generate() code path before implementation, not assumed.

**Frontend:**
- New page `ScriptStudioPage.tsx` (or a mode within an existing page — nick's call): a textarea for
  the script, a parsed speaker list below it (auto-detected from `Speaker:` prefixes) each with a
  voice-picker dropdown (reuse `VoiceCard`'s voice list, not a new fetch), a per-line preview list
  (reuse `StitchTimeline`'s clip-row visual language for consistency — same rounded card language,
  same waveform-on-render pattern once available), a "Render script" button that calls
  `/scripts/render` and polls progress the same way OmniVoice audition does today.
- This is the single largest net-new feature in this roadmap — budget it as its own multi-step
  delivery (parse+assign UI first, wire real rendering second, add per-line waveform/re-take third)
  rather than one PR.

**Verification:** backend route curl-testable with a small 2-3 line script before any frontend
exists (mirrors the delivery-order discipline already used for stitch_plan in
`PLAN_stitch_editor.md`); frontend `tsc --noEmit && npm run build`, then manual test with a real
multi-speaker script end to end.

---

## 4. DSP presets (Stitch Studio)

**Problem:** `StitchPlanDsp` (`store.ts`, `{segmentTargetDbfs, finalTargetDbfs, finalCeilingDb,
crossfadeMs, compressEnabled, compressThresholdDb, compressRatio}`) is fully wired end-to-end
already (`/omnivoice/stitch` and `/omnivoice/save` both accept the whole shape via `stitch_plan`),
but every session starts from the same defaults with no way to save/reuse a named tuning a user
likes (e.g. "punchy podcast," "gentle audiobook").

**Backend:** small new filesystem-backed store, same pattern as voice/segment libraries — a single
`dsp_presets.json` (or one-file-per-preset dir, matching whichever convention `voice_library.py`
uses — check before choosing, prefer consistency over inventing a new pattern) holding
`{preset_id, label, dsp: StitchPlanDsp-shaped dict, created_at}`. Routes: `GET /dsp_presets`,
`POST /dsp_presets` (create from current values), `DELETE /dsp_presets/<id>`. No update route
needed for v1 — deleting and re-saving under the same label is fine at this scale.

**Frontend:** a preset picker dropdown in the Stitch Studio DSP panel, styled after the existing
static `PRESETS` picker pattern in `voiceDesignChips.ts`/VoiceDesignPanel (same one-click-apply UX,
different data source — user-saved instead of hardcoded). "Save current as preset" button prompts
for a label, POSTs the current `ovStitchPlanDsp` values.

**Verification:** `python3 -m py_compile`; curl the three routes; `tsc --noEmit && npm run build`;
manual test: tune DSP, save preset, reload page, reapply preset, confirm identical values load.

---

## 5. Voice health dashboard

**Problem:** ASR-confidence data (`whisper_transcript`, `match_score`, computed via
`asr_check.py`'s fuzzy-match scoring against `ASR_MIN_MATCH_SHORT=0.70`/`ASR_MIN_MATCH_LONG=0.80`
thresholds) is already computed and durably stored **per segment**, but is only ever shown
transiently during generation (`TakeDebugButton`, OmniVoicePanel) — never surfaced again once a
segment is locked in or a voice is saved from it. Voices themselves have no direct quality signal.

**Backend:** no new computation needed for the segment-level signal (already stored) — just a new
read: extend `GET /voices` (or add `GET /voices/<id>/health`) to compute, per voice, the aggregate
of its composing segments' `match_score`s by walking `selections.stitch_plan.clips[].segment_id`
and joining against the segment library (same join `reopenInStitchStudio` already does
client-side — consider whether this aggregation is cheap enough to do lazily client-side instead of
adding a backend route, since the segment list is already fetched separately in
`VoiceLibraryPage.tsx`). For raw VoiceDesign/chip voices (no `stitch_plan`), there's no stored
match_score at all — either leave health "N/A" for those (simplest, honest) or add an opt-in
"re-check" action that runs a fresh ASR pass against `reference.wav` vs `sample_text` on demand
(more work, only do this if nick specifically wants a health score for chip-built voices too — ask
before building, don't assume).

**Frontend:** a small badge on `VoiceCard` (reusing the same color-coding thresholds already
defined in `TakeDebugButton`, `OmniVoicePanel.tsx` ~lines 136-143) showing aggregate confidence
for stitch_plan-based voices; clicking it expands the per-clip breakdown (which segment scored
what) — this doubles as a discovery mechanism for "which segment should I re-take" without leaving
the Voice Library. A dedicated "dashboard" page/view (sortable table: voice, avg confidence, #
flagged clips, created date) is a reasonable v2 if nick wants a library-wide overview rather than
per-card badges only — start with the per-card badge, it's cheaper and delivers most of the value.

**Verification:** since this is aggregation-only (no new ASR computation) client-side, `tsc
--noEmit && npm run build` covers most of it; manually confirm the aggregate math against a
known multi-segment voice's individual segment scores (visible today via `TakeDebugButton` history
if segments are still in the library).

---

## 6. In-place voice update (audio-level)

**Problem:** nick was explicitly torn on this one ("i'm torn on how that should be handled") — the
only in-place edit today is metadata-only (`sample_text` via `update_voice()`); every audio-level
change (chip retune, new stitch assembly) forks a new `voice_id`. This is the least-defined item in
the roadmap and should be scoped conservatively.

**Recommendation:** do **not** build silent in-place audio replacement. A voice_id being
referenced elsewhere (past generations, saved presets/scripts once §3 exists) means secretly
swapping its underlying audio changes past output retroactively with no trail — surprising and hard
to reason about. Instead, ship an explicit **"Replace audio, keep voice_id"** action, gated behind
a confirmation that says exactly what it does (old `reference.wav` is discarded, `voice_id` and any
existing tags/library entries stay put) — this is a deliberate, visible operation, not a hidden
side effect of "editing." Concretely:
- Backend: extend `update_voice()` to optionally accept new `audio_base64`/`sample_rate` (in
  addition to the already-shipped `sample_text`-only path), overwriting `reference.wav` in place,
  bumping `created_at` or adding an explicit `updated_at` field so it's visible in the UI that the
  audio changed after creation.
- Frontend: on `VoiceCard`, a clearly distinct action (different icon/color from the existing
  "Design a new voice from this one" fork action) — e.g. a small "Replace audio…" menu item that
  opens the same re-record/re-stitch flow (chip retune or reopen-in-stitch-studio) but on
  confirmation calls the extended `update_voice` PATCH instead of creating a new voice.

**Explicitly out of scope for this item** (per nick's own uncertainty, and per the existing
compression/normalization pipeline already equalizing loudness): waveform-level sample editing
(trim/cut arbitrary regions, amplitude-highlight-and-adjust). Stitch Studio's trim/fade/compression
controls already cover the realistic editing needs; a full sample editor is a large, separate
surface that duplicates DAW functionality with little marginal benefit here. Don't build this
unless a concrete need shows up that Stitch Studio's controls can't address.

**Verification:** `python3 -m py_compile`; manual test: replace a voice's audio, confirm `voice_id`
unchanged, confirm old references relying on that `voice_id` (e.g. a script mapping, once §3
exists) now produce the new audio — this is the whole point, verify it's true and clearly
communicated in the UI, not just technically true.

---

## 7. `/health` polling storm — status: shipped

Not part of the roadmap above; noted here only for completeness since it was reported in the same
message as the feature request. Root cause and fix: `useSwapStatus` (`frontend/src/hooks/
useSwapStatus.ts`) polled `/health` every 2.5s forever with a bare `fetch()` — no request timeout,
no backoff — so an unreachable backend (host asleep, network drop) let failures pile up over time
with nothing capping retry frequency or attempt duration. Fixed with an `AbortController`-based 6s
per-attempt timeout and exponential backoff (capped at 30s) that resets on the next successful
check. Shipped in commit `f326657` on this branch; no further action needed.

---

## 8. UI/UX polish audit

Current state is genuinely good, not a redo: `index.css` has full oklch-based dark/light tokens,
four accent theme variants (violet/teal/amber/rose via `data-theme`), custom slim scrollbars, and
`package.json` already includes shadcn/ui primitives, radix-ui, framer-motion, and tw-animate-css —
**no new dependencies are needed for anything below.** `VoiceCard` (`VoiceLibraryPage.tsx`) is
already a good template — rounded-xl cards, `whileHover={{ y: -2 }}` framer-motion lift, shadow-sm
→ shadow-lg on hover — new UI (script mode's per-line rows, preset picker, bulk-select toolbar)
should copy this template rather than inventing a new visual language.

### Quick wins (do alongside the features above, not a separate initiative)
- **No voice-level search/filter UI** while segments have one — the most visible inconsistency
  today, and directly required by §1 anyway. Building it well there closes this gap for free.
- **No bulk-select pattern anywhere in the app** — needed fresh for §1 (bulk delete/export) and
  reusable as-is for §3 (assign voice per script line is the same "many rows, batch action" shape).
  Build it once, in §1, as a small reusable component (checkbox column + selection state + batch
  toolbar), not bespoke twice.
- **No page-level empty-state/skeleton treatment** — per-card spinners exist (e.g.
  `VoiceAudioAutoPlayer`'s loading state) but a first-load of the Voice Library or Stitch Studio
  with zero content just shows nothing. A simple "No voices yet — build one in Persona Forge" empty
  state with a CTA button is cheap and reads as more finished.
- **Native `window.confirm()` for destructive actions** — `OmniVoicePanel.tsx:1677`,
  `VoiceLibraryPage.tsx:507`, `VoiceLibraryPage.tsx:521` all pop the raw unstyled browser confirm
  dialog for delete-voice/delete-segment. It's the single most jarring visual break in the app —
  no theming, no animation, looks like a different program. `components/ui/dialog.tsx` (shadcn over
  `radix-ui`, already a dependency) is enough to build one small reusable `ConfirmDialog` component
  and swap all three call sites — no new dependency.
- **No toast/notification system** — every action's feedback (save voice, save preset, error)
  goes through a single ad hoc `{error && <p>...}` slot per page (e.g. `VoiceLibraryPage.tsx:556`),
  so only one message can be visible at a time, a later error silently clobbers an earlier one, and
  there's no positive-confirmation UI for successful actions beyond scattered inline text like
  `{savedVoiceId && <p>...}`. `radix-ui` already bundles the Toast primitive, so a small
  `sonner`-style toast stack is buildable with zero new packages — this would unify success/error
  feedback across every page in one pass rather than each page inventing its own inline message.

### Larger investment (flag, don't block the roadmap on it)
- **Status: partially done.** `OmniVoicePanel.tsx` was ~3,100 lines mixing generation, audition,
  segment rack, and the stitch-editor trigger in one file. `ClipPlayer`, `InfoIcon`,
  `TakeDebugButton`, `SegmentRackRow`, `ChipSection`, and `AccentChipPanel` (the chip-based instruct
  composer) have been extracted into `frontend/src/components/OmniVoice/` (named for the engine
  these components are specific to — OmniVoice — not the app's overall "Persona Forge" branding),
  bringing the main file down to ~2,440 lines. What's left — the script composer, advanced-options
  panel, segment-rack orchestration, and generate/stitch triggers — is ~2,100 lines of JSX threaded
  through 20+ pieces of interdependent local state (`scriptWordCount`, `heroMeterState`,
  `examplesOpen`, `applyHeroTake`, etc.), so further splitting isn't a mechanical move anymore: it
  needs either prop-drilling two dozen values into new components or moving that state into a
  shared hook/context first. Worth doing as its own scoped task before §3 (the largest new surface,
  which will otherwise be tempted to bolt onto the same monolith) — but treat it as a real refactor,
  not a continuation of the quick extraction already done.
- No dedicated "dashboard" visual language exists yet (tables, sortable columns, aggregate stat
  cards) — only card grids so far. §5's v2 (a real health dashboard view, if wanted) and any future
  "library at scale" overview would benefit from establishing one dashboard layout pattern once,
  rather than each feature inventing its own table styling.

### Explicitly not recommended
- No new component library, animation library, or design-token system — the existing shadcn +
  radix + framer-motion + oklch-token setup is modern and sufficient; swapping any of it out would
  be pure churn with no user-visible benefit.
- No dark/light mode work — already fully implemented across accent themes.

---

## 9. Repo/image/container rebrand (`qwen3-tts` → Persona Forge) — scoped, not scheduled

**Status: flagged by nick, not decided.** During the OmniVoice/Persona Forge source-naming
cleanup (frontend components, comments), we confirmed the app's actual product brand is
"Persona Forge" (see `AppShell.tsx`'s sidebar title) while OmniVoice is one engine inside it.
Source-level naming is now consistent. What's *not* consistent is everything one level up: the
git repo, Python package, Docker image, container, and every doc/script that references them are
still named after the original `qwen3-tts` framing. This section scopes what a rebrand would
touch and what it would cost, so the decision can be made deliberately rather than by drift.

### What's actually named `qwen3-tts` today

- **Git repo**: `qwen3-tts-openvino` (GitHub: `nmorgowicz-org/qwen3-tts-openvino`).
- **Python package**: `src/qwen3_tts/` — imported as `qwen3_tts` in ~45 places across
  `src/` and referenced in `pyproject.toml`/entrypoints.
- **Docker image**: built from `Dockerfile`, tagged `qwen3-tts-openvino:<branch-or-version>`,
  pushed to GHCR as `ghcr.io/nmorgowicz-org/qwen3-tts-openvino` (`.github/workflows/image.yml`,
  `IMAGE_NAME` env var, release tag pattern `qwen3-tts-openvino-v*`).
- **Container name**: `qwen3-tts` (`compose.yml` service name `qwen3-tts`, `container_name`,
  and every runtime reference — `docker exec qwen3-tts kill -HUP 1`, `docker restart qwen3-tts`).
- **Env var prefixes**: `QWEN3_TTS_IMAGE`, `QWEN3_TTS_PORT` in `compose.yml`.
- **Docs**: `CLAUDE.md`, `AGENTS.md`, `docs/HOW_TO_RUN.md`, `docs/DEV_TEST_LOOP.md`,
  `docs/agent-reference/TRANSFORMERS_COMPAT.md` all instruct against these exact names
  (image tags, container name, exec/restart commands).
- **Claude memory files** (this machine, not the repo): several memory entries name the
  container/image directly (e.g. `dockermisc1-ops.md`, `simplify-v2-refactor.md`) — a rename
  would make those entries stale until manually updated.

### Cost/risk if fully renamed end-to-end

- **High blast radius, low reversibility on the ops side**: the container name and image tag are
  load-bearing in the documented dev-test loop (CLAUDE.md's `docker exec qwen3-tts kill -HUP 1`,
  the dockermisc1 deployment, and any external scripts/cron on that host that assume the current
  name). Renaming requires touching the live dockermisc1 container (stop old, rename/recreate,
  verify port/volumes/env all carried over correctly) — that's a real-service action, not a pure
  source change.
- **Python package rename** (`src/qwen3_tts` → e.g. `src/persona_forge`) touches ~45 import
  sites, `pyproject.toml`, Dockerfile `COPY`/`WORKDIR` references if any hardcode the path, and
  any external tooling (export scripts, benchmark scripts) that imports the package by name.
  Mechanical but wide — the kind of change that's easy to get 95% right and leave a handful of
  broken imports.
- **GHCR image rename** changes the pull path for anyone/anything already referencing
  `ghcr.io/nmorgowicz-org/qwen3-tts-openvino` — old tags don't silently redirect, so a rename is
  effectively "publish a new image location," not a rename in the strict sense. The GitHub Actions
  workflow's tag-push trigger pattern (`qwen3-tts-openvino-v*`) would also need updating, and any
  existing tags stay under the old name unless retagged.
- **Git repo rename** (via GitHub's rename) is the cheapest part in isolation — GitHub
  transparently redirects the old URL — but every hardcoded `git remote`/clone URL in scripts,
  CI, and dockermisc1's existing checkout would still work via redirect, so this alone is
  low-risk. The risk is doing it *in isolation* while image/container names diverge further from
  the repo name than they already do.

### Recommendation

Don't do this as part of the current roadmap/polish work — it's an infra/ops decision with
real-service risk, not a code-quality one, and nothing above is blocking any of §1-§8. If/when
nick wants to proceed, split it into independently-reversible steps and confirm before each one
that touches the live container:

1. **Cosmetic-only first pass (near-zero risk)**: rename just the GitHub repo (redirect-safe) and
   update CLAUDE.md/AGENTS.md/docs prose to call the product "Persona Forge" in narrative text,
   while leaving every command, env var, image tag, and container name exactly as-is. This gets
   the repo's public-facing name aligned without touching anything that runs.
2. **Env var / image tag rename** (`QWEN3_TTS_IMAGE` → e.g. `PERSONA_FORGE_IMAGE`,
   `qwen3-tts-openvino:<tag>` → `persona-forge:<tag>`) — requires a coordinated compose.yml +
   CI workflow + dockermisc1 update in one sitting, since half-migrated env vars would silently
   fall back to defaults and mask breakage. Do this only after step 1 has been live a while with
   no issues.
3. **Container rename on dockermisc1** — the actual live-service risk step: stop the old
   container, recreate under the new name with identical port/volume/env mappings, verify `/health`
   and a real `/generate` call before considering it done, then update CLAUDE.md's dev-test-loop
   commands and all Claude memory entries that reference the old container name.
4. **Python package rename** (`qwen3_tts` → e.g. `persona_forge`) — purely mechanical, do this
   whenever convenient since it has no runtime/ops risk once the import sites are all updated and
   verified with `python3 -m py_compile`/existing test tiers; not coupled to steps 1-3.

None of these steps should be bundled — each is independently shippable and independently
revertible, matching the "small, focused changes" convention already in place for this repo.

---

## Suggested delivery order

1. §1 (voice hygiene) + the bulk-select component + voice search bar — cheapest, closes the most
   visible existing gap, and the bulk-select component pays for itself again in §3.
2. §2 (subtitle export) — nearly free, no audio/model risk, good standalone win.
3. §4 (DSP presets) — small, self-contained, reuses an existing UI pattern.
4. §5 (voice health dashboard, per-card badge only) — aggregation-only, low risk.
5. Finish the `OmniVoicePanel.tsx` split (prep work, not user-visible; the easy extractions are
   already done, see §8's "Larger investment" note) — do before §3 starts, not after.
6. §3 (multi-speaker script mode) — largest item, deliver in its own sub-phases (parse+assign UI →
   real rendering → per-line re-take/waveform).
7. §6 (in-place audio replace) — smallest technical lift but needs nick's explicit sign-off on the
   "Replace audio…" UX/confirmation copy before building, since it's the one item he was personally
   unsure about.

Each numbered item above should be its own PR/commit series, following the existing dev-test loop
(commit+push, pull+rebuild on dockermisc1, `docker restart qwen3-tts` for any backend change) —
don't bundle multiple roadmap items into one deploy cycle.

§9 (repo/image/container rebrand) is deliberately **not** in this ordered list — it's an
infra/ops decision nick hasn't greenlit yet, scoped in this doc so it's ready to schedule
whenever he decides, not because it's next.
