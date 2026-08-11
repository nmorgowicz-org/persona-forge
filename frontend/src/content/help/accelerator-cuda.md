### NVIDIA GPU detected, not mapped in yet

This host has an NVIDIA GPU, but the container can't reach it yet. Add GPU passthrough and,
if you're pinning the family explicitly, set `GPU_FAMILY=cuda`.

```yaml
services:
  app:
    environment:
      - GPU_FAMILY=cuda
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

Equivalent `docker run` flag: `--gpus all`. Requires the NVIDIA Container Toolkit
(`nvidia-container-runtime`) installed on the host.

After updating compose/`docker run`, recreate the container (`docker compose up -d --force-recreate`)
and click **Re-detect** below.
