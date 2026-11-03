# ARGOS visual identity: web UI

Owner: design team (`web/src/design/`). Audience: front-end developers, icon designers,
art QA. This guide is normative: a component or icon that breaks a MUST rule here is a bug.

**Status (2026-11-01).** The owner accepted the art-direction decisions D1-D11 of the design
lab (`web/lab/PROPOSAL.md` section 10) on 2026-11-01: task modes and the task band (D1), Run
controls in Observe with a server interlock (D2), Watch and server-side attention rules
(D3), Park by hold and Stop by dialog (D4), U+202F grouping and U+00D7 factors (D5), the
cursor readout on the image HUD (D6), Comfortable density as tokens (D7), the frame sizes
toolbar 44 px, status bar 28 px, right panel 360-580 px with 400 by default (D8), queued
focuser taps (D9), check star as check − catalogue V (D10) and the data-ramp and hatching
exception to principle 2 (D11). The amendments of PROPOSAL section 4 are applied below
(sections 2, 3, 4.3, 5, 7, 8, 9, 10, 11.1 and the new section 13); the tokens of PROPOSAL
section 5 are in `tokens.css`. Where an older answer differs (README Q-G4, the 420 px rail,
the 47 px Observe toolbar, the 32 px status bar), these decisions win.

Files in this folder:

| File | Role |
|---|---|
| `tokens.css` | All colours, type, spacing, radii, icon sizes, control and frame metrics, states, motion, chart tokens. Three themes, two densities (Compact, Comfortable). |
| `fonts.css`, `fonts/` | IBM Plex Sans / Mono, bundled (SIL OFL 1.1, see `fonts/OFL.txt`). |
| `icons/<id>.svg` | One original icon per id, 24 x 24 grid, `currentColor` only. |
| `icon-inventory.json` | Every current Qt action mapped to an icon id, with the glyph's metaphor. |
| `icon-sheet.html` | Generated review page: every icon at 16 / 20 / 24 / 48 px, in context, in all three themes. |
| `tools/build_icon_sheet.py` | Regenerates `icon-sheet.html` (standard library only). Run it after any icon change. |
| `BRAND.md` | This guide. |

---

## 1. Positioning

ARGOS is a **scientific instrument**, not a consumer app. It drives a ZWO Seestar over
ASCOM Alpaca, records timed FITS sequences and measures differential photometry of
variable stars. People use it at night, outdoors, often offline, with dark-adapted eyes,
and the data it produces is submitted to the AAVSO. The interface should feel like a
well-made laboratory instrument: quiet, exact, legible at a glance, and trustworthy.

The public site says it in one line: *"Its own software stops at the picture. ARGOS starts
at the measurement."* The UI is where that measurement happens.

## 2. Design principles

1. **Data first.** The image, the coordinates and the light curve are the content; the
   chrome recedes. Neutral graphite everywhere, colour only where it carries meaning.
2. **Calm.** No decorative gradients, glows, glass, bouncing or decorative animation.
   Nothing moves unless the instrument moves, a value changes, or the observer changes
   the layout. Two graded fills are data and are allowed: a display ramp that shows the
   exact mapping of the image (LUT preview), and hard-stop hatching that marks a period
   or a stale state.
3. **Precise.** Numbers in a monospaced face with tabular figures and explicit units;
   one decimal convention per quantity; signs always shown on declinations.
4. **Dark-adapted.** Every theme is dark. Night Red guarantees that nothing on screen
   emits non-red light (section 4.3).
5. **Deliberate actions are visible, routine actions are compact.** Frequent tools are
   icon-only; anything that moves hardware irreversibly, stops a run or writes files keeps
   its label (section 7).
6. **One vocabulary.** The same shape means the same thing on the image, in the plots,
   in the controls and in the icons: circle = target, square = comparison, triangle =
   check, and these three shapes mean nothing else (an attention mark is never a
   triangle). A ring around a control is elapsed time; a dashed edge is "not current" or
   "not yet sent"; a hollow mark is idle.
7. **Say the observer's task, not the implementation.** "Identify field" on the button,
   "ASTAP plate solve" in the tooltip (the convention the Qt app already follows).
8. **Spaces follow the night.** Each section keeps one set of regions. Observe re-arranges
   them in four task modes (Framing, Focus, Field, Run) and a Watch view serves the hours
   of waiting. The observer chooses the mode; the app only suggests one.
9. **Liveness is always visible.** Anything live shows its age; a live time plot runs to
   "now"; a stale value says so in words; an alert never hides the last-frame age.

## 3. What is preserved from the current charter, and why

| Element | Decision | Why |
|---|---|---|
| Palettes | Observatory (default), Charcoal and Night Red hexes copied **unchanged** from `argos/ui/palettes.py` into `tokens.css` (checked by script against the dataclasses). | They are the product's identity and already field-tested. Mandatory token names mirror the `Palette` fields (`bg2` becomes `--bg-2`, `border_soft` becomes `--border-soft`). |
| Brass `#c49a3c` | Reserved for **focus, selection and deliberate actions** (primary button, selected rail entry, toggled tool, focus ring, the active target). Never decoration, never a large background, never body text. `--role-target` is in the brass family on purpose (the active target), so a target series already spends brass on a run screen: long or large fills (areas, coverage blocks, progress bars) never use `--accent` or a role colour; they use neutral inks. | Brass comes from the ARGOS mark; scarcity is what makes it mean "this one". |
| Graphite neutrals | Backgrounds, surfaces, borders and text stay neutral graphite. | "A scientific cockpit should not read like a dashboard of unrelated blue/green/purple status colours" (palettes.py). |
| Semantic colours | `--success`, `--warning`, `--danger` keep their muted charter values and their meaning only. | Status must never be mistaken for a data series. |
| Night Red | Kept with its rules: luminance hierarchy instead of hue, states always double-coded by icon or label. | Dark adaptation of the observer's eyes. |
| Tight radii | 2 px on controls, 4 px on cards. | The Qt stylesheet's instrument-panel look (flat, Siril-like). |
| Spacing | 4 / 6 / 8 / 12 / 18 px scale of `design.py`, plus 24. | Forms keep the rhythm users know. |
| Rail | Left navigation rail, icon above a short label, state dot. | Same mental model as the Qt shell. |

