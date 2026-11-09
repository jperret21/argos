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
[API 2 routes, wave 2](#api-2-routes-wave-2), still additive: `"api"` stays 2. Wave 3
(Observe: acquisition, rows A19-A31 and A34-A41) adds the routes of
[API 2 routes, wave 3](#api-2-routes-wave-3-observe-acquisition): Take
shot with FITS save, capture settings, filter wheel, focuser, autofocus,
jog with a server dead-man, conditions, observation identity and catalogue
lookup; still `"api": 2`. Wave 4 (rows A32-A33, A43-A49, A51-A53) adds the
field, its catalogue, layers, tracking, star selection and the target set;
wave 5 (rows A50, A54-A58) adds the live photometry of
[API 2 routes, wave 5](#api-2-routes-wave-5-live-photometry), still
`"api": 2`.

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
  Open-Meteo for the elevation). The site check and the live points'
  BJD_TDB compute offline: astropy never downloads an IERS or leap-second
  table for them (its bundled tables give the same BJD to the bit;
  `notes/release_0_5_0.md` S37).
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
| 400 | `invalid_fits` | The file exists but is not a displayable FITS image; since wave 3 also an image that is not raw 16-bit camera counts (see Opening FITS files). |
| 400 | `invalid_argument` | Also `open-fits` on a path the OS refuses to examine (name too long, unreadable directory). |
| 400 | `session_invalid` | (wave 2) A support bundle's `session_dir` holds no `session.json`. |
| 401 | `unauthorized` | Bad or missing token. |
| 403 | `forbidden_host` / `forbidden_origin` | Request for a foreign `Host` name, or from a foreign `Origin` (see Security). |
| 403 | `forbidden_path` | (wave 2) A path outside the folders the server may browse (home and the data folders), directly or through a symbolic link; or a folder the OS refuses to list. |
| 404 | `not_found` | Unknown route, unknown device id, unknown (or expired) job id, or `open-fits` on a missing file. Wave 2: a missing folder in `GET /api/fs/list`, an unknown cache kind, a job with nothing to download. |
| 405 | `method_not_allowed` | Wrong HTTP method on a known route. |
| 409 | `not_connected` | Camera or mount command with that device not connected. Also a mount command whose device was disconnected while it ran: its result is discarded. |
| 409 | `busy` | Exposure requested while the camera exposes, downloads, is live (without `save`), or is still stopping. (Wave 3) any camera, wheel, focuser or autofocus command refused because another owner holds the device: the error carries `owner` (`"single"`, `"live"`, `"autofocus"`, `"filterwheel"`, `"sequence"`, `"jog"`); a jog during a GoTo slew, or on an axis another client is jogging (`owner: "jog"`); an offset or binning change while a Take shot waits for its frame or is being saved. `POST /api/connection` or a device connect while devices are connected to **another** address or mode. `PUT /api/profile` while a device is connected (message says why). A job start while a job of the same kind runs (`owner` = its id). |
| 409 | `parked` | `goto` or `tracking` on a parked mount; (wave 3) a jog on a parked mount. |
| 409 | `dark_slot` | (wave 3 review) a Light or Flat Take shot, or an autofocus start, while the filter wheel is settled on (or turning to) its opaque `Dark` slot; `details.slot` names it. |
| 409 | `clock_error` | (wave 3) `goto` while the mount clock is more than 60 s off (`MountState.goto_blocked`); the message is the connect message (H4). |
| 409 | `not_live` | `PATCH /api/camera/live` while live view is not running. |
| 409 | `unsupported` | `DELETE /api/jobs/{id}` on a job kind that cannot be cancelled. |
| 409 | `file_exists` | (wave 2) A support bundle destination that exists, without `"overwrite": true`. |
| 409 | `not_ready` | (wave 2) `GET /api/jobs/{id}/download` while the job still runs. |
| 409 | `run_active` | Reserved: a photometry-geometry config change while a sequence runs (no sequence engine in API 2 yet, never sent). |
| 500 | `internal_error` | Any unexpected failure; the traceback is in the server log. The answer keeps the CORS headers, so the browser can read it. |
| 502 | `connection_failed` | The device could not be reached or refused to connect. Its device state becomes `error` with the full text. |
| 502 | `device_error` | A connected device refused a command or stopped answering. |
| 404 | `not_found` | (wave 3) `GET /api/catalog/resolve` for a designation the catalogues do not know (the resolver's text). |
| 502 | `lookup_failed` | (wave 3) `GET /api/catalog/resolve` or `/api/catalog/nearby` with no network answer (the resolver's text). |

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
           "truncated": bool,       // more than 5 000 entries: the first 5 000 are listed
           "selected": string|null} // wave 5: the file named by `path` (its folder is listed)
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
  invalid_argument` ("not a folder") with `kind=dir`, and with `kind=file` or
  `any` (wave 5) lists its folder with `selected` = its name (a suffix not in
  `ext` is `400` "<name> is not a <ext> file"); a folder the OS refuses to
  read is `403 forbidden_path` with the OS reason.
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

## API 2 routes, wave 3 (Observe: acquisition)

Wave 3 (`web/spec/README.md` §7 "Observe: acquisition": rows A19-A31 and
A34-A41) adds the routes, records and events below, still under `"api": 2`
(additive: every v1 and wave 1-2 route keeps its shape; records only gain
fields). Every device call runs on a worker thread or in FastAPI's
threadpool, never on the event loop.

The science rules are those of the fixed Qt engine (release 0.5.0,
`notes/release_0_5_0.md`), ported Qt-free into `argos/server/capture.py`
(Take shot and FITS), `wheel.py`, `focuser.py`, `autofocus.py`, `jog.py`,
`observation.py` and `conditions.py`; each module cites the Qt lines it
ports.

| Method | Path | Body | Returns | Row |
|---|---|---|---|---|
| GET | `/api/camera/settings` | — | CaptureSettings | A22 |
| PUT | `/api/camera/settings` | CaptureSettingsBody | CameraState | A22 |
| POST | `/api/camera/capture` | CaptureBody (extends v1) | CameraState | A23 |
| POST | `/api/camera/live` | CaptureBody without `save` (v1 shape still valid) | CameraState | A22 |
| GET | `/api/camera/saved?after=<seq>&limit=<n>` | — | `{"saves": [FrameSaved, …], "last_seq": int\|null}` | A24 |
| POST | `/api/camera/open-fits` | `{"path"}` (v1) | CameraState; raw frames only (see below) | A25, A27 |
| GET | `/api/filterwheel` | — | FilterWheelState | A28 |
| POST | `/api/filterwheel/select` | `{"name": string}` | FilterWheelState (`moving`) | A28 |
| POST | `/api/mount/jog` | JogBody | MountState | A30 |
| POST | `/api/mount/jog/stop` | `{"axis"?: "primary"\|"secondary", "client"?: string, "seq"?: int}` | MountState | A30 |
| POST | `/api/mount/tracking-rate` | `{"rate": "sidereal"\|"lunar"\|"solar"\|"king"}` | MountState (rate read back) | A31 |
| GET | `/api/focuser` | — | FocuserState | A34 |
| POST | `/api/focuser/move` | `{"position": int}` | FocuserCommand | A35 |
| POST | `/api/focuser/step` | `{"delta": int}` | FocuserCommand | A35 |
| POST | `/api/focuser/halt` | — | FocuserCommand | A35 |
| GET | `/api/autofocus` | — | AutofocusState | A36 |
| POST | `/api/autofocus/start` | AutofocusBody (optional) | AutofocusState (`running`) | A36 |
| POST | `/api/autofocus/stop` | — | AutofocusState (`stopping`, or the final state) | A36 |
| GET | `/api/session/conditions?since_seq=<n>&limit=<n>` | — | ConditionsPage | A37 |
| GET | `/api/observation` | — | Observation | A38 |
| PUT | `/api/observation` | `{"object_name": string}` | Observation | A38 |
| POST | `/api/observation/target` | ObservationTargetBody | Observation | A39 |
| DELETE | `/api/observation/target` | — | Observation (target cleared, name kept) | A39 |
| GET | `/api/catalog/resolve?q=<name>` | — | Resolved | A40 |
| GET | `/api/catalog/suggest?q=<text>&limit=8` | — | `{"query": string, "names": [string]}` | A41 |
| GET | `/api/catalog/nearby?ra_hours=&dec_deg=&network=false&radius_arcsec=90` | — | `{"candidates": [Candidate, …], "network": bool}` | A20 |

New WebSocket events (`/ws/events`): `filterwheel`, `focuser`,
`autofocus`, `observation`, `target_suggestions` and `frame_metrics` are
snapshots (the newest one is complete); `frame_saved` and `conditions` are
streams with an increasing `seq` (see "Backpressure" below). The status
record gains `filterwheel`, `focuser`, `autofocus` and `observation`, so a
client opened later has every one of them at once.

### Camera: capture settings, owner, Take shot (A21-A24)

```
CameraState += {
  "owner": "idle"|"live"|"single"|"autofocus"|"sequence",  // who drives the camera ("sequence": wave 6)
  "settings": CaptureSettings,        // what the NEXT frame uses; server state shared by every client
  "current": FrameSettings|null,      // the frame being exposed now (null when nothing exposes)
  "save_pending": int,                // Take shots still waiting for their frame (0 or 1)
  "waiting_for": "filterwheel"|null,  // a Dark/Bias Take shot waiting for the wheel to reach Dark
  "limits": {"gain_min": int, "gain_max": int,
             "exposure_min_s": float, "exposure_max_s": float}|null,  // the driver's; null when disconnected
  "offset": {"min": int, "max": int}|null,   // null: the driver has no Offset (field hidden)
  "binning": {"max": int}|null,              // null: MaxBin 1 (field hidden)
  "temperature_c": float|null}               // sensor °C, read every 10 s while connected

CaptureSettings = {"exposure_s": float, "gain": int,
                   "frame_type": "light"|"dark"|"flat"|"bias",
                   "filter": string,          // slot for Light/Flat (metadata only without a wheel, Q-O5)
                   "offset": int|null,        // read back from the driver; null when unsupported
                   "binning": int}            // 1 unless the driver bins
FrameSettings   = {"exposure_s": float, "gain": int, "frame_type": …, "filter": string,
                   "object_name": string, "light": bool,   // shutter semantics sent with StartExposure
                   "origin": "single"|"live"|"autofocus",
                   "save": bool,                            // this frame is the one a Take shot saves
                   "started_utc": ISO}                      // DATE-OBS of the frame
```

- **Defaults**: exposure 2 s, gain 80, frame type light, filter `IR` (the
  Qt Camera form's first light slot, `camera_dock.py:59`), offset and
  binning from the driver at connect. Settings survive a page reload and
  are the same for every client (decision Q-O13). When a filter wheel
  connects, or any move ends (a Camera-card select, a Dark shot, later a
  sequence), `settings.filter` follows the slot the wheel reports (S3).
- **v1 fields.** `exposure_s` and `gain` keep their v1 meaning: the frame
  being exposed (`current`) while one is, else the settings. So `PATCH
  /api/camera/live` still changes them only when the next frame starts.
- **`owner`** (port of `camera_service.py:60-77`, priority SEQUENCE >
  AUTOFOCUS > LIVE / SINGLE): `single` while a single capture runs
  (including the wait for the wheel), `live` during live view, `autofocus`
  while an autofocus sweep holds the camera (and until its focuser is back
  at the start position, S23). Starting autofocus preempts live view and a
  single capture (INFO "Live view stopped: autofocus owns the camera.").

```
CaptureSettingsBody = {"exposure_s"?: float, "gain"?: int, "frame_type"?: "light"|"dark"|"flat"|"bias",
                       "filter"?: string, "offset"?: int, "binning"?: int}       // strict, all optional
CaptureBody         = {"exposure_s"?: float, "gain"?: int,
                       "frame_type"?: "light"|"dark"|"flat"|"bias", "save"?: bool}   // strict
```

A v1 body (`{"exposure_s", "gain"}`) stays valid; both fields are now
optional and default to the settings. Unknown fields (`binning`, …) are
still `400`.

- `PUT /api/camera/settings` is one commit: every field is checked first
  (types strict; exposure and gain against `limits` when a camera is
  connected, else 0 < exposure ≤ 3600 s and 0 ≤ gain ≤ 1000; offset in
  `offset.min…max`; binning 1…`binning.max`); a value out of range is
  `400 invalid_argument` with the reason, **never clamped** (README §3.4,
  05 P6). Exposure, gain and frame type apply from the next frame in any
  mode (live view included: the frame in progress keeps its own). Offset
  and binning are sent to the driver at once (off the event loop) and read
  back. `filter` with a wheel connected moves the wheel (exactly as `POST
  /api/filterwheel/select`); without a wheel it is FITS metadata only (INFO
  "No filter wheel: 'LP' is written to FITS FILTER only."). `409 busy`
  (`owner` = `autofocus` or `sequence`) while autofocus or a sequence owns
  the camera; `409 not_connected` for offset / binning without a camera;
  `400` for offset / binning the driver does not support. Every refusal
  is checked **before any device call** (review of wave 3): a `filter`
  while the wheel moves is `409 busy` (`owner: "filterwheel"`) with nothing
  sent to the driver, so a refused PUT never leaves a new offset behind.
  Offset and binning are `409 busy` while a Take shot waits for its frame
  or is being written ("A Take shot is waiting for its frame or being
  saved — change the offset after it …"): FITS OFFSET is read from the
  camera at save time.
- `POST /api/camera/capture` writes the body's `exposure_s` / `gain` /
  `frame_type` into the settings first (same checks), then:
  - idle camera: one exposure (`owner: single`), published on `/ws/frames`;
    with `"save": true` it is also written as a FITS file (below);
  - live view and `"save": true`: no new exposure; the live loop's next
    frame is saved (Take shot during live, A23); without `save` it is
    `409 busy` as in v1;
  - `409 busy` while a single capture runs, and (with `owner`) while
    autofocus or a sequence owns the camera.
- `save` defaults to `false`, so a v1 client's capture is unchanged
  (displayed, not saved).
- A Take shot with `settings.binning` > 1 is `409 unsupported`:
  `fits_writer.py` writes `XBINNING = YBINNING = 1` and the unbinned pixel
  size, so a binned frame would carry false metadata (a frame that arrives
  binned anyway is dropped: WARN "Take shot not saved: binning is 2×2 …").
- **A Light or Flat Take shot behind the opaque slot is `409 dark_slot`**
  (science review of wave 3, the S1 counterpart; sequences already refuse
  it, S7): the server turns the wheel to Dark by itself for a Dark or Bias
  shot and nothing turns it back, so "darks, then a light" would save a
  pure-pedestal frame as a Light Frame. Message: "The filter wheel is on
  'Dark', which blocks the light — select a filter for the Light Frame."
  (0.5.0 only warned, the observer having chosen Dark by hand.)

**What a Take shot writes** (port of `AcquisitionEngine.take_shot`,
`_dark_shot_allowed`, `_on_frame` and `_save_fits_async`,
`acquisition_engine.py:420-510, 573-636, 1796-1910`, with every 0.5.0 fix):

1. **Settings snapshotted per frame (S2).** The exposure loop takes one
   snapshot of the settings when a frame starts; the FITS header uses that
   snapshot, never the settings at the time the frame arrives. A single
   Take shot that waits for a turning wheel (any frame type) takes its
   snapshot once the wheel has settled, so the frame header, the HUD and
   the conditions row name the new slot. During live view the frame in
   progress is saved with its own exposure and gain (Qt parity); when they
   differ from the shot's request INFO says so ("Take shot: saving the
   frame in progress, exposed 1 s at gain 80 (the shot asked 3 s at gain
   150).").
   **Offset and binning** are read from the camera when the file is
   written, so a frame exposed across an offset or binning change is never
   saved: INFO "Take shot: the offset or binning changed during this
   exposure — saving the next frame instead." (review of wave 3; with the
   409 above, OFFSET always describes the frame).
   **The gain is sent before every exposure** (`exposure_worker.py:145-149`):
   a refused or lost `set_gain` is retried on the next frame, and a gain
   changed by another client is restored (0.4.2's web adapter sent it once
   per change; the science review of wave 3 found every later frame could
   then be exposed at the old gain while GAIN recorded the new one).
2. **Dark / Bias need the opaque slot (S1).** The Seestar has no shutter.
   With a filter wheel whose profile has a `Dark` slot, a Dark or Bias Take
   shot is exposed only once the wheel has **settled** on Dark: if it is
   elsewhere (or its position is unknown) the server moves it to Dark first
   (CMD "Filter → Dark for the Dark Frame (the Seestar has no shutter)."),
   `waiting_for: "filterwheel"` meanwhile, then exposes. A wheel already
   moving to another slot is `409 busy`. A move that fails or does not end
   on Dark cancels the shot (WARN "Dark Frame shot not taken: …"). Without
   a wheel the shot is taken with WARN "Dark Frame: no filter wheel to
   block the light — the frame is only dark if the telescope is covered."
   Dark and Bias frames are exposed with `light: false`.
3. **A frame exposed while the wheel turned is never saved (S3 review).**
   A frame whose exposure started before the last wheel move ended (or
   while one is in flight) is not saved; the loop exposes another one,
   which is (INFO "Take shot: the filter wheel moved during this exposure
   — saving the next frame instead."). During live view the same applies.
   A single Take shot waits for a turning wheel before each exposure, and
   gives up after five unsaved frames (WARN "Take shot not saved after 5
   frames: …").
4. **A frame of another type is not saved in its place.** During live view
   the frame in progress is saved when it has the requested frame type;
   otherwise the next one is (INFO "Take shot: this frame is a Light Frame;
   saving the next Dark Frame instead."; 0.5.0 saved the in-flight frame
   with its own type, `notes/release_0_5_0.md` "Deferred"). A pending Dark /
   Bias whose frame
   arrives with the wheel no longer on Dark is dropped (WARN "Dark Frame
   shot not saved: the filter wheel reports 'IR', not 'Dark'.").
5. **FILTER is read back from the wheel (S3)** when the file is written,
   with the sequence's rules (`_wheel_filter_name`,
   `acquisition_engine.py:154-180`): a readable wheel that differs from the
   frame's filter wins (WARN); an unreadable or turning wheel keeps the
   frame's filter (WARN).
6. **QA headers measured on the saved array (S20)**: `HFD`, `NSTARS`,
   `SKYLEVEL`, `FWHM`, `ECCENTR` from `frame_metrics` and `detect_stars` of
   that very array (default aperture, as the Qt save).
7. **Pointing only from a live mount (X1)**: `RA`, `DEC`, `OBJCTRA`,
   `OBJCTDEC`, `ALTITUDE`, `AZIMUTH` (and so `AIRMASS`) come from the
   newest mount reading of the current connection when the frame arrives,
   and are absent when the mount is disconnected, lost or being retried.
   `TARGRA` / `TARGDEC` are the last GoTo target of this server process
   (the Qt `target_radec`, kept across park and reconnects). Two Qt-parity
   rules kept for the owner to decide (science review of wave 3): `OBJECT`
   is the observation name while `TARGRA` / `TARGDEC` are the last GoTo, so
   naming another object without a GoTo pairs one object's name with the
   other's coordinates (the conditions row's `airmass_target` uses the
   observation target); and the pointing is the reading when the frame
   **arrives**, while the `AIRMASS` comment says "at exposure start"
   (≈ 0.8° of altitude over a 300 s frame at 0.0026 °/s).
8. **The site only when set (X2)**: `SITELAT`, `SITELONG`, `SITEELEV` (and
   `MOONALT`) only when `argos.core.config.observing_site` says a site is
   set; never 0/0.
9. Everything else is `argos.core.imaging.fits_writer.FITSWriter.write`
   unchanged: `DATE-OBS` = the frame's start (taken just before
   `StartExposure`), `DATE-AVG` / `MJD-AVG` = the midpoint between that and
   `ImageReady` (before the download), `EXPTIME`, `GAIN`, `IMAGETYP`
   (`Light Frame`, `Dark Frame`, `Flat Frame`, `Bias Frame`), `OBJECT` (the
   observation's object name, `Unknown` when empty, as the Qt form),
   `OBSERVER`, `OFFSET`, `CCD-TEMP`, `EGAIN` (driver, else the sensor
   reference), `READOUTM` read from the camera at save time, `SOFTWARE`
   `Argos v<version>`. Folder and name as the Qt Take shot:
   `<sessions_path>/<start UTC>_<OBJECT>/<lights|darks|flats|biases>/<OBJECT>_<filter>_<type>_e<ms>ms_g<gain>_<n>.fit`,
   never overwriting (the index grows).

The file is written on the server's save thread (the live loop keeps
running). Logs (topic `camera`): CMD "Take shot — saving next frame…", OK
"Saved <name>", ERROR "FITS save failed: <reason>".

```
FrameSaved = {"type": "frame_saved", "seq": int,      // save counter, increasing
              "frame_seq": int,                       // the /ws/frames seq of that frame
              "path": path, "name": string, "source": "single"|"sequence",
              "object": string, "filter": string, "frame_type": "light"|…,
              "image_type": "Light Frame"|…, "exposure_s": float, "gain": int,
              "date_obs": ISO, "t": ISO,
              "record": {"hfd": float|null, "fwhm": float|null, "star_count": int|null,
                         "sky_adu": float|null, "peak_adu": int|null,
                         "eccentricity": float|null}}
```

`GET /api/camera/saved?after=<seq>` returns the saves after `seq` (the
last 200 are kept), so a client that missed some (a gap in `seq`) reads
them back.

### Frames: header fields and metrics (A25, A26)

The `/ws/frames` header gains (additive):

```
{… v1 fields …,
 "bayer": string|null,          // CFA layout of the raw mosaic (null for mono data)
 "origin": "single"|"live"|"autofocus"|"file",
 // camera frames:
 "frame_type": "light"|…, "gain": int, "filter": string, "started_utc": ISO, "save": bool,
 // opened files (origin "file"):
 "path": path, "file_name": string,
 "date_obs": string|null,       // the header's DATE-OBS as written
 "epoch_utc": ISO|null}         // exposure midpoint: DATE-AVG, else DATE-OBS + EXPTIME/2, else null (S39)
```

`bayer` is the profile's pattern for a colour camera (`CameraState.sensor.
bayer`), and for a file its `BAYERPAT` keyword, else the active profile's.

```
FrameMetrics = {"type": "frame_metrics", "seq": int,   // the frame's /ws/frames seq
                "hfd_px": float|null,                  // half-flux diameter of the brightest star
                "fwhm_px": float|null,                 // mean FWHM of the detected stars
                "eccentricity": float|null,
                "star_count": int,                     // local maxima above 5 σ (frame_metrics)
                "n_detected": int,                     // stars measured by detect_stars
                "sky_adu": float, "peak_adu": int,
                "star_radius_px": int,                 // imaging.star_radius_px used by detect_stars
                "plane": "green",                      // sizes in green-plane px (raw/2 on a CFA)
                "t": ISO}
```

Computed on the **full-resolution** frame (S20, Q-O14) by a metrics thread,
latest frame wins (a frame still waiting when a newer one arrives is
skipped), for every camera frame and every opened file. Autofocus sample
frames are metered too (their HFD is also in the `autofocus` record).

### Filter wheel (A28)

```
FilterWheelState = {"state": "disconnected"|"idle"|"moving"|"error",
                    "name": string|null,
                    "slots": [string],            // the active profile's slot names, in wheel order
                    "dark_slot": bool,            // a "Dark" slot exists (it blocks the light)
                    "position": int|null,         // settled slot index; null while moving or unknown
                    "slot": string|null,          // settled slot name
                    "target": string|null,        // slot a move goes to
                    "message": string|null,       // why the position is unknown, the driver's refusal
                    "settled_utc": ISO|null}      // when the last move ended (settled or failed)
```

Port of `DeviceSession.move_filter` and `_FilterMoveRunnable`
(`device_session.py:85-122, 818-889`) with H9: `POST /api/filterwheel/select
{"name"}` (case-insensitive slot name) starts the move on a worker thread
and answers at once (`moving`, `target`); the thread waits for the wheel to
leave position −1 (every 0.15 s, 20 s at most) and publishes the result.
Every mover publishes: a Camera-card select, a Dark Take shot, later a
sequence. Errors always end `moving` (H9): a refused move reads the wheel
back and reports the slot it is really on (`idle`, `message` = the
refusal), or `error` "position unknown" when it cannot be read; a wheel
still turning after 20 s is `error` with `message` "Still turning after
20 s: position unknown". Refusals: `409 not_connected`; `400
invalid_argument` "No wheel slot named 'X' (slots: Dark, IR, LP)"; `409
busy` while a move runs or autofocus owns the camera. Logs (topic
`camera`, source `filterwheel`): CMD "Filter → IR", ERROR "Filter move:
<driver text>".

### Mount: geometry, jog with a dead-man, tracking rate (A29-A31)

```
MountState += {"alignment": "altaz"|"eq"|"eq_gem"|null,    // AlignmentMode at connect
               "tracking_rate": "sidereal"|"lunar"|"solar"|"king"|null,   // read back
               "tracking_rates": [string],                // what the driver lists (Q-O15); [] unknown
               "goto_blocked": {"reason": "clock", "clock_error_s": float,
                                "message": string}|null,  // GoTo/Sync/Center are refused (H4)
               "center_available": bool,                  // wave 4: Field.center_available
               "jog": {"primary": float, "secondary": float,   // deg/s now commanded, 0 = stopped
                       "stop_pending": ["primary"|"secondary"],  // a stop failed; retried
                       "max_rate_deg_s": float, "deadman_s": float,
                       "last_stop": {"axis": string, "reason": string, "t": ISO}|null}|null}
                                                  // jog: null while no mount is connected
JogBody = {"axis": "primary"|"secondary",
           "rate_deg_s": float,        // signed, 0 < |rate| ≤ max_rate_deg_s (5)
           "client"?: string,          // the id this client passed to /ws/events?client=
           "seq"?: int,                // increasing per client (one counter per page): see below
           "renew"?: bool}             // a periodic renewal: never restarts an axis the server stopped
// The answer is the MountState plus "jog_command": {"outcome": "started"|"renewed"|"pending"|"ignored",
//   "why": "stale"|"stopped"|"late"|null}. MountState.jog also has "stop_failed": [axis].
```

- **Axes** (`telescope.py:564-592`, `manual_control_dialog.py:49-58`):
  `primary` is azimuth on an alt-az mount and right ascension / hour angle
  on an equatorial one, `secondary` altitude or declination; a positive
  rate is north / east (Q-O4: the client labels them from `alignment`).
  The Qt speeds were 0.5, 2 and 5 °/s.
- **Start and renew.** `POST /api/mount/jog` starts the axis
  (`MoveAxis(axis, rate)`) or, with the same rate, only renews it (no
  device call). The client renews each moving axis every 250 ms, with
  `renew: true`, and never while its previous request for that axis is
  unanswered. **A renewal never waits on device I/O** (review of wave 3):
  it is answered under the server's state lock, `renewed`, or `pending`
  while that axis's start is still inside a slow `MoveAxis`; so a slow
  driver cannot pile renewals up in the request threads (a 10 s `MoveAxis`
  used to stall every route, Abort included, for 44 s). A renewal of an
  axis the server stopped (dead-man, socket, Abort, Park, GoTo) is
  `ignored` / `stopped`: the observer presses again. A start that waited
  longer than `deadman_s` for the device lock, or that was sent before its
  client's socket closed or blurred, is dropped (`ignored` / `late`; the
  client sends it again once). A start on an axis another client is
  jogging is `409 busy` (`owner: "jog"`): two windows on one axis would
  reverse the motor at every renewal.
- **Dead-man.** An axis not renewed within `deadman_s` (1.0 s) is stopped
  by the server (WARN "Jog stopped by the server: no renewal for 1.0 s
  (primary axis)."). It is also stopped when the client's `/ws/events`
  socket opened with that `client` id closes, and when that socket sends
  `{"type": "jog_stop"}` (send it on window blur, a hidden tab, pointer
  loss). `POST /api/mount/jog/stop` stops one axis, or with no `axis` both
  axes whatever the server believes (the Qt ■ button).
- **Every axis it moved, retried.** Axes are tracked separately (H3): a
  diagonal jog moves both, each stops on its own. A `MoveAxis(…, 0)` that
  fails keeps its axis in `stop_pending` (WARN "Stop failed (primary axis):
  … — retrying.") and is retried every 0.5 s, five times, then ERROR "Stop
  failed again (primary axis): … — the mount may still be moving; use Abort
  on the Mount card." The axis then **stays** in `stop_pending` and is
  listed in `stop_failed`, retried every 5 s until a stop or Abort
  succeeds (OK "Stop confirmed (primary axis)."); it never re-enters
  through the dead-man, and the record never shows a failed stop as
  resolved (review of wave 3). A start that raised is kept in
  `stop_pending` too (it may have reached the mount, H3). The server-side stops log WARN "Jog
  stopped by the server: <why> (primary axis)." Abort
  (`POST /api/mount/stop`), Park, a GoTo and a mount disconnect first stop
  any jogging axis.
- Device calls are serialised in order on one jog lock, so a stop can never
  overtake its start. Command numbers are compared **per client and per
  axis**: a start or renewal not above the client's last number for that
  axis is `ignored` / `stale`. **A stop is never dropped** (it is
  idempotent and safe): its number only invalidates that client's older
  starts of the axis, so a key-up overtaken by a renewal of the other axis
  still stops its axis (review of wave 3). The client keeps one counter per
  page, so a remounted jog pad never starts again below what the server
  saw.
- Refusals: `409 not_connected`, `409 parked`, `409 busy` while a GoTo slew
  runs ("Abort the slew before jogging").
- `POST /api/mount/tracking-rate` sets the ASCOM `TrackingRate`
  (`telescope.py:610-634`) and reads it back (H6): `tracking_rate` is what
  the driver then reports; a rate the driver does not list is `400`.
- `goto_blocked` is set when the mount clock is more than 60 s off
  (`telescope.py:283-294`): the message is the one the connect logs (H4),
  and `POST /api/mount/goto` answers `409 clock_error` with it before any call.

### Focuser (A34, A35)

```
FocuserState = {"state": "disconnected"|"idle"|"moving"|"error",
                "name": string|null, "position": int|null,   // polled
                "target": int|null,                          // last move sent
                "queued": int|null,                          // target waiting for the move in progress (D9)
                "temperature_c": float|null,                 // polled every 10 s
                "max_step": int|null, "max_increment": int|null,
                "absolute": bool|null, "step_size_um": float|null,
                "locked_by": "autofocus"|null,               // manual moves refused
                "message": string|null, "t": ISO}
FocuserCommand = {"focuser": FocuserState,
                  "requested": int|null,     // the position asked for (step: position + delta)
                  "sent": int|null,          // what was sent to the driver now (null: queued or halt)
                  "clamped": bool,           // a step was clamped to 0…max_step (reported, H10)
                  "queued": bool}
```

- **Polling** (new, absent in Qt, fixes 05 P4): position and `IsMoving`
  every 0.5 s while moving, every 5 s when idle; temperature every 10 s.
  A `focuser` event follows every change.
- `POST /api/focuser/move {"position"}` (Go to): outside `0…max_step` is
  `400 invalid_argument` ("Position 120000 is outside 0–100000 (the
  focuser's MaxStep).", never clamped, H10). `POST /api/focuser/step
  {"delta"}` (Out = negative, In = positive): from the queued or current
  target, clamped to `0…max_step` and reported (`clamped: true`).
- **No Move while moving (D9).** A move or a step that arrives while the
  focuser moves is queued (`queued`, steps add up) and sent as one move
  when the current one ends.
- `POST /api/focuser/halt` halts at once and clears the queue; it is
  accepted while autofocus runs and then also ends the autofocus **where
  the focuser is** (no return to the start; Q-O6). Moves and steps are
  `409 busy` ("Autofocus owns the focuser.") while autofocus runs or
  returns (H10). Logs (source `focuser`, topic `focuser`): CMD "Focuser
  move → 5200", "Focuser step +100 → 5300", "Focuser halted".

### Autofocus (A36)

```
AutofocusBody  = {"exposure_s"?: float, "gain"?: int, "half_range"?: int (10…), "num_steps"?: int (3…41)}
AutofocusState = {"state": "idle"|"running"|"stopping"|"done"|"rejected"|"cancelled"|"failed",
                  "stage": "coarse"|"fine"|"verify"|"returning"|null,
                  "step": int, "total": int,                  // samples taken / announced
                  "params": {"exposure_s", "gain", "half_range", "num_steps"}|null,
                  "start_position": int|null, "position": int|null,   // focuser at the end
                  "samples": [{"position": int, "hfd_px": float|null,
                               "stage": "coarse"|"fine"|"verify", "t": ISO}],
                  "best": {"position": int, "hfd_px": float|null,      // measured at the end (verify)
                           "fitted_hfd_px": float|null,
                           "method": "parabola"|"raw"|"none"}|null,
                  "fit": {"coeffs": [a, b, c]|null,         // HFD = a·p² + b·p + c, the worker's own fit
                          "window": [lo, hi],               // positions the fit was allowed in
                          "samples": [[position, hfd_px], …]}|null,   // the samples it used
                  "message": string|null, "run": int,
                  "started_utc": ISO|null, "ended_utc": ISO|null}
```

A port of `AutofocusWorker` (`autofocus_worker.py:48-232`) with
`argos.core.imaging.focus` unchanged, on a server thread:

- **Refused behind the Dark slot** (review of wave 3): with a filter wheel
  that has a `Dark` slot, autofocus is `409 dark_slot` while the wheel is
  settled on Dark ("The filter wheel is on 'Dark', which blocks the light —
  select a filter before autofocus.") and `409 busy` (`owner:
  "filterwheel"`) while it turns. A Dark Take shot leaves the wheel on Dark;
  a sweep there only measured hot pixels and ended "flat HFD curve" without
  naming the cause.
- Parameters default as the fixed Qt engine does
  (`acquisition_engine.py:936-958`, `autofocus_worker.py:63-82`): exposure =
  the capture exposure, at most 10 s; gain = the capture gain; `half_range`
  2000 steps; `num_steps` 9. Exposure and gain are checked against the
  camera limits (`400`), `half_range` 10…100 000, `num_steps` 3…41. The
  Settings keys of Q-O9 (`autofocus.*`) need defaults in
  `argos/core/config.py`, which this wave leaves unchanged: they come with
  the wave that changes the core config. The gain **is applied** (S22): it
  is sent with every sample exposure.
- Stages: coarse sweep of `num_steps` positions across ±`half_range`; the
  degenerate-sweep guard (flat curve, minimum on an edge, fewer than three
  samples) restores the start and ends `rejected` with the reason ("focus
  unchanged"); four fine samples around the raw minimum; the parabola fit
  on the fine samples + the coarse minimum (`fit`); a move to the best
  position and one verification exposure (`best.hfd_px` is that measured
  value). Every sample is one `autofocus` event; sample frames are also
  published on `/ws/frames` (`origin: "autofocus"`).
- `POST /api/autofocus/stop` = cancel and **return to the start** (S23):
  the sweep move is halted, then the focuser is driven back to the start
  position and waited for (30 s at most) before the camera is released;
  meanwhile the state is `stopping` / `returning`, and a second stop is
  harmless. It ends `cancelled` with "Returned to 5000." only when the
  focuser was **read back** at the start and idle (review of wave 3). A
  focuser lost during the return, an unreadable position, or a return
  slower than the 30 s wait ends `failed` with what is known, and an ERROR
  line: "Stopped — could not read the focuser back: it may not be at its
  start (5000).", "Stopped — focuser at 4972 and still moving, not yet back
  at its start (5000).", "Stopped — focuser at 4980, not back at its start
  (5000)." The degenerate sweeps and the failure path follow the same rule. `POST /api/focuser/halt` during autofocus = stop **where it is**:
  `cancelled`, "Halted at 4875: focus left there." Halt and stop are
  ordered on the server: a halt never freezes the return move, and no
  sweep move is sent after a stop or a halt.
- Ends `done` when the sweep produced an HFD at the best position: the
  verification's, else the fit's, as the Qt engine reports it
  (`autofocus_worker.py:185`; OK "Autofocus complete — best pos=5420
  HFD=2.1"; `best.hfd_px` is null when the verification frame had no
  measurable star); `rejected` (WARN with the reason; the degenerate sweeps
  return to the start, a best position without any HFD leaves the focuser
  there); `cancelled`; or `failed` (ERROR with the exception text, and the
  focuser is driven back to the start, which the Qt worker did not do). The
  camera is released only when the worker has ended. Disconnecting the
  camera during a sweep is a Stop (return to the start); disconnecting the
  focuser is a Halt.
- Refusals: `409 not_connected` (camera or focuser), `409 busy` while an
  autofocus runs or a stopped one is still returning, or a sequence owns
  the camera. Starting it stops live view (INFO).
- The focuser moves are those of the worker: absolute moves, `IsMoving`
  polled every 0.3 s, 1 s settle after each move (`autofocus_worker.py:
  44, 214-231`).

### Conditions (A37)

```
ConditionsRow  = {"type": "conditions", "seq": int,          // row counter, increasing
                  "frame_seq": int, "t": ISO,                // exposure midpoint
                  "origin": "single"|"live", "exposure_s": float, "gain": int,
                  "frame_type": string, "filter": string,
                  "hfd_px": float|null, "fwhm_px": float|null, "star_count": int,
                  "sky_adu": float, "peak_adu": int,
                  "airmass_mount": float|null,     // Pickering, from the mount altitude (as FITS AIRMASS)
                  "airmass_target": float|null,    // the observation target from the Settings site (X2)
                  "sensor_temp_c": float|null, "focuser_temp_c": float|null,
                  "focuser_position": int|null}
ConditionsPage = {"rows": [ConditionsRow, …], "first_seq": int|null, "last_seq": int|null,
                  "truncated": bool, "boot_id": string}
```

One row per metered camera frame (live and single; not autofocus samples
nor opened files), the last 20 000 kept in memory for the session of the
server process (`GET` with `since_seq` returns rows with `seq` greater,
oldest first, `limit` 1…20 000, default 5 000). Recording the rows with a
session folder comes with sequences (wave 6); a Take shot's own values are
in its FITS header.

### Observation, catalogue lookup and suggestions (A20, A38-A41)

```
Observation = {"object_name": string,                // "" = not set ("Unknown" in FITS OBJECT)
               "target": {"name": string, "ra_hours": float, "dec_deg": float,
                          "object_type": string, "type_label": string,
                          "is_variable": bool, "source": string,
                          "programme": "variable"|"exoplanet"|"other"}|null,
               "photometry_target": {"key": string, "name": string, "path": path}|null,
               "locked": bool, "locked_reason": string|null,   // a sequence runs (wave 6)
               "revision": int}
ObservationTargetBody = {"name": string, "ra_hours": float (0…24), "dec_deg": float (−90…90),
                         "object_type"?: string, "source"?: string,
                         "programme"?: "variable"|"exoplanet"|"other"}
Resolved  = {"name", "ra_hours", "dec_deg", "object_type", "type_label", "is_variable", "source"}
Candidate = {"name", "ra_hours", "dec_deg", "object_type", "type_label", "is_variable",
             "source", "separation_arcsec"}
```

- One observation identity (D11): the object name every Take shot writes
  to `OBJECT` and its folder. `PUT /api/observation` sets the name and
  drops a target whose name differs; `POST /api/observation/target` sets
  both (port of `set_catalogue_target`, `imaging_page.py:2734-2756`): the
  name, the target coordinates (the Mount card's Slew uses them; the server
  never slews by itself), and **only for a variable-star type** (`V*`,
  `RR*`, … `is_variable_object_type`, Q-P8) or `programme: "exoplanet"`,
  the photometry target: a `target` role written to
  `<sessions_path>/targets/<object>.json` (`argos.core.catalog.targets`;
  comparisons are chosen in wave 5). Logs: INFO "Catalogue target: SS Cyg —
  RA 21.71268h Dec +43.58612°". `409 busy` with `locked_reason` while a
  sequence runs (wave 6). A change of object re-keys the target set and
  resets the live curves when those exist (waves 4-5).
- `GET /api/catalog/resolve?q=` (`object_resolver.resolve_object`, the
  bundled catalogue first, then the cache, then CDS Sesame online, 8 s):
  `400 invalid_argument` "Enter an object designation first.", `404
  not_found` "No ICRS coordinates found for ‘…’.", `502 lookup_failed`
  "Catalogue unavailable. Connect to the internet or use a previously
  searched target." (the resolver's own texts). Works without equipment.
- `GET /api/catalog/suggest?q=` (`cached_object_suggestions`): names from
  the bundled catalogue and earlier lookups, offline, at most `limit`
  (1…50, default 8): the name itself first, then the names that start with
  the text, each in natural order (numbers by value: "M 1, M 10, M 11 …",
  never "M 1, M 100, M 104", review of wave 3).
- `GET /api/catalog/nearby` (`resolve_nearby_objects`): candidates within
  `radius_arcsec` (1…3600, default 90), nearest first: the cache, then the
  bundled catalogue, then SIMBAD online **only** with `network=true`.
- **`target_suggestions` (A20).** After every Stellarium GoTo the server
  looks up names near the GoTo coordinates (port of
  `suggest_target_from_coordinates`, `imaging_page.py:2809-2841`), online
  only when `stellarium.online_target_lookup` is on, and publishes
  `{"type": "target_suggestions", "ra_hours", "dec_deg",
  "state": "checking"|"ready"|"failed", "candidates": [Candidate, …],
  "message": string|null, "t": ISO}` (INFO "Stellarium target-name
  suggestion: 2 nearby catalogue candidate(s)."; WARN "Target-name
  suggestion: …"). It only offers names: accepting one is the client's
  `POST /api/observation/target`. The newest record is also in
  `GET /api/stellarium` (`suggestions`).
- The resolver cache is `data_paths.object_catalogue_cache`.

### Opened files (A27)

`POST /api/camera/open-fits` now feeds the frame to the live pipeline as
the Qt Observe page does (`AcquisitionEngine.open_fits_frame`,
`acquisition_engine.py:741-767`, with S4):

- **Raw 16-bit data only.** The first image HDU must be one 2-D image of
  integer values 0…65535, whatever the stored type (`_raw_adu`,
  `acquisition_engine.py:125-151`): float data that is not integral (a
  calibrated or stacked frame), negative values or values above 65535 are
  `400 invalid_fits` ("… are not raw 16-bit camera counts — open the raw
  .fit frame instead"), leaving the current frame, its time and its
  metrics untouched (Review's frame inspector, wave 7, displays any FITS).
  RGB cubes are refused the same way. The size limits are unchanged.
- **Dated from its header.** `epoch_utc` is `DATE-AVG`, else `DATE-OBS` +
  `EXPTIME`/2 (`fits_exposure_mid`), else
  `null` with WARN "<name> has no usable DATE-OBS time (or EXPTIME) — no
  photometry point can be dated, so none will be measured on it." The frame
  `timestamp` is `DATE-OBS` (else the file time) as in v1; a `DATE-OBS`
  without a time part is not read as midnight: the file time stands.
- **Live view is stopped first** (Q-O11, INFO "Live view stopped to open
  <name>."); a single capture or autofocus in progress is `409 busy`.
- The frame is metered (`frame_metrics`), adds no `conditions` row, and
  becomes the frame the field identification of wave 4 will solve.

### Backpressure (wave 3)

Under backpressure (256 pending messages) the snapshot kinds of wave 3
(`filterwheel`, `focuser`, `autofocus`, `observation`,
`target_suggestions`, `frame_metrics`) are compacted to the newest of each,
like the others. The streams `frame_saved` and `conditions` are kept like
log lines (dropped oldest first only once the logs are gone); each carries
`seq`, and a client that sees a gap reads `GET /api/camera/saved` or
`GET /api/session/conditions`.

### Client messages on `/ws/events` (wave 3)

`/ws/events?token=…&client=<id>`: `client` (optional, 1-64 characters
`[A-Za-z0-9_-]`) names this connection for the jog dead-man. The socket
accepts one text message from the client: `{"type": "jog_stop"}` stops
every axis this client is jogging. Anything else is ignored.

## API 2 routes, wave 4 (Field identification and image tools)

Wave 4 (`web/spec/README.md` §7 "Field identification and image tools":
rows A32-A33, A43-A49, A51-A53) adds the routes, records and events below,
still under `"api": 2` (additive). ASTAP, catalogue queries, point
identification and the per-frame field work run on worker threads, never
on the event loop. The science rules are those of the fixed Qt engine
(0.5.0), ported Qt-free into `argos/server/field_solve.py` (ASTAP run,
WCS, grid), `field_catalog.py` (catalogue fetch, layers, candidates),
`field.py` (field state, auto identification, tracking, star selection,
centre and sync) and `targets.py` (target set and roles); each module
cites the Qt lines it ports.

| Method | Path | Body | Returns | Row |
|---|---|---|---|---|
| GET | `/api/field` | — | Field | A45 |
| POST | `/api/field/solve` | `{}` (optional) | `202 {"job_id", "field": Field}` | A43 |
| DELETE | `/api/field/solve` | — | Field (the running solve, manual or automatic, is cancelled) | A43 |
| PUT | `/api/field/auto` | `{"enabled": bool}` | Field | A44 |
| GET | `/api/field/catalog` | — | Catalog | A46 |
| POST | `/api/field/catalog/refetch` | — | `202` Catalog (`fetching`) | A46 |
| GET | `/api/field/layers` | — | FieldLayers | A47 |
| GET | `/api/field/transform` | — | FieldTransform | A48 |
| GET | `/api/field/select` | — | SelectionEvent \| `{"id": null, "selection": null}` | A49 |
| POST | `/api/field/select` | SelectBody | SelectionEvent | A49 |
| DELETE | `/api/field/select` | — | `{"id": null, "selection": null}` | A49 |
| GET | `/api/targets` | — | Targets | A51 |
| POST | `/api/targets` | TargetRoleBody | Targets | A52 |
| DELETE | `/api/targets/{key}` | — | Targets + `"removed": TargetStar` | A53 |
| POST | `/api/mount/center` | `{"target"?: {"ra_hours", "dec_deg", "name"?}}` | MountState | A32 |
| POST | `/api/mount/sync` | `{"source": "solution"}` | MountState | A33 |

New WebSocket events (`/ws/events`), all snapshots (the newest is
complete; compacted to the newest under backpressure): `field`, `catalog`,
`field_layers`, `field_transform`, `selection`, `targets`. A new client
receives each of them once, right after the replayed log lines (so the
order of the earlier snapshots is unchanged). A manual solve also
publishes `job` events (kind `field_solve`). New error codes: `no_frame` (nothing to solve),
`not_solved` (the field has no solution), `no_target`, `not_found`, `file_solution` (Centre
target or Sync on the solution of an opened file).

**Strict JSON on the socket.** `/ws/events` frames are serialised with `allow_nan=False`;
a non-finite number (NaN, ±inf) goes out as `null`, as REST answers, so `JSON.parse` never
drops a snapshot.

### Positions: frame pixels

Every position on the wire is in **frame px, numpy convention** (the
centre of pixel `(row i, column j)` is `x = j, y = i`, origin top left,
y down, never rotated by the display). The science code measures on the
green plane `(G1+G2)/2` of each 2×2 tile (`green.py:30-47`), the plane
ASTAP solves and the star detector measures; the server converts:

```
x_frame = 2 · x_green + 0.5      y_frame = 2 · y_green + 0.5      r_frame = 2 · r_green
```

(`+0.5`: the green sample of tile `(i, j)` averages raw `(2i, 2j)` and
`(2i+1, 2j+1)`, whose centroid is `(2i+0.5, 2j+0.5)`; the same rule for the
mono simulator.) Radii carry their unit: `r_px` (frame px),
`*_green_px` where a green-plane value is kept for reference.

### Field (A43-A45)

```
Field = {"state": "none"|"solving"|"solved"|"failed"|"invalidated",
         "auto": bool,                      // automatic identification armed
         "auto_source": "observer"|"sequence"|null,
         "solving": {"mode": "manual"|"auto", "job_id": string|null,
                     "frame_seq": int, "started_utc": ISO}|null,
         "reason": "slew"|"mount_moved"|"geometry"|"file_opened"|"source_changed"
                   |"center"|null,          // invalidated
         "message": string|null,            // the failure or invalidation sentence (as logged)
         "generation": int,                 // +1 on every new solution and every invalidation
         "solution": Solution|null,         // the last good solution (a failed attempt keeps it)
         "wcs": FrameWcs|null,
         "grid": Grid|null,
         "target_reticle": {"x", "y", "name", "ra_hours", "dec_deg"}|null,
                                            // null when the target is 90° or more from the
                                            // field (it has no TAN projection)
         "last_attempt": {"mode": "manual"|"auto", "outcome": "solved"|"failed"|"cancelled",
                          "message": string, "t": ISO}|null,
         "center_available": bool,          // a solution of a CAMERA frame, a connected mount
                                            // and a target (never for an opened file)
         "revision": int}

Solution = {"ra_hours", "dec_deg",                  // CRVAL (J2000)
            "scale_arcsec_px": float|null,          // per FRAME px (ASTAP green scale ÷ 2)
            "rotation_deg": float|null,             // ASTAP's (CROTA2): the sensor frame's angle
            "mirrored": bool|null,                  // the sky as the wire draws it (frame px, y
                                                    // down): det(CD) < 0; not ASTAP's FITS flag
            "delta_target_arcmin": float|null, "target_name": string|null,
            "frame_seq": int, "frame_origin": "live"|"single"|"file"|…,
            "frame_shape": [h, w],                  // frame px
            "mode": "manual"|"auto", "solved_utc": ISO,
            "hint": {"ra_hours", "dec_deg", "source": "mount"|"header"}|null,
            "summary": string}                      // the OK log line
FrameWcs = {"ctype": ["RA---TAN", "DEC--TAN"],
            "crval": [ra_deg, dec_deg],
            "crpix": [x1, y1],                      // FITS 1-based, frame px
            "cd": [[cd1_1, cd1_2], [cd2_1, cd2_2]], // degrees per frame px
            "frame_shape": [h, w]}
            // numpy x = FITS pixel − 1; TAN projection as in FrameWCS (platesolve.py:329-379)
Grid = {"lines": [[[x, y], …], …],                  // polyline segments (broken off-frame)
        "labels": [{"x", "y", "text", "axis": "ra"|"dec"}],
        "centre": {"x", "y", "label"}|null}
```

- **Identify field** (`POST /api/field/solve`, `solve_now`
  `acquisition_engine.py:1038-1056`, `astrometry_controller.py:105-119`):
  solves the newest frame (live, Take shot or opened file) on its green
  plane with the thorough settings (`build_solve_settings(live=False)`,
  `astrometry_session.py:36-75`: 120 s timeout, blind retry). The ASTAP
  database flags follow S24 (`-D <set> -d <folder>`, `platesolve.py:306-319`).
  Hint: the connected mount's pointing for a camera frame; for an opened
  file the header's `OBJCTRA`/`OBJCTDEC` (the mount points elsewhere), else
  blind. `409 no_frame` "No frame to solve yet — take a frame or open a FITS
  image first."; `409 busy` (`owner` = the solve's job id, or `"auto"`)
  while a solve runs. A half-quality preview cannot occur: the server keeps
  every frame at full resolution (Q-O14), so `decimated` is never
  answered. The answer is `202 {"job_id", "field"}`; the job (kind
  `field_solve`, resource `field`) reports its stages (`"ASTAP"`,
  `"ASTAP at native sampling"`, `"ASTAP whole-sky"`) and ends `done`
  (`result` = Solution), `failed` (`error.code` `not_solved`, message as
  ASTAP's) or `cancelled`. An unexpected error after ASTAP (a degenerate WCS, an I/O
  error) ends the attempt the same way (`failed`, `not_solved`, ERROR "Solve: the
  solution could not be used (…)"): the field is never left claimed by a finished job.
  The job starts `running` with `stage: "queued"`. CMD "Plate-solving frame #<seq>… (hint RA <h>h
  Dec <d>°)" / "(blind — no mount)" / "(hint from the FITS header)".
- **Cancel**: `DELETE /api/jobs/{id}` or `DELETE /api/field/solve` kills
  the ASTAP process at once (the Qt solve could not be cancelled); the
  field keeps its previous solution; INFO "Field identification
  cancelled.".
- **Result** (`_on_worker_solved` `astrometry_controller.py:210-238`,
  `_on_astrometry_solved` `imaging_page.py:1393-1416`): OK "Solved — RA
  …h  Dec …°  …″/px  rot …°  Δtarget …′" (the full-resolution scale; the
  Qt summary); `generation` +1; the catalogue is fetched once per field
  (A46); the target set is re-projected. A solution for a frame whose
  geometry is no longer the current one is discarded (INFO "Solve finished
  for a different frame geometry — discarded."). A failure keeps the last
  good solution: `state: "failed"`, ERROR "Solve: <message>" (manual),
  INFO for an automatic attempt.
- **Automatic identification** (`PUT /api/field/auto`,
  `astrometry_controller.py:82-85, 121-154`): per new frame (latest wins,
  on the field thread) a live solve (`live=True`: bounded timeout,
  `astrometry.live_search_radius_deg`) starts when the field has no
  solution, `astrometry.live_resolve_s` (20 s) passed, or the mount moved
  `astrometry.live_resolve_arcmin` (2′) since the last attempt. An
  automatic solve is no job (README §4.2) but is cancellable with
  `DELETE /api/field/solve`. INFO "Automatic field identification on/off".
  Sequences (wave 6) arm it for the run even without a prior solution
  (Q-O12) through `FieldService.arm_for_sequence()` / `disarm_after_sequence()`,
  which restore the observer's choice afterwards (`auto_source: "sequence"`).
- **Invalidation** (`_clear_astrometry` `imaging_page.py:2501-2563`,
  `invalidate_astrometry` `acquisition_engine.py:1067-1084`): the
  solution, the catalogue, the layers, the tracking transform and the
  selection are dropped (the Qt card and ring stayed, P24) and
  `state: "invalidated"` with `reason`: `slew` (an ARGOS GoTo), `center`
  (Centre target), `mount_moved` (the mount reports ≥
  `astrometry.live_resolve_arcmin` from where it was at the solve, a slew
  from Stellarium or the Seestar app: INFO "Mount pointing changed outside
  ARGOS — stale astrometry overlays cleared. Plate-solve the current
  frame."), `geometry` (a frame of another size, INFO "Frame geometry
  changed — WCS overlays cleared (solve again)."), `file_opened` (Open
  FITS, `acquisition_engine.py:741-767`) or `source_changed` (camera
  frames arrive after an opened file was solved: its solution would be
  drawn on another field). The target set is kept. A solve running at
  that moment is cancelled and released at once (`solving: null`; a new
  Identify field may start); one that ends after the field moved is
  discarded (INFO "Solve finished for a field that has moved since —
  discarded.": Qt applied it to the new field). A cancelled attempt
  returns the field to its previous state.

### Catalogue (A46)

```
Catalog = {"state": "idle"|"fetching"|"ready"|"error",
           "generation": int,               // the field generation it belongs to
           "centre": {"ra_hours", "dec_deg"}|null, "radius_deg": float|null,
           "counts": {"variables", "comparisons", "field_stars", "named_objects",
                      "exoplanet_hosts"},
           "limits": {"field_stars": int, "named_objects": int},   // budgets asked
           "warnings": [string],            // Qt's VSP warning, plus each source that failed
                                            // ("Gaia DR3 unavailable: …", "SIMBAD unavailable: …",
                                            // "NASA Exoplanet Archive unavailable: …"); the log
                                            // lines stay Qt's
           "error": string|null,
           "fetched_utc": ISO|null, "revision": int}
```

- Fetched on a thread once per field after a solve (`maybe_fetch_catalog`,
  `acquisition_engine.py:1105-1173`: re-used while the field centre moved
  less than the field radius; VSX at the solved centre, VSP around the
  first target of the set, the 70 / 30 Gaia / SIMBAD split of
  `catalog.identification_max_objects`, every `catalog.*` key as Qt) with
  the queries of `CatalogWorker.run` (`catalog_worker.py:90-172`). The
  log lines are Qt's (`_on_catalog`, `acquisition_engine.py:1175-1240`).
  Not cancellable (as Qt); a newer field discards a late result.
- `POST /api/field/catalog/refetch` (`refetch_catalog`,
  `acquisition_engine.py:1086-1103`): `409 not_solved` "Identify the field
  first: the catalogue is fetched around a plate solution." instead of a
  silent no-op; `409 busy` while a fetch runs. A `PATCH /api/config` of a
  key the fetch reads (`catalog.mag_limit`, `max_results`,
  `include_suspected`, `field_stars_*` except `detected_only`,
  `identification_max_objects`, `named_objects_*`, `exoplanet_hosts_*`)
  refetches the solved field (debounced 0.5 s).
- When the VSP answer arrives after a target was chosen, comparisons are
  auto-selected for it (`acquisition_engine.py:1225-1240`, A52).

### Layers (A47) and the tracking transform (A48)

```
FieldLayers = {"generation": int, "revision": int,
               "available": bool,                    // the field is solved
               "frame_shape": [h, w]|null,
               "display_mag_limit": float,          // catalog.display_mag_limit
               "aperture_r_px": float,              // photometry aperture (frame px)
               "layers": {"stars": [Marker], "variables": [Marker], "galaxies": [Marker],
                          "nebulae_clusters": [Marker], "exoplanets": [Marker],
                          "other_objects": [Marker], "vsp": [Marker], "selected": [Marker]},
               "counts": {layer: int},               // Qt chip counts (display limit applied)
               "candidates": [Candidate],            // FieldBand table (PROPOSAL §7)
               "limits": {"comparison_max_separation_arcmin", "comparison_max_delta_mag",
                          "comparison_min_snr",       // the observer's photometry.* rules
                          "gaia_depth_g": float|null  // G the held Gaia list is complete to
                         }|null}
Marker = {"id": string,                              // stable within a generation
          "x", "y",                                  // frame px through the REFERENCE solve
          "label": string,                           // "" when Qt drew no label
          "tooltip": string,                         // Qt's tooltip text, lines joined by \n
          "kind": "gaia"|"simbad"|"point_identity"|"variable"|"deep_sky"|"exoplanet"|"vsp"|"target",
          "key": string|null,                        // TargetStar key the star would have in the set
          "ra_hours", "dec_deg",
          "g_mag"?: float|null, "suspected"?: bool, "role"?: string, "detected"?: bool,
          // variables: "index", "name", "var_type", "mag_text", "max_mag", "min_mag",
          //   "brightest_mag", "period_d", "auid", "sep_arcmin" (from the field centre)
          // stars: "source_id", "bp_mag", "rp_mag", "name"|null}
Candidate = {"auid", "label", "chart_id", "x", "y", "ra_hours", "dec_deg", "key",
             "v_mag": float|null, "b_mag": float|null,
             "b_minus_v": float|null,                // VSP B − V, null unless both bands
             "delta_b_minus_v": float|null,          // minus the target's B − V (VSP or SIMBAD/Gaia: null)
             "sep_arcmin": float|null,               // from the first target, else the field centre
             "peak_adu": int|null, "snr": float|null, "saturated": bool|null,
             "neighbours_in_aperture": int|null,     // see below; null when it cannot be stated
             "vsx": {"name", "var_type", "suspected", "max_mag", "min_mag", "sep_arcsec"}|null,
                                                     // a VSX entry within 3″ (a known or
                                                     // suspected variable)
             "detected": bool, "role": string|null, "measured_seq": int|null}
FieldTransform = {"generation": int, "frame_seq": int|null,
                  "rot_deg": float, "dx": float, "dy": float,   // frame px
                  "cx": float, "cy": float,                     // pivot, frame px
                  "anchors": int, "residual_px": float|null,
                  "anchor_source": "target_set"|"detected"|null, "lost_frames": int,
                  "tracking": "ok"|"degraded"|"lost"|null}     // null: no frame tracked yet
```

- **Projection** (`_project_catalog` `imaging_page.py:1497-1754`,
  `_project_targets` 1756-1783): through the **reference** solve, sent
  once per catalogue generation and again (`revision` +1) when the target
  set or a display key changes (`catalog.display_mag_limit`,
  `catalog.field_stars_detected_only`, `catalog.show_essential_objects`,
  `catalog.show_cached_exoplanets`). Rules: VSX all in frame; Gaia carry
  `g_mag` (the client filters by the display limit; counts use it), and
  with `catalog.field_stars_detected_only` only sources within 4 green px
  of a source detected on the solved frame (up to 2 000 sources; Qt kept
  the 120 brightest, too few on a rich field); SIMBAD names cross-matched to
  Gaia within 3″ (one marker per source, 1801-1836), generic survey ids
  never used as labels (1898-1917); SIMBAD categories galaxy / nebula /
  cluster / star / other (1868-1896); Essential catalogue objects within
  the field radius (`catalog.show_essential_objects`); cached exoplanet
  hosts (`catalog.show_cached_exoplanets`); markers within 8 green px
  merged (1839-1856); VSP candidates only where a source was detected
  (1694-1705); `selected` = the target set with `role`. Point identities
  found by A49 join the stars (or their category) for the field.
- **Tracking** (`ApertureTracker`, `tracking.py:235-339`;
  `_wcs_for_frame` / `_build_live_tracker` `acquisition_engine.py:1542-1593`;
  the web's `FieldTracker`, `field_track.py`): every new frame of the solved
  geometry re-centroids the anchors and fits a rigid transform (rotation +
  translation on an alt-az mount; translation only on an equatorial mount,
  `allow_rotation`). In Qt only photometry used the tracker; here it also
  places every overlay, hit-tests clicks and gives Centre and Sync the
  current frame's centre, so it departs from Qt where a wrong lock would be
  drawn:
  - **Anchors**, chosen on the **solved** frame (where the reference
    positions are true): the target set's comparisons and checks that pass
    `select_tracking_anchors` (Qt); with fewer than two of them, up to six
    bright stars detected on the solved frame, unsaturated (3×3 peak below
    `sat_adu` on the solved frame), 20 green px apart (`anchor_source:
    "detected"`; one anchor gives no rotation and no consistency test);
    else every star of the set (Qt's last resort).
  - Each anchor's signal baseline (core's 20 % lost-anchor test) is measured
    on the solved frame; each centroid is taken twice, the second window
    centred on the first (a window centred on the prediction lags a moving
    star by about one frame px).
  - With three or more anchors an update needs two anchors whose
    separations agree with the reference within 1.5 green px; a lone window
    that slid onto another star or onto sky is no lock.
  - A frame with no consistent anchor keeps the previous transform
    (`lost_frames` counts them, `tracking: "lost"`) and is re-acquired by
    matching the frame's detected stars to the solved frame's 300 brightest
    with a translation vote (at least 6 matched stars), then refitted. WARN
    "Tracking: no anchor star found — overlays and apertures unguided" once
    per loss (Qt logged its line on every frame); INFO "Tracking: field found
    again (n anchors)." when it comes back. `degraded`: fewer anchors used
    than min(3, constellation).
  - A target-set change rebuilds the constellation **from the current
    pose** (Qt reset to the identity, `acquisition_engine.py:1301`, which is
    wrong once the field has drifted); a new solution resets to identity.
  The marker at reference position `(x, y)` is drawn at
  `x' = cx + cos θ·(x − cx) − sin θ·(y − cy) + dx`,
  `y' = cy + sin θ·(x − cx) + cos θ·(y − cy) + dy` with `θ = rot_deg`.
  Measured on 195 consecutive frames of a real RR Lyr session against
  star-matching truth: 0.2-0.9 frame px median error, no loss; with jumps of
  45 green px (every tenth frame) every step was re-acquired.
- **Candidates** (PROPOSAL §7; the FieldBand table): the VSP comparison
  stars inside the frame, measured on the solved frame (`measure_aperture`
  at the catalogue position snapped as `_pilot_comparison_quality`,
  `acquisition_engine.py:1431-1491`). `b_minus_v` = VSP `B` − VSP `V`.
  `neighbours_in_aperture` = the Gaia DR3 sources of the field, other than
  the candidate itself (its counterpart: the nearest Gaia source within
  max(3″, FWHM/2) whose G is within 1.5 mag of the VSP V; and any source
  within 1 frame px), whose reference position lies within the photometry
  aperture radius (`aperture_r_px`) of the candidate and that are at most
  3 mag fainter than it (`G ≤ m + 3`, `m` = the counterpart's G, else VSP
  V). `null` unless the held Gaia list is complete to `m + 3`
  (`limits.gaia_depth_g`: the query's G limit, or its faintest source when
  the identification budget truncated it), or without Gaia sources: a
  definite 0 is never claimed where the list cannot see. `vsx`: the VSX
  entry within 3″ of the candidate (the band says "variable?"; the
  automatic selection is Qt's and does not exclude it, an owner decision).

### Star selection (A49)

```
SelectBody = {"x": float, "y": float,     // frame px
              "seq"?: int,                 // the frame the click was made on
              "tol_px"?: float}            // hit tolerance, frame px (default 20 = 10 green px)
SelectionEvent = {"id": int, "state": "identifying"|"resolved"|"no_match"|"failed"|"tracking",
                  "selection": Selection|null, "message": string|null}
Selection = {"id": int, "seq": int,
             "kind": "target"|"variable"|"vsp"|"simbad"|"deep_sky"|"exoplanet"|"gaia"
                     |"point_identity"|"measured"|"none",
             "title": string, "rows": [{"key": string, "value": string}],
             "ring": {"x", "y", "r_px", "aperture": "photometry"|"star",
                      "space": "reference"|"frame"}|null,
                      // reference: a catalogue position, moved by field_transform like the
                      // markers; frame: the clicked / measured position on frame `seq`
             "pending_star": PendingStar|null,
             "key": string|null, "role": string|null,      // its key / role in the set
             "roles_enabled": bool, "roles_reason": string|null,
             "removable": bool, "identifying": bool,
             "measurement": {"x", "y", "fwhm_px", "hfd_px", "fwhm_arcsec", "hfd_arcsec",
                             "eccentricity", "snr", "peak_adu", "sky_adu",
                             "ra_hours"|null, "dec_deg"|null}|null}
PendingStar = {"ra_deg", "dec_deg", "ra_hours", "auid", "name", "source", "mags", "chart_id"}
```

- Hit-test order and card bodies of `_on_star_clicked`
  (`imaging_page.py:804-978`): a star of the target set, a VSX variable, a
  VSP comparison, a SIMBAD object, an Essential catalogue object, an
  exoplanet host, a Gaia source, an earlier point identity — hidden layers
  still identify (Q-O18) — then an unmarked source: `measure_star_at`
  (`metrics.py:225-276`). With a solution the click is identified by a
  10″ Gaia / SIMBAD cone (`identify_point_source`; network as Qt: Gaia
  when `catalog.field_stars_enabled`, SIMBAD when
  `catalog.named_objects_enabled` and `catalog.named_objects_allow_network`,
  Q-O1): the answer is `identifying` at once and the outcome arrives as a
  `selection` event (`resolved` / `no_match` / `failed`). A new select
  supersedes a running lookup (its late answer is dropped, P21). Without a
  solution the card shows the measurement, `roles_enabled: false`,
  `roles_reason` "identify the field first".
- A measured (unmarked) star is followed frame by frame (`state:
  "tracking"`, `_remeasure_selection` `imaging_page.py:1241-1257`,
  `TRACK_SNAP_SEARCH`). The selection is dropped by `DELETE`, a field
  invalidation and a frame geometry change.
- `409 no_frame` without a frame; `400 invalid_argument` outside the frame.

### Target set (A51-A53)

```
Targets = {"object_name": string,         // the set's key (D11), "Unknown" when empty
           "path": string,                // <sessions_path>/targets/<object>.json
           "stars": [TargetStar], "summary": {…},   // TargetSet.summary() (targets.py:98-122)
           "geometry": {"aperture_px", "annulus_in_px", "annulus_out_px",   // green px
                        "aperture_r_px", "annulus_in_r_px", "annulus_out_r_px",  // frame px
                        "fwhm_px": float|null, "fwhm_source": "frame"|"default"},
           "revision": int}
TargetStar = {"key", "role": "target"|"comparison"|"check", "name", "display_name",
              "ra_deg", "dec_deg", "ra_hours", "auid", "source", "mags", "chart_id", "note",
              "x": float|null, "y": float|null}   // reference frame px when solved and in frame
TargetRoleBody = {"role": "target"|"comparison"|"check",
                  // exactly one of:
                  "selection"?: int,            // the current Selection's id (its pending_star)
                  "star"?: PendingStar,         // ra_deg/dec_deg (exact), or ra_hours
                  "variable_index"?: int}       // Marker.index of the variables layer
```

- `POST /api/targets` (`_on_card_role` `imaging_page.py:2035-2044`,
  `set_target_role` `acquisition_engine.py:1295-1302`): fills the object
  name with the star's name when it is empty (D11, before the save), sets
  the role (`TargetSet.set_role`), auto-selects VSP comparisons for a new
  target when the field's VSP sequence is known (`_auto_select_comparisons`
  with the pilot quality gate, 1348-1491; WARN when fewer pass), writes
  `targets/<object>.json` atomically in the Qt format, resets the
  tracking, and publishes `targets` and `field_layers`. OK "<Role>:
  <name>". `409 not_found` for a selection that is no longer the current
  one; `404 not_found` for a `variable_index` the field's catalogue does
  not have; `409 busy` while a sequence owns the observation.
- `DELETE /api/targets/{key}` (`remove_target`, 1506-1511): the answer
  carries `removed` (the star as it was, for Undo = `POST` with `star`);
  `404 not_found` for an unknown key. OK "Removed from target set: <name>".
- The set follows the observation's object name (`on_object_changed`,
  1281-1293): a new name re-reads its own file and publishes `targets`.
  `geometry` is `photometry_geometry` (1493-1504) on the last frame's mean
  FWHM (`fwhm_source: "frame"`), else the default FWHM.

### Centre target and Sync (A32, A33)

- `POST /api/mount/center` (`_center_selected_target`
  `imaging_page.py:2692-2715`, `center_target_from_solution`
  `device_session.py:734-765`): target = the body's, else the first
  `target` of the set, else the last GoTo target; the solved centre is
  read through the **tracked** solution (the current frame's centre, S30:
  Qt used the reference solve). Tracking on, Sync to the solved centre,
  GoTo the target; the field is invalidated (`reason: "center"`). CMD
  "Center: synced solved field RA …h Dec …°", "Center: slewing to target
  RA …h Dec …°". `409 not_solved`, `409 file_solution` ("This solution is
  for an opened file, not where the mount points: identify a camera frame
  first."; an opened file says nothing about the mount's pointing, and a
  sync on it would corrupt the pointing model), `409 no_target`,
  `409 not_connected`, `409 clock_error` (H4), `409 parked`.
- `POST /api/mount/sync` `{"source": "solution"}` (Q-O3: "Sync to plate
  solution", no slew; `telescope.py:540-562`): syncs the mount to the
  current frame's solved centre; the field stays valid (its mount
  reference is moved to the new reading). `409 not_solved`,
  `file_solution`, `not_connected`, `clock_error`, `parked`; a driver refusal (tracking off)
  is `502 device_error` with its text.

### Backpressure (wave 4)

`field`, `catalog`, `field_layers`, `field_transform`, `selection` and
`targets` are snapshots: under backpressure only the newest of each is
kept. `field_layers` can carry a few thousand markers (the Gaia budget),
so it is sent once per generation or change, never per frame; the per
frame motion is `field_transform`.

## API 2 routes, wave 5 (Live photometry)

Wave 5 (`web/spec/README.md` §7 "Live photometry": rows A50, A54-A58) adds
the routes, records and events below, still under `"api": 2` (additive).
The live measurement is the fixed Qt engine's (0.5.0), ported Qt-free into
`argos/server/photometry.py` with the source lines it ports:
`_measure_photometry`, `_wcs_for_frame`, `_build_live_tracker`,
`_emit_live_point`, `_apply_systematic_floor`, `_write_live_quality_report`,
`_photometry_csv_path`, `_diagnostics`, `propose_comparison_stars`,
`reselect_comparison_stars` (`acquisition_engine.py:887-913, 1304-1346,
1531-1795`) over the unchanged core (`measure_frame`, `ApertureTracker`,
`comparison_quality_report`, `LightCurve.to_csv`, `bjd_tdb`, `airmass_at`).
Every measurement runs on the photometry thread, never on the event loop.

| Method | Path | Body | Returns | Row |
|---|---|---|---|---|
| GET | `/api/field/variables` | — | FieldVariables | A50 |
| GET | `/api/photometry/live` | — | LivePhotometry | A54 |
| POST | `/api/photometry/comparisons/recommend` | RecommendBody | Recommendation | A58 |

New WebSocket events (`/ws/events`): `photometry_point` (A55) and
`photometry_reset` (A56) form one **stream** with its own `seq` (a client
that sees a gap, or a `revision` it does not hold, re-reads `GET
/api/photometry/live`); `comparison_quality` (A57) and `photometry` (the
live status, shown by the Field band) are **snapshots**. A new client
receives `photometry`, `comparison_quality` and the newest `frame_metrics`
once, after the wave 4 snapshots. New error code: `no_comparison`.

### When a point is measured

As Qt, **one point per solution outside a sequence**
(`measure_photometry_if_idle`, `acquisition_engine.py:1062-1065`, called by
`_on_astrometry_solved`, `imaging_page.py:1417`): every successful Identify
field (A43) and every automatic identification (A44) measures the target
set once, on the newest frame of the solved geometry at the moment the
solution is applied (Qt's `_last_raw`), through that solution. With
automatic identification on, live view therefore gives one point per
re-solve (`astrometry.live_resolve_s`, 20 s by default, or a mount move).
A sequence (wave 6) will measure every saved sub instead
(`_on_seq_frame_saved`, 772-797); the service already has that entry
(`measure_saved_frame`).

Nothing is measured (`photometry.state` says why, no point, no CSV line)
when the set has no `target` (`no_target`), the frame has no epoch
(`no_epoch`: WARN "Photometry skipped: the frame has no exposure time
(DATE-OBS/EXPTIME).") or no star of the set is where the solution places it
(`field_lost`, see the tracker below). The epoch is the exposure **midpoint**: camera frames
`start + (end − start)/2` (`_on_frame`, 588-591); opened files `DATE-AVG`,
else `DATE-OBS` + `EXPTIME`/2 (`fits_exposure_mid`); a frame written by Argos
before 0.5.0 (`SOFTWARE` `Argos` or `Argos v0.x` below 0.5) always by
`DATE-OBS` + `EXPTIME`/2, its sequence `DATE-AVG` being late by half the image
download (release S39). A point is
kept when its differential magnitude **or** its flux ratio exists (S18:
ratio-only points have `mag: null`); a star with neither (off frame,
saturated ensemble, no comparison) gives no point that frame.

### Measurement (identical to Qt)

- **Plane and geometry**: the green plane (`green_plane`); aperture
  `max(photometry.aperture_min_px, photometry.aperture_fwhm_mult × FWHM)`,
  annulus `max(annulus_in_px, r_ap + 1)` to `max(annulus_out_px, r_in + 2)`
  (green px, `measure_frame`, `params.py:80-111`). **Series FWHM** (P7): the
  mean FWHM of the stars detected on the first measured frame (`detect_stars`
  with `imaging.star_radius_px`, as `frame_metrics`), frozen for the series;
  3.0 px (`DEFAULT_FWHM`) on a frame without a measurable FWHM, re-sampled on
  the next. The series restarts at an object change. (Qt 0.5.0 froze the
  **second** frame's FWHM, so the first point had its own aperture: fixed
  for 0.5.0 in the release branch, see `notes/release_0_5_0.md` S31; the
  server follows the fix.)
- **Apertures placed by core's `ApertureTracker`** (owner decision; not the
  wave 4 `FieldTracker`, which keeps placing the overlays): built on the
  first measured frame after a new solution, a target-set change or an
  object change (`_build_live_tracker`, 1569-1582): anchors =
  `select_tracking_anchors` over the comparisons and checks (SNR ≥ 10,
  unsaturated, not suspect, at most 6), else any star of the set **seen where
  the solution places it** (SNR ≥ 5); a tracker built with none is built
  again on the next frame. Search radius `max(8, 2 × aperture(None))` green
  px; updated on every measured frame with rotation unless the mount reports
  `eq` / `eq_gem` (`_wcs_for_frame`, 1542-1567). A frame on which no anchor
  is found (the field moved further than the search radius since the
  solution, or clouds hide every anchor) gets **no point**: WARN "Photometry
  skipped: no star of the set where the solution places it — the field moved
  since the solve, or clouds.", status `skipped` / `field_lost`, a
  `frame_skipped` event in the flight recorder. (Qt 0.4.2 fell back to every
  star of the set unseen and measured blank sky with no flag: fixed for
  0.5.0, `notes/release_0_5_0.md` S35; the server follows the fix.)
  `photometry.track_apertures: false` measures through the solution alone.
  Outside a sequence each point follows a fresh solution, so the tracker
  only re-centres the solution on that frame's anchors.
- **Calibration** (`measure_targets`, `session.py:47-160`): targets and
  checks against the full ensemble, each comparison leave-one-out;
  `egain` from `camera.egain_table`, else the driver, else the sensor model;
  an opened frame keeps its own: the table at its `GAIN`, else its `EGAIN`
  (`frame_egain`, release S41), the chain above only when it records neither.
  A Take shot's header `EGAIN` follows the same chain (release S42).
- **Errors and flags**: `formal_mag_err`; `mag_err` = `hypot(max(0,
  formal), σ_syst)` once the curve has ten valid points (or with
  `photometry.systematic_floor_mag`), recomputed for every point of the
  curve after each new point (`_apply_systematic_floor`, 1767-1795; the
  client recomputes the earlier bars the same way from `sigma_syst`);
  `saturated` (aperture peak ≥ `camera.linearity_max_adu`), `suspect`
  (hot pixel / cosmic, `aperture.py:109-136`), never used to drop a point.
- **Time and airmass** (X2): `jd_utc` of the midpoint; with a site set
  (`observing_site`: a name, or coordinates other than 0/0) `bjd_tdb` from
  astropy for the star's own RA / Dec and the site, and the star's own
  airmass at `jd_utc` (Pickering); without a site no `bjd_tdb` and the
  mount's airmass for a camera frame (`null` without a mount, and `null` for an
  opened file, another night: Qt used the mount's current altitude, fixed for
  0.5.0, `notes/release_0_5_0.md` S34).
- **Files**: each curve is rewritten after every point by
  `LightCurve.to_csv` (15 columns, `lightcurve.py:14-30`; written beside the
  file and renamed over it, so a reader never sees it half written: release
  S38) at
  `<sessions_path>/targets/<object>_<YYYYMMDDTHHMMSSZ>_<auid or name>.csv`
  outside a run, one file per curve named after its start (`-2`, `-3`… on the
  time for two in one second), so measuring an object again never overwrites
  an earlier curve (`_photometry_csv_path`, release S40; inside a run, wave 6:
  `<run>/photometry/<role>_<object>_<tag>.csv`); with `diagnostics.enabled`
  the flight recorder `<sessions_path>/targets/<object>_live_diagnostics.jsonl`
  (`star`, `ensemble`, `frame` records). The leave-one-out report is written
  to `<run>/photometry_quality.json` inside a run only (S17).

### Live photometry (A54)

```
LivePhotometry = {"object_name": string, "run_root": path|null,
                  "sequence_running": bool,
                  "band": string,                    // photometry.default_band ("TG")
                  "obscode": string,                 // observer.obscode
                  "chart_id": string|null,           // the comparisons' single VSP chart
                  "site_set": bool,                  // X2: BJD_TDB and the star's airmass
                  "geometry": Geometry,              // as Targets.geometry, plus
                                                     // "series_fwhm_px": float|null
                  "curves": [Curve], "quality": Report|null,
                  "status": PhotometryStatus,
                  "revision": int,                   // +1 at every reset
                  "seq": int}                        // the newest point / reset seq
Curve = {"key": string,                  // Qt's curve key: AUID, else the display name
         "star_key": string|null,        // TargetStar key in the set (null: no longer in it)
         "role": "target"|"comparison"|"check", "name": string, "auid": string|null,
         "mags": {band: float},          // catalogue magnitudes (VSP)
         "catalogue_v": float|null,      // D10: the check is plotted as check − this
         "sigma_syst": float|null,       // the curve's current floor
         "csv": path|null,
         "points": [LcPoint]}
LcPoint = {"jd_utc": float, "t": ISO,    // the exposure midpoint (ms)
           "bjd_tdb": float|null,
           "mag": float|null,            // null: ratio-only point (S18)
           "mag_err": float|null,        // final: with the floor
           "formal_mag_err": float|null, "sigma_syst": float|null,
           "airmass": float|null, "fwhm": float|null,   // series FWHM, green px
           "sky_adu": float|null, "comps_used": int,
           "relative_flux": float|null, "relative_flux_err": float|null,
           "relative_comps_used": int,
           "saturated": bool, "suspect": bool,
           "frame_seq": int,             // the /ws/frames seq it was measured on
           "zero_point": float|null,     // the star's ensemble zero point on that frame
           "zp_rms": float|null}         //   (mean catalogue − instrumental) and its rms
```

`LcPoint` carries every `LcPoint` field of `lightcurve.py:38-62` (the CSV
columns) unrounded; `null` for a value the CSV leaves empty or a NaN.
`zero_point` and `zp_rms` are `DiffResult.zero_point` / `zp_rms` (rounded to
4 decimals by core, as the flight recorder's `ensemble` record): not in the
CSV; for the target, the night's extinction and transparency (the plot's
ensemble facet). A frame may be measured twice (two solutions on the same
opened frame): its points are kept twice, as Qt keeps them.
Curves are listed in measurement order (Qt's dict order).

### Points and resets (A55, A56)

```
PhotometryPoint = {"type": "photometry_point", "seq": int, "revision": int,
                   "frame_seq": int, "key": string, "star_key": string, "role": string,
                   "name": string, "auid": string|null,
                   "index": int,                 // position of the point in its curve
                   "point": LcPoint,
                   "sigma_syst": float|null}     // the curve's floor after this point
                   // when it changed, every earlier point with a magnitude has
                   // mag_err = hypot(max(0, formal_mag_err), sigma_syst) (Python's
                   // math.hypot bits): the client recomputes them row by row, in
                   // whatever order the frames were measured (Qt re-rendered the
                   // store, S19). The whole column is never resent.
PhotometryReset = {"type": "photometry_reset", "seq": int, "revision": int,
                   "reason": "object_changed"|"role_changed"|"cleared"|"sequence_started"}
```

One `photometry_point` per kept point, in measurement order (the frame's
stars in target-set order). `index` counts the curve's points received
(measurement order, not time order: an older opened frame is inserted in
time by the client). `photometry_reset` follows an object change
(`on_object_changed` → `clear_lightcurves`, 258-274, 1281-1293; the CSVs stay
on disk), a star measured under a new role (its curve starts again: a
comparison's leave-one-out magnitudes and a check's are different quantities;
Qt appended to the old curve, fixed for 0.5.0, `notes/release_0_5_0.md` S33)
and, in wave 6, a sequence start (650-692). Both kinds share `seq`; a client
that re-reads the snapshot ignores the events whose `seq` it covers.

### Comparison quality (A57) and the live status

```
ComparisonQuality = {"type": "comparison_quality", "revision": int,
                     "frame_seq": int|null, "report": Report|null}
Report = {… comparison_quality_report (quality.py:22-98) as written to
          photometry_quality.json: schema, generated_utc, selection_status
          ("insufficient_data"|"not_ready"|"live_preview_consistent"),
          scientific_note, criteria {min_points, max_scatter_mag,
          max_formal_error_mag}, comparison_stars [Entry] …}
Entry = {"name", "auid", "n_valid", "scatter_mag", "median_formal_error_mag",
         "status": "insufficient_data"|"noisy"|"unstable"|"stable",
         // added on the wire:
         "key": string,                          // its curve key
         "star_key": string,                     // its TargetStar key
         "last": {"mag", "mag_err", "comps_used", "jd_utc"}|null}
                                                 // its newest leave-one-out point
PhotometryStatus = {"type": "photometry",
                    "state": "off"|"waiting"|"measured"|"skipped",
                    "reason": "no_target"|"not_solved"|"no_epoch"|"no_comparison"
                              |"no_point"|"field_lost"|null,
                    "message": string|null,
                    "frames": int, "points": int,        // since the last reset
                    "last": {"frame_seq", "t", "jd_utc", "bjd_tdb"|null,
                             "points": int,               // kept on that frame
                             "target": {"key", "mag", "mag_err", "bjd_tdb"}|null,
                             "aperture_px": float, "fwhm_px": float,   // green px
                             "anchors": int|null,         // tracker anchors used
                             "tracking": {"rot_deg", "dx", "dy",       // green px
                                          "residual_px"}|null}|null,
                    "revision": int}
```

The leave-one-out report is computed after every measured frame, in live
preview too (S17, Q-R13), with `photometry.comparison_validation_*`; a reset
sends `report: null`. Per comparison, `status` is its leave-one-out status
(PROPOSAL §7). `photometry.state`: `off` (no target in the set), `waiting`
(a target, no solution yet, or the set changed since the last measurement:
the next solution measures), `measured` (the last attempt kept points),
`skipped` (the last attempt kept none: `no_epoch`, `field_lost`,
`no_comparison` when the set has no comparison, else `no_point`). A curve's
`star_key` is `null` once its star left the set.

### Field variables (A50)

```
FieldVariables = {"available": bool,           // the field is solved and its catalogue known
                  "generation": int,           // field_layers generation
                  "rows": [VariableRow]}
VariableRow = {"index": int,                   // A52 variable_index
               "name", "var_type", "mag_text",  // "max – min" as VSX gives them
               "brightest_mag": float|null, "period_d": float|null,
               "sep_arcmin": float|null,        // from the solved field centre
               "in_set_role": "target"|"comparison"|"check"|null,
               "suspected": bool, "auid": string|null, "key": string,
               "ra_hours", "dec_deg", "x", "y"}  // reference frame px
```

The VSX variables inside the solved frame, in catalogue order (brightest
first), as the Qt Variables tab (`_refresh_variable_table`,
`imaging_page.py:2230-2250`; `variable_table.py:58-200`; the role instead
of Qt's "●"). Filtering and sorting are the client's (Q-R: no server
filter). Before a solution: `available: false`, no rows.

### Comparison recommendation (A58)

```
RecommendBody = {"mode": "replace"|"complete",
                 "count"?: int}                // 1-20: also sets photometry.auto_comparisons
Recommendation = {"added": int, "removed": [TargetStar],
                  "comparisons": [TargetStar],  // the set's comparisons afterwards
                  "targets": Targets}
```

- `replace` = Qt "Recommend from pilot" (`reselect_comparison_stars`,
  1324-1346; `imaging_page.py:2213-2224`): the comparisons whose source is
  `vsp` or `vsp_auto` are replaced by the pilot-qualified picks on the newest
  solved frame (`_auto_select_comparisons` with `_pilot_comparison_quality`:
  SNR ≥ `comparison_min_snr`, Δmag ≤ `comparison_max_delta_mag`, distance ≤
  `comparison_max_separation_arcmin`; score 0.5·SNR + 0.4·Δmag + 0.1·distance,
  `catalog/photometry.py:88-170`); manual comparisons stay. The new ensemble
  is chosen on a copy: when no VSP star passes the gate, nothing is removed
  or saved (`added: 0`, `removed: []`; Qt removed the VSP ensemble anyway,
  fixed for 0.5.0, `notes/release_0_5_0.md` S32 extended). OK "Photometry:
  replaced the VSP ensemble with {n} pilot-qualified star(s)." / WARN
  "Photometry: no pilot-qualified comparison found — the ensemble is
  unchanged." (after core's WARN that names the gate).
- `complete` = `propose_comparison_stars` (1304-1322): only adds missing
  calibrated VSP members up to `photometry.auto_comparisons`. OK
  "Photometry: selected {n} pilot-qualified comparison(s)." / INFO "Photometry:
  no comparison added ({m} in the ensemble)."
- `count` = Qt's "Automatically propose" spin
  (`_on_auto_comparison_count_changed`, `imaging_page.py:2196-2211`): the
  config key is written (a `config` event follows) before the action; with
  `replace` the Qt texts are OK "Photometry: selected {n} pilot-qualified
  comparison(s)." / INFO "Photometry: requested {count} comparison(s);
  {selected} pilot-qualified VSP star(s) selected."
- `409 not_solved` "Identify the field first: comparisons are chosen on the
  solved frame."; `409 no_target` "Choose a target star first."; `409
  no_comparison` "No VSP comparison stars are known for this field — refresh
  the catalogue." (Qt removed the VSP ensemble and added nothing in these
  cases: fixed for 0.5.0, `notes/release_0_5_0.md` S32); `409 busy` while a
  sequence owns the observation. The set is saved, the tracker reset, and
  `targets` and `field_layers` published as for A52.

### Wave 4 follow-ups

- **Undo of a new target** (A52, A53): the `POST /api/targets` answer gains
  `"auto_selected": [key]`, the comparisons chosen automatically with this
  call (empty otherwise). `DELETE /api/targets/{key}?also=<key>&also=<key>`
  (or comma-separated: a piece that does not start with `auid:` or `pos:`
  continues the previous key, whose `pos:<ra>,<dec>` holds a comma)
  removes the star and, in the same save, each listed star that is still a
  comparison of source `vsp_auto` (one the observer has not changed since);
  the answer carries `removed` and `"removed_also": [TargetStar]`. Undo of a
  new target = `DELETE` with `also` = its `auto_selected`. One OK line
  "Removed from target set: <name> (and <n> automatic comparison(s))".
- **`frame_metrics`** is replayed to a client that connects mid-run (the
  newest record, once, after the wave 4 snapshots).
- **File listing** (A11): with `kind=file` or `kind=any`, a `path` naming a
  file lists its folder with `"selected": <file name>` (a typed file path in
  the picker); a file whose suffix is not in `ext` is `400 invalid_argument`
  "<name> is not a <ext> file". Every listing carries `selected` (`null`
  otherwise). `kind=dir` still answers `400` "not a folder".

### Backpressure (wave 5)

`photometry_point` and `photometry_reset` are a stream (with `log`,
`frame_saved` and `conditions`): never compacted into one, the oldest dropped
after the log lines when a client lags; `seq` shows the gap. `photometry`,
`comparison_quality` and `frame_metrics` are snapshots (newest kept).

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
| `{"type": "filterwheel", …FilterWheelState}` | Wave 3. Every wheel change (move started, settled, failed, connected, disconnected); also in `status.filterwheel`. |
| `{"type": "focuser", …FocuserState}` | Wave 3. Every focuser change (polled position, move, queue, halt); also in `status.focuser`. |
| `{"type": "autofocus", …AutofocusState}` | Wave 3. Every sample, stage and end of an autofocus; also in `status.autofocus`. |
| `{"type": "observation", …Observation}` | Wave 3. Every change of the object name or target; also in `status.observation`. |
| `{"type": "target_suggestions", …}` | Wave 3. After each Stellarium GoTo: names near its coordinates (A20). |
| `{"type": "frame_metrics", …FrameMetrics}` | Wave 3. Once per metered frame (latest frame wins). |
| `{"type": "frame_saved", …FrameSaved}` | Wave 3. Every FITS a Take shot wrote; a stream with `seq`. |
| `{"type": "conditions", …ConditionsRow}` | Wave 3. One row per metered camera frame; a stream with `seq`. |
| `{"type": "field", …Field}` | Wave 4. Every change of the field: solve started, solved, failed, cancelled, invalidated, automatic mode, Centre availability. |
| `{"type": "catalog", …Catalog}` | Wave 4. Fetch started, ready, error, reset by an invalidation. |
| `{"type": "field_layers", …FieldLayers}` | Wave 4. Once per catalogue generation, then on a role or display-setting change, and once more when the candidates are measured. |
| `{"type": "field_transform", …FieldTransform}` | Wave 4. Every new frame of the solved field (the tracking fit); identity after a solve or an invalidation. |
| `{"type": "selection", …SelectionEvent}` | Wave 4. Every star selection, its identification outcome, each followed frame of a measured star, and its clearing. |
| `{"type": "targets", …Targets}` | Wave 4. Every change of the target set, of its object (name), of its positions (a new solution) and of the aperture. |
| `{"type": "photometry_point", …PhotometryPoint}` | Wave 5. One per kept live point (a stream with `seq`, shared with `photometry_reset`). |
| `{"type": "photometry_reset", …PhotometryReset}` | Wave 5. The live curves changed under the client (object change, role change, sequence start): re-read `GET /api/photometry/live`. |
| `{"type": "comparison_quality", …ComparisonQuality}` | Wave 5. The leave-one-out report after every measured frame (`report: null` after a reset). |
| `{"type": "photometry", …PhotometryStatus}` | Wave 5. Every change of the live photometry status (set, field, outcome of a measurement). |
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
letter case. It reads the first image HDU; the file is never modified.
Since wave 3 (A27, S4) the frame enters the live pipeline, so it must be
what a camera delivers:

- **Raw 16-bit counts only.** One 2-D image whose values are integers from
  0 to 65535, whatever the stored type (integer after BZERO/BSCALE, or
  float holding whole numbers). Float data that is not integral (Siril's
  32-bit [0, 1] output, a calibrated or stacked frame), NaN or infinite
  values, negative values, values above 65535 and `(3, H, W)` colour cubes
  are refused with `400 invalid_fits`, the reason in the message, and the
  current frame is left as it was. A `(1, H, W)` cube is a 2-D image.
- **Size.** Read from the header first: more than 16384 px on a side (the
  viewer's GPU texture limit) or more than 100 M samples is refused with
  `400 invalid_fits` before any pixel is loaded.
- **Time.** `timestamp` is `DATE-OBS` (else the file's modification time);
  the header's `date_obs` and the exposure midpoint `epoch_utc` are in the
  frame header (see [Opened files](#opened-files-a27)).

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
- **Filter wheel** (wave 3). The active profile's slots (Dark, IR, LP on a
  Seestar), starting on the first light slot (IR, the Qt form's default;
  wave 1 started on slot 0). A move takes
  `SimOptions.wheel_slot_s` (0.6 s) per slot, during which the position
  reads −1, as the Alpaca wheel does. With the wheel on **Dark** the camera
  receives no light: frames hold the pedestal, read noise, the hot pixels
  and their dark current only, so the Dark guard can be checked on the
  pixels. A frame exposed while the wheel turns is dimmed.
- **Focuser** (wave 3). MaxStep 10 000, starting at 5 000, moving at
  `SimOptions.focuser_speed_steps_s` (2 000 steps/s); Halt stops it where
  it is; a move is clamped to 0…MaxStep as `Focuser.move_to` does. Its
  temperature is a constant 12.5 °C. The optics keep its position across
  disconnects, as on a telescope.
- **Focus.** The star FWHM depends on the focuser position:
  FWHM(p) = 2.8 px · √(1 + ((p − best) / 450)²) with best focus at
  `SimOptions.focus_best` (5 300), flux conserved, so the HFD of
  `compute_hfd` traces a V with its minimum at best focus and the
  autofocus of A36 converges there (the start position, 5 000, is slightly
  out of focus: FWHM × 1.2). A frame exposed while the focuser moves takes
  the worse focus of its start and end.
- **Camera extras** (wave 3). Gain 0-600, exposure 0.001-3600 s, offset
  0-255 (default 10, it adds 2 ADU per unit to the pedestal of 1600 at
  offset 10), MaxBin 1, sensor temperature 21.0 °C, no driver ElectronsPerADU
  (FITS `EGAIN` comes from the sensor reference) and no readout mode.
- **Mount extras** (wave 3). Alignment `eq_gem`; `MoveAxis` jogs at up to
  5 °/s per axis (primary = RA, positive east; secondary = Dec, positive
  north); tracking rates sidereal, lunar, solar and king (read back, not
  modelled); no clock error.

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
| A19-A20 | Wave 3: `target_suggestions` after a Stellarium GoTo, `GET /api/catalog/nearby`, `suggestions` in the Stellarium record |
| A21-A24 | Wave 3: `CameraState` owner / settings / current / limits / offset / binning / temperature, `PUT /api/camera/settings`, Take shot with FITS save (`save: true`, every 0.5.0 science fix), `frame_saved`, `GET /api/camera/saved` |
| A25-A27 | Wave 3: frame header fields (`bayer`, `origin`, frame settings, file `path` / `date_obs` / `epoch_utc`), `frame_metrics` on the full frame, Open FITS raw-only and dated from its header |
| A28 | Wave 3: filter wheel record and event, `GET /api/filterwheel`, `POST /api/filterwheel/select` |
| A29-A31 | Wave 3: `MountState` alignment / tracking rate / goto_blocked / jog, `POST /api/mount/jog` with a server dead-man, `/jog/stop`, `/tracking-rate`; `?client=` and `jog_stop` on `/ws/events` |
| A34-A36 | Wave 3: focuser record and polling, `POST /api/focuser/move` / `step` / `halt` (D9 queue), autofocus `start` / `stop` with V-curve samples and fit |
| A37 | Wave 3: `conditions` rows, `GET /api/session/conditions` |
| A38-A41 | Wave 3: observation identity (`GET` / `PUT /api/observation`, `POST` / `DELETE /api/observation/target`), `GET /api/catalog/resolve`, `GET /api/catalog/suggest` |
| A43-A45 | Wave 4: `GET /api/field`, `POST` / `DELETE /api/field/solve` (job `field_solve`, ASTAP killed on cancel), `PUT /api/field/auto`, `field` event; positions in frame px |
| A46-A48 | Wave 4: `GET /api/field/catalog`, `POST /api/field/catalog/refetch`, `GET /api/field/layers`, `GET /api/field/transform`; `catalog`, `field_layers` (with the FieldBand `candidates`: `b_minus_v`, `neighbours_in_aperture`), `field_transform` events |
| A49 | Wave 4: `GET` / `POST` / `DELETE /api/field/select`, `selection` event (point identification superseded by a newer click) |
| A51-A53 | Wave 4: `GET` / `POST /api/targets`, `DELETE /api/targets/{key}` (`removed` for Undo), `targets` event; `targets/<object>.json` in the Qt format |
| A32-A33 | Wave 4: `POST /api/mount/center` (tracked solution, S30), `POST /api/mount/sync` `{"source": "solution"}` (Q-O3); `MountState.center_available` |
| A50 | Wave 5: `GET /api/field/variables` |
| A54-A57 | Wave 5: `GET /api/photometry/live`; `photometry_point` and `photometry_reset` (a stream), `comparison_quality` and `photometry` (snapshots); BJD_TDB per point; leave-one-out status per comparison |
| A58 | Wave 5: `POST /api/photometry/comparisons/recommend` (`replace` / `complete`, `count`) |
| — | Wave 5 follow-ups of wave 4: `auto_selected` in the `POST /api/targets` answer and `DELETE /api/targets/{key}?also=` (Undo of a new target); `frame_metrics` replayed to a new client; `GET /api/fs/list` lists a typed file's folder with `selected` |
