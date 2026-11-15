//! ARGOS desktop shell (W8 groundwork): one Tauri window around the web UI,
//! with the headless ARGOS server as its sidecar.
//!
//! Start-up: the window opens at once on the shell's "Starting the ARGOS
//! server…" page (`argos:` scheme, pages.rs); a helper thread starts the
//! sidecar (sidecar.rs) and reads `ARGOS_PORT` / `ARGOS_TOKEN` from its
//! stdout within `sidecar::STARTUP_TIMEOUT`; the window then loads the bundled
//! web UI with `?api=http://127.0.0.1:<port>&token=<token>`. A server that is
//! missing, cannot be launched, stops or stays silent leaves the failure page
//! (cause, its last stderr lines, log folder, Copy details, Open log folder,
//! Retry). A server that stops later brings the same page back.
//!
//! Shutdown: the sidecar is stopped (SIGTERM, `sidecar::STOP_GRACE` for its
//! graceful shutdown, then SIGKILL of its process group) when the app exits
//! (window closed, Cmd+Q, `quit app`), on SIGTERM / SIGINT / SIGHUP, and from
//! the panic hook. A SIGKILL of the shell cannot be caught: see the open W8
//! item about a server-side parent watch (stdin is kept open for it).
//!
//! Environment, for development and tests only:
//! - `ARGOS_SIDECAR_ARGS`: extra server arguments, split on whitespace
//!   (e.g. `--simulator`). The server also reads `ARGOS_CONFIG_DIR` and
//!   `ARGOS_LOG_DIR`, which the sidecar inherits.
//! - `ARGOS_DESKTOP_TEST_PANIC` (debug builds only): panic on the start-up
//!   thread once the server is ready. The hook must stop the sidecar; a debug
//!   build unwinds that thread only (no crash report), a release build would
//!   abort after the same hook.
//!
//! Not yet here (W8 proper, after W7): the A7 shutdown with the Quit
//! confirmation and the shutdown scrim, A12 reveal, the custom title bar, the
//! native app menu, the crash notice inside the UI, and the web UI's own
//! start-up stage replacing pages.rs.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod pages;
mod sidecar;

use std::path::PathBuf;
use std::process::ChildStdin;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use tauri::http::{header, Request, Response, StatusCode};
use tauri::utils::config::FrontendDist;
use tauri::webview::NewWindowResponse;
use tauri::window::Color;
use tauri::{AppHandle, Manager, RunEvent, Url, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_window_state::StateFlags;

/// The one window (D27: no multi-window in v1).
const MAIN: &str = "main";
/// Scheme of the shell's own pages (pages.rs).
const SCHEME: &str = "argos";
/// The reference size of the UI (web/spec/01-shell-and-global.md 2.4.8).
const DEFAULT_SIZE: (f64, f64) = (1440.0, 900.0);
const MIN_SIZE: (f64, f64) = (1024.0, 700.0);
/// Observatory `--bg` (web/src/design/tokens.css), behind the first paint.
const BACKGROUND: Color = Color(0x19, 0x1b, 0x1f, 0xff);

enum Phase {
    Starting,
    Ready,
    Failed(pages::Failure),
    Quitting,
}

struct Shell {
    phase: Mutex<Phase>,
    /// Start attempts so far; a late event of an older attempt is ignored.
    attempt: AtomicU64,
    /// The sidecar's stdin, held open while it runs.
    stdin: Mutex<Option<ChildStdin>>,
    launched: Instant,
}

fn main() {
    let launched = Instant::now();
    install_panic_hook();

    let app = tauri::Builder::default()
        .plugin(
            tauri_plugin_window_state::Builder::new()
                // Geometry only: visibility is the shell's, and decorations
                // will be the custom title bar's (W8).
                .with_state_flags(
                    StateFlags::SIZE
                        | StateFlags::POSITION
                        | StateFlags::MAXIMIZED
                        | StateFlags::FULLSCREEN,
                )
                .build(),
        )
        .register_uri_scheme_protocol(SCHEME, |ctx, request| serve(ctx.app_handle(), &request))
        .manage(Shell {
            phase: Mutex::new(Phase::Starting),
            attempt: AtomicU64::new(0),
            stdin: Mutex::new(None),
            launched,
        })
        .setup(|app| {
            let handle = app.handle().clone();
            if let Err(err) = sidecar::watch_signals(move |signal| on_signal(&handle, signal)) {
                eprintln!("argos-desktop: no signal watch ({err})");
            }
            open_main_window(app.handle())?;
            start_server(app.handle());
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("the ARGOS desktop app could not be built");

    app.run(|app, event| {
        if let RunEvent::Exit = event {
            quit(app);
        }
    });
}

/// Any panic stops the sidecar (lock-free), after the default report. Release
/// builds then abort (Cargo.toml: panic = "abort").
fn install_panic_hook() {
    let default_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        default_hook(info);
        sidecar::stop(Duration::from_secs(5));
    }));
}

