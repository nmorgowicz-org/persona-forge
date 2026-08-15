// SCENARIO INTENT: Show the prosody alignment comparison view.
import { captureShot } from '../../harness/shot.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    await page.goto(baseURL, { waitUntil: 'networkidle0' });
    await page.click('[data-testid="nav-voice-library"]');
    await page.waitForSelector('[data-testid="voice-card"]');
    await page.waitForSelector('[data-testid="alignment-compare"]');
    // INTENT: Alignment comparison panel.
    await captureShot(page, 'alignment-compare-alignment-compare.png', { fullPage: true });
}
