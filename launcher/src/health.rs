//! Port/health probing (contract §6.3, `docs/plans/20260925-native_app_shell_auto_update.md`
//! Phase 2). std-only HTTP/1.1 GET over `TcpStream`; no HTTP client dependency, since the only
//! thing ever probed is `GET /health` against a local Persona Forge server.

use std::io::{BufRead, BufReader, Read, Write};
use std::net::{Ipv4Addr, SocketAddr, TcpListener, TcpStream};
use std::str::FromStr;
use std::time::{Duration, Instant};

#[derive(Debug, PartialEq, Eq)]
pub enum PortState {
    /// Nothing is bound to the port.
    Free,
    /// Something is bound and its `/health` body looks like Persona Forge's.
    PersonaForge,
    /// Something is bound, but it isn't Persona Forge (or didn't answer coherently in time).
    Other,
}

/// Contract §6.3: `Free` if `TcpListener::bind((bind_host, port))` succeeds (dropped at once);
/// otherwise `GET http://127.0.0.1:<port>/health` with `timeout`: `PersonaForge` if the body is
/// a JSON object with a string `"status"` key and a `"service_started"` key; anything else
/// (non-2xx, non-JSON, wrong shape, or no response inside `timeout`) is `Other`.
pub fn probe_port(bind_host: &str, port: u16, timeout: Duration) -> PortState {
    let addr = match std::net::IpAddr::from_str(bind_host) {
        Ok(ip) => SocketAddr::from((ip, port)),
        Err(_) => SocketAddr::from((Ipv4Addr::UNSPECIFIED, port)),
    };
    if TcpListener::bind(addr).is_ok() {
        return PortState::Free;
    }
    if get_health(port, timeout).is_some_and(|body| looks_like_persona_forge(&body)) {
        PortState::PersonaForge
    } else {
        PortState::Other
    }
}

/// True if a `GET /health` against `127.0.0.1:<port>` returns 200 with a JSON body inside
/// `timeout`.
pub fn health_ok(port: u16, timeout: Duration) -> bool {
    get_health(port, timeout).is_some()
}

/// Perform `GET /health` and return the response body iff the status line is 2xx and the body
/// parses as JSON. `None` on any I/O error, non-2xx status, timeout, or non-JSON body.
fn get_health(port: u16, timeout: Duration) -> Option<serde_json::Value> {
    let deadline = Instant::now() + timeout;
    let addr = SocketAddr::from((Ipv4Addr::LOCALHOST, port));
    let remaining = deadline.saturating_duration_since(Instant::now());
    if remaining.is_zero() {
        return None;
    }
    let mut stream = TcpStream::connect_timeout(&addr, remaining).ok()?;
    stream
        .set_read_timeout(Some(
            deadline
                .saturating_duration_since(Instant::now())
                .max(Duration::from_millis(1)),
        ))
        .ok()?;
    stream
        .set_write_timeout(Some(
            deadline
                .saturating_duration_since(Instant::now())
                .max(Duration::from_millis(1)),
        ))
        .ok()?;

    let request = format!("GET /health HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\nAccept: application/json\r\n\r\n");
    stream.write_all(request.as_bytes()).ok()?;

    let mut reader = BufReader::new(stream);
    let mut status_line = String::new();
    reader.read_line(&mut status_line).ok()?;
    // "HTTP/1.1 200 OK\r\n"
    let status: u32 = status_line.split_whitespace().nth(1)?.parse().ok()?;
    if !(200..300).contains(&status) {
        return None;
    }

    let mut content_length: Option<usize> = None;
    let mut chunked = false;
    loop {
        let mut line = String::new();
        if reader.read_line(&mut line).ok()? == 0 {
            return None; // connection closed mid-headers
        }
        let trimmed = line.trim_end();
        if trimmed.is_empty() {
            break; // end of headers
        }
        if let Some((name, value)) = trimmed.split_once(':') {
            let name = name.trim().to_ascii_lowercase();
            let value = value.trim();
            if name == "content-length" {
                content_length = value.parse().ok();
            } else if name == "transfer-encoding" && value.eq_ignore_ascii_case("chunked") {
                chunked = true;
            }
        }
    }

    let mut body = Vec::new();
    if chunked {
        read_chunked_body(&mut reader, &mut body)?;
    } else if let Some(len) = content_length {
        body.resize(len, 0);
        reader.read_exact(&mut body).ok()?;
    } else {
        reader.read_to_end(&mut body).ok()?;
    }

    serde_json::from_slice(&body).ok()
}

