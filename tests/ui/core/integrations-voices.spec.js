// Plan §5.7 Integrations: the Available IDs table (servable-now filter, engine column, copy
// buttons, pagination over 100+ pack voices) and the snippet toggle that derives snippets from
// the selected Speak voice instead of the API default.
//
// Stub only public API boundaries: the shared fake server has no installed pack engines.
// Kitten's 115 real preset records come from the bundled catalog, not placeholder voice names.
// Speak selection still performs its existing best-effort warm POST; passive Integrations
// interactions must not prepare, warm, synthesize, install, or change the API default.
// UI preference persistence is allowed and stubbed per test; only POST /ui/preferences
// is excluded. POST/PUT/PATCH/DELETE to every other endpoint count as operational writes.
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'

const bundled = JSON.parse(readFileSync(new URL('../../../src/persona_forge/engine_voice_catalog.json', import.meta.url), 'utf8'))
const READY_ID = 'vd_111111111111'
const UNPREPPED_ID = 'vd_222222222222'

function pocketVoice(id, name) {
  return {
    voice_id: `pocket:${id}`,
    builtin_voice: id,
    backend: 'pocket_tts',
    display_name: name,
    source: 'kyutai/tts-voices',
    license: 'see upstream',
    language: 'English',
    language_code: 'en',
    category: 'conversation',
    note: '',
    prompt: id,
    requires_backend: 'pocket_tts',
    engine: 'pocket-tts',
    engine_label: 'Pocket TTS',
    installed: true,
  }
}

function packVoice(id, engine, engineLabel, over = {}) {
  return {
    voice_id: id,
    builtin_voice: id.split(':')[1],
    backend: engine,
    display_name: id.split(':')[1],
    source: null,
    license: 'Apache-2.0',
    language: 'English',
    language_code: 'en',
    category: 'preset',
    note: '',
    prompt: id.split(':')[1],
    requires_backend: null,
    engine,
    engine_label: engineLabel,
    installed: true,
    ...over,
  }
}

function catalog() {
  const kitten = bundled.kitten2.map((voice) =>
    packVoice(`kitten2:${voice.name}`, 'kitten2', 'Kitten TTS 2', {
      language: voice.language === 'en' ? 'English' : voice.language,
      language_code: voice.language,
      note: voice.description,
      gender: voice.gender,
      gender_source: voice.gender_source,
    }),
  )
  return {
    voices: [
      pocketVoice('vera', 'Vera'),
      pocketVoice('amelie', 'Amélie'),
      pocketVoice('hilary', 'Hilary'),
      packVoice('kokoro:af_heart', 'kokoro', 'Kokoro 82M'),
      packVoice('kokoro:bm_george', 'kokoro', 'Kokoro 82M'),
      ...kitten,
      packVoice('phonon:imported-narrator', 'phonon-31m', 'Phonon 31M', {
        category: 'imported', imported: true, display_name: 'Imported narrator',
        source: 'narrator.safetensors',
        provenance: {
          source_filename: 'narrator.safetensors', sha256: 'a'.repeat(64), size: 4096,
          imported_at: '2026-10-27T00:00:00Z', engine_revision: 'fixture-revision',
        },
      }),
      packVoice('pocket-lite:alba', 'pocket-lite', 'Pocket Lite (18M)', { installed: false }),
      packVoice('pocket-lite:jane', 'pocket-lite', 'Pocket Lite (18M)', { installed: false }),
    ],
    engines: [],
  }
}

function savedVoices() {
  return {
    voices: [
      {
        voice_id: READY_ID,
        description: 'Narrator Ready',
        sample_text: 'A transcript.',
        sample_text_source: 'user',
        needs_review: false,
        language: 'English',
        created_at: 0,
      },
      {
        voice_id: UNPREPPED_ID,
        description: 'Rough Cut',
        sample_text: 'Words to review.',
        sample_text_source: 'user',
        needs_review: false,
        language: 'English',
        created_at: 0,
      },
    ],
  }
}

function bindings() {
  const ready = {
    engine: 'kitten2',
    label: 'Kitten TTS 2',
    status: 'ready',
    supported: true,
    installed: true,
    needs_transcript: true,
    blocker: null,
    reason: null,
    error: null,
    prepared_at: 1730000000,
    can_prepare: false,
  }
  const unprepped = {
    ...ready,
    status: 'needs_preparation',
    prepared_at: null,
    can_prepare: true,
  }
  const pocketReady = {
    engine: 'pocket-tts', label: 'Pocket TTS', status: 'ready', supported: true,
    installed: true, needs_transcript: false, blocker: null, reason: null,
    error: null, prepared_at: null, can_prepare: false,
  }
  return {
    voices: {
      [READY_ID]: [
        ready,
        pocketReady,
        {
          engine: 'phonon-31m',
          label: 'Phonon 31M',
          status: 'unsupported',
          supported: false,
          installed: true,
          needs_transcript: false,
          blocker: null,
          reason: 'no local cloning',
          error: null,
          prepared_at: null,
          can_prepare: false,
        },
      ],
      [UNPREPPED_ID]: [pocketReady, unprepped],
    },
  }
}

function engineCard(id, label, over = {}) {
  return {
    id,
    label,
    description: '',
    kind: id === 'pocket-tts' ? 'builtin' : 'pack',
    version: null,
    runtime: 'python-cpu',
    source: null,
    license: null,
    active: id === 'pocket-tts',
    capabilities: { presets: true, clone: id !== 'phonon-31m' },
    state: {
      status: id === 'pocket-lite' ? 'not-installed' : 'verified',
      artifacts_present: 0,
      artifacts_total: 0,
      disk_bytes: 0,
      verified: id !== 'pocket-lite',
      errors: [],
    },
    requirements: [],
    install_check: null,
    benchmark: null,
    pack: null,
    ...over,
  }
}

