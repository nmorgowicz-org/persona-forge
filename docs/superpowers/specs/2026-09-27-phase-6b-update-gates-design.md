# Phase 6B: signed update feeds and update gates — design

**Status:** approved in conversation on 2026-09-27; awaiting written-spec review.

## Purpose and success criteria

Phase 6B completes Persona Forge's desktop update trust chain before a production release points to `releases/latest/download/`:

1. Windows and Linux update artifacts are signed after their final artifact names are assigned.
2. The macOS DMG is represented in a Sparkle-compatible, EdDSA-signed `appcast.xml`.
3. The three platform artifacts and their feeds are exercised through isolated GitHub pre-release test channels.
4. Valid updates from `90.0.1` to `90.0.2` install on every supported desktop platform.
5. Corrupted updates are rejected on every platform, with the previous installation intact.
6. No signing secret reaches a persistent runner, a repository checkout, a build artifact, command-line arguments, or logs.

This design implements the binding desktop-shell contract: D12 (signed GitHub Release feeds), D14 (environment retention), D19 (ephemeral-only secrets), §6.12 (test-only `--ci-update`), §8 (build topology), §9.1 and §9.2 (feed formats), and §12 (key handling).

## Security and trust boundaries

### Key scope

The following three repository-level GitHub Actions secrets have been confirmed present for `nmorgowicz-org/persona-forge`:

- `TAURI_SIGNING_PRIVATE_KEY`
- `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`
- `SPARKLE_ED_PRIVATE_KEY`

They are deliberately Persona Forge-specific. They must not be organization-wide or shared with Local LLM Foundry: each application has a separate update trust boundary.

Existing organization-scoped Apple signing/notarization secrets (`MACOS_*` and `APPLE_*`) continue to be used only by the existing ephemeral macOS signing jobs.

### Secret handling

- `updater-sigs` receives only the two `TAURI_SIGNING_*` secrets and runs on ephemeral `arc-persona-forge-desktop`.
- The feed-publishing job receives only `SPARKLE_ED_PRIVATE_KEY` and runs on ephemeral `arc-general`.
- Persistent `self-hosted-macos` and `self-hosted-windows` jobs never receive any signing secret.
- The feed generator derives the transient Ed25519 PKCS#8 key from the base64 seed in a mode-`0600` temp file, removes it in `finally`, and never puts it in argv, stdout, stderr, feeds, or artifacts.

## Build and signing flow

`desktop-build.yml` remains a reusable, dispatchable build workflow.

1. `build-macos`, `build-windows`, and `build-linux` produce their native unsigned/finally-renamed distribution artifacts without updater signing keys.
2. `sign-macos-app` and `dmg-macos` continue the existing Developer-ID/notarization chain on the specified runner split.
3. A new `updater-sigs` job runs only when `inputs.sign` is true. It waits for the signed DMG, Windows setup executable, and Linux AppImage jobs as appropriate; it downloads the renamed Windows and Linux artifacts; and it uses `cargo tauri signer sign` to produce their `.sig` companions. It reuploads each `.sig` with the artifact it authenticates.
4. The update-feed generator consumes the signed DMG, Windows setup executable plus `.sig`, and Linux AppImage plus `.sig`. It writes:
   - `appcast.xml`: a Sparkle RSS item whose enclosure contains the final DMG URL, length, EdDSA signature, version, and minimum macOS version.
   - `latest.json`: the Tauri v2 static feed, with `windows-x86_64-nsis` and `linux-x86_64-appimage` entries referencing final URLs and the Tauri-generated signatures.

The existing `ci_hooks` input remains test-only. When true, Windows and Linux builds compile `--features ci-hooks`; a release invocation does not enable it.

## Release-artifact guard

A production artifact must reject the test-only argument `--ci-update <path>` before it starts Tauri or a server. Therefore, when `ci_hooks` is false, the existing platform smoke scripts invoke the built artifact with that argument and require exit code `2`. Windows uses `Start-Process -Wait -PassThru` to make the exit-code assertion reliable.

This proves a release build cannot expose the automated updater driver accidentally.

## Normal production-release behavior

The `90.0.1` / `90.0.2` versions and `desktop-updater-test` /
`desktop-updater-badsig` pre-releases are one-time qualification fixtures. They are not part of
ordinary releases.

Once Phase 6B proves the trust chain and Phase 7 connects it to release automation, a normal
Persona Forge release builds and publishes only its real version's signed DMG, Windows installer,
Linux AppImage, and their update metadata. The production `appcast.xml` and `latest.json` are
still generated automatically because installed applications require them, but they reference
only the proper release assets through `releases/latest/download/`. The test pre-releases are
deleted after qualification and do not need to be created again for each production release.

## Temporary update-test channels

The workflow uses two owner-created GitHub pre-releases:

| Pre-release tag | Purpose | Contents |
| --- | --- | --- |
| `desktop-updater-test` | Valid-update channel | Correctly signed `90.0.2` DMG, setup executable, AppImage, `.sig` files, `appcast.xml`, and `latest.json`. |
| `desktop-updater-badsig` | Negative-security channel | Corrupted copies of the three `90.0.2` artifacts plus feeds retaining their original/wrong signatures. |

Only plain test versions `90.0.1` and `90.0.2` are used. Pre-release semver suffixes are not used because Sparkle and Tauri compare them differently. The `90.x` range cannot collide with a product release.

Both pre-releases are temporary and are deleted by the owner after the successful gate procedure.

## Update E2E workflow

`desktop-update-e2e.yml` replaces its stub with a dispatch-only workflow accepting the existing inputs:

- `n_run_id`: successful signed `desktop-build.yml` run for `90.0.1`.
- `n1_run_id`: successful signed `desktop-build.yml` run for `90.0.2`.
- `mode`: `good` or `badsig`.

Top-level permissions remain `contents: read`. The `publish-feeds` job alone elevates to `contents: write`, runs on ephemeral `arc-general`, downloads N+1 artifacts with `gh run download`, and publishes/replaces release assets with `gh release upload --clobber`.

### Valid path (`good`)

`publish-feeds` runs the generator against N+1's correctly signed artifacts and uploads all three artifacts, both update signatures, and both generated feeds to `desktop-updater-test`.

- `e2e-linux` runs on `arc-persona-forge-desktop` with no secrets. It uses a fresh `PERSONA_FORGE_HOME`, installs/copies N, runs its smoke test, runs `--ci-update`, and requires `ok: true`, `phase: "installed"`, and `to_version: "90.0.2"`. A final smoke test confirms `90.0.2` and exactly `90.0.1` and `90.0.2` environments.
- `e2e-windows` runs on `self-hosted-windows` with no secrets. It silently installs N using NSIS `/S`, runs its smoke test, runs `--ci-update`, requires `phase: "installing"`, and polls the uninstall registry for `DisplayVersion` `90.0.2` for at most 120 seconds. It stops a relaunching app before cleanup, confirms the same two retained environments, and uninstalls in `finally`.

### Rejection path (`badsig`)

`publish-feeds` flips one byte in every N+1 artifact. It deliberately leaves Tauri signatures stale and gives Sparkle a wrong EdDSA signature before publishing the corrupted release assets.

Both E2E jobs require `ok: false` and `phase: "verify"`. Linux reruns the smoke test and requires version `90.0.1`; Windows requires registry `DisplayVersion` to remain `90.0.1` and uninstalls in `finally`.

## Gate sequence and owner checks

After implementation and local validation, the owner runs the following in order:

1. Create the two empty GitHub pre-releases.
2. Dispatch three signed `desktop-build.yml` runs from `desktop/p6-updates`:
   - A: `90.0.1`, `ci_hooks=true`, test-feed base URL.
   - B: `90.0.2`, `ci_hooks=false`, test-feed base URL.
   - C: `90.0.1`, `ci_hooks=true`, bad-signature-feed base URL.
3. Dispatch `desktop-update-e2e.yml` in `good` mode using A and B. Both platform jobs must pass.
4. Dispatch it in `badsig` mode using C and B. Both platform jobs must reject the update.
5. On macOS, clean-install run A's DMG into `/Applications`, use **Check for Updates**, and confirm N+1 launches, the server stops cleanly, the SPA/theme survives, and exactly the two expected environments remain.
6. On Windows 11, install run A's setup executable and repeat the real GUI update test.
7. On macOS, install run C's DMG and confirm Sparkle rejects the bad-signature update.
8. Delete the two temporary pre-releases.

The owner receives numbered, copy-pasteable instructions only at the stages requiring their GitHub or GUI interaction.

## Failure behavior and stop conditions

- Missing/empty asset or signature, malformed Sparkle seed, unsupported OpenSSL, or feed-version mismatch is a hard failure; no incomplete feed is published.
- An update with a bad signature installed on any platform is a security stop. Do not merge.
- A valid macOS update that fails to install through Sparkle, or freezes the UI for more than two seconds during download, is a stop. Do not merge.
- Test-only CI updater access in a production artifact is a release-blocking failure.

## Verification requirements

Before the external update gates, the branch must pass:

```bash
cargo test --manifest-path desktop/Cargo.toml
OPENSSL=/opt/homebrew/bin/openssl PYTHONPATH=src:src/export \
  uv run --frozen python -m pytest tests/tier1_unit/test_generate_update_feeds.py -v -rs
python scripts/validate_repo.py
git diff --check
```

The feed test report must show zero skipped tests. Delivery records the URLs for build runs A/B/C, both E2E runs, the macOS and Windows owner outcomes, and the bad-signature rejection results.

## Scope exclusions

Phase 6B does not alter the Docker deployment path, Linux CLI archive behavior, application update UX beyond the already-merged Phase 6A client plumbing, or Local LLM Foundry. It does not add a Windows code-signing certificate.
