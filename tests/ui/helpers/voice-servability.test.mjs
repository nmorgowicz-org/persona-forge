import assert from 'node:assert/strict'
import { registerHooks } from 'node:module'
import test from 'node:test'

// Use Node 26's native TypeScript stripping; resolve the same source alias as Vite.
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier.startsWith('@/')) {
      return nextResolve(new URL(`../../../frontend/src/${specifier.slice(2)}.ts`, import.meta.url).href, context)
    }
    return nextResolve(specifier, context)
  },
})
const { buildServableVoiceRows, engineChipText, engineSortTier, firstServableEngine, speakSelectionFallback } =
  await import('../../../frontend/src/lib/voiceServability.ts')

const voiceId = 'vd_aabbccddeeff'
const saved = {
  voice_id: voiceId, display_name: 'My voice', description: '', sample_text: 'The exact words.',
  sample_text_source: 'user', language: 'English', created_at: 1,
}
function binding(engine, over = {}) {
  return {
    engine, label: engine, status: 'ready', supported: true, installed: true,
    needs_transcript: engine === 'kitten2', blocker: null, reason: null, error: null,
    prepared_at: 1, can_prepare: false, ...over,
  }
}
function card(id, over = {}) {
  return {
    id, label: id, description: '', kind: id === 'pocket-tts' ? 'builtin' : 'pack',
    version: null, runtime: 'python-cpu', source: null, license: null,
    active: id === 'pocket-tts', capabilities: { clone: true, presets: true },
    state: { status: id === 'pocket-tts' ? 'built-in' : 'verified', artifacts_present: 1,
      artifacts_total: 1, disk_bytes: 1, verified: true, errors: [] },
    requirements: [], pack: null, load_status: { state: 'idle' }, ...over,
  }
}
function preset(id, engine, over = {}) {
  return {
    voice_id: id, builtin_voice: id.split(':')[1], backend: engine === 'pocket-tts' ? 'pocket_tts' : engine,
    engine, engine_label: engine, display_name: id, source: 'bundled', license: 'test',
    language: 'English', language_code: 'en', category: 'conversation', note: '', prompt: '',
    requires_backend: null, installed: true, ...over,
  }
}
function input(over = {}) {
  return {
    catalog: [], saved: [saved], bindings: { [voiceId]: [binding('pocket-tts'), binding('kitten2'), binding('pocket-lite')] },
    runtimeTtsBackend: 'pocket_tts', engines: [card('pocket-tts'), card('kitten2'), card('pocket-lite')],
    serviceReady: true, pocketCloningAvailable: true, enforceLanguage: false, ...over,
  }
}
function savedRow(over = {}) {
  return buildServableVoiceRows(input(over)).find((row) => row.id === voiceId)
}
function engine(row, id) { return row.engines.find((item) => item.id === id) }

test('saved selection uses the exact selected engine, or the active runtime for null', () => {
  const row = savedRow()
  assert.equal(speakSelectionFallback([row], voiceId, null), null)
  assert.equal(speakSelectionFallback([row], voiceId, 'kitten2'), null)
  assert.equal(firstServableEngine(row, null)?.id, null)
  assert.equal(firstServableEngine(row, 'pocket-lite')?.id, 'pocket-lite')
})

test('an unavailable selected engine never changes to a different prepared engine', () => {
  const row = savedRow({ bindings: { [voiceId]: [binding('pocket-tts'),
    binding('kitten2', { installed: false }), binding('pocket-lite')] } })
  assert.equal(row.servable, true)
  assert.equal(engine(row, 'pocket-lite').servable, true)
  assert.equal(firstServableEngine(row, 'kitten2'), null)
  const fallback = speakSelectionFallback([row], voiceId, 'kitten2')
  assert.equal(fallback.row, row)
  assert.match(fallback.reason, /Install Kitten 2/)
  assert.match(fallback.reason, /API default/)
})

test('unknown, absent, and unsupported selections fall back without guessing another voice', () => {
  const row = savedRow()
  assert.match(speakSelectionFallback([row], null, null).reason, /No voice/)
  assert.match(speakSelectionFallback([row], 'vd_deleted', null).reason, /not in the catalog/)
  assert.match(speakSelectionFallback([row], voiceId, 'kokoro').reason, /not supported|cannot serve/)
})

