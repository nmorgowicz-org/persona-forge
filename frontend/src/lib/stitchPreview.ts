// Client-side stitch-preview rendering: turns a durable StitchPlanState into an audio Blob,
// either by asking the server (no region edits, no manual-prosody-repair clips) or by
// mixing it locally in WebAudio (region edits present). Moved out of StitchTimeline.tsx per
// docs/plans/20260920-stitch_studio_ux_execution_plan.md Packet 2, so frontend/src/hooks/
// useStitchPreview.ts can own the render lifecycle without importing component code.
import { base64ToBlob } from '@/lib/utils'
import { renderStitchPlan, type StitchPlanPayload } from '@/lib/api'
import { toPayloadRegionEdits, type StitchPlanState, type StitchRegionEdit, type StitchRegionEditsByClip } from '@/lib/stitchPlan'
import type { StitchPlanClip } from '@/store'
import { renderRegionEdits } from '@/components/waveform/regionAudio'

function hasRegionEdits(editsByClip: StitchRegionEditsByClip): boolean {
  return Object.values(editsByClip).some((edits) => edits.length > 0)
}

function msToSample(ms: number, sampleRate: number): number {
  return Math.max(0, Math.round((ms / 1000) * sampleRate))
}

function cloneChannels(buffer: AudioBuffer): Float32Array[] {
  return Array.from({ length: buffer.numberOfChannels }, (_, channel) => new Float32Array(buffer.getChannelData(channel)))
}

function sliceChannels(channels: Float32Array[], start: number, end: number): Float32Array[] {
  return channels.map((channel) => channel.slice(start, end))
}

function applyClipFade(channels: Float32Array[], sampleRate: number, fadeInMs: number, fadeOutMs: number) {
  const length = channels[0]?.length ?? 0
  if (!length) return
  const fadeIn = Math.min(length, msToSample(fadeInMs, sampleRate))
  const fadeOut = Math.min(length, msToSample(fadeOutMs, sampleRate))
  for (const channel of channels) {
    for (let i = 0; i < fadeIn; i++) channel[i] *= i / Math.max(1, fadeIn)
    for (let i = 0; i < fadeOut; i++) {
      const idx = length - 1 - i
      channel[idx] *= i / Math.max(1, fadeOut)
    }
  }
}

export async function decodeClipAudio(ctx: AudioContext, clip: StitchPlanClip): Promise<AudioBuffer> {
  const blob = base64ToBlob(clip.sourceAudioBase64)
  const arrayBuffer = await blob.arrayBuffer()
  return ctx.decodeAudioData(arrayBuffer.slice(0))
}

export function processClipAudio(buffer: AudioBuffer, clip: StitchPlanClip, edits: StitchRegionEdit[]): Float32Array[] {
  const sampleRate = buffer.sampleRate
  const start = msToSample(clip.trimStartMs, sampleRate)
  const end = Math.max(start + 1, buffer.length - msToSample(clip.trimEndMs, sampleRate))
  let channels = sliceChannels(cloneChannels(buffer), start, Math.min(end, buffer.length))

  channels = renderRegionEdits({ channels, sampleRate }, edits)

  applyClipFade(channels, sampleRate, clip.fadeInMs, clip.fadeOutMs)
  return channels
}

export function appendWithGapAndCrossfade(
  output: Float32Array[],
  clip: Float32Array[],
  sampleRate: number,
  gapMs: number,
  crossfadeMs: number,
): Float32Array[] {
  if (!output.length) return clip
  const channels = Math.max(output.length, clip.length)
  const gap = msToSample(gapMs, sampleRate)
  const fade = gap > 0 ? 0 : Math.min(msToSample(crossfadeMs, sampleRate), output[0].length, clip[0].length)
  return Array.from({ length: channels }, (_, channelIndex) => {
    const prev = output[channelIndex] ?? output[0]
    const next = clip[channelIndex] ?? clip[0]
    const length = prev.length + gap + next.length - fade
    const merged = new Float32Array(length)
    merged.set(prev, 0)
    if (fade > 0) {
      const start = prev.length - fade
      for (let i = 0; i < fade; i++) {
        const a = 1 - i / fade
        const b = i / fade
        merged[start + i] = prev[start + i] * a + next[i] * b
      }
      merged.set(next.slice(fade), prev.length + gap)
    } else {
      merged.set(next, prev.length + gap)
    }
    return merged
  })
}

