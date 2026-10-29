// Plan §5.10: optional Compare "auto-check" hints (word error rate, speaker similarity) under each
// clip. The hints are offline and non-authoritative, never run until a Check click, never download
// until the "Enable auto-check" button is clicked, and in blind mode only exist after the reveal.
//
// The Compare tab needs two installed engines and a generated clip, which the shared fake server
// does not have, so the API boundary is stubbed with the documented payload shapes (the same
// approach as engine-status-chip.spec.js). /compare/auto-check* is stubbed with a small state
// machine; the real routes are covered by tests/tier2_backend/test_compare_autocheck_route.py.
import { test, expect } from '@playwright/test'

const SAMPLE = 'Hello there. Your timer is set for ten minutes, and the kitchen lights are now on.'
const CLONE_ID = 'vd_aabbccddeeff'

function wavBytes(seconds = 1, freq = 220, sr = 16000) {
  const n = Math.floor(seconds * sr)
  const buf = Buffer.alloc(44 + n * 2)
  buf.write('RIFF', 0)
  buf.writeUInt32LE(36 + n * 2, 4)
  buf.write('WAVEfmt ', 8)
  buf.writeUInt32LE(16, 16)
  buf.writeUInt16LE(1, 20)
  buf.writeUInt16LE(1, 22)
  buf.writeUInt32LE(sr, 24)
  buf.writeUInt32LE(sr * 2, 28)
  buf.writeUInt16LE(2, 32)
  buf.writeUInt16LE(16, 34)
  buf.write('data', 36)
  buf.writeUInt32LE(n * 2, 40)
  for (let i = 0; i < n; i++) buf.writeInt16LE(Math.round(12000 * Math.sin((2 * Math.PI * freq * i) / sr)), 44 + i * 2)
  return buf
}

const MODELS_MISSING = [
  { id: 'whisper-tiny-en', label: 'Speech-to-text (Whisper tiny.en)', purpose: 'word_error_rate', available: false, size_bytes: 78090594, size_label: '78 MB' },
  { id: 'wavlm-base-plus-sv', label: 'Speaker similarity (WavLM-SV)', purpose: 'speaker_similarity', available: false, size_bytes: 404605907, size_label: '405 MB' },
]
const available = (models) => models.map((m) => ({ ...m, available: true }))

async function stubCompare(page, { modelsPresent = false, checkReply } = {}) {
  const state = {
    models: modelsPresent ? available(MODELS_MISSING) : MODELS_MISSING,
    job: { state: 'idle', step: '', step_index: 0, step_count: 0, error: null },
    polls: 0,
    installs: [],
    checks: [],
  }
  const json = (route, value, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) })
  const statusBody = () => ({ models: state.models, job: state.job, disclaimer: 'x' })

  await page.route((url) => url.pathname === '/v1/models', (route) =>
    json(route, {
      data: ['alpha', 'beta'].map((id) => ({
        id, label: id === 'alpha' ? 'Alpha TTS' : 'Beta TTS', installed: true, capabilities: { clone: true },
      })),
    }))
  await page.route((url) => url.pathname === '/v1/audio/voices', (route) =>
    json(route, {
      data: [
        { voice_id: 'alpha:one', engine: 'alpha', kind: 'preset', display_name: 'Alpha one' },
        { voice_id: 'beta:one', engine: 'beta', kind: 'preset', display_name: 'Beta one' },
        { voice_id: CLONE_ID, engine: null, kind: 'library', display_name: 'My clone' },
      ],
    }))
  await page.route((url) => url.pathname === '/v1/audio/speech', (route) =>
    route.fulfill({ status: 200, contentType: 'audio/wav', body: wavBytes() }))
  await page.route((url) => url.pathname === `/voices/${CLONE_ID}`, (route) =>
    json(route, { description: 'My clone', sample_text: 'Reference words.', audio_base64: wavBytes(0.5).toString('base64') }))
  await page.route((url) => url.pathname === '/compare/results', (route) => json(route, { count: 0, summary: [] }))
  await page.route((url) => url.pathname === '/compare/auto-check/status', (route) => {
    state.polls += 1
    if (state.job.state === 'running' && state.polls > 1) {
      state.models = available(MODELS_MISSING)
      state.job = { ...state.job, state: 'done', step: 'Downloaded' }
    }
    return json(route, statusBody())
  })
  await page.route((url) => url.pathname === '/compare/auto-check/install', (route) => {
    state.installs.push(route.request().postDataJSON())
    state.polls = 0
    state.job = { state: 'running', step: 'Downloading Speech-to-text (Whisper tiny.en) (78 MB)', step_index: 1, step_count: 2, error: null }
    return json(route, { started: true, ...statusBody() }, 202)
  })
  await page.route((url) => url.pathname === '/compare/auto-check', (route) => {
    const body = route.request().postDataBuffer().toString('latin1')
    state.checks.push({
      text: /name="text"\r\n\r\n([^\r]*)/.exec(body)?.[1] ?? null,
      reference: /name="reference_voice_id"\r\n\r\n([^\r]*)/.exec(body)?.[1] ?? null,
      hasAudio: body.includes('name="audio"') && body.includes('RIFF'),
    })
    if (checkReply) return checkReply(route, json)
    return json(route, {
      wer: 0.0625,
      transcript: 'hello there your timer is set for 10 minutes',
      similarity: 0.93,
      details: { substitutions: 1, deletions: 0, insertions: 0, reference_words: 16, hypothesis_words: 16 },
      notes: [],
      disclaimer: 'x',
      models: state.models,
    })
  })
  return state
}

