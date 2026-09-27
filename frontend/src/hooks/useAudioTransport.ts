// One audio source per mounted surface (plan A / T1).
//
// Registers after commit and disposes on unmount, so the coordinator's registry follows the
// mounted audio surfaces without creating external state during render. The stable proxy
// lazily registers if an autoplay/claim event arrives before effects flush.
// Its stable `claim` callback can be installed into media-element handlers during render.
import { useCallback, useEffect, useMemo, useRef } from 'react'
import { registerSource, type AudioSource } from '@/lib/audioTransport'

export function useAudioSource(kind: string, label: string): AudioSource {
  const sourceRef = useRef<AudioSource | null>(null)
  const ensureSource = useCallback(() => {
    if (!sourceRef.current) sourceRef.current = registerSource(kind, label)
    return sourceRef.current
  }, [kind, label])
  const source = useMemo<AudioSource>(() => ({
    get id() { return sourceRef.current?.id ?? '' },
    kind,
    label,
    claim: (pause) => ensureSource().claim(pause),
    release: () => sourceRef.current?.release(),
    report: (position, duration) => sourceRef.current?.report(position, duration),
    dispose: () => {
      sourceRef.current?.dispose()
      sourceRef.current = null
    },
  }), [ensureSource, kind, label])
  useEffect(() => {
    ensureSource()
    return () => {
      sourceRef.current?.dispose()
      sourceRef.current = null
    }
  }, [ensureSource])
  return source
}
