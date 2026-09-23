// The one source of every *signal* color (plan B, doctrine "two color roles").
//
// Signal is not the theme accent. Accent (--primary, four themes) is selection, focus, chrome
// glow and the CTA. Signal is waveforms, meters, the spectrogram and the playhead, and it
// never re-skins: like a plugin whose analyzer stays readable under any skin. This module is
// the fixed palette chosen at CP0b (D9 = the S-c hybrid: the hero's electric blue -> violet ->
// pale lavender ramp), so a theme change can never move a meter's meaning.
//
// Values are verbatim from the plan (B P1 "Signal constants"), which were verified on the
// look-dev signal board.

/** Ramp stops as `[t, L, C, H]`: electric blue -> violet -> hot magenta -> near-white.
 * Interpolated per channel. */
export const SIGNAL_RAMP: ReadonlyArray<readonly [number, number, number, number]> = [
  [0, 0.72, 0.13, 235],
  [0.45, 0.64, 0.22, 285],
  [0.8, 0.7, 0.21, 332],
  [1, 0.95, 0.04, 330],
]

/** The playhead is the one warm thing in the signal language -- amber against a cool ramp. */
export const SIGNAL_PLAYHEAD = 'hsl(38 95% 62%)'

/** Spectrogram color stops, evenly spaced across the dB window. */
export const SPECTRO_STOPS: readonly string[] = [
  '#05040f',
  'oklch(0.26 0.1 275)',
  'oklch(0.58 0.16 245)',
  'oklch(0.62 0.23 290)',
  'oklch(0.7 0.22 335)',
  'oklch(0.97 0.03 330)',
]

/** Spectrogram dynamic range, in dBFS. */
export const SPECTRO_FLOOR_DB = -72
export const SPECTRO_CEIL_DB = -12

/** Meter scale. `CLIP_DBFS` is where the clip indicator latches. */
export const METER_FLOOR_DB = -60
export const METER_CEIL_DB = 0
export const METER_TICKS: readonly number[] = [-48, -36, -24, -18, -12, -6, -3, 0]
export const CLIP_DBFS = -0.1

const clamp01 = (value: number) => (value < 0 ? 0 : value > 1 ? 1 : value)

function rampAt(t: number): readonly [number, number, number] {
  const clamped = clamp01(t)
  for (let i = 1; i < SIGNAL_RAMP.length; i++) {
    const [stopT, stopL, stopC, stopH] = SIGNAL_RAMP[i]
    if (clamped <= stopT) {
      const [prevT, prevL, prevC, prevH] = SIGNAL_RAMP[i - 1]
      const span = stopT - prevT
      const k = span <= 0 ? 0 : (clamped - prevT) / span
      return [prevL + (stopL - prevL) * k, prevC + (stopC - prevC) * k, prevH + (stopH - prevH) * k]
    }
  }
  const [, lastL, lastC, lastH] = SIGNAL_RAMP[SIGNAL_RAMP.length - 1]
  return [lastL, lastC, lastH]
}

const fmt = (value: number) => value.toFixed(3).replace(/0+$/, '').replace(/\.$/, '')

/** Color for one signal sample at intensity `t` in [0, 1]. `played` is the brighter, more
 * saturated "already heard" state; unplayed drops lightness and chroma so the heard/unheard
 * boundary is legible without a second hue. */
export function signalColor(t: number, played = false): string {
  const [light, chroma, hue] = rampAt(t)
  if (played) {
    return `oklch(${fmt(light)} ${fmt(chroma)} ${fmt(hue)} / ${fmt(0.6 + 0.4 * clamp01(t))})`
  }
  return `oklch(${fmt(light - 0.2)} ${fmt(chroma * 0.6)} ${fmt(hue)} / ${fmt(0.32 + 0.2 * clamp01(t))})`
}

/** Intensity for a sample amplitude, in [0, 1] -- dBFS, never linear.
 *
 * Linear amplitude spends almost all of its range on material nobody hears: speech peaking at
 * -6 dBFS is 0.5 linear, so a linear ramp leaves the hot end of the palette permanently
 * unreached and every waveform reads mid-scale. This maps -48 dBFS to 0 and 0 dBFS to 1. */
export function heat(amplitude: number): number {
  const amp = Math.abs(amplitude)
  if (amp <= 0) return 0
  return clamp01((20 * Math.log10(amp) + 48) / 48)
}
