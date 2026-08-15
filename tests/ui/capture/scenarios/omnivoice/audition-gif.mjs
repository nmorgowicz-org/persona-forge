// SCENARIO INTENT: Animate an OmniVoice audition run as a GIF.
import { createRecorder, framesToGif, cleanupFrames } from '../../harness/shot.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    const prefix = 'omnivoice-audition';
    cleanupFrames();
    const recorder = createRecorder(prefix);

    await page.goto(baseURL, { waitUntil: 'networkidle0' });
    await page.click('[data-testid="nav-voice-design"]');
    await page.click('[data-testid="engine-omnivoice"]');
    await page.waitForSelector('[data-testid="accent-bank-au"]');
    await page.click('[data-testid="accent-bank-au"]');
    await page.waitForSelector('[data-testid="omnivoice-script"]');
    await page.type('[data-testid="omnivoice-script"]', 'The quick brown fox jumps over the lazy dog.');
    await recorder.snap(page);
    await page.click('[data-testid="omnivoice-audition-button"]');
    await recorder.snap(page);

    const candidateDeadline = Date.now() + 120000;
    while (Date.now() < candidateDeadline) {
        const count = await page
            .$eval('[data-testid="omnivoice-candidate-take"]', (els) => els.length)
            .catch(() => 0);
        await recorder.snap(page);
        if (count >= 3) break;
        await new Promise((r) => setTimeout(r, 1000));
    }

    await page.click('[data-testid="omnivoice-stitch-button"]');
    const resultHandle = await page.waitForSelector('[data-testid="omnivoice-result"]', { timeout: 60000 });
    await page.evaluate((el) => el.scrollIntoView({ block: 'center', behavior: 'instant' }), resultHandle);
    await page.waitForFunction(
        (el) => {
            const r = el.getBoundingClientRect();
            return r.top >= 0 && r.top < window.innerHeight;
        },
        { timeout: 5000 },
        resultHandle
    );
    await recorder.snap(page);

    framesToGif(page, prefix, 'omnivoice-audition-gif-audition.gif', 2);
    cleanupFrames();
}
