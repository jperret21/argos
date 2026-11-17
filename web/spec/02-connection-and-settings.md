# Connection and Settings: Qt inventory and web redesign

Spec 02 of the web UI rewrite. Source of truth: the Qt code on branch `explore/web-ui`
(every claim below carries a `file:line`). Read with `web/src/design/BRAND.md`,
`web/src/design/icon-inventory.json`, `argos/server/protocol.md` and the existing Observe
screen (`web/src/App.svelte`, `web/src/lib/**`).

Notation in tables: `1.n #k` = control k of inventory section 1.n. In wireframes `{id}` is an
icon from `icons/<id>.svg`, `(o)` / `(x)` are CSS status dots (never Unicode pictographs,
BRAND 4.3), `[ ... ]` is a field, `<Label>` a button.

---

## 0. Scope

### 0.1 Files covered

| File | Lines | Role |
|---|---|---|
| `argos/ui/pages/connection_page.py` | 471 | Connection page, start card, device cards, bulk row |
| `argos/ui/panels/stellarium_card.py` | 167 | Stellarium telescope-control server card |
| `argos/ui/pages/configuration_page.py` | 1269 | Settings page (5-section accordion) |
| `argos/ui/widgets/astrometry_settings.py` | 396 | "Field identification & catalogue settings" modal dialog |
| `argos/core/config.py` | 396 | Config defaults, load/save, migrations (appendix A) |
| `argos/workers/discovery_worker.py` | 64 | Discovery thread |
| `argos/workers/network_monitor.py` | 84 | Seestar / internet reachability thread |
| `argos/workers/stellarium_worker.py` | 130 | Stellarium asyncio server thread |
| Followed for real effects | | `argos/core/session/device_session.py` (199-263, 265-567, 783-831), `argos/core/alpaca/discovery.py` (1-47, 167-199), `argos/core/alpaca/client.py` (87-88), `argos/core/hardware/{active.py, catalog.py, profile.py}`, `argos/core/location_resolver.py`, `argos/workers/location_resolver_worker.py`, `argos/core/imaging/platesolve.py` (119-144, 305-319), `argos/core/imaging/astrometry_session.py` (40-73), `argos/ui/shell.py` (93-96, 185-265, 319-361, 409-411, 463-472), `main.py` (97-175), `argos/ui/statusbar.py` (152-168) |

### 0.2 Every window, page, panel and pop-up in scope

| Ref | Element | Class, file:line | Kind | How opened | Modal |
|---|---|---|---|---|---|
| 1.1 | Connection page | `ConnectionPage`, connection_page.py:49 | Page in the main `QStackedWidget` (shell.py:153-155), scroll page (76-77) | Sidebar "Connection" (sidebar.py:39); View menu F1 (shell.py:230-234); click on a *disconnected* device badge in the top status bar (shell.py:409-411); landing page at start-up when the last mode was Observe or unknown (shell.py:93-96) | No |
| 1.2 | Start card "Telescope · equipment" | `design.Card`, connection_page.py:109-169 | Card, always visible | With the page | No |
| 1.3 | "Individual devices" (4 device cards) + bulk row | `_DeviceCard` connection_page.py:383-471; bulk row 206-215 | Collapsed region | Disclosure button "Show connection and device details" (82-85, 260-267); collapsed at every launch (104) | No |
| 1.4 | Stellarium card ("Planetarium") | `StellariumCard(QGroupBox)`, stellarium_card.py:33 | Group box inside 1.3's collapsed region (94-103) | Same disclosure | No |
| 1.5 | Network reachability | `NetworkMonitor`, network_monitor.py:48 -> `TopStatusBar.set_network`, statusbar.py:152-168 | Display only (top status bar), behaviour behind the Connection page | Always running from start-up (shell.py:130-133) | No |
| 1.6 | Settings page | `ConfigurationPage`, configuration_page.py:57 | Page, `QToolBox` accordion of 5 sections (86-111), max width 940 (78) | Sidebar "Settings" (sidebar.py:43); View menu F5 | No |
| 1.7 | Settings › Observatory | card "Observer · Site", 141-265 | Accordion section 1 | Accordion header | No |
| 1.8 | Settings › Equipment · camera | cards "Telescope" 520-556, "Camera" 608-637 | Accordion section 2 | Accordion header | No |
| 1.9 | Settings › Astrometry | card "Astrometry (plate solving)", 639-714 | Accordion section 3 | Accordion header | No |
| 1.10 | Settings › Catalogues · data | card "Data · catalogues", 319-518 | Accordion section 4 | Accordion header | No |
| 1.11 | Settings › Files · application | cards "Observation files" 297-317, "Appearance" 716-764, "About" 766-773 | Accordion section 5 | Accordion header | No |
| 1.12 | Cache clear confirmation | `QMessageBox.question`, configuration_page.py:1130-1137 | Message box | Any "Refresh" button of 1.10 | Yes |
| 1.13 | Native file / folder pickers (10 call sites) | `QFileDialog`, configuration_page.py:1017, 1026, 1035 (x5), 1188, 1195; astrometry_settings.py:347 | OS dialogs | "Browse…" buttons | Yes |
| 1.14 | Dialog "Field identification & catalogue settings", tab "Plate solving" | `AstrometrySettingsDialog(QDialog)`, astrometry_settings.py:48, 90-126 | Modal dialog, `exec()` | Field → "Configure field identification…" (shell.py:260-262, opens this tab) | Yes |
| 1.15 | Same dialog, tab "Field catalogue" + Save / Cancel | astrometry_settings.py:128-268, 77-82 | Modal dialog tab | Field → "Configure catalogues…" (shell.py:263-265); Observe overlay bar "Catalogues / depth…" (overlay_bar.py:120-126 -> imaging_page.py:1427-1432); analysis window (analysis_window.py:564-569) | Yes |

No `QMenu`, context menu, `setShortcut`, drag-and-drop target, double-click handler or
tooltip-driven popover exists in the four UI files (re-scanned with grep). Every tooltip is
listed in the control tables.

### 0.3 Cross-area entry points (inventoried by the shell spec, placed by this spec)

| Qt | file:line | Proposed web home (2.1) |
|---|---|---|
| More → "Documentation & website" | shell.py:212-215, 602-605 | Settings › About |
| More → "Create local support bundle…" (+ 2 message boxes, 2 file dialogs) | shell.py:216-221, 478-533 | Settings › Privacy & diagnostics |
| More → "About & credits" (About dialog) | shell.py:223-225, 535-600 | Settings › About |
| Field → "Configure field identification…" / "Configure catalogues…" | shell.py:260-265 | Observe popovers (2.3 W9) + Settings |
| View → "Reset Window Layout" | shell.py:237-239, 452-457 | Not here (layout belongs to each screen spec) |

---

## 1. Inventory (Qt, as it is today)

### 1.1 Connection page (`ConnectionPage`, connection_page.py:49, page, not modal, full-width scroll page)

- Purpose: the start-of-night set-up stop: choose the instrument model, enter or discover the
  Seestar address, connect the four Alpaca devices, run the Stellarium bridge.
- Layout top to bottom (79-107): heading "Connection" (79), start card 1.2 (80), disclosure
  button (82-85), collapsed region 1.3 + 1.4 (87-105).
- The page emits intents only; the Shell routes them to `DeviceSession` (shell.py:319-340).
- Controls: see 1.2, 1.3, 1.4 (16 in total).

Implicit behaviours (whole page)

| Behaviour | Where |
|---|---|
| Form→config sync muted until `_load_config` has run (`_loading`) | 63, 347-351 |
| Host and port loaded from `alpaca.host` / `alpaca.port` (default 32323) | 349-350 |
| Device state arrives from `ImagingPage.device_state_changed` (re-emitted from `DeviceSession`), fanned out by the Shell to the status bar and this page | shell.py:305, 367-372; imaging_page.py:513, 530, 658 |
| `set_device_state` updates the card and recomputes the summary, the connect/disconnect enablement and the telescope-combo lock | 226-230, 269-305 |
| Discovery result fills host + port (`set_discovered_address`), which persists through `textChanged` | 232-235, shell.py:327 |
| Stellarium state and client count arrive from `DeviceSession` signals | shell.py:337-340 |
| Every connect call runs synchronously on the GUI thread (blocking HTTP: 5 s GET, 10 s PUT timeouts) | device_session.py:265-488; client.py:87-88 |
| Mount poll every 2 s re-emits `connected` with an empty info, or `busy` "slewing" | device_session.py:552-555 |
| Mount connection lost -> state `error` with empty info, auto-retry every 10 s until the user disconnects | device_session.py:155-160, 299-333, 557-567 |
| Connecting camera checks the profile against the camera (name, size) and logs mismatches; never switches profile | device_session.py:368-390 |
| No auto-connect and no auto-discovery at start-up; Observe is never restored at start-up | shell.py:69-72, 93-96 |
| All session messages go to the Observe page's Activity log, not to this page; the "action" text goes to the top status bar | imaging_page.py:515-516, 614; shell.py:307 |

Messages produced by actions started on this page (exact text; where shown)

| Text | Level | Shown in | Source |
|---|---|---|---|
| "Starting Alpaca discovery…" | INFO | Observe log | device_session.py:202 |
| "No Alpaca devices found (broadcast, direct probes and subnet scan)." | WARN | Observe log | device_session.py:215-217 |
| "Found {host}:{port}" | OK | Observe log | device_session.py:220 |
| "Discovery: {message}" | ERROR | Observe log | device_session.py:224 |
| "Connecting mount {host}:{port}…" (also camera / filter wheel / focuser) | action | Top status bar | device_session.py:268, 354, 433, 463 |
| "Mount connected: {name}" | OK | Observe log | device_session.py:275 |
| "Mount coordinates: {system} → Argos J2000 conversion enabled." | INFO | Observe log | device_session.py:277-280 |
| "Mount coordinate system unavailable; assuming the driver accepts J2000." | WARN | Observe log | device_session.py:282-285 |
| "Mount clock is {h} h off — correct date/time in the Seestar app; GoTo and Sync are disabled." | ERROR | Observe log | device_session.py:287-291 |
| "Mount: {exc}" / "Camera: {exc}" / "Filter wheel: {exc}" / "Focuser: {exc}" | ERROR | Observe log; card shows `str(exc)[:48]` | device_session.py:296-297, 365-366, 447-448, 487-488 |
| "Camera connected: {name}" | OK | Observe log | device_session.py:362 |
| "Profile mismatch — {note}" | WARN | Observe log | device_session.py:384 |
| "This looks like a {name} — change it in Settings → Telescope." | WARN | Observe log | device_session.py:388-390 |
| "Camera limits: gain {min}–{max}, exposure {min}–{max}s[, offset][, bin ≤{n}]" | INFO | Observe log | device_session.py:409-415 |
| "Filter wheel connected — {position}" | OK | Observe log | device_session.py:444 |
| "Focuser connected: {name}  pos={pos}" | OK | Observe log | device_session.py:484 |
| "Mount disconnected." / "Camera disconnected." / "Filter wheel disconnected." / "Focuser disconnected." | INFO | Observe log | device_session.py:349, 428, 458, 501 |
| "Disconnected" | action | Top status bar | device_session.py:263 |
| "Mount connection lost." then "Retrying the mount every 10s — disconnect to stop." | ERROR / INFO | Observe log | device_session.py:558, 566 |
| "Mount reconnected: {name}" | OK | Observe log | device_session.py:314 |
| "Poll: {message}" | WARN | Observe log | device_session.py:541 |
| "Refused telescope profile change while equipment is connected" | warning | Python log only (not visible) | connection_page.py:250 |
| "{Device} connect — not implemented yet" | action | Top status bar (unreachable from this page) | device_session.py:238 |

### 1.2 Start card "Telescope · equipment" (`design.Card`, connection_page.py:109-169, card, always visible)

- Purpose: the one-glance nightly checklist: instrument model, Alpaca endpoint, four device
  states, connect / disconnect everything.

| # | Control | Qt type | Label / tooltip (exact) | Default / range / units | Enabled / visible when | Shortcut | Action: handler -> effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Telescope model | `QComboBox` 122-130 | Row label "Telescope". Tooltip "Select the physical telescope before connecting equipment."; when locked "Disconnect equipment before changing telescope model. The model controls plate scale, sensor geometry and FITS metadata." (300-305). Options (catalog.py:99): "ZWO Seestar S30 Pro", "ZWO Seestar S30 (unvalidated)", "ZWO Seestar S50 (unvalidated)" (suffix 125) | Active profile (127-128); default `s30pro` (config.py:68) | Disabled while any device is connected or busy (298-299) | — | `_on_telescope_changed` 307-314 -> `telescope_profile_requested` -> `Shell._on_telescope_profile_requested` shell.py:355-358 -> `apply_telescope_profile` 237-258: refuse (log only, combo restored) if a device is connected/busy; else `config.set("hardware.profile")`, `active.set_profile(apply_overrides(profile, hardware.overrides))` (active.py:56-89), refresh specs; then `ConfigurationPage.sync_telescope_profile` | `hardware.profile` |
| 2 | IP address | `QLineEdit` 176-180 | Row label "IP address"; placeholder "192.168.x.x"; tooltip "IPv4 address of the Seestar on the current network" | `alpaca.host` (349), default "" | Always | — | `textChanged` -> `_on_host_changed` 353-356 -> `config.alpaca_host = text.strip()` (writes the JSON file on every keystroke, config.py:241-248) | `alpaca.host` |
| 3 | Port | `QSpinBox` 182-186 | Row label "Port"; no tooltip | 1-65535, default 32323 (350), max width 96 px | Always | — | `valueChanged` -> `_on_port_changed` 358-361 -> `config.alpaca_port` | `alpaca.port` |
| 4 | Discover | `design.PrimaryButton` 187-190 | "⚡  Discover"; tooltip "Send an Alpaca UDP discovery broadcast" | — | Always (no busy state) | — | `discover_requested` -> `DeviceSession.discover` device_session.py:199-211: ignored while a scan runs; `DiscoveryWorker(port=alpaca.port, candidates=(alpaca.host, profile.ap_host "10.0.0.1"), timeout=8)` -> `discover_all` discovery.py:167-199: UDP broadcast on 32227 for 8 s; else HTTP probe of each candidate (2 s); else TCP sweep of the local /24 (0.4 s, 64 workers) + HTTP confirm. First device -> `discovered_address` -> fills #2 and #3 (232-235) | via #2 / #3 |
| 5 | Connect equipment | `design.SuccessButton` 159-161 | "Connect equipment"; becomes "Equipment ready" (293); tooltip "Connect telescope, camera, filter wheel and focuser" | — | Disabled only when all 4 devices are `connected` (289-294) | — | `_on_connect_all` 370-375: returns silently when #2 is empty; else `connect_all_requested(host, port)` -> `DeviceSession.connect_all` 252-256: `connect_mount`, `connect_camera`, `connect_filterwheel`, `connect_focuser` in sequence (each also writes `alpaca.host/port`, 266-267 etc.) | `alpaca.host`, `alpaca.port` |
| 6 | Disconnect equipment | `design.DangerButton` 162-166 | "Disconnect equipment"; tooltip "Disconnect telescope, camera, filter wheel and focuser from Argos" | — | Enabled when any device is connected or busy (295-297) | — | `disconnect_all_requested` -> `DeviceSession.disconnect_all` 258-263: camera (engine releases live/single first, acquisition_engine.py:432-438), mount (stops auto-retry), filter wheel, focuser (engine stops autofocus, acquisition_engine.py:198). No confirmation | — |
| 7 | Show / hide details | `QPushButton` class secondary 82-85 | "Show connection and device details" / "Hide connection and device details" (263-267) | Collapsed (104) | Always | — | `_toggle_advanced` 260-267: show/hide 1.3 + 1.4 | No (collapsed at every launch) |

