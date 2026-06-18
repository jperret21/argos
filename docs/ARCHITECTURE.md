# Argos — Architecture

> *A differential-photometry controller for the ZWO Seestar S30 Pro.*  
> *~16 kLoC, three layers, zero emoji.*

---

## Why This Exists

The Seestar S30 Pro is a capable little astrograph — 160 mm f/5.3 quadruplet APO,
IMX585 (Starvis 2), 3840×2160 at 2.9 µm. But its native app treats it as an
eyepiece replacement, not a science instrument. Argos fills the gap:

- **ASCOM Alpaca** for all hardware control (telescope, camera, focuser, filter wheel)
- **Differential photometry pipeline** — from raw GRBG mosaic to ensemble light curve
- **AAVSO-ready** — VSX/VSP catalogue queries, TG-band photometry, Siril-compatible
  folder structure
- **Live preview with scientific tools** — HFD metrics, plate solving, multi-star
  aperture photometry, all off the UI thread

The Seestar hardware constraints are real: 2.9 µm pixels, 3.74″/pixel scale,
~4.6° FOV, 55 °C thermal veto, and a WiFi bottleneck that makes a full-frame
download take ~5 s. Every design decision below respects those limits.

---

## Layer Map

Three layers, one dependency direction. This is the core architectural invariant:

```
┌──────────────────────────────────────────────────────────┐
│                    UI (PyQt6)                             │
│  argos/ui/                                         │
│  Panels, widgets, shell, theme, pages                    │
│  Ø business logic. Ø network I/O.                        │
│  Imports: PyQt6, workers (via signals)                   │
├──────────────────────────────────────────────────────────┤
│                  Workers (QThread)                        │
│  argos/workers/                                    │
│  Bridge: core ↔ UI. Qt signals only.                     │
│  Imports: core/, PyQt6.QtCore                            │
│  Ø UI widgets. Ø requests.                               │
├──────────────────────────────────────────────────────────┤
│                  Core (pure Python)                       │
│  argos/core/                                       │
│  Business logic, network clients, data pipelines.        │
│  Imports: stdlib, numpy, astropy, requests               │
│  Ø PyQt6. Testable headless.                             │
└──────────────────────────────────────────────────────────┘
```

The rule is enforced by code review, not by linter — but it's kept simple enough
that a single `grep PyQt6 argos/core/` suffices to audit it.

---

## Complete Module Map

### `core/` — Pure Python, zero Qt

All frame maths, network protocols, catalogues, and science logic live here.

```
core/
├── alpaca/                        # ASCOM Alpaca HTTP device wrappers
│   ├── client.py                  Low-level GET/PUT with typed error handling
│   ├── discovery.py               UDP broadcast scan (port 32227, unreliable)
│   ├── telescope.py               Slew, track, park, MoveAxis (port 32323)
│   ├── camera.py                  Expose, gain, ImageArray download, ImageBytes
│   ├── focuser.py                 Absolute/relative moves, HFD sweep support
│   └── filterwheel.py             Dark(0) / IR(1) / LP(2) positions
│
├── catalog/                       # Star catalogue access (Qt-free, network-isolated)
│   ├── aavso.py                   AAVSO VSX cone search + VSP chart HTTP clients
│   ├── photometry.py              Comparison-star ranking by magnitude, colour, sep
│   └── targets.py                 Persistent target/comparison set for a session
│
├── imaging/                       # Frames, FITS, solving, metrics
│   ├── imx585.py                  Sony IMX585 constants: QE curve, gain, saturation
│   ├── debayer.py                 GRBG → super-pixel / bilinear / CFA channels
│   ├── green.py                   Single-source-of-truth green-plane extraction
│   ├── stretch.py                 Histogram-based display stretch + statistics
│   ├── metrics.py                 HFD, FWHM, star detection, eccentricity
│   ├── fits_writer.py             16-bit FITS with science-grade headers
│   ├── sequencer.py               Multi-step acquisition plan (Light/Dark/Flat/Bias)
│   ├── session_log.py             Per-frame QA records → session.json (§7)
│   ├── platesolve.py              ASTAP wrapper → WCS, pointing correction
│   ├── astrometry_session.py      Shared solve lifecycle (live plate solve + manual)
│   └── sky_geometry.py            Airmass, Moon separation, phase, Sun altitude
│
├── photometry/                    # Differential pipeline, all Qt-free (§6)
│   ├── aperture.py                Aperture photometry on green plane (§6 C1)
│   ├── differential.py            Ensemble differential: target / comparison / check
│   ├── lightcurve.py              Time-series accumulator + AAVSO-format CSV export
│   ├── airmass.py                 Julian date, airmass from site + WCS (§6 C4)
│   └── session.py                 Measure a target set on one solved frame (§6 C4)
│
├── seestar/                       # Native JSON-RPC 2.0 TCP (port 4700)
│   └── native_client.py           scope_speed_move jogging; heartbeat; guest mode
│
├── stellarium/                    # Planetarium integration
│   ├── protocol.py                Stellarium Telescope Protocol v1.0 binary codec
│   └── server.py                  Asyncio TCP server, bridges to Qt worker
│
└── config.py                      ~/.argos/config.json: observer, astrometry,
                                   photometry params, camera constants, UI state
```