async function stubIntegrations(page, options = {}) {
  const fixture = {
    catalog: catalog(),
    saved: savedVoices(),
    bindings: bindings(),
    engines: {
      engines: [
        engineCard('pocket-tts', 'Pocket TTS'),
        engineCard('kokoro', 'Kokoro 82M', { capabilities: { presets: true, clone: false } }),
        engineCard('kitten2', 'Kitten TTS 2'),
        engineCard('phonon-31m', 'Phonon 31M'),
        engineCard('pocket-lite', 'Pocket Lite (18M)'),
      ],
      nudge: null,
    },
    apiDefault: {
      default: {
        engine: 'kokoro', engine_label: 'Kokoro 82M', voice: 'kokoro:af_heart',
        variant: null, kind: 'preset', display_name: 'af_heart',
        language: 'English', language_code: 'en', servable: true, problem: null,
      },
    },
    mutations: [],
    preferences: {
      theme: 'violet', experienceLevel: 'expert', voiceFavorites: [],
      'voiceCatalog.language': 'all', 'integrations.servableOnly': true,
      'api.enforceLanguage': false,
    },
    preferenceWrites: [],
  }
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname
    const method = request.method()
    const preferenceWrite = method === 'POST' && path === '/ui/preferences'
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method) && !preferenceWrite) {
      fixture.mutations.push(path)
    }
  })
  const json = (route, value) => route.fulfill({ contentType: 'application/json', body: JSON.stringify(value) })
  // Never leak persisted filter/language choices into the shared fake server or other specs.
  await page.route((url) => url.pathname === '/ui/preferences', (route) => {
    if (route.request().method() === 'POST') {
      const values = route.request().postDataJSON().values ?? {}
      Object.assign(fixture.preferences, values)
      fixture.preferenceWrites.push(values)
    } else if (route.request().method() !== 'GET') {
      return route.fulfill({ status: 405, body: 'Unsupported preference method' })
    }
    return json(route, { values: fixture.preferences })
  })
  for (const [path, value] of [
    ['/voices/built-in', () => fixture.catalog],
    ['/voices', () => fixture.saved],
    ['/voices/engines', () => fixture.bindings],
    ['/engines', () => fixture.engines],
    ['/api-default', () => fixture.apiDefault],
    ['/v1/models', () => ({
      data: fixture.engines.engines.map((engine) => ({
        id: engine.id, label: engine.label, active: engine.active,
        installed: engine.state.status !== 'not-installed', capabilities: engine.capabilities,
      })),
    })],
    ['/v1/audio/voices', () => ({
      data: fixture.catalog.voices.filter((voice) => voice.installed).map((voice) => ({
        voice_id: voice.voice_id, engine: voice.engine, kind: 'preset', display_name: voice.display_name,
      })),
    })],
  ]) {
    await page.route((url) => url.pathname === path, (route) => {
      // Unexpected writes must not change the shared fake server or masquerade as GET success.
      if (route.request().method() !== 'GET') return route.fulfill({ status: 405, body: 'Read-only fixture' })
      return json(route, value())
    })
  }
  // Preserve Speak's existing warm call, without loading anything in the shared fake process.
  await page.route('**/voices/*/warm', (route) => json(route, { status: 'ready' }))
  // The shell's /health poll overwrites the store's runtime backend (store.ts), so /runtime/config
  // alone is not enough: pass the live response through and amend the fields the app reads.
  const runtimeBackend = options.runtimeBackend ?? 'pocket_tts'
  await page.route('**/health', async (route) => {
    const response = await route.fetch()
    const data = await response.json()
    data.backend = runtimeBackend
    data.resolved_backend = runtimeBackend
    if (runtimeBackend === 'pocket_tts') {
      data.pocket_tts = { pocket_cloning_available: options.pocketCloningAvailable ?? true, message: '' }
    }
    await route.fulfill({ response, json: data })
  })
  await page.route((url) => url.pathname === '/runtime/config', (route) => json(route, {
    reconfig_in_progress: false,
    live: {
      TTS_BACKEND: options.runtimeBackend ?? 'pocket_tts',
      IDLE_UNLOAD_SECONDS: 0, SILENCE_TRIM: true, SILENCE_TRIM_THRESH: -60,
      SILENCE_TRIM_PAD_MS: 300, OV_DYNAMIC_QUANT_GROUP_SIZE: 128, MODEL_DTYPE: 'float32',
      pocket_tts_voice_cloning_available: options.pocketCloningAvailable ?? true,
    },
    read_only: {}, not_live: {},
  }))
  return fixture
}

async function openIntegrations(page) {
  await page.goto('/')
  await expect(page.getByTestId('speak-text-input')).toBeVisible()
  await enterIntegrations(page)
}

async function selectSpeakVoice(page, name) {
  await page.goto('/')
  await expect(page.getByTestId('speak-text-input')).toBeVisible()
  await chooseSpeakVoice(page, name)
}

async function chooseSpeakVoice(page, name) {
  await page.getByTestId('voice-selector-trigger').click()
  await expect(page.getByRole('listbox', { name: 'Voices' })).toBeVisible()
  if (name !== 'Runtime default') await page.getByRole('textbox', { name: 'Search voices' }).fill(name)
  const option = page.getByRole('option', { name: new RegExp(name) }).first()
  // Match the existing picker specs: await the API-derived badge before selecting a saved
  // voice, so handleVoiceChange sees the prepared/preparable engine bindings, not a race.
  if (name === 'Narrator Ready') await expect(option).toContainText('Ready on Kitten 2')
  if (name === 'Rough Cut') await expect(option).toContainText('Prepare Kitten 2 first')
  await option.click()
}

