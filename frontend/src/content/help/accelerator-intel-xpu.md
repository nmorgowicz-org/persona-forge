### Intel iGPU detected, not mapped in yet

This host has an Intel GPU, but the container can't reach it yet. Add render-node passthrough and,
if you're pinning the family explicitly, set `GPU_FAMILY=intel-xpu`.

```yaml
services:
  app:
    environment:
      - GPU_FAMILY=intel-xpu
    devices:
      - /dev/dri
    group_add:
      - render
```

Equivalent `docker run` flags: `--device=/dev/dri --group-add render`. On some hosts the `render`
group's GID must match the host's — check with `getent group render`.

After updating compose/`docker run`, recreate the container (`docker compose up -d --force-recreate`)
and click **Re-detect** below.
