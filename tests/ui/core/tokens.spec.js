import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { test, expect } from '@playwright/test'

// B-P1: the Obsidian material + signal + motion token layer. The look was chosen on the
// look-dev board (CP0b, D1) and its approved values live in the board's own CSS; this spec
// asserts the real app now carries them, that the CTA follows the accent theme (D3), and that
// the new material/type utilities actually resolve.
//
// RED-first: every test must fail on unmodified code because the layer is missing.

const HERE = dirname(fileURLToPath(import.meta.url))
const OBSIDIAN_CSS = resolve(HERE, '../capture/lookdev/obsidian.css')

/** The approved value of a custom property, read from the board that was signed off. */
function boardValue(name) {
  const css = readFileSync(OBSIDIAN_CSS, 'utf8')
  const match = css.match(new RegExp(`--${name}:\\s*([^;]+);`))
  if (!match) throw new Error(`--${name} not found in ${OBSIDIAN_CSS}`)
  return match[1].trim()
}

const cssVar = (page, name) =>
  page.evaluate((n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim(), name)

/** OKLCH components as numbers. The board file and the browser write the same color two ways
 * -- `oklch(0.118 0.004 270)` vs `oklch(11.8% .004 270)` -- so comparing the strings would
 * fail on notation while the color is identical. Compare what the color *is*. */
function parseOklch(value) {
  const match = String(value).match(/oklch\(\s*([\d.]+)(%?)\s+([\d.]+)\s+([\d.]+)/i)
  if (!match) return null
  return {
    l: Number(match[1]) / (match[2] === '%' ? 100 : 1),
    c: Number(match[3]),
    h: Number(match[4]),
  }
}

function expectSameColor(actual, expected, label) {
  const a = parseOklch(actual)
  const b = parseOklch(expected)
  expect(a, `${label}: could not parse ${actual}`).not.toBeNull()
  expect(b, `${label}: could not parse ${expected}`).not.toBeNull()
  expect(Math.abs(a.l - b.l), `${label} lightness: ${actual} vs ${expected}`).toBeLessThan(0.002)
  expect(Math.abs(a.c - b.c), `${label} chroma: ${actual} vs ${expected}`).toBeLessThan(0.002)
  expect(Math.abs(a.h - b.h), `${label} hue: ${actual} vs ${expected}`).toBeLessThan(0.5)
}

test.describe('B-P1: material, signal, and motion tokens', () => {
  test('the dark theme carries the Obsidian neutral values from the approved board', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('html')).toHaveClass(/dark/)

    for (const name of ['background', 'card', 'popover', 'secondary', 'muted', 'accent', 'muted-foreground']) {
      expectSameColor(await cssVar(page, `--${name}`), boardValue(name), `--${name}`)
    }
    // The tighter Obsidian radius and the inset-surface value the board adds on top.
    // Lengths compare numerically too: the browser writes `.3rem` for `0.3rem`.
    expect(Number.parseFloat(await cssVar(page, '--radius'))).toBe(Number.parseFloat(boardValue('radius')))
    expectSameColor(await cssVar(page, '--well'), 'oklch(0.1 0.004 270)', '--well')
  })

  test('the brand CTA follows the accent theme (D3)', async ({ page }) => {
    await page.goto('/')
    for (const theme of ['violet', 'teal', 'amber', 'rose']) {
      await page.evaluate((t) => document.documentElement.setAttribute('data-theme', t), theme)
      const primary = await cssVar(page, '--primary')
      const gradient = await page.evaluate(() => {
        const el = document.createElement('div')
        el.className = 'btn-brand'
        document.body.appendChild(el)
        const value = getComputedStyle(el).backgroundImage
        el.remove()
        return value
      })
      // The primary itself is one of the gradient stops, so the accent is literally in the
      // CTA rather than a separate hard-coded cyan.
      const stops = [...gradient.matchAll(/oklch\([^)]+\)/gi)].map((m) => m[0])
      expect(stops.length, `theme ${theme}: no color stops in ${gradient}`).toBeGreaterThan(0)
      const target = parseOklch(primary)
      expect(
        stops.some((stop) => {
          const s = parseOklch(stop)
          return s && Math.abs(s.l - target.l) < 0.002 && Math.abs(s.c - target.c) < 0.002 && Math.abs(s.h - target.h) < 0.5
        }),
        `theme ${theme}: ${primary} is not a stop in ${gradient}`,
      ).toBe(true)
      expect(gradient).not.toContain('rgb(34, 211, 238)')
    }
  })

  test('the material, glow, and readout utilities resolve', async ({ page }) => {
    await page.goto('/')
    // Each class must change something a consumer can see; "the class exists" alone is not
    // observable, and a rule that computes to the default is indistinguishable from no rule.
    const changed = await page.evaluate(() => {
      const bare = document.createElement('div')
      document.body.appendChild(bare)
      const baseline = getComputedStyle(bare)
      const out = {}
      for (const cls of ['panel-1', 'well', 'glow-active', 'readout', 'micro-label']) {
        const el = document.createElement('div')
        el.className = cls
        document.body.appendChild(el)
        const computed = getComputedStyle(el)
        out[cls] = ['boxShadow', 'filter', 'fontFamily', 'fontVariantNumeric', 'textTransform', 'letterSpacing']
          .filter((prop) => computed[prop] !== baseline[prop])
        el.remove()
      }
      bare.remove()
      return out
    })
    for (const [cls, props] of Object.entries(changed)) {
      expect(props.length, `.${cls} has no computed effect`).toBeGreaterThan(0)
    }
  })
})
