# Observe screen orchestration (Qt imaging page): Qt inventory and web redesign

Author: spec agent "observe-page", 2026-11-01. Source of truth: the code at branch
`explore/web-ui` (all `file:line` below are from that tree). Docks are only referenced
here; their own controls are inventoried by the viewer-tools and hardware-dock specs.

## 0. Scope

### Files covered

| File | Lines | Covered how |
|---|---|---|
| `argos/ui/pages/imaging_page.py` | 2888 | Every line read. Primary subject. |
| `argos/ui/widgets/image_toolbar.py` | 106 | Read in full (hosted by the page). |
| `argos/ui/widgets/overlay_bar.py` | 194 | Read in full (hosted by the page). |
| `argos/ui/widgets/star_info_card.py` | 240 | Read in full (owned by the page). |
| `argos/ui/widgets/dock_host.py` | 180 | Read in full (dock factory, panel-strip style). |
| `argos/ui/panels/manual_control_dialog.py` | 215 | Read in full (opened by the page). |
| `argos/ui/panels/log_panel.py` | 84 | Read in full (dock content). |
| `argos/ui/shell.py` | 625 | Lines 120-477 and 610-620: the menu entries and wiring that drive this page. |
| `argos/core/session/acquisition_engine.py` | 1652 | Handlers followed: 115-1060, 1222-1652. |
| `argos/core/session/device_session.py` | 831 | Mount / focuser / filter / camera commands 540-770. |
| `argos/workers/astrometry_controller.py` | 247 | Read in full (plate-solve lifecycle, auto-solve policy). |
| `argos/workers/object_resolver_worker.py` | 106 | Read in full. |
| `argos/workers/preview_processor.py` | 150 | Read in full. |
| `argos/workers/photometry_batch_worker.py` | 402 | 1-160 (request, result, run loop). |
| `argos/ui/panels/photometry_window.py` | 327 | Structure and signals only (photometry spec owns it). |
| `argos/ui/widgets/astrometry_settings.py` | 396 | Keys and signals only (settings spec owns it). |
| web: `App.svelte`, `lib/imaging/*`, `lib/shell/StatusBar.svelte`, `lib/app/shortcuts.ts`, `lib/app/state.svelte.ts`, `README.md`, `argos/server/protocol.md`, `design/BRAND.md`, `design/icon-inventory.json` | | Read to design section 2. |

Offscreen checks (read-only, `QT_QPA_PLATFORM=offscreen`, isolated `HOME`, `Config.save`
neutralised; scripts and PNGs in the session scratchpad `webui-spec/observe-page/`):
`imaging_default.png` and `imaging_all_docks.png` (1376 x 820 grabs), the dock areas after
the default layout, the implicit dock context menu, and the star-card Dismiss bug (1.7).

### Everything in scope and how it opens

| # | Element | Kind | Opened by | Modal |
|---|---|---|---|---|
| A | `ImagingPage` (Qt mode "capture", label "Observe") | page hosting an inner `QMainWindow` workspace | sidebar F2 (`shell.py:230-234`), File ▸ Open FITS image (`shell.py:288`), status-bar capture strip (`shell.py:317`) | no |
| B | Image toolbar (`ImageToolbar`) | toolbar row 1 | always | no |
| C | Panel-toggle strip | `QToolBar` row 2 | always | no |
| D | "Panels ▾" menu | `QMenu` popup | C, InstantPopup | no |
| E | "Arrange ▾" menu | `QMenu` popup, rebuilt on every show | C, InstantPopup | no |
| F | 8 dock containers ("Acquisition", "Telescope", "Focusing", "Image display", "Image statistics", "Focus diagnostics (HFD/FWHM)", "Activity log", "Differential photometry") | `QDockWidget` | C chips, D, E, default layout | no |
| G | Implicit dock list context menu | `QMainWindow.createPopupMenu()` | right-click on a dock title bar / dock separator (Qt default, not coded) | no |
| H | Overlay bar (`OverlayBar`) | toolbar rows 3-4 | always | no |
| I | Viewer click / marker hover (page-owned part) | mouse behaviour | left click on image, hover on markers | no |
| J | Star info card (`StarInfoCard`) | on-image floating card | left click on image | no |
| K | Context bar (Frame / Sequence) | status strip under the image | always | no |
| L | "Open FITS" file dialog | `QFileDialog` (native) | B "Open image…", File ▸ Open FITS image… Ctrl+O | yes |
| M | Field identification & catalogue settings dialog, Catalogue tab | `QDialog.exec()` | H "Catalogues / depth…" (also Field menu, shell) | yes |
| N | Field photometry window (`PhotometryWindow`) | top-level window | Photometry ▸ Photometry setup… / Live curves & diagnostics… (shell), end of a batch re-run | no |
| O | Batch re-run: 4 information boxes, folder dialog, progress dialog, failure box | `QMessageBox`, `QFileDialog`, `QProgressDialog` | Photometry ▸ Re-run subs… (shell) | boxes and folder dialog modal; progress dialog shown with `show()` and no modality set, so non-modal (U5) |
| P | Manual control dialog (`ManualControlDialog`) | tool window, stay-on-top | Telescope dock "Jog dialog…" | no |
| Q | Marker tooltips (8 formats) | hover tooltips on viewer markers | hover | no |
| R | Analysis window (`AnalysisWindow`) via `open_analysis` | top-level window | **unreachable from the page** (no caller, 1.21) | no |
| S | Shell menu entries that drive this page (File, Field, Photometry, View ▸ Reset Window Layout) | `QAction` | menu bar | no |

## 1. Inventory (Qt, as it is today)

Log levels used by the page and the engine: `OK`, `INFO`, `WARN`, `ERROR`, `CMD`
(`log_panel.py:71` colours them; the web log knows only info / warning / error).

### 1.1 ImagingPage container (`ImagingPage`, `imaging_page.py:135`, page, sidebar F2, non-modal, central stack)

- Purpose: the observing workspace. Builds the toolbars and docks, routes dock intents to
  `DeviceSession` / `AcquisitionEngine`, renders their signals, and owns the field
  workflows (identify, catalogue overlays, target roles, live photometry, batch re-run).
- Layout (`_build_ui`, 230-328): row 1 image toolbar (236), row 2 panel strip (313-314),
  row 3-4 overlay bar (317-322), then an inner `QMainWindow` used as a widget (256-264:
  `AnimatedDocks | AllowTabbedDocks | AllowNestedDocks | GroupedDragging`, nesting on).
  Central widget = viewer + context bar (269-275).
- Docks (279-307), object names stable for `saveState`: `dock.camera` "Acquisition"
  (CameraDock), `dock.mount` "Telescope" (MountDock), `dock.focuser` "Focusing"
  (FocuserDock), `dock.display` "Image display" (HistogramDock), `dock.statistics`
  "Image statistics" (StatisticsDock), `dock.hfd_history` "Focus diagnostics (HFD/FWHM)"
  (HfdHistoryDock, no scroll), `dock.log` "Activity log" (LogPanel, no scroll),
  `dock.lightcurve` "Differential photometry" (LightCurvePanel, no scroll).
- Default arrangement (`_apply_default_layout`, 443-483): right area Camera, Mount and
  Focuser tabbed, Camera raised; bottom area Log; Display, Statistics, HFD history and
  Light curve hidden. Verified offscreen: the light curve ends in the **right** area,
  not tabbed with Log (problem P2).
- Persistence: `ui.imaging.layout` = base64 `QMainWindow.saveState()` (120-121, 495-498),
  written by the Shell on close (`shell.py:448`); restored at build (485-493, corrupt
  blob logged and ignored); "Reset layout" sets it to `None` and re-applies defaults live
  (500-503).
- Timers: `_catalog_project_timer`, single-shot 75 ms, coalesces overlay re-projection
  (206-212, 1467-1472). No other timer in the page.
- Threads owned: `PreviewProcessor` (163, 219-220, latest-frame-wins), and on demand
  `ObjectResolverWorker`, `NearbyObjectResolverWorker`, `PointIdentityWorker`,
  `PhotometryBatchWorker`.
- Startup (214-224): engine gets the capture-parameter providers
  `CameraDock.params` / `CameraDock.preview_scale` (217); persisted target set is
  projected and stored curves rendered before the first frame (223-224).
- Shutdown (`shutdown`, 2854-2879; `closeEvent` 2886-2888): closes analysis windows and
  the photometry window, cancels the batch worker (wait 3 s), waits the object resolver
  (9 s) and point identification (38 s, "Gaia and SIMBAD have independent bounded requests
  (20 s + 15 s)"), then `engine.shutdown()` (5 s budget) and the processor (2 s).
- Resize: keeps the star card inside the viewer (2881-2884).

Upward signals (138-149) relayed to the Shell:

| Signal | Source | Consumer |
|---|---|---|
| `device_state_changed(device, state, info)` | session + engine (513, 530, 658) | status bar, Connection page (`shell.py:305, 367-372`) |
| `tracking_changed(bool\|None)` | session (514) | status bar (`shell.py:306`) |
| `action_changed(text)` | session, engine, `_STATE_ACTION` (126-132, 633), AF done (2848) | status bar action text (`shell.py:307`) |
| `log_message(level, msg)` | everything | Activity log dock (614) and Shell |
| `camera_state_changed(CameraState)` | engine (529) | status LIVE chip (`shell.py:315, 383-384`) |
| `hfd_updated(float\|None)` | per processed frame (748) | status bar HFD (`shell.py:314`) |
| `autofocus_state(bool)` | engine (2830) | sidebar dot (`shell.py:316`) |
| `auto_solve_armed(bool)` | sequence start/stop (2545, 2548) | Field ▸ Keep field identified automatically (`shell.py:257`) |
| `target_coordinates_changed(name, ra_h, dec_d)` | catalogue target (2665) | Sequencer (`shell.py:172`) |
| `autofocus_step`, `autofocus_best` | AF (2838, 2846) | **no consumer** (dead relay) |

Action texts (`_STATE_ACTION`, 126-132): "Idle", "Live preview", "Taking shot…",
"Sequence running", "Autofocus running"; plus from the astrometry controller
"Plate-solving…", "Idle", "Solve failed — keeping last WCS", "Auto-solve on",
"Auto-solve off", "WCS cleared (slew)" (`astrometry_controller.py:85, 99, 190, 211, 216`),
and "Focused  pos={best}" (2848).

### 1.2 Image toolbar (`ImageToolbar`, `image_toolbar.py:22`, built `imaging_page.py:236`, toolbar row 1, always visible)

- Purpose: open a FITS frame and choose the display-only preview view.
- Height 38-48 px (39-40).

| # | Control | Qt type | Label / tooltip (exact) | Default / range | Enabled / visible | Shortcut | Action: handler -> effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Open image… | QPushButton (51-54) | "Open image…" / "Open a FITS image" | | always | none here (Ctrl+O is on the Shell File menu) | `open_requested` -> `_on_open_fits` (553, 1312-1339): native dialog (1.9), astropy `getdata`, must be 2-D, cast to uint16, `engine.ingest_frame` (`acquisition_engine.py:515`) -> `frame_ready` -> normal pipeline | no |
| 2 | Preview | QComboBox (56-77), caption "Preview:" | options: "Colour (CFA)" = `Super-pixel` (default), "Raw CFA", "Red (CFA)", "Green (CFA)", "Blue (CFA)" / tooltip "Changes only the on-screen preview; every view keeps the same sensor geometry and annotation coordinates. FITS data are unchanged." | index 0 | always | none | `channel_changed` -> `_on_channel_changed` (552, 714-719): stores the view, re-submits the last raw frame to `PreviewProcessor` (`render_view`) | no (resets to Colour at launch) |
| 3 | Palette | QComboBox (79-94), caption "Palette:" | "Neutral", "Negative", "Fire", "Ice" / "False-colour display palette for inspecting faint detail and saturation." | Neutral | always | none | `palette_changed` is **never connected** on this page (only `analysis_window.py:281`): dead control (P1) | no |

Displayed data: right-aligned muted label "Preview only · FITS unchanged" (97).

### 1.3 Panel-toggle strip, "Panels ▾" and "Arrange ▾" (`_build_panel_bar`, `imaging_page.py:348-391`; menus 370, 384; toolbar row 2)

- Purpose: show / hide / float docks and reset the layout. Style: neutral chips
  (`panel_toolbar_qss`, `dock_host.py:134-180`); checked = dock visible.
- Each chip is the dock's `toggleViewAction()` renamed (`style_toggle_action`,
  `dock_host.py:122-131`); tooltip for every chip (356-359): "Show/hide {label}. Drag its
  title bar to arrange it; double-click the title to detach it."

