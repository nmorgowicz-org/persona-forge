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

export interface VoiceDesignResult {
  voice_id: string
  sample_rate: number
  seed: number
  audio_base64: string
}

export async function createVoiceDesign(params: VoiceDesignParams): Promise<VoiceDesignResult> {
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
  [key: string]: unknown
}

export async function getHealth(): Promise<HealthState> {
  const res = await fetch('/health')
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
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
