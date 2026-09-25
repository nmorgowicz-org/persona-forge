# Native App Shell + Auto-Update — Execution Plan

Status: **draft — planning only, expect several revisions before Phase 0 begins**

> This document intentionally follows the repo's "phases + gates" execution-plan format
> (`docs/archive/no-docker/20260829-no_more_docker_requirement.md`), not the lighter
> `docs/plans/20260924-audiodeck_decomposition.md` style, because this initiative changes a
> released, signed, user-facing artifact (the launcher) and needs the same fail-closed gate
> discipline that the no-Docker migration used. Unlike that migration, this plan has **no separate
> architecture-contract doc** yet — the "Options considered" and "Recommendation" sections below
> serve that role until/unless the owner wants them split out after the spike.

**Baseline:** `87d6547` (post PR #326 — macOS launcher signing/notarization/deployment-target fix,
fully verified live in run `36139559115`).
**Target:** a `PersonaForge.app` (macOS), `PersonaForge.exe`/installer (Windows), and an
equivalent Linux artifact, each of which (a) is a real app shell instead of a bare CLI binary the
user double-clicks and watches open a browser tab, (b) can staple a notarization ticket on macOS
(closing the "no stapling for bare executables" gap noted in
`docs/archive/macos-code-signing/20260918-macos_code_signing.md`), and (c) can check for and
install newer releases itself, tying back to the existing GitHub Releases pipeline
(`.github/workflows/release-launcher.yml`).

## Current state (read first)

- **Two install paths exist today:** a Docker/Compose deployment, and the native thin-launcher
  archive from Phase 7 of the no-Docker migration (`launcher/src/{main,bootstrap,manifest,paths}.rs`,
  761 lines total). Neither is a desktop "app" — the launcher is a CLI binary
  (`persona-forge-launcher serve`) that starts a Flask server and the user opens a browser tab to
  `localhost`. This plan only concerns the native-launcher path; Docker is out of scope.
- **The launcher has no update mechanism.** To update, the README tells users to download a new
  release archive and re-run its launcher (`scripts/package_launcher_archive.py` README template,
  lines 58-61). No in-app check, no notification, no self-replace.
- **macOS signing/notarization is done but incomplete by design.** `rcodesign sign
  --for-notarization` + `rcodesign notary-submit --wait` + `rcodesign verify` run in
  `release-launcher.yml` today (`build-launcher` job, gated on
  `matrix.target == 'aarch64-apple-darwin'`). There is deliberately **no staple step** — Apple only
  supports stapling a notarization ticket to `.app`/`.pkg`/`.dmg`, never a bare Mach-O executable
  (`docs/archive/macos-code-signing/20260918-macos_code_signing.md` lines 137-139, 281-283). Today's
  binary relies on Apple's online Gatekeeper check on first launch. A real `.app` bundle removes
  this online-check dependency.
- **Windows and Linux have no code signing at all today.** Only macOS has certificates/secrets
  provisioned (`MACOS_KEY_PEM`, `MACOS_CERT_PEM`, `APPLE_ISSUER_ID`, `APPLE_KEY_ID`,
  `APPLE_PRIVATE_KEY`, all org-level secrets shared with `local-llm-foundry`). Windows builds today
  produce an unsigned `.exe` that will show a SmartScreen "unknown publisher" warning; the owner
  should decide whether Authenticode signing is in scope now or deferred before this plan's later
  phases assume either way — see "Open questions for the owner" #5.
- **The frontend is React 19 + Vite, built to static `dist/`, served by Flask at `/`**
  (`docs/architecture/FRONTEND_OVERVIEW.md`). No router; page switch is a zustand store field. Any
  native shell wraps this existing static build rather than rebuilding UI.
- **CI already cross-builds all four target triples on one runner.** Both persona-forge
  (`release-launcher.yml`) and the sibling project `local-llm-foundry` (`release.yml`) build
  `x86_64-unknown-linux-gnu`, `aarch64-unknown-linux-gnu`, `x86_64-pc-windows-gnu`, and
  `aarch64-apple-darwin` on the same `arc-llama-monitor` self-hosted runner via osxcross/cross-rs.
  persona-forge's matrix currently only builds three of these four (no `aarch64-unknown-linux-gnu`);
  see "Open questions for the owner" #4.
- **`local-llm-foundry` already ships a tray icon + popover webview + self-update binary on this
  exact toolchain, today, in production** — but per the project owner (2026-09-25) it is "still
  just a webapp" with a tray icon, not yet a first-class native app experience, and its
  `release.yml` has **no code-signing workflow of any kind** (confirmed via grep — no rcodesign,
  notarytool, codesign, or Authenticode references). The owner's stated longer-term intent is that
  *both* projects eventually move toward a more first-class, non-browser feel, but neither has yet.
  This is still the single most important piece of prior art for this plan (its self-update
  mechanism and its tray/webview cross-compile story are both real, working code) — it just isn't
  a template to copy wholesale for "what a finished app should feel like," and this plan's Phase 3
  would be the first attempt in the org to push meaningfully past where local-llm-foundry currently
  stops.

## Options considered

Four approaches were evaluated for "what wraps the launcher into a real, auto-updating app."

### Option A — Tauri

