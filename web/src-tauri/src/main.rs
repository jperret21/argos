//! ARGOS desktop shell (W8): one Tauri window around the web UI, with the
//! headless ARGOS server as its sidecar.
//!
//! Start-up (web/spec/01-shell-and-global.md 2.3.8): the window opens on the
//! bundled web UI with no server address ("waiting": the UI's start-up screen,
//! in the observer's theme, shows "Starting the ARGOS server…") and is shown
//! once that page has loaded. Meanwhile a helper thread starts the one-dir
//! sidecar (sidecar.rs) and reads `ARGOS_PORT` / `ARGOS_TOKEN` from its stdout
//! within `sidecar::STARTUP_TIMEOUT`; the shell then sends the UI
//! `argos://server-state` "ready" with the address and token, and the UI
//! reloads itself on them. A server that is missing, cannot be launched,
//! stops or stays silent is "failed" (cause, last stderr lines, log folder:
//! the UI's start-up failure, Retry = `argos://restart-server`); a server
//! that ends later, unasked, is "stopped" (the UI's crash notice). A page that
//! never attaches gets the old behaviour: the UI loaded with `?api=&token=`
//! once the server is ready, the shell's own failure page (pages.rs).
//!
//! Quit (A7, 01 2.3.7): ⌘Q (the menu's Quit), a close request, the Dock's
//! Quit and `quit app` (`terminate:`, appkit.rs) and a last window going away
//! (`ExitRequested`) are all prevented and become one quit request. With the
//! UI attached and the server ready, it goes to the UI
//! (`argos://quit-requested`), whose Quit dialog decides (busy refusal,
//! force), asks the server to shut down, shows the scrim, then sends
//! `argos://quit`; the shell hides the window, lets the server end, stops it
//! if it has not, and exits. Otherwise (start-up, failure) the shell quits at
//! once.
//!
//! Shell and UI: the contract is web/src/lib/shell/desktop/bridge.ts (Tauri
//! events, JSON payloads; the UI uses `__TAURI_INTERNALS__`, no npm package):
//! - shell → UI: `argos://server-state` {phase: "starting" | "ready" |
//!   "failed" | "stopped", api, token, title, cause, details, log_dir,
//!   status, version} on every change and in answer to `argos://ui-ready`;
//!   `argos://quit-requested` {source}; `argos://menu` {id} (menu.rs).
//! - UI → shell: `argos://ui-ready` (attach: quit requests and menu items go
//!   to this page from now on; a page load detaches), `argos://quit`,
//!   `argos://restart-server`, `argos://reset-window-state`,
//!   `argos://open-log-folder`, `argos://reveal` {path}.
//! - Downloads (the UI's exports: `<a download>` of a blob): saved in the
//!   Downloads folder under a free name, then `argos://download` {status:
//!   "saved" | "failed", path, name} to the UI (its toast, Reveal in Finder).
//!   Without a handler WKWebView cancels every download (wry).
//! - Title bar (Q-G14: the UI draws it, in every theme): the window plugin's
//!   `start_dragging`, `minimize`, `toggle_maximize` (capabilities/default.json).
//!   Decorations are off; on macOS the borderless window gets the system's
//!   rounded corners and shadow (appkit.rs `round_corners`, square in full
//!   screen) without the grey outline macOS draws around titled windows.
//! - Window: `argos://window` {fullscreen, double_click} on every full-screen
//!   change and in answer to `argos://ui-ready` (the UI hides its title bar in
//!   full screen; double_click is the system's title-bar setting);
//!   `argos://toggle-fullscreen` from the UI; `argos://theme` {theme, bg}: the
//!   window is painted with the theme's `--bg` behind the page, and the
//!   shell's own pages follow Night Red.
//!
//! Shutdown paths: the sidecar is stopped (SIGTERM, `sidecar::STOP_GRACE`
//! for its graceful shutdown, then SIGKILL of its process group) when the app
//! exits, on SIGTERM / SIGINT / SIGHUP, and from the panic hook. A SIGKILL of
//! the shell cannot be caught: the server then ends by itself when its stdin
//! closes (`--exit-on-stdin-eof`).
//!
//! Environment: the server reads `ARGOS_CONFIG_DIR` and `ARGOS_LOG_DIR`,
//! which the sidecar inherits. Dev builds only (identifier ending in `.dev`,
//! tauri.dev.conf.json; a release build ignores them):
//! - `ARGOS_SIDECAR`: the server executable to run instead of the bundled
//!   one (e.g. a script running `.venv/bin/python -m argos.server "$@"`).
//! - `ARGOS_SIDECAR_ARGS`: extra server arguments, split on whitespace
//!   (e.g. `--simulator`), placed before the shell's own (`--host 127.0.0.1
//!   --port 0 --desktop --exit-on-stdin-eof`, which therefore win).
//! - `ARGOS_DESKTOP_UI_PAGE` opens another page of the bundled UI instead of
//!   index.html (a test page); `ARGOS_DESKTOP_TEST_PANIC` panics on the
//!   start-up thread once the server is ready (the hook must stop the
//!   sidecar; release profiles then abort).
//!
//! Diagnostics go to stderr through [`log!`], never `eprintln!`: that panics
//! when stderr is gone (a closed terminal or pipe), and a release build
//! aborts on a panic, stopping the server and any running sequence.
//!
//! Start-up time: the first sidecar is spawned at the top of `main`, before
//! Tauri builds its event loop and the window (about 0.2 s sooner).

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

/// One line on stderr, ignoring a write error (EPIPE: the terminal or pipe is
/// gone). Defined before the modules so that they all use it.
macro_rules! log {
    ($($arg:tt)*) => {
        $crate::log_line(::std::format_args!($($arg)*))
    };
}

