# CLAUDE.md — SeerControl

Development guidelines for Claude Code and human contributors.
**Read this file in full before making any changes to the project.**

---

## 1. Project Vision

**SeerControl** is a Python desktop application for astrophotography control of the **ZWO Seestar S30 Pro**.

Goals in priority order:
1. Full telescope control via ASCOM Alpaca (mount, camera, focuser, filter wheel)
2. Science-grade image acquisition — FITS files compliant with astronomical standards
3. Native compatibility with processing software (Siril, PixInsight, AstroImageJ)
4. Long-term evolution toward citizen science (differential photometry, asteroid tracking, exoplanets)

**This is not** a consumer app. It is a precision tool for amateur astronomers working
with the same standards as professional observatories.

---

## 2. Core Architecture Decisions

### 2.1 PyQt6 Desktop Application — No Web Interface

**Final and non-negotiable decision.**

| Requirement | Web | PyQt6 |
|---|---|---|
| FITS file writing | Not possible natively | Direct |
| Real-time camera feed | Latency + CORS | Native PyQtGraph |
| Alpaca UDP discovery | Requires proxy | Direct |
| Long-running tasks (sequences, guiding) | Fragile | Native QThread |
| Siril / astrometry.net integration | Not possible | subprocess |
| Dockable multi-panel layout | Complex | Native QDockWidget |

The web prototype (`legacy/`) serves as a **functional reference** only.
Do not extend it — it is archived and frozen.

### 2.2 Protocol: Direct ASCOM Alpaca

All Alpaca HTTP calls are made **directly from Python code** to the device.
No proxy, no intermediate server.

```python
# Correct
response = requests.get(f"http://{host}:{port}/api/v1/telescope/0/rightascension")

# Wrong — pointless in a desktop app
response = requests.get("http://localhost:5123/alpaca/get?device=telescope&...")
```

### 2.3 Threading Model — Absolute Rule

```
Main thread   →  UI only (PyQt6 widgets, event loop)
QThread workers →  everything else (network, disk I/O, computation)
```

**Never run blocking code on the main thread.** Any operation > 50ms must run in a QThread.
A network call on the UI thread freezes the interface — this is unacceptable.

Thread communication: **Qt signals only** (`pyqtSignal`).
No shared variables, no asyncio queues, no `threading.Event`.

### 2.4 Image Format: FITS

All saved images are **16-bit unsigned FITS** (BITPIX=16).
FITS headers are the single source of truth for acquisition metadata.
See section 6 for mandatory headers.

---

## 3. Project Structure

```
seercontrol/
│
├── seercontrol/                  # Main package
│   ├── __init__.py
│   │
│   ├── core/                     # Business logic — zero UI dependencies
│   │   ├── __init__.py
│   │   ├── alpaca/
│   │   │   ├── __init__.py
│   │   │   ├── client.py         # HTTP Alpaca client (synchronous requests)
│   │   │   ├── discovery.py      # UDP broadcast on port 32227
│   │   │   ├── telescope.py      # Mount wrapper (goto, track, park…)
│   │   │   ├── camera.py         # Camera wrapper (expose, gain, imagearray…)
│   │   │   ├── focuser.py        # Focuser wrapper (move, position…)
│   │   │   └── filterwheel.py    # Filter wheel wrapper
│   │   │
│   │   ├── imaging/
│   │   │   ├── __init__.py
│   │   │   ├── sequencer.py      # Light/Dark/Flat/Bias sequencer
│   │   │   ├── fits_writer.py    # FITS writing with compliant headers
│   │   │   └── autofocus.py      # AF routine — HFD V-curve
│   │   │
│   │   └── config.py             # Persistent JSON config (~/.seercontrol/config.json)
│   │
│   ├── workers/                  # QThread workers — bridge between core and UI
│   │   ├── __init__.py
│   │   ├── polling_worker.py     # Mount status polling every 2s
│   │   ├── exposure_worker.py    # Single camera exposure lifecycle
│   │   ├── sequence_worker.py    # Full sequence execution
│   │   └── discovery_worker.py   # UDP Alpaca scan (blocking → thread)
│   │
│   └── ui/                       # PyQt6 — no business logic here
│       ├── __init__.py
│       ├── main_window.py        # QMainWindow — dockable layout
│       ├── theme.py              # Color palette, global Qt stylesheet
│       ├── panels/
│       │   ├── __init__.py
│       │   ├── mount_panel.py    # Live mount control + coordinates
│       │   ├── camera_panel.py   # Live preview + exposure/gain controls
│       │   ├── sequencer_panel.py# Sequence planning and progress
│       │   ├── filterwheel_panel.py
│       │   ├── focuser_panel.py  # Focuser control + AF curve
│       │   ├── skymap_panel.py   # Sky chart (alt/az, goto)
│       │   └── log_panel.py      # Session log
│       └── widgets/              # Reusable custom widgets
│           ├── __init__.py
│           ├── led_indicator.py  # Connected/disconnected indicator
│           ├── coords_display.py # RA/Dec/Alt/Az formatted display
│           └── fits_viewer.py    # FITS image viewer (PyQtGraph)
│
├── tests/
│   ├── __init__.py
│   ├── core/
│   │   ├── test_fits_writer.py
│   │   ├── test_sequencer.py
│   │   └── test_alpaca_client.py
│   └── conftest.py               # pytest fixtures (Alpaca simulator)
│
├── legacy/                       # Frozen web prototype — reference only, do not modify
│   ├── backend/
│   └── frontend/
│
├── docs/
│   └── fits_headers.md           # Reference for all FITS headers used
│
├── main.py                       # Entry point: python main.py
├── requirements.txt
├── requirements-dev.txt          # pytest, black, ruff
├── .gitignore
├── handoff.md                    # Project history and known hardware limitations
└── CLAUDE.md                     # This file
```

