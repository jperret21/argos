# Application shell and global elements: Qt inventory and web redesign

Spec 01 of the web-UI consolidation. Author: shell agent. Status: draft for the owner.
Source of truth: the Qt code at branch `explore/web-ui` (version 0.4.2). Every claim cites
`file:line`; anything not verified says so. Screenshots used for checking (offscreen Qt,
not committed) are in the session scratchpad `webui-spec/shell/`.

## 0. Scope

### 0.1 Files covered

| File | Lines | What it holds |
|---|---|---|
| `main.py` | 197 | Entry point: Qt plugin fix, config, logging, crash reporter, splash stages, palette, Shell |
| `argos/ui/shell.py` | 625 | `Shell(QMainWindow)`: layout, menu bar, signal fan-out, persistence, About, support bundle, close |
| `argos/ui/sidebar.py` | 299 | `Sidebar(QToolBar)` nav rail, `_NavButton`, state dots, `MODES` |
| `argos/ui/statusbar.py` | 320 | `TopStatusBar`: device badges, capture strip, network, mount geometry, tracking, last action |
| `argos/ui/splash.py` | 183 | `Splash(QSplashScreen)`: logo, version, staged progress |
| `argos/ui/panels/log_panel.py` | 84 | `LogPanel`: the Activity log (hosted as an Observe dock) |
| `argos/ui/widgets/dock_host.py` | 180 | `make_dock`, `style_toggle_action`, `panel_toolbar_qss`: the dock mechanism of Observe, Plan, Review |
| `argos/ui/theme.py` | 706 | Palette rebinding, `LOG_COLORS`, global QSS (behaviour only here) |
| `argos/ui/design.py` | 447 | Spacing scale, Card, SliderSpin, button classes, `stat_color` (behaviour only) |
| `argos/ui/palettes.py` (read for theme behaviour) | 162 | The three palettes |
| Total in scope | 3 203 | |

Followed into (read-only, for real effects): `argos/core/config.py`, `argos/core/support_bundle.py`,
`argos/workers/network_monitor.py`, `argos/workers/astrometry_controller.py`,
`argos/core/session/acquisition_engine.py`, `argos/core/session/device_session.py`,
`argos/ui/pages/{imaging,analyze,sequencer,configuration}_page.py`, `argos/ui/widgets/sequence_panel.py`.

### 0.2 Elements in scope and how each is opened

| # | Element | Class / ref | Kind | Opened by |
|---|---|---|---|---|
| E1 | Start-up sequence | `main.main` main.py:137 | process lifecycle | launching `main.py` / `run.sh` / packaged app |
| E2 | Splash | `Splash` splash.py:99 | frameless `QSplashScreen` | main.py:150 unless `ARGOS_NO_SPLASH` (main.py:128) |
| E3 | Main window | `Shell` shell.py:75 | `QMainWindow` | main.py:178-181 |
| E4 | Menu bar (File, More, View, Field, Photometry) | shell.py:185-285 | menu bar | always (native global menu on macOS) |
| E5 | Navigation rail | `Sidebar` sidebar.py:232 | left `QToolBar` | always (shell.py:120-121) |
| E6 | Top status strip | `TopStatusBar` statusbar.py:30 | strip above the pages | always (shell.py:112-113) |
| E7 | Activity log | `LogPanel` log_panel.py:23 | dock "Activity log" on Observe | imaging_page.py:298, visible by default |
| E8 | Dock mechanism | dock_host.py:48, 122, 134 | `QDockWidget` factory + toggle chips | used by Observe (imaging_page.py:279), Plan (sequence_panel.py:489), Review (analyze_page.py:198) |
| E9 | About dialog | `_build_about_dialog` shell.py:535 | modal `QDialog` | More > About & credits (shell.py:223) |
| E10 | Support bundle flow | `_create_support_bundle` shell.py:478 | 1 question box, 2 file dialogs, 2 message boxes | More > Create local support bundle… (shell.py:216) |
| E11 | Theme and appearance behaviour | theme.py:46, palettes.py:162, configuration_page.py:716 | settings card + runtime rebinding | Settings > Files · application > Appearance |
| E12 | Implicit window status bar | `QMainWindow.statusBar()` shell.py:457, 605 | transient message bar | created lazily by the first message |
| E13 | Implicit window context menu | `QMainWindow.createPopupMenu` (Qt default) | context menu | right-click on the rail |
| E14 | Shutdown sequence | `Shell.closeEvent` shell.py:611 | lifecycle | File > Quit, window close box, Cmd+Q |
| E15 | Cross-page wiring | shell.py:166-179, 303-411 | implicit behaviours | signals |

Dialogs opened from the shell but owned by other areas (described in depth by their specs, listed
in Appendix A): `AstrometrySettingsDialog` (shell.py:470), `PhotometryWindow` (via
imaging_page.py:2093), Re-run subs flow (imaging_page.py:2248), `AnalyzeScreen._open_lightcurve`
(analyze_page.py:732).

## 1. Inventory (Qt, as it is today)

### 1.1 Start-up sequence (`main.main`, main.py:137, process lifecycle, no window of its own)

- Purpose: build the application, honest staged start-up, apply the palette before any widget.

Steps, in order:

| Step | Code | Effect |
|---|---|---|
| Qt plugin fix (macOS only) | main.py:31-79 | Sets `QT_QPA_PLATFORM_PLUGIN_PATH`; removes the quarantine xattr from the PyQt6 tree once per install, stamp `.argos-qt-prepared` in site-packages (main.py:14, 63-74). Best effort, errors swallowed (main.py:75-76). |
| QApplication | main.py:139-141 | Application and organisation name "Argos". |
| Config | main.py:143 -> config.py:197-219 | Reads `~/.argos/config.json`; first run writes the defaults (config.py:200-204); a corrupt file falls back to defaults with an error log (config.py:217-219). Migrations: config.py:210-214. |
| Logging | main.py:144 -> support_bundle.py:67-101 | Console + rotating file `argos.log` (2 MB x 5) in `~/Library/Logs/Argos` (macOS) or `$XDG_STATE_HOME/argos` (support_bundle.py:56-64). Level from `ui.log_level` (default `INFO`), read only here. |
| Crash reporter | main.py:145 -> support_bundle.py:126-147 | Uncaught main-thread and thread exceptions write `crash-<UTC>-<pid>.txt` in the same folder. Nothing is shown to the user. |
| Splash | main.py:150, 122-134 | Shown unless env `ARGOS_NO_SPLASH` is set. |
| Stage `config` | main.py:157 | Splash 5 % "Reading configuration…" (already read at this point). |
| Stage `imports` | main.py:159-160 | Imports `argos.ui.shell` (numpy, astropy, pyqtgraph, alpyca). 35 %. |
| Stage `profile` | main.py:166-168 | `hardware.load_from_config(config)` (telescope profile, default `s30pro`, config.py:67-70). 45 %. |
| Stage `theme` | main.py:173-175 | `ui.theme.preset` -> `theme.apply_palette`, global QSS. 55 %. |
| Stage `shell` | main.py:177-178 | `Shell(config)`: builds all five pages and their docks. 90 %. |
| Stage `layout` | main.py:180-181 | `window.show()`. 100 %. |
| Failure | main.py:182-187 | Any exception: `splash.fail()` closes the splash, exception re-raised (traceback on stderr, crash file written). No dialog. |
| Ready | main.py:189-193 | `splash.finish(window)`, event loop. |

- Implicit behaviours: devices are never connected at start-up (shell.py:69-72 comment); the
  network monitor starts immediately (shell.py:131-133).
- First run: no wizard, no welcome. Defaults are written, the Shell lands on Connection
  (shell.py:93-95), observer and site are empty (config.py:43-56).
- Messages: none visible. Log lines "Argos starting" (main.py:148), "Driving %s" (main.py:168),
  "UI ready" (main.py:192).
- Problems found:
  - P1 A start-up failure is invisible to a user who launched from Finder or a desktop icon: the
    splash closes and nothing else appears (main.py:182-187); the crash file is never mentioned.
  - P2 Stage labels are not fully honest: "Reading configuration…" is shown after the config was
    read (main.py:143 vs 157); "Restoring layout…" is shown at `show()`, the layout was restored
    inside `Shell()` (shell.py:91).

### 1.2 Splash (`Splash`, splash.py:99, frameless `QSplashScreen`, opened by main.py:150, non-modal, centred, 460 x 280 px)

- Purpose: logo, wordmark, version, licence and staged progress during start-up.
- Controls: none (Qt splash closes on click by default; not overridden, so a click hides it early: Qt default behaviour, not verified on macOS).
- Displayed data:

| Item | Source | Refresh |
|---|---|---|
| Logo 96 px | `assets/logo.svg`, fallback `logo.png`, else nothing (splash.py:66-96) | once |
| Wordmark "Argos" 26 pt DemiBold | splash.py:120-125 | once |
| "Version 0.4.2" | `argos.__version__` (splash.py:131-133) | once |
| Progress bar 340 x 4 px, gold on dark | `STAGES` fractions (splash.py:53-60, 147-158) | each `stage()` |
| Status text | stage label (splash.py:160-164) | each `stage()` |
| "GNU GPL v3 — free software, with no warranty - Developed by Jules Perret" | splash.py:137-145 | once |

- Stage labels (exact): "Reading configuration…", "Loading scientific libraries…", "Resolving
  telescope profile…", "Applying theme…", "Building the workspace…", "Restoring layout…"
  (splash.py:54-59). Initial text "Starting…" (splash.py:104). Unknown keys advance the text, not
  the bar (splash.py:168-178).
- Implicit: `stage()` forces `repaint()` + `processEvents()` (splash.py:177-178). `fail()` logs
  "Startup failed during %r: %s" and closes (splash.py:180-183).
- Problems found:
  - P3 Fixed brand colours (gold `#c49a3c`, text `#dedede`) whatever the theme (splash.py:44-48):
    with Night Red active the first thing on screen emits non-red light (BRAND 4.3 forbids a bright
    splash).
  - P4 The 26 pt title box (y 140, h 38) touches the version line (y 176) (splash.py:125, 131);
    visible on the offscreen grab.
  - P5 Wordmark is "Argos", BRAND wordmark is "ARGOS" in Plex Sans 600.

### 1.3 Main window (`Shell`, shell.py:75, `QMainWindow`, top-level)

- Purpose: the single window: rail + status strip + stacked pages.
- Geometry: title "Argos  v0.4.2" (shell.py:84, two spaces), minimum 1100 x 700 (shell.py:85),
  default 1440 x 900 (shell.py:86).
- Layout: central widget = `TopStatusBar` (32 px) above a `QStackedWidget` (shell.py:105-118);
  `Sidebar` added as a left tool bar (shell.py:120-121).

| # | Control | Qt type | Label / tooltip (exact) | Default / range | Enabled / visible when | Shortcut | Action: handler -> effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Window close box | window frame | — | — | always | platform close | `closeEvent` shell.py:611 -> shutdown sequence (1.14) | — |
| 2 | Window move / resize | window frame | — | min 1100 x 700 | always | — | saved on close by `_save_state` shell.py:443-445 | `ui.shell.geometry` (base64 `saveGeometry`) |
| 3 | Right-click on the rail | implicit `QMainWindow` context menu (`createPopupMenu`) | single checkable entry "Modes" (verified offscreen) | checked | right-click on the `Sidebar` tool bar | — | unchecking hides the navigation rail | `ui.shell.state` (base64 `saveState`, shell.py:445) |

