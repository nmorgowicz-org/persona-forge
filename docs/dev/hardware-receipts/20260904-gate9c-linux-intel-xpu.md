# Gate 9C hardware receipt — Linux Docker + Intel iGPU (XPU)

Phase 9 of `docs/plans/20260829-no_more_docker_requirement.md`. Real hardware, not simulated.

## Source

- Repo: `feat/no-docker-implementation`
- Commit under test: `2b5643e` (`fix(entrypoint): install accel wheels via pip --prefix, not --target`
  — found and fixed live during this gate, see Findings)
- Test host: `docker-agent`, an unprivileged LXC container (VMID 117) on Proxmox host `nuc13`,
  built from the repo's Dockerfile (`persona-forge:local-xpu-fixed`), run via
  `docker compose -f docker-compose.yml -f docker-compose.persona-forge-gate9c-xpu.yml up -d persona-forge`

Unlike Gates 9A/9B (native `uv sync` + `persona-forge serve`), this gate validates the intended
end-user path for Linux with an accelerator: the Docker image, with `entrypoint.sh`'s first-boot
accel-family torch install (`persona_forge.gpu_family.resolve_gpu_family()` →
`persona_forge.accelerator_manifest.pin_for_family()`), not a source checkout.

## Host

- Hardware: Intel Iris Xe Graphics (integrated GPU, no discrete accelerator)
- OS: Debian GNU/Linux 13 (trixie), kernel `7.0.2-6-pve` (Proxmox), x86_64
- Container runtime: Docker inside an unprivileged LXC (VMID 117)
- Python (in-container): 3.13.15
- Torch: `2.13.0+xpu`, installed on first boot per `entrypoint.sh`'s accel-family logic from
  the `intel-xpu` manifest pin

## 1. Accel-family resolution + first-boot torch install

- `entrypoint.sh` resolved `_gpu_family=intel-xpu` and installed the manifest-pinned
  `torch==2.13.0+xpu` / `torchaudio` / `omnivoice==0.2.1` wheels into
  `/opt/accel-venv/intel-xpu` on first boot, writing the `.installed` marker
- Confirmed the marker persists across container recreation (cached-install path skipped on
  subsequent starts, per log line `intel-xpu: cached torch install found, skipping install`)

## 2. `torch.xpu` availability + device identification

Verified via `docker exec` (with `PYTHONPATH`/`LD_LIBRARY_PATH` manually re-exported from the
live process's `/proc/1/environ`, since `entrypoint.sh` only exports them within its own
process tree — a fresh `docker exec` shell does not inherit them):

```
torch: 2.13.0+xpu
xpu available: True
device count: 1
device name: Intel(R) Iris(R) Xe Graphics
has_fp64: False
```

Torch itself warns that Iris Xe is not officially supported (only Arc/Alchemist+ is) — expected,
non-blocking; the manifest pin still initializes and runs correctly on this hardware.

- fp32 tensor op on `xpu` device: passed (`[2.0, 4.0, 6.0]`)
- fp64 tensor op on `xpu` device: `RuntimeError: Required aspect fp64 is not supported on the
  device` — expected hardware/backend behavior (`has_fp64: False` is a genuine device property,
  not a bug); the NEO fp64-emulation env vars `entrypoint.sh` sets
  (`NEOReadDebugKeys`, `OverrideDefaultFP64Settings`, `IGC_EnableDPEmulation`) target
  OpenVINO's GPU plugin specifically and have no effect on torch's own XPU aspect check

## 3. App-level readiness + generation smoke

- `/health`: `status: "ok"`, `service_started: true`, `resolved_backend: "pocket_tts"`,
  `backend: "pocket_tts"`, `device: "xpu"`, `model_loaded: true`, `swap_in_progress: false`,
  `reconfig_in_progress: false`
- Generation smoke: `POST /generate` with `builtin_voice: "vera"`, `seed: 42`, three identical
  requests (same body used in the Gate 9A/9B receipts):
  - First request: HTTP 500 — the same builtin-voice-registration race already documented as a
    non-blocking finding in the Gate 9A (macOS) and Gate 9B (Windows) receipts; reproduced here
    identically, confirming it is backend/platform-independent
  - Second/third requests: HTTP 200, byte-identical SHA-256
    `3fbb4c622920e4b92c4a650b1cecd582da5f67975581577ad6c77e84672fc5fd`
  - App logs confirm real on-device generation: `RTF=0.34x` / `RTF=0.36x`, not a CPU fallback
  - This hash differs from the Gate 9A (macOS/CPU) and Gate 9B (Windows/CUDA) hashes — expected,
    since Pocket-TTS runs on a different device/backend per platform; determinism is verified
    *within* each platform (repeat requests match), not claimed *across* platforms