**Changes, deliberately:**

- **IBM Plex Sans and Plex Mono replace the system stacks** (the stacks remain as
  fallbacks): shared with the website and the 0.4.1 art-direction study, so the app and
  the site finally speak with one voice, and identical on macOS and Debian.
- **Live readouts are `--fg`, not brass.** The Qt `MetricLabel` painted every value in
  brass, which contradicts the brass reservation; a readout turns brass only when it is
  the selected or active quantity.
- **Content on brass and on danger fills is dark** (`--on-accent`, `--on-danger`). The Qt
  hover state put `#e8e5df` on `#c49a3c` (2.08:1, illegible); `#191b1f` on `#c49a3c` is
  6.60:1.
- **Text buttons become icons** following the grammar of section 6. The Qt sidebar's
  Feather icons (MIT, generic) are replaced by original ARGOS drawings.
- **Photometric role colours are re-stepped for plots** (`--role-*`, section 10): the
  charter's cyan and sage are only dE 5.5 apart (normal vision), too close to tell series
  apart.

## 4. Colour

All colours are tokens; components never contain a hex value. Themes switch with
`<html data-theme="observatory|charcoal|night-red">`.

### 4.1 Roles

| Token | Use |
|---|---|
| `--bg` | Window background. |
| `--bg-2` | Sunken: inputs, log, plot backgrounds, tooltips. |
| `--surface` | Raised: hover fill, toggled fill, cards in a sunken area, tab background. |
| `--border` / `--border-soft` | Region separators and control outlines / separators inside a panel. |
| `--fg` / `--fg-muted` / `--fg-disabled` | Primary text and glyphs / idle toolbar glyphs, rules, dots / disabled. |
| `--text-muted` | Secondary **words** (captions, form keys, rail labels, tick labels). Equals `--fg-muted` in Observatory and Charcoal; in Night Red it is the palette's `#bb6667`, because `--fg-muted` is below AA there. |
| `--primary-bg`, `--primary-fg`, `--primary-border`, `--primary-bg-hover`, `--primary-fg-hover` | The primary (deliberate) control, per theme (section 8). |
| `--accent` / `--accent-hover` / `--accent-deep` | Brass: selection, focus, deliberate actions (section 3). |
| `--cyan` | Secondary information: coordinates context, mount status, WCS grid. |
| `--variable` | VSX variable-star markers. |
| `--success` / `--warning` / `--danger` | Status only: ready / busy-attention / error-destructive. Always with an icon or a label. |
| `--on-accent`, `--on-accent-deep`, `--on-danger` | Text and glyphs drawn on those fills. |
| `--status-*`, `--log-*` | Device states and log levels (mirror the Qt mapping, except INFO: `--log-info` is `--text-muted` in every theme, as Night Red already had it, since 2026-11-01. INFO is the most frequent routine level; in brass it spent the brass budget on the least important lines. CMD, OK, WARN and ERROR keep their colours). |
| `--role-target`, `--role-comparison`, `--role-check` | Photometric roles, on the image and in plots. |
| `--overlay-*` | Catalogue layers on the image (mirror `fits_viewer.py`). |
| `--chart-*`, `--viewer-*` | Plots and the image canvas (sections 10 and 11). |

### 4.2 Contrast facts (WCAG 2 ratios on the exact hexes)

Worst case over `--bg`, `--bg-2` and `--surface` (AA: 4.5:1 for text, 3:1 for glyphs,
dots and outlines). Computed on the resolved tokens, `color-mix()` included.

| Token | Observatory | Charcoal | Night Red |
|---|---|---|---|
| `--fg` | 12.09 | 10.95 | 7.22 |
| `--text-muted` | 6.39 | 5.98 | 4.56 |
| `--fg-muted` | 6.39 | 5.98 | **3.61** (glyphs only) |
| `--fg-disabled` | 3.13 | 2.94 | 1.55 (disabled, exempt) |
| `--accent` | 5.82 | 5.08 | **3.89** (glyphs, outlines) |
| `--toggled-fg` | 5.82 | 6.87 | 5.31 |
| `--danger` | **4.41** | **4.09** | 5.20 |
| `--success` / `--warning` | 5.64 / 6.83 | 4.98 / 6.09 | **2.32** / **3.36** |
| `--cyan` / `--variable` | 5.87 / 7.09 | 5.25 / 6.77 | 4.56 / **3.16** |
| `--role-target / comparison / check` | 4.96 / 5.00 / 5.29 | 4.33 / 4.37 / 4.62 | 5.31 / 4.56 / 3.16 |
| `--border` on `--bg` | 2.13 | 2.26 | 1.40 |

Pairs: `--primary-fg` on `--primary-bg` 6.60 / 5.87 / 5.31, on hover 8.53 / 7.94 / 5.91;
`--on-danger` on `--danger` 5.01 / 4.73 / 5.79; `--selection-fg` on `--selection-bg`
7.10 / 6.38 / 5.64; `--on-accent-deep` on `--accent-deep` 3.91 / 3.60 / 3.85 (never a
label at rest). Every `--log-*` is at least 5.07:1 on `--bg-2` in every theme. Overlays on
the black canvas are at least 3.61:1.

Consequences (MUST):

- Words use `--fg` or `--text-muted`, never `--fg-muted` (it fails AA in Night Red),
  `--fg-disabled`, a status colour or a role colour.
- `--danger` is a glyph and outline colour; a danger control's **label stays `--fg`** at
  rest (danger text on `--surface` is 4.41:1 / 4.09:1, and lower on a danger tint).
- Night Red: `--success`, `--warning`, `--variable` and `--accent` are marks, not text;
  status dots there sit below 3:1 (`--success` 2.32:1), so the status **label** carries
  the state.
- Control outlines (`--border`, 1.40-2.26:1) are never the only cue that something is a
  control: icon, position and hover state carry it too.

### 4.3 Night Red: the dark-adaptation contract

In `[data-theme="night-red"]` **nothing on screen may emit non-red light.**

- Every visible pixel comes from a Night Red token or is black (`#000000`). No white,
  grey, blue or green anywhere: not in images, plots, focus rings, selection, scrollbars,
  tooltips, menus, cursors, splash or empty states.
