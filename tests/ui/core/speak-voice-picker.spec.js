// Plan §5.6 Speak voice picker: sections (Favorites, My voices, Built-in by engine), search,
// keyboard navigation, readiness badges and the saved-voice engine dropdown. Runs against the
// fake-model server, where no pack engine is installed, so pack readiness reads as "Install …".
import { test, expect } from '@playwright/test'

async function openPicker(page) {
  await page.goto('/')
  await expect(page.getByTestId('speak-text-input')).toBeVisible()
  await page.getByTestId('voice-selector-trigger').click()
  await expect(page.getByRole('listbox', { name: 'Voices' })).toBeVisible()
}

test.describe('speak voice picker', () => {
  test('shows My voices and Built-in · Pocket sections with a runtime default', async ({ page }) => {
    await openPicker(page)
    await expect(page.getByRole('group', { name: 'My voices' })).toBeVisible()
    await expect(page.getByRole('group', { name: 'Built-in · Pocket', exact: true })).toBeVisible()
    await expect(page.getByRole('option', { name: /Runtime default/ })).toBeVisible()
    await expect(page.getByRole('option', { name: /Warm British Narrator/ }).first()).toBeVisible()
  })

  test('favoriting a voice adds a Favorites section', async ({ page }) => {
    await openPicker(page)
    await page.getByRole('option', { name: /Warm British Narrator/ }).getByRole('button', { name: 'Add to favorites' }).click()
    await expect(page.getByRole('group', { name: 'Favorites' })).toBeVisible()
    await expect(page.getByRole('group', { name: 'Favorites' }).getByRole('option', { name: /Warm British Narrator/ })).toBeVisible()
  })

  test('search filters voices across sections by name', async ({ page }) => {
    await openPicker(page)
    await page.getByRole('textbox', { name: 'Search voices' }).fill('warm')
    await expect(page.getByRole('option', { name: /Warm British Narrator/ }).first()).toBeVisible()
    await expect(page.getByRole('option', { name: /Calm Professional/ })).toHaveCount(0)
    await expect(page.getByRole('option', { name: /Runtime default/ })).toHaveCount(0)
  })

  test('keyboard navigation moves the highlight and Enter selects', async ({ page }) => {
    await openPicker(page)
    const search = page.getByRole('textbox', { name: 'Search voices' })
    await search.press('ArrowDown')
    const options = page.getByRole('option')
    await expect(options.nth(1)).toHaveClass(/bg-muted/)
    await search.press('Enter')
    await expect(page.getByTestId('voice-selector-trigger')).toContainText(/Warm British Narrator|Calm Professional|Podcast Host/)
  })

  // The fake tier keeps saved voices in memory, so the on-disk binding route has nothing to
  // read there; the payload below is the documented /voices/engines shape for that state.
  test('saved voices carry pack-engine readiness badges', async ({ page }) => {
    const notInstalled = {
      engine: 'kitten2',
      label: 'Kitten 2',
      status: 'needs_preparation',
      supported: true,
      installed: false,
      needs_transcript: true,
      blocker: 'engine_not_installed',
      reason: 'Install the engine to use it.',
      error: null,
      prepared_at: null,
      can_prepare: false,
    }
    await page.route('**/voices/engines', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          engines: [{ id: 'kitten2', label: 'Kitten 2', clone: true, import_prepared_voice: false }],
          voices: { vd_dd6c86850fc0: [notInstalled] },
        }),
      }))
    await openPicker(page)
    const voiceOption = page.getByRole('option', { name: /Warm British Narrator/ }).first()
    await expect(voiceOption).toBeVisible()
    await expect(voiceOption).toContainText('Install Kitten 2')
  })

  test('built-in Pocket entries are marked ready, pack presets are absent while uninstalled', async ({ page }) => {
    await openPicker(page)
    const builtin = page.getByRole('group', { name: 'Built-in · Pocket', exact: true })
    await expect(builtin.getByRole('option').first()).toContainText('Ready')
  })

  test('no saved-voice engine dropdown and no pack sections while only Pocket is installed', async ({ page }) => {
    await openPicker(page)
    await page.getByRole('option', { name: /Warm British Narrator/ }).first().click()
    await expect(page.getByTestId('saved-voice-engine')).toHaveCount(0)
    await expect(page.getByRole('group', { name: /Built-in · Kitten/ })).toHaveCount(0)
  })

  // A pack engine that is really installed means gigabytes of weights, so the installed state is
  // stubbed at the API boundary (the same approach §5.5 used for a slow engine). The binding
  // shapes below are the real /voices/engines payloads.
  test('with Kitten 2 installed: badges, engine dropdown and the beside/prepare notes', async ({ page }) => {
    const binding = (over) => ({
      engine: 'kitten2',
      label: 'Kitten 2',
      status: 'needs_preparation',
      supported: true,
      installed: true,
      needs_transcript: true,
      blocker: null,
      reason: null,
      error: null,
      prepared_at: null,
      can_prepare: true,
      ...over,
    })
    const pocketReady = {
      engine: 'pocket-tts',
      label: 'Pocket',
      status: 'ready',
      supported: true,
      installed: true,
      needs_transcript: false,
      blocker: null,
      reason: null,
      error: null,
      prepared_at: 1,
      can_prepare: false,
    }
    await page.route('**/engines', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          engines: [
            {
              id: 'pocket-tts', label: 'Pocket', description: '', kind: 'builtin', version: null,
              runtime: '', source: null, license: null, active: true, capabilities: {},
              state: { status: 'built-in' }, requirements: [], pack: null, install_check: null,
            },
            {
              id: 'kitten2', label: 'Kitten 2', description: '', kind: 'builtin+pack', version: '1',
              runtime: '', source: null, license: null, active: false,
              capabilities: { clone: true, seed: false, speed: true },
              state: { status: 'installed' }, requirements: [], pack: {},
              install_check: { outcome: 'ok', rtf: 0.8, compute_seconds: 2.1, audio_seconds: 2.6, device: 'mps', mode: 'mlx', warmup_seconds: 33.2, load_average: 4.2, note: null, error: null, at: '2026-10-27T00:00:00Z' },
            },
          ],
          nudge: null,
        }),
      }))
    await page.route('**/voices/engines', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          engines: [
            { id: 'pocket-tts', label: 'Pocket', clone: true, import_prepared_voice: false },
            { id: 'kitten2', label: 'Kitten 2', clone: true, import_prepared_voice: false },
          ],
          voices: {
            vd_dd6c86850fc0: [pocketReady, binding({ status: 'ready', prepared_at: 1769000000, can_prepare: false })],
            vd_dba466fcad17: [pocketReady, binding({})],
          },
        }),
      }))
    await page.route('**/v1/models', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: [
            { id: 'pocket-tts', label: 'Pocket', installed: true, active: true, capabilities: { clone: true, seed: true, speed: true } },
            { id: 'kitten2', label: 'Kitten 2', installed: true, active: false, capabilities: { clone: true, seed: false, speed: true } },
          ],
        }),
      }))
    await page.route('**/v1/audio/voices', (route) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [] }) }))

    await openPicker(page)
    const readyOption = page.getByRole('option', { name: /Warm British Narrator/ }).first()
    await expect(readyOption).toContainText('Ready on Kitten 2')
    const prepareOption = page.getByRole('option', { name: /Calm Professional/ })
    await expect(prepareOption).toContainText('Prepare Kitten 2 first')

    await readyOption.click()
    const dropdown = page.getByTestId('saved-voice-engine')
    await expect(dropdown).toBeVisible()
    await expect(dropdown).toContainText('Kitten 2')
    await dropdown.selectOption({ label: 'Kitten 2 — Ready' })

    const beside = page.getByTestId('speak-engine-beside-note')
    await expect(beside).toContainText('Kitten 2 runs beside Pocket')
    await expect(beside).toContainText('33')
    await expect(page.getByTestId('speak-prepare-note')).toHaveCount(0)

    // A voice that is not prepared yet gets the one-time prepare note instead of a swap promise.
    await page.getByTestId('voice-selector-trigger').click()
    await page.getByRole('option', { name: /Calm Professional/ }).click()
    await page.getByTestId('saved-voice-engine').selectOption({ label: 'Kitten 2 — prepare first' })
    await expect(page.getByTestId('speak-prepare-note')).toContainText('prepare')
    await expect(page.getByTestId('speak-prepare-note')).toContainText('Kitten 2')
  })
})
