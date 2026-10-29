# Speech engines

Persona Forge speaks through one or more **engines**. Pocket TTS is built in and is the default. The
others are optional **engine packs** you install from **Runtime → Speech engines**. A pack downloads once,
then runs offline in its own process beside the active engine, so installing one never replaces or unloads
Pocket.

This page is the task guide. The design and the measurements behind it are in
[the multi-engine plan](archive/multi-engine-speech/20261023-kokoro_phonon_kittentts2.md); every endpoint is in the
[HTTP API reference](api/HTTP_API_REFERENCE.md). Related pages: [Voices](VOICES.md), [Compare](COMPARE.md).

## The engines

| Engine (`id`) | Cloning | Built-in voices | Streams PCM | Runs on | Install size |
| --- | --- | --- | --- | --- | --- |
| **Pocket TTS** (`pocket-tts`), default | Yes, from a saved voice | 30 curated (English, French, German, Spanish, Italian, Portuguese) | Yes | CPU everywhere; a GPU is optional | built in |
| **Pocket Lite 18M** (`pocket-lite`) | Yes, from the reference clip (no transcript needed) | 21 English | Yes | CPU | about 190 MB |
| **Kitten TTS 2** (`kitten2`) | Yes, needs a reviewed transcript of the reference | 115 | No | Apple silicon (MLX) or an NVIDIA GPU. Not CPU-only machines, not Intel Macs | about 2.4 GB; about 2 GB in memory while loaded |
| **Phonon 31M** (`phonon-31m`) | No (it can import prepared voice files) | 37 English | Yes | CPU with AVX2 (Intel/AMD, about 2013 or newer) or Apple silicon | about 70 MB |
| **Kokoro 82M** (`kokoro`) | No | 41: English (US and UK), Spanish, French, Hindi, Italian, Portuguese | No | CPU | about 120 MB |

Sources: the engine registry (`src/persona_forge/speech_engines.py`), the voice catalog
(`src/persona_forge/engine_voice_catalog.json`) and the per-engine install sections of the API reference.

**Cloning vs presets.** A *preset* is a voice the engine ships (`kokoro:af_heart`). *Cloning* makes an engine
speak like one of your saved voices. Only Pocket, Pocket Lite and Kitten TTS 2 clone; for the others a saved
voice is refused with a message, never replaced by another speaker. Each saved voice is prepared per cloning
engine: see [Voices](VOICES.md).

**Speed and seed.** Phonon and Kokoro honour a `speed` control; Pocket, Pocket Lite and Kitten 2 ignore it.
Kokoro has no seed control; the other engines accept a `seed`.

No engine has been ranked best. Pocket stays the default because it is the baseline everywhere; the plan records
why and what was and was not listened to (§0.1, §4.6, §9).

## Hardware fit and speed on your machine

- Each card shows a **fit line** computed from your hardware: "Recommended for Apple silicon (runs on MLX)",
  "Recommended for your NVIDIA GPU", "Runs on CPU (N cores); no GPU needed", or the reason an engine cannot run
  here (for example Kitten 2 on an Intel Mac or a CPU-only PC).
- While no pack is installed, a dismissible hint at the top of the section says which engines your hardware can
  run. It states support only, never quality or speed.
- **Install check.** Every pack install ends with a "Measuring speed" step that times one short sentence through
  the pack's own worker after warm-up. The card shows, for example, "Install check: RTF 0.18 on mps". RTF is
  compute seconds per second of audio: below 1 is faster than real time. A machine that is slower than real time
  gets a labelled warning, not a failed install. Set `ENGINE_INSTALL_SPEED_CHECK=0` to skip the step
  ([ENV_REFERENCE](ENV_REFERENCE.md)).
- **Run quick benchmark** repeats the measurement on demand: one cold request and three warm ones, saved with the
  load average at the time. It is machine-specific and load-sensitive, so treat it as a rough figure.
  "Speed not measured" means neither has run.

## Install, repair and remove

1. Open **Runtime → Speech engines** and choose **Install** on the engine's card. Progress shows as "Step N of M".
   Timings the plan recorded: about 13 s for Kokoro and 50 s for Phonon on a Windows host with an empty
   package cache (§9.3.3), and 2-3 minutes for Kitten 2 with warm caches (its weights dominate; a first attempt
   took longer, §7.1.2).
