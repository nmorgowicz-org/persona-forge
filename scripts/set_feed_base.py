#!/usr/bin/env python3
"""Set desktop updater feeds for a one-off build without changing production defaults."""

from __future__ import annotations

import argparse
import json
import plistlib
from pathlib import Path
from urllib.parse import urlparse

PRODUCTION_FEED_BASE = "https://github.com/nmorgowicz-org/persona-forge/releases/latest/download"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plist", type=Path, help="Info.plist to update for Sparkle")
    parser.add_argument("--tauri-config", type=Path, help="write a Tauri updater endpoint override")
    parser.add_argument("--base", default=PRODUCTION_FEED_BASE)
    args = parser.parse_args()

    if args.plist is None and args.tauri_config is None:
        parser.error("provide --plist, --tauri-config, or both")

    base = args.base.rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "https" or not parsed.netloc:
        parser.error("--base must be an HTTPS URL")

    if args.plist is not None:
        with args.plist.open("rb") as stream:
            values = plistlib.load(stream)
        values["SUFeedURL"] = f"{base}/appcast.xml"
        with args.plist.open("wb") as stream:
            plistlib.dump(values, stream, sort_keys=True)

    if args.tauri_config is not None:
        args.tauri_config.parent.mkdir(parents=True, exist_ok=True)
        args.tauri_config.write_text(
            json.dumps({"plugins": {"updater": {"endpoints": [f"{base}/latest.json"]}}}),
            encoding="utf-8",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
