// Independent, always-visible control for the gap between two adjacent clips -- rendered
// between clips in the timeline (not nested inside either clip's card), so it reads as
// belonging to "the space between" rather than to one clip. Every seam renders here,
// including a 0.00s one: a hidden-until-clicked "+" affordance made the zero state
// indistinguishable from "no control exists here at all."
//
// Supports three input paths, each committing the same clamped [0, 5000]ms value:
//   - Drag anywhere on the control body (pointer events + setPointerCapture; snaps to the
//     locked ladder [0, 80, 150, 250, 400, 600, 900]ms unless Alt is held; Shift = fine).
//   - Click-to-type: accepts "200", "0.2s", and "200ms"; Enter commits, Escape reverts,
//     blur commits.
//   - Keyboard, once the control or its input has focus: Up/Down = 10ms, Shift+Up/Down =
//     100ms.
// The gesture lives in hooks/useDragScrubValue.ts (extracted from this component); this
// file only supplies the gap-specific snap ladder, clamps, and rendering.
import { useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import { formatMsValue } from '@/lib/timeAxis'
import { NUMERIC_CONTROL_FOCUS_CLASS, NUMERIC_CONTROL_UNIT_CLASS, useDragScrubValue } from '@/hooks/useDragScrubValue'
import * as ContextMenu from '../ui/context-menu'

const SNAP_MS = [0, 80, 150, 250, 400, 600, 900]
const MAX_GAP_MS = 5000
const ZERO_BOX_PX = 48
const MIN_NONZERO_BOX_PX = 84

function snapToLadder(ms: number): number {
  let closest = SNAP_MS[0]
  let bestDistance = Infinity
  for (const candidate of SNAP_MS) {
    const distance = Math.abs(candidate - ms)
    if (distance < bestDistance) {
      closest = candidate
      bestDistance = distance
    }
  }
  return closest
}

export function GapControl({
  gapIndex,
  paddingMs,
  onSetPadding,
  pixelsPerSecond,
  defaultMs,
}: {
  gapIndex: number
  paddingMs: number
  onSetPadding: (gapIndex: number, ms: number) => void
  pixelsPerSecond: number
  /** Double-click reset target (N1): the punctuation-suggested gap for this seam. */
  defaultMs?: number
}) {
  const inputRef = useRef<HTMLInputElement | null>(null)
  const {
    editing,
    draftText,
    setDraftText,
    beginEdit,
    commitEdit,
    nudge,
    displayValue: displayMs,
    beginScrub,
    handleKeyDown,
    handleDoubleClick,
  } = useDragScrubValue({
    value: paddingMs,
    min: 0,
    max: MAX_GAP_MS,
    step: 10,
    shiftStep: 100,
    onChange: (v) => onSetPadding(gapIndex, v),
    dragScale: 1000 / Math.max(1, pixelsPerSecond),
    snap: snapToLadder,
    format: (v) => String(Math.round(v)),
    defaultValue: defaultMs,
  })

  useEffect(() => {
    if (editing) inputRef.current?.focus()
  }, [editing])

  const isZero = Math.round(displayMs) <= 0
  const naturalWidthPx = (displayMs / 1000) * pixelsPerSecond
  const widthPx = isZero ? ZERO_BOX_PX : Math.max(MIN_NONZERO_BOX_PX, naturalWidthPx)
  const isClamped = !isZero && naturalWidthPx < MIN_NONZERO_BOX_PX
  const ariaLabel = `Gap between clip ${gapIndex + 1} and clip ${gapIndex + 2}`
  const unit = formatMsValue(displayMs)
  const setGap = (ms: number) => onSetPadding(gapIndex, Math.max(0, Math.min(MAX_GAP_MS, Math.round(ms))))

  return (
    <ContextMenu.Root>
      <ContextMenu.Trigger asChild>
    <div
      data-testid="stitch-gap-control"
      data-numeric-control="gap"
      data-gap-index={gapIndex}
      data-gap-ms={Math.round(paddingMs)}
      data-gap-zero={isZero ? 'true' : 'false'}
      data-gap-clamped={isClamped ? 'true' : 'false'}
      title={`${Math.round(paddingMs)}ms gap`}
      tabIndex={0}
      role="group"
      aria-label={ariaLabel}
      onKeyDown={handleKeyDown}
      onPointerDown={(e) => beginScrub(e.nativeEvent, e.currentTarget)}
      onDoubleClick={handleDoubleClick}
      className={cn(
        'group relative mt-3 flex h-24 shrink-0 flex-col items-center justify-center gap-1 rounded px-1 select-none touch-none',
        NUMERIC_CONTROL_FOCUS_CLASS,
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
          onPointerDown={(event) => event.stopPropagation()}
          className="w-14 rounded border border-cyan-500/40 bg-muted/40 px-1 py-0.5 text-center text-[10px] font-mono text-foreground outline-none"
        />
      ) : (
        <button
          type="button"
          tabIndex={-1}
          data-testid="stitch-gap-value"
          aria-label={ariaLabel}
          onClick={beginEdit}
          onPointerDown={(event) => event.stopPropagation()}
          className="inline-flex min-w-[24px] justify-center rounded px-1 text-xs font-mono tabular-nums text-foreground hover:bg-muted/70"
        >
          {unit.text}
        </button>
      )}
      <span data-testid="stitch-gap-unit" className={NUMERIC_CONTROL_UNIT_CLASS}>
        {unit.unit}
      </span>
      <div className="flex items-center gap-0.5">
        <button
          type="button"
          tabIndex={-1}
          className="inline-flex size-4 items-center justify-center rounded bg-muted/70 text-[10px] text-muted-foreground hover:bg-muted"
          aria-label="Decrease gap"
          onClick={() => nudge(-10)}
          onPointerDown={(event) => event.stopPropagation()}
        >
          −
        </button>
        <button
          type="button"
          tabIndex={-1}
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
          {unit.text}
          {unit.unit}
        </span>
      )}
    </div>
      </ContextMenu.Trigger>
      <ContextMenu.Content data-testid="stitch-context-menu" data-menu-scope="seam">
        <ContextMenu.Label>{ariaLabel}</ContextMenu.Label>
        <ContextMenu.Item
          data-testid="stitch-menu-gap-suggested"
          disabled={defaultMs == null || Math.round(defaultMs) === Math.round(paddingMs)}
          onSelect={() => setGap(defaultMs ?? 0)}
        >
          Use suggested gap
          {defaultMs != null && <ContextMenu.Hint>{Math.round(defaultMs)}ms</ContextMenu.Hint>}
        </ContextMenu.Item>
        <ContextMenu.Item data-testid="stitch-menu-gap-zero" disabled={isZero} onSelect={() => setGap(0)}>
          Remove gap
          <ContextMenu.Hint>0ms</ContextMenu.Hint>
        </ContextMenu.Item>
        <ContextMenu.Separator />
        <ContextMenu.Item data-testid="stitch-menu-gap-tighter" disabled={isZero} onSelect={() => setGap(paddingMs - 100)}>
          Tighten by 100ms
        </ContextMenu.Item>
        <ContextMenu.Item data-testid="stitch-menu-gap-wider" onSelect={() => setGap(paddingMs + 100)}>
          Widen by 100ms
        </ContextMenu.Item>
      </ContextMenu.Content>
    </ContextMenu.Root>
  )
}
