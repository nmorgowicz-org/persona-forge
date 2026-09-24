// SCENARIO INTENT: Show the Stitch Studio readiness rail's honest state progression --
// blocked without enough source speech, warning below 10s, ideal at 10–15s, and overlong
// above 15s. Spacing changes the rendered total but cannot satisfy the source-material gate.
import { captureShot } from '../../harness/shot.mjs';

async function setGap(page, index, value) {
    const controls = await page.$$('[data-testid="stitch-gap-control"]');
    const control = controls[index];
    const valueButton = await control.$('button[aria-label^="Gap between clip"]');
    await valueButton.click();
    const input = await control.$('input[aria-label^="Gap between clip"]');
    await input.evaluate((el, next) => {
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, next);
        el.dispatchEvent(new Event('input', { bubbles: true }));
    }, value);
    await page.keyboard.press('Enter');
}

export default async function (ctx) {
    const { page, baseURL } = ctx;
    await page.goto(baseURL, { waitUntil: 'networkidle0' });
    await page.click('[data-testid="nav-stitch-studio"]');
    await page.waitForSelector('[data-testid="stitch-reference-readiness"]');

    await captureShot(page, 'readiness-states-blocked.png', {
        fullPage: false,
        scrollToSelector: '[data-testid="stitch-reference-readiness"]',
    });

    await page.click('[data-testid="stitch-picker-toggle-segments"], [data-testid="empty-state-action"]');
    await page.waitForSelector('[data-testid="segment-browser-dialog"]');
    const items = await page.$$('[data-testid="stitch-picker-item-segments"]');
    await items[0].click();
    await items[1].click();
    await items[2].click();
    await page.click('[data-testid="stitch-picker-insert-segments"]');
    await page.waitForFunction(
        () => document.querySelector('[data-testid="stitch-reference-readiness"]')?.getAttribute('data-readiness-state') === 'warning',
        { timeout: 5000 }
    );
    await captureShot(page, 'readiness-states-warning.png', {
        fullPage: false,
        scrollToSelector: '[data-testid="stitch-reference-readiness"]',
    });

    await setGap(page, 0, '2s');
    await setGap(page, 1, '2s');
    await page.waitForFunction(
        () => document.querySelector('[data-testid="stitch-reference-readiness"]')?.getAttribute('data-readiness-state') === 'ideal',
        { timeout: 5000 }
    );
    await captureShot(page, 'readiness-states-ideal.png', {
        fullPage: false,
        scrollToSelector: '[data-testid="stitch-reference-readiness"]',
    });

    await setGap(page, 0, '5s');
    await setGap(page, 1, '5s');
    await page.waitForFunction(
        () => document.querySelector('[data-testid="stitch-reference-readiness"]')?.getAttribute('data-readiness-state') === 'overlong',
        { timeout: 5000 }
    );
    await captureShot(page, 'readiness-states-overlong.png', {
        fullPage: false,
        scrollToSelector: '[data-testid="stitch-reference-readiness"]',
    });
}
