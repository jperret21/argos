# Review (analysis page and frame viewer): Qt inventory and web redesign

Area 07. Author: spec agent, 2026-11-01. Source of truth: the code at branch `explore/web-ui`.
Everything below was read line by line; behaviours marked **(verified)** were also exercised
offscreen with `QT_QPA_PLATFORM=offscreen` on a real session
(`~/Argos/sessions/20260907T040723Z_XX_Cyg`, 24 lights, 9 curve CSVs, quality report).

## 0. Scope

### 0.1 Files

| Abbrev. | File | Lines | Role here |
|---|---|---|---|
| AP | `argos/ui/pages/analyze_page.py` | 780 | Review page (`AnalyzeScreen`), **in scope** |
| AW | `argos/ui/analysis_window.py` | 1197 | Frame Viewer window (`AnalysisWindow`), **in scope** |
| RV | `argos/core/session/review.py` | 279 | Session reader (behaviour) |
| BW | `argos/workers/photometry_batch_worker.py` | 402 | Batch re-run worker (behaviour) |
| LP | `argos/ui/widgets/lightcurve_panel.py` | 324 | Plot used inside every curve dock |
| TCP / CCP | `argos/ui/widgets/target_curve_panel.py` / `comparison_curve_panel.py` | 84 / 85 | Selector + plot of a Review curve dock |
| SR | `argos/ui/widgets/session_review.py` | 65 | Frame-quality plot |
| CT | `argos/ui/widgets/comparison_table.py` | 262 | Comparison quality table (Review) and ensemble table (Field photometry) |
| DH | `argos/ui/widgets/dock_host.py` | 180 | Dock chrome, toggle chips, toolbar style |
| PW | `argos/ui/panels/photometry_window.py` | 327 | Field photometry window opened by "Open curve CSV…" |
| VT / TT / MP | `variable_table.py` / `target_table.py` / `metrics_panel.py` (widgets) | 207 / 94 / 80 | Tabs of the Field photometry window |
| IT / OB / HD / FV | `image_toolbar.py` / `overlay_bar.py` / `histogram_dock.py` / `fits_viewer.py` (widgets) | 106 / 194 / 296 / 989 | Parts of the Frame Viewer |
| AS | `argos/ui/widgets/astrometry_settings.py` | 396 | Catalogue settings dialog (owned by the Settings spec) |
| LC | `argos/core/photometry/lightcurve.py` | 262 | CSV read/write, AAVSO writer |
| IP | `argos/ui/pages/imaging_page.py` (lines 2087-2089, 2248-2368) | partial | Batch re-run UI (the only caller of BW) |
| SH / SB | `argos/ui/shell.py` / `argos/ui/sidebar.py` | partial | Entry points into Review |

### 0.2 Every window, panel and pop-up in scope

