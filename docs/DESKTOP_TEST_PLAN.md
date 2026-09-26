# Persona Forge — Desktop Manual Test Plan (release gate)

**Status:** placeholder — build is not yet releasable; execute this plan **near release** (Phase 7),
not during the current build-out. This file is the **living home for every manual desktop QA test**;
Phases 4–7 append their packaging/signing/update checks here as they land.

Owner runs this on the Mac (`darwin arm64`). Where a test says "other machine", use a Debian LXC
(`docker-agent`/`hermes-*` neighbor) or a spare browser — one is enough.

---

## How to run this plan

1. **Build close to release.** Keep `main` green; these tests assume the current `desktop/p3-shell`
   desktop app plus the packaged build you're about to push (`cargo tauri build` or the DMG/AppImage
   from the release pipeline). If you're testing the pre-packaged binary instead, use
   `cargo tauri dev` — note which in the results table.
2. **Fresh state per run** so ports/preferences don't leak between cases:
   `PERSONA_FORGE_HOME="$(mktemp -d)"` and **quit the app fully** (Cmd+Q) between cases that
   depend on startup behavior. Some cases intentionally reuse state (port persistence) — they say so.
3. **Free a dedicated test port.** Most cases use the default auto range (8318–8348). The
   fixed-port cases use 9123.
