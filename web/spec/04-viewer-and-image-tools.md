# Image viewer and image tools: Qt inventory and web redesign

Spec 04 of the web-UI rewrite. Branch `explore/web-ui`, Qt sources as of `74c9c2e` plus the
working tree on 2026-11-01. pyqtgraph behaviour is quoted from the installed 0.13.7
(`.venv/lib/python3.11/site-packages/pyqtgraph`). Every Qt claim cites `file:line`; points
inferred rather than observed are flagged **(uncertain)** and repeated in the structured
result.

Conventions in this document:

- "display px" = pixels of the array the Qt viewer shows (always the full sensor geometry,
  see `debayer.render_view`), "green px" = the half-resolution green plane every science
  routine uses (`argos/core/imaging/green.py:1-20`), "frame px" = web frame pixels in the
  numpy convention (pixel centres at integers, `web/src/lib/viewer/types.ts:13-21`).
- Problems are numbered P1…P31 in section 1.9 and referenced from each element.
- Icon ids are from `web/src/design/icon-inventory.json`. No new icon id is needed (2.2).

---

## 0. Scope

### 0.1 Files covered

| File | Lines | Role |
|---|---|---|
| `argos/ui/widgets/fits_viewer.py` | 989 | `FitsViewer`: pyqtgraph `ImageView` + stretch, rotation, palettes, saturation, ROI, crosshair, loupe, selection ring, WCS grid, 8 marker layers |
| `argos/ui/widgets/image_toolbar.py` | 106 | `ImageToolbar`: Open image, Preview (CFA view), Palette |
| `argos/ui/widgets/overlay_bar.py` | 194 | `OverlayBar`: 10 overlay chips, Gaia G limit slider, catalogue settings button |
| `argos/ui/widgets/histogram_dock.py` | 296 | `HistogramDock` ("Adjust image"): histogram, levels, transfer, rotation, auto, 5 tool toggles, star aperture, ROI stats |
| `argos/ui/widgets/star_info_card.py` | 240 | `StarInfoCard`: floating on-image card with role buttons |
| `argos/ui/widgets/statistics_dock.py` | 90 | `StatisticsDock`: 11 whole-frame statistics |
| **Total** | **1915** | |

Read for wiring only (owned by other specs): `argos/ui/pages/imaging_page.py` (2888, the
Observe host), `argos/ui/analysis_window.py` (1197, the "Frame Viewer" host, Review), and
the core they call: `argos/core/imaging/{stretch,debayer,metrics,green,platesolve,astrometry_session}.py`,
`argos/workers/preview_processor.py`, `argos/core/session/acquisition_engine.py`,
`argos/core/catalog/targets.py`.

### 0.2 Elements in scope

| Id | Element | Class / file:line | Kind | How opened | Modal | Placement |
|---|---|---|---|---|---|---|
| E1 | Image canvas | `FitsViewer` fits_viewer.py:73 | central widget (pyqtgraph `ImageView`, fits_viewer.py:137-142) | always present | no | Observe: central widget above the context strip (imaging_page.py:240, 269-275). Frame Viewer: left pane of a splitter (analysis_window.py:194, 235-242) |
| E2 | Viewer context menu | pyqtgraph `ViewBoxMenu` (ViewBox.py:1298-1310, ViewBoxMenu.py:10-66) + scene "Export..." (GraphicsScene.py:102-103) | context menu + export dialog | right-click on the image | no | at the cursor |
| E3 | In-image readouts and overlays | fits_viewer.py:147-247 | overlays on the canvas | by the toggles of E7/E8 and by host calls | no | readout top-left (10,10); centre label (10,36); loupe top-right; selection label bottom-left |
| E4 | Marker hover tooltip | pyqtgraph `ScatterPlotItem` tip, `_marker_tip` fits_viewer.py:54-61 | tooltip popover | hover a marker | no | at the cursor |
| E5 | Region box (ROI) | `pg.RectROI` fits_viewer.py:386-395 | draggable on-image box | E8 "Region statistics" checkbox (Observe only) | no | in image coordinates, starts at (10,10) 80×80 |
| E6 | Image toolbar | `ImageToolbar` image_toolbar.py:22 | toolbar (38-48 px, :39-40) | always | no | top of Observe (imaging_page.py:236-237) and of the Frame Viewer (analysis_window.py:185-186) |
| E7 | Overlay bar | `OverlayBar` overlay_bar.py:54 | two-row chip strip (≤ 76 px, :67) | always; chips disabled until a solve (:144) | no | Observe: under the panel strip (imaging_page.py:317-322); Frame Viewer: under the toolbar (analysis_window.py:187-192) |
| E8 | "Adjust image" card | `HistogramDock` histogram_dock.py:41 | `design.Card` in a dock / tab | Observe: dock "Image display" (imaging_page.py:283), hidden by default (:451), shown by the "Image display" chip of the panel strip (:354-364). Frame Viewer: tab "Adjust image" (analysis_window.py:232) or the checkable "Adjust image" button (:260-264, :276-277); built with `show_roi=False` and the WCS checkbox hidden (:195, :292) | no | Observe: right dock area; Frame Viewer: right tab pane |
| E9 | Star info card | `StarInfoCard` star_info_card.py:21 | floating frame, child of the viewer (imaging_page.py:242) | left-click hit on the image (imaging_page.py:793-1006). Observe only | no | bottom-left of the viewer (star_info_card.py:135-141), draggable, resizable |
| E10 | Statistics card | `StatisticsDock` statistics_dock.py:22 | `design.Card` in dock "Image statistics" (imaging_page.py:287-289) | hidden by default (:451); "Panels ▾" menu (:366-375). Observe only | no | right dock area |
| E11 | "Open FITS" file dialog | `QFileDialog.getOpenFileName` (imaging_page.py:1320-1322; analysis_window.py:441-443) | native file dialog | E6 "Open image…" | yes | OS |
| E12 | Catalogue settings dialog | `AstrometrySettingsDialog(section=SECTION_CATALOG)` (imaging_page.py:1427-1433; analysis_window.py:564-569) | modal dialog, `exec()` | E7 "Catalogues / depth…" | yes | **out of scope** (Settings spec); only its entry point and its `saved` side effects are covered here |

---

## 1. Inventory (Qt, as it is today)

### 1.1 Image canvas (`FitsViewer`, fits_viewer.py:73, central widget, always visible, non-modal)

- Purpose: show a linear 16-bit display array through a non-destructive stretch, read pixels,
  measure regions and stars, and draw every astrometric and catalogue overlay. Nothing
  touches the FITS data (module docstring :1-12).
- Construction: `ImageView` with its ROI button, menu button and histogram hidden
  (:138-141); the ViewBox right-click menu is **not** disabled (E2).

Controls (pointer):

| # | Control | Qt type | Label / tooltip (exact text) | Default / range / step / units | Enabled or visible when | Shortcut | Action: handler file:line → effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Left click | `scene.sigMouseClicked` (:250) | none | position in display px, un-rotated before emit | a frame is shown and the click is inside the image; left button only (:867-879) | — | `_on_mouse_clicked` :867-881 → `star_clicked(x, y)` → Observe `_on_star_clicked` imaging_page.py:793 (hit-test and card, see 1.6); Frame Viewer `_on_star_clicked` analysis_window.py:885 (nearest visible catalogue source, else `measure_star_at`, result in the "Frame · selected star" tab) | no |
| 2 | Left drag | pyqtgraph `ViewBox` PanMode | none | — | always | — | `ViewBox.mouseDragEvent` ViewBox.py:1331-1355 → pan; auto-range stops until the next rotation change | no |
| 3 | Middle drag | same | none | — | always | — | same as #2 (ViewBox.py:1331) | no |
| 4 | Right drag | `ViewBox` | none | 2 % per px of vertical travel, aspect locked | always | — | ViewBox.py:1356-1375 → zoom about the press point | no |
| 5 | Wheel | `ViewBox.wheelEvent` | none | factor 1.02^(delta × −1/8) ≈ ×1.35 per 120-unit notch; no zoom or pan limits | always | — | ViewBox.py:1283-1296 → zoom about the cursor | no |
| 6 | Double click | `GraphicsScene.mouseDoubleClickEvent` | none | — | — | — | no ARGOS action; pyqtgraph queues an extra click event (GraphicsScene.py:245-248) that `_on_mouse_clicked` does not filter (`ev.double()` unchecked) → a second `star_clicked` **(uncertain)** | no |
| 7 | Hover | `scene.sigMouseMoved` (:249) | readout text `({x}, {y})   {v} ADU` (mono) or `({x}, {y})   R {r}  G {g}  B {b}` (colour) | coordinates un-rotated display px (:435-440) | frame shown; outside the image the readout, crosshair and loupe hide (:446-451) | — | `_on_mouse_moved` :420-451 → readout label, crosshair lines (if on), loupe (if on) | no |
| 8 | Hover a marker | `ScatterPlotItem(hoverable=True, tip=_marker_tip)` | the marker's full identity text (multi-line, HTML-escaped, :54-61); texts built by the host (imaging_page.py:1505-1507, 1905-2008) | hover sizes: variables 36, stars 24, context layers 36, VSP 26, selected set 40 px | layer visible | — | Qt tooltip + enlarged symbol (:662, :702, :741, :794, :859) | no |
| 9 | Drag the region box | `pg.RectROI` (:388) | none | starts at (10,10), 80×80 view px, yellow 1 px pen `"y"` | E8 #10 on (Observe only) | — | `sigRegionChanged` → `_on_roi_changed` :397-414 → `region_stats` (stretch.py:195) on the clipped display array (RGB averaged) → `region_info` → `HistogramDock.set_region_info` (histogram_dock.py:238-257) | no |
| 10 | Drag the box's corner handle | `RectROI` scale handle | none | — | same | — | resize, same chain as #9 | no |
| — | Keyboard | `ImageView.keyPressEvent` | — | — | — | none | without a time axis keys pass through (ImageView.py:516-519); the ViewBox `+`/`-`/Backspace act only on a RectMode zoom history (ViewBox.py:1377-1395): **no effective binding** | — |

Public API used by the hosts (not user controls, listed so nothing is lost):
`set_rotation` :256, `display` :293, `set_palette` :337, `set_stretch` :364, `auto_stretch`
:370, `set_saturation` :377, `set_roi_enabled` :386, `set_crosshair_enabled` :453,
`set_frame_geometry` :464, `set_astrometry_overlay/_enabled` :472/:479,
`set_catalog_markers/_enabled` :552/:562, `set_field_catalogue_markers/_enabled` :566/:575,
`set_context_markers/_enabled` :579/:595, `set_marker_labels_enabled` :601,
`set_comparison_markers/_enabled` :748/:760, `set_target_markers/_enabled` :809/:816,
`set_loupe_enabled` :862, `mark_selection` :883, `clear_selection` :918, `reset` :967 (never
called, P15). Signals: `levels_changed(black, white, midtones)` :76, `region_info(dict|None)`
:77, `star_clicked(x, y)` :78.

Displayed data:

| Element | Source and format | Placement / style | Refresh |
|---|---|---|---|
| Image | `apply_stretch(_last_arr, black, white, mode, midtones)` (stretch.py:57) → uint8, then palette LUT (:337-345) | `ImageView`, row 0 at the top | each `display()` (every processed frame) and each stretch change |
| Pixel readout | value of the **display** array, not the raw frame (P4) | label top-left (10,10), `BG2`, mono 11 px (:155-162) | mouse move |
| Crosshair | two `InfiniteLine`s, `WARNING` 1 px (:147-151), through the cursor | full width and height | mouse move, only when on |
| Loupe | 42×42 display px of the stretched u8 image (saturation colour included) scaled to 168×168, nearest neighbour (:923-954), `WARNING` 1 px crosshair (:956-963), black background, `WARNING` border | top-right (w − 178, 10) | mouse move, only when on |
| Selection ring | `ACCENT` 2 px circle, 60 points, radius = aperture in display px; `ACCENT` 6 px centre dot (:167-174, :883-908) | data space (grows with zoom) | click; every frame for a pinned field star (imaging_page.py:1230-1255) |
| Selection label | text passed to `mark_selection` (:909-916) | bottom-left (10, h − label − 10), `BG2`, `ACCENT` border | Frame Viewer measured star (analysis_window.py:977); Observe photometry-table focus, `"{Role} · {name}"` (imaging_page.py:2071-2077) |
| WCS grid | `WCSOverlay.lines` (platesolve.py:105-116, built by `wcs_grid` :437-527, spacing `astrometry.grid_spacing_arcmin`, astrometry_session.py:137-153), NaN-broken polyline, `ACCENT` 2 px dotted (:194-198) | data space | solve, rotation, new frame |
| Grid labels | `TextItem` `ACCENT` at the first in-frame point of each line: RA `HHhMMmSS.Ss`, Dec `±DD°MM'SS.S"` (platesolve.py:487-511, :535-572) | data space | with the grid |
| Centre label | `"Centre  RA {hms}  Dec {dms}"` (platesolve.py:518-520) | label (10, 36), `ACCENT` border (:241-247, :523-530) | with the grid |
| Target reticle | `SUCCESS` 2 px circle, r = 5 % of min(w, h), at the GoTo target (:199-201, :514-521) | data space | only after a live solve that had a pending target (astrometry_controller.py:187, :223) |
| Saturation | pixels ≥ threshold painted (255, 0, 0) (:347-358); threshold `camera.full_well_adu`, default 60000 (imaging_page.py:721-723) | in the image | each render |
| Marker layers | see table below | data space, pixel-sized symbols | each `display()` and each host re-projection |

Marker layers (all positions arrive in green px and are scaled `display = green × (dw/gw)`,
then rotated, e.g. :635-645):

| Overlay chip (E7) | Viewer setter | Symbol, size (screen px) | Pen | Label when "Labels" is on | Hover | file:line |
|---|---|---|---|---|---|---|
| Variables (VSX) | `set_catalog_markers((x, y, suspected, name, tooltip))` | circle 30 (item built at 28, :205) | `VARIABLE` 2 px; suspected `VARIABLE` 1 px dashed | name, `VARIABLE`, slot-limited | 36 | :205-207, :622-663 |
| Stars (Gaia DR3, SIMBAD stars, point identities) | `set_field_catalogue_markers((x, y, name, tooltip))` | circle 18 | `FG_MUTED` 2 px | name if not a survey id (imaging_page.py:1543-1548, :1884-1902), `FG_MUTED` | 24 | :208-212, :665-703 |
| Galaxies | `set_context_markers("galaxies", …)` | circle 28 | `CYAN` 2 px | `CYAN` | 36 | :213-215, :705-742 |
| Nebulae + clusters | `"nebulae_clusters"` | square 30 | `WARNING` 2 px | `WARNING` | 36 | :216-218 |
| Exoplanets | `"exoplanets"` | `star` (five-point) 26 | `SUCCESS` 2 px | `SUCCESS` | 36 | :219-221 |
| Other objects | `"other_objects"` | circle 24 | `FG_MUTED` 2 px | `FG_MUTED` | 36 | :222-224 |
| VSP references | `set_comparison_markers((x, y, tooltip))` | `+` 20 (item built as square 16, :230) | `CYAN` 2 px | never: VSP chart labels are magnitudes (:748-754) | 26 | :230-234, :770-795 |
| Selected stars | `set_target_markers((x, y, name, role, tooltip))` | target circle 34; comparison square 30; check triangle pointing **down** (`'t'`) 30 | `ACCENT` 3 / `CYAN` 3 / `SUCCESS` 3 (:803-807) | target and check names in the role colour, **not** slot-limited; comparisons never (:852-858) | 40 | :238-240, :809-860 |

Label rules: whitespace collapsed; longer than 18 characters becomes first 11 + "…" + last 6
(`_short_marker_label` :46-51). De-overlap: one label per 150×42 **image-px** cell including
its 8 neighbours (`_claim_label_slot` :613-620), recomputed per refresh (P27).

Implicit behaviours:

- **Auto levels.** `_auto_on` starts true (:90). Each `display()` runs `auto_stf` on the
  un-rotated array (median − 2.8 σ_MAD black, 99.8th percentile white, midtones mapping the
  median to 0.25; stretch.py:34-54) and emits `levels_changed` (:304-306). Any
  `set_stretch` turns auto off until `auto_stretch` (:364-375).
- **Rotation.** `auto` turns portrait frames 90° clockwise, fixed modes are clockwise
  (:39-43, :265-269). A change of quarter turns clears the selection and auto-ranges the
  view (:302-303, :317-318). Overlays, clicks and readouts speak un-rotated coordinates
  (:271-291, :880).
- **Every `display()`** re-renders all layers and the ROI statistics (:307-320).
- **Geometry.** Markers stay hidden until `set_frame_geometry` gave a green shape (:487-488).
- **Colours** of the crosshair, selection, grid, target reticle and loupe pens are read
  from `theme` once, at build time (:147-201): a live theme switch does not repaint them
  (theme.py:14-17, P6).
- **Host-driven (Observe).** The card hides and the selection clears when the green
  geometry changes (imaging_page.py:737-742). Every WCS overlay is dropped after a slew
  (`session.slewed`, :524 → `_clear_astrometry` :2440-2498) and when the displayed geometry
  differs from the solved one (:763-771). Markers follow the live tracker through
  `engine.tracked_wcs()` (:1474-1481), re-projected after a 75 ms debounce (:210-212,
  :1467-1472) on `apertures_tracked` (:546), on each frame when solved (:775-778) and on
  catalogue delivery (:1460-1464).
- **Auto-arming (Observe).** A layer is switched on automatically the first time it has
  data in a field (`_arm_overlay` imaging_page.py:1452-1458); grid at solve (:1397); VSP
  candidates are never auto-shown and are hidden when none is detected (:1735-1739);
  "Labels" is armed **off** (:1763-1769). `_armed` resets on every slew (:2467).

Messages: the widget itself emits none. Host messages tied to it:

| Text (exact) | Level | When | file:line |
|---|---|---|---|
| `Frame geometry changed — WCS overlays cleared (solve again at full res).` | INFO log | displayed green shape ≠ solved green shape | imaging_page.py:769-771 |
| `Solve finished for a different frame geometry — discarded.` | INFO log | solve result for an older geometry | imaging_page.py:1390-1392 |
| `Selected star is outside the solved image.` | WARN log | Photometry table row focused but off-frame | imaging_page.py:2062 |

Problems: P4, P5, P6, P9, P15, P18, P19, P21, P22, P23, P25, P27, P28.

### 1.2 Viewer context menu (pyqtgraph `ViewBoxMenu` + scene "Export...", right-click, non-modal popup)

- Purpose: library defaults left enabled. None is an ARGOS feature; all act on the view.

