// One playback model for the whole Stitch Studio arrangement (Packet 7). A single
// HTMLAudioElement is created once and reused for the arrangement toggle, ruler/waveform
// seek, and every per-clip "listen to just this segment" button -- none of those surfaces
// creates its own Audio instance. Playhead-following UI must not read `currentTimeSec` as
// React state (that would re-render the whole tree on every animation frame); instead,
// subscribe to `subscribeTime`, which only runs while playing and calls back via
// requestAnimationFrame so a consumer can push the position straight onto a DOM node's style.
import { useCallback, useEffect, useRef, useState } from 'react'

export interface StitchTransport {
  /** Attach to the single <audio> element that plays the rendered preview. It's a callback
   * ref, not a plain ref object: the element is conditionally rendered (only once the
   * arrangement has clips), so listeners must (re-)attach at the moment it actually mounts
   * rather than once on this hook's own first render, which can run before that element
   * exists at all. */
  audioRef: React.Ref<HTMLAudioElement>
  isPlaying: boolean
  durationSec: number
  /** clipId of the clip whose bounded range is currently playing, or null when playback is
   * either stopped or spans the whole arrangement. Coarse (updated on play/pause/range-end),
   * not per-frame -- safe to read as React state. */
  activeRangeId: string | null
  play(): void
  pause(): void
  toggle(): void
  /** Seeks to an absolute position in the underlying audio element's own seconds. */
  seek(sec: number): void
  /** Plays a bounded [startSec, endSec) range on the shared audio element, tagged with an id
   * so callers can tell whether it's their own range currently active. Calling it again with
   * the same id while that range is already playing pauses instead (toggle semantics). */
  playRange(id: string, startSec: number, endSec: number): void
  /** Runs `cb` on every animation frame while playing, with the audio element's current time
   * in seconds. Returns an unsubscribe function. Never triggers a React re-render. */
  subscribeTime(cb: (sec: number) => void): () => void
  /** One-shot read of the audio element's current time, for initializing a playhead position
   * without waiting for the next frame (e.g. right after a seek while paused). */
  getCurrentTime(): number
}

export function useStitchTransport(src: string | null): StitchTransport {
  const elRef = useRef<HTMLAudioElement | null>(null)
  const [attachTick, setAttachTick] = useState(0)
  const audioRef = useCallback((el: HTMLAudioElement | null) => {
    elRef.current = el
    setAttachTick((t) => t + 1)
  }, [])
  const [isPlaying, setIsPlaying] = useState(false)
  const [durationSec, setDurationSec] = useState(0)
  const [activeRangeId, setActiveRangeId] = useState<string | null>(null)
  const rangeEndRef = useRef<number | null>(null)
  const subscribersRef = useRef<Set<(sec: number) => void>>(new Set())
  const rafRef = useRef<number | null>(null)

  // A new rendered preview replaces the element's `src` (React updates the same <audio>
  // node's attribute rather than remounting it); playback/range state from the previous
  // preview no longer applies to the new audio.
  useEffect(() => {
    setIsPlaying(false)
    setActiveRangeId(null)
    rangeEndRef.current = null
    setDurationSec(0)
  }, [src])

  useEffect(() => {
    const audio = elRef.current
    if (!audio) return
    const onLoadedMetadata = () => setDurationSec(isFinite(audio.duration) ? audio.duration : 0)
    const onPlay = () => setIsPlaying(true)
    const onPause = () => setIsPlaying(false)
    const onEnded = () => {
      setIsPlaying(false)
      setActiveRangeId(null)
      rangeEndRef.current = null
    }
    const onTimeUpdate = () => {
      if (rangeEndRef.current != null && audio.currentTime >= rangeEndRef.current) {
        audio.pause()
        setActiveRangeId(null)
        rangeEndRef.current = null
      }
    }
    audio.addEventListener('loadedmetadata', onLoadedMetadata)
    audio.addEventListener('play', onPlay)
    audio.addEventListener('pause', onPause)
    audio.addEventListener('ended', onEnded)
    audio.addEventListener('timeupdate', onTimeUpdate)
    return () => {
      audio.removeEventListener('loadedmetadata', onLoadedMetadata)
      audio.removeEventListener('play', onPlay)
      audio.removeEventListener('pause', onPause)
      audio.removeEventListener('ended', onEnded)
      audio.removeEventListener('timeupdate', onTimeUpdate)
    }
  }, [attachTick])

  // RAF loop: only scheduled while playing, torn down on pause/unmount. Notifies subscribers
  // directly -- never sets React state, so a scrubbing/playing arrangement never re-renders
  // this hook's owner (or anything else) once per frame.
  useEffect(() => {
    if (!isPlaying) return
    let cancelled = false
    const tick = () => {
      if (cancelled) return
      const audio = elRef.current
      if (audio) {
        for (const cb of subscribersRef.current) cb(audio.currentTime)
      }
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => {
      cancelled = true
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
  }, [isPlaying])

  const subscribeTime = useCallback((cb: (sec: number) => void) => {
    subscribersRef.current.add(cb)
    return () => { subscribersRef.current.delete(cb) }
  }, [])

  const getCurrentTime = useCallback(() => elRef.current?.currentTime ?? 0, [])

  const play = useCallback(() => {
    const audio = elRef.current
    if (!audio) return
    rangeEndRef.current = null
    setActiveRangeId(null)
    void audio.play()
  }, [])

  const pause = useCallback(() => { elRef.current?.pause() }, [])

  const toggle = useCallback(() => {
    const audio = elRef.current
    if (!audio) return
    if (audio.paused) {
      rangeEndRef.current = null
      setActiveRangeId(null)
      void audio.play()
    } else {
      audio.pause()
    }
  }, [])

  const seek = useCallback((sec: number) => {
    const audio = elRef.current
    if (!audio) return
    audio.currentTime = Math.max(0, sec)
    // One-shot notify so a paused playhead moves immediately instead of waiting for the RAF
    // loop, which only runs while playing.
    for (const cb of subscribersRef.current) cb(audio.currentTime)
  }, [])

  const playRange = useCallback((id: string, startSec: number, endSec: number) => {
    const audio = elRef.current
    if (!audio) return
    if (activeRangeId === id && !audio.paused) {
      audio.pause()
      setActiveRangeId(null)
      rangeEndRef.current = null
      return
    }
    audio.currentTime = Math.max(0, startSec)
    rangeEndRef.current = endSec
    setActiveRangeId(id)
    void audio.play()
  }, [activeRangeId])

  return {
    audioRef,
    isPlaying,
    durationSec,
    activeRangeId,
    play,
    pause,
    toggle,
    seek,
    playRange,
    subscribeTime,
    getCurrentTime,
  }
}
