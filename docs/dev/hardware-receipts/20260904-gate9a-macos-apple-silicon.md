# Gate 9A hardware receipt — macOS Apple Silicon

Phase 9 of `docs/plans/20260829-no_more_docker_requirement.md`. Real hardware, not simulated.

## Source

- Repo: `feat/no-docker-implementation`
- Commit under test: `96f94a8ab6c8718f0a90c8878ef6ee88ad32c5fe`
- Working tree: clean at time of test (verified `git status --short` before each run)
- Test checkout: temp clone at `/tmp/pf-gate9a/repo`, fast-forwarded to the commit above

## Host

- Hardware: Apple M5 Max (`sysctl -n machdep.cpu.brand_string`)
- OS: Darwin 25.5.0, arm64 (`uname -a`)
- Python: 3.13.14 (via `uv venv --python 3.13`); system `python3` is 3.14.6 (outside the
  package's `>=3.13,<3.14` bound — confirms the bound is load-bearing, not decorative)
- uv: 0.12.0 (Homebrew)

## 1. Locked sync + CLI install (source checkout)

- `uv sync --locked` — exit 0
- `persona-forge doctor --json` — ran, valid JSON, no exceptions
- `persona-forge setup` — ran against isolated `PERSONA_FORGE_HOME=/tmp/pf-gate9a/home`
  (**not** the real user app-data dir — see Notes)
- Packaged UI: doctor JSON `ui.mode: "ui"`, `ui.dist_dir_present: true`

## 2. Pocket-TTS semantic readiness + generation smoke (source checkout)

- Readiness: `service_started: true`, `resolved_backend: "pocket_tts"`, reached in ~22s cold
  (first run, model download+load)
- Generation smoke: `POST /generate` with `builtin_voice: "vera"`, `seed: 42`
  - Two identical requests → byte-identical SHA-256:
    `bd5c1c9f8e2227ce5a220fd1fa0f6774d8230e0463d24d5f1da04fa3543b99e1`
- Torch/MPS recorded **separately** from Pocket's actual device use:
  - Generic: `torch.backends.mps.is_available() == True`, `is_built() == True`
  - Pocket-TTS itself is CPU-only in code (`pocket_tts_runtime.py`: `audio.float().cpu()`) —
    the doctor JSON's `device: "mps"` field reflects generic torch capability, **not** what
    Pocket-TTS used for this generation. Do not read this receipt as "Pocket used MPS."

## 3. Wheel target-native doctor/serve smoke

- Built via `uv build` at commit `96f94a8` →
  - `persona_forge-1.3.0-py3-none-any.whl`
    SHA-256 `276bb98c84a7f5d484ea515006fa7d1039c44ae37d3de07a5dd48539a4684f6c`
  - `persona_forge-1.3.0.tar.gz`
    SHA-256 `1f07cef25dd69e03295b9822e73dc32a84f6d426eb8f926f32b4cbcfdc7d6792`
- Installed into a fresh, isolated venv (`uv venv --python 3.13`, `uv pip install`) — no
  source checkout involved for this leg
- `persona-forge doctor --json` (`PERSONA_FORGE_HOME=/tmp/pf-gate9a/wheel-home`): passed,
  `ui.mode: "ui"`, `ui.dist_dir_present: true`, `backend.resolved: "pocket_tts"`
- `persona-forge serve --port 8319`: reached semantic readiness via
  `scripts/wait_for_readiness.py` in 5.2s (warm — model artifacts already cached from step 2)
  - `status: "ok"`, `service_started: true`, `resolved_backend: "pocket_tts"`
- Generation smoke (`builtin_voice: "vera"`, `seed: 42`) x3 against the wheel install:
  - First request: HTTP 500 — `[pocket_tts] voice_id 'vera' not found in voice_library`
  - Second/third requests: HTTP 200, byte-identical SHA-256
    `bd5c1c9f8e2227ce5a220fd1fa0f6774d8230e0463d24d5f1da04fa3543b99e1` — **matches step 2's
    hash**, confirming determinism holds across the source-checkout and wheel builds
  - Reproduced identically on a second install/serve cycle after the `.config` path-parity
    change landed (see Notes) — same 500-then-200 pattern, same final hash
- Process terminated cleanly (`pkill` + confirmed `/health` unreachable afterward) on every run

## 4. Launcher archive smoke

**Not exercised this pass.** `release-launcher.yml` is `workflow_dispatch`-only (not triggered
on every push/tag), so launcher archives are not part of this branch's default release surface.
The wheel leg above already proves package-native operation independent of the source checkout.
If launcher archives are dispatched for an actual release, they need their own smoke pass before
that release ships — this receipt does not cover them.

## Findings

- **Builtin-voice-registration race on first request after readiness:** the very first
  `/generate` call immediately after `service_started: true` intermittently 500s with
  `voice_id 'vera' not found in voice_library`, even though the log shows the request already
  resolved to `voice_id='pocket:vera'`. All subsequent identical requests succeed. Reproduced
  on both the source-checkout and wheel-installed runs. Not a wheel/native-packaging defect —
  it's a pre-existing readiness/voice-registry ordering gap: `service_started` doesn't
  guarantee the builtin voice table has finished populating. Not fixed here (out of Phase 9's
  scope); flagged for a follow-up, not blocking this gate since the readiness contract as
  written only requires `service_started` + backend match.

## Notes

- Mid-run, `~/Library/Application Support/persona-forge` (macOS app-data root) was changed to
  `~/.config/persona-forge` for cross-platform parity with Linux/Windows (commit `96f94a8`,
  separate from the readiness-harness commit `085425d`). All doctor/serve smokes in this
  receipt after that point used `PERSONA_FORGE_HOME` overrides, not the real default, so the
  change itself was verified separately via the pure `paths.app_data_root()` resolver
  (`/Users/nick/.config/persona-forge`, no filesystem I/O) rather than by touching the real
  home directory.
- An earlier, corrected mistake: a first, unscoped `persona-forge setup` call (before adopting
  `PERSONA_FORGE_HOME` overrides throughout) created empty directories under the real
  `/Users/nick/Library/Application Support/persona-forge/`. Verified empty (no data loss) and
  removed before any further steps. All Gate 9A work after that point used isolated homes
  under `/tmp/pf-gate9a/`.