| # | Control | Qt type | Label / tooltip | Default | Enabled / visible | Shortcut | Action -> effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Acquisition | checkable QAction (355, 362-364) | "Acquisition" | checked | always | none | toggle `dock.camera` visibility | layout blob |
| 2 | Telescope | same | "Telescope" | checked (tabbed behind) | always | none | toggle `dock.mount` | layout blob |
| 3 | Focusing | same | "Focusing" | checked (tabbed behind) | always | none | toggle `dock.focuser` | layout blob |
| 4 | Image display | same | "Image display" | unchecked | always | none | toggle `dock.display` | layout blob |
| 5 | Differential photometry | same | "Differential photometry" | unchecked | always | none | toggle `dock.lightcurve` | layout blob |
| 6 | Panels ▾ | QToolButton InstantPopup (366-375) | "Panels ▾" / "Show optional diagnostics and the activity log" | | always | none | opens menu D | no |
| 7 | D ▸ Image statistics | checkable QAction (371-373) | "Image statistics" | unchecked | always | none | toggle `dock.statistics` | layout blob |
| 8 | D ▸ Focus diagnostics (HFD/FWHM) | same | "Focus diagnostics (HFD/FWHM)" | unchecked | always | none | toggle `dock.hfd_history` | layout blob |
| 9 | D ▸ Activity log | same | "Activity log" | checked | always | none | toggle `dock.log` | layout blob |
| 10 | Arrange ▾ | QToolButton InstantPopup (380-387) | "Arrange ▾" / "Float, re-dock or reset any panel" | | always | none | opens menu E, rebuilt on `aboutToShow` (385, 393-403) | no |
| 11 | E ▸ Restore default layout | QAction (396-397) | "Restore default layout" | | always | none | `reset_layout` (500-503) | clears `ui.imaging.layout` |
| 12-19 | E ▸ "Float {label}" / "Dock {label}" x 8, in `_PANEL_ORDER` (332-341) | QAction (399-403) | verb from `dock.isFloating()` | | always | none | `_toggle_dock_floating` (405-410): flip floating, `show()`, `raise_()` (a hidden dock becomes visible) | layout blob |
| 20 | Reset layout | QAction on the bar (388-390) | "Reset layout" / "Restore the default panel arrangement" | | always | none | `reset_layout` (same as #11) | clears `ui.imaging.layout` |

Implicit behaviour: `toggleViewAction` stays checked for a dock tabbed *behind* another,
so clicking "Telescope" while "Acquisition" is the front tab hides Telescope instead of
raising it (P3).

### 1.4 Dock containers (`make_dock`, `dock_host.py:48-115`; 8 instances, `imaging_page.py:279-307`)

- Purpose: NINA-style movable / closable / floatable panels (features 69-74).
- Scroll docks wrap content in a vertical-only `QScrollArea` (92-112); Card titles are
  blanked so the dock title is the only heading (82-90).

| # | Control | Qt type | Label / tooltip | Enabled when | Action -> effect | Persisted |
|---|---|---|---|---|---|---|
| 1 | Title-bar drag | dock title (Qt) | dock title | always | move, re-dock into another area, tab onto another dock (`GroupedDragging` moves a tab group) | layout blob |
| 2 | Title-bar double-click | Qt default | | always | float / re-dock | layout blob |
| 3 | Float button | title-bar button (Qt) | | always | float / re-dock | layout blob |
| 4 | Close button | title-bar button (Qt) | | always | hide the dock; its chip unchecks | layout blob |
| 5 | Dock tab bar | auto tab bar of tabified docks | dock titles | when tabified | raise the clicked dock | layout blob |
| 6 | Splitters | dock-area / central separators | | always | resize | layout blob |
| 7 | Dock list context menu (G) | `QMainWindow.createPopupMenu` (default `DefaultContextMenu` policy, verified offscreen) | 8 checkable entries: Telescope, Focusing, Acquisition, Differential photometry, Activity log, Image display, Image statistics, Focus diagnostics (HFD/FWHM) | right-click on a dock title / separator (uncertain: trigger not tested) | toggle visibility | layout blob |
| 8 | Vertical scroll | QScrollArea | | when the dock is shorter than its card | scroll | no |

### 1.5 Overlay bar (`OverlayBar`, `overlay_bar.py:54`, built `imaging_page.py:317-322`, rows 3-4, max height 76 px)

- Purpose: show / hide solved-field layers, set the stellar display depth, open the
  catalogue settings. Row "Objects" (76-80), row "Display" (82-129).
- Chips are checkable, **disabled until available** (144); disabled tooltip "Solve and
  identify the field to enable this layer." (178); text gets a count "{label} · {n}"
  (166-169). All chips signal `toggled(name, on)` -> `_on_overlay_toggled` (555,
  1409-1425) -> the matching `FitsViewer.set_*_enabled`.

| # | Control | Qt type | Label / tooltip (exact) | Default | Enabled when | Action -> effect | Persisted |
|---|---|---|---|---|---|---|---|
| 1 | Stars (`catalogue`) | checkable QPushButton (24, 141-149) | "Stars · n" / "Gaia DR3 stars, enriched with conventional SIMBAD identities when available." | auto-checked the first time it has points (1698) | field solved (1723-1734) | `viewer.set_field_catalogue_enabled` | no (re-armed per field) |
| 2 | Variables (`variables`) | same (25) | "Variables · n" / "Variable stars from the AAVSO VSX catalogue." | auto-checked first time (1699) | field solved | `viewer.set_catalog_enabled` | no |
| 3 | Galaxies | same (26) | "Galaxies · n" / "Galaxies identified by SIMBAD or the bundled Messier/NGC/IC catalogue." | auto (1700-1704) | field solved | `set_context_enabled("galaxies")` | no |
| 4 | Nebulae + clusters | same (27) | "Nebulae + clusters · n" / "Nebulae and stellar clusters identified by SIMBAD or the bundled Messier/NGC/IC catalogue." | auto (1705-1709) | field solved | `set_context_enabled("nebulae_clusters")` | no |
| 5 | Exoplanets | same (28) | "Exoplanets · n" / "Confirmed exoplanet hosts returned by NASA (cache first)." | auto (1710-1714) | field solved | `set_context_enabled("exoplanets")` | no |
| 6 | Other objects | same (29) | "Other objects · n" / "Other physically classified SIMBAD sources, such as radio or X-ray sources." | auto (1715-1719) | field solved | `set_context_enabled("other_objects")` | no |
| 7 | Coordinate grid (`grid`) | same (32) | "Coordinate grid" / no specific tooltip -> "Show or hide this overlay." (146) | auto-checked on first solve (1397) | after a solve (1397) | `viewer.set_astrometry_enabled`; duplicate of the Image display dock "WCS grid overlay" checkbox (P6) | no |
| 8 | VSP references (`comparisons`) | same (33) | "VSP references · n" / "AAVSO VSP reference candidates; not necessarily the selected ensemble." | never auto-checked (1735-1737) | field solved | `viewer.set_comparison_enabled`; forced off without unchecking the chip when 0 points (1738-1739, P22) | no |
| 9 | Selected stars (`targets`) | same (34) | "Selected stars" / "The target, selected comparison stars and check stars for this observation." | auto when the target set has a marker (1752); forced on by a table selection (2069-2070) | target projected (1752) | `viewer.set_target_enabled` | no |
| 10 | Labels | same (35) | "Labels" / "Show compact non-overlapping labels; hover a marker for its full identity." | forced **off** the first time (1763-1769) | any marker exists (1753-1762) | `viewer.set_marker_labels_enabled` | no |
| 11 | Gaia G limit | QSlider (98-111), caption "Gaia G limit" (89-97), value label "≤ 18.0" (112-118) | caption tooltip "Stellar display limit in the Gaia G passband. It does not filter galaxies or nebulae whose integrated magnitudes use different passbands." / slider tooltip "Faint-end Gaia G display limit. Move left to declutter; move right to reveal fainter Gaia stars already cached for this field." | raw 50..200 = 5.0..20.0 mag, step 0.1; max reset to `catalog.field_stars_mag_limit` (default 18.0, 318-320, 1435-1439); value `catalog.display_mag_limit` (default 18.0, 190, 321) | always | `valueChanged` -> `_on_catalogue_magnitude_changed` (557, 1441-1445) re-projects from cache; `sliderReleased` -> `_save_catalogue_magnitude` (558, 1447-1450) `config.set` + `config.save()` | `catalog.display_mag_limit` (only on mouse release: keyboard changes are not saved, P23) |
| 12 | Catalogues / depth… | QToolButton (120-127) | "Catalogues / depth…" / "Choose Gaia, VSX, SIMBAD, NASA and offline catalogue sources, query depth, cache folders and refresh behaviour." | | always | `configure_requested` -> `_open_field_catalogue` (556, 1427-1433): dialog M on the Catalogue tab, `exec()`; on `saved`: `engine.refetch_catalog` (`acquisition_engine.py:815`), `_schedule_catalog_project`, `_sync_catalogue_depth` (1435-1439) | `catalog.*` (dialog) |

Captions "Objects" / "Display" (`_section_label`, 131-139).

### 1.6 Viewer interaction owned by the page (`FitsViewer`, wired 576-578; behaviour 793-1310)

The viewer's own tools (pan, zoom, ROI, loupe, crosshair, rotation, stretch) are in the
viewer-tools spec. The page owns:

| # | Control | Qt type | Behaviour | Enabled when | Action -> effect | Persisted |
|---|---|---|---|---|---|---|
| 1 | Left click on the image | `star_clicked(x, y)` (`fits_viewer.py:867-881`, un-rotated display px) | `_on_star_clicked` (793-967): convert to green px (1286-1293); hit-test in this order, tolerance max(6, 14 x green_w / disp_w) green px, default 10 (969-983): (1) saved target, (2) VSX variable, (3) VSP comparison, (4) SIMBAD object, (5) Essential Messier/NGC/IC, (6) exoplanet host, (7) Gaia star, (8) earlier point identity, (9) otherwise measure the star (`measure_star_at`) and, if a WCS exists, start a point identification (1036-1082); without WCS show a manual-measurement card (966-967); no star -> clear card (960-965) | a frame exists (797) | star card J + selection ring (aperture radius `engine.photometry_geometry()`, `acquisition_engine.py:1222-1233`) | no |
| 2 | Hover on a marker | viewer tooltip (strings built by the page) | 8 formats, see "Displayed data" | markers shown | tooltip | no |

Displayed data:
- Selection ring: centre dot + aperture ring, no label (993-995, 1020-1023, 1054-1057);
  for a measured field star the ring follows small drift every frame
  (`_remeasure_selection`, 1230-1246, `TRACK_SNAP_SEARCH`).
- Marker tooltips: VSX "Variable star\n{name}\n…" (1507 + 1188-1204); Gaia / SIMBAD star
  (1905-1928); SIMBAD object "SIMBAD identified object\n…" (1940-1949); point identity
  "Point catalogue identification\n…WCS match offset {x}″" (1951-1961); Essential
  "Argos Essential Catalogue\n…" (1930-1938); exoplanet host "Prepared exoplanet host\n…
  Source: local NASA Exoplanet Archive cache" (1963-1975); VSP "VSP reference candidate\n
  AUID …" (1984-1993); target set "{Photometry target | Selected reference star | Check
  star}\n{name}\nAUID …" (1995-2008).

### 1.7 Star info card (`StarInfoCard`, `star_info_card.py:21`, child of the viewer, created `imaging_page.py:242`)

- Purpose: show what was clicked and assign photometric roles. Starts bottom-left, 12 px
  inset (135-141); min 240 x 120 (37); body is plain monospace text (67-74). Tooltip on
  the card: "Drag the title to move this panel. Drag its lower-right corner to resize it."

| # | Control | Qt type | Label / tooltip (exact) | Enabled / visible | Action -> effect | Persisted |
|---|---|---|---|---|---|---|
| 1 | × | QPushButton 18 x 18 (59-64) | "×" / "Dismiss" | always | hide + `cleared` -> `_on_card_cleared` (561, 2042-2046): clear ring, selection, pending star | no |
| 2 | Target | QPushButton (79-97) | "Target" / "Variable star whose brightness you are measuring" | `roles_enabled` (126-128): catalogue picks always; manual measurement only with a WCS (1031-1032); disabled while identifying | `role_selected("target")` -> `_on_card_role` (559, 2021-2030): `TargetStar(role, **pending)`, `camera_dock.set_object_name_if_empty`, `engine.set_target_role` (`acquisition_engine.py:1024-1031`: set role, auto-select VSP comparisons for a target, save `targets/<object>.json`, reset tracker, `targets_changed`) | `sessions/targets/<object>.json` |
| 3 | Comparison star | QPushButton | "Comparison star" / "Reference star used to calibrate differential magnitudes" | same | same with role `comparison` | same |
| 4 | Check star | QPushButton | "Check star" / "Expected-constant star measured against the comparison ensemble to verify it" | same | same with role `check` | same |
| 5 | Remove | QPushButton (100-104) | "Remove" / "Drop this star from the target set" | visible only if the clicked star is already saved (996-1005, 129) | `_on_card_remove` (560, 2032-2040): `engine.remove_target(key)`, hide, clear | same |
| 6 | Dismiss | QPushButton (105-109) | "Dismiss" / "Close this card (keeps the target set as is)" | always | emits `cleared` only: the ring clears but **the card stays visible** (verified offscreen, P19) | no |
| 7 | Title drag | QLabel event filter (52-54, 147-161) | "Drag to move this panel" | always | move, clamped inside the viewer | no (session only) |
| 8 | Corner resize | mouse in the 16 px lower-right grip (163-180, 225-227) | | always | resize, clamped | no |

Card titles (exact): "Target · {name}" (807), "Variable · {name}" (825), "VSP reference ·
{auid}" (843), "Identified object · {name}" (862), "Deep-sky object · {name}" (880),
"Exoplanet host · {host}" (898), "Identified star · {name}" or "Gaia DR3 · {id}" (926-930),
"Identified star|object · {name}" (1176), "Manual image measurement" (1024),
"Identifying catalogue source…" (1059), "No catalogue match" (1099),
"Point identification unavailable" (1143). Catalogue picks end with "Photometry aperture
{r:.1f} green px" (1002).

Manual-measurement body (`_format_star_text`, 1257-1284): "Selected star   FWHM {x}″   HFD
{x}″   ecc {x}   SNR {x}   peak {n} ADU", then "field  RA {h}h  Dec {d}°   ·   {s}″/px"
or "scale  {s}″/px   (mount not connected)", then either "star   RA …  Dec …" +
"catalogue identifier   no loaded marker" (solved) or "catalogue identifier   identify the
field first". Prefix line "No loaded catalogue marker. Gaia/SIMBAD point identification is
available." (1027) or a catalogue note (1094, 1138).

Point identification (1036-1155): one at a time; Gaia + SIMBAD cone of 10″ off the UI
thread (`PointIdentityWorker`, `object_resolver_worker.py:66-106`); flags
`catalog.field_stars_enabled`, `catalog.named_objects_enabled`,
`catalog.named_objects_allow_network` (1066-1076); results within 1″ of an earlier one are
merged (1107-1119) and kept as markers until the field changes.

### 1.8 Context bar (`_build_context_bar`, `imaging_page.py:412-437`, under the image)

No controls. Displayed data:

| Readout | Text | Source / refresh |
|---|---|---|
| "Frame" key + file | "No FITS frame loaded" (422), "Opened  {name}" (1336), "Saved  {name}" (2565); tooltip "Most recently opened or saved FITS image" | Open FITS and sequence `frame_saved` only; single-shot saves never update it (P7) |
| Sequence | "Sequence  {done}/{total}  ·  ETA {m}m {ss}s" (2559-2561); cleared when total ≤ 0 or the run stops (2550, 2555-2557); tooltip "Progress of the active acquisition sequence" | `engine.sequence_progress` |

### 1.9 Open FITS flow (`_on_open_fits`, `imaging_page.py:1312-1339`; `open_fits` 1341-1343)

| # | Control | Qt type | Label | Default | Action -> effect |
|---|---|---|---|---|---|
| 1 | File dialog | `QFileDialog.getOpenFileName` (1320-1322) | title "Open FITS"; filters "FITS (*.fits *.fit *.fts)", "All files (*)" | start dir `sessions_path` (else home) | cancel -> nothing; else read, ingest (1.2 #1) |

Messages: ERROR "Open FITS: {exc}" (1332), including "expected a single 2-D image HDU"
(1330); OK "Loaded {name} — solve to enable catalog & photometry." (1337-1339).
Problems: P8 (uint16 cast), P9 (stale WCS and stale JD after open).

### 1.10 Field identification workflow (Shell Field menu + page, engine, controller)

End to end:
1. User: Field ▸ Identify field (`shell.py:244-247`) -> `engine.solve_now`
   (`acquisition_engine.py:767-785`): refuses with WARN "No frame to solve yet — start a
   preview first." or "Preview is at half quality — set Preview to Full res to
   plate-solve."; else `AstrometryController.solve_now` (`astrometry_controller.py:105-119`,
   returns False silently if a solve runs) -> `SolveWorker` on the green plane with mount
   hint; CMD "Plate-solving current frame… (hint RA {h}h Dec {d}°)" or "… (blind — no
   mount)".
