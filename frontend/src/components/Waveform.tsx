import { useRef, useState, type RefObject } from 'react'
import { cn } from '@/lib/utils'
import { createTimeTicks } from '@/lib/timeAxis'
import type { AudioEnvelope } from '@/lib/waveform'
import { WaveformCanvas } from '@/components/waveform/WaveformCanvas'
import { useElementWidth } from '@/hooks/useElementWidth'
import { HOVER_TIME_GUIDE_LABEL_CLASS, HOVER_TIME_GUIDE_LINE_CLASS, useHoverTimeGuide } from '@/hooks/useHoverTimeGuide'

// A highlighted region of the waveform, expressed as 0..1 fractions of the clip.
export interface WaveformRegion {
  start: number
  end: number
}

interface WaveformProps {
  /** True-scale envelope (absolute units). Null while the audio is still decoding, which
   * renders the designed skeleton rather than invented signal. */
  envelope: AudioEnvelope | null
  /** The audio could not be decoded -- shown as a fallback, not as endless loading. */
  failed?: boolean
  /** Element whose `currentTime` drives the playhead at display rate. */
  mediaRef?: RefObject<HTMLMediaElement | null> | null
  playing?: boolean
  progress?: number // 0..1, static playhead for surfaces with no element of their own
  duration?: number | null // total audio duration in seconds, drives time axis
  className?: string
  onClick?: (progress: number) => void
  // Opt-in drag-to-select scrubbing: a click still seeks (onClick), but a click-and-drag
  // reports a region (0..1 fractions) the caller can loop. `selection` is the controlled
  // highlight; while dragging, the live band is shown regardless.
  selection?: WaveformRegion | null
  onSelectRegion?: (region: WaveformRegion | null) => void
  /** Modifier-held (Alt) drag: reports the fraction under the pointer continuously instead of
   * selecting a slice. The caller decides what scrubbing means for its own audio. */
  onScrub?: (fraction: number) => void
  /** Test hook for the waveform surface; also names the selection band `${testId}-selection`
   * and the hover time readout `${testId}-time`. */
  testId?: string
}

export function Waveform({
  envelope,
  failed = false,
  mediaRef = null,
  playing = false,
  progress = 0,
  duration = null,
  className,
  onClick,
  selection = null,
  onSelectRegion,
  onScrub,
  testId,
}: WaveformProps) {
  const hasTimeAxis = duration != null && duration > 0 && isFinite(duration)
  const [containerRef, widthPx] = useElementWidth<HTMLDivElement>()
  const pixelsPerSecond = hasTimeAxis && widthPx > 0 ? widthPx / (duration as number) : 0
  const guide = useHoverTimeGuide()

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
  //
  // Modifier-held scrub: Alt-drag moves the playhead continuously (the caller decides what
  // that means -- the deck seeks its audio) instead of selecting a slice, so the same surface
  // can be scrubbed without a second control.
  const dragRef = useRef<{ pointerId: number; mode: 'select' | 'scrub'; start: number; end: number; moved: boolean } | null>(null)
  const [dragBand, setDragBand] = useState<WaveformRegion | null>(null)

  const onDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return
    const start = fracAt(e.clientX, e.currentTarget)
    dragRef.current = { pointerId: e.pointerId, mode: e.altKey && onScrub ? 'scrub' : 'select', start, end: start, moved: false }
    e.currentTarget.setPointerCapture(e.pointerId)
    if (e.altKey && onScrub) onScrub(start)
  }
  const onMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const frac = fracAt(e.clientX, e.currentTarget)
    // The readout tracks the pointer whether or not a gesture is in flight. Written straight
    // to the DOM, so a hover sweep never re-renders the waveform.
    if (pixelsPerSecond > 0 && e.pointerType !== 'touch') guide.show(`${frac * 100}%`, frac * (duration as number), frac)
    const d = dragRef.current
    if (!d || d.pointerId !== e.pointerId) return
    if (d.mode === 'scrub') {
      onScrub?.(frac)
      return
    }
    d.end = frac
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
    // A scrub gesture never changes the selected slice -- it only moved the playhead.
    if (d.mode === 'scrub') return
    if (!d.moved) {
      onSelectRegion?.(null)
      onClick?.(d.start)
      return
    }
    onSelectRegion?.({ start: Math.min(d.start, d.end), end: Math.max(d.start, d.end) })
  }

  const interactive = onSelectRegion != null
  const band = dragBand ?? selection

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
      onPointerLeave={pixelsPerSecond > 0 ? guide.hide : undefined}
      style={{ touchAction: interactive ? 'none' : undefined }}
    >
      {/* center track line, like a DAW lane */}
      <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-border/60" />

      {/* hover time readout: the exact time under the pointer, same grammar as the ruler */}
      {pixelsPerSecond > 0 && (
        <div ref={guide.guideRef} data-testid={testId ? `${testId}-time` : undefined} className={HOVER_TIME_GUIDE_LINE_CLASS} style={{ left: 0, display: 'none' }}>
          <span ref={guide.labelRef} className={HOVER_TIME_GUIDE_LABEL_CLASS}>
            0.0s
          </span>
        </div>
      )}

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

      {/* The waveform and its playhead, drawn in one canvas pass (B-P2). The playhead comes
          from the media clock, so it moves at display rate instead of the browser's ~4 Hz
          `timeupdate`; nothing here re-renders per frame. */}
      <WaveformCanvas
        envelope={envelope}
        failed={failed}
        mediaRef={mediaRef}
        playing={playing}
        progress={progress}
        className="-m-px h-full"
        showPeakReadout
      />

      {/* bottom time axis */}
      {hasTimeAxis && ticks != null && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end">
          {ticks.map((t, i) => (
            <span
              key={i}
              className={cn(
                'absolute -bottom-0 text-[9px] font-mono tabular-nums text-muted-foreground/50',
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
