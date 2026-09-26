#!/usr/bin/env python3
"""Write a Tauri updater static `latest.json` (spike 1C task 3; contract §9.1 shape).

usage: make_latest_json.py --version V --out PATH
                           --platform KEY URL SIGFILE [--platform KEY URL SIGFILE ...]

`signature` is the verbatim content of the `.sig` file written by `cargo tauri signer sign`.
Fails closed on an empty or missing signature file.
"""
import argparse
import datetime
import json
import sys


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--platform", nargs=3, action="append", required=True,
                    metavar=("KEY", "URL", "SIGFILE"))
    args = ap.parse_args()

    platforms = {}
    for key, url, sigfile in args.platform:
        try:
            with open(sigfile, encoding="ascii") as f:
                sig = f.read().strip()
        except OSError as exc:
            sys.exit(f"cannot read signature {sigfile}: {exc}")
        if not sig:
            sys.exit(f"empty signature file: {sigfile}")
        platforms[key] = {"signature": sig, "url": url}

    doc = {
        "version": args.version,
        "notes": "desktop spike update test",
        "pub_date": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platforms": platforms,
    }
    try:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)
            f.write("\n")
    except OSError as exc:
        sys.exit(f"cannot write {args.out}: {exc}")
    print(f"wrote {args.out}: version {args.version}, platforms {sorted(platforms)}")


if __name__ == "__main__":
    main()
