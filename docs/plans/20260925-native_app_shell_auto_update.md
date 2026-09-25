# Persona Forge Desktop — Execution Plan

Status: **draft. The owner reviews it together with the architecture contract before Phase 0.**

**Architecture contract (binding):** `docs/plans/20260925-native_app_shell_architecture.md`.
Every decision ID (`D1`…`D19`) and section reference (`§6.2` etc.) below points into that doc.
If this plan and the contract disagree, the contract wins. **Stop and report**; do not pick one
yourself.

**Baseline:** `1e2f520` on branch `plan/native-app-shell-auto-update`.

This plan is written so that a Sonnet-class implementer can run one phase per fresh context.
Each phase lists:

- what to read
- which files to touch
- the exact interfaces
- tests to write first
- a fail-closed gate
- stop conditions

Items marked **OWNER** need a human: credentials, physical machines, runner installs, or product
decisions. An implementer must never simulate them.

---

## Worker protocol (mandatory, every phase, every fresh context)

1. Read this section, the phase you are running, and every file in the phase's "Read first"
   list, **completely**. Always read the architecture contract §2 (Decisions) and the sections
   the phase cites.
2. Work on a branch named `desktop/pN-<slug>` cut from `main` after the previous phase's PR has
   merged. Use one PR per phase. Phase 1 is a spike: its code is never merged (see Phase 1).
3. **Do not invent APIs.** Before you use any Tauri, plugin, `process-wrap`, or Sparkle API, check
   it against the docs for the *exact pinned version* (docs.rs for crates, `v2.tauri.app` for
   Tauri, or the Context7 MCP). If the API differs from what this plan says, follow the real API,
   keep the behavior this plan specifies, and record the difference in the PR description.
   - If the behavior itself is impossible, **stop and report**.
4. Gates are fail-closed. Never do any of these:
   - `| tail` or `| head` away failures
   - `2>/dev/null` on a gate command
   - `|| true`
   - `continue-on-error: true`
   - weaken a test to make it pass
   - turn a hardware or signing check into prose

   Paste real command output (or a CI run URL) into the PR description for every gate line.
5. Stop conditions are hard. When one triggers, commit nothing further. Write down what you ran,
   what you saw, and which stop condition fired, and hand back to the owner.
6. Never touch `main` directly, and never force-push shared branches. Do not run `git push`
   unless the phase says to open a PR. Do not create or edit GitHub secrets. Do not install
   software on self-hosted runners. The only infrastructure changes allowed are those in
   **Phase 0R**, a paired session run with the owner present, under its own rules.
7. Repository rules from `AGENTS.md` apply:
   - Conventional Commit PR titles
   - a `BEGIN_COMMIT_OVERRIDE` block in every PR body
   - no model weights, audio, keys, or IR in Git
   - `python scripts/validate_repo.py` and `git diff --check` before every PR
8. Scope discipline: implement exactly the phase's task list. Anything else you notice goes into
   the PR description under "Follow-ups". Do not fix it.

## Owner actions (blocking prerequisites)

| ID | Action | Blocks |
| --- | --- | --- |
| OA-1 | Approve the architecture contract (all D-decisions), or amend it. | Phase 0 |
| OA-2 | Done 2026-09-25: product identity D16 confirmed; icon source is the Signal Crucible concept pack (contract D16). Remaining: review the rendered Dock icon on macOS 26 in Phase 4. | Phase 4 (review only) |
| OA-3 | Generate the Tauri updater key and add its GitHub secrets, following **Appendix A, steps A2 and A4**. Give the implementer the **public** key. | Phase 1 |
| OA-4 | Generate the Sparkle key and add its GitHub secret, following **Appendix A, steps A3 and A4**. Give the implementer the **public** key. | Phase 1 |
| OA-5 | Be present for **Phase 0R** (runner infrastructure, driven by the agent over `ssh nick@arc-runner`). Approve each mutating step when asked, and merge the `../llama-monitor-runner` PRs. | Gate 0 Linux job; Phases 1A (signing), 1C, 2 (CI lane), 3, 4, 5, 6 |
| OA-6 | On `self-hosted-macos`: make sure Xcode Command Line Tools and rustup are present, plus 10 GB of free disk. On `self-hosted-windows`: Visual Studio 2022 Build Tools ("Desktop development with C++", Windows 11 SDK) and rustup. Use the Phase 0 preflight output to see what is missing. | Phase 1A/1B |
| OA-7 | Manual test machines (owner, 2026-09-25): the Mac on macOS 26 (Tahoe), and the Windows 11 PC (record its Smart App Control state once: Windows Security → App & browser control → Smart App Control). No Linux desktop exists, so every Linux gate is automated (contract D8). Optional: a Debian 13 LXC for a headless `--smoke-test` of the AppImage; a macOS 14 VM (for example with Tart on the Mac) for the minimum-OS check. | Phases 1A/1B/1D, 3, 5, 6, 8 |
| OA-8 | Create, and afterwards delete, the test **pre-releases** (never marked latest): `desktop-spike`, `desktop-spike-badsig` (Phase 1), `desktop-updater-test`, `desktop-updater-badsig` (Phase 6B). The implementer asks when each is needed. | Phases 1, 6B |

---

## Common verification commands

Run from the repo root:

```bash
# Repo hygiene (every phase)
python scripts/validate_repo.py
git diff --check

# Rust (Phases 2+)
cargo fmt --manifest-path launcher/Cargo.toml --check
cargo clippy --manifest-path launcher/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path launcher/Cargo.toml

# Desktop crate (Phases 3+; needs the payload staged, see Phase 3 "Local dev loop")
cargo fmt --manifest-path desktop/Cargo.toml --check
cargo clippy --manifest-path desktop/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path desktop/Cargo.toml

# Python tier 1 (Phases 3+, 4+, 6+, 7)
PYTHONPATH=src:src/export uv run --frozen python -m pytest tests/tier1_unit -q

# Frontend (Phase 3 only; the banner change)
npm run --prefix frontend check
```

---

## Phase 0 — Baseline, inventory, and runner requests

### Objective

Record facts before any code exists: runner reality, toolchains and secrets. Land the workflow
stubs that later phases need (contract §5, "Workflow bootstrap rule"). No product code.

### Read first

- Architecture contract §2, §8, §11, §12.
- `.github/workflows/release-launcher.yml`, `.github/workflows/ci-packaging.yml`.
- `../llama-monitor-runner/Dockerfile`, `../llama-monitor-runner/deploy/*.yaml`,
  `../llama-monitor-runner/docs/arc-runners-for-other-repos.md`.

### Tasks

1. Branch `desktop/p0-baseline`.
2. Add `scripts/desktop_preflight.sh <macos|windows|linux>`, in bash, runnable in Git Bash on
   Windows. It checks **every** tool, prints its version or one `MISSING: <tool>` line, and exits
   1 at the end if anything was missing (so one run yields the complete list):
   - all: `rustc`, `cargo`, `rustup target list --installed`, `python3 --version`, `uv --version`
     (warn only)
   - macos: `xcode-select -p`, `hdiutil`, `codesign`, `spctl`, `xcrun stapler`, free disk ≥ 10 GB
     on `$RUNNER_TEMP` (`df -g`)
   - windows: `cl.exe` reachable through `vswhere` (`"C:/Program Files (x86)/Microsoft Visual
     Studio/Installer/vswhere.exe" -latest -products '*' -requires
     Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath` must be
     non-empty), a Windows SDK directory under `C:/Program Files (x86)/Windows Kits/10/Include`,
     and the WebView2 runtime registry key
     `HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}`
     (or the HKCU equivalent)
   - linux: `ldd --version` (the first line must show glibc ≤ 2.35), `pkg-config --modversion
     webkit2gtk-4.1 gtk+-3.0 ayatana-appindicator3-0.1 gstreamer-1.0`, `patchelf`, `xvfb-run`,
     `WebKitWebDriver`, `tauri-driver`, `rcodesign --version`, and `openssl version` starting with
     `OpenSSL 3`
3. Add `.github/workflows/desktop-preflight.yml` (`workflow_dispatch` only, no secrets) with four
   jobs:
   - `self-hosted-macos`: runs `desktop_preflight.sh macos` and prints `sw_vers`
   - `self-hosted-windows`: runs it in `shell: bash`, then the PowerShell OS probe
   - `arc-persona-forge-desktop`: runs `desktop_preflight.sh linux`. It stays queued until Phase
     0R has created the runner; that is expected.
   - `runner-label-probe` on `arc-llama-monitor`: `uname -a`, `cat /etc/os-release`,
     `ldd --version | sed -n 1p`. It confirms the shared runner's OS (Ubuntu 26.04 expected),
     which Phase 4 uses as the "newest distro" headless smoke target.
4. Add workflow **stubs** (contract §5 bootstrap rule) for `desktop-build.yml`,
   `desktop-update-e2e.yml` and `desktop-spike.yml`: each has `on: workflow_dispatch` with the
   exact inputs its phase defines (listed below), `permissions: contents: read`, and one job on
   `arc-general` that runs `echo "stub: implemented in a later phase"; exit 1`.
   - `desktop-build.yml`: `version` (string, required), `sign` (boolean, default false),
     `feed_base` (string, default ""), `ci_hooks` (boolean, default false), `wheel_artifact`
     (string, default "")
   - `desktop-update-e2e.yml`: `n_run_id` (string), `n1_run_id` (string), `mode` (choice:
     `good`, `badsig`)
   - `desktop-spike.yml`: `version` (string, required)
5. Open PR 1 with tasks 2–4 only; the owner merges it. GitHub can then dispatch these workflows,
   and later phases run their branch versions with `--ref`.
6. Record secret **presence** and **scope**, without values: `gh secret list` and `gh secret list
   --org nmorgowicz-org`. Confirm the `MACOS_*`/`APPLE_*` secrets are org secrets visible to this
   repo. A permission error is recorded as-is.
7. Runner infrastructure is **not** part of this task list. It is Phase 0R, below.
8. On a second branch, append a `## Phase 0 results` section at the end of this doc containing:
   the preflight output per runner (a CI run URL plus the key lines), the label-probe result,
   the secret presence and scope table, and the list of OA items still open. Open it as PR 2.

### Gate 0

```bash
bash -n scripts/desktop_preflight.sh
python scripts/validate_repo.py
git diff --check
gh workflow run desktop-preflight.yml --ref main   # after PR 1 is merged
gh run watch <run-id>
```

Pass: the macOS and Windows preflight jobs are green, **or** they fail with a precise list of
missing tools (that list becomes OA-6). The Linux job is green once Phase 0R has run; until then
cancel the run after the other jobs finish. `runner-label-probe` output is recorded. The three
stubs appear in `gh workflow list`.

### Stop conditions

- `self-hosted-macos` is not Apple Silicon, or runs macOS < 14. Report this. D6 assumes an arm64
  build host.
- `runner-label-probe` never gets a runner. Record it and continue; this does not block the
  desktop work.

PR 1 title: `ci(desktop): add desktop toolchain preflight and workflow stubs`. PR 2 title:
`docs(plan): record desktop Phase 0 results`.

---

## Phase 0R — Runner infrastructure, paired session (agent drives, owner present)

### Objective

Carry out contract §11 items 1–4 in `../llama-monitor-runner` and on the k3s cluster: a new
Ubuntu 22.04 runner image and an org-scoped `arc-persona-forge-desktop` scale set, the stale
`arc-llama-monitor` values file fixed, and the abandoned `arc-persona-forge-release` removed.
The owner asked for this to be done together (2026-09-25): the agent drives, the owner watches
and approves.

### Session rules (read before anything else)

1. **Read-only commands run freely** (`helm list`, `helm get values`, `kubectl get`,
   `kubectl describe`, `kubectl logs`, `git diff`).
2. **Every mutating command is shown to the owner first, with what it does and how to undo it,
   and runs only after the owner says yes in chat.** Mutating means: `helm install`, `upgrade`
   or `uninstall`; any `kubectl` `apply`, `delete`, `patch`, `scale` or `edit`; `git push`;
   `gh workflow run`; `gh pr create`.
3. Only these Helm releases may be changed: `arc-persona-forge-desktop` (new) and
   `arc-persona-forge-release` (removal). Never touch the controller `arc` in `arc-systems`, or
   `arc-general`, `arc-general-docker`, `arc-llama-monitor`, `arc-llama-monitor-fast`.
4. Anything unexpected (a release not in contract §11's table, a failing listener, a pod in
   `CrashLoopBackOff`): stop, show the output, and decide with the owner.
5. Cluster access is `ssh nick@arc-runner`, which has `helm` and `kubectl` (no `docker`).
   Values files are copied there with `scp` into `~/` before `helm` runs. That is where the
   existing `arc-llama-monitor-values.yaml` already lives.

### Read first

- Contract §11 in full, including the inspected cluster table.
- `../llama-monitor-runner/Dockerfile`, `.github/workflows/runner-image.yml`,
  `deploy/arc-general-values.yaml`, `deploy/arc-llama-monitor-values.yaml`,
  `docs/arc-runners-for-other-repos.md`.

### Steps

R0. **Pre-check (read-only).**

```bash
ssh nick@arc-runner 'helm list -A; kubectl get autoscalingrunnersets -n arc-runners; kubectl get pods -n arc-systems'
grep -rn "arc-persona-forge-release" .github/     # in persona-forge; must print nothing
ssh nick@arc-runner 'helm get values arc-persona-forge-release -n arc-runners' > /tmp/arc-persona-forge-release.values.backup.yaml
```

Confirm the chart version the others use (`gha-runner-scale-set-0.14.2` on 2026-09-25). Keep the
backup file as a record; it is not a working undo on its own (contract §11 item 4).

R1. **Runner repo branch** `feat/persona-forge-desktop-runner` in `../llama-monitor-runner`:

