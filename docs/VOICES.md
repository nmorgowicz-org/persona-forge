# Voices: built-in, saved and imported

The **Voice Library** page has the tabs **My voices**, **Built-in voices**, **Segments** and **Compare**. This
page covers the first two and imported voices; [Compare](COMPARE.md) has its own page. Which engines exist and how
to install them is in [Speech engines](SPEECH_ENGINES.md); the endpoints are in the
[HTTP API reference](api/HTTP_API_REFERENCE.md).

## Built-in voices

The tab lists the presets of **every engine, installed or not**, from one searchable grid. Voices of an engine
that is not installed come from a catalog bundled with the app, so browsing needs no download. Those cards carry a
**Needs install** badge and an **Install** button; the install runs inline with step progress, and the list
reloads with the engine's real voices when it finishes.

### Find a voice

- **Search**, then filter by **Language** (English only by default, or All languages; a note says how many were
  hidden and offers *Show all languages*), **Engine**, **Gender** (any, female, male, unspecified), **Accent** and
  **Category**. **Installed only** appears while at least one engine is not installed.
- A card shows the engine, language, category and, where known, gender, accent and age, plus *Imported*,
  *Needs install* and *API default* badges. The star adds it to your favorites.
- Where the gender comes from differs by engine (the API reports it as `gender_source`):
  - Phonon: the engine's own catalog. 12 of its 37 voices are "character" voices with no gender.
  - Kokoro: the voice name (`af_`, `bm_`: the second letter is `f` or `m`). The accent comes from the first letter
    (`a` American, `b` British).
  - Pocket and Pocket Lite: the app's own note on the voice.
  - **Kitten TTS 2 publishes no gender.** 9 of its 115 voices state it in their name (`NewsAnchorFemale`). The other
    106 are **estimated** from the median pitch of the voice's reference clip and shown as "Female (est.)" or
    "Male (est.)". Treat "(est.)" as a guess: the plan checked the rule against 27 voices whose gender it judged
    from first names and it agreed on 22; the misses were low female and high male voices. That sample is the
    author's own judgement, not ground truth.

### Preview, use and serve

- **Preview** generates the sample "Hi, I'm <name>. This is how I sound." locally, so it needs the engine installed
  (an Install button replaces Preview until then). One preview plays at a time and nothing autoplays. A cold engine shows its
  loading or warming message and the preview continues when it is ready.
- **Details** opens a drawer with the **API voice ID** and a copy button (for example `kokoro:af_heart`), the
  voice's note, and, for an imported voice, where it came from.
- **Use in Speak** is offered for Pocket voices only. For a pack voice, choose its engine in Speak's *Engine*
  selector (shown when more than one engine is installed).
- **Set as API default** makes the voice the one served when a request names no voice. It works for every installed
  engine's voices and is not offered for an engine that is not installed. See
  [Speech engines](SPEECH_ENGINES.md#serving-an-engine-from-the-api).

## My voices (saved voices and cloning)

A saved voice keeps its families and variants as before. Each voice card also has an **Engines** row, one chip
per engine, saying whether the voice is ready there:

| Chip | Meaning |
| --- | --- |
| `Pocket ✓ Ready` | Pocket clones the voice on every request; there is nothing to prepare. |
| `Kitten 2 • Prepare` / `Pocket Lite • Prepare` | The engine is installed but has not prepared this voice yet. |
| `… Preparing`, `! Failed, retry` | Preparation is running, or failed with a reason in the chip's explanation. |
| `… · Install to use` | The engine is not installed; choosing the chip opens Speech engines. |
| `Phonon — not supported`, `Kokoro — not supported` | These engines cannot clone; use their built-in voices. |

Hover, focus or tap a chip for the plain-language explanation. Every chip is a button.

### Prepare

- **Prepare** (choose the chip) readies a saved voice for an engine now. Only Kitten TTS 2 and Pocket Lite need
  it. Pocket Lite uses the reference clip. **Kitten 2 clones with the transcript**, so a review step first asks you
  to confirm the stored words or type them ("Confirm and prepare", "Save words and prepare"). **Generate with
  Whisper** there is a separate action you click; preparation never runs it.
- Preparing is also lazy: a request that uses a valid saved voice on Kitten 2 or Pocket Lite prepares it on first
  use. Prepare just moves that cost earlier. A missing or unreviewed Kitten transcript is refused with a message
  instead; **synthesis never transcribes or downloads a model**.
- A voice is ready for an engine only for the exact reference audio, transcript (Kitten) and pack version it was
  prepared with. Editing the reference, switching the active variant, editing Kitten's transcript or a pack
  update makes it **Prepare** again. A ready chip does not promise a loaded engine: after an idle unload the engine
  rebuilds the state locally on its next request.
- **Cancel** stops a queued or waiting preparation; a worker step already running finishes within its timeout.
- Choose **Compare engines** in a voice's actions to open [Compare](COMPARE.md) with that voice on every installed
  cloning engine.

## Imported voices

An *imported voice* is not cloned from audio. It is a **prepared voice file** that an engine already understands,
like the built-in voices it ships with. Only **Phonon 31M** accepts them (its runtime registers a precomputed
speaker embedding). Kitten's native `voices.json`/NPZ format is **not importable**: its runtime reads a fixed
snapshot and has no add-voice call.

1. Install Phonon 31M (the button is disabled until then, because Phonon's own parser must accept every import).
2. In **Built-in voices**, choose **Add imported voice**, pick a `.safetensors` file of at most 1 MiB and give it a
   name (1-40 letters, digits, spaces, dots, underscores or dashes, starting with a letter or digit).
3. The file is checked offline: structure, tensor name, type, shape, and that Phonon can load it. Pickle and
   NumPy/Torch archives, paths and URLs are refused. Nothing is executed. A name already in use is refused.
4. The voice appears with an *Imported* badge, is served as `phonon:imported-<slug>` (the slug is made from the name, for example `imported-my-narrator`), and can be the API default.
   Its drawer shows the file name, checksum, date and engine revision.

**Remove imported voice** deletes only the app's own copy and its record; catalog voices and your source file are
untouched. Imports are stored under `<app data>/imported-voices` (`IMPORTED_VOICES_DIR` overrides it). If the
removed voice was the API default, requests report `api_default_unavailable` rather than using another speaker.
A damaged or incompatible import is not offered for synthesis.

## Known limitations

- **No Compare button in the Built-in drawer.** To compare engines, start from a saved voice or open the Compare tab.
- **No preview cache.** None of these engines ships upstream sample files, so previews are always generated
  locally and need the engine installed.
- **Gender for Kitten TTS 2 is an estimate** (above), and Kitten has no language field: voices named for a
  language (for example `KoreanNewsAnchor`) are read as that language, so English-only hides them.
- **Cloning only on three engines**, and only the saved voice's reference clip is used. Cloned-voice similarity
  was measured on a few references; see the plan §4.6 and §9.1. Male voices and your own recordings were untested.
- **Imports are Phonon-only**, one file format, one size limit. The real Phonon catalog roundtrip was checked on
  one Mac.
- **Linux CUDA is untested and no pack engine was exercised over HTTP on Windows** (see
  [Speech engines](SPEECH_ENGINES.md#known-limitations)).
- A saved voice served by the API without naming an engine still uses the active backend: name `kitten2` or
  `pocket-lite` in `model` to clone it there (Integrations does this for you). The API default can be a saved voice
  on a cloning pack engine.
