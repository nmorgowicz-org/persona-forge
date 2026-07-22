### AMD GPU detected, not mapped in yet

This host has an AMD GPU, but the container can't reach it yet. Add device passthrough and,
if you're pinning the family explicitly, set `GPU_FAMILY=rocm`.

```yaml
services:
  app:
    environment:
      - GPU_FAMILY=rocm
    devices:
      - /dev/kfd
      - /dev/dri
    group_add:
      - video
```

Equivalent `docker run` flags: `--device=/dev/kfd --device=/dev/dri --group-add video`.

After updating compose/`docker run`, recreate the container (`docker compose up -d --force-recreate`)
and click **Re-detect** below.
