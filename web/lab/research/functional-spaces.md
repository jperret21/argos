# Functional spaces for an ARGOS night

UX research for the design team, 2026-11-01. Audience: the owner, the design team, the
front-end and server teams. Status: **research and proposals, nothing prototyped**. No code
was written for this study; every wireframe is a proposal to be prototyped and reviewed on
screenshots.

Question asked by the owner: how does an observer actually work with ARGOS during a night,
and what task-oriented spaces (layouts, modes, patterns) should the web UI offer, compared
with what the specification (`web/spec/README.md`) and the current Observe screen do?

Inputs read:

- the user guide and method pages: `docsrc/guide.md`, `docsrc/differential_photometry.md`
  (sections 3.5, 6, 10), `docsrc/field_identification.md`, `docsrc/field_connectivity.md`,
  `docsrc/exoplanet_transits.md`;
- the code that runs the night: `argos/workers/sequence_worker.py`,
  `argos/core/imaging/sequencer.py`, `argos/core/session/device_session.py`,
  `argos/core/session/acquisition_engine.py`, `argos/core/alpaca/telescope.py`,
  `argos/core/photometry/quality.py`, `argos/core/photometry/tracking.py`,
  `argos/core/config.py`, `argos/core/photometry/lightcurve.py`;
- the specification `web/spec/README.md` and the area specs `01`, `03`, `05`, `06`, `07`;
  `web/src/design/BRAND.md`, `tokens.css`, the icon ids, `web/src/lib/app/keymap.ts`,
  `web/src/lib/imaging/layout.ts`;
- the screenshots of the current Observe screen
  (`web/screenshots/2026-11-01_observe-spike/`, 18 PNG files);
- **the owner's own sessions** under `~/Argos/sessions` (19 folders, 9 with a
  `session.json`, three nights: 2026-08-29, 2026-09-07, 2026-09-25), read only: frame records,
  FITS headers (no pixels), photometry CSV files and `photometry_quality.json`. Only
  aggregated numbers are quoted here; no observer identity and no site coordinates.

What is evidence and what is assumption: numbers marked **[code]** come from a file and line
cited next to them, **[data]** from the owner's sessions, **[measured]** from a measurement
made for this study (method given), **[assumption]** from reasoning that must be checked on a
real night with the owner (section 8).

Notation in wireframes (as in the area specs): `(id)` icon-only button with that icon id,
`[id Label]` icon + label, `<A|B|C>` segmented control, `v` open card, `>` folded card,
`o Label` status badge (dot + word). Wireframes are ASCII at about 12 px per column; glyphs
such as `o [] ^` stand for the role shapes (circle target, square comparison, triangle
check) and are never UI text (BRAND 4.3).

---

## 0. The study in one page

**Findings**

1. **The real cadence is about one frame a minute, not one every ten seconds.** On the
   owner's longest run (RR Lyr, 195 frames of 10 s, 2026-09-25) the median start-to-start
   interval is **51.5 s**; 70.7 s for 15 s exposures and 84.9 s for 20 s exposures on the
   other nights **[data]**. A light curve grows by about 70 points an hour, and the
   comparison-quality verdict, which needs 10 valid points **[code]**
   (`quality.py:26`), arrives about 9 minutes after the start. The night is a slow
   process watched in glances, with long quiet stretches.
2. **A run degraded for its last 40 minutes and nothing on screen said so.** On the same run the HFD
   jumped from 5.5 px (frame 147, 22:13:41 UTC) to 17.5 px (frame 148) and stayed there
   until the end (median 6.25 px over frames 131-146, 16.7 px over frames 148-195); the
   median of each frame's brightest raw pixel (`peak_adu`, `metrics.py:154`) fell from
   58 824 to 47 960 ADU, as when light spreads out of focus; the target's point-to-point
   noise (median absolute second difference of the magnitudes) doubled, 0.025 mag over
   frames 1-147 against 0.053 mag over frames 148-195 **[data]**. The run alone cannot prove
   the cause (dew, focus or tracking), but the coincidence is plain. A simple rule (HFD above
   1.5 times the median of the first 20 frames for 3 frames in a row) would have fired at
   frame 150, **22:16:14 UTC, 38 minutes before the run ended at 22:54:16** (section 4.10).
   The FWHM column did not move (2.16 to 2.19 px), which is worth checking in the metrics
   code (open issue for the science side, not a UI matter).
3. **The site in Settings did not match where the telescope was, and nothing said so.** On
   2026-09-25 the FITS headers give the mount altitude of RR Lyr as 75.4° at 20:05 UTC and
   47.1° at 22:54 UTC (header AIRMASS 1.033 to 1.364), while the airmass ARGOS computed from
   the Settings site, which feeds the photometry CSV and the AAVSO `AMASS` column
   (`lightcurve.py:248`), runs from **4.09 to 1.51** **[data]**. Recomputed with astropy from
   the headers' `SITELAT`, `SITELONG`, `DATE-OBS`, `RA` and `DEC`, the Settings site puts RR
   Lyr at 13.8° at the start, **61.6° below what the mount reported**; on the two earlier
   nights the same Settings site agrees with the mount within 2.1° **[measured]**. The
   telescope had moved; Settings had not. A check comparing the mount's reported altitude
   with the altitude computed from Settings catches this at connection time (section 4.13).
4. **Observers iterate by restarting runs.** 2026-09-25: **7 sequence starts in 17 minutes**
   (19:47 to 20:04 UTC), six of them stopped after 1 to 5 frames, the filter alternating LP
   and IR between them, before the 195-frame run. 2026-09-07: four runs, exposure 20 s then
   60 s, gain 80 then 100 **[data]**. Exposure and filter were tuned through full sequence
   starts, which is what the guide's "test Shot, check the peak" loop is meant to replace
   (guide section 6). Each restart also leaves a session folder, so Review opens on a list of
   trial runs.
5. **The most valuable band of the screen is spent on a set-once control.** At 1440 x 900 the
   16:9 frame fills 928 x 522 px and the band under it, 299 px tall (33 % of the window
   height), holds the display stretch **[measured on `live-1440x900-observatory.png`]**. The
   stretch is needed while framing; during the two to three hours of a run the same band
   could show the live light curve.
6. **Nothing is readable from two metres.** The status bar carries the run state in 12 px
   text. Reading a value at 2 m needs digits of about 66 px (16 arcmin) to 83 px (20 arcmin) on
   a 13-inch laptop at 1440 x 900 (section 2.5) **[measured + computed]**. The spec has no
   glance view, no alerts (OS notifications are forbidden, there is no sound) and the light
   curve tab is not opened when a run starts (Q-O24).
7. **During a run the observer's information is spread over four places**: the status-bar
   run chip (progress, D18), Plan's run strip (step, last frame), the Photometry rail card
   (verdict) and two drawer tabs (Light curve, Conditions). Answering "is my run fine?"
   means navigating.
8. **Mount commands are not interlocked with a running sequence.**
   `DeviceSession.goto` enables tracking and slews, `park` parks and `set_tracking` switches
   tracking with no check that a sequence is exposing (`device_session.py:573-583, 628-635,
   656-663`) **[code]**. The spec adds no confirmation for GoTo, Centre or tracking
   (README 3.3). One click can ruin a three-hour time series.