#[cfg(target_os = "macos")]
mod appkit;
mod json;
#[cfg(target_os = "macos")]
mod menu;
mod pages;
mod sidecar;

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::process::ChildStdin;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{mpsc, Mutex, MutexGuard, OnceLock};
use std::thread;
use std::time::{Duration, Instant};

use tauri::http::{header, Request, Response, StatusCode};
use tauri::utils::config::FrontendDist;
use tauri::webview::{DownloadEvent, NewWindowResponse, PageLoadEvent};
use tauri::window::Color;
use tauri::{
    AppHandle, Emitter, Listener, LogicalSize, Manager, RunEvent, Url, WebviewUrl,
    WebviewWindowBuilder, WindowEvent,
};
use tauri_plugin_window_state::{AppHandleExt, StateFlags};

/// The one window (D27: no multi-window in v1).
const MAIN: &str = "main";
/// Scheme of the shell's own pages (pages.rs).
const SCHEME: &str = "argos";
/// The reference size of the UI (web/spec/01-shell-and-global.md 2.4.8).
const DEFAULT_SIZE: (f64, f64) = (1440.0, 900.0);
const MIN_SIZE: (f64, f64) = (1024.0, 700.0);
/// Behind the first paint: black, allowed in every theme (Night Red's rule A
/// fails on Observatory's `--bg`); the UI then sends its theme's `--bg`
/// (`argos://theme`).
const BACKGROUND: Color = Color(0, 0, 0, 0xff);
/// The window shows once its first page has loaded, or after this.
const SHOW_FALLBACK: Duration = Duration::from_secs(3);
/// A start-up failure or a crash with no UI attached: how long a loading UI
/// may take to attach before the shell's own failure page replaces it.
const ATTACH_WAIT: Duration = Duration::from_secs(5);
/// After the UI's `argos://quit`: how long a server finishing its A7
/// shutdown (it exits about 0.3 s after its last stage) may take to end by
/// itself before the shell stops it.
const QUIT_SETTLE: Duration = Duration::from_secs(3);

/// Event names (web/src/lib/shell/desktop/bridge.ts `SHELL_EVENTS`).
mod events {
    pub const SERVER_STATE: &str = "argos://server-state";
    pub const QUIT_REQUESTED: &str = "argos://quit-requested";
    // The native app menu exists on macOS only (`mod menu`).
    #[cfg(target_os = "macos")]
    pub const MENU: &str = "argos://menu";
    pub const UI_READY: &str = "argos://ui-ready";
    pub const QUIT: &str = "argos://quit";
    pub const RESTART_SERVER: &str = "argos://restart-server";
    pub const RESET_WINDOW_STATE: &str = "argos://reset-window-state";
    pub const OPEN_LOG_FOLDER: &str = "argos://open-log-folder";
    pub const REVEAL: &str = "argos://reveal";
    pub const DOWNLOAD: &str = "argos://download";
    pub const WINDOW: &str = "argos://window";
    pub const TOGGLE_FULLSCREEN: &str = "argos://toggle-fullscreen";
    pub const THEME: &str = "argos://theme";
}

enum Phase {
    Starting,
    Ready {
        port: u16,
        token: String,
    },
    /// The server did not start.
    Failed(pages::Failure),
    /// The server ended, unasked, after it was ready.
    Stopped(pages::Failure),
    Quitting,
}

struct Shell {
    phase: Mutex<Phase>,
    /// Start attempts so far; a late event of an older attempt is ignored.
    attempt: AtomicU64,
    /// The sidecar's stdin, held open while it runs.
    stdin: Mutex<Option<ChildStdin>>,
    launched: Instant,
    /// The page now loaded sent `argos://ui-ready`.
    attached: AtomicBool,
    /// The window has been shown.
    shown: AtomicBool,
    /// Downloads under way: their URL and where they are saved (macOS does
    /// not say where at the end).
    downloads: Mutex<HashMap<String, PathBuf>>,
    /// The UI's theme (`argos://theme`), for the shell's own pages.
    theme: Mutex<String>,
    /// The window is in full screen (last state sent to the UI).
    fullscreen: AtomicBool,
    /// The system's title-bar double-click setting: "zoom", "minimize", "none".
    double_click: Mutex<&'static str>,
}

/// The first server start, begun at the top of `main` and collected by the
/// first [`start_server`].
struct EarlyStart {
    result: mpsc::Receiver<Result<sidecar::Ready, sidecar::StartError>>,
    tail: sidecar::Tail,
}

static EARLY: Mutex<Option<EarlyStart>> = Mutex::new(None);
/// The app, once built (the first server's exit callback may run before).
static APP: OnceLock<AppHandle> = OnceLock::new();
/// "Quit now" (the scrim, past 20 s): stop the server at once on exit.
static QUIT_NOW: AtomicBool = AtomicBool::new(false);

/// [`log!`]'s writer.
fn log_line(args: std::fmt::Arguments<'_>) {
    use std::io::Write;
    let _ = writeln!(std::io::stderr().lock(), "{args}");
}

