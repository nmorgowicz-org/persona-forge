// SCENARIO INTENT: Show accent voices grouped by project.
import { captureShot } from '../../harness/shot.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    await page.goto(baseURL, { waitUntil: 'networkidle0' });
    await page.click('[data-testid="nav-voice-library"]');
    await page.waitForSelector('[data-testid="voice-library-group-by-project"]');
    await page.click('[data-testid="voice-library-group-by-project"]');
    await page.waitForSelector('[data-testid="segment-project-group"]');
    const group = await page.$('[data-testid="segment-project-group"]');
    await page.evaluate((el) => el.scrollIntoView({ block: 'center', behavior: 'instant' }), group);
    await page.waitForFunction(
        (el) => {
            const r = el.getBoundingClientRect();
            return r.top >= 0 && r.top < window.innerHeight;
        },
        { timeout: 5000 },
        group
    );
    // INTENT: Voice library grouped by project.
    await captureShot(page, 'accent-project-grouping-project-grouping.png', { fullPage: true });
}
