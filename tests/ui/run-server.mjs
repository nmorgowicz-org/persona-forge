// Spawns the fake-model test server (fixtures/fake_model_server.py) and waits for it to become
// healthy. Used by playwright.config.js's webServer block and by capture.mjs's default mode.
// See docs/plans/20260702-e2e_and_screenshotting.md §3.1/§4.3.
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = join(__dirname, '..', '..')

// Prefer the repo's own .venv (has flask/numpy/soundfile installed) over a bare `python3`,
// which on a fresh dev machine won't have these deps.
function resolvePython() {
  const venvPython = join(REPO_ROOT, '.venv', 'bin', 'python')
  return existsSync(venvPython) ? venvPython : 'python3'
}

export function startFakeServer({ port = 8319 } = {}) {
  const voiceLibraryDir = mkdtempSync(join(tmpdir(), 'qwen3-tts-e2e-voices-'))
  const env = {
    ...process.env,
    PYTHONPATH: join(REPO_ROOT, 'src'),
    VOICE_LIBRARY_DIR: voiceLibraryDir,
    FRONTEND_DIST_DIR: join(REPO_ROOT, 'frontend', 'dist'),
    QWEN3_TTS_TEST_PORT: String(port),
  }

  const child = spawn(resolvePython(), [join(__dirname, 'fixtures', 'fake_model_server.py')], {
    env,
    stdio: 'inherit',
  })

  const url = `http://127.0.0.1:${port}`

  async function waitUntilHealthy(timeoutMs = 15000) {
    const deadline = Date.now() + timeoutMs
    while (Date.now() < deadline) {
      try {
        const res = await fetch(`${url}/health`)
        if (res.ok) return
      } catch {
        // not up yet
      }
      await new Promise((r) => setTimeout(r, 200))
    }
    throw new Error(`fake_model_server did not become healthy within ${timeoutMs}ms`)
  }

  function stop() {
    child.kill('SIGTERM')
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

  return { child, url, port, waitUntilHealthy, stop }
}

// Allow running directly: `node tests/ui/run-server.mjs [port]`
if (import.meta.url === `file://${process.argv[1]}`) {
  const port = Number(process.argv[2]) || 8319
  const server = startFakeServer({ port })
  server
    .waitUntilHealthy()
    .then(() => console.log(`[run-server] healthy at ${server.url}`))
    .catch((err) => {
      console.error(err)
      process.exit(1)
    })
}
