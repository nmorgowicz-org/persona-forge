# Gate 9B hardware receipt — Windows x86-64 + NVIDIA

Phase 9 of `docs/plans/20260829-no_more_docker_requirement.md`. Real hardware, not simulated.

## Source

- Repo: `feat/no-docker-implementation`
- Commit under test: `a8fff11` (fixes below were found and committed live during this gate)
- Working tree: clean at time of the final smoke run (`git status --short` — only untracked
  scratch/diagnostic files, no tracked-file changes)
- Test checkout: `D:\scripts\claude\persona-forge` on host `ryne`, fast-forwarded to `origin`

## Host

- Hardware: NVIDIA GeForce RTX 5090 (Blackwell, compute capability `(12, 0)` / sm_120)
- Driver: 616.56 (`nvidia-smi --query-gpu=driver_version`)
- OS: Microsoft Windows 11 Enterprise, 64-bit
- Python: 3.13.10
- uv: 0.12.3
- CUDA extra used: `cuda13` (index `cu130`) — required for Blackwell (sm_120 needs CUDA
  12.8+/13.x); confirmed correct both by the compute-capability requirement and by the host
  owner's direct confirmation of CUDA 13.3 being installed
- Accessed via `ssh nick@ryne`, commands run through `cmd /c "..."` (PowerShell's
  `$ErrorActionPreference` reports false failures for commands like `uv sync` that write
  informational progress to stderr — see Notes)

## 1. Locked sync + CLI install (source checkout)

- `uv sync --locked --extra cuda13` — exit 0
- `persona-forge doctor --json` — ran, valid JSON, no exceptions:
  - `accelerator.family: "cuda"`, `accelerator.device: "cuda"`, `accelerator.capable: true`
  - `dependencies.torch.runtime_device: "cuda"`
  - `backend.resolved: "pocket_tts"`, `ui.mode: "ui"`, `ui.dist_dir_present: true`

## 2. Torch/CUDA capability (recorded separately from the resolved backend device, per plan)

- `torch.__version__`: `2.14.0+cu130`
- `torchaudio.__version__`: `2.11.0+cu130`
- `torch.cuda.is_available()`: `True`
- `torch.cuda.get_device_name(0)`: `NVIDIA GeForce RTX 5090`
- `torch.cuda.get_device_capability(0)`: `(12, 0)`
- `torch.version.cuda`: `13.0`

## 3. Studio UI build (checkout `frontend/dist`)

- First attempt failed: `[build-ui] npm not found on PATH`, despite Node.js/npm genuinely
  installed and discoverable via `where npm` — root cause and fix in Findings below
  (commit `ae311a4`)
- After the fix: `npm ci` / `npm run check` / `npm run build` all ran and succeeded —
  `[build-ui] built D:\SCRIPTS\CLAUDE\persona-forge\frontend\dist`

## 4. Pocket-TTS semantic readiness + generation smoke (source checkout, `--extra cuda13`)

- First attempt failed outright: model load crashed with
  `ModuleNotFoundError: No module named 'fcntl'` — root cause and fix in Findings below
  (commit `adca692`)
- Second attempt failed differently: model loaded but the generated Pocket-TTS YAML config
  failed to parse (`yaml.scanner.ScannerError: ... found unknown escape character`) — root
  cause and fix in Findings below (commit `a8fff11`)
- Third attempt (commit `a8fff11`), clean `PERSONA_FORGE_HOME`, `persona-forge serve --port
  8320` via `Start-Process -PassThru` inside `try/finally`:
  - Readiness reached in well under the poll window: `status: "ok"`, `service_started: true`,
    `resolved_backend: "pocket_tts"`, `backend: "pocket_tts"`, `device: "cuda"`,
    `swap_in_progress: false`, `reconfig_in_progress: false`
  - Generation smoke: `POST /generate` with `builtin_voice: "vera"`, `seed: 42`, three
    identical requests:
    - First request: HTTP 500 — the same builtin-voice-registration race already documented
      as a non-blocking finding in the Gate 9A (macOS) receipt; reproduced here identically,
      confirming it is platform-independent, not a Windows-specific defect
    - Second/third requests: HTTP 200, byte-identical SHA-256
      `402a5baf3eb9f61a14c08eef05d61e9e8e95816ab1ee9c0bbc10db93f5322830`
  - Server process stopped cleanly in `finally` on every run (success and failure paths)

