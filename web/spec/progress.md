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

## Wave 2: Settings (2026-11-02)

Scope (README section 7, row W2): API rows A5, A6, A11, A67 (list only), A81-A84 and the
site-against-mount check of `web/lab/PROPOSAL.md` section 7 (server, `argos/server/protocol.md`
"API 2 routes, wave 2"); the shared components SettingsForm, FilePicker, Sheet, Undo toast,
SupportBundleDialog; the Settings screen with its nine categories, the Help menu items and
About; the W2 promotions of PROPOSAL section 6 and the BRAND / token amendments of its
sections 4 and 5 (owner decisions D1-D11, section 10).
Screenshots: `web/screenshots/2026-11-02_wave2-settings/` (51 shots with captions, taken
after the review round of section 6: Settings in several categories, the site mismatch, the
FilePicker, the palette, the support bundle, About, the Help menu, Connection and Observe,
key hints and the Undo toast; 1440 x 900 in the three themes and 1280 x 800 Observatory).

**Status: wave 2 is complete for its exit criterion, and its design and technical reviews
are applied (section 6, 2026-11-02).** Every key of 02 appendix A is
editable in the web UI or deliberately read-only with its reason (section 2 below, checked
in the running UI), and configuration changes sync live between two open clients (checked
with two browsers at once). The rows left partial wait for a later wave (the Settings sheets
over the image need the W4 Catalogue layers popover).

Verification (2026-11-02, server on port 8743 with a temporary `--config-dir`, `--log-dir`,
`HOME` and sessions folder; vite on 5174; `~/.argos/config.json` (last modified Sep 28) and
`~/Argos/sessions` untouched). Scripted checks with real input in headless Chrome, all
passing on the final code:

- Edit every category (23 checks): one value per category written through the UI and read
  back from `GET /api/config`; refusals shown with the server's words under the field and
  reverted by Esc (an observer code with "-" "contains characters that are not allowed", a
  relative ASTAP path "must be an absolute path", a sessions folder in `/System` "not
  writable", a bad Stellarium host "must be an IP address or a host name"); latitude 95
  refused, never clamped; comma decimal and grouped input ("58 000") accepted; "does not
  exist, it will be created" kept under the field; Gaia off makes its depth unavailable
  with the reason; Comfortable density sets `data-density` and `--row-h` 28 px.
- Two clients (9 checks, two browsers): a commit in one appears in the other without reload
  and its header says "Changed in another window: Site name"; a field holding a draft is not
  overwritten ("Changed elsewhere" + Reload, which then shows the other value); a switch
  follows; both converge on the server's values.
- Site against mount (15 checks): the simulator mount (its own site: APC Paris) slewed to
  RR Lyr, the Settings site set to Berkeley in the UI: the server says mismatch (84.0° between
  the directions, altitude +22.5°, driver site 8 941 km away); Settings shows both altitudes
  and azimuths, the difference against the 5° limit and when it was checked; the Connection
  Instrument card shows the warning line, the status bar "Site ≠ mount", the rail's Settings
  entry and the Observer & site category need attention, the server logged a WARN; Check now
  re-checks (trigger manual); the right site agrees (0.0° apart) and the marks go away.
- Support bundle (9 checks + 8 on the ZIP): opened from the Help menu, it proposes the
  temporary Desktop with the UTC time in the name, session metadata off and site coordinates
  out by default; the ZIP is written there; a second one with one session's metadata on the
  same name asks "Replace?" (409 file_exists) and replaces it. In the ZIP: README, manifest,
  `logs/argos.log`, `session/session.json`; no token, no home path, no Paris or Berkeley
  coordinates (the site-check lines read `<redacted-site>`), `ra`, `dec`, `observer`, `site`
  redacted in the session file, no FITS.
- Command palette (17 checks): Mod+K opens it (119 commands); "park" ranks Park first,
  marked CONFIRM; Enter opens the confirmation and the mount does not move; Esc cancels the
  confirmation only; a second Enter parks; Park then reads "the mount is parked already";
  "elevation" opens Settings › Observer & site with Elevation focused and the help column on
  its key; Density: Comfortable applies; "Crosshair" (a key of Observe) opens Observe and
  toggles it.
- FilePicker (6 checks): [browse] opens it with the server's places; a place navigates;
  Choose folder commits the key; `/etc` typed is refused with the server's words.
- Find a place (9 checks): the job's two browser requests answered by the test (Nominatim
  and Open-Meteo never contacted): empty query refused before any request; stage and Cancel
  while it runs; editing the query abandons it (DELETE of the job); the matches with their
  values; Use as default site writes the four keys in one commit; Undo restores the site.
