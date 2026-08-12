import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Sparkles, X } from 'lucide-react'
import { getHealth } from '@/lib/api'
import { checkForUpdate, getDismissedVersion, setDismissedVersion } from '@/lib/updateCheck'

// Startup delay avoids competing with the initial model-load/health-poll burst.
const STARTUP_DELAY_MS = 5_000
const RECHECK_INTERVAL_MS = 24 * 60 * 60 * 1000

export function UpdateAvailableBanner() {
  const [update, setUpdate] = useState<{ version: string; url: string } | null>(null)

  useEffect(() => {
    let cancelled = false

    const run = async () => {
      try {
        const health = await getHealth()
        const currentVersion = typeof health.version === 'string' ? health.version : null
        if (!currentVersion || cancelled) return
        const found = await checkForUpdate(currentVersion)
        if (cancelled) return
        if (found && found.version !== getDismissedVersion()) {
          setUpdate(found)
        }
      } catch {
        // Non-critical — silently skip (e.g. offline, repo not yet public, GitHub rate limit)
      }
    }

    const startupTimer = setTimeout(run, STARTUP_DELAY_MS)
    const intervalId = setInterval(run, RECHECK_INTERVAL_MS)
    return () => {
      cancelled = true
      clearTimeout(startupTimer)
      clearInterval(intervalId)
    }
  }, [])

  if (!update) return null

  return (
    <AnimatePresence initial={false}>
      <motion.div
        initial={{ height: 0, opacity: 0 }}
        animate={{ height: 'auto', opacity: 1 }}
        exit={{ height: 0, opacity: 0 }}
        className="overflow-hidden border-b border-primary/30 bg-primary/10"
      >
        <div className="flex items-center gap-2 px-4 py-1.5 text-xs text-primary">
          <Sparkles className="size-3 shrink-0" />
          <span className="min-w-0 flex-1 truncate">
            Persona Forge {update.version} is available.{' '}
            <a
              href={update.url}
              target="_blank"
              rel="noopener noreferrer"
              className="underline"
            >
              See what's new
            </a>
          </span>
          <button
            type="button"
            onClick={() => {
              setDismissedVersion(update.version)
              setUpdate(null)
            }}
            className="shrink-0 rounded p-0.5 hover:bg-primary/20"
            title="Dismiss"
          >
            <X className="size-3" />
          </button>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}
