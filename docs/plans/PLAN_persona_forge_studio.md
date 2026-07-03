# Plan: Persona Forge Studio — OmniVoice engine integration + audio pipeline + UI redesign

> Audience: a fresh AI coding agent with **zero prior context** on this repo. Read
> `docs/plans/PLAN_omnivoice_integration.md` first — it is the research/validation doc this plan
> builds on (accent capability, reliability numbers, sentence-bank findings, memory/CPU numbers).
> This doc is the *build* plan for the three things nick asked for in the same request: (1) wire
> OmniVoice into the existing container using the already-built model-swap/RAM-freeing machinery,
> (2) a real audio post-processing pipeline (normalization/compression) for stitched multi-segment
> clips, (3) a UI redesign with "VST-level" visualization and 2026 styling as a top requirement,
> not an afterthought. Total redesign of the affected UI surfaces is explicitly in scope if that's
> what doing this properly requires.

## 0. Why this doc exists / decisions already made

`PLAN_omnivoice_integration.md` validated that OmniVoice can produce genuine Australian-accented
output, established the generate-N-and-pick + short-sentence-stitching workflow as the only
reliable path to a 10-15s reference clip, and confirmed the practical numbers: RTF≈12 on
dockermisc1's real CPU (irrelevant now — batch/attach-to-message flow, not live), and 2.80 GB
peak RSS during generation (confirmed fine, no memory optimization needed). Three decisions were
made in conversation and are treated as settled here, not re-litigated:

1. **In-container, not a sibling container.** OmniVoice reuses this repo's existing
   load/unload/swap infrastructure (`model.py`'s `force_unload()` / `load_model()`, the pattern
   already proven by `voice_design.py`'s Base↔VoiceDesign swap), not a second Docker service.
   `torch==2.12.1` / `torchaudio==2.11.0` / `transformers==5.12.1` are already pinned in the
   Dockerfile for `qwen-tts`'s own preprocessing and match OmniVoice's dependency floors exactly —
   the only new runtime dependency is `pydub` (lightweight, pure-Python; `omnivoice`'s heavier
   extras — `gradio`, `webdataset`, `tensorboardx` — are training/demo-only and untouched by the
   inference path, confirmed by inspecting `omnivoice/__init__.py`'s import graph).
2. **On-demand swap, not resident.** Same one-model-at-a-time discipline as VoiceDesign: swap Base
   out, load OmniVoice, run a whole *job* (all segments, all candidate takes) in one swap window,
   swap Base back in. Never resident alongside Base.
3. **Full redesign is in scope for the UI surfaces this touches.** Not a bolt-on panel — nick
   explicitly said "if this means a total redesign, thats fine." Treat §3 below as the real
   target, not a nice-to-have.

## 1. Backend: OmniVoice engine module

### 1.1 New module: `src/qwen3_tts/omnivoice_engine.py`

Mirrors `voice_design.py`'s shape (`swap_in_progress()`, a `run_*` entry point run inside
`model.executor`, `finally`-guaranteed restore of Base) with two structural differences forced by
the cherry-pick workflow:

- **Request shape is multi-segment, multi-candidate, not single-shot.** VoiceDesign's
  `run_voice_design_request` produces exactly one WAV per call. OmniVoice's equivalent needs to
  produce `len(segments) × candidates_per_segment` WAVs from *one* swap (load OmniVoice once,
  generate everything, unload once) — paying the model-load cost once per job, not once per
  candidate. Suggested signature:

  ```python
  def run_omnivoice_job(
      segments: list[str],
      instruct: str,
      candidates_per_segment: int = 3,
      seed: int | None = None,
  ) -> list[list[tuple[Any, int]]]:
      """Returns segments × candidates of (wav, sample_rate), Base always restored on exit."""
  ```

- **The loaded object is a plain `nn.Module`, not an OV runtime.** Introduce a
  module-level `_omnivoice_model: OmniVoice | None = None` global in `omnivoice_engine.py` —
  don't try to force it through `model.py`'s `model` global, which is typed/used throughout that
  file for the OV runtime specifically. The swap sequence is:

  ```python
  model.force_unload()                    # drop Base, gc.collect() x2, malloc_trim(0)
  _omnivoice_model = OmniVoice.from_pretrained(
      "k2-fsa/OmniVoice", dtype=torch.float32
  ).to("cpu")
  try:
      # generate all segments × candidates here
  finally:
      _omnivoice_model = None
      gc.collect(); gc.collect()
      ctypes.CDLL("libc.so.6").malloc_trim(0)   # same idiom force_unload() already uses
      model.load_model(model.BASE_PROFILE)
  ```

  This duplicates ~4 lines of `force_unload()`'s cleanup tail rather than trying to generalize it
  to handle a non-OV model — `force_unload()` is reused as-is for dropping Base; the OmniVoice
  teardown is separate code because it's a different object type. Don't over-abstract this into a
  shared "unload anything" helper for a two-caller case.

- **Seeding:** no manual seed by default (2026-07-03 finding: manual-seeding a whole batch made
  results *worse*, not more reproducible — see `PLAN_omnivoice_integration.md` §5a). Accept an
  optional seed per job for reproducibility/debugging, but the default UX path should leave it
  unset so each segment/candidate gets an independent draw.

### 1.2 New routes in `app.py`

Separate from `/voice_design` — the request/response shape is different enough (multi-segment,
multi-candidate, plus a distinct stitch step) that overloading the existing route would make both
worse. Suggested:

- `POST /omnivoice/audition` — body `{"segments": [...], "instruct": "...", "candidates_per_segment": 3}`.
  Runs `omnivoice_engine.run_omnivoice_job` via `model.executor.submit(...)` (same pattern as
  `voice_design_create`), returns `{"segments": [{"candidates": [{"candidate_id", "audio_base64", "sample_rate"}, ...]}, ...]}`.
  This is the "generate options to cherry-pick from" call — no stitching yet, no save yet.
- `POST /omnivoice/stitch` — body `{"selections": ["candidate_id", "candidate_id", ...]}` (one
  chosen candidate per segment, referencing IDs from the immediately-preceding `/audition`
  response — needs a short-lived server-side cache of the raw candidate WAVs keyed by
  `candidate_id`, since re-sending base64 audio back from the client is wasteful; a simple
  in-memory dict with a TTL, cleared on next `/audition` call, is enough — this is a single-user
  local tool, not a multi-tenant service). Runs the §2 post-processing pipeline (normalize each
  segment, crossfade-concatenate, final limiter pass) — **pure numpy/no model needed**, so this
  route does not need `model.executor` at all and can run inline, fast. Returns the final WAV,
  which then flows into the existing `voice_library.save_voice` path exactly like
  `/voice_design`'s output does today.

Both routes reject concurrent use the same way `/voice_design` does (`swap_in_progress()` gate),
extended to also cover `omnivoice_engine.swap_in_progress()`.

## 2. Audio post-processing pipeline (normalization/compression)

This is a new, required piece — nick's exact complaint was that a naive concatenation ("stitch")
of independently-generated segments leaves the result "all over the place" in level, which is
expected: each segment is an independent model draw with its own loudness. The pipeline below
runs entirely in `omnivoice_engine.py` (or a new `src/qwen3_tts/audio_post.py` if it's reused
elsewhere — e.g. VoiceDesign output could benefit from the same final normalization pass, worth
checking once built), using only numpy/soundfile/librosa (already in `requirements-runtime.txt`,
no new deps needed for this part).

1. **Per-segment loudness normalization, before concatenation.** Normalize each candidate to a
   common target loudness so cherry-picking in the UI (§3.3) is a fair A/B comparison — otherwise
   a quieter take can sound "worse" for reasons unrelated to accent/delivery quality. RMS-based
   normalization is simplest and sufficient here (LUFS/ITU-R BS.1770 via `pyloudnorm` is more
   "correct" for perceived loudness but is a new dependency for marginal benefit on short speech
   clips — start with RMS, revisit only if it's audibly insufficient).
2. **Gentle dynamic-range compression per segment**, applied *before* normalization, not instead
   of it — normalization alone can't fix a segment that's internally uneven (loud word, quiet
   word). Soft-knee, mild ratio (~2:1–3:1), fast-ish attack/release tuned for speech (not music) —
   the goal is evening out delivery, not squashing expressiveness. A from-scratch numpy compressor
   is a small amount of code (envelope follower + gain computer + smoothing) — no new dependency
   required, but flag `pedalboard` (Spotify's audio-effects library, has a proper
   `Compressor`/`Limiter`/`Gain` chain, permissive license, pure-C++-backed so fast) as an
   alternative if hand-rolling turns out fiddly. Decide during implementation, not in this doc.
3. **Crossfade instead of a hard silence gap at segment boundaries.** The prototype script used a
   flat 350ms silence gap between segments — fine for a quick reliability test, not fine for a
   real reference clip: an abrupt cut between two independently-normalized/compressed segments
   will still have an audible seam (room tone, breath noise, tiny level step). Use a short
   (~80-150ms) equal-power crossfade instead of pure silence, with a small silence pad only if the
   segments' natural pause needs it for pacing.
4. **Final pass on the fully stitched clip**: peak limiting (prevent clipping introduced by the
   crossfade overlap adding two signals together) + a final loudness normalization to a fixed
   target (e.g. -16 to -18 dB RMS, reasonable for a spoken reference clip — not a broadcast/music
   loudness target). This is the last step before the clip is handed to `voice_library.save_voice`
   or `/voices/import`.
5. **Order matters — don't skip straight to "just normalize the final output."** Per-segment
   compression before per-segment normalization before crossfade before final limiting, in that
   order. Normalizing only the final concatenated clip does nothing to fix uneven *internal*
   dynamics of individual segments (the actual complaint) — it just moves the average level, not
   the variance.

This pipeline is deterministic, cheap (no model inference), and should be fast enough to run
synchronously inside `/omnivoice/stitch` without a job queue.

## 3. Frontend: "VST-level" UI redesign, 2026 styling

### 3.1 Framing

The current frontend (`frontend/src/`) is a standard shadcn/Tailwind admin-panel look — functional
chip-based forms, no audio visualization beyond an `<audio>` element presumably. Nick's ask is
explicit: treat this like a real audio-plugin/DAW surface, not a form. Concretely, that means the
UI needs to *show* the audio, not just let you play it — waveforms, levels, and generation
progress should be visual, live, and responsive, the way a VST GUI (analog-modeled compressor
plugin, iZotope RX, a DAW's clip lane) communicates state at a glance. "2026 styling" here means:
depth/motion as information (not decoration), high information density with progressive
disclosure (a studio surface, not a wizard), dark-first (already the case —
`<html class="dark">`), and spring-physics motion rather than linear CSS transitions, which reads
as dated next to any current native app or serious web audio tool.

### 3.2 New/changed frontend dependencies

- **Waveform rendering + interaction:** `wavesurfer.js` (canvas-based, region/marker support,
  actively maintained, MIT) — renders per-segment and stitched-clip waveforms, supports zoom,
  playhead scrubbing, and region highlighting (useful for showing crossfade boundaries). Avoids
  hand-rolling canvas waveform math.
- **Motion:** `framer-motion` (or `motion` — same library, renamed) — spring-based layout
  animations, shared-element transitions between "generating" → "candidate ready" states,
  micro-interactions on hover/select. This is the single highest-leverage dependency for hitting
  the "2026, not 2021" bar — most of what reads as dated in the current UI is linear
  opacity/transform transitions, not the component library choice underneath.
- **Live metering during playback:** no new dependency — Web Audio API's `AnalyserNode` (built
  into every browser) is enough for a real-time level meter / mini-spectrum tied to the
  `<audio>`/`AudioBufferSourceNode` playback, canvas-rendered.
- Evaluate whether shadcn/Tailwind stays as the base layer (recommended: yes — the *components*
  aren't the problem, the motion/visualization layer on top of them is) vs. a fuller rip-and-
  replace. Recommendation: keep Tailwind + shadcn primitives for structural chrome (dialogs,
  buttons, layout), add the above three for the studio-specific surfaces (segment rack, waveform
  cards, meters) rather than replacing the whole design system — lower risk, faster to ship,
  and the "VST-level" ask is really about the audio-specific surfaces, not the settings pages.

### 3.3 New components (Persona Forge Studio surface)

- **`EngineSelector`** — top-level choice between "Qwen VoiceDesign" (free-form, fast, no accent
  guarantee — carries the caveat copy already added to `VoiceDesignPanel.tsx`) and "Persona Forge
  Engine" (OmniVoice-backed, accent-bank-driven, slower/multi-step but higher accent fidelity).
  Not a toggle buried in settings — this is a primary navigation decision, should be presented
  like choosing an instrument/preset category in a DAW, not a dropdown.
- **`AccentBank`** — replaces free-text sample input for the OmniVoice path (per
  `PLAN_omnivoice_integration.md` §5a): a per-accent set of curated segment sentences, each with
  an audition ("preview") action before committing to a full job. Visually: a card grid or
  horizontal rack, one card per accent, showing the segments included and a quick-play of a
  pre-baked reference (not live-generated — bake one canonical example per accent at build/deploy
  time so browsing the bank doesn't cost a generation).
- **`SegmentRack`** — the core new surface: one row/card per sentence segment in the current job,
  each showing:
  - `candidates_per_segment` waveform thumbnails (wavesurfer instances) side by side, one marked
    selected (matches "cherry-pick" requirement from the prior conversation turn).
  - A live level meter overlay while the job is generating (indeterminate "working" animation
    before real data exists — see §3.4 — not a bare spinner).
  - Per-segment "regenerate" action (re-roll just this segment's candidates without restarting the
    whole job) — this is the concrete UI expression of the per-segment cherry-pick requirement.
- **`StitchPreview`** — once segments are picked, a single combined waveform (post §2 pipeline)
  with visible crossfade regions marked (wavesurfer regions), playhead scrub, and a final
  loudness/peak readout (simple numeric + small meter, VST-plugin-style) so the effect of
  normalization/compression is visible, not just audible.
- **`GenerationProgress`** — replaces a bare spinner during the OmniVoice swap+generate window
  (which, per §0, can take real wall-clock time — RTF≈12 on dockermisc1, batch is fine but still
  visible): a live-feeling progress surface (animated waveform "building," per-segment status
  chips going pending→generating→ready) rather than a static loading indicator, consistent with
  the "communicate state visually" framing above.

### 3.4 Motion/interaction requirements (explicit, since "2026 styling" is otherwise vague)

- Spring-based (not linear-eased) transitions for anything that changes size/position — candidate
  cards appearing, segment status changing, panel expand/collapse.
- No layout jank: use `framer-motion`'s `layout` prop / `AnimatePresence` for list changes
  (candidates appearing one at a time as they finish generating) rather than a full re-render pop-
  in.
- Waveforms should animate in (draw-on, not appear instantly) when a candidate finishes
  generating — reinforces "this just got made," not "this was always here."
- Meters/levels should feel real-time even where the underlying data is static post-generation
  (i.e., animate the meter sweeping to its value rather than snapping) — small touch, disproportionate
  effect on "does this feel like a real audio tool."
- Respect `prefers-reduced-motion` — don't skip this because the rest of the ask is maximalist;
  it's a one-line media query condition on the animation config, not a design compromise.

### 3.5 Explicit non-goals for this section

- Not building a full multi-track DAW timeline — segments are sequential, not overlappable by the
  user; the "timeline" is really a linear rack.
- Not exposing the raw compressor/limiter parameters from §2 as user-tunable controls in v1 — ship
  sane defaults first, add an "advanced" reveal only if it turns out to be needed after living with
  the defaults.
- Not redesigning `RuntimeConfigPage`/`IntegrationsPage`/`VoiceLibraryPage` as part of this pass —
  scope is the OmniVoice generation surface specifically; the rest of the app can pick up the new
  motion/visual language incrementally later.

## 4. Suggested implementation order

1. `omnivoice_engine.py` swap manager (§1.1) + `/omnivoice/audition` and `/omnivoice/stitch`
   routes (§1.2), tested via curl/Postman before any UI exists — validates the backend contract
   independent of frontend work.
2. Audio post-processing pipeline (§2) as a standalone, unit-testable module (feed it synthetic
   segments with deliberately mismatched levels, assert the output is within a tolerance band) —
   easy to verify correctness without needing real OmniVoice generations for every test run.
3. `AccentBank` data (curated sentence content — already partially exists from
   `PLAN_omnivoice_integration.md` §1a/§5a's validated AU sentences; needs the same curation pass
   for any additional accents before they're offered).
4. Frontend: `EngineSelector` + `AccentBank` (lower risk, less new-dependency surface) before
   `SegmentRack`/`StitchPreview` (the wavesurfer/framer-motion-heavy pieces) — validates the
   engine-choice/job-kickoff flow before investing in the visualization layer.
5. `SegmentRack`, `StitchPreview`, `GenerationProgress` — the actual "VST-level" surface.

## 5. Decisions (settled 2026-07-03, were open questions in an earlier draft of this doc)

1. **Compressor: hand-rolled numpy, not `pedalboard`.** No new runtime dependency for §2.2 — a
   small soft-knee envelope-follower/gain-computer function, tuned for speech. If it turns out to
   sound bad on real segments during implementation, `pedalboard` (Spotify's audio-effects
   library, proper Compressor/Limiter/Gain chain, C++-backed) is the documented fallback, but
   start hand-rolled.
2. **`candidate_id` cache: in-memory dict, single-user, no persistence.** TTL'd dict keyed by
   `candidate_id`, cleared on the next `/omnivoice/audition` call (§1.2). Confirmed this is a
   single-user local tool with no concurrent-job requirement — a page refresh or brief service
   hiccup losing not-yet-picked candidates is an acceptable tradeoff for the simplicity, not a bug
   to design around.
3. **`AccentBank` preview audio: repo-committed, not build-time generated.** Curated by human
   listen-through, same process and same files as the existing `audio/omnivoice_au_*.wav`
   validation artifacts (or a promoted subset of them) — zero build-time cost, zero flakiness risk
   from the ~25% broken-output rate leaking into every image build.
4. **CC-BY-NC license: deferred, not a blocker.** Keep building while the repo stays
   personal/pre-FOSS. Revisit with an actual legal/human judgment call only once a commercial
   Hermes tier is genuinely on the table — not before, and not as a precondition for continuing
   this plan's implementation work.