## Findings (bugs found and fixed live during this gate)

1. **`pip install --target` silently drops native runtime libraries (`scripts/entrypoint.sh`,
   commit `2b5643e`).** Some accel wheels (e.g. `intel-xpu`'s `intel-sycl-rt`) ship native `.so`
   files via install-scheme "data" entries with `../`-relative RECORD paths, meant to land at
   `<prefix>/lib/*.so*`. `pip install --target` has no destination for a path that resolves
   outside `site-packages` and silently drops those files — torch then imports fine at install
   time but crashes at runtime with `ImportError: libsycl.so.9: cannot open shared object file`.
   Only reproducible on real hardware with an accel family that ships such data-scheme files;
   never surfaced on CPU-only test paths. Fixed by switching to `pip install --prefix`, which
   places `data`-scheme files correctly, plus exporting `LD_LIBRARY_PATH="${_accel_prefix}/lib"`
   so the dynamic linker can find them at import time.

2. **`/dev/dri` inaccessible to the unprivileged LXC (host infra, not application code — see
   Infrastructure notes below).** Blocked all XPU access until fixed with a surgical
   `lxc.idmap` gid-split on the Proxmox host.

3. **Builtin-voice-registration race (not fixed, not blocking — see Gate 9A/9B receipts).**
   Reproduced identically here: the first `/generate` call immediately after
   `service_started: true` 500s; every subsequent identical request succeeds with a deterministic
   hash. Confirms this is a pre-existing, platform- and backend-independent readiness ordering
   gap.

## Infrastructure notes (host-level, not application code)

The real host's `/dev/dri/renderD128` and `/dev/dri/card0` are owned `root:video` / `root:render`
(group-only access, mode `crw-rw----`, no "other" bit). An unprivileged LXC's default uid/gid
mapping (`0 100000 65536`) never maps container-side access to real host gid 44/104, so `/dev/dri`
was invisible/inaccessible from inside the container regardless of file permissions on the
Docker/compose side.

Fixed with a narrow, additive `lxc.idmap` gid-split on `/etc/pve/lxc/117.conf` — mapping real
host gid 44 (`video`) and 104 (`render`) into two new, previously-unused container-side gids
(65536/65537), added to the existing base mapping without touching `unprivileged:` or the bulk
id-mapping range:

```
lxc.idmap: u 0 100000 65536
lxc.idmap: g 0 100000 65536
lxc.idmap: g 65536 44 1
lxc.idmap: g 65537 104 1
```

Paired with `group_add: ['65536', '65537']` on the `persona-forge` Docker service so its process
picks up the new supplementary groups. This approach was deliberately chosen over flipping the
container to privileged mode (attempted and reverted earlier in this same investigation — see
git history around this date on `docker-agent` host-config backups
`/etc/pve/lxc/117.conf.bak-pre-privileged` / `.bak-pre-idmap`) because it doesn't reinterpret file
ownership for the rest of the container's id space, only adds two precise 1:1 mappings.

Two unrelated, pre-existing latent bugs were also found and repaired on the host in the course of
recovering from the privileged-mode round-trip: several Docker containers' internal `mounts`
metadata directories had real host uid/gid `0` ownership (dated well before this session), and
the firecrawl stack's postgres/redis/rabbitmq bind-mounted data directories had raw/unshifted
real host uids throughout. Both predate this gate's work and are unrelated to persona-forge; both
were repaired via `nsenter`-based uid/gid correction from the real Proxmox host and verified clean
afterward.

## Not claimed

- This receipt validates Intel iGPU (Iris Xe) via `torch.xpu` specifically. It does not
  validate NVIDIA/AMD Docker+GPU paths (Gate 9B covers NVIDIA natively on Windows, not via
  Docker) or OpenVINO's own GPU plugin path independent of torch.
- fp64 workloads are not supported on this hardware/backend combination — any feature requiring
  fp64 precision on Intel XPU will fail here; this is a hardware/backend limitation, not
  something Phase 9 fixes or works around.
- Launcher archive smoke: out of scope, same reasoning as the Gate 9A/9B receipts
  (`release-launcher.yml` is `workflow_dispatch`-only).
