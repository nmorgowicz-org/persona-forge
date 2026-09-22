import { test, expect } from '@playwright/test'

async function openVoiceEdit(page) {
  await page.goto('/')
  await page.getByTestId('nav-voice-edit').click()
  await expect(page.getByTestId('voice-edit-page')).toBeVisible()
}

test.describe('Voice Edit workspace', () => {
  test('Voice Edit deep link preselects the saved voice', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-stitch-studio').click()
    await page.getByTestId('stitch-picker-toggle-segments').click()
    await page.getByTestId('stitch-picker-item-segments').nth(0).click()
    await page.getByTestId('stitch-picker-item-segments').nth(1).click()
    await page.getByTestId('stitch-picker-item-segments').nth(2).click()
    await page.getByTestId('stitch-picker-insert-segments').click()
    await page.getByTestId('stitch-voice-name').fill('Voice Edit deep link')
    await page.getByTestId('stitch-save-voice').click()
    await expect(page.getByTestId('stitch-adjust-prosody')).toBeVisible()
    const savedVoiceId = await page.getByTestId('stitch-adjust-prosody').evaluate((button) =>
      button.parentElement?.innerText.match(/(?:fake_voice_\d+|vd_[a-f0-9]+)/)?.[0] ?? '',
    )
    await page.getByTestId('stitch-adjust-prosody').click()

    await expect(page.getByTestId('voice-edit-page')).toBeVisible()
    await expect(page.getByTestId('voice-edit-picker')).toHaveValue(savedVoiceId)
  })

  test('variant saved in Voice Edit appears in Voice Library prosody editor', async ({ page }) => {
    await openVoiceEdit(page)
    await page.getByTestId('voice-edit-picker').selectOption({ index: 1 })
    const variants = page.getByTestId('voice-edit-variant')
    await expect(variants.first()).toBeVisible()
    const countBefore = await variants.count()
    await page.getByTestId('voice-edit-save-variant').click()
    await expect(variants).toHaveCount(countBefore + 1, { timeout: 20000 })

    await page.getByTestId('nav-voice-library').click()
    await expect(page.getByTestId('voice-card').first()).toContainText('Prosody Variants')
    // Repeated saves (earlier suite state, retries) can leave several variants sharing the
    // "Neutral 1.0x" label, so this asserts the label is present, not that it is unique.
    await expect(page.getByTestId('voice-card').first().getByText('Neutral 1.0x').first()).toBeVisible()
  })

  test('promoting a saved variant moves the primary flag and serves its audio', async ({ page }) => {
    await openVoiceEdit(page)
    const picker = page.getByTestId('voice-edit-picker')
    // Index 2 is any real seeded voice (the picker's disabled placeholder holds index 0);
    // counts are relative, so prior saves on the same voice (earlier suite state or
    // retries) cannot break the assertions.
    await picker.selectOption({ index: 2 })
    const voiceId = await picker.inputValue()

    const variants = page.getByTestId('voice-edit-variant')
    await expect(variants.first()).toBeVisible()
    const countBefore = await variants.count()
    await page.getByTestId('voice-edit-save-variant').click()
    await expect(variants).toHaveCount(countBefore + 1, { timeout: 20000 })

    // The new row is the last one (variants append after the master reference row). Its
    // addressable id/filename come from the same /variants payload the list renders --
    // the slug itself is not asserted, since repeated saves on one voice get sequential
    // slugs. (The row's label span carries the id only as a tooltip: the app's
    // TitleTooltipBridge rewrites `title` into `data-app-tooltip` at runtime.)
    const variantRow = variants.nth(countBefore)
    const created = await page.evaluate(async (id) => {
      const res = await fetch(`/voices/${encodeURIComponent(id)}/variants`)
      const body = await res.json()
      const saved = body.entries.filter((entry) => !entry.is_original)
      const last = saved[saved.length - 1]
      return { id: last?.id, filename: last?.filename }
    }, voiceId)
    expect(created.id).toBeTruthy()
    expect(created.id.startsWith(`${voiceId}.`)).toBe(true)
    const variantFilename = created.filename

    // Before promoting: exactly one row is primary (the master reference on a fresh voice,
    // or a previously promoted variant on a re-run), and the new variant is not it.
    const primaryBefore = await variants.evaluateAll((els) =>
      els.findIndex((el) => el.textContent?.includes('Primary')),
    )
    expect(primaryBefore).toBeGreaterThanOrEqual(0)
    expect(primaryBefore).not.toBe(countBefore)
    await expect(variantRow).not.toContainText('Primary')

    await variantRow.getByRole('button', { name: 'Make this the primary variant' }).click()

    // After promoting: the flag moves to the promoted row and off the previous holder.
    await expect(variantRow).toContainText('Primary')
    await expect(variants.nth(primaryBefore)).not.toContainText('Primary')

    // The promoted variant is what the voice now serves, and its audio endpoint serves
    // the baked file.
    const audio = await page.evaluate(async ({ id, filename }) => {
      const listRes = await fetch(`/voices/${encodeURIComponent(id)}/variants`)
      const list = await listRes.json()
      const res = await fetch(`/voices/${encodeURIComponent(id)}/variants/${filename}/audio`)
      if (!res.ok) return { status: res.status }
      const body = await res.json()
      return {
        status: 200,
        hasAudio: typeof body.audio_base64 === 'string' && body.audio_base64.length > 0,
        activeFilename: list.active_filename,
      }
    }, { id: voiceId, filename: variantFilename })
    expect(audio).toEqual({ status: 200, hasAudio: true, activeFilename: variantFilename })
  })

  test('Voice Library retains its existing prosody controls', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-voice-library').click()
    await expect(page.getByTestId('voice-card').first().getByRole('button', { name: /Adjust prosody/i })).toBeVisible()
  })

  test('Voice Library uses the shared compact prosody panel', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-voice-library').click()
    await page.getByTestId('voice-card').first().getByRole('button', { name: /Adjust prosody/i }).click()
    await expect(page.getByTestId('prosody-editor-panel')).toHaveAttribute('data-layout', 'compact')
  })
})
