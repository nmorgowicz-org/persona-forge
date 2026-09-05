<div align="center">

# Persona Forge

**Open-source voice-cloning and voice-design studio**

Clone a voice from a single reference WAV. Design accents from scratch. Assemble clips in a
timeline editor. Serve it all over an OpenAI-compatible API. One process, no training required —
run it in the container or natively.

[![Release](https://img.shields.io/github/v/release/nmorgowicz-org/persona-forge)](https://github.com/nmorgowicz-org/persona-forge/releases)
[![Container](https://img.shields.io/badge/ghcr.io-persona--forge-blue?logo=docker)](https://github.com/nmorgowicz-org/persona-forge/pkgs/container/persona-forge)
[![License](https://img.shields.io/github/license/nmorgowicz-org/persona-forge)](LICENSE)

</div>

---

**OmniVoice accent audition** — generate candidates per segment, across accents, in real time:

![OmniVoice audition](docs/screenshots/omnivoice-audition-gif--omnivoice--audition.gif)

**Voice Design → Stitch Studio** — compose a voice from trait chips, then assemble it into a
reference clip:

![Voice Design to Stitch](docs/screenshots/design-to-stitch-gif--pocket-tts--design-to-stitch.gif)

---

## What it does

| | Feature | Description |
|---|---|---|
| 🎙️ | **Voice cloning** | Clone a voice from one reference WAV. No fine-tuning, no training data. |
| 🎨 | **Voice Design** | Compose a voice from trait chips — gender, register, texture, persona — or a free-form description. Preview, then save. |
| 🌏 | **Accent design** | OmniVoice generates candidates per segment across accents. Audition them, cherry-pick the best takes, stitch the winners into a reference voice. |
| ✂️ | **Stitch Studio** | Drag segments onto a timeline. Per-clip trim, fade, gain, and DSP, with live preview. |
| 📚 | **Voice Library** | Prosody fingerprints (LUFS, speech rate, pause ratio, peak dBFS) for every saved voice. Fork, edit, compare variants. |
| 🎵 | **Prosody Adjustment** | Precise control over pause placement — choose style presets (Calm, Energetic, etc.), see word-level pause markers, and preview before saving. |
| 🔌 | **OpenAI-compatible API** | `POST /v1/audio/speech` — a drop-in TTS endpoint for any OpenAI SDK client. |
| ⚡ | **CPU-first** | The default pocket-tts backend runs on any CPU. Qwen3-TTS (PyTorch or OpenVINO) is opt-in. |
| 🎛️ | **Live runtime config** | Change backend, idle-unload timer, and DSP knobs from the UI. No restart. |

---

## Screenshots

<table>
<tr>
<td width="50%">

**Speak** — generate from any saved voice

![Speak](docs/screenshots/speak-generate--pocket-tts--after-generate.png)

</td>
<td width="50%">

**Voice Design** — compose from trait chips

![Voice Design](docs/screenshots/hero-voice-design--neutral--panel.png)

</td>
</tr>
<tr>
<td width="50%">

**Prosody Adjustment** — control pause placement with word-level precision

![Prosody Adjustment](docs/screenshots/prosody-adjustment--pocket-tts--calm-adjusted.png)

</td>
<td width="50%">

**Stitch Studio** — assemble clips into a new reference voice

![Stitch Studio](docs/screenshots/stitch-assembly--neutral--assembly.png)

</td>
</tr>
</table>

---

## Getting started

**Prerequisites:** Docker and Docker Compose. Images are published to
[GHCR](https://github.com/nmorgowicz-org/persona-forge/pkgs/container/persona-forge) on every
release — this pulls a prebuilt image rather than building from source.

```bash
git clone https://github.com/nmorgowicz-org/persona-forge.git
cd persona-forge
cp .env.example .env          # optional: set HF_TOKEN, REF_AUDIO_PATH
echo 'PERSONA_FORGE_IMAGE=ghcr.io/nmorgowicz-org/persona-forge:latest' >> .env
docker compose up -d persona-forge
open http://localhost:8318
```

The service is ready when `GET /health` reports `"model_loaded": true` — roughly 30–60 seconds on
first boot with the default pocket-tts backend.

Leave `PERSONA_FORGE_IMAGE` unset only if you're changing the Dockerfile/source and want
`docker compose up --build` to build a local image instead. See [Container image](#container-image)
below for pinned version/digest tags.

> **No Compose, or don't want to clone the repo?** Run the published image directly:
>
> ```bash
> docker run -d --name persona-forge -p 8318:8318 \
>   -v "$(pwd)/data/model:/root/.cache/huggingface/hub" \
>   -v "$(pwd)/data/voices:/voices" \
>   ghcr.io/nmorgowicz-org/persona-forge:latest
> ```
>
> Covers the pocket-tts default with a persistent model cache and voice library. See
> [compose.yml](compose.yml) for the full set of optional volumes/env (reference audio, OpenVINO
> IR cache, segment library).

> **Want the Qwen engine with OpenVINO acceleration?** Run the export step first and set
> `TTS_BACKEND=openvino`. See [HOW_TO_RUN.md](docs/HOW_TO_RUN.md).

> **Don't want Docker?** Persona Forge also runs natively — via a source checkout (`uv sync`), an
> installed wheel (`pip install persona-forge`), or a self-contained launcher archive with no
> Python preinstall required. See [RUN_LOCAL.md](docs/RUN_LOCAL.md); to move an existing Docker
> deployment's data over, see [MIGRATION.md](docs/MIGRATION.md).

> On macOS, verify the release checksum first. If Gatekeeper blocks the extracted launcher, run
> `xattr -dr com.apple.quarantine .` from that archive's directory. See [native setup](docs/RUN_LOCAL.md)
> for the safety note.

---

## HTTP API

Everything is served on port 8318. There is **no authentication by default**.

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health, model status, backend and mount info |
| `POST` | `/v1/audio/speech` | **OpenAI-compatible TTS** |
| `POST` | `/generate` | Native TTS — adds `language`, `seed`, `prosody_repair` |
| `GET` | `/voices` | Saved voices with prosody metrics |
| `POST` | `/voice_design` | Generate a voice from a description |
| `POST` | `/omnivoice/audition` | Accent audition (streaming, multi-segment) |
| `GET`/`POST` | `/runtime/config` | Live runtime configuration |

```bash
curl -s http://localhost:8318/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "Hello world", "voice_id": "vd_000000000001", "response_format": "mp3"}' \
  --output speech.mp3
```

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8318/v1", api_key="unused")
client.audio.speech.create(
    model="tts-1", voice="vd_000000000001", input="Hello world"
).stream_to_file("speech.mp3")
```

Full reference: **[docs/api/HTTP_API_REFERENCE.md](docs/api/HTTP_API_REFERENCE.md)**

---

## Container image

```bash
docker pull ghcr.io/nmorgowicz-org/persona-forge:latest
```

Pin a version — or a digest — for anything you depend on:

```bash
docker pull ghcr.io/nmorgowicz-org/persona-forge:v1.4.1  # x-release-please-version
```

Tags: `latest`, `v<major>.<minor>.<patch>`, `<git-sha>`. Use any of these as
`PERSONA_FORGE_IMAGE` (see [Getting started](#getting-started)) instead of `latest` for a
reproducible deploy.

**Container vs. native — why both exist.** The runtime depends on pinned torch/torchaudio
wheels, source-level patches applied to installed third-party packages (qwen_tts, transformers),
a per-accelerator-family install step, and a Node/npm frontend build (`frontend/`) that has to
run and get bundled in ahead of time. The container packages all of that into one pinned,
reproducible artifact — backend and frontend — so none of it is visible to the operator, and it
stays the most-tested, canonical deployment path. Persona Forge also installs and runs natively
(source checkout via `uv`, an installable wheel/sdist, or a self-contained launcher archive) —
the same pins and patches are applied by the native `setup`/`serve` commands instead of a
container build. See [RUN_LOCAL.md](docs/RUN_LOCAL.md) for the native paths and their current
hardware-validation status, and [MIGRATION.md](docs/MIGRATION.md) for moving between the two.

---

## Documentation

**[📖 Full documentation index](docs/README.md)**

Quick links: [Docker setup](docs/HOW_TO_RUN.md) · [Native setup](docs/RUN_LOCAL.md) ·
[Migration](docs/MIGRATION.md) · [Environment](docs/ENV_REFERENCE.md) ·
[HTTP API](docs/api/HTTP_API_REFERENCE.md) ·
[Architecture](docs/architecture/SYSTEM_OVERVIEW.md) ·
[Contributing](docs/dev/LOCAL_SETUP.md)

---

## Security

No authentication and no TLS out of the box. Persona Forge is built to run on a trusted LAN or
behind an authenticated reverse proxy. **Do not expose port 8318 to the internet** without putting
auth in front of it.

Reporting: [SECURITY.md](SECURITY.md)

---

## License

[MIT](LICENSE) — with the exception of OmniVoice model weights, which are CC-BY-NC
(non-commercial). See [OMNIVOICE_REFERENCE.md](docs/architecture/OMNIVOICE_REFERENCE.md).