- Displayed data: the active page (`QStackedWidget`, shell.py:115).
- Implicit behaviours:
  - Start mode: `ui.shell.mode` (default `connect`); `capture` (Observe) is never restored and
    becomes `connect`, because devices are never connected at start-up (shell.py:72, 93-96).
  - `_restore_state` (shell.py:429-441) restores geometry and tool-bar state; failures only log a
    warning.
  - Every mode switch writes `ui.shell.mode` (shell.py:406), and `Config.set` rewrites
    `config.json` on every call (config.py:241-248).
  - Pages built eagerly at start-up (shell.py:135-139); the network monitor thread starts
    (shell.py:131-133).
- Problems found:
  - P6 Right-clicking the rail offers "Modes" (Qt default, verified with `createPopupMenu`);
    unchecking it hides the rail, the hidden state is saved in `ui.shell.state` on close and
    restored next launch. Nothing in the UI brings it back (F1-F5 still switch pages).
  - P7 Config defaults `ui.window_state` / `ui.window_geometry` (config.py:59-60) are dead: the
    Shell uses `ui.shell.state` / `ui.shell.geometry` (shell.py:64-65).
  - P8 Docstring "Three-mode workspace shell" (shell.py:76) and module text "Equipment / Capture /
    Analyze" (shell.py:5-9) disagree with the five labels the user sees.

### 1.4 Menu bar (shell.py:185-285, `QMenuBar`; native global menu on macOS)

- Purpose: files, resources, navigation, field identification and photometry entry points.

| # | Menu | Control | Qt type | Label / tooltip (exact) | Enabled when | Shortcut | Action: handler -> effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | File | Open FITS image… | QAction shell.py:192 | tip "Open a saved FITS image in Capture; then use Field → Identify field." | always | `StandardKey.Open` (Cmd+O / Ctrl+O) shell.py:193 | `_open_fits_from_menu` shell.py:287 -> switch to Observe, `ImagingPage.open_fits` imaging_page.py:1341 -> file dialog "Open FITS" (imaging_page.py:1320), `astropy.io.fits.getdata`, must be 2-D, then `engine.ingest_frame` (imaging_page.py:1335); log "Loaded <name> — solve to enable catalog & photometry." or "Open FITS: <exc>" | — |
| 2 | File | Open session photometry… | QAction shell.py:197 | tip "Open the saved differential-photometry measurements of a session" | always | Ctrl+Shift+O (Cmd+Shift+O) shell.py:198 | `_open_session_photometry_from_menu` shell.py:291 -> switch to Review, `AnalyzeScreen.open_session_photometry` analyze_page.py:601 -> `_open_lightcurve` analyze_page.py:732: CSV picker "Open session light curve", `read_curves_csv`, opens a separate floating `PhotometryWindow` (analyze_page.py:747-763) | — |
| 3 | File | Quit Argos | QAction shell.py:203 | (no tip) | always | `StandardKey.Quit` (Cmd+Q macOS, Ctrl+Q Linux; Qt defines none on Windows: unverified here) shell.py:204 | `self.close` -> `closeEvent` (1.14) | — |
| 4 | More | Documentation & website | QAction shell.py:212 | tip "Open the Argos documentation and project website" | always | — | `_open_project_website` shell.py:602 -> `QDesktopServices.openUrl("https://github.com/jperret21/argos")`; failure -> window status message "Could not open the Argos website." 4 s | — |
| 5 | More | Create local support bundle… | QAction shell.py:216 | tip "Create a local ZIP of redacted logs and optionally session metadata. Nothing is uploaded." | always | — | `_create_support_bundle` shell.py:478 (1.10) | — |
| 6 | More | About & credits | QAction shell.py:223 | (no tip) | always | — | `_show_about` shell.py:474 -> modal About (1.9) | — |
| 7-11 | View | Connection / Observe / Plan / Review / Settings | QAction x 5 shell.py:230-234, built from `MODES` | (no tip) | always | F1 / F2 / F3 / F4 / F5 shell.py:232 (window shortcuts: fire from text fields too) | `Sidebar.select(mode)` sidebar.py:266 | `ui.shell.mode` |
| 12 | View | Reset Window Layout | QAction shell.py:237 | (no tip) | always | — | `_reset_layout` shell.py:452: sets `ui.shell.geometry`, `ui.shell.state`, `ui.sequencer.layout`, `ui.review.layout` to `None`; window status message "Window layout will reset on next launch." 4 s | clears 4 keys (not `ui.imaging.layout`) |
| 13 | Field | Identify field | QAction shell.py:244 | tip "Find coordinates and scale for the current image (ASTAP)" | always (no guard) | — | `engine.solve_now` acquisition_engine.py:767: needs a frame and a full-resolution preview, else WARN "No frame to solve yet — start a preview first." / "Preview is at half quality — set Preview to Full res to plate-solve."; else ASTAP solve with the mount hint, CMD "Plate-solving current frame… (hint RA …h Dec …°)" or "(blind — no mount)"; failure ERROR "Solve: <msg>" | — |
| 14 | Field | Keep field identified automatically | checkable QAction shell.py:248 | tip "Refresh field coordinates when needed so the grid and markers follow the field.\nIt is enabled automatically during a sequence." | always | — | `toggled` -> `AstrometryController.set_auto` astrometry_controller.py:82 (status text "Auto-solve on/off"); also set by `ImagingPage.auto_solve_armed` (shell.py:257): a sequence start arms it when a WCS exists, its end restores the previous choice (imaging_page.py:2538-2548) | not persisted (off at launch) |
| 15 | Field | Configure field identification… | QAction shell.py:260 | (no tip) | always | — | `_open_astrometry_settings(SECTION_ASTROMETRY)` shell.py:463 -> modal `AstrometrySettingsDialog` on tab "Plate solving"; on Save -> `engine.refetch_catalog` acquisition_engine.py:815 | `astrometry.*` (by the dialog) |
| 16 | Field | Configure catalogues… | QAction shell.py:263 | (no tip) | always | — | same dialog on tab "Field catalogue" | `catalog.*` (by the dialog) |
| 17 | Photometry | Photometry setup… | QAction shell.py:270 | tip "Choose a variable-star target and review the comparison-star ensemble in this field" | always | — | `ImagingPage.open_photometry(select_variable=True)` imaging_page.py:2083 -> creates or raises the floating "Field photometry" window, tab Variable stars (imaging_page.py:2142-2145) | — |
| 18 | Photometry | Live curves & diagnostics… | QAction shell.py:278 | tip "Open live differential light curves, image quality and selected stars" | always | — | same window, current tab kept | — |
| 19 | Photometry | Re-run subs… | QAction shell.py:282 | tip "Re-run differential photometry over a folder of saved subs" | always | — | `ImagingPage.rerun_subs` imaging_page.py:2087 -> precondition boxes (Appendix A), folder picker "Folder of saved subs", `PhotometryBatchWorker` with a "Batch photometry" progress dialog | — |

- Messages: window status bar "Window layout will reset on next launch." (shell.py:457), "Could not
  open the Argos website." (shell.py:605); the menu handlers' own messages are listed above.
- Problems found:
  - P9 Reset Window Layout does nothing: `closeEvent` calls `_save_state`, which writes the four
    cleared keys again from the live window before quitting (shell.py:622, 443-450). It also never
    clears `ui.imaging.layout` (imaging_page.py:121), the busiest workspace. The per-page "Reset
    layout" buttons work live (imaging_page.py:500, analyze_page.py:423, sequence_panel.py:584).
  - P10 None of the menu tooltips is ever shown: `QMenu.toolTipsVisible` is false by default and
    no code enables it (no `setToolTipsVisible` in argos/ui). The explanations of items 1, 2, 4, 5,
    13, 14, 17-19 are invisible.
  - P11 "&" in "Documentation & website" and "About & credits" (shell.py:212, 223, 594) is read
    as a mnemonic on the following space: the ampersand disappears ("Documentation  website"), the
    About button renders "Documentation _website" (offscreen grab) and the derived tooltip is
    "About  credits" (verified).
  - P12 "Documentation & website" opens the GitHub repository, not the documentation site
    (`perretjules.com/argos`, README.md:40) (shell.py:67).
  - P13 "Open session photometry…" switches to Review but opens a CSV in a separate floating
    window, while Review's own "Open session…" loads a session folder into the page
    (analyze_page.py:605). Two different operations share one icon id (`open-session`). An empty
    CSV only logs a Python warning, no UI feedback (analyze_page.py:741-743).
  - P14 Inconsistent context switching: Open FITS switches to Observe (shell.py:288) but Identify
    field, auto-solve and the Photometry items act on Observe without switching, and their feedback
    goes to the Observe Activity log, invisible from another page.
  - P15 Item tips and status texts say "Capture" (shell.py:194, statusbar.py:75) for the page
    labelled Observe.
  - P16 On macOS, Qt's default text heuristic (`QAction.MenuRole.TextHeuristicRole`) moves "Quit
    Argos" and "About & credits" to the application menu, and one item starting with "Settings" or
    "Config…" becomes Preferences. Which one wins is not verified (offscreen platform has no
    native menu).
  - P17 The Field dialog duplicates the ASTAP controls of Settings > Astrometry
    (astrometry_settings.py:90-110 vs configuration_page.py:640-714).

### 1.5 Navigation rail (`Sidebar`, sidebar.py:232, `QToolBar` on the left, fixed 92 px, always visible)

- Purpose: switch between the five workflow phases; show a state dot per phase.
- Layout: entries 88 x 66 px, 24 px Feather icon above an 11 px label (sidebar.py:144, 155-162);
  Settings pushed to the bottom after a spacer and a separator (sidebar.py:250-256).

| # | Control | Qt type | Label / tooltip (exact) | Enabled / visible | Shortcut | Action -> effect | Persisted |
|---|---|---|---|---|---|---|---|
| 1 | Connection | `_NavButton` sidebar.py:124 | "Connection" / tip "Connect the telescope equipment" (sidebar.py:39) | always | F1 (View menu); Tab focus + Space / Return / Enter (sidebar.py:145, 206-210) | left-release inside -> `Sidebar.select("connect")` sidebar.py:212-215, 266-273 -> `mode_changed` -> `Shell._on_mode_changed` shell.py:401 -> stack page, `ui.shell.mode` | `ui.shell.mode` |
| 2 | Observe | same | "Observe" / "Frame, focus and monitor the observation" (sidebar.py:40) | always | F2 | select "capture" | same |
| 3 | Plan | same | "Plan" / "Plan and run the night's capture sequence" (sidebar.py:41) | always | F3 | select "sequencer" | same |
| 4 | Review | same | "Review" / "Inspect the light curve and export AAVSO" (sidebar.py:42) | always | F4 | select "analyze" | same |
| 5 | Settings | same | "Settings" / "Observer, site, paths, appearance" (sidebar.py:43) | always (bottom) | F5 | select "settings" | same |

- Displayed data: selected entry = accent icon and label, surface fill, 3 px accent left border;
  hover / keyboard focus = `FG` on surface (sidebar.py:217-229). State dot "●" 8 px top-right
  (sidebar.py:165-169):

| Dot | Colour | Rule (shell.py:386-399) |
|---|---|---|
| ready | `SUCCESS` | Observe: camera `connected` or `busy` |
| active | `ACCENT` | Observe: autofocus running; Plan: sequence running |
| blocked | `WARNING` | Observe: camera not connected |
| none | hidden | Connection, Review, Settings always; Plan when idle |

