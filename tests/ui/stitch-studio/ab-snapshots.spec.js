import { test, expect } from '@playwright/test'

// A-8 (M5): A/B plan snapshots for the stitch plan -- capture the plan as A, edit to B, switch
// between them without losing either, and audition each. Session-local, existing stitch
// payloads, no backend change. Plan: docs/plans/20260922-premium_audio_plugin_ux.md M5;
// runbook card A-8.
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

async function setGap(page, index, value) {
  const gap = page.getByTestId('stitch-gap-control').nth(index)
  await gap.getByRole('button', { name: /Gap between clip/ }).click()
  const input = gap.getByRole('textbox', { name: /Gap between clip/ })
  await input.fill(value)
  await input.press('Enter')
}

async function addOneClip(page) {
  await page.getByTestId('stitch-picker-toggle-segments').or(page.getByTestId('empty-state-action')).click()
  const items = page.getByTestId('stitch-picker-item-segments')
  await expect(items.first()).toBeVisible()
  await items.nth(0).click()
  await page.getByTestId('stitch-picker-insert-segments').click()
}

const gapMs = (page, index) => page.getByTestId('stitch-gap-control').nth(index).getAttribute('data-gap-ms')
const depth = (page) => page.getByTestId('stitch-undo').getAttribute('data-history-depth')
const paused = (page, testId) => page.getByTestId(testId).evaluate((el) => el.paused)

