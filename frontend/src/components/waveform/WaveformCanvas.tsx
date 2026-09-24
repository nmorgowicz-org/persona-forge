// The one waveform renderer (B-P2). Every waveform surface in the app draws through this:
// the Speak/VoiceDesign/OmniVoice decks, stitch clip lanes, the prosody A/B lanes, the variant
// compare, the region editor. It replaces two ad-hoc drawings -- 64-120 animated DOM nodes in
// the deck and a separate canvas in the lane -- that disagreed about scale, resolution and
// colour.
//
// What it is honest about:
//
// - **Level.** Columns come from the envelope pyramid in absolute units, so a clip 18 dB
//   quieter draws shorter. Multi-clip views pass a shared `scaleFloorDbfs` so all lanes share
//   one vertical scale; a lone clip may auto-fit, but then it must say so (`showPeakReadout`),
//   because a fitted waveform looks identical to a loud one.
// - **Resolution.** Column count follows the lane's device pixels, not a constant: zoom and
//   resize never re-decode, they pick a different pyramid level.
// - **Motion.** The playhead is drawn in the same pass from `useMediaClock`, per animation
//   frame, and written to `data-playhead-pct` so a test can prove display-rate motion without
//   reading pixels.
// - **Loading.** No signal before the audio exists: a designed skeleton, never placeholder
//   bars (audit A5).
import { useEffect, useRef, type RefObject } from 'react'
import { SIGNAL_PLAYHEAD, heat, signalColor } from '@/lib/signal'
import { envelopeColumns, type AudioEnvelope } from '@/lib/waveform'
import { useMediaClock } from '@/hooks/useMediaClock'
import { cn } from '@/lib/utils'

/** Device pixels between column centres. ~2 keeps the mirrored outline reading as a
 * continuous silhouette instead of a picket fence, which is what the reference board draws. */
const BAR_PITCH = 2

export interface WaveformCanvasProps {
  envelope: AudioEnvelope | null
  /** Source window to draw, in ms. Defaults to the whole clip. */
  startMs?: number
  endMs?: number
  /**
   * The absolute amplitude that maps to full height, shared by every lane on screen. Omit for
   * a single-clip view: it auto-fits to its own peak and shows the readout.
   */
  scaleAbs?: number | null
  /** Element whose `currentTime` drives the playhead. */
  mediaRef?: RefObject<HTMLMediaElement | null> | null
  /** Whether the media is advancing (starts/stops the clock). */
  playing?: boolean
  /** Static playhead for surfaces with no element of their own (0..1). */
  progress?: number
  /** Show the `-x dBFS` peak readout, required whenever the view auto-fits. */
  showPeakReadout?: boolean
  /** The audio could not be decoded. Renders the "No waveform" fallback rather than the
   * loading skeleton, which would otherwise shimmer forever for audio that never arrives. */
  failed?: boolean
  className?: string
  testId?: string
  /** The canvas element's own testid. Hosts that already name their canvas (the stitch lane)
   * keep that name, so existing specs and captures still find it. */
  canvasTestId?: string
  /** Extra drawing (region tints, pause bands) between the waveform and the playhead. */
  onOverlay?: (ctx: CanvasRenderingContext2D, size: { width: number; height: number }) => void
}

