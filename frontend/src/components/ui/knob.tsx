// Knob (B-P5, CP0 decision D2).
//
// The same control as Plan A's drag-scrubbable numbers, in the form a plugin uses for a
// parameter you tune by feel: an arc you drag vertically, with a value bubble you can read
// while you are dragging. Everything the numeric fields learned in A-1 still applies --
// Shift for fine, double-click to reset, wheel to nudge, click to type, arrow keys, and a
// slider role -- because a knob that behaved differently from the fields beside it would be
// two controls pretending to be one.
import { useCallback, useRef, useState } from 'react'
import { NUMERIC_CONTROL_FOCUS_CLASS, parseNumericText, quantiseToStep, useDragScrubValue } from '@/hooks/useDragScrubValue'
import { cn } from '@/lib/utils'

/** Sweep of the arc, centred on straight up: -135deg to +135deg. */
const SWEEP_DEG = 270
const START_DEG = -135

function polar(cx: number, cy: number, radius: number, degrees: number): [number, number] {
  const radians = ((degrees - 90) * Math.PI) / 180
  return [cx + radius * Math.cos(radians), cy + radius * Math.sin(radians)]
}

function arcPath(cx: number, cy: number, radius: number, fromDeg: number, toDeg: number): string {
  const [x1, y1] = polar(cx, cy, radius, fromDeg)
  const [x2, y2] = polar(cx, cy, radius, toDeg)
  const largeArc = Math.abs(toDeg - fromDeg) > 180 ? 1 : 0
  return `M ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2}`
}

export interface KnobProps {
  value: number
  min: number
  max: number
  step: number
  onChange: (value: number) => void
  label: string
  format: (value: number) => string
  /** Double-click reset target. Undefined disables the reset gesture. */
  defaultValue?: number
  disabled?: boolean
  /** Diameter of the arc in px. */
  size?: number
  /** Value units per dragged pixel. Defaults to the whole range over 140 px. */
  dragScale?: number
  /** Override the settle rounding. Defaults to the nearest multiple of `step`. */
  round?: (value: number) => number
  testId?: string
}

export function Knob({
  value,
  min,
  max,
  step,
  onChange,
  label,
  format,
  defaultValue,
  disabled = false,
  size = 44,
  dragScale,
  round,
  testId,
}: KnobProps) {
  const [hovered, setHovered] = useState(false)
  const [dragging, setDragging] = useState(false)
  const rootRef = useRef<HTMLDivElement | null>(null)

  const {
    editing,
    draftText,
    setDraftText,
    beginEdit,
    commitEdit,
    displayValue,
    beginScrub,
    handleKeyDown,
    handleDoubleClick,
    nudge,
    wheelTargetRef,
  } = useDragScrubValue({
    value,
    min,
    max,
    step,
    onChange,
    // 140 px of vertical travel spans the whole range by default: enough resolution to place a
    // value without a long drag, which is what a knob is for.
    dragScale: dragScale ?? (max - min) / 140,
    dragThreshold: 2,
    shiftStep: step * 5,
    parse: parseNumericText,
    // On the step grid, not Math.round: a knob with a fractional step would otherwise snap
    // every value to a whole number and appear not to move.
    round: round ?? quantiseToStep(min, max, step),
    defaultValue,
    wheel: true,
    axis: 'y',
    disabled,
  })

  const fraction = max > min ? Math.min(1, Math.max(0, (displayValue - min) / (max - min))) : 0
  const valueDeg = START_DEG + fraction * SWEEP_DEG
  const radius = size / 2 - 3
  const centre = size / 2
  const [pointerX, pointerY] = polar(centre, centre, radius - 1, valueDeg)
  const [innerX, innerY] = polar(centre, centre, radius * 0.45, valueDeg)

  const attachWheelTarget = useCallback(
    (node: HTMLDivElement | null) => {
      rootRef.current = node
      wheelTargetRef.current = node
    },
    [wheelTargetRef],
  )

  const showBubble = (dragging || hovered) && !editing

  return (
    <div
      ref={attachWheelTarget}
      data-testid={testId}
      role="slider"
      aria-label={label}
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={displayValue}
      aria-valuetext={format(displayValue)}
      aria-disabled={disabled || undefined}
      tabIndex={disabled ? -1 : 0}
      className={cn(
        'relative flex flex-col items-center gap-1 select-none',
        NUMERIC_CONTROL_FOCUS_CLASS,
        disabled ? 'opacity-50' : 'cursor-ns-resize',
      )}
      onPointerDown={(event) => {
        if ((event.target as HTMLElement).closest('input, button')) return
        setDragging(true)
        beginScrub(event.nativeEvent, event.currentTarget, { openEditorOnRelease: false })
      }}
      onPointerUp={() => setDragging(false)}
      onPointerCancel={() => setDragging(false)}
      onPointerEnter={() => setHovered(true)}
      onPointerLeave={() => setHovered(false)}
      onDoubleClick={handleDoubleClick}
      onKeyDown={(event) => {
        // A slider is a keyboard control: arrows step, Shift is the coarse step.
        const big = event.shiftKey
        if (event.key === 'ArrowUp' || event.key === 'ArrowRight') {
          event.preventDefault()
          nudge(big ? step * 5 : step)
        } else if (event.key === 'ArrowDown' || event.key === 'ArrowLeft') {
          event.preventDefault()
          nudge(big ? -step * 5 : -step)
        }
      }}
    >
      <span className="micro-label">{label}</span>

      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden className="block">
        <path d={arcPath(centre, centre, radius, START_DEG, START_DEG + SWEEP_DEG)} fill="none" stroke="var(--border)" strokeWidth={3} strokeLinecap="round" />
        {fraction > 0 && (
          <path d={arcPath(centre, centre, radius, START_DEG, valueDeg)} fill="none" stroke="var(--primary)" strokeWidth={3} strokeLinecap="round" />
        )}
        <line x1={innerX} y1={innerY} x2={pointerX} y2={pointerY} stroke="var(--foreground)" strokeWidth={2} strokeLinecap="round" />
      </svg>

      {editing ? (
        <input
          type="text"
          inputMode="decimal"
          value={draftText}
          aria-label={label}
          onChange={(event) => setDraftText(event.target.value)}
          onBlur={commitEdit}
          onKeyDown={handleKeyDown}
          className="w-16 rounded border border-primary/40 bg-muted/40 px-1 text-center text-[11px] font-mono tabular-nums text-foreground outline-none"
          autoFocus
        />
      ) : (
        <button
          type="button"
          onClick={beginEdit}
          disabled={disabled}
          className="readout rounded px-1 text-[11px] hover:bg-muted"
          aria-label={`${label} value`}
        >
          {format(displayValue)}
        </button>
      )}

      {showBubble && (
        <span
          data-testid="knob-bubble"
          className="readout pointer-events-none absolute -top-6 rounded border border-border bg-popover px-1.5 py-0.5 text-[10px] shadow-sm"
        >
          {format(displayValue)}
        </span>
      )}
    </div>
  )
}
