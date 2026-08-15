// SCENARIO INTENT: Promote a non-default voice variant to family default.
import { captureShot } from '../../harness/shot.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    // Seeded fixtures ship one family member already promoted; duplicate it (which copies
    // family_id but drops is_default) to get a non-default sibling this scenario can promote.
    const { voices } = await (await fetch(`${baseURL}/voices`)).json();
    const familyMember = voices.find((v) => v.family_id);
    if (!familyMember) throw new Error('voice-promote-variant: no family_id voice in fixtures to fork from');
    await fetch(`${baseURL}/voices/${familyMember.voice_id}/duplicate`, { method: 'POST' });

    await page.goto(baseURL, { waitUntil: 'networkidle0' });
    await page.click('[data-testid="nav-voice-library"]');
    await page.waitForSelector('[data-testid="voice-card"]');
    // INTENT: Voice library before promoting a variant.
    await captureShot(page, 'voice-promote-variant-promote-before.png', { fullPage: true });

    const triggers = await page.$$('[data-testid="voice-actions-trigger"]');
    let promoted = false;
    for (const trigger of triggers) {
        await trigger.click();
        // Radix mounts the popover content into a portal with a CSS transition; give it a
        // beat to settle before querying, and wait for any previous popover's close
        // animation to clear so the selector below can't match a stale node.
        await new Promise((resolve) => setTimeout(resolve, 400));
        const setDefaultBtn = await page.$('[data-testid="voice-set-default"]:not([disabled])');
        if (setDefaultBtn) {
            await Promise.all([
                page.waitForResponse((res) => res.url().includes('/set-default') && res.ok()),
                setDefaultBtn.click(),
            ]);
            await page.waitForFunction(
                () => document.body.innerText.includes('DEFAULT'),
                { timeout: 10000 }
            );
            await page.keyboard.press('Escape');
            promoted = true;
            break;
        }
        await page.keyboard.press('Escape');
        await new Promise((resolve) => setTimeout(resolve, 200));
    }
    if (!promoted) throw new Error('voice-promote-variant: no promotable (non-default) voice found in fixtures');

    // INTENT: Voice library after promoting the variant to default.
    await captureShot(page, 'voice-promote-variant-promote-after.png', { fullPage: true });
}
