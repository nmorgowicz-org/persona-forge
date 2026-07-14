// Thin client for the Flask API in src/qwen3_tts/app.py. No auth — same trust boundary
// as the rest of the service (see SECURITY.md); this UI is meant to run on the same
// trusted network as the container.

import type { AccentFeature } from './accentBank'

export function classifyGenerateError(
  message: string | null,
  status: number | null,
): {
  type:
    | 'TOO_LONG'
    | 'TIMEOUT'
    | 'NOT_READY'
    | 'BUSY_SWAP'
    | 'SERVER_BUSY'
    | 'SERVER_ERROR'
    | 'UNKNOWN'
  headline: string
  detail: string
} {
  const m = (message || '').toLowerCase()

  if (
    status === 422 ||
    m.includes('capacity exceeded') ||
    m.includes('exceeded its allowed')
  ) {
    return {
      type: 'TOO_LONG',
      headline: 'Generation was cut off: it ran longer than allowed.',
      detail:
        'This often means the reference text does not match the audio, or your text is too long.',
    }
  }

  if (m.includes('timed out') || m.includes('timeout') || status === 504) {
    return {
      type: 'TIMEOUT',
      headline: 'Generation timed out.',
      detail: 'Try shorter text or try again in a moment.',
    }
  }

  if (m.includes('not loaded') || m.includes('not ready')) {
    return {
      type: 'NOT_READY',
      headline: 'Model is not ready yet.',
      detail: "It's starting up or reloading — try again shortly.",
    }
  }

  if (m.includes('in progress') || m.includes('already')) {
    return {
      type: 'BUSY_SWAP',
      headline: 'Another task is in progress.',
      detail:
        'The model is switching tasks — generation is temporarily unavailable.',
    }
  }

  if (status === 503) {
    return {
      type: 'SERVER_BUSY',
      headline: 'Server is busy.',
      detail: 'Try again in a moment.',
    }
  }

  if (status && status >= 500) {
    return {
      type: 'SERVER_ERROR',
      headline: 'Something went wrong.',
      detail:
        'The server encountered an error. Try again; if it persists, contact your admin.',
    }
  }

  return {
    type: 'UNKNOWN',
    headline: 'Generation failed.',
    detail: 'An unexpected error occurred. Try again or shorten your text.',
  }
}

export interface GenerateParams {
  text: string
  language?: string
  voiceId?: string | null
  builtinVoice?: string | null
  seed?: number | null
  instruct?: string | null
  stylePreset?: string | null
  postprocess?: boolean | Record<string, unknown> | null
  prosodyRepair?: boolean
  responseFormat?: 'mp3' | 'wav'
}

export type ProsodyRepairOutcome =
  | 'not_requested'
  | 'pending'
  | 'repaired'
  | 'unnecessary'
  | 'failed'
  | 'budget_fallback'

export interface ProsodyRepairMetadata {
  requested: boolean
  outcome: ProsodyRepairOutcome
  budget_seconds?: number | null
  duration_seconds?: number | null
  boundary_count?: number
  resolved_mode?: string | null
  fallback?: string | null
  error?: string
}

export interface VoiceMeta {
  voice_id: string
  family_id?: string
  display_name?: string
  variant_name?: string
  variant_kind?: string
  description: string
  sample_text: string
  language: string
  seed?: number | null
  selections?: unknown
  created_at: number
  audio_base64?: string
  source?: string
  sha256?: string
  sample_text_source?: 'env' | 'whisper' | 'user' | 'none' | 'unset' | string
  needs_review?: boolean
  is_default?: boolean
  quality_score?: number
  quality_warnings?: string[]
  auto_fixed?: boolean
  // True when this voice is the runtime default the OpenAI endpoint clones from (pocket_tts only).
  api_active?: boolean
  undo_available?: boolean
  // True when original.wav is a symlink resolving outside the voice library tree (e.g. a
  // container bind-mount) — in-place edits are blocked server-side and should be routed
  // through "edit on a copy" instead.
  mounted_reference?: boolean
  // Accent Design Project this voice is grouped under (§4) — null/absent means "Ungrouped".
  project_id?: string | null
  project_name?: string | null
  asr?: {
    ok?: boolean
    severity?: 'ok' | 'warn' | 'fail' | 'no_speech' | 'error' | string
    match_score?: number | null
    whisper_transcript?: string | null
    avg_logprob?: number | null
    suggestion?: string | null
  }
}

