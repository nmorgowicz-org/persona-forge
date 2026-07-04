// Thin client for the Flask API in src/qwen3_tts/app.py. No auth — same trust boundary
// as the rest of the service (see SECURITY.md); this UI is meant to run on the same
// trusted network as the container.

export interface GenerateParams {
  text: string
  language?: string
  voiceId?: string | null
  seed?: number | null
  instruct?: string | null
  responseFormat?: 'mp3' | 'wav'
}

export interface VoiceMeta {
  voice_id: string
  description: string
  sample_text: string
  language: string
  seed?: number | null
  selections?: unknown
  created_at: number
  audio_base64?: string
}

export interface GenerateResult {
  blob: Blob
  seed: number | null
}

async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json()
    return body.error ?? `HTTP ${res.status}`
  } catch {
    return `HTTP ${res.status}`
  }
}

export async function generateSpeech(params: GenerateParams): Promise<GenerateResult> {
  const res = await fetch('/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: params.text,
      language: params.language ?? 'English',
      voice_id: params.voiceId ?? undefined,
      seed: params.seed ?? undefined,
      instruct: params.instruct ?? undefined,
      response_format: params.responseFormat ?? 'mp3',
    }),
  })
  if (!res.ok) throw new Error(await readError(res))
  const seedHeader = res.headers.get('X-Seed')
  return { blob: await res.blob(), seed: seedHeader ? Number(seedHeader) : null }
}

export interface VoiceDesignParams {
  description: string
  sampleText: string
  language?: string
  seed?: number | null
  selections?: unknown
}

export interface VoiceDesignPreviewResult {
  preview_id: string
  sample_rate: number
  seed: number
  audio_base64: string
}

