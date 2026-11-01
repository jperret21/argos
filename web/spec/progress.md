# ARGOS web UI: implementation progress

Status of the waves of [README.md section 7](README.md#7-implementation-plan-in-waves),
row by row. "Done" means built, wired to the server and checked in the running UI (scripted
checks and screenshots at 1440 x 900 in the three themes and at 1280 x 800); "partial" says
what is missing; nothing here is claimed from code reading alone.

## Wave 1: Shell and Connection (2026-11-01)

Scope: API rows A1-A4, A8-A10, A13-A18, A80, and A19 (the Stellarium bridge, brought
forward from W3 by the review round so that the exit criterion holds) (server,
`argos/server/protocol.md`, API 2); the shared components of the W1 row; the Connection
screen; the Observe changes D10 and D15.
Screenshots: `web/screenshots/2026-11-01_wave1-connection/` (final state after the review
fixes, 13 shots with captions) and `web/screenshots/2026-11-01_wave1-integration/` (the
integration state the reviews looked at, 36 shots).

**Status: wave 1 is complete.** Every row of section 1 below is done or partial for a
reason that belongs to a later wave, and every Qt Connection control of 02 section 2.2 has
its working web control (section 2). The review round (design and technical reviews,
section 4) was applied on 2026-11-01.

Verification (2026-11-01, server on port 8742 with a temporary `--config-dir`, `--log-dir`
and `HOME`; `~/.argos/config.json` untouched):

- 57 / 57 scripted UI checks in Observatory, Charcoal, Night Red at 1440 x 900 and
  Observatory at 1280 x 800, plus 6 link-loss checks (server stopped and restarted under the
  page). No console error except the browser's own line for the expected `502` of the
  closed-port test; no request left the machine.
- Discovery: a local fake responder answered the Alpaca broadcast with two ports, so the job
  ended at the broadcast stage (no subnet sweep of the LAN). Longest gap between animation
  frames while it ran: 17 ms. Cancel: "Cancelled" on screen about 160 ms after the click.
- Closed port (127.0.0.1:9): the camera row shows "Cannot reach 127.0.0.1:9 — Connection
  refused" in full, with Retry; toast and ERROR log line.
- Black-hole address (192.0.2.1): Connect all failed in 3.1 s (one 3 s address check for the
  four devices), four rows in error with the full reason; meanwhile the longest frame gap was
  17 ms, F2 switched section in 20 ms and `GET /api/status` answered in at most 3 ms.
- Night Red: 0 pixels that are neither black nor red-dominant in the six Night Red
  screenshots (1 296 000 pixels each).
- `npm run check`, `npm test`, `npm run build`, `.venv/bin/python -m pytest tests/server -q`:
  see the final report of the wave (all passing at the time of writing).

### 1. Mapping rows closed by the wave

| Row | Qt element | Web | Status |
|---|---|---|---|
| M1 | Start-up sequence `main.main` | `StartupScreen` over the shell (`App.svelte`): honest stage "Connecting to the ARGOS server…" until `GET /api/health` answers and `/ws/events` sends its first `status`; failure (server unreachable after 3 tries, token rejected 4401, page refused 4403, no status within 10 s) stays with the exact cause, Copy details, Retry; log folder from `GET /api/app/info` when known | Done (browser). The desktop sidecar stage ("Starting the ARGOS server…") and "Open log folder" wait for the Tauri shell (W8). |
| M2 | Splash | Same screen, themed before first paint (`index.html`), mark from `brand/argos-mark.svg` (never redrawn), wordmark in Plex Sans 600 | Done |
| M3 | `Shell` main window | `App.svelte`: NavRail + section + StatusBar, Toasts, start-up overlay | Done |
| M9 | `Sidebar` | `NavRail`: five entries, F1-F5 through the registry, revised state dots (Connection ready / active / attention, Observe ready / active, Settings attention while the observer code or the site is missing, Q-G11); footer: Help menu and theme button | Done. Plan and Review dots wait for their waves (nothing to report yet). |
| M10 | Rail context menu "Modes" | Dropped: the rail is always visible | Done (nothing to build) |
| M11 | `TopStatusBar` | StatusBar global segments: server link when down, device cluster (four marks, shape = state, link to Connection), Seestar / Net (three states each; "not in use" for an unreachable Seestar the simulator link does not use), mount state and RA / Dec from the mount's own device record (+ angle to go and Abort during a slew), run chip (LIVE, exposure), activity text (`activity` event: the last action **or its outcome**, UTC time, full text in the tooltip, muted once nothing runs), Log with unseen problems; priority folding (Rate / Latency fold first, the Log button never hides) | Partial: Alt-Az / EQ chip needs `MountState.alignment` (A29, W3); the sequence run chip comes with W6; tracking is shown through the mount state badge, not as its own segment. |
| M12 | `LogPanel` dock | One log store (`app.log`, 5 000 lines): `log` v2 events, replay on (re)connection, gaps and history from `GET /api/logs`, server restarts told by the server's `boot_id` (exact, whatever the ring size; a marker line in every view); windowed views (300 lines in the page, 300 more at the top), one notification per animation frame; Log tab in the drawer of Observe and the placeholders (`L`); on Connection `L` widens the screen's own log to every topic: level filter, debug toggle, search, copy, save, clear (view), follow / pause (paused only by the observer's own scrolling) | Done. Observe's drawer keeps a fixed height (its grid sets 216 px). |
| M13 | Dock mechanism | Panel host: foldable rail cards, drawer tabs, Panels popover (`arrange`) with Reset layout on Observe | Done for Observe (Camera, Mount, levels strip, Log). Plan and Review get theirs with their waves. |
| M17 | Implicit window status bar | Toasts (merged repeats, timed) + log lines; every failed request is a toast and a line | Done |
| M19 | Cross-page wiring | Server events consumed: `status`, `camera`, `mount`, `devices`, `network`, `activity`, `config`, `job`, `log` | Partial: `observation`, `stellarium`, `target_suggestions`, `sequence` arrive with W3-W6. |
| M21 | `ConnectionPage` | Connection screen: toolbar + two columns + filtered log, nothing scrolls but the log at 1440 x 900 and 1280 x 800 | Done |
| M22 | Start card | Instrument card (profile Select, specs, validated badge, Q-C2 wording and caveats, profile-mismatch warnings, site summary with a Settings link), Link card, toolbar Connect all / Disconnect all | Done |
| M23 | Device cards + bulk row | Devices table: four rows always visible, state word + mark, full reason, warnings, per-row Connect / Disconnect / Retry / Stop retrying / Cancel; bulk actions merged into the toolbar | Done ("Stop retrying" is wired and unit-tested; the mount auto-retry itself was not reproduced live: the simulator cannot lose its mount) |
| M24 | Details disclosure | Dropped: nothing is hidden | Done (nothing to build) |
| M25 | `StellariumCard` | Planetarium card on the server bridge (A19): Start / Stop bridge, state badge (Stopped / Listening · port / Error), the bind error in full, Stellarium clients, the last GoTo (RA / Dec, UTC time, outcome), host shown (read-only), port (disabled while the bridge runs) and online lookup saved to the config, help disclosure | Done. The target-name suggestion after a Stellarium GoTo (`target_suggestions`, shell.py:346-353) comes with W3, with the Observe GoTo work. |
| M26 | Network reachability | Status bar Seestar / Net + Link card lines with the time of the last check; Seestar probed by the server every 10 s, the internet only on request ("Check the internet") | Done |

Also delivered in this wave (README section 1.3 decisions): D10 (Connection card removed
from the Observe rail; the toolbar's equipment button connects or disconnects everything and
asks first while something runs), D15 (theme button moved to the rail footer, removed from
the Observe toolbar), D17 (one log store, Log tab everywhere), D21 (Escape aborts a slew from
any section, then closes the top layer), D22 (keymap), D28 (profile edited on Connection,
locked while a device holds the link).

### 2. Exit criterion: every Qt Connection control of 02 section 2.2 and its web control

| Qt ref | Qt control | Web control | Status |
|---|---|---|---|
| 1.2 #1 | Telescope model `QComboBox` | Instrument card `Select` "Telescope" (token-drawn), options with sensor and plate scale; locked with "Disconnect the equipment before changing the telescope: it sets plate scale, sensor geometry and FITS metadata." while a device is connected, connecting, busy or retrying; the server's `409` is shown verbatim if it refuses | Done |
| 1.2 #2 | IP address `QLineEdit` | Link card "Seestar address" (mono), saved to `alpaca.host` on Enter or leaving the field (never per keystroke), Esc reverts, server refusal shown under the field | Done |
| 1.2 #3 | Port `QSpinBox` | Link card "Alpaca port" 1-65535, integers, saved to `alpaca.port` on Enter or blur; range message under the field | Done |
| 1.2 #4 | Discover | Link card [discover Discover]: server job (A16) with JobProgress (stage, n of 3, elapsed, Cancel); one device fills the address, several open the "Devices found" popover (02 W2), none gives the warning line; address read-only while it runs | Done |
| 1.2 #5 | Connect equipment | Toolbar [connect Connect all] (primary), connects only what is not connected (A15) with the chosen link; the server claims the devices at once ("Queued" rows, profile locked, summary "checking the address…" then "connecting camera…"); "Equipment ready" (disabled) when the four are; disabled with "enter the Seestar address in the Link card" when empty (fixes the silent Qt return) | Done |
| 1.2 #6 | Disconnect equipment | Toolbar [disconnect Disconnect all] (danger); confirmation only while an exposure, live view or a slew runs (Q-C5, 02 W10b); also cancels a Connect all in progress, from its first moment (the address check included) | Done |
| 1.2 #7 | Show / hide details | Dropped: the device table is always visible | Done (dropped by decision) |
| 1.3 #1 | Telescope card button | Devices table, Mount row: Connect / Disconnect / Retry / Stop retrying / Cancel; disconnecting a slewing mount asks first | Done |
| 1.3 #2 | Camera card button | Camera row, same actions; disconnecting during an exposure or live view asks first | Done |
| 1.3 #3 | Filter Wheel card button | Filter wheel row, same actions | Done |
| 1.3 #4 | Focuser card button | Focuser row, same actions | Done |
| 1.3 #5 | Connect all (bulk row) | Merged into the toolbar Connect all | Done |
| 1.3 #6 | Disconnect all (bulk row) | Merged into the toolbar Disconnect all | Done |
| 1.4 #1 | Stellarium TCP port | Planetarium card "Port" 1024-65535, saved to `stellarium.port` on commit (Qt saved it only when the server started); disabled while the bridge runs, as in Qt | Done |
| 1.4 #2 | Start / Stop server | Planetarium card [planetarium Start bridge] / [stop Stop bridge] on `POST` / `DELETE /api/stellarium` (A19); state, clients, last GoTo and bind error on the card | Done (checked with a scripted Stellarium client: a GoTo slews the simulator's mount, a port in use is shown on the card) |
| 1.4 #3 | Online lookup `QCheckBox` | Planetarium card checkbox "Look up target names online after a GoTo" with the Qt tooltip as caption, saved to `stellarium.online_target_lookup` at once | Done (the Settings › Privacy mirror comes with W2) |
| (web) | Simulator / Seestar | Link card `Segmented` "Equipment"; follows the link the devices hold, locked while they hold it | Done |
| (web) | Retry server | Link card [refresh Retry server] while the event link is down; the start-up screen has its own Retry | Done |
| (new) | Stellarium host | Planetarium card "Host 127.0.0.1" (read-only, `stellarium.host`) | Done |
| (new) | Site summary | Instrument card "Site": name, signed coordinates (5 decimals), elevation, or the missing-site warning; [site Change in Settings] | Done (Settings itself is W2) |
| (new) | Connection log | `LogPanel` filtered on the topics connection, discovery, planetarium, with level filter, search, copy, save, clear, and [log] to open the full Log drawer (`L`) | Done |

Qt readouts of the same page: specs line (Instrument "Optics"), unvalidated warning (one Q-C2
wording + the profile's caveats), 2 x 2 summary ("n of 4 devices ready" in the toolbar and the
table states), device card status lines (table State + Detail, full text), Stellarium status
(badge), client count ("Clients") and GoTo flash ("Last GoTo", which no longer reverts to a
stale label).

### 3. Known gaps and issues (before wave 2)

- **Stellarium target names**: a GoTo from Stellarium slews the mount; the target-name
  suggestion (`target_suggestions`, local catalogue then the optional online lookup the
  card's checkbox enables) comes with W3. The checkbox is saved but not used yet.
- **Status bar**: no Alt-Az / EQ chip (A29, W3) and no sequence run chip (W6).
- **Help menu**: "Create support bundle…" and "About ARGOS" are listed disabled ("not
  available in this version yet"; they come with Settings, W2); Quit is desktop-only (W8).
- **Mount auto-retry** ("Lost · retrying every 10 s", Stop retrying) was not reproduced live:
  the simulator never loses its mount. Covered by the server tests and the UI model tests.
- **Real Seestar**: never connected in this wave; Alpaca was exercised against a closed port,
  a black-hole address and fake devices in the server tests only.
- **Library lock** (from the backend report): alpyca holds one process-wide lock per HTTP
  request; a device that accepts TCP and then hangs at the HTTP level can stall the other
  devices' requests for up to 5 s. The UI stays responsive (the event loop is free) but the
  other rows may wait.
- **Clear on a log view** clears the view of the one log store, so every log view is cleared
  (the server keeps its log; nothing is lost).
- **Reconnection delay**: after a server restart the event socket retries with a backoff
  capped at 10 s; "Retry server" reconnects at once.
- **Observe drawer height** is fixed (216 px).
- **Settings attention mark** (Q-G11) shows on a fresh configuration, while the observer code
  and the site can only be set in the Qt app until Settings ships (W2).
- **`--log-info` token** (INFO tags muted instead of brass, design review): applied in
  `design/tokens.css` and BRAND 4.1; it departs from the Qt colour mapping, so it needs the
  owner's sign-off (two lines to revert).
- **Toolbar wording**: spec 02 section 2.2 keeps the disabled "Equipment ready" button; the
  summary beside it now only counts ("4 of 4 devices ready"). The owner may prefer the
  other option of the design review (button "Connect all" with the reason in its tooltip).
- **WebKit** (the future Tauri webview) is untested; only headless Chrome was used.
- **Plan**: README section 7 lists A19 and the Planetarium card in W3; they shipped in W1
  (this section). W3 keeps the Stellarium target-name suggestion.

Fixed during the integration, before the review round (with tests): Disconnect all did not
stop a running Connect all, which went on connecting the remaining devices
(`argos/server/hub.py`, `tests/server/test_devices.py`); the log store dropped every line of a
restarted server as a duplicate, because the new process numbers its lines from 1 again (a
marker line now separates the two processes); a log view that followed the newest line lost
it when a drawer shrank the region.

### 4. Review round (2026-11-01): what was fixed

Design review (3 high, 11 medium, 9 low) and technical review (1 high, 4 medium, 3 low).
Every high and medium finding was fixed; every low one too, except the toolbar wording,
left to the owner (above).

| Finding | Fix |
|---|---|
| Log stopped following when a card above grew (H) | `LogView`: `overflow-anchor: none`; only a scroll the observer makes (wheel, touch, keys, scrollbar) pauses; a scroll caused by layout re-pins a following view. Checked: profile changed by mouse, discovery started, log still at the bottom. |
| Activity text stuck on "Connecting…" (H) | Server: every outcome sets the activity (connected, the failure, "Equipment ready" / "3 of 4 devices ready · camera failed", discovery found / none / cancelled / failed, frame received, slew finished / stopped, mount lost / reconnected); "Slewing" only while slewing. UI: muted and without "…" once nothing runs. Tests in `test_devices.py`. |
| Server link lost: screen still claimed "Equipment ready" (H) | Connection: "Last known: n of 4 ready" with a neutral ring, rows without state colours under "Last known · server link lost", Planetarium "No link". Observe prompt reworded to what is drawn ("last frame and readouts received, commands paused"). |
| Observe used the v1 connection for the mount and the camera (technical H) | `deviceUsable()` per device record: the Mount card, the status bar and `slewing` need the mount connected, capture / live / E / V the camera. Camera only: Mount "—", Tracking and Park disabled; mount only: capture disabled, E sends nothing, prompt "Camera not connected". `protocol.md` corrected. Tests in `model.test.ts`. |
| Restarted server's lines hidden after a long session (technical M) | Server `boot_id` in `/api/health`, `status` and LogPage; the client restarts its seq space on a new id; fallback heuristic (a lower, unheld seq with a later time) for servers without it. Tests in `log.test.ts`, `test_logs_activity.py`; checked live. |
| Log views not virtualised (technical M) | Windowed `LogView` (300 lines, 300 more at the top, the line under the eyes kept), version bumps once per frame, one filtered result per (version, filter). Full 5 000-line ring with about 60 lines arriving: 60 fps, longest frame gap 17 ms, about 2 700 DOM nodes (review: 6 fps, 160 000+ nodes). |
| Connect all left the devices "disconnected" during its address check (technical M) | The server claims every device first (`connecting`, `info: "queued"`): profile locked, events sent, Disconnect all and the row Cancel work from the first moment; queued devices released unopened. Tests: 4 in `test_devices.py`. |
| Exit criterion: Stellarium Start / Stop missing (technical M) | A19 implemented (`argos/server/stellarium.py`, port of `stellarium_worker.py`; hub, routes, `stellarium` event, 7 tests in `test_stellarium.py`) and the Planetarium card wired. |
| Status bar overflow on Observe with the link lost (M) | Priority folding (`crowded`), no reserved widths for "—", shorter "Server link lost". Log button inside the bar at 1440 and 1280. |
| Row action selected the row, brass over the error edge (M) | `Table`: clicks on controls never select; `selectable={false}` for the Devices table; danger edge outermost when a row is both. |
| Rail dots by colour only (M) | Shapes: filled ready, half running, ring needs attention; the word in the tooltip too. |
| Warning noise on a fresh config (M) | One "Setup" line (observer code and ASTAP) with one Settings link; the site only in the Instrument card; one Settings link style. |
| INFO tags in brass (M) | `--log-info: var(--text-muted)` (owner sign-off pending, see gaps). |
| Compact Segmented cramped (M) | Size `s`: segments sized to their words, 2 px gaps. |
| L stacked a second log on Connection (M) | Connection has no drawer: `L` (and its [log] switch, and the status-bar Log button there) widens its own log to every topic. |
| Discovery popover: three brass marks; "host : port" (M) | Radios in `--fg`; addresses "host:port". |
| Layout moved by discovery and Connect all (M) | The Search row is always there (hint before the first search; compact JobProgress); queued rows are one line. |
| Seestar red while the simulator is the link (M) | "not in use", idle. |
| Select brass ring after a mouse pick (M) | 2 px ring with a 2 px offset, border untouched, keyboard only. |
| Low ones | No roadmap words in reasons; busy Button keeps its label; profile details in mono; LogPanel title in the card style; Devices table aligned with the card; one "check now" glyph next to its caption; spinner stroke 1.5; start-up mark at a fixed height; job snapshot and config answers never overwrite newer events; publish order of log lines fixed under one lock; F1-F5 swallowed under an open menu or dialog. |

Verification of the round (server on port 8742 with temporary `--config-dir`, `--log-dir`
and `HOME`; vite on 5173; `~/.argos/config.json` untouched):

- `pytest tests/server` 295 passed, `tests/core` 389 passed and 45 skipped; ruff and black
  clean; `npm run check` 0 errors 0 warnings, `npm test` all passing (282 in `src/lib`),
  `npm run build` OK.
- 46 scripted checks in the running UI, all passing (each finding above, the final shots in
  the three themes at 1440 x 900 and Observatory at 1280 x 800, the server stopped and
  restarted under the page at both sizes). No request left the machine; the console held
  only the expected 502s (closed port, port in use) and the socket retries while the server
  was stopped.
- Night Red: 0 pixels where green or blue exceeds 72 % of red in the three Night Red shots
  (the highest ratio, 0.67, is the palette's own `--fg`).
- Discovery was answered by a local fake responder: it stopped at the broadcast stage, the
  LAN was never swept.
