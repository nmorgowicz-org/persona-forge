//! Server process supervision (contract §6.2, `docs/plans/20260925-native_app_shell_auto_update.md`
//! Phase 2). Spawns `<python> -m persona_forge.cli serve` in its own process group (Unix) /
//! kill-on-close Job Object (Windows), and gives the desktop shell a clean stop/health handshake
//! instead of relying on the child ever seeing a console Ctrl+C.

use std::io;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::time::{Duration, Instant};

use process_wrap::std::*;

use crate::health;

pub struct ServerSpec {
    pub python: PathBuf,
    /// "127.0.0.1" or "0.0.0.0" (D18).
    pub host: String,
    pub port: u16,
    pub extra_env: Vec<(String, String)>,
    pub log_path: PathBuf,
}

pub struct ServerHandle {
    child: Box<dyn ChildWrapper>,
    pid: u32,
}

impl ServerHandle {
    /// Spawns `<python> -m persona_forge.cli serve --host <host> --port <port>` in its own
    /// process group (Unix) / kill-on-close Job Object (Windows, `CREATE_NO_WINDOW`), stdout and
    /// stderr appended to `log_path`.
    pub fn spawn(spec: &ServerSpec) -> io::Result<Self> {
        let args = [
            "-m".to_string(),
            "persona_forge.cli".to_string(),
            "serve".to_string(),
            "--host".to_string(),
            spec.host.clone(),
            "--port".to_string(),
            spec.port.to_string(),
        ];
        let args: Vec<&str> = args.iter().map(String::as_str).collect();
        Self::spawn_command(&spec.python, &args, &spec.extra_env, &spec.log_path)
    }

    /// Same wrapping as [`spawn`](Self::spawn), for an arbitrary program/args — used by tests
    /// (including the real-server supervisor test) so they don't have to construct a full
    /// `ServerSpec`/manifest just to exercise process-group/job-object teardown.
    #[cfg_attr(not(test), allow(dead_code))]
    pub fn spawn_command(
        program: &Path,
        args: &[&str],
        env: &[(String, String)],
        log_path: &Path,
    ) -> io::Result<Self> {
        let log_file = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(log_path)?;
        let log_file_err = log_file.try_clone()?;

        let mut command = CommandWrap::with_new(program, |command| {
            command.args(args);
            for (k, v) in env {
                command.env(k, v);
            }
            command.stdin(Stdio::null());
            command.stdout(log_file);
            command.stderr(log_file_err);
            #[cfg(windows)]
            {
                use std::os::windows::process::CommandExt;
                const CREATE_NO_WINDOW: u32 = 0x0800_0000;
                command.creation_flags(CREATE_NO_WINDOW);
            }
        });

        #[cfg(unix)]
        command.wrap(ProcessGroup::leader());
        #[cfg(windows)]
        {
            command.wrap(CreationFlags(
                windows::Win32::System::Threading::PROCESS_CREATION_FLAGS(0x0800_0000),
            ));
            command.wrap(JobObject);
        }

        let child = command.spawn()?;
        let pid = child.id();
        Ok(Self { child, pid })
    }

    pub fn pid(&self) -> u32 {
        self.pid
    }

    pub fn try_wait(&mut self) -> io::Result<Option<std::process::ExitStatus>> {
        self.child.try_wait()
    }

    /// Unix: `SIGTERM` the group, wait up to `grace`, then `SIGKILL` the group.
    /// Windows: `TerminateJobObject` immediately (no graceful signal exists; `grace` is ignored).
    pub fn stop(mut self, grace: Duration) -> io::Result<()> {
        #[cfg(unix)]
        {
            self.child.signal(libc::SIGTERM)?;
            let deadline = Instant::now() + grace;
            loop {
                if self.child.try_wait()?.is_some() {
                    return Ok(());
                }
                if Instant::now() >= deadline {
                    break;
                }
                std::thread::sleep(Duration::from_millis(50));
            }
            self.child.start_kill()?;
            self.child.wait()?;
            Ok(())
        }
        #[cfg(windows)]
        {
            let _ = grace;
            self.child.start_kill()?;
            self.child.wait()?;
            Ok(())
        }
    }
}

#[derive(Debug)]
pub enum ReadyError {
    Exited(Option<i32>),
    Timeout,
}

pub fn wait_ready(h: &mut ServerHandle, port: u16, timeout: Duration) -> Result<(), ReadyError> {
    let deadline = Instant::now() + timeout;
    loop {
        if let Some(status) = h.try_wait().map_err(|_| ReadyError::Timeout)? {
            return Err(ReadyError::Exited(status.code()));
        }
        if health::health_ok(port, Duration::from_millis(300)) {
            return Ok(());
        }
        if Instant::now() >= deadline {
            return Err(ReadyError::Timeout);
        }
        std::thread::sleep(Duration::from_millis(100));
    }
}

