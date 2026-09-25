# macOS Code Signing and Notarization

Date: 2026-09-18
Status: Resolved — implemented in `.github/workflows/release-launcher.yml`
(2026-09-24). This document is kept as the historical record of the signing
setup; see that workflow file for the current pipeline.

This document describes the plan to code-sign and notarize the macOS
launcher binary so it launches without Gatekeeper quarantine prompts. It
replaces the current workaround documented in
`scripts/package_launcher_archive.py` (the `xattr -dr com.apple.quarantine`
instruction) and removes the need for any macOS build runner.

## Background

### Current state

- The launcher is cross-compiled for `aarch64-apple-darwin` on the Linux runner
  `arc-llama-monitor` using the osxcross toolchain
  (`scripts/build_launcher_target.sh`).
- The resulting binary is unsigned. When a user downloads the release archive
  and extracts the launcher, Gatekeeper marks it as quarantined.
- The README bundled in the archive currently tells users to run
  `xattr -dr com.apple.quarantine .` to bypass quarantine. This is a manual,
  error-prone step that also leaves the binary un-notarized.

### Goal

Produce a launcher binary that:

1. Is signed with an Apple **Developer ID Application** certificate.
2. Is notarized by Apple's notary service.
3. Launches without Gatekeeper prompts on macOS 13+. Apple does not support
   stapling notarization tickets to a bare Mach-O executable (only
   `.app`/`.pkg`/`.dmg`), so first launch performs Apple's normal online
   Gatekeeper check instead of using a stapled ticket. This still eliminates
   the quarantine dialog and manual `xattr` workaround; it just requires
   internet connectivity on first launch.

### Constraint: all-Linux pipeline

The macOS binary is cross-compiled on a Linux runner. The signing process must
also run on Linux — no reliance on the `self-hosted-macos` MacBook Pro runner,
so the pipeline survives when that machine is offline.

## Verified tooling (checked 2026-09-18)

### `rcodesign` / `apple-codesign` (Rust)

- Repository: <https://github.com/indygreg/apple-platform-rs/tree/main/apple-codesign>
- Current version: 0.29.0
- License: MIT (with Apache-2.0 and Unicode-DFS-2016 components)
- Author: Gregory Szorc (indygreg)

**Key facts:**