for (const engineId of ['kitten2', 'pocket-lite']) {
  for (const status of ['ready', 'needs_preparation', 'failed', 'preparing']) {
    test(`${engineId} ${status} remains eligible for route-supported lazy preparation/retry`, () => {
      const row = savedRow({ bindings: { [voiceId]: [binding('pocket-tts'), binding(engineId, {
        status, error: status === 'failed' ? 'previous encoder failure' : null,
      })] } })
      assert.equal(engine(row, engineId).servable, true)
      assert.equal(speakSelectionFallback([row], voiceId, engineId), null)
    })
  }
  test(`${engineId} ready does not override an uninstalled binding`, () => {
    const row = savedRow({ bindings: { [voiceId]: [binding('pocket-tts'), binding(engineId, { installed: false })] } })
    assert.equal(engine(row, engineId).servable, false)
    assert.match(engine(row, engineId).reason, /Install/)
  })
  test(`${engineId} ready does not override a removed or invalid pack card`, () => {
    for (const status of ['not-installed', 'invalid']) {
      const row = savedRow({ engines: [card('pocket-tts'), card(engineId, {
        state: { status, artifacts_present: 0, artifacts_total: 1, disk_bytes: 0, verified: false, errors: ['bad files'] },
      })] })
      assert.equal(engine(row, engineId).servable, false)
      assert.match(engine(row, engineId).reason, /Install|Repair/)
    }
  })
}

test('missing reference/binding evidence never leaves an unconditional active-engine success', () => {
  for (const bindings of [{}, { [voiceId]: [] }]) {
    const row = savedRow({ bindings })
    assert.equal(row.servable, false)
    assert.equal(engine(row, null).servable, false)
    assert.match(speakSelectionFallback([row], voiceId, null).reason, /reference|readiness/i)
  }
})

test('active runtime requires a ready supported installed baseline, not pack-only partial data', () => {
  for (const baseline of [null, { status: 'needs_preparation' }, { supported: false }, { installed: false }]) {
    const voiceBindings = [binding('kitten2')]
    if (baseline !== null) voiceBindings.unshift(binding('pocket-tts', baseline))
    const row = savedRow({ bindings: { [voiceId]: voiceBindings } })
    assert.equal(engine(row, null).servable, false)
    assert.equal(engine(row, 'kitten2').servable, true)
    assert.notEqual(speakSelectionFallback([row], voiceId, null), null)
  }
})

test('missing selected binding is not replaced by another ready binding', () => {
  const row = savedRow({ bindings: { [voiceId]: [binding('pocket-tts'), binding('pocket-lite')] } })
  assert.notEqual(speakSelectionFallback([row], voiceId, 'kitten2'), null)
})

for (const blocker of ['transcript_missing', 'transcript_unreviewed']) {
  test(`${blocker} blocks Kitten even with a stale ready marker, not Pocket Lite`, () => {
    const row = savedRow({ bindings: { [voiceId]: [binding('pocket-tts'),
      binding('kitten2', { blocker, reason: 'Review the transcript in Voice Library.' }), binding('pocket-lite')] } })
    assert.equal(engine(row, 'kitten2').servable, false)
    assert.match(engine(row, 'kitten2').reason, /transcript/i)
    assert.equal(engine(row, 'pocket-lite').servable, true)
    assert.notEqual(speakSelectionFallback([row], voiceId, 'kitten2'), null)
  })
}

test('fresh saved transcript metadata can conservatively invalidate an older ready binding', () => {
  for (const change of [{ sample_text: '  ' }, { sample_text_source: 'whisper', asr: { severity: 'fail' } }]) {
    const row = savedRow({ saved: [{ ...saved, ...change }] })
    assert.equal(engine(row, 'kitten2').servable, false)
    assert.equal(engine(row, 'pocket-lite').servable, true)
  }
})

test('Pocket cloning capability is independent of pack cloning and Pocket presets', () => {
  for (const pocketCloningAvailable of [false, null]) {
    const rows = buildServableVoiceRows(input({ pocketCloningAvailable,
      catalog: [preset('pocket:vera', 'pocket-tts')] }))
    assert.equal(engine(rows.find((row) => row.id === voiceId), null).servable, false)
    assert.equal(engine(rows.find((row) => row.id === voiceId), 'pocket-lite').servable, true)
    assert.equal(rows.find((row) => row.id === 'pocket:vera').servable, true)
  }
})

test('Pocket presets require the active Pocket backend; pack presets do not', () => {
  const rows = buildServableVoiceRows(input({ runtimeTtsBackend: 'openvino',
    catalog: [preset('pocket:vera', 'pocket-tts'), preset('kitten2:Bruno', 'kitten2')] }))
  assert.equal(rows.find((row) => row.id === 'pocket:vera').servable, false)
  assert.equal(rows.find((row) => row.id === 'kitten2:Bruno').servable, true)
  assert.equal(engine(rows.find((row) => row.id === voiceId), null).servable, true)
})

