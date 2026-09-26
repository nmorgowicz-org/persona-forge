//! The startup state machine (contract §6.1), IPC commands (§6.6), window construction and
//! nav/download/menu/tray wiring (§6.4, §6.5). Runs on `tauri::Builder::default()`; every
//! plugin is registered on the `Builder` chain, never inside `.setup()` (Phase 1 finding:
//! `--ci-update` drives the updater right after `build()`, before `run()` would ever call
//! `.setup()`'s closure).

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;

use parking_lot::Mutex;
use persona_forge_launcher::{bootstrap, health, manifest, paths, supervisor};
use serde::Serialize;
use tauri::menu::MenuEvent;
use tauri::{AppHandle, Emitter, Manager, RunEvent, Runtime, WebviewUrl, WebviewWindowBuilder};

use crate::bundle_paths::bundle_paths;
use crate::downloads::unique_path;
use crate::marker::{current_platform, desktop_marker_script};
use crate::{logs, menu, nav, netinfo, port, settings, tray};

const READY_TIMEOUT: Duration = Duration::from_secs(180);
const STOP_GRACE: Duration = Duration::from_secs(10);

#[derive(Debug, Clone, Serialize)]
pub struct BootstrapState {
    pub step: &'static str,
    pub ready: bool,
    pub error: Option<String>,
    pub log_tail: Vec<String>,
}

impl Default for BootstrapState {
    fn default() -> Self {
        BootstrapState {
            step: "verify",
            ready: false,
            error: None,
            log_tail: Vec::new(),
        }
    }
}

pub struct ManagedState {
    pub bootstrap: Mutex<BootstrapState>,
    pub server: Mutex<Option<supervisor::ServerHandle>>,
    pub port: Mutex<Option<u16>>,
    pub desktop_dir: PathBuf,
    pub downloads_pending: Mutex<HashMap<String, (PathBuf, String)>>,
    pub translocation_disabled: AtomicBool,
    pub quitting: AtomicBool,
}

fn current_port<R: Runtime>(app: &AppHandle<R>) -> u16 {
    (*app.state::<ManagedState>().port.lock()).unwrap_or(0)
}

fn environ() -> HashMap<String, String> {
    std::env::vars().collect()
}

fn home_dir() -> PathBuf {
    std::env::var("HOME")
        .or_else(|_| std::env::var("USERPROFILE"))
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("."))
}

// ---------------------------------------------------------------------------------------------
// IPC commands (contract §6.6). Splash: get_bootstrap_state, retry_bootstrap, show_logs,
// quit_app, open_settings. Settings: get_settings, apply_settings, list_addresses, copy_text.
// ---------------------------------------------------------------------------------------------

#[tauri::command]
fn get_bootstrap_state(state: tauri::State<ManagedState>) -> BootstrapState {
    state.bootstrap.lock().clone()
}

#[tauri::command]
fn retry_bootstrap<R: Runtime>(app: AppHandle<R>) {
    {
        let state = app.state::<ManagedState>();
        *state.bootstrap.lock() = BootstrapState::default();
    }
    spawn_bootstrap_thread(app);
}

