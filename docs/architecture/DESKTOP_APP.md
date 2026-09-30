# Persona Forge Desktop

Persona Forge Desktop is the recommended install for using the studio as a local app. It is a
Tauri v2 shell around the existing Python server and React web UI; it does not replace either.
The shell provisions and supervises the server, and displays the UI in a native window.

## Availability and platform status

Download desktop assets from the [GitHub Releases](https://github.com/nmorgowicz-org/persona-forge/releases)
page:

| Platform | Asset | Status / requirements |
| --- | --- | --- |
| macOS Apple Silicon | `PersonaForge-macos-aarch64.dmg` | Signed, notarized, and stapled; macOS 14 or later |
| Windows x86-64 | `PersonaForge-windows-x86_64-setup.exe` | Per-user NSIS installer; unsigned preview; Windows 11 |
| Linux x86-64 | `PersonaForge-linux-x86_64.AppImage` | **Preview**, glibc 2.35 or later (Ubuntu 22.04+); AppIndicator support is needed for the GNOME tray icon |

On macOS, open the DMG and drag Persona Forge to Applications. On Windows, run the per-user
installer; it does not require administrator privileges. On Linux, mark the downloaded AppImage
executable and launch it. All platforms detect your GPU automatically and provision the matching
PyTorch accelerator (CUDA 12/13 on NVIDIA, Intel XPU on Arc iGPUs, ROCm on AMD — Linux only),
falling back to CPU inference with a notice when anything fails. See [GPU acceleration](#gpu-acceleration).

The Linux desktop build is a preview because it is validated through automated CI rather than a
maintainer's Linux desktop. The AppImage is the only Linux desktop package. Intel macOS, Windows
ARM64, and Linux ARM64 are not provided.

### Windows unsigned installer warning

The installer is not code-signed. Windows SmartScreen may show **"Windows protected your PC"**;
click **More info → Run anyway**. This allows only this installer; do not turn SmartScreen off.
The prompt can appear again after an update.

If **Smart App Control (SAC)** is enabled, Windows blocks unsigned apps without a **Run anyway**
option. Installing requires turning SAC off in **Windows Security → App & browser control → Smart
App Control settings → Off**. On some Windows versions, it cannot be turned back on without
resetting Windows, so consider that consequence before disabling it.

## First launch and everyday use

The app starts with a native splash while it verifies its bundled payload and provisions the
versioned Python environment. First use downloads Python and package dependencies; the first
server start may also download model assets. The splash reports progress, and on failure offers
Retry, Show Logs, and Quit. Subsequent launches reuse the provisioned environment and cached data.

When the server is ready, the main window opens the local UI at `http://127.0.0.1:<port>/`. The
app owns the server process and stops it when the app quits. It enforces one app instance; a
second launch focuses the existing window instead of starting another server. On macOS, closing
the window hides the app (use Cmd+Q to quit). On Windows and Linux, closing hides it to the tray
when tray support is enabled; otherwise it quits. The menu and tray include **Open in Browser**,
**Copy Server Address**, **Show Logs**, **Settings**, and update controls where supported. Audio
downloads are saved in the Downloads folder by default; Settings can instead ask for a location
for each download.

## Settings, server address, and data

Open **Settings** from the app menu (Cmd+, on macOS; Ctrl+, on Windows/Linux) or the tray. The
settings include:

- **Port:** Automatic (default) chooses 8318, or the first available port from 8319 through 8348,
  and remembers it. Fixed mode uses the selected port (1024–65535).
- **Allow other devices on my network:** off by default. When enabled, the server binds to all
  interfaces (`0.0.0.0`) and Settings lists the machine's LAN addresses. The server has no
  authentication; anyone on the reachable network can use it and access its voices. Enable this
  only on a network you trust.
- **Keep running in the menu bar / system tray** and **Ask where to save each file**.
- **Acceleration:** Automatic (default), CPU only, NVIDIA, Intel, or AMD. Automatic detects
  the best available accelerator and provisions the matching PyTorch wheel; explicit choices
  force a specific path and fall back to CPU when the hardware does not match. See
  [GPU acceleration](#gpu-acceleration) for details.

The app window uses the loopback URL `http://127.0.0.1:<port>/` even when network access is
enabled. Settings shows the loopback address and, when applicable, each LAN address. It also
shows the OpenAI-compatible base URL, `http://<host>:<port>/v1`, for clients and other tools.

Desktop settings and logs live under `<app data root>/desktop/`. The root is
`~/.config/persona-forge` on macOS, `%LOCALAPPDATA%\persona-forge` on Windows, and
`$XDG_DATA_HOME/persona-forge` on Linux (default `~/.local/share/persona-forge`). In particular:

- `settings.json` stores the desktop port and other app settings.
- `logs/desktop.log` records shell activity, `logs/server.log` the server output, and
  `logs/bootstrap.log` environment setup output. Use the app's **Show Logs** menu command to open
  the log folder.
- `server.pid` supports Unix recovery after a crash; `webview/` contains the Windows WebView2 data.

Python-side data (voices, models, projects, and UI preferences) remains in the existing Persona
Forge data locations. The desktop app and CLI share that data; UI preferences are stored with the
server, so they survive port changes and are shared with browsers connected to the same server.

## Ports and running alongside the CLI

The default port is 8318. Automatic mode searches 8318–8348 and persists its choice. If another
application occupies an automatically selected port, the app can choose the next available port
and notify you. If a fixed port is busy, the app keeps that choice and offers Settings, Retry, or
Quit. If the busy port responds as a Persona Forge server, the desktop app refuses to attach to it
or start a second server; stop the existing CLI/container server or choose another port.

The desktop app and `persona-forge serve` cannot run at the same time on the same port. To change
the desktop port, open **Settings**, select Automatic or Fixed, and Apply; changing the port
restarts the managed server. To reset the saved port to automatic selection, close the app and
delete only the `port` key from `<app data root>/desktop/settings.json`, then relaunch. If the
file has no port value, the app selects an available port on startup.

## GPU acceleration

The desktop app detects your GPU family automatically on first launch (and after each update)
and provisions the matching PyTorch accelerator wheel into a versioned environment:

| Platform | Accelerator | Requirements |
|---|---|---|
| macOS Apple Silicon | MPS (Metal Performance Shaders) | macOS 14 or later; no extra steps — the default PyTorch wheel includes MPS |
| Windows x86-64 | NVIDIA CUDA 13 or 12 | NVIDIA GPU with compute capability ≥ 7.5; CUDA 13 chosen when the driver supports it, otherwise CUDA 12 |
| Linux x86-64 | NVIDIA CUDA 13 or 12, Intel XPU (Arc), AMD ROCm | Same CUDA rules as Windows; Intel XPU uses the Arc iGPU; ROCm requires AMD GPU |

NVIDIA driver detection accepts both the older `CUDA Version` header and the newer
`CUDA UMD Version` header from `nvidia-smi`. Bundled accelerator requirements include
package-specific wheel sources, so provisioning does not depend on a repository checkout
or a manually configured PyTorch index.

If the detected GPU family is not supported (for example, an AMD GPU on Windows), or if the
accelerator installation or verification fails, the app falls back to CPU inference and shows a
notice with details in Settings. The fallback is never silent.

**Settings → Acceleration** lets you override the automatic choice:

- **Automatic** (default): detects the best available accelerator.
- **CPU only**: forces CPU inference regardless of hardware.
- **NVIDIA**: forces the CUDA path (will fall back to CPU on non-NVIDIA hardware).
- **Intel**: forces the Intel XPU path (will fall back to CPU on non-Intel hardware).
- **AMD**: forces the ROCm path (Linux only; unavailable on macOS and Windows).

The detected device name and any `acceleration_status` error are shown in Settings. A **Retry**
button appears after a failed provision attempt. Applying a change re-provisions the environment
and restarts the managed server.

## Updates

The app checks for updates after startup and every 24 hours while it is running. It does not
install automatically: review the release notes and choose **Install and Relaunch** or **Later**.
Update packages are cryptographically verified before installation. macOS uses Sparkle and also
checks the Developer ID; Windows and Linux use the Tauri updater. The server is stopped before an
update is installed, and the new app provisions its matching Python environment after relaunch.

Automated update and signature checks are exercised in CI. Real GUI update verification has not
been performed before a release is available; verifying update checks in the actual macOS and
Windows GUIs is deferred until the first actual desktop release.

## Troubleshooting

### Blank window on NVIDIA / Wayland (Linux)

Try launching the AppImage with WebKit's DMA-BUF renderer disabled:

```bash
WEBKIT_DISABLE_DMABUF_RENDERER=1 ./PersonaForge-linux-x86_64.AppImage
```

### No tray icon on GNOME

Install and enable a GNOME Shell **AppIndicator** extension. If the tray cannot be created, the
app logs a warning and continues without tray behavior for that session; keep the main window open
if you need to keep it visible.

### SmartScreen or Smart App Control blocks the Windows installer

For SmartScreen, choose **More info → Run anyway**; SmartScreen does not need to be disabled. If
SAC is on, there is no bypass button for an unsigned app: review the warning above before deciding
whether to turn SAC off. The installer is unsigned by design, and Windows may show the warning
again after an update.

### Find logs or diagnose startup failure

Use **Show Logs** in the app menu or tray to open the log directory. Review `desktop.log` for
shell and port decisions, `bootstrap.log` for Python/environment provisioning, and `server.log`
for server startup and runtime output. The splash also shows recent log lines and has **Retry**,
**Show Logs**, and **Quit** actions when startup fails.

### NVIDIA detected but generation still runs on CPU

Hardware detection and accelerator installation are separate steps. Check **Settings →
Acceleration** for an installation failure; detecting NVIDIA does not prove the running
Python environment has CUDA-enabled Torch. Older builds can misread the `CUDA UMD Version`
driver header or fail to find accelerator wheels because their bundled requirements omit
the wheel sources. Install an updated build with these fixes, then use **Retry** if a failure
remains. Once background provisioning succeeds, relaunch the app to use its GPU environment.


### Change or reset the port

Use **Settings → Port** to choose Automatic or Fixed and Apply. If you need to reset port
selection completely, quit the app and remove the `port` entry from
`<app data root>/desktop/settings.json`; do not delete other settings. Relaunch to have Automatic
select a free port again.

### Firewall prompt names Python when enabling network access

When **Allow other devices on my network** is enabled, the server listens on `0.0.0.0`. The
firewall prompt may name the bundled Python executable rather than Persona Forge. Allow that
Python process if you want other devices to reach the server:

- **Windows:** Windows Defender Firewall → **Allow an app through Windows Defender Firewall**;
  allow the Python executable on the appropriate network profile.
- **macOS:** System Settings → **Network → Firewall → Options**; allow the Python process.

Network access is unauthenticated. Do not allow it on an untrusted network or expose it to the
public internet.

### Desktop app says Persona Forge is already running

The selected port is already serving Persona Forge, commonly from a CLI or container process.
The desktop app deliberately refuses to attach to that server or start a second one. Stop the
other Persona Forge process, or change the desktop app's port in Settings.
