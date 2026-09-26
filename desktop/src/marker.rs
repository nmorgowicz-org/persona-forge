//! Desktop marker (contract D20/§6.10). This is not IPC and grants nothing: it's the `main`
//! window's initialization script, so `window.__PERSONA_FORGE_DESKTOP__` exists before any page
//! script runs, on every top-level navigation, only for origins the shell itself trusts.

/// `platform` is fixed at compile time (`cfg!(target_os)`), never read from the OS at runtime.
pub fn desktop_marker_script(platform: &str) -> String {
    format!(
        r#"if ((location.protocol === 'http:' && location.hostname === '127.0.0.1') ||
    location.protocol === 'tauri:' || location.hostname === 'tauri.localhost') {{
  window.__PERSONA_FORGE_DESKTOP__ = Object.freeze({{ platform: '{platform}' }});
}}"#
    )
}

/// The compile-time platform string used everywhere `desktop_marker_script` is called.
pub fn current_platform() -> &'static str {
    if cfg!(target_os = "macos") {
        "macos"
    } else if cfg!(target_os = "windows") {
        "windows"
    } else {
        "linux"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn contains_the_origin_guard_and_the_platform_string() {
        let script = desktop_marker_script("macos");
        assert!(script.contains("127.0.0.1"));
        assert!(script.contains("tauri:"));
        assert!(script.contains("tauri.localhost"));
        assert!(script.contains("'macos'"));
    }

    #[test]
    fn current_platform_matches_the_current_target_os() {
        let p = current_platform();
        assert!(p == "macos" || p == "windows" || p == "linux");
        #[cfg(target_os = "macos")]
        assert_eq!(p, "macos");
    }
}
