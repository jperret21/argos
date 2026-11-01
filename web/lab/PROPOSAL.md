# ARGOS UI refresh: synthesis of the design lab

Status: proposal for the owner, 2026-11-01. Author: art direction (synthesis of the design
team). Audience: the owner first, then the front-end, server and design teams.
Open the lab at `http://localhost:5205/lab/index.html` (`cd web && npx vite --port 5205
--strictPort`); hero screenshots: `web/screenshots/2026-11-01_lab-synthesis/`.

This file decides nothing on its own. It says what the lab proposes, what art direction
recommends to keep, change or drop, and what the owner must decide. BRAND.md and
`web/src/lib` were not edited (wave 1 is being built); section 4 gives the exact BRAND text
to add once the owner agrees.

Contents

0. [The direction in one page](#0-the-direction-in-one-page)
1. [What the lab contains](#1-what-the-lab-contains)
2. [Review: one product, one voice?](#2-review-one-product-one-voice)
3. [Decisions on every proposal](#3-decisions-on-every-proposal)
4. [BRAND.md amendments (exact text)](#4-brandmd-amendments-exact-text)
5. [New tokens](#5-new-tokens)
6. [Components to promote, and the wave where each lands](#6-components-to-promote-and-the-wave-where-each-lands)
7. [Server and API work implied](#7-server-and-api-work-implied)
8. [Dependencies](#8-dependencies)
9. [WebKit risks and how to check them](#9-webkit-risks-and-how-to-check-them)
10. [Decisions for the owner](#10-decisions-for-the-owner)
11. [Not design, but urgent](#11-not-design-but-urgent)
12. [Limits of this synthesis](#12-limits-of-this-synthesis)

---

## 0. The direction in one page

The charter does not move: the three palettes (exact hexes), graphite neutrals, brass for
"this one", IBM Plex Sans and Mono, original icons, the mark never redrawn, Night Red
red-only, offline. What changes is how the interface follows an observing night. Seven
principles carry the refresh:

1. **Spaces follow the night.** Observe keeps one set of regions (toolbar, image, the band
   under the image, the right panel, the drawer, the status bar) and re-arranges them in four
   task modes: Framing, Focus, Field, Run. The band under the image belongs to the current
   task. A Watch view serves the hours of waiting. The observer chooses the mode; the app
   only suggests one.
2. **Liveness is always visible.** Anything live shows its age. A live time plot runs to
   "now", so the gap after the newest point is the age of the last frame; an overdue gap is
   hatched and named. A stale value says so in words. An alert never hides the pulse.
3. **Time is a ring, state is a word, role is a shape.** One vocabulary everywhere: circle =
   target, square = comparison, triangle = check (and nothing else); a ring around a control =
   elapsed time, filled linearly; a dashed edge = not current or not yet sent; a hollow mark
   = idle; a level (critical, attention, info) = a mark and a word.
4. **Every action says what it will do, and why it cannot.** A split button shows the
   options it will use ("2.0 s"). An unavailable control stays focusable and a press shows
   the reason at once. A device value is sent once per commit, never per keystroke or pixel
   of drag, and the field shows whether it matches the device.
5. **Physical actions are deliberate.** Hardware never sits on a single key (jog arrows and
   Esc excepted). Actions that are hard to undo at night (Park, pausing a run to slew) are a
   700 ms hold with a ring, and a two-step inline confirmation from the keyboard. The server
   refuses mount motion during a run.
6. **Truthful motion.** Values, plots, handles and the image jump to the truth. Motion is
   for orientation only (a mode switch, a popover, a segmented block, a re-sorted row), and
   it is listed (section 4). Live statistics are causal: a point once drawn never moves.
   Reduced motion makes every transition instant.
7. **Brass is counted, Night Red is tested.** Brass marks the selection, the deliberate
   action and the active target; long fills never use it (measured below). Every Night Red
   screenshot is audited pixel by pixel in Chromium and WebKit.

What was verified and what is a mock: the four labs run in Chrome 156 and render in a real
macOS 26.5 WKWebView (static renders; interactions were driven in Chrome only). All data is
synthetic; hardware is simulated; attention rules run in the browser (the product needs them
on the server); Plan, Review, Connection and Settings exist as blueprints and chart
prototypes, not as built screens. WebKitGTK (Linux) and WebView2 (Windows) are untested.

---

## 1. What the lab contains

| Lab | Page | Code | Owns (single source after promotion) |
|---|---|---|---|
| Observe workspace | `lab/workspace.html` | `src/lab/workspace/` (64 files) | Task modes and per-mode layouts, the task band, image HUD, Run card and wrap-up, Watch, attention UI, command palette, comparison workspace, sections overview |
| Live charts | `lab/charts.html` | `src/lab/charts/` | Light curve (facets, zoom states, time axes), plot wall and health strip, V-curve with fit uncertainty, conditions, visibility, histogram handles, mini-charts, export hooks |
| Controls | `lab/controls.html` | `src/lab/controls/` | Control button and states, time ring, tooltip with reason, key hints, toolbar with overflow, split button, segmented, value fields (scrub, stepper, slider), focuser, jog pad, hold-to-confirm, chips |
| Stack research | `lab/research.html` | `src/lab/research/`, `lab/research/*.md` | Performance and platform patterns, OKLCH LUTs, gestures, popover fallback, virtual table, support matrix, Night Red audit method |
| UX research | `lab/research/functional-spaces.md` | (no code) | The night as 13 tasks, reading distance, evidence from three real nights |
| Synthesis | `lab/index.html`, this file, `lab/synthesis/audit-png.mjs` | | Lab home, decisions, a dependency-free pixel audit |

Checks run by the synthesis (2026-11-01, after the fixes of section 2.3): `svelte-check`
0 errors and 0 warnings over 436 files; `vitest run src/lab` 13 files, 74 tests passing;
controls behaviour checks (`behave.mjs`) 29 / 29;
fresh captures of the three designers' labs on port 5205 (40 workspace, 28 chart and 43
control shots, plus 10 heroes): no page error, no console error, no request outside the
machine.

---

## 2. Review: one product, one voice?

### 2.1 What holds

- **Charter fidelity.** No hex outside the tokens; Plex everywhere; icons from the inventory
  (three proposed `lab-*` glyphs aside); the mark only through the generated `about.svg`.
  The workspace reads as the same instrument as the wave-1 spike, with more of the screen
  given to data.
- **Space.** At 1440 x 900 the Run screen gives the image 947 x 533 px with no black band and
  the band under it 294 px; at 1280 x 800, 787 x 443 px and 284 px (capture report). The
  band's size rule of BRAND 11.1 is kept; only its content changes.
- **Night Red.** All 34 fresh Night Red captures and 56 of the 57 Night Red shots in the
  designers' folders pass rule A (no pixel with green or blue above red); the 57th is a
  resampling artefact (below). Rule B (the research labs' palette test, G/R at most 0.68)
  flags only three workspace shots, on anti-aliased edges of overlay labels drawn in `--fg`
  `#d88f8f` over their black halo (23-48 pixels, at most 15/255), which pass once 8-bit
  rounding is allowed for. The exception: `lab-workspace/webkit-run-night-red.png` is a 2x
  WKWebView capture downscaled to 1440 px; it has 19 near-black pixels with G or B above R
  by at most 2 levels. A resampler with negative lobes creates them; audit originals, never
  resampled copies (the designer reports the 2x original passes; it was not kept, so this
  synthesis could not re-check it).
- **Motion restraint.** Every lab keeps values instant; rings are linear; reduced motion is
  honoured (workspace mode switch, controls rings in quarters, charts zoom glide off).
- **Honesty.** Synthetic data is labelled on screen ("SYNTHETIC DATA" in the workspace status
  bar, invented catalogue ids `000-LAB-xxx`), and the designers state what is a mock.

### 2.2 Where the three designers diverged (and the resolution)

| Concept | Workspace | Charts | Controls | Resolution |
|---|---|---|---|---|
| Thousands grouping | U+2009 thin space | U+0020 space | comma | **U+202F narrow no-break space** in every lab (fixed). Owner decision D5. |
| Attention level marks | ring + upright mark glyph (`lab-attention`), warning outline | brass dot + warning outline | triangle for "attention" | **No triangle** (it is the check star). Critical = filled disc, Attention = upright mark (bar over dot), Info = hollow ring, always with the word. Fixed in `Chip.svelte`; the others converge on promotion. |
| Hold-to-confirm | fill grows behind the label, label changes to "Release to cancel" | — | ring around the glyph, label fixed, caption below | **The controls version**: the ring is the one sign of elapsed time, and a label never changes width. Workspace `ui/HoldButton.svelte` is replaced on promotion (not changed in the lab: different API and tokens). |
| Run progress bar | brass fill | neutral fill | — | **Neutral** (fixed in `RunCard.svelte`). |
| Check star facet | Δ from its median | check − catalogue V | — | **check − catalogue V** everywhere (offset and scatter both visible; readout gives rms). Owner decision D10. Not changed in the lab. |
| V-curve | dashed fit, best position | fit ± 1σ envelope, provisional vertex, verdict in words | gauge diamond = last AF best | **The charts V-curve** in the Focus band and the Focuser card. |
| Focuser card | step segmented + In/Out | — | two-scale gauge, queued taps, Go to as action field | **The controls card.** |
| Observe › Run composition | the full prototype | "In context" mock | — | **The workspace prototype.** The charts mock is kept only to show charts at true size. |
| Toolbar | lab-specific icon buttons | — | data-driven, overflow, split capture | **The controls Toolbar** builds the workspace toolbar on promotion. |
| Jog key labels | — | — | N / S / E / W on an alt-az mount | **Axis words on alt-az** (Alt + / Alt − / Az − / Az +), N / S / W / E on EQ: README Q-O4, already accepted. Fixed in `JogPad.svelte`. |
| Large fills | — | coverage block and altitude areas in the target colour | — | **Neutral inks** for coverage, areas and bars (fixed). |
| Factors in text | "2.5 x baseline" | "1.5× baseline" | "x10" | **U+00D7** ("2.5× baseline", "20 × 10 s"); fixed in the workspace texts. The controls "×10" chip already used it. |

### 2.3 Harmonisation fixes made in the lab

All inside `web/lab/` and `web/src/lab/`; type-check and tests re-run after them.

| Fix | Files |
|---|---|
| Thousands grouped with U+202F (Plex Mono and Sans both carry it; measured: one 0.6 em cell in Mono, 0.118 em in Sans), tests updated | `src/lab/controls/format.ts`, `controls.test.ts`, `src/lab/charts/core/format.ts`, `format.test.ts`, `src/lab/workspace/model/format.ts`, `controls/plates/PlateFocuser.svelte` |
| Attention level "attention" drawn as an upright mark, never a triangle; plate note updated | `src/lab/controls/components/Chip.svelte`, `plates/PlateStatus.svelte` |
| Jog keys show axis words on an alt-az mount, compass letters on EQ (`alignment` prop); tooltips, accessible names, capture and behaviour scripts follow (the behaviour check of the grouped focuser position too) | `src/lab/controls/instruments/JogPad.svelte`, `plates/PlateMount.svelte`, `plates/PlateStatus.svelte`, `capture.mjs`, `behave.mjs` |
| Visibility: frames-taken coverage in a neutral ink; altitude sparklines neutral | `src/lab/charts/charts/VisibilityTimeline.svelte`, `charts/InContext.svelte`, `mini/MiniCharts.svelte` |
| Run card progress bar neutral (`--fg-muted`) | `src/lab/workspace/observe/cards/RunCard.svelte` |
| Watch: the attention row keeps the last-frame age and n / N; sizes fitted so the headline never ellipsises at 1440 and 1280 px | `src/lab/workspace/overlays/WatchView.svelte` |
| "×" instead of the letter x in rule texts, thresholds and darks / biases | `src/lab/workspace/model/rules.ts`, `observe/Drawer.svelte`, `observe/bands/FocusBand.svelte`, `observe/cards/RunCard.svelte`, `overlays/commandIndex.ts`, `overview/sections.ts` |

The designers' screenshot folders predate these fixes (their PNGs still show commas in the
controls lab, N / S / E / W keys, the attention triangle and the brass Run bar); the hero set
was captured after them. The controls behaviour checks pass 29 / 29 after the fixes (real
keyboard and pointer input in Chrome 156, run against port 5205).

### 2.4 Brass, measured

Method (`node web/lab/synthesis/audit-png.mjs --brass`): pixels within RGB distance 28 of
`--accent` `#c49a3c`, `--accent-hover`, `--warning` `#d0a85a` and `--role-target`
`#b48e2c`. Anti-aliased edges are not counted; compare screens only with the same method.

| Screen (1440 x 900) | `--accent` px | `--warning` px | `--role-target` px |
|---|---|---|---|
| Wave-1 spike, live view, Observatory | 1 546 | 0 | 66 |
| Lab Run, before the synthesis | 1 289 | 1 721 | 3 533 |
| Lab Run, after (hero 01) | 513 | 1 721 | 3 533 |
| Lab Field (hero 04) | 463 | 53 | 180 |

Reading: the accent itself is now scarcer than on the spike. What makes the Run screen look
golden in Observatory is the target series (the role colour is in the brass family on
purpose: BRAND 3 lists "the active target" among brass uses) and the `--warning` rule marks.
Both are charter values; the remedy is discipline, not new hexes: no other long golden fill
(the Run bar was one), warning marks only where a rule holds, and role colours only for
photometric series and role markers.

### 2.5 What is gimmicky, and what is not

- **Sections overview** (blueprints of five sections in the rail foot): a fine design
  artefact, no use at night. Keep it in the lab and the spec; do not ship it.
- **Dial tape under a scrubbed field**: useful while dragging, hidden otherwise. Keep.
- **Sliding segmented block, mode cross-fade, flip re-sort**: orientation for a layout
  change, 120-180 ms, instant under reduced motion. Keep, and nothing more.
- **Key hints while ⌘ is held**: genuinely teaches an icon-only interface. Keep with neutral
  caps (no brass).
- **Live layout cost while dragging a separator** ("Band 445 px · image 681 × 383"): cheap
  and honest about BRAND 11.1. Keep.
- **Comfortable density**: needed for reading from a step away (17 px digits are 13.8′ at
  0.6 m, functional-spaces 2.5). Keep as tokens; not a zoom.

---

## 3. Decisions on every proposal

ADOPT = promote as proposed. ADAPT = promote with the change stated. REJECT = do not ship.
"Owner" marks the rows that need decision D-n of section 10.

### 3.1 Night and spaces (UX research and the workspace)

| Proposal | Verdict | Reason and change |
|---|---|---|
| Observe task modes (Framing, Focus, Field, Run; mode bar, Alt+1-4 on `code`, suggestion chip, never automatic) | ADOPT (owner D1) | The night is a loop of different tasks, then hours of watching; one fixed layout shows rare controls and hides needed ones. Prototype verified. |
| Per-mode layouts with "modified" mark, Arrange popover, reset per mode and for all | ADOPT | Says what a reset undoes (fixes the Qt reset that did nothing, 01 P9). Keys `argos.layout.observe.<mode>.*`. |
| Task band: content per mode, size rule unchanged, one-row summary below 150 px | ADOPT (owner D1) | The 294 px band was spent on a set-once stretch for the whole night. Amends BRAND 11.1 (section 4). |
| Live layout cost while dragging a separator | ADOPT | Keeps the space rule visible. |
| Image HUD (frame chips, field state, N / E compass, arcminute scale bar, cursor readout, 64-bin mini histogram) | ADAPT (owner D6) | Chips, compass, scale bar: yes. The mini histogram only when the band does not show the levels (Focus, Field, Run). Moving the cursor readout from the status bar to the HUD changes BRAND 11.1 "one home per value" and D18. |
| Exposure check "peak, not picture" (true-length bars to 65 535, clipped pixels, sky, HFD, stars) | ADOPT | The guide's rule; peaks measured, never an OK badge. |
| Run card (state, n / N, last-frame age with observed cadence, end from cadence, next AF, end action, attention items, Pause, Stop) | ADOPT (owner D2) | One answer to "is my run fine?". Pause and Stop in Observe change README 1.4. |
| End-of-night wrap-up (tracking still on, darks and biases prefilled with time estimate, Park by hold, session folder) | ADOPT | No calibration frame exists in any of the owner's 19 session folders (functional-spaces 1.2). |
| Watch view (W; 88 / 66 / 48 / 30 px; dim 100 / 60 / 30 %; Pause by hold; only W, Esc, ?, Mod+K act) | ADAPT (owner D3) | Adopt with the synthesis fix: the attention row keeps the last-frame age and n / N. Distances to validate on a real night. |
| Attention system (rules per frame, three levels, status chip + list + Run card + Watch, Web Audio tones, Off / Soft / Normal) | ADAPT (owner D3) | Rules on the server (WS `attention` event, ack route), not in the browser; thresholds replayed on all sessions with the owner marking true and false alarms before shipping. No OS notification in v1 (README 3.2, Night Red). |
| Keep the computer awake during a run | ADAPT | Server-side first (caffeinate, systemd-inhibit, SetThreadExecutionState); `navigator.wakeLock` in Watch as a second layer. Lid-closed sleep is out of software reach; say so in the preflight. |
| Comparison workspace (candidates table with V, B−V, Δ(B−V), separation, peak, SNR, neighbours in aperture, status; row ↔ image hover; compact star card; Inspector) | ADOPT | Ensemble rules are comparisons between stars. Needs `b_minus_v` and `neighbours_in_aperture` from the server. |
| Night checklist (devices, clock, site against mount, alignment, disk, field, roles incl. check star, keep-awake, calibration, park) | ADOPT | Highest value per line of code: the site check would have caught the 61.6° error of 2026-09-25 (section 11). |
| Safe hardware patterns: server interlock `409 run_active` on mount motion during a run, one explicit "Pause the run and slew" | ADOPT (owner D2) | GoTo, park and tracking run today with no check for an active sequence. |
| Hold-to-confirm for Park and for Watch's Pause; Enter / Space open the inline confirmation | ADOPT (owner D4) | Single large target for gloves and cold trackpads; keyboard users keep a two-step path. |
| Hold-to-confirm for Stop sequence | REJECT (owner D4) | Keep the spec's ConfirmDialog (README 3.3, Q-P7 accepted): Stop ends the run and discards the exposure in progress; the dialog says what is saved. |
| Command palette (Mod+K, fed by the shortcut registry, modes, cards, settings keys, stars; disabled reasons; hardware confirms in place) | ADOPT | Keyboard path to hardware actions that have no key on purpose; teaches the shortcuts. Register W, Mod+K, Alt+1-4 in `keymap.ts` and run its conflict checker. |
| Comfortable density (tokens: readouts 20 px, key values 26 px, rows 28 px) | ADAPT (owner D7) | As a Settings › Appearance token set, never a page zoom; revisits Q-G4. |
| Review grouped by night, runs under 10 frames folded, health strip, site check repeated in the AAVSO dialog | ADOPT | Seven trial sessions on 2026-09-25; a bad stretch must show before export. |
| Device plan: ≥ 1800 px side-by-side Run layout | ADOPT later (W8) | Cheap with container queries once the modes exist. |
| Tablet Watch over the LAN with a paired token | REJECT for v1 | Needs a security review of binding the server beyond 127.0.0.1; revisit after W8. |
| Sections overview overlay | REJECT as a feature | Design artefact (kept in the lab and the spec), no use at night. |

### 3.2 Charts

| Proposal | Verdict | Reason and change |
|---|---|---|
| LightCurvePlot with linked facets (target, check with trailing band, comparison ensemble), flags by shape, newest point a static ring, three sizes | ADAPT | One component for Observe and Review. Observe's band shows target + check (two facets, D25); the ensemble facet lives in Review and the drawer's Light curve tab. Check plotted as check − catalogue V (D10). Merges the charts, workspace and research implementations. |
| TimeZoom: fit / follow / zoom kept, named by a chip; drag, wheel and pinch about the pointer; F, +/−, End; new frames never move a kept zoom | ADOPT | README 3.13. Ctrl/⌘ + wheel inside scrolling walls (Review), plain wheel in a single plot. |
| UTC / JD / BJD axis on a scale kept in unix seconds, readout with all three to 5 decimals | ADOPT | D26 without losing the zoom. BJD comes from the server (the lab's is approximate, within about 4 s). |
| Liveness on the time axis (x to now, overdue gap hatched, "no frame for …") | ADOPT | Principle 2. |
| Attention rule drawn on the chart with a draggable threshold | ADAPT | Draw the server's rule and episodes. On a live chart the line is read-only, with "Change rule…" to Settings › Alerts; a draggable handle that silently changes a running rule, or a second local threshold, would mislead. In Review the handle may be an exploratory filter labelled "view only". |
| Review plot wall with health strip, linked cursor and zoom, selected time across cells, cell menu | ADOPT | Spec 07 WF-B, D4. |
| V-curve with weighted hyperbola fit, ±1σ envelope, asymptotes, provisional vertex, verdict in words | ADOPT | 05 P9; brass only for the accepted decision. Replaces the workspace's simpler V-curve. |
| Visibility timeline (twilight as luminance steps, minimum-altitude handle, transit, Moon, planned run, frames taken, planning check) | ADOPT | With the neutral coverage fill (fixed). Low-precision lab astronomy; the server computes it with astropy (A65). |
| Histogram: keyboard B / M / W handles, clipped fractions, transfer curve, saturated count | ADOPT | The current handles are pointer-only. |
| Histogram display ramp (the exact LUT mapping as a gradient) | ADOPT (owner D11) | A legend of the image mapping is data, not decoration; BRAND 2 needs an explicit exception (section 4), as does the hatch pattern of stale and overdue states. |
| Mini-charts (sparkline, age meter, run progress, altitude arc, chip state matrix, glance tiles) | ADAPT | Sparklines and geometry in neutral inks (fixed for altitude); role colours only for photometric series. Chips converge on one `Chip` (section 6). |
| rAF-batched live append, one uPlot batch per plot per update | ADOPT | Chrome median 4.2 ms, WKWebView median 6 ms for 3 facets of 5 000-5 520 points (designer's measurement). The cost recorder stays dev-only. |
| Export hooks (TSV with UTC, JD, BJD, values, errors, flags; PNG composed from the canvases) | ADOPT | Q-G16; Tauri dialog / fs route in W8. |
| Chart tokens (`--lab-chart-*`) | ADAPT | Subset in section 5. |
| "In context" Observe › Run composition | REJECT as a second layout | Superseded by the workspace prototype: one Run layout. Its run-chip progress and frame-age chip feed the status bar design. |

### 3.3 Controls

| Proposal | Verdict | Reason and change |
|---|---|---|
| One control button (`Ctl`): ghost, secondary, primary, danger, routine stop, layout and instrument toggles; rest, hover, pressed, focus, toggled, unavailable (+ reason), busy, error, progress, hold ring, key hint | ADOPT | Merges `IconButton` and `Button` so states cannot drift; adds the states an instrument needs. |
| Time ring vocabulary (track only = hold here; arc = exact elapsed fraction, linear, butt caps; quarters under reduced motion) | ADOPT | Principle 3. |
| Tooltip with a reason line, press-to-explain on unavailable controls | ADOPT | The moment a control does nothing is when the reason is needed. Replaces `lib/components/tooltip.ts` behaviour, same timings. |
| Key hints while ⌘ / Ctrl is held alone (450 ms; cancelled by any other key) | ADAPT | Caps neutral (`--fg` on `--surface`, `--border` edge), no brass: they appear on every control at once. WebKit key-up of Meta to check (section 9). |
| Data-driven toolbar with priority overflow and counted trigger, densities M (46) and S (40) | ADAPT | Measure natural widths once (or declare them) instead of a hidden inert copy of every tool; add roving tabindex (one tab stop per toolbar). |
| Split button that shows its options | ADOPT | Capture "2.0 s", Autofocus options, Export formats. |
| Segmented with sliding block (120 ms, after the value) and manual activation for hardware, busy segment | ADOPT | Walking the filter wheel with arrows never moves it three times. |
| ScrubField: commit model and visible states (not sent, sending, applied, refused, invalid never clamped, unavailable), action mode for Go to, exposure ladder, dial tape while scrubbing | ADOPT | Fixes Qt P5, P6, P28; README 3.4. No Pointer Lock (a long scrub stops at the screen edge): acceptable. |
| Stepper with hold-to-repeat (400 ms, then 80 ms, ×10 after 1.6 s), one value sent 400 ms after release, limits named | ADOPT | |
| Slider with ticks, magnetic detents (5 px), Alt fine drag at 1/10, start mark and Esc, editable readout, wheel only when focused | ADOPT | No native range input (grey in Night Red). |
| One modifier convention (plain step, Shift ×10 or snap, Alt ×0.1, wheel only when focused, Enter / release / blur send, Esc reverts) | ADOPT | BRAND 8 amendment. |
| Focuser card: two-scale travel gauge, polled needle (never interpolated), commanded target, queued taps, Go to as action field, Stop AF with ring, Halt always | ADOPT (owner D9) | Fixes Qt P4-P7. Queued taps differ from spec 05 ("disabled while moving"). |
| Jog pad with visible dead-man (renewal age, server stop after 1 s, stalled key dashed), two axes tracked separately, J arms arrows, rate in °/s | ADOPT | With axis words on alt-az (Q-O4, fixed). The armed state keeps one brass edge (the pad); pressed keys use `--toggled-fg`. |
| HoldButton (700 ms, ring, captions for released, tapped, busy, failed; inline confirmation from the keyboard) | ADOPT | The one hold implementation. |
| Chips and attention levels | ADAPT | No triangle for "attention" (fixed). One `Chip` for device states, HUD, status bar and alerts across the product. |
| `--lab-*` control tokens | ADAPT | Subset in section 5; `--lab-accent-tint` dropped (a large tinted area breaks the brass rule, as the designer found). |
| Capture, Night Red audit and behaviour scripts | ADOPT | As CI; see 3.5. |

### 3.4 Platform techniques (stack research)

| Proposal | Verdict | Reason and change |
|---|---|---|
| Big data outside the reactive graph (typed-array columns, `$state.raw`, a version counter, `subarray` views to uPlot) | ADOPT | Reading 100 000 numbers through a `$state` proxy cost 276 ms (Chromium) and 190 ms (WebKit) against 0.5 and 2 ms raw (measured). Front-end rule. |
| uPlot markers and error bars in one Path2D per kind, culled, clipped, never `closePath` on a shared path | ADOPT | 50 000 triangles: 4.4 s with `closePath` in Chromium, 18 ms without (measured). One implementation for the three labs. |
| Stability band (trailing 15-point mean ± 1σ, native uPlot band) | ADOPT | Causal: appending never changes the past band. |
| Synced crosshair, linked zoom, zoom kept under live data | ADOPT | Merged with TimeZoom. |
| Worker statistics + WebGL2 R16UI upload + LUT texture | ADOPT | About 2-3 ms of main thread per 2 Mpx frame (measured). Check R16UI on Linux drivers first (section 9). |
| Perceptual (OKLCH) Fire and Ice LUTs | ADOPT | Old stops had lightness steps varying 21-fold. Neutral only in Night Red (D30). |
| Motion for orientation only (spring star card, ghost of previous levels, flip re-rank, linear hold fill; springing data handles rejected) | ADOPT | Codified in BRAND 9 (section 4). |
| Gesture attachments (splitter, pan / wheel / pinch / long-press, value handle) | ADOPT | One tested layer. Touch and trackpad pinch untested on hardware. |
| Container queries, subgrid, `:has()` | ADOPT | WebKitGTK 2.48+ documented; Debian trixie ships 2.52 / 2.54. |
| Popover API + anchor positioning with script fallback | ADAPT | Keep `lib/components/position.ts` the default path; enable the Popover API only after the release binary's SDK is confirmed (WKWebView enables it only for apps linked on the macOS 14+ SDK, measured). |
| Virtual table + CSS Custom Highlight API | ADOPT | 10 000 rows in 41 DOM rows. |
| Token-drawn controls only, Night Red pixel audit in CI | ADOPT | A native checkbox drew grey (115, 113, 113) in Night Red (measured). |
| Screen Wake Lock | ADAPT | Second layer behind the server-side power assertion. |
| View Transitions for section and mode switches (180 ms) | ADAPT | Only on those two switches, never on a pane being dragged or a data region; skipped under reduced motion; WebKitGTK untested. |
| Tauri: custom title bar, second window, global abort shortcut, no vibrancy | ADAPT | Custom title bar: yes (Q-G14). Second window: later (D27). A system-wide abort shortcut: owner's call in W8 (it captures a key from every other app). Vibrancy: rejected (non-red light behind the window). |

### 3.5 Tooling

| Proposal | Verdict | Reason and change |
|---|---|---|
| Four capture scripts with Night Red audits | ADAPT | Merge into one `web/scripts/capture-lab.mjs` with a shared shot format, and gate CI on `lab/synthesis/audit-png.mjs` (rules A and B with tolerance; exit 1 on failure). Audit captured originals only. |
| Frame synthesis worker (deterministic 1080 x 1920 16-bit frames, measured peaks) | ADOPT (dev only) | Reproducible screenshots and offline reviews; excluded from the production bundle. |
| Behaviour checks with real input (`behave.mjs`, 29 checks) | ADOPT | Gate the promotion of each control. |

---

## 4. BRAND.md amendments (exact text)

Apply after the owner's decisions; each block says where it goes.

**§2 Design principles.** Replace principle 2 and principle 6, and append 8 and 9:

> 2. **Calm.** No decorative gradients, glows, glass, bouncing or decorative animation.
>    Nothing moves unless the instrument moves, a value changes, or the observer changes
>    the layout. Two graded fills are data and are allowed: a display ramp that shows the
>    exact mapping of the image (LUT preview), and hard-stop hatching that marks a period
>    or a stale state.

> 6. **One vocabulary.** The same shape means the same thing on the image, in the plots,
>    in the controls and in the icons: circle = target, square = comparison, triangle =
>    check, and these three shapes mean nothing else (an attention mark is never a
>    triangle). A ring around a control is elapsed time; a dashed edge is "not current" or
>    "not yet sent"; a hollow mark is idle.

> 8. **Spaces follow the night.** Each section keeps one set of regions. Observe re-arranges
>    them in four task modes (Framing, Focus, Field, Run) and a Watch view serves the hours
>    of waiting. The observer chooses the mode; the app only suggests one.
> 9. **Liveness is always visible.** Anything live shows its age; a live time plot runs to
>    "now"; a stale value says so in words; an alert never hides the last-frame age.

**§3, row "Brass", append:**

> `--role-target` is in the brass family on purpose (the active target), so a target series
> already spends brass on a run screen: long or large fills (areas, coverage blocks,
> progress bars) never use `--accent` or a role colour; they use neutral inks.

**§4.3 Night Red, append:**

> **Audit (MUST, in CI).** Every Night Red screenshot, in Chromium and in WebKit, passes:
> (a) no pixel has G > R or B > R; (b) no pixel has max(G, B) > 8 and max(G, B) > 0.68 × R,
> with ±0.5 per channel allowed for 8-bit rounding (anti-aliased `--fg` edges over black).
> Audit captured originals, never a resampled copy: a resampling filter with negative lobes
> creates green above red on near-black edges. Tool: `web/lab/synthesis/audit-png.mjs`
> (to move to `web/scripts/`).

**§5 Typography, "Numbers" paragraph, append:**

> Thousands are grouped with U+202F NARROW NO-BREAK SPACE from 1 000 up, in every face
> (`12 450`, `65 535 ADU`): one cell wide in Plex Mono, so columns stay aligned, and never
> broken across lines. Never a comma (a decimal mark for much of Europe) or a plain space.
> Factors and products use U+00D7 (`2.5× baseline`, `20 × 10 s`), never the letter x.
> `Intl` number formatters are not used for display (they produce U+002D).

and add two rows to the formats table:

> | Integers and counts | grouped with U+202F | `12 450 steps` |
> | Factors | value + U+00D7 | `1.5× baseline` |

**§7 Icon and label rules, add rows to the table:**

> | Physical action that is hard to undo at night (Park; pause the run to slew) | Icon + label at `--control-h-l` (40 px), **hold to confirm** for `--hold-duration` with the time ring; Enter / Space open an inline two-button confirmation instead. The label never changes while held; the caption under the button does. |
> | A control that cannot act now | `aria-disabled` (still focusable), the reason in the tooltip's second line; a press shows the reason at once. |
> | An action with options | Split button: the main part acts with the options written on it (`2.0 s`); the chevron or ArrowDown opens them; choosing an option never runs the action. |

and append after the table:

> Holding ⌘ (Ctrl elsewhere) alone for 450 ms shows each control's shortcut as a neutral
> key cap where the control is; any other key cancels. The command palette (⌘K / Ctrl+K)
> lists every action with its key or its unavailable reason; a hardware action in it opens
> its confirmation and never runs on Enter alone. Jog keys show axis words on an alt-az
> mount (Alt +, Alt −, Az −, Az +) and N / S / W / E on an equatorial one (Q-O4).

**§8 States, add to the table or after it:**

> - **Error** (the last attempt failed): `--danger` outline, a 6 px `--danger` dot in the
>   top-right corner, the device's words in the tooltip and `aria-describedby`; cleared by
>   the next success.
> - **Progress** (a timed operation: exposure, autofocus sweep, export): a ring around the
>   glyph whose arc is the exact elapsed fraction, linear, butt caps, `--ring-w`; under
>   reduced motion it advances in quarters and the numbers stay exact.
> - **Pressed** adds `--pressed-inset` (a 1 px black inner top edge) to the pressed fill; no
>   scale, no bounce.
> - **Device value fields**: not sent (dashed edge, "Enter sends"), sending (spinner in the
>   unit slot), applied (with when it takes effect), refused (the device's words; Esc
>   reverts), invalid (never clamped silently), unavailable (the reason). One value per
>   commit (Enter, release, blur), never per keystroke or pixel of drag.
> - **Modifiers**, for every value control: plain = one step; Shift = ×10 or snap to ticks;
>   Alt = ×0.1; the wheel acts only on a focused control; Esc returns to the device value.
> - **Attention levels** (chips, lists, Run card, Watch), always with the word: Critical =
>   filled `--danger` disc, its sound repeats until acknowledged; Attention = upright mark
>   (a bar over a dot) in `--warning`; Info = hollow ring.

Replace the brass budget sentence with:

> Brass budget while observing: about eight marks (selected rail entry and its state dot,
> the live toggle and its ring, auto stretch, the LIVE / REC chip dot, the exposure ring,
> the black and white levels, the active target's marker and series). Run progress bars,
> coverage blocks, key-hint caps and attention marks are not brass. Count them on a live
> screenshot after any change (`audit-png.mjs --brass`).

and the control sizes sentence with:

> Control sizes: `--control-h-s` 30 px (16 px icon), `--control-h-m` 34 px (20 px icon),
> `--control-h-l` 40 px (hold-to-confirm targets, Watch), jog keys `--jog-key` 44 px,
> inputs 28 px; hit targets are never below 24 x 24 px.

**§9 Layout, density, elevation, motion.** Append to "Density":

> **Comfortable** density (Settings › Appearance) changes tokens, never the page zoom:
> readouts 20 px, key readouts 26 px, rows 28 px; toolbar, icons and image unchanged.
> **Watch** sizes: primary values 88 px, secondary 66 px, conditions 48 px, labels 30 px
> (digits of 66-83 px read from 2 m on a 13-inch 1440 x 900 screen; functional-spaces 2.5).

Replace "Motion" with:

> - **Motion** is for state changes and orientation, and is limited to this list: colour
>   state changes `--duration-fast`; popovers and panels `--duration-base` (opacity and a
>   4 px move); the segmented control's block slides `--duration-fast` after the value is
>   applied; task-mode and section switches cross-fade `--duration-base`; a table re-sort
>   uses flip for `--duration-fast`; a dragged star card settles into a corner (a spring,
>   instant while dragged); a keyboard or button zoom of a plot glides for
>   `--duration-base`.
> - **Elapsed time is linear** (rings, hold fill), never eased.
> - **Data never animates**: values, plots, handles and the image jump to the truth. Live
>   statistics are causal (trailing windows), so a point once drawn never moves.
> - `prefers-reduced-motion: reduce` sets every duration to 0 (tokens do it) except
>   `--hold-duration`, which carries information; rings then advance in quarters and the
>   spinner becomes a static arc with `aria-busy`.

**§10 Data visualisation, append:**

> - **Live plots**: the x range ends at "now". Past max(2 × cadence, cadence + 60 s) the gap
>   after the newest point is hatched and the header says "no frame for …".
> - **Zoom states** are named by a chip: Whole run, Following (the right edge on the newest
>   frame), Zoom kept. New data never moves a kept zoom; `F` fits, `End` follows.
> - The newest point wears a static ring in `--chart-highlight`, never a pulse.
> - **Rules**: a dashed `--warning` line at the server's threshold, the period where the rule
>   holds hatched from the frame where it fired, a rug on the frames over it. A live chart
>   never edits a rule.
> - **Check star**: plotted as check − catalogue V with a trailing 15-point mean ± 1σ band;
>   its rms is in the readout. Observe shows target and check as two facets on one time axis
>   (D25); the comparison ensemble facet lives in Review and in the drawer's Light curve tab.
> - **Provisional vs decided**: a fit result stays neutral and labelled "provisional" until
>   it is accepted; brass marks only the accepted decision (the autofocus position).
> - Sparklines and geometry (altitude, airmass) use neutral inks; role colours are for
>   photometric series and role markers only.

**§11.1 Use of space.** Replace the "Levels strip" bullet with:

> - **Task band (was the levels strip).** The band under the image keeps its size rule
>   (`band = centre height − drawer − centre width × frame h / w`,
>   `web/src/lib/imaging/layout.ts`), and its content follows the Observe task mode:
>   Framing = levels and the exposure check (peaks against 65 535); Focus = V-curve and HFD
>   trend; Field = comparison candidates; Run = the live light curve (target and check).
>   Below 150 px it becomes a one-row summary still as tall as the band. `H` hides it in
>   every mode. Dragging its edge overrides the height for that mode and shows the cost on
>   the image (`Band 445 px · image 681 × 383 · side margins 133 px`); "Fit to image" returns
>   to the rule. When the band does not show the levels, the image HUD carries a 64-bin mini
>   histogram with them.

and, if D6 is accepted, replace "One home per value" with:

> - **One home per value.** Frame number and exposure on the image chips; cursor X, Y,
>   value and RA / Dec on the image HUD (bottom right); the settings in use and the sensor
>   in the Camera card; mount, run and rate in the status bar.

**New §13 Attention and alerts:**

> Rules run on the server, on every frame (no new frame, HFD rise, star-count drop, too few
> comparisons, tracker lost, altitude limit, disk, run stopped on error, device lost). Each
> item has a level (§8), a short headline for Watch and the rule with its numbers for the
> list. It is shown in the status-bar attention chip (count and newest), its list
> (Acknowledge, suggested view), the Run card and Watch's first row. Sound: Web Audio tones
> (Critical 3, Attention 2, Info 1), Off / Soft / Normal, armed by a click. No OS
> notification, no flashing, no large red fill.

---

## 5. New tokens

Theme-independent unless noted; none adds a hex (black shadows only). Promote without the
`--lab-` prefix.

| Token | Value | Use | From |
|---|---|---|---|
| `--control-h-l` | 40px | hold-to-confirm targets, Watch buttons | controls |
| `--jog-key` | 44px | jog keys | controls |
| `--hold-duration` | 700ms (kept under reduced motion) | hold-to-confirm | controls, workspace |
| `--hold-drain` | 150ms (0 reduced) | ring drain after an early release | controls |
| `--repeat-delay` / `--repeat-interval` | 400ms / 80ms | stepper and tap repeat | controls |
| `--ring-w` | 1.5px | time and hold rings | controls |
| `--track-h`, `--thumb` | 4px, 14px | sliders, handles | controls |
| `--tick-minor`, `--tick-major` | 4px, 8px | slider and gauge ticks | controls |
| `--cap-h` | 16px | key caps | controls |
| `--pressed-inset` | `inset 0 1px 0 rgba(0, 0, 0, 0.4)` | pressed state | controls |
| `--readout`, `--readout-key` | 17px, 17px (Comfortable 20px, 26px) | rail readouts | workspace |
| `--row-h` | 24px (Comfortable 28px) | table and list rows | workspace |
| `--watch-xl`, `--watch-l`, `--watch-m`, `--watch-s`, `--watch-tick` | 88px, 66px, 40px, 30px, 22px | Watch | workspace |
| `--band-header-h` | 28px | task band header | workspace |
| `--splitter-hit` | 7px | hit area of 1 px separators | workspace |
| `--elev-hud` | `0 1px 0 rgba(0, 0, 0, 0.6)` | opaque chips over the image | workspace |
| `--duration-mode` | `var(--duration-base)` | mode and section cross-fade | workspace |
| `--chart-band-alpha` | 0.16 (Night Red 0.20, theme block) | bands and envelopes | charts, workspace |
| `--chart-flag-alpha` | 0.22 | rule hatch | workspace |
| `--chart-clip-alpha` | as in `src/lab/charts/lab.css` | clipped regions of the histogram | charts |
| `--chart-twilight-0` … `-4` | luminance steps of `--fg-muted` | twilight bands (Night Red safe) | charts |
| `--chart-header-h`, `--chart-toolbar-h` | 26px, 38px | plot headers and toolbars | charts |
| `--toolbar-h` | 44px (owner D8; Observe is 47 today) | section toolbar | workspace |
| `--statusbar-h` | 28px (owner D8; 32 today) | status bar | workspace |
| `--rail-min-w`, `--rail-w`, `--rail-max-w` | 360px, 400px, 580px (owner D8; 420-580 today) | right panel | workspace |

Dropped: `--lab-accent-tint` (a tinted area breaks the brass rule); `--lab-glance-l/m`
(replaced by the `--watch-*` set).

---

## 6. Components to promote, and the wave where each lands

Waves are those of `web/spec/README.md` §7. Nothing is promoted while the wave-1 team works
in `web/src/lib`; the first promotions open W2. "One implementation" rows merge code that
exists two or three times in the lab.

| Lab source | Becomes (in `web/src/lib`) | Wave | Notes |
|---|---|---|---|
| `controls/format.ts`, `charts/core/format.ts`, `workspace/model/format.ts` | `format/number.ts` (one implementation) | W2 | U+202F grouping, U+2212, U+00D7, `parseNumber` (comma or point decimal). |
| `research/tokens.ts`, `charts/core/palette.ts` | `charts/ink.ts` | W2 | Tokens resolved by the engine for canvas (handles `color(srgb …)`). |
| `controls/components/Ctl.svelte`, `Ring.svelte` | `components/Control.svelte`, `Ring.svelte` | W2 | Replaces `IconButton` and `Button`; keep them as thin wrappers during migration. |
| `controls/tip.ts`, `TipStatic.svelte` | `components/tooltip.ts` (v2) | W2 | Reason line, press-to-explain. |
| `controls/hints.svelte.ts` | `app/keyhints.svelte.ts` | W2 | Reads the W1 shortcut registry. |
| `controls/components/Chip.svelte` | extends `components/StatusBadge.svelte` | W2 | Levels, stale, HUD and bar variants; used by every lab's chips. |
| `controls/components/ScrubField.svelte`, `Stepper.svelte`, `Slider.svelte`, `values.ts` | `components/NumberField.svelte` (v2), `Stepper`, `Slider` | W2 | Settings forms need the commit model, ranges and refusals; scrubbing first used in W3. |
| `workspace/ui/Readouts.svelte` + density tokens | `components/Readouts.svelte` | W2 | Settings › Appearance › Density. |
| `workspace/overlays/CommandPalette.svelte`, `commandIndex.ts`, `model/commands.ts` | `shell/CommandPalette.svelte` | W2 (end) | Indexes the registry (W1) and settings keys (W2 config meta). |
| `controls/components/Seg.svelte` | extends `components/Segmented.svelte` | W3 | Manual activation, busy segment, sliding block. |
| `controls/components/SplitButton.svelte` | `components/SplitButton.svelte` | W3 | Capture, Autofocus. |
| `controls/components/Toolbar.svelte`, `overflow.ts` | `components/Toolbar.svelte` | W3 | Observe toolbar rebuilt from data; measure widths once; roving tabindex. |
| `controls/components/HoldButton.svelte` | `components/HoldButton.svelte` | W3 | Park. Replaces `workspace/ui/HoldButton.svelte` and `hold.ts`. |
| `controls/instruments/FocuserControl.svelte`, `FocuserGauge.svelte` | `imaging/FocuserCard.svelte` | W3 | Server A15 / A16. |
| `controls/instruments/JogPad.svelte`, `jog.ts` | `imaging/JogPad.svelte` | W3 | Server dead-man A10; `alignment` from `MountState`. |
| `workspace/model/layout.ts`, `observe/ModeBar.svelte`, `ArrangePopover.svelte`, `Band.svelte` | `imaging/modes/*`, extends `PanelsPopover` | W3 | Framing and Focus in W3; Field in W4; Run in W5 / W6. `bandLayout()` wraps `layout.ts` unchanged. |
| `research/space/splitter.ts`, `frame/` gestures | `app/attachments/*` | W3 | Rail, band and drawer separators. |
| `workspace/observe/Viewer.svelte` HUD parts | `viewer/Hud.svelte` | W3 (chips, cursor), W4 (compass, scale bar) | Screen-space overlay; keeps rotation display-only. |
| `workspace/observe/bands/FramingBand.svelte` (exposure check) | `imaging/ExposureCheck.svelte` | W3 | Peaks from the frame worker. |
| `charts/charts/VCurve.svelte`, `core/fit.ts` | `charts/VCurvePlot.svelte` | W3 | Fit from the server's autofocus worker in the app. |
| `charts/charts/ConditionsTimeline.svelte`, `workspace/charts/Trend.svelte` | `charts/ConditionsTimeline.svelte` (one implementation) | W3 | D6. |
| `charts/charts/HistogramStretch.svelte` | extends `imaging/Histogram.svelte` | W3 | Keyboard handles, clipped fractions, ramp (D11). |
| `research/frame/*` (worker stats, R16UI, `gl.ts` LUTs) | `viewer/*` | W3 (stats), W4 (palettes) | Check WebKitGTK first. |
| `charts/mini/*` (Sparkline, AgeMeter, RunProgress), `workspace/charts/Spark.svelte` | `charts/mini/*` (one implementation) | W3 (conditions), W6 (run) | Neutral inks. |
| `research/table/*` (`rowWindow`, highlight) | extends `components/Table` | W4 | Variables and Gaia lists; Frames in W7. |
| `workspace/observe/bands/FieldBand.svelte`, `cards/InspectorCard.svelte`, `StarCard.svelte` | `imaging/field/*` | W4 (table, card), W5 (live status) | Server fields of section 7. |
| `charts/charts/LightCurve.svelte`, `core/uplot/{markers,zoom,axes,overlays}.ts`, `research/curve/{plugins,band,handle}.ts`, `workspace/charts/{LightCurve,plugins,axes}` | `charts/LightCurvePlot.svelte` + `charts/uplot/*` (one implementation) | W5 | The Run band and the drawer tab use the same component. |
| `workspace/observe/cards/RunCard.svelte` | `imaging/RunCard.svelte` | W6 | Sequence events A63. |
| `workspace/overlays/WatchView.svelte` | `shell/Watch.svelte` | W6 | With the pulse fix. |
| `workspace/overlays/AttentionPopover.svelte`, `model/sound.ts` (`model/rules.ts` as the server's test oracle) | `shell/attention/*` | W6 | Rules move to the server. |
| `charts/charts/VisibilityTimeline.svelte`, `sim/astro.ts` (tests only) | `charts/VisibilityTimeline.svelte` | W6 | Server A65 computes the geometry. |
| `charts/charts/PlotWall.svelte`, `core/export.ts` | `review/PlotWall.svelte`, `charts/export.ts` | W7 | Health strip, cell menu; Tauri export route W8. |
| `workspace/model/frame.worker.ts` | `web/scripts/` or `src/dev/` (dev only) | W3 | Never in the production bundle. |
| Capture scripts, `lab/synthesis/audit-png.mjs`, `controls/behave.mjs` | `web/scripts/` | W2 | CI gate. |
| `workspace/overview/*` | stays in the lab | — | Design artefact. |
| `workspace/ui/LabIcon.svelte` (`lab-watch`, `lab-attention`, `lab-inspector`) | `icons/watch.svg`, `attention.svg`, `inspector.svg` via `icon-inventory.json` | before W3 | Redrawn or reviewed under BRAND 6.10 at 16 px; not used as inline SVG. |

Small changes the wave-1 team can take when convenient (from the workspace report): a
`summary` slot on `Card` when folded; text helpers that always set `textAlign` and
`textBaseline` on canvas (uPlot leaves `center` on the context); W, Mod+K and Alt+1-4 in
`keymap.ts` through its conflict checker. The proposed "glyph snippet on IconButton" is
rejected: new glyphs go through the inventory.

---

## 7. Server and API work implied

From functional-spaces C15 and the labs; none of it exists today.

- WS `attention` event, `POST /api/attention/{id}/ack`, rules evaluated per frame, tracker
  fields in `frame_metrics`.
- Mount-motion interlock: `409 run_active` on GoTo, Centre, Park, tracking off, jog and Sync
  while a sequence runs, with a `pause_run` option for "Pause the run and slew".
- Keep-awake while a run is active (OS assertions), reported in the status record.
- Site check in the status record: altitude and azimuth computed from the Settings site and
  the clock against what the mount reports; alert above 5°.
- Candidates: `b_minus_v`, `neighbours_in_aperture`; leave-one-out status per comparison.
- Preflight: disk needed against free space, calibration counts per night, the lid note.
- BJD_TDB per frame in the photometry stream (the lab approximates it).

---

## 8. Dependencies

**No new npm dependency is proposed.** Every prototype uses Svelte 5.57, uPlot 1.6.32 and
the platform (Canvas, WebGL2, SVG, CSS, Web Audio, workers). The research catalogue
(`lab/research/stack-capabilities.md` §13) lists what was considered and why it was not
needed (a virtualisation library, Floating UI, culori, a gesture library).

Tauri plugins, for W8 only, not npm packages of the web UI: `tauri-plugin-window-state`
(already in the spec), `tauri-plugin-global-shortcut` (only if the owner wants a system-wide
abort), `tauri-plugin-notification` (rejected for v1). Their licences and sizes were not
verified in this synthesis.

---

## 9. WebKit risks and how to check them

| Risk | Where it bites | Status | How to check |
|---|---|---|---|
| Popover API only for apps linked on the macOS 14+ SDK | menus, popovers if the Popover API path is used | measured on WKWebView | Keep `position.ts` as the default; on the release binary run `vtool -show-build` and record the SDK. |
| WebGL2 R16UI textures on Linux GPU drivers | the image viewer | untested on WebKitGTK | Tauri dev build on Debian trixie (WebKitGTK 2.52 / 2.54): open `lab/research.html?demo=frame`, then the workspace with live frames. |
| CSS feature floor | anchor positioning 2.50, `field-sizing` and `scrollbar-color` 2.52 on WebKitGTK | documented from WebKit flags | Plan for 2.50; keep the `::-webkit-scrollbar` fallback; record `lab/research.html?demo=support` into `recorded.json`. |
| Web Audio arming (autoplay policy) | attention sounds | untested in WKWebView and WebKitGTK | Arm by a click; play each level in both engines; check it survives the display sleeping. |
| Screen Wake Lock | Watch | granted in WKWebView (probed), untested on WebKitGTK | Second layer only; the server assertion is the guarantee. |
| Meta key-up delivery while ⌘ is held | key hints | Chrome only | Drive held-⌘ input in WKWebView (the probe can send events); hints must clear on blur. |
| Trackpad pinch (WebKit `GestureEvent` vs ctrl+wheel), touch | viewer and plot zoom | mouse and wheel only | Real MacBook trackpad and a touch screen; uPlot's own drag-zoom listens to mouse events only. |
| View Transitions | mode and section switch | WKWebView yes, WebKitGTK untested | Instant fallback is acceptable; screenshots show end states only. |
| Timer resolution (1 ms) | benchmarks | known | Read WebKit's sub-millisecond numbers as upper bounds. |
| `Intl` hyphen-minus, `<input type=number>` locale (`0,0004` in Chrome) | numbers | measured | Formatters of `format/number.ts`; text inputs with `inputmode="decimal"`. |
| Night Red in WebKit renders | every screen | WKWebView renders audited by the designers | Audit 2x originals with `audit-png.mjs`, never downscaled copies. |
| WebView2 (Windows) | everything | untested; Chrome 156 stands in | One pass of the four labs' capture in a Tauri dev build on Windows before W8. |

---

## 10. Decisions for the owner

Each with art direction's recommendation.

| # | Decision | Recommendation |
|---|---|---|
| D1 | Observe task modes (Framing, Focus, Field, Run) and a task band whose content follows the mode (amends BRAND 11.1). | **Yes.** Names as in the UX research (the brief's "Photometry / Monitoring" are covered by Field and Run). |
| D2 | Run controls in Observe (Run card with Pause and Stop) and a server interlock on mount motion during a run, with one explicit "Pause the run and slew". | **Yes**, both; the interlock is the safety, the card is the convenience. |
| D3 | Watch view, attention rules on the server with sound, no OS notification in v1. | **Yes**; thresholds replayed on every session with you marking true and false alarms before release. |
| D4 | Confirmation forms: Park = 700 ms hold with ring (Enter opens the inline confirmation); Stop sequence = the spec's dialog. | **Yes** as stated. |
| D5 | Thousands grouping in BRAND 5: U+202F narrow no-break space; U+00D7 for factors. | **Yes** (applied in the lab). |
| D6 | Cursor readout (X, Y, value, RA / Dec) on the image HUD instead of the status bar. | **Yes**: it sits where the eye is and frees the status bar for mount and run. |
| D7 | Comfortable density as a token set in Settings › Appearance (revisits Q-G4 "no UI scale"). | **Yes**; not a zoom, the image keeps its size. |
| D8 | Frame metrics: toolbar 44 px (47 on Observe today), status bar 28 px (32), right panel 360-580 px with 400 by default (420-580). | **Yes**: at 1440 x 900 the image gains 20 px of width (927 → 947 px, about 11 px of height, since the rotated frame fills the width) and the band 7 px. |
| D9 | Focuser taps during a move: queued and sent as one move (shown "+300 queued"), instead of disabled. | **Queued**: taps are never lost, and no Move is sent while moving. |
| D10 | Check star plotted as check − catalogue V everywhere (offset and scatter), not Δ from its median. | **Yes**: one definition, the offset is itself a check. |
| D11 | BRAND 2 exception for data ramps (LUT preview) and hatching. | **Yes**, worded as in section 4. |

---

## 11. Not design, but urgent

From the UX research, on the owner's own files (read-only, aggregated):

- **Wrong site on 2026-09-25.** In session `20260925T200453Z_RR_Lyr` the Settings site
  (FITS `SITELAT` / `SITELONG`) disagrees with the mount's reported altitude by 61.6° at
  20:05 UTC (astropy recomputation; the two earlier nights agree within 2.1°). The
  photometry airmass (4.09 to 1.51) and any AAVSO `AMASS` exported from that run are wrong.
  Check Settings › Observer & site before the next export.
- In the same run HFD rose from about 6 to 17 px while the FWHM column stayed at
  2.16-2.19 px: the FWHM measurement may not track defocus (`argos/core/imaging/metrics.py`).
- No check star was assigned in any of the three main runs; D25 and the AAVSO `KNAME`
  column rely on one.

---

## 12. Limits of this synthesis

- Everything is a prototype on synthetic data. The RR Lyr night replays the totals of a real
  run; it is not the owner's data. Hardware is simulated; the server routes these screens
  need (A10, A15-A17, A37, A54-A55, A63, A65, A69 and section 7) mostly do not exist.
- Interactions were exercised in Chrome 156 only; WKWebView renders are static. WebKitGTK,
  WebView2, touch, trackpad pinch and screen readers are untested. Audio was not heard
  (headless has no output).
- Reading distances (2 m Watch), glance frequency and hold-to-confirm with gloves are
  assumptions to validate on a real night (functional-spaces §7 gives the protocol).
- The brass counts are indicative (nearest-colour counting without anti-aliased edges).
- The designers' screenshot folders predate the fixes of section 2.3 (their captions
  describe the earlier state); the shared gallery `screenshots/index.html` was not
  regenerated (`python web/scripts/build_screenshot_gallery.py`).
- `lab/workspace` imports research pieces (`tokens.ts`, `curve/band.ts`, `curve/plugins.ts`,
  `space/splitter.ts`) read-only: removing the research lab breaks it until they are
  promoted.
- The lab's Vitest tests live under `src/` and run in the project's `npm test`
  (74 tests in `src/lab`, all passing).
