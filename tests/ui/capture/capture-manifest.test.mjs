// Ported verbatim from local-llm-foundry's tests/ui/capture/capture-manifest.test.mjs
// per docs/plans/archive/screenshots/20260815-screenshot_and_docs_edit.md Step 1.15.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const captureDir = dirname(fileURLToPath(import.meta.url));
const manifest = resolve(captureDir, 'cli-manifest.mjs');

test('strict capture manifest has registered, intentional outputs', () => {
    assert.doesNotThrow(() => {
        execFileSync(process.execPath, [manifest, '--strict'], {
            cwd: resolve(captureDir, '../..'),
            stdio: 'pipe',
            encoding: 'utf8',
        });
    });
});
