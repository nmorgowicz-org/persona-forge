// Plan §5.1: the global engine status chip in the shell header. Every page shows the active
// engine, its state (Ready / Loading / Warming / Error) and device; clicking it opens Runtime.
//
// State is driven two ways, both documented for this suite:
//   - GET /engines is stubbed at the API boundary with real payload shapes (a pack engine that
//     is really installed means gigabytes of weights — the same approach §5.5/§5.6 used), because
//     the Playwright webServer runs ONE shared fake server for the whole suite.
//   - model-load and startup-failure states use the fake server's /_test/* control endpoints
//     (see _install_test_controls in tests/ui/fixtures/fake_model_server.py), with a reset in
//     finally so the shared server stays healthy for the next spec.
import { test, expect } from '@playwright/test'

function pocketCard(over = {}) {
  return {
    id: 'pocket-tts',
    label: 'Pocket TTS',
    description: 'Low-resource CPU engine with local cloning and a curated built-in catalog.',
    kind: 'builtin',
    version: null,
    runtime: 'python-cpu',
    source: 'kyutai/pocket-tts',
    license: 'see upstream',
    active: true,
    api_default: false,
    capabilities: { presets: true, clone: true },
    state: {
      status: 'built-in',
      artifacts_present: 0,
      artifacts_total: 0,
      disk_bytes: 0,
      verified: true,
      errors: [],
    },
    requirements: [],
    install_check: null,
    benchmark: null,
    pack: null,
    ...over,
  }
}

function kittenCard(loadStatus, over = {}) {
  return {
    id: 'kitten2',
    label: 'Kitten TTS 2',
    description: 'A fast English engine with prepared saved voices.',
    kind: 'pack',
    version: '0.2.4',
    runtime: 'python-mlx',
    source: null,
    license: 'Apache-2.0',
    active: false,
    api_default: true,
    capabilities: { presets: true, clone: true },
    state: {
      status: 'verified',
      artifacts_present: 3,
      artifacts_total: 3,
      disk_bytes: 1024,
      verified: true,
      errors: [],
    },
    requirements: [],
    install_check: {
      outcome: 'ok',
      rtf: 0.4,
      compute_seconds: 0.5,
      audio_seconds: 1.2,
      device: 'mps',
      mode: 'compiled',
      warmup_seconds: 33,
      load_average: null,
      note: null,
      error: null,
      at: '2026-10-28T00:00:00Z',
    },
    benchmark: null,
    load_status: loadStatus,
    pack: null,
    ...over,
  }

}

/** Stub GET /engines (exact path only — /voices/engines and friends must pass through). */
function stubEngines(page, engines) {
  return page.route((url) => url.pathname === '/engines', (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ engines, nudge: null }),
    }),
  )
}

