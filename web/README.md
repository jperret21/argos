# ARGOS web front-end

The new ARGOS UI, wired to the headless Python server: the shell (rail, status bar,
start-up screen, log, keyboard shortcuts, command palette), the **Connection** screen
(wave 1 of `spec/README.md` section 7), **Observe** (imaging) and **Settings** (wave 2). Svelte 5 (runes) + TypeScript +
Vite, offline-first: fonts, icons and every script are bundled; the only network
traffic goes to the local ARGOS server (REST under `/api`, live state on
`WS /ws/events`, binary frames on `WS /ws/frames`, contract API 2 in
`argos/server/protocol.md`). Progress against the specification: `spec/progress.md`.

The Tauri desktop shell is not part of this spike: the UI runs in a browser against
the server.

## Run it (development)

```sh
# terminal 1, repo root: the server, with the simulator and a fixed dev token.
# --config-dir keeps your real ~/.argos/config.json out of development runs.
.venv/bin/python -m argos.server --simulator --dev-token dev --config-dir /tmp/argos-dev   # port 8742

# terminal 2
cd web
npm install
npm run dev        # open http://localhost:5173/?api=http://127.0.0.1:8742&token=dev
```

- `?api=` and `?token=` select the server. Without them the UI falls back to
  `VITE_ARGOS_API` / `VITE_ARGOS_TOKEN`, then to `http://127.0.0.1:8742` with no
  token (every authenticated call then fails with "Token rejected").
- Without `--dev-token` the server prints a random token on stdout
  (`ARGOS_TOKEN=…`); pass it as `?token=`. `--dev-token dev` is guessable and the server
  says so on stderr: development only. The server also refuses requests whose `Host`
  is not a loopback name or whose `Origin` is foreign (DNS rebinding), so a web page
  cannot drive the mount even with a guessed token.
- A query `?api=` naming another machine is ignored unless `?token=` comes with it, so
  a crafted link cannot send a build's `VITE_ARGOS_TOKEN` elsewhere.
- `?perf` logs per-frame decode / upload / stats / draw timings in the console
  (upload and draw are then fenced with a 1-pixel readPixels: measurements only).
- The page reconnects by itself when the server restarts.

| Script | What it does |
|---|---|
| `npm run dev` | Vite dev server (port 5173) |
| `npm run build` | production bundle in `dist/` (relative paths, for the future Tauri shell) |
| `npm run check` | svelte-check (types + a11y); warnings fail |
| `npm test` | vitest (pure modules and `scripts/*.test.mjs`, no browser) |
| `npm run screenshot -- …` | headless-Chrome screenshots of the app (`scripts/screenshot.mjs`), see below |
| `npm run audit:night-red -- DIR_OR_PNGS` | **CI gate**: Night Red pixel audit of every `*night-red*.png` given (BRAND 4.3); exit 1 on a failure, 2 when no Night Red file was given |
| `npm run audit:brass -- PNGS` | brass pixel counts per token (BRAND 8 brass budget); Night Red shots get the Night Red audit instead |
| `npm run capture:lab -- LAB --out DIR` | design-lab captures (`workspace`, `charts`, `controls`) or behaviour checks (`behave`), then the Night Red audit of the shots |

## The shell (every section)

- **Start-up screen** (01 2.3.8): mark, wordmark, version and honest stages until
  `GET /api/health` answers and `/ws/events` sends its first `status`; a failure (server
  unreachable, token rejected, page refused) stays on screen with the exact cause,
  Copy details and Retry.
- **Rail**: Connection, Observe, Plan, Review, Settings (F1 to F5) with state marks
  whose shape says the state (filled = ready, half = running, ring = needs attention;
  the word is in the tooltip; Settings carries the upright attention mark, a bar over
  a dot, while the site is missing or disagrees with the mount, and the ring while the
  observer code is missing); footer: Help
  menu (version and API level, documentation, keyboard shortcuts, command palette,
  support bundle, About) and the theme button (click cycles Observatory, Charcoal,
  Night Red; right-click lists them).
- **Key hints**: hold `⌘` (`Ctrl`) alone and every control with a shortcut shows
  its neutral key cap where it is: toolbar buttons, the rail entries (F1-F5), the
  Help button (`?`), the Settings filter (`/`), and a chip above the status bar for
  the command palette (`⌘K`), which has no button.