2. When it finishes the card reads *Verified*. Packs are checked locally against pinned hashes; **Verify hashes**
   re-checks them, and **Repair** replaces **Install** on a pack that is not verified. A retry resumes where it stopped.
3. **Remove** deletes the pack. It is disabled while the engine serves the API default (see below).
4. In **Voices → Built-in** you can also install an engine from one of its voices.

Packs live under `<DATA_DIR>/engine-packs` (`ENGINE_PACKS_DIR` overrides it).

### Details and logs

**Details** on a pack card shows what was pinned versus what is actually installed in the pack's own environment
(flagged when they differ), the weights and their revisions, the runtime device, the install check, the idle-unload
value and where it came from, and disk use. It also shows the last 200 lines of the install log and of the worker's
log. Lines are redacted before they are stored (tokens, `Authorization`/`Bearer` values). A failed install offers
**Retry** and **View logs**.

### Hugging Face token (Pocket Lite)

Pocket Lite's cloning weights are in a gated Hugging Face repository (`kyutai/pocket-tts`). You must accept its
terms on Hugging Face yourself; the app never does that for you.

1. Create a token on Hugging Face and paste it into the masked field on the Pocket Lite card.
2. Choose **Install**. The token is stored in `<DATA_DIR>/.engine_hf_token` (owner-only), is given only to the
   download process, and is never shown again, logged or returned by the API.
3. Without the card, `HF_TOKEN` in the environment or your own `huggingface-cli login` also work.

A failed install says which case it was: no token, a token Hugging Face rejected (it answers 401 to a mistyped
token exactly as to none), terms not accepted (403), or a network error, each with a link.

## Warming, loading and idle unload

- An installed pack is **idle** until first used: the first request starts its worker. The header status chip
  reads *Ready* for an idle engine because it loads on the next request. States are `idle` → `loading` → (`warming`) → `ready`, or `error`.
- **Warming** is a first call that compiles or caches kernels. Today only Kitten 2 has a separate warm-up step (about
  33 s for the compiled NVIDIA path; about 1 s measured on an Apple-silicon Mac). The card and the header chip show "Loading" or "Warming".
- An API request to an engine that is still loading waits up to `ENGINE_WARM_WAIT_S` seconds (default 5), then
  receives `503` with `Retry-After` and the error code `engine_warming`; the load carries on in the background.
  The Speak page, Compare and voice previews retry by themselves; OpenAI SDKs retry a 503 and honour
  `Retry-After`.
- **Idle unload is per engine.** Each pack's manifest sets how long it may sit unused before its worker is
  stopped: 30 minutes for Kitten 2 (a reload pays the compile again), 10 minutes for Phonon, Kokoro and Pocket
  Lite. An environment variable per engine overrides it (`KITTEN2_IDLE_UNLOAD_S`, `PHONON_IDLE_UNLOAD_S`,
  `KOKORO_IDLE_UNLOAD_S`, `POCKET_LITE_IDLE_UNLOAD_S`; `0` keeps it loaded). Pocket's own idle unload is the
  separate `IDLE_UNLOAD_SECONDS`. The runtime rules are in
  [RUNTIME_AND_MEMORY](agent-reference/RUNTIME_AND_MEMORY.md) §6.

## Serving an engine from the API

Pack engines are served by `POST /v1/audio/speech` beside the active backend; no switch is needed.

