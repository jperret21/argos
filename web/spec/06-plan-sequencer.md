# Plan (sequencer, targets, variable stars): Qt inventory and web redesign

Status: spec for review. Author: spec agent "06-plan", 2026-11-01. Source of truth: the Qt code on
branch `explore/web-ui` (commit 74c9c2e + working tree). Everything below was read line by line;
behaviours marked **(verified)** were also reproduced offscreen with `QT_QPA_PLATFORM=offscreen`.

## 0. Scope

### Files covered

| Abbrev. | File | Lines |
|---|---|---|
| PG | `argos/ui/pages/sequencer_page.py` | 323 |
| SP | `argos/ui/widgets/sequence_panel.py` | 1069 |
| TT | `argos/ui/widgets/target_table.py` | 94 |
| VT | `argos/ui/widgets/variable_table.py` | 207 |
| SEQ | `argos/core/imaging/sequencer.py` (model) | 228 |
| TS | `argos/core/catalog/targets.py` (target set) | 252 |
| SW | `argos/workers/sequence_worker.py` (run loop) | 512 |
| AE | `argos/core/session/acquisition_engine.py` (entry points, lines 86-200, 438-666, 967-1240) | 1652 |

Followed for behaviour (read, not inventoried): `argos/ui/shell.py` (wiring, F3, layout reset),
`argos/ui/panels/photometry_window.py` (hosts VT and TT), `argos/ui/pages/imaging_page.py` (IP: handlers
of VT/TT signals, catalogue target, science source), `argos/ui/widgets/dock_host.py`,
`argos/core/exoplanet/transit.py`, `argos/core/catalog/exoplanets.py`, `argos/core/catalog/object_resolver.py`,
`argos/core/imaging/sky_geometry.py`, `argos/core/imaging/fits_writer.py`, `argos/core/imaging/session_log.py`,
`argos/workers/camera_service.py`, `argos/workers/object_resolver_worker.py`, `argos/workers/exoplanet_worker.py`.

### Everything in scope and how it opens

| Ref | Element | Kind | Opened by |
|---|---|---|---|
| 1.1 | `SequencerPage` "Plan" | page (stacked in the shell) | Sidebar "Plan" (`sidebar.py:41`), View ▸ Plan **F3** (`shell.py:229-234`) |
| 1.2 | Panel toolbar | toolbar strip at the top of the page | always visible on the page |
| 1.3 | Five dock frames (Scientific source, Acquisition options, Target visibility, Presets, Sequence control) | `QDockWidget`s in a nested `QMainWindow` (SP:211-219, 489-500) | always; toggled by 1.2, floated by double-click |
| 1.4 | Steps table + edit row | central widget of the workspace (SP:222-271) | always |
| 1.5 | Scientific source dock (two stacked pages: Variable star / Exoplanet transit) | dock + stacked sub-panels (SP:274-448) | dock 1.3 |
| 1.6 | Acquisition options dock | dock (SP:302-337) | dock 1.3 |
| 1.7 | Target visibility dock (`TargetVisibilityPlot`) | dock with a pyqtgraph plot (SP:96-171, 339-343) | dock 1.3 |
| 1.8 | Presets dock | dock, tabbed behind 1.9 by default (SP:450-461, 546) | tab "Presets" |
| 1.9 | Sequence control dock | dock (SP:463-487) | always (raised tab) |
| 1.10 | "Save sequence preset" | modal native `QFileDialog` (SP:899) | 1.8 #1 |
| 1.11 | "Load sequence preset" | modal native `QFileDialog` (SP:913) | 1.8 #2 |
| 1.5 #3, #6 | Autocomplete pop-ups | `QCompleter` pop-up lists (SP:286, 360) | typing in the search fields |
| 1.12 | `VariableTable` | tab "Variable stars" (index 0) of the non-modal floating window "Field photometry" (`photometry_window.py:222, 230`) | Photometry ▸ Photometry setup… (`shell.py:270-276`, opens on this tab); Photometry ▸ Live curves & diagnostics… (`shell.py:278-281`) |
| 1.13 | `TargetTable` | tab "Targets" (index 3) of the same window (`photometry_window.py:225, 233`) | same menu entries, then the tab |
| (shell) | Status-strip "●REC" sequence progress, sidebar Plan "active" dot | shell widgets fed by the engine (`statusbar.py:204-240`, `shell.py:312-313, 374-399`) | owned by the shell spec; listed here because they show this area's state |

No context menu, no `QMessageBox`, no keyboard shortcut and no tooltip-driven popover exists in the four
files. The pyqtgraph plot (1.7) brings pyqtgraph's default right-click menu.

## 1. Inventory (Qt, as it is today)

Column "Persisted" means across launches. "—" = not persisted.

### 1.1 SequencerPage (PG:24, page, opened by sidebar/F3, non-modal, full content area)

- Purpose: host the planning workspace and wire it to the engine, the device session, the object resolver
  and the NASA exoplanet lookup.
- Controls: none of its own. One heading `design.HeadingLabel("Plan")` (PG:47).
- Wiring (PG:52-69):

| Signal | Handler | Effect |
|---|---|---|
| panel `start_requested(plan)` | `_on_start` PG:73 | `engine.start_sequence(plan)` (AE:444); on `False` → `panel.set_running(False)` (snap back) |
| panel `pause_requested` / `resume_requested` / `stop_requested` | AE:489 / AE:495 / AE:484 | worker `pause()` / `resume()` / `stop()` |
| panel `object_lookup_requested(str)` | `_lookup_object` PG:89 | one `ObjectResolverWorker` at a time (second request ignored) |
| panel `exoplanet_lookup_requested(str)` | `_lookup_exoplanet` PG:120 | one `ExoplanetLookupWorker` at a time |
| panel `transit_plan_requested` | `_prepare_transit_plan` PG:248 | builds and loads a transit plan |
| engine `sequence_running(bool)` | `panel.set_running` SP:978 | |
| engine `sequence_paused(bool)` | `panel.set_paused` SP:1000 | |
| engine `sequence_progress(obj, done, total, eta)` | PG:300 → SP:1016 | |
| engine `sequence_step(i, step)` | PG:303 | highlight row + status "Step {i+1}: {count}× {exp:.1f}s {filter}" |
| session `capabilities_ready(caps)` | PG:310 → SP:930 | exposure/gain ranges from the camera |
| session `filterwheel_state(fw)` | PG:316 → SP:957 | filter names from the wheel |
| session `device_state_changed(dev, state, info)` | PG:320 | readiness; camera `disconnected` → default limits |
| page `target_resolved(obj)` | `IP.set_catalogue_target` IP:2658 (`shell.py:173`) | mount card target armed (not slewed), Observe object name set with emit, log "Catalogue target: …", auto photometry target if SIMBAD type is variable |
| page `science_source_resolved(prog, obj)` | `IP.set_science_source` IP:2709 (`shell.py:174`) | `_set_photometry_target` IP:2683 → `engine.set_target_role` (+ auto comparisons) |
| Observe `target_coordinates_changed` | `set_target_coordinates` PG:79 (`shell.py:172`) | visibility plot for a target chosen in Observe ▸ Mount |
| Observe camera `object_name_changed` | `panel.set_object_name` (`shell.py:170`) | keeps "Target name (FITS)" in sync |
| panel `object_name_changed` | `shell._on_sequence_object_changed` (`shell.py:176`) | sets the Observe object name, then `engine.on_object_changed()` (AE:1010: reload target set by new name, clear curves, reset tracker) |

- Implicit behaviours: `shutdown()` waits up to 9 s (resolver) and 13 s (NASA) for workers (PG:291-297);
  `save_layout()` on application close (`shell.py:449`).
- Messages (PG): "Find a planet before preparing a transit sequence." (PG:252, unreachable in practice: the
  button is disabled without a window); "Set and save the observing site in Settings before preparing transit
  coverage." (PG:257); `ValueError` text from `predict_next_transit` / `make_transit_sequence` (PG:273-275, list
  in 1.5); "Transit sequence prepared: {count} light frames at {cadence:.1f}s cadence. Review the start time
  before running." (PG:283-286); "Step {n}: {count}× {exp:.1f}s {filter}" (PG:305-307).

### 1.2 Panel toolbar (SP:512-531, `QToolBar`, top of page, always visible)

| # | Control | Qt type | Label / tooltip (exact) | Default | Enabled / visible | Shortcut | Action | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Scientific source | checkable `QAction` (`toggleViewAction`) SP:518 | "Scientific source" / "Drag the panel title to arrange it; double-click to detach it." | checked | always | — | show/hide dock 1.5 | in `ui.sequencer.layout` |
| 2 | Acquisition options | same SP:519 | "Acquisition options" / same tooltip | checked | always | — | show/hide 1.6 | same |
| 3 | Visibility | same SP:520 | "Visibility" / same tooltip | checked | always | — | show/hide 1.7 | same |
| 4 | Presets | same SP:521 | "Presets" / same tooltip | checked | always | — | show/hide 1.8 | same |
| 5 | Sequence control | same SP:522 | "Sequence control" / same tooltip | checked | always | — | show/hide 1.9 | same |
| 6 | Reset panels | `QAction` SP:527 | "Reset panels" / "Restore the default Sequencer panel arrangement" | — | always | — | `reset_layout` SP:584: clears `ui.sequencer.layout`, re-applies `_apply_default_layout` SP:533 | clears key |

### 1.3 Dock frames (SP:489-500 via `make_dock`, `dock_host.py:48-119`)

Features: movable, closable, floatable (`dock_host.py:68-74`). Default layout (SP:533-562): right area
Source (115 px) / Visibility (330 px) / Acquisition options (250 px), stacked vertically; bottom area Sequence
control (108 px) tabbed with Presets, Sequence control raised. Minimum heights: Source 118, Options 215
(SP:504-505). Docks 1.5, 1.6, 1.8, 1.9 scroll; 1.7 does not (`scroll=False`).