2. Auto mode: Field ▸ Keep field identified automatically (checkable, `shell.py:248-258`)
   -> `set_auto`; per processed full-res frame `engine.on_processed` (`imaging_page.py:774`,
   `acquisition_engine.py:750-765`) re-solves when no WCS, every
   `astrometry.live_resolve_s` (20 s) or after `astrometry.live_resolve_arcmin` (2′) of
   mount motion (`astrometry_controller.py:135-154`).
3. Result: failure -> ERROR "Solve: {msg}" (`acquisition_engine.py:789`), last WCS kept.
   Success -> `_on_astrometry_solved` (`imaging_page.py:1378-1403`): discard if the frame
   geometry changed meanwhile (INFO "Solve finished for a different frame geometry —
   discarded."); else OK "Solved — RA {h}h  Dec {d}°  {s}″/px  rot {r}°  Δtarget {t}′"
   (`astrometry_controller.py:226-238`), enable "Center selected target" (1395), draw grid
   (1396), auto-show the grid chip (1397), sync the dock grid checkbox (1398-1399),
   re-measure the selection, fetch catalogues once per field (1401, 1.11), re-project
   (1402), and measure one photometry point unless a sequence owns the camera (1403,
   `acquisition_engine.py:791-794`).
4. Invalidation (`_clear_astrometry`, 2440-2498): on an Argos GoTo (`session.slewed`, 524),
   on a frame-geometry change (763-771, INFO "Frame geometry changed — WCS overlays cleared
   (solve again at full res)."), on mount motion ≥ 2′ outside Argos (2604-2610, INFO "Mount
   pointing changed outside Argos — stale astrometry overlays cleared. Plate-solve the
   current full-resolution frame."). Clears WCS + catalogue cache + tracker, every
   projection and marker layer, disables all chips and zeroes counts, re-arms auto-show.
   It does **not** clear the star card or the selection ring (P24).
5. Sequences (`_on_sequence_running`, 2537-2550): at start, if a WCS exists and auto is
   off, emits `auto_solve_armed(True)` (INFO "Sequence: auto-solve armed for the run.");
   at stop restores off when it was off (P13: never armed when no WCS exists at start).

Shell entry points (S):

| # | Control | Qt type | Label / tooltip | Shortcut | Action |
|---|---|---|---|---|---|
| 1 | File ▸ Open FITS image… | QAction (`shell.py:192-196`) | tooltip "Open a saved FITS image in Capture; then use Field → Identify field." | Ctrl+O | select Observe, `open_fits` (1.9) |
| 2 | Field ▸ Identify field | QAction (244-247) | "Find coordinates and scale for the current image (ASTAP)" | none | `engine.solve_now` |
| 3 | Field ▸ Keep field identified automatically | checkable QAction (248-258) | "Refresh field coordinates when needed so the grid and markers follow the field.\nIt is enabled automatically during a sequence." | none | `astrometry.set_auto` |
| 4 | Field ▸ Configure field identification… | QAction (260-262) | | none | dialog M, Astrometry tab, `saved` -> `refetch_catalog` only (463-472) |
| 5 | Field ▸ Configure catalogues… | QAction (263-265) | | none | dialog M, Catalogue tab, same (P18) |
| 6 | Photometry ▸ Photometry setup… | QAction (270-277) | "Choose a variable-star target and review the comparison-star ensemble in this field" | none | `open_photometry(select_variable=True)` (1.13) |
| 7 | Photometry ▸ Live curves & diagnostics… | QAction (278-281) | "Open live differential light curves, image quality and selected stars" | none | `open_photometry()` |
| 8 | Photometry ▸ Re-run subs… | QAction (282-285) | "Re-run differential photometry over a folder of saved subs" | none | `rerun_subs` (1.14) |
| 9 | View ▸ Reset Window Layout | QAction (237-239) | | none | clears the Shell, Sequencer and Review layouts on next launch, **not** `ui.imaging.layout` (P5) |

### 1.11 Catalogue fetch and overlay projection

- Fetch (`maybe_fetch_catalog`, `acquisition_engine.py:834-901`): once per field (skips
  while the centre moved less than the field radius); VSX at the solved centre, VSP around
  the first target; budgets from `catalog.identification_max_objects` (400, split 70/30
  Gaia/SIMBAD); keys `catalog.mag_limit` (15), `catalog.max_results` (250),
  `catalog.include_suspected`, `catalog.field_stars_enabled`,
  `catalog.field_stars_mag_limit` (18), `catalog.named_objects_enabled`,
  `catalog.named_objects_allow_network`, `catalog.exoplanet_hosts_enabled`,
  `catalog.exoplanet_hosts_allow_network`. `CatalogWorker` is not cancellable.
- Result (`_on_catalog`, 904-965): WARN "Catalog: {error}" or per-warning; OK "Catalog: {n}
  variable(s) in field", "… Gaia DR3 source(s) in field", "… named SIMBAD object(s) in
  field", "… confirmed exoplanet host(s) in field", "… calibrated VSP comparison star(s)
  available"; INFO budget-reached notes (924-936); WARN "Catalog: no calibrated VSP
  comparison stars returned for this field. Refresh the field catalogue or choose
  calibrated comparisons manually."; back-fills comparisons for an existing target.
- Projection (`_project_catalog`, `imaging_page.py:1483-1740`, coalesced 75 ms; triggers:
  solve, `catalog_ready` 540, `apertures_tracked` 546, each processed frame with a WCS
  775-778, magnitude slider, dialog save, point identity): through `engine.tracked_wcs()`
  (rotation + translation in alt-az, translation only in EQ). Rules: VSX all in-frame,
  filtered to the Variables table's visible rows (1771-1780); Gaia G ≤ display limit and,
  if `catalog.field_stars_detected_only`, within 4 px of a detected source (1528-1538,
  1977-1982); SIMBAD names cross-matched to Gaia within 3″ (1786-1822) so one source has
  one marker; generic survey ids not used as labels (1883-1902); SIMBAD categories
  galaxy / nebula / cluster / star / other (1853-1881); Essential catalogue objects within
  the field radius if `catalog.show_essential_objects` (1620-1626); cached exoplanet hosts
  if `catalog.show_cached_exoplanets` (1627-1630); markers within 8 px de-duplicated
  (1824-1841); VSP candidates only where a source is detected (1684-1697); target-set
  markers with role (1742-1751). Counts and availability per chip (1720-1737).

### 1.12 Target-set workflow (engine-owned set, page-owned views)

| Trigger | Handler | Effect | Message |
|---|---|---|---|
| Card role button | `_on_card_role` 2021-2030 | object name filled if empty, `set_target_role` | OK "{Role}: {name}" |
| Card Remove | `_on_card_remove` 2032-2040 | `remove_target` | OK "Removed from target set: {name}" |
| Variables table "target" | `_on_variable_target_requested` 2224-2242 | same as card Target with source `vsx` | OK "Target: {name}" |
| Catalogue lookup of a `V*` object | `set_catalogue_target` 2658-2676 -> `_set_photometry_target` 2683-2706 | target from the resolver result (source `variable_catalogue`) | INFO "Photometry target saved — solve a full-resolution frame to draw its marker and select field comparison stars." (no WCS) |
| Plan section science source | `set_science_source` 2708-2719 (`shell.py:174`) | target with source `exoplanet_host` / `variable_catalogue` | OK "{Exoplanet host\|Variable star} selected for photometry: {name}. Identify the field, then review the comparison ensemble." |
| Object name edit | `camera_dock.object_changed` -> `engine.on_object_changed` (588, `acquisition_engine.py:1010-1022`) | reload the set keyed by the new name, clear live curves, reset tracker | |
| Any change | `_on_targets_changed` 2014-2019 | re-project markers, refresh Targets / Variables tables | |

### 1.13 Live photometry wiring (`PhotometryWindow`, `photometry_window.py:200`; light-curve dock)

Window contents belong to the photometry spec. The page:
- creates it once (`_open_photometry`, 2091-2145), title "Field photometry — {object}",
  export meta `observer.obscode` (default "XXX") and `photometry.default_band` ("TG")
  (2095-2099); tabs "Variable stars", "Light curve", "Metrics", "Targets", "Comparison
  stars", "Aperture · references" (`photometry_window.py:230-235`); `select_variable`
  shows the Variable stars tab (2142-2143);
- wires: targets / comparisons `remove_requested` -> `engine.remove_target` (2100-2101);
  `star_selected` -> `_on_photometry_star_selected` (2048-2077: ring + label "{Role} ·
  {name}" on the image, forces Selected stars on; WARN "Selected star is outside the solved
  image."); variables `target_requested` (2106-2108); `visible_rows_changed` -> VSX
  overlay filter (2109-2111); comparisons `refresh_requested` -> `engine.refetch_catalog`
  (2112-2114); `recommend_requested` -> `_recommend_comparison_stars` (2185-2196: OK
  "Photometry: replaced the VSP ensemble with {n} pilot-qualified star(s)." / WARN
  "Photometry: no pilot-qualified comparison found — solve a full-resolution frame
  first."); `auto_count_changed` -> `_on_auto_comparison_count_changed` (2167-2183,
  `photometry.auto_comparisons`, OK / INFO texts); setup `setting_changed` ->
  `_on_photometry_setting_changed` (2152-2165: `config.set(key)`, redraw the ring, INFO
  "Photometry measurement geometry updated.");
- feeds: every `photometry_point` to the dock and, when visible, the window (2390-2406);
  `curves_changed` re-renders both (2376-2388); `comparison_quality_updated` (2408-2412);
  metrics samples (elapsed s, sky, FWHM, HFD, stars, airmass from mount altitude) per
  processed frame while visible (2419-2433) and CCD temperature per measurement (2369-2374,
  2435-2438).
- Light-curve dock "Differential photometry" (`LightCurvePanel`): `set_curves` /
  `add_point` (2379, 2396-2403); hidden by default.

### 1.14 Batch re-run (`_on_rerun_subs`, `imaging_page.py:2248-2367`; `PhotometryBatchWorker`)

| # | Control | Qt type | Text (exact) | When | Effect |
|---|---|---|---|---|---|
| 1 | "Solve first" box | `QMessageBox.information` (2262-2264) | "Plate-solve the live frame before a batch re-run." | no WCS | abort |
| 2 | "No targets" box | same (2268) | "Assign at least one target star first." | no target | abort |
| 3 | "No comparison stars" box | same (2273-2282) | "The target set has no comparison stars, so differential\nphotometry cannot produce magnitudes.\n\nSolve the field and wait for the catalog (comps auto-select\nonce it arrives), or click a comparison marker on the image\nand assign it the Comp role." | no comparison | abort |
| 4 | Folder dialog | `QFileDialog.getExistingDirectory` (2283-2286) | "Folder of saved subs" | start `last_sequence_dir` or `sessions_path` | cancel -> abort |
| 5 | "No frames" box | information (2290-2292) | "No FITS files in {folder}" | no `*.fits` in the folder nor recursively | abort |
| 6 | Progress dialog | `QProgressDialog` (2308-2317) | title "Batch photometry", label "Re-running photometry…", button "Cancel", 0..N | running | Cancel -> `worker.cancel()` (stops at the next frame boundary, `photometry_batch_worker.py:92-94`) |
| 7 | "Batch failed" box | `QMessageBox.warning` (2344) | `result.error` | crash | |

Flow: only one batch at a time (2255-2256); frames `*.fits` sorted by mtime (2287-2289);
`PhotometryParams.from_config` with e-/ADU from `camera.egain_table` or the sensor model
(2320-2335); site `site.latitude/longitude/elevation`; diagnostics `diagnostics.enabled`;
output `sessions_path.parent / "targets"` (2299, P10). End (`_on_batch_done`, 2337-2367):
WARN "Batch photometry: no points measured — see the per-frame notes in
targets/*_diagnostics.jsonl."; OK "Batch photometry: {n} frame(s), {m} target(s)."; INFO
"Apertures tracked the field: {r:+.2f}° rotation, {s:.1f} px drift vs the reference
solve."; curves folded into the store (`adopt_curves`) and the photometry window opened.

### 1.15 Catalogue settings dialog (M) as opened from the page

`AstrometrySettingsDialog(config, self, section=SECTION_CATALOG)`
(`astrometry_settings.py:50-86`), title "Field identification & catalogue settings",
Save / Cancel. Keys written (363-395): `catalog.mag_limit`, `catalog.max_results`,
`catalog.include_suspected`, `catalog.field_stars_enabled`,
`catalog.field_stars_mag_limit`, `catalog.identification_max_objects`,
`catalog.field_stars_max_results`, `catalog.field_stars_detected_only`,
`catalog.show_essential_objects`, `catalog.show_cached_exoplanets`,
`catalog.named_objects_enabled`, `catalog.named_objects_max_results`,
`catalog.named_objects_allow_network`, `catalog.exoplanet_hosts_enabled`,
`catalog.exoplanet_hosts_allow_network`. Controls inventoried by the settings spec.

### 1.16 Mount workflows owned by the page (Telescope dock wiring 593-605)

| Dock signal | Page handler | Effect | Messages |
|---|---|---|---|
| `goto_clicked(ra, dec)` | `_on_goto` 2612-2614 | `session.goto` (`device_session.py:573-583`): tracking on, slew, `slewed` -> `_clear_astrometry` | CMD "Slewing → RA … Dec …"; ERROR "Goto: …" |
| `object_lookup_requested(q)` | `_lookup_object` 2641-2651 | one `ObjectResolverWorker` at a time, dock busy | WARN "Catalogue lookup: {msg}" (2724) |
| resolver result | `set_catalogue_target` 2657-2676 | dock shows the result, Object name set (emits), `target_coordinates_changed`, `V*` -> photometry target | INFO "Catalogue target: {name} — RA {h:.5f}h Dec {d:+.5f}°" |
| `resolved_goto_clicked(ra, dec, label)` | `_goto_resolved_object` 2767-2773 | goto | WARN "Slew requested but mount not connected"; CMD "Catalogue slew {label} → RA … Dec …" |
| `target_suggestion_accepted(result)` | `set_catalogue_target` | as above | |
| `sync_to_current_clicked` | `session.sync_current` (597) | syncs the mount to **its own** last position (`device_session.py:585-593`, P14) | CMD "Sync at RA … Dec …" |
| `center_target_clicked` | `_center_selected_target` 2616-2639 | needs WCS; target = first `target` role else the last GoTo; solved centre of the reference WCS; fills the GoTo fields; `center_target_from_solution` (`device_session.py:595-626`: sync to the solved centre, slew to the target, `slewed`) | WARN "Center target: plate-solve the current frame first." / "Center target: select a target or issue a GoTo first."; INFO "Centering {label} from the current plate solution…"; CMD "Center: synced …", "Center: slewing to target …" |
| `tracking_toggled`, `tracking_rate_changed`, `abort_clicked`, `park_clicked` | session direct (599-602) | | CMD / ERROR from the session |
| `manual_control_requested` | `_open_jog` 2790-2798 | dialog P (cached once) | |
| `jog_start(axis, rate)` / `jog_stop(axis)` | `session.jog` / `_on_jog_stop` 2587-2588 | MoveAxis off-thread (`device_session.py:665-675`) | |
| Stellarium GoTo (`shell.py:346-353`) | `goto_target` 2775-2788 + `suggest_target_from_coordinates` 2733-2765 | fills GoTo fields, slews; nearby-name worker (network only if `stellarium.online_target_lookup`) | WARN "Goto requested but mount not connected"; CMD "{Stellarium goto\|Goto} → RA … Dec …"; INFO "Stellarium target-name suggestion: {n} nearby catalogue candidate(s)."; WARN "Target-name suggestion: {msg}" |
| `session.mount_position` | `_on_mount_position` 2590-2610 | dock readouts; stale-WCS guard | see 1.10 step 4 |

### 1.17 Manual control dialog (`ManualControlDialog`, `manual_control_dialog.py:66`, tool window, non-modal, stay-on-top, fixed 280 x 320, title "Manual Control")

| # | Control | Qt type | Label / tooltip | Default / range | Shortcut | Action |
|---|---|---|---|---|---|---|
| 1 | Speed | QComboBox (103-113), caption "Speed" | Slow 0.5, Normal 2.0, Fast 5.0 deg/s | Normal | | sets the rate |
| 2 | North | hold QPushButton (124-135) | "↑" / "North" | | Up arrow when focused (184-197) | press `move_axis(1, +rate)`, release `stop_axis` (157-178), synchronous on the UI thread |
| 3 | South | same | "↓" / "South" | | Down | axis 1, −rate |
| 4 | West | same | "←" / "West" | | Left | axis 0, −rate |
| 5 | East | same | "→" / "East" | | Right | axis 0, +rate |
| 6 | Stop | QPushButton (137-141) | "■" / "Stop" | | | stop the active axis |
| 7 | Arrow keys | key events (184-205) | | | ↑ ↓ ← → (auto-repeat ignored) | start on press, stop on release |

Labels: "Hold to move · Release to stop" (115), "Arrow keys work when this window is
focused" (145). Messages: ERROR "Move failed: {exc}", WARN "Stop failed: {exc}". Closing
stops motion (209-211).

### 1.18 Camera, filter and focuser workflows owned by the page

| Dock signal | Page handler | Effect | Messages |
|---|---|---|---|
| `take_shot_clicked` | `engine.take_shot` (581) | `acquisition_engine.py:317-330`: tag the next live frame, or acquire SINGLE; save full-res FITS off-thread (1510-1595) | WARN "Camera not connected."; CMD "Take shot — saving next frame…"; OK "Saved {name}"; ERROR "FITS save failed: …" |
| `live_start_requested` / `live_stop_requested` | `engine.start_live` / `stop_live` (582-583) | camera ownership LIVE | CMD "Live preview started."; INFO "Live preview stopped."; ERROR "Preview: …" |
| `offset_changed(v)` | `_on_camera_offset` 2504-2517 | refused while a sequence / autofocus owns the camera (re-syncs the spin box), else `set_camera_offset` | WARN "{Sequence\|Autofocus} running — it owns the camera. Stop it first."; CMD "Offset → {v}" |
| `binning_changed(v)` | `_on_camera_binning` 2519-2530 | same guard, `set_camera_binning` | same; CMD "Binning → {v}×{v}" |
| `filter_selected(name)` | `_on_camera_dock_filter` 690-702 -> `_on_filter_move` 684-688 | moves the wheel (off-thread) | WARN "Filter wheel not connected — '{name}' is metadata only."; WARN "No wheel position matches filter '{name}'."; CMD "Filter → {name}" |
| `object_changed` | `engine.on_object_changed` (588) | 1.12 | |
| `step_requested(delta)` / `move_to_requested(pos)` | 2804-2811 | focuser move, dock position | CMD "Focuser step …", "Focuser move → …" |
| `halt_requested` | `_on_focuser_halt` 2813-2817 | stops autofocus too, then halt | CMD "Focuser halted" |
| `autofocus_requested` | `engine.start_autofocus` (610) | AF sweep (camera AUTOFOCUS) | WARN "Autofocus needs focuser + camera connected"; CMD "Autofocus started…" |
| AF progress | `_on_af_step` 2832-2839, `_on_af_done` 2841-2848, `_on_autofocus_state` 2827-2830 | dock position, status "Step {s}/{t}  HFD={h}", V-curve points, best | INFO "AF {s}/{t}  pos={p}  HFD={h}"; OK "Autofocus complete — best pos={p}  HFD={h}" |
| Session state | `_on_session_device_state` 644-658, `_on_camera_capabilities` 660-669, `_on_filterwheel_state` 671-678, `_on_focuser_state` 680-682, `_on_filter_moved` 704-708, temperatures 522-523 | enable / disable docks, driver limits, filter names | |
| Camera ownership | `_on_camera_state` 630-638 | status action text, Live toggle, sequence lock of the capture form | |

### 1.19 Frame pipeline (`_on_frame` 2578-2581 -> `_show_raw` 729-732 -> `PreviewProcessor` -> `_on_processed` 734-780)

Per processed frame (latest-wins): reset a selection if the green geometry changed
(737-742); HFD to the Acquisition dock and the status bar (745, 748); HFD-history and
statistics docks (746-747); histogram (751); viewer geometry + image (752-753); detected
star list for overlay gating (754); re-measure the selection (756); metrics samples
(757); WCS geometry guard (763-771); `engine.on_processed` (auto-solve, 774); re-project
when solved (775-778); refresh the photometry setup when its window is visible (779-780).
Display-only page handlers: saturation threshold `camera.full_well_adu` (default 60000,
721-723); rotation persisted as `ui.display.rotation` (default "auto", 572-575, 725-727);
star radius for HFD/FWHM 2..30 px pushed to the processor (786-791).

### 1.20 Referenced docks (inventoried elsewhere; the page only wires them)

| Dock | Spec owner | Page wiring lines |
|---|---|---|
| Acquisition (`CameraDock`) | hardware docks | 217, 522, 581-588, 634-638, 651-653, 664-669, 677-678, 687, 707-708, 745 |
| Telescope (`MountDock`) | hardware docks | 593-605, 1395, 2443, 2592-2599, 2635, 2645, 2660, 2723, 2727, 2739, 2749, 2758, 2785 |
| Focusing (`FocuserDock`) | hardware docks | 523, 608-611, 657, 682, 2807-2845 |
| Image display (`HistogramDock`) | viewer tools | 563-575, 577-578, 751, 1398-1399, 2445-2446 |
| Image statistics, Focus diagnostics | viewer tools | 746-747 |
| Activity log (`LogPanel`) | this spec (content: "Clear" button `log_panel.py:42-58`, unbounded colour-coded HTML lines "HH:MM:SS [LEVEL] message") | 614 |
| Differential photometry (`LightCurvePanel`) | photometry | 2379, 2396-2403 |

### 1.21 Dead or unreachable paths

| What | Where | Evidence |
|---|---|---|
| Palette combo on Observe | `image_toolbar.py:79-94` | `palette_changed` connected only in `analysis_window.py:281` |
| `load_fits`, `open_analysis` (floating analysis window from the page) | 1345-1368 | no caller in `argos/` (Review opens its own `AnalysisWindow`, `analyze_page.py:723, 776`) |
| `request_autofocus`, `nudge_focuser` ("Focus screen" API) | 2819-2825 | no caller in `argos/` or `tests/` |
| `autofocus_step`, `autofocus_best` upward signals | 142, 144, 2838, 2846 | not connected by the Shell |
| `_on_filter_move` as a separate entry | 684-688 | single caller 702 |
| Module / method docstrings describing a Sequence dock, a Filter dock and a stats bar | 3-16, 444-450 | those no longer exist |

### 1.22 Problems found (consolidated)

| Id | Problem | Where |
|---|---|---|
| P1 | Palette combo is a dead control on Observe. | `image_toolbar.py:79-94`, `imaging_page.py:552-553` |
| P2 | The light-curve dock is meant to be tabbed with the Log (comment) but the `hidden` loop re-adds it to the right area; verified offscreen (`dockWidgetArea` = Right). | `imaging_page.py:451, 472-474, 479-480` |
| P3 | Panel chips are `toggleViewAction`s: a dock tabbed behind another counts as visible, so its chip reads "on" and a click hides it instead of raising it. | 355, 466-468 |
| P4 | Two identical reset entries ("Reset layout", "Restore default layout"). | 388, 396 |
| P5 | View ▸ Reset Window Layout (deferred, next launch) ignores `ui.imaging.layout`, unlike the page's live reset. | `shell.py:452-457` |
| P6 | Grid toggle duplicated (overlay chip and Image display "WCS grid overlay"), synchronised only at solve time. | `overlay_bar.py:32`, `histogram_dock.py:152-156`, `imaging_page.py:569, 1398-1399, 1411` |
| P7 | Frame context shows only opened files and sequence saves; Take-shot saves never appear; "Opened X" stays while live frames replace the image. | 422-428, 1336, 2565; `acquisition_engine.py:1591` |
| P8 | Open FITS casts to `uint16` without scaling: Siril float [0, 1] frames become ~0, negative integers wrap (the server's `open-fits` handles both). | 1335; `protocol.md` "Opening FITS files" |
| P9 | Opening a FITS keeps the previous WCS when the geometry matches: old-field overlays and targets are drawn on the new image, and a solve-time photometry point is stamped with the previous frame's mid-exposure time or "now" (the file's DATE-OBS is ignored). | 1312-1339; `acquisition_engine.py:515-526, 1357` |
| P10 | Batch output in `sessions_path.parent/targets` while the live path uses `sessions_path/targets` (intent unclear). | 2299; `acquisition_engine.py:978, 1269` |
| P11 | Batch preconditions surface as modal boxes after the click instead of a disabled action with a reason. | 2260-2282 |
| P12 | Batch takes every `*.fits` (recursive fallback) sorted by mtime, with no frame-type or object filter; `.fit` / `.fts` files, accepted by Open FITS (1321), are ignored. | 2287-2289 |
| P13 | Auto-solve is armed for a sequence only if a WCS already exists, so a run started unsolved measures no photometry until a manual solve. | 2543-2546 |
| P14 | "Sync" syncs the mount to its own reported position (no-op for the pointing model). | `device_session.py:585-593`, wired 597 |
| P15 | The jog dialog caches the first `Telescope` handle (stale after reconnect) and calls MoveAxis on the UI thread, the pattern `session.jog` was written to avoid; two jog UIs with two code paths. | 2790-2798; `manual_control_dialog.py:157-178`; `device_session.py:665-675` |
| P16 | Mount commands are synchronous Alpaca HTTP calls on the UI thread. | `device_session.py:573-663` |
| P17 | Centring uses the reference WCS, not the tracked one (drift since the solve ignored). Impact unverified. | 2618, 2634 |
| P18 | The catalogue dialog opened from the Field menu only refetches; from the overlay bar it also re-projects and resyncs the G-limit range. | `shell.py:470-472` vs `imaging_page.py:1429-1433` |
| P19 | "Dismiss" leaves the star card visible (only × hides it); role buttons then do nothing because the pending star is cleared. Verified offscreen. | `star_info_card.py:105-108`, `imaging_page.py:2042-2046` |
| P20 | After a role is assigned the card is not refreshed (no Remove button until the next click). | 2021-2030 |
| P21 | A click during a running point identification is ignored with an INFO log only. | 1038-1042 |
| P22 | "VSP references" chip can stay checked while its layer is forced off. | 1738-1739 |
| P23 | G-limit is saved only on mouse release; keyboard changes are applied but not saved. | `overlay_bar.py:107-110` |
| P24 | A slew clears the WCS and markers but leaves the star card and the selection ring of the old field. | 2440-2498 |
| P25 | Activity log is unbounded (one HTML line per event all night). | `log_panel.py:80` |
| P26 | Sequence progress shown twice (context bar and Shell status strip). | 2552-2561; `shell.py:313` |
| P27 | Dead code and stale docstrings (1.21). | |

## 2. Web redesign

Legend for wireframes: `[id]` = an icon-only button using that icon id, `[id Label]` =
icon + label, `(…)` = text button, `‹…›` = segmented control, `[x]`/`[ ]` = toggle on/off.
Glyphs in wireframes are placeholders, never UI text (BRAND 4.3: no Unicode pictographs).

### 2.1 Placement in the new information architecture

What the web Observe screen already has (`web/src/lib/imaging/*`, `StatusBar.svelte`) and
what this page still needs:

| Qt capability (page-owned) | Web today | Missing |
|---|---|---|
| Open a FITS frame (toolbar, Ctrl+O) | `client.openFits` exists (`api/client.ts:195`), **no UI** | toolbar button, file picker, Ctrl+O, empty-state CTA |
| Preview view (Colour / Raw / R / G / B) | mono mosaic only (README "Known limits") | view selector (client-side debayer from `sensor.bayer`) |
| Palette | none | Neutral / Negative / Fire / Ice in the display card (Night Red rules) |
| Panel strip, Panels ▾, Arrange ▾, Reset | rail toggle `P`, collapsible cards (persisted) | Panels popover (cards + drawer tabs), Reset layout |
| Overlay layers + counts + G limit + catalogue settings | none | Field toolbar group, Catalogue layers popover, marker layers on the viewer's SVG overlay |
| Identify field, auto-identify | none (no API) | Field group, HUD field chip, API |
| Click-to-identify, star card, roles, point identification | none | star card, selection ring, API |
| Target set, live photometry, light-curve dock, photometry window | none | Photometry rail card, drawer "Light curve" tab, side sheet (photometry spec) |
| Batch re-run | none | Photometry card action, folder picker, inline progress |
| Context bar (file, sequence) | status bar shows frame #, size, exposure | file name, sequence progress, HFD |
| Activity log | drawer with Clear / Close, unseen-problem badge | OK and CMD levels, line cap |
| Focus / statistics / HFD history docks | none | drawer tabs (viewer-tools / hardware specs own content) |
| Centre target, catalogue lookup, Stellarium suggestion, jog dialog | Mount card: position, tracking, park, GoTo, abort | hardware spec; APIs listed in 2.5 |

Placement of every Qt element:

| Qt element | Section -> screen -> region | Justification |
|---|---|---|
| A ImagingPage | Observe -> Observe screen | owner IA |
| B Open image | Observe -> toolbar, new "Source" group left of capture | opening a frame feeds the same pipeline as a capture |
| B Preview view, Palette | Observe -> rail card "Display" (existing "Display stretch" card, renamed) | display-only choices, next to rotation and stretch which already live there; keeps the toolbar for actions |
| B "Preview only · FITS unchanged" | Observe -> tooltip of the Display card title | BRAND 11.1: no dead bands |
| C/D/E/F/G panel strip, menus, docks | Observe -> toolbar `arrange` popover "Panels" + collapsible rail cards + bottom drawer tabs | fixed, predictable layout; image keeps the space (BRAND 11.1) |
| H overlay chips, G limit | Observe -> toolbar "Field" group + "Catalogue layers" popover | frequent toggles icon-only; counts and depth in the popover |
| H "Catalogues / depth…" | Settings -> Catalogues section, opened as a modal sheet from the popover | one form for both entry points (fixes P18) |
| I click / hover | Observe -> viewer SVG overlay | |
| J star card | Observe -> on-image card, bottom-left of the image rectangle, draggable | same as Qt; does not hide the clicked star |
| K context bar | global status bar (Frame item gains the file name; Sequence and HFD items) | visible on every section, like the Qt capture strip; removes P26 duplication |
| L file dialog | modal dialog "Open FITS image" (custom, server-side listing) | Night Red forbids grey OS dialogs (BRAND 4.3); Tauri native dialog allowed in the other themes |
| M catalogue dialog | Settings -> Catalogues, modal sheet from Observe | settings spec owns the form |
| N photometry window | Observe -> rail card "Photometry" + side sheet "Field photometry" (non-modal, 580 px, over the rail) + drawer tab "Light curve" | live work stays next to the image; the photometry spec owns contents |
| O batch re-run | Observe -> Photometry card action; folder picker modal; inline progress in the card + status bar | it needs the current field solution and target set, which live on Observe (open question Q2) |
| P jog dialog | Observe -> Mount card jog pad (hardware spec) | one jog path |
| Q marker tooltips | Observe -> viewer tooltip (tokens, mono) | |
| R analysis window | Review (review spec) | dead from this page |
| S Field menu | Observe toolbar Field group; "Configure field identification…" -> Settings -> Field identification | no menu bar in the web UI |
| S Photometry menu | Observe Photometry card | |
| S View ▸ Reset Window Layout | Observe Panels popover "Reset layout" (applies live) | fixes P5 |
| Activity log dock | existing log drawer, now the first drawer tab | |
| Light curve, HFD history, statistics docks | drawer tabs "Light curve", "Focus trend", "Statistics" | time series and tables want width, not rail height |
| Acquisition, Telescope, Focusing, Image display docks | rail cards Camera, Mount, Focuser, Display (hardware / viewer specs) | |

### 2.2 Control mapping

| Qt ref | Web control | Decision | Icon id | Display | Shortcut |
|---|---|---|---|---|---|
| 1.2 #1 Open image… | toolbar button "Open FITS image" | keep | `open-image` | icon | Ctrl+O (qt) |
| 1.2 #2 Preview | Display card ‹Colour · Raw · R · G · B›, tooltip keeps the Qt text | move | none (text segmented) | label | none |
| 1.2 #3 Palette | Display card ‹Neutral · Negative · Fire · Ice›; Fire and Ice disabled in Night Red with reason | move + fix P1 | none | label | none |
| 1.3 #1-#5 panel chips | Panels popover checkboxes (rail: Connection, Camera, Display, Photometry, Focuser, Mount) + card fold | merge (fixes P3: a card is either shown or not, no hidden tabs) | `arrange` (popover trigger) | text rows | none |
| 1.3 #6 Panels ▾ | same popover | merge | `arrange` | icon | none |
| 1.3 #7-#9 Statistics, Focus diagnostics, Activity log | Panels popover "Drawer" checkboxes; Log also via the status-bar Log button | merge | `statistics`, `focus-metrics`, `log` (16 px in rows) | text rows | none |
| 1.3 #10 Arrange ▾ | Panels popover | merge | `arrange` | icon | none |
| 1.3 #11 Restore default layout | Panels popover "Reset layout" | merge with #20 (P4) | `layout-reset` | icon+label | none |
| 1.3 #12-#19 Float / Dock x 8 | none in the browser | drop: a web page cannot detach panels to another monitor; revisit with Tauri multi-window (Q1) | (`panel-float` reserved) | | |
| 1.3 #20 Reset layout | Panels popover "Reset layout": restores card order / folds, drawer height and tab, rail width | keep | `layout-reset` | icon+label | none |
| 1.4 #1 dock drag | none | drop: fixed rail + drawer IA (BRAND 11.1); card order fixed | | | |
| 1.4 #2 double-click float | none | drop: as 1.3 #12 | | | |
| 1.4 #3 float button | none | drop: as 1.3 #12 | | | |
| 1.4 #4 close button | card fold chevron; Panels popover to remove a card | merge | `disclosure` | icon | none |
| 1.4 #5 dock tabs | drawer tab strip (Log, Light curve, Focus trend, Statistics) | keep (drawer only) | `log`, `light-curve`, `focus-metrics`, `statistics` | icon+label tabs | none |
| 1.4 #6 splitters | drawer height handle (160 px to 50 % of the centre); rail width 420-580 px handle | keep | | | none |
| 1.4 #7 dock context menu | Panels popover | merge | | | |
| 1.4 #8 dock scroll | rail scrolls as a whole (exists) | keep | | | |
| 1.5 #1 Stars | popover row toggle "Stars (Gaia DR3 + SIMBAD)" + count | move | `field-stars` | icon+label row | none |
| 1.5 #2 Variables | popover row "Variables (VSX)" + count | move | `variable-star` | icon+label row | none |
| 1.5 #3 Galaxies | popover row + count | move | `galaxy` | icon+label row | none |
| 1.5 #4 Nebulae + clusters | popover row + count | move | `nebula` | icon+label row | none |
| 1.5 #5 Exoplanets | popover row "Exoplanet hosts" + count | move | `exoplanet` | icon+label row | none |
| 1.5 #6 Other objects | popover row + count | move | `other-objects` | icon+label row | none |
| 1.5 #7 Coordinate grid | toolbar toggle "Coordinate grid"; the Display card's duplicate checkbox is removed (P6) | keep + merge | `sky-grid` | icon | G (proposed in inventory) |
| 1.5 #8 VSP references | popover row "VSP reference candidates" + count; toggle state always equals layer state (P22) | move + fix | `comparison-star` | icon+label row | none |
| 1.5 #9 Selected stars | toolbar toggle "Selected stars" | keep | `target-star` | icon | none |
| 1.5 #10 Labels | toolbar toggle "Labels" | keep | `labels` | icon | L (NEW proposal) |
| 1.5 #11 Gaia G limit | popover slider "Gaia G ≤ 16.4", live filter client-side, saved on change (debounced 500 ms, also from keyboard, fixes P23) | keep | none | label + value | none |
| 1.5 #12 Catalogues / depth… | popover footer link "Catalogue settings…" -> Settings Catalogues form in a modal sheet; Save refetches and re-projects | keep | `settings` (16 px) | text with icon | none |
| (popover trigger) | toolbar "Catalogue layers" popover button, toggled style while open, a dot when any layer is on | new trigger | `catalogue` | icon | O (NEW proposal) |
| 1.6 #1 left click | click on the image -> identify (API `field/identify`); drag still pans | keep | | | |
| 1.6 #2 marker hover | tooltip from tokens, mono, same text formats | keep | | | |
| 1.7 #1 × | card close button, also Escape | keep | `close` | icon | Escape (inventory proposal; also still aborts a slew) |
| 1.7 #2 Target | card button "Target" | keep | `target-star` | icon+label | none |
| 1.7 #3 Comparison star | card button "Comparison" | keep | `comparison-star` | icon+label | none |
| 1.7 #4 Check star | card button "Check" | keep | `check-star` | icon+label | none |
| 1.7 #5 Remove | card button "Remove", shown when saved; card refreshes after any role change (P20) | keep + fix | `remove` | icon+label | none |
| 1.7 #6 Dismiss | none | drop: duplicate of × and broken (P19) | | | |
| 1.7 #7 title drag | drag the card header, clamped to the image | keep | | | |
| 1.7 #8 corner resize | none: card sized to content, max 320 x 260 px, body scrolls | drop: content-fit card; the Qt grip compensated QLabel wrapping | | | |
| 1.8 Frame readout | status bar "Frame #128 · {file name}" with tooltip "Most recently opened or saved FITS image"; HUD source chip shows the file name | move | | label | |
| 1.8 Sequence readout | status bar "Sequence 12/120 · ETA 54m 10s" (only while running, click -> Plan) | move | | label | |
| 1.9 #1 file dialog | modal "Open FITS image": server listing, path field, Cancel / Open | keep | `open-image`, `browse` | text buttons | Enter / Escape |
| 1.10 S#1 File ▸ Open FITS | = 1.2 #1 | merge | `open-image` | icon | Ctrl+O |
| 1.10 S#2 Identify field | toolbar "Identify field" (tooltip "Find coordinates and scale for the current image (ASTAP)"), busy spinner while solving | keep | `plate-solve` | icon | S (proposed in inventory) |
| 1.10 S#3 Keep field identified automatically | toolbar toggle "Keep field identified automatically"; server arms it for sequences and shows it pressed | keep | `plate-solve-auto` | icon | none |
| 1.10 S#4 Configure field identification… | Settings -> Field identification (settings spec), reachable from Observe through a "Field identification settings…" row in the Catalogue layers popover footer | move | `settings` | text with icon | none |
| 1.10 S#5 Configure catalogues… | = 1.5 #12 | merge | `settings` | | |
| 1.10 S#6 Photometry setup… | Photometry card "Field photometry…" opens the side sheet on Variables | move | `photometry` | icon+label | none |
| 1.10 S#7 Live curves & diagnostics… | Photometry card light-curve button opens the drawer "Light curve" tab; sheet tab "Metrics" | move | `light-curve` | icon | none |
| 1.10 S#8 Re-run subs… | Photometry card "Re-run subs…" | move | `rerun-photometry` | icon+label | none |
| 1.10 S#9 Reset Window Layout | = 1.3 #20 | merge | `layout-reset` | | |
| 1.14 #1-#3 precondition boxes | the Re-run button is `aria-disabled` with the reason as tooltip: "identify the field first", "assign a target star first", "the target set has no comparison stars: identify the field and wait for the catalogue, or assign Comparison from the image" | replace (P11) | | | |
| 1.14 #4 folder dialog | modal "Folder of saved subs": server listing filtered to folders, shows the FITS count per folder | keep | `browse` | text buttons | |
| 1.14 #5 "No frames" box | inline error in the folder dialog ("No FITS files in this folder"), Open disabled | replace | | | |
| 1.14 #6 progress dialog | inline progress row in the Photometry card + status bar item, "Cancel" | keep | `stop` | icon+label | none |
| 1.14 #7 "Batch failed" box | error toast + log line | replace | | | |
| 1.17 #1 Speed | Mount card jog speed ‹Slow · Normal · Fast› (hardware spec) | merge | | label | |
| 1.17 #2-#5 N/S/W/E | Mount card jog pad (hardware spec) | merge | `jog-north`, `jog-south`, `jog-west`, `jog-east` | icon | arrows when the pad has focus (qt) |
| 1.17 #6 Stop | Mount card jog stop | merge | `stop` | icon | |
| 1.17 #7 arrow keys | as #2-#5 | merge | | | arrows |

Not dropped silently: the dead public API of 1.21 has no UI and is not carried over;
Panels "Float/Dock" and dock drag are dropped for the browser with Q1 open.

### 2.3 Wireframes

W1. Observe at 1440 x 900, drawer closed, card open (rail 420 px, sidebar 92 px).

```
+------+-------------------------------------------------------------------------------------------------------------+
| NAV  | [disconnect Disconnect] | [open-image] | [capture][live][stop Stop] | [-] 100% [+][fit][1:1] |              |
| 92px |  [stretch-auto][stretch-reset][histogram][crosshair] | [plate-solve][plate-solve-auto][sky-grid][target-star]   |
|      |  [labels][catalogue v]  ......................................................  [arrange][panels][theme]     | 47 px, one row
|      +------------------------------------------------------------------------+------------------------------------+
| (F1) | (LIVE) (#128) (10.0 s) (Seestar) (2.39"/px rot 91.2 deg dTarget 1.2') |  v Camera            (Live)        |
| (F2) |                                                                        |    Exposure [ 10.0 s ] Gain [ 80 ] |
| (F3) |                                                                        |    HFD 2.4 px  Temp 21.3 C         |
| (F4) |                           IMAGE (about 927 x 821)                      |  v Display               (Auto)    |
|      |                    markers: o target  [] comp  ^ check                 |    histogram 120 px                |
|      |                                                                        |    Black / Mid / White             |
|      |                                                                        |    <Colour Raw R G B> <rot auto..> |
|      |  +- Variable . XX Cyg ------------- [close] +                          |    <Neutral Negative Fire Ice>     |
|      |  | type HADS   max 11.2  min 12.1           |                          |  > Photometry  XX Cyg  5 comps ok  |
|      |  | period 0.134865 d   AUID 000-BBC-123     |                          |  > Focuser     12 345              |
|      |  | RA 20h 03m 15.6s  Dec +58 57' 16"        |                          |  > Mount       Tracking            |
|      |  | Aperture 6.2 px                          |                          |  > Connection  Seestar S50         |
|      |  | [target-star Target][comparison-star Comparison][check-star Check][remove Remove]                   |
|      |  +------------------------------------------+                          |                                    |
+------+------------------------------------------------------------------------+------------------------------------+
| (*) Connected Seestar S50 | X 512 Y 960 Value 2011 ADU | Frame #128 1080x1920 10.0 s M42_Light_..._0012.fits |   |
|      Sequence 12/120 . ETA 54m 10s | HFD 2.4 px 80 stars | Rate 0.1 fps Latency 0.4 s | [log Log 3]           32 px |
+--------------------------------------------------------------------------------------------------------------------+
```

The toolbar is drawn on three lines here for width; it is one 47 px row (estimated 1 000 px
of controls in 1 348 px). The status bar drops its Zoom item (the toolbar already shows
the zoom) and its Theme item (the theme button tooltip names it) to make room.

W2. Catalogue layers popover (opened by `[catalogue]`, anchored under it, 320 px).

```
+- Catalogue layers -----------------------------------+
| OBJECTS                                         n    |
| [x] [field-stars]   Stars (Gaia DR3 + SIMBAD)  312   |
| [x] [variable-star] Variables (VSX)              4   |
| [ ] [galaxy]        Galaxies                     2   |
| [ ] [nebula]        Nebulae + clusters           0   |
| [x] [exoplanet]     Exoplanet hosts              1   |
| [ ] [other-objects] Other objects                0   |
| REFERENCES                                           |
| [ ] [comparison-star] VSP reference candidates  11   |
| STELLAR DEPTH                                        |
| Gaia G <= [=========|------]  16.4                   |
| Querying catalogues... (spinner)      (busy only)    |
| ---------------------------------------------------  |
| [settings] Catalogue settings...                     |
| [settings] Field identification settings...          |
+------------------------------------------------------+
```

Before a solve every row is disabled with the reason "identify the field first"; counts
show "—".

W3. Star card states (same frame, 320 px max width, bottom-left of the image rectangle).

```
Identifying                                  Manual measurement (no WCS)
+- Identifying catalogue source... [close] + +- Manual image measurement ------- [close] +
| (spinner) Point lookup within 10"        | | No loaded catalogue marker.               |
| RA 05h 35m 17.3s  Dec -05 23' 28"        | | FWHM 3.1"  HFD 3.4"  ecc 0.12  SNR 85     |
| Gaia astrometry . SIMBAD identity        | | peak 41 203 ADU                           |
| [Target][Comparison][Check] (disabled)   | | Scale 2.39"/px  (mount not connected)     |
+------------------------------------------+ | Catalogue identity: identify the field    |
                                             | [Target][Comparison][Check] disabled:     |
                                             |   "identify the field first"              |
                                             +-------------------------------------------+
```

W4. Panels popover (opened by `[arrange]`, 260 px).

```
+- Panels -------------------------+
| RAIL                              |
| [x] Connection                    |
| [x] Camera                        |
| [x] Display                     H |
| [x] Photometry                    |
| [x] Focuser                       |
| [x] Mount                         |
| DRAWER                            |
| [x] [log] Activity log            |
| [ ] [light-curve] Light curve     |
| [ ] [focus-metrics] Focus trend   |
| [ ] [statistics] Statistics       |
| --------------------------------- |
| [layout-reset Reset layout]       |
+-----------------------------------+
```

W5. Bottom drawer (default 216 px, height handle on its top edge).

```
+-- [log Activity log] [light-curve Light curve] [focus-metrics Focus trend] [statistics Statistics] ---- [clear][close] --+
| Light curve: target + check, magnitude axis inverted, BJD or UTC named; one plot, at most 3 series (BRAND 10)                  |
| (contents owned by the photometry and viewer-tools specs)                                                                     |
+-------------------------------------------------------------------------------------------------------------------------------+
```

W6. Photometry rail card (collapsed header shows target, comparison count, quality).

```
v Photometry                                   (Quality ok)
  Target      XX Cyg                 dmag 11.482 +/- 0.012
  Comparisons 5 (VSP 4, manual 1)    used 5
  Check       000-BBC-456            RMS 0.018
  Aperture    6.2 px   annulus 9-14 px
  [photometry Field photometry...] [light-curve] [rerun-photometry Re-run subs...]
  Re-running photometry  37 / 120  [=====-------]  [stop Cancel]     (only while a batch runs)
```

W7. Open FITS image dialog (modal, 640 x 480, also used for "Folder of saved subs" with
folders only).

```
+- Open FITS image ------------------------------------------------------- [close] +
| [up] ~/Argos/sessions/M42/2026-11-01/Light_IR                                     |
| +-----------------------------------------------------------------------------+   |
| | [browse] calib/                                                             |   |
| | M42_Light_10.0s_IR_0001.fits           2026-11-01 21:04     4.1 MB         |   |
| | M42_Light_10.0s_IR_0002.fits           2026-11-01 21:04     4.1 MB         |   |
| +-----------------------------------------------------------------------------+   |
| Path [ /Users/.../M42_Light_10.0s_IR_0002.fits                              ]   |
|                                                           (Cancel)  (Open)        |
+-----------------------------------------------------------------------------------+
```

### 2.4 Interaction and states

- Empty states (existing ImagingScreen messages kept): add a secondary CTA
  `[open-image Open FITS image]` to "No equipment connected" and "Ready for a first frame"
  (offline replay without a telescope is a real workflow).
- Field states, shown in a HUD chip after the frame chips (tokens, text, never colour
  alone): no solution "Field not identified"; solving: spinner + "Identifying field…";
  solved: "{scale}″/px · rot {r}° · Δtarget {t}′" plus "Auto" when auto mode is on;
  failed with a previous solution: warning "Identification failed, last solution kept";
  invalidated: "Field moved: identify again" (reason in the log).
- Identify field disabled reasons: "no frame yet", "preview is at half quality: set Preview
  to Full res", busy while a solve runs (no queue, as Qt). Manual failures raise a toast;
  auto-mode failures only log (no toast every 20 s).
- Layer controls before a solve: disabled with "identify the field first". After a solve
  every layer stays clickable even at count 0 (Qt rule 1720-1722). First solve of a field
  auto-shows Stars, Variables, Galaxies, Nebulae, Exoplanets, Other, Grid and Selected
  stars once; Labels and VSP candidates stay off (Qt 1735-1769). A layer the viewer turned
  off stays off for later fields in the same session (per-viewer pref).
- Star card: opens on click; Escape or `[close]` closes it (Escape also aborts a slew,
  the safety rule of the existing screen). Clicking during a pending identification
  replaces the pending request instead of being ignored (fixes P21: server cancels or
  drops the stale result). The card and the ring are cleared when the field is
  invalidated (fixes P24). Roles are disabled until a solution exists, reason
  "identify the field first".
- Confirmations: none for roles, Remove, layer toggles, Reset layout (all reversible).
  Centre target moves the mount: label "Centre target" with icon (hardware spec), no
  dialog, Escape aborts. Re-run subs: no confirmation, cancellable.
- Busy: catalogue fetch shows a spinner row in the popover and a "Catalogues…" suffix in
  the field chip; batch shows progress in the card and the status bar; point
  identification shows the spinner card.
- Keyboard (single keys never fire in a text field, BRAND 7): S identify field, G grid,
  L labels (new), O catalogue layers popover (new), Ctrl+O open FITS, Escape close card or
  popover and abort a slew, arrows jog only when the Mount jog pad has focus. No single key
  for auto-identify or for roles (they write the target set).
- Night Red: markers keep shape coding (circle target, square comparison, triangle check,
  BRAND 6.8/11); layer colours from `--overlay-*` only; the selection ring uses
  `--accent`; palettes Fire and Ice disabled with the reason "false colour is off in Night
  Red" (Neutral and Negative are drawn through `--viewer-tint`); the file dialogs are the
  custom ones (no OS dialog); the batch progress bar uses tokens.
- Persistence: server config (shared with Qt): `catalog.display_mag_limit`,
  `catalog.*`, `photometry.*`, `camera.full_well_adu`, target sets. Per viewer
  (localStorage, existing `prefs.ts`): card folds (exists), rail open (exists), rail
  width, drawer open / height / tab, layer toggles, Panels selection. Display rotation is
  per viewer today (`argos.rotation`) while Qt uses `ui.display.rotation` (Q6).
- Visible without scrolling at 1440 x 900: toolbar, image, HUD chips, star card, Camera
  and Display cards (BRAND 11.1), Photometry card header, status bar with sequence
  progress. Focuser, Mount and Connection cards are folded below.
- Connect / disconnect / error: the last frame and its overlays stay; the field chip keeps
  its state; device-dependent controls show "connect the equipment first"; a lost mount
  disables Centre target; server link loss keeps the last state (existing behaviour).

### 2.5 API needs beyond v1

| Name | Kind | Payload sketch | Core / worker code it wraps | Notes |
|---|---|---|---|---|
| Identify field | HTTP `POST /api/field/solve` | `{}` -> `202 {state:"solving"}`; 409 `no_frame`, `decimated`, `busy` | `AcquisitionEngine.solve_now` (`acquisition_engine.py:767-785`), `AstrometryController.solve_now` (`astrometry_controller.py:105-119`), `SolveWorker` | long-running (ASTAP); not cancellable today; result via `field` event |
| Auto-identify | HTTP `PUT /api/field/auto` | `{enabled: bool}` -> field state | `AstrometryController.set_auto` (82-85); sequence arming moved server-side from `imaging_page.py:2537-2550` | arm even without a prior WCS (P13, Q12) |
| Field state | WS `field` | `{state:"none"\|"solving"\|"solved"\|"failed"\|"invalidated", auto, reason, solution:{ra_hours, dec_deg, scale_arcsec_px, rotation_deg, delta_target_arcmin, frame_seq, solved_at}}` | `astrometry.state/solved/failed` (`astrometry_controller.py:49-51`), `_on_astrometry_solved` (`imaging_page.py:1378-1403`), `_clear_astrometry` (2440-2498), mount guard (2604-2610), geometry guard (763-771) | sent on every transition |
| Overlay layers | WS `overlays` | `{frame_seq, layers:{grid:{lines:[[x,y]...], centre, target}, stars:[{id,x,y,label,mag_g,details}], variables:[{id,x,y,label,suspected,vsx_index}], galaxies, nebulae_clusters, exoplanets, other_objects, vsp_candidates, targets:[{key,x,y,role,label}]}, counts:{...}, available}` in **sensor px** | `_project_catalog` (`imaging_page.py:1483-1740`), `_project_targets` (1742-1769), `overlay_for` (`astrometry_controller.py:223`), `tracked_wcs` (`acquisition_engine.py:1313-1322`) | coalesce ≥ 75 ms (1472); green px -> sensor px is ×2 on the G1 grid (`green.py:30-47`; exact offset to confirm, U2); Gaia lists can reach 5 000 rows: send static positions once per solve and a per-frame tracker transform `{dx, dy, rot_deg}` instead of re-sending (U6); `details` carries the tooltip lines |
| Display depth | client-side filter on `mag_g` + settings write | `PATCH /api/settings {"catalog.display_mag_limit": 16.4}` | `_on_catalogue_magnitude_changed` / `_save_catalogue_magnitude` (1441-1450) | settings route from the settings spec |
| Catalogue refetch | HTTP `POST /api/field/catalog/refetch` | `{}` | `refetch_catalog` (`acquisition_engine.py:815-832`) | after a settings save; no-op unsolved |
| Catalogue state | WS `catalog` | `{state:"idle"\|"fetching"\|"ready"\|"error", counts, warnings[]}` | `maybe_fetch_catalog`, `_on_catalog` (834-965) | `CatalogWorker` not cancellable |
| Identify point | HTTP `POST /api/field/identify` | `{x, y}` sensor px -> `{request_id, card:{title, lines[], kind, star:{ra_deg,dec_deg,auid,name,source,mags}\|null, roles_enabled, removable, aperture_px, ring:{x,y,r}}, pending:bool}` | hit-test `_on_star_clicked` (793-967), `_nearest` (969-983), `measure_star_at`, card bodies (1188-1284, 1905-2008) | when `pending`, the final card arrives on WS `identify` (`PointIdentityWorker`, `object_resolver_worker.py:66-106`, up to ~35 s, network flags 1066-1076); a new request supersedes the old |
| Selection follow | WS `selection` | `{x, y, r, fwhm_arcsec, hfd_arcsec, ecc, snr, peak_adu}` per frame | `_remeasure_selection` (1230-1246), `_format_star_text` (1257-1284) | only while a measured field star is selected; `DELETE /api/field/selection` to clear |
| Target set | HTTP `POST /api/targets` / `DELETE /api/targets/{key}`; WS `targets` | `{star:{...}, role}`; event `{object_name, stars:[{key, role, name, ra_deg, dec_deg, auid, source, mags}], geometry:{aperture, annulus_in, annulus_out}}` | `set_target_role` (`acquisition_engine.py:1024-1031`), `remove_target` (1235-1240), `set_object_name_if_empty` (`imaging_page.py:2028, 2240`), `photometry_geometry` (1222-1233) | writes `targets/<object>.json` |
| Observation identity | HTTP `PUT /api/observation`; WS `observation` | `{object_name}`; event `{object_name, target:{ra_hours, dec_deg}\|null}` | `on_object_changed` (1010-1022), `set_catalogue_target` (`imaging_page.py:2657-2676`), `set_science_source` (2708-2719) | clears live curves (WS `curves` reset) |
| Catalogue lookup | HTTP `GET /api/catalog/resolve?q=` | -> `{name, ra_hours, dec_degrees, object_type}`; 404 / 502 with the resolver message | `ObjectResolverWorker` (`object_resolver_worker.py:18-34`) | ≤ 8 s (2871); applying it = `PUT /api/observation` + target if `V*` (2675-2676) |
| Nearby names | HTTP `GET /api/catalog/nearby?ra_hours&dec_deg&network=bool`; WS `target_suggestions` on a Stellarium GoTo | `[{name, ra_hours, dec_degrees, object_type, separation}]` | `NearbyObjectResolverWorker` (37-63), `suggest_target_from_coordinates` (`imaging_page.py:2733-2765`), `shell.py:346-353` | hardware spec places it |
| Centre target | HTTP `POST /api/mount/center` | `{}` -> MountState; 409 `no_solution`, `no_target`, `not_connected` | `_center_selected_target` (`imaging_page.py:2616-2639`), `center_target_from_solution` (`device_session.py:595-626`) | moves the mount; invalidates the field |
| Sync | HTTP `POST /api/mount/sync` | `{source:"solution"}` | `sync_current` (`device_session.py:585-593`) | behaviour to decide (P14, Q3) |
| File listing | HTTP `GET /api/files?dir=&kind=fits\|dir` | -> `{dir, parent, entries:[{name, kind, size, mtime, fits_count?}]}` | none (new); defaults `sessions_path` (`imaging_page.py:1319`), `last_sequence_dir` (2283) | local server only; restrict to readable dirs; Tauri may use a native dialog outside Night Red (Q4) |
| Open FITS | existing `POST /api/camera/open-fits` + frame header fields | header `{path, file_name, date_obs}` for `source:"file"` | server `hub.py` `load_fits_frame`; Qt `_on_open_fits` (1312-1339) | must invalidate the field and set the photometry epoch from DATE-OBS (P9) |
| Frame metrics | frame header field `metrics` | `{hfd_px, mean_fwhm_px, star_count, sky_adu}` | `build_processed_frame` (`preview_processor.py:59-111`), `frame_metrics` | feeds HFD in the status bar and the camera card, focus trend, metrics tab |
| Frame saved | WS `frame_saved` | `{path, name, source:"single"\|"sequence", hfd, fwhm, star_count}` | `frame_saved` (`acquisition_engine.py:554`), `_save_fits_async` (1510-1595) | single-shot saves must emit too (P7) |
| Sequence progress | WS `sequence` | `{running, object, done, total, eta_s}` | `sequence_running`, `sequence_progress` (93-95) | shared with the Plan spec |
| Activity text | WS `activity` | `{text}` | `_STATE_ACTION` (`imaging_page.py:126-132`), `astrometry.state`, preview `status_updated`, AF done (2848) | the HUD shows camera and field states; this feeds the status bar tooltip |
| Log levels | WS `log` field | add levels `ok` and `cmd` | `LogPanel.append` levels (`log_panel.py:64-80`) | web log drawer adds two styles; cap at N lines (P25) |
| Batch re-run | HTTP `POST /api/photometry/batch` / `DELETE /api/photometry/batch`; WS `batch` | `{folder}` -> `202`; 409 `no_solution`, `no_target`, `no_comparison`, `no_frames`, `busy`; event `{state, done, total, result:{frames_done, targets, rotation_deg, shift_px, error}}` | `_on_rerun_subs` (`imaging_page.py:2248-2318`), `PhotometryBatchWorker` (`photometry_batch_worker.py:71-155`), `_on_batch_done` (2337-2367), `adopt_curves` (`acquisition_engine.py:258-267`) | cancellable at frame boundaries; output folder to settle (P10) |
| Photometry stream | WS `photometry_point`, `curves`, `comparison_quality` | as `PhotometryPoint` / store snapshot / report | `acquisition_engine.py:106-108, 1415-1479` | photometry spec owns the shape |
| Comparisons | HTTP `POST /api/photometry/comparisons/reselect` | `{}` -> `{added}` | `reselect_comparison_stars` (1053-1075), `_recommend_comparison_stars` (`imaging_page.py:2185-2196`) | photometry spec |
| Camera offset / binning / filter | HTTP `PUT /api/camera/settings`, `POST /api/filterwheel/select` | `{offset?, binning?}` -> 409 `busy` "{owner} running — it owns the camera. Stop it first."; `{name}` -> 409 `not_connected` / 404 `unknown_filter` | `_on_camera_offset` / `_on_camera_binning` (2504-2530), `_on_camera_dock_filter` (690-702) | hardware spec |
| Autofocus progress | WS `autofocus` | `{running, step, total, position, hfd, best:{position, hfd}}` | `_on_af_step` / `_on_af_done` (2832-2848) | hardware spec |
| Display measurement radius | `PATCH /api/settings` or `PUT /api/display/star-radius` | `{radius_px: 2..30}` | `_on_star_radius` (`imaging_page.py:786-791`) | changes server-side HFD/FWHM measurement; viewer-tools spec |
| Saturation threshold | settings read | `camera.full_well_adu` | `_on_saturation_toggled` (721-723) | client-side overlay |

## 3. Open questions for the owner

1. Q1 Floating panels: Qt docks float to a second monitor. Drop for the browser, or plan
   Tauri multi-window "open in window" for the light curve and the log?
2. Q2 Re-run subs: keep it on Observe (it uses the current solve and target set) or move
   it to Review with an explicit reference frame?
3. Q3 Sync: make it sync to the plate-solved centre, or remove it in favour of "Centre
   target" (today it syncs the mount to its own position, P14)?
4. Q4 File access: may the server list directories for the file pickers (local token
   holder only), or must every pick go through a Tauri native dialog (grey in Night Red)?
5. Q5 Layer toggles and the Gaia depth: per viewer (localStorage) or shared server
   settings (Qt saves only the depth)?
6. Q6 Display rotation: keep the web per-viewer pref or reuse Qt's `ui.display.rotation`?
7. Q7 Point identification queries Gaia and SIMBAD on every click on an unmarked star:
   keep automatic, or make it an explicit "Identify" action when offline-first matters?
8. Q8 Palettes in Night Red: allow only Neutral and Negative?
9. Q9 Batch output folder: `~/Argos/targets` (today) or the session's own folder?
10. Q10 Should the Light curve drawer tab open automatically when a target exists and a
    run starts (Qt hides it by default and misplaces it, P2)?
11. Q11 Opening a FITS while live view runs: stop live first, or let the next live frame
    replace the file (Qt behaviour)?
12. Q12 Arm auto-identification for every sequence, even without a prior solution (P13)?
13. Q13 Design tokens: there is no `--overlay-*` token for VSP reference candidates or
    for the selection ring; the design team must add them (BRAND 12).

Uncertain points (not verified, to check before implementation):

- U1 The dock list context menu (1.4 #7): its content was listed offscreen with
  `createPopupMenu()`; the right-click trigger itself was not exercised.
- U2 Green-plane to sensor pixel mapping for the overlay API: the green plane is
  `(H//2, W//2)` on the G1 grid with G2 averaged (`argos/core/imaging/green.py:30-47`), so
  sensor x is about 2·gx (+0.5 for the G1/G2 centroid). The exact convention must be
  fixed and tested against `photutils` centres; the core also uses this green plane for
  the mono simulator.
- U3 P17: whether centring should use the tracked WCS was not measured on sky.
- U4 P10: whether `sessions_path.parent / "targets"` is intended.
- U5 `QProgressDialog` modality: not set in code and shown with `show()`; Qt's default is
  non-modal, not checked at run time.
- U6 Size and rate of the `overlays` event with thousands of Gaia markers: not measured.
- U7 Marker hover tooltips are rendered by `FitsViewer` (viewer-tools spec); this spec
  only lists the strings the page builds.
