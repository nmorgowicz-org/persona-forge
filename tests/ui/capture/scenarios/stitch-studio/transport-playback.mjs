// SCENARIO INTENT: Show the unified Stitch Studio transport -- one playhead, positioned
// mid-arrangement after a ruler seek, with the arrangement toggle and a per-clip range button
// both reflecting the same underlying <audio> element (Packet 7: one playback model).
import { captureShot } from '../../harness/shot.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    await page.goto(baseURL, { waitUntil: 'networkidle0' });
    await page.click('[data-testid="nav-stitch-studio"]');
    await page.waitForSelector('[data-testid="stitch-picker-toggle-segments"], [data-testid="empty-state-action"]');
    await page.click('[data-testid="stitch-picker-toggle-segments"], [data-testid="empty-state-action"]');
    await page.waitForSelector('[data-testid="segment-browser-dialog"]');
    await page.waitForFunction(
        () => {
            const el = document.querySelector('[data-testid="segment-browser-dialog"]');
            return el && getComputedStyle(el).opacity === '1';
        },
        { timeout: 5000 }
    );

    const items = await page.$$('[data-testid="stitch-picker-item-segments"]');
    await items[0].click();
    if (items[1]) await items[1].click();
    await page.click('[data-testid="stitch-picker-insert-segments"]');
    await page.waitForSelector('[data-testid="stitch-clip"]');
    await page.waitForSelector('[data-testid="stitch-preview-ready"] audio[src^="blob:"]', { timeout: 15000 });

    // Seek by clicking the ruler's top edge (above the clip lane it overlays), moving the
    // playhead partway into the arrangement.
    const ruler = await page.waitForSelector('[data-testid="stitch-timeline-ruler"]');
    const box = await ruler.boundingBox();
    await page.mouse.click(box.x + box.width * 0.55, box.y + 8);
    await page.waitForFunction(
        () => document.querySelector('[data-testid="stitch-transport-playhead"]')?.style.transform !== 'translateX(0px)',
        { timeout: 5000 }
    );

    // Start the per-clip range play on the second clip -- same shared <audio>, different
    // bounded range -- so the arrangement toggle also shows "Pause".
    const clipPlayButtons = await page.$$('[aria-label="Play clip playback"]');
    await clipPlayButtons[clipPlayButtons.length - 1].click();
    await page.waitForSelector('[data-testid="stitch-transport-toggle"][aria-label="Pause"]');

    // INTENT: Playhead visibly offset from the left edge on the ruler, the arrangement toggle
    // showing "Pause", and the just-clicked clip's own button showing "Pause clip playback" --
    // one shared transport driving all three surfaces at once.
    await captureShot(page, 'transport-playback-playback.png', {
        fullPage: false,
        scrollToSelector: '[data-testid="stitch-timeline-ruler"]',
    });
}
