//! macOS App Translocation (contract §6.9). Only meaningful on macOS: elsewhere `check_and_handle`
//! is a no-op that always returns `false` (updates never disabled).
//!
//! No crate dependency: `Do not add a crate unless Phase 1 finds a maintained one` (contract).
//! Phase 1's spike never needed this, so it's implemented directly.

use tauri::{AppHandle, Runtime};

/// Returns `true` if update checks should be disabled for this session (the user declined the
/// move, or the app relaunched after copying itself and this call should be a no-op there too).
#[cfg(target_os = "macos")]
pub fn check_and_handle<R: Runtime>(app: &AppHandle<R>) -> bool {
    let Ok(exe) = std::env::current_exe() else {
        return false;
    };
    if !is_translocated_or_read_only(&exe) {
        return false;
    }

    if !ask_move_to_applications(app) {
        return true;
    }

    match perform_move_and_relaunch(app, &exe) {
        Ok(true) => {
            app.exit(0);
            true
        }
        Ok(false) => true,
        Err(e) => {
            log::warn!("failed to move Persona Forge to Applications: {e}");
            true
        }
    }
}

#[cfg(not(target_os = "macos"))]
pub fn check_and_handle<R: Runtime>(_app: &AppHandle<R>) -> bool {
    false
}

#[cfg(target_os = "macos")]
fn is_translocated_or_read_only(exe: &std::path::Path) -> bool {
    if is_translocated_path(exe) {
        return true;
    }
    use std::os::unix::ffi::OsStrExt;
    let Ok(path) = std::ffi::CString::new(exe.as_os_str().as_bytes()) else {
        return false;
    };
    // SAFETY: `path` is NUL-terminated and `stat` is zero-initialized storage.
    unsafe {
        let mut stat: libc::statfs = std::mem::zeroed();
        libc::statfs(path.as_ptr(), &mut stat) == 0 && mount_is_read_only(stat.f_flags)
    }
}

#[cfg(target_os = "macos")]
fn is_translocated_path(exe: &std::path::Path) -> bool {
    let path = exe.to_string_lossy();
    path.starts_with("/private/var/folders/") && path.contains("/AppTranslocation/")
}

#[cfg(target_os = "macos")]
fn mount_is_read_only(flags: u32) -> bool {
    flags & libc::MNT_RDONLY as u32 != 0
}

#[cfg(target_os = "macos")]
fn ask_move_to_applications<R: Runtime>(app: &AppHandle<R>) -> bool {
    use tauri_plugin_dialog::{DialogExt, MessageDialogButtons};
    app.dialog()
        .message("Persona Forge is running from a temporary location. Move it to Applications for the best experience (required for automatic updates)?")
        .title("Move Persona Forge to Applications?")
        .buttons(MessageDialogButtons::OkCancelCustom("Move to Applications".into(), "Not Now".into()))
        .blocking_show()
}

/// Copies the `.app` bundle with `ditto`, clears quarantine only on the copy, launches it with
/// `open -n`, and exits. Refusing to replace an existing app keeps the current app running.
#[cfg(target_os = "macos")]
fn perform_move_and_relaunch<R: Runtime>(
    app: &AppHandle<R>,
    exe: &std::path::Path,
) -> std::io::Result<bool> {
    let bundle = bundle_root(exe)
        .ok_or_else(|| std::io::Error::other("could not locate .app bundle root"))?;
    let bundle_name = bundle
        .file_name()
        .ok_or_else(|| std::io::Error::other("bundle has no file name"))?;
    let applications = std::path::Path::new("/Applications");
    let target = applications.join(bundle_name);

    let target = match copy_to_target(&bundle, &target, app)? {
        CopyResult::Copied => target,
        CopyResult::Declined => return Ok(false),
        CopyResult::AccessDenied => {
            let target = dirs_home().join("Applications").join(bundle_name);
            match copy_to_target(&bundle, &target, app)? {
                CopyResult::Copied => target,
                CopyResult::Declined => return Ok(false),
                CopyResult::AccessDenied => {
                    return Err(std::io::Error::new(
                        std::io::ErrorKind::PermissionDenied,
                        "permission denied copying app to /Applications and ~/Applications",
                    ));
                }
            }
        }
    };

    remove_quarantine(&target);
    let status = std::process::Command::new("open")
        .arg("-n")
        .arg(&target)
        .status()?;
    if !status.success() {
        return Err(std::io::Error::other(
            "open failed to launch the copied app",
        ));
    }
    Ok(true)
}