/// SIGTERM, SIGINT or SIGHUP: stop the server, then exit with 128 + signal.
/// A second signal while stopping kills the server's group and exits at once.
fn on_signal(app: &AppHandle, signal: i32) {
    static STOPPING: AtomicBool = AtomicBool::new(false);
    if STOPPING.swap(true, Ordering::SeqCst) {
        sidecar::kill_now();
        std::process::exit(128 + signal);
    }
    eprintln!("argos-desktop: signal {signal}, stopping the server");
    set_quitting(app);
    sidecar::stop(sidecar::STOP_GRACE);
    app.exit(128 + signal);
}

/// The app is exiting (last window closed, Cmd+Q, `quit app`, app.exit).
fn quit(app: &AppHandle) {
    set_quitting(app);
    for window in app.webview_windows().values() {
        let _ = window.hide();
    }
    sidecar::stop(sidecar::STOP_GRACE);
}

fn set_quitting(app: &AppHandle) {
    let shell = app.state::<Shell>();
    let mut phase = shell
        .phase
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    *phase = Phase::Quitting;
}

fn open_main_window(app: &AppHandle) -> tauri::Result<()> {
    let (width, height) = initial_size(app);
    let dev_origin = dev_url(app).map(|url| url.origin());
    let window = WebviewWindowBuilder::new(app, MAIN, WebviewUrl::CustomProtocol(page_url("/")))
        .title("ARGOS")
        .inner_size(width, height)
        .min_inner_size(MIN_SIZE.0, MIN_SIZE.1)
        .center()
        .theme(Some(tauri::Theme::Dark))
        .background_color(BACKGROUND)
        // Shown below, once the window-state plugin has restored the geometry.
        .visible(false)
        // The window only ever shows the UI or the shell's pages; any other
        // page (a link to the documentation, a dropped file) would replace
        // the UI with no way back.
        .on_navigation(move |url| {
            let in_app = match url.scheme() {
                "tauri" | "argos" | "about" | "blob" => true,
                _ => {
                    let origin = url.origin();
                    Some(&origin) == dev_origin.as_ref()
                        || matches!(url.host_str(), Some("tauri.localhost" | "argos.localhost"))
                }
            };
            if !in_app {
                open_outside(url);
            }
            in_app
        })
        .on_new_window(|url, _features| {
            open_outside(&url);
            NewWindowResponse::Deny
        })
        .build()?;
    window.show()?;
    window.set_focus()?;
    Ok(())
}

/// The reference size, shrunk to fit the primary monitor's work area.
fn initial_size(app: &AppHandle) -> (f64, f64) {
    let Ok(Some(monitor)) = app.primary_monitor() else {
        return DEFAULT_SIZE;
    };
    let scale = monitor.scale_factor();
    let area = monitor.work_area().size;
    // Leave room for the title bar and the window shadow.
    let fit_width = area.width as f64 / scale - 16.0;
    let fit_height = area.height as f64 / scale - 40.0;
    (
        DEFAULT_SIZE.0.min(fit_width).max(MIN_SIZE.0),
        DEFAULT_SIZE.1.min(fit_height).max(MIN_SIZE.1),
    )
}