export interface BuiltInVoiceMeta {
  voice_id: string
  builtin_voice: string
  backend: 'pocket_tts'
  display_name: string
  source: string
  license: string
  language: string
  language_code: string
  category: 'conversation' | 'reading' | 'multilingual' | 'other' | string
  note: string
  prompt: string
  requires_backend: 'pocket_tts'
}

export interface GenerateResult {
  blob: Blob
  seed: number | null
  prosodyRepair?: ProsodyRepairMetadata
}

export interface AsyncJobIdResult {
  job_id: string
  prosody_repair?: ProsodyRepairMetadata
}

export interface GenerateJobProgress {
  job_id: string
  status: 'running' | 'completed' | 'failed' | 'cancelled'
  frames_generated: number
  expected_total_frames: number
  progress_pct: number
  elapsed_seconds: number
  audio_seconds_generated: number
  audio_seconds?: number
  live_rtf_estimate: number | null
  rtf?: number | null
  eta_seconds: number | null
  message: string | null
  voice_family_id?: string | null
  variant_kind?: string | null
  style_preset?: string | null
  postprocess_applied?: boolean
  applied_steps?: string[] | null
  audio_available?: boolean
  prosody_repair?: ProsodyRepairMetadata
}

async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json()
    return body.error ?? `HTTP ${res.status}`
  } catch {
    return `HTTP ${res.status}`
  }
}

function builtinVoiceFromParams(params: GenerateParams): string | undefined {
  if (params.builtinVoice) return params.builtinVoice.replace(/^pocket:/, '')
  if (params.voiceId?.startsWith('pocket:')) return params.voiceId.slice('pocket:'.length)
  return undefined
}

function prosodyRepairFromHeaders(res: Response): ProsodyRepairMetadata | undefined {
  const outcome = res.headers.get('X-Prosody-Repair-Outcome') as ProsodyRepairOutcome | null
  if (!outcome) return undefined
  const numberHeader = (name: string): number | null => {
    const value = res.headers.get(name)
    return value === null ? null : Number(value)
  }
  return {
    requested: outcome !== 'not_requested',
    outcome,
    budget_seconds: numberHeader('X-Prosody-Repair-Budget-Seconds'),
    duration_seconds: numberHeader('X-Prosody-Repair-Duration-Seconds'),
    boundary_count: numberHeader('X-Prosody-Repair-Boundaries') ?? 0,
  }
}

export async function generateSpeech(params: GenerateParams): Promise<GenerateResult> {
  const res = await fetch('/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: params.text,
      language: params.language ?? 'English',
      voice_id: params.voiceId?.startsWith('pocket:') ? undefined : params.voiceId ?? undefined,
      builtin_voice: builtinVoiceFromParams(params),
      seed: params.seed ?? undefined,
      instruct: params.instruct ?? undefined,
      style_preset: params.stylePreset ?? undefined,
      postprocess: params.postprocess ?? undefined,
      prosody_repair: params.prosodyRepair ?? undefined,
      response_format: params.responseFormat ?? 'mp3',
    }),
  })
  if (!res.ok) throw new Error(await readError(res))
  const seedHeader = res.headers.get('X-Seed')
  return {
    blob: await res.blob(),
    seed: seedHeader ? Number(seedHeader) : null,
    prosodyRepair: prosodyRepairFromHeaders(res),
  }
}

export interface ReferenceMetrics {
  duration_seconds?: number
  sample_rate?: number
  lufs_integrated?: number | null
  rms_dbfs?: number
  peak_dbfs?: number
  true_peak_dbtp?: number | null
  speech_rate_proxy?: number
  pause_count?: number
  pause_total_seconds?: number
  pause_ratio?: number
  median_pause_ms?: number
  longest_pause_ms?: number
  pause_intervals?: [number, number][]
  error?: string
}

