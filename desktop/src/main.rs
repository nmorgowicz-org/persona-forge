#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
//! Persona Forge desktop shell entry point (contract §6.8: argument parsing runs before
//! anything else, including single-instance).

mod app;
mod args;
mod bundle_paths;
#[cfg(feature = "ci-hooks")]
mod ci_hooks;
mod downloads;
mod logs;
mod marker;
mod menu;
mod nav;
mod netinfo;
mod port;
mod settings;
mod smoke;
mod translocation;
mod tray;
mod updates;

use std::io::Write;
use std::process::ExitCode;

fn main() -> ExitCode {
    // Unix (contract §6.2): block the quit signals process-wide BEFORE any thread exists.
    // Without this, a process-directed SIGTERM can be delivered to a thread without a
    // handler and the default disposition kills the app instantly, bypassing the graceful
    // do_quit path and leaking the server (observed by the Phase 4 GUI check). The
    // sigwait thread installed later then receives the signals deterministically.
    #[cfg(unix)]
    unsafe {
        let mut set: libc::sigset_t = std::mem::zeroed();
        libc::sigemptyset(&mut set);
        for sig in [libc::SIGTERM, libc::SIGINT, libc::SIGHUP] {
            libc::sigaddset(&mut set, sig);
        }
        libc::pthread_sigmask(libc::SIG_BLOCK, &set, std::ptr::null_mut());
    }

    let context = tauri::generate_context!();

    match args::parse(std::env::args().skip(1)) {
        Err((flag, code)) => {
            eprintln!("unknown argument: {flag}");
            ExitCode::from(code as u8)
        }
        Ok(args::Args::SmokeTest(out_path)) => run_smoke_test(&context, &out_path),
        #[cfg(all(feature = "ci-hooks", not(target_os = "macos")))]
        Ok(args::Args::CiUpdate(out_path)) => run_ci_update(context, out_path),
        Ok(args::Args::Gui) => run_gui(context),
    }
}

fn run_smoke_test(context: &tauri::Context, out_path: &std::path::Path) -> ExitCode {
    let environ: std::collections::HashMap<String, String> = std::env::vars().collect();
    let home = std::env::var("HOME")
        .or_else(|_| std::env::var("USERPROFILE"))
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|_| std::path::PathBuf::from("."));
    let platform = marker::current_platform();

    let result = smoke::run(context.package_info(), &environ, &home, platform);
    let ok = result.ok;

    if let Ok(json) = serde_json::to_string_pretty(&result) {
        println!("{json}");
        if let Ok(mut f) = std::fs::File::create(out_path) {
            let _ = f.write_all(json.as_bytes());
        }
    }

    if ok {
        ExitCode::SUCCESS
    } else {
        ExitCode::FAILURE
    }
}

fn run_gui(context: tauri::Context) -> ExitCode {
    let app = match app::build_app(context) {
        Ok(app) => app,
        Err(e) => {
            eprintln!("persona-forge-desktop: failed to build app: {e}");
            return ExitCode::FAILURE;
        }
    };

    #[cfg(unix)]
    app::install_unix_signal_quit(app.handle().clone());

    app.run(|app_handle, event| {
        app::handle_run_event(app_handle, &event);
    });

    ExitCode::SUCCESS
}

#[cfg(all(feature = "ci-hooks", not(target_os = "macos")))]
fn run_ci_update(context: tauri::Context, out_path: std::path::PathBuf) -> ExitCode {
    let app = match tauri::Builder::default()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .build(context)
    {
        Ok(app) => app,
        Err(error) => {
            eprintln!("persona-forge-desktop: failed to initialize updater: {error}");
            return ExitCode::FAILURE;
        }
    };

    ci_hooks::run(app.handle().clone(), out_path)
}
