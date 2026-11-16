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
                                 [--connect-timeout S] [--sim-replay DIR] [--desktop]
                                 [--exit-on-stdin-eof] [--self-check]
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
| `--sim-replay` | (Wave 6a) With `--simulator`: the camera plays the FITS frames of DIR. See [Simulator replay source](#simulator-replay-source). |
| `--desktop` | (Wave 8) Started by the desktop shell: AppInfo `desktop: true`, `POST /api/fs/reveal` allowed. See [Desktop app](#desktop-app-wave-8-shutdown-reveal-the-shells-stdin). |
| `--exit-on-stdin-eof` | (Wave 8) Shut down gracefully (SIGTERM) when stdin reaches end of file: the shell's pipe closed, whatever ended the shell. |
| `--self-check` | (Wave 8) Import the app and every module the server loads by file path (`argos/core/session/review.py`), print `loaded <path>` lines and `ARGOS <version> self-check: ok`, exit 0; no socket, no configuration read. The release workflow runs it on the frozen sidecar (`packaging/smoke_sidecar.py`): a freeze missing such a file fails there, not when Review opens a session. |

Once the socket is bound and listening, stdout carries exactly two lines, in
this order, for a supervising process such as the desktop app's shell:

```
ARGOS_PORT=8742
ARGOS_TOKEN=<token>
```

The desktop app (wave 8, `web/src-tauri/src/sidecar.rs`) runs the frozen
one-dir server (`argos-server`, `packaging/argos_server.spec`) as
`argos-server --host 127.0.0.1 --port 0 --desktop --exit-on-stdin-eof`, its
stdin a pipe it holds open, reads the two lines within 60 s, and opens the UI
with the address and the token. It spawns the server first thing, before its
own window exists. A dev build (`org.argos.argos.dev`) may add arguments
(`ARGOS_SIDECAR_ARGS`) or run another executable (`ARGOS_SIDECAR`); the extra
arguments come before the shell's own, which therefore win (argparse keeps
the last value: no `--host` can expose a desktop server). A release build
ignores both variables.

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
| 409 | `run_active` | (wave 6a, sequences) a mount motion during a run (the interlock: GoTo, Centre, Sync, Park, Unpark, tracking off, tracking rate, jog) or a photometry-geometry config change during a run; `details: {state, run_id, …}`. |
| 409 | `preflight_blocked` | (wave 6a) `POST /api/sequence/start` refused by a preflight block (`details.checks`). |
| 409 | `not_running` | (wave 6a) `POST /api/sequence/pause` or `/resume` with no run, or while it waits for its start time. |
| 500 | `internal_error` | Any unexpected failure; the traceback is in the server log. The answer keeps the CORS headers, so the browser can read it. |
| 502 | `connection_failed` | The device could not be reached or refused to connect. Its device state becomes `error` with the full text. |
| 502 | `device_error` | A connected device refused a command or stopped answering. |
| 404 | `not_found` | (wave 3) `GET /api/catalog/resolve` for a designation the catalogues do not know (the resolver's text). |
| 502 | `lookup_failed` | (wave 3) `GET /api/catalog/resolve` or `/api/catalog/nearby` with no network answer (the resolver's text). (Wave 6a) `GET /api/exoplanets/lookup` with no answer from the NASA Exoplanet Archive. |
| 409 | `site_missing` | (wave 6a, plan) `GET /api/visibility`, `POST /api/transit/predict` or `/plan` with no observing site set (X2: never 0/0). |
| 409 | `run_active` | (wave 6a, plan) `PUT /api/sequence/plan`, `POST /api/sequence/plan/import` or `POST /api/transit/plan` while a sequence runs (Q-P9: the plan is locked). |
| 409 | `file_exists` | (wave 6a, plan) `PUT /api/sequence/presets/{name}` on an existing preset without `?overwrite=true`; `POST /api/sequence/plan/export` on an existing file without `"overwrite": true`. |
| 404 | `not_found` | (wave 6a, plan) a missing preset or import file; `GET /api/exoplanets/lookup` for a planet the archive does not know. |
| 422 | `ephemeris_unusable` | (wave 6a, plan) the archive's planet has no usable transit ephemeris (no BJD_TDB epoch, a missing or invalid column); the core's text. |
| 422 | `no_observable_transit` | (wave 6a, plan) `POST /api/transit/predict` or `/plan`: no transit is observable (night, minimum altitude) in the next 366 days. |

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
           "docs_url": "https://perretjules.com/argos/",
           "desktop": bool}              // wave 8: started by the desktop shell (--desktop)
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
                  "quality": {"stable": int, "total": int}|null,  // (W7 fix) its verdict:
                                                        //   comparisons "stable" of those vetted
                  "issues": [string]}
```

(W7 fix) `issues` also carries the open's cheap readiness lines, so R0
agrees with R1's badge: the header site check (X3) on the first light
frame's header only ("The site in Settings was not where the telescope
was…"), "<n> frame(s) flagged by the flight recorder: no detection of the
target, or a zero point more than 1 mag off." and "<n> frame(s) measured
while fewer than 3 comparison or check stars reached SNR 10 (S56: lock not
verified)." (the counts of A69's `low_snr`/`zp_outlier` and `few_anchors`
rules on the run's `diagnostics/*_live_diagnostics.jsonl`).

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
  precession, nutation or refraction). With coordinates of date it agrees with
  astropy (FK5 of date, no refraction) within 0.01°; fed J2000 coordinates it
  is off by the precession since 2000, up to about 0.4° in 2026
  (`tests/server/test_site_check.py` sweeps 120 random directions, sites and
  2026 dates with bounds of 0.05° and 0.5°). The mount's RA/Dec reach it as
  J2000 (`argos.core.alpaca.telescope` converts from the driver's
  `EquatorialSystem`). Release S51 (wave 6b) precesses J2000 to the date
  first (IAU 1976): J2000 within 0.05° once release/0.5.0 is merged (the
  sweep test follows the core). Either way far inside the 5° tolerance. It
  never downloads anything.
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
   reference; with the release core, S73, the profile's measured e-/ADU first),
   `READOUTM` read from the camera at save time, `SOFTWARE`
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
- **Wrong solutions refused** (release S50, wave 6b; `_on_worker_solved`): a
  camera frame's solution whose plate scale (its CD matrix, ″ per green px)
  is more than 1 % from the **first good solve of the session** is refused
  and the last good solution kept, as a failure: `state: "failed"`,
  `last_attempt.outcome: "failed"`, the job `failed` / `not_solved`, WARN
  "Solve: solution refused — plate scale 3.547″/px is 3.4 % below this
  session's 3.671″/px (a wrong match); the previous solution is kept" (per
  full-resolution px, as the summary). The reference is the first accepted
  solve of a camera frame for the active `hardware.profile` and frame
  geometry; another profile or geometry, or a camera disconnect, starts a new
  one (the profile's
  nominal scale is not used: it is 1.8 % above every measured solve). An
  opened file (another instrument, another night) is never gated and never
  sets the reference. On the owner's runs: 270 solves, the good ones within
  0.3 % of their night's first, one refused (XX Cyg 2026-09-07 `045156Z`
  frame 1, its second, 7.093″ per green px against 7.341-7.343). The S48 lock
  check is not a guard against a wrong solution (a new solution rebuilds the
  tracker from the stars it shows): S54 below is.
  **The reference moves** (release S55): when the last 3 camera solves of that
  reference (refused ones included) agree with each other within 0.3 % (max /
  min − 1), the reference becomes their mean, so a wrong first solve no longer
  refuses every later good one: the third agreeing solve is accepted, WARN
  "Solve: the plate-scale reference moves from 3.546″/px to 3.671″/px — 3 solves
  agree; the earlier reference was a wrong match" (only when it moves by more
  than the 1 % tolerance; within it the re-centring is silent). On the owner's
  270 solves it changes no decision.
- **Solutions the photometry's anchors do not confirm are refused** (release
  S54; `AcquisitionEngine._solution_refusal`): a camera frame's solution on
  which fewer than ceil(k/2) of the photometry tracker's k anchor stars show a
  star (aperture SNR ≥ 5) where it places them, on the frame it solved, is
  refused as above: WARN "Solve: solution refused — only 1 of the 6 anchor
  stars show a star where it places them (3 needed: a wrong match, or the field
  is not there); the previous solution is kept", activity "Field
  identification refused (anchor stars)". The tracker and its points stay on
  the previous solution. Only a tracker built for the field's current
  solution (its `generation`) counts: none on the first solve, after an
  invalidation (which drops the photometry's tracker, as Qt's
  `invalidate_astrometry`), an opened file or a set change. XX Cyg 2026-09-07
  `045156Z` frame 1: 1 anchor of 6 seen (S50 refuses it first, by its scale).
  **A re-pointing the mount did not report** (S54 as amended, owner decision
  2026-11-15): 3 consecutive solutions refused by this check (failed solves and
  S50 refusals between them neither count nor break the count) that agree with
  each other within 20 green px (the largest distance between where they put
  the newest one's frame centre) are a field that moved without a slew
  (camera only, another app): the third is accepted, WARN "Solve: 3 consecutive
  solutions agree within 8.0 px on a field where the anchor stars are not (0 of
  6 seen) — accepted as a re-pointing the mount did not report". 20 px is twice
  the largest span of 3 consecutive good solves on the owner's runs (10.4 px,
  RR Lyr 2026-09-25: 4.3 px of drift per sub; the subs across its two mount
  jumps span 22.7 and 145 px); a solution passing the check, an accepted one,
  an invalidation or a set change restarts the count.
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
  `FieldService.resolve_due(frame_seq, now=)` (release S48, wave 6b): the
  photometry lost the field (`field_lost`, `lock_lost`) or its lock is
  unverified (S56), or a run's sub of 1 or 2 anchors was verified through the
  previous sub's solution (S56, second set of 2026-11-15): the next frame is due
  whatever the cadence; with `now` (a sequence sub) the frame in hand is solved
  at once when it is still the newest and no solve runs.
  `FieldService.reference_with_frame()` gives the reference solution, its
  generation, and the seq and raw pixels of the frame it was solved on, read
  under one lock (None without a solution): a sequence's sub is measured with
  them (S56: its freshness, and the frame its tracker's anchors are chosen on;
  read apart, a solve landing in between paired the old solution with no frame).
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
  drawn on another field; release S59 keeps that solution in Qt until the
  camera's own solve and never checks a camera solution against the file's
  anchors, which cannot happen here). The target set is kept. A solve running at
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
    on the solved frame; each centroid is the core's converged one (S69,
    `_converged_centroid_measurement`: re-centred on itself until it moves
    less than 0.01 px, then in a 4 px window). Two passes kept 0.31° of lag
    on XX Cyg 2026-09-07 `040723Z` (0.7° of field rotation per sub), 0.07°
    now (GUARD: two passes with a core before S69). The anchors follow S69's
    neighbour rule (a candidate beside a brighter star of the set is none).
  - With three or more anchors an update needs two anchors whose
    separations agree with the reference within 1.5 green px; a lone window
    that slid onto another star or onto sky is no lock. The core tracker has
    the same rule since S80 (`tracking.consistent_pairs`, used here when
    present): every inconsistent anchor leaves the fit, not one at most.
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
           "revision": int,
           "crowding": [string]}          // S79: one line per crowded comparison or check star
TargetStar = {"key", "role": "target"|"comparison"|"check", "name", "display_name",
              "ra_deg", "dec_deg", "ra_hours", "auid", "source", "mags", "chart_id", "note",
              "x": float|null, "y": float|null,   // reference frame px when solved and in frame
              "proper_motion": {"pm_ra_mas_yr": float, "pm_dec_mas_yr": float,   // S77
                                "epoch": float, "source": string}|null,
              "crowded": {"neighbour": string, "separation_arcsec": float,      // S79
                          "delta_mag": float|null, "band": string|null,
                          "radius_arcsec": float, "text": string}|null}
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
- **Proper motion** (S77, GUARD: the release core): a field catalogue answer's
  Gaia DR3 sources give the set's VSX/VSP stars with an AUID their proper
  motion and Gaia's 2016.0 position (`TargetService.backfill_proper_motions`,
  as Qt's `_on_catalog`; the object's set and the running run's
  `targets.json` are saved, INFO "Catalog: proper motion from Gaia DR3 for N
  star(s) of the set …"). `ra_deg`/`dec_deg` stay the catalogue's J2000.0
  position; `x`, `y` are where the star is now, and every path that places an
  aperture (live, sequence, re-run) measures the set at the frame's date
  (`TargetSet.at_jd`). A Gaia source is a star's when its J2000.0 or 2016.0
  position lies within 1" of the catalogue one, or for a star with a V, when
  it is the one source within 6" whose G is within 1 mag of V.
- **Crowding** (S79, GUARD): a comparison or check star with a brighter star
  of the set (by its catalogue V, else a band both hold), or one of unknown
  brightness (a variable), within 2 aperture radii of the series FWHM at the
  profile's green-plane scale carries `crowded`, and `crowding` lists the
  lines (the Field band shows them under its note line; Qt's Comparison stars
  tab). The server logs the WARN "Comparison crowded — …" once per newly
  crowded star (topic `photometry`), as Qt does. The separations behind the
  Gaia match and the crowding are taken across RA 0h (S77/S79 amended).

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
(`measure_saved_frame`). A run's sub is never measured again by this path,
even when its solve ends after the run did (wave 6b integration: it gave a
second, one-point curve under no filter).

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
  object change (`_build_live_tracker`, 1569-1582). After a set change
  (release S52, wave 6b science review) it is built on the solution **as
  tracked so far** (the solve with the dropped tracker's shift and rotation,
  frozen at the change), never on the raw solve the field has drifted from,
  until the next solution; in a run the set change also makes the next sub's
  solve due (`FieldService.resolve_due`). Anchors =
  `select_tracking_anchors` over the comparisons and checks (SNR ≥ 10,
  unsaturated, not suspect, at most 6), else any star of the set **seen where
  the solution places it** (SNR ≥ 5), chosen **on the frame the solution was
  solved on** (`MeasureRequest.solved_raw`: the field's solved frame for a live
  point, `FieldService.reference_with_frame()` for a sequence's sub), through that
  solution, where it is exact (release S56 as amended, owner decision 2026-11-15,
  second set; the measured frame only when the solved one is unknown or of
  another geometry); the tracker is placed through the solution or its S52
  freeze as before. Chosen on the measured sub through an earlier sub's
  solution, after a jump only the stars that happened to show at the stale
  positions qualified, and the lock check verified the very star that moved the
  apertures (real RR Lyr subs moved 500 px: 1 anchor, the target 496 px off);
  on the solved frame all 6 qualify and 1 shows a star on the moved sub: the
  lock is lost. A tracker built with none is built again on the next frame.
  Search radius `max(8, 2 × aperture(None))` green px; updated on every measured frame with rotation unless the mount reports
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
- **Lock check** (release S48, wave 6b): after the tracker update, at least
  ceil(n/2) of the tracker's n anchor stars must show a star (aperture SNR ≥ 5)
  where the tracked solution puts them (`anchors_seen`, the batch's S43 rule).
  Otherwise the frame gets **no point**: WARN "Photometry skipped: fewer than
  half the anchor stars show a star where the solution places them — the
  field moved since the solve, or clouds. Re-solving.", status
  `skipped` / `lock_lost` (message "Skipped frame #<seq>: …"), a
  `frame_skipped` event (`reason: "lock_lost"`), and the next solve is **due
  at once** (`FieldService.resolve_due`): in a run the sub in hand is solved
  now (its solution serves the next sub); outside a run the next frame is due
  (a live point follows each solve: solving the same frame again would repeat
  it). S35's `field_lost` makes the solve due the same way. It catches a jump
  where one window centroided a neighbour (S35 sees an anchor and does not
  fire), and clouds that dim most anchors below SNR 5; not a wrong plate
  solution, whose rebuilt tracker anchors on the stars it shows. The status record's
  `lock` gives the last check (`PhotometryStatus` below); the attention rule
  `tracker_lost` counts both reasons.
- **Unverified lock** (release S56): with 1 or 2 anchors, ceil(n/2) is met by the
  very anchor that moved the solution, so the check verifies nothing. Such a
  frame is **verified all the same** (S56 as amended, owner decision 2026-11-15)
  when it is measured through a solution of this sub or the previous one (the
  solved frame's seq is the measured one's or one less) and the tracker moved no
  aperture of the set **2 green px or more** from where that solution puts it
  (the largest distance, over the set's stars, between their positions through
  the raw and the tracked solution: the tracker's own outlier floor; between two
  subs the owner's fields drift 1-5 px, a neighbour locked after a jump or a
  stale rebuild moves them 22-36 px); no re-solve is made due then. Otherwise
  the frame keeps its points, each flagged **`suspect`** (the point's existing
  flag: the CSV's `suspect` column, `photometry_point.point.suspect`, drawn
  hollow as the other suspect points, left out of an AAVSO export), and the next
  solve is due at once as after `lock_lost` (in a run the sub in hand). WARN
  "Photometry: only 2 anchor stars steer the apertures — the lock cannot be
  verified; points are flagged suspect while fewer than 3 anchor stars steer
  the apertures (except within 10 px of a solution of this sub or the previous
  one). Re-solving." once per episode (a verified frame, an invalidation or a
  set change ends it; a solve that lands does not), a `lock_unverified` event
  (`anchors`) per flagged frame in the flight recorder, `lock.verified: false`.
  In a run (a sequence's sub) a frame of 1 or 2 anchors verified through the
  **previous** sub's solution makes its own solve due at once
  (`FieldService.resolve_due(seq, now=True)`, S56 as amended, owner decision
  2026-11-15, second set): the next sub is then measured through a solution of
  the previous one, never two subs from it (with one solve per run XX Cyg
  2026-08-29 `050148Z` alternated verified and flagged subs: 12 of 22 flagged,
  now 2). Outside a run a live point follows each solve: nothing more is due.
  This needs the sub's solve to land before the next sub is measured: with solves
  slower than one sub interval such subs stay flagged and every other sub is
  solved (no loop or stall: at most one solve starts per sub).
  The 2 px threshold stays until a field drifting more is observed.
- **Tracker on an alt-az run** (release S69, GUARD: active once the release
  core is merged, `photometry.s69_core()`). The tracker's centroids are
  re-centred on themselves until they converge (core `tracking.py`): one
  centroid per window centred on the prediction lagged a field turning 0.7°
  per sub by about 1° (XX Cyg 2026-09-07). (a) A solve is due when the tracked
  rotation since the solution (`TrackedWCS.rotation_deg`, a set-change rebase
  included) exceeds **2°**, as after `lock_lost` (in a run the sub in hand);
  while none lands, again only after 2° more (`rotation_resolve_due`), so a
  failing solver never loops; a `rotation_resolve_due` event (`rotation_deg`)
  in the flight recorder. (b) Each frame, every comparison and check star seen
  at SNR >= 5 has its centroid measured within its aperture
  (`tracking.centring_offsets`); one more than **1 green px** from its aperture
  centre is left out of the frame's ensemble (`measure_frame(exclude=…)`), its
  own point is flagged `suspect`, its star record carries `off_centre: true`
  (every tested star its `centroid_offset_px`), an `off_centre` event
  (`stars`) is recorded and a WARN "Photometry: N comparison/check stars more
  than 1 px from the aperture centre — left out of the frame's ensemble, their
  points flagged suspect." is logged once per episode (a frame with none ends
  it). The anchors counted by the unverified-lock rule above are those centred:
  off-centre anchors that leave fewer than 3 make the frame unverified unless
  it is fresh.
- **One curve per (star, filter)** (release S49, wave 6b): the filter of the
  measured frame is a sub's read-back `FILTER`, an opened file's `FILTER` card
  (none: `clear`), a live frame's wheel slot when the wheel reports one
  settled, else the frame's Camera form filter. Its **token** is the frame
  file name's (`fits_writer.filter_token`: the abbreviation, `[A-Za-z0-9_-]`,
  lower case, `clear` for none: `IR` → `ir`, `LP` → `lp`). Each (star, token)
  has its own curve, floor, CSV and series; the leave-one-out report vets the
  comparisons of the measured frame's filter only.
- **Calibration** (`measure_targets`, `session.py:47-160`): targets and
  checks against the full ensemble, each comparison leave-one-out;
  `egain` from `camera.egain_table`, else the driver, else the sensor model;
  an opened frame keeps its own: the table at its `GAIN`, else its `EGAIN`
  (`frame_egain`, release S41), the chain above only when it records neither.
  A Take shot's header `EGAIN` follows the same chain (release S42).
  Once release/0.5.0's core is merged (S73, GUARD: `hardware.egain`, imported
  when present): the telescope profile's photon-transfer e-/ADU comes after the
  table and before the driver (S30 Pro: 0.228 ± 0.005 at gain 80, scaled by
  0.1 dB per step over gains 0-251; elsewhere the driver, then the reference,
  logged unverified); an opened or re-run frame of the camera its `TELESCOP`
  names takes it at its `GAIN` instead of its `EGAIN` (the 0.8 or 1.723 the
  0.4.x frames carry), an `EGAIN` the table wrote excepted (the opened frame's
  `gain_header` is a `fits.Header` keeping that comment). A scaled gain carries
  the read noise measured at gain 80 (2.6 e-), and every gain other than 80 and
  100 is logged once "e-/ADU at gain N scaled, not measured" (S73 amended). The
  e-/ADU is the frame's own gain's (S83): a sequence sub's step gain, a camera
  frame's (`MeasureRequest.gain`, `Frame.gain`), the Camera form's only for a
  frame that records none (the S54 re-pointing check and the pilot's comparison
  quality). The value is an
  `Egain` (a float with `source` and, measured, `read_noise_e`); the flight
  recorder's `frame` record carries `egain` and `egain_source` (Qt and server).
  New frames write it to `EGAIN` ("S30 Pro PTC", "S30 Pro PTC scaled") and, at
  a measured gain, to `RDNOISE`. `OpenedFrame.gain_header` keeps `TELESCOP`,
  `EXPTIME`, `AIRMASS` and `SITEELEV` for it and for S74.
  Once release/0.5.0's core is merged (S71, S72): the zero point is the
  comparisons' mean weighted by `1/(inst_mag_err² + 0.01²)`, clipped at 2.5
  normalised residuals about the weighted median, and its error
  `max(sqrt(1/Σw), weighted rms/√n)` is in `formal_mag_err`; when the
  comparison holding more than half the weight is contradicted by the
  weighted mean of two others or more (beyond 2.5 combined σ), the point is
  flagged suspect and the `ensemble` record's note says so (release
  `DiffResult.suspect`, read with `getattr`: GUARD). S72's noise model
  (the (G1+G2)/2 plane's: `2 × egain` e-/ADU, read noise `rn/√2` ADU, the
  telescope profile's black level `black_level_adu` subtracted from the sky
  before its Poisson term; the read noise measured with the profile's e-/ADU
  when it gave it, else `photometry.read_noise_e`) is the default once the
  release core is merged (`photometry.noise_model`: `green_plane`; `pixel`, the
  0.4.x formula, for comparison only; the Settings key's default is the core's
  `NOISE_MODEL_DEFAULT`, `pixel` on a core without it: GUARD). With it: S75,
  the sky estimate's error, `n_ap (1 + (π/2) n_ap / n_sky)` sky variances (the
  annulus median); S74, each star's scintillation, Young's formula with Osborn's
  `C_Y = 1.5` from the profile's aperture, the frame's exposure and airmass and
  the site's height (`PhotometryParams.with_frame`: an opened or re-run frame's
  `EXPTIME`, `AIRMASS`, `SITEELEV`; live, the sub's exposure, the mount's
  airmass, the Settings site; sea level when none), added in quadrature to each
  star's `inst_mag_err` (hence the zero point's weights and every target's
  error), never to the SNR the gates read. The server calls the same core
  functions (`MeasureRequest.scintillation`, `exposure_s`); `field.py`'s
  comparison-quality aperture and `targets.py`'s pilot-quality aperture
  (`_pilot_comparison_quality`) pass `black_adu` and `plane_pixels` (GUARD:
  `_APERTURE_TAKES_BLACK`).
- **Errors and flags**: `formal_mag_err`; `mag_err` = `hypot(max(0,
  formal), σ_syst)` once the curve has ten valid points (or with
  `photometry.systematic_floor_mag`), recomputed for every point of the
  curve after each new point (`_apply_systematic_floor`, 1767-1795; the
  client recomputes the earlier bars the same way from `sigma_syst`);
  `saturated` (aperture peak ≥ `camera.linearity_max_adu`), `suspect`
  (hot pixel / cosmic, `aperture.py:109-136`; or the frame's lock rests on fewer
  than 3 anchors, release S56), never used to drop a point.
- **Time and airmass** (X2): `jd_utc` of the midpoint; with a site set
  (`observing_site`: a name, or coordinates other than 0/0) `bjd_tdb` from
  astropy for the star's own RA / Dec and the site, and the star's own
  airmass at `jd_utc` (Pickering; `airmass_at`, its J2000 position precessed
  to the date once release S51 is merged: +0.0006 at 68°, up to +0.029 at
  12° on the owner's runs); without a site no `bjd_tdb` and the
  mount's airmass for a camera frame (`null` without a mount, and `null` for an
  opened file, another night: Qt used the mount's current altitude, fixed for
  0.5.0, `notes/release_0_5_0.md` S34). S78 (GUARD: the release core's
  `SiteFit`): each star's airmass is computed for the site fitted to the mount's
  polls of the measured frames (3 over 10 minutes, rms under 0.1°; a slewing
  mount's poll and one that repeats the last, a lost mount's, are not added);
  before a fit, for the Settings site only when it reproduces the mount's
  pointing within 0.1°, else every star takes the mount's airmass (S78 amended).
- **Files**: each curve is rewritten after every point by
  `LightCurve.to_csv` (15 columns, `lightcurve.py:14-30`; written beside the
  file and renamed over it, so a reader never sees it half written: release
  S38) at
  `<sessions_path>/targets/<object>_<YYYYMMDDTHHMMSSZ>_<filter>_<auid or name>.csv`
  outside a run, one file per curve named after its start (`-2`, `-3`… on the
  time for two in one second), so measuring an object again never overwrites
  an earlier curve (`_photometry_csv_path`, release S40; inside a run, wave 6:
  `<run>/photometry/<role>_<object>_<filter>_<tag>.csv`; `<filter>` the token,
  release S49: before 6b the name had no filter, the contents are unchanged);
  with `diagnostics.enabled`
  the flight recorder `<sessions_path>/targets/<object>_live_diagnostics.jsonl`
  (`star`, `ensemble`, `frame` records). The leave-one-out report is written
  to `<run>/photometry_quality.json` inside a run only (S17); with several
  filters, that file vets the run's first filter and
  `<run>/photometry_quality_<filter>.json` each other one (S49). Each file names
  the filter it vets in an additive last key `"filter"` (the token, release S57;
  readers ignore unknown keys: Qt Review, the session list).

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
Curve = {"key": string,                  // "<AUID, else display name>@<filter token>" (S49)
         "star_key": string|null,        // TargetStar key in the set (null: no longer in it)
         "filter": string,               // the filter token ("ir", "v", "clear"): one curve
                                         //   per (star, filter); say it when several
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
                   "filter": string,             // the curve's filter token (S49)
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
                     "frame_seq": int|null,
                     "filter": string|null,       // the filter whose comparisons it vets (S49)
                     "report": Report|null}
Report = {… comparison_quality_report (quality.py:22-98) as written to
          photometry_quality.json (the file adds its "filter", S57; here it is
          the record's): schema, generated_utc, selection_status
          ("insufficient_data"|"not_ready"|"live_preview_consistent"),
          scientific_note, criteria {min_points, max_scatter_mag,
          max_formal_error_mag}, comparison_stars [Entry] …}
Entry = {"name", "auid", "n_valid", "scatter_mag", "median_formal_error_mag",
         "status": "insufficient_data"|"noisy"|"unstable"|"stable",
         // added on the wire:
         "key": string,                          // its curve key (of the report's filter)
         "star_key": string,                     // its TargetStar key
         "last": {"mag", "mag_err", "comps_used", "jd_utc"}|null}
                                                 // its newest leave-one-out point
PhotometryStatus = {"type": "photometry",
                    "state": "off"|"waiting"|"measured"|"skipped",
                    "reason": "no_target"|"not_solved"|"no_epoch"|"no_comparison"
                              |"no_point"|"field_lost"|"lock_lost"|null,
                    "message": string|null,
                    "frames": int, "points": int,        // since the last reset
                    "last": {"frame_seq", "t", "jd_utc", "bjd_tdb"|null,
                             "points": int,               // kept on that frame
                             "target": {"key", "mag", "mag_err", "bjd_tdb"}|null,
                             "filter": string,            // its filter token (S49)
                             "aperture_px": float, "fwhm_px": float,   // green px
                             "anchors": int|null,         // tracker anchors used
                             "tracking": {"rot_deg", "dx", "dy",       // green px
                                          "residual_px"}|null}|null,
                    "lock": {"frame_seq": int,           // S48: the last lock check
                             "anchors": int,             //   the tracker's anchor stars
                             "seen": int,                //   showing a star (SNR ≥ 5)
                             "needed": int,              //   ceil(anchors / 2)
                             "held": bool,               //   seen ≥ needed
                             "verified": bool}|null,     //   S56: held, and 3 anchors or more or within 10 px of a fresh solution
                                                         //   null: tracking off, S35, reset
                    "revision": int}
```

The leave-one-out report is computed after every measured frame, in live
preview too (S17, Q-R13), with `photometry.comparison_validation_*`; a reset
sends `report: null`. Per comparison, `status` is its leave-one-out status
(PROPOSAL §7). `photometry.state`: `off` (no target in the set), `waiting`
(a target, no solution yet, or the set changed since the last measurement:
the next solution measures), `measured` (the last attempt kept points),
`skipped` (the last attempt kept none: `no_epoch`, `field_lost`,
`lock_lost` (S48), `no_comparison` when the set has no comparison, else
`no_point`). A curve's `star_key` is `null` once its star left the set.

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

## API 2 routes, wave 6a (Plan)

Wave 6a, plan half (`web/spec/README.md` §4.3 rows A42, A59-A61, A65, A66;
`web/spec/06-plan-sequencer.md` §1.14, §2.5): the sequence plan draft, its
presets and files, the target's visibility and the transit planner, in
`argos/server/sequence_plan.py` and `argos/server/planning.py`. The model,
totals, estimate, transit window and transit plan are the core's
(`sequencer.py`, `transit.py`, `airmass.py`), called as Qt calls them, so
the numbers are Qt's by construction. Run control and the `sequence` event
(A62-A64) are described under the sequences part of wave 6a.

| Method | Path | Body | Returns | Row |
|---|---|---|---|---|
| GET | `/api/sequence/plan` | — | PlanRecord | A59 |
| PUT | `/api/sequence/plan` | Plan | PlanRecord | A59 |
| POST | `/api/sequence/plan/import` | `{"path"}` or `{"preset"}` | PlanRecord | A61 |
| POST | `/api/sequence/plan/export` | `{"path", "overwrite"?: false}` | `{"path"}` | A61 |
| GET | `/api/sequence/presets` | — | PresetList | A60 |
| GET | `/api/sequence/presets/{name}` | — | Preset | A60 |
| PUT | `/api/sequence/presets/{name}?overwrite=true` | Plan, or none (the draft) | PresetList | A60 |
| DELETE | `/api/sequence/presets/{name}` | — | PresetList | A60 |
| GET | `/api/visibility?ra_hours=&dec_deg=&night=YYYY-MM-DD&step_min=10&min_alt_deg=` | — | Visibility | A65 |
| GET | `/api/exoplanets/lookup?q=` | — | Exoplanet | A42 |
| GET | `/api/exoplanets/suggest?q=&limit=8` | — | `{"query", "names": [string]}` | A42 |
| POST | `/api/transit/predict` | TransitBody | TransitPrediction | A66 |
| POST | `/api/transit/plan` | TransitPlanBody | `{"plan": PlanRecord, "prediction": TransitPrediction}` | A66 |

New WebSocket snapshot: `{"type": "sequence_plan", …PlanRecord}` after every
change of the draft (any client, a transit plan, an import, the observation
object followed, a run starting or ending). New error codes:
`ephemeris_unusable`, `no_observable_transit`; `site_missing` and
`run_active` are now sent (see Errors).

### Plan (A59)

```
Plan = {"schema": 2,                      // optional on PUT; any other value is 400
        "object_name": string,            // FITS OBJECT, run folder, target set
        "repeat": int,                    // whole step list replayed
        "autofocus_every_n": int,         // 0 = off
        "autofocus_on_filter_change": bool,
        "on_complete": "Nothing"|"Stop tracking"|"Park mount",
        "base_dir": string|null,          // run folder root; null = sessions_path
        "metadata": {string: string|number|bool|null},   // planning hand-off (S5)
        "start_at_utc": string|null,      // web only: scheduled start (Q-P2)
        "steps": [Step]}
Step = {"enabled": bool, "frame_type": "Light"|"Dark"|"Flat"|"Bias",
        "filter_name": string, "exposure_s": number, "gain": int, "count": int,
        "interval_s": number, "cadence_s": number|null, "dither_every": int}
PlanRecord = {"plan": Plan,
              "derived": {"total_frames": int,       // sequencer.total_frames
                          "estimate_s": number,      // sequencer.estimated_duration_s
                          "per_step_s": [number],    // one pass, 0 for a step that does not run
                          "start_utc": string,       // start_at_utc when in the future, else now
                          "end_utc": string},        // start_utc + estimate_s
              "issues": [Issue],
              "ready": bool,                         // no issue of level "error"
              "locked": bool, "locked_reason": string|null,   // a run is active (Q-P9)
              "notes": [string],                     // what the last change did (see below)
              "filters": {"names": [string], "source": "wheel"|"profile"|"default"},
              "limits": {"exposure_s": [min, max], "gain": [min, max],
                         "source": "camera"|"last_camera"|"default"},
              "path": string|null,                   // sequence_draft.json, null in memory
              "revision": int}
Issue = {"step": int|null,     // 0-based step index; null = a plan-level field
         "field": string,      // "exposure_s", "repeat", "steps", …
         "code": string, "level": "error"|"warning", "message": string}
```

The plan is the core `SequencePlan` (`plan_to_dict` keys) plus `schema` and
`start_at_utc`. A step's missing keys take the `SequenceStep` defaults; a
missing top-level key its `plan_from_dict` default. The body is strict like
every other: an unknown key, a wrong type (`"10"`, `80.0` for a gain, `1`
for a boolean), a non-finite number, more than 200 steps or 64 metadata keys
is `400 invalid_argument`. A frame type is matched case-insensitively
(`"dark"` is stored `"Dark"`, as `plan_from_dict`).

**No silent clamp.** The plan is stored exactly as typed; every value the
Qt editor would clamp or substitute is an issue instead:

| code | level | when (Qt behaviour replaced) |
|---|---|---|
| `no_enabled_step` | error | no enabled step with a count (Qt "Add an enabled step", `sequence_panel.py:1150-1156`) |
| `out_of_range` | error | exposure outside the camera range (`limits`; Qt's 0.01-600 s default without one), gain outside it (0-600 default), count 1-9999, interval 0-3600 s, dither 0-999, cadence 0.01-3600 s, repeat 1-999, autofocus every 0-999 (the Qt spin-box ranges) |
| `cadence_short` | error | cadence shorter than the exposure (`transit.py:86-89`) |
| `unknown_frame_type` | error | not Light, Dark, Flat or Bias (Qt: loaded as Light, then refused) |
| `unknown_on_complete` | error | not one of the three end-of-run actions (Qt: "Nothing") |
| `base_dir_relative` | error | `base_dir` is not an absolute path |
| `unknown_filter` | error with the wheel connected, warning from the profile | a Light or Flat filter that is not a slot (Qt: the first light slot, S7) |
| `dark_slot` | error | a Light or Flat step on the opaque Dark slot: black frames (S7; Qt allows it, the engine refuses it at start, so the plan does too) |
| `interval_ignored` | warning | an interval on a step with a cadence: the cadence wins (P2) |
| `no_object` | warning | empty object name (Qt readiness "Object name required"; frames say "Unknown") |
| `start_in_past` | warning | `start_at_utc` already passed: Start runs at once |
| `light_filters` | warning | the enabled Light steps use two filters or more (two names of one filter token count once): "Light steps use 2 filters (IR and LP): each star gets one light curve and one CSV per filter." (release S49, the Qt editor's words; `step` null, `field` `filter_name`) |

Ranges: the connected camera's limits as Qt's `set_camera_limits`
(`sequence_panel.py:1016-1041`: exposure from max(min, 0.01 s)); after a
disconnect the last camera's limits stay (S7: the ranges are not reset); the
Qt defaults before any camera. Filter names: the wheel's slots when it is
connected, else the telescope profile's slots (warning only), else Qt's
defaults `IR`, `LP`, `Dark` (warning only). `derived` is computed on the
plan as typed, with the core's own `max(1, repeat)` and `count > 0` rules;
`per_step_s[i]` = count × (cadence, else exposure + interval + 3 s) for an
enabled step, 0 otherwise.

- **Object** (Q-P1): one object per plan, shared with Observe. A `PUT`
  whose non-empty `object_name` differs from the observation's sets the
  observation (`PUT /api/observation` semantics: target set re-keyed, live
  curves reset), as Qt's Object field does. An empty name never clears the
  observation (P10). When Observe changes the object, the draft follows it
  on its next read (`notes` says so).
- **Metadata** (S5): kept while the object is the one it was prepared for
  (a transit plan: its host star); a change of object drops it and `notes`
  says "Planning metadata dropped: it was prepared for <object>." A `PUT`
  that echoes the stored metadata keeps it; new metadata belongs to the
  `PUT`'s object.
- **Draft** (Q-P3): `sequence_draft.json` beside `config.json` (the
  server's config folder), written atomically (temporary file, fsync,
  rename) on every change and read back at start-up; with no config folder
  (tests) it lives in memory. The file is a Plan (plus `metadata_object`, the
  object its metadata was prepared for), so the Qt app opens it as a preset. An unreadable draft is kept aside as
  `sequence_draft.json.unreadable-<UTC stamp>` and logged; the server starts
  from Qt's first row (one enabled Light step, 10 × 10 s, gain 80, on the
  first slot that passes light, never Dark).
- **Locked** (Q-P9): `PUT`, `import` and `POST /api/transit/plan` answer
  `409 run_active` "The plan is locked while the sequence runs." while a run
  is active. Presets, export, visibility and prediction stay available.

Hooks for the sequence engine (`hub.plan`, a `PlanService`):
`hub.plan.plan_for_run()` returns the draft as a core `SequencePlan` (the
object followed, metadata only for its own object) or raises `400
invalid_argument` "Fix step 2: cadence 5 s is shorter than the 10 s
exposure." (the first error); `hub.plan.publish()` re-sends `sequence_plan`
(call it when a run starts or ends, so `locked` follows);
`sequence_plan.observation_payload(plan)` and `observation_json(plan)` give
`observation.json` exactly as `SequenceWorker._write_observation_metadata`
(`sequence_worker.py:462-480`: `schema_version` 1, `object_name`, the
metadata; `indent=2, sort_keys=True`). The plan service asks
`hub.sequence.run_active()` (a bool; the sequence engine's), and reads
"not active" while `hub.sequence` does not exist.

### Presets (A60) and files (A61)

```
PresetList = {"directory": string,          // data_paths.sequence_presets_directory
              "presets": [{"name": string, "modified_utc": string,
                           "object_name": string|null, "steps": int|null,
                           "total_frames": int|null, "estimate_s": number|null,
                           "error": string|null}]}     // unreadable file: why
Preset = {"name", "modified_utc", "path", "plan": Plan, "derived", "issues", "ready"}
```

A preset is `<directory>/<name>.json` in **Qt's format**: `plan_to_dict`
with `indent=2` (`sequence_panel.py:973-985`), no `schema`, no
`start_at_utc`; the Qt app and the server read each other's files. The list
holds every `*.json` file that is not hidden, by name (case-insensitive).
A name is 1-100 characters, no `/ \ : * ? " < > |` or control character, no
leading dot or space, no trailing dot or space (`400 invalid_argument`); a
trailing `.json` is ignored. `GET` of a missing preset, `DELETE` of one:
`404 not_found`. `PUT` saves the body (or the draft when there is none) and
answers `409 file_exists` when the preset exists without `?overwrite=true`;
saving stays available during a run. A file Qt cannot read (unknown step
key, unknown frame type, wrong JSON) is listed with its `error` and `GET`
answers `400 invalid_argument` with the reason.

- **`POST /api/sequence/plan/import`** `{"path": "/abs/file.json"}` (any
  `.json` inside the folders ARGOS may browse; `403 forbidden_path`
  outside, `404 not_found` missing) or `{"preset": name}` replaces the draft
  as Qt's Load preset does (`sequence_panel.py:987-1013`): the planning
  metadata is **not** restored (a transit window belongs to one night) and
  `notes` says "Planning metadata not restored: use Prepare transit for
  tonight's window."; values Qt would adjust are kept and shown as issues.
  `409 run_active` during a run.
- **`POST /api/sequence/plan/export`** `{"path", "overwrite"}` writes the
  draft in Qt's format (metadata included, as Qt's Save preset). A path
  without a suffix gets `.json` (Qt); another suffix is `400`; an existing
  file without `"overwrite": true` is `409 file_exists`; a folder that does
  not exist is `400` "No folder <path>." (nothing is created). Exported
  files, presets and the draft get a plain file's mode (0644 under the usual
  umask), and a replaced file keeps its own.

### Visibility (A65)

```
Visibility = {"site": {"name": string, "latitude_deg", "longitude_deg", "elevation_m"},
              "target": {"ra_hours", "dec_deg"},
              "night": {"date": "YYYY-MM-DD",          // the evening's date
                        "dusk_utc": string|null,      // Sun below −18°
                        "dawn_utc": string|null},     // Sun above −18° again
              "twilight": {"sunset_utc", "civil_dusk_utc", "nautical_dusk_utc",
                           "astronomical_dusk_utc", "astronomical_dawn_utc",
                           "nautical_dawn_utc", "civil_dawn_utc", "sunrise_utc"},  // string|null
              "samples": [{"t_utc", "alt_deg", "sun_alt_deg"}],
              "peak": {"t_utc", "alt_deg"},           // highest in the night (else the span)
              "window": {"start_utc", "end_utc"}|null, // longest part above min_alt_deg in the night
              "windows": [{"start_utc", "end_utc"}],
              "min_alt_deg": number, "min_alt_source": "site"|"query",
              "step_min": int, "notes": [string]}
```

`409 site_missing` "Set the observing site in Settings to compute
altitudes." when no site is set (X2: a name, or coordinates other than 0/0;
never 0/0). The night of `night=D` runs from local solar noon of D (UTC noon
minus longitude/15 h) to the next one, so a night spans midnight and an
02:00 instant belongs to the night of the previous date (S26). Without
`night`, the night whose dawn has not passed yet. `night` is astronomical
dusk to dawn (Q-P6): the longest interval with the Sun below −18°; none
(`dusk_utc`/`dawn_utc` null, `window` null) where the Sun never gets that
low, with a note. Samples run every `step_min` (1-60) from an hour before
sunset to an hour after sunrise (solar 16:00 to 08:00 when the Sun does not
set or rise), on UTC multiples of `step_min`. Altitudes are the core's fast
spherical trigonometry (`sky_geometry.altitude_at`, ≈0.1°, no refraction;
within 0.01° once release S51 precesses J2000 to the date); the Sun is the
Astronomical Almanac low-precision position (≈0.01°), already of date, so its
altitude takes the hour-angle formula without that precession
(`planning._altitude_of_date`); both are checked against astropy in the
tests. `min_alt_deg` comes from the
config key `site.min_altitude_deg` (default 30°) unless the query gives one
(a handle being dragged). The Moon comes later (Q-P6).

### Exoplanets (A42)

```
Exoplanet = {"planet_name", "host_name", "ra_hours", "dec_deg", "period_days",
             "epoch_bjd_tdb", "duration_hours": number|null, "depth_percent": number|null,
             "period_error_days": number|null, "epoch_error_days": number|null,
             "epoch_system", "source", "retrieved_utc"}
```

`lookup` is `exoplanets.lookup_exoplanet` (the cache first, then at most two
NASA Exoplanet Archive queries of 12 s each; a result is cached in
`data_paths.exoplanet_cache`). Errors, with the core's text: an empty query
`400 invalid_argument`; no such planet `404 not_found`; no network answer
`502 lookup_failed`; a planet whose ephemeris cannot be used (no BJD_TDB
epoch, missing or invalid column) `422 ephemeris_unusable`. `suggest` is
`cached_exoplanet_suggestions`: offline, names from the cache only. The
request runs off the event loop; a client that gives up simply ignores the
answer (the lookup still fills the cache).

### Transit prediction and plan (A66)

```
TransitBody = {"planet_name": string, "baseline_minutes": number = 60,
               "date": "YYYY-MM-DD"?,        // search from that night (solar noon)
               "from_utc": string?,          // or from this instant; default now
               "epoch_number": int?,         // this transit exactly (plan what was predicted)
               "observable_only": bool = true}
TransitPlanBody = TransitBody + {"exposure_s": number = 10, "cadence_s": number = 13,
                                 "gain": int = 80, "filter_name": string}
TransitPrediction = {"planet": Exoplanet,
                     "window": {"epoch_number", "mid_bjd_tdb", "ingress_bjd_tdb",
                                "egress_bjd_tdb", "coverage_start_bjd_tdb",
                                "coverage_end_bjd_tdb", "baseline_minutes", "coverage_hours"},
                     "utc": {"coverage_start", "ingress", "mid", "egress", "coverage_end"},
                     "altitude_deg": {same keys},
                     "sun_alt_deg": {same keys},
                     "night": {"date", "dusk_utc", "dawn_utc"},   // the night of the midpoint
                     "observable": {"transit": bool,     // ingress → egress dark and above the limit
                                    "coverage": bool},   // with both baselines
                     "usable": {"start_utc", "end_utc"}|null,   // part of the coverage dark and above
                     "skipped": [{"epoch_number", "mid_utc", "reason": "daylight"|"below_limit"}],
                     "skipped_count": int, "min_alt_deg": number}
```

`predict_next_transit` (`transit.py:34-68`) from `bjd_tdb(julian_date(from))`
at the site (`sequencer_page.py:132-145`), the UTC instants by
`utc_from_bjd_tdb` (`airmass.py:117-148`) as `_local_transit_window`. With
`observable_only` (Q-P10) the server chooses the date: it steps epoch by
epoch (366 days at most) and skips every transit whose ingress → egress is
not entirely in the astronomical night (`daylight`) or not entirely above
`site.min_altitude_deg` (`below_limit`), sampled every 2 min; `skipped`
lists the first 20. Without it, the next transit whatever the sky (Qt). A
given `epoch_number` is taken as is. Errors: `409 site_missing` (X2);
`400 invalid_argument` with the core's text ("A BJD_TDB transit epoch is
required for prediction.", "A published transit duration is required to
prepare coverage.", a negative baseline, a baseline above 240 min, the Qt
spin-box limit); `422 no_observable_transit` "No transit of <planet> is
observable from this site above 30° in the next 366 days."; the lookup's
own errors (A42).

`POST /api/transit/plan` predicts the same way, builds
`make_transit_sequence` (`transit.py:71-122`: one Light step, the count to
cover the window at the cadence, autofocus and dither off, the 13 metadata
keys) and makes it the draft, its object the host star (the observation
follows, as Qt's `load_plan`; the host becomes the catalogue target with
programme `exoplanet` unless it already is, as Qt's Find did), its metadata
kept for that object (S5), its `start_at_utc` the coverage start (Q-P2; Qt
P7: Start ran at once), said in `notes`. `filter_name` defaults to the first
slot that passes light. An exposure ≤ 0 or a cadence shorter than the
exposure is `400` with the core's text; a gain or exposure outside the
camera range becomes the plan's issue, never clamped. `409 run_active`
during a run. A run of that draft writes `observation.json` with the same
keys and values as Qt's. Logs (source `plan`, topic `sequence`): INFO
"Transit plan: <planet>, E=<n>, <count> frames from <UTC>"; OK "Preset
saved: <file>", "Plan saved to <path>"; INFO "Preset deleted: <file>".

## API 2 routes, wave 6a: sequences (A62-A64, the mount interlock)

Wave 6a, sequence half: the run of a plan (start now or at a set time,
pause, resume, stop), the `sequence` event, the preflight and the
mount-motion interlock of `web/lab/PROPOSAL.md` §7 (owner decision D2). The
plan itself is the plan half above; the engine runs the plan it holds.
Still `"api": 2` (additive).

The engine (`argos/server/sequence.py`) is a Qt-free port of the **fixed**
Qt sequence path (release 0.5.0): `AcquisitionEngine.start_sequence`,
`stop_sequence`, `pause_sequence`, `resume_sequence_run`,
`_on_seq_frame_saved`, `_on_seq_autofocus_due`, `_on_seq_finished`,
`_run_on_complete_action`, `_sequence_frame_context`
(`acquisition_engine.py:712-945`) and `SequenceWorker._run`, `_set_filter`,
`_read_back_filter`, `_shoot_one`, `_append_session`,
`_write_observation_metadata`, `_dither`, `_await_autofocus`
(`sequence_worker.py:162-503`), over the unchanged core (`expand_plan`,
`total_frames`, `FITSWriter`, `SessionLog`, `TargetSet`). The run has its
own thread; the FITS write runs on it (never on the event loop), each
photometry point on the photometry thread.

| Method | Path | Body | Returns | Row |
|---|---|---|---|---|
| GET | `/api/sequence` | — | SequenceState | A63 |
| POST | `/api/sequence/start` | StartBody | SequenceState | A62 |
| POST | `/api/sequence/pause` | — | SequenceState | A62 |
| POST | `/api/sequence/resume` | — | SequenceState | A62 |
| POST | `/api/sequence/stop` | — | SequenceState | A62 |
| GET | `/api/sequence/preflight` | `?start_at_utc=` | Preflight | A64 |

New WebSocket event: `sequence` (a **snapshot**, newest kept), sent on
every state change and after every saved sub, and once to a client that
connects (with the wave 4 snapshots), so a page opened mid-run shows the run
at once. `frame_saved` (A24) also carries the subs of a run
(`"source": "sequence"`). The status record (`GET /api/status`, `status`)
gains `"sequence": {"state", "active", "run_id", "object_name"}`. New error
codes: `preflight_blocked`, `not_running`; `run_active` is sent (below).

```
StartBody     = {"start_at_utc"?: ISO 8601 UTC|null}   // absent: the draft's start_at_utc; null: now
SequenceState = {"state": "idle"|"waiting"|"running"|"pausing"|"paused"|"autofocus"|"stopping",
                 "active": bool,                 // state != "idle": the plan is locked (Q-P9)
                 "run_id": string|null,          // UTC start "YYYYMMDDTHHMMSSZ" (Qt run id)
                 "run_root": path|null,          // <base>/<run_id>_<OBJECT>, created at the first save
                 "object_name": string|null,
                 "plan": Plan|null,              // the plan the run executes, frozen at start
                 "start_at_utc": ISO|null,       // scheduled start (state "waiting")
                 "started_utc": ISO|null,        // the run left "waiting"
                 "step_index": int|null,         // 0-based, in plan.steps
                 "step": Step|null,              // plan.steps[step_index]
                 "pass_index": int|null,         // 1-based pass (plan "repeat")
                 "repeat": int|null,
                 "frames_done": int, "frames_total": int,
                 "eta_s": float|null,            // time per frame x frames left (Qt), pauses excluded
                 "end_utc": ISO|null,            // now + eta_s (waiting: start + estimate)
                 "current": {"frame_type", "image_type", "filter", "exposure_s", "gain",
                             "index", "step_index", "started_utc"}|null,   // the sub exposing
                 "last_frame_utc": ISO|null,     // DATE-OBS of the newest saved sub
                 "last_saved_utc": ISO|null,     // when it was written
                 "last_frame_name": string|null,
                 "cadence_s": float|null,        // planned start-to-start of the current step
                 "observed_cadence_s": float|null,
                 "next_autofocus": {"reason": "every_n", "in_frames": int}|null,
                 "autofocus_runs": int,          // mid-run autofocus passes so far
                 "paused_by": "observer"|"motion"|null,
                 "end_action": "Nothing"|"Stop tracking"|"Park mount",
                 "last_result": RunResult|null,  // the last run's outcome, kept until the next start
                 "revision": int}
RunResult     = {"completed": bool,
                 "reason": "completed"|"stopped"|"cancelled"|"camera_error"|"device_lost"
                           |"wheel_error"|"save_error"|"autofocus_timeout"|"refused"|"shutdown",
                 "message": string,              // for the observer, shown verbatim
                 "frames_saved": int, "frames_total": int,
                 "run_root": path|null, "started_utc": ISO|null, "ended_utc": ISO}
Preflight     = {"checks": [Check], "level": "ok"|"note"|"block", "can_start": bool,
                 "frames_total": int, "estimate_s": float, "start_utc": ISO, "end_utc": ISO,
                 "bytes_needed": int, "bytes_free": int|null}
Check         = {"id": string, "level": "ok"|"note"|"block", "message": string,
                 "details"?: object}
```

- `Plan` and `Step` are the plan half's records.
- `cadence_s` is the step's `cadence_s`, else `exposure_s + interval_s + 3`
  (the 3 s per-frame overhead of `estimated_duration_s`). `observed_cadence_s`
  is the median start-to-start interval (DATE-OBS) of the last 10 subs of
  the step, a pause or an autofocus in between excluded; `null` before two
  subs. RunCard's "last-frame age against cadence" is `now − last_frame_utc`
  against these.
- `eta_s` is Qt's (`sequence_worker.py:226-228`: elapsed / done × left),
  with the time spent paused and in autofocus taken out of "elapsed" (Qt
  counted it, 06 P16); before the first sub, the plan's estimate.
- `next_autofocus`: with `autofocus_every_n > 0`, the subs left before the
  next periodic pass (Qt `frames_since_af`); a pass on a filter change
  cannot be counted ahead and is not listed.

### In-process interface with the plan half

- `hub.sequence.run_active()` (bool; also the `active` property): a run is
  waiting, running, pausing, paused, in autofocus or stopping.
  `hub.refuse_if_run_active(what)` raises `409 run_active` "A sequence is
  running — <what> is locked until it ends." with `details: {"state",
  "run_id"}`.
- At `POST /api/sequence/start` the engine takes the plan from
  `hub.plan.plan_for_run()` (its `400 invalid_argument` on the first error
  issue is passed on) and the draft's `start_at_utc` when the body has no
  `start_at_utc` member; it calls `hub.plan.publish()` when a run starts and
  ends, and writes `observation.json` with
  `sequence_plan.observation_json(plan)`. The engine checks again what it
  relies on, so nothing is ever clamped or remapped: in particular a Light
  or Flat step on the wheel's opaque slot is **refused** at start (S7, `400
  invalid_argument`, issue code `dark_slot`).

### Start (A62)

`POST /api/sequence/start` answers at once with the new state (`waiting` or
`running`). Refusals, in this order:

| HTTP | code | When |
|---|---|---|
| 409 | `busy` | A run is active (`details.owner: "sequence"`): "A sequence is already running." Also the second of two Starts sent at once (two clients): one start is prepared at a time, so they never share the camera. |
| 409 | `not_connected` | No camera: "Connect the camera before running a sequence." (Qt) |
| 409 | `busy` | Autofocus owns the camera (`owner: "autofocus"`): "Autofocus is running — it owns the camera. Wait for it to finish." (Qt `camera_service`) |
| 400 | `invalid_argument` | `start_at_utc` not an ISO time with a zone, or more than 24 h ahead; a plan error (the plan half's text; `details.issues` when the engine's own checks find it): no enabled step, a value outside the camera's limits, a cadence shorter than its exposure, a Light or Flat step on the wheel's opaque slot (S7), a filter the wheel does not have (never remapped), a binning other than 1 (FITS `XBINNING` assumes 1×1). A start time already passed starts at once (the plan's `start_in_past` warning). |
| 409 | `preflight_blocked` | Another `block` of the preflight (`details.checks`): the run folder not writable, not enough free disk space. |
| 500 | `internal_error` | The run could not begin after it was registered (an OS error opening the run, …): "The sequence could not start: <reason>". The engine is left free: `idle`, camera, focuser and observation released, `last_result.reason: "refused"` with that text. |

Then, as Qt (`start_sequence`, 712-753): the plan is frozen (`plan` in the
record), the observation's object is the plan's (the plan half keeps them
one, Q-P1) and is locked (`locked_reason` "A sequence is running
(<object>)."), the camera owner becomes `sequence` (a live view or a single
shot in progress is stopped: INFO "Live preview stopped — the sequence owns
the camera."), the focuser is locked (`locked_by: "sequence"`, manual moves
`409 busy` "A sequence owns the focuser."; Halt stays allowed), the live
curves are cleared (`photometry_reset`, reason `sequence_started`; their CSVs
stay on disk) and the series FWHM and flight recorder restart with the run
(Qt: at the run's first save, `_on_seq_frame_saved`). Field identification
is armed for a run with Light frames (S14, `FieldService.arm_for_sequence`;
WARN "Sequence: ASTAP not found — the field cannot be identified, so no
live photometry will be measured." without ASTAP) and restored after the
run. CMD "Sequence started — N frame(s)."

**Scheduled start (Q-P2).** With a start time the state is `waiting` until
then: the camera, mount and wheel stay free (live view and a slew to the
target are allowed), the plan is locked. The wait is the server's: it
survives client disconnects and is cancelled by Stop (`last_result.reason:
"cancelled"`). At the start time the camera checks are made again; an
autofocus in progress is waited for (INFO once, at most 300 s, then
`reason: "refused"`); a camera gone is `reason: "refused"` with the text.
`run_id` is the moment the run really starts.

### Each sub (`SequenceWorker._run`, `_shoot_one`)

In Qt's order, for each frame of `expand_plan(plan)` (steps, counts,
repeats; the frame index restarts per (type, filter, exposure, gain) series
and grows across passes):

1. stop flag and pause gate (a pause holds here);
2. a new step → INFO "Step <n>/<N>: <count> × <type> <filter> <exposure> s";
3. wheel (when connected): Light / Flat to the step's filter, Dark / Bias to
   the opaque slot (`FrameSpec.wheel_filter`); the engine waits for the
   wheel to settle (≤ 20 s, as Qt; `wheel_error` when it does not); an
   autofocus on a filter change runs when the new slot passes light
   (`autofocus_on_filter_change`); without a wheel nothing moves;
4. periodic autofocus (`autofocus_every_n`), below;
5. FILTER read back from the wheel before the exposure (Qt
   `_read_back_filter`: a readable wheel that differs wins, with a WARN;
   without a wheel, the plan's); gain is the step's (sent with every
   exposure; the drivers have no read-back, as the Take shot);
6. the exposure: DATE-OBS just before StartExposure, the end at ImageReady
   (S36); the camera's own timeout (exposure + its grace) ends the run with
   `camera_error`;
7. the frame is published on `/ws/frames` (`origin: "sequence"`,
   `save: true`), measured for `frame_metrics` and the conditions rows, and,
   for a Light frame, given to field identification (calibration frames are
   not: a Dark has no field);
8. QA metrics on the array (`frame_metrics`, `detect_stars`), then the FITS
   through `FITSWriter.write` with the headers of Qt's sequence path
   (`_sequence_frame_context`: pointing of a live mount only, X1; the site
   only when set, X2; `EGAIN` from `camera.egain_table`, else the driver,
   else the sensor reference, S42), never overwriting; `session.json`
   rewritten; `observation.json` written with the first frame when the
   plan has `metadata` (S5: Qt's bytes, `sequence_plan.observation_json`);
9. `frame_saved` (`source: "sequence"`, `run_root`, `index`, `record`) and
   OK "Saved <file>  HFD=<hfd> FWHM=<fwhm>  stars=<n>" (Qt
   `imaging_page._on_seq_frame_saved`); the first save of the run writes
   `targets.json`, `photometry_selection.json` and
   `photometry_selection_history.jsonl` into the run folder;
10. **one photometry point per saved Light sub** (Qt `_on_seq_frame_saved`,
    `acquisition_engine.py:837-862`) when the field is identified and the set
    has a target: `PhotometryService.measure_saved_frame` on that sub's
    array, through the current **reference** solution with core's
    `ApertureTracker` plus S35 (owner decision 2: no point and the WARN
    "Photometry skipped: no star of the set where the solution places it…"
    when no anchor is found), epoch = DATE-OBS + EXPTIME / 2 (as Qt), CSVs
    in `<run>/photometry/`, the leave-one-out report rewritten to
    `<run>/photometry_quality.json` after every measured sub (S17). A fresh
    solution during the run resets the tracker (Qt `_on_reference_solved`)
    and is not itself measured;
11. progress (`frames_done`, `eta_s`), a dither every `dither_every` subs
    (counted over the run, as Qt: MoveAxis ±0.05 °/s for 1 s on both axes,
    alternating, 3 s settle; skipped without a mount);
12. the wait: `cadence_s` start-to-start (acquisition and save use the
    budget), else `interval_s` after the frame; Stop and a pause interrupt it.

### Run folder (as Qt)

```
<plan.base_dir or sessions_path>/<run_id>_<OBJECT>/
  lights/ darks/ flats/ biases/        <OBJECT>_<filter>_<type>_e<ms>ms_g<gain>_<index>.fit
  session.json                          SessionLog, rewritten after every sub
  observation.json                      plan metadata (S5), only when the plan has some
  targets.json  photometry_selection.json  photometry_selection_history.jsonl
  photometry/<role>_<OBJECT>_<auid or name>.csv
  photometry_quality.json
  diagnostics/<OBJECT>_live_diagnostics.jsonl   (diagnostics.enabled)
```

Two runs started within the same second would share a folder in Qt; the
server then appends `-2`, `-3`… to the run id. An in-run target-set edit
(A52, A53, A58: allowed during a run, Q-P9) rewrites
`photometry_selection.json` and appends to the history in the run folder
(`_write_active_selection`).

### Pause, resume, stop, end

- **Pause** (Qt `pause_sequence`): the exposure in progress **completes and
  is saved**; the run holds before the next exposure. The state is
  `pausing` while a sub is exposing or being saved, `paused` as soon as none
  is (a cadence or interval wait is cut short). A pause during a cadence
  step breaks the cadence: WARN "Pausing breaks the <cadence> s cadence of
  step <n>." (06 P16).
- **Resume** (`resume_sequence_run`): the run goes on with the next sub.
  A Pause asked during a mid-run autofocus is pending (state `autofocus`,
  `paused_by` set): Resume then cancels it (CMD "Pause cancelled: the run
  goes on after the autofocus.").
- **Never exposing while the mount moves** (not in Qt, whose Plan page locks
  the mount controls): before each sub the run stops any jog left running
  (a jog started while `waiting`) and holds while the mount slews (a
  scheduled start during a slew, Resume right after "Pause the run and
  slew"): INFO "Waiting for the slew to end before the next frame…", then
  "Slew finished — the run goes on.". Stop ends the wait. A slew still
  reported after 300 s pauses the run (`paused_by: "motion"`, ERROR "The
  mount still reports a slew after 300 s: the run is paused. Resume once
  the mount is still.").
- **Stop** (`stop_sequence`): the exposure in progress is **aborted** and
  that frame discarded (Qt `_safe_stop_exposure`); waits end; a mid-run
  autofocus is stopped (the focuser returns to its start, S23: Qt let the
  sweep finish); every saved frame stays. `stopping` until the run thread
  ends, then `idle` with `last_result.reason: "stopped"`.
- `pause` and `resume` answer `409 not_running` "No sequence is running."
  in `idle`, and in `waiting` ("The sequence has not started yet — Stop
  cancels it."); pausing a paused run or resuming a running one is a no-op;
  `stop` in `idle` answers the idle state.
- **End** (`_on_seq_finished`): camera owner back to `idle`, focuser
  unlocked, observation unlocked, field identification restored, OK
  "Sequence complete." or INFO "Sequence stopped: <message>", the outcome in
  `last_result`. On full completion only, the plan's end action
  (`on_complete`: "Stop tracking", "Park mount") runs, CMD "Sequence
  complete → parking the mount (plan option)." (Qt `_run_on_complete_action`).
- **Device lost.** The camera disconnected or failing ends the run
  (`device_lost` / `camera_error`, the text); the filter wheel disconnected
  during a run ends it too (`device_lost`, "The filter wheel was
  disconnected."), even when no further move is needed: without the wheel
  the FITS `FILTER` of the next subs could not be verified; a wheel that
  fails or does not settle when a move is needed ends it (`wheel_error`); a FITS that cannot
  be written ends it (`save_error`). A lost mount does not: subs are saved
  without pointing (X1) and dithers are skipped. Without a focuser the
  autofocus passes are skipped (INFO once; Qt skipped silently).
- **Server shutdown** during a run: Stop, then the run thread is joined
  (≤ 15 s); `session.json` is complete; `reason: "shutdown"`.
- Client disconnects change nothing.

### Mid-run autofocus (`_on_seq_autofocus_due`, `_await_autofocus`)

The run hands the camera to an autofocus sweep (owner `sequence` →
`autofocus` → `sequence`; state `autofocus`) with the Camera settings' gain
and `min(exposure, 10 s)` (Qt `_start_autofocus_worker`), ±2 000 steps,
9 positions (A36 defaults); the `autofocus` events and V-curve are the
usual ones. The series FWHM is re-sampled on the next measured sub (Qt
`_on_af_finished`; a manual autofocus outside a run does the same now).
Bounded: when the sweep has not ended after `9 × (exposure + 10 s) + 120 s`,
the run ends (`autofocus_timeout`).

### Photometry geometry locked (S15)

While a run is active, `PATCH /api/config` touching
`photometry.aperture_fwhm_mult`, `photometry.aperture_min_px`,
`photometry.annulus_in_px` or `photometry.annulus_out_px` answers
`409 run_active` "The aperture geometry is locked while a sequence runs
(one curve, one aperture)." with `details.keys`; nothing is written. The
other photometry settings (comparison selection) stay editable, as Qt.

### Mount-motion interlock (PROPOSAL §7, D2)

While a run is `running`, `pausing`, in `autofocus` or `stopping`, every
route that moves the mount (or changes where it points) answers
`409 run_active` with `details: {"state", "run_id", "action"}` and "A
sequence is running — <action> would move the field under it. Pause the run
first.":

| Route | Action |
|---|---|
| `POST /api/mount/goto` | GoTo |
| `POST /api/mount/center` (A32) | Centre |
| `POST /api/mount/sync` (A33) | Sync (changes the pointing model) |
| `POST /api/mount/park`, `/unpark` | Park, Unpark (the arm moves) |
| `POST /api/mount/tracking` `{"enabled": false}` | Tracking off (the field drifts); `true` is allowed |
| `POST /api/mount/tracking-rate` | Tracking rate |
| `POST /api/mount/jog` (dead-man) | Jog |
| Stellarium bridge GoTo (A19) | refused with WARN "Stellarium GoTo refused: a sequence is running — pause it first." (the bridge has no answer channel) |

Never refused: `POST /api/mount/stop` and `/mount/jog/stop` (safety). The
run's own motions (dither, the end action) are not refused. Autofocus and
field identification never move the mount. In `waiting`, `paused` and `idle`
the mount is free (a slew while paused drops the solution as usual; the
armed identification solves again on the next Light sub).

**"Pause the run and slew".** Each body above takes `"pause_run": true`
(`park`, `unpark` and `center` accept a body with only that member): the run
is paused (`paused_by: "motion"`, Qt pause semantics: the sub in progress
completes and is saved), the request waits for `paused` (at most the
exposure in progress plus 60 s, or a mid-run autofocus's bound), then the
motion runs and its usual answer is returned; the run stays paused until
Resume. If the run does not pause in time: `409 run_active` "The run did not
pause in time — nothing moved." Outside an active run `pause_run` is
ignored. **A client must wait that long for the answer** (the web client
waits the exposure in progress + 75 s, or 400 s during a mid-run autofocus:
`run.ts pauseRunTimeoutMs`): the server moves the mount when the run has
paused even if the client gave up, so a client timeout shorter than the
bound would report a failure the mount then belies.

### Preflight (A64)

`GET /api/sequence/preflight[?start_at_utc=]` checks the draft (during a
run, the running plan) against the devices and folders, worst level first;
`can_start` is false while one check is `block`, and Start refuses then
(codes above). Ids are unique within one answer: a plan issue's check is
`plan:<code>` (`plan:<code>:<step number>` for a step's, e.g.
`plan:interval_ignored:1`), any other repeated id gets `:<n>`; the base id
(before the first `:`) names the check. Ids and rules:

| id | ok | note | block |
|---|---|---|---|
| `run` | no run active | — | a run is active |
| `camera` | connected (name, sensor) | — | not connected; autofocus owns it |
| `plan` | frames and estimate | a plan warning (one note per issue, `plan:<code>[:<step>]`) | a plan error (`plan:<code>[:<step>]`); a Light / Flat step on the opaque slot (S7) |
| `start_at` | now, or the scheduled time | already passed (starts at once) | not a time, or > 24 h ahead |
| `object` | the plan's object | no object name (files say "Unknown", as Qt) | — |
| `mount` | connected, tracking | not connected (no pointing in the FITS); parked, idle or slewing with Light frames | — |
| `site` | set (name) | not set (X2: no BJD_TDB, the mount's airmass, no altitude check); the site check (X3) disagrees with the mount | — |
| `wheel` | every step's slot exists | no wheel and Light / Flat steps (FITS `FILTER` unverified) | a slot the wheel does not have |
| `focuser` | no autofocus planned, or a focuser | autofocus planned and no focuser (the passes are skipped) | — |
| `altitude` | the target stays above the limit over the run | it dips below the limit during the run (from when) | — |
| `output` | the run folder's parent is writable | — | not writable (the OS reason) |
| `disk` | needed against free | needed > 80 % of free | needed > free |
| `calibration` | darks, flats and biases matching the plan's Light steps that night | "Missing tonight: step 2 (10 s, gain 80, IR): flats and biases." (counts per kind in `details`) | — |
| `lid` | Dark / Bias steps through the wheel's Dark slot (the telescope's lid; the client names it "Dark frames") | Dark / Bias steps without a wheel with a Dark slot: "put the lid on" | — |
| `sleep` | keep-awake works (wave 6b): "The computer is kept awake during the run (caffeinate). Keep its lid open: a closed lid still sleeps most laptops." (`details.method`) | no method, or off in Settings › Alerts: "The computer is not kept awake: <why>. Keep it awake and its lid open for the whole run: a sleeping computer stops the run." (PROPOSAL §7: lid-closed sleep is out of software reach) | — |

- **Altitude**: the target is the observation's target (else the plan's
  metadata `ra_deg` / `dec_deg`, a transit plan's); altitude from the site
  (`sky_geometry.horizontal_at`) every 5 min from the start to the planned
  end; the limit is `site.min_altitude_deg` when that setting exists (Q-P6),
  else 30°. No site or no coordinates: a note says why.
- **Disk**: frames × (width × height × 2 bytes + 17 280 bytes of header and
  padding) for the camera's sensor, against `shutil.disk_usage` of the
  nearest existing folder of the run root.
- **Calibration counts per night**: the night is the 24 h from local noon
  before the run's start; the `session.json` of every run folder of the
  sessions folder started in it are read (not the FITS headers). Darks match
  a Light step's exposure and gain, biases its gain, flats its filter; the
  plan's own Dark / Flat / Bias steps count. `details: {"night_start_utc",
  "per_step": [{"step", "darks", "flats", "biases"}]}`.

### Simulator replay source

`--sim-replay DIR` (CLI; `SimOptions.replay_dir` in tests) makes the
`simulator` mode serve a folder of real FITS **copies** (nothing is written
there):

- **Camera**: each exposure returns the pixels of the next file, in file
  name order (`.fit`, `.fits`, `.fts`; raw 16-bit as Open FITS), and starts
  again from the first after the last (WARN once). The exposure time is
  still waited (Stop interrupts it); exposure, gain, focus and wheel do not
  change the pixels. The sensor is the first file's (`NAXIS1` × `NAXIS2`,
  `BAYERPAT`); `fits_readings` give the file's `CCD-TEMP` and `OFFSET`.
- **Mount**: the simulated mount reports the pointing of the file being
  exposed (before the first exposure, the first file's): `RA` / `DEC`
  (else `OBJCTRA` / `OBJCTDEC`), `ALTITUDE` / `AZIMUTH` when present (else
  computed at the simulator's site), tracking. It starts unparked and
  tracking; a GoTo or a park behaves as usual, and the replayed pointing
  comes back once it tracks again.
- The replay mount is alt-az (as the Seestar that took the frames): the
  photometry tracker allows the field rotation, no pier side.
- So field identification (the mount is the hint), tracking and photometry
  work during a sequence on the simulator. The saved subs are dated by the
  server clock (today): BJD_TDB and airmass are today's for that field.
- A folder with no FITS image, or a first file that is not raw 16-bit, stops
  the server at start-up with the reason.

### Errors (wave 6a, sequences)

| HTTP | code | When |
|---|---|---|
| 409 | `run_active` | A mount motion during a run (interlock above); a photometry-geometry change during a run; `details: {"state", "run_id", …}`. |
| 409 | `preflight_blocked` | Start refused by a preflight `block` other than the camera and plan checks; `details.checks`. |
| 409 | `not_running` | Pause or resume with no run, or while waiting for the start time. |

`sequence` is a snapshot (newest kept); `frame_saved` stays a stream.
`GET /api/photometry/live` (A54) now fills `run_root` and
`sequence_running` while a run is active.

## Night (wave 6b): attention, keep-awake, wrap-up

Wave 6b, server half (`web/lab/PROPOSAL.md` §3.1 and §7, owner decisions
D2 and D3; `web/lab/research/functional-spaces.md` §4.10 and §4.14). Still
`"api": 2` (additive). Modules: `argos/server/attention.py` (rules, items,
acknowledgement), `argos/server/keepawake.py` (the OS sleep assertion),
`argos/server/wrapup.py` (the end-of-run record and the calibration plan).

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/attention` | — | AttentionState |
| POST | `/api/attention/{id}/ack` | AckBody (optional) | AttentionState |
| POST | `/api/attention/ack-all` | AckBody (optional) | AttentionState |
| GET | `/api/sequence/wrapup` | — | WrapUp (`404 not_found` "No run has ended yet." before the first end) |
| POST | `/api/sequence/calibration-plan` | CalibrationBody (optional) | `{"plan": PlanRecord, "replaced": Plan}` |

New WebSocket event `attention` (a **snapshot**, newest kept; sent on
every change and once to a client that connects, after `sequence`). The
status record gains `keep_awake`; the `sequence` record gains `autofocus`,
`autofocus_passes` and `wrapup`. New config category `alerts` (Settings ›
Alerts).

### Attention (PROPOSAL §7, D3)

The rules run **on the server**, so every client shows the same list and
an acknowledgement made on one is seen by all. Port of
`web/src/lab/workspace/model/rules.ts` (its tests are the oracle:
`tests/server/test_attention.py` replays the lab's synthetic night), turned
from "evaluate the whole list" into per-frame state with hysteresis.

```
AttentionItem  = {"id": string,             // "<rule>-<run_id or 'server'>-<n>", unique in the server process
                  "rule": RuleId,             // machine id, below
                  "cause": string,            // rule + subject ("hfd_rise:IR", "device_lost:mount"): one open item per cause
                  "name": string,             // the rule in words: "HFD rise", "No new frame", …
                  "level": "critical"|"attention"|"info",
                  "kind": "condition"|"event",// condition: clears itself when its cause ends; event: stays until acknowledged
                  "title": string,            // the rule and the numbers, never an interpretation alone
                  "short": string,            // Watch headline (read from 2 m): the value and the factor only
                  "detail": string,           // the rule, its threshold and the frames that fired it
                  "values": {string: number|string|null}, // hfd_rise, star_drop: + the baseline's origin (Baselines, below)
                  "since": ISO,               // when the cause began (the firing sub's DATE-OBS, or when found)
                  "raised_utc": ISO, "updated_utc": ISO,
                  "frame": int|null,          // the run's sub number (1-based, as frames_done) that fired it
                  "run_id": string|null,
                  "action": {"to": "focus"|"field"|"run"|"watch"|"devices", "label": string}|null,
                  "active": bool,             // in the active list
                  "cleared_utc": ISO|null,
                  "cleared_reason": "resolved"|"run_ended"|"new_run"|"acknowledged"|null,
                  "acked": bool, "acked_utc": ISO|null, "acked_by": string|null,
                  "occurrences": int,         // 1, +1 each time the same cause fires again within 10 min of its clear
                  "tone": int, "toned_utc": ISO, // 1, +1 at a reopen that sounds again; the client plays one tone per (id, tone)
                  "sound": bool,              // the client plays the level's tone when it appears (info: alerts.sound_info)
                  "repeat_s": int|null}       // critical only: repeat the tone every N s while active and not acknowledged
AttentionState = {"active": [AttentionItem],  // critical, then attention, then info; newest first within a level
                  "history": [AttentionItem], // items that left the active list (resolved, run_ended, new_run, acknowledged events), newest first, at most 200
                  "counts": {"critical": int, "attention": int, "info": int,
                             "unacked": int}, // active, not acknowledged, level ≠ info (the status-bar chip)
                  "sound": {"level": "off"|"soft"|"normal", "info": bool, "repeat_s": int},
                  "thresholds": {…the alerts.* values in force},
                  "baselines": [RunBaseline], // the run's HFD and star baselines, one entry per filter with either (the last run's until the next Start; [] before the first)
                  "last_change": {"change": "raised"|"updated"|"reopened"|"cleared"|"acked",
                                  "id": string}|null,
                  "revision": int}
AckBody        = {"by"?: string (≤ 64)}       // who acknowledged (the client's label); default "observer"
RunBaseline    = {"filter": string, "object": string,
                  "hfd_px": number|null, "stars": number|null, // null: none yet (or no value among its subs)
                  "hfd_from": BaselineFrom|null, "stars_from": BaselineFrom|null}
BaselineFrom   = {"frames": int,              // B of the run that made it
                  "origin": "this_run"|"earlier_run",
                  "run_id": string|null, "run_utc": ISO|null, // the run whose first B subs made it, and its start
                  "exposure_s"?: number|null, "gain"?: int|null} // stars_from only: the setup it was made with
```

- **Levels by mark and word** (D3): critical = filled disc, attention =
  upright mark, info = hollow ring, always with the word; never a triangle.
- **Numbers in the texts** follow the UI's (`web/src/lib/format/number.ts`):
  counts grouped with U+202F from 1 000 ("2 010 stars"), U+2212 for
  negatives, ranges "23 … 25". HFD keeps the lab's one decimal in the texts
  (rules.ts, the oracle).
- **Hysteresis.** A frame rule fires after `alerts.consecutive_frames` (K,
  default 3) subs in a row past its threshold and clears after K subs in a
  row back inside it; the timed rules have the margins below. At most **one
  open item per cause**; a cause that fires again within 10 min of its clear
  **reopens** its item (`occurrences` + 1, `last_change.change:
  "reopened"`), later it is a new item. A reopened item is **unacknowledged**
  again: a new episode needs a new acknowledgement (wave 6b review: an
  acknowledged "No new frame" that came back was silent). A critical reopen
  always sounds (`tone` + 1, a log line); a non-critical one within 15 min
  of its last tone keeps its `tone` and logs nothing (a value flapping
  across its threshold all night: one item, no storm of tones or lines;
  the next audible reopen logs "<name> again (×n): …").
- **Acknowledge** (any client): `acked`, `acked_utc`, `acked_by` set;
  repeats stop. An acknowledged **condition** stays active until its cause
  ends; an acknowledged **event** moves to the history (`cleared_reason:
  "acknowledged"`). A second ack is a no-op; an unknown id is `404
  not_found`. `ack-all` acknowledges every active item.
- **Scope.** The rules watch a run (from Start to its end): the frame rules
  read the run's own subs (`frame_saved` with `source: "sequence"`, Light
  frames) and the photometry outcome of each; nothing fires outside a run.
  When a run ends its open conditions clear (`run_ended`); a new run moves
  the previous run's unacknowledged events to the history (`new_run`).
- **Log.** Every raise is a log line (`source: "attention"`; critical
  ERROR, attention WARNING, info INFO): "HFD rise: HFD 17.5 px = 2.8× the
  first 20 frames" (the title alone when it already starts with the rule's
  name: "Run stopped: …"); a clear "Cleared: <name> — <why>"; an ack
  "Acknowledged: <name> (<title>)".
- **Evaluation never blocks the event loop**: the service observes the
  published events (an `EventBus` tap only queues them) and evaluates them
  on its own thread, plus a 1 s timer for the timed rules.

| `rule` | Level | Kind | Fires | Clears | Action |
|---|---|---|---|---|---|
| `no_frame` | critical | condition | running or pausing, and `now − save of the last sub` > max(F × c, c + M) s, c = median save-to-save interval of the run's subs since the last break (pause, autofocus, new step): a client learns of a frame when it is saved (`frame_saved` `t`); before two saves since the break, > F × f + M s, f = the larger of the planned `cadence_s` and the newest sub's start-to-save time (a Seestar's 10 s sub costs 20-45 s), counted from the start or the resume before the first save. Counted from the sub's start (before the wave 6b fix) it fired at the start of all 9 of the owner's runs; from the save: 0 false alarms, worst 0.77 of the limit, the real freeze of RR Lyr 2026-09-25 still fires (112 s after the last save) | a sub is saved; the run pauses or ends | Watch |
| `hfd_rise` | attention | condition | HFD > H × the filter's HFD baseline (the median of B Light subs: below), K in a row | K in a row at or under | Focus |
| `star_drop` | attention | condition | stars < S × the filter's star baseline (the median of the same B subs), K in a row | K in a row at or over | — |
| `comps_low` | attention | condition | the target's point used fewer than C comparisons, K measured subs in a row (subs without a target point do not count) | K in a row with C or more | Field |
| `tracker_lost` | attention | condition | K Light subs in a row got no point because the stars are not where the solution puts them: photometry `reason` `field_lost` (S35) or `lock_lost` (S48, below) | K subs in a row measured | Field |
| `altitude` | attention | condition | the target is below `site.min_altitude_deg` (30° when unset) now, or will be within A min (checked every 60 s; Light runs only: a plan with no enabled Light step has none, as the preflight's "Calibration frames only"). "Now" is the mount's altitude when the mount points within 1° of the target, else the Settings site's; "within A min" is extrapolated from the Settings site only while the site check (`site_check.state`) is not `mismatch`. With a mismatching site and no mount reading on the target: no verdict (RR Lyr 2026-09-25: 13.9° from the wrong site while the mount read 75°). The detail says where "now" came from | above the limit + 0.5° and not below within A min | Run |
| `disk` | attention | condition | free space of the run folder's disk < the subs of D min at the cadence, or of the run's remaining frames (`frames_total` − saved) when fewer (the newest sub's file size) | free ≥ 1.1 × that | — |
| `device_lost` | critical | condition | a mount or focuser connected when the run started is no longer connected (a camera or wheel lost ends the run: `run_error`) | connected again | Devices |
| `run_error` | critical | event | the run ended with `camera_error`, `device_lost`, `wheel_error`, `save_error`, `autofocus_timeout` or `refused` (the message verbatim) | acknowledged | Run |
| `autofocus_failed` | attention | event | a mid-run autofocus ended `rejected`, `failed`, `cancelled`, `timeout` or `not_started` without a Stop | acknowledged | Focus |
| `run_started` | info | event | the run left `waiting` ("Run started · RR Lyr · 195 frames · ends about 22:54 UTC") | acknowledged, or the next run | — |
| `run_ended` | info | event | the run ended `completed`, `stopped` or `cancelled` | acknowledged, or the next run | Run |
| `autofocus_done` | info | event | a mid-run autofocus ended `done` (best position, HFD) | acknowledged, or the next run | — |

Thresholds are config keys, category `alerts` (`GET /api/config` meta;
`PATCH /api/config`); a change applies from the next evaluation:

| Key | Default | Range | Meaning |
|---|---|---|---|
| `alerts.sound` | `"normal"` | off, soft, normal | Tone volume of the clients (Web Audio; the client plays, armed by a user gesture) |
| `alerts.sound_info` | `false` | — | Info items sound too (one soft tone) |
| `alerts.repeat_critical_s` | 30 | 0-600 s | Repeat a critical tone until acknowledged (0: once) |
| `alerts.consecutive_frames` | 3 | 1-20 | K |
| `alerts.baseline_frames` | 20 | 5-200 | B |
| `alerts.hfd_factor` | 1.5 | 1.1-5 | H |
| `alerts.star_factor` | 0.7 | 0.1-0.95 | S |
| `alerts.comparisons_min` | 3 | 1-20 | C |
| `alerts.no_frame_factor` | 2.0 | 1.2-10 | F |
| `alerts.no_frame_margin_s` | 60 | 0-3600 s | M |
| `alerts.altitude_warn_min` | 15 | 0-180 min | A |
| `alerts.disk_minutes` | 30 | 1-600 min | D |
| `alerts.keep_awake` | `true` | — | Keep the computer awake during a run (below) |

Defaults are `functional-spaces.md` §4.10 (replayed on the 2026-09-25
run: the HFD rise fires at frame 150; no star, comparison or silence alarm).

**Baselines carried over runs** (owner decisions 2026-11-14 and
2026-11-15). The HFD and star baselines of a filter are the medians of B
Light subs. A run's first sub of a filter looks for baselines the **server
session** already holds: the **HFD baseline for the same object and
filter**, the **star baseline for the same object, filter, exposure and
gain** (star counts follow exposure and gain: 2 217 at 20 s gain 80 against
3 455 at 60 s gain 100 on 2026-09-07; object names compare without case or
extra spaces; an unnamed object, "Unknown", never carries):

- found: that baseline is **carried** and its rule judges the filter from
  its first sub (the owner restarts runs after trouble: 7 of the 9 runs of
  the three nights had fewer than B + K = 23 subs, so per run they were
  never judged);
- not found: the run makes its own from its first B subs of the filter, as
  before, and the session keeps it for the later runs of that setup (the
  star baseline only when those B subs share one exposure and gain). A
  carried baseline is never replaced by a later run's.
- **12 hours without a sub of its setup** (sub DATE-OBS; for the HFD, any
  sub of the object and filter): the baseline is no longer carried (a server
  left running would carry one night's seeing into the next). On the owner's
  three nights in one server it changes one thing: 2026-09-07 040723Z is not
  judged against 2026-08-29's 6.55 px (it fired at sub 20, 04:34:43 UTC,
  without the rule; with it, at sub 23 on its own 7.60 px, as per run).
- A later step that changes the exposure or gain under a carried star
  baseline starts that baseline again as at the filter's first sub (an open
  `star_drop` item clears: "frame n changed the exposure or gain; its
  baseline starts again."); the HFD baseline stays.
- **A server restart starts fresh**: the session's baselines live in the
  server process only (never in a file).

The texts name a carried baseline's origin: "HFD 11.1 px = 1.7× the first
20 frames of the run of 05:01 UTC" (the log line is "HFD rise: " + that
title), the detail ends "Baseline: the first 20 frames of the run of 05:01
UTC, same object and filter." (a star item's: "…, same object, filter,
exposure and gain."); a run's own baseline keeps
"… the first 20 frames". The items' `values` add `baseline_frames`,
`baseline_origin` (`"this_run"` | `"earlier_run"`), `baseline_run_id` and
`baseline_run_utc` (that run's start), and `AttentionState.baselines`
lists the run's baselines in force (`RunBaseline`) so a client draws the
threshold the server compares with before any item fires (a new snapshot is
sent when one is set). Replayed on the owner's three nights
(`web/spec/wave6b-attention-replay.md`, "Baselines carried over runs"):
two new alerts, both HFD rises on a carried baseline: 2026-08-29 053540Z
sub 4 (05:39:38 UTC, 11.1 px = 1.7× the 6.55 px of 050148Z) and the
degraded 2026-09-07 045626Z run (60 s, gain 100) at sub 3 (05:00:02 UTC,
39.2 px = 5.2× the 7.60 px of 040723Z, 20 s, gain 80); no star alert, no
other change, the same with one server for the three nights.

**Hook agreed with the photometry half (S48).** A Light sub refused by the
S48 lock check (fewer than ceil(n/2) anchors show a star of SNR ≥ 5 where
the tracked solution puts them) leaves the `photometry` status with
`state: "skipped"`, `reason: "lock_lost"`; `tracker_lost` counts it as it
counts S35's `field_lost`. Each skipped outcome is counted once (its
`message` names the frame).

### Keep-awake (PROPOSAL §3.1)

While a run is active (from Start, `waiting` included: a scheduled start
needs the computer awake, to its end) the server holds an OS sleep
assertion with the tools the OS has (no dependency): macOS `caffeinate -i
-w <server pid>` (the assertion "caffeinate command-line tool" in `pmset -g
assertions`; it ends with the server even after a crash), Linux
`systemd-inhibit --what=idle:sleep --mode=block` around `tail --pid=<server
pid> -f /dev/null`, Windows `SetThreadExecutionState(ES_CONTINUOUS |
ES_SYSTEM_REQUIRED)` on a holder thread. Released when the run ends
(completed, stopped, failed, the run thread crashed) and at shutdown. Only
the server started by the CLI takes a real assertion; in-process tests use
a fake.

```
KeepAwake = {"state": "off"|"held"|"failed"|"unsupported"|"disabled",
             "method": "caffeinate"|"systemd-inhibit"|"SetThreadExecutionState"|null,
             "since": ISO|null,          // held since
             "reason": string|null,      // why it is held: "A sequence is running (RR Lyr)."
             "message": string|null}     // failed / unsupported: why
```

- In `status.keep_awake` (a change sends `status`).
- Preflight `sleep` row: `ok` "The computer is kept awake during the run
  (caffeinate). Keep its lid open: a closed lid still sleeps most laptops."
  when a method exists and `alerts.keep_awake` is on; `note` otherwise
  ("…not kept awake: <why>. Keep the computer awake and its lid open…").
  Lid-closed sleep stays out of software reach: the row always says so.
- A failed assertion is a WARNING log line and `state: "failed"`; the run
  goes on.
- `alerts.keep_awake` changed during a run applies at once: off releases the
  assertion (`state: "disabled"`), on takes it (wave 6b review; before, both
  waited for the next run).
- A shutdown or a Stop that arrives while the OS call is being made never
  leaves the assertion held: it is released as soon as the call returns.
- (Wave 8) `held` is reported from the moment the run asks for it, in the
  same `status` that announces the run, when a method exists and the
  setting is on: the macOS and Linux helpers hold the OS assertion within
  milliseconds of their start, while the check that they stayed alive takes
  0.2 s (before, `status.keep_awake.state` read `off` during that check
  although `pmset` already listed the assertion). A helper that exits at
  once turns the record to `failed`, with the WARNING line.

### Sequence record additions (6a leftovers, D2)

```
"autofocus": {"started_utc": ISO, "stage": string|null, "step": int,
              "total": int, "position": int|null}|null,   // the mid-run pass in progress (state "autofocus")
"autofocus_passes": [{"started_utc": ISO, "ended_utc": ISO|null,
                      "state": "done"|"rejected"|"failed"|"cancelled"|"timeout"|"not_started",
                      "position": int|null, "hfd_px": float|null,
                      "message": string|null, "frames_done": int}],   // the run's passes, oldest first
                                                         // (idle: the last run's, until the next Start)
"wrapup": WrapUp|null                                    // the last run's, from its end to the next Start
```

The record is re-sent on every sample of a mid-run autofocus (the run
strip's `afStep` is `autofocus.step` of `autofocus.total`).

### Wrap-up (PROPOSAL §3.1, D2; functional-spaces §4.14)

Built when a run ends, after its last point is measured (the run waits up
to 10 s for the photometry queue, 2 s at shutdown), then the `sequence`
record is re-sent with it (`wrapup` is `null` in the first record of the
end, for a moment).

```
WrapUp = {"run_id": string|null, "object_name": string,
          "outcome": RunResult,                          // = last_result
          "started_utc": ISO|null, "ended_utc": ISO,
          "frames": {"saved": int, "total": int, "by_type": {"Light": int, …}},
          "points": {"target": int, "all": int, "flagged": int,   // suspect or saturated points
                     "frames_measured": int,
                     "frames_skipped": {"field_lost": int, "lock_lost": int, "other": int}},
          "attention": {"critical": int, "attention": int, "info": int,
                        "items": [{"id", "rule", "name", "level", "title", "since",
                                   "cleared_utc", "acked"}]},   // the run's items, oldest first
          "run_root": path|null, "run_folder": string|null, "run_bytes": int|null,
          "mount": {"connected": bool, "state": string|null, "tracking": bool|null,
                    "end_action": string},                // after the end action ran
          "calibration": Calibration}
Calibration = {"darks": [{"exposure_s": float, "gain": int, "count": int,
                          "existing": int, "estimate_s": float}],
               "biases": [{"exposure_s": float, "gain": int, "count": int,
                           "existing": int, "estimate_s": float}],
               "overhead_s": float,       // median (DATE-OBS to save − exposure) of the subs, ≥ 3 s
               "cadence_s": float|null,   // the run's observed cadence
               "dark_slot": bool,         // the wheel has a Dark slot (else: put the lid on)
               "note": string|null}
CalibrationBody = {"darks"?: int (0-999, default 20), "biases"?: int (0-999, default 30)}
```

- One dark entry per (exposure, gain) of the run's Light steps, one bias
  entry per gain (exposure max(the camera's shortest, 0.01 s): the plan's
  floor, Qt's); counts
  are the guide's 20 darks and 30 biases; `existing` are tonight's
  (the preflight's `calibration` count: the night from local noon);
  `estimate_s` = count × (exposure + `overhead_s`): the observed cadence,
  not the exposure alone (functional-spaces finding 1).
- `POST /api/sequence/calibration-plan` replaces the **draft** with those
  Dark and Bias steps (the last run's object, its gain, the Dark slot
  through the wheel; nothing starts) and returns the plan record and the
  draft it replaced (for an Undo). Without a wrap-up it uses the draft's
  Light steps. `409 run_active` while a run is active; `400
  invalid_argument` when there is no Light step to match.

### Errors (wave 6b)

| HTTP | code | When |
|---|---|---|
| 404 | `not_found` | Ack of an unknown attention id; the wrap-up before any run ended. |
| 409 | `run_active` | Calibration plan during a run. |
| 400 | `invalid_argument` | Calibration plan with no Light step to match; counts out of range. |

## Review (wave 7): sessions, curves, frames

Wave 7 (`web/spec/README.md` rows A67-A75 on the job model A80) adds the
routes below, still under `"api": 2` (additive). They read recorded
sessions, curve CSVs and FITS files and never write into them. The session
reader is the fixed Qt reader itself: `argos/core/session/review.py`
(`load_session`, `identify_curve_file`, `nearest_light_frame`; 0.5.0 with
S9, S10, S49, S57) is loaded from its file by `argos/server/review.py`,
because its package `argos.core.session` imports PyQt6 and the server must
not. The frame tools are the Frame Viewer's (`analysis_window.py`) over the
unchanged core (`measure_star_at`, `build_solve_settings`, `wcs_from_result`,
`overlay_for`) and the wave 4 server ports (`field_solve.py`,
`field_catalog.py`).

| Method | Path | Body | Returns | Row |
|---|---|---|---|---|
| POST | `/api/sessions/scan` | — | `202 {job_id, job}`, job `sessions_scan` | A67 |
| POST | `/api/review/session` | `{"path": path}` | `202 {job_id, job}`, job `session_open`; result OpenSummary (the ReviewSession is read with the GET below, from the cache this open filled) | A68 |
| GET | `/api/review/session?path=` | — | ReviewSession (the cached open, recomputed when stale or missing) | A68 |
| GET | `/api/review/session/curves?path=` | — | CurveSet of the session | A69 |
| GET | `/api/review/live/curves` | — | CurveSet of the live run (A54's store) | A69 |
| POST | `/api/review/import-csv` | `{"path": path}` | CurveSet of one curve CSV; `422 invalid_csv` | A70 |
| GET | `/api/files/frame?path=&view=raw` | — | binary frame, `/ws/frames` layout | A71 |
| GET | `/api/files/fits-header?path=` | — | FitsHeader | A72 |
| POST | `/api/files/measure-star` | MeasureStarBody | StarMeasure | A73 |
| POST | `/api/files/solve` | `{"path": path}` | `202 {job_id, job}`, job `file_solve`; result FileSolution | A74 |
| GET | `/api/files/solution?path=` | — | FileSolution of the last good solve of that file; `404 not_found` | A74 |
| POST | `/api/files/catalogue` | `{"path": path}` | `202 {job_id, job}`, job `file_catalogue`; result FileLayers | A75 |

**Paths.** Every `path` is absolute (`~` expanded) and must lie in the
folders the file listing may browse (home and the ARGOS data folders, A11,
symbolic links resolved): outside is `403 forbidden_path`, relative `400
invalid_argument`, missing `404 not_found`. A session path is the folder or
its `session.json`. FITS routes accept `.fit`, `.fits`, `.fts` (any letter
case), else `400 invalid_argument`.

### Sources (shared with the exports and re-run routes, A76-A79)

```
Source = {"kind": "session", "path": path}   // a session folder (A68, A69)
       | {"kind": "import",  "path": path}   // one curve CSV (A70)
       | {"kind": "live"}                    // the live run's curves (A54), read-only (D3)
```

In process, `hub.review.curve_set(source)` returns the same CurveSet as
Python objects (`review.CurveSetData`): the core `LightCurve` objects as
loaded (points untouched, the input of `write_aavso` / `write_curves_csv`),
each with its wire key, filter token, flags and `problem`. A session's set
is cached (keyed by the stamps of `session.json`, `targets.json`, the
`photometry/` folder and its files), so the exports read the very curves
the plot shows.

### Session scan (A67)

`GET /api/sessions` is unchanged (wave 2). `POST /api/sessions/scan`
re-summarises every session folder under `sessions_path`, ignoring the
cache (resource `sessions`, `409 busy` while one runs); progress
`done`/`total` = folders, cancellable between folders. Result:
`{"root": path, "total": int, "scanned_utc": ISO}`; the list is then read
with `GET /api/sessions`.

### Open a session (A68)

```
ReviewSession = {"source": Source, "path": path, "folder": string,
  "object": string, "started_utc": string, "software": string,   // session.json as written
  "observer": string,                         // session.json "observer" ("" when none)
  "summary": object|null,                     // session.json "summary" block as written
  "counts": {"frames": int, "lights": int, "missing_frames": int,
             "filters": {"<filter_name or —>": int}, "image_types": {"<type>": int}},
  "metadata": object,                         // observation.json as written ({} when none)
  "quality": {"default": Report|null,         // photometry_quality.json (core's comparison_quality)
              "default_filter": string|null,  // its "filter" key (S57); null: written before
                                              //   0.5.0 (one-filter run, or both bands mixed)
              "by_filter": {"<token>": Report}},   // photometry_quality_<token>.json (S57)
  "warnings": [string],                       // load_session's warnings, verbatim
  "readiness": {"state": "ready"|"warnings"|"blocked",
                "issues": [{"code": string, "level": "error"|"warn"|"info",
                            "message": string, "count"?: int}]},
  "frames": [ReviewFrame],
  "targets": {"object_name": string|null, "chart_id": string|null,    // comparison_chart_id
              "stars": [{"key", "role", "name", "display_name", "auid", "ra_hours",
                         "dec_deg", "source", "mags", "chart_id"}]},
  "curves": [{"key", "role", "name", "filter", "n", "file_name"}],    // summary; points: A69
  "filters": [string], "multi_filter": bool,  // curve filter tokens ("" left out)
  "site_check": HeaderSiteCheck,
  "airmass_source": "csv"|"header",           // which airmass the plots should use (see below)
  "diagnostics": {"file": string|null, "frames": int},   // the run's flight recorder
  "revision": string,                         // changes when any file read changes
  "opened_utc": ISO}
ReviewFrame = {"index": int, "filename": string,
  "path": path|null,                          // the FITS found in the session tree; null: missing
  "image_type": string, "filter_name": string, "filter": string,   // + its token (S49)
  "light": bool,                              // a light frame (light_frames, review.py:61-63)
  "exposure_s": float, "gain": int,
  "timestamp": ISO|null,                      // session.json (exposure start)
  "hfd": float|null, "fwhm": float|null, "star_count": int|null,   // as logged (green px)
  "sky_adu": float|null, "peak_adu": float|null, "eccentricity": float|null,
  "ccd_temp": float|null,                     // header CCD-TEMP (Qt's read_temperature)
  "header": {"date_obs": string|null, "mid_utc": ISO|null, "jd_mid": float|null,
             "airmass": float|null, "altitude": float|null, "azimuth": float|null,
             "software": string|null, "width": int|null, "height": int|null,
             "bayer": string|null}|null}      // null: no file or unreadable header
HeaderSiteCheck = {"state": "ok"|"mismatch"|"unknown", "frames": int,
                   "median_deg": float|null, "max_deg": float|null, "message": string}
```

- The job (`session_open`, resource = the folder, cancellable between
  frames) reads `session.json` with core `load_session(read_temperature=
  False)` (`review.py:102-175`, so every warning text is Qt's), then one
  primary header per frame (stage `"headers"`, `done`/`total` = frames),
  then the curves (stage `"curves"`, A69). A folder without `session.json`,
  or one the core cannot read, fails with `session_invalid` and the core's
  text ("No session.json in …", "Could not read session.json: …",
  "session.json has no frame list"). The result is atomic: a session or an
  error, never half of one (U9). (W7 fix) The cancel flag is also checked
  while the curves are linked (every 500 points and between curves) and
  before the job ends: a cancel during stage `"curves"` ends `cancelled`.
  Each point finds its light frame by bisection (the same frame as Qt's
  linear `nearest_light_frame`, ties to the earliest), not a scan per point.
- (W7 fix) The job's result is `OpenSummary = {"path", "folder", "object",
  "revision", "counts", "readiness"}`, not the ReviewSession: a job's
  result travels in every `job` event and `GET /api/jobs` listing (4.7 MB
  for a 6000-frame session). The client reads `GET /api/review/session`
  once the job is `done` (the cached open, same `revision`).
- `readiness.issues`: `session_warning` (warn, one per core warning, e.g.
  "Missing FITS frame: <name>"), `no_lights` and `no_fits` (error; the
  texts of `readiness_issues`, `review.py:76-82`), `site_mismatch` (warn),
  `flagged_points` (warn, `count` = target points with `zp_outlier`,
  `low_snr` or `no_detection`), `unverified_lock` (warn, W7 fix, `count` =
  target points with `few_anchors` and none of those), `faint_comparisons`
  (warn, S71, `median_snr`: each comparison's median recorder SNR over the
  run, the median of those, below 10; unsaturated records only; with
  release/0.5.0's core the core's value, `OldFileRules.comparison_median_snr`,
  which Qt's Review warns on alike), `unidentified_curve` (warn,
  one per curve file whose star or role is unknown). `state` is `blocked`
  with an error, `warnings` with a warning, else `ready`.
- **Header site check** (X3 on the files, `notes/release_0_5_0.md` "Site
  set but wrong"): for each light frame carrying `RA` (h), `DEC`,
  `ALTITUDE`, `AZIMUTH`, `SITELAT`, `SITELONG` and `DATE-OBS`, the
  direction `horizontal_at` (`sky_geometry.py`) gives for the header site
  is compared with the mount's `ALTITUDE`/`AZIMUTH` (`angle_between_
  directions`, the whole direction). Median above 5° (`SITE_CHECK_TOLERANCE_
  DEG`): `mismatch`, `airmass_source: "header"` and the issue "The site in
  Settings was not where the telescope was during this run (the mount's
  direction is <median>° from the one computed for that site): the curves'
  airmass is wrong; the FITS header AIRMASS (from the mount) is right." The
  owner's RR Lyr 2026-09-25 run is such a run. Otherwise `airmass_source:
  "csv"`. Nothing is rewritten: the CSV keeps its airmass, A69 adds the
  header's beside it.
- (S66, the owner's option b; GUARD: release/0.5.0's core,
  `review.core_rules()`) Whatever the site check says, the curves' `airmass`
  becomes the header AIRMASS of the Argos light whose `DATE-OBS +
  EXPTIME/2` is nearest the point, within 5 s, unless that light's pointing
  is frozen (X1: `RA`, `DEC`, `ALTITUDE`, `AZIMUTH`, `AIRMASS` all those of a
  light 60 s or more before, a lost mount's last poll; such lights are not
  site-checked either); a point without one keeps the CSV's (computed for the
  Settings site). By the core's `apply_old_file_rules` as Qt's
  `load_session_curves` applies it: `CurveSet.airmass_column: "header"` when
  any point took it. The site check stays a warning: on `mismatch` the
  `site_mismatch` issue says "…: fix it in Settings › Observer & site. The
  airmass shown and exported is each frame's FITS header AIRMASS, from the
  mount (S66)." (plus the count of points left with the computed airmass).
  The same rule reads the run's flight recorder (S67, "Curves" below). The
  owner's runs: RR Lyr AMASS 1.033 on its first row (4.088 before; the target
  within 0.00035 of astropy at the site fitted to the mount), XX Cyg 09-07
  and 08-29 within 0.00044 and 0.00009. S78 (GUARD: the release core's
  `fitted_site`): the header AIRMASS is the field centre's, the target's; a
  comparison or check star's curve takes its own airmass, computed for the
  site fitted to the lights' `RA`/`DEC`/`ALTITUDE`/`AZIMUTH` (frozen lights
  left out; 3 lights over 10 minutes at least, rms under 0.1°), else for the
  Settings site the lights recorded when it reproduces the mount's pointing
  (median S66 offset within 0.1°: `settings_site_reproduces`, S78 amended),
  else the header AIRMASS as the target (`OldFileRules.airmass_own_star`,
  `star_airmass_site: "fitted"|"settings"|null`).

### Curves (A69, A70)

```
CurveSet = {"source": Source, "object": string|null, "root": path|null,
            "targets": {…as ReviewSession.targets},
            "curves": [ReviewCurve],
            "filters": [string], "multi_filter": bool,
            "problems": [string],             // per-file problems (identify_curve_file)
            "airmass_source": "csv"|"header", "revision": string,
            "airmass_column": "csv"|"header", // (S66) "header": `airmass` is the header AIRMASS
                                              //   (points without one keep the CSV's)
            "old_file_rules": OldFileRules|null}   // (S66, S67) null before the merge (GUARD)
OldFileRules = {"site_mismatch": bool, "airmass_from_header": int,
                "airmass_computed": int,          // points left with the CSV's airmass (S66)
                "frozen_lights": int,             // X1: lights whose pointing is frozen
                "airmass_own_star": int,          // S78: comparison/check points, own airmass
                "star_airmass_site": "fitted"|"settings"|null,   // S78: computed for
                "no_detection_frames": [{"file", "frame": int, "jd_utc",
                                         "low_snr": [string],   // targets below SNR 3
                                         "zp_outlier": bool}],
                "no_detection_points": int,
                "comparison_median_snr": float|null,     // S71 (faint_comparisons)
                "sigma_syst": {name: [before, after]},   // floors recomputed (S67)
                "messages": [string]}                    // Qt Review's warning lines
ReviewCurve = {"key": string,                 // "<AUID, else display name>@<filter token>" (S49)
               "identity": string,            // the core's identity key (dedup of aliases)
               "role": "target"|"comparison"|"check", "name": string, "auid": string|null,
               "role_source": "column"|"prefix"|"targets"|"default",
               "filter": string,              // token; "" when nothing says (pre-0.5.0 name)
               "filter_source": "name"|"session"|"live"|null,
               "csv": path|null, "file_name": string|null,
               "mags": {band: float}, "catalogue_v": float|null,   // the star in targets.json
               "sigma_syst": float|null,      // the last point's floor
               "exportable": bool, "problem": string|null,         // false: star or role unknown
               "n": int,
               "columns": {                   // n values each; null = empty in the CSV, or NaN
                 "jd_utc", "bjd_tdb", "mag", "mag_err", "formal_mag_err", "sigma_syst",
                 "airmass", "fwhm", "sky_adu", "comps_used", "relative_flux",
                 "relative_flux_err", "relative_comps_used",         // LcPoint, lightcurve.py:39-62
                 "saturated": [bool], "suspect": [bool],
                 "frame": [int|null],         // ReviewSession.frames index (Qt's nearest_light_frame)
                 "frame_dt_s": [float|null],  // jd_utc − that frame's header mid-exposure (s)
                 "header_airmass": [float|null],   // that frame's header AIRMASS (the mount's)
                 "zero_point": [float|null], "zp_rms": [float|null],  // flight recorder (4 dp)
                 "snr": [float|null],         // the star's SNR on that frame (flight recorder)
                 "flags": [[string]]}}        // see below; [] for a clean point
```

- **Session curves** (`GET /api/review/session/curves?path=`): every
  `photometry/*.csv` through core `read_curves_csv` + `identify_curve_file`
  as `load_session_curves` does (`review.py:178-212`): the role from the
  `target_`, `comparison_`, `check_` prefix (S9: a check is a check), the
  star from `targets.json` (AUID suffix, then name), aliases of one target
  merged (the longer curve kept). Both S49 names are read: `{role}_{object}_
  {filter}_{star}.csv` gives the filter token, a pre-0.5.0 `{role}_{object}_
  {star}.csv` none: then `filter` is the token of the session's light frames
  when they all used one filter (`filter_source: "session"`, the run could
  only be that band), else `""`. Points keep file order (time order).
- **Keys**: `<AUID or display name>@<token>` as the live store
  (`curve_key`, S49). `multi_filter` is true when more than one token is
  loaded: label a series "Name [filter]" only then (`series_label`).
- **Flags** (display; nothing is dropped, the AAVSO export decides,
  A77-A78):
  - `suspect` and `saturated` are the CSV's (S56/S58 suspects: draw hollow).
  - `zp_outlier`, `low_snr`: the release's "check your old files" rule for
    S35/S52 (`notes/release_0_5_0.md`) applied from the run's flight recorder
    (`diagnostics/<object>_live_diagnostics.jsonl`, written when
    `diagnostics.enabled`). `zp_outlier`: on a frame where a **target**'s
    ensemble zero point departs more than 1 mag from its run median, every
    star's point of that frame (the zero point does not depend on the
    target's own flux: the frame was measured off the stars, or through
    thick cloud). `low_snr`: the point's own star had an SNR below 3 on that
    frame (no detection), whatever its role. The owner's RR Lyr 2026-09-25
    run has two `zp_outlier` frames (lights `_00053`, `_00176`, S35). No
    recorder: neither flag.
  - `few_anchors` (W7 fix): the release's S56 rule for old files, from the
    same recorder: fewer than 3 `star` records of role comparison or check
    with `snr` ≥ 10, not saturated, on that frame: the lock was not
    verified; every star's point of the frame. Conservative (0.5.0 still
    verifies such a sub within 10 px of a fresh solution, which old files do
    not record): on the owner's files, all 22 frames of XX Cyg 2026-08-29
    and RR Lyr frames 52 and 175 (already `zp_outlier`). Display and
    readiness only (`unverified_lock`); the export decides (A77).
  - `no_detection` (S67, GUARD): on a frame of the recorder where the
    `zp_outlier` rule holds, every star's point, and where a target has an
    SNR below 3, that target's points (the owner's option b: per target), are
    `suspect` (the column) and carry this flag; it is left out of the AAVSO
    export (counted apart, A77) and the curve's `sigma_syst` (with each
    `mag_err`) is recomputed without those points when the file's floor is
    the automatic estimate of its own points (a manual floor is kept). The
    core's `apply_old_file_rules`, as Qt's Review: the owner's RR Lyr run
    loses frames `_00053`, `_00176` (both rules; target `sigma_syst` 0.01657
    → 0.01497), XX Cyg 2026-09-07 `040723Z` frame 20's target point (SNR
    1.6, its zero point normal; 0.2918 → 0.2365). `few_anchors`
    points are never dropped by it (a re-run, S58, verifies them).
  - The client draws `zp_outlier` / `low_snr` points hollow, leaves them out
    of a cell's y range (a point off the range is a chevron on the edge) and
    draws their error bar at half the error ink.
  - `no_frame`: no logged light frame within 60 s of the point.
- **Live** (`GET /api/review/live/curves`): the store of A54 in the same
  shape (`filter_source: "live"`, `frame`/`frame_dt_s`/`header_airmass`/
  `snr` null, `zero_point`/`zp_rms` as A54). Read-only (D3).
- **Import** (`POST /api/review/import-csv`, A70): `read_curves_csv`; the
  target set is `_target_set_of_curve`'s (`analyze_page.py:786-806`: the
  CSV's folder or its parent's `targets.json`, else a live preview's
  `<sessions>/targets/<object>.json`); a one-star CSV takes its role and star
  from `identify_curve_file` (S10: never "target named after the file");
  a multi-curve export keeps its `role` column (`role_source: "column"`);
  a pre-0.5.0 name inside a session (its folder or `photometry/`) takes the
  session's single light filter as A69 (`filter_source: "session"`, read
  from `session.json` alone).
  A curve whose star or role is unknown has `exportable: false` and the
  core's problem text. (S66, S67, GUARD) A run's own CSV (`<session>/
  photometry/*.csv`) gets its session's old-file rules as Analyze's Open
  curve CSV applies them (`apply_old_file_rules_to_file`): `airmass_column`,
  `old_file_rules` and the `no_detection` flag as for the session; a batch
  re-run's CSV or a preview curve is read as written. `422 invalid_csv` with the reason: no valid row
  ("No valid photometry rows in <name>"), a missing column ("<name> has no
  'mag_err' column"), not UTF-8 text, not a CSV.

### Frames (A71-A73)

- **Frame** (`GET /api/files/frame?path=&view=raw`, A71): the first image
  HDU as one binary message in the `/ws/frames` layout, `Content-Type:
  application/octet-stream`; it is **never** published on `/ws/frames` (the
  live image is not disturbed, W3). Any FITS image is displayed
  (`load_fits_frame`, as the v1 Open FITS: integers clipped to 0…65535, float
  data in [0, 1] scaled by 65535, a `(3, H, W)` cube interleaved), within the
  size limits (`400 invalid_fits` beyond, or for a file that is not a FITS
  image). `view` is `raw` only: the colour, R, G, B previews are computed by
  the client from the raw mosaic and `bayer` (`viewer/palettes/cfa.ts`), as
  for live frames. Header: the v1 fields (`seq` counts file frames, not
  `/ws/frames` frames; `source: "file"`) plus `origin: "file"`, `path`,
  `file_name`, `date_obs`, `epoch_utc` (exposure midpoint, S39 rule),
  `bayer` (`BAYERPAT`, else the profile's for a 2-D integer frame, else
  null), `filter`, `image_type`, `object`, `green_shape: [h, w]`, `raw: bool`
  (the pixels are the file's own 16-bit counts; false: converted for
  display, measurements still use the file's values).
- **FITS header** (`GET /api/files/fits-header?path=`, A72):
  `FitsHeader = {"path", "file_name", "text": string, "cards": [{"key",
  "value", "comment"}], "keywords": {"<KEY>": string}}`. `text` is the
  primary header one card per line, `END` last (Qt showed `str(header)`: the
  same 80-column cards run together); `keywords` are `read_fits_meta`'s (`analysis_window.py:
  68-123`, values as strings). `400 invalid_fits` when the file has no
  readable FITS header.
- **Measure star** (`POST /api/files/measure-star`, A73):

```
MeasureStarBody = {"path": path, "x": float, "y": float,   // frame px (numpy convention)
                   "radius"?: int,       // aperture, green px (default imaging.star_radius_px)
                   "snap"?: bool}        // true (default): snap within 6 green px to the peak
                                         //   (measure_star_at's default); false: 2 (re-measure)
StarMeasure = {"found": bool, "message": string|null,
               "x", "y",                 // centroid, frame px
               "x_green", "y_green",     // the core's green-plane centroid
               "fwhm_px", "hfd_px",      // frame px (2 × green)
               "fwhm_arcsec", "hfd_arcsec",
               "scale_arcsec_px": float, // per frame px
               "scale_source": "solution"|"profile",
               "eccentricity": float|null, "snr": float, "peak_adu": int, "sky_adu": float,
               "flux": float, "radius_green_px": int,
               "scale": "raw"|"converted",   // (W7 fix) "converted": a float frame in [0, 1]
                                             //   (Siril, PixInsight) measured × 65535 (Qt: S65)
               "ra_hours": float|null, "dec_deg": float|null,   // through the file's solution
               "ra_text": string|null, "dec_text": string|null}
```

  `snr` is `measure_star_at`'s peak above sky over the sky's σ (a detection
  measure; R2 labels it "Peak/σ"), not the aperture photometric SNR of the
  curves (A69 `snr`): on RR Lyr frame 1 they read 1 090 and 148.

  The numbers are `measure_star_at` (`metrics.py:225-276`) on the file read
  as the Frame Viewer reads it (`read_fits_2d`, `analysis_window.py:54-65`:
  float32, NaN zeroed, a cube averaged), so they equal Qt's. Arcseconds use
  the file's solution scale (its CD matrix) when A74 solved it, else the
  profile's `arcsec_per_green_px` (Qt always used the profile's).
  `found: false` (200) with "No star near (x, y)." when the core finds no
  star-like signal; a position outside the frame is `400 invalid_argument`.

### Solve and catalogue (A74, A75)

- **Solve** (`POST /api/files/solve`, A74; job `file_solve`, resource = the
  file, `409 busy` with `owner` while that file is solving): the green
  plane (`green_plane`, the Frame Viewer's `extract_plane(VIEW_G)` in
  float) solved by ASTAP with `build_solve_settings(live=False)` (120 s,
  whole-sky retry), hinted by the header's `OBJCTRA`/`OBJCTDEC` when present
  (as Observe for an opened file; Qt's Frame Viewer solved blind with the
  scale hint only). Stages `"reading"`, `"ASTAP"`, `"ASTAP at native
  sampling"`, `"ASTAP whole-sky"`. Cancel kills ASTAP at once (Qt could
  not, P28); a cancel that lands as ASTAP answers still ends `cancelled`
  and keeps no solution. A failure ends `failed` / `not_solved` with
  ASTAP's message.

```
FileSolution = {"path": path, "file_name": string,
                "solution": {"ra_hours", "dec_deg", "scale_arcsec_px",   // per frame px
                             "rotation_deg", "mirrored",                 // as Field's Solution
                             "frame_shape": [h, w], "hint": {"ra_hours", "dec_deg",
                             "source": "header"}|null, "solved_utc": ISO, "summary": string},
                "wcs": FrameWcs, "grid": Grid|null}                     // as Field (A43)
```

  The last good solution of a file is kept by the server (keyed by path,
  size and modification time, the 16 newest files) for A73, A75 and `GET
  /api/files/solution`.
- **Catalogue** (`POST /api/files/catalogue`, A75; job `file_catalogue`,
  resource = the file): `409 not_solved` "Identify the field first: the
  catalogue is fetched around a plate solution." without a kept solution.
  The request is the Frame Viewer's (`analysis_window.py:588-629`, the same
  `catalog.*` keys and the 70/30 Gaia/SIMBAD budget as Observe); VSP around
  the session's first target (the `targets.json` of the nearest session
  folder above the file, `analysis_window.py:343-348`), else around the
  field centre named by `OBJECT`. Network: VSX, VSP, Gaia, SIMBAD and NASA
  as configured (`*_allow_network`). Cancel ends the job at once; a late
  answer is dropped. A VSX failure ends `failed` / `lookup_failed`; a
  failed optional source is in `warnings`.

```
FileLayers = {"path": path, "frame_shape": [h, w], "display_mag_limit": float,
              "layers": {"stars", "variables", "galaxies", "nebulae_clusters", "exoplanets",
                         "other_objects", "vsp", "selected"},   // [Marker] as FieldLayers (A47)
              "counts": {layer: int},
              "catalog": {"centre": {"ra_hours", "dec_deg"}, "radius_deg": float,
                          "counts": {"variables", "comparisons", "field_stars",
                                     "named_objects", "exoplanet_hosts"},
                          "limits": {"field_stars": int, "named_objects": int},
                          "warnings": [string]}}
```

  Markers are projected through the file's solution (`project_field`, the
  Observe projection, with no detected-source filter: the Frame Viewer drew
  every source in the frame); Gaia markers carry `g_mag` so the client
  re-filters by `catalog.display_mag_limit` without a new request;
  `selected` is the session's target set with roles.

### Errors (wave 7, sessions and frames)

| HTTP | code | When |
|---|---|---|
| 400 | `session_invalid` | A68/A69 on a folder without a readable `session.json` (the core's text). |
| 400 | `invalid_fits` | A71-A74 on a file that is not a FITS image, or too large to display. |
| 400 | `invalid_argument` | A relative path, a wrong suffix, a `view` other than `raw`, a measure position outside the frame. |
| 403 | `forbidden_path` | A path outside home and the ARGOS data folders. |
| 404 | `not_found` | A missing file or folder; `GET /api/files/solution` for a file never solved (or changed since). |
| 409 | `busy` | A second `sessions_scan`, or a second `session_open` / `file_solve` / `file_catalogue` of the same path (`owner` = its job). |
| 409 | `not_solved` | A75 without a kept solution of the file. |
| 422 | `invalid_csv` | A70: the CSV holds no usable curve (the reason). |

Job errors: `session_invalid` (A68), `not_solved` (A74), `lookup_failed`
(A75), `invalid_fits` (A74, A75).

## Review (wave 7): exports and re-run

Rows A76-A79 on the job model (A80), still `"api": 2` (additive). The
exports call the fixed core writers themselves, `write_aavso` and
`write_curves_csv` (`lightcurve.py`, 0.5.0 with S11, S53 and S60), on the
very `LightCurve` objects `hub.review.curve_set(source)` returns (the
curves the plot shows, points untouched), driven as Qt's Review drives
them: Analyze **Open curve CSV** (`analyze_page.py:737-783`) then the
Photometry window's **Export AAVSO** / **Export measurements**
(`photometry_window.py:338-418`), FILT = `photometry.default_band`, OBSCODE
= `observer.obscode`, CHART = `comparison_chart_id` of the target set. The
re-run is a Qt-free port of the fixed `PhotometryBatchWorker`
(`photometry_batch_worker.py`, 0.5.0: S12, S13, S41, S43, S49, S58, S62
and S63), measuring with the unchanged core (`measure_frame`,
`ApertureTracker`, `anchors_seen`, `estimate_systematic_floor`).

| Method | Path | Body | Returns | Row |
|---|---|---|---|---|
| POST | `/api/review/rerun/plan` | RerunBody | RerunPlan (what a start now would do; never writes) | A76 |
| POST | `/api/review/rerun` | RerunBody | `202 {job_id, job}`, job `rerun`; result RerunResult | A76 |
| POST | `/api/export/aavso/preview` | AavsoBody | AavsoPreview (never writes) | A77 |
| POST | `/api/export/aavso` | AavsoBody + ExportTarget | `202 {job_id, job}`, job `export`; result ExportResult | A78 |
| POST | `/api/export/csv` | CsvBody + ExportTarget | `202 {job_id, job}`, job `export`; result ExportResult | A79 |
| GET | `/api/jobs/{id}/download` | — | an export written for a download (`text/plain` for `.txt`, `text/csv` for `.csv`, attachment) | A78, A79 |

Paths follow the rule of the section above (absolute, inside home and the
ARGOS data folders, else `400` / `403`).

### AAVSO preview (A77) and export (A78)

```
AavsoBody    = {"source": Source,
                "filter": string|null,    // the filter token to report (S53); null: the source's only one
                "keys": [string]|null,    // target curves (ReviewCurve.key); null: every target curve of that filter
                "check_key": string|null, // the check curve for KNAME/KMAG; null: the first check curve of that filter
                "use_check": bool,        // default true; false: KNAME/KMAG "na"
                "obscode": string|null,   // null: Settings observer.obscode
                "filt": string|null,      // FILT; null: Settings photometry.default_band (Q-R2)
                "chart": string|null}     // CHART; null: comparison_chart_id of the source's target set
ExportTarget = {"path": path|null,        // absolute file; null: kept by the server for a download
                "overwrite": bool}        // default false: an existing file is 409 file_exists
AavsoPreview = {"source": Source, "object": string|null,
                "obscode": string, "obscode_set": bool,  // what OBSCODE would be ("" when unset)
                "band": string, "band_source": "request"|"settings",
                "filter": string|null, "filters": [string],   // reported token; tokens of the source
                "band_note": string|null,                     // FILT vs the frames' filter (S11)
                "chart": string, "chart_source": "request"|"targets"|"none",   // "na" when none
                "check": {"key", "name", "kname", "points", "kmag_rows"}|null,
                "targets": [{"key", "name", "points", "rows",
                             "saturated", "no_detection", "suspect", "nonfinite", "undated",
                             "recorder_flagged": [int],     // point indices, see below
                             "unverified_lock": [int]}],    // (W7 fix) S56 rule, see below
                "rows": int,
                "excluded": {"saturated": int, "no_detection": int,   // (S67) no_detection
                             "suspect": int, "nonfinite": int, "undated": int},
                "recorder_flagged": int,           // rows written although the recorder flags them
                "unverified_lock": int,            // (W7 fix) rows on a few-anchor frame (S56)
                "flagged_points": [{"key", "index", "jd_utc", "mag", "mag_err", "flags"}],  // both, named
                "warnings": [{"code": "airmass_wrong_site"|"recorder_flagged"|"unverified_lock",
                              "count": int, "message": string}],   // (W7 fix) shown with the glyph
                "airmass": {"source": "csv"|"header",   // (S66) "header": AMASS is the header AIRMASS
                            "state": "ok"|"mismatch", "message": string|null},
                "notes": [string],                 // the other lines the dialog shows (the
                                                   //   left-out counts, the check, the band note)
                "refusal": {"code", "message", "details"?}|null,   // what A78 would answer now
                "head": string,                    // the file's header and its first 3 rows
                "default_path": path|null}         // <session>/<object>_<filter>_aavso.txt
ExportResult = {"path": path|null, "name": string, "bytes": int, "download": bool,
                "rows": int, "curves": int, "filter": string|null,
                "excluded": {…as AavsoPreview}|null,   // AAVSO only
                "notes": [string]}
```

- **What is written** is `write_aavso(path, curves, obscode=, filt=, chart=)`
  with `curves` = the selected target curves in source order, then the
  check curve: only target-role curves become rows; KNAME/KMAG come from
  the check curve (its ensemble magnitude on the same frame, matched by
  `jd_utc`); `DATE` is JD UTC at mid-exposure, `MTYPE=STD`,
  `CNAME=ENSEMBLE`, `CMAG=na`, `TRANS=NO`, `GROUP=na`, `AMASS` the curve's
  `airmass` column. The preview writes the same call into a temporary
  file and reads it back: preview and export cannot differ.
- **Left out, always, with counts and a note**: saturated points, suspect
  points (cosmic ray or hot pixel, S43/S56/S58 points measured without a
  verified lock), points with a non-finite magnitude or error, and (S60)
  undated points (`jd_utc` not finite or below JD 2 400 000: a pre-0.5.0
  batch re-run wrote JD 0 for a frame without `DATE-OBS`, S13). There is
  no option to include them. (S67) A suspect point flagged `no_detection`
  (`LcPoint.no_detection`, the core's rule from the run's flight recorder)
  is counted apart as `no_detection` and named "N suspect (no detection)"
  in the notes and the export's log line, as Qt's Export AAVSO message.
- **Flight-recorder flags** (A69 `flags` `low_snr`, `zp_outlier`: a target SNR
  below 3, S35's "not a detection", or a zero point more than 1 mag off, S52):
  the fixed Qt export reads the CSV only and writes these points; so does
  A78 while the owner decides (`recorder_flagged` counts them, a
  `warnings` line says "… would be written although the run's flight
  recorder marks them …", `flagged_points` names them). The owner's RR Lyr
  2026-09-25 run has two (lights `_00053`, `_00176`, measured on blank sky
  before S35). (W7 fix) `few_anchors` points (S56's conservative old-file
  rule) are counted apart in `unverified_lock` with their own warning:
  written too, as the fixed Qt writes them (XX Cyg 2026-08-29: all 22).
  (S67, GUARD) With release/0.5.0's core the no-detection points are suspect
  (A69) and left out by the writer, Qt and server alike: `recorder_flagged`
  is then 0 and its warning gone. The `unverified_lock` warning stays and
  points to a re-run (S58), which verifies each such frame with a plate
  solve (owner decision 2026-11-15: the S56 old-file rule over-flags, it
  never drops a row).
- **One filter at a time (S53)**: `filters` are the tokens of the source's
  target and check curves (`ReviewCurve.filter`; a pre-0.5.0 file name
  takes the session frames' filter, else `""`). With more than one, a
  `filter` must be chosen; KNAME/KMAG then come from that filter's check
  curve only. `band_note` warns (export allowed, Q-R2) when FILT does not
  fit the filter: `lp` (a duo-band nebula filter, not a photometric band),
  or a Johnson/Cousins token (`u b v r i`) whose letter is not FILT.
- **Airmass**: AMASS is the curve CSV's `airmass` (Qt's). When the session's
  header site check says `mismatch` (`CurveSet.airmass_source: "header"`,
  the owner's RR Lyr 2026-09-25 run), `airmass.state` is `mismatch` and a
  `warnings` line (`airmass_wrong_site`) says the values were computed for
  the wrong site (the FITS header AIRMASS is right); the export still
  writes the CSV values. (S66, the owner's option b; GUARD) With
  release/0.5.0's core the `airmass` column is already each frame's header
  AIRMASS (`CurveSet.airmass_column: "header"`; a point without one keeps
  the CSV's): the message says "AMASS is each frame's FITS header AIRMASS,
  from the mount (S66)." and, on `mismatch`, "The site in Settings was not
  where the telescope was during this run."; an `airmass_wrong_site`
  warning remains only when points of the run were left with the airmass
  computed for that wrong site (`count`: `OldFileRules.airmass_computed`).
  Qt's Review and Analyze write the same bytes.
- **#SOFTWARE, #OBSTYPE, CHART** (S64, S68): `#SOFTWARE=Argos v<version>`
  (`argos.SOFTWARE_ID`, the writer's default; the server passes no
  `software=`). `#OBSTYPE=CCD`: the AAVSO Extended File Format reports a
  CMOS camera as CCD. CHART is the comparisons' single VSP chart
  (`comparison_chart_id`); a VSP answer now names the chart of comparisons
  kept from before 0.4.2 (`TargetService.backfill_chart_ids`, S68), so new runs
  write it; older runs' `targets.json` keep `na`.
- **Refusals** (`refusal` in the preview, the same `409` from A78 before
  any job starts): `obscode_unset` ("Set your AAVSO observer code in
  Settings first: it is stamped on every AAVSO report.", Q-R2: empty or
  `XXX`, never written silently), `no_target` ("No target points to
  export."), `multiple_filters` (`details.filters`; "These curves are in 2
  filters (b, v), and an AAVSO report has one band: choose one."),
  `curve_unidentified` ("The star or role of this light curve is unknown —
  no AAVSO export.", S10; `details.problems`), `unknown_curve` (a key or
  `check_key` the source does not have, or `check_key` of another role or
  filter), `no_rows` (every point left out), `invalid_band` (FILT empty,
  longer than 5 characters or not letters and digits). A78 adds
  `file_exists`, `protected_path` and the path errors.
- (W7 fix) **Protected files**: A78 and A79 answer `409 protected_path`
  ("… holds the session's own data: an export never replaces it. Choose
  another file name or folder."), whatever `overwrite` says, for a
  destination that is one of the export's own source CSVs, or inside an
  Argos session (a folder holding `session.json`) its `session.json`,
  `targets.json`, or anything under `photometry/`, `photometry_rerun_*/`,
  `lights/`, `diagnostics/`, `darks/`, `flats/`, `biases/`. The file is
  written beside its destination (`.<name>.<job>.part`) and renamed over
  it: a failed write never truncates the file it replaces.
- **The job** (`export`, resource = the destination or the download, not
  cancellable, about a second) writes the file and logs "AAVSO export:
  <rows> observations written to <name>. Left out: …" (W7 fix: plurals
  spelled out). A write error
  ends `failed` / `write_failed` with the OS text. With `path: null` the
  file (`<object>_<filter>_aavso.txt`) is kept for `GET /api/jobs/{id}/
  download` as long as the job (10 min).

### CSV export (A79)

```
CsvBody = {"source": Source, "keys": [string]|null,   // null: every curve with points
           "filter": string|null}                     // null: the source's only filter
```

`write_curves_csv(path, curves)` (`lightcurve.py`: one lossless file,
columns `star_id, role, name, auid` + the 15 point columns), curves in
source order; Qt's **Export measurements**. Refusals (`409`): `no_points`
("No measurements to export."), `unknown_curve`, `multiple_filters` (S61:
the file has no filter column, so two filters' curves of one star would
be read back as one curve: export one filter at a time). Default file
`<session>/<object>_<filter>_photometry.csv`. Same job as A78.

### Re-run photometry (A76)

```
RerunBody   = {"session": path,             // the session folder (or a folder of FITS frames)
               "frames": path|null,         // a frames folder; null: the session's (lights/ …)
               "targets": "session"|"live", // default "session": <session>/targets.json
               "reference": "solve"|"live", // default "solve": ASTAP on reference_frame
               "reference_frame": path|null,   // null: the first light frame in time order
               "diagnostics": bool|null}    // null: Settings diagnostics.enabled
RerunPlan   = {"session": path, "frames_dir": path, "frames": int,
               "frame_names": {"first": string|null, "last": string|null},
               "left_out": {"calibration": int, "other_object": int,
                            "outside_lights": int, "duplicates": int},   // S62, S63
               "stars": {"object": string, "target": int, "comparison": int, "check": int},
               "targets": "session"|"live",
               "reference": {"mode": "solve"|"live", "frame": string|null,
                             "live_available": bool, "astap": bool},
               "params": {"aperture_fwhm_mult", "aperture_min_px", "annulus_in_px",
                          "annulus_out_px", "egain", "read_noise_e", "sat_adu",
                          "band", "min_comps", "track_apertures"},
               "site_set": bool,            // no site: no airmass and no BJD_TDB (never 0/0)
               "out_dir": path,             // the folder a start now would create
               "refusal": {"code", "message"}|null}
RerunResult = {"out_dir": path, "folder": string, "source": Source,   // open it in Review
               "frames_total": int, "frames_done": int, "frames_skipped": int,
               "frames_resolved": int, "frames_unanchored": int, "frames_unverified": int,
               "frames_rotation_solved": int,   // S69 (a): re-solved, the field turned > 2°
               "stars_off_centre": int,         // S69 (b): comparison/check rows > 1 px off
               "frames_rotation_unsolved": int, // S69 (a): such a re-solve failed (tracker kept)
               "frames_no_target_point": int,   // S69 (b): every comparison off-centre
               "frames_no_detection": int,      // S67: points flagged no_detection (suspect)
               "frames_header_airmass": int,    // S66: airmass = the frame's header AIRMASS
               "frames_site_wrong": int,        // S66: header says the Settings site > 5° off
               "left_out": {…as RerunPlan},
               "rotation_deg": float, "shift_px": float,
               "series_fwhm_px": float|null, "aperture_px": float,
               "reference": {"mode", "frame": string|null, "ra_hours", "dec_deg",
                             "scale_arcsec_px": float|null},     // per frame px
               "curves": [{"key", "role", "name", "auid", "filter", "points", "file"}],
               "check_rms": [{"key", "filter", "rms_mag", "n"}],
               "notes": [string]}           // the Qt log lines of _on_batch_done, same texts
```

- **Frames** (S12, S62): `discover_light_frames` — `.fit`, `.fits`, `.fts`
  (any case) in the folder, else in its subfolders (a session root holds
  `lights/`); a frame whose `IMAGETYP` names a calibration type is left
  out, and so is one whose `OBJECT` names another object than the target
  set's (S62; compared without case, spaces or underscores). In the subfolder
  search, an Argos session folder's frames are its `lights/` only and a link
  to a frame already listed is that frame (S63: star_var_script's Siril
  `process/` beside the lights holds a link to each light and a registered
  copy; the owner's RR Lyr 2026-09-25 folder gave 585 frames for 195
  lights before). Ordered by `DATE-OBS`, undated last. A frame without a usable `DATE-OBS` is skipped
  and counted (`frames_skipped`): an undated point would carry JD 0 (S13).
  (W7 fix) The scan (one header per frame, about 4 ms each) is kept while
  no FITS file below the folder changes (name, size, modification time):
  the dialog's plans and the start cost one scan (23 s for 6000 frames
  before, past the client's timeout; the client now waits 60 s for a plan,
  a start or an AAVSO preview). A file announced larger than the display
  limits is unreadable (skipped, as a corrupt one) and refused as a
  reference frame (`invalid_fits`), from its header, before its pixels are
  read.
- (W7 fix) **Inputs**: a `session` that is a file (other than
  `session.json`) is `400 invalid_argument` "<name> is not a session
  folder" (as A68); a `reference_frame` without a FITS suffix is
  `400 invalid_argument`.
- **Stars**: the session's `targets.json` (`TargetSet.load`) or the live set
  (A51); at least one target and one comparison, else `409 no_targets` /
  `409 no_comparisons` (Qt's texts). S77 (GUARD): the set's VSX/VSP stars
  without a proper motion take their Gaia DR3 one at the start
  (`gaia_sources_for_set`, cached, online when Settings' field-star catalogue
  is; a failure is a WARN and the catalogue positions; each cone gives up after
  5 s, the stars after a failure are read from the cache only, and the job's
  cancel stops the lookup between stars; the job's message reads "proper
  motions (Gaia DR3)" meanwhile), every frame measures the set at its date, and
  the `targets.json` written beside the CSVs carries the motions (a
  `proper_motions` event in the recorder). S78 (GUARD): a comparison or check
  star's airmass is its own, for the site fitted to the frames' header
  pointing, else for the request's Settings site when it reproduces that
  pointing within 0.1° (S78 amended; GUARD `settings_site_reproduces`), else
  the header AIRMASS (a `star_airmass_site` event); the target's stays the
  header AIRMASS (S66). S74: each star's scintillation takes the airmass its
  row gets (GUARD: `measure_frame(star_airmass=…)`). S82: a frame's `OBJECT`
  matches the set's object without SIMBAD's identifier prefixes ("V* XX Cyg" is
  XX Cyg). S81: a star whose aperture or 12 px sky annulus runs off the frame is
  not measured (no row), in every path.
  S80: the recorder's `tracking` record counts `anchors_inconsistent`.
- **Reference**: `solve` plate-solves the reference frame's green plane
  with ASTAP (`build_solve_settings(live=False)`, hinted by `OBJCTRA` /
  `OBJCTDEC`, as A74), stage `"solving the reference"`; a failure ends the
  job `failed` / `not_solved`. `live` uses the field's current solution
  (A43; `409 not_solved` "Plate-solve the live frame before a batch
  re-run." without one). The S43/S58 re-solves of a frame use the live
  settings around the reference's centre without the whole-sky retry
  (`batch_frame_solver`), through the cancellable ASTAP runner.
- **Measurement** is the worker's, frame by frame: the series FWHM on the
  first readable frame (one aperture for the run), the tracker on the
  comparisons and checks, the S43 lock check (half the anchors seen at SNR
  5), a re-solve when the field is lost, S58's verification of a lock on 1
  or 2 anchors (a solution of this frame or the previous one within 10 px,
  else a re-solve, else the points flagged suspect), each frame's own
  e-/ADU (`frame_egain`, S41, S73; the fallback is Settings' table at the
  Camera gain, the profile's measurement, else the sensor reference, as
  `_engine_egain`; S74's exposure, airmass and height from each frame's header,
  GUARD: `with_frame`; S70, GUARD with
  S69: in the tracker's anchors and the lock checks too, not only in the
  measurement), S69 (GUARD: the release core): a re-solve once the tracked
  rotation since the solution exceeds 2° (a failed one retried only after 2°
  more; `re_solved_rotation` / `rotation_not_re_solved` events, the count
  `frames_rotation_solved` and an `info` note "the field turned more than 2°
  since its solution on N frames; each was re-solved (S69)"), and each
  comparison and check star more than 1 px from its aperture centre left out
  of its frame's ensemble, its row flagged suspect (the count
  `stars_off_centre`, a `warning` note, the frame's `tracking` record's
  `off_centre`; the anchors S58 counts are those centred), JD UTC at
  mid-exposure (`DATE-OBS` + `EXPTIME`/2), BJD_TDB and airmass for the
  Settings site (none without a site; S66, the owner's option b, GUARD: an
  Argos frame with a header AIRMASS takes it, the mount's, unless its
  pointing is frozen (X1), whatever the site; `frames_header_airmass` and
  an `info` note "the airmass of N frames of M is the FITS header AIRMASS
  …"; a frame whose header puts the mount more than 5° from the direction
  computed for the Settings site counts in `frames_site_wrong`, one WARN per
  run and a `warning` note "on N frames the site in Settings was not where
  the telescope was …"; both counts as Qt's `BatchResult` and the recorder's
  `batch_end`), S67 (GUARD) at the end of the run (a target below SNR 3: its
  points; a zero point more than 1 mag from the run's: every point of the
  frame; flagged `no_detection`, suspect, out of `sigma_syst`;
  `frames_no_detection`, a `warning` note, a `no_detection` event), S71
  (release `DiffResult.suspect`: the comparison holding over half the weight
  contradicted by two others or more, the point suspect, its note in the
  `ensemble` record), S69's failed re-solves for rotation
  (`frames_rotation_unsolved`, a `warning` note; the solve failure's own
  "its points are flagged" line is not said for them) and frames without a
  target point (`frames_no_target_point`), one curve per (star, filter)
  (S49), the systematic floor per curve over the points measured with the
  field. Progress: `done`/`total` = frames handled / frames, `message` =
  the frame's name, stage `"measuring"` (`"re-solving"` while ASTAP runs).
- **Output**: a **new** folder `<session>/photometry_rerun_<YYYYMMDDTHHMMSSZ>`
  (`rerun_output_dir`; `-2`, `-3`… when that second's folder exists; W7 fix:
  inside the session also when `frames` names another folder, the frames'
  folder only when `session` holds no `session.json`), never
  another run's files; it holds `{role}_{object}_{filter}_{star}.csv` per
  curve (the 15-column CSV), the `targets.json` measured with and, when
  diagnostics are on, `<object>_diagnostics.jsonl`. It is read in Review as
  `{"kind": "import", "path": <one CSV of it>}` (its `targets.json` sits
  beside), and `source` names its target CSV.
- **Cancel** (`DELETE /api/jobs/{id}`) is honoured between frames and kills
  a running ASTAP at once. A cancelled run writes no CSV (a partial run
  replaces nothing, Qt's rule); its folder is removed unless diagnostics
  were written into it. The job ends `cancelled` (`result: null`); its
  `message` and the log say "Cancelled after <n>/<total> frames: no curve
  saved", plus "; the per-frame notes are kept in <folder>/" when the
  diagnostics stay (the job strip shows that message, not the last frame's
  name). A cancel while the reference is being identified says "Cancelled
  while identifying the reference frame: no curve saved" (W7 fix).
- One re-run at a time per session (`409 busy`, `owner` = its job). The
  re-run never touches the live photometry, its tracker or its curves
  (S59).

### Errors (wave 7, exports and re-run)

| HTTP | code | When |
|---|---|---|
| 409 | `obscode_unset`, `no_target`, `no_rows`, `multiple_filters`, `curve_unidentified`, `unknown_curve`, `invalid_band` | A77 refusal, A78 before the job |
| 409 | `no_points`, `unknown_curve`, `multiple_filters` | A79 before the job |
| 409 | `file_exists` | A78, A79: the destination exists without `"overwrite": true` |
| 409 | `protected_path` | A78, A79 (W7 fix): the destination is a source of the export or a session's own data (see "Protected files") |
| 400 | `invalid_argument` | A76 (W7 fix): `session` is a file; `reference_frame` is not a FITS file |
| 409 | `no_frames`, `no_targets`, `no_comparisons`, `not_solved`, `astap_missing` | A76 before the job |
| 409 | `busy` | A second re-run of the same session, or an export to a destination being written |

Job errors: `write_failed` (A78, A79), `not_solved` (A76 reference solve),
`invalid_fits` (A76: the reference frame is unreadable or too large),
`rerun_failed` (A76, the worker's exception text).

## Desktop app (wave 8): shutdown, reveal, the shell's stdin

Rows A7 and A12 of `web/spec/README.md` §7 and the two start-up flags the
Tauri shell passes (`web/src-tauri/src/sidecar.rs`). Still `"api": 2`
(additive). Module: `argos/server/desktop.py`.

| Method | Path | Body | Returns | Row |
|---|---|---|---|---|
| POST | `/api/app/shutdown` | `{"force": bool}` (optional, default `false`) | `202` ShutdownStarted; `409 busy` with `what` | A7 |
| POST | `/api/fs/reveal` | `{"path": "<absolute path>"}` | `{"path": "<resolved path>", "method": string}` | A12 |

New WebSocket event `shutdown` (a snapshot: the newest stage is enough).
AppInfo gains `"desktop": bool`.

### Started by the desktop shell (`--desktop`, `--exit-on-stdin-eof`)

The shell starts the frozen server as `argos-server --host 127.0.0.1 --port
0 --desktop --exit-on-stdin-eof`, its stdin a pipe the shell keeps open and
never writes to, and reads `ARGOS_PORT` / `ARGOS_TOKEN` (see Launching).

- `--desktop`: the server was started by the desktop shell. AppInfo says
  `"desktop": true` (the UI offers Quit and Reveal only then) and
  `POST /api/fs/reveal` works; without it the route is
  `403 desktop_only`. Nothing else changes.
- `--exit-on-stdin-eof`: a daemon thread reads stdin until end of file,
  then sends the server process SIGTERM, the graceful path of Launching (a
  run stopped, jobs cancelled, devices released, the keep-awake assertion
  released; exit status −15). The pipe closes however the shell ends (Quit,
  a crash, `kill -9`), so the server never outlives it. SIGTERM is sent
  only once uvicorn's signal handlers are installed (an earlier end of file
  waits for them), so even a stdin at end of file from the start
  (`/dev/null`) takes the graceful path: that server stops right after
  start-up. The server logs "Standard input closed (the desktop shell is
  gone): shutting down." Without the flag, stdin is never read.

### Shutdown (A7)

`POST /api/app/shutdown` with `{"force": false}` (or no body):

- Something is busy (see below): `409 busy`, nothing is stopped; the
  error carries `what: [BusyItem]` and a message listing the same texts.
- Nothing is busy, or `"force": true`: `202` ShutdownStarted; the stages
  below run on a server thread, each announced by a `shutdown` event. After
  the last one, a server started by the CLI exits with status **0**
  (uvicorn closes the WebSockets, 1012 or 1001). An in-process server
  (tests) runs the same stages and stays.
- During the shutdown, a second `POST /api/app/shutdown` answers `202`
  with the same record (`forced` of the first), and every other `POST`,
  `PUT`, `PATCH` or `DELETE` is `503 shutting_down`; `GET` routes answer
  while the process lives.

```
BusyItem = {"kind": "run"|"exposure"|"slew"|"job"|"write",
            "text": string,              // one sentence, shown as is in the Quit dialog
            "job_id": string|null,       // kind "job" or "write" from a job (A80)
            "job_kind": string|null}
ShutdownStarted = {"state": "shutting_down", "forced": bool,
                   "what": [BusyItem],   // what was busy when it started
                   "stages": [{"id": string, "label": string}],
                   "budget_s": 60}
ShutdownEvent = {"type": "shutdown", "stage": string, "label": string,
                 "index": int,           // 1-based, of "count"
                 "count": int, "forced": bool, "budget_s": 60, "t": ISO}
```

What counts as busy, in the order of `what` (port of P39: Qt quit stopped
these silently, `acquisition_engine.py:1621-1622`):

| kind | When | text (examples) |
|---|---|---|
| `run` | A sequence is active (`waiting`, `running`, `pausing`, `paused`, `autofocus`, `stopping`) | "A sequence is running: SS Cyg, 34 of 120 frames." · "A sequence is paused: SS Cyg, 34 of 120 frames." · "A sequence waits for its start time: SS Cyg." · "A sequence is stopping: SS Cyg."; without an object name the count comes first: "A sequence is running: 0 of 10 frames (no object name)." · "A sequence is stopping." |
| `exposure` | Outside a run: the camera exposes or downloads, live view runs, a Take shot waits for its frame, an autofocus runs | "The camera is exposing (30 s)." · "The camera is downloading a frame." · "Live view is running." · "A Take shot waits for its frame." · "Autofocus is running." |
| `slew` | The mount slews (GoTo, Centre, Park) or an axis is jogged | "The mount is slewing." · "The mount is being jogged." |
| `job` | Every active job (A80) that is not a write: `discovery`, `site_search`, `field_solve`, `file_solve`, `file_catalogue`, `sessions_scan`, `session_open`, any later kind | "Plate-solving the frame." · "Searching the network for devices." |
| `write` | A Take-shot FITS handed to the save thread and not yet written; the jobs that write files: `export`, `support_bundle`, `rerun` | "A FITS file is being written." · "Writing an export file." · "Re-running photometry (12 of 340 frames)." |

The camera and an autofocus that belong to the run (camera owner
`sequence`, a mid-run autofocus) are part of its `run` item, not listed
again. A filter-wheel turn or a focuser move (seconds, harmless to cut)
does not count.

Stages, in order (port of `Shell.closeEvent` `shell.py:611-625`: the engine
shutdown `acquisition_engine.py:1607-1650`, `DeviceSession.shutdown`
`device_session.py:822-831`; the server's `Hub.shutdown`), each bounded:

| # | `stage` | `label` | What it does | Bound |
|---|---|---|---|---|
| 1 | `sequence` | Stopping the sequence | Stops a run (`reason: "shutdown"`: the sub in progress is discarded, the saved subs stay, no wrap-up), then releases the keep-awake assertion | 15 s + 4 s |
| 2 | `services` | Stopping background tasks | Attention rules, field and live photometry workers, every job cancelled and awaited, the network monitor, the Stellarium bridge | 3 s (jobs) |
| 3 | `devices` | Closing the equipment connections | An autofocus stopped (the focuser back to its start), then camera (exposure aborted), mount (jogging axes stopped first), filter wheel, focuser disconnected | 5 s per thread |
| 4 | `files` | Finishing file writes | The frame-metrics worker; a FITS being written is finished, never cut; the private download folder removed | one write |
| 5 | `exit` | Stopping the ARGOS server | Sent last; the process exits about 0.3 s later | — |

`budget_s` is the whole bound: a CLI server still in its stages after 60 s
logs an ERROR naming the stage and ends its process at once (exit status
70); the OS then drops its device sockets and the keep-awake helper, which
is tied to the server's pid. The shell keeps its own SIGTERM, then
SIGKILL, for a server that is still there after that: when the app exits
(Quit with no UI to ask, SIGTERM / SIGINT / SIGHUP to the shell, the end of
the UI's quit), it sends SIGTERM and waits up to 65 s (the 60 s bound plus a
margin, its window already hidden) before it SIGKILLs the server's process
group, so a slow real mount is never cut off mid-stop. "Quit now" on a stuck
scrim (past 20 s) asks the shell for the short path instead (`argos://quit`
`{now: true}`: SIGTERM, SIGKILL 2 s later). Whenever the server process
ends, the shell sweeps its process group (helpers such as `caffeinate` or a
solver) before reaping it.

