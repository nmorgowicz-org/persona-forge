import { memo, useCallback, useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { AnimatePresence, motion, Reorder } from 'motion/react'
import { ChevronUp, ChevronDown, GripVertical, X, Loader2, Play, Pause, Scissors, Trash2, Volume2, VolumeX, Gauge, RotateCcw } from 'lucide-react'
import { type StitchPlanClip, type StitchPlanDsp } from '@/store'
import { base64ToBlob, cn } from '@/lib/utils'
import {
  getStitchPacingTargets,
  type StitchPlanPayload,
  type SegmentMeta,
  type VoiceMeta,
} from '@/lib/api'
import {
  clipEffectiveDurationMs,
  hashStitchPlan,
  type StitchPlanState,
  type StitchRegionEdit,
} from '@/lib/stitchPlan'
import { getClipAudioAnalysis } from '@/lib/waveform'
import { createTimeTicks } from '@/lib/timeAxis'
import { useElementWidth } from '@/hooks/useElementWidth'
import { type StitchPlanSession } from '@/hooks/useStitchPlanSession'
import { planStateToPayload } from '@/lib/stitchPreview'
import { useStitchPreview } from '@/hooks/useStitchPreview'
import { SegmentBrowserModal } from './stitch/SegmentBrowserModal'
import { WaveformLane } from './waveform/WaveformLane'

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

function makeRegionEditId(type: RegionEdit['type']): string {
  return `${type}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}


/* ---------- sub-components ---------- */

function StitchTimelineClip({
  clip,
  onRemove,
  onUpdate,
  regionEdits,
  onAddRegionEdit,
  onRemoveRegionEdit,
  onSplitRegion,
  isReordering,
  reducedMotion: _reducedMotion,
}: {
  clip: StitchPlanClip
  onRemove: (clipId: string) => void
  onUpdate: (clipId: string, patch: Partial<StitchPlanClip>) => void
  regionEdits: RegionEdit[]
  onAddRegionEdit: (clipId: string, edit: RegionEdit) => void
  onRemoveRegionEdit: (clipId: string, editId: string) => void
  onSplitRegion: (clipId: string, startMs: number, endMs: number) => void
  isReordering?: boolean
  reducedMotion: boolean
}) {
  const [peaks, setPeaks] = useState<number[] | null>(null)
  const [durMs, setDurMs] = useState<number | null>(null)
  const [clipPlaying, setClipPlaying] = useState(false)
  const clipAudioRef = useRef<HTMLAudioElement | null>(null)
  const clipAudioUrlRef = useRef<string | null>(null)
  const [editingText, setEditingText] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [draftText, setDraftText] = useState(clip.text ?? '')
  const [selection, setSelection] = useState<{ startMs: number; endMs: number } | null>(null)
  const [gainDb, setGainDb] = useState(-3)
  const [regionFadeInMs, setRegionFadeInMs] = useState(15)
  const [regionFadeOutMs, setRegionFadeOutMs] = useState(35)
  const [silenceMs, setSilenceMs] = useState(180)
  const textInputRef = useRef<HTMLInputElement | null>(null)
  const activeHandle = useRef<'leftTrim' | 'rightTrim' | 'leftFade' | 'rightFade' | null>(null)
  const selectionDrag = useRef<{ startMs: number } | null>(null)
  const laneRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (editingText) textInputRef.current?.focus()
  }, [editingText])

  const beginEditText = () => {
    setDraftText(clip.text ?? '')
    setEditingText(true)
  }

  const commitText = () => {
    setEditingText(false)
    const trimmed = draftText.trim()
    if (trimmed !== (clip.text ?? '')) onUpdate(clip.clipId, { text: trimmed })
  }

  const cancelEditText = () => {
    setEditingText(false)
    setDraftText(clip.text ?? '')
  }

  useEffect(() => {
    return () => {
      clipAudioRef.current?.pause()
      if (clipAudioUrlRef.current) URL.revokeObjectURL(clipAudioUrlRef.current)
    }
  }, [])

  const toggleClipPlay = () => {
    if (!clip.sourceAudioBase64) return
    if (!clipAudioRef.current) {
      const url = URL.createObjectURL(base64ToBlob(clip.sourceAudioBase64))
      clipAudioUrlRef.current = url
      const audio = new Audio(url)
      audio.addEventListener('ended', () => setClipPlaying(false))
      clipAudioRef.current = audio
    }
    if (clipPlaying) {
      clipAudioRef.current.pause()
      setClipPlaying(false)
    } else {
      void clipAudioRef.current.play()
      setClipPlaying(true)
    }
  }

  useEffect(() => {
    let dead = false
    if (!clip.sourceAudioBase64) return
    const assetKey = `clip:${clip.clipId}:${clip.sourceAudioBase64.length}`
    getClipAudioAnalysis(assetKey, clip.sourceAudioBase64, 48)
      .then((analysis) => {
        if (dead) return
        setDurMs(analysis.durationMs)
        setPeaks(analysis.peaks)
      })
      .catch(() => {
        if (!dead) setPeaks([])
      })
    return () => { dead = true }
  }, [clip.clipId, clip.sourceAudioBase64])

  const effectiveDuration = clipEffectiveDurationMs(clip)

  const clampTrimStart = useCallback((v: number) => {
    const nv = Math.max(0, Math.min(v, (durMs ?? 0) - 20))
    if (nv + clip.trimEndMs >= (durMs ?? 0)) return durMs ? durMs - 20 - clip.trimEndMs : 0
    return nv
  }, [clip.trimEndMs, durMs])
  const clampTrimEnd = useCallback((v: number) => {
    const nv = Math.max(0, Math.min(v, (durMs ?? 0) - 20))
    if (nv + clip.trimStartMs >= (durMs ?? 0)) return durMs ? durMs - 20 - clip.trimStartMs : 0
    return nv
  }, [clip.trimStartMs, durMs])
  const clampFade = useCallback((v: number) => {
    const maxMs = Math.max(10, effectiveDuration - 10)
    return Math.max(0, Math.min(v, maxMs))
  }, [effectiveDuration])
  const clampSelection = useCallback((startMs: number, endMs: number) => {
    let start = clampMs(Math.min(startMs, endMs), 0, effectiveDuration)
    let end = clampMs(Math.max(startMs, endMs), 0, effectiveDuration)
    if (end - start < 10) {
      if (end >= effectiveDuration) start = Math.max(0, end - 10)
      else end = Math.min(effectiveDuration, start + 10)
    }
    return { startMs: start, endMs: end }
  }, [effectiveDuration])
  const selectedRegion = selection ?? { startMs: 0, endMs: Math.min(500, effectiveDuration) }
  const selectedDuration = Math.max(10, selectedRegion.endMs - selectedRegion.startMs)
  const regionPercent = (ms: number) => `${(ms / Math.max(1, effectiveDuration)) * 100}%`

  const pointToMs = useCallback((clientX: number) => {
    if (!laneRef.current) return 0
    const rect = laneRef.current.getBoundingClientRect()
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
    return ratio * effectiveDuration
  }, [effectiveDuration])

  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      if (!activeHandle.current || !laneRef.current || !durMs) return

      const rect = laneRef.current.getBoundingClientRect()
      const offsetX = e.clientX - rect.left
      const width = rect.width
      const msPerPx = effectiveDuration / width

      const handle = activeHandle.current
      if (handle === 'leftTrim') {
        onUpdate(clip.clipId, { trimStartMs: clampTrimStart(clip.trimStartMs + offsetX * msPerPx) })
      } else if (handle === 'rightTrim') {
        onUpdate(clip.clipId, { trimEndMs: clampTrimEnd(clip.trimEndMs + (width - offsetX) * msPerPx) })
      } else if (handle === 'leftFade') {
        onUpdate(clip.clipId, { fadeInMs: clampFade(clip.fadeInMs + offsetX * msPerPx) })
      } else if (handle === 'rightFade') {
        onUpdate(clip.clipId, { fadeOutMs: clampFade(clip.fadeOutMs + (width - offsetX) * msPerPx) })
      }
    },
    [clip, durMs, effectiveDuration, onUpdate, clampTrimStart, clampTrimEnd, clampFade],
  )

  const handleMouseUp = useCallback(() => {
    activeHandle.current = null
    window.removeEventListener('mousemove', handleMouseMove)
    window.removeEventListener('mouseup', handleMouseUp)
  }, [handleMouseMove])

  const startDrag = (handle: 'leftTrim' | 'rightTrim' | 'leftFade' | 'rightFade') => {
    activeHandle.current = handle
    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
  }

  const handleSelectionMove = useCallback(
    (e: MouseEvent) => {
      if (!selectionDrag.current) return
      setSelection(clampSelection(selectionDrag.current.startMs, pointToMs(e.clientX)))
    },
    [clampSelection, pointToMs],
  )

  const handleSelectionUp = useCallback(() => {
    selectionDrag.current = null
    window.removeEventListener('mousemove', handleSelectionMove)
    window.removeEventListener('mouseup', handleSelectionUp)
  }, [handleSelectionMove])

  const startSelection = (e: ReactMouseEvent<HTMLDivElement>) => {
    if (!durMs) return
    e.preventDefault()
    e.stopPropagation()
    const startMs = pointToMs(e.clientX)
    selectionDrag.current = { startMs }
    setSelection(clampSelection(startMs, startMs + 10))
    window.addEventListener('mousemove', handleSelectionMove)
    window.addEventListener('mouseup', handleSelectionUp)
  }

  const addRegionEdit = (edit: RegionEdit) => onAddRegionEdit(clip.clipId, edit)

  const applyGain = () => {
    addRegionEdit({
      id: makeRegionEditId('gain'),
      type: 'gain',
      startMs: selectedRegion.startMs,
      endMs: selectedRegion.endMs,
      gainDb,
      fadeInMs: regionFadeInMs,
      fadeOutMs: regionFadeOutMs,
    })
  }

  const applyMute = () => {
    addRegionEdit({
      id: makeRegionEditId('mute'),
      type: 'mute',
      startMs: selectedRegion.startMs,
      endMs: selectedRegion.endMs,
      fadeInMs: regionFadeInMs,
      fadeOutMs: regionFadeOutMs,
    })
  }

  const applyDelete = () => {
    addRegionEdit({
      id: makeRegionEditId('delete'),
      type: 'delete',
      startMs: selectedRegion.startMs,
      endMs: selectedRegion.endMs,
    })
  }

  const applyFade = () => {
    addRegionEdit({
      id: makeRegionEditId('fade'),
      type: 'fade',
      startMs: selectedRegion.startMs,
      endMs: selectedRegion.endMs,
      fadeInMs: regionFadeInMs,
      fadeOutMs: regionFadeOutMs,
    })
  }

  const insertSilenceAt = (placement: 'before' | 'after') => {
    addRegionEdit({
      id: makeRegionEditId('insert_silence'),
      type: 'insert_silence',
      atMs: placement === 'before' ? selectedRegion.startMs : selectedRegion.endMs,
      durationMs: silenceMs,
    })
  }

  const describeEdit = (edit: RegionEdit) => {
    if (edit.type === 'insert_silence') return `silence ${edit.durationMs ?? 0}ms at ${edit.atMs ?? 0}ms`
    if (edit.type === 'gain') return `gain ${edit.gainDb ?? 0}dB ${edit.startMs ?? 0}-${edit.endMs ?? 0}ms`
    return `${edit.type} ${edit.startMs ?? 0}-${edit.endMs ?? 0}ms`
  }

  const fadeOverlay = (side: 'left' | 'right', ms: number) => {
    if (!ms || ms <= 0) return null
    const widthPct = Math.min(100, (ms / Math.max(1, effectiveDuration)) * 100)
    return (
      <div
        data-testid={`stitch-fade-overlay-${side}`}
        className={cn(
          'pointer-events-none absolute inset-y-0',
          side === 'left' ? 'left-0' : 'right-0',
        )}
        style={{
          width: `${widthPct}%`,
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
      className={cn(
        "group relative flex w-full min-w-0 flex-col overflow-hidden rounded-lg border border-border/50 bg-muted/10 p-1.5",
        isReordering && 'cursor-grab',
      )}
    >
      <div className="flex items-center justify-between gap-2 px-1.5 pt-1 pb-1">
        {editingText ? (
          <input
            ref={textInputRef}
            type="text"
            value={draftText}
            onChange={(e) => setDraftText(e.target.value)}
            onBlur={commitText}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                commitText()
              } else if (e.key === 'Escape') {
                e.preventDefault()
                cancelEditText()
              }
            }}
            className="min-w-0 flex-1 rounded border border-cyan-500/40 bg-muted/40 px-1.5 py-0.5 text-xs font-medium text-foreground outline-none"
            aria-label="Edit clip text"
          />
        ) : (
          <span
            className="min-w-0 flex-1 cursor-text truncate text-xs font-medium text-foreground hover:text-cyan-400"
            title={`${clip.text ?? ''}\\n(click to edit reference text)`}
            onClick={beginEditText}
          >
            {clip.text || '(untitled — click to add reference text)'}
          </span>
        )}
        <div className="flex shrink-0 items-center gap-1.5">
          <select
            value={clip.prosodyMode ?? 'auto'}
            onChange={(event) => onUpdate(clip.clipId, { prosodyMode: event.currentTarget.value as StitchPlanClip['prosodyMode'] })}
            onMouseDown={(event) => event.stopPropagation()}
            className="rounded border border-border/50 bg-muted/50 px-1 py-0.5 text-[10px] text-muted-foreground"
            aria-label="Internal pacing repair mode"
            title="Repair internal blended sentence boundaries before stitching"
          >
            <option value="off">Repair off</option>
            <option value="auto">Repair auto</option>
            <option value="precise">Repair precise</option>
          </select>
          <button
            type="button"
            className="rounded px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-muted hover:text-foreground"
            onClick={() => setShowAdvanced((visible) => !visible)}
            aria-expanded={showAdvanced}
            data-testid="stitch-clip-edit-toggle"
          >
            {showAdvanced ? 'Hide edits' : 'Edit clip'}
          </button>
          {isReordering && (
            <div className="flex items-center text-muted-foreground/60">
              <GripVertical className="size-3.5" />
            </div>
          )}
          <button
            type="button"
            className="rounded p-0.5 text-muted-foreground hover:text-foreground"
            onClick={toggleClipPlay}
            disabled={!clip.sourceAudioBase64}
            aria-label={clipPlaying ? "Pause clip playback" : "Play clip playback"}
            title="Listen to just this segment"
          >
            {clipPlaying ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
          </button>
          <button
            type="button"
            className="rounded p-0.5 text-muted-foreground hover:text-destructive"
            onClick={() => onRemove(clip.clipId)}
            aria-label="Remove clip"
            title="Remove clip"
          >
            <X className="size-3.5" />
          </button>
        </div>
      </div>

      <div className="relative h-24 overflow-hidden rounded-md bg-black/40">
        <div ref={laneRef} className="relative h-full w-full" onMouseDown={startSelection}>
          <WaveformLane peaks={peaks} durMs={durMs} trimStartMs={clip.trimStartMs} trimEndMs={clip.trimEndMs} fadeInMs={clip.fadeInMs} fadeOutMs={clip.fadeOutMs} />
          {fadeOverlay('left', clip.fadeInMs)}
          {fadeOverlay('right', clip.fadeOutMs)}

          {regionEdits.map((edit) => {
            if (edit.type === 'insert_silence') {
              return (
                <div
                  key={edit.id}
                  className="pointer-events-none absolute inset-y-2 w-1 rounded-full bg-sky-300/70"
                  style={{ left: regionPercent(edit.atMs ?? 0) }}
                  title={describeEdit(edit)}
                />
              )
            }
            const left = regionPercent(edit.startMs ?? 0)
            const width = regionPercent(Math.max(10, (edit.endMs ?? 0) - (edit.startMs ?? 0)))
            return (
              <div
                key={edit.id}
                className={cn(
                  'pointer-events-none absolute inset-y-1 rounded-sm border',
                  edit.type === 'delete' && 'border-destructive/60 bg-destructive/20',
                  edit.type === 'mute' && 'border-zinc-300/40 bg-zinc-950/55',
                  edit.type === 'gain' && 'border-warning/50 bg-warning/15',
                  edit.type === 'fade' && 'border-cyan-300/50 bg-gradient-to-r from-transparent via-cyan-300/20 to-transparent',
                )}
                style={{ left, width }}
                title={describeEdit(edit)}
              />
            )
          })}

          {selection && (
            <div
              className="pointer-events-none absolute inset-y-0 rounded-sm border border-cyan-300/80 bg-cyan-300/15"
              style={{ left: regionPercent(selection.startMs), width: regionPercent(selection.endMs - selection.startMs) }}
            >
              <div className="absolute inset-y-0 left-0 w-1 bg-cyan-300" />
              <div className="absolute inset-y-0 right-0 w-1 bg-cyan-300" />
            </div>
          )}

          {durMs && (
            <>
              <div
                className="absolute inset-y-0 left-0 w-[2px] cursor-ew-resize bg-cyan-500/50 hover:bg-cyan-400 transition-colors"
                onMouseDown={(e) => {
                  e.stopPropagation()
                  startDrag('leftTrim')
                }}
              />
              <div
                className="absolute inset-y-0 right-0 w-[2px] cursor-ew-resize bg-cyan-500/50 hover:bg-cyan-400 transition-colors"
                onMouseDown={(e) => {
                  e.stopPropagation()
                  startDrag('rightTrim')
                }}
              />
              <div
                className="absolute inset-y-0 w-[2px] cursor-ew-resize bg-cyan-500/50 hover:bg-cyan-400 transition-colors"
                style={{ left: `${(clip.fadeInMs / effectiveDuration) * 100}%` }}
                onMouseDown={(e) => {
                  e.stopPropagation()
                  startDrag('leftFade')
                }}
              />
              <div
                className="absolute inset-y-0 w-[2px] cursor-ew-resize bg-cyan-500/50 hover:bg-cyan-400 transition-colors"
                style={{ right: `${(clip.fadeOutMs / effectiveDuration) * 100}%` }}
                onMouseDown={(e) => {
                  e.stopPropagation()
                  startDrag('rightFade')
                }}
              />
            </>
          )}
        </div>
      </div>

      {showAdvanced && (
        <>
          <div className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1.5">
            <MsStepper label="Trim start" value={clip.trimStartMs} min={0} max={durMs ?? 0} step={10} onChange={(v) => onUpdate(clip.clipId, { trimStartMs: clampTrimStart(v) })} />
            <MsStepper label="Trim end" value={clip.trimEndMs} min={0} max={durMs ?? 0} step={10} onChange={(v) => onUpdate(clip.clipId, { trimEndMs: clampTrimEnd(v) })} />
            <MsStepper label="Fade in" value={clip.fadeInMs} min={0} max={2000} step={10} onChange={(v) => onUpdate(clip.clipId, { fadeInMs: clampFade(v) })} />
            <MsStepper label="Fade out" value={clip.fadeOutMs} min={0} max={2000} step={10} onChange={(v) => onUpdate(clip.clipId, { fadeOutMs: clampFade(v) })} />
          </div>

          <div className="mt-2 rounded-md border border-border/50 bg-black/20 p-2">
            <div className="grid grid-cols-3 gap-1.5">
              <MsStepper label="Region start" value={selectedRegion.startMs} min={0} max={effectiveDuration} step={10} onChange={(v) => setSelection(clampSelection(v, selectedRegion.endMs))} compact />
              <MsStepper label="Region end" value={selectedRegion.endMs} min={0} max={effectiveDuration} step={10} onChange={(v) => setSelection(clampSelection(selectedRegion.startMs, v))} compact />
              <span className="self-center text-[10px] font-mono text-muted-foreground">{selectedDuration}ms</span>
              <MsStepper label="Gain" value={gainDb} min={-24} max={12} step={1} onChange={setGainDb} compact />
              <MsStepper label="Fade in" value={regionFadeInMs} min={0} max={500} step={5} onChange={setRegionFadeInMs} compact />
              <MsStepper label="Fade out" value={regionFadeOutMs} min={0} max={500} step={5} onChange={setRegionFadeOutMs} compact />
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <button type="button" className="inline-flex items-center gap-1 rounded bg-muted/70 px-2 py-1 text-[10px] text-foreground hover:bg-muted" onClick={applyGain} title="Apply gain to selected region"><Volume2 className="size-3" /> gain</button>
              <button type="button" className="inline-flex items-center gap-1 rounded bg-muted/70 px-2 py-1 text-[10px] text-foreground hover:bg-muted" onClick={applyMute} title="Mute selected region"><VolumeX className="size-3" /> mute</button>
              <button type="button" className="inline-flex items-center gap-1 rounded bg-muted/70 px-2 py-1 text-[10px] text-foreground hover:bg-muted" onClick={applyDelete} title="Delete selected region"><Trash2 className="size-3" /> delete</button>
              <button type="button" className="inline-flex items-center gap-1 rounded bg-muted/70 px-2 py-1 text-[10px] text-foreground hover:bg-muted" onClick={applyFade} title="Fade selected region"><ChevronUp className="size-3" /> fade</button>
              <button type="button" className="inline-flex items-center gap-1 rounded bg-muted/70 px-2 py-1 text-[10px] text-foreground hover:bg-muted" onClick={() => onSplitRegion(clip.clipId, selectedRegion.startMs, selectedRegion.endMs)} title="Split clip at selected region boundaries"><Scissors className="size-3" /> split</button>
              <MsStepper label="Silence" value={silenceMs} min={20} max={2000} step={10} onChange={setSilenceMs} compact />
              <button type="button" className="rounded bg-muted/70 px-2 py-1 text-[10px] text-foreground hover:bg-muted" onClick={() => insertSilenceAt('before')} title="Insert silence before selected region">+ before</button>
              <button type="button" className="rounded bg-muted/70 px-2 py-1 text-[10px] text-foreground hover:bg-muted" onClick={() => insertSilenceAt('after')} title="Insert silence after selected region">+ after</button>
            </div>
            {regionEdits.length > 0 && (
              <div className="mt-2 flex flex-col gap-1 border-t border-border/40 pt-2">
                {regionEdits.map((edit) => (
                  <div key={edit.id} data-testid="stitch-region-edit" className="flex items-center justify-between gap-2 text-[10px] text-muted-foreground">
                    <span className="truncate">{describeEdit(edit)}</span>
                    <button type="button" className="shrink-0 rounded p-0.5 hover:bg-muted hover:text-foreground" onClick={() => onRemoveRegionEdit(clip.clipId, edit.id)} title="Remove edit">
                      <X className="size-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

// Independent, always-visible control for the gap between two adjacent clips —
// rendered between clips in the timeline (not nested inside either clip's card),
// so it reads as belonging to \"the space between\" rather than to one clip.
function GapControl({
  gapIndex,
  paddingMs,
  onSetPadding,
}: {
  gapIndex: number
  paddingMs: number
  onSetPadding: (gapIndex: number, ms: number) => void
}) {
  if (paddingMs <= 0) {
    return (
      <button
        type="button"
        onClick={() => onSetPadding(gapIndex, 200)}
        title="Add a gap between these clips"
        className="mt-3 flex h-24 w-8 shrink-0 items-center justify-center rounded border border-dashed border-border/40 text-sm text-muted-foreground/50 hover:border-cyan-500/50 hover:text-cyan-400"
      >
        +
      </button>
    )
  }
  return (
    <div
      className="mt-3 flex h-24 shrink-0 flex-col items-center justify-center gap-1.5 rounded border border-dashed border-cyan-500/40 bg-cyan-500/5 px-1.5"
      style={{ flex: `${Math.max(1, paddingMs)} 0 auto`, minWidth: 56 }}
      title={`${paddingMs}ms gap`}
    >
      <span className="text-[10px] uppercase text-muted-foreground">gap</span>
      <MsStepper label="gap" value={paddingMs} min={0} max={3000} step={10} onChange={(v) => onSetPadding(gapIndex, v)} compact />
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
    <div className={cn('flex min-w-0 items-center gap-1', compact && 'gap-0.5')} title={label}>
      {!compact && <span className="min-w-0 flex-1 truncate text-[10px] uppercase text-muted-foreground/70">{label}</span>}
      <button type="button" className="inline-flex size-5 shrink-0 items-center justify-center rounded bg-muted/70 text-xs text-muted-foreground hover:bg-muted" aria-label={`Decrease ${label}`} onClick={() => onChange(Math.max(min, value - step))}>−</button>
      <span className="inline-flex min-w-[28px] shrink-0 justify-center text-xs font-mono tabular-nums text-foreground">{value}</span>
      <button type="button" className="inline-flex size-5 shrink-0 items-center justify-center rounded bg-muted/70 text-xs text-muted-foreground hover:bg-muted" aria-label={`Increase ${label}`} onClick={() => onChange(Math.min(max, value + step))}>+</button>
    </div>
  )
}


/* ---------- main component ---------- */

interface StitchTimelineProps {
  totalDurationMs: number
  isPreviewStale: boolean
  library: SegmentMeta[]
  onInsertFromLibrary: (segs: SegmentMeta[], afterClipId: string | null) => void
  session: StitchPlanSession
  voiceLibrary?: VoiceMeta[]
  onInsertVoiceFromLibrary?: (voices: VoiceMeta[], afterClipId: string | null) => void
}

export const StitchTimeline = memo(function StitchTimeline({
  totalDurationMs: _totalDurationMs,
  isPreviewStale: _isPreviewStale,
  library,
  onInsertFromLibrary,
  session,
  voiceLibrary,
  onInsertVoiceFromLibrary,
}: StitchTimelineProps) {
  const reducedMotion = useReducedMotion()
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
  // for the empty-timeline case, which threw \"rendered more hooks than previous render\" (React
  // error #310) the instant a first clip was inserted (0 clips -> hook skipped, 1+ clips -> hook
  // ran), crashing the page. Stitch Studio hits the empty state on first load, so it surfaced
  // this immediately; OmniVoice's editor rarely opened with zero clips, so it went unnoticed.
  const effectiveTotalMs = useMemo(() => {
    let sum = 0
    for (const c of clips) {
      sum += clipEffectiveDurationMs(c)
    }
    sum += (paddingMs || []).reduce((a, b) => a + b, 0)
    return Math.max(1, sum)
  }, [clips, paddingMs])

  const autoPace = useCallback(() => {
    setPaddingMs(clips.slice(0, -1).map((clip) => {
      const text = (clip.text ?? '').trim()
      if (/[.!?]["')\]]?$/.test(text)) return 520
      if (/[,;:]["')\]]?$/.test(text)) return 260
      return 90
    }))
  }, [clips, setPaddingMs])

  const [rulerRef, rulerWidthPx] = useElementWidth<HTMLDivElement>()

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
            />
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="relative flex min-w-0 flex-col gap-2">
      {/* Library insert bar */}
      {(library.length > 0 || hasVoiceLibrary) && (
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-muted-foreground">
            Drag to reorder clips, trim edges, and adjust gaps to build your 10–15s reference voice.
          </span>
          <div className="flex shrink-0 items-center gap-2">
            <button type="button" className="inline-flex h-8 items-center gap-1.5 rounded border border-border bg-background px-2.5 text-xs hover:bg-muted" onClick={autoPace}>
              <Gauge className="size-3.5" /> Auto-pace
            </button>
            {(library.length > 0 || hasVoiceLibrary) && (
              <SegmentBrowserModal
                segments={library}
                onInsertSegments={onInsertFromLibrary}
                voices={voiceLibrary}
                onInsertVoices={onInsertVoiceFromLibrary}
                insertAfterClipId={selectedClipId}
              />
            )}
          </div>
        </div>
      )}

      {/* Timeline */}
      <div className="relative flex items-stretch gap-0 overflow-x-auto overflow-y-visible pl-5" style={{ minWidth: 0 }}>
        {effectiveTotalMs > 0 && (
          <div ref={rulerRef} className="pointer-events-none absolute inset-x-5 top-0 flex h-4 items-start border-b border-border/30">
            {(rulerWidthPx > 0
              ? createTimeTicks({
                  durationSeconds: effectiveTotalMs / 1000,
                  pixelsPerSecond: rulerWidthPx / (effectiveTotalMs / 1000),
                  widthPx: rulerWidthPx,
                })
              : []
            ).map((tick) => (
              <div
                key={tick.seconds}
                data-testid="stitch-ruler-tick"
                data-seconds={tick.seconds}
                className="absolute text-[10px] font-mono text-muted-foreground/50"
                style={{ left: `${(tick.x / rulerWidthPx) * 100}%`, transform: 'translateX(-50%)' }}
              >
                {tick.label}
              </div>
            ))}
          </div>
        )}

        <Reorder.Group
          axis="x"
          values={clips}
          onReorder={handleReorder}
          className="mt-3 flex w-max min-w-full items-start gap-0"
        >
          {clips.map((clip, i) => (
            <div key={clip.clipId} className="flex shrink-0 items-start gap-4">
              {i > 0 && (
                <GapControl gapIndex={i - 1} paddingMs={paddingMs[i - 1] || 0} onSetPadding={setPadding} />
              )}
              <Reorder.Item
                value={clip}
                data-testid="stitch-clip"
                data-clip-id={clip.clipId}
                onClick={() => setSelectedClipId((prev) => (prev === clip.clipId ? null : clip.clipId))}
                className={cn(
                  'group relative flex flex-col rounded-md',
                  selectedClipId === clip.clipId && 'ring-2 ring-cyan-500/70',
                )}
                style={{ flex: `${Math.max(300, clipEffectiveDurationMs(clip))} 0 auto`, minWidth: 320 }}
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
                  onRemove={removeClip}
                  onUpdate={updateClip}
                  regionEdits={regionEditsByClip[clip.clipId] ?? []}
                  onAddRegionEdit={onAddRegionEdit}
                  onRemoveRegionEdit={onRemoveRegionEdit}
                  onSplitRegion={splitRegion}
                  isReordering
                  reducedMotion={reducedMotion}
                />
              </Reorder.Item>
            </div>
          ))}
        </Reorder.Group>
      </div>
    </div>
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
            <SliderField label="Segment target" value={dsp.segmentTargetDbfs} min={-40} max={-10} step={0.5} format={(v) => `${v} dBFS`} onChange={(v) => setDsp({ segmentTargetDbfs: v })} />
            <SliderField label="Final target" value={dsp.finalTargetDbfs} min={-40} max={-10} step={0.5} format={(v) => `${v} dBFS`} onChange={(v) => setDsp({ finalTargetDbfs: v })} />
            <SliderField label="Final ceiling" value={dsp.finalCeilingDb} min={-6} max={0} step={0.2} format={(v) => `${v} dB`} onChange={(v) => setDsp({ finalCeilingDb: v })} />
            <SliderField label="Crossfade" value={dsp.crossfadeMs} min={0} max={400} step={5} format={(v) => `${v} ms`} onChange={(v) => setDsp({ crossfadeMs: v })} />
            <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">
              Pacing style
              <select value={dsp.prosodyStylePreset} onChange={(e) => setDsp({ prosodyStylePreset: e.currentTarget.value as typeof dsp.prosodyStylePreset })} className="rounded border border-border bg-background px-2 py-1 text-xs text-foreground">
                {['Neutral', 'Storyteller', 'Calm', 'Energetic', 'Broadcast', 'Clean'].map((name) => <option key={name} value={name}>{name}</option>)}
              </select>
            </label>
            <SliderField label="Pace" value={dsp.paceMultiplier} min={0.5} max={2} step={0.05} format={(v) => `${v.toFixed(2)}×`} onChange={(v) => setDsp({ paceMultiplier: v })} />
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
  const [showDsp, setShowDsp] = useState(false)
  const [isNormalizingPacing, setIsNormalizingPacing] = useState(false)

  const preview = useStitchPreview(plan)
  const planHash = useMemo(() => hashStitchPlan(plan), [plan])

  const handleSave = useCallback(async () => {
    if (props.surface !== 'studio') return
    preview.cancel()
    const segments = clips.map((c) => c.text?.trim()).filter((t): t is string => !!t)
    await props.onSave(planStateToPayload(plan), segments)
  }, [props, plan, clips, preview])

  const normalizePacing = useCallback(async () => {
    if (!clips.length) return
    setIsNormalizingPacing(true)
    try {
      const result = await getStitchPacingTargets({
        transcripts: clips.map((clip) => clip.text ?? ''),
        stylePreset: dsp.prosodyStylePreset,
        paceMultiplier: dsp.paceMultiplier,
        pauseOffsetMs: dsp.pauseOffsetMs,
      })
      session.setPadding(result.padding_ms)
      session.setClips((current) => current.map((clip) => ({ ...clip, prosodyMode: 'auto' })))
    } catch {
      // Surfaced via the preview's own error state on the next render attempt.
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
            <PreviewPlayer src={preview.url} />
          ) : (
            <div className="flex h-10 items-center px-3 text-xs text-muted-foreground">
              Generating preview…
            </div>
          )}
        </div>
      )}

      <div className="mt-1 flex items-center justify-between border-t border-border/60 pt-3">
        {props.surface === 'studio' ? (
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              data-testid="stitch-save-voice"
              onClick={handleSave}
              disabled={preview.isRendering || clips.length === 0}
              className="btn-brand inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 text-xs font-medium"
              title="This will be used as a reusable cloning source for text-to-speech."
            >
              Save as reference voice
            </button>
          </div>
        ) : (
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
        )}
        <div className="text-[10px] text-muted-foreground">{(totalMs / 1000).toFixed(1)}s total</div>
      </div>
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