Rust host process + OS-native webview (via `wry` under the hood) + a JS/TS frontend, with a
"sidecar" mechanism for spawning a bundled backend process (our existing Flask server, unchanged).

- **Pros:** Mature, widely used in 2026 for exactly this shape of app (thin native shell around a
  web frontend + local backend); `tauri-plugin-updater` is purpose-built for this — it reads a
  signed update manifest (Ed25519/minisign signatures, not Apple/Microsoft code-signing) and can
  point at GitHub Releases directly; official bundler produces `.app`/`.dmg`, `.msi`/`.exe`, and
  `.deb`/`.AppImage` outputs with an installer builder built in; large ecosystem/docs/community
  support for the signing+notarization+stapling flow specifically (Tauri's own docs document
  `rcodesign`-style flows and, via `tauri-apple`, entitlements/hardened-runtime out of the box).
- **Cons:** New framework dependency the org has no existing production usage of — this would be
  the first Tauri app in this GitHub org. Node/Cargo build surface grows (Tauri CLI, its own plugin
  ecosystem, `tauri.conf.json`). Cross-compiling a full Tauri app (not just a bare Rust binary) from
  the Linux `arc-llama-monitor` runner for macOS via osxcross is unproven — Tauri's macOS bundling
  step (codesigning + `.app` structure + `Info.plist` generation) is typically documented for a
  native macOS build host; whether it cross-compiles cleanly through osxcross the way our current
  bare-binary launcher does is an open, spike-worthy question (see Phase 0).

### Option B — Electron + electron-builder/electron-updater — ruled out

- **Pros:** `electron-updater` has a first-class GitHub Releases provider requiring the least glue
  of any option here — point it at the repo and it handles feed generation, download, and staged
  install. Extremely well trodden path in 2026 for exactly this use case (this is what LM Studio
  ships). Ships its own Chromium/Node runtime, so no OS-webview version-fragmentation bugs to chase
  across old macOS/Windows/Linux webview builds.
- **Cons:** Heaviest option by far — bundles its own Chromium (~150-200MB uncompressed per
  platform), which cuts directly against this launcher's whole reason for existing (a *thin*
  bootstrap that avoids bundling heavy runtimes — see `README_TEMPLATE` in
  `scripts/package_launcher_archive.py`: "It does not contain the Python runtime, large ML
  dependency wheels..."). Also a new framework with zero production precedent in this org.
- **Ruled out by the project owner (2026-09-25):** Electron's memory/bloat reputation is a
  dealbreaker regardless of its updater convenience — not being carried into Phase 0's spike scope.
  Kept in this document only as a record of why it was considered and rejected, not as a live
  option for the spike.

### Option C — `wry` + `tray-icon` direct (no wrapper framework) — the `local-llm-foundry` pattern