export interface GenerateWithMetricsResult {
  blob: Blob
  seed: number | null
  metrics: ReferenceMetrics
  prosodyRepair?: ProsodyRepairMetadata
}

export async function generateSpeechWithMetrics(
  params: GenerateParams,
): Promise<GenerateWithMetricsResult> {
  const res = await fetch('/generate/with_metrics', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: params.text,
      language: params.language ?? 'English',
      voice_id: params.voiceId?.startsWith('pocket:') ? undefined : params.voiceId ?? undefined,
      builtin_voice: builtinVoiceFromParams(params),
      seed: params.seed ?? undefined,
      instruct: params.instruct ?? undefined,
      style_preset: params.stylePreset ?? undefined,
      postprocess: params.postprocess ?? undefined,
      prosody_repair: params.prosodyRepair ?? undefined,
    }),
  })
  if (!res.ok) throw new Error(await readError(res))
  const body = await res.json()
  const bytes = Uint8Array.from(atob(body.audio_base64), (c) => c.charCodeAt(0))
  return {
    blob: new Blob([bytes], { type: body.media_type ?? 'audio/wav' }),
    seed: typeof body.seed === 'number' ? body.seed : null,
    metrics: body.metrics ?? {},
    prosodyRepair: body.prosody_repair,
  }
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

