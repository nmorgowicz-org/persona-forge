// Ported from ../../llama-monitor/tests/ui/capture.mjs (captureFrames/framesToGif/cleanupFrames).
// Uses the system ffmpeg binary via execFileSync argument arrays — never a shell string.
import { execFileSync } from 'node:child_process'
import { mkdirSync, rmSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const FRAME_DIR = join(__dirname, '..', 'frames')

// A fixed-cadence background capture loop running concurrently with driveActions' clicks/
// typing/navigation was tried and abandoned: under real model-inference CPU load, page.screenshot()
// can be starved on the renderer's main thread for the ENTIRE duration of a scenario, not just
// during navigation — so no timeout/retry scheme salvages a background loop. A recorder that only
// takes a screenshot when the caller explicitly asks (between driveActions steps, never
// concurrently with one) sidesteps the contention entirely: each snap() happens while the page is
// otherwise idle.
function createRecorder(prefix) {
  mkdirSync(FRAME_DIR, { recursive: true })
  let i = 0
  return {
    async snap(page) {
      const path = join(FRAME_DIR, `${prefix}_${String(i).padStart(3, '0')}.png`)
      await page.screenshot({ path })
      i += 1
    },
    count() {
      return i
    },
  }
}

function framesToGif(prefix, output, fps) {
  execFileSync(
    'ffmpeg',
    [
      '-y',
      '-framerate', String(fps),
      '-i', join(FRAME_DIR, `${prefix}_%03d.png`),
      '-vf',
      'scale=900:-1:flags=lanczos,split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5',
      output,
    ],
    { stdio: 'inherit' }
  )
}

function cleanupFrames() {
  rmSync(FRAME_DIR, { recursive: true, force: true })
}

export { createRecorder, framesToGif, cleanupFrames }
