# Argos — UI / UX Design

> *How the application is presented to the user: window layout, workflow,
> navigation, panels. This is the information-architecture spec. It is the
> contract the UI code implements — agreed on paper first, then built screen by
> screen.*
>
> Companion docs: `ARCHITECTURE.md` (code layers), `capture_panel.md` (the
> photometry science pipeline), `acquisition_sequence.md` (sequence model),
> `photometry_plan.md` (science roadmap). This document owns *presentation*; those
> own *logic*.

Status: **draft v1** — direction agreed, screens specified, not yet implemented.

---

## 0. The problem this fixes

The current app puts almost the whole night into one screen (`ImagingPage`) with
a right rail of six tabs — `Capture / Sequence / Mount / Focus / Filter /
Display`. Those six tabs mix **three unrelated axes**:

- equipment (Mount, Focus, Filter),
- activity (Capture, Sequence),
- image appearance (Display).

The user has to hunt across tabs that are not conceptually parallel, there is no
sense of *where you are in the night*, and the photometry workflow — the entire
point of Argos — lives in detached floating windows, outside the main flow.

This document replaces that with a **workflow-ordered shell**: one screen per
phase of an observing night, each doing exactly one job, with the heavy and
occasional tasks moved to **companion windows** on a second monitor.

---

## 1. Design philosophy

Five principles. Every layout decision in this document is justified by one of
them.

1. **The navigation is the workflow.** The left rail lists the phases of a
   photometry night, top to bottom, in the order they happen. Reading the rail
   *is* reading the procedure. (Borrowed directly from NINA, whose tab rail runs
   `Equipment -> Sky Atlas -> Framing -> Sequencer -> Imaging`.)

2. **One screen, one job.** Each rail entry is a full-screen context that does a
   single thing. When you are framing, you frame; you do not configure a focuser.
   If a screen needs the word "and" to describe it, it is doing too much.

3. **The image is the hero.** On every screen that shows a frame, the image gets
   the space and the visual weight. Controls are secondary, quiet, and pushed to
   the edges.

4. **Simple by default, advanced on request (progressive disclosure).** The
   common path is visible with nothing extra. Expert controls (gamma, debayer
   mode, fine aperture parameters) live behind a collapsed `Advanced` section. A
   beginner never sees them; a pro expands them once and they are remembered.

5. **The main window stays uncluttered; heavy work pops out.** Occasional,
   focused tasks (picking comparison stars, post-session analysis) open as
   **companion windows**, ideally on a second monitor. This keeps the primary
   window calm and uses the two-screen setup the way an observatory actually
   works.

### The decision method (how to place any new element)

When you add anything to the UI, answer three questions:

1. **Which phase of the night does it serve?** -> it lives on that rail screen.
2. **Permanent or occasional?** Permanent / glanced-at constantly -> always
   visible (a strip or status bar). Occasional / focused -> a companion window or
   a dialog.
3. **A setting you freeze, or a live value you watch?** Setting -> collapsed
   under `Advanced` or in Settings. Live value -> prominent.

### The one-axis rule

> A container (a tab strip, a rail, a menu, a toolbar) groups items of **one**
> nature only. Never equipment + activity + appearance in the same row.

This single rule is what the current six-tab rail violates, and fixing it is most
of the redesign.

---

## 2. The shell

```
+------+-------------------------------------------------------------+
| RAIL |  STATUS BAR  (devices o o o o | tracking | current action)  |
|      +-------------------------------------------------------------+
|      |                                                             |
|      |                                                             |
|  ..  |                   ACTIVE SCREEN                             |
|      |              (swaps with the rail selection)                |
|      |                                                             |
|      |                                                             |
+------+-------------------------------------------------------------+
```

### 2.1 The workflow rail (left)

A vertical rail of icon + label buttons, mutually exclusive, accent highlight on
the active one. Reuses the existing `Sidebar` widget; only the entries change.

```
  Connect
  Target
  Focus
  Photometry
  Capture
  Analyze
  ----------
  Settings
```

Order = chronology of a night. `Settings` is separated at the bottom because it
is not a phase — it is a destination you visit out of band.