`local-llm-foundry`'s `llama-monitor` binary (Cargo features `native-tray = ["dep:tray-icon",
"dep:winit"]`, `webview-popover = ["dep:wry"]`; `wry = "0.57"` with `default-features = false,
features = ["os-webview"]`; `tray-icon = "0.25"`) implements a system tray icon plus an on-demand
popover webview directly against `wry`/`tray-icon`/`winit`, with no Tauri or Electron in between.
It **already has a working, shipped self-update mechanism**
(`local-llm-foundry/docs/archive/implementation/20260429-app_update_capability.md`):

- Reuses the *existing* GitHub-release-asset download/extract code path (`install` module in
  `src/agent.rs`) — no new update-manifest format, no new signing scheme beyond what already signs
  the release asset.
- Unix/macOS: download to a temp file in the *same directory* as the running executable (avoids
  `EXDEV` cross-device rename failures), `chmod 0o755`, then `std::fs::rename()` — atomic even
  while the old binary is still running, because the OS keeps the old inode mapped for the running
  process.
- Windows: in-place `.exe` replacement is blocked by the OS while the process is running, so it
  writes a detached `.bat` helper to `%TEMP%` that polls for the old PID to exit (`tasklist /FI`),
  `copy /Y`s the new binary in, relaunches, and self-deletes
  (`(goto) 2>NUL & del "%~f0"` trick), spawned with the Win32 `DETACHED_PROCESS` flag (`0x8`) so it
  survives the parent's exit.
- Frontend: version injected via HTML template substitution, an update-pill UI polls the existing
  `GET /api/.../releases/latest`-style endpoint, dismissal cached in `localStorage` with a 24h
  cooldown, `POST /api/self-update` triggers the swap and exits after a 600ms flush delay, frontend
  polls `HEAD /` to detect the relaunched server and reload.
- **Pros:** Already proven, in this org, on this exact CI runner and toolchain
  (`arc-llama-monitor`, osxcross), building the same four target triples persona-forge already
  targets. Smallest dependency footprint of the three GUI options (`wry` + `tray-icon` + `winit`
  only — no bundler framework, no plugin ecosystem, no Node build step for the shell itself).
  Closest in spirit to the existing "thin bootstrap" launcher philosophy — this is additive to
  `launcher/src/`, not a replacement of it.
- **Cons:** `local-llm-foundry`'s `release.yml` has **no code-signing or notarization at all today**
  (confirmed via grep — zero rcodesign/notarytool/codesign/MACOS_KEY_PEM references). Combining
  this pattern with full Apple notarization + `.app` stapling would be new, unproven work for this
  org, not a copy of an existing pattern — persona-forge would be first. No built-in "installer"
  concept (`.dmg`/`.msi`) — packaging a proper `.app` bundle structure (`Info.plist`,
  `Contents/MacOS/`, icon `.icns`) and `.dmg` would need to be hand-rolled or use a small
  purpose-built tool (e.g. `create-dmg`, or `rcodesign`'s own bundling helpers) rather than getting
  it "for free" the way Tauri's bundler provides it.

## Update mechanism options (orthogonal to the shell choice)

The shell choice (Options A-D above) and the *update mechanism* are separate decisions — a
Tauri, wry, or bare-CLI shell can each pair with different update machinery. Researched
2026-09-25 (not part of the original draft, added after the owner asked to reconsider against
current industry practice rather than defer entirely to the in-org precedent):

### Mechanism 1 — Reuse `local-llm-foundry`'s DIY approach (atomic rename / detached batch)

The mechanism described under Option C above: no signed update-manifest format of its own, just
re-downloads the same release asset already covered by this repo's existing signing/notarization,
verifies it, and swaps the binary in place (atomic `rename()` on Unix; detached-`.bat`-helper
relaunch on Windows).

- **Pros:** Zero new dependencies, zero new signing scheme, works identically for a bare CLI
  binary or a `wry`-shell binary, and is proven, shipped code in this org today.
- **Cons:** It is a hand-rolled mechanism, not an industry-standard one — no appcast, no delta
  updates, no phased rollout, no "critical update" flagging, and (per the production incident
  below) the naive in-process-replace-and-relaunch approach has a known real-world failure mode.

### Mechanism 2 — Sparkle (macOS) + WinSparkle (Windows), the de facto native-app standard

Sparkle is the standard self-update framework for non-App-Store macOS apps (used by countless
mature macOS apps); WinSparkle is its Windows counterpart, explicitly modeled on Sparkle's UX.
Both are appcast-based (an XML/RSS feed listing versions + signed download URLs) and both verify
updates with **EdDSA (Ed25519) signatures** — a real signature scheme, not just a checksum
(checksums alone prove integrity, not authenticity — a compromised distribution channel could
serve a checksummed-but-malicious binary; this is a specific point raised against DIY
checksum-only approaches in current write-ups).

- Sparkle does not require Xcode — it's a framework bundle (`Sparkle.framework`) plus an
  `SUFeedURL` key in `Info.plist`; a Rust binary can drive it via the `sparkle-updater` crate
  (wraps `Sparkle.framework` on macOS and `WinSparkle.dll` on Windows behind one API) or via direct
  FFI. This fits a `wry`-based (or bare-CLI-in-an-`.app`) shell without adopting Tauri.
- **A real production gotcha that's directly relevant here:** a Tauri app (socadb-desktop) found
  that `tauri-plugin-updater`'s default in-process install *blocks the app for 20-30 seconds*
  while the `.app` bundle is replaced, and switched to `tauri-plugin-sparkle-updater` specifically
  to move the install into Sparkle's out-of-process XPC helper and avoid that freeze. This is a
  concrete argument for Sparkle/WinSparkle over a naive in-process swap, independent of which
  shell option is chosen — worth explicitly testing for in Phase 2 (does our detached-process
  swap already avoid this, or does it have the same freeze?).
- **Another real gotcha:** Sparkle refuses to update an app running "translocated" (macOS's App
  Translocation — launched from the exact place it was downloaded/quarantined rather than moved to
  `/Applications`), and translocated launches were also observed triggering XProtect behavioral
  detection in one team's testing. Mitigation is a "move to Applications" prompt on first launch —
  worth adding regardless of update mechanism chosen, since it also affects Gatekeeper/staple
  behavior generally.
- WinSparkle's default mode fetches and launches a **signed installer package**, not an in-place
  `.exe` patch — different from the llama-monitor DIY approach's in-place swap. This is a real
  design fork for Windows specifically: if this plan wants a true installer-based Windows
  experience (more standard, cleaner uninstall/upgrade story) that's a bigger scope addition than
  reusing llama-monitor's detached-batch in-place-swap trick.
- **Cons:** New dependency (Sparkle/WinSparkle, or the `sparkle-updater` crate), a new signing
  keypair to generate and protect (EdDSA, separate from the Apple Developer ID / Authenticode
  identities already in play), a new appcast feed to host and keep in sync with GitHub Releases
  (unless a tool bridges the two — needs research in Phase 0), and unproven in this org (no
  existing usage to draw on, unlike Option C's shell).

### Recommendation on mechanism

Use **Phase 0's spike to answer this too**, not just the shell question — specifically: (a) whether
the llama-monitor-style detached-swap already avoids the 20-30s in-process-freeze problem Tauri hit
(if so, that's a point in its favor since it sidesteps Sparkle's main advantage for free), and (b)
how much work it is to generate a GitHub-Releases-backed appcast feed automatically as part of
`release-launcher.yml` (if trivial, Sparkle/WinSparkle's better signature scheme and native update
UI probably outweigh the extra dependency). Do not lock in the mechanism before Phase 0 reports
back — this is exactly the kind of "how do real 2026 apps do this" question the owner asked to
defer to research on, and the two production incidents above (blocking install, translocation
refusal) are the kind of thing only surfaces by testing, not by reasoning in the abstract.

### Option D — No GUI shell; self-update the existing CLI launcher only

Keep `persona-forge-launcher` exactly as it is (a CLI binary that starts a server and the user
opens a browser tab to), and only add: (1) self-update logic to the existing binary (same
atomic-rename/detached-batch pattern as Option C, without the tray/webview parts), and (2) wrap the
already-signed/notarized binary in a minimal `.app` bundle purely so it can be stapled — no tray
icon, no popover, no new UI surface.

- **Pros:** Smallest possible change. No new GUI dependencies at all. Directly closes the "no
  stapling for bare executables" gap with the least code. Self-update logic is a strict subset of
  Option C's already-proven pattern, so risk is lower still.
- **Cons:** Doesn't address the user's stated goal of "a proper Mac PersonaForge.app" in the fuller
  sense (dock icon, tray presence, no visible terminal/browser-tab UX) — it's a stapling+update fix
  dressed as an app, not a real desktop app experience. Likely a stepping stone rather than an end
  state if the user wants tray/menu-bar presence later.

## Recommendation

**Option C (`wry` + `tray-icon`, following `local-llm-foundry`'s shipped pattern) over Option A
(Tauri)**, revising the verbal recommendation given earlier in this conversation (which leaned
Tauri before the `local-llm-foundry` precedent was found). Reasoning:

1. It is proven, in production, in this org, on the exact CI runner and cross-compile toolchain
   persona-forge already depends on — Tauri's macOS bundling step through osxcross is an unknown
   that would need its own spike with a real chance of failure, whereas `wry`+`tray-icon` cross-
   compiling through that runner is already a settled fact.
2. It leaves the update *mechanism* undecided rather than coupling it to the shell framework —
   `local-llm-foundry`'s DIY atomic-swap approach is available for free, but so is layering
   Sparkle/WinSparkle on top of a `wry` shell if Phase 0 finds that's worth the extra dependency
   (see "Update mechanism options" above). Tauri, by contrast, couples you to its own
   minisign-signed-manifest updater by default (with Sparkle only available via a third-party
   bridge plugin) — one more framework opinion to either accept or fight.
3. It keeps the "thin bootstrap, no bundled heavy runtime" philosophy that motivated the launcher
   architecture in the first place (`docs/archive/no-docker/20260829-no_more_docker_architecture.md`
   §9); Tauri is close to this too, but pulls in a materially larger build/plugin surface for
   marginal benefit given #1 and #2.

Option D is not rejected — it is effectively **Phase 2 of Option C** (see phases below): get
stapling + self-update working on the existing CLI shape first, then layer tray/popover UI on top
once that is proven. This plan sequences it that way rather than as a separate competing option.

**The macOS notarization+stapling combination with a `wry`-based shell is new territory for this
org** (Option C's own con, restated): no existing project here has combined `wry`/tray-icon with
full Apple Developer ID signing + notarization + `.app` stapling — `local-llm-foundry`'s tray
binary ships unsigned today, and its tray+popover is itself a webapp-in-a-tray rather than a
first-class app shell. This is the primary reason a spike phase is first, not optional: Phase 0
must prove the signing/notarization/stapling combination works before this plan commits to it, and
should also record whether Phase 3's tray/popover shell is the right end state or whether the
"more first-class, non-browser feel" the owner described (2026-09-25) points toward something
further (e.g. a dedicated main window instead of a popover) — left as an open question below rather
than decided here, since neither project has gotten that far yet.

With Electron ruled out (Option B, above) and Tauri's org-precedent gap unresolved until Phase 0
reports back, Option C is the only approach with both a memory/footprint profile in line with the
owner's stated preference and a working reference implementation to adapt.

## Global constraints

- Never weaken or bypass the existing signed/notarized launcher binary pipeline in
  `release-launcher.yml` — new work wraps/extends it, does not replace working steps.
- No new secrets beyond what's already provisioned unless a phase gate proves they're required;
  reuse the org-level `MACOS_KEY_PEM`/`MACOS_CERT_PEM`/`APPLE_ISSUER_ID`/`APPLE_KEY_ID`/
  `APPLE_PRIVATE_KEY` secrets already shared between persona-forge and local-llm-foundry.
- Self-update must never run without the same signature/notarization verification the manual
  install path gets today — an auto-updated binary is not permitted to be less verified than a
  freshly downloaded one.
- All cross-compilation stays on `arc-llama-monitor`; no phase may introduce a dependency on the
  `self-hosted-macos`/`self-hosted-windows` runners for anything beyond the smoke-test role they
  already play.
- Every phase ships working, testable software on its own — no phase may leave `main` (or this
  branch, pre-merge) in a state where the existing launcher archive pipeline regresses.

## Worker protocol

(Mirrors `docs/archive/no-docker/20260829-no_more_docker_requirement.md` — repeated here so this
doc is self-sufficient.)

1. Work on a feature branch per phase, never directly on `main`.
2. Read every phase's "References to read completely" before editing that phase.
3. Gates are fail-closed: no `tail`-ing away failures, no discarding stderr, no turning a hardware
   gate into a "trust me" note. A hardware/signing gate (anything touching `rcodesign`,
   notarization, or a real macOS/Windows runner) must show real command output, not a simulated or
   cross-compiled substitute.
4. One phase per context/commit where practical; the spike phase (Phase 0) is explicitly allowed to
   span multiple throwaway commits/branches since its purpose is answering unknowns, not shipping.
5. Record exact commands, exit codes, and artifact locations in the PR description for each phase.

## Common verification commands

```bash
cd /Users/nick/SCRIPTS/CLAUDE/persona-forge
uv run --frozen python -m pytest tests/tier1_unit -q
cargo test --manifest-path launcher/Cargo.toml
gh workflow run release-launcher.yml -f tag_name=<test-tag>
gh run watch <run-id>
```

---

## Phase 0 — Spike: prove the chosen shell cross-compiles, signs, notarizes, and staples;
settle the update mechanism

### Objective

Before committing any of this plan's later phases, prove — with real CI runs on real runners, not
local approximation — that a `wry`+`tray-icon` binary built for `aarch64-apple-darwin` on
`arc-llama-monitor` can be: (a) wrapped in a minimal `.app` bundle, (b) signed with the existing
Developer ID certificate, (c) notarized, (d) **stapled** (the capability today's bare-binary
pipeline explicitly cannot use), and (e) launched on a real Mac with Gatekeeper showing no warning
and no network check on second launch (proving the staple, not just the online check, is what's
satisfied). This phase is throwaway-code-friendly: its deliverable is a written verdict plus
receipts, not production code.

This phase also settles the **update mechanism** question (see "Update mechanism options" above):
whether to reuse `local-llm-foundry`'s DIY atomic-swap approach, adopt Sparkle/WinSparkle, or some
hybrid — by testing for the two concrete failure modes real teams have hit (in-process install
blocking the app for 20-30s; Sparkle's refusal to update a translocated `.app`), not by reasoning
about it in the abstract.

### References to read completely

- `docs/archive/macos-code-signing/20260918-macos_code_signing.md` (full signing/notarization
  background, why stapling was skipped originally).
- `.github/workflows/release-launcher.yml` (current `build-launcher` job, lines 77-224).
- `local-llm-foundry/Cargo.toml` (`native-tray`/`webview-popover` feature flags, `wry`/`tray-icon`
  version pins) and `local-llm-foundry/src/tray.rs` (966 lines — the working reference
  implementation).
- `local-llm-foundry/docs/archive/implementation/20260429-app_update_capability.md` (self-update
  mechanism, referenced again in Phase 2).
- Apple's stapling docs: `rcodesign staple` usage
  (<https://gregoryszorc.com/docs/apple-codesign/main/>) — confirm exact CLI invocation and that it
  accepts a directory (`.app`) vs. requiring a `.zip`/`.dmg` wrapper first.
- `scripts/build_launcher_target.sh` and `scripts/launcher_preflight.sh` (current osxcross
  cross-build mechanics the spike must fit within, or explicitly diverge from with a documented
  reason).
- Sparkle docs (<https://sparkle-project.org/documentation/>) and the `sparkle-updater` crate — read
  the App Translocation / read-only-mount caveats specifically
  (Sparkle silently no-ops on a translocated app by default).
- WinSparkle docs (<https://winsparkle.org/>) — confirm whether its default installer-package flow
  is compatible with this launcher's no-installer distribution model, or whether it would require
  adding a Windows installer this plan doesn't currently have.

### Tasks

1. Create branch `spike/native-app-shell-macos` from this plan's branch.
2. Add a minimal `wry`+`tray-icon` "hello world" binary under `launcher-app-spike/` (separate Cargo
   package, not wired into the real launcher yet) — just enough to produce a window/tray icon, no
   real Flask integration.
3. Hand-construct a minimal macOS `.app` bundle structure
   (`PersonaForge.app/Contents/{MacOS,Resources}`, a hand-written `Info.plist`, a placeholder
   `.icns`) around the cross-compiled `aarch64-apple-darwin` binary, scripted (not manual) so the
   spike's process is reusable in Phase 3.
4. Add a throwaway `workflow_dispatch`-only CI job (not on the `release` trigger) that: builds the
   spike binary on `arc-llama-monitor` for `aarch64-apple-darwin`, assembles the `.app`, runs
   `rcodesign sign --for-notarization` on the bundle, `rcodesign notary-submit --wait`, then
   **`rcodesign staple`** — the step today's pipeline cannot use.
5. Download the resulting `.app` to a real Mac (via the existing `self-hosted-macos` smoke-test
   runner, matching how `smoke-launcher` already works) and verify: `spctl --assess --verbose=4`
   passes, `codesign --verify --deep --strict --verbose=2` passes, and — critically — that
   disconnecting from the network before first launch still allows launch (proves the staple, not
   an online check, is satisfying Gatekeeper).
6. Separately, spend a time-boxed session (recommend: half a day) attempting the same for Option A
   (Tauri) far enough to answer only one question: does `tauri build --target aarch64-apple-darwin`
   (or the equivalent lower-level bundling command) work at all when invoked from the
   `arc-llama-monitor` Linux runner via osxcross, without needing a native macOS build host? Record
   a pass/fail/blocked verdict; do not fully productionize this path regardless of outcome — it
   exists only to confirm or refute the Option A "cons" risk called out above.
7. Build a throwaway "old version" and "new version" of the spike binary, wire in the
   llama-monitor-style atomic-swap self-update from a local test HTTP server (not the real GitHub
   Releases feed yet), and time the install step end-to-end — record whether the app UI freezes and
   for how long, to directly test for the blocking-install problem the socadb-desktop Tauri
   migration hit.
8. Separately, spend a time-boxed session (recommend: half a day) wiring the same spike `.app`
   through Sparkle (`sparkle-updater` crate or direct `Sparkle.framework` embed) against a hand-
   written test appcast, and deliberately reproduce the App Translocation scenario (launch the
   `.app` directly from a Downloads-folder-like quarantined location rather than `/Applications`)
   to confirm whether it silently refuses to update, as the research above describes.
9. Write up findings as a short addendum to this doc (new `## Phase 0 results` section) — what
   worked, exact commands, exact CI run IDs/URLs, measured install-freeze duration for the DIY
   mechanism, translocation behavior for Sparkle, and whether the Recommendation above (shell
   *and* update mechanism) still holds.
