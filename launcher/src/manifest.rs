//! Bundle manifest: validated before the launcher touches the filesystem
//! (docs/plans/20260829-no_more_docker_requirement.md Phase 7, "Launcher behavior" item 1).

use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Deserialize)]
pub struct WheelEntry {
    pub file: String,
    pub sha256: String,
}

#[derive(Debug, Deserialize)]
pub struct UvEntry {
    pub file: String,
    pub sha256: String,
    #[allow(dead_code)] // part of the archive contract (build-time provenance); not read at runtime
    pub version: String,
}

#[derive(Debug, Deserialize)]
pub struct Manifest {
    pub schema_version: u32,
    pub app: String,
    pub version: String,
    #[allow(dead_code)] // part of the archive contract; validated by the build, not the launcher
    pub target: String,
    #[allow(dead_code)] // part of the archive contract; validated by the build, not the launcher
    pub python_constraint: String,
    pub wheel: WheelEntry,
    pub uv: UvEntry,
    pub requirements_file: String,
    pub requirements_sha256: String,
}

const SUPPORTED_SCHEMA_VERSION: u32 = 1;

#[derive(Debug)]
pub enum ManifestError {
    Io(String, std::io::Error),
    Parse(serde_json::Error),
    UnsupportedSchema(u32),
    WrongApp(String),
    MissingMember(String),
    HashMismatch { member: String, expected: String, actual: String },
}

impl fmt::Display for ManifestError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ManifestError::Io(path, e) => write!(f, "cannot read {path}: {e}"),
            ManifestError::Parse(e) => write!(f, "manifest.json is not valid: {e}"),
            ManifestError::UnsupportedSchema(v) => {
                write!(f, "manifest schema_version {v} is not supported (expected {SUPPORTED_SCHEMA_VERSION})")
            }
            ManifestError::WrongApp(app) => write!(f, "manifest is for app '{app}', not 'persona-forge'"),
            ManifestError::MissingMember(m) => write!(f, "bundle is missing required member: {m}"),
            ManifestError::HashMismatch { member, expected, actual } => write!(
                f,
                "sha256 mismatch for {member}: manifest says {expected}, computed {actual}"
            ),
        }
    }
}

impl std::error::Error for ManifestError {}

pub fn sha256_file(path: &Path) -> Result<String, std::io::Error> {
    let bytes = fs::read(path)?;
    let mut hasher = Sha256::new();
    hasher.update(&bytes);
    Ok(hex_encode(hasher.finalize().as_slice()))
}