async function openCompare(page) {
  await page.goto('/')
  await page.getByTestId('nav-voice-library').click()
  await page.getByTestId('voice-library-tab-compare').click()
  await expect(page.getByRole('button', { name: 'Generate' })).toBeVisible()
  // Slot 1 is the cloned voice so similarity applies; slot 2 is a plain preset.
  await page.getByLabel('Voice for slot 1').selectOption(CLONE_ID)
}

test.describe('compare auto-check', () => {
  test('blind mode shows no hints and downloads nothing until after the reveal and an explicit click', async ({ page }) => {
    const state = await stubCompare(page)
    await openCompare(page)
    await page.getByRole('button', { name: 'Generate' }).click()
    await expect(page.getByRole('button', { name: 'Play' })).toHaveCount(2)

    // Blind and not yet revealed: engines stay hidden and there is no auto-check UI at all.
    const clipCards = page.getByRole('button', { name: 'Play' }).locator('xpath=ancestor::div[contains(@class,"rounded-control")][1]')
    await expect(clipCards).toHaveCount(2)
    for (const card of await clipCards.all()) await expect(card).not.toContainText(/Alpha TTS|Beta TTS/)
    await expect(page.getByTestId('auto-check')).toHaveCount(0)
    await expect(page.getByTestId('auto-check-setup')).toHaveCount(0)
    await expect(page.getByText(/auto-check hints appear after you reveal/i)).toBeVisible()

    await page.getByRole('button', { name: /Reveal engines/ }).click()
    const setup = page.getByTestId('auto-check-setup')
    await expect(setup).toBeVisible()
    await expect(setup).toContainText('nothing is downloaded until you ask')
    const enable = setup.getByRole('button', { name: 'Enable auto-check: download models (483 MB)' })
    await expect(enable).toBeVisible()
    // Hints exist but cannot run without the speech-to-text model.
    await expect(page.getByTestId('auto-check')).toHaveCount(2)
    await expect(page.getByTestId('auto-check').first().getByRole('button', { name: 'Check' })).toBeDisabled()
    expect(state.installs).toEqual([])
    expect(state.checks).toEqual([])

    await enable.click()
    await expect(page.getByTestId('auto-check-download')).toContainText('Downloading')
    expect(state.installs).toEqual([{ models: ['whisper-tiny-en', 'wavlm-base-plus-sv'] }])
    await expect(page.getByTestId('auto-check-setup')).toHaveCount(0)
    await expect(page.getByTestId('auto-check').first().getByRole('button', { name: 'Check' })).toBeEnabled()
    expect(state.checks).toEqual([]) // enabling never runs a check by itself
  })

  test('Check scores one clip on click with the disclaimer, similarity only for the cloned slot', async ({ page }) => {
    const state = await stubCompare(page, { modelsPresent: true })
    await openCompare(page)
    await page.getByLabel(/Blind mode/).uncheck()
    await page.getByRole('button', { name: 'Generate' }).click()
    await expect(page.getByRole('button', { name: 'Play' })).toHaveCount(2)

    const hints = page.getByTestId('auto-check')
    await expect(hints).toHaveCount(2)
    await expect(page.getByTestId('auto-check-setup')).toHaveCount(0) // everything already on disk
    for (const hint of await hints.all()) {
      await expect(hint).toContainText('Not calibrated for synthetic voices; never replaces the rating.')
      await expect(hint.getByTestId('auto-check-result')).toHaveCount(0) // nothing ran yet
    }
    expect(state.checks).toEqual([])

    // Slot 1: the cloned voice.
    await hints.nth(0).getByRole('button', { name: 'Check' }).click()
    await expect(hints.nth(0).getByTestId('auto-check-wer')).toContainText('Word error: 6.3%')
    await expect(hints.nth(0).getByTestId('auto-check-wer')).toContainText('hello there your timer is set for 10 minutes')
    await expect(hints.nth(0).getByTestId('auto-check-similarity')).toContainText('0.93')
    expect(state.checks).toHaveLength(1)
    expect(state.checks[0]).toEqual({ text: SAMPLE, reference: CLONE_ID, hasAudio: true })

    // Slot 2: a preset has no reference, so no similarity row and no reference id is sent.
    await hints.nth(1).getByRole('button', { name: 'Check' }).click()
    await expect(hints.nth(1).getByTestId('auto-check-wer')).toBeVisible()
    await expect(hints.nth(1).getByTestId('auto-check-similarity')).toHaveCount(0)
    expect(state.checks).toHaveLength(2)
    expect(state.checks[1].reference).toBeNull()
  })

  test('a refused or failed check is shown without inventing a score', async ({ page }) => {
    await stubCompare(page, {
      modelsPresent: true,
      checkReply: (route, json) => json(route, { error: 'Another auto-check is still running.', code: 'busy' }, 429),
    })
    await openCompare(page)
    await page.getByLabel(/Blind mode/).uncheck()
    await page.getByRole('button', { name: 'Generate' }).click()
    const hint = page.getByTestId('auto-check').first()
    await hint.getByRole('button', { name: 'Check' }).click()
    await expect(hint.getByRole('alert')).toContainText('Another auto-check is still running.')
    await expect(hint.getByTestId('auto-check-result')).toHaveCount(0)
  })
})
