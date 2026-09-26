#!/usr/bin/env python3
"""Assert the outcome of `--ci-update` on Linux (spike 1C task 4; contract §6.12).

usage: assert_ci_update.py <out.json> <good|badsig> <appimage>

good:   ok true,  phase "installed", to_version 0.1.1, and the AppImage on disk now
        prints "desktop-spike 0.1.1" for --version (the updater replaced the file).
badsig: ok false, phase "verify" (signature rejected), and the file still prints 0.1.0.
"""
import json
import subprocess
import sys

FROM, TO = "0.1.0", "0.1.1"


def version_of(appimage: str) -> str:
    out = subprocess.run([appimage, "--version"], capture_output=True, text=True, timeout=120)
    return out.stdout.strip()


def main() -> None:
    if len(sys.argv) != 4 or sys.argv[2] not in ("good", "badsig"):
        sys.exit(f"usage: {sys.argv[0]} <out.json> <good|badsig> <appimage>")
    out_path, mode, appimage = sys.argv[1:]
    try:
        with open(out_path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError) as exc:
        sys.exit(f"cannot read {out_path}: {exc}")
    print(f"out.json: {json.dumps(d)}")

    failures = []

    def check(cond: bool, what: str) -> None:
        print(("PASS " if cond else "FAIL ") + what)
        if not cond:
            failures.append(what)

    check(d.get("from_version") == FROM, f"from_version == {FROM}")
    if mode == "good":
        check(isinstance(d.get("ok"), bool) and d["ok"], "ok is true")
        check(d.get("phase") == "installed", 'phase == "installed"')
        check(d.get("to_version") == TO, f"to_version == {TO}")
        on_disk = version_of(appimage)
        check(on_disk == f"desktop-spike {TO}", f"file on disk prints {TO} (got {on_disk!r})")
    else:
        check(isinstance(d.get("ok"), bool) and not d["ok"], "ok is false")
        check(d.get("phase") == "verify", 'phase == "verify" (signature rejected)')
        check(bool(d.get("error")), "error text present")
        on_disk = version_of(appimage)
        check(on_disk == f"desktop-spike {FROM}", f"file on disk still prints {FROM} (got {on_disk!r})")

    if failures:
        sys.exit(f"{len(failures)} assertion(s) failed")
    print(f"all {mode} assertions passed")


if __name__ == "__main__":
    main()
