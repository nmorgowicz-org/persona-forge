//! Thin native bootstrap for Persona Forge release archives
//! (docs/plans/20260829-no_more_docker_requirement.md Phase 7).
//!
//! Every invocation: (1) validate the bundle manifest, (2) verify every referenced member's
//! SHA-256 before anything is mutated, (3) provision (or reuse) a versioned app-managed Python
//! env via bundled `uv`, (4) invoke the installed `persona_forge.cli` module through
//! the relocated venv's Python, passing user arguments straight through (`doctor`,
//! `setup`, `serve`, ...). Never logs
//! environment variables or manifest secrets - there are none in the manifest schema, and none
//! of the args this launcher forwards are inspected or echoed beyond argv itself.

mod bootstrap;
mod manifest;
mod paths;

use std::env;
use std::path::PathBuf;
use std::process::ExitCode;

fn bundle_dir() -> PathBuf {
    env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|p| p.to_path_buf()))
        .unwrap_or_else(|| PathBuf::from("."))
}

fn platform_tag() -> &'static str {
    if cfg!(target_os = "windows") {
        "windows"
    } else if cfg!(target_os = "macos") {
        "darwin"
    } else {
        "linux"
    }
}

fn run() -> Result<ExitCode, String> {
    let bundle = bundle_dir();

    let manifest = manifest::load(&bundle).map_err(|e| format!("manifest error: {e}"))?;
    manifest::verify_bundle(&manifest, &bundle).map_err(|e| format!("bundle verification failed: {e}"))?;

    let environ: paths::Environ = env::vars().collect();
    let home = env::var("HOME")
        .or_else(|_| env::var("USERPROFILE"))
        .map(PathBuf::from)
        .map_err(|_| "could not determine home directory (HOME/USERPROFILE unset)".to_string())?;
    let platform = platform_tag();

    let versions_dir = paths::versions_dir(&environ, platform, &home);
    let current_marker = paths::current_marker(&environ, platform, &home);
    let uv_path = bundle.join(&manifest.uv.file);

    let runner = bootstrap::SystemRunner;
    let env_dir = bootstrap::ensure_env(&manifest, &bundle, &uv_path, &versions_dir, &current_marker, &runner)
        .map_err(|e| format!("environment bootstrap failed: {e}"))?;

    let python = bootstrap::venv_python(&env_dir);
    let args: Vec<String> = env::args().skip(1).collect();

    exec_python_module(&python, &args)
}

#[cfg(unix)]
fn exec_python_module(python: &std::path::Path, args: &[String]) -> Result<ExitCode, String> {
    use std::os::unix::process::CommandExt;
    let err = std::process::Command::new(python)
        .args(["-m", "persona_forge.cli"])
        .args(args)
        .exec();
    Err(format!("failed to exec {}: {err}", python.display()))
}

#[cfg(not(unix))]
fn exec_python_module(python: &std::path::Path, args: &[String]) -> Result<ExitCode, String> {
    let status = std::process::Command::new(python)
        .args(["-m", "persona_forge.cli"])
        .args(args)
        .status()
        .map_err(|e| format!("failed to spawn {}: {e}", python.display()))?;
    let code = status.code().unwrap_or(1);
    Ok(ExitCode::from(code.clamp(0, 255) as u8))
}

fn main() -> ExitCode {
    match run() {
        Ok(code) => code,
        Err(msg) => {
            eprintln!("persona-forge-launcher: {msg}");
            ExitCode::FAILURE
        }
    }
}