10. Delete the throwaway CI job and spike branch's experimental workflow file before merging
    anything from this phase into a real phase branch (the spike's *findings* persist in this doc;
    its scaffolding code does not need to).

### Gate 0

```bash
cd /Users/nick/SCRIPTS/CLAUDE/persona-forge
gh workflow run <spike-workflow>.yml -f tag_name=spike-test
gh run watch <run-id>
# on the self-hosted-macos runner or a real Mac:
spctl --assess --verbose=4 PersonaForge.app
codesign --verify --deep --strict --verbose=2 PersonaForge.app
# with networking disabled:
open PersonaForge.app   # must launch with no Gatekeeper network-check delay/failure
```

All must pass with real command output pasted into the phase write-up — no "should work" language.
If stapling or notarization fails for the `.app` bundle in a way that isn't a quick fix, **stop and
report to the owner before proceeding to Phase 1** — this would materially change the
recommendation.

Suggested commit message for the write-up-only commit landing back on this plan's branch:

```text
docs(plan): record Phase 0 spike results for native app shell
```

---

## Phase 1 — `.app` bundle packaging for the existing CLI launcher (Option D groundwork)

### Objective

Get the *existing* launcher binary (no new GUI yet) into a real, signed, notarized, **stapled**
`.app` bundle in the release pipeline, reusing the exact bundling/signing/stapling steps proven in
Phase 0. This alone closes the "online Gatekeeper check" gap for macOS users and is valuable even
if later phases stall.

