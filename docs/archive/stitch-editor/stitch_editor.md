# Stitch Editor (VST-style timeline for Persona Forge / OmniVoice)

Status: COMPLETED (2026-07-04)

A VST-style timeline editor was added between OmniVoice "select takes" and
"commit stitch" so users can reorder clips, trim edges, insert silence,
control fades/compression, and preview live before committing a final stitch
or saving to the voice library.

## Context

Persona Forge's OmniVoice workflow originally allowed one-click stitching of
selected takes with no editing control: no reordering, no trimming of
generated padding, no silence insertion, and no fade/compression tuning.
Most of the DSP primitives already existed in `audio_post.py`, but had
hardcoded defaults and no override path.

The stitch editor was implemented as an intermediate timeline step — similar
to a DAW/VST clip view — to expose those controls without changing the
basic one-click flow.

## Implementation summary

### Backend: audio_post.py

Pure additions; no existing signature changes:

- `trim(audio, sr, start_ms, end_ms)` — clips head/tail; clamped to never
  produce negative-length output.
- `apply_fades(audio, sr, fade_in_ms, fade_out_ms)` — per-clip user-controlled
  fades, applied before any joining.
- `silence(sr, duration_ms)` — np.zeros helper for inter-clip padding.
- `concat_with_padding(segments, sr, padding_ms, crossfade_ms)` — joins
  segments using either:
  - silence + short fade (padding_ms[i] > 0), or
  - crossfade (padding_ms[i] == 0), reusing the existing fade-curve logic.
- `stitch_segments` was extended with optional kwargs (`padding_ms`, `trims`,
  `fades`, `compress_params`), all defaulting to original behavior to keep
  the current callers unchanged.

Per-segment processing order: trim → compress (if enabled) →
normalize_rms(segment_target_dbfs) → apply_fades → concat_with_padding →
limit_peak → normalize_rms(final) → limit_peak.

### Backend: "stitch plan" data shape

A JSON-serializable dict travels in request bodies and is stored verbatim
in voice_library meta.json for reproducibility. No new persisted entity.

StitchPlan:
- clips: list of:
  - ref: { segment_id } or { candidate_id } (exactly one)
  - trim_start_ms, trim_end_ms, fade_in_ms, fade_out_ms
- padding_ms: list[float], length == len(clips) - 1 (silence after clip i; 0 = crossfade)
- crossfade_ms: float (used where padding_ms[i] == 0)
- segment_target_dbfs, final_target_dbfs, final_ceiling_db: float
- compress: { threshold_db, ratio, attack_ms, release_ms } | null

Clip refs resolve through the existing segment-library / ephemeral-cache
mechanisms; no new clip-storage layer was introduced.

### Backend API changes

Both endpoints remain backward-compatible:

- POST /omnivoice/stitch — now accepts:
  - current flat shape (segment_ids / selections), or
  - new `stitch_plan` key (new code path).
- POST /omnivoice/save — same dual-mode; when stitch_plan is used, it is
  persisted verbatim into voice_library's meta.json under
  selections["stitch_plan"].

New helpers:
- `_resolve_stitch_plan(data)` — validates/interprets stitch_plan and
  resolves clip refs into (wav, sr) tuples.
- `_resolve_one_clip_ref(ref)` — factored out from `_resolve_omnivoice_clips`
  so both flat-list and stitch-plan paths share one implementation.

omnivoice_engine.stitch_selected accepts an optional `plan=` kwarg; `plan=None`
behaves byte-identical to the original.

### Voice library

No changes to voice_library.py itself. stitch_plan is stored inside the
existing `selections` dict in meta.json.

Design note: only segment_id-based plans are durably re-editable; candidate_id
refs live in an ephemeral in-memory cache and are lost after restart/eviction.
A future "reopen saved voice in editor" feature should nudge users toward
locking clips into the segment library first.

### Frontend: store

New store interfaces and fields in frontend/src/store.ts:

- StitchPlanClip: client clip entry (clipId, ref, text, sourceAudioBase64,
  sampleRate, trim/fade params).
- StitchPlanDsp: global DSP settings (segment/final targets, ceiling,
  crossfade, compression).
- Store fields:
  - ovStitchPlanClips
  - ovStitchPlanPaddingMs (length = clips.length - 1)
  - ovStitchPlanDsp
  - ovStitchEditorOpen
  - ovStitchPreviewUrl, ovStitchPreviewBlob
  - ovIsRenderingPreview

New actions: setOvStitchPlanClips, reorderOvStitchPlanClip,
updateOvStitchPlanClip, removeOvStitchPlanClip,
setOvStitchPlanPaddingAt, setOvStitchPlanDsp, setOvStitchEditorOpen.

Existing fields (ovStitchedUrl, ovStitchedBlob, ovSavedVoiceId) preserved
to represent the final committed result, distinct from editor previews.

### Frontend: entry point (segment rack → stitch editor)

"Stitch all" was updated to offer an "Open stitch editor" entry point:

- Validates every row has a selected take.
- Builds ovStitchPlanClips from segmentRack (one per row, candidate_id
  refs, all trim/fade zeroed).
