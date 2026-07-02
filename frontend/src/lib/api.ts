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
  created_at: number
  audio_base64?: string
}

async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json()
    return body.error ?? `HTTP ${res.status}`
  } catch {
    return `HTTP ${res.status}`
  }
}

export async function generateSpeech(params: GenerateParams): Promise<Blob> {
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
  return res.blob()
}

export interface VoiceDesignParams {
  description: string
  sampleText: string
  language?: string
}

export interface VoiceDesignResult {
  voice_id: string
  sample_rate: number
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

export async function getHealth(): Promise<Record<string, unknown>> {
  const res = await fetch('/health')
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}
