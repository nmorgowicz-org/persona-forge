//! `--smoke-test` mode (contract §6.8): verify → ensure_env → select port → start → wait for
//! /health → stop → port free again, writing the documented JSON shape. Runs before any Tauri
//! or webview initialization — `run` only depends on the launcher lib and `tauri::PackageInfo`
//! (for `bundle_paths`), never an `AppHandle`.

use std::collections::HashMap;
use std::time::{Duration, Instant};

use persona_forge_launcher::{bootstrap, health, manifest, paths, supervisor};
use serde::Serialize;
use tauri::PackageInfo;

use crate::bundle_paths::bundle_paths;

#[derive(Debug, Serialize)]
pub struct StepResult {
    pub name: &'static str,
    pub ok: bool,
    pub ms: u128,
    pub detail: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct SmokeResult {
    pub ok: bool,
    pub version: String,
    pub port: u16,
    pub steps: Vec<StepResult>,
}

/// Records one step's timing/outcome and returns its value, or `None` (with the failure
/// already pushed onto `steps`) so the caller can bail with `return`.
fn record<T, E: ToString>(
    steps: &mut Vec<StepResult>,
    name: &'static str,
    started: Instant,
    result: Result<T, E>,
) -> Option<T> {
    match result {
        Ok(v) => {
            steps.push(StepResult {
                name,
                ok: true,
                ms: started.elapsed().as_millis(),
                detail: None,
            });
            Some(v)
        }
        Err(e) => {
            steps.push(StepResult {
                name,
                ok: false,
                ms: started.elapsed().as_millis(),
                detail: Some(e.to_string()),
            });
            None
        }
    }
}

pub fn run(
    package_info: &PackageInfo,
    environ: &HashMap<String, String>,
    home: &std::path::Path,
    platform: &str,
) -> SmokeResult {
    let version = package_info.version.to_string();
    let mut steps: Vec<StepResult> = Vec::new();
    let failed = |steps: Vec<StepResult>, version: &str| SmokeResult {
        ok: false,
        version: version.to_string(),
        port: 0,
        steps,
    };

    let t = Instant::now();
    let Some((payload_dir, uv_path)) = record(&mut steps, "verify", t, bundle_paths(package_info))
    else {
        return failed(steps, &version);
    };

    let t = Instant::now();
    let manifest = match manifest::load(&payload_dir) {
        Ok(m) => m,
        Err(e) => {
            record::<(), _>(&mut steps, "verify", t, Err(e));
            return failed(steps, &version);
        }
    };
    let Some(()) = record(
        &mut steps,
        "verify",
        t,
        manifest::verify_payload(&manifest, &payload_dir),
    ) else {
        return failed(steps, &version);
    };

    let versions_dir = paths::versions_dir(environ, platform, home);
    let current_marker = paths::current_marker(environ, platform, home);
    let runner = bootstrap::SystemRunner;
    let t = Instant::now();
    let Some(env_dir) = record(
        &mut steps,
        "venv",
        t,
        bootstrap::ensure_env(
            &manifest,
            &payload_dir,
            &uv_path,
            &versions_dir,
            &current_marker,
            &runner,
        ),
    ) else {
        return failed(steps, &version);
    };
    let python = bootstrap::venv_python(&env_dir);

    let probe = |port: u16| health::probe_port("127.0.0.1", port, Duration::from_secs(2));
    let t = Instant::now();
    let port_check: Result<u16, String> = match probe(8318) {
        health::PortState::Free => Ok(8318),
        _ => Err("port 8318 is not free (smoke mode never shows a dialog)".to_string()),
    };
    let Some(port) = record(&mut steps, "sync", t, port_check) else {
        return failed(steps, &version);
    };

    let log_path =
        std::env::temp_dir().join(format!("persona-forge-smoke-{}.log", std::process::id()));
    let spec = supervisor::ServerSpec {
        python,
        host: "127.0.0.1".to_string(),
        port,
        extra_env: vec![("PERSONA_FORGE_SHELL".to_string(), "desktop".to_string())],
        log_path,
    };
    let t = Instant::now();
    let Some(mut handle) = record(
        &mut steps,
        "start",
        t,
        supervisor::ServerHandle::spawn(&spec),
    ) else {
        return failed(steps, &version);
    };

    let t = Instant::now();
    let ready: Result<(), String> =
        supervisor::wait_ready(&mut handle, port, Duration::from_secs(180)).map_err(|e| match e {
            supervisor::ReadyError::Exited(code) => {
                format!("server exited before becoming ready (code {code:?})")
            }
            supervisor::ReadyError::Timeout => "timed out waiting for /health".to_string(),
        });
    if record(&mut steps, "wait", t, ready).is_none() {
        let _ = handle.stop(Duration::from_secs(10));
        return failed(steps, &version);
    }

    let t = Instant::now();
    let _ = handle.stop(Duration::from_secs(10));
    let port_freed = matches!(probe(port), health::PortState::Free);
    let stop_result: Result<(), String> = if port_freed {
        Ok(())
    } else {
        Err("port did not free after stop".to_string())
    };
    let ok = record(&mut steps, "stop", t, stop_result).is_some();

    SmokeResult {
        ok,
        version,
        port,
        steps,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn serializes_with_the_documented_field_names() {
        let result = SmokeResult {
            ok: true,
            version: "2.1.4".to_string(),
            port: 8318,
            steps: vec![StepResult {
                name: "verify",
                ok: true,
                ms: 3,
                detail: None,
            }],
        };
        let value: serde_json::Value = serde_json::to_value(&result).unwrap();
        assert_eq!(value["ok"], true);
        assert_eq!(value["version"], "2.1.4");
        assert_eq!(value["port"], 8318);
        assert_eq!(value["steps"][0]["name"], "verify");
        assert_eq!(value["steps"][0]["ok"], true);
        assert_eq!(value["steps"][0]["ms"], 3);
        assert!(value["steps"][0]["detail"].is_null());
    }
}
