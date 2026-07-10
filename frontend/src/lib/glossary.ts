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