async function enterIntegrations(page) {
  await page.getByTestId('nav-integrations').click()
  await expect(page.getByTestId('available-ids')).toBeVisible()
  await expect(page.getByTestId('ids-refresh')).toBeEnabled()
}

async function showRow(page, id) {
  await page.getByRole('searchbox', { name: 'Search available voice IDs' }).fill(id)
  await expect(row(page, id)).toBeVisible()
  return row(page, id)
}

async function enableSpeakSnippets(page) {
  await enterIntegrations(page)
  await page.getByTestId('snippet-speak-toggle').locator('input').check()
}

async function refreshIds(page) {
  await Promise.all([
    page.waitForResponse((response) => new URL(response.url()).pathname === '/voices/engines'),
    page.getByTestId('ids-refresh').click(),
  ])
  await expect(page.getByTestId('ids-refresh')).toBeEnabled()
}

async function expectSnippets(page, voice, model = 'persona-forge') {
  const [curl, python, js] = [0, 1, 2].map((index) => page.locator('pre code').nth(index))
  await expect(curl).toContainText(`"voice_id": "${voice}"`)
  await expect(python).toContainText(`voice="${voice}"`)
  await expect(js).toContainText(`"voice": "${voice}"`)
  await expect(python).toContainText(`model="${model}"`)
  await expect(js).toContainText(`"model": "${model}"`)
  if (model === 'persona-forge') await expect(curl).not.toContainText('"model"')
  else await expect(curl).toContainText(`"model": "${model}"`)
}

function row(page, id) {
  // Exact ID match: "kitten2:Arabic" is a prefix of kitten2:ArabicNews etc.
  return page.getByTestId('voice-row').filter({ has: page.getByTestId('voice-id').getByText(id, { exact: true }) })
}

function deferred() {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}

test.describe('integrations available IDs table', () => {
  test('lists every servable voice with an engine column and copy buttons', async ({ page }) => {
    await stubIntegrations(page)
    await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
    await openIntegrations(page)

    // Search crosses page boundaries; each exact ID remains individually copyable.
    for (const [id, chips] of [
      ['kokoro:af_heart', ['Kokoro']],
      ['kitten2:AirportAnnouncer', ['Kitten 2']],
      ['phonon:imported-narrator', ['Phonon']],
      ['pocket:vera', ['Pocket']],
      [READY_ID, ['Active engine', 'Kitten 2']],
    ]) {
      const found = await showRow(page, id)
      await expect(found.getByTestId('engine-chip')).toHaveText(chips)
    }
    const defaultRow = await showRow(page, 'kokoro:af_heart')
    await expect(defaultRow.getByText('API default')).toBeVisible()
    const copyRow = await showRow(page, 'kokoro:bm_george')
    await copyRow.getByTestId('copy-voice-id').click()
    await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe('kokoro:bm_george')
  })

  test('servable now is on by default and hides rows a request would reject', async ({ page }) => {
    await stubIntegrations(page)
    await openIntegrations(page)

    // A saved voice remains routable through the active runtime and lazy pack preparation.
    // Only the two uninstalled Pocket Lite presets are hidden (123 of 125 total IDs).
    await expect(page.getByTestId('ids-count')).toContainText('25 of 123 IDs')
    await page.getByRole('searchbox', { name: 'Search available voice IDs' }).fill('pocket-lite:')
    await expect(page.getByTestId('voice-row')).toHaveCount(0)
    await showRow(page, UNPREPPED_ID)
    await expect(row(page, UNPREPPED_ID).getByTestId('set-default')).toBeEnabled()
    await expect(page.getByTestId('ids-count')).toContainText('servable now')
    await expect(page.getByTestId('servable-filter').locator('input')).toBeChecked()
  })

  test('turning the filter off reveals each unservable row with its fix', async ({ page }) => {
    await stubIntegrations(page)
    await openIntegrations(page)
    await page.getByTestId('servable-filter').locator('input').uncheck()

    await expect(page.getByTestId('ids-count')).toContainText('25 of 125 IDs')
    await expect(page.getByTestId('ids-count')).toContainText('including not-yet-servable')
    const missing = await showRow(page, 'pocket-lite:alba')
    await expect(missing.getByTestId('engine-chip')).toHaveText(['Install Pocket Lite'])
    await expect(missing.getByText('Not servable yet')).toBeVisible()
    await expect(missing.getByTestId('set-default')).toHaveCount(0)
    await expect(missing.getByTestId('engine-chip')).toHaveAttribute(
      'data-app-tooltip', /Install Pocket Lite.*Runtime → Speech engines/,
    )
  })

  test('pagination keeps a 100+-row catalog usable without collapsing engines', async ({ page }) => {
    const fixture = await stubIntegrations(page)
    await openIntegrations(page)
    // Five real pages, including a partial last page. Collect every public table ID once.
    expect(bundled.kitten2.length).toBeGreaterThanOrEqual(100)
    await expect(page.getByTestId('ids-prev')).toBeDisabled()
    const seen = []
    for (let index = 1; index <= 5; index++) {
      await expect(page.getByTestId('ids-count')).toContainText(`page ${index} of 5`)
      await expect(page.getByTestId('voice-row')).toHaveCount(index === 5 ? 23 : 25)
      seen.push(...await page.getByTestId('voice-id').allTextContents())
      if (index < 5) await page.getByTestId('ids-next').click()
    }
    await expect(page.getByTestId('ids-next')).toBeDisabled()
    const expected = [
      ...fixture.catalog.voices.filter((voice) => voice.installed).map((voice) => voice.voice_id),
      READY_ID, UNPREPPED_ID,
    ]
    expect(seen.map((id) => id.trim()).sort()).toEqual(expected.sort())

    // Changing the filter on the last page resets to page one, before slicing the rows.
    await page.getByTestId('servable-filter').locator('input').uncheck()
    await expect(page.getByTestId('ids-count')).toContainText('25 of 125 IDs · page 1 of 5')
    await expect(page.getByTestId('ids-prev')).toBeDisabled()
  })

  test('search matches IDs, labels, engines and languages before pagination', async ({ page }) => {
    await stubIntegrations(page)
    await openIntegrations(page)
    await page.getByTestId('ids-next').click()
    const search = page.getByRole('searchbox', { name: 'Search available voice IDs' })
    await search.fill('kitten2:')
    await expect(page.getByTestId('ids-count')).toContainText('25 of 115 IDs · page 1 of 5')
    expect((await page.getByTestId('voice-id').allTextContents()).every((id) => id.startsWith('kitten2:'))).toBe(true)
    await search.fill('Kitten 2')
    await expect(page.getByTestId('ids-count')).toContainText('25 of 117 IDs · page 1 of 5')
    await expect(row(page, READY_ID)).toBeVisible()
    await expect(row(page, UNPREPPED_ID)).toBeVisible()
    await search.fill('Imported narrator')
    await expect(page.getByTestId('voice-id')).toHaveText(['phonon:imported-narrator'])
    await search.fill('English')
    await expect(row(page, 'pocket:vera')).toBeVisible()
    await expect(row(page, 'kitten2:Arabic')).toHaveCount(0)
    await search.fill('no-such-voice')
    await expect(page.getByTestId('voice-row')).toHaveCount(0)
    await expect(page.getByText(/No matching voice IDs/)).toBeVisible()
    await search.clear()
    await expect(page.getByTestId('ids-count')).toContainText('25 of 123 IDs · page 1 of 5')
  })

  test('Pocket presets are not servable on a non-Pocket runtime', async ({ page }) => {
    await stubIntegrations(page, { runtimeBackend: 'pytorch' })
    await openIntegrations(page)
    const search = page.getByRole('searchbox', { name: 'Search available voice IDs' })
    await search.fill('pocket:vera')
    await expect(row(page, 'pocket:vera')).toHaveCount(0)
    await page.getByTestId('servable-filter').locator('input').uncheck()
    await expect(row(page, 'pocket:vera').getByTestId('engine-chip')).toHaveText(['Pocket — not active'])
    await expect(row(page, 'pocket:vera').getByTestId('engine-chip')).toHaveAttribute('data-app-tooltip', /Runtime/)
    await expect(row(page, 'pocket:vera').getByText('Not servable yet')).toBeVisible()
  })
})