- Name the engine with `model` (`kokoro`, `phonon-31m`, `kitten2`, `pocket-lite`; aliases such as `phonon` work)
  and/or use a **namespaced voice ID**, which implies its engine even when `model` is a generic label such as
  `tts-1`:

  ```sh
  curl http://localhost:8318/v1/audio/speech \
    -H 'Content-Type: application/json' \
    -d '{"model":"kokoro","input":"Hello there.","voice":"kokoro:af_heart","response_format":"mp3"}' \
    -o hello.mp3
  ```

  Voice IDs look like `kokoro:af_heart`, `phonon:Zoey`, `kitten2:Bruno`, `pocket-lite:alba`, `pocket:vera`.
  Copy them from **Voices → Built-in** (the drawer's *API voice ID*) or the **Integrations** page, which also
  generates curl, Python and JavaScript snippets. `GET /v1/models` and `GET /v1/audio/voices` list what a server
  can serve.
- A request that names a voice that belongs to a different engine than `model` is a 400, not a substitution.
- **Make a pack voice the API default.** The default is an *engine + voice*. Choose **Set as API default** in
  **Voices → Built-in** (or **Use as API default…** on a pack's card, which opens that view). A request with no
  voice and no engine then goes to that engine. A saved voice can be the default on a cloning pack engine too;
  it is prepared on the first request. An engine that serves the default cannot be removed until you change the
  default. If it is removed outside the app, requests fail with `409 api_default_unavailable` and Integrations
  shows how to repair it, rather than silently using another speaker.
- **Loudness.** Engines differ in native level, so every complete clip is normalised to one level before encoding
  (about −23 dBFS RMS of the speech, boosted by at most 12 dB, peaks limited under −1 dBFS). Opt out with
  `"normalize_loudness": false` on a request or `TTS_NORMALIZE_LOUDNESS=0` on the server. Streamed PCM is never
  normalised (a stream cannot know the whole clip's level); those responses say
  `X-Loudness-Normalized: false`.
- **English only.** Two separate settings, both English-leaning by default:
  - *Voice languages* (in Speech engines, and on the Built-in tab) hides non-English voices from lists. It is
    on by default and does not stop a request from naming any voice.
  - *Enforce English on the API* (Integrations, **off** by default) makes `/v1/audio/speech` return a 400 for a
    non-English voice or `language`, naming the voice and the setting.
- **Unknown `model` labels** (`tts-1`, `custom`) are served by the API default or the active engine, so existing
  OpenAI clients keep working; the response says `X-Model-Recognized: false` for a label it did not recognise.

### Why a request cannot switch engines

There is no "allow API requests to switch engines" setting, on purpose. Pack engines never need a switch. What is
left is swapping the built-in backends (Pocket, OpenVINO, PyTorch), and the one swap that exists is a global
reconfiguration: it makes `/generate` and `/v1/audio/speech` answer 503 to everyone while it runs, changes the
backend before the load succeeds, cannot roll back, and loads 5.4-6.9 GiB. Change the backend in **Runtime**. See
"Switching engines from a request" in the [API reference](api/HTTP_API_REFERENCE.md) and plan §4.3.

## Known limitations

- **Where it has been verified.** Mostly one Apple-silicon Mac with real packs. On a Windows RTX 5090 host the
  installs, workers and engine classes ran, but **no pack engine was exercised through the HTTP path on Windows**
  (plan §7.1.2, §9.3.2). On Linux, Pocket Lite, Phonon and Kokoro ran in a throwaway container on an Intel CPU; **Linux CUDA is
  untested** (the code path is shared with Windows).
- **Kitten TTS 2 needs Apple silicon or an NVIDIA GPU.** On NVIDIA its fast mode needs a C++ compiler (Microsoft C++
  Build Tools on Windows, `build-essential` on Linux); without one it runs in a standard mode that measured
  RTF 1.2-1.3 on a 5090, slower than real time. Its first compiled call takes about 33 s and is paid again after
  an idle unload; the compile is not cached across restarts.
- **Streaming PCM is available only from Pocket, Pocket Lite and Phonon.** Kitten 2 and Kokoro answer a `pcm`
  request with one whole clip. Kokoro is excluded on purpose (sentence-chunking would add audible seams).
- **Pocket Lite is tied to the app's `pocket-tts` version.** After an app update that changes it, the engine
  reports "installed with X, app has Y" when it loads. Its message says "Repair", but by reading the code the
  Repair button is only shown for a pack that is not verified, which a version mismatch does not cause; if you
  see it, **Remove** the pack and **Install** it again. The real "terms not accepted" (403) path was not
  exercised live, only through stubs.
- **Phonon 40M, KokoClone and Kitten's small models are not offered.** The plan records why (§9).
- **Speed figures are per machine.** The numbers on cards are from your hardware and load, not a promise. Unmeasured
  engines say so.
- **No quality ranking.** Listening results are the owner's, on a few references; male voices and your own
  recordings were untested. Use [Compare](COMPARE.md) to judge on your voices.
- **Request-time switching is not supported** (above), and there is no preview cache because none of these engines
  ships upstream sample files.
