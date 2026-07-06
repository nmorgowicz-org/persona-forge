import { useEffect, useState } from 'react'
import { getHealth } from '@/lib/api'

// Polls /health so any page can show a prominent, honest "VoiceDesign swap in progress"
// banner (docs/dev/architecture/voice_design.md §3: "do not hide behind a spinner with no explanation") —
// a swap unloads the Base model for tens of seconds to minutes, so every generation
// endpoint 503s for that whole window, not just the /voice_design call that triggered it.
const POLL_MS = 2500
// Bare fetch() has no timeout, so a dead/unreachable host (dockermisc1 asleep, wifi drop)
// let each tick hang until the browser's own connection timeout, then immediately retry —
// flooding the console with ERR_CONNECTION_TIMED_OUT. Cap each attempt and back off on
// repeated failures instead of hammering at a fixed 2.5s cadence forever.
const REQUEST_TIMEOUT_MS = 6000
const MAX_BACKOFF_MS = 30000

export function useSwapStatus(): boolean {
  const [swapping, setSwapping] = useState(false)

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>
    let consecutiveFailures = 0

    async function tick() {
      const controller = new AbortController()
      const abortTimer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
      try {
        const health = await getHealth(controller.signal)
        if (!cancelled) setSwapping(Boolean(health.swap_in_progress))
        consecutiveFailures = 0
      } catch {
        // Health check failures are non-fatal here — just skip this tick and back off.
        consecutiveFailures++
      } finally {
        clearTimeout(abortTimer)
        if (!cancelled) {
          const delay = Math.min(POLL_MS * 2 ** consecutiveFailures, MAX_BACKOFF_MS)
          timer = setTimeout(tick, delay)
        }
      }
    }

    tick()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [])

  return swapping
}