#[tauri::command]
fn show_logs<R: Runtime>(app: AppHandle<R>) -> Result<(), String> {
    let state = app.state::<ManagedState>();
    tauri_plugin_opener::reveal_item_in_dir(state.desktop_dir.join("logs"))
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn quit_app<R: Runtime>(app: AppHandle<R>) {
    do_quit(&app);
}

#[tauri::command]
fn open_settings<R: Runtime>(app: AppHandle<R>) -> Result<(), String> {
    open_settings_window(&app).map_err(|e| e.to_string())
}

#[derive(Serialize)]
struct SettingsPayload {
    port_mode: String,
    port: Option<u16>,
    network_access: bool,
    tray_enabled: bool,
    ask_where_to_save: bool,
}

#[tauri::command]
fn get_settings<R: Runtime>(app: AppHandle<R>) -> SettingsPayload {
    let state = app.state::<ManagedState>();
    let s = settings::load(&state.desktop_dir);
    SettingsPayload {
        port_mode: if s.port_mode == settings::PortMode::Fixed {
            "fixed".into()
        } else {
            "auto".into()
        },
        port: s.port,
        network_access: s.network_access,
        tray_enabled: s.tray_enabled,
        ask_where_to_save: s.ask_where_to_save,
    }
}

#[tauri::command]
fn apply_settings<R: Runtime>(
    app: AppHandle<R>,
    port_mode: String,
    port: Option<u16>,
    network_access: bool,
    tray_enabled: bool,
    ask_where_to_save: bool,
) -> Result<(), String> {
    if let Some(p) = port {
        if !settings::is_valid_port(p) {
            return Err("port must be between 1024 and 65535".to_string());
        }
    }
    let state = app.state::<ManagedState>();
    let mut s = settings::load(&state.desktop_dir);
    let old_mode = s.port_mode.clone();
    let old_network = s.network_access;
    let old_port = s.port;

    s.port_mode = if port_mode == "fixed" {
        settings::PortMode::Fixed
    } else {
        settings::PortMode::Auto
    };
    s.port = port.or(s.port);
    s.network_access = network_access;
    s.tray_enabled = tray_enabled;
    s.ask_where_to_save = ask_where_to_save;
    settings::save(&state.desktop_dir, &s).map_err(|e| e.to_string())?;

    let needs_restart =
        s.port_mode != old_mode || s.port != old_port || s.network_access != old_network;
    if needs_restart {
        {
            let mut b = state.bootstrap.lock();
            *b = BootstrapState {
                step: "start",
                ..Default::default()
            };
        }
        if let Some(main) = app.get_webview_window("main") {
            let _ = main.navigate("tauri://localhost/index.html".parse().unwrap());
        }
        spawn_restart_thread(app.clone());
    }
    Ok(())
}

#[tauri::command]
fn list_addresses<R: Runtime>(app: AppHandle<R>) -> Vec<String> {
    let state = app.state::<ManagedState>();
    let Some(port) = *state.port.lock() else {
        return Vec::new();
    };
    let mut out = vec![format!("http://127.0.0.1:{port}")];
    if let Ok(ifaces) = if_addrs::get_if_addrs() {
        let ips: Vec<std::net::IpAddr> = ifaces.into_iter().map(|i| i.ip()).collect();
        for ip in netinfo::lan_ipv4(&ips) {
            out.push(format!("http://{ip}:{port}"));
        }
    }
    out
}

#[tauri::command]
fn copy_text<R: Runtime>(app: AppHandle<R>, text: String) -> Result<(), String> {
    use tauri_plugin_clipboard_manager::ClipboardExt;
    app.clipboard().write_text(text).map_err(|e| e.to_string())
}

// ---------------------------------------------------------------------------------------------
// Builder
// ---------------------------------------------------------------------------------------------

pub fn build_app(context: tauri::Context) -> tauri::Result<tauri::App> {
    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.show();
                let _ = w.set_focus();
            }
        }))
        .plugin(
            tauri_plugin_window_state::Builder::new()
                .skip_initial_state("main")
                .build(),
        )
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_log::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            get_bootstrap_state,
            retry_bootstrap,
            show_logs,
            quit_app,
            open_settings,
            get_settings,
            apply_settings,
            list_addresses,
            copy_text,
        ]);

    builder
        .setup(|app| {
            let home = home_dir();
            let platform = current_platform();
            let env = environ();
            let desktop_dir = paths::app_data_root(&env, platform, &home).join("desktop");
            std::fs::create_dir_all(&desktop_dir)?;
            std::fs::create_dir_all(desktop_dir.join("logs"))?;
            let downloads_tmp = desktop_dir.join("downloads-tmp");
            let _ = std::fs::remove_dir_all(&downloads_tmp); // startup: drop ask-mode leftovers
            std::fs::create_dir_all(&downloads_tmp)?;

            logs::rotate_if_large(&desktop_dir.join("logs").join("server.log"));
            logs::rotate_if_large(&desktop_dir.join("logs").join("bootstrap.log"));

            app.manage(ManagedState {
                bootstrap: Mutex::new(BootstrapState::default()),
                server: Mutex::new(None),
                port: Mutex::new(None),
                desktop_dir: desktop_dir.clone(),
                downloads_pending: Mutex::new(HashMap::new()),
                translocation_disabled: AtomicBool::new(false),
                quitting: AtomicBool::new(false),
            });

            let translocation_disabled = crate::translocation::check_and_handle(app.handle());
            app.state::<ManagedState>()
                .translocation_disabled
                .store(translocation_disabled, Ordering::SeqCst);

            let menu = menu::build_menu(app.handle(), translocation_disabled)?;
            app.set_menu(menu)?;
            app.on_menu_event(handle_menu_event);

            let s = settings::load(&desktop_dir);
            if s.tray_enabled {
                let icon_bytes: &[u8] = if cfg!(target_os = "macos") {
                    include_bytes!("../icons/tray/tray-template@2x.png")
                } else {
                    include_bytes!("../icons/tray/tray-color@2x.png")
                };
                if let Err(e) =
                    tray::build_tray(app.handle(), icon_bytes, cfg!(target_os = "macos"))
                {
                    log::warn!("tray creation failed; disabling tray for this session: {e}");
                }
            }

            let mut window_builder =
                WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                    .title("Persona Forge")
                    .inner_size(1280.0, 832.0)
                    .min_inner_size(960.0, 640.0)
                    .initialization_script(desktop_marker_script(current_platform()));

            #[cfg(target_os = "macos")]
            {
                window_builder = window_builder
                    .title_bar_style(tauri::TitleBarStyle::Transparent)
                    .hidden_title(true)
                    .transparent(true)
                    .effects(tauri::utils::config::WindowEffectsConfig {
                        effects: vec![tauri_utils::WindowEffect::Sidebar],
                        state: Some(tauri_utils::WindowEffectState::FollowsWindowActiveState),
                        radius: None,
                        color: None,
                    });
            }

            let nav_handle = app.handle().clone();
            window_builder = window_builder.on_navigation(move |url| {
                let port = current_port(&nav_handle);
                match nav::classify(url, port) {
                    nav::Decision::Allow => true,
                    nav::Decision::OpenExternal => {
                        let _ = tauri_plugin_opener::open_url(url.as_str(), None::<&str>);
                        false
                    }
                    nav::Decision::Deny => false,
                }
            });

            let new_window_handle = app.handle().clone();
            window_builder = window_builder.on_new_window(move |url, _features| {
                let port = current_port(&new_window_handle);
                if nav::classify(&url, port) == nav::Decision::OpenExternal {
                    let _ = tauri_plugin_opener::open_url(url.as_str(), None::<&str>);
                }
                tauri::webview::NewWindowResponse::Deny
            });

            let download_app_handle = app.handle().clone();
            window_builder = window_builder.on_download(move |webview, event| {
                handle_download_event(&download_app_handle, &webview, event)
            });

            window_builder.build()?;

            spawn_bootstrap_thread(app.handle().clone());

            Ok(())
        })
        .on_window_event(|window, event| {
            if window.label() != "main" {
                return;
            }
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                #[cfg_attr(target_os = "macos", allow(unused_variables))]
                let app = window.app_handle();
                #[cfg(target_os = "macos")]
                {
                    api.prevent_close();
                    let _ = window.hide();
                }
                #[cfg(not(target_os = "macos"))]
                {
                    let s = settings::load(&app.state::<ManagedState>().desktop_dir);
                    if s.tray_enabled {
                        api.prevent_close();
                        let _ = window.hide();
                        notify_once_tray_hidden(app);
                    }
                    // tray disabled: default close behavior runs (quits).
                }
            }
        })
        .build(context)
}

