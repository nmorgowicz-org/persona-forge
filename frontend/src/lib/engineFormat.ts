import type { EngineInstallCheck } from '@/lib/api'

/** "Install check: RTF 0.18 on mps", or the slower-than-real-time warning, or why it was not measured. */
export function installCheckText(check: EngineInstallCheck): string {
  if (check.outcome === 'unavailable') {
    return `Install check: speed could not be measured${check.error ? ` (${check.error})` : ''}`
  }
  const rtf = check.rtf !== null ? `RTF ${check.rtf.toFixed(2)}` : 'RTF unknown'
  const where = check.device
    ? ` on ${check.device}${check.mode && check.mode !== check.device ? ` (${check.mode})` : ''}`
    : ''
  const load = check.load_average !== null ? `, load ${check.load_average}` : ''
  return check.outcome === 'slow'
    ? `Install check: runs slower than real time on this machine (${rtf}${where}${load})`
    : `Install check: ${rtf}${where}${load}`
}

export function formatBytes(value: number): string {
  if (value <= 0) return '0 MB'
  const mib = value / (1024 * 1024)
  return mib >= 1024 ? `${(mib / 1024).toFixed(1)} GB` : `${mib.toFixed(0)} MB`
}