test('preset implicit namespace is supported, but an explicit different engine is not substituted', () => {
  const rows = buildServableVoiceRows(input({ catalog: [preset('kitten2:Bruno', 'kitten2')] }))
  assert.equal(speakSelectionFallback(rows, 'kitten2:Bruno', null), null)
  assert.equal(speakSelectionFallback(rows, 'kitten2:Bruno', 'kitten2'), null)
  assert.match(speakSelectionFallback(rows, 'kitten2:Bruno', 'pocket-lite').reason, /does not belong|mismatch/)
})

test('Pocket Lite retains the route-supported pocket preset alias', () => {
  const rows = buildServableVoiceRows(input({ runtimeTtsBackend: 'openvino', catalog: [
    preset('pocket:vera', 'pocket-tts'), preset('pocket-lite:vera', 'pocket-lite'),
  ] }))
  assert.equal(speakSelectionFallback(rows, 'pocket:vera', 'pocket-lite'), null)
})

test('preset installation and engine cards must agree; missing card data is not success', () => {
  for (const overrides of [{ engines: [] }, { catalog: [preset('kitten2:Bruno', 'kitten2', { installed: false })] }]) {
    const rows = buildServableVoiceRows(input({ catalog: [preset('kitten2:Bruno', 'kitten2')], ...overrides }))
    assert.equal(rows.find((row) => row.id === 'kitten2:Bruno').servable, false)
  }
})

test('service startup blocks all pairs without initiating work', () => {
  const rows = buildServableVoiceRows(input({ serviceReady: false, catalog: [preset('kitten2:Bruno', 'kitten2')] }))
  assert.ok(rows.every((row) => !row.servable))
})

test('idle/loading/warming preserve the selected engine; only load errors block, with no warmup calls', () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = () => { throw new Error('status helpers must not fetch, prepare, or warm engines') }
  try {
    for (const [state, servable] of [['idle', true], ['ready', true], ['loading', true], ['warming', true], ['error', false]]) {
      const row = savedRow({ engines: [card('pocket-tts'), card('kitten2', { load_status: { state, error: 'worker failed' } })] })
      assert.equal(engine(row, 'kitten2').servable, servable)
      assert.equal(speakSelectionFallback([row], voiceId, 'kitten2') === null, servable)
    }
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('Pocket sorting uses the actual short label and cold-start chips preserve the engine', () => {
  const rows = buildServableVoiceRows(input({ catalog: [preset('pocket:vera', 'pocket-tts')],
    engines: [card('pocket-tts', { load_status: { state: 'loading' } })] }))
  const pocket = rows.find((row) => row.id === 'pocket:vera').engines[0]
  assert.ok(engineSortTier(pocket.label) < engineSortTier('Active engine'))
  assert.equal(engineChipText(pocket), 'Pocket')
})

for (const [language_code, language, eligible] of [
  ['en', 'French', true],
  ['EN-us', 'French', true],
  ['en-GB', 'Unknown', true],
  ['fr-CA', 'English', false],
  ['??', 'English', false],
  ['unknown', 'English', false],
  ['english', 'English', false],
  ['en_US', 'English', false],
  [' en ', 'English', false],
  ['', 'French', true],
  [null, 'French', true],
  [undefined, 'French', true],
]) {
  test(`API language enforcement uses backend code ${String(language_code)}, not label ${language}`, () => {
    const rows = buildServableVoiceRows(input({
      enforceLanguage: true,
      saved: [{ ...saved, language_code, language }],
      catalog: [preset('kitten2:Bruno', 'kitten2', { language_code, language })],
    }))
    for (const row of rows) {
      assert.equal(row.servable, eligible)
      assert.ok(row.engines.every((entry) => entry.servable === eligible))
      assert.equal(speakSelectionFallback(rows, row.id, row.kind === 'saved' ? null : 'kitten2') === null, eligible)
      if (!eligible) {
        for (const entry of row.engines) {
          assert.match(entry.reason, /English/)
          assert.match(entry.reason, /Integrations|API setting/)
        }
      }
    }
  })
}

test('API language enforcement off does not filter non-English saved, preset, or imported voices', () => {
  const rows = buildServableVoiceRows(input({
    enforceLanguage: false,
    saved: [{ ...saved, language: 'French', language_code: 'fr' }],
    catalog: [
      preset('kitten2:FrenchVoice', 'kitten2', { language: 'French', language_code: 'fr' }),
      preset('kitten2:imported-voice', 'kitten2', { category: 'imported', language: 'French', language_code: 'fr' }),
    ],
  }))
  assert.equal(rows.length, 3)
  assert.ok(rows.every((row) => row.servable && row.engines.every((entry) => entry.servable)))
})