Displayed data

| Readout | Source | Refresh |
|---|---|---|
| Specs line "{aperture} mm · f/{ratio} · {sensor} · {scale}″/px · {w}° × {h}°" (e.g. "30 mm · f/5.3 · IMX585 · 3.74″/px · 3.99° × 2.24°") | `active.profile()` derived properties, profile.py:94-121 | On profile change (257, 325-333) |
| Warning (colour `theme.WARNING`) "Unvalidated profile — do not use it for scientific photometry: " + caveats joined " · " (catalog.py:33-37) | 135-138, 334-341 | Same; hidden for a validated profile |
| Summary grid 2x2: "●  Telescope — Ready" / "○  Camera — Error" / "Busy" / "Disconnected"; colour success / warning / danger / muted | `_refresh_summary` 269-288 | Every device-state change |

Problems found

- The summary drops the error reason ("Error" only, 279); the reason lives in the collapsed
  device cards (1.3), truncated to 48 characters (device_session.py:297, 366, 448, 488).
- #5 with some devices already connected reconnects all four: `connect_mount` replaces
  `_telescope` and `_start_polling` starts a second `MountPollingWorker` without stopping the
  first (device_session.py:265-294, 525-532); `connect_camera` drops the previous `Camera`
  without `disconnect()` (351-358).
- Empty host: #5 does nothing and says nothing (373-374).
- Connect runs on the GUI thread: with an unreachable host, "Connect equipment" can freeze the
  window for about 4 x 10 s (PUT timeout, client.py:88); the "Connecting…" action text may not
  even repaint.
- Discovery gives no feedback on this page: no busy state on #4, repeated clicks are silently
  ignored (device_session.py:200-201), results and failures only reach the Observe log; only
  the first device found is used (device_session.py:219). Worst case about 8 s + 2 x 2 s + ~2 s
  sweep + 2 s per hit (constants, discovery.py:30-34), not measured.
- #2 writes the config file on every keystroke, and `NetworkMonitor` then probes partial
  addresses (network_monitor.py:80-82).
- Unvalidated wording differs from Settings: here "do not use it for scientific photometry"
  (338), in Settings "never run on this hardware" (configuration_page.py:580); combo suffix
  " (unvalidated)" (125) vs "  (unvalidated)" (configuration_page.py:528); the specs line
  omits pixel size and Bayer pattern shown in Settings (configuration_page.py:568-571).
- No confirmation for #6 even while a sequence runs; the engine releases only LIVE / SINGLE
  camera states (acquisition_engine.py:432-438), so a running sequence plausibly loses its
  camera mid-exposure (PLAUSIBLE, not run).
- Unicode pictograph in a label ("⚡", 187), forbidden by BRAND 4.3 in the web UI.

### 1.3 Individual devices + bulk row (connection_page.py:193-215, 383-471; collapsed region, not modal)

- Purpose: per-device connect / disconnect / retry with the device's status and error text;
  duplicate bulk actions.
- Device cards (198-203), grid 2x2, titles and hints from `_DEVICES` (41-46): "Telescope" /
  "Mount control via ASCOM Alpaca"; "Camera" / "Telephoto IMX585 sensor"; "Filter Wheel" /
  "Dark / IR / LP slots"; "Focuser" / "Telephoto focuser".