#[cfg(not(target_os = "macos"))]
fn notify_once_tray_hidden<R: Runtime>(app: &AppHandle<R>) {
    use std::sync::OnceLock;
    static SHOWN: OnceLock<()> = OnceLock::new();
    if SHOWN.set(()).is_ok() {
        use tauri_plugin_notification::NotificationExt;
        let _ = app
            .notification()
            .builder()
            .title("Persona Forge")
            .body("Persona Forge is still running in the system tray.")
            .show();
    }
}

fn handle_menu_event<R: Runtime>(app: &AppHandle<R>, event: MenuEvent) {
    let id = event.id().0.as_str();
    match id {
        menu::ID_CHECK_UPDATES | tray::ID_CHECK_UPDATES => {
            // Disabled until Phase 6A wires the real updater UX.
        }
        menu::ID_SETTINGS => {
            let _ = open_settings_window(app);
        }
        menu::ID_ABOUT_FALLBACK => {
            // Non-macOS "About" fallback: a simple dialog with the build version.
            use tauri_plugin_dialog::DialogExt;
            app.dialog()
                .message(format!("Persona Forge {}", app.package_info().version))
                .title("About Persona Forge")
                .blocking_show();
        }
        menu::ID_OPEN_IN_BROWSER | tray::ID_OPEN_IN_BROWSER => open_in_browser(app),
        menu::ID_COPY_SERVER_ADDRESS | tray::ID_COPY_SERVER_ADDRESS => copy_primary_address(app),
        menu::ID_SHOW_LOGS | tray::ID_SHOW_LOGS => {
            let state = app.state::<ManagedState>();
            let _ = tauri_plugin_opener::reveal_item_in_dir(state.desktop_dir.join("logs"));
        }
        menu::ID_DOCUMENTATION => {
            let _ = tauri_plugin_opener::open_url(
                "https://github.com/nmorgowicz-org/persona-forge#readme",
                None::<&str>,
            );
        }
        menu::ID_REPORT_ISSUE => {
            let _ = tauri_plugin_opener::open_url(
                "https://github.com/nmorgowicz-org/persona-forge/issues/new",
                None::<&str>,
            );
        }
        tray::ID_OPEN => {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.show();
                let _ = w.set_focus();
            }
        }
        tray::ID_QUIT => do_quit(app),
        _ => {}
    }
}

