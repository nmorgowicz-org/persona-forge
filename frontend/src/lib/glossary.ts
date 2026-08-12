export const GLOSSARY: Record<string, { term: string; definition: string }> = {
  'LUFS': {
    term: 'LUFS',
    definition: 'Loudness Units relative to Full Scale. A standard for measuring perceived loudness, ensuring audio sounds consistent across different devices.',
  },
  'dBTP': {
    term: 'dBTP',
    definition: 'Decibels True Peak. Measures the absolute highest peak of a signal, including inter-sample peaks, to prevent digital clipping.',
  },
  'dBFS': {
    term: 'dBFS',
    definition: 'Decibels relative to Full Scale. The standard way of measuring digital audio levels, where 0 dB is the maximum possible level.',
  },
  'True Peak': {
    term: 'True Peak',
    definition: 'The actual peak level of the reconstructed analog signal, which can be higher than the digital sample peak.',
  },
  'RMS': {
    term: 'RMS',
    definition: 'Root Mean Square. An average of the audio level over time, providing a better sense of overall loudness than peak levels.',
  },
  'Guidance Scale': {
    term: 'Guidance Scale',
    definition: 'Controls how strongly the model follows the provided prompt. Higher values lead to more distinct styles but can introduce artifacts.',
  },
  'Num Steps': {
    term: 'Num Steps',
    definition: 'The number of iterations the model uses to generate audio. More steps generally improve quality but increase generation time.',
  },
  'Voice State': {
    term: 'Voice State',
    definition: 'A compact numerical representation of a speaker\'s identity and style, allowing the model to clone a voice without reprocessing the reference audio every time.',
  },
  'Symmetric Seed': {
    term: 'Symmetric Seed',
    definition: 'A number used to initialize the random generator. Using the same seed with the same settings produces the same audio output.',
  },
  'RTF': {
    term: 'Real-Time Factor',
    definition: 'A measure of generation speed. An RTF of 0.1 means 1 second of audio is generated in 0.1 seconds of real time.',
  },
}

export interface TroubleshootingEntry {
  id: string
  title: string
  symptoms: string
  fix: string
}

// Deep-linkable by id (see store.openGlossaryAt) — the same id scheme C4's diagnosis
// chips use as kbEntryId to link a detected problem straight to its fix.
export const TROUBLESHOOTING: Record<string, TroubleshootingEntry> = {
  clipping: {
    id: 'clipping',
    title: 'Clipping / digital distortion',
    symptoms: 'Crackling, harsh or "fuzzy" sound, especially on loud syllables or plosives.',
    fix: 'Lower Guidance Scale slightly, or reduce the reference audio\'s input level before cloning. If it only happens on stitched output, check each clip\'s gain in the Stitch Timeline before the crossfade.',
  },
  'robotic-cadence': {
    id: 'robotic-cadence',
    title: 'Robotic or flat cadence',
    symptoms: 'Speech sounds monotone, rushed, or mechanically evenly-paced.',
    fix: 'Try a Style Preset closer to natural speech (e.g. Storyteller or Conversational), increase Num Steps for a cleaner render, or use the prosody nudge controls to add pitch/pace variation on the flat segment.',
  },
  'accent-drift': {
    id: 'accent-drift',
    title: 'Accent drift across a longer take',
    symptoms: 'The accent is correct at the start of a segment but fades or shifts partway through, especially on long sentences.',
    fix: 'Raise Guidance Scale toward the top of its range (closer to 3.0) for tighter accent adherence, or split the sentence into shorter segments and stitch them — shorter generations drift less.',
  },
  'stitching-artifacts': {
    id: 'stitching-artifacts',
    title: 'Clicks or pops at clip boundaries',
    symptoms: 'An audible click, pop, or abrupt level jump right where two clips join in the Stitch Timeline.',
    fix: 'Increase the crossfade duration for that gap, or nudge the clip trim so the join lands in a silent/low-energy part of the waveform rather than mid-word.',
  },
}