fn main() {
    let launched = Instant::now();
    install_panic_hook();
    let context = tauri::generate_context!();
    spawn_early(context.config().identifier.ends_with(".dev"));

    let builder = tauri::Builder::default()
        // menu.rs replaces Tauri's default menu, whose Quit would terminate
        // the app without asking.
        .enable_macos_default_menu(false)
        .plugin(
            tauri_plugin_window_state::Builder::new()
                .with_state_flags(state_flags())
                .build(),
        )
        .register_uri_scheme_protocol(SCHEME, |ctx, request| serve(ctx.app_handle(), &request))
        .manage(Shell {
            phase: Mutex::new(Phase::Starting),
            attempt: AtomicU64::new(0),
            stdin: Mutex::new(None),
            launched,
            attached: AtomicBool::new(false),
            shown: AtomicBool::new(false),
            downloads: Mutex::new(HashMap::new()),
            theme: Mutex::new(String::new()),
            fullscreen: AtomicBool::new(false),
            double_click: Mutex::new("zoom"),
        })
        .on_window_event(|window, event| {
            if window.label() != MAIN {
                return;
            }
            match event {
                WindowEvent::CloseRequested { api, .. } => {
                    api.prevent_close();
                    request_quit(window.app_handle(), "window");
                }
                // Entering or leaving full screen resizes the window.
                WindowEvent::Resized(_) => check_fullscreen(window.app_handle()),
                _ => {}
            }
        })
        .on_page_load(|webview, payload| {
            if webview.label() != MAIN {
                return;
            }
            let app = webview.app_handle();
            match payload.event() {
                // A new page has not attached yet (the UI reloading on its
                // server, the shell's pages): until it does, the shell
                // answers quit requests itself.
                PageLoadEvent::Started => {
                    app.state::<Shell>().attached.store(false, Ordering::SeqCst);
                }
                PageLoadEvent::Finished => show_main(app),
            }
        })
        .setup(|app| {
            let _ = APP.set(app.handle().clone());
            let handle = app.handle().clone();
            if let Err(err) = sidecar::watch_signals(move |signal| on_signal(&handle, signal)) {
                log!("argos-desktop: no signal watch ({err})");
            }
            listen_to_ui(app.handle());
            #[cfg(target_os = "macos")]
            {
                let product = app.package_info().name.clone();
                app.set_menu(menu::build(app.handle(), &product)?)?;
                let handle = app.handle().clone();
                if !appkit::route_terminate(move || allow_terminate(&handle)) {
                    log!("argos-desktop: terminate requests are not routed (Quit dialog bypassed)");
                }
                read_double_click(app.handle());
            }
            open_main_window(app.handle())?;
            start_server(app.handle());
            let handle = app.handle().clone();
            thread::spawn(move || {
                thread::sleep(SHOW_FALLBACK);
                show_main(&handle);
            });
            Ok(())
        });
    #[cfg(target_os = "macos")]
    let builder = builder.on_menu_event(|app, event| on_menu(app, event.id().as_ref()));

    let app = builder
        .build(context)
        .expect("the ARGOS desktop app could not be built");

    app.run(|app, event| match event {
        // A last window going away without the shell deciding (code None;
        // the shell's own exits carry a code).
        RunEvent::ExitRequested {
            code: None, api, ..
        } if !is_quitting(app) => {
            api.prevent_exit();
            request_quit(app, "app");
        }
        RunEvent::Exit => quit(app),
        _ => {}
    });
}

/// Geometry only: visibility and the window's style are the shell's (Q-G14).
fn state_flags() -> StateFlags {
    StateFlags::SIZE | StateFlags::POSITION | StateFlags::MAXIMIZED | StateFlags::FULLSCREEN
}

fn lock<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

/// A dev build (tauri.dev.conf.json): test hooks are honoured.
fn dev_build(app: &AppHandle) -> bool {
    app.config().identifier.ends_with(".dev")
}

fn is_quitting(app: &AppHandle) -> bool {
    matches!(*lock(&app.state::<Shell>().phase), Phase::Quitting)
}

fn attached(app: &AppHandle) -> bool {
    app.state::<Shell>().attached.load(Ordering::SeqCst)
}

/// The UI is attached and its server runs: the UI decides a quit.
fn routes_to_ui(app: &AppHandle) -> bool {
    let ready = matches!(*lock(&app.state::<Shell>().phase), Phase::Ready { .. });
    ready && attached(app)
}

fn show_main(app: &AppHandle) {
    if app.state::<Shell>().shown.swap(true, Ordering::SeqCst) {
        return;
    }
    if let Some(window) = app.get_webview_window(MAIN) {
        let _ = window.show();
        let _ = window.set_focus();
    }
}

// -- The UI's events --------------------------------------------------------------------

