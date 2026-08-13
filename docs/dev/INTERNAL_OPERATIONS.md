# Internal operations (dockermisc1 and related)

Internal, host-specific notes. Not intended as public deployment documentation.

## dockermisc1 layout

- Host: shared live host; multiple containers coexist.
- Docker Compose lives at `~/docker/docker-compose.yml`.
- Qwen3-TTS data lives under:

  - `/var/data/autopirate/persona-forge/model`        → HF cache (MODEL_CACHE_PATH)
  - `/var/data/autopirate/persona-forge/openvino`     → OpenVINO IR (OV_DATA_PATH)
  - `/var/data/autopirate/persona-forge/voices`       → VoiceDesign voices (VOICE_LIBRARY_PATH)
  - `/var/data/autopirate/persona-forge/voice/`       → Reference audio (e.g. voice_A.wav)

## Basic operations

- Start:
  - `docker compose -f ~/docker/docker-compose.yml up -d persona-forge`
- Stop (don’t touch unrelated services):
  - `docker compose -f ~/docker/docker-compose.yml down persona-forge`
- Pull new image (example):
  - `export PERSONA_FORGE_IMAGE=ghcr.io/nmorgowicz-org/persona-forge:<sha>`
  - `docker compose -f ~/docker/docker-compose.yml pull persona-forge`
  - `docker compose -f ~/docker/docker-compose.yml up -d persona-forge`
- Export (stop service first if constrained):
  - `docker compose -f ~/docker/docker-compose.yml down persona-forge`
  - `docker compose -f ~/docker/docker-compose.yml run --rm export`
  - `docker compose -f ~/docker/docker-compose.yml up -d persona-forge`

Never run a 13 GiB export alongside a 10 GiB serve on this box (OOM).

## Validation after changes

After image, model, IR, or runtime-setting changes:

- `curl -fsS http://localhost:8318/health | python -m json.tool`
- `docker inspect --format '{{.Image}}' persona-forge`
- `docker exec persona-forge cat /sys/fs/cgroup/memory.current`
- `docker exec persona-forge cat /sys/fs/cgroup/memory.peak`
- `docker stats --no-stream persona-forge`

Record:
- Image tag/digest
- Source commit
- Model revision, IR metadata hash (from /health)
- Backend, compression, cache profile
- Prompts and sampling settings
- Latency, audio duration/RTF
- Memory current/peak, host available RAM, swap delta
- Listening notes

Use deterministic greedy runs for code/parity comparisons; use production sampling for
final listening and performance decisions.

## Rollback

- Fastest: restore previous immutable image and restart Compose.
- Backend: `TTS_BACKEND=pytorch`; verify via /health. Slower, for recovery only.

## Notes

- Only touch `persona-forge`; other services (`litellm*`, `headroom-proxy`, `crowdsec`,
  `hermes-*`, `*arr`, `searxng`) must not be affected.
- Keep port 8318 trusted-network-only or behind an authenticated reverse proxy.
