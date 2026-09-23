// SCENARIO INTENT: Show the dedicated Voice Edit workspace with a saved voice selected —
// the prosody editor plus the always-mounted A/B strip (ORIGINAL lane on load), and a
// second frame with a rendered preview showing the ADJUSTED lane below it.
import { captureShot } from '../../harness/shot.mjs';

export default async function ({ page, baseURL }) {
  await page.goto(baseURL, { waitUntil: 'networkidle0' });
  await page.click('[data-testid="nav-voice-edit"]');
  await page.waitForSelector('[data-testid="voice-edit-page"]');
  await page.waitForSelector('[data-testid="voice-edit-picker"]');
  // Wait for the voice list to populate and the auto-selected voice's variant list
  // to render before the shot -- the capture must not race the auto-select.
  await page.waitForSelector('[data-testid="voice-edit-variant"]', { timeout: 15000 });
  // The A/B strip mounts with the selected voice (no preview required). Wait for the
  // ORIGINAL lane's waveform to actually paint, so the shot is not taken against an
  // empty lane while the reference audio is still decoding.
  await page.waitForSelector('[data-testid="alignment-compare"]', { timeout: 15000 });
  await page.waitForSelector('[data-testid="stitch-waveform-canvas"]', { timeout: 15000 });
  await captureShot(page, 'voice-edit-workspace.png', { fullPage: true });

  // Drive a preview so the ADJUSTED lane, its cut markers, and the A/B transport are
  // all populated -- this is the state that answers "where does the adjusted take go".
  // Puppeteer, not Playwright: click by text match in-page.
  await page.evaluate(() => {
    for (const btn of document.querySelectorAll('button')) {
      if ((btn.textContent || '').trim().startsWith('Preview')) {
        btn.click();
        return;
      }
    }
  });
  await page.waitForFunction(
    () => {
      const buttons = document.querySelectorAll('button');
      for (const btn of buttons) {
        if ((btn.textContent || '').includes('Reset Preview')) return true;
      }
      return false;
    },
    { timeout: 60000 }
  );
  // Two lanes now exist; wait for the second waveform canvas to paint as well.
  await page.waitForFunction(
    () => document.querySelectorAll('[data-testid="stitch-waveform-canvas"]').length >= 2,
    { timeout: 30000 }
  );
  await captureShot(page, 'voice-edit-prosody-ab.png', { scrollToSelector: '[data-testid="alignment-compare"]' });
}