- Pure Rust implementation of Apple's code-signing format.
- Does **not** require Xcode, macOS, or any proprietary software.
- Officially supports Linux, Windows, and macOS as signing hosts.
- Provides the `rcodesign` CLI binary.
- Pre-built Linux binaries are published on GitHub Releases:
  - `*-unknown-linux-gnu` — compiled against glibc 2.35 (Ubuntu 22.04+, Fedora 36+)
  - `*-unknown-linux-musl` — static, runs anywhere but lacks PKCS#11 support
    (PKCS#11 is not needed for our flow)
- Handles **signing, notarizing, and stapling** natively — it calls Apple's
  App Store Connect API directly, so no `notarytool` or `stapler` binary is
  required.

Installation options (all valid on Linux):

```bash
# Option A: download pre-built binary (fastest, recommended)
# NOTE: release tags use a `apple-codesign/X.Y.Z` (slash) format, and assets
# are named `apple-codesign-X.Y.Z-<target>.tar.gz` archives (not bare
# binaries) - there is no `-unknown-linux-gnu` asset, only
# `-unknown-linux-musl`. The URL below was corrected after the first live
# CI run 404'd on the originally-assumed URL shape.
curl -fL -o rcodesign.tar.gz \
  "https://github.com/indygreg/apple-platform-rs/releases/download/apple-codesign%2F0.29.0/apple-codesign-0.29.0-x86_64-unknown-linux-musl.tar.gz"
tar -xzf rcodesign.tar.gz apple-codesign-0.29.0-x86_64-unknown-linux-musl/rcodesign
mv apple-codesign-0.29.0-x86_64-unknown-linux-musl/rcodesign ./rcodesign
chmod +x rcodesign

# Option B: cargo install
cargo install apple-codesign --locked

# Option C: from git main
cargo install --git https://github.com/indygreg/apple-platform-rs --branch main --bin rcodesign apple-codesign
```

### Apple Developer ID Application certificate

Required for signing software distributed outside the Mac App Store. The
certificate type is **Developer ID Application** (not "Mac App Distribution",
not "Developer ID Installer", not "Apple Development"). This is what
Gatekeeper checks for third-party CLI tools and binaries.

### App Store Connect API key

Required for notarization and stapling. Generated at
<https://appstoreconnect.apple.com/access/api>. Needs the **Developer** access
role (other roles may or may not work for notarization).

The key has three components:

- **Issuer ID** — a UUID
- **Key ID** — an alphanumeric string (e.g. `DEADBEEF42`)
- **Private key** — a PEM file (`AuthKey_XXXXXX.p8`), downloadable once at
  creation time

`rcodesign` provides `encode-app-store-connect-api-key` to bundle these three
into a single JSON file for easier secret management.

## The signing process

The complete flow for the macOS binary:

```
1. Sign the binary (in place)
   rcodesign sign \
     --pem-file key.pem --pem-file cert.pem \
     --for-notarization \
     launcher-binary

2. Notarize the signed binary (must be zipped — rcodesign does not
   notarize a bare Mach-O binary directly)
   zip notarize.zip launcher-binary
   rcodesign notary-submit \
     --api-key-file ~/.appstoreconnect/key.json \
     --wait \
     notarize.zip

3. Verify
   rcodesign verify launcher-binary
```

No staple step: Apple only supports stapling on `.app`/`.pkg`/`.dmg`, not a
bare executable. The binary is signed and notarized; Gatekeeper performs its
normal online ticket check on first launch instead of reading a local staple.

### Requirements enforced by Apple's notary service

The notary service requires:

- A valid **Developer ID Application** certificate signature.
- The **Hardened Runtime** capability (`--option runtime`).
- A **secure timestamp** (`--timestamped`).
- No `com.apple.security.get-task-allow` entitlement set to `true`.
- Link against macOS 10.9 or later SDK (osxcross provides this).
- Properly formatted entitlements (our binary has no special entitlements,
  so this is satisfied by the hardened runtime default).

## Secrets required

Five secrets must be added to the repository settings (Settings → Secrets and
variables → Actions):

| Secret name | Content | Secret? |
| --- | --- | --- |
| `MACOS_KEY_PEM` | Developer ID private key in PEM format | Yes |
| `MACOS_CERT_PEM` | Developer ID public certificate in PEM format | No (embeds in signature) |
| `APPLE_ISSUER_ID` | App Store Connect API key issuer UUID | Yes |
| `APPLE_KEY_ID` | App Store Connect API key identifier | Yes |
| `APPLE_PRIVATE_KEY` | App Store Connect API private key (`.p8` PEM) | Yes |

The PEM certificate and key should be extracted from the Developer ID
Application certificate exported from Keychain Access. The public cert
(`-----BEGIN CERTIFICATE-----`) is not secret and is embedded in every
signature; the private key (`-----BEGIN PRIVATE KEY-----`) is the secret.

## CI workflow changes

### File: `.github/workflows/release-launcher.yml`

Add five steps to the `build-launcher` job, gated on
`matrix.target == 'aarch64-apple-darwin'`. They run after "Fetch + verify
pinned uv binary" and before "Package launcher archive".

**Step 1: Install rcodesign**

```yaml
- name: Install rcodesign (macOS signing)
  if: matrix.target == 'aarch64-apple-darwin'
  run: |
    set -euo pipefail
    RCODESIGN_VERSION="0.29.0"
    RCODESIGN_ASSET="apple-codesign-${RCODESIGN_VERSION}-x86_64-unknown-linux-musl"
    curl --fail --location --silent --show-error -o rcodesign.tar.gz \
      "https://github.com/indygreg/apple-platform-rs/releases/download/apple-codesign%2F${RCODESIGN_VERSION}/${RCODESIGN_ASSET}.tar.gz"
    tar -xzf rcodesign.tar.gz "${RCODESIGN_ASSET}/rcodesign"
    mv "${RCODESIGN_ASSET}/rcodesign" ./rcodesign
    chmod +x rcodesign
```

(Using `curl`, not `wget` — the `arc-llama-monitor` runner image didn't ship
`wget` at the time, which caused the first live run to fail with
`wget: command not found`; `wget` has since been added to the runner image
as well.)

The second live run then hit a 404: release tags on this repo use a
`apple-codesign/X.Y.Z` (slash) format, not `apple-codesign-X.Y.Z` (hyphen),
and there is no bare `rcodesign-x86_64-unknown-linux-gnu` asset — only
`.tar.gz` archives, and only for the `musl` target (no glibc Linux build).
The snippet above reflects the corrected download.

**Step 2: Prepare App Store Connect API key**

```yaml
- name: Prepare App Store Connect API key
  if: matrix.target == 'aarch64-apple-darwin'
  env:
    APPLE_ISSUER_ID: ${{ secrets.APPLE_ISSUER_ID }}
    APPLE_KEY_ID: ${{ secrets.APPLE_KEY_ID }}
    APPLE_PRIVATE_KEY: ${{ secrets.APPLE_PRIVATE_KEY }}
  run: |
    set -euo pipefail
    mkdir -p ~/.appstoreconnect
    echo "$APPLE_PRIVATE_KEY" | tr ' ' '\n' > /tmp/AuthKey.pem
    ./rcodesign encode-app-store-connect-api-key \
      -o ~/.appstoreconnect/key.json \
      "$APPLE_ISSUER_ID" "$APPLE_KEY_ID" /tmp/AuthKey.pem
```

**Step 3: Sign the launcher binary**

```yaml
- name: Sign launcher binary (macOS)
  if: matrix.target == 'aarch64-apple-darwin'
  env:
    MACOS_KEY_PEM: ${{ secrets.MACOS_KEY_PEM }}
    MACOS_CERT_PEM: ${{ secrets.MACOS_CERT_PEM }}
  run: |
    set -euo pipefail
    echo "$MACOS_KEY_PEM" > key.pem
    echo "$MACOS_CERT_PEM" > cert.pem
    LAUNCHER="launcher/target/aarch64-apple-darwin/release/persona-forge-launcher"
    ./rcodesign sign \
      --pem-file key.pem --pem-file cert.pem \
      --for-notarization \
      "$LAUNCHER"
```

`--for-notarization` is rcodesign's purpose-built flag for this flow: it requires a
Developer ID cert, requires a secure timestamp, and enables the hardened runtime
(equivalent of `--code-signature-flags runtime`) in one place. An earlier iteration
used only `--code-signature-flags runtime` directly, which does *not* force the
timestamp requirement — the notary service rejected those binaries with "signature
does not include a secure timestamp" and (likely a fallout of the same incomplete
signature) "not signed with a valid Developer ID certificate." A CA-chain fix
(appending Apple's Developer ID intermediate + root certs to `MACOS_CERT_PEM`) was
tried first and did not resolve it, confirming the missing timestamp was the actual
cause, not the certificate chain.

**Step 4: Notarize the signed binary**

```yaml
- name: Notarize launcher binary (macOS)
  if: matrix.target == 'aarch64-apple-darwin'
  run: |
    set -euo pipefail
    # rcodesign does not notarize a bare Mach-O binary; it must be zipped.
    LAUNCHER="launcher/target/aarch64-apple-darwin/release/persona-forge-launcher"
    zip notarize.zip "$LAUNCHER"
    ./rcodesign notary-submit \
      --api-key-file ~/.appstoreconnect/key.json \
      --wait \
      notarize.zip
```

**Step 5: Verify**

```yaml
- name: Verify launcher signature (macOS)
  if: matrix.target == 'aarch64-apple-darwin'
  run: |
    set -euo pipefail
    LAUNCHER="launcher/target/aarch64-apple-darwin/release/persona-forge-launcher"
    ./rcodesign verify "$LAUNCHER"
```

No staple step — Apple does not support stapling a notarization ticket to a
bare executable (only `.app`/`.pkg`/`.dmg`). The signed, notarized binary
relies on Apple's online Gatekeeper check on first launch instead.

The existing "Package launcher archive" step then bundles the already-signed
and notarized binary. Linux and Windows targets are unaffected — the steps
are gated on the macOS target.

### Timing considerations

- `rcodesign sign` is fast (milliseconds).
- `rcodesign notary-submit --wait` blocks while Apple scans the binary.
  Typical wait is 1–5 minutes. The `build-launcher` job has a 45-minute
  timeout, which is sufficient.
- `rcodesign verify` is fast (milliseconds).

If notarization timeout becomes an issue, the `--wait` flag can be removed and
the job can poll the submission ID until it succeeds, but this is unlikely to
be needed.

## Documentation changes

### File: `scripts/package_launcher_archive.py`

Remove the Gatekeeper quarantine instruction from `README_TEMPLATE`:

```diff
 Before running the launcher, verify this archive against checksums.json from the same
-GitHub Release. On macOS, if Gatekeeper blocks the extracted binary, first run:
-  xattr -dr com.apple.quarantine .
-Only run that command inside this verified archive directory.
+GitHub Release. The macOS launcher is code-signed and notarized by Apple.
+Gatekeeper verifies this online on first launch (requires internet
+connectivity once); no manual quarantine removal is needed.
```

Keep the archive verification instruction. The signed/notarized binary does
not require manual quarantine removal.

## Local development flow

Local development is unchanged. Developers who build the macOS binary locally
(use the native macOS runner or a Mac) will still get an unsigned binary that
Gatekeeper quarantines. The local workflow remains:

```bash
codesign -s - ./persona-forge-launcher  # ad-hoc sign
xattr -dr com.apple.quarantine ./persona-forge-launcher  # strip quarantine
```

Full Developer ID signing + notarization runs only in CI on release.

## Verification

After the CI workflow runs, the macOS release binary should:

1. Pass `rcodesign verify` on Linux.
2. Pass `codesign --verify --deep --strict --verbose=2` on macOS.
3. Launch on macOS without a Gatekeeper quarantine dialog. First launch
   performs Apple's normal online notarization check (requires internet);
   there is no local staple, since Apple does not support stapling to a
   bare executable.

To verify locally once the workflow produces an artifact:

```bash
# Download and extract the macos-aarch64 archive
codesign -dv --verbose=4 persona-forge-launcher  # shows signing info
spctl --assess --verbose=4 persona-forge-launcher  # shows Gatekeeper verdict
```

## Completed items

All items below are done as of 2026-09-24:

1. **Apple Developer account activation** — completed.

2. **Developer ID Application certificate generated** — CSR created via
   Keychain Access on a local Mac (required for the cert to be paired with
   a private key only the account holder holds), submitted in the Developer
   Portal, downloaded, imported into Keychain Access, and exported as PEM
   cert + key files.

3. **App Store Connect API key generated** — Issuer ID, Key ID, and `.p8`
   private key obtained with the Developer role.

4. **Secrets added** — all five (`MACOS_KEY_PEM`, `MACOS_CERT_PEM`,
   `APPLE_ISSUER_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY`) added as
   **organization-level** secrets (not repo-level), scoped to
   `persona-forge` and `local-llm-foundry` so both repos can reuse the same
   Developer ID identity and API key.

5. **CI workflow implemented** — the five signing/notarizing/verifying
   steps landed in `.github/workflows/release-launcher.yml`, gated on the
   `aarch64-apple-darwin` matrix target.

### Remaining follow-up (not blocking merge)

- **Trigger a live test run** — Use `workflow_dispatch` on
  `release-launcher.yml` with a test tag to verify the full signing flow
  end-to-end (the exact `rcodesign` CLI flags below were verified against
  published docs, not by running the binary in this environment).

## Alternatives considered

### Use `notarytool` and `stapler` on a macOS runner

- **Pros:** Canonical Apple tools, well-documented.
- **Cons:** Requires the `self-hosted-macos` runner to be online. The user
  prefers keeping the pipeline on the Linux runners for reliability. `notarytool`
  also requires a macOS keychain profile for credential storage.

### Use the `indygreg/apple-code-sign-action` GitHub Action

- **Pros:** Thin wrapper over `rcodesign`, tested, handles credential setup.
- **Cons:** Adds a third-party action dependency. The inline `rcodesign` steps
  give more control and keep the workflow self-contained.

### Ad-hoc signing + quarantine removal only

- **Pros:** No certificate needed, no Apple fees.
- **Cons:** Gatekeeper still shows a warning on first launch ("unidentified
  developer"). Users must manually approve or run `xattr -d`. Not suitable for
  a polished distribution.

### App Store distribution

- **Pros:** No notarization needed (App Store review replaces it).
- **Cons:** Requires an app bundle, not a CLI binary. Adds App Store review
  overhead and distribution constraints. Not appropriate for a bootstrap
  launcher that downloads its own dependencies.

## References

- `rcodesign` crate: <https://github.com/indygreg/apple-platform-rs/tree/main/apple-codesign>
- `rcodesign` docs: <https://gregoryszorc.com/docs/apple-codesign/main/>
- Apple notarization docs:
  <https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution>
- App Store Connect API key setup:
  <https://developer.apple.com/documentation/appstoreconnectapi/creating_api_keys_for_app_store_connect_api>
- `rcodesign` certificate management:
  <https://gregoryszorc.com/docs/apple-codesign/stable/apple_codesign_certificate_management.html>