fn hex_encode(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// Load `manifest.json` from `bundle_dir` and parse it. Does not touch any other file.
pub fn load(bundle_dir: &Path) -> Result<Manifest, ManifestError> {
    let path = bundle_dir.join("manifest.json");
    let text = fs::read_to_string(&path).map_err(|e| ManifestError::Io(path.display().to_string(), e))?;
    let manifest: Manifest = serde_json::from_str(&text).map_err(ManifestError::Parse)?;
    if manifest.schema_version != SUPPORTED_SCHEMA_VERSION {
        return Err(ManifestError::UnsupportedSchema(manifest.schema_version));
    }
    if manifest.app != "persona-forge" {
        return Err(ManifestError::WrongApp(manifest.app));
    }
    Ok(manifest)
}

/// Verify every member the manifest references exists in `bundle_dir` and matches its declared
/// SHA-256. Fail-closed: the first mismatch or missing file aborts before anything is mutated.
pub fn verify_bundle(manifest: &Manifest, bundle_dir: &Path) -> Result<(), ManifestError> {
    verify_member(bundle_dir, &manifest.wheel.file, &manifest.wheel.sha256)?;
    verify_member(bundle_dir, &manifest.uv.file, &manifest.uv.sha256)?;
    verify_member(bundle_dir, &manifest.requirements_file, &manifest.requirements_sha256)?;
    Ok(())
}

fn verify_member(bundle_dir: &Path, member: &str, expected_sha256: &str) -> Result<(), ManifestError> {
    let path: PathBuf = bundle_dir.join(member);
    if !path.is_file() {
        return Err(ManifestError::MissingMember(member.to_string()));
    }
    let actual = sha256_file(&path).map_err(|e| ManifestError::Io(path.display().to_string(), e))?;
    if !actual.eq_ignore_ascii_case(expected_sha256) {
        return Err(ManifestError::HashMismatch {
            member: member.to_string(),
            expected: expected_sha256.to_string(),
            actual,
        });
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    fn write_file(dir: &Path, name: &str, contents: &[u8]) -> PathBuf {
        let path = dir.join(name);
        let mut f = fs::File::create(&path).unwrap();
        f.write_all(contents).unwrap();
        path
    }

    fn sample_manifest_json(wheel_sha: &str, uv_sha: &str, req_sha: &str) -> String {
        format!(
            r#"{{
                "schema_version": 1,
                "app": "persona-forge",
                "version": "1.3.0",
                "target": "x86_64-unknown-linux-gnu",
                "python_constraint": "==3.13.*",
                "wheel": {{"file": "persona_forge-1.3.0-py3-none-any.whl", "sha256": "{wheel_sha}"}},
                "uv": {{"file": "uv", "sha256": "{uv_sha}", "version": "0.12.9"}},
                "requirements_file": "requirements-x86_64-unknown-linux-gnu.txt",
                "requirements_sha256": "{req_sha}"
            }}"#
        )
    }

    #[test]
    fn loads_and_verifies_a_clean_bundle() {
        let dir = tempfile::tempdir().unwrap();
        write_file(dir.path(), "persona_forge-1.3.0-py3-none-any.whl", b"wheel-bytes");
        write_file(dir.path(), "uv", b"uv-binary-bytes");
        write_file(dir.path(), "requirements-x86_64-unknown-linux-gnu.txt", b"foo==1.0\n");

        let wheel_sha = sha256_file(&dir.path().join("persona_forge-1.3.0-py3-none-any.whl")).unwrap();
        let uv_sha = sha256_file(&dir.path().join("uv")).unwrap();
        let req_sha = sha256_file(&dir.path().join("requirements-x86_64-unknown-linux-gnu.txt")).unwrap();
        write_file(
            dir.path(),
            "manifest.json",
            sample_manifest_json(&wheel_sha, &uv_sha, &req_sha).as_bytes(),
        );

        let manifest = load(dir.path()).expect("manifest should load");
        verify_bundle(&manifest, dir.path()).expect("bundle should verify clean");
    }

    #[test]
    fn rejects_unsupported_schema_version() {
        let dir = tempfile::tempdir().unwrap();
        write_file(
            dir.path(),
            "manifest.json",
            br#"{"schema_version": 99, "app": "persona-forge", "version": "1.0", "target": "t",
                "python_constraint": "c", "wheel": {"file": "a", "sha256": "x"},
                "uv": {"file": "u", "sha256": "y", "version": "1"},
                "requirements_file": "r", "requirements_sha256": "z"}"#,
        );
        let err = load(dir.path()).unwrap_err();
        assert!(matches!(err, ManifestError::UnsupportedSchema(99)));
    }

    #[test]
    fn rejects_manifest_for_a_different_app() {
        let dir = tempfile::tempdir().unwrap();
        write_file(
            dir.path(),
            "manifest.json",
            br#"{"schema_version": 1, "app": "not-persona-forge", "version": "1.0", "target": "t",
                "python_constraint": "c", "wheel": {"file": "a", "sha256": "x"},
                "uv": {"file": "u", "sha256": "y", "version": "1"},
                "requirements_file": "r", "requirements_sha256": "z"}"#,
        );
        let err = load(dir.path()).unwrap_err();
        assert!(matches!(err, ManifestError::WrongApp(_)));
    }

    #[test]
    fn detects_missing_member() {
        let dir = tempfile::tempdir().unwrap();
        write_file(dir.path(), "manifest.json", sample_manifest_json("x", "y", "z").as_bytes());
        let manifest = load(dir.path()).unwrap();
        let err = verify_bundle(&manifest, dir.path()).unwrap_err();
        assert!(matches!(err, ManifestError::MissingMember(m) if m == "persona_forge-1.3.0-py3-none-any.whl"));
    }

    #[test]
    fn detects_hash_mismatch() {
        let dir = tempfile::tempdir().unwrap();
        write_file(dir.path(), "persona_forge-1.3.0-py3-none-any.whl", b"wheel-bytes");
        write_file(dir.path(), "uv", b"uv-binary-bytes");
        write_file(dir.path(), "requirements-x86_64-unknown-linux-gnu.txt", b"foo==1.0\n");
        write_file(
            dir.path(),
            "manifest.json",
            sample_manifest_json("0000000000000000000000000000000000000000000000000000000000000000", "y", "z")
                .as_bytes(),
        );
        let manifest = load(dir.path()).unwrap();
        let err = verify_bundle(&manifest, dir.path()).unwrap_err();
        assert!(matches!(err, ManifestError::HashMismatch { member, .. } if member == "persona_forge-1.3.0-py3-none-any.whl"));
    }
}
