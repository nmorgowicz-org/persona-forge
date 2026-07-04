import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion, Reorder } from 'framer-motion'
import { ChevronUp, ChevronDown, GripVertical, X, Loader2, Play } from 'lucide-react'
import { useAppStore, type StitchPlanClip } from '@/store'
import { base64ToBlob, cn } from '@/lib/utils'
import { renderStitchPlan, type StitchPlanPayload, type SegmentMeta } from '@/lib/api'

/* ---------- helpers ---------- */

function clipEffectiveDurationMs(clip: StitchPlanClip): number {
  const base = clip.durationMs ?? 0
  if (!base) return 0
  return Math.max(10, base - clip.trimStartMs - clip.trimEndMs)
}

function barColor(peak: number) {
  const hue = 190 + peak * 140
  const light = 40 + peak * 10
  const alpha = 0.3 + peak * 0.25
  return `hsl(${hue} 45% ${light}% / ${alpha})`
}

/* ---------- sub-components ---------- */

function StitchTimelineClip({
  clip,
  gapIndex,
  totalDurationMs,
  onRemove,
  onUpdate,
  onSetPadding,
  isReordering,
}: {
  clip: StitchPlanClip
  gapIndex: number | null
  totalDurationMs: number
  onRemove: (clipId: string) => void
  onUpdate: (clipId: string, patch: Partial<StitchPlanClip>) => void
  onSetPadding: (gapIndex: number, ms: number) => void
  isReordering?: boolean
}) {
  const [peaks, setPeaks] = useState<number[] | null>(null)
  const [durMs, setDurMs] = useState<number | null>(null)

  useEffect(() => {
    let dead = false
    ;(async () => {
      if (!clip.sourceAudioBase64) return
      const blob = base64ToBlob(clip.sourceAudioBase64)
      try {
        const arrayBuffer = await blob.arrayBuffer()
        const ctx = new (window.AudioContext || (window as any).webkitAudioContext)()
        const audioBuffer = await ctx.decodeAudioData(arrayBuffer.slice(0))
        const channel = audioBuffer.getChannelData(0)
        if (!dead) setDurMs(Math.round(audioBuffer.duration * 1000))
        const count = 48
        const bucketSize = Math.max(1, Math.floor(channel.length / count))
        const pks: number[] = []
        for (let i = 0; i < count; i++) {
          const start = i * bucketSize
          const end = Math.min(start + bucketSize, channel.length)
          let max = 0
          for (let j = start; j < end; j++) {
            const abs = Math.abs(channel[j])
            if (abs > max) max = abs
          }
          pks.push(max)
        }
        const overallMax = Math.max(...pks, 0.01)
        if (!dead) setPeaks(pks.map((p) => p / overallMax))
        ctx.close()
      } catch {
        if (!dead) setPeaks([])
      }
    })()
    return () => { dead = true }
  }, [clip.sourceAudioBase64])

  const effectiveDuration = clipEffectiveDurationMs(clip)
  const widthPct = totalDurationMs > 0 ? Math.max(3, (effectiveDuration / totalDurationMs) * 100) : 3

  const clampTrimStart = (v: number) => {
    const nv = Math.max(0, Math.min(v, (durMs ?? 0) - 20))
    if (nv + clip.trimEndMs >= (durMs ?? 0)) return durMs ? durMs - 20 - clip.trimEndMs : 0
    return nv
  }
  const clampTrimEnd = (v: number) => {
    const nv = Math.max(0, Math.min(v, (durMs ?? 0) - 20))
    if (nv + clip.trimStartMs >= (durMs ?? 0)) return durMs ? durMs - 20 - clip.trimStartMs : 0
    return nv
  }
  const clampFade = (v: number) => {
    const maxMs = Math.max(10, effectiveDuration - 10)
    return Math.max(0, Math.min(v, maxMs))
  }

  const visiblePeaks = useMemo(() => {
    if (!peaks || !durMs || durMs <= 0) return peaks
    const startRatio = clip.trimStartMs / durMs
    const endRatio = clip.trimEndMs / durMs
    const from = Math.floor(startRatio * peaks.length)
    const to = peaks.length - Math.floor(endRatio * peaks.length)
    return peaks.slice(from, to)
  }, [peaks, durMs, clip.trimStartMs, clip.trimEndMs])

  const fadeOverlay = (side: 'left' | 'right', ms: number) => {
    if (!ms || ms <= 0) return null
    return (
      <div
        className={cn(
          'pointer-events-none absolute inset-y-0 w-[32px]',
          side === 'left' ? 'left-0' : 'right-0',
        )}
        style={{
          background:
            side === 'left'
              ? 'linear-gradient(to right, rgba(0,0,0,0.7) 0%, transparent 100%)'
              : 'linear-gradient(to left, rgba(0,0,0,0.7) 0%, transparent 100%)',
        }}
      />
    )
  }

  return (
    <div
      className={cn("group relative flex flex-col", isReordering && 'cursor-grab')}
      style={{ width: `${widthPct}%`, minWidth: 140 }}
    >
      <div className="flex items-center justify-between gap-2 px-1.5 pt-1 pb-1">
        <span className="truncate text-xs font-medium text-foreground" title={clip.text}>
          {clip.text || '(untitled)'}
        </span>
        <div className="flex items-center gap-1.5">
          {isReordering && (
            <div className="flex items-center text-muted-foreground/60">
              <GripVertical className="size-3.5" />
            </div>
          )}
          <button
            type="button"
            className="rounded p-0.5 text-muted-foreground hover:text-destructive"
            onClick={() => onRemove(clip.clipId)}
            title="Remove clip"
          >
            <X className="size-3.5" />
          </button>
        </div>
      </div>

      <div className="relative h-24 overflow-hidden rounded-md bg-black/40">
        {visiblePeaks && visiblePeaks.length > 0 ? (
          <div className="flex h-full items-center gap-[0.5px] px-0.5">
            {visiblePeaks.map((p, i) => {
              const h = Math.max(0.06, p)
              return (
                <div
                  key={i}
                  className="h-full min-w-[1px] flex-1 rounded-full"
                  style={{
                    transformOrigin: 'center',
                    transform: `scaleY(${h})`,
                    background: barColor(p),
                  }}
                />
              )
            })}
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-[10px] text-muted-foreground/60">
            loading…
          </div>
        )}
        {fadeOverlay('left', clip.fadeInMs)}
        {fadeOverlay('right', clip.fadeOutMs)}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <MsStepper label="Trim start" value={clip.trimStartMs} min={0} max={durMs ?? 0} step={10} onChange={(v) => onUpdate(clip.clipId, { trimStartMs: clampTrimStart(v) })} />
        <MsStepper label="Trim end" value={clip.trimEndMs} min={0} max={durMs ?? 0} step={10} onChange={(v) => onUpdate(clip.clipId, { trimEndMs: clampTrimEnd(v) })} />
        <MsStepper label="Fade in" value={clip.fadeInMs} min={0} max={2000} step={10} onChange={(v) => onUpdate(clip.clipId, { fadeInMs: clampFade(v) })} />
        <MsStepper label="Fade out" value={clip.fadeOutMs} min={0} max={2000} step={10} onChange={(v) => onUpdate(clip.clipId, { fadeOutMs: clampFade(v) })} />
      </div>

      {gapIndex != null && (
        <GapControl gapIndex={gapIndex} onSetPadding={onSetPadding} />
      )}
    </div>
  )
}