/// Each handler runs on the main thread, never in the listener itself: Tauri
/// calls listeners with its listener table locked, and a window call made
/// there (the window-state plugin's save during a resize) would wait on a
/// main thread that waits on that lock.
fn listen_to_ui(app: &AppHandle) {
    let on = |event: &'static str, handler: fn(&AppHandle, &str)| {
        let handle = app.clone();
        app.listen_any(event, move |e| {
            let (app, payload) = (handle.clone(), e.payload().to_owned());
            let run = move || handler(&app, &payload);
            if let Err(err) = handle.run_on_main_thread(run) {
                log!("argos-desktop: {event} dropped: {err}");
            }
        });
    };
    on(events::UI_READY, |app, _| {
        let shell = app.state::<Shell>();
        if !shell.attached.swap(true, Ordering::SeqCst) {
            log!(
                "argos-desktop: UI attached {} ms after launch",
                shell.launched.elapsed().as_millis()
            );
        }
        show_main(app);
        emit_state(app);
        emit_window(app);
    });
    on(events::QUIT, ui_quit);
    on(events::RESTART_SERVER, |app, _| {
        let ended = matches!(
            *lock(&app.state::<Shell>().phase),
            Phase::Failed(_) | Phase::Stopped(_)
        );
        if ended {
            start_server(app);
        }
    });
    on(events::RESET_WINDOW_STATE, |app, _| {
        if let Err(err) = reset_window(app) {
            log!("argos-desktop: cannot reset the window: {err}");
        }
    });
    on(
        events::OPEN_LOG_FOLDER,
        |_, _| open_outside_path(&log_dir()),
    );
    on(events::REVEAL, |_, payload| {
        match json::get_string(payload, "path") {
            Some(path) => reveal(Path::new(&path)),
            None => log!("argos-desktop: reveal without a path"),
        }
    });
    on(events::TOGGLE_FULLSCREEN, |app, _| {
        if let Some(window) = app.get_webview_window(MAIN) {
            let on = window.is_fullscreen().unwrap_or(false);
            if let Err(err) = window.set_fullscreen(!on) {
                log!("argos-desktop: cannot change full screen: {err}");
            }
        }
        // The transition is animated: look again once it has ended.
        let app = app.clone();
        thread::spawn(move || {
            thread::sleep(Duration::from_millis(900));
            let handle = app.clone();
            let _ = app.run_on_main_thread(move || check_fullscreen(&handle));
        });
    });
    on(events::THEME, |app, payload| {
        let theme = json::get_string(payload, "theme").unwrap_or_default();
        let bg = json::get_string(payload, "bg").and_then(|bg| parse_hex_color(&bg));
        *lock(&app.state::<Shell>().theme) = theme;
        if let (Some(color), Some(window)) = (bg, app.get_webview_window(MAIN)) {
            if let Err(err) = window.set_background_color(Some(color)) {
                log!("argos-desktop: cannot paint the window: {err}");
            }
            // The window itself stays clear outside its rounded content.
            let fullscreen = app.state::<Shell>().fullscreen.load(Ordering::SeqCst);
            set_corners(&window, fullscreen);
        }
    });
}

/// "#rrggbb" (the UI's `--bg`).
fn parse_hex_color(text: &str) -> Option<Color> {
    let hex = text.trim().strip_prefix('#')?;
    if hex.len() != 6 || !hex.chars().all(|c| c.is_ascii_hexdigit()) {
        return None;
    }
    let byte = |at: usize| u8::from_str_radix(&hex[at..at + 2], 16).ok();
    Some(Color(byte(0)?, byte(2)?, byte(4)?, 0xff))
}

/// Full screen changed (a resize, the menu's Enter Full Screen, the UI's
/// toggle): tell the UI, which hides its title bar there.
fn check_fullscreen(app: &AppHandle) {
    let Some(window) = app.get_webview_window(MAIN) else {
        return;
    };
    let on = window.is_fullscreen().unwrap_or(false);
    if app.state::<Shell>().fullscreen.swap(on, Ordering::SeqCst) != on {
        set_corners(&window, on);
        emit_window(app);
    }
}

/// `argos://window`: full screen and the double-click setting.
fn emit_window(app: &AppHandle) {
    let shell = app.state::<Shell>();
    let payload = window_payload(
        shell.fullscreen.load(Ordering::SeqCst),
        *lock(&shell.double_click),
    );
    if let Err(err) = app.emit_str(events::WINDOW, payload) {
        log!("argos-desktop: {} not sent: {err}", events::WINDOW);
    }
}

fn window_payload(fullscreen: bool, double_click: &str) -> String {
    format!(
        "{{\"fullscreen\":{fullscreen},\"double_click\":{}}}",
        json::string(double_click)
    )
}

/// macOS's "double-click a window's title bar to" (Desktop & Dock), read once
/// off the main thread: `AppleActionOnDoubleClick` ("Maximize" by default,
/// "Fill", "Minimize", "None").
#[cfg(target_os = "macos")]
fn read_double_click(app: &AppHandle) {
    let app = app.clone();
    thread::spawn(move || {
        let out = std::process::Command::new("defaults")
            .args(["read", "-g", "AppleActionOnDoubleClick"])
            .output();
        let value = out
            .ok()
            .filter(|o| o.status.success())
            .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_owned());
        let action = double_click_action(value.as_deref());
        *lock(&app.state::<Shell>().double_click) = action;
        if attached(&app) {
            emit_window(&app);
        }
    });
}

// Read on macOS only (the system's title-bar double-click setting); unit-tested everywhere.
#[cfg(any(target_os = "macos", test))]
fn double_click_action(setting: Option<&str>) -> &'static str {
    match setting {
        Some("Minimize") => "minimize",
        Some("None" | "No Action" | "Do Nothing") => "none",
        _ => "zoom",
    }
}

/// `argos://server-state`: the server as the shell sees it now.
fn emit_state(app: &AppHandle) {
    let version = app.package_info().version.to_string();
    let payload = {
        let shell = app.state::<Shell>();
        let phase = lock(&shell.phase);
        let failure = |phase: &str, f: &pages::Failure| {
            json::object(&[
                ("phase", Some(phase)),
                ("title", Some(f.title)),
                ("cause", Some(&f.cause)),
                ("details", Some(&f.details)),
                ("log_dir", Some(&f.log_dir)),
                ("status", f.status.as_deref()),
                ("version", Some(&version)),
            ])
        };
        match &*phase {
            Phase::Quitting => return,
            Phase::Starting => {
                json::object(&[("phase", Some("starting")), ("version", Some(&version))])
            }
            Phase::Ready { port, token } => json::object(&[
                ("phase", Some("ready")),
                ("api", Some(&api_base(*port))),
                ("token", Some(token)),
                ("version", Some(&version)),
            ]),
            Phase::Failed(f) => failure("failed", f),
            Phase::Stopped(f) => failure("stopped", f),
        }
    };
    if let Err(err) = app.emit_str(events::SERVER_STATE, payload) {
        log!("argos-desktop: cannot reach the UI: {err}");
    }
}

