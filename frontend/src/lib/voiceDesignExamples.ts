// Curated "tried and true" instruct strings for the qwen3-tts VoiceDesign checkpoint, plus
// short authoring tips. Nick's feedback, 2026-07-03: the chip presets (voiceDesignChips.ts)
// assume users can assemble a good description from independent trait chips, but this engine
// responds better to a few concrete, holistic reference descriptions than to combinatorial
// chip soup — these exist so users have real starting points to copy/adapt, not just guess.
//
// Sourced from Qwen3-TTS-specific writeups (not generic TTS advice): the official
// Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign model card, GetStream's "How To Design AI Voices in
// Minutes Using Qwen3-TTS", and Voice Creator Pro's Qwen3-TTS voice-design prompting guide.
// No accent-carrying examples here on purpose — see composeDescription's docstring in
// voiceDesignChips.ts for why accent control was removed from this engine's UI entirely.

export interface VoiceDesignExample {
  id: string
  label: string
  text: string
}

export const VOICE_DESIGN_EXAMPLES: VoiceDesignExample[] = [
  {
    id: 'warm-support-agent',
    label: 'Warm customer support agent',
    text: 'A friendly, patient female voice in her late 20s, clear mid-range tone, unhurried pace, warm reassuring diction.',
  },
  {
    id: 'confident-narrator',
    label: 'Confident narrator',
    text: 'A warm, confident female narrator in her 30s, clear mid-range voice.',
  },
  {
    id: 'documentary-male',
    label: 'Documentary narrator (male)',
    text: 'A calm, middle-aged male voice, deep, magnetic tone. Slow, steady pace, clear articulation. Suitable for documentary narration.',
  },
  {
    id: 'energetic-livestream',
    label: 'Energetic young female (livestream/sales)',
    text: 'A young, lively female voice with a fast speaking rate and noticeably rising intonation, suitable for introducing products with enthusiasm.',
  },
  {
    id: 'authoritative-male',
    label: 'Deep, authoritative male',
    text: 'A middle-aged male voice, warm and authoritative, low-medium pitch, measured pace, rich timbre, suited to documentary narration.',
  },
  {
    id: 'calm-elderly-male',
    label: 'Calm elderly voice',
    text: "An elderly man in his 80s, a reedy, quavering voice that wavers with age, slow and breathless, with a warm scratchy quality.",
  },
  {
    id: 'cranky-grandmother',
    label: 'Cranky elderly grandmother',
    text: "An elderly grandmother, 80 years old, high-pitched, thin, croaky old woman's voice. She sounds cranky and a little shrill.",
  },
  {
    id: 'fantasy-deity',
    label: 'Powerful fantasy deity',
    text: 'A powerful male god, immensely deep, booming, resonant bass voice that reverberates as if echoing through a vast marble hall.',
  },
  {
    id: 'mysterious-fantasy-female',
    label: 'Mysterious fantasy female',
    text: 'Gender: female. Age: fifties. Pitch: low, eerie resonance. Pace: slow, deliberate, with dramatic pauses. Emotion: mysterious, commanding. Characteristics: smooth, powerful.',
  },
  {
    id: 'podcast-host-upbeat',
    label: 'Podcast host (upbeat)',
    text: 'A cheerful male voice in his early 30s, warm mid-range tone, upbeat, energetic pacing.',
  },
  {
    id: 'podcast-host-calm',
    label: 'Podcast host (calm counterpart)',
    text: 'A thoughtful female voice in her 40s, calm, lower register, measured, deliberate pacing.',
  },
  {
    id: 'noir-detective',
    label: 'Noir detective',
    text: 'A grizzled male detective in his 50s, gravelly, world-weary baritone, clipped sentences, a dry sardonic undertone.',
  },
  {
    id: 'anime-villain',
    label: 'Anime villain',
    text: 'A low-pitched male voice with dramatic pitch swings, intimidating and mischievous.',
  },
  {
    id: 'late-night-radio',
    label: 'Late-night radio host',
    text: 'A smooth, alluring young female voice, late twenties, low pitch, breathy, intimate delivery.',
  },
]

export const VOICE_DESIGN_AUTHORING_TIPS: string[] = [
  'Keep it to 2–4 sentences (~40–80 words) — shorter reads as a generic voice, longer tends to introduce conflicting traits.',
  'Describe how it sounds — pitch, pace, timbre — not what it would say or its personality. "A slow, deep baritone" works better than "a wise old philosopher."',
  'Cover the traits in order: who (gender/age) → how (pitch/pace/timbre) → optional use-case ("suitable for documentary narration").',
  "Avoid contradictory descriptors in one description (e.g. \"extremely high pitch\" and \"deep bass tone\" together) — the model resolves the conflict unpredictably rather than blending them.",
  'Real names or celebrity likenesses are not supported.',
  "This engine's English is plain English only — regional or foreign-accent requests don't come through reliably here, so don't describe an accent.",
]
