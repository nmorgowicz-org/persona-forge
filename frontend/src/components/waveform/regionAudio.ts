import type { StitchPlanRegionEdit } from '@/lib/api'

export type RegionAudio = { channels: Float32Array[]; sampleRate: number }

const sampleAt = (ms: number | undefined, sampleRate: number, max: number) => Math.max(0, Math.min(max, Math.round(((ms ?? 0) / 1000) * sampleRate)))

export function renderRegionEdits(source: RegionAudio, edits: StitchPlanRegionEdit[]): Float32Array[] {
  let channels = source.channels.map((channel) => new Float32Array(channel))
  for (const edit of edits) {
    if (edit.type === 'insert_silence') continue
    const start = sampleAt(edit.startMs, source.sampleRate, channels[0].length)
    const end = sampleAt(edit.endMs, source.sampleRate, channels[0].length)
    if (end <= start || edit.type === 'delete') continue
    for (const channel of channels) for (let i = start; i < end; i++) {
      const pos = i - start
      const length = end - start
      let factor = edit.type === 'mute' ? 0 : edit.type === 'gain' ? Math.pow(10, (edit.gainDb ?? 0) / 20) : 1
      if (edit.type === 'fade') {
        const fadeIn = sampleAt(edit.fadeInMs, source.sampleRate, length)
        const fadeOut = sampleAt(edit.fadeOutMs, source.sampleRate, length)
        if (fadeIn && pos < fadeIn) factor = Math.min(factor, pos / fadeIn)
        if (fadeOut && length - pos < fadeOut) factor = Math.min(factor, (length - pos) / fadeOut)
      }
      channel[i] *= factor
    }
  }
  for (const edit of edits.filter((item) => item.type === 'delete').sort((a, b) => (b.startMs ?? 0) - (a.startMs ?? 0))) {
    const start = sampleAt(edit.startMs, source.sampleRate, channels[0].length)
    const end = sampleAt(edit.endMs, source.sampleRate, channels[0].length)
    if (end <= start) continue
    channels = channels.map((channel) => { const next = new Float32Array(channel.length - (end - start)); next.set(channel.slice(0, start)); next.set(channel.slice(end), start); return next })
  }
  let inserted = 0
  for (const edit of edits.filter((item) => item.type === 'insert_silence').sort((a, b) => (a.atMs ?? 0) - (b.atMs ?? 0))) {
    const at = sampleAt(edit.atMs, source.sampleRate, channels[0].length) + inserted
    const length = sampleAt(edit.durationMs, source.sampleRate, Number.MAX_SAFE_INTEGER)
    channels = channels.map((channel) => { const next = new Float32Array(channel.length + length); next.set(channel.slice(0, at)); next.set(channel.slice(at), at + length); return next })
    inserted += length
  }
  return channels
}

export function encodeRegionWav(channels: Float32Array[], sampleRate: number): Blob {
  const count = channels.length
  const frames = channels[0]?.length ?? 0
  const buffer = new ArrayBuffer(44 + frames * count * 2)
  const view = new DataView(buffer)
  const text = (offset: number, value: string) => { for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i)) }
  text(0, 'RIFF'); view.setUint32(4, 36 + frames * count * 2, true); text(8, 'WAVE'); text(12, 'fmt ')
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, count, true); view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * count * 2, true); view.setUint16(32, count * 2, true); view.setUint16(34, 16, true); text(36, 'data'); view.setUint32(40, frames * count * 2, true)
  let offset = 44
  for (let frame = 0; frame < frames; frame++) for (let channel = 0; channel < count; channel++) { const value = Math.max(-1, Math.min(1, channels[channel][frame])); view.setInt16(offset, value < 0 ? value * 0x8000 : value * 0x7fff, true); offset += 2 }
  return new Blob([buffer], { type: 'audio/wav' })
}