fn open_in_browser<R: Runtime>(app: &AppHandle<R>) {
    let port = *app.state::<ManagedState>().port.lock();
    if let Some(port) = port {
        let _ = tauri_plugin_opener::open_url(format!("http://127.0.0.1:{port}"), None::<&str>);
    }
}

fn copy_primary_address<R: Runtime>(app: &AppHandle<R>) {
    use tauri_plugin_clipboard_manager::ClipboardExt;
    let state = app.state::<ManagedState>();
    let port = *state.port.lock();
    let Some(port) = port else { return };
    let s = settings::load(&state.desktop_dir);
    let text = if s.network_access {
        if_addrs::get_if_addrs()
            .ok()
            .and_then(|ifaces| {
                netinfo::lan_ipv4(&ifaces.into_iter().map(|i| i.ip()).collect::<Vec<_>>())
                    .into_iter()
                    .next()
            })
            .map(|ip| format!("http://{ip}:{port}"))
            .unwrap_or_else(|| format!("http://127.0.0.1:{port}"))
    } else {
        format!("http://127.0.0.1:{port}")
    };
    let _ = app.clipboard().write_text(text);
}

fn open_settings_window<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<()> {
    if let Some(w) = app.get_webview_window("settings") {
        w.show()?;
        w.set_focus()?;
        return Ok(());
    }
    WebviewWindowBuilder::new(app, "settings", WebviewUrl::App("settings.html".into()))
        .title("Persona Forge Settings")
        .inner_size(520.0, 440.0)
        .resizable(false)
        .initialization_script(desktop_marker_script(current_platform()))
        .build()?;
    Ok(())
}

