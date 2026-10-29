// Saved Compare-tab ratings live on the server (/compare/results) so they follow the install.
// Ratings the earlier version kept in this browser are uploaded once and then removed.

export interface EngineSummary {
  engine: string
  clips: number
  natural: number
  clean: number
  similarity: number | null
  favourites: number
  speed_median: number | null
  speed_worst: number | null
}

export interface CompareSummary {
  count: number
  summary: EngineSummary[]
}

const LEGACY_KEY = 'pf-compare-results'

async function parse(res: Response): Promise<CompareSummary> {
  if (!res.ok) throw new Error(`Compare results request failed (${res.status})`)
  return (await res.json()) as CompareSummary
}

export async function loadCompareSummary(): Promise<CompareSummary> {
  try {
    const legacy: unknown = JSON.parse(localStorage.getItem(LEGACY_KEY) || '[]')
    if (Array.isArray(legacy) && legacy.length > 0) {
      await saveCompareSessions(legacy)
    }
    localStorage.removeItem(LEGACY_KEY)
  } catch {
    // A migration problem must not hide the saved results.
  }
  return parse(await fetch('/compare/results'))
}

export async function saveCompareSessions(sessions: unknown[]): Promise<CompareSummary> {
  return parse(
    await fetch('/compare/results', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sessions }),
    }),
  )
}

export async function clearCompareResults(): Promise<CompareSummary> {
  return parse(await fetch('/compare/results', { method: 'DELETE' }))
}