- The image canvas renders the red channel only: a stretched value `v` is drawn as
  `v x --viewer-tint` (`#d80000`, the red channel of `--fg`), so the brightest star never
  outshines the interface text.
- Plots use the single-hue `--role-*` values; series are told apart by **marker shape** and
  direct labels, never by colour alone.
- States differ by luminance only, so every status carries its icon or label.
- Native widgets: `color-scheme: dark` and `accent-color` are set by the tokens, but native
  `<select>` pop-ups, date pickers, scrollbars and OS dialogs can still draw grey. In Night
  Red, use custom menus and pickers built from tokens and set
  `scrollbar-color: var(--border) var(--bg)`.
- The app must never flash white: apply `data-theme` before first paint and give `html` a
  token background.
- No OS notifications, no bright splash, no flashing animation.
- **No Unicode pictographs in UI text** (in any theme): characters such as ⚡ ▶ ■ ◉ ⟳ can
  be drawn as colour emoji, which emit yellow, blue or white light in Night Red. The Qt
  labels used them as icons; the web UI uses `icons/` instead.

**Audit (MUST, in CI).** Every Night Red screenshot, in Chromium and in WebKit, passes:
(a) no pixel has G > R or B > R; (b) no pixel has max(G, B) > 8 and max(G, B) > 0.68 × R,
with ±0.5 per channel allowed for 8-bit rounding (anti-aliased `--fg` edges over black).
Audit captured originals, never a resampled copy: a resampling filter with negative lobes
creates green above red on near-black edges. Tool: `web/scripts/audit-png.mjs`
(`npm run audit:night-red`; moved from `web/lab/synthesis/` in wave 2).

Note (measured, not changed): the charter's Night Red colours are red-dominant but not
pure red. Green and blue carry 60 % of the luminance of `--fg` (`#d88f8f`), 48-50 % of
`--fg-muted`, `--text-muted` and `--variable`, and 33-38 % of the accents, warning, danger
and success. The hexes are kept unchanged by contract. A strictly red-only text colour
cannot exceed about 4.6:1 on `--surface` (pure `#ff0000` gives 4.60:1), so a stricter
Night Red would trade legibility for dark adaptation: the owner's decision. Non-palette
tokens add no green or blue (`--viewer-tint` `#d80000`, black shadows, `--scrim`).

## 5. Typography

