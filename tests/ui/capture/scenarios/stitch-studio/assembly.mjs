// SCENARIO INTENT: Assemble segments into a stitched clip.
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

    const checkboxes = await page.$$('[data-testid="stitch-picker-item-segments"]');
    await checkboxes[0].click();
    if (checkboxes[1]) await checkboxes[1].click();

    await page.click('[data-testid="stitch-picker-insert-segments"]');
    await page.waitForSelector('[data-testid="stitch-clip"]');
    // INTENT: Assembled stitch clip.
    await captureShot(page, 'stitch-assembly-assembly.png', { fullPage: true });
}