fn do_quit<R: Runtime>(app: &AppHandle<R>) {
    let state = app.state::<ManagedState>();
    if state.quitting.swap(true, Ordering::SeqCst) {
        return; // already quitting
    }
    if let Some(handle) = state.server.lock().take() {
        let _ = handle.stop(STOP_GRACE);
        let _ = std::fs::remove_file(state.desktop_dir.join("server.pid"));
    }
    app.exit(0);
}

/// Handles `SIGTERM`/`SIGINT`/`SIGHUP` (Unix) and `RunEvent::ExitRequested`: both run `Stopping`
/// exactly like menu/tray Quit (contract §6.2).
pub fn handle_run_event<R: Runtime>(app: &AppHandle<R>, event: &RunEvent) {
    if let RunEvent::ExitRequested { .. } = event {
        do_quit(app);
    }
}

#[cfg(unix)]
pub fn install_unix_signal_quit<R: Runtime + 'static>(app: AppHandle<R>) {
    for sig in [libc::SIGTERM, libc::SIGINT, libc::SIGHUP] {
        let app = app.clone();
        std::thread::spawn(move || unsafe {
            let mut set: libc::sigset_t = std::mem::zeroed();
            libc::sigemptyset(&mut set);
            libc::sigaddset(&mut set, sig);
            let mut received = 0;
            libc::sigwait(&set, &mut received);
            do_quit(&app);
        });
    }
}

// ---------------------------------------------------------------------------------------------
// Downloads (contract §6.5, D21). Never blocks: `on_download` runs on the main thread.
// ---------------------------------------------------------------------------------------------

fn handle_download_event<R: Runtime>(
    app: &AppHandle<R>,
    webview: &tauri::Webview<R>,
    event: tauri::webview::DownloadEvent,
) -> bool {
    use tauri::webview::DownloadEvent;
    let state = app.state::<ManagedState>();
    match event {
        DownloadEvent::Requested { url, destination } => {
            let name = destination
                .file_name()
                .map(|s| s.to_string_lossy().to_string())
                .unwrap_or_else(|| "download".to_string());
            let s = settings::load(&state.desktop_dir);
            let dir = if s.ask_where_to_save {
                state.desktop_dir.join("downloads-tmp")
            } else {
                app.path()
                    .download_dir()
                    .unwrap_or_else(|_| std::env::temp_dir())
            };
            if std::fs::create_dir_all(&dir).is_err() {
                return false;
            }
            let mut pending = state.downloads_pending.lock();
            let reserved: Vec<PathBuf> = pending.values().map(|(p, _)| p.clone()).collect();
            let target = unique_path(&dir, &name, &reserved);
            log::info!("download destination {url} -> {}", target.display());
            pending.insert(url.to_string(), (target.clone(), name));
            *destination = target;
            true
        }
        DownloadEvent::Finished { url, success, .. } => {
            let entry = state.downloads_pending.lock().remove(url.as_str());
            let Some((dest, name)) = entry else {
                return true;
            };
            if !success {
                let _ = std::fs::remove_file(&dest);
                notify(app, "Download failed", &name);
                return true;
            }
            let s = settings::load(&state.desktop_dir);
            if s.ask_where_to_save {
                use tauri_plugin_dialog::DialogExt;
                let app2 = app.clone();
                let name2 = name.clone();
                webview
                    .dialog()
                    .file()
                    .set_file_name(&name)
                    .save_file(move |choice| {
                        use tauri_plugin_dialog::FilePath;
                        let chosen: Option<PathBuf> = match choice {
                            Some(FilePath::Path(p)) => Some(p),
                            Some(FilePath::Url(u)) => u.to_file_path().ok(),
                            None => None,
                        };
                        match chosen {
                            Some(final_dest) => {
                                if move_file(&dest, &final_dest).is_ok() {
                                    notify(&app2, "Saved", &name2);
                                    let _ = tauri_plugin_opener::reveal_item_in_dir(&final_dest);
                                }
                            }
                            None => {
                                let _ = std::fs::remove_file(&dest);
                            }
                        }
                    });
            } else {
                notify(app, "Saved", &name);
                let _ = tauri_plugin_opener::reveal_item_in_dir(&dest);
            }
            true
        }
        _ => true,
    }
}