**Decision: IBM Plex Sans for the interface, IBM Plex Mono for every number, coordinate,
unit, identifier and log line.** Both are bundled locally (woff2 from `docs/fonts`, the
website's files: Sans 400/500/600, Mono 400/500) under the SIL OFL 1.1. No network font
is ever requested. Fallbacks are the Qt stacks.

| Token | Size | Family / weight | Use |
|---|---|---|---|
| `--text-2xs` | 10 px | Mono 500, uppercase, `--tracking-caps` | Micro labels ("RA", "HFD", panel eyebrows), plot ticks. |
| `--text-xs` | 11 px | Sans 500 | Rail labels, chips, tooltips, captions. |
| `--text-s` | 12 px | Sans 400 / Mono 400 | Form keys, status strip, table cells, log. |
| `--text-m` | 13 px | Sans 400, buttons 500 | Body, buttons, inputs (the Qt base size). |
| `--text-l` | 14 px | Sans 600 | Section titles inside cards. |
| `--text-xl` | 17 px | Mono 500 | Live readouts: RA/Dec, Alt/Az, HFD, magnitude. |
| `--text-2xl` | 22 px | Sans 600, tracking -0.02em | Page titles (rare). |

Line heights: `--leading-tight` 1.2 (readouts, buttons), `--leading-normal` 1.4 (UI),
`--leading-relaxed` 1.55 (help text).

**Numbers.** Always `font-family: var(--font-mono); font-variant-numeric: var(--numeric);`
(tabular, lining; both Plex faces already have tabular digits, the property makes it
explicit). Right-align numeric columns and give each quantity a fixed number of decimals so
decimal points line up. Display negatives with U+2212 MINUS SIGN so `+` and `-` take the
same width.

Thousands are grouped with U+202F NARROW NO-BREAK SPACE from 1 000 up, in every face
(`12 450`, `65 535 ADU`): one cell wide in Plex Mono, so columns stay aligned, and never
broken across lines. Never a comma (a decimal mark for much of Europe) or a plain space.
Factors and products use U+00D7 (`2.5× baseline`, `20 × 10 s`), never the letter x.
`Intl` number formatters are not used for display (they produce U+002D).
(Implementation: `web/src/lib/format/number.ts`, which also parses what an observer types,
point or comma decimal.)

**Coverage facts** (checked on the bundled files): Plex Mono has no Greek letters; set
alpha, delta, sigma, Delta in `--font-ui`. Neither face has U+25CF / U+25CB; draw status
dots with CSS or SVG. Degree, prime, double prime, plus-minus, multiplication and minus
signs are present in both.

**Astronomical formatting conventions** (one per quantity, everywhere):

| Quantity | Format | Example |
|---|---|---|
| Right ascension | `HHh MMm SS.Ss`, zero-padded | `05h 35m 17.3s` |
| Declination | sign always, `±DD° MM′ SS″` (U+2032, U+2033, never `'` `"`); `SS.S″` where astrometric precision matters | `+05° 23′ 28″`, `−00° 04′ 07.2″` |
| Alt / Az | decimal degrees, 2 decimals, no space before ° | `41.27°` |
| Time | UTC, ISO 8601, explicit zone | `2026-11-01 21:34:05 UTC` |
| Julian dates | JD / HJD / BJD named, 5 decimals (0.86 s) | `BJD 2461346.40123` |
| Magnitude | 3 decimals with uncertainty | `12.345 ± 0.012` |
| Limits | relational sign + value | `≤ 18.0` |
| Plate scale | `″/px` | `3.67″/px` |
| Durations / ETA | `1h 05m`, `12m 30s`, `10 s` exposure | `ETA 1h 05m` |
| Temperature | space before °C (SI) | `−10.0 °C` |
| Pixel measures | value + `px` (state the channel when it matters) | `HFD 2.1 px` |
| Integers and counts | grouped with U+202F | `12 450 steps` |
| Factors | value + U+00D7 | `1.5× baseline` |

Rounding: round once to the displayed precision, then carry (59.96 s becomes 00.0 s and
the minute increments), as `format_ra_hms` in `argos/core/imaging/platesolve.py` does.
(The Qt mount panel truncates declination seconds; the web formatters must round both
coordinates the same way.)

**Wordmark.** "ARGOS" in Plex Sans 600 with tight tracking (-0.065em), next to the brass
mark, as on the website. Inside the app the mark sits at the top of the rail at 24 px.
This is the reference wordmark (owner's decision, 2026-11-01). The generator's
"argos-avec-nom" preset ("Argos" in Inter 800) is not: do not use it.

**The mark is never redrawn (MUST).** The ARGOS mark (ring, centre dot and four hooked
swirl arms) has exactly one source: the official generator, `tools/logo-generator.html`,
mirrored by `tools/gen_presets.py`. The web files are generated from it by
`python web/src/design/tools/build_brand_mark.py`, which changes nothing but the colour
(currentColor):

- `brand/argos-mark.svg`: the mark on its 100-unit grid, for large uses (splash, about, empty
  states);
- `icons/about.svg`: the same geometry scaled into the 24 grid, for the rail and the about
  entry. It keeps the generator's stroke (4 on 100, about 1 px at 24 px) and is exempt
  from the icon grammar of section 6.

Never simplify, re-draw, re-weight, crop or re-symmetrise the arms, and never trace the
mark by hand in an icon. Icons may borrow its motifs (ring, centre dot, four-fold symmetry,
round strokes) but must not imitate the mark itself. To change the logo, change the
generator, then re-run the script.

## 6. Iconography grammar

Every icon is an **original ARGOS drawing**. Do not copy, trace or adapt Lucide, Material,
Tabler, Phosphor, Feather, Font Awesome or any other set (identity and licence). Shared
concepts (a plus, an x) are fine; the drawing must follow this grammar.

### 6.1 Grid and keylines

- `viewBox="0 0 24 24"`, units are grid units. Display sizes: 16 px (`--icon-s`), 20 px
  (`--icon-m`, default), 24 px (`--icon-l`, rail).
- Stroke centrelines stay inside 2.25-21.75 (ink 1.5-22.5).
- Keylines (stroke centres), for equal optical weight:
  - circle: r = 9 (centre 12, 12);
  - square: 3.75-20.25 (16.5);
  - landscape rect: 2.25-21.75 x 5.25-18.75; portrait: the transpose.
- Anchor points (centres, corners, line ends, radii) on the **0.75 sub-grid** (1/32 of the
  box), 0.375 when a finer step is needed. Points computed from that geometry (an arc's
  end on its circle, chevron arms built on a curve's tangent) keep their exact values, to
  3 decimals.
- **Pixel lattice:** horizontal and vertical strokes sit on the odd multiples of 0.75:
  `0.75 2.25 3.75 5.25 6.75 8.25 9.75 11.25 12.75 14.25 15.75 17.25 18.75 20.25 21.75`.
  Those centres are pixel-exact at 16 px on 1x and 2x screens and at 24 px on 2x screens.
  The centre axis (12) is allowed for the symmetry axis of symmetric glyphs (crosshair
  ticks); it renders 2 px soft at 16 px@1x, which is the accepted trade-off.
- **Filled edges** (transport solids) sit on multiples of 1.5 (`6 7.5 9 ... 16.5 18`), the
  same three crisp cases. A centred solid is therefore 9 or 12 units wide, never 10.5.

### 6.2 Strokes

- One weight: **1.5 units** = 1 px at 16, 1.25 px at 20, 1.5 px at 24. No other width.
- `stroke-linecap="round"`, `stroke-linejoin="round"` (the logo's round strokes).
- Set once on the root `<svg>` (`fill="none" stroke="currentColor" stroke-width="1.5"
  stroke-linecap="round" stroke-linejoin="round"`); children inherit. This lets the
  front-end override the weight per size in CSS if a size ever needs it.
- Dashed lines are drawn as **explicit segments** (`M... M...`), never `stroke-dasharray`,
  so they stay identical at every size.

### 6.3 Corners and curves

- Corner radius 2.25 for frames of 12 units or more; 1.5 for elements of 6-12; none below
  (round joins already give 0.75). Corner brackets take their frame's radius (2.25).
- Angles: 0, 45, 90 degrees by default; 30 / 60 only for perspective (orbits, tilted tube).
- Curves are circular arcs, ellipse arcs or quadratic curves with the gentle hook of the
  logo's arcs. No free-form blobs.

### 6.4 Fills

Fills (`fill="currentColor" stroke="none"`) are allowed only for:

1. **Stars and data points**: filled dots, magnitude-coded like a star chart (brighter =
   bigger): r = 2.25 bright, 1.875, 1.5 standard, 1.125 faint (minimum: 1.5 px at 16).
2. **Transport glyphs**: `start` (solid triangle 12 tall, shifted +0.75), `pause` (two
   bars 3 x 12, radius 0.75, 3 apart: 7.5-10.5 and 13.5-16.5), `stop` (solid rounded
   square 9, 7.5-16.5, radius 1.5: the most ink of the three, so it does not need to be
   larger), `abort` (the same stop square inside the ring r = 9). They must read
   instantly in peripheral vision, and all edges are pixel-exact (section 6.1).
3. **The ARGOS centre dot** (logo heritage), and `theme`'s half disc, where the fill is the
   symbol.

No other solid areas. Never opacity, gradients or two tones: state is the component's job.

### 6.5 Spacing inside a glyph

- Two separate elements: at least **1.5 units of visible gap** between stroke edges (1 px
  at 16). A line that ends near a dot stops at `dot r + 1.5 + 0.75` from its centre.
- Lines either touch (constellation lines meet their stars) or clear by 1.5. Never a
  near-miss. A curve that runs into a line (a Gaussian tail on its baseline) starts
  exactly on it.
- An arrowhead's arms are part of the arrow: the rule applies between the arrow and
  everything else, not between the arms and their own shaft.
- A dot carried on a post (the mount hub) shows at least 1.5 of visible post, or dot and
  base fuse at 16 px.
- Computed geometry (dashes placed on an ellipse, tangent points) may land up to 0.06
  under 1.5 (0.04 px at 16 px); anything closer is a defect.

### 6.6 Optical balance

- Circles use r = 9, squares 16.5: they then look the same size.
- Triangles pointing right (play, live) shift 0.75 to the right of the geometric centre.
- Solid glyphs are inset (stop 10.5) so their mass matches a line icon.
- Wide glyphs (connect, goto) may stay lighter vertically; never stretch them to fill.
- At most about six elements per glyph; if it needs more, it is two icons.

### 6.7 Composition and modifiers

- A **modifier badge** lives in the lower-right cell (keyline box 14.25-21.75). The main
  glyph is cut back so 1.5 units of clearance surround the badge (no masks: cut the paths).
- Modifiers: plus (add), minus (remove), x (clear / failed), **A** (automatic: a stroked
  capital A 6 tall), return arc (reset), outgoing arrow (export), incoming arrow (open).
- Letters and digits are forbidden except the **A** badge and the **1:1** of `zoom-1to1`,
  drawn as strokes. No `<text>`.

### 6.8 Motifs (the ARGOS vocabulary)

| Motif | Drawing | Meaning | Used by |
|---|---|---|---|
| Ring + centre dot | ring r = 4.5, dot r = 1.5 | the observed object / the ARGOS eye (logo centre) | capture, goto, target-star, site, nav-imaging, about |
| Star | filled dot, graded radii | a point source; size = brightness | field-stars, plate-solve, galaxy core, transit, all star plots |
| Role frame | circle / square / triangle around a star dot | target / comparison / check (same as the image overlay) | target-star, comparison-star, check-star, relative-flux |
| Reticle | ring r = 7.5 broken at N/E/S/W, ticks through the gaps (arc ends 3 from the tick centreline), open centre | pointing, measuring | crosshair |
| Sensor frame | rounded square 3.75-20.25, radius 2.25 | one frame / the sensor | capture, live, camera, open-image |
| Field brackets | four corner brackets, arms 4.5, radius 2.25 | the field of view, the displayed image (the viewport) | plate-solve, every zoom-* (zoom-fit pushes them out with diagonal shafts) |
| Region marquee | landscape rounded rectangle drawn as even dashes (1.5 long, 1.5 gaps) | a user-drawn region | region-stats |
| Window | landscape rounded rectangle 2.25-21.75 x 5.25-18.75 | the app window and its panes | panels, layout-tile, layout-reset |
| Motion arc | quadratic or circular arc ending in an open chevron (arms 3-3.4, 90 degrees) | slew, rotation, refresh, reset | goto, refresh, tracking, layout-reset, stretch-reset |
| Light curve | dots following a curve, magnitude increasing downwards; a dip drawn as a line where dots would not fit | photometry results | nav-analyze, light-curve, transit, export-aavso, open-session |
| Axes | L-shape on the left and bottom | a measured plot | nav-analyze, stretch-*, histogram |
| Four-fold symmetry | the logo's C4 rotation | instrument geometry | crosshair, filter-wheel, jog-pad |
| Coupling | plug and socket half-ellipses, two prongs | the device link | connect, disconnect, simulator, nav-connection |
| Mount hub | dot r = 1.5 at (12.75, 17.25) on a post to the base line y = 21.75 | the alt-az mount | mount, park, unpark |

**Astronomy depictions, fixed once:** stars are dots (never 5-point stars, never sparkles);
the sky grid is a bowed RA/Dec graticule on a square field (never a globe); a mount is an
alt-az profile (tube on a fork); the sensor is a chip seen face-on (never a consumer camera
body); focus is a ray diagram; autofocus is the V-curve (five dots on two fitted lines)
with the automatic A badge (a best-focus tick under the vertex read as a letter Y);
catalogues are ledgers of star dots; galaxies and clusters use star-atlas symbols (tilted
ellipse, dashed circle); light curves follow the magnitude convention (fainter is lower);
settings is a calibration gauge with an open 270-degree scale (a full graduated ring with a
needle reads as a clock).

**Reserved glyphs:** the eye only for `nav-imaging`; the magnifier only for `search`; the
ARGOS mark only for `about`. **Banned clichés:** cog wheels, lightning bolts, floppy disks,
globes, five-point stars, sparkles, rockets, eye-for-visibility.

### 6.9 File contract

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="4.5"/>
  <circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none"/>
</svg>
```

- File `icons/<id>.svg`, id in kebab-case, exactly the inventory id.
- No `width`/`height` on the root `<svg>` (a `<rect>` keeps its own), no colour other than
  `currentColor` (and `none`), no `<style>`,
  `id`, `class`, `<defs>`, `<use>`, `<mask>`, `<clipPath>`, `<text>`, `<title>`, script,
  external reference, `opacity`, `stroke-dasharray` or extra `stroke-width`.
- Elements: `path`, `circle`, `ellipse`, `rect`, `line`, `polyline`, `polygon`. A
  `transform="rotate(...)"` is tolerated on a single element; prefer baked coordinates.
- Up to 3 decimals, one element per line, 2-space indent.
- The accessible name comes from the component (`Icon label` / `IconButton label`), not
  from the file.

### 6.10 Review procedure (every icon, before hand-off)

Render with currentColor substituted in a temporary copy, at 16, 20, 24 and 96 px, on
every theme background, and look at the PNGs:

```sh
sed 's/currentColor/#e8e5df/g' icons/goto.svg > /tmp/goto.svg
for s in 16 20 24 32 48 96; do rsvg-convert -w $s -h $s -b '#191b1f' /tmp/goto.svg -o goto-$s.png; done
```

Check: crisp at 16 px@1x (enlarge with nearest-neighbour to inspect), recognisable at 16
without its label, consistent weight with the keystones side by side, legible in Night Red
`--fg-muted` (`#a65758` on `#1a0304`), and not confusable at 16 px with any other icon of
the set (compare it with its family: zoom, layout, files, transport, mount). Then run
`python web/src/design/tools/build_icon_sheet.py` and review `icon-sheet.html` in the
three themes; the page also shows the icons in toolbar, rail and button states.

Intentional near-twins, told apart by one modifier and always shown with a tooltip or a
label: `zoom-in` / `zoom-out`, `plate-solve` / `plate-solve-auto`, `panel-float` /
`panel-dock`, `export` / `export-aavso`, `jog-south` / `disclosure` (never in the same
place).

**Keystones** (drawn by the art director, the reference for everything else): `connect`,
`capture`, `goto`, `plate-solve`, `crosshair`, `nav-analyze`.

## 7. Icon and label rules

| Situation | Display |
|---|---|
| Frequent, reversible tool in a toolbar or viewer (zoom, stretch, overlays, capture, live, jog, focus steps, plate-solve) | **Icon only**, with tooltip (label + shortcut), `aria-label`, `aria-keyshortcuts`. |
| Moves hardware deliberately, stops a run, irreversible or rare (connect page primary, disconnect, goto in the mount panel, park, unpark, abort, start/stop sequence, export, re-run, reset layout, quit) | **Icon + label**. |
| Dialog OK / Cancel, confirmations ("Park the mount?"), form submit | **Text only.** |
| Menu items | Text, with an optional 16 px icon on the left. |
| Navigation rail | 24 px icon above an 11 px label, plus the state dot (ready / active / blocked). |
| Toggles (overlays, tracking, crosshair, loupe) | Same glyph on and off; state shown by the toggled style and `aria-pressed`. A running process (live, autofocus) may swap to `stop` and changes its `aria-label`. |
| Physical action that is hard to undo at night (Park; pause the run to slew) | Icon + label at `--control-h-l` (40 px), **hold to confirm** for `--hold-duration` with the time ring; Enter / Space open an inline two-button confirmation instead. The label never changes while held; the caption under the button does. |
| A control that cannot act now | `aria-disabled` (still focusable), the reason in the tooltip's second line; a press shows the reason at once. |
| An action with options | Split button: the main part acts with the options written on it (`2.0 s`); the chevron or ArrowDown opens them; choosing an option never runs the action. |

Holding ⌘ (Ctrl elsewhere) alone for 450 ms shows each control's shortcut as a neutral
key cap where the control is; any other key cancels. The command palette (⌘K / Ctrl+K)
lists every action with its key or its unavailable reason; a hardware action in it opens
its confirmation and never runs on Enter alone. Jog keys show axis words on an alt-az
mount (Alt +, Alt −, Az −, Az +) and N / S / W / E on an equatorial one (Q-O4).

`icon-inventory.json` gives the default `display` per id; a context may promote an icon to
icon + label, never the reverse for the second row above. Every icon has an accessible name;
an icon next to visible text is `aria-hidden`. Tooltips appear after about 500 ms of hover
and immediately on keyboard focus; they never carry information found nowhere else.
Shortcuts are shown with macOS glyphs on macOS (⌘ ⇧ ⌥) and `Ctrl+Shift+` elsewhere. In
the inventory, `shortcut_origin: "qt"` marks existing bindings; `"proposed"` ones are for
the front-end to confirm. Single-key shortcuts only fire when focus is not in a text field
and never move hardware (exceptions: the jog arrows, kept from the Qt pad, and `Escape` =
abort motion).

Sky orientation: jog icons are plain chevrons whose accessible names say North / South /
East / West. On a north-up sky image east is on the **left**; never assume "east = right".

## 8. States

Mirrors the Qt stylesheet, with the contrast fixes of section 3.

| State | Ghost / toolbar button | Secondary (outlined) | Primary (deliberate) | Danger |
|---|---|---|---|---|
| Rest | glyph `--fg-muted`, no fill | `--border` outline, `--fg` | fill `--primary-bg`, content `--primary-fg`, outline `--primary-border` (brass fill in Observatory and Charcoal; outlined in Night Red, less light) | `--danger` outline + glyph, **label `--fg`**, on `--surface` |
| Hover | fill `--hover-bg`, glyph `--fg` | fill `--hover-bg` | fill `--primary-bg-hover`, content `--primary-fg-hover` | fill `--danger`, content `--on-danger` |
| Pressed | fill `--pressed-bg` | fill `--pressed-bg` | fill `--accent-deep`, `--on-accent-deep` (a flash, 3.6-3.9:1) | fill `--danger` |
| Toggled on | fill `--toggled-bg`, glyph `--toggled-fg`, **no outline** (several toolbar toggles can be on at once; brass outlines on each would no longer single anything out). A **layout** toggle (panels, levels strip: on most of the time, not instrument state) keeps the fill with an `--fg` glyph. | fill `--toggled-bg`, glyph and label `--toggled-fg`, 1 px `--toggled-border` (tracking) | n/a | n/a |
| Focus (keyboard) | 2 px `--focus-ring` outline, 2 px offset, on top of any other state; never removed | same | same | same |
| Disabled | glyph/text `--fg-disabled`, outline `--border-soft`, no hover; prefer `aria-disabled` + a tooltip saying why | same | fill `--surface` | same |
| Busy | glyph replaced by a spinner (a logo-like arc, 1.5 stroke, 0.9 s per turn), `aria-busy`, width unchanged, still focusable | same | same | same |

- **Error** (the last attempt failed): `--danger` outline, a 6 px `--danger` dot in the
  top-right corner, the device's words in the tooltip and `aria-describedby`; cleared by
  the next success.
- **Progress** (a timed operation: exposure, autofocus sweep, export): a ring around the
  glyph whose arc is the exact elapsed fraction, linear, butt caps, `--ring-w`; under
  reduced motion it advances in quarters and the numbers stay exact.
- **Pressed** adds `--pressed-inset` (a 1 px black inner top edge) to the pressed fill; no
  scale, no bounce.
- **Device value fields**: not sent (dashed edge, "Enter sends"), sending (spinner in the
  unit slot), applied (with when it takes effect), refused (the device's words; Esc
  reverts), invalid (never clamped silently), unavailable (the reason). One value per
  commit (Enter, release, blur), never per keystroke or pixel of drag.
- **Modifiers**, for every value control: plain = one step; Shift = ×10 or snap to ticks;
  Alt = ×0.1; the wheel acts only on a focused control; Esc returns to the device value.
- **Attention levels** (chips, lists, Run card, Watch), always with the word: Critical =
  filled `--danger` disc, its sound repeats until acknowledged; Attention = upright mark
  (a bar over a dot) in `--warning`; Info = hollow ring.

Selected rail entry: glyph and label `--toggled-fg`, fill `--surface`, 3 px `--accent` bar
on the left (as in Qt). Segmented choices (transfer, rotation, equipment) always hold one
selection, so the selected segment is fill `--toggled-bg`, text `--fg`, edge `--border`:
no brass. A routine stop (live view) is a secondary button with only its glyph in
`--danger`; the full danger style is for motion (a slew) and destructive actions.

Brass budget while observing: about eight marks (selected rail entry and its state dot,
the live toggle and its ring, auto stretch, the LIVE / REC chip dot, the exposure ring,
the black and white levels, the active target's marker and series). Run progress bars,
coverage blocks, key-hint caps and attention marks are not brass. Count them on a live
screenshot after any change (`audit-png.mjs --brass`).

`--toggled-fg` is brass in Observatory, the lighter brass in Charcoal and the bright red
in Night Red, so the label passes AA on `--surface` and on a 14 % brass tint in every
theme.

Control sizes: `--control-h-s` 30 px (16 px icon), `--control-h-m` 34 px (20 px icon),
`--control-h-l` 40 px (hold-to-confirm targets, Watch), jog keys `--jog-key` 44 px,
inputs 28 px; hit targets are never below 24 x 24 px.

## 9. Layout, density, elevation, motion

- **Density:** compact, instrument-like. Spacing scale `--space-1` 4, `-2` 6, `-3` 8, `-4`
  12, `-5` 18, `-6` 24 px. Card padding 12 / 14 / 12 / 10 px (Qt `CARD_PADDING`). Table rows
  24 px, list rows 28 px. Sparse form pages are capped at `--page-max-w` (880 px); the
  observing cockpit uses the full width with a right rail of 360-580 px, 400 px by default
  (`--rail-min-w`, `--rail-w`, `--rail-max-w`), under a 44 px section toolbar
  (`--toolbar-h`) and over a 28 px status bar (`--statusbar-h`) (owner D8).
  **Comfortable** density (Settings › Appearance) changes tokens, never the page zoom:
  readouts 20 px (`--readout`: the Mount card's RA, Dec, Alt, Az), key readouts 26 px
  (`--readout-key`), card facts and frame statistics 16 px (`--readout-s`, 13 px compact:
  the Camera card's In use / Sensor, the Levels band's Black / Mid / White and Min / Median
  / Max), table and list rows 28 px (`--row-h`), activity-log lines 24 px (`--log-row-h`,
  20 px compact); toolbar, icons and image unchanged (wave 2 review: the first cut changed
  only the Mount readouts).
  **Watch** sizes: primary values 88 px, secondary 66 px, conditions 48 px, labels 30 px
  (digits of 66-83 px read from 2 m on a 13-inch 1440 x 900 screen; functional-spaces 2.5).
- **Radii:** `--radius-s` 2 px (controls, chips), `--radius-m` 4 px (cards, popovers,
  dialogs), `--radius-round` for dots.
- **Elevation:** flat. Regions are separated by 1 px borders (`--border` between regions,
  `--border-soft` inside). Shadows only on floating layers (menus, popovers, tooltips,
  dragged panels: `--shadow-2`). Shadows are black, so they are safe in Night Red. No
  blur, glow or translucency except the modal `--scrim`.
- **Motion** is for state changes and orientation, and is limited to this list: colour
  state changes `--duration-fast`; popovers and panels `--duration-base` (opacity and a
  4 px move); the segmented control's block slides `--duration-fast` after the value is
  applied; task-mode and section switches cross-fade `--duration-base`; a table re-sort
  uses flip for `--duration-fast`; a dragged star card settles into a corner (a spring,
  instant while dragged); a keyboard or button zoom of a plot glides for
  `--duration-base`.
- **Elapsed time is linear** (rings, hold fill), never eased.
- **Data never animates**: values, plots, handles and the image jump to the truth. Live
  statistics are causal (trailing windows), so a point once drawn never moves.
- `prefers-reduced-motion: reduce` sets every duration to 0 (tokens do it) except
  `--hold-duration`, which carries information; rings then advance in quarters and the
  spinner becomes a static arc with `aria-busy`.

## 10. Data visualisation

- **Roles:** target `--role-target`, comparison `--role-comparison`, check `--role-check`,
  each paired with its marker shape (circle, square, triangle). Text in plots wears text
  tokens (`--chart-text`), never the series colour.
- The three Observatory/Charcoal role colours were chosen by search and validated as an
  all-pairs categorical palette (dataviz validator) on every dark surface of both themes:
  lightness band and chroma pass, worst colour-vision-deficiency dE 9.8 (deutan), worst
  normal-vision dE 15.0, all at least 3:1 against the surface. They sit in the charter's
  hue families (brass, steel blue, sage) with enough chroma to do identity work.
- **More than three series in one plot is not allowed**: facet into small multiples (the
  Review page already gives each comparison star its own plot) or fold into "others".
- Light curves: magnitude axis inverted (brighter up), time on x (BJD or UTC, named), error
  bars in the series colour at `--chart-error-opacity`, markers `--chart-marker` (6 px,
  dense series) / `--chart-marker-sparse` (8 px) / `--chart-marker-hover` (10 px), lines
  `--chart-line-w`. Grid `--chart-grid`, axes `--chart-axis`, reference lines (zero, fit,
  ensemble mean) `--chart-reference`, hover crosshair `--chart-highlight`.
- Always: a legend for two or more series, selective direct labels, a value tooltip in mono
  on hover, one y-axis per plot (never dual axes), the plot surface `--chart-surface`.
- Night Red: the role colours collapse to one hue by design; shape and labels carry
  identity. Not a valid categorical palette on colour alone, and documented as such.
- **Live plots**: the x range ends at "now". Past max(2 × cadence, cadence + 60 s) the gap
  after the newest point is hatched and the header says "no frame for …".
- **Zoom states** are named by a chip: Whole run, Following (the right edge on the newest
  frame), Zoom kept. New data never moves a kept zoom; `F` fits, `End` follows.
- The newest point wears a static ring in `--chart-highlight`, never a pulse.
- **Rules**: a dashed `--warning` line at the server's threshold, the period where the rule
  holds hatched from the frame where it fired, a rug on the frames over it. A live chart
  never edits a rule.
- **Check star**: plotted as check − catalogue V with a trailing 15-point mean ± 1σ band;
  its rms is in the readout. Observe shows target and check as two facets on one time axis
  (D25); the comparison ensemble facet lives in Review and in the drawer's Light curve tab.
- **Provisional vs decided**: a fit result stays neutral and labelled "provisional" until
  it is accepted; brass marks only the accepted decision (the autofocus position).
- Sparklines and geometry (altitude, airmass) use neutral inks; role colours are for
  photometric series and role markers only.
- Canvas inks come from the tokens through `web/src/lib/charts/ink.ts` (resolved by the
  engine, `color-mix()` included, re-read on a theme change); canvas labels go through
  `web/src/lib/charts/text.ts`, which always sets `textAlign` and `textBaseline`.

## 11. Image viewer

- Canvas `--viewer-bg` (black), the frame outlined in `--border-soft`, pixels drawn as
  `stretched value x --viewer-tint` (white in Observatory and Charcoal, `#d80000` in Night
  Red).
- Overlays: 1.5-2 px strokes, shape-coded like the icons (target circle, comparison square,
  check triangle; catalogue layers per `--overlay-*`). Labels in Plex Mono 11 px,
  `--overlay-label`, with a 1 px black halo for legibility over stars.
- Measurement readouts (cursor RA/Dec, pixel value, HFD) in mono with the formats of
  section 5.

### 11.1 Use of space (MUST, owner's request 2026-11-01)

The image is the instrument's reason to exist: on the observing screen it gets the largest
possible area, and no region may waste space around it. The first integration draft failed
this: a portrait Seestar frame (1080 x 1920) fitted into a landscape viewer left about
half the viewer black, while the stretch card and histogram were pushed below the fold.

- **Display rotation.** Portrait sensor frames are shown rotated to landscape by default
  ("auto", 90° clockwise), exactly like the Qt viewer (`ROTATION_MODES` and `set_rotation`
  in `argos/ui/widgets/fits_viewer.py`, config key `ui.display.rotation`, default `auto`).
  Modes auto / 0 / 90 / 180 / 270 are offered. Rotation is display-only: cursor readouts,
  overlays and any coordinate sent to the server stay in un-rotated frame pixels.
- **Fit fills the viewer.** At "fit", the black margin on the frame's short sides must stay
  small at the reference sizes 1440 x 900 and 1280 x 800. Check it on screenshots.
- **Rails earn their width.** The right rail is collapsible (keyboard shortcut, state
  remembered per viewer) and no wider than its content needs. Cards are collapsible.
  The cards used while observing (camera and stretch with the histogram) are visible
  without scrolling at 1440 x 900. Rarely used fields (target entry, connection details)
  go below them or in a disclosure.
- **No dead bands.** Toolbars, status bar and chips take one row each, with no empty
  strips. Frame chips sit over the image in a corner, not in a reserved band.
- **Task band (was the levels strip).** The band under the image keeps its size rule
  (`band = centre height − drawer − centre width × frame h / w`,
  `web/src/lib/imaging/layout.ts`), and its content follows the Observe task mode:
  Framing = levels and the exposure check (peaks against 65 535); Focus = V-curve and HFD
  trend; Field = comparison candidates; Run = the live light curve (target and check).
  Below 150 px it becomes a one-row summary still as tall as the band. `H` hides it in
  every mode. Dragging its edge overrides the height for that mode and shows the cost on
  the image (`Band 445 px · image 681 × 383 · side margins 133 px`); "Fit to image" returns
  to the rule. When the band does not show the levels, the image HUD carries a 64-bin mini
  histogram with them.
- **Fill fit mode.** `Shift+F` (icon `zoom-fill`) fills the viewer and crops the frame's
  long sides equally; `F` returns to the whole frame. The mode is remembered, and a
  "Fill · cropped" chip on the image says so whenever it crops: a crop is never silent.
- **Mount always in view.** The status bar carries the mount's state and RA / Dec (and,
  during a slew, the angle still to go with an abort button), because the Mount card can
  sit below the fold; the device name moved into the connection badge's tooltip, the
  zoom stays in the toolbar only and the theme in its button's tooltip, to make room.
- **One home per value.** Frame number and exposure on the image chips; cursor X, Y,
  value and RA / Dec on the image HUD (bottom right); the settings in use and the sensor
  in the Camera card; mount, run and rate in the status bar.
- **Stale frames say so.** A frame that is not current (equipment disconnected, server
  link down, or no new frame for max(5 s, three exposures)) gets a muted
  "Last frame · 21:34:05 UTC" chip and a dashed frame edge; rate and latency show "—";
  the connect prompt sits at the bottom of the image, never over its centre.

## 12. Working with the team

- Designers draw from `icon-inventory.json` (`metaphor` is the brief, grid units refer to
  section 6) and match the keystones' weight. Art QA renders the full set side by side and
  checks section 6.9 / 6.10.
- Front-end: consume `tokens.css` only; `Icon.svelte` inlines `icons/*.svg` and shows a
  visible placeholder for unknown ids. Ask the design team before adding a token or an id.
- Any new action: add it to the inventory first (id, labels, sources, metaphor, display),
  then draw it.

## 13. Attention and alerts

Rules run on the server, on every frame (no new frame, HFD rise, star-count drop, too few
comparisons, tracker lost, altitude limit, disk, run stopped on error, device lost). Each
item has a level (§8), a short headline for Watch and the rule with its numbers for the
list. It is shown in the status-bar attention chip (count and newest), its list
(Acknowledge, suggested view), the Run card and Watch's first row. Sound: Web Audio tones
(Critical 3, Attention 2, Info 1), Off / Soft / Normal, armed by a click. No OS
notification, no flashing, no large red fill.
