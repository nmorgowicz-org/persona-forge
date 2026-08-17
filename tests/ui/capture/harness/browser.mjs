import puppeteer from 'puppeteer';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { DEFAULT_VIEWPORT, sleep } from './paths.mjs';

export async function launchBrowser(viewport = DEFAULT_VIEWPORT, { noAttach = false } = {}) {
    const userDataDir = mkdtempSync(join(tmpdir(), 'persona-forge-capture-'));
    const browser = await puppeteer.launch({
        // `headless: 'new'` was removed from Puppeteer; the option is `boolean | 'shell'` and
        // `true` is the new headless mode. Passing the stale string still worked on macOS but
        // broke browser launch on Windows (EBUSY on first_party_sets.db on a fresh profile dir).
        headless: !noAttach,
        userDataDir,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-cache', '--disable-service-workers'],
    });
    const closeBrowser = browser.close.bind(browser);
    browser.close = async (...args) => {
        try {
            await closeBrowser(...args);
        } finally {
            try {
                rmSync(userDataDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
            } catch {
            }
        }
    };
    const page = await browser.newPage();
    await page.setCacheEnabled(false);
    await page.setViewport(viewport);
    return { browser, page };
}

export async function gotoApp(page, baseUrl, waitUntil = 'networkidle0') {
    await page.goto(baseUrl, { waitUntil });
    page.__fontDiagnostics = await assertDeterministicFonts(page);
    await page.evaluate(() => { document.documentElement.dataset.screenshotCapture = 'true'; });
    await sleep(1500);
}

// persona-forge is a React SPA navigated via [data-testid="nav-*"], not the
// #view-setup / #page-* / #settings-modal DOM local-llm-foundry drives.
export async function gotoPage(page, baseURL, navTestId, readySelector) {
    await gotoApp(page, baseURL);
    await page.click(`[data-testid="${navTestId}"]`);
    await page.waitForSelector(readySelector, { timeout: 15000 });
}

const REQUIRED_FACES = ['Geist Variable', 'Geist Mono Variable'];

export async function assertDeterministicFonts(page) {
    const diagnostics = await page.evaluate(async (families) => {
        // Force the required faces to download first. They are lazy: until a glyph is
        // needed they sit at status 'unloaded', and both the measurement and the
        // enumeration below would then describe the fallback rather than the real face.
        await Promise.all(families.map((family) =>
            document.fonts.load(`400 16px "${family}"`, '0123456789 RTF 1.23x')));
        await document.fonts.ready;

        // Enumerate faces that actually loaded. Two things are deliberately avoided here:
        // document.fonts.check(), which returns true whenever a fallback can render the
        // string; and unfiltered enumeration, which includes merely-declared faces.
        const loadedFaces = [...new Set([...document.fonts]
            .filter((face) => face.status === 'loaded')
            .map((face) => face.family))];
        return {
            status: document.fonts.status,
            loadedFaces: loadedFaces.sort(),
            missingFaces: families.filter((family) => !loadedFaces.includes(family)),
            // Every face is bundled and Vite-served same-origin. Any request to a font CDN
            // means a regression that makes captures depend on network reachability.
            externalFontRequests: performance.getEntriesByType('resource')
                .map((entry) => entry.name)
                .filter((url) => /fonts\.(googleapis|gstatic)\.com|use\.typekit|fonts\.bunny/i.test(url)),
            rootFontSize: getComputedStyle(document.documentElement).fontSize,
            bodyFontFamily: getComputedStyle(document.body).fontFamily,
        };
    }, REQUIRED_FACES);

    if (diagnostics.status !== 'loaded' || diagnostics.missingFaces.length) {
        throw new Error(`Fonts not deterministically loaded: ${JSON.stringify(diagnostics)}`);
    }
    if (diagnostics.externalFontRequests.length) {
        throw new Error(`External font requests break capture determinism: ${JSON.stringify(diagnostics)}`);
    }
    if (diagnostics.rootFontSize !== '16px') {
        throw new Error(`Root font size is ${diagnostics.rootFontSize}, expected the explicit 16px baseline`);
    }
    return diagnostics;
}
