// Shared drag-scrub value interaction for every visible numeric audio control, extracted
// from GapControl's established gesture (pointer capture, ladder snapping with Alt bypass,
// click-to-type with Enter/Escape/blur semantics, Shift-scaled keyboard increments) and
// generalized with the plugin-convention upgrades from plan A S1/N1/N2:
//   - Drag anywhere on the control body (window listeners + setPointerCapture; the value
//     commits once, on pointerup, computed from that event's own clientX).
//   - Shift during a drag = fine scale (dragScale / 4 by default); Alt bypasses snapping.
//   - Click-to-type via the `parse` grammar; Enter commits, Escape reverts, blur commits.
//   - Keyboard: ArrowUp/Down = `step`, Shift+ArrowUp/Down = `shiftStep` (default step * 10).
//   - N1: double-click on the control body (not on a button/input) restores `defaultValue`.
//   - N2: opt-in wheel nudge (one `step` per wheel event, Shift = step / 10 fine). Attached
//     as a native non-passive listener so it can preventDefault; never register it on the
//     timeline.
// The window-lifetime callbacks (move/up/cancel) are identity-stable and read all props
// through latestRef: re-renders mid-gesture (e.g. the rAF-throttled dragValue state) must
// never churn listener identities, or the cleanup effect would strip the in-flight
// gesture's listeners from the window.
import { useCallback, useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type MouseEvent as ReactMouseEvent } from 'react'

/** GapControl's original typed-value grammar, moved here verbatim: "200", "0.2s", "200ms". */
export function parseGapText(raw: string): number | null {
  const trimmed = raw.trim().toLowerCase()
  if (!trimmed) return null
  const msMatch = trimmed.match(/^(-?\d+(?:\.\d+)?)\s*ms$/)
  if (msMatch) return Math.round(parseFloat(msMatch[1]))
  const secondsMatch = trimmed.match(/^(-?\d+(?:\.\d+)?)\s*s$/)
  if (secondsMatch) return Math.round(parseFloat(secondsMatch[1]) * 1000)
  const bareMatch = trimmed.match(/^-?\d+(?:\.\d+)?$/)
  if (bareMatch) return Math.round(parseFloat(trimmed))
  return null
}

/** Tolerant grammar for controls whose units are not milliseconds: accepts an optional
 * suffix (ms, s, x, ×, db, dbfs — case-insensitive); only bare "s" scales (×1000). */
export function parseNumericText(raw: string): number | null {
  const trimmed = raw.trim().toLowerCase()
  if (!trimmed) return null
  const match = trimmed.match(/^(-?\d+(?:\.\d+)?)\s*(ms|s|x|×|db|dbfs)?$/)
  if (!match) return null
  const n = parseFloat(match[1])
  if (match[2] === 's') return n * 1000
  return n
}

/** The house focus ring (the same utilities Button/Input use), shared by every numeric
 * control so trim, fade, and gap cannot drift into three different focus affordances. The
 * controls are one tab stop each (WAI-ARIA spinbutton model): the root is focusable and
 * arrow keys adjust the value, so the −/+ buttons stay out of the tab order. */
export const NUMERIC_CONTROL_FOCUS_CLASS = 'outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50'

/** Shared styling for the unit label that follows a numeric control's value. */
export const NUMERIC_CONTROL_UNIT_CLASS = 'shrink-0 font-mono text-[10px] text-muted-foreground/70'

export interface UseDragScrubValueOptions {
  value: number
  min: number
  max: number
  step: number
  onChange: (v: number) => void
  /** Value units per dragged pixel (GapControl: 1000 / pixelsPerSecond). */
  dragScale: number
  /** Shift-drag value units per pixel; defaults to dragScale / 4. */
  fineDragScale?: number
  /** Pointer travel (px) before the gesture counts as a drag. Default 0 keeps GapControl's
   * semantics: any pointerdown starts a drag and even a no-travel release commits. */
  dragThreshold?: number
  /** Snap applied to dragged values; Alt bypasses it. */
  snap?: (v: number) => number
  /** Shift keyboard step; defaults to step * 10. */
  shiftStep?: number
  parse?: (raw: string) => number | null
  /** Draft-text formatter for typed entry; default String. */
  format?: (v: number) => string
  /** Commit rounding; default Math.round. */
  round?: (v: number) => number
  /** N1 double-click reset target; undefined disables the reset gesture. */
  defaultValue?: number
  /** N2 opt-in wheel nudge (native non-passive listener on the attached element). */
  wheel?: boolean
  /** Drag axis. Knobs and faders use 'y' (up increases), the numeric fields use 'x'. */
  axis?: 'x' | 'y'
  disabled?: boolean
}

