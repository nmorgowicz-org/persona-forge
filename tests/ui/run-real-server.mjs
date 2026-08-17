// Thin re-export shim. The implementation moved to
// tests/ui/capture/harness/server.mjs as part of the capture harness port
// (docs/plans/20260815-screenshot_and_docs_edit.md Step 1.6). Kept because
// tests/ui/fixtures/generate-capture-fixtures.mjs still imports this path directly.
import { fileURLToPath } from 'node:url'
export { startRealServer } from './capture/harness/server.mjs'

if (fileURLToPath(import.meta.url) === process.argv[1]) {
  const { startRealServer } = await import('./capture/harness/server.mjs')
  const port = parseInt(process.argv[2] || '8319', 10)
  const server = await startRealServer({ port })
  await server.waitUntilHealthy()
  console.log(`[run-real-server] real server healthy at ${server.url}`)
}