| # | Control | Qt type | Label | Action | Persisted |
|---|---|---|---|---|---|
| 1-5 | Title-bar drag of each dock (Source, Options, Visibility, Presets, Control) | `QDockWidget` title | dock titles "Scientific source", "Acquisition options", "Target visibility", "Presets", "Sequence control" | move / nest / tab the dock; double-click detaches (floats) | `ui.sequencer.layout` (base64 `saveState`, SP:579-582) |
| 6-10 | Float button of each dock | title-bar button | (Qt default, no text) | float / re-dock | same |
| 11-15 | Close button of each dock | title-bar button | (Qt default) | hide the dock; 1.2 brings it back | same |
| 16-17 | Bottom tabs "Sequence control", "Presets" | `QTabBar` from `tabifyDockWidget` SP:546 | dock titles | switch tab | same |

### 1.4 Steps table and edit row (SP:222-271, central widget, always visible)

Columns `_COLUMNS` (SP:65): "✓", "Type", "Filter", "Exp (s)", "Gain", "Count", "Interval (s)", "Dither every".
One editable row is created at start (SP:196). Each row is built by `_add_row` SP:678-741 from a
`SequenceStep` (defaults below). The table height follows its rows between 120 and 420 px (SP:762-769),
with a stretch between the table and the edit row (SP:269).

| # | Control | Qt type | Label / tooltip (exact) | Default / range / step / units | Enabled / visible | Shortcut | Action: handler → effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Enabled (per row) | `QCheckBox` in a centred wrapper SP:683-691 | header "✓", no tooltip | checked (`step.enabled`) | table enabled (not running, SP:983) | Space (Qt default when focused) | `toggled` → `_refresh_estimate` SP:1030 | — (preset only) |
| 2 | Type (per row) | `QComboBox` SP:693 | header "Type" | options Light, Dark, Flat, Bias (SP:61); default Light; unknown value → stays Light | same | — | read at `to_plan` SP:793 | — |
| 3 | Filter (per row) | `QComboBox` SP:698 | header "Filter" | wheel names, else IR, LP, Dark (SP:64); model default "LRGB" is not in the list → first item shown **(verified)** | same; editable also on Dark/Bias rows where it is ignored (SEQ:114-123) | — | read at SP:794; rebuilt by `set_filter_options` SP:957 (missing name → index 0) | — |
| 4 | Exp (s) (per row) | `QDoubleSpinBox` SP:705 | header "Exp (s)", no tooltip | 10.00 s; range camera `exposure_min`(≥0.01)…`exposure_max`, else 0.01…600 s; 2 decimals; step 1.0 | same | ↑/↓, wheel | `valueChanged` → estimate; holds the hidden `cadence_s` property (SP:709) | — |
| 5 | Gain (per row) | `QSpinBox` SP:713 | header "Gain", no tooltip | 80; range camera gain_min…gain_max, else 0…600; step 1 | same | ↑/↓ | read at SP:796 (no estimate refresh) | — |
| 6 | Count (per row) | `QSpinBox` SP:718 | header "Count" | 10; 1…9999 | same | ↑/↓ | `valueChanged` → estimate | — |
| 7 | Interval (s) (per row) | `QDoubleSpinBox` SP:724 | header "Interval (s)" / "Idle delay after each frame of this step" | 0.0 s; 0…3600; 1 decimal; step 1.0 | same; silently ignored when the row carries a cadence (SW:234-239) | ↑/↓ | `valueChanged` → estimate | — |
| 8 | Dither every (per row) | `QSpinBox` SP:732 | header "Dither every" / "Nudge the mount a few arcminutes every N frames (0 = off)" | 0 shown "off"; 0…999 frames | same | ↑/↓ | read at SP:800 | — |
| 9 | Row selection | `QTableWidget` single row select SP:232-233 | — | last added row selected (SP:739) | always | arrows | `_selected_row` SP:743: selected row, **else the last row** | — |
| 10 | Column resize | header SP:234-239 | — | cols Type, Filter interactive; others fit content | always | — | Qt resize | — |
| 11 | Add | `SecondaryButton` SP:249 | "＋ Add" / "Add a step" | — | always (also while running) | — | `_add_row` SP:678: appends a default `SequenceStep` at the end | — |
| 12 | Dup | `SecondaryButton` SP:250 | "⧉ Dup" / "Duplicate the selected step" | — | always | — | `_duplicate_row` SP:749: copies the selected (or last) row, **appends at the end** (cadence copied) | — |
| 13 | Remove | `SecondaryButton` SP:251 | "－ Remove" / "Remove the selected step" | — | always; no-op when 1 row left (SP:757) | — | `_remove_row` SP:755: removes the selected (or last) row; no confirmation | — |
| 14 | ↑ | `SecondaryButton` SP:252 (min width 42) | "↑" / "Move step up" | — | always | — | `_move_up` SP:771 → `_swap_rows` SP:777 (values swapped, selection follows) | — |
| 15 | ↓ | `SecondaryButton` SP:253 | "↓" / "Move step down" | — | always | — | `_move_down` SP:774 | — |

- Displayed data: estimate label (SP:263) "≈ {h}h {mm}m total" or "≈ {m}m {ss}s total", empty when 0;
  tooltip "Exposures + intervals + per-frame overhead; autofocus passes not counted" (SP:265-267); refreshed on
  enabled, exposure, count, interval, repeat changes (not on gain/dither/cadence). Formula in 1.14. Active run
  step highlighted with `SURFACE_3` background on every cell widget (SP:1007-1014).
- Hidden data: `cadence_s` lives as a Qt property of the exposure spin box (SP:709, 799, 810); never displayed.

### 1.5 Scientific source dock (SP:274-448, dock "Scientific source")

A combo selects which of two stacked pages shows (`_CurrentPageStack` SP:73-87, sized to the visible page).