test.describe('integrations snippet source toggle', () => {
  test('snippets derive from the API default until the toggle is on', async ({ page }) => {
    await stubIntegrations(page)
    await openIntegrations(page)

    const curl = page.locator('pre code').first()
    await expect(curl).toContainText('kokoro:af_heart')
    // URL composition: the endpoint carries /v1 exactly once; no double or missing segment.
    await expect(curl).toContainText('base_url="$PERSONA_FORGE_BASE_URL"')
    await expect(curl).toContainText('${base_url}/v1/audio/speech')
    await expect(curl).not.toContainText('/v1/v1')
    const python = page.locator('pre code').nth(1)
    await expect(python).toContainText('os.environ["PERSONA_FORGE_BASE_URL"]')
    await expect(python).toContainText('base_url=base_url + "/v1"')
    await expect(python).not.toContainText('$PERSONA_FORGE_BASE_URL')
    const js = page.locator('pre code').nth(2)
    await expect(js).toContainText('process.env.PERSONA_FORGE_BASE_URL')
    await expect(js).toContainText('baseURL: baseURL.replace(')
    await expect(js).toContainText('+ "/v1"')
    await expect(js).not.toContainText('$PERSONA_FORGE_BASE_URL')
    await expectSnippets(page, 'kokoro:af_heart', 'kokoro')
  })

  test('a servable Speak selection replaces the default and names its engine', async ({ page }) => {
    await stubIntegrations(page)
    await selectSpeakVoice(page, 'Narrator Ready')
    await expect(page.getByTestId('saved-voice-engine')).toHaveValue('kitten2')
    await enableSpeakSnippets(page)
    await expect(page.getByTestId('snippet-fallback-reason')).toHaveCount(0)
    await expectSnippets(page, READY_ID, 'kitten2')
  })

  test('a blocked selected engine falls back even when the saved voice can use the active runtime', async ({ page }) => {
    const fixture = await stubIntegrations(page)
    Object.assign(fixture.bindings.voices[UNPREPPED_ID].find((binding) => binding.engine === 'kitten2'), {
      blocker: 'transcript_unreviewed', can_prepare: true,
      reason: 'Review and confirm the transcript in Voice Library.',
    })
    fixture.saved.voices[1].sample_text_source = 'whisper'
    fixture.saved.voices[1].needs_review = true
    await selectSpeakVoice(page, 'Rough Cut')
    await page.getByTestId('saved-voice-engine').selectOption('kitten2')
    await enableSpeakSnippets(page)
    await expect(page.getByTestId('snippet-fallback-reason')).toContainText(/transcript|review/i)
    await expectSnippets(page, 'kokoro:af_heart', 'kokoro')
    // It must not vanish from the table merely because this particular engine is blocked.
    await showRow(page, UNPREPPED_ID)
    await expect(row(page, UNPREPPED_ID).getByTestId('set-default')).toBeEnabled()
  })

  test('the active-engine choice is respected instead of re-inferring a prepared pack', async ({ page }) => {
    await stubIntegrations(page)
    await selectSpeakVoice(page, 'Narrator Ready')
    await page.getByTestId('saved-voice-engine').selectOption('')
    await enableSpeakSnippets(page)
    await expect(page.getByTestId('snippet-fallback-reason')).toHaveCount(0)
    await expectSnippets(page, READY_ID)
  })

  test('an eligible unprepared saved voice uses lazy preparation, not a false fallback', async ({ page }) => {
    await stubIntegrations(page)
    await selectSpeakVoice(page, 'Rough Cut')
    await page.getByTestId('saved-voice-engine').selectOption('kitten2')
    await enableSpeakSnippets(page)
    await expect(page.getByTestId('snippet-fallback-reason')).toHaveCount(0)
    await expectSnippets(page, UNPREPPED_ID, 'kitten2')
    await showRow(page, UNPREPPED_ID)
    await expect(row(page, UNPREPPED_ID).getByTestId('engine-chip')).toHaveText(['Active engine', 'Kitten 2'])
  })

  test('an installed namespaced pack preset implies its own engine', async ({ page }) => {
    await stubIntegrations(page)
    await selectSpeakVoice(page, 'AirportAnnouncer')
    await enableSpeakSnippets(page)
    await expect(page.getByTestId('snippet-fallback-reason')).toHaveCount(0)
    await expectSnippets(page, 'kitten2:AirportAnnouncer', 'kitten2')
  })

  test('the legacy Engine voice dropdown overrides the saved voice in all snippets', async ({ page }) => {
    await stubIntegrations(page)
    await selectSpeakVoice(page, 'Narrator Ready')
    await page.getByRole('combobox', { name: 'Engine', exact: true }).selectOption('kokoro')
    await page.getByRole('combobox', { name: 'Engine voice', exact: true }).selectOption('kokoro:bm_george')
    await enableSpeakSnippets(page)
    await expectSnippets(page, 'kokoro:bm_george', 'kokoro')
    await expect(page.locator('pre code').first()).not.toContainText(READY_ID)
  })

  test('a missing pack selection falls back with an install hint', async ({ page }) => {
    await stubIntegrations(page)
    await selectSpeakVoice(page, 'alba')
    await enableSpeakSnippets(page)
    await expect(page.getByTestId('snippet-fallback-reason')).toContainText(/Install Pocket Lite/)
    await expectSnippets(page, 'kokoro:af_heart', 'kokoro')
  })

  test('a voice removed from the catalog falls back instead of emitting a stale selection', async ({ page }) => {
    const fixture = await stubIntegrations(page)
    await selectSpeakVoice(page, 'AirportAnnouncer')
    fixture.catalog.voices = fixture.catalog.voices.filter((voice) => voice.voice_id !== 'kitten2:AirportAnnouncer')
    await enableSpeakSnippets(page)
    await expect(page.getByTestId('snippet-fallback-reason')).toContainText('not in the catalog')
    await expectSnippets(page, 'kokoro:af_heart', 'kokoro')
  })

  test('selecting Runtime default does not substitute the first saved voice', async ({ page }) => {
    await stubIntegrations(page)
    await selectSpeakVoice(page, 'Narrator Ready')
    await chooseSpeakVoice(page, 'Runtime default')
    await enableSpeakSnippets(page)
    await expect(page.getByTestId('snippet-fallback-reason')).toContainText('No voice is selected in Speak')
    await expectSnippets(page, 'kokoro:af_heart', 'kokoro')
  })

  test('without an explicit API default snippets omit the voice and use the runtime reference', async ({ page }) => {
    const fixture = await stubIntegrations(page)
    fixture.apiDefault.default = null
    await openIntegrations(page)
    await page.getByTestId('snippet-speak-toggle').locator('input').check()
    await expect(page.getByTestId('snippet-fallback-reason')).toContainText('No voice is selected in Speak')
    const snippets = page.locator('pre code')
    await expect(snippets).toHaveCount(3)
    for (const snippet of await snippets.all()) {
      await expect(snippet).not.toContainText(READY_ID)
      await expect(snippet).not.toContainText('my-voice')
    }
    await expect(snippets.nth(0)).not.toContainText('"voice_id"')
    await expect(snippets.nth(1)).not.toContainText(/\bvoice\s*=/)
    await expect(snippets.nth(1)).toContainText('response = client.post(')
    await expect(snippets.nth(2)).not.toContainText('"voice":')
    await expect(snippets.nth(2)).toContainText('client.post("/audio/speech"')
  })

  test('no Speak selection falls back to the default with a plain reason', async ({ page }) => {
    await stubIntegrations(page)
    await openIntegrations(page)
    await page.getByTestId('snippet-speak-toggle').locator('input').check()

    await expect(page.getByTestId('snippet-fallback-reason')).toContainText(
      'No voice is selected in Speak',
    )
    await expect(page.locator('pre code').first()).toContainText('kokoro:af_heart')
  })
})

