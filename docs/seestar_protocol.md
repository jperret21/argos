# Seestar S30 Pro — Protocol & Control Reference

> Synthesized from: `seevar-main/dev/logic/*.MD`, `seestar_alp` source code,
> and real-device testing (firmware 7.18 / fw_ver_int ~2706+, April 2026).

---

## 1. Hardware Facts

| Property | Value |
|----------|-------|
| Model | ZWO Seestar S30 Pro |
| Sensor | Sony IMX585 |
| Resolution | **3840 × 2160** (width × height) |
| Pixel size | 2.9 µm |
| **Bayer pattern** | **GRBG** ← critical for photometry (NOT RGGB) |
| Science channel | Green (G) — densest sampling in Bayer |
| AAVSO filter code | TG (untransformed Bayer green) |
| Optics | 160 mm f/5.3, quadruplet APO |
| Pixel scale | 3.74 arcsec/pixel |
| Field of view | ~4.6° (276 arcmin) |
| Mount type | Alt-Az |

---

## 2. Port Architecture

| Port | Protocol | Status | Purpose |
|------|----------|--------|---------|
| **32323** | HTTP Alpaca REST | **Active — primary** | All hardware control |
| **4700** | JSON-RPC TCP | **Active — jogging only** | `scope_speed_move` (no Alpaca equivalent) |
| **4720** | UDP | Active | `scan_iscope` handshake before port 4700 TCP |
| 32227 | UDP | Unreliable on S30-Pro | Alpaca discovery broadcast |
| 4800 | — | Does not exist | — |
| 4801 | Binary | Deprecated | Old raw frame stream — replaced by Alpaca imagearray |

### Key insight

`seevar` migrated to **Alpaca-only** (port 32323) for all production control.
Port 4700 is kept **only** for `scope_speed_move` (manual jogging) because Alpaca
`MoveAxis` returns error 1032 (not implemented) on the Seestar firmware.

---

## 3. Alpaca REST API (Port 32323)

Base URL: `http://<telescope_ip>:32323`

### Device map

| Device | Index | Purpose |
|--------|-------|---------|
| Telescope | 0 | Slew, track, park, unpark |
| Camera | 0 | IMX585 telephoto (science camera) |
| Camera | 1 | Wide-angle / finder |
| Focuser | 0 | Telephoto focuser |
| Focuser | 1 | Wide-angle focuser |
| FilterWheel | 0 | Dark(0) / IR(1) / LP(2) |
| Switch | 0 | Dew heater on/off |

### Common query parameters

```
ClientID=42&ClientTransactionID=<n>
```

`ClientTransactionID` is an atomic counter — increment on each call.
Always check `ErrorNumber` in every response: 0 = success, anything else = failure.

---

## 4. Telescope Control

### GET — Properties

```
GET /api/v1/telescope/0/<property>?ClientID=42&ClientTransactionID=<n>
```

| Property | Type | Description |
|----------|------|-------------|
| `connected` | bool | Connection state |
| `tracking` | bool | Sidereal tracking enabled |
| `slewing` | bool | Slew in progress |
| `atpark` | bool | At park position |
| `athome` | bool | At home position |
| `rightascension` | float | Current RA (decimal hours, J2000) |
| `declination` | float | Current Dec (decimal degrees, J2000) |
| `altitude` | float | Altitude (degrees) |
| `azimuth` | float | Azimuth (degrees) |
| `siderealtime` | float | Local sidereal time (hours) |
| `sitelatitude` | float | Observer latitude |
| `sitelongitude` | float | Observer longitude |

### PUT — Commands

```
PUT /api/v1/telescope/0/<method>
Content-Type: application/x-www-form-urlencoded
Body: ClientID=42&ClientTransactionID=<n>&<params>
```

| Method | Params | Effect |
|--------|--------|--------|
| `connected` | `Connected=true` | Connect to telescope |
| `unpark` | — | Deploy arm → ScopeMoveToHorizon event |
| `park` | — | Park mount (closes arm) |
| `slewtocoordinatesasync` | `RightAscension=<hours>&Declination=<degrees>` | Async slew to target |
| `synctocoordinates` | `RightAscension=<hours>&Declination=<degrees>` | Sync pointing model |
| `abortslew` | — | Abort active slew |
| `tracking` | `Tracking=true` | Enable sidereal tracking |

### Alpaca error codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1024 | Property not implemented |
| 1032 | Not initialised (unpark first) |
| 1036 | Action not implemented |
| 1279 | Command rejected (e.g. below horizon) |

### Important: MoveAxis does NOT work

`MoveAxis` returns error 1032 on the Seestar firmware.
Use port 4700 `scope_speed_move` for manual jogging (see section 6).

---

## 5. Camera Control

### GET — Properties

```
GET /api/v1/camera/0/<property>?ClientID=42&ClientTransactionID=<n>
```

| Property | Type | Description |
|----------|------|-------------|
| `gain` | int (0-600) | Current gain value |
| `ccdtemperature` | float | Sensor temperature °C |
| `imageready` | bool | Image ready for download |
| `camerastate` | int | 0=Idle 1=Waiting 2=Exposing 3=Reading 4=Download 5=Error |
| `cameraxsize` | int | 3840 (S30-Pro identifier) |
| `cameraysize` | int | 2160 |

### PUT — Commands

| Method | Params | Effect |
|--------|--------|--------|
| `gain` | `Gain=<0-600>` | Set sensor gain (default: 80) |
| `startexposure` | `Duration=<seconds>&Light=true` | Start exposure |
| `abortexposure` | — | Stop active exposure |

