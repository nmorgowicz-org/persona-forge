// One audio source per mounted surface (plan A / T1).
//
// Registers with the transport coordinator on first render and disposes on unmount, so the
// coordinator's registry is exactly "the audio surfaces that exist right now". The returned
// object is stable for the lifetime of the mount, which matters because the callers install
// its `claim` callback into media-element event handlers.
import { useEffect, useRef } from 'react'
import { registerSource, type AudioSource } from '@/lib/audioTransport'

export function useAudioSource(kind: string, label: string): AudioSource {
  const ref = useRef<AudioSource | null>(null)
  // Lazy init in render rather than an effect: the element handlers below can fire before
  // effects flush (a deck autoplays on mount), and a claim must not find a missing source.
  if (ref.current === null) ref.current = registerSource(kind, label)
  useEffect(() => {
    const source = ref.current
    return () => {
      source?.dispose()
      ref.current = null
    }
  }, [])
  return ref.current
}
