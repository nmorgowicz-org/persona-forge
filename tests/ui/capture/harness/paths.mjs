// Shared paths, ports, and constants for the capture harness.
// Ported from local-llm-foundry's tests/ui/capture/harness/paths.mjs.
import fs from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

export const __filename = fileURLToPath(import.meta.url);
export const __dirname = dirname(__filename);
export const UI_DIR = join(__dirname, '../..');
export const ROOT_DIR = join(UI_DIR, '../..');
export const ARTIFACTS_DIR = join(ROOT_DIR, 'docs/screenshots/artifacts');
export const SCREENSHOTS_DIR = join(ROOT_DIR, 'docs/screenshots');

export const DEFAULT_VIEWPORT = { width: 1440, height: 900, deviceScaleFactor: 1 };
export const DEFAULT_PORT = parseInt(process.env.SCREENSHOT_PORT || '8892', 10);

// Point captures at an already-running persona-forge instance instead of spawning one.
// Example: CAPTURE_REMOTE_SERVER=http://192.168.10.72:8318 node tests/ui/capture/index.mjs --source remote
export const REMOTE_SERVER = process.env.CAPTURE_REMOTE_SERVER || 'http://192.168.10.72:8318';

export const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

fs.mkdirSync(ARTIFACTS_DIR, { recursive: true });
fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

// Screenshots are grouped into category subdirectories (mirroring
// tests/ui/capture/scenarios/<category>/) instead of one flat directory.
// index.mjs sets this before running each scenario; shot.mjs reads it to
// pick the output directory.
let activeCategory = null;
export function setArtifactCategory(category) {
    activeCategory = category || null;
}
export function currentArtifactsDir() {
    const dir = activeCategory ? join(ARTIFACTS_DIR, activeCategory) : ARTIFACTS_DIR;
    fs.mkdirSync(dir, { recursive: true });
    return dir;
}

// Runtime tag (which backend the captured UI is showing -- or `neutral` for
// backend-independent chrome) gets woven into every filename so it's visible
// without opening the image: `<scenario>--<runtime>--<description>.ext`.
let activeScenarioKey = null;
let activeRuntimeTag = null;
export function setArtifactRuntime(scenarioKey, runtimeTag) {
    activeScenarioKey = scenarioKey || null;
    activeRuntimeTag = runtimeTag || null;
}

// Individual shots within a mixed-runtime scenario can override the
// scenario's default tag by passing { runtimeTag: '...' } into captureShot/etc.
export function tagFilename(filename, overrideRuntimeTag) {
    const runtimeTag = overrideRuntimeTag || activeRuntimeTag;
    if (!runtimeTag) return filename;
    const scenarioKey = activeScenarioKey;
    if (scenarioKey && filename.startsWith(`${scenarioKey}-`)) {
        const rest = filename.slice(scenarioKey.length + 1);
        return `${scenarioKey}--${runtimeTag}--${rest}`;
    }
    if (scenarioKey && filename === scenarioKey) {
        return `${scenarioKey}--${runtimeTag}`;
    }
    return `${runtimeTag}--${filename}`;
}
