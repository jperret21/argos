# ARGOS server protocol — API 2

The contract between the headless Python server (`argos.server`) and the web
front-end. `GET /api/health` reports `"api": 2`; any breaking change to what
follows bumps that number.

API 2 is **additive** over API 1: every v1 route, record and event keeps its
meaning and shape; v2 adds routes, events, record fields and log levels.
Section [What API 2 adds](#what-api-2-adds) lists them; wave 1 of the web
UI (`web/spec/README.md` §7, rows A1-A4, A8-A10, A13-A18, A80, plus the
Stellarium bridge A19 brought forward from wave 3 so that every Qt
Connection control has its web control) is what ships in API 2. Wave 2
(Settings: rows A5, A6, A11, A67 list only, A81-A84, plus the site check of
`web/lab/PROPOSAL.md` §7) adds the routes of
[API 2 routes, wave 2](#api-2-routes-wave-2), still additive: `"api"` stays 2.

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
  probe), and for explicit requests: discovery (`POST /api/discovery`), the
  internet check (`POST /api/network/check` with `internet: true`) and the
  place search (`POST /api/site/search`: OpenStreetMap Nominatim, then
  Open-Meteo for the elevation). The site check computes offline: astropy
  never downloads an IERS or leap-second table for it.
- **Files.** The server browses only the observer's home folder and the
  ARGOS data folders (`GET /api/fs/list`, see
  [File listing](#file-listing-a11)); it reads session folders only to list
  them and to copy redacted metadata into a support bundle the observer
  asked for, and never writes into a session. Wave 2 writes only the
  support-bundle ZIP (at the destination the observer chose, inside those
  folders, or in a private temporary folder for a download) and deletes
  only the catalogue cache files of `DELETE /api/caches/{kind}`.

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
| 400 | `session_invalid` | (wave 2) A support bundle's `session_dir` holds no `session.json`. |
| 401 | `unauthorized` | Bad or missing token. |
| 403 | `forbidden_host` / `forbidden_origin` | Request for a foreign `Host` name, or from a foreign `Origin` (see Security). |
| 403 | `forbidden_path` | (wave 2) A path outside the folders the server may browse (home and the data folders), directly or through a symbolic link; or a folder the OS refuses to list. |
| 404 | `not_found` | Unknown route, unknown device id, unknown (or expired) job id, or `open-fits` on a missing file. Wave 2: a missing folder in `GET /api/fs/list`, an unknown cache kind, a job with nothing to download. |
| 405 | `method_not_allowed` | Wrong HTTP method on a known route. |
| 409 | `not_connected` | Camera or mount command with that device not connected. Also a mount command whose device was disconnected while it ran: its result is discarded. |
| 409 | `busy` | Exposure requested while the camera exposes, downloads, is live, or is still stopping. `POST /api/connection` or a device connect while devices are connected to **another** address or mode. `PUT /api/profile` while a device is connected (message says why). A job start while a job of the same kind runs (`owner` = its id). |
| 409 | `parked` | `goto` or `tracking` on a parked mount. |
| 409 | `not_live` | `PATCH /api/camera/live` while live view is not running. |
| 409 | `unsupported` | `DELETE /api/jobs/{id}` on a job kind that cannot be cancelled. |
| 409 | `file_exists` | (wave 2) A support bundle destination that exists, without `"overwrite": true`. |
| 409 | `not_ready` | (wave 2) `GET /api/jobs/{id}/download` while the job still runs. |
| 409 | `run_active` | Reserved: a photometry-geometry config change while a sequence runs (no sequence engine in API 2 yet, never sent). |
| 500 | `internal_error` | Any unexpected failure; the traceback is in the server log. The answer keeps the CORS headers, so the browser can read it. |
| 502 | `connection_failed` | The device could not be reached or refused to connect. Its device state becomes `error` with the full text. |
| 502 | `device_error` | A connected device refused a command or stopped answering. |

Codes reserved by `web/spec/README.md` §4.1 for later waves: `not_solved`,
`no_target`, `no_comparison`, `no_frames`, `site_missing`.

A failed job carries `{code, message}` in its `error` (see Jobs); wave 2
adds the job error codes `lookup_failed` (place search: no network answer),
`not_found` (place search: no place) and `bundle_failed` (the ZIP could not
be written; the message is the OS reason).

## HTTP routes

Bodies and responses are JSON. All routes except health need the token.

### API 1 routes (unchanged)

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/health` | — | `{"ok": true, "version": "0.4.2", "api": 2, "boot_id": "<16 hex>"}` (v2 adds `boot_id`) |
| GET | `/api/status` | — | `{"boot_id": string, "connection": ConnectionState, "camera": CameraState, "mount": MountState, "devices": DevicesState, "profile": ProfileSummary, "site_check": SiteCheck}` (v2 adds `boot_id`, `devices`, `profile`; wave 2 adds `site_check`) |
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

- Kinds in API 2: `discovery`; wave 2 adds `site_search` and
  `support_bundle` (see [API 2 routes, wave 2](#api-2-routes-wave-2)).
  Reserved by `web/spec/README.md` §4.2: `sessions_scan`, `session_open`,
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
           "copyright": "Copyright © 2026 ARGOS contributors",
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
- **Two clients** (two browser tabs, or the web UI beside the Qt app) see
  the same configuration: commits are serialised by the store lock, each one
  re-reads a file another program changed before applying its keys, and the
  `config` event of every commit carries the full `values`, so a client
  that applies the newest event (highest `revision`) holds what `GET
  /api/config` returns. Two PATCHes of different keys never lose either;
  two PATCHes of the same key end with the later commit's value on every
  client. `tests/server/test_settings_wave2.py` checks it.

## API 2 routes, wave 2

Wave 2 (`web/spec/README.md` §7 "Settings") adds the routes below, still
under `"api": 2` (additive). Every route needs the token, answers JSON
unless stated, and never blocks the event loop.

| Method | Path | Body | Returns | Row |
|---|---|---|---|---|
| POST | `/api/support-bundle` | SupportBundleBody | `202 {"job_id", "job"}` (job `support_bundle`) | A5 |
| GET | `/api/jobs/{id}/download` | — | the job's file (`application/zip`, attachment) | A5 |
| GET | `/api/diagnostics/crash-reports?since=<ISO>` | — | CrashReports | A6 |
| GET | `/api/fs/list?path=&kind=&ext=&counts=&hidden=` | — | Listing | A11 |
| GET | `/api/sessions?offset=&limit=` | — | SessionPage | A67 (list only) |
| GET | `/api/astrometry/astap?path=&database_path=&database=` | — | AstapState | A81 |
| POST | `/api/site/search` | `{"query": string}` | `202 {"job_id", "job"}` (job `site_search`) | A82 |
| GET | `/api/caches` | — | `{"caches": [Cache, …]}` | A83 |
| DELETE | `/api/caches/{kind}` | — | `{"cache": Cache, "removed": int}` | A83 |
| GET | `/api/catalogues/essential` | — | EssentialCatalogue | A84 |
| GET | `/api/site/check` | — | SiteCheck | PROPOSAL §7 |
| POST | `/api/site/check` | — | SiteCheck (checked now, from the latest mount reading) | PROPOSAL §7 |

Job kinds in wave 2: `discovery`, `site_search`, `support_bundle`. Still
reserved: `sessions_scan` (the session list is fast enough without it, see
below), `session_open`, `file_solve`, `file_catalogue`, `rerun`, `export`.

### Config meta, wave 2 additions (A8)

```
KeyMeta           += {"read_only_reason": string|null,   // why a read_only key cannot be PATCHed
                      "path_kind": "dir"|"file"|"exe"|null, // what a "path" key names; null otherwise
                      "personal": bool}                  // the observer's own value: no default to reset to
ConfigSnapshot    += {"omitted": [{"key": string, "reason": string}, …]}
```

- `read_only_reason` is set on every `read_only` key, written for the
  observer (shown under the field, so it names no route and no decision
  code): `hardware.profile` ("Changed on the Connection screen (Instrument
  card), which checks that no equipment is connected."; the route is `PUT
  /api/profile`), the two legacy
  `camera.*` mirrors, and `hardware.overrides.adc_bits` (new in wave 2,
  `int|null`, read-only by decision Q-C1: the ADC depth is the sensor's, set
  by the profile).
- A `PATCH` of a read-only key is refused with that same reason:
  `fields: {"hardware.profile": "is read-only. Changed on the Connection
  screen (Instrument card), which checks that no equipment is connected."}`
  (wave 2 review: the refusal named `PUT /api/profile`). No `help`, `label`
  or reason names an API route, a config key or a JSON shape
  (`tests/server/test_config.py`).
- `personal` (wave 2 review) is true for `observer.name`,
  `observer.obscode`, `site.name`, `site.latitude`, `site.longitude` and
  `site.elevation`: their shipped default ("" or 0) is a placeholder, not
  a value to go back to. The web form offers no "Reset to the default" and
  Restore defaults leaves them alone, so one click never moves the site to
  0°, 0° or blanks the AAVSO code (the class of the 2026-09-25 wrong-site
  incident). The server still accepts any valid value for them.
- `photometry.default_band` has `options` (wave 2 review): the AAVSO
  filter codes TG, TB, TR, V, B, U, R, I, CV, CR, CBB, SU, SG, SR, SI, SZ,
  J, H, K, with words ("TG · Tri-colour green"); another value is `400 invalid_argument`
  ("must be one of …"), so a typo can no longer write a wrong FILT into
  every report. A configuration file that already holds another code is
  read as it is (validation applies to `PATCH` only).
- `catalog.identification_max_objects` labels its options with the
  numbers ("100" … "1 600", U+202F), so the five fit a segmented control;
  the names (fast, balanced, detailed, dense field) are in its help.
- `path_kind` says what a `path` key names, as the server validates it: a
  folder (`dir`), a file (`file`: the two JSON caches) or a program (`exe`:
  `astrometry.astap_path`). The web FilePicker opens in that mode.
- `omitted` lists the keys of `web/spec/02-connection-and-settings.md`
  appendix A that are deliberately **not** in `meta`, each with its reason
  (Qt window state, the dead keys of Q-C7, internal markers, the legacy
  `observer.*` site). With `meta`, it covers every key of appendix A: the
  wave 2 exit criterion ("every key editable or deliberately read-only")
  is checked by `tests/server/test_settings_wave2.py` against that table.
- Changing `site.name`, `site.latitude` or `site.longitude` re-runs the
  site check (below) on the first mount reading that is not a slew once
  the site has stayed unchanged for 2 s.

### File listing (A11)

```
GET /api/fs/list?path=<absolute>&kind=any|dir|file&ext=.fits,.fit,.fts&counts=fits&hidden=false

Listing = {"path": path,            // the folder listed, symbolic links resolved
           "parent": path|null,     // null at an allowed root's top (nothing above to browse)
           "root": path,            // the allowed root that contains it
           "places": [Place, …],    // shortcuts for the picker's side list
           "entries": [Entry, …],   // folders first, then files; each group by name (case-insensitive)
           "truncated": bool}       // more than 5 000 entries: the first 5 000 are listed
Place   = {"id": "home"|"desktop"|"sessions"|"presets"|"calibrations"|"diagnostics"|"config",
           "label": string, "path": path, "exists": bool}
Entry   = {"name": string, "kind": "dir"|"file", "size": int|null,   // null for a folder
           "mtime": ISO, "symlink": bool,
           "fits_count": int|null}  // with counts=fits: .fit/.fits/.fts files directly inside a folder
```

Read-only and limited (decisions D20, Q-G7, Q-R4): the server lists only
folders inside **its allowed roots**: the observer's home folder and the
ARGOS data folders (`sessions_path`, `data_paths.sequence_presets_directory`,
`data_paths.camera_calibration_directory`, the five catalogue caches, the
config folder and the log folder), each taken with its symbolic links
resolved, so a data folder moved to another disk and linked from home
stays browsable.

- `path` defaults to `sessions_path` (home when that folder does not exist
  yet). It must be absolute (`~` is expanded); a relative path is `400
  invalid_argument`. It is resolved (`realpath`) before the check, so
  neither `..` nor a symbolic link can leave the roots: outside them is
  `403 forbidden_path`. A missing folder is `404 not_found`; a file is `400
  invalid_argument` ("not a folder"); a folder the OS refuses to read is
  `403 forbidden_path` with the OS reason.
- Entries whose symbolic link points outside the roots, or nowhere, are
  left out (never shown, never followed). Hidden names (leading `.`) are
  left out unless `hidden=true`.
- `kind=dir` lists folders only; `kind=file` lists folders (to navigate)
  and the files whose suffix is in `ext` (comma-separated, any letter case;
  every file when `ext` is empty); `kind=any` (default) lists everything,
  `ext` still filtering files.
- Nothing is read inside files and nothing is written. `fits_count` scans
  one level (at most 10 000 names per folder).

### Session list (A67, list only)

```
GET /api/sessions?offset=0&limit=50

SessionPage    = {"root": path, "exists": bool, "total": int, "offset": int, "limit": int,
                  "sessions": [SessionSummary, …], "scanned_utc": ISO}
SessionSummary = {"path": path, "folder": string, "object": string, "started_utc": string,
                  "frames": int, "lights": int,
                  "filters": {"<filter>": int, …},      // "—" for frames without a filter
                  "image_types": {"<IMAGETYP>": int, …},
                  "missing_frames": int,                // frames of session.json whose FITS is not found
                  "curves": {"target": int, "comparison": int, "check": int},
                  "has_quality": bool,                  // photometry_quality.json
                  "has_targets": bool,                  // targets.json
                  "issues": [string]}
```

A session is a folder directly inside `sessions_path` that holds a
`session.json`; folders without one are not listed. Sessions come newest
first (`started_utc`, then the folder name). `limit` is 1…500 (default 50).
The summary is a Qt-free port of `argos/core/session/review.py:76-175`
(`load_session(read_temperature=False)` and `readiness_issues`; the module
itself cannot be imported, `argos.core.session` loads PyQt6): same files,
same readiness texts ("No light frames were recorded.", "No FITS frames
found in this session folder.", "Could not read observation.json.", …),
except that missing frames are counted in one line ("12 FITS frames listed
in session.json are missing") instead of one line each. A folder whose
`session.json` cannot be read is listed with `issues` saying why and zero
frames. Curves are the `photometry/*.csv` files counted by their prefix
`target_`, `comparison_`, `check_`. Summaries are cached per folder and
recomputed when `session.json` or the folder changes, so a second call is
a few milliseconds. The server never writes into a session.

### Support bundle (A5) and crash reports (A6)

```
SupportBundleBody = {"destination": path|null,      // absolute .zip; null = the server keeps it for a download
                     "include_session": bool,       // default false (decision Q-G17)
                     "session_dir": path|null,      // required when include_session is true; ignored otherwise
                     "include_site": bool,          // default false: site coordinates redacted everywhere
                     "include_crash_reports": bool, // default true
                     "overwrite": bool}             // default false

Job result = {"path": path|null,   // the ZIP written at destination; null when kept for download
              "name": string,       // argos-support-<version>-<UTC>.zip
              "bytes": int, "files": [string, …],
              "download": bool,     // true: fetch it with GET /api/jobs/{id}/download
              "session_included": bool, "site_included": bool}

CrashReports = {"directory": path|null,
                "reports": [{"path": path, "name": string, "t": ISO, "size": int,
                             "summary": string}, …]}   // newest first, at most 50
```

- Checked before the job starts: `destination` absolute and inside the
  allowed roots of the file listing (`403 forbidden_path` otherwise); a
  destination that names an existing folder is `400 invalid_argument` ("is
  a folder: name the .zip file"), checked before any suffix is added; a
  missing `.zip` suffix is appended (`c.tar.gz` becomes `c.tar.gz.zip`;
  `support_bundle.py:177-179` swapped the suffix instead); an existing file
  without `"overwrite": true` is `409 file_exists`; a path with a NUL byte
  is `400 invalid_argument`;
  `include_session` without `session_dir` is `400 invalid_argument`, a
  `session_dir` outside the roots `403 forbidden_path`, one without
  `session.json` `400 session_invalid`. One bundle at a time (`409 busy`
  with `owner`). The job is not cancellable (seconds).
- Content (a port of `create_support_bundle`, `support_bundle.py:162-221`,
  run on the job thread): `README.txt`; `manifest.json` (format 1, version,
  API, UTC time, platform, privacy flags, and the configuration summary of
  `shell.py:511-516`: `hardware.profile`, `ui.log_level`,
  `diagnostics.enabled`, ASTAP configured); `logs/argos.log*` from the log
  folder (10 MB each); with `include_crash_reports`, the 20 newest
  `crash/crash-*.txt` (1 MB each); with `include_session`, the session's
  `.csv`, `.json` and `.jsonl` files (10 MB each, 50 MB in all, no links,
  no FITS), as `support_bundle.py:224-302`.
- Redaction, in every text that enters the ZIP: the bearer token (its value,
  `token=…`, `Bearer …`, `ARGOS_TOKEN=…`), IPv4 addresses, the home folder
  path (`~`) and, unless `include_site`, the observer's coordinates: every
  writing of the Settings site's and saved sites' latitude, longitude and
  elevation (2 to 8 decimals), `lat=` / `lon=` / `elev=` values, every
  `(lat°, lon°)` pair (as the site check writes a site, also an older one), and in
  session files the keys `site`, `latitude`, `longitude`, `elevation`,
  `sitelat`, `sitelong`, `siteelev`, `lat`, `lon` (and the spellings
  `lat_deg`, `lon_deg`, `lng`, `site_lon`, `site_latitude`,
  `site_longitude`, `site_elevation`, `elevation_m`, `observing_site`,
  `geo`, `location`; case and separators ignored), plus every JSON number,
  under any key or in an array, that writes a site coordinate exactly or
  rounded to 2-8 decimals (whole numbers are kept: frame counts, gains).
  Free text in 1-decimal or degrees-minutes-seconds form is not recognised
  (best effort). Observer and network
  identity (`observer`, `obscode`, `host`, `ip`, `address`) and target
  coordinates (`ra`, `dec`) are always redacted in session files, as the Qt
  bundle does. The ZIP never leaves the computer.
- `destination: null` (the browser build): the ZIP goes into a private
  temporary folder of the server; `GET /api/jobs/{id}/download` serves it
  (`Content-Disposition: attachment; filename="argos-support-….zip"`) for
  as long as the job is kept (10 min), then it is deleted (also at
  shutdown). `404 not_found` for a job with no file, `409 not_ready` while
  it runs.
- Logs (topic `app`): INFO "Support bundle created: <name> (<n> files).
  ARGOS did not upload it."; ERROR "Support bundle failed: <reason>" (job
  error `bundle_failed`).
- Crash reports are the `crash-<UTC>-<pid>.txt` files of the log folder
  (`support_bundle.py:104-122`); `t` comes from the name's stamp (else the
  file time), `summary` is the report's last line (the exception), home
  path redacted. `since` keeps the reports with `t` after it.

### ASTAP detection (A81)

```
GET /api/astrometry/astap?path=<exe>&database_path=<folder>&database=<set>   // each defaults to the config's

AstapState = {"astap": path|null,                 // the binary ASTAP would run
              "configured": string,               // the path asked about ("" = auto-detect)
              "configured_found": bool,           // that path is an existing file
              "database_dir": path|null,          // the folder of star files used
              "database_source": "configured"|"detected"|null,
              "database_found": bool,             // star files (*.1476, *.290, *.101) in that folder
              "database": string,                 // the database set asked about
              "database_ignored": bool,           // a set and a folder are both given: the set is ignored (Q-C9)
              "database_args": [string],          // the -D / -d flags the solve will pass
              "message": string}                  // one line for Settings › Plate solving
```

Port of `ConfigurationPage._refresh_astap_status`
(`configuration_page.py:1208-1231`) with `find_astap`, `find_astap_db` and
`_database_args` (`platesolve.py:119-144, 305-319`) and the database choice
of `astrometry_session.py:64`. It only looks at the filesystem (no ASTAP
run), so the form can call it on every committed change.

### Place search (A82)

`POST /api/site/search {"query": "Saint-Michel-l'Observatoire"}` starts a
job of kind `site_search` (an empty query is `400 invalid_argument` "Enter
a city, country, or address first."; one search at a time, `409 busy`).
Port of `search_locations` (`location_resolver.py:34-87`): one
OpenStreetMap Nominatim query (up to 5 places), then one Open-Meteo
elevation query per place, 8 s each; the User-Agent carries the server's
version (`Argos/<version> (astronomical observing-site search)`).

| `stage` | done / total | |
|---|---|---|
| `search` | 0 / n+1 | The place query. |
| `elevation` | i / n+1 | Elevation of place i (a failure gives `elevation_m: null`, never fails the job). |

Result `{"query": string, "places": [{"label": string, "latitude": float,
"longitude": float, "elevation_m": float|null}, …]}`. Failures end the
job `failed` with `error.code` `lookup_failed` ("Location search is
unavailable. Check your internet connection.") or `not_found` ("No place
found for ‘…’." / "No usable coordinates found for ‘…’."). Cancel is
honoured within about 0.25 s, even during an HTTP request (its answer is
then dropped). Nothing is written: the client PATCHes `site.*` when the
observer picks a place. The elevation is a 90 m DEM estimate: the form says
so.

### Catalogue caches (A83) and the essential catalogue (A84)

```
Cache = {"kind": "object"|"exoplanet"|"aavso"|"gaia"|"field_catalogue",
         "label": string,        // "CDS/SIMBAD target-name cache", …
         "key": string,          // the data_paths.* config key
         "path": path, "path_kind": "file"|"dir",
         "exists": bool, "files": int, "bytes": int}
EssentialCatalogue = {"name": string, "version": string, "source": string,
                      "source_url": string, "object_count": int}
```

A port of `configuration_page.py:1104-1163`: the same five caches, the same
files counted and cleared: only the files each cache writes, so a cache
pointed at a general folder never loses the observer's own files (`object`,
`exoplanet`: the JSON file; `aavso`: SHA-1 hex names `<40 hex>.json`
(`aavso.py:188-189`); `gaia`: `<64 hex>.csv` (`gaia.py:57-58`);
`field_catalogue`: `<64 hex>.json` in its `simbad/` and `nasa/` subfolders
only (`field_objects.py:52,66`, `exoplanets.py:37,91`); symbolic links
never followed). The Qt page cleared every `*.json` / `*.csv`, recursively
for the field identities (`configuration_page.py:1149-1152`). `DELETE /api/caches/{kind}` clears one
synchronously (the client confirms first, as the Qt dialog did), logs INFO
"Cleared the <label> (<n> files)." (topic `config`), and downloads nothing;
an unknown kind is `404 not_found`, an OS refusal `500 internal_error` with
the reason. `GET /api/catalogues/essential` is
`argos.core.catalog.offline.essential_catalogue_info()` (bundled, offline).

### Site check (PROPOSAL §7)

The mount reports where it points (altitude, azimuth) from **its own** site
and clock (the Seestar takes them from the phone); ARGOS computes airmass,
BJD_TDB and FITS `SITELAT` / `SITELONG` from the **Settings** site. On
2026-09-25 the Settings site was Berkeley while the telescope was in
France: the mount put RR Lyr at altitude 75.4°, the Settings site at 13.8°,
and the run's airmass and AAVSO AMASS are wrong. The server compares the
two, as the Qt release does (commit `de5732f` on `release/0.5.0`,
`DeviceSession._check_site_against_mount`):

```
SiteCheck = {"state": "ok"|"mismatch"|"unknown",
             "reason": "no_mount"|"no_site"|"waiting"|"no_position"|null,  // set when unknown
             "message": string,                  // one line for the observer
             "tolerance_deg": 5.0,
             "checked_utc": ISO|null,            // the clock the comparison used
             "trigger": "connect"|"periodic"|"site_change"|"manual"|null,
             "site": {"name": string, "latitude": float, "longitude": float}|null,
             "mount": {"ra_hours": float, "dec_deg": float,
                       "alt_deg": float, "az_deg": float}|null,   // the reading compared
             "expected": {"alt_deg": float, "az_deg": float}|null, // same RA/Dec from the Settings site
             "separation_deg": float|null,       // angle between the two DIRECTIONS
             "altitude_diff_deg": float|null,    // mount minus expected, for the text only
             "driver_site": {"latitude": float, "longitude": float,
                             "elevation_m": float|null,
                             "distance_km": float|null,    // to the Settings site (null without one)
                             "state": "ok"|"mismatch"|"unknown"}|null}  // null: the driver does not say
```

- **The rule compares whole directions, never the altitude alone**:
  `separation_deg` is the angle between the mount's (alt, az) and the
  (alt, az) of the mount's own RA/Dec seen from the Settings site at the
  computer's clock. Over the 2026-09-25 run the altitudes were 61.5° apart
  at the start but only 6.2° at the end, while the directions stayed
  83.6-88.5° apart; sessions with the right site agree within 1.9-3.1°.
  More than `tolerance_deg` (5°) is `mismatch`.
- The expected direction uses the fast spherical trigonometry of
  `sky_geometry.horizontal_at` (`de5732f`; GMST IAU 1982 linear term, no
  precession, nutation or refraction). With coordinates of date (what the
  mount reports) it agrees with astropy (FK5 of date, no refraction) within
  0.01°; fed J2000 coordinates it is off by the precession since 2000, up to
  about 0.4° in 2026 (`tests/server/test_site_check.py` sweeps 120 random
  directions, sites and 2026 dates with bounds of 0.05° and 0.5°). Either
  way far inside the 5° tolerance. It never downloads anything.
- A Settings site counts as set when it has a name or when its coordinates
  are not the 0/0 default (`argos.core.config.observing_site`, `de5732f`);
  otherwise the check is `unknown` / `no_site` and nothing is compared.
- When: on the **first mount reading that is not a slew** after each
  connection and each automatic reconnection (`trigger: "connect"`), again
  every 5 minutes while the mount is connected (`"periodic"`, skipped while
  it slews), on the first reading once `site.name`, `site.latitude` and
  `site.longitude` have stayed unchanged for 2 s after a change
  (`"site_change"`; latitude and longitude are separate commits, so the
  pause keeps a half-typed site from being compared and logged), and on
  `POST /api/site/check`
  (`"manual"`, from the latest reading, `409 not_connected` without a
  mount). Before the first such reading the state is `unknown` /
  `waiting`; without a mount `unknown` / `no_mount`; a reading without
  alt/az is `unknown` / `no_position`.
- **Driver site.** When the Alpaca driver exposes `SiteLatitude` /
  `SiteLongitude` (`telescope.py:193-215`; several Seestar firmwares do
  not), they are read once per connection and compared directly:
  `distance_km` is the great-circle distance to the Settings site and
  `state` is `mismatch` beyond 100 km (about 1° of sky: a choice of this
  server, not a measured bound). The simulator reports its fixed site (APC,
  Paris). A driver-site mismatch alone makes the whole check `mismatch`.
- Logs (source `mount`, topic `mount`): on the first check of a connection
  or after a site change, WARN "Site check: the mount points at altitude
  75.4°, azimuth 258.9°; from the Settings site (37.871°, -122.273°) the
  same RA/Dec is at altitude 13.8°, azimuth 45.9°, 88.5° apart. Airmass,
  BJD and the FITS site use the Settings site: correct Settings › Observer
  & site if the telescope is elsewhere." or INFO "Site check: the Settings
  site agrees with the mount (2.8° apart)."; a periodic check logs only a
  change of state (the WARN, or INFO "Site check: the Settings site agrees
  with the mount again (…° apart)."). The driver-site comparison adds WARN
  "Site check: the mount's own site (…) is <d> km from the Settings site.";
  when the pointing agrees but the driver site does not, that WARN reads
  "Site check: the pointing agrees with the Settings site (2.8° apart), but
  the mount's own site (…) is <d> km from the Settings site." and no INFO
  "agrees" line is written (the log never contradicts the `mismatch`
  verdict).
- Published as `{"type": "site_check", …SiteCheck}` after every check and
  every state change, and inside the status record (`status.site_check`),
  so a client opened later has it at once.

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
| `{"type": "status", "connection": …, "camera": …, "mount": …, "devices": …, "profile": …, "site_check": …}` | Immediately on connect, then on every state transition: connection change, any device-state change, a profile change, any camera change, a mount change of `state`, `tracking`, `pier_side` or `target`, or a new site check (wave 2). |
| `{"type": "camera", "camera": CameraState}` | On every camera change, including each new frame in live view. |
| `{"type": "mount", "mount": MountState}` | Telemetry while connected: every 0.25 s for the simulator (4 Hz) and every 2 s for a Seestar, the Qt app's polling period. |
| `{"type": "devices", "devices": DevicesState}` | API 2. On every device-state change (with a `status`). |
| `{"type": "network", …NetworkState}` | API 2. After every Seestar probe (every 10 s) and every on-demand check; once right after the first `status`. |
| `{"type": "activity", "text": string, "source": string, "t": ISO}` | API 2. The last action started **or its outcome** (status-bar activity text). Starts end with "…" ("Connecting mount 192.168.1.42:32323…", "Searching for Alpaca devices…", "Exposing 2 s…", "Slewing"); every outcome replaces them, without an ellipsis: "<Device> connected", "<Device>: <full error>", "Equipment ready" or "3 of 4 devices ready · camera failed" (end of a Connect all), "Cannot reach <host>:<port> — … (… not connected)", "<Device> disconnected", "Disconnected", "Discovery: 2 devices found", "Discovery: no Alpaca device found", "Discovery cancelled", "Discovery failed: …", "Frame #12 received (2 s)", "Camera: <error>", "Slew finished", "Slew stopped", "Mount connection lost · retrying every 10 s", "Mount reconnected". A start is also a `cmd` log line, unless a more detailed line says the same; outcomes have their own OK / ERROR lines. Sent once right after the first `status` when there is one. |
| `{"type": "config", "changed": {key: value}, "values": {…}, "revision": int, "source": "api"\|"file"}` | API 2. After every config commit (`source: "api"`), or when the server finds the file changed by another program (`"file"`). `values` is the full value set, so the newest event alone is enough. |
| `{"type": "job", "job": Job}` | API 2. Job progress (≤ 4 Hz per job) and the final state. |
| `{"type": "site_check", …SiteCheck}` | API 2, wave 2. After every site check and every change of its state (mount connected or gone, site changed); the same record is in `status.site_check`. |
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
`network`, `activity`, `config`, `stellarium`, `site_check`) and the newest `job` event **of each job**
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
| A5, A6 | Wave 2: `POST /api/support-bundle` (job `support_bundle`, redacted), `GET /api/jobs/{id}/download`, `GET /api/diagnostics/crash-reports` |
| A8 | Wave 2: `read_only_reason` in KeyMeta, `omitted` in ConfigSnapshot, `hardware.overrides.adc_bits` (read-only) |
| A11 | Wave 2: `GET /api/fs/list`, read-only, limited to home and the data folders |
| A67 | Wave 2: `GET /api/sessions` (list only) |
| A81-A84 | Wave 2: `GET /api/astrometry/astap`, `POST /api/site/search` (job `site_search`), `GET` / `DELETE /api/caches[/{kind}]`, `GET /api/catalogues/essential` |
| §7 | Wave 2: site check: `site_check` in the status record and as an event, `GET` / `POST /api/site/check` |
