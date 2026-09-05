//! Provision (or reuse) a versioned app-managed Python environment from a verified bundle
//! (docs/plans/20260829-no_more_docker_requirement.md Phase 7, "Launcher behavior" items 2-4, 7).
//!
//! Provisioning always happens in a `.staging` sibling directory and is only promoted to the
//! versioned env dir on full success (`fs::rename`, atomic on the same filesystem). A failed
//! update never touches an existing versioned env dir or the `current.txt` marker, so the
//! previous environment stays launchable (item 7).

use crate::manifest::Manifest;
use std::fmt;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

/// Abstracts process execution so bootstrap logic is unit-testable without a real `uv` binary.
pub trait Runner {
    fn run(&self, program: &Path, args: &[&str]) -> io::Result<i32>;
}

pub struct SystemRunner;

impl Runner for SystemRunner {
    fn run(&self, program: &Path, args: &[&str]) -> io::Result<i32> {
        let status = std::process::Command::new(program).args(args).status()?;
        Ok(status.code().unwrap_or(-1))
    }
}

#[derive(Debug)]
pub enum BootstrapError {
    Io(String, io::Error),
    CommandFailed { step: String, code: i32 },
}

impl fmt::Display for BootstrapError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            BootstrapError::Io(ctx, e) => write!(f, "{ctx}: {e}"),
            BootstrapError::CommandFailed { step, code } => {
                write!(f, "{step} exited with status {code}")
            }
        }
    }
}

impl std::error::Error for BootstrapError {}

fn io_err(ctx: &str, e: io::Error) -> BootstrapError {
    BootstrapError::Io(ctx.to_string(), e)
}

pub fn venv_python(venv_dir: &Path) -> PathBuf {
    let posix = venv_dir.join("bin").join("python");
    if posix.exists() {
        return posix;
    }
    venv_dir.join("Scripts").join("python.exe")
}

fn ready_marker(env_dir: &Path) -> PathBuf {
    env_dir.join(".ready")
}

/// Ensure a fully-provisioned venv exists for `manifest.version` under `versions_dir`, building
/// it if necessary, and return the venv directory. Never mutates `versions_dir/<version>` or
/// `current_marker` unless every provisioning step succeeds.
pub fn ensure_env(
    manifest: &Manifest,
    bundle_dir: &Path,
    uv_path: &Path,
    versions_dir: &Path,
    current_marker: &Path,
    runner: &dyn Runner,
) -> Result<PathBuf, BootstrapError> {
    // `env_dir` IS the venv root once provisioned (the staged venv is renamed directly onto
    // it below) - there is no extra "venv" nesting level.
    let env_dir = versions_dir.join(&manifest.version);
    let marker = ready_marker(&env_dir);

    if marker.is_file() {
        let recorded = fs::read_to_string(&marker).unwrap_or_default();
        if recorded.trim() == manifest.wheel.sha256 {
            return Ok(env_dir); // fast path: already provisioned for this exact wheel
        }
    }

    let staging_dir = versions_dir.join(format!("{}.staging", manifest.version));
    if staging_dir.exists() {
        fs::remove_dir_all(&staging_dir)
            .map_err(|e| io_err(&format!("cleaning stale staging dir {}", staging_dir.display()), e))?;
    }
    fs::create_dir_all(&staging_dir)
        .map_err(|e| io_err(&format!("creating staging dir {}", staging_dir.display()), e))?;

    if let Err(e) = provision(manifest, bundle_dir, uv_path, &staging_dir, runner) {
        let _ = fs::remove_dir_all(&staging_dir); // best-effort cleanup; the error already explains why
        return Err(e);
    }

    fs::create_dir_all(versions_dir)
        .map_err(|e| io_err(&format!("creating versions dir {}", versions_dir.display()), e))?;
    if env_dir.exists() {
        fs::remove_dir_all(&env_dir)
            .map_err(|e| io_err(&format!("replacing previous env dir {}", env_dir.display()), e))?;
    }
    fs::rename(staging_dir.join("venv"), &env_dir)
        .map_err(|e| io_err(&format!("promoting staged env to {}", env_dir.display()), e))?;
    let _ = fs::remove_dir_all(versions_dir.join(format!("{}.staging", manifest.version)));

    fs::write(ready_marker(&env_dir), &manifest.wheel.sha256)
        .map_err(|e| io_err("writing ready marker", e))?;

    write_atomically(current_marker, &manifest.version)?;

    Ok(env_dir)
}