fn move_file(from: &std::path::Path, to: &std::path::Path) -> std::io::Result<()> {
    if std::fs::rename(from, to).is_ok() {
        return Ok(());
    }
    std::fs::copy(from, to)?;
    std::fs::remove_file(from)
}

fn notify<R: Runtime>(app: &AppHandle<R>, title: &str, body: &str) {
    use tauri_plugin_notification::NotificationExt;
    let _ = app.notification().builder().title(title).body(body).show();
}

// ---------------------------------------------------------------------------------------------
// Bootstrap state machine (contract §6.1)
// ---------------------------------------------------------------------------------------------

struct ThreadProgress<R: Runtime> {
    app: AppHandle<R>,
}

impl<R: Runtime> bootstrap::Progress for ThreadProgress<R> {
    fn step(&self, step: bootstrap::Step) {
        let name = match step {
            bootstrap::Step::Venv => "venv",
            bootstrap::Step::Sync => "sync",
            bootstrap::Step::Install => "install",
        };
        emit_step(&self.app, name, None);
    }
}

fn emit_step<R: Runtime>(app: &AppHandle<R>, step: &'static str, line: Option<String>) {
    {
        let state = app.state::<ManagedState>();
        let mut b = state.bootstrap.lock();
        b.step = step;
        if let Some(l) = &line {
            b.log_tail.push(l.clone());
            while b.log_tail.len() > 200 {
                b.log_tail.remove(0);
            }
        }
    }
    let _ = app.emit(
        "bootstrap://progress",
        serde_json::json!({ "step": step, "line": line }),
    );
}

fn set_error<R: Runtime>(app: &AppHandle<R>, message: String) {
    let state = app.state::<ManagedState>();
    let mut b = state.bootstrap.lock();
    b.error = Some(message);
}

fn spawn_bootstrap_thread<R: Runtime + 'static>(app: AppHandle<R>) {
    std::thread::spawn(move || run_bootstrap(app));
}

fn spawn_restart_thread<R: Runtime + 'static>(app: AppHandle<R>) {
    std::thread::spawn(move || {
        {
            let state = app.state::<ManagedState>();
            let taken = state.server.lock().take();
            if let Some(handle) = taken {
                let _ = handle.stop(STOP_GRACE);
            }
        }
        run_bootstrap(app);
    });
}

