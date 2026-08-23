import { test, expect } from '@playwright/test'

// Font determinism contract (Step 1.5a.5 of the 2026-08-15 screenshot plan,
// docs/plans/archive/screenshots/20260815-screenshot_and_docs_edit.md).
//
// Screenshot reproducibility depends on the UI's faces being bundled (Vite-served,
// same-origin) and the root baseline being explicit. The capture harness'
// assertDeterministicFonts (tests/ui/capture/harness/browser.mjs) is the second line of
// defence at capture time; this spec is the first line of defence and runs on every CI
// e2e lane.
//
// Two measured traps avoided here (plan corrections #39/#40): document.fonts.check()
// returns true whenever a fallback can render the string, and FontFaceSet enumerates
// declared faces regardless of load state (fontsource ships one face per unicode
// subset). So force-load each required family first, then count only faces whose
// status is 'loaded'.

const REQUIRED_FACES = ['Geist Variable', 'Geist Mono Variable']

test.describe('font determinism', () => {
  test('bundled faces load, root baseline is 16px, and no external font requests are made', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByTestId('nav-speak')).toBeVisible()

    const diagnostics = await page.evaluate(async (families) => {
      // Force the required faces to download first: they are lazy, so until a glyph
      // is needed they sit at status 'unloaded' and both the measurement and the
      // enumeration below would describe the fallback rather than the real face.
      await Promise.all(families.map((family) =>
        document.fonts.load(`400 16px "${family}"`, '0123456789 RTF 1.23x')))
      await document.fonts.ready

      const loadedFaces = [...new Set([...document.fonts]
        .filter((face) => face.status === 'loaded')
        .map((face) => face.family))]

      return {
        status: document.fonts.status,
        loadedFaces: loadedFaces.sort(),
        missingFaces: families.filter((family) => !loadedFaces.includes(family)),
        // Every face is bundled and same-origin. Any request to a font CDN means a
        // regression that makes renders depend on network reachability.
        externalFontRequests: performance.getEntriesByType('resource')
          .map((entry) => entry.name)
          .filter((url) => /fonts\.(googleapis|gstatic)\.com|use\.typekit|fonts\.bunny/i.test(url)),
        rootFontSize: getComputedStyle(document.documentElement).fontSize,
      }
    }, REQUIRED_FACES)

    expect(diagnostics.status).toBe('loaded')
    expect(diagnostics.missingFaces).toEqual([])
    expect(diagnostics.externalFontRequests).toEqual([])
    expect(diagnostics.rootFontSize).toBe('16px')
  })
})