/// `argos://quit` {now?}: the observer quit (the server shut down through A7,
/// is gone, or "Quit now"). Hide the window, give a server still finishing
/// its shutdown [`QUIT_SETTLE`], then exit (RunEvent::Exit stops what is
/// left). `now` ("Quit now" on a stuck shutdown): no settle, and the exit
/// stops the server within `sidecar::QUIT_NOW_GRACE`.
fn ui_quit(app: &AppHandle, payload: &str) {
    let now = json::get_bool(payload, "now") == Some(true);
    if now {
        QUIT_NOW.store(true, Ordering::SeqCst);
    }
    let was_ready = {
        let shell = app.state::<Shell>();
        let mut phase = lock(&shell.phase);
        if matches!(*phase, Phase::Quitting) {
            return;
        }
        // Only a ready server can be finishing an A7 shutdown.
        let previous = std::mem::replace(&mut *phase, Phase::Quitting);
        matches!(previous, Phase::Ready { .. })
    };
    log!(
        "argos-desktop: quit from the UI{}",
        if now { " (now)" } else { "" }
    );
    if let Some(window) = app.get_webview_window(MAIN) {
        let _ = window.hide();
    }
    let app = app.clone();
    thread::spawn(move || {
        let began = Instant::now();
        if was_ready && !now && sidecar::wait_exit(QUIT_SETTLE) {
            log!(
                "argos-desktop: server gone {} ms after the UI's quit",
                began.elapsed().as_millis()
            );
        }
        app.exit(0);
    });
}

/// "Reset all layouts" includes the window (01 2.4.7): its reference size,
/// centred, and that state saved.
fn reset_window(app: &AppHandle) -> tauri::Result<()> {
    let Some(window) = app.get_webview_window(MAIN) else {
        return Ok(());
    };
    if window.is_fullscreen()? {
        window.set_fullscreen(false)?;
    }
    if window.is_maximized()? {
        window.unmaximize()?;
    }
    let (width, height) = initial_size(app);
    window.set_size(LogicalSize::new(width, height))?;
    window.center()?;
    // The plugin saves what its resize and move events recorded: save once
    // those have arrived, so a crash before quitting keeps the reset.
    let app = app.clone();
    thread::spawn(move || {
        thread::sleep(Duration::from_millis(600));
        let handle = app.clone();
        let _ = app.run_on_main_thread(move || {
            if let Err(err) = handle.save_window_state(state_flags()) {
                log!("argos-desktop: cannot save the window state: {err}");
            }
        });
    });
    log!("argos-desktop: window reset to its reference size");
    Ok(())
}

/// A12's fallback: the file or folder in the file manager.
fn reveal(path: &Path) {
    if !path.is_absolute() || !path.exists() {
        log!("argos-desktop: reveal of a missing or relative path refused");
        return;
    }
    let (program, args): (&str, Vec<String>) = if cfg!(target_os = "macos") {
        ("open", vec!["-R".into(), path.display().to_string()])
    } else if cfg!(windows) {
        ("explorer", vec![format!("/select,{}", path.display())])
    } else {
        let folder = if path.is_dir() {
            path
        } else {
            path.parent().unwrap_or(path)
        };
        ("xdg-open", vec![folder.display().to_string()])
    };
    run_detached(program, args);
}

// -- Downloads --------------------------------------------------------------------------

/// The UI's exports (log, plot, view, CSV, support bundle): wry has chosen a
/// free name in the Downloads folder; keep it, make sure the folder exists,
/// and tell the UI where the file went once it is written.
fn on_download(app: &AppHandle, event: DownloadEvent<'_>) -> bool {
    let shell = app.state::<Shell>();
    match event {
        DownloadEvent::Requested { url, destination } => {
            if let Some(folder) = destination.parent() {
                if let Err(err) = std::fs::create_dir_all(folder) {
                    log!("argos-desktop: no Downloads folder ({err})");
                    return false;
                }
            }
            log!("argos-desktop: download to {}", tilde(destination));
            lock(&shell.downloads).insert(url.to_string(), destination.clone());
            true
        }
        DownloadEvent::Finished { url, path, success } => {
            let path = path.or_else(|| lock(&shell.downloads).remove(url.as_str()));
            log!(
                "argos-desktop: download {}",
                if success { "saved" } else { "failed" }
            );
            let payload = download_payload(path.as_deref(), success);
            if let Err(err) = app.emit_str(events::DOWNLOAD, payload) {
                log!("argos-desktop: {} not sent: {err}", events::DOWNLOAD);
            }
            true
        }
        _ => true,
    }
}

/// `argos://download`: {status: "saved" | "failed", path, name}.
fn download_payload(path: Option<&Path>, success: bool) -> String {
    let full = path.map(|p| p.display().to_string());
    let name = path
        .and_then(|p| p.file_name())
        .map(|n| n.to_string_lossy().into_owned());
    json::object(&[
        ("status", Some(if success { "saved" } else { "failed" })),
        ("path", full.as_deref()),
        ("name", name.as_deref()),
    ])
}

// -- Quit requests ----------------------------------------------------------------------

/// ⌘Q, a close request, the Dock's Quit, `quit app`: the UI's Quit dialog
/// decides when the UI is up on a running server; otherwise the shell quits
/// at once. Ignored while quitting (a hung UI or server: Force Quit, and the
/// server ends through its stdin).
fn request_quit(app: &AppHandle, source: &'static str) {
    if is_quitting(app) {
        log!("argos-desktop: quit request ({source}) while quitting: ignored");
    } else if routes_to_ui(app) {
        log!("argos-desktop: quit request ({source}) sent to the UI");
        let payload = json::object(&[("source", Some(source))]);
        if let Err(err) = app.emit_str(events::QUIT_REQUESTED, payload) {
            log!("argos-desktop: cannot reach the UI ({err}): quitting");
            set_quitting(app);
            app.exit(0);
        }
    } else {
        log!("argos-desktop: quit request ({source}), no UI to ask: quitting");
        set_quitting(app);
        app.exit(0);
    }
}

