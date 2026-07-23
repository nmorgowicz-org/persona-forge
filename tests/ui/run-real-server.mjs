// Spawns the real backend (Flask dev server, D1) on disposable temp voice/segment library
// dirs and blocks until the model has finished loading. Used by real-mode capture (Phase B).
// See docs/dev/resolved/E2E_AND_SCREENSHOTTING.md; docs/plans/20260720-post_merge_initiatives.md Phase B1.
import { spawn } from 'node:child_process'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { resolvePython } from './lib/python.mjs'
import { seedCaptureFixtures } from './lib/seed.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = join(__dirname, '..', '..')

export function startRealServer({
  port = 8319,
  voiceLibraryDir,
  segmentLibraryDir,
  modelSize = '0.6B',
  device = 'cpu',
  timeoutMs = 120000,
  seedFixtures = true,
} = {}) {
  voiceLibraryDir ??= mkdtempSync(join(tmpdir(), 'qwen3-tts-capture-voices-'))
  segmentLibraryDir ??= mkdtempSync(join(tmpdir(), 'qwen3-tts-capture-segments-'))

  if (seedFixtures) seedCaptureFixtures(voiceLibraryDir, segmentLibraryDir)

  const env = {
    ...process.env,
    PYTHONPATH: [REPO_ROOT, join(REPO_ROOT, 'src'), join(REPO_ROOT, 'src', 'export')].join(
      process.platform === 'win32' ? ';' : ':'
    ),
    TTS_BACKEND: 'pytorch',
    DEVICE: device,
    MODEL_SIZE: modelSize,
    VOICE_LIBRARY_DIR: voiceLibraryDir,
    SEGMENT_LIBRARY_DIR: segmentLibraryDir,
    FRONTEND_DIST_DIR: join(REPO_ROOT, 'frontend', 'dist'),
    FRONTEND_ENABLED: '1',
    IDLE_UNLOAD_SECONDS: '0',
  }
  if (!process.env.HF_TOKEN) delete env.HF_TOKEN

  const python = resolvePython()
  const child = spawn(
    python,
    ['-c', `from qwen3_tts.app import app; app.run(host='127.0.0.1', port=${port}, threaded=True)`],
    { env, stdio: 'inherit' }
  )

  child.on('error', (err) => {
    console.error(`[run-real-server] spawn failed for python=${python}: ${err.message}`)
    process.exit(1)
  })
  child.on('close', (code) => {
    if (code !== 0 && code !== null) {
      console.error(`[run-real-server] app exited with code ${code}`)
      process.exit(code || 1)
    }
  })

  const url = `http://127.0.0.1:${port}`

  async function waitUntilHealthy(waitMs = timeoutMs) {
    const deadline = Date.now() + waitMs
    let lastBody = null
    while (Date.now() < deadline) {
      try {
        const res = await fetch(`${url}/health`)
        lastBody = await res.json()
        if (lastBody.model_loaded === true) return
      } catch {
        // not up yet
      }
      await new Promise((r) => setTimeout(r, 500))
    }
    throw new Error(
      `real server did not report model_loaded within ${waitMs}ms; last /health body: ${JSON.stringify(lastBody)}`
    )
  }

  function stop() {
    child.kill('SIGTERM')
    setTimeout(() => {
      if (!child.killed) child.kill('SIGKILL')
    }, 3000)
  }

  process.on('exit', stop)
  process.on('SIGINT', () => {
    stop()
    process.exit(0)
  })
  process.on('SIGTERM', () => {
    stop()
    process.exit(0)
  })

  return { child, url, port, voiceLibraryDir, segmentLibraryDir, waitUntilHealthy, stop }
}

// Allow running directly: `node tests/ui/run-real-server.mjs [port]`
if (import.meta.url === `file://${process.argv[1]}`) {
  const port = Number(process.argv[2]) || 8319
  const server = startRealServer({ port })
  server
    .waitUntilHealthy()
    .then(() => {
      console.log(`[run-real-server] healthy at ${server.url}`)
      console.log(`[run-real-server] voice library: ${server.voiceLibraryDir}`)
      console.log(`[run-real-server] segment library: ${server.segmentLibraryDir}`)
    })
    .catch((err) => {
      console.error(err)
      process.exit(1)
    })
}
