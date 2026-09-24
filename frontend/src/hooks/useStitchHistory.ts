// Stitch editor undo/redo (T2): bounded, in-memory past/future stacks of complete
// StitchPlanState snapshots. An explicit, owner-approved exception to the 2026-09-20
// "no undo/history" constraint -- see docs/plans/20260922-premium_audio_plugin_ux.md T2.
//
// Recording is driven by the *store*, not by the editor's callbacks, so any change to the four
// plan slices becomes an entry whatever code path made it -- including the quick-insert
// commit, which replaces the plan wholesale. A quick-insert *draft* keeps its edits in local
// state and never touches the store, so drafts are structurally outside history until they are
// committed, which is exactly the contract the plan asks for. The stacks live in memory only:
// they are never serialized, so a reload starts a fresh history.
//
// Continuous edits coalesce. A trim/fade handle drag commits once on pointerup, but a numeric
// drag-scrub writes on every pointermove; both have to be one entry. A change that differs from
// the previous plan only in one control's numeric fields therefore merges into the entry the
// gesture already opened, and any other kind of change (or a quiet gap, or an undo) closes it.
import { useMemo } from 'react'
import { create } from 'zustand'
import { useAppStore } from '@/store'
import { type StitchPlanState } from '@/lib/stitchPlan'

/** Undo steps kept. Snapshots are structurally shared with the plan they came from, so an
 * entry costs a handful of references plus whatever the edit itself allocated. */
const HISTORY_CAP = 100
/** A numeric burst whose changes arrive further apart than this is a new gesture. */
const NUMERIC_MERGE_MS = 800

type Delta = { kind: 'numeric'; target: string } | { kind: 'other' }
const OTHER: Delta = { kind: 'other' }

/** The dsp slice is a flat record of numbers; only its own keys can differ. */
function changedDspKeys(prev: StitchPlanState['dsp'], next: StitchPlanState['dsp']): (keyof StitchPlanState['dsp'])[] {
  const keys = new Set([...Object.keys(prev), ...Object.keys(next)] as (keyof StitchPlanState['dsp'])[])
  const changed: (keyof StitchPlanState['dsp'])[] = []
  for (const key of keys) if (prev[key] !== next[key]) changed.push(key)
  return changed
}

/** Fields a drag-scrub or a slider writes continuously. */
const CONTINUOUS_CLIP_KEYS = new Set(['trimStartMs', 'trimEndMs', 'fadeInMs', 'fadeOutMs'])

function planOf(state: {
  ovStitchPlanClips: StitchPlanState['clips']
  ovStitchPlanPaddingMs: number[]
  ovStitchPlanDsp: StitchPlanState['dsp']
  ovStitchRegionEditsByClip: StitchPlanState['regionEditsByClip']
}): StitchPlanState {
  return {
    clips: state.ovStitchPlanClips,
    paddingMs: state.ovStitchPlanPaddingMs,
    dsp: state.ovStitchPlanDsp,
    regionEditsByClip: state.ovStitchRegionEditsByClip,
  }
}

/** Identity comparison, not deep equality: every store mutation allocates new objects for what
 * it changed and keeps the identity of what it did not, so this is both exact and cheap -- and
 * it never has to touch a clip's base64 audio. */
function samePlan(a: StitchPlanState, b: StitchPlanState): boolean {
  if (a.clips === b.clips && a.paddingMs === b.paddingMs && a.dsp === b.dsp && a.regionEditsByClip === b.regionEditsByClip) return true
  if (a.clips.length !== b.clips.length || a.paddingMs.length !== b.paddingMs.length) return false
  for (let i = 0; i < a.clips.length; i++) if (a.clips[i] !== b.clips[i]) return false
  for (let i = 0; i < a.paddingMs.length; i++) if (a.paddingMs[i] !== b.paddingMs[i]) return false
  if (a.dsp !== b.dsp && changedDspKeys(a.dsp, b.dsp).length > 0) return false
  if (a.regionEditsByClip !== b.regionEditsByClip) {
    const keys = new Set([...Object.keys(a.regionEditsByClip), ...Object.keys(b.regionEditsByClip)])
    for (const key of keys) if (a.regionEditsByClip[key] !== b.regionEditsByClip[key]) return false
  }
  return true
}

function onlyContinuousClipFieldsChanged(a: StitchPlanState['clips'][number], b: StitchPlanState['clips'][number]): boolean {
  for (const key of Object.keys(a) as (keyof typeof a)[]) {
    if (CONTINUOUS_CLIP_KEYS.has(key as string)) continue
    if (a[key] !== b[key]) return false
  }
  return true
}