fn provision(
    manifest: &Manifest,
    bundle_dir: &Path,
    uv_path: &Path,
    staging_dir: &Path,
    runner: &dyn Runner,
) -> Result<(), BootstrapError> {
    let venv_dir = staging_dir.join("venv");
    let venv_dir_str = venv_dir.to_string_lossy().into_owned();

    let code = runner
        .run(uv_path, &["venv", &venv_dir_str, "--python", "3.13"])
        .map_err(|e| io_err("spawning uv venv", e))?;
    if code != 0 {
        return Err(BootstrapError::CommandFailed { step: "uv venv".to_string(), code });
    }

    let python = venv_python(&venv_dir);
    let python_str = python.to_string_lossy().into_owned();
    let requirements_path = bundle_dir.join(&manifest.requirements_file);
    let requirements_str = requirements_path.to_string_lossy().into_owned();

    let code = runner
        .run(uv_path, &["pip", "sync", "--python", &python_str, &requirements_str])
        .map_err(|e| io_err("spawning uv pip sync", e))?;
    if code != 0 {
        return Err(BootstrapError::CommandFailed { step: "uv pip sync".to_string(), code });
    }

    let wheel_path = bundle_dir.join(&manifest.wheel.file);
    let wheel_str = wheel_path.to_string_lossy().into_owned();
    let code = runner
        .run(uv_path, &["pip", "install", "--no-deps", "--python", &python_str, &wheel_str])
        .map_err(|e| io_err("spawning uv pip install", e))?;
    if code != 0 {
        return Err(BootstrapError::CommandFailed { step: "uv pip install --no-deps".to_string(), code });
    }

    Ok(())
}

