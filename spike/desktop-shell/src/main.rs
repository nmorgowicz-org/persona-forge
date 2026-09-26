#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
// Phase 1 spike (persona-forge desktop execution plan): proves the four risky
// integrations before the real `desktop/` crate exists. NOTHING from this crate
// merges except the results write-up.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};

use tauri::{
    menu::{MenuBuilder, SubmenuBuilder},
    webview::DownloadEvent,
    WebviewUrl, WebviewWindowBuilder,
};

#[cfg(not(target_os = "macos"))]
const DEFAULT_FEED_BASE: &str =
    "https://github.com/nmorgowicz-org/persona-forge/releases/download/desktop-spike";
const TEST_ORIGIN_PORT: u16 = 8318;

#[cfg(not(target_os = "macos"))]
fn feed_base() -> &'static str {
    option_env!("SPIKE_FEED_BASE").unwrap_or(DEFAULT_FEED_BASE)
}

// ── contract §6.5 classify (a copy of the pure function) ─────────────────────
#[derive(Debug, PartialEq, Eq, Clone, Copy)]
enum Decision {
    Allow,
    OpenExternal,
    Deny,
}

/// `http://127.0.0.1:<TEST_ORIGIN_PORT>` — the only non-splash origin allowed in-app.
fn is_test_origin(url: &tauri::Url) -> bool {
    url.scheme() == "http"
        && url.host_str() == Some("127.0.0.1")
        && url.port() == Some(TEST_ORIGIN_PORT)
}

fn classify(url: &tauri::Url) -> Decision {
    match url.scheme() {
        "mailto" => Decision::OpenExternal,
        "about" => {
            if url.as_str() == "about:blank" {
                Decision::Allow
            } else {
                Decision::Deny
            }
        }
        // splash origins: tauri://localhost (macOS/Linux), http://tauri.localhost (Windows)
        "tauri" => Decision::Allow,
        "http" | "https" => {
            let windows_splash =
                url.scheme() == "http" && url.host_str() == Some("tauri.localhost");
            if windows_splash || is_test_origin(url) {
                Decision::Allow
            } else {
                Decision::OpenExternal
            }
        }
        // blob: URLs carry their origin inside the path ("blob:http://127.0.0.1:8318/<uuid>"),
        // so url.host_str() is None; judge the inner origin (contract §6.5).
        "blob" => match tauri::Url::parse(url.path()) {
            Ok(inner) if is_test_origin(&inner) => Decision::Allow,
            _ => Decision::Deny,
        },
        _ => Decision::Deny,
    }
}

// ── downloads (contract §6.5 prototype) ──────────────────────────────────────
/// Spike stand-in for the Settings toggle "Ask where to save each file" (default off).
fn ask_where_to_save() -> bool {
    std::env::var_os("SPIKE_ASK_WHERE_TO_SAVE").is_some()
}

/// The user's Downloads folder; `SPIKE_DOWNLOAD_DIR` overrides it for CI.
fn downloads_dir<R: tauri::Runtime>(app: &tauri::AppHandle<R>) -> PathBuf {
    if let Some(dir) = std::env::var_os("SPIKE_DOWNLOAD_DIR") {
        return PathBuf::from(dir);
    }
    use tauri::Manager;
    app.path().download_dir().unwrap_or_else(|_| std::env::temp_dir())
}

type Pending = HashMap<String, (PathBuf, String)>;

/// In-flight downloads: URL -> (assigned destination, suggested file name).
fn pending_downloads() -> &'static Mutex<Pending> {
    static PENDING: OnceLock<Mutex<Pending>> = OnceLock::new();
    PENDING.get_or_init(Default::default)
}