export function WaveformCanvas({
  envelope,
  startMs = 0,
  endMs,
  scaleAbs = null,
  mediaRef = null,
  playing = false,
  progress = 0,
  showPeakReadout = false,
  failed = false,
  className,
  testId,
  canvasTestId = 'waveform-canvas',
  onOverlay,
}: WaveformCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const clock = useMediaClock(mediaRef ?? { current: null }, playing)
  // Read by the draw pass, so a frame callback never has to re-create the drawing closure.
  const drawRef = useRef<() => void>(() => {})
  const playheadRef = useRef<number | null>(null)

  const windowStart = startMs
  const windowEnd = endMs ?? envelope?.durationMs ?? 0
  const autoFit = scaleAbs == null
  const effectiveScale = scaleAbs ?? envelope?.peakAbs ?? 1

  // One drawing routine, called on data/layout changes and on every clock frame. The waveform
  // itself is drawn once per resize; only the playhead is redrawn per frame, because redrawing
  // a 900-column silhouette at 60 Hz is work nobody asked for.
  useEffect(() => {
    drawRef.current = () => {
      const canvas = canvasRef.current
      if (!canvas || !envelope) return
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      const dpr = window.devicePixelRatio || 1
      const width = canvas.clientWidth
      const height = canvas.clientHeight
      if (width <= 0 || height <= 0) return
      if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
        canvas.width = Math.round(width * dpr)
        canvas.height = Math.round(height * dpr)
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, width, height)

      const columns = Math.max(1, Math.round(width / BAR_PITCH))
      const data = envelopeColumns(envelope, windowStart, windowEnd, columns)
      const mid = height / 2
      const scale = effectiveScale > 0 ? effectiveScale : 1
      const barWidth = width / columns

      const playheadFraction = playheadRef.current
      const playedUntil = playheadFraction == null ? -1 : playheadFraction

      data.forEach((column, index) => {
        const x = index * barWidth
        const fraction = index / columns
        const played = fraction <= playedUntil
        // Mirrored peak outline, then the brighter RMS body inside it: the pro-DAW two-tone
        // silhouette. `heat` maps dBFS, not linear amplitude, so speech at -6 dBFS actually
        // reaches the warm end of the ramp.
        const peakHalf = Math.max(0.5, (Math.max(Math.abs(column.max), Math.abs(column.min)) / scale) * mid)
        ctx.fillStyle = signalColor(Math.min(1, heat(column.max) * 0.7), played)
        ctx.fillRect(x, mid - peakHalf, Math.max(1, barWidth - 0.5), peakHalf * 2)

        const rmsHalf = Math.max(0.5, (column.rms / scale) * mid)
        ctx.fillStyle = signalColor(Math.min(1, heat(column.rms) * 1.15), played)
        ctx.fillRect(x, mid - rmsHalf, Math.max(1, barWidth - 0.5), rmsHalf * 2)
      })

      onOverlay?.(ctx, { width, height })

      if (playheadFraction != null && playheadFraction >= 0 && playheadFraction <= 1) {
        const x = playheadFraction * width
        // The playhead reads as light rather than paint: a short shadow under the line, which
        // costs one property and no per-frame layout (B-P7).
        ctx.save()
        ctx.shadowColor = SIGNAL_PLAYHEAD
        ctx.shadowBlur = 8
        ctx.fillStyle = SIGNAL_PLAYHEAD
        ctx.fillRect(x - 0.5, 0, 1, height)
        ctx.beginPath()
        ctx.arc(x, 4, 3.5, 0, Math.PI * 2)
        ctx.fill()
        ctx.restore()
      }
    }
  }, [envelope, windowStart, windowEnd, effectiveScale, onOverlay])

  // Redraw on data/layout changes.
  useEffect(() => {
    drawRef.current()
    const canvas = canvasRef.current
    if (!canvas) return
    const observer = new ResizeObserver(() => drawRef.current())
    observer.observe(canvas)
    return () => observer.disconnect()
  }, [envelope, windowStart, windowEnd, effectiveScale, onOverlay])

  // Playhead: per frame from the media clock when there is an element, otherwise from the
  // static `progress` the caller already has.
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const publish = (fraction: number) => {
      playheadRef.current = fraction
      canvas.setAttribute('data-playhead-pct', fraction.toFixed(4))
      drawRef.current()
    }
    if (mediaRef && playing) {
      const duration = mediaRef.current?.duration
      return clock.subscribe((seconds) => {
        const total = duration != null && isFinite(duration) && duration > 0 ? duration : null
        publish(total == null ? 0 : Math.min(1, Math.max(0, seconds / total)))
      })
    }
    publish(progress)
  }, [clock, mediaRef, playing, progress])

  if (!envelope) {
    if (failed) {
      return (
        <div
          data-testid={testId}
          className={cn('flex h-full w-full items-center justify-center text-[10px] text-muted-foreground/60', className)}
        >
          No waveform
        </div>
      )
    }
    return (
      <div
        data-testid={testId}
        className={cn('relative flex h-full w-full items-center justify-center overflow-hidden', className)}
        aria-hidden
      >
        {/* A designed skeleton: a hairline centre track and a shimmer, no invented bars. */}
        <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-border/50" />
        <div className="h-1/3 w-2/3 animate-pulse rounded-sm bg-muted/40" />
        <div data-testid="waveform-skeleton" className="absolute inset-0" />
      </div>
    )
  }

  return (
    <div data-testid={testId} className={cn('relative flex h-full w-full items-center overflow-hidden', className)}>
      <canvas ref={canvasRef} data-testid={canvasTestId} className="block h-full w-full" />
      {showPeakReadout && autoFit && (
        <span className="readout absolute top-0.5 right-1 text-[10px] text-muted-foreground/70">
          {envelope.peakDbfs === -Infinity ? '−∞' : envelope.peakDbfs.toFixed(1)}
          <span className="readout-unit">dBFS</span>
        </span>
      )}
    </div>
  )
}