fn write_atomically(path: &Path, contents: &str) -> Result<(), BootstrapError> {
    let tmp = path.with_extension("tmp");
    fs::write(&tmp, contents).map_err(|e| io_err(&format!("writing {}", tmp.display()), e))?;
    fs::rename(&tmp, path).map_err(|e| io_err(&format!("renaming {} to {}", tmp.display(), path.display()), e))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::manifest::{Manifest, UvEntry, WheelEntry};
    use std::cell::RefCell;

    fn manifest(version: &str, wheel_sha: &str) -> Manifest {
        Manifest {
            schema_version: 1,
            app: "persona-forge".to_string(),
            version: version.to_string(),
            target: "x86_64-unknown-linux-gnu".to_string(),
            python_constraint: "==3.13.*".to_string(),
            wheel: WheelEntry { file: "app.whl".to_string(), sha256: wheel_sha.to_string() },
            uv: UvEntry { file: "uv".to_string(), sha256: "uvsha".to_string(), version: "0.12.9".to_string() },
            requirements_file: "reqs.txt".to_string(),
            requirements_sha256: "reqsha".to_string(),
        }
    }

    struct FakeRunner {
        calls: RefCell<Vec<Vec<String>>>,
        fail_step: Option<&'static str>,
    }

    impl FakeRunner {
        fn new(fail_step: Option<&'static str>) -> Self {
            Self { calls: RefCell::new(Vec::new()), fail_step }
        }
    }

    impl Runner for FakeRunner {
        fn run(&self, program: &Path, args: &[&str]) -> io::Result<i32> {
            self.calls
                .borrow_mut()
                .push(std::iter::once(program.display().to_string()).chain(args.iter().map(|s| s.to_string())).collect());

            if args.first() == Some(&"venv") {
                let venv_dir = PathBuf::from(args[1]);
                fs::create_dir_all(venv_dir.join("bin")).unwrap();
                fs::write(venv_dir.join("bin").join("python"), b"").unwrap();
                if self.fail_step == Some("venv") {
                    return Ok(1);
                }
                return Ok(0);
            }
            if args.first() == Some(&"pip") && args.get(1) == Some(&"sync") {
                if self.fail_step == Some("sync") {
                    return Ok(1);
                }
                return Ok(0);
            }
            if args.first() == Some(&"pip") && args.get(1) == Some(&"install") {
                if self.fail_step == Some("install") {
                    return Ok(1);
                }
                // simulate the wheel installing the console script
                let python_idx = args.iter().position(|a| *a == "--python").unwrap();
                let python_path = PathBuf::from(args[python_idx + 1]);
                let bin_dir = python_path.parent().unwrap();
                fs::write(bin_dir.join("persona-forge"), b"").unwrap();
                return Ok(0);
            }
            Ok(0)
        }
    }

    #[test]
    fn provisions_a_fresh_env_and_marks_it_current() {
        let root = tempfile::tempdir().unwrap();
        let bundle_dir = root.path().join("bundle");
        fs::create_dir_all(&bundle_dir).unwrap();
        let versions_dir = root.path().join("versions");
        let current_marker = root.path().join("current.txt");
        let uv_path = bundle_dir.join("uv");
        let m = manifest("1.3.0", "wheelsha");
        let runner = FakeRunner::new(None);

        let env_dir = ensure_env(&m, &bundle_dir, &uv_path, &versions_dir, &current_marker, &runner).unwrap();

        assert!(venv_python(&env_dir).exists());
        assert_eq!(fs::read_to_string(&current_marker).unwrap(), "1.3.0");
        assert!(ready_marker(&env_dir).is_file());
        assert_eq!(fs::read_to_string(ready_marker(&env_dir)).unwrap(), "wheelsha");
    }

    #[test]
    fn reuses_an_already_provisioned_env_without_calling_uv_again() {
        let root = tempfile::tempdir().unwrap();
        let bundle_dir = root.path().join("bundle");
        fs::create_dir_all(&bundle_dir).unwrap();
        let versions_dir = root.path().join("versions");
        let current_marker = root.path().join("current.txt");
        let uv_path = bundle_dir.join("uv");
        let m = manifest("1.3.0", "wheelsha");

        let first_runner = FakeRunner::new(None);
        ensure_env(&m, &bundle_dir, &uv_path, &versions_dir, &current_marker, &first_runner).unwrap();

        let second_runner = FakeRunner::new(None);
        ensure_env(&m, &bundle_dir, &uv_path, &versions_dir, &current_marker, &second_runner).unwrap();

        assert!(second_runner.calls.borrow().is_empty(), "fast path must not invoke uv again");
    }

    #[test]
    fn a_failed_update_leaves_the_previous_env_launchable() {
        let root = tempfile::tempdir().unwrap();
        let bundle_dir = root.path().join("bundle");
        fs::create_dir_all(&bundle_dir).unwrap();
        let versions_dir = root.path().join("versions");
        let current_marker = root.path().join("current.txt");
        let uv_path = bundle_dir.join("uv");

        let old = manifest("1.2.0", "oldsha");
        let good_runner = FakeRunner::new(None);
        let old_env = ensure_env(&old, &bundle_dir, &uv_path, &versions_dir, &current_marker, &good_runner).unwrap();
        assert!(venv_python(&old_env).exists());

        let new = manifest("1.3.0", "newsha");
        let bad_runner = FakeRunner::new(Some("install"));
        let err = ensure_env(&new, &bundle_dir, &uv_path, &versions_dir, &current_marker, &bad_runner);
        assert!(err.is_err());

        // current.txt still points at the old, working version.
        assert_eq!(fs::read_to_string(&current_marker).unwrap(), "1.2.0");
        assert!(!versions_dir.join("1.3.0").exists());
        assert!(!versions_dir.join("1.3.0.staging").exists());
        assert!(versions_dir.join("1.2.0").exists());
    }

    #[test]
    fn venv_python_finds_windows_layout() {
        let dir = tempfile::tempdir().unwrap();
        fs::create_dir_all(dir.path().join("Scripts")).unwrap();
        fs::write(dir.path().join("Scripts").join("python.exe"), b"").unwrap();
        assert_eq!(venv_python(dir.path()), dir.path().join("Scripts").join("python.exe"));
    }
}
