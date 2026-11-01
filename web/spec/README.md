# ARGOS web UI: consolidated specification (architecture and art direction)

Status: synthesis of the eight area specs below, 2026-11-01. Audience: the front-end and
server teams, the design team, the owner. This file **decides** where the area specs
disagree; when an area spec and this file conflict, this file wins and the area spec is
read for detail (inventories, exact Qt texts, wireframes).

| # | Area spec | Qt scope | Controls inventoried |
|---|---|---|---|
| 01 | [Shell and global](01-shell-and-global.md) | `main.py`, `splash.py`, `shell.py`, `sidebar.py`, `statusbar.py`, `log_panel.py`, `dock_host.py`, theme, census of every pop-up | 53 |
| 02 | [Connection and Settings](02-connection-and-settings.md) | `connection_page.py`, `stellarium_card.py`, `configuration_page.py`, `astrometry_settings.py`, config keys | 102 |
| 03 | [Observe page](03-observe-page.md) | `imaging_page.py` (orchestration, overlays, star card wiring, batch re-run) | 77 |
| 04 | [Viewer and image tools](04-viewer-and-image-tools.md) | `fits_viewer.py`, `image_toolbar.py`, `overlay_bar.py`, `histogram_dock.py`, `star_info_card.py`, `statistics_dock.py` | 52 |
| 05 | [Hardware controls](05-hardware-controls.md) | `camera_dock.py`, `mount_dock.py`, `focuser_dock.py`, `vcurve.py`, `hfd_history_dock.py`, `metrics_panel.py`, `manual_control_dialog.py` | 80 |
| 06 | [Plan (sequencer)](06-plan-sequencer.md) | `sequencer_page.py`, `sequence_panel.py`, `target_table.py`, `variable_table.py` | 76 |
| 07 | [Review: analysis and frame viewer](07-review-analysis.md) | `analyze_page.py`, `analysis_window.py`, batch re-run | 136 |
| 08 | [Review: photometry](08-review-photometry.md) | `photometry_window.py`, `lightcurve_panel.py`, `comparison_table.py`, curve panels, `session_review.py` | 97 |

Binding inputs: the owner's decisions (five sections Connection / Observe / Plan / Review /
Settings; symbols rather than text; professional instrument look; space first, reference
screen 1440 x 900; Night Red red-only; logo never redrawn) and
[`web/src/design/BRAND.md`](../src/design/BRAND.md) (normative). Notation in this file:
`icon-id` is an id of [`icon-inventory.json`](../src/design/icon-inventory.json);
`[icon Label]` is an icon + label button; Qt references are `file.py:line` under
`argos/ui/` unless a path is given; "Pn" refers to the problem list of the area spec named
before it (for example 05 P1).

Contents