interface GestureState {
  pointerId: number
  startClient: number
  axis: 'x' | 'y'
  startValue: number
  scale: number
  fineScale: number
  threshold: number
  moved: boolean
  openEditorOnRelease: boolean
}

/** Pointer travel along the control's own axis, in the direction that increases the value. */
function dragDelta(state: GestureState, event: PointerEvent): number {
  return state.axis === 'y' ? state.startClient - event.clientY : event.clientX - state.startClient
}

export function useDragScrubValue({
  value,
  min,
  max,
  step,
  onChange,
  dragScale,
  fineDragScale,
  dragThreshold = 0,
  snap,
  shiftStep,
  parse = parseGapText,
  format = String,
  round = Math.round,
  defaultValue,
  wheel = false,
  axis = 'x',
  disabled = false,
}: UseDragScrubValueOptions) {
  const [editing, setEditing] = useState(false)
  const [draftText, setDraftText] = useState(format(value))
  const [dragValue, setDragValue] = useState<number | null>(null)
  const dragStateRef = useRef<GestureState | null>(null)
  const rafRef = useRef<number | null>(null)
  const wheelTargetRef = useRef<HTMLElement | null>(null)

  const fineScale = fineDragScale ?? dragScale / 4
  const bigStep = shiftStep ?? step * 10

  // Fresh values for the identity-stable callbacks and the long-lived native listeners.
  const latestRef = useRef({ value, min, max, step, editing, disabled, onChange, snap, round, dragScale, fineScale, dragThreshold, defaultValue, format })
  latestRef.current = { value, min, max, step, editing, disabled, onChange, snap, round, dragScale, fineScale, dragThreshold, defaultValue, format }

  const commitValue = useCallback((next: number) => {
    const l = latestRef.current
    l.onChange(l.round(Math.max(l.min, Math.min(l.max, next))))
  }, [])

  const beginEdit = useCallback(() => {
    const l = latestRef.current
    if (l.disabled) return
    setDraftText(l.format(l.value))
    setEditing(true)
  }, [])

  const commitEdit = useCallback(() => {
    const parsed = parse(draftText)
    if (parsed !== null) commitValue(parsed)
    setEditing(false)
  }, [parse, draftText, commitValue])

  const cancelEdit = useCallback(() => {
    setEditing(false)
    setDraftText(format(value))
  }, [format, value])

  const nudge = useCallback(
    (delta: number) => {
      // A nudge while the value is being typed would commit a stale base and fight the
      // pending text; ignore it until the edit commits or cancels.
      if (editing || disabled) return
      commitValue(value + delta)
    },
    [editing, disabled, commitValue, value],
  )

  const handlePointerMove = useCallback((event: PointerEvent) => {
    const state = dragStateRef.current
    if (!state || state.pointerId !== event.pointerId) return
    const dx = dragDelta(state, event)
    if (!state.moved && Math.abs(dx) < state.threshold) return
    state.moved = true
    const l = latestRef.current
    const scale = event.shiftKey ? state.fineScale : state.scale
    let next = state.startValue + dx * scale
    if (l.snap && !event.altKey) next = l.snap(next)
    next = Math.max(l.min, Math.min(l.max, next))
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(() => setDragValue(l.round(next)))
  }, [])

  const endDrag = useCallback((event: PointerEvent) => {
    const state = dragStateRef.current
    if (!state || state.pointerId !== event.pointerId) return
    window.removeEventListener('pointermove', handlePointerMove)
    window.removeEventListener('pointerup', endDrag)
    window.removeEventListener('pointercancel', endDrag)
    dragStateRef.current = null
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current)
      // Compute the committed value directly from this event's own clientX -- see the
      // matching comment in StitchClipCard.tsx's endDrag for why reading the
      // rAF-throttled `dragValue` state here would silently commit a stale value on a
      // fast pointerup. threshold === 0 keeps GapControl's reference semantics: even a
      // no-travel release (and a pointercancel) commits the snap of the start value.
      const l = latestRef.current
      const dx = dragDelta(state, event)
      const scale = event.shiftKey ? state.fineScale : state.scale
      let next = state.startValue + dx * scale
      if (l.snap && !event.altKey) next = l.snap(next)
      commitValue(next)
    } else if (state.openEditorOnRelease && event.type === 'pointerup') {
      // Stepper semantics: a press-release without travel is a click-to-type.
      beginEdit()
    }
    setDragValue(null)
  }, [handlePointerMove, commitValue, beginEdit])

  const beginScrub = useCallback(
    (event: PointerEvent, captureElement: HTMLElement, options?: { openEditorOnRelease?: boolean }) => {
      const l = latestRef.current
      if (l.disabled || l.editing) return
      // Only the primary button scrubs: the secondary one belongs to the context menu, and a
      // right-press must neither capture the pointer nor commit a value on release.
      if (event.button !== 0) return
      // No preventDefault: it would suppress the synthesized mouse events (click,
      // dblclick) Chromium needs for N1's double-click reset and button clicks. Text
      // selection is prevented by the controls' select-none class instead.
      dragStateRef.current = {
        pointerId: event.pointerId,
        startClient: axis === 'y' ? event.clientY : event.clientX,
        axis,
        startValue: l.value,
        scale: l.dragScale,
        fineScale: l.fineScale,
        threshold: l.dragThreshold,
        moved: false,
        openEditorOnRelease: options?.openEditorOnRelease ?? false,
      }
      captureElement.setPointerCapture(event.pointerId)
      window.addEventListener('pointermove', handlePointerMove)
      window.addEventListener('pointerup', endDrag)
      window.addEventListener('pointercancel', endDrag)
    },
    // `axis` belongs here: the drag state records it at gesture start, and a stale closure
    // would capture the initial axis for the life of the control (a vertical drag then reads
    // as zero travel and silently commits the starting value).
    [handlePointerMove, endDrag, axis],
  )

  // The gesture listeners live on window and are normally removed by the end handlers, so
  // unmounting mid-drag would leak them and leave a pending rAF callback. Tear everything
  // down on unmount. The identity-stable callbacks above mean this effect never re-runs
  // mid-gesture, so it cannot strip an in-flight gesture's listeners.
  useEffect(() => {
    return () => {
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', endDrag)
      window.removeEventListener('pointercancel', endDrag)
      dragStateRef.current = null
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
    }
  }, [handlePointerMove, endDrag])

  const handleKeyDown = useCallback(
    (event: ReactKeyboardEvent) => {
      if (editing) {
        if (event.key === 'Enter') {
          event.preventDefault()
          commitEdit()
        } else if (event.key === 'Escape') {
          event.preventDefault()
          cancelEdit()
        }
        return
      }
      if (event.key === 'ArrowUp') {
        // The focused control is not an editable target, so the timeline's global shortcut
        // would also see this event; stop propagation so it never reaches the window handler.
        event.stopPropagation()
        event.preventDefault()
        nudge(event.shiftKey ? bigStep : step)
      } else if (event.key === 'ArrowDown') {
        event.stopPropagation()
        event.preventDefault()
        nudge(event.shiftKey ? -bigStep : -step)
      }
    },
    [editing, commitEdit, cancelEdit, nudge, bigStep, step],
  )

  const handleDoubleClick = useCallback(
    (event: ReactMouseEvent) => {
      const l = latestRef.current
      if (l.defaultValue === undefined || l.disabled || l.editing) return
      const target = event.target as HTMLElement
      // Buttons, the typed-entry input, and form controls keep their own click semantics.
      if (target.closest('button, input, textarea, select')) return
      commitValue(l.defaultValue)
    },
    [commitValue],
  )

  // N2 opt-in wheel nudge: native, non-passive, so the control can preventDefault page
  // scroll. One step per wheel event; Shift = step / 10 fine.
  useEffect(() => {
    if (!wheel) return
    const element = wheelTargetRef.current
    if (!element) return
    const onWheel = (event: WheelEvent) => {
      const l = latestRef.current
      if (l.disabled || l.editing) return
      event.preventDefault()
      const delta = (event.shiftKey ? l.step / 10 : l.step) * (event.deltaY < 0 ? 1 : -1)
      l.onChange(l.round(Math.max(l.min, Math.min(l.max, l.value + delta))))
    }
    element.addEventListener('wheel', onWheel, { passive: false })
    return () => element.removeEventListener('wheel', onWheel)
  }, [wheel])

  const displayValue = dragValue ?? value

  return {
    editing,
    draftText,
    setDraftText,
    beginEdit,
    commitEdit,
    cancelEdit,
    nudge,
    displayValue,
    beginScrub,
    handleKeyDown,
    handleDoubleClick,
    wheelTargetRef,
  }
}
