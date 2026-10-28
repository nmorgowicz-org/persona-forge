import { useCallback, useEffect, useState } from 'react'
import { listEngines, type EngineCard, type EngineLoadStatus } from '@/lib/api'

/** An engine that is still getting ready: its worker is loading, or compiling its first call. */
export function isEngineBusy(status?: EngineLoadStatus | null): boolean {
  return status?.state === 'loading' || status?.state === 'warming'
}

function seconds(value?: number | null): string | null {
  return typeof value === 'number' ? `${Math.round(value)} s` : null
}

/** One line for a busy engine, from the real state the API reports. Null when it is not busy. */
export function engineLoadNote(label: string, status?: EngineLoadStatus | null): string | null {
  if (status?.state === 'loading') {
    const elapsed = seconds(status.elapsed_s)
    return `${label} is loading${elapsed ? ` (${elapsed} so far)` : ''}. Requests wait for it automatically.`
  }
  if (status?.state === 'warming') {
    const elapsed = seconds(status.elapsed_s)
    const estimate = seconds(status.estimated_s)
    const progress = elapsed ? (estimate ? ` (${elapsed} of about ${estimate})` : ` (${elapsed} so far)`) : ''
    return `${label} is warming up: its first call compiles the model${progress}. Requests wait for it automatically.`
  }
  return null
}

/** Short suffix for an engine picker option, or an empty string when the engine is ready. */
export function engineLoadSuffix(status?: EngineLoadStatus | null): string {
  if (status?.state === 'warming') return ' (warming up)'
  if (status?.state === 'loading') return ' (loading)'
  return ''
}

/**
 * State of the engine the shell's status chip (§5.1) watches, in the plan §5.8 vocabulary the
 * UI can honestly claim from GET /engines plus the startup/health state. There is no Busy here
 * on purpose: neither /engines nor the store carries a request/queue signal today, so an
 * idle-but-serving engine reads as Ready instead of inventing one.
 */
export type EngineChipState = 'ready' | 'loading' | 'warming' | 'error'

export const ENGINE_CHIP_WORD: Record<EngineChipState, string> = {
  ready: 'Ready',
  loading: 'Loading',
  warming: 'Warming',
  error: 'Error',
}

/**
 * The engine the chip watches: the engine that serves the API default when one is set (it
 * answers the endpoint's default requests), else the active backend's engine (Pocket today).
 */
export function chooseChipEngine(cards: EngineCard[]): EngineCard | null {
  return cards.find((card) => card.api_default) ?? cards.find((card) => card.active) ?? null
}

/**
 * Chip state from the signals that exist: a server-reported model load wins (it blocks every
 * engine), then the watched engine's own load state, then its install/verification failures.
 * The reason, when there is one, is the actionable text for the tooltip.
 */
export function deriveChipState(
  card: EngineCard | null,
  health: { loadingMessage: string | null; healthStatus: string | null; healthError: string | null },
): { state: EngineChipState; reason: string | null } {
  if (health.healthStatus === 'error') {
    return {
      state: 'error',
      reason: health.healthError || health.loadingMessage || 'The model failed to load.',
    }
  }
  if (health.loadingMessage) {
    return { state: 'loading', reason: health.loadingMessage }
  }
  if (!card) return { state: 'ready', reason: null }
  const load = card.load_status
  if (load?.state === 'warming') return { state: 'warming', reason: engineLoadNote(card.label, load) }
  if (load?.state === 'loading') return { state: 'loading', reason: engineLoadNote(card.label, load) }
  if (load?.state === 'error') {
    return { state: 'error', reason: load.error || `${card.label} failed to load.` }
  }
  // An install of the watched engine runs in the background while its card already exists
  // (and may already be the API default); that is progress, not a failure.
  if (card.install_job?.state === 'running') {
    const step = card.install_job.step ? ` (${card.install_job.step})` : ''
    return { state: 'loading', reason: `Installing ${card.label}${step}.` }
  }
  if (card.install_job?.state === 'error') {
    return { state: 'error', reason: card.install_job.error || `${card.label} could not be installed.` }
  }
  if (card.state.status === 'invalid') {
    return {
      state: 'error',
      reason: card.state.errors.join(' ') || `The ${card.label} files failed verification.`,
    }
  }
  if (card.api_default && card.state.status === 'not-installed') {
    return { state: 'error', reason: `The API default needs ${card.label}, which is not installed.` }
  }
  return { state: 'ready', reason: null }
}