test.describe('engine status chip', () => {
  test('shows the active engine, Ready state and device; tooltip explains; click opens Runtime', async ({
    page,
  }) => {
    stubEngines(page, [pocketCard(), kittenCard({ state: 'idle' }, { api_default: false })])
    // The fake server's /health carries no device field; the real one does. Add it the way
    // health-banner.spec.js patches /health: pass the live response through, then amend.
    await page.route('**/health', async (route) => {
      const response = await route.fetch()
      const data = await response.json()
      data.device = 'cpu'
      await route.fulfill({ response, json: data })
    })

    await page.goto('/')
    const chip = page.getByTestId('engine-status-chip')
    await expect(chip).toBeVisible()
    await expect(chip).toContainText('Pocket TTS')
    await expect(page.getByTestId('engine-status-state')).toHaveText('Ready')
    await expect(page.getByTestId('engine-status-device')).toHaveText('cpu')

    // The tooltip gives detail (hover for pointer users).
    await chip.hover()
    await expect(page.getByRole('tooltip')).toContainText('active engine')
    await expect(page.getByRole('tooltip')).toContainText('Ready')
    await expect(page.getByRole('tooltip')).toContainText('cpu')

    // Clicking the chip navigates to the Runtime page with the engine cards.
    await chip.click()
    await expect(page.getByText('Speech engines', { exact: true })).toBeVisible()
  })

  test('the API default\u2019s pack engine wins over the active backend', async ({ page }) => {
    stubEngines(page, [pocketCard({ active: true }), kittenCard({ state: 'idle' })])
    await page.goto('/')
    const chip = page.getByTestId('engine-status-chip')
    await expect(chip).toBeVisible()
    await expect(chip).toContainText('Kitten TTS 2')
    await expect(page.getByTestId('engine-status-state')).toHaveText('Ready')
    await expect(page.getByTestId('engine-status-device')).toHaveText('mps')
  })

  test('a warming pack engine shows Warming with the measured-warm-up note', async ({ page }) => {
    stubEngines(page, [
      pocketCard(),
      kittenCard({ state: 'warming', elapsed_s: 5, estimated_s: 33 }),
    ])
    await page.goto('/')
    const chip = page.getByTestId('engine-status-chip')
    await expect(chip).toBeVisible()
    await expect(page.getByTestId('engine-status-state')).toHaveText('Warming')
    await chip.hover()
    await expect(page.getByRole('tooltip')).toContainText('warming up')
    await expect(page.getByRole('tooltip')).toContainText('Requests wait for it automatically')
  })

  test('a mid-install API default shows Loading, not Error', async ({ page }) => {
    stubEngines(page, [
      pocketCard(),
      kittenCard(undefined, {
        state: {
          status: 'not-installed',
          artifacts_present: 1,
          artifacts_total: 3,
          disk_bytes: 1024,
          verified: false,
          errors: [],
        },
        install_check: null,
        install_job: {
          state: 'running',
          step: 'Downloading weights',
          step_index: 2,
          step_count: 4,
          error: null,
        },
      }),
    ])
    await page.goto('/')
    const chip = page.getByTestId('engine-status-chip')
    await expect(chip).toBeVisible()
    await expect(page.getByTestId('engine-status-state')).toHaveText('Loading')
    await chip.hover()
    await expect(page.getByRole('tooltip')).toContainText('Installing Kitten TTS 2')
    await expect(page.getByRole('tooltip')).toContainText('Downloading weights')
  })

  test('an engine load failure shows Error with the reason in the tooltip', async ({ page }) => {
    stubEngines(page, [
      pocketCard(),
      kittenCard({
        state: 'error',
        error: 'Kitten 2 failed to use your GPU (installed CUDA wheel lacks sm_120).',
      }),
    ])
    await page.goto('/')
    await expect(page.getByTestId('engine-status-state')).toHaveText('Error')
    const chip = page.getByTestId('engine-status-chip')
    await chip.hover()
    await expect(page.getByRole('tooltip')).toContainText('sm_120')
  })

  test('model loading shows Loading, announced politely, then returns to Ready', async ({
    page,
    request,
  }) => {
    stubEngines(page, [pocketCard()])
    await page.goto('/')
    const live = page.getByTestId('engine-status-live')
    await expect(page.getByTestId('engine-status-state')).toHaveText('Ready')
    await expect(live).toContainText('Pocket TTS: Ready')

    try {
      // Longer than the steady-state 5s /health poll so the load window cannot be missed.
      await request.post('/_test/simulate-base-load', { data: { duration_seconds: 8 } })
      await expect(page.getByTestId('engine-status-state')).toHaveText('Loading', {
        timeout: 15_000,
      })
      await expect(live).toContainText('Pocket TTS: Loading')
    } finally {
      await request.post('/_test/reset-state')
    }
    await expect(page.getByTestId('engine-status-state')).toHaveText('Ready', { timeout: 15_000 })
  })

  test('a startup failure shows Error with the server\u2019s reason', async ({ page, request }) => {
    stubEngines(page, [pocketCard()])
    await page.goto('/')
    await expect(page.getByTestId('engine-status-state')).toHaveText('Ready')
    try {
      await request.post('/_test/simulate-startup-failure')
      await expect(page.getByTestId('engine-status-state')).toHaveText('Error', {
        timeout: 15_000,
      })
      const chip = page.getByTestId('engine-status-chip')
      await chip.hover()
      await expect(page.getByRole('tooltip')).toContainText('fake startup error')
    } finally {
      await request.post('/_test/reset-state')
    }
  })

  test('with no engine information the chip renders nothing', async ({ page }) => {
    stubEngines(page, [])
    await page.goto('/')
    await expect(page.getByTestId('speak-text-input')).toBeVisible()
    await expect(page.getByTestId('engine-status-chip')).toHaveCount(0)
  })

  test('keyboard: focus opens the tooltip, Enter opens Runtime', async ({ page }) => {
    stubEngines(page, [pocketCard()])
    await page.goto('/')
    const chip = page.getByTestId('engine-status-chip')
    await expect(chip).toBeVisible()
    await chip.focus()
    await expect(page.getByRole('tooltip')).toBeVisible()
    await chip.press('Enter')
    await expect(page.getByText('Speech engines', { exact: true })).toBeVisible()
  })

  test('the chip is present on other pages and does not overflow a narrow viewport', async ({
    page,
  }) => {
    stubEngines(page, [pocketCard()])
    // Phone width: the sidebar collapses to a toggle (pre-existing responsive behavior), the
    // header keeps every control, and the page must not grow horizontal scroll.
    await page.setViewportSize({ width: 360, height: 720 })
    await page.goto('/')
    await expect(page.getByTestId('engine-status-chip')).toBeVisible()
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(2)

    // Back at a normal width, the same chip follows navigation to another page.
    await page.setViewportSize({ width: 1280, height: 720 })
    await page.getByTestId('nav-voice-library').click()
    await expect(page.getByTestId('engine-status-chip')).toBeVisible()
    await expect(page.getByTestId('engine-status-state')).toHaveText('Ready')

    // The header title must absorb the squeeze on a long-label page, not wrap inside the
    // fixed-height header: shrink on New Voice (Guided), whose description is the longest.
    await page.getByTestId('nav-wizard').click()
    await page.setViewportSize({ width: 360, height: 720 })
    await expect(page.getByTestId('engine-status-chip')).toBeVisible()
    const wizardOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(wizardOverflow).toBeLessThanOrEqual(2)
    const headerBox = await page.locator('header.h-14').boundingBox()
    const titleBox = await page.locator('header.h-14 div.flex.flex-col').boundingBox()
    expect(headerBox && titleBox ? titleBox.height : 0).toBeLessThanOrEqual(
      (headerBox?.height ?? 0) + 1,
    )
  })
})
