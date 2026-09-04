//! Native filesystem contract, mirrored from `src/persona_forge/paths.py::app_data_root`
//! (docs/plans/20260829-no_more_docker_architecture.md §4). Keep both resolvers in lockstep:
//! the launcher and the installed CLI must agree on where the app-managed environment lives.

use std::collections::HashMap;
use std::path::{Path, PathBuf};

pub type Environ = HashMap<String, String>;

fn clean(environ: &Environ, key: &str) -> Option<String> {
    environ.get(key).map(|v| v.trim().to_string()).filter(|v| !v.is_empty())
}

fn expand(value: &str, home: &Path) -> PathBuf {
    if value == "~" {
        return home.to_path_buf();
    }
    if let Some(rest) = value.strip_prefix("~/").or_else(|| value.strip_prefix("~\\")) {
        return home.join(rest);
    }
    PathBuf::from(value)
}

/// Resolve the application-state root: `PERSONA_FORGE_HOME` else the platform default.
pub fn app_data_root(environ: &Environ, platform: &str, home: &Path) -> PathBuf {
    if let Some(override_value) = clean(environ, "PERSONA_FORGE_HOME") {
        return expand(&override_value, home);
    }
    if platform.starts_with("win") {
        if let Some(local_appdata) = clean(environ, "LOCALAPPDATA") {
            return PathBuf::from(local_appdata).join("persona-forge");
        }
        return home.join("AppData").join("Local").join("persona-forge");
    }
    if platform == "darwin" {
        return home.join("Library").join("Application Support").join("persona-forge");
    }
    if let Some(xdg) = clean(environ, "XDG_DATA_HOME") {
        return PathBuf::from(xdg).join("persona-forge");
    }
    home.join(".local").join("share").join("persona-forge")
}

/// Where the launcher keeps its app-managed Python environments: `<app_data_root>/launcher`.
/// Kept as a distinct subtree from the Python-side state directories in `paths.py` so the
/// launcher never touches voice/model/runtime data while provisioning or rolling back envs.
pub fn launcher_root(environ: &Environ, platform: &str, home: &Path) -> PathBuf {
    app_data_root(environ, platform, home).join("launcher")
}

pub fn versions_dir(environ: &Environ, platform: &str, home: &Path) -> PathBuf {
    launcher_root(environ, platform, home).join("versions")
}

pub fn current_marker(environ: &Environ, platform: &str, home: &Path) -> PathBuf {
    launcher_root(environ, platform, home).join("current.txt")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn env(pairs: &[(&str, &str)]) -> Environ {
        pairs.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect()
    }

    #[test]
    fn honors_persona_forge_home_override() {
        let home = PathBuf::from("/home/nick");
        let e = env(&[("PERSONA_FORGE_HOME", "/custom/root")]);
        assert_eq!(app_data_root(&e, "linux", &home), PathBuf::from("/custom/root"));
    }

    #[test]
    fn expands_tilde_in_override_against_injected_home() {
        let home = PathBuf::from("/home/nick");
        let e = env(&[("PERSONA_FORGE_HOME", "~/custom")]);
        assert_eq!(app_data_root(&e, "linux", &home), home.join("custom"));
    }

    #[test]
    fn linux_default_uses_xdg_data_home() {
        let home = PathBuf::from("/home/nick");
        let e = env(&[("XDG_DATA_HOME", "/xdg")]);
        assert_eq!(app_data_root(&e, "linux", &home), PathBuf::from("/xdg/persona-forge"));
    }

    #[test]
    fn linux_default_falls_back_to_local_share() {
        let home = PathBuf::from("/home/nick");
        let e = env(&[]);
        assert_eq!(
            app_data_root(&e, "linux", &home),
            home.join(".local").join("share").join("persona-forge")
        );
    }

    #[test]
    fn macos_default_uses_application_support() {
        let home = PathBuf::from("/Users/nick");
        let e = env(&[]);
        assert_eq!(
            app_data_root(&e, "darwin", &home),
            home.join("Library").join("Application Support").join("persona-forge")
        );
    }

    #[test]
    fn windows_default_uses_localappdata() {
        let home = PathBuf::from("C:\\Users\\nick");
        let e = env(&[("LOCALAPPDATA", "C:\\Users\\nick\\AppData\\Local")]);
        assert_eq!(
            app_data_root(&e, "windows", &home),
            PathBuf::from("C:\\Users\\nick\\AppData\\Local").join("persona-forge")
        );
    }

    #[test]
    fn windows_default_falls_back_to_home_appdata_local() {
        let home = PathBuf::from("C:\\Users\\nick");
        let e = env(&[]);
        assert_eq!(
            app_data_root(&e, "windows", &home),
            home.join("AppData").join("Local").join("persona-forge")
        );
    }

    #[test]
    fn launcher_subtree_paths_derive_from_app_data_root() {
        let home = PathBuf::from("/home/nick");
        let e = env(&[]);
        let root = app_data_root(&e, "linux", &home);
        assert_eq!(launcher_root(&e, "linux", &home), root.join("launcher"));
        assert_eq!(versions_dir(&e, "linux", &home), root.join("launcher").join("versions"));
        assert_eq!(
            current_marker(&e, "linux", &home),
            root.join("launcher").join("current.txt")
        );
    }
}
