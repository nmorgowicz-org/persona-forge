// Runtime → Speech engines: the Repair button must agree with the messages that tell the user to
// "choose Repair". A pack whose files verify can still fail to load (e.g. Pocket Lite installed
// with another pocket-tts release); that card must offer Repair, a healthy verified card must not.
//
// GET /engines is stubbed at the API boundary with real payload shapes (a pack engine that is
// really installed means weights on disk), like engine-status-chip.spec.js.
import { test, expect } from '@playwright/test'

const MISMATCH =
  'Pocket Lite was installed with pocket-tts 4.0.0 but the app now has 4.0.1. Choose Repair in ' +
  'Runtime → Speech engines to download the matching weights.'

function builtinCard() {
  return {
    id: 'pocket-tts',
    label: 'Pocket TTS',
    description: 'Low-resource CPU engine.',
    kind: 'builtin',
    version: null,
    runtime: 'python-cpu',
    source: 'kyutai/pocket-tts',
    license: 'see upstream',
    active: true,
    api_default: false,
    capabilities: { presets: true, clone: true },
    state: { status: 'built-in', artifacts_present: 0, artifacts_total: 0, disk_bytes: 0, verified: true, errors: [] },
    requirements: [],
    install_check: null,
    benchmark: null,
    pack: null,
  }
}

function liteCard({ status = 'verified', loadStatus = { state: 'idle' } } = {}) {
  return {
    id: 'pocket-lite',
    label: 'Pocket Lite (18M)',
    description: 'A smaller Pocket model that still clones.',
    kind: 'pack',
    version: '4.0.1',
    runtime: 'python-cpu',
    source: 'kyutai/pocket-tts',
    license: 'CC-BY-4.0',
    active: false,
    api_default: false,
    capabilities: { presets: true, clone: true },
    state: {
      status,
      artifacts_present: status === 'not-installed' ? 0 : 1,
      artifacts_total: 1,
      disk_bytes: 1024,
      verified: status === 'verified',
      errors: [],
    },
    requirements: [],
    install_check: null,
    benchmark: null,
    load_status: loadStatus,
    pack: null,
  }
}

async function openRuntimeWith(page, lite) {
  await page.route((url) => url.pathname === '/engines', (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ engines: [builtinCard(), lite], nudge: null }),
    }),
  )
  await page.goto('/')
  await page.getByTestId('nav-runtime').click()
  const card = page.locator('#speech-engines-list > div').filter({ hasText: 'pocket-lite' })
  await expect(card).toBeVisible()
  return card
}

test.describe('engine card Repair button', () => {
  test('a verified pack that failed to load shows its error and offers Repair', async ({ page }) => {
    const card = await openRuntimeWith(
      page,
      liteCard({ loadStatus: { state: 'error', error: MISMATCH } }),
    )
    await expect(card).toContainText('Choose Repair')
    await expect(card.getByRole('button', { name: 'Repair', exact: true })).toBeEnabled()
  })

  test('a healthy verified pack has no Repair or Install button', async ({ page }) => {
    const card = await openRuntimeWith(page, liteCard())
    await expect(card.getByRole('button', { name: 'Verify hashes' })).toBeVisible()
    await expect(card.getByRole('button', { name: 'Repair', exact: true })).toHaveCount(0)
    await expect(card.getByRole('button', { name: 'Install', exact: true })).toHaveCount(0)
  })

  test('an invalid pack offers Repair and a missing pack offers Install', async ({ page }) => {
    const invalid = await openRuntimeWith(page, liteCard({ status: 'invalid' }))
    await expect(invalid.getByRole('button', { name: 'Repair', exact: true })).toBeVisible()
    await page.unrouteAll({ behavior: 'ignoreErrors' })

    const missing = await openRuntimeWith(page, liteCard({ status: 'not-installed' }))
    await expect(missing.getByRole('button', { name: 'Install', exact: true })).toBeVisible()
  })
})
