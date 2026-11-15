//! The ARGOS server sidecar: start it, read its address, stop it.
//!
//! The server is the PyInstaller-frozen `python -m argos.server`
//! (`packaging/argos_server.spec`), shipped as Tauri's `externalBin`: next to
//! the shell's own executable, without the target-triple suffix. It prints
//! `ARGOS_PORT=<port>` then `ARGOS_TOKEN=<token>` on stdout once its socket
//! listens (argos/server/protocol.md, "Launching"); everything else goes to
//! stderr.
//!
//! It runs as the leader of its own process group, so that a stop can sweep
//! everything it started (the PyInstaller bootloader, the Python process it
//! forks, helpers such as `caffeinate`). A stop sends SIGTERM to the leader
//! only (the bootloader forwards it once to Python: a second SIGTERM would make
//! uvicorn skip its graceful shutdown), waits [`STOP_GRACE`], then SIGKILLs the
//! whole group.
//!
//! The pid lives in an atomic and every stop path uses atomics only, so the
//! panic hook and the signal watcher can call [`stop`] whatever lock another
//! thread holds.

use std::collections::VecDeque;
use std::io::{self, BufRead, BufReader};
use std::path::PathBuf;
use std::process::{ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicI32, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

/// How long the server may take to print its address. A one-file sidecar
/// unpacks itself before Python starts, and the first launch after an
/// install is scanned by the OS: keep a wide margin.
pub const STARTUP_TIMEOUT: Duration = Duration::from_secs(60);

/// How long a stop waits for the server's graceful shutdown (jobs cancelled,
/// exposure cancelled, devices disconnected) before the group is killed.
pub const STOP_GRACE: Duration = Duration::from_secs(10);

/// Lines of the server's stderr kept for the failure page.
const TAIL_LINES: usize = 80;

/// pid of the running sidecar (leader of its own process group), 0 when none.
static PID: AtomicI32 = AtomicI32::new(0);

/// Set while the shell stops the sidecar on purpose: that exit is no crash.
static STOPPING: AtomicBool = AtomicBool::new(false);

/// The server's address, read from its stdout.
pub struct Ready {
    pub port: u16,
    pub token: String,
    pub elapsed: Duration,
    /// Kept open for the server's lifetime. Nothing is written to it; its end
    /// of file is how a future server-side watch can tell that the shell died
    /// without stopping it (see the W8 notes in main.rs).
    pub stdin: Option<ChildStdin>,
}

/// Why the server did not start.
pub enum StartError {
    NotFound(PathBuf),
    Spawn(PathBuf, io::Error),
    Exited(String),
    Timeout(Duration),
}

impl StartError {
    /// One sentence for the failure page.
    pub fn cause(&self) -> String {
        match self {
            StartError::NotFound(path) => format!(
                "The ARGOS server is missing from the application ({}).",
                path.display()
            ),
            StartError::Spawn(path, err) => format!(
                "The ARGOS server could not be launched ({}): {err}.",
                path.display()
            ),
            StartError::Exited(status) => {
                format!("The ARGOS server stopped during start-up ({status}).")
            }
            StartError::Timeout(after) => format!(
                "The ARGOS server did not report its address within {} s; it was stopped.",
                after.as_secs()
            ),
        }
    }
}

/// The last lines the server wrote on stderr, shared with the failure page.
#[derive(Clone, Default)]
pub struct Tail(Arc<Mutex<VecDeque<String>>>);

impl Tail {
    fn push(&self, line: String) {
        if let Ok(mut lines) = self.0.lock() {
            if lines.len() == TAIL_LINES {
                lines.pop_front();
            }
            lines.push_back(line);
        }
    }

    pub fn text(&self) -> String {
        self.0
            .lock()
            .map(|lines| lines.iter().cloned().collect::<Vec<_>>().join("\n"))
            .unwrap_or_default()
    }
}

/// The frozen server next to the shell's executable (Tauri strips the
/// target-triple suffix of `externalBin` when it bundles or copies it).
pub fn path() -> io::Result<PathBuf> {
    let exe = std::env::current_exe()?;
    let dir = exe
        .parent()
        .ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, "no executable folder"))?;
    Ok(dir.join(if cfg!(windows) {
        "argos-server.exe"
    } else {
        "argos-server"
    }))
}

