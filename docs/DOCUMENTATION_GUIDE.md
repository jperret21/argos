# Argos — Documentation Guide

This file is the working plan and convention for documenting the codebase.
It exists so that any contributor (human or AI) writing documentation produces
output consistent with the style already established in the source.

The code is ~16k LOC across three layers (see `ARCHITECTURE.md`). Module-level
docstring coverage is already good; the gaps are: stale high-level docs, missing
`__init__.py` package docstrings, and the absence of a reader-facing API / module
reference. This guide tracks that work.

---

## 1. Documentation convention

Match the style already in the source (see `core/catalog/aavso.py`,
`core/photometry/aperture.py` for canonical examples). The house style is:

- **Module docstring, always.** One-sentence summary line, then a short paragraph
  on what the module is responsible for and — crucially — its boundaries
  (Qt-free? network-isolated? display-only?). State what it does *not* do.
- **Spec back-references.** When a module implements a spec, cite it inline:
  `(docs/photometry_plan.md §6 C1)`. Keep these accurate; they are load-bearing.
- **reST cross-references** for linking symbols: `:func:`, `:class:`, `:meth:`.
- **Dataclass fields** documented with a trailing `#` comment on each field,
  including units (`adu`, `e-`, `px`, `deg`, `mag`).
- **Concise over exhaustive.** Explain the *why* and the non-obvious; do not
  restate what the signature already says. No emoji, no pictographs (hard rule).
- **Layer discipline in prose.** `core/` is pure Python; `workers/` bridges with
  Qt signals; `ui/` holds no business logic. Documentation should reinforce these
  rules, never blur them.

Public functions/classes get a docstring with Args/Returns/Raises when the
contract is non-trivial. Private helpers (`_name`) get a one-liner if their intent
isn't obvious from the name.

---

## 2. Current module map