### `workers/` — QThread Bridges

Each worker encapsulates one background concern. They form the signal fabric
between core logic and the UI.

```
workers/
├── discovery_worker.py            One-shot UDP scan → device list signal
├── polling_worker.py              Mount RA/Dec/Alt/Az every 2 s
├── exposure_worker.py             Continuous live preview loop
├── preview_processor.py           Off-thread: debayer → stretch → star detect
│                                  (latest-frame-wins: drops stale jobs)
├── sequence_worker.py             Executes SequencePlan → FITS files + session log
├── autofocus_worker.py            HFD V-curve: sweep, measure, parabola fit
├── solve_worker.py                ASTAP solve on one frame → SolveResult signal
├── astrometry_controller.py       Auto-solve policy: cadence, mount-distance gate
├── catalog_worker.py              VSX cone search + VSP chart off the UI thread
└── stellarium_worker.py           Asyncio event loop → Qt signals
```

### `ui/` — Presentation Only

Layout, colour, widgets. No `requests`, no `socket`, no business logic.

```
ui/
├── shell.py                       Main window, 3-mode navigation
├── sidebar.py                     Mode switcher (Connection / Imaging / Config)
├── statusbar.py                   Live status: devices, tracking, last action
├── theme.py                       Siril-inspired equilux dark palette
├── design.py                      Spacing, typography, layout primitives
├── analysis_window.py             Standalone FITS inspector (post-processing)
│
├── pages/                         # The three main modes
│   ├── connection_page.py         Device connect/discover + Stellarium pairing
│   ├── imaging_page.py            Live view, capture, focus, sequence, photometry
│   └── configuration_page.py      Observer, site, astrometry, catalog settings
│
├── panels/                        # Floating / modal panels
│   ├── log_panel.py               Session log (§7) viewer
│   ├── manual_control_dialog.py   MoveAxis jogging with direction pads
│   ├── photometry_setup_window.py Target selection, comparison stars, session prefs
│   ├── photometry_window.py       Live light curve + comparison table (§6 C5/C6)
│   └── stellarium_card.py         Server on/off, connection status
│
└── widgets/                       # Reusable dock widgets
    ├── fits_viewer.py             PyQtGraph image display, stretch, crosshair
    ├── image_toolbar.py           Debayer view mode / channel toggles
    ├── overlay_bar.py             Catalog markers, grid, FOV, annotations
    ├── histogram_dock.py          R/G/B histograms, black/white/midtone sliders
    ├── camera_dock.py             Single-shot and continuous exposure controls
    ├── focuser_dock.py            Position readout, move, autofocus trigger
    ├── mount_dock.py              RA/Dec, Alt/Az, jog, GoTo, tracking toggle
    ├── filterwheel_dock.py        Current filter display, position selector
    ├── sequence_panel.py          Multi-step plan table (Light/Dark/Flat/Bias)
    ├── astrometry_settings.py     Solve parameters: radius, scale hint, timeout
    ├── star_info_card.py          On-click star: coordinates, magnitude, HFD
    ├── target_table.py            Target set: name, RA/Dec, priority, status
    ├── comparison_table.py        Full photometry table for a single variable
    ├── lightcurve_panel.py        Live differential light-curve plot (§6 C5)
    └── metrics_panel.py           Session trending: HFD, SNR, airmass over time
```

---

## Communication Protocols

### ASCOM Alpaca — HTTP REST (port **32323**)

The primary control channel. Every hardware operation goes through this:

```
http://<device>:32323/api/v1/<device_type>/<index>/<property|method>
```

| Device        | Index | Purpose                            |
|---------------|-------|------------------------------------|
| Telescope     | 0     | Slew, track, park, MoveAxis        |
| Camera        | 0     | IMX585 science camera              |
| Camera        | 1     | Wide-angle finder (unused)         |
| Focuser       | 0     | Telephoto focuser                  |
| Focuser       | 1     | Wide-angle focuser (unused)        |
| FilterWheel   | 0     | Dark(0) / IR(1) / LP(2)            |
| Switch        | 0     | Dew heater on/off                  |

**Port note.** Earlier code defaults to port 4700 (the native JSON-RPC port).
Real-device testing on firmware 7.18+ (2026-05-10) confirms the Alpaca server
is on **32323**. The default in `config.py` is being updated to match.

MoveAxis — reported broken in earlier firmware — works correctly on 7.18+.
Use it for all manual jogging; the native JSON-RPC path is no longer needed.

