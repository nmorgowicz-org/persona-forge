import { useEffect, useState } from 'react'
import { getHealth } from '@/lib/api'

// Polls /health so any page can show a prominent, honest "VoiceDesign swap in progress"
// banner (PLAN_voice_design.md §3: "do not hide behind a spinner with no explanation") —
// a swap unloads the Base model for tens of seconds to minutes, so every generation
// endpoint 503s for that whole window, not just the /voice_design call that triggered it.
const POLL_MS = 2500

export function useSwapStatus(): boolean {
  const [swapping, setSwapping] = useState(false)

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>

    async function tick() {
      try {
        const health = await getHealth()
        if (!cancelled) setSwapping(Boolean(health.swap_in_progress))
      } catch {
        // Health check failures are non-fatal here — just skip this tick.
      } finally {
        if (!cancelled) timer = setTimeout(tick, POLL_MS)
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
