// A media clock that runs at display rate (B-P2, fixes audit A2).
//
// The browser fires `timeupdate` about four times a second. Anything driven by it -- a
// playhead, a meter, a scrolling cursor -- steps visibly, which is the difference between a
// plugin and a web page. This reads `currentTime` from the element once per animation frame
// instead, and hands the value to subscribers directly: **no React state per frame**, because
// a commit per frame is exactly the cost the doctrine forbids.
//
// Subscribers write to canvas or to DOM nodes. If a value must also be readable by React
// (a label that says "1.2s"), it belongs in the coarse state the component already has, not
// in this stream.
import { useEffect, useRef, type RefObject } from 'react'

export interface MediaClock {
  /** Called with the element's current time on every animation frame while the clock runs.
   * Returns an unsubscribe function. */
  subscribe(callback: (seconds: number) => void): () => void
  /** One-shot read, for positioning a paused playhead without waiting a frame. */
  read(): number
}

/**
 * `active` should be true only while the media is actually advancing (i.e. `!paused`): an
 * idle page must not run a RAF loop forever.
 */
export function useMediaClock(
  mediaRef: RefObject<HTMLMediaElement | null>,
  active: boolean,
): MediaClock {
  const subscribersRef = useRef(new Set<(seconds: number) => void>())

  const clockRef = useRef<MediaClock | null>(null)
  if (clockRef.current === null) {
    clockRef.current = {
      subscribe: (callback) => {
        subscribersRef.current.add(callback)
        return () => {
          subscribersRef.current.delete(callback)
        }
      },
      read: () => mediaRef.current?.currentTime ?? 0,
    }
  }

  useEffect(() => {
    if (!active) return
    let frame = 0
    const tick = () => {
      const media = mediaRef.current
      if (media) {
        const seconds = media.currentTime
        for (const callback of subscribersRef.current) callback(seconds)
      }
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [active, mediaRef])

  return clockRef.current
}
