import type { BuiltInVoiceMeta, EngineCard, VoiceEngineBinding, VoiceMeta } from '@/lib/api'
import { shortEngineLabel } from '@/lib/voiceEngines'

/**
 * What the Integrations "Available voice IDs" table and the snippet source share (plan §5.7):
 * one row per addressable voice, its engines, and repair actions for blocked pairs.
 * "Servable" is eligibility from a read-only snapshot, not a promise of resident weights
 * or a successful worker call: idle engines load and eligible clones prepare lazily.
 */

export interface ServableEngine {
  /** Engine id, or null for the built-in runtime that serves whatever TTS_BACKEND is active. */
  id: string | null
  label: string
  /** Eligible on this engine, including route-supported lazy preparation and idle loading. */
  servable: boolean
  /** Present when not servable: the exact action that fixes it (Journey 5 vocabulary). */
  reason: string | null
}

export interface ServableVoiceRow {
  /** The id a request names: namespaced for presets/imported voices, plain for saved ones. */
  id: string
  label: string
  kind: 'preset' | 'imported' | 'saved'
  language: string | null
  engines: ServableEngine[]
  /** At least one engine is eligible; rows blocked everywhere are the filter's target. */
  servable: boolean
}

export interface ServabilityInput {
  catalog: BuiltInVoiceMeta[]
  saved: VoiceMeta[]
  /** Per saved voice engine bindings (GET /voices/engines), keyed by voice_id. */
  bindings: Record<string, VoiceEngineBinding[]>
  /** The runtime `TTS_BACKEND` (store value the Speak page reads). */
  runtimeTtsBackend: string | null
  /** GET /engines snapshot; absence is unknown, never evidence of installation. */
  engines: EngineCard[]
  /** Initial startup/errors block the route; idle-unloaded after startup remains ready. */
  serviceReady: boolean
  /** Pocket model capability, not whether the runtime default reference is encoded. */
  pocketCloningAvailable: boolean | null
  /** Mirror api.enforceLanguage; it is a request policy, not a UI language filter. */
  enforceLanguage: boolean
}

export const POCKET_ENGINE_ID = 'pocket-tts'
const POCKET_BACKEND = 'pocket_tts'

function apiLanguageProblem(enforceLanguage: boolean, languageCode: string | null | undefined): string | null {
  if (!enforceLanguage) return null
  // Match app._voice_language_code/_language_enforcement_error exactly: missing/empty
  // defaults to en, regional '-' subtags are stripped, labels/underscores are not normalized.
  // Generated requests omit language, so the route's request-language default is English.
  const code = (languageCode || 'en').toLowerCase().split('-')[0]
  if (code === 'en') return null
  return 'Enforce English on the API is on — choose an English voice or turn it off in Integrations.'
}

/** No worker calls: reconcile catalog/binding evidence with the engine status snapshot. */
function engineProblem(input: ServabilityInput, id: string, label: string): string | null {
  if (!input.serviceReady) return 'The speech service is starting or unavailable — wait for Ready.'
  const card = input.engines.find((candidate) => candidate.id === id)
  if (!card) return `${label} readiness is unavailable — refresh the voice IDs.`
  if (card.state.status === 'not-installed') return `Install ${label} in Runtime → Speech engines.`
  if (card.state.status === 'invalid') return `Repair ${label} in Runtime → Speech engines.`
  // Loading/warming is a transient retry on the same engine, not a broken selection.
  // Keep its snippets stable through a cold start; never warm anything from this snapshot.
  if (card.load_status?.state === 'error') {
    return `${label} failed to load — retry or Repair in Runtime → Speech engines.${card.load_status.error ? ` ${card.load_status.error}` : ''}`
  }
  return null
}

function transcriptProblem(voice: VoiceMeta, binding: VoiceEngineBinding): string | null {
  if (binding.blocker === 'transcript_missing' ||
      (binding.needs_transcript && !voice.sample_text.trim())) {
    return 'This engine needs a transcript — Transcribe or type the words in Voice Library.'
  }
  const unreviewed = voice.asr?.severity &&
    ['warn', 'fail', 'no_speech', 'error'].includes(voice.asr.severity) &&
    voice.sample_text_source !== 'user'
  if (binding.blocker === 'transcript_unreviewed' || (binding.needs_transcript && unreviewed)) {
    return 'Review the transcript in Voice Library and confirm or edit the words.'
  }
  return null
}