| # | Control | Qt type | Label / tooltip (exact) | Default | Enabled / visible when | Shortcut | Action: handler -> effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Telescope card button | `design.PrimaryButton` 425-427 | "↗  Connect" (disconnected), "✗  Disconnect" (connected or busy, danger style), "↗  Retry" (error) (448-463); no tooltip | Connect | Region expanded | — | `_on_button` 467-471 -> connect: `ConnectionPage._on_connect_one` 363-368 (silent return on empty host) -> `connect_requested(id, host, port)` -> `DeviceSession.connect_device` 230-240 -> `connect_mount` 265-297 (also `_start_polling`, mount mode to status bar). Disconnect: `disconnect_requested` -> `disconnect_device` 242-250 -> `disconnect_mount` 335-349 (stops auto-retry) | `alpaca.host/port` on connect |
| 2 | Camera card button | same | same | Connect | same | — | `connect_camera` 351-366 (profile check, capabilities, temperature poll) / `disconnect_camera` 417-428 | same |
| 3 | Filter Wheel card button | same | same | Connect | same | — | `connect_filterwheel` 430-448 / `disconnect_filterwheel` 450-458 | same |
| 4 | Focuser card button | same | same | Connect | same | — | `connect_focuser` 460-488 (temperature poll) / `disconnect_focuser` 490-501 | same |
| 5 | Connect all | `design.SuccessButton` 209-210 | "▶  Connect all" | — | Region expanded; never disabled | — | `_on_connect_all` 370-375 (same as 1.2 #5) | same |
| 6 | Disconnect all | `design.DangerButton` 211-212 | "■  Disconnect all" | — | Region expanded; never disabled | — | `disconnect_all_requested` (same as 1.2 #6) | — |

Displayed data per card: glyph "○" / "●" / "✗" coloured muted / success / warning / danger
(402-406, 431-446); status "Disconnected", "Connected — {info}", "Busy — {info}",
"Error — {info}" (448-461); the hint (415-419).

Problems found

- 1.3 #5 / #6 duplicate 1.2 #5 / #6 with different enablement (never disabled here).
- Hints are hard-coded to the S30 Pro: "Telephoto IMX585 sensor" is wrong for the S30
  (IMX662) and S50 (IMX462) profiles (41-46; catalog.py:65, 84).
- The 2 s mount poll overwrites "Connected — {name}" with "Connected" (device_session.py:552-555).
- Mount auto-retry shows as "Error" with no text; the retry loop is invisible here
  (device_session.py:563-567).
- A busy (slewing) mount can be disconnected without confirmation (448-455, 467-469).
- Pictographs "↗ ✗ ▶ ■" in labels (BRAND 4.3).

### 1.4 Stellarium card (`StellariumCard(QGroupBox)`, stellarium_card.py:33; inside 1.3's region under "Planetarium", connection_page.py:94-103; not modal)

- Purpose: run the Stellarium *Telescope Control* TCP server; Stellarium connects as a
  telescope, Ctrl+1 / ⌘+1 sends a GoTo that Argos forwards to the mount.

| # | Control | Qt type | Label / tooltip (exact) | Default / range | Enabled when | Shortcut | Action: handler -> effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | TCP port | `QSpinBox` 71-74 | Row label "TCP port"; no tooltip | 1024-65535; `stellarium.port` default 10001 (connection_page.py:96) | Disabled while the server runs (142) | — | Read at start (161) | `stellarium.port`, only when the server starts (device_session.py:794) |
| 2 | Start / Stop server | `QPushButton` 76-79 | "▶  Start server" (primary) / "■  Stop server" (danger) (126-141) | Stopped | Always | — | `_on_server_toggle` 157-161 -> start: `start_server_requested(host, port)` -> `DeviceSession.start_stellarium` 783-798 (stops a previous worker, persists `stellarium.host` + `stellarium.port`, starts `StellariumWorker` stellarium_worker.py:88-130, log "Stellarium server starting on {host}:{port}"); stop: `stop_server_requested` -> `stop_stellarium` 800-806 (wait 3 s) | host, port |
| 3 | Online lookup | `QCheckBox` 98-105 | "Look up target names online after a GoTo"; tooltip "When no local catalogue match exists, send the GoTo coordinates to CDS/SIMBAD to suggest a target name. Argos always asks before changing FITS metadata." | `stellarium.online_target_lookup` default False (config.py:174) | Always | — | `toggled` -> shell.py:334-336 `config.set("stellarium.online_target_lookup")`; read on every GoTo (shell.py:349-353) | `stellarium.online_target_lookup` |

Displayed data

| Readout | Source | Refresh |
|---|---|---|
| Status "○  stopped" / "●  listening on :{port}" (success colour) | `set_server_state` 123-142 <- `DeviceSession.stellarium_state` (808-812) | On start / stop |
| "↗  goto  RA {ra:.4f}h  Dec {dec:+.4f}°" | `flash_goto` 149-151 <- shell.py:347 | On each GoTo; never reverts |
| "{n} client" / "{n} clients" (success colour when > 0) | `set_client_count` 144-147 <- `client_count_changed` | On (dis)connection of Stellarium |
| Help (10 px): "In Stellarium: Telescope Control plugin → add a telescope “External software or remote computer (TCP)” on this host/port, then select an object and press Ctrl+1 (⌘+1) to slew. A cached target name is suggested locally; online lookup is optional." | 107-117 | Static |

Implicit behaviours: the host is `stellarium.host` (default "127.0.0.1", connection_page.py:95)
and has no control; the mount position is pushed to the server for Stellarium's reticle on
every poll (device_session.py:550-551); a GoTo from Stellarium (shell.py:346-353) slews the
mount (`ImagingPage.goto_target`, imaging_page.py:2775-2788; logs "Goto requested but mount
not connected" when no mount) and starts a target-name suggestion (2733-2763, network only if
#3). The server is never started automatically and its running state is not persisted.

Messages: "Stellarium: bind {host}:{port} failed — {exc}" (stellarium_worker.py:122 via
device_session.py:815), "Stellarium: {exc}" on a loop crash (stellarium_worker.py:96), both in
the Observe log; "Stellarium goto → RA … Dec …" (imaging_page.py:2786-2787);
"Stellarium target-name suggestion: {n} nearby catalogue candidate(s)." (2751-2754);
"Target-name suggestion: {message}" (2759).

Problems found

- A bind error is invisible on the card: the Shell calls `set_server_state(False, "✗  error")`
  (shell.py:360-361) but the `False` branch ignores `message` and shows "○  stopped"
  (stellarium_card.py:133-139).
- The host cannot be set or even seen, yet the help says "on this host/port"; Stellarium on
  another computer cannot connect to 127.0.0.1.
- The port is saved only when the server starts; the GoTo flash never reverts.

### 1.5 Network reachability (`NetworkMonitor`, network_monitor.py:48; display in `TopStatusBar`, statusbar.py:152-168)

- Purpose: answer "is the Seestar reachable, is there internet for catalogues" quietly.
- No control. Every 10 s (32) a TCP connect (1.5 s timeout, 33) to `alpaca.host:alpaca.port`
  (re-read each cycle, 80-82; `None` when no host) and to 1.1.1.1:53 then 8.8.8.8:53 (37, 83).
- Display: "Seestar ● / ○   Net ● / ○" (statusbar.py:161-168); green dot when up, muted
  hollow dot when down or unknown.
- Problems: "down" and "no host configured" look the same; the internet probe contacts public
  resolvers every 10 s with no opt-in, unlike every other network use (stated privacy policy,
  config.py:171-173, 164-166); no timestamp of the last check.

### 1.6 Settings page (`ConfigurationPage`, configuration_page.py:57; page, not modal, scroll page max 940 px)

- Purpose: observer identity, site, instrument, plate solving, catalogues, file locations,
  appearance, about.
- Five accordion sections in a `QToolBox` (86-111); index 0 at every launch (109), not
  persisted; height recomputed per section (114-125).

| # | Control | Qt type | Label | Default | Enabled | Shortcut | Action | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Section header | `QToolBox` item 88-90 | "Observatory" | Open | Always | — | Show 1.7 (`currentChanged` -> `_sync_settings_height` 110) | No |
| 2 | Section header | 91-94 | "Equipment · camera" | Closed | Always | — | Show 1.8 | No |
| 3 | Section header | 95-97 | "Astrometry" | Closed | Always | — | Show 1.9 | No |
| 4 | Section header | 98-100 | "Catalogues · data" | Closed | Always | — | Show 1.10 | No |
| 5 | Section header | 101-108 | "Files · application" | Closed | Always | — | Show 1.11 | No |

Implicit behaviours

| Behaviour | Where |
|---|---|
| All fields loaded once at construction (`_load_config`), never reloaded | 67, 779-848 |
| Building the page applies the five catalogue cache locations and the calibration directory to the core modules (start-up side effect: the Settings page is what configures the caches) | 823-824, 1040-1084 |
| Telescope changes go through the Shell's guarded applier | 587-589, shell.py:326 |
| On close, waits up to 9 s for an in-flight location search | 995-999, shell.py:614 |
| `Config.set` already writes the file; most `_save_*` call `save()` again | config.py:241-248; e.g. 859, 868 |

Problems found (page level)

- Stale overwrite: the dialog 1.14 / 1.15 and the Observe overlay (imaging_page.py:1449) write
  the same keys, but this page never reloads; editing any astrometry field rewrites all six
  `astrometry.*` keys from stale widgets (1172-1184); same for the identification budget
  (1096-1102).
- Long help labels are clipped instead of wrapping (no `setWordWrap`): 331-337, 418-424,
  512-517 (seen in an offscreen render at 1340 px).

### 1.7 Settings › Observatory (card "Observer · Site", configuration_page.py:141-265)

- Purpose: who observes (FITS OBSERVER, AAVSO OBSCODE) and the default site (FITS SITELAT /
  SITELONG / SITEELEV, airmass, Moon, visibility).

| # | Control | Qt type | Label / tooltip (exact) | Default / range / units | Enabled when | Shortcut | Action: handler -> effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Observer | `QLineEdit` 151-154 | "Observer"; no tooltip | "" | Always | — | `editingFinished` -> `_save_observer` 856-859 | `observer.name` |
| 2 | AAVSO code | `QLineEdit` 155-160 | "AAVSO code"; placeholder "e.g. ABC"; tooltip "Your AAVSO observer code — stamped on every AAVSO export" | "" | Always | — | same; stored upper-case (858), field not re-cased | `observer.obscode` |
| 3 | Default site (name) | `QLineEdit` 162-167 | "Default site"; placeholder "Home observatory"; tooltip "Name recorded with the current default observing site" | "" | Always | — | `editingFinished` -> `_save_site` 861-868 | `site.name` |
| 4 | Latitude | `QDoubleSpinBox` 169-170, 267-273 | "Latitude" | -90…90, 5 decimals, suffix " °", 0.0 | Always | — | `valueChanged` -> `_save_site` (every step) | `site.latitude` |
| 5 | Longitude | same 171-172 | "Longitude" | -180…180, 5 decimals, " °" | Always | — | same | `site.longitude` |
| 6 | Elevation | `QDoubleSpinBox` 178-184 | "Elevation" | -500…9000, 1 decimal, " m" | Always | — | same | `site.elevation` |
| 7 | Find location | `QLineEdit` 186-191 | "Find location"; placeholder "Berkeley, France, Mauna Kea…"; tooltip "Search a place online to fill latitude, longitude and terrain elevation" | "" | Disabled during a search (873, 905) | Return | `returnPressed` -> `_search_site` | No |
| 8 | Search | `SecondaryButton` 195-196 | "Search" | — | Disabled during a search | — | `_search_site` 870-881 -> `LocationResolverWorker` (location_resolver_worker.py:20-26) -> `search_locations` location_resolver.py:34-70: Nominatim (limit 5, 8 s) then Open-Meteo elevation per result (8 s each) | No |
| 9 | Matches | `QComboBox` 203-207 | "Matches"; tooltip "Choose the intended place before applying its coordinates"; item = Nominatim display name (tooltip = same) | Empty, disabled | Enabled when results exist (891-893) | — | Selection only | No |
| 10 | Use selected | `SecondaryButton` 208-210 | "Use selected" | — | Enabled with results | — | `_apply_location_result` 912-929: site name = label up to the first comma, lat, lon, elevation (if any) -> `_save_site` | `site.*` |
| 11 | Saved sites | `QComboBox` 226-227 | "Saved sites"; items = favourite names | From `site.favorites` | Disabled when empty (945-948) | — | Selection only | No |
| 12 | Set default | `SecondaryButton` 228-230 | "Set default" | — | Enabled with favourites | — | `_use_selected_favorite` 970-981 -> copies the favourite into #3-#6, `_save_site` | `site.*` |
| 13 | Remove | `SecondaryButton` 231-233 | "Remove" | — | Enabled with favourites | — | `_remove_selected_favorite` 983-993; no confirmation | `site.favorites` |
| 14 | Favourite name | `QLineEdit` 244-246 | "Add favourite"; placeholder "Favourite name" | "" | Always | Return | `returnPressed` -> `_save_current_favorite` | No |
| 15 | Save current | `SecondaryButton` 247-248 | "Save current" | — | Always | — | `_save_current_favorite` 950-968: name = #14 or #3; replaces a same-name favourite (case-insensitive); appends {name, latitude, longitude, elevation} | `site.favorites` |

Displayed data: status line (220-224, wraps); footnote "Default site is written to every FITS
header (SITELAT/LONG/ELEV) and used for airmass, Moon geometry and target visibility."
(259-264).

Messages (status line): "Search is optional. Verify the terrain elevation for a permanent
observatory." (221); "Searching location and terrain elevation…" (875); "Choose a match, then
use it. Elevation is terrain-modelled; edit it for a surveyed site." (894-896); failures:
"Enter a city, country, or address first." (location_resolver.py:38), "Location search is
unavailable. Check your internet connection." (49-51), "No place found for ‘{query}’." (53),
"No usable coordinates found for ‘{query}’." (69), "Location search failed unexpectedly."
(location_resolver_worker.py:26); "Default site set: {lat:.5f}°, {lon:.5f}°, elevation
{e:.0f} m|not available." (924-929); "Name the site before saving it as a favourite." (953);
"Saved favourite site: {name}." (968); "Default site set to saved site: {name}." (981);
"Removed saved site: {name}." (993).

Problems found

- #4-#6 save (and write the file about 5 times) on every spin step (861-868, config.py:248).
- #13 removes without confirmation or undo.
- Up to 6 sequential HTTP calls of 8 s each (location_resolver.py:40-66, 73-87) while shutdown
  waits 9 s (995-999, comment says "both requests"); User-Agent hard-coded "Argos/0.4.1"
  (location_resolver.py:17).
- The favourite lookup after save is case-sensitive (941) while de-duplication is not (962).

### 1.8 Settings › Equipment · camera (cards "Telescope" 520-556 and "Camera" 608-637)

| # | Control | Qt type | Label / tooltip (exact) | Default / range | Enabled when | Shortcut | Action: handler -> effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Model | `QComboBox` 525-530 | "Model"; items "{name}" or "{name}  (unvalidated)"; no tooltip | Active profile | Always (not locked while connected, unlike 1.2 #1) | — | `_save_telescope` 583-598 -> Shell applier (same path and guard as 1.2 #1; a refusal silently snaps back via `sync_telescope_profile`, shell.py:355-358) | `hardware.profile` |
| 2 | Full-well (ADU) | `QSpinBox` 616-620 | "Full-well (ADU)" | 0…65535, step 1000, `camera.full_well_adu` 60000 | Always | — | `_save_camera` 1001-1007 | `camera.full_well_adu` (read by the saturation overlay, imaging_page.py:722, analysis_window.py:458) |
| 3 | Linearity max (ADU) | `QSpinBox` 622-626 | "Linearity max (ADU)" | 0…65535, step 1000, 50000 | Always | — | same | `camera.linearity_max_adu` (read as photometry `sat_adu`, photometry/params.py:64) |
| 4 | ADC bits | `QSpinBox` 628-631 | "ADC bits" | 8…16, 12 | Always | — | same | `camera.adc_bits` (read by no code) |

Displayed data: specs "{aperture} mm f/{ratio} · {sensor} · {pixel} µm · {scale}″/px · {w}° ×
{h}° · {bayer}" (567-572); warning "Unvalidated profile — never run on this hardware. " +
caveats (574-581); note "Applies immediately — every spec below comes from this choice. Do not
change it mid-series: the plate scale would move under a running light curve." (549-555);
"Full-well = the saturation/clipping threshold (Display tab)." (634-636).

Problems found

- Two sources of truth: config.py:75-77 declares `camera.adc_bits / full_well_adu /
  linearity_max_adu` deprecated (moved to the profile + `hardware.overrides`), yet the readers
  still use `camera.*`, the profile fields are read by nothing, `hardware.overrides` has no
  editor (written only by the migration, config.py:301-325) and `camera.adc_bits` has no
  reader.
- #1 is not locked while equipment is connected; the refusal is silent.
- "(Display tab)" names a tab that no longer exists (the dock is "Image display",
  imaging_page.py:336).
- Unvalidated wording conflicts with 1.2 (see 1.2 problems).

### 1.9 Settings › Astrometry (card "Astrometry (plate solving)", configuration_page.py:639-714)

| # | Control | Qt type | Label / tooltip (exact) | Default / range | Enabled when | Shortcut | Action: handler -> effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | ASTAP path | `QLineEdit` 647-650 | "ASTAP"; placeholder "auto-detect (astap_cli on PATH)" | "" | Always | — | `editingFinished` -> `_save_astrometry` 1172-1185 (writes all six keys, refreshes status) | `astrometry.astap_path` |
| 2 | Browse… | `SecondaryButton` 651-653 | "Browse…" | — | Always | — | `_browse_astap` 1187-1191: `getOpenFileName("Locate the ASTAP executable", "/")` -> #1 + save | same |
| 3 | Database folder | `QLineEdit` 662-669 | "Database folder"; placeholder "auto-detect (ASTAP default locations)"; tooltip "Folder containing the downloaded ASTAP star databases. Leave empty to use ASTAP's normal locations." | "" | Always | — | same as #1 | `astrometry.database_path` |
| 4 | Browse… | `SecondaryButton` 670-672 | "Browse…" | — | Always | — | `_browse_astap_database` 1193-1198: `getExistingDirectory("Locate ASTAP star databases")` | same |
| 5 | Database set | `QComboBox` 680-687 | "Database set"; tooltip "Star database ASTAP matches against. 'Auto' lets ASTAP pick by field\nof view (recommended). For the Seestar's ~1° field, D50/D80 or V17 fit."; options Auto, D05, D20, D50, D80, G17, H17, H18, V17, W08 (52) | Auto ("" in config) | Always | — | `currentTextChanged` -> `_save_astrometry` | `astrometry.database` |
| 6 | Search radius | `QSpinBox` 689-694 | "Search radius"; tooltip "Search radius around the hint (0 = blind, whole sky)." | 0…180 °, 30 | Always | — | same | `astrometry.search_radius_deg` |
| 7 | Downsample | `QComboBox` 696-700 | "Downsample"; options Auto (0), 1×, 2×, 3×, 4× (54) | 2× | Always | — | same | `astrometry.downsample` |
| 8 | Scale hint | `QCheckBox` 704-706 | "Use the known plate scale as a hint (faster solve)" | True | Always | — | `toggled` -> same | `astrometry.use_scale_hint` |

Displayed data: ASTAP status (656-657, 1208-1231): "✓ ASTAP detected: {path}" + one of
" · Star database: {folder}", " · Star database not found in: {folder}" (looks for *.1476,
*.290, *.101), " · Star database not detected"; or "✗ ASTAP not found — install it or set the
path above". Note "Solving runs on the green channel. Install ASTAP + a star database from
hnsky.org/astap.htm, then 'Solve' from a loaded FITS." (708-713).

Real effect: `solve_settings_from_config` (astrometry_session.py:40-73) passes
`database = database_path or database`; `_database_args` (platesolve.py:305-319) sends
`-d <path>` for a path, else `-D <set>` plus an auto-detected `-d`.

Problems found

- #3 set silently disables #5: with a folder, only `-d` is passed and the database set is
  ignored (astrometry_session.py:64, platesolve.py:313-314), but both controls stay active.
- `astrometry.grid_spacing_arcmin` is editable only in the dialog (1.14 #8); the database
  folder only here; the live auto-solve keys (`live_*`) nowhere.
- Status refreshes only on save; nothing tests that ASTAP actually runs.

### 1.10 Settings › Catalogues · data (card "Data · catalogues", configuration_page.py:319-518)

Two path helpers: `_catalogue_path_row` (276-295) adds "Browse…" (tooltip "Choose a different
local cache location", 283) and optionally "Refresh" (tooltip "Clear this local cache; the next
matching search fetches fresh data", 288-290).

| # | Control | Qt type | Label / tooltip (exact) | Default | Enabled | Shortcut | Action: handler -> effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Sequence presets folder | `QLineEdit` 349-351 | "Sequence presets"; tooltip "Folder used by Save/Load sequence preset" | ~/Argos/sequences | Always | — | `editingFinished` -> `_save_local_data_paths` 1086-1089 -> `_apply_local_data_paths(save=True)` 1074-1084 | `data_paths.sequence_presets_directory` |
| 2 | Browse… | `SecondaryButton` 282-285 via 354-361 | "Browse…"; tooltip "Choose a different local cache location" | — | Always | — | `_browse_catalogue_directory` 1033-1038, title "Choose sequence preset folder" | same |
| 3 | Camera calibration folder | `QLineEdit` 364-368 | "Camera photon-transfer calibrations"; tooltip "Folder containing local camera_calibration*.json photon-transfer files" | ~/.argos | Always | — | same -> `sensor_reference.configure_calibration_directory`, `imx585.configure_calibration_directory` (1080-1081) | `data_paths.camera_calibration_directory` |
| 4 | Browse… | 370-378 | same tooltip | — | Always | — | title "Choose camera calibration folder" | same |
| 5 | Field identification budget | `QComboBox` 396-408 | (section "Field identification performance"); options "Fast · 100 objects", "Fast · 200 objects", "Balanced · 400 objects", "Detailed · 800 objects", "Dense field · 1,600 objects"; no tooltip | 400 | Always | — | `_save_field_identity_budget` 1096-1102; no catalogue refetch | `catalog.identification_max_objects` |
| 6 | CDS / SIMBAD cache file | `QLineEdit` 426-428 | "Target names · CDS / SIMBAD"; tooltip "CDS/SIMBAD object-name cache file" | ~/Argos/cache/object_resolver.json | Always | — | `editingFinished` -> `_save_catalogue_paths` 1091-1094 -> `_apply_catalogue_paths(save=True)` 1040-1072 (`object_resolver.configure_cache_path`) | `data_paths.object_catalogue_cache` |
| 7 | Browse… | 430-433 | "Browse…" | — | Always | — | `_browse_catalogue_file` 1023-1031: `getSaveFileName("Choose CDS cache file", "JSON files (*.json);;All files (*)")` | same |
| 8 | Refresh | 287-292, 434 | "Refresh"; tooltip above | — | Always | — | `_clear_catalogue_cache("object")` 1120-1163 -> 1.12 -> unlink the file | — |
| 9 | NASA cache file | `QLineEdit` 439-441 | "Transit ephemerides · NASA Exoplanet Archive"; tooltip "NASA Exoplanet Archive ephemeris cache file" | ~/Argos/cache/exoplanets.json | Always | — | same (`exoplanets.configure_cache_path`) | `data_paths.exoplanet_cache` |
| 10 | Browse… | 443-446 | "Browse…" | — | Always | — | title "Choose NASA ephemeris cache file" | same |
| 11 | Refresh | 447 | "Refresh" | — | Always | — | `_clear_catalogue_cache("exoplanet")` | — |
| 12 | AAVSO cache folder | `QLineEdit` 452-454 | "Variables & comparison stars · AAVSO VSX / VSP"; tooltip "AAVSO VSX/VSP solved-field cache folder" | ~/.argos/cache/catalog | Always | — | same (`aavso.configure_cache_directory`) | `data_paths.aavso_cache_directory` |
| 13 | Browse… | 456-459 | "Browse…" | — | Always | — | title "Choose AAVSO field-cache folder" | same |
| 14 | Refresh | 460 | "Refresh" | — | Always | — | `_clear_catalogue_cache("aavso")`: delete *.json | — |
| 15 | Gaia cache folder | `QLineEdit` 465-467 | "Field-star identifiers · Gaia DR3"; tooltip "Gaia DR3 solved-field identifier cache folder" | ~/.argos/cache/gaia | Always | — | same (`gaia.configure_cache_directory`) | `data_paths.gaia_cache_directory` |
| 16 | Browse… | 469-472 | "Browse…" | — | Always | — | title "Choose Gaia field-cache folder" | same |
| 17 | Refresh | 473 | "Refresh" | — | Always | — | `_clear_catalogue_cache("gaia")`: delete *.csv | — |
| 18 | Field identification cache folder | `QLineEdit` 478-482 | "Whole-field identities · SIMBAD / NASA"; tooltip "SIMBAD and NASA solved-field identification cache folder" | ~/.argos/cache/field_catalogue | Always | — | same (`field_objects.configure_cache_directory`, `exoplanets.configure_field_cache_directory`, sub-folders simbad/ and nasa/) | `data_paths.field_catalogue_cache_directory` |
| 19 | Browse… | 484-487 | "Browse…" | — | Always | — | title "Choose field-identification cache folder" | same |
| 20 | Refresh | 488 | "Refresh" | — | Always | — | `_clear_catalogue_cache("field_catalogue")`: delete **/*.json | — |
| 21 | Local diagnostics | `QCheckBox` 499-505 | "Save per-frame diagnostic records"; tooltip "Writes a compact JSONL file beside each session: exposure, mount, focus and photometry-quality measurements. Nothing is uploaded." | False | Always | — | `_save_diagnostics` 1200-1206: sets `diagnostics.local_opt_in_v1 = True` then `diagnostics.enabled` | `diagnostics.enabled` (+ marker) |

Displayed data: "Included with Argos" + "Essential catalogue · v{version} · {count:,} objects"
(326-330, live: v1.0, 13,229 objects) + description (331-337) + "Source: {source}" (338, "CDS/VizieR
VII/118 — NGC 2000.0 (Sinnott 1988)") + "Storage: inside the Argos application · read-only"
(339); "These folders remain on this computer. They are not catalogues and are never
uploaded." (343-347); calibration note (380-386); budget note (390-395) and "The magnitude depth
and provider switches are available from Capture → Catalogues & depth…" (409-414); caches note
(418-424); cache status "CDS: cached|empty · NASA: cached|empty · AAVSO: {n} field file(s) ·
Gaia: {n} field file(s) · Field identities: {n} field file(s)" (1104-1118); diagnostics notes
(506-511) and the HD note (512-517).

Messages: "Choose a valid file or folder for each catalogue cache." (1054-1056); "Could not
clear {label}: {exc}" (1158); "{label} cleared. " + status (1161-1163).

Problems found

- "Refresh" deletes the cache (1120-1163): label and action disagree.
- #2 / #4 carry the cache tooltip "Choose a different local cache location" (283) although
  presets and calibrations are not caches.
- #7 / #10 use a Save dialog to pick an existing cache file (1026-1028): the OS may ask
  "Replace?" (platform behaviour, not tested).
- Cache counts are computed at load and after a change only; they go stale during a night.
- The hint names "Capture → Catalogues & depth…" (412); the controls are labelled
  "Catalogues / depth…" (overlay_bar.py:121) and "Field → Configure catalogues…"
  (shell.py:263), and the overlay tooltip promises "cache folders and refresh behaviour"
  (overlay_bar.py:122-124) which only this page has.
- #5 here does not keep the legacy keys in step and does not refetch, unlike 1.15 #4.
- The HD note sits under "Local diagnostics" although it is about catalogues (512-517).

### 1.11 Settings › Files · application (configuration_page.py:297-317, 716-773)

| # | Control | Qt type | Label / tooltip (exact) | Default / options | Enabled | Shortcut | Action: handler -> effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Sessions folder | `QLineEdit` 304-306 | "Default working folder (sessions)" | ~/Argos/sessions | Always | — | `editingFinished` -> `_save_sessions_path` 1009-1013 (empty text ignored, no existence check) | `sessions_path` |
| 2 | Browse… | `design.PrimaryButton` 307-309 | "Browse…" | — | Always | — | `_browse_sessions_path` 1015-1021: `getExistingDirectory("Choose sessions folder")` | same |
| 3 | Color preset | `QComboBox` 726-731 | "Color preset"; options "Observatory", "Charcoal", "Night (Red)" (palettes.py:73-162) | "Observatory" | Always | — | `_save_palette` 1233-1257: `theme.apply_palette`, regenerate global QSS, show the restart notice | `ui.theme.preset` |
| 4 | Language | `QComboBox` 733-738 | "Language"; options "English" (en), "Français" (fr) | en | Always | — | `_save_language` 1259-1263 | `ui.language` (read by no code) |
| 5 | Log level | `QComboBox` 740-745 | "Log level"; options DEBUG, INFO, WARNING, ERROR | INFO | Always | — | `_save_log_level` 1265-1269 | `ui.log_level` (read at start-up only, main.py:144) |

Displayed data: "Each observation receives its own folder here: raw FITS, session.json,
metadata, preview products and local diagnostics." (311-316); restart notice (warning colour)
"Restart to fully apply — global colors update live, but some widgets (sidebar, status bar)
take effect on next launch." (752-761, after #3); "Language change applies after restart."
(763); About: "Argos — ZWO Seestar controller", "Version {__version__}", "Science-grade
acquisition · ASCOM Alpaca · FITS", "GNU GPL v3 · linked against PyQt6 (GPL v3)" (766-773).

Problems found: #4 has no effect at all (no i18n; the note promises a restart effect); #5
needs a restart but says nothing; #2 is the only primary-styled "Browse…" (307); #1 accepts
a non-existent or unwritable folder silently.

### 1.12 Cache clear confirmation (`QMessageBox.question`, configuration_page.py:1130-1137, modal)

| # | Control | Qt type | Label | Default | Action |
|---|---|---|---|---|---|
| 1 | Yes | standard button | "Yes" | — | Delete the cache file(s) (1140-1159), refresh status |
| 2 | Cancel | standard button | "Cancel" | Default button | Nothing |

Title "Refresh local catalogue cache"; text "Clear the {label}?\n\nNo data will be downloaded
now. The next matching lookup refreshes it if internet access is available." with labels
"CDS/SIMBAD target-name cache", "NASA exoplanet ephemeris cache", "AAVSO VSX/VSP field
cache", "Gaia DR3 field-star cache", "SIMBAD / NASA field-identification cache" (1122-1128).

### 1.13 Native file and folder pickers (`QFileDialog`, modal OS dialogs, 10 call sites)

| Call site | Kind | Title | Start |
|---|---|---|---|
| configuration_page.py:1017 | folder | "Choose sessions folder" | current sessions path |
| configuration_page.py:1026 | save-file | "Choose CDS cache file" / "Choose NASA ephemeris cache file" (filter "JSON files (*.json);;All files (*)") | field text or home |
| configuration_page.py:1035 | folder (x5) | "Choose sequence preset folder", "Choose camera calibration folder", "Choose AAVSO field-cache folder", "Choose Gaia field-cache folder", "Choose field-identification cache folder" | field text or home |
| configuration_page.py:1188 | open-file | "Locate the ASTAP executable" | "/" |
| configuration_page.py:1195 | folder | "Locate ASTAP star databases" | field text or "/" |
| astrometry_settings.py:347 | open-file | "Select ASTAP binary" | default |

No own controls (the "Browse…" buttons are counted in their sections).

### 1.14 Dialog "Field identification & catalogue settings", tab "Plate solving" (`AstrometrySettingsDialog`, astrometry_settings.py:48, 90-126; modal `exec()`, min width 440)

- Purpose: tune plate solving without leaving the image. Writes the same keys as 1.9 only on
  Save (1.15 #16). On Save the opener reacts: Shell -> `engine.refetch_catalog`
  (shell.py:470-472); Observe -> refetch + reproject + clamp the depth slider
  (imaging_page.py:1429-1438); analysis window -> refresh (analysis_window.py:567-577).

| # | Control | Qt type | Label / tooltip (exact) | Default / range | Enabled | Shortcut | Action | Persisted (on Save) |
|---|---|---|---|---|---|---|---|---|
| 1 | Tab | `QTabWidget` 72-75 | "Plate solving" | Opened when `section="astrometry"` (86) | Always | — | Show tab | No |
| 2 | Tab | 74 | "Field catalogue" | Opened when `section="catalog"` | Always | — | Show tab | No |
| 3 | ASTAP executable | `QLineEdit` 94-101 | "ASTAP executable"; placeholder "auto-detect (astap_cli / astap on PATH)" | `astrometry.astap_path` | Always | — | — | `astrometry.astap_path` |
| 4 | Browse… | `QPushButton` 96-97 | "Browse…" | — | Always | — | `_browse_astap` 344-349 (no save, no detection status) | — |
| 5 | Star database | `QComboBox` 103-105 | "Star database"; no tooltip; same 10 options | Auto | Always | — | — | `astrometry.database` |
| 6 | Pointing search radius | `QSpinBox` 107-111 | tooltip "Search radius around the pointing hint (0 = whole-sky blind)" | 0…180 °, 30 | Always | — | — | `astrometry.search_radius_deg` |
| 7 | Solve-image downsampling | `QComboBox` 113-116 | same 5 options | 2× | Always | — | — | `astrometry.downsample` |
| 8 | Coordinate-grid spacing | `QSpinBox` 118-122 | tooltip "RA/Dec grid spacing in arcminutes (0 = auto, adaptive)" | 0…120 ′, 0 | Always | — | — | `astrometry.grid_spacing_arcmin` (only editor) |
| 9 | Scale hint | `QCheckBox` 124-125 | "Use camera plate scale as a field-of-view hint" | True | Always | — | — | `astrometry.use_scale_hint` |

### 1.15 Same dialog, tab "Field catalogue" and buttons (astrometry_settings.py:128-268, 77-82, 351-396)

Help label (132-137): "These controls define what is fetched and displayed for a solved
image. They do not change a FITS frame or the scientific photometry."

| # | Control | Qt type | Label / tooltip (exact) | Default / range | Enabled | Shortcut | Action | Persisted (on Save) |
|---|---|---|---|---|---|---|---|---|
| 1 | VSX faint-end magnitude limit | `QDoubleSpinBox` 139-144 | tooltip "Drop catalog objects fainter than this (a dense field is huge)" | 5.0…20.0, step 0.5, 1 decimal; 15.0 | Always | — | — | `catalog.mag_limit` |
| 2 | Maximum VSX variables in field | `QSpinBox` 146-150 | tooltip "Cap on variable stars drawn (brightest kept)" | 10…2000, step 10; 250 | Always | — | — | `catalog.max_results` |
| 3 | Include suspected variables | `QCheckBox` 152-153 | — | True | Always | — | — | `catalog.include_suspected` |
| 4 | Field identification budget | `QComboBox` 155-169 | tooltip "Maximum online field identities shared between Gaia and SIMBAD. A smaller budget is faster. Scientific VSX/VSP results are not truncated by it."; 5 options as 1.10 #5 | 400 | Always | — | `_apply_identification_budget` 338-342 mirrors into hidden H1/H2 | `catalog.identification_max_objects`, `field_stars_max_results`, `named_objects_max_results` |
| 5 | Identify ordinary field stars with Gaia DR3 | `QCheckBox` 171-176 | tooltip "Queries Gaia after a field solve and uses the local cache when available. Gaia identifiers are for field recognition, not calibrated photometry." | True | Always | — | — | `catalog.field_stars_enabled` |
| 6 | Gaia cached-depth G limit | `QDoubleSpinBox` 178-185 | tooltip "Only Gaia sources brighter than this G magnitude are shown" | 3.0…20.0, step 0.5; 18.0 | Always (even with #5 off) | — | — | `catalog.field_stars_mag_limit` |
| 7 | Gaia cache depth | `QComboBox` 193-199 | options "Bright field · Gaia G ≤ 15" (15), "Standard field · Gaia G ≤ 18" (18), "Deep field · Gaia G ≤ 20" (20), "Custom" | Matched from #6 at load (324-330) | Always | — | `_apply_field_depth` 332-336 sets #6 | via #6 |
| 8 | Only draw Gaia sources with a local image detection | `QCheckBox` 201-208 | tooltip "Off by default: after a good plate solve, Gaia/WCS coordinates are the identification reference. Enable only to declutter a noisy preview." | False | Always | — | — | `catalog.field_stars_detected_only` |
| 9 | Show bundled Messier, NGC and IC objects in the solved field | `QCheckBox` 210-216 | tooltip "Works offline. This compact catalogue identifies deep-sky objects, not every star." | True | Always | — | — | `catalog.show_essential_objects` |
| 10 | Show previously prepared exoplanet hosts from the local cache | `QCheckBox` 218-224 | tooltip "Does not query the network and is not a complete exoplanet-field catalogue." | True | Always | — | — | `catalog.show_cached_exoplanets` |
| 11 | Identify named objects and types with SIMBAD for every solved field | `QCheckBox` 226-233 | tooltip "Uses the local field cache first, then SIMBAD after Field → Identify field. Gaia remains the complete star layer." | True | Always | — | — | `catalog.named_objects_enabled` |
| 12 | Allow SIMBAD lookup when this field is not cached | `QCheckBox` 241-243 | tooltip "Disable for a cache-only / offline observing session." | True | Always (even with #11 off) | — | — | `catalog.named_objects_allow_network` |
| 13 | Find confirmed exoplanet hosts for every solved field | `QCheckBox` 245-251 | tooltip "Uses the local field cache first, then NASA Exoplanet Archive when permitted." | True | Always | — | — | `catalog.exoplanet_hosts_enabled` |
| 14 | Allow NASA lookup when this field is not cached | `QCheckBox` 253-257 | tooltip "Disable for a cache-only / offline observing session." | True | Always (even with #13 off) | — | — | `catalog.exoplanet_hosts_allow_network` |
| 15 | Automatic reference stars | `QSpinBox` 262-267 | tooltip "How many comparison stars are auto-picked when a target is chosen" | 1…20; 5 | Always | — | — | `photometry.auto_comparisons` (also edited in Observe, imaging_page.py:2167-2169) |
| 16 | Save | `QDialogButtonBox.Save` 77-80 | "Save" | — | Always | Enter (default button) | `_on_save` 351-396: writes all 21 keys, `config.save()`, emits `saved`, closes | all above |
| 17 | Cancel | `QDialogButtonBox.Cancel` 77-81 | "Cancel" | — | Always | Esc | `reject` | — |
| H1 | (hidden) Gaia max markers | `QSpinBox` 187-191, hidden | tooltip "Cap on named Gaia source markers in the solved field" | 10…5000 | Never visible | — | Mirrors #4 | `catalog.field_stars_max_results` (no reader) |
| H2 | (hidden) SIMBAD max | `QSpinBox` 235-239, hidden | tooltip "Cap for named SIMBAD objects returned for a crowded field" | 50…2000 | Never visible | — | Mirrors #4 | `catalog.named_objects_max_results` (no reader) |

Problems found (1.14 + 1.15)

- #7 is not updated when #6 changes (no `valueChanged` connection, 178-199): the combo shows
  a preset that no longer matches the limit.
- Dependent controls stay enabled: #6 / #7 / #8 with #5 off, #12 with #11 off, #14 with #13
  off.
- H1 / H2 are dead UI writing dead keys.
- Subsets differ from 1.9 (no database folder, no ASTAP status here; grid spacing only here)
  and the save model differs (Save button here, save-on-edit in Settings).
- Checkbox labels are truncated at the 440 px minimum width (69; seen in the render).
- The window title says "Field identification" while its entry points say "Configure field
  identification…", "Configure catalogues…" and "Catalogues / depth…".

---

## 2. Web redesign

### 2.1 Placement in the new information architecture

Principles: the Connection section is the start-of-night stop and shows everything needed to
get the equipment ready on one screen without a disclosure (four devices are four rows, they
do not need hiding). Settings becomes a two-level page (category list + form) with one
canonical place per key; point-of-use popovers on Observe edit the same keys through the same
API and stay in sync through a `config` event (fixes the Qt stale overwrite).

| Qt element | Web section | Screen | Region | Why |
|---|---|---|---|---|
| 1.1 Connection page | Connection (F1) | Connection screen (W1) | Full section | Owner decision. Two columns + log, no scrolling at 1440 x 900 |
| 1.2 #1 telescope model + specs + warning | Connection | Connection | "Instrument" card, left column top | Qt rationale kept (connection_page.py:115-118): the profile sets plate scale, sensor geometry and FITS identity before the first device call |
| 1.2 #2-#4 address, port, discover | Connection | Connection | "Link" card, left column | Plus the web-only Simulator / Seestar mode and the ARGOS server line already in `ConnectionCard.svelte` |
| 1.2 summary + 1.3 device cards | Connection | Connection | "Devices" table, right column | One table replaces summary + 4 hidden cards; the error reason is always visible |
| 1.2 #5-#6 + 1.3 #5-#6 | Connection | Connection | Screen header (always visible) | Duplicates merged into one pair |
| 1.2 #7 disclosure | — | — | — | Dropped (nothing hidden any more) |
| 1.4 Stellarium card | Connection | Connection | "Planetarium" card, right column | Set-up time; host now visible; error visible |
| 1.5 network dots | Global + Connection | Status bar (all screens) + Link card | Status bar item, Link card line | Reachability matters on every screen; detail (last check) on Connection |
| Site summary (new, read-only) | Connection | Connection | Instrument card footer | A wrong site is a science error like a wrong profile; link to Settings › Observer & site |
| Connection log (new view of existing data) | Connection | Connection | Bottom region, filtered | Qt shows discovery / connect results only on the Observe log |
| 1.6 Settings page | Settings (F5) | Settings screen (W3) | Category list (left) + form (max 880 px) + optional help column | Owner decision; 9 categories replace the 5 accordion sections |
| 1.7 Observatory | Settings | Observer & site | Form | Same content |
| 1.8 #1 Model | Settings | Instrument | "Telescope profile" group | Same API and guard as Connection, locked while connected |
| 1.8 #2-#4 camera thresholds | Settings | Instrument | "Sensor limits" group | One source of truth after owner decision (Q2) |
| 1.10 #3-#4 calibration folder | Settings | Instrument | "Photon-transfer calibrations" | It describes the sensor, not storage |
| 1.9 Astrometry + 1.14 tab | Settings | Plate solving | Form (canonical) | Merges the two subsets; Observe popover W9a for the frequent ones |
| 1.15 tab Field catalogue + 1.10 #5 | Settings | Catalogues | Form (canonical) | Merges budget duplicates; Observe popover W9b at point of use |
| 1.15 #15 automatic reference stars | Settings | Photometry | Form | It is a photometry parameter (config `photometry.*`); also edited in Observe photometry setup |
| 1.10 essential catalogue facts | Settings | Catalogues | "Bundled catalogue" facts | Information about a catalogue |
| 1.10 #1-#2 presets, 1.11 #1-#2 sessions, 1.10 #6-#20 caches | Settings | Data & storage | Folders group + caches table | All on-disk locations together |
| 1.10 #21 diagnostics, 1.11 #5 log level, shell support bundle | Settings | Privacy & diagnostics | Form | Everything about what is recorded locally and what leaves the machine |
| Online permissions (1.4 #3, 1.15 #12, #14) | Settings | Privacy & diagnostics | "Online services" list (mirror) | One place to make a session offline; same keys as the point-of-use toggles |
| 1.11 #3 colour preset | Settings | Appearance | Theme segmented control | Also the existing toolbar `theme` button |
| 1.11 #4 language | — | — | — | Dropped (no effect, Q4) |
| 1.11 About card + shell About / Documentation | Settings | About | Facts + links | One place for version, licence, credits, docs |
| 1.12 confirmation | Settings | Data & storage | Modal dialog (W10a) | Destructive |
| 1.13 pickers | Settings | any path field | Tauri native dialog, or in-app folder browser modal (W11) | Browser and Night Red cannot use OS dialogs well (Q10) |
| 1.14 / 1.15 dialog itself | Observe | Observe toolbar | Two popovers (W9a, W9b) + "All settings" link | Keeps the image visible (BRAND 11.1); no modal over the image |

### 2.2 Control mapping

Connection (1.2, 1.3, 1.4)

| Qt ref | Web control | Decision | Icon id | Display | Shortcut |
|---|---|---|---|---|---|
| 1.2 #1 Telescope model | Custom `Select` "Telescope" (tokens, no native select) with option badge "Unvalidated"; specs line below | Keep. Locked with `disabledReason` "Disconnect the equipment before changing the telescope: it sets plate scale, sensor geometry and FITS metadata." while any device is connected or busy | — (`mount` as card icon) | label | — |
| 1.2 #2 IP address | `TextField` "Seestar address" (mono), commit on blur / Enter, persisted via `PATCH /api/config` (`alpaca.host`) | Keep; write on commit, not per keystroke | — | label | — |
| 1.2 #3 Port | `NumberField` "Alpaca port" 1…65535 integer | Keep | — | label | — |
| 1.2 #4 Discover | `IconButton` "Discover", busy spinner while scanning, results popover (W2) | Keep; show progress, all results, failure inline | `discover` | icon+label | — |
| 1.2 #5 Connect equipment | Header `IconButton` "Connect all" (primary); "Equipment ready" disabled state when all ready; connects only devices not yet connected | Merge with 1.3 #5 | `connect` | icon+label | — |
| 1.2 #6 Disconnect equipment | Header `IconButton` "Disconnect all" (danger), confirmation only when a sequence, exposure, slew or autofocus runs (W10b) | Merge with 1.3 #6 | `disconnect` | icon+label | — |
| 1.2 #7 Show / hide details | — | Drop: the device table is always visible (4 rows of 32 px) | — | — | — |
| 1.3 #1-#4 per-device button | Row action in the Devices table: "Connect" / "Disconnect" / "Retry" (error) / "Stop retrying" (mount auto-retry) | Keep. Disconnect of a slewing mount asks for confirmation | `connect` / `disconnect` / `refresh` | icon+label | — |
| 1.3 #5 Connect all | (merged) | Merge into the header action | `connect` | — | — |
| 1.3 #6 Disconnect all | (merged) | Merge into the header action | `disconnect` | — | — |
| 1.4 #1 TCP port | `NumberField` "Port" 1024…65535, disabled while running, saved on commit | Keep; persist on commit, not only on start | — | label | — |
| 1.4 #2 Start / Stop server | `IconButton` "Start bridge" (primary) / "Stop bridge" | Keep | `planetarium` / `stop` | icon+label | — |
| 1.4 #3 Online lookup | Checkbox "Look up target names online after a GoTo" (same text, help as caption) | Keep, mirrored in Settings › Privacy | — | label | — |
| (web) Simulator / Seestar | `Segmented` "Equipment" (existing) | Keep (web-only) | `simulator` on connect | label | — |
| (web) Retry server | `IconButton` "Retry server" (existing) | Keep, moves to Link card | `refresh` | icon+label | — |
| (new) Stellarium host | Read-only fact "Host 127.0.0.1"; editable only if Q6 says yes | New (makes the help text true) | — | label | — |
| (new) Site summary | Fact line + link "Change in Settings" | New, read-only | `site` | icon+label link | — |
| (new) Connection log | Filtered `LogDrawer` (topics connection, discovery, planetarium) with `clear` | New view of existing messages | `log`, `clear` | icon | — |

Settings (1.6 to 1.13)

| Qt ref | Web control | Decision | Icon id | Display | Shortcut |
|---|---|---|---|---|---|
| 1.6 #1-#5 accordion headers | Category list: Observer & site, Instrument, Plate solving, Catalogues, Photometry, Data & storage, Privacy & diagnostics, Appearance, About; plus a "Filter settings" field | Merge (accordion -> list; selected category remembered per viewer) | `site`, `mount`, `plate-solve`, `catalogue`, `photometry`, `browse`, `log`, `theme`, `about`; `search` for the filter | 16 px icon + label | ↑ / ↓ in the list; `/` focuses the filter (proposed) |
| 1.7 #1 Observer | `TextField` "Observer name" | Keep | — | label | — |
| 1.7 #2 AAVSO code | `TextField` "AAVSO observer code" (mono, upper-cased as typed), caption "Stamped on every AAVSO export" | Keep | — | label | — |
| 1.7 #3 Default site name | `TextField` "Site name" | Keep | — | label | — |
| 1.7 #4 Latitude | `NumberField` "Latitude" −90…90, 5 decimals, unit °, sign always shown | Keep; commit on blur / Enter, not per step | — | label | — |
| 1.7 #5 Longitude | `NumberField` "Longitude" −180…180, 5 decimals, ° (east positive stated in caption) | Keep | — | label | — |
| 1.7 #6 Elevation | `NumberField` "Elevation" −500…9000 m, 1 decimal | Keep | — | label | — |
| 1.7 #7 Find location | `TextField` "Find a place" with the existing placeholder, Enter runs the search | Keep; caption names the services (OpenStreetMap Nominatim, Open-Meteo) | — | label | Enter |
| 1.7 #8 Search | `IconButton` "Search" (busy while running, cancel by editing) | Keep | `search` | icon+label | — |
| 1.7 #9 Matches | Radio list of up to 5 results (name, lat, lon, elevation) | Keep, as a list instead of a combo (values visible before choosing) | — | label | — |
| 1.7 #10 Use selected | `IconButton` "Use as default site" | Keep | `site` | icon+label | — |
| 1.7 #11 Saved sites | Table of favourites (name, lat, lon, elevation, "Default" chip on the current one) | Keep, table instead of combo | — | label | — |
| 1.7 #12 Set default | Row action "Set as default" | Keep | `bookmark` | icon (tooltip) | — |
| 1.7 #13 Remove | Row action "Remove" + undo toast (6 s) | Keep; undo instead of no confirmation | `remove` | icon (tooltip) | — |
| 1.7 #14 Favourite name | `TextField` "Name" under the table | Keep | — | label | Enter |
| 1.7 #15 Save current | `IconButton` "Save current site" | Keep | `bookmark` | icon+label | — |
| 1.8 #1 Model | Same `Select` as Connection, same lock and reason | Keep (Q1: editable here or read-only mirror) | — | label | — |
| 1.8 #2 Full-well | `NumberField` "Saturation (full well)" 0…65535 ADU, profile value shown as placeholder / "Profile: 60000" | Keep; binding per Q2 | — | label | — |
| 1.8 #3 Linearity max | `NumberField` "Linearity limit" 0…65535 ADU | Keep; binding per Q2 | — | label | — |
| 1.8 #4 ADC bits | Read-only fact "ADC depth 12 bit" from the profile | Move to read-only (no code reads `camera.adc_bits`); editable again only if Q2 adds a reader | — | label | — |
| 1.9 #1 ASTAP path | `PathField` "ASTAP executable" (placeholder "Auto-detect (astap_cli on PATH)") + detection `StatusBadge` | Keep | — | label | — |
| 1.9 #2 Browse | `IconButton` "Choose the ASTAP executable…" | Keep | `browse` | icon (tooltip) | — |
| 1.9 #3 Database folder | `PathField` "Star database folder" + caption "When set, ASTAP uses this folder and ignores Database set" (or Q20 fix) | Keep | — | label | — |
| 1.9 #4 Browse | `IconButton` "Choose the star database folder…" | Keep | `browse` | icon | — |
| 1.9 #5 Database set | `Select` "Database set" (Auto, D05 … W08) with the Qt tooltip as caption; disabled with reason while a folder is set (unless Q20) | Keep | — | label | — |
| 1.9 #6 Search radius | `NumberField` "Search radius" 0…180 °, caption "0 = blind, whole sky" | Keep (merged with 1.14 #6) | — | label | — |
| 1.9 #7 Downsample | `Segmented` Auto / 1× / 2× / 3× / 4× | Keep (merged with 1.14 #7) | — | label | — |
| 1.9 #8 Scale hint | Checkbox "Use the known plate scale as a hint (faster solve)" | Keep (merged with 1.14 #9) | — | label | — |
| 1.10 #1 Presets folder | `PathField` "Sequence presets" | Keep, moved to Data & storage | — | label | — |
| 1.10 #2 Browse | `IconButton` "Choose folder…" (tooltip fixed: no "cache") | Keep | `browse` | icon | — |
| 1.10 #3 Calibration folder | `PathField` "Photon-transfer calibrations" | Keep, moved to Instrument | — | label | — |
| 1.10 #4 Browse | `IconButton` "Choose folder…" | Keep | `browse` | icon | — |
| 1.10 #5 Identification budget | `Segmented` 100 / 200 / 400 / 800 / 1 600 with names as captions (Fast … Dense field) | Merge with 1.15 #4 (one control, Catalogues) | — | label | — |
| 1.10 #6, #9 cache files; #12, #15, #18 cache folders | Caches table rows (W7): name, path (mono, ellipsis in the middle), status ("cached" / "24 fields" / "empty"), actions | Keep | — | label | — |
| 1.10 #7, #10, #13, #16, #19 Browse | Row action "Choose location…" (file pickers use an open dialog, not a save dialog) | Keep | `browse` | icon | — |
| 1.10 #8, #11, #14, #17, #20 Refresh | Row action "Clear cache…" + confirmation W10a | Keep, renamed (it deletes) | `clear` | icon+label | — |
| 1.10 #21 Diagnostics | Switch "Save per-frame diagnostic records" (+ existing caption) | Keep, moved to Privacy & diagnostics; server sets the opt-in marker | — | label | — |
| 1.11 #1 Sessions folder | `PathField` "Sessions folder" with existence / writability check | Keep, moved to Data & storage | — | label | — |
| 1.11 #2 Browse | `IconButton` "Choose folder…" (secondary like all Browse) | Keep | `browse` | icon | — |
| 1.11 #3 Colour preset | `Segmented` Observatory / Charcoal / Night Red, applied instantly | Keep; "Night (Red)" renamed "Night Red" as in tokens | `theme` (category) | label | toolbar button keeps its toggle |
| 1.11 #4 Language | — | Drop: `ui.language` is read by no code (configuration_page.py:1262 only writer), so the control has no effect; return when i18n exists (Q4) | — | — | — |
| 1.11 #5 Log level | `Segmented` DEBUG / INFO / WARNING / ERROR, applied live by the server | Keep, moved to Privacy & diagnostics | — | label | — |
| 1.12 #1 Yes | Dialog button "Clear cache" (danger) | Keep, explicit verb | — | label | Enter |
| 1.12 #2 Cancel | Dialog button "Cancel" (default focus) | Keep | — | label | Esc |
| (shell) Create local support bundle | `IconButton` "Create support bundle…" | Placement proposal (shell spec owns it) | `support-bundle` | icon+label | — |
| (shell) Documentation & website | Link button | Placement proposal | `help` | icon+label | — |
| (shell) About & credits | About category content (logo from `brand/argos-mark.svg`, version, credits, licence) | Placement proposal | `about` | icon+label | — |

Dialog (1.14, 1.15) -> Settings + Observe popovers

| Qt ref | Web control | Decision | Icon id | Display | Shortcut |
|---|---|---|---|---|---|
| 1.14 #1 tab Plate solving | Settings › Plate solving category; Observe popover W9a | Merge | `plate-solve` | — | — |
| 1.14 #2 tab Field catalogue | Settings › Catalogues category; Observe popover W9b | Merge | `catalogue` | — | — |
| 1.14 #3 ASTAP executable | = 1.9 #1 (Settings only) | Merge | — | — | — |
| 1.14 #4 Browse | = 1.9 #2 | Merge | `browse` | — | — |
| 1.14 #5 Star database | = 1.9 #5 | Merge | — | — | — |
| 1.14 #6 Pointing search radius | = 1.9 #6; also in W9a | Merge | — | label | — |
| 1.14 #7 Downsampling | = 1.9 #7; also in W9a | Merge | — | label | — |
| 1.14 #8 Grid spacing | `NumberField` "Coordinate grid spacing" 0…120 ′ (0 = adaptive) in Settings › Plate solving and W9a | Keep (now also in Settings) | — | label | — |
| 1.14 #9 Scale hint | = 1.9 #8; also in W9a | Merge | — | label | — |
| 1.15 #1 VSX faint limit | `NumberField` "VSX faint limit" 5.0…20.0, step 0.5, shown "≤ 15.0" | Keep (Settings + W9b) | `variable-star` (group icon) | label | — |
| 1.15 #2 Max VSX variables | `NumberField` "Maximum variables" 10…2000 step 10 | Keep | — | label | — |
| 1.15 #3 Include suspected | Checkbox "Include suspected variables" | Keep | — | label | — |
| 1.15 #4 Budget | = 1.10 #5 (one control) | Merge | — | label | — |
| 1.15 #5 Gaia DR3 | Switch "Identify field stars with Gaia DR3" | Keep; group header for #6-#8 | `field-stars` | label | — |
| 1.15 #6 G limit | `NumberField` "Gaia depth" 3.0…20.0 step 0.5 (G ≤ value), disabled with reason when #5 off | Keep | — | label | — |
| 1.15 #7 Gaia cache depth | `Segmented` Bright ≤ 15 / Standard ≤ 18 / Deep ≤ 20 / Custom, two-way bound to #6 | Keep; fix the one-way sync | — | label | — |
| 1.15 #8 Detected only | Checkbox "Only draw Gaia sources detected in the image", disabled when #5 off | Keep | — | label | — |
| 1.15 #9 Bundled Messier/NGC/IC | Checkbox "Show bundled Messier, NGC and IC objects" | Keep | `galaxy` (group) | label | — |
| 1.15 #10 Cached exoplanet hosts | Checkbox "Show cached exoplanet hosts" | Keep | — | label | — |
| 1.15 #11 SIMBAD named objects | Switch "Identify named objects with SIMBAD" | Keep | `other-objects` (group) | label | — |
| 1.15 #12 Allow SIMBAD network | Checkbox "Query SIMBAD when the field is not cached", disabled when #11 off; mirrored in Privacy | Keep | — | label | — |
| 1.15 #13 Exoplanet hosts | Switch "Find confirmed exoplanet hosts" | Keep | `exoplanet` (group) | label | — |
| 1.15 #14 Allow NASA network | Checkbox "Query NASA when the field is not cached", disabled when #13 off; mirrored in Privacy | Keep | — | label | — |
| 1.15 #15 Automatic reference stars | `NumberField` "Automatic comparison stars" 1…20 in Settings › Photometry (and Observe photometry setup) | Move | `comparison-star` (group) | label | — |
| 1.15 #16 Save | — | Drop as a button: every control applies on commit (one save model with Settings); the server refetches the field catalogue after catalogue keys change (debounced 500 ms), which is what `saved` did | — | — | — |
| 1.15 #17 Cancel | Popover "Esc" closes; no pending state exists | Drop (nothing to cancel with immediate apply); an accidental change is undone by setting it back | — | — | Esc |
| 1.15 H1, H2 hidden spins | — | Drop: hidden, and their keys are read by no code | — | — | — |

Displayed data mapping (main readouts)

| Qt readout | Web |
|---|---|
| Profile specs (1.2, 1.8, two variants) | One spec line everywhere: aperture, f/ratio, sensor, pixel µm, ″/px, FOV, Bayer (BRAND formats) |
| Unvalidated warning (two wordings) | One `StatusBadge` "Unvalidated" (warning tone) + caveat list; wording per Q3 |
| Summary grid + card glyph / status | Devices table: State column (dot + word), Detail column (device name or full error, two lines, full text in tooltip and log) |
| Stellarium status, client count, GoTo flash | Card facts: state badge, "Clients", "Last GoTo" (RA / Dec per BRAND, UTC time) |
| Network dots | Status bar "Seestar" / "Internet" items + Link card line with "checked {n} s ago" |
| ASTAP status | `StatusBadge` "Found" / "Not found" + path; database line |
| Cache status line | Status column per cache row, refreshed on view and after each solve |
| Essential catalogue facts | Catalogues › "Bundled catalogue": name, version, objects, source (link), "Read-only, inside the application" |
| Restart notice / language note | Dropped (no restart needed; language dropped) |
| About card | About category |

### 2.3 Wireframes (1440 x 900 reference, rail 92 px, status bar 32 px)

W1 Connection screen

```
 92px                                                    1348 px
┌──────┬────────────────────────────────────────────────────────────────────────────────────────────────┐
│{about}│ Connection   (o) 2 of 4 devices ready                      {connect} Connect all  {disconnect} Disconnect all │ 40
│ARGOS ├──────────────────────────────────────────────┬─────────────────────────────────────────────────┤
│      │ {mount} INSTRUMENT                           │ {network} DEVICES                                │
│{nav-c│ Telescope [ZWO Seestar S30 Pro            v] │ Device          State      Detail          Action │
│ Conn │ 30 mm · f/5.3 · IMX585 · 2.9 µm · 3.74″/px   │ {mount} Mount   (o) Ready  Seestar S30 Pro  {disconnect} Disconnect │ 32
│      │ 3.99° × 2.24° · GRBG          [Validated]    │ {camera} Camera (x) Error  Timed out after  {refresh} Retry │
│{nav-i│ Site  Home · +48.82770° +2.38260° · 60 m     │                            10 s (PUT Connected)  │
│ Obs  │       {site} Change in Settings              │ {filter-wheel} Filter wheel (o) Off  —   {connect} Connect │
│      ├──────────────────────────────────────────────┤ {focuser} Focuser (o) Off  —        {connect} Connect │
│{nav-s│ {connect} LINK                               ├─────────────────────────────────────────────────┤
│ Plan │ Equipment ( Simulator | Seestar (Alpaca) )   │ {planetarium} PLANETARIUM · Stellarium  (o) Listening │
│      │ Address [192.168.1.42        ] Port [32323]  │ Host 127.0.0.1   Port [10001]  {stop} Stop bridge │
│{nav-a│ {discover} Discover   Last: 192.168.1.42:32323│ Clients 1   Last GoTo 05h 35m 17.3s +05° 23′ 28″ │
│ Rev  │ Seestar (o) reachable · Internet (o) · 4 s ago│          21:04:05 UTC, mount slewing             │
│      │ Server 127.0.0.1:8742 · v0.4.2 · open        │ [x] Look up target names online after a GoTo     │
│      │                                              │ {disclosure} How to connect Stellarium           │
│      ├──────────────────────────────────────────────┴─────────────────────────────────────────────────┤
│      │ {log} CONNECTION LOG  (connection · discovery · planetarium)                       {clear} {log}│
│      │ 21:03:58 UTC INFO  Starting Alpaca discovery…                                                   │
│      │ 21:04:01 UTC OK    Found 192.168.1.42:32323                                                     │
│{nav-c│ 21:04:05 UTC OK    Mount connected: Seestar S30 Pro                                             │
│ Set  │ 21:04:16 UTC ERROR Camera: timed out                                                            │
├──────┴────────────────────────────────────────────────────────────────────────────────────────────────┤
│ status: (o) Connected Seestar S30 Pro | Seestar (o) Internet (o) | …                           Log   │ 32
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
 Left column 660 px, right column 664 px, 12 px gaps. Cards ~150-200 px high; the log takes the
 remaining height (about 300 px at 900). Nothing scrolls except the log.
```

W2 Discovery results popover (anchored under "Discover", 320 px)

```
┌ Devices found ──────────────────────────┐
│ ( ) 192.168.1.42 : 32323                │
│ ( ) 10.0.0.1 : 32323                     │
│ Searched: broadcast, then subnet scan    │
│                     <Cancel> <Use address>│
└──────────────────────────────────────────┘
 One result: filled directly + info line "Found 192.168.1.42:32323" (as Qt).
 None: inline under the field, warning tone: "No Alpaca devices found (broadcast, direct
 probes and subnet scan)." Busy: button spinner + "Searching the network (up to ~15 s)…".
```

W3 Settings shell, category "Observer & site"

```
┌──────┬────────────────┬──────────────────────────────────────────────────────────────┬───────────────┐
│ rail │ Settings       │ Observer & site                                     Saved    │ ABOUT THIS    │
│      │ {search}[Filter]│─────────────────────────────────────────────────────────────│ SETTING       │
│      │ {site} Observer│ OBSERVER                                                     │ Latitude      │
│      │   & site    <  │ Name            [Jules Perret                    ]           │ Written to    │
│      │ {mount} Instr. │ AAVSO code      [PJUA  ]  Stamped on every AAVSO export      │ FITS SITELAT; │
│      │ {plate-solve}  │ DEFAULT SITE    Written to FITS SITELAT / SITELONG / SITEELEV │ used for      │
│      │   Plate solving│ Site name       [Home observatory                ]           │ airmass, Moon │
│      │ {catalogue}    │ Latitude  [+48.82770] °   Longitude [+2.38260] ° (east +)    │ and target    │
│      │   Catalogues   │ Elevation [60.0] m                                           │ visibility.   │
│      │ {photometry}   │ FIND A PLACE  online: OpenStreetMap Nominatim, Open-Meteo     │ Default 0.0 ° │
│      │   Photometry   │ [Berkeley, France, Mauna Kea…              ] {search} Search │ Key           │
│      │ {browse} Data  │ ( ) Mauna Kea, Hawaii, United States  +19.82073 −155.46806 4167 m │ site.latitude │
│      │   & storage    │ ( ) Mauna Kea Observatories …                                │ Used by FITS  │
│      │ {log} Privacy &│ Elevation is terrain-modelled: edit it for a surveyed site.  │ writer, plan  │
│      │   diagnostics  │                                     {site} Use as default site│ visibility    │
│      │ {theme} Appear.│ SAVED SITES                                                  │               │
│      │ {about} About  │ Name           Latitude    Longitude    Elev.                │               │
│      │                │ Home [Default] +48.82770   +2.38260     60 m  {bookmark}{remove}│             │
│      │                │ Pic du Midi    +42.93639   +0.14278   2877 m  {bookmark}{remove}│             │
│      │                │ [Name for the current site     ] {bookmark} Save current site│              │
└──────┴────────────────┴──────────────────────────────────────────────────────────────┴───────────────┘
 Category list 208 px; form max 880 px; help column 260 px, shown only at ≥ 1440 px (Q16),
 otherwise the help is a caption under the field. The header shows "Saved" for 2 s after a
 commit, or the server's error.
```

W4 Settings › Instrument

```
│ Instrument                                                                       │
│ TELESCOPE PROFILE   Locked while equipment is connected                          │
│ Telescope  [ZWO Seestar S30 Pro                     v]   [Validated]             │
│ 30 mm · f/5.3 · IMX585 · 2.9 µm · 3.74″/px · 3.99° × 2.24° · GRBG · ADC 12 bit   │
│ Do not change it mid-series: the plate scale would move under a running curve.   │
│ SENSOR LIMITS (override the profile for your unit)                               │
│ Saturation (full well)  [60000] ADU   Profile 60000   Used by the saturation overlay│
│ Linearity limit         [50000] ADU   Profile 50000   Flags saturated photometry   │
│ PHOTON-TRANSFER CALIBRATIONS                                                     │
│ Folder [/Users/…/.argos                                   ] {browse}             │
│ camera_calibration*.json, used only when the driver gives no electron gain.      │
```

W5 Settings › Plate solving

```
│ Plate solving                                                    ASTAP (o) Found  │
│ ASTAP executable   [Auto-detect (astap_cli on PATH)              ] {browse}       │
│                    /opt/homebrew/bin/astap_cli                                    │
│ Star database folder [Auto-detect                                ] {browse}       │
│                    Database: /opt/homebrew/opt/astap/… (D50)                      │
│ Database set       [Auto                 v]  Ignored while a folder is set        │
│ Search radius      [30] °   0 = blind, whole sky                                  │
│ Downsample         ( Auto | 1× | 2× | 3× | 4× )                                   │
│ [x] Use the known plate scale as a hint (faster solve)                            │
│ Coordinate grid    [0] ′   0 = adaptive                                           │
│ {disclosure} Automatic solving (advanced, Q8)                                      │
│    Live search radius [5] °  Re-solve every ≤ [20] s  or after [2] ′  Timeout [25] s│
│ Solving runs on the green channel.                                                │
```

W6 Settings › Catalogues

```
│ Catalogues                                                                        │
│ BUNDLED  Argos Essential Catalogue v1.0 · 13 229 objects · offline, read-only     │
│          Source CDS/VizieR VII/118 (NGC 2000.0, Sinnott 1988)                     │
│ IDENTIFICATION BUDGET ( 100 | 200 | 400 | 800 | 1 600 )  Shared by Gaia and SIMBAD │
│ {variable-star} VARIABLE STARS (AAVSO VSX)                                        │
│   Faint limit ≤ [15.0]   Maximum [250]   [x] Include suspected variables          │
│ {field-stars} [on] FIELD STARS (Gaia DR3)                                         │
│   Depth ( Bright ≤ 15 | Standard ≤ 18 | Deep ≤ 20 | Custom )  G ≤ [18.0]          │
│   [ ] Only draw sources detected in the image                                     │
│ {galaxy} CONTEXT LAYERS (local, never online)                                     │
│   [x] Bundled Messier, NGC and IC objects   [x] Cached exoplanet hosts            │
│ {other-objects} [on] NAMED OBJECTS (SIMBAD)  [x] Query SIMBAD when not cached     │
│ {exoplanet} [on] EXOPLANET HOSTS (NASA)      [x] Query NASA when not cached       │
│ HD stays an online / cache lookup (no versioned J2000 pack yet).                  │
```

W7 Settings › Data & storage

```
│ Data & storage                                                                    │
│ Sessions folder        [/Users/…/Argos/sessions                    ] {browse} (o) writable │
│ Sequence presets       [/Users/…/Argos/sequences                   ] {browse}     │
│ CATALOGUE CACHES  Never uploaded. Clearing makes the next lookup fetch fresh data.│
│ Cache                       Location                          Status   Actions   │
│ Target names (CDS/SIMBAD)   …/Argos/cache/object_resolver.json cached  {browse} {clear} Clear… │
│ Transit ephemerides (NASA)  …/Argos/cache/exoplanets.json      empty   {browse} {clear} Clear… │
│ Variables (AAVSO VSX/VSP)   …/.argos/cache/catalog              24 fields {browse} {clear} Clear… │
│ Field stars (Gaia DR3)      …/.argos/cache/gaia                 41 fields {browse} {clear} Clear… │
│ Field identities (SIMBAD/NASA) …/.argos/cache/field_catalogue   61 fields {browse} {clear} Clear… │
```

W8 Settings › Photometry, Privacy & diagnostics, Appearance, About

```
│ Photometry   (keys of the Observe photometry setup + config-only defaults, Q8/Q9)   │
│ Automatic comparison stars [5]   AAVSO band [TG]   Read noise [1.5] e⁻             │
│ Minimum comparisons [2]   Systematic floor [auto | __ mag]   [x] Track apertures   │
│ {disclosure} Comparison validation: min points [10] · max scatter [0.10] · max error [0.10] │
├────────────────────────────────────────────────────────────────────────────────────┤
│ Privacy & diagnostics                                                              │
│ ONLINE SERVICES (each used only after an explicit action or field solve)           │
│ [x] SIMBAD when a field is not cached   [x] NASA when a field is not cached        │
│ [ ] Stellarium GoTo: look up target names online (CDS/SIMBAD)                      │
│ Place search: OpenStreetMap Nominatim + Open-Meteo, only when you press Search     │
│ Reachability check: TCP to 1.1.1.1 / 8.8.8.8 every 10 s (Q7)                       │
│ LOCAL RECORDS  [ ] Save per-frame diagnostic records   Log level ( DEBUG | INFO | WARNING | ERROR ) │
│ Log folder ~/Library/Logs/Argos (macOS; support_bundle.py:57-64)  {support-bundle} Create support bundle… │
├────────────────────────────────────────────────────────────────────────────────────┤
│ Appearance   Theme ( Observatory | Charcoal | Night Red )                          │
├────────────────────────────────────────────────────────────────────────────────────┤
│ About   [ARGOS mark] ARGOS 0.4.2 · API 1 · GNU GPL v3 or later · credits          │
│         {help} Documentation & website                                             │
```

W9 Observe popovers (owned with the Observe spec; replace the modal dialog)

```
 W9a anchored to the plate-solve tool        W9b anchored to the catalogue tool (360 px)
┌ Plate-solve options ─────────────┐        ┌ Catalogues & depth ───────────────────┐
│ Search radius [30] °             │        │ Budget ( 100 | 200 | 400 | 800 | 1600 )│
│ Downsample ( A | 1 | 2 | 3 | 4 ) │        │ VSX ≤ [15.0]  max [250]  [x] suspected │
│ [x] Plate-scale hint             │        │ [on] Gaia  ( ≤15 | ≤18 | ≤20 | Custom ) │
│ Grid spacing [0] ′ (adaptive)    │        │      G ≤ [18.0]  [ ] detected only      │
│ ASTAP (o) Found                  │        │ [x] Messier/NGC/IC  [x] cached hosts    │
│ {settings} All plate-solving     │        │ [on] SIMBAD  [x] online if not cached   │
│   settings                       │        │ [on] NASA    [x] online if not cached   │
└──────────────────────────────────┘        │ Automatic comparison stars [5]          │
                                            │ {settings} All catalogue settings       │
                                            └─────────────────────────────────────────┘
 Changes apply at once; the field is re-queried 500 ms after the last change.
```

W10 Confirmations (modal, text-only buttons, BRAND 7)

```
 W10a                                          W10b
┌ Clear the Gaia DR3 field-star cache? ───┐   ┌ Disconnect the equipment? ─────────────┐
│ 41 field files in …/.argos/cache/gaia.   │   │ A sequence is running (frame 12 of 40).│
│ Nothing is downloaded now; the next      │   │ Disconnecting stops it and the current │
│ matching lookup fetches fresh data if    │   │ exposure is lost.                      │
│ the internet is available.               │   │                                        │
│                  <Cancel> <Clear cache>  │   │            <Cancel> <Disconnect all>   │
└──────────────────────────────────────────┘   └────────────────────────────────────────┘
 Also W10b variant for a slewing mount ("The mount is slewing. Disconnect it anyway?").
```

W11 In-app folder browser (browser mode, and Night Red where OS dialogs draw grey; Q10)

```
┌ Choose the sessions folder ─────────────────────────────────┐
│ / Users / jperret / Argos /                     (breadcrumb)│
│ {disclosure} cache                                                   │
│ {disclosure} sequences                                               │
│ {disclosure} sessions                                                │
│ [/Users/jperret/Argos/sessions                    ]         │
│                                  <Cancel> <Choose folder>   │
└─────────────────────────────────────────────────────────────┘
```

### 2.4 Interaction and states

Connection screen

| State | What the observer sees |
|---|---|
| Server unreachable / token rejected | Link card shows the server line in warning tone + "Retry server"; every hardware action disabled with reason "the ARGOS server is not reachable" (existing `connectReason`) |
| Disconnected, no address | "Connect all" disabled, reason "enter the Seestar address" (fixes the silent Qt return) |
| Discovering | "Discover" busy (spinner, `aria-busy`), address field read-only, log lines arrive; result per W2 |
| Connecting | Per-device row spinner in State; "Connect all" busy; other rows stay usable; the GUI never freezes (server work off the event loop) |
| Partial / error | Row in danger tone with the full reason (two lines, full text in tooltip and log) and "Retry"; header badge "2 of 4 devices ready" |
| Mount lost | Row "Lost · retrying every 10 s" (warning) with "Stop retrying" (= disconnect) |
| All ready | Header "Equipment ready" (disabled primary), profile select locked with reason |
| Profile mismatch | Instrument card shows the server warning "This looks like a {name}…" inline (today log only) |
| Stellarium | Stopped / Starting / Listening (port, host, clients) / Error (bind message shown on the card) / last GoTo with time and the outcome ("mount slewing", "mount not connected") |

Settings screen

| Topic | Rule |
|---|---|
| Save model | Immediate apply on commit: text and number fields on Enter or blur, toggles / selects / segmented on change; one `PATCH /api/config` per commit. Header shows "Saved" 2 s, or the server message in danger tone; the field keeps the rejected text until Esc reverts it |
| Sync | A `config` WS event updates every bound control on every screen; a field being edited is not overwritten, it shows "Changed elsewhere" with a reload link (fixes the Qt stale overwrite) |
| Validation | Client ranges as in Qt; server re-validates (types are strict, protocol.md "Errors"); paths: "does not exist, will be created" (warning) vs "not writable" (error) |
| Dependent controls | Disabled with a reason when their parent switch is off (Gaia, SIMBAD, NASA) |
| Long work | Place search, ASTAP detection and cache counts show a busy state; place search can be abandoned by editing the query (result ignored) |
| Empty states | No favourites: "No saved sites yet." with the save row; no search results: the Qt failure text inline; caches empty: "empty" |
| Destructive | Clear cache: W10a. Remove saved site: immediate + undo toast. Disconnect during activity: W10b |
| Restart | Nothing requires a restart in the web UI (theme live, log level applied by the server) |

Keyboard: F1 Connection, F5 Settings (existing); proposed `⌘,` / `Ctrl+,` opens Settings and `/`
focuses the settings filter when focus is not in a text field; ↑ / ↓ moves in the category
list; Enter submits the place search (explicit, network); Esc closes popovers and dialogs.
No single key connects, disconnects or starts the bridge (BRAND 7: they move or release
hardware).

Night Red: every select, checkbox, switch and segmented control is token-drawn (no native
select, BRAND 4.3); no pictographs (the Qt "⚡ ▶ ■ ↗ ✗ ✓ ○ ●" become icons or CSS dots);
every state is double-coded by a word (the success dot is 2.32:1 there); file pickers use W11
because OS dialogs draw grey; the Stellarium help and long captions use `--text-muted`, never
`--fg-muted`.

Persistence: server config for every science or path setting (appendix A); localStorage
(try/catch, `prefs.ts`) for per-viewer conveniences only: theme (applied before first paint,
existing), selected Settings category (`argos.settings.category`), help column open,
Connection log open, Stellarium help disclosure.

Visible without scrolling at 1440 x 900: on Connection, the header actions, Instrument, Link,
all four device rows, the whole Planetarium card and the start of the log. On Settings, the
category list and every category except Catalogues and Photometry (their advanced groups are
folded by default).

### 2.5 API needs beyond v1

| Name | Kind | Payload sketch | Core / worker code it wraps | Notes |
|---|---|---|---|---|
| Read config | GET `/api/config` | `{values: {key: value}, meta: {key: {type, default, min, max, step, options, unit, restart: false}}}` | `Config.get`, `_DEFAULTS` config.py:19-176, 231-239 | Meta is the single source for Settings forms and the help column |
| Write config | PATCH `/api/config` | `{"site.latitude": 48.8277}` -> `{values, warnings: [{key, message}]}`; 400 `invalid_argument` per key | `Config.set` config.py:241-248; side effects of configuration_page.py:1040-1084 (cache dirs, calibration dir), 1200-1206 (diagnostics marker), 1233-1257 (theme name), `configure_local_logging` (support_bundle.py:67) for `ui.log_level` | Strict types; atomic per request; writes the file once |
| Config changed | WS `/ws/events` `{"type": "config", "changed": {key: value}}` | — | new hub broadcast after PATCH | Keeps Observe popovers and Settings in sync |
| Telescope profiles | GET `/api/profiles`; PUT `/api/profile` `{key}` -> 409 `busy` when any device is connected | `[{key, name, validated, caveats, aperture_mm, focal_length_mm, focal_ratio, sensor, pixel_size_um, sensor_px, bayer, arcsec_per_px, fov_deg, adc_bits, full_well_adu, linearity_max_adu, ap_host}]` | catalog.py:99-112, profile.py:27-121, `apply_telescope_profile` connection_page.py:237-258, active.py:56-89 | Status record gains `profile` key |
| Per-device connection | POST `/api/devices/{mount|camera|filterwheel|focuser}/connect` `{host, port}`; DELETE `/api/devices/{id}`; POST `/api/devices/connect-all`; DELETE `/api/devices` | Returns `DevicesState` | `DeviceSession.connect_device / disconnect_device / connect_all / disconnect_all` device_session.py:230-263, 265-501 | Long (up to 10 s per device): run in a worker, return 202 or block like `POST /api/connection`; connect-all must skip connected devices (fixes the duplicate poller) |
| Device states | Field `devices` in `status` + WS `{"type": "devices", ...}` | `{mount: {state, info, retrying}, camera: {...}, filterwheel: {...}, focuser: {...}}` | `device_state_changed` emits (device_session.py:292-297, 346, 363-366, 427, 445-448, 457, 485-488, 500, 553-555, 563), `_mount_retry` 155-160, 557-567 | Full error text (no 48-char cut); `retrying` for the auto-reconnect |
| Discovery | POST `/api/discovery` -> 202; WS `{"type": "discovery", "state": "running|done|failed", "devices": [{host, port}], "message"}` | — | `DiscoveryWorker` discovery_worker.py:50-64, `discover_all` discovery.py:167-199, candidates device_session.py:205 | 8-15 s; not cancellable in core; return all devices (Qt keeps the first) |
| Network reachability | WS `{"type": "network", "seestar": true|false|null, "internet": bool, "t"}` every 10 s | — | `NetworkMonitor._check` network_monitor.py:79-84 | Opt-in or not per Q7 |
| Stellarium bridge | POST `/api/stellarium` `{port, host?}`; DELETE `/api/stellarium`; WS `{"type": "stellarium", "running", "host", "port", "clients", "error", "last_goto": {ra_hours, dec_deg, t}}` | — | `start_stellarium / stop_stellarium` device_session.py:783-816, `StellariumWorker` stellarium_worker.py:24-130, mount feed device_session.py:550-551 | Bind errors reported in the event |
| Stellarium GoTo fan-out | Server-side reaction + WS `{"type": "target_suggestions", "candidates": [...]}` | — | shell.py:346-353, `ImagingPage.goto_target` imaging_page.py:2775-2788, `suggest_target_from_coordinates` 2733-2763 | Shared with the Observe spec (mount GoTo, name suggestion) |
| Place search | POST `/api/site/search` `{query}` -> `[{label, latitude, longitude, elevation_m}]` | — | `search_locations` location_resolver.py:34-87 | Up to 6 HTTP calls x 8 s; the client may abandon; errors as the Qt texts |
| ASTAP detection | GET `/api/astrometry/astap?path=&database_path=` -> `{astap: path|null, database_dir, database_found, database_args}` | — | `find_astap`, `find_astap_db` platesolve.py:119-144, glob configuration_page.py:1208-1231, `_database_args` platesolve.py:305-319 | `database_args` exposes which of set / folder is used |
| Catalogue caches | GET `/api/caches` -> `[{kind, label, path, exists, files}]`; DELETE `/api/caches/{kind}` | — | configuration_page.py:1104-1163; `configure_cache_*` object_resolver.py:38, exoplanets.py:28-37, aavso.py:63, gaia.py:50, field_objects.py:49 | Delete is synchronous and local |
| Bundled catalogue info | GET `/api/catalogues/essential` | `{name, version, source, source_url, object_count}` | `essential_catalogue_info` catalog/offline.py:69 | Static |
| Catalogue refetch | Automatic after a PATCH of `catalog.*` (debounced), or POST `/api/catalog/refetch` | — | `AcquisitionEngine.refetch_catalog` acquisition_engine.py:815 (shell.py:471) | Only when a solved field exists |
| Path picking | GET `/api/fs/list?path=&kind=dir|file` -> `{path, parent, entries: [{name, kind}]}` | — | new (Path.iterdir) | For W11 in the browser and Night Red; Tauri dialog plugin otherwise; token-protected, localhost only |
| Start-up configuration | Server behaviour | — | configuration_page.py:823-824 (cache and calibration dirs are applied when the Qt Settings page is built), active.load_from_config (already in server/__main__.py:70-82) | The headless server must apply data paths at launch |
| Log topics | Field `topic` in WS `log` messages: `connection | discovery | planetarium | config | …` | — | `log_message` emitters in device_session.py | Lets the Connection log filter without parsing text |
| About | GET `/api/about` | `{version, api, licence, credits, project_url}` | shell.py:67, 535-600 | Version already in `/api/health` |
| Support bundle | POST `/api/support-bundle` `{session_dir?, destination}` | — | shell.py:478-533, `create_support_bundle` support_bundle.py | Cross-area (shell spec) |

## 3. Open questions for the owner

1. Telescope profile: editable in both Connection and Settings › Instrument (same guard), or
   only on Connection with a read-only mirror in Settings?
2. Sensor limits: keep `camera.full_well_adu / linearity_max_adu` (what the code reads today)
   or move the readers to the profile + `hardware.overrides` as config.py:75-77 intends? Should
   `ADC bits` stay editable although no code reads it?
3. Unvalidated profile wording: "do not use it for scientific photometry" (Connection) or
   "never run on this hardware" (Settings)?
4. Language: drop the selector until a translation exists?
5. Theme: keep it per viewer (localStorage, needed before first paint) and import the Qt
   `ui.theme.preset` once, or make the config key authoritative?
6. Stellarium host: keep 127.0.0.1 only, or allow binding to the LAN for Stellarium on
   another computer (security trade-off)?
7. Reachability probe to 1.1.1.1 / 8.8.8.8 every 10 s: keep, make opt-in, or check only on
   demand (it is the only network use without an explicit action)?
8. Config-only keys with no Qt editor (`astrometry.live_*`, `photometry.default_band`,
   `read_noise_e`, `min_comparisons`, `systematic_floor_mag`, `comparison_validation_*`,
   `track_apertures`, `camera.egain_table`): expose them under "advanced" disclosures or keep
   them file-only? The AAVSO band (`TG`) is the most consequential.
9. Photometry: a Settings category, or only the Observe photometry setup (point of use)?
10. Path pickers: Tauri native dialog everywhere, or the in-app browser W11 in Night Red and
    in the browser build?
11. Default landing section: Connection when nothing is connected (Qt, shell.py:93-96) or
    Observe (current web)?
12. Confirm "Disconnect all" only while something runs (proposed), always, or never?
13. Per-category "Restore defaults" in Settings (needs a new icon)?
14. Remove the dead keys (`field_stars_max_results`, `named_objects_max_results`,
    `ui.window_state`, `ui.window_geometry`, `camera.adc_bits`?) from the defaults?
15. "About this setting" help column at ≥ 1440 px (config key, default, used by)?
16. Database set vs folder: show "ignored while a folder is set", or change the core to pass
    both `-D` and `-d`?
17. Should the Connection screen show the default site (read-only)?
18. Network reachability: does "Seestar down" mean anything before an address is set (Qt shows
    the same hollow dot for "no host")?

---

## A. Configuration keys

File `~/.argos/config.json` (config.py:16-17). Defaults are deep-merged on load (209); five
migrations run on load (210-214). "Qt editor" lists every UI writer; "Read by" every reader
outside config.py. Web location uses the categories of 2.1.

| Key | Type | Default (config.py) | Qt editor | Read by | Web location | Notes |
|---|---|---|---|---|---|---|
| `alpaca.host` | str | "" (21) | connection_page.py:356; device_session.py:266, 352, 431, 461 | connection_page.py:349; device_session.py:205; network_monitor.py:80 | Connection › Link | Written per keystroke today |
| `alpaca.port` | int | 32323 (22) | connection_page.py:361; device_session.py:267, 353, 432, 462 | connection_page.py:350; device_session.py:207; network_monitor.py:81 | Connection › Link | Legacy `alpaca.profiles` flattened by `_migrate_alpaca_profiles` (377-396) |
| `sessions_path` | str | ~/Argos/sessions (24) | configuration_page.py:1012, 1020 | property 268-270 -> shell.py:495; analyze_page.py:607, 736, 769; imaging_page.py:1319, 2283, 2299; analysis_window.py:440; acquisition_engine.py:639 | Data & storage | |
| `data_paths.sequence_presets_directory` | str | ~/Argos/sequences (31) | configuration_page.py:1083 | sequence_panel.py:890 | Data & storage | |
| `data_paths.camera_calibration_directory` | str | ~/.argos (34) | configuration_page.py:1084 | applied at configuration_page.py:1080-1081 (sensor_reference.py:20, imx585.py:55) | Instrument | Applied only when the Settings page is built |
| `data_paths.object_catalogue_cache` | str | ~/Argos/cache/object_resolver.json (35) | configuration_page.py:1065 | applied 1058 (object_resolver.py:38) | Data & storage › caches | |
| `data_paths.exoplanet_cache` | str | ~/Argos/cache/exoplanets.json (36) | 1066 | applied 1059 (exoplanets.py:28) | Data & storage › caches | |
| `data_paths.aavso_cache_directory` | str | ~/.argos/cache/catalog (37) | 1067 | applied 1060 (aavso.py:63) | Data & storage › caches | |
| `data_paths.gaia_cache_directory` | str | ~/.argos/cache/gaia (38) | 1068 | applied 1061 (gaia.py:50) | Data & storage › caches | |
| `data_paths.field_catalogue_cache_directory` | str | ~/.argos/cache/field_catalogue (39-41) | 1069-1071 | applied 1062-1063 (field_objects.py:49 + /simbad, exoplanets.py:34 + /nasa) | Data & storage › caches | |
| `observer.name` | str | "" (44) | configuration_page.py:857 | acquisition_engine.py:626, 1524 -> FITS OBSERVER (fits_writer.py:462) | Observer & site | |
| `observer.obscode` | str | "" (45) | configuration_page.py:858 (upper-cased) | imaging_page.py:2096, 2127, 2384 (fallback "XXX"); analyze_page.py:307 | Observer & site | |
| `observer.latitude / longitude / elevation` | float | 0.0 (46-48) | none | `_migrate_legacy_site` only (328-342) | — (legacy) | Dead after migration |
| `site.name` | str | "" (51) | configuration_page.py:864 | sequencer_page.py:149 | Observer & site | |
| `site.latitude` | float | 0.0 (52) | configuration_page.py:865 | sequencer_page.py:85, 153; imaging_page.py:2302; acquisition_engine.py:627, 1360, 1525 | Observer & site | FITS SITELAT |
| `site.longitude` | float | 0.0 (53) | configuration_page.py:866 | sequencer_page.py:86, 154; imaging_page.py:2303; acquisition_engine.py:628, 1360, 1526 | Observer & site | FITS SITELONG |
| `site.elevation` | float | 0.0 (54) | configuration_page.py:867 | sequencer_page.py:155; imaging_page.py:2304; acquisition_engine.py:629, 1361, 1527 | Observer & site | FITS SITEELEV |
| `site.favorites` | list[{name, latitude, longitude, elevation}] | [] (55) | configuration_page.py:965, 988-991 | configuration_page.py:932 | Observer & site › Saved sites | |
| `ui.log_level` | str DEBUG/INFO/WARNING/ERROR | INFO (58) | configuration_page.py:1268 | main.py:144 (start-up); shell.py:513 | Privacy & diagnostics | Web: applied live |
| `ui.window_state`, `ui.window_geometry` | base64 / None | None (59-60) | none | none | — | Dead defaults (the Shell uses `ui.shell.*`) |
| `ui.theme.preset` | str palette name | not in defaults; "Observatory" (configuration_page.py:826, main.py:99) | configuration_page.py:1255 | main.py:97-101 | Appearance | Web theme is per viewer today (Q5) |
| `ui.language` | str en/fr | not in defaults; "en" | configuration_page.py:1262 | none | — (dropped, Q4) | No effect |
| `ui.display.rotation` | str auto/0/90/180/270 | not in defaults; "auto" | imaging_page.py:727 | imaging_page.py:573; analysis_window.py:296 | Observe (per viewer) | Owned by the Observe spec |
| `ui.shell.geometry`, `ui.shell.state`, `ui.shell.mode` | base64 / str | not in defaults | shell.py:406, 444-445, 453-454 | shell.py:93, 430-431 | — (Qt window state) | No web equivalent; section memory is per viewer |
| `ui.imaging.layout`, `ui.sequencer.layout`, `ui.review.layout` | base64 | not in defaults | imaging_page.py:498, 502; sequence_panel.py:582, 586; analyze_page.py:421, 424; shell.py:455-456 | imaging_page.py:487; sequence_panel.py:566; analyze_page.py:410 | — (Qt dock layouts) | Each screen spec decides |
| `hardware.profile` | str s30pro/s30/s50 | s30pro (68) | connection_page.py:254; configuration_page.py:594 | active.py:98 (main.py:167, server/__main__.py:80); shell.py:512 | Connection › Instrument (+ Settings › Instrument) | Unknown key falls back to s30pro (active.py:100-106) |
| `hardware.overrides` | dict of adc_bits, full_well_adu, linearity_max_adu, ap_host | {} (69) | none (migration only, config.py:301-325) | active.py:108; connection_page.py:255; configuration_page.py:596 | Instrument › Sensor limits (Q2) | Overridden profile fields have no reader except `ap_host` |
| `camera.adc_bits` | int | 12 (79) | configuration_page.py:1006 | none | Instrument (read-only, Q2) | Declared deprecated (75-77) |
| `camera.full_well_adu` | int ADU | 60000 (80) | configuration_page.py:1004 | imaging_page.py:722; analysis_window.py:458 | Instrument › Sensor limits | Saturation overlay threshold |
| `camera.linearity_max_adu` | int ADU | 50000 (81) | configuration_page.py:1005 | photometry/params.py:64 | Instrument › Sensor limits | Photometry saturation flag |
| `camera.egain_table` | dict gain -> e⁻/ADU | {} (82) | none | imaging_page.py:2329; acquisition_engine.py:1248 | Instrument (advanced, Q8) | |
| `astrometry.astap_path` | str | "" (87) | configuration_page.py:1176; astrometry_settings.py:355 | astrometry_session.py:63; shell.py:515 | Plate solving | |
| `astrometry.database` | str ""/D05…W08 | "" (88) | configuration_page.py:1178; astrometry_settings.py:356 | astrometry_session.py:64 (ignored when `database_path` is set) | Plate solving | |
| `astrometry.database_path` | str | "" (89) | configuration_page.py:1177 | astrometry_session.py:64 | Plate solving | |
| `astrometry.downsample` | int 0-4 | 2 (90) | configuration_page.py:1180-1182; astrometry_settings.py:358-360 | astrometry_session.py:66 | Plate solving (+ W9a) | |
| `astrometry.search_radius_deg` | int ° | 30 (91) | configuration_page.py:1179; astrometry_settings.py:357 | astrometry_session.py:59 | Plate solving (+ W9a) | |
| `astrometry.use_scale_hint` | bool | True (92) | configuration_page.py:1183; astrometry_settings.py:361 | astrometry_session.py:52 | Plate solving (+ W9a) | |
| `astrometry.grid_spacing_arcmin` | int ′ | 0 (93) | astrometry_settings.py:362 | astrometry_session.py:151 | Plate solving (+ W9a) | |
| `astrometry.live_search_radius_deg` | float ° | 5 (94) | none | astrometry_session.py:57 (code fallback 30.0) | Plate solving › advanced (Q8) | |
| `astrometry.live_resolve_s` | float s | 20 (95) | none | astrometry_controller.py:139 | Plate solving › advanced (Q8) | |
| `astrometry.live_resolve_arcmin` | float ′ | 2 (96) | none | astrometry_controller.py:152, 173 | Plate solving › advanced (Q8) | |
| `astrometry.live_timeout_s` | float s | 25 (97) | none | astrometry_session.py:60 | Plate solving › advanced (Q8) | |
| `catalog.mag_limit` | float mag | 15.0 (101) | astrometry_settings.py:363 | acquisition_engine.py:880; analysis_window.py:609 | Catalogues (+ W9b) | |
| `catalog.max_results` | int | 250 (102) | astrometry_settings.py:364 | acquisition_engine.py:881; analysis_window.py:610 | Catalogues (+ W9b) | |
| `catalog.include_suspected` | bool | True (103) | astrometry_settings.py:365 | acquisition_engine.py:882; analysis_window.py:611 | Catalogues (+ W9b) | |
| `catalog.field_stars_enabled` | bool | True (106) | astrometry_settings.py:366 | acquisition_engine.py:861; imaging_page.py:1066; analysis_window.py:596 | Catalogues (+ W9b) | |
| `catalog.field_stars_mag_limit` | float G | 18.0 (112) | astrometry_settings.py:367 | acquisition_engine.py:887; imaging_page.py:319, 1436; analysis_window.py:189, 572, 618 | Catalogues (+ W9b) | Upper bound of the image depth slider |
| `catalog.field_stars_max_results` | int | 2000 (113) | astrometry_settings.py:372 | none | — (drop, Q14) | Dead |
| `catalog.identification_max_objects` | int 100-1600 | 400 (116) | configuration_page.py:1099-1102; astrometry_settings.py:368-371 | acquisition_engine.py:864 (clamped 50-5000); analysis_window.py:594 | Catalogues (+ W9b) | |
| `catalog.display_mag_limit` | float G | 18.0 (117) | imaging_page.py:1449; analysis_window.py:585 | imaging_page.py:190; analysis_window.py:167 | Observe overlay slider | Owned by the Observe spec |
| `catalog.display_limit_version` | int | 2 (118) | migration (357-358) | config.py:354 | — (internal marker) | |
| `catalog.field_stars_detected_only` | bool | False (122) | astrometry_settings.py:373-375 | imaging_page.py:1528 | Catalogues (+ W9b) | |
| `catalog.show_essential_objects` | bool | True (125) | astrometry_settings.py:376-378 | imaging_page.py:1620; analysis_window.py:765 | Catalogues (+ W9b) | |
| `catalog.show_cached_exoplanets` | bool | True (126) | astrometry_settings.py:379-381 | imaging_page.py:1628; analysis_window.py:788 | Catalogues (+ W9b) | |
| `catalog.named_objects_enabled` | bool | True (130) | astrometry_settings.py:382 | acquisition_engine.py:862; imaging_page.py:1067; analysis_window.py:597 | Catalogues (+ W9b) | |
| `catalog.named_objects_max_results` | int | 500 (131) | astrometry_settings.py:383 | none | — (drop, Q14) | Dead |
| `catalog.named_objects_allow_network` | bool | True (132) | astrometry_settings.py:384-386 | acquisition_engine.py:892; imaging_page.py:1075; analysis_window.py:623 | Catalogues (+ W9b, Privacy mirror) | |
| `catalog.exoplanet_hosts_enabled` | bool | True (133) | astrometry_settings.py:387-389 | acquisition_engine.py:894; analysis_window.py:625 | Catalogues (+ W9b) | |
| `catalog.exoplanet_hosts_allow_network` | bool | True (134) | astrometry_settings.py:390-392 | acquisition_engine.py:896; analysis_window.py:627 | Catalogues (+ W9b, Privacy mirror) | |
| `photometry.aperture_fwhm_mult` | float | 2.5 (138) | photometry_window.py:71 (via imaging_page.py:2154) | photometry/params.py:59 | Photometry (+ Observe setup) | Editor owned by the Observe / photometry spec |
| `photometry.aperture_min_px` | float px | 4 (139) | photometry_window.py:78 | params.py:58 | Photometry | |
| `photometry.annulus_in_px` | float px | 8 (140) | photometry_window.py:85 | params.py:60 | Photometry | |
| `photometry.annulus_out_px` | float px | 12 (141) | photometry_window.py:92 | params.py:61 | Photometry | |
| `photometry.read_noise_e` | float e⁻ | 1.5 (142) | none | params.py:63 | Photometry (advanced, Q8) | |
| `photometry.default_band` | str AAVSO band | "TG" (143) | none | params.py:65; acquisition_engine.py:1091; imaging_page.py:2097, 2128, 2385; analyze_page.py:310 | Photometry (Q8) | Goes into every AAVSO report |
| `photometry.min_comparisons` | int | 2 (144) | none | params.py:66 | Photometry (advanced, Q8) | |
| `photometry.auto_comparisons` | int 1-20 | 5 (145) | astrometry_settings.py:393; imaging_page.py:2169 | acquisition_engine.py:1096; imaging_page.py:2138 | Photometry (+ W9b, Observe setup) | |
| `photometry.comparison_min_snr` | float | 10.0 (149) | photometry_window.py:105 | acquisition_engine.py:1100 | Photometry | |
| `photometry.comparison_max_delta_mag` | float mag | 1.5 (150) | photometry_window.py:119 | acquisition_engine.py:1101 | Photometry | |
| `photometry.comparison_max_separation_arcmin` | float ′ | 25.0 (154) | photometry_window.py:136 | acquisition_engine.py:1102 | Photometry | |
| `photometry.comparison_validation_min_points` | int | 10 (155) | none | acquisition_engine.py:1398 | Photometry › advanced (Q8) | |
| `photometry.comparison_validation_max_scatter_mag` | float mag | 0.10 (156) | none | acquisition_engine.py:1400 | Photometry › advanced (Q8) | |
| `photometry.comparison_validation_max_formal_error_mag` | float mag | 0.10 (157) | none | acquisition_engine.py:1403 | Photometry › advanced (Q8) | |
| `photometry.systematic_floor_mag` | float mag or None | None (161) | none | acquisition_engine.py:1483 | Photometry (Q8) | None = derived after 10 points |
| `photometry.track_apertures` | bool | not in defaults; True (params.py:67) | none | params.py:67 | Photometry (Q8) | Missing from `_DEFAULTS` |
| `diagnostics.enabled` | bool | False (166) | configuration_page.py:1206 | acquisition_engine.py:661; imaging_page.py:2306; shell.py:514 | Privacy & diagnostics | Forced False on load unless the marker is set (362-374) |
| `diagnostics.local_opt_in_v1` | bool | not in defaults | configuration_page.py:1205 | config.py:369-371 | — (server sets it with `enabled`) | |
| `stellarium.host` | str | 127.0.0.1 (169) | device_session.py:793 (no UI) | connection_page.py:95 | Connection › Planetarium (read-only, Q6) | |
| `stellarium.port` | int 1024-65535 | 10001 (170) | device_session.py:794 (on start) | connection_page.py:96 | Connection › Planetarium | Web: saved on commit |
| `stellarium.online_target_lookup` | bool | False (174) | shell.py:334-336 | shell.py:352; connection_page.py:97 | Connection › Planetarium (+ Privacy mirror) | |
