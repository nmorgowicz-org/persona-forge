// Shared "insert a library item into the stitch timeline" logic, used by both
// OmniVoicePanel's stitch editor entry point and the standalone Stitch Studio page.
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

// Public shared helpers — used by:
// - OmniVoicePanel (via insertSegmentIntoStitchTimeline / insertVoiceIntoStitchTimeline)
// - VoiceLibraryPage (directly, plus page nav and editor open)
export async function createStitchClipFromSegment(seg: SegmentMeta): Promise<StitchPlanClip> {
  let audioBase64 = seg.audio_base64
  if (!audioBase64) {
    try {
      audioBase64 = await getSegmentAudioBase64(seg.segment_id)
    } catch {
      throw new Error('No audio available for this segment')
    }
  }
  const durationMs = await decodeAudioDurationMs(audioBase64)

  return {
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
  }
}

export async function createStitchClipFromVoice(voice: VoiceMeta): Promise<StitchPlanClip> {
  let audioBase64 = voice.audio_base64
  if (!audioBase64) {
    try {
      const full = await getVoice(voice.voice_id)
      audioBase64 = full.audio_base64
    } catch {
      throw new Error('No audio available for this voice')
    }
  }
  if (!audioBase64) {
    throw new Error('No audio available for this voice')
  }

  const durationMs = await decodeAudioDurationMs(audioBase64)

  return {
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
  }
}

export async function insertSegmentIntoStitchTimeline(
  seg: SegmentMeta,
  onError: (msg: string) => void,
): Promise<void> {
  try {
    const clip = await createStitchClipFromSegment(seg)
    appendStitchPlanClip(clip)
  } catch (err) {
    onError(err instanceof Error ? err.message : String(err))
  }
}

export async function insertVoiceIntoStitchTimeline(
  voice: VoiceMeta,
  onError: (msg: string) => void,
): Promise<void> {
  try {
    const clip = await createStitchClipFromVoice(voice)
    appendStitchPlanClip(clip)
  } catch (err) {
    onError(err instanceof Error ? err.message : String(err))
  }
}
