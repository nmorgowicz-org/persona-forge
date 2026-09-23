// One playback model for the whole Stitch Studio arrangement (Packet 7). A single
// HTMLAudioElement is created once and reused for the arrangement toggle, ruler/waveform
// seek, and every per-clip "listen to just this segment" button -- none of those surfaces
// creates its own Audio instance. Playhead-following UI must not read `currentTimeSec` as
// React state (that would re-render the whole tree on every animation frame); instead,
// subscribe to `subscribeTime`, which only runs while playing and calls back via
// requestAnimationFrame so a consumer can push the position straight onto a DOM node's style.
import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { claimPlayback, releasePlayback } from '@/lib/playbackFocus'

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
  /** The active arrangement loop, in this element's own seconds, or null. Arrangement
   * seconds differ from these by `previewScale`, so the caller converts. */
  loopRange: { startSec: number; endSec: number } | null
  /** Sets or clears the arrangement loop. While one is set, arrangement playback wraps back
   * to its start instead of running past its end; a bounded clip range still plays to its own
   * end untouched. */
  setLoopRange(range: { startSec: number; endSec: number } | null): void
  /** Runs `cb` on every animation frame while playing, with the audio element's current time
   * in seconds. Returns an unsubscribe function. Never triggers a React re-render. */
  subscribeTime(cb: (sec: number) => void): () => void
  /** One-shot read of the audio element's current time, for initializing a playhead position
   * without waiting for the next frame (e.g. right after a seek while paused). */
  getCurrentTime(): number
}

/** Shortest bounded range worth playing. Anything below this is a clip whose duration is not
 * known yet, not a range the user asked to hear. */
const MIN_RANGE_SEC = 0.05

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
  const [loopRange, setLoopRangeState] = useState<{ startSec: number; endSec: number } | null>(null)
  const loopRef = useRef(loopRange)
  loopRef.current = loopRange
  const rangeEndRef = useRef<number | null>(null)
  // Playback focus (N6): this element is one audio owner among several; whoever starts
  // sounding takes the focus and stops the previous owner.
  const focusId = useId()
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
    const onPlay = () => {
      setIsPlaying(true)
      // One claim per owner, at the single place a transport can start sounding (arrangement
      // playback, a bounded clip range, or a programmatic play) -- see lib/playbackFocus.ts.
      claimPlayback(focusId, () => audio.pause())
    }
    const onPause = () => {
      setIsPlaying(false)
      releasePlayback(focusId)
    }
    const onEnded = () => {
      setIsPlaying(false)
      setActiveRangeId(null)
      rangeEndRef.current = null
      releasePlayback(focusId)
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
      // Pause before detaching: this cleanup also runs when the element unmounts (leaving the
      // studio), and an in-memory blob URL keeps playing without its DOM node. The captured
      // element is still a live object once detached, so pause() works and can't throw.
      audio.pause()
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
        // The arrangement loop wraps here rather than in 'timeupdate': that event fires a few
        // times a second, which would let playback audibly overshoot the brace end. A bounded
        // clip range owns its own end (rangeEndRef), so the loop leaves it alone.
        const loop = loopRef.current
        if (loop && rangeEndRef.current == null && audio.currentTime >= loop.endSec) {
          audio.currentTime = loop.startSec
          // Notify immediately: otherwise the playhead paints one more frame past the brace.
          for (const cb of subscribersRef.current) cb(audio.currentTime)
        }
        // Clamp at the exact audio duration: on the final frames before 'ended', currentTime
        // can overshoot it, which would push the playhead past the exact-duration tick.
        const t = durationSec > 0 ? Math.min(audio.currentTime, durationSec) : audio.currentTime
        for (const cb of subscribersRef.current) cb(t)
      }
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => {
      cancelled = true
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
  }, [isPlaying, durationSec])

  const subscribeTime = useCallback((cb: (sec: number) => void) => {
    subscribersRef.current.add(cb)
    return () => { subscribersRef.current.delete(cb) }
  }, [])

  const getCurrentTime = useCallback(() => elRef.current?.currentTime ?? 0, [])

  // With a loop set, starting playback begins at the loop -- a press of Space replays the
  // brace rather than resuming wherever the playhead was parked outside it.
  const seekToLoopStartIfOutside = useCallback(() => {
    const audio = elRef.current
    const loop = loopRef.current
    if (!audio || !loop) return
    if (audio.currentTime < loop.startSec || audio.currentTime >= loop.endSec) {
      audio.currentTime = loop.startSec
      // Notify immediately: the RAF loop only runs while playing.
      for (const cb of subscribersRef.current) cb(audio.currentTime)
    }
  }, [])

  const play = useCallback(() => {
    const audio = elRef.current
    if (!audio) return
    rangeEndRef.current = null
    setActiveRangeId(null)
    seekToLoopStartIfOutside()
    // play() rejects on interrupt (src swap mid-click) or autoplay-policy denial;
    // playback state is event-driven, so the rejection carries no state to recover.
    audio.play().catch(() => {})
  }, [])

  const pause = useCallback(() => { elRef.current?.pause() }, [])

  const toggle = useCallback(() => {
    const audio = elRef.current
    if (!audio) return
    if (audio.paused) {
      rangeEndRef.current = null
      setActiveRangeId(null)
      seekToLoopStartIfOutside()
      audio.play().catch(() => {})
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
    // No element yet (preview still mounting) or no span (a clip whose duration is not known
    // yet): there is nothing to play. Refusing beats starting a range that ends on the next
    // timeupdate, which is what a caller would otherwise hear as a click that did nothing.
    if (!audio || !(endSec - startSec > MIN_RANGE_SEC)) return
    if (activeRangeId === id && !audio.paused) {
      audio.pause()
      setActiveRangeId(null)
      rangeEndRef.current = null
      return
    }
    audio.currentTime = Math.max(0, startSec)
    rangeEndRef.current = endSec
    setActiveRangeId(id)
    audio.play().catch(() => {})
  }, [activeRangeId])

  // Clearing a loop never touches playback; a caller that also wants to stop can pause().
  const setLoopRange = useCallback((range: { startSec: number; endSec: number } | null) => {
    setLoopRangeState(range && range.endSec > range.startSec ? range : null)
  }, [])

  return {
    audioRef,
    isPlaying,
    durationSec,
    activeRangeId,
    loopRange,
    setLoopRange,
    play,
    pause,
    toggle,
    seek,
    playRange,
    subscribeTime,
    getCurrentTime,
  }
}
