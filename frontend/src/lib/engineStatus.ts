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
 * Load state of every engine, straight from GET /engines. Polls every 2 s while any engine is
 * loading or warming; call ``refresh`` when something may have started a load (a request that
 * was told to wait). Also returns the whole cards, so callers can read measured data such as
 * the install check's warm-up time.
 */
export function useEngineLoadStatus(): {
  status: Record<string, EngineLoadStatus | undefined>
  cards: EngineCard[]
  refresh: () => void
} {
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
