import { test, expect } from '@playwright/test'

// A-5 (M2 + N5): right-click menus on clips, seams, and segment-browser rows, plus a
// keyboard-only path to every one of those actions. The menus are thin wrappers over
// handlers that already exist (StitchPlanSession's remove/update, region edits, the
// clip's own text/numeric editors, the browser's insert/audition) -- no new editor
// behavior, and no new dependency: the menu primitive wraps the already-installed
// unified `radix-ui` package.

async function openPicker(page) {
  await page.getByTestId('stitch-picker-toggle-segments').click()
  await expect(page.getByTestId('segment-browser-dialog')).toBeVisible()
}

async function insertSegments(page, n) {
  await page.goto('/')
  await page.getByTestId('nav-stitch-studio').click()
  await openPicker(page)
  const items = page.getByTestId('stitch-picker-item-segments')
  await expect(items.first()).toBeVisible()
  for (let i = 0; i < n; i++) await items.nth(i).click()
  await page.getByTestId('stitch-picker-insert-segments').click()
  await expect(page.getByTestId('stitch-clip')).toHaveCount(n)
}

const menu = (page, scope) => page.locator(`[data-testid="stitch-context-menu"][data-menu-scope="${scope}"]`)
const item = (page, scope, testId) => menu(page, scope).getByTestId(testId)

test.describe('A-5: context menus', () => {
  test('a clip menu offers the domain actions and removes the clip', async ({ page }) => {
    await insertSegments(page, 2)

    await page.getByTestId('stitch-clip').first().click({ button: 'right' })

    const clipMenu = menu(page, 'clip')
    await expect(clipMenu).toBeVisible()
    for (const name of ['Play range', 'Edit text', 'Reset trim and fades', 'Focus trim editor', 'Remove clip']) {
      await expect(clipMenu.getByRole('menuitem', { name })).toBeVisible()
    }

    await item(page, 'clip', 'stitch-menu-remove-clip').click()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(1)
    await expect(clipMenu).toBeHidden()
  })

  test('clip menu resets trim and fades, and opens the numeric editor', async ({ page }) => {
    await insertSegments(page, 1)
    const clip = page.getByTestId('stitch-clip').first()
    await clip.getByTestId('stitch-clip-edit-toggle').click()

    const trimStart = clip.getByTestId('stitch-stepper-trim-start-value')
    for (let i = 0; i < 4; i++) await clip.getByRole('button', { name: 'Increase Trim start' }).click()
    await expect(trimStart).toHaveText('40')

    await clip.click({ button: 'right' })
    await item(page, 'clip', 'stitch-menu-reset-trim').click()
    await expect(trimStart).toHaveText('0')

    await clip.click({ button: 'right' })
    await item(page, 'clip', 'stitch-menu-focus-trim').click()
    // The menu action puts the caret in the typed-entry editor of the trim control.
    const editor = clip.getByTestId('stitch-stepper-trim-start-value')
    await expect(editor).toHaveRole('textbox')
    await expect(editor).toBeFocused()
  })

  test('a seam menu changes the gap', async ({ page }) => {
    await insertSegments(page, 2)
    const gap = page.getByTestId('stitch-gap-control').first()
    await expect(gap).toHaveAttribute('data-gap-ms', /\d+/)

    await gap.click({ button: 'right' })
    const seamMenu = menu(page, 'seam')
    await expect(seamMenu).toBeVisible()
    await item(page, 'seam', 'stitch-menu-gap-zero').click()
    await expect(gap).toHaveAttribute('data-gap-ms', '0')

    await gap.click({ button: 'right' })
    await item(page, 'seam', 'stitch-menu-gap-wider').click()
    await expect(gap).toHaveAttribute('data-gap-ms', '100')
  })

  test('a segment row menu inserts, auditions, and copies the id', async ({ page, context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write'])
    await page.goto('/')
    await page.getByTestId('nav-stitch-studio').click()
    await openPicker(page)

    const row = page.getByTestId('segment-browser-row').first()
    await row.click({ button: 'right' })
    const rowMenu = menu(page, 'segment')
    await expect(rowMenu).toBeVisible()
    for (const name of ['Insert', 'Audition', 'Copy id']) {
      await expect(rowMenu.getByRole('menuitem', { name })).toBeVisible()
    }

    // Copy id first (it does not close the dialog), then insert (which does).
    await item(page, 'segment', 'stitch-menu-copy-id').click()
    const copied = await page.evaluate(() => navigator.clipboard.readText())
    expect(copied).toMatch(/^seg_[0-9a-f]{12}$/)

    await row.click({ button: 'right' })
    await item(page, 'segment', 'stitch-menu-insert').click()
    await expect(page.getByTestId('segment-browser-dialog')).toBeHidden()
    await expect(page.getByTestId('stitch-clip')).toHaveCount(1)
  })

  test('every menu is reachable without a pointer', async ({ page }) => {
    await insertSegments(page, 2)

    // The seam answers the dedicated context-menu key. (Checked before the clip below is
    // removed: a seam only exists *between* two clips.)
    const gap = page.getByTestId('stitch-gap-control').first()
    await gap.focus()
    await page.keyboard.press('ContextMenu')
    await expect(menu(page, 'seam')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(menu(page, 'seam')).toBeHidden()

    // Shift+F10 on a focused control inside the clip opens the clip menu.
    const clip = page.getByTestId('stitch-clip').first()
    await clip.getByRole('button', { name: 'Remove clip' }).focus()
    await page.keyboard.press('Shift+F10')
    await expect(menu(page, 'clip')).toBeVisible()

    // ... focus lands inside the menu, and an item is reachable and activatable by keyboard
    // alone. Roving focus moves on a macrotask, so wait for the move to land rather than
    // reading the active element immediately after the key.
    await expect(page.locator('[data-testid="stitch-context-menu"] [role="menuitem"]:focus')).toHaveCount(1)
    await page.keyboard.press('End')
    await expect
      .poll(() => page.evaluate(() => document.activeElement?.getAttribute('data-testid')))
      .toBe('stitch-menu-remove-clip')
    await page.keyboard.press('Enter')
    await expect(page.getByTestId('stitch-clip')).toHaveCount(1)

    // A focused segment row too.
    await openPicker(page)
    await page.getByTestId('segment-browser-row').first().getByRole('button', { name: /^Audition/ }).focus()
    await page.keyboard.press('Shift+F10')
    await expect(menu(page, 'segment')).toBeVisible()
  })
})
