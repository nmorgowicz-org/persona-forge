#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Serve the spike test page on http://127.0.0.1:8318/ for the owner's 1D webview checks.

Run it from anywhere (no clone needed), then press the spike app's "Go" button:

    uv run https://raw.githubusercontent.com/nmorgowicz-org/persona-forge/spike/desktop/spike/desktop-shell/scripts/serve_testpage.py

It downloads the test page from the same branch (or uses the local checkout's copy when run from
the repo), writes a 1 s 440 Hz `tone.wav`, and also `tone.mp3` when `ffmpeg` is on PATH (without
it, the page's MP3 row cannot play; test MP3 on the real SPA's Speak page instead). Ctrl+C stops.
"""
import functools
import http.server
import math
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.request
import wave

PORT = 8318
PAGE_URL = ("https://raw.githubusercontent.com/nmorgowicz-org/persona-forge/spike/desktop/"
            "spike/desktop-shell/testpage/index.html")


def write_tone(path: pathlib.Path) -> None:
    rate = 44100
    frames = b"".join(
        struct.pack("<h", int(0.3 * 32767 * math.sin(2 * math.pi * 440 * i / rate)))
        for i in range(rate)
    )
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)


def main() -> None:
    site = pathlib.Path(tempfile.mkdtemp(prefix="spike-testpage-"))
    local = pathlib.Path(__file__).resolve().parent.parent / "testpage" / "index.html"
    try:
        if local.is_file():
            shutil.copy(local, site / "index.html")
        else:
            with urllib.request.urlopen(PAGE_URL, timeout=30) as r:
                (site / "index.html").write_bytes(r.read())
    except OSError as exc:
        sys.exit(f"cannot get the test page: {exc}")

    write_tone(site / "tone.wav")
    if shutil.which("ffmpeg"):
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(site / "tone.wav"),
                        "-codec:a", "libmp3lame", str(site / "tone.mp3")], check=True)
        mp3 = "tone.mp3 written"
    else:
        mp3 = "no ffmpeg: MP3 row unavailable on this page"

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site))
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    except OSError as exc:
        sys.exit(f"cannot listen on 127.0.0.1:{PORT} (already in use?): {exc}")
    print(f"serving {site} on http://127.0.0.1:{PORT}/ ({mp3}); Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
