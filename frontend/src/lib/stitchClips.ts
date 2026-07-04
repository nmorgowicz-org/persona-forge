// Shared "insert a library item into the stitch timeline" logic, used by both
// PersonaForgePanel's stitch editor entry point and the standalone Stitch Studio page.
import { useAppStore, type StitchPlanClip } from '@/store'
import { getSegmentAudioBase64, getVoice, type SegmentMeta, type VoiceMeta } from '@/lib/api'

async function decodeAudioDurationMs(audioBase64: string): Promise<number> {
  if (typeof window === 'undefined' || !window.AudioContext) return 0
  const ctx = new AudioContext()
  try {
    const byteStr = atob(audioBase64)
    const bytes = new Uint8Array(byteStr.length)
    for (let i = 0; i < byteStr.length; i++) bytes[i] = byteStr.charCodeAt(i)
    const audioBuffer = await ctx.decodeAudioData(bytes.buffer.slice(0) as ArrayBuffer)
    return Math.round(audioBuffer.duration * 1000)
  } catch {
    return 0
  } finally {
    await ctx.close()
  }
}

function appendStitchPlanClip(clip: StitchPlanClip) {
  const { setOvStitchPlanClips, setOvStitchPlanPaddingAt } = useAppStore.getState()
  setOvStitchPlanClips((prev) => {
    const next = [...prev, clip]
    const needed = Math.max(0, next.length - 1)
    const current = useAppStore.getState().ovStitchPlanPaddingMs || []
    for (let i = current.length; i < needed; i++) {
      setOvStitchPlanPaddingAt(i, 0)
    }
    return next
  })
}

export async function insertSegmentIntoStitchTimeline(
  seg: SegmentMeta,
  onError: (msg: string) => void,
): Promise<void> {
  let audioBase64 = seg.audio_base64
  if (!audioBase64) {
    try {
      audioBase64 = await getSegmentAudioBase64(seg.segment_id)
    } catch {
      onError('No audio available for this segment')
      return
    }
  }
  const durationMs = await decodeAudioDurationMs(audioBase64)
  appendStitchPlanClip({
    clipId: seg.segment_id + '-insert-' + Date.now(),
    ref: { segmentId: seg.segment_id },
    text: seg.text,
    sourceAudioBase64: audioBase64,
    sampleRate: seg.sample_rate,
    trimStartMs: 0,
    trimEndMs: 0,
    fadeInMs: 0,
    fadeOutMs: 0,
    durationMs,
  })
}

export async function insertVoiceIntoStitchTimeline(
  voice: VoiceMeta,
  onError: (msg: string) => void,
): Promise<void> {
  let audioBase64 = voice.audio_base64
  if (!audioBase64) {
    try {
      const full = await getVoice(voice.voice_id)
      audioBase64 = full.audio_base64
    } catch {
      onError('No audio available for this voice')
      return
    }
  }
  if (!audioBase64) {
    onError('No audio available for this voice')
    return
  }
  const durationMs = await decodeAudioDurationMs(audioBase64)
  appendStitchPlanClip({
    clipId: voice.voice_id + '-insert-' + Date.now(),
    ref: { voiceId: voice.voice_id },
    text: voice.description || voice.sample_text || voice.voice_id,
    sourceAudioBase64: audioBase64,
    // Not returned by the voice-library list/get endpoints; harmless placeholder since
    // the backend resolves clip audio server-side and this field is otherwise unused.
    sampleRate: 24000,
    trimStartMs: 0,
    trimEndMs: 0,
    fadeInMs: 0,
    fadeOutMs: 0,
    durationMs,
  })
}