export async function createVoiceDesign(
  params: VoiceDesignParams,
  signal?: AbortSignal,
): Promise<VoiceDesignPreviewResult> {
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
    signal,
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export interface VoiceDesignSaveResult {
  voice_id: string
}

export async function saveVoiceDesign(
  previewId: string,
  familyId?: string | null,
  variantName?: string | null,
  variantKind?: string | null,
): Promise<VoiceDesignSaveResult> {
  const res = await fetch(`/voice_design/preview/${encodeURIComponent(previewId)}/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      family_id: familyId,
      variant_name: variantName,
      variant_kind: variantKind,
    }),
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

export async function listBuiltInVoices(): Promise<BuiltInVoiceMeta[]> {
  const res = await fetch('/voices/built-in')
  if (!res.ok) throw new Error(await readError(res))
  const body = await res.json()
  return body.voices ?? body
}

export async function getVoice(voiceId: string): Promise<VoiceMeta> {
  const res = await fetch(`/voices/${encodeURIComponent(voiceId)}`)
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function updateVoiceSampleText(voiceId: string, sampleText: string): Promise<VoiceMeta> {
  const res = await fetch(`/voices/${encodeURIComponent(voiceId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sample_text: sampleText }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function deleteVoice(voiceId: string): Promise<void> {
  const res = await fetch(`/voices/${encodeURIComponent(voiceId)}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await readError(res))
}

// Forks `voiceId` into a brand-new, independent voice_id. Omitting `variantFilename` forks
// whichever audio is currently active; passing one forks that specific variant without
// disturbing which variant is active on the source voice.
export async function duplicateVoice(voiceId: string, variantFilename?: string): Promise<VoiceMeta> {
  const res = await fetch(`/voices/${encodeURIComponent(voiceId)}/duplicate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ variant_filename: variantFilename ?? null }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function getVoiceVariantAudio(voiceId: string, variantFilename: string): Promise<{ audio_base64: string }> {
  const res = await fetch(`/voices/${encodeURIComponent(voiceId)}/variants/${encodeURIComponent(variantFilename)}/audio`)
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function deleteVoiceVariant(voiceId: string, variantFilename: string): Promise<void> {
  const res = await fetch(`/voices/${encodeURIComponent(voiceId)}/variants/${encodeURIComponent(variantFilename)}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await readError(res))
}

export async function analyzeVoiceReference(voiceId: string): Promise<VoiceMeta> {
  const res = await fetch(`/voices/${encodeURIComponent(voiceId)}/analyze`, { method: 'POST' })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function undoVoiceReferenceEdit(voiceId: string): Promise<VoiceMeta> {
  const res = await fetch(`/voices/${encodeURIComponent(voiceId)}/undo-reference-edit`, { method: 'POST' })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function normalizeVoiceReference(voiceId: string): Promise<VoiceMeta> {
  const res = await fetch(`/voices/${encodeURIComponent(voiceId)}/normalize`, { method: 'POST' })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function trimVoiceReferenceSilence(voiceId: string): Promise<VoiceMeta> {
  const res = await fetch(`/voices/${encodeURIComponent(voiceId)}/trim-silence`, { method: 'POST' })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function setDefaultVoiceVariant(voiceId: string): Promise<VoiceMeta> {
  const res = await fetch(`/voices/${encodeURIComponent(voiceId)}/set-default`, { method: 'POST' })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

// Processing mode for pause shaping: 'auto' lets triage decide, 'natural' forces the
// fast energy path, 'precise' forces forced-alignment-directed surgical insertion.
export type ProsodyMode = 'auto' | 'natural' | 'precise'

export interface ProsodyPausePlanEntry {
  at_ms: number
  cut_sample: number
  cut_ms: number
  // Snapped cut in the *original* (pre-insertion) timeline — lets the UI place the
  // marker on the ORIGINAL lane next to the word labels, which live in original time.
  src_cut_ms?: number
  insert_ms: number
  target_ms: number
  existing_ms: number
  provenance: 'zero_cross' | 'energy_min' | 'boundary'
  origin: 'alignment' | 'vad' | 'energy'
}

export interface ProsodyPreview {
  audio_base64: string
  metrics: ReferenceMetrics
  sample_rate: number
  sample_count: number
  plan: ProsodyPausePlanEntry[]
}

export async function previewVoiceProsody(
  voiceId: string,
  stylePreset: string,
  paceMultiplier: number,
  pauseOffset: number,
  mode: ProsodyMode,
  // Per-boundary target deltas (ms), keyed by the boundary's rounded at_ms. Layered on
  // top of pauseOffset so one manufactured pause can be lengthened/shortened in isolation.
  targetOverrides?: Record<string, number>,
): Promise<ProsodyPreview> {
  const query = new URLSearchParams({
    style_preset: stylePreset,
    pace_multiplier: String(paceMultiplier),
    pause_offset: String(pauseOffset),
    mode,
  })
  if (targetOverrides && Object.keys(targetOverrides).length > 0) {
    query.set('target_overrides', JSON.stringify(targetOverrides))
  }
  const res = await fetch(`/voices/${encodeURIComponent(voiceId)}/preview-prosody?${query}`)
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function adjustVoiceReferencePauses(
  voiceId: string,
  stylePreset: string,
  paceMultiplier: number,
  pauseOffset: number,
  mode: ProsodyMode = 'auto',
): Promise<VoiceMeta> {
  const res = await fetch(`/voices/${encodeURIComponent(voiceId)}/adjust-pauses`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ 
      style_preset: stylePreset, 
      pace_multiplier: paceMultiplier, 
      pause_offset: pauseOffset,
      mode,
    }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

// --- Forced alignment (plan §5.5/§5.6) ---------------------------------------
// A detected linguistic boundary. `kind` distinguishes a sentence split (owns the
// big sentence-end pause) from a plain word and an uncertain (low-confidence, skipped)
// boundary; `owns_clause` marks a comma/clause owner. Times are seconds into the clip.
export interface AlignmentBoundary {
  text: string
  start: number
  end: number
  score: number
  kind: 'word' | 'sentence_split' | 'uncertain'
  owns_clause: boolean
}

export interface AlignmentRecord {
  boundaries: AlignmentBoundary[]
  model_revision?: string
  transcript_sha256?: string
}

export interface AlignJob {
  job_id: string
  voice_id: string
  status: 'queued' | 'running' | 'completed' | 'cancelled' | 'failed'
  created_at: number
  result: AlignmentRecord | null
  error: string | null
  started_at: number | null
  finished_at: number | null
  duration_seconds: number | null
  latency_budget_seconds: number
  within_latency_budget: boolean | null
}

// Kick off (or reuse) an async forced-alignment pass. Returns a job to poll.
export async function startVoiceAlignment(voiceId: string, force = false): Promise<AlignJob> {
  const res = await fetch(`/voices/${encodeURIComponent(voiceId)}/align`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ force }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function getVoiceAlignmentStatus(voiceId: string, jobId: string): Promise<AlignJob> {
  const res = await fetch(
    `/voices/${encodeURIComponent(voiceId)}/align/${encodeURIComponent(jobId)}`,
  )
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function cancelVoiceAlignment(voiceId: string, jobId: string): Promise<AlignJob> {
  const res = await fetch(
    `/voices/${encodeURIComponent(voiceId)}/align/${encodeURIComponent(jobId)}`,
    { method: 'DELETE' },
  )
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function setActiveVoiceVariant(voiceId: string, variantFilename: string | null): Promise<{ status: string; active_variant: string }> {
  const res = await fetch(`/voices/${encodeURIComponent(voiceId)}/set-active-variant`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ variant_filename: variantFilename }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function getVoiceVariants(voiceId: string): Promise<{ variants: string[]; active_variant: string | null }> {
  const res = await fetch(`/voices/${encodeURIComponent(voiceId)}/variants`)
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function applyVoiceReferenceRegionEdits(
  voiceId: string,
  edits: StitchPlanRegionEdit[],
): Promise<VoiceMeta> {
  const res = await fetch(`/voices/${encodeURIComponent(voiceId)}/region-edits`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      edits: edits.map((edit) => ({
        type: edit.type,
        start_ms: edit.startMs,
        end_ms: edit.endMs,
        gain_db: edit.gainDb,
        fade_in_ms: edit.fadeInMs,
        fade_out_ms: edit.fadeOutMs,
        at_ms: edit.atMs,
        duration_ms: edit.durationMs,
      })),
    }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function activateVoiceForApi(voiceId: string): Promise<VoiceMeta> {
  const res = await fetch(`/voices/${encodeURIComponent(voiceId)}/activate`, { method: 'POST' })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function warmVoice(voiceId: string): Promise<void> {
  const res = await fetch(`/voices/${encodeURIComponent(voiceId)}/warm`, { method: 'POST' })
  if (!res.ok) throw new Error(await readError(res))
}

export interface HealthState {
  status: string
  model_loaded: boolean
  // True forever after the first successful load, even through later idle-unload cycles —
  // distinguishes true cold-boot loading from a transparent lazy-reload-on-next-request idle.
  service_started?: boolean
  swap_in_progress: boolean
  backend: string
  resolved_backend?: string
  model: string
  loading_message?: string
  [key: string]: unknown
}

export async function getHealth(signal?: AbortSignal): Promise<HealthState> {
  const res = await fetch('/health', { signal })
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

export interface StitchPlanRegionEdit {
  type: 'gain' | 'mute' | 'delete' | 'fade' | 'insert_silence'
  startMs?: number
  endMs?: number
  gainDb?: number
  fadeInMs?: number
  fadeOutMs?: number
  atMs?: number
  durationMs?: number
}

export interface StitchPlanPayload {
  clips: {
    segmentId?: string
    candidateId?: string
    voiceId?: string
    trimStartMs: number
    trimEndMs: number
    fadeInMs: number
    fadeOutMs: number
    text?: string
    prosodyMode?: 'off' | 'auto' | 'precise'
    edits?: StitchPlanRegionEdit[]
  }[]
  paddingMs: number[]
  crossfadeMs: number
  segmentTargetDbfs: number
  finalTargetDbfs: number
  finalCeilingDb: number
  compress: { thresholdDb: number; ratio: number; attackMs: number; releaseMs: number } | null
  stylePreset: string
  paceMultiplier: number
  pauseOffsetMs: number
}

// Backend (_resolve_stitch_plan/_resolve_one_clip_ref in app.py) reads snake_case keys only —
// StitchPlanPayload is camelCase on the frontend, so every stitch_plan request must go through
// this converter or every clip ref (and every trim/fade/dsp override) silently fails to resolve.
function serializeStitchPlan(plan: StitchPlanPayload) {
  return {
    clips: plan.clips.map((c) => ({
      segment_id: c.segmentId ?? undefined,
      candidate_id: c.candidateId ?? undefined,
      voice_id: c.voiceId ?? undefined,
      trim_start_ms: c.trimStartMs,
      trim_end_ms: c.trimEndMs,
      fade_in_ms: c.fadeInMs,
      fade_out_ms: c.fadeOutMs,
      text: c.text,
      prosody_mode: c.prosodyMode,
      edits: c.edits?.length
        ? c.edits.map((e) => ({
            type: e.type,
            start_ms: e.startMs,
            end_ms: e.endMs,
            gain_db: e.gainDb,
            fade_in_ms: e.fadeInMs,
            fade_out_ms: e.fadeOutMs,
            at_ms: e.atMs,
            duration_ms: e.durationMs,
          }))
        : undefined,
    })),
    padding_ms: plan.paddingMs,
    crossfade_ms: plan.crossfadeMs,
    segment_target_dbfs: plan.segmentTargetDbfs,
    final_target_dbfs: plan.finalTargetDbfs,
    final_ceiling_db: plan.finalCeilingDb,
    compress: plan.compress
      ? {
          threshold_db: plan.compress.thresholdDb,
          ratio: plan.compress.ratio,
          attack_ms: plan.compress.attackMs,
          release_ms: plan.compress.releaseMs,
        }
      : undefined,
    style_preset: plan.stylePreset,
    pace_multiplier: plan.paceMultiplier,
    pause_offset_ms: plan.pauseOffsetMs,
  }
}

export async function getStitchPacingTargets(params: {
  transcripts: string[]
  stylePreset: string
  paceMultiplier: number
  pauseOffsetMs: number
}): Promise<{ padding_ms: number[]; style_preset: string }> {
  const res = await fetch('/omnivoice/stitch/pacing-targets', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      transcripts: params.transcripts,
      style_preset: params.stylePreset,
      pace_multiplier: params.paceMultiplier,
      pause_offset_ms: params.pauseOffsetMs,
    }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function renderStitchPlan(plan: StitchPlanPayload): Promise<Blob> {
  const res = await fetch('/omnivoice/stitch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ stitch_plan: serializeStitchPlan(plan) }),
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
  familyId?: string | null
  variantName?: string | null
  variantKind?: string | null
  /** Optional stitch_plan for full control (docs/dev/features/stitch_editor.md). */
  stitchPlan?: StitchPlanPayload | null
  projectId?: string | null
  projectName?: string | null
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
      family_id: params.familyId ?? undefined,
      variant_name: params.variantName ?? undefined,
      variant_kind: params.variantKind ?? undefined,
      stitch_plan: params.stitchPlan
        ? serializeStitchPlan(params.stitchPlan)
        : undefined,
      project_id: params.projectId ?? undefined,
      project_name: params.projectName ?? undefined,
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
  duration_sec?: number
  language?: string | null
  seed?: number | null
  num_step?: number | null
  speed?: number | null
  guidance_scale?: number | null
  diverse_candidates?: boolean | null
  postprocess_output?: string | null
  duration_target?: number | null
  candidate_id?: string | null
  job_id?: string | null
  whisper_transcript?: string | null
  match_score?: number | null
  feature_tags?: AccentFeature[]
  project_id?: string | null
  project_name?: string | null
}

export async function lockInOmniVoiceSegment(params: {
  candidateId: string
  text: string
  instruct: string
  accentId?: string | null
  featureTags?: AccentFeature[]
  projectId?: string | null
  projectName?: string | null
}): Promise<SegmentMeta> {
  const res = await fetch('/omnivoice/segments', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      candidate_id: params.candidateId,
      text: params.text,
      instruct: params.instruct,
      accent_id: params.accentId ?? undefined,
      feature_tags: params.featureTags?.length ? params.featureTags : undefined,
      project_id: params.projectId ?? undefined,
      project_name: params.projectName ?? undefined,
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

// listOmniVoiceSegments() intentionally omits audio (the list endpoint drops wav bytes for
// payload size), so anything that needs actual samples client-side — the stitch editor's
// waveform/duration decode, "insert from library" — has to fetch it separately per segment.
export async function getSegmentAudioBase64(segmentId: string): Promise<string> {
  const res = await fetch(`/omnivoice/segments/${encodeURIComponent(segmentId)}/audio`)
  if (!res.ok) throw new Error(await readError(res))
  const buf = await res.arrayBuffer()
  const bytes = new Uint8Array(buf)
  let binary = ''
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
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
    MODEL_DTYPE: string
    POCKET_TTS_TEMP: number | undefined
    POCKET_TTS_LSD_DECODE_STEPS: number | undefined
    POCKET_TTS_EOS_THRESHOLD: number | undefined
    POCKET_TTS_NOISE_CLAMP: number | null | undefined
    POCKET_TTS_FRAMES_AFTER_EOS: number | null | undefined
    pocket_tts_voice_cloning_available: boolean | undefined
    pocket_tts_voice_cloning_message: string | undefined
  }
  read_only: {
    mounts: Record<string, 'ro' | 'rw' | null>
    ref_audio_path_set: boolean
    hf_token_set: boolean
    hf_token_status: 'set' | 'not_set'
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

// ── Async generation (progress + cancel) ──────────────────────────────────────────────────

export async function generateAsync(
  params: GenerateParams,
): Promise<AsyncJobIdResult> {
  const res = await fetch('/generate/async', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: params.text,
      language: params.language ?? 'English',
      voice_id: params.voiceId?.startsWith('pocket:') ? undefined : params.voiceId ?? undefined,
      builtin_voice: builtinVoiceFromParams(params),
      seed: params.seed ?? undefined,
      instruct: params.instruct ?? undefined,
      style_preset: params.stylePreset ?? undefined,
      postprocess: params.postprocess ?? undefined,
      prosody_repair: params.prosodyRepair ?? undefined,
      response_format: params.responseFormat ?? 'mp3',
    }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function getGenerateJobProgress(
  jobId: string,
): Promise<GenerateJobProgress> {
  const res = await fetch(`/generate/progress?job_id=${encodeURIComponent(jobId)}`)
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function cancelGenerate(jobId: string): Promise<void> {
  const res = await fetch(`/generate/cancel?job_id=${encodeURIComponent(jobId)}`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(await readError(res))
}

export async function getGenerateJobAudio(
  jobId: string,
  responseFormat: 'mp3' | 'wav' = 'mp3',
): Promise<Blob> {
  const res = await fetch(
    `/generate/job/${encodeURIComponent(jobId)}/audio?response_format=${responseFormat}`,
  )
  if (!res.ok) throw new Error(await readError(res))
  return res.blob()
}

// ── OmniVoice audition cancel ─────────────────────────────────────────────────────────────

export async function cancelOmniVoiceAudition(jobId: string): Promise<void> {
  const res = await fetch(
    `/omnivoice/audition/cancel?job_id=${encodeURIComponent(jobId)}`,
    { method: 'POST' },
  )
  if (!res.ok) throw new Error(await readError(res))
}

// ── Accent Design Projects (§4) — lightweight grouping tag for voices/segments ────────────

export interface Project {
  project_id: string
  name: string
  description?: string | null
  created_at: number
}

export async function listProjects(): Promise<Project[]> {
  const res = await fetch('/projects')
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function createProject(name: string, description?: string): Promise<Project> {
  const res = await fetch('/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function renameProject(
  projectId: string,
  updates: { name?: string; description?: string },
): Promise<Project> {
  const res = await fetch(`/projects/${encodeURIComponent(projectId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function deleteProject(projectId: string): Promise<void> {
  const res = await fetch(`/projects/${encodeURIComponent(projectId)}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await readError(res))
}

export async function setVoiceProject(
  voiceId: string,
  projectId: string | null,
  projectName?: string | null,
): Promise<VoiceMeta> {
  const res = await fetch(`/voices/${encodeURIComponent(voiceId)}/project`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_id: projectId, project_name: projectName }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function setSegmentProject(
  segmentId: string,
  projectId: string | null,
  projectName?: string | null,
): Promise<SegmentMeta> {
  const res = await fetch(`/omnivoice/segments/${encodeURIComponent(segmentId)}/project`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_id: projectId, project_name: projectName }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}
