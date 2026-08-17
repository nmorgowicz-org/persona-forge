// SCENARIO INTENT: Hero candidate — the Speak page as a first-time visitor sees it, text entered.
import { gotoApp } from '../../harness/browser.mjs';
import { captureShot } from '../../harness/shot.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    await gotoApp(page, baseURL);
    await page.waitForSelector('[data-testid="speak-text-input"]');
    await page.type(
        '[data-testid="speak-text-input"]',
        'The voice was warm and clear, carrying the kind of certainty that made you want to listen.'
    );
    // INTENT: Clean, uncluttered first impression — the thing a visitor will actually do first.
    await captureShot(page, 'hero-speak-filled-speak.png', { fullPage: true });
}
