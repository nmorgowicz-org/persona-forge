#!/usr/bin/env python3
"""Drive the Linux AppImage through tauri-driver (spike 1C task 5).

usage: uv run --with selenium python gui_check.py <appimage> <app-stderr-log>

Expects tauri-driver on 127.0.0.1:4444 and the test page on http://127.0.0.1:8318/.
<app-stderr-log> is where tauri-driver's stderr (and so the app's [nav]/[download] lines) goes.

Order matters: the download checks open a blocking native Save dialog that nobody answers
under Xvfb, so they run last.
"""
import sys
import time

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.options import ArgOptions
from selenium.webdriver.support.ui import WebDriverWait

DRIVER = "http://127.0.0.1:4444"
TEST_URL = "http://127.0.0.1:8318/"
failures: list[str] = []


def check(cond: bool, what: str) -> None:
    print(("PASS " if cond else "FAIL ") + what, flush=True)
    if not cond:
        failures.append(what)


def session(appimage: str) -> webdriver.Remote:
    opts = ArgOptions()
    opts.set_capability("browserName", "wry")
    opts.set_capability("tauri:options", {"application": appimage})
    return webdriver.Remote(command_executor=DRIVER, options=opts)


def open_test_page(d: webdriver.Remote) -> bool:
    """Click the splash button; True when the webview reached the test origin."""
    WebDriverWait(d, 60).until(lambda x: x.find_elements(By.ID, "go"))
    d.find_element(By.ID, "go").click()
    try:
        WebDriverWait(d, 20).until(lambda x: x.current_url == TEST_URL)
        return True
    except WebDriverException:
        return False


def counter(d: webdriver.Remote) -> int:
    WebDriverWait(d, 10).until(lambda x: x.find_element(By.ID, "count").text.startswith("loads:"))
    return int(d.find_element(By.ID, "count").text.split(":")[1])


def audio_advances(d: webdriver.Remote, el_id: str) -> str:
    """play() the element; return 'ok <t>' when currentTime passes 0.2 s within 3 s."""
    d.set_script_timeout(20)
    return d.execute_async_script(
        """
        const [id, done] = arguments;
        const el = document.getElementById(id);
        const start = () => el.play().then(() => {
          const t0 = Date.now();
          const tick = () => {
            if (el.currentTime > 0.2) return done('ok ' + el.currentTime.toFixed(2));
            if (Date.now() - t0 > 3000) return done('stalled at ' + el.currentTime);
            setTimeout(tick, 100);
          };
          tick();
        }).catch(e => done('play() rejected: ' + e));
        // #wav gets its blob src asynchronously (OfflineAudioContext render)
        const wait = (n) => (el.src && !el.src.endsWith('#')) ? start()
          : n > 50 ? done('no src') : setTimeout(() => wait(n + 1), 100);
        wait(0);
        """,
        el_id,
    )


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(f"usage: {sys.argv[0]} <appimage> <app-stderr-log>")
    appimage, log_path = sys.argv[1:]

    # ── session 1: navigation, external link, audio ─────────────────────────
    d = session(appimage)
    try:
        check(open_test_page(d), f"splash button -> {TEST_URL} (got {d.current_url})")
        first = counter(d)
        check(first >= 1, f"localStorage counter present (loads: {first})")

        d.find_element(By.CSS_SELECTOR, 'a[href="https://example.com"]:not([target])').click()
        time.sleep(2)
        check(d.current_url == TEST_URL, f"same-window external link leaves URL unchanged (got {d.current_url})")

        for el_id in ("wav", "mp3"):
            res = audio_advances(d, el_id)
            check(res.startswith("ok"), f"#{el_id} plays and advances past 0.2 s ({res})")
    finally:
        d.quit()

    # ── session 2: restart -> counter persisted; then downloads (last) ──────
    time.sleep(2)
    d = session(appimage)
    try:
        check(open_test_page(d), "second launch reaches the test page")
        second = counter(d)
        check(second == first + 1, f"localStorage survives restart ({first} -> {second})")

        d.find_element(By.ID, "dl-blob").click()
        time.sleep(3)
        d.find_element(By.ID, "dl-http").click()
        time.sleep(3)
    finally:
        try:
            d.quit()
        except WebDriverException:
            pass  # the unanswered Save dialog may hold the app; the log is the evidence

    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            log = f.read()
    except OSError as exc:
        sys.exit(f"cannot read {log_path}: {exc}")
    # the external-link click above must have logged OpenExternal; without it the log is not
    # capturing app stderr and "no Deny" below would pass vacuously
    check("[nav] OpenExternal https://example.com" in log,
          "app stderr is captured ([nav] OpenExternal logged for the external link)")
    denies = [ln for ln in log.splitlines() if "[nav] Deny" in ln]
    check(not denies, f"no [nav] Deny lines (found: {denies})")
    requested = [ln for ln in log.splitlines() if "[download] Requested" in ln]
    print(f"on_download Requested lines: {requested}")

    if failures:
        sys.exit(f"{len(failures)} GUI check(s) failed")
    print("all GUI checks passed")


if __name__ == "__main__":
    main()
