// Thin re-export shim. The implementation moved to
// tests/ui/capture/harness/server.mjs as part of the capture harness port
// (docs/plans/20260815-screenshot_and_docs_edit.md Step 1.6). Kept because
// tests/ui/playwright.config.js and tests/ui/fixtures/generate-capture-fixtures.mjs
// still import this path directly.
import { fileURLToPath } from 'node:url'
export { startFakeServer } from './capture/harness/server.mjs'

if (fileURLToPath(import.meta.url) === process.argv[1]) {
  const { startFakeServer } = await import('./capture/harness/server.mjs')
  const port = parseInt(process.argv[2] || '8319', 10)
  const server = startFakeServer({ port })
  await server.waitUntilHealthy()
  console.log(`[run-server] fake_model_server healthy at ${server.url}`)
}
