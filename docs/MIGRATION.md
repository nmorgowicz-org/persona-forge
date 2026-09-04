# Migrating between Docker and native

Persona Forge supports two deployment paths — the Docker container
([HOW_TO_RUN.md](HOW_TO_RUN.md)) and a native install
([RUN_LOCAL.md](RUN_LOCAL.md)) — and you can move a deployment's data between them. This
document maps the env vars and paths each side uses and walks through moving state in either
direction. Neither path is being deprecated; Docker remains the reproducible, most-tested
deployment (see RUN_LOCAL.md's "Docker vs. native" table for when to pick which).

## Why the paths differ

The container's paths are fixed mount points baked into `Dockerfile`/`compose.yml` — there's a
host bind mount or named volume behind each one. A native install has no such mount to anchor
to, so it resolves the same logical directories from a platform-appropriate application-data
root instead (`persona_forge/paths.py`). Both sides honor the same override env vars — a native
install can point straight at an existing Docker bind-mount directory instead of migrating data
at all, if you'd rather share the directories in place (single-user/local hosts only; see the
port-conflict note below either way).

## Env var and path mapping

| Data | Docker (container-side default) | Native (default, platform-dependent) | Shared override var |
|---|---|---|---|
| App/model cache | `MODEL_CACHE_CONTAINER_PATH=/root/.cache/huggingface/hub` (mounted from `MODEL_CACHE_PATH` on the host) | `<app data root>/models/huggingface/hub` | `MODEL_CACHE_DIR` (native) / `HF_HUB_CACHE` / `HF_HOME` |
| Pocket-TTS artifacts | `<MODEL_CACHE_CONTAINER_PATH>/pocket-tts` | `<model cache>/pocket-tts` | `POCKET_TTS_ARTIFACT_DIR` |
| OpenVINO IR | `OV_MODEL_DIR` under `/ov` (mounted from `OV_DATA_PATH` on the host) | `<app data root>/ov` | `OV_DATA_DIR` (native) |
| OpenVINO kernel cache | `OV_CACHE_DIR=/ov/cache` | `<ov root>/cache` | `OV_CACHE_DIR` |
| Voice library | `VOICE_LIBRARY_DIR=/voices` (mounted from `VOICE_LIBRARY_PATH`) | `<app data root>/voices` | `VOICE_LIBRARY_DIR` |
| Segment library | `SEGMENT_LIBRARY_DIR=/segments` (mounted from `SEGMENT_LIBRARY_PATH`) | `<app data root>/segments` | `SEGMENT_LIBRARY_DIR` |
| Runtime settings (`runtime.json`) | rides along on the voice-library mount | rides along on the voice library dir | `DATA_DIR` |
| Reference audio | mounted at `/voice/reference.wav` from `REF_AUDIO_PATH` | `<app data root>/reference.wav` | `REF_AUDIO` |
| HF token file | Docker-secret-style `HF_TOKEN_FILE` mount | `<app data root>/.hf_token` | `HF_TOKEN_FILE` |

The native app-data root itself (`PERSONA_FORGE_HOME` if set) defaults to:

- Linux: `$XDG_DATA_HOME/persona-forge` or `~/.local/share/persona-forge`
- macOS: `~/.config/persona-forge` (a homedir dotfile, for parity with Linux/Windows rather than the platform's Application Support bundle convention)
- Windows: `%LOCALAPPDATA%/persona-forge` or `~/AppData/Local/persona-forge`

Run `persona-forge doctor --json` (native) and look at the `paths` key for the exact resolved
directories on your machine — don't hand-compute them.

Everything in [ENV_REFERENCE.md](ENV_REFERENCE.md) that isn't a path (backend selection,
memory/threading tuning, silence trim, etc.) behaves identically on both sides — those are
runtime knobs read by the same application code, not container-specific.

## Migrating Docker → native

1. Stop the container: `docker compose down persona-forge`.
2. Note your host-side bind-mount paths from `.env` (`MODEL_CACHE_PATH`, `OV_DATA_PATH`,
   `VOICE_LIBRARY_PATH`, `SEGMENT_LIBRARY_PATH`).
3. Install natively (see [RUN_LOCAL.md](RUN_LOCAL.md)) and run `persona-forge doctor --json` once
   to see where it expects each directory, or set `PERSONA_FORGE_HOME`/the per-directory override
   vars above to point straight at your existing host paths (fastest — no file copying needed).
4. If you'd rather copy instead of pointing in place, copy each host directory's contents into
   the corresponding native default path from the table above (e.g. `VOICE_LIBRARY_PATH/*` →
   `<app data root>/voices/`).
5. Run `persona-forge setup` to create any directories that don't exist yet, then
   `persona-forge serve`.

## Migrating native → Docker

1. Stop the native process.
2. Set `MODEL_CACHE_PATH`, `OV_DATA_PATH`, `VOICE_LIBRARY_PATH`, `SEGMENT_LIBRARY_PATH` in `.env`
   to point at your native app-data subdirectories directly (from `persona-forge doctor --json`'s
   `paths`), or copy them into whatever host paths you want to bind-mount.
3. `docker compose up -d persona-forge`.

## Pros and cons

See [RUN_LOCAL.md](RUN_LOCAL.md)'s "Docker vs. native" table for the full comparison
(reproducibility, setup friction, isolation, accelerator install model). In short: Docker trades
setup friction for reproducibility and host isolation; native trades some reproducibility for a
lighter footprint and no Docker dependency.

## Port conflict

Both default to port **8318**. Don't run a Docker container and a native `serve` on the same
host at the same time without giving one of them an explicit port — `--port`/`PERSONA_FORGE_PORT`
natively, `ports:` in `compose.yml` for Docker. Whichever binds second will either fail to start
or shadow the first, depending on platform socket behavior; there's no coordination between the
two paths to prevent this.
