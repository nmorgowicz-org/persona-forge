// Motion tokens (plan B P1). Named, not ad-hoc: every animation in the app picks one of
// these so the same gesture reads the same everywhere, and so a phase that changes "how the
// app moves" changes it in one place.
//
// Mirrored as CSS custom properties in `index.css` (`--motion-*`, `--ease-*`) for transitions
// that never touch React. Keep the two in step; the names are the contract.
import { useEffect, useState } from 'react'

/** Durations in seconds, for `motion/react`. */
export const DURATION = {
  /** Feedback the user caused: hover, press, toggle. Fast enough to feel like a reaction. */
  snap: 0.12,
  /** A control settling into a new value. */
  settle: 0.24,
  /** A panel or page-scale change, where the eye needs to follow. */
  drift: 0.4,
} as const

/** Easing curves, for `motion/react` and CSS. */
export const EASE = {
  /** Leaves immediately, arrives softly -- default for anything the user triggered. */
  snappy: [0.2, 0.8, 0.2, 1] as const,
  /** Symmetric, for state changes that are not direct responses. */
  settle: [0.4, 0, 0.2, 1] as const,
  /** Linear, for continuous motion (a level falling, a cursor sweeping). */
  linear: [0, 0, 1, 1] as const,
} as const

/** Springs, for values that should overshoot slightly and come to rest. */
export const SPRING = {
  snappy: { type: 'spring', stiffness: 520, damping: 34, mass: 0.7 },
  settle: { type: 'spring', stiffness: 260, damping: 30, mass: 1 },
  /** Meter ballistics: fast attack, eased release, no overshoot on the way down. */
  meterFall: { type: 'spring', stiffness: 120, damping: 26, mass: 1.1 },
} as const

/** The named transitions the UI should reach for, rather than raw numbers. */
export const MOTION = {
  /** Hover/press feedback. */
  snappy: { duration: DURATION.snap, ease: EASE.snappy },
  /** A value or panel settling. */
  settle: { duration: DURATION.settle, ease: EASE.settle },
  /** Page-scale change. */
  drift: { duration: DURATION.drift, ease: EASE.settle },
  /** Meter release. */
  meterFall: SPRING.meterFall,
} as const

/** CSS mirror of the durations and easings above, for transitions that never touch React. */
export const MOTION_CSS_VARS = {
  '--motion-snap': `${DURATION.snap}s`,
  '--motion-settle': `${DURATION.settle}s`,
  '--motion-drift': `${DURATION.drift}s`,
  '--ease-snappy': 'cubic-bezier(0.2, 0.8, 0.2, 1)',
  '--ease-settle': 'cubic-bezier(0.4, 0, 0.2, 1)',
} as const

/** `useReducedMotion` that is safe before hydration and under SSR: starts `false` (motion
 * allowed) and corrects on the first effect, so nothing renders differently on the server than
 * on the first client paint. Every animation still needs a static end-state under this flag --
 * reduced motion removes the travel, never the information. */
export function useReducedMotionSafe(): boolean {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    setReduced(query.matches)
    const onChange = (event: MediaQueryListEvent) => setReduced(event.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])
  return reduced
}