The rail is **not** a wizard: any entry is clickable at any time. We do not lock
steps. But a subtle **next-step hint** (a quiet accent dot on the next logical
phase, no blinking) nudges a new user forward. The existing `Sidebar.pulse()`
hook is the place for this; keep it calm (the blink was rightly removed).

Rationale for the phase list comes from the user's own workflow: the night is
**linear and hands-off** — once focus is locked you do not touch it again
(refocusing mid-run would shift FWHM and flux and corrupt the photometry). That
is why `Focus` is a distinct, early, finishable phase, and why `Capture` below is
a *monitoring* screen rather than a control panel.

### 2.2 The status bar (top, permanent)

Always visible, on every screen. Reuses `TopStatusBar`. Shows:

- four device dots — Mount / Camera / Filter / Focuser — green connected, grey
  not (clicking a grey dot jumps to `Connect`);
- tracking state;
- the current action ("Slewing", "Solving", "Capturing 12/40", "Idle").

This is the user's permanent "what is the system doing right now" line. It is
already implemented and correct — keep it.

### 2.3 Companion windows

Two heavy tasks open as separate top-level windows (the user explicitly prefers
pop-outs over a saturated main window, and runs two monitors):

- **Photometry Setup** — pick target / comparison / check stars and apertures on
  the solved field. (Today: `PhotometrySetupWindow`.)
- **Analyze** — post-session light-curve vetting and AAVSO export, plus the
  standalone FITS inspector. (Today: `AnalysisWindow` / `PhotometryWindow`.)

Plus small modal dialogs for rare manual actions (`ManualControlDialog` for
jogging). See section 4.

### 2.4 The menu bar

Keep it thin. Menus are for things that have **no natural home on a screen**:

- **File** — Open FITS..., Open session folder..., Quit.
- **View** — jump to each phase (F1..F7), Reset window layout.
- **Help** — About, documentation link.

No feature should be reachable *only* from a menu. Menus are shortcuts, not the
primary surface.

---

## 3. Screens, one by one

Each screen below specifies: its single **job**, **when** you are there, the
**layout** (with an ASCII wireframe), the **components** (mapped to widgets that
already exist), the **controls**, the **next-step** affordance, what is hidden
under **Advanced**, and the **NINA** reference.

A common anatomy applies to every screen with a frame: a thin **toolbar** on top
(image display controls), the **image hero** filling the centre, a quiet **stats
strip** under it, and a **context panel** on the right scoped to that one phase.

---

### 3.1 Connect

**Job.** Bring the hardware and Stellarium online. Nothing else.

**When.** Start of every session.

**Layout.**

```
+----------------------------------------------------------+
|  Devices                                                  |
|   +--------------------------------------------------+    |
|   | Mount     [ Seestar @ 10.0.0.1:5555 v]  [Connect]|    |
|   |           status: connected  -  tracking off     |    |
|   +--------------------------------------------------+    |
|   | Camera    [ Seestar v]                  [Connect]|    |
|   | Filter    [ Seestar v]                  [Connect]|    |
|   | Focuser   [ Seestar v]                  [Connect]|    |
|   +--------------------------------------------------+    |
|   [ Discover ]                    [ Connect all ]         |
|                                                          |
|  Stellarium                                              |
|   +--------------------------------------------------+    |
|   | Server [ 127.0.0.1 : 10001 ]   [Start]  0 clients|    |
|   +--------------------------------------------------+    |
+----------------------------------------------------------+
```

**Components.** Reuses `ConnectionPage`, `StellariumCard`. The key change is
**constant equipment anatomy**: every device row is identical —
`[chooser] [Connect] [status line]`. Learn one, know all four. (Today the rows
differ; standardise them.)

**Controls.** Per-device Connect/Disconnect; Discover (UDP scan,
`DiscoveryWorker`); Connect all; Stellarium Start/Stop.

**Next step.** Once Mount + Camera are connected, hint `Target`.

**Advanced.** Manual IP/port entry, Alpaca device numbers, discovery timeout.

**NINA reference.** NINA's Equipment tab with one sub-panel per device, each a
`[chooser][Connect][info]` block. We collapse NINA's many device types to the
four the Seestar exposes and drop guider/rotator/weather entirely.

