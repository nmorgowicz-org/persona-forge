// One-time generator for tests/ui/fixtures/capture-data/{voices,segments}. NOT called by
// capture.mjs — run manually after backend API changes affecting voice/segment shape:
//   node tests/ui/fixtures/generate-capture-fixtures.mjs
// Spawns a real server on throwaway temp dirs, drives the real HTTP API to create the
// minimum realistic library state, then copies the resulting dirs into capture-data/.
// All generated text/audio is synthetic/generic — never derived from real user data (§4.1).
import { cpSync, mkdirSync, rmSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { startRealServer } from '../run-real-server.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const OUT_DIR = join(__dirname, 'capture-data')

async function pollJob(url, jobId, { path = '/omnivoice/audition/progress', intervalMs = 1000, timeoutMs = 600000 } = {}) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const res = await fetch(`${url}${path}?job_id=${jobId}`)
    const body = await res.json()
    if (body.status === 'completed') return body
    if (body.status === 'failed') throw new Error(`job ${jobId} failed: ${body.message}`)
    await new Promise((r) => setTimeout(r, intervalMs))
  }
  throw new Error(`job ${jobId} did not complete within ${timeoutMs}ms`)
}

async function createVoiceViaDesign(url, { description, sampleText, familyId, variantName }) {
  const createRes = await fetch(`${url}/voice_design`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ description, sample_text: sampleText, language: 'English' }),
  })
  const created = await createRes.json()
  if (!createRes.ok) throw new Error(`voice_design create failed: ${JSON.stringify(created)}`)

  const saveRes = await fetch(`${url}/voice_design/preview/${created.preview_id}/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ family_id: familyId, variant_name: variantName }),
  })
  const saved = await saveRes.json()
  if (!saveRes.ok) throw new Error(`voice_design save failed: ${JSON.stringify(saved)}`)
  return saved.voice_id
}

async function createSegmentViaOmnivoice(
  url,
  { text, instruct, featureTags, projectId, projectName }
) {
  const auditionRes = await fetch(`${url}/omnivoice/audition`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ segments: [text], instruct, language: 'english', candidates_per_segment: 1 }),
  })
  const audition = await auditionRes.json()
  if (!auditionRes.ok) throw new Error(`audition failed: ${JSON.stringify(audition)}`)

  const progress = await pollJob(url, audition.job_id)
  const candidateId = progress.segments_completed[0].candidates[0].candidate_id

  const segRes = await fetch(`${url}/omnivoice/segments`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      candidate_id: candidateId,
      text,
      instruct,
      feature_tags: featureTags,
      project_id: projectId,
      project_name: projectName,
    }),
  })
  const seg = await segRes.json()
  if (!segRes.ok) throw new Error(`segment save failed: ${JSON.stringify(seg)}`)
  return seg
}

async function main() {
  console.log('[generate-capture-fixtures] spawning real server...')
  const server = startRealServer({ port: 8896, timeoutMs: 600000, seedFixtures: false })
  await server.waitUntilHealthy()
  console.log(`[generate-capture-fixtures] healthy at ${server.url}`)

  // --- Voices: one base voice with two variants (2nd promoted active), one duplicate. ---
  console.log('[generate-capture-fixtures] creating base voice...')
  const baseVoiceId = await createVoiceViaDesign(server.url, {
    description: 'a calm, neutral narrator voice',
    sampleText: 'This is a sample line used to preview the generated voice.',
  })

  console.log('[generate-capture-fixtures] creating variant 2 (family member, promoted default)...')
  const variant2Id = await createVoiceViaDesign(server.url, {
    description: 'a calm, neutral narrator voice, slightly warmer tone',
    sampleText: 'This is a sample line used to preview the generated voice.',
    familyId: baseVoiceId,
    variantName: 'warmer take',
  })

  console.log('[generate-capture-fixtures] promoting variant 2 to default...')
  await fetch(`${server.url}/voices/${variant2Id}/set-default`, { method: 'POST' })

  console.log('[generate-capture-fixtures] duplicating base voice...')
  await fetch(`${server.url}/voices/${baseVoiceId}/duplicate`, { method: 'POST' })

  // --- Segments: 2-3 sharing a project, 1-2 without, with distinct feature_tags. ---
  console.log('[generate-capture-fixtures] creating project segments...')
  await createSegmentViaOmnivoice(server.url, {
    text: 'The quick brown fox jumps over the lazy dog.',
    instruct: 'australian accent, female',
    featureTags: ['australian accent', 'upbeat'],
    projectId: 'proj_fixture01',
    projectName: 'Fixture Project',
  })
  await createSegmentViaOmnivoice(server.url, {
    text: 'Please hold while we connect your call.',
    instruct: 'australian accent, male',
    featureTags: ['australian accent', 'calm'],
    projectId: 'proj_fixture01',
    projectName: 'Fixture Project',
  })

  console.log('[generate-capture-fixtures] creating standalone segments...')
  await createSegmentViaOmnivoice(server.url, {
    text: 'Thank you for your patience during this process.',
    instruct: 'british accent, elderly',
    featureTags: ['british accent', 'formal'],
  })

  console.log('[generate-capture-fixtures] copying dirs into capture-data/...')
  rmSync(join(OUT_DIR, 'voices'), { recursive: true, force: true })
  rmSync(join(OUT_DIR, 'segments'), { recursive: true, force: true })
  mkdirSync(OUT_DIR, { recursive: true })
  cpSync(server.voiceLibraryDir, join(OUT_DIR, 'voices'), { recursive: true })
  cpSync(server.segmentLibraryDir, join(OUT_DIR, 'segments'), { recursive: true })

  console.log('[generate-capture-fixtures] done. Stopping server...')
  server.stop()
  process.exit(0)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
