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
    // The <audio> element exists before its media metadata arrives, and the deck renders an
    // idle zero-length bar until then — the previous capture shot exactly that state and
    // "showed" a generated waveform that read 0.0s / LEVEL 0%.
    await page.waitForFunction(
        () => {
            const el = document.querySelector('[data-testid="speak-result"] audio');
            return Boolean(el) && el.readyState >= 1 && Number.isFinite(el.duration) && el.duration > 0;
        },
        { timeout: 30000 }
    );
    // INTENT: Generated audio result rendered.
    await captureShot(page, 'speak-generate-after-generate.png', { fullPage: true });
}
