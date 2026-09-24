// Spectrogram view (B-P3). Real spectral data, drawn once off-screen and blitted.
//
// Layout: the STFT frames run left-to-right over the clip's duration, and the vertical axis is
// log-frequency over 50 Hz - 12 kHz with the high end at the top. Magnitudes are absolute, so
// the colour means the same thing on every clip: dBFS through the signal palette.
//
// Cost: the transform runs in a worker and the image is drawn once, so per-frame work is a
// blit plus the playhead. The playhead comes from P2's media clock, which is what keeps it
// moving at display rate instead of stepping with `timeupdate`.
import { useEffect, useRef, useState } from 'react'
import { dbForMagnitude, getSpectrogram, hzForRow, magnitudeAt, spectroColor, type Spectrogram } from '@/lib/spectrogram'
import { SIGNAL_PLAYHEAD } from '@/lib/signal'
import { useMediaClock } from '@/hooks/useMediaClock'
import { cn } from '@/lib/utils'

export interface SpectrogramCanvasProps {
  blob: Blob | null
  /** Analysis-contract cache key: `spectrogram:<kind>:<persistent-id>:<revision>`. */
  cacheKey: string | null
  mediaRef?: React.RefObject<HTMLMediaElement | null> | null
  playing?: boolean
  className?: string
  testId?: string
}

