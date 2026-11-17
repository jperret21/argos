# Hardware controls (camera, mount, focuser, focus quality): Qt inventory and web redesign

Branch `explore/web-ui`, read on 2026-11-01. Every `file:line` refers to the working tree at that date.
Paths are relative to the repo root; `ip` = `argos/ui/pages/imaging_page.py`, `ds` = `argos/core/session/device_session.py`,
`ae` = `argos/core/session/acquisition_engine.py`.

## 0. Scope

### Files covered

| File | Lines | Role |
|---|---|---|
| `argos/ui/widgets/camera_dock.py` | 390 | Camera form (dock "Acquisition") |
| `argos/ui/widgets/mount_dock.py` | 476 | Mount control (dock "Telescope"), inline jog pad, catalogue lookup, Stellarium suggestion |
| `argos/ui/widgets/focuser_dock.py` | 221 | Focuser control + autofocus (dock "Focusing") |
| `argos/ui/widgets/vcurve.py` | 128 | V-curve plot inside the focuser dock |
| `argos/ui/widgets/hfd_history_dock.py` | 136 | HFD / #Stars trend (dock "Focus diagnostics (HFD/FWHM)") |
| `argos/ui/widgets/metrics_panel.py` | 80 | Session metrics plot (tab "Metrics" of the Field photometry window) |
| `argos/ui/panels/manual_control_dialog.py` | 215 | Floating jog dialog "Manual Control" |
| Behaviour read from | | `argos/workers/autofocus_worker.py` (232), `camera_service.py` (228), `exposure_worker.py` (161), `polling_worker.py` (137); wiring in `ip` (2888, sections cited), `ds` (840), `ae` (1652); devices in `argos/core/alpaca/{camera,telescope,focuser,filterwheel}.py`; `argos/core/imaging/focus.py`, `metrics.py`, `debayer.py`; `argos/core/catalog/object_resolver.py`; `argos/workers/object_resolver_worker.py`, `sequence_worker.py`; `argos/ui/widgets/dock_host.py`, `argos/ui/design.py`, `argos/ui/shell.py` |

Optional offscreen renders of the Qt widgets (fake data) were made to confirm layouts; they are not part of the spec.

### Elements in scope

| # | Element | Class, file:line | Kind | How opened | Modal | Placement |
|---|---|---|---|---|---|---|
| E1 | Camera form | `CameraDock`, camera_dock.py:82 | Card in QDockWidget "Acquisition" (ip:280) | Visible by default, front tab of the right dock stack (ip:460-468); panel chip "Acquisition" (ip:354-364) | No | Right dock area |
| E1a | Optional sensor rows (Offset, Binning) | camera_dock.py:152-174 | Hidden rows | Shown when the driver proves support (ip:661-669) | No | Inside E1 |
| E1b | Sequence-lock hint | camera_dock.py:213-216 | Label | While a sequence or autofocus owns the camera (ip:638) | No | Inside E1 |
| E2 | Mount control | `MountDock`, mount_dock.py:57 | Card in QDockWidget "Telescope" (ip:281) | Tab behind "Acquisition" (ip:466-467); chip "Telescope" | No | Right dock stack |
| E2a | Catalogue lookup result | mount_dock.py:152-160 | Sub-panel (label + button) | After Find / Return in the Object field | No | Inside E2 |
| E2b | Stellarium target suggestion | mount_dock.py:165-187 | Sub-panel | After a Stellarium GoTo (shell.py:346-353 -> ip:2733) | No | Inside E2 |
| E2c | Inline jog pad | mount_dock.py:224-265 | Button cross | Always in E2 | No | Inside E2 |
| E3 | Park confirmation | `QMessageBox.question`, mount_dock.py:426-435 | Native message box | Park button | **Modal** | Centred on window |
| E4 | Focuser control | `FocuserDock`, focuser_dock.py:38 | Card in QDockWidget "Focusing" (ip:282) | Tab behind "Acquisition"; chip "Focusing" | No | Right dock stack |
| E4a | Autofocus status line | focuser_dock.py:122-129 | Label | During / after autofocus | No | Inside E4 |
| E5 | V-curve | `VCurveWidget`, vcurve.py:20, embedded focuser_dock.py:135-137 | pyqtgraph plot + summary | Shown at first autofocus start, stays visible (focuser_dock.py:185-189) | No | Inside E4 |
| E5a | V-curve context menu | pyqtgraph 0.13.7 default (`PlotWidget`, vcurve.py:31) | Context menu | Right-click on the plot | No | Pop-up |
| E6 | HFD history | `HfdHistoryDock`, hfd_history_dock.py:25 | Card in QDockWidget "Focus diagnostics (HFD/FWHM)" (ip:289-294) | Hidden by default (ip:451); "Panels ▾" menu entry (ip:366-375) | No | Right dock area |
| E6a | HFD history context menu | pyqtgraph default (hfd_history_dock.py:46) | Context menu | Right-click | No | Pop-up |
| E7 | Session metrics | `MetricsPanel`, metrics_panel.py:26 | Tab "Metrics" of the "Field photometry" window (photometry_window.py:224, :232) | Shell menu Photometry -> "Live curves & diagnostics…" (shell.py:278); the window itself belongs to the photometry spec | No | Separate window |
| E8 | Manual Control | `ManualControlDialog`, manual_control_dialog.py:66 | QDialog, `Tool` + `WindowStaysOnTopHint`, fixed 280 x 320 (manual_control_dialog.py:88-96) | "Jog dialog…" (mount_dock.py:276 -> ip:2790-2798); one instance, re-shown | No | Floating, stay-on-top |
| E9 | Dock chrome of E1, E2, E4, E6 | ip:280-294, :348-414; dock_host.py:48-75 | Panel chips, Panels ▾ entry, Arrange ▾ entries, dock title bar | Panel strip above the image | No | Imaging page (shared with the Observe layout spec) |

- No tooltip-driven popovers in scope (plain tooltips only). No explicit context menus; E5a / E6a are pyqtgraph defaults. `MetricsPanel` disables its menu (metrics_panel.py:47).
- **Filter wheel**: no dedicated window. The wheel is driven by the E1 "Filter" combo (comment ip:470-472); its state badge is in the status bar (statusbar.py, status-bar spec).
- **No Qt keyboard shortcut** exists for any control in scope, except the arrow keys inside E8 (manual_control_dialog.py:184-205). Shell shortcuts (F1…F5, Ctrl+O, Ctrl+Shift+O, Ctrl+Q) are outside this area.
- Layout persistence: the whole dock arrangement is saved under config key `ui.imaging.layout` (ip:121, save ip:495-498). No control value in scope is persisted.

## 1. Inventory (Qt, as it is today)

### 1.1 Camera form (`CameraDock`, camera_dock.py:82, card in dock "Acquisition", opened by default, non-modal, right dock stack)

- Purpose: single-shot / live preview parameters for framing and focusing (the full acquisition plan lives in the Plan section). Also holds the shared observation identity ("Object") and the filter selection that physically moves the wheel.
- Construction: `set_enabled(False)` at creation (camera_dock.py:99); only Live / Take shot are gated, the form stays editable while disconnected (camera_dock.py:244-248).

| # | Control | Qt type | Label / tooltip (exact text) | Default / range / step / units | Enabled or visible when | Shortcut | Action: handler file:line -> effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Type | QComboBox (camera_dock.py:117) | "Type"; no tooltip | "Light Frame", "Dark Frame", "Flat Frame", "Bias Frame" (camera_dock.py:57); default Light Frame | Always; disabled under lock (camera_dock.py:250-269) | — | No signal. Read through `params()` camera_dock.py:231 (provider, ip:217). `_is_light_frame` ae:80 -> `light=False` for Dark/Bias in `LivePreviewWorker.start_exposure` (exposure_worker.py:116, `Camera.start_exposure` camera.py:350). FITS IMAGETYP, folder and file name (ae:1536-1551, :1587). **Does not move the wheel to the opaque slot** (problem P1) | No |
| 2 | Object | QLineEdit (camera_dock.py:122) | "Object"; placeholder "M42, T CrB…" | Free text; empty becomes "Unknown" (camera_dock.py:234) | Always; disabled under lock | Return / focus-out commits | `editingFinished` -> `_on_object_edited` camera_dock.py:340 -> `object_changed` -> `AcquisitionEngine.on_object_changed` ae:1010 (reload the target set keyed by name, clear live curves, reset aperture tracker, emit `targets_changed`) and `object_name_changed` -> Plan `set_object_name` (shell.py:170). Written programmatically by a catalogue lookup (ip:2664, overwrites), by star picks only if empty (ip:2028, :2240; camera_dock.py:321-329) and by Plan (shell.py:176-179). FITS OBJECT + session folder (ae:1522, :1536) | No (target set files are keyed by it) |
| 3 | Filter | QComboBox (camera_dock.py:132) | "Filter"; no tooltip | "IR", "LP", "Dark" before connect (camera_dock.py:61); replaced by the wheel slot names at wheel connect (ip:672-678 -> camera_dock.py:344-354); default first item | Always; disabled while the wheel turns (camera_dock.py:362-364) and under lock | — | `activated` (user only, camera_dock.py:135) -> `filter_selected` -> `_on_camera_dock_filter` ip:690: no wheel -> WARN, name kept as metadata; no slot match -> WARN; else `_on_filter_move` ip:684 -> `set_filter_moving(True)` + `DeviceSession.move_filter` ds:681 (state "busy", off-thread `_FilterMoveRunnable` ds:70: `FilterWheel.set_position` filterwheel.py:103, poll every 0.15 s up to 20 s) -> `filter_moved` -> `_on_filter_moved` ip:705 re-enables and syncs the combo. Value also used as FITS FILTER and folder (ae:1523, :1540) | No |
| 4 | Exposure slider | QSlider in `SliderSpin` (camera_dock.py:142; design.py:179) | "Exposure"; no tooltip | Log scale, 1000 steps; 0.01–600 s fallback (camera_dock.py:65), driver ExposureMin (floored to 0.01 s) – ExposureMax after connect (camera_dock.py:286-291); default 10.0 s | Always; disabled under lock | — | Syncs the value box. Read per frame: `ae._on_frame` ae:392-403 -> `LivePreviewWorker.update_settings` exposure_worker.py:67 (next frame). Autofocus uses `min(exposure, 10 s)` (ae:692-716) | No |
| 5 | Exposure value | QDoubleSpinBox in `SliderSpin` | suffix " s" | 2 decimals, step 1.0 s | same as #4 | — | same as #4 | No |
| 6 | Gain slider | QSlider in `SliderSpin` (camera_dock.py:149) | "Gain"; no tooltip | Linear; 0–600 fallback (camera_dock.py:64), driver GainMin–GainMax after connect (camera_dock.py:281-284); default 80 | same | — | `LivePreviewWorker` calls `set_gain` before every frame (exposure_worker.py:108-111); FITS GAIN; e-/ADU lookup for batch photometry (ip:2328). Not applied by autofocus (P8) | No |
| 7 | Gain value | QSpinBox in `SliderSpin` | — | Integer, step 1 | same | — | same as #6 | No |
| 8 | Offset | QSpinBox (camera_dock.py:156) | "Offset"; no tooltip | Driver OffsetMin–OffsetMax, value read from the driver (camera_dock.py:293-300) | Hidden until `set_offset_support` (ip:666-667); hidden again on disconnect (camera_dock.py:311-319); disabled under lock | — | `valueChanged` (every keystroke / arrow step) -> `offset_changed` -> `_on_camera_offset` ip:2504: if Sequence/Autofocus owns the camera -> WARN + re-read the device value; else `ds.set_camera_offset` ds:741 -> `Camera.set_offset` camera.py:251 (clamped) | Device only |
| 9 | Binning | QSpinBox (camera_dock.py:166) | "Binning"; suffix "×" | 1 – MaxBin | Hidden until `set_binning_support` when MaxBin > 1 (ip:668-669) | — | `valueChanged` -> `binning_changed` -> `_on_camera_binning` ip:2519 (same refusal) -> `ds.set_camera_binning` ds:750 -> `Camera.set_binning` camera.py:274 | Device only |
| 10 | Preview | QComboBox (camera_dock.py:180) | "Preview"; tooltip "Preview decimation for display only — saved FITS stay full resolution" | "Full res" (scale 1), "Half res" (scale 2) (camera_dock.py:68); default Full res | Always; disabled under lock | — | `activated` -> `preview_scale_changed` (connected nowhere, P33). The engine reads `preview_scale()` at preview start and every frame (ae:358, :401) -> `downsample_cfa` (exposure_worker.py:139-140). Decimated frames are flagged so plate solve / photometry skip them (ae:411) | No |
| 11 | Live / Stop live | `SuccessButton`, becomes danger (camera_dock.py:204, :271-277) | "▶  Live" / "■  Stop live"; tooltip "Continuous preview loop for framing and manual focusing" | Toggle | Enabled when the camera is connected/busy (ip:650-651) | — | `_on_live_clicked` camera_dock.py:386 -> `ae.start_live` ae:332 (acquire LIVE through `CameraService.acquire` camera_service.py:138; refused with a reason when sequence/autofocus owns the camera) / `ae.stop_live` ae:345 (release). Label follows the ownership state (ip:631-634) | No |
| 12 | Take shot | `PrimaryButton` (camera_dock.py:207) | "◉  Take shot"; tooltip "Expose one frame and save it (for framing / focus checks)" | — | Enabled when the camera is connected | — | `take_shot_clicked` -> `ae.take_shot` ae:317: during Live, tags the next live frame for saving; else acquires SINGLE (starts the preview loop), saves one full-resolution FITS through `_save_fits_async` ae:1510 (QThreadPool), then releases (ae:423-430) | No |

