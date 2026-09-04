#!/usr/bin/env bash
# Fetch and verify one pinned uv release binary for bundling into a launcher archive (Phase 7,
# "Launcher behavior" item 8: verify uv's redistribution license and official checksum source,
# fetch the pinned target binary during build, verify SHA-256, never `curl | sh`).
#
# License: uv (github.com/astral-sh/uv) is dual-licensed MIT OR Apache-2.0, both of which permit
# unmodified redistribution of the built binary - reviewed at pin time, not re-checked per build.
#
# Checksum source: astral-sh/uv publishes a `<asset>.sha256` file alongside every release asset on
# GitHub Releases (sha256sum format: "<hex>  <filename>"). That published file is the verification
# source of truth here - this script never invents or downloads a checksum from anywhere else.
set -euo pipefail

UV_VERSION="${1:?Usage: fetch_uv_binary.sh <uv-version> <uv-release-target> <out-dir>}"
UV_TARGET="${2:?Usage: fetch_uv_binary.sh <uv-version> <uv-release-target> <out-dir>}"
OUT_DIR="${3:?Usage: fetch_uv_binary.sh <uv-version> <uv-release-target> <out-dir>}"

case "$UV_TARGET" in
  *windows*) ARCHIVE_EXT="zip"; BIN_NAME="uv.exe" ;;
  *) ARCHIVE_EXT="tar.gz"; BIN_NAME="uv" ;;
esac

ASSET="uv-${UV_TARGET}.${ARCHIVE_EXT}"
BASE_URL="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}"

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

echo "Fetching ${ASSET} (uv ${UV_VERSION})..."
curl --fail --location --silent --show-error -o "${WORK_DIR}/${ASSET}" "${BASE_URL}/${ASSET}"
curl --fail --location --silent --show-error -o "${WORK_DIR}/${ASSET}.sha256" "${BASE_URL}/${ASSET}.sha256"

echo "Verifying published SHA-256 checksum..."
(cd "$WORK_DIR" && shasum -a 256 -c "${ASSET}.sha256")

mkdir -p "$OUT_DIR"
case "$ARCHIVE_EXT" in
  zip)
    unzip -o -q "${WORK_DIR}/${ASSET}" -d "$WORK_DIR/extracted"
    ;;
  tar.gz)
    mkdir -p "$WORK_DIR/extracted"
    tar -xzf "${WORK_DIR}/${ASSET}" -C "$WORK_DIR/extracted"
    ;;
esac

found=$(find "$WORK_DIR/extracted" -type f -name "$BIN_NAME" -print -quit)
if [ -z "$found" ]; then
  echo "FAIL: ${BIN_NAME} not found inside ${ASSET}" >&2
  exit 1
fi
cp "$found" "${OUT_DIR}/${BIN_NAME}"
chmod +x "${OUT_DIR}/${BIN_NAME}" 2>/dev/null || true

echo "Verified and staged: ${OUT_DIR}/${BIN_NAME}"