- `desktop-linux/Dockerfile` per contract §11 item 2: base `ubuntu:22.04@sha256:<digest>`
  (resolve with `docker buildx imagetools inspect ubuntu:22.04` on the Mac); the apt packages
  listed there (including `rcodesign`, same version as `release-launcher.yml`); rustup
  `RUST_VERSION=1.98`; `cargo install tauri-cli --version <pinned> --locked` and `cargo install
  tauri-driver --version <pinned> --locked` (latest `2.x` of each; **record the exact versions in `## Phase 0 results` — Phase 1 pins the
  spike, and Phase 3 pins the real crates, to what Phase 0R/1 used**); uv `0.12.9`; the
  actions runner at the existing Dockerfile's `RUNNER_VERSION`; `ENV
  APPIMAGE_EXTRACT_AND_RUN=1`; a non-root `runner` user with the existing image's UID/GID.
- `.github/workflows/desktop-linux-runner-image.yml`, modeled on `runner-image.yml` but with
  only two triggers, push on its own paths and `workflow_dispatch`: **no** weekly schedule and
  **no** package-cleanup job (contract §11 item 2). It builds and pushes
  `ghcr.io/nmorgowicz-org/persona-forge-desktop-linux-runner`, amd64 only, tagged with the git
  SHA.
- `deploy/arc-persona-forge-desktop-values.yaml` per contract §11 item 3, image
  `...@sha256:TBD` for now.
- `deploy/arc-llama-monitor-values.yaml`: set `githubConfigUrl` to
  `"https://github.com/nmorgowicz-org"` to match the deployed release (contract §11 item 1). No
  redeploy.
- Delete `deploy/arc-persona-forge-release-values.yaml`.
- `docs/arc-runners-for-other-repos.md`: fix the `arc-llama-monitor` row (org-scoped), add a row
  and an install section for `arc-persona-forge-desktop`, remove any mention of
  `arc-persona-forge-release`.

Show the owner `git diff --stat` and the full diff of the values files. **Checkpoint:** push the
branch and open a PR (owner approves); the owner merges it.

R2. **Build the image.** Merging triggers the new workflow. Watch it with `gh run watch -R
nmorgowicz-org/llama-monitor-runner`. Record the pushed digest (from the workflow log, or
`docker buildx imagetools inspect ghcr.io/nmorgowicz-org/persona-forge-desktop-linux-runner:latest`).
Put the digest into the values file in a small follow-up PR (**checkpoint**: owner merges).

R3. **Install the scale set.** **Checkpoint**, then:

```bash
scp deploy/arc-persona-forge-desktop-values.yaml nick@arc-runner:~/
ssh nick@arc-runner 'helm upgrade --install arc-persona-forge-desktop \
  --namespace arc-runners \
  -f ~/arc-persona-forge-desktop-values.yaml \
  --version 0.14.2 \
  oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set'
```

Undo: `helm uninstall arc-persona-forge-desktop -n arc-runners`.
Verify (read-only): the new set appears in `kubectl get autoscalingrunnersets -n arc-runners`,
its listener pod is `Running` in `arc-systems`, and the listener log shows no auth error
(`kubectl logs -n arc-systems <listener-pod> --tail=50`).

R4. **Prove it runs jobs.** **Checkpoint**, then run the Phase 0 `desktop-preflight.yml` workflow
(or only its Linux job). The Linux job must be green: glibc ≤ 2.35, all packages found. A runner
pod appears in `arc-runners` during the job and is removed afterwards.

R5. **Confirm the old set is idle.** `gh run list --limit 50 --json databaseId,name` shows no
job on `arc-persona-forge-release`, and R0's grep was empty.

R6. **Remove the abandoned set.** **Checkpoint**, then:

```bash
ssh nick@arc-runner 'helm uninstall arc-persona-forge-release -n arc-runners'
```

Undo: the old image digest no longer exists in GHCR. If the owner ever wants it back, edit the
R0 backup values to use `ghcr.io/nmorgowicz-org/llama-monitor-runner:latest`, then `helm install
arc-persona-forge-release --namespace arc-runners -f <edited backup> --version 0.14.2
oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set`.
Verify: it is gone from `helm list -A` and `kubectl get autoscalingrunnersets -n arc-runners`,
and its listener pod is gone from `arc-systems`. Every other release is unchanged (compare with
R0's output).

R7. Append the session log (every command, its output summary, and the owner approvals) to
`## Phase 0 results`.

### Gate 0R

- `helm list -A` shows `arc-persona-forge-desktop` deployed and no `arc-persona-forge-release`;
  every other release has the same revision as in R0.
- The Linux preflight job ran green on `arc-persona-forge-desktop` (run URL recorded).
- The runner repo `main` contains the Dockerfile, image workflow, both values-file changes, the
  deletion, and the docs update.