test.describe('integrations status reconciliation without engine/default mutations', () => {
  test('passive controls only persist UI preferences, never warm, prepare, synthesize or change defaults', async ({ page }) => {
    const fixture = await stubIntegrations(page)
    await selectSpeakVoice(page, 'Narrator Ready')
    // This warmup belongs to Speak's pre-existing selection behavior, not Integrations.
    await expect.poll(() => fixture.mutations).toContain(`/voices/${READY_ID}/warm`)
    const beforeIntegrations = [...fixture.mutations]
    await enterIntegrations(page)
    await page.getByTestId('snippet-speak-toggle').locator('input').check()
    await expectSnippets(page, READY_ID, 'kitten2')
    await page.getByTestId('snippet-speak-toggle').locator('input').uncheck()
    await expectSnippets(page, 'kokoro:af_heart', 'kokoro')
    await page.getByTestId('servable-filter').locator('input').uncheck()
    await showRow(page, 'pocket-lite:alba')
    await page.getByTestId('servable-filter').locator('input').check()
    await expect(row(page, 'pocket-lite:alba')).toHaveCount(0)
    await page.getByTestId('ids-search').clear()
    await page.getByTestId('ids-next').click()
    await expect(page.getByTestId('ids-count')).toContainText('page 2 of 5')
    await refreshIds(page)
    await expect(page.getByTestId('api-default-engine')).toHaveText('Kokoro 82M')
    await expect.poll(() => fixture.preferenceWrites).toEqual(expect.arrayContaining([
      { 'integrations.servableOnly': false },
      { 'integrations.servableOnly': true },
    ]))
    expect(fixture.preferences['integrations.servableOnly']).toBe(true)
    expect(fixture.mutations).toEqual(beforeIntegrations)
  })

  test('refresh updates installed/readiness state and repairs stale snippet selection', async ({ page }) => {
    const fixture = await stubIntegrations(page)
    await selectSpeakVoice(page, 'Narrator Ready')
    await enableSpeakSnippets(page)
    await expectSnippets(page, READY_ID, 'kitten2')
    const beforeRefresh = [...fixture.mutations]
    // Simulate an external uninstall: update the public catalog, cards AND binding payload.
    const kitten = fixture.engines.engines.find((engine) => engine.id === 'kitten2')
    kitten.state.status = 'not-installed'
    for (const voice of fixture.catalog.voices.filter((voice) => voice.engine === 'kitten2')) voice.installed = false
    Object.assign(fixture.bindings.voices[READY_ID][0], {
      installed: false, status: 'needs_preparation', blocker: 'engine_not_installed',
      prepared_at: null, can_prepare: false, reason: 'Install the engine to use it.',
    })
    await refreshIds(page)
    await expect(page.getByTestId('snippet-fallback-reason')).toContainText(/Install.*Kitten/)
    await expectSnippets(page, 'kokoro:af_heart', 'kokoro')
    // The saved voice still has its active-runtime route; only pack presets disappear.
    await showRow(page, READY_ID)
    await expect(row(page, READY_ID).getByTestId('set-default')).toBeEnabled()
    await page.getByTestId('ids-search').fill('kitten2:AirportAnnouncer')
    await expect(page.getByTestId('voice-row')).toHaveCount(0)

    kitten.state.status = 'verified'
    for (const voice of fixture.catalog.voices.filter((voice) => voice.engine === 'kitten2')) voice.installed = true
    Object.assign(fixture.bindings.voices[READY_ID][0], {
      installed: true, status: 'ready', blocker: null, prepared_at: 1769000000, reason: null,
    })
    await refreshIds(page)
    await expect(page.getByTestId('snippet-fallback-reason')).toHaveCount(0)
    await expectSnippets(page, READY_ID, 'kitten2')
    await expect(row(page, 'kitten2:AirportAnnouncer')).toBeVisible()
    expect(fixture.mutations).toEqual(beforeRefresh)
  })

  for (const status of ['failed', 'preparing']) {
    test(`a ${status} binding with valid inputs remains lazily routable after refresh`, async ({ page }) => {
      const fixture = await stubIntegrations(page)
      await selectSpeakVoice(page, 'Narrator Ready')
      // Start blocked after Speak selected the previously prepared pair. Recovery to an
      // eligible failed/preparing binding must actually change the rendered fallback.
      Object.assign(fixture.bindings.voices[READY_ID][0], {
        status: 'needs_preparation', prepared_at: null,
        blocker: 'transcript_unreviewed', can_prepare: true,
        reason: 'Review the transcript before preparing.',
      })
      await enableSpeakSnippets(page)
      await expect(page.getByTestId('snippet-fallback-reason')).toContainText(/transcript|review/i)
      await expectSnippets(page, 'kokoro:af_heart', 'kokoro')
      const beforeRefresh = [...fixture.mutations]
      Object.assign(fixture.bindings.voices[READY_ID][0], {
        status, prepared_at: null, blocker: null,
        can_prepare: status === 'failed',
        error: status === 'failed' ? 'Prior preparation failed; a request can retry.' : null,
        reason: status === 'preparing' ? 'Preparing…' : 'Prior preparation failed; a request can retry.',
      })
      await refreshIds(page)
      await expect(page.getByTestId('snippet-fallback-reason')).toHaveCount(0)
      await expectSnippets(page, READY_ID, 'kitten2')
      await showRow(page, READY_ID)
      await expect(row(page, READY_ID).getByTestId('set-default')).toBeEnabled()
      await expect(row(page, READY_ID).getByTestId('engine-chip')).toHaveText(['Active engine', 'Kitten 2'])
      expect(fixture.mutations).toEqual(beforeRefresh)
    })
  }

  test('a failed status refresh does not leave a stale prepared pack in snippets', async ({ page }) => {
    const fixture = await stubIntegrations(page)
    await selectSpeakVoice(page, 'Narrator Ready')
    await enableSpeakSnippets(page)
    await expectSnippets(page, READY_ID, 'kitten2')
    const beforeRefresh = [...fixture.mutations]
    await page.route((url) => url.pathname === '/voices/engines', (route) =>
      route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: 'Bindings temporarily unavailable' }) }),
    )
    await refreshIds(page)
    await expect(page.getByText('Bindings temporarily unavailable', { exact: true })).toBeVisible()
    await expect(page.getByTestId('snippet-fallback-reason')).toBeVisible()
    await expectSnippets(page, 'kokoro:af_heart', 'kokoro')
    expect(fixture.mutations).toEqual(beforeRefresh)
  })

  test('only the explicit Test endpoint action synthesizes, with the selected pair and no default mutation', async ({ page }) => {
    const fixture = await stubIntegrations(page)
    const requests = []
    await page.route((url) => url.pathname === '/v1/audio/speech', (route) => {
      requests.push(route.request().postDataJSON())
      return route.fulfill({
        status: 400, contentType: 'application/json',
        body: JSON.stringify({ error: { message: 'Fixture endpoint failure', type: 'invalid_request_error' } }),
      })
    })
    await selectSpeakVoice(page, 'Narrator Ready')
    await enableSpeakSnippets(page)
    await expectSnippets(page, READY_ID, 'kitten2')
    const beforeTest = fixture.mutations.length
    await page.getByRole('button', { name: 'Test endpoint', exact: true }).click()
    await expect(page.getByText(/Fixture endpoint failure/)).toBeVisible()
    expect(requests).toEqual([{
      model: 'kitten2', input: 'Hello from Hermes.', voice_id: READY_ID, response_format: 'mp3',
    }])
    expect(fixture.mutations.slice(beforeTest)).toEqual(['/v1/audio/speech'])
    await expect(page.getByTestId('api-default-engine')).toHaveText('Kokoro 82M')
  })

  test('missing binding data does not invent an active cloning route when Pocket cloning is unavailable', async ({ page }) => {
    const fixture = await stubIntegrations(page, { pocketCloningAvailable: false })
    await selectSpeakVoice(page, 'Rough Cut')
    // The saved voice is user-selectable before a later GET loses its binding status.
    await page.getByTestId('saved-voice-engine').selectOption('')
    fixture.bindings.voices[UNPREPPED_ID] = []
    await enableSpeakSnippets(page)
    await expect(page.getByTestId('snippet-fallback-reason')).toBeVisible()
    await expectSnippets(page, 'kokoro:af_heart', 'kokoro')
    await page.getByTestId('ids-search').fill(UNPREPPED_ID)
    await expect(row(page, UNPREPPED_ID)).toHaveCount(0)
    await page.getByTestId('servable-filter').locator('input').uncheck()
    await expect(row(page, UNPREPPED_ID).getByText('Not servable yet')).toBeVisible()
    await expect(row(page, UNPREPPED_ID).getByTestId('set-default')).toHaveCount(0)
  })

  test('enforcing English hides a non-English ID and falls back from that Speak selection', async ({ page }) => {
    const fixture = await stubIntegrations(page)
    await selectSpeakVoice(page, 'Arabic')
    await enableSpeakSnippets(page)
    await expectSnippets(page, 'kitten2:Arabic', 'kitten2')
    await showRow(page, 'kitten2:Arabic')
    const beforeEnforcement = [...fixture.mutations]
    await page.getByTestId('enforce-language').locator('input').check()
    await expect.poll(() => fixture.preferences['api.enforceLanguage']).toBe(true)
    await expect(row(page, 'kitten2:Arabic')).toHaveCount(0)
    await expect(page.getByTestId('snippet-fallback-reason')).toContainText(/English|language/i)
    await expectSnippets(page, 'kokoro:af_heart', 'kokoro')
    await page.getByTestId('servable-filter').locator('input').uncheck()
    await expect(row(page, 'kitten2:Arabic').getByText('Not servable yet')).toBeVisible()
    await expect(row(page, 'kitten2:Arabic').getByTestId('engine-chip')).toContainText(/English|language/i)
    // Turning enforcement back off restores the exact selected speaker, without a warmup.
    await page.getByTestId('enforce-language').locator('input').uncheck()
    await expect.poll(() => fixture.preferences['api.enforceLanguage']).toBe(false)
    await expect(page.getByTestId('snippet-fallback-reason')).toHaveCount(0)
    await expectSnippets(page, 'kitten2:Arabic', 'kitten2')
    expect(fixture.mutations).toEqual(beforeEnforcement)
  })
})