**Image download.** Two paths exist:
- *Fast:* binary `ImageBytes` buffer (~3 s for 8.3 MPx)
- *Fallback:* JSON `ImageArray` (~33 s, used when binary dimensions mismatch)

The wrapper in `core/alpaca/camera.py` detects the mismatch and falls back
transparently, logging which path was taken.

### Native JSON-RPC — TCP (port 4700)

Retained exclusively for `scope_speed_move` jogging on firmware where MoveAxis
was broken (pre-7.18). On current firmware this port accepts TCP but returns
no response — the ZWO native app may hold an exclusive lock.

Keep-alive: send `scope_get_equ_coord` every 10 s or the Seestar closes the
connection (BrokenPipe on next command).

### Stellarium Telescope Protocol — TCP (port 10001)

Asyncio server speaking the v1.0 binary protocol. Lets Stellarium drive the
Seestar mount as a standard telescope. The binary codec is in
`core/stellarium/protocol.py`; the asyncio event loop runs on a QThread via
`workers/stellarium_worker.py`.

### Device Discovery

**Preferred:** Direct HTTP probe.

```
GET http://<ip>:32323/management/v1/configureddevices
```

A 200 response with 7 devices confirms the telescope is online.

**Fallback:** UDP broadcast on port 32227. Unreliable on S30 Pro — the device
often doesn't respond. The discovery worker also tries the probe.

---

## Threading Model

```
┌─ Main thread ──────────────────────────────────────────┐
│  Qt event loop. Never blocks. Never does I/O.           │
│  Receives signals from workers, updates widgets.        │
└─────────────────────────────────────────────────────────┘
         ▲ signals ▲                ▲ signals ▲
         │         │                │         │
┌────────┴─────────┴──┐   ┌────────┴─────────┴──┐
│  QThread workers     │   │  QThreadPool tasks  │
│  (long-lived loops)  │   │  (short-lived)      │
│  • exposure_worker   │   │  • solve_worker     │
│  • polling_worker    │   │  • catalog_worker   │
│  • sequence_worker   │   │  • autofocus_worker │
│  • stellarium_worker │   │                     │
└──────────────────────┘   └─────────────────────┘
```

### The preview chain (three threads, latest-frame-wins)

```{graphviz} diagrams/preview_chain.dot
:align: center
```

1. **ExposureWorker** (QThread) starts the camera exposure via Alpaca HTTP, polls
   `ImageReady`, and downloads the raw uint16 array.
2. **PreviewProcessor** (QThread) receives the raw array via the `frame_ready` signal
   and computes the display render, star field, frame metrics, and histograms — all
   off the UI thread.
3. The **UI thread** receives a `ProcessedFrame` dataclass and applies the final
   display stretch, overlays, and histogram update. These are cheap enough
   (numpy uint8 → QImage) to run on the main thread.

**Latest-frame-wins.** If frames arrive faster than `PreviewProcessor` can
process them, stale jobs are silently dropped. The processor keeps only the
most recently submitted `(raw, view)` and skips any intermediate ones.

This is the single most important performance architecture in the app.
Without it, a 5-second image download would freeze the UI. With it, the
preview stays responsive even when the camera is dumping frames faster
than the display can consume them.

---

## Data Flow — End to End

```
Seestar S30 Pro
    │
    ├── Alpaca HTTP :32323 ──► core/alpaca/ ──► workers/ ──(signals)──► ui/
    │   telescope / camera / focuser / filter wheel
    │
    ├── JSON-RPC TCP :4700 ──► core/seestar/ ──► workers/ ──► (jog only)
    │   scope_speed_move (legacy path)
    │
    ├── Stellarium TCP :10001 ──► core/stellarium/ ──► stellarium_worker ──► ui/
    │   planetarium sync
    │
    └── AAVSO VSX+VSP (HTTPS) ──► core/catalog/ ──► catalog_worker ──► ui/
        variable + comparison star data

FITS output:
    core/imaging/fits_writer.py ──► ~/Argos/sessions/{date}_{target}/
```

---

## Photometry Pipeline (Preview)

This runs live during an acquisition session — no calibration frames, no
post-processing. The publishable pipeline (darks, flats, bias) runs later
in Siril or a separate reduction script.

```
Raw frame (uint16, 3840×2160, GRBG)
    │
    ▼
green.py  ──► green plane (1920×2160, G channel only)
    │
    ▼
platesolve.py ──► WCS (via ASTAP)
    │
    ▼
catalog/aavso.py ──► variable + comparison stars from VSX/VSP
    │
    ▼
photometry/aperture.py ──► aperture sums for all targets
    │
    ▼
photometry/differential.py ──► ensemble differential magnitudes
    │
    ▼
photometry/lightcurve.py ──► time-series accumulator
```

