#!/usr/bin/env bash
# Phase 7 cross-build preflight for the Persona Forge launcher (docs/plans/20260829-no_more_docker_requirement.md).
#
# Unlike Local LLM Foundry's launcher, persona-forge-launcher is a plain CLI binary with zero GUI
# dependencies (no webview/tray), so this preflight only needs a Rust cross toolchain per target -
# no webkit2gtk/pkg-config/docker checks. Fails closed: the first missing tool aborts the build.
set -euo pipefail

echo "Running launcher release preflight checks..."

TARGET="${1:?Usage: launcher_preflight.sh <target> [toolchain]}"
RUST_TOOLCHAIN="${2:-${RUSTUP_TOOLCHAIN:-}}"

case "$TARGET" in
  x86_64-unknown-linux-gnu|x86_64-pc-windows-gnu|aarch64-apple-darwin) ;;
  *) echo "FAIL: unsupported launcher target: $TARGET"; exit 1 ;;
esac

command -v cargo >/dev/null || { echo "FAIL: cargo not found"; exit 1; }
command -v rustup >/dev/null || { echo "FAIL: rustup not found"; exit 1; }

if [[ -n "$RUST_TOOLCHAIN" ]]; then
  installed_targets=$(rustup target list --toolchain "$RUST_TOOLCHAIN" --installed)
else
  installed_targets=$(rustup target list --installed)
fi
grep -qx "$TARGET" <<<"$installed_targets" \
  || { echo "FAIL: rustup target ${TARGET} not installed${RUST_TOOLCHAIN:+ for toolchain ${RUST_TOOLCHAIN}}"; exit 1; }

case "$TARGET" in
  x86_64-unknown-linux-gnu)
    command -v cc >/dev/null \
      || { echo "FAIL: cc not found (needed for ${TARGET})"; exit 1; }
    ;;
  x86_64-pc-windows-gnu)
    command -v x86_64-w64-mingw32-gcc >/dev/null \
      || { echo "FAIL: x86_64-w64-mingw32-gcc not found (needed for ${TARGET})"; exit 1; }
    ;;
  aarch64-apple-darwin)
    DARWIN_VERSION=$(ls /opt/osxcross/target/bin/aarch64-apple-darwin*-clang 2>/dev/null \
      | head -1 | grep -oP 'darwin[\d.]+' || true)
    MACOS_SDK=$(ls -d /opt/osxcross/target/SDK/MacOSX*.sdk 2>/dev/null \
      | sort -V | tail -1 | xargs -r basename)
    if [[ -z "$DARWIN_VERSION" || -z "$MACOS_SDK" ]]; then
      echo "FAIL: could not detect osxcross toolchain in /opt/osxcross/target/"
      echo "  clang binaries found: $(ls /opt/osxcross/target/bin/*-clang 2>/dev/null || echo none)"
      echo "  SDKs found: $(ls -d /opt/osxcross/target/SDK/*.sdk 2>/dev/null || echo none)"
      exit 1
    fi
    for tool in clang ar ranlib; do
      bin="/opt/osxcross/target/bin/aarch64-apple-${DARWIN_VERSION}-${tool}"
      test -x "$bin" || { echo "FAIL: missing osxcross tool: $bin"; exit 1; }
    done
    test -d "/opt/osxcross/target/SDK/${MACOS_SDK}" \
      || { echo "FAIL: missing SDK dir: /opt/osxcross/target/SDK/${MACOS_SDK}"; exit 1; }
    ;;
esac

echo "Launcher preflight passed for ${TARGET}${RUST_TOOLCHAIN:+ with toolchain ${RUST_TOOLCHAIN}}."