9. **Calibration frames are never taken in ARGOS** in the owner's sessions: no dark, bias
   or flat frame in any of the 19 folders **[data]**, as the guide warns ("ARGOS will not
   remind you", guide section 6).
10. **No sleep prevention exists** (no `caffeinate`, wake lock or power assertion anywhere
    in `argos/` or `web/`) **[code search]**. A laptop that goes to sleep stops the server.
    Not tested on a real night (section 8).
11. **None of the three main runs had a check star.** Their `targets.json` hold 1 target
    and 6 comparisons (2026-09-25), 1 and 8 (2026-09-07), 2 and 5 (2026-08-29), and no check
    curve was written **[data]**. The guide recommends one, the live curve (D25) and the AAVSO
    `KNAME` field rely on it. The UI must say "no check star" where the check would be,
    before the start (preflight note) and during the run (Watch, Run card).

**Proposals** (section 4; the structured list returned with this file has the same names)

| # | Space or pattern | One line |
|---|---|---|
| P1 | Observe task modes | Observe keeps one screen but gets four layout presets, **Framing · Focus · Field · Run**, that open the cards, fill the band and show the tools each task needs. |
| P2 | Task band | The band under the image (sized by `layout.ts`) shows what the mode needs: levels and exposure check, V-curve and HFD trend, comparison candidates, the live light curve. |
| P3 | Watch | A full-window glance view readable at 2 m: state, frames, last-frame age, latest magnitude, check star, end time, light curve, conditions, attention banner; dimmable; red-only in Night Red. |
| P4 | Run card | Run status and Pause / Stop live where the observer is during a run (Observe › Run), not only in the status bar and Plan. |
| P5 | Comparison workspace and Inspector | A candidates table (V, B−V, Δ(B−V), separation, peak, blends) linked to the image, and one Inspector card for the selected star. |
| P6 | Attention system | Rules computed by the server on every frame, three levels, an attention chip and list, audible alerts through Web Audio, keep-awake during runs. |
| P7 | Night checklist | The guide's order of the night computed from server state, with new checks: site against mount, clock, disk space, calibration still to take. |
| P8 | Safe hardware patterns | Server interlock of mount motion during a run, hold-to-confirm, inline confirm for the keyboard, undo windows, armed jog, Watch ignores keys that act. |
| P9 | Command palette | `Mod+K`: every action, section, card, setting and star by name, with its shortcut and disabled reason; hardware actions keep their confirmation. |
| P10 | Regions, presets and density | Per-mode memory of rail width, card folds, band and drawer; three densities (Compact, Comfortable, Watch) through tokens, not zoom. |
| P11 | Wrap-up | The end of the run proposes matching darks and biases (estimated from tonight's cadence), Park, disconnect and the session folder. |
| P12 | Review triage | Review groups runs by night, folds trial runs, and opens a session on a health strip (gaps, HFD rises, comparisons used) before the plot wall. |
| P13 | Devices | Laptop first; an external-monitor breakpoint; Watch as the later tablet view, read-only plus acknowledge and pause. |

---

## 1. Evidence

### 1.1 What the code does during a night

| Fact | Where | Consequence for the UI |
|---|---|---|
| 0.4.2 is attended only: no weather safety, no restart recovery | `guide.md` admonition, `differential_photometry.md` section 10 | Someone must watch; watching must be cheap and work from a distance. |
| A plan has steps (type, filter, exposure, gain, count, interval, cadence, dither), `repeat`, `autofocus_every_n`, `autofocus_on_filter_change`, `on_complete` in Nothing / Stop tracking / Park mount | `sequencer.py:28-91`, `ON_COMPLETE_CHOICES` line 61 | The end-of-run action is known in advance: show it during the run. |
| Pause holds at a frame boundary; Stop interrupts the exposure | `sequence_worker.py:132-146, 280-289, 361-362` | "Pausing" exists as a visible transitional state (spec A63). |
| Exposure timeout: exposure + 15 s, then the run stops with "Exposure timeout after N s" | `sequence_worker.py:44, 361-366` | A stop on error must be loud (critical alert). |
| Autofocus handshake: if autofocus does not resume within 120 s the sequence is aborted | `sequence_worker.py:51, 485-503` | Mid-run autofocus can end a night: show next AF, its outcome, and alert on abort. |
| Mount auto-reconnects every 10 s after a lost connection | `device_session.py:155-160, 300-314, 567` | "Lost, retrying" is a state, not an error popup; it needs an alert during a run. |
| Mount clock more than 60 s off: GoTo and Sync refused, logged as hours off | `telescope.py:134-162, 283-294`; `device_session.py:286-290` | A checklist line, and disabled GoTo with the reason (spec H4). |
| The mount's own site (`SiteLatitude`, `SiteLongitude`) is read only for topocentric drivers and never compared with Settings; FITS `SITELAT` and the photometry airmass come from Settings | `telescope.py:193-215`; `acquisition_engine.py:627, 1525` | Finding 3: a stale site goes unnoticed. |
| `goto`, `park`, `set_tracking` act with no sequence check | `device_session.py:573-583, 628-635, 656-663` | Finding 8: needs a server interlock. |
| Live re-solve ceiling 20 s, live solve timeout 25 s | `config.py:95-97` | Field state changes often during a run; the field chip must be quiet (log, not toasts). |
| Auto comparisons 5, floor 2, separation limit 25′, validation needs 10 points | `config.py:144-155`; `quality.py:26, 55` | The comparison workspace must show count against 5, separation, and "waiting for 10 points". |
| Ensemble verdict: insufficient data / not ready (< 3 stable) / live-preview consistent | `differential_photometry.md` section 6 | Three words to show, never a green tick that reads as "calibrated". |
| Saturation flag threshold 50 000 ADU is not reconciled with the full well; judge the peak ADU yourself | `differential_photometry.md` section 3.5 | Show the peak ADU as a number against 65 535; never an "OK" badge for saturation. |
| Aperture 2.5 x FWHM, at least 4 green px: about 30″ on an S30 Pro; blends matter | `differential_photometry.md` section 3.1 | Show neighbours inside the aperture when choosing stars. |
| Live aperture tracker counts frames with no anchor (`frames_lost`) but no event reports it | `tracking.py:274-311`; `acquisition_engine.py:1284-1292` | "Lost tracking" is detectable but invisible today (API addition, section 4.10). |
| No sleep prevention, no sound anywhere | code search for `caffeinate`, `IOPM`, `inhibit`, `wakeLock`, `audio` | Findings 10 and 6. |
| Frame sizes: S30 Pro 3840 x 2160, S30 and S50 1920 x 1080; 16-bit FITS: 16.6 MB and 4.1 MB per frame | `hardware/catalog.py:48-87`; file sizes in the sessions **[data]** | Disk-space check before a run (the 195-frame run used 3.0 GB). |

### 1.2 What the owner's sessions show

| Night | Runs started | Frames per run | Exposure, gain, filter | Median start-to-start | Notes |
|---|---|---|---|---|---|
| 2026-08-29, XX Cyg | 5 | 1, 1, 22, 4, 4 | 5.9 s g65 LP, then 10 s g80 IR, then 15 s g80 IR | 70.7 s (15 s) | Short re-runs after the 22-frame run. |
| 2026-09-07, XX Cyg + RR Lyr | 5 | 24, 2, 3, 3, 1 | 20 s g80, then 60 s g80, 60 s g100 | 84.9 s (20 s); 74.8 and 125 s (60 s, runs of 3 and 2 frames) | Last XX Cyg run: HFD 24.7-39.2 px, stars 826-2273: degraded, stopped after 3 frames. |
| 2026-09-25, RR Lyr | 7 | 1, 1, 1, 5, 1, 1, **195** | 10 s g80; LP x5, IR x2 | **51.5 s** (10 s) | 7 starts between 19:47 and 20:04 UTC; long run 20:04-22:54 UTC (169.3 min). |

Long run, 2026-09-25 (195 frames):

- conditions: star count 2 091-3 466 (median of the first 20 frames 2 982; lowest single
  frame 0.70 of it); sky 1 168-1 192 ADU; HFD event of finding 2;
- comparisons: six in the set, all "stable" at the end (scatter 0.019-0.029 mag), verdict
  "live_preview_consistent"; but `comps_used` per point was 5 in 92 points, 4 in 62, 3 in 36
  and **2 in 5** (the magnitude ensemble after clipping) **[data]**. "Stable" at the end did
  not mean "five comparisons on every frame": comparisons used per frame is a value to watch;
- the target faded smoothly by about 0.12 mag/h over the run, so the second-difference
  scatter quoted in finding 2 measures noise, not variability;
- no check star in the set (finding 11).

Limits of this evidence: three nights, one observer, Qt UI (0.4.x). What was on screen,
why runs were stopped and whether the HFD rise was noticed are not recorded; the
interpretations above are the most plausible reading of the files, to be confirmed with the
owner.

### 1.3 What the current web Observe screen does

Measured on `web/screenshots/2026-11-01_observe-spike/live-1440x900-observatory.png` and its
siblings:

| Region | Size at 1440 x 900 | Used for |
|---|---|---|
| NavRail | 92 px | five sections |
| Toolbar | 47 px | equipment chip, capture / live / stop, zoom, stretch, histogram, crosshair, panels, theme |
| Image | 928 x 522 px | the rotated 16:9 frame, HUD chips top-left |
| Band under the image | 928 x 299 px | levels strip: histogram with B / M / W handles, levels, transfer, rotation, frame statistics |
| Right rail | 420 px | Connection (folded), Camera (exposure, gain, progress, in use, sensor), Mount (RA / Dec / Alt / Az, tracking, park, target RA / Dec form, Slew, Abort, Use current) |
| Status bar | 32 px | connection, mount state and RA / Dec, cursor X / Y / value, rate, latency, Log |

Observations: the levels strip and the always-open Mount target form take about 470 px of
height for controls used a few times a night; the Connection card is still in the rail (D10
removes it); the Camera card's "In use 1.0 s, gain 80" repeats the two fields above it; while
slewing, the Slew button keeps its brass fill next to the danger Abort
(`slew-1280x800.png`). None of this is wrong for a framing task; it is wrong for the three
hours that follow.

---

## 2. The night as tasks and states

### 2.1 Timeline

```
 day before / dusk           dusk, at the telescope                 first 30-60 min                         2-6 h                      end             next day
+-------------------+  +------------------------------+  +-----------------------------------+  +--------------------------+  +-----------------+  +---------------+
| T1 Prepare        |  | T2 Seestar app: init,        |  | T4 Framing + GoTo                 |  | T10 Monitor (glances)    |  | T12 Wrap-up     |  | T13 Review    |
| settings, site,   |->| GoTo calibration, focus      |->| T5 Exposure check (Shot, peak)    |->|   every 5-20 min         |->| outcome, darks, |->| triage, curves|
| targets, plan     |  | T3 Connect + checks          |  | T6 Focus / autofocus              |  | T11 Problems (rare,      |  | biases, park,   |  | export, hand  |
| (indoors, online) |  |   (devices, clock, site)     |  | T7 Solve + identify               |  |   urgent)                |  | disconnect      |  | off to Siril  |
+-------------------+  +------------------------------+  | T8 Roles (target, comps, check)   |  +--------------------------+  +-----------------+  +---------------+
                                                         | T9 Start run (often several times)|
                                                         +-----------------------------------+
  0.6 m, focused           0.5 m, focused, phone            0.5 m, focused, Night Red               1-3 m, glance                 0.5-2 m              0.6 m, focused
```

### 2.2 Observer-facing states

The observer thinks in these states; every space should make the current one obvious.

```
                    +--------------+   connect    +-------------+  slew / live / shot  +-----------+
   server down ---> | Disconnected | -----------> | Ready, idle | -------------------> | Framing   |
                    +--------------+              +-------------+                      +-----------+
                          ^  link lost (retry 10 s)       |  autofocus                       | solve
                          |                               v                                  v
                    +--------------+              +-------------+                      +-----------+   roles   +-------------+
                    | Device lost  |              | Focusing    |                      | Field     | --------> | Ready to run|
                    | (retrying)   |              | (AF n/N)    |                      | identified|           | (preflight) |
                    +--------------+              +-------------+                      +-----------+           +-------------+
                                                                                                                      | start
             +----------------------------------------------------------------------------------------+               v
             |  RUNNING: exposing -> saving -> measuring -> (autofocus) -> exposing ...                 | <-------------+
             |  sub-states: Pausing (until the frame ends) / Paused / Autofocus / Stopping              |
             +----------------------------------------------------------------------------------------+
                 | complete                 | stopped by observer          | stopped on error (timeout, AF lost, device)
                 v                          v                              v
             +-----------+            +-----------+                  +-----------+
             | Finished  |            | Stopped   |                  | Failed    |  -> outcome kept until dismissed
             +-----------+            +-----------+                  +-----------+
                 | darks / biases, park, disconnect
                 v
             +-----------+         next day         +-----------+
             | Parked    | -----------------------> | Review    |
             +-----------+                          +-----------+

  Conditions overlaid on RUNNING (they do not stop the run): clouds (stars down), focus loss (HFD up),
  field drift or tracker lost, target below the altitude limit, comparisons used < 3, disk low, stale frame.
```

### 2.3 Task table A: what the observer needs to see and do

| # | Task | See: primary | See: secondary | Do: frequent | Do: rare | Do: dangerous |
|---|---|---|---|---|---|---|
| T1 | Prepare (indoors) | site, observer code, telescope profile, sessions folder; tonight's targets resolved and their altitude | ASTAP found, catalogues cached, disk free | search targets, check visibility, edit the plan | edit Settings | change the profile (locked while connected, D28) |
| T2 | Seestar app start | (outside ARGOS) | ARGOS reminder that it must be done | none in ARGOS | none | none |
| T3 | Connect and checks | four devices Ready, Seestar and Net links | mount clock offset, site against mount, alignment (Alt-Az / EQ), profile caveats | Connect all, Discover | per-device retry | Disconnect during a run |
| T4 | Framing and GoTo | live image, target name, distance to target (°), mount state | Alt / Az, tracking, field chip | search object, Slew, Shot, Live, zoom, stretch | jog, accept a Stellarium suggestion | Slew, Centre, Park or tracking off **during a run**; Unpark |
| T5 | Exposure check | peak ADU of the target and comparisons against 65 535; histogram | sky ADU, HFD, star count | Shot, change exposure / gain | filter, frame type | none |
| T6 | Focus | HFD now and its trend; star shape (loupe); V-curve | focuser position and temperature | step in / out, Shot / Live | Autofocus, Go to position | none (Halt is safe) |
| T7 | Solve and identify | field state, scale, rotation, distance to target; markers on stars | catalogue counts, layers | Identify (S), layers, labels | catalogue depth, settings | Centre target (moves the mount) |
| T8 | Roles | candidates with V, B−V, separation, peak, blends; set count against 5 | VSP chart, ensemble preview | click star, assign role, Recommend 5 | remove, manual comparison | role changes during a run (confirm, spec 3.3) |
| T9 | Start run | preflight (ready / notes / blocks), total, end time, end-of-run action | altitude through the run, disk needed | Start, Start at | edit steps | Stop |
| T10 | Monitor | running?, frame n / N, **time since last frame**, latest magnitude ± error, check star steady?, stars and HFD, end time | comparisons used, verdict, altitude to limit, next autofocus | glance, open the curve, acknowledge an alert | open a frame | Pause, Stop, any mount command |
| T11 | Handle a problem | what happened (rule, value, since when), what ARGOS is doing (retrying?), what is safe now | log | acknowledge, pause, refocus, re-identify | reconnect, restart the run | slew or centre during a run, disconnect |
| T12 | Wrap-up | outcome (complete, stopped, failed), frames saved, session folder and size | calibration still needed, mount state | take darks and biases, Park | disconnect, quit | Park while a frame is exposing |
| T13 | Review and export | session health (gaps, conditions, flags), curves, comparison quality | frames, metadata, chart, observer code | open session, point to frame, export CSV | AAVSO export, re-run photometry | overwriting an export (never silent, D29) |

### 2.4 Task table B: context

| # | When | How often, how long | Distance from the screen | Attention | Theme | Device |
|---|---|---|---|---|---|---|
| T1 | day before, dusk | once, 10-30 min | 0.5-0.7 m | focused | Observatory / Charcoal (indoors) | laptop or external monitor |
| T2 | dusk | once, 10-15 min | phone in hand | focused, on the phone | (Seestar app) | phone or tablet |
| T3 | dusk | once, again after each link loss | 0.5 m | focused | Night Red outdoors | laptop |
| T4 | per target | 1-3 a night, 2-10 min each | 0.5 m | focused | Night Red | laptop |
| T5 | per target | 2-10 shots | 0.5 m | focused | Night Red | laptop |
| T6 | start, after a temperature drop | 1-3 a night; autofocus runs for minutes | 0.5 m, then away during AF | focused, then unattended | Night Red | laptop |
| T7 | after each slew | 1-5 | 0.5 m | focused | Night Red | laptop |
| T8 | per target | once, 5-15 min; errors cost the night (guide section 5) | 0.5 m | focused, high stakes | Night Red or Charcoal | laptop |
| T9 | per run | **1-7** (7 on 2026-09-25 **[data]**) | 0.5 m | focused | any | laptop |
| T10 | during the run | 2-6 h; a glance every 5-20 min **[assumption]**, i.e. 10-50 glances | **1-3 m**, sometimes another room (the Seestar is on Wi-Fi) | glance, under 2 s | Night Red outside; Charcoal indoors | laptop on a table; external monitor indoors; tablet later |
| T11 | any time | rare, minutes | from 3 m back to 0.5 m | interrupted, then focused | Night Red | laptop |
| T12 | end | once, 20-40 min (20 darks at tonight's 51.5 s cadence: about 17 min) | 0.5-2 m | focused, then glance | Night Red | laptop |
| T13 | next day | once per session, 15-60 min | 0.6 m | focused, analytical | Observatory / Charcoal | laptop or external monitor |

Two consequences. First, **T10 dominates the night by duration** and is the task the spec
serves least. Second, **T4-T9 are a loop, not a line**: the 2026-09-25 evidence shows seven
passes through T5-T9 before the long run.

### 2.5 Reading distance and type size

Method. ISO 9241-303 and ANSI/HFES 100-2007 put the character height for reading at a
minimum of 16 arcmin, 20-22 arcmin preferred. Character height h at distance d:
`h = d x tan(angle)`. Plex digits measure **0.71 em** high and **0.60 em** wide, capitals
0.698 em **[measured]**: canvas `measureText` on the bundled `IBMPlexMono-Medium.woff2` and
`IBMPlexSans-SemiBold.woff2` in headless Chrome, 100 px font, digit "0" ascent 71 px, width
60 px, "H" ascent 69.8 px. Pixel density of the reference screens: a 13.3-inch laptop at 1440
x 900 shows about 5.0 CSS px per mm, a 15.3-inch one at 1440 x 932 about 4.4, a 27-inch
2560 x 1440 monitor about 4.3. The worst case (smallest physical digits) is the 13-inch
laptop, 5.0 px/mm.

| Distance | 16′ (minimum) | 20′ (preferred) | 22′ |
|---|---|---|---|
| 0.6 m (at the table) | 2.8 mm, digits of **20 px** | 3.5 mm, **25 px** | 3.8 mm, 27 px |
| 1 m (chair beside the table) | 4.7 mm, **33 px** | 5.8 mm, **41 px** | 6.4 mm, 45 px |
| 2 m (across the room) | 9.3 mm, **66 px** | 11.6 mm, **83 px** | 12.8 mm, 91 px |

Font size = `h (mm) x 5.0 px/mm / 0.71`. Notes:

- At the table, the BRAND readout size `--text-xl` (17 px) gives digits of 13.8′ at 0.6 m:
  fine for focused reading, too small for a glance from a step away. Run values deserve
  22-28 px even at the table (Comfortable density, section 4.8).
- At night the observer dims the screen and Night Red text is dim red: vision is mesopic,
  acuity drops. Take the 20′ column, not the 16′ one, for anything read from afar, and test
  it in the field (section 7).
- Labels ("ETA", "STARS") at 32-40 px are readable to about 1 m; from 2 m the fixed position of
  each value teaches its meaning. Watch therefore never moves a value from its place.

---

## 3. Gaps between the night and the spec

| # | Gap | Where in the spec or the screen | Evidence |
|---|---|---|---|
| G1 | No space answers "is my run fine?" from more than a metre away. | Run progress only in the status-bar chip (D18) and Plan's run strip; light curve drawer tab not opened at start (Q-O24) | Finding 6; T10 distance 1-3 m |
| G2 | The band under the image is fixed to the display stretch for the whole night. | BRAND 11.1 levels strip; `layout.ts` | Finding 5 |
| G3 | Run information is split over four places. | D18, 06 §2.3.2 run strip, D8 Photometry card, D6 / D25 drawer tabs | Finding 7 |
| G4 | Degradation is silent: no rule, no alert, no sound; OS notifications forbidden in every build. | README 3.2, 3.8, BRAND 4.3 | Finding 2 (40 minutes, no alert) |
| G5 | Mount commands are not interlocked with a running sequence; GoTo, Centre, tracking have no confirmation. | README 3.3; `device_session.py` | Finding 8 |
| G6 | Choosing comparisons is a comparison between stars, but the UI offers a Recommend popover and an Ensemble table without B−V, separation, peak or blend columns. | D8, A58, 08 spec | guide section 8 (aim for 5, B−V within 0.3 mag); method section 3.1 (30″ apertures) |
| G7 | The exposure check is done by restarting sequences; Review then lists trial runs as sessions. | 03 / 05 Camera card; 07 R0 list | Finding 4 |
| G8 | One fixed layout for every task: the Mount target form (rare) is above the fold, the Focuser card (needed while focusing) below. | README 1.1 "fixed order per screen"; spike screenshots | section 1.3 |
| G9 | No keep-awake during a run. | absent from the spec | Finding 10 |
| G10 | Site, clock and calibration are not checked or reminded. | Q-G11 first-run checklist covers observer code, site set, ASTAP only | Findings 3 and 9 |
| G11 | Every hardware action without a shortcut is mouse-only; there is no keyboard path to "the thing I cannot find". | README 3.10 (not bound on purpose) | — |
| G12 | Pause and Stop live only in Plan, while the observer watches the run from Observe. | README 1.4 (sequences owned by Plan) | T10, T11 |

---

## 4. Proposed functional spaces

### 4.0 Overview

```
                        +---------------------------- one window, five sections (unchanged) ----------------------------+
                        |  Connection      Observe (one screen, four task modes)             Plan      Review   Settings|
                        |                  Framing | Focus | Field | Run                                                |
                        +-----------------------------------------------------------------------------------------------+
  cross-cutting:         Watch (glance view, any section, W)   Command palette (Mod+K)   Attention chip + list
                         Night checklist (popover)              Safe hardware patterns    Density (Compact / Comfortable)
```

| Task | Space | Section of this file |
|---|---|---|
| T1 | Plan, Settings (unchanged) + Night checklist | 4.13 |
| T2 | Night checklist (manual line) | 4.13 |
| T3 | Connection (unchanged) + Night checklist checks | 4.13 |
| T4, T5 | Observe › Framing | 4.3 |
| T6 | Observe › Focus | 4.4 |
| T7, T8 | Observe › Field | 4.5 |
| T9 | Plan (unchanged) + preflight additions | 4.13 |
| T10 | Observe › Run at the table; Watch from a distance | 4.6, 4.7 |
| T11 | Attention system + safe patterns | 4.10, 4.11 |
| T12 | Wrap-up in the Run card and Plan's outcome strip | 4.14 |
| T13 | Review triage | 4.15 |

### 4.1 Observe task modes (P1)

The spec's single Observe cockpit stays: one image, one rail, one drawer, one toolbar, the
same components. A **mode** is a named layout preset that decides which cards are open,
folded or hidden, what the band under the image shows, which tool group the toolbar shows
next to the common tools, and the default drawer tab. Nothing else changes: every shortcut
works in every mode, no data or hardware state depends on the mode.

| | Framing | Focus | Field | Run |
|---|---|---|---|---|
| Task | point, frame, check exposure (T4, T5) | focus, autofocus (T6) | identify, choose roles (T7, T8) | watch a run at the table (T10) |
| Band under the image | levels + exposure check | V-curve + HFD / FWHM trend | Variables / Candidates / Ensemble table | live light curve: target + check, shared time axis |
| Rail, open | Mount (target block), Camera | Focuser, Camera | Inspector, Photometry, Field | Run, Photometry, Conditions |
| Rail, folded (header with a summary) | Focuser, Photometry | Mount, Photometry | Camera, Mount | Mount, Camera |
| Rail, hidden (Panels popover brings them back) | Statistics | Display, Statistics | Display, Statistics | Display, Statistics, Focuser |
| Toolbar mode group | crosshair, saturation, loupe | loupe, crosshair, region | identify, auto-identify, grid, layers, labels, selected stars | grid, layers, error bars, magnitude / flux |
| Drawer default | Log | Log | Log | Ensemble (when opened) |
| Overlays default | crosshair; target reticle if solved | HFD rings on measured stars | all layers of the first solve (03 §2.4 rule) | roles only |

Common toolbar part, always visible: equipment chip, mode bar, `(capture)` `(live)`
`[stop Stop]`, zoom group, `(stretch-auto)`, then at the right `(watch)` `(arrange)`
`(panels)`. Widths at 1440 x 900: common part about 650 px, mode bar about 330 px (four icon +
label segments), mode group at most 300 px: about 1 280 of the 1 348 px available. At 1280 x
800 the mode bar would show icons only, with the label in the tooltip; BRAND 7 does not cover
an icon-only segmented control, so the design team must decide.

Switching:

- by the mode bar, by `Alt+1` to `Alt+4` (matched on `KeyboardEvent.code` `Digit1-4`, so it
  works on AZERTY and on macOS where Option+digit types a symbol), and by the palette;
- **never automatically**. The system suggests: when a sequence starts, a chip on the image
  "Run started · Run view (Alt+4)"; when a solve succeeds in Framing, "Field identified ·
  Field view (Alt+3)". Autofocus keeps the spec rule: the Focuser card unfolds wherever it is
  (05 §2.4), without a mode change. This keeps Q-O24 (no automatic tab opening) in spirit;
- per-mode memory: rail width, folds, band open / height, drawer tab and height are stored
  per mode (`argos.layout.observe.<mode>.*`, extending README 3.11). "Reset layout" in the
  Panels popover resets the current mode and offers "Reset all modes".

Pinned in every mode (never hidden): the status bar device cluster, mount state and RA / Dec,
the run chip, the attention chip (4.10), the `Esc` abort rule, the last-frame age while a run
is active (run chip tooltip and Run card).

On demand in every mode: Settings sheets, catalogue layers popover (`O`), Statistics (`I`),
FITS header, log (`L`), Panels popover, command palette.

### 4.2 The task band (P2)

`layout.ts` already computes the band: `centre height − drawer − centre width x frame h / w`,
299 px at 1440 x 900 with the rail open, 289 px at 1280 x 800, from 150 to 300 px kept
(BRAND 11.1). The proposal keeps the computation and changes only the content by mode. The
spec's levels strip remains the Framing content; `H` toggles the band in every mode.

| Mode | Band content | Why there |
|---|---|---|
| Framing | Histogram with B / M / W, levels, transfer, rotation (existing) + **exposure check** column: peak ADU of the selected or brightest unsaturated star against 65 535, clipped-pixel count, sky ADU, HFD, stars | The exposure decision is made on these numbers (guide "Check the peak, not the picture"). |
| Focus | V-curve of the current or last autofocus (left), HFD and FWHM over the last 30 min (right), current and best HFD in 22 px | Focus is judged against the curve and the trend, beside the stars it is measured on. |
| Field | Tabs Variables · Candidates · Ensemble (moved from the drawer, D7) | The comparison choice needs width and must sit next to the image it points at. |
| Run | Live light curve: target facet (magnitude axis inverted) over a check facet (Δ from its median), one shared UTC axis, error bars, the newest point ringed | The curve is the run's reason to exist; the band is where the eye already is. |

The drawer keeps the Log and the wide tables; when it opens, the band shrinks (the existing
`reserved` term) and below 150 px collapses to its compact one-row form (levels row, or the
latest magnitude and check value in Run).

### 4.3 Framing (W1)

Goal: get the target in the field and the exposure right with Shots, not with sequence
restarts (finding 4).

```
 <-92-><---------------------------------- centre 928 ---------------------------------><------------- rail 420 ------------->
+-----+-------------------------------------------------------------------------------+-------------------------------------+
|ARGOS| [eq] <[goto Framing]|[focuser Focus]|[plate-solve Field]|[light-curve Run]>  (capture)(live)[stop Stop]             |
|     | zoom (stretch-auto) . (crosshair)(saturation)(loupe)                (watch)(arrange)(panels)   one 47 px row        |
+-----+-------------------------------------------------------------------------------+-------------------------------------+
| Con | LIVE  #128  10.0 s  IR  RR Lyr                         Field not identified   | v (mount) Mount          o Tracking |
|>Obs |                                                                               |   OBJECT [ RR Lyr          ](search)|
| Pla |                                                                               |   RR Lyr . RR Lyrae var . cached    |
| Rev |                       IMAGE 928 x 522 (16:9 frame, shown landscape)           |   19h 25m 27.9s  +42 47' 03"        |
|     |                    + centre reticle                                           |   ALT 75.38  AZ 301.12  0.08 away   |
|     |                                                                               |   [goto Slew]   [abort Abort]       |
|     |                                                                               |   [center-target Centre] after solve|
|     |                                                                               |   > Jog          J arms the arrows  |
|     |                                                                               | v (camera) Camera        o Live     |
+-----+-------------------------------------------------------------------------------+   EXPOSURE [ 10.0 ] s  GAIN [ 80 ]  |
|     | BAND 299 px  histogram (B / M / W handles)        | EXPOSURE CHECK            |   FRAME  <Light|Dark|Flat|Bias>     |
|     |   |                                               | PEAK  41 203 / 65 535 ADU |   FILTER <IR|LP|Dark>  IR advised   |
|     |   |   /\                                          |   on: selected star       |   [capture Shot]   E                |
|     |   |  /  \__                                       | CLIPPED  12 px  (C shows) |   last shot 21:04:11 UTC . #128     |
|     |   +--B--M-------------W---                        | SKY  1 176 ADU            | > (focuser) Focuser  1 305 . idle   |
|     |  levels . transfer . rotation                     | HFD 8.7 px . STARS 2 906  | > (photometry) Photometry  no target|
+-----+-------------------------------------------------------------------------------+-------------------------------------+
| devices . Seestar o Net o . Alt-Az . Tracking . X 512 Y 960 2 011 ADU . #128 . [attention 0] . Log                        |
+---------------------------------------------------------------------------------------------------------------------------+
```

- The Mount card opens on the Target block (spec 05 §2.3 C) because pointing is the task;
  its readouts shrink to one row. In other modes it folds to "Tracking · RR Lyr · 0.08°
  away".
- Shot is labelled and keeps `E`. The exposure-check column updates with each frame; the
  peak is a number, never an "OK" badge (method section 3.5: the saturation threshold is not
  trustworthy).
- Filter hint "IR advised" (tooltip: "IR for photometry; LP changes the passband", guide
  section 6) is a muted note, not a warning. On 2026-09-25 the filter changed between LP
  and IR across the trial runs (finding 4); the filter in use is also on the HUD chip.
- Display card hidden: the band is the Display.

### 4.4 Focus (W2)

```
+-----+-------------------------------------------------------------------------------+-------------------------------------+
|ARGOS| [eq] <Framing|[focuser Focus]|Field|Run> (capture)(live)[stop Stop] zoom . (loupe)(crosshair)(region-stats)         |
+-----+-------------------------------------------------------------------------------+-------------------------------------+
|     | LIVE  #212  2.0 s  IR                                 HFD 3.4 px . 117 stars  | v (focuser) Focuser     o Autofocus |
|     |                                                                +- loupe x4 -+ |   POSITION 1 250   TARGET 1 250     |
|     |                                                                |            | |   FOCUSER 12.3 C   RANGE 0-100 000  |
|     |          IMAGE 928 x 522, HFD rings on measured stars          |    (*)     | |   STEP <1|10|50|100|500|1000>       |
|     |                                                                |            | |   (focus-out)(focus-in) GO TO [    ]|
|     |                                                                +------------+ |   [autofocus Autofocus] [stop Halt] |
|     |                                                                               |   step 7 / 14 . fine . ======----   |
|     |                                                                               | v (camera) Camera     o Autofocus   |
+-----+-------------------------------------------------------------------------------+   AF frames 2.0 s . gain 80         |
|     | BAND  V-CURVE (this autofocus)          | HFD / FWHM, last 30 min (UTC)       |   (fields owned by autofocus)       |
|     |  9 | .                          .       | 12 |                                | > (mount) Mount  Tracking . RR Lyr  |
|     |  6 |     .                  .           |  8 |..  ...  ..  ...                | > (photometry) Photometry           |
|     |  3 |        .  .  |  .  .              |  4 +-------------------------- UTC   |                                     |
|     |    +---500----1 000----1 500---- steps  | HFD 3.4 px now . best 3.10 px       |                                     |
+-----+-------------------------------------------------------------------------------+-------------------------------------+
```

- The V-curve leaves the Focuser card (05 §2.3 D) for the band, where it gets 460 x 270 px
  instead of 396 x 140; the Focuser card keeps position, steps, Autofocus, Halt, progress.
- The HFD trend is the Conditions timeline (D6) filtered to HFD and FWHM.

### 4.5 Field: identify and choose roles (W3, P5)

The guide's rules for a good ensemble are concrete: aim for five comparisons, keep them
within about 0.3 mag of the target in B−V, within 25′, and check the aperture (about 30″ on an
S30 Pro) for neighbours. They are comparisons between stars, so the space is a table linked
to the image.

```
+-----+-------------------------------------------------------------------------------+-------------------------------------+
|ARGOS| [eq] <Framing|Focus|[plate-solve Field]|Run> zoom . (plate-solve)(plate-solve-auto)(sky-grid)(catalogue)(labels)    |
+-----+-------------------------------------------------------------------------------+-------------------------------------+
|     | #212 10.0 s IR   2.39"/px . rot 91.2 . target 1.2' . Auto . catalogues ready  | v Inspector  [] 000-BJW-665         |
|     |                                                                               |   VSP comparison . chart X12345     |
|     |      o RR Lyr       [] 665      [] 666                                        |   V 7.95   B-V 0.62   d(B-V) +0.10  |
|     |                [] 953                ^ 523                                    |   sep 6.2'   peak 38 120 ADU        |
|     |                                                                               |   SNR 410 . HFD 8.1 px              |
|     |         IMAGE 928 x 522: roles, VSP candidates, variables                     |   in aperture (29.9"): 1 Gaia star  |
|     |   +------------------------------------------+                                |     G 13.1, 21" away                |
|     |   | [] 000-BJW-665 . VSP . V 7.95             |  compact star card            |   [aperture thumbnail 96 x 96]      |
|     |   | [target-star][comparison-star][check-star][remove]                        | v Photometry       o not ready      |
+-----+-------------------------------------------------------------------------------+   o RR Lyr  target                  |
|     | BAND  [Variables 4] [Candidates 11] [Ensemble 5]      filter...   sort: d(B-V)|   [] 5 of 5 . ^ 1 check             |
|     | Role Name          V     B-V   d(B-V)  Sep'  Peak ADU   SNR  Nbr  Status      |   aperture 4 px (29.9") . 8-12 px   |
|     | []   000-BJW-665   7.95  0.62  +0.10    6.2    38 120   410   1   waiting 7/10|  [recommend-comparisons Recommend 5]|
|     | []   000-BCG-953   8.41  0.48  -0.04    9.8    21 004   280   0   waiting 7/10| v Field          o identified       |
|     |      000-BCG-512   6.10  1.31  +0.79   14.1    65 535   -     2   clipped     |   2.39"/px . rot 91.2 . re-solve 20s|
|     |  hover a row: ring on the image . Enter: Inspector . role keys: none (Q-O26)  |   [plate-solve Identify field]  S   |
+-----+-------------------------------------------------------------------------------+-------------------------------------+
```

- **Candidates** = VSP references in the field and the current comparisons. Columns:
  V and B−V from VSP, Δ(B−V) against the target when the target's colour is known (blank
  with a tooltip otherwise), separation from the target, peak ADU on the latest frame
  ("clipped" at 65 535, never "saturated"), SNR, **Nbr** = catalogue stars inside the
  aperture radius brighter than the star's G + 3 (blend risk), live status from the
  leave-one-out check ("waiting n / 10", Stable, Noisy, Unstable). Row hover rings the star
  on the image; image hover highlights the row.
- **Inspector** replaces the details of the floating star card (D8 dissolved the Qt
  window; 03 W3 put the details on the image). The on-image card shrinks to identity and role
  buttons so it hides fewer stars; the Inspector holds measurements, catalogue rows, the
  aperture thumbnail and, in Run mode, the star's own mini curve. It keeps the last five
  selections for comparing candidates.
- New server fields: `neighbours_in_aperture` and `b_minus_v` per candidate (extend A51 /
  A58), the target colour when VSX or VSP gives it. Owner decision: whether Δ(B−V) beyond
  0.3 mag is only shown or also sorts candidates last in Recommend.

### 4.6 Run, at the table (W4, P4)

Values in W4 and W5 are those of the 2026-09-25 run at frame 160 (22:24:42 UTC) where the
files record them (frame count, end, magnitude and error, stars, HFD, sky); the check star,
the altitude and its limit time are illustrative (that run had no check star, and its
Settings site was wrong).

```
+-----+-------------------------------------------------------------------------------+-------------------------------------+
|ARGOS| [eq] <Framing|Focus|Field|[light-curve Run]> zoom . (sky-grid)(catalogue)(error-bars)(relative-flux) (watch)        |
+-----+-------------------------------------------------------------------------------+-------------------------------------+
|     | #160  10.0 s  IR  RR Lyr       field tracked . re-identified 21 s ago         | v (nav-sequencer) Run  o Running REC|
|     |                                                                               |   RR Lyr . step 1/1 . 160 / 195     |
|     |                                                                               |   last frame 12 s ago (every 51 s)  |
|     |         IMAGE 928 x 522: latest frame, roles overlay                          |   ends 22:54 UTC . in 30 min        |
|     |                                                                               |   next AF: off . end of run: nothing|
|     |                                                                               |   [pause Pause]   [stop Stop...]    |
|     |                                                                               | v (photometry) Photometry o consist.|
|     |                                                                               |   7.692 +- 0.035 (TG, latest)       |
+-----+-------------------------------------------------------------------------------+   comps used 5 / 6 . check rms 0.018|
|     | BAND  LIGHT CURVE   <UTC|JD|BJD>    target o (inverted)  /  check ^           | v (session-metrics) Conditions      |
|     | 7.3 | o o oo  o o o oo o  oo  o o oo                                          |   STARS 2 926   ~~~~~~~~~~~         |
|     | 7.5 |                  o o  oo o  o o o oo oo o  o(newest)                    |   HFD 18.3 px   ____/~~~~  (!)      |
|     | 7.7 +-----------------------------------------------------------------------  |   SKY 1 184 ADU ~~~~~~~~~~~         |
|     | chk | ^ ^^ ^  ^ ^^ ^ ^^ ^^ ^ ^ ^^ ^  ^ ^ ^^  ^                (d median)      |   ALT 52 . above 30 until 01:10     |
|     |     +--20:30-------21:00-------21:30-------22:00-------22:30-------- UTC      | > (mount) Mount  Tracking . 0.02    |
+-----+-------------------------------------------------------------------------------+-------------------------------------+
| devices . Seestar o Net o . Alt-Az . Tracking . REC RR Lyr 160/195 ETA 30m . [attention 1 . HFD] . Log                    |
+---------------------------------------------------------------------------------------------------------------------------+
```

- **Run card** (new, P4): state with its word, step and frame counts, **last frame age**
  with the observed cadence (the liveness signal: a frozen run looks exactly like a
  healthy one between frames otherwise), end time and remaining time, next autofocus,
  end-of-run action, Pause and Stop. The spec keeps sequence *control* in Plan (README 1.4);
  this card adds the same two transport actions where the observer is. Stop keeps the
  spec's dialog (06 §2.3.6); Pause has no confirmation (it holds at a frame boundary and is
  undone by Resume).
- The light curve is two facets on one time axis, not two series on one axis: the target
  and the check differ by magnitudes, one y axis would flatten both. This refines D25 within
  BRAND 10 (at most three series per plot, one y axis per plot).
- Conditions shows numbers with sparklines; a rule that fires marks its row (icon + word,
  never colour alone) and raises an attention item (4.10).
- Altitude is "above 30° until 01:10" (from A65 visibility with the site limit), honest
  about the site check (4.13).

At 1280 x 800 the image is 768 x 432 and the band 289 px; the Conditions card folds to its
header ("Stars 2 926 · HFD 18.3 px (!)") and the Photometry card to two lines.

### 4.7 Watch: the glance view (W5, P3)

A full-window view of the run, opened by `W` (unused in `keymap.ts`), the `(watch)` toolbar
button or the palette, from any section; `W` or `Esc` returns (`Esc` keeps its abort meaning,
D21). It is not a separate OS window (D27 stays) and works with no run (it then shows
"Idle" and the live frame state).

```
1440 x 900, Charcoal or Night Red. Sizes in brackets are font sizes (section 2.5).
+------------------------------------------------------------------------------------------------------------------------+
|  RUNNING  [88]                         160 / 195  [66]                         12 s ago  [66]                          | 120 px
|  RR Lyr . step 1 of 1  [32]            frames  [32]                            last frame . every 51 s  [32]           |
+---------------------------------------+---------------------------------------+----------------------------------------+
|  TARGET  RR Lyr  [32]                 |  CHECK STAR  [32]                     |  ENDS  [32]                            | 210 px
|  7.692  [88]                          |  0.018  [66]                          |  22:54  [88]                           |
|  +- 0.035  TG  [40]                   |  rms . comps 5 / 6 . consistent [40]  |  UTC . in 30 min  [40]                 |
+---------------------------------------+---------------------------------------+----------------------------------------+
|  o target (magnitude, brighter up)                                                               newest point (o)      | 380 px
|    o o oo  o o o oo o  oo  o o oo     o o  oo o  o o o oo oo o                                                         |
|  ^ check (from its median)                                                                                             |
|    ^ ^^ ^  ^ ^^ ^ ^^ ^^ ^ ^ ^^ ^  ^ ^ ^^  ^ ^^ ^                                                                       |
|  20:30           21:00           21:30           22:00           22:30   UTC   [24]                                    |
+---------------------------------------+---------------------------------------+----------------------------------------+
|  STARS  2 926  [48]  ~~~~~~~~~~~      |  HFD  18.3 px  [48]  ____/~~~  (!)    |  ALT  52  [48]  > 30 until 01:10       | 130 px
+---------------------------------------+---------------------------------------+----------------------------------------+
|  Seestar o  Net o  server o      dim <100|60|30>       [pause Pause, hold]        W or Esc: back                       | 40 px
+------------------------------------------------------------------------------------------------------------------------+

No check star (the case of all three real runs): the CHECK tile reads "No check star [40] .
add one in Field [32]" and shows "comps 5 / 6 . consistent" as its value line.

Attention (replaces the first row; critical items also sound, 4.10):
+------------------------------------------------------------------------------------------------------------------------+
|  (!) ATTENTION  [66]   HFD 23.6 px = 2.7 x the first 20 frames (8.65 px), 3 frames in a row [40]  [Acknowledge]        |
+------------------------------------------------------------------------------------------------------------------------+
```

Rules for Watch:

- **Sizes** from section 2.5: primary values 88 px (21′ at 2 m on the 13-inch worst case),
  secondary values 66 px (16′), labels 32-40 px, chart ticks 24 px. Widths checked with the
  measured 0.60 em Plex Mono digit: "7.692" at 88 px is 264 px, "160 / 195" at 66 px is 356
  px, both fit a 1280 px window split in three (396 px per tile after padding). At 1280 x 800
  only the heights shrink (110 / 190 / 330 / 120 / 40 px); at narrower widths "UTC" and
  similar units move to the label line, values never shrink below 66 px.
- **What it shows is fixed** (positions teach meaning from afar): state, frames, last-frame
  age; latest target magnitude with error and band; check star scatter, comparisons used and
  verdict; end time; the curve; stars, HFD, altitude. No toolbar, no rail, no cursor
  readouts. The frame thumbnail is not shown by default (it adds light and says little at 2
  m); an option shows it at 320 px in the curve row, red-tinted in Night Red.
- **Truthful updates**: values change when data arrives, instantly, no counting animation,
  no smoothing; the last-frame age ticks once a second (it is a clock); the newest point
  is marked by a static ring, not a pulse. A value older than its expected cadence turns
  `--text-muted` with "as of 22:41" next to it.
- **Night Red**: everything from tokens, the curve in the single-hue role colours with
  marker shapes; attention by luminance, icon and word. A critical item is drawn as a 2 px
  outline with bold text, not a filled block (a large red fill is the brightest thing in
  the room). **Dim** (100 / 60 / 30 %) multiplies the whole view's luminance with a CSS
  brightness filter: hue is kept, so a red-only pixel stays red-only; the charter's
  non-pure-red tokens keep their ratio (BRAND 4.3 note).
- **Keys**: only `W`, `Esc`, `?` and `Mod+K` act in Watch. A key pressed to wake the
  screen must not take a Shot or start live view; every other single-key shortcut is
  ignored while Watch is open.
- **Actions**: Acknowledge, and Pause by hold-to-confirm (4.11). No Stop, no mount action:
  those need the observer at the table, in Run mode, where the consequences are shown.

### 4.8 Regions, presets and density (P10)

| Region | Behaviour | Remembered |
|---|---|---|
| Right rail | drag 360-580 px (420 default; 360 allowed in Run and Field where cards are read-only summaries), collapse `P` | per mode |
| Cards | fold / unfold; hide / show in the Panels popover; order fixed per mode | per mode |
| Band | `H` toggles; height computed (`layout.ts`), drag to shrink only | per mode (open state) |
| Drawer | `D` toggles, drag 160 px to 50 %, tab | per mode |
| Watch | dim level, thumbnail on / off | per viewer |

Density is a token set on the root (`data-density`), not a page zoom (webview zoom would
also shrink the image's share of the window and its chrome together, Q-G4):

| Density | Table / list rows | Card readouts | Run and Photometry key values | Use |
|---|---|---|---|---|
| Compact (default) | 24 / 28 px | 17 px (`--text-xl`) | 17 px | at the table, focused work |
| Comfortable | 28 / 32 px | 20 px | 26 px (about 20′ at 0.6 m, 16′ at 0.8 m) | late night, tired eyes, sitting back |
| Watch | none | none | 66-88 px | from 2 m (section 4.7) |

Comfortable changes rows and readouts only; toolbars, icon sizes and the image keep their
size. Rail cards adapt to the rail width with container queries (two columns of fields
above 400 px, one below).

### 4.9 Command palette (W6, P9)

`Mod+K` opens a token-drawn palette (Night Red safe, no native list). It searches one index
built from the shortcut registry (`keymap.ts` already holds ids, labels, keys and scopes),
the sections, the cards of every mode, the Settings keys (from config meta, A8), the stars of
the target set and the field variables, and the recent sessions.

```
                    +-- Command ---------------------------------------------------------- Mod+K --+
                    | > park                                                                       |
                    +------------------------------------------------------------------------------+
                    | ACTIONS                                                                      |
                    | [park] Park the mount                      Mount . hold, or Enter to confirm |
                    |        not now: the sequence is running (pause it first)                     |
                    | [unpark] Unpark the mount                  Mount                             |
                    | MODES AND VIEWS                                                              |
                    | [light-curve] Observe . Run                Alt+4                             |
                    | SETTINGS                                                                     |
                    | [settings] Observer & site . Site           opens the sheet at the field     |
                    | HELP                                                                         |
                    | [help] Guide: end of the night (darks, park)                                 |
                    +------------------------------------------------------------------------------+
                      Up / Down move . Enter run . Tab details . Esc close (and aborts motion, D21)
```

- Every row shows its shortcut (teaching the keyboard) and, when disabled, the reason the
  button's tooltip would give.
- A hardware action from the palette never runs on Enter alone: Enter opens the same inline
  confirmation as the button (4.11). Navigation and display actions run at once.
- Matching is a small hand-written ranker (prefix, word starts, then subsequence), no
  dependency; recent commands first when the field is empty.

### 4.10 Attention for unattended runs (W7, P6)

Three levels, one list, the same everywhere: the status-bar attention chip (count and the
newest item), the Run card, Watch's first row, and sound.

| Level | Examples | Visual | Sound (default) | Repeats |
|---|---|---|---|---|
| Critical | run stopped on error (exposure timeout, autofocus not resumed in 120 s); a device lost during a run; server link lost; no new frame (rule below) | chip in `--danger` with icon and word; Watch row; Run card | three-tone alarm | every 30 s until acknowledged |
| Attention | HFD rise; star count drop; comparisons used below 3; ensemble back to "not ready"; disk space for under 30 min of frames; target below the altitude limit within 15 min | chip in `--warning` with icon and word | two tones, once | no |
| Info | run complete; autofocus done; target rose above the limit | chip neutral | one soft tone, once (off by default) | no |

Rules (computed by the server on each frame, so that every client agrees and an
acknowledgement is shared). Each message states the rule and the numbers, never an
interpretation alone:

| Rule | Default | Tested on the 2026-09-25 run **[data]** |
|---|---|---|
| No new frame | after max(2 x median start-to-start, median + 60 s) | median 51.5 s gives 111.5 s; the longest real gap was 74.6 s: no false alarm |
| HFD rise | HFD > 1.5 x median of the first 20 frames, 3 frames in a row | fires at frame 150, 22:16:14 UTC; no false alarm before |
| Star count drop | stars < 0.7 x median of the first 20 frames, 3 frames in a row | lowest single frame 0.70: no alarm; the degraded 2026-09-07 run (826 stars against about 3 500) would fire |
| Comparisons used | fewer than 3 for 3 frames in a row | frames 53, 186, 188, 190 and 192 had 2, never two in a row: no alarm; four of the five fall in the HFD event, a reason to keep the rule |
| Tracker lost | `frames_lost` > 0 for 3 frames (needs an event, see below) | not recorded |
| Altitude | below the site limit now (info, once) or within 15 min (attention) | not usable on this run: the Settings site was wrong (finding 3) |
| Disk | free space < frames for 30 min at the observed cadence | 16.6 MB per S30 Pro frame |

- **Sound** through the Web Audio API: short synthesized tones (no sound files, no
  dependency), volume and a per-level choice in Settings › Alerts (new category, owner
  decision); sound never carries information found nowhere else (BRAND 7). Sound is the only
  channel that reaches an observer in another room and it emits no light. WebKit and
  Chromium only allow audio after a user gesture: the sound context is armed when the
  observer presses Start sequence or Watch, and Settings has a "Test sound" button.
- **OS notifications** stay forbidden in Night Red (BRAND 4.3). Outside Night Red, and
  only when the ARGOS window is hidden, an opt-in OS notification for Critical items is an
  owner decision; in the Tauri app it needs `tauri-plugin-notification` (MIT or Apache-2.0,
  size not measured: a dependency proposal, not adopted). The web build would use the
  Notification API with the browser's permission prompt.
- **Keep awake**: while a sequence runs, the server holds a sleep assertion with tools the
  OS already has (macOS `caffeinate -i -w <server pid>`, Linux `systemd-inhibit`, Windows
  `SetThreadExecutionState` through `ctypes`): no new dependency. The display may still
  sleep; Watch may request a screen wake lock (`navigator.wakeLock`, Chromium; Safari 16.4+,
  WKWebView and WebKitGTK **untested**). Closing a laptop lid still sleeps most laptops: the
  preflight says so.
- **API additions**: WS `attention` `{id, level, rule, message, values, since, acked_by}`,
  `POST /api/attention/{id}/ack`; tracker fields `{anchors_used, frames_lost, shift_px,
  rotation_deg}` added to `frame_metrics` (A26) so "lost tracking" stops being invisible.

```
Status bar:   ... | REC RR Lyr 160/195 ETA 30m | [attention] 1 . HFD 18.3 px | Log
Popover (anchored on the chip, 420 px):
+- Attention -------------------------------------------------- sound <off|soft|normal> -+
| ATTENTION  22:16 UTC  HFD 23.6 px = 2.7 x the first 20 frames (8.65 px), 3 frames.     |
|            HFD 17.5, 17.6, 23.6 px; brightest pixel 48 592 ADU (median 58 824 before). |
|            [focuser Focus view]   [Acknowledge]                                        |
| INFO       20:04 UTC  Run started . 195 frames . ends about 22:54 UTC.  [Acknowledge]  |
| -------------------------------------------------------------------------------------- |
| Rules and thresholds: Settings > Alerts . acknowledged items stay in the Log           |
+----------------------------------------------------------------------------------------+
```

### 4.11 Safe patterns for hardware actions (W8, P8)

Classify by consequence, then choose the lightest pattern that prevents the accident:

| Class | Actions | Pattern |
|---|---|---|
| Reversible, frequent | zoom, layers, roles before a run, mode switch, fold | no confirmation; Undo toast (6 s) where data changes (spec 3.3) |
| Motion when idle | Slew, Centre, Unpark, tracking on, jog | labelled button, busy state, `Esc` aborts (spec, unchanged) |
| **Motion during a run** | Slew, Centre, Park, tracking off, jog, Sync | **server interlock**: `409 run_active` "The sequence is running: slewing now breaks the time series"; the UI disables the button with that reason and offers one explicit path, `[pause Pause the run and slew]` by hold-to-confirm |
| Ends a run | Stop sequence | dialog (spec 06 §2.3.6: says what is discarded and saved); in Watch, not offered |
| Physical, irreversible for the night | Park (closes the Seestar arm) | hold-to-confirm for the pointer; Enter opens the inline confirmation (spec, built) |
| Changes the measurement | exposure, gain, filter, aperture during a run; removing a comparison during a run | owner lock (A21), `409 run_active` (Q-R10), confirm (spec 3.3), unchanged |

```
Hold to confirm (pointer; 700 ms; keyboard: Enter opens the inline confirmation instead)
  rest      [park  Park                ]   tooltip: "Hold to park . Enter to confirm"
  holding   [park  Park  ======-------- ]   "Release to cancel"      (reduced motion: 4 steps)
  done      [park  Parking...  (spinner)]   then the mount badge says Parked
  released  back to rest, nothing sent

Interlock during a run (Mount card, Slew)
  [goto Slew]  disabled  "The sequence is running: slewing now breaks the time series."
  [pause Pause the run and slew]  (hold)    -> pauses at the frame boundary, then slews; the run stays Paused

Armed jog (spec D23)
  [jog-pad] J -> pad outlined "Arrows jog . armed"; blur, hidden tab or link loss stop every axis

Undo window (spec)
  toast: "Comparison 000-BCG-512 removed . [Undo] 6 s"
```

- Hold is chosen for Park and for Pause in Watch because the targets are single and large,
  the hand may be cold or gloved, and a trackpad tap in the dark is easy to make by
  mistake. It is never the only path: the keyboard and assistive technologies get the
  two-step inline confirmation (a timed hold is hard for some users).
- The progress fill is state feedback, not decoration; with reduced motion it advances in
  four steps.
- The interlock lives in the server (A30, A32, A33 and the tracking and park routes), so
  the palette, a second client or a future tablet cannot bypass it.

### 4.12 Keyboard-first flows

| Flow | Keys (existing in the registry unless marked new) |
|---|---|
| Shot, judge, adjust | `Alt+1` (new) Framing, `E` Shot, `A` auto stretch, `C` clipped pixels, Tab to Exposure, Enter commits |
| Identify and pick roles | `Alt+3` (new), `S` identify, `O` layers, band table: arrows, Enter = Inspector, role buttons by Tab (no single-key roles, Q-O26) |
| Start | `F3` Plan, `Mod+S` save, Tab to Start (no shortcut on purpose) |
| Watch the run | `Alt+4` (new) Run, `W` (new) Watch, `W` back |
| Handle an alert | `Mod+K` "ack", or the chip by Tab; `Alt+2` (new) Focus view |
| Find anything | `Mod+K` (new) |
| Safety | `Esc` aborts slew, jog, focuser move, and closes the top layer (D21) |

### 4.13 Night checklist (W9, P7)

The guide says the order of the night "is not obvious from the interface". The checklist
makes it visible, computed from server state; only the Seestar-app step is ticked by hand.
It is a popover from the status bar (and the palette), the top of the Connection screen,
and the Plan preflight (A64) for the run-related lines.

```
+- Tonight ------------------------------------------------------------- 6 of 11 -+
| [ok]    Seestar app: initialised, GoTo calibration, focus        ticked by you  |
| [ok]    Mount, camera, filter wheel, focuser ready                              |
| [ok]    Mount clock 0.4 s from this computer                                    |
| [warn]  Site: Settings and the mount disagree by 61.6 deg in altitude.          |
|         Check Settings > Observer & site.  [Open]                               |
| [ok]    Alt-Az . tracking                                                       |
| [warn]  Disk: 30 GB free . this plan needs about 3.2 GB . lid must stay open    |
| [ ]     Field identified (S)                                                    |
| [ ]     Target, 5 comparisons (3 at least), check star                          |
| [ ]     Sequence started . keeping the computer awake                           |
| [ ]     Darks 20 x 10 s, gain 80, Dark slot . biases 30 x shortest              |
| [ ]     Mount parked                                                            |
+---------------------------------------------------------------------------------+
```

- **Site against mount** (new, finding 3): at connection and every few minutes, compute the
  altitude of the mount's own RA / Dec from the Settings site and the computer clock, and
  compare it with the altitude (and azimuth) the mount reports. More than 5° apart: warning
  with both numbers. The threshold comes from the owner's sessions: 0.1-2.1° on the two
  nights where the site was right, 61.6° at the start of the 2026-09-25 run and still 6.0° at
  its end **[measured]**. When the driver exposes `SiteLatitude` / `SiteLongitude`
  (`telescope.py:199`), compare them directly too. The same check also catches a computer
  clock off by tens of minutes (the sky turns 15° an hour).
- **Disk** (new): frames x frame size (16.6 MB S30 Pro, 4.1 MB S30 / S50) against free space;
  with the observed cadence when one exists.
- **Calibration** (new): counts dark and bias frames matching tonight's light exposure and
  gain in tonight's session folders.

### 4.14 Wrap-up (W10, P11)

When a run ends, the Run card (and Plan's outcome strip, 06 §2.4) turns into the next steps:

```
| v (nav-sequencer) Run            o Complete                          |
|   RR Lyr . 195 frames . 20:04-22:54 UTC . end of run: nothing        |
|   Tracking is still on.                                              |
|   CALIBRATION FOR TONIGHT'S LIGHTS                                   |
|   [start Take 20 darks]   10 s . gain 80 . Dark slot                 |
|                           about 17 min at tonight's 51 s cadence     |
|   [start Take 30 biases]  shortest exposure . gain 80 . Dark slot    |
|   [park Park]  (hold)          [disconnect Disconnect]               |
|   Session 20260925T200453Z_RR_Lyr . 3.0 GB      [browse Reveal]      |
```

- The dark and bias buttons start a one-step sequence prefilled from the run (same exposure
  and gain, Dark slot, the guide's counts 15-20 and 20-30); the estimate uses the observed
  cadence, not the exposure alone (finding 1).
- Park keeps the hold pattern; Disconnect has no confirmation once nothing runs (Q-C5).

### 4.15 Review the morning after (W11, P12)

```
R0 Sessions, grouped by night (newest first)
| v Night of 2026-09-25 . RR Lyr . 7 runs                                                    |
|     20:04 UTC  RR Lyr  195 lights . IR . 10 s . 1 target, 6 comparisons . consistent       |
|     > 6 short runs (1-5 lights, 19:47-20:03 UTC) . LP x5, IR x1      [show]                |
| > Night of 2026-09-07 . XX Cyg, RR Lyr . 5 runs                                            |
| > Night of 2026-08-29 . XX Cyg . 5 runs                                                    |

R1 health strip (56 px, above the plot wall, shares the wall's time axis)
| frames  |||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||| no gap > 2 x cadence|
| HFD     ___________________________________________/~~~~~~~~~  > 1.5 x baseline from 22:14 |
| comps   5 5 4 5 3 5 5 4 4 5 3 ...                                frames with 2 comps: 5    |
| site    Settings site and mount altitude disagree (61.6 deg): airmass column not reliable  |
```

- Runs of fewer than 10 frames fold under the night (not hidden, not deleted).
- The health strip states rules and numbers, never "bad data". Clicking a band selects its
  time range on every facet (uPlot cursor sync).
- The site line comes from comparing the frames' `ALTITUDE` keyword with the altitude
  computed from `SITELAT` / `SITELONG`; the AAVSO export dialog repeats it next to the
  `AMASS` column preview.

### 4.16 Devices (P13)

| Device | Where it is used | What changes |
|---|---|---|
| Laptop 13-16 inch, 1280 x 800 to 1512 x 982 | everything, at the table | the reference; Watch for the distance |
| External monitor indoors, 1920 x 1080 to 2560 x 1440 | Plan, Review, a long run watched from a desk | at 1800 px and wider, Run mode places the curve and conditions side by side in the band and the rail widens to 480 px; Review shows three wall columns |
| Tablet (later) | Watch only, on the same Wi-Fi or hotspot | read-only Watch plus Acknowledge and Pause (hold); needs the server bound to the LAN with a paired token (today it binds 127.0.0.1, `argos/server/__main__.py:54`): a security review first; nothing leaves the local network |
| Phone | Seestar app (T2) | none in ARGOS |

---

## 5. What to change in the spec and the current screen

| # | Change | Spec today | Current Observe | Decision needed |
|---|---|---|---|---|
| C1 | Observe gets four task modes (layout presets); card order is fixed per mode | "Foldable cards, fixed order per screen" (README 1.1); Panels popover per section | one layout | owner |
| C2 | The band under the image becomes mode-dependent (BRAND 11.1 amended: levels strip in Framing only) | levels strip always | levels strip always | owner + design |
| C3 | Run card with Pause / Stop in Observe › Run | sequences owned by Plan, status-bar chip only on Observe (README 1.4, D18) | none | owner |
| C4 | Run-mode light curve: target and check as two facets in the band; drawer tab stays for other modes | D25 drawer tab, 2 series | none | design |
| C5 | Watch view (`W`) | none | none | owner |
| C6 | Attention system, sound, Settings › Alerts, keep-awake; OS notification opt-in outside Night Red | no OS notification in any build (README 3.2) | none | owner (new category, notification plugin) |
| C7 | Server interlock of mount motion during a run, with "Pause the run and slew" | no confirmation for GoTo, Centre, tracking (README 3.3) | none | owner + server team |
| C8 | Hold-to-confirm for Park and for Watch's Pause; inline confirmation kept for the keyboard | inline confirm for Park | inline confirm (built) | design |
| C9 | Command palette `Mod+K` fed by the shortcut registry | none | none | front-end |
| C10 | Density setting (Compact, Comfortable) through tokens | Q-G4: no UI scale in v1 | none | owner (revisits Q-G4) |
| C11 | Mount Target block open only in Framing; one-line folded summary elsewhere | always in the Mount card | always open, about 165 px | design |
| C12 | Comparison candidates table and Inspector; compact on-image star card | Recommend popover, Ensemble tab, star card with details (D8, 03 W3) | none yet | owner (Δ(B−V) use) |
| C13 | Night checklist with site-against-mount, clock, disk and calibration checks; preflight additions | first-run checklist (Q-G11) | none | owner + server team |
| C14 | Review groups runs by night and folds runs under 10 frames; health strip | flat session list (07 WF-A) | none | owner |
| C15 | API: `attention` event and ack route, tracker fields in `frame_metrics`, site check, `b_minus_v` and `neighbours_in_aperture`, disk need in preflight | not in API v2 | — | server team |
| C16 | Front-end details seen on the spike: Slew keeps its brass fill while slewing; Camera "In use" repeats the fields; Connection card still in the rail (D10) | — | `slew-1280x800.png`, `live-1440x900-*.png` | front-end |

Unchanged on purpose: five sections, NavRail, status bar contents (D18) plus the attention
chip, the single window (D27), the shortcut map apart from `W`, `Mod+K`, `Alt+1-4`, the
`Esc` rule, the role shapes, Night Red rules, the drawer and its Log tab.

---

## 6. What the installed libraries already allow

Checked in `web/node_modules` (uPlot 1.6.32, Svelte 5.57.3); no new npm dependency is needed
for any proposal above.

| Need | How, with what is installed | Note |
|---|---|---|
| Linked time cursor across facets (Run band, Review wall, health strip) | uPlot `cursor.sync` (`uPlot.d.ts:592`) | one sync key per screen |
| Role shapes in plots (circle, square, triangle) | uPlot `points.paths` custom point builder (`uPlot.d.ts:824`) | Night Red: shape carries identity |
| Error bars, hatched periods (HFD rise, pauses) | uPlot `hooks.draw` on the canvas | colours read from tokens at draw time |
| New points without resetting a manual zoom | `setData(data, false)` then keep the x scale | README 3.13 rule |
| Panel resize and fold with reduced motion | `Tween` / `Spring` from `svelte/motion`, `prefersReducedMotion` | durations from tokens, zero when reduced |
| Breakpoints and density | `MediaQuery` from `svelte/reactivity`; CSS container queries for cards | container queries: check the WebKitGTK version shipped on Debian |
| Hold-to-confirm, resize handles | Svelte attachments (`svelte/attachments`) or actions | pointer and keyboard paths both |
| Row re-sort in the candidates table | `flip` from `svelte/animate`, 120 ms, zero when reduced | orientation only, values never tween |
| Alert sounds | Web Audio API (`AudioContext`, oscillators) | armed by a user gesture (WebKit and Chromium policy) |
| Screen awake in Watch | `navigator.wakeLock` | WKWebView and WebKitGTK untested |
| OS notification (opt-in) | Tauri `tauri-plugin-notification` | dependency proposal: MIT or Apache-2.0, size not measured |

---

## 7. How to validate (with the owner, on a real night)

1. **Distance test**: Watch at 1440 x 900 on the owner's laptop, Night Red, screen at the
   brightness actually used, at 1, 2 and 3 m; read the state, frames, magnitude, end time.
   Adjust the 88 / 66 / 40 px sizes until 2 m reads without effort.
2. **Alert rules replay**: run the section 4.10 rules over every session in
   `~/Argos/sessions` and list each firing; the owner marks true and false alarms before any
   threshold ships.
3. **Mode switching**: time a full framing-to-start cycle (T4-T9) with and without modes,
   against the seven-start evening of 2026-09-25.
4. **Hold-to-confirm**: gloves and a cold trackpad; count accidental Parks (target zero)
   and failed intended holds.
5. **Site check**: replay the three nights' FITS headers; the check must flag 2026-09-25
   only.
6. **WebKit**: Watch, sound arming, wake lock, container queries and the palette in
   WKWebView (macOS) and WebKitGTK (Debian), not only Chrome.
7. **Screenshots** at 1440 x 900 and 1280 x 800 in the three themes for every mode and for
   Watch, with the brass budget counted (BRAND 8: about eight marks while observing).

---

## 8. Limits of this study

- No observation of a real night; tasks, distances, glance frequencies and durations marked
  [assumption] come from the guide, the code and three nights of files, not from watching
  the owner work.
- The session evidence is one observer, three nights, Qt 0.4.x. It shows what happened in
  the files, not what was on screen or why runs were stopped.
- The type sizes rest on ISO / ANSI reading minima for photopic vision and on measured font
  metrics; dark-adapted (mesopic) reading of dim red text is worse and must be tested.
- Nothing here was prototyped; nothing was checked in WebKit. The wireframes are proposals
  for the visual team to draw and the front-end team to estimate.
- The alert thresholds were checked against one long run; they are starting points.

## Appendix: additions implied

| Kind | Addition |
|---|---|
| Shortcuts | `W` Watch (global); `Mod+K` palette (global); `Alt+1-4` Observe modes (matched on `code`) |
| Icons (inventory first, BRAND 12) | `watch` (glance view: a window holding one large reading; no digits, no eye, which is reserved for `nav-imaging`), `attention` (the status chip and alert rows; the inventory has no warning glyph today), `inspector` (optional). In wireframes `[eq]` is the existing equipment connect / disconnect button. |
| Settings | new category Alerts (levels, sound, rules and thresholds, OS notification opt-in); Appearance › Density |
| Preferences | `argos.layout.observe.<mode>.*`, `argos.observe.mode`, `argos.watch.dim`, `argos.watch.thumbnail`, `argos.density` |
| API | WS `attention` + `POST /api/attention/{id}/ack`; tracker fields in `frame_metrics`; site check in the status record; mount-motion interlock `409 run_active` with `pause_run` option; `b_minus_v`, `neighbours_in_aperture` on candidates; disk need and lid note in preflight; calibration counts per night |
