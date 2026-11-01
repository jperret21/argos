# ARGOS server protocol — API 2

The contract between the headless Python server (`argos.server`) and the web
front-end. `GET /api/health` reports `"api": 2`; any breaking change to what
follows bumps that number.

API 2 is **additive** over API 1: every v1 route, record and event keeps its
meaning and shape; v2 adds routes, events, record fields and log levels.
Section [What API 2 adds](#what-api-2-adds) lists them; wave 1 of the web
UI (`web/spec/README.md` §7, rows A1-A4, A8-A10, A13-A18, A80, plus the
Stellarium bridge A19 brought forward from wave 3 so that every Qt
Connection control has its web control) is what ships in API 2.

## Launching

```
.venv/bin/python -m argos.server [--host 127.0.0.1] [--port 8742] [--simulator]
                                 [--dev-token TOKEN] [--config-dir DIR] [--log-dir DIR]
                                 [--connect-timeout S]
```

| Flag | Meaning |
|---|---|
| `--host` | Interface to bind. Default `127.0.0.1`; anything else logs a warning. |
| `--port` | TCP port. Default `8742`; `0` lets the OS choose a free one. |
| `--simulator` | Connect the built-in simulator (camera and mount) during startup. |
| `--dev-token` | Fixed token for development. Without it the token is random per launch (`secrets.token_urlsafe(32)`). |
| `--config-dir` | Folder holding `config.json`. Default: `$ARGOS_CONFIG_DIR`, else `~/.argos` (the Qt app's file, shared during the transition). Tests and smoke runs always pass a temporary folder. |
| `--log-dir` | Folder of the rotating server log `argos.log` and crash reports. Default: `$ARGOS_LOG_DIR`, else the platform diagnostics folder (`~/Library/Logs/Argos` on macOS, `$XDG_STATE_HOME/argos` or `~/.local/state/argos` elsewhere). |
| `--connect-timeout` | Seconds a TCP pre-check of an Alpaca address may take before a device connect is attempted (default 3). See [Unreachable addresses](#unreachable-addresses). |

Once the socket is bound and listening, stdout carries exactly two lines, in
this order, for a supervising process such as the future Tauri sidecar:

```
ARGOS_PORT=8742
ARGOS_TOKEN=<token>
```

Logs, uvicorn's access log included, go to stderr, with any `token=…`
redacted. SIGINT and SIGTERM shut down gracefully: running jobs are
cancelled, the exposure is cancelled, worker threads are joined, devices are
disconnected and WebSockets are closed (code 1012 from uvicorn, or 1001 from
the server). uvicorn then re-raises the signal, so a clean SIGTERM exit has
status −15 (143 in a shell), not 0. A Ctrl-C (SIGINT) exits with status 0
and no traceback. A `--dev-token` shorter than 16 characters draws a warning
on stderr: it is guessable, for development only.

Start-up (API 2, row A3), before the first request is served:

1. `config.json` is read from the config folder (defaults merged and the
   Qt app's migrations applied, exactly as `argos.core.config.Config.load`
   does). A missing file is not created until the first write; an
   unreadable file is kept aside (`config.json.unreadable-<UTC>`) before the
   first write replaces it, and the server starts on the defaults.
2. Logging honours `ui.log_level` (stderr and the rotating file
   `argos.log`, 2 MB × 5 backups, as the Qt app); uncaught exceptions,
   in any thread, leave a `crash-<UTC>-<pid>.txt` report in the log folder.
3. The telescope profile `hardware.profile` (+ `hardware.overrides`) is made
   active; it supplies `sensor.bayer` in Alpaca mode.
4. The catalogue cache locations (`data_paths.*_cache*`) and the
   photon-transfer calibration folder (`data_paths.camera_calibration_directory`)
   are applied to the core modules that use them.
5. The network monitor starts (Seestar probe only, see `network`).

WebSocket compression (permessage-deflate) is disabled. Compressing one
1080×1920 frame with zlib takes about 240 ms on the event-loop thread and
only reaches a 0.59 ratio, because sensor noise barely compresses.

Dependencies: `uv pip install --python .venv/bin/python fastapi 'uvicorn[standard]'`
(the `server` extra in `pyproject.toml`). The server imports no Qt, and
`tests/server/test_no_qt.py` enforces that.

## Security

- **Token.** Every HTTP route except `GET /api/health` requires
  `Authorization: Bearer <token>`. WebSockets pass `?token=<token>` because
  browsers cannot set headers on them. A missing or wrong token gets HTTP
  `401` (`unauthorized`, with `WWW-Authenticate: Bearer`) or WebSocket close
  code **4401**. The socket is accepted before it is closed, so a browser
  sees 4401 and not a failed handshake (1006).
- **Origins.** CORS allows `http://localhost[:port]`, `http://127.0.0.1[:port]`,
  `tauri://localhost` and `http://tauri.localhost`, for the methods `GET`,
  `POST`, `PUT`, `PATCH` and `DELETE`. CORS does not apply to WebSockets, so
  the server checks their `Origin` header against the same list. A
  disallowed origin gets close code **4403**. Clients that send no `Origin`,
  such as curl, tests or a supervisor, are authenticated by the token alone.
- **Host and Origin (DNS rebinding).** CORS only stops a page from reading
  an answer; a page whose hostname was rebound to 127.0.0.1 is same-origin
  and would still make its requests run. So, when bound to loopback, the
  server answers only to the `Host` names `127.0.0.1`, `localhost`, `::1`
  and `tauri.localhost` (`403 forbidden_host`, WebSocket close 4403), and
  any HTTP request carrying a foreign `Origin` is refused before it runs
  (`403 forbidden_origin`; CORS preflights are left to CORS). Bound to a
  network interface (`--host`), any `Host` is accepted.
- No OpenAPI or docs pages are served, because every route except health is
  protected.
- **Network use.** The server opens network connections only to the devices
  the observer connects, to the configured Seestar address (reachability
  probe), and for explicit requests: discovery (`POST /api/discovery`) and
  the internet check (`POST /api/network/check` with `internet: true`).

## Errors

Every 4xx and 5xx response has this body:

```json
{"error": {"code": "<snake_case>", "message": "<human text>"}}
```

The `message` is written for the observer and may be shown verbatim (a
`409` in particular). Some errors carry extra members inside `error`
(API 2): `fields` (`{"<config key>": "<message>"}`, for `PATCH /api/config`)
and `owner` (the job id that holds a resource, for `409 busy` on a job
start).

| HTTP | code | When |
|---|---|---|
| 400 | `invalid_argument` | Body fails validation: wrong type, out of range, unknown field, relative path, wrong file suffix. Request bodies are strict, so `"2"` is not a number, `80.0` is not an integer gain and `1` is not a boolean. `PATCH /api/config` adds `fields`. |
| 400 | `invalid_fits` | The file exists but is not a displayable FITS image. |
| 400 | `invalid_argument` | Also `open-fits` on a path the OS refuses to examine (name too long, unreadable directory). |
| 401 | `unauthorized` | Bad or missing token. |
| 403 | `forbidden_host` / `forbidden_origin` | Request for a foreign `Host` name, or from a foreign `Origin` (see Security). |
| 404 | `not_found` | Unknown route, unknown device id, unknown (or expired) job id, or `open-fits` on a missing file. |
| 405 | `method_not_allowed` | Wrong HTTP method on a known route. |
| 409 | `not_connected` | Camera or mount command with that device not connected. Also a mount command whose device was disconnected while it ran: its result is discarded. |
| 409 | `busy` | Exposure requested while the camera exposes, downloads, is live, or is still stopping. `POST /api/connection` or a device connect while devices are connected to **another** address or mode. `PUT /api/profile` while a device is connected (message says why). A job start while a job of the same kind runs (`owner` = its id). |
| 409 | `parked` | `goto` or `tracking` on a parked mount. |
| 409 | `not_live` | `PATCH /api/camera/live` while live view is not running. |
| 409 | `unsupported` | `DELETE /api/jobs/{id}` on a job kind that cannot be cancelled. |
| 409 | `run_active` | Reserved: a photometry-geometry config change while a sequence runs (no sequence engine in API 2 yet, never sent). |
| 500 | `internal_error` | Any unexpected failure; the traceback is in the server log. The answer keeps the CORS headers, so the browser can read it. |
| 502 | `connection_failed` | The device could not be reached or refused to connect. Its device state becomes `error` with the full text. |
| 502 | `device_error` | A connected device refused a command or stopped answering. |

Codes reserved by `web/spec/README.md` §4.1 for later waves: `not_solved`,
`no_target`, `no_comparison`, `no_frames`, `site_missing`, `session_invalid`.

## HTTP routes

Bodies and responses are JSON. All routes except health need the token.

### API 1 routes (unchanged)

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/health` | — | `{"ok": true, "version": "0.4.2", "api": 2, "boot_id": "<16 hex>"}` (v2 adds `boot_id`) |
| GET | `/api/status` | — | `{"boot_id": string, "connection": ConnectionState, "camera": CameraState, "mount": MountState, "devices": DevicesState, "profile": ProfileSummary}` (v2 adds `boot_id` and the last two) |
| POST | `/api/connection` | `{"mode": "simulator"}` or `{"mode": "alpaca", "host": "<ip>", "port": <int>}` | ConnectionState |
| DELETE | `/api/connection` | — | ConnectionState. Idempotent. Disconnects all four devices. |
| POST | `/api/camera/capture` | `{"exposure_s": <float, 0 < x ≤ 3600>, "gain": <int, 0…1000>}` | CameraState (`exposing`); one frame follows. |
| POST | `/api/camera/live` | same | CameraState (`live`); frames follow until stop. |
| PATCH | `/api/camera/live` | same | CameraState. Changes the running live view's exposure and gain from its **next** frame: the exposure in progress ends with the old settings, and the record's `exposure_s` / `gain` change (with a `camera` event) when the next exposure starts, so they always describe the frame being taken. `409 not_live` otherwise. Added in API 1 without a version bump (additive). |
| POST | `/api/camera/stop` | — | CameraState (`idle`). Also clears a camera `error`. |
| POST | `/api/camera/open-fits` | `{"path": "<absolute path>"}` | CameraState. The file is published as a frame. Works without a connection. |
| POST | `/api/mount/goto` | `{"ra_hours": <0…24>, "dec_deg": <-90…90>}` | MountState (`slewing`). Turns tracking on. |
| POST | `/api/mount/stop` | — | MountState. Aborts a slew (ASCOM `AbortSlew`) and leaves tracking as it was. |
| POST | `/api/mount/park` | — | MountState. Slews to park, stops tracking, clears the target. |
| POST | `/api/mount/unpark` | — | MountState (`idle`). |
| POST | `/api/mount/tracking` | `{"enabled": <bool>}` | MountState |

v1 connection behaviour (kept):

- `POST /api/connection` connects the **mount, then the camera** (the
  mount's connect syncs the mount clock, as in the Qt app) and blocks until
  both answer, a few seconds on Alpaca. Meanwhile `/ws/events` shows
  `connecting`. Both must succeed: if the camera fails, the mount this call
  connected is released again, and the answer is `502 connection_failed`.
- Posting the same parameters again while connected returns the current
  state. Posting different ones returns `409 busy`; disconnect first.
- Since API 2 the record is **derived** from the per-device states (see
  `ConnectionState` below), so it also reflects devices connected with the
  v2 per-device routes.

Coordinates are ICRS/J2000, like everywhere in ARGOS. In Alpaca mode the
conversion to the driver's frame (topocentric-of-date on the Seestar) is
done by `argos.core.alpaca.telescope.Telescope`.

### API 2 routes

| Method | Path | Body | Returns | Row |
|---|---|---|---|---|
| GET | `/api/app/info` | — | AppInfo | A1 |
| GET | `/api/logs?after=<seq>&limit=<n>&level=<lvl>` | — | LogPage | A2 |
| GET | `/api/config` | — | ConfigSnapshot | A8 |
| PATCH | `/api/config` | `{"<key>": <value>, …}` | ConfigPatchResult | A9 |
| GET | `/api/devices` | — | DevicesState | A13 |
| POST | `/api/devices/{id}/connect` | ConnectBody (optional) | DevicesState | A14 |
| DELETE | `/api/devices/{id}` | — | DevicesState. Idempotent; also stops the mount's auto-retry ("Stop retrying"). | A14 |
| POST | `/api/devices/connect-all` | ConnectBody (optional) | DevicesState | A15 |
| DELETE | `/api/devices` | — | DevicesState. Idempotent. | A15 |
| POST | `/api/discovery` | DiscoveryBody (optional) | `202 {"job_id": "<id>", "job": Job}` | A16 |
| GET | `/api/profiles` | — | ProfilesState | A17 |
| PUT | `/api/profile` | `{"key": "s30pro"\|"s30"\|"s50"}` | ProfilesState | A17 |
| GET | `/api/network` | — | NetworkState | A18 |
| POST | `/api/network/check` | `{"internet": <bool>}` (optional, default false) | NetworkState | A18 |
| GET | `/api/jobs` | — | `{"jobs": [Job, …]}`: every active job, then the last 20 finished ones (newest first) | A80 |
| GET | `/api/jobs/{id}` | — | Job (finished jobs are kept 10 min) | A80 |
| DELETE | `/api/jobs/{id}` | — | Job. Requests a cancel; the final `cancelled` state follows on `/ws/events`. Idempotent on a finished job. `409 unsupported` if the kind cannot be cancelled. | A80 |
| GET | `/api/stellarium` | — | StellariumState | A19 |
| POST | `/api/stellarium` | `{"host": string, "port": int 1024…65535}` (both optional, default the config's) | StellariumState; `502 bind_failed` with the reason | A19 |
| DELETE | `/api/stellarium` | — | StellariumState. Idempotent. | A19 |

**Server process (`boot_id`).** A random id drawn when the server process
starts, in `/api/health`, every `status` (event and route) and every
LogPage. Log `seq` numbers start again at 1 in a new process, so a client
that sees another `boot_id` on its first `status` after a reconnection knows
its log lines come from a restarted server (it marks the change and reads
`GET /api/logs?after=0`), however many lines the old process had numbered.

`{id}` of a device is `mount`, `camera`, `filterwheel` or `focuser`; anything
else is `404 not_found`.

#### Devices (A13-A15)

```
ConnectBody = {"mode": "alpaca"|"simulator",   // default "alpaca"
               "host": string,                // alpaca only; default config alpaca.host
               "port": int 1…65535}           // alpaca only; default config alpaca.port
```

- Every device connect runs in a worker thread, never on the event loop; a
  request blocks until that device answers or fails (≤ `connect-timeout` +
  10 s on Alpaca). While it runs, the device is `connecting` on
  `/ws/events` and every other route, the other devices included, keeps
  answering.
- `alpaca` with no host in the body and an empty `alpaca.host` is
  `400 invalid_argument` ("Enter the Seestar address first").
- **One link at a time.** All connected devices share one link
  (`mode`, `host`, `port`). Connecting a device with another link while a
  device is connected or connecting is `409 busy`; disconnect first.
- Connecting a device that is already connected with the same link returns
  at once (idempotent). A second request for a device that is still
  connecting with the same link waits for that attempt and returns its
  outcome.
- A successful Alpaca connect writes `alpaca.host` / `alpaca.port` to the
  config when they differ (as the Qt app did), with a `config` event.
- A failure answers `502 connection_failed` with the full driver text; the
  device's state is `error` with the same text in `info` and `error`, and an
  ERROR log line `"<Device>: <text>"` (topic `connection`).
- `POST /api/devices/connect-all` connects the mount, the camera, the filter
  wheel and the focuser **in that order**, skipping the devices already
  connected with the same link (no duplicate pollers). One device failing
  does not stop the others; the answer is `200` with every device's state,
  which the client reads to show failures. `409 busy` / `400` as above are
  checked before anything is connected.
- **Connect all claims its devices at once.** Every device it will connect
  becomes `connecting` with `info: "queued"` in the first `devices` event,
  before the address check: the profile is locked from that moment, clients
  show the run, and `DELETE /api/devices` (or `DELETE /api/devices/{id}`)
  can stop it at any time. When its turn comes, a device's `info` goes back
  to `null` (it is being opened). A device another request is already
  opening is not claimed: Connect all waits for that attempt.
- On Alpaca the address is then pre-checked once (see below): if nothing
  answers there, every claimed device is `error` with that reason at once
  (one ERROR log line "Cannot reach … (mount, camera, … not connected)"),
  instead of one timeout per device.
- `DELETE /api/devices` disconnects the camera (its exposure or live view is
  stopped first), the mount (auto-retry stopped), the filter wheel, the
  focuser. It also cancels a `connect-all` in progress, during the address
  check too: the device being opened is dropped and the queued ones are
  released unopened (no "… disconnected." line for them; that request then
  answers `200` with the states). `DELETE /api/devices/{id}` during a
  `connect-all` releases that device only (a queued one is never opened);
  the others still connect.
- In `simulator` mode the four devices exist: the v1 simulated camera and
  mount, plus a filter wheel (the active profile's slots, at slot 0) and a
  focuser (position 5 000 of 10 000), which only connect in API 2.
- **Mount auto-retry** (port of `device_session.py:155-160, 299-333,
  557-567` and `polling_worker.py:84-87`): after 3 consecutive failed mount
  polls the connection is declared lost: ERROR "Mount connection lost.",
  INFO "Retrying the mount every 10s — disconnect to stop.", the mount is
  `error` with `retrying: true`, and a reconnect is tried every 10 s until
  it succeeds (OK "Mount reconnected: <name>") or the mount is disconnected.
  Before that, failed polls behave as in API 1 (mount record `error`, "Mount
  not responding", "Mount responding again").

#### Unreachable addresses

Before a device is opened on Alpaca, the server makes one TCP connect to
`host:port` with the `--connect-timeout` budget (default 3 s; reported as
"Cannot reach <host>:<port> — timed out after 3 s" or the OS reason, such as
"connection refused"). This keeps a dead address from holding the Alpaca
library: alpyca 3.1.2 holds one process-wide lock (`Device._ctid_lock`)
during every HTTP request, so a request hanging on a black-hole address
would otherwise stall every other device's requests for up to 5 s. The
event loop never waits on any of this; tests measure `GET /api/status`
staying fast while a connect to a black-hole address runs.

#### Discovery (A16)

```
DiscoveryBody = {"port": int,                     // default config alpaca.port
                 "candidates": [string],          // default [config alpaca.host, profile ap_host]
                 "broadcast_timeout_s": number}   // 0.5…30, default 8
```

Starts a job of kind `discovery` (`409 busy` with `owner` while one runs):
the layered search of `argos.core.alpaca.discovery.discover_all`
(`discovery_worker.py:50-64`, candidates `device_session.py:205`), stopping
at the first layer that finds something:

| `stage` | done / total | What |
|---|---|---|
| `broadcast` | 0 / 3 | Alpaca UDP discovery broadcast on port 32227, replies collected for `broadcast_timeout_s`. |
| `probe` | 1 / 3 | HTTP probe (2 s) of each candidate's management API. |
| `subnet` | 2 / 3 | TCP sweep of the local /24 (0.4 s per host, 64 at a time), hits confirmed over HTTP. |
| `names` | 3 / 3 | Each device's `ServerName` (management API, 1 s each; `null` if it does not say). |

Result: `{"devices": [{"host": string, "port": int, "name": string|null}],
"method": "broadcast"|"probe"|"subnet"|null, "searched": ["broadcast", …]}`.
Every device found is returned (the Qt app kept only the first). Cancel
(`DELETE /api/jobs/{id}`) is honoured within about 0.25 s at any stage.
Logs (topic `discovery`): INFO "Starting Alpaca discovery…", OK
"Found <host>:<port>" per device, WARN "No Alpaca devices found (broadcast,
direct probes and subnet scan).", ERROR "Discovery: <message>", INFO
"Discovery cancelled.". The server never fills the address itself: the
client writes `alpaca.host` / `alpaca.port` with `PATCH /api/config` when
the observer picks a device.

#### Profiles (A17)

```
ProfilesState = {"active": string, "locked": bool, "locked_reason": string|null,
                 "profiles": [Profile, …]}            // catalogue order: s30pro, s30, s50
Profile = {"key", "name", "validated": bool, "caveats": [string],
           "aperture_mm", "focal_length_mm", "focal_ratio", "sensor", "pixel_size_um",
           "sensor_px": [w, h], "bayer", "arcsec_per_px", "fov_deg": [w, h],
           "adc_bits", "full_well_adu", "linearity_max_adu",
           "filter_names": [string], "ap_host",
           "overrides": {"<field>": value}}           // applied hardware.overrides (active profile only)
ProfileSummary = {"key", "name", "validated"}          // in the status record
```

Numbers are the profile's own (`argos.core.hardware.catalog`); derived ones
(`focal_ratio`, `arcsec_per_px` per full-resolution pixel, `fov_deg`) are
computed by `TelescopeProfile`, never stored. The active profile shows its
values with `hardware.overrides` applied. `PUT /api/profile` writes
`hardware.profile`, makes the profile active with the overrides, and
announces it (`config` event, `status` event, INFO log "Telescope profile:
…"). It is refused with `409 busy` while any device is connecting,
connected, busy or retrying ("Disconnect the equipment before changing the
telescope: it sets plate scale, sensor geometry and FITS metadata.");
choosing the active key again is always accepted. `hardware.profile` is
read-only through `PATCH /api/config`: this route is its only writer.

#### Network (A18)

```
NetworkState = {"seestar": bool|null,      // null = no Seestar address configured
                "internet": bool|null,     // null = not checked since start-up
                "host": string|null, "port": int|null,   // what was probed
                "t": ISO|null,             // last Seestar probe
                "internet_t": ISO|null}    // last internet check
```

A Qt-free port of `network_monitor.py:40-84`, with the owner's decision
Q-G13: every 10 s (and at once after `alpaca.host` / `alpaca.port` change)
the server makes one TCP connect (1.5 s) to the configured Seestar address.
The internet is **never** probed in the background: `POST
/api/network/check` with `{"internet": true}` checks it on demand (TCP to
1.1.1.1:53, then 8.8.8.8:53, 1.5 s each), for instance before an online
lookup the observer asked for. Without a body it re-probes the Seestar only.

#### Stellarium bridge (A19)

```
StellariumState = {"running": bool,
                   "host": string|null, "port": int|null,  // of the last start
                   "clients": int,                         // Stellarium connections now
                   "error": string|null,                   // the last start's bind error
                   "last_goto": {"ra_hours": float, "dec_deg": float, "t": ISO,
                                 "outcome": string}|null}  // since the last start
```

A Qt-free port of `stellarium_worker.py:24-130` and `DeviceSession.
start_stellarium / stop_stellarium` (`device_session.py:783-816`) around
the unchanged core server `argos.core.stellarium.server.StellariumServer`
(Stellarium Telescope Protocol v1.0). It runs on its own thread and event
loop, so a Stellarium client never holds the HTTP loop.

- `POST /api/stellarium` writes `stellarium.host` / `stellarium.port` to
  the config when they differ (the Qt app did so on start), stops a running
  bridge, and answers once the socket listens. A bind failure (port in use)
  answers `502 bind_failed` with the reason, which stays in `error` (the Qt
  card never showed it); logs (topic `planetarium`): INFO "Stellarium server
  starting on <host>:<port>", OK "Stellarium bridge listening on …", ERROR
  "Stellarium: bind <host>:<port> failed — <reason>".
- The mount's position is pushed to Stellarium's reticle with every mount
  telemetry event while the mount is connected (`device_session.py:550-551`).
- A GoTo from Stellarium slews the mount (`shell.py:346-353`): INFO
  "Stellarium GoTo → RA … h, Dec …°"; `last_goto.outcome` is `slewing`, or
  `mount not connected` / `mount parked` / the driver's error, with a WARN
  "Stellarium GoTo not sent: <outcome>". The target-name suggestion
  (`target_suggestions`, `stellarium.online_target_lookup`) comes with the
  Observe wave.
- A `stellarium` event (the whole record) follows every change: start,
  stop, a client connecting or leaving, a GoTo. The server stops the bridge
  at shutdown.

#### Jobs (A80)

```
Job = {"id": string, "kind": "discovery"|…,
       "state": "queued"|"running"|"done"|"failed"|"cancelled",
       "done": number, "total": number|null,   // total null = indeterminate
       "stage": string|null, "message": string|null,
       "started_utc": ISO, "ended_utc": ISO|null,
       "result": object|null,                  // set when done
       "error": {"code", "message"}|null,      // set when failed
       "cancellable": bool, "cancel_requested": bool,
       "seq": int}                             // increases on every published change
```

- Kinds in API 2: `discovery`. Reserved by `web/spec/README.md` §4.2:
  `site_search`, `support_bundle`, `sessions_scan`, `session_open`,
  `file_solve`, `file_catalogue`, `rerun`, `export`.
- Progress is published on `/ws/events` as `job` events, at most 4 per
  second per job; the final state is always sent.
- Cancel is honoured at a safe boundary of the kind (for discovery: within
  about 0.25 s). A cancelled job ends `cancelled` with `result: null`.
- A client that reconnects re-reads `GET /api/jobs`; nothing is lost when a
  page reloads.

#### App info (A1)

```
AppInfo = {"name": "ARGOS", "version": "0.4.2", "api": 2,
           "python": "3.11.5", "platform": "macOS-…",
           "paths": {"config": path|null, "config_dir": path|null,
                     "sessions": path, "presets": path, "calibrations": path,
                     "diagnostics": path|null, "log_file": path|null},
           "profile": ProfileSummary, "log_level": "INFO",
           "diagnostics_enabled": bool, "astap_configured": bool,
           "licence": "GPL-3.0-or-later", "licence_name": "GNU GPL v3 or later",
           "copyright": "Copyright © 2026 Argos contributors",
           "author": "Jules Perret",
           "description": "Scientific acquisition and differential photometry for ZWO Seestar telescopes.",
           "credits": [{"name", "use", "licence", "url"}],
           "project_url": "https://github.com/jperret21/argos",
           "docs_url": "https://perretjules.com/argos/"}
```

`config` is `null` when the server runs on an in-memory configuration
(tests); `log_file` is `null` when file logging is off or failed.
`astap_configured` is true when `astrometry.astap_path` is set (as the Qt
support-bundle summary, `shell.py:515`). `credits` lists the server-side
software; the front-end adds its own (fonts, Svelte, uPlot, Tauri).

#### Logs (A2)

```
LogEntry = {"type": "log", "id": int, "seq": int,          // id == seq, increasing
            "level": "debug"|"cmd"|"info"|"ok"|"warning"|"error",
            "source": string, "topic": string,
            "message": string, "t": ISO}
LogPage  = {"entries": [LogEntry, …],   // oldest first, seq > after
            "first_seq": int|null,      // oldest line still in the ring
            "last_seq": int|null,       // newest line
            "truncated": bool,          // true when lines after `after` were already dropped
            "boot_id": string}          // the server process these seq numbers belong to
```

- Lines are numbered and handed to the event stream under one lock, so they
  leave in `seq` order even when several threads log at once: a gap in the
  `seq` a client receives is a real gap (lines dropped by compaction), never
  a reordering.

- The server keeps the last **5 000** lines in a ring. `GET /api/logs`
  returns the lines with `seq > after` (default 0, i.e. everything kept),
  oldest first, at most `limit` (default 1 000, 1…5 000); `level` keeps that
  level and the more severe ones (`debug` < `cmd` < `info` < `ok` <
  `warning` < `error`).
- `source` names the producer: `server`, `mount`, `camera`, `filterwheel`,
  `focuser`, `discovery`, `network`, `config`, `profile`, `core` (a
  WARNING-and-above record of `argos.core`, such as an Alpaca driver
  warning). `topic` groups lines for views: `connection`, `discovery`,
  `planetarium`, `config`, `camera`, `mount`, `network`, `app`. The
  Connection screen's log shows the topics `connection`, `discovery` and
  `planetarium`.
- `debug` lines are recorded only while `ui.log_level` is `DEBUG`.
- Levels v1 clients already knew (`info`, `warning`, `error`) keep their
  meaning; `cmd` marks an action the observer started (it is also the
  `activity` text), `ok` a success.

#### Configuration (A8-A10)

```
ConfigSnapshot    = {"values": {"<key>": value, …}, "meta": {"<key>": KeyMeta, …},
                     "revision": int, "path": path|null}
KeyMeta           = {"type": "bool"|"int"|"float"|"str"|"path"|"host"|"list"|"object",
                     "default": value, "nullable": bool,
                     "min": number|null, "max": number|null, "step": number|null,
                     "options": [{"value": value, "label": string}]|null,
                     "unit": string|null, "label": string, "help": string,
                     "used_by": [string], "category": Category,
                     "advanced": bool, "read_only": bool}
ConfigPatchResult = {"values": {…}, "changed": {"<key>": value, …},
                     "warnings": [{"key": string, "message": string}], "revision": int}
Category = "connection"|"observer_site"|"instrument"|"plate_solving"|"catalogues"|
           "photometry"|"data_storage"|"privacy_diagnostics"|"appearance"|"observe"
```

- Keys are the dotted names of `~/.argos/config.json`
  (`web/spec/02-connection-and-settings.md` appendix A), so the Qt app and
  the server read and write the same file during the transition. `values`
  holds exactly the keys of `meta`. Not exposed: Qt window state
  (`ui.window_*`, `ui.shell.*`, `ui.*.layout`), the dead keys of Q-C7
  (`ui.language`, `catalog.field_stars_max_results`,
  `catalog.named_objects_max_results`, `camera.adc_bits`), internal markers
  (`catalog.display_limit_version`, `diagnostics.local_opt_in_v1`) and the
  legacy `observer.latitude/longitude/elevation`. They are kept untouched
  in the file.
- `hardware.overrides.full_well_adu`, `….linearity_max_adu` and
  `….ap_host` are the per-unit corrections of the active profile (`null` =
  use the profile's value, the default). Writing one also writes the legacy
  key the Qt app still reads (`camera.full_well_adu`,
  `camera.linearity_max_adu`, which are exposed read-only), so both UIs
  agree (decision Q-C1).
- **PATCH** is one commit: every key is validated first (strict types as in
  request bodies: an `int` key refuses `80.0` and `true`; a `float` key
  accepts integers; ranges and options from `meta`); one invalid key fails
  the whole request with `400 invalid_argument` and `fields`, and nothing
  is written. Unknown keys and `read_only` keys are invalid too. Then the
  file is re-read if another program (the Qt app) changed it since the
  server read it, the keys are applied, and the whole file is written
  atomically (temporary file in the same folder, `fsync`, rename): a crash
  leaves the old or the new file, never a mix. An unchanged value is not
  written and not reported in `changed`.
- `path` values accept `~`, are stored expanded and must be absolute. A
  folder that does not exist yet is accepted with the warning "does not
  exist, it will be created"; an existing folder (or file's folder) that is
  not writable is refused ("not writable"). `astrometry.astap_path` and
  `astrometry.database_path` may be empty (auto-detect).
- Normalisation: strings are stripped; `observer.obscode` is upper-cased;
  `site.favorites` items are `{"name", "latitude", "longitude",
  "elevation"}`.
- Side effects, applied when the commit succeeds: `data_paths.*` caches and
  the calibration folder are applied to the core modules at once;
  `diagnostics.enabled` also records the explicit opt-in
  (`diagnostics.local_opt_in_v1`, as `configuration_page.py:1200-1206`);
  `ui.log_level` changes the server's log level live (stderr, file and the
  `debug` lines of the log ring); `alpaca.host` / `alpaca.port` re-probe the
  Seestar; `stellarium.host` other than a loopback address draws the
  warning "reachable from the network: Stellarium on another computer can
  drive the mount" (Q-C3). Reserved for later waves: `catalog.*` will
  trigger a debounced field catalogue refetch (W4), `imaging.star_radius_px`
  a re-measure of the last frame (W4), photometry geometry `409 run_active`
  during a sequence (W6).
- Every successful commit, and every change found in the file written by
  another program, is announced with a `config` event to every client.
  `revision` counts those changes since the server started (it restarts at
  0 with the server; compare it within one connection only).

## State records

```
ConnectionState = {"state": "disconnected"|"connecting"|"connected"|"error",
                   "mode": "simulator"|"alpaca"|null, "device_name": string|null,
                   "message": string|null}                 // message: error text

CameraState     = {"state": "idle"|"exposing"|"downloading"|"live"|"error",
                   "exposure_s": float, "gain": int,       // current or last request
                   "last_frame_seq": int|null,             // newest published frame
                   "sensor": {"width": int, "height": int, "bitpix": 16,
                              "bayer": string|null}|null}  // null when disconnected

MountState      = {"state": "parked"|"idle"|"slewing"|"tracking"|"error",
                   "ra_hours": float, "dec_deg": float,
                   "alt_deg": float|null, "az_deg": float|null,
                   "tracking": bool, "pier_side": "east"|"west"|null,
                   "target": {"ra_hours": float, "dec_deg": float}|null}

DevicesState    = {"mount": DeviceState, "camera": DeviceState,     // API 2
                   "filterwheel": DeviceState, "focuser": DeviceState}

DeviceState     = {"state": "disconnected"|"connecting"|"connected"|"busy"|"error",
                   "name": string|null,       // driver's name once connected
                   "info": string|null,       // one line: name, "slewing", filter slot, the error,
                                              // or "queued" (claimed by a Connect all, not opened yet)
                   "error": string|null,      // full error text while state is "error"
                   "retrying": bool,          // mount auto-reconnect in progress
                   "warnings": [string],      // e.g. profile mismatch, mount clock off
                   "link": {"mode": "simulator"|"alpaca", "host": string|null,
                            "port": int|null}|null,
                   "since": ISO}              // last change of state
```

- A single capture goes `exposing` → `downloading` → `idle`. A live view
  stays `live`, and `last_frame_seq` increases with every frame.
- `last_frame_seq` is the `seq` of the newest frame published on
  `/ws/frames`, whether it came from a capture, a live view or a file.
- `sensor.bayer` is `null` for the mono simulator. For a Seestar it is the
  active hardware profile's CFA pattern, for example `"GRBG"`, and frames are
  raw mosaics with `channels: 1`.
- While the mount is disconnected, its record is a placeholder (`idle`, zero
  coordinates, null alt/az). Check `devices.mount.state` (`connected` or
  `busy`) before showing it, and `devices.camera.state` before offering an
  exposure. **Not** `connection.state`: since API 2 it reads `connected`
  when either the camera or the mount is, so the camera alone would make the
  placeholder mount record look real.
- `target` is the last GoTo target. It survives `stop`, is cleared by
  `park`, and is reset on disconnect.
- **ConnectionState is derived** (API 2) from the camera and mount device
  states: `connecting` if either is connecting; else `connected` if either
  is connected or busy; else `error` if either is in error (`message` = its
  text); else `disconnected`. `mode` is their link's mode, `device_name`
  the mount's name ("ARGOS Simulator (Seestar S50)" for the simulator), or
  the camera's when only the camera is connected.
- **DeviceState** (port of the Qt `device_state_changed` emits,
  `device_session.py:292-298, 346, 363-366, 427, 445-448, 457, 485-488,
  500, 553-567`): `busy` means the mount is slewing (`info` "slewing") or
  the camera exposes, downloads or runs live view (`info` "exposing",
  "downloading", "live"). The error text is never cut (Qt cut it to 48
  characters). `warnings` of the camera hold the profile mismatch notes
  (`device_session.py:368-390`); those of the mount the clock and
  coordinate-system warnings (`device_session.py:276-291`).

## WebSocket `/ws/events?token=…` (server → client, JSON text)

| Message | When |
|---|---|
| `{"type": "status", "connection": …, "camera": …, "mount": …, "devices": …, "profile": …}` | Immediately on connect, then on every state transition: connection change, any device-state change, a profile change, any camera change, or a mount change of `state`, `tracking`, `pier_side` or `target`. |
| `{"type": "camera", "camera": CameraState}` | On every camera change, including each new frame in live view. |
| `{"type": "mount", "mount": MountState}` | Telemetry while connected: every 0.25 s for the simulator (4 Hz) and every 2 s for a Seestar, the Qt app's polling period. |
| `{"type": "devices", "devices": DevicesState}` | API 2. On every device-state change (with a `status`). |
| `{"type": "network", …NetworkState}` | API 2. After every Seestar probe (every 10 s) and every on-demand check; once right after the first `status`. |
| `{"type": "activity", "text": string, "source": string, "t": ISO}` | API 2. The last action started **or its outcome** (status-bar activity text). Starts end with "…" ("Connecting mount 192.168.1.42:32323…", "Searching for Alpaca devices…", "Exposing 2 s…", "Slewing"); every outcome replaces them, without an ellipsis: "<Device> connected", "<Device>: <full error>", "Equipment ready" or "3 of 4 devices ready · camera failed" (end of a Connect all), "Cannot reach <host>:<port> — … (… not connected)", "<Device> disconnected", "Disconnected", "Discovery: 2 devices found", "Discovery: no Alpaca device found", "Discovery cancelled", "Discovery failed: …", "Frame #12 received (2 s)", "Camera: <error>", "Slew finished", "Slew stopped", "Mount connection lost · retrying every 10 s", "Mount reconnected". A start is also a `cmd` log line, unless a more detailed line says the same; outcomes have their own OK / ERROR lines. Sent once right after the first `status` when there is one. |
| `{"type": "config", "changed": {key: value}, "values": {…}, "revision": int, "source": "api"\|"file"}` | API 2. After every config commit (`source: "api"`), or when the server finds the file changed by another program (`"file"`). `values` is the full value set, so the newest event alone is enough. |
| `{"type": "job", "job": Job}` | API 2. Job progress (≤ 4 Hz per job) and the final state. |
| `{"type": "stellarium", …StellariumState}` | API 2. The Stellarium bridge's record after every change; once right after the first `status` (after `network`). |
| `{"type": "log", …LogEntry}` | Server events, plus WARNING-and-above records from `argos.core`, such as Alpaca driver warnings (core INFO, logged on every exposure, stays in the server log; a core message repeated within 60 s is sent once). Right after the first `status` (and `network`, `stellarium`, `activity`, in that order), a new client receives the last 200 log lines, oldest first, so a page opened mid-session shows what happened before; older lines come from `GET /api/logs`. A client that reconnects drops the lines whose `seq` it already holds. |

A camera change therefore sends both a `camera` message and a `status`
message. Coordinate changes alone send only `mount`.

Messages arrive in order. A client that keeps up sees every transition,
for example `connecting` before `connected`, or `exposing` → `downloading`
→ `idle`.

A slow client never makes the server buffer without bound. Once 256
messages are pending for a client, its backlog is compacted: only the
newest snapshot of each type (`status`, `camera`, `mount`, `devices`,
`network`, `activity`, `config`, `stellarium`) and the newest `job` event **of each job**
are kept, then the oldest log lines are dropped. A lagging client loses
history, never the current state. Every snapshot is complete, so a client
can always replace its state with the latest one it received. Log lines
carry `seq` and job events `job.seq`: a client that sees a gap in the log
`seq` re-reads `GET /api/logs?after=<last seq it holds>`.

## WebSocket `/ws/frames?token=…` (server → client, binary)

One binary message per frame. Frames are latest-wins: the server keeps at
most one pending frame per client, and a slow client skips frames. On
connect, the most recent frame (if any) is sent at once. At most 8 frame
clients are served at a time; a ninth is closed with code 1013 (try again
later). The CLI selects uvicorn's `websockets-sansio` implementation when
available, the one the bounded-memory behaviour was measured with.

```
bytes [0, 4)            uint32 little-endian N = byte length of the JSON header
bytes [4, 4+N)          UTF-8 JSON header
bytes [4+N, offset)     zero padding; offset = pixel_offset, a multiple of 8
bytes [offset, …)       width*height*channels uint16 little-endian,
                        row-major, channels interleaved,
                        row 0 = TOP of the image as displayed
```

Header:

```json
{"seq": 12, "width": 1080, "height": 1920, "channels": 1, "dtype": "uint16",
 "pixel_offset": 256, "exposure_s": 2.0, "timestamp": "2026-11-01T21:04:05.123Z",
 "source": "simulator",
 "stats": {"min": 1814, "max": 65535, "median": 2000.0, "mad": 25.0, "mean": 2016.4}}
```

- **Orientation.** Row 0 is the first row of the array as the camera
  download (`Camera.get_image_array`, `(height, width)`) or the FITS file
  delivers it, with no flip. The Qt viewer shows the same row at the top
  (`fits_viewer.py`: pyqtgraph `ImageView`, row-major, y-axis down).
  Rotating a portrait frame to landscape is a display choice left to the
  front-end, as with the Qt viewer's "auto" rotation.
- **Stats** are exact over all pixels, with channels pooled. They come from
  one 65 536-bin histogram, so `median` matches `numpy.median`, including the
  mean of the two middle values when the count is even. `mad` is the raw
  median absolute deviation: multiply by 1.4826 for a Gaussian σ.
- **Alignment.** Because `pixel_offset % 8 == 0`, a browser can view the
  pixels without copying:
  `new Uint16Array(buf, pixel_offset, width*height*channels)`. All current
  browser platforms are little-endian.
- **`source`** is `"simulator"`, `"alpaca"` or `"file"`.
- **`timestamp`** is the end of the exposure for a camera frame (shutter
  closed, before the download), and `DATE-OBS` (or the file's modification
  time) for a file.
- **`exposure_s`** is the requested exposure for a camera frame, and
  `EXPTIME`/`EXPOSURE` (or 0) for a file.

Decoding in TypeScript:

```ts
const dv = new DataView(buf);
const n = dv.getUint32(0, true);
const header = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, n)));
const pixels = new Uint16Array(buf, header.pixel_offset,
                               header.width * header.height * header.channels);