**Stop conditions:** the listener cannot authenticate; the runner pod cannot pull the image
(check `ghcr-pull-secret` and the package's visibility); the Linux preflight fails for anything
other than a missing package that R1 can add.

---

## Phase 1 — Spike: prove the four risky integrations

### Objective

Answer, with real runs, the unknowns the contract marks for Phase 1. **Nothing from the spike
merges** except the results write-up and any corrections to the contract. The spike code lives on
branch `spike/desktop` under `spike/desktop-shell/`, and its real workflow replaces the Phase 0
stub **on that branch only**. Every spike run is `gh workflow run desktop-spike.yml --ref
spike/desktop -f version=<v>`.

Sub-phases 1A–1D are independent. They can run in parallel contexts once their prerequisites are
met. All jobs follow D19: secrets only on `arc-persona-forge-desktop` or `arc-general`, never on
`self-hosted-macos` or `self-hosted-windows`.

### Read first

- Contract §6.4, §6.5, §7, §8, §9, §10, §14.
- `docs/archive/macos-code-signing/20260918-macos_code_signing.md` (the rcodesign flow already in
  use).
- Tauri docs: "Create a project" (manual Cargo setup, no npm), "Sidecar", "Resources",
  "Updater", "macOS Application Bundle", "Windows Installer", "AppImage", "WebDriver" (testing
  with `tauri-driver`).
- The `ahonn/tauri-plugin-sparkle-updater` README and example, at the pinned version.
- Sparkle "Publishing an update" and "Sandboxing" (XPC re-signing) docs.

### Spike app (shared by 1A–1D)

A minimal Tauri v2 app at `spike/desktop-shell/`:

- Built with `cargo tauri`. No npm. `frontendDist` = `spike/desktop-shell/splash/` (static HTML).
- The main window starts on the splash. A button navigates to `http://127.0.0.1:8318/`.
- `on_navigation` applies the **real** contract §6.5 `classify` rule (a copy of the pure
  function) and logs every decision, so the spike shows whether the rule itself breaks blob
  downloads. `on_download` shows a Save dialog (`tauri-plugin-dialog`).
- It has the predefined Edit menu.
- It includes `tauri-plugin-updater` (Windows/Linux) or `tauri-plugin-sparkle-updater` (macOS),
  with a "Check for Updates" menu item.
- The feed base URL comes from the build-time env var `SPIKE_FEED_BASE` (read with
  `option_env!`), default
  `https://github.com/nmorgowicz-org/persona-forge/releases/download/desktop-spike`. The badsig
  builds set it to `.../releases/download/desktop-spike-badsig`. Both are **pre-releases** the
  owner creates (OA-8), never marked latest.
- It embeds a 10 MB dummy resource file (random bytes generated at build time, not committed).
  This makes bundle replacement non-trivial.
- Versions: `0.1.0` (N) and `0.1.1` (N+1).
- Spike-only arguments `--version` (prints the version and exits, no window) and `--ci-update
  <out.json>` with the behavior of contract §6.12 (Windows and Linux only). They exist so 1C can
  test updates without a human; `--ci-update` is the prototype for the real `ci-hooks` feature
  in Phase 6A.

The test page is `spike/desktop-shell/testpage/index.html`, served by
`python3 -m http.server 8318 --bind 127.0.0.1 --directory spike/desktop-shell/testpage`. It
contains:

1. two `<a download="tone.wav">` links: `#dl-blob` with `href=blob:…` (a WAV generated in JS —
   a 1 s sine wave through `OfflineAudioContext`, encoded to WAV in JS) and `#dl-http` with
   `href="tone.wav"` (the same WAV served next to the page; a same-origin URL download, which is
   the shape `AudioDeck.tsx` actually uses — contract §6.5)
2. an `<audio>` element playing the same blob
3. `<a target="_blank" href="https://example.com">`
4. `window.open('https://example.com')`
5. `<input type=file>`
6. a `<textarea>` for Cmd/Ctrl+C/V/Z/A
7. a `localStorage` counter that increments on each load
8. `<a href="https://example.com">` (same-window navigation)
9. two `<audio>` elements with fixed ids: `#wav` (the blob from item 1) and `#mp3` (`tone.mp3`
   served next to the page; generated at test time with `ffmpeg -f lavfi -i
   sine=frequency=440:duration=1 tone.mp3`, never committed)

MP3 playback is also tested with the real app in 1D. No audio files are committed.

### 1A — macOS: bundle, sign/notarize/staple on Linux, DMG, Sparkle update

Tasks:

1. `desktop-spike.yml` macOS jobs, in this order, passing files as workflow artifacts (zip
   `.app` bundles with `ditto -c -k --keepParent` so symlinks survive):
   - `spike-macos-build` on `self-hosted-macos`, **no secrets**: `cargo tauri build --no-sign
     --bundles app --target aarch64-apple-darwin --config '{"version":"<version>"}'`.
   - `spike-macos-sign-app` on `arc-persona-forge-desktop`, with the Apple secrets (the same
     key/cert/API-key steps as `release-launcher.yml`, files in `$RUNNER_TEMP`, removed in an
     `if: always()` step): `rcodesign sign --pem-file … --pem-file … --for-notarization
     --entitlements-xml-file spike/desktop-shell/entitlements.plist "<App>.app"`, then
     `rcodesign notary-submit --api-key-file … --staple "<App>.app"`.
   - `spike-macos-dmg` on `self-hosted-macos`, no secrets: a staging dir holding the signed
     `.app` and an `Applications -> /Applications` symlink, then `hdiutil create -volname
     "Persona Forge" -srcfolder <staging> -ov -format UDZO <dmg>`.
   - `spike-macos-sign-dmg` on `arc-persona-forge-desktop`, Apple secrets: `rcodesign sign`, then
     `notary-submit --staple` the DMG.
   - `spike-macos-verify` on `self-hosted-macos`, no secrets: `xcrun stapler validate` on the
     `.app` and the DMG, `codesign --verify --deep --strict --verbose=2` and `spctl --assess
     --type execute --verbose=4` on the `.app`, `spctl --assess --type open --context
     context:primary-signature --verbose=4` on the DMG. Only these checks count as proof of
     stapling (rcodesign #169 can exit 0 without stapling).
   - `spike-sparkle-sig` on `arc-general`, with `SPARKLE_ED_PRIVATE_KEY`: the OpenSSL 3 recipe
     from contract §9.2 (`openssl pkeyutl -sign -rawin`), output the base64 signature and the DMG
     length.
2. Run it with `version=0.1.0` and `version=0.1.1`. Upload `0.1.1`'s DMG to the `desktop-spike`
   pre-release, together with a hand-written `appcast.xml` (the Sparkle 2 format from contract
   §9.1) carrying `0.1.1`'s edSignature and length.
3. **OWNER** on the Mac (macOS 26): download `0.1.0`'s DMG through a browser, so it is
   quarantined.
   - Disconnect the network, open the DMG, drag the app to Applications, launch it. Expected: no
     Gatekeeper prompt beyond the standard "downloaded from the Internet" confirmation, and no
     network-check failure. This proves the staple.
   - Reconnect, then Check for Updates. Expected: Sparkle offers 0.1.1, installs it after the
     app quits, relaunches at 0.1.1, and the app stays responsive while downloading. Record how
     long it takes from clicking Install to relaunch.
   - Launch `0.1.0` straight from the mounted DMG or from `~/Downloads` (translocated) and Check
     for Updates. Record what Sparkle shows.

Pass criteria (every one required):

- the `.app` and the DMG both pass `stapler validate`, `codesign --verify --deep --strict` and
  `spctl` on the runner
- the offline first launch works
- the Sparkle update installs and relaunches
- `Sparkle.framework`'s XPC services are signed with our Team ID (`codesign -dv --verbose=4` on
  each `.xpc` and on `Autoupdate`)

**Stop conditions:**

- rcodesign on Linux cannot produce a notarization-accepted signature for the bundle with
  Sparkle inside (the notary log, from `rcodesign notary-log`, shows errors on the Sparkle
  helpers). Try once with a `--code-signature-flags runtime` scope on the nested helpers. If it
  still fails, stop and report. The fallback (signing on a Mac) conflicts with D19 and needs an
  owner decision.
- `tauri-plugin-sparkle-updater` does not build against the pinned Tauri 2.x.

### 1B — Windows: NSIS per-user build and Tauri updater

Tasks:

1. `desktop-spike.yml` Windows jobs:
   - `spike-windows-build` on `self-hosted-windows`, **no secrets**, a matrix of N (`0.1.0`,
     feed `desktop-spike`) and N+1 (`0.1.1`): `cargo tauri build --bundles nsis --target
     x86_64-pc-windows-msvc --config
     '{"version":"<v>","bundle":{"createUpdaterArtifacts":false}}'` with
     `windows.nsis.installMode: "currentUser"` and `windows.webviewInstallMode.type:
     "embedBootstrapper"`. Upload each `*-setup.exe`.
   - `spike-updater-sigs` on `arc-persona-forge-desktop`, with the Tauri signing secrets: `cargo
     tauri signer sign` on N+1's setup exe and N+1's AppImage (1C), producing `.sig` files.
2. Publishing is done once for both OSes by `spike-linux-publish` (1C task 3), which writes one
   `latest.json` with both keys, `windows-x86_64-nsis` and `linux-x86_64-appimage`.
3. **OWNER** on the Windows 11 PC:
   - install `0.1.0` by downloading it in Edge. Record the SmartScreen dialog text and whether
     Smart App Control blocked it (record the SAC state: On, Evaluation or Off).
   - Check for Updates, then install. Record whether the passive NSIS UI appears, whether the app
     relaunches at 0.1.1, and whether SmartScreen or SAC intervened on the update.
4. Automated on `self-hosted-windows` (no secrets needed): silent-install `0.1.0` (`/S`), run it
   with `--ci-update out.json` through `Start-Process -Wait -PassThru` (a GUI-subsystem exe does
   not block PowerShell otherwise). Expect `out.json` to say `"phase": "installing"` (contract
   §6.12: Tauri exits the app during a Windows install). Then poll
   `HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*` (the entry whose `DisplayName`
   is the spike's product name) until `DisplayVersion` is `0.1.1`, for at most 120 s, failing
   closed. Stop any app instance the installer relaunched and uninstall in `finally`. (The
   registry `DisplayVersion` is the version check; a GUI-subsystem exe prints nothing.)

Pass: task 4 passes, and the owner's GUI update in task 3 installs and relaunches. SmartScreen
warnings are **recorded**, not a failure (D7). If Smart App Control is **On** and blocks the
install outright, record it; task 4 is then the pass evidence.

**Stop condition:** the MSVC build fails on the runner for a toolchain reason that OA-6 cannot
fix.

### 1C — Linux: AppImage build, automated update and GUI checks (on `arc-persona-forge-desktop`, needs OA-5)

No human tests Linux (contract D8), so this sub-phase is fully automated. All GUI steps run under
`xvfb-run -a` with a D-Bus session (`dbus-run-session`).

Tasks:

The Windows and Linux matrices always build both `0.1.0` and `0.1.1` in one dispatch; the
`version` input only drives the macOS jobs (1A runs twice). Because the feed base is compiled in,
the Linux update test needs two builds of N. The Linux jobs, in order:

1. `spike-linux-build` (matrix of three builds, **no secrets**): N good (`0.1.0`,
   `SPIKE_FEED_BASE` = `desktop-spike`), N badsig (`0.1.0`, `SPIKE_FEED_BASE` =
   `desktop-spike-badsig`), and N+1 (`0.1.1`). Each: `cargo tauri build --bundles appimage
   --config '{"version":"<v>","bundle":{"createUpdaterArtifacts":false,"linux":{"appimage":{"bundleMediaFramework":true}}}}'`,
   then `objdump -T <binary> | grep -o 'GLIBC_[0-9.]*' | sort -Vu | tail -1` must be ≤
   `GLIBC_2.35`.
2. `spike-updater-sigs` (secrets, 1B): signs N+1's AppImage and setup exe.
3. `spike-linux-publish` on `arc-general` (job `permissions: contents: write`, `GH_TOKEN: ${{
   github.token }}`): uploads N+1's AppImage and setup exe, their `.sig` files, and one
   `latest.json` (keys `linux-x86_64-appimage` and `windows-x86_64-nsis`) to `desktop-spike` with
   `gh release upload --clobber`. Then it copies N+1's AppImage, flips one byte, and uploads that
   copy with a `latest.json` carrying the **original** signature to `desktop-spike-badsig`.
4. `spike-linux-update`: run N good with `--ci-update out.json`. Assert `ok: true`,
   `to_version: "0.1.1"`, and that the AppImage file on disk now prints `0.1.1` for `--version`.
   Then run N badsig with `--ci-update`. Assert `ok: false`, a signature error, and that its file
   still prints `0.1.0`.
5. `spike-linux-gui`: start `tauri-driver` and the test page server, then drive N good's
   AppImage with a small Python WebDriver script (Selenium, `uv run --with selenium`; follow the
   Tauri WebDriver docs for the capability that names the application path). Checks:
   - after clicking the splash button, the current URL is `http://127.0.0.1:8318/`
   - clicking the same-window external link leaves the URL unchanged
   - `#wav` and `#mp3`: `play()` resolves and `currentTime` advances past 0.2 s within 3 s
     (proves GStreamer decodes both inside the AppImage)
   - the `localStorage` counter survives a restart of the app
   - clicking the `#dl-blob` and `#dl-http` download links does not trigger a `Deny` in the
     navigation log
6. `spike-linux-newest` on `arc-llama-monitor` (Ubuntu 26.04), with `env:
   APPIMAGE_EXTRACT_AND_RUN: "1"` (that image does not set it, and pods have no FUSE): run N
   good's `--version`.

Pass: every assertion in tasks 1–6 holds. Tray behavior on Linux cannot be tested headlessly;
record it as untested.

**Stop conditions:** the AppImage will not start on Ubuntu 22.04 or 26.04; `tauri-driver`
cannot drive the AppImage at all (then report; Linux GUI coverage would drop to the smoke test).

### 1D — Webview behavior matrix (Mac and Windows by the OWNER, Linux from 1C)

Run the 1A/1B/1C spike builds against the test page, then against the real SPA:

```bash
PERSONA_FORGE_PORT=8318 uv run persona-forge serve
```

The spike's "go" button targets 8318.

Fill this table. It goes into the results section:

| Check | macOS 26 | Windows 11 | Linux (1C, automated) |
| --- | --- | --- | --- |
| Page at `http://127.0.0.1:8318` loads (ATS on macOS) | | | |
| `#dl-blob` and `#dl-http` downloads reach `on_download`; Save dialog; file written | | | n/a |
| `<audio>` blob WAV plays | | | |
| MP3 plays (test page; on Mac/Windows also the real SPA Speak page) | | | |
| `target=_blank` link: which hook fires; opens the system browser | | | n/a |
| `window.open`: which hook fires | | | n/a |
| Same-window external link: `on_navigation` sees it | | | |
| `<input type=file>` picker works | | | n/a |
| Clipboard shortcuts in the textarea | | | n/a |
| localStorage counter persists across app restart | | | |
| Tray icon visible and its menu works | | | untested |
| `persona-forge serve --host 0.0.0.0`: exact firewall prompt text, if any | | | n/a |
| From another machine (for example a Debian LXC): `curl http://<machine-ip>:8318/health` returns 200 after allowing the prompt | | | n/a |

**Stop conditions:**

- blob downloads never reach `on_download` on any platform (contract §6.5)
- ATS blocks `127.0.0.1` on macOS 26 and no plist key fixes it (contract §10)
- MP3 does not play in the AppImage (1C task 5)

For each of these, stop and report. The fallbacks change the SPA or the transport and need owner
sign-off.

### Phase 1 deliverable and cleanup

1. Append `## Phase 1 results` to this doc:
   - the pass/fail for every criterion above, with CI run URLs
   - the 1D matrix
   - the measured Sparkle install-to-relaunch time
   - the exact Tauri hook names that catch new-window requests on each OS (used by Phase 3
     `nav.rs`)
   - the firewall prompt behavior for `0.0.0.0` on macOS and Windows (used by Phase 3's Settings
     hint text)
   - every API difference from this plan
2. If a finding changes a contract decision, amend the architecture doc in a **separate commit**
   titled `docs(plan): amend desktop architecture after Phase 1 spike`, and flag it for owner
   sign-off.
3. Before deleting anything, tag the spike head `desktop-spike-final`, push the tag, and record
   the tag and the path of the `--ci-update` code in `## Phase 1 results` (Phase 6A ports the
   client side from there; Phase 6B reuses the Windows install-wait logic). Then delete `spike/` and restore the stub `desktop-spike.yml` on the branch.
   Cherry-pick only the docs commits onto `desktop/p1-results`, and in that PR also delete the
   `desktop-spike.yml` stub from `main`. The owner deletes both spike pre-releases. Final state
   after Gate 1's PR: `desktop-spike.yml` and `spike/` exist nowhere in the repo.

Gate 1 = every pass criterion in 1A–1D is met, or the owner has explicitly accepted a stop
condition's fallback in writing. PR title: `docs(plan): record desktop spike results`.

---

## Phase 2 — Core library: lib extraction, progress, payload verification, supervisor, retention

### Objective

Turn `launcher/` into lib + bin (D9) and add the pieces the desktop shell needs. Make `serve`
supervisable (contract §6.2), which also fixes `serve` from the CLI archive. The CLI's behavior
otherwise stays the same, except for D14 retention. Add the first Rust CI lane and the
`dry_run` release input.

### Read first

- Contract D4, D5, D9, D14, §6.2, §6.3, §7 (payload verification).
- `launcher/src/{main,bootstrap,manifest,paths}.rs` in full, including their tests.
- `src/persona_forge/cli.py` `cmd_serve`, `_server_command`; `tests/tier1_unit/test_cli.py`
  (`TestServerCommand`, `TestSpawnedProcessAcceptance`); `tests/fixtures/fake_wsgi_app.py`.
- The `process-wrap` and `sysinfo` docs for the versions you pin.

### Task 0 — Reproduce the `serve` bug first (bug protocol)

`TestSpawnedProcessAcceptance` passes today only in environments where the server binary is
already on `PATH` (typically because `uv run` puts `.venv/bin` there; the test itself does not
manage `PATH`).
Add a variant that spawns the same command with `PATH` reduced to the OS default
(`os.defpath` on POSIX; `C:\Windows\System32;C:\Windows` on Windows) and assert it reaches
`/health`. Run it **before** changing `cli.py` and record the failure (expected:
`FileNotFoundError` for `gunicorn`). Then fix it. The test stays as the regression test.

### Files

- Create `launcher/src/lib.rs`, `launcher/src/supervisor.rs`, `launcher/src/retention.rs`,
  `launcher/src/health.rs`.
- Modify `launcher/src/main.rs` (use the lib crate, `mod` → `use`), `bootstrap.rs`,
  `manifest.rs`, and `launcher/Cargo.toml` (add `[lib] name = "persona_forge_launcher"`,
  `path = "src/lib.rs"`; add `process-wrap` with features `std`, `process-group`, `job-object`,
  `kill-on-drop`, and `sysinfo`, both pinned with `=`).
- Modify `src/persona_forge/cli.py` (`_server_command`, `cmd_serve`) and
  `tests/tier1_unit/test_cli.py`.
- Modify `.github/workflows/release-launcher.yml` (`dry_run` input only).
- Create `.github/workflows/ci-desktop.yml`.

### Python change (`cli.py`, contract §6.2)

- POSIX: `_server_command` returns `[sys.executable, "-m", "gunicorn", <target>, <same flags as
  today>]`, and `cmd_serve` calls `os.execv(sys.executable, argv)`. No PATH lookup.
- Windows: `cmd_serve` imports the WSGI target (`module:attr` from `PERSONA_FORGE_WSGI_TARGET`,
  default `persona_forge.app:app`) and calls `waitress.serve(app, host=..., port=...,
  threads=4)` in-process. `_server_command` keeps returning the equivalent argv for the
  `[serve] ... exec:` log line and the existing unit tests.
- Update `TestServerCommand` expectations to the new argv. Delete any assertion that only pins
  wording.

Rust lockstep nit: add the filesystem-root rejection to `launcher/src/paths.rs::app_data_root`
that `src/persona_forge/paths.py` already has (`paths.py:78-79`), with a test. This closes the
one known gap in the paths.rs/paths.py lockstep (D9).

### Required interfaces

```rust
// lib.rs
pub mod bootstrap; pub mod health; pub mod manifest; pub mod paths; pub mod retention; pub mod supervisor;

// bootstrap.rs  (existing ensure_env keeps its exact signature and delegates)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Step { Venv, Sync, Install }
pub trait Progress { fn step(&self, step: Step); }
pub struct NoProgress;
impl Progress for NoProgress { fn step(&self, _: Step) {} }
pub fn ensure_env_with_progress(
    manifest: &Manifest, bundle_dir: &Path, uv_path: &Path, versions_dir: &Path,
    current_marker: &Path, runner: &dyn Runner, progress: &dyn Progress,
) -> Result<PathBuf, BootstrapError>;
// After a successful promote + current marker write, call
// retention::prune_versions(versions_dir, &manifest.version, previous.as_deref(), &SysinfoInUse)
// where `previous` = contents of current_marker read BEFORE the write (None if absent or equal).
// A prune failure is logged to stderr and never fails ensure_env.

// manifest.rs
pub fn verify_payload(manifest: &Manifest, payload_dir: &Path) -> Result<(), ManifestError>; // wheel + requirements only
// verify_bundle = verify_payload + uv member check (refactor, same behavior)

// retention.rs
pub trait InUse { fn is_in_use(&self, dir: &Path) -> bool; }
pub struct SysinfoInUse; // true if any live process's executable path is under `dir` (sysinfo)
/// Delete every direct child directory of `versions_dir` whose name is not `keep_current` or
/// `keep_previous` (including stale `*.staging` dirs), skipping any for which `in_use` returns
/// true **or whose version compares semver-greater than `keep_current`** (D14: a stale older
/// CLI archive must never delete a newer desktop env). Unparseable names are treated as older.
/// Ignores regular files. Returns the deleted paths. Never follows symlinks (a symlinked
/// child is removed as a link, not recursed).
pub fn prune_versions(versions_dir: &Path, keep_current: &str, keep_previous: Option<&str>,
    in_use: &dyn InUse) -> std::io::Result<Vec<PathBuf>>;

// health.rs  (std-only HTTP/1.1 GET over TcpStream; no new HTTP client dependency)
#[derive(Debug, PartialEq, Eq)]
pub enum PortState { Free, PersonaForge, Other }
/// Contract §6.3: Free if TcpListener::bind((bind_host, port)) succeeds (dropped at once);
/// otherwise GET http://127.0.0.1:<port>/health with `timeout`: PersonaForge if the body is a JSON
/// object with a string "status" and a "service_started" key; anything else is Other.
pub fn probe_port(bind_host: &str, port: u16, timeout: Duration) -> PortState;
pub fn health_ok(port: u16, timeout: Duration) -> bool; // 200 + JSON body from 127.0.0.1

// supervisor.rs
pub struct ServerSpec {
    pub python: PathBuf, pub host: String, pub port: u16, // host: "127.0.0.1" or "0.0.0.0" (D18)
    pub extra_env: Vec<(String, String)>, pub log_path: PathBuf,
}
pub struct ServerHandle { /* process-wrap child */ }
impl ServerHandle {
    /// Spawns `<python> -m persona_forge.cli serve --host <host> --port <port>` in its own
    /// process group (Unix) / kill-on-close Job Object (Windows, CREATE_NO_WINDOW), stdout+stderr
    /// appended to log_path.
    pub fn spawn(spec: &ServerSpec) -> std::io::Result<Self>;
    pub fn pid(&self) -> u32;
    pub fn try_wait(&mut self) -> std::io::Result<Option<std::process::ExitStatus>>;
    /// Unix: SIGTERM the group, wait up to `grace`, then SIGKILL the group.
    /// Windows: TerminateJobObject immediately (no graceful signal exists; `grace` is ignored).
    pub fn stop(self, grace: Duration) -> std::io::Result<()>;
}
pub enum ReadyError { Exited(Option<i32>), Timeout }
pub fn wait_ready(h: &mut ServerHandle, port: u16, timeout: Duration) -> Result<(), ReadyError>;
// Pidfile (Unix orphan recovery, §6.2):
pub struct PidRecord { pub pid: u32, pub pgid: u32, pub port: u16, pub started_at: u64 }
pub fn write_pidfile(path: &Path, rec: &PidRecord) -> std::io::Result<()>; // atomic
pub fn read_pidfile(path: &Path) -> Option<PidRecord>;
#[cfg(unix)] pub fn kill_orphan(rec: &PidRecord, grace: Duration) -> std::io::Result<bool>;
// kill_orphan returns false without signalling if `pid` is not alive or its command line (from
// `ps -o command= -p <pid>`) does not contain "persona_forge.app:app".
```

For testability, `ServerHandle` has a `#[cfg(test)]`-visible constructor
`spawn_command(program, args, env, log_path)` that uses the same wrapping as `spawn`.

### Tests first (in-module `#[cfg(test)]`, same style as the existing ones)

- `retention` (with a fake `InUse`):
  - keeps current and previous and deletes others
  - deletes `*.staging`
  - ignores files
  - `keep_previous = None` keeps only current
  - a missing `versions_dir` returns `Ok(vec![])`
  - a dir the fake reports in use is kept
  - a version semver-greater than `keep_current` is kept even when idle (dual CLI-archive +
    desktop installs share one `versions/` dir; D14)
  - (Unix) a symlink child is unlinked and its target survives
  - `SysinfoInUse` for real: copy the system `sleep` (Unix) or `ping.exe` (Windows) into
    `<tmp>/versions/old/bin/`, start it from there, and assert `is_in_use(<tmp>/versions/old)` is
    true while it runs and false after it is killed
- `bootstrap`:
  - `ensure_env_with_progress` reports `Venv, Sync, Install` in order, using the existing fake
    `Runner`
  - the fast path reports nothing
  - retention runs only after success; the previous version dir survives a failed provision
    (reuse the existing failure-injection tests)
  - `current.txt` holding the same version as the new one means `previous = None`
- `manifest`: `verify_payload` passes when uv is missing or has a different hash, and fails on a
  wheel mismatch and a requirements mismatch. `verify_bundle` behavior is unchanged: the existing
  tests pass unmodified.
- `health`: a `TcpListener` fixture thread in the test that serves
  1. 200 with `{"status":"ok","service_started":true,"version":"x"}` → `PersonaForge`
  2. 200 with `{"status":"error","service_started":false}` (no `version`) → `PersonaForge`
  3. a 200 HTML body → `Other`
  4. a 500 status → `Other`
  5. an unbound port → `Free`
  6. an accept-then-never-respond → `Other` within the timeout
- `supervisor` (Unix `#[cfg(unix)]`): `spawn_command("sh", ["-c", "sleep 60 & echo $! >
  <tmp>/gc; wait"])`, then `stop(2s)`. Assert that the child **and** the grandchild pid (read
  from the file) are gone (`kill -0` fails).
  - `try_wait` reports the exit of a `sh -c 'exit 3'` child.
  - `wait_ready` returns `Exited(Some(3))` for it.
- `supervisor` (Windows `#[cfg(windows)]`): the same, with
  `cmd /c "start /b ping -n 60 127.0.0.1 >NUL & ping -n 60 127.0.0.1 >NUL"`. After `stop`,
  none of the PIDs captured before `stop` is alive.
- `supervisor` with the **real** server (both OSes, `#[ignore]` by default and run explicitly in
  the gate): spawn `<repo .venv python> -m persona_forge.cli serve` with
  `PERSONA_FORGE_WSGI_TARGET=tests.fixtures.fake_wsgi_app:app`, `PYTHONPATH=<repo>/src:<repo>`,
  and `PATH` reduced to the OS default. `wait_ready` succeeds, `probe_port` says
  `PersonaForge`, and after `stop` the port is `Free` and no process with `persona_forge.app:app`
  or `fake_wsgi_app` in its command line survives.
- pidfile round-trip. `kill_orphan` refuses a live pid whose command line lacks
  `persona_forge.app:app` (use the test process's own pid).

### CI lane `.github/workflows/ci-desktop.yml`

- Triggers: `pull_request` on paths `launcher/**`, `desktop/**`, `.github/workflows/ci-desktop.yml`;
  `workflow_dispatch`.
- Fork guard on every job:
  `if: github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository`.
- Job `launcher-linux` on `arc-persona-forge-desktop`: fmt check, clippy `-D warnings`, test.
- Job `launcher-windows` on `self-hosted-windows` (`shell: bash`): test.
- Job `launcher-macos` on `self-hosted-macos`: test.
- Use rustup `RUST_VERSION` `1.98`. Add `ci-desktop.yml` (and, in later phases,
  `desktop-build.yml`) to the `managerFilePatterns` of the Renovate `RUST_VERSION` regex manager
  in `renovate.json`, which today matches only `release-launcher.yml`.
- **No secrets** in this workflow, ever (D19).

### `dry_run` input (`release-launcher.yml`)

Add a `workflow_dispatch` input `dry_run` (boolean, default `false`). Both
`softprops/action-gh-release` steps get `if: … && !inputs.dry_run`; everything else, including
the contract validation, still runs. Without it the manual path **publishes a real,
non-prerelease GitHub Release** that becomes `releases/latest`, and every gate in this plan must
avoid that. (Reviewed 2026-09-25: `validate_release_contract.py` checks the wheel name and each
archive's `manifest.version` against the `--version` argument; it does **not** read
`pyproject.toml`.) Dry runs therefore always pass
`persona-forge-v<pyproject version>` so the dry-run artifacts match what a real release would ship.

### Gate 2

```bash
cargo fmt --manifest-path launcher/Cargo.toml --check
cargo clippy --manifest-path launcher/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path launcher/Cargo.toml
cargo test --manifest-path launcher/Cargo.toml -- --ignored   # the real-server supervisor test
cargo build --manifest-path launcher/Cargo.toml --release
PYTHONPATH=src:src/export uv run --frozen python -m pytest tests/tier1_unit/test_cli.py -v
python scripts/validate_repo.py && git diff --check
V=$(uv run --frozen python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
gh workflow run release-launcher.yml --ref desktop/p2-core-lib -f tag_name="persona-forge-v$V" -f dry_run=true
gh run watch <run-id>
```

Pass: every command above succeeds; the Task 0 test failed before the fix and passes after
(both outputs in the PR); `ci-desktop.yml` is green on all three launcher jobs; the dry run is
green with `smoke-launcher` passing on all three OSes and no release created (`gh release view
persona-forge-v$V` shows the existing release unchanged, or none).

Manual smoke (implementer, on the Mac): download the dry run's macOS archive artifact, extract
it, run `PERSONA_FORGE_HOME=$(mktemp -d) ./persona-forge-launcher serve --port 18318` in a
normal Terminal (no venv activated), wait for `curl -fsS http://127.0.0.1:18318/health`, then
stop it. Paste the output.

**Deviation allowed:** if `process-wrap` cannot express the Windows Job Object kill-on-close
together with `CREATE_NO_WINDOW`, implement it directly with `windows-sys` (`CreateJobObjectW`,
`SetInformationJobObject`, `AssignProcessToJobObject`) behind the same interface and note it in
the PR.

PR title: `feat(launcher): extract core library with server supervisor and env retention`

```text
BEGIN_COMMIT_OVERRIDE
feat(launcher): extract core library with server supervisor and env retention

fix(cli): run gunicorn and waitress without relying on PATH so native serve works

ci(desktop): add Rust test lane for launcher on Linux, macOS and Windows
END_COMMIT_OVERRIDE
```

---

## Phase 2b — Server-side UI preferences (independent of Phases 1–2; can run in parallel)

### Objective

Implement contract D17 / §6.11: UI preferences are saved by the server in
`ui_preferences.json` next to `runtime.json`, for every deployment. This phase touches no Rust
and no desktop code, and can merge before the desktop shell exists.

### Read first

- Contract D17, §6.11.
- `src/persona_forge/runtime_store.py` and `tests/tier1_unit/test_runtime_store.py` (the pattern
  to copy), `src/persona_forge/paths.py` `runtime_data_dir`.
- `src/persona_forge/app.py` `/runtime/config` routes (route and error-response style), and
  `tests/tier2_backend/test_app_runtime_config.py` (endpoint test style).
- `frontend/src/lib/theme.ts`, `frontend/src/lib/experienceLevel.ts`,
  `frontend/src/lib/updateCheck.ts`, the `localStorage` uses in
  `frontend/src/pages/VoiceLibraryPage.tsx`, and `frontend/src/lib/api.ts`.
- `docs/api/HTTP_API_REFERENCE.md` (`/runtime/config` section as the format to follow).
- `tests/ui/README.md` (Playwright tier).

### Files

- Create `src/persona_forge/ui_preferences_store.py`, `tests/tier1_unit/test_ui_preferences_store.py`.
- Modify `src/persona_forge/app.py` (two routes). Create `tests/tier2_backend/test_app_ui_preferences.py`.
- Create `frontend/src/lib/uiPreferences.ts`. Modify `theme.ts`, `experienceLevel.ts`,
  `updateCheck.ts` (dismissal only), `VoiceLibraryPage.tsx`, `api.ts`.
- Create one Playwright spec under `tests/ui/` (follow the existing layout).
- Modify `docs/api/HTTP_API_REFERENCE.md`.

### Required interfaces

```python
# ui_preferences_store.py
ALLOWED_KEYS: dict[str, Validator]  # exactly the six keys in contract §6.11
def load(path: Path | None = None) -> dict[str, Any]           # missing/corrupt -> {} + warning
def merge_and_save(update: Mapping[str, Any], path: Path | None = None) -> dict[str, Any]
# merge_and_save raises ValueError(<key>: <reason>) for an unknown key or invalid value, before
# writing anything. Writes are atomic (tempfile in the same dir + os.replace), same as runtime_store.
```

Routes: `GET /ui/preferences` returns `{"values": {...}}`; `POST /ui/preferences` takes
`{"values": {...}}` and returns the full merged `{"values": {...}}`; a `ValueError` is a 400
with `{"error": "<message>"}`; a body over 16 KB is a 413. These routes do not use the model
executor and work before the model loads (never 503).

```ts
// uiPreferences.ts
export type PrefKey = 'theme' | 'experienceLevel' | 'voiceLibrary.tab' | 'voiceLibrary.layout'
  | 'voiceLibrary.analysisExpanded' | 'updates.dismissedVersion'
export function getPref<T>(key: PrefKey, fallback: T): T          // sync, from the local copy
export function setPref(key: PrefKey, value: unknown): void       // local copy + background POST
export async function syncPrefsFromServer(): Promise<void>        // called once at app start
export function subscribePrefs(cb: () => void): () => void        // re-render after sync
```

The local copy uses each key's **existing** `localStorage` key name **and encoding** (contract
§6.11 table). Implement a per-key codec (`decode(raw: string | null) -> value | undefined`,
`encode(value) -> string`): raw strings stay raw; `voiceLibrary.analysisExpanded` maps
`'true'`/`'false'` to a bool; anything that fails to decode is `undefined` and is skipped by the
migration.

### Tests first

- tier 1 (`test_ui_preferences_store.py`): missing file → `{}`; corrupt JSON → `{}` and a
  warning; unknown key rejected and file unchanged; wrong type rejected (`analysisExpanded:
  "yes"`); over-length string rejected; merge keeps untouched keys; round trip.
- tier 2 (`test_app_ui_preferences.py`): GET on an empty store; POST then GET; 400 on an unknown
  key; 413 on an oversize body; GET works while the model is not loaded.
- Playwright spec 1: set the theme in the UI, clear the browser's `localStorage`, reload, and
  assert the theme is still applied (it came from the server).
- Playwright spec 2 (migration): against an empty server store, seed the **old** keys in
  `localStorage` before the first load (including `voice-library-analysis-expanded` = `'false'`
  and a non-default theme), load the app, and assert `GET /ui/preferences` then returns
  `analysisExpanded: false` and that theme.

### Gate 2b

```bash
PYTHONPATH=src:src/export uv run --frozen python -m pytest tests/tier1_unit/test_ui_preferences_store.py -v
PYTHONPATH=src:src/export uv run --frozen python -m pytest tests/tier2_backend/test_app_ui_preferences.py -v
PYTHONPATH=src:src/export uv run --frozen python -m pytest tests/tier1_unit -q
npm run --prefix frontend check
python scripts/validate_repo.py && git diff --check
```

Plus the Playwright spec run per `tests/ui/README.md`, with output in the PR.

Manual smoke (implementer, on the Mac): `PERSONA_FORGE_HOME=$(mktemp -d) uv run persona-forge
serve`, open the UI in two different browsers, change the theme in one, reload the other, and
confirm it matches; then `cat "$PERSONA_FORGE_HOME"/voices/ui_preferences.json` (or wherever
`paths.runtime_data_dir()` resolves; print it with `persona-forge doctor --json`).

PR title: `feat(ui): save UI preferences on the server so they follow the install`

---

## Phase 3 — Desktop shell (runs locally; no packaging or signing yet)

### Objective

A `desktop/` Tauri v2 app that implements contract §6 end to end on the developer's Mac (the
workstation is darwin arm64), and compiles on Windows and Linux in CI. It also includes the
Python `/health` field and the frontend banner change (§6.10).

### Read first

- Contract §6 in full (including §6.11–§6.13), D2, D10, D11, D13, D16, D17, D18.
- Phase 2b must be merged first (the Settings window assumes server-side preferences).
- `## Phase 1 results`, especially the hook names and every API difference.
- The Phase 2 lib API (`launcher/src/lib.rs` and its modules).
- `frontend/src/components/UpdateAvailableBanner.tsx`, `frontend/src/lib/api.ts` (the `getHealth`
  type), `src/persona_forge/app.py` `health()`, `tests/tier2_backend/test_app_health.py`,
  `docs/api/HTTP_API_REFERENCE.md` (`/health`), `docs/ENV_REFERENCE.md`.

### Files

- Create `desktop/` per contract §5. `Cargo.toml` depends on `persona-forge-launcher = { path =
  "../launcher" }`, `tauri` (features `tray-icon`), `tauri-build`, and plugins `single-instance`,
  `window-state`, `dialog`, `opener`, `notification`, `log`, `clipboard-manager`. Pin every Tauri
  crate with `=` to the versions Phase 1 used. Commit `desktop/Cargo.lock`.
- `.gitignore`: add `desktop/payload/`, `desktop/binaries/`, `desktop/target/`.
- Create `scripts/stage_desktop_payload.py` (below). Create
  `tests/tier1_unit/test_stage_desktop_payload.py`.
- Modify `src/persona_forge/app.py` (`health()` adds `"shell"`, contract §6.10) and
  `tests/tier2_backend/test_app_health.py` (both the normal and the startup-failed case).
- Modify `frontend/src/components/UpdateAvailableBanner.tsx` and the `getHealth` response type.
- Modify `docs/ENV_REFERENCE.md` (`PERSONA_FORGE_SHELL`) and `docs/api/HTTP_API_REFERENCE.md`
  (the `shell` field).
- Icons (contract D16), all committed:
  - `desktop/icons/source/app-icon.svg`: a 1024×1024 canvas holding the contents of
    `assets/brand/concepts/persona-forge/hero-v2/finalists/signal-crucible/svg/favicon.svg`
    scaled to an 824×824 square at offset (100, 100) (Apple's macOS icon grid), transparent
    outside it. Keep the gradients and colors exactly.
  - `desktop/icons/source/tray-template.svg`: `mark-small.svg` reduced to one color: every
    stroke and fill `#000000`, gradients and filters removed, and shape opacity kept, so macOS
    can tint it as a template image.
  - Generate the icon set with `cargo tauri icon desktop/icons/source/app-icon.svg`. If the
    pinned `tauri-cli` does not accept SVG input, rasterize it first with `rsvg-convert -w 1024
    -h 1024` (Homebrew `librsvg`) and feed it the PNG. Render the tray PNGs (`@1x` 22 px, `@2x`
    44 px) the same way, from `tray-template.svg` for macOS and from `mark-small.svg` for
    Windows/Linux.
- Extend `ci-desktop.yml` with `desktop-linux` (fmt, clippy, test on `arc-persona-forge-desktop`),
  `desktop-macos` and `desktop-windows` (`cargo check`, plus test). These need a staged payload
  (see `tauri.conf.json` resources). Use `scripts/stage_desktop_payload.py --fake` (below) in CI.

### `scripts/stage_desktop_payload.py`

```text
usage: stage_desktop_payload.py --target <triple> --version X.Y.Z --wheel <whl> --uv-binary <path>
                                --uv-version V --out-root desktop [--fake]
```

- `--target` accepts `aarch64-apple-darwin`, `x86_64-pc-windows-msvc`, `x86_64-unknown-linux-gnu`.
  Define a small `DESKTOP_TARGETS` map in this script that reuses the `--python-platform` values
  from `package_launcher_archive.TARGETS` (MSVC maps to the same value as the existing GNU
  entry). Do **not** add keys to `TARGETS`: it drives the CLI archive's target choices and its
  `.exe` naming.
- It writes:
  - `desktop/payload/<wheel>`
  - `desktop/payload/requirements-<target>.txt`, via
    `package_launcher_archive.export_requirements` (which runs `uv pip compile`)
  - `desktop/payload/manifest.json`, schema v1, built with the same fields as the archive
    manifest; factor a `build_manifest(...)` helper out of `package_launcher_archive.main` and
    reuse it
  - `desktop/binaries/uv-<target>[.exe]`
- `--fake` writes placeholder files and a manifest whose `wheel.sha256` and
  `requirements_sha256` are 64 zeros, for CI compile/test lanes only. It never runs `uv pip
  compile`. `verify_payload` must reject it with an error that contains "fake payload" (special
  case the all-zero hash); add that test in Phase 3.
- Tests follow the existing `test_package_launcher_archive.py` subprocess-fake convention.

### Tauri configuration essentials (`desktop/tauri.conf.json`)

- `productName` "Persona Forge"; `identifier` per D16; `version` "0.0.0" (overridden at build).
- `build.frontendDist` "splash".
- `app.windows`: none declared. Create `main` in Rust, so `on_navigation` and `on_download`
  handlers attach at build time.
- `app.security.csp` for the splash:
  `default-src 'self'; script-src 'self'; style-src 'self'; connect-src ipc: http://ipc.localhost`.
- `bundle.resources`: `{"payload/": "payload/"}`. `bundle.externalBin`: `["binaries/uv"]`.
- `bundle.macOS.minimumSystemVersion` "14.0". `bundle.windows.nsis.installMode` "currentUser".
  `bundle.windows.webviewInstallMode` `{"type":"embedBootstrapper"}`.
- `bundle.linux.appimage.bundleMediaFramework` true. No `deb` configuration (contract D8).
- `capabilities/splash.json` and `capabilities/settings.json` exactly as in contract §6.6. No
  `remote` key anywhere.

### Behavior tasks (each maps to a contract section)

1. `main.rs` + `args.rs` (contract §6.8):
   - `#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]`
   - first, `args::parse()`: `--smoke-test <out.json>` runs `smoke::run` and exits; any other
     `--` flag prints `unknown argument: <flag>` to stderr and exits **2** (`--ci-update` is
     added in Phase 6A behind the `ci-hooks` feature); non-flag OS arguments are ignored
   - otherwise build Tauri, registering `tauri-plugin-single-instance` **first** (its callback
     shows and focuses `main`), then the other plugins
2. `settings.rs`: load/save `desktop/settings.json` (§6.7) under
   `paths::app_data_root(...)`, using the same `environ`/`home` resolution as the CLI `main.rs`
   (factor a `paths::resolve_app_data_root_from_env()` helper into the lib if needed). Unknown
   keys are preserved (store a `serde_json::Map` for extras). Writes are atomic.
3. `port.rs`: `select_port(mode, persisted, probe)` (§6.3) as a pure function. It returns
   `PortDecision { Use(u16), Moved { from: u16, to: u16 }, ExternalPersonaForge(u16),
   FixedPortBusy(u16), NoneFree }`. The dialogs and the one-time "port moved" notification live
   in `app.rs`.
4. `app.rs`: the state machine from §6.1 runs on a background thread. It emits
   `bootstrap://progress` events and keeps `BootstrapState` in `tauri::State<Mutex<…>>`.
   - The `Runner` implementation pipes uv output line by line to `logs/bootstrap.log` and the
     event (a ring buffer of 200 lines).
   - Payload dir and uv path come from `bundle_paths()` (contract §6.8), the same function smoke
     mode uses. In debug builds, assert it matches `app.path().resource_dir()`. Follow the Phase 1
     findings for the dev (`cargo tauri dev`) layout.
   - `Running`: `main.navigate(http://127.0.0.1:<port>/)`, whatever the bind address.
   - Bind address: `127.0.0.1`, or `0.0.0.0` when `network_access` is true (D18), passed as
     `ServerSpec.host` (defined in Phase 2).
   - Unix orphan recovery (§6.2) runs before port selection.
5. `nav.rs`: `classify(url, port)` (§6.5), a pure function. `app.rs` wires it into
   `on_navigation` and into whichever new-window hook Phase 1 found. `OpenExternal` goes to
   `tauri_plugin_opener::open_url`.
6. `downloads.rs`: `on_download` → the Save dialog → set the destination. On success, notify with
   "Show in Folder" (`opener::reveal_item_in_dir`).
7. `menu.rs`, `tray.rs`: exactly the menus and close behavior in §6.4. "Open in Browser" calls
   `opener::open_url(http://127.0.0.1:<port>/)`. "Show Logs" calls `reveal_item_in_dir(logs dir)`.
   "Check for Updates…" exists but stays disabled until Phase 6A. Tray creation failure disables
   the tray for the session.
8. Window-state plugin: exclude `VISIBLE` from the restored flags, so a window hidden to the tray
   never restores as invisible.
9. `logs.rs`: `tauri-plugin-log` to `desktop/logs/desktop.log`. Rotate `server.log` and
   `bootstrap.log` at startup (`.1`, `.2`, cap 10 MB).
10. Quit path (menu, tray, Cmd+Q, `RunEvent::ExitRequested` with no prevent, and on Unix
    `SIGTERM`/`SIGINT`/`SIGHUP` via a signal handler that asks the app to exit):
    `ServerHandle::stop(10s)`, delete `server.pid`, flush logs, exit. Guard it so it runs once.
11. `splash/`: plain HTML/CSS/JS (no build step). It shows the step list with the current step
    highlighted, a scrolling log tail, and the error panel with Retry / Show Logs / Quit. It
    follows the SPA's dark theme colors. No external resources.
12. Python: in `app.py` `health()`, add `state["shell"] = os.environ.get("PERSONA_FORGE_SHELL")
    or None` (contract §6.10). Tests in `tests/tier2_backend/test_app_health.py`: `None` by
    default, `"desktop"` when the env var is set (monkeypatch), and present in the
    startup-failed response too.
13. Frontend: `UpdateAvailableBanner` returns `null` when `health.shell === 'desktop'`. Add
    `shell?: string | null` to the health type. Run `npm run --prefix frontend check`.
14. Settings window (§6.13): `desktop/splash/settings.html` + `settings.js`, loaded as
    `WebviewUrl::App("settings.html")`, the `settings` window
    created on demand (only one at a time; focus it if already open), and the commands in §6.6.
    `apply_settings` validates the port (1024–65535, integer), writes `settings.json`, and
    restarts the server only when `port_mode`, `port` or `network_access` changed. When
    `network_access` turns on, show the firewall hint text recorded in the Phase 1 results.
15. `netinfo.rs`: `fn lan_ipv4(addrs: &[IpAddr]) -> Vec<Ipv4Addr>` as a pure filter (drop
    loopback, link-local `169.254/16`, unspecified and IPv6), fed by the interface crate. Used by
    the Settings list and "Copy Server Address" (§6.4), which writes to the clipboard through
    the Tauri clipboard plugin.
16. Windows only: create the main webview with the WebView2 data directory set to
    `<app_data_root>/desktop/webview` (the webview builder's data-directory option; verify the
    name in the pinned Tauri version), so it follows `PERSONA_FORGE_HOME` (contract §6.7).

### Tests first (Rust unit tests in `desktop/`)

- `nav::classify`: allowed port; `blob:http://127.0.0.1:<port>/<uuid>` (`Allow`); `about:blank`
  (`Allow`); the same host on another port (`Deny`); `localhost:<port>` (`Deny`; only
  `127.0.0.1` is allowed); `https://github.com/...` (`OpenExternal`); `mailto:`
  (`OpenExternal`); `file:///etc/passwd`, `javascript:`, `data:` (`Deny`); the splash origins
  (`Allow`).
- `args::parse`: `--smoke-test x.json` → smoke; `--bogus` → exit code 2; `--ci-update x.json`
  without the feature → exit code 2; a macOS `-psn_0_123` argument is ignored.
- `bundle_paths`: the documented layout for each OS resolves to `payload` and `uv[.exe]`.
- `manifest::verify_payload` (launcher crate): a `--fake` payload is rejected with "fake payload".
- `port::select_port`: each branch of §6.3 in both modes, including: auto + persisted Free;
  auto + persisted PersonaForge (→ `ExternalPersonaForge`); auto + persisted Other with 8319
  free (→ `Moved { 8318, 8319 }`); fixed + persisted Other (→ `FixedPortBusy`, never moved);
  first run with 8318 answering as Persona Forge (→ `ExternalPersonaForge(8318)`, never a second
  server); first run with 8318 busy (`Other`) and 8319 free (→ `Use(8319)`); all busy (→
  `NoneFree`).
- `netinfo::lan_ipv4`: keeps `192.168.1.20` and `10.0.0.5`; drops `127.0.0.1`, `169.254.3.4`,
  `0.0.0.0` and every IPv6 address.
- `settings`: defaults when the file is missing (`port_mode: "auto"`, `network_access: false`,
  `tray_enabled: true`); unknown keys survive a round trip; an out-of-range port is rejected; a
  corrupt file → defaults, and the corrupt file is renamed to `settings.json.bad` and a log line
  written.
- `smoke`: JSON shape serialization. The end-to-end behavior is covered by the gate.

### Local dev loop (the developer's Mac)

```bash
uv build                                                     # wheel -> dist/
bash scripts/fetch_uv_binary.sh 0.12.9 aarch64-apple-darwin uv-bin
uv run --frozen python scripts/stage_desktop_payload.py --target aarch64-apple-darwin \
  --version "$(uv run --frozen python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")" \
  --wheel dist/*.whl --uv-binary uv-bin/uv --uv-version 0.12.9 --out-root desktop
cargo install tauri-cli --version <pinned> --locked          # once
(cd desktop && PERSONA_FORGE_HOME="$(mktemp -d)" cargo tauri dev)
```

### Gate 3

```bash
cargo fmt --manifest-path desktop/Cargo.toml --check
cargo clippy --manifest-path desktop/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path desktop/Cargo.toml
cargo test --manifest-path launcher/Cargo.toml
PYTHONPATH=src:src/export uv run --frozen python -m pytest tests/tier1_unit -q
npm run --prefix frontend check
# Headless end-to-end on the Mac (real payload, fresh state):
(cd desktop && cargo build --release)
PERSONA_FORGE_HOME="$(mktemp -d)" desktop/target/release/persona-forge-desktop --smoke-test /tmp/pf-smoke.json; echo "exit=$?"
python3 -c "import json;d=json.load(open('/tmp/pf-smoke.json'));assert d['ok'],d;print(d)"
python scripts/validate_repo.py && git diff --check
```

Plus `ci-desktop.yml` green on all six jobs.

Plus an **OWNER / implementer-at-the-Mac** interactive checklist, run through `cargo tauri dev`.
Record each item with a screenshot or log line in the PR:

- [ ] First run: the splash shows venv → sync → install → start → wait, then the SPA loads.
- [ ] Second launch while running: the existing window focuses, and no second server
      (`pgrep -fl persona_forge.app:app` shows one server process group).
- [ ] Cmd+C/V/Z/A work in the Speak page textarea.
- [ ] Speak → download audio → the Save dialog appears → the file is written → the notification
      reveals it.
- [ ] "See what's new"-style external links open the system browser. The `UpdateAvailableBanner`
      is **not** shown (`/health` has `shell: "desktop"`).
- [ ] Close the window → the app stays (Dock). Dock click → the window returns. Cmd+Q → within 10
      s no `persona_forge` process remains.
- [ ] `kill -9 <shell pid>` → relaunch → the orphan server group is killed (the log line
      confirms) and the app starts normally on the same port.
- [ ] Occupy 8318 with `python3 -m http.server 8318` before the first run (fresh
      `PERSONA_FORGE_HOME`) → the app picks 8319 and persists it. Then quit, occupy 8319 the same
      way, relaunch → the app moves to the next free port and shows the "port moved"
      notification.
- [ ] Settings → Fixed port 9123 → Apply → the splash shows a restart, the SPA reloads at
      `127.0.0.1:9123`, and the theme chosen earlier is unchanged (server-side preferences).
- [ ] With 9123 fixed, quit, occupy 9123 with `python3 -m http.server 9123`, relaunch → the
      "port in use" dialog with Open Settings / Retry / Quit, and the app does **not** move to
      another port.
- [ ] Settings → Allow other devices on my network → Apply → the address list shows the Mac's
      LAN IP and the `/v1` base URL. From another machine (for example a Debian LXC):
      `curl http://<mac-ip>:9123/health` returns 200. Record any macOS firewall prompt.
- [ ] Copy Server Address (menu and tray) puts the LAN URL on the clipboard when network access
      is on, and the `127.0.0.1` URL when it is off.
- [ ] The Dock icon, the About panel icon, and the menu-bar icon (in light and dark menu bars)
      render correctly. Screenshot them.
- [ ] The tray/menu-bar toggle persists across restarts. With it off, the tray icon is gone.
- [ ] Window size and position persist across restarts.
- [ ] Break the payload (edit `desktop/payload/manifest.json` wheel sha) → the error screen with
      Retry / Show Logs / Quit.

**Stop condition:** a Phase 1 fallback turns out to be needed that the owner has not approved.

PR title: `feat(desktop): add Tauri desktop shell with managed local server`

```text
BEGIN_COMMIT_OVERRIDE
feat(desktop): add Tauri desktop shell with managed local server

feat(api): report desktop shell in /health and hide web update banner in the desktop app

ci(desktop): build and test the desktop crate on Linux, macOS and Windows
END_COMMIT_OVERRIDE
```

---

## Phase 4 — Packaging and native smoke in CI (unsigned artifacts, not published)

### Objective

The real `desktop-build.yml` (replacing the Phase 0 stub) builds all three desktop targets from
one wheel, stages the payload, bundles, and smoke-tests the **installed/bundled** artifact on
native runners. Nothing is signed or published yet; Phase 4 implements the no-secret jobs of
contract §8 only.

### Read first

- Contract §7, §8, D19. Phase 1 results (the exact build commands that worked).
- `.github/workflows/release-launcher.yml` in full: reuse its checkout, uv, wheel-download and
  artifact action pins **exactly** (the same SHAs).

### Files

- Replace the `desktop-build.yml` stub. Triggers: `workflow_call` and `workflow_dispatch`, both
  with the inputs fixed in Phase 0: `version` (required), `sign` (default false; used from Phase
  5), `feed_base` and `ci_hooks` (used from Phase 6B), `wheel_artifact` (default empty: build the
  wheel in this workflow; non-empty: download that artifact name instead, used in Phase 7).
  Top-level `permissions: contents: read`.
- Create `scripts/smoke_desktop.sh <macos|linux>` and `scripts/smoke_desktop.ps1` (Windows).
- Create `scripts/build_macos_dmg.sh <app-path> <dmg-path>`: a staging dir with the `.app` and an
  `Applications` symlink, `hdiutil create -volname "Persona Forge" … -format UDZO`, fail closed.
- Create `scripts/desktop_gui_check.py`: the Linux WebDriver check (below), run with `uv run
  --with selenium==<pinned> python scripts/desktop_gui_check.py --app <AppImage> --state
  <PERSONA_FORGE_HOME>`. Reuse the Selenium capability shape proven in Phase 1C.
- Add `desktop-build.yml` to the Renovate `RUST_VERSION` regex manager's file patterns.

### Workflow structure

Every job passes `--version ${{ inputs.version }}` to `stage_desktop_payload.py` and
`--config '{"version":"<v>","bundle":{"createUpdaterArtifacts":false}}'` to `cargo tauri
build` (contract §8: one version input; updater `.sig` files come from Phase 6B's
`updater-sigs` job, never from the build).

1. `build-wheel` (only when `wheel_artifact` is empty): the same steps as
   `release-launcher.yml` `build-wheel`. Upload it as `desktop-wheel-and-sdist`.
2. `build-macos` on `self-hosted-macos` (no secrets): `desktop_preflight.sh macos`,
   `fetch_uv_binary.sh` for `aarch64-apple-darwin`, `stage_desktop_payload.py`, `cargo tauri
   build --no-sign --bundles app --target aarch64-apple-darwin`, then
   `scripts/build_macos_dmg.sh` → `PersonaForge-macos-aarch64.dmg`. Upload artifact
   `desktop-macos-aarch64`. (Phase 5 splits this into the signed chain of contract §8.)
3. `build-windows` on `self-hosted-windows` (no secrets; `shell: bash` for the scripts): uv
   `x86_64-pc-windows-msvc`, stage, `cargo tauri build --bundles nsis --target
   x86_64-pc-windows-msvc`, rename the output to `PersonaForge-windows-x86_64-setup.exe`, upload.
4. `build-linux` on `arc-persona-forge-desktop` (no secrets): stage, `cargo tauri build --bundles
   appimage`, rename to `PersonaForge-linux-x86_64.AppImage`, run the glibc check from 1C (fail
   if > 2.35), upload.
5. `smoke-macos` on `self-hosted-macos`, fresh `PERSONA_FORGE_HOME` in `$RUNNER_TEMP`:
   `hdiutil attach -nobrowse -readonly`, copy the `.app` to a temp dir, `hdiutil detach`, run
   `<app>/Contents/MacOS/persona-forge-desktop --smoke-test $RUNNER_TEMP/smoke.json`, assert
   `ok`. Then run it with `--bogus` and assert exit code 2.
6. `smoke-windows` on `self-hosted-windows` (PowerShell), fresh `PERSONA_FORGE_HOME`:
   - install: `$p = Start-Process -FilePath PersonaForge-windows-x86_64-setup.exe -ArgumentList
     '/S' -Wait -PassThru`; fail if `$p.ExitCode -ne 0`
   - **after** install, read `InstallLocation` from the
     `HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*` entry whose `DisplayName` is
     "Persona Forge"; the exe is `<InstallLocation>\persona-forge-desktop.exe`
   - run it with `Start-Process -Wait -PassThru -ArgumentList '--smoke-test',"$env:RUNNER_TEMP\smoke.json"`
     (a GUI-subsystem exe does not block PowerShell otherwise), assert exit code 0 and `ok`
   - run it the same way with `--bogus`; assert exit code 2
   - in `finally`, run the uninstaller from the same registry entry silently
7. `smoke-gui-linux` on `arc-persona-forge-desktop`, **one job** (pods are ephemeral, so the
   provisioned environment cannot be shared across jobs), fresh `PERSONA_FORGE_HOME`:
   - `chmod +x` the AppImage, run `--smoke-test`, assert `ok` (this provisions the env)
   - run `--bogus`, assert exit code 2
   - under `dbus-run-session xvfb-run -a`, start `tauri-driver`, then run
     `desktop_gui_check.py` with the same `PERSONA_FORGE_HOME`, which asserts:
     - within 180 s the main window's URL is `http://127.0.0.1:<port>/` (port read from
       `<state>/desktop/settings.json`) and the SPA root element `#root` has children
     - `window.location.href = 'https://example.com'` leaves the URL unchanged (navigation
       guard)
     - after `POST /ui/preferences {"values":{"theme":"<a non-default theme from theme.ts>"}}`
       and a reload, `document.documentElement.dataset.theme` equals that theme (D17 end to end)
     - it ends the session by sending the app `SIGTERM` (the §6.2 signal path), then asserts
       within 15 s that `pgrep -f persona_forge.app:app` finds nothing and the port is free
8. `smoke-linux-newest` on `arc-llama-monitor` (Ubuntu 26.04), with `env:
   APPIMAGE_EXTRACT_AND_RUN: "1"` (that image does not set it; pods have no FUSE): the same
   AppImage with `--smoke-test`.
9. **Optional OWNER** check on a Debian 13 LXC: download the artifact, `chmod +x`, run
   `APPIMAGE_EXTRACT_AND_RUN=1 ./PersonaForge-linux-x86_64.AppImage --smoke-test /tmp/s.json`,
   and paste `/tmp/s.json` into the PR.

Every smoke script fails closed and prints the smoke JSON. Every script checks at the end that no
server survives: Unix `pgrep -f persona_forge.app:app` finds nothing; Windows
`Get-CimInstance Win32_Process | ? CommandLine -match 'persona_forge\.app:app'` is empty.

### Gate 4

```bash
bash -n scripts/smoke_desktop.sh scripts/build_macos_dmg.sh
python scripts/validate_repo.py && git diff --check
gh workflow run desktop-build.yml --ref desktop/p4-packaging -f version=0.0.0-p4test
gh run watch <run-id>
```

Pass: all build, smoke and GUI-check jobs are green, and the run URL is in the PR. Record the
artifact sizes: DMG, setup.exe, AppImage.

**OWNER** (OA-2 review): install the Phase 4 macOS DMG on the Mac. It is unsigned at this phase,
so after the first blocked launch use System Settings → Privacy & Security → "Open Anyway".
Confirm the Dock icon sits in the normal rounded-square shape, not inside a gray frame, on macOS
26. If it is framed, adjust `app-icon.svg` margins and rebuild before Phase 5.

**Stop condition:** `stage_desktop_payload.py` resolves a different requirement set than the CLI
archive for the same target. Compare against a `release-launcher.yml` artifact of the same commit
with comment lines removed, because `uv pip compile` writes its own command line (including the
output path) into the header: `diff <(grep -v '^#' <desktop file>) <(grep -v '^#' <archive
file>)`. For Windows, compare the desktop `requirements-x86_64-pc-windows-msvc.txt` with the
archive's `requirements-x86_64-pc-windows-gnu.txt`; both resolve for the same
`x86_64-pc-windows-msvc` Python platform.

PR title: `ci(desktop): build and smoke-test desktop bundles on native runners`

---

## Phase 5 — macOS signing, notarization, stapling, and translocation guard

### Objective

When `sign: true`, the macOS artifact is a Developer-ID-signed, notarized, stapled `.app` inside a
signed, notarized, stapled DMG, produced by the job chain in contract §8 (secrets only on the
ephemeral Linux runner, D19) and verified on the Mac. Add the App Translocation guard (§6.9).

### Read first

- Phase 1A results (the exact rcodesign invocations and entitlements that passed) and the
  `desktop-spike-final` tag's `desktop-spike.yml` macOS jobs.
- Contract §6.9, §8, §10, §12, D19.

### Tasks

1. `desktop/entitlements.plist`: exactly the set Phase 1A proved necessary. The default is an
   empty `<dict/>` with the hardened runtime applied through rcodesign flags.
2. Create `scripts/sign_macos.sh <app|dmg> <input> <output>` (runs on Linux): write the PEM and
   API-key files to `$RUNNER_TEMP/pf-sign/` (the same steps as `release-launcher.yml`), run
   `rcodesign sign` (for `app`: `--for-notarization --entitlements-xml-file
   desktop/entitlements.plist`, nested code first), then `rcodesign notary-submit --api-key-file …
   --staple`. It fails closed; the workflow deletes `$RUNNER_TEMP/pf-sign/` in an `if: always()`
   step. It also prints the certificate's Team ID (subject `OU`, via `openssl x509 -noout
   -subject`) and the job exposes it as an output, so the verify job needs no secret.
3. When `inputs.sign` is true, split Phase 4's `build-macos` into the contract §8 chain:
   `build-macos` (unsigned `.app`, zipped with `ditto -c -k --keepParent`) → `sign-macos-app` on
   `arc-persona-forge-desktop` → `dmg-macos` on `self-hosted-macos` → `sign-macos-dmg` on
   `arc-persona-forge-desktop` → `verify-macos` on `self-hosted-macos`. When `sign` is false, the
   Phase 4 behavior stays. The signing jobs run only for `workflow_dispatch` and `workflow_call`
   (never `pull_request`).
4. `verify-macos` (no secrets; all must pass): `xcrun stapler validate` on the `.app` (unzipped
   with `ditto -x -k`) and the DMG; `codesign --verify --deep --strict --verbose=2` and `spctl
   --assess --type execute --verbose=4` on the `.app`; `spctl --assess --type open --context
   context:primary-signature --verbose=4` on the DMG; `codesign -dv --verbose=4` on the main
   binary, `uv`, `Sparkle.framework` and each nested bundle, asserting every `TeamIdentifier`
   equals the Team ID output from `sign-macos-app`. rcodesign #169: a stapling step that exits 0
   is not proof; only `stapler validate` counts.
5. `src/translocation.rs` (macOS only), per §6.9:
   - Detection: the bundle path starts with `/private/var/folders/` and contains
     `/AppTranslocation/`, **or** `statfs` reports `MNT_RDONLY` for the bundle's volume.
   - On accept: `ditto` the bundle to `/Applications/Persona Forge.app`. If that fails with
     EACCES, use `~/Applications/`. Then `xattr -dr com.apple.quarantine` on the **copy**,
     `open -n <copy>`, and exit.
   If the destination already exists, ask "Replace existing Persona Forge?" first.
   On decline: continue, and set a flag that Phase 6A uses to disable update checks.
6. `smoke-macos` runs on the signed DMG when `sign` is true.

### Gate 5

```bash
gh workflow run desktop-build.yml --ref desktop/p5-macos-signing -f version=0.0.0-p5test -f sign=true
gh run watch <run-id>
```

Pass: the macOS build and smoke jobs are green, and the verify-step output is pasted into the PR.

**OWNER** (OA-7): on the Mac (macOS 26), ideally in a second, clean user account, download the artifact DMG
through a browser (quarantine), turn Wi-Fi off, open the DMG, drag to Applications, and launch.
Record the Gatekeeper dialog text; there must be no "cannot be checked for malicious software".
Also launch directly from the mounted DMG, confirm the translocation prompt appears, and accept
it. Confirm the relaunched app runs from `/Applications`.

**Stop condition:** notarization rejects the bundle, per the log fetched with `rcodesign
notary-log`. Attach the log and stop.

PR title: `ci(desktop): sign, notarize and staple the macOS app and DMG`, plus
`feat(desktop): offer to move a translocated app to Applications` in the override block.

---

## Phase 6A — Updater client plumbing (shell side; no feeds yet)

### Objective

The shell can check for, download, verify, consent to, and install updates through Sparkle
(macOS) and `tauri-plugin-updater` (Windows/Linux), including the test-only `--ci-update`
driver (contract §6.12). No feed generation and no e2e in this phase: a check against the
production feed must safely end in "no update" (contract §9.1's 404 path), because no desktop
feeds exist until Phase 6B.

### Read first

- Contract §6.12, §9 (§9.3 client behavior), D3, D12, D13, D19. Phase 1A/1B/1C results. OA-3
  and OA-4 public keys.
- The `desktop-spike-final` tag (the spike's `--ci-update` code; the path is recorded in
  `## Phase 1 results`; Phase 6A ports the client side, Phase 6B reuses the Windows
  install-wait logic).
