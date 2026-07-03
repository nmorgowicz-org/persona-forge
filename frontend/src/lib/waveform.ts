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
