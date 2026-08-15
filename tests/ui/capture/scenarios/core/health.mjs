// SCENARIO INTENT: Prove the service is up and reporting backend/model status.
import { captureShot } from '../../harness/shot.mjs';

export default async function (ctx) {
    const { page, baseURL } = ctx;
    // INTENT: /health JSON response, proving the backend is reachable.
    const res = await page.goto(`${baseURL}/health`);
    if (!res.ok()) throw new Error(`/health returned ${res.status()}`);
    await captureShot(page, 'health-health.png', { fullPage: true });
}