test.describe('A-8: A/B plan snapshots', () => {
  test('capturing A and B keeps both plans, and switching restores each', async ({ page }) => {
    await insertSegments(page, 2)
    const initialGap = await gapMs(page, 0)

    await page.getByTestId('stitch-ab-capture-a').click()
    await setGap(page, 0, '700')
    await page.getByTestId('stitch-ab-capture-b').click()

    // Capturing B makes it the active slot, and the active slot says so.
    await expect(page.getByTestId('stitch-ab-slot-b')).toHaveAttribute('data-active', 'true')
    await expect(page.getByTestId('stitch-ab-slot-b')).toContainText('active')

    await page.getByTestId('stitch-ab-slot-a').click()
    await expect.poll(() => gapMs(page, 0)).toBe(initialGap)
    await expect(page.getByTestId('stitch-ab-slot-a')).toHaveAttribute('data-active', 'true')
    await expect(page.getByTestId('stitch-ab-slot-b')).toHaveAttribute('data-active', 'false')

    await page.getByTestId('stitch-ab-slot-b').click()
    await expect.poll(() => gapMs(page, 0)).toBe('700')
  })

  test('switching A/B is one undoable entry', async ({ page }) => {
    await insertSegments(page, 2)
    const initialGap = await gapMs(page, 0)
    const before = Number(await depth(page))

    await page.getByTestId('stitch-ab-capture-a').click()
    await setGap(page, 0, '700')
    await page.getByTestId('stitch-ab-capture-b').click()
    await page.getByTestId('stitch-ab-slot-a').click()
    await expect.poll(() => gapMs(page, 0)).toBe(initialGap)
    expect(Number(await depth(page))).toBe(before + 2)

    // One undo returns to the plan that was live before the switch -- not to a half-applied
    // mixture of the two.
    await page.keyboard.press('ControlOrMeta+z')
    await expect.poll(() => gapMs(page, 0)).toBe('700')
    expect(Number(await depth(page))).toBe(before + 1)
  })

  test('both slots audition, one at a time', async ({ page }) => {
    await insertSegments(page, 2)
    await page.getByTestId('stitch-ab-capture-a').click()
    await setGap(page, 0, '700')
    await page.getByTestId('stitch-ab-capture-b').click()

    const auditionA = page.getByTestId('stitch-ab-audition-a')
    const auditionB = page.getByTestId('stitch-ab-audition-b')
    await expect(auditionA).toBeEnabled()
    await expect(auditionB).toBeEnabled()

    await auditionA.click()
    await expect.poll(() => paused(page, 'stitch-ab-audio-a')).toBe(false)
    expect(await paused(page, 'stitch-ab-audio-b')).toBe(true)

    await auditionB.click()
    await expect.poll(() => paused(page, 'stitch-ab-audio-b')).toBe(false)
    await expect.poll(() => paused(page, 'stitch-ab-audio-a')).toBe(true)
  })

  test('auditioning a snapshot takes playback from the arrangement', async ({ page }) => {
    await insertSegments(page, 2)
    await page.getByTestId('stitch-ab-capture-a').click()
    await expect(page.getByTestId('stitch-ab-audition-a')).toBeEnabled()

    await page.getByTestId('stitch-transport-toggle').click()
    await expect.poll(() => paused(page, 'stitch-transport-audio')).toBe(false)

    await page.getByTestId('stitch-ab-audition-a').click()
    await expect.poll(() => paused(page, 'stitch-transport-audio')).toBe(true)
  })

  test('snapshots are session-local and never persisted', async ({ page }) => {
    await insertSegments(page, 2)
    await page.getByTestId('stitch-ab-capture-a').click()
    await setGap(page, 0, '700')
    await page.getByTestId('stitch-ab-capture-b').click()
    await expect(page.getByTestId('stitch-ab-slot-a')).toBeEnabled()

    const stored = await page.evaluate(() =>
      Object.keys(window.localStorage)
        .map((key) => `${key}=${window.localStorage.getItem(key) ?? ''}`)
        .join('\n'),
    )
    expect(stored).not.toContain('stitch-ab')
    expect(stored).not.toContain('snapshot')

    // The app starts on its default page after a reload (nothing is persisted), so the studio
    // has to be reopened before the bar can be inspected.
    await page.reload()
    await openStudio(page)
    await expect(page.getByTestId('stitch-ab-bar')).toBeVisible()
    await expect(page.getByTestId('stitch-ab-slot-a')).toBeDisabled()
    await expect(page.getByTestId('stitch-ab-slot-b')).toBeDisabled()
  })
  test('a filled slot says what it holds, so A and B are tellable apart', async ({ page }) => {
    // CP1 finding (owner, 2026-09-23): "i got confused once and accidentally overwrote my A
    // clip". Two slots that both read "A" and "B" and nothing else give no way to tell which
    // plan is in which, and the control that overwrites sat where the control that shows it
    // should be.
    await insertSegments(page, 2)
    await page.getByTestId('stitch-ab-capture-a').click()
    await addOneClip(page)
    await page.getByTestId('stitch-ab-capture-b').click()

    await expect(page.getByTestId('stitch-ab-slot-a')).toContainText('2 clips')
    await expect(page.getByTestId('stitch-ab-slot-b')).toContainText('3 clips')
    // The rendered length, not just the count: two plans can hold the same clips at
    // different gaps, which is exactly what an A/B comparison is for.
    await expect(page.getByTestId('stitch-ab-slot-a')).toContainText(/\d+\.\ds/)
    await expect(page.getByTestId('stitch-ab-slot-b')).toContainText(/\d+\.\ds/)
    await expect(page.getByTestId('stitch-ab-slot-a')).not.toContainText('empty')
    await expect(page.getByTestId('stitch-ab-slot-b')).not.toContainText('empty')
  })

  test('overwriting a slot asks first, and declining keeps the stored plan', async ({ page }) => {
    await insertSegments(page, 2)
    await page.getByTestId('stitch-ab-capture-a').click()
    const storedGap = await gapMs(page, 0)
    await setGap(page, 0, '900')

    page.once('dialog', (dialog) => dialog.dismiss())
    await page.getByTestId('stitch-ab-capture-a').click()
    await page.getByTestId('stitch-ab-slot-a').click()
    expect(await gapMs(page, 0)).toBe(storedGap)

    // Accepting it replaces the snapshot with the live plan. The plan is moved off A's
    // content first, so "A now holds what was live" is distinguishable from "A never moved".
    await setGap(page, 0, '900')
    page.once('dialog', (dialog) => dialog.accept())
    await page.getByTestId('stitch-ab-capture-a').click()
    await setGap(page, 0, '300')
    await page.getByTestId('stitch-ab-slot-a').click()
    expect(await gapMs(page, 0)).toBe('900')
  })
})