fn run_bootstrap<R: Runtime + 'static>(app: AppHandle<R>) {
    emit_step(&app, "verify", None);

    let (payload_dir, uv_path) = match bundle_paths(app.package_info()) {
        Ok(p) => p,
        Err(e) => return set_error(&app, e.to_string()),
    };
    #[cfg(debug_assertions)]
    if let Ok(app_resource_dir) = app.path().resource_dir() {
        crate::bundle_paths::assert_matches_app_resource_dir(&payload_dir, &app_resource_dir);
    }
    let manifest = match manifest::load(&payload_dir).and_then(|m| {
        manifest::verify_payload(&m, &payload_dir)?;
        Ok(m)
    }) {
        Ok(m) => m,
        Err(e) => return set_error(&app, e.to_string()),
    };

    let home = home_dir();
    let platform = current_platform();
    let env = environ();
    let versions_dir = paths::versions_dir(&env, platform, &home);
    let current_marker = paths::current_marker(&env, platform, &home);
    let runner = bootstrap::SystemRunner;
    let progress = ThreadProgress { app: app.clone() };

    let env_dir = match bootstrap::ensure_env_with_progress(
        &manifest,
        &payload_dir,
        &uv_path,
        &versions_dir,
        &current_marker,
        &runner,
        &progress,
    ) {
        Ok(d) => d,
        Err(e) => return set_error(&app, e.to_string()),
    };
    let python = bootstrap::venv_python(&env_dir);

    let desktop_dir = app.state::<ManagedState>().desktop_dir.clone();

    // Unix orphan recovery (§6.2) before port selection.
    #[cfg(unix)]
    {
        let pidfile = desktop_dir.join("server.pid");
        if let Some(rec) = supervisor::read_pidfile(&pidfile) {
            let _ = supervisor::kill_orphan(&rec, STOP_GRACE);
        }
        let _ = std::fs::remove_file(&pidfile);
    }

    let s = settings::load(&desktop_dir);
    let mode = if s.port_mode == settings::PortMode::Fixed {
        port::PortMode::Fixed
    } else {
        port::PortMode::Auto
    };
    let probe = |p: u16| match health::probe_port("127.0.0.1", p, Duration::from_secs(2)) {
        health::PortState::Free => port::PortState::Free,
        health::PortState::PersonaForge => port::PortState::PersonaForge,
        health::PortState::Other => port::PortState::Other,
    };
    let decision = port::select_port(mode, s.port, probe);

    let network_access = s.network_access;
    let chosen_port = match decision {
        port::PortDecision::Use(p) => p,
        port::PortDecision::Moved { to, .. } => {
            let mut s2 = s;
            s2.port = Some(to);
            let _ = settings::save(&desktop_dir, &s2);
            to
        }
        port::PortDecision::ExternalPersonaForge(p) => {
            return set_error(
                &app,
                format!(
                    "Persona Forge is already running outside the app on port {p}. Stop it and Retry, or choose another port in Settings."
                ),
            );
        }
        port::PortDecision::FixedPortBusy(p) => {
            return set_error(&app, format!("Port {p} is in use by another program."));
        }
        port::PortDecision::NoneFree => {
            return set_error(
                &app,
                "No free port found in the 8318-8348 range.".to_string(),
            );
        }
    };

    *app.state::<ManagedState>().port.lock() = Some(chosen_port);

    emit_step(&app, "start", None);
    let host = if network_access {
        "0.0.0.0"
    } else {
        "127.0.0.1"
    }
    .to_string();
    let log_path = desktop_dir.join("logs").join("server.log");
    let spec = supervisor::ServerSpec {
        python,
        host,
        port: chosen_port,
        extra_env: vec![
            ("PERSONA_FORGE_SHELL".to_string(), "desktop".to_string()),
            ("PERSONA_FORGE_PORT".to_string(), chosen_port.to_string()),
        ],
        log_path,
    };
    let mut handle = match supervisor::ServerHandle::spawn(&spec) {
        Ok(h) => h,
        Err(e) => return set_error(&app, e.to_string()),
    };

    #[cfg(unix)]
    {
        let rec = supervisor::PidRecord {
            pid: handle.pid(),
            pgid: handle.pid(),
            port: chosen_port,
            started_at: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_secs(),
        };
        let _ = supervisor::write_pidfile(&desktop_dir.join("server.pid"), &rec);
    }

    emit_step(&app, "wait", None);
    if let Err(e) = supervisor::wait_ready(&mut handle, chosen_port, READY_TIMEOUT) {
        let msg = match e {
            supervisor::ReadyError::Exited(code) => {
                format!("server exited before becoming ready (code {code:?})")
            }
            supervisor::ReadyError::Timeout => {
                "timed out waiting for the server to become ready".to_string()
            }
        };
        let _ = handle.stop(STOP_GRACE);
        return set_error(&app, msg);
    }

    {
        let state = app.state::<ManagedState>();
        *state.server.lock() = Some(handle);
        state.bootstrap.lock().ready = true;
    }

    if let Some(main) = app.get_webview_window("main") {
        if let Ok(url) = format!("http://127.0.0.1:{chosen_port}/").parse() {
            let _ = main.navigate(url);
        }
    }
}
