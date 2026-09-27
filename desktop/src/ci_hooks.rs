#[cfg(not(target_os = "macos"))]
use std::path::Path;
#[cfg(not(target_os = "macos"))]
use std::path::PathBuf;
#[cfg(not(target_os = "macos"))]
use std::process::ExitCode;
#[cfg(not(target_os = "macos"))]
use std::sync::{Arc, Mutex};

#[cfg(any(not(target_os = "macos"), test))]
use serde::Serialize;
#[cfg(not(target_os = "macos"))]
use tauri::{AppHandle, Runtime};

#[cfg(any(not(target_os = "macos"), test))]
#[derive(Clone, Debug, Serialize)]
struct CiUpdateReport {
    ok: bool,
    phase: String,
    from_version: String,
    to_version: Option<String>,
    error: Option<String>,
}

#[cfg(not(target_os = "macos"))]
fn write_report(path: &Path, report: &CiUpdateReport) -> std::io::Result<()> {
    let bytes = serde_json::to_vec(report).map_err(std::io::Error::other)?;
    std::fs::write(path, bytes)
}

#[cfg(not(target_os = "macos"))]
pub fn run<R: Runtime>(app: AppHandle<R>, out_path: PathBuf) -> ExitCode {
    use tauri_plugin_updater::UpdaterExt;

    let report = Arc::new(Mutex::new(CiUpdateReport {
        ok: false,
        phase: "check".to_string(),
        from_version: app.package_info().version.to_string(),
        to_version: None,
        error: None,
    }));
    let before_exit_report = Arc::clone(&report);
    let before_exit_path = out_path.clone();
    let before_exit_app = app.clone();
    let updater = app
        .updater_builder()
        .on_before_exit(move || {
            let snapshot = {
                let mut report = before_exit_report.lock().expect("CI report mutex poisoned");
                report.ok = true;
                report.phase = "installing".to_string();
                report.clone()
            };
            if let Err(error) = write_report(&before_exit_path, &snapshot) {
                eprintln!("persona-forge-desktop: failed to write update status: {error}");
            }
            before_exit_app.cleanup_before_exit();
        })
        .build();

    let result = tauri::async_runtime::block_on(async {
        let update = match updater.check().await {
            Ok(Some(update)) => update,
            Ok(None) => return Err(("check", "no update available".to_string())),
            Err(error) => return Err(("check", error.to_string())),
        };
        report.lock().expect("CI report mutex poisoned").to_version = Some(update.version.clone());

        let bytes = match update.download(&mut |_chunk, _total| {}, &mut || {}).await {
            Ok(bytes) => bytes,
            Err(error) => {
                use tauri_plugin_updater::Error;
                let phase = if matches!(
                    error,
                    Error::Minisign(_) | Error::Base64(_) | Error::SignatureUtf8(_)
                ) {
                    "verify"
                } else {
                    "download"
                };
                return Err((phase, error.to_string()));
            }
        };

        update
            .install(bytes.as_slice())
            .map_err(|error| ("install", error.to_string()))
    });

    let mut final_report = report.lock().expect("CI report mutex poisoned").clone();
    match result {
        Ok(()) => {
            final_report.ok = true;
            final_report.phase = "installed".to_string();
            app.cleanup_before_exit();
        }
        Err((phase, error)) => {
            final_report.ok = false;
            final_report.phase = phase.to_string();
            final_report.error = Some(error);
        }
    }

    if let Err(error) = write_report(&out_path, &final_report) {
        eprintln!("persona-forge-desktop: failed to write update status: {error}");
        return ExitCode::FAILURE;
    }

    if final_report.ok {
        ExitCode::SUCCESS
    } else {
        ExitCode::FAILURE
    }
}

#[cfg(test)]
mod tests {
    use super::CiUpdateReport;

    #[test]
    fn report_serializes_all_contract_fields_including_nulls() {
        let report = CiUpdateReport {
            ok: false,
            phase: "verify".to_string(),
            from_version: "2.1.4".to_string(),
            to_version: Some("2.1.5".to_string()),
            error: Some("invalid signature".to_string()),
        };

        let value = serde_json::to_value(report).unwrap();
        assert_eq!(value["ok"], false);
        assert_eq!(value["phase"], "verify");
        assert_eq!(value["from_version"], "2.1.4");
        assert_eq!(value["to_version"], "2.1.5");
        assert_eq!(value["error"], "invalid signature");

        let no_update = CiUpdateReport {
            ok: false,
            phase: "check".to_string(),
            from_version: "2.1.4".to_string(),
            to_version: None,
            error: None,
        };
        let value = serde_json::to_value(no_update).unwrap();
        assert!(value.get("to_version").is_some());
        assert!(value.get("error").is_some());
    }
}
