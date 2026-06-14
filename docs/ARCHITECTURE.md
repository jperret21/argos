# SeerControl — Architecture

---

## Overview

SeerControl is a **PyQt6 desktop application** that communicates with the
ZWO Seestar S30 Pro via the ASCOM Alpaca protocol. The codebase is organized
into three layers with strict dependency rules.

```
┌─────────────────────────────────────────────────────┐
│                     UI (PyQt6)                       │
│  seercontrol/ui/                                     │
│  panels, widgets, shell, theme                       │
│  No business logic. No network I/O.                  │
├─────────────────────────────────────────────────────┤
│                  Workers (QThread)                    │
│  seercontrol/workers/                                 │
│  Bridge between core and UI. Qt signals only.        │
├─────────────────────────────────────────────────────┤
│                  Core (pure Python)                   │
│  seercontrol/core/                                    │
│  Business logic. No PyQt6 imports.                   │
│  Testable without a display.                         │
└─────────────────────────────────────────────────────┘
```

---

## Layer Rules

| Layer | Can import | Cannot import |
|---|---|---|
| `core/` | Python stdlib, requests, astropy, numpy | PyQt6 |
| `workers/` | core/, PyQt6.QtCore | UI widgets |
| `ui/` | PyQt6, workers (via signals) | requests, socket |

`workers/` is the **only** layer allowed to import both `core/` and PyQt6.

---

## Module Map

```
seercontrol/
├── core/
│   ├── alpaca/
│   │   ├── client.py         HTTP Alpaca client
│   │   ├── discovery.py      UDP device discovery (port 32227)
│   │   ├── telescope.py      Mount control wrapper
│   │   ├── camera.py         Camera control wrapper
│   │   ├── focuser.py        Focuser control wrapper
│   │   └── filterwheel.py    Filter wheel wrapper
│   ├── seestar/
│   │   └── native_client.py  TCP JSON-RPC client (port 4700)
│   ├── imaging/
│   │   ├── fits_writer.py    FITS file generation
│   │   ├── sequencer.py      Capture sequence automation
│   │   ├── debayer.py        Bayer pattern rendering
│   │   ├── metrics.py        HFD, star detection, frame stats
│   │   ├── stretch.py        Auto-stretch algorithms
│   │   └── sky_geometry.py   Coordinate calculations
│   └── config.py             Persistent JSON config (~/.seercontrol/)
│
├── workers/
│   ├── exposure_worker.py    Camera exposure loop
│   ├── polling_worker.py     Mount position (2s interval)
│   ├── discovery_worker.py   UDP scan thread
│   ├── sequence_worker.py    Automated sequence execution
│   ├── autofocus_worker.py   V-curve autofocus routine
│   └── stellarium_worker.py  Stellarium server integration
│
└── ui/
    ├── shell.py              Main window (3-mode shell)
    ├── theme.py              Dark theme colors and styles
    ├── design.py             Reusable layout components
    ├── sidebar.py            Navigation sidebar
    ├── pages/
    │   ├── connection_page.py    Device discovery and connect
    │   ├── imaging_page.py       Live preview, capture, focus
    │   └── configuration_page.py Settings editor
    ├── panels/
    │   ├── log_panel.py          Session log viewer
    │   ├── manual_control_dialog.py  Joystick controller
    │   └── stellarium_card.py    Stellarium pairing UI
    └── widgets/
        ├── camera_dock.py       Camera control panel
        ├── fits_viewer.py       FITS image display (PyQtGraph)
        ├── focuser_dock.py      Focuser control panel
        ├── histogram_dock.py    Histogram + stretch controls
        ├── image_toolbar.py     View controls toolbar
        ├── mount_dock.py        Mount control panel
        └── sequence_panel.py    Sequence planner and progress
```

---

## Communication Protocols

### ASCOM Alpaca (HTTP, port 4700)

Primary protocol for telescope, camera, focuser, and filter wheel control.
All calls are made directly from Python to the device — no proxy.
Binary ImageBytes transfer for faster image download.

### Native JSON-RPC (TCP, port 4700)

Used exclusively for manual jogging (`scope_speed_move`) since the
Alpaca `MoveAxis` command is not implemented on the Seestar firmware.

---

## Threading Model

```
Main thread    Qt UI event loop. Never blocks.
QThreads       All network, disk I/O, and computation.
Signals        The only communication channel between threads.
```

A worker never holds a reference to a widget.
Communication is one-way: worker emits signals, UI receives them.

---

## Data Flow

```
Seestar S30 Pro
     │
     ├── Alpaca HTTP ──► core/alpaca/ ──► workers/ ──(signals)──► ui/
     │   (telescope, camera, focuser)
     │
     └── JSON-RPC TCP ──► core/seestar/ ──► workers/ ──(signals)──► ui/
         (manual jogging)

     FITS output:
     core/imaging/ ──► ~/SeerControl/sessions/{date}_{target}/
```

---

## Configuration

Persistent settings are stored in `~/.seercontrol/config.json`.
See `core/config.py` for the schema and defaults.
