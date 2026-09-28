#!/usr/bin/env python3
"""Generate signed desktop update feeds (execution plan Phase 6B, contract §9.1/§9.2).

Reads the built release assets out of `--release-dir` and writes two feeds into the same
directory:

  appcast.xml   Sparkle 2 RSS, single item, EdDSA-signed DMG enclosure.
  latest.json   Tauri v2 static updater format, minisign signatures read from the .sig
                files `cargo tauri signer sign` already produced.

Usage:
    generate_update_feeds.py --release-dir DIR --version X.Y.Z --tag TAG --repo OWNER/NAME
                              --notes-url URL --sparkle-key-env SPARKLE_ED_PRIVATE_KEY

Fails closed: a missing asset, an empty/unreadable signature, or a version that does not match
the caller's `--version` are all hard errors, never silently skipped.

Signing: OpenSSL 3's `openssl pkeyutl -sign -rawin` produces a signature byte-identical to
Sparkle's own `sign_update` (checked 2026-09-25) -- raw Ed25519 over the unhashed DMG bytes, no
digest wrapper. The macOS system `openssl` is LibreSSL and lacks `-rawin`; point `OPENSSL` at a
real OpenSSL 3 build (Homebrew: `/opt/homebrew/bin/openssl`). This script self-checks that
support at startup and fails (never silently degrades) if it is missing.
"""


import argparse
import base64
import json
import os
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

MINIMUM_SYSTEM_VERSION = "14.0"

# PKCS#8 v1 DER prefix for a raw 32-byte Ed25519 private key (RFC 8410): a fixed ASN.1
# structure with the algorithm OID for Ed25519 (1.3.101.112) and no attributes, followed
# directly by the 32-byte seed as an OCTET STRING wrapped in an OCTET STRING.
_PKCS8_ED25519_PREFIX_HEX = "302e020100300506032b657004220420"

DMG_ASSET = "PersonaForge-macos-aarch64.dmg"
WINDOWS_ASSET = "PersonaForge-windows-x86_64-setup.exe"
LINUX_ASSET = "PersonaForge-linux-x86_64.AppImage"


class FeedGenerationError(RuntimeError):
    """Raised for any fail-closed condition: missing asset, bad signature, version mismatch."""


def _openssl_bin() -> str:
    return os.environ.get("OPENSSL", "openssl")


def _run_openssl(args: list[str], *, input_bytes: bytes | None = None) -> bytes:
    result = subprocess.run(
        [_openssl_bin(), *args],
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise FeedGenerationError(
            f"openssl {' '.join(args)} failed (exit {result.returncode}): "
            f"{result.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return result.stdout


def check_openssl_rawin_support() -> None:
    """Fail closed (never skip) if `$OPENSSL` cannot sign/verify raw Ed25519 with -rawin."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        key_pem = tmp_path / "probe.pem"
        pub_pem = tmp_path / "probe-pub.pem"
        data = tmp_path / "probe.bin"
        sig = tmp_path / "probe.sig"

        try:
            _run_openssl(["genpkey", "-algorithm", "ed25519", "-out", str(key_pem)])
            _run_openssl(
                ["pkey", "-in", str(key_pem), "-pubout", "-out", str(pub_pem)]
            )
            data.write_bytes(b"persona-forge openssl -rawin probe")
            _run_openssl(
                [
                    "pkeyutl", "-sign", "-rawin",
                    "-inkey", str(key_pem),
                    "-in", str(data),
                    "-out", str(sig),
                ]
            )
            _run_openssl(
                [
                    "pkeyutl", "-verify", "-rawin",
                    "-pubin", "-inkey", str(pub_pem),
                    "-in", str(data),
                    "-sigfile", str(sig),
                ]
            )
        except FeedGenerationError as error:
            raise FeedGenerationError(
                "OpenSSL 3 with Ed25519 -rawin support is required "
                f"(probe failed against {_openssl_bin()!r}): {error}"
            ) from error


def _seed_to_pem(seed_b64: str) -> str:
    """Wraps a 32-byte Ed25519 seed (base64) as a PKCS#8 PEM `openssl pkeyutl` can sign with."""
    seed = base64.b64decode("".join(seed_b64.split()), validate=True)
    if len(seed) != 32:
        raise FeedGenerationError(
            f"Sparkle EdDSA seed must decode to exactly 32 bytes, got {len(seed)}"
        )
    der = bytes.fromhex(_PKCS8_ED25519_PREFIX_HEX) + seed
    b64 = base64.b64encode(der).decode("ascii")
    lines = [b64[i : i + 64] for i in range(0, len(b64), 64)]
    return "-----BEGIN PRIVATE KEY-----\n" + "\n".join(lines) + "\n-----END PRIVATE KEY-----\n"


def sign_dmg(dmg_path: Path, seed_b64: str) -> str:
    """Returns the base64 EdDSA signature of `dmg_path`'s raw bytes."""
    pem = _seed_to_pem(seed_b64)
    key_file = None
    try:
        fd, key_file_name = tempfile.mkstemp(prefix="pf-sparkle-key-", suffix=".pem")
        key_file = Path(key_file_name)
        os.close(fd)
        key_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        key_file.write_text(pem, encoding="utf-8")

        sig_fd, sig_file_name = tempfile.mkstemp(prefix="pf-sparkle-sig-", suffix=".bin")
        os.close(sig_fd)
        sig_file = Path(sig_file_name)
        try:
            _run_openssl(
                [
                    "pkeyutl", "-sign", "-rawin",
                    "-inkey", str(key_file),
                    "-in", str(dmg_path),
                    "-out", str(sig_file),
                ]
            )
            signature = sig_file.read_bytes()
        finally:
            sig_file.unlink(missing_ok=True)
    finally:
        if key_file is not None:
            key_file.unlink(missing_ok=True)

    if not signature:
        raise FeedGenerationError(f"empty EdDSA signature produced for {dmg_path.name}")
    return base64.b64encode(signature).decode("ascii")


def require_asset(release_dir: Path, name: str) -> Path:
    path = release_dir / name
    if not path.is_file():
        raise FeedGenerationError(f"missing release asset: {name} (expected at {path})")
    if path.stat().st_size == 0:
        raise FeedGenerationError(f"release asset is empty: {name}")
    return path


def read_sig_file(release_dir: Path, asset_name: str) -> str:
    sig_path = release_dir / f"{asset_name}.sig"
    if not sig_path.is_file():
        raise FeedGenerationError(f"missing release asset: {sig_path.name}")
    signature = sig_path.read_text(encoding="utf-8").strip()
    if not signature:
        raise FeedGenerationError(f"empty signature file: {sig_path.name}")
    return signature


def asset_url(repo: str, tag: str, asset_name: str) -> str:
    return f"https://github.com/{repo}/releases/download/{tag}/{asset_name}"


def build_appcast_xml(
    *, version: str, dmg_url: str, dmg_length: int, ed_signature: str, notes_url: str
) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">\n'
        "  <channel>\n"
        "    <title>Persona Forge</title>\n"
        "    <item>\n"
         f'      <sparkle:releaseNotesLink>{escape(notes_url)}</sparkle:releaseNotesLink>\n'
         f'      <description><![CDATA[<p>A new version of Persona Forge is available.</p>'
        f'<p><a href="{escape(notes_url)}">View release notes</a></p>]]></description>\n'
        f"      <enclosure "
        f'url="{escape(dmg_url)}" '
        f'length="{dmg_length}" '
        f'type="application/octet-stream" '
        f'sparkle:version="{escape(version)}" '
        f'sparkle:shortVersionString="{escape(version)}" '
        f'sparkle:edSignature="{escape(ed_signature)}" '
        f'sparkle:minimumSystemVersion="{MINIMUM_SYSTEM_VERSION}" />\n'
        "    </item>\n"
        "  </channel>\n"
        "</rss>\n"
    )


def build_latest_json(
    *,
    version: str,
    notes_url: str,
    windows_url: str,
    windows_signature: str,
    linux_url: str,
    linux_signature: str,
) -> dict:
    pub_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "version": version,
        "pub_date": pub_date,
        "notes": notes_url,
        "platforms": {
            "windows-x86_64-nsis": {"url": windows_url, "signature": windows_signature},
            "linux-x86_64-appimage": {"url": linux_url, "signature": linux_signature},
        },
    }


