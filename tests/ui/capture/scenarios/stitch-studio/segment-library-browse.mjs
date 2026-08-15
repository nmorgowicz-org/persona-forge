// SCENARIO INTENT: Browse the segment library picker in Stitch Studio.
import { captureShot } from '../../harness/shot.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    await page.goto(baseURL, { waitUntil: 'networkidle0' });
    await page.click('[data-testid="nav-stitch-studio"]');
    await page.waitForSelector('[data-testid="stitch-picker-toggle-segments"]');
    await page.click('[data-testid="stitch-picker-toggle-segments"]');
    await page.waitForSelector('[data-testid="stitch-picker-item-segments"]');
    await page.waitForFunction(
        () => {
            const el = document.querySelector('[data-testid="stitch-picker-item-segments"]')?.closest('.shadow-lg');
            return el && getComputedStyle(el).opacity === '1';
        },
        { timeout: 5000 }
    );
    // INTENT: Segment library picker open and settled.
    await captureShot(page, 'segment-library-browse-segment-library-browse.png', { fullPage: true });
}
