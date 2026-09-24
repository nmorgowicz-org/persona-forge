// STFT worker (B-P3).
//
// The spectrogram is the one visualization that can freeze a page: a 30 s mono clip at 24 kHz
// is ~2.8k frames of a 1024-point FFT. It runs here, off the main thread, so a long task never
// lands while the user is dragging a handle. No dependency: a radix-2 Cooley-Tukey FFT is
// about forty lines and avoids pulling a DSP library into the bundle.
//
// Protocol: post `{ samples, sampleRate, windowSize, hop }` (samples transferred), receive
// `{ magnitudes, frames, bins, ... }` (transferred back).

// A module worker's own global scope. Declared rather than asserted: the app compiles with the
// DOM lib, where `self` is a Window whose postMessage takes a targetOrigin, not a transfer list.
declare const self: {
  onmessage: ((event: MessageEvent<StftRequest>) => void) | null
  postMessage(message: unknown, transfer?: Transferable[]): void
}

interface LoudnessRequest {
  requestId: number
  kind: 'loudness'
  samples: Float32Array
  sampleRate: number
}

interface StftRequest {
  requestId: number
  kind?: 'stft'
  samples: Float32Array
  sampleRate: number
  windowSize: number
  hop: number
}

/** In-place iterative radix-2 FFT. `re`/`im` must be power-of-two length. */
function fft(re: Float64Array, im: Float64Array): void {
  const n = re.length
  // Bit-reversal permutation.
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1
    for (; j & bit; bit >>= 1) j ^= bit
    j ^= bit
    if (i < j) {
      ;[re[i], re[j]] = [re[j], re[i]]
      ;[im[i], im[j]] = [im[j], im[i]]
    }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const angle = (-2 * Math.PI) / len
    const wRe = Math.cos(angle)
    const wIm = Math.sin(angle)
    for (let i = 0; i < n; i += len) {
      let curRe = 1
      let curIm = 0
      for (let k = 0; k < len / 2; k++) {
        const uRe = re[i + k]
        const uIm = im[i + k]
        const vRe = re[i + k + len / 2] * curRe - im[i + k + len / 2] * curIm
        const vIm = re[i + k + len / 2] * curIm + im[i + k + len / 2] * curRe
        re[i + k] = uRe + vRe
        im[i + k] = uIm + vIm
        re[i + k + len / 2] = uRe - vRe
        im[i + k + len / 2] = uIm - vIm
        const nextRe = curRe * wRe - curIm * wIm
        curIm = curRe * wIm + curIm * wRe
        curRe = nextRe
      }
    }
  }
}

export interface LoudnessResult {
  peakDbfs: number
  rmsDbfs: number
  /** Integrated loudness, ITU-R BS.1770-4. -Infinity when the whole clip is below the gate. */
  lufs: number
}

/** K-weighting: the two filters BS.1770 specifies, designed for the actual sample rate. The
 * published parameter values are the standard's own, not a fit. */
function kWeighting(sampleRate: number): { b: number[]; a: number[] }[] {
  const shelfF0 = 1681.974450955533
  const shelfGainDb = 3.999843853973347
  const shelfQ = 0.7071752369554196
  const shelfK = Math.tan((Math.PI * shelfF0) / sampleRate)
  const vh = 10 ** (shelfGainDb / 20)
  const vb = vh ** 0.4996667741545416
  const shelfA0 = 1 + shelfK / shelfQ + shelfK * shelfK
  const shelf = {
    b: [
      (vh + (vb * shelfK) / shelfQ + shelfK * shelfK) / shelfA0,
      (2 * (shelfK * shelfK - vh)) / shelfA0,
      (vh - (vb * shelfK) / shelfQ + shelfK * shelfK) / shelfA0,
    ],
    a: [1, (2 * (shelfK * shelfK - 1)) / shelfA0, (1 - shelfK / shelfQ + shelfK * shelfK) / shelfA0],
  }

  const hpF0 = 38.13547087602444
  const hpQ = 0.5003270373238773
  const hpK = Math.tan((Math.PI * hpF0) / sampleRate)
  const hpA0 = 1 + hpK / hpQ + hpK * hpK
  const highPass = {
    b: [1, -2, 1],
    a: [1, (2 * (hpK * hpK - 1)) / hpA0, (1 - hpK / hpQ + hpK * hpK) / hpA0],
  }

  return [shelf, highPass]
}