- The pinned `tauri-plugin-sparkle-updater` and `tauri-plugin-updater` docs.

### Files (client side)

- `desktop/Cargo.toml`: add a feature `ci-hooks = []` (contract §6.12, off by default) and
  `src/ci_hooks.rs` behind `#[cfg(feature = "ci-hooks")]`, ported from the spike code at the
  `desktop-spike-final` tag. `args.rs` accepts `--ci-update` only with that feature. Add
  `tauri-plugin-updater` under
  `[target.'cfg(not(target_os = "macos"))'.dependencies]` and `tauri-plugin-sparkle-updater`
  under `[target.'cfg(target_os = "macos")'.dependencies]`, both pinned `=`.
- `desktop/tauri.conf.json`: `plugins.updater.pubkey` (OA-3 public),
  `plugins.updater.endpoints` [`<FEED_BASE>/latest.json`], `plugins.updater.windows.installMode`
  "passive". `bundle.createUpdaterArtifacts` stays **false**: `.sig` files come from the
  `updater-sigs` job (contract §8), so builds never need the private key.
- `desktop/tauri.macos.conf.json`: `bundle.createUpdaterArtifacts` false. Sparkle framework
  embedding per the plugin docs.
- `desktop/Info.plist`: `SUPublicEDKey` (OA-4 public), `SUFeedURL` `<FEED_BASE>/appcast.xml`,
  `SUEnableAutomaticChecks` true, `SUScheduledCheckInterval` 86400,
  `SUAutomaticallyUpdate` false, `LSMinimumSystemVersion` 14.0.