### References to read completely

- Phase 0 results section (once written).
- `scripts/package_launcher_archive.py` (current archive assembly, README template referencing the
  no-staple caveat that this phase removes).
- `.github/workflows/release-launcher.yml` `build-launcher` job.

### Tasks

1. Branch `feat/macos-app-bundle` from this plan's branch (post-Phase-0 merge).
2. Add a `scripts/build_macos_app_bundle.py` (or extend `package_launcher_archive.py`) that wraps
   the signed `persona-forge-launcher` binary in a `PersonaForge.app` structure using the process
   scripted in Phase 0 Task 3.
3. Insert `rcodesign staple` into `release-launcher.yml` after the existing verify step, gated the
   same way (`matrix.target == 'aarch64-apple-darwin'`), operating on the `.app` instead of the bare
   binary.
4. Update the release archive to ship `PersonaForge.app.zip` (or a `.dmg`, decide per Phase 0
   findings) alongside — or instead of — the current bare-binary tarball; update
   `scripts/validate_release_contract.py` expectations accordingly.
5. Update `README_TEMPLATE` in `scripts/package_launcher_archive.py` to remove the now-inaccurate
   "Gatekeeper verifies this online" language once stapling is live.
6. Update/add tests in `tests/tier1_unit/test_package_launcher_archive.py` for the new bundling
   function, following the existing subprocess-fake convention in that file.

