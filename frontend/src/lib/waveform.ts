// Decodes an audio Blob into a fixed number of peak amplitudes for waveform rendering.
let sharedContext: AudioContext | null = null

function getAudioContext(): AudioContext {
  if (!sharedContext) sharedContext = new AudioContext()
  return sharedContext
}

export async function computePeaks(blob: Blob, buckets = 64): Promise<number[]> {
  const arrayBuffer = await blob.arrayBuffer()
  const ctx = getAudioContext()
  const audioBuffer = await ctx.decodeAudioData(arrayBuffer.slice(0))
  const channel = audioBuffer.getChannelData(0)
  const bucketSize = Math.max(1, Math.floor(channel.length / buckets))
  const peaks: number[] = []
  for (let i = 0; i < buckets; i++) {
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
