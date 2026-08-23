// Fixture helpers for the capture harness: locating the interpreter to spawn
// the app with, and seeding a real server's disposable data dirs with the
// committed synthetic fixtures (tests/ui/fixtures/capture-data/). Never
// copies from real data/voices or data/segments.
// Moved from tests/ui/lib/python.mjs and tests/ui/lib/seed.mjs
// (docs/plans/archive/screenshots/20260815-screenshot_and_docs_edit.md Step 1.7).
import { cpSync, existsSync, readdirSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = join(__dirname, '..', '..', '..', '..')
const CAPTURE_DATA_DIR = join(__dirname, '..', '..', 'fixtures', 'capture-data')

export function resolvePython() {
  const venvPython = join(REPO_ROOT, '.venv', 'bin', 'python')
  if (existsSync(venvPython)) return venvPython

  const pythonLocation = process.env.pythonLocation
  if (pythonLocation) {
    const candidate = join(pythonLocation, 'bin', 'python')
    if (existsSync(candidate)) return candidate
  }

  return 'python'
}

export function seedCaptureFixtures(voiceLibraryDir, segmentLibraryDir) {
  const voicesSrc = join(CAPTURE_DATA_DIR, 'voices')
  const segmentsSrc = join(CAPTURE_DATA_DIR, 'segments')

  if (existsSync(voicesSrc)) {
    for (const entry of readdirSync(voicesSrc)) {
      cpSync(join(voicesSrc, entry), join(voiceLibraryDir, entry), { recursive: true })
    }
  }
  if (existsSync(segmentsSrc)) {
    for (const entry of readdirSync(segmentsSrc)) {
      cpSync(join(segmentsSrc, entry), join(segmentLibraryDir, entry), { recursive: true })
    }
  }
}

export { REPO_ROOT }
