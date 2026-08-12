// Checks GitHub Releases for a newer persona-forge version than what /health reports.
// Public repo, no auth — cached in localStorage to stay well under GitHub's rate limit.

const REPO = 'nmorgowicz-org/persona-forge'
const CACHE_KEY = 'pf-update-check-cache'
const DISMISSED_KEY = 'pf-update-dismissed-version'
const CACHE_TTL_MS = 24 * 60 * 60 * 1000

interface CachedCheck {
  checkedAt: number
  latestVersion: string | null
  releaseUrl: string | null
}

/** Strips a leading "v" and any "+dev.<sha>" build suffix (see model.get_app_version). */
function normalizeVersion(v: string): string {
  return v.replace(/^v/, '').replace(/\+.*$/, '')
}

/** Compares dotted numeric versions. Returns >0 if a > b, 0 if equal, <0 if a < b. */
export function compareVersions(a: string, b: string): number {
  const pa = normalizeVersion(a).split('.').map((n) => parseInt(n, 10) || 0)
  const pb = normalizeVersion(b).split('.').map((n) => parseInt(n, 10) || 0)
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const diff = (pa[i] || 0) - (pb[i] || 0)
    if (diff !== 0) return diff
  }
  return 0
}

function readCache(): CachedCheck | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return null
    return JSON.parse(raw) as CachedCheck
  } catch {
    return null
  }
}

function writeCache(entry: CachedCheck) {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(entry))
  } catch {
    // localStorage unavailable (private browsing, quota) — non-critical, skip caching
  }
}

async function fetchLatestRelease(): Promise<{ version: string; url: string } | null> {
  const res = await fetch(`https://api.github.com/repos/${REPO}/releases/latest`, {
    headers: { Accept: 'application/vnd.github+json' },
  })
  if (!res.ok) return null
  const data = await res.json()
  const tag = data?.tag_name
  const url = data?.html_url
  if (typeof tag !== 'string' || typeof url !== 'string') return null
  return { version: tag, url }
}

/** Returns the latest release info if newer than currentVersion, using a ~1 day cache. */
export async function checkForUpdate(
  currentVersion: string,
): Promise<{ version: string; url: string } | null> {
  const cached = readCache()
  let latestVersion: string | null
  let releaseUrl: string | null

  if (cached && Date.now() - cached.checkedAt < CACHE_TTL_MS) {
    latestVersion = cached.latestVersion
    releaseUrl = cached.releaseUrl
  } else {
    const fetched = await fetchLatestRelease().catch(() => null)
    latestVersion = fetched?.version ?? null
    releaseUrl = fetched?.url ?? null
    writeCache({ checkedAt: Date.now(), latestVersion, releaseUrl })
  }

  if (!latestVersion || !releaseUrl) return null
  if (compareVersions(latestVersion, currentVersion) <= 0) return null
  return { version: latestVersion, url: releaseUrl }
}

export function getDismissedVersion(): string | null {
  try {
    return localStorage.getItem(DISMISSED_KEY)
  } catch {
    return null
  }
}

export function setDismissedVersion(version: string) {
  try {
    localStorage.setItem(DISMISSED_KEY, version)
  } catch {
    // non-critical
  }
}
