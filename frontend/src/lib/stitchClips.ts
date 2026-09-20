// Shared "insert a library item into the stitch timeline" logic, used by both
// OmniVoicePanel's stitch editor entry point and the standalone Stitch Studio page.
import type { StitchPlanClip } from '@/store'
import { getSegmentAudioBase64, getVoice, type SegmentMeta, type VoiceMeta } from '@/lib/api'
import { getClipAudioAnalysis } from '@/lib/waveform'
import type { StitchPlanSession } from '@/hooks/useStitchPlanSession'

// Appends to whichever session is active (the store-backed Studio session or a quick-insert
// draft) -- callers never write to zustand directly, so a quick-insert draft can never leak
// into the live plan before it is explicitly committed.
function appendStitchPlanClip(clip: StitchPlanClip, session: StitchPlanSession) {
  const clipCountBefore = session.plan.clips.length
  const paddingLenBefore = session.plan.paddingMs.length
  session.setClips((prev) => [...prev, clip])
  for (let i = paddingLenBefore; i < clipCountBefore; i++) {
    session.setPaddingAt(i, 0)
  }
}

// Public shared helpers — used by:
// - OmniVoicePanel (via insertSegmentIntoStitchTimeline / insertVoiceIntoStitchTimeline)
// - VoiceLibraryPage (directly, plus page nav and editor open)
export function suggestedStitchVoiceName(clip: StitchPlanClip): string {
  const source = [clip.sourceProject, clip.sourceLabel].filter(Boolean).join(' — ')
  return [source || clip.text.trim(), clip.sourceOrigin].filter(Boolean).join(' · ') || 'Stitched voice'
}

export async function createStitchClipFromSegment(seg: SegmentMeta): Promise<StitchPlanClip> {
  let audioBase64 = seg.audio_base64
  if (!audioBase64) {
    try {
      audioBase64 = await getSegmentAudioBase64(seg.segment_id)
    } catch {
      throw new Error('No audio available for this segment')
    }
  }
  const durationMs = (await getClipAudioAnalysis(`segment:${seg.segment_id}:${audioBase64.length}`, audioBase64)).durationMs

  return {
    clipId: seg.segment_id + '-insert-' + Date.now(),
    ref: { segmentId: seg.segment_id },
    text: seg.text,
    sourceAudioBase64: audioBase64,
    sampleRate: seg.sample_rate,
    sourceLabel: seg.text,
    sourceProject: seg.project_name ?? null,
    sourceOrigin: seg.engine || seg.instruct || null,
    trimStartMs: 0,
    trimEndMs: 0,
    fadeInMs: 0,
    fadeOutMs: 0,
    prosodyMode: 'auto',
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

  const durationMs = (await getClipAudioAnalysis(`voice:${voice.voice_id}:${voice.sha256 ?? audioBase64.length}`, audioBase64)).durationMs

  return {
    clipId: voice.voice_id + '-insert-' + Date.now(),
    ref: { voiceId: voice.voice_id },
    text: voice.description || voice.sample_text || voice.voice_id,
    sourceAudioBase64: audioBase64,
    sourceLabel: voice.display_name || voice.description || voice.sample_text || voice.voice_id,
    sourceProject: voice.project_name ?? null,
    sourceOrigin: voice.source || 'Voice library',
    // Not returned by the voice-library list/get endpoints; harmless placeholder since
    // the backend resolves clip audio server-side and this field is otherwise unused.
    sampleRate: 24000,
    trimStartMs: 0,
    trimEndMs: 0,
    fadeInMs: 0,
    fadeOutMs: 0,
    prosodyMode: 'auto',
    durationMs,
  }
}

export async function insertSegmentIntoStitchTimeline(
  seg: SegmentMeta,
  session: StitchPlanSession,
  onError: (msg: string) => void,
): Promise<void> {
  try {
    const clip = await createStitchClipFromSegment(seg)
    appendStitchPlanClip(clip, session)
  } catch (err) {
    onError(err instanceof Error ? err.message : String(err))
  }
}

export async function insertVoiceIntoStitchTimeline(
  voice: VoiceMeta,
  session: StitchPlanSession,
  onError: (msg: string) => void,
): Promise<void> {
  try {
    const clip = await createStitchClipFromVoice(voice)
    appendStitchPlanClip(clip, session)
  } catch (err) {
    onError(err instanceof Error ? err.message : String(err))
  }
}
