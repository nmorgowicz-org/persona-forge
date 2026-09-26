//! Navigation allowlist (contract §6.5). A pure function so the entire policy is unit-testable
//! without a webview.

use tauri::Url;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Decision {
    Allow,
    OpenExternal,
    Deny,
}

/// True for the app's own served origin: `http://127.0.0.1:<port>` (no other host, no other
/// scheme — only `127.0.0.1` is allowed, never the `localhost` hostname, which resolves
/// differently across OSes and browsers).
fn is_app_origin(url: &Url, port: u16) -> bool {
    url.scheme() == "http" && url.host_str() == Some("127.0.0.1") && url.port() == Some(port)
}

/// The two splash origins wry actually produces (contract §6.5): `tauri://localhost` on
/// macOS/Linux, `http://tauri.localhost` on Windows.
fn is_splash_origin(url: &Url) -> bool {
    if url.scheme() == "tauri" {
        return true;
    }
    url.scheme() == "http" && url.host_str() == Some("tauri.localhost")
}

/// Classify a navigation/new-window target against the app's allowed origins.
///
/// `port` is the current server port; only `http://127.0.0.1:<port>/...` (and its `blob:`
/// object URLs) are `Allow`. Any other `127.0.0.1` port, and the `localhost` hostname, are
/// `Deny` (not `OpenExternal`): they look like the app but aren't, so silently handing them to
/// the system browser would be surprising. External `http(s)` hosts and `mailto:` are
/// `OpenExternal`. Everything else (`file:`, `javascript:`, `data:`, ...) is `Deny`.
pub fn classify(url: &Url, port: u16) -> Decision {
    match url.scheme() {
        "mailto" => Decision::OpenExternal,
        "about" => {
            if url.as_str() == "about:blank" {
                Decision::Allow
            } else {
                Decision::Deny
            }
        }
        "tauri" => Decision::Allow,
        "http" | "https" => {
            if is_splash_origin(url) || is_app_origin(url, port) {
                return Decision::Allow;
            }
            if url.host_str() == Some("127.0.0.1") || url.host_str() == Some("localhost") {
                // Same host (or the ambiguous "localhost" name) but the wrong port/hostname:
                // never silently hand this to the system browser.
                return Decision::Deny;
            }
            Decision::OpenExternal
        }
        // blob: URLs carry their origin inside the path ("blob:http://127.0.0.1:8318/<uuid>"),
        // so url.host_str() is None for them; judge the inner URL instead (Phase 1 1C finding:
        // every blob was denied without this).
        "blob" => match Url::parse(url.path()) {
            Ok(inner) if is_app_origin(&inner, port) => Decision::Allow,
            _ => Decision::Deny,
        },
        _ => Decision::Deny,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const PORT: u16 = 8318;

    fn u(s: &str) -> Url {
        Url::parse(s).unwrap()
    }

    #[test]
    fn allowed_port_is_allowed() {
        assert_eq!(
            classify(&u("http://127.0.0.1:8318/voice-library"), PORT),
            Decision::Allow
        );
    }

    #[test]
    fn blob_on_the_allowed_port_is_allowed() {
        assert_eq!(
            classify(&u("blob:http://127.0.0.1:8318/9c858...uuid"), PORT),
            Decision::Allow
        );
    }

    #[test]
    fn about_blank_is_allowed() {
        assert_eq!(classify(&u("about:blank"), PORT), Decision::Allow);
    }

    #[test]
    fn the_same_host_on_another_port_is_denied() {
        assert_eq!(classify(&u("http://127.0.0.1:9999/"), PORT), Decision::Deny);
    }

    #[test]
    fn localhost_hostname_is_denied_even_on_the_right_port() {
        assert_eq!(classify(&u("http://localhost:8318/"), PORT), Decision::Deny);
    }

    #[test]
    fn external_https_opens_externally() {
        assert_eq!(
            classify(&u("https://github.com/nmorgowicz-org/persona-forge"), PORT),
            Decision::OpenExternal
        );
    }

    #[test]
    fn mailto_opens_externally() {
        assert_eq!(
            classify(&u("mailto:someone@example.com"), PORT),
            Decision::OpenExternal
        );
    }

    #[test]
    fn file_scheme_is_denied() {
        assert_eq!(classify(&u("file:///etc/passwd"), PORT), Decision::Deny);
    }

    #[test]
    fn javascript_scheme_is_denied() {
        assert_eq!(classify(&u("javascript:alert(1)"), PORT), Decision::Deny);
    }

    #[test]
    fn data_scheme_is_denied() {
        assert_eq!(classify(&u("data:text/html,hi"), PORT), Decision::Deny);
    }

    #[test]
    fn the_tauri_splash_origin_is_allowed() {
        assert_eq!(
            classify(&u("tauri://localhost/index.html"), PORT),
            Decision::Allow
        );
    }

    #[test]
    fn the_windows_splash_origin_is_allowed() {
        assert_eq!(
            classify(&u("http://tauri.localhost/index.html"), PORT),
            Decision::Allow
        );
    }

    #[test]
    fn a_blob_off_the_app_origin_is_denied() {
        assert_eq!(
            classify(&u("blob:https://evil.example/9c858...uuid"), PORT),
            Decision::Deny
        );
    }
}