- Feed base selection (no `build.rs` logic): the workflow input `feed_base` (empty = production
  `https://github.com/nmorgowicz-org/persona-forge/releases/latest/download`) is applied at build
  time in two places. The Tauri endpoint goes in through `cargo tauri build --config
  '{"plugins":{"updater":{"endpoints":["<base>/latest.json"]}}}'`. On macOS, the new script
  `scripts/set_feed_base.py --plist desktop/Info.plist --base <base>` rewrites `SUFeedURL` with
  `plistlib` in the CI checkout before the build. The committed `Info.plist` always holds the
  production URL.
- `desktop/src/updates.rs`: the "Check for Updates…" menu, tray item, a 24 h timer, and the
  consent dialog (§9.3). Before `install()`, run the Stopping sequence (server down). On macOS,
  hand everything to Sparkle, and hook Sparkle's will-relaunch or app termination into the
  Stopping sequence. Disable checks when the §6.9 decline flag is set.

### Tests first (6A)

- `args.rs`: `--ci-update x.json` **without** the `ci-hooks` feature → exit code 2 (extends the
  Phase 3 test); with the feature, the argument parses and reaches the updater driver.
- `ci_hooks.rs`: the `out.json` shape serializes with all fields (`ok`, `phase`,
  `from_version`, `to_version`, `error`).