---

### 3.2 Target

**Job.** Put the right star in the centre of the frame, confirmed by a plate
solve, and confirm the field is worth observing tonight.

**When.** After connecting, once per target.

**Layout.**

```
+--------------------------------------------+---------------+
| [toolbar: stretch  channel]                | TARGET        |
|                                            |  Name  RR Lyr |
|                                            |  RA  19 25 28 |
|              IMAGE (live, hero)            |  Dec +42 47   |
|              with solved overlay           |  ----         |
|              + center reticle              |  Alt   58 deg |
|                                            |  Airmass 1.18 |
|                                            |  Transit 23:40|
|                                            |  Moon sep 71  |
|  solved: yes   offset 12"  scale 3.74"/px  |  ----         |
+--------------------------------------------+  [ Slew ]     |
|  RA/Dec readout - tracking                 |  [ Solve ]    |
|                                            |  [ Center ]   |
+--------------------------------------------+---------------+
```

**Components.** `FitsViewer` (hero) + solved-field overlay (`OverlayBar` to toggle
grid/stars), `MountDock` condensed into the right panel, `ImageToolbar`. The
right panel adds a **target summary card** driven by `sky_geometry`
(altitude, airmass, transit time, Moon separation) — new, small, high value.

**Controls.** Target normally arrives from Stellarium (select object, Ctrl+1);
this screen exposes Slew, Solve (`SolveWorker` / `AstrometryController`), and
Center (solve -> sync/nudge -> re-solve until the offset is small).

**Next step.** Once the solve offset is small, hint `Focus`.

**Advanced.** Solver search radius, downsample, max stars (`astrometry_settings`);
sync vs nudge centering strategy.

**NINA reference.** NINA's Framing Assistant + the target info from Sky Atlas
(altitude curve, transit, Moon). We keep the actionable numbers (airmass,
transit, Moon separation) because they gate photometric quality, and drop the
mosaic planner and the sky survey background.

---

### 3.3 Focus

**Job.** Reach and **lock** best focus. After this you do not touch it.

**When.** Once, after centering, before capture.

**Layout.**

```
+--------------------------------------------+---------------+
|                                            | FOCUS         |
|                                            |  Position 4120|
|            IMAGE (live, hero)              |  HFD    2.04  |
|         with HFD on detected stars         |  ----         |
|                                            |  V-curve:     |
|                                            |   \         / |
|                                            |    \       /  |
|                                            |     \_____/   |
|   HFD 2.04   Stars 240                     |  best @ 4120  |
+--------------------------------------------+  ----         |
|                                            |  [ Auto-focus]|
|                                            |  [ - ] [ + ]  |
+--------------------------------------------+---------------+
```

**Components.** `FitsViewer` (hero), `FocuserDock` (condensed: position, nudge),
a **V-curve plot** (the autofocus run, `AutofocusWorker` output — likely a new
small pyqtgraph panel), live HFD from `metrics`.

**Controls.** Auto-focus (runs the V-curve sweep and parks at the parabola
minimum); manual +/- nudge; a clear "focus locked at NNNN" confirmation.

**Next step.** After a successful auto-focus, hint `Photometry`.

**Advanced.** Step size, sweep range, samples per point, backlash.

**NINA reference.** NINA's AutoFocus panel with the HFR V-curve and the fitted
minimum. We mirror it closely; this is a solved problem and NINA's presentation
is the standard.

---

### 3.4 Photometry

**Job.** Define the science: which star is the **target**, which are
**comparison**, which is the **check**, and the **aperture** for each. This is
what makes Argos a photometer rather than a camera app — so it is a first-class
phase, not a detached window buried off the imaging screen.

**When.** Once per target, after focus, before the run.

**Layout (main screen — overview and launch).**

```
+--------------------------------------------+---------------+
|                                            | PHOTOMETRY    |
|        SOLVED FIELD (hero)                 |  Target RR Lyr|
|        T = target (boxed)                  |  Comparisons 5|
|        C1..C5 = comparisons                |  Check    1   |
|        K = check                           |  ----         |
|        catalog (VSX/VSP) overlay           |  Aperture     |
|                                            |   r=6  in=10   |
|                                            |   out=15 px    |
|                                            |  ----         |
+--------------------------------------------+  [ Pick stars]|
|  catalog loaded: VSP chart X28401          |  [ Auto comp ]|
+--------------------------------------------+---------------+
```

