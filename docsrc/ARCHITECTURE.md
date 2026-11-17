# Architecture

ARGOS 0.5.0 is a desktop app made of three parts: a **web interface**
(Svelte 5 and TypeScript), a **headless Python server** that owns the devices
and the measurements (FastAPI and uvicorn), and a **Tauri v2 shell** that shows
the interface in a native window and starts the server beside it as a
*sidecar*. The science lives in `argos/core`, which the server shares with the
PyQt6 app that ARGOS shipped up to 0.4.2. That app is retired: it is not
released any more, and its code stays in the repository as the reference of
the parity tests.

```{admonition} What has been tested, and how
:class: important

0.5.0 is the first beta of the new interface. The web UI and its server were
tested with the built-in simulator and with replays of real nights recorded
by the Seestar; their use live on the telescope is still to come. The
server's Alpaca path has been run against fake devices and unreachable
addresses in its tests, not against a Seestar (`web/spec/progress.md`, waves 1
and 3, "Real Seestar").
```

```{seealso}
The contract between the interface and the server is
[`argos/server/protocol.md`](https://github.com/jperret21/argos/blob/main/argos/server/protocol.md)
(API 2, every route and event). Running the interface for development is in
[`web/README.md`](https://github.com/jperret21/argos/blob/main/web/README.md)
and {doc}`simulator_testing`. {doc}`api/index` documents the Python modules
from their docstrings, {doc}`differential_photometry` what the photometry
computes, and {doc}`seestar_protocol` the wire format under the Alpaca
clients.
```

## The pieces

```{graphviz} diagrams/architecture.dot
:align: center
:alt: The desktop app holds the Tauri shell, the web UI and the frozen server. The shell spawns the server and reads its port and token; the UI talks to the server over REST and two WebSockets. The server imports argos/core, runs the simulator in process and ASTAP as a subprocess; the core reaches the Seestar over Alpaca and the catalogue services over HTTPS, and writes the session folders. The retired Qt app imports the same core.
```