4. **Record results** in the [Results table](#results-table) at the end: pass/fail + a one-line
   evidence note (screenshot path or log line) + a GitHub issue number if you filed a fix.
5. **File failures as fix-PRs** — small fix PRs after the fact are expected and fine. Reference
   this test-plan checklist item (e.g. `T1.2` / `D-GUI-05`) in the issue body so the acceptance
   record stays linkable.

The **stop condition** for the whole gate is any case below failing in a way you don't want to
ship with (esp. anything on the macOS vibrancy or security-adjacent rows).

---

## 0. Environment & prerequisites

- macOS 14.0+ (the artifact's `minimumSystemVersion`), tested on macOS 26.
- Rust toolchain 1.98 (CI-standard), `cargo-tauri` installed (`cargo install tauri-cli --version
  <pinned> --locked`).
- No other Persona Forge server/container on 127.0.0.1 (check `pgrep -fl persona_forge.app:app`;
  stop it if present).
- A real staged payload (the fake CI payload must **not** be present — it is rejected by design):

```bash
# from repo root, with network (uv pip compile needs to reach the index):
uv build                                                    # wheel -> dist/
bash scripts/fetch_uv_binary.sh 0.12.9 aarch64-apple-darwin uv-bin
uv run --frozen python scripts/stage_desktop_payload.py \
  --target aarch64-apple-darwin \
  --version "$(uv run --frozen python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")" \
  --wheel dist/*.whl --uv-binary uv-bin/uv --uv-version 0.12.9 --out-root desktop
```

- Headless end-to-end smoke (run this **first**; if this fails, stop — the GUI can't work):

```bash
mkdir -p /tmp/desktop-gate
(cd desktop && cargo build --release)
PERSONA_FORGE_HOME="$(mktemp -d)" desktop/target/release/persona-forge-desktop \
  --smoke-test /tmp/desktop-gate/smoke.json; echo "exit=$?"
python3 -c "import json;d=json.load(open('/tmp/desktop-gate/smoke.json'));assert d['ok'],d;print(d)"
```

  Expect `ok:true`, `exit=0`, and `/tmp/desktop-gate/smoke.json` with `steps` covering
  `verify` → `venv`/`sync`/`install` → `start` → `wait` → `stop`.

---

## 1. First-run bootstrap & focus behavior

### T1.1 — Fresh first run: splash → SPA

- **Setup:** fresh `PERSONA_FORGE_HOME`, no prior server.
- **Action:** launch the app.
- **Expected:** splash shows the step list `venv → sync → install → start → wait` advancing with
  the active step highlighted and a scrolling log tail; then the main window navigates to
  `http://127.0.0.1:<port>/` and the SPA loads (theme from the previous step's server-side
  preference applies — the default violet on a truly fresh home). Record a screenshot of the
  splash and of the loaded SPA.

### T1.2 — Second launch while running: focus, no second server

- **Setup:** app already running (T1.1 left it up).
- **Action:** launch the app a second time.
- **Expected:** the existing window is shown and focused; **no** second server process
  (`pgrep -fl persona_forge.app:app` shows exactly **one** process group).

### T1.3 — Fresh `PERSONA_FORGE_HOME` still finds the port free / first-run marks itself

- Covered implicitly by T1.1 (a fresh home has no persisted `port`, so the app scans from 8318).

---

## 2. Core text-editing shortcuts

### T2.1 — Cmd+C / Cmd+V / Cmd+Z / Cmd+A in the Speak page textarea

- **Action:** Speak page → type a line → select all (Cmd+A), copy (Cmd+C), paste (Cmd+V), undo
  (Cmd+Z). Repeat in a Voice Library reference-text inline-edit textarea.
- **Expected:** standard macOS editing semantics work in both (this validates the Edit menu has
  the predefined Undo/Redo/Cut/Copy/Paste/Select All items that WKWebView needs).

---

## 3. Downloads

### T3.1 — Default save: file to `~/Downloads` with `(1)` de-duplication, "Saved" notification

- **Setup:** default ("Ask where to save" off).
- **Action:** Speak → generate audio → download it. Download the **same name** a second time.
  Build a `~/Downloads/tone.wav` first and download to confirm the collision path too.
- **Expected:** first download → `~/Downloads/<name>`; a same-named download → `<stem> (1).<ext>`
  (then `(2)`, ...) if the name already exists or is in flight. No dialog. The "Saved" system
  notification appears with **Show in Finder**, which reveals the file.

### T3.2 — Ask mode: responsive during Save dialog; Save moves; Cancel leaves no temp

- **Setup:** Settings → **Ask where to save each file** → on (applies to the next download, no
  restart).
- **Action:** download → the Save dialog opens. While it's open, **scroll the sidebar and click
  around — the app must stay responsive**. Choose a destination → the file lands there. Repeat,
  **Cancel** the second one.
- **Expected:** app fully responsive with the dialog open (no deadlock — Phase 1 proved a blocking
  dialog deadlocks here); Save moves the temp file to your chosen path + "Saved" notification;
  Cancel deletes the temp file — `desktop/downloads-tmp/` is empty afterward
  (`find "$PERSONA_FORGE_HOME/desktop/downloads-tmp" -type f` → nothing).

### T3.3 — Download failure path

- **Setup:** optional. Requires a way to make a download fail mid-write (e.g. fill the destination
  volume). If impractical, skip and note it as not-exercised.
- **Expected:** partial file removed and a "Download failed" notification.

---

## 4. Navigation, external links, update banner

### T4.1 — External links open the system browser

- **Action:** trigger an outbound link — the update banner's "See what's new" **if shown**, plus a
  Help → Documentation / Report an Issue menu item.
- **Expected:** the link opens in your default system browser, **not** inside the app window, and
  the app window does not navigate away. (Known Phase 1 gap tracked under `<a target="_blank">`:
  anchor `target=_blank` may be swallowed on macOS/Windows; `window.open` is confirmed working. If
  an in-app anchor link does nothing, that's the known finding — record `T4.1-NOCLICK` against it.)

### T4.2 — Desktop app does **not** show the web update banner

- **Setup:** run with a build whose version is behind the current GitHub release (any tagged
  release newer than the app's build).
- **Action:** wait ~10s after the SPA loads (banner has a 5s startup delay then a 24h recheck).
- **Expected:** **no** `UpdateAvailableBanner` in-app — `/health` reports `shell: "desktop"` and the
  banner returns `null` (D13). Confirm the inverse path too: open the **same server in a browser**
  (Safari at `http://127.0.0.1:<port>/`) — there the banner **does** show.

---

## 5. Window lifecycle, tray, quit

### T5.1 — Close keeps app running (Dock + tray); Dock/tray reopens; Cmd+Q quits

- **Setup:** app running, server up.
- **Action:**
  1. Close the window (red light). 2. Click the Dock icon. 3. Close again, then click
     File → (tray) Open, or the tray icon. 4. Cmd+Q.
- **Tray:** macOS menu-bar icon; Windows/Linux hide-to-tray (with a one-time "still running in the
  system tray" notification when the tray is enabled).
- **Expected:** closing hides, app stays in the Dock/tray; Dock click / tray Open re-shows the
  window at the same port; Cmd+Q **within 10s** leaves **no** `persona_forge` process
  (`pgrep -fl persona_forge` empty).

### T5.2 — SIGTERM orphan recovery

- **Setup:** app running on a fresh home; note the server process pid
  (`pgrep -fl persona_forge.app:app`).
- **Action:** `kill -9 <shell pid>` (the **desktop app** process, not the server), then immediately
  relaunch.
- **Expected:** the orphaned server **group** is killed (check the bootstrap log line that confirms
  kill_orphan ran) and the app starts normally **on the same port** — no port bump, no
  `ExternalPersonaForge` prompt.

### T5.3 — Window size & position persist

- **Action:** resize / move the window, quit, relaunch.
- **Expected:** size, position and maximized state restore (window-state plugin; hidden windows never
  restore as invisible).

### T5.4 — Tray toggle persists; off removes the icon

- **Setup:** Settings → **Keep running in the menu bar / system tray** available (Phase 3 ships the
  setting; tray-off behavior).
- **Action:** toggle off, relaunch.
- **Expected:** no tray/menu-bar icon on relaunch (tray creation failure also degrades to
  tray-disabled **for that session** rather than failing the app).

---

## 6. Port selection & conflicts

### T6.1 — Auto: occupied 8318 → app moves to 8319 and persists it

- **Setup:** fresh `PERSONA_FORGE_HOME`.
- **Action:** occupy 8318 with `python3 -m http.server 8318` → launch.
- **Expected:** the app picks **8319** and persists it. Quit, keep 8318 free, relaunch → stays on
  8319 (persisted). Then occupy **8319** (the persisted port) with `python3 -m http.server 8319`,
  relaunch → the app moves to the next free port **and shows the one-time "port moved"
  notification** ("Tools pointed at the old port need updating").

### T6.2 — Fixed: never moves; conflict shows Open Settings / Retry / Quit

- **Setup:** Settings → **Fixed** port **9123** → Apply → confirm the splash restarts and the SPA
  reloads at `127.0.0.1:9123` (theme from earlier is unchanged — server-side preferences, D17).
- **Action:** quit, occupy **9123** with `python3 -m http.server 9123`, relaunch.
- **Expected:** the "Port 9123 is in use by another program" error with **Open Settings / Retry /
  Quit** — and the app does **not** move to another port.
- **Also confirm:** auto + persisted port already answering as Persona Forge (a CLI/container
  server on 8318) → the "already running outside the app" prompt, and the app does **not** attach
  to it.

### T6.3 — No free port → clear error

- **Setup (optional, resource-hungry):** occupy the whole 8318–8348 range.
- **Expected:** "No free port found" error with Open Settings.

---

## 7. Network access (LAN)

### T7.1 — Allow other devices on my network

- **Setup:** Settings → **Allow other devices on my network** → Apply. Expect a **macOS firewall
  prompt** — allow it, and record what it says.
- **Action:** note the address list in Settings (127.0.0.1 plus every LAN IPv4, each with an
  OpenAI-compatible `/v1` base URL). From another machine (e.g. a Debian LXC):
  `curl http://<your-mac-ip>:9123/health` → 200. Then from the Mac browser open that URL.
- **Expected:** the LAN address serves `/health` (this is the desktop-hosted server, so the SPA on
  a remote machine **also** reports `shell: "desktop"` and shows the update banner — that's
  correct, D18/D13). Record the firewall-prompt text.

### T7.2 — Copy Server Address

- **Action:** menu + tray **Copy Server Address**.
- **Expected:** with network access **off** → clipboard has `http://127.0.0.1:<port>`; with it
  **on** → `http://<first-LAN-IPv4>:<port>`.

---

## 8. Icons & appearance

### T8.1 — Dock / About / menu-bar icons

- **Action:** screenshot the Dock icon, the About panel icon, and the menu-bar (tray) icon in
  **both** a light and a dark menu bar.
- **Expected:** the Signal Crucible mark renders correctly at every size; the tray icon follows the
  menu-bar color in both appearances (macOS template image).

### T8.2 — macOS vibrancy (D20) — light **and** dark mode

- **Action:** screenshot both modes: the sidebar and the title strip show the **translucent native
  material** (your desktop picture shows through, blurred); the content column is **opaque**; the
  traffic lights sit on the material.
- **Expected:** dragging the title strip moves the window; double-clicking it zooms. There are no
  HTML drag regions.
- **Deactivate** the window (click another app): the material **dims** (`followsWindowActiveState`).
- **Resize / enter+leave full screen:** no flicker or blank frames.

### T8.3 — System Reduce Transparency

- **Setup:** System Settings → Accessibility → Display → **Reduce transparency** → on.
- **Expected:** the sidebar turns **opaque without any app change** (AppKit does this; record what
  actually happens — contract D20 expects no app code path toggling it).

### T8.4 — macOS accent color

- **Action:** change the macOS accent color, relaunch.
- **Expected:** any native checkboxes/radios/sliders on the page use the **system** accent; the
  app's brand theme (`data-theme`) is unchanged.

---

## 9. Payload failure & error screen

### T9.1 — Broken payload → error screen with Retry / Show Logs / Quit

- **Setup:** break the *staged* payload's `desktop/payload/manifest.json` wheel `sha256`
  (change one hex digit), keep a **real** shadow copy to restore afterward.
- **Action:** relaunch.
- **Expected:** the error screen with the cause, the last ~30 log lines, and **Retry / Show Logs /
  Quit**. Retry re-runs verify (and fails again while the manifest is broken); **Show Logs**
  reveals the logs dir; restore the good manifest + Retry → the splash proceeds normally.
- **Note:** the **fake** CI payload (all-zero sha256) is rejected with a distinct "fake payload"
  error — that is by design, not the same case.

---

## 10. Regression cross-check (non-desktop must be unchanged)

### T10.1 — Same server in a plain browser (Safari)

- **Action:** open `http://127.0.0.1:<port>/` in Safari.
- **Expected:** looks **exactly** as before this phase: **no `data-desktop`** on `<html>`, opaque
  background, and the update banner **is** shown (if behind release). Text editing now uses the
  system shortcut set appropriate to the browser (Cmd), not the app's WKWebView default.

---

## Release-wiring checks (Phase 7 addition)

These are appended here so the release gate is one place — the Phase 4/5/6/7 stamp/build/sign/
update manual checks will slot into this section as those phases land. Expected additions:

- [ ] Phase 4: unsigned artifacts build on all three OSes; native smoke passes (headless, per job)
- [ ] Phase 5: `.app` + DMG notarized/stapled; `codesign --verify --deep --strict` and `spctl`
      clean; offline install launches (no Gatekeeper failure)
- [ ] Phase 6A/6B: in-app "Check for Updates…" offers/installs/relaunches; good + badsig feeds;
      Windows silent install; Sparkle appcast path
- [ ] Phase 7: release artifacts match the contract (`validate_release_contract.py`), checksums
      coverage, feed generation, rollback procedure tested

---

## Results table

Copy this block into the PR (or a gist) and fill it in near release. `pass` / `FAIL(#<issue>)` /
`n/e` (not exercised — note why).

| # | Test | Result | Evidence (screenshot/log) |
| --- | ------ | -------- | --------------------------- |
| T0.0 | real-payload `--smoke-test` | | |
| T1.1 | first-run splash → SPA | | |
| T1.2 | second launch focuses; one server | | |
| T2.1 | Cmd+C/V/Z/A in Speak + library textareas | | |
| T3.1 | default save → `~/Downloads`, `(1)` dedup, Saved notif | | |
| T3.2 | ask mode: responsive dialog; Save moves; Cancel clears tmp | | |
| T3.3 | download failure → partial removed + "Download failed" | | |
| T4.1 | external links → system browser | | |
| T4.2 | no web update banner in-app; banner shows in browser | | |
| T5.1 | close-to-tray/Dock; reopen; Cmd+Q quits in 10s | | |
| T5.2 | SIGTERM orphan recovery; same port after relaunch | | |
| T5.3 | window size/position persist | | |
| T5.4 | tray toggle persists; off = no icon | | |
| T6.1 | auto 8318 busy → 8319 persisted; 8319 busy → "port moved" | | |
| T6.2 | fixed 9123 never moves; conflict dialog; external-PF prompt | | |
| T6.3 | no free port → clear error | | |
| T7.1 | LAN reachable; firewall prompt recorded | | |
| T7.2 | Copy Server Address (off = 127.0.0.1, on = LAN) | | |
| T8.1 | Dock/About/tray icons light + dark | | |
| T8.2 | vibrancy light + dark; dims on deactivate; no flicker | | |
| T8.3 | Reduce Transparency → opaque sidebar (record actual) | | |
| T8.4 | system accent on native controls; brand theme unchanged | | |
| T9.1 | broken payload → error screen; Retry/Show Logs/Quit | | |
| T10.1 | Safari: no data-desktop, opaque, banner shown | | |
| Phase 4 | unsigned artifacts + smoke (slot) | | |
| Phase 5 | notarized `.app`/DMG, offline install | | |
| Phase 6A/6B | update offer/install/relaunch; feeds; sigs | | |
| Phase 7 | release contract + rollback | | |

---

## Bug-reporting convention

- File against the release; open **fix-PRs** after the fact (the user has confirmed this is the
  intended loop — nothing sits waiting on the first release being flawless).
- Reference the test id (`T6.2`, `D-GUI-…`) and paste the evidence line from the results table.
- Update this file's results table / "known findings" as fixes land so the next release's gate is
  current.
