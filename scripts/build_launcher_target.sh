#!/usr/bin/env bash
# Cross-compile persona-forge-launcher for one target (Phase 7). Adapted from Local LLM Foundry's
# scripts/build-single-target.sh, minus the GUI/webview toolchain that launcher/ has no need of.
set -euo pipefail

TARGET="${1:?Usage: build_launcher_target.sh <target>}"
MANIFEST="launcher/Cargo.toml"

DARWIN_VERSION=$(ls /opt/osxcross/target/bin/aarch64-apple-darwin*-clang 2>/dev/null \
  | head -1 | grep -oP 'darwin[\d.]+' || true)
MACOS_SDK=$(ls -d /opt/osxcross/target/SDK/MacOSX*.sdk 2>/dev/null \
  | sort -V | tail -1 | xargs -r basename)

case "$TARGET" in
  x86_64-unknown-linux-gnu)
    cargo build --release --manifest-path "$MANIFEST" --target x86_64-unknown-linux-gnu
    ;;
  x86_64-pc-windows-gnu)
    CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER=x86_64-w64-mingw32-gcc \
      cargo build --release --manifest-path "$MANIFEST" --target x86_64-pc-windows-gnu
    ;;
  aarch64-apple-darwin)
    if [[ -z "$DARWIN_VERSION" || -z "$MACOS_SDK" ]]; then
      echo "FAIL: osxcross toolchain not found; run scripts/launcher_preflight.sh first" >&2
      exit 1
    fi
    SDKROOT="/opt/osxcross/target/SDK/${MACOS_SDK}" \
      CC_aarch64_apple_darwin="/opt/osxcross/target/bin/aarch64-apple-${DARWIN_VERSION}-clang" \
      AR_aarch64_apple_darwin="/opt/osxcross/target/bin/aarch64-apple-${DARWIN_VERSION}-ar" \
      CARGO_TARGET_AARCH64_APPLE_DARWIN_LINKER="/opt/osxcross/target/bin/aarch64-apple-${DARWIN_VERSION}-clang" \
      cargo build --release --manifest-path "$MANIFEST" --target aarch64-apple-darwin
    ;;
  *)
    echo "ERROR: unknown target '$TARGET'" >&2
    exit 1
    ;;
esac
