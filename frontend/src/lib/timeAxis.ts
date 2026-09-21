// Shared time-axis math (locked contract: docs/archive/stitch-studio/20260920-stitch_studio_ux_execution_plan.md
// "Time-axis contract"). Every ruler in the app -- Waveform.tsx, waveform/TimeRuler.tsx, and
// Stitch Timeline's top ruler -- computes tick spacing and labels through this module so their
// "nice number" step choice and time formatting cannot drift into three different dialects.

export interface TimeTick {
  seconds: number
  x: number
  label: string
}

// A 1-2-5 "nice number" ladder in seconds, covering sub-second waveform zooms through
// hour-scale timelines.
const NICE_SECONDS = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600]

/** Picks the smallest "nice" tick spacing (in seconds) such that consecutive ticks are at
 * least `minimumTickPx` apart given `secondsPerPixel`. `minimumTickPx` is expressed in
 * whatever linear unit the caller's `secondsPerPixel` uses (real CSS px, or a percent-of-width
 * unit) -- the math is scale-free. */
export function niceTimeStep(secondsPerPixel: number, minimumTickPx = 60): number {
  if (!isFinite(secondsPerPixel) || secondsPerPixel <= 0) return NICE_SECONDS[0]
  const minStep = Math.max(0.001, secondsPerPixel * minimumTickPx)
  for (const step of NICE_SECONDS) {
    if (step >= minStep) return step
  }
  // Beyond the table: keep climbing a 1-2-2.5-2 ladder from the largest tabulated step.
  let step = NICE_SECONDS[NICE_SECONDS.length - 1]
  const multipliers = [2, 2.5, 2]
  let i = 0
  while (step < minStep) {
    step *= multipliers[i % multipliers.length]
    i++
  }
  return step
}

/** Formats a duration for ruler labels: short (< 10s) durations get one decimal of seconds;
 * longer durations switch to m:ss so labels stay compact at any scale. */
export function formatTimelineTime(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) return '0.0s'
  if (seconds < 10) return `${seconds.toFixed(1)}s`
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

/** Builds evenly-spaced ticks from 0 through `durationSeconds`, choosing a "nice" step so
 * labels don't collide, and always includes a final tick at the exact duration even if it
 * falls short of the next evenly-spaced step. */
export function createTimeTicks({
  durationSeconds,
  pixelsPerSecond,
  widthPx,
}: {
  durationSeconds: number
  pixelsPerSecond: number
  widthPx: number
}): TimeTick[] {
  if (
    !isFinite(durationSeconds) ||
    durationSeconds <= 0 ||
    !isFinite(pixelsPerSecond) ||
    pixelsPerSecond <= 0 ||
    !isFinite(widthPx) ||
    widthPx <= 0
  ) {
    return []
  }

  const secondsPerPixel = 1 / pixelsPerSecond
  const step = niceTimeStep(secondsPerPixel)
  const ticks: TimeTick[] = []
  for (let seconds = 0; seconds <= durationSeconds + step * 0.02; seconds += step) {
    ticks.push({ seconds, x: seconds * pixelsPerSecond, label: formatTimelineTime(seconds) })
  }

  const last = ticks[ticks.length - 1]
  if (!last || durationSeconds - last.seconds > step * 0.02) {
    ticks.push({
      seconds: durationSeconds,
      x: durationSeconds * pixelsPerSecond,
      label: formatTimelineTime(durationSeconds),
    })
  }

  return ticks
}
