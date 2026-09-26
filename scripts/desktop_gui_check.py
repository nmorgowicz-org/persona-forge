#!/usr/bin/env python3
"""Desktop GUI check on Linux (execution plan Phase 4, Gate 4, contract D17/D20/D21).

Runs against `tauri-driver` (WebKitWebDriver) started by the caller under
`dbus-run-session xvfb-run -a`, driving the bundled AppImage end to end:

- within 180s the main window lands on http://127.0.0.1:<port>/ (port read from
  <state>/desktop/settings.json) and the SPA root element #root has children
- the navigation guard leaves the URL unchanged after a JS navigation to an
  external origin (nav.rs Deny)
- after POST /ui/preferences {"values":{"theme":"teal"}} and a reload,
  document.documentElement.dataset.theme == "teal" (D17 end to end)
- document.documentElement.dataset.desktop == "linux" (D20 marker reaches the SPA)
- downloads (D21, no model needed): two clicks on an injected
  <a download href="/health"> produce two `download destination` log lines in
  <state>/desktop/logs/desktop.log naming different paths, both files exist and
  parse as JSON, and the app still answers
- ends the session with SIGTERM (the contract 6.2 signal path), then asserts
  within 15s that no persona_forge.app:app server survives and the port is free

Usage:
  uv run --with selenium==4.35.0 --with requests python scripts/desktop_gui_check.py \
      --app <AppImage> --state <PERSONA_FORGE_HOME> [--driver-url http://127.0.0.1:4444]
"""

from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import time
from pathlib import Path

import requests
from selenium import webdriver
from selenium.common.exceptions import WebDriverException

NAV_TIMEOUT_S = 180
DOWNLOAD_TIMEOUT_S = 15
SHUTDOWN_TIMEOUT_S = 15
SERVER_PROCESS_PATTERN = "persona_forge.app:app"
APP_PROCESS_PATTERN = "persona-forge-desktop"
THEME = "teal"  # non-default (theme.ts default is violet)


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    sys.exit(1)


def read_port(state: Path) -> int:
    settings = state / "desktop" / "settings.json"
    deadline = time.monotonic() + NAV_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
            port = int(data["port"])
            if port > 0:
                return port
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            pass
        time.sleep(1)
    fail(f"no usable port appeared in {settings} within {NAV_TIMEOUT_S}s")
    raise AssertionError("unreachable")  # fail() exits


def wait_for_spa(driver: webdriver.Remote, origin: str) -> None:
    deadline = time.monotonic() + NAV_TIMEOUT_S
    last_error = "not started"
    while time.monotonic() < deadline:
        try:
            if driver.current_url.startswith(origin + "/") or driver.current_url == origin:
                children = driver.execute_script(
                    "return document.getElementById('root') !== null"
                    " && document.getElementById('root').children.length > 0"
                )
                if children:
                    return
            last_error = f"url is {driver.current_url!r}, root not populated"
        except WebDriverException as exc:
            last_error = str(exc).splitlines()[0]
        time.sleep(2)
    fail(f"SPA did not load at {origin} within {NAV_TIMEOUT_S}s: {last_error}")


def check_navigation_guard(driver: webdriver.Remote, origin: str) -> None:
    driver.execute_script("window.location.href = 'https://example.com'")
    time.sleep(3)
    if not driver.current_url.startswith(origin):
        fail(f"navigation guard did not hold: url is now {driver.current_url!r}")
    print("navigation guard holds")


def check_theme_round_trip(driver: webdriver.Remote, origin: str) -> None:
    response = requests.post(
        f"{origin}/ui/preferences",
        json={"values": {"theme": THEME}},
        timeout=10,
    )
    if response.status_code != 200:
        fail(f"POST /ui/preferences returned {response.status_code}: {response.text[:200]}")
    driver.refresh()
    wait_for_spa(driver, origin)
    theme = None
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        theme = driver.execute_script("return document.documentElement.dataset.theme")
        if theme == THEME:
            break
        time.sleep(1)
    else:
        fail(f"theme never became {THEME!r} after reload (dataset.theme={theme!r})")
    desktop = driver.execute_script("return document.documentElement.dataset.desktop")
    if desktop != "linux":
        fail(f"data-desktop marker is {desktop!r}, expected 'linux'")
    # Cleanup: the theme pref lives in the shared PERSONA_FORGE_HOME; reset it so the
    # check is repeatable against the same state dir.
    requests.post(
        f"{origin}/ui/preferences",
        json={"values": {"theme": "violet"}},
        timeout=10,
    ).raise_for_status()
    print(f"theme round-trip ({THEME}) and data-desktop=linux hold")


