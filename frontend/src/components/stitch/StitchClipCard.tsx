// Extracted from StitchTimeline.tsx (Packet 6): one clip's waveform, trim/fade handles,
// selection, and region-edit panel. Trim, fade, and selection gestures are pointer
// transactions -- setPointerCapture on the handle, {pointerId, startClientX, startValue}
// frozen once at pointerdown, and the semantic value (clip.trimStartMs etc.) committed once
// on pointerup/cancel. During the drag only local `dragPreview` state changes (RAF-throttled),
// so mid-drag movement never re-triggers the store write / debounced preview render pipeline
// on every pointermove -- only the final value does. Using pointer events (not mouse events)
// means touch and pen produce the same gesture, and setPointerCapture keeps receiving
// move/up even if the cursor leaves the handle mid-drag.
import { memo, useCallback, useEffect, useLayoutEffect, useState, useRef, type PointerEvent as ReactPointerEvent } from 'react'
import { ChevronUp, Crosshair, GripVertical, Pencil, RotateCcw, X, Play, Pause, Scissors, Trash2, Volume2, VolumeX } from 'lucide-react'
import { type StitchPlanClip } from '@/store'
import { cn } from '@/lib/utils'
import { clipEffectiveDurationMs, type StitchRegionEdit } from '@/lib/stitchPlan'
import { formatMsValue } from '@/lib/timeAxis'
import { getClipAudioAnalysis, type AudioEnvelope } from '@/lib/waveform'
import { NUMERIC_CONTROL_FOCUS_CLASS, NUMERIC_CONTROL_UNIT_CLASS, useDragScrubValue } from '@/hooks/useDragScrubValue'
import { WaveformLane } from '../waveform/WaveformLane'
import * as ContextMenu from '../ui/context-menu'

type RegionEdit = StitchRegionEdit
type HandleKind = 'leftTrim' | 'rightTrim' | 'leftFade' | 'rightFade'

function clampMs(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, Math.round(v)))
}

