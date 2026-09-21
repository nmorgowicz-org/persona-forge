// Pure stitch-plan domain operations, shared by the zustand-backed Stitch Studio session
// and the quick-insert draft session (frontend/src/hooks/useStitchPlanSession.ts). No React,
// no zustand: every function here takes a plan and returns a new plan (or derived value).
//
// See docs/archive/stitch-studio/20260920-stitch_studio_ux_execution_plan.md "Locked interfaces" for the
// contract this module implements; later packets depend on these exact names/signatures.
import type { StitchPlanClip, StitchPlanDsp } from '@/store'
import type { StitchPlanRegionEdit } from '@/lib/api'

/** A region edit plus a UI-only id so it can be listed/removed before it is serialized into
 * a stitch-plan payload. `toPayloadRegionEdits` strips the id back out. */
export type StitchRegionEdit = StitchPlanRegionEdit & { id: string }
export type StitchRegionEditsByClip = Record<string, StitchRegionEdit[]>

export interface StitchPlanState {
  clips: StitchPlanClip[]
  paddingMs: number[]
  dsp: StitchPlanDsp
  regionEditsByClip: StitchRegionEditsByClip
}

export interface StitchDurations {
  /** Sum of trimmed clip durations only -- excludes inter-clip gaps. Drives the hard
   * reference-voice minimum; padding must never be able to satisfy it. */
  sourceMaterialMs: number
  /** Sum of inter-clip gaps (paddingMs). */
  spacingMs: number
  /** Total crossfade overlap subtracted from the rendered length -- only present when
   * clips actually have adjacent seams to crossfade across. */
  crossfadeOverlapMs: number
  /** sourceMaterialMs + spacingMs - crossfadeOverlapMs, clamped to >= 0. */
  renderedMs: number
}

/** Deep-clones a plan so a draft session can mutate its own copy without aliasing the
 * committed store state (or vice versa). */
export function cloneStitchPlanState(plan: StitchPlanState): StitchPlanState {
  return {
    clips: plan.clips.map((clip) => ({ ...clip })),
    paddingMs: [...plan.paddingMs],
    dsp: { ...plan.dsp },
    regionEditsByClip: Object.fromEntries(
      Object.entries(plan.regionEditsByClip).map(([clipId, edits]) => [
        clipId,
        edits.map((edit) => ({ ...edit })),
      ]),
    ),
  }
}

/** A clip's audible duration after trims -- never negative, never below a 10ms floor so a
 * fully-trimmed clip still occupies a nonzero, selectable span. */
export function clipEffectiveDurationMs(clip: StitchPlanClip): number {
  const base = clip.durationMs ?? 0
  if (!base) return 0
  return Math.max(10, base - clip.trimStartMs - clip.trimEndMs)
}

/** Source material, spacing, crossfade overlap, and rendered length for a plan. Excludes
 * paddingMs from sourceMaterialMs (so gaps alone can never satisfy the reference-voice
 * minimum), and only subtracts crossfade overlap when there are adjacent clips to crossfade
 * across (a single clip has no seams). Every public duration is clamped to >= 0. */
export function computeStitchDurations(plan: StitchPlanState): StitchDurations {
  const sourceMaterialMs = Math.max(
    0,
    plan.clips.reduce((sum, clip) => sum + clipEffectiveDurationMs(clip), 0),
  )
  const spacingMs = Math.max(
    0,
    (plan.paddingMs ?? []).reduce((sum, ms) => sum + Math.max(0, ms), 0),
  )
  const seamCount = Math.max(0, plan.clips.length - 1)
  const crossfadeMs = Math.max(0, plan.dsp?.crossfadeMs ?? 0)
  const crossfadeOverlapMs = seamCount > 0 ? crossfadeMs * seamCount : 0
  const renderedMs = Math.max(0, sourceMaterialMs + spacingMs - crossfadeOverlapMs)
  return { sourceMaterialMs, spacingMs, crossfadeOverlapMs, renderedMs }
}

/** Punctuation-derived gap suggestion for the seam following a clip ending with `text`:
 * sentence-final punctuation suggests a longer pause, clause punctuation a medium pause,
 * otherwise a short default pause. */
