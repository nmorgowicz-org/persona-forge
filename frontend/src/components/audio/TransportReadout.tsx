// What the transport coordinator currently holds, rendered for reading (plan A / T1).
//
// The position changes every animation frame, so this writes to the DOM imperatively and
// never through React state -- the same discipline as the timeline playhead. It is the
// screen-reader-visible answer to "what is audible right now", and the observable the
// transport spec asserts on.
import { useEffect, useRef } from 'react'
import { getTransportState, subscribeTransport, type TransportState } from '@/lib/audioTransport'

const seconds = (value: number | null) => (value == null ? '' : value.toFixed(3))

export function TransportReadout() {
  const ref = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const write = (state: TransportState) => {
      el.dataset.source = state.activeId ?? ''
      el.dataset.sourceKind = state.activeKind ?? ''
      el.dataset.sourceLabel = state.activeLabel ?? ''
      el.dataset.sources = state.sources.join(',')
      el.dataset.positionSec = seconds(state.positionSec)
      el.dataset.durationSec = seconds(state.durationSec)
      el.textContent = state.activeLabel
        ? `${state.activeLabel} at ${(state.positionSec ?? 0).toFixed(2)}s`
        : 'Nothing playing'
    }
    write(getTransportState())
    return subscribeTransport(write)
  }, [])

  return <div ref={ref} data-testid="transport-active-source" className="sr-only" aria-live="off" />
}
