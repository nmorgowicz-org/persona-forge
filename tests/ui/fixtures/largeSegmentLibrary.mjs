// Deterministic generator plus Playwright request-interception helper for a 250-row segment
// library spread across five projects. Used to test Voice Library / segment-browser scale
// behavior (project filtering, one-active-player audition, no eager audio fetches) without
// committing 250 real audio files to Git -- every /audio request is fulfilled with the same
// tiny, valid, generated-in-memory WAV body.
const PROJECT_NAMES = ['Narration', 'Commercials', 'Podcast Intros', 'IVR Prompts', 'Audiobook'];

/** A minimal valid 24kHz mono 16-bit PCM WAV, `durationSec` long (default ~50ms of silence).
 * Generated at call time so no binary fixture lives in the repo. */
export function makeTinyWavBuffer(durationSec = 0.05) {
  const sampleRate = 24000;
  const numSamples = Math.round(sampleRate * durationSec);
  const dataSize = numSamples * 2;
  const buffer = Buffer.alloc(44 + dataSize);
  buffer.write('RIFF', 0);
  buffer.writeUInt32LE(36 + dataSize, 4);
  buffer.write('WAVE', 8);
  buffer.write('fmt ', 12);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate * 2, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write('data', 36);
  buffer.writeUInt32LE(dataSize, 40);
  // PCM samples stay zeroed (silence) by Buffer.alloc.
  return buffer;
}

/** Deterministic 250-row (by default) segment metadata fixture, five projects round-robin. */
export function generateLargeSegmentLibrary(count = 250) {
  const rows = [];
  for (let i = 0; i < count; i++) {
    const projectIndex = i % PROJECT_NAMES.length;
    rows.push({
      segment_id: `seg_${i.toString(16).padStart(12, '0')}`,
      text: `Segment number ${i + 1} for scale testing.`,
      instruct: 'Neutral narrator',
      tags: [],
      engine: 'omnivoice',
      accent_id: null,
      sample_rate: 24000,
      created_at: 1700000000 + i,
      duration_sec: 1 + (i % 10) * 0.5,
      project_id: `proj_large_${projectIndex}`,
      project_name: PROJECT_NAMES[projectIndex],
    });
  }
  return rows;
}

/** Registers route interception for the segment list and per-segment audio endpoints on
 * `page`. The list is fulfilled entirely from the deterministic fixture (never touches the
 * real backend); each `/audio` request is logged into the returned `audioRequests` array (so a
 * test can assert on eager-fetch behavior) and fulfilled with the same tiny WAV body. */
export async function installLargeSegmentLibrary(page, { count = 250 } = {}) {
  const rows = generateLargeSegmentLibrary(count);
  const wav = makeTinyWavBuffer();
  const audioRequests = [];

  await page.route('**/omnivoice/segments', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ segments: rows }),
    });
  });

  await page.route('**/omnivoice/segments/*/audio', async (route) => {
    audioRequests.push(route.request().url());
    await route.fulfill({ status: 200, contentType: 'audio/wav', body: wav });
  });

  return { rows, projectNames: PROJECT_NAMES, audioRequests };
}