export function encodeWav(channels: Float32Array[], sampleRate: number): Blob {
  const channelCount = channels.length
  const frameCount = channels[0]?.length ?? 0
  const bytesPerSample = 2
  const dataSize = frameCount * channelCount * bytesPerSample
  const buffer = new ArrayBuffer(44 + dataSize)
  const view = new DataView(buffer)
  const writeString = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i))
  }
  writeString(0, 'RIFF')
  view.setUint32(4, 36 + dataSize, true)
  writeString(8, 'WAVE')
  writeString(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, channelCount, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * channelCount * bytesPerSample, true)
  view.setUint16(32, channelCount * bytesPerSample, true)
  view.setUint16(34, bytesPerSample * 8, true)
  writeString(36, 'data')
  view.setUint32(40, dataSize, true)
  let offset = 44
  for (let i = 0; i < frameCount; i++) {
    for (let channel = 0; channel < channelCount; channel++) {
      const sample = Math.max(-1, Math.min(1, channels[channel][i]))
      view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
      offset += bytesPerSample
    }
  }
  return new Blob([buffer], { type: 'audio/wav' })
}

export async function renderEditedStitchPreview(
  clips: StitchPlanClip[],
  paddingMs: number[],
  crossfadeMs: number,
  editsByClip: StitchRegionEditsByClip,
): Promise<Blob> {
  // SAFETY: Safari exposes AudioContext only under the vendor-prefixed global; feature-detected below.
  const webkitCtor = (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  const AudioContextCtor = window.AudioContext ?? webkitCtor
  if (!AudioContextCtor) throw new Error('Browser audio rendering is unavailable.')
  const ctx = new AudioContextCtor()
  try {
    let sampleRate = 24000
    let output: Float32Array[] = []
    for (let i = 0; i < clips.length; i++) {
      const clip = clips[i]
      if (!clip.sourceAudioBase64) throw new Error('Region preview needs source audio for every clip.')
      const buffer = await decodeClipAudio(ctx, clip)
      sampleRate = buffer.sampleRate
      const processed = processClipAudio(buffer, clip, editsByClip[clip.clipId] ?? [])
      output = appendWithGapAndCrossfade(output, processed, sampleRate, i > 0 ? paddingMs[i - 1] || 0 : 0, i > 0 ? crossfadeMs : 0)
    }
    return encodeWav(output, sampleRate)
  } finally {
    await ctx.close()
  }
}

/** Converts a durable plan into the wire payload shape `renderStitchPlan` expects. */
export function planStateToPayload(plan: StitchPlanState): StitchPlanPayload {
  const { clips, paddingMs, dsp, regionEditsByClip } = plan
  return {
    clips: clips.map((c) => {
      const anyRef = c.ref as Record<string, string>
      const edits = regionEditsByClip[c.clipId] ?? []
      return {
        segmentId: 'segmentId' in anyRef ? anyRef.segmentId : undefined,
        candidateId: 'candidateId' in anyRef ? anyRef.candidateId : undefined,
        voiceId: 'voiceId' in anyRef ? anyRef.voiceId : undefined,
        trimStartMs: c.trimStartMs,
        trimEndMs: c.trimEndMs,
        fadeInMs: c.fadeInMs,
        fadeOutMs: c.fadeOutMs,
        text: c.text,
        prosodyMode: c.prosodyMode ?? 'auto',
        edits: edits.length ? toPayloadRegionEdits(edits) : undefined,
      }
    }),
    paddingMs: paddingMs.length ? paddingMs : new Array(Math.max(0, clips.length - 1)).fill(0),
    crossfadeMs: dsp.crossfadeMs,
    segmentTargetDbfs: dsp.segmentTargetDbfs,
    finalTargetDbfs: dsp.finalTargetDbfs,
    finalCeilingDb: dsp.finalCeilingDb,
    compress: dsp.compressEnabled
      ? {
          thresholdDb: dsp.compressThresholdDb,
          ratio: dsp.compressRatio,
          attackMs: 5,
          releaseMs: 80,
        }
      : null,
    stylePreset: dsp.prosodyStylePreset,
    paceMultiplier: dsp.paceMultiplier,
    pauseOffsetMs: dsp.pauseOffsetMs,
  }
}

/** Renders one preview for `plan`: server-side for the common case, or a local WebAudio mix
 * when region edits are present and no clip needs server-side prosody repair (region edits
 * are rendered against the clip's raw source audio, which server-side repair would re-derive
 * from scratch). `signal` aborts the in-flight server request; the local WebAudio path has no
 * cancellable primitive, so callers must discard a stale result themselves (see
 * frontend/src/hooks/useStitchPreview.ts's sequence guard). */
export async function renderStitchPreview(plan: StitchPlanState, signal?: AbortSignal): Promise<Blob> {
  const payload = planStateToPayload(plan)
  const requiresServerRepair = plan.clips.some((clip) => (clip.prosodyMode ?? 'auto') !== 'off')
  if (hasRegionEdits(plan.regionEditsByClip) && !requiresServerRepair) {
    return renderEditedStitchPreview(plan.clips, payload.paddingMs, plan.dsp.crossfadeMs, plan.regionEditsByClip)
  }
  return renderStitchPlan(payload, signal)
}