### Structure Rules

- `core/` **never** imports `PyQt6`. It must be testable without a display.
- `ui/` **never** imports `requests` or `socket`. All I/O goes through a worker.
- `workers/` is the only layer allowed to import both `core/` and `PyQt6`.
- One module = one responsibility. If a file exceeds 300 lines, split it.
- `main.py` only does: create `QApplication`, load config, instantiate `MainWindow`, call `app.exec()`.

---

## 4. Python Conventions

### Language

**Everything is written in English** — variable names, function names, class names,
comments, docstrings, commit messages, and log messages. No exceptions.
French is allowed only in user-facing UI strings (labels, tooltips, menu items).

### Code Style

- Python **3.11+** required (match/case, ExceptionGroups, tomllib).
- Type hints on **all** public signatures. No `Any` unless explicitly justified.
- Docstrings on all public classes and methods (Google style format).
- Line length: **100 characters** max.
- Formatter: **black** (non-negotiable). Linter: **ruff**.
- No `print()` in application code — use `logging.getLogger(__name__)` everywhere.

### Logging

```python
import logging
logger = logging.getLogger(__name__)

logger.debug("Technical detail")
logger.info("Normal event")
logger.warning("Abnormal but recoverable situation")
logger.error("Functional error")
logger.critical("Application-blocking failure")
```

Log level is configurable via `config.json`. Production: `INFO`. Development: `DEBUG`.

### Error Handling

Every Alpaca network call can fail. The rule:
- Methods in `core/alpaca/` raise typed exceptions (`AlpacaError`, `AlpacaTimeoutError`).
- Workers catch these exceptions and emit an `error_occurred(str)` signal.
- The UI receives the signal and displays it in the log panel.
- **No silent try/except blocks anywhere.**

```python
# core/alpaca/client.py
class AlpacaError(Exception):
    def __init__(self, number: int, message: str): ...

class AlpacaTimeoutError(AlpacaError): ...
class AlpacaConnectionError(AlpacaError): ...
```

### Alpaca-Specific Rules

- `ClientID` = 1 (fixed).
- `ClientTransactionID` = atomic counter in `AlpacaClient`, incremented on each call.
- PUT requests are **always** encoded as `application/x-www-form-urlencoded`.
- GET timeout: **5s**. PUT timeout: **10s**. Exposure timeout: `duration + 15s`.
- Always check `ErrorNumber` in every Alpaca JSON response — 0 = success, otherwise raise `AlpacaError`.
- **Do not implement** camera ROI mode (firmware bug, see handoff.md).
- **Park** closes the arm reliably. **Unpark** via Alpaca does not open the arm — the user must use the native Seestar app for initialization. See handoff.md for details.

---

## 5. PyQt6 Conventions

### Signals and Slots