The same `Hub.shutdown` runs, once, for every way out: this route,
SIGTERM, SIGINT, stdin end of file (the uvicorn lifespan), whichever comes
first; a second caller waits for the first to finish.

### Reveal (A12)

`POST /api/fs/reveal` with `{"path": "<absolute path>"}` shows a file or a
folder in the OS file manager, selected in its folder: macOS `open -R`
(Finder); Linux the freedesktop `org.freedesktop.FileManager1.ShowItems`
through `dbus-send`, else `xdg-open` on its folder (nothing selected);
Windows `explorer /select,`. The answer names the `method` (`"open -R"`,
`"FileManager1"`, `"xdg-open"`, `"explorer"`). The server waits up to 5 s
for the command's answer; it never opens or runs the file itself. Uses:
the support bundle just written (M15), an export, a run folder, the log
(`paths.log_file` of AppInfo: the log folder opens with `argos.log`
selected).

- Only a server started with `--desktop` (`403 desktop_only`): a browser
  page must not make the server open windows on the computer it runs on.
- The path is checked as in [File listing](#file-listing-a11): absolute
  (`400 invalid_argument`), resolved and inside the allowed roots (home,
  the data folders, the config and log folders; `403 forbidden_path`),
  existing (`404 not_found`).

### Version

`/api/health`, AppInfo and the log's start line report
`argos.__version__` (`argos/__init__.py`), the one version source: the
frozen sidecar, the `.app` (`tauri.conf.json`, `Cargo.toml`) and the
`.dmg` follow it.

### Errors (wave 8)

| HTTP | code | When |
|---|---|---|
| 409 | `busy` | `POST /api/app/shutdown` without `force` while something is busy; `what` lists it |
| 503 | `shutting_down` | Any `POST`, `PUT`, `PATCH` or `DELETE` but the shutdown route once a shutdown started |
| 403 | `desktop_only` | `POST /api/fs/reveal` on a server started without `--desktop` |
| 400 / 403 / 404 | `invalid_argument` / `forbidden_path` / `not_found` | `POST /api/fs/reveal`: relative path / outside the allowed roots / missing |
| 502 | `reveal_failed` | The file manager command failed or could not start (its message) |

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
| `{"type": "attention", …AttentionState}` | Wave 6b. Every change of the attention list (raised, updated, reopened, cleared, acknowledged); once to a client that connects. A snapshot. |
| `{"type": "shutdown", …ShutdownEvent}` | Wave 8. Each stage of a shutdown started by `POST /api/app/shutdown`, the last one `exit`. A snapshot. |
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
- **Replay** (wave 6a). `--sim-replay DIR` plays a folder of real FITS
  copies instead of the synthetic sky (see "Simulator replay source").
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
| A62-A64 | Wave 6a: `GET /api/sequence`, `POST /api/sequence/start` (`start_at_utc`, Q-P2) / `pause` / `resume` / `stop`, `sequence` event and `status.sequence`, `GET /api/sequence/preflight`; the mount interlock (`409 run_active`, `pause_run`), the geometry lock (S15), `frame_saved` of a run, `--sim-replay` |
| §7 (6b) | Wave 6b: `attention` event, `GET /api/attention`, `POST /api/attention/{id}/ack` and `/ack-all`, config category `alerts`; `status.keep_awake` and the preflight `sleep` row; `GET /api/sequence/wrapup`, `POST /api/sequence/calibration-plan`; `sequence.autofocus`, `autofocus_passes`, `wrapup` |
| A67-A75 | Wave 7 (Review): `POST /api/sessions/scan` (job `sessions_scan`), `POST` / `GET /api/review/session` (job `session_open`), `GET /api/review/session/curves`, `GET /api/review/live/curves`, `POST /api/review/import-csv`, `GET /api/files/frame` (not on `/ws/frames`), `GET /api/files/fits-header`, `POST /api/files/measure-star`, `POST /api/files/solve` (job `file_solve`), `GET /api/files/solution`, `POST /api/files/catalogue` (job `file_catalogue`); the Source model |
| A7, A12 | Wave 8 (desktop): `POST /api/app/shutdown` (`409 busy` with `what`, stages, `shutdown` event, `503 shutting_down`), `POST /api/fs/reveal` (`--desktop` only), `--exit-on-stdin-eof`, AppInfo `desktop`; keep-awake `held` from the run's first `status` |
