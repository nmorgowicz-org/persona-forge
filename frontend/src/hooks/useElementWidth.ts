import { useCallback, useEffect, useState } from 'react'

/** Tracks an element's content-box width in real CSS pixels via ResizeObserver. Rulers need
 * this so `timeAxis.ts`'s tick-spacing math sees genuine pixels-per-second instead of guessing
 * density from a fixed percentage width -- a ruler at 200px and one at 1000px need different
 * tick counts to stay readable.
 *
 * Returns a callback ref (not a plain `useRef`): several callers attach this ref to an element
 * that mounts conditionally after the hook itself, and a plain ref's effect (empty deps) would
 * run once before that element exists and never re-run once it does. */
export function useElementWidth<T extends HTMLElement>(): [(node: T | null) => void, number] {
  const [node, setNode] = useState<T | null>(null)
  const [width, setWidth] = useState(0)
  const ref = useCallback((el: T | null) => setNode(el), [])

  useEffect(() => {
    if (!node) return
    setWidth(node.getBoundingClientRect().width)
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) setWidth(entry.contentRect.width)
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [node])

  return [ref, width]
}
