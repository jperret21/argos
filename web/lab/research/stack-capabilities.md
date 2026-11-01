# What our stack can do for the ARGOS UI: a verified catalogue

Technology scouting for the design team, 2026-11-01. Audience: the owner, the design team,
the front-end team building the waves. Status: **research with live proofs**. Seven demos
run in `web/lab/research.html` (synthetic data generated in the browser, no server); every
number below was measured in the engine named next to it, on the machine described in
section 0.2, unless the line says "documented" (read from a source, cited) or "assumption".

The question: what do Svelte 5.57, uPlot 1.6.32, Canvas 2D / WebGL2, workers and current
CSS / DOM give us for an interface that is beautiful, ergonomic, flexible and still a
calm scientific instrument (BRAND 1-2), and how much of it works in the engines Tauri v2
actually embeds: **WebKit** (WKWebView on macOS, WebKitGTK on Linux) and **Chromium**
(WebView2 on Windows, Chrome during development)?

Files of this study (all under `web/`):

| Path | What |
|---|---|
| `lab/research.html` | Lab page (Vite dev: `/lab/research.html?demo=curve|frame|motion|space|popover|table|support&theme=observatory|charcoal|night-red&motion=reduced`). Not part of the app build. |
| `src/lab/research/` | The demos (Svelte 5 + TS). `curve/` light-curve wall and its uPlot plugins, `frame/` 2 Mpx pipeline (worker, WebGL2, LUTs, gestures, sparklines), `motion/`, `space/` (splitters, container-query cards), `popover/`, `table/` (virtual table), `support/` (feature probes, benchmarks, recorded runs), `tokens.ts` (token resolution for canvas), `env.svelte.ts` (theme / motion / engine). Unit tests: `curve/band.test.ts`, `frame/lut.test.ts`, `frame/stats.test.ts`, `table/virtual.test.ts` (15 tests). |
| `lab/research/demos/capture.mjs` | Screenshots in headless Chrome + the Night Red pixel audit. |
| `lab/research/demos/webkit-probe.swift` | Opens a page in a real WKWebView, runs JS, saves a PNG (how the WebKit column was measured). |
| `screenshots/2026-11-01_lab-research/` | 36 screenshots with captions (28 Chromium, 8 WKWebView). |
| `lab/research/functional-spaces.md` | The UX study of the same day (not mine); several proposals there (Watch view, attention, keep-awake, hold-to-confirm, task band) are served by techniques below and are cross-referenced as "FS Pn". |

---

## 0. The catalogue in one page

### 0.1 Recommendations

