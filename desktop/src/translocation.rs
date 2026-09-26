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

    let accepted = ask_move_to_applications(app);
    if !accepted {
        return true; // continue running, but disable update checks for the session
    }

    match perform_move_and_relaunch(&exe) {
        Ok(()) => {
            app.exit(0);
            true // unreachable in practice; exit() above ends the process
        }
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
    let path_str = exe.to_string_lossy();
    if path_str.contains("/private/var/folders/") {
        return true;
    }
    // A read-only volume: the exe's directory can't be written to (e.g. mounted from a DMG the
    // user launched without copying to Applications first).
    if let Some(dir) = exe.parent() {
        let probe = dir.join(".persona-forge-write-probe");
        let writable = std::fs::write(&probe, b"").is_ok();
        let _ = std::fs::remove_file(&probe);
        if !writable {
            return true;
        }
    }
    false
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

/// Finds the `.app` bundle root above `exe` (`.../Persona Forge.app/Contents/MacOS/<exe>`),
/// copies it to `/Applications` (or `~/Applications` if that isn't writable), removes
/// quarantine only from the copy this app makes, then relaunches the copy and exits.
#[cfg(target_os = "macos")]
fn perform_move_and_relaunch(exe: &std::path::Path) -> std::io::Result<()> {
    let bundle = bundle_root(exe)
        .ok_or_else(|| std::io::Error::other("could not locate .app bundle root"))?;
    let bundle_name = bundle
        .file_name()
        .ok_or_else(|| std::io::Error::other("bundle has no file name"))?;

    let applications = std::path::Path::new("/Applications");
    let target_root = if is_writable_dir(applications) {
        applications.to_path_buf()
    } else {
        dirs_home().join("Applications")
    };
    std::fs::create_dir_all(&target_root)?;
    let target = target_root.join(bundle_name);

    if target.exists() {
        std::fs::remove_dir_all(&target)?;
    }
    copy_dir_recursive(&bundle, &target)?;
    remove_quarantine(&target);

    let new_exe = target
        .join("Contents")
        .join("MacOS")
        .join(exe.file_name().unwrap());
    std::process::Command::new(&new_exe).spawn()?;
    Ok(())
}

#[cfg(target_os = "macos")]
fn bundle_root(exe: &std::path::Path) -> Option<std::path::PathBuf> {
    // <bundle>.app/Contents/MacOS/<exe>
    exe.parent()?.parent()?.parent().map(|p| p.to_path_buf())
}

#[cfg(target_os = "macos")]
fn is_writable_dir(dir: &std::path::Path) -> bool {
    let probe = dir.join(".persona-forge-write-probe");
    let writable = std::fs::write(&probe, b"").is_ok();
    let _ = std::fs::remove_file(&probe);
    writable
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
    let status = std::process::Command::new("ditto")
        .arg(from)
        .arg(to)
        .status()?;
    if !status.success() {
        return Err(std::io::Error::other("ditto failed to copy the app bundle"));
    }
    Ok(())
}

#[cfg(target_os = "macos")]
fn remove_quarantine(bundle: &std::path::Path) {
    let _ = std::process::Command::new("xattr")
        .args(["-dr", "com.apple.quarantine"])
        .arg(bundle)
        .status();
}
