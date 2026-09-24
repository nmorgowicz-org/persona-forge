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

interface StftRequest {
  requestId: number
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

self.onmessage = (event: MessageEvent<StftRequest>) => {
  const { requestId, samples, sampleRate, windowSize, hop } = event.data
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