export function SpectrogramCanvas({
  blob,
  cacheKey,
  mediaRef = null,
  playing = false,
  className,
  testId,
}: SpectrogramCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const imageRef = useRef<HTMLCanvasElement | null>(null)
  const spectrogramRef = useRef<Spectrogram | null>(null)
  const [spectrogram, setSpectrogram] = useState<Spectrogram | null>(null)
  const [failed, setFailed] = useState(false)
  const clock = useMediaClock(mediaRef ?? { current: null }, playing)
  const playheadRef = useRef<number | null>(null)
  const readoutRef = useRef<HTMLSpanElement | null>(null)

  // Decode, then transform off-thread. The decode is async and lives in the browser, so this
  // never blocks a frame either.
  useEffect(() => {
    let dead = false
    setSpectrogram(null)
    setFailed(false)
    spectrogramRef.current = null
    if (!blob || !cacheKey) return
    const run = async () => {
      try {
        const ctx = new AudioContext()
        const buffer = await ctx.decodeAudioData(await blob.arrayBuffer())
        const samples = buffer.getChannelData(0)
        const result = await getSpectrogram(cacheKey, samples, buffer.sampleRate)
        void ctx.close()
        if (!dead) {
          spectrogramRef.current = result
          setSpectrogram(result)
        }
      } catch {
        if (!dead) setFailed(true)
      }
    }
    void run()
    return () => {
      dead = true
    }
  }, [blob, cacheKey])

  // Paint the spectrogram once into an off-screen canvas; frames blit it and add the playhead.
  useEffect(() => {
    if (!spectrogram) return
    const canvas = canvasRef.current
    if (!canvas) return
    const dpr = window.devicePixelRatio || 1
    const width = Math.max(1, Math.round(canvas.clientWidth * dpr))
    const height = Math.max(1, Math.round(canvas.clientHeight * dpr))
    canvas.width = width
    canvas.height = height

    const offscreen = imageRef.current ?? document.createElement('canvas')
    imageRef.current = offscreen
    offscreen.width = Math.max(1, spectrogram.frames)
    offscreen.height = height
    const offCtx = offscreen.getContext('2d')
    if (!offCtx) return
    const image = offCtx.createImageData(offscreen.width, offscreen.height)
    const { magnitudes, bins, sampleRate, frames } = spectrogram
    const nyquist = sampleRate / 2

    for (let y = 0; y < height; y++) {
      // Row -> frequency once per row, then bin once per row: the inner loop is a lookup.
      const hz = hzForRow(y, height)
      const bin = Math.max(0, Math.min(bins - 1, Math.round((hz / nyquist) * (bins - 1))))
      for (let x = 0; x < frames; x++) {
        const db = dbForMagnitude(magnitudes[x * bins + bin])
        const [r, g, b] = spectroColor(db)
        const offset = (y * frames + x) * 4
        image.data[offset] = r
        image.data[offset + 1] = g
        image.data[offset + 2] = b
        image.data[offset + 3] = 255
      }
    }
    offCtx.putImageData(image, 0, 0)

    const paint = () => {
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      ctx.setTransform(1, 0, 0, 1, 0, 0)
      ctx.drawImage(offscreen, 0, 0, width, height)
      const fraction = playheadRef.current
      if (fraction != null && fraction >= 0 && fraction <= 1) {
        ctx.fillStyle = SIGNAL_PLAYHEAD
        ctx.fillRect(fraction * width - 0.5, 0, 1, height)
      }
    }
    paint()

    const observer = new ResizeObserver(paint)
    observer.observe(canvas)
    return () => observer.disconnect()
  }, [spectrogram])

  // Playhead per frame, from the media clock -- no React state per frame.
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const publish = (fraction: number) => {
      playheadRef.current = fraction
      canvas.setAttribute('data-playhead-pct', fraction.toFixed(4))
      const offscreen = imageRef.current
      const ctx = canvas.getContext('2d')
      if (!offscreen || !ctx) return
      ctx.setTransform(1, 0, 0, 1, 0, 0)
      ctx.drawImage(offscreen, 0, 0, canvas.width, canvas.height)
      if (fraction >= 0 && fraction <= 1) {
        ctx.fillStyle = SIGNAL_PLAYHEAD
        ctx.fillRect(fraction * canvas.width - 0.5, 0, 1, canvas.height)
      }
    }
    if (mediaRef && playing) {
      const duration = mediaRef.current?.duration
      return clock.subscribe((seconds) => {
        const total = duration != null && isFinite(duration) && duration > 0 ? duration : null
        publish(total == null ? 0 : Math.min(1, Math.max(0, seconds / total)))
      })
    }
    publish(0)
  }, [clock, mediaRef, playing, spectrogram])

  // Hover: the readout is the whole reason the axis exists, so it reports time, frequency and
  // level together rather than making the reader estimate from the colour.
  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const spec = spectrogramRef.current
    const el = readoutRef.current
    if (!spec || !el) return
    const rect = event.currentTarget.getBoundingClientRect()
    if (rect.width <= 0 || rect.height <= 0) return
    const xFrac = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width))
    const yFrac = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height))
    const dpr = window.devicePixelRatio || 1
    const row = yFrac * (Math.max(1, Math.round(rect.height * dpr)) - 1)
    const hz = hzForRow(row, Math.max(1, Math.round(rect.height * dpr)))
    const frame = xFrac * spec.frames
    const db = dbForMagnitude(magnitudeAt(spec, frame, hz))
    el.textContent = `${(xFrac * spec.durationMs / 1000).toFixed(2)}s · ${hz < 1000 ? `${hz.toFixed(0)} Hz` : `${(hz / 1000).toFixed(2)} kHz`} · ${db.toFixed(1)} dB`
    el.style.opacity = '1'
  }

  if (failed) {
    return (
      <div data-testid={testId} className={cn('flex h-full w-full items-center justify-center text-[10px] text-muted-foreground/60', className)}>
        No spectrum
      </div>
    )
  }

  return (
    <div
      className={cn('relative flex h-full w-full items-center overflow-hidden', className)}
      onPointerMove={onPointerMove}
      onPointerLeave={() => {
        if (readoutRef.current) readoutRef.current.style.opacity = '0'
      }}
    >
      {spectrogram ? (
        <>
          <canvas ref={canvasRef} data-testid="spectrogram-canvas" className="block h-full w-full" />
          <span
            ref={readoutRef}
            data-testid="spectrogram-readout"
            className="readout pointer-events-none absolute top-0.5 right-1 rounded bg-background/70 px-1 text-[10px] opacity-0 transition-opacity"
          />
        </>
      ) : (
        <div
          data-testid={testId}
          className="relative flex h-full w-full items-center justify-center overflow-hidden"
        >
          <div className="h-1/3 w-2/3 animate-pulse rounded-sm bg-muted/40" />
          <div data-testid="spectrogram-skeleton" className="absolute inset-0" />
        </div>
      )}
    </div>
  )
}