test.describe('Speak and Integrations public request races', () => {
  for (const selection of ['saved-engine', 'legacy-preset']) {
    test(`Speak remount preserves the ${selection} request while model discovery is delayed`, async ({ page }) => {
      const fixture = await stubIntegrations(page)
      await selectSpeakVoice(page, 'Narrator Ready')
      const expected = selection === 'legacy-preset'
        ? { model: 'kokoro', voice: 'kokoro:bm_george' }
        : { model: 'kitten2', voice: READY_ID }
      if (selection === 'legacy-preset') {
        await page.getByRole('combobox', { name: 'Engine', exact: true }).selectOption('kokoro')
        await page.getByRole('combobox', { name: 'Engine voice', exact: true }).selectOption('kokoro:bm_george')
      }
      await enterIntegrations(page)
      const discoveryStarted = deferred()
      const discoveryGate = deferred()
      const speechRequests = []
      const jobRequests = []
      await page.route((url) => url.pathname === '/v1/models', async (route) => {
        discoveryStarted.resolve()
        await discoveryGate.promise
        await route.fallback()
      })
      await page.route((url) => url.pathname === '/v1/audio/speech', (route) => {
        speechRequests.push(route.request().postDataJSON())
        return route.fulfill({
          status: 400, contentType: 'application/json',
          body: JSON.stringify({ error: { message: 'Discovery race fixture', type: 'invalid_request_error' } }),
        })
      })
      await page.route((url) => url.pathname === '/generate/async', (route) => {
        jobRequests.push(route.request().postDataJSON())
        return route.fulfill({
          status: 400, contentType: 'application/json',
          body: JSON.stringify({ error: 'Wrong active-runtime job path' }),
        })
      })
      try {
        await page.getByTestId('nav-speak').click()
        await expect(page.getByTestId('speak-text-input')).toBeVisible()
        await discoveryStarted.promise
        await page.getByTestId('speak-text-input').fill('Keep the explicitly selected engine.')
        const generate = page.getByTestId('speak-generate-button')
        if (await generate.isDisabled()) {
          // Disabling until discovery completes is also safe; silently taking the active
          // job route is not. An enabled control below is clicked while GET is still held.
          expect(jobRequests).toEqual([])
          discoveryGate.resolve()
          await generate.click()
        } else {
          await generate.click()
          discoveryGate.resolve()
        }
        await expect.poll(() => speechRequests.length + jobRequests.length).toBe(1)
        expect(jobRequests).toEqual([])
        expect(speechRequests).toEqual([expect.objectContaining({
          ...expected, input: 'Keep the explicitly selected engine.', response_format: 'wav',
        })])
        // Speak classifies failures into a friendly headline; the server's raw message is behind Details.
        await page.getByTestId('speak-error').getByRole('button', { name: 'Details' }).click()
        await expect(page.getByTestId('speak-error')).toContainText('Discovery race fixture')
        expect(fixture.mutations.filter((path) => path === '/api-default')).toEqual([])
      } finally {
        discoveryGate.resolve()
      }
    })
  }

  test('Speak "Set current" saves the engine and preset that Generate would use', async ({ page }) => {
    const fixture = await stubIntegrations(page)
    await selectSpeakVoice(page, 'Narrator Ready')
    await page.getByRole('combobox', { name: 'Engine', exact: true }).selectOption('kokoro')
    await page.getByRole('combobox', { name: 'Engine voice', exact: true }).selectOption('kokoro:bm_george')
    const writes = []
    await page.route((url) => url.pathname === '/api-default', (route) => {
      if (route.request().method() !== 'PUT') return route.fallback()
      writes.push(route.request().postDataJSON())
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify(fixture.apiDefault) })
    })

    await page.getByRole('button', { name: 'Set current' }).click()

    await expect.poll(() => writes.length).toBe(1)
    expect(writes[0]).toEqual({ voice: 'kokoro:bm_george', engine: 'kokoro' })
  })

  test('an older default GET snapshot cannot overwrite a successful Set default PUT', async ({ page }) => {
    const fixture = await stubIntegrations(page)
    await openIntegrations(page)
    await expectSnippets(page, 'kokoro:af_heart', 'kokoro')
    const snapshotStarted = deferred()
    const snapshotGate = deferred()
    const putStarted = deferred()
    const putGate = deferred()
    const bindingsStarted = deferred()
    const bindingsGate = deferred()
    const defaultWrites = []
    await page.route((url) => url.pathname === '/api-default', async (route) => {
      if (route.request().method() === 'GET') {
        const snapshot = structuredClone(fixture.apiDefault)
        snapshotStarted.resolve()
        await snapshotGate.promise
        return route.fulfill({ contentType: 'application/json', body: JSON.stringify(snapshot) })
      }
      if (route.request().method() === 'PUT') {
        const request = route.request().postDataJSON()
        defaultWrites.push(request)
        putStarted.resolve()
        await putGate.promise
        fixture.apiDefault.default = {
          ...fixture.apiDefault.default,
          voice: request.voice, display_name: 'bm_george',
        }
        return route.fulfill({ contentType: 'application/json', body: JSON.stringify(fixture.apiDefault) })
      }
      return route.fulfill({ status: 405, body: 'Unexpected default method' })
    })
    await page.route((url) => url.pathname === '/voices/engines', async (route) => {
      bindingsStarted.resolve()
      await bindingsGate.promise
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify(fixture.bindings) })
    })
    const oldResponse = page.waitForResponse((response) =>
      new URL(response.url()).pathname === '/api-default' && response.request().method() === 'GET',
    )
    const committedResponse = page.waitForResponse((response) =>
      new URL(response.url()).pathname === '/api-default' && response.request().method() === 'PUT',
    )
    const bindingsResponse = page.waitForResponse((response) =>
      new URL(response.url()).pathname === '/voices/engines',
    )
    try {
      // Start the public PUT while the table is usable. A refresh disables Set default,
      // so create the overlap through its public focus listener after the PUT has begun.
      const target = await showRow(page, 'kokoro:bm_george')
      await target.getByTestId('set-default').click()
      await putStarted.promise
      await page.evaluate(() => window.dispatchEvent(new Event('focus')))
      await Promise.all([snapshotStarted.promise, bindingsStarted.promise])
      putGate.resolve()
      await committedResponse
      await expect(target.getByText('API default')).toBeVisible()
      await expectSnippets(page, 'kokoro:bm_george', 'kokoro')
      expect(defaultWrites).toEqual([{ voice: 'kokoro:bm_george' }])
      expect(fixture.mutations.filter((path) => path === '/api-default')).toEqual(['/api-default'])

      bindingsGate.resolve()
      await bindingsResponse
      snapshotGate.resolve()
      await oldResponse
      await expect(page.getByTestId('ids-refresh')).toBeEnabled()
      await expect(target.getByText('API default')).toBeVisible()
      await expectSnippets(page, 'kokoro:bm_george', 'kokoro')
    } finally {
      snapshotGate.resolve()
      bindingsGate.resolve()
      putGate.resolve()
    }
  })
})
