# SeerControl — Project Status

> Early development. Not ready for testing.
> Last updated: April 2025

---

## Implementation Status

### Working

| Module | Notes |
|---|---|
| Telescope control | GoTo (RA/Dec), tracking, park/unpark, sync via ASCOM Alpaca |
| Manual jogging | N/S/E/W movement at 3 speeds via native `scope_speed_move` API |
| Live preview | Continuous exposure loop, adjustable zoom (1x-8x) |
| FITS writer | 16-bit unsigned FITS with full science header set |
| UDP discovery | Automatic Seestar detection on local network |
| Alpaca integration | Binary ImageBytes transfer, typed error handling |
| Auto-stretch | Real-time histogram-based image stretch |
| HFD metrics | Per-frame Half Flux Diameter measurement |
| Crosshair + pixel readout | On-image overlay with coordinates and pixel values |

### In Progress

| Module | What's left |
|---|---|
| Imaging page redesign | Layout refactor, stats bar, log panel integration |
| Sequencer | Light/Dark/Flat/Bias sequence automation |
| Hardware limitations doc | Known firmware bugs documented in internal handoff |

### Planned

| Module | Description |
|---|---|
| Plate solving | ASTAP / astrometry.net integration for target centering |
| Focuser control | Alpaca focuser wrapper + autofocus V-curve |
| Filter wheel control | Alpaca filter wheel wrapper |
| Binary preview stream | Port 4801 for faster live view (1-5 fps) |

---

## Known Issues

### Seestar Firmware Limitations

| Issue | Workaround |
|---|---|
| `MoveAxis` returns error 1032 | Use native `scope_speed_move` API instead |
| `SlewToAltAzAsync` not implemented | Not available |
| Camera ROI / subframing broken | Do not use — firmware bug |
| `Unpark` via Alpaca doesn't deploy arm | Use native Seestar app for initialization |
| ImageArray download ~5s for 16 MB | Hardware WiFi limit |

### Software Issues

| Issue | Status |
|---|---|
| PyQt6 >= 6.8.0 crashes on macOS | Pinned to < 6.8.0 in pyproject.toml |
| macOS quarantine blocks Qt dylibs | Handled by `_fix_qt_plugin_path()` in main.py |

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| PyQt6 | < 6.8.0 | Desktop UI framework |
| pyqtgraph | < 0.14.0 | FITS image display |
| requests | >= 2.31.0 | HTTP client for Alpaca API |
| astropy | >= 6.0.0 | FITS I/O, coordinates, time |
| numpy | >= 1.26.0 | Image array manipulation |

---

## Branch Structure

```
main        -- Stable, tagged releases
develop     -- Integration branch
feat/*      -- New features
fix/*       -- Bug fixes
docs/*      -- Documentation
```