```python
# Worker definition
class ExposureWorker(QThread):
    frame_ready = pyqtSignal(np.ndarray, dict)   # (pixels, fits_headers)
    progress = pyqtSignal(int, int)               # (current_frame, total)
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()

# Connection in the panel
self.worker.frame_ready.connect(self._on_frame_ready)
self.worker.error_occurred.connect(self.log_panel.log_error)
```

- Signals carry **data**, not widgets.
- A worker never holds a reference to a widget. Communication is one-way: worker → UI via signals.
- Always call `worker.quit()` + `worker.wait()` before closing the application.

### Dockable Panels

- Each panel inherits from `QDockWidget`.
- Dock state (position, visibility) is saved via `QMainWindow.saveState()` in `config.json`.
- Each panel must be self-contained — no cross-panel dependencies.

### Visual Theme

Dark theme consistent with the observation environment (preserving night vision).

```python
# ui/theme.py — canonical colors
ACCENT       = "#58a6ff"   # blue — primary accents, links
SUCCESS      = "#3fb950"   # green — connected, OK
WARNING      = "#f0883e"   # orange — warnings
DANGER       = "#f85149"   # red — errors, destructive actions
SURFACE_1    = "#0d1117"   # application background
SURFACE_2    = "#161b22"   # panel background
SURFACE_3    = "#21262d"   # input/card background
SURFACE_4    = "#30363d"   # borders, hover
TEXT_PRIMARY = "#e6edf3"
TEXT_MUTED   = "#8b949e"
```

The global Qt stylesheet is defined in `ui/theme.py` and applied once on `QApplication`.
Never hardcode colors in panels — always reference constants from `theme.py`.

### Image Display (PyQtGraph)

- `fits_viewer.py` uses `pyqtgraph.ImageView` for FITS display.
- Auto-stretch on first display (1%-99% percentile).
- Interactive histogram available.
- Native PyQtGraph zoom/pan. No custom reimplementation.

---

## 6. FITS Standards — Critical for Scientific Value

This is the most important section for the long-term value of the project.

### Mandatory Headers on Every Frame

```
SIMPLE  = T
BITPIX  = 16                        # unsigned 16-bit integer
NAXIS   = 2
NAXIS1  = <pixel width>
NAXIS2  = <pixel height>
BZERO   = 32768                     # uint16 → int16 offset (FITS convention)
BSCALE  = 1

# Acquisition
DATE-OBS= '2025-08-14T22:31:05.123' # UTC ISO 8601, exposure start
EXPTIME = 10.0                      # seconds
GAIN    = 80                        # ADU gain value
XBINNING= 1
YBINNING= 1
IMAGETYP= 'Light Frame'             # 'Light Frame', 'Dark Frame', 'Flat Frame', 'Bias Frame'

# Instrument
TELESCOP= 'ZWO Seestar S30 Pro'
INSTRUME= 'IMX585'
FOCALLEN= 160                       # mm — Seestar S30 Pro focal length
XPIXSZ  = 2.9                       # µm — IMX585 pixel size
YPIXSZ  = 2.9
BAYERPAT= 'GRBG'                    # IMX585 Bayer pattern (Sony GRBG — NOT RGGB)

# Pointing (read from Alpaca at exposure start)
RA      = <decimal hours J2000>
DEC     = <decimal degrees J2000>
OBJCTRA = '<sexagesimal RA>'        # e.g. '05 34 32.0'
OBJCTDEC= '<sexagesimal Dec>'       # e.g. '+22 00 52'
ALTITUDE= <degrees>
AZIMUTH = <degrees>
PIERSIDE= 'EAST'                    # or 'WEST' if available

# Target
OBJECT  = '<target name>'           # e.g. 'M42', 'NGC 224'
FILTER  = '<filter name>'           # 'LRGB', 'Ha', 'OIII', 'SII', 'IR-cut'

# Observer site
SITELAT = <latitude degrees>
SITELONG= <longitude degrees>
SITEELEV= <elevation meters>
OBSERVER= '<name>'                  # from user config
```

### File Naming Convention

```
{OBJECT}_{IMAGETYP}_{DATE}_{TIME}_{EXPTIME}s_{FILTER}_{FRAME:04d}.fits

# Examples:
M42_Light_20250814_223105_10s_Ha_0001.fits
M42_Dark_20250814_230000_10s_NoFilter_0001.fits
NGC224_Flat_20250814_201500_1s_LRGB_0001.fits
```