| Part | Where | Built with | What it owns |
|---|---|---|---|
| Web UI | `web/src` | Svelte 5 (runes), TypeScript, Vite; uPlot, its one runtime dependency (`web/package.json`) | Every screen. It computes no measurement: its only science code is display maths ported from Python and tested against it. |
| Server | `argos/server` | Python 3.11, FastAPI, uvicorn (the `server` extra of `pyproject.toml`) | Devices, state, jobs, sequences, live photometry, Review, exports, the configuration file. |
| Desktop shell | `web/src-tauri` | Rust, Tauri v2: the crates `tauri`, `tauri-build` and `tauri-plugin-window-state` only (`Cargo.toml`) | The window, the native macOS menu, Quit, the sidecar's life. |
| Sidecar | `packaging/argos_server.spec` | PyInstaller, one-dir | The server and its Python, frozen, without Qt. |
| Shared core | `argos/core` | Python, numpy, astropy, alpyca, requests | Frame maths, photometry, the ASTAP wrapper, catalogues, Alpaca clients, the FITS writer, the configuration format. |
| Qt app, retired | `main.py`, `argos/ui`, `argos/workers` | PyQt6, pyqtgraph (the `qt` extra) | Nothing at runtime: the parity reference ([below](#the-retired-qt-app-and-why-it-stays)). |

For scale, at 0.5.0: about 18 700 lines of Python in `argos/core`, 34 300 in
`argos/server`, 97 300 lines of TypeScript and Svelte in `web/src/lib`, 2 700
of Rust in the shell, and 21 300 in the retired `argos/ui` and
`argos/workers` (`wc -l` on commit `175abf6`, comments and blank lines
included, tests excluded).

## The rules between the parts

| Rule | Why | Where it is enforced |
|---|---|---|
| The server never imports Qt, even indirectly. | The desktop app ships no Qt. | `tests/server/test_no_qt.py`; `packaging/argos_server.spec` fails the build if a Qt module is collected. |
| The interface reaches the server only through API 2: REST under `/api`, the WebSockets `/ws/events` and `/ws/frames`. API 2 only grows. | The same interface runs in the desktop window and in a browser; a change is reviewed in one place. | `protocol.md` (written before the code); `GET /api/health` reports `"api": 2`, and a breaking change would bump it. |
| No blocking work on the server's event loop. | The loop feeds the WebSockets; a slow Alpaca call must not freeze them. | Every REST route is a plain `def`, run in FastAPI's threadpool; devices, jobs and services have their own threads (docstrings of `app.py` and `hub.py`). |
| `argos/core` is Qt-free, except `argos/core/session`. | The server imports the core directly. | `acquisition_engine.py` and `device_session.py` use `QObject`, and the package's `__init__` imports them. The server imports nothing from that package, except `review.py`, which it loads by file path ([Review](#review-exports-and-re-run)). |
| The interface sends no request except to the local server. | Offline first: fonts, icons and scripts are bundled. | The desktop app's content security policy (`tauri.conf.json`: `connect-src` allows `'self'`, IPC and `127.0.0.1` only). |
| Components use design tokens, never a colour value. | Every theme holds, Night Red included. | `web/README.md` "Architecture"; `web/src/design/BRAND.md`. |

In docstrings and comments, `S1`-`S85` and `X1`-`X3` are the 0.5.0 fixes of
[`notes/release_0_5_0.md`](https://github.com/jperret21/argos/blob/main/notes/release_0_5_0.md);
rows `A1`-`A84` (API) and `M1`-`M103` (Qt to web mapping) are in
`web/spec/README.md`; `§n` points into `notes/photometry_plan.md`. All are in
the repository and not published on this site.

## The server: `argos/server`

### Process

`python -m argos.server` binds `127.0.0.1:8742` by default (`--port 0` takes
any free port). Once the socket listens, it prints exactly two lines on
stdout, `ARGOS_PORT=<port>` then `ARGOS_TOKEN=<token>`, for whatever process
started it; everything else, uvicorn's access log included, goes to stderr
with any token redacted (`argos/server/__main__.py`; protocol.md
"Launching").

Before it serves the first request, it reads `config.json` from
`--config-dir`, else `$ARGOS_CONFIG_DIR`, else `~/.argos` (the Qt app's file,
same format); sets up its rotating log `argos.log` (2 MB × 5) and crash
reports; makes the telescope profile active; applies the data paths; and
starts the network monitor. SIGINT and SIGTERM stop it gracefully: jobs and
the exposure are cancelled, threads joined, devices disconnected, sockets
closed. A SIGTERM exit has status −15 (143 in a shell), a Ctrl-C status 0, and
`POST /api/app/shutdown` (the desktop Quit) status 0.

Security, in short (protocol.md "Security"): every route except
`GET /api/health` needs `Authorization: Bearer <token>`, and the WebSockets
take `?token=`; bound to loopback, the server answers only to the `Host`
names `127.0.0.1`, `localhost`, `::1` and `tauri.localhost`, and refuses a
foreign `Origin` (the guard against DNS rebinding); it serves no OpenAPI
pages. It opens network connections to the devices the observer connects, to
the configured Seestar address (a reachability probe), to the catalogue
services when a field is identified or a name looked up, and for the
observer's explicit requests (discovery, the place search, the internet
check).

### Threads and the event bus

```{graphviz} diagrams/server_threads.dot
:align: center
:alt: Request, device, service and job threads all call the Hub, which publishes each change under its lock with a sequence number to the EventBus; the bus hands events and frames over to the per-client WebSocket senders on the event loop, which send them to the web UI.
```

- **Routes are thin.** Each validates its body strictly (`"2"` is not a
  number, `80.0` not an integer gain) and calls one `Hub` method.
- **The hub owns the devices** (`hub.py`): four slots, mount, camera, filter
  wheel and focuser, each with its state and a *generation* that every connect
  and teardown bumps, so the answer of a device disconnected meanwhile is
  discarded. It keeps the contract's records as immutable snapshots
  (`state.py`) and is their only writer. Its lock is never held across device
  I/O, a thread join or a configuration write.
- **The event bus** (`events.py`) is the only crossing point between the
  threads and the asyncio loop. Each client's buffers are bounded: events in a
  FIFO which, past 256 pending messages, keeps only the newest snapshot of each
  kind and drops `log` lines first; frames in one slot, so a slow client skips
  frames. Each stream (`log`, `frame_saved`, `conditions`, `photometry_point`,
  `photometry_reset`) carries its own sequence number, and a client that sees
  a gap reads the REST page again (`events.py`; protocol.md "Backpressure").
- **Long work is a job** (`jobs.py`): the route answers `202 {"job_id"}`,
  progress arrives as `job` events at most every 0.25 s, and
  `DELETE /api/jobs/{id}` cancels it at a safe boundary. A second job of the
  same kind on the same resource gets `409 busy` with the running job's id.
- **Errors** have one shape, `{"error": {"code", "message"}}` (`errors.py`).
  The message is written for the observer, and the interface shows it as it
  is.

### Modules

The first line of each module's docstring says what it owns. Code ported
from the Qt app cites the Qt file and lines it reproduces, so a difference can
be traced to its source.

| Area | Modules |
|---|---|
| Process and contract | `__main__.py`, `settings.py`, `app.py`, `auth.py`, `errors.py`, `state.py`, `events.py`, `frames.py`, `jobs.py`, `logbook.py` |
| Devices and connection | `hub.py`, `devices/` (`base.py`, the device protocols the hub calls; `alpaca.py` over `argos.core.alpaca`; `sim_camera.py`, `sim_mount.py`, `sim_aux.py`, `sim_replay.py`), `discovery.py`, `network.py`, `profiles.py`, `stellarium.py` |
| Settings | `config_store.py`, `config_meta.py` (every key the interface may read or write), `runtime.py`, `settings_helpers.py`, `site_check.py`, `fs.py`, `sessions.py`, `support.py` |
| Observe | `capture.py` (Take shot and the FITS save), `wheel.py`, `focuser.py`, `autofocus.py`, `jog.py` (with a server-side dead-man), `conditions.py`, `observation.py`, `fits_source.py` (Open FITS) |
| Field | `field.py`, `field_solve.py` (ASTAP, killed on cancel), `field_catalog.py`, `field_track.py`, `field_measure.py`, `targets.py` |
| Photometry | `photometry.py` (live points; the method is the core's) |
| Plan and run | `sequence_plan.py`, `sequence.py` (the run and the mount interlock), `planning.py` (visibility, transits) |
| The night | `attention.py` (alerts, never an action on the mount), `keepawake.py`, `wrapup.py` |
| Review | `review.py`, `review_routes.py`, `files.py` (frame inspector), `exports.py`, `export_routes.py`, `rerun.py` |
| Desktop | `desktop.py` (shutdown, reveal in the file manager, the shell's stdin) |

## The web UI: `web/`

`src/main.ts` mounts `App.svelte`: the shell (rail, section, status bar)
around five sections, Connection, Observe, Plan, Review and Settings. The code
is under `src/lib`:

| Folder | What it holds |
|---|---|
| `api/` | Wire types, the REST client, the event socket, frame decoding |
| `app/` | `ArgosApp` (`state.svelte.ts`), the one shared state; shortcuts, theme, preferences, log, jobs, layout |
| `connection/`, `settings/`, `imaging/`, `plan/`, `run/`, `review/` | One folder per screen or area (`imaging/` is Observe) |
| `viewer/` | The image viewer: WebGL2 renderer and shaders, stretch, histogram, rotation, overlays |
| `charts/` | Light curves (uPlot), the autofocus V-curve, the conditions and visibility timelines |
| `components/` | Shared controls; in development, `/?gallery=1` shows each in every state |
| `format/` | Every number on screen: RA and Dec, U+202F digit grouping, U+2212 minus, times |
| `shell/` | Rail, status bar, start-up screen, toasts, log drawer, command palette; `shell/desktop/`, the desktop side (title bar, Quit dialog, crash notice, the bridge to the shell) |

- **One state, one runner.** Every hardware action goes through one runner:
  it marks the action busy, applies the REST answer at once (the WebSocket
  echo follows) and turns a failure into a toast and a log line. The last
  known state is kept while the link is down, and the page reconnects by
  itself.
- **Science ports, tested against Python.** The automatic stretch
  (`stretch.ts`, byte-exact against `apply_stretch`), the histogram binning
  (against numpy) and the rotation (against `numpy.rot90`) are the only
  computations ported from Python, each with tests that compare them
  (`web/README.md` "Architecture").
- **Which server.** In a browser, `?api=` and `?token=` select it
  (`run_web.py` opens the page with them). In the desktop app, the shell sends
  the address and the token once the sidecar is ready.

## The desktop app: `web/src-tauri`, `packaging/`

### The shell

| File | What it does |
|---|---|
| `main.rs` | The life cycle below, the quit path, downloads, the window. Its header comment is the reference. |
| `sidecar.rs` | Starts the server, reads its address, stops it. |
| `menu.rs` | The native macOS menu bar, mirroring the interface's commands. Linux has no menu bar. |
| `pages.rs` | The shell's own fallback pages, for a failure before the interface can show one. |
| `appkit.rs` | macOS: routes the system's quit requests through the shell; rounds the borderless window's corners. |
| `json.rs` | The few JSON payloads exchanged with the interface (no serde crate). |

The interface talks to the shell through Tauri events named `argos://…`,
declared in `web/src/lib/shell/desktop/bridge.ts`; it uses no npm Tauri
package.

### Life cycle

1. The shell spawns the sidecar first, before its window exists:
   `argos-server --host 127.0.0.1 --port 0 --desktop --exit-on-stdin-eof`,
   with a stdin pipe that the shell keeps open.
2. The window opens on the bundled interface, which shows "Starting the
   ARGOS server…".
3. The shell reads `ARGOS_PORT` and `ARGOS_TOKEN` within 60 s, then sends the
   interface `argos://server-state` "ready" with the address and the token,
   and the interface adopts them in place, without a reload
   (`web/src/lib/shell/desktop/desktop.svelte.ts`, `adopt`).
4. A server that is missing, cannot be launched, stops or stays silent is a
   start-up failure: the interface shows the cause, the last lines of the
   server's error output, the log folder and a Retry. A server that ends
   later, unasked, gives the crash notice.
5. Quit (⌘Q, the menu, the window's close, the Dock) becomes one quit request
   to the interface. Its Quit dialog asks the server (`POST /api/app/shutdown`;
   `409 busy` says what would stop, and the observer may force it), the server
   shuts down within its 60 s budget, and the shell exits. A server still
   running then gets SIGTERM, and SIGKILL of its process group 65 s later
   (`sidecar.rs` `STOP_GRACE`).
6. If the shell itself dies, even by `kill -9`, the pipe closes and the
   server takes its SIGTERM path (`--exit-on-stdin-eof`): it never outlives
   the app.

On the macOS development build of wave 8's final review, the server's ready
line came 1.14 to 1.26 s after launch and the interface was connected at about
1.5 s (warm launches); the first run of freshly written sidecar binaries took
22.3 s to the ready line, macOS checking them once (`web/spec/progress.md`,
wave 8, "Technical review" and "Evidence (final builds)"). Measured on one
machine, not on Linux.

### The sidecar

`packaging/argos_server.spec` freezes `argos/server/__main__.py` *one-dir*:
the server starts in about 1 s instead of about 16 s for a one-file build,
runs as one process and leaves nothing behind after a SIGKILL (the spec's
header). It is built from an environment without the `qt` extra and refuses
to finish if a Qt module was collected. It carries the offline catalogue, the
core's `review.py` (loaded by path), the hidden imports that file needs, and
`LICENSE`; ASTAP is not bundled. The frozen folder is 97 MB
(`web/spec/progress.md`, wave 8).

- **Where it goes.** `ARGOS.app/Contents/Resources/argos-server/` on macOS,
  `/usr/lib/argos/argos-server/` in the `.deb` (`tauri.conf.json`).
- **Self-check.** `argos-server --self-check` imports the server and every
  file it loads by path, prints `ARGOS <version> self-check: ok` and exits;
  `packaging/smoke_sidecar.py` runs it, then checks the ready lines, the
  health route, the version and the exit on end of stdin.
- **Signing.** Ad hoc, without the hardened runtime (its library validation
  would refuse PyInstaller's ad hoc-signed libraries) and without
  notarisation: hence the first-launch steps of {doc}`install`.

### Development and release builds

- **Two identities.** The release app is "ARGOS", `org.argos.argos`
  (`tauri.conf.json`); every local build is "ARGOS Dev",
  `org.argos.argos.dev` (`tauri.dev.conf.json`), so tests never touch the
  release app's WebKit data or window state. Only a development build honours
  `ARGOS_SIDECAR` (run another server executable), `ARGOS_SIDECAR_ARGS` (add
  server arguments, placed before the shell's own so that those win) and two
  test hooks. Every build passes `ARGOS_CONFIG_DIR` and `ARGOS_LOG_DIR` to the
  server.
- **One version.** `argos/__init__.py`'s `__version__`; `pyproject.toml` and
  `web/src-tauri/Cargo.toml` must match it (`build.rs` refuses a mismatch,
  `tests/packaging` checks it), and `tauri.conf.json` sets none.
- **Release.** `.github/workflows/release.yml`, on a `v*` tag or a manual
  run: a macOS `.dmg` (`packaging/make_dmg.sh`: the app, an Applications
  link, `READ ME FIRST.txt`, `LICENSE.txt`) and an Ubuntu 22.04 `.deb`
  (WebKitGTK 4.1). It runs the tests, an exact Qt-free install, the freeze and
  its smoke test, the web and shell checks, the Tauri build, and checks that
  the macOS app was linked on SDK 14 or newer (the interface uses the Popover
  API). A tag ends with a **draft** GitHub release; publishing it is a human
  step. The steps are in `web/README.md` "Desktop app (Tauri)".

## How a night flows through the code

### Live view

```{graphviz} diagrams/preview_chain.dot
:align: center
:alt: The camera's frame is downloaded by the exposure job thread, published by the hub with its statistics, queued one per client, sent on /ws/frames, decoded without a copy and drawn as a WebGL2 texture. Field tracking, frame metrics and the FITS save are also fed with each frame.
```

The exposure job downloads the frame (Alpaca `ImageBytes`, or the
simulator); the hub publishes it with statistics from a 65 536-bin histogram,
exact median and MAD in a few milliseconds (`frames.py`). Each client holds at
most one pending frame. On `/ws/frames` a frame is a JSON header and the
`uint16` pixels at an 8-byte aligned offset, so the interface builds a
`Uint16Array` on the message buffer without a copy and uploads it as a texture;
stretch, rotation and zoom are shader uniforms, so moving a slider never
uploads the image again. At most 8 frame clients are served at a time.

### A sequence

```{graphviz} diagrams/sequence_execution.dot
:align: center
:alt: The plan is expanded into frames; for each frame the run thread checks stop and pause, moves the wheel, runs any autofocus, reads the filter back, exposes, publishes the frame, writes the FITS and session.json, sends frame_saved, measures one photometry point for a light sub, reports progress and waits for the next frame.
```

`argos/server/sequence.py` ports the fixed Qt sequence path step by step
(protocol.md "Each sub"). The run has its own thread and writes each FITS on
it; each photometry point is measured on the photometry thread. While a run
is active, the server refuses a change of the aperture geometry, of the noise
model or of the camera's e-/ADU inputs (`409 run_active`), so that a run keeps
one aperture and one error model (S15, S84). Not covered: another program
editing `config.json`, or an edit of the photon-transfer file, during a run
(protocol.md "Photometry geometry and noise model locked"). The run folder is the Qt app's
(`{RUN}_{OBJECT}/` with `lights/ darks/ flats/ biases/`, `session.json`,
`photometry/`); the FITS keywords are specified once, in {doc}`fits_headers`.

### Photometry

```{graphviz} diagrams/photometry_pipeline.dot
:align: center
:alt: The raw frame becomes the green plane; the target set's coordinates become pixel positions through the tracked WCS; measure_frame measures each star's aperture, differential_mag forms the ensemble magnitude, the point gets its run-level systematic floor and is written to CSV or an AAVSO report.
```

The live points (`argos/server/photometry.py`) and the batch re-run
(`argos/server/rerun.py`) call the same core functions; the server adds when
a point is measured, its flags and its files, not a second method. What each
step computes, and its limits, is {doc}`differential_photometry`.

### Review, exports and re-run

- **Review** opens a session as a job and reads it with the fixed Qt reader
  itself, `argos/core/session/review.py`. The server loads that file by path
  (`argos/server/review.py`, `core_review`), because importing it as
  `argos.core.session.review` would run the package's `__init__` and import
  PyQt6. One reader, no copy that could drift. Nothing is written into a
  session.
- **Exports** (AAVSO, CSV) are written by the core writers, `write_aavso` and
  `write_curves_csv`, on the very curves the Review plot shows, behind the
  refusals of 0.5.0 (an unidentified curve, a missing observer code, one
  filter per file, no undated row).
- **Re-run** measures a session's saved frames again (a port of the fixed
  `PhotometryBatchWorker`) and writes into a new folder inside the session,
  never over an earlier result.

## The shared core: `argos/core`

Frame maths, protocols, catalogues and the science. Everything here is
Qt-free and testable without a display, except `session/`.

```
core/
├── alpaca/          ASCOM Alpaca over alpyca: client, discovery (UDP, probe, /24 sweep),
│                    telescope, camera (ImageBytes, JSON fallback), focuser, filter wheel
├── catalog/         AAVSO VSX and VSP, Gaia DR3, SIMBAD, Sesame resolver, NASA Exoplanet
│                    Archive, the bundled offline catalogue, comparison selection,
│                    point identity, the target set
├── exoplanet/       transit.py: ephemeris to contact times, coverage, plan
├── hardware/        telescope profiles (S30 Pro validated; S30, S50 not), driver
│                    cross-check, the active profile, egain.py (e-/ADU and its source)
├── imaging/         green plane, debayer, stretch, metrics (HFD, FWHM, stars), focus
│                    V-curve, ASTAP wrapper, sequencer, FITS writer, session log,
│                    sensor references (IMX585, IMX662, IMX462), sky geometry
├── photometry/      aperture, differential (ensemble), lightcurve (CSV, AAVSO),
│                    airmass and BJD, params, session, quality, tracking, uncertainty
├── seestar/         native_client.py: JSON-RPC on port 4700 (used by no app, see below)
├── session/         the Qt exception: acquisition_engine.py and device_session.py are
│                    QObjects; review.py and diagnostics.py are Qt-free
├── stellarium/      the Stellarium Telescope Protocol: codec and asyncio TCP server
├── config.py        config.json: defaults and migrations
├── location_resolver.py   site name to coordinates and elevation
└── support_bundle.py      local logs, crash reports, redacted support ZIPs
```

## Talking to devices and services

| Channel | Port | Who uses it |
|---|---|---|
| ASCOM Alpaca, HTTP | 32323 on the Seestar | Every device: telescope, camera, focuser, filter wheel (`argos.core.alpaca`, adapted by `argos/server/devices/alpaca.py`) |
| Alpaca discovery, UDP broadcast | 32227 | First layer of discovery; then a direct probe of the last address and the profile's access-point address (`10.0.0.1` for the S30 Pro), then a sweep of the local /24, each confirmed on `/management/v1/configureddevices` |
| Stellarium Telescope Control, TCP | 10001 on `127.0.0.1` by default | The bridge: Stellarium drives the mount through ARGOS (`argos/server/stellarium.py`, the core's codec and server) |
| Native JSON-RPC, TCP | 4700 | No app. `argos/core/seestar/native_client.py` and its tests remain; the server jogs with Alpaca `MoveAxis`, as the Qt app did ({doc}`seestar_protocol`) |
| HTTPS | 443 | Catalogue lookups when a field is identified or a name looked up, and the place search on request; results cached under `data_paths` |
| ASTAP | (a subprocess) | Plate solving, the observer's own installation |

## Files and configuration

`config.json` (default folder `~/.argos`) is shared by the server and the Qt
app, with the same defaults and migrations (`argos/core/config.py`). Its
sections are `alpaca`, `sessions_path` (default `~/Argos/sessions`),
`data_paths`, `observer`, `site`, `hardware` (profile and overrides),
`camera`, `astrometry`, `catalog`, `photometry`, `diagnostics`, `stellarium`
and `ui`. What each key means, its unit and its limits are in
`argos/server/config_meta.py`, which the Settings screen is built from. The
server notices when another program changes the file (a `config` event with
`source: "file"`).

The session folder layout and every FITS keyword are specified once, in
{doc}`fits_headers`.

### Data model

```{graphviz} diagrams/data_model.dot
:align: center
:alt: The core's classes by area (acquisition, astrometry, catalogue, photometry, session record) and the files they become: config.json, session.json, targets.json, the light frames, the photometry CSVs and the AAVSO report.
```

| Class | Module | Purpose |
|---|---|---|
| `Config` | `core/config.py` | The settings file, defaults and migrations |
| `SequencePlan`, `FrameSpec` | `core/imaging/sequencer.py` | A plan and the frames it expands to |
| `SolveResult`, `FrameWCS` | `core/imaging/platesolve.py` | An ASTAP outcome; pixel to sky |
| `TrackedWCS`, `ApertureTracker` | `core/photometry/tracking.py` | The solution followed from frame to frame |
| `TargetSet`, `TargetStar` | `core/catalog/targets.py` | The stars of a run and their roles (target, comparison, check) |
| `AperturePhot` | `core/photometry/aperture.py` | One aperture measurement |
| `DiffResult` | `core/photometry/differential.py` | One differential magnitude |
| `LightCurve`, `LcPoint` | `core/photometry/lightcurve.py` | A curve and its points |
| `SessionLog`, `FrameRecord` | `core/imaging/session_log.py` | The per-frame quality record, `session.json` |

## The retired Qt app, and why it stays

The PyQt6 app (`main.py`, `argos/ui`, `argos/workers`) was ARGOS up to 0.4.2.
It is not shipped any more: PyQt6, pyqtgraph and pytest-qt moved to the `qt`
extra, and the sidecar refuses Qt. Its code stays for three reasons:

1. **The 0.5.0 fixes were made there.** The photometry, FITS and session
   fixes of 0.5.0 (S1-S85) were made in the Qt app and the core, on the
   `release/0.5.0` branch, each with a regression test, then merged. The server
   ports that fixed code and cites it line by line.
2. **Parity tests.** Tests in eleven files of `tests/server` run the Qt code
   and the server on the same inputs and compare the results (live
   photometry, re-run, exports, sequences, plan files, visibility, Review,
   old-file rules). They call `pytest.importorskip` on a PyQt6 module, so a
   Qt-free install skips them; CI installs the `qt` extra and runs them.
   Identity with the fixed Qt proves non-regression only: results are first
   checked against references independent of it (Siril, astropy, VSP, the
   AAVSO format).
3. **One reader.** Review reads sessions with the core's `review.py`, the same
   file the Qt app uses.

The Qt app ran its work on `QThread` workers and drew live frames through a
three-thread, latest-frame-wins chain; the server keeps that pattern
(latest-wins frame queues, work off the event loop) with plain threads and an
event bus instead of Qt signals. Its interface code is not documented further
here; the API reference keeps its modules as the legacy parity reference.

## Hardware constants (Seestar S30 Pro)

From the built-in profile `S30_PRO` in `argos/core/hardware/catalog.py`.

| Quantity | Value | Note |
|---|---|---|
| Aperture, focal length | 30 mm, 160 mm | f/5.3 |
| Sensor | Sony IMX585 | 2.9 µm pixels |
| Frame | 3840 × 2160 | 8.3 Mpx |
| Bayer pattern | GRBG | not RGGB; photometry uses the green plane, (G1 + G2) / 2 |
| Data | 12-bit values × 16 in 16-bit files | `adc_bits = 12`; 99.92 % of raw values are multiples of 16 (`web/spec/decisions-s66-s72-independent-checks.md`, "Raw values") |
| Pixel scale | 3.74″ per pixel | nominal: 206.265 × 2.9 / 160 |
| Field of view | 3.99° × 2.24° | 4.58° diagonal; `TelescopeProfile.fov_deg` |
| Filter wheel | Dark, IR, LP | slots 0, 1, 2 |
| AAVSO filter code | TG | untransformed green |
| Access-point address | `10.0.0.1` | the profile's `ap_host` |

The S30 and S50 profiles exist and are not validated for photometry. The
profile also carries measured values (the black level and the camera's
e-/ADU at gain 80); where they come from, and in which order the photometry
looks for the e-/ADU, is in {doc}`differential_photometry`.
