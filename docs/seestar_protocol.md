# Seestar S30 Pro — Protocol & Control Reference

> Synthesized from: `seevar-main/dev/logic/*.MD`, `seestar_alp` source code,
> and real-device testing (firmware 7.18 / fw_ver_int ~2706+, April–May 2026).

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
| 4700 | JSON-RPC TCP | Silent — unusable | Accepts TCP but never responds to any command |
| 4720 | UDP | No response | `scan_iscope` — not required on firmware 7.18+ |
| 32227 | UDP | No response | Alpaca discovery broadcast — unreliable on S30-Pro |
| 4801 | Binary | Open but unused | Preview frame stream — see plan_live_preview.md |
| 80 | HTTP | Incomplete responses | Internal firmware web UI — not usable |

### Key insight (validated 2026-05-10, firmware 7.18)

**Port 32323 Alpaca is the only working control channel.**

- Port 4700 (JSON-RPC) connects but returns no response to any command.
  The native ZWO app may hold an exclusive lock that cannot be released.
- `MoveAxis` (Alpaca) **works** on firmware 7.18+ despite earlier docs saying otherwise.
  Measured: ~3°/1.5s at 2 deg/s, all 4 directions confirmed.
- No UDP handshake is required. Direct HTTP to port 32323 is sufficient.

---

## 3. Validated Connection Recipe (2026-05-10)

Tested against real Seestar S30 Pro at 192.168.0.18, firmware 7.18.

### Step 1 — Connect telescope

```http
PUT http://192.168.0.18:32323/api/v1/telescope/0/connected
Body: ClientID=1&ClientTransactionID=1&Connected=true
→ {"ErrorNumber":0, ...}
```

### Step 2 — Read position

```http
GET http://192.168.0.18:32323/api/v1/telescope/0/rightascension?ClientID=1&ClientTransactionID=2
→ {"Value": 22.52, "ErrorNumber": 0, ...}
```

Also works: `altitude`, `azimuth`, `declination`, `tracking`, `slewing`, `atpark`.

### Step 3 — Jog (MoveAxis)

```http
# Start moving North (altitude+) at 2 deg/s
PUT /api/v1/telescope/0/moveaxis
Body: ClientID=1&ClientTransactionID=3&Axis=1&Rate=2.0

# Stop
PUT /api/v1/telescope/0/moveaxis
Body: ClientID=1&ClientTransactionID=4&Axis=1&Rate=0.0
```

Axis mapping: `0` = Azimuth (E/W), `1` = Altitude (N/S).
Positive rate: North / East. Negative rate: South / West.

### Step 4 — Connect camera

```http
PUT http://192.168.0.18:32323/api/v1/camera/0/connected
Body: ClientID=1&ClientTransactionID=5&Connected=true
```

Camera 0 = IMX585 telephoto (science). Camera 1 = wide-angle finder.
GainMin=0, GainMax=600. Default gain: 80.

### Step 5 — Take an exposure

```http
PUT /api/v1/camera/0/startexposure
Body: ClientID=1&ClientTransactionID=6&Duration=10.0&Light=true

# Poll until ready
GET /api/v1/camera/0/imageready   → {"Value": false, ...}  (repeat)
GET /api/v1/camera/0/imageready   → {"Value": true, ...}   (download now)

# Download (slow ~33s via JSON, fast ~3s via ImageBytes)
GET /api/v1/camera/0/imagearray
```

### Python shortcut (uses our wrapper)

```python
from argos.core.alpaca.telescope import Telescope
from argos.core.alpaca.camera import Camera

scope = Telescope("192.168.0.18", 32323)
scope.connect()                         # returns "Seestar S30 Pro_... Telescope"

scope.move_axis(1, 2.0)                 # start moving North
import time; time.sleep(2.0)
scope.stop_axis(1)                      # stop

cam = Camera("192.168.0.18", 32323)
cam.connect()                           # width=2160, height=3840, gain 0-600
cam.set_gain(80)
cam.start_exposure(10.0)
while not cam.is_image_ready():
    time.sleep(0.5)
arr = cam.get_image_array()             # numpy uint16 (height, width)
```

---

## 4. Alpaca REST API (Port 32323)

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

## 5. Telescope Control

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

### MoveAxis — confirmed working on firmware 7.18+

`MoveAxis` was previously believed broken (error 1032). Tested 2026-05-10:
it works correctly. Use it for all manual jogging. Port 4700 is not needed.

```python
# Axis 0 = Azimuth (Primary)   — positive rate = East
# Axis 1 = Altitude (Secondary) — positive rate = North
PUT /api/v1/telescope/0/moveaxis
Body: ClientID=1&ClientTransactionID=<n>&Axis=0&Rate=2.0   # start moving East
# ...hold...
PUT /api/v1/telescope/0/moveaxis
Body: ClientID=1&ClientTransactionID=<n>&Axis=0&Rate=0.0   # stop
```

Measured movement: ~3° per 1.5 s at Rate=2.0 deg/s.
Rate=0.0 stops immediately.

---

## 6. Camera Control

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

## 7. Native JSON-RPC TCP (Port 4700) — Jogging Only

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

## 8. Filter Wheel

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

## 9. Hardware Fingerprinting

To confirm the device is an S30 Pro (not S30 or S50):

```
GET /api/v1/camera/0/cameraxsize?ClientID=42&ClientTransactionID=1
```

- **3840** → S30 Pro (IMX585) ✅
- **1920** → S30 or S50 (IMX662/IMX462)

---

## 10. Device Discovery

**Preferred:** Direct HTTP probe

```
GET http://<ip>:32323/management/v1/configureddevices
```

A 200 response with 7 devices confirms the telescope is online.

**Fallback:** UDP broadcast on port 32227 (unreliable on S30-Pro).

---

## 11. Unpark Behaviour

`PUT /api/v1/telescope/0/unpark` deploys the arm and triggers a `ScopeMoveToHorizon`
event — the arm swings to the horizon ready for use.

`park` closes the arm and is the correct safe end state.

**Important:** Alpaca `unpark` does not always open the arm reliably via firmware.
The user may need to use the native Seestar app for the first initialization in a session.
After that, `park` / `unpark` via Alpaca work correctly.

---

## 12. Safety Vetoes

| Condition | Threshold | Action |
|-----------|-----------|--------|
| Sensor temperature | > 55 °C | Park, abort |
| Battery | < 10% | Park, alert |
| Target below horizon | altitude < 30° | Skip target |
| Pointing error (post-solve) | > 12 arcmin | Retry/skip |

---

## 13. FITS Headers (Correct Values for S30 Pro)

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
