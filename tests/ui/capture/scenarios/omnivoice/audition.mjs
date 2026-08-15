// SCENARIO INTENT: Drive an OmniVoice audition and stitch to a result.
import { captureShot } from '../../harness/shot.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    await page.goto(baseURL, { waitUntil: 'networkidle0' });
    await page.click('[data-testid="nav-voice-design"]');
    await page.click('[data-testid="engine-omnivoice"]');
    await page.waitForSelector('[data-testid="accent-bank-au"]');
    await page.click('[data-testid="accent-bank-au"]');
    await page.waitForSelector('[data-testid="omnivoice-script"]');
    await page.type('[data-testid="omnivoice-script"]', 'The quick brown fox jumps over the lazy dog.');
    await page.click('[data-testid="omnivoice-audition-button"]');
    await page.waitForSelector('[data-testid="omnivoice-candidate-take"]', { timeout: 180000 });
    // INTENT: OmniVoice audition candidates rendered.
    await captureShot(page, 'omnivoice-audition-audition-candidates.png', { fullPage: true });

    await page.waitForFunction(
        () => document.querySelectorAll('[data-testid="omnivoice-candidate-take"]').length >= 3,
        { timeout: 180000 }
    );
    await page.click('[data-testid="omnivoice-stitch-button"]');
    // Real CPU inference — do not shorten this timeout.
    const resultHandle = await page.waitForSelector('[data-testid="omnivoice-result"]', { timeout: 120000 });
    await page.evaluate((el) => el.scrollIntoView({ block: 'center', behavior: 'instant' }), resultHandle);
    await page.waitForFunction(
        (el) => {
            const r = el.getBoundingClientRect();
            return r.top >= 0 && r.top < window.innerHeight;
        },
        { timeout: 5000 },
        resultHandle
    );
    // INTENT: Stitched OmniVoice audition result.
    await captureShot(page, 'omnivoice-audition-audition-result.png', { fullPage: true });
}