export function suggestedGapMs(text: string): number {
  const trimmed = (text ?? '').trim()
  if (/[.!?]["')\]]?$/.test(trimmed)) return 520
  if (/[,;:]["')\]]?$/.test(trimmed)) return 260
  return 90
}

/** One suggested gap per seam (clips.length - 1 values), derived from each clip's own
 * trailing punctuation. */
export function suggestedPaddingForClips(clips: StitchPlanClip[]): number[] {
  return clips.slice(0, -1).map((clip) => suggestedGapMs(clip.text ?? ''))
}

export interface StitchClipRangeMs {
  clipId: string
  startMs: number
  endMs: number
}

/** Each clip's approximate [startMs, endMs) span within the *rendered* arrangement, derived
 * client-side from trims, gaps, and the flat per-seam crossfade duration -- the same terms
 * `computeStitchDurations` already uses for `renderedMs`. This is an approximation, not a
 * sample-accurate readout of the backend's actual render (the backend's DSP chain can shift
 * boundaries by effects this module intentionally never models); callers scale it against the
 * real rendered preview's measured duration before using it to seek/bound playback. */
export function computeClipRangesMs(plan: StitchPlanState): StitchClipRangeMs[] {
  const crossfadeMs = Math.max(0, plan.dsp?.crossfadeMs ?? 0)
  let cursor = 0
  return plan.clips.map((clip, i) => {
    if (i > 0) cursor += (plan.paddingMs[i - 1] ?? 0) - crossfadeMs
    const startMs = Math.max(0, cursor)
    const endMs = startMs + clipEffectiveDurationMs(clip)
    cursor = endMs
    return { clipId: clip.clipId, startMs, endMs }
  })
}

/** Moves the clip at `from` to `to`. Seam semantics are preserved: padding values stay
 * attached to their timeline boundary (index), not to the clip pair that originally sat
 * there, so reordering clips changes clip order without moving gaps. */
export function reorderStitchPlan(plan: StitchPlanState, from: number, to: number): StitchPlanState {
  if (
    from === to ||
    from < 0 ||
    to < 0 ||
    from >= plan.clips.length ||
    to >= plan.clips.length
  ) {
    return plan
  }
  const clips = [...plan.clips]
  const [moved] = clips.splice(from, 1)
  clips.splice(to, 0, moved)
  return { ...plan, clips }
}

/** Removes a clip and merges its two adjacent gaps into one: drops the seam that followed
 * it, or (when removing the final clip) the seam that preceded it, so the padding array
 * stays aligned to clips.length - 1. Also drops that clip's region edits. */
export function removeClipFromStitchPlan(plan: StitchPlanState, clipId: string): StitchPlanState {
  const idx = plan.clips.findIndex((clip) => clip.clipId === clipId)
  if (idx === -1) return plan
  const clips = plan.clips.filter((clip) => clip.clipId !== clipId)
  const paddingMs = [...plan.paddingMs]
  if (idx < paddingMs.length) paddingMs.splice(idx, 1)
  else if (idx - 1 >= 0) paddingMs.splice(idx - 1, 1)
  const regionEditsByClip = { ...plan.regionEditsByClip }
  delete regionEditsByClip[clipId]
  return { ...plan, clips, paddingMs, regionEditsByClip }
}

/** Strips the UI-only `id` field so durable region edits can be serialized into a
 * StitchPlanPayload clip's `edits` array. */
export function toPayloadRegionEdits(edits: StitchRegionEdit[]): StitchPlanRegionEdit[] {
  return edits.map(({ id: _id, ...rest }) => rest)
}

/** Deterministic fingerprint of everything that changes rendered audio: clip audio
 * identity/trims/fades/text/prosody, seam padding, DSP, and region edits. Used to decide
 * when a live preview must re-render and to tag the rendered preview for automation
 * (`stitch-preview-ready`'s `data-plan-hash`). Not a security hash -- collisions are
 * acceptable only in the sense that two structurally-identical plans should collide. */
export function hashStitchPlan(plan: StitchPlanState): string {
  return JSON.stringify({
    clips: plan.clips.map((c) => [
      c.clipId,
      c.trimStartMs,
      c.trimEndMs,
      c.fadeInMs,
      c.fadeOutMs,
      c.text,
      c.prosodyMode,
    ]),
    paddingMs: plan.paddingMs,
    dsp: plan.dsp,
    regionEditsByClip: plan.regionEditsByClip,
  })
}
