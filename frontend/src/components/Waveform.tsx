import { useRef, useState } from 'react'
import { motion } from 'motion/react'
import { cn } from '@/lib/utils'
import { createTimeTicks } from '@/lib/timeAxis'
import { waveformBarColor, WAVEFORM_PLAYHEAD_COLOR } from '@/lib/waveform'
import { useElementWidth } from '@/hooks/useElementWidth'

// A highlighted region of the waveform, expressed as 0..1 fractions of the clip.
export interface WaveformRegion {
  start: number
  end: number
}

interface WaveformProps {
  peaks: number[]
  progress?: number // 0..1, how much of the waveform is "played"
  isActive?: boolean // pulses idle bars gently while audio is loading/generating
  duration?: number | null // total audio duration in seconds, drives time axis
  className?: string
  onClick?: (progress: number) => void
  // Opt-in drag-to-select scrubbing: a click still seeks (onClick), but a click-and-drag
  // reports a region (0..1 fractions) the caller can loop. `selection` is the controlled
  // highlight; while dragging, the live band is shown regardless.
  selection?: WaveformRegion | null
  onSelectRegion?: (region: WaveformRegion | null) => void
  /** Test hook for the waveform surface; also names the selection band `${testId}-selection`. */
  testId?: string
}

export function Waveform({ peaks, progress = 0, isActive = false, duration = null, className, onClick, selection = null, onSelectRegion, testId }: WaveformProps) {
  const playheadPct = Math.min(100, Math.max(0, progress * 100))
  const hasTimeAxis = duration != null && duration > 0 && isFinite(duration)

  const fracAt = (clientX: number, el: Element) => {
    const rect = el.getBoundingClientRect()
    return Math.min(1, Math.max(0, (clientX - rect.left) / rect.width))
  }

  const handleWaveformClick = (e: React.MouseEvent) => {
    if (!onClick) return
    onClick(fracAt(e.clientX, e.currentTarget))
  }

  // Drag-to-select: track the gesture in a ref (no re-render churn) and mirror the live band
  // into `dragBand` state so it paints while dragging. A gesture that barely moves is a click.
  //
  // The gesture is owned by the waveform itself (pointer capture), not by whatever happens to
  // be under the pointer: a drag that wanders off the control -- up to the transport, out of
  // the window -- keeps tracking and still commits on release, and a pointercancel (touch
  // scroll takeover, browser gesture) ends it without selecting anything.
  const dragRef = useRef<{ pointerId: number; start: number; end: number; moved: boolean } | null>(null)
  const [dragBand, setDragBand] = useState<WaveformRegion | null>(null)

  const onDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return
    const start = fracAt(e.clientX, e.currentTarget)
    dragRef.current = { pointerId: e.pointerId, start, end: start, moved: false }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const onMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const d = dragRef.current
    if (!d || d.pointerId !== e.pointerId) return
    d.end = fracAt(e.clientX, e.currentTarget)
    if (Math.abs(d.end - d.start) > 0.01) d.moved = true
    setDragBand({ start: Math.min(d.start, d.end), end: Math.max(d.start, d.end) })
  }
  const finishDrag = (e: React.PointerEvent<HTMLDivElement>) => {
    const d = dragRef.current
    if (!d || d.pointerId !== e.pointerId) return
    dragRef.current = null
    setDragBand(null)
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId)
    if (e.type === 'pointercancel') return
    if (!d.moved) {
      onSelectRegion?.(null)
      onClick?.(d.start)
      return
    }
    onSelectRegion?.({ start: Math.min(d.start, d.end), end: Math.max(d.start, d.end) })
  }

  const interactive = onSelectRegion != null
  const band = dragBand ?? selection


  const [containerRef, widthPx] = useElementWidth<HTMLDivElement>()

  // Compute time ticks via the shared time-axis module, using the container's real measured
  // width so density adapts to how much room the ruler actually has.
  const ticks =
    hasTimeAxis && widthPx > 0
      ? createTimeTicks({ durationSeconds: duration as number, pixelsPerSecond: widthPx / (duration as number), widthPx }).map((t) => ({
          pos: (t.x / widthPx) * 100,
          text: t.label,
        }))
      : null

  return (
    <div
      ref={containerRef}
      data-testid={testId}
      className={cn(
        'relative overflow-hidden rounded-md bg-gradient-to-b from-black/30 to-transparent px-0.5 select-none',
        interactive ? 'cursor-ew-resize' : onClick ? 'cursor-pointer' : '',
        hasTimeAxis ? 'h-20' : 'h-16',
        className,
      )}
      onClick={interactive ? undefined : handleWaveformClick}
      onPointerDown={interactive ? onDown : undefined}
      onPointerMove={interactive ? onMove : undefined}
      onPointerUp={interactive ? finishDrag : undefined}
      onPointerCancel={interactive ? finishDrag : undefined}
      style={{ touchAction: interactive ? 'none' : undefined }}
    >
      {/* center track line, like a DAW lane */}
      <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-border/60" />

      {/* drag/loop selection band */}
      {band && band.end > band.start && (
        <div
          data-testid={testId ? `${testId}-selection` : undefined}
          className="pointer-events-none absolute inset-y-0 z-10 border-x border-warning/60 bg-warning/15"
          style={{ left: `${band.start * 100}%`, width: `${(band.end - band.start) * 100}%` }}
        />
      )}

      {/* time grid lines */}
      {ticks != null &&
        ticks.map((t, i) => (
          <div
            key={i}
            className="absolute inset-y-0 w-px bg-white/[0.06]"
            style={{ left: `${t.pos}%` }}
          />
        ))}

      <div className="relative -m-px flex h-full items-center">
        {peaks.map((peak, i) => {
          const played = (i / peaks.length) * 100 <= playheadPct
          const height = Math.max(0.06, peak)
          const color = waveformBarColor(height, played)

          return (
            <motion.div
              key={i}
              className="h-full min-w-[1px] flex-1 rounded-full"
              style={{
                transformOrigin: 'center',
                background: color,
                filter: played && height > 0.35 ? `drop-shadow(0 0 3px ${color})` : undefined,
              }}
              initial={{ scaleY: 0 }}
              animate={{
                scaleY: isActive ? [height * 0.55, height, height * 0.55] : height,
              }}
              transition={
                isActive
                  ? { duration: 0.85 + (i % 5) * 0.09, repeat: Infinity, ease: 'easeInOut' }
                  : { type: 'spring', stiffness: 320, damping: 24, delay: i * 0.004 }
              }
            />
          )
        })}
      </div>

      {progress > 0 && (
        <motion.div
          className="pointer-events-none absolute top-0 h-full w-px"
          style={{ background: WAVEFORM_PLAYHEAD_COLOR, boxShadow: `0 0 8px 1px ${WAVEFORM_PLAYHEAD_COLOR}` }}
          animate={{ left: `${playheadPct}%` }}
          transition={{ type: 'tween', ease: 'linear', duration: 0.1 }}
        >
          <span
            className="absolute -top-0.5 -left-[3px] size-[7px] rounded-full"
            style={{ background: WAVEFORM_PLAYHEAD_COLOR, boxShadow: `0 0 6px 1px ${WAVEFORM_PLAYHEAD_COLOR}` }}
          />
        </motion.div>
      )}

      {/* bottom time axis */}
      {hasTimeAxis && ticks != null && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end">
          {ticks.map((t, i) => (
            <span
              key={i}
              className={cn(
                'absolute -bottom-0 text-[9px] font-mono text-muted-foreground/50',
                t.pos >= 99.5 ? '-translate-x-full' : '-translate-x-1/2',
              )}
              style={{ left: `${t.pos}%` }}
            >
              {t.text}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
