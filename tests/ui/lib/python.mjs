import { existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = join(__dirname, '..', '..', '..')

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

export { REPO_ROOT }