// --- Orphan recovery pidfile (Unix, §6.2) ---

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PidRecord {
    pub pid: u32,
    pub pgid: u32,
    pub port: u16,
    pub started_at: u64,
}

pub fn write_pidfile(path: &Path, rec: &PidRecord) -> io::Result<()> {
    let contents = format!(
        "{}\n{}\n{}\n{}\n",
        rec.pid, rec.pgid, rec.port, rec.started_at
    );
    let tmp = path.with_extension("tmp");
    std::fs::write(&tmp, contents)?;
    std::fs::rename(&tmp, path)?;
    Ok(())
}

pub fn read_pidfile(path: &Path) -> Option<PidRecord> {
    let contents = std::fs::read_to_string(path).ok()?;
    let mut lines = contents.lines();
    Some(PidRecord {
        pid: lines.next()?.parse().ok()?,
        pgid: lines.next()?.parse().ok()?,
        port: lines.next()?.parse().ok()?,
        started_at: lines.next()?.parse().ok()?,
    })
}

/// Kills the process group recorded in `rec` iff `rec.pid` is alive and its command line
/// contains `persona_forge.app:app` — refuses to signal anything else that happens to reuse the
/// pid. Returns `Ok(true)` if it signalled, `Ok(false)` if the pid wasn't alive or wasn't ours.
#[cfg(unix)]
pub fn kill_orphan(rec: &PidRecord, grace: Duration) -> io::Result<bool> {
    if !pid_alive(rec.pid) {
        return Ok(false);
    }
    if !command_line_matches(rec.pid, "persona_forge.app:app") {
        return Ok(false);
    }

    unsafe { libc::killpg(rec.pgid as i32, libc::SIGTERM) };
    let deadline = Instant::now() + grace;
    while pid_alive(rec.pid) {
        if Instant::now() >= deadline {
            unsafe { libc::killpg(rec.pgid as i32, libc::SIGKILL) };
            break;
        }
        std::thread::sleep(Duration::from_millis(50));
    }
    Ok(true)
}

#[cfg(unix)]
fn pid_alive(pid: u32) -> bool {
    unsafe { libc::kill(pid as i32, 0) == 0 }
}