1. [Information architecture](#1-information-architecture)
2. [Qt to web mapping](#2-qt-to-web-mapping-every-window-page-dock-panel-dialog-pop-up-and-menu)
3. [Cross-cutting UI patterns](#3-cross-cutting-ui-patterns-build-once)
4. [API v2](#4-api-v2-consolidated)
5. [New icons](#5-new-icons)
6. [Qt problems to fix during the migration](#6-qt-problems-worth-fixing-during-the-migration)
7. [Implementation plan in waves](#7-implementation-plan-in-waves)
8. [Open questions for the owner](#8-open-questions-for-the-owner)
- [Appendix A: coverage check](#appendix-a-coverage-check-of-qt-control-constructions)


---

## 1. Information architecture

### 1.1 Frame and layout constants (every section)

| Region | Size at 1440 x 900 | Rule |
|---|---|---|
| NavRail (left) | 92 px, full height | Mark + "ARGOS" wordmark (IBM Plex Sans 600), five entries with state dot, footer: `theme` quick toggle, `help` popover. Always visible (Qt's "Modes" right-click that hid the rail is dropped, 01 P6). |
| Section toolbar | one row, 40 px (47 px on Observe) | Left: section actions. Right end, same on Observe / Plan / Review: `arrange` (Panels popover) then `panels` (right-rail toggle, `P`). No page heading row (06 P26, BRAND 11.1). |
| Centre | the rest | The image (Observe, R2), the steps + visibility (Plan), the plot wall (R1), the form (Settings, max 880 px). |
| Right rail | 420 px default, drag 420-580 px, collapsible (`P`) | Foldable cards, fixed order per screen, fold state per viewer. Scrolls as a whole. |
| Bottom drawer | default 216 px, 160 px to 50 % of the section, resizable | Tabs per section; the **Log** tab exists in every section (`L`). The drawer shrinks the section, never covers the image. `D` toggles it. |
| Status bar | 32 px, one row | Global segments (devices, network, mount geometry, tracking, run chip, activity text, Log button) + section segments (cursor, frame, HFD on Observe and R2). |
| Overlays | on demand | Popovers (260-360 px, anchored), sheets (560 px, right side, modal), dialogs (480 / 560 / 640 px, modal), toasts (bottom right), context menus. All token-drawn (Night Red). |

### 1.2 Site map

```
ARGOS window (Tauri) or browser tab
├─ Start-up screen ............ mark, wordmark, version, honest stages; failure state with Retry, log folder, Copy details  [01 §2.3.8]
└─ Shell
   ├─ NavRail: Connection F1 · Observe F2 · Plan F3 · Review F4 · Settings F5
   │   └─ footer: [theme] quick toggle · [help] Help popover: Documentation · Keyboard shortcuts (?) ·
   │              Create support bundle… · About ARGOS (-> Settings › About) · Quit ARGOS (desktop only)
   ├─ StatusBar: device cluster (mount, camera, filter-wheel, focuser) · Seestar / Net · Alt-Az|EQ · Tracking ·
   │             [section segments] · run chip (REC / LIVE / AF / RE-RUN) · activity text · [log Log n]
   ├─ Global overlays: Toasts · Support bundle dialog · Keyboard shortcuts sheet · Quit confirmation + shutdown scrim ·
   │                   shared FilePicker · shared Confirm dialog
   │
   ├─ CONNECTION (F1) — one screen, nothing scrolls but the log                                   [02 §2.3 W1]
   │   ├─ Header: "n of 4 devices ready" · [connect Connect all] · [disconnect Disconnect all]
   │   ├─ Left column: Instrument card (profile select, specs, validated badge, caveats, site summary -> Settings)
   │   │               Link card (Simulator | Seestar, address, port, [discover Discover] -> Discovery results popover,
   │   │                          reachability with last check, server line, first-run checklist)
   │   ├─ Right column: Devices table (Mount, Camera, Filter wheel, Focuser: state, full reason, Connect / Disconnect /
   │   │                Retry / Stop retrying) · Planetarium card (Stellarium bridge, host, port, clients, last GoTo,
   │   │                online name lookup, help disclosure)
   │   ├─ Bottom: Connection log = Log component filtered on topics connection · discovery · planetarium
   │   └─ Dialogs: Disconnect confirmation (only while something runs)
   │
   ├─ OBSERVE (F2) — the cockpit                                                                [03 §2.3 W1]
   │   ├─ Toolbar (one row): Equipment [connect|disconnect] │ [open-image] │ [capture E] [live V] [stop Stop] │
   │   │   [zoom-out] zoom% [zoom-in] [zoom-fit F] [zoom-1to1 1] │ [stretch-auto A] [stretch-reset ⇧A] [histogram H] │
   │   │   Inspect [crosshair X] [loupe Z] [saturation C] [region-stats R] [statistics I] │
   │   │   Field [plate-solve S] [plate-solve-auto] [sky-grid G] [target-star] [labels N] [catalogue O ▾] │ … [arrange] [panels P]
   │   ├─ Viewer: image · HUD chips top-left (source/LIVE, frame #, exposure, object, field state) · loupe inset top-right ·
   │   │   overlays (grid, layers, roles, selection ring, region box + chip) · star card bottom-left (draggable) ·
   │   │   hover popover on markers · context menu (right-click)                                    [04 §2.3]
   │   ├─ Right rail cards (order fixed): Camera · Display · Statistics (hidden by default, I) · Photometry ·
   │   │   Mount (Target block with Object + search, Stellarium notice, Solved-field row, Jog disclosure) · Focuser (V-curve)
   │   ├─ Drawer tabs: Log · Light curve · Conditions · Variables · Ensemble
   │   ├─ Popovers: Catalogue layers (O) · Panels (arrange) · Recommend comparisons (Photometry card)
   │   └─ Dialogs / sheets: Open FITS image (FilePicker) · Settings sheet (Catalogues, Plate solving) ·
   │       Park (inline confirm in Mount card) · Remove comparison during a run (confirm)
   │
   ├─ PLAN (F3) — steps and time get the centre                                                 [06 §2.3]
   │   ├─ Toolbar: [bookmark Presets ▾] [save Save…] │ readiness chip -> Preflight popover │
   │   │           [start Start sequence | Start at hh:mm] [pause] [stop Stop] │ … [arrange] [panels P]
   │   ├─ Run strip (while running, and the outcome after the end until dismissed)
   │   ├─ Centre: Steps region (table + row tools add / duplicate / remove / move-up / move-down, totals, end time) ·
   │   │          Visibility timeline (altitude, limit, now, planned-run band, transit band)
   │   ├─ Right rail cards: Source (Variable star | Exoplanet transit, search + suggestions, transit sub-form,
   │   │   [goto Slew in Observe]) · Run options (Object, repeat, autofocus, end of run) · Target set (shared list,
   │   │   "Pick in field" -> Observe › Variables tab)
   │   ├─ Drawer tabs: Log
   │   └─ Dialogs: Stop sequence · Replace unsaved plan · Overwrite preset · FilePicker (import / export preset)
   │
   ├─ REVIEW (F4)                                                                                [07 §2.1, 08 §2.1]
   │   ├─ R0 Sessions (landing when nothing is open): "Live run" row first while the engine holds curves, then sessions
   │   │   under sessions_path (object, start UTC, frames, curves, quality, issues) · [browse Open folder…] ·
   │   │   [open-file Import CSV…] · [open-image Open FITS…] · filter (/)
   │   ├─ R1 Session or run: toolbar (identity, readiness badge -> issues popover, "Preview" chip for live data,
   │   │   time axis UTC | JD | BJD, [error-bars U] [relative-flux M] [zoom-fit F], [rerun-photometry Re-run photometry…],
   │   │   [export Export CSV…] [export-aavso Export AAVSO…], [arrange] [panels P]) ·
   │   │   plot wall (target facet(s), check facet, one facet per comparison, Conditions facet; linked time axis;
   │   │   cell menu: expand, copy data, hide) · rail cards Selected point · Ensemble (compact) · Session (metadata) ·
   │   │   AAVSO export (summary) · drawer tabs Frames · Ensemble (all columns) · Log · job strip (re-run, export)
   │   ├─ R2 Frame inspector: toolbar (back Alt+←, [frame-prev] [frame-next], [open-image], view, display and inspect
   │   │   tools, [plate-solve S], [sky-grid G], [labels N], [catalogue O ▾]) · same Viewer in mode "inspect" ·
   │   │   rail cards Frame · Selected star · Identification (solve, catalogues, Cancel) · Display · FITS header
   │   └─ Dialogs: Re-run photometry · Export AAVSO (preview, guards) · Export CSV · FilePicker
   │
   └─ SETTINGS (F5) — category list + form (max 880 px) + help column at ≥ 1440 px              [02 §2.3 W3-W8]
       ├─ Categories: Observer & site · Instrument · Plate solving · Catalogues · Photometry · Data & storage ·
       │              Privacy & diagnostics · Appearance · About        (filter field, /)
       └─ Dialogs: Clear cache · FilePicker (folders, ASTAP binary) · Support bundle (shared)
```

### 1.3 Conflicts between area proposals and the decisions taken

| # | Topic | Proposals in the area specs | Decision | Why |
|---|---|---|---|---|
| D1 | Icon of the Panels popover vs the rail toggle | 01 and 08: `panels` = popover; 03, 07 and the built toolbar (`ImagingToolbar.svelte:172`): `panels` = rail toggle | `panels` = right-rail toggle (`P`) everywhere; `arrange` = **Panels popover** (show / hide rail cards, drawer tabs, plot facets, Reset layout). The inventory concept of `arrange` is updated (float / dock no longer exist). | Keeps the built meaning; one popover per section with one icon. |
| D2 | Home of "Re-run subs" (batch photometry) | 03: Observe Photometry card; 01, 07, 08: Review | **Review R1** toolbar `[rerun-photometry Re-run photometry…]` -> dialog -> job strip. The dialog offers reference = "live field solution" (only when the source is the live run and a solution exists) or "solve a frame of the session" (default for saved sessions); target set = live set or the session's `targets.json`; output = new `<session>/photometry_rerun_<UTC>/`, never overwritten. No button on Observe. | It analyses saved frames; outputs belong to the session (fixes 07 P33-P35). Owner sign-off: Q-R1. |
| D3 | Live run in Review, and where ensemble edits live | 08: Review "Live run" source with edits; 07: Review offline only | Review R0 lists **"Live run"** as a read-only source (same plot wall as sessions). Ensemble **edits** (remove, recommend, refresh catalogue, proposed count) live only in **Observe** (Photometry card + Ensemble drawer tab), where the run is. Review shows "Edit the ensemble in Observe" on the live run. | One place that changes the running measurement; Review never edits (07 principle). |
| D4 | Plot wall | 07: one star per cell + per-cell picker + "Ensemble overlay" cell; 08: one facet per star | **One facet per star** (targets, check, each comparison) + one Conditions facet; no picker, no "All targets / All comparisons" overlay, no "+ Comparison plot below". Facet visibility in the `arrange` popover. | BRAND 10: at most 3 series per plot; Qt already created one dock per star. |
| D5 | Frames, metadata, ensemble in Review | 07: Frames drawer + Metadata rail card; 08: both drawer tabs | Drawer tabs **Frames**, **Ensemble** (all columns), **Log**; rail cards **Selected point**, **Ensemble** (compact verdict), **Session** (metadata, folded), **AAVSO export**. | Wide tables in the drawer, key/value lists in the rail. |
| D6 | Focus and quality time series | 03: drawer "Focus trend"; 05: drawer "Focus" + "Conditions"; 07: "Frame quality" cell; 08: "Quality trend" facet | **One `ConditionsTimeline` component** named **Conditions**: Observe drawer tab and Review facet; metric chips (HFD, FWHM, stars, sky, airmass, sensor / focuser temperature, focuser position), up to 3 small multiples, shared time axis; one server data source (`conditions`). V-curve stays in the Focuser card. | Replaces HFD history, Metrics tab, Frame quality plot (fixes 05 P10-P11, P34; 08 P20-P21). |
| D7 | Variable-star list of the solved field | 06: Observe drawer tab; 08: Photometry rail card picker; 03: side sheet | **Observe drawer tab "Variables"** (filter, sort, set as target); Plan's Target set card links to it. | It needs width, a solved frame, and its filter drives the image markers. |
| D8 | Qt "Field photometry" window | 03: 580 px side sheet; 08: dissolved | **Dissolved**, no side sheet: Photometry rail card (target, comparisons, check, quality verdict, effective geometry, actions), drawer tabs Light curve / Variables / Ensemble / Conditions, Settings › Photometry (aperture and reference criteria), exports in Review. | No floating window, no overlay over the rail. |
| D9 | Image statistics | 03: drawer tab; 04: rail card | **Rail card "Statistics"**, hidden by default, toggled by `statistics` (`I`). | Eleven key/value readouts + star aperture: narrow, not a time series. |
| D10 | Observe rail order and the Connection card | built: Connection, Camera, Display, Mount; 03: Connection last; 04: Connection first | **Camera · Display · Statistics · Photometry · Mount · Focuser**. The Connection card is **removed** from the Observe rail: the toolbar equipment button (connect / disconnect all) stays, details live on the Connection screen, the status-bar device cluster links there. | Duplicate controls; the cards used while observing must be visible without scrolling (BRAND 11.1). |
| D11 | Observation identity ("Object") | Qt: camera Object + mount Object (05 P15); 06: Plan Run options; 05: Mount card Target block | **One server value** (`PUT /api/observation`), edited in the Observe Mount card Target block (Object field merged with catalogue search) and in Plan Run options; echoed as a HUD chip; locked while a sequence runs. The Camera card has no Object field. | One field for one concept; the FITS OBJECT and the target-set key cannot diverge. |
| D12 | Catalogue / plate-solve settings at the point of use | 02: subset popovers W9a / W9b with their own forms; 03, 04: Settings form in a sheet | Observe and R2 **Catalogue layers popover (`O`)** holds display only (layer toggles + counts, Gaia display depth). Its footer links "Catalogue settings…" and "Plate-solving settings…" open the **Settings category form in a sheet** (same component, same immediate-apply save, `config` event, catalogue refetch on change). No subset form. | One form per key; fixes the Qt dialog / page split (01 P17, 02 stale overwrite). |
| D13 | Settings category names | 01: "Astrometry"; 03: "Field identification" | 02's nine categories are canonical: Observer & site, Instrument, Plate solving, Catalogues, Photometry, Data & storage, Privacy & diagnostics, Appearance, About. | One vocabulary. |
| D14 | About and support bundle | 01: About modal dialog; 02: Settings › About | **Settings › About** is the only About (version, licence, credits, paths, documentation link); the Help popover item opens it. The **Support bundle dialog** is one modal opened from the Help popover and from Settings › Privacy & diagnostics. | One place, no duplicate wording (01 P34). |
| D15 | Theme switch | built: Observe toolbar `theme`; 01: rail footer | Rail footer quick toggle (all sections) + Settings › Appearance; **removed from the Observe toolbar** and the status bar. | Night Red one click away from every section; frees a toolbar slot. |
| D16 | Reset layout | 06: Settings only; 01, 03, 07: per section | `[layout-reset Reset layout]` at the bottom of each section's Panels popover (live, that section) + "Reset all layouts" in Settings › Appearance. | Fixes Qt reset that did nothing (01 P9). |
| D17 | Activity log | Qt: Observe dock only (01 P31) | One global log store; **Log tab in every section's drawer** (`L`), plus the filtered Connection log region; levels CMD, INFO, OK, WARN, ERROR (+ debug hidden). | Feedback visible from any section. |
| D18 | Status bar content | 01: global segments; 03: frame file, sequence, HFD; built: zoom, theme | Left: device cluster, Seestar / Net, Alt-Az / EQ, Tracking. Middle (section): Observe and R2 cursor X Y value (+ RA / Dec when solved), frame # and file, HFD and stars; R1 selected time. Right: run chip (sequence progress lives **only** here, fixes 03 P26), activity text, Log. Zoom and Theme items removed. | One row, no duplicates. |
| D19 | ⌘/Ctrl+O and ⌘/Ctrl+Shift+O | 01: global, Observe; 07: Review opens the inspector | ⌘/Ctrl+O = "Open FITS image": in Review it opens **R2** (never disturbs the live view), in every other section it opens into **Observe**. ⌘/Ctrl+Shift+O = Review R0 Sessions. "Import CSV" is a separate R0 action. | One verb, the context decides the viewer (fixes 01 P13). |
| D20 | File pickers | 01, 03: in-app picker; 04, 06, 07: Tauri native dialogs | **One in-app `FilePicker`** over `GET /api/fs/list` in every build and theme (Night Red safe, works in the browser). Tauri native dialogs are an option outside Night Red only if the owner asks (Q-G7). | One component, one behaviour, no grey OS dialog at night. |
| D21 | Escape | 01: close popover first, then abort; 03, 04: both; 07: never navigation | `Esc` **always** aborts mount motion (slew, jog) and a manual focuser move when one is in progress, in any section and any focus, **and** closes the topmost transient layer (menu, popover, card, dialog = Cancel). It never stops an exposure, a sequence or autofocus. | Safety key works in one press. |
| D22 | Single-key conflicts | 01: `L` = log; 03, 04: `L` = labels; 08: `R` = relative flux vs 04 `R` = region; 07: `T` = Frames drawer vs 08 `D` = drawer | `L` = Log (global); **`N` = labels** ("names"); **`M` = magnitude / relative flux**; `R` = region statistics; `D` = drawer of the current section; `T` unused (tracking moves hardware). Full map: §3.10. | Conflict-free registry. |
| D23 | Keyboard jog | 03: arrows when the pad has focus; 05: `J` arms arrow keys | Both: arrows jog while the Jog pad has focus **or** after `J` armed it; key-down starts, key-up stops, each axis tracked; blur, hidden tab or link loss stops all axes; server dead-man. | Replaces the stay-on-top Qt dialog. |
| D24 | Target set list | 06: Plan card reusing a component; 08: Observe Photometry card | One **`TargetSetList`** component in the Observe Photometry card and the Plan Target set card; remove = immediate + Undo toast (confirmation during a run). | One view of one set. |
| D25 | Light curve on Observe | 08 Q14 | Drawer "Light curve" tab shows **target + check** (2 series), comparisons only in Review. | BRAND 10; the check validates the target at a glance. |
| D26 | Light-curve time axis | 07: UTC clock default; 08: JD default | **UTC clock** default with the night's date in the axis title; JD and BJD_TDB one click away (segmented), remembered per viewer; tooltips always show UTC, JD and BJD (5 decimals). | Readable at night; science values one click away (owner may veto, Q-R6). |
| D27 | Second monitor / floating panels | all specs: open question | No floating panels in v1. `panel-float` stays reserved for a later Tauri multi-window "Open in new window" (Review, drawer). | Single window keeps the layout predictable; revisit in wave 8. |
| D28 | Telescope profile editing | 02 Q1: both Connection and Settings | Edited on **Connection** (Instrument card) only; Settings › Instrument shows it read-only with a link. Locked while any device is connected (server 409 with reason). | One control, one guard (fixes 02 silent refusal). |
| D29 | Exports destination | 07: server writes in the session; 08: download or server | Desktop: server writes into `<session>/exports/` by default (path editable in the dialog through the FilePicker); browser build: download. Never overwrite silently. | Exports belong next to the session, not in `~` (07 P32). |
| D30 | Night Red palettes | 03, 04: Neutral + Negative; 07: Neutral only | **Neutral only** in Night Red; Negative, Fire and Ice disabled with the reason "false colour is off in Night Red". | Negative turns the sky background bright red: more light, against dark adaptation. |

### 1.4 Section responsibilities (one owner per function)

| Function | Lives in | Never duplicated in |
|---|---|---|
| Connect / disconnect devices, discovery, profile, Stellarium bridge | Connection (+ Observe toolbar equipment button as the one shortcut) | Observe rail, Settings |
| Live image, capture, live view, display, field identification, overlays, roles | Observe | Plan, Review (R2 is read-only: no roles, no capture) |
| Mount, focuser, autofocus, filter wheel | Observe rail cards | Plan (only "Slew in Observe" link) |
| Observation identity | server; edited in Observe Mount card and Plan Run options | Camera card |
| Target set edits | Observe (star card, Photometry card, Variables tab); removal also from the Plan Target set card (same `TargetSetList`, D24) | Review (read-only) |
| Ensemble edits (remove comparison, recommend, refresh catalogue, proposed count) | Observe (Photometry card, Ensemble tab) | Review, Plan |
| Sequences, presets, visibility, transits | Plan | Observe (status-bar run chip only) |
| Sessions, curves, exports, re-run, frame inspection | Review | Observe |
| Persistent parameters (site, paths, ASTAP, catalogues, photometry, privacy, appearance) | Settings (sheets reuse the same forms) | anywhere else as a separate form |


---

## 2. Qt to web mapping (every window, page, dock, panel, dialog, pop-up and menu)

Every element found by the eight inventories, with its destination after the decisions of
§1.3. "Dropped" rows say why; nothing else is left without a home. Control-level mapping
(each button, field, shortcut) is in each spec's §2.2; Appendix A proves every control
construction is inventoried.

### 2.1 Shell and global

| # | Qt element (file:line) | Kind | Web destination | Spec |
|---|---|---|---|---|
| M1 | Start-up sequence `main.main` main.py:137 | process lifecycle | Start-up screen inside the window, honest stages, failure screen with Retry | [01 §1.1](01-shell-and-global.md#11-start-up-sequence-mainmain-mainpy137-process-lifecycle-no-window-of-its-own), [01 §2.3.8](01-shell-and-global.md#238-start-up-screen-and-start-up-failure) |
| M2 | `Splash` splash.py:99 | frameless splash | Start-up screen (themed before first paint, mark from `brand/argos-mark.svg`) | [01 §1.2](01-shell-and-global.md#12-splash-splash-splashpy99-frameless-qsplashscreen-opened-by-mainpy150-non-modal-centred-460-x-280-px) |
| M3 | `Shell` shell.py:75 | main window | Shell frame: NavRail + section + StatusBar (exists in `App.svelte`) | [01 §1.3](01-shell-and-global.md#13-main-window-shell-shellpy75-qmainwindow-top-level) |
| M4 | Menu **File** shell.py:191: Open FITS image… (⌘O), Open session photometry… (⌘⇧O), Quit | menu bar | Observe toolbar `open-image` + ⌘/Ctrl+O (D19); Review R0 + ⌘/Ctrl+Shift+O; Help popover "Quit ARGOS" + ⌘/Ctrl+Q (desktop) | [01 §1.4](01-shell-and-global.md#14-menu-bar-shellpy185-285-qmenubar-native-global-menu-on-macos) |
| M5 | Menu **More** shell.py:211: Documentation & website, Create local support bundle…, About & credits | menu bar | Help popover in the rail footer; Support bundle dialog; Settings › About (D14) | [01 §1.4](01-shell-and-global.md#14-menu-bar-shellpy185-285-qmenubar-native-global-menu-on-macos), [01 §2.3.3](01-shell-and-global.md#233-rail-footer-and-help-popover) |
| M6 | Menu **View** shell.py:227: Connection … Settings (F1-F5), Reset Window Layout | menu bar | NavRail entries F1-F5; Panels popover "Reset layout" + Settings › Appearance "Reset all layouts" (D16) | [01 §1.4](01-shell-and-global.md#14-menu-bar-shellpy185-285-qmenubar-native-global-menu-on-macos) |
| M7 | Menu **Field** shell.py:243: Identify field, Keep field identified automatically, Configure field identification…, Configure catalogues… | menu bar | Observe toolbar `plate-solve` (S), `plate-solve-auto`; Settings › Plate solving and › Catalogues, opened as sheets from the Catalogue layers popover (D12) | [01 §1.4](01-shell-and-global.md#14-menu-bar-shellpy185-285-qmenubar-native-global-menu-on-macos), [03 §1.10](03-observe-page.md#110-field-identification-workflow-shell-field-menu--page-engine-controller) |
| M8 | Menu **Photometry** shell.py:269: Photometry setup…, Live curves & diagnostics…, Re-run subs… | menu bar | Observe Photometry card + Settings › Photometry; Observe drawer "Light curve" (+ Review Live run); Review R1 Re-run photometry (D2) | [01 §1.4](01-shell-and-global.md#14-menu-bar-shellpy185-285-qmenubar-native-global-menu-on-macos), [03 §1.13](03-observe-page.md#113-live-photometry-wiring-photometrywindow-photometry_windowpy200-light-curve-dock), [08 §1.8](08-review-photometry.md#18-entry-points-outside-the-window-shellpy-imaging_pagepy) |
| M9 | `Sidebar` sidebar.py:232 | navigation rail | `NavRail` (exists), revised state dots, footer `theme` + `help` | [01 §1.5](01-shell-and-global.md#15-navigation-rail-sidebar-sidebarpy232-qtoolbar-on-the-left-fixed-92-px-always-visible), [01 §2.4.4](01-shell-and-global.md#244-rail-state-dots-revised) |
| M10 | Rail context menu "Modes" (`createPopupMenu`, shell.py:121) | implicit context menu | **Dropped**: hid the rail with no way back (01 P6) | [01 §1.3](01-shell-and-global.md#13-main-window-shell-shellpy75-qmainwindow-top-level) |
| M11 | `TopStatusBar` statusbar.py:30 (device badges, capture strip, network, geometry, tracking, last action) | status strip | Global segments of the bottom StatusBar (D18) | [01 §1.6](01-shell-and-global.md#16-top-status-strip-topstatusbar-statusbarpy30-32-px-strip-above-every-page-always-visible), [01 §2.3.2](01-shell-and-global.md#232-status-bar-states-32-px-one-row-nothing-reserved-when-empty) |
| M12 | `LogPanel` log_panel.py:23 | dock "Activity log" | Log tab of every section drawer (`L`), level filter, search, copy, save, clear, capped | [01 §1.7](01-shell-and-global.md#17-activity-log-logpanel-log_panelpy23-dock-activity-log-in-observes-bottom-area-visible-by-default-tabbed-with-the-hidden-light-curve-dock-imaging_pagepy298-472-475), [01 §2.3.9](01-shell-and-global.md#239-activity-log-drawer-global-under-the-section-content-default-200-px-resizable) |
| M13 | Dock mechanism `make_dock` dock_host.py:48, chips `style_toggle_action` :122, page dock-list menus (imaging_page.py:256, analyze_page.py:81, sequence_panel.py:211) | dock factory, chips, implicit menus | Panel host convention: foldable rail cards, drawer tabs, Panels popover (`arrange`); title drag, float, double-click float **dropped** (D27) | [01 §1.8](01-shell-and-global.md#18-dock-mechanism-make_dock-dock_hostpy48-style_toggle_action-dock_hostpy122-panel_toolbar_qss-dock_hostpy134), [01 §2.3.10](01-shell-and-global.md#2310-panels-popover-shared-panel-host-right-end-of-each-section-toolbar) |
| M14 | About dialog shell.py:535 | modal `QDialog` | Settings › About (D14) | [01 §1.9](01-shell-and-global.md#19-about-dialog-_build_about_dialog-shellpy535-modal-qdialog-about-argos-min-width-460-opened-by-more--about--credits), [02 §1.11](02-connection-and-settings.md#111-settings--files--application-configuration_pagepy297-317-716-773) |
| M15 | Support bundle flow shell.py:478 (question 481, folder 494, save 503, warning 526, info 528) | 5 modal boxes | One Support bundle dialog: session select, include-metadata checkbox (off), destination, inline error, success toast | [01 §1.10](01-shell-and-global.md#110-support-bundle-flow-_create_support_bundle-shellpy478-opened-by-more--create-local-support-bundle), [01 §2.3.6](01-shell-and-global.md#236-support-bundle-dialog-modal-560-px) |
| M16 | Theme / appearance (configuration_page.py:716, theme.py:46) | settings card + runtime | Settings › Appearance (live) + rail footer quick toggle (D15) | [01 §1.11](01-shell-and-global.md#111-theme-palette-and-typography-behaviour-themepy-palettespy-designpy-controls-in-settings--files--application--appearance-configuration_pagepy716-764) |
| M17 | Implicit window status bar shell.py:457, 605 | transient message bar | Toasts + log lines | [01 §1.12](01-shell-and-global.md#112-implicit-window-status-bar-e12-qmainwindowstatusbar-shellpy457-605) |
| M18 | Shutdown `Shell.closeEvent` shell.py:611 | lifecycle | Quit confirmation when busy + shutdown progress scrim (desktop) | [01 §1.14](01-shell-and-global.md#114-shutdown-sequence-shellcloseevent-shellpy611-file--quit-close-box-cmdq), [01 §2.3.7](01-shell-and-global.md#237-quit-confirmation-and-shutdown-desktop-app) |
| M19 | Cross-page wiring shell.py:166-179, 303-411 | signals | Server events (`observation`, `devices`, `stellarium`, `target_suggestions`, `sequence`) | [01 §1.13](01-shell-and-global.md#113-cross-page-wiring-owned-by-the-shell-shellpy166-179-303-361-367-411) |
| M20 | Qt standard edit context menu of every text field | implicit context menu | Browser / webview default in text fields; in Night Red the native menu is suppressed (keyboard copy / paste remain) | [01 §A.3](01-shell-and-global.md#a3-menus-and-context-menus) |

### 2.2 Connection and Settings

| # | Qt element (file:line) | Kind | Web destination | Spec |
|---|---|---|---|---|
| M21 | `ConnectionPage` connection_page.py:49 | page | Connection screen (two columns + log) | [02 §1.1](02-connection-and-settings.md#11-connection-page-connectionpage-connection_pagepy49-page-not-modal-full-width-scroll-page), [02 §2.3](02-connection-and-settings.md#23-wireframes-1440-x-900-reference-rail-92-px-status-bar-32-px) |
| M22 | Start card "Telescope · equipment" connection_page.py:109-169 | card | Instrument card + Link card + header actions Connect all / Disconnect all | [02 §1.2](02-connection-and-settings.md#12-start-card-telescope--equipment-designcard-connection_pagepy109-169-card-always-visible) |
| M23 | Individual devices `_DeviceCard` connection_page.py:383-471 + bulk row 206-215 | collapsed region | Devices table (always visible, full error reason, Retry / Stop retrying); bulk buttons merged into the header | [02 §1.3](02-connection-and-settings.md#13-individual-devices--bulk-row-connection_pagepy193-215-383-471-collapsed-region-not-modal) |
| M24 | Details disclosure connection_page.py:82-85 | toggle | **Dropped**: nothing hidden any more | [02 §1.2](02-connection-and-settings.md#12-start-card-telescope--equipment-designcard-connection_pagepy109-169-card-always-visible) |
| M25 | `StellariumCard` stellarium_card.py:33 | group box | Connection › Planetarium card (host shown, bind error shown) | [02 §1.4](02-connection-and-settings.md#14-stellarium-card-stellariumcardqgroupbox-stellarium_cardpy33-inside-13s-region-under-planetarium-connection_pagepy94-103-not-modal) |
| M26 | Network reachability network_monitor.py:48 -> statusbar.py:152-168 | display | Status bar "Seestar / Net" (three states) + Link card line with last check | [02 §1.5](02-connection-and-settings.md#15-network-reachability-networkmonitor-network_monitorpy48-display-in-topstatusbar-statusbarpy152-168) |
| M27 | `ConfigurationPage` configuration_page.py:57 (`QToolBox`, 86-111) | page, accordion | Settings screen: category list + filter + form + help column | [02 §1.6](02-connection-and-settings.md#16-settings-page-configurationpage-configuration_pagepy57-page-not-modal-scroll-page-max-940-px), [02 §2.3](02-connection-and-settings.md#23-wireframes-1440-x-900-reference-rail-92-px-status-bar-32-px) |
| M28 | Settings › Observatory configuration_page.py:141-265 | accordion section | Settings › Observer & site | [02 §1.7](02-connection-and-settings.md#17-settings--observatory-card-observer--site-configuration_pagepy141-265) |
| M29 | Settings › Equipment · camera configuration_page.py:520-637 | accordion section | Settings › Instrument (profile read-only mirror D28, Sensor limits) | [02 §1.8](02-connection-and-settings.md#18-settings--equipment--camera-cards-telescope-520-556-and-camera-608-637) |
| M30 | Settings › Astrometry configuration_page.py:639-714 | accordion section | Settings › Plate solving (canonical) | [02 §1.9](02-connection-and-settings.md#19-settings--astrometry-card-astrometry-plate-solving-configuration_pagepy639-714) |
| M31 | Settings › Catalogues · data configuration_page.py:319-518 | accordion section | Settings › Catalogues (budget, bundled catalogue), › Instrument (calibration folder), › Data & storage (presets, caches table), › Privacy & diagnostics (diagnostics) | [02 §1.10](02-connection-and-settings.md#110-settings--catalogues--data-card-data--catalogues-configuration_pagepy319-518) |
| M32 | Settings › Files · application configuration_page.py:297-317, 716-773 | accordion section | Settings › Data & storage (sessions), › Appearance (theme), › Privacy & diagnostics (log level), › About; Language **dropped** (dead, 01 P38) | [02 §1.11](02-connection-and-settings.md#111-settings--files--application-configuration_pagepy297-317-716-773) |
| M33 | Cache clear `QMessageBox.question` configuration_page.py:1130 | modal box | Confirm dialog "Clear the … cache?" (Cancel / Clear cache) | [02 §1.12](02-connection-and-settings.md#112-cache-clear-confirmation-qmessageboxquestion-configuration_pagepy1130-1137-modal) |
| M34 | Settings file pickers configuration_page.py:1017, 1026, 1035 (x5), 1188, 1195 | OS dialogs | FilePicker (folder, file, executable modes) | [02 §1.13](02-connection-and-settings.md#113-native-file-and-folder-pickers-qfiledialog-modal-os-dialogs-10-call-sites) |
| M35 | `AstrometrySettingsDialog` astrometry_settings.py:48, tab Plate solving 90-126 | modal dialog | Settings › Plate solving (form), also opened as a sheet from Observe / R2 | [02 §1.14](02-connection-and-settings.md#114-dialog-field-identification--catalogue-settings-tab-plate-solving-astrometrysettingsdialog-astrometry_settingspy48-90-126-modal-exec-min-width-440) |
| M36 | Same dialog, tab Field catalogue + Save / Cancel astrometry_settings.py:128-268, 77-82 | modal dialog tab | Settings › Catalogues (+ › Photometry for the automatic comparison count); Save / Cancel replaced by immediate apply | [02 §1.15](02-connection-and-settings.md#115-same-dialog-tab-field-catalogue-and-buttons-astrometry_settingspy128-268-77-82-351-396) |
| M37 | ASTAP binary picker astrometry_settings.py:347 | OS dialog | FilePicker (executable mode) | [02 §1.13](02-connection-and-settings.md#113-native-file-and-folder-pickers-qfiledialog-modal-os-dialogs-10-call-sites) |

### 2.3 Observe, viewer and hardware

| # | Qt element (file:line) | Kind | Web destination | Spec |
|---|---|---|---|---|
| M38 | `ImagingPage` imaging_page.py:135 (inner `QMainWindow` workspace 256) | page | Observe screen | [03 §1.1](03-observe-page.md#11-imagingpage-container-imagingpage-imaging_pagepy135-page-sidebar-f2-non-modal-central-stack), [03 §2.3](03-observe-page.md#23-wireframes) |
| M39 | `ImageToolbar` image_toolbar.py:22: Open image…, Preview, Palette, caption | toolbar | `open-image` in the Observe toolbar; Preview (Colour / Raw / R / G / B) and Palette in the Display card "View options"; caption moved to the tooltip | [03 §1.2](03-observe-page.md#12-image-toolbar-imagetoolbar-image_toolbarpy22-built-imaging_pagepy236-toolbar-row-1-always-visible), [04 §1.3](04-viewer-and-image-tools.md#13-image-toolbar-imagetoolbar-image_toolbarpy22-toolbar-always-visible-non-modal) |
| M40 | Panel-toggle strip imaging_page.py:348-364 | toolbar | Panels popover (`arrange`) + card fold | [03 §1.3](03-observe-page.md#13-panel-toggle-strip-panels--and-arrange--_build_panel_bar-imaging_pagepy348-391-menus-370-384-toolbar-row-2) |
| M41 | "Panels ▾" menu imaging_page.py:366-375 | popup menu | Panels popover | [03 §1.3](03-observe-page.md#13-panel-toggle-strip-panels--and-arrange--_build_panel_bar-imaging_pagepy348-391-menus-370-384-toolbar-row-2) |
| M42 | "Arrange ▾" menu imaging_page.py:380-403 + "Reset layout" 388 | popup menu | Panels popover "Reset layout"; Float / Dock **dropped** (D27) | [03 §1.3](03-observe-page.md#13-panel-toggle-strip-panels--and-arrange--_build_panel_bar-imaging_pagepy348-391-menus-370-384-toolbar-row-2) |
| M43 | 8 docks imaging_page.py:279-307: Acquisition, Telescope, Focusing, Image display, Image statistics, Focus diagnostics, Activity log, Differential photometry | docks | Rail cards Camera, Mount, Focuser, Display, Statistics; drawer tabs Conditions, Log, Light curve | [03 §1.4](03-observe-page.md#14-dock-containers-make_dock-dock_hostpy48-115-8-instances-imaging_pagepy279-307) |
| M44 | `OverlayBar` overlay_bar.py:54 (10 chips, Gaia G slider) | 2-row toolbar | Toolbar Field group (`sky-grid` G, `target-star`, `labels` N) + Catalogue layers popover (`catalogue` O: layer rows with counts, Gaia display depth) | [03 §1.5](03-observe-page.md#15-overlay-bar-overlaybar-overlay_barpy54-built-imaging_pagepy317-322-rows-3-4-max-height-76-px), [04 §1.4](04-viewer-and-image-tools.md#14-overlay-bar-overlaybar-overlay_barpy54-two-row-chip-strip-always-visible-non-modal) |
| M45 | "Catalogues / depth…" overlay_bar.py:120 | tool button -> modal dialog | Popover footer link -> Settings › Catalogues sheet (D12) | [03 §1.15](03-observe-page.md#115-catalogue-settings-dialog-m-as-opened-from-the-page) |
| M46 | Viewer click / marker hover imaging_page.py:793-1310 | mouse behaviour | Viewer selection (10 screen px hit), hover popover | [03 §1.6](03-observe-page.md#16-viewer-interaction-owned-by-the-page-fitsviewer-wired-576-578-behaviour-793-1310), [04 §2.4](04-viewer-and-image-tools.md#24-interaction-and-states) |
| M47 | `StarInfoCard` star_info_card.py:21 | on-image card | Star card bottom-left, draggable, content-sized; Dismiss and resize grip **dropped** (duplicate / broken) | [03 §1.7](03-observe-page.md#17-star-info-card-starinfocard-star_info_cardpy21-child-of-the-viewer-created-imaging_pagepy242), [04 §1.6](04-viewer-and-image-tools.md#16-star-info-card-starinfocard-star_info_cardpy21-floating-on-image-card-observe-only-non-modal) |
| M48 | Context bar imaging_page.py:412-437 | strip under the image | Status bar Frame segment (file name) + run chip | [03 §1.8](03-observe-page.md#18-context-bar-_build_context_bar-imaging_pagepy412-437-under-the-image) |
| M49 | Open FITS `QFileDialog` imaging_page.py:1320 | OS dialog | FilePicker "Open FITS image" (FITS filter) | [03 §1.9](03-observe-page.md#19-open-fits-flow-_on_open_fits-imaging_pagepy1312-1339-open_fits-1341-1343) |
| M50 | Batch re-run flow imaging_page.py:2248-2367: info boxes 2262, 2268, 2273, folder dialog 2284, "No frames" 2291, progress 2308, "Batch failed" 2344 | 5 boxes + dialogs | Review R1 Re-run photometry dialog (disabled reasons instead of boxes, inline "no frames"), job strip with Cancel, error toast (D2) | [03 §1.14](03-observe-page.md#114-batch-re-run-_on_rerun_subs-imaging_pagepy2248-2367-photometrybatchworker), [07 §1.13](07-review-analysis.md#113-batch-photometry-re-run-e29-photometry--re-run-subs-ui-in-ip-worker-bw) |
| M51 | Marker tooltips fits_viewer.py:54-61 (bodies imaging_page.py:1904-2008) | hover tips | Viewer hover popover (tokens, mono) | [03 §1.11](03-observe-page.md#111-catalogue-fetch-and-overlay-projection), [04 §1.1](04-viewer-and-image-tools.md#11-image-canvas-fitsviewer-fits_viewerpy73-central-widget-always-visible-non-modal) |
| M52 | `FitsViewer` fits_viewer.py:73 | image widget | Shared `FitsViewer.svelte` (exists), extended; Observe and R2 (`mode="inspect"`) | [04 §1.1](04-viewer-and-image-tools.md#11-image-canvas-fitsviewer-fits_viewerpy73-central-widget-always-visible-non-modal) |
| M53 | pyqtgraph viewer context menu + Export fits_viewer.py:138-141 | context menu | ARGOS viewer context menu: Fit, 1:1, Measure / identify here, Copy pixel position, Copy RA / Dec, Region statistics here, Clear selection, Save view as PNG; axis, mouse-mode and exporter entries **dropped** | [04 §1.2](04-viewer-and-image-tools.md#12-viewer-context-menu-pyqtgraph-viewboxmenu--scene-export-right-click-non-modal-popup) |
| M54 | In-image readouts, loupe, selection label fits_viewer.py:147-247 | overlays | Status-bar cursor readout (+ RA / Dec), HUD centre chip, loupe inset top-right; selection label **dropped** (card carries it) | [04 §1.1](04-viewer-and-image-tools.md#11-image-canvas-fitsviewer-fits_viewerpy73-central-widget-always-visible-non-modal) |
| M55 | Region box `RectROI` fits_viewer.py:386-395 | draggable ROI | Region tool (`region-stats`, R) + on-image chip + Statistics card block | [04 §1.1](04-viewer-and-image-tools.md#11-image-canvas-fitsviewer-fits_viewerpy73-central-widget-always-visible-non-modal) |
| M56 | `HistogramDock` histogram_dock.py:41 ("Image display" / "Adjust image") | dock card | Display card (existing StretchCard: histogram R/G/B, levels, transfer, auto, rotation, View options); tool toggles -> toolbar Inspect group; WCS checkbox merged into `sky-grid`; star aperture -> Statistics card | [04 §1.5](04-viewer-and-image-tools.md#15-adjust-image-card-histogramdock-histogram_dockpy41-dock-image-display--tab-adjust-image-non-modal) |
| M57 | Histogram pyqtgraph menu histogram_dock.py:75 | context menu | **Dropped**: fixed data range, hover readout | [04 §1.5](04-viewer-and-image-tools.md#15-adjust-image-card-histogramdock-histogram_dockpy41-dock-image-display--tab-adjust-image-non-modal) |
| M58 | `StatisticsDock` statistics_dock.py:22 | dock card | Statistics rail card, hidden by default (I) (D9) | [04 §1.7](04-viewer-and-image-tools.md#17-statistics-card-statisticsdock-statistics_dockpy22-dock-image-statistics-observe-only-non-modal) |
| M59 | `CameraDock` camera_dock.py:82 (+ Offset / Binning rows 152-174, lock hint 213-216) | dock card | Camera card: exposure, gain, Frame segmented, Filter segmented, Sensor disclosure (offset, binning, preview), facts HFD / stars / sensor °C, owner badge; Object -> Mount card (D11) | [05 §1.1](05-hardware-controls.md#11-camera-form-cameradock-camera_dockpy82-card-in-dock-acquisition-opened-by-default-non-modal-right-dock-stack) |
| M60 | `MountDock` mount_dock.py:57 (lookup result 152-160, Stellarium suggestion 165-187, inline jog 224-265) | dock card | Mount card: readouts, tracking (+ rate), park / unpark, Target block (Object + search + result), Stellarium notice, Solved-field row (Centre, Sync if kept), Jog disclosure | [05 §1.2](05-hardware-controls.md#12-mount-control-mountdock-mount_dockpy57-card-in-dock-telescope-tab-behind-acquisition-non-modal) |
| M61 | Park confirmation mount_dock.py:426 | modal box | Inline confirm in the Mount card (built, `MountCard.svelte:136-161`) | [05 §1.3](05-hardware-controls.md#13-park-confirmation-qmessageboxquestion-mount_dockpy426-435-modal-opened-by-mount-21) |
| M62 | `FocuserDock` focuser_dock.py:38 (+ autofocus status 122-129) | dock card | Focuser card (position, temperature, moving, Out / In, Go to, Autofocus / Stop AF, Halt, progress); auto-unfolds during AF | [05 §1.4](05-hardware-controls.md#14-focuser-control-focuserdock-focuser_dockpy38-card-in-dock-focusing-tab-behind-acquisition-non-modal) |
| M63 | `VCurveWidget` vcurve.py:20 + pyqtgraph menu | plot | Plot inside the Focuser card, worker's own fit, hover value; menu **dropped** | [05 §1.5](05-hardware-controls.md#15-v-curve-vcurvewidget-vcurvepy20-inside-14-visible-from-the-first-autofocus) |
| M64 | `HfdHistoryDock` hfd_history_dock.py:25 + pyqtgraph menu | dock plot | Observe drawer **Conditions** tab (D6); menu dropped | [05 §1.6](05-hardware-controls.md#16-hfd-history-hfdhistorydock-hfd_history_dockpy25-dock-focus-diagnostics-hfdfwhm-hidden-by-default-opened-from-panels-) |
| M65 | `MetricsPanel` metrics_panel.py:26 (Field photometry tab "Metrics") | tab plot | Conditions tab (Observe) and Conditions facet (Review) (D6) | [05 §1.7](05-hardware-controls.md#17-session-metrics-metricspanel-metrics_panelpy26-tab-metrics-in-the-field-photometry-window), [08 §1.3](08-review-photometry.md#13-metrics-tab-metricspanel-metrics_panelpy26-tab-of-w1) |
| M66 | `ManualControlDialog` manual_control_dialog.py:66 | stay-on-top tool window | Mount card Jog disclosure + `J` / focused-pad arrow keys + server dead-man (D23) | [05 §1.8](05-hardware-controls.md#18-manual-control-dialog-manualcontroldialog-manual_control_dialogpy66-floating-tool-window-non-modal-stay-on-top-opened-by-mount-22), [03 §1.17](03-observe-page.md#117-manual-control-dialog-manualcontroldialog-manual_control_dialogpy66-tool-window-non-modal-stay-on-top-fixed-280-x-320-title-manual-control) |
| M67 | Dock chrome of the hardware docks imaging_page.py:280-294, 348-414 | chips, menus, title bars | Card fold (persisted), `P`, drawer tabs | [05 §1.9](05-hardware-controls.md#19-dock-chrome-for-these-panels-ip280-294-348-414-dock_hostpy48-75-shared-with-the-observe-layout-spec) |

### 2.4 Plan

| # | Qt element (file:line) | Kind | Web destination | Spec |
|---|---|---|---|---|
| M68 | `SequencerPage` sequencer_page.py:24 (heading 47) | page | Plan screen; heading row **dropped** | [06 §1.1](06-plan-sequencer.md#11-sequencerpage-pg24-page-opened-by-sidebarf3-non-modal-full-content-area) |
| M69 | Panel toolbar sequence_panel.py:512-531 (5 chips, Reset panels) | toolbar | Card fold + Panels popover (`arrange`) + Settings "Reset all layouts" | [06 §1.2](06-plan-sequencer.md#12-panel-toolbar-sp512-531-qtoolbar-top-of-page-always-visible) |
| M70 | Five docks sequence_panel.py:489-500 | docks | Fixed regions and cards; floating **dropped** | [06 §1.3](06-plan-sequencer.md#13-dock-frames-sp489-500-via-make_dock-dock_hostpy48-119) |
| M71 | Steps table + edit row sequence_panel.py:222-271, 678-783 | table | Steps region (Cadence and Duration columns, explicit selection, totals, end time) | [06 §1.4](06-plan-sequencer.md#14-steps-table-and-edit-row-sp222-271-central-widget-always-visible) |
| M72 | Scientific source dock, stacked Variable / Exoplanet pages, two `QCompleter` pop-ups sequence_panel.py:274-448 | dock + pop-ups | Source card: programme segmented, one search field with token-drawn suggestion list, transit sub-form | [06 §1.5](06-plan-sequencer.md#15-scientific-source-dock-sp274-448-dock-scientific-source) |
| M73 | Acquisition options dock sequence_panel.py:302-337 | dock | Run options card | [06 §1.6](06-plan-sequencer.md#16-acquisition-options-dock-sp302-337-dock-acquisition-options) |
| M74 | `TargetVisibilityPlot` sequence_panel.py:96 (+ pyqtgraph menu 105) | dock plot | Visibility timeline (centre, full width), menu **dropped** | [06 §1.7](06-plan-sequencer.md#17-target-visibility-dock-sp96-171-339-343-dock-target-visibility) |
| M75 | Presets dock sequence_panel.py:450-461 | dock | Toolbar Presets popover (server list) + Save popover | [06 §1.8](06-plan-sequencer.md#18-presets-dock-sp450-461-dock-presets-tabbed-behind-19) |
| M76 | Sequence control dock sequence_panel.py:463-487 | dock | Toolbar transport + readiness chip -> Preflight popover + run strip | [06 §1.9](06-plan-sequencer.md#19-sequence-control-dock-sp463-487-dock-sequence-control) |
| M77 | Save / Load preset dialogs sequence_panel.py:899, 913 | OS dialogs | Presets popover (server presets folder) + FilePicker for "Open file…" / "Save as file…" | [06 §1.10](06-plan-sequencer.md#110--111-preset-file-dialogs-sp899-sp913-modal-native-qfiledialog) |
| M78 | `VariableTable` variable_table.py:58 (Field photometry tab) | tab table | Observe drawer **Variables** tab (D7) | [06 §1.12](06-plan-sequencer.md#112-variabletable-vt58-tab-variable-stars-of-the-field-photometry-window), [08 §1.5](08-review-photometry.md#15-variable-stars-tab-variabletable-variable_tablepy58-tab-of-w1-cross-reference-observe-spec) |
| M79 | `TargetTable` target_table.py:27 (Field photometry tab) | tab table | `TargetSetList` in Observe Photometry card and Plan Target set card (D24) | [06 §1.13](06-plan-sequencer.md#113-targettable-tt27-tab-targets-of-the-field-photometry-window), [08 §1.4](08-review-photometry.md#14-targets-tab-targettable-target_tablepy27-tab-of-w1-cross-reference-observe-spec) |

### 2.5 Review

| # | Qt element (file:line) | Kind | Web destination | Spec |
|---|---|---|---|---|
| M80 | `AnalyzeScreen` analyze_page.py:59 (heading, scroll area) | page | Review R1 (R0 landing when nothing is open) | [07 §1.1](07-review-analysis.md#11-review-page-shell-toolbar-and-menus-analyzescreen-ap59-page-in-the-shell-stack-non-modal-full-page), [08 §1.10](08-review-photometry.md#110-review-page-analyzescreen-analyze_pagepy59-page-in-the-main-window-rail-f4) |
| M81 | Session card analyze_page.py:133-155 | card | R1 toolbar identity + readiness badge (issues popover) + Session rail card | [07 §1.1](07-review-analysis.md#11-review-page-shell-toolbar-and-menus-analyzescreen-ap59-page-in-the-shell-stack-non-modal-full-page) |
| M82 | Review panel toolbar analyze_page.py:252-300 (Open session, Open curve CSV, Open FITS, + Comparison plot below, 7 chips, Tile, Reset) | toolbar | R1 toolbar; opens move to R0; "+ Comparison plot below" **dropped** (D4); Tile -> Panels popover columns (`layout-tile`) | [07 §1.1](07-review-analysis.md#11-review-page-shell-toolbar-and-menus-analyzescreen-ap59-page-in-the-shell-stack-non-modal-full-page) |
| M83 | Review "Panels ▾" analyze_page.py:278-285 | popup menu | Panels popover (`arrange`) | [07 §1.1](07-review-analysis.md#11-review-page-shell-toolbar-and-menus-analyzescreen-ap59-page-in-the-shell-stack-non-modal-full-page) |
| M84 | Review "Arrange ▾" analyze_page.py:287-294, 427-446 | popup menu | Panels popover (facets, columns, Reset layout); Float **dropped** | [07 §1.1](07-review-analysis.md#11-review-page-shell-toolbar-and-menus-analyzescreen-ap59-page-in-the-shell-stack-non-modal-full-page) |
| M85 | Review workspace (nested docks) analyze_page.py:81-108 | dock area | Plot wall grid (2 columns, 3 with the rail collapsed) | [07 §1.1](07-review-analysis.md#11-review-page-shell-toolbar-and-menus-analyzescreen-ap59-page-in-the-shell-stack-non-modal-full-page) |
| M86 | Source light curve docks (`TargetCurvePanel` target_curve_panel.py:14 + `LightCurvePanel` + point row analyze_page.py:169-183) | docks | Target / check facets (selector **dropped**, D4) + Selected point card with Open frame | [07 §1.2](07-review-analysis.md#12-source-light-curve-docks-e7-targetcurvepanel-tcp14--lightcurvepanelviewtarget-lp25--point-row-ap169-183-non-modal-dock), [08 §1.11](08-review-photometry.md#111-targetcurvepanel-target_curve_panelpy14-content-of-p1d1--p1d1) |
| M87 | Comparison docks (`ComparisonCurvePanel` comparison_curve_panel.py:14) | docks | One comparison facet each (selector and "All comparison stars" **dropped**) | [07 §1.3](07-review-analysis.md#13-comparison-star-docks-e8-comparisoncurvepanel-ccp14--lightcurvepanelviewcomparison-non-modal-dock), [08 §1.12](08-review-photometry.md#112-comparisoncurvepanel-comparison_curve_panelpy14-content-of-p1d3--p1d3) |
| M88 | Frame quality dock (`SessionQualityPlot` session_review.py:21) + its pyqtgraph menu | dock plot | Conditions facet (D6); menu dropped (copy data from the cell menu) | [07 §1.4](07-review-analysis.md#14-frame-quality-dock-e9-sessionqualityplot-sr21-dock-frame-quality--fwhm-ap202), [08 §1.14](08-review-photometry.md#114-sessionqualityplot-session_reviewpy21-content-of-p1d2) |
| M89 | Comparison quality dock (`ComparisonQualityTable` comparison_table.py:208) | dock table | Ensemble rail card (compact) + Ensemble drawer tab (all columns) (D5) | [07 §1.5](07-review-analysis.md#15-comparison-quality-dock-e10-comparisonqualitytable-ct208-tabbed-right-raised-by-default), [08 §1.13](08-review-photometry.md#113-comparisonqualitytable-comparison_tablepy208-content-of-p1d4) |
| M90 | Frames dock analyze_page.py:186-192 | dock table | Drawer Frames tab (read-only, double-click -> R2) | [07 §1.6](07-review-analysis.md#16-frames-dock-e11-qtablewidget0-9-ap186-192-bottom-hidden-by-default) |
| M91 | Session metadata dock analyze_page.py:193-196 | dock table | Session rail card (folded, read-only, copy) | [07 §1.7](07-review-analysis.md#17-session-metadata-dock-e12-qtablewidget0-2-ap193-196-tabbed-right-hidden-by-default) |
| M92 | AAVSO export dock analyze_page.py:118-131 | dock card | AAVSO export rail card + Export AAVSO dialog | [07 §1.8](07-review-analysis.md#18-aavso-export-dock-e13-designcardaavso-export-ap118-131-tabbed-right-hidden-by-default) |
| M93 | Floating dock windows dock_host.py:68-74 | windows | **Dropped** in v1 (D27) | [07 §1.1](07-review-analysis.md#11-review-page-shell-toolbar-and-menus-analyzescreen-ap59-page-in-the-shell-stack-non-modal-full-page) |
| M94 | Review dialogs and boxes analyze_page.py:606 (session folder), 614 (could not open), 717 (frame unavailable), 733 (CSV), 766 (FITS) | modal | R0 Sessions list + FilePicker; errors as toasts / inline states | [07 §1.9](07-review-analysis.md#19-review-file-dialogs-and-message-boxes-ap) |
| M95 | `PhotometryWindow` photometry_window.py:200 (banner, 6 tabs, export footer 240-244, save dialogs 306, 316) | top-level window | **Dissolved** (D8): Variables -> Observe drawer; Light curve -> Observe drawer + Review; Metrics -> Conditions; Targets -> `TargetSetList`; Comparison stars -> Observe Ensemble tab + Photometry card actions; Aperture · references -> Settings › Photometry; exports -> Review dialogs; banner -> R1 "Preview" chip | [08 §1.1](08-review-photometry.md#11-photometrywindow-field-photometry-photometrywindow-photometry_windowpy200-top-level-window-non-modal-separate-os-window), [07 §1.10](07-review-analysis.md#110-field-photometry-window-e22-photometrywindow-pw200-top-level-non-modal-as-opened-from-review) |
| M96 | `LightCurvePanel` lightcurve_panel.py:25 (checkboxes, legend click, auto-range "A") | plot widget | Shared `LightCurvePlot` (Observe drawer, Review facets); global U / M toggles; legend click and "A" replaced by facet visibility and Fit (F) | [08 §1.2](08-review-photometry.md#12-light-curve-tab-and-every-live-curve-lightcurvepanel-lightcurve_panelpy25-widget-view-both-in-w1-and-in-the-capture-dock-x1-target--comparison-inside-111--112) |
| M97 | `ComparisonEnsembleTable` comparison_table.py:54 (Remove, Refresh catalogue, Recommend, auto count) | tab table | Observe Ensemble drawer tab + Photometry card actions; read-only copy in Review (D3) | [08 §1.6](08-review-photometry.md#16-comparison-stars-tab-comparisonensembletable-comparison_tablepy54-tab-of-w1) |
| M98 | `PhotometrySetupPanel` photometry_window.py:36 | tab form | Settings › Photometry (+ read-only effective geometry on the Photometry card) | [08 §1.7](08-review-photometry.md#17-aperture--references-tab-photometrysetuppanel-photometry_windowpy36-tab-of-w1) |
| M99 | "Differential photometry" dock imaging_page.py:301-306 | dock | Observe drawer Light curve tab (target + check, D25) | [08 §1.8](08-review-photometry.md#18-entry-points-outside-the-window-shellpy-imaging_pagepy) |
| M100 | `AnalysisWindow` "Frame Viewer" analysis_window.py:136 (3 tabs, bottom bar, open dialog 441) | top-level window | Review **R2 Frame inspector** | [07 §1.11](07-review-analysis.md#111-frame-viewer-window-e24-analysiswindow-aw136-top-level-qmainwindow-non-modal-min-900640) |
| M101 | Frame Viewer catalogue settings entry analysis_window.py:564-569 | modal dialog | Settings › Catalogues sheet from the R2 Catalogue layers popover | [07 §1.12](07-review-analysis.md#112-catalogue-settings-dialog-as-opened-from-the-frame-viewer-e26-astrometrysettingsdialogsectioncatalog-as48-modal) |
| M102 | Frame Viewer image context menu (pyqtgraph, fits_viewer.py:138) | context menu | Viewer context menu in inspect mode (no role items) | [07 §1.11](07-review-analysis.md#111-frame-viewer-window-e24-analysiswindow-aw136-top-level-qmainwindow-non-modal-min-900640), [04 §1.2](04-viewer-and-image-tools.md#12-viewer-context-menu-pyqtgraph-viewboxmenu--scene-export-right-click-non-modal-popup) |
| M103 | Shell entry points into Review shell.py:197-201, 228-232 | menu actions | NavRail Review (F4), ⌘/Ctrl+Shift+O -> R0 | [07 §1.14](07-review-analysis.md#114-shell-entry-points-into-review-e30) |


---

## 3. Cross-cutting UI patterns (build once)

### 3.1 Shared components

Existing ones (`web/src/lib/components/*`, `lib/shell/*`) are extended, not duplicated.

| Component | Status | Used by | Notes |
|---|---|---|---|
| `Icon`, `IconButton`, `tooltip` | exists | everywhere | Tooltip = label + shortcut from the registry (§3.10); `aria-keyshortcuts`. |
| `Card` (fold, `persist`) | exists | every rail | Header may carry a status badge and a summary when folded (Photometry, Focuser). |
| `NumberField`, `TextField`, `Segmented`, `StatusBadge` | exist | forms, cards | `NumberField` gains unit suffix, range from config meta, error slot. |
| `Select` / `Listbox` | **new** | filter, frame type, profile, presets, suggestions | Token-drawn, never a native `<select>` (Night Red). |
| `Menu` (context and dropdown) | **new** | viewer context menu, cell menu, Presets, Help | Keyboard: arrows, Enter, Esc, type-ahead. |
| `Popover` | **new** | Catalogue layers, Panels, Discovery results, Preflight, readiness issues, Recommend | 260-360 px, anchored, closes on outside click and Esc, focus returns to the trigger. |
| `Dialog` + `ConfirmDialog` | **new** | every modal (§3.2, §3.3) | Replaces the 12 `QMessageBox`; the three Qt `QDialog`s become Settings › About, Settings sheets and the Mount jog pad (§2). |
| `Sheet` | **new** | Settings category forms over Observe / R2 | Right side, 560 px, modal, hosts the same `SettingsForm`. |
| `SettingsForm` | **new** | Settings, sheets | Generated from `GET /api/config` meta (type, range, unit, default, help). |
| `FilePicker` | **new** | 18 Qt `QFileDialog` sites | §3.6. |
| `Table` | **new** | Devices, Steps, Variables, Ensemble, Frames, Sessions, caches, saved sites, FITS header | §3.5. |
| `Drawer` with tabs | extend `LogDrawer` | Observe, Plan, Review, (Log everywhere) | Height handle, tab persisted, unseen-problem badge per tab. |
| `PanelsPopover` | **new** | Observe, Plan, Review | Lists rail cards, drawer tabs, plot facets; Reset layout. |
| `JobProgress` (inline row + job strip) | **new** | discovery, re-run, exports, session open, file solve / catalogues, support bundle | §3.7. |
| `Toasts` | extend | everywhere | Actions (Undo, Reveal, Open), merge repeats, never the only carrier of information. |
| `LightCurvePlot`, `ConditionsTimeline`, `VCurvePlot`, `VisibilityTimeline`, `Histogram` | new / exists (`Histogram`) | Observe, Plan, Review | uPlot (already a dependency), tokens read at draw time, redraw on theme change (§3.13). |
| `TargetSetList` | **new** | Observe Photometry card, Plan Target set card | Role glyph, name, source, magnitude; remove with Undo. |
| `FitsViewer` (+ overlay layer, star card, loupe, region tool, context menu) | extend | Observe, R2 (`mode="inspect"`) | Overlay coordinates in un-rotated frame px (numpy convention), rotation applied by the viewer. |
| `StartupScreen`, `HelpPopover`, `ShortcutSheet`, `SupportBundleDialog`, `QuitDialog` | **new** | shell | 01 §2.3. |

### 3.2 Dialogs, sheets, popovers

- **Dialog**: modal, width 480 (confirm) / 560 (form) / 640 (pickers), title is the question or
  the task ("Park the mount?", "Export AAVSO"), body text `--fg`, buttons text-only
  (BRAND 7), primary on the right, `Esc` = Cancel (and still aborts motion, D21). One modal
  at a time; a `ConfirmDialog` may stack once over a sheet or a form dialog.
- **Sheet**: for "edit settings without leaving the image" (D12). Changes apply on commit;
  closing the sheet triggers the dependent refresh (catalogue refetch).
- **Popover**: no OK button; changes apply at once; never contains a destructive action
  without a confirmation.
- **No OS dialog, alert or notification** in any build (Night Red, BRAND 4.3); Tauri native
  dialogs only if the owner asks (Q-G7), never in Night Red.

### 3.3 Confirmations (hardware and destructive actions)

| Action | Confirmation | Form | Default focus |
|---|---|---|---|
| Park | yes | inline in the Mount card (built): "Parking physically closes the Seestar arm and stops tracking." [Cancel] [Park] | Cancel |
| Disconnect all / a device while a sequence, exposure, autofocus or slew runs | yes | `ConfirmDialog` 02 W10b; no confirmation when idle | Cancel |
| Stop sequence | yes | `ConfirmDialog` 06 §2.3.6: says what is discarded and saved, [Keep running] [Stop] | Keep running |
| Quit while busy (desktop) | yes | `QuitDialog` (01 §2.3.7), lists what runs | Cancel |
| Remove a comparison or the target during a run | yes | `ConfirmDialog` (08 §2.3 G); otherwise immediate + Undo toast | Cancel |
| Replace comparisons (Recommend, mode replace) during a run | yes | inside the Recommend popover | Cancel |
| Clear a catalogue cache | yes | `ConfirmDialog` 02 W10a | Cancel |
| Replace an unsaved plan (open preset, prepare transit), overwrite a preset | yes | `ConfirmDialog` | Cancel |
| Sync to plate solution (if kept, Q-O3) | yes | inline in the Mount card | Cancel |
| Export AAVSO with no observer code | blocked | inline in the dialog with a link to Settings (Q-R2) | — |
| GoTo / Slew, Centre target, Abort, tracking on / off, unpark, live, capture, autofocus start, connect, reset layout, remove a step or a saved site | **no** | deliberate labelled buttons; reversible actions use an Undo toast (6 s) | — |

Rules: hardware actions are never on a single key (exceptions: jog arrows, `Esc` abort);
they are icon + label (BRAND 7), show busy (`aria-busy`, spinner, width unchanged), are
disabled with the reason in the tooltip when the server would refuse (not connected,
parked, clock error, camera owned by the sequence), and the server stays the authority
(a `409` reason is shown verbatim in a toast and the log).

### 3.4 Forms and validation

| Rule | Detail |
|---|---|
| Save model | **Settings and sheets**: immediate apply on commit (Enter / blur for text and numbers, change for toggles and segmented), one `PATCH /api/config` per commit, "Saved" for 2 s in the header. **Dialogs** (export, re-run, support bundle, preset save): draft then submit. **Device fields** (exposure, gain, offset, binning, filter): commit then `PUT`, never per keystroke (fixes 05 P28, 02 host-per-keystroke). |
| Ranges and units | From config meta or device state (`limits`), mono digits, unit suffix, BRAND 5 formats; out-of-range input shows a message under the field and is **never clamped silently** (06 P11, 05 P6). |
| Server errors | Field keeps the rejected text, message in words under it (`--danger` outline, label `--fg`), `Esc` reverts. |
| Sync | `config` WS event updates every bound control; a field being edited is not overwritten, it shows "Changed elsewhere · Reload". |
| Dependent controls | Disabled with the reason while their parent is off (Gaia, SIMBAD, NASA network toggles; transit fields; Dark slot rows). |
| Paths | Validated by the server: "does not exist, will be created" (warning) vs "not writable" (error); picked with `FilePicker`. |
| Coordinates | Sexagesimal or decimal accepted (exists in `format/astro.ts`), echoed in canonical format after commit. |

### 3.5 Tables

One `Table` component: 24 px rows, sticky header, numeric columns right-aligned in Plex
Mono with fixed decimals, text left; single-row selection (click, ↑ ↓, Home / End); Enter
activates the row's default action; `⌘/Ctrl+C` copies the selection (or the table) as TSV;
sortable headers with the new `sort` icon (§5), sort persisted per table; column visibility
menu for wide tables (Frames, Ensemble), persisted; virtualised above 500 rows (Frames,
Gaia lists); empty state as a single row in `--text-muted`. Tables are **read-only**
(fixes 07 P11); the Plan Steps table is the only editable one and uses explicit cell
editors that ignore the mouse wheel unless focused (06 P27).

### 3.6 File pickers (browser and Tauri)

- One in-app `FilePicker` dialog (01 §2.3.12, 03 W7, 02 W11): breadcrumb, Places (Sessions,
  Presets, Home, last used), list with name / size / modified (and FITS count for folders
  when picking a frames folder), path field accepting a typed absolute path, type filter,
  [Cancel] [Open | Choose folder | Save]. Modes: open file, open folder, save file
  (collision -> inline "Replace?" choice), executable.
- Backed by `GET /api/fs/list` (token, localhost only, read-only listing of the user's home
  and configured data paths; anything else only by an explicitly typed path).
- The 18 Qt sites (01 A.2) map to it, except the support-bundle session chooser (a session
  select fed by `GET /api/sessions`) and the Review session folder (R0 list first).
- Drag-and-drop of a FITS onto the Observe viewer (desktop app) opens it (new, 01 A.7).

### 3.7 Long-running work: progress and cancel

| Duration | Pattern |
|---|---|
| < 2 s (most commands) | Button busy (spinner replaces the glyph, `aria-busy`), result applied from the REST answer, WS echo follows (existing runner). |
| 2 s - minutes, one-off (discovery, place search, file solve, file catalogues, session open, re-run, exports, support bundle) | **Generic job** (API §4.2): `POST` -> `202 {job_id}`; inline `JobProgress` row where it was started (determinate bar when `total` is known, stage text), `[stop Cancel]` when cancellable; Review uses a job strip in the toolbar; completion -> toast with an action (Open, Reveal) + log line; failure -> error toast + log + inline message where it applies. |
| Stateful runs (live view, sequence, autofocus, live field solve, catalogue fetch, filter move, slew, jog, focuser move) | Domain events (`sequence`, `autofocus`, `field`, `catalog`, `filterwheel`, `mount`, `focuser`); status-bar run chip for sequence / live / AF / re-run; rail dots (01 §2.4.4); the owning card shows stage and progress. |
| Reconnect | The client re-reads `GET /api/jobs` and the status record; progress resumes, nothing is lost when the page reloads. |

### 3.8 Toasts, log and activity

- **Log** (one store, server ring buffer + `GET /api/logs` replay): levels DEBUG (hidden by
  default), CMD, INFO, OK, WARN, ERROR (`--log-*` tokens exist), UTC timestamps, `source`
  and `topic` fields; level filter, search, copy visible, save as text, clear (view only),
  cap 5 000 lines client side, no forced scroll while the user reads (fixes 01 P28-P30).
- **Toasts**: every failed user action (API error) = error toast + log line (exists);
  background failures (auto-solve every 20 s) = log only; successes of long jobs = toast with
  action; reversible removals = toast with Undo; repeats merge with a count; toasts never
  carry information found nowhere else (BRAND 7).
- **Activity text** (status bar, right): last action with time, full text in the tooltip,
  every change also logged (fixes 01 P25).

### 3.9 Empty, loading, error and disconnected states

| State | Pattern |
|---|---|
| Server link down / token rejected | Status-bar connection item in warning tone; last known data kept read-only; every action disabled with "the ARGOS server is not reachable" (exists). |
| Not connected | Device-dependent controls disabled with "connect the equipment first"; fields stay editable for planning; Observe empty state offers Connect and `[open-image Open FITS image]`. |
| Prerequisite missing | Disabled with the reason in the tooltip, never a modal after the click: "identify the field first (S)", "set the observing site in Settings", "assign a target star first" (fixes 03 P11). |
| Empty data | One line in `--text-muted` saying what will appear and how ("No sessions in ~/Argos/sessions. Open folder… / Import CSV…"). |
| Loading | Skeleton rows or axis frames, `aria-busy`; never a blank white area (Night Red). |
| Partial | Badge with count ("3 issues") + popover listing them; warning tone only when it is a warning (fixes 07 P5). |
| Error | Exact server text inline where the action was taken + toast + log; previous content stays (07 P28). |

### 3.10 Keyboard shortcut map (single registry, conflict-free)

Single-key shortcuts fire only when focus is not in a text field, never move hardware
(exceptions: jog arrows, `Esc`), and come from **one registry** that also feeds tooltips,
`aria-keyshortcuts` and the `?` sheet. The matcher must accept ⌘ / Ctrl / Alt modifiers
(today `matchesShortcut` rejects them, `web/src/lib/app/shortcuts.ts:64`); letters match
`KeyboardEvent.key` (layout aware), digits also match `KeyboardEvent.code` `DigitN` so that
`1` works on AZERTY without Shift.

| Key | Action | Scope | Origin |
|---|---|---|---|
| F1 … F5 | Connection, Observe, Plan, Review, Settings (also from text fields) | global | Qt |
| ⌘/Ctrl+1 … 5 | same (macOS needs Fn for F-keys) | global, desktop app | proposed (Q-G9) |
| ⌘/Ctrl+O | Open FITS image (Review -> R2, elsewhere -> Observe) | global | Qt (D19) |
| ⌘/Ctrl+Shift+O | Review R0 Sessions | global | Qt |
| ⌘/Ctrl+, | Settings | global | proposed |
| ⌘/Ctrl+Q | Quit (desktop app) | global | Qt |
| ? | Keyboard shortcuts sheet | global | proposed |
| L | Drawer on the Log tab (toggle) | global | proposed (D22) |
| D | Drawer open / close (last tab) | Observe, Plan, Review | proposed |
| P | Right rail open / close | Observe, Plan, R1, R2 | built |
| / | Focus the section search (Plan source, Settings filter, R0 filter, Variables filter when its tab is open) | section | proposed |
| Esc | Abort slew / jog / manual focuser move if moving, and close the topmost layer (D21) | global | built + Qt |
| E | One exposure | Observe | built |
| V | Live view on / off | Observe | built |
| + / − | Zoom in / out (R1: time axis) | Observe, R1, R2 | built |
| F | Fit (R1: fit all plots) | Observe, R1, R2 | built |
| 1 | Actual pixels (1:1) | Observe, R2 | built |
| A / Shift+A | Auto stretch / reset stretch | Observe, R2 | built |
| H | Display card | Observe, R2 | built |
| X | Crosshair | Observe, R2 | built |
| Z | Loupe | Observe, R2 | inventory |
| C | Saturation highlight | Observe, R2 | proposed (04) |
| R | Region statistics | Observe, R2 | proposed (04) |
| I | Statistics card | Observe, R2 | proposed (04) |
| S | Identify field | Observe, R2 | inventory |
| G | Coordinate grid | Observe, R2 | inventory |
| N | Object labels | Observe, R2 | changed from proposed L (D22) |
| O | Catalogue layers popover | Observe, R2 | proposed |
| J | Arm / disarm keyboard jogging | Observe | proposed (05) |
| ← ↑ → ↓ (hold) | Jog W N E S while armed or while the pad has focus | Observe | Qt (Manual Control) |
| U | Error bars | R1 | proposed (08) |
| M | Magnitude / relative flux | R1 | changed from proposed R (D22) |
| ← / → | Previous / next point of the selected series | R1 | proposed |
| Enter | Open the frame of the selected point or row | R1, R0 | proposed |
| PageUp / PageDown | Previous / next frame of the session | R2 | proposed |
| Alt+← | Back from R2 to R1 | R2 | proposed |
| Insert, ⌘/Ctrl+D, Delete, Alt+↑ / ↓, Space | Add, duplicate, remove (Undo), move, enable a step (focus in the Steps table) | Plan | proposed (06) |
| ⌘/Ctrl+S | Save preset | Plan | proposed |
| ⌘/Ctrl+C | Copy the focused table as TSV | any table | proposed |
| Tab, Enter, Space | Standard focus and activation | all | Qt |

Not bound on purpose: tracking (`T`), autofocus, focus steps (`[` `]`), roles on the star
card, start / pause / stop sequence, connect / disconnect (BRAND 7; Q-O7).

### 3.10.1 Rail state dots

As 01 §2.4.4: Connection ready = mount and camera connected, active = discovering /
connecting, attention = a device in error or server link lost; Observe ready = camera
connected, active = live, exposure, autofocus or slew (no amber at launch, fixes 01 P18-P19);
Plan active = sequence running, attention = stopped on an error; Review active = re-run or
export job; Settings attention = observer code or site missing (Q-G11).

### 3.11 Persistence of preferences

| What | Where | Keys |
|---|---|---|
| Science, paths, catalogue, photometry, privacy settings | server config (shared with Qt during the transition) | `site.*`, `observer.*`, `astrometry.*`, `catalog.*`, `photometry.*`, `data_paths.*`, `ui.log_level`, … (02 appendix A) |
| Capture state: exposure, gain, frame type, filter, offset, binning, object | server state (shared by every client, survives reload) | status record (Q-O13) |
| Sequence draft, presets | server (`sequence_draft.json`, presets folder) | Q-P3 |
| Display depth, star aperture | server config | `catalog.display_mag_limit`, `imaging.star_radius_px` (new) |
| Theme | per viewer, before first paint | `argos.theme` (exists); seeded once from `ui.theme.preset` |
| Rotation | per viewer | `argos.rotation` (exists); seeded once from `ui.display.rotation` |
| Section, rail, cards, drawer | per viewer | `argos.section`, `argos.rail-open` (exists), `argos.rail-width.<section>`, `argos.card.<id>` (exists), `argos.layout.<section>.<panel>`, `argos.drawer.<section>` (open, tab, height) |
| Viewer tools | per viewer | `argos.view.preview`, `.palette`, `.crosshair`, `.loupe`, `.saturation`, `.region`, `.stats`, `.card-pos`, `argos.layers.<layer>` |
| Tables | per viewer | `argos.table.<id>` (sort, hidden columns) |
| Review | per viewer | `argos.review.last`, `.time-axis`, `.errors`, `.flux`, `.facets`, `.columns` |
| Settings / Connection conveniences | per viewer | `argos.settings.category`, `argos.settings.help`, `argos.connection.log` |
| Window size and position | Tauri window-state plugin | — |

All browser-storage access stays wrapped in try / catch (`prefs.ts`) and the UI renders
correctly without it. "Reset layout" clears `argos.layout.<section>.*`,
`argos.drawer.<section>`, `argos.rail-width.<section>`; "Reset all layouts" clears them for
every section and the Tauri window state, keeping theme, rotation and science settings.
Dropped Qt keys: `ui.shell.state`, `ui.imaging.layout`, `ui.sequencer.layout`,
`ui.review.layout`, `ui.window_state`, `ui.window_geometry`, `ui.language`.

### 3.12 Night Red rules for every component

Token colours only; image as `v x --viewer-tint`; saturated pixels black; only the Neutral
palette (D30); plots single-hue, series told apart by marker shape and direct labels;
every status double-coded by a word or icon; custom menus, selects, pickers and scrollbars;
no OS dialog, notification or native context menu; no Unicode pictographs (the Qt labels'
⚡ ▶ ■ ◉ ⟳ ⊙ ✥ ↑ ↓ ＋ ⧉ － become icons); no white flash at start-up.

### 3.13 Plots

uPlot everywhere; BRAND 10: at most three series per plot (facet otherwise), one y axis
(no dual axes, fixes 05 P11), magnitude inverted, time named (UTC / JD / BJD), legend in the
header never over the data, hover value tooltip in mono, no pan / zoom menus (Fit `F` and
`+ / −` on the time axis instead), new data never resets a manual zoom, "Copy data (TSV)"
in the cell menu instead of pyqtgraph Export. No brass for data (07 P39).


---

## 4. API v2 (consolidated)

### 4.1 Conventions (additive to `argos/server/protocol.md`, API 1)

- **Additive**: v1 routes and records stay; `GET /api/health` reports `"api": 2` once a
  wave's routes ship. Bodies stay strict; errors keep `{"error": {code, message}}` and the
  v1 codes; new codes: `busy` (with `owner`), `not_solved`, `no_target`, `no_comparison`,
  `no_frames`, `site_missing`, `run_active`, `not_found`, `session_invalid`, `unsupported`.
  A `409` message is written for the observer and shown verbatim.
- **Names and units**: `ra_hours`, `dec_deg` everywhere (03 used `dec_degrees`, 06 `ra_deg`:
  unified); times ISO 8601 UTC (`t`, `*_utc`); JD fields named `jd_utc`, `bjd_tdb`;
  positions in **frame px, numpy convention, un-rotated** (04 §2.5); the server converts
  from the green plane (×2 on the G1 grid, exact offset to verify, 03 U2); radii carry
  their unit (`r_px`, `radius_green_px`).
- **Events**: `/ws/events` messages `{"type": …}`. Snapshot types (`status`, `devices`,
  `network`, `field`, `catalog`, `targets`, `observation`, `sequence`, `autofocus`,
  `focuser`, `filterwheel`, `stellarium`, `config`) are compacted to the newest under
  backpressure (as v1). Stream types (`log`, `frame_saved`, `frame_metrics`,
  `photometry_point`, `conditions`, `job`) carry a monotonically increasing `seq` or
  `revision`; a client that sees a gap re-reads the matching REST snapshot.
- **Off the event loop**: every Alpaca call, file scan, ASTAP run, catalogue query and
  photometry pass runs in a worker thread (fixes the Qt UI-thread calls, 02, 03 P16, 05 P27).
- **Qt-free**: logic that lives in Qt pages today must move to `argos/core` or
  `argos/server` services (the server forbids Qt, `tests/server/test_no_qt.py`): hit-test and
  card bodies (`imaging_page.py:793-1284`), overlay projection (`:1483-1769`), session
  metrics (`:2370-2439`), science source (`:2657-2720`), batch pre-checks (`:2248-2318`),
  network monitor (`network_monitor.py`, a `QThread`), Frame Viewer projection
  (`analysis_window.py:588-858`).

### 4.2 Long-running job model

| Item | Rule |
|---|---|
| Start | `POST` on the domain route returns `202 {"job_id"}` (or `409 busy` when a job of the same kind on the same resource runs). |
| Progress | WS `{"type":"job","job":{id, kind, state: queued\|running\|done\|failed\|cancelled, done, total\|null, stage, message, started_utc, ended_utc, result\|null, error\|null, seq}}`, throttled to ≤ 4 Hz, final message always sent. |
| Cancel | `DELETE /api/jobs/{id}`: honoured at a safe boundary (between frames, between devices, kill the ASTAP process); `409 unsupported` when the kind cannot be cancelled. |
| Recover | `GET /api/jobs` (active + last 20), `GET /api/jobs/{id}` (result kept 10 min). |
| Kinds | `discovery`, `site_search`, `support_bundle`, `sessions_scan`, `session_open`, `file_solve`, `file_catalogue`, `rerun`, `export` |
| Not jobs | Stateful singletons keep their domain events: live view, capture, sequence, autofocus, live field solve, live catalogue fetch, point identification (`selection`), filter move, slew, jog, focuser move. |

### 4.3 Routes and events

Priority: **P0** foundation (waves 1-2), **P1** observing parity (waves 3-6), **P2**
analysis, export and comfort (waves 6-8). "Merges" names the duplicate proposals folded
into the row.

| # | Route / event | Payload sketch | Wraps (core / worker code) | Long / cancel | Prio | Wave | Merges |
|---|---|---|---|---|---|---|---|
| **App, log, diagnostics** | | | | | | | |
| A1 | `GET /api/app/info` | version, api, platform, paths {config, sessions, presets, diagnostics, log_file}, profile, log_level, diagnostics_enabled, astap_configured, licence, credits, project_url, docs_url | `argos/__init__.py:9`; `config.py:16-17, 268-270`; `support_bundle.py:56-64`; `shell.py:67, 511-516, 535-600` | instant | P0 | 1 | 01 App info, 02 About |
| A2 | WS `log` v2 + `GET /api/logs?after=&limit=` | `{id, seq, level: debug\|cmd\|info\|ok\|warning\|error, source, topic, message, t}`; ring buffer 5 000, replay extends the v1 200-line replay | 148 `log_message.emit` sites (levels CMD, INFO, OK, WARN, ERROR); `server/hub.py:156-163` | — | P0 | 1 | 01 Log stream v2, 02 Log topics, 03 Log levels |
| A3 | Server behaviour: rotating file log, crash reporter, data paths applied at start-up | honours `ui.log_level`; cache and calibration dirs configured before the first request | `support_bundle.py:67-147`; `configuration_page.py:823-824, 1040-1084`; `server/__main__.py:70-99` | — | P0 | 1 | 01, 02 Start-up configuration |
| A4 | WS `activity` | `{text, source, t}` | `imaging_page.py:126-132, 2848`; `astrometry_controller.py:85-216`; `device_session.py:238-463`; `exposure_worker.py:114-149` | — | P1 | 1 | 01, 03 |
| A5 | `POST /api/support-bundle` (job `support_bundle`) | `{destination\|null, session_dir\|null, include_session: false}` -> result `{path, files[]}`; browser: `GET /api/jobs/{id}/download` | `support_bundle.py:162-221` | seconds, not cancellable | P2 | 2 | 01, 02 |
| A6 | `GET /api/diagnostics/crash-reports?since=` | `[{path, t, summary}]` | `support_bundle.py:104-147` | — | P2 | 2 | 01 |
| A7 | `POST /api/app/shutdown` + WS `shutdown` | `{force: bool}` -> `409 busy {what[]}` unless forced; stages | `shell.py:611-625`; `acquisition_engine.py:1607-1650`; `device_session.py:822-831`; `server/hub.py:278` | bounded budget | P1 | 8 | 01 Graceful shutdown, 01 Busy summary |
| **Config and files** | | | | | | | |
| A8 | `GET /api/config` | `{values, meta: {key: {type, default, min, max, step, options, unit, help, used_by}}}` | `config.py:19-176, 231-239` | — | P0 | 1 | 02, 04 A15, 07 Config subset, 08 Photometry settings |
| A9 | `PATCH /api/config` | partial `{key: value}` -> `{values, warnings}`; side effects: cache dirs, calibration dir, diagnostics marker, log level live, `catalog.*` -> debounced field refetch, `imaging.star_radius_px` -> re-process last frame, photometry geometry -> `409 run_active` while a sequence runs (Q-R10) | `config.py:241-248`; `configuration_page.py:1040-1084, 1200-1206`; `support_bundle.py:67`; `preview_processor.py:121-123`; `acquisition_engine.py:815-832, 1222-1233` | — | P0 | 1 | 02, 03 Display depth / radius, 04 A3, 08 |
| A10 | WS `config` | `{changed: {key: value}}` | new hub broadcast | — | P0 | 1 | 02 |
| A11 | `GET /api/fs/list` | `?path=&kind=dir\|file&ext=.fits,.fit,.fts&counts=fits` -> `{path, parent, places[], entries[{name, kind, size, mtime, fits_count?}]}` | new (`pathlib`); defaults `sessions_path`, `last_sequence_dir` (`imaging_page.py:1319, 2283`) | — | P0 | 2 | 01 File browsing, 02 Path picking, 03 File listing, 08 File browser |
| A12 | `POST /api/fs/reveal` | `{path}` (desktop app only) | new | — | P2 | 8 | 01 |
| **Connection and devices** | | | | | | | |
| A13 | Status field `devices` + WS `devices` | `{mount\|camera\|filterwheel\|focuser: {state: disconnected\|connecting\|connected\|busy\|error, info, retrying, name}}`, full error text | `device_session.py:292-298, 346, 363-366, 427, 445-448, 457, 485-488, 500, 553-567`; `_mount_retry` 155-160 | — | P0 | 1 | 01 Per-device state, 02 Device states |
| A14 | `POST /api/devices/{id}/connect`, `DELETE /api/devices/{id}` | `{host, port}` -> `DevicesState` | `device_session.py:230-263, 265-501` | ≤ 10 s each, off loop | P0 | 1 | 02 |
| A15 | `POST /api/devices/connect-all`, `DELETE /api/devices` | skip connected devices (fixes duplicate pollers) | `device_session.py:252-263` | ≤ 40 s, per-device events | P0 | 1 | 02 (v1 `/api/connection` kept) |
| A16 | `POST /api/discovery` (job `discovery`) | -> result `{devices: [{host, port, name}], method}` | `discovery_worker.py:50-64`; `discovery.py:167-199`; candidates `device_session.py:205` | 8-15 s, cancellable between layers | P0 | 1 | 02 |
| A17 | `GET /api/profiles`, `PUT /api/profile` | profiles with derived specs, `validated`, `caveats`; `409 busy` when a device is connected | `catalog.py:99-112`; `profile.py:27-121`; `active.py:56-89`; `connection_page.py:237-258` | — | P0 | 1 | 02 |
| A18 | WS `network` | `{seestar: true\|false\|null, internet: true\|false\|null, t}`; `null` = not configured / not probed (Q-G13) | `network_monitor.py:40-84` (Qt-free port) | every 10 s and on change | P1 | 1 | 01, 02 |
| A19 | `POST /api/stellarium`, `DELETE /api/stellarium`, WS `stellarium` | `{port, host}`; event `{running, host, port, clients, error, last_goto: {ra_hours, dec_deg, t, outcome}}` | `device_session.py:783-816, 550-551`; `stellarium_worker.py:24-130` | — | P1 | 3 | 01 Stellarium GoTo notice, 02 |
| A20 | WS `target_suggestions` + `GET /api/catalog/nearby` | `{ra_hours, dec_deg, state: checking\|ready\|failed, candidates[{name, type_label, separation_arcsec, ra_hours, dec_deg}]}`; nearby `?ra_hours&dec_deg&network=` | `object_resolver.py:289`; `object_resolver_worker.py:37-63`; `imaging_page.py:2733-2765`; `shell.py:346-353` | ≤ 8 s | P1 | 3 | 02 fan-out, 03 Nearby names, 05 A13 |
| **Camera, frames, filter wheel** | | | | | | | |
| A21 | `CameraState` extension | `limits {gain_min, gain_max, exposure_min_s, exposure_max_s}`, `offset {value, min, max}\|null`, `binning {value, max}\|null`, `temperature_c`, `owner: idle\|live\|single\|sequence\|autofocus`, `frame_type`, `filter`, `preview_scale` | `camera.py:70-133, 251-289`; `device_session.py:392-415`; `polling_worker.py:96-137`; `camera_service.py:60-170` | — | P0 | 3 | 05 A1, 06 Device vocabulary / Camera owner |
| A22 | `PUT /api/camera/settings` | `{exposure_s?, gain?, frame_type?, preview_scale?, offset?, binning?}`; applies to the next frame in any mode; `409 busy {owner}` while a sequence / autofocus owns the camera; v1 `PATCH /api/camera/live` stays as an alias | `acquisition_engine.py:392-403`; `exposure_worker.py:67-91`; `device_session.py:741-757`; `imaging_page.py:2504-2531` | Alpaca off loop | P0 | 3 | 03 Camera offset / binning, 05 A2, A4 |
| A23 | `POST /api/camera/capture` (extend) | `{…, save: true}`; parameters snapshotted per frame (05 P4b); Dark / Bias move the wheel to the opaque slot first (05 P1); during live: tags the next frame instead of `409` | `acquisition_engine.py:80-83, 317-330, 1510-1594`; `sequencer.py:115-123` | — | P0 | 3 | 05 A3 |
| A24 | WS `frame_saved` | `{seq, path, name, source: single\|sequence, object, filter, frame_type, record?: FrameRecord}` | `acquisition_engine.py:532-557, 1510-1595`; `sequence_worker.py:424-439`; `session_log.py` | — | P0 | 3 | 03 Frame saved, 05 A3, 06 Saved sequence frame |
| A25 | `/ws/frames` header fields | `bayer` (camera profile or FITS `BAYERPAT`), `path`, `file_name`, `date_obs` for `source: file` | protocol frame header; `CameraState.sensor.bayer`; `imaging_page.py:1312-1339` | — | P0 | 3 | 03 Open FITS metadata, 04 A1 |
| A26 | WS `frame_metrics` | `{seq, hfd_px, fwhm_px, star_count, n_detected, sky_adu, peak_adu, eccentricity, star_radius_px}` computed on the full-resolution frame, latest wins | `preview_processor.py:58-123`; `metrics.py:146, 158`; `debayer.py:284` | off loop | P0 | 3 | 03 Frame metrics, 04 A2, 05 A5 |
| A27 | `POST /api/camera/open-fits` (extend) | also `engine.ingest_frame`, invalidates the field, photometry epoch from `DATE-OBS`, stops live first (Q-O11) | `imaging_page.py:1312-1339`; `acquisition_engine.py:515-526, 1357` | — | P1 | 3 | 03, 04 A13 |
| A28 | Status field `filterwheel` + WS `filterwheel` + `POST /api/filterwheel/select` | `{state: disconnected\|idle\|moving\|error, slots[], position, name, message}`; `{name}`; errors end `moving`; sequence moves published | `device_session.py:85-94, 430-458, 681-701`; `filterwheel.py:24-34, 90-135`; `sequence_worker.py:291-304` | ≤ 20 s | P0 | 3 | 03, 05 A6, 06 |
| **Mount** | | | | | | | |
| A29 | `MountState` extension | `alignment: altaz\|eq\|eq_gem\|null`, `tracking_rate`, `tracking_rates[]`, `goto_blocked: {reason: clock, clock_error_s}\|null`, `center_available`, `jog: {primary, secondary}` | `telescope.py:266, 283-294, 610-634`; `device_session.py:110, 286-293, 332, 348, 562` | — | P0 | 3 | 01 Mount geometry, 05 A7, A11 |
| A30 | `POST /api/mount/jog`, `POST /api/mount/jog/stop` | `{axis: primary\|secondary, rate_deg_s}`; stop `{axis?}`; **dead-man**: axis stopped if not renewed within ~1 s or when the client's event socket closes | `telescope.py:564-592`; `device_session.py:45-67, 665-679` | — | P1 | 3 | 03, 05 A10 |
| A31 | `POST /api/mount/tracking-rate` | `{rate: sidereal\|lunar\|solar}`, read back | `telescope.py:610-634`; `device_session.py:637-645` | — | P2 | 3 | 05 A7 |
| A32 | `POST /api/mount/center` | `{target?}` (default photometry target, else last GoTo); `409 not_solved / no_target / not_connected` | `imaging_page.py:2616-2640`; `device_session.py:595-626` | slew via `mount` events | P1 | 4 | 03 Centre target, 05 A9 |
| A33 | `POST /api/mount/sync` | `{source: "solution"}` (only if kept, Q-O3) | `telescope.py:540-562`; `device_session.py:585-593` | — | P2 | 4 | 03, 05 A8 |
| **Focuser, autofocus, conditions** | | | | | | | |
| A34 | Status field `focuser` + WS `focuser` | `{state, name, position, target, temperature_c, max_step, max_increment, absolute, step_size_um}`; **new polling** 0.5 s moving / 5 s idle, temperature 10 s | `focuser.py:53-125`; `device_session.py:460-505` | — | P1 | 3 | 05 A15 |
| A35 | `POST /api/focuser/move`, `/step`, `/halt` | `{position}`, `{delta}`, `{}`; clamp reported; `409 busy` during AF except halt | `focuser.py:127-155`; `device_session.py:705-739` | — | P1 | 3 | 05 A16 |
| A36 | `POST /api/autofocus/start`, `/stop` + WS `autofocus` | start `{exposure_s?, gain?, half_range?, num_steps?}` (defaults from settings, Q-O9); event `{state: running\|done\|rejected\|cancelled\|failed, stage, step, total, samples[], best, fit, message}` | `autofocus_worker.py:48-232`; `acquisition_engine.py:672-744`; `camera_service.py:138-207`; `focus.py:82-160` | minutes, cancellable (stop = return to start) | P1 | 3 | 03 Autofocus progress, 05 A17 |
| A37 | `GET /api/session/conditions?since_seq=` + WS `conditions` | one row per processed frame `{t, seq, hfd_px, fwhm_px, star_count, sky_adu, airmass_target, airmass_mount, sensor_temp_c, focuser_temp_c, focuser_position}`; recorded with the session for Review | `hfd_history_dock.py:107-136`; `metrics_panel.py:62-80`; `imaging_page.py:2370-2439`; `acquisition_engine.py:750-765` | — | P1 | 3 | 05 A18, 08 session_metrics |
| **Observation and catalogue lookup** | | | | | | | |
| A38 | `GET` / `PUT /api/observation` + WS `observation` | `{object_name, target: {ra_hours, dec_deg}\|null}`; `409 busy` while a sequence runs; changing it re-keys the target set and resets live curves | `acquisition_engine.py:971-1022`; `shell.py:166-179`; `camera_dock.py:321-342` | — | P0 | 3 | 01 Observation object, 03, 05 A14, 06 |
| A39 | `POST /api/observation/target` | `{programme: variable\|exoplanet\|other, name, ra_hours, dec_deg, object_type, source}`: sets object name, mount target, and the photometry target **only for variable types** (Q-P8) | `imaging_page.py:2657-2720` (moved to a Qt-free service) | — | P1 | 3 | 05 A14 target, 06 Science source |
| A40 | `GET /api/catalog/resolve?q=` | `{name, ra_hours, dec_deg, object_type, type_label, is_variable, source}`; `404 not_found` / `502` with the resolver texts | `object_resolver.py:116, 136, 369`; `object_resolver_worker.py:18-34` | ≤ 8 s | P0 | 3 | 03, 05 A12, 06 |
| A41 | `GET /api/catalog/suggest?q=&limit=8` | names from cache + embedded catalogue (file cached server-side) | `object_resolver.py:326-341` | — | P1 | 3 | 06 |
| A42 | `GET /api/exoplanets/lookup?q=`, `GET /api/exoplanets/suggest?q=` | `ExoplanetTarget` fields; names | `exoplanets.py:299, 368` | ≤ 2 x 12 s | P2 | 6 | 06 |
| **Live field: plate solve, catalogues, selection** | | | | | | | |
| A43 | `POST /api/field/solve` | `202 {state: solving}`; `409 no_frame / decimated / busy` | `acquisition_engine.py:767-785`; `astrometry_controller.py:105-119`; `SolveWorker` | ASTAP, not cancellable today | P1 | 4 | 03 Identify field |
| A44 | `PUT /api/field/auto` | `{enabled}`; armed by the server for every sequence (Q-O12) | `astrometry_controller.py:82-85`; `imaging_page.py:2537-2550` | — | P1 | 4 | 03 |
| A45 | WS `field` | `{state: none\|solving\|solved\|failed\|invalidated, auto, reason, solution {ra_hours, dec_deg, scale_arcsec_px, rotation_deg, delta_target_arcmin, frame_seq}, wcs {crval, crpix, cd}, grid {lines, labels}, target_reticle}` | `astrometry_controller.py:49-51, 210-238`; `platesolve.py:327-357, 437-527`; `astrometry_session.py:137-153`; `imaging_page.py:757-771, 1378-1403, 2440-2498, 2604-2610` | — | P1 | 4 | 03 Field state, 04 A10 |
| A46 | WS `catalog` + `POST /api/field/catalog/refetch` | `{state: idle\|fetching\|ready\|error, counts, warnings}`; refetch `409 not_solved` instead of a silent no-op | `acquisition_engine.py:815-965` | network, not cancellable | P1 | 4 | 02 Catalogue refetch, 03, 04 A14, 08 Refresh catalogue |
| A47 | WS `field_layers` | `{generation, layers {stars, variables, galaxies, nebulae_clusters, exoplanets, other_objects, vsp, selected}, counts, available}`; markers `{x, y, label, tooltip, g_mag?, suspected?, role?, key?}`; once per catalogue generation | `imaging_page.py:1483-1769, 1904-2008` | — | P1 | 4 | 03 Overlay layers, 04 A11 |
| A48 | WS `field_transform` | `{generation, dx, dy, rot_deg}` per frame | `acquisition_engine.py:1313-1322` | — | P1 | 4 | 03, 04 A12 |
| A49 | `POST /api/field/select`, `DELETE /api/field/select` + WS `selection` | `{x, y, seq, tol_px}` -> `Selection {id, kind, title, rows[], ring{x, y, r_px, aperture: photometry\|star}, pending_star, roles_enabled, removable, identifying}`; event `{id, state: identifying\|resolved\|no_match\|failed\|tracking, selection}`; a new select cancels the running lookup | `imaging_page.py:793-1284, 2042-2046`; `object_resolver_worker.py:66-106`; `metrics.py:45, 225-276` | ≤ ~35 s, superseded | P1 | 4 | 03 Identify point / Selection follow, 04 A4-A7 |
| A50 | `GET /api/field/variables` | rows `{index, name, var_type, mag_text, brightest_mag, period_d, sep_arcmin, in_set_role, suspected}` | `imaging_page.py:2202-2240`; `acquisition_engine.py:225-227, 904-917` | — | P1 | 5 | 06 Field variables |
| **Targets and live photometry** | | | | | | | |
| A51 | `GET /api/targets` + WS `targets` | `{object_name, stars[{key, role, name, ra_hours, dec_deg, auid, source, mags, chart_id, note}], summary, geometry {aperture_px, annulus_in_px, annulus_out_px, fwhm_px, fwhm_source}}` | `acquisition_engine.py:980-1031, 1222-1233`; `targets.py:98-122` | — | P1 | 4 | 03, 04, 06, 08 photometry_targets |
| A52 | `POST /api/targets` | `{star: PendingStar \| variable_index, role: target\|comparison\|check}`; auto-selects VSP comparisons when none; writes `targets/<object>.json` | `acquisition_engine.py:1024-1031, 1077`; `imaging_page.py:2021-2030, 2202-2240` | — | P1 | 4 | 04 A8, 06 from-variable, 08 set-role |
| A53 | `DELETE /api/targets/{key}` | -> target set (Undo = A52) | `acquisition_engine.py:1235-1240` | — | P1 | 4 | 04 A9, 08 remove |
| A54 | `GET /api/photometry/live` | snapshot: object, run root, band, obscode, chart id, curves with every `LcPoint` field + `sigma_syst`, quality report, geometry, revision | `acquisition_engine.py:235-256`; `targets.py:219-228` | — | P1 | 5 | 08 |
| A55 | WS `photometry_point` | `{key, role, name, auid, point: LcPoint, sigma_syst, revision}` for every point (no full re-render) | `acquisition_engine.py:1415-1479` | — | P1 | 5 | 03, 08 (replaces `PhotometryPoint` `types.py:75-86`) |
| A56 | WS `photometry_reset` | `{reason: cleared\|object_changed\|adopted, revision}` | `acquisition_engine.py:258-274, 444-458, 1010-1022` | — | P1 | 5 | 03 curves, 08 |
| A57 | WS `comparison_quality` | full leave-one-out report incl. `selection_status`, `scientific_note`; also outside a sequence (Q-R13) | `acquisition_engine.py:1386-1413`; `quality.py:22-98` | — | P2 | 5 | 03, 08 |
| A58 | `POST /api/photometry/comparisons/recommend` | `{mode: complete\|replace, count?}` -> `{added, comparisons}`; `409 not_solved` | `acquisition_engine.py:1033-1075, 1160-1220`; `catalog/photometry.py:88-170` | pilot pass off loop | P2 | 5 | 03 Reselect, 08 Recommend |
| **Sequence and planning** | | | | | | | |
| A59 | `GET` / `PUT /api/sequence/plan` | plan JSON (`schema: 2`, keeps `metadata`) -> `{plan, derived {total_frames, estimate_s, per_step_s[], end_utc}, issues[{step, field, code, message}]}`; persisted draft | `sequencer.py:28-91, 172-228` | — | P1 | 6 | 06 |
| A60 | `GET /api/sequence/presets`, `GET` / `PUT` / `DELETE /api/sequence/presets/{name}` | list `[{name, modified_utc}]`; `?overwrite=true` | `sequence_panel.py:888-924` | — | P1 | 6 | 06 |
| A61 | `POST /api/sequence/plan/import`, `/export` | `{path}` absolute `.json` | `sequence_panel.py:898-924` | — | P2 | 6 | 06 |
| A62 | `POST /api/sequence/start`, `/pause`, `/resume`, `/stop` | start `{start_at_utc?}` (Q-P2); `409 not_connected / busy`, `400 invalid_argument` | `acquisition_engine.py:444-499` | run, stoppable | P1 | 6 | 06 |
| A63 | WS `sequence` | `{state: idle\|running\|pausing\|paused\|autofocus\|stopping, object_name, run_root, step_index, step, pass_index, repeat, frames_done, frames_total, eta_s, current{exposure_s, started_utc}, last_result{completed, reason, message, frames_saved, ended_utc}}` | `acquisition_engine.py:93-96, 506-513, 584-596`; `sequence_worker.py:94-102` | — | P1 | 6 | 01 Run summary, 03 Sequence progress, 06 |
| A64 | `GET /api/sequence/preflight` | `[{id, level: ok\|note\|block, message}]` (camera, object, mount, site, wheel names, focuser vs AF, altitude, output folder) | `sequence_panel.py:1037-1054` + new checks | — | P1 | 6 | 06 |
| A65 | `GET /api/visibility` | `?ra_hours&dec_deg&night=YYYY-MM-DD&step_min=10` -> `{site, samples[{t_utc, alt_deg}], peak, window, min_alt_deg}`; `409 site_missing` | `sky_geometry.py:60-88` | — | P1 | 6 | 06 |
| A66 | `POST /api/transit/predict`, `POST /api/transit/plan` | `{planet_name, baseline_minutes, date?}` -> window, local / UTC, altitudes; plan -> draft with metadata | `transit.py:34-122`; `sequencer_page.py:132-187, 248-286`; `airmass.py:52-101` | — | P2 | 6 | 06 |
| **Review** | | | | | | | |
| A67 | `GET /api/sessions` (job `sessions_scan` when slow) | `[{path, folder, object, started_utc, frames, lights, filters, curves {target, comparison, check}, has_quality, issues}]`; cached by folder mtime | `config.py:268-270`; `review.py:102` (`read_temperature=False`) | paginated | P1 | 2 / 7 | 01 Session list, 07 List sessions, 08 Session list |
| A68 | `GET /api/review/session?path=` (job `session_open` with progress) | identity, summary, metadata, quality report, warnings, readiness issues, frames with resolved path, targets, chart id; atomic | `review.py:76-175`; `targets.py:207, 219` | FITS headers, cancellable | P1 | 7 | 07, 08 Open session |
| A69 | `GET /api/review/session/curves?path=` | columnar per curve (all `LcPoint` fields); fixes the `check_` role | `review.py:178-240`; `lightcurve.py:39-62` | — | P1 | 7 | 07, 08 |
| A70 | `POST /api/review/import-csv` | `{path}` -> curves + targets + inferred roles; `422` with the reason | `lightcurve.py:150-170`; `analyze_page.py:754-760` | — | P2 | 7 | 07, 08 Open CSV |
| A71 | `GET /api/files/frame?path=&view=` | binary frame in the `/ws/frames` layout, **not** published on `/ws/frames` | `analysis_window.py:54-65`; `preview_processor.py:58` | — | P1 | 7 | 07 Frame pixels, 08 Source frame |
| A72 | `GET /api/files/fits-header?path=` | `{text, keywords}` | `analysis_window.py:68-133` | — | P2 | 7 | 07 |
| A73 | `POST /api/files/measure-star` | `{path, x, y, radius, snap}` -> centroid, FWHM / HFD (px and ″), ecc, SNR, peak, sky, RA / Dec if solved | `metrics.py:59, 225`; `FrameWCS.pixel_to_radec` | — | P2 | 7 | 07 |
| A74 | `POST /api/files/solve` (job `file_solve`) | `{path}` -> solution, WCS, grid | `solve_worker.py:20`; `astrometry_session.py:36-153` | ASTAP, cancellable (kill) | P2 | 7 | 07 |
| A75 | `POST /api/files/catalogue` (job `file_catalogue`) | `{path\|solve_job}` -> per-layer markers + counts | `catalog_worker.py:33, 80`; `analysis_window.py:588-858`; `offline.py:81`; `exoplanets.py:138` | network, cancellable | P2 | 7 | 07 |
| A76 | `POST /api/review/rerun` (job `rerun`) | `{frames_dir\|paths[], targets {session_path\|live}, reference {solve_path\|live}, out_dir, diagnostics}` -> progress, result `{frames_done, frames_skipped, curves[], rotation_deg, shift_px, check_rms, out_dir, cancelled}`; globs `.fit/.fits/.fts`, light frames only | `photometry_batch_worker.py:43-155`; `params.py:48-68`; `imaging_page.py:2248-2368` | long, cancellable between frames | P2 | 7 | 03 Batch re-run, 07, 08 |
| A77 | `POST /api/export/aavso/preview` | `{source: live\|session\|import, keys, exclude_saturated, exclude_suspect}` -> `{obscode, band, chart, kname, rows, skipped_nonfinite, saturated, suspect, session_filter}` | `lightcurve.py:204-254`; `targets.py:219-228` | — | P2 | 7 | 07, 08 |
| A78 | `POST /api/export/aavso` (job `export`) | same + `{path?, obscode, filt, chart}` -> `{path, rows}` or text for a download; target-role curves only; refuses an unset obscode (Q-R2) | `lightcurve.py:204-254` | — | P2 | 7 | 07, 08 |
| A79 | `POST /api/export/csv` (job `export`) | `{source, keys?, path?}` -> `{path, rows}` or text | `lightcurve.py:136-147` | — | P2 | 7 | 07, 08 |
| **Jobs** | | | | | | | |
| A80 | WS `job`, `GET /api/jobs`, `GET /api/jobs/{id}`, `DELETE /api/jobs/{id}` | §4.2 | wraps A5, A16, A67, A68, A74-A76, A78-A79, A82 | — | P0 | 1 | 07 Generic job events |
| **Settings helpers** | | | | | | | |
| A81 | `GET /api/astrometry/astap` | `?path&database_path` -> `{astap, database_dir, database_found, database_args}` | `platesolve.py:119-144, 305-319`; `configuration_page.py:1208-1231` | — | P1 | 2 | 02 |
| A82 | `POST /api/site/search` (job `site_search`) | `{query}` -> `[{label, latitude, longitude, elevation_m}]`; User-Agent from the version | `location_resolver.py:17, 34-87` | ≤ 6 x 8 s, cancellable | P1 | 2 | 02 |
| A83 | `GET /api/caches`, `DELETE /api/caches/{kind}` | `[{kind, label, path, exists, files}]` | `configuration_page.py:1104-1163`; `object_resolver.py:38`; `exoplanets.py:28-37`; `aavso.py:63`; `gaia.py:50`; `field_objects.py:49` | — | P1 | 2 | 02 |
| A84 | `GET /api/catalogues/essential` | `{name, version, source, source_url, object_count}` | `catalog/offline.py:69` | — | P2 | 2 | 02 |

Not carried as separate routes (deduplicated): `GET /api/about` (= A1); `run` and busy
summaries (derived client-side from `sequence`, `autofocus`, `CameraState.owner`, jobs;
quit uses A7's `409 busy {what}`); `PUT /api/imaging/star-radius`, `PUT
/api/display/star-radius`, `PATCH /api/settings`, `/api/settings/photometry` (= A9 config
keys); `POST /api/targets/science-source` (= A39); `/api/photometry/targets/remove`,
`/set-role`, `/api/targets/from-variable` (= A52, A53); `/api/photometry/batch`,
`/api/photometry/rerun` (= A76); `/api/photometry/export.csv`, `/aavso.txt`,
`/api/review/export/*` (= A77-A79); `sequence_frame` (= A24); `session_metrics` (= A37);
`photometry_targets` (= A51); `/api/files`, `/api/fs/list`, `/api/files?dir=` (= A11);
`POST /api/catalog/refresh`, `/api/field/catalogue/refetch` (= A46); `POST
/api/image/select`, `/api/field/identify` (= A49).


---

## 5. New icons

Checked against the 109 ids of `icon-inventory.json`. Six ids were proposed by the area
specs; three are accepted, three are rejected because an existing id or a text button
covers them.

| Id | Concept | Needed by | Why no existing id fits | Decision | Display |
|---|---|---|---|---|---|
| `sort` | Column sort indicator (ascending; drawn mirrored by CSS for descending; no glyph in catalogue order) | `Table` headers: Variables, Frames, Sessions, Ensemble, caches (06, 07, 08) | `disclosure` means expand / collapse; `move-up` / `move-down` mean reorder a step | **Accept** | icon in header, `aria-sort` carries the state |
| `frame-prev` | Step to the previous light frame of the session (PageUp) | R2 Frame inspector toolbar (07) | jog chevrons are reserved for mount directions; `move-up` / `move-down` reorder lists | **Accept** (pair with `frame-next`: sensor frame + chevron) | icon, tooltip "Previous frame (PageUp)" |
| `frame-next` | Step to the next light frame of the session (PageDown) | R2 toolbar (07) | same | **Accept** | icon |
| `expand-pane` | Expand one pane (a plot cell of the Review wall, the drawer) to fill its region, and restore it | R1 cell menu and header, drawer header (07 proposed `expand-plot`) | `zoom-fit` means fit the data / frame, `panels` toggles the rail, `panel-float` means a separate window | **Accept**, renamed from `expand-plot` so the drawer can use it too | icon, toggled style when expanded |
| `restore-default` | Restore a Settings category to the shipped defaults (02 Q13) | Settings form footer | — | **Reject**: a form action is text-only (BRAND 7 row 3): text button "Restore defaults" with a confirmation | text |
| `scheduled-start` | Start the sequence at a chosen time (06 Q2) | Plan transport | — | **Reject**: `start` with the label "Start at 21:30" says it (start sequence is icon + label anyway) | icon + label |

Inventory updates without a new id (design team, BRAND 12):

| Id | Change |
|---|---|
| `arrange` | Concept becomes "Panels popover: show / hide rail cards, drawer tabs and plot facets, reset layout" (D1); float / dock entries no longer exist. |
| `panels` | Concept: "Show or hide the right rail" (built), shortcut `P`. |
| `jog-pad` | Concept: "Arm keyboard jogging / open the Jog disclosure of the Mount card" (no dialog any more), shortcut `J`. |
| `session-metrics` | Concept: the **Conditions** timeline (Observe drawer tab, Review facet). |
| `labels` `N`, `catalogue` `O`, `statistics` `I`, `saturation` `C`, `region-stats` `R`, `log` `L`, `help` `?` | New proposed shortcuts (§3.10). |
| `tracking`, `focus-in`, `focus-out` | Drop the proposed `T`, `[`, `]` (they move hardware, BRAND 7). |
| `close`, `abort` | Both list `Escape` (D21: one key closes the top layer and aborts motion). |
| `add-plot` | Retired ("+ Comparison plot below" is dropped, D4). |
| `panel-float`, `panel-dock` | Reserved for a later Tauri multi-window (D27). |
| `open-session` | Also labels the "Session" back button of R2. |

Token requests (not icons): `--viewer-saturated` (loud clipped-pixel colour for Observatory
and Charcoal; Night Red draws clipped pixels black), `--overlay-vsp` (VSP reference
candidates; 04 suggests `--role-comparison` "+"), and confirmation that the selection ring
and region box use `--accent` (03 Q13, 04 Q2).


---

## 6. Qt problems worth fixing during the migration

Deduplicated from the eight specs (about 280 findings, many reported by two or three
areas). Severity: **S** science data or FITS metadata at risk, **H** hardware safety or a
frozen UI, **U** wrong, dead or duplicated UI, **N** Night Red / identity. "Fix" says where
the web or server design removes it; "API" ids refer to §4.3.

### 6.1 Science data and metadata (S)

| # | Problem (Qt refs) | Fix | Source |
|---|---|---|---|
| S1 | Dark / Bias Take shot never moves the wheel to the opaque slot: on the shutterless Seestar a "Dark" single shot is a light frame tagged Dark (camera_dock.py:57; acquisition_engine.py:80-83, 349-359) | Server capture moves the wheel first, as sequences do (A23) | 05 P1 |
| S2 | Take shot writes exposure / gain / type / filter read when the frame arrives, not those used (acquisition_engine.py:1511 vs 392-403) | Per-frame parameter snapshot (A23) | 05 P4b |
| S3 | Sequence wheel moves bypass `move_filter`: next Take shot writes a stale FITS FILTER and folder (sequence_worker.py:291-304; acquisition_engine.py:1523, 1540) | Filter state published by every mover (A28) | 05 P3 |
| S4 | Open FITS keeps the previous WCS when the geometry matches (old overlays on a new image) and dates the photometry point "now", ignoring DATE-OBS (imaging_page.py:1312-1339; acquisition_engine.py:515-526, 1357). (The uint16 cast of float FITS, 03 P8, is already handled by the v1 server, protocol.md "Opening FITS files".) | `open-fits` ingests, invalidates the field, uses DATE-OBS (A27) | 03 P8-P9 |
| S5 | Transit metadata dropped by `to_plan` / `load_plan`: `observation.json` never written, presets save `{}` (sequence_panel.py:816-838; sequence_worker.py:459-477) | Plan JSON keeps `metadata`, schema 2 (A59) | 06 P1 |
| S6 | `cadence_s` hidden on the exposure spin box, Interval silently ignored, no cadence ≥ exposure check (sequence_panel.py:709, 799, 810; sequence_worker.py:234-239) | Visible Cadence column, server validation `issues[]` | 06 P2 |
| S7 | Silent substitution in steps: unknown filter -> first slot, unknown type -> Light, ranges clamp on connect (sequence_panel.py:695-702, 930-976) | Invalid cells flagged, never clamped (§3.4) | 06 P11 |
| S8 | Plan "Find" turns any object (M 42) into a photometry target (sequencer_page.py:107; imaging_page.py:2671-2676, 2709-2720) | A39 sets the photometry target for variable types only (Q-P8) | 06 P8 |
| S9 | Check-star CSVs classified as targets in Review (review.py:218) | A69 fixes `_curve_identity` | 07 P19, 08 P4 |
| S10 | A single-star CSV loads as role target: a comparison exported to AAVSO as a science target named after the file (lightcurve.py:164-168; analyze_page.py:741-753) | A70 restores role and name from prefix and `targets.json` | 07 P31, 08 P5 |
| S11 | AAVSO export: saturated / suspect points included without note, OBSCODE `XXX` written silently, FILT never checked against the session filter, KNAME / KMAG `na` from Review, exports silent, `OSError` uncaught, default folder `~` (lightcurve.py:204-254; photometry_window.py:302-327) | Export dialog with preview, guards and exclusions (A77-A78, Q-R2, Q-R3) | 07 P32, 08 P6-P7 |
| S12 | Batch re-run globs only `*.fits` (Argos writes `.fit`), takes every file by mtime with no frame-type / object filter (imaging_page.py:2287-2289; fits_writer.py:241) | A76: `.fit/.fits/.fts`, light frames of the object | 03 P12, 07 P33 |
| S13 | Batch output in `sessions_path.parent/targets`, overwritten, no role prefix, missing DATE-OBS plotted at JD 0, cancelled run reported as success, skipped frames not counted (imaging_page.py:2299, 2306, 2349; photometry_batch_worker.py:276, 392-402) | A76 writes a new folder in the session and reports skips and cancellation | 03 P10, 07 P34-P35, 08 P33 |
| S14 | Auto-identification armed for a sequence only when a WCS already exists, so an unsolved run measures no photometry (imaging_page.py:2543-2546) | A44 armed for every sequence (Q-O12) | 03 P13 |
| S15 | Aperture geometry editable mid-run without warning (curve mixes apertures), spins persist and log on every step (photometry_window.py:70-139; imaging_page.py:2152-2165) | Settings › Photometry, `409 run_active` while a sequence runs (A9, Q-R10) | 08 P13 |
| S16 | Relative-flux normalisation median includes saturated points (lightcurve_panel.py:224-235) | `LightCurvePlot` excludes them (Q-R11) | 08 P34 |
| S17 | Quality report computed only during a sequence; `selection_status` / `scientific_note` never shown; "Waiting for 10 points" hard-coded (acquisition_engine.py:1393-1394; quality.py:76-91; comparison_table.py:42) | A57 always, shown in the Ensemble card | 07 P22, 08 P14-P16 |
| S18 | Live dock fed without `relative_flux`: a ratio-only point raises `TypeError`, aborting the slot so the Photometry window misses it (imaging_page.py:2396-2406; lightcurve_panel.py:127) | One point stream (A55) with every field | 08 P1 |
| S19 | After 10 points every point re-renders all curves (O(N²)) and resets the user's zoom (acquisition_engine.py:1456-1461, 1494-1504; lightcurve_panel.py:277) | Append-only points, client recomputes error bars from `sigma_syst` (A55) | 08 P3 |
| S20 | HFD measured on the displayed (possibly half-res) array; 5 / 10 px colour thresholds scale-dependent; FWHM / HFD arcsec from the nominal scale after a solve (imaging_page.py:1257-1276, 2581; camera_dock.py:372) | A26 on the full-res frame; scale from the solution; no colour-only thresholds (Q-O10) | 04 P17, 05 P13 |
| S21 | Pixel readout labelled ADU reads the display array; saturation compares neutralised RGB to a raw full-well threshold; "Bit depth" says 16 for a 12-bit ADC; statistics mix populations without units (fits_viewer.py:347-351, 411-414, 436-440; preview_processor.py:86; metrics.py:146-158, 377-389) | Raw samples client-side, labelled statistics (04 §2.4) | 04 P4-P5, P16, P29 |
| S22 | Autofocus ignores gain, filter and frame type; exposure silently from the camera card capped at 10 s; the V-curve re-fits all samples and can disagree with the chosen position (autofocus_worker.py:81, 148-149; vcurve.py:117; acquisition_engine.py:701-708) | A36 applies settings, publishes the worker's fit | 05 P8-P9 |
| S23 | Stop AF / Halt race: return-to-start interrupted, "Autofocus complete" logged after a cancel or rejected sweep (autofocus_worker.py:118-121, 187-203; imaging_page.py:2813-2817, 2842-2847) | Stop and halt ordered server-side, terminal states (A36) | 05 P43 |
| S24 | ASTAP database folder silently disables the database set (astrometry_session.py:64; platesolve.py:313-314) | A81 reports `database_args`; inline note (Q-C9) | 02 |
| S25 | Two sources of truth for sensor limits; `camera.adc_bits` read by no code; `hardware.overrides` has no editor (config.py:75-77; imaging_page.py:722; photometry/params.py:64) | Q-C1 | 02 |
| S26 | Visibility at lat / lon 0 / 0 without a site; transit after midnight drawn off the plot; fixed 60 min baseline after Find; "site required" shown when prediction failed (sequencer_page.py:79-87, 147-158, 211-216; sequence_panel.py:653-654, 868-877) | A65 / A66 with `site_missing`, client-chosen night | 06 P3-P6 |
| S27 | Dither: model says unsupported on the Seestar, worker moves the mount (sequencer.py:44-46; sequence_worker.py:229, 249-278) | Q-P5 | 06 P23 |
| S28 | Time axes disagree (JD with SI-scaled ticks, Review quality in elapsed hours, live metrics in seconds since an app-wide t0 never reset) (lightcurve_panel.py:58-66; session_review.py:42, 62; imaging_page.py:2414-2417) | Shared linked time axis (D26) | 07 P16-P17, 08 P20-P21 |
| S29 | Unvalidated-profile wording contradicts itself; device hints hard-coded to the S30 Pro sensor (connection_page.py:41-46, 125, 338; configuration_page.py:528, 580) | Profile caveats from A17 (Q-C2) | 02 |
| S30 | Centre target uses the reference WCS, not the tracked one (imaging_page.py:2618, 2634), unverified | Check during A32 | 03 P17 |

### 6.2 Hardware safety and responsiveness (H)

| # | Problem (Qt refs) | Fix | Source |
|---|---|---|---|
| H1 | Every Alpaca connect, mount, focuser, offset and binning call is synchronous on the GUI thread: an unreachable host freezes the window ~40 s on Connect all (device_session.py:265-488, 573-757; client.py:88) | All device work off the event loop (§4.1) | 02, 03 P16, 05 P27 |
| H2 | Connect all reconnects connected devices: a second mount poller, a Camera dropped without disconnect (device_session.py:265-294, 351-358, 525-532) | A15 skips connected devices | 02 |
| H3 | Manual Control dialog keeps a stale Telescope after reconnect, calls MoveAxis on the UI thread, tracks one axis (two keys -> wrong axis stopped) (manual_control_dialog.py:157-178; imaging_page.py:2790-2798) | One jog path with per-axis state and a server dead-man (A30, D23) | 03 P15, 05 P20-P22 |
| H4 | Clock error logged as "GoTo and Sync disabled" but the buttons stay enabled (device_session.py:286-290; telescope.py:287-294) | `goto_blocked` disables them with the reason (A29) | 05 P26 |
| H5 | Sync syncs the mount to its own polled position (no-op) and fails with tracking off (device_session.py:585-593) | Q-O3 | 03 P14, 05 P17 |
| H6 | Tracking rate never read back; "Tracking ON" while disconnected (device_session.py:637-645; mount_dock.py:116) | A29 / A31 | 05 P18-P19 |
| H7 | Disconnect without confirmation during a sequence; the engine releases only live / single owners (acquisition_engine.py:432-438), plausible | Confirm while busy (§3.3) | 02 |
| H8 | No quit confirmation; shutdown blocks the UI up to ~96 s; devices not disconnected at quit (shell.py:611-625; device_session.py:822-831) | Quit dialog + A7 | 01 P39-P41 |
| H9 | A failed filter move leaves the Filter combo disabled for the session (device_session.py:85-94; imaging_page.py:707) | Errors end `moving` (A28) | 05 P2 |
| H10 | Focuser position never polled; Go to overwritten by AF steps; range ignores MaxStep and clamps silently; during AF Move stays enabled while Halt is disabled (focuser_dock.py:100, 113-116, 160, 182-184; device_session.py:466-476; focuser.py:133) | A34-A35, Focuser card states (05 §2.4) | 05 P4-P7 |
| H11 | Values written on every keystroke: offset / binning to the driver, `alpaca.host` to disk (and probed half-typed), site spins rewrite the config ~5 times per step (camera_dock.py:158, 170; connection_page.py:179, 353-356; configuration_page.py:861-868) | Commit-based save (§3.4) | 02, 05 P28 |
| H12 | Silent failures on connection: empty address returns silently; discovery feedback only in the Observe log, no busy state, only the first device kept; auto-reconnect shown as "Error" with no text; reasons cut to 48 chars (connection_page.py:366-374; device_session.py:200-224, 297, 552-567) | Connection screen states (02 §2.4), A13, A16 | 01 P23-P24, 02 |
| H13 | Telescope profile changeable in Settings while connected, refusal silent (configuration_page.py:525-530, 583-589) | D28, `409 busy` shown | 02 |
| H14 | Stellarium bind error invisible on the card, host never shown, port saved only when started, GoTo label never reverts (stellarium_card.py:107-151; device_session.py:793-794, 814-816) | A19 event, Planetarium card | 02 |
| H15 | Camera lock hint says "Sequence running" during a stand-alone autofocus (imaging_page.py:638; camera_dock.py:213) | `owner` badge (A21) | 05 P39 |
| H16 | Network probe of 1.1.1.1 / 8.8.8.8 every 10 s without opt-in; "no host" and "down" look the same (network_monitor.py:32-37, 83; statusbar.py:161-164) | Q-G13, three states (A18) | 01 P22, 02 |
| H17 | Place search up to 6 x 8 s while shutdown waits 9 s; User-Agent hard-coded "Argos/0.4.1" (location_resolver.py:17, 40-87; configuration_page.py:995-999) | Cancellable job (A82) | 02 |

### 6.3 Wrong, dead or duplicated UI (U)

| # | Problem (Qt refs) | Fix | Source |
|---|---|---|---|
| U1 | Palette combo dead on Observe; palettes inert on any RGB image (image_toolbar.py:79-94; fits_viewer.py:326-357) | Palette in the shader LUT (04 §2.5 client-only) | 03 P1, 04 P1-P2 |
| U2 | Two grid toggles drive one setter and desynchronise (overlay_bar.py:32; histogram_dock.py:153-157) | One `sky-grid` toggle | 03 P6, 04 P3 |
| U3 | Star card: Dismiss never hides it, card not refreshed after a role, clicks ignored while a lookup runs, card and ring survive a slew, hit tolerance in image px, two ring meanings, overlaps the selection label (star_info_card.py:105-109; imaging_page.py:973-975, 991-1023, 1038-1042, 2021-2030, 2440-2498) | Star card + A49 (supersede, 10 screen px, labelled ring styles) | 03 P19-P21, P24; 04 P7-P10, P21, P31 |
| U4 | Panel chips are `toggleViewAction`s (a tabbed dock reads "on" and a click hides it); light-curve dock misplaced; duplicate reset entries; View › Reset Window Layout a no-op overwritten at close (imaging_page.py:355, 388, 396, 451-480; shell.py:452-457, 622) | Panels popover, live Reset layout (D16) | 01 P9, 03 P2-P5, 07 P18 |
| U5 | Review: FWHM dock never placed (floating window), chips rename to dock titles, extra docks have no chip, Arrange omits them, toolbar overflows (analyze_page.py:270-277, 340-348, 441-446, 522, 551) | Plot wall + Panels popover (D4) | 07 P1, P3-P4; 08 P25, P30 |
| U6 | Light-curve hover dead (scatter not hoverable) while the UI says "Hover a point" (lightcurve_panel.py:140-180) | uPlot hover tooltip | 07 P6, 08 P2 |
| U7 | Click feedback only in the first source dock; a quality-table click retargets the first comparison panel and fails without AUID (analyze_page.py:165-183, 559-565; comparison_table.py:252; review.py:239) | One selection model (07 §2.4) | 07 P7, P10; 08 P26 |
| U8 | Frames and Metadata tables editable (analyze_page.py:186-196) | Read-only `Table` | 07 P11, 08 P27 |
| U9 | Session load on the UI thread with one FITS header read per frame; malformed CSV `KeyError` crash leaves the page half updated; silent failures (empty CSV, unreadable FITS, missing frame) (review.py:167; lightcurve.py:175-178; analyze_page.py:727, 742-744, 778-779; analysis_window.py:444-445) | Atomic A68-A70 jobs, error states (§3.9) | 04 P24, 07 P12-P14, P28, 08 P29 |
| U10 | Field photometry window opened from Review is unwired: 4 of 6 tabs inert, aperture spins show minima (analyze_page.py:745-763) | Window dissolved (D8) | 07 P30, 08 P9 |
| U11 | "Open session photometry…" (⌘⇧O) opens a CSV in a floating window while "Open session…" opens a folder; docs link points to GitHub; menu tooltips invisible; `&` eaten as a mnemonic (shell.py:67, 194-283, 197-201, 212, 223, 594) | D19, Help popover, tooltips from the registry | 01 P10-P13, 07 P36, 08 P22 |
| U12 | Review has an "AAVSO export" dock but no export action (analyze_page.py:118-131, 221) | R1 Export AAVSO | 07 P8, 08 P23 |
| U13 | Readiness line always in warning colour; one warning per missing FITS overflows a 112 px card (analyze_page.py:151, 154, 641-645) | Readiness badge + popover | 07 P5, 08 P28 |
| U14 | Frame Viewer: solve result overwritten by the catalogue message, "Adjust image" button and tab duplicate, Preview forced to Raw CFA, sensor value without unit, solve not cancellable (analysis_window.py:260-277, 333-334, 367, 494, 666) | R2 Identification card, A74 cancellable | 07 P24-P29 |
| U15 | Gaia G limit saved only on mouse release; VSP chip checked while its layer is forced off; catalogue dialog from the Field menu only refetches (overlay_bar.py:107-110; imaging_page.py:1429-1433, 1738-1739; shell.py:470-472) | Catalogue layers popover, one save path (D12) | 03 P18, P22-P23; 04 P11 |
| U16 | Context bar never shows Take-shot saves and keeps "Opened X" under live frames; sequence progress shown twice (imaging_page.py:422-428, 1336, 2552-2565) | Status bar frame segment + run chip (D18) | 03 P7, P26 |
| U17 | Two "Object" fields with different meanings, a lookup overwrites the typed one; duplicate slew buttons (camera_dock.py:321-329; imaging_page.py:2664; mount_dock.py:156, 210) | D11, one Slew | 05 P15-P16 |
| U18 | HFD history misaligns HFD and stars, uses dual y axes, title says FWHM without FWHM; HFD shown three times; session metrics sampled only while a window is visible, t0 never reset, blocking temperature read (hfd_history_dock.py:62-74, 114-120; imaging_page.py:290, 338, 2370-2439) | Conditions timeline (D6, A37) | 05 P10-P12, P14, P34; 08 P21 |
| U19 | pyqtgraph default menus (Invert Axis, manual ranges, Mouse Mode, Export…) on the viewer and five plots; pan / zoom disables auto-range (fits_viewer.py:138; histogram_dock.py:75; vcurve.py:31; hfd_history_dock.py:46; session_review.py:40; sequence_panel.py:105) | ARGOS context menu, plot rules (§3.13) | 01 census, 04 P25, 05 P35, 07 P38, 08 P32 |
| U20 | Plan: during a run only the table is locked (object, presets, transit stay active; object change mid-run); preset load overwrites the object; outcome and refusals only in the log; one shared status label; second Start refused silently (sequence_panel.py:832, 840-848, 880, 983-988, 1016-1024; sequencer_page.py:73-77, 305; acquisition_engine.py:449-450, 512-513, 591-594) | Locked states, run strip, inline refusals (06 §2.4) | 06 P9-P10, P14-P15 |
| U21 | Plan: Remove / Dup / move act on the last row without a selection, Dup appends at the end, dead `count > 0` check, cell spin boxes take wheel events, suggestions read the cache file per keystroke, preset load errors raw, no schema version, editor state lost at restart (sequence_panel.py:592-593, 705-760, 918-924, 1064; sequencer.py:201-228) | Steps region rules, A41, A59-A60 | 06 P12-P13, P19-P20, P27-P28 |
| U22 | Pausing gives no feedback until the frame ends, ETA includes pauses and AF, readiness ignores site / wheel / focuser / altitude, Dark slot selectable for Light, Filter editable on Dark / Bias (sequence_worker.py:225-227, 280-289; sequence_panel.py:698-703, 1048-1049) | A63 `pausing`, A64 preflight | 06 P16, P18, P30 |
| U23 | Target table: stale current row removes another star, buttons always enabled; Variable table: no catalogue order, unlabelled first column, filter keeps hiding markers after close (target_table.py:59-61, 80-83; variable_table.py:31, 111, 188-199; imaging_page.py:1776-1779) | `TargetSetList`, Variables tab (D7, D24) | 06 P21-P22, 08 P35 |
| U24 | Auto-count spin reselects on every step (UI-thread pilot), duplicated in the catalogue dialog with another range; Remove / Recommend without confirmation or undo (comparison_table.py:81-124; imaging_page.py:2167-2183; astrometry_settings.py:262-267) | A58 with explicit button, Undo / confirm (§3.3), Q-R12 | 08 P11-P12 |
| U25 | Settings page read once: dialog and overlay writes overwritten by stale widgets; dialog and page expose different plate-solving subsets (configuration_page.py:67, 779-848, 1096-1102, 1172-1184; astrometry_settings.py:90-122) | One form per key + `config` event (D12, A10) | 01 P17, 02 |
| U26 | Catalogue dialog: Gaia preset not updated, dependent toggles active with their parent off, hidden spins write dead keys (astrometry_settings.py:171-257, 324-336, 372, 383) | `SettingsForm` dependencies, Q-C7 | 02 |
| U27 | Cache "Refresh" buttons actually delete; Browse tooltips wrong; Save dialog used to pick an existing file; counts stale; saved-site removal without undo, case mismatch (configuration_page.py:283-291, 354-378, 941-993, 1026-1028, 1104-1163) | Caches table "Clear cache…" + confirm, Undo toast | 02 |
| U28 | Language selector dead; log level needs a restart (unstated); theme switch only partly live (configuration_page.py:740-763, 1233-1268; theme.py:16-19; main.py:144) | Language dropped; A9 applies live | 01 P36-P38, 02 |
| U29 | Cache and calibration folders applied only when the Settings page is built (configuration_page.py:823-824, 1040-1084) | A3 at server start-up | 02 |
| U30 | Rail right-click "Modes" hides the rail for good; Field / Photometry menus act on Observe without switching; only Observe's sources reach the log (shell.py:121, 246, 275-284; imaging_page.py:516, 531, 614) | Always-visible rail, global log (D17) | 01 P6, P14, P31 |
| U31 | Log unbounded, force-scrolls while reading, 38 WARN lines uncoloured (`WARN` vs `WARNING` key) (log_panel.py:44, 57-58, 71, 80-84; theme.py:97-106) | Log v2 (A2, §3.8) | 01 P28-P30, 03 P25 |
| U32 | Start-up failure invisible outside a terminal; splash stages dishonest; title box touches the version (main.py:143-187; splash.py:125, 131) | Start-up screen with failure state | 01 P1-P2, P4 |
| U33 | Status strip: Observe amber at every launch, live view never marks Observe active, every child label underlined, badges without tooltip, badge click on any button (shell.py:393-397, 409-411; statusbar.py:47, 309-320) | Rail dots (§3.10.1), status bar | 01 P18-P19, P21, P23-P24 |
| U34 | Support bundle: cancelling the session chooser aborts the bundle, privacy question defaults to Yes, fixed file name (shell.py:488-506) | One dialog (M15) | 01 P35 |
| U35 | Long help labels clipped, stale "Display tab" and "Capture → Catalogues & depth…" references (configuration_page.py:331-337, 412, 418-424, 512-517, 635; overlay_bar.py:121-124) | Help text from config meta | 02 |
| U36 | Review plots: triple headings, legend over data, quality title fixed to FWHM, brass used as a data colour, overlays of 8 series, colours by insertion order including WARNING / DANGER (lightcurve_panel.py:20-22, 131-160; session_review.py:22, 45; target_curve_panel.py:65-66) | Plot rules (§3.13), BRAND 10 | 07 P16-P17, P39-P40; 08 P18-P19 |
| U37 | Plan wastes space (heading row, table capped at 420 px, control dock clips readiness); visibility plot with an unexplained 30° line, no "now", no target name (sequencer_page.py:47; sequence_panel.py:126-160, 262-270, 558-562) | Plan layout (06 §2.3) | 06 P26, P29 |
| U38 | Viewer: label de-overlap in image px, loupe of the 8-bit image ignoring HiDPI, marker shape and colour collisions (five-point star for exoplanets, CYAN reused), WCS grid and histogram B curve in brass, tool settings forgotten at launch, crosshair semantics differ from the web (fits_viewer.py:35-37, 194-232, 613-620, 803-807, 923-954; histogram_dock.py:85-87) | 04 §2.4 overlay drawing, persistence | 04 P14, P18-P20, P26-P28 |
| U39 | Dead code and stale docs not to port: `open_analysis` / `load_fits`, `request_autofocus`, `nudge_focuser`, AF relays, `FocuserDock.set_moving`, `preview_scale_changed`, `HfdHistoryDock.cleared`, `FitsViewer.reset`, `StatisticsDock.clear`, `TargetSet.summary` unused, dock `setEnabled` loop, `_grid_btn`; dead keys `ui.window_state`, `ui.window_geometry`, `field_stars_max_results`, `named_objects_max_results` (imaging_page.py:1345-1368, 2819-2825; analyze_page.py:646-647; config.py:59-60) | Not carried over (Q-C7) | 01 P7, 03 P27, 04 P15, 05, 06 P31, 07 P23, P29 |

### 6.4 Night Red and identity (N)

| # | Problem (Qt refs) | Fix | Source |
|---|---|---|---|
| N1 | The Qt viewer ignores Night Red: no tint, yellow ROI pen, Fire / Ice emit blue and green, red saturation invisible on red, pens baked at build time (fits_viewer.py:147-201, 337-358, 388) | Viewer tint (exists), D30, black saturation | 04 P6, 07 |
| N2 | Splash in fixed gold / white; About logo PNG with an opaque white square (splash.py:44-48; shell.py:549) | Start-up screen and About from tokens and `brand/argos-mark.svg` | 01 P3, P33 |
| N3 | Unicode pictographs used as icons in labels (⚡ ▶ ■ ◉ ⟳ ⊙ ✥ ↑ ↓ ＋ ⧉ － ✗ ✓ ○ ●) (connection_page.py:187, 209-211, 402-463; stellarium_card.py:76-151; camera_dock.py:204-207; mount_dock.py; sequence_panel.py:249-253, 466-472) | ARGOS icons (BRAND 4.3) | 02, 05 P40, 06 |

### 6.5 Gaps in the new code found by the area specs

| # | Gap | Fix |
|---|---|---|
| W1 | `matchesShortcut` rejects ⌘ / Ctrl, so ⌘O, ⌘⇧O, ⌘Q cannot be bound (`web/src/lib/app/shortcuts.ts:64`) | Modifier-aware registry (§3.10), wave 1 |
| W2 | The server logs to stderr only: a support bundle from the server would contain no server log (`argos/server/__main__.py:99`) | A3, wave 1 |
| W3 | v1 `open-fits` publishes on `/ws/frames`, so a Review frame would replace the live image | A71 separate route |

(05 noted "Applies when live view restarts" in `CameraCard.svelte:64`; the client now has
`PATCH /api/camera/live`, `web/src/lib/api/client.ts:198`, and the text is gone: resolved.)


---

## 7. Implementation plan in waves

Each wave ships something an observer can use against the simulator and a Seestar, is
reviewed on screenshots at 1440 x 900 and 1280 x 800 in the three themes, and closes the
mapping rows (§2) it lists. Server work is Qt-free and tested in `tests/server/`; science
ports are tested against the Python functions they replace (as `stretch.ts` is today).

```
W1 shell + Connection ──► W2 Settings ──► W4 field + overlays ──► W5 live photometry ──► W7 Review
        │                      │                 ▲                        │                  ▲
        └──► W3 Observe acquisition ─────────────┘                        └──► W6 Plan ──────┘
                                                                                  W8 desktop + Qt retirement (after W7)
```

| Wave | Goal (smallest valuable increment) | API (§4.3) | Shared components | Screens and mapping rows closed | Exit criterion |
|---|---|---|---|---|---|
| **W1 Shell and Connection** | Start a night in the web UI: see and fix every device, find the Seestar, pick the profile; global log and status | A1-A4, A8-A10, A13-A18, A80 | Shortcut registry with modifiers + `?` sheet (W1 gap), `Dialog` / `ConfirmDialog`, `Popover`, `Menu`, `Select`, `Table` (basic), `Drawer` tabs + global Log tab, `PanelsPopover` + Reset layout, `JobProgress`, StatusBar global segments, rail footer (`theme`, Help popover), `StartupScreen` | Connection screen; Observe rail Connection card removed (D10), theme moved (D15); M1-M3, M9-M13, M17, M19, M21-M26 | Connect, discover, retry, disconnect each device without freezing; every Qt Connection control of 02 §2.2 has its web control |
| **W2 Settings** | Configure observer, site, paths, ASTAP, catalogues, privacy, appearance without Qt | A5, A6, A11, A67 (list only), A81-A84 | `SettingsForm` from config meta, `FilePicker`, `Sheet`, Undo toast, `SupportBundleDialog` | Settings screen (9 categories), Help popover items, About; M5-M6, M14-M16, M27-M37 | Every key of 02 appendix A editable or deliberately read-only; config changes sync live between two open clients |
| **W3 Observe: acquisition** | A full capture night: framing, filter, focus, autofocus, single FITS saves (lights, darks), jog, catalogue GoTo, Stellarium | A19-A31, A34-A41 | Segmented filter control, Jog pad, `VCurvePlot`, `ConditionsTimeline`, HUD chips | Camera, Mount, Focuser cards, Conditions drawer tab, Open FITS dialog, status-bar frame / HFD segments; Planetarium card (Connection); M4 (Open FITS), M38-M43, M48-M49, M59-M67 | Take shot writes correct FITS metadata (S1-S3 fixed); autofocus runs, cancels and halts cleanly; jog stops on key-up, blur and socket loss |
| **W4 Field identification and image tools** | Identify the field, see catalogues and roles on the image, click stars, centre the target; complete viewer tools | A32-A33, A43-A49, A51-A53 | Overlay layer (SVG), star card, viewer context menu, loupe, region tool, CFA preview and palettes (GPU), Statistics card, Catalogue layers popover, Settings sheet reuse | Observe Field group, popover, star card, Statistics card, Display card View options; M7, M44-M47, M50 (pre-checks only), M51-M58 | Overlays follow the tracked field; clicking a star assigns a role and writes `targets/<object>.json`; Night Red shows no non-red pixel |
| **W5 Live photometry** | Measure a variable star live: target set, ensemble, light curve, variables list | A50, A54-A58 | `LightCurvePlot`, `TargetSetList`, Ensemble table | Photometry card, drawer tabs Light curve / Variables / Ensemble; M8 (live parts), M78-M79, M95 (live tabs), M96-M99 | A sequence-free live run shows target and check curves identical to the Qt values (same points, same errors) |
| **W6 Plan** | Plan and run sequences, transits, presets, visibility | A42, A59-A66 | `VisibilityTimeline`, Steps table editors, run strip, Preflight popover | Plan screen; M68-M77 | A transit plan written by the web UI produces `observation.json` (S5); Stop / Pause / outcome visible; no silent clamp |
| **W7 Review** | Review sessions and the live run, export to AAVSO, inspect frames, re-run photometry | A67-A79 | Plot wall (facets, linked axis, cell menu, `expand-pane`), job strip, Export dialogs, `frame-prev` / `frame-next` | R0, R1, R2, Re-run dialog; M8 (re-run), M50, M80-M95, M100-M103 | Exports byte-identical to `write_aavso` / `write_curves_csv` for the sample sessions, with the new guards; a re-run writes a new folder inside the session |
| **W8 Desktop app and Qt retirement** | Ship the Tauri app; remove PyQt from the runtime | A7, A12 | Quit dialog + shutdown scrim, custom title bar (Night Red), native app menu (optional, Q-G10), crash notice, ⌘1-5 | M18, M20; optional multi-window (D27) | Every mapping row of §2 is "done"; Appendix A re-run on the final Qt tree shows nothing new; `PyQt6` and `pyqtgraph` leave the runtime dependencies |

Status note (2026-11-01): A19 (the Stellarium bridge) and the Planetarium card's Start /
Stop shipped with W1, so that the W1 exit criterion (every Qt Connection control of 02 §2.2
has its web control) holds; W3 keeps the Stellarium target-name suggestion. See
`progress.md`.

Ordering notes: W2 before W4 because plate solving needs the ASTAP settings and catalogue
budgets; W3 does not need W2 (camera, mount and focuser settings come from devices). The
Review wave is last because it depends on the job model (W1), the config (W2), the viewer
tools (W4) and the light-curve component (W5); its R0 session list (A67) can ship in W2 for
the support-bundle dialog.


---

## 8. Open questions for the owner

Deduplicated from the 119 questions of the area specs; questions already settled by a
decision of §1.3 are not repeated (the owner can veto any D-row). Each has a recommended
answer; the implementation follows it unless the owner says otherwise.

**Status (2026-11-01): the owner accepted every recommended answer below, and the D-rows of
§1.3, D2 included.** They are decisions now, not open questions: implement them as written.

### 8.1 Global, shell, platform

| # | Question | Recommended answer | Raised by |
|---|---|---|---|
| Q-G1 | When the desktop window closes, should a running sequence and the server stop, or keep running headless for a later reconnect? | Closing = quit; while something runs the Quit dialog says what will stop. A headless "keep observing" mode is a later feature. | 01 |
| Q-G2 | Device status: bottom status bar or a 2 x 2 block in the rail footer? | Status bar device cluster (D18); the rail footer keeps theme and help only. | 01 |
| Q-G3 | Theme quick toggle in the rail footer, and a shortcut? | Yes, one click cycles Observatory / Charcoal / Night Red with a popover on long-press; no shortcut. | 01, 02 |
| Q-G4 | UI scale preference (100 / 112 / 125 %)? | Not in v1; webview zoom covers it. | 01 |
| Q-G5 | Second monitor: Tauri multi-window pop-outs (Review, drawer, jog pad) in v1? | No (D27); revisit in wave 8 with "Open Review in a new window" first. | 01, 03, 05, 06, 07, 08 |
| Q-G6 | Preferences per viewer or in the shared server config (theme, rotation, layer toggles)? | Per viewer, seeded once from the Qt keys (`ui.theme.preset`, `ui.display.rotation`); science settings stay in the server config. | 01, 02, 03, 04 |
| Q-G7 | File pickers: Tauri native dialogs allowed outside Night Red, or the in-app picker everywhere? | In-app `FilePicker` everywhere (D20), served by a read-only listing limited to home and data paths. | 01, 02, 03, 07, 08 |
| Q-G8 | Documentation link: GitHub repository (Qt today) or the documentation site? | Documentation site (perretjules.com/argos per README) with GitHub as a second link and a local copy offline. | 01 |
| Q-G9 | ⌘ / Ctrl+1 … 5 as section alternates (F-keys need Fn on macOS)? | Yes in the desktop app; F1-F5 kept. | 01 |
| Q-G10 | A minimal native macOS menu bar (App, File, View, Help) in the desktop app? | Yes, mirroring the in-window commands, no extra functions. | 01, 07 |
| Q-G11 | First-run checklist (observer code, site, ASTAP) on Connection, and a Settings rail dot when they are missing? | Yes to both. | 01, 02 |
| Q-G12 | Language selector: drop until a translation exists? | Drop. | 01, 02 |
| Q-G13 | Reachability probe to 1.1.1.1 / 8.8.8.8 every 10 s? | Probe the Seestar only; check the internet on demand when an online lookup is attempted; show "not configured" distinctly. | 01, 02 |
| Q-G14 | Night Red window chrome and cursors? | Custom token-drawn title bar (Tauri `decorations: false`) in every theme; system cursors accepted. | 01 |
| Q-G15 | Credits for the web build? | IBM Plex (OFL), Svelte, uPlot, Tauri and the Python server stack; PyQt6 / pyqtgraph removed once Qt retires. | 01 |
| Q-G16 | Plot and viewer export (pyqtgraph "Export…")? | "Copy data (TSV)" per plot, "Save view as PNG" on the viewer; no SVG / print. | 01, 04, 08 |
| Q-G17 | Support bundle: include session metadata by default? | Off by default. | 01 |
| Q-G18 | Log timestamps: UTC only or a local toggle? | UTC (BRAND 5), local time in the tooltip. | 01 |
| Q-G19 | Default landing section? | Connection when nothing is connected and no frame is shown, otherwise the last section (Qt rule, 01 §2.4.1). | 01, 02 |

### 8.2 Connection and Settings

| # | Question | Recommended answer | Raised by |
|---|---|---|---|
| Q-C1 | Sensor limits: keep `camera.full_well_adu` / `linearity_max_adu` (what the code reads) or move readers to the profile + `hardware.overrides`? ADC bits editable? | Move readers to profile + overrides; Settings › Instrument edits the overrides; ADC bits read-only. | 02 |
| Q-C2 | Unvalidated-profile wording? | "Not validated on this hardware: do not use it for scientific photometry." everywhere. | 02 |
| Q-C3 | Stellarium bridge host: 127.0.0.1 only or LAN? | 127.0.0.1 by default; LAN binding behind an explicit setting with a warning. | 02 |
| Q-C4 | Expose config-only keys (`astrometry.live_*`, `photometry.default_band`, `read_noise_e`, `min_comparisons`, `systematic_floor_mag`, `comparison_validation_*`, `track_apertures`, `camera.egain_table`)? | Yes under "Advanced" disclosures generated from config meta; `photometry.default_band` visible in Settings › Photometry and in the AAVSO dialog. | 02, 08 |
| Q-C5 | Confirm "Disconnect all": always, only while something runs, never? | Only while something runs (§3.3). | 02 |
| Q-C6 | Per-category "Restore defaults"? | Yes, text button + confirmation (no new icon, §5). | 02 |
| Q-C7 | Remove dead keys (`field_stars_max_results`, `named_objects_max_results`, `ui.window_state`, `ui.window_geometry`, `ui.language`, `camera.adc_bits`)? | Yes, with a config migration that ignores them. | 02, 01 |
| Q-C8 | "About this setting" help column at ≥ 1440 px? | Yes, fed by config meta (key, default, used by). | 02 |
| Q-C9 | ASTAP database set vs folder? | Now: show "ignored while a folder is set"; later: core passes both `-D` and `-d`. | 02 |
| Q-C10 | Show the default site read-only on Connection? | Yes, Instrument card footer with a Settings link. | 02 |

### 8.3 Observe, viewer, hardware

| # | Question | Recommended answer | Raised by |
|---|---|---|---|
| Q-O1 | Point identification queries Gaia / SIMBAD on every click on an unmarked star: keep automatic? | Automatic only when online lookups are enabled in Settings › Privacy; otherwise local catalogues only. | 03 |
| Q-O2 | Layer toggles and Gaia depth: per viewer or server? | Layer toggles per viewer; display depth in server config (as Qt). | 03, 04 |
| Q-O3 | Sync: keep (no-op today), redefine, or drop? | Redefine as "Sync to plate solution" (no slew) in the Solved-field row with an inline confirmation. | 03, 05 |
| Q-O4 | Jog labels on the alt-az Seestar: N / S / E / W or axis words? | Axis words on Alt-Az (Alt + / Alt − / Az − / Az +), N / S / E / W on EQ, chosen from `MountState.alignment`. | 05 |
| Q-O5 | Filter row without a wheel: metadata-only selection or disabled? | Metadata only, with the note "no filter wheel: written to FITS FILTER only". | 05 |
| Q-O6 | Autofocus: Stop AF = cancel and return to start, Halt = stop where it is? | Agree. | 05 |
| Q-O7 | Focus step keys `[` `]` (BRAND 7 forbids single keys that move hardware)? | No shortcut; buttons only. | 05 |
| Q-O8 | Escape also cancels autofocus? | No: Esc stops slew, jog and a manual focuser move only (D21). | 05 |
| Q-O9 | Autofocus parameters (half range, steps, settle, AF exposure / gain): expose? Used by mid-run AF? | Yes in Settings › Instrument "Autofocus" (advanced), used by Observe and by mid-run AF; the 120 s handshake raised to cover the sweep. | 05, 06 |
| Q-O10 | HFD colour thresholds (5 / 10 px)? | Drop the colours; show numbers and the Conditions trend. | 05 |
| Q-O11 | Opening a FITS while live view runs? | Stop live view first, with a toast. | 03 |
| Q-O12 | Arm auto-identification for every sequence, even without a prior solution? | Yes. | 03 |
| Q-O13 | Capture settings (exposure, gain, frame type, filter, offset, binning): shared on the server or per viewer? | Shared on the server, survive reloads. | 05 |
| Q-O14 | Preview quality (Full / Half): keep or replace by stream decimation? | Replace by a client-chosen stream decimation; metrics always on the full frame (A26). | 05 |
| Q-O15 | Offer Lunar / Solar tracking? | Only when the driver lists them (A29). | 05 |
| Q-O16 | Crosshair: centre reticle, cursor lines, or both? | Both: centre by default, "Cursor" in View options. | 04 |
| Q-O17 | Default Preview: Colour or Raw CFA? | Colour in Observe and R2. | 04, 07 |
| Q-O18 | Hit-test hidden layers? VSP candidates default? | Observe rule everywhere: hidden layers still identify; VSP off by default and near detected sources only. | 04 |
| Q-O19 | Star aperture vs photometry aperture: two radii? persist? | Two radii with labelled ring styles; persist `imaging.star_radius_px`. | 04 |
| Q-O20 | Cursor RA / Dec in the status bar when solved? | Yes. | 04 |
| Q-O21 | Show the effective ADC depth ("12-bit, 16 ADU steps")? | Yes. | 04 |
| Q-O22 | CFA preview on the GPU (client) or server-rendered? | GPU in the client. | 04 |
| Q-O23 | Loupe magnification? | 4x default, 2 / 4 / 8 in View options. | 04 |
| Q-O24 | Open the Light curve drawer tab automatically when a run starts? | No; badge the tab instead. | 03 |
| Q-O25 | Design tokens: `--viewer-saturated`, `--overlay-vsp`; saturated pixels black in Night Red? | Yes (design team, §5). | 03, 04 |
| Q-O26 | Role shortcuts on the star card (they write `targets.json`)? | None. | 04 |

### 8.4 Plan

| # | Question | Recommended answer | Raised by |
|---|---|---|---|
| Q-P1 | Several objects per night in one plan? | Out of scope for v1. | 06 |
| Q-P2 | Scheduled "Start at" (transit coverage start)? | Yes; `start` with the label "Start at hh:mm", worker waits (A62). | 06 |
| Q-P3 | Persist the draft plan server-side across restarts? | Yes, `sequence_draft.json` beside `config.json`. | 06 |
| Q-P4 | Presets: server list + file import / export, or file dialogs only? | Server list + import / export. | 06 |
| Q-P5 | Dithering on a Seestar: keep, hide, remove? | Hide the column by default (column menu), keep for EQ mounts; fix the model docstring. | 06 |
| Q-P6 | Visibility: 30° limit as a site setting? Twilight and Moon? Night window? | Site setting (default 30°); night = astronomical dusk to dawn; Moon later. | 06 |
| Q-P7 | Confirm Stop sequence? | Yes (§3.3). | 06 |
| Q-P8 | Plan Find on a non-variable (M 42): photometry target or only observation and pointing? | Only observation and pointing. | 06 |
| Q-P9 | Editing the plan while running? | Locked; the target set stays editable (journalled). | 06 |
| Q-P10 | Transit prediction: choose the date and skip daylight / below-limit transits? | Yes. | 06 |

### 8.5 Review and photometry

| # | Question | Recommended answer | Raised by |
|---|---|---|---|
| Q-R1 | Re-run photometry in Review (D2) with a session-scoped reference and output `<session>/photometry_rerun_<UTC>/`? Compare live and re-run side by side? | Yes; comparison view later. | 03, 07, 08 |
| Q-R2 | AAVSO export with no observer code; FILT from the configured band or the session filter? | Block until the code is set (link to Settings); keep the configured band (TG) and warn when the session filter looks inconsistent. | 07, 08 |
| Q-R3 | Exclude saturated and suspect points from AAVSO exports by default; note them? | Exclude by default with counts in the preview; a NOTES entry when included. | 08 |
| Q-R4 | Browser build: open folders / CSVs outside `sessions_path` through the server? | Only by an explicitly typed path from the token holder; listing limited to home and data paths. | 07, 08 |
| Q-R5 | Session list roots: only `sessions_path` or several? | `sessions_path` + folders opened explicitly (remembered). | 07 |
| Q-R6 | Default light-curve time axis? | UTC clock (D26), JD / BJD_TDB one click away. | 07, 08 |
| Q-R7 | Surface star_var_script outputs (`results/`, `process/`) and `diagnostics/` in Review? | Later; list them as files in the Session card. | 07 |
| Q-R8 | Post-hoc ensemble editing in Review? | No in v1; use Re-run with an edited target set. | 07, 08 |
| Q-R9 | Precision: magnitudes and scatter? | Magnitudes 3 decimals ± error (BRAND 5); scatter and formal errors 4 decimals. | 08 |
| Q-R10 | Aperture / annulus changes during a sequence? | Locked while a sequence runs (`409 run_active`, reason in the form). | 08 |
| Q-R11 | Exclude saturated points from the relative-flux normalisation median? | Yes. | 08 |
| Q-R12 | Changing the proposed comparison count: complete or replace the ensemble? | Complete (`propose`); replacing is the explicit Recommend action. | 08 |
| Q-R13 | Compute the comparison quality report during plain live preview? | Yes. | 08 |
| Q-R14 | Check star in the Observe light-curve drawer? | Yes, target + check (D25). | 08 |


---

## Appendix A: coverage check of Qt control constructions

Method (read-only, reproducible; the script `coverage_final.py` is kept outside the repository, in
the synthesis scratch folder): it greps
`argos/ui/**/*.py` for every construction of `QPushButton`, `QToolButton`, `QAction`,
`QCheckBox`, `QRadioButton`, `QComboBox`, `QSpinBox`, `QDoubleSpinBox`, `QSlider`, `QLineEdit`,
`QMenu`, `QMessageBox.*`, `QFileDialog.*`, `QDialog` (constructions and subclasses), `QInputDialog`,
`.addAction(`, `.addMenu(`, `.setShortcut(`, the `design.py` buttons (`PrimaryButton`,
`SecondaryButton`, `SuccessButton`, `DangerButton`) and the two local `QPushButton` subclasses
(`_JogButton` manual_control_dialog.py:56, `_JogArrowButton` mount_dock.py:445). Comments,
docstrings, imports, type hints, enum uses (`QMessageBox.StandardButton`), `findChild` look-ups and
`theme.py` stylesheet selectors are excluded. A hit is **covered** when a `web/spec/0*.md` file cites
its file and line within ±1 line (explicit `file.py:N`, an abbreviation such as `SP:N` / `AP:N`,
a `:N` continuation, or a bare line number in an inventory row of a section about that file), or
when it is a helper whose every call site is covered. Remaining hits were checked by hand.

| Result | Hits |
|---|---|
| covered by a cited file:line (±1) | 291 |
| covered through all call sites of a helper | 2 |
| covered, verified by hand | 2 |
| **Total constructions** | **295** |
| **Covered** | **295** |
| **Uncovered** | **0** |

Excluded from the count: 36 stylesheet lines of `theme.py`, 7 button class definitions
(`design.py:312-349`, `_JogButton`, `_JogArrowButton`; their instances are counted), 123 mentions
that construct nothing.

Hits by construct: `addAction` 34, `QComboBox` 33, `design.SecondaryButton` 27, `QSpinBox` 24, `QLineEdit` 23, `QCheckBox` 22, `QPushButton` 21, `QFileDialog` 18, `QDoubleSpinBox` 17, `QAction` 16, `QMessageBox` 12, `design.PrimaryButton` 8, `design.SuccessButton` 7, `addMenu` 5, `QToolButton` 5, `design.DangerButton` 5, `setShortcut` 4, `local QPushButton subclass` 4, `QMenu` 4, `QSlider` 3, `QDialog subclass` 2, `QDialog` 1.

Hits checked by hand or through call sites (none is uncovered):

| Ref | Source | Covered by |
|---|---|---|
| panels/photometry_window.py:159 | `spin = QDoubleSpinBox()` | helper; call sites 75, 82, 89 all cited in 07 |
| pages/configuration_page.py:287 | `clear_btn = design.SecondaryButton("Refresh")` | 02: cache "Refresh" buttons, rows #8, #11, #14 … of 02 §1.10 ("287-292, 434") |
| widgets/camera_dock.py:221 | `combo = QComboBox()` | helper; call sites 117, 132, 180 all cited in 05 |
| widgets/sequence_panel.py:255 | `btn = design.SecondaryButton(label)` | 06: loop creating the five step buttons; each is a row of 06 §1.4 (#11-#15, SP:249-253) |

Per file (line numbers of every hit, grouped by the spec that inventories it):

| File (`argos/ui/`) | Hits | Lines -> spec |
|---|---|---|
| pages/configuration_page.py | 48 | 01: 726, 733, 740, 1017, 1026, 1035, 1130, 1188, 1195; 02: 151, 155, 162, 178, 186, 195, 203, 208, 226, 228, 231, 244, 247, 269, 282, 287, 304, 307, 349, 364, 396, 426, 439, 452, 465, 478, 499, 525, 616, 622, 628, 647, 651, 662, 670, 680, 689, 696, 704 |
| shell.py | 45 | 01: 191, 192, 193, 196, 197, 198, 203, 204, 211, 212, 215, 216, 223, 227, 231, 232, 234, 237, 243, 244, 247, 248, 258, 260, 262, 263, 269, 270, 277, 278, 281, 282, 481, 494, 503, 526, 528, 537; 02: 206, 221, 225, 239, 265; 07: 201, 285 |
| widgets/sequence_panel.py | 35 | 01: 526, 527, 530, 899, 913; 06: 255, 280, 293, 310, 319, 324, 328, 331, 354, 367, 380, 389, 396, 406, 411, 418, 433, 455, 457, 466, 468, 472, 683, 693, 698, 705, 713, 718, 724, 732 |
| widgets/astrometry_settings.py | 26 | 01: 48, 94, 96, 103, 107, 347; 02: 113, 118, 124, 139, 146, 152, 155, 171, 178, 187, 193, 201, 210, 218, 226, 235, 241, 245, 253; 08: 262 |
| pages/analyze_page.py | 23 | 01: 257, 259, 261, 263, 281, 291, 295, 298, 429, 431, 437, 443, 606, 614, 717, 733, 766; 07: 140, 179, 277, 278, 283, 287 |
| widgets/mount_dock.py | 20 | 01: 426; 05: 116, 119, 138, 145, 156, 174, 176, 181, 197, 201, 210, 212, 215, 229, 246, 252, 270, 273, 276 |
| pages/imaging_page.py | 16 | 01: 370, 384, 388, 396, 402, 1320, 2262, 2268, 2273, 2284, 2291, 2344; 05: 364, 366, 373, 380 |
| pages/connection_page.py | 10 | 02: 82, 122, 159, 162, 176, 182, 187, 209, 211, 425 |
| panels/photometry_window.py | 9 | 01: 306, 316; 07: 64, 96, 109, 124, 159, 244; 08: 240 |
| widgets/histogram_dock.py | 9 | 04: 112, 128, 134, 138, 142, 147, 153, 201; 07: 117 |
| widgets/focuser_dock.py | 7 | 05: 83, 88, 91, 99, 103, 116, 118 |
| widgets/camera_dock.py | 6 | 05: 122, 156, 166, 204, 207, 221 |
| widgets/comparison_table.py | 5 | 07: 113, 119, 125; 08: 81, 110 |
| panels/manual_control_dialog.py | 4 | 01: 66; 05: 105, 131, 137 |
| widgets/star_info_card.py | 4 | 03: 105; 04: 59, 92, 100 |
| analysis_window.py | 3 | 01: 441; 07: 251, 260 |
| design.py | 3 | 05: 217, 222, 227 |
| panels/stellarium_card.py | 3 | 02: 71, 76, 98 |
| widgets/image_toolbar.py | 3 | 03: 80; 04: 51, 57 |
| widgets/overlay_bar.py | 3 | 01: 120; 04: 98, 142 |
| widgets/variable_table.py | 3 | 06: 75, 82, 111 |
| widgets/lightcurve_panel.py | 2 | 07: 85, 90 |
| widgets/target_table.py | 2 | 06: 47, 49 |
| panels/log_panel.py | 1 | 01: 42 |
| widgets/comparison_curve_panel.py | 1 | 07: 38 |
| widgets/hfd_history_dock.py | 1 | 05: 90 |
| widgets/metrics_panel.py | 1 | 05: 38 |
| widgets/session_review.py | 1 | 07: 30 |
| widgets/target_curve_panel.py | 1 | 07: 37 |

Supplementary pass (not required by the brief, same method, ±2 lines): containers and input
handlers that can hide controls: `QTabWidget`, `QTableWidget`, `QDockWidget`, `QProgressDialog`,
`QSplashScreen`, `QToolBar`, `QGroupBox`, `QTextEdit`, `QPlainTextEdit`, `QMainWindow`,
`QStackedWidget`, `QToolBox`, `QSplitter`, key / mouse / close event handlers and pyqtgraph click /
hover signals.

| Result | Hits |
|---|---|
| covered (±2 lines or call sites) | 46 |
| covered by a section range, verified by hand | 2 |
| not cited by line, verified by hand | 2 |
| **Total** | **50** |

Hand-verified rows: `pages/imaging_page.py:350` (`QToolBar` of the panel strip, 03 §1.3 range 348-391);
`widgets/sequence_panel.py:229` (steps `QTableWidget`, 06 §1.4 SP:222-271); `widgets/comparison_table.py:225`
(`QTableWidget` inside `ComparisonQualityTable`, inventoried as a whole in 07 §1.5 CT:208-232 and 08 §1.13
comparison_table.py:208-246); `design.py:93` (`Card(QGroupBox)`, a layout container with no control,
out of scope).

Limits of the check: it proves that each construction is **cited** by an inventory, not that the
inventory row is correct; implicit controls (pyqtgraph menus, `QCompleter` pop-ups, dock title-bar
buttons, Qt edit menus) are not constructions and were checked through the census of 01 §A and the
scope tables of each spec instead.
