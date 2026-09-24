// Decodes an audio Blob into peak amplitudes for waveform rendering.
// Buckets are chosen relative to duration so the waveform visually spans the
// full width of the container instead of bunching into one side.

let sharedContext: AudioContext | null = null

function getAudioContext(): AudioContext {
  if (!sharedContext) sharedContext = new AudioContext()
  return sharedContext
}

// ---- Multi-resolution envelope (B-P2) --------------------------------------------------
//
// The waveform has to be true to level: a clip recorded 18 dB quieter must *look* quieter
// next to its neighbour, which is the single most useful thing to see when stitching
// segments. That is impossible from the old normalized peak array, and impossible at a fixed
// 120 buckets -- a 900 px lane wants ~900 columns, not 120 stretched ones.
//
// So the decode produces a pyramid of min/max/RMS in **absolute sample units** (never
// normalized), 256 samples at the base and x4 per level. Rendering picks the level that has
// at least as many buckets as the lane has pixels and aggregates down, so zooming and
// resizing never re-decode, and level is preserved all the way through.

/** One pyramid level. `bucketSize` is in samples; the arrays are per bucket, absolute units. */
export interface EnvelopeLevel {
  bucketSize: number
  min: Float32Array
  max: Float32Array
  rms: Float32Array
}

export interface AudioEnvelope {
  durationMs: number
  sampleRate: number
  /** Level 0 is the finest (256 samples per bucket); each next level is 4x coarser. */
  levels: EnvelopeLevel[]
  /** Largest absolute sample in the whole buffer, and its level in dBFS. */
  peakAbs: number
  peakDbfs: number
}

const BASE_BUCKET_SAMPLES = 256
const PYRAMID_FACTOR = 4
/** Past this the pyramid stops growing: below one bucket per pixel there is nothing to gain. */
const MAX_LEVELS = 6

function envelopeFromBuffer(audioBuffer: AudioBuffer): AudioEnvelope {
  return envelopeFromChannels([audioBuffer.getChannelData(0)], audioBuffer.sampleRate)
}

/** Build an envelope from samples already in memory (no decode). */
export function envelopeFromChannels(channels: Float32Array[], sampleRate: number): AudioEnvelope {
  const channel = channels[0]

  let min = new Float32Array(Math.max(1, Math.ceil(channel.length / BASE_BUCKET_SAMPLES)))
  let max = new Float32Array(min.length)
  let rms = new Float32Array(min.length)
  let peakAbs = 0

  for (let bucket = 0; bucket < min.length; bucket++) {
    const start = bucket * BASE_BUCKET_SAMPLES
    const end = Math.min(start + BASE_BUCKET_SAMPLES, channel.length)
    let lo = 0
    let hi = 0
    let sumSquares = 0
    for (let i = start; i < end; i++) {
      const value = channel[i]
      if (value < lo) lo = value
      if (value > hi) hi = value
      sumSquares += value * value
    }
    const count = Math.max(1, end - start)
    min[bucket] = lo
    max[bucket] = hi
    rms[bucket] = Math.sqrt(sumSquares / count)
    const abs = Math.max(Math.abs(lo), Math.abs(hi))
    if (abs > peakAbs) peakAbs = abs
  }

  const levels: EnvelopeLevel[] = [{ bucketSize: BASE_BUCKET_SAMPLES, min, max, rms }]
  for (let level = 1; level < MAX_LEVELS && min.length > 1; level++) {
    const count = Math.max(1, Math.ceil(min.length / PYRAMID_FACTOR))
    const nextMin = new Float32Array(count)
    const nextMax = new Float32Array(count)
    const nextRms = new Float32Array(count)
    for (let bucket = 0; bucket < count; bucket++) {
      let lo = Infinity
      let hi = -Infinity
      let sumSquares = 0
      let n = 0
      for (let k = bucket * PYRAMID_FACTOR; k < Math.min((bucket + 1) * PYRAMID_FACTOR, min.length); k++) {
        if (min[k] < lo) lo = min[k]
        if (max[k] > hi) hi = max[k]
        sumSquares += rms[k] * rms[k]
        n++
      }
      nextMin[bucket] = n > 0 ? lo : 0
      nextMax[bucket] = n > 0 ? hi : 0
      nextRms[bucket] = n > 0 ? Math.sqrt(sumSquares / n) : 0
    }
    min = nextMin
    max = nextMax
    rms = nextRms
    levels.push({ bucketSize: BASE_BUCKET_SAMPLES * PYRAMID_FACTOR ** level, min, max, rms })
  }

  return {
    durationMs: Math.round((channel.length / sampleRate) * 1000),
    sampleRate,
    levels,
    peakAbs,
    peakDbfs: peakAbs > 0 ? 20 * Math.log10(peakAbs) : -Infinity,
  }
}

/** Decode a blob into a true-scale envelope. */
export async function computeEnvelope(blob: Blob): Promise<AudioEnvelope> {
  const arrayBuffer = await blob.arrayBuffer()
  const ctx = getAudioContext()
  const audioBuffer = await ctx.decodeAudioData(arrayBuffer.slice(0))
  return envelopeFromBuffer(audioBuffer)
}

/** The pyramid level whose bucket count is at least `count` (finest that still covers it). */
function levelFor(levels: EnvelopeLevel[], count: number): EnvelopeLevel {
  for (const level of levels) {
    if (level.max.length <= count) return level
  }
  return levels[levels.length - 1]
}

export interface EnvelopeColumn {
  min: number
  max: number
  rms: number
}

/**
 * Columns for a window of the source, in absolute units. `count` should be the lane's device
 * pixels divided by the bar pitch, so density follows the pixels rather than a constant.
 */