- Implicit: `select` ignores an unknown id or the current one (sidebar.py:268); icons cached per
  (mode, colour) (sidebar.py:83-111), so a live palette change leaves stale icon colours.
- Problems found:
  - P18 Observe shows the amber "blocked" dot at every launch, because devices are never
    auto-connected (shell.py:393-397): warning colour for the normal initial state.
  - P19 Live view does not mark Observe "active"; only autofocus does (shell.py:394-397).
  - P20 `mode_changed` comment lists a `target` mode that does not exist (sidebar.py:235).

### 1.6 Top status strip (`TopStatusBar`, statusbar.py:30, 32 px strip above every page, always visible)

- Purpose: "am I connected, is the mount tracking, is a run going" on every page.
- Layout, left to right (statusbar.py:33-38): device badges | stretch | capture strip | stretch |
  network | mount geometry | tracking | separator | last action.

| # | Control | Qt type | Label / tooltip (exact) | Visible when | Action: handler -> effect |
|---|---|---|---|---|---|
| 1 | Mount badge | `_Badge(QLabel)` statusbar.py:276 | glyph + "Mount" [+ " · info"]; no tooltip | always | any mouse button press (statusbar.py:318-320) -> `badge_clicked("mount")` -> `Shell._on_badge_clicked` shell.py:409: switch to Connection only if the badge state is `disconnected` |
| 2 | Camera badge | same | "Camera" | always | same |
| 3 | Filter Wheel badge | same | "Filter Wheel" | always | same |
| 4 | Focuser badge | same | "Focuser" | always | same |
| 5 | Capture strip | `_ClickLabel` statusbar.py:261 | tip "Capture in progress — click to open the Capture screen" (statusbar.py:75) | sequence running or LIVE (statusbar.py:233-258) | left press -> `capture_clicked` -> select Observe (shell.py:317) |

- Displayed data:

| Readout | Text (exact formats) | Source and refresh |
|---|---|---|
| Badge state | `○` disconnected (muted), `●` connected (success), `◐` busy (warning), `✗` error (danger) + label + optional " · info" (statusbar.py:294-316) | `device_state_changed(device, state, info)` relayed by `ImagingPage` (shell.py:305, 367-372); emitted at device_session.py:292-698 (connect name, "slewing", "moving", filter name, error text cut to 48 chars) and acquisition_engine.py:366, 375 ("exposing") |
| Capture strip, sequence | "●REC  ·  <object>  ·  <done>/<total>  ·  ETA <m>m<ss>s  ·  HFD <x.x>" in danger colour, mono, bold (statusbar.py:237-247) | `engine.sequence_running` / `sequence_progress` (shell.py:312-313), HFD `hfd_updated` (shell.py:314) |
| Capture strip, live | "LIVE  ·  HFD <x.x>" success colour (statusbar.py:248-252) | `camera_state_changed` == LIVE (shell.py:383-384) |
| Network | "Seestar ●/○   Net ●/○" (statusbar.py:166-168); tip "Seestar: the configured address answers on the Alpaca port.\nNet: internet is reachable (AAVSO catalogs available)." | `NetworkMonitor` every 10 s: TCP connect to `alpaca.host:port`, then 1.1.1.1:53 / 8.8.8.8:53, 1.5 s timeout each (network_monitor.py:32-84). Empty until the first result. |
| Mount geometry | "Alt-Az" / "EQ" / "EQ (GEM)", hidden when unknown; tip "Mount geometry reported by the firmware.\nAlt-Az: the field rotates during a session (apertures drift on long runs).\nEQ (wedge): no field rotation." (statusbar.py:98-110) | `session.mount_mode` (shell.py:328; device_session.py:293, 332, 348, 562) |
| Tracking | "Tracking —" muted / "Tracking ON" success / "Tracking OFF" warning (statusbar.py:179-191) | `tracking_changed` (shell.py:306) |
| Last action | mono, default "Idle" (statusbar.py:126-131, 193-194) | `action_changed`, last writer wins, from: device_session.py:238, 263, 268, 354, 433, 463 ("Connecting mount <host>:<port>…", "Disconnected", …); astrometry state ("Plate-solving…", "Auto-solve on", "WCS cleared (slew)", "Solve failed — keeping last WCS", "Idle": astrometry_controller.py:85-216); exposure worker ("Exposing  <t>s…", "Downloading…": exposure_worker.py:114-149); camera ownership ("Idle", "Live preview", "Taking shot…", "Sequence running", "Autofocus running": imaging_page.py:126-132, 633); "Focused  pos=<n>" (imaging_page.py:2848) |

- Implicit: HFD re-renders only while a run or live is active (statusbar.py:227-231); sequence end
  clears object, counts and ETA (statusbar.py:204-211).
- Problems found:
  - P21 The strip stylesheet has no selector (statusbar.py:47), so `border-bottom` cascades to every
    child label: each badge and readout is underlined (visible on the offscreen grab).
  - P22 "Seestar ○" means both "unreachable" and "no host configured" (statusbar.py:161-164);
    the label is empty for up to ~4.5 s at launch (network_monitor.py:79-84).
  - P23 Badges have no tooltip; an error shows at most 48 characters in the strip and the full text
    nowhere else in the strip (device_session.py:297, statusbar.py:309-311).
  - P24 Clicking a badge in `error` state does nothing (shell.py:409-411); any mouse button, right
    included, triggers the click (statusbar.py:318-320).
  - P25 The last-action label has no time and no history; a later message (e.g. "Auto-solve on")
    hides a more important one ("Sequence running").
  - P26 Capture-strip tooltip says "Capture in progress" also for LIVE, and names "Capture".
  - P27 Unicode pictographs in UI text (●REC, ◐, ✗) are forbidden by BRAND 4.3 in the web UI.

### 1.7 Activity log (`LogPanel`, log_panel.py:23, dock "Activity log" in Observe's bottom area, visible by default, tabbed with the hidden light-curve dock: imaging_page.py:298, 472-475)

- Purpose: timestamped, colour-coded session log.

| # | Control | Qt type | Label | Default | Action -> effect |
|---|---|---|---|---|---|
| 1 | Clear | QPushButton log_panel.py:42 | "Clear" (60 px, right-aligned) | enabled | `QTextEdit.clear` (rewired at log_panel.py:57-58) |
| 2 | Log text | read-only QTextEdit, no wrap, mono 11 px (log_panel.py:48-54) | — | — | mouse selection, Cmd/Ctrl+C, native context menu "Copy" / "Select All" (Qt default) |

- Displayed data: one row per message, `HH:MM:SS` local time (log_panel.py:72), `[LEVEL]` bold in
  `theme.LOG_COLORS[level]` (theme.py:97-106: DEBUG muted, INFO accent, OK success, WARNING and
  DISC warning, ERROR / CRITICAL danger, CMD cyan), message HTML-escaped. Always scrolls to the
  bottom (log_panel.py:83-84).
- Sources (imaging_page.py:516, 531, 614, 2796): `DeviceSession.log_message`,
  `AcquisitionEngine.log_message`, `ImagingPage.log_message` and the Manual Control dialog. 148
  `log_message.emit(` sites (plus indirect `log_emit` / `_log` helpers, e.g.
  acquisition_engine.py:1591, manual_control_dialog.py:167); literal levels used: CMD 26, ERROR 27,
  INFO 30, OK 27, WARN 38.
- Problems found:
  - P28 The 38 `WARN` messages are not coloured: `LOG_COLORS` has `WARNING`, not `WARN`
    (log_panel.py:71, theme.py:97-106).
  - P29 Unbounded growth over a night (log_panel.py:80) and forced scroll to the bottom even while
    the user reads older lines (log_panel.py:83-84).
  - P30 Dead wiring: `clear_btn.clicked.connect(self._text.clear if hasattr(...) else lambda: None)`
    then disconnect / reconnect (log_panel.py:44, 57-58).
  - P31 Only Observe's sources reach it; Plan, Review and Settings report through their own status
    labels or the Python logger only (e.g. analyze_page.py:742). The `ui.log_level` setting does
    not filter it. No filter, search or save; local time while BRAND section 5 wants UTC.

### 1.8 Dock mechanism (`make_dock` dock_host.py:48, `style_toggle_action` dock_host.py:122, `panel_toolbar_qss` dock_host.py:134)

- Purpose: every Observe, Plan and Review panel is a `QDockWidget` inside a page-local
  `QMainWindow` (imaging_page.py:256-264, sequence_panel.py:211, analyze_page.py:81) that the user
  can move, tab, nest, close and float to another monitor.
- `make_dock`: stable `objectName` (needed by `saveState`), features movable + closable + floatable
  (dock_host.py:66-74); a `design.Card` loses its title (the dock title replaces it) and gets compact
  margins (dock_host.py:82-90); with `scroll=True` the content sits top-aligned in a frameless
  vertical scroll area (dock_host.py:92-112).

| # | Control (per dock) | Qt type | Label / tooltip | Action -> effect | Persisted |
|---|---|---|---|---|---|
| 1 | Title bar drag | QDockWidget title | dock title | move, tab onto, nest beside another dock (`AllowTabbedDocks`, `AllowNestedDocks`, `GroupedDragging`, imaging_page.py:259-264) | page layout key |
| 2 | Float button | title-bar button | — (Qt) | detach to a floating window (second monitor) | page layout key |
| 3 | Close button | title-bar button | — (Qt) | hide the dock | page layout key |
| 4 | Title double-click | Qt implicit | (documented in chip tooltips) | float / re-dock | page layout key |
| 5 | Panel chip | `toggleViewAction` restyled (dock_host.py:122-131) in a page tool bar | per page: tip "Show/hide <label>. Drag its title bar to arrange it; double-click the title to detach it." (imaging_page.py:356-359), Review analyze_page.py:272-274, Plan "Drag the panel title to arrange it; double-click to detach it." (sequence_panel.py:525) | show / hide the dock, check state follows real visibility | page layout key |
| 6 | Right-click on a dock title or the page tool bar | implicit `createPopupMenu` | list of all docks (verified: Observe 8, Review 5 listed, Plan 5) | show / hide | page layout key |

- Per-page instances (owned by the section specs, listed here so the census closes): Observe
  "Panels ▾", "Arrange ▾" (Restore default layout; Float / Dock <panel> x 8), "Reset layout"
  (imaging_page.py:348-414); Review "Panels ▾", "Arrange ▾" (Tile plots — 2 columns, Restore
  default layout, Float / Dock …), "Tile plots — 2 columns", "Reset layout" (analyze_page.py:252-300,
  427-447); Plan five chips + "Reset panels" (sequence_panel.py:512-531).
- Layout keys: `ui.imaging.layout`, `ui.sequencer.layout`, `ui.review.layout` (saved on close only:
  shell.py:448-450).
