// Owns the Stitch Studio live-preview lifecycle: debounced render scheduling, request
// abort/supersede guarding, and object-URL cleanup. Zustand owns none of this -- see
// docs/archive/stitch-studio/20260920-stitch_studio_ux_execution_plan.md "Preview contract". A hook instance
// is scoped to whichever editor mounts it (StitchEditorBody), so unmounting an editor
// (navigating away, closing quick insert) always revokes its preview URL and aborts any
// in-flight render.
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { hashStitchPlan, type StitchPlanState } from '@/lib/stitchPlan'
import { renderStitchPreview } from '@/lib/stitchPreview'

const DEBOUNCE_MS = 700

export interface StitchPreviewState {
  url: string | null
  blob: Blob | null
  isRendering: boolean
  isStale: boolean
  error: string | null
  renderNow(): Promise<void>
  scheduleRender(): void
  cancel(): void
  clear(): void
}

export function useStitchPreview(plan: StitchPlanState): StitchPreviewState {
  const [url, setUrl] = useState<string | null>(null)
  const [blob, setBlob] = useState<Blob | null>(null)
  const [isRendering, setIsRendering] = useState(false)
  const [isStale, setIsStale] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Always current -- renderNow must render whatever plan is live *right now*, not the plan
  // captured in whichever closure scheduled it (the debounce timer may be seconds stale).
  const planRef = useRef(plan)
  useLayoutEffect(() => {
    planRef.current = plan
  }, [plan])

  const seqRef = useRef(0)
  const urlRef = useRef<string | null>(null)
  const allocatedUrlsRef = useRef(new Set<string>())
  const debounceRef = useRef<number | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const lastHashRef = useRef('')

  const clearTimer = useCallback(() => {
    if (debounceRef.current != null) {
      window.clearTimeout(debounceRef.current)
      debounceRef.current = null
    }
  }, [])

  const swapUrl = useCallback((nextBlob: Blob | null) => {
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current)
      allocatedUrlsRef.current.delete(urlRef.current)
    }
    const nextUrl = nextBlob ? URL.createObjectURL(nextBlob) : null
    urlRef.current = nextUrl
    if (nextUrl) allocatedUrlsRef.current.add(nextUrl)
    setUrl(nextUrl)
    setBlob(nextBlob)
  }, [])

  const renderNow = useCallback(async (): Promise<void> => {
    clearTimer()
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    const seq = ++seqRef.current
    const currentPlan = planRef.current

    if (currentPlan.clips.length === 0) {
      swapUrl(null)
      setIsStale(false)
      setError(null)
      return
    }

    setIsRendering(true)
    try {
      const nextBlob = await renderStitchPreview(currentPlan, controller.signal)
      if (seq !== seqRef.current) return // superseded by a newer render while awaiting
      swapUrl(nextBlob)
      setIsStale(false)
      setError(null)
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      if (seq === seqRef.current) {
        setError(err instanceof Error ? err.message : 'Preview render failed.')
      }
    } finally {
      if (seq === seqRef.current) setIsRendering(false)
    }
  }, [clearTimer, swapUrl])

  const scheduleRender = useCallback(() => {
    clearTimer()
    setIsStale(true)
    setError(null)
    debounceRef.current = window.setTimeout(() => {
      debounceRef.current = null
      void renderNow()
    }, DEBOUNCE_MS)
  }, [clearTimer, renderNow])

  const cancel = useCallback(() => {
    clearTimer()
    abortRef.current?.abort()
    seqRef.current++ // invalidate any response that was already in flight
    setIsRendering(false)
  }, [clearTimer])

  const clear = useCallback(() => {
    cancel()
    lastHashRef.current = ''
    swapUrl(null)
    setIsStale(true)
    setError(null)
    setIsRendering(false)
  }, [cancel, swapUrl])

  const hash = useMemo(() => hashStitchPlan(plan), [plan])

  useEffect(() => {
    if (hash === lastHashRef.current) return
    lastHashRef.current = hash
    if (plan.clips.length === 0) {
      cancel()
      swapUrl(null)
      setIsStale(false)
      setError(null)
      return
    }
    scheduleRender()
    // Only the plan's fingerprint should retrigger scheduling -- scheduleRender/cancel/
    // swapUrl are stable callbacks that would otherwise cause redundant re-subscriptions.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hash])

  // Unmount: revoke every URL created before React could commit its latest URL state, abort
  // any in-flight render, and invalidate any late result.
  const dispose = useCallback(() => {
    clearTimer()
    abortRef.current?.abort()
    seqRef.current++
    for (const objectUrl of allocatedUrlsRef.current) URL.revokeObjectURL(objectUrl)
    allocatedUrlsRef.current.clear()
    urlRef.current = null
  }, [clearTimer])
  useEffect(() => () => dispose(), [dispose])

  return { url, blob, isRendering, isStale, error, renderNow, scheduleRender, cancel, clear }
}
