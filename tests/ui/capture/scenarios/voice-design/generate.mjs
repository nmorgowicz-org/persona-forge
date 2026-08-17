// SCENARIO INTENT: Fill in Voice Design fields and generate a result.
import { captureShot } from '../../harness/shot.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    await page.goto(baseURL, { waitUntil: 'networkidle0' });
    await page.click('[data-testid="nav-voice-design"]');
    await page.waitForSelector('[data-testid="voice-design-description"]');
    await page.type(
        '[data-testid="voice-design-description"]',
        'Warm, calm narrator with a slight British accent.',
    );
    await page.type(
        '[data-testid="voice-design-sample-text"]',
        'This is a short sample line for the voice.',
    );
    // INTENT: Filled-in voice design fields, before generation.
    await captureShot(page, 'voice-design-generate-filled.png', { fullPage: true });
    await page.click('[data-testid="voice-design-generate-button"]');
    // Real CPU inference — do not shorten this timeout.
    await page.waitForSelector('[data-testid="voice-design-result"]', { timeout: 120000 });
    // INTENT: Generated voice design result.
    await captureShot(page, 'voice-design-generate-result.png', { fullPage: true });
}