function makeRegionEditId(type: RegionEdit['type']): string {
  return `${type}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}
export function MsStepper({
  label,
  value,
  min,
  max,
  step,
  onChange,
  compact,
  testId,
  defaultValue,
  controlName,
  editorRef,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  onChange: (v: number) => void
  compact?: boolean
  testId?: string
  /** N1 double-click reset target. */
  defaultValue?: number
  /** Shared numeric-control grammar (S4): names the control for the tab-order/focus-ring
   * contract, so trim/fade pairs group as `trim` and `fade` in the tab walk. */
  controlName?: 'trim' | 'fade'
  /** Exposes the typed-entry opener so a context menu can focus this control's editor. */
  editorRef?: React.MutableRefObject<(() => void) | null>
}) {
  const rootRef = useRef<HTMLDivElement | null>(null)
  const {
    editing,
    draftText,
    setDraftText,
    beginEdit,
    commitEdit,
    nudge,
    displayValue,
    beginScrub,
    handleKeyDown,
    handleDoubleClick,
    wheelTargetRef,
  } = useDragScrubValue({
    value,
    min,
    max,
    step,
    onChange,
    dragScale: (max - min) / 200,
    dragThreshold: 2,
    defaultValue,
    wheel: true,
  })
  const unit = formatMsValue(displayValue)
  const inputRef = useRef<HTMLInputElement | null>(null)

  // Children's layout effects run before the parent's, so a card that asks for the editor in
  // its own layout effect always finds this ref populated.
  useLayoutEffect(() => {
    if (!editorRef) return
    editorRef.current = () => {
      beginEdit()
      // The input mounts on the next commit and the context menu's close sequence (which
      // restores focus to the trigger) runs in between -- so focus after both.
      window.setTimeout(() => inputRef.current?.focus(), 0)
    }
    return () => {
      editorRef.current = null
    }
  }, [editorRef, beginEdit])

  // Native capture-phase pointerdown: the stepper sits inside the clip's Reorder.Item,
  // whose own drag listener is a native bubble-phase listener on the card element. A React
  // (delegated) handler cannot stop it, so the scrub start must be native and capture-phase
  // and must stop propagation before the card's listener runs -- otherwise the card also
  // follows the pointer while the value scrubs.
  useEffect(() => {
    const element = rootRef.current
    if (!element) return
    const onPointerDown = (event: PointerEvent) => {
      // The −/+ nudge buttons and the typed-entry input keep their own pointer semantics:
      // a press on them must neither start a scrub nor block the card's reorder drag.
      if ((event.target as HTMLElement).closest('button, input')) return
      // Anywhere else on the control (label, value, track) scrubs; a no-travel release
      // on the value span is a click-to-type.
      beginScrub(event, element, { openEditorOnRelease: (event.target as HTMLElement).hasAttribute('data-testid') })
    }
    element.addEventListener('pointerdown', onPointerDown, { capture: true })
    return () => element.removeEventListener('pointerdown', onPointerDown, { capture: true })
    // beginScrub is identity-stable (reads props through latestRef internally).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div
      ref={(node) => {
        rootRef.current = node
        wheelTargetRef.current = node
      }}
      data-testid={testId ? `${testId}-row` : undefined}
      data-numeric-control={controlName}
      tabIndex={0}
      role="group"
      aria-label={label}
      className={cn(
        'flex min-w-0 cursor-ew-resize touch-none select-none items-center gap-1 rounded',
        compact && 'gap-0.5',
        NUMERIC_CONTROL_FOCUS_CLASS,
      )}
      title={label}
      onKeyDown={handleKeyDown}
      onDoubleClick={handleDoubleClick}
    >
      {!compact && <span className="min-w-0 flex-1 truncate text-[10px] uppercase text-muted-foreground/70">{label}</span>}
      <button type="button" tabIndex={-1} className="inline-flex size-5 shrink-0 items-center justify-center rounded bg-muted/70 text-xs text-muted-foreground hover:bg-muted" aria-label={`Decrease ${label}`} onClick={() => nudge(-step)} onPointerDown={(e) => e.stopPropagation()}>−</button>
      {editing ? (
        <input
          ref={inputRef}
          type="text"
          inputMode="decimal"
          data-testid={testId}
          value={draftText}
          aria-label={label}
          onChange={(event) => setDraftText(event.target.value)}
          onBlur={commitEdit}
          onPointerDown={(event) => event.stopPropagation()}
          className="w-12 rounded border border-cyan-500/40 bg-muted/40 px-1 text-center font-mono tabular-nums text-foreground outline-none"
          autoFocus
        />
      ) : (
        <>
          <span
            data-testid={testId}
            className="inline-flex min-w-[28px] shrink-0 justify-center font-mono tabular-nums text-foreground"
          >
            {unit.text}
          </span>
          <span data-testid={testId ? `${testId}-unit` : undefined} className={NUMERIC_CONTROL_UNIT_CLASS}>
            {unit.unit}
          </span>
        </>
      )}
      <button type="button" tabIndex={-1} className="inline-flex size-5 shrink-0 items-center justify-center rounded bg-muted/70 text-xs text-muted-foreground hover:bg-muted" aria-label={`Increase ${label}`} onClick={() => nudge(step)} onPointerDown={(e) => e.stopPropagation()}>+</button>
    </div>
  )
}

export const StitchClipCard = memo(function StitchClipCard({
  clip,
  onRemove,
  onUpdate,
  regionEdits,
  onAddRegionEdit,
  onRemoveRegionEdit,
  onSplitRegion,
  isReordering,
  isSelected,
  isWidthClamped,
  isRangePlaying,
  onPlayRange,
  rangePlayReady = true,
  scaleAbs = null,
  showPeakReadout = false,
}: {
  clip: StitchPlanClip
  onRemove: (clipId: string) => void
  onUpdate: (clipId: string, patch: Partial<StitchPlanClip>) => void
  regionEdits: RegionEdit[]
  onAddRegionEdit: (clipId: string, edit: RegionEdit) => void
  onRemoveRegionEdit: (clipId: string, editId: string) => void
  onSplitRegion: (clipId: string, startMs: number, endMs: number) => void
  isReordering?: boolean
  isSelected?: boolean
  isWidthClamped?: boolean
  /** Whether this clip's bounded range is the one currently playing on the shared transport. */
  isRangePlaying: boolean
  /** Plays/pauses this clip's span on the shared transport -- never creates its own Audio.
   * The card supplies its own clipId at click time so the timeline can pass one stable
   * callback to every memoized card. */
  onPlayRange: (clipId: string) => void
  /** False until the shared transport has an audio element that knows its duration: before
   * that a range play would either silently do nothing or start a degenerate range. */
  rangePlayReady?: boolean
  /** Absolute amplitude at full lane height, shared by every clip on the timeline (B-P2), so a
   * quiet segment looks quiet next to its neighbours. */
  scaleAbs?: number | null
  /** Set when this is the only lane on screen: it then auto-fits, and the readout keeps the
   * fit from being mistaken for level. */
  showPeakReadout?: boolean
}) {
  const [envelope, setEnvelope] = useState<AudioEnvelope | null>(null)
  const [decodeFailed, setDecodeFailed] = useState(false)
  const [durMs, setDurMs] = useState<number | null>(null)
  const [editingText, setEditingText] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [draftText, setDraftText] = useState(clip.text ?? '')
  const [selection, setSelection] = useState<{ startMs: number; endMs: number } | null>(null)
  const [gainDb, setGainDb] = useState(-3)
  const [regionFadeInMs, setRegionFadeInMs] = useState(15)
  const [regionFadeOutMs, setRegionFadeOutMs] = useState(35)
  const [silenceMs, setSilenceMs] = useState(180)
  const textInputRef = useRef<HTMLInputElement | null>(null)
  const laneRef = useRef<HTMLDivElement>(null)
  // Context menu (A-5). The menu only wraps handlers this card already had: the session's
  // remove/update, the shared transport's range play, and the card's own text and numeric
  // editors. Actions that move focus themselves must stop Radix's FocusScope from pulling
  // focus back to the trigger when the menu unmounts.
  const focusManagedRef = useRef(false)
  const trimEditorRef = useRef<(() => void) | null>(null)
  const [numericFocusRequest, setNumericFocusRequest] = useState(0)

  // Visual-only preview during a handle drag: the committed clip.trimStartMs/etc. is only
  // written once, on pointerup, so intermediate pointermove events never thrash the store or
  // the debounced preview render.
  const [dragPreview, setDragPreview] = useState<{ kind: HandleKind; value: number } | null>(null)
  const dragStateRef = useRef<{ pointerId: number; kind: HandleKind; startClientX: number; startValue: number; msPerPx: number } | null>(null)
  const rafRef = useRef<number | null>(null)
  const selectionDragRef = useRef<{ pointerId: number } | null>(null)
  // Last trim/fade/selection gesture that actually moved, tagged by pointer and timestamp:
  // a click arriving right after such a gesture must not bubble to Reorder.Item and flip the
  // clip selection off mid-edit, while plain clicks (no move) keep selecting.
  const movedGestureRef = useRef<{ pointerId: number; at: number } | null>(null)

  useEffect(() => {
    if (editingText) textInputRef.current?.focus()
  }, [editingText])

  const beginEditText = () => {
    setDraftText(clip.text ?? '')
    setEditingText(true)
  }

  const menuEditText = () => {
    focusManagedRef.current = true
    beginEditText()
    // The menu's close sequence (which restores focus to the trigger) runs in the same
    // commit, so the caret has to be placed after it.
    window.setTimeout(() => textInputRef.current?.focus(), 0)
  }

  /** Opens the trim control's typed entry, expanding the edit panel first if it is collapsed. */
  const menuFocusNumericEditor = () => {
    focusManagedRef.current = true
    setShowAdvanced(true)
    // A counter, not a boolean: asking twice in a row must focus twice.
    setNumericFocusRequest((n) => n + 1)
  }

  useLayoutEffect(() => {
    if (numericFocusRequest === 0) return
    trimEditorRef.current?.()
  }, [numericFocusRequest])

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
    let dead = false
    if (!clip.sourceAudioBase64) return
    const assetKey = `clip:${clip.clipId}:${clip.sourceAudioBase64.length}`
    getClipAudioAnalysis(assetKey, clip.sourceAudioBase64, 48)
      .then((analysis) => {
        if (dead) return
        setDurMs(analysis.durationMs)
        setEnvelope(analysis.envelope)
        setDecodeFailed(analysis.decodeFailed)
      })
      .catch(() => {
        if (!dead) {
          setEnvelope(null)
          setDecodeFailed(true)
        }
      })
    return () => { dead = true }
  }, [clip.clipId, clip.sourceAudioBase64])

  const effectiveDuration = clipEffectiveDurationMs(clip)

  // A committed trim can shrink the effective window below an existing selection; clamp the
  // stored selection back into [0, effectiveDuration] so the region panel and its edits
  // never target audio outside the kept window.
  useEffect(() => {
    setSelection((prev) => {
      if (!prev) return prev
      const start = clampMs(Math.min(prev.startMs, prev.endMs), 0, effectiveDuration)
      const end = clampMs(Math.max(prev.startMs, prev.endMs), 0, effectiveDuration)
      return start === prev.startMs && end === prev.endMs ? prev : { startMs: start, endMs: end }
    })
  }, [effectiveDuration])

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

  const clampForKind = useCallback((kind: HandleKind, value: number) => {
    if (kind === 'leftTrim') return clampTrimStart(value)
    if (kind === 'rightTrim') return clampTrimEnd(value)
    if (kind === 'leftFade') return clampFade(value)
    return clampFade(value)
  }, [clampTrimStart, clampTrimEnd, clampFade])

  const startValueForKind = (kind: HandleKind) => {
    if (kind === 'leftTrim') return clip.trimStartMs
    if (kind === 'rightTrim') return clip.trimEndMs
    if (kind === 'leftFade') return clip.fadeInMs
    return clip.fadeOutMs
  }

  const patchKeyForKind = (kind: HandleKind): keyof StitchPlanClip =>
    kind === 'leftTrim' ? 'trimStartMs' : kind === 'rightTrim' ? 'trimEndMs' : kind === 'leftFade' ? 'fadeInMs' : 'fadeOutMs'

  const handlePointerMove = useCallback((e: PointerEvent) => {
    const state = dragStateRef.current
    if (!state || state.pointerId !== e.pointerId) return
    movedGestureRef.current = { pointerId: state.pointerId, at: performance.now() }
    const deltaMs = (e.clientX - state.startClientX) * state.msPerPx
    // Right-side handles (rightTrim/rightFade) invert the sign: dragging the right edge
    // rightward means *less* is trimmed/faded from the end.
    const signed = state.kind === 'rightTrim' || state.kind === 'rightFade' ? -deltaMs : deltaMs
    const next = clampForKind(state.kind, state.startValue + signed)
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(() => setDragPreview({ kind: state.kind, value: next }))
  }, [clampForKind])

  const endDrag = useCallback((e: PointerEvent) => {
    const state = dragStateRef.current
    if (!state || state.pointerId !== e.pointerId) return
    window.removeEventListener('pointermove', handlePointerMove)
    window.removeEventListener('pointerup', endDrag)
    window.removeEventListener('pointercancel', endDrag)
    dragStateRef.current = null
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    // Compute the committed value directly from this event's own clientX rather than reading
    // the rAF-throttled `dragPreview` state: a pointerup that follows its last pointermove
    // faster than one animation frame (routine for scripted/automated input, and possible for
    // a fast real gesture) would otherwise commit a stale, pre-drag value because the final
    // rAF-scheduled preview update never had a chance to run before this handler read it.
    const deltaMs = (e.clientX - state.startClientX) * state.msPerPx
    const signed = state.kind === 'rightTrim' || state.kind === 'rightFade' ? -deltaMs : deltaMs
    const finalValue = clampForKind(state.kind, state.startValue + signed)
    onUpdate(clip.clipId, { [patchKeyForKind(state.kind)]: finalValue } as Partial<StitchPlanClip>)
    setDragPreview(null)
  }, [handlePointerMove, onUpdate, clip.clipId, clampForKind])

  const startDrag = (kind: HandleKind) => (e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return
    e.stopPropagation()
    e.preventDefault()
    if (!laneRef.current || !durMs) return
    const rect = laneRef.current.getBoundingClientRect()
    dragStateRef.current = {
      pointerId: e.pointerId,
      kind,
      startClientX: e.clientX,
      startValue: startValueForKind(kind),
      msPerPx: effectiveDuration / Math.max(1, rect.width),
    }
    e.currentTarget.setPointerCapture(e.pointerId)
    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', endDrag)
    window.addEventListener('pointercancel', endDrag)
  }

  const handleSelectionPointerMove = useCallback((e: PointerEvent) => {
    if (!selectionDragRef.current || selectionDragRef.current.pointerId !== e.pointerId) return
    movedGestureRef.current = { pointerId: e.pointerId, at: performance.now() }
    setSelection((prev) => clampSelection(prev?.startMs ?? pointToMs(e.clientX), pointToMs(e.clientX)))
  }, [clampSelection, pointToMs])

  const endSelectionDrag = useCallback((e: PointerEvent) => {
    if (selectionDragRef.current?.pointerId !== e.pointerId) return
    selectionDragRef.current = null
    window.removeEventListener('pointermove', handleSelectionPointerMove)
    window.removeEventListener('pointerup', endSelectionDrag)
  }, [handleSelectionPointerMove])

  // The gesture listeners live on window and are normally removed by the end handlers, so
  // unmounting mid-drag (e.g. the clip gets removed) would leak them and leave a pending
  // rAF callback. Tear everything down on unmount -- and whenever the callback identities
  // change, since the window holds the instances captured by whichever render started the
  // gesture.
  useEffect(() => {
    return () => {
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', endDrag)
      window.removeEventListener('pointercancel', endDrag)
      window.removeEventListener('pointermove', handleSelectionPointerMove)
      window.removeEventListener('pointerup', endSelectionDrag)
      dragStateRef.current = null
      selectionDragRef.current = null
      movedGestureRef.current = null
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
    }
  }, [handlePointerMove, endDrag, handleSelectionPointerMove, endSelectionDrag])

  const startSelection = (e: ReactPointerEvent<HTMLDivElement>) => {
    // Only the primary button starts a gesture; the secondary one belongs to the context menu.
    if (e.button !== 0) return
    if (!durMs) return
    e.preventDefault()
    e.stopPropagation()
    const startMs = pointToMs(e.clientX)
    selectionDragRef.current = { pointerId: e.pointerId }
    setSelection(clampSelection(startMs, startMs + 10))
    e.currentTarget.setPointerCapture(e.pointerId)
    window.addEventListener('pointermove', handleSelectionPointerMove)
    window.addEventListener('pointerup', endSelectionDrag)
  }

  const addRegionEdit = (edit: RegionEdit) => onAddRegionEdit(clip.clipId, edit)

  const applyGain = () => addRegionEdit({ id: makeRegionEditId('gain'), type: 'gain', startMs: selectedRegion.startMs, endMs: selectedRegion.endMs, gainDb, fadeInMs: regionFadeInMs, fadeOutMs: regionFadeOutMs })
  const applyMute = () => addRegionEdit({ id: makeRegionEditId('mute'), type: 'mute', startMs: selectedRegion.startMs, endMs: selectedRegion.endMs, fadeInMs: regionFadeInMs, fadeOutMs: regionFadeOutMs })
  const applyDelete = () => addRegionEdit({ id: makeRegionEditId('delete'), type: 'delete', startMs: selectedRegion.startMs, endMs: selectedRegion.endMs })
  const applyFade = () => addRegionEdit({ id: makeRegionEditId('fade'), type: 'fade', startMs: selectedRegion.startMs, endMs: selectedRegion.endMs, fadeInMs: regionFadeInMs, fadeOutMs: regionFadeOutMs })
  const insertSilenceAt = (placement: 'before' | 'after') => addRegionEdit({ id: makeRegionEditId('insert_silence'), type: 'insert_silence', atMs: placement === 'before' ? selectedRegion.startMs : selectedRegion.endMs, durationMs: silenceMs })

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
        className={cn('pointer-events-none absolute inset-y-0', side === 'left' ? 'left-0' : 'right-0')}
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

  const trimStartMs = dragPreview?.kind === 'leftTrim' ? dragPreview.value : clip.trimStartMs
  const trimEndMs = dragPreview?.kind === 'rightTrim' ? dragPreview.value : clip.trimEndMs
  const fadeInMs = dragPreview?.kind === 'leftFade' ? dragPreview.value : clip.fadeInMs
  const fadeOutMs = dragPreview?.kind === 'rightFade' ? dragPreview.value : clip.fadeOutMs

  return (
    <ContextMenu.Root>
      <ContextMenu.Trigger asChild>
        <div
          className={cn(
            'group relative flex w-full min-w-0 flex-col overflow-hidden rounded-control border border-border/50 bg-muted/10 p-1.5',
            isReordering && 'cursor-grab',
            isSelected && 'ring-2 ring-cyan-500/70',
          )}
        >
          {isWidthClamped && (
            <div
              data-testid="stitch-clip-clamped"
              title={`Real width would be narrower than the minimum interactive size (effective duration ${effectiveDuration}ms)`}
              className="pointer-events-none absolute inset-0 z-10 rounded-control bg-[repeating-linear-gradient(45deg,rgba(6,182,212,0.12),rgba(6,182,212,0.12)_4px,transparent_4px,transparent_8px)]"
            />
          )}
          <div className="flex flex-col gap-1 px-1.5 pt-1 pb-1" onClick={(e) => e.stopPropagation()}>
            <div className="min-w-0">
              {editingText ? (
                <input
                  ref={textInputRef}
                  type="text"
                  value={draftText}
                  onChange={(e) => setDraftText(e.target.value)}
                  onBlur={commitText}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') { e.preventDefault(); commitText() }
                    else if (e.key === 'Escape') { e.preventDefault(); cancelEditText() }
                  }}
                  className="w-full min-w-0 rounded border border-cyan-500/40 bg-muted/40 px-1.5 py-0.5 text-xs font-medium text-foreground outline-none"
                  aria-label="Edit clip text"
                />
              ) : (
                <span
                  className="block min-w-0 cursor-text truncate text-xs font-medium text-foreground hover:text-cyan-400"
                  title={`${clip.text ?? ''}\n(click to edit reference text)`}
                  onClick={beginEditText}
                >
                  {clip.text || '(untitled — click to add reference text)'}
                </span>
              )}
            </div>
            <div className="flex items-center justify-end gap-1.5">
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
                onClick={() => onPlayRange(clip.clipId)}
                disabled={!clip.sourceAudioBase64 || !rangePlayReady || clipEffectiveDurationMs(clip) <= 0}
                aria-label={isRangePlaying ? 'Pause clip playback' : 'Play clip playback'}
                title={rangePlayReady ? 'Listen to just this segment' : 'Waiting for the preview to render'}
              >
                {isRangePlaying ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
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
            <div
              ref={laneRef}
              className="relative h-full w-full"
              onPointerDown={startSelection}
              onLostPointerCapture={(e) => endSelectionDrag(e.nativeEvent)}
              onClick={(e) => {
                const gesture = movedGestureRef.current
                if (gesture && gesture.pointerId === (e.nativeEvent as PointerEvent).pointerId && performance.now() - gesture.at < 500) {
                  e.stopPropagation()
                  movedGestureRef.current = null
                }
              }}
            >
              <WaveformLane envelope={envelope} scaleAbs={scaleAbs} showPeakReadout={showPeakReadout} failed={decodeFailed} durMs={durMs} trimStartMs={trimStartMs} trimEndMs={trimEndMs} fadeInMs={fadeInMs} fadeOutMs={fadeOutMs} timeGuideTestId="stitch-lane-time" />
              {fadeOverlay('left', fadeInMs)}
              {fadeOverlay('right', fadeOutMs)}

              {regionEdits.map((edit) => {
                if (edit.type === 'insert_silence') {
                  return (
                    <div key={edit.id} className="pointer-events-none absolute inset-y-2 w-1 rounded-full bg-sky-300/70" style={{ left: regionPercent(edit.atMs ?? 0) }} title={describeEdit(edit)} />
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
                    data-testid="stitch-trim-handle-left"
                    className="absolute inset-y-0 left-0 z-20 w-2 cursor-ew-resize touch-none bg-cyan-500/50 hover:bg-cyan-400 transition-colors"
                    onPointerDown={startDrag('leftTrim')}
                    onLostPointerCapture={(e) => endDrag(e.nativeEvent)}
                  />
                  <div
                    data-testid="stitch-trim-handle-right"
                    className="absolute inset-y-0 right-0 z-20 w-2 cursor-ew-resize touch-none bg-cyan-500/50 hover:bg-cyan-400 transition-colors"
                    onPointerDown={startDrag('rightTrim')}
                    onLostPointerCapture={(e) => endDrag(e.nativeEvent)}
                  />
                  {/* Trim handles render with a higher z-index than fade handles: at the default
                      fadeInMs/fadeOutMs = 0, a fade handle sits at the exact same pixel position as
                      its corresponding trim handle, and without this precedence the fade handle
                      (later in paint order) would always win the hit-test, making the trim handle
                      silently unreachable by pointer whenever fade is at its default. */}
                  <div
                    data-testid="stitch-fade-handle-left"
                    className="absolute inset-y-0 z-10 w-2 cursor-ew-resize touch-none bg-warning/50 hover:bg-warning transition-colors"
                    style={{ left: `${(fadeInMs / effectiveDuration) * 100}%` }}
                    onPointerDown={startDrag('leftFade')}
                    onLostPointerCapture={(e) => endDrag(e.nativeEvent)}
                  />
                  <div
                    data-testid="stitch-fade-handle-right"
                    className="absolute inset-y-0 z-10 w-2 cursor-ew-resize touch-none bg-warning/50 hover:bg-warning transition-colors"
                    style={{ right: `${(fadeOutMs / effectiveDuration) * 100}%` }}
                    onPointerDown={startDrag('rightFade')}
                    onLostPointerCapture={(e) => endDrag(e.nativeEvent)}
                  />
                </>
              )}
            </div>
          </div>

          {showAdvanced && (
            <>
              <div className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1.5" onClick={(e) => e.stopPropagation()}>
                <MsStepper testId="stitch-stepper-trim-start-value" controlName="trim" label="Trim start" editorRef={trimEditorRef} value={clip.trimStartMs} min={0} max={durMs ?? 0} step={10} defaultValue={0} onChange={(v) => onUpdate(clip.clipId, { trimStartMs: clampTrimStart(v) })} />
                <MsStepper testId="stitch-stepper-trim-end-value" controlName="trim" label="Trim end" value={clip.trimEndMs} min={0} max={durMs ?? 0} step={10} defaultValue={0} onChange={(v) => onUpdate(clip.clipId, { trimEndMs: clampTrimEnd(v) })} />
                <MsStepper testId="stitch-stepper-fade-in-value" controlName="fade" label="Fade in" value={clip.fadeInMs} min={0} max={2000} step={10} defaultValue={0} onChange={(v) => onUpdate(clip.clipId, { fadeInMs: clampFade(v) })} />
                <MsStepper testId="stitch-stepper-fade-out-value" controlName="fade" label="Fade out" value={clip.fadeOutMs} min={0} max={2000} step={10} defaultValue={0} onChange={(v) => onUpdate(clip.clipId, { fadeOutMs: clampFade(v) })} />
              </div>

              <div className="mt-2 rounded-md border border-border/50 bg-black/20 p-2" onClick={(e) => e.stopPropagation()}>
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
      </ContextMenu.Trigger>
      <ContextMenu.Content
        data-testid="stitch-context-menu"
        data-menu-scope="clip"
        // FocusScope restores focus to the trigger when a menu unmounts; the two actions that
        // hand focus to an editor must keep it there.
        onCloseAutoFocus={(event) => {
          if (!focusManagedRef.current) return
          focusManagedRef.current = false
          event.preventDefault()
        }}
      >
        <ContextMenu.Item
          data-testid="stitch-menu-play-range"
          disabled={!clip.sourceAudioBase64 || !rangePlayReady || clipEffectiveDurationMs(clip) <= 0}
          onSelect={() => onPlayRange(clip.clipId)}
        >
          {isRangePlaying ? <Pause className="size-3" /> : <Play className="size-3" />}
          {isRangePlaying ? 'Pause range' : 'Play range'}
        </ContextMenu.Item>
        <ContextMenu.Item data-testid="stitch-menu-edit-text" onSelect={menuEditText}>
          <Pencil className="size-3" />
          Edit text
        </ContextMenu.Item>
        <ContextMenu.Item
          data-testid="stitch-menu-reset-trim"
          onSelect={() => onUpdate(clip.clipId, { trimStartMs: 0, trimEndMs: 0, fadeInMs: 0, fadeOutMs: 0 })}
        >
          <RotateCcw className="size-3" />
          Reset trim and fades
        </ContextMenu.Item>
        <ContextMenu.Item data-testid="stitch-menu-focus-trim" onSelect={menuFocusNumericEditor}>
          <Crosshair className="size-3" />
          Focus trim editor
        </ContextMenu.Item>
        <ContextMenu.Separator />
        <ContextMenu.Item danger data-testid="stitch-menu-remove-clip" onSelect={() => onRemove(clip.clipId)}>
          <X className="size-3" />
          Remove clip
        </ContextMenu.Item>
      </ContextMenu.Content>
    </ContextMenu.Root>
  )
})
