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
import { startRealServer } from './run-real-server.mjs'
import { createRecorder, framesToGif, cleanupFrames } from './lib/gif.mjs'

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

  async scenarioVoiceVariantList({ page, baseURL }) {
    await page.goto(baseURL, { waitUntil: 'networkidle0' })
    await page.click('[data-testid="nav-voice-library"]')
    await page.waitForSelector('[data-testid="voice-card"]')
    await screenshot(page, 'voice-library', 'variant-list.png')
  },

  async scenarioVoicePromoteVariant({ page, baseURL }) {
    // Seeded fixtures ship one family member already promoted; duplicate it (which copies
    // family_id but drops is_default) to get a non-default sibling this scenario can promote.
    const { voices } = await (await fetch(`${baseURL}/voices`)).json()
    const familyMember = voices.find((v) => v.family_id)
    if (!familyMember) throw new Error('scenarioVoicePromoteVariant: no family_id voice in fixtures to fork from')
    await fetch(`${baseURL}/voices/${familyMember.voice_id}/duplicate`, { method: 'POST' })

    await page.goto(baseURL, { waitUntil: 'networkidle0' })
    await page.click('[data-testid="nav-voice-library"]')
    await page.waitForSelector('[data-testid="voice-card"]')
    await screenshot(page, 'voice-library', 'promote-before.png')

    const triggers = await page.$$('[data-testid="voice-actions-trigger"]')
    let promoted = false
    for (const trigger of triggers) {
      await trigger.click()
      const setDefaultBtn = await page.$('[data-testid="voice-set-default"]:not([disabled])')
      if (setDefaultBtn) {
        await Promise.all([
          page.waitForResponse((res) => res.url().includes('/set-default') && res.ok()),
          setDefaultBtn.click(),
        ])
        await page.waitForFunction(
          () => document.body.innerText.includes('DEFAULT'),
          { timeout: 10000 }
        )
        await page.keyboard.press('Escape')
        promoted = true
        break
      }
      await page.keyboard.press('Escape')
    }
    if (!promoted) throw new Error('scenarioVoicePromoteVariant: no promotable (non-default) voice found in fixtures')

    await screenshot(page, 'voice-library', 'promote-after.png')
  },

  async scenarioAlignmentCompare({ page, baseURL }) {
    await page.goto(baseURL, { waitUntil: 'networkidle0' })
    await page.click('[data-testid="nav-voice-library"]')
    await page.waitForSelector('[data-testid="voice-card"]')
    await page.waitForSelector('[data-testid="alignment-compare"]')
    await screenshot(page, 'prosody', 'alignment-compare.png')
  },

  async scenarioSegmentLibraryBrowse({ page, baseURL }) {
    await page.goto(baseURL, { waitUntil: 'networkidle0' })
    await page.click('[data-testid="nav-stitch-studio"]')
    await page.waitForSelector('[data-testid="stitch-picker-toggle-segments"]')
    await page.click('[data-testid="stitch-picker-toggle-segments"]')
    await page.waitForSelector('[data-testid="stitch-picker-item-segments"]')
    await page.waitForFunction(
      () => {
        const el = document.querySelector('[data-testid="stitch-picker-item-segments"]')?.closest('.shadow-lg')
        return el && getComputedStyle(el).opacity === '1'
      },
      { timeout: 5000 }
    )
    await screenshot(page, 'stitch-studio', 'segment-library-browse.png')
  },

  async scenarioStitchAssembly({ page, baseURL }) {
    await page.goto(baseURL, { waitUntil: 'networkidle0' })
    await page.click('[data-testid="nav-stitch-studio"]')
    await page.waitForSelector('[data-testid="stitch-picker-toggle-segments"]')
    await page.click('[data-testid="stitch-picker-toggle-segments"]')
    await page.waitForSelector('[data-testid="stitch-picker-item-segments"]')
    await page.waitForFunction(
      () => {
        const el = document.querySelector('[data-testid="stitch-picker-item-segments"]')?.closest('.shadow-lg')
        return el && getComputedStyle(el).opacity === '1'
      },
      { timeout: 5000 }
    )

    const checkboxes = await page.$$('[data-testid="stitch-picker-item-segments"]')
    await checkboxes[0].click()
    if (checkboxes[1]) await checkboxes[1].click()

    await page.click('[data-testid="stitch-picker-insert-segments"]')
    await page.waitForSelector('[data-testid="stitch-clip"]')
    await screenshot(page, 'stitch-studio', 'assembly.png')
  },

  async scenarioOmniVoiceAudition({ page, baseURL }) {
    await page.goto(baseURL, { waitUntil: 'networkidle0' })
    await page.click('[data-testid="nav-voice-design"]')
    await page.click('[data-testid="engine-omnivoice"]')
    await page.waitForSelector('[data-testid="accent-bank-au"]')
    await page.click('[data-testid="accent-bank-au"]')
    await page.waitForSelector('[data-testid="omnivoice-script"]')
    await page.type('[data-testid="omnivoice-script"]', 'The quick brown fox jumps over the lazy dog.')
    await page.click('[data-testid="omnivoice-audition-button"]')
    await page.waitForSelector('[data-testid="omnivoice-candidate-take"]', { timeout: 120000 })
    await screenshot(page, 'omnivoice', 'audition-candidates.png')

    await page.waitForFunction(
      () => document.querySelectorAll('[data-testid="omnivoice-candidate-take"]').length >= 3,
      { timeout: 120000 }
    )
    await page.click('[data-testid="omnivoice-stitch-button"]')
    const resultHandle = await page.waitForSelector('[data-testid="omnivoice-result"]', { timeout: 60000 })
    await page.evaluate((el) => el.scrollIntoView({ block: 'center', behavior: 'instant' }), resultHandle)
    await page.waitForFunction(
      (el) => {
        const r = el.getBoundingClientRect()
        return r.top >= 0 && r.top < window.innerHeight
      },
      { timeout: 5000 },
      resultHandle
    )
    await screenshot(page, 'omnivoice', 'audition-result.png')
  },

  async scenarioPersonaForgeCandidates({ page, baseURL }) {
    await page.goto(baseURL, { waitUntil: 'networkidle0' })
    await page.click('[data-testid="nav-voice-design"]')
    await page.click('[data-testid="engine-omnivoice"]')
    await page.waitForSelector('[data-testid="accent-bank-au"]')
    await page.click('[data-testid="accent-bank-au"]')

    await page.click('[data-testid="omnivoice-advanced-toggle"]')
    const candidatesInput = await page.waitForSelector('[data-testid="omnivoice-candidates-per-segment"]')
    await page.waitForFunction(
      (el) => {
        const h1 = el.getBoundingClientRect().top
        return new Promise((resolve) => {
          requestAnimationFrame(() => {
            requestAnimationFrame(() => {
              const h2 = el.getBoundingClientRect().top
              resolve(h1 === h2)
            })
          })
        })
      },
      { timeout: 5000, polling: 100 },
      candidatesInput
    )
    await candidatesInput.evaluate((el) => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set
      setter.call(el, '2')
      el.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await page.waitForFunction(
      (el) => el.value === '2',
      { timeout: 5000 },
      candidatesInput
    )

    await page.waitForSelector('[data-testid="omnivoice-script"]')
    await page.type('[data-testid="omnivoice-script"]', 'The quick brown fox jumps over the lazy dog.')
    await page.click('[data-testid="omnivoice-audition-button"]')
    await page.waitForFunction(
      () => document.querySelectorAll('[data-testid="omnivoice-candidate-take"]').length >= 2,
      { timeout: 120000 }
    )
    const takeHandles = await page.$$('[data-testid="omnivoice-candidate-take"]')
    await page.evaluate((el) => el.scrollIntoView({ block: 'center', behavior: 'instant' }), takeHandles[takeHandles.length - 1])
    await page.waitForFunction(
      (el) => {
        const r = el.getBoundingClientRect()
        return r.top >= 0 && r.top < window.innerHeight
      },
      { timeout: 5000 },
      takeHandles[takeHandles.length - 1]
    )
    await screenshot(page, 'omnivoice', 'persona-forge-candidates.png')
  },

  async scenarioAccentProjectGrouping({ page, baseURL }) {
    await page.goto(baseURL, { waitUntil: 'networkidle0' })
    await page.click('[data-testid="nav-voice-library"]')
    await page.waitForSelector('[data-testid="voice-library-group-by-project"]')
    await page.click('[data-testid="voice-library-group-by-project"]')
    await page.waitForSelector('[data-testid="segment-project-group"]')
    const group = await page.$('[data-testid="segment-project-group"]')
    await page.evaluate((el) => el.scrollIntoView({ block: 'center', behavior: 'instant' }), group)
    await page.waitForFunction(
      (el) => {
        const r = el.getBoundingClientRect()
        return r.top >= 0 && r.top < window.innerHeight
      },
      { timeout: 5000 },
      group
    )
    await screenshot(page, 'voice-library', 'project-grouping.png')
  },

  // Screenshots are taken sequentially between driveActions steps rather than on a concurrent
  // fixed-cadence loop — under real model-inference CPU load, a background screenshot loop can be
  // starved for the entire scenario, producing a GIF with zero usable frames (see gif.mjs).
  async scenarioOmniVoiceAuditionGif({ page, baseURL }) {
    const path = outPath('omnivoice', 'audition.gif')
    const prefix = 'omnivoice-audition'
    cleanupFrames()
    const recorder = createRecorder(prefix)

    await page.goto(baseURL, { waitUntil: 'networkidle0' })
    await page.click('[data-testid="nav-voice-design"]')
    await page.click('[data-testid="engine-omnivoice"]')
    await page.waitForSelector('[data-testid="accent-bank-au"]')
    await page.click('[data-testid="accent-bank-au"]')
    await page.waitForSelector('[data-testid="omnivoice-script"]')
    await page.type('[data-testid="omnivoice-script"]', 'The quick brown fox jumps over the lazy dog.')
    await recorder.snap(page)

    await page.click('[data-testid="omnivoice-audition-button"]')
    await recorder.snap(page)

    // Poll for candidates, snapping between polls — no concurrent driveActions activity during
    // this wait, so screenshots aren't contended with clicks/typing/navigation.
    const candidateDeadline = Date.now() + 120000
    while (Date.now() < candidateDeadline) {
      const count = await page
        .$$eval('[data-testid="omnivoice-candidate-take"]', (els) => els.length)
        .catch(() => 0)
      await recorder.snap(page)
      if (count >= 3) break
      await new Promise((r) => setTimeout(r, 1000))
    }

    await page.click('[data-testid="omnivoice-stitch-button"]')
    const resultHandle = await page.waitForSelector('[data-testid="omnivoice-result"]', { timeout: 60000 })
    await page.evaluate((el) => el.scrollIntoView({ block: 'center', behavior: 'instant' }), resultHandle)
    await page.waitForFunction(
      (el) => {
        const r = el.getBoundingClientRect()
        return r.top >= 0 && r.top < window.innerHeight
      },
      { timeout: 5000 },
      resultHandle
    )
    await recorder.snap(page)

    framesToGif(prefix, path, 2)
    cleanupFrames()
    console.log(`[capture] wrote ${path}`)
  },

  // Snapping only while the page is otherwise idle guarantees every frame lands.
  async scenarioDesignToStitchWizardGif({ page, baseURL }) {
    const path = outPath('wizard', 'design-to-stitch.gif')
    const prefix = 'design-to-stitch'
    cleanupFrames()
    const recorder = createRecorder(prefix)

    await page.goto(baseURL, { waitUntil: 'networkidle0' })
    await recorder.snap(page)

    await page.click('[data-testid="nav-voice-design"]')
    await recorder.snap(page)

    await page.click('[data-testid="engine-omnivoice"]')
    await recorder.snap(page)

    await page.waitForSelector('[data-testid="accent-bank-au"]')
    await page.click('[data-testid="accent-bank-au"]')
    await recorder.snap(page)

    await page.waitForSelector('[data-testid="omnivoice-script"]')
    await page.type('[data-testid="omnivoice-script"]', 'The quick brown fox jumps over the lazy dog.')
    await recorder.snap(page)

    await page.click('[data-testid="omnivoice-audition-button"]')
    await recorder.snap(page)

    // Poll for candidates, snapping between polls — no concurrent driveActions activity during
    // this wait, so screenshots aren't contended with clicks/typing/navigation.
    const candidateDeadline = Date.now() + 120000
    while (Date.now() < candidateDeadline) {
      const count = await page
        .$$eval('[data-testid="omnivoice-candidate-take"]', (els) => els.length)
        .catch(() => 0)
      if (count >= 3) break
      await recorder.snap(page)
      await new Promise((r) => setTimeout(r, 1500))
    }
    await recorder.snap(page)

    const lockButton = await page.waitForSelector('[data-testid="omnivoice-lock-segment"]')
    await lockButton.click()
    await page.waitForFunction((el) => el.disabled, { timeout: 15000 }, lockButton)
    await recorder.snap(page)

    await page.click('[data-testid="nav-stitch-studio"]')
    await page.waitForSelector('[data-testid="stitch-voice-name"]')
    await recorder.snap(page)

    await page.type('[data-testid="stitch-voice-name"]', 'Wizard Demo Voice')
    await recorder.snap(page)

    await page.click('[data-testid="stitch-picker-toggle-segments"]')
    await page.waitForSelector('[data-testid="stitch-picker-item-segments"]')
    await page.waitForFunction(
      () => {
        const el = document.querySelector('[data-testid="stitch-picker-item-segments"]')?.closest('.shadow-lg')
        return el && getComputedStyle(el).opacity === '1'
      },
      { timeout: 5000 }
    )
    await recorder.snap(page)

    const items = await page.$$('[data-testid="stitch-picker-item-segments"]')
    await items[0].click()
    await page.click('[data-testid="stitch-picker-insert-segments"]')
    await page.waitForSelector('[data-testid="stitch-clip"]')
    await recorder.snap(page)

    await page.click('[data-testid="stitch-save-voice"]')
    await page.waitForSelector('[data-testid="voice-card"]', { timeout: 30000 })
    await recorder.snap(page)

    framesToGif(prefix, path, 2)
    cleanupFrames()
    console.log(`[capture] wrote ${path}`)
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
  const args = {
    scenario: null,
    listScenarios: false,
    noAttach: false,
    target: null,
    real: false,
    modelSize: '0.6B',
    device: 'cpu',
  }
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i]
    if (arg === '--scenario') args.scenario = argv[++i]
    else if (arg === '--list-scenarios') args.listScenarios = true
    else if (arg === '--no-attach') args.noAttach = true
    else if (arg === '--target') args.target = argv[++i]
    else if (arg === '--real') args.real = true
    else if (arg === '--model-size') args.modelSize = argv[++i]
    else if (arg === '--device') args.device = argv[++i]
  }
  if (args.real && args.target) {
    throw new Error('--real and --target are mutually exclusive')
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
    server = args.real
      ? startRealServer({ port: SCREENSHOT_PORT, modelSize: args.modelSize, device: args.device })
      : startFakeServer({ port: SCREENSHOT_PORT })
    await server.waitUntilHealthy(args.real ? 120000 : undefined)
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