/** Which continuous control this change belongs to, if it is a continuous change at all. */
function classifyDelta(prev: StitchPlanState, next: StitchPlanState): Delta {
  if (prev.clips.length !== next.clips.length) return OTHER
  if (prev.paddingMs.length !== next.paddingMs.length) return OTHER
  if (prev.regionEditsByClip !== next.regionEditsByClip) {
    const keys = new Set([...Object.keys(prev.regionEditsByClip), ...Object.keys(next.regionEditsByClip)])
    for (const key of keys) if (prev.regionEditsByClip[key] !== next.regionEditsByClip[key]) return OTHER
  }

  let changedClipId: string | null = null
  for (let i = 0; i < prev.clips.length; i++) {
    const a = prev.clips[i]
    const b = next.clips[i]
    if (a === b) continue
    if (changedClipId !== null) return OTHER
    if (!onlyContinuousClipFieldsChanged(a, b)) return OTHER
    changedClipId = b.clipId
  }

  let changedGapIndex: number | null = null
  for (let i = 0; i < prev.paddingMs.length; i++) {
    if (prev.paddingMs[i] === next.paddingMs[i]) continue
    if (changedGapIndex !== null) return OTHER
    changedGapIndex = i
  }

  const dspKeys = prev.dsp === next.dsp ? [] : changedDspKeys(prev.dsp, next.dsp)
  if (dspKeys.length > 1) return OTHER
  const changedDspKey: string | null = dspKeys[0] ?? null

  const touched = [changedClipId !== null, changedGapIndex !== null, changedDspKey !== null].filter(Boolean).length
  if (touched !== 1) return OTHER
  if (changedClipId !== null) return { kind: 'numeric', target: `clip:${changedClipId}` }
  if (changedGapIndex !== null) return { kind: 'numeric', target: `gap:${changedGapIndex}` }
  return { kind: 'numeric', target: `dsp:${changedDspKey}` }
}

interface PendingGroup {
  /** The plan as it was before the gesture started -- the state an undo returns to. */
  base: StitchPlanState
  target: string
  at: number
}

interface StitchHistoryStore {
  past: StitchPlanState[]
  future: StitchPlanState[]
  /** Open continuous gesture, not yet pushed onto `past`. */
  pending: PendingGroup | null
  undo(): void
  redo(): void
}

function pushBounded(past: StitchPlanState[], additions: StitchPlanState[]): StitchPlanState[] {
  if (additions.length === 0) return past
  const next = [...past, ...additions]
  return next.length > HISTORY_CAP ? next.slice(next.length - HISTORY_CAP) : next
}

/** Bumped while the history itself is writing the plan, so an undo is not recorded as an edit. */
let suppressDepth = 0

export const useStitchHistoryStore = create<StitchHistoryStore>((set, get) => ({
  past: [],
  future: [],
  pending: null,

  undo: () => {
    const { past, future, pending } = get()
    // An open gesture is a real entry: close it before unwinding so the first undo returns to
    // the pre-gesture value rather than leaving a mid-drag state behind.
    const closed = pending ? pushBounded(past, [pending.base]) : past
    if (closed.length === 0) return
    const target = closed[closed.length - 1]
    const current = planOf(useAppStore.getState())
    suppressDepth += 1
    try {
      useAppStore.getState().replaceOvStitchPlan(target)
    } finally {
      suppressDepth -= 1
    }
    set({ past: closed.slice(0, -1), future: [...future, current], pending: null })
  },

  redo: () => {
    const { past, future, pending } = get()
    if (future.length === 0) return
    const target = future[future.length - 1]
    const current = planOf(useAppStore.getState())
    suppressDepth += 1
    try {
      useAppStore.getState().replaceOvStitchPlan(target)
    } finally {
      suppressDepth -= 1
    }
    set({ past: pushBounded(pending ? pushBounded(past, [pending.base]) : past, [current]), future: future.slice(0, -1), pending: null })
  },
}))

function record(prev: StitchPlanState, next: StitchPlanState): void {
  const state = useStitchHistoryStore.getState()
  const delta = classifyDelta(prev, next)
  const now = performance.now()

  if (delta.kind === 'numeric' && state.pending && state.pending.target === delta.target && now - state.pending.at < NUMERIC_MERGE_MS) {
    useStitchHistoryStore.setState({ pending: { base: state.pending.base, target: delta.target, at: now } })
    return
  }

  const closing = state.pending ? [state.pending.base] : []
  if (delta.kind === 'numeric') {
    useStitchHistoryStore.setState({
      past: pushBounded(state.past, closing),
      future: [],
      pending: { base: prev, target: delta.target, at: now },
    })
    return
  }

  useStitchHistoryStore.setState({
    past: pushBounded(state.past, [...closing, prev]),
    future: [],
    pending: null,
  })
}

let installed = false

/** Subscribes once to the plan slices of the app store. Module scope, not a hook: the history
 * belongs to the plan, not to whichever editor instance happens to be mounted. */
function installRecorder(): void {
  if (installed) return
  installed = true
  let previous = planOf(useAppStore.getState())
  useAppStore.subscribe((state) => {
    const next = planOf(state)
    if (samePlan(previous, next)) {
      previous = next
      return
    }
    if (suppressDepth === 0) record(previous, next)
    previous = next
  })
}

installRecorder()

export interface StitchHistory {
  undo(): void
  redo(): void
  canUndo: boolean
  canRedo: boolean
  /** Undo steps available, including an open gesture. */
  depth: number
  redoDepth: number
}

export function useStitchHistory(): StitchHistory {
  const past = useStitchHistoryStore((s) => s.past)
  const future = useStitchHistoryStore((s) => s.future)
  const pending = useStitchHistoryStore((s) => s.pending)
  const undo = useStitchHistoryStore((s) => s.undo)
  const redo = useStitchHistoryStore((s) => s.redo)

  return useMemo(
    () => ({
      undo,
      redo,
      canUndo: past.length + (pending ? 1 : 0) > 0,
      canRedo: future.length > 0,
      depth: past.length + (pending ? 1 : 0),
      redoDepth: future.length,
    }),
    [past, future, pending, undo, redo],
  )
}