- **Command palette** (`⌘K` / `Ctrl+K`, or the Help menu): one field over the
  sections, every Settings category and key (opens Settings at the field), every
  built shortcut of the registry (an Observe key opens Observe first), the actions
  that have no key on purpose and Appearance. Each row shows its key or why it cannot
  run, in the button's words. Hardware actions (Connect all, Disconnect all, Park,
  Unpark, Tracking) never run on Enter alone: Enter opens their confirmation in
  place, a second Enter confirms; Esc cancels it, then closes (and, as everywhere,
  aborts a slew). The highlighted row is always the row Enter runs (one index in
  display order, `layoutGroups` in `shell/commands.ts`); with an empty field it opens
  on the first row that moves no hardware.
- **Undo**: reversible changes (remove a saved site, reset a setting, restore a
  category's defaults, reset all layouts) apply at once and offer Undo for 6 s in
  the toasts' column (paused while pointed at or focused). On Settings that column
  sits at the bottom left of the form, clear of the row and table actions.
- **Status bar**: server link when it is down, the four device marks (shape = state;
  a device that is not connected opens the Connection screen), Seestar / Net
  reachability (three states each; the internet is never probed in the background; an
  unreachable Seestar that the simulator link does not use reads "not in use"),
  the mount's state and RA / Dec (from the mount's own record: with the camera alone
  they read "—"), "Site ≠ mount" while the site check disagrees (opens Settings ›
  Observer & site), run chip, activity text (the last action or its outcome; muted, and
  without a trailing "…", once nothing runs), Log with the count of unseen warnings
  and errors. Priority decides what folds: Rate / Latency first (at 1280 px, or while
  the server-link item or a slew's "to go + Abort" is shown); the Log button and the
  device cluster never hide.
- **Log** (`L`, every section): the one log store (server lines of API 2 with `seq`,
  source and topic, replayed on reconnection and completed from `GET /api/logs`; a
  restarted server, told by its `boot_id`, gets a marker line), level filter, search,
  copy, save, clear, follow / pause. The views are windowed (the newest 300 lines in
  the page, 300 more each time the top is reached) and the store notifies them once
  per animation frame, so a full 5 000-line log costs nothing while lines arrive. A
  view pauses only when the observer scrolls (wheel, touch, keys, scrollbar), never
  when a card above it grows. On Observe and the placeholders it is a drawer; on
  Connection, `L` widens the screen's own log to every topic instead (no second copy
  of the same lines).
- **Server link lost**: every record on screen is the last one received and says so
  ("Last known" on Connection, muted readouts, "Last frame" on the image, commands
  disabled), until the page reconnects by itself (or Retry server).
- **Keyboard**: one registry (`lib/app/keymap.ts`) feeds dispatch, tooltips,
  `aria-keyshortcuts` and the `?` sheet; Escape always aborts a slew (D21).

## The Connection screen

Toolbar: "n of 4 devices ready" (plus what a Connect all is doing: "checking the
address…", "connecting camera…"), [Connect all] (only what is not connected yet; it
reads "Equipment ready" when the four are) and [Disconnect all] (asks first only
while an exposure, live view or a slew runs; it also stops a Connect all from its
first moment, the server claims the devices at once). Left: Instrument (telescope
profile, locked while a device holds the link; specs; validated or not, with the
caveats; the site with its Settings link) and Link (Simulator | Seestar, address and
port saved on Enter or blur, a Search row that is always there so a Discover never
moves the cards, Discover as a cancellable server job with a choice when several
devices answer, Seestar and internet reachability with "check now" next to each,
server line, one Setup line while the observer code or ASTAP is missing). Right:
Devices (mount, camera, filter wheel, focuser: state, full error text, Connect /
Disconnect / Retry / Stop retrying / Cancel per row; "Queued" while waiting in a
Connect all; rows are not selectable, so a row action never paints the row) and
Planetarium (the Stellarium bridge: Start / Stop, listening state, clients, the last
GoTo with its outcome, the bind error in full; port and online lookup saved to the
config). Bottom: the log filtered on the topics connection, discovery and planetarium
(`L` or its [log] switch: every topic).

