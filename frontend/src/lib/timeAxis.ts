// Shared time-axis math (locked contract: docs/archive/stitch-studio/20260920-stitch_studio_ux_execution_plan.md
// "Time-axis contract"). Every ruler in the app -- Waveform.tsx, waveform/TimeRuler.tsx, and
// Stitch Timeline's top ruler -- computes tick spacing and labels through this module so their
// "nice number" step choice and time formatting cannot drift into three different dialects.

export interface TimeTick {
  seconds: number
  x: number
  label: string
}

/** One display grammar for every millisecond-valued control (clip trim/fade, seam gaps):
 * below a second the number is shown in whole milliseconds, at or above a second it is
 * shown in seconds with trailing zeros stripped. The number and its unit are returned
 * separately so a control can keep the number itself machine-readable (tests, aria) while
 * still showing the unit -- see `parseGapText` for the matching input grammar, which
 * accepts a bare number, `ms`, or `s`. */
export function formatMsValue(ms: number): { text: string; unit: 'ms' | 's' } {
  if (!isFinite(ms)) return { text: '0', unit: 'ms' }
  const rounded = Math.round(ms)
  if (Math.abs(rounded) < 1000) return { text: String(rounded), unit: 'ms' }
  return { text: String(Number((rounded / 1000).toFixed(3))), unit: 's' }
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
 * longer durations switch to m:ss so labels stay compact at any scale. When the tick step is
 * sub-second, the m:ss form keeps a tenths-of-a-second digit so adjacent ticks (less than a
 * second apart) never collapse into identical labels. */
export function formatTimelineTime(seconds: number, stepSeconds = 1): string {
  if (!isFinite(seconds) || seconds < 0) return '0.0s'
  if (seconds < 10) return `${seconds.toFixed(1)}s`
  if (stepSeconds >= 1) {
    const m = Math.floor(seconds / 60)
    const s = Math.floor(seconds % 60)
    return `${m}:${s.toString().padStart(2, '0')}`
  }
  // Sub-second steps: round to integer tenths first so float wobble (3 * 0.1 =
  // 0.30000000000000004) can't mislabel a tick, and the carry rolls into the minutes.
  const tenths = Math.round(seconds * 10)
  const m = Math.floor(tenths / 600)
  const sWhole = Math.floor((tenths % 600) / 10)
  const d = tenths % 10
  return `${m}:${sWhole.toString().padStart(2, '0')}.${d}`
}

/** One hover readout grammar for every waveform surface. Delegates to `formatTimelineTime`
 * with the same "nice" step the ruler above the surface uses, so the readout under the
 * pointer and the tick labels around it cannot drift into two dialects. */
export function formatHoverTime(seconds: number, pixelsPerSecond: number): string {
  if (!isFinite(seconds)) return '0.0s'
  const pps = isFinite(pixelsPerSecond) && pixelsPerSecond > 0 ? pixelsPerSecond : 1
  return formatTimelineTime(Math.max(0, seconds), niceTimeStep(1 / pps))
}

/** Builds evenly-spaced ticks from 0 through `durationSeconds`, choosing a "nice" step so
 * labels don't collide. Grid ticks stop strictly before the exact duration; the final tick is
 * always appended at exactly `durationSeconds`, dropping any last grid tick whose label would
 * be identical to it or that sits within a label-width of it. */
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
  // Index-based so float error doesn't accumulate across iterations. The epsilon only absorbs
  // float noise, so grid ticks stay strictly below the exact duration and can never overshoot
  // it and replace the exact-duration label.
  const epsilon = 1e-9
  for (let k = 0; ; k++) {
    const seconds = k * step
    if (seconds >= durationSeconds - epsilon) break
    ticks.push({ seconds, x: seconds * pixelsPerSecond, label: formatTimelineTime(seconds, step) })
  }

  const finalTick: TimeTick = {
    seconds: durationSeconds,
    x: durationSeconds * pixelsPerSecond,
    label: formatTimelineTime(durationSeconds, step),
  }
  // Drop the last grid ticks that would collide with the final one: identical labels, or
  // closer than the widest rendered label (~6 mono chars at 10px), so the right edge never
  // shows two equal labels or a crowding pair.
  const MIN_FINAL_TICK_GAP_PX = 36
  while (ticks.length > 0) {
    const last = ticks[ticks.length - 1]
    if (last.label !== finalTick.label && finalTick.x - last.x >= MIN_FINAL_TICK_GAP_PX) break
    ticks.pop()
  }
  ticks.push(finalTick)

  return ticks
}
