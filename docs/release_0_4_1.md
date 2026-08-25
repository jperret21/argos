# Argos 0.4.1 — release plan

> Branch: `release/0.4.1`, cut from `main` (note: `develop` is 127 commits
> behind and 0 ahead — `main` is the real integration branch).
> Last updated: 2026-08-25.

Three headline goals: **open the software to the Seestar family**, **ship
binaries**, and **make startup honest**. What follows is the plan and the
measurements it rests on.

---

## Measurements taken before planning

| Finding | Measured | Consequence |
|---|---|---|
| `run.sh` runs `xattr -dr com.apple.quarantine .venv/` every launch | **26.1 s**, 6754 files, **0** actually quarantined | This — not Python — is the slow startup. A splash shown from `main.py` cannot cover it: it happens before the interpreter starts. |
| Importing all of `argos.ui.shell` (numpy, astropy, pyqtgraph, alpyca) | 1.25 s | Imports are not the bottleneck. |
| `uv sync` on a warm venv | 0.09 s | Not the bottleneck either. |
| `FOCRATIO` in `fits_writer.py` | `160 / 50.0` → **f/3.2** | Every FITS written so far carries a wrong focal ratio. The S30 Pro is f/5.3 (160 mm / 30 mm); the `50.0` is an S50 aperture left in the code. |
| Version declared in 4 places | 2 said `0.2.0-redesign` | Included the FITS `SWCREATE`/`CREATOR` stamp. Fixed in `6b2a94f`. |

---

## Licence

Argos is **GPL v3** as of `6b2a94f`. PyQt6 is GPL v3, so shipping a binary
means redistributing PyQt6; a project announced as MIT could not do that.
This is the licence Siril and INDI use. ASTAP stays external — Argos never
bundles it.

---

## Workstreams

### A — Telescope profiles  *(the bulk of the release)*

Hardware specs are currently module-level constants, **duplicated**, and two
of them are imported into UI modules (so they bind at import time).

| File | Hard-coded |
|---|---|
| `core/alpaca/camera.py:29–33` | `PIXEL_SIZE_UM` `FOCAL_LENGTH` `BAYER_PATTERN` `INSTRUMENT` `TELESCOPE_NAME` |
| `core/imaging/fits_writer.py:27–31` | the same five, redefined |
| `core/imaging/metrics.py:47–48` | `ARCSEC_PER_FULL_PX` — imported by 2 UI modules |
| `core/imaging/imx585.py` | the whole module: EGAIN curve, read noise, full well, HCG threshold |
| `core/imaging/green.py:27`, `debayer.py:26` | GRBG pattern and the `G1=[0::2,0::2]` geometry |
| `core/alpaca/filterwheel.py:22` | `POSITION_NAMES` Dark/IR/LP |
| `core/alpaca/discovery.py:34` | `SEESTAR_AP_HOST` |
| `core/config.py:51–53` | `adc_bits` `full_well_adu` `linearity_max_adu` |

Resolution is already read from the driver at connect (`CameraXSize/YSize`)
— those 3840×2160 are only a fallback. Only two test assertions bake S30 Pro
values.

**Shape.** A Qt-free `argos/core/hardware/` package: `profile.py`
(`TelescopeProfile`, frozen, with derived properties), `catalog.py` (the
built-in registry — data, no logic), `active.py` (the process-wide current
profile). Derived quantities are never stored: `focal_ratio` and
`arcsec_per_full_px` are computed, which is what kills the f/3.2 bug.

**Access pattern.** A module accessor, like the existing
`theme.apply_palette()` — but constants become *functions called at the use
site* (`arcsec_per_full_px()`), never rebound module constants. The palette
approach requires a precise import order (see the comment in `main.py`) and
is fragile; this must not copy it.

**Sensors are separate from telescopes.** `imx585.py` becomes `sensors.py`,
a registry keyed by sensor name; the profile carries only the name. Science
rule: when the sensor is unknown, prefer the driver's `ElectronsPerADU`, and
failing that write **no** `EGAIN` at all rather than an invented number.

**Profiles shipped:**

| Profile | Aperture | Focal | f/ | Sensor | ″/px | Status |
|---|---|---|---|---|---|---|
| S30 Pro | 30 mm | 160 mm | 5.3 | IMX585 | 3.74 | **Reference — validated** |
| S30 | 30 mm | 150 mm | 5.0 | IMX662 | 3.99 | Unvalidated |
| S50 | 50 mm | 250 mm | 5.0 | IMX462 | 2.39 | Unvalidated |
| S50 Pro | 50 mm | 260 mm | 5.2 | 1/1.2″ 4K | — | Deferred — specs unconfirmed |

Optics for S30/S50 are known; their Bayer pattern, gain range and EGAIN
curve are **not**. Those profiles must be flagged unvalidated in the UI and
must leave photometric headers empty rather than approximate.

**Guard rails.** At connect, compare `Camera.Name` and the driver resolution
against the active profile; on mismatch, warn in the status bar and log
`WARN` — never switch silently mid-session. Existing `camera.*` config keys
become *overrides* on top of the profile, not a parallel source.

### B — Startup

- **B1** — make the `xattr` sweep conditional in `run.sh` and
  `main.py._fix_qt_plugin_path()` (sentinel file, invalidated when the venv
  is newer). Same for the two framework-cleanup `find` passes.
- **B2** — `argos/ui/splash.py`: logo, version, licence line, progress bar,
  status line. `main.py` imports the Qt minimum, shows the splash, then does
  the heavy imports with `processEvents()` between stages. Must close even
  if loading raises, and prefer an indeterminate bar over a fake percentage.

### C — Packaging

- **CI** — `.github/workflows/ci.yml`: ruff, black, pytest on macOS. Landed
  first, as the safety net for workstream A.
- **.dmg** — PyInstaller → `.app` → `create-dmg`, on tag `v*`, attached to
  the GitHub Release. Unsigned for 0.4.1 (alpha testers); Apple signing and
  notarisation budgeted for 0.5. ASTAP stays external, so its auto-detection
  must survive packaging and its "not found" message becomes real UI.
- **.deb** — **deferred to 0.4.2.** Argos has never run on Linux: the ASTAP
  search paths are macOS/Homebrew only, `run.sh` is macOS-specific, and
  PyQt6 under Wayland/X11 is unvalidated. Shipping a package that installs
  an app that will not start is worse than shipping nothing. A Linux CI job
  lands with that work, not before.

---

## Order

1. CI + `LICENSE` — the safety net *(done: `6b2a94f`, `ba35f02`)*
2. The 26 seconds — conditional `xattr`
3. Workstream A — profiles, in three commits: structure, migration of the
   eight sites, guard rails
4. The f/3.2 bug — falls out of A, plus a per-profile focal-ratio test
5. B2 — splash, after A so the active profile appears on it
6. C — `.dmg`
7. Deferred to 0.4.2 — Linux port then `.deb`

**Method note.** Workstream A touches science code. Every step ends with a
green `pytest` *and* a before/after FITS header comparison on a test frame:
for the S30 Pro every value must be identical except `FOCRATIO`, which must
go from 3.2 to 5.3. That is the only proof the refactor moved nothing
silently.