Each module is unit-testable in isolation. The full chain runs off the UI
thread via `photometry_setup_window.py` + `solve_worker.py` + `catalog_worker.py`.

---

## Configuration

File: `~/.argos/config.json`

Key sections:

| Path | Key | Default | Notes |
|------|-----|---------|-------|
| `alpaca` | `host` / `port` | `""` / `32323` | Device IP and Alpaca port |
| `sessions_path` | — | `~/Argos/sessions/` | Output; Siril-compatible layout |
| `observer` | `name` / `lat` / `lon` / `elev` | empty / 0 | FITS header site info |
| `camera` | `adc_bits` / `full_well_adu` | 12 / 60000 | IMX585: 12-bit ADC → 16-bit FITS |
| `astrometry` | `astap_path` / `database` | `""` / `""` | Empty → auto-detect |
| `catalog` | `mag_limit` / `max_results` | 15.0 / 250 | VSX cone search bounds |
| `photometry` | `aperture_fwhm_mult` / etc. | 2.5 / ... | Aperture radii in FWHM units |

---

## Session Layout (Siril-Compatible)

```
~/Argos/sessions/
└── 20250814_SS_CYG/
    ├── Lights/
    │   ├── SS_CYG_Light_20250814_213045_10s_TG_0001.fits
    │   ├── SS_CYG_Light_20250814_213100_10s_TG_0002.fits
    │   └── ...
    ├── Darks/
    │   └── 10s/
    │       └── Dark_*.fits
    ├── Flats/
    ├── Bias/
    └── session.json               ← per-frame QA: HFD, SNR, FWHM, star count
```

FITS header includes all mandatory fields: `SIMPLE`, `BITPIX`, `NAXIS1/2`,
`BZERO`/`BSCALE`, `DATE-OBS`, `EXPTIME`, `GAIN`, `IMAGETYP`, `TELESCOP`,
`INSTRUME`, `FOCALLEN` (160), `XPIXSZ`/`YPIXSZ` (2.9), `BAYERPAT` (GRBG),
`RA`/`DEC`/`OBJCTRA`/`OBJCTDEC`, `ALTITUDE`/`AZIMUTH`, `OBJECT`, `FILTER` (TG),
`SITELAT`/`LON`/`ELEV`, `OBSERVER`.

---

## Data Model

```{graphviz} diagrams/data_model.dot
:align: center
```

### File persistence

| File | Format | Schema | Lifetime |
|------|--------|--------|----------|
| `~/.argos/config.json` | JSON | `Config` | Permanent |
| `session.json` | JSON | `SessionLog` + `FrameRecord`[] | One session |
| `targets.json` | JSON | `TargetSet` + `TargetStar`[] | One session |
| `*.fits` | FITS | 16-bit uint, full headers | Per frame |
| `photometry.csv` | CSV | `LcPoint` columns | Per target |

### Key dataclasses

| Class | Module | Purpose |
|---|---|---|
| `Config` | `core/config.py` | Application settings (observer, camera, astrometry, photometry) |
| `SequencePlan` | `core/imaging/sequencer.py` | Acquisition plan (multiple steps) |
| `FrameSpec` | `core/imaging/sequencer.py` | One frame to shoot |
| `FrameWCS` | `core/imaging/platesolve.py` | Pixel ↔ celestial mapping |
| `SolveResult` | `core/imaging/platesolve.py` | ASTAP outcome |
| `TargetSet` | `core/catalog/targets.py` | Session's selected stars |
| `TargetStar` | `core/catalog/targets.py` | One star with role (target/comp/check) |
| `AperturePhot` | `core/photometry/aperture.py` | Raw aperture measurement |
| `DiffResult` | `core/photometry/differential.py` | Calibrated differential magnitude |
| `LightCurve` | `core/photometry/lightcurve.py` | Accumulated points for a target |
| `SessionLog` | `core/imaging/session_log.py` | Per-frame QA records |

---

## Key Constants (from Hardware)

| Quantity | Value | Source |
|----------|-------|--------|
| Focal length | 160 mm | seevar hardware docs |
| Aperture | f/5.3 | 160 / 30.2 mm |
| Sensor | Sony IMX585 (Starvis 2) | — |
| Bayer pattern | **GRBG** (not RGGB) | critical for photometry |
| Pixel size | 2.9 µm | IMX585 datasheet |
| Resolution | 3840 × 2160 | 8.3 MPx |
| Pixel scale | 3.74″/px | 206.265 × 2.9 / 160 |
| Field of view | ~4.6° × ~2.6° | 3840 × 3.74 / 3600 |
| Saturation guard | 60 000 ADU | linearity limit |
| Default gain | 80 | 12-bit ADC |
| AAVSO filter code | TG | untransformed Bayer green |
| Thermal veto | > 55 °C | sensor shutdown |