## The Settings screen (F5, `⌘,`)

Category list (208 px) | form (max 880 px) | "About this setting" (260 px, at 1440 px
and wider: key, default, range, where ARGOS uses it). Nine categories (D13): Observer
& site, Instrument, Plate solving, Catalogues, Photometry, Data & storage, Privacy &
diagnostics, Appearance, About. `↑ ↓` move in the list; `/` focuses the filter, which
searches every category at once (label, help, key, unit, use) and shows the matching
fields in place.

- **Generated from the server's config meta** (`GET /api/config`, A8): each key gets
  its control (checkbox, number with unit and range, segmented, token-drawn select,
  text, path with the in-app FilePicker over `GET /api/fs/list`), sized for what it
  holds (numbers about 12 characters plus the unit, codes 8-10, names about 280 px,
  paths the full width). One `PATCH` per commit (Enter or blur for text and numbers,
  at once for the others); a value typed while another is on its way waits for that
  answer and is then sent, so the server always ends with the last commit. A refusal
  shows the server's words under the field (up to three lines, never cut) and Esc
  reverts; warnings ("does not exist, it will be created") stay under it. Numbers
  accept a point or a comma decimal and spaces as grouping; "60,000" is 60 000 in a
  whole-number field and is refused as ambiguous in a decimal one; ranges read
  "−90° … +90°" and a refusal "Latitude must be between −90° and +90°". A key
  changed from its default has a small dot after its label and [Reset] (Undo) on
  hover or focus; the observer's own values (name, AAVSO code, the site: meta
  `personal`) have no Reset and are left alone by Restore defaults, so the site can
  never jump to 0°, 0°. Read-only keys show their reason (an empty override shows
  what is in effect: "12 bit · from the telescope profile"); dependent keys are
  unavailable with the reason (Gaia, SIMBAD, NASA, the ASTAP database set while a
  folder is set). Advanced keys sit under a disclosure; the keys only the Qt app
  reads sit in a closed "Qt app compatibility" disclosure at the end. Paths show the
  middle cut and the last segment whole while not focused. The help column shows the
  pointed key, else a summary of the category; where it is shown, each row keeps one
  line of help.
- **Live sync**: every client's commit arrives as a `config` event; a field follows
  it unless it holds a draft ("Changed elsewhere" with Reload); the header names a
  change made in another window ("Changed in another window: Site name").
- **Observer & site**: observer, AAVSO code, the default site (name, then latitude,
  longitude and elevation side by side in one Position row), and the **site against
  mount** check (server, protocol.md "Site check"; run once the site has stayed
  unchanged for 2 s): both altitudes and azimuths (2 decimals), the angle between
  the directions against the 5° limit, when and why it was checked, the mount's own
  site and its distance; a mismatch carries the Attention chip (StatusBadge level
  attention, one alert vocabulary) and a left warning bar with its consequence
  (airmass, BJD and FITS site would be wrong), and the same mark on the Connection
  Instrument card, in the status bar, in the category list and on the rail's Settings
  entry, plus a server WARN. Fits 1 440 × 900 without scrolling. Find a place (online only when you press Search: Nominatim and
  Open-Meteo, a cancellable server job; editing the query abandons it) and Saved
  sites (table, set as default, remove with Undo, save current).
- **Instrument**: the profile as a read-only mirror (chosen on Connection, D28),
  sensor limits as overrides with the profile's values as placeholders, the
  calibration folder, the access point, ADC depth and electron gain table (Advanced),
  the Qt copies of saturation and linearity (Qt app compatibility).
- **Plate solving**: ASTAP status (A81: program, star database, the `-D` / `-d`
  flags), re-read after every change of the ASTAP keys.
- **Catalogues**: the bundled catalogue (A84), the budget, one group per source, the
  Gaia depth presets bound both ways to the G limit.
- **Data & storage**: sessions and presets folders; the five catalogue caches (A83)
  with contents, location (FilePicker) and Clear… (confirmation, local).
- **Privacy & diagnostics**: online permissions (mirrors), the other network uses in
  words, diagnostic records, log level (applied live), log file, crash reports (A6),
  the support bundle, the Stellarium bridge host (network exposure, Q-C3).