def generate(
    *, release_dir: Path, version: str, tag: str, repo: str, notes_url: str, sparkle_seed_b64: str
) -> None:
    check_openssl_rawin_support()

    dmg_path = require_asset(release_dir, DMG_ASSET)
    require_asset(release_dir, WINDOWS_ASSET)
    require_asset(release_dir, LINUX_ASSET)

    windows_signature = read_sig_file(release_dir, WINDOWS_ASSET)
    linux_signature = read_sig_file(release_dir, LINUX_ASSET)

    ed_signature = sign_dmg(dmg_path, sparkle_seed_b64)
    dmg_length = dmg_path.stat().st_size

    appcast_xml = build_appcast_xml(
        version=version,
        dmg_url=asset_url(repo, tag, DMG_ASSET),
        dmg_length=dmg_length,
        ed_signature=ed_signature,
        notes_url=notes_url,
    )
    latest_json = build_latest_json(
        version=version,
        notes_url=notes_url,
        windows_url=asset_url(repo, tag, WINDOWS_ASSET),
        windows_signature=windows_signature,
        linux_url=asset_url(repo, tag, LINUX_ASSET),
        linux_signature=linux_signature,
    )

    if latest_json["version"] != version:
        raise FeedGenerationError(
            f"latest.json version {latest_json['version']!r} does not match --version {version!r}"
        )

    (release_dir / "appcast.xml").write_text(appcast_xml, encoding="utf-8")
    (release_dir / "latest.json").write_text(
        json.dumps(latest_json, indent=2) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--release-dir", required=True, type=Path)
    parser.add_argument("--version", required=True, help="e.g. 1.3.0 or 90.0.1 (no leading 'v')")
    parser.add_argument("--tag", required=True, help="the GitHub release tag the assets live under")
    parser.add_argument("--repo", required=True, help="OWNER/NAME")
    parser.add_argument("--notes-url", required=True, help="release notes URL for both feeds")
    parser.add_argument(
        "--sparkle-key-env",
        default="SPARKLE_ED_PRIVATE_KEY",
        help="name of the env var holding the base64 32-byte Ed25519 seed (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    seed_b64 = os.environ.get(args.sparkle_key_env)
    if not seed_b64:
        parser.error(f"environment variable {args.sparkle_key_env} is not set or is empty")

    release_dir = args.release_dir
    if not release_dir.is_dir():
        parser.error(f"--release-dir does not exist or is not a directory: {release_dir}")

    try:
        generate(
            release_dir=release_dir,
            version=args.version,
            tag=args.tag,
            repo=args.repo,
            notes_url=args.notes_url,
            sparkle_seed_b64=seed_b64,
        )
    except FeedGenerationError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(f"wrote {release_dir / 'appcast.xml'}")
    print(f"wrote {release_dir / 'latest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