/// Start the server on a helper thread, then load the UI or the failure page.
fn start_server(app: &AppHandle) {
    let shell = app.state::<Shell>();
    let attempt = shell.attempt.fetch_add(1, Ordering::SeqCst) + 1;
    if let Ok(mut phase) = shell.phase.lock() {
        if matches!(*phase, Phase::Quitting) {
            return;
        }
        *phase = Phase::Starting;
    }
    let app = app.clone();
    thread::spawn(move || {
        let tail = sidecar::Tail::default();
        let (exit_app, exit_tail) = (app.clone(), tail.clone());
        let result = sidecar::start(&extra_args(), tail.clone(), move |status, on_purpose| {
            if !on_purpose {
                server_stopped(&exit_app, attempt, &status, &exit_tail);
            }
        });
        let shell = app.state::<Shell>();
        match result {
            Ok(ready) => {
                eprintln!(
                    "argos-desktop: server ready on 127.0.0.1:{} after {} ms ({} ms since launch)",
                    ready.port,
                    ready.elapsed.as_millis(),
                    shell.launched.elapsed().as_millis()
                );
                if let Ok(mut phase) = shell.phase.lock() {
                    if shell.attempt.load(Ordering::SeqCst) != attempt
                        || matches!(*phase, Phase::Quitting)
                    {
                        return;
                    }
                    *phase = Phase::Ready;
                }
                if let Ok(mut stdin) = shell.stdin.lock() {
                    *stdin = ready.stdin;
                }
                if let Some(window) = app.get_webview_window(MAIN) {
                    if let Err(err) = window.navigate(ui_url(&app, ready.port, &ready.token)) {
                        eprintln!("argos-desktop: cannot load the UI: {err}");
                    }
                }
                #[cfg(debug_assertions)]
                if std::env::var_os("ARGOS_DESKTOP_TEST_PANIC").is_some() {
                    panic!("ARGOS_DESKTOP_TEST_PANIC");
                }
            }
            Err(err) => {
                let cause = err.cause();
                eprintln!("argos-desktop: {cause}");
                fail(&app, attempt, "ARGOS could not start", cause, tail.text());
            }
        }
    });
}

/// The server ended without the shell asking: after start-up, that is a
/// crash; during start-up, `sidecar::start` reports it instead.
fn server_stopped(app: &AppHandle, attempt: u64, status: &str, tail: &sidecar::Tail) {
    let shell = app.state::<Shell>();
    let was_ready = shell.attempt.load(Ordering::SeqCst) == attempt
        && shell
            .phase
            .lock()
            .map(|p| matches!(*p, Phase::Ready))
            .unwrap_or(false);
    if was_ready {
        fail(
            app,
            attempt,
            "The ARGOS server stopped",
            format!("The ARGOS server ended unexpectedly ({status}). Retry starts it again."),
            tail.text(),
        );
    }
}

fn fail(app: &AppHandle, attempt: u64, title: &'static str, cause: String, details: String) {
    let shell = app.state::<Shell>();
    if let Ok(mut phase) = shell.phase.lock() {
        if shell.attempt.load(Ordering::SeqCst) != attempt || matches!(*phase, Phase::Quitting) {
            return;
        }
        *phase = Phase::Failed(pages::Failure {
            title,
            cause,
            details,
            log_dir: tilde(&log_dir()),
        });
    }
    if let Some(window) = app.get_webview_window(MAIN) {
        let _ = window.navigate(page_url("/"));
    }
}

/// The shell's pages and their two actions.
fn serve(app: &AppHandle, request: &Request<Vec<u8>>) -> Response<Vec<u8>> {
    let version = app.package_info().version.to_string();
    match (request.method().as_str(), request.uri().path()) {
        ("GET", "/" | "/index.html") => {
            let shell = app.state::<Shell>();
            let html = match shell.phase.lock().as_deref() {
                Ok(Phase::Failed(failure)) => pages::failure(&version, failure),
                _ => pages::starting(&version),
            };
            Response::builder()
                .header(header::CONTENT_TYPE, "text/html; charset=utf-8")
                .header(header::CACHE_CONTROL, "no-store")
                .header(
                    header::CONTENT_SECURITY_POLICY,
                    "default-src 'none'; style-src 'unsafe-inline'; \
                     script-src 'unsafe-inline'; connect-src 'self'",
                )
                .body(html.into_bytes())
                .unwrap_or_default()
        }
        ("POST", "/retry") => {
            let failed = app
                .state::<Shell>()
                .phase
                .lock()
                .map(|p| matches!(*p, Phase::Failed(_)))
                .unwrap_or(false);
            if failed {
                start_server(app);
            }
            empty(StatusCode::NO_CONTENT)
        }
        ("POST", "/open-log-folder") => {
            open_outside_path(&log_dir());
            empty(StatusCode::NO_CONTENT)
        }
        _ => empty(StatusCode::NOT_FOUND),
    }
}