- **Appearance**: theme, **density** (Compact or Comfortable: `data-density` on
  `<html>`, tokens only, applied before the first paint: Mount readouts 20 px, card
  values and frame statistics 16 px, rows 28 px, log lines 24 px), image rotation,
  Reset all layouts (Undo); the Observe display values (server); the Qt app's own
  theme and rotation in Qt app compatibility (this browser seeded its own from them
  once, Q-G6).
- **About**: the mark (generator output, never redrawn), versions, credits (the
  server's list plus IBM Plex, Svelte, uPlot), licence, folders, Copy version info,
  Documentation & website.
- **Support bundle** (Help menu, Privacy & diagnostics): the shared dialog (what the
  ZIP holds and what is replaced; session metadata off by default, Q-G17; site
  coordinates out by default); the server writes it at the chosen path (Desktop by
  default, UTC time in the name, shown with the middle cut so the file name stays
  whole) and an existing file asks "Replace?".

## The Observe screen

```
┌──────┬──────────────────────────────────────────────────────────────────────┬───────────────┐
│ rail │ [Disconnect all] Framing Focus (Field Run) │ open · Take shot ▾ Light · 2.0 s│               │
│      │   Live Stop · Autofocus ▾ · zoom · display · [3] … arrange panels    │ Camera        │
│ F1…  ├──────────────────────────────────────────────────────────────────────┤ Mount         │
│ F5   │   16-bit image viewer (WebGL2), HUD chips (state, #, exposure,       │ Focuser       │
│      │   filter, type, object, time, Saved), cursor X Y ADU on the image    │               │
│      ├──────────────────────────────────────────────────────────────────────┤               │
│      │   task band: Framing = levels + exposure check; Focus = V-curve +    │               │
│      │   HFD trend (H hides it)                                             │               │
│      ├──────────────────────────────────────────────────────────────────────┤               │
│      │   drawer (D): Conditions · Log                                       │               │
├──────┴──────────────────────────────────────────────────────────────────────┴───────────────┤
│ devices · Seestar / Net · Mount state Alt-Az|EQ RA Dec · run chip (LIVE, AF n/N) · Frame # file · HFD Stars · Log │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Task modes** (owner D1): Framing (Alt+1), Focus (Alt+2) and Field (Alt+3, wave 4); Run
  is listed, unavailable, and says which wave brings it. Each mode remembers its rail
  width, card states, band, drawer and catalogue layers (Framing and Focus default to the
  grid and the target set only) (Arrange, `arrange`, with Reset and Undo).
- **Toolbar**, built from data (`components/Toolbar`): the equipment button and the modes,
  then Open FITS (⌘O), **Take shot** (E; a split button whose face says the frame type and
  exposure it will use; its menu sets them, never shoots; the face reserves the width of
  its widest value, so the toolbar never reflows when the value changes), Live (V), Stop
  (unavailable while autofocus owns the camera: Stop AF returns the focuser to its start,
  the focuser's Halt stops it where it is), **Autofocus** (a split button: sweep range and
  positions; while it runs it is "Stop AF" with the sweep's ring; the count is in the
  Focus band and the status-bar chip), then zoom (the zoom % stays visible at 1 440) and
  display tools. When the window is narrow the low-priority tools go into a counted
  overflow menu; Take shot, Live and Stop never do. Holding ⌘ shows the key caps, the
  task modes included (Alt+1, Alt+2).
- **Viewer**: portrait Seestar frames are turned landscape by default ("auto", 90°
  clockwise, like the Qt viewer); rotation is display-only and the cursor readout stays in
  sensor pixels. Night Red draws the image as `v × --viewer-tint`. `F` frames the whole
  image, `Shift+F` fills the viewer and crops the long sides (a "Fill · cropped" chip says
  so). The band under the image takes exactly the space the fitted frame leaves (BRAND
  11.1) unless its edge is dragged; while a separator is dragged the image says what the
  layout costs.
- **Take shot saves a FITS** with exactly the metadata of the fixed Qt engine (server
  `capture.py`): settings frozen per frame, FILTER read back from the wheel, a Dark or Bias
  turns the wheel to Dark first (refused while the wheel turns elsewhere, said in words
  before and on press), a Light or Flat is refused while the wheel sits on Dark (the
  server leaves it there after darks), a frame exposed across a wheel move or an offset /
  binning change is never saved, the gain is sent before every exposure, pointing only
  from a live mount, the site only when set, QA values measured on the saved array.
  During live view it saves the frame in progress (the log says when its exposure or gain
  differ from the request). Each save is a toast, a log line and the status-bar Frame
  segment (file name).
- **Camera card**: exposure and gain within the driver's limits (one `PUT
  /api/camera/settings` per commit, never clamped, refusals under the field in the
  server's words), frame type, filter (manual activation, the requested slot spins, the
  wheel's real slot after a refusal; metadata only without a wheel; a turning wheel spins
  on its slot, no line is inserted), Sensor disclosure (offset, binning; refused while a
  Take shot waits), the sensor's °C and format, the settings of the frame in progress
  ("filter LP (turning)" while the wheel moves). Autofocus or a sequence owning the camera
  says so in one line. The exposure's progress is the toolbar ring and the HUD's.
- **Mount card**: RA / Dec / Alt / Az, tracking with its rate (as the driver lists them,
  read back), **Park by a 700 ms hold** (Enter opens the inline confirmation), the
  **Object** field (offline names while typing, Enter resolves; Slew sends the object
  with its name: the observation's name and target are set first), typed coordinates,
  Abort, the Stellarium target-name suggestion, and the **Jog** section (pad, rate,
  dead-man meter; J arms the arrow keys; the offset readout and scope follow the key
  words' frame: ΔRA / ΔDec on an equatorial mount, ΔAz / ΔAlt on alt-az, and the scope's
  scale grows ±2°, ±10°, ±45°). Slew is brass only while the fields hold a new target,
  never because a jog moved the mount away; Tracking is a neutral toggle. Offline name
  suggestions come in natural order (M 1, M 10, M 11 …).
- **Focuser card**: polled position on a two-scale gauge, taps queued during a move and
  sent as one, Go to bounded by MaxStep (refused in words), Autofocus / Stop AF (returns
  to the start; "Returned to" only once the focuser is read back there, else the server
  says where it is), Halt always available. While autofocus runs the card says in words
  what the focuser does; the numbers are the Focus band's. Autofocus is refused behind
  the Dark slot.
- **Focus band**: the V-curve ("this autofocus" while it runs, "last autofocus · HH:MM
  UTC" after), its hyperbola kept in every state (over every sample when the worker's
  few points give none, or the reason in words), the legend listing only what is drawn;
  HFD now, step or best, verified HFD; the HFD trend over min(30 min, the session).
- **Framing band**: the levels (handles carry only their letter, the fields hold the
  values; under them the share of pixels shown black and white)
  and the exposure check (the last measured peaks stay, at one emphasis, with "#34 · 1
  frame behind"; two or more clipped stars are one line).
- **Conditions** drawer tab: HFD, FWHM, stars, sky, peak, airmass, sensor and focuser per
  frame, up to three small plots on one UTC axis, sparklines with current values. An
  interval with no frame breaks every line and is a hatched period named by its cause
  ("autofocus 13:36–13:38", else "no frame"). The history survives a reload while frames
  arrive (live rows are held during the read and merged after it).
- **Field mode** (wave 4, `spec/progress.md` Wave 4): **Identify field** (S; ASTAP as a
  cancellable job, the same button cancels it) and **Keep identified automatically**; the
  HUD chip says the state in words ("Identified · 3.67″/px · PA −177.0° · Δtarget …",
  "tracking lost"), with the frame-centre RA / Dec, a N / E compass and an arcminute scale
  bar. The **overlay** (screen-space SVG) draws the catalogue layers (Gaia, VSX, SIMBAD,
  VSP, exoplanet hosts; one shape per layer, the Catalogue layers popover O is their
  legend), the RA / Dec grid (G) and the target set (circle target, square comparison,
  triangle check), moved frame by frame by the server's tracking; labels (N) avoid each
  other and the HUD. A **click** identifies the star (A49): the star card (identity, facts,
  role buttons) writes `targets/<object>.json` in the Qt format with one grouped Undo toast
  at the bottom left of the image; the selection is four brass corner brackets. The
  **Field band** lists the VSP comparison candidates (V, B−V, Δ(B−V), separation against
  the observer's limit, peak and SNR on the solved frame, Gaia sources in the aperture
  when the Gaia list can tell, VSX entries; the target and the rules in words on one note
  line), the ensemble, and virtual tables of the VSX variables and Gaia stars; a row picks
  the star on the image. The **Inspector** card shows the picked candidate with an
  aperture thumbnail. The Mount card's **Solved field** row offers Centre target and Sync
  (inline confirmation), refused for the solution of an opened file. Image tools: loupe
  (Z), region statistics (R) and the Statistics card (I), the context menu, CFA preview
  (Raw, R, G, B) and Fire / Ice palettes (OKLab lightness linear in the stretch; neutral
  only in Night Red).
- **Live photometry** (wave 5, `spec/progress.md` Wave 5): one point per field solution
  outside a sequence, measured by the server with the fixed Qt engine's code (apertures
  placed by core's tracker; a frame on which no star of the set is where the solution
  places it gets no point, with a warning). The **Photometry** card (the set with roles,
  the target's newest magnitude, the check's 15-point scatter and check − V, comparisons
  used / in the set, the geometry, the ensemble verdict, Recommend… with each action's
  effect in numbers) and the drawer tabs **Light curve** (one `LightCurvePlot`: target,
  check as check − catalogue V on a symmetric ±rung scale with its trailing ±1σ band,
  and from 300 px the target's ensemble zero point ± rms; flags by shape; the newest
  point ringed; Whole run / Following / Zoom kept with an "n newer" button; UTC / JD /
  BJD; Copy data as TSV), **Variables** (the field's VSX list, Set as target) and
  **Ensemble** (the leave-one-out report, the check's own row). The Field band says the
  live status.
- **Open FITS image** (⌘O from any section): the in-app file picker; raw 16-bit frames
  only, a calibrated or stacked file is refused in the server's words and the dialog
  stays open; live view stops first.
- **Planetarium card** (Connection): the same target-name suggestion as the Mount card.
- **Stale states**: a frame that is not current gets a muted "Last frame" chip and a
  dashed edge; with the server link down, device badges read "No link", readouts grey out
  and hardware actions are refused.
- **Feedback**: API errors become a toast (merged when repeated) and a line in the
  activity log, which also shows the server's log (the last 200 lines are replayed on
  every connection).

Keyboard (single keys never fire in a text field; a press on the image ends typing):

| Key | Action | Key | Action |
|---|---|---|---|
| E | Take shot (saved FITS) | A | auto stretch on / off |
| V | live view on / off | Shift+A | reset stretch (linear, full range) |
| Esc | abort a slew, a jog or a manual focuser move (never an exposure or the autofocus) | H | task band |
| + / − | zoom in / out | X | crosshair |
| F | fit: whole frame | P | instrument rail |
| Shift+F | fill the viewer (crops) | D | drawer (Conditions, Log) |
| 1 | actual pixels (1:1) | J | arm / disarm keyboard jogging |
| Alt+1 / Alt+2 | Framing / Focus | arrows | jog while armed or the pad has focus; else pan the viewer |
| ⌘O | Open FITS image | L | log drawer (any section) |
| Alt+3 | Field mode | S | identify the field (again: cancel) |
| G | coordinate grid | N | catalogue labels |
| O | Catalogue layers popover | Z | loupe |
| R | region statistics | I | Statistics card |

Tracking, autofocus and focuser steps keep no single key: they move hardware (BRAND 7);
the command palette (⌘K) has them, with a confirmation in place.

## Architecture

```
src/
  main.ts, App.svelte, app.css     entry, shell (rail | section | status bar), global base
  design/                          design system: tokens, icons, BRAND.md (design team)
  lib/config.ts                    API base + token resolution (query, env, default)
  lib/api/                         wire types, REST client, events (reactive), frames
  lib/app/state.svelte.ts          ArgosApp: one instance in Svelte context; server link,
                                   observer settings, display state, actions, toasts
  lib/app/                         shortcuts, theme + prefs (localStorage, try/catch),
                                   frame-rate meter, status wording
  lib/format/astro.ts              RA / Dec / Alt-Az formats and sexagesimal parsing
  lib/format/number.ts, time.ts    every number on screen: U+202F grouping from 1 000,
                                   U+2212 minus, U+00D7 factors, parseNumber (point or
                                   comma decimal); UTC, durations, Julian dates (no Intl)
  lib/charts/ink.ts, text.ts       tokens resolved for canvas / WebGL (color(srgb …),
                                   color-mix()); canvas labels that always set
                                   textAlign and textBaseline
  lib/viewer/                      WebGL2 renderer + shaders, stretch (port of stretch.py),
                                   histogram binning (port of the Qt preview), rotation,
                                   level-handle maths, view maths (fit / fill),
                                   FitsViewer.svelte
  lib/components/                  Icon, IconButton, tooltip action, Card, StatusBadge,
                                   NumberField, TextField, Segmented, Button, Checkbox,
                                   Select, Menu, Popover, Dialog, ConfirmDialog, Table,
                                   Drawer, Log*, JobProgress, PanelsPopover (gallery:
                                   /?gallery=1 in development)
  lib/app/                         … plus log, jobs, shortcuts + keymap, panels / layout,
                                   startup (pure models, tested)
  lib/connection/                  Connection screen: InstrumentCard, LinkCard,
                                   DevicesCard, PlanetariumCard, DeviceMark, model.ts
  lib/settings/                    Settings screen (wave 2): SettingsScreen, pages/ (one
                                   per category), SettingsBlock (SettingsForm bound to
                                   the app), SiteCheckPanel, PlaceSearch, SavedSites,
                                   EgainTable; categories.ts and sites.ts (pure, tested)
  lib/shell/                       NavRail (+ RailFooter, ShortcutSheet), StatusBar,
                                   StartupScreen, Toasts (+ the Undo queue), LogDrawer,
                                   EmptySection, CommandPalette (+ commands.ts,
                                   commandIndex.ts), SupportBundle
  lib/imaging/                     ImagingScreen, toolbar, the three cards, LevelsStrip,
                                   Histogram (with level handles), layout.ts (strip height)
scripts/screenshot.mjs             screenshots for reviews (puppeteer-core + system Chrome)
scripts/audit-png.mjs              Night Red and brass pixel audits (no dependency; CI gate)
scripts/capture-lab.mjs            one entry point for the design lab's captures + audit
```

- **State**: `ArgosApp` (`lib/app/state.svelte.ts`) holds everything the screen
  shares. Every hardware action goes through one runner that marks it busy, applies
  the REST answer immediately (the WebSocket echo follows) and turns a failure into a
  toast plus a log line. The last known server state is kept when the link drops.
- **Frames**: `decodeFrame()` is zero-copy (a `Uint16Array` view at `pixel_offset`);
  the raw samples go to an `R16UI` / `RGB16UI` texture. Stretch, rotation, tint and
  zoom are shader uniforms: a slider or a theme change never re-uploads the image.
- **Science ports, tested against Python**: auto-stretch (`stretch.ts`, byte-exact vs
  `apply_stretch`), histogram binning with the ADU quantization grid (`histogram.ts`,
  vs `quantization_step` / `_histogram_edges` + `numpy.histogram`), rotation
  (`rotation.ts`, vs `numpy.rot90(frame, -k)` and the Qt `_rot_pt` / `_unrot_pt`).
- **Formats** (BRAND.md section 5): RA `05h 35m 17.3s`, Dec `−05° 23′ 28″` (U+2212,
  primes), Alt / Az `41.27°`, all mono with tabular figures; rounding carries.
- **Styling**: tokens only (`var(--…)`), never a hex value in a component, so every
  theme holds, Night Red included (custom range inputs, segmented controls instead of
  native selects, tooltips drawn from tokens, no native `title` tooltips).
- **1:1** means one image pixel per *device* pixel (no resampling on HiDPI).
- **Overlay coordinates** follow numpy/photutils (pixel centres at integers) in
  sensor pixels; FitsViewer applies the display rotation for you.

## Screenshots (`scripts/screenshot.mjs`)

```sh
node scripts/screenshot.mjs --out /tmp/shots --themes observatory,charcoal,night-red --live
node scripts/screenshot.mjs --out /tmp/shots --themes charcoal --live \
     --slew "5.5881 -5.3911" --name slew
node scripts/screenshot.mjs --out /tmp/shots --live --pref argos.rail-open=false --name rail-closed
```

It talks to the server directly (connect the simulator, start live view, GoTo), sets
the theme and any `--pref KEY=JSON` (e.g. `--pref argos.rail-open=false`) in
localStorage before the page loads, waits until a *new* frame is on screen
(`[data-frame-seq]`), and writes one PNG per theme plus a JSON report of console
messages, any non-local request and the measured layout (black bands on each side of
the image, levels strip height, the rail's cards, the D8 frame sizes: toolbar, status
bar and right panel, and every element that scrolls, since only the log may). With
`--audit` each shot is also audited (below) and a failing Night Red shot makes it exit 1.
All options are documented at the top of the file. It uses Google Chrome at the default
macOS path, or `CHROME_PATH`.

## Pixel audits (`scripts/audit-png.mjs`, CI gate)

```sh
npm run screenshot -- --out /tmp/shots --themes observatory,charcoal,night-red --live --audit
npm run audit:night-red -- /tmp/shots          # every *night-red*.png in the folder
npm run audit:brass -- /tmp/shots/argos-observatory.png
npm run capture:lab -- controls --out /tmp/lab --only buttons-night-red
```

- **Night Red** (BRAND 4.3, MUST): rule A, no pixel with G > R or B > R; rule B, no
  pixel with max(G, B) > 8 and max(G, B) > 0.68 × R, allowing ±0.5 per channel for 8-bit
  rounding (anti-aliased `--fg` edges over black). Audit the PNG as captured: a resampled
  copy (a 2x shot scaled down) creates green above red on near-black edges.
- **Brass** (BRAND 8): pixels within RGB distance 28 of the theme's `--accent`,
  `--accent-hover`, `--warning` and `--role-target`. Anti-aliased edges are not counted,
  so compare screens with the same method only (the counts in `web/lab/PROPOSAL.md` 2.4
  are reproduced exactly).
- Dependency-free (a PNG decoder on `node:zlib`), tested in `scripts/audit-png.test.mjs`.
  `web/lab/synthesis/audit-png.mjs` forwards to it, so the lab's command still works.

## Known limits

- Connection, Observe (Framing, Focus, Field) and Settings exist; Plan and Review are
  placeholders (waves 6 and 7). Live photometry runs outside a sequence; sequences, the
  Run band and the server's per-sub measurement come with wave 6. What is done and what
  is missing, row by row: `spec/progress.md`.
- Alpaca mode is wired but has only been exercised against a closed port (the error
  path); the server side was tested against fake devices, not a Seestar.
- Seestar frames are raw colour mosaics (`channels: 1`, `sensor.bayer` set): they are
  shown as a mono mosaic (no debayer) and the histogram pools the channels (the Qt
  dock draws R / G / B).
- Rendering was verified in headless Chrome (SwiftShader). WebKit, the future Tauri
  webview, is untested.
- Settings › Observer & site fits 1 440 × 900 but scrolls about 90 px at 1 280 × 800 with
  a site mismatch shown; Catalogues and Photometry scroll at both sizes (allowed by 02
  section 2.4).
- Simulator frames cannot be plate-solved: the field and its tracking were exercised on
  copies of real Seestar raw frames opened through Open FITS (the server's tests drive
  the frame-to-frame tracking).
- Statistics for the stretch run on the main thread (about 2 ms for 2 Mpx); 4K frames
  may want a Web Worker.
- The status bar latency compares the frame's server timestamp (end of exposure) with
  the browser clock: valid because both run on the same machine, as they will under
  the Tauri shell. Frames older than max(5 s, 3 exposures), such as the frame the
  server replays to a new socket, are not counted.
- `npm audit` reports two low-severity advisories in dev dependencies
  (`deepmerge` via `@sveltejs/vite-plugin-svelte`), with no fix available.
- Histogram binning copies the Qt preview exactly, including its one artefact: for
  integer data without a quantization grid and a bin width under about 1.5 ADU (short,
  low-noise exposures), some bins hold no integer and show as gaps. Fixing it means
  changing `argos/core/imaging/stretch.py` too, so both UIs stay identical.
- A token given as `?token=` stays in the address bar and the history; under the
  Tauri shell the token will come from the sidecar instead of the URL.