/// `name`, else `stem (1).ext`, `stem (2).ext`, ...: skipping files that exist and
/// destinations already reserved by in-flight downloads.
fn unique_path(dir: &Path, name: &str, pending: &Pending) -> PathBuf {
    let taken = |p: &Path| p.exists() || pending.values().any(|(d, _)| d == p);
    let first = dir.join(name);
    if !taken(&first) {
        return first;
    }
    let as_path = Path::new(name);
    let stem = as_path.file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or_default();
    let ext = as_path
        .extension()
        .map(|e| format!(".{}", e.to_string_lossy()))
        .unwrap_or_default();
    (1..)
        .map(|n| dir.join(format!("{stem} ({n}){ext}")))
        .find(|p| !taken(p))
        .expect("an unused name exists")
}

/// rename, falling back to copy + remove across filesystems (temp dir -> another volume).
fn move_file(from: &Path, to: &Path) -> std::io::Result<()> {
    std::fs::rename(from, to).or_else(|_| {
        std::fs::copy(from, to)?;
        std::fs::remove_file(from)
    })
}

// ── strict argument parsing (contract §6.8 shape) ────────────────────────────
enum Args {
    Version,
    #[cfg(not(target_os = "macos"))]
    CiUpdate(PathBuf),
    Gui,
}

#[cfg_attr(target_os = "macos", allow(unused_variables))]
fn parse_args() -> Args {
    let args: Vec<String> = std::env::args().skip(1).collect();
    for (idx, arg) in args.iter().enumerate() {
        match arg.as_str() {
            "--version" => return Args::Version,
            #[cfg(not(target_os = "macos"))]
            "--ci-update" => {
                match args.get(idx + 1) {
                    Some(out) => return Args::CiUpdate(PathBuf::from(out)),
                    None => fail_unknown("--ci-update (missing <out.json>)"),
                }
            }
            other => {
                if other.starts_with("--") {
                    fail_unknown(other);
                }
                // non-flag OS-supplied arguments (e.g. macOS -psn_...) are ignored
            }
        }
    }
    Args::Gui
}

fn fail_unknown(flag: &str) -> ! {
    eprintln!("unknown argument: {flag}");
    std::process::exit(2);
}

// ── --ci-update: headless updater driver (prototype of contract §6.12) ───────
#[cfg(not(target_os = "macos"))]
fn run_ci_update(app: tauri::AppHandle, out_path: PathBuf) -> Result<(), String> {
    use std::io::Write;
    use tauri_plugin_updater::UpdaterExt;

    let mut json = serde_json::json!({
        "ok": false,
        "phase": "unknown",
        "from_version": app.package_info().version.to_string(),
        "to_version": serde_json::Value::Null,
        "error": serde_json::Value::Null,
        // diagnostics: on Linux the updater replaces $APPIMAGE if set, else current_exe()
        "appimage_env": std::env::var("APPIMAGE").ok(),
        "current_exe": std::env::current_exe().ok().map(|p| p.display().to_string()),
    });

    let result: Result<(), String> = tauri::async_runtime::block_on(async {
        let endpoint = format!("{}/latest.json", feed_base());
        let updater = app
            .updater_builder()
            .endpoints(vec![endpoint.parse().expect("valid endpoint")])
            .map_err(|e| e.to_string())?
            .build()
            .map_err(|e| e.to_string())?;
        let update = match updater.check().await {
            Ok(Some(update)) => {
                json["to_version"] = serde_json::Value::String(update.version.clone());
                update
            }
            Ok(None) => {
                json["phase"] = serde_json::Value::String("noupdate".into());
                return Err("no update available".into());
            }
            Err(e) => {
                json["phase"] = serde_json::Value::String("check".into());
                return Err(e.to_string());
            }
        };
        // download() fetches the bytes AND verifies the minisign signature
        // (plugin updater.rs verify_signature); contract §6.12 reports a
        // signature failure as phase "verify", anything else as "download"
        json["phase"] = serde_json::Value::String("download".into());
        let bytes = match update.download(&mut |_len, _total| {}, &mut || {}).await {
            Ok(bytes) => bytes,
            Err(e) => {
                use tauri_plugin_updater::Error as E;
                if matches!(e, E::Minisign(_) | E::Base64(_) | E::SignatureUtf8(_)) {
                    json["phase"] = serde_json::Value::String("verify".into());
                }
                return Err(e.to_string());
            }
        };
        json["phase"] = serde_json::Value::String("installing".into());
        update.install(bytes.as_slice()).map_err(|e| e.to_string())?;
        Ok::<(), String>(())
    });

    if let Err(e) = result {
        json["error"] = serde_json::Value::String(e);
    } else {
        json["phase"] = serde_json::Value::String("installed".into());
        json["ok"] = serde_json::Value::Bool(true);
    }

    let mut f = std::fs::File::create(&out_path).map_err(|e| e.to_string())?;
    f.write_all(json.to_string().as_bytes()).map_err(|e| e.to_string())?;
    let _ = app.cleanup_before_exit();
    if json["ok"] == serde_json::Value::Bool(true) {
        std::process::exit(0);
    }
    std::process::exit(1);
}

