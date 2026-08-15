// SCENARIO INTENT: Show OmniVoice advanced candidates-per-segment control in use.
import { captureShot } from '../../harness/shot.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    await page.goto(baseURL, { waitUntil: 'networkidle0' });
    await page.click('[data-testid="nav-voice-design"]');
    await page.click('[data-testid="engine-omnivoice"]');
    await page.waitForSelector('[data-testid="accent-bank-au"]');
    await page.click('[data-testid="accent-bank-au"]');

    // The advanced (candidates-per-segment) control only renders in Expert mode.
    const isExpert = await page.$eval(
        '[data-testid="experience-level-toggle"]',
        (el) => el.textContent.includes('Expert')
    );
    if (!isExpert) await page.click('[data-testid="experience-level-toggle"]');

    await page.waitForSelector('[data-testid="omnivoice-advanced-toggle"]');
    await page.click('[data-testid="omnivoice-advanced-toggle"]');
    const candidatesInput = await page.waitForSelector('[data-testid="omnivoice-candidates-per-segment"]');
    await page.waitForFunction(
        (el) => {
            const h1 = el.getBoundingClientRect().top;
            return new Promise((resolve) => {
                requestAnimationFrame(() => {
                    requestAnimationFrame(() => {
                        const h2 = el.getBoundingClientRect().top;
                        resolve(h1 === h2);
                    });
                });
            });
        },
        { timeout: 5000, polling: 100 },
        candidatesInput
    );
    await candidatesInput.evaluate((el) => {
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, '2');
        el.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await page.waitForFunction(
        (el) => el.value === '2',
        { timeout: 5000 },
        candidatesInput
    );

    await page.waitForSelector('[data-testid="omnivoice-script"]');
    await page.type('[data-testid="omnivoice-script"]', 'The quick brown fox jumps over the lazy dog.');
    await page.click('[data-testid="omnivoice-audition-button"]');
    await page.waitForFunction(
        () => document.querySelectorAll('[data-testid="omnivoice-candidate-take"]').length >= 2,
        { timeout: 120000 }
    );
    const takeHandles = await page.$$('[data-testid="omnivoice-candidate-take"]');
    await page.evaluate((el) => el.scrollIntoView({ block: 'center', behavior: 'instant' }), takeHandles[takeHandles.length - 1]);
    await page.waitForFunction(
        (el) => {
            const r = el.getBoundingClientRect();
            return r.top >= 0 && r.top < window.innerHeight;
        },
        { timeout: 5000 },
        takeHandles[takeHandles.length - 1]
    );
    // INTENT: Multiple candidate takes per segment rendered.
    await captureShot(page, 'omnivoice-candidates-persona-forge-candidates.png', { fullPage: true });
}
