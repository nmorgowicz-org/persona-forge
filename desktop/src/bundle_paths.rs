//! Finding the payload without Tauri (contract §6.8). Used by both `--smoke-test` (which runs
//! before any Tauri/webview initialization) and the GUI bootstrap path, so both resolve the
//! bundle the same way.

use std::path::PathBuf;
#[cfg(debug_assertions)]
use std::path::Path;
use tauri::utils::platform::{current_exe, resource_dir};
use tauri::utils::Env;
use tauri::PackageInfo;

/// `(payload_dir, uv_path)`. `payload_dir` is `<resource_dir>/payload`. `uv_path` is
/// `uv`/`uv.exe` next to the current executable (the bundler strips the externalBin
/// target-triple suffix at bundle time, contract §6.8).
pub fn bundle_paths(package_info: &PackageInfo) -> tauri::utils::Result<(PathBuf, PathBuf)> {
    let resources = resource_dir(package_info, &Env::default())?;
    let payload_dir = resources.join("payload");

    let exe = current_exe()?;
    let exe_dir = exe
        .parent()
        .expect("current_exe has a parent directory")
        .to_path_buf();
    let uv_name = if cfg!(target_os = "windows") {
        "uv.exe"
    } else {
        "uv"
    };
    let uv_path = exe_dir.join(uv_name);

    Ok((payload_dir, uv_path))
}

/// Debug-build sanity check: `bundle_paths`' resource dir must agree with
/// `app.path().resource_dir()` (contract §6.8, task 4). Kept separate from `bundle_paths` so
/// `--smoke-test` (which has no `AppHandle`) never needs it.
#[cfg(debug_assertions)]
pub fn assert_matches_app_resource_dir(bundle_payload_dir: &Path, app_resource_dir: &Path) {
    let expected = app_resource_dir.join("payload");
    assert_eq!(
        bundle_payload_dir, expected,
        "bundle_paths() payload dir must match app.path().resource_dir()/payload"
    );
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn uv_name_is_platform_correct() {
        let name = if cfg!(target_os = "windows") {
            "uv.exe"
        } else {
            "uv"
        };
        assert!(name == "uv" || name == "uv.exe");
    }

    #[cfg(debug_assertions)]
    #[test]
    fn assert_matches_app_resource_dir_agrees_when_dirs_match() {
        let dir = Path::new("/tmp/pf-resources");
        assert_matches_app_resource_dir(&dir.join("payload"), dir);
    }

    #[cfg(debug_assertions)]
    #[test]
    #[should_panic]
    fn assert_matches_app_resource_dir_panics_when_dirs_disagree() {
        assert_matches_app_resource_dir(Path::new("/tmp/a/payload"), Path::new("/tmp/b"));
    }
}
