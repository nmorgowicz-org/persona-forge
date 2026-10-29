import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AutoCheckError,
  getAutoCheckStatus,
  runAutoCheck,
  startAutoCheckDownload,
  type AutoCheckResult,
  type AutoCheckStatus,
} from '@/lib/compareAutoCheck'

export const AUTO_CHECK_DISCLAIMER = 'Not calibrated for synthetic voices; never replaces the rating.'
export const WER_MODEL = 'whisper-tiny-en'
export const SIMILARITY_MODEL = 'wavlm-base-plus-sv'

export type CheckState =
  | { state: 'running' }
  | { state: 'done'; result: AutoCheckResult }
  | { state: 'error'; message: string }

/**
 * Auto-check state for the Compare tab. Nothing is requested until `enabled` (blind mode is over
 * or off) and nothing runs until `check()` is called from a click. Models are only downloaded from
 * `download()`, which the setup box calls from an explicit button.
 */
export function useAutoCheck(enabled: boolean) {
  const [status, setStatus] = useState<AutoCheckStatus | null>(null)
  const [statusError, setStatusError] = useState<string | null>(null)
  const [checks, setChecks] = useState<Record<number, CheckState>>({})
  const running = useRef(false)

  const refresh = useCallback(async () => {
    try {
      setStatus(await getAutoCheckStatus())
      setStatusError(null)
    } catch (err) {
      setStatusError(String((err as Error)?.message || err))
    }
  }, [])

  useEffect(() => {
    if (!enabled) return
    getAutoCheckStatus()
      .then((next) => {
        setStatus(next)
        setStatusError(null)
      })
      .catch((err: unknown) => setStatusError(String((err as Error)?.message || err)))
  }, [enabled])

  const downloading = status?.job.state === 'running'
  useEffect(() => {
    if (!downloading) return
    const timer = setInterval(() => void refresh(), 1500)
    return () => clearInterval(timer)
  }, [downloading, refresh])

  async function download(ids: string[]) {
    try {
      setStatus(await startAutoCheckDownload(ids))
    } catch (err) {
      setStatusError(String((err as Error)?.message || err))
    }
  }

  async function check(index: number, clip: Blob, text: string, referenceVoiceId: string | null) {
    if (running.current) return
    running.current = true
    setChecks((cur) => ({ ...cur, [index]: { state: 'running' } }))
    try {
      const result = await runAutoCheck(clip, text, referenceVoiceId)
      setChecks((cur) => ({ ...cur, [index]: { state: 'done', result } }))
      setStatus((cur) => (cur ? { ...cur, models: result.models } : cur))
    } catch (err) {
      if (err instanceof AutoCheckError && err.code === 'models_missing') void refresh()
      setChecks((cur) => ({ ...cur, [index]: { state: 'error', message: String((err as Error)?.message || err) } }))
    } finally {
      running.current = false
    }
  }

  const anyRunning = Object.values(checks).some((c) => c.state === 'running')
  const werReady = status?.models.find((m) => m.id === WER_MODEL)?.available ?? false
  return { status, statusError, checks, check, download, anyRunning, werReady, reset: () => setChecks({}) }
}