- Problems found: P9 (reset); P32 a page-level reset is live but the shell-level one is not; the
  two use different words ("Reset layout", "Reset panels", "Restore default layout", "Reset Window
  Layout").

### 1.9 About dialog (`_build_about_dialog`, shell.py:535, modal `QDialog` "About Argos", min width 460, opened by More > About & credits)

| # | Control | Qt type | Label | Shortcut | Action -> effect |
|---|---|---|---|---|---|
| 1 | Documentation & website | QDialogButtonBox ActionRole button shell.py:593 | "Documentation & website" (renders "Documentation _website", P11) | — | `_open_project_website` shell.py:602 |
| 2 | Close | QDialogButtonBox Close shell.py:592 | "Close" | Esc (QDialog default) | `reject` |

- Displayed data (exact): logo 104 px from `assets/logo.png` (shell.py:546-559); "Argos" 26 px
  bold; "Version 0.4.2"; "Scientific acquisition and differential photometry for ZWO Seestar
  telescopes."; "**Credits**<br>Created and maintained by Jules Perret.<br><br>Built with Python,
  PyQt6, NumPy, Astropy, pyqtgraph and ASCOM Alpaca.<br><br>Copyright © 2026 Argos contributors ·
  GNU GPL v3 or later." (shell.py:580-585).
- Problems found:
  - P33 `logo.png` has an opaque white background (verified pixel 0xffffffff): a white square in
    every theme, Night Red included (shell.py:549).
  - P34 Settings > Files · application has a second "About" card with other wording
    (configuration_page.py:766-773: "Argos — ZWO Seestar controller", "Science-grade acquisition ·
    ASCOM Alpaca · FITS", "GNU GPL v3 · linked against PyQt6 (GPL v3)").

### 1.10 Support bundle flow (`_create_support_bundle`, shell.py:478; opened by More > Create local support bundle…)

Sequence of modal steps:

| # | Step / control | Qt type | Exact text | Default | Action -> effect |
|---|---|---|---|---|---|
| 1 | Yes | QMessageBox.question shell.py:481 | title "Include session metadata?", text "Include one session's JSON, JSONL and CSV files? Raw FITS, site coordinates and network addresses are excluded. The ZIP stays on this computer until you choose to share it." | **Yes** (shell.py:488) | go to step 3 |
| 2 | No | same | | | skip to step 5 |
| 3 | Choose | QFileDialog.getExistingDirectory shell.py:494 | "Choose an Argos session", starts at `sessions_path` | | `session_dir` |
| 4 | Cancel | same | | | **aborts the whole bundle** (shell.py:497-498) |
| 5 | Save | QFileDialog.getSaveFileName shell.py:503 | "Save local support bundle", default `~/Desktop/argos-support-0.4.2.zip` (home if no Desktop), filter "ZIP archive (*.zip)" | | `create_support_bundle` (below) |
| 6 | Cancel | same | | | abort |
| 7 | OK | QMessageBox.warning shell.py:526 | title "Support bundle", "Could not create the ZIP:\n<OSError>" | | — |
| 8 | OK | QMessageBox.information shell.py:528 | title "Local support bundle created", "Created <name> with <n> file(s).\n\nArgos did not upload it. Review the ZIP before sharing it." | | — |

- Real effect (`create_support_bundle`, support_bundle.py:162-221): forces `.zip`; writes
  `README.txt`, `manifest.json` (format 1, version, UTC time, platform, privacy flags, config
  summary: `hardware.profile`, `ui.log_level`, `diagnostics.enabled`, ASTAP configured: shell.py:511-516),
  every `argos.log*` of the diagnostics folder up to 10 MB each with IPv4 and home path redacted
  (support_bundle.py:150-156, 200-210); optional session `.csv/.json/.jsonl` files (10 MB each,
  50 MB total, no symlinks, private keys such as `ra`, `dec`, `site`, `observer`, `host` replaced by
  `<redacted>`: support_bundle.py:41-53, 224-302). Nothing is uploaded.
- Problems found:
  - P35 Cancelling the session chooser cancels the whole bundle instead of continuing without a
    session (shell.py:497-498); the privacy question defaults to Yes (shell.py:488); the chosen folder
    is not checked to be an Argos session; the fixed file name triggers an overwrite prompt on the
    second bundle of the same version.

### 1.11 Theme, palette and typography behaviour (theme.py, palettes.py, design.py; controls in Settings > Files · application > Appearance, configuration_page.py:716-764)

The Settings spec owns these controls; they are listed because the shell spec owns the switching
behaviour.

| # | Control | Qt type | Label | Options / default | Action -> effect | Persisted |
|---|---|---|---|---|---|---|
| 1 | Color preset | QComboBox configuration_page.py:726 | "Color preset" | "Observatory" (default), "Charcoal", "Night (Red)" (palettes.py:73-162) | `_save_palette` configuration_page.py:1233: `theme.apply_palette`, regenerated global QSS applied live, config saved, warning notice "Restart to fully apply — global colors update live, but some widgets (sidebar, status bar) take effect on next launch." (configuration_page.py:752-760) | `ui.theme.preset` |
| 2 | Log level | QComboBox configuration_page.py:740 | "Log level" | DEBUG, INFO (default), WARNING, ERROR | `_save_log_level` configuration_page.py:1265; takes effect only at next launch (main.py:144), not said in the UI | `ui.log_level` |
| 3 | Language | QComboBox configuration_page.py:733 | "Language" + note "Language change applies after restart." | English (`en`), Français (`fr`) | `_save_language` configuration_page.py:1259 | `ui.language`, never read anywhere (dead) |

- Runtime behaviour: `apply_palette` rebinds module constants and `LOG_COLORS` (theme.py:46-106).
  Widgets that baked a colour into their own stylesheet at construction keep the old palette until
  restart: sidebar icons and labels (sidebar.py:83-111, 217-229), status strip (statusbar.py:47-131),
  dock title QSS (dock_host.py:27-45), splash (fixed colours).
- Typography: fixed pixel sizes (design.py:71-77: body 13, label 12, metric 17, heading 22,
  section 14, small 12, tiny 11), system font stacks (palettes.py:91-92). There is **no font
  scaling** control.
- Layout primitives with behaviour worth keeping: spacing scale 4 / 6 / 8 / 12 / 18 (design.py:50-54),
  card padding 12 / 14 / 12 / 10 (design.py:57), form pages capped at 880 px (design.py:81,
  127-154), right rail 420-580 px (design.py:67-68), `SliderSpin` slider + value box with an
  optional logarithmic slider (design.py:179-304), `stat_color` three-band thresholds for HFD, drift,
  SNR (design.py:431-447).
- Problems found: P36 live switch is partial (above); P37 log level change silently needs a restart;
  P38 language selector is dead.

### 1.12 Implicit window status bar (E12, `QMainWindow.statusBar()`, shell.py:457, 605)

- `statusBar()` creates an empty bottom `QStatusBar` the first time it is called; from then on the
  window carries a second, mostly empty, status bar for the rest of the session. Messages: see 1.4.

### 1.13 Cross-page wiring owned by the Shell (shell.py:166-179, 303-361, 367-411)

| Behaviour | Code | User-visible effect |
|---|---|---|
| One observation object | shell.py:166-179 | Camera dock object name <-> Plan object name; a Plan change re-keys the engine target set and **clears the live light curves** (acquisition_engine.py:1010-1022). |
| Target hand-over | shell.py:172-174 | Observe target coordinates -> Plan; Plan resolved target / science source -> Observe. |
| Connection intents | shell.py:320-326 | Connection page discover / connect / disconnect (per device and all) -> `DeviceSession`; telescope profile kept in sync between Connection and Settings (shell.py:355-358). |
| Stellarium GoTo | shell.py:330-353 | A GoTo from Stellarium (any time, any page) flashes the Stellarium card, **slews the mount immediately** (`goto_target`, imaging_page.py:2775) and proposes a target name (online lookup only if `stellarium.online_target_lookup`). Errors: card shows "✗  error", the message goes to the log (device_session.py:814-816, shell.py:360-361). |
| Device state fan-out | shell.py:367-372 | Status strip + Connection page + rail dots. |
| Sequence / live / autofocus | shell.py:312-317, 374-384 | Capture strip and rail dots. |

### 1.14 Shutdown sequence (`Shell.closeEvent`, shell.py:611; File > Quit, close box, Cmd+Q)

| Order | Call | Waits up to |
|---|---|---|
| 1 | `ConfigurationPage.shutdown` (geocoding worker) configuration_page.py:995 | 9 s |
| 2 | `SequencerPage.shutdown` (resolver 9 s, exoplanet 13 s) sequencer_page.py:291-297 | 22 s |
| 3 | `ImagingPage.shutdown`: close Frame Viewers and Field photometry, cancel batch (3 s), resolver (9 s), point identity (38 s), `engine.shutdown` (stops **sequence**, preview, autofocus; 5 s shared budget, acquisition_engine.py:1607-1650), preview processor (2 s) imaging_page.py:2854-2878 | about 57 s |
| 4 | `DeviceSession.shutdown`: retry timer, Stellarium server, pollers, temperature polls, discovery (2 s) device_session.py:822-831 | 2 s |
| 5 | `NetworkMonitor.stop` + `wait(6000)` shell.py:618-621 | 6 s |
| 6 | `_save_state` (geometry, state, three page layouts) + `config.save` shell.py:622-623 | — |

- Problems found:
  - P39 No quit confirmation, even while a sequence, an exposure or a slew is running: the sequence
    is stopped silently (acquisition_engine.py:1621-1622).
  - P40 The UI thread blocks during shutdown with no feedback; the sum of the waits is about 96 s
    in the worst case (typical: under a second; worst case is a sum of timeouts, not measured).
  - P41 Devices are not disconnected at quit, only their pollers stop (device_session.py:822-831);
    impact on the Seestar not verified.

## 2. Web redesign

### 2.1 Placement in the new information architecture

| Qt element | Section | Screen / region | Decision and justification |
|---|---|---|---|
| E1 start-up + E2 splash | all | **Start-up screen** inside the window (full window, tokens) | Tauri shows the window at once; the screen covers server spawn and first link. In-window and themed, so Night Red never flashes gold or white, and a failure stays on screen (P1, P3). |
| E3 main window | all | Tauri window: `NavRail` 92 px + section + `StatusBar` 32 px (existing `App.svelte`) | Same mental model; no menu bar inside the window (space, BRAND 11.1). |
| E4 File > Open FITS image… | Observe | section toolbar, icon `open-image` + global Cmd/Ctrl+O | Opens into the viewer, as in Qt; global shortcut switches to Observe first. |
| E4 File > Open session photometry… | Review | Review toolbar `open-session` + global Cmd/Ctrl+Shift+O | Merged with Review's "Open session…" (P13): one operation that loads a session into Review. Review spec owns the details. |
| E4 File > Quit | all | Help popover (Tauri only) + native app menu Cmd/Ctrl+Q | Quit is rare and destructive: icon + label, behind a confirmation when busy. Browser mode has no Quit. |
| E4 More > Documentation, Support bundle, About | all | **Help popover** from a `help` button in the rail footer | Rare resources; one place, always reachable, takes no toolbar room. |
| E4 View > sections | all | `NavRail` entries + F1-F5 (exists) | Same. |
| E4 View > Reset Window Layout | each section | "Reset layout" in each section's Panels popover + "Reset all layouts" in Settings > Appearance | Live reset, per section (fixes P9). |
| E4 Field menu (4 items) | Observe / Settings | Observe toolbar `plate-solve`, toggle `plate-solve-auto`; settings in Settings > Astrometry and Settings > Catalogues (deep links from the Observe solve and overlay popovers) | Point of use; the Observe spec owns the controls. |
| E4 Photometry menu (3 items) | Observe / Review | Photometry card + light-curve drawer tab on Observe; "Re-run subs…" on the Review toolbar | No floating windows; Observe and Review specs own them. |
| E5 rail | all | `NavRail` (exists) + footer `help` and `theme` buttons | Footer space is otherwise empty. |
| E6 status strip | all | **Global segments of the bottom `StatusBar`**, merged with the existing per-section readouts | One status row instead of two (Qt had a top strip, the web has a bottom bar). |
| E7 Activity log | all | Bottom **drawer**, opened from the status bar "Log" button or `L`, in every section | Feedback must be visible from any section (P14, P31). |
| E8 dock mechanism | Observe, Plan, Review | **Panel host convention**: right-rail cards (fold), bottom drawer tabs, a `panels` popover with show / hide + Reset layout | Single webview window: no floating, no drag-rearrange in v1 (see dropped). |
| E9 About | all | modal dialog from the Help popover | Rare. |
| E10 support bundle | all | modal dialog from the Help popover | One dialog instead of four modal steps. |
| E11 theme | Settings | Settings > Appearance (segmented control) + rail footer quick toggle `theme` | Night Red must be one click away at the telescope; switch is live everywhere (fixes P36). |
| E12 window status messages | all | toasts (exists) + log line | Already the web pattern. |
| E13 rail context menu | — | dropped | P6. |
| E14 shutdown | all | Quit confirmation dialog + shutdown progress overlay | Fixes P39, P40. |

### 2.2 Control mapping

| Qt ref | Web control | Decision | Icon id | Display | Shortcut |
|---|---|---|---|---|---|
| 1.3 #1 close box | Tauri window close | keep; same path as Quit (confirmation when busy) | — | — | platform |
| 1.3 #2 move / resize | Tauri window | keep; persisted by the Tauri window-state plugin | — | — | — |
| 1.3 #3 "Modes" context menu | — | **drop**: hides the rail with no way back (P6); the rail is always visible | — | — | — |
| 1.4 #1 Open FITS image… | Observe toolbar button "Open FITS image" | move | `open-image` | icon | Cmd/Ctrl+O (qt), global |
| 1.4 #2 Open session photometry… | Review toolbar "Open session" | merge with Review "Open session…" (P13) | `open-session` | icon | Cmd/Ctrl+Shift+O (qt), global |
| 1.4 #3 Quit Argos | Help popover "Quit ARGOS" (Tauri only) + native app menu | keep (desktop only) | `quit` | icon+label | Cmd/Ctrl+Q (qt) |
| 1.4 #4 Documentation & website | Help popover item, opens the default browser | keep; target URL is an open question (P12) | `help` | icon+label (menu item) | — |
| 1.4 #5 Create local support bundle… | Help popover item -> dialog 2.3.6 | keep | `support-bundle` | icon+label | — |
| 1.4 #6 About & credits | Help popover item -> dialog 2.3.5 | keep | `about` | icon+label | — |
| 1.4 #7-11 View sections | `NavRail` entries | keep (exists) | `nav-connection`, `nav-imaging`, `nav-sequencer`, `nav-analyze`, `nav-configuration` | icon+label | F1-F5 (qt) |
| 1.4 #12 Reset Window Layout | "Reset layout" in each Panels popover; "Reset all layouts" in Settings > Appearance | move + fix semantics (live, all keys) | `layout-reset` | icon+label | — |
| 1.4 #13 Identify field | Observe toolbar | move (Observe spec) | `plate-solve` | icon | S (proposed in inventory) |
| 1.4 #14 Keep field identified automatically | Observe toolbar toggle, `aria-pressed`, state from server (armed by a sequence) | move (Observe spec) | `plate-solve-auto` | icon | — |
| 1.4 #15 Configure field identification… | Settings > Astrometry; link from the Observe solve popover | move; single home for ASTAP settings (P17) | `settings` | label (link) | — |
| 1.4 #16 Configure catalogues… | Settings > Catalogues; link from the Observe overlay popover | move | `catalogue` | label (link) | — |
| 1.4 #17 Photometry setup… | Observe Photometry card / panel | move (Observe spec) | `photometry` | icon | — |
| 1.4 #18 Live curves & diagnostics… | Observe drawer tab "Light curve" | move (Observe spec) | `light-curve` | icon | — |
| 1.4 #19 Re-run subs… | Review toolbar | move (Review spec) | `rerun-photometry` | icon+label | — |
| 1.5 #1-5 rail entries | `NavRail` | keep; dot rules revised (2.4.4) | `nav-*` | icon+label | F1-F5; Tab + Enter / Space |
| 1.6 #1-4 device badges | status bar device cluster, one icon + state mark each; click opens Connection for any state but `connected` | keep + fix P23, P24 | `mount`, `camera`, `filter-wheel`, `focuser` | icon (name and state in tooltip and `aria-label`) | — |
| 1.6 #5 capture strip | status bar **run chip** (sequence / live / autofocus); click opens Plan for a sequence, Observe for live / autofocus | keep | `nav-sequencer` (sequence), `live`, `autofocus` | icon+label | — |
| 1.6 network readout | status bar "Seestar / Net" marks | keep; three states (P22) | `network` | icon+label | — |
| 1.6 mount geometry | status bar chip "Alt-Az" / "EQ" | keep | — | label | — |
| 1.6 tracking readout | status bar "Tracking ON / OFF / —" | keep (display only; the toggle stays on the Mount card) | `tracking` | icon+label | — |
| 1.6 last action | status bar activity text, truncated, full text in tooltip, each change also logged | keep (P25) | — | label | — |
| 1.7 #1 Clear | drawer header button | keep (exists) | `clear` | icon | — |
| 1.7 #2 log text | drawer list, selectable; + Copy visible lines, Save as text, level filter, search | keep + extend | `copy`, `save`, `search` | icon | `L` toggles the drawer (proposed) |
| 1.8 #1 title drag | — | **drop**: fixed regions (rail cards, drawer tabs); predictable at 1440 x 900, trivial reset | — | — | — |
| 1.8 #2 float button | — | **drop for v1**: one webview window; detaching to a second monitor is an open question (Tauri multi-window) | (`panel-float` reserved) | — | — |
| 1.8 #3 close button | Panels popover checkbox; card header fold | merge into the popover | `panels` | icon | — |
| 1.8 #4 title double-click float | — | **drop** (same reason as #2) | — | — | — |
| 1.8 #5 panel chips | Panels popover checkboxes | merge (space: one icon instead of a chip row) | `panels` | icon | — |
| 1.8 #6 dock-list context menu | Panels popover | merge | `panels` | icon | — |
| 1.9 #1 About: Documentation & website | link button in the About dialog | keep | `help` | label | — |
| 1.9 #2 About: Close | "Close" | keep | — | label | Esc |
| 1.10 #1-2 Include session? Yes / No | checkbox "Include one session's metadata" in the dialog, **off** by default | merge (privacy-first default, open question) | — | label | — |
| 1.10 #3-4 session folder chooser | session select fed by `GET /api/sessions` | replace (no OS picker; Night Red safe) | — | label | — |
| 1.10 #5-6 save dialog | "Save to" path field + browse | keep (in-app picker or Tauri dialog) | `browse` | icon | — |
| 1.10 #7 failure box | inline error in the dialog | replace | — | label | — |
| 1.10 #8 success box | toast "Support bundle created" with "Reveal" (Tauri) | replace | — | label | — |
| 1.11 #1 Color preset | Settings > Appearance segmented "Observatory / Charcoal / Night Red", live; rail footer quick toggle | keep + quick access | `theme` | icon (rail) / label (Settings) | open question |
| 1.11 #2 Log level | Settings (Settings spec), with "applies on next server start" note if still true | keep | — | label | — |
| 1.11 #3 Language | — | **drop until translations exist** (dead control, P38) | — | — | — |

### 2.3 Wireframes (1440 x 900)

Icon ids in brackets; `*` filled mark (connected), `o` ring (disconnected), `(` half (busy), `x`
(error). The real marks are drawn in CSS/SVG, never as Unicode characters.

#### 2.3.1 Global frame

```
0        92                                                                                    1440
+--------+-------------------------------------------------------------------------------------+ 0
|(o)ARGOS| section toolbar (47 px, as on Observe)                         ... [panels]          |
+--------+-------------------------------------------------------------------------------------+ 47
|[nav-   |                                                                                     |
| conn.] |                                                                                     |
|Connect.|                          section content                                            |
|[nav-   |              (Observe: viewer + right rail, as built today)                         |
|imaging]|                                                                                     |
|Observe*|                                                                                     |
|[nav-   |                                                                                     |
|seq.]   |                                                                                     |
|Plan  * |                                                                                     |
|[nav-   +-------------------------------------------------------------------------------------+
|analyze]| bottom drawer (optional, any section): tabs [Light curve][HFD] ... [Activity log]   |
|Review  |                                                                                     |
|        |                                                                                     |
|[help][theme]                                                                                 |
|[nav-cfg]                                                                                     |
|Settings|                                                                                     |
+--------+-------------------------------------------------------------------------------------+ 868
| [mount]* [camera]( [filter-wheel]o [focuser]o | <run chip> | <section readouts> .... | [network] Seestar * Net o | Alt-Az | [tracking] ON | Exposing 10.0 s... | [log] Log 2 |
+----------------------------------------------------------------------------------------------+ 900
```

#### 2.3.2 Status bar states (32 px, one row, nothing reserved when empty)

```
Idle, not connected:
| [mount]o [camera]o [filter-wheel]o [focuser]o | X — Y — Value —  Frame —  Zoom — ...... | [network] Seestar o  Net * | Tracking — | Idle | [log] Log |

Live view:
| [mount]* [camera]( [fw]* [foc]* | [live] LIVE  HFD 2.1 px | X 512 Y 960 Value 2 014 ADU  Frame #128 ... | Seestar * Net * | Alt-Az | [tracking] ON | Live preview | [log] Log |

Sequence running (from any section):
| [mount]* [camera]( [fw]* [foc]* | [nav-sequencer] REC  SS Cyg  34/120  ETA 12m 34s  HFD 2.1 px | <section> ... | Seestar * Net * | Alt-Az | [tracking] ON | Sequence running | [log] Log 1 |

Server link lost (web only):
| [network] Server link lost, reconnecting...  (last state kept, greyed) .............................. | [log] Log |
```

Priority when narrow (1280 px): the last-action text shrinks first (ellipsis), then the section
readouts drop Rate / Latency into a tooltip, then the network labels become marks only. Device
cluster, run chip, tracking and Log never hide.

#### 2.3.3 Rail footer and Help popover

```
                 +--------------------------------------------+
                 | ARGOS 0.4.2  ·  server 0.4.2  ·  API 1     |  (mono, text-muted)
                 +--------------------------------------------+
                 | [help]  Documentation & website          > |  (external)
                 |         Keyboard shortcuts               ? |
                 | [support-bundle] Create support bundle...  |
                 | [about] About & credits                    |
                 +--------------------------------------------+
                 | [quit]  Quit ARGOS               Cmd+Q     |  (desktop app only)
                 +--------------------------------------------+
  [help] [theme]   <- 2 x 32 px icon buttons above the Settings entry
  [nav-configuration]
     Settings
```

#### 2.3.4 Theme quick toggle

Click cycles Observatory > Charcoal > Night Red (as `nextTheme`, web/src/lib/app/theme.ts:27);
tooltip "Theme: Night Red. Click for Observatory". Settings > Appearance has the explicit
three-way segmented control and "Reset all layouts".

#### 2.3.5 About dialog (modal, 480 px)

```
+-------------------------- About ARGOS ------------------------ [x] +
|                     (ARGOS mark, 96 px, --accent)                   |
|                               ARGOS                                 |
|            Version 0.4.2  ·  server 0.4.2  ·  API 1  (mono)         |
|  Scientific acquisition and differential photometry for ZWO        |
|  Seestar telescopes.                                               |
|  CREDITS                                                           |
|  Created and maintained by Jules Perret.                           |
|  Built with Python, NumPy, Astropy, FastAPI, Svelte, uPlot and     |
|  ASCOM Alpaca. IBM Plex fonts under the SIL Open Font Licence 1.1. |
|  Copyright (c) 2026 ARGOS contributors · GNU GPL v3 or later.      |
|  [Copy version info]   [Documentation & website]          [Close]  |
+--------------------------------------------------------------------+
```

The mark comes from `brand/argos-mark.svg` (generator output, `currentColor`), never a PNG. Credits
wording for the web build is an open question.

#### 2.3.6 Support bundle dialog (modal, 560 px)

```
+-------------------- Create a local support bundle ------------------ [x] +
| A ZIP of redacted ARGOS logs for a bug report. It contains no raw FITS,  |
| site coordinates or network addresses. ARGOS never uploads it.          |
|                                                                          |
| [ ] Include one session's metadata (JSON, JSONL, CSV)                    |
|     Session [ 2026-10-31  SS Cyg  412 frames                       v ]   |
|                                                                          |
| Save to [ ~/Desktop/argos-support-0.4.2-20261101T213405Z.zip  ] [browse] |
|                                                                          |
| (x) Could not create the ZIP: Permission denied: '/Volumes/…'            |
|                                          [Cancel]  [Create bundle]       |
+--------------------------------------------------------------------------+
```

Busy: "Create bundle" shows the spinner, the dialog stays open. Success closes it and shows a toast
"Support bundle created: argos-support-….zip, 14 files. ARGOS did not upload it." with a "Reveal"
action (desktop app only).

#### 2.3.7 Quit confirmation and shutdown (desktop app)

```
+------------------------- Quit ARGOS? -------------------------+
| A sequence is running: SS Cyg, 34 of 120 frames.               |
| Quitting stops the sequence and the camera, closes the         |
| equipment connections and shuts down the ARGOS server.         |
|                                      [Cancel]  [Quit ARGOS]    |
+----------------------------------------------------------------+
then, full-window scrim:
            Shutting down ARGOS...   stopping the sequence (2 s)
```

Shown only when something is running (sequence, exposure, live, autofocus, slew, solve, batch
re-run). Idle: quit at once.

#### 2.3.8 Start-up screen and start-up failure

```
+-------------------------------- full window, --bg ---------------------------------+
|                                                                                     |
|                          (ARGOS mark 96 px, --accent)                               |
|                                   ARGOS                                             |
|                               Version 0.4.2                                         |
|                  [==================-----------------------]                        |
|                         Starting the ARGOS server...                                |
|                                                                                     |
|     GNU GPL v3 or later · free software with no warranty · Developed by Jules Perret|
+-------------------------------------------------------------------------------------+

Failure (stays until the user acts):
|  ARGOS could not start                                                              |
|  The ARGOS server stopped during start-up.                                          |
|  +-- mono, --bg-2 ---------------------------------------------------------------+  |
|  | ModuleNotFoundError: No module named 'astropy'                                |  |
|  +-------------------------------------------------------------------------------+  |
|  Log folder: ~/Library/Logs/Argos                                                   |
|  [Copy details]  [Open log folder]                                     [Retry]      |
```

Stages (honest, each marked when it completes): "Starting the ARGOS server…" (until the sidecar
prints `ARGOS_PORT` / `ARGOS_TOKEN`), "Connecting…" (until `/api/health` answers and
`/ws/events` sends its first `status`), then the screen fades out (`--duration-base`, 0 with
reduced motion). Browser mode skips the first stage.

#### 2.3.9 Activity log drawer (global, under the section content, default 200 px, resizable)

```
+-----------------------------------------------------------------------------------------------+
| [log] Activity log  1 204 lines · UTC   [All | Warnings | Errors]  [search][______]  [copy][save][clear][close] |
| 21:34:05  CMD    Plate-solving current frame... (hint RA 5.588h Dec -5.39°)                   |
| 21:34:09  OK     Field identified: 3.67″/px                                                    |
| 21:34:12  WARN   Center target: plate-solve the current frame first.                          |
| 21:35:00  ERROR  Solve: ASTAP executable not found                                             |
+===== drag handle ===============================================================================+
```

Levels shown: CMD, INFO, OK, WARN, ERROR (tokens `--log-cmd`, `--log-info`, `--log-ok`,
`--log-warning`, `--log-error` already exist in tokens.css:188-193). In sections with their own
drawer tabs (Observe: light curve, focus diagnostics) the log is the last tab of the same drawer.

#### 2.3.10 Panels popover (shared panel host, right end of each section toolbar)

```
                                   +-- Panels -------------------------+
                                   | RIGHT RAIL                        |
                                   | [x] Camera                        |
                                   | [x] Display stretch               |
                                   | [x] Mount                         |
                                   | [ ] Focuser                       |
                                   | BOTTOM DRAWER                     |
                                   | [ ] Light curve                   |
                                   | [ ] Focus diagnostics             |
                                   | [x] Activity log                  |
                                   +-----------------------------------+
                                   | [layout-reset] Reset layout       |
                                   +-----------------------------------+
```

Panel names are examples; each section spec fills its own list.

#### 2.3.11 Keyboard shortcuts sheet (modal, opened by `?` or the Help popover)

```
+--------------------------- Keyboard shortcuts ------------------------- [x] +
| GLOBAL                               OBSERVE                                 |
| F1 ... F5   Sections                 E        One exposure                   |
| Cmd O       Open FITS image          V        Live view on / off             |
| Cmd Shift O Open session (Review)    Esc      Abort a slew                   |
| L           Activity log             + / -    Zoom in / out                  |
| ?           This sheet               F, 1     Fit, actual pixels             |
| Cmd Q       Quit (desktop app)       A, Shift A, H, X, P ...                 |
+------------------------------------------------------------------------------+
```

Generated from one shortcut registry so tooltips, `aria-keyshortcuts` and the sheet never
disagree.

#### 2.3.12 Shared dialog patterns (replace every QMessageBox and QFileDialog, Appendix A)

```
Confirm (replaces QMessageBox.question):     In-app file picker (replaces QFileDialog):
+---- Park the mount? ------------- [x] +     +---- Open FITS image -------------------------- [x] +
| Parking physically closes the        |     | [<][>]  ~/Argos/sessions/2026-10-31/lights  [refresh]|
| Seestar arm and stops tracking.      |     | Places          | Name             Size   Modified |
|               [Cancel]  [Park]       |     | Sessions        | ..                                |
+--------------------------------------+     | Home            | SS_Cyg_0001.fits 4.0 MB 21:04    |
 (destructive button: danger outline,         | Desktop         | SS_Cyg_0002.fits 4.0 MB 21:04    |
  default focus on Cancel)                    | Path [ ~/Argos/sessions/.../SS_Cyg_0002.fits      ] |
                                              | Type [ FITS (.fits .fit .fts) ]  [Cancel]  [Open]  |
                                              +----------------------------------------------------+
```

### 2.4 Interaction and states

#### 2.4.1 Lifecycle

| Moment | Qt today | Web / Tauri |
|---|---|---|
| Launch | splash with 6 stages | start-up screen (2.3.8), themed before first paint (theme applied by web/index.html:14-16 before first paint) |
| Start-up failure | splash closes, nothing visible (P1) | failure screen with message, log folder, Copy details, Retry |
| First run | defaults written, lands on Connection | same landing; Connection shows a one-line checklist "Observer code, site, ASTAP" linking to Settings (open question) |
| Section restore | last mode except Observe, which becomes Connection (shell.py:93-96) | same rule, stored per viewer (`argos.section`); Observe is restored when a device is connected or a frame is shown |
| Crash last time | crash file written silently | toast on next start "ARGOS stopped unexpectedly last time. A crash report was saved." with "Create support bundle" (needs `GET /api/diagnostics/crash-reports`) |
| Quit | immediate, silent stop of any run, UI frozen up to ~96 s (P39, P40) | confirmation when busy (2.3.7), progress scrim with the current stage, then the window closes |
| UI closed, server alive (browser mode) | n/a | closing a browser tab never stops the server; reopening reconnects and replays state (open question: should the desktop app keep the server running headless?) |

#### 2.4.2 Empty, loading, busy, error

| Element | Empty | Loading / busy | Error |
|---|---|---|---|
| Device badge | ring mark, tooltip "Mount: not connected" | half mark "connecting" | x mark, tooltip with the full error, click opens Connection |
| Run chip | absent (no reserved space) | n/a | sequence error: danger mark "Sequence stopped: <reason>", click opens Plan |
| Network | "Seestar —" when no host is configured | marks muted until the first check | ring = unreachable |
| Activity log | "No messages yet. Server events, warnings and failed commands appear here." (exists) | — | errors also raise a toast (exists) |
| Help popover items | — | support bundle button busy while creating | inline error in the dialog |
| Server link | — | "Connecting…" in the status bar connection item | "Server link lost, reconnecting…"; "Token rejected" when `unauthorized` |

#### 2.4.3 Confirmations

Text-only buttons (BRAND 7), destructive button outlined in `--danger`, initial focus on Cancel:
Quit while busy (new), Park (exists in Qt, Mount card), clear a catalogue cache (Settings),
Reset all layouts: no confirmation (reversible preference), a toast "Layouts restored".

#### 2.4.4 Rail state dots (revised)

| Entry | ready (`--success`) | active (`--accent`) | needs attention (`--warning`) |
|---|---|---|---|
| Connection | mount and camera connected | discovering / connecting | a device in error, or the server link lost / token rejected |
| Observe | camera connected | live view, exposure, autofocus or slew | — (not connected is the normal start: no amber, fixes P18) |
| Plan | — | sequence running | sequence stopped on an error |
| Review | — | batch re-run running | — |
| Settings | — | — | open question: observer code or site missing |

The state word is part of the entry's `aria-label` (exists in `NavRail.svelte`).

#### 2.4.5 Keyboard

| Key | Action | Origin |
|---|---|---|
| F1 ... F5 | sections, also from text fields | qt (exists in web) |
| Cmd/Ctrl+O | Open FITS image (switches to Observe) | qt |
| Cmd/Ctrl+Shift+O | Open session (switches to Review) | qt |
| Cmd/Ctrl+Q | Quit (desktop app only) | qt |
| Cmd/Ctrl+, | Settings | proposed (macOS convention) |
| L | Activity log drawer | proposed (free in the inventory) |
| ? | Keyboard shortcuts sheet | proposed |
| Esc | close popover / dialog first; on Observe with nothing open, abort a slew (exists) | qt dialogs + web |
| Tab, Enter, Space | rail entries and every control | qt |

`matchesShortcut` rejects any Ctrl / Meta modifier today (web/src/lib/app/shortcuts.ts:64); the
Cmd/Ctrl shortcuts need a modifier-aware matcher. On macOS F1-F5 need Fn; an alternative binding
is an open question.

#### 2.4.6 Night Red specifics

- Start-up screen, About and Help use tokens only; the mark is `currentColor` SVG (fixes P3, P33).
- No OS dialog in Night Red: confirmations, alerts and file choice are in-app components (2.3.12),
  because native `QFileDialog` / Tauri dialogs and message boxes draw grey and white (BRAND 4.3).
- State is double-coded: device marks differ by shape (filled, ring, half, x) and the tooltip
  names the state; the run chip carries its icon and the word REC / LIVE / AF.
- No Unicode pictographs (P27); no OS notifications; toasts are the only pop-ups.
- Open: OS window title bar and system cursors are not red (Tauri `decorations: false` with a
  token-drawn drag strip would fix the title bar).

#### 2.4.7 Persistence (per viewer, `localStorage`, every access wrapped as in `prefs.ts`)

| Preference | Qt key | Web key |
|---|---|---|
| Last section | `ui.shell.mode` | `argos.section` |
| Window size / position | `ui.shell.geometry` | Tauri window-state plugin |
| Rail visibility | `ui.shell.state` | none (rail always visible) |
| Observe / Plan / Review layout | `ui.imaging.layout`, `ui.sequencer.layout`, `ui.review.layout` | `argos.layout.<section>.<panel>` (visible, folded), `argos.drawer.<section>` (tab, height) |
| Right rail open | dock visibility | `argos.rail-open` (exists) |
| Theme | `ui.theme.preset` (config) | `argos.theme` (exists); first launch could adopt `ui.theme.preset` (open question) |
| Log drawer | dock visibility | `argos.log.open`, `argos.log.height`, `argos.log.filter` |
| Log level | `ui.log_level` (config, server side) | Settings API (Settings spec) |

"Reset layout" clears `argos.layout.<section>.*` and `argos.drawer.<section>` live; "Reset all
layouts" clears every `argos.layout.*`, `argos.drawer.*`, `argos.rail-open` and the Tauri window
state, keeping theme and rotation.

#### 2.4.8 Always visible without scrolling (1440 x 900 and 1280 x 800)

Rail entries and footer, the whole status bar (device cluster, run chip, tracking, Log), toasts.
The drawer never covers the image: it shrinks the section (as `LogDrawer` does today).

### 2.5 API needs beyond v1

| Name | Kind | Payload sketch | Core / worker code it wraps | Notes |
|---|---|---|---|---|
| App info | HTTP `GET /api/app/info` | `{"version","api","python","platform","paths":{"config","sessions","diagnostics","log_file"},"hardware_profile","log_level","diagnostics_enabled","astap_configured"}` | argos/__init__.py:9; config.py:16-17, 268-270; support_bundle.py:56-64; shell.py:511-516 | Instant. Feeds About, Help header, failure screen, support bundle. |
| Support bundle | HTTP `POST /api/support-bundle` | body `{"destination": "<abs .zip>", "session_dir": "<abs>" or null}` -> `{"path","files":[…]}`; errors `invalid_argument`, `bundle_failed` | support_bundle.py:162-221 (`create_support_bundle`), shell.py:478-533 | Seconds (up to 50 MB of session text). Not cancellable. Browser mode alternative: `GET /api/support-bundle.zip?session=<id>` streamed download. Qt-free already. |
| Session list | HTTP `GET /api/sessions` | `[{"id","path","object","started_utc","frames","has_photometry"}]` | config.py:268 (`sessions_path`), session/review.py:102 (`load_session`) | Shared with the Review spec. Scan can be slow on large trees: paginate. |
| Network reachability | WS `/ws/events` `{"type":"network","seestar":true\|false\|null,"internet":bool,"t"}` | as left | network_monitor.py:40-84 | Every 10 s and on change. `NetworkMonitor` is a `QThread`: needs a Qt-free port (the server forbids Qt, tests/server/test_no_qt.py). Open question on the 1.1.1.1 / 8.8.8.8 probes. |
| Per-device state | `status` / new `devices` record | `"devices":{"mount"\|"camera"\|"filterwheel"\|"focuser":{"state":"disconnected\|connecting\|connected\|busy\|error","info":string,"error":string\|null}}` | device_session.py:292-698, acquisition_engine.py:366, 375 | v1 has one `ConnectionState` for mount + camera only. Full error text (not cut to 48). Shared with the Connection spec. |
| Mount geometry | field in `MountState` | `"alignment":"Alt-Az"\|"EQ"\|"EQ (GEM)"\|null` | device_session.py:110, 293, 332 (`scope.alignment_mode`) | Static per connection. |
| Activity line | WS `{"type":"activity","text","source","t"}` | as left | device_session.py:238-463; astrometry_controller.py:85-216; exposure_worker.py:114-149; imaging_page.py:126-132, 633, 2848 | Also written to the log. |
| Run summary | WS `{"type":"run","kind":"sequence"\|"live"\|"autofocus"\|null,"object","done","total","eta_s","hfd_px","error"}` | as left | acquisition_engine.py:93-95 (`sequence_running`, `sequence_progress`), `hfd_updated` (imaging_page.py:149), `autofocus_state` (imaging_page.py:145) | Plan and Observe specs own the details; the shell only needs this summary. |
| Busy summary | field in `status` | `"activity":{"sequence","exposure","live","autofocus","slewing","solving","batch":bool}` | camera_service.py (`CameraState`), astrometry_controller.py:79 (`is_busy`), imaging_page.py:2248 (batch worker) | Drives the quit confirmation and the rail dots. |
| Graceful shutdown | HTTP `POST /api/app/shutdown` + WS `{"type":"shutdown","stage","t"}` | `{"force":false}` -> 202 | order of shell.py:611-625; acquisition_engine.py:1607-1650; device_session.py:822-831; hub.py:278 (`shutdown`) | Long-running (bounded budget, progress stages). Tauri may also send SIGTERM, already graceful (protocol.md "Launching"). |
| Log stream v2 | WS `log` extended + HTTP `GET /api/logs?after=<id>&limit=<n>` | `{"type":"log","id":int,"level":"debug"\|"cmd"\|"info"\|"ok"\|"warning"\|"error","source":"mount"\|"camera"\|"solve"\|"sequence"\|…,"message","t"}` | the 148 `log_message.emit` sites (levels CMD, INFO, OK, WARN, ERROR); hub.py:156-163 | v1 has only info / warning / error and no history: a reconnecting client loses the night's log. Ring buffer of a few thousand lines. |
| Server logging and crash reports | server start-up + HTTP `GET /api/diagnostics/crash-reports?since=` | `[{"name","created_utc"}]` | support_bundle.py:67-101 (`configure_local_logging`), 104-147 (`install_crash_reporter`) | The server logs to stderr only (server/__main__.py:99): a bundle built today would hold no server log. Honour `ui.log_level`. |
| File browsing | HTTP `GET /api/fs/list?path=&kind=file\|dir&ext=` | `{"path","parent","entries":[{"name","kind","size","mtime"}]}` | replaces the 18 `QFileDialog` sites (Appendix A.2) | Read-only, limited to the user's home and the configured data paths. Needed for the in-app picker (Night Red, browser mode). Optional `POST /api/fs/reveal {"path"}` if Tauri's opener is not used. |
| Stellarium GoTo notice | WS `{"type":"stellarium_goto","ra_hours","dec_deg","t"}` | as left | shell.py:346-353, device_session.py:128 | Toast "Stellarium GoTo: RA … Dec …" because it slews from any section. Connection spec owns the server controls. |
| Observation object | HTTP `PUT /api/session/object` + event | `{"name"}` | shell.py:166-179, acquisition_engine.py:1010-1022 | Clears live curves: the UI must say so. Owned by Plan / Observe specs. |
| Field and photometry actions | `POST /api/astrometry/solve`, `PUT /api/astrometry/auto`, astrometry / catalogue settings routes, `POST /api/photometry/rerun` | — | acquisition_engine.py:767, 815; astrometry_controller.py:82; imaging_page.py:2248 | Listed for the census only: specified by the Observe, Review and Settings specs. |

Cross-cutting note: `argos/core/session/*.py` and 17 modules of `argos/workers/` import PyQt6, and
the server must not (tests/server/test_no_qt.py). Every route above that "wraps" them needs a
Qt-free port or adapter; `config.py` and `support_bundle.py` are already Qt-free.

## 3. Open questions for the owner

1. When the desktop window closes, should the server (and a running sequence) stop, or keep running
   headless so the UI can reconnect later? This decides the quit dialog and `POST /api/app/shutdown`.
2. Device status: bottom status bar (recommended above) or a 2 x 2 device block in the rail footer?
3. Theme quick toggle in the rail footer: wanted? With a shortcut (none proposed yet)?
4. UI scale (100 / 112 / 125 %): new, Qt had none. Wanted?
5. Detachable panels for a second monitor (Qt floating docks): needed in v1 (Tauri multi-window), or
   dropped?
6. Preferences: per viewer in `localStorage` (as built) or in the server config (shared with the Qt
   app, e.g. adopt `ui.theme.preset` on first launch)?
7. "Documentation & website": GitHub repository (Qt today) or `perretjules.com/argos`?
8. Support bundle: session metadata off by default (proposed) or on (Qt)?
9. Log times: UTC only (BRAND, web today) or a local-time toggle (Qt shows local)?
10. Desktop app: a minimal native menu bar on macOS (App, File, View, Help) in addition to the
    in-window controls?
11. F1-F5 need Fn on macOS keyboards: add Cmd+1 ... Cmd+5?
12. First run: show a checklist (observer code, site, ASTAP) on Connection?
13. Language selector: drop until a translation exists?
14. Network probe to 1.1.1.1 / 8.8.8.8 every 10 s: keep, make it a setting, or probe only when a
    catalogue needs the internet?
15. Night Red window chrome and cursors: custom title bar (`decorations: false`)? Native file
    dialogs never, or allowed outside Night Red?
16. Credits text for the web build (FastAPI, Svelte, uPlot, IBM Plex OFL notice; PyQt6 and pyqtgraph
    no longer shipped)?
17. pyqtgraph's right-click "Export…" (image / plot export) is used by nobody on purpose but exists
    everywhere (Appendix A.3): replace with explicit "Export PNG / CSV" actions per plot?

## A. Global census of pop-ups, menus and shortcuts (whole `argos/ui`)

Method: `grep` over `argos/ui/**/*.py` for each Qt class or call, then offscreen instantiation of
the Shell to list implicit menus (`createPopupMenu`, pyqtgraph `ViewBox.menu`). Web replacement
patterns: **C** = confirm dialog, **T** = toast + log line, **D** = control disabled with the reason
in its tooltip (BRAND 8), **I** = inline error, **P** = in-app file picker (2.3.12).

### A.1 QMessageBox (12)

| File:line | Kind | Title / text (exact) | When | Web |
|---|---|---|---|---|
| shell.py:481 | question Yes/No, default Yes | "Include session metadata?" / "Include one session's JSON, JSONL and CSV files? Raw FITS, site coordinates and network addresses are excluded. The ZIP stays on this computer until you choose to share it." | support bundle | checkbox in dialog |
| shell.py:526 | warning | "Support bundle" / "Could not create the ZIP:\n<exc>" | `OSError` | I |
| shell.py:528 | information | "Local support bundle created" / "Created <name> with <n> file(s).\n\nArgos did not upload it. Review the ZIP before sharing it." | success | T |
| analyze_page.py:614 | warning | "Could not open session" / `<SessionReviewError>` | bad session folder | T |
| analyze_page.py:717 | warning | "Frame unavailable" / "Could not find <filename>." | frame file missing | T |
| imaging_page.py:2262 | information | "Solve first" / "Plate-solve the live frame before a batch re-run." | Re-run subs without WCS | D |
| imaging_page.py:2268 | information | "No targets" / "Assign at least one target star first." | Re-run without target | D |
| imaging_page.py:2273 | information | "No comparison stars" / "The target set has no comparison stars, so differential\nphotometry cannot produce magnitudes.\n\nSolve the field and wait for the catalog (comps auto-select\nonce it arrives), or click a comparison marker on the image\nand assign it the Comp role." | Re-run without comps | D (+ help text in the tooltip or the panel) |
| imaging_page.py:2291 | information | "No frames" / "No FITS files in <folder>" | empty folder | I in the picker |
| imaging_page.py:2344 | warning | "Batch failed" / `<result.error>` | batch error | T |
| configuration_page.py:1130 | question Yes/Cancel, default Cancel | "Refresh local catalogue cache" / "Clear the <label>?\n\nNo data will be downloaded now. The next matching lookup refreshes it if internet access is available." | clear a cache | C |
| widgets/mount_dock.py:426 | question Yes/No, default No | "Park mount" / "Parking physically closes the Seestar arm and stops tracking.\n\nPark the mount now?" | Park | C |

### A.2 QFileDialog (18) — all become **P** (or Tauri dialog outside Night Red, open question 15)

| File:line | Call | Title / start / filter |
|---|---|---|
| shell.py:494 | getExistingDirectory | "Choose an Argos session" / sessions_path (web: session select) |
| shell.py:503 | getSaveFileName | "Save local support bundle" / ~/Desktop/argos-support-<v>.zip / "ZIP archive (*.zip)" |
| analysis_window.py:441 | getOpenFileName | "Open FITS" / sessions_path / "FITS (*.fits *.fit *.fts);;All files (*)" |
| panels/photometry_window.py:306 | getSaveFileName | "Export light curve" / ~/photometry.csv / "CSV (*.csv)" |
| panels/photometry_window.py:316 | getSaveFileName | "Export AAVSO" / ~/aavso.txt / "Text (*.txt)" |
| pages/analyze_page.py:606 | getExistingDirectory | "Open Argos session folder" / sessions_path |
| pages/analyze_page.py:733 | getOpenFileName | "Open session light curve" / sessions_path / "CSV (*.csv);;All files (*)" |
| pages/analyze_page.py:766 | getOpenFileName | "Open FITS frame" / sessions_path / FITS filter |
| pages/imaging_page.py:1320 | getOpenFileName | "Open FITS" / sessions_path / FITS filter |
| pages/imaging_page.py:2284 | getExistingDirectory | "Folder of saved subs" / last sequence folder or sessions_path |
| pages/configuration_page.py:1017 | getExistingDirectory | "Choose sessions folder" |
| pages/configuration_page.py:1026 | getSaveFileName | caller title (cache files, callers :431, :444) / "JSON files (*.json);;All files (*)" |
| pages/configuration_page.py:1035 | getExistingDirectory | caller title (cache folders, callers :356, :373, :457, :470, :485) |
| pages/configuration_page.py:1188 | getOpenFileName | "Locate the ASTAP executable" / "/" |
| pages/configuration_page.py:1195 | getExistingDirectory | "Locate ASTAP star databases" |
| widgets/sequence_panel.py:899 | getSaveFileName | "Save sequence preset" / presets dir / "Sequence preset (*.json)" |
| widgets/sequence_panel.py:913 | getOpenFileName | "Load sequence preset" / presets dir / same |
| widgets/astrometry_settings.py:347 | getOpenFileName | "Select ASTAP binary" (no start folder, no filter) |

### A.3 Menus and context menus

| File:line | Menu | Entries | How opened |
|---|---|---|---|
| shell.py:191 | File | Open FITS image…, Open session photometry…, —, Quit Argos | menu bar |
| shell.py:211 | More | Documentation & website, Create local support bundle…, —, About & credits | menu bar |
| shell.py:227 | View | Connection, Observe, Plan, Review, Settings, —, Reset Window Layout | menu bar |
| shell.py:243 | Field | Identify field, Keep field identified automatically (check), —, Configure field identification…, Configure catalogues… | menu bar |
| shell.py:269 | Photometry | Photometry setup…, Live curves & diagnostics…, Re-run subs… | menu bar |
| pages/imaging_page.py:370 | "Panels ▾" (InstantPopup, :366) | Image statistics, Focus diagnostics (HFD/FWHM), Activity log (check) | Observe panel bar |
| pages/imaging_page.py:384 | "Arrange ▾" (InstantPopup, :380; rebuilt on show, :393) | Restore default layout, —, Float / Dock <panel> x 8 | Observe panel bar |
| pages/analyze_page.py:281 | "Panels ▾" (InstantPopup, :278) | Metadata, AAVSO export (check) | Review panel bar |
| pages/analyze_page.py:291 | "Arrange ▾" (InstantPopup, :287; rebuilt :427) | Tile plots — 2 columns, Restore default layout, —, Float / Dock <panel> x 7 + extra source plots | Review panel bar |
| shell.py:121 (implicit) | `QMainWindow.createPopupMenu` | "Modes" (check): hides the rail (P6) | right-click on the rail |
| imaging_page.py:256, analyze_page.py:81, sequence_panel.py:211 (implicit) | `createPopupMenu` of each page workspace | every dock of the page (check) | right-click on a dock title or page tool bar |
| widgets/fits_viewer.py:138 (implicit, pyqtgraph) | ViewBox menu + scene menu | View All, X axis, Y axis, Mouse Mode, Export... (verified) | right-click on the Observe viewer (imaging_page.py:240) and the Frame Viewer (analysis_window.py:194) |
| widgets/histogram_dock.py:75, widgets/vcurve.py:31, widgets/hfd_history_dock.py:46, widgets/session_review.py:40, widgets/sequence_panel.py:105 (implicit) | pyqtgraph ViewBox menu (enabled; verified for the histogram) | same generic entries | right-click on the plot |
| widgets/lightcurve_panel.py:102, widgets/metrics_panel.py:47 | pyqtgraph menu disabled | — | — |
| every QLineEdit / QTextEdit / QSpinBox (implicit) | Qt standard edit menu | Undo, Redo, Cut, Copy, Paste, Delete, Select All (spin: Step up / down) | right-click in a field |

### A.4 QAction (excluding plain menu-bar entries already in A.3)

| File:line | Action | Notes |
|---|---|---|
| shell.py:192, 197, 203, 212, 216, 223, 231 (x5), 237, 244, 248, 260, 263, 270, 278, 282 | 19 menu-bar actions | 1.4 |
| pages/imaging_page.py:355 | 8 dock `toggleViewAction` chips (Acquisition, Telescope, Focusing, Image display, Image statistics, Focus diagnostics (HFD/FWHM), Activity log, Differential photometry) | 5 on the bar, 3 in Panels ▾ |
| pages/imaging_page.py:388 | "Reset layout" (tip "Restore the default panel arrangement") | live reset |
| pages/imaging_page.py:396, 402 | "Restore default layout"; "Float <panel>" / "Dock <panel>" | Arrange ▾ |
| pages/analyze_page.py:257, 259, 261, 263 | "Open session…", "Open curve CSV…", "Open FITS…", "+ Comparison plot below" | Review bar |
| pages/analyze_page.py:271 | 7 dock chips (Source curve, FWHM, Comparison stars, Comparison quality, Frames, Metadata, AAVSO export) | 5 on the bar, 2 in Panels ▾ |
| pages/analyze_page.py:295, 298 | "Tile plots — 2 columns", "Reset layout" | Review bar |
| pages/analyze_page.py:429, 431, 437, 443 | Arrange ▾ entries | dynamic |
| widgets/sequence_panel.py:524, 527 | 5 dock chips (Scientific source, Acquisition options, Visibility, Presets, Sequence control); "Reset panels" | Plan bar |
| widgets/overlay_bar.py:120 | `QToolButton` "Catalogues / depth…" (not an action) | opens `AstrometrySettingsDialog` catalogue tab (imaging_page.py:1427) |

### A.5 Shortcuts and keyboard handlers

| File:line | Key | Effect | Scope |
|---|---|---|---|
| shell.py:193 | `QKeySequence.StandardKey.Open` (Cmd+O / Ctrl+O) | Open FITS image… | window |
| shell.py:198 | Ctrl+Shift+O (Cmd+Shift+O on macOS) | Open session photometry… | window |
| shell.py:204 | `StandardKey.Quit` (Cmd+Q / Ctrl+Q; none on Windows, unverified) | Quit | window |
| shell.py:232 | F1 ... F5 | sections | window, also from text fields |
| sidebar.py:145, 206-210 | Tab (focus), Space / Return / Enter | activate a rail entry | focused entry |
| panels/manual_control_dialog.py:184-205 | Up / Down / Left / Right, press-and-hold (auto-repeat ignored) | jog North / South / West / East, release stops | Manual Control dialog focused |
| implicit, every QDialog / QMessageBox / QProgressDialog | Esc, Enter | cancel / default button | dialog |
| implicit, every QDockWidget | title double-click | float / re-dock | dock |

No `QShortcut` object and no other `setShortcut` exist in `argos/ui`.

### A.6 Window-level dialogs and secondary windows

| File:line | Class / title | Kind | Opened from |
|---|---|---|---|
| shell.py:75 | `Shell` "Argos  v0.4.2" | main window | main.py:178 |
| splash.py:99 | `Splash` | frameless splash | main.py:150 |
| shell.py:537 | `QDialog` "About Argos" | modal (`exec`) | More > About & credits |
| widgets/astrometry_settings.py:48 | `AstrometrySettingsDialog` "Field identification & catalogue settings" (tabs Plate solving, Field catalogue; Save / Cancel) | modal (`exec`) | shell.py:470-472 (Field menu x2), imaging_page.py:1429-1433 (overlay bar), analysis_window.py:567-569 |
| panels/manual_control_dialog.py:66 | `ManualControlDialog` "Manual Control" | non-modal tool window, stays on top (:90-93) | imaging_page.py:2795 (Mount card "✥  Jog dialog…") |
| analysis_window.py:136 | `AnalysisWindow` "Frame Viewer" / "Frame Viewer — <name>  (<w>×<h>)" (tabs Frame · selected star, FITS header, Adjust image) | top-level, non-modal | analyze_page.py:723, 776; imaging_page.py:1358 (`open_analysis`, no in-app caller: dead path) |
| panels/photometry_window.py:200 | `PhotometryWindow` "Field photometry" / "Field photometry — <object>" (tabs Variable stars, Light curve, Metrics, Targets, Comparison stars, Aperture · references) | top-level, non-modal | imaging_page.py:2093 (Photometry menu, via `_open_photometry` :2091), analyze_page.py:747 (Open curve CSV, File > Open session photometry) |
| pages/imaging_page.py:2308 | `QProgressDialog` "Batch photometry" / "Re-running photometry…" + Cancel | modeless (`show`) | Re-run subs |

### A.7 On-image overlays, tooltips and mouse behaviours

| File:line | Element | Behaviour |
|---|---|---|
| widgets/star_info_card.py:21, 147-182 | `StarInfoCard` floating card on the viewer | click a star; draggable; close "×" (Observe spec) |
| widgets/fits_viewer.py:249-250 | viewer | mouse move -> readout; click -> star selection (Observe spec) |
| pages/analyze_page.py:192 | Frames table | double-click opens the frame in a Frame Viewer |
| widgets/variable_table.py:107 | Variable table | double-click selects the target |
| statusbar.py:270, 318 | capture strip, badges | click (1.6) |
| sidebar.py:212 | rail entries | left-release (1.5) |
| all | tooltips | 140 static `setToolTip` calls in 26 files (most: sequence_panel 17, astrometry_settings 17, configuration_page 17, shell 9, photometry_window 9, mount_dock 8); no `QToolTip.showText` popover; style theme.py:644-651 |
| — | drag and drop | none (`setAcceptDrops` never called). Web opportunity: drop a FITS on the viewer (desktop app). |
