// SCENARIO INTENT: Drive a basic speak-generate round trip.
import { captureShot } from '../../harness/shot.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    await page.goto(baseURL, { waitUntil: 'networkidle0' });
    await page.waitForSelector('[data-testid="speak-text-input"]');
    await page.type('[data-testid="speak-text-input"]', 'The voice was warm and clear, carrying the kind of certainty that made you want to listen.');
    // INTENT: Text entered, ready to generate.
    await captureShot(page, 'speak-generate-before-generate.png', { fullPage: true });
    await page.click('[data-testid="speak-generate-button"]');
    // Real CPU inference — do not shorten this timeout.
    await page.waitForSelector('[data-testid="speak-result"] audio', { timeout: 120000 });
    // INTENT: Generated audio result rendered.
    await captureShot(page, 'speak-generate-after-generate.png', { fullPage: true });
}
