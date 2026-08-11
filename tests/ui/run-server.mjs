// Spawns the fake-model test server (fixtures/fake_model_server.py) and waits for it to become
// healthy. Used by playwright.config.js's webServer block and by capture.mjs's default mode.
// See docs/dev/resolved/E2E_AND_SCREENSHOTTING.md §3.1/§4.3.
import { spawn } from 'node:child_process'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { resolvePython } from './lib/python.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = join(__dirname, '..', '..')

export function startFakeServer({ port = 8319 } = {}) {
  const voiceLibraryDir = mkdtempSync(join(tmpdir(), 'qwen3-tts-e2e-voices-'))
  const env = {
    ...process.env,
    PYTHONPATH: [REPO_ROOT, join(REPO_ROOT, 'src'), join(REPO_ROOT, 'src', 'export')].join(
      process.platform === 'win32' ? ';' : ':'
    ),
    VOICE_LIBRARY_DIR: voiceLibraryDir,
    FRONTEND_DIST_DIR: join(REPO_ROOT, 'frontend', 'dist'),
    PERSONA_FORGE_TEST_PORT: String(port),
  }

  const python = resolvePython()
  const child = spawn(python, [join(__dirname, 'fixtures', 'fake_model_server.py')], {
    env,
    stdio: 'inherit',
  })

  child.on('error', (err) => {
    console.error(`[run-server] spawn failed for python=${python}: ${err.message}`)
    process.exit(1)
  })
  child.on('close', (code) => {
    if (code !== 0 && code !== null) {
      console.error(`[run-server] fake_model_server exited with code ${code}`)
      process.exit(code || 1)
    }
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