### Gate 6A

```bash
cargo fmt --manifest-path desktop/Cargo.toml --check
cargo clippy --manifest-path desktop/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path desktop/Cargo.toml
python scripts/validate_repo.py && git diff --check
```

Plus, on the Mac (implementer): a local unsigned release build
(`cargo tauri build --no-sign --bundles app --target aarch64-apple-darwin`), launch it, run
"Check for Updates…" against the production feed URL, and record that Sparkle reports "no
update" (the feeds do not exist yet) and the app stays responsive.

PR title: `feat(desktop): add Sparkle and Tauri updater plumbing with a test-only update driver`

---

## Phase 6B — Update feeds, signing jobs, and end-to-end update gates

### Objective

Feed generation, the `updater-sigs` signing job, `ci_hooks` build wiring, the e2e workflow, and
the good/badsig gate procedure proving N→N+1 on every OS through test feeds before anything
points at `releases/latest`.

### Read first

- Contract §6.12, §8, §9.1, §9.2, §12, D12, D19. Phase 6A merged. OA-3/OA-4 secrets must exist.
- The `desktop-spike-final` tag: the Windows install-wait logic (registry polling) proven in
  Phase 1B task 4.

### Files (feeds, build wiring, e2e)

- `scripts/generate_update_feeds.py`, with tests in
  `tests/tier1_unit/test_generate_update_feeds.py`:

  ```text
  usage: generate_update_feeds.py --release-dir DIR --version X.Y.Z --tag TAG --repo OWNER/NAME
                                  --notes-url URL --sparkle-key-env SPARKLE_ED_PRIVATE_KEY
  ```

  - Uses the `openssl` binary named by the `OPENSSL` env var (default `openssl`). At start it
    signs and verifies a temp file with `-rawin`; if that fails it exits non-zero with "OpenSSL 3
    with Ed25519 -rawin support is required" (the macOS system `openssl` is LibreSSL).
  - Reads `PersonaForge-macos-aarch64.dmg` and computes its length and EdDSA signature. It builds
    the PKCS#8 PEM from the base64 seed (whitespace stripped, must decode to exactly 32 bytes;
    the prefix `302e020100300506032b657004220420` hex + seed, then base64-wrap) and signs with
    `openssl pkeyutl -sign -rawin`. The key material goes to a `0600` temp file that is deleted
    in `finally`, never onto argv.
  - Reads the `.sig` contents for the Windows and Linux assets.
  - Writes `appcast.xml` and `latest.json` into `--release-dir`, with exact asset URLs
    `https://github.com/<repo>/releases/download/<tag>/<asset>`.
  - It fails closed on any missing asset, empty signature, or version mismatch.
  - Tests (never skipped; a missing capable OpenSSL is a test failure, not a skip):
    - generate a throwaway Ed25519 key with `$OPENSSL` inside the test
    - check the appcast signature verifies with `$OPENSSL pkeyutl -verify`
    - `latest.json` validates against the required keys (contract §9.1), and the version in
      `latest.json` matches the appcast
    - each missing asset raises an error
    - no key material appears in stdout, stderr, or the generated files
