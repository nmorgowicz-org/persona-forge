// StitchPlanSession: the interface StitchEditorBody edits through, so it behaves identically
// whether the plan being edited is the live durable Studio session (zustand-backed) or a local
// draft (quick-insert modal) that never touches the store until explicitly committed. See
// docs/archive/stitch-studio/20260920-stitch_studio_ux_execution_plan.md "Session contract" -- later packets
// depend on these exact names/signatures.
import { useCallback, useMemo, useRef, useState } from 'react'
import { useAppStore, type StitchPlanClip, type StitchPlanDsp } from '@/store'
import {
  cloneStitchPlanState,
  removeClipFromStitchPlan,
  reorderStitchPlan,
  spliceStitchPlanClips,
  type StitchPlanState,
  type StitchRegionEdit,
} from '@/lib/stitchPlan'

export interface StitchPlanSession {
  plan: StitchPlanState
  setClips(updater: StitchPlanClip[] | ((clips: StitchPlanClip[]) => StitchPlanClip[])): void
  updateClip(clipId: string, patch: Partial<StitchPlanClip>): void
  removeClip(clipId: string): void
  reorderClip(from: number, to: number): void
  insertClips(clips: StitchPlanClip[], afterClipId?: string | null): void
  setPaddingAt(index: number, milliseconds: number): void
  setPadding(values: number[]): void
  setDsp(patch: Partial<StitchPlanDsp>): void
  setRegionEdits(clipId: string, edits: StitchRegionEdit[]): void
  reset(): void
}

/** Live, durable Studio session -- every edit is a zustand write, visible immediately to every
 * other store-backed consumer (e.g. re-opening Stitch Studio from a different page). */
export function useStoreStitchPlanSession(): StitchPlanSession {
  const clips = useAppStore((s) => s.ovStitchPlanClips)
  const paddingMs = useAppStore((s) => s.ovStitchPlanPaddingMs)
  const dsp = useAppStore((s) => s.ovStitchPlanDsp)
  const regionEditsByClip = useAppStore((s) => s.ovStitchRegionEditsByClip)
  const setClipsStore = useAppStore((s) => s.setOvStitchPlanClips)
  const updateClipStore = useAppStore((s) => s.updateOvStitchPlanClip)
  const removeClipStore = useAppStore((s) => s.removeOvStitchPlanClip)
  const reorderClipStore = useAppStore((s) => s.reorderOvStitchPlanClip)
  const setPaddingAtStore = useAppStore((s) => s.setOvStitchPlanPaddingAt)
  const setPaddingStore = useAppStore((s) => s.setOvStitchPlanPaddingMs)
  const setDspStore = useAppStore((s) => s.setOvStitchPlanDsp)
  const setRegionEditsStore = useAppStore((s) => s.setOvStitchRegionEdits)

  const plan = useMemo<StitchPlanState>(
    () => ({ clips, paddingMs, dsp, regionEditsByClip }),
    [clips, paddingMs, dsp, regionEditsByClip],
  )

  const reset = useCallback(() => {
    setClipsStore([])
    setPaddingStore([])
    for (const clipId of Object.keys(useAppStore.getState().ovStitchRegionEditsByClip)) {
      setRegionEditsStore(clipId, [])
    }
  }, [setClipsStore, setPaddingStore, setRegionEditsStore])

  const insertClips = useCallback((clips: StitchPlanClip[], afterClipId?: string | null) => {
    // One zustand set so the clip splice and the padding resize commit together: the seam
    // index is resolved against the freshest state inside the set, so a clip or padding edit
    // landing between a batch insert's fetches and its commit is never silently overwritten.
    useAppStore.setState((s) => {
      const next = spliceStitchPlanClips(
        {
          clips: s.ovStitchPlanClips,
          paddingMs: s.ovStitchPlanPaddingMs,
          dsp: s.ovStitchPlanDsp,
          regionEditsByClip: s.ovStitchRegionEditsByClip,
        },
        clips,
        afterClipId,
      )
      return { ovStitchPlanClips: next.clips, ovStitchPlanPaddingMs: next.paddingMs }
    })
  }, [])

  return useMemo<StitchPlanSession>(
    () => ({
      plan,
      setClips: setClipsStore,
      updateClip: updateClipStore,
      removeClip: removeClipStore,
      reorderClip: reorderClipStore,
      insertClips,
      setPaddingAt: setPaddingAtStore,
      setPadding: setPaddingStore,
      setDsp: setDspStore,
      setRegionEdits: setRegionEditsStore,
      reset,
    }),
    [plan, setClipsStore, updateClipStore, removeClipStore, reorderClipStore, insertClips, setPaddingAtStore, setPaddingStore, setDspStore, setRegionEditsStore, reset],
  )
}