`[Pick stars]` opens the **Photometry Setup companion window** (section 4.1) where
the detailed clicking happens — so the main screen stays an overview, and the
fiddly work is on the second monitor.

**Components.** `FitsViewer` + catalog overlay (VSX/VSP via `CatalogWorker`),
`target_table` / `comparison_table`, the existing `PhotometrySetupWindow` becomes
the companion. Aperture preview from `photometry/aperture.py`.

**Controls.** Pick stars (-> companion), Auto-select comparisons
(`catalog/photometry.py` ranks by magnitude / colour / separation), set apertures.

**Next step.** Once a target + at least one comparison are defined, hint
`Capture`.

**Advanced.** Aperture vs annulus radii, comparison selection weights, magnitude
and colour limits, ensemble vs single-comp mode.

**NINA reference.** NINA has no native differential-photometry star roles — this
is Argos-specific and your differentiator. The interaction model (click a
detected star, assign a role, see it tabulated) is the new ground to get right;
see `capture_panel.md` and `photometry_plan.md` for the science contract.

---

### 3.5 Capture

**Job.** Run the sequence and let the user **watch it stay healthy**. Because the
night is hands-off, this is a **monitoring** screen, not a control surface. The
only controls are Start / Pause / Stop.

**When.** The main event — most of the night is spent here.

**Layout.**

```
+--------------------------------------------+----------------+
| [toolbar: stretch  channel]                | SEQUENCE       |
|                                            |  Run 12 / 40   |
|                                            |  ETA 18 min    |
|           IMAGE (latest frame, hero)       |  step: Light   |
|                                            |   10s  LP  g80 |
|                                            |  ------         |
|                                            | STABILITY      |
|                                            |  HFD  2.1  ok  |
|   HFD 2.1   Stars 240   SNR 180            |  SNR  180  ok  |
+--------------------------------------------+  bg   stable   |
|  LIGHT CURVE (live)   . . .^. . .^. . .    |  ------         |
|                                            | [Start][Pause] |
|  session log ......................        | [   Stop    ]  |
+--------------------------------------------+----------------+
```

**Components.** `FitsViewer` (latest saved frame), `SequencePanel` condensed to a
**progress** view (run N/total, ETA, current step), a **stability** block
(FWHM/HFD, SNR, Max ADU (saturation watch), background/skyglow and tracking error from `MetricsPanel` — the question it answers is
"is the run still good", not "let me tune"), the **live light-curve panel**
(`lightcurve_panel`, fed by `photometry/session.py` as solved frames arrive),
`LogPanel` along the bottom. Runtime is `SequenceWorker` +
`LivePreviewWorker`/`PreviewProcessor`.

**Controls.** Start, Pause/Resume, Stop. Nothing else by default — deliberately.
Editing the plan happens before the run (a `[Edit plan]` link opens the sequence
editor; loading/saving plans as presets is in that editor, reusing the
`SequencePlan` model that already serialises).

**Next step.** On completion, hint `Analyze`.

**Advanced.** Autofocus-every-N and on-filter-change triggers (kept in the model
for completeness but off by default, consistent with "do not refocus mid-run");
dither (Seestar has no guiding — disabled, shown greyed with a tooltip).

**NINA reference.** NINA's Imaging tab is a fully dockable cockpit. We
deliberately **do not** copy the free dock layout — it is heavy to build and easy
to turn into a mess. Instead we take NINA's *content* (image, sequence progress,
HFR history, statistics) and fix it into a calm, non-rearrangeable layout, with a
photometry-specific addition NINA lacks: the live light curve.

---

### 3.6 Analyze

**Job.** After the run (or on any saved session), inspect the light curve, reject
bad points, and export AAVSO-format photometry. Also the standalone FITS
inspector for any single frame.

**When.** End of session, or any time on archived data. Opens as a **companion
window** so you can analyse last night while tonight's run continues.

**Layout (companion window).**