- `desktop-build.yml`: add the `updater-sigs` job (contract §8) when `inputs.sign` is true:
  on `arc-persona-forge-desktop`, with `TAURI_SIGNING_PRIVATE_KEY(_PASSWORD)`, download the
  renamed setup exe and AppImage and run `cargo tauri signer sign` on each, uploading the
  `.sig` files in the same artifacts. `ci_hooks: true` adds `--features ci-hooks` to the Windows
  and Linux builds. A release call never sets `ci_hooks`.
- Release-artifact guard: when `ci_hooks` is false, the smoke scripts also run the built app with
  `--ci-update $RUNNER_TEMP/x.json` and assert **exit code 2** (contract §6.12; the Windows
  script uses `Start-Process -Wait -PassThru`).
- Replace the `desktop-update-e2e.yml` stub (inputs fixed in Phase 0: `n_run_id`, `n1_run_id`,
  `mode` = `good` | `badsig`). Top-level `permissions: contents: read`. Jobs:
  - `publish-feeds` on `arc-general`, job `permissions: contents: write`, `GH_TOKEN: ${{
    github.token }}`, secret `SPARKLE_ED_PRIVATE_KEY`: download N+1's artifacts from run
    `n1_run_id` (`gh run download`). For `good`: run `generate_update_feeds.py --tag
    desktop-updater-test` and upload the DMG, setup exe, AppImage, `.sig` files and both feeds to
    `desktop-updater-test` with `gh release upload --clobber`. For `badsig`: flip one byte in each
    of the three assets, write `latest.json` with the **original** signatures and `appcast.xml`
    with a deliberately wrong `edSignature`, and upload all of it to `desktop-updater-badsig`.
  - `e2e-linux` on `arc-persona-forge-desktop` and `e2e-windows` on `self-hosted-windows` (no
    secrets), after `publish-feeds`, each with a fresh `PERSONA_FORGE_HOME`, using N's artifacts
    from run `n_run_id`:
    - install N (Windows: silent NSIS `/S` via `Start-Process -Wait -PassThru`; Linux: copy the
      AppImage) and run `--smoke-test` so the `90.0.1` env exists
    - run N with `--ci-update out.json`
    - Linux: `good` → `ok: true`, `phase: "installed"`, `to_version: "90.0.2"`; `badsig` →
      `ok: false`, `phase: "verify"`, and a second `--smoke-test` still reports `version`
      `90.0.1` (the product has no `--version` flag)
    - Windows `good`: `out.json` has `phase: "installing"`; then poll the uninstall registry
      entry until `DisplayVersion` is `90.0.2` (at most 120 s, fail closed) and stop any app
      instance the installer relaunched. Windows `badsig`: `ok: false`, `phase: "verify"`, and
      `DisplayVersion` stays `90.0.1`
    - `good` only: run the installed app with `--smoke-test`; assert `version` is `90.0.2` and
      `<PERSONA_FORGE_HOME>/launcher/versions/` holds exactly `90.0.1` and `90.0.2` (D14)
    - Windows: uninstall in `finally`

### Update gate procedure

Runs, in order (the owner creates the two pre-releases first, OA-8):

1. Versions: plain `90.0.1` (N) and `90.0.2` (N+1). Semver pre-release suffixes compare
   differently in Sparkle and Tauri, and `90.x` never collides with real releases.
2. `desktop-build.yml --ref desktop/p6-updates` three times, all with `sign=true`:
   - run A: `version=90.0.1`, `ci_hooks=true`,
     `feed_base=https://github.com/nmorgowicz-org/persona-forge/releases/download/desktop-updater-test`
   - run B: `version=90.0.2`, `ci_hooks=false`, same `feed_base` (N+1; its own feed setting is
     irrelevant)
   - run C: `version=90.0.1`, `ci_hooks=true`,
     `feed_base=https://github.com/nmorgowicz-org/persona-forge/releases/download/desktop-updater-badsig`
3. `desktop-update-e2e.yml --ref desktop/p6-updates -f n_run_id=<A> -f n1_run_id=<B> -f
   mode=good`. Both e2e jobs must pass.
4. `desktop-update-e2e.yml --ref desktop/p6-updates -f n_run_id=<C> -f n1_run_id=<B> -f
   mode=badsig`. Both e2e jobs must show the update **rejected**.
