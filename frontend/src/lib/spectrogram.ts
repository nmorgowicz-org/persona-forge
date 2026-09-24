// Spectrogram: worker management, cache, log-frequency axis, and the signal colormap (B-P3).
//
// A6's problem was that `SpectralAccent` drew the peak array as cells and invented a sine when
// it had nothing -- a picture that was never spectral data. This module is the real thing: the
// STFT runs in a module worker (lib/stft.worker.ts), magnitudes come back in absolute units,
// and the axis is log-frequency over the voice-relevant 50 Hz - 12 kHz.
import { useSyncExternalStore } from 'react'
import { SPECTRO_CEIL_DB, SPECTRO_FLOOR_DB, SPECTRO_STOPS } from '@/lib/signal'

export interface Spectrogram {
  /** Absolute magnitude per (frame, bin), row-major. */
  magnitudes: Float32Array
  frames: number
  bins: number
  sampleRate: number
  windowSize: number
  hop: number
  durationMs: number
}

export const SPECTRO_F_MIN = 50
export const SPECTRO_F_MAX = 12000

/** Frequency at row `y` of an `height`-row canvas: high frequencies at the top, which is what
 * the spec's axis formula asserts and what every analyzer does. */
export function hzForRow(y: number, height: number): number {
  if (height <= 1) return SPECTRO_F_MIN
  return SPECTRO_F_MIN * (SPECTRO_F_MAX / SPECTRO_F_MIN) ** (1 - y / (height - 1))
}

/** Inverse of `hzForRow`, for hit-testing and axis ticks. */
export function rowForHz(hz: number, height: number): number {
  const clamped = Math.max(SPECTRO_F_MIN, Math.min(SPECTRO_F_MAX, hz))
  return (1 - Math.log(clamped / SPECTRO_F_MIN) / Math.log(SPECTRO_F_MAX / SPECTRO_F_MIN)) * (height - 1)
}

/** dBFS for a magnitude, clamped to the display window. */
export function dbForMagnitude(magnitude: number): number {
  if (magnitude <= 0) return SPECTRO_FLOOR_DB
  return Math.max(SPECTRO_FLOOR_DB, Math.min(SPECTRO_CEIL_DB, 20 * Math.log10(magnitude)))
}

const FRAME_LRU_MAX = 64
const spectrogramCache = new Map<string, Spectrogram>()

function touch(key: string, value: Spectrogram): void {
  spectrogramCache.delete(key)
  spectrogramCache.set(key, value)
  while (spectrogramCache.size > FRAME_LRU_MAX) {
    const oldest = spectrogramCache.keys().next().value
    if (oldest === undefined) break
    spectrogramCache.delete(oldest)
  }
}

let worker: Worker | null = null
let nextRequestId = 1
const pending = new Map<number, { resolve: (value: Spectrogram) => void; reject: (error: Error) => void }>()

function ensureWorker(): Worker | null {
  if (worker) return worker
  if (typeof Worker === 'undefined') return null
  worker = new Worker(new URL('./stft.worker.ts', import.meta.url), { type: 'module' })
  worker.onmessage = (event: MessageEvent<Spectrogram & { requestId: number }>) => {
    const entry = pending.get(event.data.requestId)
    pending.delete(event.data.requestId)
    entry?.resolve(event.data)
  }
  worker.onerror = () => {
    for (const [id, entry] of pending) {
      pending.delete(id)
      entry.reject(new Error('STFT worker failed'))
    }
  }
  return worker
}

/**
 * Compute (or reuse) the spectrogram for a decoded clip. `cacheKey` follows the analysis
 * contract: `spectrogram:<kind>:<persistent-id>:<revision>`.
 */
export async function getSpectrogram(
  cacheKey: string,
  samples: Float32Array,
  sampleRate: number,
): Promise<Spectrogram> {
  const cached = spectrogramCache.get(cacheKey)
  if (cached) {
    touch(cacheKey, cached)
    return cached
  }
  const instance = ensureWorker()
  if (!instance) throw new Error('Web Workers are unavailable')
  const requestId = nextRequestId++
  const result = await new Promise<Spectrogram>((resolve, reject) => {
    pending.set(requestId, { resolve, reject })
    // One copy goes to the worker, and its buffer is transferred: the caller's samples are the
    // decoded clip, which other surfaces may still need, so they are never handed away.
    const payload = samples.slice()
    instance.postMessage(
      { requestId, samples: payload, sampleRate, windowSize: 1024, hop: 256 },
      [payload.buffer],
    )
  })
  touch(cacheKey, result)
  return result
}

/** Magnitude at a time/frequency point, for the hover readout. */
export function magnitudeAt(spectrogram: Spectrogram, frame: number, hz: number): number {
  const clampedFrame = Math.max(0, Math.min(spectrogram.frames - 1, Math.round(frame)))
  const bin = Math.round((hz / (spectrogram.sampleRate / 2)) * (spectrogram.bins - 1))
  const clampedBin = Math.max(0, Math.min(spectrogram.bins - 1, bin))
  return spectrogram.magnitudes[clampedFrame * spectrogram.bins + clampedBin] ?? 0
}

/**
 * Colormap lookup built from `SPECTRO_STOPS`, using the browser's own color math: the stops are
 * CSS strings (hex and oklch), so a 256px gradient is drawn once into a canvas and read back as
 * RGB. Writing an oklch-to-sRGB conversion by hand would be a second, divergent implementation
 * of something the engine already does correctly.
 */
let colorTable: Uint8ClampedArray | null = null

function ensureColorTable(): Uint8ClampedArray | null {
  if (colorTable) return colorTable
  if (typeof document === 'undefined') return null
  const canvas = document.createElement('canvas')
  canvas.width = 256
  canvas.height = 1
  const ctx = canvas.getContext('2d')
  if (!ctx) return null
  const gradient = ctx.createLinearGradient(0, 0, 256, 0)
  SPECTRO_STOPS.forEach((stop, index) => {
    gradient.addColorStop(index / (SPECTRO_STOPS.length - 1), stop)
  })
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, 256, 1)
  colorTable = ctx.getImageData(0, 0, 256, 1).data
  return colorTable
}

/** RGB for a dBFS level, through the signal-palette colormap. */
export function spectroColor(db: number): [number, number, number] {
  const table = ensureColorTable()
  const t = (db - SPECTRO_FLOOR_DB) / (SPECTRO_CEIL_DB - SPECTRO_FLOOR_DB)
  const index = Math.max(0, Math.min(255, Math.round(t * 255)))
  if (!table) return [index, index, index]
  return [table[index * 4], table[index * 4 + 1], table[index * 4 + 2]]
}

// ---- The Wave/Spectrum view preference -------------------------------------------------------
//
// A session preference, not a per-deck one: switching a deck to Spectrum and then walking to
// another page and back must not silently undo it, and it is the same choice on every surface
// that offers it. Module state (like the A/B snapshots): it survives navigation, resets on
// reload, and is never written to the store or the backend.

export type SignalView = 'wave' | 'spectrum'

let view: SignalView = 'wave'
const viewListeners = new Set<() => void>()

export function setSignalView(next: SignalView): void {
  if (view === next) return
  view = next
  for (const listener of viewListeners) listener()
}

function subscribeView(listener: () => void): () => void {
  viewListeners.add(listener)
  return () => {
    viewListeners.delete(listener)
  }
}

export function useSignalView(): SignalView {
  return useSyncExternalStore(
    subscribeView,
    () => view,
    () => 'wave' as SignalView,
  )
}