**Displayed data**

| Readout | Source | Refresh |
|---|---|---|
| HFD (camera_dock.py:195) | `set_hfd` camera_dock.py:366, fed by `_on_processed` ip:745 (`frame_metrics` metrics.py:146 -> `compute_hfd` debayer.py:284, brightest star, green-plane px of the **displayed** array) | Every processed frame. Text "{:.1f} px", colour `stat_color` ok < 5, warn < 10 px (camera_dock.py:372; design.py:431) |
| Temp (camera_dock.py:199) | `set_temperature` camera_dock.py:378 <- `ds.camera_temperature` (ip:522) <- `TemperaturePollingWorker(Camera.get_ccd_temperature)` (ds:507-511; polling_worker.py:96) | Every 10 s (polling_worker.py:93); "—" on disconnect (camera_dock.py:319). Text "{:.1f}°C" |
| Lock hint (camera_dock.py:213) | `set_sequence_lock` | On ownership change |

**Implicit behaviours**

- Ownership state machine (`CameraService`, camera_service.py:60-207): IDLE, LIVE, SINGLE, SEQUENCE, AUTOFOCUS; priority SEQUENCE > AUTOFOCUS > LIVE/SINGLE (camera_service.py:71-77). A higher-priority owner preempts the preview loop. State -> status bar text "Idle" / "Live preview" / "Taking shot…" / "Sequence running" / "Autofocus running" (ip:126-132, :633).
- Lock: the whole form is disabled while SEQUENCE **or AUTOFOCUS** owns the camera (ip:638).
- Live loop (exposure_worker.py:101-161): set gain, StartExposure, poll ImageReady every 100 ms, timeout exposure + 20 s, download, decimate, emit; status texts go to the status bar (ae:362).
- Connect: driver limits pushed into the form, offset/binning rows appear (ds:392-415 -> ip:661-669). Disconnect: `camera_will_disconnect` stops the preview first (ae:432-440), then limits reset and extra rows hide (ip:652-653).
- Wheel connect: combo items replaced by the slot names, synced to the real slot (ip:672-678).
- Picking a star / catalogue target prefills Object (see #2).

**Messages** (log level, exact text, when)

- WARN "Camera not connected." (ae:318, :333, :351) — Live / Take shot without camera.
- CMD "Take shot — saving next frame…" (ae:325, :330); OK "Saved {name}" / ERROR "FITS save failed: {exc}" (ae:1591-1593).
- CMD "Live preview started." (ae:343); INFO "Live preview stopped." (ae:347).
- WARN refusals (camera_service.py:81-86): "Sequence running — the sequence owns the camera. Stop it first." / "Autofocus running — it owns the camera. Wait for it to finish." / "Live preview running — it owns the camera. Stop it first." / "A single shot is in progress — wait for it to finish."
- INFO "Live preview stopped — the sequence owns the camera." / "Live preview stopped — autofocus owns the camera." (camera_service.py:164-166).
- ERROR "Preview: {msg}" (ae:379), e.g. "Exposure timeout — no image after expected duration" (exposure_worker.py:124).
- Status: "Exposing  {exp:.1f}s…", "Downloading…", "Live  {exp:.1f}s  gain {g}  preview {w}×{h}" + "  (1/{s}²)" (exposure_worker.py:114, :133, :149-153).
- WARN "Filter wheel not connected — '{name}' is metadata only." (ip:694-697); WARN "No wheel position matches filter '{name}'." (ip:700); CMD "Filter → {name}" (ds:699); ERROR "Filter move: {exc}" (ds:93-94).
- WARN "{Sequence\|Autofocus} running — it owns the camera. Stop it first." (ip:2512, :2527); CMD "Offset → {v}", ERROR "Offset: {exc}" (ds:746-748); CMD "Binning → {v}×{v}", ERROR "Binning: {exc}" (ds:755-757).
- INFO "Camera limits: gain {a}–{b}, exposure {x}–{y}s[, offset][, bin ≤{n}]" (ds:409-415).
- Lock hint: "Sequence running — the sequence owns the camera." (camera_dock.py:213).

**Problems found**

- P1 (science data) Dark / Bias single shots do not move the wheel to the opaque "Dark" slot. On the shutterless Seestar the wheel is the only shutter (sequencer.py:115-123, field bug 2026-07-11, fixed for sequences only). A "Dark Frame" Take shot is a light frame tagged IMAGETYP=Dark unless the observer also picks "Dark" in Filter (camera_dock.py:57; ae:80-83, :349-359).
- P2 A failed wheel move leaves the Filter combo disabled for the session: `_FilterMoveRunnable` logs the AlpacaError but never emits `done` (ds:85-94), so `set_filter_moving(False)` (ip:707) never runs and the wheel state stays "busy" (ds:684). A wheel that does not settle in 20 s emits name "Moving…" (filterwheel.py:133), which `set_current_filter` cannot match (stale display).
- P3 (metadata) The sequence moves the wheel directly (`SequenceWorker._set_filter`, sequence_worker.py:291-304) without `filter_moved`, so after a run the Filter combo still shows the pre-run filter; the next Take shot writes that stale name to FITS FILTER and the folder (ae:1523, :1540).
- P4b (metadata, derived from code, not reproduced) Take shot reads exposure, gain, frame type and filter **when the frame arrives** (`_save_fits_async` calls `self._params()` again, ae:1511), not the values the frame was exposed with. Editing Exposure during a live exposure and pressing Take shot can write the new EXPTIME/GAIN for a frame taken with the old ones (ae:392-430, :1510-1551).
- P13 HFD is measured on the displayed array (`_show_raw(frame.preview)` ip:2581; preview_processor.py:71): with Preview = Half res it is in decimated green px (about half), so the colour thresholds 5 / 10 px (camera_dock.py:372) and the HFD history mix two scales. It is the brightest star's HFD (debayer.py:284-303), possibly saturated.
- P14 The same HFD is shown three times: camera form (camera_dock.py:195), HFD history (hfd_history_dock.py:82), status-bar strip (shell.py:314; statusbar.py:227).
- P15 Two different "Object" fields: here the observation identity (FITS OBJECT, target-set key); in the mount panel a catalogue search query (mount_dock.py:138). A catalogue result overwrites this field even when the observer typed a name (ip:2664), contradicting `set_object_name_if_empty` (camera_dock.py:321-329).
- P28 Offset and Binning write to the driver on every `valueChanged` (camera_dock.py:158, :170): typing "35" writes 3 then 35; holding an arrow floods the driver with blocking calls on the UI thread.
- P30 No capture parameter is persisted (exposure, gain, type, filter, preview reset at every launch).
- P39 The lock hint says "Sequence running — the sequence owns the camera." also during a stand-alone autofocus (lock applied for AUTOFOCUS, ip:638).
- P40 Unicode pictographs in labels ("▶", "■", "◉"): banned in the web UI (BRAND 4.3).
- P42 "Temp" here is the sensor temperature; the focuser panel also says "Temp" for the focuser probe (focuser_dock.py:71): ambiguous.

### 1.2 Mount control (`MountDock`, mount_dock.py:57, card in dock "Telescope", tab behind "Acquisition", non-modal)

- Purpose: live pointing readout, tracking, catalogue lookup, manual GoTo, centring from a plate solution, inline jog, sync, park, access to the floating jog dialog.
- `set_enabled(connected)` gates only actions; GoTo coordinates and the lookup stay usable offline (mount_dock.py:286-303).

| # | Control | Qt type | Label / tooltip (exact text) | Default / range / step / units | Enabled or visible when | Shortcut | Action: handler file:line -> effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Tracking | checkable `SuccessButton` (mount_dock.py:116) | "Tracking ON" / "Tracking OFF"; no tooltip | Checked = mount `Tracking`, re-synced by every poll (mount_dock.py:323-329) | Mount connected / busy | — | `toggled` -> `_on_tracking_toggle` mount_dock.py:437 -> `ds.set_tracking` ds:628 -> `Telescope.set_tracking` telescope.py:482 | Device |
| 2 | Rate | QComboBox (mount_dock.py:119) | "Rate"; no tooltip | "Sidereal", "Lunar", "Solar" (mount_dock.py:47); default Sidereal; never read back | Connected | — | `currentIndexChanged` -> `ds.set_tracking_rate(idx)` ds:637 -> `Telescope.set_tracking_rate` telescope.py:610 (ASCOM DriveRates) | No |
| 3 | Object (search) | QLineEdit (mount_dock.py:138) | "Object"; placeholder "M 42, NGC 7000, HD 189733…"; tooltip "Search an astronomical catalogue by designation" | Free text | Always (also offline); disabled while a lookup runs (mount_dock.py:339-345) | Return | `returnPressed` -> `_request_lookup` mount_dock.py:406 -> `_lookup_object` ip:2641 (one at a time) -> `ObjectResolverWorker` object_resolver_worker.py:18 -> `resolve_object` object_resolver.py:369 (local cache, then CDS Sesame, 8 s timeout) -> `set_catalogue_target` ip:2658 | Resolver cache file (object_resolver.py:165-180) |
| 4 | Find | `SecondaryButton` (mount_dock.py:145) | "Find"; no tooltip | — | same as #3 | — | same as #3 | — |
| 5 | Slew to selected object | `PrimaryButton` (mount_dock.py:156) | "Slew to selected object"; tooltip "Send the selected catalogue coordinates to the mount" | — | Hidden until a resolved object (mount_dock.py:357); enabled when connected | — | `_on_resolved_slew` mount_dock.py:409 -> `_goto_resolved_object` ip:2767 -> `_on_goto` ip:2612 -> `ds.goto` ds:573 (Tracking on, `slew_to`, remember target, emit `slewed` -> astrometry cleared ip:524) | No |
| 6 | Candidate list | QComboBox (mount_dock.py:174) | items "{name} · {type} — {sep:.1f}″ away" | Candidates within 90″ (`resolve_nearby_objects` object_resolver.py:289) | Visible after a Stellarium GoTo with ≥ 1 candidate (mount_dock.py:376-397) | — | Selection only | No |
| 7 | Use as target name | `SecondaryButton` (mount_dock.py:176) | "Use as target name"; tooltip "Use this canonical catalogue name for Capture, the plan and FITS OBJECT" | — | With candidates | — | `_accept_target_suggestion` mount_dock.py:417 -> `set_catalogue_target` ip:2658: fills GoTo fields, sets camera Object (emit), `target_coordinates_changed` -> Plan, variable star -> photometry target (ip:2675-2676) | No |
| 8 | Ignore | `SecondaryButton` (mount_dock.py:181) | "Ignore" | — | With candidates | — | Hides E2b (mount_dock.py:182) | No |
| 9 | Goto RA | QDoubleSpinBox (mount_dock.py:197) | "Goto RA"; suffix "  h" | 0.0–23.9999 h, 4 decimals, Qt default step 1.0 | Always editable | — | Read by Slew; written by lookup, suggestion, Stellarium GoTo (ip:2785) and Center (ip:2635) via `set_goto_fields` mount_dock.py:335 | No |
| 10 | Goto Dec | QDoubleSpinBox (mount_dock.py:201) | "Goto Dec"; suffix "  °" | −90–90°, 4 decimals | Always editable | — | same | No |
| 11 | Slew | `PrimaryButton` (mount_dock.py:210) | "▶  Slew"; no tooltip | — | Connected | — | `_on_slew` mount_dock.py:403 -> `_on_goto` ip:2612 -> `ds.goto` ds:573 -> `Telescope.slew_to` telescope.py:409 | No |
| 12 | Abort | `DangerButton` (mount_dock.py:212) | "■  Abort"; no tooltip | Danger styling only while slewing (mount_dock.py:330-333) | Connected | — | `abort_clicked` -> `ds.abort_slew` ds:647 -> `Telescope.abort_slew` telescope.py:490 | No |
| 13 | Center selected target | `SecondaryButton` (mount_dock.py:215) | "Center selected target"; tooltip "Correct the mount model from the current plate solution, then slew to the selected target" | — | Connected **and** a plate solution exists (mount_dock.py:302-308; set ip:1395, cleared ip:2443) | — | `_center_selected_target` ip:2616: WCS centre of the displayed green frame; target = first role "target" else last GoTo -> `ds.center_target_from_solution` ds:595 (Tracking on, `SyncToCoordinates(solved centre)`, `slew_to(target)`) | No |
| 14 | Jog speed | QComboBox (mount_dock.py:229) | "Jog speed" | "Slow" 0.5, "Normal" 2.0, "Fast" 5.0 deg/s (mount_dock.py:50-54); default Normal | Connected | — | Read at press (mount_dock.py:440-442) | No |
| 15 | Jog ↑ (North) | `_JogArrowButton` 54 x 54 (mount_dock.py:241, :445) | "↑"; no tooltip | axis 1, rate +speed | Connected | — | `pressed` -> `jog_start(1, +v)` -> `ds.jog` ds:665 (QThreadPool `_JogRunnable` ds:45 -> `Telescope.move_axis` telescope.py:564); `released` -> `jog_stop(1)` -> `_on_jog_stop` ip:2587 -> `ds.jog(1, 0.0)` | No |
| 16 | Jog ← (West) | same (mount_dock.py:242) | "←" | axis 0, −speed | Connected | — | same, axis 0 | No |
| 17 | Jog → (East) | same (mount_dock.py:243) | "→" | axis 0, +speed | Connected | — | same | No |
| 18 | Jog ↓ (South) | same (mount_dock.py:244) | "↓" | axis 1, −speed | Connected | — | same | No |
| 19 | Jog stop | `_JogArrowButton` (mount_dock.py:252) | "■"; tooltip "Stop" | — | Connected | — | `clicked` -> `jog_stop(0)` and `jog_stop(1)` (mount_dock.py:254) | No |
| 20 | Sync | `SecondaryButton` (mount_dock.py:270) | "⟳  Sync"; tooltip "Sync mount pointing model to current RA/Dec" | — | Connected | — | `sync_to_current_clicked` -> `ds.sync_current` ds:585 -> `Telescope.sync_to(last polled RA/Dec)` telescope.py:540 (requires Tracking, clock check) | No |
| 21 | Park | `SecondaryButton` (mount_dock.py:273) | "⊙  Park"; tooltip "Park the mount — physically closes the Seestar arm" | — | Connected | — | `_on_park_clicked` mount_dock.py:423 -> E3 -> Yes -> `ds.park` ds:656 -> `Telescope.park` telescope.py:505 (Unpark first if AtPark, then Park) | No |
| 22 | Jog dialog… | `SecondaryButton` (mount_dock.py:276) | "✥  Jog dialog…"; tooltip "Open the floating jog dialog (arrow-key navigation, stay-on-top)" | — | Connected | — | `manual_control_requested` -> `_open_jog` ip:2790 (creates E8 once with the current `Telescope`, then show/raise) | No |

**Displayed data**

| Readout | Source | Refresh |
|---|---|---|
| RA (mount_dock.py:98) | `_format_ra` mount_dock.py:462 ("HHh MMm SSs", seconds rounded) | `MountPollingWorker` every 2 s (polling_worker.py:29) -> `ds._on_position` ds:544 -> `_on_mount_position` ip:2591 |
| Dec (mount_dock.py:99) | `_format_dec` mount_dock.py:469 ("±DD° MM′ SS″", seconds **truncated**) | same |
| Alt, Az (mount_dock.py:100-101) | "{:.2f}°" | same |
| Tracking state | button text and style (mount_dock.py:323-329) | same |
| Lookup result E2a | "Searching catalogue…" (mount_dock.py:344) then "{name} · {type}\nRA {ra:.5f} h · Dec {dec:+.5f}°" (mount_dock.py:353-355) or the error text | On lookup |
| Suggestion E2b | "Catalogue candidate after a Stellarium GoTo — confirm before using it." (initial), "Checking a local catalogue match…" (busy), "{n} catalogue candidate{s} near the Stellarium GoTo. Choose one only if it is the intended target." (mount_dock.py:169-170, :370, :389-393) | On Stellarium GoTo |

**Implicit behaviours**

- Polling: 2 s; 3 consecutive connection/timeout errors -> `connection_lost` (polling_worker.py:50, :83-86) -> `ds._on_mount_lost` ds:557 (state "error", dock disabled) -> auto-reconnect every 10 s (ds:156-160, :300-333).
- Mount "busy" (slewing) keeps the dock enabled (ip:646-649).
- A pointing change not commanded by ARGOS (Seestar app, Stellarium) clears astrometry (ip:2600-2610).
- Stellarium GoTo: `goto_target` (fills fields, slews) then a nearby-name suggestion (shell.py:346-353; ip:2733-2765).
- Catalogue result of SIMBAD type `V*` also creates the photometry target (ip:2675-2676).
- Mount clock more than 60 s off: GoTo, Sync and Center are refused by `Telescope._assert_clock_synchronized` (telescope.py:287-294; checked at :429, :549, :646); the dock buttons stay enabled.
- GoTo always switches tracking on first (ds:577).

**Messages**

- CMD "Slewing → RA {ra:.4f}h Dec {dec:+.4f}°" / ERROR "Goto: {exc}" (ds:580-583).
- CMD "Catalogue slew {name} → RA {ra:.4f}h Dec {dec:+.4f}°" / WARN "Slew requested but mount not connected" (ip:2770-2772).
- CMD "{Stellarium goto\|Goto} → RA … Dec …" / WARN "Goto requested but mount not connected" (ip:2782-2787).
- CMD "Sync at RA {ra:.4f}h Dec {dec:+.4f}°" / ERROR "Sync: {exc}" (ds:590-593), e.g. "Tracking must be enabled before syncing — enable tracking first" (telescope.py:551-553), "Mount UTC is {h:.1f} hours off. Correct the Seestar date/time in its native app, then reconnect before using GoTo or Sync." (telescope.py:290-294).
- WARN "Center target: plate-solve the current frame first." / WARN "Center target: select a target or issue a GoTo first." / INFO "Centering {label} from the current plate solution…" (ip:2620, :2631, :2636); CMD "Center: synced solved field RA … Dec …", CMD "Center: slewing to target RA … Dec …", ERROR "Center target: {exc}", WARN "Center target: mount not connected" (ds:609-626).
- CMD "Tracking ON\|OFF" / ERROR "Tracking: {exc}"; CMD "Tracking rate → {name}" / ERROR "Tracking rate: {exc}" (ds:631-645).
- CMD "Slew aborted" / ERROR "Abort: {exc}"; CMD "Park — arm closing." / ERROR "Park: {exc}" (e.g. "Mount does not support Park", telescope.py:516) (ds:650-663).
- ERROR "Jog: {exc}" / WARN "Stop jog: {exc}" (ds:64-67).
- INFO "Catalogue target: {name} — RA {ra:.5f}h Dec {dec:+.5f}°" (ip:2666-2669); WARN "Catalogue lookup: {message}" (ip:2724) with "Enter an object designation first.", "Catalogue unavailable. Connect to the internet or use a previously searched target.", "Object lookup failed unexpectedly. See the log for details." (object_resolver.py:383, :416-418; object_resolver_worker.py:34).
- INFO "Photometry target saved — solve a full-resolution frame to draw its marker and select field comparison stars." (ip:2695-2699).
- INFO "Stellarium target-name suggestion: {n} nearby catalogue candidate(s)." / WARN "Target-name suggestion: {message}" / "Target-name lookup failed unexpectedly. See the log for details." (ip:2751-2759; object_resolver_worker.py:63).
- WARN "Poll: {msg}"; ERROR "Mount connection lost."; INFO "Retrying the mount every 10s — disconnect to stop."; OK "Mount reconnected: {name}"; ERROR "Mount clock is {h:.1f} h off — correct date/time in the Seestar app; GoTo and Sync are disabled." (ds:286-290, also on reconnect); WARN :541, ERROR :558, INFO :566, OK :314.
- INFO "Mount pointing changed outside Argos — stale astrometry overlays cleared. Plate-solve the current full-resolution frame." (ip:2605-2609).

**Problems found**

- P16 Duplicate slew: "Slew to selected object" (#5) and "▶ Slew" (#11) slew to the same coordinates after a lookup (the lookup fills the GoTo fields, mount_dock.py:350); only the log line differs (ip:2770 vs ds:582).
- P17 Sync syncs the mount to its own last polled position (ds:585-589): a no-op correction at best (a J2000 / topocentric round trip at worst). Unlike Center (ds:613) it does not switch tracking on first, so it fails when tracking is off.
- P18 Tracking rate is never read back (`Telescope.get_tracking_rate` telescope.py:628 is unused); a rejected rate leaves the combo on the rejected value (ds:637-645).
- P19 The tracking button reads "Tracking ON" while disconnected and unchecked, until the first poll (mount_dock.py:116).
- P23 Inline jog arrows have no tooltip or accessible direction names (mount_dock.py:240-250), and no keyboard support.
- P24 (uncertain) N/S/E/W map mount axes, not sky directions: axis 0 = azimuth, axis 1 = altitude on the alt-az Seestar (mount_dock.py:71-73); the mapping changes in EQ mode (`mount_mode` ds:110). Rates 0.5 / 2 / 5 deg/s are not checked against the driver's AxisRates.
- P25 Jog speed table duplicated in E8 (mount_dock.py:50-54 vs manual_control_dialog.py:38-42) with different fallbacks (1.0 at mount_dock.py:441, 2.0 at manual_control_dialog.py:110).
- P26 The clock-error log says "GoTo and Sync are disabled" (ds:286-290) but Slew, Sync and Center stay enabled; the refusal only appears after a click.
- P27 GoTo, Sync, Center, Tracking, Rate, Abort and Park call Alpaca synchronously on the UI thread (ds:573-663). (Qt only; the server must run them off its event loop.)
- P37 `_format_ra` rounds and can print "24h 00m 00s" for RA ≥ 23.99986 h; `_format_dec` truncates seconds (mount_dock.py:462-476). BRAND 5 already requires one rounding rule.
- P40 Pictographs "▶ ■ ⟳ ⊙ ✥ ↑ ↓ ← →" in labels.
- P15 (see 1.1) the "Object" search field collides with the camera "Object" identity.

### 1.3 Park confirmation (`QMessageBox.question`, mount_dock.py:426-435, modal, opened by Mount #21)

- Purpose: confirm a physical action (arm closes, tracking stops, any capture is ended).
- Title "Park mount"; text "Parking physically closes the Seestar arm and stops tracking.\n\nPark the mount now?".

| # | Control | Qt type | Label | Default | Enabled when | Shortcut | Action | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Yes | standard button | "Yes" (platform text) | — | Always | Return (platform) | emits `park_clicked` -> `ds.park` ds:656 | No |
| 2 | No | standard button | "No" | **Default** (mount_dock.py:432) | Always | Esc | Closes, nothing | No |

No problems beyond the native look (not themeable in Night Red).

### 1.4 Focuser control (`FocuserDock`, focuser_dock.py:38, card in dock "Focusing", tab behind "Acquisition", non-modal)

- Purpose: manual focus (relative steps, absolute move), autofocus start/stop, halt, V-curve read-back.

| # | Control | Qt type | Label / tooltip (exact text) | Default / range / step / units | Enabled or visible when | Shortcut | Action: handler file:line -> effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Step | QComboBox, not editable (focuser_dock.py:83) | "Step"; tooltip "Increment used for each manual focus movement" | 1, 10, 50, 100, 500, 1000 steps (focuser_dock.py:35); default 100 | Focuser connected | — | Read by Out / In (focuser_dock.py:202-206) | No |
| 2 | Out | `SecondaryButton` (focuser_dock.py:88) | "◀ Out"; tooltip "Move focuser outward (position decreases)" | −Step | Connected and no autofocus (focuser_dock.py:182) | — | `_on_step_out` focuser_dock.py:208 -> `_on_focuser_step` ip:2804 -> `ds.focuser_step` ds:705 -> `Focuser.step` focuser.py:140 (read Position, clamp 0..MaxStep, Move); the panel shows the commanded target | No |
| 3 | In | `SecondaryButton` (focuser_dock.py:91) | "In ▶"; tooltip "Move focuser inward (position increases)" | +Step | same | — | `_on_step_in` focuser_dock.py:211, same path | No |
| 4 | Go to | QSpinBox, no arrows (focuser_dock.py:99) | "Go to" | 0–200 000 steps (not MaxStep); overwritten by every `set_position` (focuser_dock.py:160) | Connected (also **during** autofocus) | Return does nothing | Read by Move | No |
| 5 | Move | `SecondaryButton` (focuser_dock.py:103) | "Move"; tooltip "Move to the specified absolute focuser position" | — | Connected (also during autofocus) | — | `_on_move_to` focuser_dock.py:214 -> `_on_focuser_move_to` ip:2809 -> `ds.focuser_move_to` ds:717 -> `Focuser.move_to` focuser.py:127 (clamped silently); the panel shows the **requested** value | No |
| 6 | Autofocus / Stop AF | `SuccessButton`, becomes danger (focuser_dock.py:118, :176-181) | "⚡  Autofocus" / "■  Stop AF"; no tooltip | — | Connected | — | `_on_autofocus` focuser_dock.py:217. Idle: `ae.start_autofocus` ae:679 (needs focuser + camera; acquire AUTOFOCUS, preempting Live; refused while a sequence runs) -> `AutofocusWorker` (exposure `min(camera exposure, 10 s)`, gain = camera gain but unused, half range 2000, 9 coarse steps; ae:692-716). Running: `halt_requested` -> `_on_focuser_halt` ip:2813 | No |
| 7 | Halt | `DangerButton` (focuser_dock.py:116) | "■  Halt"; no tooltip | — | Connected; **disabled during autofocus** (focuser_dock.py:184) | — | `halt_requested` -> `_on_focuser_halt` ip:2813 -> `ae.stop_autofocus` ae:718 (stop + wait ≤ 10 s + release) then `ds.focuser_halt` ds:728 -> `Focuser.halt` focuser.py:151 | No |

**Displayed data**

| Readout | Source | Refresh |
|---|---|---|
| Position (focuser_dock.py:66) "{:,}" | `set_position` focuser_dock.py:158 from: `focuser_state` at connect only (ds:466-476 -> ip:681), commanded target after Step/Move (ip:2804-2811), each AF step (ip:2834), AF result (ip:2843) | **Not polled**: shows commanded values, never the real position |
| Moving colour | `set_moving` focuser_dock.py:168 | **Never called** (dead) |
| Temp (focuser_dock.py:67) "{:.1f}°C" | `TemperaturePollingWorker(Focuser.get_temperature)` ds:479-482 -> ip:523 | 10 s; "—" on disconnect (ip:656-657) |
| AF status (focuser_dock.py:123) | "Autofocus in progress…" then "Step {step}/{total}  HFD={hfd:.1f\|—}" (focuser_dock.py:186; ip:2836) | Per AF step |
| V-curve | 1.5 | Per AF step |

**Implicit behaviours: the autofocus run** (autofocus_worker.py)

1. Start position read; range `[max(0, start − 2000), min(MaxStep, start + 2000)]`; 9 coarse positions (`np.linspace`, unique) (autofocus_worker.py:103-107). Total announced = coarse + 4 fine + 1 verification (:111).
2. Each sample: Move, poll `IsMoving` every 300 ms up to 30 s, settle 1 s (:43-44, :192-203); `StartExposure(exposure)` (light, **no gain set**), poll ImageReady every 300 ms up to exposure + 15 s, download, `compute_hfd` (:205-232). Failure = NaN sample, step still announced with HFD None.
3. Fewer than 3 valid samples or stopped -> move back to start, `best_found(start, None)` (:118-122).
4. Degenerate sweep (`sweep_is_degenerate` focus.py:82: "fewer than 3 valid samples", "non-positive HFD", "flat HFD curve (a–b, span < 15%)", "HFD minimum at the sweep edge — best focus outside the scanned range") -> restore start, error "Autofocus: {reason} — focus unchanged" (:127-133).
5. Fine: 4 positions within one coarse interval of the raw minimum (`refine_positions` focus.py:103); fit `fit_v_curve` on fine samples + raw minimum, bounded to ±1 interval (:146-149).
6. Verify: move to best, one more exposure, report the **measured** HFD (warning in the log only if > 2 x fitted, :163-166).
- Signals: `step_done` -> ip:2833 (position, status, V-curve sample, log); `best_found` -> ip:2842 (position, V-curve summary, log OK, status-bar action "Focused  pos={best}"); `error_occurred` -> ERROR "AF: {msg}" (ae:729-730); `finished` -> release camera, re-sample photometry FWHM (ae:732-744).
- Mid-sequence autofocus uses the same worker through the SEQUENCE -> AUTOFOCUS handshake (ae:559-582; camera_service.py:172-184).
- Focuser disconnect stops a running sweep first (`focuser_will_disconnect`, ds:492).

**Messages**

- CMD "Focuser step {delta:+d} → pos {target}" / ERROR "Focuser step: {exc}"; CMD "Focuser move → {position}" / ERROR "Focuser move: {exc}"; CMD "Focuser halted" / WARN "Focuser halt: {exc}" (ds:711-739).
- WARN "Autofocus needs focuser + camera connected" (ae:681); CMD "Autofocus started…" (ae:715); refusals and preemption texts of 1.1.
- INFO "AF {step}/{total}  pos={pos}  HFD={hfd}" (ip:2839); OK "Autofocus complete — best pos={best}  HFD={hfd}" (ip:2847); ERROR "AF: Autofocus: {reason} — focus unchanged".
- Focuser connect: OK "Focuser connected: {name}  pos={pos}" / ERROR "Focuser: {exc}" (ds:484, :487).

**Problems found**

- P4 Focuser position is never polled (only at connect, ds:466-476); the panel shows commanded targets; `set_moving` (focuser_dock.py:168) is dead, so a move in progress is invisible.
- P5 Every `set_position` overwrites "Go to" (focuser_dock.py:160), including AF steps: a typed target is lost.
- P6 "Go to" accepts 0–200 000 (focuser_dock.py:100) regardless of MaxStep (default 100 000, focuser.py:43); `move_to` clamps silently (focuser.py:133) while the panel shows the unclamped request (ip:2810-2811).
- P7 During autofocus "Go to" + Move stay enabled (only Out/In/Halt are disabled, focuser_dock.py:182-184): a manual move can be sent mid-sweep. Halt, described as "the emergency interruption" (focuser_dock.py:113-115), is disabled exactly while automation moves the focuser.
- P8 Autofocus ignores the gain (stored at autofocus_worker.py:81, never applied), the frame type and the filter; exposure comes from the camera form (capped 10 s, ae:704), a hidden coupling with another tab; sweep parameters (2000 / 9 / 4 / 1 s settle) are hard-coded (autofocus_worker.py:43-45, :73-74; ae:701-708).
- P43 Stop AF / Halt race (derived from code, not reproduced): the worker reacts to stop by commanding a move back to the start position and returning at once (autofocus_worker.py:118-121, :187-203: the wait loop exits on the stop flag); `_on_focuser_halt` then sends Halt (ip:2815-2817), which can stop that return move midway. The panel shows the start position (`best_found(start, None)` -> ip:2843) and logs "Autofocus complete" (ip:2847) after a cancel or a rejected sweep, contradicting the ERROR line.
- P32 `_step_value` ValueError fallback is dead (the combo is not editable, focuser_dock.py:202-206).
- P33 `ImagingPage.request_autofocus` and `nudge_focuser` (ip:2819-2825) are never called (the "Focus screen" they mention does not exist).
- P42 "Temp" label ambiguous (focuser probe vs sensor).
- Qt-specific: the V-curve sits in the "Focusing" tab, which is behind "Acquisition" by default, so starting autofocus from elsewhere (mid-sequence) shows nothing unless the observer switches tabs.

### 1.5 V-curve (`VCurveWidget`, vcurve.py:20, inside 1.4, visible from the first autofocus)

- Purpose: show the sweep samples, the fitted parabola and best focus.
- Content: white sample dots (vcurve.py:43-46), accent fit curve (:42), dashed success vertex line only for a reliable parabola (:47-51, :121-128), summary "Best focus  {hfd:.2f} px at {pos:,}" in success colour (:76-81). Axes "Position" (steps) and "HFD" (px) (:37-38). Height 140–180 px (:33-34). `start_sweep` clears it at AF start (:88-96).

| # | Control | Qt type | Label | Default | Enabled when | Shortcut | Action | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Pan / zoom | pyqtgraph ViewBox mouse (default) | — | Wheel zoom, left-drag pan, right-drag zoom | Always | — | Changes the view; disables auto-range | No |
| 2 | Context menu (E5a) | pyqtgraph default | "View All", "X axis", "Y axis", "Mouse Mode", "Plot Options", "Export…" (library defaults, not inspected at runtime) | — | Right-click | — | View / export dialogs | No |
| 3 | Auto-range button | pyqtgraph "A" corner button | — | Appears when auto-range is off | Hover | — | Restores auto-range | No |

**Problems found**

- P9 The widget re-fits **all** samples (coarse far-defocus samples and the verification frame included, no bounds, vcurve.py:117), while the worker fits only the fine window (autofocus_worker.py:148-149). The drawn parabola / vertex can disagree with the position the focuser was sent to.
- P35 After a pan or zoom new samples can fall outside the view (auto-range off); `MetricsPanel` disables the menu but these two plots do not.

### 1.6 HFD history (`HfdHistoryDock`, hfd_history_dock.py:25, dock "Focus diagnostics (HFD/FWHM)", hidden by default, opened from "Panels ▾")

- Purpose: focus drift and cloud diagnosis: HFD and detected star count over the last 100 frames (hfd_history_dock.py:22).
- Content: HFD (accent, left axis "HFD (px)") and #Stars (muted, **second right axis** "#Stars") vs frame index (:46-76); readouts HFD "{:.1f} px", Stars, Sky "{:.0f}" (:79-88). Fed by `push_metrics` ip:746 for every processed frame.

| # | Control | Qt type | Label / tooltip | Default | Enabled when | Shortcut | Action | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Clear | `SecondaryButton` (hfd_history_dock.py:90) | "Clear"; tooltip "Reset the HFD / #Stars trend" | — | Always | — | `clear_metrics` :127: empty both series and readouts, emit `cleared` (connected nowhere) | No |
| 2 | Pan / zoom | pyqtgraph default | — | — | Always | — | as 1.5 #1 | No |
| 3 | Context menu (E6a) | pyqtgraph default | as 1.5 #2 | — | Right-click | — | as 1.5 #2 | No |
| 4 | Auto-range button | pyqtgraph default | — | — | Hover | — | as 1.5 #3 | No |

**Problems found**

- P10 Frames without an HFD are skipped in the HFD series but not in the star series (hfd_history_dock.py:114-120): indices drift apart and the two curves are misaligned.
- P11 Dual y-axes (hfd_history_dock.py:62-74): forbidden in the web UI (BRAND 10, "one y-axis per plot").
- P12 Title "Focus diagnostics (HFD/FWHM)" (ip:290, :338) but no FWHM is shown; the card title "HFD History" (hfd_history_dock.py:31) is erased by `make_dock` (dock_host.py:82-83).
- The trend is never cleared on an object change or a slew (the docstring says "e.g. when switching targets", :128) and `cleared` is unused.
- P13 / P14 apply (decimated HFD, triple display).

### 1.7 Session metrics (`MetricsPanel`, metrics_panel.py:26, tab "Metrics" in the Field photometry window)

- Purpose: conditions over the session: airmass, FWHM, sky, HFD, star count, sensor temperature vs elapsed time (one series shown at a time).

| # | Control | Qt type | Label | Default / options | Enabled when | Shortcut | Action | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Metric | QComboBox (metrics_panel.py:38) | "Metric:" | "Airmass", "FWHM (green px)", "Sky (ADU)", "HFD (green px)", "Star count", "Sensor temp (°C)" (metrics_panel.py:16-23); default Airmass | Always | — | `_refresh` :72 swaps the plotted series and the y label | No |
| 2 | Pan / zoom | pyqtgraph default (menu disabled, :47) | — | — | Always | — | View only | No |
| 3 | Auto-range button | pyqtgraph default | — | — | Hover | — | Restores auto-range | No |

- Data: `add_sample(t, **values)` (metrics_panel.py:62) from `_feed_metrics` ip:2419 (sky, mean FWHM, HFD, star count, airmass from the mount altitude) for every processed frame **only while the photometry window is visible**, and the sensor temperature at each photometry measurement start (ip:2370-2374, blocking read `ds.ccd_temperature` ds:759). X = seconds since the first sample of the app lifetime (ip:2414-2417).
- Problems: P34 gaps whenever the window is hidden; `clear()` (metrics_panel.py:78) never called and t0 never reset; a blocking network temperature read on the UI thread although the 10 s poller already publishes it (ds:507-511); units "green px" here vs "px" elsewhere (P13).

### 1.8 Manual Control dialog (`ManualControlDialog`, manual_control_dialog.py:66, floating Tool window, non-modal, stay-on-top, opened by Mount #22)

- Purpose: hold-to-move jogging with mouse or arrow keys, kept on top of the main window.
- Static texts: title "Manual Control"; "Speed" (:103); "Hold to move · Release to stop" (:115); "Arrow keys work when this window is focused" (:145).

| # | Control | Qt type | Label / tooltip | Default / range | Enabled when | Shortcut | Action: handler -> effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Speed | QComboBox (:105) | "Speed" | Slow 0.5, Normal 2.0, Fast 5.0 deg/s; default Normal (:108) | Always | — | sets `_speed` (:109-111) | No |
| 2 | ↑ | `_JogButton` 64 x 64 (:131) | tooltip "North" | axis 1, +speed | Always (never disabled) | — | `pressed` -> `_start("North")` :157 -> `Telescope.move_axis` **synchronously on the UI thread** (:163); `released` -> `_stop` :169 | No |
| 3 | ↓ | same | "South" | axis 1, −speed | Always | — | same | No |
| 4 | ← | same | "West" | axis 0, −speed | Always | — | same | No |
| 5 | → | same | "East" | axis 0, +speed | Always | — | same | No |
| 6 | ■ | `_JogButton` (:137) | tooltip "Stop" | — | Always | — | `_stop` :169: stops only the last started axis | No |
| 7 | Arrow Up | `keyPressEvent` :184 | — | — | Window focused | ArrowUp | `_start("North")`; key release -> `_stop` (:199-205); auto-repeat ignored | No |
| 8 | Arrow Down | same | — | — | same | ArrowDown | South | No |
| 9 | Arrow Left | same | — | — | same | ArrowLeft | West | No |
| 10 | Arrow Right | same | — | — | same | ArrowRight | East | No |
| 11 | Window close | title-bar button (:93) | — | — | Always | — | `closeEvent` :209 -> `_stop` | No |

- Messages: ERROR "Move failed: {exc}", WARN "Stop failed: {exc}" (:167, :178) forwarded to the activity log (ip:2796).
- Problems: P20 the dialog keeps the `Telescope` it was created with (ip:2794-2795) after a reconnect (a new `Telescope` is created, ds:307-312) and is never disabled when the mount disconnects; P21 synchronous `MoveAxis` on the UI thread, the exact failure `ds._JogRunnable` was written to avoid (ds:45-52: the ~600 ms first call swallows the release event); P22 one `_active_axis`: holding Up then Right and releasing Up stops the wrong axis and the altitude axis keeps moving; ■ cannot stop a "lost" axis (the inline pad's ■ stops both, mount_dock.py:254); (uncertain) when the Speed combo has focus, Up/Down change the speed instead of jogging (Qt combo key handling, not reproduced); P25 duplicated speed table.

### 1.9 Dock chrome for these panels (ip:280-294, :348-414; dock_host.py:48-75; shared with the Observe layout spec)

| # | Control | Qt type | Label / tooltip | Default | Enabled when | Shortcut | Action | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Chip "Acquisition" | checkable QAction on the panel strip (ip:354-364) | tooltip "Show/hide Acquisition. Drag its title bar to arrange it; double-click the title to detach it." | Checked | Always | — | `toggleViewAction` of dock E1 | `ui.imaging.layout` |
| 2 | Chip "Telescope" | same | same pattern | Checked (tab) | Always | — | dock E2 | same |
| 3 | Chip "Focusing" | same | same pattern | Checked (tab) | Always | — | dock E4 | same |
| 4 | "Focus diagnostics (HFD/FWHM)" | entry in "Panels ▾" menu (ip:366-375) | same pattern | Unchecked (hidden, ip:451) | Always | — | dock E6 | same |
| 5–8 | "Float {label}" / "Dock {label}" for the four docks | "Arrange ▾" menu entries rebuilt on open (ip:393-414) | — | — | Always | — | `_toggle_dock_floating` ip:406-411 | same |
| 9–12 | Dock title-bar Float button (x4) | QDockWidget feature (dock_host.py:68-74) | — | — | Always | Double-click on the title floats | Detach / re-dock | same |
| 13–16 | Dock title-bar Close button (x4) | QDockWidget feature | — | — | Always | — | Hide the dock | same |

Mouse: dragging a title bar moves / tabs a dock; the right dock area holds E1, E2, E4 as three tabs of one stack (only one visible at a time).

## 2. Web redesign

### 2.1 Placement in the new information architecture

**What the web UI already has vs what is missing** (web/src/lib/imaging/CameraCard.svelte, MountCard.svelte, ImagingToolbar.svelte, ImagingScreen.svelte)

| Area | Built | Missing (this spec adds it) |
|---|---|---|
| Camera | Exposure field (0.001–3600 s static, step 0.5, CameraCard.svelte:56-65), Gain field (0–1000 static, step 10, :66-74), exposure progress (:77-88), facts Last frame / In use / Sensor (:90-107); toolbar Capture `E`, Live `V`, Stop (ImagingToolbar.svelte:59-90) | Frame type; Filter (filter wheel); observation Object; driver limits for exposure / gain; Offset; Binning; Preview quality; HFD; sensor temperature; camera owner (sequence / autofocus lock); Take shot **saving a FITS**; live parameter update without restart ("Applies when live view restarts", CameraCard.svelte:64) |
| Mount | RA / Dec / Alt / Az (MountCard.svelte:91-108), target line with distance (:110-121), Tracking toggle (:124-134), Park with inline confirm (:136-161), Unpark (:142-149, new vs Qt), GoTo with sexagesimal parsing (:164-182), Slew (:184), Abort `Esc` (:195-206), Use current (:208, new vs Qt) | Tracking rate; catalogue search + result; Stellarium name suggestion; Center on target from the plate solution; Sync (decision needed); inline jog pad + speed; keyboard jog (replaces the Qt dialog); clock-error gating |
| Focuser | — | The whole card: position, temperature, moving state, step size, Out / In, Go to + Move, Autofocus / Stop AF, Halt, progress |
| Focus quality | — | V-curve; HFD / stars trend; session metrics (conditions timeline) |
| Filter wheel | — | Slot names, current slot, moving / error state, selection |

**Placement**

| Qt element | Web section -> screen -> region | Why |
|---|---|---|
| E1 Camera form | Observe -> right rail -> **Camera** card (extend the existing card) | Settings used while observing stay in the first card (BRAND 11.1) |
| E1 #2 Object (identity) | Observe -> rail -> **Mount** card, top of the new "Target" block (merged with E2 #3); read-only echo as a frame chip in the HUD | One field for one concept (P15); the identity travels with the target, not the camera |
| E1 #3 Filter | Observe -> rail -> Camera card, Filter row (segmented) | The wheel is capture state (as Qt, ip:470-472) |
| E1a Offset / Binning / Preview | Camera card, "Sensor" disclosure (folded) | Rare, driver-dependent settings |
| E1 #11, #12 Live / Take shot | Observe -> toolbar (already built) | Frequent, icon-only |
| E1 HFD, Temp | Camera card facts row | Glance values next to the exposure |
| E1b Lock hint | Camera card status badge + disabled reasons | No dead band |
| E2 Mount | Observe -> rail -> Mount card (extend the existing card) | — |
| E2 #3–#8 lookup, suggestion | Mount card "Target" block; suggestion as an inline notice | Target entry is rare: below the readouts (BRAND 11.1) |
| E2c jog pad + E8 dialog | Mount card, "Jog" disclosure (folded), with a keyboard-arming toggle | One pad instead of two (P20-P22, P25) |
| E3 Park confirm | Mount card inline confirm (already built) | No native dialog (Night Red) |
| E4 Focuser | Observe -> rail -> **Focuser** card (new), after Mount; auto-unfolds and scrolls into view when autofocus starts | Used at set-up and for refocus; visible when it matters |
| E5 V-curve | Inside the Focuser card (396 x 140 px plot) | Read where focus is driven, as Qt |
| E6 HFD history + E7 session metrics | Observe -> bottom drawer, new tabs **Focus** and **Conditions** next to **Log**; the same timeline in Review -> session -> Conditions | Wide plots get the drawer width; one data source fixes P10/P34 |
| E9 dock chrome | Replaced by card fold (persisted), rail toggle `P`, drawer tabs | The web rail is fixed and collapsible (BRAND 11.1); no floating docks in a browser |

### 2.2 Control mapping

| Qt ref | Web control | Decision (reason) | Icon id | Display | Shortcut |
|---|---|---|---|---|---|
| 1.1 #1 Type | Camera card "Frame" segmented: Light / Dark / Flat / Bias | Keep. Dark and Bias move the wheel to the opaque slot server-side before exposing (fixes P1) | — | label | — |
| 1.1 #2 Object | Mount card Target block "Object" field (identity) | Merge with 1.2 #3 (P15). Typing never overwrites silently: a catalogue result offers "Use as target name" when the canonical name differs | `search` on the field | icon (search button) | Enter = search |
| 1.1 #3 Filter | Camera card "Filter" segmented with the wheel's slot names; spinner on the moving slot | Keep. Re-synced from server state after any move, including sequence moves (fixes P2, P3) | `filter-wheel` (row key) | label | — |
| 1.1 #4 Exposure slider | — | Drop: merged into the numeric field (space; the field takes wheel / arrow steps); log presets not needed | — | — | — |
| 1.1 #5 Exposure value | Existing Exposure field | Keep; range from driver limits (A1) | — | label | — |
| 1.1 #6 Gain slider | — | Drop: merged into the numeric field (same reason as #4) | — | — | — |
| 1.1 #7 Gain value | Existing Gain field | Keep; range from driver limits | — | label | — |
| 1.1 #8 Offset | Sensor disclosure "Offset" numeric field | Move; shown only when supported; commits on Enter / blur (fixes P28); refused with reason while a sequence or autofocus owns the camera | — | label | — |
| 1.1 #9 Binning | Sensor disclosure "Binning" segmented 1× … MaxBin× | Move; shown only when MaxBin > 1; same refusal | — | label | — |
| 1.1 #10 Preview | Sensor disclosure "Preview" segmented Full / Half, hint "display only, FITS stay full resolution" | Move (open question Q12 on its future) | — | label | — |
| 1.1 #11 Live | Toolbar `live` (built) | Keep | `live` | icon | V |
| 1.1 #12 Take shot | Toolbar `capture` (built); server saves the FITS; during Live it saves the next frame instead of answering 409 | Keep, extend API (A3) | `capture` | icon | E |
| 1.1 HFD / Temp / lock | Camera facts "HFD", "Stars", "Sensor °C"; badge "Sequence" / "Autofocus" when owned | Keep; HFD not colour-coded by fixed thresholds (Q9) | — | label | — |
| 1.2 #1 Tracking | Existing Tracking toggle | Keep | `tracking` | icon+label (built) | none (moves hardware) |
| 1.2 #2 Rate | Segmented Sidereal / Lunar / Solar next to Tracking, values from `tracking_rates`, read back | Keep (fixes P18); hidden when the mount supports only Sidereal | — | label | — |
| 1.2 #3 Object search | Target block field (merged with 1.1 #2) | Merge (P15) | `search` | icon | Enter |
| 1.2 #4 Find | Search icon button inside the field | Keep | `search` | icon | Enter |
| 1.2 #5 Slew to selected object | — | Drop: the resolved object fills Target RA / Dec and the single Slew sends it with its name (P16) | — | — | — |
| 1.2 #6 Candidate list | Inline notice in the Target block, custom menu (no native select) | Keep | — | label | — |
| 1.2 #7 Use as target name | Notice button | Keep | `labels` | icon+label (writes FITS OBJECT, rare) | — |
| 1.2 #8 Ignore | Notice close button | Keep | `close` | icon | Esc when focused |
| 1.2 #9, #10 Goto RA / Dec | Existing Target RA / Dec text fields (sexagesimal or decimal) | Keep | — | label | Enter = Slew |
| 1.2 #11 Slew | Existing Slew | Keep | `goto` | icon+label | — |
| 1.2 #12 Abort | Existing Abort | Keep; Escape also stops jog and focuser motion (Q4) | `abort` | icon+label | Esc |
| 1.2 #13 Center selected target | "Solved field" row of the Target block (shown only while a plate solution exists; otherwise one muted line "Plate-solve the current frame to center or sync") | Keep, promoted to icon+label (syncs and slews: moves hardware) | `center-target` | icon+label | — |
| 1.2 #14 Jog speed | Jog disclosure, segmented Slow / Normal / Fast | Keep; one speed setting (P25); persisted per viewer | — | label | — |
| 1.2 #15–#18 Jog arrows | Jog pad, press-and-hold, accessible names North / South / East / West (or axis names, Q2) | Keep; pointer leave, blur and socket loss stop the axis | `jog-north`, `jog-south`, `jog-west`, `jog-east` | icon | Arrow keys while armed |
| 1.2 #19 Jog stop | Pad centre, stops both axes | Keep | `stop` | icon (inventory note allows it in the pad centre) | Esc |
| 1.2 #20 Sync | "Solved field" row, button "Sync" = sync the mount to the plate solution without slewing, with inline confirm | Move and redefine pending Q1 (P17: syncing to its own position is a no-op); dropped if the owner prefers Center only | `sync` | icon+label (changes the pointing model, rare) | — |
| 1.2 #21 Park | Existing Park + inline confirm | Keep | `park` | icon+label | — |
| 1.2 #22 Jog dialog… | Jog disclosure toggle "Arrow keys" that arms keyboard jogging | Merge: the dialog existed only for keyboard jogging and stay-on-top; its bugs disappear (P20-P22). Inventory concept of `jog-pad` to update | `jog-pad` | icon (toggle, `aria-pressed`) | J (proposed, does not move hardware) |
| 1.3 #1 Yes | Inline "Park" text button (built) | Keep | — | text | Enter |
| 1.3 #2 No | Inline "Cancel" (built) | Keep | — | text | Esc |
| 1.4 #1 Step | Segmented 1 / 10 / 50 / 100 / 500 / 1000, persisted per viewer | Keep | — | label | — |
| 1.4 #2 Out | Icon button, tooltip "Focus out: position decreases by {step}" | Keep | `focus-out` | icon | none by default (Q3; inventory proposed `[`) |
| 1.4 #3 In | Icon button, tooltip "Focus in: position increases by {step}" | Keep | `focus-in` | icon | none by default (Q3; proposed `]`) |
| 1.4 #4 Go to | Numeric field, range 0 – MaxStep from the server, never overwritten while focused or edited (fixes P5, P6) | Keep | — | label | Enter = Move |
| 1.4 #5 Move | Icon button next to the field | Keep; disabled during autofocus (fixes P7) | `focus-move` | icon | Enter |
| 1.4 #6 Autofocus / Stop AF | Card button; swaps to `stop` + "Stop AF" while running | Keep, promoted to icon+label (minutes-long hardware routine) | `autofocus` / `stop` | icon+label | none (starts hardware) |
| 1.4 #7 Halt | Danger button "Halt", enabled whenever the focuser is connected, **including during autofocus** | Keep (fixes P7). Halt = stop where it is; Stop AF = cancel and return to the start position (Q8, fixes P43) | `stop` | icon+label | Esc (Q4) |
| 1.4 position / temp | Facts "Position", "Target", "Focuser °C", "Range"; badge "Moving" from polled state (fixes P4) | Keep | — | label | — |
| 1.5 #1 Pan / zoom | — | Drop: fixed auto-ranged plot; hover tooltip gives (position, HFD) per BRAND 10 | — | — | — |
| 1.5 #2 Context menu / Export | — | Drop from the plot; the AF samples and fit are kept in the session log and exportable from Review (Q7 / Q10) | — | — | — |
| 1.5 #3 Auto-range button | — | Drop: always auto-ranged (P35) | — | — | — |
| 1.6 #1 Clear | Drawer Focus tab header button "Clear focus trend" (client view reset; the session record is kept) | Keep | `clear` | icon | — |
| 1.6 #2–#4 Pan / zoom, menu, auto-range | — | Drop (as 1.5); hover tooltip; two stacked plots replace the dual axis (P11) | — | — | — |
| 1.7 #1 Metric | Drawer Conditions tab: chip group HFD / Stars / Sky / FWHM / Airmass / Sensor °C, up to 3 shown as small multiples | Merge with 1.6 (one conditions timeline, P10, P34) | `session-metrics` (tab) | label chips | — |
| 1.7 #2, #3 Pan / zoom, auto-range | — | Drop (as 1.5) | — | — | — |
| 1.8 #1 Speed | Mount jog speed (1.2 #14) | Merge (P25) | — | — | — |
| 1.8 #2–#5 Arrows | Mount jog pad | Merge | `jog-*` | icon | — |
| 1.8 #6 Stop | Pad centre stop (stops both axes) | Merge (fixes P22) | `stop` | icon | Esc |
| 1.8 #7–#10 Arrow keys | Arrow keys while "Arrow keys" is armed and focus is not in a text field; key-up stops that axis, per-axis tracking | Keep (BRAND 7 jog exception) | — | — | Arrow keys |
| 1.8 #11 Close | Disarming the toggle or folding the Jog section stops every axis | Merge | — | — | J / Esc |
| 1.9 #1–#4 Panel chips / Panels entry | Card fold (persisted per viewer), rail toggle `P`, drawer tabs | Replace (fixed rail, BRAND 11.1) | `panels` not needed | — | P |
| 1.9 #5–#16 Float / dock / close | — | Drop in the browser (no floating docks); a Tauri pop-out of the jog pad or the drawer is Q11 | — | — | — |

### 2.3 Wireframes

Notation (wireframes only, never UI text): `(id)` icon-only button with that icon id; `[id] Label` icon + label; `<A|B|C>` segmented control; `>` folded disclosure, `v` open disclosure; `o Label` status badge (dot + word). Reference screen 1440 x 900: nav rail 92 px, right rail 420 px (cards 396 px inside), status bar 32 px, toolbar about 42 px, so the viewer is about 928 x 826 px, or 928 x 610 px with the 216 px drawer open.

**A. Observe while focusing (drawer on "Focus", Focuser unfolded by autofocus)**

```
+--------+---------------------------------------------------------------+------------------------------------------+
| ARGOS  | [disconnect] Disconnect | (capture)(live)[stop] Stop | (zoom-out) 62% (zoom-in)(zoom-fit)(zoom-1to1) | (stretch-auto)(stretch-reset) ... |
|        +---------------------------------------------------------------+------------------------------------------+
| (nav)  | LIVE  #128  2.0 s  M 42  Seestar                              | > (connect) Connection        o Connected|
| Conn.  |                                                               | v (camera) Camera             o Autofocus|
| Observe|                                                               |   EXPOSURE [   2.000 ] s  GAIN [   80 ]  |
| Plan   |                  image 928 x 610                              |   FRAME  <Light|Dark|Flat|Bias>          |
| Review |                                                               |   FILTER <IR|LP|Dark>                    |
|Settings|                                                               |   > Sensor   offset 20 . bin 1x . Full   |
|        |                                                               |   HFD 2.1 px  STARS 117  SENSOR 21.4 °C  |
|        +--(log) Log | (focus-metrics) Focus | (session-metrics) Conditions ----- (clear) +   > (histogram) Display stretch      |
|        | HFD px 4 |    .  .      .                     | HFD   3.4 px |   > (mount) Mount            o Tracking  |
|        |        3 | . .  .  . . .  . .  .              | STARS 117    |   v (focuser) Focuser        o Autofocus |
|        | STARS130 |---\__/------\_/----                | SKY   2000   |     POSITION 1,250  TEMP 12.3 °C         |
|        |      110 +--21:04-------21:20------21:36 UTC-- | FWHM  2.9 px |     [stop] Stop AF   step 7/14 . fine     |
|        |                                                              |     [V-curve 396 x 140]                  |
+--------+---------------------------------------------------------------+------------------------------------------+
| o Connected . x 512 y 960 2 034 ADU . #128 . 0.5 fps . 42 ms . 62% . Observatory . Log                           |
+------------------------------------------------------------------------------------------------------------------+
```

Visible without scrolling: toolbar, Camera (all observing fields), headers of Display stretch, Mount and Focuser with their status. When the Focuser card unfolds for autofocus, the rail scrolls it into view and Display stretch stays folded until the observer opens it.

**B. Camera card (396 px)**

```
+ (camera) Camera ----------------------------------------- o Live +
| EXPOSURE                    GAIN                                 |
| [      2.000 ] s            [      80 ]                          |
| 0.032 - 2000 s (driver)     0 - 600 (driver)                     |
| FRAME   <Light|Dark|Flat|Bias>                                   |
| FILTER  <IR|LP|Dark>                                 (spinner)   |
| > Sensor                       offset 20 . bin 1x . preview Full |
| ======================================------------  1.2 / 2.0 s  |
| HFD        STARS      SENSOR       LAST      IN USE       SENSOR  |
| 2.1 px     117        21.4 °C      #128      2.0 s . 80   1080x1920 GRBG |
+------------------------------------------------------------------+

  Sensor disclosure open:
| v Sensor                                                         |
|   OFFSET [    20 ]  0 - 100        BINNING <1x|2x>               |
|   PREVIEW <Full|Half>   display only; saved FITS stay full size  |

  Owned by a run (fields disabled, one line, no extra band):
+ (camera) Camera ------------------------------------- o Sequence +
|   ...fields greyed, tooltip "The sequence owns the camera"...    |
```

The facts row is two rows of three when the card is narrower than 396 px.

**C. Mount card with Target block, suggestion and jog**

```
+ (mount) Mount --------------------------------------- o Tracking +
| RA                          DEC                                  |
| 05h 35m 17.3s               -05° 23' 28"                         |
| ALT                         AZ                                   |
| 41.27°                      182.30°                              |
| TARGET  M 42  05h 35m 17.3s  -05° 23' 28"          0.12° away    |
| [tracking] Tracking  <Sidereal|Lunar|Solar>           [park] Park|
| -- Target ------------------------------------------------------ |
| OBJECT [ M 42                                        ](search)   |
|         M 42 . HII region . RA 5.58817 h . Dec -5.39111°         |
| TARGET RA [ 05h 35m 17.3s ]     TARGET DEC [ -05° 23' 28" ]      |
| [goto] Slew  [abort] Abort                          Use current  |
| SOLVED FIELD  [center-target] Center   [sync] Sync               |
| > Jog                                                            |
+------------------------------------------------------------------+

  Stellarium suggestion (inline notice under OBJECT, dismissible):
| +(labels) 2 catalogue candidates near the Stellarium GoTo -(close)+|
| | Choose one only if it is the intended target.                  ||
| | [ M 42 . HII region - 12.3" away              v ]              ||
| | [labels] Use as target name                                    ||
| +----------------------------------------------------------------+|

  Jog open:
| v Jog          SPEED <Slow|Normal|Fast>        (jog-pad) Arrow keys |
|                       (jog-north)                                |
|            (jog-west)   (stop)   (jog-east)                      |
|                       (jog-south)                                |
| Hold to move, release to stop.                                   |

  Without a plate solution the SOLVED FIELD row reads: "Plate-solve the current frame to center or sync".
```

Prime and double-prime marks render as U+2032 / U+2033 in the UI (BRAND 5); ASCII here only.

**D. Focuser card**

```
+ (focuser) Focuser ------------------------------------- o Idle  +
| POSITION      TARGET       FOCUSER °C     RANGE                 |
| 1,305         1,305        12.3 °C        0 - 100,000           |
| STEP <1|10|50|100|500|1000>                 (focus-out)(focus-in)|
| GO TO [        1305 ](focus-move)                               |
| [autofocus] Autofocus                             [stop] Halt   |
| +-- V-curve ----------------------------------------------------+|
| | HFD px                                                        ||
| | 9 +  .                                              .         ||
| | 6 +          .                                .               ||
| | 3 +                    .  . | .  .                            ||
| |   +-------+---------+---------+---------+---------            ||
| |          500      1,000     1,500     2,000   position (steps) ||
| +---------------------------------------------------------------+|
| Best focus 3.10 px at 1,290 . parabola . measured               |
+-----------------------------------------------------------------+

  Running:
| [stop] Stop AF           step 7 / 14 . fine . 1,250 . HFD 3.4 px|
| ==========================--------------                        |
  Rejected:
| o Rejected  Flat HFD curve (3.1 - 3.3, span < 15%): focus unchanged |
  Cancelled:
| Autofocus cancelled: returned to 1,305                          |
```

The AF exposure comes from the Camera card; a one-line hint under the button says "AF frames: 2.0 s, gain 80 (Camera)" (fixes the hidden coupling of P8). Sweep settings stay in Settings if exposed (Q7).

**E. Drawer tabs (full drawer width, 216 px)**

```
+(log) Log | (focus-metrics) Focus | (session-metrics) Conditions --------------------------- (clear) (close)+
| HFD px  4 +       .   .          .                           |  HFD     3.4 px                         |
|         3 +  . .    .   .  . .     . .   .                   |  STARS   117                            |
| STARS 130 +                                                  |  SKY     2 000 ADU                      |
|       110 +---\__/------\_/-------                           |  FWHM    2.9 px (green plane)           |
|           +--21:04------------21:20------------21:36 UTC---  |  100 frames, full resolution            |
+-------------------------------------------------------------------------------------------------------+

  Conditions tab: <HFD|Stars|Sky|FWHM|Airmass|Sensor °C>  up to 3 selected, stacked, shared UTC axis
```

### 2.4 Interaction and states

- **Empty / offline.** Camera fields stay editable (plan before connecting, as Qt); actions show the disabled reason "connect the equipment first". Mount and Focuser show "—" readouts and the badge "Offline". The Target block search works offline from the cache (resolver cache, object_resolver.py:165-180) and says "Catalogue unavailable. Connect to the internet or use a previously searched target." when it cannot.
- **Driver limits unknown.** Fallback ranges are the Qt ones (exposure 0.01–600 s, gain 0–600) until `CameraState.limits` arrives, then the server's values. Out-of-range input shows the field error, never a clamp without notice.
- **Busy.** Every hardware action uses the existing runner (busy spinner, `aria-busy`, toast + log on failure). Filter: spinner on the requested slot, other slots disabled, error toast and revert to the polled slot. Focuser moving: badge "Moving", Out / In / Move disabled, Halt enabled. Catalogue lookup: spinner in the search button, field read-only, up to 8 s.
- **Ownership.** Badge on the Camera card header: "Live", "Exposing", "Sequence", "Autofocus". While a sequence or autofocus owns the camera, Camera fields and Offset / Binning are disabled with the reason "The sequence owns the camera" or "Autofocus owns the camera" (fixes P39). Starting autofocus during live view stops the live view and says so in a toast ("Live view stopped: autofocus owns the camera").
- **Autofocus.** States idle, running (stage coarse / fine / verify, step n / total, progress bar, V-curve filling, Focuser card unfolded), done (summary in `--fg` with "measured"), rejected (status badge "Rejected" + the exact reason, "focus unchanged"), cancelled ("returned to {start}"), failed (badge "Failed" + message); no new warning glyph is needed. Only "done" writes "Autofocus complete" to the log (fixes P43).
- **Mount.** Parked: GoTo, Tracking, Center, Jog disabled with "unpark the mount first" (built for GoTo / Tracking). Clock error: Slew, Center, Sync disabled with "Mount clock is {h} h off: correct the Seestar date and time, then reconnect" (fixes P26). Slewing: Abort turns danger (built). Jogging: the pressed arrow keeps its pressed style while its axis moves.
- **Confirmations.** Park (inline, built). Sync to plate solution (inline "Sync the mount to the solved field?" Sync / Cancel) if kept. No confirmation for Center, Slew, Stop AF, Halt (deliberate labelled buttons). "Use as target name" is itself the confirmation of a suggestion.
- **Keyboard.** Existing: `E`, `V`, `Esc`, view keys. Added: Enter submits the field it is in (search, GoTo, Go to). `J` (proposed) arms / disarms keyboard jogging; while armed and focus is not in a text field, arrow keys jog (key-down start, key-up stop, each axis tracked separately) and the pad shows the armed state; window blur, tab hidden or link loss stop every axis. `Esc` stops slew, jog axes and a manual focuser move (Q4). No single key starts autofocus, tracking or focuser steps (BRAND 7) unless the owner extends the exception (Q3).
- **Night Red.** No pictographs: every glyph from `icons/`. Segmented controls and custom menus only (the Stellarium candidate list included), never a native `<select>`. Plots: one series per plot in the chart tokens, samples as dots, fit as `--chart-reference`, best-focus line `--accent`, all red in Night Red; HFD readouts never rely on green / amber / red (Q9). Jog pressed state by fill luminance plus `aria-pressed`.
- **Persistence.** Per viewer (localStorage, try / catch, existing `prefs`): card open states (built), Sensor and Jog disclosures, jog speed, focuser step, drawer tab, selected Conditions metrics. On the server (shared by every client, survives a page reload): exposure, gain, frame type, filter, offset, binning, object name; preview quality per client (Q12, Q13). Qt persisted none of these.
- **Disconnect / error.** Mount lost: badge "Error", controls disabled, a toast "Mount connection lost; retrying every 10 s" (ds:557-571 behaviour kept server-side); the jog pad stops locally and the server dead-man stops the axes. Camera disconnect: limits return to fallbacks, Sensor rows hide. Focuser disconnect: autofocus is stopped first (ds:492 behaviour kept).

### 2.5 API needs beyond v1

| Name | Kind | Payload sketch | Core / worker code it wraps (file:line) | Notes |
|---|---|---|---|---|
| A1 Camera state extension | Fields in `CameraState` (status / camera events) | `limits {gain_min, gain_max, exposure_min_s, exposure_max_s}`, `offset {value, min, max}\|null`, `binning {value, max}\|null`, `temperature_c\|null`, `owner "idle"\|"live"\|"single"\|"sequence"\|"autofocus"`, `frame_type`, `filter`, `preview_scale` | camera.py:70-133 (limits cached at connect), ds:392-415, polling_worker.py:96-137 (10 s temperature), camera_service.py:60-77 | Temperature at 10 s rides on the next `camera` event |
| A2 Live settings | HTTP `PUT /api/camera/settings` | `{exposure_s?, gain?, frame_type?, preview_scale?}` -> CameraState | ae:392-403, exposure_worker.py:67-91 (`update_settings`, applies to the next frame) | Removes the "restart live view" limitation; 409 `busy` when a sequence owns the camera |
| A3 Capture that saves | HTTP `POST /api/camera/capture` (extend) + WS `{"type":"frame_saved","path","seq","object","filter"}` | `{exposure_s, gain, frame_type, save: true}`; during live: tags the next frame instead of 409 | ae:317-330, :1510-1594 (`_save_fits_async`, FITSWriter), ae:80-83; wheel logic of sequencer.py:115-123 | Server must snapshot the parameters used **for that frame** (fixes P4b) and move the wheel to Dark for Dark / Bias (fixes P1) |
| A4 Offset / binning | HTTP `POST /api/camera/offset`, `POST /api/camera/binning` | `{value: int}` -> CameraState | ds:741-757, camera.py:251-289; refusal logic ip:2504-2531 | 409 `busy` while sequence / autofocus own the camera; blocking Alpaca call off the event loop |
| A5 Frame metrics | Frame header field `metrics` or WS `{"type":"frame_metrics"}` | `{seq, hfd_px, star_count, sky_adu, peak_adu, fwhm_px\|null, scale: 1\|2}` | metrics.py:146 `frame_metrics`, debayer.py:284 `compute_hfd`, preview_processor.py:71 | Computed on the full-resolution frame, so HFD does not depend on preview quality (fixes P13); off the event loop |
| A6 Filter wheel | Status field `filterwheel` + WS `{"type":"filterwheel"}`; HTTP `POST /api/filterwheel/select` | state `{state: "disconnected"\|"idle"\|"moving"\|"error", slots: [names], position, name, message}`; body `{name}` | ds:430-458 (connect), :681-701 (move, settle), filterwheel.py:24-34, :90-135; sequence_worker.py:291-304 | Long-running (≤ 20 s); an error must end "moving" (fixes P2); sequence moves must publish too (fixes P3) |
| A7 Tracking rate | `MountState.tracking_rate`, `MountState.tracking_rates`; HTTP `POST /api/mount/tracking-rate` | `{rate: "sidereal"\|"lunar"\|"solar"}` | telescope.py:610-634 (set + `get_tracking_rate`), ds:637-645 | Read back after set (fixes P18); supported list from the driver (uncertain on Seestar) |
| A8 Sync | HTTP `POST /api/mount/sync` | `{source: "solution"}` or `{ra_hours, dec_deg}` | telescope.py:540-562, ds:585-593 | Only if Q1 keeps it; needs tracking on (switch it on first, as Center) |
| A9 Center on target | HTTP `POST /api/mount/center` + `MountState.center_available` | `{target?: {ra_hours, dec_deg, name}}` (default: photometry target, else last GoTo) | ip:2616-2640 (`_center_selected_target`), ds:595-626, `engine.astrometry` (ae:221) | Needs the plate solution on the server (astrometry spec); slew then reported by `mount` events |
| A10 Jog | HTTP `POST /api/mount/jog`, `POST /api/mount/jog/stop`; `MountState.jog {primary, secondary}`, `MountState.alignment` | `{axis: "primary"\|"secondary", rate_deg_s}`; stop `{axis?}` | telescope.py:564-592 (`move_axis`, `stop_axis`), ds:45-67, :665-679; alignment telescope.py:266 | **Dead-man**: the server stops an axis not renewed within about 1 s or when the client's event socket closes; rates checked against the driver AxisRates (not read today, uncertain) |
| A11 Mount clock guard | `MountState.goto_blocked` | `{reason: "clock", clock_error_s}\|null` | telescope.py:283-294, ds:286-290 | Lets the UI disable Slew / Center / Sync with a reason (fixes P26) |
| A12 Catalogue resolve | HTTP `GET /api/catalog/resolve?q=` | -> `{name, ra_hours, dec_deg, object_type, type_label, is_variable}` | object_resolver.py:369 `resolve_object`, :116 `object_type_label`, :136 `is_variable_object_type` | Up to 8 s network; errors with the exact messages of 1.2; works without equipment |
| A13 Target-name suggestions | WS `{"type":"target_suggestions"}` | `{ra_hours, dec_deg, state: "checking"\|"ready"\|"failed", candidates: [{name, type_label, separation_arcsec, ra_hours, dec_deg}], message}` | object_resolver.py:289 `resolve_nearby_objects`; ip:2733-2765; shell.py:346-353 | Emitted after a Stellarium GoTo; online lookup per config `stellarium.online_target_lookup` |
| A14 Observation identity | HTTP `GET` / `PUT /api/observation` + WS `{"type":"observation"}`; `POST /api/observation/target` | `{object_name}`; target `{name, ra_hours, dec_deg, object_type}` | camera_dock.py:321-342, ae:1010 `on_object_changed`, shell.py:166-179, ip:2658-2716 (`set_catalogue_target`, variable star -> photometry target) | Shared with the Plan and photometry specs |
| A15 Focuser state + telemetry | Status field `focuser` + WS `{"type":"focuser"}` | `{state: "disconnected"\|"idle"\|"moving"\|"error", name, position, target, temperature_c, max_step, max_increment, absolute, step_size_um}` | focuser.py:53-125 (capabilities, Position, IsMoving, Temperature), ds:460-505 | **New polling** (absent in Qt, fixes P4): position + IsMoving about every 0.5 s while moving, 5 s idle; temperature 10 s |
| A16 Focuser commands | HTTP `POST /api/focuser/move`, `/step`, `/halt` | `{position}`, `{delta}`, `{}` -> FocuserState | focuser.py:127-155, ds:705-739 | 409 `busy` during autofocus except halt; clamping reported in the answer (fixes P6) |
| A17 Autofocus | HTTP `POST /api/autofocus/start`, `POST /api/autofocus/stop`; WS `{"type":"autofocus"}` | start `{exposure_s?, gain?, half_range?, num_steps?}`; stop `{return_to_start: true}`; event `{state: "running"\|"done"\|"rejected"\|"cancelled"\|"failed", stage, step, total, samples: [{position, hfd_px\|null, stage}], best: {position, hfd_px, fitted_hfd_px, method}\|null, fit: {coeffs, window}\|null, message}` | autofocus_worker.py:48-232, ae:672-744, camera_service.py:138-207, focus.py:82-160 | Minutes long, cancellable, one event per step; the server applies the gain (fixes P8) and publishes the worker's own fit (fixes P9); stop and halt ordered on the server (fixes P43) |
| A18 Conditions timeline | HTTP `GET /api/session/conditions?since_seq=` + WS `{"type":"conditions"}` | rows `{t, seq, hfd_px, star_count, sky_adu, fwhm_px, airmass, sensor_temp_c, focuser_temp_c, focuser_position}` | hfd_history_dock.py:107-136, metrics_panel.py:62-80, ip:2370-2433 (airmass from altitude, temperature) | One row per processed frame whatever is open (fixes P10, P34); kept with the session for Review |

## 3. Open questions for the owner

1. **Sync**: keep the Qt behaviour (sync to the mount's own position, effectively a no-op), redefine it as "Sync to plate solution" without a slew, or drop it because Center already syncs?
2. **Jog labels**: North / South / East / West as in Qt, or mount-axis words (Up / Down / Left / Right, or Alt + / Alt − / Az − / Az +) on the alt-az Seestar? What should the pad do on a mount in EQ mode?
3. **Focus step keys**: BRAND 7 forbids single keys that move hardware (except the jog arrows and Esc), but the inventory proposes `[` / `]` for focus out / in. Extend the exception, use a modifier (for example Alt+[ / Alt+]), or no shortcut?
4. **Escape**: should it also stop jog axes and a manual focuser move (proposed), and should it cancel autofocus (proposed: no)?
5. **Observation identity**: one "Object" field in the Mount card's Target block, echoed as a frame chip, instead of the two Qt fields. Is that the right home given that Plan also edits it?
6. **Filter without a wheel**: keep the Qt "metadata only" choice (the name goes into FITS FILTER) or disable the filter row?
7. **Autofocus parameters**: expose half range, step count, settle time, AF exposure / gain (Settings or a Focuser disclosure), or keep them fixed?
8. **Stop AF vs Halt**: proposed Stop AF = cancel and return to the start position, Halt = stop where it is. Agree?
9. **HFD colour**: the Qt thresholds (green < 5 px, amber < 10 px) are scale-dependent and colour-only. Drop them, or make them a setting tied to the plate scale?
10. **Conditions timeline**: merge HFD history and the Metrics tab into one drawer tab (Focus + Conditions) recorded for the whole session and shown again in Review?
11. **Pop-out windows**: in the Tauri app, offer an always-on-top pop-out for the jog pad (the Qt dialog's use case) or the drawer?
12. **Preview quality**: still needed once frames travel over WebSocket (bandwidth), or replaced by a stream decimation chosen by the client?
13. **Capture settings**: shared on the server (every client and the next launch see the same exposure, gain, frame type, filter) or per viewer?
14. **Tracking rate**: offer Lunar / Solar at all on the Seestar (driver support not verified)?

## Appendix: verification list (every Qt widget in scope found by scan)

| Pattern | Occurrences -> inventory row |
|---|---|
| QComboBox | camera_dock.py:117, :132, :180 -> 1.1 #1, #3, #10; mount_dock.py:119, :174, :229 -> 1.2 #2, #6, #14; focuser_dock.py:83 -> 1.4 #1; metrics_panel.py:38 -> 1.7 #1; manual_control_dialog.py:105 -> 1.8 #1 |
| QSpinBox / QDoubleSpinBox | camera_dock.py:156, :166 -> 1.1 #8, #9; SliderSpin spins (design.py:222, :227) -> 1.1 #5, #7; mount_dock.py:197, :201 -> 1.2 #9, #10; focuser_dock.py:99 -> 1.4 #4 |
| QSlider | SliderSpin (design.py:217) in camera_dock.py:142, :149 -> 1.1 #4, #6 |
| QLineEdit | camera_dock.py:122 -> 1.1 #2; mount_dock.py:138 -> 1.2 #3 |
| QPushButton and design buttons | camera_dock.py:204, :207; mount_dock.py:116, :145, :156, :176, :181, :210, :212, :215, :246 (x4), :252, :270, :273, :276; focuser_dock.py:88, :91, :103, :116, :118; hfd_history_dock.py:90; manual_control_dialog.py:131 (x4), :137 -> all listed |
| QMessageBox | mount_dock.py:426 -> 1.3 |
| QDialog | manual_control_dialog.py:66 -> 1.8 |
| keyPressEvent / keyReleaseEvent | manual_control_dialog.py:184, :199 -> 1.8 #7-#10 |
| QAction / QMenu / QToolButton (for these docks) | ip:354-389, :393-411 -> 1.9 |
| QCheckBox, QRadioButton, QTabWidget, QTableWidget, QFileDialog, setShortcut, QShortcut | none in the seven files (QTabWidget hosting E7 is photometry_window.py:228, other spec) |