### Image download

```
GET /api/v1/camera/0/imagearray?ClientID=42&ClientTransactionID=<n>
```

- Returns JSON with `Value` field containing int32 array
- Shape: **3840 × 2160** (width × height), flattened 1D
- Download time: ~33 seconds for full 8.3MP frame via JSON
- Reshape: `np.array(value).reshape(2160, 3840)`

### Exposure timing

```
GET /api/v1/camera/0/camerastate  ← poll this
GET /api/v1/camera/0/imageready   ← True when ready
```

Timeouts used in seevar:
- `SLEW_TIMEOUT = 60 s`
- `EXPOSE_TIMEOUT = 120 s`
- `DOWNLOAD_TIMEOUT = 300 s`

---

## 6. Native JSON-RPC TCP (Port 4700) — Jogging Only

Port 4700 is retained **exclusively** for `scope_speed_move`.
Everything else uses Alpaca.

### Wire format

```python
msg = {"jsonrpc": "2.0", "id": <int>, "method": "<method>", "params": <value>}
wire = (json.dumps(msg) + "\r\n").encode("utf-8")
```

**Note:** Some methods must omit the `params` key entirely (do not send `"params": {}`).
`get_device_state` is one such method — the firmware rejects an explicit empty dict.

### UDP handshake (required before TCP connect)

```python
msg = {"id": 1, "method": "scan_iscope", "params": ""}
# Send to port 4720 via UDP before opening TCP socket on 4700
```

### Guest mode / master CLI

After TCP connect, send `set_setting(master_cli=true)` to claim control.
Without this, the device is in observer mode: it sends events (PiStatus, EqModePA…)
but silently ignores all control commands.

```python
{"id": <n>, "method": "set_setting", "params": {"master_cli": true}}
```

Required only when using port 4700. Alpaca has no session lock — no claim needed.

### Manual jogging command

```python
{
    "id": <n>,
    "method": "scope_speed_move",
    "params": {"speed": <int>, "angle": <int>, "dur_sec": <int>}
}
```

| Parameter | Values | Notes |
|-----------|--------|-------|
| `speed` | 500–8000 | 4000 = normal, 8000 = fast |
| `angle` | 0/90/180/270 | 0=North, 90=East, 180=South, 270=West |
| `dur_sec` | int | Mount moves for this duration then auto-stops |

Pattern for held-button jogging:
- Button pressed → send `scope_speed_move(dur_sec=2)`
- Timer every 1500ms → resend to extend movement
- Button released → send `iscope_stop_view`

### Stop command

```python
{"id": <n>, "method": "iscope_stop_view", "params": {}}
```

### Firmware verify injection

| Firmware ver_int | Action |
|-----------------|--------|
| < 2582 | No inject |
| 2582 – 2705 | Add `"verify": true` to params |
| ≥ 2706 (SSL-auth) | No inject (rejected with code 109) |
| 0 (unknown) | No inject (assume modern) |

### Heartbeat (keep TCP alive)

Send `scope_get_equ_coord` every 10s — without it the Seestar closes the connection
after ~20s of inactivity (BrokenPipe on next command).

---

## 7. Filter Wheel

```
PUT /api/v1/filterwheel/0/position
Body: ClientID=42&ClientTransactionID=<n>&Position=<0-2>
```

| Position | Filter | Use |
|----------|--------|-----|
| 0 | Dark | Calibration / closed shutter |
| 1 | IR | Infrared pass |
| 2 | LP | Light pollution filter |

---

## 8. Hardware Fingerprinting

To confirm the device is an S30 Pro (not S30 or S50):

```
GET /api/v1/camera/0/cameraxsize?ClientID=42&ClientTransactionID=1
```

- **3840** → S30 Pro (IMX585) ✅
- **1920** → S30 or S50 (IMX662/IMX462)

---

## 9. Device Discovery

**Preferred:** Direct HTTP probe

```
GET http://<ip>:32323/management/v1/configureddevices
```

A 200 response with 7 devices confirms the telescope is online.

**Fallback:** UDP broadcast on port 32227 (unreliable on S30-Pro).

---

## 10. Unpark Behaviour

`PUT /api/v1/telescope/0/unpark` deploys the arm and triggers a `ScopeMoveToHorizon`
event — the arm swings to the horizon ready for use.

`park` closes the arm and is the correct safe end state.

**Important:** Alpaca `unpark` does not always open the arm reliably via firmware.
The user may need to use the native Seestar app for the first initialization in a session.
After that, `park` / `unpark` via Alpaca work correctly.

---

## 11. Safety Vetoes

| Condition | Threshold | Action |
|-----------|-----------|--------|
| Sensor temperature | > 55 °C | Park, abort |
| Battery | < 10% | Park, alert |
| Target below horizon | altitude < 30° | Skip target |
| Pointing error (post-solve) | > 12 arcmin | Retry/skip |

---

## 12. FITS Headers (Correct Values for S30 Pro)

```
BAYERPAT = 'GRBG'        # Sony IMX585 — NOT RGGB
INSTRUME = 'IMX585'
TELESCOP = 'ZWO Seestar S30 Pro'
FOCALLEN = 160            # mm
XPIXSZ  = 2.9            # µm
YPIXSZ  = 2.9
NAXIS1  = 3840            # width
NAXIS2  = 2160            # height
GAIN    = 80              # default gain
```

> **Correction vs earlier assumption:** CLAUDE.md listed BAYERPAT=RGGB and FOCALLEN=150.
> The correct values (from seevar hardware docs) are GRBG and 160 mm.
