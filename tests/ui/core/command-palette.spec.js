import { test, expect } from '@playwright/test'

// A-7 (M4): one global shortcut/command registry feeding both the Cmd/Ctrl+K command palette
// and the `?` keymap. Pages register their own commands and keys; both surfaces read the same
// registry. Plan: docs/archive/luminous-instrument/20260922-premium_audio_plugin_ux.md M4; runbook card A-7.
//
// RED-first: every test must fail on unmodified code because the feature is missing.

async function openStudio(page) {
  await page.goto('/')
  await page.getByTestId('nav-stitch-studio').click()
}

async function insertSegments(page, n) {
  await openStudio(page)
  await page.getByTestId('stitch-picker-toggle-segments').or(page.getByTestId('empty-state-action')).click()
  const items = page.getByTestId('stitch-picker-item-segments')
  await expect(items.first()).toBeVisible()
  for (let i = 0; i < n; i++) await items.nth(i).click()
  await page.getByTestId('stitch-picker-insert-segments').click()
  await expect(page.getByTestId('stitch-clip')).toHaveCount(n)
}

const palette = (page) => page.getByTestId('command-palette')

test.describe('A-7: command palette and keymap', () => {
  test('Cmd/Ctrl+K opens the palette, and a command navigates', async ({ page }) => {
    await page.goto('/')
    await page.keyboard.press('ControlOrMeta+k')

    const box = palette(page)
    await expect(box).toBeVisible()
    const input = page.getByTestId('command-palette-input')
    await expect(input).toBeFocused()

    await input.fill('stitch')
    const items = box.getByTestId('command-item')
    await expect(items).toHaveCount(1)
    await expect(items.first()).toContainText('Stitch Studio')

    await page.keyboard.press('Enter')
    await expect(box).toBeHidden()
    await expect(page.getByTestId('stitch-voice-name')).toBeVisible()
  })

  test('? opens the keymap, listing the shortcuts the stitch dialog used to list', async ({ page }) => {
    // The stitch scope has to be mounted for its rows to be in the registry.
    await insertSegments(page, 1)
    await page.locator('body').click()
    await page.keyboard.press('?')

    const keymap = page.getByTestId('shortcut-keymap')
    await expect(keymap).toBeVisible()

    // Exactly the rows the old stitch-only dialog carried.
    for (const [keys, description] of [
      ['Space', 'Play/pause the arrangement'],
      ['Click ruler', 'Seek the arrangement'],
      ['←/→', 'Select the previous/next clip'],
      ['Shift+←/→', 'Reorder the selected clip'],
      ['↑/↓', 'Nudge trim start'],
      ['Delete/Backspace', 'Remove the selected clip'],
      ['?', 'Show this dialog'],
      ['Cmd/Ctrl+Z', 'Undo the last plan change'],
    ]) {
      const row = keymap.locator(`[data-testid="shortcut-row"][data-keys="${keys}"]`)
      await expect(row, `keymap row for ${keys}`).toHaveCount(1)
      await expect(row).toContainText(description)
    }

    // The global layer is in there too -- it is one registry, not a stitch dialog.
    await expect(keymap.locator('[data-testid="shortcut-row"][data-keys="Cmd/Ctrl+K"]')).toHaveCount(1)

    await page.keyboard.press('Escape')
    await expect(keymap).toBeHidden()
  })

  test('Space inside a text input types a space and never toggles playback', async ({ page }) => {
    await insertSegments(page, 1)
    // Wait until the transport exists, so a hijacked Space would have something to toggle.
    await expect(page.getByTestId('stitch-transport-toggle')).toBeVisible()

    const name = page.getByTestId('stitch-voice-name')
    // The field arrives pre-filled with the suggested name; clear it so the assertion is about
    // the two spaces this test types, not about where the caret happened to land.
    await name.fill('')
    await name.click()
    await name.pressSequentially('two words')

    await expect(name).toHaveValue('two words')
    await expect(page.getByTestId('stitch-transport-toggle')).toHaveAttribute('aria-label', 'Play')
  })

  test('a page-scoped command runs from the palette', async ({ page }) => {
    await insertSegments(page, 2)
    await page.getByTestId('stitch-clip').first().getByRole('button', { name: 'Remove clip' }).click()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(1)

    await page.keyboard.press('ControlOrMeta+k')
    const input = page.getByTestId('command-palette-input')
    await input.fill('undo')
    await expect(palette(page).getByTestId('command-item').first()).toContainText('Undo')
    await page.keyboard.press('Enter')

    await expect(palette(page)).toBeHidden()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(2)
  })

  test('the header button opens the palette without a keyboard', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('command-palette-button').click()
    await expect(palette(page)).toBeVisible()
    await page.getByTestId('command-palette-input').fill('voice library')
    await page.keyboard.press('Enter')
    await expect(palette(page)).toBeHidden()
    await expect(page.getByTestId('nav-voice-library')).toHaveAttribute('data-active', 'true')
  })
})
