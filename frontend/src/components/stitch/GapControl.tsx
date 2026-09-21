// Independent, always-visible control for the gap between two adjacent clips -- rendered
// between clips in the timeline (not nested inside either clip's card), so it reads as
// belonging to "the space between" rather than to one clip. Every seam renders here,
// including a 0.00s one: a hidden-until-clicked "+" affordance made the zero state
// indistinguishable from "no control exists here at all."
//
// Supports three input paths, each committing the same clamped [0, 5000]ms value:
//   - Drag anywhere on the control body (pointer events + setPointerCapture; snaps to the
//     locked ladder [0, 80, 150, 250, 400, 600, 900]ms unless Alt is held).
//   - Click-to-type: accepts "200", "0.2s", and "200ms"; Enter commits, Escape reverts,
//     blur commits.
//   - Keyboard, once the control or its input has focus: Up/Down = 10ms, Shift+Up/Down =
//     100ms.
import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type KeyboardEvent as ReactKeyboardEvent } from 'react'
import { cn } from '@/lib/utils'

const SNAP_MS = [0, 80, 150, 250, 400, 600, 900]
const MAX_GAP_MS = 5000
const ZERO_BOX_PX = 48
const MIN_NONZERO_BOX_PX = 84

function parseGapText(raw: string): number | null {
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

function snapToLadder(ms: number): number {
  let closest = SNAP_MS[0]
  let bestDistance = Infinity
  for (const candidate of SNAP_MS) {
    const distance = Math.abs(candidate - ms)
    if (distance < bestDistance) {
      bestDistance = distance
      closest = candidate
    }
  }
  return closest
}

export function GapControl({
  gapIndex,
  paddingMs,
  onSetPadding,
  pixelsPerSecond,
}: {
  gapIndex: number
  paddingMs: number
  onSetPadding: (gapIndex: number, ms: number) => void
  pixelsPerSecond: number
}) {
  const [editing, setEditing] = useState(false)
  const [draftText, setDraftText] = useState(String(Math.round(paddingMs)))
  const [dragValue, setDragValue] = useState<number | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)
  const dragStateRef = useRef<{ pointerId: number; startClientX: number; startValue: number; msPerPx: number } | null>(null)
  const rafRef = useRef<number | null>(null)

  useEffect(() => {
    if (editing) inputRef.current?.focus()
  }, [editing])

  const commitValue = useCallback((next: number) => {
    onSetPadding(gapIndex, Math.max(0, Math.min(MAX_GAP_MS, Math.round(next))))
  }, [gapIndex, onSetPadding])

  const beginEdit = () => {
    setDraftText(String(Math.round(paddingMs)))
    setEditing(true)
  }

  const commitEdit = () => {
    const parsed = parseGapText(draftText)
    if (parsed !== null) commitValue(parsed)
    setEditing(false)
  }

  const cancelEdit = () => {
    setEditing(false)
    setDraftText(String(Math.round(paddingMs)))
  }

  const handlePointerMove = useCallback((event: PointerEvent) => {
    const state = dragStateRef.current
    if (!state) return
    const deltaMs = (event.clientX - state.startClientX) * state.msPerPx
    let next = Math.max(0, Math.min(MAX_GAP_MS, state.startValue + deltaMs))
    if (!event.altKey) next = snapToLadder(next)
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(() => setDragValue(Math.round(next)))
  }, [])

  const endDrag = useCallback((event: PointerEvent) => {
    const state = dragStateRef.current
    if (state?.pointerId !== event.pointerId) return
    window.removeEventListener('pointermove', handlePointerMove)
    window.removeEventListener('pointerup', endDrag)
    window.removeEventListener('pointercancel', endDrag)
    dragStateRef.current = null
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    // Compute the committed value directly from this event's own clientX -- see the matching
    // comment in StitchClipCard.tsx's endDrag for why reading the rAF-throttled `dragValue`
    // state here would silently commit a stale value on a fast pointerup.
    const deltaMs = (event.clientX - state.startClientX) * state.msPerPx
    let next = Math.max(0, Math.min(MAX_GAP_MS, state.startValue + deltaMs))
    if (!event.altKey) next = snapToLadder(next)
    commitValue(next)
    setDragValue(null)
  }, [handlePointerMove, commitValue])

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
      dragStateRef.current = null
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
    }
  }, [handlePointerMove, endDrag])

  const startDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (editing) return
    event.preventDefault()
    dragStateRef.current = {
      pointerId: event.pointerId,
      startClientX: event.clientX,
      startValue: paddingMs,
      msPerPx: 1000 / Math.max(1, pixelsPerSecond),
    }
    event.currentTarget.setPointerCapture(event.pointerId)
    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', endDrag)
    window.addEventListener('pointercancel', endDrag)
  }

  const nudge = (deltaMs: number) => {
    // A nudge while the value is being typed would commit a stale base and fight the
    // pending text; ignore it until the edit commits or cancels.
    if (editing) return
    commitValue(paddingMs + deltaMs)
  }

  const handleKeyDown = (event: ReactKeyboardEvent) => {
    if (event.key === 'ArrowUp' && !editing) {
      // The focused gap button is not an editable target, so the timeline's global
      // shortcut would also see this event and silently trim the selected clip.
      // Stop propagation so it never reaches the window handler.
      event.stopPropagation()
      event.preventDefault()
      nudge(event.shiftKey ? 100 : 10)
    } else if (event.key === 'ArrowDown' && !editing) {
      event.stopPropagation()
      event.preventDefault()
      nudge(event.shiftKey ? -100 : -10)
    } else if (event.key === 'Enter' && editing) {
      event.preventDefault()
      commitEdit()
    } else if (event.key === 'Escape' && editing) {
      event.preventDefault()
      cancelEdit()
    }
  }

  const displayMs = dragValue ?? paddingMs
  const isZero = Math.round(displayMs) <= 0
  const naturalWidthPx = (displayMs / 1000) * pixelsPerSecond
  const widthPx = isZero ? ZERO_BOX_PX : Math.max(MIN_NONZERO_BOX_PX, naturalWidthPx)
  const isClamped = !isZero && naturalWidthPx < MIN_NONZERO_BOX_PX
  const ariaLabel = `Gap between clip ${gapIndex + 1} and clip ${gapIndex + 2}`

  return (
    <div
      data-testid="stitch-gap-control"
      data-gap-index={gapIndex}
      data-gap-ms={Math.round(paddingMs)}
      data-gap-zero={isZero ? 'true' : 'false'}
      data-gap-clamped={isClamped ? 'true' : 'false'}
      title={`${Math.round(paddingMs)}ms gap`}
      onPointerDown={startDrag}
      className={cn(
        'group relative mt-3 flex h-24 shrink-0 flex-col items-center justify-center gap-1 rounded px-1 select-none touch-none',
        isZero
          ? 'border border-dashed border-border/40 hover:border-cyan-500/50'
          : 'border border-cyan-500/40 bg-cyan-500/5',
        isClamped &&
          'bg-[repeating-linear-gradient(45deg,rgba(6,182,212,0.18),rgba(6,182,212,0.18)_4px,transparent_4px,transparent_8px)]',
      )}
      style={{ width: editing ? Math.max(widthPx, 72) : widthPx, cursor: 'ew-resize' }}
    >
      {isZero && <div data-testid="stitch-gap-zero-marker" className="pointer-events-none absolute h-10 w-px bg-border/70" />}
      <span className="text-[9px] uppercase text-muted-foreground/70">gap</span>
      {editing ? (
        <input
          ref={inputRef}
          type="text"
          inputMode="decimal"
          value={draftText}
          aria-label={ariaLabel}
          onChange={(event) => setDraftText(event.target.value)}
          onBlur={commitEdit}
          onKeyDown={handleKeyDown}
          onPointerDown={(event) => event.stopPropagation()}
          className="w-14 rounded border border-cyan-500/40 bg-muted/40 px-1 py-0.5 text-center text-[10px] font-mono text-foreground outline-none"
        />
      ) : (
        <button
          type="button"
          aria-label={ariaLabel}
          onClick={beginEdit}
          onPointerDown={(event) => event.stopPropagation()}
          onKeyDown={handleKeyDown}
          className="inline-flex min-w-[24px] justify-center rounded px-1 text-xs font-mono tabular-nums text-foreground hover:bg-muted/70"
        >
          {Math.round(displayMs)}
        </button>
      )}
      <div className="flex items-center gap-0.5">
        <button
          type="button"
          className="inline-flex size-4 items-center justify-center rounded bg-muted/70 text-[10px] text-muted-foreground hover:bg-muted"
          aria-label="Decrease gap"
          onClick={() => nudge(-10)}
          onPointerDown={(event) => event.stopPropagation()}
        >
          −
        </button>
        <button
          type="button"
          className="inline-flex size-4 items-center justify-center rounded bg-muted/70 text-[10px] text-muted-foreground hover:bg-muted"
          aria-label="Increase gap"
          onClick={() => nudge(10)}
          onPointerDown={(event) => event.stopPropagation()}
        >
          +
        </button>
      </div>
      {isClamped && (
        <span className="absolute -bottom-4 whitespace-nowrap text-[9px] font-mono text-cyan-400/80">
          {Math.round(displayMs)}ms
        </span>
      )}
    </div>
  )
}
