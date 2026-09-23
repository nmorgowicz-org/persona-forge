import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { AnimatePresence, motion, MotionConfig, Reorder } from 'motion/react'
import { ChevronUp, ChevronDown, Loader2, Play, Gauge, RotateCcw, Minus, Plus, Maximize2 } from 'lucide-react'
import { type StitchPlanClip, type StitchPlanDsp } from '@/store'
import {
  getStitchPacingTargets,
  type StitchPlanPayload,
  type SegmentMeta,
  type VoiceMeta,
} from '@/lib/api'
import {
  clipEffectiveDurationMs,
  computeClipRangesMs,
  hashStitchPlan,
  suggestedGapMs,
  type StitchPlanState,
  type StitchRegionEdit,
} from '@/lib/stitchPlan'
import { useElementWidth } from '@/hooks/useElementWidth'
import { type StitchPlanSession } from '@/hooks/useStitchPlanSession'
import { useStitchTransport, type StitchTransport } from '@/hooks/useStitchTransport'
import { planStateToPayload } from '@/lib/stitchPreview'
import { useStitchPreview } from '@/hooks/useStitchPreview'
import { SegmentBrowserModal, type SegmentBrowserModalController } from './stitch/SegmentBrowserModal'
import { useDragScrubValue, parseNumericText } from '@/hooks/useDragScrubValue'
import { cn } from '@/lib/utils'
import { TimelineRuler } from './stitch/TimelineRuler'
import { GapControl } from './stitch/GapControl'
import { StitchClipCard } from './stitch/StitchClipCard'
import { ReferenceReadiness } from './stitch/ReferenceReadiness'

// Helper for reduced motion
const useReducedMotion = () => {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (media.matches) setReduced(true)
    const listener = (e: MediaQueryListEvent) => setReduced(e.matches)
    media.addEventListener('change', listener)
    return () => media.removeEventListener('change', listener)
  }, [])
  return reduced
}


/* ---------- helpers ---------- */

type RegionEdit = StitchRegionEdit

function clampMs(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, Math.round(v)))
}

const MIN_PPS = 8
const MAX_PPS = 400
const DEFAULT_PPS = 60
const MIN_CLIP_PX = 160
const RAIL_PADDING_PX = 32

function clampPps(v: number): number {
  return Math.max(MIN_PPS, Math.min(MAX_PPS, v))
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  const tag = target.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable
}

// Shared empty array so cards with no region edits receive a stable prop and their
// React.memo comparison holds across plain re-renders.
const EMPTY_REGION_EDITS: RegionEdit[] = []


/* ---------- main component ---------- */

interface StitchTimelineProps {
  totalDurationMs: number
  isPreviewStale: boolean
  library: SegmentMeta[]
  onInsertFromLibrary: (segs: SegmentMeta[], afterClipId: string | null) => void
  session: StitchPlanSession
  voiceLibrary?: VoiceMeta[]
  onInsertVoiceFromLibrary?: (voices: VoiceMeta[], afterClipId: string | null) => void
  transport: StitchTransport
  /** Controller handle for the mounted segment-browser modal(s); the editor body uses it
   * to open the picker from the readiness guidance instead of a DOM click. */
  pickerRef?: { current: SegmentBrowserModalController | null }
}

