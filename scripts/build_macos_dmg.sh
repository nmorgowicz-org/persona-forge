#!/usr/bin/env bash
# Build the macOS DMG from an unsigned .app (execution plan Phase 4, Gate 4).
#
# Usage: build_macos_dmg.sh <app-path> <dmg-path>
#
# Stages a directory containing the .app and an /Applications symlink, then
# creates a compressed (UDZO) DMG. Fails closed: any hdiutil error fails the
# script, and a partial output DMG is removed.
set -euo pipefail

APP_PATH="${1:?Usage: build_macos_dmg.sh <app-path> <dmg-path>}"
DMG_PATH="${2:?Usage: build_macos_dmg.sh <app-path> <dmg-path>}"

if [ ! -d "$APP_PATH" ]; then
  echo "FAIL: .app bundle is missing: $APP_PATH" >&2
  exit 1
fi
if [ "${APP_PATH##*.}" != "app" ]; then
  echo "FAIL: not a .app bundle: $APP_PATH" >&2
  exit 1
fi

STAGING=$(mktemp -d)
trap 'rm -rf "$STAGING"' EXIT

cp -R "$APP_PATH" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

rm -f "$DMG_PATH"
hdiutil create \
  -volname "Persona Forge" \
  -srcfolder "$STAGING" \
  -format UDZO \
  -fs HFS+ \
  "$DMG_PATH"

if [ ! -s "$DMG_PATH" ]; then
  echo "FAIL: hdiutil produced no DMG at $DMG_PATH" >&2
  exit 1
fi

echo "DMG created: $DMG_PATH ($(du -h "$DMG_PATH" | cut -f1))"