/** Local quick-insert draft -- deep-clones `initial` exactly once (on first render of whatever
 * component instance calls this hook) and never writes to zustand. The caller commits by
 * reading `.plan` and passing it to `replaceOvStitchPlan` explicitly. */
export function useDraftStitchPlanSession(initial: StitchPlanState): StitchPlanSession {
  const initialRef = useRef<StitchPlanState | null>(null)
  if (initialRef.current === null) initialRef.current = cloneStitchPlanState(initial)
  const [plan, setPlan] = useState<StitchPlanState>(initialRef.current)

  const setClips = useCallback((updater: StitchPlanClip[] | ((clips: StitchPlanClip[]) => StitchPlanClip[])) => {
    setPlan((prev) => ({ ...prev, clips: typeof updater === 'function' ? updater(prev.clips) : updater }))
  }, [])

  const updateClip = useCallback((clipId: string, patch: Partial<StitchPlanClip>) => {
    setPlan((prev) => ({
      ...prev,
      clips: prev.clips.map((c) => (c.clipId === clipId ? { ...c, ...patch } : c)),
    }))
  }, [])

  const removeClip = useCallback((clipId: string) => {
    setPlan((prev) => removeClipFromStitchPlan(prev, clipId))
  }, [])

  const reorderClip = useCallback((from: number, to: number) => {
    setPlan((prev) => reorderStitchPlan(prev, from, to))
  }, [])

  const insertClips = useCallback((clips: StitchPlanClip[], afterClipId?: string | null) => {
    // One local setState so clips and padding commit together in the draft as well.
    setPlan((prev) => spliceStitchPlanClips(prev, clips, afterClipId))
  }, [])

  const setPaddingAt = useCallback((index: number, milliseconds: number) => {
    setPlan((prev) => {
      const next = [...prev.paddingMs]
      next[index] = milliseconds
      return { ...prev, paddingMs: next }
    })
  }, [])

  const setPadding = useCallback((values: number[]) => {
    setPlan((prev) => ({ ...prev, paddingMs: values }))
  }, [])

  const setDsp = useCallback((patch: Partial<StitchPlanDsp>) => {
    setPlan((prev) => ({ ...prev, dsp: { ...prev.dsp, ...patch } }))
  }, [])

  const setRegionEdits = useCallback((clipId: string, edits: StitchRegionEdit[]) => {
    setPlan((prev) => {
      const next = { ...prev.regionEditsByClip }
      if (edits.length) next[clipId] = edits
      else delete next[clipId]
      return { ...prev, regionEditsByClip: next }
    })
  }, [])

  const reset = useCallback(() => {
    setPlan((prev) => ({ clips: [], paddingMs: [], dsp: prev.dsp, regionEditsByClip: {} }))
  }, [])

  return useMemo<StitchPlanSession>(
    () => ({ plan, setClips, updateClip, removeClip, reorderClip, insertClips, setPaddingAt, setPadding, setDsp, setRegionEdits, reset }),
    [plan, setClips, updateClip, removeClip, reorderClip, insertClips, setPaddingAt, setPadding, setDsp, setRegionEdits, reset],
  )
}
