// SCENARIO INTENT: Show the app's landing state before any interaction.
import { captureShot } from '../../harness/shot.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    await page.goto(baseURL, { waitUntil: 'networkidle0' });
    await page.waitForSelector('[data-testid="speak-text-input"]');
    // INTENT: Home screen, ready for text input.
    await captureShot(page, 'home-home.png', { fullPage: true });
}
