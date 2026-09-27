#!/usr/bin/env bash
# Sign, notarize, and staple a macOS .app or DMG on an ephemeral Linux runner.
# Usage: sign_macos.sh <app|dmg> <input> <output>
set -euo pipefail

KIND="${1:?Usage: sign_macos.sh <app|dmg> <input> <output>}"
INPUT="${2:?Usage: sign_macos.sh <app|dmg> <input> <output>}"
OUTPUT="${3:?Usage: sign_macos.sh <app|dmg> <input> <output>}"
OUTPUT="$(python3 -c 'import os, sys; print(os.path.abspath(sys.argv[1]))' "$OUTPUT")"

case "$KIND" in
  app|dmg) ;;
  *) echo "FAIL: kind must be app or dmg, got: $KIND" >&2; exit 2 ;;
esac
[[ -s "$INPUT" ]] || { echo "FAIL: input is missing or empty: $INPUT" >&2; exit 1; }
: "${RUNNER_TEMP:?RUNNER_TEMP is required}"
: "${MACOS_KEY_PEM:?MACOS_KEY_PEM is required}"
: "${MACOS_CERT_PEM:?MACOS_CERT_PEM is required}"
: "${APPLE_ISSUER_ID:?APPLE_ISSUER_ID is required}"
: "${APPLE_KEY_ID:?APPLE_KEY_ID is required}"
: "${APPLE_PRIVATE_KEY:?APPLE_PRIVATE_KEY is required}"
command -v rcodesign >/dev/null || { echo "FAIL: rcodesign is not installed" >&2; exit 1; }
command -v openssl >/dev/null || { echo "FAIL: openssl is not installed" >&2; exit 1; }

SIGN_DIR="$RUNNER_TEMP/pf-sign"
WORK_DIR=$(mktemp -d "$RUNNER_TEMP/pf-sign-work.XXXXXX")
mkdir -p "$SIGN_DIR"
chmod 700 "$SIGN_DIR"
trap 'rm -rf "$WORK_DIR"' EXIT
umask 077
printf '%s\n' "$MACOS_KEY_PEM" > "$SIGN_DIR/key.pem"
printf '%s\n' "$MACOS_CERT_PEM" > "$SIGN_DIR/cert.pem"
printf '%s\n' "$APPLE_PRIVATE_KEY" > "$SIGN_DIR/AuthKey.p8"
rcodesign encode-app-store-connect-api-key \
  -o "$SIGN_DIR/key.json" \
  "$APPLE_ISSUER_ID" "$APPLE_KEY_ID" "$SIGN_DIR/AuthKey.p8"

SUBJECT=$(openssl x509 -in "$SIGN_DIR/cert.pem" -noout -subject -nameopt RFC2253)
TEAM_ID=$(printf '%s\n' "$SUBJECT" | sed -n 's/.*\(^\|,\)OU=\([^,]*\).*/\2/p')
[[ -n "$TEAM_ID" && "$TEAM_ID" != "not set" ]] || {
  echo "FAIL: could not extract certificate Team ID from subject: $SUBJECT" >&2
  exit 1
}
echo "Apple Developer ID Team ID: $TEAM_ID"
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  printf 'team_id=%s\n' "$TEAM_ID" >> "$GITHUB_OUTPUT"
fi

mkdir -p "$(dirname "$OUTPUT")"
case "$KIND" in
  app)
    unzip -q "$INPUT" -d "$WORK_DIR"
    find "$WORK_DIR" -name '._*' -type f -delete
    APP="$WORK_DIR/Persona Forge.app"
    [[ -d "$APP" ]] || { echo "FAIL: zipped input does not contain Persona Forge.app" >&2; exit 1; }
    rcodesign sign \
      --pem-file "$SIGN_DIR/key.pem" \
      --pem-file "$SIGN_DIR/cert.pem" \
      --for-notarization \
      --entitlements-xml-file desktop/entitlements.plist \
      "$APP"
    rcodesign notary-submit --api-key-file "$SIGN_DIR/key.json" --wait --staple "$APP"
    rm -f "$OUTPUT"
    (cd "$WORK_DIR" && zip -q -r -y "$OUTPUT" "Persona Forge.app")
    [[ -s "$OUTPUT" ]] || { echo "FAIL: signed app archive was not produced: $OUTPUT" >&2; exit 1; }
    ;;
  dmg)
    cp "$INPUT" "$OUTPUT"
    rcodesign sign \
      --pem-file "$SIGN_DIR/key.pem" \
      --pem-file "$SIGN_DIR/cert.pem" \
      "$OUTPUT"
    rcodesign notary-submit --api-key-file "$SIGN_DIR/key.json" --wait --staple "$OUTPUT"
    [[ -s "$OUTPUT" ]] || { echo "FAIL: signed DMG was not produced: $OUTPUT" >&2; exit 1; }
    ;;
esac