/**
 * Load state of every engine, straight from GET /engines. Polls every 2 s while any engine is
 * loading or warming; call ``refresh`` when something may have started a load (a request that
 * was told to wait). Also returns the whole cards, so callers can read measured data such as
 * the install check's warm-up time.
 *
 * ``idleIntervalMs`` keeps a slow poll running while nothing is in flight, so a always-mounted
 * surface (the shell's engine status chip) notices a load an API request started outside this
 * tab. Page-level callers omit it and keep the mount-plus-while-busy behavior.
 */
export function useEngineLoadStatus(options?: {
  /** Slow re-read period while no engine is loading or warming. */
  idleIntervalMs?: number
}): {
  status: Record<string, EngineLoadStatus | undefined>
  cards: EngineCard[]
  refresh: () => void
} {
  const idleIntervalMs = options?.idleIntervalMs
  const [status, setStatus] = useState<Record<string, EngineLoadStatus | undefined>>({})
  const [cards, setCards] = useState<EngineCard[]>([])
  const refresh = useCallback(() => {
    listEngines()
      .then((next) => {
        setCards(next)
        setStatus(Object.fromEntries(next.map((card) => [card.id, card.load_status])))
      })
      .catch(() => undefined)
  }, [])
  useEffect(() => {
    refresh()
  }, [refresh])
  const busy = Object.values(status).some(isEngineBusy)
  useEffect(() => {
    if (!busy) return
    const timer = window.setInterval(refresh, 2000)
    return () => window.clearInterval(timer)
  }, [busy, refresh])
  useEffect(() => {
    if (busy || !idleIntervalMs) return
    const timer = window.setInterval(refresh, idleIntervalMs)
    return () => window.clearInterval(timer)
  }, [busy, refresh, idleIntervalMs])
  return { status, cards, refresh }
}

export interface SpeechWait {
  /** The server's own message, which names the engine. */
  message: string
  retryAfterS: number
  attempt: number
}

const MAX_RETRY_WAIT_S = 10
const GIVE_UP_AFTER_MS = 10 * 60 * 1000

/**
 * POST /v1/audio/speech, waiting out an engine that is loading or warming up.
 *
 * The API answers such a request with 503, ``Retry-After`` and error code ``engine_warming``
 * instead of holding the connection open. This retries on that signal only; any other response is
 * returned as is. ``waitedMs`` is the time spent waiting, so callers that report generation time
 * can leave the one-off warm-up out of it.
 */
export async function fetchSpeech(
  payload: Record<string, unknown>,
  onWait?: (wait: SpeechWait) => void,
): Promise<{ response: Response; waitedMs: number }> {
  const waitStart = Date.now()
  let waitedMs = 0
  for (let attempt = 1; ; attempt++) {
    const attemptStart = Date.now()
    const response = await fetch('/v1/audio/speech', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (response.status !== 503) return { response, waitedMs }
    const body = await response
      .clone()
      .json()
      .catch(() => null)
    if (body?.error?.code !== 'engine_warming' || Date.now() - waitStart > GIVE_UP_AFTER_MS) {
      return { response, waitedMs }
    }
    const header = Number(response.headers.get('Retry-After'))
    const retryAfterS = Math.min(Math.max(Number.isFinite(header) && header > 0 ? header : 5, 1), MAX_RETRY_WAIT_S)
    onWait?.({ message: String(body.error.message), retryAfterS, attempt })
    // Project targets ES2023, which has no Promise.withResolvers typings; the executor form stays.
    await new Promise<void>((resolve) => window.setTimeout(resolve, retryAfterS * 1000))
    waitedMs += Date.now() - attemptStart
  }
}