function GapControl({
  gapIndex,
  onSetPadding,
}: {
  gapIndex: number
  onSetPadding: (gapIndex: number, ms: number) => void
}) {
  const padding = useAppStore((s) => s.ovStitchPlanPaddingMs)
  const value = padding[gapIndex] ?? 0
  return (
    <div className="mx-1.5 flex items-center gap-1.5 rounded border border-dashed border-border/60 px-1.5 py-1 bg-black/10">
      <span className="text-[10px] uppercase text-muted-foreground">gap</span>
      <MsStepper label="gap" value={value} min={0} max={3000} step={10} onChange={(v) => onSetPadding(gapIndex, v)} compact />
    </div>
  )
}

function MsStepper({
  label,
  value,
  min,
  max,
  step,
  onChange,
  compact,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  onChange: (v: number) => void
  compact?: boolean
}) {
  return (
    <div className={cn('inline-flex items-center gap-1', compact && 'gap-0.5')} title={label}>
      {!compact && <span className="shrink-0 text-[10px] uppercase text-muted-foreground/70">{label}</span>}
      <button type="button" className="inline-flex size-5 shrink-0 items-center justify-center rounded bg-muted/70 text-xs text-muted-foreground hover:bg-muted" onClick={() => onChange(Math.max(min, value - step))}>−</button>
      <span className="inline-flex min-w-[32px] justify-center text-xs font-mono tabular-nums text-foreground">{value}</span>
      <button type="button" className="inline-flex size-5 shrink-0 items-center justify-center rounded bg-muted/70 text-xs text-muted-foreground hover:bg-muted" onClick={() => onChange(Math.min(max, value + step))}>+</button>
    </div>
  )
}

