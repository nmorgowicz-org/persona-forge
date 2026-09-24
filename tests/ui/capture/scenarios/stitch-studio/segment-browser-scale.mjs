// SCENARIO INTENT: Prove the segment browser renders and scrolls a 250-row library across five
// projects without clipping, using the same deterministic large-library fixture the scale
// Playwright tests use (tests/ui/fixtures/largeSegmentLibrary.mjs) -- never a real 250-segment
// backend.
import { captureShot } from '../../harness/shot.mjs';
import { generateLargeSegmentLibrary, makeTinyWavBuffer } from '../../../fixtures/largeSegmentLibrary.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    const rows = generateLargeSegmentLibrary(250);
    const wav = makeTinyWavBuffer();

    await page.setRequestInterception(true);
    page.on('request', (req) => {
        const url = req.url();
        if (req.method() === 'GET' && /\/omnivoice\/segments\/[^/]+\/audio$/.test(url)) {
            req.respond({ status: 200, contentType: 'audio/wav', body: wav });
            return;
        }
        if (req.method() === 'GET' && url.endsWith('/omnivoice/segments')) {
            req.respond({ status: 200, contentType: 'application/json', body: JSON.stringify({ segments: rows }) });
            return;
        }
        req.continue();
    });

    await page.goto(baseURL, { waitUntil: 'networkidle0' });
    await page.click('[data-testid="nav-stitch-studio"]');
    await page.waitForSelector('[data-testid="stitch-picker-toggle-segments"], [data-testid="empty-state-action"]');
    await page.click('[data-testid="stitch-picker-toggle-segments"], [data-testid="empty-state-action"]');
    await page.waitForSelector('[data-testid="segment-browser-dialog"]');
    await page.waitForSelector('[data-testid="stitch-picker-item-segments"]');
    await page.waitForFunction(
        () => {
            const el = document.querySelector('[data-testid="segment-browser-dialog"]');
            return el && getComputedStyle(el).opacity === '1';
        },
        { timeout: 5000 }
    );

    // Scroll partway down the row list so the capture proves the list actually renders and
    // scrolls at scale, not just its first screenful.
    await page.evaluate(() => {
        const dialog = document.querySelector('[data-testid="segment-browser-dialog"]');
        const scrollArea = dialog?.querySelector('.overflow-y-auto');
        if (scrollArea) scrollArea.scrollTop = scrollArea.scrollHeight / 2;
    });
    await new Promise((resolve) => setTimeout(resolve, 200));

    // INTENT: Segment browser mid-scroll through a 250-row, five-project library.
    await captureShot(page, 'segment-browser-scale-scale.png', { fullPage: true });
}
