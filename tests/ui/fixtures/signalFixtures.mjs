// Deterministic audio fixtures for signal-truth tests (B-P2).
//
// A waveform test that uses whatever audio happens to be lying around cannot assert anything
// about *level*: the whole point of the true-scale renderer is that a quieter clip draws
// shorter, so the fixtures have to be generated at known amplitudes. These write 16-bit PCM
// WAVs, the format the app decodes everywhere else.

const SAMPLE_RATE = 24000

/** Amplitude for a dBFS level. -6 dBFS -> 0.501, -24 dBFS -> 0.063. */
export function amplitudeFor(dbfs) {
  return 10 ** (dbfs / 20)
}

function writeWav(samples, sampleRate = SAMPLE_RATE) {
  const dataBytes = samples.length * 2
  const buffer = Buffer.alloc(44 + dataBytes)
  buffer.write('RIFF', 0, 'ascii')
  buffer.writeUInt32LE(36 + dataBytes, 4)
  buffer.write('WAVE', 8, 'ascii')
  buffer.write('fmt ', 12, 'ascii')
  buffer.writeUInt32LE(16, 16) // PCM header size
  buffer.writeUInt16LE(1, 20) // PCM
  buffer.writeUInt16LE(1, 22) // mono
  buffer.writeUInt32LE(sampleRate, 24)
  buffer.writeUInt32LE(sampleRate * 2, 28) // byte rate
  buffer.writeUInt16LE(2, 32) // block align
  buffer.writeUInt16LE(16, 34) // bits per sample
  buffer.write('data', 36, 'ascii')
  buffer.writeUInt32LE(dataBytes, 40)
  for (let i = 0; i < samples.length; i++) {
    const clamped = Math.max(-1, Math.min(1, samples[i]))
    buffer.writeInt16LE(Math.round(clamped * 32767), 44 + i * 2)
  }
  return buffer
}

/** A steady sine at a known level. */
export function sineWav({ hz = 440, dbfs = -6, seconds = 2, sampleRate = SAMPLE_RATE } = {}) {
  const count = Math.max(1, Math.round(seconds * sampleRate))
  const amplitude = amplitudeFor(dbfs)
  const samples = new Float32Array(count)
  for (let i = 0; i < count; i++) {
    samples[i] = amplitude * Math.sin((2 * Math.PI * hz * i) / sampleRate)
  }
  return writeWav(samples, sampleRate)
}

/** A single-sample impulse at a known level: the honest way to pin a peak without a tone. */
export function impulseWav({ dbfs = 0, seconds = 0.5, sampleRate = SAMPLE_RATE } = {}) {
  const count = Math.max(1, Math.round(seconds * sampleRate))
  const samples = new Float32Array(count)
  samples[Math.floor(count / 2)] = amplitudeFor(dbfs)
  return writeWav(samples, sampleRate)
}