export function envelopeColumns(
  envelope: AudioEnvelope,
  startMs: number,
  endMs: number,
  count: number,
): EnvelopeColumn[] {
  const columns: EnvelopeColumn[] = []
  const wanted = Math.max(1, Math.round(count))
  const level = levelFor(envelope.levels, wanted)
  const totalMs = Math.max(1, envelope.durationMs)
  const from = Math.max(0, Math.min(startMs, totalMs))
  const to = Math.max(from + 1, Math.min(endMs, totalMs))
  const samplesPerMs = envelope.sampleRate / 1000
  const startBucket = Math.floor((from * samplesPerMs) / level.bucketSize)
  const endBucket = Math.max(startBucket + 1, Math.ceil((to * samplesPerMs) / level.bucketSize))
  const span = endBucket - startBucket
  const step = span / wanted

  for (let column = 0; column < wanted; column++) {
    const bucketStart = startBucket + Math.floor(column * step)
    const bucketEnd = Math.max(bucketStart + 1, startBucket + Math.floor((column + 1) * step))
    let lo = Infinity
    let hi = -Infinity
    let sumSquares = 0
    let n = 0
    for (let bucket = bucketStart; bucket < Math.min(bucketEnd, level.max.length); bucket++) {
      if (level.min[bucket] < lo) lo = level.min[bucket]
      if (level.max[bucket] > hi) hi = level.max[bucket]
      sumSquares += level.rms[bucket] * level.rms[bucket]
      n++
    }
    columns.push({
      min: n > 0 ? lo : 0,
      max: n > 0 ? hi : 0,
      rms: n > 0 ? Math.sqrt(sumSquares / n) : 0,
    })
  }
  return columns
}

/** Normalized peaks derived from an envelope, for consumers that still want the old shape. */
export function envelopePeaks(envelope: AudioEnvelope, buckets?: number): number[] {
  const level = levelFor(envelope.levels, buckets ?? 64)
  const source = level.max.length <= (buckets ?? 64) ? level.max : null
  if (source) {
    const overall = Math.max(...source, 0.01)
    return Array.from(source, (value) => value / overall)
  }
  const columns = envelopeColumns(envelope, 0, envelope.durationMs, buckets ?? 64)
  const overall = Math.max(...columns.map((c) => c.max), 0.01)
  return columns.map((c) => c.max / overall)
}

// ---- Shared clip-audio-analysis cache (locked contract: docs/plans/20260920- ----
// stitch_studio_ux_execution_plan.md "Audio-analysis contract"). Callers key entries with
// `<kind>:<persistent-id>:<revision>` so a clip's cached peaks/duration survive re-renders
// but are invalidated whenever the underlying audio actually changes.

export interface ClipAudioAnalysis {
  durationMs: number
  sampleRate: number
  peaks: number[]
  /** B-P2: absolute-unit pyramid. Additive -- `peaks` stays for any consumer not migrated. */
  envelope: AudioEnvelope | null
  /** True when the audio could not be decoded. Distinct from `envelope === null`, which also
   * means "not loaded yet": a surface must not show a loading state forever for audio that
   * will never arrive. */
  decodeFailed: boolean
}

const ANALYSIS_CACHE_MAX = 64
// Map preserves insertion order, which doubles as LRU recency when re-inserted on touch.
const analysisCache = new Map<string, ClipAudioAnalysis>()

function cacheKeyFor(assetKey: string, buckets: number | undefined): string {
  return `${assetKey}::${buckets ?? 'auto'}`
}

function touchCache(key: string, value: ClipAudioAnalysis): void {
  analysisCache.delete(key)
  analysisCache.set(key, value)
  while (analysisCache.size > ANALYSIS_CACHE_MAX) {
    const oldestKey = analysisCache.keys().next().value
    if (oldestKey === undefined) break
    analysisCache.delete(oldestKey)
  }
}

async function blobFromAudioSource(audio: Blob | string): Promise<Blob> {
  if (typeof audio !== 'string') return audio
  const byteStr = atob(audio)
  const bytes = new Uint8Array(byteStr.length)
  for (let i = 0; i < byteStr.length; i++) bytes[i] = byteStr.charCodeAt(i)
  return new Blob([bytes])
}

/** Decodes (or returns a cached decode of) `audio`, keyed by `assetKey` plus the requested
 * bucket count. A failed decode is never cached -- a later call with valid audio for the
 * same key must not be poisoned by a cached failure. */
export async function getClipAudioAnalysis(
  assetKey: string,
  audio: Blob | string,
  buckets?: number,
): Promise<ClipAudioAnalysis> {
  const cacheKey = cacheKeyFor(assetKey, buckets)
  const cached = analysisCache.get(cacheKey)
  if (cached) {
    touchCache(cacheKey, cached)
    return cached
  }

  const ctx = getAudioContext()
  let audioBuffer: AudioBuffer
  try {
    const blob = await blobFromAudioSource(audio)
    const arrayBuffer = await blob.arrayBuffer()
    audioBuffer = await ctx.decodeAudioData(arrayBuffer.slice(0))
  } catch {
    return { durationMs: 0, sampleRate: ctx.sampleRate, peaks: [], envelope: null, decodeFailed: true }
  }

  const envelope = envelopeFromBuffer(audioBuffer)
  const analysis: ClipAudioAnalysis = {
    durationMs: envelope.durationMs,
    sampleRate: audioBuffer.sampleRate,
    // Derived from the envelope so the two can never disagree about the same audio.
    peaks: envelopePeaks(envelope, buckets),
    envelope,
    decodeFailed: false,
  }
  touchCache(cacheKey, analysis)
  return analysis
}
