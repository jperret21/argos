# ARGOS web front-end (spike)

The first screen of the new ARGOS UI: **Observe** (imaging), wired to the headless
Python server. Svelte 5 (runes) + TypeScript + Vite, offline-first: fonts, icons and
every script are bundled; the only network traffic goes to the local ARGOS server
(REST under `/api`, live state on `WS /ws/events`, binary frames on `WS /ws/frames`,
contract v1 in `argos/server/protocol.md`).

The Tauri desktop shell is not part of this spike: the UI runs in a browser against
the server.

## Run it (development)

```sh
# terminal 1, repo root: the server, with the simulator and a fixed dev token
.venv/bin/python -m argos.server --simulator --dev-token dev        # port 8742

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
| `npm test` | vitest (pure modules, no browser) |
| `node scripts/screenshot.mjs …` | headless-Chrome screenshots, see below |

## The Observe screen

```
┌──────┬────────────────────────────────────────────────────────────┬───────────────┐
│ rail │ toolbar: [● Simulator] | capture live stop | zoom fit fill │               │
│      ├────────────────────────────────────────────────────────────┤ Connection ▸ │
│ F1…  │   16-bit image viewer (WebGL2), frame chips in the         │ Camera        │
│ F5   │   image's corner, crosshair, pan / zoom                    │ Mount         │
│      ├────────────────────────────────────────────────────────────┤               │
│      │   levels strip: histogram + B/M/W handles | levels | view  │               │
│      ├────────────────────────────────────────────────────────────┤               │
│      │   activity log drawer (optional)                           │               │
├──────┴────────────────────────────────────────────────────────────┴───────────────┤
│ status: connection · mount state RA Dec (abort) · cursor x y ADU · rate · latency · Log │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

- **Left rail**: the ARGOS lockup, then Connection, Observe, Plan, Review and Settings
  (F1 to F5, as in Qt). Only Observe is built; the others show a short statement of
  what they will hold. State dots: ready, running, needs attention.
- **Toolbar**: the first slot is a connection chip (state and device; click it to open
  the Connection card); routine tools are icon-only with a tooltip (label +
  shortcut); Stop keeps its label (BRAND.md section 7, inventory `display`). Connecting
  happens in the Connection card or the viewer's prompt, with the mode chosen there.
- **Viewer**: portrait Seestar frames are turned landscape by default ("auto", 90°
  clockwise, like the Qt viewer); rotation is display-only and the cursor readout
  stays in sensor pixels. Night Red draws the image as `v × --viewer-tint` (#d80000).
  `F` frames the whole image, `Shift+F` fills the viewer and crops the long sides
  (a "Fill · cropped" chip says so); the mode is remembered. The viewer is a tab stop:
  arrow keys pan it (Shift: 10× steps).
- **Levels strip** (H hides it), docked under the image and sized to the band a 16:9
  frame leaves there (`lib/imaging/layout.ts`), so the fitted image has no black bands:
  uPlot histogram on a log axis with **draggable black / midtones / white handles** on
  its own ADU axis, the three levels as numbers, transfer, display rotation and the
  frame statistics. With the rail closed it folds to one compact row.
- **Right rail** (P hides it): Connection (folds itself once connected, unfolds when
  the link or the equipment is lost; asks before disconnecting during live view or a
  slew), Camera (exposure, gain, progress, settings in use, sensor), Mount (RA / Dec /
  Alt / Az, tracking, park / unpark, GoTo accepting sexagesimal or decimal input; Abort
  is enabled only during a slew). Every card folds, remembered per viewer.
- **Exposure and gain** always show the settings in use (they follow the server). While
  live view runs, a change is committed on Enter, on blur or after a 600 ms pause, sent
  with `PATCH /api/camera/live`, and applies from the next frame: until then the card
  reads "Next frame: 2.0 s (now 1.0 s)" with a button to cancel, and the image chip
  "1.0 → 2.0 s".
- **Status bar**: connection (device in its tooltip), the mount's state and RA / Dec
  (during a slew, the angle to go and an abort button), cursor X / Y / ADU, rate and
  latency (shown only while frames flow), the log.
- **Stale states**: a frame that is not current gets a muted "Last frame · hh:mm:ss UTC"
  chip and a dashed edge; with the server link down, device badges read "No link",
  readouts grey out and hardware actions are refused.
- **Feedback**: API errors become a toast (bottom right, merged when repeated,
  dismissed after a few seconds) and a line in the activity log, which also shows the
  server's `/ws/events` log messages, including the last 200 sent before the page
  opened (repeats after a reconnection are dropped).

Keyboard (single keys never fire in a text field):

| Key | Action | Key | Action |
|---|---|---|---|
| E | one exposure | A | auto stretch on / off |
| V | live view on / off | Shift+A | reset stretch (linear, full range) |
| Esc | abort a slew (never an exposure) | H | levels strip |
| + / − | zoom in / out | X | crosshair |
| F | fit: whole frame | P | instrument rail |
| Shift+F | fill the viewer (crops) | F1…F5 | rail sections |
| 1 | actual pixels (1:1) | arrows | pan (viewer focused; Shift ×10) |

Tracking keeps no single key: the inventory proposes `T`, but starting or stopping the
sidereal drive moves the mount, which BRAND.md forbids for single-key shortcuts.

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
  lib/viewer/                      WebGL2 renderer + shaders, stretch (port of stretch.py),
                                   histogram binning (port of the Qt preview), rotation,
                                   level-handle maths, view maths (fit / fill),
                                   FitsViewer.svelte
  lib/components/                  Icon, IconButton, tooltip action, Card, StatusBadge,
                                   NumberField, TextField, Segmented
  lib/shell/                       NavRail, StatusBar, Toasts, LogDrawer, EmptySection
  lib/imaging/                     ImagingScreen, toolbar, the three cards, LevelsStrip,
                                   Histogram (with level handles), layout.ts (strip height)
scripts/screenshot.mjs             screenshots for reviews (puppeteer-core + system Chrome)
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
the image, levels strip height, the rail's cards). All options are documented at the
top of the file. It uses Google Chrome at the default macOS path, or `CHROME_PATH`.

## Known limits

- Only the Observe screen exists; Connection, Plan, Review and Settings are
  placeholders. No focuser, filter wheel, plate solving, catalogue overlays, star
  selection, photometry, sequences or FITS saving yet (not in API v1).
- Alpaca mode is wired but has only been exercised against a closed port (the error
  path); the server side was tested against fake devices, not a Seestar.
- Seestar frames are raw colour mosaics (`channels: 1`, `sensor.bayer` set): they are
  shown as a mono mosaic (no debayer) and the histogram pools the channels (the Qt
  dock draws R / G / B).
- Rendering was verified in headless Chrome (SwiftShader). WebKit, the future Tauri
  webview, is untested.
- Not ported from the Qt viewer: saturation overlay, loupe, false-colour palettes,
  region statistics, WCS grid.
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
