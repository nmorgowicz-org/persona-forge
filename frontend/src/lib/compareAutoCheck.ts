// Optional Compare "auto-check" hints (plan §5.10): word error rate and speaker similarity for one
// generated clip. Offline and non-authoritative; models are only downloaded from an explicit click.

export interface AutoCheckModel {
  id: string
  label: string
  purpose: 'word_error_rate' | 'speaker_similarity'
  available: boolean
  size_bytes: number
  size_label: string
}

export interface AutoCheckJob {
  state: 'idle' | 'running' | 'done' | 'error'
  step: string
  step_index: number
  step_count: number
  error: string | null
}

export interface AutoCheckStatus {
  models: AutoCheckModel[]
  job: AutoCheckJob
  disclaimer: string
}

export interface AutoCheckResult {
  wer: number | null
  transcript: string | null
  similarity: number | null
  details: {
    substitutions: number
    deletions: number
    insertions: number
    reference_words: number
    hypothesis_words: number
  } | null
  notes: string[]
  disclaimer: string
  models: AutoCheckModel[]
}

export class AutoCheckError extends Error {
  code: string | null
  models: AutoCheckModel[] | null

  constructor(message: string, code: string | null, models: AutoCheckModel[] | null) {
    super(message)
    this.code = code
    this.models = models
  }
}

async function failure(res: Response): Promise<AutoCheckError> {
  const body = await res.json().catch(() => ({}))
  return new AutoCheckError(
    typeof body?.error === 'string' ? body.error : `Auto-check request failed (${res.status})`,
    typeof body?.code === 'string' ? body.code : null,
    Array.isArray(body?.models) ? (body.models as AutoCheckModel[]) : null,
  )
}

export async function getAutoCheckStatus(): Promise<AutoCheckStatus> {
  const res = await fetch('/compare/auto-check/status')
  if (!res.ok) throw await failure(res)
  return (await res.json()) as AutoCheckStatus
}

/** The explicit opt-in: downloads the listed auto-check models (the server skips any already on disk). */
export async function startAutoCheckDownload(ids: string[]): Promise<AutoCheckStatus> {
  const res = await fetch('/compare/auto-check/install', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ models: ids }),
  })
  if (!res.ok && res.status !== 409) throw await failure(res)
  return (await res.json()) as AutoCheckStatus
}

export async function runAutoCheck(
  clip: Blob,
  text: string,
  referenceVoiceId: string | null,
): Promise<AutoCheckResult> {
  const form = new FormData()
  form.append('audio', clip, 'clip.wav')
  form.append('text', text)
  if (referenceVoiceId) form.append('reference_voice_id', referenceVoiceId)
  const res = await fetch('/compare/auto-check', { method: 'POST', body: form })
  if (!res.ok) throw await failure(res)
  return (await res.json()) as AutoCheckResult
}