/// `applicationShouldTerminate:` (appkit.rs): go ahead only when no UI must
/// decide; the shell's own exit does not go through `terminate:`.
#[cfg(target_os = "macos")]
fn allow_terminate(app: &AppHandle) -> bool {
    if is_quitting(app) {
        // The shell is already ending the app (the scrim may be up).
        return false;
    }
    if routes_to_ui(app) {
        request_quit(app, "app");
        return false;
    }
    log!("argos-desktop: quit request (app), no UI to ask: quitting");
    set_quitting(app);
    true
}

#[cfg(target_os = "macos")]
fn on_menu(app: &AppHandle, id: &str) {
    if id == menu::QUIT {
        request_quit(app, "menu");
    } else if menu::forwarded().any(|item| item == id) {
        if attached(app) {
            let payload = json::object(&[("id", Some(id))]);
            if let Err(err) = app.emit_str(events::MENU, payload) {
                log!("argos-desktop: cannot reach the UI: {err}");
            }
        } else {
            log!("argos-desktop: menu {id} ignored: no UI attached");
        }
    }
}

// -- Life cycle -------------------------------------------------------------------------

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
    log!("argos-desktop: signal {signal}, stopping the server");
    set_quitting(app);
    // The server may take its whole shutdown bound (a real mount): no window
    // meanwhile.
    if let Some(window) = app.get_webview_window(MAIN) {
        let _ = window.hide();
    }
    sidecar::stop(sidecar::STOP_GRACE);
    app.exit(128 + signal);
}

/// The app is exiting (`app.exit`, an allowed `terminate:`): hide the
/// window, stop a server still running.
fn quit(app: &AppHandle) {
    set_quitting(app);
    for window in app.webview_windows().values() {
        let _ = window.hide();
    }
    let grace = if QUIT_NOW.load(Ordering::SeqCst) {
        sidecar::QUIT_NOW_GRACE
    } else {
        sidecar::STOP_GRACE
    };
    sidecar::stop(grace);
}

fn set_quitting(app: &AppHandle) {
    *lock(&app.state::<Shell>().phase) = Phase::Quitting;
}

/// The window, hidden until its first page has loaded (show_main), on the
/// UI in its "waiting" start-up (no server address yet).
fn open_main_window(app: &AppHandle) -> tauri::Result<()> {
    let (width, height) = initial_size(app);
    let dev_origin = dev_url(app).map(|url| url.origin());
    let builder = WebviewWindowBuilder::new(app, MAIN, WebviewUrl::App(ui_page(app).into()))
        .title(app.package_info().name.clone());
    // The UI draws its own title bar, in every theme (Q-G14): no decorations
    // (a titled macOS window draws a grey outline no theme can colour); the
    // corners are rounded below.
    let window = builder
        .decorations(false)
        .shadow(true)
        .inner_size(width, height)
        .min_inner_size(MIN_SIZE.0, MIN_SIZE.1)
        .center()
        .theme(Some(tauri::Theme::Dark))
        .background_color(BACKGROUND)
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
        .on_download(|webview, event| on_download(webview.app_handle(), event))
        .build()?;
    set_corners(&window, false);
    Ok(())
}

