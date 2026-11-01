# ARGOS server protocol — API v1

The contract between the headless Python server (`argos.server`) and the web
front-end. `GET /api/health` reports `"api": 1`; any breaking change to what
follows bumps that number.

## Launching

```
.venv/bin/python -m argos.server [--host 127.0.0.1] [--port 8742] [--simulator] [--dev-token TOKEN]
```

| Flag | Meaning |
|---|---|
| `--host` | Interface to bind. Default `127.0.0.1`; anything else logs a warning. |
| `--port` | TCP port. Default `8742`; `0` lets the OS choose a free one. |
| `--simulator` | Connect the built-in simulator during startup. |
| `--dev-token` | Fixed token for development. Without it the token is random per launch (`secrets.token_urlsafe(32)`). |

Once the socket is bound and listening, stdout carries exactly two lines, in
this order, for a supervising process such as the future Tauri sidecar:

```
ARGOS_PORT=8742
ARGOS_TOKEN=<token>
```

Logs, uvicorn's access log included, go to stderr, with any `token=…`
redacted. SIGINT and SIGTERM shut down gracefully: the exposure is
cancelled, worker threads are joined, devices are disconnected and
WebSockets are closed (code 1012 from uvicorn, or 1001 from the server).
uvicorn then re-raises the signal, so a clean SIGTERM exit has status
−15 (143 in a shell), not 0. A Ctrl-C (SIGINT) exits with status 0 and no
traceback. A `--dev-token` shorter than 16 characters draws a warning on
stderr: it is guessable, for development only.

At startup the CLI reads `~/.argos/config.json`, as the Qt app does, to
activate the configured telescope profile. That profile supplies
`sensor.bayer` in Alpaca mode.

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
  `tauri://localhost` and `http://tauri.localhost`. CORS does not apply to
  WebSockets, so the server checks their `Origin` header against the same
  list. A disallowed origin gets close code **4403**. Clients that send no
  `Origin`, such as curl, tests or a supervisor, are authenticated by the
  token alone.
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

## Errors

Every 4xx and 5xx response has this body:

```json
{"error": {"code": "<snake_case>", "message": "<human text>"}}
```

| HTTP | code | When |
|---|---|---|
| 400 | `invalid_argument` | Body fails validation: wrong type, out of range, unknown field, relative path, wrong file suffix. Request bodies are strict, so `"2"` is not a number, `80.0` is not an integer gain and `1` is not a boolean. |
| 400 | `invalid_fits` | The file exists but is not a displayable FITS image. |
| 400 | `invalid_argument` | Also `open-fits` on a path the OS refuses to examine (name too long, unreadable directory). |
| 401 | `unauthorized` | Bad or missing token. |
| 403 | `forbidden_host` / `forbidden_origin` | Request for a foreign `Host` name, or from a foreign `Origin` (see Security). |
| 404 | `not_found` | Unknown route, or `open-fits` on a missing file. |
| 405 | `method_not_allowed` | Wrong HTTP method on a known route. |
| 409 | `not_connected` | Camera or mount command with no device connected. |
| 409 | `busy` | Exposure requested while the camera exposes, downloads, is live, or is still stopping. Also returned by `POST /api/connection` while connected with different parameters. |
| 409 | `parked` | `goto` or `tracking` on a parked mount. |
| 409 | `not_live` | `PATCH /api/camera/live` while live view is not running. |
| 409 | `not_connected` | Also a mount command whose session ended (disconnect) while it ran: its result is discarded. |
| 500 | `internal_error` | Any unexpected failure; the traceback is in the server log. The answer keeps the CORS headers, so the browser can read it. |
| 502 | `connection_failed` | The device could not be reached or refused to connect. The connection state becomes `error`. |
| 502 | `device_error` | A connected device refused a command or stopped answering. |

## HTTP routes

Bodies and responses are JSON. All routes except health need the token.

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/health` | — | `{"ok": true, "version": "0.4.2", "api": 1}` |
| GET | `/api/status` | — | `{"connection": ConnectionState, "camera": CameraState, "mount": MountState}` |
| POST | `/api/connection` | `{"mode": "simulator"}` or `{"mode": "alpaca", "host": "<ip>", "port": <int>}` | ConnectionState |
| DELETE | `/api/connection` | — | ConnectionState. Idempotent. |
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

Connection behaviour:

- `POST /api/connection` blocks until the devices answer, which takes a few
  seconds on Alpaca. Meanwhile `/ws/events` shows `connecting`.
- Posting the same parameters again while connected returns the current
  state. Posting different ones returns `409 busy`; disconnect first.
- In `alpaca` mode the mount connects first, as in the Qt app (its connect
  syncs the mount clock), then the camera. Both must succeed.

Coordinates are ICRS/J2000, like everywhere in ARGOS. In Alpaca mode the
conversion to the driver's frame (topocentric-of-date on the Seestar) is
done by `argos.core.alpaca.telescope.Telescope`.

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
```

- A single capture goes `exposing` → `downloading` → `idle`. A live view
  stays `live`, and `last_frame_seq` increases with every frame.
- `last_frame_seq` is the `seq` of the newest frame published on
  `/ws/frames`, whether it came from a capture, a live view or a file.
- `sensor.bayer` is `null` for the mono simulator. For a Seestar it is the
  active hardware profile's CFA pattern, for example `"GRBG"`, and frames are
  raw mosaics with `channels: 1`.
- While disconnected, the mount record is a placeholder (`idle`, zero
  coordinates, null alt/az). Check `connection.state` before showing it.
- `target` is the last GoTo target. It survives `stop`, is cleared by
  `park`, and is reset on disconnect.

## WebSocket `/ws/events?token=…` (server → client, JSON text)

| Message | When |
|---|---|
| `{"type": "status", "connection": …, "camera": …, "mount": …}` | Immediately on connect, then on every state transition: connection change, any camera change, or a mount change of `state`, `tracking`, `pier_side` or `target`. |
| `{"type": "camera", "camera": CameraState}` | On every camera change, including each new frame in live view. |
| `{"type": "mount", "mount": MountState}` | Telemetry while connected: every 0.25 s for the simulator (4 Hz) and every 2 s for a Seestar, the Qt app's polling period. |
| `{"type": "log", "level": "info"\|"warning"\|"error", "message": string, "t": "<ISO 8601 UTC>"}` | Server events, plus WARNING-and-above records from `argos.core`, such as Alpaca driver warnings (core INFO, logged on every exposure, stays in the server log; a core message repeated within 60 s is sent once). Right after the first `status`, a new client receives the last 200 log lines, oldest first, so a page opened mid-session shows what happened before; a client that reconnects drops exact repeats of `(t, level, message)`. |

A camera change therefore sends both a `camera` message and a `status`
message. Coordinate changes alone send only `mount`.

Messages arrive in order. A client that keeps up sees every transition,
for example `connecting` before `connected`, or `exposing` → `downloading`
→ `idle`.

A slow client never makes the server buffer without bound. Once 256
messages are pending for a client, its backlog is compacted: only the
newest snapshot of each type (`status`, `camera`, `mount`) is kept, then
the oldest log lines are dropped. A lagging client loses history, never the
current state. Every snapshot is complete, so a client can always replace
its state with the latest one it received.

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
