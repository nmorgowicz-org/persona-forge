//! Download destination naming (contract §6.5, D21). `unique_path` is a pure function; the
//! `on_download` wiring (never blocking, per Phase 1's deadlock finding) lives in `app.rs`.

use std::collections::HashSet;
use std::path::{Path, PathBuf};

/// `dir/name` if free, else `dir/<stem> (1).<ext>`, `dir/<stem> (2).<ext>`, ...: skipping names
/// that already exist on disk **or** are reserved by another in-flight download.
pub fn unique_path(dir: &Path, name: &str, reserved: &[PathBuf]) -> PathBuf {
    let reserved: HashSet<&Path> = reserved.iter().map(PathBuf::as_path).collect();
    let candidate = dir.join(name);
    if !candidate.exists() && !reserved.contains(candidate.as_path()) {
        return candidate;
    }

    let path = Path::new(name);
    let stem = path.file_stem().and_then(|s| s.to_str()).unwrap_or(name);
    let ext = path.extension().and_then(|e| e.to_str());

    for n in 1u32.. {
        let numbered = match ext {
            Some(ext) => format!("{stem} ({n}).{ext}"),
            None => format!("{stem} ({n})"),
        };
        let candidate = dir.join(&numbered);
        if !candidate.exists() && !reserved.contains(candidate.as_path()) {
            return candidate;
        }
    }
    unreachable!("u32 exhausted before finding a free name")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_free_name_is_kept() {
        let dir = tempfile::tempdir().unwrap();
        assert_eq!(
            unique_path(dir.path(), "tone.wav", &[]),
            dir.path().join("tone.wav")
        );
    }

    #[test]
    fn an_existing_file_gets_1() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("tone.wav"), b"").unwrap();
        assert_eq!(
            unique_path(dir.path(), "tone.wav", &[]),
            dir.path().join("tone (1).wav")
        );
    }

    #[test]
    fn a_name_reserved_by_an_in_flight_download_is_skipped() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("tone.wav"), b"").unwrap();
        let reserved = vec![dir.path().join("tone (1).wav")];
        assert_eq!(
            unique_path(dir.path(), "tone.wav", &reserved),
            dir.path().join("tone (2).wav")
        );
    }

    #[test]
    fn a_name_without_an_extension() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("README"), b"").unwrap();
        assert_eq!(
            unique_path(dir.path(), "README", &[]),
            dir.path().join("README (1)")
        );
    }
}