/// Start the server and wait for its address. Blocking: run it off the main
/// thread. `on_exit(status, on_purpose)` runs once, on a helper thread, when
/// the process ends (on_purpose: the shell stopped it).
pub fn start(
    extra_args: &[String],
    tail: Tail,
    on_exit: impl FnOnce(String, bool) + Send + 'static,
) -> Result<Ready, StartError> {
    let path = path().map_err(|err| StartError::Spawn(PathBuf::from("argos-server"), err))?;
    if !path.is_file() {
        return Err(StartError::NotFound(path));
    }
    let mut command = Command::new(&path);
    // An OS-chosen free port on the loopback interface only.
    command
        .args(["--host", "127.0.0.1", "--port", "0"])
        .args(extra_args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        command.process_group(0);
    }
    let started = Instant::now();
    let mut child = command
        .spawn()
        .map_err(|err| StartError::Spawn(path.clone(), err))?;
    let pid = child.id() as i32;
    STOPPING.store(false, Ordering::SeqCst);
    PID.store(pid, Ordering::SeqCst);
    let stdin = child.stdin.take();
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();

    // stdout: the two machine lines, then anything else (drained, never
    // shown: the server writes nothing else there).
    let (lines_tx, lines_rx) = mpsc::channel::<String>();
    if let Some(stdout) = stdout {
        thread::Builder::new()
            .name("argos-server-stdout".into())
            .spawn(move || {
                for line in BufReader::new(stdout).lines() {
                    let Ok(line) = line else { break };
                    let _ = lines_tx.send(line);
                }
            })
            .ok();
    }
    // stderr: echoed to the shell's own stderr and kept for the failure page.
    if let Some(stderr) = stderr {
        let tail = tail.clone();
        thread::Builder::new()
            .name("argos-server-stderr".into())
            .spawn(move || {
                for line in BufReader::new(stderr).lines() {
                    let Ok(line) = line else { break };
                    eprintln!("{line}");
                    tail.push(line);
                }
            })
            .ok();
    }
    // The process itself: reaped here, its status reported once.
    let status_slot: Arc<Mutex<Option<String>>> = Arc::default();
    {
        let status_slot = status_slot.clone();
        thread::Builder::new()
            .name("argos-server-wait".into())
            .spawn(move || {
                let status = match child.wait() {
                    Ok(status) => describe(status),
                    Err(err) => format!("wait failed: {err}"),
                };
                let _ = PID.compare_exchange(pid, 0, Ordering::SeqCst, Ordering::SeqCst);
                let on_purpose = STOPPING.load(Ordering::SeqCst);
                eprintln!("argos-desktop: server process {pid} ended ({status})");
                if let Ok(mut slot) = status_slot.lock() {
                    *slot = Some(status.clone());
                }
                on_exit(status, on_purpose);
            })
            .map_err(|err| StartError::Spawn(path.clone(), err))?;
    }

    let deadline = started + STARTUP_TIMEOUT;
    let (mut port, mut token) = (None::<u16>, None::<String>);
    loop {
        let left = deadline.saturating_duration_since(Instant::now());
        match lines_rx.recv_timeout(left) {
            Ok(line) => {
                let line = line.trim();
                if let Some(value) = line.strip_prefix("ARGOS_PORT=") {
                    port = value.parse().ok();
                } else if let Some(value) = line.strip_prefix("ARGOS_TOKEN=") {
                    token = Some(value.to_owned()).filter(|t| !t.is_empty());
                }
                if let (Some(port), Some(token)) = (port, token.clone()) {
                    return Ok(Ready {
                        port,
                        token,
                        elapsed: started.elapsed(),
                        stdin,
                    });
                }
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                // stdout closed: the server is ending; give the reaper a moment.
                let until = Instant::now() + Duration::from_secs(3);
                while Instant::now() < until {
                    if let Some(status) = status_slot.lock().ok().and_then(|slot| slot.clone()) {
                        return Err(StartError::Exited(status));
                    }
                    thread::sleep(Duration::from_millis(20));
                }
                stop(STOP_GRACE);
                return Err(StartError::Exited("its output closed".into()));
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {
                stop(STOP_GRACE);
                return Err(StartError::Timeout(STARTUP_TIMEOUT));
            }
        }
    }
}

/// Stop the sidecar, if one runs: SIGTERM, up to `grace` for the graceful
/// shutdown, then SIGKILL to its whole process group. Idempotent, lock-free,
/// safe from the panic hook and the signal watcher.
pub fn stop(grace: Duration) {
    let pid = PID.load(Ordering::SeqCst);
    if pid <= 0 {
        return;
    }
    STOPPING.store(true, Ordering::SeqCst);
    let began = Instant::now();
    sys::terminate(pid);
    let deadline = began + grace;
    while PID.load(Ordering::SeqCst) == pid && Instant::now() < deadline {
        thread::sleep(Duration::from_millis(20));
    }
    if PID.load(Ordering::SeqCst) == pid {
        eprintln!(
            "argos-desktop: server {pid} still running after {} ms, killing its process group",
            began.elapsed().as_millis()
        );
        sys::kill_group(pid);
        let deadline = Instant::now() + Duration::from_secs(3);
        while PID.load(Ordering::SeqCst) == pid && Instant::now() < deadline {
            thread::sleep(Duration::from_millis(20));
        }
    } else {
        // Leftover helpers of a clean exit (an external solver, say): the
        // group id cannot be reused while any of them lives.
        sys::kill_group(pid);
        eprintln!(
            "argos-desktop: server stopped in {} ms",
            began.elapsed().as_millis()
        );
    }
}

fn describe(status: std::process::ExitStatus) -> String {
    #[cfg(unix)]
    {
        use std::os::unix::process::ExitStatusExt;
        if let Some(signal) = status.signal() {
            return format!("signal {signal}");
        }
    }
    match status.code() {
        Some(code) => format!("exit status {code}"),
        None => "unknown status".into(),
    }
}

/// Run `on_signal(signal)` on a helper thread for each SIGTERM, SIGINT or
/// SIGHUP the shell receives. The handler only writes the signal number to a
/// socket pair (async-signal-safe); the thread does the work.
#[cfg(unix)]
pub fn watch_signals(on_signal: impl Fn(i32) + Send + 'static) -> io::Result<()> {
    use std::io::Read;
    use std::os::fd::IntoRawFd;
    use std::os::unix::net::UnixStream;

    let (mut reader, writer) = UnixStream::pair()?;
    writer.set_nonblocking(true)?;
    sys::WAKE_FD.store(writer.into_raw_fd(), Ordering::SeqCst);
    for signal in [sys::SIGTERM, sys::SIGINT, sys::SIGHUP] {
        sys::install(signal);
    }
    thread::Builder::new()
        .name("argos-signals".into())
        .spawn(move || {
            let mut byte = [0u8; 1];
            while let Ok(1) = reader.read(&mut byte) {
                on_signal(i32::from(byte[0]));
            }
        })?;
    Ok(())
}

#[cfg(not(unix))]
pub fn watch_signals(_on_signal: impl Fn(i32) + Send + 'static) -> io::Result<()> {
    Ok(())
}

/// Kill every process of the sidecar's group at once (second signal).
pub fn kill_now() {
    let pid = PID.load(Ordering::SeqCst);
    if pid > 0 {
        STOPPING.store(true, Ordering::SeqCst);
        sys::kill_group(pid);
    }
}

/// The few libc calls the stop paths need, declared here: the owner's W8
/// decision allows no crate beyond tauri, tauri-build and the window-state
/// plugin.
#[cfg(unix)]
mod sys {
    use std::ffi::{c_int, c_void};
    use std::sync::atomic::{AtomicI32, Ordering};

    pub const SIGHUP: c_int = 1;
    pub const SIGINT: c_int = 2;
    pub const SIGKILL: c_int = 9;
    pub const SIGTERM: c_int = 15;

    /// Write end of the signal watcher's socket pair, -1 before it exists.
    pub static WAKE_FD: AtomicI32 = AtomicI32::new(-1);

    extern "C" {
        fn kill(pid: i32, signal: c_int) -> c_int;
        // sighandler_t is a pointer-sized function pointer on macOS and Linux.
        fn signal(signum: c_int, handler: usize) -> usize;
        fn write(fd: c_int, buf: *const c_void, count: usize) -> isize;
    }

    extern "C" fn on_signal(signum: c_int) {
        let fd = WAKE_FD.load(Ordering::Relaxed);
        if fd >= 0 {
            let byte = signum as u8;
            // SAFETY: write(2) is async-signal-safe; the fd stays open for
            // the life of the process (its owner was leaked on purpose).
            unsafe {
                write(fd, (&byte as *const u8).cast(), 1);
            }
        }
    }

    pub fn install(signum: c_int) {
        // SAFETY: the handler only touches an atomic and calls write(2).
        unsafe {
            signal(signum, on_signal as extern "C" fn(c_int) as usize);
        }
    }

    pub fn terminate(pid: i32) {
        // SAFETY: plain kill(2) on a pid this process spawned.
        unsafe {
            kill(pid, SIGTERM);
        }
    }

    pub fn kill_group(pid: i32) {
        // SAFETY: the sidecar leads its own process group (process_group(0)).
        unsafe {
            kill(-pid, SIGKILL);
        }
    }
}

/// Windows has no signals: taskkill ends the process tree. Not built or
/// tested yet (Windows is not a release target of W8).
#[cfg(windows)]
mod sys {
    pub fn terminate(pid: i32) {
        let _ = std::process::Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/T"])
            .status();
    }

    pub fn kill_group(pid: i32) {
        let _ = std::process::Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .status();
    }
}