| # | Control | Qt type | Label / tooltip (exact) | Default / range / step / units | Enabled / visible | Shortcut | Action: handler → effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Programme | `QComboBox` SP:433 | items "Variable star" (data `variable`), "Exoplanet transit" (data `exoplanet`) / "Both programmes use the same target and comparison-star workflow" | Variable star | always | — | `currentIndexChanged` → stack page (SP:444-447). Visual only: the programme sent to Observe depends on which Find was used | — |
| 2 | Variable search | `QLineEdit` SP:280 | placeholder "T CrB, RR Lyr, V404 Cyg…" / "Resolve the variable star's designation to its observing coordinates" | empty | page Variable; disabled while busy (SP:606) | Return (SP:291) | Return → `_request_object_lookup` SP:589 → PG:89 → `resolve_object` (`object_resolver.py:369`: embedded Messier/NGC/IC, then local cache, then CDS Sesame, 8 s timeout) | text — ; results cached in `data_paths.object_catalogue_cache` |
| 3 | Suggestions | `QCompleter` pop-up SP:286-289 | — | case-insensitive, max 8 | on each edit | ↑/↓, Return | `textEdited` → `cached_object_suggestions` (`object_resolver.py:326`, cache file + embedded catalogue, read from disk on every keystroke) | — |
| 4 | Find | `SecondaryButton` SP:293 | "Find", no tooltip | — | disabled while busy (SP:607) | — | same as Return | — |
| 5 | Planet search | `QLineEdit` SP:354 | placeholder "HD 189733 b, WASP-12 b…" / "Search the NASA Exoplanet Archive for a published transit ephemeris" | empty | page Exoplanet; disabled while busy (SP:625) | Return (SP:365) | → PG:120 → `lookup_exoplanet` (`exoplanets.py:368`: cache, then NASA TAP `pscomppars`, exact then prefix match, 12 s each) | results cached in `data_paths.exoplanet_cache` |
| 6 | Planet suggestions | `QCompleter` pop-up SP:360-363 | — | from the exoplanet cache only, max 8 | on edit | ↑/↓ | `cached_exoplanet_suggestions` (`exoplanets.py:299`) | — |
| 7 | Find planet | `SecondaryButton` SP:367 | "Find planet", no tooltip | — | disabled while busy | — | same as Return | — |
| 8 | Baseline | `QSpinBox` SP:380 | label "Baseline" / "Out-of-transit coverage before ingress and after egress" | 60 "min each side"; 0…240; step 1 | page Exoplanet | — | read only by Prepare (SP:667); the window shown after Find always uses 60 (PG:213) | — |
| 9 | Exposure | `QDoubleSpinBox` SP:389 | label "Exposure", no tooltip | 10.00 s; camera range (default 0.01…600); 2 decimals | same | — | read by Prepare | — |
| 10 | Cadence | `QDoubleSpinBox` SP:396 | label "Cadence" / "Start-to-start cadence; includes the exposure and any idle interval" | 13.0 s; 0.01…3600; 1 decimal | same | — | read by Prepare; must be ≥ exposure (`transit.py:88-89`) | — |
| 11 | Gain | `QSpinBox` SP:406 | label "Gain", no tooltip | 80; camera range (default 0…600) | same | — | read by Prepare | — |
| 12 | Filter | `QComboBox` SP:411 | label "Filter" / "Keep one filter for the entire transit; do not change filters mid-series" | wheel names or IR, LP, Dark | same | — | read by Prepare | — |
| 13 | Prepare transit sequence | `SuccessButton` SP:418 | "Prepare transit sequence" / "Replace the table with one uninterrupted light-only acquisition step" | — | disabled until a transit window exists (SP:419, 657, 662) | — | `transit_plan_requested` → PG:248: site check, `predict_next_transit` (baseline from #8) + `make_transit_sequence` (`transit.py:71`), then `load_plan` **replaces the whole table, object name := host name (with emit), repeat 1, AF off, end Nothing**; no confirmation | — |

- Displayed data:
  - Variable result (SP:612-618): "{name} · {type label}\nRA {ra:.5f} h · Dec {dec:+.5f}°" (decimal hours and
    degrees; type label from `object_type_label`, `object_resolver.py:116`).
  - Planet result (SP:631-657): "{planet} — host: {host}\nP {period:.8f} d · duration {h:.2f} h|not published ·
    depth {d:.3g}%|not published\nEpoch: {epoch:.6f} ({system})" then either "\nNext mid-transit: BJD_TDB
    {mid:.6f} (E={n}); coverage {hours:.2f} h." and "\nApprox. local midpoint: {YYYY-mm-dd HH:MM TZ}." or
    "\nObserving site required for coverage.". Coverage start/end times are not printed (only shaded on 1.7).
- Busy texts: "Searching catalogue…" (SP:609), "Searching NASA Exoplanet Archive…" (SP:628).
- Error texts shown in the result label: resolver "Enter an object designation first.", "Catalogue unavailable.
  Connect to the internet or use a previously searched target.", "The catalogue returned an invalid response.",
  "No ICRS coordinates found for ‘{q}’.", "The catalogue returned invalid coordinates for ‘{q}’.", "Object lookup
  failed unexpectedly. See the log for details."; NASA "Enter a planet designation first (for example HD 189733
  b).", "NASA Exoplanet Archive is unavailable. Connect to the internet or use a cached planet.", "No confirmed
  transiting planet named ‘{q}’ was found.", "NASA Exoplanet Archive search failed.", "The catalogue has no {key}
  for this planet.", "The catalogue returned an invalid {key} value.", "The catalogue returned an unusable transit
  ephemeris.", "The published transit epoch is not explicitly BJD_TDB; Argos will not silently convert it. Choose
  an ephemeris with a BJD_TDB reference.", "Planet lookup failed unexpectedly. See the local log for details.";
  transit build "A BJD_TDB transit epoch is required for prediction.", "baseline_minutes must not be negative",
  "A published transit duration is required to prepare coverage.", "exposure_s must be positive", "cadence_s
  cannot be shorter than exposure_s".
- Implicit behaviours on a variable result (PG:101-107): result label; visibility plot (site lat/lon, **0/0 if no
  site saved**); `target_resolved` → Observe (mount target armed, object name, log); `science_source_resolved
  ("variable", obj)` → photometry target **for any object type**, comparisons auto-picked when VSP stars are known.
- On a planet result (PG:208-233): BJD_TDB now needs a saved site (`site.name` non-empty, PG:147-158); next
  transit with mid ≥ now; local coverage via `utc_from_bjd_tdb`; host star (never the planet) sent to Observe as
  `ResolvedObject(object_type="Exoplanet host")`; visibility for the transit night with the coverage shaded.

### 1.6 Acquisition options dock (SP:302-337, dock "Acquisition options")

| # | Control | Qt type | Label / tooltip (exact) | Default / range | Enabled / visible | Shortcut | Action | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Target name (FITS) | `QLineEdit` SP:310 | label "Target name (FITS)"; placeholder "M42, T CrB…" / "Target identifier written to FITS OBJECT and used for this run's target set. It is not the observation-session name." | synced from Observe | **always, also during a run** | — | `editingFinished` → `_on_object_edited` SP:880 → readiness + `object_name_changed` → Observe object + `engine.on_object_changed()` (target set re-keyed) | — (shared with Observe; target set file keyed by it) |
| 2 | Repeat plan | `QSpinBox` SP:319 | label "Repeat plan", no tooltip | 1; 1…999 | always | — | estimate refresh | — |
| 3 | Autofocus every | `QSpinBox` SP:324 | label "Autofocus every"; suffix " frames (0=off)" | 0; 0…999 | always | — | plan field; AF triggered when frames since last AF ≥ N, counted across steps (SW:209-213) | — |
| 4 | Autofocus on filter change | `QCheckBox` SP:328 | "Autofocus on filter change" | off | always | — | AF after a wheel move to a light-passing filter, never before the first frame (SW:195-206) | — |
| 5 | End of run | `QComboBox` SP:331 | label "End of run"; items "Nothing", "Stop tracking", "Park mount" (SEQ:61) / "Mount action after FULL completion only — never after a stop or error" | Nothing | always | — | stored in plan; AE:598-610 runs `session.set_tracking(False)` or `session.park()` only when `completed` | — |

### 1.7 Target visibility dock (SP:96-171, 339-343, dock "Target visibility")

- Purpose: altitude of the current source over "the next local night", 18:00 → 06:00 local, 10 min samples
  (`upcoming_night_altitudes`, `sky_geometry.py:60-88`).
- Plot: curve in `ACCENT` (2 px); fixed dashed line at **30°** (SP:126-131, unlabelled, not configurable); y range
  −15…90°; x = local time (`DateAxisItem`); transit coverage region in `WARNING` tint (SP:115-125). Summary under
  the plot "Peak {alt:.1f}° · {HH:MM} local" (SP:159).
- Refreshed only on a lookup result, a transit preparation, or a target chosen in Observe; no timer, no "now"
  marker, the target name is not shown (`name` unused, SP:139-160). Empty plot shows meaningless ticks.

| # | Control | Qt type | Behaviour | Persisted |
|---|---|---|---|---|
| 1 | Drag to pan, wheel to zoom | pyqtgraph `ViewBox` default | changes axes; no way back except #3 | — |
| 2 | Right-click menu | pyqtgraph default (View All, X axis, Y axis, Mouse Mode, Plot Options, Export…; exact entries depend on the pyqtgraph version) | inherited, never configured | — |
| 3 | Auto-range "A" button | pyqtgraph default, bottom-left on hover | restores range | — |

### 1.8 Presets dock (SP:450-461, dock "Presets", tabbed behind 1.9)

| # | Control | Qt type | Label / tooltip | Enabled | Action | Persisted |
|---|---|---|---|---|---|---|
| 1 | Save preset… | `SecondaryButton` SP:455 | "Save preset…", no tooltip | always | `_on_save_preset` SP:898 → dialog 1.10; adds ".json" if missing; writes `json.dumps(plan_to_dict(to_plan()), indent=2)`; status "Preset saved: {file}" / "Preset save failed: {exc}" | file on disk |
| 2 | Load preset… | `SecondaryButton` SP:457 | "Load preset…", no tooltip | **always, also during a run** | `_on_load_preset` SP:912 → dialog 1.11; `plan_from_dict` (errors → "Preset load failed: {exc}"); `load_plan` SP:827 (replaces table, object name with emit); status "Preset loaded: {file}" | — |

### 1.9 Sequence control dock (SP:463-487, dock "Sequence control")

| # | Control | Qt type | Label / tooltip (exact) | Enabled / visible | Action | Persisted |
|---|---|---|---|---|---|---|
| 1 | Start sequence | `SuccessButton` SP:466 | "▶  Start sequence", no tooltip | enabled when not running (SP:980); **not** gated by readiness | `_on_start` SP:1062: refuses with "Add an enabled step" (warning colour) if no enabled step; else `start_requested(plan)` → PG:73 → AE:444 | — |
| 2 | Pause / Resume | `SecondaryButton` SP:468 | "⏸  Pause" / "Hold after the current frame; Resume releases it"; text "▶  Resume" while paused (SP:1003) | enabled while running | `_on_pause_clicked` SP:1056 → AE:489 (log "Pausing after the current frame…") or AE:495 | — |
| 3 | Stop | `DangerButton` SP:472 | "■  Stop", no tooltip | enabled while running | `stop_requested` → AE:484 (log "Stopping sequence…"); worker aborts the current exposure (`_safe_stop_exposure`, SW:361-363); no confirmation | — |

- Displayed data: progress bar "%v / {total}" (SP:478, 1016-1019), visible while running; status label
  (SP:481): "Frame {done}/{total} — ETA {dur}", "Step n: …", "Paused", preset and transit messages (they
  overwrite each other); readiness label (SP:485, tooltip "Sequence readiness", SP:1037-1054):

| Condition | Text | Colour |
|---|---|---|
| camera not `connected` (disconnected or error; the session never sends `busy` for the camera) | "Camera required" | warning |
| object name empty | "Object name required" | warning |
| mount `connected` | "Ready" | success |
| mount anything else (offline, error, **busy/slewing**) | "Ready · telescope offline" | warning |

### 1.10 / 1.11 Preset file dialogs (SP:899, SP:913, modal native `QFileDialog`)

| # | Dialog | Title | Start directory | Filter |
|---|---|---|---|---|
| 1.10 #1 | Save | "Save sequence preset" | `data_paths.sequence_presets_directory`, default `~/Argos/sequences`, created if missing (SP:888-896) | "Sequence preset (*.json)" |
| 1.11 #1 | Open | "Load sequence preset" | same | same |

### 1.12 VariableTable (VT:58; tab "Variable stars" of the "Field photometry" window)

- Purpose: list the VSX variables of the solved field and pick the photometry target; the filter also filters the
  VSX markers on the image (`visible_rows_changed` → IP:1776-1779).
- Rows: built by `IP._refresh_variable_table` IP:2202-2222 from `engine.variables` (VSX, brightest first) **inside
  the solved image only**; refreshed on catalogue ready (IP:1461-1464), target-set change (IP:2015-2019) and window
  open (IP:2140). Suspected variables in muted colour (VT:179-180).

| # | Control | Qt type | Label / tooltip (exact) | Default / range | Enabled | Shortcut | Action | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Filter | `QLineEdit` VT:75 | placeholder "Filter by designation or type…" / "Case- and space-insensitive; for example, XX Cyg or xxcyg" | empty | always | — | `textChanged` → `_apply_filters` VT:137 (normalised substring on name + type) | — |
| 2 | Clear | line-edit clear button VT:77 | (Qt default) | — | when text | — | clears #1 | — |
| 3 | Brightest mag ≤ | `QDoubleSpinBox` VT:82 | label "Brightest mag ≤" / "Show variables whose brightest catalogued magnitude is at or brighter than this limit" | 0 shown "Any"; 0.0…20.0; step 0.5; 1 decimal | always | ↑/↓ | `valueChanged` → `_apply_filters` (rows without a magnitude are hidden when a limit is set) | — |
| 4 | Row selection | `QTableWidget` VT:96-101 | — | single row | always | arrows | — | — |
| 5 | Header click | `sectionClicked` VT:106 | — | catalogue order until first click | always | — | `_sort_by_column` VT:188: ascending, then toggles; no return to catalogue order | — |
| 6 | Double-click row | `doubleClicked` VT:107 | — | — | always | — | `_on_select` VT:201 → `target_requested(index)` → IP:2224: `TargetStar(role="target", source="vsx")`, Observe object name set if empty, `engine.set_target_role` (+ auto comparisons), log "Target: {name}" | target set file |
| 7 | Set as target | `QPushButton` VT:111 | "Set as target" / "Make this variable a photometry target (comparison stars are\npicked automatically when none are chosen yet). Same action as\nclicking its circle on the image." | — | **always** (no-op without selection) | — | same as #6 | same |

- Columns: "" (● when the star is in the target set with **any** role), "Name", "Type" ("?" if none), "Mag" (catalogue
  "max – min" text), "Period (d)" (`:g`), "Sep (′)" (separation from the solved field centre, 1 decimal).
  Semantic sort keys (VT:166-173). Count label "0 stars" then "{shown} of {total} star(s)" (VT:92, 185).

### 1.13 TargetTable (TT:27; tab "Targets" of the "Field photometry" window)

- Columns "Role", "Name", "RA", "Dec", "Mags" (TT:24); RA `format_ra_hms`, Dec `format_dec_dms`, mags "{band}
  {m:.2f}" joined by two spaces (TT:63-70). Refreshed on `targets_changed` (IP:2018) and window open (IP:2133).

| # | Control | Qt type | Label | Enabled | Action | Persisted |
|---|---|---|---|---|---|---|
| 1 | Row selection | `QTableWidget` single row TT:37-42 | — | always | `star_selected(key)` → IP:2049: marks the star on the Observe image ("Selected star is outside the solved image." if off-frame) | — |
| 2 | Remove selected | `QPushButton` TT:47 | "Remove selected", no tooltip | **always** | `remove_requested(key)` → `engine.remove_target` AE:1235 (save, reset tracker, broadcast); no confirmation, no undo, no log line | `{sessions}/targets/{object}.json` |
| 3 | Copy TSV | `QPushButton` TT:49 | "Copy TSV", no tooltip | always | header line + displayed cell texts, tab-separated, to the clipboard (TT:85-94) | — |

### 1.14 Sequence model, validation, persistence, file formats

`SequenceStep` (SEQ:28-57):

| Field | Type | Model default | Qt UI | Meaning |
|---|---|---|---|---|
| `enabled` | bool | `True` | 1.4 #1 | step included |
| `frame_type` | str | `"Light"` | 1.4 #2; `FRAME_TYPES` = Light, Dark, Flat, Bias (SEQ:21, duplicated in SP:61) | → FITS `IMAGETYP` via `IMAGE_TYPE_MAP` (`fits_writer.py:95-100`); Light/Flat open the shutter (SEQ:153) |
| `filter_name` | str | `"LRGB"` (no such Seestar slot) | 1.4 #3 | Light/Flat use it; Dark/Bias go to the opaque "Dark" slot (`wheel_filter`, SEQ:114-123) |
| `exposure_s` | float | 10.0 | 1.4 #4 | seconds |
| `gain` | int | 80 | 1.4 #5 | camera gain, read back after set (SW:306-323) |
| `count` | int | 10 | 1.4 #6 | frames per pass |
| `interval_s` | float | 0.0 | 1.4 #7 | idle wait after each frame |
| `cadence_s` | float \| None | `None` | hidden (transit only) | start-to-start period; replaces `interval_s` (SW:234-239) |
| `dither_every` | int | 0 | 1.4 #8 | MoveAxis nudge every N frames **counted over the whole run** (SW:229); docstring says unsupported on Seestar (SEQ:44-46) yet the worker moves the mount (SW:249-278: ±0.05 °/s for 1 s on both axes, alternating, 3 s settle) |

`SequencePlan` (SEQ:64-90): `steps` (list), `object_name` ("", FITS OBJECT, folder and file names), `repeat`
(1; whole list replayed), `autofocus_every_n` (0 = off), `autofocus_on_filter_change` (False), `on_complete`
("Nothing" | "Stop tracking" | "Park mount"), `base_dir` (None → `sessions_path`; no UI), `metadata` (dict,
JSON-safe; only the transit builder fills it, `transit.py:107-121`).

Derived values:

| Value | Rule | Code |
|---|---|---|
| frame list | per pass, per enabled step with count > 0, `count` frames; `frame_index` restarts per (IMAGETYP, filter, exposure, gain) series and increases across passes (Siril basename convention) | `expand_plan` SEQ:131-169 |
| total frames | Σ enabled `count` × max(1, repeat) | SEQ:172-175 (recomputed inline in AE:480) |
| estimate | Σ `count` × (`cadence_s` if set, else `exposure_s` + `interval_s` + 3.0 s) × max(1, repeat); AF, filter moves and dithers not counted | SEQ:178-198 |

Validation (where it really happens):

| Layer | Rule | Code |
|---|---|---|
| Model | none (no `__post_init__`) | SEQ |
| Preset load | step keys strict (unknown key → `TypeError`), no type/range check; top-level unknown keys ignored, missing ones defaulted | SEQ:215-228 |
| Qt spin boxes | values clamped silently to ranges (also on camera connect/disconnect, SP:930-955) | SP |
| Start | at least one enabled step ("Add an enabled step") | SP:1062-1069 |
| Engine | camera connected ("Connect the camera before running a sequence."), no active sequence (silent), camera ownership (`camera_service.py:81-86`: "Autofocus running — it owns the camera. Wait for it to finish." etc.; a running live view is pre-empted with "Live preview stopped — the sequence owns the camera.") | AE:444-454 |
| Transit | BJD_TDB epoch, baseline ≥ 0, duration > 0, exposure > 0, cadence ≥ exposure | `transit.py:46-53, 86-89` |
| Run | exposure timeout = exposure + 15 s; wheel settle ≤ 20 s; AF handshake ≤ 120 s | SW:44-51 |

Preset file (`*.json`, `plan_to_dict` SEQ:201-212, indent 2, **no schema version**). From the Qt UI `base_dir` is
always `null` and `metadata` always `{}` (see Problems):

```json
{
  "object_name": "T CrB",
  "repeat": 1,
  "autofocus_every_n": 0,
  "autofocus_on_filter_change": false,
  "on_complete": "Nothing",
  "base_dir": null,
  "metadata": {},
  "steps": [
    {"enabled": true, "frame_type": "Light", "filter_name": "IR", "exposure_s": 10.0, "gain": 80,
     "count": 10, "interval_s": 0.0, "cadence_s": null, "dither_every": 0}
  ]
}
```

Other persistence and outputs:

| What | Where | Format / writer |
|---|---|---|
| Draft plan in the editor | **not persisted** (lost on quit) | — |
| Panel layout | config `ui.sequencer.layout` (SP:70) | base64 `QMainWindow.saveState`; saved on quit (`shell.py:449`); cleared by 1.2 #6 and View ▸ Reset Window Layout (`shell.py:455`, next launch) |
| Target set | `{sessions_path}/targets/{safe object}.json` (AE:976-978) | `{"schema": 1, "object", "stars": [{role, ra_deg, dec_deg, auid, name, source, mags, note, chart_id}]}` (TS:117-122), atomic (TS:198-204), on every change (AE:988-993) |
| Run root | `{plan.base_dir or sessions_path}/{RUNID}_{OBJECT}/`, RUNID = UTC start `YYYYMMDDTHHMMSSZ` (SW:179, `fits_writer.py:275-293`) | |
| Frames | `lights/ darks/ flats/ biases/` + `{obj}_{filt}_{type}_e{ms:06d}ms_g{gain:03d}_{index:05d}.fit` (`fits_writer.py:209-273`), never overwritten | `FITSWriter.write` (SW:412-422), headers from read-back gain/filter and `_sequence_frame_context` (AE:612-635) |
| `session.json` | run root | `SessionLog` + `FrameRecord` (filename, image_type, filter, exposure, gain, timestamp, hfd, fwhm, star_count, sky_adu, peak_adu, eccentricity), rewritten after each frame (SW:441-457) |
| `observation.json` | run root | plan `metadata` + `schema_version` 1 (SW:459-477); **never written from the UI** (Problems #1) |
| `targets.json`, `photometry_selection.json`, `photometry_selection_history.jsonl` | run root | at the first saved frame and on every in-run target-set edit (AE:532-547, 995-1008, TS:124-184) |
| `diagnostics/{obj}_live_diagnostics.jsonl` | run root | when `diagnostics.enabled` (AE:643-666) |

### 1.15 Run behaviour (engine + worker)

Start (AE:444-482): checks (1.14) → `_seq_object` → `clear_lightcurves()` → `SequenceWorker` (camera, mount,
wheel, plan, context provider, base dir) → `sequence_running(True)` → log "Sequence started — {n} frame(s)." Observe
arms auto-solve if a WCS exists and restores the user's choice after the run (IP:2538-2550, log "Sequence:
auto-solve armed for the run.").

Per frame (SW:183-243), in order: stop / pause gate (pause holds at the frame boundary, `paused(True/False)`) →
`step_started(i, SequenceStep)` when the step index changes (not on a new pass of a single-step plan) → wheel move
if needed (unknown name: warning, move skipped; settle ≤ 20 s) → AF on filter change → periodic AF →
`frame_started` (**not connected by the engine**) → set gain, read back gain and filter → expose, poll every 200 ms,
timeout → download → `frame_image` (shown in Observe) → metrics (HFD, FWHM, stars, sky, eccentricity) → FITS +
`session.json` → `frame_saved` (Observe log "Saved {file}  HFD={hfd:.1f} FWHM={fwhm:.1f}  stars={n}", FWHM part optional, IP:2563-2570; photometry point if WCS
and target, AE:532-557) → `progress(done, total, eta = mean time per frame × remaining)` → dither → interval or
cadence wait (interruptible).

Mid-run autofocus (AE:559-582): skipped silently without focuser; otherwise camera handed to AF (exposure
`min(Observe exposure, 10 s)`, Observe gain, 9 steps), then resumed. Worker aborts after 120 s without resume.

End (AE:584-610): `sequence_running(False)`, log "Sequence complete." (OK) or "Sequence stopped." (INFO, also after
an error), end-of-run mount action on completion only. Errors from the worker are logged "Sequence: {message}"
(AE:512-513): "Exposure timeout after {N}s", "Autofocus did not resume within 120s — sequence aborted", Alpaca
errors.

### 1.16 Problems found

| # | Problem | Where |
|---|---|---|
| P1 | Transit metadata is lost: `to_plan()` rebuilds the plan without `metadata`/`base_dir`, `load_plan` discards them, so a prepared transit never writes `observation.json` (ephemeris hand-off) and presets always save `{}`/`null` **(verified)** | SP:816-838, SW:459-477 |
| P2 | `cadence_s` is invisible state on the exposure spin box; the Interval column is silently ignored on those rows; Dup copies it; editing exposure above the cadence is not checked | SP:709, 799, 810; SW:234-239 |
| P3 | Transit after local midnight is drawn outside the plot: the coverage midpoint is passed as `night_date` and the window starts at 18:00 **of that day**; a 02:00 midpoint plots 18:00 → 06:00 the next day **(verified)**. More generally, between 00:00 and 06:00 the plot shows the next evening, not the current night | SP:868-877, `sky_geometry.py:78-80` |
| P4 | Visibility of a looked-up target uses latitude/longitude 0/0 when no site is saved (no `site.name` guard, unlike the transit path) | PG:79-87 vs PG:147-158 |
| P5 | After Find planet the window uses a 60 min baseline whatever the Baseline field says; changing Baseline updates nothing until Prepare | PG:213, SP:380 |
| P6 | "Observing site required for coverage." is shown when the site is set but the prediction failed (no published duration, non-BJD epoch) | PG:211-216, SP:653-654 |
| P7 | No scheduled start: Start runs immediately while a transit plan is a fixed frame count; the coverage start time is never printed, yet the status says "Review the start time before running" | PG:283-286, SP:646-654 |
| P8 | Plan ▸ Find turns **any** resolved object (M 42, a galaxy) into a photometry target (`science_source_resolved("variable", …)` unconditionally), contradicting Observe's rule that only variable types become targets; for variable types the target is set twice | PG:107, IP:2671-2676, 2709-2720 |
| P9 | Editing during a run: only the table is disabled. Add/Dup/Remove/↑/↓, Load preset, Prepare transit and Target name stay active; Load/Prepare/name edits change the shared object name → `engine.on_object_changed()` mid-run (target set swapped, curves cleared) while the worker keeps writing the old object; row edits shift the active-step highlight | SP:983, 832, 880; `shell.py:176-179`; AE:1010-1022 |
| P10 | Loading a preset overwrites the observation object name; a calibration preset with `""` clears it and switches the target set to "Unknown" | SP:832, 840-848 |
| P11 | Silent substitution: unknown filter → first wheel slot, unknown frame type → Light **(verified)**; a filter missing after a wheel update → index 0; spin-box ranges clamp plan values on camera connect/disconnect (a 900 s preset loads as 600 s without a camera) | SP:695-702, 957-976, 930-955 |
| P12 | Preset load: `load_plan` is outside the `try`, so a wrong value type raises in the slot (reaches the global excepthook, `support_bundle.py:134`); an unknown key shows the raw Python `TypeError` text; no schema version | SP:918-924, SEQ:201-228 |
| P13 | The editor plan, programme choice and transit form values are not persisted | SP:579-582 |
| P14 | The run outcome is invisible on Plan: `set_running(False)` clears the status; completion, stop and worker errors are only in the log; start refusals only in the log (button snaps back); a second start while active is refused silently | SP:985-988, PG:73-77, AE:449-450, 512-513, 591-594 |
| P15 | One status label for step text, frame/ETA text, presets and transit messages: they overwrite each other; `set_progress` does not make it visible; the warning colour from "Add an enabled step" sticks | PG:305, SP:1016-1024, 1066-1068 |
| P16 | Pause gives no feedback until the frame boundary (button still "Pause"); pausing a cadence (transit) step breaks the cadence with no warning; ETA mean includes pause and AF time | SP:1056-1060, SW:225-227, 280-289 |
| P17 | Mid-run AF: 120 s handshake may be shorter than a 9-step sweep at up to 10 s exposures (**plausible, not measured**); AF uses the Observe camera card's exposure/gain, not the plan; AF options do nothing without a focuser, silently | SW:51, 485-503; AE:565-567, 701-706 |
| P18 | Readiness: a slewing mount (`busy`) reads "Ready · telescope offline"; site, wheel, focuser and target altitude are not checked | SP:1048-1049, `device_session.py:553` |
| P19 | With no selection, Remove/↑/↓/Dup act on the **last** row; Remove silently refuses the last row; Dup appends at the end | SP:743-760 |
| P20 | Dead check `s.count > 0` (Count minimum is 1) | SP:719, 1064 |
| P21 | TargetTable: after a refresh `clearSelection()` keeps the current row, so "Remove selected" with nothing visibly selected removes whichever star now sits there **(verified)**; buttons always enabled; no confirmation, undo or log | TT:59-61, 80-83 |
| P22 | VariableTable: no return to catalogue order after sorting; first column unlabelled (● = in the set, any role); "Set as target" enabled without selection; the filter keeps hiding image markers after the window is closed | VT:31, 111, 188-199; IP:1776-1779 |
| P23 | Dither semantics inconsistent (model says unsupported on Seestar, worker moves the mount); counter global, not per step | SEQ:44-46, SW:229, 249-278 |
| P24 | Estimate is a floor (no AF, wheel moves, dither ~4 s each) and gives no end time; the engine recomputes total frames separately | SEQ:178-198, AE:480 |
| P25 | `sequence_step` documented as FrameSpec but carries SequenceStep; `frame_started` never connected; the pass number (repeat) is never reported | AE:96, SW:95, 189 |
| P26 | Wasted space: page heading row; table capped at 420 px with an empty stretch below; default Sequence control dock (108 px) clips the readiness line (seen on the offscreen grab) | PG:47, SP:262-270, 558-562 |
| P27 | Spin boxes in table cells take wheel events by default: scrolling over the table can change exposure or count (**plausible**) | SP:705-737 |
| P28 | Suggestions read the cache file from disk on every keystroke on the UI thread | SP:592-593, `object_resolver.py:326-341` |
| P29 | Visibility plot: unexplained fixed 30° line, no target name, no "now", meaningless ticks when empty, pyqtgraph Export menu exposed | SP:126-131, 139-160 |
| P30 | "Dark" can be chosen as the filter of a Light/Flat step (opaque slot) without warning; the Filter cell stays editable on Dark/Bias rows where it is ignored | SP:698-703, SEQ:114-123 |
| P31 | `TargetSet.summary()` (target/comparison/check counts, `complete`) exists but no view shows it | TS:98-115 |

## 2. Web redesign

### 2.1 Placement in the new information architecture

The Plan section becomes one fixed screen built like Observe (rail | centre | right rail, BRAND 9 and 11.1):
the **steps table and the visibility timeline are the data** and get the centre; forms go to a 420 px right rail
of collapsible cards; the transport stays in the toolbar, always visible. No floating docks.

| Qt element | Web section → screen → region | Why |
|---|---|---|
| 1.1 page | Plan (F3) → Plan screen | owner's navigation |
| 1.1 heading "Plan" | dropped | the rail label and `aria-label` name the section; one row saved |
| 1.2 panel toggles | merged into card headers (fold / unfold) | same function, no extra strip (11.1 "no dead bands") |
| 1.2 #6 Reset panels | Settings → Appearance → "Reset panel layout" (all screens) | one reset for every screen, as View ▸ Reset Window Layout today |
| 1.3 docks | fixed regions; cards collapsible, state per viewer | web shell has no docking; multi-window is a Tauri question (Q11) |
| 1.4 steps table | Plan → centre → **Steps** region (top) | primary data |
| 1.4 estimate | Plan → Steps region header (frames, duration, end time) | next to what it sums |
| 1.5 source | Plan → right rail → **Source** card (first) | entry point of planning |
| 1.6 options | Plan → right rail → **Run options** card | run-level form |
| 1.7 visibility | Plan → centre → **Visibility** timeline (bottom, full centre width) | a time axis needs width; shows the planned run window and transit coverage |
| 1.8 presets + 1.10/1.11 | Plan → toolbar → **Presets** popover (server-side list) + "Open file…" / "Save as file…" (Tauri native dialogs) | presets are rare actions; a list is faster than a file dialog |
| 1.9 control | Plan → toolbar right: readiness chip, Start / Pause / Stop; Plan → **run strip** under the toolbar while running | always visible without scrolling |
| 1.9 readiness | Plan → toolbar → readiness chip → **Preflight** popover | more checks than fit in a label |
| 1.13 TargetTable | Plan → right rail → **Target set** card; the same component is reused by the Observe photometry panel (photometry spec) | the target set is keyed by the observation object chosen in Plan; Plan must show what will be measured |
| 1.12 VariableTable | **Observe → bottom drawer → "Field variables" tab** (beside the log); Plan's Target set card links to it | its filter drives the image markers and it needs a solved frame (Q1) |
| shell "●REC" strip, Plan dot | global status bar + rail dot (shell spec) | visible on every screen |

### 2.2 Control mapping

Display: I = icon only (tooltip + `aria-label`), I+L = icon + label, L = label. Shortcuts marked (p) are proposed.

| Qt ref | Web control | Decision | Icon id | Display | Shortcut |
|---|---|---|---|---|---|
| 1.1 heading | — | drop: rail label names the screen | — | — | — |
| 1.2 #1 | Source card header | merge: header folds the card | `search` | I+L (card title) | — |
| 1.2 #2 | Run options card header | merge | `camera` (inventory "Acquisition options") | I+L | — |
| 1.2 #3 | Visibility region | merge: fixed region; fold to a 28 px line | `visibility` | I+L | — |
| 1.2 #4 | Presets popover button | merge into toolbar | `bookmark` | I+L "Presets" | — |
| 1.2 #5 | toolbar transport | merge: always visible, never hidden | — | — | — |
| 1.2 #6 | Settings → Appearance "Reset panel layout" | move + merge with View ▸ Reset Window Layout | `layout-reset` | I+L | — |
| 1.3 #1-5 | — | drop: no docking in the web shell (fixed regions + collapsible cards, BRAND 11.1) | — | — | — |
| 1.3 #6-10 | — | drop: floating to another monitor is a Tauri multi-window decision (Q11) | — | — | — |
| 1.3 #11-15 | card fold | merge into card headers | `disclosure` | I | — |
| 1.3 #16-17 | — | drop: Presets and transport both live in the toolbar, no tabs needed | — | — | — |
| 1.4 #1 | "On" checkbox cell | keep | — | custom checkbox | Space (row focus) (p) |
| 1.4 #2 | Type cell, token menu Light / Dark / Flat / Bias | keep; never substitutes an unknown value: flags it | — | L | — |
| 1.4 #3 | Filter cell, token menu of wheel slots | keep; Dark/Bias rows show "Dark slot" read-only; unknown slot flagged, Dark on Light/Flat warned | — | L | — |
| 1.4 #4 | Exp (s) `NumberField` | keep; out-of-range flagged, not clamped; no wheel changes | — | mono | ↑/↓ |
| 1.4 #5 | Gain `NumberField` | keep (camera range) | — | mono | ↑/↓ |
| 1.4 #6 | Count `NumberField` | keep (1…9999) | — | mono | ↑/↓ |
| 1.4 #7 | Interval (s) `NumberField` | keep; disabled with tooltip when Cadence is set | — | mono | ↑/↓ |
| new (from hidden `cadence_s`) | Cadence (s) cell, empty = off | **expose** hidden state (P2); must be ≥ exposure | — | mono | ↑/↓ |
| 1.4 #8 | Dither cell, "off" at 0 | keep (Q5) | — | mono | — |
| new | Duration cell (per step, read-only) | add: count × period, makes the estimate checkable | — | mono | — |
| 1.4 #9 | row selection (`aria-selected`) | keep; nothing selected = row actions disabled (P19) | — | — | ↑/↓ |
| 1.4 #10 | — | drop column resize: fixed widths sized to the mono content | — | — | — |
| 1.4 #11 | Add step (inserts after selection, else at end) | keep | `add` | I | Insert (p) |
| 1.4 #12 | Duplicate step (inserts after the source) | keep | `duplicate` | I | Ctrl/⌘+D (p) |
| 1.4 #13 | Remove step + "Undo" toast | keep; last step removable (empty state) | `remove` | I | Delete (p), Ctrl/⌘+Z undo (p) |
| 1.4 #14 | Move up; also drag by the row number | keep | `move-up` | I | Alt+↑ (p) |
| 1.4 #15 | Move down | keep | `move-down` | I | Alt+↓ (p) |
| 1.5 #1 | Programme `Segmented` [Variable star \| Transit] | keep | `variable-star`, `transit` | I+L | — |
| 1.5 #2 | Source search field | keep; placeholder by programme | `search` (in field) | — | `/` focuses (p), Enter |
| 1.5 #3 | Suggestion listbox (token-drawn, debounced, server) | keep | — | L | ↑/↓, Enter |
| 1.5 #4 | Find (in-field button) | keep | `search` | I | Enter |
| 1.5 #5 | — | merge into 1.5 #2 (one field, programme decides the catalogue) | — | — | — |
| 1.5 #6 | — | merge into 1.5 #3 | — | — | — |
| 1.5 #7 | — | merge into 1.5 #4 (the inventory maps "Find planet" to `exoplanet`; the programme segment carries that glyph instead) | — | — | — |
| 1.5 #8 | Baseline `NumberField` "min each side" | keep; recomputes the window immediately (P5) | — | mono | — |
| 1.5 #9 | Exposure `NumberField` | keep | — | mono | — |
| 1.5 #10 | Cadence `NumberField`, live check ≥ exposure | keep | — | mono | — |
| 1.5 #11 | Gain `NumberField` | keep | — | mono | — |
| 1.5 #12 | Filter menu | keep | — | L | — |
| 1.5 #13 | Prepare transit sequence (asks before replacing a non-empty, unsaved plan) | keep | `transit` | I+L | — |
| new | "Observe ▸ Mount: target armed" link | add: Qt arms the slew silently in another screen | `goto` | I+L "Slew in Observe" (navigates, never slews) | — |
| 1.6 #1 | Object (FITS) field, shared with Observe | keep; locked while running (P9) | — | L | — |
| 1.6 #2 | Repeat plan `NumberField` "×" | keep | — | mono | — |
| 1.6 #3 | Autofocus every `NumberField` "frames, 0 = off" | keep; warns when no focuser | `autofocus` (label glyph) | I+L | — |
| 1.6 #4 | Autofocus on filter change checkbox | keep | — | L | — |
| 1.6 #5 | End of run `Segmented` [Nothing \| Stop tracking \| Park] | keep, same tooltip | `tracking`, `park` | I+L | — |
| 1.7 #1 | — | drop pan/zoom: fixed night window; hover readout instead | — | — | — |
| 1.7 #2 | — | drop pyqtgraph menu/Export: nothing to export from a planning curve | — | — | — |
| 1.7 #3 | — | drop auto-range: axes are fixed | — | — | — |
| 1.8 #1 + 1.10 | Save… popover (name, overwrite confirm) + "Save as file…" | keep, moved to toolbar | `save` | I+L "Save…" | Ctrl/⌘+S (p) |
| 1.8 #2 + 1.11 | Presets popover list + "Open file…" | keep, moved to toolbar | `bookmark`, `open-file` | I+L | — |
| new | delete preset (row action in the popover) | add: presets are now a list | `remove` | I | — |
| 1.9 #1 | Start sequence (primary) | keep; disabled with reason only when the server would refuse | `start` | I+L | — (deliberate) |
| 1.9 #2 | Pause ⇄ Resume | keep; "Pausing…" state | `pause` / `start` | I (pause), I+L "Resume" | — |
| 1.9 #3 | Stop (danger) + confirmation dialog | keep; confirm (Q7) | `stop` | I+L | — (Esc never stops a run) |
| 1.9 readiness | readiness chip → Preflight popover | keep + extend | status dot | L | — |
| 1.12 #1 | Field variables filter | keep (Observe drawer) | `search` (in field) | — | `/` when drawer focused (p) |
| 1.12 #2 | clear in field | keep | `close` | I | Esc in field |
| 1.12 #3 | "Brightest ≤" `NumberField`, empty = any | keep | — | mono | — |
| 1.12 #4 | row selection | keep | — | — | ↑/↓ |
| 1.12 #5 | header sort: ascending → descending → catalogue order | keep, fix P22 | NEW:`sort` | I | — |
| 1.12 #6 | double-click / Enter = set as target | keep | — | — | Enter |
| 1.12 #7 | Set as target (disabled without selection) | keep | `target-star` | I+L | — |
| 1.13 #1 | row select; double-click / Enter → Observe, star marked | keep (navigates from Plan) | — | — | Enter |
| 1.13 #2 | Remove from set (row action) + Undo toast | keep, fix P21 | `remove` | I | Delete (p) |
| 1.13 #3 | Copy TSV (same columns and header) | keep | `copy` | I | — |
| new | "Pick in field" (opens Observe, Field variables tab) | add: link from Plan to 1.12 | `variable-star` | I+L | — |

### 2.3 Wireframes

Reference 1440 × 900: rail 92 px, status bar 32 px, content 1348 × 868. Data in the wireframes are illustrative. Right rail 420 px (`--rail-min-w`, as
Observe). Centre 928 px. Glyph notation: `{id}` = icon id; `[ ]` = control; `▾` = menu; `○ □ △` = role shapes
drawn as icons (`target-star`, `comparison-star`, `check-star`).

**2.3.1 Plan, idle, variable star (default)**

```
┌──────┬──────────────────────────────────────────────────────────────────────────────────┬─────────────────────────────────────┐
│ ARGOS│ [{bookmark} Presets ▾] [{save} Save…]          ● Ready · 1 note ▾  [{start} Start sequence] [{pause}] [{stop} Stop] │ 40
│      ├──────────────────────────────────────────────────────────────────────────────────┤ {search} Source  [{variable-star} Variable star|{transit} Transit] ▾│
│ Conn │ {nav-sequencer} STEPS   3 steps · 50 frames · ≈ 21m 30s · ends ≈ 21:52 local    │ [{search} T CrB, RR Lyr, V404 Cyg…  ]│
│ Obs  │                                         [{add}][{duplicate}][{remove}][{move-up}][{move-down}] │ T CrB · Variable star              │
│▌Plan │ #  On  Type   Filter     Exp s   Gain  Count  Interval s  Cadence s  Dither  Duration│ RA 15h 59m 30.2s  Dec +25° 55′ 13″ │
│ Rev  │ 1  ☑   Light  IR         10.00     80     30        0.0          —     off   6m 30s│ CDS Sesame · cached                │
│      │ 2  ☑   Light  LP         30.00     80     10        0.0          —     off   5m 30s│ [{goto} Slew in Observe]           │
│      │ 3  ☐   Dark   Dark slot  30.00     80     10        0.0          —     off   5m 30s│─────────────────────────────────────│
│      │                                                                                  │ {camera} Run options             ▾ │
│      │   (rows 24 px; ~18 rows visible before the region scrolls)                      │ Object (FITS) [T CrB             ] │
│      │                                                                                  │ Repeat plan   [   1] ×              │
│      │                                                                                  │ Autofocus     every [  0] frames    │
│      │                                                                                  │               ☐ on filter change    │
│      │                                                                                  │ End of run [Nothing|{tracking}Stop tracking|{park}Park] │
│      ├──────────────────────────────────────────────────────────────────────────────────┤─────────────────────────────────────│
│      │ {visibility} VISIBILITY  T CrB · Paris (48.83° N) · night of 2026-11-01   Peak 63.2° 23:41 ▾│ {target-star} Target set  1 ○ 5 □ 0 △ ✓ [{copy}] ▾│
│      │ 90°┤                 ╭─────────╮                                               │ ○ T CrB         target   V 10.20 │
│      │    │           ╭─────╯         ╰──────╮                                        │ □ 000-BBC-123   VSP      V 10.81 │
│      │ 30°┤╌╌╌╌╌╌╌╌╌╌╱╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╲╌╌╌╌╌╌╌╌╌  min. altitude 30°        │ □ 000-BBC-124   VSP      V 11.02 │
│      │    │▕▓▓▓ planned run ▓▓▓▏       ▲ now 21:31                                     │ □ …                               │
│      │  0°┼────┬──────┬──────┬──────┬──────┬──────┬──────                            │ [{variable-star} Pick in field]   │
│      │     18:00  20:00  22:00  00:00  02:00  04:00  06:00 local · UTC on hover       │                                     │
├──────┴──────────────────────────────────────────────────────────────────────────────────┴─────────────────────────────────────┤
│ status bar (shell): connection · … · ●REC T CrB 12/50 ETA 6m 30s (while running) · theme · Log                             │ 32
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
 centre 928 px: toolbar 40 · Steps ≈ 560 · Visibility 240 (fold → 28)     right rail 420 px: Source ≈ 180 · Run options ≈ 190 · Target set rest
```

**2.3.2 Plan, running (row 2 active; editing locked)**

```
│ [{bookmark} Presets ▾] [{save} Save…]               ● Running   [{start} Start sequence](disabled) [{pause}] [{stop} Stop] │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ███████████████████░░░░░░░░░░░░  Step 2/3 · 10 × 30.0 s LP · pass 1/1 · frame 37/50 · ETA 6m 30s · ends ≈ 21:52        │ 28 run strip
│ last  tcrb_lp_light_e030000ms_g080_00007.fit  HFD 2.1 px · FWHM 2.6 px · 143 stars · 21:45:12 UTC         [log ▸]     │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ STEPS  (locked while the sequence runs: edits wait for the end)                                                          │
│ 1  ☑ Light IR  10.00  80  30  0.0  —  off  6m 30s   ✓ done 30/30                                                         │
│▌2  ☑ Light LP  30.00  80  10  0.0  —  off  5m 30s   ● 7/10        ← active row: --selection-bg + left accent bar         │
│ 3  ☐ Dark  …                                         skipped                                                             │
```

Paused: chip "● Paused", pause button becomes `[{start} Resume]`, strip text "Paused after frame 37 · cadence
broken" (cadence rows only). Pausing (between click and frame boundary): chip "● Pausing after this frame…".
Autofocus: chip "● Autofocus", strip "Autofocus pass (step 4/9)".

**2.3.3 Source card, Transit programme**

```
┌ {search} Source  [{variable-star} Variable star|{transit} Transit] ▾ ┐
│ [{search} HD 189733 b, WASP-12 b…                              ]   │
│ HD 189733 b — host HD 189733                                        │
│ P 2.21857567 d · duration 1.84 h · depth 2.4 % · epoch BJD_TDB     │
│ Next mid-transit  BJD 2461347.41234 (E = 3254)                      │
│ Coverage  01:12 → 05:02 local · 00:12 → 04:02 UTC · 3.84 h          │
│ ⚠ Mid-transit at 18° altitude; coverage ends below 30°  (if so)    │
│ Baseline  [  60] min each side   Exposure [10.00] s                 │
│ Cadence   [13.0] s               Gain     [  80]                     │
│ Filter    [IR ▾]                                                    │
│ [{transit} Prepare transit sequence]                                │
└─────────────────────────────────────────────────────────────────────┘
```

**2.3.4 Presets popover (toolbar, 360 px)**

```
┌ Presets ─────────────────────────────────────┐
│ [{search} Filter presets              ]      │
│ T CrB nightly          2026-10-28  [{remove}]│
│ Darks 30 s x 20        2026-10-12  [{remove}]│
│ Transit HD 189733 b    2026-09-30  [{remove}]│
│──────────────────────────────────────────────│
│ [{open-file} Open file…]                      │
└──────────────────────────────────────────────┘
 Save… popover:  Name [T CrB nightly        ]  [Save]   → "Replace "T CrB nightly"?" [Replace] [Cancel]
                 [{save} Save as file…]
```

Loading a preset when the draft has unsaved changes: dialog "Replace the current plan? Unsaved steps are lost."
[Replace] [Cancel]. A preset's object name is applied only if non-empty (fix P10).

**2.3.5 Preflight popover (readiness chip)**

```
┌ Preflight ───────────────────────────────────────────┐
│ ● Camera            connected (Seestar S50)          │
│ ● Object name       T CrB                            │
│ ● Mount             tracking                         │
│ ● Observing site    Paris · saved                    │
│ ● Filter wheel      IR, LP, Dark · all steps match   │
│ ○ Focuser           not connected · AF options off   │
│ ▲ Altitude          ends at 24° (below 30°)          │
│ ● Output folder     ~/Argos/sessions · writable      │
└──────────────────────────────────────────────────────┘
 chip: "Ready" | "Ready · 1 note" | "Blocked · camera"  (label always present; dot = tone)
```

**2.3.6 Stop confirmation (modal, text buttons)**

```
┌ Stop the sequence? ───────────────────────────────────┐
│ The current 30 s exposure is discarded. 37 of 50      │
│ frames are saved in 20261101T204502Z_T_CrB.           │
│ The end-of-run mount action is not applied.           │
│                               [Keep running] [Stop]   │
└───────────────────────────────────────────────────────┘
```

**2.3.7 Observe → bottom drawer → "Field variables" tab (shares the log drawer, 240 px)**

```
┌ [Log] [{variable-star} Field variables 12/41] ────────────────────────────────────────────────────────── [{close}] ┐
│ [{search} Filter by designation or type…   ]  Brightest ≤ [ any ]  12 of 41 stars       [{target-star} Set as target] │
│ Role  Name ↓{sort}   Type   Mag            Period (d)   Sep (′)                                                     │
│ ○     XX Cyg         RRAB   11.3 – 12.9    0.1349        3.2                                                        │
│       V0534 Cyg      EA     12.6 – 13.4    1.2280        8.7                                                        │
│       (suspected rows in --text-muted)                                                                              │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
 Empty: "Identify the field (S) to list its catalogued variables." · Loading: "Loading VSX for this field…"
```

### 2.4 Interaction and states

| State | Behaviour |
|---|---|
| Server unreachable / token rejected | Plan shows the shell's banner; the draft stays visible read-only; transport disabled with reason |
| No camera | Start disabled (`aria-disabled`, tooltip "Connect the camera first"); plan editing stays available (Qt allows offline planning) |
| No site saved | Visibility region: "Set the observing site in Settings to compute altitudes." with a link; no 0/0 curve (P4); transit coverage disabled with the same message (P6 text fixed) |
| No source yet | Visibility: "Find a source to see its altitude tonight."; Target set: "No photometry target yet. Find a variable star, or pick one in the solved field." |
| Lookup busy | spinner in the Find button (BRAND 8), field read-only; server cancels on a new query |
| Lookup error | message under the field, exact server text (1.5 list), plus a log line; no toast for "not found" |
| Empty plan | Steps region: "No steps. Add a step or open a preset." Start disabled |
| Invalid cell | outlined `--danger`, message in words under the row; Start disabled with "Fix step 2: cadence shorter than exposure" |
| Running | everything that changes the plan or the object is locked (`aria-disabled`, tooltip "Locked while the sequence runs"): steps, Run options, Source Prepare, preset open; Presets save stays available; Field variables and Target set stay editable (in-run target-set edits are legitimate and journalled, AE:995-1008) |
| Pausing / Paused / Autofocus | chip and strip text as in 2.3.2 |
| Finished | the run strip stays with the outcome until dismissed: "Sequence complete · 50 frames · 21:52 · end of run: park" / "Stopped by the observer after 37 frames" / "Stopped: Exposure timeout after 45s" (P14); toast and log line too |
| Start refused | inline message under the transport with the server text (409), plus toast |

- **Confirmations**: Stop (2.3.6); replacing an unsaved plan (preset open, transit prepare); overwriting a preset.
  Removing a step or a target-set star is immediate with an Undo toast (6 s).
- **Keyboard**: F3 opens Plan; `/` focuses the source search; Insert / Ctrl/⌘+D / Delete / Alt+↑↓ act on the
  focused step row when focus is not in a field; Space toggles "On"; Ctrl/⌘+S opens Save. No single key starts,
  pauses or stops a run; Escape never stops a sequence (consistent with Observe, where Escape aborts a slew only).
- **Night Red**: all menus (Type, Filter, presets, suggestions) are token-drawn, no native `<select>`; the planned
  run band is an outlined band and the transit coverage a hatched band, so they differ by pattern, not hue; the
  altitude curve uses `--chart-1`, the limit line `--chart-reference` with a text label, "now" `--chart-highlight`;
  status chips always carry their label; no Unicode pictographs (the Qt "▶ ⏸ ■ ＋ ⧉ － ↑ ↓ ●" become icons).
- **Formats**: RA/Dec per BRAND 5 (Qt shows decimal "RA 15.99172 h"); exposures with 2 decimals "s"; durations
  "1h 05m" / "12m 30s"; times local with UTC on hover; BJD with 5 decimals in labels (6 in tooltips, as Qt).
- **Persistence**: draft plan server-side (Q3); presets as files in `data_paths.sequence_presets_directory`;
  object name server-side (shared with Observe); card folds (`argos.card.plan.*`), programme choice and transit
  form values (`argos.plan.transit`) in per-viewer prefs; `ui.sequencer.layout` dropped.
- **Visible without scrolling at 1440 × 900**: toolbar (presets, readiness, transport), run strip, the first ~18
  steps, the whole visibility timeline, Source and Run options cards, the Target set header (counts) and its first
  rows.

### 2.5 API needs beyond v1

| Name | Kind | Payload sketch | Wraps (file:line) | Notes |
|---|---|---|---|---|
| Sequence draft | `GET` / `PUT /api/sequence/plan` | `SequencePlan` JSON (`plan_to_dict` + `"schema": 2`) → `{plan, derived: {total_frames, estimate_s, per_step_s[]}, issues: [{step, field, code, message}]}` | SEQ:28-91, 172-228 | server-side validation (types, ranges vs camera caps, filter ∈ wheel names, cadence ≥ exposure); persisted draft (Q3); keeps `metadata` (P1) |
| Presets | `GET /api/sequence/presets`; `GET`/`PUT`/`DELETE /api/sequence/presets/{name}` | list `[{name, modified_utc}]`; body = plan; `?overwrite=true` | SP:888-924 | directory from `data_paths.sequence_presets_directory`; reads schema-less legacy files |
| Preset file import / export | `POST /api/sequence/plan/import`, `/export` | `{"path": "<absolute .json>"}` | SP:898-924 | for Tauri native dialogs; same path rules as `open-fits` |
| Run control | `POST /api/sequence/start` · `/pause` · `/resume` · `/stop` | start: `{}` (uses the draft) | AE:444-499 | 409 `not_connected` "Connect the camera before running a sequence."; 409 `busy` (sequence active, AF owns camera); 400 `invalid_argument` (no enabled step, invalid cells); start pre-empts live view |
| Sequence state | WS `{"type":"sequence","sequence":SequenceState}` | `{state: idle\|running\|pausing\|paused\|autofocus\|stopping, object_name, run_id, run_root, step_index, step, pass_index, repeat, frames_done, frames_total, eta_s, started_utc, current: {exposure_s, started_utc}\|null, last_result: {completed, reason, message, frames_saved, ended_utc}\|null}` | AE:93-96, 506-513, 584-596; SW:94-102 | needs `pass_index`, "pausing" (set on request) and `frame_started` (SW:95, unconnected today) |
| Saved frame | WS `{"type":"sequence_frame","path","record":FrameRecord}` | FrameRecord fields of `session_log.py` | AE:97, 532-557; SW:424-439 | feeds the run strip and Review |
| Preflight | `GET /api/sequence/preflight` (+ in `sequence` events) | `[{id, level: ok\|note\|block, message}]` | SP:1037-1054 + new checks | engine stays the authority; blocks only what the engine would refuse |
| Object name | `GET`/`PUT /api/observation` + WS `observation` | `{"object_name": "T CrB"}` | `shell.py:176-179`, AE:971-986, 1010-1022 | single source for Observe and Plan; refused (409 busy) while a sequence runs |
| Resolve object | `GET /api/catalog/resolve?q=` | → `{name, ra_deg, dec_deg, object_type, object_type_label, is_variable, source}` | `object_resolver.py:369`, `:116`, `:136` | ≤ 8 s; 404 `not_found` / 502 `catalogue_unavailable` with the exact texts |
| Object suggestions | `GET /api/catalog/suggest?q=&limit=8` | → `["T CrB", …]` | `object_resolver.py:326` | local only; client debounces 150 ms; server caches the file (P28) |
| Exoplanet lookup | `GET /api/exoplanets/lookup?q=` · `GET /api/exoplanets/suggest?q=` | → `ExoplanetTarget` fields · names | `exoplanets.py:368`, `:299` | ≤ 2 × 12 s; cancellable |
| Transit window | `POST /api/transit/predict` | `{planet_name, baseline_minutes, from_utc?}` → `{window: TransitWindow, local: {start, mid, end}, utc: {…}, altitude: {at_start, at_mid, at_end}}` | `transit.py:34-68`, PG:132-187, `airmass.py:52-101` | 409 `site_missing`; ValueError texts as 400 |
| Transit plan | `POST /api/transit/plan` | `{planet_name, baseline_minutes, exposure_s, cadence_s, gain, filter_name}` → plan (becomes the draft, with metadata) | `transit.py:71-122`, PG:248-286 | keeps `metadata` so `observation.json` is written (P1) |
| Visibility | `GET /api/visibility?ra_hours=&dec_deg=&night=YYYY-MM-DD&step_min=10` | → `{site, samples: [{t_utc, alt_deg}], peak: {t_utc, alt_deg}, window: {start_utc, end_utc}, min_alt_deg}` | `sky_geometry.py:60-88` | site from settings with the `site.name` guard (P4); `night` chosen by the client (fixes P3) |
| Science source | `POST /api/targets/science-source` | `{programme: variable\|exoplanet, name, ra_deg, dec_deg, object_type, source}` | IP:2658-2720 (to move into a Qt-free service) | arms the mount target, sets the object name, sets the photometry target (variable types only, Q8) |
| Target set | `GET /api/targets` · `DELETE /api/targets/{key}` · WS `targets` | `{object, stars: [{key, role, display_name, ra_deg, dec_deg, auid, source, mags, chart_id, note}], summary}` | AE:980-1031, 1235-1240; TS:98-122 | `summary` = TS:98 (P31) |
| Field variables | `GET /api/field/variables` · WS `catalog` · `POST /api/targets/from-variable` | rows `{index, name, var_type, mag_text, brightest_mag, period_d, sep_arcmin, in_set_role, suspected}`; body `{index}` | IP:2202-2240, AE:225-227, 904-917 | in-frame filter needs the server-side WCS projection; overlay filtering stays client-side |
| Device vocabulary | `CameraState.capabilities` + WS `filterwheel` | `{gain_min, gain_max, exposure_min, exposure_max}`; `{names: [], position, moving}` | PG:65-69, 310-323 | probably shared with the Camera/Observe spec |
| Camera owner | `CameraState.owner` | `"live"\|"single"\|"sequence"\|"autofocus"\|null` | `camera_service.py:81-170` | Observe must show "camera owned by the sequence" |

## 3. Open questions for the owner

1. **Field variables placement**: Observe bottom drawer (recommended: its filter drives the image markers and it
   needs a solved frame) or a Plan region?
2. **Scheduled start**: add "Start at" (wait until a local time, e.g. transit coverage start) to the run? It needs a
   worker change and a new icon (`scheduled-start`).
3. **Draft persistence**: keep the editor plan server-side across restarts (recommended)? Where (config, or a
   `sequence_draft.json` beside `config.json`)?
4. **Presets**: server-side list in the presets folder plus file import/export (proposed), or file dialogs only?
5. **Dithering on a Seestar**: keep the column (the worker moves the mount), hide it behind a column toggle, or
   remove it? The model docstring says unsupported.
6. **Visibility limit and night**: make the 30° line a site setting? Add twilight and Moon (needs Sun/Moon
   ephemerides offline)? Night window 18:00-06:00 local or astronomical dusk to dawn?
7. **Stop confirmation**: confirm (proposed, 2.3.6) or immediate as in Qt?
8. **Plan Find on a non-variable** (M 42): should it still create a photometry target (Qt today, P8) or only set the
   observation and pointing (recommended)?
9. **Mid-run autofocus parameters**: keep using the Observe camera card's exposure and gain, or carry AF exposure,
   gain and step count in the plan? Raise the 120 s handshake?
10. **Several objects per night**: the model has one `object_name` per plan. Is a multi-target night in scope?
11. **Second monitor**: the Qt docks can float; should Tauri offer a detachable Plan or visibility window?
12. **Next observable transit**: let the observer choose the date or skip transits that are in daylight or below the
    limit, rather than "next midpoint after now"?
13. **Editing while running**: keep the plan locked (proposed) or allow editing future steps?
