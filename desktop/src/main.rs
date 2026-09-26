#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
//! Persona Forge desktop shell entry point (contract §6.8: argument parsing runs before
//! anything else, including single-instance).

mod app;
mod args;
mod bundle_paths;
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

use std::io::Write;
use std::process::ExitCode;

fn main() -> ExitCode {
    let context = tauri::generate_context!();

    match args::parse(std::env::args().skip(1)) {
        Err((flag, code)) => {
            eprintln!("unknown argument: {flag}");
            ExitCode::from(code as u8)
        }
        Ok(args::Args::SmokeTest(out_path)) => run_smoke_test(&context, &out_path),
        #[cfg(feature = "ci-hooks")]
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

#[cfg(feature = "ci-hooks")]
fn run_ci_update(context: tauri::Context, out_path: std::path::PathBuf) -> ExitCode {
    // Phase 6A/6B port the client side from the desktop-spike-final tag; not wired yet.
    let _ = (context, out_path);
    eprintln!("persona-forge-desktop: --ci-update is not implemented until Phase 6A/6B");
    ExitCode::FAILURE
}