- Restore defaults, Reset and Reset all layouts (9 checks): confirmation listing the changes,
  one commit, Undo; a field's Reset with Undo; Reset all layouts clears the layout keys and
  keeps the theme, Undo puts them back.
- Catalogue cache (5 checks): a temporary Gaia cache of 3 files is counted, Clear… asks
  first (what, where, "nothing is downloaded now"), the files are deleted, the row reads
  "empty" and a toast gives the count.
- Coverage walk (exit criterion): every category opened in the UI, Advanced disclosures
  expanded: 74 keys of the config meta, each editable or read-only with its reason, none
  without a home; 17 keys `omitted` by the server, each with its reason.
- No console error except the browser's own lines for the expected 400 / 403 / 404 / 409
  answers; no request left the machine in any check.
- Night Red: the 11 Night Red shots pass `scripts/audit-png.mjs` (rules A and B, 0 px).
  Brass (`--accent` px, Observatory 1440 x 900): Settings categories 291 (rail selection and
  mark), the palette 0, About 1 734 (the mark), the FilePicker 5 467 (its primary button and
  the list's focus ring), Connection 3 384 (the enabled Connect all), Observe 2 804 with the
  mount tracking (the Mount card's Slew primary and Tracking toggle; 847 in the design-system
  capture with the mount parked; not changed by this wave).
- `npm run check` 0 errors 0 warnings (499 files, `src/lab` included, unchanged), `npm test`
  495 passed (44 files), `npm run build` OK (548 kB JS, 177 kB gzip: over Vite's 500 kB
  warning), `pytest tests/server` 362 passed, `tests/core` 389 passed and 45 skipped, ruff and
  black clean.

### 1. Mapping rows closed by the wave

| Row | Qt element | Web | Status |
|---|---|---|---|
| M5 | Menu More: Documentation & website, Create local support bundle…, About & credits | Help menu of the rail footer: version and API line, Documentation & website (opens the browser, on request), Keyboard shortcuts (?), Command palette (⌘K), Create support bundle… (the shared dialog), About ARGOS (Settings › About, D14) | Done (Quit is desktop only, W8) |
| M6 | Menu View: sections F1-F5, Reset Window Layout | NavRail F1-F5 (W1); Panels popover Reset layout (W1, Observe); Settings › Appearance Reset all layouts (every section's panels, drawer, rail and card folds, levels strip; theme, density, rotation and settings stay), with Undo (D16) | Done |
| M14 | About dialog | Settings › About: the mark from `brand/argos-mark.svg` (never redrawn), ARGOS in Plex Sans 600, version · API · Python · platform, description, credits (the server's list from `GET /api/app/info` plus IBM Plex under the OFL, Svelte, uPlot; Tauri in the desktop app, Q-G15), copyright and licence, folders in use, Copy version info (no path, no address), Documentation & website, Source code | Done |
| M15 | Support bundle flow (5 modal boxes) | One dialog (Help menu, Privacy & diagnostics, palette): what the ZIP holds and what is replaced, crash reports in, site coordinates out, one session's metadata off by default (Q-G17) with a session chooser fed by `GET /api/sessions`; the server writes the ZIP at the chosen path (Desktop by default, UTC time in the name, FilePicker in save mode); existing file: inline "Replace?"; failure inline with the server's words; success toast "ARGOS did not upload it" | Done. "Reveal" (desktop) waits for W8; the browser-download path (`destination: null`, `GET /api/jobs/{id}/download`) is wired in `createSupportBundle` but the dialog always lets the local server write the file, so it was not exercised. |
| M16 | Theme / appearance | Settings › Appearance: theme (live), Comfortable density (owner D7: `data-density` on `<html>`, tokens only, applied before the first paint, per viewer), image rotation (per viewer), Reset all layouts; the rail footer's quick toggle (W1); theme and rotation seeded once from the Qt keys (Q-G6) | Done |
| M27 | `ConfigurationPage` | Settings screen: category list (208 px, `↑ ↓ Home End`, attention ring), filter over every category (`/`; label, help, key, unit, use; mirrored keys shown once), form (max 880 px) with a 44 px header ("Saved · Latitude" for 2 s, "Changed in another window: …"), Restore defaults… (Q-C6, confirmation + Undo), "About this setting" column at ≥ 1440 px (Q-C8: key, default, now, range, used by) | Done. The header shows "Saved" and remote changes; a refusal stays under its field only (02 2.4 also asks for it in the header). |
| M28 | Settings › Observatory | Observer & site: observer name, AAVSO code (upper-cased); default site (signed 5 decimals, comma or point decimal); the site-against-mount panel; Find a place (cancellable `site_search` job, matches as a radio list with their values, Use as default site = one commit, Undo); Saved sites table (Default chip, Set as default, Remove with Undo, Save current replaces a site of the same name) | Done. The real Nominatim / Open-Meteo path was never contacted (the UI was checked with the job answered by the test, the server with a fake HTTP getter). |
| M29 | Settings › Equipment · camera | Instrument: the profile as a read-only mirror with the server's lock reason and "Change on Connection" (D28); specs with ADC depth; Sensor limits as overrides with the profile's values as placeholders (Q-C1); calibration folder; Advanced: access-point address, ADC depth (read-only, shows what is in effect), the electron gain table editor; the two legacy Qt keys (read-only mirrors) in a closed "Qt app compatibility" disclosure | Done |
| M30 | Settings › Astrometry | Plate solving: ASTAP status from A81 (program, database, `-D` / `-d` flags; re-read after every change of the ASTAP keys, from any client), executable (FilePicker, executable mode), database folder, database set (unavailable while a folder is set, Q-C9), radius, downsample, scale hint, grid spacing; Advanced: the four live-solve keys | Done |
| M31 | Settings › Catalogues · data | Catalogues (bundled catalogue A84, budget, VSX, Gaia with the depth presets bound both ways, context layers, SIMBAD, NASA); Instrument (calibration folder); Data & storage (presets, the five caches); Privacy & diagnostics (diagnostic records) | Done |
| M32 | Settings › Files · application | Data & storage (sessions folder), Appearance (theme), Privacy & diagnostics (log level, applied live by the server), About; Language dropped (Q-G12) | Done |
| M33 | Cache clear `QMessageBox.question` | ConfirmDialog "Clear the … cache?" (what and where, "nothing is downloaded now"), Cancel / Clear cache (danger); `DELETE /api/caches/{kind}`; toast with the file count | Done (checked on a temporary Gaia cache of 3 files: counted, confirmed, deleted, the row reads "empty"; Clear… is unavailable with "the cache is empty" on an empty cache) |
| M34 | Settings file pickers (10 sites) | In-app FilePicker on every path key (folder, executable modes) and on the cache locations (a file cache keeps its file name: the folder is chosen, never a save dialog, 02 1.10 #7) | Done |
| M35 | `AstrometrySettingsDialog`, tab Plate solving | Settings › Plate solving | Partial: "also opened as a sheet from Observe / R2" needs the Catalogue layers popover (W4); the Sheet component is ready |
| M36 | Same dialog, tab Field catalogue + Save / Cancel | Settings › Catalogues (+ Photometry for the automatic comparison count); immediate apply | Partial: same sheet entry point (W4) |
| M37 | ASTAP binary picker | FilePicker, executable mode | Done |

API rows wired by the UI: A5 (dialog), A6 (Privacy › crash reports line), A11 (FilePicker),
A67 (support-bundle session chooser), A81 (Plate solving, the Connection Setup line), A82
(Find a place), A83 (caches table), A84 (bundled catalogue); the site check
(`status.site_check`, `site_check` events, `GET` / `POST /api/site/check`).

### 2. Exit criterion: every key of 02 appendix A and its web control

"Editable" = a working control that commits one `PATCH /api/config` (refusals in the
server's words); "read-only" = shown with the reason; "omitted" = not in the server's meta,
listed in `ConfigSnapshot.omitted` with the reason (`argos/server/config_meta.py` OMITTED).
Checked by walking every category in the running UI (section above, coverage walk).

| Key | Web control | Status |
|---|---|---|
| `alpaca.host` | Connection › Link "Seestar address" (W1); in the Settings filter: shown, "Set on the Connection screen (F1)" | Editable (Connection) |
| `alpaca.port` | Connection › Link "Alpaca port" | Editable (Connection) |
| `sessions_path` | Data & storage › Folders "Sessions folder" (FilePicker; "will be created" / "not writable") | Editable |
| `data_paths.sequence_presets_directory` | Data & storage › "Sequence presets" | Editable |
| `data_paths.camera_calibration_directory` | Instrument › "Photon-transfer calibrations" | Editable |
| `data_paths.object_catalogue_cache` | Data & storage › Catalogue caches "Target names cache": location (folder picker, file name kept), Reset, Clear… | Editable |
| `data_paths.exoplanet_cache` | same, "Transit ephemerides cache" | Editable |
| `data_paths.aavso_cache_directory` | same, "Variables cache" | Editable |
| `data_paths.gaia_cache_directory` | same, "Field stars cache" | Editable |
| `data_paths.field_catalogue_cache_directory` | same, "Field identities cache" | Editable |
| `observer.name` | Observer & site › "Observer name" | Editable; personal (no Reset, not restored) |
| `observer.obscode` | Observer & site › "AAVSO observer code" (upper-cased; letters and digits) | Editable; personal (no Reset, not restored) |
| `observer.latitude`, `.longitude`, `.elevation` | — | Omitted: legacy keys, migrated to `site.*` on load |
| `site.name`, `site.latitude`, `site.longitude`, `site.elevation` | Observer & site › Default site: Site name, then one Position row (+ site check, Find a place, Saved sites › Set as default) | Editable; personal (no Reset, not restored) |
| `site.favorites` | Observer & site › Saved sites table | Editable |
| `ui.log_level` | Privacy & diagnostics › "Log level" (applied live) | Editable |
| `ui.window_state`, `ui.window_geometry` | — | Omitted: dead defaults (Q-C7) |
| `ui.theme.preset` | Appearance › Qt app compatibility "Qt app theme"; the web theme is per viewer (Appearance › Theme, rail toggle), seeded once from it (Q-G6) | Editable |
| `ui.language` | — | Omitted: no translation (Q-G12) |
| `ui.display.rotation` | Appearance › Qt app compatibility "Qt app image rotation"; the web rotation is per viewer (Appearance › Image rotation, Observe levels strip), seeded once | Editable |
| `ui.shell.geometry`, `ui.shell.state`, `ui.shell.mode` | — | Omitted: Qt window state |
| `ui.imaging.layout`, `ui.sequencer.layout`, `ui.review.layout` | — | Omitted: Qt dock layouts |
| `hardware.profile` | Connection › Instrument "Telescope" (locked while equipment holds the link, D28); Settings › Instrument mirror | Editable (Connection); read-only in Settings with "Disconnect the equipment before changing the telescope…" / "Changed on the Connection screen…" |
| `hardware.overrides` (`full_well_adu`, `linearity_max_adu`) | Instrument › Sensor limits (empty = the profile's value, shown as the placeholder) | Editable |
| `hardware.overrides.ap_host` | Instrument › Advanced "Access-point address" | Editable |
| `hardware.overrides.adc_bits` | Instrument › Advanced "ADC depth" | Read-only: "The ADC depth is the sensor's, set by the telescope profile." (Q-C1) |
| `camera.adc_bits` | — | Omitted: deprecated, no reader (Q-C7) |
| `camera.full_well_adu`, `camera.linearity_max_adu` | Instrument › Qt app compatibility ("Qt app saturation", "Qt app linearity limit") | Read-only: they follow the overrides so the Qt app reads the same value (Q-C1) |
| `camera.egain_table` | Instrument › Advanced "Electron gain table" (add a gain / e⁻/ADU pair, remove with Undo) | Editable |
| `astrometry.astap_path` | Plate solving › "ASTAP executable" (FilePicker, executable; empty = auto-detect) | Editable |
| `astrometry.database` | Plate solving › "Database set" | Editable; unavailable while a database folder is set (Q-C9) |
| `astrometry.database_path` | Plate solving › "Star database folder" | Editable |
| `astrometry.downsample`, `.search_radius_deg`, `.use_scale_hint`, `.grid_spacing_arcmin` | Plate solving › Solving | Editable |
| `astrometry.live_search_radius_deg`, `.live_resolve_s`, `.live_resolve_arcmin`, `.live_timeout_s` | Plate solving › Advanced (Q-C4) | Editable |
| `catalog.mag_limit`, `.max_results`, `.include_suspected` | Catalogues › Variable stars · AAVSO VSX | Editable |
| `catalog.field_stars_enabled`, `.field_stars_mag_limit`, `.field_stars_detected_only` | Catalogues › Field stars · Gaia DR3 (+ depth presets) | Editable; depth and detected-only unavailable while Gaia is off |
| `catalog.field_stars_max_results` | — | Omitted: dead (Q-C7) |
| `catalog.identification_max_objects` | Catalogues › Identification budget (segmented 100 … 1 600) | Editable |
| `catalog.display_mag_limit` | Appearance › Observe display "Display depth" (the Observe overlay slider is W4) | Editable |
| `catalog.display_limit_version` | — | Omitted: internal migration marker |
| `catalog.show_essential_objects`, `.show_cached_exoplanets` | Catalogues › Context layers | Editable |
| `catalog.named_objects_enabled` | Catalogues › Named objects · SIMBAD | Editable |
| `catalog.named_objects_max_results` | — | Omitted: dead (Q-C7) |
| `catalog.named_objects_allow_network` | Catalogues (+ Privacy › Online services mirror) | Editable; unavailable while SIMBAD is off |
| `catalog.exoplanet_hosts_enabled` | Catalogues › Exoplanet hosts · NASA | Editable |
| `catalog.exoplanet_hosts_allow_network` | Catalogues (+ Privacy mirror) | Editable; unavailable while hosts are off |
| `photometry.aperture_fwhm_mult`, `.aperture_min_px`, `.annulus_in_px`, `.annulus_out_px` | Photometry › Apertures | Editable |
| `photometry.auto_comparisons`, `.comparison_min_snr`, `.comparison_max_delta_mag`, `.comparison_max_separation_arcmin` | Photometry › Comparison stars | Editable |
| `photometry.default_band` (a list of AAVSO codes), `.systematic_floor_mag` (empty = derived), `.track_apertures` | Photometry › Reports and errors | Editable |
| `photometry.read_noise_e`, `.min_comparisons`, `.comparison_validation_min_points`, `.comparison_validation_max_scatter_mag`, `.comparison_validation_max_formal_error_mag` | Photometry › Advanced (Q-C4) | Editable |
| `diagnostics.enabled` | Privacy & diagnostics › Local records | Editable |
| `diagnostics.local_opt_in_v1` | — | Omitted: internal marker, written by the server with `diagnostics.enabled` |
| `stellarium.host` | Connection › Planetarium "Host" (shown); Privacy & diagnostics › Network exposure (editable, with the server's warning for a non-loopback address, Q-C3) | Editable |
| `stellarium.port` | Connection › Planetarium "Port" | Editable (Connection) |
| `stellarium.online_target_lookup` | Connection › Planetarium checkbox (+ Privacy › Online services mirror) | Editable |
| `imaging.star_radius_px` (new, not in appendix A) | Appearance › Observe display "Star aperture" | Editable |

### 3. PROPOSAL section 6, W2 promotions

| Lab source | In `web/src/lib` | Status |
|---|---|---|
| three `format.ts` | `format/number.ts` (+ `time.ts`) | Done (design-system role); used by every screen (D5) |
| `research/tokens.ts`, `charts/core/palette.ts` | `charts/ink.ts` (+ `charts/text.ts`) | Done (design-system role) |
| `Ctl.svelte`, `Ring.svelte` | `components/Control.svelte`, `Ring.svelte`; `IconButton` / `Button` as thin wrappers | Done (components role) |
| `tip.ts`, `TipStatic.svelte` | `components/tooltip.ts` v2, `TooltipStatic.svelte` | Done (components role) |
| `hints.svelte.ts` | `app/keyhints.svelte.ts` | Done (components role) |
| `Chip.svelte` | `components/StatusBadge.svelte` (badge, hud, bar, alert; levels) | Done (components role); the status bar's "Site ≠ mount" uses the bar variant |
| `ScrubField`, `Stepper`, `Slider`, `values.ts` | `components/NumberField.svelte` v2, `Stepper`, `Slider`, `values.ts` | Done (components role); scrubbing by the label only (dial tape and Pointer Lock: W3) |
| `workspace/ui/Readouts.svelte` + density tokens | `components/Readouts.svelte`; Comfortable density in Appearance | Done; the component is promoted but no screen uses it yet (the Mount card keeps its own grid on `--readout`) |
| `CommandPalette.svelte`, `commandIndex.ts`, `model/commands.ts` | `shell/CommandPalette.svelte`, `shell/commandIndex.ts`, `shell/commands.ts` | Done (this role): the app's registry (new `canTrigger` / `trigger`), sections, Settings categories and every config key, the hardware actions with their confirmation and reasons, Appearance, Help; tighter ranking (scattered subsequences dropped); `palette.open` (Mod+K) is no longer `planned` |
| capture scripts, `audit-png.mjs`, `behave.mjs` | `web/scripts/audit-png.mjs` (CI gate, tests), `capture-lab.mjs` | Partial (design-system role): the lab capture scripts are wrapped, not merged into one shot format; `behave.mjs` keeps its hard-coded port |
| small changes | `Card` summary slot, canvas text helpers, W / Mod+K / Alt+1-4 in `keymap.ts` | Done |
| sections 4 and 5 | BRAND.md amendments, PROPOSAL tokens, D8 sizes | Done (design-system role). This wave changed the stacking tokens (`--z-modal` 100 under `--z-popover` 200 and `--z-tooltip` 300) so that a Select, menu or tooltip opened from a dialog or a sheet shows above it |

### 4. Fixed during the integration (found in the running UI)

- A Select (the support bundle's session chooser) opened behind its dialog: list boxes,
  menus, popovers and tooltips were stacked under the modal layer (`tokens.css`).
- Two places naming the same folder (the presets folder set to the Desktop) crashed the
  FilePicker (Svelte `each_key_duplicate`): places are now deduplicated (`filepicker.ts`,
  test).
- A visually hidden label inside the Settings form grew the document by 112 px, so a
  `scrollIntoView` scrolled the whole shell 32 px up: the form's scroller is now positioned.
- The unit of a number field ("× FWHM") overlapped the value: the field keeps room for the
  unit's length (`NumberField`).
- Tables ignored Comfortable density (`Table` set its own `--row-h`).
- Switch rows reserved an empty status line: their "Saved" now sits beside the label
  (`SettingField`), so a switch row is one line plus its help.
- The Connection Setup line said "ASTAP is not set" while ASTAP was found on PATH (A81 is
  now read at every connection and after a change of the ASTAP keys).
- Levels black / white values were not grouped (`1721` beside `1 662–2 008`).
- Info toasts spent brass; the Undo queue now shares the toasts' column (no overlap).
- Server (with tests and `protocol.md`): `KeyMeta.path_kind` is sent, so the picker opens in
  the mode the server validates (`exe`, `file`, `dir`); the observer-facing read-only reasons
  no longer name a route or a decision code; the two Qt-app appearance keys are labelled
  "Qt app theme" / "Qt app image rotation" (they sat beside the web's own Theme and Image
  rotation); the identification budget option reads "1 600" (U+202F, BRAND 5), not "1,600".

### 5. Known gaps and issues (before wave 3)

Updated after the review round (section 6). Closed by it: the transient site-check WARN while
a site is typed (the server now waits until the site is unchanged for 2 s), paths cut at the
end (middle cut), Restore defaults clearing the observer code and the site (personal keys),
the Observe brass with the mount tracking (2 804 -> 1 151 `--accent` px).

- **Settings sheets over the image** (D12; M35, M36): the Sheet component exists, the
  entry point (Catalogue layers popover) comes with W4.
- **Online services never contacted**: place search was checked with its job answered by the
  test and the server's fake HTTP getter; the real Nominatim / Open-Meteo requests, their
  timings and error texts are untested.
- **Real Seestar**: whether its Alpaca driver exposes `SiteLatitude` / `SiteLongitude` is not
  verified; the simulator does.
- **Observer & site at 1 280 x 800** with a mismatch shown scrolls about 90 px (fits at
  1 440 x 900, the reference of 02 2.4); Catalogues and Photometry scroll at both sizes, as
  02 2.4 allows. Only the site got a compound row; the Photometry apertures could take one
  too ("r 2.50× FWHM · floor 4.0 px · sky 8.0-12.0 px").
- **Settings header**: shows "Saved" and changes made elsewhere; a refusal stays under its
  field only (02 2.4 also asks for the header).
- **Comfortable density**: Mount readouts, card values, frame statistics, table rows and log
  lines follow it; the levels' number fields, the Devices table rows and `--readout-key`
  (no screen uses Readouts.svelte yet) do not.
- **Brass**: FilePicker 2 548 and support bundle 2 721 `--accent` px (their primary buttons
  and the first checkbox's focus ring), Connection 3 384 (the enabled Connect all); the
  mismatch adds 637 `--warning` px on Settings (bar, chip, rail and list marks), close to the
  review's 600 target.
- **Support bundle**: the browser-download path is implemented but not exercised; "Reveal"
  waits for the desktop app (W8). Redaction of free text is best effort (1-decimal and
  degrees-minutes-seconds writings are not recognised).
- **Documentation**: no local offline copy (Q-G8 asks for one).
- **Keyboard table** of README 3.10 not updated: ⌘K (palette) and `/` (Settings filter) are
  now active; Undo has no Mod+Z.
- **Bundle size**: 561 kB of JS (181 kB gzip), over Vite's 500 kB warning; Settings could be
  split into its own chunk.
- **Parsing**: "60,000" is read as 60 000 in a whole-number field and refused as ambiguous in
  a decimal one ("Write 60 000 or 60.000"); a French observer typing "2,500" for 2.5 in a
  decimal field gets that refusal too (by design: never a silent factor of 1 000).
- **WebKit** (the future Tauri webview) and screen readers untested; headless Chrome only.
- The status bar's "Site ≠ mount" item is a stand-in until the attention system (W6).

### 6. Review round (2026-11-02): what was fixed

Design review (22 findings) and technical review (11 findings), all applied; nothing
skipped. High first.

- **Command palette ran another command than the one highlighted** (high): the highlight,
  `aria-activedescendant`, hover and Enter now share one index in display order
  (`layoutGroups`, `shell/commands.ts`); the empty field opens on the first row that moves no
  hardware. Tests: `commands.test.ts` (highlight == executed for an empty field, a query,
  recent rows); live: 3 x ArrowDown highlights Review and Enter opens Review.
- **Reset moved the site to 0°, 0°** (high): the server's meta has `personal` (observer name
  and code, site name, latitude, longitude, elevation); those rows have no Reset and no
  "changed" mark, Restore defaults leaves them alone, the help column says "Default: None:
  your own value" (`test_personal_keys_are_the_observer_and_the_site`).
- **Commit model lost commits made while a value was in flight** (medium): one request at a
  time, the newer commit queued and sent after the answer, a draft typed meanwhile kept
  (`commit.svelte.ts`; the reviewer's three cases plus supersede and Esc in
  `commit.test.ts`).
- **"60,000" saved as 60** (medium): `parseNumber(text, { integer })` reads it as 60 000 in a
  whole-number field; a decimal field refuses it as ambiguous (`ambiguousComma`); Stepper
  parses as integers (`number.test.ts`; live: Saturation "60,000" saves 60 000).
- **Observer & site scrolled at 1 440 x 900** (medium): one Position row (latitude,
  longitude, elevation side by side, `SitePosition.svelte`), one line of help per row where the
  help column shows it in full, compact row padding, the mismatch verdict in one paragraph:
  773 / 773 px. Privacy at 1 280 x 800 fits too.
- **Forms read as a database dump** (medium): controls sized by content (numbers about 12 ch
  plus the unit, codes 12 ch, names 280 px, paths full width), no rule per row (rules between
  groups), Reset on row hover or focus (keyboard reachable), a small neutral dot after the
  label for "changed" instead of the left bar (also PrefRow).
- **One alert, four looks** (medium): the mismatch uses the upright Attention mark everywhere
  (category list, intro list via StatusBadge, rail Settings entry, Connection callout, status
  bar); the ring stays for info (no AAVSO code). The site panel lost its brass-looking
  `--warning` frame (3 101 -> 996 brass-family px on Settings).
- **Device and server words cut off** (medium): refusals, reasons and warnings wrap to three
  lines in NumberField, Stepper, CommitTextField and SettingField.
- **D5 grouping and range notation** (medium): NumberField groups by default (ports opt out),
  every numeric key groups from 1 000, saved-site elevations too; `formatRange` / `betweenText`
  give "−90° … +90°", "1 … 3 600 s"; refusals read "Latitude must be between −90° and +90°";
  ° ′ ″ sit against the number in values, ranges and unit slots; the Dec echo is signed.
- **Help leaked config keys, Qt clutter** (medium): help in the observer's words (no key, no
  JSON, no route: `test_no_observer_facing_text_names_an_api_route`), the read-only refusal
  reuses the reason; the Qt copies and the Qt theme / rotation in one closed "Qt app
  compatibility" disclosure; ADC depth reads "12 bit · from the telescope profile".
- **Comfortable density barely applied** (medium): new tokens `--readout-s` (13 / 16 px) and
  `--log-row-h` (20 / 24 px) for the Camera facts, the frame statistics and log lines (BRAND
  amended); the Appearance help says exactly what changes.
- **Slew always brass** (medium): primary only for a target farther than 0.01° from the
  pointing (Observe 2 804 -> 1 151 `--accent` px).
- **Paths cut at the end** (medium): `middleEllipsis` (`format/path.ts`, tested) through a
  `middlePath` action on path fields, the support bundle's Save to and the FilePicker's path;
  the full path in the token tooltip, raw on focus.
- **Key hints only on Observe** (medium): `KeyHint.svelte` caps on the rail entries, the Help
  button, the Settings filter; `KeyHintBanner.svelte` shows ⌘K and ? above the status bar.
- **FilePicker brass ring** (medium): no region ring; the active row carries the focus, a
  neutral edge when none is active (5 467 -> 2 548 px).
- **Undo toast over the row actions** (medium): on Settings the toasts' column sits at the
  bottom left of the form.
- Low: draft words by context ("Not saved · ↵ saves" in Settings, "Not sent · ↵ sends" on
  devices); site check alt / az with 2 decimals and the mount's site with 5; "ARGOS" in all
  copy; AAVSO band a list of AAVSO codes (server `options`); About actions equal secondary
  buttons and "macOS 26.5"; "Restore the Catalogues defaults?"; the palette's confirm button
  shows Enter as a key cap; the identification budget a segmented 100 … 1 600.
- Server, technical review (low): the site-check log never says "agrees" when the verdict is a
  mismatch through the driver site; numeric JSON coordinates are redacted in session files;
  a NUL byte in a path is 400, not 500; a folder destination is refused and ".zip" appended,
  never swapped (server and client); the accuracy claim reads 0.01° for coordinates of date,
  about 0.4° for J2000, with a 120-direction astropy sweep in the tests; a path typed in another
  letter case on macOS is respelled from the disk (`samefile`-checked, never widens the
  roots); cache Clear deletes only the hash-named files each cache writes (the field
  identities only in `simbad/` and `nasa/`); `compactCount`, `seconds` and grouping of
  exponent forms fixed. Also: the site check runs once the site is unchanged for 2 s.

Verification of the round (server on 8744 and vite on 5175 with temporary `--config-dir`,
`--log-dir`, `HOME`, `TMPDIR` and sessions folder; stopped afterwards; `~/.argos/config.json`
still last modified Sep 28, `~/Argos/sessions` untouched):

- `npm run check` 0 errors 0 warnings (506 files, `src/lab` compiles unchanged), `npm test`
  515 passed (45 files), `npm run build` OK; `pytest tests/server` 375 passed, `tests/core`
  389 passed and 45 skipped; ruff and black clean.
- Fix checks in headless Chrome (`check-fix.cjs`, 32 of 33 pass; the one failure is Observer
  & site at 1 280 x 800, section 5): palette highlight == Enter (empty field, arrows, hover),
  Park confirmation, no Reset on personal keys, every category's height, Restore defaults,
  the help column, "60,000" in both kinds of field, the range refusal, the path middle cut,
  key hints, the attention marks. The integration's sync (9/9), edit (23/23, adapted to the
  band list) and restore (9/9, new dialog title) checks pass again.
- 51 screenshots read; 9 Night Red shots pass `scripts/audit-png.mjs` (rules A and B, 0 px);
  no console error and no request off the machine in any capture.