/* ---------- main component ---------- */

interface StitchTimelineProps {
  totalDurationMs: number
  isPreviewStale: boolean
  library: SegmentMeta[]
  onInsertFromLibrary: (seg: SegmentMeta) => void
}

export const StitchTimeline = memo(function StitchTimeline({
  totalDurationMs: _totalDurationMs,
  isPreviewStale: _isPreviewStale,
  library,
  onInsertFromLibrary,
}: StitchTimelineProps) {
  const clips = useAppStore((s) => s.ovStitchPlanClips)
  const paddingMs = useAppStore((s) => s.ovStitchPlanPaddingMs)
  const reorderClip = useAppStore((s) => s.reorderOvStitchPlanClip)
  const removeClip = useAppStore((s) => s.removeOvStitchPlanClip)
  const updateClip = useAppStore((s) => s.updateOvStitchPlanClip)
  const setPadding = useAppStore((s) => s.setOvStitchPlanPaddingAt)
  const [libraryPickerOpen, setLibraryPickerOpen] = useState(false)

  const handleReorder = useCallback(
    (next: StitchPlanClip[]) => {
      const newIndices: number[] = []
      for (const c of next) {
        const idx = clips.findIndex((oc) => oc.clipId === c.clipId)
        if (idx !== -1) newIndices.push(idx)
      }
      // Build a mapping: for each new position, find the original index
      for (let i = 0; i < next.length; i++) {
        const from = clips.findIndex((oc) => oc.clipId === next[i].clipId)
        if (from !== i) {
          reorderClip(from, i)
          break
        }
      }
    },
    [clips, reorderClip],
  )

  const moveClip = useCallback(
    (index: number, direction: 'left' | 'right') => {
      const to = direction === 'left' ? index - 1 : index + 1
      if (to < 0 || to >= clips.length) return
      reorderClip(index, to)
    },
    [clips.length, reorderClip],
  )

  if (!clips.length) {
    return (
      <div className="flex h-24 flex-col items-center justify-center gap-2 text-xs text-muted-foreground">
        <span>No clips in timeline</span>
        {library.length > 0 && (
          <button
            type="button"
            onClick={() => setLibraryPickerOpen(true)}
            className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground hover:bg-muted"
          >
            Add saved segment
          </button>
        )}
      </div>
    )
  }

  const effectiveTotalMs = useMemo(() => {
    let sum = 0
    for (const c of clips) {
      sum += clipEffectiveDurationMs(c)
    }
    sum += (paddingMs || []).reduce((a, b) => a + b, 0)
    return Math.max(1, sum)
  }, [clips, paddingMs])

  return (
    <div className="relative flex flex-col gap-2">
      {/* Library insert bar */}
      {library.length > 0 && (
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">
              Drag to reorder clips, trim edges, and adjust gaps to build your 10–15s reference voice.
            </span>
          </div>
          <div className="relative">
            <button
              type="button"
              onClick={() => setLibraryPickerOpen((v) => !v)}
              className="inline-flex items-center gap-1 rounded-full border border-border px-3 py-1 text-xs text-muted-foreground hover:bg-muted"
            >
              {libraryPickerOpen ? 'Hide segments' : 'Add saved segment'}
            </button>

            <AnimatePresence>
              {libraryPickerOpen && (
                <motion.div
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  className="absolute right-0 top-9 z-30 flex max-h-52 w-72 flex-col gap-1 overflow-y-auto rounded-lg border border-border bg-background p-2 shadow-lg"
                >
                  <span className="text-[10px] uppercase text-muted-foreground">Saved segments</span>
                  {library.map((seg) => (
                    <button
                      key={seg.segment_id}
                      type="button"
                      onClick={() => {
                        onInsertFromLibrary(seg)
                        setLibraryPickerOpen(false)
                      }}
                      className="flex items-center justify-between gap-2 rounded-md border border-transparent px-2 py-1 text-xs text-foreground hover:border-border hover:bg-muted"
                    >
                      <span className="truncate">{seg.text}</span>
                    </button>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      )}

      {/* Timeline */}
      <div className="relative flex items-stretch gap-0 overflow-x-auto overflow-y-visible pl-5" style={{ minWidth: 0 }}>
        {effectiveTotalMs > 0 && (
          <div className="pointer-events-none absolute inset-x-5 top-0 flex h-4 items-start border-b border-border/30">
            {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
              const ms = ratio * effectiveTotalMs
              const sec = ms / 1000
              return (
                <div
                  key={ratio}
                  className="absolute text-[10px] font-mono text-muted-foreground/50"
                  style={{ left: `${ratio * 100}%`, transform: 'translateX(-50%)' }}
                >
                  {sec < 10 ? `${sec.toFixed(1)}s` : `${Math.floor(sec / 60)}:${(sec % 60).toFixed(0).padStart(2, '0')}`}
                </div>
              )
            })}
          </div>
        )}

        <Reorder.Group
          axis="x"
          values={clips}
          onReorder={handleReorder}
          className="mt-3 flex flex-1 items-start gap-3"
        >
          {clips.map((clip, i) => (
            <Reorder.Item
              key={clip.clipId}
              value={clip}
              className="group relative flex flex-col"
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
              <StitchTimelineClip
                clip={clip}
                gapIndex={i < clips.length - 1 ? i : null}
                totalDurationMs={effectiveTotalMs}
                onRemove={removeClip}
                onUpdate={updateClip}
                onSetPadding={setPadding}
                isReordering
              />
            </Reorder.Item>
          ))}
        </Reorder.Group>
      </div>
    </div>
  )
})

/* ---------- DSP controls panel ---------- */

export function StitchDspControls({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const dsp = useAppStore((s) => s.ovStitchPlanDsp)
  const setDsp = useAppStore((s) => s.setOvStitchPlanDsp)

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
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="grid grid-cols-2 gap-x-6 gap-y-3 overflow-hidden rounded-lg border border-border/60 bg-muted/40 px-4 py-3"
          >
            <SliderField label="Segment target" value={dsp.segmentTargetDbfs} min={-40} max={-10} step={0.5} format={(v) => `${v} dBFS`} onChange={(v) => setDsp({ segmentTargetDbfs: v })} />
            <SliderField label="Final target" value={dsp.finalTargetDbfs} min={-40} max={-10} step={0.5} format={(v) => `${v} dBFS`} onChange={(v) => setDsp({ finalTargetDbfs: v })} />
            <SliderField label="Final ceiling" value={dsp.finalCeilingDb} min={-6} max={0} step={0.2} format={(v) => `${v} dB`} onChange={(v) => setDsp({ finalCeilingDb: v })} />
            <SliderField label="Crossfade" value={dsp.crossfadeMs} min={0} max={400} step={5} format={(v) => `${v} ms`} onChange={(v) => setDsp({ crossfadeMs: v })} />
            <div className="col-span-2 flex items-center justify-between pt-1">
              <label className="flex items-center gap-2 text-xs text-foreground">
                <input type="checkbox" checked={dsp.compressEnabled} onChange={(e) => setDsp({ compressEnabled: e.currentTarget.checked })} className="h-3.5 w-3.5 accent-cyan-500" />
                Compression
              </label>
              <div className="flex items-center gap-4">
                <SliderField label="Threshold" value={dsp.compressThresholdDb} min={-60} max={-12} step={0.5} format={(v) => `${v} dB`} onChange={(v) => setDsp({ compressThresholdDb: v })} disabled={!dsp.compressEnabled} />
                <SliderField label="Ratio" value={dsp.compressRatio} min={1} max={10} step={0.1} format={(v) => `${v}:1`} onChange={(v) => setDsp({ compressRatio: v })} disabled={!dsp.compressEnabled} />
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
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  format: (v: number) => string
  onChange: (v: number) => void
  disabled?: boolean
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-muted-foreground">{label}</span>
        <span className="text-[11px] font-mono tabular-nums text-foreground">{format(value)}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} disabled={disabled} className="h-1.5 w-full cursor-pointer accent-cyan-500" />
    </div>
  )
}

/* ---------- Editor shell ---------- */

export function StitchEditorPanel({
  onClose,
  onRender,
  onSave,
  library,
  onInsertFromLibrary,
}: {
  onClose: () => void
  onRender: (plan: StitchPlanPayload) => Promise<void>
  onSave: (plan: StitchPlanPayload) => Promise<void>
  library: SegmentMeta[]
  onInsertFromLibrary: (seg: SegmentMeta) => void
}) {
  const clips = useAppStore((s) => s.ovStitchPlanClips)
  const paddingMs = useAppStore((s) => s.ovStitchPlanPaddingMs)
  const dsp = useAppStore((s) => s.ovStitchPlanDsp)
  const previewUrl = useAppStore((s) => s.ovStitchPreviewUrl)
  const _previewBlob = useAppStore((s) => s.ovStitchPreviewBlob)
  void _previewBlob
  const isRendering = useAppStore((s) => s.ovIsRenderingPreview)
  const setPreviewUrl = useAppStore((s) => s.setOvStitchPreviewUrl)
  const setPreviewBlob = useAppStore((s) => s.setOvStitchPreviewBlob)
  const setIsRendering = useAppStore((s) => s.setOvIsRenderingPreview)
  const [showDsp, setShowDsp] = useState(false)
  const [staleFlags, setStaleFlags] = useState(true)
  const debounceRef = useRef<number | null>(null)
  const lastHashRef = useRef('')

  const planPayload = useMemo<StitchPlanPayload>(() => {
    return {
      clips: clips.map((c) => {
        const anyRef = c.ref as Record<string, string>
        const isSegment = 'segmentId' in anyRef
        const segId = isSegment ? anyRef.segmentId : undefined
        const candId = !isSegment ? anyRef.candidateId : undefined
        return {
          segmentId: segId,
          candidateId: candId,
          trimStartMs: c.trimStartMs,
          trimEndMs: c.trimEndMs,
          fadeInMs: c.fadeInMs,
          fadeOutMs: c.fadeOutMs,
        }
      }),
      paddingMs: paddingMs.length ? paddingMs : new Array(clips.length - 1).fill(0),
      crossfadeMs: dsp.crossfadeMs,
      segmentTargetDbfs: dsp.segmentTargetDbfs,
      finalTargetDbfs: dsp.finalTargetDbfs,
      finalCeilingDb: dsp.finalCeilingDb,
      compress: dsp.compressEnabled
        ? {
            thresholdDb: dsp.compressThresholdDb,
            ratio: dsp.compressRatio,
            attackMs: 5,
            releaseMs: 80,
          }
        : null,
    }
  }, [clips, paddingMs, dsp])

  const hash = useMemo(() => {
    return JSON.stringify({
      clips: clips.map((c) => [c.trimStartMs, c.trimEndMs, c.fadeInMs, c.fadeOutMs]),
      paddingMs,
      dsp,
    })
  }, [clips, paddingMs, dsp])

  useEffect(() => {
    if (hash === lastHashRef.current || clips.length === 0) {
      if (hash !== lastHashRef.current) lastHashRef.current = hash
      return
    }
    lastHashRef.current = hash
    setStaleFlags(true)

    if (debounceRef.current != null) clearTimeout(debounceRef.current)
    debounceRef.current = window.setTimeout(async () => {
      debounceRef.current = null
      try {
        setIsRendering(true)
        const blob = await renderStitchPlan(planPayload)
        if (previewUrl) URL.revokeObjectURL(previewUrl)
        const url = URL.createObjectURL(blob)
        setPreviewUrl(url)
        setPreviewBlob(blob)
        setStaleFlags(false)
      } catch {
        /* keep last-good preview */
      } finally {
        setIsRendering(false)
      }
    }, 500)

    return () => {
      if (debounceRef.current != null) {
        clearTimeout(debounceRef.current)
        debounceRef.current = null
      }
    }
  }, [hash, planPayload, clips.length, setPreviewUrl, setPreviewBlob, setIsRendering, previewUrl])

  const handleRender = useCallback(async () => {
    setStaleFlags(false)
    await onRender(planPayload)
  }, [planPayload, onRender])

  const handleSave = useCallback(async () => {
    setStaleFlags(false)
    await onSave(planPayload)
  }, [planPayload, onSave])

  const totalMs = useMemo(() => {
    let sum = 0
    for (const c of clips) {
      sum += clipEffectiveDurationMs(c)
    }
    sum += (paddingMs || []).reduce((a, b) => a + b, 0)
    return Math.max(1, sum)
  }, [clips, paddingMs])

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <motion.div
        initial={{ opacity: 0, y: 12, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 12, scale: 0.98 }}
        className="flex max-h-[88vh] w-full max-w-5xl flex-col gap-4 overflow-y-auto rounded-2xl border border-border bg-background px-6 py-5 shadow-2xl"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="text-sm font-semibold uppercase tracking-wider text-foreground">Arrange your reference clip</span>
            <span className="text-xs text-muted-foreground/70">{clips.length} clip{clips.length !== 1 ? 's' : ''}</span>
            {staleFlags && (
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-400">
                changes pending
              </span>
            )}
          </div>
          <button type="button" onClick={onClose} className="rounded-full p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground" title="Close editor">
            <X className="size-4" />
          </button>
        </div>

        <StitchTimeline totalDurationMs={totalMs} isPreviewStale={staleFlags} library={library} onInsertFromLibrary={onInsertFromLibrary} />
        <StitchDspControls open={showDsp} onToggle={() => setShowDsp((v) => !v)} />

        {previewUrl && (
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold uppercase text-muted-foreground">Live preview</span>
                {isRendering && (
                  <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
                    <Loader2 className="size-3 animate-spin" />
                    rendering…
                  </span>
                )}
              </div>
            </div>
            <PreviewPlayer src={previewUrl} />
          </div>
        )}

        <div className="mt-1 flex items-center justify-between border-t border-border/60 pt-3">
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={handleRender}
              disabled={isRendering || clips.length === 0}
              className="inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-[hsl(190,90%,50%)] to-[hsl(210,90%,45%)] px-4 py-1.5 text-xs font-medium text-background shadow-[0_4px_15px_rgba(34,211,238,0.25)] transition-all hover:scale-[1.02] hover:shadow-[0_8px_25px_rgba(34,211,238,0.35)] disabled:opacity-50 disabled:shadow-none"
            >
              <Play className="size-3.5" />
              {isRendering ? 'Updating…' : 'Update preview'}
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={isRendering || clips.length === 0}
              className="inline-flex items-center gap-1.5 rounded-full border border-border px-4 py-1.5 text-xs font-medium text-foreground transition-all hover:bg-muted disabled:opacity-50"
              title="This will be used as a reusable cloning source for text-to-speech."
            >
              Save as reference voice
            </button>
          </div>
          <div className="text-[10px] text-muted-foreground">{(totalMs / 1000).toFixed(1)}s total</div>
        </div>
      </motion.div>
    </motion.div>
  )
}

/* ---------- minimal preview player ---------- */

function PreviewPlayer({ src }: { src: string }) {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const a = audioRef.current
    if (!a) return
    const onEnd = () => { setPlaying(false); setProgress(0) }
    const onTimeUpdate = () => {
      if (a.duration && isFinite(a.duration)) setProgress(a.currentTime / a.duration)
    }
    a.addEventListener('ended', onEnd)
    a.addEventListener('timeupdate', onTimeUpdate)
    return () => {
      a.removeEventListener('ended', onEnd)
      a.removeEventListener('timeupdate', onTimeUpdate)
    }
  }, [src])

  const togglePlay = async () => {
    const a = audioRef.current
    if (!a) return
    if (playing) a.pause()
    else await a.play()
    setPlaying(!playing)
  }

  return (
    <div className="flex items-center gap-2">
      <button type="button" onClick={togglePlay} className="inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground hover:text-foreground">
        {playing
          ? <div className="flex gap-[3px]"><div className="h-3 w-[2px] bg-current" /><div className="h-3 w-[2px] bg-current" /></div>
          : <Play className="size-3" />}
      </button>
      <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-black/40">
        <div className="absolute inset-y-0 left-0 bg-gradient-to-r from-cyan-500/50 to-fuchsia-500/40" style={{ width: `${progress * 100}%` }} />
      </div>
      <audio ref={audioRef} src={src} preload="auto" />
    </div>
  )
}
