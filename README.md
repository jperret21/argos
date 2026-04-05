# SeerControl

Desktop astrophotography control application for the **ZWO Seestar S30 Pro**, built with Python 3.11 and PyQt6.

> **Goal:** Replace the ZWO mobile app with a precision tool that produces science-grade FITS files compatible with Siril, PixInsight, and AstroImageJ — the same standards used in professional observatories.

---

## Features

| Module | Status | Description |
|---|---|---|
| Telescope control | ✅ | GoTo (RA/Dec), tracking, park/unpark, sync |
| Manual jogging | ✅ | Native `scope_speed_move` API — N/S/E/W at 3 speeds |
| Camera live preview | ✅ | Continuous exposure loop with adjustable scale (1×–8×) |
| FITS saving | ✅ | Full-resolution 16-bit FITS with complete science headers |
| UDP discovery | ✅ | Automatic Seestar detection on local network |
| Alpaca via alpyca | ✅ | Binary ImageBytes transfer (8× faster than JSON) |
| Sequencer | 🔜 | Light / Dark / Flat / Bias sequences |
| Plate solving | 🔜 | Center-on-target with astrometry.net |
| Focuser / Filter wheel | 🔜 | Alpaca wrappers + autofocus V-curve |

---

## Requirements

- macOS (Apple Silicon or Intel)
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- ZWO Seestar S30 Pro connected in **Station Mode** (WiFi)

> **PyQt6 version is pinned to `<6.8.0`** — versions 6.8+ crash on macOS with a cocoa platform plugin error.

---

## Installation

```bash
# 1. Install uv (once)
brew install uv

# 2. Clone and install dependencies
git clone <repo-url>
cd Seestar_controller
uv sync --extra dev
```

---

## Running

```bash
./run.sh
```

`run.sh` sets the required Qt platform plugin path and launches the app via `uv run`.

**Prerequisites before connecting:**
1. Open the Seestar app → Advanced settings → enable **Station Mode**
2. Note the Seestar's IP address (shown in the app)
3. The Seestar Alpaca server runs on port **4700**

---

## Architecture

```
seercontrol/
├── core/                   # Business logic — no UI dependencies
│   ├── alpaca/             # ASCOM Alpaca wrappers (telescope, camera, …)
│   ├── seestar/            # Native JSON-RPC TCP client (port 4700)
│   ├── imaging/            # FITS writer
│   └── config.py           # Persistent JSON config
├── workers/                # QThread workers — bridge core ↔ UI
│   ├── exposure_worker.py  # Live preview acquisition loop
│   ├── polling_worker.py   # Mount position polling (2s interval)
│   └── discovery_worker.py # UDP Alpaca device scan
└── ui/                     # PyQt6 panels — no business logic
    ├── panels/
    │   ├── mount_panel.py       # GoTo, tracking, park, manual jog
    │   ├── camera_panel.py      # Live preview + FITS saving
    │   └── manual_control_dialog.py  # Joystick dialog
    └── widgets/
        └── fits_viewer.py       # PyQtGraph image display
```

### Two protocols

| Protocol | Port | Used for |
|---|---|---|
| ASCOM Alpaca HTTP | 4700 | GoTo, tracking, position, camera, FITS download |
| Native JSON-RPC TCP | 4700 | `scope_speed_move` — manual jogging (MoveAxis not implemented on Seestar) |

### Threading model

```
Main thread    → Qt UI only (never blocks)
QThread        → all network / disk / computation
Qt signals     → only communication channel between threads
```

---

## FITS Headers

Every saved frame includes the full science header set:

```
DATE-OBS  UTC exposure start (ISO 8601)
DATE-AVG  UTC exposure midpoint — for photometric time analysis
MJD-OBS   Modified Julian Date (required by many analysis tools)
EXPTIME   Exposure time (seconds)
GAIN      Camera gain
TELESCOP  ZWO Seestar S30 Pro
INSTRUME  IMX585
FOCALLEN  150 mm
XPIXSZ    2.9 µm
BAYERPAT  RGGB
RA / DEC  Pointing coordinates (J2000)
OBJECT    Target name
FILTER    Filter used
SITELAT/SITELONG/SITEELEV  Observer location
```

File naming: `M42_Light_20260405_223105_10s_Ha_0001.fits`

Session folders are Siril-compatible:
```
~/SeerControl/sessions/20260405_M42/Lights/Ha/
```

---

## Known Hardware Limitations (Seestar S30 Pro)

| Feature | Status |
|---|---|
| `MoveAxis` | Error 1032 — not implemented; use native `scope_speed_move` |
| `SlewToAltAzAsync` | Error 1024 — not implemented |
| Camera ROI / subframing | Firmware bug — do not use |
| `Unpark` via Alpaca | Does not open the arm physically; use native app |
| ImageBytes | ✅ Supported — binary transfer active |
| ImageArray download speed | ~5s for 16 MB over WiFi — hardware limit |

---

## Development

```bash
# Tests
uv run python -m pytest tests/ -v

# Format + lint
uv run black seercontrol/ tests/
uv run ruff check seercontrol/ tests/
```

### Testing without the telescope

Use the [ASCOM Alpaca Simulator](https://github.com/ASCOMInitiative/ASCOM.Alpaca.Simulators/releases) (macOS compatible), which starts on `localhost:32323`.

---

## License

MIT
