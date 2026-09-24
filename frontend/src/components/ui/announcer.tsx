import { useEffect } from 'react'
import { useAppStore } from '@/store'

/** How long a message stays in the region before it is cleared. Long enough to be read at a
 * screen reader's pace, short enough that the next announcement replaces old news. */
const ANNOUNCE_MS = 6000

/**
 * B-P9: the app's single live region. One element, mounted for the app's whole life, that
 * every async success/failure announces into via `useAppStore.announce()`.
 *
 * The element exists before any message arrives -- a live region created together with its
 * text is not reliably announced -- and it is cleared on a timer rather than accumulating, so
 * the region is never left holding stale news. (Announcing the identical text twice in a row
 * inside that window is a single announcement; after it clears, the same text announces
 * again.)
 *
 * It is deliberately visually hidden: the visible confirmation of an action belongs to the
 * surface that performed it (the card's own "Saved as ..." state), and a region that also
 * rendered a toast would be two places claiming to speak for the app.
 */
export function Announcer() {
  const message = useAppStore((s) => s.announcedMessage)
  const clear = useAppStore((s) => s.clearAnnouncedMessage)

  useEffect(() => {
    if (!message) return
    const timer = window.setTimeout(clear, ANNOUNCE_MS)
    return () => window.clearTimeout(timer)
  }, [message, clear])

  return (
    <div
      data-testid="announcer"
      role="status"
      aria-live="polite"
      aria-atomic="true"
      className="sr-only"
    >
      {message ?? ''}
    </div>
  )
}