/**
 * Rows for every voice the endpoint can address: Pocket presets, every pack engine's presets
 * and imported voices (installed or not — the filter decides visibility), and saved voices
 * with one engine entry per engine that can run them. Bindings marked unsupported (engines
 * that cannot clone at all) are omitted from saved voices: those engines are reached through
 * their presets, and listing them per voice would repeat the same dead end on every row.
 */
export function buildServableVoiceRows(input: ServabilityInput): ServableVoiceRow[] {
  const { catalog, saved, bindings, runtimeTtsBackend } = input
  const pocketActive = runtimeTtsBackend === POCKET_BACKEND
  const rows: ServableVoiceRow[] = []

  for (const voice of catalog) {
    const imported = voice.category === 'imported'
    const installed = voice.installed !== false
    const engineId = voice.engine ?? voice.backend
    const pocket = voice.backend === POCKET_BACKEND
    // Chips read the same short names the Speak picker uses ("Kitten 2", "Pocket Lite").
    const engineLabel = shortEngineLabel({ engine: engineId ?? '', label: voice.engine_label ?? engineId ?? '' })
    const reason = apiLanguageProblem(input.enforceLanguage, voice.language_code) ?? (
      pocket && !pocketActive
        ? 'Runs when Pocket is the active engine — change it in Runtime → Speech engines.'
        : !installed
          ? `Install ${engineLabel} in Runtime → Speech engines.`
          : engineProblem(input, pocket ? POCKET_ENGINE_ID : engineId, engineLabel)
    )
    const engine: ServableEngine = {
      id: pocket ? POCKET_ENGINE_ID : engineId,
      label: engineLabel,
      servable: reason === null,
      reason,
    }
    const presetParts = [voice.display_name]
    if (voice.language && voice.language !== voice.display_name) presetParts.push(voice.language)
    rows.push({
      id: voice.voice_id,
      label: presetParts.join(' · '),
      kind: imported ? 'imported' : 'preset',
      language: voice.language ?? null,
      engines: [engine],
      servable: engine.servable,
    })
  }

  for (const voice of saved) {
    const id = voice.voice_id
    // /voices/engines omits voices whose reference disappeared. A list_voices entry alone
    // is not sufficient: the independent GET snapshots may straddle a deletion/edit.
    const voiceBindings = bindings[id] ?? []
    // A raw aggregate is normally complete, but partial/stale client snapshots must not
    // infer active-runtime readiness from a pack binding alone.
    const referenceKnown = voiceBindings.some((binding) =>
      binding.engine === POCKET_ENGINE_ID && binding.supported && binding.installed &&
      binding.status === 'ready' && binding.blocker === null,
    )
    const referenceProblem = 'Reference audio/readiness is missing — refresh or restore the clip in Voice Library.'
    let activeReason: string | null = !referenceKnown ? referenceProblem
      : !input.serviceReady ? 'The speech service is starting or unavailable — wait for Ready.'
        : !runtimeTtsBackend ? 'The active engine is unknown — refresh Runtime status.'
          : null
    if (activeReason === null && pocketActive) {
      activeReason = engineProblem(input, POCKET_ENGINE_ID, 'Pocket')
      if (activeReason === null && input.pocketCloningAvailable !== true) {
        activeReason = input.pocketCloningAvailable === false
          ? 'Pocket cloning is unavailable — choose cloning-capable weights in Runtime → Speech engines.'
          : 'Pocket cloning capability is unknown — wait for Runtime status.'
      }
    }
    const engines: ServableEngine[] = [
      { id: null, label: 'Active engine', servable: activeReason === null, reason: activeReason },
    ]
    for (const binding of voiceBindings) {
      if (!binding.supported || binding.status === 'unsupported' || binding.engine === POCKET_ENGINE_ID) continue
      const name = shortEngineLabel(binding)
      const reason = !binding.installed || binding.blocker === 'engine_not_installed'
        ? `Install ${name} in Runtime → Speech engines.`
        : engineProblem(input, binding.engine, name) ?? transcriptProblem(voice, binding)
      // ready is a validated-input marker, not a prerequisite for synthesis. Both cloning
      // adapters retry lazy preparation after failed/needs_preparation and serialize with a
      // preparing job. Never turn those states into a new frontend-only preparation policy.
      engines.push({ id: binding.engine, label: name, servable: reason === null, reason })
    }
    const languageReason = apiLanguageProblem(input.enforceLanguage, voice.language_code)
    if (languageReason) {
      for (const engine of engines) {
        engine.servable = false
        engine.reason = languageReason
      }
    }
    rows.push({
      id,
      label: voice.display_name || voice.description || id,
      kind: 'saved',
      language: voice.language ?? null,
      engines,
      servable: engines.some((engine) => engine.servable),
    })
  }

  return rows
}