/// macOS: rounded corners, square in full screen (appkit.rs).
fn set_corners(window: &tauri::WebviewWindow, fullscreen: bool) {
    #[cfg(target_os = "macos")]
    {
        let radius = if fullscreen {
            0.0
        } else {
            appkit::CORNER_RADIUS
        };
        match window.ns_window() {
            Ok(ns_window) if appkit::round_corners(ns_window, radius) => {}
            _ => log!("argos-desktop: the window corners could not be rounded"),
        }
    }
    #[cfg(not(target_os = "macos"))]
    let _ = (window, fullscreen);
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

/// Start the server on a helper thread; tell the UI (or load it on the
/// server's address, or the failure page, when no UI has attached).
fn start_server(app: &AppHandle) {
    let shell = app.state::<Shell>();
    let attempt = shell.attempt.fetch_add(1, Ordering::SeqCst) + 1;
    {
        let mut phase = lock(&shell.phase);
        if matches!(*phase, Phase::Quitting) {
            return;
        }
        *phase = Phase::Starting;
    }
    if attached(app) {
        emit_state(app);
    }
    // The first attempt collects the start begun at the top of main().
    let early = if attempt == 1 {
        lock(&EARLY).take()
    } else {
        None
    };
    let dev = dev_build(app);
    let app = app.clone();
    thread::spawn(move || {
        let (result, tail) = match early {
            Some(early) => {
                let result = early.result.recv().unwrap_or_else(|_| {
                    Err(sidecar::StartError::Exited(
                        "its start-up thread ended".into(),
                    ))
                });
                (result, early.tail)
            }
            None => {
                let tail = sidecar::Tail::default();
                let (exit_app, exit_tail) = (app.clone(), tail.clone());
                let exe = sidecar_override(dev);
                let result = sidecar::start(
                    exe.as_deref(),
                    &extra_args(dev),
                    tail.clone(),
                    move |status, on_purpose| {
                        if !on_purpose {
                            server_stopped(&exit_app, attempt, status, &exit_tail);
                        }
                    },
                );
                (result, tail)
            }
        };
        let shell = app.state::<Shell>();
        match result {
            Ok(ready) => {
                log!(
                    "argos-desktop: server ready on 127.0.0.1:{} after {} ms ({} ms since launch)",
                    ready.port,
                    ready.elapsed.as_millis(),
                    shell.launched.elapsed().as_millis()
                );
                {
                    let mut phase = lock(&shell.phase);
                    if shell.attempt.load(Ordering::SeqCst) != attempt
                        || matches!(*phase, Phase::Quitting)
                    {
                        return;
                    }
                    *phase = Phase::Ready {
                        port: ready.port,
                        token: ready.token.clone(),
                    };
                }
                *lock(&shell.stdin) = ready.stdin;
                if attached(&app) {
                    emit_state(&app);
                } else if let Some(window) = app.get_webview_window(MAIN) {
                    // No UI listening (yet): load it on the server's address.
                    let url = ui_url(&app, Some((ready.port, &ready.token)));
                    if let Err(err) = window.navigate(url) {
                        log!("argos-desktop: cannot load the UI: {err}");
                    }
                }
                if dev_build(&app) && std::env::var_os("ARGOS_DESKTOP_TEST_PANIC").is_some() {
                    panic!("ARGOS_DESKTOP_TEST_PANIC");
                }
            }
            Err(err) => {
                let cause = err.cause();
                log!("argos-desktop: {cause}");
                let failure = failure("ARGOS could not start", cause, tail.text(), None);
                ended(&app, attempt, Phase::Failed(failure));
            }
        }
    });
}

fn failure(
    title: &'static str,
    cause: String,
    details: String,
    status: Option<String>,
) -> pages::Failure {
    pages::Failure {
        title,
        cause,
        details,
        log_dir: tilde(&log_dir()),
        status,
    }
}

/// The server ended without the shell asking: after start-up, that is a
/// crash; during start-up, `sidecar::start` reports it instead. Runs on the
/// sidecar's reaper thread.
fn server_stopped(app: &AppHandle, attempt: u64, status: String, tail: &sidecar::Tail) {
    let ready = matches!(*lock(&app.state::<Shell>().phase), Phase::Ready { .. });
    if ready {
        let cause = format!("The ARGOS server ended unexpectedly ({status}).");
        let failure = failure("The ARGOS server stopped", cause, tail.text(), Some(status));
        ended(app, attempt, Phase::Stopped(failure));
    }
}

/// The server failed or stopped: the UI shows it; with no UI attached, the
/// shell's failure page does (after [`ATTACH_WAIT`] for a UI still loading).
fn ended(app: &AppHandle, attempt: u64, phase: Phase) {
    {
        let shell = app.state::<Shell>();
        let mut current = lock(&shell.phase);
        if shell.attempt.load(Ordering::SeqCst) != attempt || matches!(*current, Phase::Quitting) {
            return;
        }
        *current = phase;
    }
    if attached(app) {
        emit_state(app);
        return;
    }
    let on_shell_page = app
        .get_webview_window(MAIN)
        .and_then(|window| window.url().ok())
        .is_some_and(|url| url.scheme() == SCHEME || url.host_str() == Some("argos.localhost"));
    let app = app.clone();
    thread::spawn(move || {
        let until = Instant::now() + ATTACH_WAIT;
        while !on_shell_page && Instant::now() < until && !attached(&app) {
            thread::sleep(Duration::from_millis(50));
        }
        // A UI that attached got the state in answer to argos://ui-ready.
        let shell = app.state::<Shell>();
        let still_ended = !attached(&app)
            && shell.attempt.load(Ordering::SeqCst) == attempt
            && matches!(*lock(&shell.phase), Phase::Failed(_) | Phase::Stopped(_));
        if still_ended {
            if let Some(window) = app.get_webview_window(MAIN) {
                let _ = window.navigate(page_url("/"));
            }
            show_main(&app);
        }
    });
}

/// The shell's pages and their actions.
fn serve(app: &AppHandle, request: &Request<Vec<u8>>) -> Response<Vec<u8>> {
    let version = app.package_info().version.to_string();
    match (request.method().as_str(), request.uri().path()) {
        ("GET", "/" | "/index.html") => {
            let shell = app.state::<Shell>();
            let night_red = *lock(&shell.theme) == "night-red";
            let html = match &*lock(&shell.phase) {
                Phase::Failed(failure) | Phase::Stopped(failure) => {
                    pages::failure(&version, failure, night_red)
                }
                _ => pages::starting(&version, night_red),
            };
            Response::builder()
                .header(header::CONTENT_TYPE, "text/html; charset=utf-8")
                .header(header::CACHE_CONTROL, "no-store")
                .header(header::CONTENT_SECURITY_POLICY, pages::CSP)
                .body(html.into_bytes())
                .unwrap_or_default()
        }
        ("POST", "/quit") => {
            request_quit(app, "window");
            empty(StatusCode::NO_CONTENT)
        }
        ("POST", "/retry") => {
            let ended = matches!(
                *lock(&app.state::<Shell>().phase),
                Phase::Failed(_) | Phase::Stopped(_)
            );
            if ended {
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

fn api_base(port: u16) -> String {
    format!("http://127.0.0.1:{port}")
}

/// The UI's page: index.html, or a test page in a dev build.
fn ui_page(app: &AppHandle) -> String {
    std::env::var("ARGOS_DESKTOP_UI_PAGE")
        .ok()
        .filter(|page| dev_build(app) && test_page_name(page))
        .unwrap_or_else(|| "index.html".to_owned())
}

/// The web UI's page, with the server's address and token when given.
fn ui_url(app: &AppHandle, server: Option<(u16, &str)>) -> Url {
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
    let mut url = base.join(&ui_page(app)).unwrap_or(base);
    if let Some((port, token)) = server {
        url.query_pairs_mut()
            .append_pair("api", &api_base(port))
            .append_pair("token", token);
    }
    url
}

/// A bare `name.html` of the bundled UI (no path, no scheme).
fn test_page_name(page: &str) -> bool {
    page.ends_with(".html")
        && page
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '_' | '.'))
        && !page.starts_with('.')
}

/// The first server start, before Tauri builds anything: its result waits in
/// [`EARLY`] for the first [`start_server`]; its exit callback waits for the
/// app (a crash right after start-up).
fn spawn_early(dev: bool) {
    let tail = sidecar::Tail::default();
    let (tx, rx) = mpsc::channel();
    let (start_tail, exit_tail) = (tail.clone(), tail.clone());
    *lock(&EARLY) = Some(EarlyStart { result: rx, tail });
    let spawned = thread::Builder::new()
        .name("argos-server-start".into())
        .spawn(move || {
            let exe = sidecar_override(dev);
            let result = sidecar::start(
                exe.as_deref(),
                &extra_args(dev),
                start_tail,
                move |status, on_purpose| {
                    if !on_purpose {
                        if let Some(app) = wait_app() {
                            server_stopped(app, 1, status, &exit_tail);
                        }
                    }
                },
            );
            let _ = tx.send(result);
        });
    if let Err(err) = spawned {
        log!("argos-desktop: no early start ({err})");
        lock(&EARLY).take();
    }
}

/// The app handle, once `setup` has run (at most 30 s from now).
fn wait_app() -> Option<&'static AppHandle> {
    let until = Instant::now() + Duration::from_secs(30);
    loop {
        if let Some(app) = APP.get() {
            return Some(app);
        }
        if Instant::now() >= until {
            return None;
        }
        thread::sleep(Duration::from_millis(20));
    }
}

/// `$ARGOS_SIDECAR`, honoured by dev builds only.
fn sidecar_override(dev: bool) -> Option<PathBuf> {
    let path = std::env::var_os("ARGOS_SIDECAR").filter(|p| !p.is_empty())?;
    if dev {
        Some(PathBuf::from(path))
    } else {
        log!("argos-desktop: ARGOS_SIDECAR ignored (release build)");
        None
    }
}

/// `$ARGOS_SIDECAR_ARGS`, honoured by dev builds only (split on whitespace;
/// placed before the shell's own arguments, which therefore win).
fn extra_args(dev: bool) -> Vec<String> {
    let Ok(args) = std::env::var("ARGOS_SIDECAR_ARGS") else {
        return Vec::new();
    };
    if !dev {
        log!("argos-desktop: ARGOS_SIDECAR_ARGS ignored (release build)");
        return Vec::new();
    }
    args.split_whitespace().map(str::to_owned).collect()
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
fn tilde(path: &Path) -> String {
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
        log!("argos-desktop: navigation to {} blocked", url.scheme());
    }
}

fn open_outside_path(path: &Path) {
    open_with_system(&path.to_string_lossy());
}

/// The platform's opener (no plugin: owner decision W8).
fn open_with_system(target: &str) {
    let opener = if cfg!(target_os = "macos") {
        "open"
    } else if cfg!(windows) {
        "explorer"
    } else {
        "xdg-open"
    };
    run_detached(opener, vec![target.to_owned()]);
}

/// Run a helper with argv entries (never parsed by a shell), waited on a
/// helper thread so no zombie is left behind.
fn run_detached(program: &'static str, args: Vec<String>) {
    thread::spawn(move || {
        if let Err(err) = std::process::Command::new(program).args(&args).status() {
            log!("argos-desktop: {program} failed: {err}");
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn window_payload_and_double_click() {
        assert_eq!(
            window_payload(true, "minimize"),
            r#"{"fullscreen":true,"double_click":"minimize"}"#
        );
        assert_eq!(
            json::get_bool(&window_payload(false, "zoom"), "fullscreen"),
            Some(false)
        );
        assert_eq!(double_click_action(None), "zoom");
        assert_eq!(double_click_action(Some("Maximize")), "zoom");
        assert_eq!(double_click_action(Some("Fill")), "zoom");
        assert_eq!(double_click_action(Some("Minimize")), "minimize");
        assert_eq!(double_click_action(Some("None")), "none");
    }

    #[test]
    fn theme_background_is_read_from_the_ui() {
        let c = parse_hex_color("#1a0304").expect("a colour");
        assert_eq!((c.0, c.1, c.2, c.3), (0x1a, 0x03, 0x04, 0xff));
        assert!(parse_hex_color("1a0304").is_none());
        assert!(parse_hex_color("#1a03").is_none());
        assert!(parse_hex_color("#zz0304").is_none());
    }

    #[test]
    fn download_payload_names_the_saved_file() {
        let saved = download_payload(
            Some(Path::new("/Users/o/Downloads/argos log (1).txt")),
            true,
        );
        assert_eq!(json::get_string(&saved, "status").as_deref(), Some("saved"));
        assert_eq!(
            json::get_string(&saved, "path").as_deref(),
            Some("/Users/o/Downloads/argos log (1).txt")
        );
        assert_eq!(
            json::get_string(&saved, "name").as_deref(),
            Some("argos log (1).txt")
        );
        let failed = download_payload(None, false);
        assert_eq!(
            json::get_string(&failed, "status").as_deref(),
            Some("failed")
        );
        assert_eq!(json::get_string(&failed, "path"), None);
    }
}