```

## Opening FITS files

`POST /api/camera/open-fits` accepts `.fit`, `.fits` and `.fts`, in any
letter case. It reads the first image HDU and converts it for display only;
the file is never modified:

- Integer data, after astropy applies BZERO/BSCALE, is clipped to 0…65535.
- Float data in [0, 1], Siril's 32-bit default, is scaled by 65535. Other
  float data is clipped. NaN and −inf become 0, +inf (a saturated pixel)
  becomes 65535. The conversion works on one float32 copy.
- The size is read from the header first: more than 16384 px on a side
  (the viewer's GPU texture limit) or more than 100 M samples is refused
  with `400 invalid_fits` before any pixel is loaded.
- A `(3, H, W)` cube becomes `(H, W, 3)` with `channels: 3`. A `(1, H, W)`
  cube becomes 2-D.

## Simulator

The `simulator` mode emulates a Seestar S50 as it delivers frames: 1080 px
wide by 1920 px high, 16-bit, mono.

- **Camera.** The background sits near 2000 ADU at the reference settings
  (2 s at gain 80): a 1600 ADU pedestal plus 200 ADU/s of sky, with a 4 %
  vertical gradient. Noise is shot noise (3 ADU/e⁻) plus 12 ADU of read
  noise, giving a MAD of about 25 ADU at the reference settings.
- **Stars.** 240 Gaussian stars with a 2.8 px FWHM and ±4 % seeing jitter.
  Their brightness follows a Pareto law, and four are saturated at the
  reference settings. Hot pixels stay fixed on the sensor. Between frames
  the field drifts by about 5 px with 0.25 px of jitter.
- **Gain** scales everything by 10^((gain−80)/200), since ZWO gain steps
  are 0.1 dB.
- **Timing.** The exposure time is actually waited, and stop interrupts it.
  Frame *n* is a deterministic function of (seed, n, exposure, gain).
  Rendering takes about 20 ms and encoding about 4 ms at full size.
- **Mount.** Slews at 4°/s per axis and tracks at the sidereal rate. It
  starts parked at the celestial pole, at a fixed site (APC, Paris:
  48.8277° N, 2.3826° E).
  - Alt/az come from a closed-form GMST and spherical trigonometry. They
    ignore precession, nutation and refraction, about 0.4° from J2000 in
    2026, which the tests check against astropy.
  - `pier_side` follows the German-equatorial convention from the hour
    angle. A real Seestar is alt-az and reports `null`.
- **Filter wheel and focuser** (API 2). Connect-only stand-ins so the four
  device rows can be exercised: the wheel reports the active profile's
  slots at slot 0, the focuser "ARGOS Simulator focuser" at position 5 000.

## What API 2 adds

| Row | Addition |
|---|---|
| A1 | `GET /api/app/info` |
| A2 | Log lines v2: `id`/`seq`, levels `debug`/`cmd`/`ok`, `source`, `topic`; 5 000-line ring; `GET /api/logs` |
| A3 | Start-up: config folder, rotating file log, crash reports, `ui.log_level`, data paths and profile applied before the first request; `--config-dir`, `--log-dir`, `--connect-timeout` |
| A4 | `activity` event |
| A8-A10 | `GET /api/config` (values + meta), `PATCH /api/config` (validated, atomic), `config` event |
| A13 | `devices` in the status record and the `devices` event; ConnectionState derived from it |
| A14-A15 | Per-device connect / disconnect, connect-all (skips connected devices), disconnect-all |
| A16 | `POST /api/discovery` as a cancellable job |
| A17 | `GET /api/profiles`, `PUT /api/profile`; `profile` in the status record |
| A18 | `network` event, `GET /api/network`, `POST /api/network/check` |
| A19 | Stellarium bridge: `GET` / `POST` / `DELETE /api/stellarium`, `stellarium` event (brought forward from wave 3) |
| A80 | Job model: `job` event, `GET /api/jobs`, `GET` / `DELETE /api/jobs/{id}` |
| — | `boot_id` in `/api/health`, `status` and LogPage (log `seq` restarts at 1 in a new process); Connect all claims its devices (`info: "queued"`) before the address check; activity outcomes |