/**
 * Engine ordering tier for the table sort: Pocket's catalog first, then the built-in runtime
 * entry of saved voices, then pack engines (alphabetically, by label) — magic tiers the
 * comparator alone would not explain.
 */
export function engineSortTier(label: string): 0 | 1 | 2 {
  if (label === 'Pocket' || label.startsWith('Pocket TTS')) return 0
  if (label === 'Active engine') return 1
  return 2
}

/**
 * Select only the requested engine. Null means the active runtime for saved voices, or the
 * namespace's own engine for presets. Never substitute another prepared engine on failure.
 */
export function firstServableEngine(
  row: ServableVoiceRow,
  engineId: string | null = null,
): ServableEngine | null {
  const requested = engineId ?? (row.kind === 'saved' ? null : row.engines[0]?.id)
  return row.engines.find((engine) => engine.id === requested && engine.servable) ?? null
}

/**
 * Short chip text for the table's Engine column. Not-yet-servable engines read as the action
 * that fixes them; the full sentence stays in the chip's tooltip (`engine.reason`).
 */
export function engineChipText(engine: ServableEngine): string {
  if (engine.servable) return engine.label
  const trimmed = engine.reason?.replace(' in Runtime → Speech engines.', '').replace(' in Voice Library.', '')
  if (engine.id === POCKET_ENGINE_ID && engine.reason?.startsWith('Runs when Pocket')) {
    return 'Pocket — not active'
  }
  return trimmed ?? engine.label
}

/**
 * Why the page falls back from the Speak selection to the API default in snippet mode, or
 * null when the selection is servable. Mirrors the table so both surfaces say the same thing.
 */
export function speakSelectionFallback(
  rows: ServableVoiceRow[],
  speakVoiceId: string | null,
  engineId: string | null = null,
): { row: ServableVoiceRow | null; reason: string } | null {
  if (!speakVoiceId) {
    return { row: null, reason: 'No voice is selected in Speak — snippets use the API default.' }
  }
  const row = rows.find((candidate) => candidate.id === speakVoiceId) ?? null
  if (row === null) {
    return {
      row: null,
      reason: `The Speak selection "${speakVoiceId}" is not in the catalog — snippets use the API default.`,
    }
  }
  // Pocket Lite deliberately accepts pocket:<name> aliases. Require matching catalog
  // evidence rather than assuming every Pocket voice is also offered by Lite.
  const aliasRow = engineId === 'pocket-lite' && row.id.startsWith('pocket:')
    ? rows.find((candidate) => candidate.id === `pocket-lite:${row.id.slice('pocket:'.length)}`)
    : undefined
  const selectedRow = aliasRow ?? row
  if (firstServableEngine(selectedRow, engineId)) return null
  const requested = engineId ?? (row.kind === 'saved' ? null : row.engines[0]?.id)
  const selected = selectedRow.engines.find((engine) => engine.id === requested)
  const reason = selected?.reason ?? (row.kind === 'saved'
    ? `Engine ${engineId ?? 'active runtime'} is not supported or its readiness is missing; refresh the voice IDs.`
    : `Voice ${row.id} does not belong to engine ${engineId}; choose a matching voice and engine.`)
  return {
    row,
    reason: `The Speak selection "${row.label}" is not servable right now (${reason}). Snippets use the API default.`,
  }
}
