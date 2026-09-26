//! Version directory retention (contract D14, `docs/plans/20260925-native_app_shell_auto_update.md`
//! Phase 2). After a successful `ensure_env` promote, delete every stale `versions/<name>` entry
//! that is not the version just promoted, not the immediately previous version, not currently in
//! use by a live process, and not a semver-greater version than the one just promoted (D14: a
//! dual CLI-archive + desktop install share one `versions/` directory, and a stale older CLI
//! archive must never delete a newer desktop env).

use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use semver::Version;

/// Abstracts "is this directory currently in use by a live process" so retention is
/// unit-testable without spawning real processes.
pub trait InUse {
    fn is_in_use(&self, dir: &Path) -> bool;
}

/// Real `InUse`: true if any live process's executable path is under `dir`.
pub struct SysinfoInUse;

impl InUse for SysinfoInUse {
    fn is_in_use(&self, dir: &Path) -> bool {
        use sysinfo::{ProcessRefreshKind, RefreshKind, System};

        let dir = match fs::canonicalize(dir) {
            Ok(d) => d,
            // A directory that doesn't exist can't be in use.
            Err(_) => return false,
        };
        let system = System::new_with_specifics(
            RefreshKind::nothing().with_processes(ProcessRefreshKind::everything()),
        );
        system.processes().values().any(|process| {
            process
                .exe()
                .and_then(|exe| fs::canonicalize(exe).ok())
                .is_some_and(|exe| exe.starts_with(&dir))
        })
    }
}

/// Delete every direct child of `versions_dir` whose name is not `keep_current` or
/// `keep_previous` (including stale `*.staging` dirs left by an interrupted provision),
/// skipping any for which `in_use` returns true or whose version compares semver-greater than
/// `keep_current` (D14). Unparseable names are treated as older (never protected on that
/// basis). Ignores regular files. Never follows symlinks: a symlinked child is removed as a
/// link (`remove_file`/equivalent), never recursed into, so its target survives.
///
/// A missing `versions_dir` is not an error; it returns `Ok(vec![])`.
pub fn prune_versions(
    versions_dir: &Path,
    keep_current: &str,
    keep_previous: Option<&str>,
    in_use: &dyn InUse,
) -> io::Result<Vec<PathBuf>> {
    let entries = match fs::read_dir(versions_dir) {
        Ok(entries) => entries,
        Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(e) => return Err(e),
    };

    let current_version = Version::parse(strip_staging(keep_current)).ok();
    let mut deleted = Vec::new();

    for entry in entries {
        let entry = entry?;
        let file_type = entry.file_type()?;
        let name = entry.file_name();
        let name_str = name.to_string_lossy();
        let path = entry.path();

        if name_str == keep_current || Some(name_str.as_ref()) == keep_previous {
            continue;
        }
        if file_type.is_symlink() {
            fs::remove_file(&path)?;
            deleted.push(path);
            continue;
        }
        if !file_type.is_dir() {
            continue; // regular files are ignored
        }
        if let (Some(current), Some(candidate)) = (
            &current_version,
            Version::parse(strip_staging(&name_str)).ok(),
        ) {
            if candidate > *current {
                continue; // D14: never delete a version newer than the one just promoted
            }
        }
        if in_use.is_in_use(&path) {
            continue;
        }

        fs::remove_dir_all(&path)?;
        deleted.push(path);
    }

    Ok(deleted)
}

/// `<version>.staging` dirs carry a suffix that isn't part of the semver string.
fn strip_staging(name: &str) -> &str {
    name.strip_suffix(".staging").unwrap_or(name)
}

#[cfg(test)]
mod tests {
    use super::*;

    struct FakeInUse<'a>(&'a [&'a Path]);

    impl InUse for FakeInUse<'_> {
        fn is_in_use(&self, dir: &Path) -> bool {
            self.0.contains(&dir)
        }
    }

    struct NeverInUse;
    impl InUse for NeverInUse {
        fn is_in_use(&self, _dir: &Path) -> bool {
            false
        }
    }

    fn make_dir(root: &Path, name: &str) -> PathBuf {
        let p = root.join(name);
        fs::create_dir_all(&p).unwrap();
        p
    }

    #[test]
    fn keeps_current_and_previous_and_deletes_others() {
        let root = tempfile::tempdir().unwrap();
        make_dir(root.path(), "1.0.0");
        make_dir(root.path(), "1.1.0");
        make_dir(root.path(), "1.2.0");

        let deleted = prune_versions(root.path(), "1.2.0", Some("1.1.0"), &NeverInUse).unwrap();

        assert_eq!(deleted, vec![root.path().join("1.0.0")]);
        assert!(root.path().join("1.1.0").exists());
        assert!(root.path().join("1.2.0").exists());
        assert!(!root.path().join("1.0.0").exists());
    }

    #[test]
    fn deletes_stale_staging_dirs() {
        let root = tempfile::tempdir().unwrap();
        make_dir(root.path(), "1.2.0");
        make_dir(root.path(), "1.1.0.staging");

        let deleted = prune_versions(root.path(), "1.2.0", None, &NeverInUse).unwrap();

        assert_eq!(deleted, vec![root.path().join("1.1.0.staging")]);
    }

