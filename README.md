# ARGOS

**A desktop observing workspace for time-series photometry with smart telescopes.**

ARGOS helps an observer move from a connected telescope to a well-documented
observing session: acquire raw FITS frames, solve and identify the field, keep
the chosen target/comparison/check-star ensemble with the session, and review
what happened afterwards.

The point is to make a small smart telescope useful for measurement without
pretending that a live curve is a final scientific result. ARGOS keeps the raw
data intact. Calibration, registration and final photometry remain a separate,
auditable reduction workflow in Siril and `star_var_script`.

> **0.5.0 is the first beta of the new ARGOS**, a stable version with the new
> interface: a web interface in a desktop app, with the ARGOS server beside it;
> the PyQt6 app is retired. It was tested with its built-in simulator and with
> replays of real nights; it has not yet been used live on a telescope. Use it
> with the telescope attended, retain every raw FITS frame, and independently
> review or reduce the data before drawing a scientific conclusion.

## What ARGOS 0.5.0 does

- Runs as a desktop app: macOS on Apple silicon, and an x86_64 Debian/Ubuntu
  package as a technical preview.
- Connects to Seestar equipment through Alpaca, with discovery, pointing,
  framing, focusing controls and sequence capture.
- Writes a durable session record alongside unmodified raw FITS frames,
  including observing context, frame inventory and selected-star roles.
- Uses a local ASTAP installation to recover a WCS and align the solved field
  with catalogue information.
- Identifies and filters Gaia stars, variable stars, exoplanet hosts, deep-sky
  objects and available VSP references; catalogue lookups and caches remain
  under the observer's control.
- Supports target, comparison-star and check-star selection, with a quick-look
  differential-photometry preview during acquisition.
- Opens a completed session in Review: inspect frame-quality trends, curves,
  metadata, source FITS frames and field overlays without reconnecting a
  telescope, re-run the photometry on the raw frames, and export the curve CSV
  and the AAVSO Extended File report.
- Creates an explicit, local and redacted support bundle. ARGOS has no
  telemetry, analytics or automatic crash upload.

Read the documentation before the first session:

- [Install and release notes](https://perretjules.com/argos/install.html)
- [Observing with ARGOS: a complete session](docsrc/guide.md)
- [Identify a solved field](docsrc/field_identification.md)
- [What changed in 0.5.0](docsrc/release_0_5_0.md) (full notes:
  [`notes/release_0_5_0.md`](notes/release_0_5_0.md))
- [How the results were checked](docsrc/validation.md)

## Supported scope and roadmap

The **Seestar S30 Pro** is the 0.5.0 reference profile. S30 and S50 profiles
can be selected for connection, framing and exploratory work, but their
camera-specific assumptions still need field validation before they are used
for precision claims.

ARGOS is being extended to the full Seestar range. **DwarfLab support is
planned for the next ARGOS version**; it is not part of 0.5.0.

## Install

Release packages are attached to the
[ARGOS 0.5.0 release](https://github.com/jperret21/argos/releases/tag/v0.5.0):

- **macOS / Apple silicon:** download `ARGOS-0.5.0-macOS-arm64.dmg` and drag
  ARGOS to Applications. The app is signed ad hoc and not notarised, so macOS
  blocks its first launch: open it once and click **Done**, then on macOS 15
  or later use **System Settings › Privacy & Security › Open Anyway**; on
  macOS 11 to 14, right-click ARGOS in Applications and choose **Open**.
  `READ ME FIRST.txt` in the image has the steps. If macOS reports that it is
  damaged, remove the quarantine attribute deliberately:

  ```bash
  xattr -dr com.apple.quarantine "/Applications/ARGOS.app"
  ```

  The app declares macOS 11 as its minimum; its interface needs the WebKit of
  Safari 16.2 or later. It was tested on macOS 26 only.

- **Debian-family Linux / x86-64:** download `ARGOS_0.5.0_amd64.deb` and
  install it with:

  ```bash
  sudo apt install ./ARGOS_0.5.0_amd64.deb
  ```

  The Debian package is a technical preview (WebKitGTK 4.1, built on Ubuntu
  22.04, so it needs Ubuntu 22.04 or Debian 12 or later), not yet run on a
  Linux desktop. Validate it on the actual field
  computer before relying on it for a session.

ARGOS does not bundle ASTAP. Install [ASTAP](https://www.hnsky.org/astap.htm)
and an appropriate star database separately, then set both in
**Settings › Plate solving**.

## Run from source

```bash
git clone https://github.com/jperret21/argos.git
cd argos
uv sync --extra dev --extra qt --extra server
(cd web && npm install)

# the web UI (the server, Vite and the browser in one command; Ctrl+C stops both)
uv run python run_web.py           # your config and devices
uv run python run_web.py --sim     # the simulator, a separate dev config (~/.argos-dev)

# the retired Qt app (kept as the parity reference for tests)
uv run python main.py
```

Without a telescope, `run_web.py --sim` runs the built-in simulator and
`run_web.py --replay DIR` replays copies of real Seestar frames through it. For the
Alpaca path, the repository also includes a minimal mock (telescope and camera only):

```bash
# terminal 1 — mock Alpaca devices on 127.0.0.1:8765
uv run python scripts/mock_alpaca_server.py

# terminal 2 — ARGOS on its dev config; in Connection: Disconnect all, then Seestar,
# address 127.0.0.1, port 8765, Connect all
uv run python run_web.py --sim
```

See [`docsrc/simulator_testing.md`](docsrc/simulator_testing.md) for the
simulator workflow and [`docsrc/guide.md`](docsrc/guide.md) for the observing
guide.

## Privacy and field diagnostics

ARGOS does not collect telemetry or upload data automatically. Network-backed
catalogue and site lookups are initiated by the observer; local catalogue data
and caches can be inspected in Settings.

**Help › Create support bundle…** (also in **Settings › Privacy &
diagnostics**) creates a ZIP only when requested. It contains redacted logs and
optional redacted session metadata. Raw FITS, observer identity, network
addresses and private paths are excluded by design; site coordinates are
removed unless you ask for them. Review the ZIP and share it manually only when you decide
to do so.

## Development, CI and releases

GitHub Actions runs formatting, linting, tests and documentation checks on pull
requests and on pushes to `main` or `release/**`. A version tag such as
`v0.5.0` builds the macOS DMG and Debian package, then creates a GitHub release
draft with both assets. Publishing that draft remains a deliberate human step.

For local checks:

```bash
uv run --extra dev ruff check argos/ tests/ main.py packaging/
uv run --extra dev black --check argos/ tests/ main.py packaging/
# The suite runs in two processes; a single process can abort on the
# simulator fixtures. This is what CI does.
export QT_QPA_PLATFORM=offscreen
uv run --extra dev --extra qt --extra server pytest -q --deselect tests/ui/test_photometry_window.py
uv run --extra dev --extra qt --extra server pytest -q tests/ui/test_photometry_window.py
uv run --extra docs sphinx-build -W -b html docsrc /tmp/argos-docs
```

Contributions, issue reports and field observations are welcome. See
[`docsrc/CONTRIBUTING.md`](docsrc/CONTRIBUTING.md).

## License

ARGOS is distributed under the [GNU General Public License v3.0](LICENSE).
It does not bundle ASTAP, which remains a separate tool under its own licence.
