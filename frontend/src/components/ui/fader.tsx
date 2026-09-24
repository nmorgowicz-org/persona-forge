// Fader (B-P5, CP0 decision D2).
//
// The linear sibling of the knob, for parameters whose range is long enough that an arc would
// make the useful part of it feel cramped -- the compressor threshold spans 48 dB, where a knob
// spends most of its sweep in territory nobody uses. Same hook, same contract: horizontal drag,
// Shift for fine, double-click to reset, wheel to nudge, click to type, arrow keys, slider role,
// and a value bubble while you drag.
import { useCallback, useRef, useState } from 'react'
import { NUMERIC_CONTROL_FOCUS_CLASS, parseNumericText, quantiseToStep, useDragScrubValue } from '@/hooks/useDragScrubValue'
import { cn } from '@/lib/utils'

export interface FaderProps {
  value: number
  min: number
  max: number
  step: number
  onChange: (value: number) => void
  label: string
  format: (value: number) => string
  defaultValue?: number
  disabled?: boolean
  /** Track length in px. */
  width?: number
  testId?: string
}

export function Fader({
  value,
  min,
  max,
  step,
  onChange,
  label,
  format,
  defaultValue,
  disabled = false,
  width = 160,
  testId,
}: FaderProps) {
  const [hovered, setHovered] = useState(false)
  const [dragging, setDragging] = useState(false)
  const trackRef = useRef<HTMLDivElement | null>(null)

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
    dragScale: (max - min) / width,
    dragThreshold: 2,
    shiftStep: step * 5,
    // Same reason as the knob: on the step grid, not Math.round.
    round: quantiseToStep(min, max, step),
    parse: parseNumericText,
    defaultValue,
    wheel: true,
    axis: 'x',
    disabled,
  })

  const fraction = max > min ? Math.min(1, Math.max(0, (displayValue - min) / (max - min))) : 0

  const attachWheelTarget = useCallback(
    (node: HTMLDivElement | null) => {
      trackRef.current = node
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
        'relative flex flex-col gap-1 select-none',
        NUMERIC_CONTROL_FOCUS_CLASS,
        disabled ? 'opacity-50' : 'cursor-ew-resize',
      )}
      style={{ width }}
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
        const big = event.shiftKey
        if (event.key === 'ArrowRight' || event.key === 'ArrowUp') {
          event.preventDefault()
          nudge(big ? step * 5 : step)
        } else if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') {
          event.preventDefault()
          nudge(big ? -step * 5 : -step)
        }
      }}
    >
      <div className="flex items-center justify-between">
        <span className="micro-label">{label}</span>
        {editing ? (
          <input
            type="text"
            inputMode="decimal"
            value={draftText}
            aria-label={label}
            onChange={(event) => setDraftText(event.target.value)}
            onBlur={commitEdit}
            onKeyDown={handleKeyDown}
            className="w-16 rounded border border-primary/40 bg-muted/40 px-1 text-right text-[11px] font-mono tabular-nums text-foreground outline-none"
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
      </div>

      <div className="well relative h-1.5 w-full overflow-hidden">
        <div className="absolute inset-y-0 left-0 bg-primary" style={{ width: `${fraction * 100}%` }} />
      </div>

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