#[cfg(unix)]
fn command_line_matches(pid: u32, needle: &str) -> bool {
    let output = std::process::Command::new("ps")
        .args(["-o", "command=", "-p", &pid.to_string()])
        .output();
    match output {
        Ok(out) => String::from_utf8_lossy(&out.stdout).contains(needle),
        Err(_) => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pidfile_round_trips() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("server.pid");
        let rec = PidRecord {
            pid: 4242,
            pgid: 4242,
            port: 8318,
            started_at: 1_700_000_000,
        };

        write_pidfile(&path, &rec).unwrap();

        assert_eq!(read_pidfile(&path), Some(rec));
    }

    #[test]
    fn read_pidfile_missing_file_is_none() {
        let dir = tempfile::tempdir().unwrap();
        assert_eq!(read_pidfile(&dir.path().join("nope.pid")), None);
    }

    #[cfg(unix)]
    #[test]
    fn kill_orphan_refuses_a_live_pid_whose_command_line_lacks_the_marker() {
        // The test process's own pid is alive, but its command line is the test binary, not
        // persona_forge.app:app -- kill_orphan must refuse to signal it.
        let rec = PidRecord {
            pid: std::process::id(),
            pgid: std::process::id(),
            port: 8318,
            started_at: 0,
        };
        assert!(!kill_orphan(&rec, Duration::from_millis(100)).unwrap());
    }

    #[cfg(unix)]
    #[test]
    fn spawn_stop_reaps_child_and_grandchild() {
        let dir = tempfile::tempdir().unwrap();
        let log_path = dir.path().join("server.log");
        let gc_pid_file = dir.path().join("gc");
        let script = format!("sleep 60 & echo $! > {}; wait", gc_pid_file.display());

        let handle =
            ServerHandle::spawn_command(Path::new("sh"), &["-c", &script], &[], &log_path).unwrap();
        let child_pid = handle.pid();

        // Wait for the grandchild pid file to appear.
        let deadline = Instant::now() + Duration::from_secs(5);
        while !gc_pid_file.exists() && Instant::now() < deadline {
            std::thread::sleep(Duration::from_millis(20));
        }
        let grandchild_pid: i32 = std::fs::read_to_string(&gc_pid_file)
            .unwrap()
            .trim()
            .parse()
            .unwrap();

        handle.stop(Duration::from_secs(2)).unwrap();

        assert_ne!(
            unsafe { libc::kill(child_pid as i32, 0) },
            0,
            "child must be gone"
        );
        assert_ne!(
            unsafe { libc::kill(grandchild_pid, 0) },
            0,
            "grandchild must be gone"
        );
    }

    #[cfg(unix)]
    #[test]
    fn try_wait_reports_exit_status() {
        let dir = tempfile::tempdir().unwrap();
        let log_path = dir.path().join("server.log");
        let mut handle =
            ServerHandle::spawn_command(Path::new("sh"), &["-c", "exit 3"], &[], &log_path)
                .unwrap();

        let deadline = Instant::now() + Duration::from_secs(5);
        let status = loop {
            if let Some(status) = handle.try_wait().unwrap() {
                break status;
            }
            assert!(Instant::now() < deadline, "child never exited");
            std::thread::sleep(Duration::from_millis(20));
        };
        assert_eq!(status.code(), Some(3));
    }

    #[cfg(unix)]
    #[test]
    fn wait_ready_returns_exited_for_a_process_that_exits() {
        let dir = tempfile::tempdir().unwrap();
        let log_path = dir.path().join("server.log");
        let mut handle =
            ServerHandle::spawn_command(Path::new("sh"), &["-c", "exit 3"], &[], &log_path)
                .unwrap();

        let result = wait_ready(&mut handle, 0, Duration::from_secs(5));

        assert!(matches!(result, Err(ReadyError::Exited(Some(3)))));
    }

    #[cfg(windows)]
    #[test]
    fn spawn_stop_reaps_all_captured_pids() {
        let dir = tempfile::tempdir().unwrap();
        let log_path = dir.path().join("server.log");
        let script = "start /b ping -n 60 127.0.0.1 >NUL & ping -n 60 127.0.0.1 >NUL";

        let handle =
            ServerHandle::spawn_command(Path::new("cmd"), &["/c", script], &[], &log_path).unwrap();
        let pid = handle.pid();

        handle.stop(Duration::from_secs(2)).unwrap();

        let alive = std::process::Command::new("tasklist")
            .args(["/FI", &format!("PID eq {pid}")])
            .output()
            .map(|out| String::from_utf8_lossy(&out.stdout).contains(&pid.to_string()))
            .unwrap_or(false);
        assert!(!alive, "process must be gone after stop");
    }

    #[cfg(windows)]
    #[test]
    fn try_wait_reports_exit_status() {
        let dir = tempfile::tempdir().unwrap();
        let log_path = dir.path().join("server.log");
        let mut handle =
            ServerHandle::spawn_command(Path::new("cmd"), &["/c", "exit 3"], &[], &log_path)
                .unwrap();

        let deadline = Instant::now() + Duration::from_secs(5);
        let status = loop {
            if let Some(status) = handle.try_wait().unwrap() {
                break status;
            }
            assert!(Instant::now() < deadline, "child never exited");
            std::thread::sleep(Duration::from_millis(20));
        };
        assert_eq!(status.code(), Some(3));
    }

    #[cfg(windows)]
    #[test]
    fn wait_ready_returns_exited_for_a_process_that_exits() {
        let dir = tempfile::tempdir().unwrap();
        let log_path = dir.path().join("server.log");
        let mut handle =
            ServerHandle::spawn_command(Path::new("cmd"), &["/c", "exit 3"], &[], &log_path)
                .unwrap();

        let result = wait_ready(&mut handle, 0, Duration::from_secs(5));

        assert!(matches!(result, Err(ReadyError::Exited(Some(3)))));
    }

    /// Real-server acceptance (both OSes): run `#[ignore]`d explicitly in Gate 2.
    #[test]
    #[ignore]
    fn spawns_the_real_server_and_reaches_health() {
        let repo_root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .to_path_buf();
        let python = if cfg!(windows) {
            repo_root.join(".venv").join("Scripts").join("python.exe")
        } else {
            repo_root.join(".venv").join("bin").join("python")
        };
        let dir = tempfile::tempdir().unwrap();
        let log_path = dir.path().join("server.log");

        let listener = std::net::TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        drop(listener);

        let path_sep = if cfg!(windows) { ";" } else { ":" };
        let env = vec![
            (
                "PERSONA_FORGE_WSGI_TARGET".to_string(),
                "tests.fixtures.fake_wsgi_app:app".to_string(),
            ),
            (
                "PYTHONPATH".to_string(),
                format!(
                    "{}{path_sep}{}",
                    repo_root.join("src").display(),
                    repo_root.display()
                ),
            ),
            (
                "PATH".to_string(),
                if cfg!(windows) {
                    "C:\\Windows\\System32;C:\\Windows".to_string()
                } else {
                    "/usr/bin:/bin".to_string()
                },
            ),
        ];

        let spec = ServerSpec {
            python,
            host: "127.0.0.1".to_string(),
            port,
            extra_env: env,
            log_path,
        };
        let mut handle = ServerHandle::spawn(&spec).unwrap();

        wait_ready(&mut handle, port, Duration::from_secs(20)).expect("server must become ready");
        assert_eq!(
            health::probe_port("127.0.0.1", port, Duration::from_secs(2)),
            health::PortState::PersonaForge
        );

        handle.stop(Duration::from_secs(5)).unwrap();

        assert_eq!(
            health::probe_port("127.0.0.1", port, Duration::from_secs(2)),
            health::PortState::Free
        );
    }
}