def check_downloads(driver: webdriver.Remote, origin: str, state: Path) -> None:
    driver.execute_script(
        "const a = document.createElement('a');"
        "a.id='pf-dl-test'; a.download='health.json'; a.href='/health';"
        "document.body.appendChild(a);"
    )
    driver.execute_script("document.getElementById('pf-dl-test').click()")
    time.sleep(1)
    driver.execute_script("document.getElementById('pf-dl-test').click()")

    log_file = state / "desktop" / "logs" / "desktop.log"
    deadline = time.monotonic() + DOWNLOAD_TIMEOUT_S
    destinations: list[str] = []
    while time.monotonic() < deadline:
        try:
            destinations = [
                line.rsplit(" -> ", 1)[1].strip()
                for line in log_file.read_text(encoding="utf-8", errors="replace").splitlines()
                if "download destination" in line and "/health" in line
            ]
            if len(destinations) >= 2:
                break
        except OSError:
            pass
        time.sleep(1)
    if len(destinations) < 2:
        fail(f"expected 2 'download destination' log lines in {log_file}, found {len(destinations)}")
    if len(set(destinations[-2:])) != 2:
        fail(f"both downloads went to the same path: {destinations[-2:]}")
    for dest in destinations[-2:]:
        path = Path(dest)
        if not path.is_file():
            fail(f"download destination does not exist: {path}")
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            fail(f"download destination {path} is not JSON: {exc}")
    if driver.execute_script("return 1") != 1:
        fail("app stopped answering after downloads")
    print("downloads produce two distinct parsed files; app still answers")


def shutdown_and_verify(state: Path) -> None:
    pids = subprocess.run(
        ["pgrep", "-f", APP_PROCESS_PATTERN], capture_output=True, text=True
    ).stdout.split()
    for pid in pids:
        try:
            subprocess.run(["kill", "-TERM", pid], check=False)
        except OSError:
            pass

    deadline = time.monotonic() + SHUTDOWN_TIMEOUT_S
    while time.monotonic() < deadline:
        server = subprocess.run(
            ["pgrep", "-f", SERVER_PROCESS_PATTERN], capture_output=True, text=True
        ).stdout.split()
        port = None
        try:
            port = int(json.loads((state / "desktop" / "settings.json").read_text())["port"])
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            pass
        if not server and port is not None:
            probe = subprocess.run(
                ["bash", "-c", f"exec <>/dev/tcp/127.0.0.1/{port}"], capture_output=True
            )
            if probe.returncode != 0:
                print("SIGTERM shutdown: no server left, port free")
                return
        time.sleep(1)
    fail(f"server or app still alive after SIGTERM within {SHUTDOWN_TIMEOUT_S}s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, help="path to the PersonaForge AppImage")
    parser.add_argument("--state", required=True, help="PERSONA_FORGE_HOME used by the app")
    parser.add_argument("--driver-url", default="http://127.0.0.1:4444")
    args = parser.parse_args()

    app = Path(args.app).resolve()
    state = Path(args.state).resolve()
    if not app.is_file():
        fail(f"app bundle is missing: {app}")
    if not state.is_dir():
        fail(f"state dir is missing: {state}")

    # Bare options: ChromeOptions would add browserName:"chrome" + goog:chromeOptions to
    # alwaysMatch, which tauri-driver's capability matcher rejects ("Failed to match
    # capabilities" — Phase 4 run 6).
    from selenium.webdriver.common.options import BaseOptions

    options = BaseOptions()
    options.set_capability("tauri:options", {"application": str(app)})
    driver = webdriver.Remote(command_executor=args.driver_url, options=options)
    try:
        port = read_port(state)
        origin = f"http://127.0.0.1:{port}"
        wait_for_spa(driver, origin)
        print(f"SPA loaded at {origin}")
        check_navigation_guard(driver, origin)
        check_theme_round_trip(driver, origin)
        check_downloads(driver, origin, state)
    finally:
        try:
            driver.quit()
        except WebDriverException:
            pass
    shutdown_and_verify(state)
    print("PASS: desktop GUI check")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    main()
