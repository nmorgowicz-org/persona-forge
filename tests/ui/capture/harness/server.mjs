import { spawn } from 'node:child_process'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import net from 'node:net'
import { resolvePython } from './fixtures.mjs'
import { seedCaptureFixtures } from './fixtures.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = join(__dirname, '..', '..', '..', '..')

export async function startFakeServer({ seedFixtures = true, port } = {}) {
  port ??= await findAvailablePort(8319)
  const voiceLibraryDir = mkdtempSync(join(tmpdir(), 'persona-forge-e2e-voices-'))
  const segmentLibraryDir = mkdtempSync(join(tmpdir(), 'persona-forge-e2e-segments-'))
  if (seedFixtures) seedCaptureFixtures(voiceLibraryDir, segmentLibraryDir)
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
  const child = spawn(python, [join(REPO_ROOT, 'tests', 'ui', 'fixtures', 'fake_model_server.py')], {
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

// Spawns the real backend (Flask dev server) on disposable temp voice/segment library
// dirs and blocks until the model has finished loading.
export async function startRealServer({
  port,
  voiceLibraryDir,
  segmentLibraryDir,
  modelSize = '0.6B',
  device = 'cpu',
  timeoutMs = 120000,
  seedFixtures = true,
} = {}) {
  port ??= await findAvailablePort(8319)
  voiceLibraryDir ??= mkdtempSync(join(tmpdir(), 'persona-forge-capture-voices-'))
  segmentLibraryDir ??= mkdtempSync(join(tmpdir(), 'persona-forge-capture-segments-'))

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
    ['-c', `from persona_forge.app import app; app.run(host='127.0.0.1', port=${port}, threaded=True)`],
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

// Ported from local-llm-foundry: used when a caller doesn't pin an explicit port.
export async function findAvailablePort(startPort = 8892) {
  for (let port = startPort; port < startPort + 200; port += 1) {
    const available = await new Promise(resolve => {
      const server = net.createServer()
      server.unref()
      server.on('error', () => resolve(false))
      server.listen(port, '127.0.0.1', () => {
        server.close(() => resolve(true))
      })
    })
    if (available) return port
  }
  throw new Error(`No available port found starting at ${startPort}`)
}