    #[test]
    fn ignores_regular_files() {
        let root = tempfile::tempdir().unwrap();
        make_dir(root.path(), "1.2.0");
        fs::write(root.path().join("README.txt"), b"not a version dir").unwrap();

        let deleted = prune_versions(root.path(), "1.2.0", None, &NeverInUse).unwrap();

        assert!(deleted.is_empty());
        assert!(root.path().join("README.txt").exists());
    }

    #[test]
    fn keep_previous_none_keeps_only_current() {
        let root = tempfile::tempdir().unwrap();
        make_dir(root.path(), "1.0.0");
        make_dir(root.path(), "1.1.0");
        make_dir(root.path(), "1.2.0");

        let mut deleted = prune_versions(root.path(), "1.2.0", None, &NeverInUse).unwrap();
        deleted.sort();

        assert_eq!(
            deleted,
            vec![root.path().join("1.0.0"), root.path().join("1.1.0")]
        );
    }

    #[test]
    fn a_missing_versions_dir_returns_empty() {
        let root = tempfile::tempdir().unwrap();
        let missing = root.path().join("does-not-exist");

        assert_eq!(
            prune_versions(&missing, "1.2.0", None, &NeverInUse).unwrap(),
            Vec::<PathBuf>::new()
        );
    }

    #[test]
    fn a_dir_the_fake_reports_in_use_is_kept() {
        let root = tempfile::tempdir().unwrap();
        make_dir(root.path(), "1.0.0");
        make_dir(root.path(), "1.2.0");
        let protected = root.path().join("1.0.0");

        let deleted =
            prune_versions(root.path(), "1.2.0", None, &FakeInUse(&[&protected])).unwrap();

        assert!(deleted.is_empty());
        assert!(protected.exists());
    }

    #[test]
    fn a_version_semver_greater_than_current_is_kept_even_when_idle() {
        // Dual CLI-archive + desktop installs share one versions/ dir; a stale older CLI
        // archive run must never delete a newer version a desktop install already promoted.
        let root = tempfile::tempdir().unwrap();
        make_dir(root.path(), "1.2.0");
        make_dir(root.path(), "1.3.0");

        let deleted = prune_versions(root.path(), "1.2.0", None, &NeverInUse).unwrap();

        assert!(deleted.is_empty());
        assert!(root.path().join("1.3.0").exists());
    }

    #[cfg(unix)]
    #[test]
    fn a_symlink_child_is_unlinked_and_its_target_survives() {
        use std::os::unix::fs::symlink;

        let root = tempfile::tempdir().unwrap();
        make_dir(root.path(), "1.2.0");
        let target = tempfile::tempdir().unwrap();
        fs::write(target.path().join("marker"), b"still here").unwrap();
        let link = root.path().join("1.0.0");
        symlink(target.path(), &link).unwrap();

        let deleted = prune_versions(root.path(), "1.2.0", None, &NeverInUse).unwrap();

        assert_eq!(deleted, vec![link.clone()]);
        assert!(!link.exists());
        assert!(target.path().join("marker").exists());
    }

    #[cfg(unix)]
    #[test]
    fn sysinfo_in_use_detects_a_real_running_process() {
        let root = tempfile::tempdir().unwrap();
        let old_bin_dir = root.path().join("old").join("bin");
        fs::create_dir_all(&old_bin_dir).unwrap();
        let sleep_copy = old_bin_dir.join("sleep");
        fs::copy("/bin/sleep", &sleep_copy).unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut perms = fs::metadata(&sleep_copy).unwrap().permissions();
            perms.set_mode(0o755);
            fs::set_permissions(&sleep_copy, perms).unwrap();
        }

        // Linux errors with "Text file busy" (ETXTBSY) if we exec the freshly-copied ELF before
        // the copy is fully flushed; retry briefly, which is the canonical workaround.
        let mut child: Option<std::process::Child> = None;
        for _ in 0..10 {
            if let Ok(c) = std::process::Command::new(&sleep_copy).arg("5").spawn() {
                child = Some(c);
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(50));
        }
        let Some(mut child) = child else {
            panic!("could not spawn the copied sleep binary")
        };

        assert!(SysinfoInUse.is_in_use(&root.path().join("old")));

        child.kill().unwrap();
        child.wait().unwrap();

        // Give the OS a moment to actually reap/remove the process from the table.
        std::thread::sleep(std::time::Duration::from_millis(200));
        assert!(!SysinfoInUse.is_in_use(&root.path().join("old")));
    }

    #[cfg(windows)]
    #[test]
    fn sysinfo_in_use_detects_a_real_running_process() {
        let root = tempfile::tempdir().unwrap();
        let old_bin_dir = root.path().join("old").join("bin");
        fs::create_dir_all(&old_bin_dir).unwrap();
        let ping_copy = old_bin_dir.join("ping.exe");
        fs::copy("C:\\Windows\\System32\\ping.exe", &ping_copy).unwrap();

        let mut child = std::process::Command::new(&ping_copy)
            .args(["-n", "20", "127.0.0.1"])
            .spawn()
            .unwrap();

        assert!(SysinfoInUse.is_in_use(&root.path().join("old")));

        child.kill().unwrap();
        child.wait().unwrap();

        std::thread::sleep(std::time::Duration::from_millis(200));
        assert!(!SysinfoInUse.is_in_use(&root.path().join("old")));
    }
}
