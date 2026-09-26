#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
// Phase 1 spike (persona-forge desktop execution plan): proves the four risky
// integrations before the real `desktop/` crate exists. NOTHING from this crate
// merges except the results write-up.

use std::path::PathBuf;

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
        "http" | "https" | "blob" => {
            let host = url.host_str().unwrap_or("");
            if host.split('#').next() == Some("tauri.localhost")
                && url.scheme() == "http" {
                    return Decision::Allow;
                }
            if host == "127.0.0.1" && url.port() == Some(TEST_ORIGIN_PORT) {
                Decision::Allow
            } else if url.scheme() == "http" || url.scheme() == "https" {
                Decision::OpenExternal
            } else {
                // blob: to any other origin
                Decision::Deny
            }
        }
        _ => Decision::Deny,
    }
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
                json["phase"] = serde_json::Value::String("verify".into());
                return Err(e.to_string());
            }
        };
        // download returns the verified bytes (progress closures only)
        let bytes = update
            .download(&mut |_len, _total| {}, &mut || {})
            .await
            .map_err(|e| e.to_string())?;
        json["phase"] = serde_json::Value::String("installing".into());
        update.install(bytes.as_slice()).map_err(|e| e.to_string())?;
        Ok(())
    });

    if let Err(e) = result {
        json["error"] = serde_json::Value::String(e);
    } else {
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
                Ok(())
            }
            None => {
                eprintln!("[update] no update available");
                Ok(())
            }
        }
    };
    if let Err(e) = run.await {
        eprintln!("[update] failed: {e}");
    }
}

fn main() {
    // 1. strict argument parsing before anything else
    match parse_args() {
        Args::Version => {
            println!("desktop-spike {}", env!("CARGO_PKG_VERSION"));
            return;
        }
        // macOS: "--ci-update" is intentionally unknown here -> exit 2
        #[cfg(not(target_os = "macos"))]
        Args::CiUpdate(out_path) => {
            // updater plugins need an app context; build one with no windows
            let app = build_app(None).expect("failed to build spike app");
            run_ci_update(app.handle().clone(), out_path);
        }
        Args::Gui => {}
    }

    // 2. GUI run
    let app = build_app(Some(TEST_ORIGIN_PORT)).expect("failed to build spike app");
    app.run(|_app, event| {
        if let tauri::RunEvent::ExitRequested { .. } = event {
            // spike: nothing to stop
        }
    });
}

fn build_app(_test_port: Option<u16>) -> tauri::Result<tauri::App> {
    tauri::Builder::default()
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

            builder = builder.on_download(|_webview, event| match event {
                DownloadEvent::Requested { url, destination } => {
                    eprintln!("[download] Requested {url}");
                    let suggested = destination
                        .file_name()
                        .map(|s| s.to_string_lossy().to_string())
                        .unwrap_or_else(|| "download".into());
                    // native Save dialog seeded with the suggested filename (contract §6.5)
                    match tauri_plugin_dialog::DialogExt::dialog(&_webview)
                        .file()
                        .set_file_name(&suggested)
                        .blocking_save_file()
                    {
                        Some(path) => {
                            let p = match &path {
                                tauri_plugin_dialog::FilePath::Path(p) => p.clone(),
                                tauri_plugin_dialog::FilePath::Url(u) => PathBuf::from(u.path()),
                            };
                            *destination = p;
                            true
                        }
                        None => false, // cancelled
                    }
                }
                DownloadEvent::Finished { url, path, success } => {
                    eprintln!("[download] Finished {url} -> {path:?} success={success}");
                    true
                }
                _ => true,
            });

            builder.build()?;

            // spike updater plugins
            #[cfg(not(target_os = "macos"))]
            {
                app.handle().plugin(
                    tauri_plugin_updater::Builder::new().build(),
                )?;
            }
            #[cfg(target_os = "macos")]
            {
                app.handle().plugin(tauri_plugin_sparkle_updater::init())?;
            }
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
        .build(tauri::generate_context!())
}