```
+-------------------------------------------------------------+
|  Session  RR_Lyr_2026-06-18      [ Export AAVSO ]  [ CSV ]   |
+----------------------------------+--------------------------+
|  LIGHT CURVE                     |  FRAME / MEASUREMENTS     |
|     .  . .^. .  .^ .  .           |  JD       2460xxx.71     |
|    .                . .           |  target   12.840 +/-0.01 |
|   click a point -> its frame      |  comp ens 11.20          |
|                                  |  airmass  1.21           |
|  [x] show rejected               |  HFD 2.1  SNR 180        |
+----------------------------------+--------------------------+
|  thumbnail strip of frames .... [reject] [keep]             |
+-------------------------------------------------------------+
```

**Components.** `AnalysisWindow` / `PhotometryWindow`, `lightcurve_panel`,
`comparison_table`, `FitsViewer` for the selected frame. Export via
`photometry/lightcurve.py` (AAVSO format) and `core/imaging` readers.

**Controls.** Click a light-curve point to see its frame and per-star
measurements; reject/keep points; toggle rejected; Export AAVSO / CSV.

**Diagnostics and ensemble — from VPhot / AstroImageJ, the science standard.**
The light curve never stands alone. Show the **check-star light curve** beside it
— its scatter is the de-facto error estimate, the "conscience" of the dataset —
plus diagnostic co-plots: **SNR, airmass, FWHM, Max ADU (saturation), skyglow,
tracking error**, so the observer can see *why* a point is bad. Let the user
**toggle each comparison in or out of the ensemble** and recompute instantly (a
"drop one comparison at a time" helper finds the bad comp). Outlier removal is
**direct and reversible on the plot** (click to reject, click again to restore) —
never silent sigma-clipping. Export is **one-click AAVSO Extended Format** (ready
to submit to WebObs unchanged) plus raw CSV.

**NINA reference.** NINA defers post-processing to PixInsight/Siril and has no
photometry analysis. This screen is Argos-specific; the model to imitate is a
focused desktop analysis tool (one curve, one frame, clear reject/keep), not a
general image processor.

---

### 3.7 Settings

**Job.** Everything you set once and forget: observer identity and site
coordinates, file paths and folder structure, astrometry defaults, catalog
preferences, appearance/theme, language.

**When.** Out of band; rarely during a session.

**Layout.** Reuses `ConfigurationPage`. Group into a small set of sub-sections
(one axis per group, per the one-axis rule): **Observer & Site**, **Files &
Folders**, **Astrometry**, **Photometry defaults**, **Appearance**. Settings that
also appear as `Advanced` on a screen read and write the same `Config` keys — the
screen's Advanced block is just a shortcut to the relevant setting.

**NINA reference.** NINA's Options tab with sub-tabs. Same idea, fewer groups.

---

## 4. Companion windows (detail)

### 4.1 Photometry Setup

Opened from the Photometry screen via `[Pick stars]`. Single job: assign roles
and apertures by clicking the solved field.

```
+---------------------------------------------------------+
|  Solved field - click a detected star to assign a role  |
|                                                         |
|     o  o      (T)        o    o   (C2)                   |
|        (C1)        o          (K)        o              |
|                                                         |
+---------------------------------------------------------+
|  Star  | Role        | Mag   | B-V  | Sep   | Aperture  |
|  0431  | TARGET      | 12.8  | 0.31 |  -    |  r=6      |
|  0218  | comparison  | 11.2  | 0.28 | 4.1'  |  r=6      |
|  ...                                                    |
+---------------------------------------------------------+
|  [ Auto-select comparisons ]      [ Apply ]  [ Close ]  |
+---------------------------------------------------------+
```

**Interaction model — the AstroImageJ standard. Do not reinvent it.** Click the
target first: it gets a green aperture labelled `T1`. Click each comparison: red
apertures `C2, C3, ...`. Click the check star: `K`. Right-click finalises and the
ensemble is computed. On later frames apertures re-centroid automatically and halt
if a star drifts beyond its aperture (then the user re-picks). A side table
mirrors every aperture — the star is always chosen on the *picture*, never blind
in a table. This is exactly what AstroImageJ, VPhot and C-Munipack do; advanced
users already know it. Reuses `StarInfoCard`, `target_table`, `comparison_table`,
and the existing `PhotometrySetupWindow` logic.