### Gate 1

```bash
uv run --frozen python -m pytest tests/tier1_unit/test_package_launcher_archive.py -v
gh workflow run release-launcher.yml -f tag_name=<test-tag>
gh run watch <run-id>
# on self-hosted-macos, network disabled:
spctl --assess --verbose=4 PersonaForge.app
```

---

## Phase 2 — Self-update for the existing CLI launcher

### Objective

Implement whichever update mechanism Phase 0 settled on for `persona-forge-launcher`, without yet
adding tray/webview UI. The two shapes this objective covers, chosen by Phase 0's findings (default
to the DIY path below if Phase 0's results are inconclusive, since it's the lower-risk, already-
proven-in-org option — but Phase 0's written recommendation governs):

- **If DIY (`local-llm-foundry`-style):** port the mechanism in
  `docs/archive/implementation/20260429-app_update_capability.md` — Unix/macOS atomic
  rename-in-place, Windows detached-batch relaunch, a small HTTP endpoint + frontend pill reusing
  the existing Flask app, matching the llama-monitor UX pattern.
- **If Sparkle/WinSparkle:** integrate the `sparkle-updater` crate (or direct framework embed),
  generate an EdDSA signing keypair (private half in a new CI secret, alongside the existing
  `MACOS_KEY_PEM`-family secrets, public half embedded in the binary), and add an appcast-generation
  step to `release-launcher.yml` that runs after `release` publishes GitHub Release assets (an
  appcast entry needs the final download URL, so it is generated from the already-published
  release, not before).

