// SCENARIO INTENT: Animate the end-to-end design-to-stitch wizard flow as a GIF.
import { createRecorder, framesToGif, cleanupFrames } from '../../harness/shot.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    const prefix = 'design-to-stitch';
    cleanupFrames();
    const recorder = createRecorder(prefix);

    await page.goto(baseURL, { waitUntil: 'networkidle0' });
    await recorder.snap(page);
    await page.click('[data-testid="nav-voice-design"]');
    await recorder.snap(page);
    await page.click('[data-testid="engine-omnivoice"]');
    await recorder.snap(page);
    await page.waitForSelector('[data-testid="accent-bank-au"]');
    await page.click('[data-testid="accent-bank-au"]');
    await recorder.snap(page);
    await page.waitForSelector('[data-testid="omnivoice-script"]');
    await page.type('[data-testid="omnivoice-script"]', 'The quick brown fox jumps over the lazy dog.');
    await recorder.snap(page);
    await page.click('[data-testid="omnivoice-audition-button"]');
    await recorder.snap(page);

    const candidateDeadline = Date.now() + 180000;
    while (Date.now() < candidateDeadline) {
        const count = await page
            .$eval('[data-testid="omnivoice-candidate-take"]', (els) => els.length)
            .catch(() => 0);
        if (count >= 3) break;
        await new Promise((r) => setTimeout(r, 1500));
    }
    await recorder.snap(page);

    const lockButton = await page.waitForSelector('[data-testid="omnivoice-lock-segment"]');
    await lockButton.click();
    await page.waitForFunction(
        (el) => el.disabled,
        { timeout: 15000 },
        lockButton
    );
    await recorder.snap(page);

    await page.click('[data-testid="nav-stitch-studio"]');
    await page.waitForSelector('[data-testid="stitch-voice-name"]');
    await recorder.snap(page);
    await page.type('[data-testid="stitch-voice-name"]', 'Wizard Demo Voice');
    await recorder.snap(page);

    await page.click('[data-testid="stitch-picker-toggle-segments"]');
    await page.waitForSelector('[data-testid="stitch-picker-item-segments"]');
    await page.waitForFunction(
        () => {
            const el = document.querySelector('[data-testid="stitch-picker-item-segments"]')?.closest('.shadow-lg');
            return el && getComputedStyle(el).opacity === '1';
        },
        { timeout: 5000 }
    );
    await recorder.snap(page);

    const items = await page.$$('[data-testid="stitch-picker-item-segments"]');
    await items[0].click();
    await page.click('[data-testid="stitch-picker-insert-segments"]');
    await page.waitForSelector('[data-testid="stitch-clip"]');
    await recorder.snap(page);

    await page.click('[data-testid="stitch-save-voice"]');
    await page.waitForSelector('[data-testid="voice-card"]', { timeout: 60000 });
    await recorder.snap(page);

    framesToGif(page, prefix, 'design-to-stitch-gif-design-to-stitch.gif', 2);
    cleanupFrames();
}
