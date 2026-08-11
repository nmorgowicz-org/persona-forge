// Copies committed synthetic fixtures (tests/ui/fixtures/capture-data/) into a real server's
// disposable temp voice/segment library dirs. Never copies from real data/voices or data/segments.
import { cpSync, existsSync, readdirSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const CAPTURE_DATA_DIR = join(__dirname, '..', 'fixtures', 'capture-data')

export function seedCaptureFixtures(voiceLibraryDir, segmentLibraryDir) {
  const voicesSrc = join(CAPTURE_DATA_DIR, 'voices')
  const segmentsSrc = join(CAPTURE_DATA_DIR, 'segments')

  if (existsSync(voicesSrc)) {
    for (const entry of readdirSync(voicesSrc)) {
      cpSync(join(voicesSrc, entry), join(voiceLibraryDir, entry), { recursive: true })
    }
  }
  if (existsSync(segmentsSrc)) {
    for (const entry of readdirSync(segmentsSrc)) {
      cpSync(join(segmentsSrc, entry), join(segmentLibraryDir, entry), { recursive: true })
    }
  }
}