fn empty(status: StatusCode) -> Response<Vec<u8>> {
    Response::builder()
        .status(status)
        .body(Vec::new())
        .unwrap_or_default()
}

/// A page of the `argos:` scheme (Windows serves custom schemes over http).
fn page_url(path: &str) -> Url {
    let url = if cfg!(windows) {
        format!("http://{SCHEME}.localhost{path}")
    } else {
        format!("{SCHEME}://localhost{path}")
    };
    Url::parse(&url).expect("valid page URL")
}

fn dev_url(app: &AppHandle) -> Option<Url> {
    if tauri::is_dev() {
        app.config().build.dev_url.clone()
    } else {
        None
    }
}

/// The web UI's index.html with the server's address and token.
fn ui_url(app: &AppHandle, port: u16, token: &str) -> Url {
    let base = dev_url(app)
        .or_else(|| match app.config().build.frontend_dist.as_ref() {
            Some(FrontendDist::Url(url)) => Some(url.clone()),
            _ => None,
        })
        .unwrap_or_else(|| {
            let origin = if cfg!(windows) {
                "http://tauri.localhost/"
            } else {
                "tauri://localhost/"
            };
            Url::parse(origin).expect("valid app URL")
        });
    let mut url = base.join("index.html").unwrap_or(base);
    url.query_pairs_mut()
        .append_pair("api", &format!("http://127.0.0.1:{port}"))
        .append_pair("token", token);
    url
}

fn extra_args() -> Vec<String> {
    std::env::var("ARGOS_SIDECAR_ARGS")
        .map(|args| args.split_whitespace().map(str::to_owned).collect())
        .unwrap_or_default()
}

/// The server's log folder, as argos/server/runtime.py `default_log_dir`
/// (`$ARGOS_LOG_DIR` with `~` expanded, else
/// support_bundle.diagnostics_directory).
fn log_dir() -> PathBuf {
    let home = home();
    if let Some(dir) = std::env::var("ARGOS_LOG_DIR")
        .ok()
        .filter(|d| !d.is_empty())
    {
        return match dir.strip_prefix('~') {
            Some(rest) if rest.is_empty() || rest.starts_with('/') => {
                home.join(rest.trim_start_matches('/'))
            }
            _ => PathBuf::from(dir),
        };
    }
    if cfg!(target_os = "macos") {
        return home.join("Library/Logs/Argos");
    }
    match std::env::var_os("XDG_STATE_HOME").filter(|d| !d.is_empty()) {
        Some(state) => PathBuf::from(state).join("argos"),
        None => home.join(".local/state/argos"),
    }
}

fn home() -> PathBuf {
    std::env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_default()
}

/// A path as the spec writes it: `~/Library/Logs/Argos` (2.3.8).
fn tilde(path: &std::path::Path) -> String {
    let home = home();
    match path.strip_prefix(&home) {
        Ok(rest) if !home.as_os_str().is_empty() => {
            if rest.as_os_str().is_empty() {
                "~".into()
            } else {
                format!("~/{}", rest.display())
            }
        }
        _ => path.display().to_string(),
    }
}

/// A web link (documentation, website) in the system browser, never in the
/// app's window. Only http(s) and mailto, and never the local server.
fn open_outside(url: &Url) {
    let loopback = matches!(url.host_str(), Some("127.0.0.1" | "localhost" | "[::1]"));
    if matches!(url.scheme(), "http" | "https" | "mailto") && !loopback {
        open_with_system(url.as_str());
    } else {
        eprintln!("argos-desktop: navigation to {} blocked", url.scheme());
    }
}

fn open_outside_path(path: &std::path::Path) {
    open_with_system(&path.to_string_lossy());
}

/// The platform's opener (no plugin: owner decision W8). The argument is a
/// single argv entry, never parsed by a shell.
fn open_with_system(target: &str) {
    let opener = if cfg!(target_os = "macos") {
        "open"
    } else if cfg!(windows) {
        "explorer"
    } else {
        "xdg-open"
    };
    let target = target.to_owned();
    // Waited on a helper thread, so no zombie is left behind.
    thread::spawn(move || {
        if let Err(err) = std::process::Command::new(opener).arg(&target).status() {
            eprintln!("argos-desktop: {opener} failed: {err}");
        }
    });
}
