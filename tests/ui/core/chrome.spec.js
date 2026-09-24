import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { test, expect } from '@playwright/test'

// B-P6: chrome depth, header grammar, info strip, and the brand mark (audit A10 -- ad-hoc
// radii; A11 -- the product had no mark at all, and its favicon was byte-identical to the Vite
// scaffold's).
//
// RED-first: every test must fail on unmodified code.

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO = resolve(HERE, '../../..')
const read = (path) => readFileSync(resolve(REPO, path))

const CRUCIBLE_SVG = 'assets/brand/concepts/persona-forge/hero-v2/finalists/signal-crucible/svg'

test.describe('B-P6: chrome, header grammar, and brand', () => {
  test('the shipped favicon is the Signal Crucible mark, byte for byte', async () => {
    const favicon = read('frontend/public/favicon.svg')
    const canonical = read(`${CRUCIBLE_SVG}/favicon.svg`)
    expect(favicon.equals(canonical), 'frontend/public/favicon.svg differs from the selected mark').toBe(true)
    // ...and the copy the app serves at /favicon.svg is the same file.
    expect(read('src/persona_forge/static/favicon.svg').equals(canonical)).toBe(true)
  })

  test('the sidebar brand tile is the product mark, not a stock icon', async ({ page }) => {
    await page.goto('/')
    const mark = page.getByTestId('app-brand-mark')
    await expect(mark).toBeVisible()
    expect(await mark.evaluate((el) => el.tagName)).toBe('IMG')
    expect(await mark.getAttribute('src')).toContain('favicon.svg')
    // The stock lucide tile is gone from the brand slot.
    expect(await mark.locator('svg').count()).toBe(0)
  })

  test('a control with data-help explains itself in the info strip', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-voice-design').click()
    await page.getByTestId('engine-omnivoice').click()

    // The high-pitch note is genuine product knowledge, so it survives as design: it appears
    // when the control it is about is hovered, not as a paragraph read before any choice.
    const help = page.locator('[data-help]:not([data-help=""])').first()
    await expect(help).toBeVisible({ timeout: 15000 })
    const text = await help.getAttribute('data-help')
    await help.hover()

    // The strip holds nothing until there is something to say -- a permanent empty bar would
    // be chrome for its own sake.
    const strip = page.getByTestId('info-strip')
    await expect(strip).toBeVisible()
    await expect(strip).toHaveAttribute('role', 'status')
    await expect(strip).toContainText(text.slice(0, 24))
  })

  test('the banners share one shape and one tone vocabulary', async ({ page }) => {
    // Two banners at once, deliberately different tones: a degraded health response with a
    // loading message gives the danger bar, and a model swap on the Voice Design page gives
    // the neutral one. They must present the same root contract.
    await page.route('**/health', async (route) => {
      const response = await route.fetch()
      const body = await response.json()
      await route.fulfill({
        response,
        json: {
          ...body,
          service_started: false,
          loading_message: 'Loading the model…',
          status: 'error',
          error: 'probe',
          swap_in_progress: true,
        },
      })
    })
    await page.goto('/')
    await page.getByTestId('nav-voice-design').click()

    const banners = page.getByTestId('app-banner')
    await expect(banners.first()).toBeVisible({ timeout: 15000 })
    await expect.poll(() => banners.count(), { timeout: 15000 }).toBeGreaterThanOrEqual(2)

    const tones = []
    for (let index = 0; index < (await banners.count()); index++) {
      const tone = await banners.nth(index).getAttribute('data-tone')
      expect(tone, `banner ${index} has no data-tone`).toBeTruthy()
      tones.push(tone)
    }
    // Same shape, and the tone vocabulary is actually used rather than defaulted.
    expect(new Set(tones).size, `tones: ${tones.join(', ')}`).toBeGreaterThan(1)
  })

  test('every page opens with the same header band', async ({ page }) => {
    const pages = [
      ['speak', 'nav-speak'],
      ['voice-design', 'nav-voice-design'],
      ['voice-library', 'nav-voice-library'],
      ['voice-edit', 'nav-voice-edit'],
      ['stitch-studio', 'nav-stitch-studio'],
      ['integrations', 'nav-integrations'],
      ['runtime', 'nav-runtime'],
    ]
    await page.goto('/')
    for (const [name, nav] of pages) {
      await page.getByTestId(nav).click()
      const header = page.getByTestId('page-header')
      await expect(header, `${name} has no header band`).toBeVisible({ timeout: 15000 })
      // Title, context line, and the right-aligned action slot: one form, same content.
      await expect(header.getByTestId('page-title')).toBeVisible()
      expect((await header.getByTestId('page-title').textContent())?.trim().length).toBeGreaterThan(2)
    }
  })

  test('a tooltip names an icon-only control but never renames a labelled one', async ({ page }) => {
    // The app's tooltip layer moves `title` to `data-app-tooltip` and removes the attribute.
    // Native `title` does supply an accessible name, so an icon-only control must keep one --
    // but an `aria-label` *overrides* a button's own text, so copying the tooltip onto a
    // labelled control renames it. These tooltips describe what the control will do next
    // ("Play from playhead", "Pause"), which is not the control's name.
    await page.goto('/')
    await page.evaluate(() => {
      const bare = document.createElement('button')
      bare.id = 'probe-bare'
      bare.setAttribute('title', 'Restart the transport')
      document.body.appendChild(bare)

      const labelled = document.createElement('button')
      labelled.id = 'probe-labelled'
      labelled.setAttribute('title', 'Play from playhead')
      labelled.textContent = 'Original'
      document.body.appendChild(labelled)
    })

    await expect
      .poll(() => page.evaluate(() => document.getElementById('probe-bare')?.getAttribute('aria-label')))
      .toBe('Restart the transport')
    expect(await page.evaluate(() => document.getElementById('probe-labelled')?.hasAttribute('aria-label'))).toBe(false)
    await expect(page.locator('#probe-labelled')).toHaveAccessibleName('Original')

    // ...and the surface that broke: the A/B lane buttons keep their visible names, so a
    // consumer can still find them by what they say.
    await page.getByTestId('nav-voice-edit').click()
    await expect(page.getByTestId('voice-edit-page')).toBeVisible({ timeout: 15000 })
    await page.getByTestId('voice-edit-picker').selectOption({ index: 1 })
    await expect(page.getByTestId('alignment-compare').getByRole('button', { name: 'Original' })).toBeVisible({ timeout: 20000 })
  })
})