export const StitchTimeline = memo(function StitchTimeline({
  totalDurationMs: _totalDurationMs,
  isPreviewStale: _isPreviewStale,
  library,
  onInsertFromLibrary,
  session,
  voiceLibrary,
  onInsertVoiceFromLibrary,
  transport,
  pickerRef,
}: StitchTimelineProps) {
  const { plan, reorderClip, removeClip, updateClip, setClips, setPaddingAt: setPadding, setPadding: setPaddingMs, setRegionEdits: onAddOrRemoveRegionEdit } = session
  const { clips, paddingMs, regionEditsByClip } = plan
  const [selectedClipId, setSelectedClipId] = useState<string | null>(null)
  const onAddRegionEdit = useCallback((clipId: string, edit: RegionEdit) => {
    onAddOrRemoveRegionEdit(clipId, [...(regionEditsByClip[clipId] ?? []), edit])
  }, [onAddOrRemoveRegionEdit, regionEditsByClip])
  const onRemoveRegionEdit = useCallback((clipId: string, editId: string) => {
    onAddOrRemoveRegionEdit(clipId, (regionEditsByClip[clipId] ?? []).filter((edit) => edit.id !== editId))
  }, [onAddOrRemoveRegionEdit, regionEditsByClip])
  const hasVoiceLibrary = (voiceLibrary?.length ?? 0) > 0 && !!onInsertVoiceFromLibrary

  // The selected clip may have been removed/reordered away; drop a selection that no longer
  // resolves so "insert after selection" silently falls back to "append at the end" instead of
  // silently targeting a stale id.
  useEffect(() => {
    if (selectedClipId && !clips.some((c) => c.clipId === selectedClipId)) setSelectedClipId(null)
  }, [clips, selectedClipId])

  // A single Reorder.Group drag always moves exactly one item (Framer Motion decomposes any
  // drag into a sequence of `next` arrays); the plan's domain layer (reorderStitchPlan) already
  // keeps gaps positional (indexed by seam, not by which clips flank them), so the correct and
  // simplest reconciliation for *any* permutation -- not just an adjacent one -- is to replace
  // the clip order outright rather than searching for a single (from, to) pair to hand to
  // reorderClip. The previous "find the first index that differs" search silently misattributed
  // which clip moved whenever a drag crossed more than one neighbor in a single gesture.
  const handleReorder = useCallback((next: StitchPlanClip[]) => setClips(next), [setClips])

  const moveClip = useCallback(
    (index: number, direction: 'left' | 'right') => {
      const to = direction === 'left' ? index - 1 : index + 1
      if (to < 0 || to >= clips.length) return
      reorderClip(index, to)
    },
    [clips.length, reorderClip],
  )

  const splitRegion = useCallback(
    (clipId: string, startMs: number, endMs: number) => {
      const index = clips.findIndex((clip) => clip.clipId === clipId)
      if (index === -1) return
      const clip = clips[index]
      const duration = clip.durationMs ?? 0
      if (!duration) return
      const effectiveDuration = clipEffectiveDurationMs(clip)
      const start = clampMs(startMs, 0, effectiveDuration)
      const end = clampMs(endMs, start + 10, effectiveDuration)
      const absoluteStart = clip.trimStartMs + start
      const absoluteEnd = clip.trimStartMs + end
      const parts: StitchPlanClip[] = []
      const addPart = (label: string, trimStartMs: number, trimEndMs: number) => {
        if (duration - trimStartMs - trimEndMs < 20) return
        parts.push({
          ...clip,
          clipId: `${clip.clipId}-${label}-${Date.now()}`,
          trimStartMs,
          trimEndMs,
          fadeInMs: 0,
          fadeOutMs: 0,
        })
      }
      addPart('pre', clip.trimStartMs, duration - absoluteStart)
      addPart('region', absoluteStart, duration - absoluteEnd)
      addPart('post', absoluteEnd, clip.trimEndMs)
      if (parts.length <= 1) return
      setClips((prev) => {
        const next = [...prev]
        next.splice(index, 1, ...parts)
        return next
      })
      const nextPadding = [...paddingMs]
      const inheritedGap = nextPadding[index] ?? 0
      nextPadding.splice(index, 0, ...new Array(parts.length - 1).fill(0))
      if (index + parts.length - 1 < nextPadding.length) nextPadding[index + parts.length - 1] = inheritedGap
      setPaddingMs(nextPadding.slice(0, Math.max(0, clips.length + parts.length - 2)))
    },
    [clips, paddingMs, setClips, setPaddingMs],
  )

  // Hooks must run unconditionally on every render — this used to sit after an early return
  // for the empty-timeline case, which threw "rendered more hooks than previous render" (React
  // error #310) the instant a first clip was inserted (0 clips -> hook skipped, 1+ clips -> hook
  // ran), crashing the page. Stitch Studio hits the empty state on first load, so it surfaced
  // this immediately; OmniVoice's editor rarely opened with zero clips, so it went unnoticed.
  const effectiveTotalMs = useMemo(() => {
    let sum = 0
    for (const c of clips) {
      sum += clipEffectiveDurationMs(c)
    }
    sum += (paddingMs || []).reduce((a, b) => a + b, 0)
    // Subtract per-seam crossfade overlap so the ruler total, clip ranges, and the
    // readiness bar's renderedMs (computeStitchDurations) agree on the same terms.
    const seamCount = Math.max(0, clips.length - 1)
    const crossfadeMs = Math.max(0, plan.dsp?.crossfadeMs ?? 0)
    sum -= seamCount > 0 ? crossfadeMs * seamCount : 0
    return Math.max(1, sum)
  }, [clips, paddingMs, plan.dsp?.crossfadeMs])

  // Each clip's approximate span in the rendered arrangement (Packet 7), scaled onto the
  // shared transport's actual measured audio duration -- the client-side estimate and the
  // backend's real render can differ slightly (crossfade/DSP), so this keeps seek and
  // clip-range playback from drifting past the end of the real audio.
  const clipRanges = useMemo(() => computeClipRangesMs(plan), [plan])
  const previewScale = transport.durationSec > 0 && effectiveTotalMs > 0
    ? (transport.durationSec * 1000) / effectiveTotalMs
    : 1
  const [shortcutsOpen, setShortcutsOpen] = useState(false)
  const reducedMotion = useReducedMotion()

  const autoPace = useCallback(() => {
    setPaddingMs(clips.slice(0, -1).map((clip) => {
      const text = (clip.text ?? '').trim()
      if (/[.!?]["')\]]?$/.test(text)) return 520
      if (/[,;:]["')\]]?$/.test(text)) return 260
      return 90
    }))
  }, [clips, setPaddingMs])

  // Zoom state: `manualPps === null` means "auto-fit" (pixelsPerSecond recomputed from the
  // scroll container's own visible width every time content changes) -- this preserves the
  // original always-fits behavior until the user explicitly zooms, at which point the Fit
  // button is the only way back to auto mode.
  const [scrollRef, containerWidthPx] = useElementWidth<HTMLDivElement>()
  const [manualPps, setManualPps] = useState<number | null>(null)
  const totalSeconds = effectiveTotalMs / 1000
  const autoFitPps = useMemo(() => {
    if (containerWidthPx <= 0 || totalSeconds <= 0) return DEFAULT_PPS
    return clampPps((containerWidthPx - RAIL_PADDING_PX) / totalSeconds)
  }, [containerWidthPx, totalSeconds])
  const pixelsPerSecond = manualPps ?? autoFitPps
  const zoomIn = useCallback(() => setManualPps(clampPps(pixelsPerSecond * 1.25)), [pixelsPerSecond])
  const zoomOut = useCallback(() => setManualPps(clampPps(pixelsPerSecond / 1.25)), [pixelsPerSecond])
  const zoomFit = useCallback(() => setManualPps(null), [])
  const onWheelZoom = useCallback(
    (e: React.WheelEvent<HTMLDivElement>) => {
      if (!(e.ctrlKey || e.metaKey)) return
      e.preventDefault()
      setManualPps(clampPps(pixelsPerSecond * (e.deltaY < 0 ? 1.1 : 1 / 1.1)))
    },
    [pixelsPerSecond],
  )
  const contentWidthPx = totalSeconds * pixelsPerSecond

  const handleSeek = useCallback(
    (arrangementSec: number) => transport.seek(arrangementSec * previewScale),
    [transport, previewScale],
  )

  // One stable playback callback shared by every card: the card supplies its own clipId at
  // click time, so memoized cards receive an identical function across plain re-renders
  // (only a real preview/range change, or the range becoming active, changes identity).
  const { playRange } = transport
  const handlePlayRange = useCallback((clipId: string) => {
    const index = clips.findIndex((c) => c.clipId === clipId)
    const range = index >= 0 ? clipRanges[index] : undefined
    if (!range) return
    playRange(clipId, (range.startMs * previewScale) / 1000, (range.endMs * previewScale) / 1000)
  }, [playRange, clips, clipRanges, previewScale])

  // Keyboard shortcuts for playback, selection, reorder, removal, and trim nudging -- scoped
  // to this component's lifetime and unconditionally skipped whenever the event target is an
  // editable control, so typing in a clip's text field, a gap's typed-value input, etc. is
  // never hijacked by these bindings. Space and `?` don't require a selected clip; the rest do.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (isEditableTarget(e.target)) return
      if ((e.code === 'Space' || e.key === ' ') && !e.repeat) {
        // The shortcuts dialog is open on a non-editable surface; Space there would
        // otherwise toggle arrangement playback behind the dialog.
        if (shortcutsOpen) return
        e.preventDefault()
        transport.toggle()
        return
      }
      if (e.key === '?' && !e.repeat) {
        e.preventDefault()
        setShortcutsOpen(true)
        return
      }
      if (!selectedClipId) return
      const index = clips.findIndex((c) => c.clipId === selectedClipId)
      if (index === -1) return
      if (e.key === 'ArrowRight' && !e.shiftKey) {
        e.preventDefault()
        const next = clips[index + 1]
        if (next) setSelectedClipId(next.clipId)
      } else if (e.key === 'ArrowLeft' && !e.shiftKey) {
        e.preventDefault()
        const prev = clips[index - 1]
        if (prev) setSelectedClipId(prev.clipId)
      } else if (e.key === 'ArrowRight' && e.shiftKey) {
        e.preventDefault()
        moveClip(index, 'right')
      } else if (e.key === 'ArrowLeft' && e.shiftKey) {
        e.preventDefault()
        moveClip(index, 'left')
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        e.preventDefault()
        removeClip(selectedClipId)
      } else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
        e.preventDefault()
        const clip = clips[index]
        if (!clip.durationMs) return
        const delta = (e.key === 'ArrowUp' ? 1 : -1) * (e.shiftKey ? 100 : 10)
        const maxStart = Math.max(0, clip.durationMs - 20 - clip.trimEndMs)
        const nextTrimStart = Math.max(0, Math.min(maxStart, clip.trimStartMs + delta))
        updateClip(selectedClipId, { trimStartMs: nextTrimStart })
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [selectedClipId, clips, moveClip, removeClip, updateClip, transport, shortcutsOpen])

  if (!clips.length) {
    return (
      <div className="flex h-24 flex-col items-center justify-center gap-2 text-xs text-muted-foreground">
        <span>No clips in timeline</span>
        <div className="flex items-center gap-2">
          {(library.length > 0 || hasVoiceLibrary) && (
            <SegmentBrowserModal
              segments={library}
              onInsertSegments={onInsertFromLibrary}
              voices={voiceLibrary}
              onInsertVoices={onInsertVoiceFromLibrary}
              insertAfterClipId={null}
              controllerRef={pickerRef}
            />
          )}
        </div>
      </div>
    )
  }

  return (
    <>
    <div className="relative flex min-w-0 flex-col gap-2">
      {/* Library insert bar */}
      {(library.length > 0 || hasVoiceLibrary) && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs text-muted-foreground">
            Drag to reorder clips, trim edges, and adjust gaps to build your 10–15s reference voice.
          </span>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <div className="flex items-center gap-1 rounded border border-border bg-background px-1">
              <button type="button" data-testid="stitch-zoom-out" className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground" onClick={zoomOut} aria-label="Zoom out">
                <Minus className="size-3.5" />
              </button>
              <button type="button" data-testid="stitch-zoom-fit" className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground" onClick={zoomFit} aria-label="Fit timeline to view" title="Fit timeline to view">
                <Maximize2 className="size-3.5" />
              </button>
              <button type="button" data-testid="stitch-zoom-in" className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground" onClick={zoomIn} aria-label="Zoom in">
                <Plus className="size-3.5" />
              </button>
              <span data-testid="stitch-zoom-level" className="px-1 text-[10px] font-mono text-muted-foreground/70">{Math.round(pixelsPerSecond)}px/s</span>
            </div>
            <button type="button" className="inline-flex h-8 items-center gap-1.5 rounded border border-border bg-background px-2.5 text-xs hover:bg-muted" onClick={autoPace}>
              <Gauge className="size-3.5" /> Auto-pace
            </button>
            <button type="button" className="inline-flex h-8 items-center gap-1.5 rounded border border-border bg-background px-2.5 text-xs hover:bg-muted" onClick={() => setShortcutsOpen(true)} title="Keyboard shortcuts (?)">
              Shortcuts
            </button>
            {(library.length > 0 || hasVoiceLibrary) && (
              <SegmentBrowserModal
                segments={library}
                onInsertSegments={onInsertFromLibrary}
                voices={voiceLibrary}
                onInsertVoices={onInsertVoiceFromLibrary}
                insertAfterClipId={selectedClipId}
                controllerRef={pickerRef}
              />
            )}
          </div>
        </div>
      )}

      {/* Timeline */}
      <div
        ref={scrollRef}
        onWheel={onWheelZoom}
        className="relative flex items-stretch gap-0 overflow-x-auto overflow-y-visible pl-5"
        style={{ minWidth: 0 }}
      >
        {contentWidthPx > 0 && (
          <TimelineRuler
            durationSeconds={totalSeconds}
            pixelsPerSecond={pixelsPerSecond}
            widthPx={contentWidthPx}
            laneHeightPx={140}
            transport={transport}
            previewScale={previewScale}
            onSeekSeconds={handleSeek}
          />
        )}

        <MotionConfig reducedMotion={reducedMotion ? 'always' : 'never'}>
        <Reorder.Group
          axis="x"
          values={clips}
          onReorder={handleReorder}
          className="relative z-[1] mt-5 flex w-max min-w-full items-start gap-0"
        >
          <AnimatePresence initial={false}>
          {clips.map((clip, i) => {
            const clipSeconds = clipEffectiveDurationMs(clip) / 1000
            const naturalWidthPx = clipSeconds * pixelsPerSecond
            const clipWidthPx = Math.max(MIN_CLIP_PX, naturalWidthPx)
            const isClipClamped = naturalWidthPx < MIN_CLIP_PX
            const isRangePlaying = transport.activeRangeId === clip.clipId
            return (
              <motion.div
                key={clip.clipId}
                data-testid="stitch-clip-wrapper"
                layout
                initial={{ opacity: 0, scale: 0.96 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.96 }}
                transition={{ duration: reducedMotion ? 0 : 0.18, ease: 'easeOut' }}
                className="flex shrink-0 items-start gap-4 transition-transform duration-150 ease-out motion-reduce:transition-none motion-reduce:duration-0"
              >
                {i > 0 && (
                  <GapControl gapIndex={i - 1} paddingMs={paddingMs[i - 1] || 0} onSetPadding={setPadding} pixelsPerSecond={pixelsPerSecond} defaultMs={suggestedGapMs(clips[i - 1]?.text ?? '')} />
                )}
                <Reorder.Item
                  value={clip}
                  data-testid="stitch-clip"
                  data-clip-id={clip.clipId}
                  data-selected={selectedClipId === clip.clipId ? 'true' : 'false'}
                  onClick={() => setSelectedClipId((prev) => (prev === clip.clipId ? null : clip.clipId))}
                  className="group relative flex flex-col rounded-md"
                  style={{ width: clipWidthPx, minWidth: MIN_CLIP_PX }}
                >
                  {/* Keyboard-accessible reorder buttons */}
                  <div className="absolute -left-5 top-6 flex flex-col gap-0.5 opacity-40 group-hover:opacity-100 z-10">
                    <button type="button" className="size-4 rounded bg-muted/70 text-[10px] text-muted-foreground hover:bg-muted" onClick={() => moveClip(i, 'left')} title="Move left">
                      <ChevronUp className="size-3" />
                    </button>
                    <button type="button" className="size-4 rounded bg-muted/70 text-[10px] text-muted-foreground hover:bg-muted" onClick={() => moveClip(i, 'right')} title="Move right">
                      <ChevronDown className="size-3" />
                    </button>
                  </div>
                  <StitchClipCard
                    clip={clip}
                    onRemove={removeClip}
                    onUpdate={updateClip}
                    regionEdits={regionEditsByClip[clip.clipId] ?? EMPTY_REGION_EDITS}
                    onAddRegionEdit={onAddRegionEdit}
                    onRemoveRegionEdit={onRemoveRegionEdit}
                    onSplitRegion={splitRegion}
                    isReordering
                    isSelected={selectedClipId === clip.clipId}
                    isWidthClamped={isClipClamped}
                    isRangePlaying={isRangePlaying}
                    onPlayRange={handlePlayRange}
                  />
                </Reorder.Item>
              </motion.div>
            )
          })}
          </AnimatePresence>
        </Reorder.Group>
        </MotionConfig>
      </div>
    </div>
    <ShortcutsDialog open={shortcutsOpen} onOpenChange={setShortcutsOpen} />
    </>
  )
})

/* ---------- DSP controls panel ---------- */

export function StitchDspControls({
  open,
  onToggle,
  dsp,
  onSetDsp: setDsp,
}: {
  open: boolean
  onToggle: () => void
  dsp: StitchPlanDsp
  onSetDsp: (patch: Partial<StitchPlanDsp>) => void
}) {
  const reducedMotion = useReducedMotion()

  return (
    <div className="mt-2 flex flex-col gap-2">
      <button
        type="button"
        onClick={onToggle}
        className="self-start text-xs text-muted-foreground underline decoration-dotted underline-offset-2 hover:text-foreground"
      >
        {open ? 'Hide DSP controls' : 'DSP controls'}
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={reducedMotion ? { opacity: 0 } : { opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={reducedMotion ? { opacity: 0 } : { opacity: 0, height: 0 }}
            className="grid grid-cols-2 gap-x-6 gap-y-3 overflow-hidden rounded-lg border border-border/60 bg-muted/40 px-4 py-3"
          >
            <SliderField label="Segment target" value={dsp.segmentTargetDbfs} min={-40} max={-10} step={0.5} defaultValue={-20} format={(v) => `${v} dBFS`} onChange={(v) => setDsp({ segmentTargetDbfs: v })} />
            <SliderField label="Final target" value={dsp.finalTargetDbfs} min={-40} max={-10} step={0.5} defaultValue={-18} format={(v) => `${v} dBFS`} onChange={(v) => setDsp({ finalTargetDbfs: v })} />
            <SliderField label="Final ceiling" value={dsp.finalCeilingDb} min={-6} max={0} step={0.2} defaultValue={-1} format={(v) => `${v} dB`} onChange={(v) => setDsp({ finalCeilingDb: v })} />
            <SliderField label="Crossfade" value={dsp.crossfadeMs} min={0} max={400} step={5} defaultValue={100} format={(v) => `${v} ms`} onChange={(v) => setDsp({ crossfadeMs: v })} />
            <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">
              Pacing style
              <select value={dsp.prosodyStylePreset} onChange={(e) => setDsp({ prosodyStylePreset: e.currentTarget.value as typeof dsp.prosodyStylePreset })} className="rounded border border-border bg-background px-2 py-1 text-xs text-foreground">
                {['Neutral', 'Storyteller', 'Calm', 'Energetic', 'Broadcast', 'Clean'].map((name) => <option key={name} value={name}>{name}</option>)}
              </select>
            </label>
            <SliderField label="Pace" value={dsp.paceMultiplier} min={0.5} max={2} step={0.05} defaultValue={1} format={(v) => `${v.toFixed(2)}×`} onChange={(v) => setDsp({ paceMultiplier: v })} />
            <div className="col-span-2 flex items-center justify-between pt-1">
              <label className="flex items-center gap-2 text-xs text-foreground">
                <input type="checkbox" checked={dsp.compressEnabled} onChange={(e) => setDsp({ compressEnabled: e.currentTarget.checked })} className="h-3.5 w-3.5 accent-cyan-500" />
                Compression
              </label>
              <div className="flex items-center gap-4">
                <SliderField label="Threshold" value={dsp.compressThresholdDb} min={-60} max={-12} step={0.5} defaultValue={-24} format={(v) => `${v} dB`} onChange={(v) => setDsp({ compressThresholdDb: v })} disabled={!dsp.compressEnabled} />
                <SliderField label="Ratio" value={dsp.compressRatio} min={1} max={10} step={0.1} defaultValue={2.5} format={(v) => `${v}:1`} onChange={(v) => setDsp({ compressRatio: v })} disabled={!dsp.compressEnabled} />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
function SliderField({
  label,
  value,
  min,
  max,
  step,
  format,
  onChange,
  disabled,
  defaultValue,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  format: (v: number) => string
  onChange: (v: number) => void
  disabled?: boolean
  /** N1 double-click reset target (the plan-start value from store.ts). */
  defaultValue?: number
}) {
  const {
    editing,
    draftText,
    setDraftText,
    commitEdit,
    displayValue,
    beginScrub,
    handleKeyDown,
    handleDoubleClick,
  } = useDragScrubValue({
    value,
    min,
    max,
    step,
    onChange,
    dragScale: (max - min) / 160,
    dragThreshold: 2,
    shiftStep: step * 5,
    parse: parseNumericText,
    defaultValue,
    disabled,
  })
  return (
    <div
      className={cn('flex flex-col gap-1 select-none', disabled && 'opacity-50')}
      onPointerDown={(e) => { if (!(e.target as HTMLElement).closest('input')) beginScrub(e.nativeEvent, e.currentTarget, { openEditorOnRelease: true }) }}
      onDoubleClick={handleDoubleClick}
    >
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-muted-foreground">{label}</span>
        {editing ? (
          <input
            type="text"
            inputMode="decimal"
            value={draftText}
            aria-label={label}
            onChange={(event) => setDraftText(event.target.value)}
            onBlur={commitEdit}
            onKeyDown={handleKeyDown}
            className="w-16 rounded border border-cyan-500/40 bg-muted/40 px-1 text-right text-[11px] font-mono tabular-nums text-foreground outline-none"
            autoFocus
          />
        ) : (
          <span className="text-[11px] font-mono tabular-nums text-foreground">
            {format(displayValue)}
          </span>
        )}
      </div>
      <div
        className="h-1.5 w-full rounded bg-muted"
        aria-hidden
        style={{
          background: `linear-gradient(to right, var(--color-cyan-500) ${((displayValue - min) / (max - min)) * 100}%, var(--color-muted) ${((displayValue - min) / (max - min)) * 100}%)`,
        }}
      />
    </div>
  )
}

/* ---------- Editor shell ---------- */

interface StitchEditorCommonProps {
  session: StitchPlanSession
  library: SegmentMeta[]
  onInsertFromLibrary: (segs: SegmentMeta[], afterClipId: string | null) => void
  voiceLibrary?: VoiceMeta[]
  onInsertVoiceFromLibrary?: (voices: VoiceMeta[], afterClipId: string | null) => void
}

export type StitchEditorBodyProps =
  | (StitchEditorCommonProps & {
      surface: 'studio'
      /** Reference texts, in clip order, used as the transcript for the saved voice's cloning
       * reference audio -- kept separate from onSave's plan payload because it's derived from
       * the clips' (possibly user-edited) text, not from DSP/trim/fade params. */
      onSave: (plan: StitchPlanPayload, segments: string[]) => Promise<void>
      onStartOver?: () => void
      name: string
      saveLabel: string
      isSaving: boolean
      isActivating: boolean
      onFocusName: () => void
    })
  | (StitchEditorCommonProps & {
      surface: 'quick-insert'
      /** Atomically commits the draft plan into the store, then either stays on the calling
       * page ('caller') or navigates to Stitch Studio ('studio'). */
      onCommitDraft: (plan: StitchPlanState, destination: 'caller' | 'studio') => void
      onCancelDraft: () => void
    })

// Shared editor internals (timeline + DSP controls + live preview + render/commit footer),
// with no opinion on how it's framed -- StitchEditorPanel wraps it in a Radix dialog (the
// quick-insert surface, hoisted once in App.tsx); StitchEditorInline renders it as plain page
// content (the studio surface, used by the standalone Stitch Studio page). The two surfaces
// never mix: quick-insert never renders a reference-voice save control, and studio never
// renders the draft's commit/cancel footer.
function StitchEditorBody(props: StitchEditorBodyProps) {
  const { session, library, onInsertFromLibrary, voiceLibrary, onInsertVoiceFromLibrary } = props
  const { plan } = session
  const { clips, paddingMs, dsp } = plan
  const hasSuggestedGap = paddingMs.some(
    (padding, index) => padding === suggestedGapMs(clips[index]?.text ?? ''),
  )
  const [showDsp, setShowDsp] = useState(false)
  const [isNormalizingPacing, setIsNormalizingPacing] = useState(false)
  const [normalizeError, setNormalizeError] = useState<string | null>(null)
  const pickerRef = useRef<SegmentBrowserModalController | null>(null)

  const preview = useStitchPreview(plan)
  const transport = useStitchTransport(preview.url)
  const planHash = useMemo(() => hashStitchPlan(plan), [plan])

  const handleSave = useCallback(async () => {
    if (props.surface !== 'studio') return
    preview.cancel()
    const segments = clips.map((c) => c.text?.trim()).filter((t): t is string => !!t)
    await props.onSave(planStateToPayload(plan), segments)
  }, [props, plan, clips, preview])

  const requestAddClips = useCallback(() => {
    pickerRef.current?.open()
  }, [])

  const normalizePacing = useCallback(async () => {
    if (!clips.length) return
    setIsNormalizingPacing(true)
    setNormalizeError(null)
    try {
      const result = await getStitchPacingTargets({
        transcripts: clips.map((clip) => clip.text ?? ''),
        stylePreset: dsp.prosodyStylePreset,
        paceMultiplier: dsp.paceMultiplier,
        pauseOffsetMs: dsp.pauseOffsetMs,
      })
      session.setPadding(result.padding_ms)
      session.setClips((current) => current.map((clip) => ({ ...clip, prosodyMode: 'auto' })))
      setNormalizeError(null)
    } catch (err) {
      // The pacing call failed and no plan state changed, so no re-render would otherwise
      // surface it -- track it locally and show it next to the button.
      setNormalizeError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsNormalizingPacing(false)
    }
  }, [clips, dsp, session])

  const handleStartOver = useCallback(() => {
    if (props.surface !== 'studio') return
    if (!clips.length || !window.confirm('Clear this timeline and start over?')) return
    preview.clear()
    session.reset()
    props.onStartOver?.()
  }, [props, clips.length, preview, session])

  const handleCommitDraft = useCallback((destination: 'caller' | 'studio') => {
    if (props.surface !== 'quick-insert') return
    preview.cancel()
    props.onCommitDraft(plan, destination)
  }, [props, plan, preview])

  const handleCancelDraft = useCallback(() => {
    if (props.surface !== 'quick-insert') return
    preview.cancel()
    props.onCancelDraft()
  }, [props, preview])

  const totalMs = useMemo(() => {
    let sum = 0
    for (const c of clips) {
      sum += clipEffectiveDurationMs(c)
    }
    sum += (paddingMs || []).reduce((a, b) => a + b, 0)
    return Math.max(1, sum)
  }, [clips, paddingMs])

  return (
    <>
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2.5">
          <span className="text-sm font-semibold uppercase tracking-wider text-foreground">Arrange your reference clip</span>
          <span className="text-xs text-muted-foreground/70">{clips.length} clip{clips.length !== 1 ? 's' : ''}</span>
          <button
            type="button"
            onClick={normalizePacing}
            disabled={!clips.length || isNormalizingPacing}
            className="inline-flex items-center gap-1 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-1 text-[10px] font-medium text-cyan-300 hover:bg-cyan-500/15 disabled:opacity-50"
            title="Set seam targets from the shared pacing engine and auto-repair internal blended boundaries"
          >
            {isNormalizingPacing ? <Loader2 className="size-3 animate-spin" /> : <Gauge className="size-3" />}
            Normalize pacing
          </button>
          {normalizeError && (
            <span className="status-badge status-tone-danger px-2 py-0.5 text-[10px] font-medium" title={normalizeError}>
              normalize failed
            </span>
          )}
          {hasSuggestedGap && (
            <span data-testid="stitch-gap-suggestion" className="text-[10px] text-muted-foreground">
              Suggested from punctuation
            </span>
          )}
          {preview.isStale && !preview.error && (
            <span className="inline-flex items-center gap-1 rounded-full bg-warning/10 px-2 py-0.5 text-[10px] font-medium text-warning">
              changes pending
            </span>
          )}
          {preview.error && (
            <span
              className="inline-flex items-center gap-1 rounded-full bg-destructive/10 px-2 py-0.5 text-[10px] font-medium text-destructive"
              title={preview.error}
            >
              preview failed — showing last good render
            </span>
          )}
        </div>
        {props.surface === 'studio' && clips.length > 0 && (
          <div className="flex shrink-0 items-center gap-1.5">
            <button
              type="button"
              data-testid="stitch-start-over"
              onClick={handleStartOver}
              className="inline-flex items-center gap-1 rounded-full border border-border bg-background px-2.5 py-1 text-[10px] font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <RotateCcw className="size-3" />
              Start over
            </button>
          </div>
        )}
      </div>

      <StitchTimeline
        totalDurationMs={totalMs}
        isPreviewStale={preview.isStale}
        library={library}
        onInsertFromLibrary={onInsertFromLibrary}
        session={session}
        voiceLibrary={voiceLibrary}
        onInsertVoiceFromLibrary={onInsertVoiceFromLibrary}
        transport={transport}
        pickerRef={pickerRef}
      />
      <StitchDspControls open={showDsp} onToggle={() => setShowDsp((v) => !v)} dsp={dsp} onSetDsp={session.setDsp} />

      {clips.length > 0 && (
        <div
          data-testid="stitch-preview-ready"
          data-plan-hash={planHash}
          className="flex flex-col gap-2"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold uppercase text-muted-foreground">Live preview</span>
              {preview.isRendering && (
                <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
                  <Loader2 className="size-3 animate-spin" />
                  rendering…
                </span>
              )}
            </div>
          </div>
          {preview.url ? (
            <>
              <TransportBar transport={transport} />
              <audio ref={transport.audioRef} src={preview.url} preload="auto" data-testid="stitch-transport-audio" />
            </>
          ) : (
            <div className="flex h-10 items-center px-3 text-xs text-muted-foreground">
              Generating preview…
            </div>
          )}
        </div>
      )}

      {props.surface === 'studio' ? (
        <ReferenceReadiness
          plan={plan}
          name={props.name}
          isSaving={props.isSaving}
          isActivating={props.isActivating}
          isPreviewRendering={preview.isRendering}
          saveLabel={props.saveLabel}
          onSave={handleSave}
          onFocusName={props.onFocusName}
          onAddClips={requestAddClips}
        />
      ) : (
        <div className="mt-1 flex items-center justify-between border-t border-border/60 pt-3">
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              data-testid="stitch-cancel-draft"
              onClick={handleCancelDraft}
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              Cancel
            </button>
            <button
              type="button"
              data-testid="stitch-save-close"
              onClick={() => handleCommitDraft('caller')}
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted"
              title="Keep this segment in your Stitch Studio draft"
            >
              Save and close
            </button>
            <button
              type="button"
              data-testid="stitch-open-studio"
              onClick={() => handleCommitDraft('studio')}
              className="btn-brand inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 text-xs font-medium"
            >
              Open in Stitch Studio
            </button>
          </div>
          <div className="text-[10px] text-muted-foreground">{(totalMs / 1000).toFixed(1)}s total</div>
        </div>
      )}
    </>
  )
}

export function StitchEditorPanel(props: Extract<StitchEditorBodyProps, { surface: 'quick-insert' }>) {
  const handleOpenChange = useCallback((open: boolean) => {
    if (!open) props.onCancelDraft()
  }, [props])

  return (
    <Dialog open onOpenChange={handleOpenChange}>
      <DialogContent
        data-testid="stitch-editor-dialog"
        className="flex max-h-[88vh] w-full max-w-5xl flex-col gap-4 overflow-y-auto sm:max-w-5xl"
      >
        <DialogTitle className="sr-only">Stitch Studio quick insert</DialogTitle>
        <DialogDescription className="sr-only">
          Arrange the inserted clip, then choose whether to open it in Stitch Studio or keep it in your draft.
        </DialogDescription>
        <StitchEditorBody {...props} />
      </DialogContent>
    </Dialog>
  )
}

// Plain page content, no portal/backdrop/close button -- used by the standalone Stitch Studio
// page, which is the editor's home rather than something popping over another workflow.
export function StitchEditorInline(props: Extract<StitchEditorBodyProps, { surface: 'studio' }>) {
  return (
    <div className="flex min-w-0 flex-col gap-4 rounded-2xl border border-border bg-background/50 px-6 py-5">
      <StitchEditorBody {...props} />
    </div>
  )
}

/* ---------- shared transport bar ---------- */

// Replaces the old PreviewPlayer, which owned its own <audio> element and local playing/
// progress state -- Packet 7 requires exactly one audio element for the whole arrangement, so
// the toggle button and progress rail here are driven entirely by the shared transport passed
// down from StitchEditorBody. The progress fill is pushed via RAF through `subscribeTime`
// (never React state per frame), the same pattern the ruler's playhead uses.
function TransportBar({ transport }: { transport: StitchTransport }) {
  const fillRef = useRef<HTMLDivElement>(null)
  const { subscribeTime, getCurrentTime, durationSec } = transport

  useEffect(() => {
    const el = fillRef.current
    if (!el) return
    const apply = (sec: number) => {
      const pct = durationSec > 0 ? Math.min(100, Math.max(0, (sec / durationSec) * 100)) : 0
      el.style.width = `${pct}%`
    }
    apply(getCurrentTime())
    return subscribeTime(apply)
  }, [subscribeTime, getCurrentTime, durationSec])

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        data-testid="stitch-transport-toggle"
        onClick={transport.toggle}
        aria-label={transport.isPlaying ? 'Pause' : 'Play'}
        className="inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground hover:text-foreground"
      >
        {transport.isPlaying
          ? <div className="flex gap-[3px]"><div className="h-3 w-[2px] bg-current" /><div className="h-3 w-[2px] bg-current" /></div>
          : <Play className="size-3" />}
      </button>
      <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-black/40">
        <div ref={fillRef} className="absolute inset-y-0 left-0 bg-gradient-to-r from-cyan-500/50 to-fuchsia-500/40" style={{ width: '0%' }} />
      </div>
    </div>
  )
}

/* ---------- shortcuts dialog ---------- */

const SHORTCUTS: Array<[string, string]> = [
  ['Space', 'Play/pause the arrangement'],
  ['Click ruler', 'Seek the arrangement'],
  ['←/→', 'Select the previous/next clip'],
  ['Shift+←/→', 'Reorder the selected clip'],
  ['↑/↓', 'Nudge trim start by 10ms (Shift = 100ms)'],
  ['Delete/Backspace', 'Remove the selected clip'],
  ['?', 'Show this dialog'],
]

function ShortcutsDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="stitch-shortcuts-dialog" className="max-w-sm">
        <DialogTitle>Keyboard shortcuts</DialogTitle>
        <DialogDescription className="sr-only">Stitch Studio keyboard shortcuts</DialogDescription>
        <dl className="flex flex-col gap-2 text-xs">
          {SHORTCUTS.map(([key, desc]) => (
            <div key={key} className="flex items-center justify-between gap-4">
              <dt className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[11px] text-foreground">{key}</dt>
              <dd className="text-muted-foreground">{desc}</dd>
            </div>
          ))}
        </dl>
      </DialogContent>
    </Dialog>
  )
}