**Reusable field sequence — the VPhot idea, high value for a repeat observer.**
The chosen target/comparison/check set for a field is saved (it already persists
via `core/catalog/targets.py::TargetSet`). On a return night, after the plate
solve, Argos re-matches the saved set to the catalog automatically — the user
confirms instead of re-picking. This is what makes a hands-off, same-targets
observer fast.

### 4.2 Analyze

Specified as screen 3.6; it is implemented as a companion window so it can run
concurrently with an active capture on the other monitor.

### 4.3 Manual Control (modal dialog)

`ManualControlDialog` — direction-pad jogging at three speeds. Rare, occasional,
so it stays a small modal opened from the Target screen, not a permanent panel.

---

## 5. Persistent elements

- **Status bar** (top, every screen): device dots, tracking, current action.
  Already implemented (`TopStatusBar`).
- **Session log** (`LogPanel`): visible on Capture; reachable elsewhere via View.
- **Toasts**: transient one-line confirmations for discrete events ("Solved",
  "Focus locked", "Sequence complete"). Bottom-of-window, auto-dismiss. (The
  status bar's `showMessage` already does a basic version.)

---

## 6. Visual style guide

The theme is already good (`theme.py` equilux dark, `design.py` spacing tokens,
Feather line icons, no emoji). Four rules make it read as "pro" without extra
effort:

1. **Group with space, not borders.** Whitespace separates groups; reserve boxes
   and rules for genuine containers. Use `design.SPACING_*` consistently.
2. **One accent colour.** `theme.ACCENT` marks the active and the actionable.
   Everything else is greyscale. Resist a second accent.
3. **Two type sizes, two weights.** A label size and a value size; regular and
   medium. That is enough hierarchy. Numbers the user reads at a glance
   (`design.MetricLabel`) get the larger/medium treatment.
4. **The image is the hero.** It gets the stretch factor and the contrast; panels
   are quiet (`SURFACE_*`), thin, and edge-aligned.

Icons: Feather SVG only, recoloured per state (muted / hover / accent). No emoji,
anywhere — including in code and logs.

---

## 7. What we take from NINA, and what we drop

**Take:** the workflow-ordered navigation rail; one screen per job; constant
equipment-panel anatomy; the autofocus V-curve presentation; sequence
progress/ETA; target altitude/airmass/transit info; progressive disclosure
(simple vs advanced); a persistent status line.

**Drop (on purpose, to stay simple and maintainable):** the fully dockable
free-form Imaging workspace; the MEF plugin system; guiding/dithering and the
guider graph (no guiding on Seestar); rotator/weather/dome device types; the
mosaic planner; the flat wizard's full complexity. None of these serve a Seestar
photometry user, and each adds surface area we cannot afford to maintain.

**Add (NINA has no equivalent):** the Photometry phase (target/comparison/check
roles + apertures), the live light curve on Capture, and the Analyze window with
AAVSO export. This is the science layer that defines Argos. Its interaction model
is **not** invented here: it follows AstroImageJ (click-to-place `T1`/`C2`/`C3`,
live ensemble toggle, in-plot reversible outlier removal) and VPhot (reusable
per-field sequences, check-star-as-error discipline, one-click AAVSO Extended
Format). For the live-capture screen we also borrow the ASIAIR / Seestar house
look (full-bleed image, quiet right-rail of icon actions, one primary action) so
Argos stays visually native to a ZWO device.

---

## 8. Current code -> new IA (migration map)

The redesign is mostly **redistribution**, not rewriting — the widgets exist.

| New screen     | Reuses today                                              | Main change |
|----------------|-----------------------------------------------------------|-------------|
| Connect        | `ConnectionPage`, `StellariumCard`, `DiscoveryWorker`     | Standardise device-row anatomy |
| Target         | `FitsViewer`, `MountDock`, `OverlayBar`, `AstrometryController`, `sky_geometry` | Add target-summary card (alt/airmass/transit/Moon) |
| Focus          | `FitsViewer`, `FocuserDock`, `AutofocusWorker`, `metrics` | Add V-curve plot panel |
| Photometry     | `FitsViewer`, catalog overlay, `CatalogWorker`, `target_table`, `comparison_table` | Promote from detached window to a rail phase; `[Pick stars]` opens companion |
| Capture        | `FitsViewer`, `SequencePanel`, `MetricsPanel`, `lightcurve_panel`, `SequenceWorker`, `LogPanel` | Reframe as monitoring: progress + stability + live curve; controls reduced to Start/Pause/Stop |
| Analyze        | `AnalysisWindow`, `PhotometryWindow`, `lightcurve_panel`  | Keep as companion window; wire AAVSO export |
| Settings       | `ConfigurationPage`                                       | Group into one-axis sections |

The big structural consequence: the 1755-line `ImagingPage` is split. Its layout
becomes several small screen widgets, and its orchestration moves to a controller
layer — see `ui-controller-layer-strategy` notes and a follow-up section in
`ARCHITECTURE.md`. UX and code refactor proceed in step but are tracked
separately.

The single UI smoke test (`tests/ui/test_shell.py`) pokes private attributes of
the windows; update it in the same commit as each screen extraction (see
`AGENTS.md`).

---

## 9. Open questions (to settle before building)

1. **Target vs Focus — one screen or two?** Specified as two (one job each). If
   you would rather frame and focus on a single screen, they can merge with a
   sub-toggle. Default: keep separate.
2. **Capture stability block — which metrics?** Proposed HFD, SNR, background
   trend. Is HFD drift the signal you most want to watch, or peak flux / star
   count?
3. **Light-curve rejection — live or analyze-only?** Proposed: view-only during
   Capture, reject/keep only in Analyze (don't let a tired observer corrupt the
   set mid-run). Confirm.
4. **Sequence editor — its own rail phase, or a dialog off Capture?** Proposed: a
   dialog off Capture (`[Edit plan]`), since the plan is set once before the run.

---

## 10. Build order (when we start)

Paper first, then one screen at a time, each leaving the app working:

1. Reshape the rail to the seven phases (entries only; route to current content).
2. **Capture** screen (highest time-spent; sets the cockpit style).
3. **Connect** (standardised anatomy; low risk).
4. **Target** (+ summary card) and **Focus** (+ V-curve).
5. **Photometry** phase + Photometry Setup companion.
6. **Analyze** companion + AAVSO export.
7. **Settings** grouping.

Each step is a self-contained change with its `test_shell.py` update.

---

## 11. Validation against reference tools

This design was checked against a scan of the major acquisition and photometry
tools (June 2026). What confirmed the plan, what it changed, and the sources.

**Confirmed.** The workflow-ordered left rail is the dominant acquisition pattern
(N.I.N.A. icon rail; Ekos module tabs; ASIAIR/Seestar mode rail). Constant
equipment-panel anatomy — driver dropdown + connect + a global connected-state
indicator — is universal (N.I.N.A., APT's connection asterisk, ASIAIR/Seestar
status strip). Progressive disclosure (simple vs advanced) is standard (N.I.N.A.
Simple/Advanced sequencer; AstroImageJ's "show other configuration panel").

**Adopted from the photometry tools.**
- *Comparison-star selection (AstroImageJ):* click-to-place `T1` (green) /
  `C2, C3...` (red) / `K` on the solved frame, right-click to finalise, live
  re-centroiding. The de-facto standard — folded into Photometry (3.4 / 4.1).
- *Reusable per-field sequence (VPhot):* save the comp/check set, auto-match on
  return via plate-solve + catalog. Folded into Photometry.
- *Diagnostics (VPhot):* the check-star light curve as the error estimate, plus
  SNR / airmass / FWHM / Max ADU (saturation) / skyglow / tracking co-plots.
  Folded into Analyze (3.6) and the Capture stability block (3.5).
- *Outlier handling (AstroImageJ):* direct, reversible removal on the plot.
- *Export (VPhot):* one-click AAVSO Extended Format for WebObs. AstroImageJ
  deliberately does *not* do AAVSO — confirming this belongs to our Analyze step,
  not the capture loop.
- *Live-capture look (ASIAIR / Seestar):* full-bleed image, quiet right-rail of
  icon actions, one primary action, top health strip.

**Resolved open questions (section 9).**
- *Capture metrics (Q2):* the canonical health set is FWHM/HFD, SNR, Max ADU
  (saturation), background/skyglow and tracking error (VPhot's diagnostic set).
- *Outlier rejection (Q3):* view-only live curve during Capture; full reversible
  reject/restore only in Analyze — consistent with not corrupting the series
  mid-night.

**Deliberately not adopted.** AstroImageJ's many-floating-window sprawl — we keep
a single main window plus *at most two* deliberate companion windows (Photometry
Setup, Analyze), which is the endorsed "detach the plot to a second monitor", not
sprawl. A full Advanced-Sequencer / Voyager DragScript engine — the Seestar night
is linear and fixed-focus, so it is over-engineering. Gnuplot/external plotting
(Siril) — render natively so the curve updates live. APT-level on-screen density.

**Sources.** N.I.N.A. docs (nighttime-imaging.eu); Ekos/KStars manual
(kstars-docs.kde.org); ASIAIR manual + ZWO Seestar manual (i.seestar.com);
AstroImageJ User Guide (astro.louisville.edu) + Collins et al. 2017
(arXiv:1701.04817); AAVSO VPhot Users Guide v3.2 (aavso.org); C-Munipack
(sourceforge.net); Siril photometry docs (siril.org); SGP, APT, Voyager and
MaxIm DL vendor docs.

---

## 12. Missing for a complete UX (running list)

Options and features not yet in the design that a complete, usable photometry
app needs. Captured here as they surface; triage and schedule per release. Items
marked [SCI] are science-correctness, not just convenience.

**Planning / targets**
- **Target queue / "tonight's plan"** — a list of variable stars to cycle through
  in one night, with per-target exposure/filter/comp-set. Today targeting is
  one-object-at-a-time via Stellarium. A photometry program is inherently a list.
- **Altitude-vs-time curve** for the session (NINA Sky Atlas) — we show
  instantaneous airmass; the curve tells you *when* to shoot and when the target
  drops below the horizon/airmass limit.
- **Horizon / altitude / airmass limits** — warn or skip when a target is too low.

**Science correctness [SCI]**
- **Field-rotation tracking on alt-az** — the Seestar is alt-az, so the field
  rotates during a session; stars move across the frame and apertures must follow
  (we have re-centroiding) but long runs may need a rotation warning or a session
  length cap. Must be surfaced, not silent.
- **AAVSO observer code + transform coefficients (Tg, etc.)** in Settings — needed
  for valid AAVSO Extended Format submission (see capture_panel.md TG band).
- **Comp-star saturation / linearity guard** — flag comps near saturation (Max
  ADU) that would bias the ensemble.
- **Per-target filter/band binding** — tie the Seestar wheel (Dark/IR/LP) choice
  to the photometric band recorded in headers and export.

**Capture robustness**
- **Plate-solve failure handling** — explicit retry / blind-solve fallback /
  manual sync UX when ASTAP fails, instead of a dead end.
- **Session resume / crash recovery** — resume an interrupted sequence; recover
  the live light curve from saved frames after a restart.
- **Storage gauge + low-disk warning** — long runs fill the disk (ASIAIR has one).
- **Battery + thermal (55 C veto) indicators** in the status bar — Seestar-specific
  health the observer must see at a glance.
- **End-of-target / error notifications** — toast + optional sound so an
  unattended observer knows a target finished or a fault occurred.

**Analysis / data management**
- **Session browser** — pick past sessions/nights to open in Analyze (multi-night).
- **Comp-set mismatch handling** — when a saved field sequence does not fully
  re-match on a return night (missing/extra stars).

**Calibration**
- **Guided flat/dark/bias capture** — the sequencer has the frame types; a light
  "calibration helper" (flat target ADU check) would complete the loop.

**Cross-cutting**
- **First-run / empty states** — what each screen shows before any device or frame
  exists (currently implicit). Connect should be the obvious starting point.
- **Keyboard shortcuts map** — beyond F1..F7 phase switching (start/stop capture,
  solve, next target).