5. **OWNER** on the Mac (clean install of run A's DMG into `/Applications`), and once on the
   Windows 11 PC through the real GUI (run A's setup exe): launch N, choose Check for Updates,
   install. Expected:
   - the server stops cleanly (no `persona_forge.app:app` process in the gap)
   - the app relaunches at N+1 (About shows it)
   - the splash provisions the new env version, and the SPA loads with the same theme (D17)
   - `<app_data_root>/launcher/versions/` contains exactly `90.0.1` and `90.0.2`
6. **OWNER** on the Mac: install run C's DMG, Check for Updates, and confirm Sparkle refuses the
   update with a signature error.
7. The owner deletes both pre-releases afterwards.

### Gate 6B

```bash
cargo test --manifest-path desktop/Cargo.toml
OPENSSL=$(command -v openssl) PYTHONPATH=src:src/export uv run --frozen python -m pytest tests/tier1_unit/test_generate_update_feeds.py -v -rs
python scripts/validate_repo.py && git diff --check
```

Plus the URLs of runs A, B, C and both `desktop-update-e2e.yml` runs, the owner's macOS and
Windows results, and all negative tests showing rejection. The pytest output must show zero
skipped tests. (On the Mac, set `OPENSSL=/opt/homebrew/bin/openssl`.)

**Stop conditions:**

- A good update fails to install on macOS through Sparkle, or the app freezes for more than 2 s
  in the UI during download.
- A bad signature **is** installed on any platform. This is a security stop. Do not merge.

PR title: `feat(desktop): signed update feeds and automated update gates`

---

## Phase 7 — Release integration and documentation

### Objective

Every published release ships the desktop artifacts and feeds, validated by the release contract,
alongside the existing CLI archives. Update the active docs.

### Read first

- `.github/workflows/release-launcher.yml`, `scripts/validate_release_contract.py` and its
  tests, `scripts/validate_docs_semantics.py` (the `ACTIVE_DOCS` list and banned phrases),
  `renovate.json`.
- Contract §8, §9.1, §12, §13, D19.

### Tasks

1. In `release-launcher.yml`:
   - add a `version` job (on `arc-general`, no secrets) that outputs the `pyproject.toml`
     `[project].version` (the same one-liner the "Package launcher archive" step uses)
   - add `desktop: uses: ./.github/workflows/desktop-build.yml` with `needs: [build-wheel,
     version]`, `with: {version: ${{ needs.version.outputs.version }}, sign: true,
     wheel_artifact: wheel-and-sdist}` and `secrets: inherit`. The desktop jobs download that
     artifact instead of building a second wheel; one wheel per release.
   - the `release` job `needs:` gains `desktop`, and it downloads the desktop artifacts into
     `release/`.
   - the `release` job step order becomes: download artifacts → determine release version →
     `generate_update_feeds.py` (with `SPARKLE_ED_PRIVATE_KEY`; the `release` job already runs on
     the ephemeral `arc-general`, D19) → generate SHA-256 checksums (so the feeds are covered) →
     validate release contract → publish.
2. `validate_release_contract.py`: add the desktop assets to `expected_assets()`:
   - `PersonaForge-macos-aarch64.dmg`, `PersonaForge-windows-x86_64-setup.exe` +
     `.sig`, `PersonaForge-linux-x86_64.AppImage` + `.sig`,
     `appcast.xml`, `latest.json` (no Linux `.deb`, contract D8)
   - new checks: `latest.json` version == release version; every `platforms.*.url` ends with an
     existing asset name and every `signature` equals that asset's `.sig` contents; the appcast
     `sparkle:version` == release version and the enclosure length == DMG size
   - tests: positive, a missing desktop asset, a version mismatch, a signature mismatch
3. Documentation:
   - `README.md`: an "Install the desktop app" section (macOS DMG; Linux AppImage "preview" with
     the GNOME AppIndicator note; Windows preview with the note below). The CLI archive stays
     documented as the headless option. Windows note, near the top of the Windows install steps
     (owner, 2026-09-25: no code-signing certificate will be bought):

     > **Windows: the installer is not code-signed.** Windows SmartScreen will show "Windows
     > protected your PC". Click **More info → Run anyway**. This allows only this installer; you
     > do not need to turn SmartScreen off. The same prompt can appear after an update.
     >
     > If **Smart App Control** is on, Windows blocks unsigned apps with no "Run anyway" option.
     > To install, turn it off in Windows Security → App & browser control → Smart App Control
     > settings → Off. On some Windows versions it cannot be turned back on without resetting
     > Windows, so decide before you switch it off.
   - `docs/HOW_TO_RUN.md` and `docs/RUN_LOCAL.md`: a desktop-app path.
   - `docs/architecture/DESKTOP_APP.md` (new, active): a condensed, current version of the
     contract's §4, §6, §7, §9 and the troubleshooting list below. Add it to `docs/README.md`.
     Add it to `ACTIVE_DOCS` in `validate_docs_semantics.py` only if that script's structure
     requires listing it (read the script).
   - Troubleshooting in `DESKTOP_APP.md`: a blank window on NVIDIA/Wayland
     (`WEBKIT_DISABLE_DMABUF_RENDERER=1`); no tray on GNOME (the AppIndicator extension); Windows
     SmartScreen/SAC on the preview; where the logs are; changing or resetting the port (Settings,
     or delete `port` from `settings.json`); the firewall prompt that names Python when network
     access is turned on, and how to allow it afterwards (Windows Defender Firewall "Allow an app";
     macOS System Settings → Network → Firewall → Options); running the CLI and the desktop app
     on the same port at the same time is refused.
   - `docs/api/HTTP_API_REFERENCE.md`: a short "Connecting other tools" note: the OpenAI base URL
     is `http://<host>:<port>/v1`, shown in the desktop app's Settings window.
   - `docs/TEST_STRATEGY.md`: the desktop lanes (`ci-desktop.yml`, `desktop-build.yml` smoke,
     owner acceptance).
   - `AGENTS.md` quick orientation: add a `desktop/` line and a pointer to `DESKTOP_APP.md`.
   - `scripts/package_launcher_archive.py` `README_TEMPLATE`: one line pointing desktop users to
     the desktop assets. Update its test if the test asserts the template text; per repo rules,
     delete wording-pinning asserts rather than re-pinning them.
4. Renovate: confirm the existing cargo rule (`automerge: false` for every cargo dependency)
   covers `desktop/Cargo.toml`, and that the `RUST_VERSION` regex manager includes
   `ci-desktop.yml` and `desktop-build.yml` (added in Phases 2 and 4). No new rule is needed
   unless one of these checks fails.

### Gate 7

```bash
PYTHONPATH=src:src/export uv run --frozen python -m pytest tests/tier1_unit -q
uv run --frozen python scripts/validate_docs_semantics.py
python scripts/validate_repo.py && git diff --check
docker compose config --quiet
V=$(uv run --frozen python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
gh workflow run release-launcher.yml --ref desktop/p7-release -f tag_name="persona-forge-v$V" -f dry_run=true
gh run watch <run-id>
```

Pass: the full dry-run release is green: CLI archives, desktop builds, smokes, feeds,
checksums, and the contract validation over the complete asset set. Nothing is published. The
first real publication is the next Release Please release, and Phase 8 covers it.

PR title: `feat(release): publish signed desktop apps and update feeds with each release`

---

## Phase 8 — Owner acceptance, handoff, archive

### Acceptance matrix (OWNER, on the first real release that contains desktop assets)

On the Mac (macOS 26) and the Windows 11 PC. Linux is covered by the automated jobs in Phases
4 and 6 (contract D8); record their run URLs for this release instead.

- [ ] Install from the release page. Record any OS warning text verbatim.
- [ ] First run completes. The SPA works: Speak generates and plays audio; download → Save dialog.
- [ ] Contract §1 items 2, 4, 5, 7, 8 behave as specified (use the Phase 3 checklist).
- [ ] The next real release (N+1) is offered and installs through the in-app updater.
- [ ] Existing CLI-archive users: after installing the desktop app, their voices and projects
      appear (shared app-data root).
- [ ] Settings: fixed port and "Allow other devices on my network" work, and a tool on another
      machine can call `http://<ip>:<port>/v1/audio/speech`.
- [ ] Uninstall (drag to Trash / the Windows uninstaller) leaves user data in place.

### Handoff (in the final PR, per `AGENTS.md` "Agent handoff requirements", adapted)

```text
Source commit / release tag:
Desktop artifacts + sha256 (from checksums.json):
Tauri / plugin / Sparkle / process-wrap versions (Cargo.lock):
Runner images (digests) and labels used:
Phases completed / gates + run URLs:
Owner acceptance matrix results:
Known divergences from the contract (with the amendment commits):
Update-key custody confirmed (OA-3/OA-4 offline backups): yes/no
Rollback procedure (below) tested: yes/no
Follow-ups: Windows signing, API auth, macOS data-root migration, Linux aarch64, Tauri v3
```

### Rollback

- A bad desktop release: publish a fixed N+2. Updaters only move forward. Do not delete the
  release that has the bad assets until N+2 is live; deleting it makes `latest` point at an older
  release, and clients then see "no update".
- Stop shipping desktop entirely: revert the Phase 7 commit. The CLI archives are unaffected,
  because they are independent jobs. Installed desktop apps keep working and stop seeing updates
  (the feeds 404 → "no update").
- Key compromise: rotate per contract §9.2. For Sparkle, ship one release signed with the old
  Developer ID and a new EdDSA key, never both changed at once. For Tauri, installed apps trust
  only the embedded key, so a compromised minisign key needs an out-of-band notice to reinstall.

### Archive

Once acceptance passes, move both plan docs to `docs/archive/desktop-app/` and mark them
complete. `docs/architecture/DESKTOP_APP.md` remains the active reference.

---

## Appendix A — Update signing keys: owner walkthrough (OA-3, OA-4)

Two keys prove that an update really came from you. Installed apps carry the **public** half and
refuse any update not signed with the matching **private** half.

- **If a private key is lost:** installed apps can never auto-update again. Every user has to
  download and reinstall by hand once, to get an app that trusts a new key.
- **If a private key leaks:** someone who can also get a file into your GitHub release (or trick
  the app's download) could push a malicious update. Both are needed, which is why the key is a
  second lock on top of GitHub access.
- **Public keys are not secret.** They get committed into `desktop/tauri.conf.json` and
  `desktop/Info.plist`.

Run everything below on your Mac, in Terminal. It takes about ten minutes.

### A1. A private folder

```bash
mkdir -m 700 ~/.persona-forge-keys
cd ~/.persona-forge-keys
```

### A2. Tauri updater key (Windows and Linux updates)

```bash
npx --yes @tauri-apps/cli@2 signer generate -w ~/.persona-forge-keys/tauri-updater.key
```

It asks for a password twice. Make a strong one and save it in the Passwords app as "Persona
Forge — Tauri updater key password". This creates `tauri-updater.key` (private) and
`tauri-updater.key.pub` (public).

### A3. Sparkle key (macOS updates)

Use Homebrew's OpenSSL 3. The `/usr/bin/openssl` that ships with macOS is LibreSSL and is not
used here. This exact recipe was checked on this Mac with OpenSSL 3.6.4 on 2026-09-25, including
a sign-and-verify round trip.

```bash
OPENSSL=/opt/homebrew/bin/openssl
$OPENSSL genpkey -algorithm Ed25519 -outform DER -out sparkle_ed.der
tail -c 32 sparkle_ed.der | base64 > sparkle_ed_private_seed.b64
$OPENSSL pkey -in sparkle_ed.der -inform DER -pubout -outform DER | tail -c 32 | base64 > sparkle_ed_public.b64
wc -c sparkle_ed_private_seed.b64 sparkle_ed_public.b64   # each must be 45 (44 characters + newline)
chmod 600 ~/.persona-forge-keys/*
```

`generate_update_feeds.py` strips surrounding whitespace from the seed, so the trailing newline
is harmless.

### A4. Put the private keys into GitHub (repository secrets)

```bash
cd ~/SCRIPTS/CLAUDE/persona-forge
gh secret set TAURI_SIGNING_PRIVATE_KEY < ~/.persona-forge-keys/tauri-updater.key
gh secret set TAURI_SIGNING_PRIVATE_KEY_PASSWORD      # it prompts; paste the A2 password
gh secret set SPARKLE_ED_PRIVATE_KEY < ~/.persona-forge-keys/sparkle_ed_private_seed.b64
gh secret list                                        # the three names must appear
```

Reading from a file or a prompt keeps the secret out of your shell history. Never use `--body`
with a private key.

Then give the implementer the two **public** keys (safe to paste anywhere):

```bash
cat ~/.persona-forge-keys/tauri-updater.key.pub ~/.persona-forge-keys/sparkle_ed_public.b64
```

### A5. Backups

1. **Time Machine:** confirm your backups are encrypted (System Settings → General → Time
   Machine → select the disk → Options; it must say the backup is encrypted). An unencrypted
   backup disk holds the private keys in readable form. If it is not encrypted, rely on step 2.
2. **Email copy, encrypted first.** Never email the raw key files: they would sit readable in
   your mailbox, and anyone who gets into that account gets the keys. Wrap them in an encrypted
   disk image instead:

   ```bash
   hdiutil create -encryption AES-256 -srcfolder ~/.persona-forge-keys -format UDZO ~/Desktop/persona-forge-keys.dmg
   ```

   It asks for a password. Use a **different** strong password, save it in the Passwords app as
   "Persona Forge — key backup image", and never put it in the same email. Email
   `persona-forge-keys.dmg` to yourself, then delete the Desktop copy.
3. **Test the restore once:** download the attachment, double-click it, enter the password, and
   check that the five files are there (`tauri-updater.key`, `tauri-updater.key.pub`,
   `sparkle_ed.der`, `sparkle_ed_private_seed.b64`, `sparkle_ed_public.b64`).

Keep `~/.persona-forge-keys/` on the laptop. CI only needs the GitHub secrets; the local folder
plus the two backups are how you recover if a secret is ever deleted.

### A6. Rules

- Never commit anything from `~/.persona-forge-keys/` except the **public** key values, which the
  implementer copies into config files.
- Never paste a private key or its password into chat, an issue, a PR, or a log.
- Replacing a key later: Sparkle allows changing either the Sparkle key or the Apple Developer ID
  certificate in one release, never both at once. A new Tauri key needs every Windows and Linux
  user to reinstall once, so avoid it unless the old key leaked.

---

## Phase 0 results

Recorded 2026-09-25. Gate 0 runs: 36186476248 (initial; Windows job mis-fired on WSL bash),
36186911975 (custom-shell quoting attempt), **36187051719 (valid run, evidence below)**.
Two workflow fixes rode along on `desktop/p0-results`: `shell: bash` resolves to WSL's
`C:\WINDOWS\system32\bash.EXE` (no distro installed) on `self-hosted-windows`, so the preflight
is now invoked via PowerShell calling Git Bash explicitly, with the exit code propagated.

### Preflight — `self-hosted-macos` (run 36187051719, job `preflight-macos`: green)

- macOS 26.5.1 (BuildVersion 25F80), Apple Silicon — D6's arm64 build-host assumption holds;
  no Gate 0 stop condition.
- `rustc`/`cargo` 1.98.0; rustup targets `aarch64-apple-darwin`, `x86_64-pc-windows-gnu`;
  `python3` 3.14.7; `uv` 0.12.12 (warn-only check).
- `xcode-select -p` → Xcode 26.6.0; `hdiutil`, `codesign`, `spctl`, `xcrun stapler` all present.
- Free disk on `$RUNNER_TEMP`: 980 GB (>= 10 GB).
- **0 missing.** OA-6 macOS items: already satisfied.

### Preflight — `self-hosted-windows` (job `preflight-windows`: failed with the precise
missing-tool list, which is Gate 0's documented pass path)

Present: VS 2022 BuildTools with VC.Tools.x86.x64 (`vswhere` → `C:\Program Files (x86)\Microsoft
Visual Studio\2022\BuildTools`), Windows SDK 10.0.26100.0, WebView2 Evergreen runtime registry
entry. Missing (→ **OA-6 Windows task**):

1. `rustc`, `cargo`, `rustup` — rustup is not installed on the runner. Install rustup with the
   `x86_64-pc-windows-msvc` host and toolchain `1.98` (matching `release-launcher.yml`'s
   `RUST_VERSION`).
2. `python3` — no `python3` on Git Bash's PATH. Either install Python 3.13 so `python3`
   resolves inside Git Bash, or (simpler) relax the all-OS check to accept `python` on
   Windows — decide at install time; the desktop lane itself only needs `uv run python` and
   the venv's own interpreter.

### Runner-label probe — `arc-llama-monitor` (green)

`Linux ... 6.8.0-142-generic x86_64`, `PRETTY_NAME="Ubuntu 26.04 LTS"`, glibc **2.43**
(`ldd` 2.43-2ubuntu2). Confirms contract §11's "shared runner image is Ubuntu 26.04" and its
use as the newest-distro smoke target.

### Preflight — `arc-persona-forge-desktop`

Not run: the scale set does not exist until Phase 0R. Both valid runs were cancelled after the
other jobs finished (Gate 0's documented handling). This job must go green at Gate 0R.

### Secret presence and scope (2026-09-25, `gh secret list`, no values)

| Secret | Scope |
| --- | --- |
| `APPLE_ISSUER_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY`, `MACOS_CERT_PEM`, `MACOS_KEY_PEM` | org, SELECTED repos |
| `GH_APP_PRIVATE_KEY` | org ALL + repo copy |
| `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` | repo |
| `SPARKLE_ED_PRIVATE_KEY`, `TAURI_SIGNING_PRIVATE_KEY(_PASSWORD)` | **not present yet** — created at OA-3/OA-4 (Appendix A), before Phase 1 |

SELECTED scope means this repo's inclusion cannot be proven from `gh secret list` alone; the
Phase 1A signing jobs will prove it (a permission error there is recorded as-is per Phase 0
task 6).

### Open OA items after Phase 0

- **OA-6 Windows half**: rustup (msvc host, toolchain 1.98) + the `python3` decision above.
- **OA-3 / OA-4**: update signing keys (Appendix A) — before Phase 1.
- **OA-5**: Phase 0R paired session — next in strict sequence.
- **OA-7 / OA-8**: test machines / spike pre-releases — needed at Phases 1 and 6.

### Workflow stubs on `main`

`desktop-preflight.yml`, `desktop-build.yml`, `desktop-update-e2e.yml`, `desktop-spike.yml` all
exist on `main` (PR #328) and are dispatchable (`gh workflow list` shows all four).