- Sets ovStitchPlanPaddingMs to all-zero (default crossfade behavior).
- Opens the editor (ovStitchEditorOpen = true).

A "quick stitch with defaults" path was kept for users who prefer the
original one-click flow.

### Frontend: StitchTimeline

New component (frontend/src/components/StitchTimeline.tsx) provides a
proportional horizontal timeline:

- Clips sized by post-trim duration relative to total.
- Reorder: initially up/down buttons; later framer-motion Reorder.Group/Item.
- Per-clip:
  - Trim steppers at each edge.
  - Fade-in/fade-out controls.
  - Visual indicators (fade overlays, cropped peaks).
- Gaps:
  - Visually distinct segments between clips, sized by padding_ms[i].
  - +/- steppers for gap length.
- Numeric inputs provided alongside any drag controls for precision.
- "Add from library" dropdown in timeline header to insert SegmentMeta-based
  clips at the end.

Reuses computePeaks (decode once per clip, memoize) and Waveform's visual
style; no new DSP implemented client-side.

### Frontend: DSP controls panel

Compact panel aligned with the existing advanced-options pattern:
- Segment/final target level.
- Final ceiling.
- Crossfade length (where gap padding is 0).
- Compression: on/off, threshold, ratio.
- Attack/release remain at DSP defaults.

### Frontend: live preview

- POST /omnivoice/stitch is called with stitch_plan via renderStitchPlan().
- Debounced re-render (400–600ms after last edit).
- While rendering:
  - Last-good preview audio is retained.
  - "Preview stale" indicator is shown.
- Server is authoritative for audio; client-side visuals (trim/padding)
  are approximations only.

### Frontend: handleStitch / handleSave

- handleStitch ("Render/commit" in editor) builds StitchPlanPayload,
  calls renderStitchPlan, sets ovStitchedUrl/ovStitchedBlob.
- handleSave passes stitch_plan into /omnivoice/save and persists it.

## Changelog (delivery increments)

Each step was independently shippable.

1. audio_post.py primitives:
   - trim, apply_fades, concat_with_padding, silence, extended stitch_segments kwargs.
2. /omnivoice/stitch accepts stitch_plan:
   - _resolve_stitch_plan, _resolve_one_clip_ref, widened stitch_selected(plan=...).
3. /omnivoice/save accepts stitch_plan:
   - persisted into voice_library meta.json.
4. Frontend v1:
   - StitchTimeline with proportional layout and reorder buttons.
   - "Edit in timeline" entry point in PersonaForgePanel.
5. Frontend v2:
   - Per-clip trim steppers.
   - Gap padding controls.
   - Debounced live preview.
6. Frontend v3:
   - Fade-in/out per clip.
   - DSP controls panel (segment/final target, ceiling, crossfade, compression threshold/ratio).
7. Polish:
   - Drag-and-drop reorder (framer-motion Reorder.Group/Item).
   - "Add from library" dropdown to insert segment-based clips into timeline.

## Design decisions

Decisions already taken and reflected in the implementation:

- Pure additions in audio_post.py:
  - No changes to existing signatures or defaults; original callers unaffected.
- Dual-mode endpoints:
  - Both /omnivoice/stitch and /omnivoice/save accept either flat-list or
    stitch_plan; flat-list remains stable for non-editor callers.
- Server-authoritative audio:
  - No client-side DSP duplication; timeline only approximates edits visually.
  - A "preview stale" indicator handles the gap between edits and last render.
- Ephemeral candidate_id plans:
  - Allowed for flexibility; only segment_id-based plans are considered
    durably re-editable.
- Compression complexity:
  - Only threshold, ratio, and on/off exposed in UI; attack/release left
    at DSP defaults.
- compress() performance:
  - Known to be a per-sample Python loop.
  - Debounce on re-renders is the chosen mitigation; no additional
    pipeline-staging complexity for v1.
- Padding as silence:
  - Implemented with a small fade into/out of the silence to avoid clicks,
    separate from user-set clip fades.

## Related Persona Forge polish

The following smaller Persona Forge changes were implemented and deployed
alongside the stitch editor (as of 2026-07-04):

- "Autoplay takes" toggle moved from segments-only header into the always-visible
  advanced-options panel in PersonaForgePanel.tsx.
- Waveform x-axis always shows the clip's exact total duration at the far right
  (Waveform.tsx); last label right-aligns.
- Live-adjustable ASR match-score confidence threshold (min_match_score) wired
  through omnivoice_engine.run_omnivoice_job, /omnivoice/audition, and the
  advanced-options panel (slider with "Auto" pill).
- Segment text is click-to-edit directly in SegmentRackRow (not only via pencil icon).

## Notes for future work

- Implement "reopen a saved voice in the editor" for stitch_plan stored in
  meta.json; require or prompt locking clips into the segment library first.
- Optionally consolidate stitch code paths in app.py by making stitch_plan
  the canonical implementation with the flat-list path delegating into it.
- If compression latency becomes an issue, consider a preview optimization
  that skips re-running compression when its parameters haven't changed.
- Add end-to-end integration tests that:
  - send a stitch_plan via /omnivoice/stitch,
  - verify /omnivoice/save persists stitch_plan in meta.json,
  - compare preview vs. final audio under controlled conditions.
