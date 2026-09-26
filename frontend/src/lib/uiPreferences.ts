// D17 / §6.11: the server keeps UI preferences in ui_preferences.json next to runtime.json;
// localStorage only holds a first-paint copy under each key's OLD name and encoding, so the
// first paint needs no server round-trip and existing installs migrate transparently.
//
// This module owns the local copy, the per-key codec, the one-time migration, and the
// background POSTs. It deliberately does not use Tauri IPC: it talks to the same local server
// the SPA already fetches from, so browser and desktop app behave identically (contract D10).
//
// Storage keys and encodings must stay in sync with their original owners:
//   theme                      lib/theme.ts
//   experienceLevel            lib/experienceLevel.ts
//   voiceLibrary.tab/layout    pages/VoiceLibraryPage.tsx
//   voiceLibrary.analysisExpanded  pages/VoiceLibraryPage.tsx ('true'/'false', default true)
//   updates.dismissedVersion   lib/updateCheck.ts

export type PrefKey =
  | 'theme'
  | 'experienceLevel'
  | 'voiceLibrary.tab'
  | 'voiceLibrary.layout'
  | 'voiceLibrary.analysisExpanded'
  | 'updates.dismissedVersion'

type Codec = {
  storageKey: string
  /** localStorage raw -> typed value; undefined = absent or not decodable (skip it). */
  decode: (raw: string | null) => unknown
  encode: (value: unknown) => string
}

// Keep these value lists in sync with their owner modules (theme.ts, experienceLevel.ts,
// VoiceLibraryPage.tsx). Mirrored here so the migration never uploads a value the server
// would reject with a 400 and lose the rest of the batch.
const THEMES = ['violet', 'teal', 'amber', 'rose']
const EXPERIENCE_LEVELS = ['guided', 'expert']
const VOICE_LIBRARY_TABS = ['voices', 'segments']

const isString = (value: unknown): value is string => typeof value === 'string'
const oneOf =
  (choices: string[]) =>
  (raw: string | null): unknown =>
    isString(raw) && choices.includes(raw) ? raw : undefined

const CODECS: Record<PrefKey, Codec> = {
  theme: {
    storageKey: 'persona-forge-theme',
    decode: oneOf(THEMES),
    encode: (value) => String(value),
  },
  experienceLevel: {
    storageKey: 'persona-forge-experience-level',
    decode: oneOf(EXPERIENCE_LEVELS),
    encode: (value) => String(value),
  },
  'voiceLibrary.tab': {
    storageKey: 'voice-library-tab',
    decode: oneOf(VOICE_LIBRARY_TABS),
    encode: (value) => String(value),
  },
  'voiceLibrary.layout': {
    storageKey: 'voice-library-layout',
    decode: (raw) => (isString(raw) ? raw : undefined),
    encode: (value) => String(value),
  },
  'voiceLibrary.analysisExpanded': {
    storageKey: 'voice-library-analysis-expanded',
    decode: (raw) => (raw === 'false' ? false : raw === 'true' ? true : undefined),
    encode: (value) => String(Boolean(value)),
  },
  'updates.dismissedVersion': {
    storageKey: 'pf-update-dismissed-version',
    decode: (raw) => (isString(raw) ? raw : undefined),
    encode: (value) => String(value),
  },
}

const PREF_KEYS = Object.keys(CODECS) as PrefKey[]
const subscribers = new Set<() => void>()

function notify() {
  subscribers.forEach((cb) => cb())
}

export function getPref<T>(key: PrefKey, fallback: T): T {
  const value = CODECS[key].decode(localStorage.getItem(CODECS[key].storageKey))
  return value === undefined ? fallback : (value as T)
}

export function setPref(key: PrefKey, value: unknown): void {
  const codec = CODECS[key]
  try {
    localStorage.setItem(codec.storageKey, codec.encode(value))
  } catch (err) {
    console.warn(`uiPreferences: could not persist ${key} locally`, err)
  }
  void fetch('/ui/preferences', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ values: { [key]: value } }),
  }).catch((err) => console.warn(`uiPreferences: could not sync ${key} to the server`, err))
}

export function subscribePrefs(cb: () => void): () => void {
  subscribers.add(cb)
  return () => subscribers.delete(cb)
}

/**
 * Pull the server's values into the local copy (server wins), and push any local keys the
 * server does not have yet (one-time migration of existing installs). Never throws.
 */
export async function syncPrefsFromServer(): Promise<void> {
  let values: Partial<Record<PrefKey, unknown>>
  try {
    const res = await fetch('/ui/preferences')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    values = ((await res.json()) as { values?: Record<string, unknown> }).values ?? {}
  } catch (err) {
    console.warn('uiPreferences: could not load preferences from the server', err)
    return
  }

  const migration: Record<string, unknown> = {}
  let changed = false
  for (const key of PREF_KEYS) {
    const codec = CODECS[key]
    if (key in values) {
      const remote = codec.encode(values[key])
      if (localStorage.getItem(codec.storageKey) !== remote) {
        localStorage.setItem(codec.storageKey, remote)
        changed = true
      }
    } else {
      const local = codec.decode(localStorage.getItem(codec.storageKey))
      if (local !== undefined) migration[key] = local
    }
  }
  if (Object.keys(migration).length) {
    try {
      const res = await fetch('/ui/preferences', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ values: migration }),
      })
      if (res.ok) changed = true
      else console.warn('uiPreferences: migration upload failed', res.status)
    } catch (err) {
      console.warn('uiPreferences: migration upload failed', err)
    }
  }
  if (changed) notify()
}