### References to read completely

- Phase 0 results section — **read this first**; it determines which of the two task lists below
  applies.
- `docs/archive/implementation/20260429-app_update_capability.md` (DIY mechanism, if chosen).
- Sparkle/`sparkle-updater`/WinSparkle docs (if chosen), plus Phase 0's translocation and
  install-freeze findings.
- `launcher/src/{main.rs,bootstrap.rs,manifest.rs,paths.rs}` (current launcher structure this
  extends either way).
- `docs/architecture/FRONTEND_OVERVIEW.md` (where any update-pill UI plugs into the existing React
  app, if the DIY path's in-app UI is kept even alongside Sparkle's native dialog).

### Tasks (DIY mechanism)

1. Branch `feat/launcher-self-update`.
2. Add an `update` module to `launcher/src/` implementing: check-latest-release (reuse whatever
   endpoint/logic already resolves release info, or add a thin GitHub Releases API call),
   download-to-sibling-temp-file, verify signature/notarization/checksum against `checksums.json`
   from the release **before** swapping (Global Constraint above), then platform-specific swap
   (`std::fs::rename` on Unix, detached `.bat` helper on Windows via `DETACHED_PROCESS`).
3. Add a Flask endpoint mirroring llama-monitor's `POST /api/self-update` (exits process after a
   short flush delay) and a `GET` endpoint for latest-version info.
4. Add the update-pill UI to the frontend (version injected at build/package time, `localStorage`
   dismissal cooldown, polls for update availability, polls `HEAD /` after triggering update to
   detect relaunch).
5. Unit-test the update module's pure logic (path selection, checksum verification, version
   comparison) with fakes for the network/filesystem boundary, matching the existing
   `test_package_launcher_archive.py` fake-subprocess convention.

### Tasks (Sparkle/WinSparkle mechanism)

1. Branch `feat/launcher-self-update`.
2. Generate an EdDSA signing keypair; add the private key as a new CI secret and embed the public
   key (`SUPublicEDKey`) in the bundle's `Info.plist` (macOS) / binary resources (Windows).
3. Add an appcast-generation step to `release-launcher.yml`'s `release` job (after assets publish)
   that emits `appcast.xml` from the release's assets/checksums and publishes it as a release asset
   or to a stable URL the app's `SUFeedURL` points at.
4. Wire `sparkle-updater` (or direct framework calls) into `launcher/src/main.rs`, gated to the
   `.app`-bundle build shape from Phase 1.
5. Add the "move to Applications" first-launch prompt (mitigates the App Translocation refusal
   Phase 0 is expected to reproduce).
6. Unit/integration-test what's testable without a real macOS/Windows signing round-trip (appcast
   XML generation, keypair handling); the signature verification itself is exercised by Gate 2
   below on real runners, not by unit tests.

### Gate 2

```bash
cargo test --manifest-path launcher/Cargo.toml
uv run --frozen python -m pytest tests/tier1_unit -q
# manual: run an old launcher build, trigger self-update, confirm it relaunches as the new version
# on macOS, Windows, and Linux smoke runners (self-hosted-macos, self-hosted-windows, arc-general).
```

---

## Phase 3 — Tray + popover webview shell (Option C full realization)

### Objective

Layer the `wry`+`tray-icon` shell on top of the now-signed/notarized/self-updating launcher: a
menu-bar/tray icon replaces the "run a CLI and open a browser tab" UX, with a popover webview
hosting the existing React frontend, matching `local-llm-foundry`'s `src/tray.rs` pattern.

### References to read completely

