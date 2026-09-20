// Decodes an audio Blob into peak amplitudes for waveform rendering.
// Buckets are chosen relative to duration so the waveform visually spans the
// full width of the container instead of bunching into one side.
let sharedContext: AudioContext | null = null

function getAudioContext(): AudioContext {
  if (!sharedContext) sharedContext = new AudioContext()
  return sharedContext
}

function bucketsForDuration(duration: number): number {
  if (duration <= 0 || !isFinite(duration)) return 64
  const target = Math.round(duration * 24)
  return Math.max(24, Math.min(target, 120))
}

export async function computePeaks(blob: Blob, buckets?: number): Promise<number[]> {
  const arrayBuffer = await blob.arrayBuffer()
  const ctx = getAudioContext()
  const audioBuffer = await ctx.decodeAudioData(arrayBuffer.slice(0))
  const channel = audioBuffer.getChannelData(0)

  const count =
    buckets != null
      ? buckets
      : bucketsForDuration(audioBuffer.duration)

  const bucketSize = Math.max(1, Math.floor(channel.length / count))
  const peaks: number[] = []
  for (let i = 0; i < count; i++) {
    const start = i * bucketSize
    const end = Math.min(start + bucketSize, channel.length)
    let max = 0
    for (let j = start; j < end; j++) {
      const abs = Math.abs(channel[j])
      if (abs > max) max = abs
    }
    peaks.push(max)
  }
  const overallMax = Math.max(...peaks, 0.01)
  return peaks.map((p) => p / overallMax)
}

// ---- Shared clip-audio-analysis cache (locked contract: docs/plans/20260920- ----
// stitch_studio_ux_execution_plan.md "Audio-analysis contract"). Callers key entries with
// `<kind>:<persistent-id>:<revision>` so a clip's cached peaks/duration survive re-renders
// but are invalidated whenever the underlying audio actually changes.

export interface ClipAudioAnalysis {
  durationMs: number
  sampleRate: number
  peaks: number[]
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
    return { durationMs: 0, sampleRate: ctx.sampleRate, peaks: [] }
  }

  const channel = audioBuffer.getChannelData(0)
  const count = buckets ?? bucketsForDuration(audioBuffer.duration)
  const bucketSize = Math.max(1, Math.floor(channel.length / count))
  const peaks: number[] = []
  for (let i = 0; i < count; i++) {
    const start = i * bucketSize
    const end = Math.min(start + bucketSize, channel.length)
    let max = 0
    for (let j = start; j < end; j++) {
      const abs = Math.abs(channel[j])
      if (abs > max) max = abs
    }
    peaks.push(max)
  }
  const overallMax = Math.max(...peaks, 0.01)
  const analysis: ClipAudioAnalysis = {
    durationMs: Math.round(audioBuffer.duration * 1000),
    sampleRate: audioBuffer.sampleRate,
    peaks: peaks.map((p) => p / overallMax),
  }
  touchCache(cacheKey, analysis)
  return analysis
}

/** Drops every cached analysis for `assetKey` (all bucket-count variants). */
export function invalidateClipAudioAnalysis(assetKey: string): void {
  for (const key of analysisCache.keys()) {
    if (key === assetKey || key.startsWith(`${assetKey}::`)) analysisCache.delete(key)
  }
}