// menu-triggered check + install (Win/Linux); endpoints per call site
#[cfg(not(target_os = "macos"))]
async fn check_and_install(app: &tauri::AppHandle) {
    use tauri_plugin_updater::UpdaterExt;
    let endpoint = format!("{}/latest.json", feed_base());
    let run = async {
        let updater = app
            .updater_builder()
            .endpoints(vec![endpoint.parse().expect("valid endpoint")])
            .map_err(|e| e.to_string())?
            .build()
            .map_err(|e| e.to_string())?;
        match updater.check().await.map_err(|e| e.to_string())? {
            Some(update) => {
                eprintln!("[update] offering {}", update.version);
                let bytes = update
                    .download(&mut |_len, _total| {}, &mut || {})
                    .await
                    .map_err(|e| e.to_string())?;
                update.install(bytes.as_slice()).map_err(|e| e.to_string())?;
                Ok::<(), String>(())
            }
            None => {
                eprintln!("[update] no update available");
                Ok::<(), String>(())
            }
        }
    };
    if let Err(e) = run.await {
        eprintln!("[update] failed: {e}");
    }
}

fn main() {
    // The version comes from the Tauri context: `cargo tauri build --config {"version":..}`
    // sets it, while CARGO_PKG_VERSION (Cargo.toml) stays 0.1.0 for every build.
    let context = tauri::generate_context!();

    // 1. strict argument parsing before anything else
    match parse_args() {
        Args::Version => {
            println!("desktop-spike {}", context.package_info().version);
            return;
        }
        // macOS: "--ci-update" is intentionally unknown here -> exit 2
        #[cfg(not(target_os = "macos"))]
        Args::CiUpdate(out_path) => {
            // updater plugins need an app context; build one with no windows
            let app = build_app(context).expect("failed to build spike app");
            let _ = run_ci_update(app.handle().clone(), out_path); // exits the process internally
            return;
        }
        Args::Gui => {}
    }

    // 2. GUI run
    let app = build_app(context).expect("failed to build spike app");
    app.run(|_app, event| {
        if let tauri::RunEvent::ExitRequested { .. } = event {
            // spike: nothing to stop
        }
    });
}