- `DATE` = `YYYYMMDD`, `TIME` = `HHMMSS` (UTC)
- `FRAME` = 4-digit index, starts at 0001
- No spaces or special characters in filenames

### Session Folder Structure (Siril-Compatible)

```
~/SeerControl/
└── sessions/
    └── 20250814_M42/             # {DATE}_{OBJECT}
        ├── Lights/
        │   ├── Ha/               # subfolder per filter when using multiple filters
        │   │   └── M42_Light_*.fits
        │   └── OIII/
        ├── Darks/
        │   └── 10s/              # subfolder per exposure duration
        │       └── Dark_*.fits
        ├── Flats/
        │   └── Ha/
        │       └── Flat_*.fits
        ├── Bias/
        │   └── Bias_*.fits
        └── session.json          # session metadata (config, stats, log)
```

This structure is directly importable in Siril via "Open as sequence".

---

## 7. Dependencies

Dependencies are declared in `pyproject.toml` and locked in `uv.lock`.

### Package manager: uv (mandatory)

**Never use `pip install` directly in this project.**
This project uses [uv](https://github.com/astral-sh/uv) for all dependency management.
`pip install` ignores the lockfile and can pull incompatible versions — e.g. PyQt6 6.11
which crashes on macOS at startup with a cocoa platform plugin error.

```bash
# Install uv (once)
brew install uv

# Install / sync the full environment (reads uv.lock — exact versions guaranteed)
uv sync --extra dev

# Add a production dependency
uv add package-name

# Add a dev-only dependency
uv add --optional dev package-name
```

### Why uv, not pip+venv

- Creates `uv.lock` — all versions pinned exactly, like `package-lock.json` in JS
- 10-100x faster than pip
- Immune to conda `(base)` environment interference (active by default on this machine)
- `uv sync` is idempotent and safe to run at any time

### Production dependencies (`pyproject.toml`)

```
PyQt6>=6.6.0,<6.8.0      # ⚠ KEEP <6.8.0 — see note below
PyQt6-Qt6>=6.6.0,<6.8.0
pyqtgraph>=0.13.0
requests>=2.31.0
astropy>=6.0.0
numpy>=1.26.0
```

### PyQt6 version constraint — critical

PyQt6 **6.8.0 and above crashes on macOS** with:
```
qt.qpa.plugin: Could not find the Qt platform plugin "cocoa"
This application failed to start because no Qt platform plugin could be initialized.
```
The `<6.8.0` constraint in `pyproject.toml` prevents this.
**Do not relax this constraint** without testing on macOS Apple Silicon first.

### Rules for Adding Dependencies

1. Can an existing library already do this?
2. Is it actively maintained (recent commit < 6 months)?
3. Is it compatible with macOS Apple Silicon (arm64)?

Do not add scipy, OpenCV, tensorflow, or any library > 50MB without prior discussion.

---

## 8. Development Workflow

### First-time setup

```bash
brew install uv           # install package manager (once)
uv sync --extra dev       # create .venv and install all dependencies
```

### Daily commands

```bash
# Run the app
./run.sh

# Tests
.venv/bin/python3.11 -m pytest tests/ -v

# Format + lint
.venv/bin/black seercontrol/ tests/
.venv/bin/ruff check seercontrol/ tests/
```

### Git Workflow

#### Branch strategy

```
main        — stable, tagged releases only. Never commit directly.
develop     — integration branch. All features land here first.
feat/<name> — new features (e.g. feat/preview-port-4801)
fix/<name>  — bug fixes  (e.g. fix/imagearray-timeout)
chore/<name>— tooling, deps, config (e.g. chore/update-deps)
docs/<name> — documentation only
```

Rules:
- `main` is updated only via PR from `develop`, after validation.
- Every task starts with a branch cut from `develop`.
- Claude Code manages commits and branch creation for all coding tasks.
- No direct commits to `main` or `develop` — always branch + PR.

#### Commit message format (Conventional Commits)

```
<type>(<scope>): <short description>

Types  : feat | fix | chore | docs | refactor | test | perf
Scope  : native | alpaca | camera | mount | ui | sequencer | fits | config
Examples:
  feat(native): add port 4801 binary frame receiver
  fix(camera): fallback to JSON if ImageBytes unsupported
  chore(deps): pin PyQt6 < 6.8.0
  docs(claude): add git workflow section
```

#### Workflow for a new task

```bash
git checkout develop
git pull origin develop
git checkout -b feat/<name>

# ... implement ...

git add <specific files>
git commit -m "feat(<scope>): ..."
git push -u origin feat/<name>
# → open PR to develop via gh pr create
```

### Testing Without the Real Telescope

ASCOM Alpaca Simulator — works on macOS:
- https://github.com/ASCOMInitiative/ASCOM.Alpaca.Simulators/releases
- Starts on `localhost:32323` by default
- Simulates telescope, camera, focuser, filterwheel with realistic data
- Tests check for its presence and skip if absent:

```python
# tests/conftest.py
SIMULATOR_HOST = "localhost"
SIMULATOR_PORT = 32323

def is_simulator_running() -> bool:
    try:
        requests.get(
            f"http://{SIMULATOR_HOST}:{SIMULATOR_PORT}/api/v1/telescope/0/connected",
            timeout=1
        )
        return True
    except Exception:
        return False

simulator_required = pytest.mark.skipif(
    not is_simulator_running(),
    reason="ASCOM Alpaca Simulator not running"
)
```

---

## 9. What Never to Do

- **Never** run blocking code on the UI thread (requests, sleep, socket, heavy computation).
- **Never** hardcode colors in widgets — use `theme.py` constants.
- **Never** hardcode file paths — use `pathlib.Path` and `config.py`.
- **Never** use `time.sleep()` in a QThread — use `QThread.msleep()`.
- **Never** use `pip install` — use `uv add` instead to keep `uv.lock` in sync.
- **Never** commit `config.json` (contains IP, paths, user data).
- **Never** implement camera ROI mode (Seestar firmware bug, see handoff.md).
- **Never** delete `handoff.md` — it is the project's technical memory.
- **Do not** reimplement what astropy already does (coordinates, FITS, time).
- **Do not** use a database — JSON + FITS headers are the source of truth.

---

## 10. Legacy Files

The initial web prototype is archived in `legacy/` as a functional reference.

| File | Remaining purpose |
|---|---|
| `legacy/backend/seercontrol_proxy.py` | Reference: UDP discovery implementation |
| `legacy/backend/main.py` | Reference: Alpaca proxy routes |
| `legacy/backend/index.html` | Reference: MVP UX and feature list |

Do not modify these files. Do not delete them until equivalent features
are implemented in the PyQt6 app.

---

## 11. Technical Roadmap

### Phase 1 — Foundations ✅
- [x] Canonical project structure (folders, `__init__.py`, `main.py`)
- [x] `core/alpaca/client.py` — HTTP client with typed error handling
- [x] `core/alpaca/discovery.py` — UDP broadcast
- [x] `core/config.py` — persistent config
- [x] `ui/main_window.py` — main window with empty docks
- [x] `ui/theme.py` — dark Qt stylesheet

### Phase 2 — Mount Control ✅
- [x] `core/alpaca/telescope.py`
- [x] `workers/polling_worker.py`
- [x] `ui/panels/mount_panel.py`
- [x] `core/seestar/native_client.py` — TCP port 4700, jogging, master lock

### Phase 3 — Camera and FITS ✅ (partial)
- [x] `core/alpaca/camera.py`
- [x] `core/imaging/fits_writer.py` — full compliant headers
- [x] `workers/exposure_worker.py`
- [x] `ui/panels/camera_panel.py` + `ui/widgets/fits_viewer.py`
- [ ] `core/seestar/preview_client.py` — port 4801 binary stream (~1-5fps)
- [ ] ImageBytes fast path confirmed working on ZWO firmware

### Phase 4 — Sequencer
- [ ] `core/imaging/sequencer.py` — Light/Dark/Flat/Bias (A1-A12 chain, see docs/acquisition_sequence.md)
- [ ] `workers/sequence_worker.py`
- [ ] `ui/panels/sequencer_panel.py`

### Phase 5 — Filter Wheel and Focuser
- [ ] `core/alpaca/filterwheel.py` + `core/alpaca/focuser.py`
- [ ] `core/imaging/autofocus.py` — HFD V-curve
- [ ] Corresponding UI panels

### Phase 6 — Science
- [ ] Plate solving integration (local astrometry.net or API)
- [ ] Siril-compatible export (preprocessing scripts)
- [ ] Basic differential photometry