#[cfg(target_os = "macos")]
enum CopyResult {
    Copied,
    Declined,
    AccessDenied,
}

#[cfg(target_os = "macos")]
fn copy_to_target<R: Runtime>(
    bundle: &std::path::Path,
    target: &std::path::Path,
    app: &AppHandle<R>,
) -> std::io::Result<CopyResult> {
    if target.exists() {
        use tauri_plugin_dialog::{DialogExt, MessageDialogButtons};
        let replace = app
            .dialog()
            .message("Persona Forge already exists in Applications. Replace it?")
            .title("Replace existing Persona Forge?")
            .buttons(MessageDialogButtons::OkCancelCustom(
                "Replace".into(),
                "Not Now".into(),
            ))
            .blocking_show();
        if !replace {
            return Ok(CopyResult::Declined);
        }
        if let Err(error) = std::fs::remove_dir_all(target) {
            if error.kind() == std::io::ErrorKind::PermissionDenied {
                return Ok(CopyResult::AccessDenied);
            }
            return Err(error);
        }
    }
    if let Some(parent) = target.parent() {
        if let Err(error) = std::fs::create_dir_all(parent) {
            if error.kind() == std::io::ErrorKind::PermissionDenied {
                return Ok(CopyResult::AccessDenied);
            }
            return Err(error);
        }
    }
    match copy_dir_recursive(bundle, target) {
        Ok(()) => Ok(CopyResult::Copied),
        Err(error) if error.kind() == std::io::ErrorKind::PermissionDenied => {
            let _ = std::fs::remove_dir_all(target);
            Ok(CopyResult::AccessDenied)
        }
        Err(error) => Err(error),
    }
}

#[cfg(target_os = "macos")]
fn bundle_root(exe: &std::path::Path) -> Option<std::path::PathBuf> {
    // <bundle>.app/Contents/MacOS/<exe>
    exe.parent()?.parent()?.parent().map(|p| p.to_path_buf())
}

#[cfg(target_os = "macos")]
fn dirs_home() -> std::path::PathBuf {
    std::env::var("HOME")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|_| std::path::PathBuf::from("/"))
}

#[cfg(target_os = "macos")]
fn copy_dir_recursive(from: &std::path::Path, to: &std::path::Path) -> std::io::Result<()> {
    // `ditto` preserves resource forks, symlinks and code-signature-relevant metadata that a
    // plain recursive file copy would silently corrupt (Phase 1 finding: signature stripping
    // via a naive copy/zip).
    let output = std::process::Command::new("ditto")
        .arg(from)
        .arg(to)
        .output()?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let kind = if stderr.to_ascii_lowercase().contains("permission denied") {
            std::io::ErrorKind::PermissionDenied
        } else {
            std::io::ErrorKind::Other
        };
        return Err(std::io::Error::new(
            kind,
            format!("ditto failed to copy the app bundle: {}", stderr.trim()),
        ));
    }
    Ok(())
}

#[cfg(target_os = "macos")]
fn remove_quarantine(bundle: &std::path::Path) {
    let status = std::process::Command::new("xattr")
        .args(["-dr", "com.apple.quarantine"])
        .arg(bundle)
        .status();
    if !matches!(status, Ok(status) if status.success()) {
        log::warn!(
            "could not remove quarantine from copied app at {}",
            bundle.display()
        );
    }
}
#[cfg(all(test, target_os = "macos"))]
mod tests {
    use super::*;

    #[test]
    fn detects_only_the_app_translocation_path_component() {
        assert!(is_translocated_path(std::path::Path::new(
            "/private/var/folders/ab/cd/AppTranslocation/123/d/Persona Forge.app/Contents/MacOS/persona-forge-desktop"
        )));
        assert!(!is_translocated_path(std::path::Path::new(
            "/private/var/folders/ab/cd/T/Persona Forge.app/Contents/MacOS/persona-forge-desktop"
        )));
        assert!(!is_translocated_path(std::path::Path::new(
            "/Applications/Persona Forge.app/Contents/MacOS/persona-forge-desktop"
        )));
    }

    #[test]
    fn detects_read_only_mount_flag() {
        assert!(mount_is_read_only(libc::MNT_RDONLY as u32));
        assert!(!mount_is_read_only(0));
    }
}