Layer rules and protocols live in `ARCHITECTURE.md`. This is the authoritative
file-by-file map (one-line purpose taken from each module's own docstring).

### core/ — pure Python, no PyQt6

**alpaca/** — ASCOM Alpaca device control (HTTP, backed by alpyca)
- `client.py` — low-level ASCOM Alpaca HTTP client
- `discovery.py` — ASCOM Alpaca UDP discovery
- `telescope.py` — telescope/mount wrapper
- `camera.py` — camera wrapper
- `focuser.py` — focuser wrapper
- `filterwheel.py` — filter wheel wrapper

**seestar/** — vendor-native protocol
- `native_client.py` — native JSON-RPC 2.0 TCP client for the Seestar S30 Pro

**stellarium/** — planetarium integration
- `protocol.py` — Stellarium Telescope Protocol v1.0 binary codec
- `server.py` — asyncio TCP server speaking that protocol

**imaging/** — frames, FITS, solving, metrics
- `imx585.py` — Sony IMX585 calibration constants (Seestar telephoto camera)
- `debayer.py` — Bayer demosaicing, CFA channel split, focus metrics (GRBG)
- `green.py` — the canonical green plane, one definition for the science stack
- `stretch.py` — display stretch transforms + measurement stats (display only)
- `metrics.py` — per-frame quality metrics: focus (§5) and acquisition QA (§7)
- `fits_writer.py` — science-grade FITS output
- `sequencer.py` — acquisition sequence model and expansion (pure logic)
- `session_log.py` — per-frame QA records persisted to `session.json` (§7)
- `platesolve.py` — plate-solving via ASTAP, recover a WCS (§6)
- `astrometry_session.py` — shared astrometry helpers (one path: live + Open-FITS)
- `sky_geometry.py` — airmass, Moon distance, phase

**catalog/** — external star catalogs
- `aavso.py` — AAVSO VSX + VSP HTTP clients (Qt-free, network-isolated)
- `photometry.py` — comparison-star selection for differential photometry
- `targets.py` — persistent target / comparison set for a session (§5 B4)

**photometry/** — differential photometry pipeline (all Qt-free, §6)
- `aperture.py` — aperture photometry on the green plane (§6 C1)
- `differential.py` — ensemble differential photometry (§6 C2)
- `lightcurve.py` — light-curve accumulator + CSV export (§6 C3)
- `airmass.py` — airmass + Julian date helpers (§6 C4)
- `session.py` — measure a target set on one solved frame (§6 C4)

**config.py** — persistent application configuration stored as JSON

### workers/ — QThread bridges, core + QtCore only

- `discovery_worker.py` — Alpaca UDP discovery thread
- `polling_worker.py` — continuous mount status polling
- `exposure_worker.py` — live preview, continuous short exposures
- `preview_processor.py` — off-thread display compute so preview never freezes
- `sequence_worker.py` — executes a multi-step acquisition plan
- `autofocus_worker.py` — HFD V-curve sweep and parabola fit
- `solve_worker.py` — runs an ASTAP plate-solve off the UI thread (§6)
- `astrometry_controller.py` — live page solve lifecycle + auto-solve policy
- `catalog_worker.py` — fetch VSX/VSP catalog objects off the UI thread
- `stellarium_worker.py` — bridge between the asyncio Stellarium server and Qt

### ui/ — PyQt6, no business logic, no network I/O

**Shell & chrome**
- `shell.py` — main window built around 3 modes
- `sidebar.py` — left navigation, switches the 3 modes
- `statusbar.py` — permanent top status strip (devices, tracking, last action)
- `theme.py` — Siril-inspired equilux dark palette
- `design.py` — design system, single source of truth for layout primitives
- `analysis_window.py` — standalone viewer for inspecting a single FITS frame

**pages/** — the three modes
- `connection_page.py` — connect Seestar devices + Stellarium server
- `imaging_page.py` — acquisition mode, the main work surface
- `configuration_page.py` — software settings (observer, site, paths, appearance)

**panels/**
- `log_panel.py` — session log viewer
- `manual_control_dialog.py` — Alpaca MoveAxis jogging
- `stellarium_card.py` — Stellarium server toggle card
- `photometry_setup_window.py` — "mission control" for a photometry session
- `photometry_window.py` — floating photometry window (§6 C5/C6)

**widgets/**
- `fits_viewer.py` — FITS/raw viewer (PyQtGraph), stretch + measurement tools
- `image_toolbar.py` — debayer-mode / channel selection
- `overlay_bar.py` — overlay-toggle bar under the image toolbar (§5 B1)
- `histogram_dock.py` — per-channel histogram, stretch, measurement readouts
- `camera_dock.py` — single-shot capture controls
- `focuser_dock.py` — focuser control (right rail)
- `mount_dock.py` — mount control (right side)
- `filterwheel_dock.py` — filter wheel control (right rail)
- `sequence_panel.py` — advanced multi-step acquisition table
- `astrometry_settings.py` — popup to tune solving + catalog queries
- `star_info_card.py` — on-image star-info card (§5 B2)
- `target_table.py` — target-set management table (§5 B4)
- `comparison_table.py` — full photometry table for a variable (popup)
- `lightcurve_panel.py` — live differential light-curve plot (§6 C5)
- `metrics_panel.py` — session metrics over time (§6 C6)

---

## 3. Documentation backlog

Check off as completed. Keep changes scoped so parallel work doesn't collide.

- [ ] **Refresh `ARCHITECTURE.md`.** Its module map predates `catalog/`,
      `photometry/`, and ~half the current workers/widgets. Reconcile it with
      §2 above. Verify the port numbers in "Communication Protocols".
- [ ] **Package docstrings.** Every `__init__.py` is empty. Add a one-paragraph
      docstring per package summarising what it groups and its layer rule.
- [ ] **Module reference.** A reader-facing reference per layer (core / workers /
      ui), expanding §2 with the key public classes/functions of each module.
- [ ] **Public-API audit.** For each `core/` and `workers/` public symbol,
      ensure Args/Returns/Raises are complete where the contract is non-trivial.
- [ ] **Cross-link the specs.** `capture_panel.md` and `photometry_plan.md` are
      the specs; ensure code back-references (`§…`) still point at the right
      sections after the recent refactors.
- [ ] **Getting-started / dev setup.** uv-managed project; document
      `uv run --extra dev pytest` and the run/sim workflow (`simulator_testing.md`).
- [ ] **Docstring lint pass.** The two modules with empty summary lines
      (`pages/_placeholder.py`, `panels/log_panel.py`) and any others.

---

## 4. Coordination

- Branch: `docs/code-documentation`.
- Documentation-only changes: prefer docstrings + Markdown under `docs/`. Do not
  alter behaviour. If a docstring reveals a bug, note it; fix it in its own commit.
- One area per commit (e.g. "docs(photometry): module reference") to keep the
  history reviewable and reduce merge conflicts across parallel contributors.