Status: **verified** = demonstrated in the lab and measured in Chromium 156 and WebKit
(WKWebView, macOS 26.5); **probed** = feature detection in both engines, no demo;
**documented** = read from the cited source only. WebKitGTK is never "verified": no Linux
machine was available (its column is read from WebKit's per-branch feature flags).

| # | Technique | What it gives ARGOS | Status | WebKit (mac) | WebKitGTK | Fallback |
|---|---|---|---|---|---|---|
| T1 | Big data outside the reactive graph (typed-array columns, `$state.raw`, a version counter) | Live curves of thousands of points, frame stats, 10 000-row tables without proxy cost | verified | yes | yes (language feature) | none needed |
| T2 | uPlot light-curve plugins: shape-coded markers + error bars in one Path2D per kind, culled and clipped | BRAND 10 markers (circle / square / triangle) at any point count | verified | yes | untested | none |
| T3 | uPlot native bands for error / scatter envelopes (trailing window) | Check-star stability band that widens in a cloud passage; ensemble ± sigma; fit ± error | verified | yes | untested | draw-hook polygon |
| T4 | Cursor sync + linked x zoom + "new data never resets a manual zoom" | Plot wall of R1, Observe drawer Light curve (D25), spec 3.13 | verified | yes | untested | none |
| T5 | Annotations with HTML handles over uPlot (draw hook + `posToVal` + pointer capture + slider semantics) | HFD / sky quality threshold that flags frames (FS finding 2: a 40-minute focus loss went unnoticed), levels on a histogram, time markers | verified | yes | untested | keyboard only |
| T6 | Worker statistics with zero-copy transfer + WebGL2 R16UI upload | A 2 Mpx frame per second with the main thread busy about 2-3 ms per frame | verified | yes | untested | none needed |
| T7 | Perceptual false colour: OKLCH LUTs computed in 30 lines | Fire / Ice palettes whose lightness equals the stretched value (a rainbow lies) | verified | yes | yes (math) | none |
| T8 | svelte/motion `Spring` and `Tween`, `animate:flip`, with the "values jump, only orientation moves" rule | Star card that docks to a corner; ghost of previous levels; ensemble re-ranking you can follow | verified | yes | untested | instant swap (reduced motion) |
| T9 | Attachments (`{@attach}`) for gestures: splitter, viewer pan / zoom / pinch / long-press, value handle | One reusable, testable gesture layer instead of per-component listeners | verified | yes | untested | none |
| T10 | Container queries + subgrid + `:has()` | One card component reflows from rail to drawer to Watch view; aligned forms; validation styling without script | verified | yes | yes (2.48+: documented) | none needed |
| T11 | Popover API + CSS anchor positioning + `@starting-style` | Toolbar popovers, tooltips, menus with no placement script, top layer, light dismiss | verified | yes, **only for an app linked on the macOS 14+ SDK** | anchor 2.50+ | `lib/components/position.ts` (demonstrated) |
| T12 | Virtual table (row windowing) + CSS Custom Highlight API | Frames, Gaia lists, logs at night scale; filter matches painted without DOM edits | verified | yes | untested | `<mark>` split |
| T13 | Token-drawn controls for anything native (checkbox, range, select, context menu, scrollbar) | Night Red contract: a native checkbox drew grey even with `accent-color` (measured) | verified | yes | `scrollbar-color` 2.52+ | `::-webkit-scrollbar` |
| T14 | Night Red pixel audit in CI (capture + per-pixel red test) | Turns BRAND 4.3 into a test | verified | n/a | n/a | n/a |
| T15 | Screen Wake Lock | Keep the display on during a run (FS finding 10, P6) | probed (granted in both) | yes | untested | Tauri-side power assertion (documented only) |
| T16 | View Transitions (same document) | 180 ms cross-fade between sections and task modes (FS P1) | probed | yes | untested | instant |
| T17 | `field-sizing`, `text-box-trim`, `text-wrap: pretty`, `scrollbar-gutter`, `:user-invalid`, `@property`, `linear()` | Small polish: growing inputs, exact label centring, no layout jump | probed | yes (26.2 for field-sizing, scrollbar-color) | mostly 2.50-2.52 | ignore when missing |
| T18 | Tauri v2 window features | Custom title bar, second window for the plot wall or Watch, global abort shortcut | documented | n/a | n/a | n/a |

**Rejected or deferred**, with the reason: gradients and glow under curves (BRAND 2,
although Canvas makes them trivial); vibrancy / translucent windows (BRAND 9 and Night Red:
the desktop behind would bleed non-red light); WebGPU (off by default in WebKitGTK, WebGL2
covers the viewer); Canvas 2D `filter` (off in every WebKit); `requestIdleCallback` and
`scheduler.yield()` (absent in WebKit); `SharedArrayBuffer` (needs cross-origin isolation;
transfer is enough); `popover="hint"`, `dialog closedby`, `CloseWatcher`, `overlay`,
`interpolate-size` (absent in WebKit 26.5); any new npm dependency (none was needed, section 13).

### 0.2 Method and limits

- Machine: Apple M2 Pro, macOS 26.5 (25F71), display at 2x. Engines: headless Chrome 156
  through `puppeteer-core`, run on the **Metal GPU** (`--use-angle=metal`; the default
  headless SwiftShader renders WebGL on the CPU and gave pessimistic GPU timings in a first
  pass); **WKWebView** of macOS 26.5 (WebKit 605.1.15, the engine a Tauri app gets on that
  macOS) driven by `demos/webkit-probe.swift` in an on-screen, transparent, click-through
  window, with WebKit's occlusion throttling switched off so `requestAnimationFrame` and
  timers run at full rate.
- **SDK matters in WKWebView.** The probe was built with the Command Line Tools (macOS 13.3
  SDK) and run twice: as built, and re-stamped for the macOS 26 SDK (`vtool
  -set-build-version macos 13.0 26.0`), which is what a Tauri app built with a current
  Xcode gets. Of 66 probes **only one differs: the Popover API is off for the 13.3-SDK
  binary** (WebKit gates it on the SDK the app was linked with). Consequence: build the
  macOS app with a current Xcode / SDK, and keep the JS fallback anyway.
- Recorded runs: `src/lab/research/support/recorded.json` (probes and benchmarks of
  Chromium, WebKit SDK 26, WebKit SDK 13.3). The Support demo shows them beside a live run
  in whatever engine opens the page: **open `lab/research.html?demo=support` in a Tauri dev
  build on Linux to fill the WebKitGTK column** (and on Windows for WebView2).
- WebKit clamps `performance.now()` to 1 ms: its sub-millisecond timings read 0-3 ms and
  are only upper bounds. Benchmarks are medians of 5; they compare approaches inside one
  engine, not engines with each other.
- WebKitGTK statuses come from WebKit's `Source/WTF/Scripts/Preferences/UnifiedWebPreferences.yaml`
  on the branches `webkitglib/2.48`, `2.50`, `2.52`, `2.54` [S3]: a key `status: stable`
  with `default: true` is on in every port. Checked on those branches for anchor
  positioning, `field-sizing`, `scrollbar-color`, `CloseWatcher`, `command` / `commandfor`,
  Canvas filters, `popover="hint"`, `requestIdleCallback`, WebGPU; the others are "not
  flag-gated, follows WebCore" and untested.
- Which WebKitGTK will users have? Debian 13 "trixie" ships WebKitGTK through security
  updates: 2.52.6 (DSA-6463-1) and 2.54.0 (DSA-6534-2, October 2026) [S4]; Ubuntu LTS
  follows the same upstream stable series (assumption, not checked). Plan for **2.50 as the
  floor** (anchor positioning stable) and treat everything newer as progressive.
- Night Red audit: every Night Red screenshot is decoded and each pixel tested; a pixel
  "emits non-red light" when `max(G, B) > 8` and `max(G, B) > 0.68 × R` (0.68 is just above
  the greenest Night Red token, `--fg` `#d88f8f`, G/R 0.66). Result on the final set: 0
  offending pixels in 9 Chromium and 3 WebKit Night Red shots (the first pass found 165, a
  native checkbox, fixed with T13).
- Not tested: WebKitGTK, WebView2, real touch screens and trackpad pinch on hardware (the
  gesture code handles both; only wheel zoom and mouse drag were exercised), screen readers,
  the server's real frame format (the frame demo synthesises frames in a worker).

---

## 1. Engines Tauri v2 gives us (baseline)

| Platform | Engine | Version control | Practical consequence |
|---|---|---|---|
| macOS | WKWebView = the system's Safari engine (WebKit 26.x on macOS 26) | Follows the OS; features also gated by the **SDK the app links against** | Build with a current Xcode; on macOS 14 / 15 the engine is whatever Safari version is installed (Safari 26.2 ships for macOS Sonoma and Sequoia too [S2]). Anchor positioning and scroll-driven animations need Safari 26.0; `field-sizing`, `scrollbar-color`, `command` need 26.2 [S1, S2]. |
| Linux | WebKitGTK (webkit2gtk-4.1) from the distribution | Distribution security updates | Debian trixie: 2.52 / 2.54 in 2026 [S4]. Floor 2.50. Features flagged "preview" or "testable" are off even when the code exists. |
| Windows | WebView2 (evergreen Chromium) | Auto-updated by Microsoft | Same features as Chrome; the most capable engine of the three. |

Design rule that follows: **write for WebKit, enhance for Chromium.** Every technique in
this file either works in WebKit 26.x or has a fallback that renders the same (the popover
demo proves it with three paths).

---

## 2. Svelte 5 (runes)

### 2.1 Large data: keep it out of the deep proxy (T1, verified)

`$state` wraps arrays and objects in a deep proxy: every read goes through a trap. For
plots and frames this is pure cost. Measured (`support/bench.svelte.ts`, median of 5):

| Operation | Chromium 156 | WebKit 26.5 |
|---|---|---|
| Read 100 000 numbers × 5 through a `$state` proxy | 276.5 ms | 190 ms |
| Same, plain array | 0.5 ms | 2 ms |
| uPlot draw of 10 000 points read from `$state` arrays | 11.6 ms | 10 ms |
| Same from `$state.raw` arrays | 2.6 ms | 3 ms |

Pattern used in the light-curve demo (`curve/CurveWall.svelte`): the columns are
`Float64Array`s grown by doubling, **not reactive at all**; a small `$state` counter tells
the UI how many points exist; uPlot gets `subarray` views (no copy).

```ts
let cols = emptyColumns(1024);           // Float64Array columns, plain `let`
let count = $state(0);                   // the only reactive bit
function tick(p: CurvePoint) {
  cols = appendPoint(cols, p);           // amortised O(1), realloc on doubling
  for (const [id, u] of plots) u.setData(dataFor(id), !manualZoom);
  count = cols.length;                   // header readouts re-derive from this
}
```

Use `$state.raw` for immutable records replaced as a whole (the 10 000 frame rows of the
table, a frame's statistics object): reassign, never mutate. Rule for the app: **anything
above a few hundred elements that is drawn, not edited, is `$state.raw` or not state.**

### 2.2 Transitions, `animate:flip` (T8, verified)

`animate:flip` on a keyed `{#each}` moves rows to their new place: in the ensemble ranking
(motion demo, panel 3) a comparison star that changes rank travels 260 ms so the eye can
follow it, while the RMS value inside it is already the new one. `out:fade` (120 ms) when a
star is removed from the ensemble. Durations go through one helper that returns 0 under
reduced motion:

```svelte
{#each comps as c, i (c.id)}
  <li animate:flip={{ duration: dur(260) }} out:fade={{ duration: dur(120) }}>…</li>
{/each}
```

Use in ARGOS: ensemble re-ranking (Review, Observe Ensemble card), the run's step list when
a step completes (Plan), toasts. Never on a table that the observer is reading row by row
while it updates at 1 Hz (the Frames table appends, it does not re-sort live).

### 2.3 `svelte/motion`: `Spring` and `Tween` (T8, verified)

Available since Svelte 5.8 (classes; the old stores are deprecated) [S5]. Two uses passed
the "does motion lie?" test in the demo, one was rejected:

- **Star card on a spring** (panel 1): while dragged the card is exactly under the pointer
  (`card.set(p, { instant: true })`), on release it settles into the nearest corner
  (stiffness 0.16, damping 0.72), never over the image centre. Keyboard: arrows move it
  between corners. Use: the star Inspector card (FS P5), the levels popover, any floating
  panel that docks.
- **Ghost of the previous value** (panel 2): after Auto stretch the B / W handles and their
  numbers jump to the new levels at once; a dashed ghost of the old levels fades out over
  900 ms (`Tween` on opacity). Orientation without delaying the truth.
- **Rejected: springing the handles themselves** (a switch in the demo shows it): the handle
  lags behind its number for about half a second, so the picture and the value disagree.
  Data and anything that encodes data never animate (BRAND 9).

```ts
const card = new Spring({ x: 12, y: 240 }, { stiffness: 0.16, damping: 0.72 });
card.set(cornerPos(corner), { instant: reducedMotion() });
// in markup: style:transform="translate({card.current.x}px, {card.current.y}px)"
```

Reduced motion: `prefersReducedMotion` from `svelte/motion` (5.7+) or `MediaQuery` from
`svelte/reactivity` (used in `env.svelte.ts`, which also honours the lab's override);
every `set` passes `instant: reduced`, every duration becomes 0. The tokens already zero
`--duration-*` under the media query (tokens.css), so CSS transitions follow for free.

### 2.4 Attachments for pointer gestures (T9, verified)

`{@attach fn}` (Svelte 5.29+) runs `fn(element)` on mount and its returned cleanup on
destroy; unlike actions it re-runs when the reactive values it reads change, works on
components through spread, and `fromAction` converts old actions [S6]. Three attachments
in the lab, each under 160 lines and framework-free inside:

| Attachment | File | Gestures |
|---|---|---|
| `splitter({ axis, get, set, min, max, reset, snaps, invert })` | `space/splitter.ts` | Drag with pointer capture, snaps at 8 px from a detent (420 / 500 / 580 px), WAI-ARIA window-splitter keys (arrows 8 px, Shift 40 px, Home / End, Enter reset), double-click reset |
| `gestures({ pan, zoom, fit, menu, hover })` | `frame/gestures.ts` | Drag pan (capture), wheel and trackpad pinch zoom about the pointer, two-finger touch pinch, double-click fit, long-press (touch, pen) and right-click menu |
| `valueHandle({ toValue, get, set, step, min, max })` | `curve/handle.ts` | Vertical drag of an annotation line with capture, `role="slider"` keys |

```svelte
<div class="viewer" {@attach gestures({ pan, zoom, fit: fitView, menu: openMenu })}></div>
```

### 2.5 Snippets for compound components

The virtual table (`table/VirtualTableDemo.svelte`) takes one snippet per column for its
cells, so one table component renders frames, comparison stars or Gaia lists with their
own formatting while keeping keyboard, sorting and windowing in one place. Same pattern for
the app's Card (header actions snippet) and for the plot facets (a header snippet with the
role glyph, title and live readout). No new technique to verify: snippets are the
documented Svelte 5 replacement for slots; the point is to **design compound components
around snippets** (Table + columns, Card + header / actions, Facet + header) rather than
growing prop lists.

---

## 3. uPlot 1.6.32

uPlot draws a 2D canvas from column arrays and gives hooks at every stage (`init`,
`setData`, `setScale`, `setCursor`, `setSelect`, `drawClear`, `drawAxes`, `drawSeries`,
`draw`, `destroy`). It has no opinion on styling, which suits BRAND 10: every visual below
is a token. Measured draw times (setData to the end of the `draw` hook, with the markers
plugin and error bars):

| Points | Chromium 156 | WebKit 26.5 |
|---|---|---|
| 1 000 | 0.5 ms | ≤ 1 ms |
| 10 000 | 3.6 ms | 2 ms |
| 100 000 | 29.4 ms | 25 ms |

At the real cadence (about one frame a minute, FS finding 1) a night is 600-700 points per
series: uPlot is never the bottleneck. Three facets of a 3 600-point night redraw in about
28-35 ms in Chromium.

### 3.1 Markers and error bars: one plugin (T2, verified)

`curve/plugins.ts → markers()`: in the `draw` hook, build **one `Path2D` for all error bars
and one for all markers** of a series, then one `stroke` and one `fill`. Cull to the visible
index range (`u.series[i].idxs`), clip to `u.bbox`, skip an error bar shorter than the
marker. Shapes have equal areas (square side 0.886 × the circle's diameter, triangle
1.347 × the radius) so no role looks heavier. The latest point gets a static ring
(`--chart-highlight`), never a pulse.

**Trap found here (Chromium only): `Path2D.closePath()` is quadratic.** With `closePath()`
after each triangle, loading the 50 000-point season took **9.3 s** from the click to the
second frame (CPU profile: 9.2 s inside `closePath`); without it, **89 ms** including the
synthesis of the points, and each later live redraw of the three facets 41-58 ms (fill
closes each subpath anyway). Isolated benchmark, 10 000 triangles: Chromium
183.9 ms with `closePath()` vs 2.5 ms without; WebKit 8 ms vs 6 ms (linear). 50 000:
Chromium 4 384 ms vs 18 ms; WebKit 44 vs 31 ms. Rule: **never call `closePath()` on a
Path2D that accumulates many shapes**; for stroked closed shapes, `lineTo` the start point.

Second trap: uPlot leaves the last series' line dash on the context; a plugin that strokes
must `ctx.setLineDash([])` after `ctx.save()` (the error bars came out dashed otherwise).

### 3.2 Bands (T3, verified)

uPlot fills between two series with `bands: [{ series: [hi, lo], fill }]`. The check-star
facet carries five columns: x, magnitude, `hi`, `lo`, `mean`. The band is the **trailing
15-point mean ± 1 sample sigma** (`curve/band.ts`, incremental, O(w) per new point,
unit-tested): trailing so that appending a point never changes the band already drawn, and
"no spread claimed" below 3 points. It works with the inverted magnitude scale (`dir: -1`)
without special handling. On the synthetic night it visibly widens during each cloud
passage: the scatter the check star exists to reveal, readable at a glance.

```ts
series: [{}, checkSeries, { stroke: edge, width: 1 }, { stroke: edge, width: 1 },
         { stroke: reference, width: 1, dash: [3, 3] }],
bands: [{ series: [2, 3], fill: () => withAlpha(pal.check, 0.14) }],
```

Use in ARGOS: check-star stability (Observe D25 and Review), ensemble mean ± sigma, a model
fit ± its uncertainty, the V-curve fit envelope. Per-point error bars stay in the markers
plugin (the band is a statistic, the bar is a measurement: both can be on).

The cursor would add one hover ring per series (band edges included); `cursor.points.show`
accepts a function `(u, seriesIdx) => HTMLElement | undefined`, used to keep the ring on the
measured series only.

### 3.3 Cursor sync and linked zoom (T4, verified)

- `cursor.sync: { key: 'lightcurve' }` synchronises the crosshair across facets; it does
  **not** link scales. A `setScale` hook (`linkX` in `plugins.ts`) copies the x range to
  the other plots, with a re-entrancy guard.
- `setData(data, resetScales)`: pass `false` while the observer has zoomed, so live points
  never move the view (spec 3.13); a chip says "Manual zoom kept · F fits"; `F` or a
  double-click fits all.
- Drag-zoom is uPlot's `cursor.drag: { x: true, setScale: true }`; the selection rectangle
  is styled from tokens (`.u-select`: 14 % brass fill, brass edges).

### 3.4 Scales and axes

- Magnitudes: `scales.y.dir = -1` (brighter up), one decimal convention per axis
  (`values` formatter with `toFixed`), minimum span 0.06 mag so a flat check star is not
  blown up into noise.
- Time: `scales.x.time = true` with `tzDate: ts => uPlot.tzDate(new Date(ts * 1e3),
  'Etc/UTC')` for the UTC clock axis (D26); JD as a plain numeric axis of `JD − 2461346`
  with the offset in the axis title (5 decimals in readouts). BJD_TDB comes from the server.
- A `range` function can add a constraint: the HFD axis always includes the observer's
  threshold, so the line and its handle never leave the plot.
- Ticks in Plex Mono 10 px (`--text-2xs`) from the tokens; grid `--chart-grid`; one y axis
  per plot (BRAND 10).

### 3.5 Annotations and handles (T5, verified)

The HFD facet shows a **quality threshold**: `thresholdMarks()` draws a dashed
`--chart-reference` line, a ring on every frame at or above it and a rug tick on the x axis
(`--warning`, so a run of bad frames is visible even when 50 000 points are on screen), and
reports the line's position and the count after each draw. The handle is **HTML**, not
canvas: a 16 px brass tab positioned from that report, with `role="slider"`, `aria-valuetext
"2.60 px"`, pointer capture and arrow keys (`curve/handle.ts`). While dragging, the value
comes from `u.posToVal(clientY − over.top, 'y')`: the line follows the pointer exactly and
the count updates on each move; no spring. The header chip says "4 frames ≥ 2.60 px" with a
status dot: the state is in words (BRAND 4.2).

This is the instrument for FS finding 2 (HFD jumped from 5.5 to 17.5 px and stayed there
for 40 minutes, unnoticed): the server-side attention rule (FS P6) decides; the chart shows
the rule's threshold and where it fired.

Canvas vs HTML for annotation parts: draw what is data-dense on the canvas (rings, rugs,
lines), make what is interactive HTML (handles, labels that must be focusable or selectable).

### 3.6 Live append performance

The lab appends a point every 0.5 s (120 × the real cadence) to three facets and redraws
in 1-2 ms at night start, 28-35 ms with 3 600 points per facet (Chromium). Rebuilding a
plot is reserved for theme and axis-type changes; resizes go through `setSize`
(ResizeObserver), error-bar toggles and threshold moves through `redraw(false, false)`.

### 3.7 Colours, gradients, fonts

- Canvas cannot read `var(--x)`. `getComputedStyle(el).getPropertyValue('--selection-bg')`
  returns the **unresolved text** (`color-mix(in srgb, #8d6b2b 55%, #191b1f)`), and the
  app's `parseCssColor` (lib/app/theme.ts) only understands hex and `rgb()`; both engines
  serialise a computed `color-mix()` as `color(srgb 0.466863 0.379804 …)`. `tokens.ts →
  resolveColor()` lets the engine do it: set the value as an element's `color`, paint one
  canvas pixel, read the bytes; cached per string. Rebuild the chart options on a theme
  change (the demo watches `env.theme`).
- Gradients are one call (`ctx.createLinearGradient` in a series `fill` function) and both
  engines draw them, but BRAND 2 forbids gradients under curves: **not recommended**. The
  only gradients in ARGOS are LUTs on the image (section 4.3).

---

## 4. Canvas 2D and WebGL2

### 4.1 Overlays: SVG or canvas

- **SVG** for the interactive marks of a few hundred objects (target, comparisons, check,
  VSX variables): hit-testing, focus and `aria-*` for free, strokes from tokens by CSS
  (the motion demo's field and the popover demo's markers are SVG).
- **Canvas 2D** for thousands of marks (Gaia field stars, WCS grid), redrawn on view change,
  hit-tested by a spatial index if needed. Canvas `roundRect` is in both engines; Canvas
  `filter` (blur, drop-shadow) is **off in every WebKit** (testable flag) [S3]: never use it.

### 4.2 Sparklines (verified)

`frame/Sparkline.svelte`: a canvas, tokens resolved at draw time, last value as a dot, no
library. 120 points: 0.004 ms per draw in Chromium, 0.008 ms in WebKit. Sized from
`ResizeObserver`; `devicePixelRatio`-aware. Use: conditions in a card, Watch view tiles,
run strip, Ensemble rows. Accessible name = label + latest value (the visible number next
to it is the real readout).

### 4.3 WebGL2 viewer: R16UI, stretch in the shader, LUT texture (T6, T7, verified)

`frame/gl.ts` (the app's `lib/viewer/renderer.ts` already does the stretch):

- The 16-bit frame is uploaded as an `R16UI` texture and read with `texelFetch`: exact ADU
  values, no float conversion on the CPU. `texSubImage2D` of 2.07 Mpx: 0.1-0.3 ms of main
  thread; upload + draw + forced sync (`readPixels`) 2.0 ms Chromium (Metal), 3 ms WebKit.
- Minification takes the **max over the screen pixel's footprint** (up to 4 × 4 taps): at
  "fit" a faint star never falls between samples.
- `MAX_TEXTURE_SIZE` 16 384 in both: a 1080 × 1920 frame fits without tiling.
- False colour through a 256 × 1 RGBA LUT texture sampled after the stretch.
- `EXT_disjoint_timer_query_webgl2` (true GPU timings) exists in Chromium, **not in
  WebKit**: measure with a `readPixels` sync instead (as the demo does).
- `OffscreenCanvas` with a WebGL2 context **in a worker** works in both engines (probed):
  the viewer could move off the main thread later if the UI ever janks; not needed now.

**Perceptual LUTs (T7).** The first lab LUTs were hand-picked sRGB stops; their OKLab
lightness steps varied 21-fold (0.0025 to 0.0528 per level), which brightens faint sky noise
and compresses star cores. The new ones (`buildLut`, 30 lines, no library) are OKLCH ramps
with **lightness equal to the stretched value**, hue 20 → 100° (Fire) or 275 → 200° (Ice),
chroma `0.2 × sin(πv)^0.75` reduced by bisection until in the sRGB gamut (lightness is never
traded for chroma). `frame/lut.test.ts` checks monotone lightness, exact black and white.
OKLab conversion: Ottosson [S8].

Night Red: only the neutral LUT, multiplied by `--viewer-tint` (`#d80000`) in the shader;
other palettes disabled with the reason in words (spec D30). Audited: 0 non-red pixels in
both engines.

### 4.4 Where CSS colour features fit

`color-mix()`, `oklch()`, relative colour syntax and `contrast-color()` are all in both
engines (probed), and Canvas `fillStyle` accepts `color-mix()` and `oklch()` in both. For
tokens: keep `color-mix(in srgb, …)` (as tokens.css does) for Night Red tints. Mixing two
reds in sRGB stays red; interpolating in OKLCH goes around the hue circle and can pass
through orange. Note that Safari 26.2 defaults `color-mix()` without a space to **oklab**
[S2]: always name the space.

---

## 5. Workers and OffscreenCanvas (T6, verified)

`frame/frame.worker.ts` synthesises a 1920 × 1080 u16 frame and computes its statistics
(median, MAD, 1024-bin histogram, star count, HFD) each second; the pixel buffer is
**transferred** to the main thread, uploaded to WebGL, then transferred back for reuse
(ping-pong: no copy, no garbage per frame). Measured per frame:

| Step | Chromium 156 | WebKit 26.5 |
|---|---|---|
| Worker: synthesis (lab only) | 9-19 ms | 38 ms |
| Worker: statistics of 2.07 Mpx | 9-10 ms | 15 ms (7 ms in the isolated benchmark) |
| Main: `texSubImage2D` + draw call | 0.2 ms | ≤ 1 ms |
| GPU upload + draw, synced | 2.0-2.5 ms | 3 ms |
| Request to pixels on screen | 20-25 ms | 58 ms |

In the app the frame arrives from the server's WebSocket; the same worker shape decodes it
and computes display statistics while the main thread only uploads. `SharedArrayBuffer` is
not usable (needs cross-origin isolation headers; transfer is enough at 1 fps).
`requestIdleCallback` and `scheduler.yield()` are **missing in WebKit**: break long tasks
with `setTimeout(0)` or a `MessageChannel` post.

---

## 6. Modern CSS and DOM: support and use

Cr = Chromium 156, WK = WKWebView macOS 26.5 (SDK 26), both measured; GTK = first
WebKitGTK release with the feature on by default, from WebKit's feature flags [S3]
("·" = not flag-gated, untested). Safari version where it landed from Apple's notes [S1, S2].

| Feature | Use in ARGOS (concrete) | Cr | WK | GTK | Fallback / note |
|---|---|---|---|---|---|
| Container queries (size) | Card content reflows by its own width: the Conditions component is a list in the 420 px rail, four cards in the drawer, big tiles in a Watch view; Mount readouts go 2 × 2 → 1 × 4 above 520 px (verified, space demo) | yes | yes | · | none needed |
| Container style queries | Density variants (`--density: watch`) without prop drilling | yes | yes | · | attribute selectors |
| `:has()` | A form row marks itself when its field is invalid or busy, no script (verified: `.group:has(#exp:invalid)`); a card header shows a dot when any child is in error | yes | yes | · | class from script |
| Subgrid | One label column across every fieldset of a card (Camera form, verified) | yes | yes | · | fixed label width |
| CSS nesting, `@scope` | Not needed: Svelte scopes styles; fine in `tokens.css` | yes | yes | · | |
| `field-sizing: content` | Object name and notes fields that grow with their text | yes | yes (Safari 26.2) | 2.52 | fixed width |
| `text-box-trim` | Exact vertical centring of 12-13 px labels in 30 px controls | yes | yes | · | padding |
| `text-wrap: balance / pretty` | Empty states, help text, captions | yes | yes | pretty 2.50 | ragged text |
| `content-visibility: auto` | Skip rendering folded cards and off-screen facets | yes | yes | · | |
| `scrollbar-color`, `scrollbar-gutter` | Night Red scrollbars from tokens; no layout jump when a rail starts to scroll | yes | yes (Safari 26.2) | 2.52 | `::-webkit-scrollbar` (in `lab.css`) |
| `color-mix()`, `oklch()`, relative colours | Tints from tokens (selection, 14 % brass), LUT design | yes | yes | · | section 4.4 |
| `@starting-style` + `transition-behavior: allow-discrete` | Popover / menu entry (opacity + 4 px, 180 ms) with no JS (verified) | yes | yes | · | instant |
| `overlay` property | Keeps a closing popover in the top layer during its fade | yes | **no** | · | exit is instant in WebKit (acceptable) |
| View Transitions (same document), `view-transition-class` | 180 ms cross-fade between sections and task modes (FS P1); never on data panes | yes | yes | · | instant; skip under reduced motion |
| Scroll-driven animations | A rule under a sticky card header that appears once the rail scrolls | yes | yes (Safari 26.0) | 2.48 | static rule |
| `@property` | Animatable typed `--hold` for hold-to-confirm (verified) | yes | yes | · | |
| `linear()` easing | Spring-like CSS curve for a drawer snap | yes | yes | · | `--ease-out` |
| `interpolate-size` / `calc-size()` | `height: auto` transitions | yes | **no** | · | `grid-template-rows: 0fr → 1fr` (works everywhere) |
| Popover API | Toolbar popovers, menus, tooltips in the top layer, light dismiss, Esc (verified) | yes | yes, **SDK 14+ link** | · | `position.ts` + manual dismiss (verified) |
| `popover="hint"` | Tooltips that do not close an open menu | yes | **no** | preview in 2.54 | `manual` popover |
| CSS anchor positioning, `position-try-fallbacks` | Popovers, tooltips, the segmented control's indicator; flip when no room (verified) | yes | yes (Safari 26.0) | 2.50 | `position.ts` |
| `<dialog>` `showModal`, `inert` | Modal dialogs; inert background (layers.ts uses it) | yes | yes | · | |
| `dialog closedby` | Light dismiss of sheets | yes | **no** | · | manual handler |
| `command` / `commandfor` | Declarative open / close of dialogs and popovers | yes | yes (Safari 26.2) | 2.52 | `onclick` |
| `CloseWatcher` | Esc / back stack | yes | **no** | 2.54 | `layers.ts` stack (exists) |
| `accent-color` | Not enough for Night Red (section 9) | yes | yes | · | token-drawn controls |
| `:user-invalid` | Show a field error only after the observer touched it | yes | yes | · | `:invalid` + touched class |
| CSS Custom Highlight API | Filter / search matches in tables and the log without DOM rewriting (verified) | yes | yes | · | `<mark>` split |

Dates of the newest WebKit ones: anchor positioning and scroll-driven animations in Safari
26.0; `field-sizing`, `scrollbar-color`, `command` / `commandfor` and the `scrollend` event
in Safari 26.2 (December 2025) [S1, S2]; WebKitGTK anchor positioning stable from 2.50
(testable in 2.48), `field-sizing` and `command` stable from 2.52 (preview in 2.50),
`CloseWatcher` from 2.54 (testable in 2.52), verified on the branches [S3].

### 6.1 Popover with anchor positioning, and the fallback (T11, verified)

```svelte
<button style="anchor-name: --cat" popovertarget="cat">…</button>
<div id="cat" popover="auto" class="pop">…</div>
<style>
  .pop { position: fixed; inset: auto; position-anchor: --cat;
         position-area: bottom span-left; margin-top: 4px;
         position-try-fallbacks: flip-block, flip-inline;
         transition: opacity var(--duration-base) var(--ease-out),
                     transform var(--duration-base) var(--ease-out),
                     overlay var(--duration-base) allow-discrete,
                     display var(--duration-base) allow-discrete; }
  .pop:not(:popover-open) { opacity: 0; transform: translateY(4px); }
  @starting-style { .pop:popover-open { opacity: 0; transform: translateY(4px); } }
</style>
```

The demo picks the path at run time: native (Popover API + anchor), Popover API + JS
placement (`lib/components/position.ts`, for engines without anchor positioning), or JS
only (no Popover API: WKWebView in an app linked on an older SDK); a toggle forces each, and
they render the same (screenshots `popover-observatory` / `popover-fallback-observatory`).
One shared tooltip element is re-anchored to the hovered or focused button; note that
`anchor-name` is a single property, so a button that already has one must list both
(`--own, --tip`).

Night Red: the popover's checkboxes and range are token-drawn; `title=""` tooltips are
native and would draw the OS's grey tooltip, so never use `title` on anything visible.

---

## 7. Pointer events and gestures (T9, verified for mouse and wheel)

| Gesture | How | Engine notes |
|---|---|---|
| Drag (splitter, pan, card, handle) | `pointerdown` → `setPointerCapture` → `pointermove` → `pointerup` / `pointercancel` | Both engines. Safari 26.2 fixed click targeting under capture and added fractional `clientX/Y` for pointer events [S2]. |
| Trackpad pinch | Arrives as `wheel` with `ctrlKey` in Chromium and WebKit on macOS; WebKit also fires `gesturestart/change/end` (`GestureEvent`, probed: WK yes, Cr no). The attachment ignores ctrl+wheel while a WebKit gesture is active, so a pinch is never applied twice | Register `wheel` on the element with `{ passive: false }` or `preventDefault` is ignored |
| Touch pinch | Two active pointers: distance ratio = zoom, midpoint delta = pan | `touch-action: none` on the element, or the browser zooms the page. Not tested on hardware |
| Long-press | 500 ms timer on touch / pen `pointerdown`, cancelled beyond 6 px of motion | |
| Right-click | `contextmenu` with `preventDefault` + ARGOS menu | The native menu is grey (Night Red) |
| Double-click / tap | `dblclick` → fit | |
| High-rate drawing (region box) | `getCoalescedEvents()` (both engines) | `pointerrawupdate` is Chromium only: not needed |

Values never lag the pointer: no spring or tween on a dragged value; the spring only
settles a released panel into its dock (section 2.3).

---

## 8. Layout tools

### 8.1 Resizable split panes (verified)

`space/splitter.ts` (section 2.4) on a `role="separator"` element with
`aria-orientation`, `aria-valuenow/min/max`. The space demo measures the cost of each layout
in image pixels: with the rail at 420 px and the drawer at 216 px the image is 987 × 555
with 16 px bands (1440 × 900), 802 × 451 with 29 px bands at 1280 × 800; rail at 580 px:
36 px bands; drawer at 50 %: 167 px side bands. Showing that cost while dragging is cheap
and keeps BRAND 11.1 honest. Persist sizes per section (and per task mode, FS P10) in the
app's prefs, never in `localStorage` keys of the lab.

### 8.2 Virtualised tables (T12, verified)

`table/virtual.ts → rowWindow(scrollTop, viewport, rowH, count, overscan)`: a pure function
(unit-tested) gives the rows to render and their offset; the table renders 41 DOM rows for
10 000 frames at 24 px; window update 0.0-0.1 ms in Chromium (10 ms measured once in
WebKit, not investigated). One tab stop (`role="grid"`), arrows / PageUp / PageDown / Home /
End move the selection and scroll it into view, `aria-sort` on headers, HFD as a data bar
from zero (a truthful length). Above 500 rows per spec 3.5. A library is not needed.

### 8.3 Use of space in practice

- The Watch view (FS P3) is a container-query layout, not a separate app: the same card
  components at a `watch` density token set (digits of 66-83 px for 2 m reading, FS
  finding 6).
- Fill-the-band (BRAND 11.1, FS P2): the band under the image is a size container; what
  goes in it (levels strip, live curve, V-curve) adapts to its height through `@container
  (min-height: …)`.

---

## 9. Night Red: implementation rules learnt from the audit (T13, T14)

1. **No native control renders red-only.** Measured: a native checkbox draws a grey box
   (`rgb(115, 113, 113)`) in Night Red even with `accent-color` set (165 offending pixels).
   Native `<select>` pop-ups, `<input type=range>`, date pickers, number spinners, the
   context menu and `title` tooltips are drawn by the OS. Use the app's token-drawn
   `Checkbox`, `Select`, `Menu`, `tooltip` (they exist in `lib/components`).
2. Canvas and WebGL read colours at draw time from tokens (section 3.7) and rebuild on a
   theme change; the image is `value × --viewer-tint`; LUTs other than neutral are off.
3. Scrollbars: `scrollbar-color: var(--border) var(--bg)` (Safari 26.2+, WebKitGTK 2.52+),
   `::-webkit-scrollbar` styles for older WebKit (in `lab.css`).
4. `<input type="number">` is also a locale trap: on this machine (region France) Chromium
   displays `0,0004` and WebKit `0.0004` for the same value. The app's `NumberField` is a
   text input with `inputmode="decimal"` and its own parser, which is the right choice;
   keep it everywhere a number is typed.
5. Run the audit (`demos/capture.mjs`, Night Red shots) on every UI change; a non-zero
   count fails the change.

## 10. Reduced motion (checklist)

- Tokens zero every `--duration-*` under `prefers-reduced-motion: reduce` (tokens.css); the
  lab adds a `html[data-motion]` override for testing.
- JS motion: `Spring.set(v, { instant: true })`, `Tween.set(v, { duration: 0 })`,
  `animate:flip` / `fade` with duration 0, View Transitions skipped, the ghost of previous
  levels not drawn. The state shown after an action is identical with and without motion
  (screenshots `motion-ghost-observatory` / `motion-reduced-observatory`).
- Information that happens to move stays: the hold-to-confirm fill is elapsed time, linear,
  and keeps running (with a countdown label).

---

## 11. Intl and formatting

| Need | Finding | Recommendation |
|---|---|---|
| Signed numbers (Dec, Δmag, °C) | `Intl.NumberFormat('en-GB', { signDisplay: 'always' })` gives U+002D HYPHEN-MINUS in both engines | Replace with U+2212 (BRAND 5) in one formatter module |
| Thousands | `en-GB` groups with a comma (`50,006`); the lab is inconsistent (`31 207 ADU` elsewhere) | Owner's decision: one grouping (comma or thin space U+2009) in BRAND 5; then one cached formatter |
| UTC clock | `Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', hourCycle: 'h23' })` → `21:34:05` in both | Or `toISOString().slice(11, 19)`, simpler and allocation-free |
| Durations / ETA | `Intl.DurationFormat` exists in both | Not used: BRAND fixes `1h 05m`; a 10-line formatter |
| Cost | Cached `Intl.NumberFormat`, 10 000 formats: 2.4 ms Cr, 3 ms WK; `toFixed`: 0.6-0.7 ms | Cache formatters at module level; `toFixed` + manual minus for hot paths (tables, ticks) |
| Typed input | `<input type=number>` follows the engine locale (section 9.4) | Text input + `inputmode="decimal"`, accept `,` and `.` |

---

## 12. Tauri v2 window features (notes only, not prototyped)

- **Custom title bar.** `decorations: false` plus an element with `data-tauri-drag-region`
  (applies to that element only, not its children), or `window.startDragging()` from a
  pointer handler; window permissions in the capability file [S9]. On macOS a transparent
  / overlay title bar keeps the traffic lights over our own bar (Rust
  `TitleBarStyle::Transparent` in the docs [S9]). For ARGOS: fold the OS title bar (about 28 px on
  macOS) into the section toolbar row (more image height at 1280 × 800); the bar must be
  token-drawn so Night Red holds (the OS title bar is grey).
- **Vibrancy / window effects.** Available (`WindowEffectsConfig`, `window-vibrancy`,
  macOS needs `transparent` + `macOSPrivateApi`) [S10]. **Not for ARGOS**: translucency is
  outside BRAND 9, and in Night Red it would let desktop colours through.
- **Multi-window.** A second `WebviewWindow` for the plot wall or the Watch view on a second
  screen (FS P13). Sync state through the server's event WebSocket (each window subscribes)
  or `BroadcastChannel` (probed in both engines); avoid window-to-window coupling.
- **Global shortcuts.** `@tauri-apps/plugin-global-shortcut`, `register('CommandOrControl+
  Shift+…', cb)`, permissions `global-shortcut:allow-register` [S11]. Only one candidate: a
  system-wide "abort slew" that works when ARGOS is not focused; everything else stays
  in-app (global keys steal them from other apps).
- **Keep-awake.** The Screen Wake Lock API was **granted** in both WKWebView (macOS 26.5) and
  Chromium in a visible page (probed): it keeps the display on. It does not keep a laptop
  awake with the lid closed and does not protect the Python server; a Tauri-side power
  assertion (macOS IOPM, logind inhibitor) is the complete answer (documented only, FS P6).
- **Notifications** are forbidden in Night Red (BRAND 4.3); `Notification` exists in both
  engines but must not be used for alerts; Web Audio (`AudioContext`, present in both) is
  the alert channel FS P6 proposes.

---

## 13. Dependencies

**None was needed.** Everything above is Svelte 5.57, uPlot 1.6.32 and the platform.
Libraries considered and not proposed (sizes are approximate, from memory, not re-measured):
a virtualisation library (TanStack Virtual, MIT, a few kB): `rowWindow` is 25 lines; a
positioning library (Floating UI, MIT, about 10 kB gzipped): anchor positioning plus
`position.ts` cover it; a colour library (culori, MIT): the OKLab conversion is 20 lines;
a gesture library: three attachments cover drag, pinch, wheel and long-press.

---

## 14. Open issues

1. **WebKitGTK is untested.** Run `lab/research.html?demo=support` (and the six demos) in a
   Tauri dev build on Debian trixie / Ubuntu LTS, record with `window.__labSupport()` into
   `recorded.json`, and check WebGL2 R16UI and the frame pipeline there first (GPU drivers
   vary most on Linux).
2. **WebView2 is untested** (Chromium 156 stands in for it).
3. **macOS SDK**: the Popover API needs an app linked on the macOS 14+ SDK; confirm the
   Tauri release build's SDK (`vtool -show-build` on the binary) and keep the JS path.
4. **Touch and trackpad pinch on hardware** and **screen readers** (VoiceOver on the table
   grid, the slider handle, the splitters) were not exercised.
5. The WebKit table window update read 10 ms once (Chromium 0.0-0.1 ms): not investigated.
6. Thousands grouping and the minus sign need one decision in BRAND 5 (section 11).
7. `screenshots/index.html` (the gallery) was not regenerated by this study: run
   `python web/scripts/build_screenshot_gallery.py` to include the new folder.

---

## Sources

- [S1] Apple, Safari 26.0 release notes (CSS Anchor Positioning, scroll-driven animations):
  https://developer.apple.com/documentation/safari-release-notes/safari-26-release-notes
- [S2] Apple, Safari 26.2 release notes, released 2025-12-12 (`field-sizing`,
  `scrollbar-color`, `command` / `commandfor`, `color-mix()` default oklab, pointer-capture
  click targeting, fractional pointer coordinates, `scrollend`):
  https://developer.apple.com/documentation/safari-release-notes/safari-26_2-release-notes
- [S3] WebKit, `Source/WTF/Scripts/Preferences/UnifiedWebPreferences.yaml` on branches
  `webkitglib/2.48`, `2.50`, `2.52`, `2.54`:
  https://github.com/WebKit/WebKit/blob/webkitglib/2.54/Source/WTF/Scripts/Preferences/UnifiedWebPreferences.yaml
- [S4] Debian security tracker, webkit2gtk (DSA-6463-1: 2.52.6 for trixie; DSA-6534-2:
  2.54.0 for trixie): https://security-tracker.debian.org/tracker/webkit2gtk ,
  https://security-tracker.debian.org/tracker/DSA-6463-1 ; WebKitGTK 2.50.0 announcement:
  https://webkitgtk.org/2025/09/17/webkitgtk2.50.0-released.html
- [S5] Svelte docs, `svelte/motion` (`Spring`, `Tween` since 5.8, `prefersReducedMotion`
  since 5.7): https://svelte.dev/docs/svelte/svelte-motion
- [S6] Svelte docs, `{@attach}` and `svelte/attachments` (since 5.29):
  https://svelte.dev/docs/svelte/@attach , https://svelte.dev/docs/svelte/svelte-attachments
- [S7] uPlot 1.6.32 source (`node_modules/uplot/dist/uPlot.esm.js`: bands 2981-2985 and
  4313-4345, cursor points 1297-1313 and 3608-3619) and https://github.com/leeoniya/uPlot
- [S8] B. Ottosson, "A perceptual color space for image processing" (OKLab):
  https://bottosson.github.io/posts/oklab/
- [S9] Tauri v2, Window customization: https://v2.tauri.app/learn/window-customization/
- [S10] Tauri, window-vibrancy: https://github.com/tauri-apps/window-vibrancy
- [S11] Tauri v2, Global shortcut plugin: https://v2.tauri.app/plugin/global-shortcut/
