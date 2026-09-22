// SCENARIO INTENT: Show gap controls as always-visible, first-class timeline elements --
// a 0.00s seam and a typed nonzero seam side by side, distinguishable by shape and width,
// not by a hidden-until-clicked "+" affordance.
import { captureShot } from '../../harness/shot.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    await page.goto(baseURL, { waitUntil: 'networkidle0' });
    await page.click('[data-testid="nav-stitch-studio"]');
    await page.waitForSelector('[data-testid="stitch-picker-toggle-segments"]');
    await page.click('[data-testid="stitch-picker-toggle-segments"]');
    await page.waitForSelector('[data-testid="segment-browser-dialog"]');
    await page.waitForSelector('[data-testid="stitch-picker-item-segments"]');
    await page.waitForFunction(
        () => {
            const el = document.querySelector('[data-testid="segment-browser-dialog"]');
            return el && getComputedStyle(el).opacity === '1';
        },
        { timeout: 5000 }
    );

    // Three clips -> two seams, both arriving at the punctuation-suggested 520ms.
    // The shot pairs a typed 250ms seam with a seam typed down to 0, so the
    // zero-state and the nonzero state sit side by side in one frame.
    const items = await page.$$('[data-testid="stitch-picker-item-segments"]');
    await items[0].click();
    if (items[1]) await items[1].click();
    if (items[2]) await items[2].click();
    await page.click('[data-testid="stitch-picker-insert-segments"]');
    await page.waitForSelector('[data-testid="stitch-clip"]');
    await page.waitForSelector('[data-testid="stitch-gap-control"]');

    // Type a value into the first seam via the same click-to-type path a user takes: click
    // the always-visible value button, then set the (React-controlled) input's value through
    // its native setter + input event -- Puppeteer's synthesized keyboard select-all does not
    // reliably clear a controlled input's existing text before typing.
    const gapControls = await page.$$('[data-testid="stitch-gap-control"]');
    const valueButton = await gapControls[0].$('button');
    await valueButton.click();
    await page.waitForSelector('[data-testid="stitch-gap-control"] input');
    const input = await gapControls[0].$('input');
    await input.evaluate((el, val) => {
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, val);
        el.dispatchEvent(new Event('input', { bubbles: true }));
    }, '250ms');
    await page.keyboard.press('Enter');
    await page.waitForFunction(
        () => document.querySelectorAll('[data-testid="stitch-gap-control"]')[0]?.getAttribute('data-gap-ms') === '250',
        { timeout: 5000 }
    );

    // Both seams start at the punctuation-suggested 520ms, so type the second one
    // down to 0 as well -- the zero-state dashed box must be part of the shot.
    const valueButton1 = await gapControls[1].$('button');
    await valueButton1.click();
    await page.waitForFunction(
        () => document.querySelectorAll('[data-testid="stitch-gap-control"]')[1]?.querySelector('input') !== null,
        { timeout: 5000 }
    );
    const input1 = await gapControls[1].$('input');
    await input1.evaluate((el, val) => {
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, val);
        el.dispatchEvent(new Event('input', { bubbles: true }));
    }, '0');
    await page.keyboard.press('Enter');
    await page.waitForFunction(
        () => document.querySelectorAll('[data-testid="stitch-gap-control"]')[1]?.getAttribute('data-gap-ms') === '0',
        { timeout: 5000 }
    );
    // INTENT: One zero-width seam and one typed 250ms seam visible in the same frame, plus
    // the zoom controls that make the timeline's real time-scale geometry legible.
    await captureShot(page, 'gap-editing-gap-editing.png', {
        fullPage: false,
        scrollToSelector: '[data-testid="stitch-gap-control"]',
    });
}