fn read_chunked_body<R: BufRead>(reader: &mut R, out: &mut Vec<u8>) -> Option<()> {
    loop {
        let mut size_line = String::new();
        reader.read_line(&mut size_line).ok()?;
        let size_str = size_line.trim().split(';').next()?;
        let size = usize::from_str_radix(size_str, 16).ok()?;
        if size == 0 {
            break;
        }
        let mut chunk = vec![0u8; size];
        reader.read_exact(&mut chunk).ok()?;
        out.extend_from_slice(&chunk);
        let mut crlf = [0u8; 2];
        reader.read_exact(&mut crlf).ok()?;
    }
    Some(())
}

fn looks_like_persona_forge(body: &serde_json::Value) -> bool {
    let Some(obj) = body.as_object() else {
        return false;
    };
    matches!(obj.get("status"), Some(serde_json::Value::String(_)))
        && obj.contains_key("service_started")
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;
    use std::thread;

    fn spawn_responder(respond: impl Fn(&str) -> Vec<u8> + Send + 'static) -> u16 {
        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        thread::spawn(move || {
            if let Ok((mut stream, _)) = listener.accept() {
                let mut reader = BufReader::new(stream.try_clone().unwrap());
                let mut request_line = String::new();
                let _ = reader.read_line(&mut request_line);
                let response = respond(&request_line);
                let _ = stream.write_all(&response);
            }
        });
        port
    }

    fn json_response(status_line: &str, body: &str) -> Vec<u8> {
        format!("{status_line}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len())
            .into_bytes()
    }

    #[test]
    fn persona_forge_body_with_service_started_true() {
        let port = spawn_responder(|_| {
            json_response(
                "HTTP/1.1 200 OK",
                r#"{"status":"ok","service_started":true,"version":"x"}"#,
            )
        });
        assert_eq!(
            probe_port("127.0.0.1", port, Duration::from_secs(2)),
            PortState::PersonaForge
        );
    }

    #[test]
    fn persona_forge_body_with_no_version_key() {
        let port = spawn_responder(|_| {
            json_response(
                "HTTP/1.1 200 OK",
                r#"{"status":"error","service_started":false}"#,
            )
        });
        assert_eq!(
            probe_port("127.0.0.1", port, Duration::from_secs(2)),
            PortState::PersonaForge
        );
    }

    #[test]
    fn html_body_is_other() {
        let port = spawn_responder(|_| {
            let body = "<html>hi</html>";
            format!("HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len())
                .into_bytes()
        });
        assert_eq!(
            probe_port("127.0.0.1", port, Duration::from_secs(2)),
            PortState::Other
        );
    }

    #[test]
    fn server_error_status_is_other() {
        let port = spawn_responder(|_| {
            json_response(
                "HTTP/1.1 500 Internal Server Error",
                r#"{"status":"ok","service_started":true}"#,
            )
        });
        assert_eq!(
            probe_port("127.0.0.1", port, Duration::from_secs(2)),
            PortState::Other
        );
    }

    #[test]
    fn an_unbound_port_is_free() {
        // Find a free port, then immediately drop the listener so nothing else grabs it.
        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        drop(listener);
        assert_eq!(
            probe_port("127.0.0.1", port, Duration::from_secs(1)),
            PortState::Free
        );
    }

    #[test]
    fn accept_then_never_respond_is_other_within_timeout() {
        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        thread::spawn(move || {
            // Accept and hold the connection open without ever writing a response.
            if let Ok((stream, _)) = listener.accept() {
                thread::sleep(Duration::from_secs(5));
                drop(stream);
            }
        });
        let started = Instant::now();
        assert_eq!(
            probe_port("127.0.0.1", port, Duration::from_millis(500)),
            PortState::Other
        );
        assert!(
            started.elapsed() < Duration::from_secs(3),
            "must not block for the full 5s hold"
        );
    }

    #[test]
    fn health_ok_true_for_a_200_json_body() {
        let port = spawn_responder(|_| json_response("HTTP/1.1 200 OK", r#"{"status":"ok"}"#));
        assert!(health_ok(port, Duration::from_secs(2)));
    }
}
