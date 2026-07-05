// Puppeteer-based screenshot/GIF capture harness. Local-only tool — never run in CI (§6 of
// docs/dev/resolved/E2E_AND_SCREENSHOTTING.md). By default spawns the same fake-model server
// used by Playwright (via run-server.mjs) on a distinct port so it can run alongside a real
// service (8318) and the Playwright test server (8319) without colliding. Pass --target <url>
// to point at an already-running instance instead (e.g. the dockermisc1 real-model tunnel, §7).
import { mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import puppeteer from 'puppeteer'
import { startFakeServer } from './run-server.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = join(__dirname, '..', '..')
const ARTIFACTS_DIR = join(REPO_ROOT, 'docs', 'screenshots', 'artifacts')
const SCREENSHOT_PORT = 8892

function outPath(feature, filename) {
  const dir = join(ARTIFACTS_DIR, feature)
  mkdirSync(dir, { recursive: true })
  return join(dir, filename)
}

async function screenshot(page, feature, filename) {
  const path = outPath(feature, filename)
  await page.screenshot({ path })
  console.log(`[capture] wrote ${path}`)
}

// Each scenario receives { page, baseURL } and must run its own interactions/screenshots.
// Scenarios must be deterministic — no clocks, no random content, no waiting on real timers
// tied to wall-clock time (e.g. VoiceDesign swap-in-progress UI is intentionally not screenshot
// here since its duration/visibility depends on real model swap timing).
const SCENARIOS = {
  async scenarioHealth({ page, baseURL }) {
    const res = await page.goto(`${baseURL}/health`)
    if (!res.ok()) throw new Error(`/health returned ${res.status()}`)
    await screenshot(page, 'core', 'health.png')
  },

  async scenarioHome({ page, baseURL }) {
    await page.goto(baseURL, { waitUntil: 'networkidle0' })
    await page.waitForSelector('[data-testid="speak-text-input"]')
    await screenshot(page, 'core', 'home.png')
  },

  async scenarioGenerate({ page, baseURL }) {
    await page.goto(baseURL, { waitUntil: 'networkidle0' })
    await page.waitForSelector('[data-testid="speak-text-input"]')
    await page.type('[data-testid="speak-text-input"]', 'Hello from the capture harness.')
    await screenshot(page, 'generate', 'before-generate.png')
    await page.click('[data-testid="speak-generate-button"]')
    await page.waitForSelector('[data-testid="speak-result"] audio')
    await screenshot(page, 'generate', 'after-generate.png')
  },

  async scenarioVoiceDesignPanel({ page, baseURL }) {
    await page.goto(baseURL, { waitUntil: 'networkidle0' })
    await page.click('[data-testid="nav-voice-design"]')
    await page.waitForSelector('[data-testid="voice-design-description"]')
    await screenshot(page, 'voice-design', 'panel-empty.png')
  },

  async scenarioVoiceDesignGenerate({ page, baseURL }) {
    await page.goto(baseURL, { waitUntil: 'networkidle0' })
    await page.click('[data-testid="nav-voice-design"]')
    await page.waitForSelector('[data-testid="voice-design-description"]')
    await page.type(
      '[data-testid="voice-design-description"]',
      'Warm, calm narrator with a slight British accent.',
    )
    await page.type(
      '[data-testid="voice-design-sample-text"]',
      'This is a short sample line for the voice.',
    )
    await screenshot(page, 'voice-design', 'filled.png')
    await page.click('[data-testid="voice-design-generate-button"]')
    await page.waitForSelector('[data-testid="voice-design-result"]')
    await screenshot(page, 'voice-design', 'result.png')
  },

  async scenarioVoicesList({ page, baseURL }) {
    await page.goto(baseURL, { waitUntil: 'networkidle0' })
    await page.click('[data-testid="nav-voice-design"]')
    await page.waitForSelector('[data-testid="voice-design-description"]')
    await page.type('[data-testid="voice-design-description"]', 'Bright, energetic assistant voice.')
    await page.type('[data-testid="voice-design-sample-text"]', 'This is a short sample line.')
    await page.click('[data-testid="voice-design-generate-button"]')
    await page.waitForSelector('[data-testid="voice-design-result"]')

    await page.click('[data-testid="nav-voice-library"]')
    await page.waitForSelector('[data-testid="voice-card"]')
    await screenshot(page, 'voice-library', 'list.png')
  },
}

function parseArgs(argv) {
  const args = { scenario: null, listScenarios: false, noAttach: false, target: null }
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i]
    if (arg === '--scenario') args.scenario = argv[++i]
    else if (arg === '--list-scenarios') args.listScenarios = true
    else if (arg === '--no-attach') args.noAttach = true
    else if (arg === '--target') args.target = argv[++i]
  }
  return args
}

async function main() {
  const args = parseArgs(process.argv.slice(2))

  if (args.listScenarios) {
    for (const name of Object.keys(SCENARIOS)) console.log(name)
    return
  }

  const names = args.scenario ? [args.scenario] : Object.keys(SCENARIOS)
  for (const name of names) {
    if (!SCENARIOS[name]) {
      console.error(`Unknown scenario: ${name}. Use --list-scenarios to see valid names.`)
      process.exitCode = 1
      return
    }
  }

  let server = null
  let baseURL = args.target
  if (!baseURL) {
    server = startFakeServer({ port: SCREENSHOT_PORT })
    await server.waitUntilHealthy()
    baseURL = server.url
  }

  const browser = await puppeteer.launch({
    headless: !args.noAttach ? 'new' : false,
    defaultViewport: { width: 1440, height: 900 },
  })

  try {
    // Sequential by design — scenarios share no state but running concurrently against a
    // single-worker Flask process (or a real service under test) would be misleading.
    for (const name of names) {
      console.log(`[capture] running ${name}`)
      const page = await browser.newPage()
      try {
        await SCENARIOS[name]({ page, baseURL })
      } finally {
        await page.close()
      }
    }
  } finally {
    await browser.close()
    if (server) server.stop()
  }
}

main().catch((err) => {
  console.error(err)
  process.exitCode = 1
})
