//! Log rotation for `server.log` and `bootstrap.log` at startup (contract §6.2, §6.9): keep
//! `.1` and `.2`, cap each at 10 MB. `desktop.log` itself is rotated by `tauri-plugin-log`.

use std::fs;
use std::path::Path;

const MAX_BYTES: u64 = 10 * 1024 * 1024;

/// If `path` exists and is over `MAX_BYTES`, rotate it: `.2` is discarded, `.1` -> `.2`,
/// `path` -> `.1`. A fresh `path` is created by whatever writes to it next. Never fails the
/// caller: any I/O error here is logged and swallowed, since a startup log rotation must never
/// block the app from starting.
pub fn rotate_if_large(path: &Path) {
    if let Err(e) = try_rotate(path) {
        eprintln!(
            "persona-forge-desktop: log rotation failed for {}: {e}",
            path.display()
        );
    }
}

fn try_rotate(path: &Path) -> std::io::Result<()> {
    let Ok(meta) = fs::metadata(path) else {
        return Ok(());
    };
    if meta.len() <= MAX_BYTES {
        return Ok(());
    }
    let dot2 = path.with_file_name(append_ext(path, "2"));
    let dot1 = path.with_file_name(append_ext(path, "1"));
    let _ = fs::remove_file(&dot2);
    if dot1.exists() {
        fs::rename(&dot1, &dot2)?;
    }
    fs::rename(path, &dot1)?;
    Ok(())
}

/// `server.log` -> `server.log.1` (append, don't replace, the existing extension).
fn append_ext(path: &Path, suffix: &str) -> std::ffi::OsString {
    let mut name = path.file_name().unwrap_or_default().to_os_string();
    name.push(".");
    name.push(suffix);
    name
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_small_file_is_left_alone() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("server.log");
        fs::write(&path, b"small").unwrap();
        rotate_if_large(&path);
        assert!(path.exists());
        assert!(!dir.path().join("server.log.1").exists());
    }

    #[test]
    fn a_large_file_rotates_to_dot1() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("server.log");
        fs::write(&path, vec![0u8; (MAX_BYTES + 1) as usize]).unwrap();
        rotate_if_large(&path);
        assert!(!path.exists());
        assert!(dir.path().join("server.log.1").exists());
    }

    #[test]
    fn rotating_twice_pushes_dot1_to_dot2() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("server.log");
        fs::write(&path, vec![0u8; (MAX_BYTES + 1) as usize]).unwrap();
        rotate_if_large(&path);
        fs::write(&path, vec![1u8; (MAX_BYTES + 1) as usize]).unwrap();
        rotate_if_large(&path);

        assert!(!path.exists());
        assert!(dir.path().join("server.log.1").exists());
        assert!(dir.path().join("server.log.2").exists());
        assert_eq!(fs::read(dir.path().join("server.log.1")).unwrap()[0], 1);
        assert_eq!(fs::read(dir.path().join("server.log.2")).unwrap()[0], 0);
    }
}
