#!/usr/bin/env python3
"""Drive the Linux AppImage through tauri-driver (spike 1C task 5).

usage: uv run --with selenium python gui_check.py <full|ask> <appimage> <app-stderr-log> <download-dir>

Expects tauri-driver on 127.0.0.1:4444 and the test page on http://127.0.0.1:8318/.
<app-stderr-log> is where tauri-driver's stderr (and so the app's [nav]/[download] lines) goes.

full: navigation, audio, localStorage across a restart, and downloads saved straight to
      <download-dir> (the app must run with SPIKE_DOWNLOAD_DIR=<download-dir>).
ask:  the app runs with SPIKE_ASK_WHERE_TO_SAVE=1; after a download its Save dialog is open and
      unanswered, and the app must still answer WebDriver (no main-thread deadlock).
"""
import pathlib
import sys
import time

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.options import ArgOptions
from selenium.webdriver.remote.client_config import ClientConfig
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
    # bounded HTTP timeout: a hung app must fail the check, not freeze the job
    return webdriver.Remote(options=opts, client_config=ClientConfig(DRIVER, timeout=60))


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


def read_log(log_path: str) -> str:
    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError as exc:
        sys.exit(f"cannot read {log_path}: {exc}")


def wait_for(cond, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.5)
    return cond()


def full(appimage: str, log_path: str, dl_dir: pathlib.Path) -> None:
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

    # ── session 2: restart -> counter persisted; downloads straight to disk ─
    time.sleep(2)
    d = session(appimage)
    try:
        check(open_test_page(d), "second launch reaches the test page")
        second = counter(d)
        check(second == first + 1, f"localStorage survives restart ({first} -> {second})")

        d.find_element(By.ID, "dl-blob").click()
        d.find_element(By.ID, "dl-http").click()
        files = lambda: sorted(p.name for p in dl_dir.glob("*.wav"))  # noqa: E731
        wait_for(lambda: len(files()) >= 2, 15)
        got = files()
        check(got == ["tone (1).wav", "tone.wav"], f"both downloads saved with unique names (got {got})")
        for name in got:
            head = (dl_dir / name).read_bytes()[:4]
            check(head == b"RIFF", f"{name} is a WAV file (starts with {head!r})")
        check(d.execute_script("return 1") == 1, "app still responsive after downloads")
    finally:
        d.quit()

    log = read_log(log_path)
    # without this line the log is not capturing app stderr and "no Deny" would pass vacuously
    check("[nav] OpenExternal https://example.com" in log,
          "app stderr is captured ([nav] OpenExternal logged for the external link)")
    denies = [ln for ln in log.splitlines() if "[nav] Deny" in ln]
    check(not denies, f"no [nav] Deny lines (found: {denies})")
    finished = [ln for ln in log.splitlines() if "[download] Finished" in ln and "success=true" in ln]
    check(len(finished) == 2, f"both downloads reached on_download Finished with success ({len(finished)})")


def ask(appimage: str, log_path: str) -> None:
    d = session(appimage)
    try:
        check(open_test_page(d), "ask mode: test page reached")
        d.find_element(By.ID, "dl-blob").click()
        wait_for(lambda: "success=true" in read_log(log_path), 15)
        # the non-blocking Save dialog is now open and unanswered; a deadlocked main thread
        # would make these commands time out
        time.sleep(2)
        check(d.execute_script("return 1") == 1, "app answers WebDriver while the Save dialog is open")
        check(d.current_url == TEST_URL, "webview still on the test page")
    finally:
        try:
            d.quit()
        except WebDriverException:
            pass
    log = read_log(log_path)
    check(any("[download] Finished" in ln and "success=true" in ln for ln in log.splitlines()),
          "ask mode: download finished into the temp file")


def main() -> None:
    if len(sys.argv) != 5 or sys.argv[1] not in ("full", "ask"):
        sys.exit(f"usage: {sys.argv[0]} <full|ask> <appimage> <app-stderr-log> <download-dir>")
    mode, appimage, log_path, dl_dir = sys.argv[1:]
    if mode == "full":
        full(appimage, log_path, pathlib.Path(dl_dir))
    else:
        ask(appimage, log_path)
    if failures:
        sys.exit(f"{len(failures)} GUI check(s) failed")
    print(f"all {mode} GUI checks passed")


if __name__ == "__main__":
    main()