export async function createVoiceDesign(params: VoiceDesignParams): Promise<VoiceDesignPreviewResult> {
  const res = await fetch('/voice_design', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      description: params.description,
      sample_text: params.sampleText,
      language: params.language ?? 'English',
      seed: params.seed ?? undefined,
      selections: params.selections ?? undefined,
    }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export interface VoiceDesignSaveResult {
  voice_id: string
}

export async function saveVoiceDesign(previewId: string): Promise<VoiceDesignSaveResult> {
  const res = await fetch(`/voice_design/preview/${encodeURIComponent(previewId)}/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function listVoices(): Promise<VoiceMeta[]> {
  const res = await fetch('/voices')
  if (!res.ok) throw new Error(await readError(res))
  const body = await res.json()
  return body.voices
}

export async function getVoice(voiceId: string): Promise<VoiceMeta> {
  const res = await fetch(`/voices/${encodeURIComponent(voiceId)}`)
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function deleteVoice(voiceId: string): Promise<void> {
  const res = await fetch(`/voices/${encodeURIComponent(voiceId)}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await readError(res))
}

export interface HealthState {
  status: string
  model_loaded: boolean
  swap_in_progress: boolean
  backend: string
  model: string
  loading_message?: string
  [key: string]: unknown
}

export async function getHealth(): Promise<HealthState> {
  const res = await fetch('/health')
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export interface OmniVoiceAuditionParams {
  segments: string[]
  instruct: string
  language?: string
  candidatesPerSegment?: number
  seed?: number | null
  /** Diffusion step count — quality/speed tradeoff. Server clamps to [16, 32]; omit for the
   * model's own default (32). */
  numStep?: number | null
  /** Target clip duration in seconds. Overrides `speed` when both are set (real
   * OmniVoice.generate() behavior). Legacy global; prefer `durations` per-segment now. */
  durationSeconds?: number | null
  /** Playback-rate-style multiplier. Server clamps to [0.5, 2.5]. */
  speed?: number | null
  /** Classifier-free guidance scale for accent/voice fidelity. Server clamps to [1.5, 3.0]. */
  guidanceScale?: number | null
  /** When true, candidates use varied position_temperatures [5, 7, 10] for prosodic diversity. */
  diverseCandidates?: boolean
  /** Per-segment target durations (aligned with segments list); null = auto. */
  durations?: (number | null)[]
  /** When false, disables trailing-silence trimming post-processing. */
  postprocessOutput?: boolean | null
  /** Overrides the ASR match-score acceptance threshold [0-1] for this job; null/omitted
   * uses the server's env-var defaults (word-count-based short/long thresholds). */
  minMatchScore?: number | null
}

export interface OmniVoiceCandidate {
  candidate_id: string
  sample_rate: number
  audio_base64: string
  duration_sec: number | null
  /** True if audio_post.analyze_take's drone/silence heuristic (or the Whisper no-speech
   * gate) flagged this take even after one in-server retry. */
  flagged: boolean
  flag_reason: string | null
  whisper_transcript: string | null
  /** Fuzzy match score between Whisper transcript and the reference text [0–1].
   * Higher is better; null if not computed. */
  match_score: number | null
}

export interface OmniVoiceAuditionResult {
  segments: { text: string; candidates: OmniVoiceCandidate[] }[]
}

export interface OmniVoiceCandidateSegment {
  segment_index: number
  text: string
  candidates: OmniVoiceCandidate[]
}

export interface OmniVoiceStreamingJobResult {
  job_id: string
  total_segments: number
}

export interface OmniVoiceAuditionProgressResult {
  status: 'running' | 'completed' | 'failed'
  job_id: string
  total_segments: number
  current_segment_index: number | null
  segments_completed: OmniVoiceCandidateSegment[]
  message: string | null
  eta?: number | null
  total_candidates?: number
  completed_candidates?: number
  avg_seconds?: number | null
  estimated_remaining_seconds?: number | null
  current_candidate_index?: number | null
}

/**
 * Streaming audition: starts job and returns immediately with job_id.
 * Call getOmniVoiceAuditionProgress(job_id) to poll for incremental results.
 */
export async function auditionOmniVoiceStreaming(
  params: OmniVoiceAuditionParams,
): Promise<OmniVoiceStreamingJobResult> {
  const res = await fetch('/omnivoice/audition', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      segments: params.segments,
      instruct: params.instruct,
      language: params.language ?? 'english',
      candidates_per_segment: params.candidatesPerSegment ?? 3,
      seed: params.seed ?? undefined,
      num_step: params.numStep ?? undefined,
      duration: params.durationSeconds ?? undefined,
      speed: params.speed ?? undefined,
      guidance_scale: params.guidanceScale ?? undefined,
      diverse_candidates: params.diverseCandidates ?? undefined,
      durations: params.durations ?? undefined,
      postprocess_output: params.postprocessOutput ?? undefined,
      min_match_score: params.minMatchScore ?? undefined,
    }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

/**
 * Legacy single-shot audition (still wired to same endpoint; for backward compat).
 */
export async function auditionOmniVoice(
  params: OmniVoiceAuditionParams,
): Promise<OmniVoiceAuditionResult> {
  // Reuses streaming job internally; wait for completion here for backward compatibility.
  const { job_id } = await auditionOmniVoiceStreaming(params)
  const deadline = Date.now() + 1800_000
  let lastSegments: OmniVoiceCandidateSegment[] = []
  while (Date.now() < deadline) {
    const progress = await getOmniVoiceAuditionProgress(job_id)
    if (progress.status === 'completed') {
      lastSegments = progress.segments_completed
      break
    }
    if (progress.status === 'failed') {
      throw new Error(progress.message ?? 'OmniVoice job failed')
    }
    lastSegments = progress.segments_completed
    await new Promise((r) => setTimeout(r, 600))
  }
  if (lastSegments.length === 0 && Date.now() >= deadline) {
    throw new Error('OmniVoice audition timed out')
  }
  const segments = lastSegments.map((s) => ({
    text: s.text,
    candidates: s.candidates,
  }))
  return { segments }
}

export async function getOmniVoiceAuditionProgress(
  jobId: string,
): Promise<OmniVoiceAuditionProgressResult> {
  const res = await fetch(`/omnivoice/audition/progress?job_id=${encodeURIComponent(jobId)}`)
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export interface OmniVoiceProgress {
  phase: 'idle' | 'loading' | 'generating'
  total: number
  completed: number
  current_segment_index: number
  current_candidate_index: number
  segment_count: number
  candidates_per_segment: number
  avg_seconds: number | null
  estimated_remaining_seconds: number | null
}

export async function getOmniVoiceProgress(): Promise<OmniVoiceProgress> {
  const res = await fetch('/omnivoice/progress')
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export interface VoiceDesignProgress {
  phase: 'idle' | 'loading' | 'generating'
  avg_seconds: number | null
  estimated_remaining_seconds: number | null
}

export async function getVoiceDesignProgress(): Promise<VoiceDesignProgress> {
  const res = await fetch('/voice_design/progress')
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export interface OmniVoiceStitchParams {
  segmentIds?: string[]
  selections?: string[]
}

export async function stitchOmniVoice(params: OmniVoiceStitchParams | string[]): Promise<Blob> {
  // Accepts the legacy bare-array form (candidate_id selections) or the newer
  // {segmentIds | selections} form so callers can stitch from the persistent library.
  const body = Array.isArray(params)
    ? { selections: params }
    : {
        segment_ids: params.segmentIds ?? undefined,
        selections: params.selections ?? undefined,
      }
  const res = await fetch('/omnivoice/stitch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.blob()
}

export interface OmniVoiceSaveParams {
  selections?: string[]
  segmentIds?: string[]
  instruct: string
  segments: string[]
  language?: string
  accentId?: string | null
}

export interface OmniVoiceSaveResult {
  voice_id: string
  sample_rate: number
  audio_base64: string
}

export async function saveOmniVoice(params: OmniVoiceSaveParams): Promise<OmniVoiceSaveResult> {
  const res = await fetch('/omnivoice/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      selections: params.selections ?? undefined,
      segment_ids: params.segmentIds ?? undefined,
      instruct: params.instruct,
      segments: params.segments,
      language: params.language ?? 'english',
      accent_id: params.accentId ?? undefined,
    }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export interface SegmentMeta {
  segment_id: string
  text: string
  instruct: string
  tags: string[]
  engine: string
  accent_id: string | null
  sample_rate: number
  created_at: number
  audio_base64?: string
}

export async function lockInOmniVoiceSegment(params: {
  candidateId: string
  text: string
  instruct: string
  accentId?: string | null
}): Promise<SegmentMeta> {
  const res = await fetch('/omnivoice/segments', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      candidate_id: params.candidateId,
      text: params.text,
      instruct: params.instruct,
      accent_id: params.accentId ?? undefined,
    }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function listOmniVoiceSegments(): Promise<SegmentMeta[]> {
  const res = await fetch('/omnivoice/segments')
  if (!res.ok) throw new Error(await readError(res))
  const body = await res.json()
  return body.segments
}

export async function deleteOmniVoiceSegment(segmentId: string): Promise<void> {
  const res = await fetch(`/omnivoice/segments/${encodeURIComponent(segmentId)}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(await readError(res))
}

export interface RuntimeConfigState {
  reconfig_in_progress: boolean
  live: {
    TTS_BACKEND: string
    IDLE_UNLOAD_SECONDS: number
    SILENCE_TRIM: boolean
    SILENCE_TRIM_THRESH: number
    SILENCE_TRIM_PAD_MS: number
    OV_DYNAMIC_QUANT_GROUP_SIZE: number
  }
  read_only: {
    mounts: Record<string, 'ro' | 'rw' | null>
    ref_audio_path_set: boolean
    hf_token_set: boolean
    device: string
    torch_dtype: string
  }
  not_live: {
    TTS_MAX_SPEECH_SECONDS: string | null
    MODEL_SIZE: string | null
    compression: string | null
    reason: string
  }
}

export async function getRuntimeConfig(): Promise<RuntimeConfigState> {
  const res = await fetch('/runtime/config')
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function updateRuntimeConfig(
  updates: Partial<RuntimeConfigState['live']>,
): Promise<RuntimeConfigState> {
  const res = await fetch('/runtime/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}