Note: this generation hash differs from the Gate 9A macOS hash
(`bd5c1c9f8e2227ce5a220fd1fa0f6774d8230e0463d24d5f1da04fa3543b99e1`) — expected, since
Pocket-TTS runs on CPU (float32) on macOS versus CUDA (float32) here; determinism is verified
*within* each platform (repeat requests match), not claimed *across* platforms.

## 5. Windows process-management pattern

Used PowerShell `Start-Process -PassThru` to launch `uv run persona-forge serve`, redirected
stdout/stderr to log files, polled `/health` in a loop, ran the generation smoke, and stopped
the process with `Stop-Process -Id $proc.Id -Force` inside a `finally` block so the server is
terminated on every path (readiness timeout, generation error, or success). Script retained at
`gate9b_smoke.ps1` (not committed — host-local scratch).

## Findings (bugs found and fixed live during this gate)

1. **npm spawn failure on Windows (`src/persona_forge/cli.py`, commit `ae311a4`).**
   `subprocess.run(["npm", ...])` without `shell=True` raises `FileNotFoundError` on Windows
   even when `npm` (actually `npm.CMD`) is on PATH, because `CreateProcess` doesn't resolve
   extensionless commands to `.cmd`/`.bat` shims the way a shell does. Fixed by resolving the
   executable via `shutil.which()` before invoking `subprocess.run`.

2. **`fcntl` import crash on Windows (`src/persona_forge/pocket_artifact_resolver.py`, commit
   `adca692`).** The artifact-download lockfile helper unconditionally imported the POSIX-only
   `fcntl` module, crashing Pocket-TTS model load with `ModuleNotFoundError` before any lock
   was even taken. Fixed with a platform branch: `msvcrt.locking` on Windows, `fcntl.flock`
   elsewhere.

3. **Invalid YAML from raw Windows paths (`src/persona_forge/pocket_english_config.py`, commit
   `a8fff11`).** The generated Pocket-TTS config embeds local artifact paths in double-quoted
   YAML scalars. A raw Windows path (`D:\scripts\...`) is invalid inside a YAML double-quoted
   string — backslash is an escape character there — so the config failed to parse on load.
   Fixed by converting backslashes to forward slashes before substitution (forward slashes are
   valid YAML and valid Windows file paths).

4. **Builtin-voice-registration race (not fixed, not blocking — see Gate 9A receipt).**
   Reproduced identically on Windows: the first `/generate` call immediately after
   `service_started: true` intermittently 500s; every subsequent identical request succeeds
   with a deterministic hash. Confirms this is a pre-existing, platform-independent readiness
   ordering gap, not something introduced by native Windows support.

## Not claimed

- Qwen3-TTS / OpenVINO are **not** supported on Windows by this project
  (`docs/plans/20260829-no_more_docker_architecture.md` line 47) — `persona-forge setup`
  correctly no-ops the Qwen compat-patch step on Windows (`_qwen_patch_setup`); this receipt
  makes no claim about Qwen/OpenVINO on this platform.
- Launcher archive smoke: out of scope, same reasoning as the Gate 9A receipt
  (`release-launcher.yml` is `workflow_dispatch`-only).

## Notes

- PowerShell's `$ErrorActionPreference` reports a non-zero pseudo-exit-code for commands (e.g.
  `uv sync`) that write informational progress to stderr but succeed; worked around by running
  remote commands through `cmd /c "... 2>&1"` and checking `%errorlevel%` explicitly.
- The host's prior checkout (a stale `main`-branch clone with an uncommitted, unrelated
  Puppeteer-path fix) was explicitly authorized by the project owner to be purged rather than
  preserved (`git stash clear` + hard reset to `origin/main`, then fresh checkout of this
  branch) — this host is validation-only, not a source of independently valuable work.
