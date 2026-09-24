// The level meter (B-P4, fixes A1).
//
// What was here read a normalized peak bucket and printed it as a percentage. That is not a
// level: it has no unit, it cannot be compared between clips, and a percentage of a bucket is
// not a percentage of anything. This reads the clip's absolute envelope at the playhead, in
// dBFS, on the standard -60..0 scale, with the ballistics a meter needs to be readable:
//
//   - instant attack, so a transient is not smoothed away;
//   - ~20 dB per 1.5 s fall, so the eye can follow a decay;
//   - a peak-hold line that stays put for 1.5 s, then falls.
//
// It draws per animation frame from P2's media clock (fixing A2's `timeupdate` stepping) and
// writes `aria-valuenow` from the same value it draws, so assistive tech and the canvas cannot
// disagree. Reduced motion drops the fall easing but keeps the true level -- the level is data,
// not decoration.
import { memo, useEffect, useRef } from 'react'
import { dbFromAmplitude, METER_CEIL_DB, METER_FLOOR_DB, METER_TICKS, meterFraction, signalRampAt } from '@/lib/signal'
import type { AudioEnvelope } from '@/lib/waveform'
import { useMediaClock } from '@/hooks/useMediaClock'
import { useReducedMotionSafe } from '@/lib/motion'
import { cn } from '@/lib/utils'

const FALL_DB_PER_SECOND = 20 / 1.5
const PEAK_HOLD_MS = 1500

export interface LevelMeterProps {
  envelope: AudioEnvelope | null
  mediaRef?: React.RefObject<HTMLMediaElement | null> | null
  playing?: boolean
  /** Playhead position (0..1) when there is no element to read, so a paused meter still
   * reports the level where the playhead is parked. */
  progress?: number
  label?: string
  className?: string
}

/** Peak amplitude of the envelope bucket under `fraction`. */
function levelAt(envelope: AudioEnvelope, fraction: number): number {
  const level = envelope.levels[0]
  const index = Math.max(0, Math.min(level.max.length - 1, Math.floor(fraction * level.max.length)))
  return Math.max(Math.abs(level.max[index]), Math.abs(level.min[index]))
}

export const LevelMeter = memo(function LevelMeter({
  envelope,
  mediaRef = null,
  playing = false,
  progress = 0,
  label = 'Level',
  className,
}: LevelMeterProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const readoutRef = useRef<HTMLSpanElement | null>(null)
  const meterRef = useRef<HTMLDivElement | null>(null)
  const displayRef = useRef(METER_FLOOR_DB)
  const heldRef = useRef({ db: METER_FLOOR_DB, at: 0 })
  const lastFrameRef = useRef(0)
  const reduced = useReducedMotionSafe()
  const clock = useMediaClock(mediaRef ?? { current: null }, playing)
  const reducedRef = useRef(reduced)
  reducedRef.current = reduced

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const dpr = window.devicePixelRatio || 1

    const paint = (db: number) => {
      const width = canvas.clientWidth
      const height = canvas.clientHeight
      if (width <= 0 || height <= 0) return
      if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
        canvas.width = Math.round(width * dpr)
        canvas.height = Math.round(height * dpr)
      }
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, width, height)

      // Ticks first, so the bar covers them the way a real meter does.
      ctx.fillStyle = 'oklch(1 0 0 / 12%)'
      for (const tick of METER_TICKS) {
        ctx.fillRect(meterFraction(tick) * width, 0, 1, height)
      }

      // The bar: one colour per level, taken from the signal ramp so the meter, the waveform
      // and the spectrogram share one language.
      const filled = meterFraction(db) * width
      const steps = Math.max(1, Math.round(filled))
      for (let x = 0; x < steps; x++) {
        const t = steps <= 1 ? 0 : x / (steps - 1)
        const [light, chroma, hue] = signalRampAt(t)
        ctx.fillStyle = `oklch(${light} ${chroma} ${hue} / 0.9)`
        ctx.fillRect(x, 0, 1, height)
      }

      const held = heldRef.current.db
      if (held > METER_FLOOR_DB) {
        ctx.fillStyle = 'oklch(1 0 0 / 85%)'
        ctx.fillRect(meterFraction(held) * width - 0.5, 0, 1, height)
      }

      if (readoutRef.current) {
        readoutRef.current.textContent = db <= METER_FLOOR_DB ? '−∞' : db.toFixed(1)
      }
      meterRef.current?.setAttribute('aria-valuenow', String(Math.round(db * 10) / 10))
    }

    const step = (seconds: number | null) => {
      const now = performance.now()
      const elapsed = lastFrameRef.current === 0 ? 0 : (now - lastFrameRef.current) / 1000
      lastFrameRef.current = now
      const fraction = seconds != null && mediaRef?.current?.duration
        ? Math.min(1, Math.max(0, seconds / (mediaRef.current.duration || 1)))
        : progress
      const db = envelope ? dbFromAmplitude(levelAt(envelope, fraction)) : METER_FLOOR_DB

      // Instant attack, eased fall. Under reduced motion the fall is immediate: the level is
      // still true, only the ballistic travel is gone.
      const fall = reducedRef.current ? Number.POSITIVE_INFINITY : FALL_DB_PER_SECOND * elapsed
      displayRef.current = db > displayRef.current ? db : Math.max(db, displayRef.current - fall)

      const held = heldRef.current
      if (displayRef.current >= held.db) {
        heldRef.current = { db: displayRef.current, at: now }
      } else if (now - held.at > PEAK_HOLD_MS) {
        heldRef.current = { db: Math.max(displayRef.current, held.db - fall), at: held.at }
      }
      paint(displayRef.current)
    }

    if (mediaRef && playing) {
      return clock.subscribe((seconds) => step(seconds))
    }
    step(null)
  }, [clock, envelope, mediaRef, playing, progress])

  return (
    <div className={cn('flex min-w-28 flex-col gap-1', className)}>
      <div className="flex items-center justify-between text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
        <span>{label}</span>
        <span className="readout">
          <span ref={readoutRef}>−∞</span>
          <span className="readout-unit">dBFS</span>
        </span>
      </div>
      <div
        ref={meterRef}
        role="meter"
        aria-label={`${label} in dBFS`}
        aria-valuemin={METER_FLOOR_DB}
        aria-valuemax={METER_CEIL_DB}
        aria-valuenow={METER_FLOOR_DB}
        className="well relative h-2.5 overflow-hidden"
      >
        <canvas ref={canvasRef} className="block h-full w-full" />
      </div>
    </div>
  )
})