| # | Element | Kind | Class, file:line | How it is opened |
|---|---|---|---|---|
| E1 | Review page | page in the shell's stack | `AnalyzeScreen` AP:59 | Sidebar "Review" (SB:42), View ▸ Review **F4** (SH:230-234), File ▸ Open session photometry… (SH:291-293) |
| E2 | Session card | `design.Card` | AP:133-155 | always at the top of E1 |
| E3 | Panel toolbar | `QToolBar` | AP:252-300 | always, under E2 |
| E4 | "Panels ▾" menu | `QMenu` on `QToolButton` (InstantPopup) | AP:278-285 | click |
| E5 | "Arrange ▾" menu | `QMenu`, rebuilt on `aboutToShow` | AP:287-294, AP:427-446 | click |
| E6 | Review workspace | `QMainWindow` used as a widget, nested/tabbed docks, inside a vertical `QScrollArea` | AP:81-108 | always |
| E7 | Source curve dock(s): "Source light curve", retitled "Target — {name}"; extra "Target {n}" | `QDockWidget` + `TargetCurvePanel` | AP:199-201, :522, :490-505 | default layout; one per target after Open session |
| E8 | Comparison dock(s): "Comparison stars", retitled "Comparison — {name}"; extra "Comparison star {n}" | `QDockWidget` + `ComparisonCurvePanel` | AP:205-210, :551, :448-488 | one per comparison after Open session; "+ Comparison plot below" |
| E9 | "Frame quality — FWHM" dock | `QDockWidget` + `SessionQualityPlot` | AP:202-204 | chip "FWHM" (see P1) |
| E10 | "Comparison quality" dock | `QDockWidget` + `ComparisonQualityTable` | AP:211-216 | default, tabbed right |
| E11 | "Frames" dock | `QDockWidget` + `QTableWidget` | AP:186-192, :217 | chip "Frames" (hidden by default) |
| E12 | "Session metadata" dock | `QDockWidget` + `QTableWidget` | AP:193-196, :218-220 | Panels ▾ ▸ Metadata (hidden by default) |
| E13 | "AAVSO export" dock | `QDockWidget` + `design.Card` | AP:118-131, :221 | Panels ▾ ▸ AAVSO export (hidden by default) |
| E14 | Floating dock windows | any dock, `setFloating(True)` | DH:68-74, AP:587-591 | dock title-bar float button, title double-click, Arrange ▸ Float … |
| E15 | Plot in-place affordances | pyqtgraph legend, "A" auto-range button, point click, (dead) hover | LP:100-109, :176-191 | inline |
| E16 | Quality plot context menu | pyqtgraph default `ViewBox` menu | SR:40 (no `setMenuEnabled(False)`) | right-click on E9 plot |
| E17 | "Open Argos session folder" | `QFileDialog.getExistingDirectory`, modal | AP:606-608 | Open session… |
| E18 | "Could not open session" | `QMessageBox.warning`, modal | AP:614 | load error |
| E19 | "Open session light curve" | `QFileDialog.getOpenFileName`, modal | AP:733-738 | Open curve CSV…, Ctrl+Shift+O |
| E20 | "Open FITS frame" | `QFileDialog.getOpenFileName`, modal | AP:766-771 | Open FITS… |
| E21 | "Frame unavailable" | `QMessageBox.warning`, modal | AP:717 | Open source frame / Frames double-click on a missing file |
| E22 | "Field photometry" window (6 tabs, export footer) | top-level `QWidget` window, non-modal, 960×700 (min 780×620) | PW:200-255 | AP:745-763 after E19 |
| E23 | "Export light curve" / "Export AAVSO" save dialogs | `QFileDialog.getSaveFileName`, modal | PW:306-308, :316-318 | E22 footer buttons |
| E24 | "Frame Viewer — {file}  ({w}×{h})" window (3 tabs, bottom bar) | top-level `QMainWindow`, non-modal, min 900×640 | AW:136-274, title AW:146, :337 | AP:712-730 (one reused window), AP:765-780 (new window each time) |
| E25 | "Open FITS" (viewer's own) | `QFileDialog.getOpenFileName`, modal | AW:437-445 | viewer "Open image…" |
| E26 | "Field identification & catalogue settings", Catalogues tab | `QDialog.exec()`, modal | AS:48-88, opened AW:564-569 | viewer "Catalogues / depth…" |
| E27 | Marker tooltips on the image | pyqtgraph scatter tips | FV:54-61; bodies AW:1000-1105 | hover a catalogue marker |
| E28 | Frame viewer image context menu | pyqtgraph `ViewBox` default menu (uncertain, see U3) | FV:138-141 | right-click on the image |
| E29 | Batch re-run: 4 info boxes, folder dialog, progress dialog, failure box | `QMessageBox`, `QFileDialog`, `QProgressDialog` | IP:2248-2368 | Photometry ▸ Re-run subs… (SH:282-285) |
| E30 | Shell entry points | menu actions | SH:197-201, :228-232, :236-238 | menu bar |

All tooltips are given verbatim in the control tables. There are no other pop-ups, timers or
context menus in the two in-scope files (checked by grepping every `QPushButton`, `QToolButton`,
`QAction`, `QCheckBox`, `QRadioButton`, `QComboBox`, `QSpinBox`, `QDoubleSpinBox`, `QSlider`,
`QLineEdit`, `QMenu`, `QMessageBox`, `QFileDialog`, `QDialog`, `QTabWidget`, `QTableWidget`,
`setShortcut`: AP and AW contain no `setShortcut` and no `QRadioButton`/`QSpinBox`/`QLineEdit`).

### 0.3 Overlaps with the other specs (to de-duplicate at consolidation)

| Spec | What it also inventories | Divergences to settle |
|---|---|---|
| 08 Review photometry | `PhotometryWindow` (all tabs), `LightCurvePanel`, the two curve panels, both comparison tables, `SessionQualityPlot`, `AnalyzeScreen`, the batch re-run | (a) 08 gives Review two sources, "Live run" and "Session", and moves the live Field photometry window into Review; this spec keeps Review offline and read-only and leaves live curves to Observe. (b) 08 removes the per-plot star selectors (one facet per star); this spec keeps one star per cell by default plus a picker and an "Ensemble overlay" cell. (c) 08 puts Frames and Metadata in bottom-drawer tabs; here Frames is a drawer and Metadata a rail card. (d) 08 uses `panels` for its Plots popover; here `panels` keeps its Observe meaning (rail toggle, P) and plot visibility lives in the `add-plot` menu. (e) Re-run: 08 keeps the live solve and live target set; here the default is session-scoped with a solve of the first frame (Q1). |
| 04 Viewer and image tools | `FitsViewer`, `ImageToolbar`, `OverlayBar`, `HistogramDock` in both hosts | This spec maps them only as hosted by the Frame Viewer (R2) and reuses 04's web components; the placement of Preview and Palette (moved to the Display card here) was not compared in detail. |
| 01 Shell and global | `dock_host.py`, menus, View ▸ Reset Window Layout, crash reporter | P18 (layout reset overwritten at close) concerns 01 too. |
| 02 Connection and Settings | `AstrometrySettingsDialog` | 1.12 lists only the entry point; 02 owns the form. |

## 1. Inventory (Qt, as it is today)

### 1.0 Analysis workflows end to end

**W1. Review a recorded session.**

1. Review page (F4). "Open session…" (card AP:140 or toolbar AP:257) opens E17 at
   `Config.sessions_path` (default `~/Argos/sessions`, `argos/core/config.py:24`).
2. `load_session(folder)` (RV:102-175) accepts the folder or its `session.json`; requires a
   `frames` list; reads optional `observation.json` (→ metadata) and
   `photometry_quality.json` (→ comparison quality); builds one `ReviewFrame` per row, reading
   `CCD-TEMP` from **every** FITS header (RV:167, :270-279). Never writes. Errors raise
   `SessionReviewError` → E18 (AP:613-615), page unchanged.
3. Page update (AP:616-647): title "{object} · {folder}", summary line, quality plot
   (`set_session`), curves = `load_session_curves` (RV:178-212: every
   `<root>/photometry/*.csv`; role from the filename prefix, identity from `targets.json`;
   duplicates keep the longest curve), quality table, one source dock per target
   (AP:507-528), one comparison dock per comparison (AP:530-557), default two-column tile
   (AP:332-407), Frames and Metadata tables, readiness line.
4. Output: nothing written. The dock arrangement is saved to `ui.review.layout` when the
   application closes (SH:450 → AP:418-421).

**W2. From a curve point to its source frame.** Click a point (LP:181-185 → AP:688-701) →
`nearest_light_frame(JD)` (RV:88-99: nearest light frame by |timestamp − JD|, no tolerance;
timestamps are exposure **starts** per `argos/core/imaging/session_log.py:38`, curve JDs are
exposure **midpoints**) → info label + "Open source frame" enabled when the file exists
(RV:84-86, recursive glob) → AP:703-730 loads it into the single reused Frame Viewer and
raises it. Alternative entry: double-click a row of the Frames dock (AP:192, :707-710).

**W3. Inspect a FITS frame (Frame Viewer).**

1. Opened by W2, by "Open FITS…" (AP:261 → :765-780, a new window each time) or the
   viewer's "Open image…" (IT:51 → AW:437-445).
2. `load()` (AW:306-340): 2-D float32 (3-D cubes averaged, AW:63-64), header keywords,
   full header text, `targets.json` of the enclosing session if any (AW:343-348); resets
   selection, WCS, catalogues and overlay chips; forces Preview to "Raw CFA"; reprocesses
   (`build_processed_frame`) → histogram + display with auto-stretch (FV:304-306).
3. "Identify field" (AW:461-473): ASTAP on the green plane, `build_solve_settings(live=False)`;
   result (AW:475-502) → WCS, coordinate grid shown, then catalogue fetch.
4. Catalogue fetch (AW:588-640, `CatalogWorker`): VSX variables, Gaia DR3 field stars,
   SIMBAD named objects, NASA exoplanet hosts, VSP comparison candidates around the session
   target (else `OBJECT`); projection through the WCS (AW:668-858): Gaia↔SIMBAD cross-match
   at 3″, bundled Messier/NGC/IC objects, cached exoplanet hosts, saved target/comparison/check
   markers, 8 px de-duplication; per-layer counts on the chips; Gaia G display limit.
5. Click on the image (FV:867-881 → AW:885-902): nearest visible catalogue marker within
   max(6, 14 × green width / display width) green px, priority targets > variables >
   comparisons > exoplanets > galaxies = nebulae/clusters > other > Gaia (AW:918-946); else
   `measure_star_at` (FWHM, HFD, eccentricity, SNR, peak, sky); no star → selection cleared.
6. Only config writes: `catalog.display_mag_limit` + `Config.save()` on slider release
   (AW:583-586) and E26 Save.

**W4. Import a curve CSV, then export (Field photometry window).** "Open curve CSV…"
(AP:259) or File ▸ Open session photometry… **Ctrl+Shift+O** (SH:197-201, :291-293, switches
to Review first) → E19 → `read_curves_csv` (LC:150-170; multi-curve exports keep
`star_id/role/name/auid`; a single-star file becomes **one "target" curve** named after the
file) → empty: log line only (AP:742-744) → new E22 with `load_curves(curves, obscode or
"XXX", default_band)` and `set_targets(targets.json)` from the CSV folder or its parent
(AP:747-760) → "Export measurements…" (PW:302-310, `write_curves_csv` LC:136-147) or
"Export target (AAVSO)…" (PW:312-327, `write_aavso` LC:204-254: target-role curves only;
DATE = JD_UTC midpoint `.6f`, MAG/MERR `.4f`, FILT = configured band, TRANS NO, MTYPE STD,
CNAME ENSEMBLE, CMAG na, KNAME/KMAG from the first check curve at the same JD, AMASS `.3f`
or na, CHART = the single VSP chart of the comparisons (`targets.py:219-228`) or na).

**W5. Batch re-run over saved subs** (only caller: IP; Photometry ▸ Re-run subs…,
SH:282-285). Preconditions (IP:2255-2281): no batch running, a **live** plate solve exists,
the live target set has ≥ 1 target and ≥ 1 comparison. Folder dialog → `*.fits` sorted by
modification time, else recursive (IP:2286-2289). Request (IP:2293-2307): parameters from
config (`params.py:48-68`: aperture floor 4 px, 2.5 × FWHM, annulus 8-12 px, read noise
1.5 e-, saturation `camera.linearity_max_adu` 50000, band, ≥ 2 comps, aperture tracking on),
e-/ADU from `camera.egain_table` or the sensor model (IP:2320-2335), output folder
`<sessions_path parent>/targets`, site, diagnostics flag. Progress dialog (IP:2308-2318).
Worker (BW:96-155): per frame read primary HDU, JD = DATE-OBS + EXPTIME/2 (BW:359-390),
green plane, reference or tracked WCS (BW:220-254), series FWHM measured once on the first
readable frame (BW:201-218), `measure_frame`, keep a point when either a differential
magnitude or a relative flux exists (BW:256-317), BJD_TDB/airmass when the site is known;
then systematic floor (BW:320-338), one canonical CSV per star (BW:392-402), check-star RMS
and tracking totals to the log/diagnostics. Cancel stops at the next frame boundary and still
writes and adopts the partial curves. Done (IP:2337-2367): curves merged into the live
engine store (`adopt_curves`, acquisition_engine.py:258-267) and the Field photometry window
opens in its live context.

**W6. Layout.** Tile (AP:332-407), reset (AP:423-425), float/dock (AP:587-591), show/hide
chips; `ui.review.layout` = base64 `QMainWindow.saveState()` (AP:52), restored at construction
(AP:110, :409-416), saved at application close (SH:443-450).

### 1.1 Review page shell, toolbar and menus (`AnalyzeScreen`, AP:59; page in the shell stack; non-modal; full page)

- Purpose: open a finished session and arrange the review panels; launch the CSV and FITS
  companion windows.

| # | Control | Qt type | Label / tooltip (exact text) | Default / range | Enabled / visible when | Shortcut | Action: handler → effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Open session (card) | `design.PrimaryButton` | "Open session…" / "Open the folder containing session.json" | — | always | — | AP:140-142 → `_open_session` AP:605 → W1 | reads `sessions_path` |
| 2 | Open session (toolbar) | `QAction` | "Open session…" / none | — | always | — | AP:257-258 → AP:605 (duplicate of #1) | — |
| 3 | Open curve CSV | `QAction` | "Open curve CSV…" / none | — | always | (Ctrl+Shift+O via shell, 1.14 #3) | AP:259-260 → `_open_lightcurve` AP:732 → W4 | — |
| 4 | Open FITS | `QAction` | "Open FITS…" / none | — | always | — | AP:261-262 → `_open_frame` AP:765 → E20 → new E24 | — |
| 5 | Add comparison plot | `QAction` | "+ Comparison plot below" / "Add an independently selectable comparison-star plot below the last comparison plot" | preselects the first comparison not shown elsewhere, else the first one | always (also with no session) | — | AP:263-267 → AP:448-488: new `ComparisonCurvePanel` in dock "Comparison star {n}" split under the last comparison dock; scroll extent grows | saved geometry only (dock not recreated at launch, P18) |
| 6 | Toggle "Source curve" | checkable `QAction` (`toggleViewAction`, DH:122-131) | "Source curve" (becomes "Target — {name}" after a session, P3) / "Show or hide Source curve. Drag its title bar to arrange it; double-click to detach it." | checked = visible | always | — | AP:270-277 → show/hide dock | `ui.review.layout` |
| 7 | Toggle "FWHM" | same | "FWHM" / "Show or hide FWHM. Drag its title bar…" | unchecked (P1) | always | — | same → shows E9 **as a floating window** (P1) | idem |
| 8 | Toggle "Comparison stars" | same | "Comparison stars" (becomes "Comparison — {name}") / same pattern | | always | — | same | idem |
| 9 | Toggle "Comparison quality" | same | "Comparison quality" / same pattern | checked | always | — | same | idem |
| 10 | Toggle "Frames" | same | "Frames" / same pattern | unchecked | always | — | same | idem |
| 11 | Panels ▾ | `QToolButton` InstantPopup + `QMenu` | "Panels ▾" / none | — | always | — | AP:278-285 | — |
| 12 | Panels ▸ Metadata | checkable `QAction` | "Metadata" / "Show or hide Metadata. Drag…" | unchecked | | — | toggles E12 | idem |
| 13 | Panels ▸ AAVSO export | checkable `QAction` | "AAVSO export" / "Show or hide AAVSO export. Drag…" | unchecked | | — | toggles E13 | idem |
| 14 | Arrange ▾ | `QToolButton` InstantPopup + `QMenu` | "Arrange ▾" / "Float, re-dock or reset the Review workspace" | — | always; pushed into the toolbar overflow at ≤ 1360 px (P3) | — | AP:287-294; menu rebuilt by AP:427 | — |
| 15 | Arrange ▸ Tile | `QAction` | "Tile plots — 2 columns" | — | | — | AP:429-430 → `_apply_default_layout` AP:332 | no |
| 16 | Arrange ▸ Restore default | `QAction` | "Restore default layout" | — | | — | AP:431-432 → `reset_layout` AP:423: `ui.review.layout = None` then tile | clears key |
| 17 | Arrange ▸ Float/Dock {panel} | 7 `QAction` | "Float Source curve", "Float FWHM", "Float Comparison stars", "Float Comparison quality", "Float Frames", "Float Metadata", "Float AAVSO export" ("Dock …" when floating) | — | | — | AP:434-440 → AP:587-591 toggle floating, show, raise | layout |
| 18 | Arrange ▸ Float/Dock extra targets | `QAction` per extra source dock | "Float {dock title}" | — | ≥ 2 targets | — | AP:441-446 (extra comparison docks missing, P4) | layout |
| 19 | Tile (toolbar) | `QAction` | "Tile plots — 2 columns" / "Arrange active source, comparison and FWHM plots in a two-column grid" | — | always | — | AP:295-297 → AP:332 (duplicate of #15) | no |
| 20 | Reset layout (toolbar) | `QAction` | "Reset layout" / none | — | always | — | AP:298-299 → AP:423 (duplicate of #16) | clears key |
| 21 | Dock title bar drag | `QDockWidget` Movable | dock title | — | always | — | drag to an area, onto a dock to tab it, nested splits (AP:83-89, DH:68-74) | layout |
| 22 | Dock float button / title double-click | `QDockWidget` Floatable | title-bar button | — | always | — | detach to a top-level window (E14) | layout |
| 23 | Dock close button | `QDockWidget` Closable | title-bar × | — | always | — | hide dock; extra docks have no chip to reopen (P4) | layout |
| 24 | Dock separators | `QMainWindow` splitter handles | — | start heights 280 px per row (AP:385-387); minima 280/240/220/220 (AP:237-240) | — | — | resize | layout |
| 25 | Workspace scroll | `QScrollArea`, vertical only | — | workspace min height max(660, 280 × rows) (AP:102, :567-585) | — | wheel | scroll the dock wall | — |
| 26 | Tabbed-dock tab bar | `QTabBar` created by `tabifyDockWidget` | "Session metadata" / "AAVSO export" / "Comparison quality" | Comparison quality raised (AP:394-401) | when ≥ 2 tabified docks visible | — | switch tab | layout |

- Displayed data: page heading "Review" (AP:77); session title (brass metric) "No session
  selected" → "{object_name} · {root.name}" (AP:138, :617); summary
  "Started {started_utc or 'unknown'} · {N} frames ({count} {type}, …) · Filters:
  {name}: {count}, … or — · {software}" (AP:618-623), e.g. "Started
  2026-09-07T04:07:25.649170+00:00 · 24 frames (24 Light Frame) · Filters: IR: 24 · Argos
  v0.4.1" (verified); readiness line (AP:641-645). Refreshed only on Open session.
- Implicit behaviours: constructor tiles then restores the saved state (AP:109-110);
  `showEvent` refreshes the AAVSO info from Settings (AP:593-595); Open session re-tiles,
  clears the point selection and enables all docks (`setEnabled(True)`, AP:646-647, never
  disabled anywhere: dead code); companion windows are kept in `self._windows` for the life
  of the page (AP:66, :726, :763, :780); no timers; no device dependency (works offline).
- Messages: E18 "Could not open session" + one of "No session.json in {root}", "Could not read
  session.json: {exc}", "session.json has no frame list" (RV:110-118); readiness line =
  " · ".join of: "Could not read observation.json.", "Ignored an invalid
  photometry_quality.json.", "Could not read photometry_quality.json.", "Ignored an invalid
  frame row in session.json.", "Ignored a malformed frame row in session.json.", "Missing FITS
  frame: {filename}" (one per frame), "Could not read preview curve: {name}" (RV:211), "No
  light frames were recorded.", "No FITS frames found in this session folder." (RV:76-82), or
  "Session structure looks complete." (AP:643); E21 "Frame unavailable" / "Could not find
  {filename}." (AP:717); log only: "No valid photometry rows in {path}" (AP:743), "Review
  layout restore failed: {exc}" (AP:416).
- Problems found:
  - **P1 (verified)** The FWHM dock is never placed in the workspace. `_apply_default_layout`
    snapshots `isHidden()` (AP:348) before any dock has been shown (first call AP:109), so
    FWHM is skipped; after Open session it is still hidden, so it is skipped again. Probe:
    `dockWidgetArea = NoDockWidgetArea`, `isFloating() = True`, parent not the workspace,
    at init and after opening the sample session. Clicking "FWHM" then opens a separate
    floating window; `restoreState` cannot place it either (not a child of the workspace).
    The "Comparison stars" dock has the same state until a session with comparisons is opened.
  - **P2** Duplicates: "Open session…" twice (AP:140, :257); "Tile plots — 2 columns" twice
    (AP:295, :429); "Reset layout" and "Restore default layout" call the same handler under two
    names (AP:298, :431); Tile and Reset produce the same arrangement (Reset only also clears
    the saved key).
  - **P3 (verified)** Chips rename themselves to the dock title once a session is open
    ("Target — XX Cyg", "Comparison — 000-BCK-396"), because `toggleViewAction` follows
    `setWindowTitle` (AP:522, :551) after `style_toggle_action` set the short label (AP:271);
    the toolbar then overflows: at 1360 px wide "Arrange ▾", "Tile plots" and "Reset layout"
    sit in the overflow chevron.
  - **P4** Extra target and comparison docks have no chip; once closed they come back only by
    reopening a session, because Tile/Reset re-tile **visible** docks only (AP:340-347).
    Added comparison docks are missing from the Arrange menu (AP:441 iterates source docks
    only). Added plots cannot be removed, only hidden.
  - **P5 (verified)** The readiness line is always drawn in the warning colour, including
    "Session structure looks complete." (AP:149-152, :643). One "Missing FITS frame" per
    frame is joined into one line inside a card capped at 112 px (AP:154): clipped.
  - **P12** Session loading runs on the UI thread and opens one FITS header per frame
    (RV:167): 0.26 s for 195 frames measured; linear in frame count.
  - **P13** `read_curves_csv` raises `KeyError` on a CSV without `jd_utc`/`mag`/`mag_err`
    columns (LC:175-178, only `TypeError`/`ValueError` caught at LC:162); neither
    `_open_lightcurve` nor `load_session_curves` (RV:210 catches `OSError, ValueError`) catches
    it: the exception reaches the crash reporter (`main.py:145`), and Open session leaves the
    page half updated (title and quality plot of the new session, curves of the old one).
  - **P14** Silent failures: empty CSV (log only, AP:742-744); unreadable FITS from "Open
    FITS…" shows an empty viewer (AP:778-779 ignores `load()`'s result); unreadable review
    frame does nothing (AP:727).
  - **P15** Window reuse is inconsistent: review frames reuse one viewer (AP:721-726), "Open
    FITS…" creates a new one each time (AP:776), each CSV a new Field photometry window; all
    are retained until the page is destroyed.
  - **P18** Layout persistence: dynamic docks (AP:464, :498) do not exist at launch, so their
    saved geometry is dropped. View ▸ Reset Window Layout clears `ui.review.layout` and says
    "Window layout will reset on next launch." (SH:452-457), but `closeEvent` re-saves the
    current layout first (SH:622 → :450): the reset never happens.
  - **P23** `dock.setEnabled(True)` loop (AP:646-647) has no counterpart: dead code.

### 1.2 Source light curve dock(s) (E7; `TargetCurvePanel` TCP:14 + `LightCurvePanel(view="target")` LP:25 + point row AP:169-183; non-modal dock)

- Purpose: the differential magnitude of one science target (or all targets) and the entry
  point to the source frame of a point.

| # | Control | Qt type | Label / tooltip (exact text) | Default / range | Enabled / visible when | Shortcut | Action: handler → effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Target selector | `QComboBox` with caption "Target" | options: one per target curve (name, else AUID, else key), then "All targets" / "Choose the target shown in this source light curve" | the dock's own target (`preferred_key`) | items only when target curves exist | — | TCP:37-40, :51-70 → `_refresh_plot` TCP:77-84 → `LightCurvePanel.set_curves` | no |
| 2 | Show uncertainties | `QCheckBox` | "Show uncertainties" / "Show the per-image photometric uncertainty" | checked | always | — | LP:85-89 → LP:302-304, :251-258 error-bar visibility | no |
| 3 | Relative flux | `QCheckBox` | "Relative flux" / "Median-normalised live preview; final normalisation and detrending belong to post-processing" | unchecked | always | — | LP:90-95 → LP:306-319: y = relative_flux / median, axis "Relative flux (median-normalised)", y not inverted | no |
| 4 | Point click | pyqtgraph `sigPointsClicked` | — | left button | points present | — | LP:181-185 → AP:688-701 (W2) | no |
| 5 | Point hover | pyqtgraph `sigPointsHovered` | — | — | **never fires** (P6) | — | LP:176-180 → AP:683-686 | — |
| 6 | Zoom / pan | pyqtgraph `ViewBox` mouse | wheel zoom, left-drag pan, right-drag axis scale; context menu disabled (LP:102) | auto-range on load (LP:321-324) | always | — | — | no |
| 7 | Auto-range "A" | pyqtgraph corner button | "A" | appears after a manual zoom | | — | `autoRange` | no |
| 8 | Legend entry click | pyqtgraph `LegendItem` | series name | visible | ≥ 1 series | — | hides the series; error bars and saturation marks follow (LP:186-191, :251-258) | no |
| 9 | Open source frame | `design.SecondaryButton` | "Open source frame" / none | disabled | after a click matched a light frame whose file exists (AP:701) | — | AP:179-182 → AP:703-705 → AP:712-730 (reused E24) | no |

- Displayed data: caption "Source light curve" above the plot (LP:46-55); y "Differential
  mag" inverted (LP:58, :107), x "Time (JD UTC)" shown with an SI multiplier "(x1e+06)"
  (verified screenshot); markers `o` 6 px in the series palette SUCCESS, CYAN, WARNING,
  VARIABLE, ACCENT, DANGER (LP:20-22, :140-149); saturated points as red `x` 11 px
  (LP:152-160); vertical error bars without caps (LP:247); legend inside the plot; point
  info label (AP:174-178): "Hover a point to inspect it; click to select it." then, after a
  session, "Hover a point to inspect it; click to select its source frame." (AP:636-638);
  on click "{name} · {filename} · {ISO UTC or 'unknown UTC'} · FWHM {x.xx|—} · HFD {x.xx|—}"
  or "{name} · no logged light frame matches JD {jd:.6f}" (AP:694, :697-700); (dead) hover
  text "{name} · JD {jd:.6f} · preview value {mag:.4f} ± {error:.4f}" (AP:684-686).
- Implicit behaviours: one dock per target after Open session (AP:507-528), titled
  "Target — {name or AUID or index}"; unused docks titled "Target light curve" (first one
  kept visible, others hidden). The label and button live only in the **first** source dock
  but also receive clicks from every comparison plot (AP:163-166).
- Problems found:
  - **P6 (verified)** Hover is dead: the scatter items are created without `hoverable=True`
    (LP:140-149); pyqtgraph 0.13.7 emits `sigHovered` only when hoverable
    (`ScatterPlotItem.hoverEvent`), so `point_hovered` never fires and the instruction "Hover a
    point to inspect it" is false.
  - **P7** Feedback for comparison-plot clicks lands in the first source dock, which may be
    hidden or scrolled away (AP:165-166, :174-183).
  - **P16 (verified)** Three stacked headings per plot (dock title, "Target" caption,
    "Source light curve" caption) cost about 50 px per plot; the legend sits on the data; the
    JD axis with "(x1e+06)" is unreadable; JD 6 and magnitude 4 decimals in the point text
    differ from BRAND (JD 5, magnitude 3).
  - **P19** Check-star curves appear here as targets: `_curve_identity` gives every file that
    does not start with `comparison_` the target role (RV:218), while the live engine writes
    `check_<object>_<star>.csv` (acquisition_engine.py:1266).
  - **P21** Recorded per-point data never shown in Review: `suspect` flag (no parameter in
    LP:115-125), BJD_TDB, airmass, comparisons used, formal error, `sigma_syst`.
  - **P40** "All targets" overlays any number of series (BRAND §10 allows at most three).

### 1.3 Comparison star dock(s) (E8; `ComparisonCurvePanel` CCP:14 + `LightCurvePanel(view="comparison")`; non-modal dock)

- Purpose: one comparison star's residual about its own median, on its own scale.

| # | Control | Qt type | Label / tooltip (exact text) | Default / range | Enabled / visible when | Shortcut | Action: handler → effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Comparison selector | `QComboBox` with caption "Comparison star" | one per comparison curve, then "All comparison stars" / "Choose the comparison star shown in this diagnostic" | the dock's comparison | items when comparisons exist | — | CCP:38-41, :52-71 → CCP:78-85 | no |
| 2 | Show uncertainties | `QCheckBox` | as 1.2 #2 | checked | | — | LP:85-89 | no |
| 3 | Relative flux | `QCheckBox` | as 1.2 #3; axis becomes "Δ relative flux" (LP:313-316) | unchecked | | — | LP:90-95 | no |
| 4 | Point click | pyqtgraph | — | | | — | → AP:688 (feedback in the first source dock, P7) | no |
| 5 | Point hover | pyqtgraph | — | never fires (P6) | | — | → AP:683 | — |
| 6 | Zoom / pan | pyqtgraph | as 1.2 #6 | | | — | — | no |
| 7 | Auto-range "A" | pyqtgraph | "A" | | | — | — | no |
| 8 | Legend entry click | pyqtgraph | series name | | | — | hide series | no |

- Displayed data: caption "Comparison-star diagnostics"; y "Δmag from own median" inverted,
  each series minus its median (LP:63, :238-241); x "Time (JD UTC)".
- Implicit behaviours: one dock per saved comparison (AP:530-557), titled
  "Comparison — {name}"; unused docks hidden and titled "Comparison star"; the quality
  table selects a key in the **first** comparison panel only (AP:559-565).
- Problems found: **P9** "+ Comparison plot below" duplicates comparison #1 when every
  comparison already has a plot, which is the default (AP:454-460). **P10** A quality-table
  click rewrites the first panel's star (creating a duplicate) instead of showing that star's
  own plot; for comparisons without an AUID the table key is the name (CT:252) while the
  curve key is `comparison:pos:…` (RV:239), so the click silently does nothing. "All
  comparison stars" overlays up to all comparisons (8 in the sample): above BRAND's 3-series
  limit (**P40**).

### 1.4 Frame quality dock (E9; `SessionQualityPlot` SR:21, dock "Frame quality — FWHM" AP:202)

| # | Control | Qt type | Label / tooltip (exact text) | Default / range | Enabled / visible when | Shortcut | Action: handler → effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Metric | `QComboBox` with caption "Quality trend" | "FWHM (green px)", "HFD (green px)", "Sensor temperature (°C)", "Sky background (ADU)", "Star count", "Eccentricity" / none | FWHM | always | — | SR:29-37 → SR:54-65 replot | no (the class docstring says "persisted", SR:22) |
| 2 | Zoom / pan | pyqtgraph | — | | | — | — | no |
| 3 | Context menu | pyqtgraph default `ViewBox` menu | "View All", "X axis", "Y axis", "Mouse Mode", "Plot Options", "Export…" | | right-click | — | pyqtgraph | no |
| 4 | Auto-range "A" | pyqtgraph | "A" | | after zoom | — | — | no |

- Displayed data: light frames with a timestamp; x "Elapsed time (h)" since the first light
  (RV:68-74), y = the metric from `session.json` (sensor temperature from FITS headers);
  brass line with dots (SR:44-46).
- Problems found: **P1** (not placed in the workspace). **P17** The dock title stays "Frame
  quality — FWHM" whatever metric is chosen; the elapsed-hours axis cannot be compared or
  linked with the JD axis of the curves. **P38** Only this plot keeps pyqtgraph's generic
  context menu (the curve plots disable it, LP:102). **P39** Brass used as a data colour
  (SR:45), against BRAND §3.

### 1.5 Comparison quality dock (E10; `ComparisonQualityTable` CT:208; tabbed right, raised by default)

| # | Control | Qt type | Label / tooltip (exact text) | Default / range | Enabled / visible when | Shortcut | Action: handler → effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Row selection | `QTableWidget`, single row, read-only | — | none | report has entries | — | CT:228-232, :259-262 `star_selected(key)` → AP:559-565 (P10) | no |

- Displayed data: hint "No comparison-quality report in this session." or "Leave-one-out
  live-preview diagnostic · minimum {min_points} valid points. Select a row to show its
  curve." (CT:221, :239-246); columns "Name", "Samples", "Scatter (mag)" (`.4f`), "Formal
  error (mag)" (`.4f`), "Live status" with "Stable", "Unstable", "Noisy", "Waiting for 10
  points", "Waiting for data" (CT:29-51). Source: `photometry_quality.json` written live by
  `acquisition_engine.py:1395-1412` from `quality.py:22-97`.
- Problems found: **P22** "Live status" and "Waiting for data" are live wording in an
  offline review; "Waiting for 10 points" is hard-coded although `criteria.min_points` is in
  the report; the report's `selection_status` and `scientific_note` (quality.py:87-91) are
  not shown; not sortable.

### 1.6 Frames dock (E11; `QTableWidget(0, 9)` AP:186-192; bottom; hidden by default)

| # | Control | Qt type | Label / tooltip (exact text) | Default / range | Enabled / visible when | Shortcut | Action: handler → effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Row double-click | `cellDoubleClicked` | — | | rows present | — | AP:192 → AP:707-710 → AP:712-730 (E21 if missing) | no |
| 2 | Cell editing | default `QTableWidget` edit triggers | — | editable (no `setEditTriggers`) | always | typing / double-click | edits the cell text only; no effect on data (P11) | no |

- Displayed data: columns "UTC" (ISO seconds or —), "Type", "Filter" (or —), "Exp (s)"
  (`%g`), "Gain", "FWHM", "HFD", "Temp (°C)" (`.2f` or —), "File" (AP:187-189, :649-666). Not
  sortable.
- Problems found: **P11** editable cells; a double-click both opens the frame and starts
  editing. **P20** `star_count`, `sky_adu`, `peak_adu`, `eccentricity` are loaded
  (RV:37-40) but not shown; missing files are not marked.

### 1.7 Session metadata dock (E12; `QTableWidget(0, 2)` AP:193-196; tabbed right; hidden by default)

| # | Control | Qt type | Label / tooltip | Default | Enabled / visible when | Shortcut | Action | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Cell editing | default edit triggers | — | editable | always | typing | edits text only (P11) | no |

- Displayed data: "Field" / "Value" rows "Session folder", "Object", "Started UTC",
  "Software", "Observer" (or —), "Frame count", then every `observation.json` key, sorted
  (AP:668-681). The `summary` block of `session.json` (mean HFD, FWHM, sky, star count) is
  not shown (P20).

### 1.8 AAVSO export dock (E13; `design.Card("AAVSO export")` AP:118-131; tabbed right; hidden by default)

- No controls. Displayed data: "Observer code" = `observer.obscode` in brass, or
  "unset — add it in Settings" in the warning colour (AP:312-325); "Band / filter" =
  `photometry.default_band`, default "TG" (AP:309-310, :326). Refreshed at construction and
  on every page show (AP:593-595).
- Problems found: **P8** The panel is titled "AAVSO export" but has no export action; a
  session opened with "Open session…" cannot be exported from Review at all (the only export
  path is W4, one CSV at a time, see P31/P32).

### 1.9 Review file dialogs and message boxes (AP)

| # | Control | Qt type | Label / text (exact) | Default / filter | When | Shortcut | Action → effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Open session folder | `QFileDialog.getExistingDirectory`, modal | "Open Argos session folder" | start `sessions_path` | 1.1 #1/#2 | — | AP:606-610 → W1; cancel = no-op | — |
| 2 | Load error | `QMessageBox.warning`, modal | "Could not open session" / {SessionReviewError} | OK | load fails | — | AP:613-615 | — |
| 3 | Open curve CSV | `QFileDialog.getOpenFileName`, modal | "Open session light curve" | start `sessions_path`, "CSV (*.csv);;All files (*)" | 1.1 #3 | Ctrl+Shift+O (shell) | AP:733-740 → W4 | — |
| 4 | Open FITS | `QFileDialog.getOpenFileName`, modal | "Open FITS frame" | start `sessions_path`, "FITS (*.fits *.fit *.fts);;All files (*)" | 1.1 #4 | — | AP:766-773 → E24 | — |
| 5 | Frame unavailable | `QMessageBox.warning`, modal | "Frame unavailable" / "Could not find {filename}." | OK | review frame file missing | — | AP:715-718 | — |

### 1.10 Field photometry window (E22; `PhotometryWindow` PW:200; top-level, non-modal; as opened from Review)

- Purpose in Review: plot a reloaded CSV and export it. The window is shared with the live
  Observe workflow; Review connects **none** of its signals (AP:747-763), so everything that
  edits the live target set is inert here. The Observe photometry spec owns its live use.

| # | Control | Qt type | Label / tooltip (exact text) | Default / range | Enabled / visible when (Review) | Shortcut | Action: handler → effect (Review context) | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Tabs | `QTabWidget` | "Variable stars", "Light curve", "Metrics", "Targets", "Comparison stars", "Aperture · references" | "Variable stars" (first) | always | — | PW:228-236 | no |
| 2 | Variable filter | `QLineEdit` (clear button) | placeholder "Filter by designation or type…" / "Case- and space-insensitive; for example, XX Cyg or xxcyg" | empty | table always empty in Review | — | VT:74-79 → filter | no |
| 3 | Brightest mag ≤ | `QDoubleSpinBox` | caption "Brightest mag ≤" / "Show variables whose brightest catalogued magnitude is at or brighter than this limit" | 0.0 = "Any", 0-20, step 0.5, 1 dec. | | — | VT:80-90 | no |
| 4 | Column sort | header click | "", "Name", "Type", "Mag", "Period (d)", "Sep (′)" | unsorted | | — | VT:105-106 | no |
| 5 | Row double-click | table | — | | | — | VT:107 → `target_requested` (unconnected: dead) | — |
| 6 | Set as target | `QPushButton` | "Set as target" / "Make this variable a photometry target (comparison stars are\npicked automatically when none are chosen yet). Same action as\nclicking its circle on the image." | | | — | VT:111-117 → unconnected (dead) | — |
| 7 | Show uncertainties | `QCheckBox` | as 1.2 #2 | checked | | — | LP:85-89 | no |
| 8 | Relative flux | `QCheckBox` | as 1.2 #3 | unchecked | | — | LP:90-95 | no |
| 9 | Plot click / zoom / pan / "A" | pyqtgraph (target + comparison plots X-linked, splitter 320/220) | — | | | — | LP:67-81; clicks unconnected | no |
| 10 | Legend click | pyqtgraph | — | | | — | hide series | no |
| 11 | Metric | `QComboBox` with caption "Metric:" | "Airmass", "FWHM (green px)", "Sky (ADU)", "HFD (green px)", "Star count", "Sensor temp (°C)" | Airmass | always empty in Review | — | MP:15-23, :38-41 | no |
| 12 | Targets row select | `QTableWidget` | "Role", "Name", "RA", "Dec", "Mags" | | rows if `targets.json` found | — | TT:37-45 → `star_selected` unconnected | no |
| 13 | Remove selected (targets) | `QPushButton` | "Remove selected" | | | — | TT:47-48 → `remove_requested` unconnected (dead) | — |
| 14 | Copy TSV (targets) | `QPushButton` | "Copy TSV" | | | — | TT:49-50, :85-93 → clipboard | — |
| 15 | Automatically propose | `QSpinBox` | caption "Automatically propose", suffix " calibrated stars" / "Number of calibrated VSP comparison stars Argos proposes when a target is selected" | 5, 1-12 | | — | CT:79-91 → `auto_count_changed` unconnected (dead) | — |
| 16 | Comparisons row select | `QTableWidget` 10 columns | "Name", "AUID", "RA (J2000)", "Dec (J2000)", "Catalogue mags", "Source", "Samples", "Scatter (mag)", "Formal error (mag)", "Live status" | | rows if `targets.json` found | — | CT:93-103 → unconnected | no |
| 17 | Remove selected (comparisons) | `QPushButton` | "Remove selected" | | | — | CT:110-111 → unconnected (dead) | — |
| 18 | Refresh catalogue | `QPushButton` | "Refresh catalogue" / "Fetch VSP comparison-star proposals again for the solved field" | | | — | CT:113-118 → unconnected (dead) | — |
| 19 | Recommend from pilot | `QPushButton` | "Recommend from pilot" / "Replace VSP suggestions using SNR, saturation and brightness measured on the solved pilot image" | | | — | CT:119-124 → unconnected (dead) | — |
| 20 | Copy TSV (comparisons) | `QPushButton` | "Copy TSV" | | | — | CT:125-127, :195-205 → clipboard | — |
| 21 | Aperture radius (adaptive) | `QDoubleSpinBox` | suffix " × FWHM" / "Photometric aperture radius; 2–3 × FWHM is a typical start." | shows 1.00 (never initialised in Review); 1.0-6.0 step 0.25 | | — | PW:64-73 → `setting_changed` unconnected (dead) | — |
| 22 | Aperture radius floor | `QDoubleSpinBox` | suffix " green px" / "Lower limit for the aperture radius in green-plane pixels." | shows 2.0; 2-30 step 0.5 | | — | PW:75-80 (dead) | — |
| 23 | Background annulus — inner radius | `QDoubleSpinBox` | " green px" / "Inner radius of the local-sky annulus." | shows 3.0; 3-60 | | — | PW:82-87 (dead) | — |
| 24 | Background annulus — outer radius | `QDoubleSpinBox` | " green px" / "Outer radius of the local-sky annulus." | shows 5.0; 5-80 | | — | PW:89-94 (dead) | — |
| 25 | Reference-star minimum S/N | `QDoubleSpinBox` | " SNR" / "Automatic comparison candidates below this pilot-frame SNR are rejected." | shows 3.0; 3-100 step 1 | | — | PW:96-107 (dead) | — |
| 26 | Reference-star brightness difference | `QDoubleSpinBox` | " mag" / "Maximum instrumental brightness difference from the target for automatic comparisons." | shows 0.2; 0.2-5.0 step 0.1 | | — | PW:109-122 (dead) | — |
| 27 | Reference-star maximum separation | `QDoubleSpinBox` | " ′" / "Maximum target-to-comparison separation. Nearby references reduce flat-field and field-rotation systematics; Argos will propose fewer stars rather than fill the ensemble with remote candidates." | shows 5; 5-120 step 5 | | — | PW:124-139 (dead) | — |
| 28 | Export measurements | `QPushButton` | "Export measurements…" / "Export target, check-star and comparison measurements" | | always (silent no-op without points) | — | PW:240-242 → PW:302-310 → E23 → `write_curves_csv` LC:136-147 | — |
| 29 | Export target (AAVSO) | `QPushButton` | "Export target (AAVSO)…" / "Export science targets only; comparison curves are diagnostics" | | always (silent no-op without a target-role curve) | — | PW:244-246 → PW:312-327 → E23 → `write_aavso` LC:204-254 | — |
| 30 | Save CSV dialog | `QFileDialog.getSaveFileName` | "Export light curve" | `~/photometry.csv`, "CSV (*.csv)" | #28 | — | PW:306-310 | — |
| 31 | Save AAVSO dialog | `QFileDialog.getSaveFileName` | "Export AAVSO" | `~/aavso.txt`, "Text (*.txt)" | #29 | — | PW:316-327 | — |

- Displayed data: window title "Field photometry" (no object in Review: `set_export_meta`
  is not called); warning banner "Preview — raw, uncalibrated subs. BJD_TDB is recorded when
  the site and exposure time are available. Relative flux is a live diagnostic, not a
  detrended transit result; publishable reduction remains in Siril." (PW:211-220); Aperture
  tab texts "Live preview only: Argos measures circular apertures…", "Current live geometry:
  waiting for a measured FWHM", "All radii are green-plane pixels…" (PW:50-57, :142-154);
  ensemble hint and count texts (CT:71-77, :164-173).
- Messages: none on success, on an empty selection or on write errors (`OSError` uncaught).
- Problems found: **P30** Four of six tabs are live-only and inert in Review: Variable stars
  and Metrics are empty; Remove, Refresh catalogue, Recommend from pilot, Automatically
  propose and all seven Aperture spins emit signals nobody connects; the Aperture tab is
  never initialised (`set_values` not called), so it shows the spin minima (1.00 × FWHM,
  2.0 px…) as if they were the settings. **P31** A single-star CSV (every file in a
  session's `photometry/`, every batch output) is loaded as role "target" (LC:166): a
  comparison CSV is plotted as a target and written as AAVSO target rows named
  "COMPARISON_…" (LC:241-254). **P32** Exports: silent no-ops (PW:303-305, :313-315), no
  success message, `OSError` uncaught; `#OBSCODE=XXX` written without a warning when the code
  is unset (AP:751); FILT is the configured band ("TG") and is never compared with the
  session's filter ("IR" in every sample session); KNAME/KMAG are always "na" from Review
  because a check curve would have to be in the same CSV; default save folder is the home
  directory, not the session.

### 1.11 Frame Viewer window (E24; `AnalysisWindow` AW:136; top-level `QMainWindow`, non-modal, min 900×640)

- Purpose: read-only inspection of one FITS: display, field identification, catalogue layers,
  click-to-measure, header.

| # | Control | Qt type | Label / tooltip (exact text) | Default / range | Enabled / visible when | Shortcut | Action: handler → effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Open image | `QPushButton` | "Open image…" / "Open a FITS image" | | always | — | IT:51-54 → AW:437-445 → E25 (start `sessions_path`, "FITS (*.fits *.fit *.fts);;All files (*)") → `load` | — |
| 2 | Preview | `QComboBox` with caption "Preview:" | "Colour (CFA)", "Raw CFA", "Red (CFA)", "Green (CFA)", "Blue (CFA)" / "Changes only the on-screen preview; every view keeps the same sensor geometry and annotation coordinates. FITS data are unchanged." | widget default Colour (CFA), but every `load` forces Raw CFA (AW:333-334) | always | — | IT:56-77 → AW:429-431 reprocess | no |
| 3 | Palette | `QComboBox` with caption "Palette:" | "Neutral", "Negative", "Fire", "Ice" / "False-colour display palette for inspecting faint detail and saturation." | Neutral | always | — | IT:79-94 → FV:337-345 | no |
| 4 | Stars | checkable chip `QPushButton` | "Stars · {n}" / "Gaia DR3 stars, enriched with conventional SIMBAD identities when available." | off, disabled | after catalogues (tooltip "Solve and identify the field to enable this layer." while disabled, OB:171-179) | — | OB:141-149 → AW:508-521 | no |
| 5 | Variables | chip | "Variables · {n}" / "Variable stars from the AAVSO VSX catalogue." | auto-on when available | idem | — | idem | no |
| 6 | Galaxies | chip | "Galaxies · {n}" / "Galaxies identified by SIMBAD or the bundled Messier/NGC/IC catalogue." | auto-on | idem | — | idem | no |
| 7 | Nebulae + clusters | chip | "Nebulae + clusters · {n}" / "Nebulae and stellar clusters identified by SIMBAD or the bundled Messier/NGC/IC catalogue." | auto-on | idem | — | idem | no |
| 8 | Exoplanets | chip | "Exoplanets · {n}" / "Confirmed exoplanet hosts returned by NASA (cache first)." | auto-on | idem | — | idem | no |
| 9 | Other objects | chip | "Other objects · {n}" / "Other physically classified SIMBAD sources, such as radio or X-ray sources." | auto-on | idem | — | idem | no |
| 10 | Coordinate grid | chip | "Coordinate grid" / tooltip falls back to "Show or hide this overlay." (no entry in OB:38-51) | auto-on after a solve (AW:500) | after a solve | — | → `set_astrometry_enabled` | no |
| 11 | VSP references | chip | "VSP references · {n}" / "AAVSO VSP reference candidates; not necessarily the selected ensemble." | auto-on | after catalogues | — | → `set_comparison_enabled` | no |
| 12 | Selected stars | chip | "Selected stars · {n}" / "The target, selected comparison stars and check stars for this observation." | auto-on | after catalogues | — | → `set_target_enabled` | no |
| 13 | Labels | chip | "Labels" / "Show compact non-overlapping labels; hover a marker for its full identity." | **off** when armed (AW:527) | when any layer has markers | — | → `set_marker_labels_enabled` | no |
| 14 | Gaia G limit | `QSlider` + value label "≤ 18.0" | caption "Gaia G limit" / caption tooltip "Stellar display limit in the Gaia G passband. It does not filter galaxies or nebulae whose integrated magnitudes use different passbands." / slider tooltip "Faint-end Gaia G display limit. Move left to declutter; move right to reveal fainter Gaia stars already cached for this field." | `catalog.display_mag_limit` (18.0); 5.0 to `catalog.field_stars_mag_limit`, step 0.1 | always | — | OB:89-118 → AW:579-581 live re-projection; release → AW:583-586 save | `catalog.display_mag_limit` (+ `Config.save()`) on mouse release only |
| 15 | Catalogues / depth | `QToolButton` | "Catalogues / depth…" / "Choose Gaia, VSX, SIMBAD, NASA and offline catalogue sources, query depth, cache folders and refresh behaviour." | | always (no-op without config) | — | OB:120-127 → AW:564-569 → E26 | via E26 |
| 16 | Image left-click | pyqtgraph scene click | — | | frame loaded | — | FV:867-881 → AW:885-902 (W3 step 5) | no |
| 17 | Cursor readout | mouse move | "({x}, {y})   {v} ADU" or "R {r}  G {g}  B {b}" pinned top-left | | over the image | — | FV:420-451 | no |
| 18 | Zoom / pan | pyqtgraph `ImageView` | wheel zoom, drag pan | fit on load | | — | FV:138-142 | no |
| 19 | Image context menu | pyqtgraph `ViewBox` default | "View All", "X axis", "Y axis", "Mouse Mode", "Export…" (uncertain, U3) | | right-click | — | pyqtgraph | no |
| 20 | Marker tooltip | pyqtgraph tip | catalogue bodies AW:1000-1105 (e.g. "AAVSO VSX variable star / Type … / AUID … / RA … Dec …") | | hover a marker | — | FV:54-61 | — |
| 21 | Detail tabs | `QTabWidget` | "Frame · selected star", "FITS header", "Adjust image" | first tab | always | — | AW:229-233 | no |
| 22 | FITS header text | read-only `QPlainTextEdit` | placeholder "No FITS header loaded"; "FITS header unavailable" on error | | tab 2 | Ctrl+C (select/copy) | AW:215-221, :126-133 | — |
| 23 | Black | `QSlider` | caption "Black" | range = data lo..hi (HD:210-219) | tab 3 | — | HD:97-106 → FV:364-368 (auto off) | no |
| 24 | White | `QSlider` | caption "White" | idem | tab 3 | — | idem | no |
| 25 | Midtones | `QSlider` | caption "Midtones" | 500 of 1-999 (0.5) | tab 3 | — | idem | no |
| 26 | Contrast | `QComboBox` | caption "Contrast": "Linear", "Log", "Asinh" | Linear | tab 3 | — | HD:112-115 → FV:364-368 | no |
| 27 | Rotation | `QComboBox` | caption "Rotation": "Auto (landscape)", "0°", "90°", "180°", "270°" / "Rotate the displayed image (clockwise).\nAuto turns portrait frames landscape. Display only — saved FITS\nand measurements keep the sensor orientation." | `ui.display.rotation` (auto) read at construction (AW:296-298) | tab 3 | — | HD:117-125 → FV:256 | read only; changes not saved |
| 28 | Auto stretch | `design.PrimaryButton` | "Auto stretch" / "Automatically set a display stretch for the current image" | auto on until a manual change | tab 3 | — | HD:128-131 → FV:370-375 | no |
| 29 | Crosshair | `QCheckBox` | "Crosshair on image" | off | tab 3 | — | HD:134-137 → FV:453-458 | no |
| 30 | Highlight saturation | `QCheckBox` | "Highlight saturation" | off; threshold `camera.full_well_adu` (60000) | tab 3 | — | HD:138-140 → AW:457-459 → FV:377 (pixels drawn pure red, FV:347-358) | no |
| 31 | Loupe | `QCheckBox` | "Loupe (100% zoom at cursor)" / "Magnified 1:1 inset for fine manual focus" | off | tab 3 | — | HD:147-150 → FV:862-865 | no |
| 32 | WCS grid overlay | `QCheckBox` | "WCS grid overlay" / "RA/Dec grid + field centre — needs a plate-solve first" | hidden | **never visible** (AW:292) | — | HD:153-157 (dead) | — |
| 33 | Star aperture | `design.SliderSpin` | caption "Star aperture", suffix " px" / "Aperture radius for FWHM/HFD measurement (green plane px).\nSmaller = tight on the core; larger = more wings (tune per seeing)." | 5, 2-30 | tab 3 | — | HD:163-169 → AW:433-435 → reprocess + re-measure | no |
| 34 | Identify field | `QPushButton` | "Identify field" / "Determine sky coordinates and image scale with ASTAP" | | frame loaded; disabled while solving | — | AW:251-254 → AW:461-502 (W3 step 3) | no |
| 35 | Adjust image | checkable `QPushButton` | "Adjust image" / "Open the histogram, contrast and display tools" | unchecked | always | — | AW:260-264 → AW:276-277 (tab 3 on, tab 1 off) | no |
| 36 | Viewer / tabs splitter | `QSplitter` | — | 900 / 360, not collapsible | always | — | AW:235-242 | no |

- Displayed data: title "Frame Viewer — {name}  ({w}×{h})" (AW:337); info tab (mono, AW:350-416):
  "FRAME", "File: …", "Dimensions: {w} × {h} px", then first present of "Object", "Start
  (UTC)", "Exposure" (+ " s"), "Filter", "Image type", "Gain", "Sensor" (CCD-TEMP, no unit),
  "Instrument", "Frames in sequence", "Frame number", "Sequence", "Airmass"; then either
  "SELECTED STAR" / "Click a star in the image to measure it.", or position, FWHM/HFD in px
  and arcsec, eccentricity, SNR, peak ADU, sky ADU, or "CATALOGUE SOURCE" + title + body +
  "IMAGE MEASUREMENT"; histogram "Raw FITS histogram" (log1p R/G/B, 128 bins, HD:67-88);
  on-image selection label "Selected star   FWHM …″   HFD …″   ecc …   SNR …   peak … ADU",
  "scale  {s}″/px", "RA … Dec …" after a solve (AW:983-997); "Preview only · FITS
  unchanged" (IT:97); bottom status line (AW:266-271, :1184-1189).
- Implicit behaviours: load generation counter discards stale solve and catalogue results
  (AW:315, :476, :649-652); overlays armed once per load (AW:523-529); auto-stretch until a
  manual stretch (FV:304-306, :364-376); selection re-measured after radius, channel or solve
  changes (AW:427, :501, :904-916); clicking a catalogue marker switches to the first tab
  (AW:968); catalogue settings Save re-ranges the slider and re-fetches (AW:571-577);
  `closeEvent` waits up to 2 s for the solver and each catalogue worker (AW:1191-1197).
- Messages (bottom line): "field not identified" (muted), "identifying field… (ASTAP)"
  (warning), "field not identified — {message}" (danger), "Field identified — RA {h:.4f}h
  Dec {d:+.4f}°   {s:.2f}″/px   rot {r:.1f}°" (success), "Field solved · identifying
  catalogue sources…" (warning), "Field solved · catalogues unavailable: {error}" (warning),
  "Field identified · {n} catalogue sources" (success). Info: "No frame loaded". No dialog on
  load failure.
- Problems found: **P24** The solve result (RA, Dec, scale, rotation) is overwritten by
  "Field identified · {n} catalogue sources" (AW:494 → :666) and is then visible nowhere.
  **P25** "Adjust image" button and "Adjust image" tab duplicate each other and desync (a tab
  click does not check the button; unchecking jumps to the first tab even from FITS header).
  **P26** Preview reset to "Raw CFA" on every load although the widget default is "Colour
  (CFA)"; rotation, crosshair, loupe, saturation, aperture not remembered; the Gaia limit is
  saved on mouse release only (keyboard changes are lost, OB:108-110). **P27** "Sensor: 25.38"
  without °C (AW:367); arcsec values use the hardware-profile scale even after a solve
  measured the real one. **P28** `_on_open` ignores a failed load (AW:444-445); no way to
  cancel ASTAP. **P29** The hidden "WCS grid overlay" checkbox (AW:292) and the `_grid_btn`
  alias (AW:258) are dead. Night Red: "Fire"/"Ice" palettes, the white "Negative"
  background and the pure-red saturation mask (FV:357) break or defeat the red-only contract.

### 1.12 Catalogue settings dialog, as opened from the Frame Viewer (E26; `AstrometrySettingsDialog(section="catalog")` AS:48; modal)

| # | Control | Qt type | Label | Default | When | Shortcut | Action | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Entry | `QToolButton` (1.11 #15) | "Catalogues / depth…" | — | config present | — | AW:564-569: `exec()` on the Catalogues tab; `saved` → AW:571-577 | `catalog.*`, `photometry.auto_comparisons` (AS:351-395) |

- Content (owned by the Settings spec, listed for traceability): window "Field identification
  & catalogue settings"; tabs Field identification / Catalogues; Catalogues fields "VSX
  faint-end magnitude limit" (5-20), "Maximum VSX variables in field" (10-2000), "Include
  suspected variables", "Field identification budget", "Identify ordinary field stars with
  Gaia DR3", "Gaia cached-depth G limit" (3-20), "Gaia cache depth" (Bright · G ≤ 15 /
  Standard · G ≤ 18 / Deep · G ≤ 20 / Custom), detected-only, essential objects, cached
  exoplanets, named objects (+ network), exoplanet hosts (+ network), "Automatic reference
  stars" (1-20); Save / Cancel. `catalog.field_stars_detected_only` is ignored by the viewer's
  request (AW:604-629).

### 1.13 Batch photometry re-run (E29; Photometry ▸ Re-run subs…; UI in IP, worker BW)

| # | Control | Qt type | Label / text (exact) | Default / range | When | Shortcut | Action: handler → effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Menu entry | `QAction` | "Re-run subs…" / "Re-run differential photometry over a folder of saved subs" | — | always (no-op while a batch runs) | — | SH:282-285 → IP:2087-2089 → IP:2248 | — |
| 2 | Solve first | `QMessageBox.information` | "Solve first" / "Plate-solve the live frame before a batch re-run." | OK | no live WCS | — | IP:2261-2265 | — |
| 3 | No targets | `QMessageBox.information` | "No targets" / "Assign at least one target star first." | OK | no target | — | IP:2266-2269 | — |
| 4 | No comparison stars | `QMessageBox.information` | "No comparison stars" / "The target set has no comparison stars, so differential\nphotometry cannot produce magnitudes.\n\nSolve the field and wait for the catalog (comps auto-select\nonce it arrives), or click a comparison marker on the image\nand assign it the Comp role." | OK | no comparison | — | IP:2270-2281 | — |
| 5 | Folder | `QFileDialog.getExistingDirectory` | "Folder of saved subs" | start: last sequence folder or `sessions_path` | after 2-4 | — | IP:2282-2285 | — |
| 6 | No frames | `QMessageBox.information` | "No frames" / "No FITS files in {folder}" | OK | no `*.fits` | — | IP:2286-2292 | — |
| 7 | Progress | `QProgressDialog`, non-modal (`show()`, no modality set), Cancel button | title "Batch photometry", label "Re-running photometry…", button "Cancel" | 0..N frames, shown at once (`setMinimumDuration(0)`) | while running | — | IP:2308-2318; `canceled` → BW:92-94; `progress` → value | — |
| 8 | Batch failed | `QMessageBox.warning` | "Batch failed" / {error} | OK | worker exception | — | IP:2343-2345 | — |

- Outputs: `<sessions_path parent>/targets/{object}_{AUID or name}.csv` per star
  (15-column canonical CSV, LC:14-30), `{object}_diagnostics.jsonl` when
  `diagnostics.enabled` (default false); log lines "Batch photometry: no points measured — see
  the per-frame notes in targets/*_diagnostics.jsonl." (WARN), "Batch photometry: {n}
  frame(s), {m} target(s)." (OK), "Apertures tracked the field: {rot:+.2f}° rotation,
  {shift:.1f} px drift vs the reference solve." (INFO, when > 0.05° or > 1 px); worker log
  "Series FWHM … → aperture … px", "{file}: no anchor star found — apertures unguided",
  "{file}: no EXPTIME — JD is exposure start, not midpoint", "Check star {key}: RMS {rms} mag
  over {n} frames".
- Problems found: **P33** Argos saves lights as `.fit` (`fits_writer.py:241`; all 9 sample
  sessions) but the batch only globs `*.fits` (IP:2287, :2289): re-running an Argos session
  answers "No FITS files in …". **P34** Output lands outside any session, in
  `<sessions_path parent>/targets`, overwritten at each run, with names Open session cannot
  load; the empty-result message points to diagnostics that are off by default. **P35** The
  reference WCS must be the live Observe solve; `point` is not connected (no live plot);
  unreadable frames are skipped without a count (BW:162-163); check-star RMS only logged
  (BW:124-132); "{m} target(s)" counts comparisons too; a cancelled run is reported as a
  success.

### 1.14 Shell entry points into Review (E30)

| # | Control | Qt type | Label / tooltip (exact text) | Default | When | Shortcut | Action: handler → effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Sidebar entry | sidebar mode | "Review" / "Inspect the light curve and export AAVSO" | — | always | — | SB:42 → page switch | last mode (shell) |
| 2 | View ▸ Review | `QAction` | "Review" | — | always | **F4** | SH:230-234 | — |
| 3 | File ▸ Open session photometry | `QAction` | "Open session photometry…" / "Open the saved differential-photometry measurements of a session" | — | always | **Ctrl+Shift+O** | SH:197-201 → SH:291-293 → Review + 1.9 #3 | — |
| 4 | View ▸ Reset Window Layout | `QAction` | "Reset Window Layout"; status "Window layout will reset on next launch." | — | always | — | SH:237-239 → SH:452-457 (also clears `ui.review.layout`; ineffective, P18) | — |

- Problem **P36**: "Open session photometry…" opens a **CSV file** dialog while the page's
  "Open session…" opens a **folder**: same words, two different objects.

## 2. Web redesign

Principles applied: Review is offline and read-only (it never moves hardware and never edits
the night's target set); the plots and the image get the room (BRAND 11.1); one toolbar row,
compact collapsible cards in a right rail of `--rail-min-w` (420 px) that `P` collapses, as on
Observe; every number in Plex Mono with the formats of BRAND §5; no more than three series per
plot (BRAND §10); companion windows become screens of the Review section (Tauri pop-out is a
later option, Q5).

### 2.1 Placement in the new information architecture

Review (rail entry `nav-analyze`, **F4**) holds three screens:

- **R0 Sessions**: list of sessions found under `sessions_path`, plus "Open folder…",
  "Import CSV…", "Open FITS…". Landing screen when no session is open.
- **R1 Session**: one session (or one imported CSV) as a plot wall, a right rail of cards and
  a bottom Frames drawer.
- **R2 Frame inspector**: one FITS, the Observe viewer re-used read-only, with a right rail.

Review reopens the last session viewed (per-viewer preference) when it is still on disk.

| Qt element | Web placement (section → screen → region) | Why |
|---|---|---|
| E1 Review page | Review → R1 | Same job. |
| E2 Session card (title, summary, warnings, open button) | R1 toolbar: identity text (one line, ellipsis, full text in tooltip) + readiness badge (popover with the issues); summary fields in rail card **Session**; open button → R0 | The card cost about 112 px of height (AP:154) for one line of identity; BRAND 11.1 "no dead bands". |
| E3 Panel toolbar | R1 toolbar | One row. |
| E4 Panels ▾, E5 Arrange ▾ | R1 toolbar `add-plot` menu (add + "Show plots" checklist), `layout-tile`, `layout-reset`; per-cell menu (`disclosure`) for expand, pop out, copy, hide | Two menus and five chips collapse into three buttons; `panels` keeps Observe's meaning (rail toggle, P). |
| E6 Dock workspace | R1 plot wall: CSS grid of plot cells, 2 columns (3 when the rail is collapsed and the wall is ≥ 1200 px), row height 270 px (min 220), vertical scroll; cells reorder by dragging their header | Free docking was the main source of bugs (P1, P3, P4, P18) and of wasted chrome; small multiples are what BRAND §10 asks for. |
| E7 Source curve docks | Wall cells, role target, first in order | |
| E8 Comparison docks | Wall cells, role comparison, one per comparison | |
| E9 Frame quality | Wall cell, last by default, on the same UTC time axis | Linkable with the curves (P17). |
| E10 Comparison quality | Rail card **Comparison quality** (open by default) | A table, not a plot; needs width only of the rail. |
| E11 Frames | Bottom drawer **Frames** (like the Observe log drawer), toggled from the toolbar | A 12-column table needs the full width, rarely. |
| E12 Session metadata | Rail card **Session** (folded) | Provenance, one click away. |
| E13 AAVSO export | Rail card **AAVSO export** (summary + checks) + toolbar `export-aavso` → modal **Export AAVSO** dialog | Fixes P8: the card now leads to the action. |
| E14 Floating docks | Cell menu "Pop out" (`panel-float`) → separate Tauri window later; until then "Expand" fills the wall | Second-monitor use is real (AP:3-4 docstring) but needs Tauri multi-window (Q5). |
| E15-E16 plot affordances | Cell header tools + direct manipulation on the plot (2.4) | |
| E17-E21 dialogs | R0 (server-side session listing), Tauri file dialogs or a server path field, inline errors and disabled states instead of message boxes | A browser cannot browse local folders; the server can (API 2.5). |
| E22 Field photometry window | Dissolved. Imported curves open as a pseudo-session in R1 (no frames, no quality report); Targets/Comparison tables → rail card **Stars**; exports → R1 toolbar; live-only tabs (Variable stars, Metrics, Remove/Refresh/Recommend, Aperture) stay in Observe | In Review the window was a light-curve plot plus two export buttons; 4 of 6 tabs were inert (P30). |
| E23 save dialogs | Field "File" inside the export dialogs (Tauri save dialog behind `browse`), default in the session folder | Exports belong next to the session, not in `~`. |
| E24 Frame Viewer window | Review → R2 | Same section; uses the existing WebGL viewer, stretch card, cursor readout. |
| E25 viewer open dialog | R2 toolbar `open-image` (Ctrl+O) | |
| E26 catalogue settings | Settings → Catalogues (link from the R2 layers popover); on return R2 re-fetches | Settings owns the form (Settings spec). |
| E27 marker tooltips | Token tooltip on marker hover, same bodies | |
| E28 image context menu | Dropped (zoom tools cover it) | |
| E29 Batch re-run | R1 toolbar `rerun-photometry` → modal **Re-run photometry** dialog; progress in a job strip that replaces the toolbar identity while running; result loads as a new run of the session | It is an analysis of saved frames; Review has the session, its frames and its targets; outputs belong in the session (fixes P33-P35). Moving it out of Observe is an owner decision (Q1). |
| E30 Shell entries | NavRail Review (F4); Ctrl+Shift+O = R0 Sessions; layout reset in R1 (and Settings → Appearance "Reset layouts", Settings spec) | No web menu bar (a Tauri app menu could host them, Q8). |

### 2.2 Control mapping

Icon ids: existing ids from `icon-inventory.json`; `NEW:` ids are proposed in the result.
Display follows BRAND §7 (frequent, reversible: icon; rare, writes files or resets: icon +
label; dialog buttons: text).

| Qt ref | Web control | Decision (reason) | Icon id | Display | Shortcut |
|---|---|---|---|---|---|
| 1.1 #1 | R0 list row open; R1 toolbar Sessions | merge with #2 (duplicate, P2) | `open-session` | icon | Ctrl+Shift+O |
| 1.1 #2 | R1 toolbar Sessions (opens R0) | keep | `open-session` | icon | Ctrl+Shift+O |
| 1.1 #3 | R0 toolbar "Import CSV…" | move to R0 (rare; creates a pseudo-session) | `open-file` | icon+label | — |
| 1.1 #4 | R0 and R1 toolbar "Open FITS…" → R2 | keep | `open-image` | icon | Ctrl+O (in Review) |
| 1.1 #5 | `add-plot` menu: "Comparison star…", "Target…", "Ensemble overlay", "Frame quality metric" | keep + extend (any plot type; default star = first one without a cell, else the picker opens; fixes P9) | `add-plot` | icon (menu) | — |
| 1.1 #6-#10 | `add-plot` menu section "Show plots": one checkable entry per cell (all cells, incl. extra ones) | merge (fixes P3, P4) | — (menu text, role glyph left) | label | — |
| 1.1 #11 | (menu container) | merge into `add-plot` menu | — | — | — |
| 1.1 #12 | Rail card Session, fold/unfold | move (card, not a hidden dock) | `metadata` | icon in card header | — |
| 1.1 #13 | Rail card AAVSO export, fold/unfold | move | `export-aavso` | icon in card header | — |
| 1.1 #14 | (menu container) | drop the button: its entries map to #15-#18 | — | — | — |
| 1.1 #15, #19 | "Tile plots" | merge duplicates: re-tile in default order (targets, comparisons, quality), auto columns | `layout-tile` | icon | — |
| 1.1 #16, #20 | "Reset layout" | merge duplicates; restores every session plot (fixes P4), default order, row height, rail cards, drawer; clears Review prefs | `layout-reset` | icon+label | — |
| 1.1 #17, #18 | Cell menu "Pop out to a window" (Tauri, later) | keep for second monitor; returns when that window closes or via `panel-dock` there | `panel-float` / `panel-dock` | icon+label (menu) | — |
| 1.1 #21 | Drag a cell header to reorder | keep, simplified (grid order, no nested docking) | — | — | — |
| 1.1 #22 | = 1.1 #17 | merge | `panel-float` | — | — |
| 1.1 #23 | Cell menu "Hide plot" (session cells) / "Remove plot" (added cells) | keep; hidden cells reappear in "Show plots" | `remove` | icon+label (menu) | — |
| 1.1 #24 | Row-height handle under any wall row (one global row height) | keep, simplified | — | — | — |
| 1.1 #25 | Wall vertical scroll | keep | — | — | wheel, PageUp/PageDown when the wall has focus |
| 1.1 #26 | Rail cards stacked and foldable | drop the tab bar (cards replace tabs) | — | — | — |
| 1.2 #1 | Cell header star picker (custom listbox, Night Red safe) | keep; "All targets" only when ≤ 3 targets (BRAND §10) | `target-star` glyph before the name | label | — |
| 1.2 #2 | Cell header toggle "Show uncertainties" | keep; preference per role | `error-bars` | icon | — |
| 1.2 #3 | Cell header toggle "Relative flux" | keep; preference per role | `relative-flux` | icon | — |
| 1.2 #4 | Click a point → selects it on every plot (time cursor), fills card Selected point, highlights the Frames row | keep, extended | — | — | Enter = Open frame |
| 1.2 #5 | Hover a point → mono tooltip (UTC, JD/BJD 5 dec., mag ± err 3 dec., flags) | keep and fix (P6) | — | — | — |
| 1.2 #6 | Wheel = zoom time (all plots linked), Shift+wheel = zoom magnitude of this plot, drag = pan, double-click = fit | keep | — | — | `+` / `−` zoom time, `F` fit all |
| 1.2 #7 | Cell header "Fit" (visible when zoomed) | merge with double-click | `zoom-fit` | icon | F (all cells) |
| 1.2 #8 | Legend in the cell header (outside the data), click toggles a series | keep for multi-series cells | — | label | — |
| 1.2 #9 | Card Selected point → "Open frame" | move (one place for every plot, fixes P7) | `open-image` | icon+label | Enter |
| 1.3 #1 | Cell header star picker; "All comparison stars" → "Ensemble overlay" cell (all comparison residuals as one muted series, the hovered/selected one highlighted) | keep; replace the >3-series overlay (P40) | `comparison-star` glyph | label | — |
| 1.3 #2-#8 | as 1.2 #2-#8 | keep | as 1.2 | as 1.2 | as 1.2 |
| 1.4 #1 | Cell header metric picker; cell title follows the metric (fixes P17) | keep | `focus-metrics` glyph | label | — |
| 1.4 #2, #4 | as 1.2 #6-#7 (same UTC axis as the curves) | keep | `zoom-fit` | icon | F |
| 1.4 #3 | — | drop: generic pyqtgraph menu (View All = fit; plot export replaced by cell menu "Copy data (TSV)") | `copy` (cell menu) | icon+label (menu) | — |
| 1.5 #1 | Card Comparison quality: row click scrolls to and highlights that star's cell (creates it if hidden); sortable columns; status in words | keep, fixed (P10, P22) | `comparison-quality` card glyph | — | ↑/↓ in the table |
| 1.6 #1 | Frames drawer: single click = time cursor on all plots; Enter / double-click = R2 at that frame | keep, extended | `frames` (drawer toggle) | icon | T toggles the drawer (proposed) |
| 1.6 #2 | — | drop (bug: editable cells, P11) | — | — | — |
| 1.7 #1 | — | drop (bug, P11); card Session is read-only and copyable | `copy` | icon | — |
| 1.9 #1 | R0 list (server listing) + "Open folder…" (Tauri directory dialog; path field in a plain browser) | move | `open-session` | icon+label | Ctrl+Shift+O |
| 1.9 #2 | Inline error banner in R0 + toast + log line, same text | keep text, drop the modal box | — | — | — |
| 1.9 #3 | R0 "Import CSV…" (Tauri file dialog or path field) | move | `open-file` | icon+label | — |
| 1.9 #4 | "Open FITS…" (Tauri file dialog or path field) | keep | `open-image` | icon | Ctrl+O |
| 1.9 #5 | Missing frame: "Open frame" disabled with tooltip "File not found: {filename}"; Frames row dimmed "missing"; toast if it vanished meanwhile | replace the box (state shown before the click) | — | — | — |
| 1.10 #1 | — | drop the tab bar (window dissolved, see 2.1) | — | — | — |
| 1.10 #2-#6 | — | drop from Review: live variable-star target selection, empty and unconnected here (P30); Observe spec owns it | — | — | — |
| 1.10 #7-#10 | Plot-cell controls (1.2 #2-#8) | merge into the wall | `error-bars`, `relative-flux` | icon | — |
| 1.10 #11 | — | drop from Review: live session metrics, always empty here; the Frame quality cell shows the recorded metrics | — | — | — |
| 1.10 #12, #16 | Rail card Stars: one table (role glyph, name, AUID, RA, Dec, catalogue mags, chart), row click scrolls to the star's cell | merge the two tables, read-only | `target-star` card glyph | — | — |
| 1.10 #13, #17 | — | drop from Review: unconnected; Review never edits the target set (post-hoc ensemble editing is Q12) | — | — | — |
| 1.10 #14, #20 | Card Stars "Copy TSV" | merge | `copy` | icon | — |
| 1.10 #15 | — | drop from Review: unconnected; the setting exists in Settings (`photometry.auto_comparisons`, AS) | — | — | — |
| 1.10 #18, #19 | — | drop from Review: live catalogue/pilot actions, unconnected here | — | — | — |
| 1.10 #21-#27 | Read-only parameter summary in the Re-run dialog with a "Settings ›" link | drop as editors from Review (unconnected, showed wrong values, P30) | — | label | — |
| 1.10 #28 | R1 toolbar "Export CSV" (multi-curve, lossless) | keep | `export` | icon+label | — |
| 1.10 #29 | R1 toolbar "Export AAVSO…" → dialog WF-E (primary) | keep, with pre-checks (P31, P32) | `export-aavso` | icon+label | — |
| 1.10 #30 | File field in the CSV export flow; default `<session>/<object>_measurements.csv` | keep | `browse` | icon | — |
| 1.10 #31 | File field in WF-E; default `<session>/<object>_aavso.txt` | keep | `browse` | icon | — |
| 1.11 #1 | R2 toolbar "Open FITS…" | keep | `open-image` | icon | Ctrl+O |
| 1.11 #2 | Card Display: "Preview" segmented control (Colour CFA, Raw CFA, R, G, B); remembered | keep, moved to the card (rarely changed; toolbar row stays one line) | — | label | — |
| 1.11 #3 | Card Display: "Palette" segmented control; Night Red: Neutral only (Fire/Ice emit non-red, Negative floods the screen) | keep | — | label | — |
| 1.11 #4-#9 | R2 toolbar layer toggles with count in tooltip and a small mono count badge | keep | `field-stars`, `variable-star`, `galaxy`, `nebula`, `exoplanet`, `other-objects` | icon | — |
| 1.11 #10 | Coordinate grid toggle | keep | `sky-grid` | icon | G |
| 1.11 #11 | VSP references toggle | keep | `comparison-star` | icon | — |
| 1.11 #12 | Selected stars toggle | keep | `target-star` | icon | — |
| 1.11 #13 | Labels toggle | keep | `labels` | icon | — |
| 1.11 #14 | Layers popover: "Gaia G ≤ 18.0" slider; saved on change end (mouse and keyboard) | keep, moved to popover | `catalogue` (popover button) | icon | — |
| 1.11 #15 | Layers popover link "Catalogue settings…" → Settings → Catalogues | move | `settings` | icon+label (link) | — |
| 1.11 #16 | Click on the image: measure or identify | keep | — | — | — |
| 1.11 #17 | Status bar cursor readout (x, y, ADU; RA/Dec once identified) | keep, extended | — | — | — |
| 1.11 #18 | Zoom buttons and mouse | keep (Observe viewer) | `zoom-in`, `zoom-out`, `zoom-fit`, `zoom-1to1` | icon | +, −, F, 1 |
| 1.11 #19 | — | drop (generic pyqtgraph menu; zoom tools cover it) | — | — | — |
| 1.11 #20 | Marker hover tooltip (token tooltip, mono) | keep | — | — | — |
| 1.11 #21 | Rail cards Frame, Selected star, Identification, Display, FITS header | replace tabs by foldable cards | `metadata`, `crosshair`, `plate-solve`, `histogram`, `metadata` | — | — |
| 1.11 #22 | Card FITS header: mono text, filter field, Copy | keep, extended | `search`, `copy` | icon | — |
| 1.11 #23-#26 | Card Display = Observe StretchCard (black, midtones, white, transfer) | keep (reuse) | — | — | — |
| 1.11 #27 | Card Display: rotation (auto, 0, 90, 180, 270), shared preference with Observe | keep | — | label | — |
| 1.11 #28 | R2 toolbar Auto stretch (+ Reset stretch, as Observe) | keep | `stretch-auto`, `stretch-reset` | icon | A, Shift+A |
| 1.11 #29 | Crosshair toggle | keep | `crosshair` | icon | X |
| 1.11 #30 | Saturation toggle; Night Red draws saturated pixels black (no light) instead of red | keep | `saturation` | icon | — |
| 1.11 #31 | Loupe toggle | keep | `loupe` | icon | Z |
| 1.11 #32 | — | drop (dead, hidden; replaced by `sky-grid`) | — | — | — |
| 1.11 #33 | Card Selected star: "Aperture r" number field 2-30 px; remembered | keep, moved next to the measurement it drives | — | label | — |
| 1.11 #34 | R2 toolbar Identify field + card Identification button with progress and Cancel | keep | `plate-solve` (Cancel: `stop`) | icon (toolbar), icon+label (card) | S |
| 1.11 #35 | Display card toggle | merge with the Display card (duplicate, P25) | `histogram` | icon | H |
| 1.11 #36 | Rail collapse | replace the splitter | `panels` | icon | P |
| 1.12 #1 | Link to Settings → Catalogues | move | `settings` | icon+label | — |
| 1.13 #1 | R1 toolbar "Re-run photometry…" | move to Review (Q1) | `rerun-photometry` | icon+label | — |
| 1.13 #2 | Dialog "Reference" choice: "Identify the first frame" (default) or "Use the live solve from Observe" (only when one exists) | replace the refusal by a choice | `plate-solve` | label | — |
| 1.13 #3, #4 | Dialog validation line, same texts; Start disabled with the reason | replace boxes | — | — | — |
| 1.13 #5 | Dialog field "Frames" (default the session lights folder; `.fit`, `.fits`, `.fts`, fixes P33) | keep | `browse` | icon | — |
| 1.13 #6 | Dialog inline "No FITS files (.fit, .fits, .fts) in {folder}" | replace box | — | — | — |
| 1.13 #7 | Job strip "Re-running photometry · {done} / {total} frames · ETA …" + "Cancel" | keep, non-modal | `stop` | icon+label | — |
| 1.13 #8 | Error toast + log + job strip error state, same text | keep text | — | — | — |
| 1.14 #1 | NavRail Review | keep (exists) | `nav-analyze` | icon+label | F4 |
| 1.14 #2 | F4 | keep (exists) | — | — | F4 |
| 1.14 #3 | Ctrl+Shift+O → R0 Sessions (folder, not CSV; fixes P36) | keep binding, change target | `open-session` | — | Ctrl+Shift+O |
| 1.14 #4 | R1 `layout-reset` + Settings → Appearance "Reset layouts" | keep, scoped, and effective at once (fixes P18) | `layout-reset` | icon+label | — |

New controls without a Qt counterpart (proposed, each optional): R0 search filter (`search`);
R2 previous/next frame of the session (`NEW:frame-prev`, `NEW:frame-next`, PageUp/PageDown);
cell "Expand" to the whole wall and back (`NEW:expand-plot`, also double-click on the cell
header); time axis unit switch in the wall (UTC / JD / BJD_TDB, label-only segmented control);
FITS header filter.

### 2.3 Wireframes (1440 × 900, 1 character ≈ 12 px)

Legend of button tags: SL `open-session`, IM `open-file`, OF `open-image`, AD `add-plot`
(menu), LT `layout-tile`, LR `layout-reset`, RR `rerun-photometry`, EX `export`, AA
`export-aavso` (primary), FR `frames`, PN `panels` (rail, P), EB `error-bars`, RF
`relative-flux`, ZF `zoom-fit`, DS `disclosure` (cell menu), FP `NEW:frame-prev`, FN
`NEW:frame-next`, Z+ / Z- / Z1 zoom, SA `stretch-auto`, SX `stretch-reset`, HG `histogram`,
CH `crosshair`, LU `loupe`, SU `saturation`, PS `plate-solve`, GR `sky-grid`, FS
`field-stars`, VS `variable-star`, GX `galaxy`, NB `nebula`, EP `exoplanet`, OO
`other-objects`, CS `comparison-star`, TS `target-star`, LB `labels`, CT `catalogue`
(layers popover), BR `browse`, CL `close`, CP `copy`, ST `stop`. ASCII boxes are wider than
the real 34 px buttons: every toolbar is one 47 px row.

**WF-A. R0 Sessions (landing).** Toolbar 47 px, table rows 24 px, sorted by start time
(newest first); 30 rows visible without scrolling.

```
┌────────┬───────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ARGOS  │ [SL Open folder…] [IM Import CSV…] [OF] │ ~/Argos/sessions          [search: object, date, folder…   ]        │
│        ├───────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Conn.  │ Started (UTC) ▾      Object  Lights  Filters  Curves     Quality  Issues  Folder                              │
│ Observe│ 2026-09-25 20:04:53  RR Lyr     195  IR       1 T · 6 C  report   –       20260925T200453Z_RR_Lyr             │
│ Plan   │ 2026-09-07 04:07:25  XX Cyg      24  IR       1 T · 8 C  report   –       20260907T040723Z_XX_Cyg  ◂ selected │
│▌Review │ 2026-09-07 04:45:27  XX Cyg       2  IR       1 T · 8 C  report   1       20260907T044527Z_XX_Cyg             │
│        │ 2026-08-29 05:29:43  XX Cyg       4  IR       1 T · 7 C  –        –       20260829T052943Z_XX_Cyg             │
│        │ 2026-06-19 …         m42         …  …        none       –        3       20260619_m42                         │
│        │ …  (rows 24 px; Enter or double-click opens; issues column opens a popover listing them)                      │
│        │                                                                                                               │
│ Set.   │ Empty state: “No sessions in ~/Argos/sessions” + [SL Open folder…] [IM Import CSV…]                           │
├────────┴───────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ status bar (32 px): server link · Review · 9 sessions · theme · Log                                                    │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**WF-B. R1 Session (default after opening the sample XX Cyg session).** Wall 2 × 3 cells of
270 px (928 px wide with the rail open); rail 420 px; target first, then comparisons, the
frame-quality cell last. Shapes: ○ target, □ comparison, △ check (BRAND §2, principle 6).

```
┌────────┬───────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ (mark) │ [SL][OF] XX Cyg · 09-07 04:07 · 24 L · IR [ok]│[AD▾][LT][LR Reset]│[RR Re-run…][EX CSV][AA AAVSO…]│[FR][PN]   │
│        ├─────────────────────────────────────┬─────────────────────────────────────┬───────────────────────────────────┤
│        │ ○ XX Cyg ▾       24 [EB][RF][ZF][DS]│ □ 000-BCK-396 ▾  24 [EB][RF][ZF][DS]│ SELECTED POINT                  ˅ │
│ Conn.  │ 11.8┤ •                             │−0.20┤                               │ ○ XX Cyg · target                 │
│ F1     │ 12.0┤   •  •    •      •  •         │ 0.00┤ • • •  • • •  •  • • • •      │ UTC   2026-09-07 04:13:05         │
│ Observe│ 12.2┤ •   •   •  • •  •   •  •  •   │+0.20┤                               │ BJD   2461290.67812               │
│ F2     │ 12.4┤          ┆                    │+0.40┤        ┆ (linked time cursor) │ mag   12.143 ± 0.021 (σsys 0.008) │
│ Plan   │     └─04:10───04:20───04:30── UTC   │     └─04:10───04:20───04:30── UTC   │ comps 8 · airmass 1.090 · flags – │
│ F3     ├─────────────────────────────────────┼─────────────────────────────────────┤ frame …_e020000ms_g080_00007.fit  │
│▌Review │ □ 000-BCK-501 ▾  23 [EB][RF][ZF][DS]│ □ 000-BJV-169 ▾  24 [EB][RF][ZF][DS]│ Δt +10.0 s · FWHM 2.21 · HFD 6.8  │
│ F4     │        (plot, rows 270 px)          │        (plot)                       │ [OF Open frame]                   │
│        │                                     │                                     ├───────────────────────────────────┤
│        ├─────────────────────────────────────┼─────────────────────────────────────┤ COMPARISON QUALITY  6/8 stable  ˅ │
│        │ □ 000-BJV-170 ▾  24 [EB][RF][ZF][DS]│ ◇ FWHM (px) ▾          [ZF][DS]     │ Name          N  Scatter  Status  │
│        │        (plot)                       │        (plot, same UTC axis)        │ 000-BCK-396  24   0.012  Stable   │
│        │                                     │                                     │ 000-BCK-501  23   0.041  Noisy    │
│        │  ⌄ 5 more plots below (wall scrolls)│                                     │ …  (8 rows, 24 px)                │
│        │                                     │                                     ├───────────────────────────────────┤
│ Set.   │                                     │                                     │ AAVSO EXPORT                    ˅ │
│ F5     │                                     │                                     │ OBSCODE  unset · Settings ›       │
│        │                                     │                                     │ FILT TG · session filter IR  (!)  │
│        │                                     │                                     │ SESSION ›     STARS ›   (folded)  │
├────────┴─────────────────────────────────────┴─────────────────────────────────────┴───────────────────────────────────┤
│ status bar: server · Review · XX Cyg · 9 curves · cursor 04:13:05 UTC, 12.143 · theme · Log                            │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**WF-C. R1 with the Frames drawer open (T).** Drawer 260 px by default, resizable, remembered.

```
│        │   … plot wall (upper part, 3 rows still visible when the drawer is 260 px) …                                  │
│        ├─ FRAMES (24 lights · 0 missing) ─ [filter…] [CP] [columns ▾] ─ resize ═ ─ [FR]────────────────────────────────┤
│        │ UTC ▾                Type   Filter Exp (s) Gain  FWHM   HFD  Stars  Sky (ADU)  Ecc  Temp (°C)  File           │
│        │ 2026-09-07 04:07:25  Light  IR        20    80  2.18  6.90   4281       1360  0.53       25.4  …_00001.fit    │
│        │ 2026-09-07 04:13:05  Light  IR        20    80  2.21  6.80   4102       1364  0.51       25.5  …_00007.fit ◂  │
│        │ 2026-09-07 04:13:40  Light  IR        20    80     —     —      —          —     —         —  missing (dim)   │
│        │ click = time cursor on every plot · Enter / double-click = Frame inspector · right-aligned numbers            │
```

**WF-D. R2 Frame inspector.** Breadcrumb "Session › file" returns to R1 (Alt+←); the
rail cards fold; the image keeps at least 75 % of the width.

```
┌────────┬───────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ (mark) │ Session › …_00007.fit [FP][FN]│[OF]│[Z+][Z-][ZF][Z1]│[SA][SX][HG]│[CH][LU][SU]│[PS]│ (layers ↓) │[PN]         │
│        │   layers: [GR][FS][VS][GX][NB][EP][OO][CS][TS][LB][CT]  (one 47 px row in the real UI: 25 × 34 px)            │
│        ├───────────────────────────────────────────────────────────────────────────┬───────────────────────────────────┤
│ Conn.  │                                                                           │ FRAME                           ˅ │
│        │  ┌────────────────────────────────────────────────────────────────┐       │ XX_Cyg_ir_light_e020000ms_00007   │
│ Observe│  │ · ·   ·      ·   ·    ·     · ·      ·    ·   ·  ·    ·        │       │ 2160 × 3840 px · Light · IR       │
│        │  │   ·  ○ XX Cyg   □ 000-BCK-396   ·  ·       ·        ·     ·    │       │ 20 s · gain 80 · 25.4 °C          │
│ Plan   │  │ ·      ·   ·      ◎ selected       ·   ·      ·  ·             │       │ 2026-09-07 04:13:05 UTC · X 1.09  │
│        │  │   ·  ·       ·          □     ·     ·   ·    ·     ·   ·       │       ├───────────────────────────────────┤
│▌Review │  │ (portrait frame turned landscape: rotation auto)               │       │ SELECTED STAR                   ˅ │
│        │  │                                     chips: 7/24 · 20 s · IR    │       │ Gaia DR3 1234… · G 12.87          │
│        │  └────────────────────────────────────────────────────────────────┘       │ FWHM 2.21 px (3.2″) · HFD 6.8 px  │
│        │                                                                           │ ecc 0.51 · SNR 140 · peak 32010   │
│        │                                                                           │ sky 1364 ADU · aperture r [ 5 ] px│
│        │                                                                           ├───────────────────────────────────┤
│        │                                                                           │ IDENTIFICATION                  ˅ │
│        │                                                                           │ RA 20h 03m 15.6s Dec +58° 57′ 17″ │
│        │                                                                           │ 3.67″/px · rot 91.2° · 1412 src   │
│        │                                                                           │ [PS Identify field]  (or progress)│
│ Set.   │                                                                           ├───────────────────────────────────┤
│        │                                                                           │ DISPLAY (H) · FITS HEADER (folded)│
├────────┴───────────────────────────────────────────────────────────────────────────┴───────────────────────────────────┤
│ status bar: cursor x 1024 y 2210 · 1412 ADU · RA 20h 03m 12.1s Dec +58° 58′ 02″ · zoom fit · theme · Log               │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**WF-E. Export AAVSO dialog (modal, 640 px).** Opened from the toolbar or the card. "Export"
is disabled with a reason when there is no target curve; an unset OBSCODE needs the explicit
"Export anyway" variant of the primary button (text: "Export with OBSCODE=XXX").

```
┌────────────────────────────────────────────────────────────────────────────┐
│ Export AAVSO extended format                                      [CL]     │
├────────────────────────────────────────────────────────────────────────────┤
│ Source      XX Cyg · 20260907T040723Z_XX_Cyg (session photometry)          │
│ Targets     [x] ○ XX Cyg   24 rows (0 skipped: non-finite mag)             │
│ OBSCODE     unset  — the file would carry OBSCODE=XXX   [Open Settings]    │
│ FILT        [ TG ▾ ]   session frames: IR   (!) check the band code        │
│ CHART       X12345AB  (from targets.json comparisons)                      │
│ Check star  none in this source → KNAME / KMAG = na                        │
│ DATE        JD UTC, exposure midpoint · MTYPE STD · CNAME ENSEMBLE         │
│ File        [ ~/Argos/sessions/…/XX_Cyg_aavso.txt          ] [BR]          │
├────────────────────────────────────────────────────────────────────────────┤
│ Preview  #TYPE=EXTENDED / #OBSCODE=… / first 3 rows in mono                │
├────────────────────────────────────────────────────────────────────────────┤
│                                   [ Cancel ]   [ Export ]  (primary)       │
└────────────────────────────────────────────────────────────────────────────┘
```

**WF-F. Re-run photometry dialog (modal, 640 px) and the running job.**

```
┌────────────────────────────────────────────────────────────────────────────┐
│ Re-run photometry over saved frames                               [CL]     │
├────────────────────────────────────────────────────────────────────────────┤
│ Frames      [ <session>/lights       ] [BR]  195 files (.fit .fits .fts)   │
│ Stars       session targets.json · 1 target · 6 comparisons · 0 check      │
│ Reference   ( ) live solve from Observe   (•) identify first frame (ASTAP) │
│ Aperture    2.50 × FWHM, floor 4.0 px · annulus 8.0–12.0 px  Settings ›    │
│             tracking on · e-/ADU 2.31 (gain 80) · band TG · site set       │
│ Output      <session>/photometry_rerun_20261101T2104Z/   (new folder)      │
│ [x] Write diagnostics (diagnostics.jsonl)                                  │
├────────────────────────────────────────────────────────────────────────────┤
│                                   [ Cancel ]   [ Start ]  (primary)        │
└────────────────────────────────────────────────────────────────────────────┘

Job strip (replaces the identity text in the session toolbar while running):
│ [busy] Re-running photometry · 37 / 195 frames · ETA 2m 10s · field rot +0.4° │ [ST Cancel] │
```

**WF-G. Imported CSV (pseudo-session).** Same as WF-B, with: toolbar identity
"Imported · {file}.csv · {n} curves"; no `frames` button and no Frames drawer; card
Comparison quality shows "No quality report for an imported file."; card Stars filled from a
`targets.json` found next to the file (or its parent), else "No targets.json next to this
file: roles come from the file."; a role chip on each cell lets the observer correct the role
of a single-star file (target / comparison / check) before exporting (fixes P31).

### 2.4 Interaction and states

**Visible without scrolling at 1440 × 900 (R1, rail open):** toolbar; six plot cells
(target, four comparisons, the quality cell when there are few stars, else the first six in
order); cards Selected point and Comparison quality (8 rows) open, AAVSO export summary
folded to its header plus the OBSCODE/FILT lines; status bar. With the rail collapsed (P) the
wall uses 1348 px and switches to three columns.

**States.**

| State | R0 Sessions | R1 Session | R2 Inspector |
|---|---|---|---|
| Server link down | Observe's empty state ("Waiting for the ARGOS server") | last data kept, toolbar actions disabled with the reason | idem |
| Loading | skeleton rows, `aria-busy` | identity shows "Opening {folder}…" with the spinner; cells show axis frames only | viewer empty state "Loading {file}…" |
| Empty | "No sessions in {path}" + Open folder… / Import CSV… | no curves: one quality cell + message "No photometry CSV in photometry/. Re-run photometry or import a CSV." | — |
| Partial | issues count in the list | readiness badge "N issues" (warning, icon + label); popover lists them, one line each, "Missing FITS frame" grouped as "{k} missing FITS frames" with the names behind a disclosure (fixes P5) | — |
| Complete | — | badge "Complete" in a neutral style (not warning, fixes P5) | — |
| Busy | — | job strip (re-run, export) | Identification card: spinner + "Identifying field (ASTAP)…" + Cancel; then "Identifying catalogue sources…" |
| Error | inline banner with the server message (e.g. "No session.json in {root}") + toast | toast + log; failing CSV named in the badge popover ("Could not read preview curve: {name}"); a malformed CSV never leaves the screen half updated (P13: the API returns the whole session or an error) | toast "Could not open {file}: {reason}" and the previous frame stays (P28) |

**Confirmations (text-only buttons, BRAND §7).** Export AAVSO with no OBSCODE: the dialog
shows the problem inline and the primary button reads "Export with OBSCODE=XXX". FILT differs
from the session's filter: inline warning, export allowed. Re-run when the output folder
exists: never happens (a new timestamped folder each time). Reset layout: no confirmation (it
only touches layout preferences, and BRAND puts it in icon + label).

**Selection model.** One selected time (a point, a Frames row, or R2's frame) drives: the
time cursor on every cell (`--chart-highlight`), card Selected point, the Frames row
highlight, and R2's frame when R2 opens. Card Selected point shows: star and role glyph, UTC
(ISO, seconds), JD and BJD_TDB (5 decimals), magnitude ± error (3 decimals), formal error and
σ_sys, comparisons used (mag / relative), airmass, flags saturated / suspect, matched frame
name, Δt between the point (exposure mid-time) and the frame start, frame FWHM/HFD/sky, and
"Open frame". Points flagged suspect are drawn hollow; saturated points keep the × mark.

**Plots.** BRAND §10: roles by colour token and marker shape; magnitude axis inverted
(relative flux not inverted); time axis UTC clock by default with the night's date in the
axis title, JD or BJD_TDB on demand (Q6); X linked across all cells; legend in the header,
never over the data; error bars at `--chart-error-opacity`; no brass for data (P39).

**Keyboard (single keys only when focus is not in a text field; none moves hardware).**

| Screen | Key | Action | Origin |
|---|---|---|---|
| Review | F4 | Review section | Qt |
| Review | Ctrl+Shift+O | Sessions (R0) | Qt binding, new target |
| Review | Ctrl+O | Open FITS… in R2 | Qt binding (was Observe), Q8 |
| R1 | F | fit every cell | proposed (Observe meaning "fit") |
| R1 | + / − | zoom the time axis | proposed |
| R1 | T | Frames drawer | proposed |
| R1 | P | rail | as Observe |
| R1 | Enter | Open frame of the selected point / row | proposed |
| R2 | + − F 1 A Shift+A H X Z P | as Observe (zoom, stretch, display card, crosshair, loupe, rail) | Observe |
| R2 | S | Identify field | inventory `plate-solve` |
| R2 | G | coordinate grid | inventory `sky-grid` |
| R2 | PageUp / PageDown | previous / next session frame | proposed |
| R2 | Alt+← | back to the session | proposed |

Escape only closes popovers and dialogs here; it is not used for navigation so that it stays
free for the global "abort motion" key (Q11).

**Night Red.** Image drawn as `v × --viewer-tint`; palettes other than Neutral disabled with
a tooltip ("Not available in Night Red"); saturated pixels drawn black; overlays from
`--overlay-*`; plot roles single hue, told apart by shape and the header label; the time
cursor and selection in `--toggled-fg`; every status (readiness, quality Stable / Noisy /
Unstable, job state) carries a word, not only a colour; custom listboxes instead of native
`<select>`; Tauri save/open dialogs are OS dialogs and can draw grey (BRAND §4.3): prefer the
in-app path field in Night Red (Q9).

**Persistence (per viewer, `localStorage` through `lib/app/prefs.ts`, try/catch; never server
config unless stated).** Last opened session path; wall cell order, hidden cells, columns,
row height; per-role toggles (uncertainties, relative flux); quality metric; time axis unit;
rail open and card fold states; Frames drawer open, height, hidden columns, sort; R2 preview
mode, palette, aperture radius, crosshair, loupe, saturation, display card state. Server
config (shared with Observe and Settings): `catalog.display_mag_limit` (saved on change end),
`ui.display.rotation` (read; written by the rotation control as on Observe),
`observer.obscode` and `photometry.default_band` (read; edited in Settings). `ui.review.layout`
(Qt dock state) is not migrated.

### 2.5 API needs beyond v1

All routes need the token; paths are absolute server paths; the server refuses paths outside
`sessions_path` unless the observer opened them explicitly (Q4). Long jobs use one generic job
model: `POST` returns `{job_id}`; `/ws/events` sends `{"type":"job", "job": {id, kind, state:
"running"|"done"|"cancelled"|"error", done, total, message, result?}}`; `DELETE
/api/jobs/{id}` cancels.

| Name | Kind | Payload sketch | Core / worker code it wraps (file:line) | Notes |
|---|---|---|---|---|
| List sessions | GET `/api/review/sessions` | → `[{path, folder, object, started_utc, software, frames, lights, filters{}, curves{target, comparison, check}, has_quality, issues}]` | new scanner over `Config.sessions_path` (config.py:269) calling `load_session(read_temperature=False)` (RV:102) and globbing `photometry/*.csv` | fast path: no FITS header reads; cache by folder mtime |
| Open session | GET `/api/review/session?path=` | → `{root, object_name, started_utc, software, observer, summary, metadata, comparison_quality, warnings, readiness_issues, frames:[{filename, image_type, filter_name, exposure_s, gain, timestamp, hfd, fwhm, star_count, sky_adu, peak_adu, eccentricity, ccd_temp, path\|null}], targets:[TargetStar], chart_id}` | `load_session` RV:102-175, `readiness_issues` RV:76-82, frame paths from one recursive glob (RV:147, instead of `frame_path` per frame RV:84-86), `TargetSet.load` (targets.py:207), `comparison_chart_id` (targets.py:219) | atomic: whole session or an error (P13); off the event loop (P12); `summary` from session.json added (P20) |
| Session curves | GET `/api/review/session/curves?path=` | → `[{key, role, name, auid, points:{jd_utc[], bjd_tdb[], mag[], mag_err[], formal_mag_err[], sigma_syst[], airmass[], fwhm[], sky_adu[], comps_used[], relative_flux[], relative_flux_err[], relative_comps_used[], saturated[], suspect[]}}]` | `load_session_curves` RV:178-212, `LcPoint` LC:39-62 | columnar arrays; fix the `check_` role (P19) in `_curve_identity` RV:215-240 |
| Import curve CSV | POST `/api/review/import-csv` | `{path}` → same shape as Session curves + `{targets, chart_id, inferred_roles}` | `read_curves_csv` LC:150-170, targets.json lookup as AP:756-760, role from filename as RV:215-240 | KeyError/encoding errors become a 422 with the reason (P13) |
| Frame pixels (read-only) | GET `/api/files/frame?path=&view=raw\|superpixel\|r\|g\|b` | → binary frame, same layout as `/ws/frames` (`source:"file"`), header adds `green_shape`, `filename`, `date_obs`, `exptime` | `read_fits_2d` AW:54-65, `build_processed_frame` (preview_processor.py:58) for the views | must **not** publish to `/ws/frames` (v1 `open-fits` does, which would replace the live view) |
| FITS header | GET `/api/files/fits-header?path=` | → `{text, keywords:{OBJECT, DATE-OBS, …}}` | `read_fits_header_text` AW:126-133, `read_fits_meta` AW:68-123 | |
| Measure star | POST `/api/files/measure-star` | `{path, x, y, radius, snap:boolean}` → `{x, y, fwhm_px, hfd_px, eccentricity, snr, peak_adu, sky_adu, radius, arcsec_per_px, ra_hours?, dec_deg?}` | `measure_star_at` (metrics.py:225), `arcsec_per_green_px` (metrics.py:59), WCS `pixel_to_radec` | coordinates in un-rotated green-plane pixels; arcsec from the solved scale when a solve exists (P27) |
| Identify field | POST `/api/files/solve` (job) | `{path}` → result `{solved, message, ra_hours, dec_deg, scale_arcsec_px, rotation_deg, wcs, grid:{polylines, labels}}` | `SolveWorker` (solve_worker.py:20), `build_solve_settings(live=False)` (astrometry_session.py:36), `full_res_scale` (:75), `wcs_from_result` (:87), `overlay_for` (:137) | long (ASTAP); cancellable (new: kill the ASTAP process; Qt cannot, P28) |
| Field catalogues | POST `/api/files/catalogue` (job) | `{path or solve_id, mag_display_limit}` → result `{counts{layer}, markers:[{layer, x, y, label, tooltip, g_mag?, suspected?, role?}]}` | `CatalogRequest`/`CatalogWorker` (catalog_worker.py:33, :80) built as AW:588-629, projection AW:668-858, `essential_catalogue_objects` (offline.py:81), `cached_exoplanet_hosts_in_cone` (exoplanets.py:138), target set as AW:343-348 | network-dependent; progress messages; Gaia `g_mag` lets the client re-filter the limit without a new request |
| Config subset | GET / PATCH `/api/config` | keys `observer.obscode`, `photometry.default_band`, `catalog.display_mag_limit`, `catalog.field_stars_mag_limit`, `ui.display.rotation`, `camera.full_well_adu`, photometry params for the re-run summary | `Config.get/set/save` (config.py) | shared with the Settings spec |
| Export AAVSO | POST `/api/review/export/aavso` | `{source:{session_path \| import_id}, keys[], path?, obscode, filt, chart?}` → `{path, rows, skipped_nonfinite, kname, text?}` | `write_aavso` LC:204-254, `comparison_chart_id` (targets.py:219) | `path` absent → returns `text` for a browser download; never writes rows for non-target roles |
| Export measurements | POST `/api/review/export/csv` | `{source, keys[]?, path?}` → `{path, rows, text?}` | `write_curves_csv` LC:136-147 | |
| Re-run photometry | POST `/api/review/rerun` (job) | `{frames_dir \| paths[], targets:{session_path \| live:true}, reference:{solve_path \| live:true}, out_dir, diagnostics}` → progress `{done, total}`, optional point stream, result `{frames_done, frames_skipped, curves:[{key, role, n}], rotation_deg, shift_px, check_rms:{key: rms}, out_dir, cancelled}` | `PhotometryBatchWorker` BW:71-155, `BatchRequest` BW:43-53, `PhotometryParams.from_config` (params.py:48-68), e-/ADU as IP:2320-2335, `cancel` BW:92-94 | glob `.fit/.fits/.fts` (P33); default `out_dir` inside the session (P34); report skipped frames and cancellation (P35) |
| Job events / cancel | WS `job` message; DELETE `/api/jobs/{id}` | see header | wraps the three jobs above | one model for solve, catalogue, re-run |

## 3. Open questions for the owner

1. **Re-run photometry**: move it from Observe (Photometry ▸ Re-run subs…) into Review, or
   offer it in both? Should the reference be a solve of a session frame (proposed default)
   rather than the live Observe solve? Where should results go (proposed:
   `<session>/photometry_rerun_<UTC>/`, never overwritten) and should Review then compare
   the live-preview run and the re-run side by side?
2. AAVSO **FILT**: keep the configured band (default TG) or derive it from the session's
   filter (the sample sessions record "IR")? Is the "Export with OBSCODE=XXX" confirmation
   acceptable, or should export be blocked until the code is set?
3. Should Review open folders outside `sessions_path` (Open folder…, Import CSV…) when the UI
   runs in a plain browser, given that the server then reads arbitrary paths with the token?
4. Session list root: only `sessions_path`, or several roots (e.g. an external disk)?
5. Second monitor: is a Tauri "Pop out" (plot cell or frame inspector in its own window)
   needed for the first web release, or is "Expand" enough?
6. Default time axis for light curves: UTC clock, JD, or BJD_TDB (when the site was known)?
7. Keep the CFA preview modes and false-colour palettes in the inspector (Observe's web
   viewer has not ported them yet)?
8. Ctrl+O: in Qt it always opens a FITS **in Observe**; in Review the proposal opens it in
   the inspector. One global meaning, or per section? Same question for a Tauri app menu
   (File ▸ Open…).
9. Night Red and OS dialogs: accept grey native file dialogs, or require the in-app path
   field in Night Red?
10. Should the Review page show the star_var_script outputs present in some sessions
    (`results/`, `process/`) and the `diagnostics/` flight records?
11. Should Escape abort a slew from every section (the Observe screen handles it only while
    mounted), even from Review?
12. Post-hoc ensemble editing: should Review allow excluding a bad comparison (e.g.
    "Noisy") and recomputing the target curve, or stay strictly read-only?

### Uncertain points (not exercised; stated from the code)

- U1. Hover is dead per pyqtgraph 0.13.7 in `.venv` (verified there); another pyqtgraph version
  could differ.
- U2. P1 was verified with an empty config; with a saved `ui.review.layout`, the conclusion
  that `restoreState` cannot place the parentless FWHM dock is inferred from Qt's behaviour.
- U3. The Frame Viewer image and the quality plot keep pyqtgraph's default `ViewBox` context
  menu (no `setMenuEnabled(False)`); its exact entries were not opened.
- U4. Frames and Metadata cells are editable per Qt's default edit triggers (no
  `setEditTriggers` call); not clicked in the probe.
- U5. Check-star CSVs shown as targets (P19): inferred from RV:218 and
  acquisition_engine.py:1266; no session on disk contains a check star.
- U6. Batch re-run finding no `.fit` files (P33): inferred from IP:2287-2289 and the `.fit`
  names of every sample session; the batch was not run.
- U7. The `KeyError` crash path of a malformed CSV (P13) was not executed.
- U8. The batch progress dialog is non-modal because no modality is set (IP:2308-2318).
- U9. Live-run curve JDs are exposure mid-times per the `LcPoint` docstring (LC:40); only the
  batch path (BW:385-389) was traced to the code that adds EXPTIME/2.