fn build_app(context: tauri::Context) -> tauri::Result<tauri::App> {
    // All plugins go on the Builder: they are initialized in build(), before run().
    // Plugins added inside .setup() only exist once run() starts the event loop, which
    // the --ci-update path never calls (it drives the updater right after build()).
    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init());
    #[cfg(not(target_os = "macos"))]
    let builder = builder.plugin(tauri_plugin_updater::Builder::new().build());
    #[cfg(target_os = "macos")]
    let builder = builder.plugin(tauri_plugin_sparkle_updater::init());
    builder
        .setup(|app| {
            // Edit menu first: WKWebView needs predefined edit items for clipboard shortcuts.
            let edit = SubmenuBuilder::new(app, "Edit")
                .undo()
                .redo()
                .cut()
                .copy()
                .paste()
                .select_all()
                .build()?;
            let check = tauri::menu::MenuItemBuilder::with_id("check_updates", "Check for Updates")
                .build(app)?;
            let help = SubmenuBuilder::new(app, "Help").item(&check).build()?;
            let menu = MenuBuilder::new(app).items(&[&edit, &help]).build()?;

            let mut builder = WebviewWindowBuilder::new(
                app,
                "main",
                WebviewUrl::App("index.html".into()),
            )
            .title("desktop-spike")
            .inner_size(1100.0, 760.0)
            .menu(menu);

            builder = builder.on_navigation(|url| match classify(url) {
                Decision::Allow => true,
                Decision::OpenExternal => {
                    eprintln!("[nav] OpenExternal {url}");
                    let _ = tauri_plugin_opener::open_url(url.as_str(), None::<&str>);
                    false
                }
                Decision::Deny => {
                    eprintln!("[nav] Deny {url}");
                    false
                }
            });

            builder = builder.on_download(|webview, event| match event {
                // Never block in this callback: it runs on the main thread, and a blocking
                // dialog waits on the main thread itself (Phase 1 finding: deadlock on every OS).
                DownloadEvent::Requested { url, destination } => {
                    let name = destination
                        .file_name()
                        .map(|s| s.to_string_lossy().to_string())
                        .unwrap_or_else(|| "download".into());
                    let dir = if ask_where_to_save() {
                        std::env::temp_dir().join("desktop-spike-downloads")
                    } else {
                        downloads_dir(tauri::Manager::app_handle(&webview))
                    };
                    if let Err(e) = std::fs::create_dir_all(&dir) {
                        eprintln!("[download] cannot create {dir:?}: {e}");
                        return false;
                    }
                    let mut pending = pending_downloads().lock().unwrap();
                    let target = unique_path(&dir, &name, &pending);
                    eprintln!("[download] Requested {url} -> {target:?}");
                    pending.insert(url.to_string(), (target.clone(), name));
                    *destination = target;
                    true
                }
                DownloadEvent::Finished { url, path, success } => {
                    eprintln!("[download] Finished {url} -> {path:?} success={success}");
                    // `path` may be None even on success; use the destination we assigned
                    let entry = pending_downloads().lock().unwrap().remove(url.as_str());
                    if let (true, true, Some((tmp, name))) = (success, ask_where_to_save(), entry) {
                        // non-blocking Save dialog; its callback moves the finished temp file
                        tauri_plugin_dialog::DialogExt::dialog(&webview)
                            .file()
                            .set_file_name(&name)
                            .save_file(move |choice| {
                                let chosen = match choice {
                                    Some(tauri_plugin_dialog::FilePath::Path(p)) => Some(p),
                                    Some(tauri_plugin_dialog::FilePath::Url(u)) => {
                                        Some(PathBuf::from(u.path()))
                                    }
                                    None => None,
                                };
                                match chosen {
                                    Some(dest) => match move_file(&tmp, &dest) {
                                        Ok(()) => eprintln!("[download] Saved {dest:?}"),
                                        Err(e) => eprintln!("[download] move to {dest:?} failed: {e}"),
                                    },
                                    None => {
                                        let _ = std::fs::remove_file(&tmp);
                                        eprintln!("[download] Save cancelled; removed {tmp:?}");
                                    }
                                }
                            });
                    }
                    true
                }
                _ => true,
            });

            builder.build()?;
            Ok(())
        })
        .on_menu_event(|app, event| {
            if event.id().0 == "check_updates" {
                #[cfg(not(target_os = "macos"))]
                {
                    let app = app.clone();
                    tauri::async_runtime::spawn(async move { check_and_install(&app).await });
                }
                #[cfg(target_os = "macos")]
                {
                    eprintln!("[update] macOS updates are handled by Sparkle's UI");
                    let _ = app;
                }
            }
        })
        .build(context)
}