- `local-llm-foundry/src/tray.rs` in full (966 lines — the reference implementation to adapt, not
  copy verbatim, since persona-forge's backend/frontend integration differs).
- Phase 0 and Phase 1 results (bundle structure, signing steps this phase's binary must also pass
  through).
- `docs/architecture/FRONTEND_OVERVIEW.md`.

### Tasks

*(Left intentionally high-level — this phase is downstream of Phase 0's verdict and should be
detailed in a revision of this doc once Phases 0-2 land, not speculatively now.)*

1. Add `native-tray`/`webview-popover`-equivalent Cargo features to `launcher/Cargo.toml`, mirroring
   local-llm-foundry's flag names for consistency across the org's two Rust projects.
2. Wire the tray icon to start/stop the existing Flask backend process (already how the launcher
   works — `bootstrap::ensure_env` + exec) instead of `exec`-replacing the launcher process, since
   the tray shell needs to keep running as the parent.
3. Wire the popover webview to load the existing frontend `dist/` build, same as the browser-tab UX
   today, just hosted in an OS webview instead of a system browser.
4. Extend `.app` bundling (Phase 1) and self-update (Phase 2) to cover this new binary shape.

### Gate 3

To be specified in a doc revision once Phases 0-2's exact deliverables are known.

---

## Non-goals (this plan)

- Windows Authenticode / Linux package-signing (e.g. `.deb` GPG signing) are **not** committed to
  by this plan; see "Open questions for the owner" #5 — may become a Phase 4 if the owner wants
  parity.
- App Store distribution (Mac App Store or Microsoft Store) — out of scope; this launcher downloads
  its own dependencies and would need App Store review/sandboxing changes to qualify at all
  (already noted as a rejected alternative in the original macOS signing doc).
- Rebuilding the frontend for a native-shell-specific UI — this plan always reuses the existing
  React `dist/` build as-is.
- Changing or removing the Docker deployment path.

## Open questions for the owner

1. **Which option should Phase 3 actually build — full tray/popover shell (Option C), or stop after
   Phase 2 (Option D) and call that "done"?** Recommendation: decide after Phase 0's spike results
   are in hand, not now — Phase 0 and Phase 1 are valuable regardless of this answer, so there's no
   cost to deferring it.
1a. **What does "more first-class, non-browser feel" concretely mean for Phase 3** — a tray-icon
    popover (matching local-llm-foundry's current shape, just signed/notarized), a dedicated main
    application window instead of a popover, a dock-icon-first app with no tray at all, or some
    combination? The owner flagged (2026-09-25) that this is a shared, not-yet-fully-formed goal for
    both persona-forge and local-llm-foundry. Recommendation: treat Phase 3's design as explicitly
    open until Phases 0-2 ship, and revisit this doc (or split a Phase 3-specific design doc) once
    there's a working signed/notarized/self-updating binary to build the UI question on top of —
    deciding the UI shape now, before Phase 0's spike results, risks anchoring on the wrong
    constraints.
2. **`.dmg` vs. plain `.app.zip` for macOS distribution?** A `.dmg` is more familiar to macOS users
   (drag-to-Applications) but adds another artifact-building step. Recommendation: start with
   `.app.zip` in Phase 1 (simpler, and `.app` bundles staple identically either way), revisit `.dmg`
   only if user feedback asks for it.
3. **Does self-update (Phase 2) require a user-facing opt-out/settings toggle**, or is
   always-auto-check-never-auto-install (user clicks a pill) sufficient, matching llama-monitor?
   Recommendation: match llama-monitor's pattern exactly (check automatically, install only on
   explicit user action) — it's proven and avoids the harder problem of an update landing mid-use.
4. **Should the `build-launcher` matrix add `aarch64-unknown-linux-gnu`** (already built by
   local-llm-foundry on the same runner, not currently built by persona-forge) as part of this
   work, for Linux ARM parity? Recommendation: yes, bundle it into Phase 1 or 2 as a small addition
   since the toolchain step is already proven — but flag it as separable if the owner wants to keep
   phases narrowly scoped.
5. **Is Windows/Linux code-signing in scope for this initiative at all**, or a separate future
   initiative? No secrets are currently provisioned for either. Recommendation: treat as a separate
   follow-up plan — Authenticode certificates have their own procurement process (unlike Apple's,
   which is already done), and gating this plan's phases on that procurement risks stalling the
   macOS-side work, which can ship independently.
6. **Naming: is `PersonaForge.app` the confirmed product name for the bundle**, or should it match
   some other branding decision from the `persona-forge-rebrand` initiative
   ([[persona-forge-rebrand]] in memory — full plan at
   `docs/plans/20260811-persona_forge_rebrand.md`)? Recommendation: confirm before Phase 1, since
   the bundle identifier (`Info.plist` `CFBundleIdentifier`, e.g. reverse-DNS) and icon are
   effectively permanent once released and staple-verified.

## Appendix — Baseline source map

- `launcher/src/main.rs:1-82` — current CLI entry point; Phase 2/3 extend, not replace, this.
- `launcher/Cargo.toml` — dependency set to extend with `wry`/`tray-icon` (Phase 3) and any
  update-check HTTP client (Phase 2).
- `scripts/package_launcher_archive.py:32-62` — `README_TEMPLATE`, updated in Phase 1.
- `scripts/package_launcher_archive.py:73-100` — `export_requirements`, unaffected by this plan but
  adjacent in the same file Phase 1 edits.
- `.github/workflows/release-launcher.yml:77-224` — `build-launcher` job; every phase's CI changes
  land here, gated by `matrix.target`.
- `docs/archive/macos-code-signing/20260918-macos_code_signing.md` — full signing background; the
  "no staple" limitation this plan resolves is documented at lines 137-139 and 281-283 there.
- `local-llm-foundry/src/tray.rs` (966 lines) and
  `local-llm-foundry/docs/archive/implementation/20260429-app_update_capability.md` (287 lines) —
  the reference implementation and its design doc; both external to this repo, read via the
  sibling checkout at `/Users/nick/SCRIPTS/CLAUDE/local-llm-foundry`.
- Sparkle: <https://sparkle-project.org/documentation/>, source at
  <https://github.com/sparkle-project/Sparkle>. WinSparkle: <https://winsparkle.org/>, source at
  <https://github.com/vslavik/winsparkle>. Rust binding: `sparkle-updater` crate (wraps both). All
  external, researched 2026-09-25, no in-repo or in-org usage yet — see "Update mechanism options."