function biquad(input: Float32Array, coefficients: { b: number[]; a: number[] }): Float32Array {
  const { b, a } = coefficients
  const out = new Float32Array(input.length)
  let x1 = 0
  let x2 = 0
  let y1 = 0
  let y2 = 0
  for (let i = 0; i < input.length; i++) {
    const x0 = input[i]
    const y0 = b[0] * x0 + b[1] * x1 + b[2] * x2 - a[1] * y1 - a[2] * y2
    out[i] = y0
    x2 = x1
    x1 = x0
    y2 = y1
    y1 = y0
  }
  return out
}

/** ITU-R BS.1770-4 integrated loudness for one channel. */
function integratedLufs(samples: Float32Array, sampleRate: number): number {
  const [shelf, highPass] = kWeighting(sampleRate)
  const weighted = biquad(biquad(samples, shelf), highPass)

  const blockSamples = Math.max(1, Math.round(sampleRate * 0.4))
  const hopSamples = Math.max(1, Math.round(blockSamples / 4))
  if (weighted.length < blockSamples) return -Infinity

  const loudness: number[] = []
  const powers: number[] = []
  for (let start = 0; start + blockSamples <= weighted.length; start += hopSamples) {
    let sum = 0
    for (let i = start; i < start + blockSamples; i++) sum += weighted[i] * weighted[i]
    const power = sum / blockSamples
    powers.push(power)
    loudness.push(-0.691 + 10 * Math.log10(Math.max(power, Number.MIN_VALUE)))
  }

  // Absolute gate at -70 LUFS, then the relative gate 10 LU below the mean of what survived.
  const above = (threshold: number) => powers.filter((_, index) => loudness[index] > threshold)
  const absolute = above(-70)
  if (absolute.length === 0) return -Infinity
  const meanAbsolute = absolute.reduce((total, value) => total + value, 0) / absolute.length
  const relativeThreshold = -0.691 + 10 * Math.log10(Math.max(meanAbsolute, Number.MIN_VALUE)) - 10
  const relative = above(relativeThreshold)
  const gated = relative.length > 0 ? relative : absolute
  const mean = gated.reduce((total, value) => total + value, 0) / gated.length
  return -0.691 + 10 * Math.log10(Math.max(mean, Number.MIN_VALUE))
}

function measureLoudness(samples: Float32Array, sampleRate: number): LoudnessResult {
  let peak = 0
  let sumSquares = 0
  for (let i = 0; i < samples.length; i++) {
    const abs = Math.abs(samples[i])
    if (abs > peak) peak = abs
    sumSquares += samples[i] * samples[i]
  }
  return {
    peakDbfs: peak > 0 ? 20 * Math.log10(peak) : -Infinity,
    rmsDbfs: samples.length > 0 && sumSquares > 0 ? 10 * Math.log10(sumSquares / samples.length) : -Infinity,
    lufs: integratedLufs(samples, sampleRate),
  }
}

self.onmessage = (event: MessageEvent<StftRequest | LoudnessRequest>) => {
  if (event.data.kind === 'loudness') {
    const { requestId, samples, sampleRate } = event.data
    const result = { requestId, ...measureLoudness(samples, sampleRate) }
    self.postMessage(result)
    return
  }
  const { requestId, samples, sampleRate, windowSize, hop } = event.data as StftRequest
  const n = windowSize
  const bins = n / 2 + 1
  const frames = samples.length >= n ? Math.floor((samples.length - n) / hop) + 1 : 0

  // Hann window, precomputed once.
  const window = new Float64Array(n)
  for (let i = 0; i < n; i++) window[i] = 0.5 * (1 - Math.cos((2 * Math.PI * i) / (n - 1)))

  const magnitudes = new Float32Array(frames * bins)
  const re = new Float64Array(n)
  const im = new Float64Array(n)

  for (let frame = 0; frame < frames; frame++) {
    const offset = frame * hop
    for (let i = 0; i < n; i++) {
      re[i] = samples[offset + i] * window[i]
      im[i] = 0
    }
    fft(re, im)
    const base = frame * bins
    for (let bin = 0; bin < bins; bin++) {
      // Single-sided amplitude: normalize by the window's coherent gain so a full-scale sine
      // reads 0 dBFS rather than 0.5 (the Hann sum halves the amplitude).
      const magnitude = Math.hypot(re[bin], im[bin]) / (n * 0.25)
      magnitudes[base + bin] = magnitude
    }
  }

  const result = {
    requestId,
    magnitudes,
    frames,
    bins,
    sampleRate,
    windowSize: n,
    hop,
    durationMs: Math.round((samples.length / sampleRate) * 1000),
  }
  self.postMessage(result, [magnitudes.buffer])
}
