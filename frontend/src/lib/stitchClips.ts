// Shared "insert a library item into the stitch timeline" logic, used by both
// OmniVoicePanel's stitch editor entry point and the standalone Stitch Studio page.
import type { StitchPlanClip } from '@/store'
import { getSegmentAudioBase64, getVoice, type SegmentMeta, type VoiceMeta } from '@/lib/api'
import { getClipAudioAnalysis } from '@/lib/waveform'
import type { StitchPlanSession } from '@/hooks/useStitchPlanSession'

// Splices `clips` into the session's plan as one atomic clips+padding update -- appending at
// the end (afterClipId null/omitted) or inserting immediately after a specific existing clip.
// Takes a single snapshot of the pre-insert plan, so a multi-item batch (e.g. "Insert
// selected" with several checked rows) can never race itself the way calling this once per
// item against a stale snapshot would (each item would independently recompute the same
// pre-batch clip/padding counts and stomp on each other's padding-array writes).
function spliceStitchPlanClips(clips: StitchPlanClip[], session: StitchPlanSession, afterClipId?: string | null) {
  if (clips.length === 0) return
  const clipsBefore = session.plan.clips
  const paddingBefore = session.plan.paddingMs
  const afterIndex = afterClipId ? clipsBefore.findIndex((c) => c.clipId === afterClipId) : -1
  const insertAt = afterIndex === -1 ? clipsBefore.length : afterIndex + 1

  session.setClips((prev) => {
    const next = [...prev]
    next.splice(insertAt, 0, ...clips)
    return next
  })

  if (clipsBefore.length === 0) {
    session.setPadding(new Array(Math.max(0, clips.length - 1)).fill(0))
    return
  }
  const splitAt = Math.max(0, insertAt - 1)
  const zeros = new Array(clips.length).fill(0)
  session.setPadding([...paddingBefore.slice(0, splitAt), ...zeros, ...paddingBefore.slice(splitAt)])
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

export async function insertSegmentsIntoStitchTimeline(
  segs: SegmentMeta[],
  session: StitchPlanSession,
  onError: (msg: string) => void,
  afterClipId?: string | null,
): Promise<void> {
  try {
    const clips = await Promise.all(segs.map((seg) => createStitchClipFromSegment(seg)))
    spliceStitchPlanClips(clips, session, afterClipId)
  } catch (err) {
    onError(err instanceof Error ? err.message : String(err))
  }
}

export async function insertVoicesIntoStitchTimeline(
  voices: VoiceMeta[],
  session: StitchPlanSession,
  onError: (msg: string) => void,
  afterClipId?: string | null,
): Promise<void> {
  try {
    const clips = await Promise.all(voices.map((voice) => createStitchClipFromVoice(voice)))
    spliceStitchPlanClips(clips, session, afterClipId)
  } catch (err) {
    onError(err instanceof Error ? err.message : String(err))
  }
}