| # | Control | Qt type | Label (exact) | Default / range | Enabled when | Shortcut | Action: file:line → effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | View All | `QAction` | "View All" | — | always | — | ViewBoxMenu.py:18-20 → auto-range (fit the whole image) | no |
| 2 | X axis ▸ | submenu with a form | "X axis": "Manual" radio + min / max fields; "Auto" radio + "%" spin; "Invert Axis"; "Mouse Enabled"; "Link Axis:" combo; "Auto Pan Only"; "Visible Data Only" | auto, 100 % | always | — | ViewBoxMenu.py:25-48, axisCtrlTemplate_generic.py:69-87 → manual range, **mirrors the image** (Invert), disables panning on one axis | no |
| 3 | Y axis ▸ | same | "Y axis" + same form | Y already inverted (ImageView.py:148) | always | — | same; "Invert Axis" off flips the image upside down | no |
| 4 | Mouse Mode ▸ | radio group | "3 button" / "1 button" | 3 button | always | — | ViewBoxMenu.py:54-64 → "1 button" makes left drag draw a zoom rectangle | no |
| 5 | Export... | `QAction` → `ExportDialog` | "Export..." → formats "Image File (PNG, TIF, JPG, ...)", "Scalable Vector Graphics (SVG)", "CSV of original plot data", "HDF5 Export: plot (x,y)", "Matplotlib Window", "Printer" | — | always | — | GraphicsScene.py:102-103, exporters/*.py → saves or prints the rendered view (overlays included) | no |

Problems: P25.

### 1.3 Image toolbar (`ImageToolbar`, image_toolbar.py:22, toolbar, always visible, non-modal)

- Purpose: open a FITS file and choose the display rendering. Its docstring says solve,
  auto-solve and photometry moved to the Shell menus (:22-31).

| # | Control | Qt type | Label / tooltip (exact text) | Default / range | Enabled or visible when | Shortcut | Action: handler file:line → effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Open image | `QPushButton` (:51-54) | "Open image…"; tooltip "Open a FITS image" | — | always | none on the button (File ▸ "Open FITS image…" has `QKeySequence.Open`, shell.py:192-196) | `open_requested` → Observe `_on_open_fits` imaging_page.py:1312-1339: `QFileDialog.getOpenFileName(self, "Open FITS", start, "FITS (*.fits *.fit *.fts);;All files (*)")`, start = config `sessions_path` or home; astropy `getdata`, must be 2-D; `engine.ingest_frame(uint16)` (acquisition_engine.py:515-523): the frame enters the live pipeline (solve, catalogue, roles, re-run work offline). Frame Viewer `_on_open` analysis_window.py:437-445 → `load(path)` replaces the frame in the same window | start folder from `sessions_path` |
| 2 | Preview | `QComboBox` (:57-77) after label "Preview:" | items "Colour (CFA)", "Raw CFA", "Red (CFA)", "Green (CFA)", "Blue (CFA)" (data = `debayer.VIEWS` "Super-pixel", "Raw CFA", "R", "G", "B", debayer.py:45-51); tooltip "Changes only the on-screen preview; every view keeps the same sensor geometry and annotation coordinates. FITS data are unchanged." | "Colour (CFA)" (:69); the Frame Viewer forces "Raw CFA" on each load (analysis_window.py:333-334) | always | — | `channel_changed` → Observe `_on_channel_changed` imaging_page.py:714-719 (re-submits the last raw to the `PreviewProcessor`, preview_processor.py:125-129 → `render_view` debayer.py:239; colour = super-pixel 2×2 → RGB, expanded ×2, background-neutralised gains 0.25-4, debayer.py:186-202); Frame Viewer `_on_channel` :429-431 → `_reprocess` (synchronous `build_processed_frame` on the UI thread) | no |
| 3 | Palette | `QComboBox` (:80-94) after label "Palette:" | items "Neutral", "Negative", "Fire", "Ice"; tooltip "False-colour display palette for inspecting faint detail and saturation." | Neutral | always | — | `palette_changed` → Frame Viewer `viewer.set_palette` (analysis_window.py:281 → fits_viewer.py:337-345). Colour stops: neutral black→white; negative white→black; fire (0,0,0)→(50,0,80)→(190,20,20)→(255,150,0)→(255,255,210); ice (0,0,0)→(0,20,90)→(0,150,220)→(160,240,255)→(255,255,210). **Observe: not connected (P1)**; inert on RGB images (P2) | no |
| — | Caption | `QLabel` (:97) | "Preview only · FITS unchanged" | — | always | — | none | — |

`set_view(view)` (:99-106) selects a view without re-emitting (Frame Viewer only).

Messages:

| Text (exact) | Kind | When | file:line |
|---|---|---|---|
| `Open FITS: {exc}` (e.g. `Open FITS: expected a single 2-D image HDU`) | ERROR log | unreadable file or not 2-D (Observe) | imaging_page.py:1329-1333 |
| `Loaded {name} — solve to enable catalog & photometry.` | OK log | Observe open succeeded | imaging_page.py:1337-1339 |
| `Opened  {name}` | context strip under the image | same | imaging_page.py:1336 |
| `Frame Viewer — {name}  ({w}×{h})` | window title | Frame Viewer load | analysis_window.py:337 |
| (nothing) | — | Frame Viewer open of an unreadable file | analysis_window.py:444-445 (P24) |

Problems: P1, P2, P24, P26.

### 1.4 Overlay bar (`OverlayBar`, overlay_bar.py:54, two-row chip strip, always visible, non-modal)

- Purpose: show or hide every solved-field layer, set the Gaia G display limit, reach the
  catalogue settings. Row "Objects" groups physical object types; row "Display" groups the
  rest (:1-6, :74-129).
- Chips: checkable `QPushButton`s, 11 px, **disabled at creation** (:141-149). Tooltip of a
  disabled chip: `Solve and identify the field to enable this layer.` (:171-179). Text gets
  ` · {count}` from the host (:166-169).

| # | Control | Qt type | Label / tooltip (exact text) | Default / range / units | Enabled when | Shortcut | Action: handler file:line → effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Stars | checkable chip | "Stars"; "Gaia DR3 stars, enriched with conventional SIMBAD identities when available." | off; auto-on when first populated | field solved (imaging_page.py:1723-1734) | — | `toggled("catalogue", on)` → `_on_overlay_toggled` imaging_page.py:1409-1425 → `viewer.set_field_catalogue_enabled` | no |
| 2 | Variables | chip | "Variables"; "Variable stars from the AAVSO VSX catalogue." | same | same | — | → `set_catalog_enabled` | no |
| 3 | Galaxies | chip | "Galaxies"; "Galaxies identified by SIMBAD or the bundled Messier/NGC/IC catalogue." | same | same | — | → `set_context_enabled("galaxies")` | no |
| 4 | Nebulae + clusters | chip | "Nebulae + clusters"; "Nebulae and stellar clusters identified by SIMBAD or the bundled Messier/NGC/IC catalogue." | same | same | — | → `set_context_enabled("nebulae_clusters")` | no |
| 5 | Exoplanets | chip | "Exoplanets"; "Confirmed exoplanet hosts returned by NASA (cache first)." | same | same | — | → `set_context_enabled("exoplanets")` | no |
| 6 | Other objects | chip | "Other objects"; "Other physically classified SIMBAD sources, such as radio or X-ray sources." | same | same | — | → `set_context_enabled("other_objects")` | no |
| 7 | Coordinate grid | chip | "Coordinate grid"; tooltip falls back to "Show or hide this overlay." (no entry in `_TOOLTIPS`, :38-51) | auto-on at the first solve of a field (imaging_page.py:1397) | solved | — | → `set_astrometry_enabled`; duplicate of 1.5 #12 (P3) | no |
| 8 | VSP references | chip | "VSP references"; "AAVSO VSP reference candidates; not necessarily the selected ensemble." | off, never auto-shown in Observe (imaging_page.py:1735-1739); auto-on in the Frame Viewer (analysis_window.py:523-529) | solved | — | → `set_comparison_enabled` | no |
| 9 | Selected stars | chip | "Selected stars"; "The target, selected comparison stars and check stars for this observation." | auto-on when the set has on-frame stars (imaging_page.py:1752); forced on when a Photometry table row is focused (:2069-2070) | the set has on-frame stars | — | → `set_target_enabled` | no |
| 10 | Labels | chip | "Labels"; "Show compact non-overlapping labels; hover a marker for its full identity." | armed **off** (imaging_page.py:1763-1769; analysis_window.py:527) | any layer has points (imaging_page.py:1753-1762) | — | → `set_marker_labels_enabled` | no |
| 11 | Gaia G limit | `QSlider` (:98-111) + caption "Gaia G limit" + value label `≤ {v:.1f}` | caption tooltip "Stellar display limit in the Gaia G passband. It does not filter galaxies or nebulae whose integrated magnitudes use different passbands."; slider tooltip "Faint-end Gaia G display limit. Move left to declutter; move right to reveal fainter Gaia stars already cached for this field." | 5.0-20.0 mag in 0.1 steps (raw 50-200); max reset to `catalog.field_stars_mag_limit` (default 18.0, :162-164); value from `catalog.display_mag_limit` (default 18.0, imaging_page.py:190, :321) | always (even unsolved) | — | `valueChanged` → `magnitude_changed` (:151-154) → Observe `_on_catalogue_magnitude_changed` imaging_page.py:1441-1445 (re-project, 75 ms debounce; filters Gaia stars only, :1529-1538, :1782-1784); Frame Viewer `_project_field_catalogues` on every step (analysis_window.py:579-581, no debounce). `sliderReleased` → `magnitude_committed` (:108-110) → `config.set("catalog.display_mag_limit")` + `config.save()` (imaging_page.py:1447-1450) | `catalog.display_mag_limit`, **only on handle release** (P11) |
| 12 | Catalogues / depth | `QToolButton` (:120-127) | "Catalogues / depth…"; "Choose Gaia, VSX, SIMBAD, NASA and offline catalogue sources, query depth, cache folders and refresh behaviour." | — | always | — | `configure_requested` → `_open_field_catalogue` imaging_page.py:1427-1433: modal `AstrometrySettingsDialog(section=SECTION_CATALOG)` (E12); on `saved`: `engine.refetch_catalog` (acquisition_engine.py:815), re-project, `_sync_catalogue_depth` (:1435-1439, slider max and clamp). Frame Viewer: :564-577 (re-fetch if solved) | in the dialog |

Displayed data: per-chip counts (`set_count`), refreshed at each re-projection
(imaging_page.py:1724-1734; analysis_window.py:834-856); reset to 0 on slew (:2476-2498).
The "Selected stars" and "Labels" chips show no count. Messages: none besides tooltips.

Problems: P3, P11, P12, P18.

### 1.5 "Adjust image" card (`HistogramDock`, histogram_dock.py:41, dock "Image display" / tab "Adjust image", non-modal)

- Purpose: histogram, display levels, transfer, rotation and the image tools. Title
  "Adjust image" (:55). Imaging page built with `show_roi=True`, Frame Viewer with
  `show_roi=False` (analysis_window.py:195).

| # | Control | Qt type | Label / tooltip (exact text) | Default / range / step / units | Enabled or visible when | Shortcut | Action: handler file:line → effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Histogram plot | `pg.PlotWidget` (:75-88), height 120-180 px | caption "Raw FITS histogram", tooltip "Black, white and midtones change only the display mapping; the histogram keeps the original FITS sample values." (:67-72) | x = ADU over [raw min, 99.8th percentile]; y = log1p(count), axis hidden; R `DANGER`, G `SUCCESS`, B `ACCENT` 1 px | always | — | display only, but pyqtgraph-interactive: drag pans, wheel zooms, right-click menu with "Plot Options" (Transforms, Downsample, Average, Alpha, Grid, Points) and "Export..." (PlotItem.py:190-202) | no |
| 2 | Black | `QSlider` (:97) | label "Black" | int ADU; range reset per frame to [min, p99.8] (:216-219) | always | arrow keys / PgUp/PgDn when focused (Qt default) | `_emit_stretch` :288-296 → `stretch_changed` → `viewer.set_stretch` (fits_viewer.py:364) → auto off | no |
| 3 | White | `QSlider` (:98) | "White" | same, starts 65535 | always | same | same | no |
| 4 | Midtones | `QSlider` (:99) | "Midtones" | 1-999 → 0.001-0.999, default 500 = 0.5 | always | same | same | no |
| 5 | Contrast | `QComboBox` (:112-115) | label "Contrast"; items "Linear", "Log", "Asinh" (`STRETCH_MODES` stretch.py:14-17) | Linear | always | — | same as #2 (log k = 1000, asinh k = 30, stretch.py:19-21) | no |
| 6 | Rotation | `QComboBox` (:117-125) | label "Rotation"; items "Auto (landscape)", "0°", "90°", "180°", "270°"; tooltip "Rotate the displayed image (clockwise).\nAuto turns portrait frames landscape. Display only — saved FITS\nand measurements keep the sensor orientation." | from `ui.display.rotation`, default "auto" (imaging_page.py:573-575) | always | — | `_emit_rotation` :285-286 → Observe `_on_rotation_changed` imaging_page.py:725-727 (`viewer.set_rotation` + `config.set`); Frame Viewer `viewer.set_rotation` only (analysis_window.py:294) | Observe: `ui.display.rotation` (saved by the Shell on close); Frame Viewer: not saved (P12) |
| 7 | Auto stretch | `design.PrimaryButton` (:128-131) | "Auto stretch"; tooltip "Automatically set a display stretch for the current image" | — | always | — | `auto_requested` → `viewer.auto_stretch` (fits_viewer.py:370-375): auto back on for every frame; levels re-synced (`set_levels` :230-236) | no |
| 8 | Crosshair | `QCheckBox` (:134-137) | "Crosshair on image" | off | always | — | `crosshair_toggled` → `viewer.set_crosshair_enabled` (fits_viewer.py:453-458): lines follow the cursor, never at rest | no |
| 9 | Saturation | `QCheckBox` (:138-140) | "Highlight saturation" | off | always | — | Observe `_on_saturation_toggled` imaging_page.py:721-723 / Frame Viewer `_on_saturation` analysis_window.py:457-459 → `viewer.set_saturation(on, camera.full_well_adu or 60000)` (fits_viewer.py:377-380, :347-358) | no |
| 10 | Region statistics | `QCheckBox` (:141-144) | "Region statistics (drag the box on the image)" | off | Observe only (`show_roi`) | — | `roi_toggled` → `viewer.set_roi_enabled` (fits_viewer.py:386-395): adds/removes the box (E5); off emits `None` (grid shows "—") | no |
| 11 | Loupe | `QCheckBox` (:147-150) | "Loupe (100% zoom at cursor)"; tooltip "Magnified 1:1 inset for fine manual focus" | off | always | — | `loupe_toggled` → `viewer.set_loupe_enabled` (fits_viewer.py:862-865) | no |
| 12 | WCS grid | `QCheckBox` (:153-157) | "WCS grid overlay"; tooltip "RA/Dec grid + field centre — needs a plate-solve first" | disabled until a solve (`set_astrometry_available` :259-261, imaging_page.py:1398); ticked to match the chip at solve (:1399) | Observe; hidden in the Frame Viewer (analysis_window.py:292) | — | `astrometry_toggled` → `viewer.set_astrometry_enabled`; duplicate of 1.4 #7, never re-synced (P3) | no |
| 13 | Star aperture (slider) | `design.SliderSpin` slider (:163-170) | label "Star aperture"; tooltip "Aperture radius for FWHM/HFD measurement (green plane px).\nSmaller = tight on the core; larger = more wings (tune per seeing)." | 2-30 green px, step 1, default 5 (`DEFAULT_STAR_RADIUS`, metrics.py:37) | always | — | `star_radius_changed` → Observe `_on_star_radius` imaging_page.py:786-791 (`PreviewProcessor.set_radius` preview_processor.py:121-123, re-process the last frame: detection radius for Statistics FWHM/ecc and HFD history, and the click measurement radius); Frame Viewer `_on_radius` analysis_window.py:433-435 | no (P26) |
| 14 | Star aperture (spin box) | `QSpinBox` inside `SliderSpin` (design.py:217-239) | suffix " px" | same | always | ↑/↓ | same | no |

Displayed data:

| Element | Source / format | Refresh |
|---|---|---|
| R, G, B histograms | `channel_histograms` on the raw CFA (stretch.py:170-192; G = (G1+G2)>>1), bins snapped to the ADU quantization grid (stretch.py:91-167), 128 target bins, `log1p` counts (:221-224) | every processed frame |
| ROI statistics (Observe) | section "ROI statistics": Mean `.0f`, Median `.0f`, Std `.1f`, N int, Min `.0f`, Max `.0f`, all "—" when off (:172-197, :238-257); computed on the display array (P4) | ROI move and every frame |

Implicit behaviours: `set_histogram` re-ranges Black/White to [min, p99.8] each frame
(:210-224); `set_levels` moves the sliders without emitting (`_guard`, :230-236); any slider
or the Contrast combo switches the viewer to manual, invisibly (P13). No level value is
displayed as a number.

Messages: none. Problems: P3, P4, P5, P8, P13, P14, P20, P26, P30.

### 1.6 Star info card (`StarInfoCard`, star_info_card.py:21, floating on-image card, Observe only, non-modal)

- Purpose: show what was clicked (catalogue identity, coordinates, magnitudes or the
  measured profile) and assign the photometric role. The page owns the hit-test and the
  target set; the card is display plus buttons (:1-8).
- Look: `BG2` background, `ACCENT` 1 px border, 4 px radius (:42-45); min 240×120 (:37);
  frame tooltip "Drag the title to move this panel. Drag its lower-right corner to resize
  it." (:39-41). Title 12 px semibold; body mono 11 px plain text, word-wrapped (:51-74).

| # | Control | Qt type | Label / tooltip (exact text) | Default | Enabled or visible when | Shortcut | Action: handler file:line → effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Title (drag handle) | `QLabel` + event filter (:51-58, :147-161) | title text (see flows); tooltip "Drag to move this panel"; size-all cursor | anchored bottom-left (12, h − card − 12) (:135-141) | card shown | — | drag moves the card, clamped to the viewer (:189-236); after a drag the position is kept (`_user_positioned`) and re-clamped on page resize (imaging_page.py:2881-2884) | session only |
| 2 | Resize grip | lower-right 16 px zone (:163-180, :225-227) | cursor "size F-diag" | — | card shown | — | drag resizes (min 240×120, clamped, :211-218); later contents no longer auto-size (:130-131) | session only |
| 3 | Close | `QPushButton` (:59-64) | "×"; tooltip "Dismiss" | — | card shown | — | `_on_close` :238-240 → hide + `cleared` → `_on_card_cleared` imaging_page.py:2042-2046 (clear ring and pending star) | — |
| 4 | Target | `QPushButton` (:79-97) | "Target"; "Variable star whose brightness you are measuring" | — | `roles_enabled` (catalogue pick or solved field) | — | `role_selected("target")` → `_on_card_role` imaging_page.py:2021-2030: `TargetStar(role, **pending)`; `camera_dock.set_object_name_if_empty(name)` (camera_dock.py:321); `engine.set_target_role` (acquisition_engine.py:1024-1031: replace by key, **auto-select VSP comparisons when the set has none** :1077, save targets.json, reset the tracker, emit `targets_changed`) | targets.json (per object) |
| 5 | Comparison star | `QPushButton` | "Comparison star"; "Reference star used to calibrate differential magnitudes" | — | same | — | same with role "comparison" | targets.json |
| 6 | Check star | `QPushButton` | "Check star"; "Expected-constant star measured against the comparison ensemble to verify it" | — | same | — | same with role "check" | targets.json |
| 7 | Remove | `QPushButton` (:100-104) | "Remove"; "Drop this star from the target set" | hidden | the clicked star is already in the set (computed once at show time, imaging_page.py:996-1005) | — | `remove_selected` → `_on_card_remove` imaging_page.py:2032-2040: `engine.remove_target(key)` (acquisition_engine.py:1235-1240), hide card, clear selection | targets.json |
| 8 | Dismiss | `QPushButton` (:105-109) | "Dismiss"; "Close this card (keeps the target set as is)" | — | card shown | — | emits `cleared` only → `_on_card_cleared` clears the ring and the pending star but **never hides the card** (P7) | — |

Click hit-test that feeds the card (`_on_star_clicked` imaging_page.py:793-967). Tolerance:
max(6, 14 × green_w / display_w) green px, i.e. 14 **image** px (`_nearest` :969-983, P9).
Identification does not depend on layer visibility (:800-801). Order and card title:

| Order | Source | Card title (exact) | Body (main lines) | Ring radius | Roles | file:line |
|---|---|---|---|---|---|---|
| 1 | Selected set | `Target · {display_name}` (the role is in the body) | `role {role}  ·  source {source}`, magnitudes, RA/Dec | photometry aperture | yes | :802-818, :1223-1228 |
| 2 | VSX variable | `Variable · {name}` | `type {t}  (suspected)`, `max {m}  min {m}`, `period {p} d`, `AUID {a}`, RA/Dec | photometry aperture | yes | :820-836, :1188-1204 |
| 3 | VSP reference | `VSP reference · {auid}` | `AAVSO VSP reference  {auid}`, `Gaia DR3 source  {id}`, band mags, `VSP chart code {l}  (magnitude code, not a name)`, RA/Dec | photometry aperture | yes | :838-855, :1206-1221 |
| 4 | SIMBAD object | `Identified object · {name}` | SIMBAD tooltip text | photometry aperture | yes | :857-873, :1940-1949 |
| 5 | Bundled deep-sky | `Deep-sky object · {name}` | `Argos Essential Catalogue` text | photometry aperture | yes | :875-891, :1930-1938 |
| 6 | Exoplanet host | `Exoplanet host · {host}` | `Prepared exoplanet host` text | photometry aperture | yes | :893-909, :1963-1975 |
| 7 | Gaia star | `Identified star · {name}` or `Gaia DR3 · {source_id}` | `Name`, `Object type`, `Gaia DR3 source`, `Gaia G/BP/RP magnitude`, RA/Dec, `Sources  Gaia DR3 · SIMBAD` | photometry aperture | yes | :911-941, :1904-1924 |
| 8 | Earlier point identity | `Identified star · {name}` / `Identified object · {name}` | `Source`, `Object type`, `Gaia DR3 source`, mags, RA/Dec, `WCS match offset  {s}″` | photometry aperture | yes | :945-949, :1157-1186 |
| 9a | Unmarked, field solved | `Identifying catalogue source…` then the result | `Point lookup within 10″` / RA Dec / `Gaia astrometry · SIMBAD identity` | photometry aperture | no while running | :951-958, :1036-1082 |
| 9b | Unmarked, not solved, star measured | `Manual image measurement` | `No loaded catalogue marker. Gaia/SIMBAD point identification is available.` + `_format_star_text` (FWHM/HFD in ″, ecc, SNR, peak; mount field centre or `scale … (mount not connected)`; `catalogue identifier   identify the field first`) | **star aperture** (P8) | no (no RA/Dec) | :960-967, :1008-1034, :1257-1284 |
| 9c | Unmarked, nothing measurable, not solved | card hidden, selection cleared | — | — | — | :960-965 |

Every catalogue card body ends with `Photometry aperture {r:.1f} green px` (:1000-1004).

Point identification (`PointIdentityWorker`, object_resolver_worker.py:66, cone 10″, Gaia
if `catalog.field_stars_enabled`, SIMBAD if `catalog.named_objects_enabled`, SIMBAD network
if `catalog.named_objects_allow_network`, imaging_page.py:1066-1082):

| Outcome | Card | Log (exact) | file:line |
|---|---|---|---|
| Another lookup running | unchanged, click ignored | INFO `Point identification already in progress; wait for its result.` | :1038-1042 (P10) |
| Match | identity card (row 8), identity cached for later clicks and drawn in its layer | OK `Point identified: {name} ({source}, offset {s:.1f}″).` | :1107-1131 |
| No match, star measured | `Manual image measurement` with `No Gaia or SIMBAD source matched within 10″.` | INFO `Point identification: no catalogue match within 10″.` | :1090-1095, :1104 |
| No match, nothing measured | `No catalogue match` / `No measured stellar centroid or Gaia/SIMBAD identity was found within 10″.` | same | :1096-1104 |
| Failure, star measured | `Manual image measurement` with `Point catalogue lookup unavailable.` | WARN `Point identification: {message}` | :1133-1148 |
| Failure, nothing measured | `Point identification unavailable` / `{message}` | same | :1140-1148 |

Role and removal logs: OK `{Role}: {display_name}` (:2030); OK
`Removed from target set: {display_name}` (:2038).

Implicit behaviours: a pinned field star is re-measured on every frame with a 2 px snap
(`TRACK_SNAP_SEARCH`, metrics.py:45; imaging_page.py:1230-1246) so the ring follows drift; a
change of the photometry geometry redraws the ring of a catalogue pick (:2152-2165); the
card hides when the green geometry changes (:737-742).

Problems: P7, P8, P9, P10, P17, P20, P21.

### 1.7 Statistics card (`StatisticsDock`, statistics_dock.py:22, dock "Image statistics", Observe only, non-modal)

- Purpose: the full set of whole-frame numbers on demand (:1-13). No control.

| # | Readout (label exact) | Format | Source (computed off the UI thread) | file:line |
|---|---|---|---|---|
| R1 | Mean | `.1f` | `raw.mean()` | :73; preview_processor.py:100 |
| R2 | Median | `.0f` | `np.median(raw)` | :74; preview_processor.py:83 |
| R3 | StdDev | `.1f` | `raw.std()` | :75; preview_processor.py:84 |
| R4 | MAD | `.1f` (raw MAD, not σ) | median of abs deviation | :76; preview_processor.py:85 |
| R5 | Min | int | `raw.min()` | :77; preview_processor.py:98 |
| R6 | Max | int | `raw.max()` | :78; preview_processor.py:99 |
| R7 | #Stars | int | `frame_metrics.star_count`: 3×3 local maxima above 5 σ on the green plane (metrics.py:146-155, :377-389) | :79 |
| R8 | HFD | `{:.2f} px` or "—" | `compute_hfd`: HFD of the **brightest pixel's** star (debayer.py:284-322) | :80 |
| R9 | FWHM | `{:.2f} px` or "—" | `detect_stars(radius = star aperture).mean_fwhm` over ≤ 120 stars (metrics.py:158) | :81-82 |
| R10 | Eccentricity | `.3f` or "—" | `detect_stars.mean_eccentricity` | :83-84 |
| R11 | Bit depth | `{n}-bit` | dtype width × 8 (preview_processor.py:86): always "16-bit" (P16) | :85 |

Refresh: every processed frame (imaging_page.py:747). `clear()` (:87-90) is never called
(P15). Problems: P15, P16, P29.

### 1.8 Same widgets, two hosts: Observe vs Frame Viewer

| Behaviour | Observe (imaging_page.py) | Frame Viewer (analysis_window.py) |
|---|---|---|
| Default Preview | Colour (CFA) (:166) | Raw CFA, forced on each load (:333-334) |
| Palette | not connected (P1) | works on mono views (:281) |
| Rotation | saved to `ui.display.rotation` (:725-727) | applied, not saved (:294) |
| Region statistics | available (`show_roi=True`) | absent (`show_roi=False`, :195) |
| WCS grid checkbox | shown, duplicate of the chip | hidden (:292) |
| Click hit-test | all layers, visible or not (:800-801) | **visible** layers only (:929-931) |
| Click result | on-image info card with roles | text in the "Frame · selected star" tab, no roles (:948-981) |
| VSP references | hidden by default, only near detected sources (:1684-1696, :1735-1739) | shown by default, all (:523-529, :804-816) |
| G limit slider | debounced 75 ms (:1445) | re-projects on every step (:579-581) |
| Processing | worker thread, latest-wins (preview_processor.py:112-150) | synchronous on the UI thread (:418-427) |

### 1.9 Problems found (consolidated)

| Id | Problem | Evidence |
|---|---|---|
| P1 | The Palette combo is dead on Observe: `palette_changed` is never connected. | image_toolbar.py:91-93; imaging_page.py:552-553 (only channel and open are wired); only analysis_window.py:281 connects it |
| P2 | Palettes are silently inert on any RGB image: in the Colour (CFA) view, and in every view while "Highlight saturation" is on (it converts the image to RGB). pyqtgraph applies a LUT to single-channel images only. | fits_viewer.py:326-327, :352-357; pyqtgraph ImageItem.py:520-528 |
| P3 | Two controls for the WCS grid ("Coordinate grid" chip and "WCS grid overlay" checkbox) drive the same setter and are only synced at solve time: toggling one leaves the other wrong. | overlay_bar.py:32; histogram_dock.py:153-157; imaging_page.py:569, :1399, :1411 |
| P4 | The pixel readout (labelled "ADU") and the ROI statistics read the **display** array: in Colour (CFA) view these are background-neutralised RGB values (gains 0.25-4), averaged over channels for the ROI; in R/G/B views, CFA-cell values. Not raw ADU. | fits_viewer.py:411-414, :436-440; preview_processor.py:68-70; debayer.py:186-202 |
| P5 | The saturation test compares the display array (neutralised RGB, max over channels) to a raw-ADU full-well threshold: gains up to ×4 make colour-view clipping wrong. | fits_viewer.py:347-351; imaging_page.py:721-723 |
| P6 | Night Red is not honoured by the viewer: no red tint of the image; ROI pen hard-coded yellow `"y"`; saturation is pure red (invisible against a red image); Fire/Ice emit blue, green and yellow; pens baked at build time ignore a live theme change. | fits_viewer.py:388, :357, :339-344, :147-201; theme.py:14-17 |
| P7 | "Dismiss" does not close the card: it only emits `cleared`, whose handler clears the ring and the pending star. The card stays, and its role buttons then silently do nothing. | star_info_card.py:105-109; imaging_page.py:2022-2023, :2042-2046 |
| P8 | One ring, two meanings: catalogue picks are ringed with the photometry aperture (and the card says "Photometry aperture … green px"); measured field stars with the focus "Star aperture". | imaging_page.py:991-1004 vs :1019-1023; histogram_dock.py:163-170 |
| P9 | Hit tolerance is 14 image px, not screen px: about 7 screen px at fit (≈0.5×), 56 screen px at 4×. | imaging_page.py:973-975; analysis_window.py:934-936 |
| P10 | While a point lookup runs (up to ~35 s: Gaia 20 s + SIMBAD 15 s), every new click is ignored with only a log line. | imaging_page.py:1038-1042, :2874-2875 |
| P11 | The Gaia G limit is saved only on handle release: keyboard, wheel or groove clicks change the display but are not persisted. | overlay_bar.py:107-110; imaging_page.py:1447-1450 |
| P12 | Observe and Frame Viewer disagree (1.8): hit-test visibility rule, VSP default and filtering, rotation persistence, default Preview, palette wiring. | see 1.8 |
| P13 | Auto/manual stretch state is invisible; touching any slider or the Contrast combo silently freezes the levels. Black/White sliders are clamped to [min, p99.8] each frame, so a white level above the 99.8th percentile is impossible and `set_levels` clamps auto values silently; no numeric level readout. | fits_viewer.py:364-368; histogram_dock.py:210-236 |
| P14 | Same icon, label and shortcut, different tool: the Qt crosshair follows the cursor; the web crosshair is a fixed reticle at the image centre. | fits_viewer.py:428-432, :453-458; web/src/lib/viewer/FitsViewer.svelte:52-53, :452-464 |
| P15 | Dead code and doc drift: `FitsViewer.reset()` and `StatisticsDock.clear()` never called; the docstring announces a `pixel_info` signal that does not exist; "star/FWHM overlay" section without a star overlay; the comparison item documented as "hollow cyan squares" but drawn as `+`; `_comp_labels` never filled; catalogue item built at size 28, drawn at 30. | fits_viewer.py:967, :10, :461, :228-229, :789, :764-768, :205/:651; statistics_dock.py:87 |
| P16 | "Bit depth" shows the dtype width (always "16-bit") while the Seestar ADC is 12-bit left-shifted (16 ADU steps). | preview_processor.py:86; stretch.py:91-110 |
| P17 | FWHM/HFD in arcseconds use the nominal hardware plate scale even after a solve measured the real one; the mount field centre is printed in decimal hours/degrees, against the sexagesimal convention. | imaging_page.py:1257-1276; metrics.py:48-61 |
| P18 | Marker collisions: "Other objects" and "Stars" are both `FG_MUTED` circles (24 vs 18 px); `CYAN` serves galaxies, VSP candidates and selected comparisons; `VARIABLE` #8fb7ca vs `CYAN` #7da8b2 are near-identical blues; exoplanets use a five-point star (banned by BRAND 6.8); the check triangle points down while the icon points up. All collapse to one hue in Night Red. | fits_viewer.py:208-224, :230-232, :803-807; palettes.py:86, :90 |
| P19 | The WCS grid is drawn in brass `ACCENT`, which BRAND reserves for selection; tokens map the grid to `--cyan`. | fits_viewer.py:194-196, :543; tokens.css `--overlay-grid` |
| P20 | Histogram colours: B is drawn in brass `ACCENT`, R in muted `DANGER`, G in `SUCCESS`; all three are reds in Night Red. | histogram_dock.py:85-87 |
| P21 | The viewer's selection label and the info card are both anchored bottom-left and overlap when a Photometry row is focused while a card is open. | fits_viewer.py:914; star_info_card.py:139; imaging_page.py:2071-2077 |
| P22 | Sub-pixel convention mix **(uncertain)**: pyqtgraph image coordinates put pixel k on [k, k+1) while catalogue and centroid positions are numpy pixel centres; `display = 2 × green` and the integer `_unrot_pt` formulas applied to continuous click positions leave markers and clicks up to about one sensor pixel (≈ 3.7″) off at high zoom. | fits_viewer.py:271-291, :495, :645, :876-881; imaging_page.py:1286-1302 |
| P23 | Double-click probably emits a second `star_clicked` (pyqtgraph double-click event, `ev.double()` not filtered): a duplicate measurement or a spurious "already in progress" log **(uncertain)**. | fits_viewer.py:867-881; GraphicsScene.py:245-248 |
| P24 | Frame Viewer: "Open image…" on an unreadable file fails silently (`load()` result ignored). | analysis_window.py:444-445 |
| P25 | The pyqtgraph context menu exposes "Invert Axis" (silent mirror image, East/West flip risk), manual axis ranges and "1 button" mouse mode: library defaults, never designed for ARGOS. | fits_viewer.py:138-141; ViewBoxMenu.py:25-64 |
| P26 | Nothing in the image tools is remembered except rotation (Observe) and the G limit: Preview, palette, crosshair, saturation, region box, loupe, star aperture all reset at launch. | histogram_dock.py:134-170; image_toolbar.py:69 |
| P27 | Label de-overlap uses 150×42 **image-px** cells: at fit zoom (≈0.5×) the cells are ~72×20 screen px, smaller than an 18-character label, so labels overlap; at high zoom they are sparse. Target/check labels bypass the slot check. | fits_viewer.py:613-620, :854 |
| P28 | The loupe is a fixed 4× (42 → 168 px) of the 8-bit stretched image; it cannot show raw values and its size ignores HiDPI. | fits_viewer.py:35-37, :923-954 |
| P29 | Statistics mixes populations: "#Stars" counts all 5 σ local maxima (hot pixels included), "HFD" is the brightest pixel's star only, "FWHM"/"Eccentricity" average the ≤ 120 detected stars. Labels do not say so; HFD/FWHM units are green px without saying it. | metrics.py:146-158, :377-389; debayer.py:284-322 |
| P30 | Info-card styling: the `QFrame { border… }` selector also matches the child `QLabel`s, so the title and body are boxed in brass (confirmed on an offscreen grab). | star_info_card.py:42-45 |
| P31 | After a role is assigned the card is not refreshed: "Remove" stays hidden until the star is clicked again; disabled role buttons (unsolved field) keep their role tooltip instead of saying why. | star_info_card.py:126-129; imaging_page.py:996-1005, :1029-1033 |

### 1.10 Completeness check

Re-scan of the six files for `QPushButton`, `QToolButton`, `QAction`, `QCheckBox`,
`QRadioButton`, `QComboBox`, `QSpinBox`, `QDoubleSpinBox`, `QSlider`, `QLineEdit`, `QMenu`,
`QMessageBox`, `QFileDialog`, `QDialog`, `QTabWidget`, `QTableWidget`, `setShortcut`, plus
`SliderSpin`, `PrimaryButton`, `PlotWidget` and `RectROI`:

| Hit | Inventory row |
|---|---|
| image_toolbar.py:51 `QPushButton("Open image…")` | 1.3 #1 |
| image_toolbar.py:57 / :80 `QComboBox` | 1.3 #2 / #3 |
| overlay_bar.py:142 `QPushButton(text)` × 10 | 1.4 #1-#10 |
| overlay_bar.py:98 `QSlider` | 1.4 #11 |
| overlay_bar.py:120 `QToolButton` | 1.4 #12 |
| histogram_dock.py:75 `PlotWidget` | 1.5 #1 |
| histogram_dock.py:97-99 `_slider` (`QSlider`, :200-204) × 3 | 1.5 #2-#4 |
| histogram_dock.py:112 / :117 `QComboBox` | 1.5 #5 / #6 |
| histogram_dock.py:128 `PrimaryButton` | 1.5 #7 |
| histogram_dock.py:134, :138, :142, :147, :153 `QCheckBox` | 1.5 #8-#12 |
| histogram_dock.py:163 `SliderSpin` (slider + `QSpinBox`) | 1.5 #13-#14 |
| fits_viewer.py:388 `RectROI` | 1.1 #9-#10 |
| star_info_card.py:59 `QPushButton("×")` | 1.6 #3 |
| star_info_card.py:92 `QPushButton(text)` × 3 | 1.6 #4-#6 |
| star_info_card.py:100 / :105 `QPushButton` | 1.6 #7 / #8 |

No `QAction`, `QRadioButton`, `QLineEdit`, `QMenu`, `QMessageBox`, `QFileDialog`, `QDialog`,
`QTabWidget`, `QTableWidget` or `setShortcut` in the six files: the file dialog (E11), the
catalogue dialog (E12), the Frame Viewer tabs and the File menu shortcut live in the hosts
and are cited where used. The pyqtgraph context menu (1.2) is inherited, not constructed.

Control count: 1.1 = 10, 1.2 = 5, 1.3 = 3, 1.4 = 12, 1.5 = 14, 1.6 = 8, 1.7 = 0 (11
readouts): **52**.

---

## 2. Web redesign

### 2.1 Placement in the new information architecture

**Baseline: what the web viewer already does** (`web/src/lib/viewer/*`,
`web/src/lib/imaging/{ImagingScreen,ImagingToolbar,StretchCard,Histogram}.svelte`,
`web/src/lib/shell/StatusBar.svelte`):

| Capability | Web today | Qt equivalent | Gap |
|---|---|---|---|
| 16-bit GPU display, stretch in shader | yes (renderer.ts, shaders.ts) | `apply_stretch` | none (byte-exact port, stretch.test.ts) |
| Auto stretch, manual levels | yes, A toggles auto, Auto/Manual badge, sliders + number fields with an exponential slider map (levels.ts) | Auto button, three sliders, no numbers | web is better (fixes P13) |
| Transfer Linear/Log/Asinh, reset | yes (Segmented; Shift+A) | Contrast combo | none |
| Rotation auto/0/90/180/270 | yes, persisted per viewer (`argos.rotation`) | combo, config key | none |
| Histogram | pooled channels, log axis, B/M/W marks, hover readout, caption median/MAD/max | R/G/B curves, no level marks | **missing per-CFA-channel curves** |
| Pan / zoom | left or middle drag; wheel and pinch about the cursor, clamped; double-click fit; + − F 1; zoom % | drag, wheel, right drag, unlimited | right-drag zoom intentionally absent |
| Pixel readout | status bar X, Y, raw value | in-image label, display value | web is better (raw value, fixes P4 for the readout) |
| Crosshair | fixed reticle at the image centre (X) | cursor-following lines | **semantics differ (P14)** |
| Night Red | image drawn as v × `--viewer-tint` (#d80000) | not handled | web is better |
| Overlay API | `overlay` snippet in frame px, rotation applied (types.ts:13-27) | per-layer setters | **no layer drawn yet** (only the frame outline) |
| Click to select / measure, info card, roles | — | yes | **missing** |
| WCS grid, centre label, target reticle | — | yes | **missing** |
| Catalogue layers, labels, hover tooltips, G limit | — | yes | **missing** |
| Loupe | — | yes | **missing** |
| Saturation highlight | — | yes | **missing** |
| False-colour palettes | — | yes (half broken, P1/P2) | **missing** |
| Region statistics | — | yes | **missing** |
| CFA preview (Colour/Raw/R/G/B) | raw mosaic shown as mono (README "Known limits") | yes | **missing** |
| Whole-frame statistics card | caption only (median, MAD, max) | 11 values | **missing** std, star count, HFD, FWHM, ecc, ADC depth |
| Star aperture radius | — | yes | **missing** |
| Open image | client has `openFits` (api/client.ts), no button | toolbar + File menu | **missing control** |
| Context menu | none | pyqtgraph defaults | **to design** |

**Placement:**

| Qt element | Section → screen → region | Why |
|---|---|---|
| E1 canvas (Observe) | Observe → main → centre stage (existing `FitsViewer.svelte`, extended) | one viewer component |
| E1 canvas (Frame Viewer) | Review → frame inspector → centre stage, same component in `mode="inspect"` (no roles, results in the inspector's side panel) | one vocabulary everywhere; the Review spec owns that screen |
| E2 context menu | Observe/Review → viewer → ARGOS context menu (right-click, Shift+F10, Menu key) | replace library defaults by task actions |
| E3 pixel readout | status bar (exists) + RA/Dec under the cursor when solved | keeps the image clear; BRAND 11 asks for cursor RA/Dec |
| E3 centre label | viewer HUD chip row (top-left, after the frame chips), shown with the grid | BRAND 11.1: chips in a corner, no reserved band |
| E3 loupe | viewer inset, top-right | same as Qt; never under the HUD chips |
| E3 selection ring | viewer overlay, `--accent` (brass = the selected object) | BRAND 3 |
| E3 selection label | dropped as a separate element: the info card or a ring label carries it | removes P21 |
| E4 marker tooltip | viewer hover popover (tokens, mono) | same content |
| E5 region box | viewer overlay, results in a chip next to the box and in the Statistics card | results where the eye is |
| E6 Open image | Observe toolbar, acquisition group (`open-image`, ⌘/Ctrl+O) | one-step offline replay |
| E6 Preview, Palette | Observe rail → Display card → "View options" disclosure | display mapping lives with the stretch |
| E7 overlay bar (2 rows, ≤ 76 px) | Observe toolbar: `sky-grid` and `labels` toggles + `catalogue` popover "Field overlays" (10 layer rows with counts, G limit, catalogue settings link) | reclaims ~76 px for the image (BRAND 11.1); the two most used toggles stay one click away |
| E7 "Catalogues / depth…" | popover footer link → Settings ▸ Catalogues (opened as a sheet over Observe, Settings spec) | point of use kept, settings owned by Settings |
| E8 histogram, levels, transfer, rotation, auto | Observe rail → Display card (existing `StretchCard`, extended) | exists |
| E8 crosshair, saturation, region, loupe | Observe toolbar, new "Inspect" group, icon-only toggles | frequent and reversible (BRAND 7) |
| E8 WCS grid checkbox | merged into the toolbar `sky-grid` toggle | duplicate (P3) |
| E8 star aperture | Observe rail → Statistics card ("Stars" block) | it defines the FWHM/HFD shown there |
| E8 ROI statistics grid | Statistics card "Region" block + on-image chip | |
| E9 star info card | Observe → viewer overlay, bottom-left, draggable | same as Qt, fixed bugs |
| E10 statistics | Observe rail → Statistics card, hidden by default, toggled by `statistics` (I) like H toggles Display | Qt hides it by default too |
| E11 file dialog | Tauri native open dialog (browser: path field fallback until Tauri) | `open-fits` takes an absolute path |
| E12 catalogue settings | Settings spec | — |

Rail order (BRAND 11.1, observing cards first): Connection (folds when connected) →
Camera → Display → Statistics (when shown, folded by default) → Mount.

### 2.2 Control mapping

Display: `icon` = icon-only with tooltip (label + shortcut); `icon+label`; `label` = text.
Shortcuts marked *(proposed)* are new; all others exist in the web UI or the inventory.

| Qt ref | Web control | Decision | Icon id | Display | Shortcut |
|---|---|---|---|---|---|
| 1.1 #1 left click | click on the image (pointer moved ≤ 4 px, button released) → select / measure | keep | — | — | — |
| 1.1 #2 left drag | pan | keep (exists) | — | — | — |
| 1.1 #3 middle drag | pan | keep (exists) | — | — | — |
| 1.1 #4 right drag | — | **drop**: right button opens the ARGOS context menu; zoom stays on wheel, pinch, + / −, toolbar | — | — | — |
| 1.1 #5 wheel | zoom about the cursor, clamped (view.ts) | keep (exists) | — | — | Ctrl+wheel / pinch |
| 1.1 #6 double click | fit to window (exists); never re-selects | **drop** the Qt side effect (P23) | — | — | — |
| 1.1 #7 hover readout | status bar X / Y / Value (raw ADU, exists) + RA / Dec when solved | move | — | label | — |
| 1.1 #8 marker hover | hover popover with the marker's identity text; marker stroke thickens | keep | — | — | — |
| 1.1 #9 drag region box | drag inside the box moves it | keep | `region-stats` | — | — |
| 1.1 #10 resize region box | four corner handles; Shift+drag on the image draws a new box | keep (extended) | — | — | Shift+drag |
| 1.1 keyboard | arrow keys nudge the region box only while it has focus (never jog) | new, focus-scoped | — | — | ← ↑ → ↓ (focus) |
| 1.2 #1 View All | context menu "Fit to window" | merge (= toolbar `zoom-fit`) | `zoom-fit` | label | F |
| 1.2 #2 X axis ▸ | — | **drop**: library default; "Invert Axis" silently mirrors the sky (P25) | — | — | — |
| 1.2 #3 Y axis ▸ | — | **drop**: same | — | — | — |
| 1.2 #4 Mouse Mode ▸ | — | **drop**: one pointer grammar; trackpad pinch covers single-button use | — | — | — |
| 1.2 #5 Export... | context menu "Save view as PNG…" (canvas + overlays, at screen resolution) | keep, reduced to PNG (open question Q9) | `export` (16 px, menu) | label | — |
| 1.3 #1 Open image | toolbar button → native file dialog → `POST /api/camera/open-fits` (must ingest, 2.5 A13) | move | `open-image` | icon | ⌘O / Ctrl+O |
| 1.3 #2 Preview | Display card ▸ View options: Segmented "Colour · Raw · R · G · B"; row hidden for mono frames (frame `bayer` null) | move | — | label | — |
| 1.3 #3 Palette | Display card ▸ View options: Segmented "Neutral · Negative · Fire · Ice"; works for every Preview and with saturation on (fixes P1, P2); Night Red: Fire and Ice disabled, reason "Night Red shows the image in red only" | move | — | label | — |
| 1.3 caption | text moves to the Preview and Palette tooltips: "Display only: FITS data and measurements are unchanged." | **drop** as a permanent label (space) | — | — | — |
| 1.4 #1 Stars | popover row (toggle + count) | move | `field-stars` | icon+label row | — |
| 1.4 #2 Variables | popover row | move | `variable-star` | icon+label row | — |
| 1.4 #3 Galaxies | popover row | move | `galaxy` | icon+label row | — |
| 1.4 #4 Nebulae + clusters | popover row | move | `nebula` | icon+label row | — |
| 1.4 #5 Exoplanets | popover row | move | `exoplanet` | icon+label row | — |
| 1.4 #6 Other objects | popover row | move | `other-objects` | icon+label row | — |
| 1.4 #7 Coordinate grid | toolbar toggle (also a popover row, same state) | keep, single source of truth | `sky-grid` | icon | G |
| 1.4 #8 VSP references | popover row; default off, only sources detected in this frame (Observe rule, Q7) | move | `comparison-star` | icon+label row | — |
| 1.4 #9 Selected stars | popover row; auto-on when the set has on-frame stars | move | `target-star` | icon+label row | — |
| 1.4 #10 Labels | toolbar toggle (also a popover row); default off | keep | `labels` | icon | L *(proposed)* |
| 1.4 #11 Gaia G limit | popover slider 5.0-max + number field `≤ 16.5`; filters client-side (per-star `g_mag`); saved on commit from **any** input (fixes P11) | move | — | label | — |
| 1.4 #12 Catalogues / depth | popover footer link "Catalogue sources & depth…" → Settings ▸ Catalogues sheet (text only: the popover trigger already carries the `catalogue` glyph) | move | — | label | — |
| (new) popover trigger | toolbar button "Field overlays", badge = shown/available layers | new (replaces the bar) | `catalogue` | icon | O *(proposed)* |
| 1.5 #1 histogram | Display card histogram (exists) + R / G / B curves when the frame is a CFA mosaic (solid / dashed / dotted, so Night Red stays readable); pyqtgraph pan/zoom/menu **dropped** (fixed range, hover readout) | keep | `histogram` | — | H (card) |
| 1.5 #2 Black | slider + number (exists) | keep | — | label | — |
| 1.5 #3 White | slider + number (exists); range up to the frame max (fixes P13) | keep | — | label | — |
| 1.5 #4 Midtones | slider + number (exists) | keep | — | label | — |
| 1.5 #5 Contrast | "Transfer" Segmented (exists) | keep | — | label | — |
| 1.5 #6 Rotation | Segmented, moved into "View options" | keep | — | label | — |
| 1.5 #7 Auto stretch | toggle in toolbar and card (exists) | keep | `stretch-auto` | icon (toolbar) / icon+label (card) | A |
| (web) Reset | exists | keep | `stretch-reset` | icon / icon+label | Shift+A |
| 1.5 #8 Crosshair | toolbar toggle (exists) + "Crosshair: Centre · Cursor" in View options (Q1) | keep, both behaviours offered | `crosshair` | icon | X |
| 1.5 #9 Highlight saturation | toolbar toggle; threshold `camera.full_well_adu` shown in the tooltip ("Highlight clipped pixels (≥ 60 000 ADU)") and in View options; tested on **raw** samples in the shader (fixes P5) | move | `saturation` | icon | C *(proposed)* |
| 1.5 #10 Region statistics | toolbar toggle; box appears at its last place (else centred, 80×80 frame px) | move | `region-stats` | icon | R *(proposed)* |
| 1.5 #11 Loupe | toolbar toggle | move | `loupe` | icon | Z |
| 1.5 #12 WCS grid checkbox | — | **merge** into `sky-grid` (duplicate, P3) | `sky-grid` | — | G |
| 1.5 #13-14 Star aperture | Statistics card number field 2-30 px (green), stepper | move | — | label | — |
| 1.6 #1 title drag | drag the card header; position remembered per viewer | keep | — | — | — |
| 1.6 #2 resize grip | — | **drop**: the card sizes to structured rows; long values truncate with a tooltip | — | — | — |
| 1.6 #3 × | close button in the header | keep | `close` | icon | Esc (Q10) |
| 1.6 #4 Target | role button | keep | `target-star` | icon+label "Target" | — (Q8) |
| 1.6 #5 Comparison star | role button | keep | `comparison-star` | icon+label "Comparison" | — |
| 1.6 #6 Check star | role button | keep | `check-star` | icon+label "Check" | — |
| 1.6 #7 Remove | button, visible when the star is in the set, updated live from the `targets` event (fixes P31) | keep | `remove` | icon+label | — |
| 1.6 #8 Dismiss | — | **merge** into × (duplicate; broken in Qt, P7) | `close` | — | — |
| 1.7 R1-R6 | Statistics card "Frame" block: Mean, Median, Std, MAD, Min, Max (raw ADU) | keep | `statistics` (card) | label | I *(proposed)* |
| 1.7 R7-R10 | Statistics card "Stars" block: Stars, HFD, FWHM, Ecc. with their population in the tooltip (P29) | keep | — | label | — |
| 1.7 R11 Bit depth | "ADC 12-bit (16 ADU steps)" from the quantization step (histogram.ts already computes it) | keep, corrected (P16) | — | label | — |
| 1.5 ROI grid | Statistics card "Region" block + on-image chip `Mean · σ · N` | move | — | label | — |

No new icon id is needed: every action maps to an existing id; Preview, Palette, Rotation,
Crosshair mode and the G limit are labelled segmented controls or sliders.

### 2.3 Wireframes (1440 × 900 reference)

**Observe, solved field, card open, loupe and region on.** Rail 420 px, sidebar 92 px,
toolbar 47 px, status bar 32 px: the viewer is 928 × 821 CSS px. Toolbar legend: `cap`
capture, `live`, `open` open-image, `z-`/`z+` zoom, `fit`, `1:1`, `sA` stretch-auto, `sR`
stretch-reset, `hist` histogram card, `xh` crosshair, `loupe`, `roi` region-stats, `sat`
saturation, `stat` statistics card, `grid` sky-grid, `lbl` labels, `cat▾` catalogue popover,
`pnl` panels, `thm` theme. Markers: `o` Gaia star, `( )` variable, `(T)` / `[ ]` / `/K\`
selected target / comparison / check, `+` VSP candidate, `<>` other object, `·` grid.

```
┌────────┬─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│(mark)  │[Disconnect] | cap live [Stop] open | z- 48% z+ fit 1:1 | sA sR hist | xh loupe roi sat stat | grid lbl cat▾          pnl thm│
│ARGOS   ├──────────────────────────────────────────────────────────────────────────────────────┬──────────────────────────────────────┤
│        │  [LIVE] [#1284] [2.0 s] [Seestar]                               ┌─ loupe 4× ──────┐  │ > Connection          (dot) Connected│
│(conn)  │  [Centre RA 05h 35m 17.3s  Dec −05° 23′ 28″]                    │        |        │  │──────────────────────────────────────│
│Connect.│ + - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - │ -------+------- │+ │ v Camera                       Live  │
│        │ |                ·  o                                           │        |        │| │   (camera card, unchanged)           │
│(eye)   │ |    o        ( )V0123                     o                    └─────────────────┘| │                                      │
│Observe │ |                          [ ]                                                     | │──────────────────────────────────────│
│        │ |            o      (T)       o                                                    | │ v Display                     [Auto] │
│(plan)  │ |   + - - - - - - +                 /K\            o                               | │  histogram  R G B   |B    M      W|  │
│Plan    │ |   |   region    |                          +                                     | │  Median 2000 · MAD 25 · max 65535    │
│        │ |   + - - - - - - +                ·                         o                     | │  Black    ──●───────────  [  1925 ]  │
│(review)│ |   [Mean 2011  σ 24.9  N 6400]        o                                           | │  Midtones ────●─────────  [ 0.180 ]  │
│Review  │ |                         o              <>                            o           | │  White    ───────────●──  [  5180 ]  │
│        │ |                      ·                                 o                         | │  Transfer [Linear | Log | Asinh]     │
│(gauge) │ | ┌─ (var) Variable · V0123 Ori ─────── (x) ─┐                   ·                 | │  > View options                      │
│Settings│ | │ Type      EA                             │  o                                  | │  [(sA) Auto stretch]  [(sR) Reset]   │
│        │ | │ Range     max 11.2 · min 12.0            │                       o             | │──────────────────────────────────────│
│        │ | │ Period    2.345 d   AUID 000-BBC-123     │         ·                           | │ > Statistics   #1284 · HFD 2.31 px   │
│        │ | │ RA / Dec  05h 35m 17.3s  −05° 23′ 28.0″  │             o            ·          | │──────────────────────────────────────│
│        │ | │ Aperture  5.0 px green (photometry)      │                                     | │ > Mount                    Tracking  │
│        │ | │ [(T) Target][(C) Comparison][(K) Check]  │     o                       o       | │                                      │
│        │ | └──────────────────────────────────────────┘                                     | │                                      │
│        │ + - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -+ │                                      │
├────────┴──────────────────────────────────────────────────────────────────────────────────────┴──────────────────────────────────────┤
│ (dot) Connected Seestar S50 | X 512  Y 1033  Value 2011 ADU | RA 05h 35m 12.1s Dec −05° 22′ 03″ | Frame #1284 | Zoom 48% | Log       │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Width check at 1440: the toolbar holds 22 controls (≈ 22 × 38 px + separators + the
"Disconnect" label ≈ 1 000 px) in 1 348 px; at 1280 it still fits (1 188 px).

**"Field overlays" popover** (anchored under `cat▾`, 320 px, `--shadow-2`, closes on Esc,
outside click or a second O):

```
┌─ (catalogue) Field overlays ───────────────────┐
│ OBJECTS                                  count │
│ [x] (field-stars)   Stars                  212 │
│ [x] (variable-star) Variables               14 │
│ [ ] (galaxy)        Galaxies                 3 │
│ [ ] (nebula)        Nebulae + clusters       1 │
│ [ ] (exoplanet)     Exoplanets               0 │
│ [ ] (other-objects) Other objects            5 │
│ DISPLAY                                        │
│ [x] (sky-grid)      Coordinate grid          G │
│ [ ] (comparison)    VSP references           9 │
│ [x] (target-star)   Selected stars           6 │
│ [ ] (labels)        Labels                   L │
│ Gaia G limit  5.0 ─────────●── 18.0 [≤ 16.5]   │
│   stars only; galaxies and nebulae unaffected  │
│ Catalogue sources & depth…  (Settings sheet)   │
└────────────────────────────────────────────────┘

┌─ (catalogue) Field overlays ───────────────────┐
│ (plate-solve) Identify the field to show       │
│ catalogue layers.          [Identify field]    │
│ ─────────────────────────────────────────────  │
│ all 10 rows shown disabled, tooltip:           │
│ "Identify the field first (S)"                 │
│ Gaia G limit  5.0 ─────────●── 18.0 [≤ 18.0]   │
│ Catalogue sources & depth…  (Settings sheet)   │
└────────────────────────────────────────────────┘
```

(`Identify field` is the plate-solve action owned by the Field/astrometry spec; it is only
linked here.)

**Star info card states** (360 px wide, `--bg-2`, 1 px `--accent` border because it
describes the selected object; structured key / value rows in mono):

```
┌─ (variable-star) Variable · V0123 Ori ───────────── (x) ─┐
│ Type      EA  (suspected)                                │
│ Range     max 11.2 · min 12.0                            │
│ Period    2.345 d                                        │
│ AUID      000-BBC-123                                    │
│ RA        05h 35m 17.3s                                  │
│ Dec       −05° 23′ 28.0″                                 │
│ Aperture  5.0 px (green, photometry)                     │
│ [(T) Target] [(C) Comparison] [(K) Check] [(-) Remove]   │
└──────────────────────────────────────────────────────────┘

┌─ (crosshair) Measured star ──────────────────────── (x) ─┐
│ No catalogue marker here · identifying (spinner)         │
│ FWHM      2.84 px · 10.6″      HFD  3.10 px · 11.6″      │
│ Ecc.      0.12        SNR 212      Peak 18 432 ADU       │
│ Sky       2 004 ADU   Star aperture 5 px                 │
│ RA        05h 35m 21.9s   Dec −05° 21′ 40.3″             │
│ [(T) Target] [(C) Comparison] [(K) Check]                │
│   disabled before a solve, tooltip:                      │
│   "Identify the field to give this star RA/Dec"          │
└──────────────────────────────────────────────────────────┘

┌─ No catalogue match ─────────────────────────────── (x) ─┐
│ No Gaia or SIMBAD source matched within 10″.             │
│ Measured star kept: FWHM 2.84 px · SNR 212               │
│ [(T) Target] [(C) Comparison] [(K) Check]                │
└──────────────────────────────────────────────────────────┘
```

**Rail cards** (Display extended; Statistics new, hidden by default; both collapsible and
remembered per viewer):

```
┌─ v (histogram) Display ─────────── [Auto] ─┐
│ 1925–1980 ADU · 3 412 px          (hover)  │
│ ┌──────────────────────────────────────┐   │
│ │ ▁▂▇█▆▃▂▁▁ ▁ ▁         R ─  G --  B ··│   │
│ │ |B   M:          W|                  │   │
│ └──────────────────────────────────────┘   │
│ Black    ──●─────────────   [  1925 ]      │
│ Midtones ────●───────────   [ 0.180 ]      │
│ White    ────────────●───   [  5180 ]      │
│ Transfer  [ Linear | Log | Asinh ]         │
│ v View options                             │
│   Preview   [Colour | Raw | R | G | B]     │
│   Palette   [Neutral|Negative|Fire|Ice]    │
│   Rotation  [Auto | 0° | 90° | 180° | 270°]│
│   Crosshair [Centre | Cursor]              │
│   Clipping  ≥ 60 000 ADU  (Settings)       │
│ [(sA) Auto stretch]   [(sR) Reset]         │
└────────────────────────────────────────────┘

┌─ v (statistics) Statistics ──────── #1284 ─┐
│ FRAME  raw ADU, all pixels                 │
│ Mean   2016.4   Median  2000   Std  31.2   │
│ MAD      25.0   Min     1814   Max 65535   │
│ ADC    12-bit (16 ADU steps)               │
│ STARS  green plane                         │
│ Stars     212   HFD  2.31 px  FWHM 2.80 px │
│ Ecc.    0.142   Star aperture [  5 ] px    │
│ REGION (R)  x 400–480 · y 900–980          │
│ Mean   2011.2   Median  2009   Std  24.9   │
│ Min      1932   Max     2104   N    6400   │
└────────────────────────────────────────────┘
```

"View options" is folded by default so the Display card keeps its current height and the
Camera and Display cards stay above the fold at 1440 × 900.

**Viewer context menu** (token-drawn, never the native menu, so Night Red holds):

```
┌───────────────────────────────────────────┐
│ Fit to window                          F  │
│ Actual pixels (1:1)                    1  │
│ ───────────────────────────────────────── │
│ Measure / identify here          (click)  │
│ Copy pixel position     x 512   y 1033    │
│ Copy RA / Dec           (when solved)     │
│ ───────────────────────────────────────── │
│ Region statistics here                 R  │
│ Clear selection                      Esc  │
│ ───────────────────────────────────────── │
│ Save view as PNG…                         │
└───────────────────────────────────────────┘
```

Review frame inspector: same viewer, toolbar groups "view", "display", "inspect" and
"field" only; a click fills the inspector's side panel instead of the card; no role buttons
(analysis_window.py:1-7 "remaining read-only"). Layout is owned by the Review spec.

### 2.4 Interaction and states

**Pointer grammar (viewer).**

| Input | Effect |
|---|---|
| Click (≤ 4 px travel) | select: hit-test markers within **10 screen px** (fixes P9), nearest wins, priority target → variable → VSP → SIMBAD → deep-sky → exoplanet → Gaia → earlier point identity → measure + point lookup (Observe order, imaging_page.py:793-967). Hidden layers still identify (Observe rule, Q6) |
| Click on empty sky, nothing measurable | clears the selection; card closes |
| Left / middle drag | pan (exists) |
| Wheel, Ctrl+wheel, pinch | zoom about the cursor (exists) |
| Double-click | fit (exists); never selects |
| Right-click / Shift+F10 / Menu | context menu (2.3) |
| Hover a marker | marker stroke +1 px at once; identity popover after ~500 ms (BRAND 7) |
| Region tool on | drag inside the box moves it; 4 corner handles resize; Shift+drag draws a new box; arrows nudge 1 frame px (Shift: 10) while the box has focus |
| Loupe on | inset follows the cursor, top-right; hides when the cursor leaves the image |
| Crosshair on | Centre (default, exists) or Cursor lines through the pointer (View options) |

**Keyboard** (single keys never fire in a text field; none moves hardware): existing E, V,
Esc, + / −, F, 1, A, Shift+A, H, X, P, F1-F5; inventory Z (loupe), G (grid), ⌘O / Ctrl+O
(open); proposed O (overlays popover), L (labels), C (saturation), R (region), I (Statistics
card). Esc keeps its safety meaning: it always aborts a slew, and additionally closes the
topmost transient layer (menu, popover, card) (Q10).

**States.**

| State | What the observer sees |
|---|---|
| No frame | existing empty states (ImagingScreen.svelte:130-179); toolbar "inspect" and "field" groups disabled, reason "no frame yet" |
| Mono frame (`bayer` null) | Preview row hidden; histogram single curve; saturation and region work on the single channel |
| Field not identified | `sky-grid`, `labels` and the popover rows disabled with reason "Identify the field first (S)"; G limit still settable; click measures only, role buttons disabled with reason "Identify the field to give this star RA/Dec" |
| Solving / catalogues loading | `catalogue` button busy (spinner, BRAND 8); popover header "Fetching catalogues…" |
| Catalogues failed | popover warning row "Catalogues unavailable: {error}" (same wording as analysis_window.py:654-656, which prefixes "Field solved · "), layers already loaded stay |
| Point identification running | card title "Identifying catalogue source…" with spinner; a new click **cancels and replaces** it (fixes P10) |
| Slew or frame geometry change | all field layers cleared, grid off, counts 0, card closed; log line (existing wording, 1.1) and a toast only for the geometry case |
| Error from an API call | toast + log line (existing runner) |

**Overlay drawing (tokens only, shape-coded so Night Red stays readable, BRAND sections 2
(principle 6) and 11):** Gaia stars circle r 9 `--overlay-field-star`; variables circle r 15
`--overlay-variable`, suspected dashed; galaxies tilted ellipse `--overlay-galaxy`; nebulae
and clusters dashed circle `--overlay-nebula`; exoplanet hosts circle with an orbit ellipse
`--overlay-exoplanet`; other objects diamond `--overlay-other`; VSP candidates `+` in
`--role-comparison`; selected set circle / square / upward triangle in `--role-*`, 2 px;
grid `--overlay-grid` 1 px dotted with labels `--overlay-label` mono 11 px with a 1 px
black halo; selection ring and region box `--accent`; loupe border `--border`. These shapes
match the icons of the same layers (fixes P18, P19). Label de-overlap is computed in
**screen** px after each zoom (fixes P27).

**Night Red specifics.** Image drawn as v × `--viewer-tint` (exists). Saturated pixels are
drawn black (`#000000`) so a clipped core reads as a hole in a red star; Observatory and
Charcoal use a dedicated loud token (Q2, needs a new token from the design team). Fire and
Ice are disabled; Negative is allowed but warns that it brightens the whole frame (Q3). R /
G / B histogram curves are told apart by line style and a legend. Context menu, popovers,
tooltips and the card are token-drawn (no native `<select>` or menu).

**Persistence.** Per viewer (localStorage via `prefs.ts`, safe when missing): rotation
(exists), card open states (exists), "View options" open, Preview, palette, crosshair mode,
loupe, saturation, region box rectangle, Statistics card shown, info-card position, overlay
layer visibility per layer (Q5). Server config: `catalog.display_mag_limit` (saved on commit
from slider release, number entry or keyboard), star aperture `imaging.star_radius_px`
(Q11, new key). Read-only from config: `camera.full_well_adu`,
`catalog.field_stars_mag_limit`.

**Always visible without scrolling at 1440 × 900:** the toolbar (all toggles), the image,
the HUD chips, the status bar readouts, and in the rail the Camera card plus the Display
card's histogram, levels and actions. Statistics and "View options" are one click away.

### 2.5 API needs beyond v1

All positions on the wire are **frame px, numpy convention** (centre of pixel (i, j) at
(i, j), un-rotated). The server converts to and from green px (`frame = 2 × green` on the
G1 grid, green.py:10-16) so the client never sees green px except as labelled radii.

| Name | Kind | Payload sketch | Core / worker code it wraps (file:line) | Notes |
|---|---|---|---|---|
| A1 `bayer` in frame header | frame field | `"bayer": "GRBG" \| null` per frame (camera: profile; file: FITS `BAYERPAT`) | protocol.md frame header; CameraState.sensor.bayer | needed for client CFA preview, R/G/B histogram, per-channel region stats; file frames have no CameraState |
| A2 `frame_metrics` | WS event (`/ws/events`) | `{seq, star_count, hfd_px, fwhm_px, eccentricity, sky_adu, peak_adu, n_detected, star_radius_px}` | `build_processed_frame` preview_processor.py:58-109 → `frame_metrics` metrics.py:146, `detect_stars` :158 | per frame, latest-wins, computed off the event loop; Statistics "Stars" block and focus card (other spec) |
| A3 Star aperture | HTTP `PUT /api/imaging/star-radius` | `{radius_px: int 2..30}` → `{radius_px}` | `PreviewProcessor.set_radius` preview_processor.py:121-123; `_on_star_radius` imaging_page.py:786-791 | re-processes the last frame; persisted if Q11 says so |
| A4 Select / measure | HTTP `POST /api/image/select` | `{x, y, seq}` → `Selection {id, kind: target\|variable\|vsp\|simbad\|deep_sky\|exoplanet\|gaia\|point_identity\|measured\|none, title, rows: [{key, value}], ring: {x, y, r_px, aperture: "photometry"\|"star"}, pending_star\|null, roles_enabled, removable, identifying: bool}` | `_on_star_clicked` imaging_page.py:793-967, `_nearest` :969-983, `_present_card` :985-1006, `_present_field_card` :1008-1034, `measure_star_at` metrics.py:225-276, `_format_star_text` :1257-1284 | hit tolerance sent by the client in frame px (`tol_px`) so it is 10 screen px at any zoom; the logic must move from the Qt page into the engine (Qt-free) |
| A5 Point identification | WS event `selection` | `{id, state: "identifying"\|"resolved"\|"no_match"\|"failed", selection: Selection, message}` | `PointIdentityWorker` object_resolver_worker.py:66; imaging_page.py:1036-1155 | up to ~35 s; a new A4 cancels the running one (fixes P10); logs as in 1.6 |
| A6 Pinned selection tracking | WS event `selection` (same) | `{id, seq, ring, rows}` each frame while a measured star is pinned | `_remeasure_selection` imaging_page.py:1230-1246 (`TRACK_SNAP_SEARCH` metrics.py:45) | stops on A7 or geometry change |
| A7 Clear selection | HTTP `DELETE /api/image/select` | — | `_on_card_cleared` imaging_page.py:2042-2046 | — |
| A8 Assign role | HTTP `POST /api/targets` | `{star: PendingStar, role: "target"\|"comparison"\|"check"}` → `TargetSet` | `_on_card_role` imaging_page.py:2021-2030; `engine.set_target_role` acquisition_engine.py:1024-1031; `camera_dock.set_object_name_if_empty` camera_dock.py:321 | side effects: auto-selects VSP comparisons when the set has none (acquisition_engine.py:1077), writes targets.json, resets the tracker; emits WS `targets` (shared with the Photometry spec) |
| A9 Remove from set | HTTP `DELETE /api/targets/{key}` | → `TargetSet` | `engine.remove_target` acquisition_engine.py:1235-1240 | emits `targets` |
| A10 Field (WCS) | WS event `field` | `{state: "unsolved"\|"solving"\|"solved", wcs: {crval1, crval2, crpix1, crpix2, cd: [4], grid: "green"}, grid: {lines: [{x: [], y: []}], labels: [{x, y, text}]}, centre: {ra_deg, dec_deg}, target_reticle: {x, y, r}\|null, green_shape}` | `AstrometryController.solved` astrometry_controller.py:223-224; `wcs_grid` platesolve.py:437-527; `overlay_for` astrometry_session.py:137-153; `_on_astrometry_solved` imaging_page.py:1379-1403; `_clear_astrometry` :2440-2498; geometry guard :757-771 | the WCS lets the client compute cursor RA/Dec (TAN, `FrameWCS` platesolve.py:327-357) without round trips; `state` cleared on slew |
| A11 Field layers | WS event `field_layers` | `{generation, layers: {stars: [{x, y, label, tooltip, g_mag}], variables: [{x, y, label, tooltip, suspected}], galaxies, nebulae_clusters, exoplanets, other_objects: [{x, y, label, tooltip}], vsp: [{x, y, tooltip}], selected: [{x, y, label, role, key, tooltip}]}, counts, available}` | `_project_catalog` imaging_page.py:1483-1740, `_project_targets` :1742-1769, tooltips :1904-2008 | Gaia can reach `catalog.identification_max_objects` (50-5000, analysis_window.py:593-595): send once per catalogue generation; label rule `_is_generic_catalogue_identifier` server-side |
| A12 Tracking transform | WS event `field_transform` | `{generation, dx, dy, rot_deg}` (frame px, about the WCS reference) | `engine.tracked_wcs` acquisition_engine.py:1313; `apertures_tracked` imaging_page.py:546 | lets the client move every marker without re-sending A11 at each frame |
| A13 Open FITS into the pipeline | change to `POST /api/camera/open-fits` | same body; also `engine.ingest_frame`; header gains `bayer`, `path`, `name` | `_on_open_fits` imaging_page.py:1312-1339; `ingest_frame` acquisition_engine.py:515-523 | v1 publishes for display only; Observe needs solve, catalogue and roles on a replayed frame |
| A14 Catalogue re-fetch | HTTP `POST /api/field/catalogue/refetch` | — | `engine.refetch_catalog` acquisition_engine.py:815-832 | called after Settings ▸ Catalogues is saved (imaging_page.py:1430-1432) |
| A15 Config keys | HTTP config route (Settings spec) | read `camera.full_well_adu`, `catalog.field_stars_mag_limit`, `catalog.field_stars_detected_only`; read/write `catalog.display_mag_limit`, `imaging.star_radius_px` (new) | `config.get/set` imaging_page.py:190, :722, :1449, :1528 | generic route expected from the Settings spec |

Client-only (no API): CFA preview (GPU port of `render_view` + `neutralise_rgb_for_display`
with per-channel medians from per-channel histograms), per-channel histograms (port of
`channel_histograms`), region statistics on raw samples (port of `region_stats`),
saturation on raw samples, palettes (LUT in the shader), loupe (second viewport of the same
texture), cursor RA/Dec (TAN), G-limit filtering, standard deviation from the exact
histogram, ADC depth from the quantization step, label de-overlap, "Save view as PNG".

---

## 3. Open questions for the owner

| # | Question | Proposal |
|---|---|---|
| Q1 | Crosshair: the web reticle sits at the image centre, the Qt one follows the cursor (P14). Keep both? | X toggles; "Crosshair: Centre · Cursor" in View options, Centre by default |
| Q2 | Night Red saturation: black "holes", or another encoding? And a new loud token for the other themes? | black in Night Red; new token `--viewer-saturated` for Observatory/Charcoal (design team) |
| Q3 | Night Red palettes: disable Fire and Ice only, or also Negative (bright red background)? | disable Fire and Ice; allow Negative with a warning tooltip |
| Q4 | Should Preview default to Colour (Observe today) or Raw (Frame Viewer today)? | Colour for Seestar frames, Raw for the Review inspector |
| Q5 | Remember overlay layer visibility across fields and launches, or keep Qt's "auto-show once per field, Labels off"? | remember the user's choices; first-ever default = Qt arming |
| Q6 | Hit-test: identify hidden layers (Observe) or visible layers only (Frame Viewer)? | Observe rule everywhere: hiding markers changes presentation, never data |
| Q7 | VSP candidates: default off and only near detected sources (Observe), or on and all (Frame Viewer)? | Observe rule everywhere |
| Q8 | Keyboard shortcuts for Target / Comparison / Check on the card? They write targets.json and Target auto-selects comparisons. | none (deliberate action, icon + label) |
| Q9 | Is the pyqtgraph "Export..." used (PNG/SVG/print of the view with overlays)? | keep "Save view as PNG…" only |
| Q10 | Esc: abort motion only (current web rule), or also close the topmost card / popover? | both: abort (harmless when idle) and close |
| Q11 | Star aperture vs photometry aperture: keep two radii with two ring styles, or one? Persist the star aperture? | keep both, label which one the ring shows; persist `imaging.star_radius_px` |
| Q12 | Add cursor RA/Dec to the status bar when solved (Qt never had it)? | yes |
| Q13 | Show the effective ADC depth ("12-bit, 16 ADU steps") instead of "16-bit"? | yes |
| Q14 | CFA preview computed on the GPU in the browser (proposed) or rendered by the server (×3 bandwidth)? | GPU in the browser |
| Q15 | Loupe magnification: fixed 4× (Qt) or 2× / 4× / 8×? Show raw values in it? | 4× default, wheel over the loupe changes it; no values |
| Q16 | Info card: floating and draggable over the image (Qt), or a fixed slot in the rail? | floating, bottom-left, position remembered |
| Q17 | Should the Frame Viewer's read-only inspector get the role buttons (it already loads the session target set, analysis_window.py:342-348)? | no (Review spec to confirm) |
