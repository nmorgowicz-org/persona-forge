// Shared "insert a library item into the stitch timeline" logic, used by the quick-insert
// modal (App.tsx QuickInsertStitchEditor) and the standalone Stitch Studio page
// (StitchStudioPage.tsx); VoiceLibraryPage.tsx builds an incoming clip directly.
import type { StitchPlanClip } from '@/store'
import { getSegmentAudioBase64, getVoice, type SegmentMeta, type VoiceMeta } from '@/lib/api'
import { getClipAudioAnalysis } from '@/lib/waveform'
import type { StitchPlanSession } from '@/hooks/useStitchPlanSession'

// Delegates to the session's atomic `insertClips`, which splices `clips` into the plan and
// resizes `paddingMs` in a single state write (afterClipId null/omitted appends at the end).
// Resolving the seam index inside that write is what keeps a multi-item batch from racing
// itself or stomping on a concurrent clip/padding edit made while the batch's fetches and
// decodes are in flight.
function spliceStitchPlanClips(clips: StitchPlanClip[], session: StitchPlanSession, afterClipId?: string | null) {
  if (clips.length === 0) return
  session.insertClips(clips, afterClipId)
}

// Runs `fn` over `items` with at most `limit` in flight, preserving input order in the
// result. A batch insert must not fire N parallel audio fetches and N concurrent Web Audio
// decodes at once: the 64-entry analysis LRU caches results but does not cap in-flight work.
const INSERT_BATCH_CONCURRENCY = 3

async function mapInsertBatch<T, U>(items: T[], fn: (item: T) => Promise<U>): Promise<U[]> {
  const results = new Array<U>(items.length)
  let next = 0
  const worker = async () => {
    while (true) {
      const index = next++
      if (index >= items.length) return
      results[index] = await fn(items[index])
    }
  }
  const workerCount = Math.min(INSERT_BATCH_CONCURRENCY, items.length)
  await Promise.all(Array.from({ length: workerCount }, () => worker()))
  return results
}

// Public shared helpers — used by:
// - App.tsx (QuickInsertStitchEditor, via insertSegmentsIntoStitchTimeline / insertVoicesIntoStitchTimeline)
// - StitchStudioPage.tsx (same insert helpers, plus suggestedStitchVoiceName)
// - VoiceLibraryPage.tsx (createStitchClipFromSegment directly, to build the incoming clip)
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
    clipId: seg.segment_id + '-insert-' + Date.now() + '-' + crypto.randomUUID().slice(0, 8),
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
    clipId: voice.voice_id + '-insert-' + Date.now() + '-' + crypto.randomUUID().slice(0, 8),
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
    const clips = await mapInsertBatch(segs, (seg) => createStitchClipFromSegment(seg))
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
    const clips = await mapInsertBatch(voices, (voice) => createStitchClipFromVoice(voice))
    spliceStitchPlanClips(clips, session, afterClipId)
  } catch (err) {
    onError(err instanceof Error ? err.message : String(err))
  }
}
