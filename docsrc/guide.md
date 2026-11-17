# Using ARGOS: a complete session

This guide covers one full observing session, from the settings you fill in
indoors to the folder you hand to Siril at the end. It assumes ARGOS 0.5.0, the
desktop app, and a Seestar telescope.

```{admonition} 0.5.0 is a beta, not yet used live on a telescope
:class: warning

The 0.5.0 interface was tested with ARGOS's simulator and with replays of real
nights recorded with a Seestar S30 Pro; it has not yet driven a real
telescope. Operate the telescope attended: there is no weather safety and no
restart recovery. Keep every raw FITS frame, and do not treat an ARGOS curve as
publishable without an independent reduction. What the live curve does and
does not mean is set out in {doc}`differential_photometry`.
```

## The night in seven moves

`````{grid} 1 2 2 4
:gutter: 2

````{grid-item-card} 1 · Indoors
Observer code, site, sessions folder, ASTAP. Resolve tonight's targets while
you still have internet.
````

````{grid-item-card} 2 · Seestar app
Power up, run the **GoTo pointing calibration**, focus. ARGOS does not replace
this step.
````

````{grid-item-card} 3 · Connect
**Connect all**: Mount, Camera, Filter wheel and Focuser must all read
*Ready*.
````

````{grid-item-card} 4 · Identify
Take a shot, **Identify field**, then click stars to make them Target,
Comparison and Check.
````

````{grid-item-card} 5 · Plan
Resolve the target, check its altitude, build the steps, read the Preflight,
**Start sequence**.
````

````{grid-item-card} 6 · Watch
Run mode at the table, **Watch** from across the room. A shift shared by every
star is weather.
````

````{grid-item-card} 7 · Review and hand off
Read the night back in **Review**, then reduce the raw frames in
[Siril](https://siril.org) and `star_var_script`.
````
`````

## 1. The five screens

Everything below happens in one of five screens, chosen from the rail on the
left. Learn them now and the rest of the guide has somewhere to hang.

| Screen | Key | What it is for |
|---|---|---|
| **Connection** | F1 | A two-minute setup stop: the telescope profile, the link to the Seestar, the four devices, the Stellarium bridge. |
| **Observe** | F2 | Where the night happens: the image, the camera, mount and focuser cards, the field overlays and the live curve, in four task modes (Framing, Focus, Field, Run). |
| **Plan** | F3 | The source, the steps of the sequence, its visibility, the Preflight and the run controls. |
| **Review** | F4 | After the run, offline: the sessions, their curves and frames, the batch re-run, the CSV and AAVSO exports. |
| **Settings** | F5 | Observer and site, instrument, plate solving, catalogues, photometry, alerts, folders, privacy, appearance. |

On a Mac keyboard the F-keys may need **Fn**; in the desktop app **⌘1** to
**⌘5** switch screens too. Hold **⌘** (**Ctrl** on Linux) alone and every
control with a shortcut shows its key; **?** lists them all, and **⌘K**
(**Ctrl+K**) opens the command palette, which finds every action and every
setting by name. **Esc** always aborts a slew. Actions that move or release
hardware (Connect all, Park, Tracking, the filter wheel, autofocus, Centre
target, Sync, Start sequence) have no single key on purpose: in the palette,
Enter opens a confirmation and a second Enter confirms.

The **status bar** at the bottom carries the four device marks, the Seestar
and internet reachability, the mount's state and position, the run chip, and
**Log** (**L**) with the count of unseen warnings and errors. The rail's
footer holds the **Help** menu (documentation, keyboard shortcuts, the command
palette, **Create support bundle…**, **About ARGOS**, full screen, **Quit
ARGOS**) and the theme button: **Observatory**, **Charcoal** and **Night
Red**, a strictly red theme for dark-adapted eyes (in full screen, nothing
else on the display lights up).

```{figure} ../docs/img/review-wall-night-red.webp
:loading: lazy
:alt: ARGOS Review in the Night Red theme: the plot wall of a recorded RR Lyr session, every plot, label and control drawn in reds on near-black.

The Night Red theme on the Review screen: every plot, label and control in
reds on near-black. This image, stored losslessly, passes ARGOS's Night Red
pixel audit: no pixel has more green or blue than red.
```

```{admonition} Prerequisites
:class: note

This guide assumes ARGOS and ASTAP are installed and linked. If not, do
{doc}`install` first; it takes twenty minutes and it is not a field task.

If a term goes past you, {doc}`glossary` defines every one this documentation
uses: AUID, check star, ensemble, zero point, green plane, TG, HFD and the rest.
```

## 2. Before you go out

Do this indoors, with internet. Catalogue lookups are cached, so what you
resolve now still works in the field with no connection.

**Settings › Observer & site.** Enter the **Observer name** and the **AAVSO
observer code**: without the code ARGOS refuses the AAVSO export. Search for
your site with **Find a place** (the only online step, when you press
**Search**), pick the right result, correct the elevation if you have a
measured one, and keep it in **Saved sites**. Without a site ARGOS computes no
BJD_TDB and no altitude curve, and frames carry no `SITELAT`/`SITELONG`: it
never uses 0°, 0° as a site.

When the mount connects, ARGOS compares where the mount points (altitude and
azimuth) with the direction computed from this site. More than 5° apart, the
site is not where the telescope is: the page shows both directions with an
Attention mark, and the same mark appears on the rail's Settings entry, in the
status bar ("Site ≠ mount") and on the Connection screen. Fix the site before
observing: the computed airmass, BJD_TDB and the FITS site keywords all come
from it.

**The telescope profile** is chosen on the **Connection** screen's
**Instrument** card. Select the telescope you actually own. The S30 Pro is the
reference profile, the one whose sensor ARGOS has measured; the S30 and S50 are
selectable but marked *unvalidated*: do not use them for precision photometry.

**Settings › Instrument.** If you have measured your own camera's gain with a
photon-transfer analysis, put the folder of its `camera_calibration*.json`
file in **Photon-transfer calibrations**: at a gain your file measures, ARGOS
then takes your electrons per ADU (and your read noise, when the file gives
it) before the profile's (0.228 e⁻/ADU at gain 80 for the S30 Pro). The
**Electron gain table** (Advanced) overrides both. Neither can
change while a sequence runs, so one curve keeps one error model.

**Settings › Data & storage.** Choose the **Sessions folder**: FITS frames,
the session record and the measurements are written there
(`~/Argos/sessions` by default). The catalogue caches are listed on the same
page; **Clear…** empties one (it asks first); the next search fetches it
again if the internet is there.

**Settings › Catalogues** sets what the field overlays may fetch (Gaia DR3
depth, SIMBAD and NASA queries when not cached). **Settings › Photometry**
holds the **AAVSO band** (`TG` by default) and the rules for picking
comparison stars. **Settings › Alerts** holds the alert sound and thresholds,
and **Keep the computer awake during a run**. In **Settings › Privacy &
diagnostics**, turn on **Save per-frame diagnostic records** only for a run
you intend to debug: those files stay in the session folder and are never
sent anywhere.

**Plan ahead.** While you still have internet, search tonight's targets in
**Plan** (section 6), so their names and coordinates are in the cache.

```{admonition} Before you close the laptop
:class: tip

- [ ] Observer name **and** AAVSO observer code entered
- [ ] Site saved, elevation corrected
- [ ] Telescope profile on the Connection screen matches the telescope you own
- [ ] Sessions folder chosen, with room for the night
- [ ] Tonight's targets resolved, so their coordinates are in the cache
- [ ] **Settings › Plate solving** confirms the ASTAP program *and* the star
      database
```

## 3. Start the telescope in the Seestar app

Every night begins in the official Seestar app: power and initialise the
telescope, then complete its **GoTo pointing calibration** before connecting
ARGOS.

Do the initial focus there too. ARGOS's autofocus works and can refocus during
the session, but ARGOS does not replace the official app's start-up procedure
or its pointing calibration.

Check the telescope's date and time in the app as well: when the mount's clock
is more than 60 s from the computer's, ARGOS refuses GoTo, Sync and Center and
says by how many hours the clock is off. Correct it in the Seestar app, then
reconnect.

## 4. Connect

```{figure} ../docs/img/connection.webp
:loading: lazy
:alt: The ARGOS Connection screen with the simulator connected: four of four devices ready (mount, camera, filter wheel, focuser), the Seestar S30 Pro profile, the site check agreeing with the mount, and the Link card.

The Connection screen, here with the built-in simulator as the link: four of
four devices ready. Captured with a test configuration, not at a telescope.
```

1. On the **Instrument** card, check the telescope profile and the site.
2. On the **Link** card, choose **Seestar (Alpaca)**. Enter the **Seestar
   address** and the **Alpaca port** (`32323`; the address is `10.0.0.1` in
   the Seestar's own access-point mode), or press **Discover**, which searches
   the network and offers a choice when several devices answer. A typed value
   is saved when you press Enter or leave the field.
3. Press **Connect all**. Mount, Camera, Filter wheel and Focuser must all
   read *Ready*; the toolbar then says "4 of 4 devices ready" and the button
   reads **Equipment ready**. A device that fails shows the full error on its
   row, with **Retry**; **Connect all** again connects only what is not
   connected yet and leaves the others alone.
4. **Disconnect all** asks first while an exposure, live view, a slew, a
   sequence or an autofocus runs; **Cancel** leaves it running.

The **Planetarium** card starts the Stellarium bridge (**Start bridge**), so
Stellarium's telescope control can point the mount. **Look up target names
online after a GoTo** is off by default. The log at the bottom shows the
connection lines; **L** widens it to every topic.

Networks, tethering and offline use are covered in {doc}`field_connectivity`.

## 5. The order of the night

This is the sequence, and it is not obvious from the interface. Read it once
before your first session.

```text
Connection   Connect all · four devices Ready
     │
Observe      Framing  Take shot (E) → check the framing and the exposure
     │       Focus    Autofocus, if the Seestar app's focus has drifted
     │       Field    Identify field (S) → the frame is identified
     │                click the target → role buttons
     │                Recommend… → comparisons · click a check star
     │
Plan         Source · steps · Preflight · Start sequence
     │
Observe      Run (Alt+4) at the table · Watch (W) from across the room
     │
Review       the session · Re-run photometry… · Export AAVSO… / Export CSV…
```

Two points worth stating plainly, because getting them wrong costs a night:

**Choose the target before you press Start.** The target set is what makes a
sequence produce a light curve. A run identifies its field by itself on its
first frame, even with no identification made before, but without a target its
frames are saved with no measurement. Nothing is lost: **Review › Re-run
photometry…** can measure them later, but you will not see the curve during
the night.

**The frame you identify comes from Take shot.** In Observe's toolbar,
**Take shot** (**E**) is a split button: its face says the frame type and
exposure it will use, and its menu sets them. Take a *Light*: it is what you
check the framing and the exposure on, what you identify, and the *pilot
frame* on which comparison stars are measured.

## 6. Plan the sequence

```{figure} ../docs/img/plan.webp
:loading: lazy
:alt: The ARGOS Plan screen: a single step of 62 ten-second IR frames for RR Lyr, the star's altitude through the night with the planned run marked above the 30° limit, and the run options and target set beside it.

A plan for RR Lyr: one step of 62 × 10 s frames through the IR filter, the
star's altitude through the night with the planned run above the 30° limit,
and the Source, Run options and Target set cards. Test configuration, at the
simulator's default site.
```

The **Plan** screen has the steps in the centre, the night's visibility under
them, and three cards on the right: **Source**, **Run options** and **Target
set**.

1. In **Source**, choose the programme (**Variable star**, **Exoplanet** or
   **Other**) and search (**/** focuses the field). Messier, NGC and IC names
   resolve offline from the bundled catalogue, ignoring case and spaces; other
   names go to CDS once and are cached.
2. The result becomes the observation's object and the mount's target. Plan
   never slews: point the telescope from Observe's **Mount** card (**Slew**),
   or with Stellarium.
3. **Visibility** plots the target's altitude across the night, with the
   twilights and the site's minimum altitude, and the planned run on top. It
   needs a site.
4. Build the steps: **Type** (Light, Dark, Flat, Bias), **Filter**,
   **Exposure**, **Gain**, **Count**, and optionally **Interval**, **Cadence**
   and **Dither** (equatorial mounts only). **Insert** adds a row, **⌘D**
   duplicates it, **Delete** removes it (with Undo). A value out of range is
   kept as typed and listed as an issue with the reason, never cut silently.
   The **Duration** column and the end time are estimates: leave margin.
5. **Run options**: **Object (FITS)** is the scientific identifier written to
   `OBJECT`, into the file names and into the target set; it is *not* the
   session name. **Repeat**, **Autofocus every** N frames, **End of run**
   (Nothing, Stop tracking, Park mount) and **Start (UTC)** are here too.
6. **Presets ▾** opens a saved plan; **Save…** (**⌘S**) saves one as JSON.
7. The readiness chip opens the **Preflight**: one row per check (camera,
   mount, site, filter wheel, focuser, altitude, output folder, disk space,
   calibration frames, the telescope's lid, the computer's sleep), each *OK*,
   *Note* or *Blocks*. Only a block stops Start.
8. **Start sequence** starts now; its menu starts at a UTC time. **Pause**
   finishes the exposure in progress, saves it, then holds; **Stop** asks
   first. While a run is engaged the plan is locked and each row shows its
   progress; the target set stays editable.

A mount move asked during a run is refused; Observe then offers **Pause the
run and slew**, behind a hold-to-confirm control.

```{tip}
Keep the acquisition settings stable through a time-series run. Changing
exposure or gain mid-run changes the instrumental system you are measuring in.
Light steps through two filters give each star one curve per filter, and the
Plan says so.
```

### What to actually put in those boxes

The step table asks for numbers and does not suggest any. Here is a defensible
starting point, **a starting point, not a recommendation for your target**.
Take a shot and check it before committing the night.

| Setting | Start with | Why |
|---|---|---|
| **Filter** | **IR** | The IR-cut position is the broad one. `LP` narrows the passband, which changes what your instrumental green *is*; never mix the two in one run, and do not use `LP` for photometry unless you know why you are. |
| **Exposure** | 10–20 s | Long enough to be sky-limited rather than read-noise-limited; short enough that your target and comparisons stay unsaturated (on the RR Lyr night used in {doc}`validation`, stars of *V* 7.0 to 7.8 measured unsaturated in 10 s at gain 80) and that field rotation does not smear. ARGOS's own default is 10 s. |
| **Gain** | 80 | The gain at which the S30 Pro's electrons per ADU were measured (0.228 e⁻/ADU); other gains use a scaled value. A higher gain costs dynamic range: bright stars saturate sooner. |
| **Count** | enough to cover the event | For a variable: at least a full cycle for a short-period star, or two to three hours of a longer one. Below 10 valid points the run-level scatter is not estimated and your error bars are the formal ones only. |
| **Interval** | 0 | Back-to-back. Download already costs several seconds per frame. |

```{admonition} Check the peak, not the picture
:class: important

The one thing to verify on your test shot is your target's **peak ADU**: too
low and you are measuring noise; near the top of the range and you are
clipping the very star you came for. In **Framing** mode the band under the
image gives the brightest stars' peaks and says when one is clipped; in
**Field** mode the comparison candidates and the Inspector card give each
star's peak and SNR. Adjust exposure first, gain second.

ARGOS flags a point *saturated* when its aperture's brightest pixel reaches
the profile's linearity limit (50 000 ADU on the S30 Pro). Leave yourself a
margin below it.
```

```{admonition} How long is enough?
:class: tip

Scintillation alone puts roughly **0.014 mag** on a single 20-second sub of a
bright star through a 30 mm aperture at airmass 1.09, and 0.017 mag in 10 s at
airmass 1, no matter how bright the star (the values ARGOS's error model gives
on two real nights, release notes S74; that model is deliberately on the high
side). If the amplitude you are chasing is 0.3 mag, one frame sees it. If it is
0.02 mag, you need to average tens of frames and you need the night to
cooperate. Decide which case you are in before you drive somewhere.
```

### Calibration frames: take them, ARGOS will remind you

ARGOS applies no calibration. But **Siril will need** darks, biases and flats,
and the only chance to take them is while you are still out there. When a run
ends, its outcome card proposes darks and biases matching tonight's Lights,
with a time estimate, and **Prepare in Plan** writes them as steps.

The filter wheel makes two of the three easy: its first position is a physical
**Dark** slot, so darks and biases need no cap and no cover.

| Frame | How | How many (common practice, not an ARGOS check) |
|---|---|---|
| **Darks** | Filter `Dark`, *same exposure and same gain as your lights*, same temperature, so take them at the end of the run, not at home | 15–20 |
| **Biases** | Filter `Dark`, shortest exposure the camera allows, same gain | 20–30 |
| **Flats** | Needs an even light source over the *objective*: twilight sky, or a panel. The telescope is sealed, so there is no other way in | 15–20, at half saturation |

```{note}
Flats are the awkward one on a Seestar, and if you skip them Siril will still
calibrate with darks and biases alone. That is worth doing: darks remove the
hot pixels that can fake a dip in a single frame. Flats remove the vignetting
gradient, which matters most when your comparison stars are far from your
target, and is why ARGOS's automatic comparisons stay within 25′ of it by
default.
```

## 7. Observe

**Observe** is the session workspace. Its toolbar holds the task modes, then
**Open FITS** (**⌘O**), **Take shot** (**E**), **Live** (**V**), **Stop**,
**Autofocus**, the zoom and the display tools. The rail on the right holds the
**Camera**, **Mount** and **Focuser** cards, plus **Photometry** and the
**Run** card when they apply; **P** hides it. The drawer under the image
(**D**) holds **Conditions**, **Log**, and the photometry tabs.

| Mode | Key | What the band under the image shows |
|---|---|---|
| **Framing** | Alt+1 | The levels and the exposure check |
| **Focus** | Alt+2 | The autofocus V-curve and the HFD trend |
| **Field** | Alt+3 | The comparison candidates, the ensemble, the field's variables and Gaia stars |
| **Run** | Alt+4 | The live curve of the run and its small charts |

Each mode remembers its own layout; **Arrange** resets it. ARGOS never
switches mode by itself: when a run starts it *proposes* Run mode with a chip
on the image.

- **Camera card.** Exposure, gain, frame type and filter. Offset and binning
  are under **Sensor**. A typed value is applied when you press Enter or leave
  the field, not at each keystroke.
- **Mount card.** RA, Dec, altitude, azimuth and tracking. Type an object name
  (offline names appear as you type) and **Slew**; **Park** needs a 0.7 s
  hold. **Esc** aborts a slew. The **Jog** section moves the mount by hand;
  **J** arms the arrow keys, and the mount stops when you release them or the
  window loses the focus. After an identification, **Centre target** and
  **Sync** use the solved field.
- **Focuser card and autofocus.** **Autofocus** is a split button: its menu
  sets the sweep's range and positions. **Stop AF** returns the focuser to
  where the sweep started; **Halt** stops it where it is. Autofocus is refused
  while the wheel sits on the Dark slot.
- **Darks and biases from Take shot.** A Dark or Bias shot turns the wheel to
  the `Dark` slot first and is refused while the wheel is turning elsewhere; a
  Light or Flat is refused while the wheel sits on `Dark`. The Seestar has no
  shutter, so a frame exposed while the wheel moved is never saved.
- **Open FITS** opens raw frames only (Argos `.fit` or any integer data from 0
  to 65535); a calibrated or stacked file is refused, because its photometry
  would be wrong.
- **Disconnect** and **Quit** ask first while a sequence or an autofocus runs.

```{important}
Display is not data. The stretch, the zoom, the rotation, the colour palettes
and the CFA preview change only what you see. The FITS written to disk is the
raw colour mosaic as the camera delivered it, with `BAYERPAT='GRBG'`.
```

## 8. Identify the field and choose the roles

In **Field** mode, **Identify field** (**S**) runs ASTAP on the frame on screen
(press it again to cancel). The chip on the image then says the plate scale and
the rotation, with a compass and a scale bar; the overlay draws the catalogue
layers (**O** lists them), the coordinate grid (**G**), labels (**N**) and the
target set: a circle for the target, a square for a comparison, a triangle for
the check star. **Keep the field identified automatically** identifies the
field again as frames arrive, once 20 s have passed since the last attempt or
as soon as the mount has moved 2′ (both defaults); a sequence arms it by
itself.

```{figure} ../docs/img/observe-field.webp
:loading: lazy
:alt: ARGOS Observe in Field mode on a replayed frame of the RR Lyr field: the frame identified at 3.67″/px, RR Lyr circled, five comparison stars in squares and the check star 000-BCG-523 in a triangle among the VSX variables, with the comparison-candidates table below.

Field mode on a frame of the RR Lyr field, identified at 3.67″/px: RR Lyr
circled, five VSP comparison stars in squares, the check star 000-BCG-523 in a
triangle, and the comparison candidates in the band below. Captured from a
replay of real frames (2026-09-25) through ARGOS's simulator.
```

Click a star. Its card shows its identity and one line of facts (magnitude,
colour, distance from the target, catalogue); the details are in the
**Inspector**. Its role buttons make it the **target**, a **comparison** or
the **check** star; **Remove from the set** takes it out. The role buttons stay
unavailable until the field is identified: a wrong solution gives a wrong
identity. Every change can be undone from the toast that follows it.

| Role | Scientific meaning |
|---|---|
| **Target** | The variable or transit host whose differential magnitude is measured. |
| **Comparison** | A reference star of known magnitude that builds the ensemble zero point. |
| **Check** | A star expected to be constant, measured against the ensemble to expose its drift. |

The **Photometry** card (right rail) shows the set, the target's newest
magnitude, the check star's scatter and its offset from its catalogue *V*, the
comparisons used on the newest point, the aperture geometry and the ensemble's
verdict. **Recommend…** proposes comparisons from the AAVSO VSP sequence,
measured on the pilot frame: **Complete ensemble** adds the missing ones up to
the count, **Replace VSP picks** replaces ARGOS's earlier picks and keeps the
ones you chose by hand.

```{admonition} How many comparison stars? Aim for five.
:class: important

Three different numbers appear in **Settings › Photometry**, and they mean
three different things:

| | |
|---|---|
| **2** (**Minimum comparisons**) | Below this a measurement is *annotated*, not hidden. It is a floor, not a target. |
| **3** | Fewer than three *stable* comparisons and the ensemble verdict reads *not ready*. Rejecting an outlier needs three as well. |
| **5** (**Automatic comparison stars**) | What **Recommend…** proposes, and the right thing to aim for. |

ARGOS weighs each comparison by its own error, so a faint one counts for
less, and it names a comparison that sits beside a brighter star of the set.
How the ensemble is built and clipped is in {doc}`differential_photometry`.

One more thing the interface will not decide for you: **match their colour to
your target.** The zero point differences a catalogue *V* magnitude against an
instrumental green one, so a colour mismatch drifts through the night looking
like variability. The Field band lists each candidate's *B−V* and its
difference from the target's: prefer the closest.
```

Outside a sequence, every new identification of the field gives one live
point. A frame on which the stars of the set are not where the solution puts
them gets no point, and the log says why.

Selecting stars in a crowded field, catalogue depth and what an unmatched source
means are covered in {doc}`field_identification`. For a transit, see
{doc}`exoplanet_transits`.

## 9. Run, watch, and read the live curve

```{figure} ../docs/img/observe-run.webp
:loading: lazy
:alt: ARGOS Observe in Run mode during a replayed run of the RR Lyr field: RR Lyr circled, the comparison stars in squares and the check star in a triangle on the identified frame, the run's progress and the photometry card in the right rail, and below the frame the live light curve of RR Lyr with the check star's curve under it.

Run mode during a run, frame 15 of 62: the Run card (progress, last frame's
age, end time, cadence, Pause, Stop), the Photometry card (here naming a frame
that got no point because its anchor stars were not where the tracker put
them), and the live curves of RR Lyr and of the check star as *check − V*.
Captured from a replay of real frames (2026-09-25, every third light) through
ARGOS's simulator with a test configuration: the time axis is the replay's,
not the night's.
```

Once the run has started, switch Observe to **Run** (**Alt+4**). The band under
the image carries the run's live curve, and the **Run** card its state: frames
done of the total, the age of the last sub against the cadence, the end time,
the next autofocus, **Pause** and **Stop**.

The drawer's **Light curve** tab is the full plot: the target, the check star
as *check − catalogue V*, and the ensemble's zero point. Flagged points are
drawn by their shape, never as good data: hollow for *suspect*, a cross for
*saturated*. The time axis switches between UTC, JD and BJD. With the plot focused
(click it), **U** toggles the error bars, **M** shows relative flux and **F**
fits the whole run; **Copy data (TSV)** copies what is plotted. The **Ensemble** tab is the comparisons'
leave-one-out report, and **Variables** lists the field's VSX variables.

What ARGOS does with a doubtful frame, as it measures it:

- a frame on which the anchor stars are not where the tracker puts them (a
  field jump, a cloud) gets **no point**;
- a target measured below SNR 3 is flagged **suspect, no detection**;
- a point whose tracking was checked on fewer than three stars, far from a
  fresh plate solution, is flagged **suspect**; so is a hot pixel faking a
  peak;
- flagged points stay in the CSV and never reach an AAVSO report; points
  without a detection are also left out of the run-level scatter (a re-run
  also leaves out the points without a verified field and the off-centre
  rows; saturated and other suspect points stay in it).

The error model (the electrons per ADU, the noise model) and the aperture
geometry are locked while the run lasts, so one curve has one error model.

```{admonition} Reading the curve honestly
:class: important

The error bars include the photon, sky and read noise, the error of the sky
estimate, the scintillation, the zero point's own error, and, once a curve has
10 valid points, a run-level systematic floor measured from the curve itself. But the measurement is still
on **uncalibrated** sub-exposures in an instrumental band. A dip you can see is
worth reducing properly; a dip at the level of the scatter is not a detection.
The method, and its limits, are in {doc}`differential_photometry`.
```

A shift common to the target, the check star and the zero point means cloud,
tracking, focus or saturation, not variability.

**Watch** (**W**) turns the window into a view you can read from two metres:
the run's state, frames done, the last frame's age, the target's magnitude,
the check star, the end time, the curve, the star count, the HFD and the
altitude. **Dim** lowers it to 60 % or 30 %; **Pause** needs a hold; nothing
else acts on a key press there except **W**, **Esc**, **?** and **⌘K**, so a
key pressed to wake the screen never takes a shot. While Watch is shown the
screen stays on.

**Attention.** ARGOS watches the run frame by frame and raises an item when a
rule is crossed: no new frame for too long (*critical*), the HFD rising, the
star count dropping, too few comparisons used, the target nearing the site's
minimum altitude, the disk filling up. Items appear as a chip in the status
bar, in the Run card and in Watch, with a sound (**Off**, **Soft** or
**Normal**; a first click arms it). Acknowledging one in any window clears it
everywhere. The thresholds are in **Settings › Alerts**. During a run ARGOS
also keeps the computer awake, but a closed lid still sleeps most laptops:
the Preflight says so. None of this is weather safety.

**When the run ends**, the Run card shows its outcome: what the run produced,
the alerts it raised, the tracking state, the darks and biases to take now
(**Prepare in Plan**), **Park** by a hold, and the session folder.

```{warning}
Comparison curves are diagnostics. Never submit one as an AAVSO observation.
```

## 10. What ends up on disk

A sequence is organised for Siril under the sessions folder:

```text
<sessions>/
└── <UTC start>_<OBJECT>/
    ├── lights/                     (darks/, flats/, biases/ when the run takes them)
    ├── session.json
    ├── observation.json            (a prepared transit's planning record)
    ├── targets.json
    ├── photometry/<role>_<OBJECT>_<filter>_<star>.csv
    ├── photometry_quality.json
    └── diagnostics/                (with Save per-frame diagnostic records on)
```

`photometry_quality.json` is the leave-one-out assessment of the comparison
ensemble described in {doc}`differential_photometry`; a run through a second
filter gets its own `photometry_quality_<filter>.json`. The filter in the file
names is spelled as the frame names spell it (`ir`, `lp`, `v`, `clear` for
none). A Take shot is saved the same way, in a folder named by its own start
time.

Live curves measured outside a sequence are kept under `<sessions>/targets/`:
each has its own CSV, `<object>_<UTC start>_<filter>_<star>.csv`, so measuring
an object again never overwrites an earlier curve.

When you report an observation, keep the raw FITS, `session.json`, the CSV
exports and any diagnostic records together. Copy the whole session folder
before reducing it in [Siril](https://siril.org) and
[`star_var_script`](https://github.com/jperret21/star_var_script): the folder
layout is already the one Siril's sequence discovery expects. The naming rules
and the full header list are in {doc}`fits_headers`.

## 11. Review a finished session

**Review** (**F4**, or **⌘⇧O** from anywhere) opens on the sessions list: start
(UTC), object, lights, filters, curves, quality report and issues, newest
first. **Open folder…** opens a session folder from elsewhere, **Import CSV…**
reads a curve CSV, and **Open FITS** opens a single frame. While a sequence
runs, the live run sits above the list, read-only.

A session opens on a wall of plots sharing one time axis: the target, the
check star, the comparisons and the night's conditions, with a health strip.
The rail on the right holds the **Selected point**, **Ensemble**, **Session**
and **AAVSO export** cards; the drawer holds **Frames**, **Ensemble** and
**Log**. **←** and **→** step through points; **Enter** opens the selected
point's frame in the frame inspector, where **Page Up** and **Page Down** step
through the frames, the FITS header and a star measurement are a click away,
and **Alt+←** comes back.

```{figure} ../docs/img/review-wall.webp
:loading: lazy
:alt: ARGOS Review of a recorded session: RR Lyr's light curve, the frames' HFD, the check star and three comparison stars as separate plots, with the AAVSO export card and the comparison ensemble table in the right rail.

A session in Review: RR Lyr, the frames' HFD, the check star 000-BCG-523 and
the comparisons, each in its own plot on one time axis, with the AAVSO export
and Ensemble cards. The 62 frames are a replay of real frames (2026-09-25,
every third light) through ARGOS's simulator with a test configuration: the
curve's shape is the night's, compressed into 13 minutes; the time axis and the
airmass are the replay's, not the night's.
```

Review works with no telescope connected and never rewrites a file. When it
reads a run, it takes the target's airmass from each frame's header `AIRMASS`
(the mount's) and gives the comparison and check stars their own, computed for
a site fitted to the mount's pointing, and warns when the site the run was
recorded with does not match where the mount pointed. On a run recorded before
0.5.0 it also flags the points that now count as no detection, but only when
the run saved per-frame diagnostic records (**Settings › Privacy &
diagnostics**, off by default); otherwise re-run the photometry first.

```{figure} ../docs/img/review-frame.webp
:loading: lazy
:alt: The ARGOS frame inspector in Review: one recorded light of the RR Lyr field with its coordinate grid, the frame's exposure and time, its plate solution at 3.67″/px, and below it the session's light curve with the point of this frame ringed.

The frame inspector, opened from a point (Enter): light 18 of 62 with its
coordinate grid and plate solution, and the session's curve below with this
frame's point ringed. Same replay; its time and airmass are the replay's.
```

**Re-run photometry…** measures the session's light frames again with the
current code: one aperture for every frame, the session's target set, the
first frame identified with ASTAP (or the live solution, when one exists). It
writes a new `photometry_rerun_<UTC>/` folder and never touches the earlier
files; a cancelled re-run saves no curve. A frame on which the field jumped is
identified again; when that fails, its points are flagged suspect. Re-run any
session recorded before 0.5.0 whose errors you want to use: the 0.5.0 error
model differs (see {doc}`release_0_5_0`).

**Export CSV…** writes the measurements with their roles; **Export AAVSO…**
writes the report (next section). Both write either a file (by default in the
session folder; **Browse…** chooses another; an existing file is replaced only
after you confirm) or a download into your Downloads folder, and a notice names
the file.

## 12. Can I submit this to the AAVSO?

The documentation warns you repeatedly not to treat a live curve as a
publishable measurement, and then offers an **Export AAVSO…** button. Both are
right, and here is how they fit together.

**What the export is.** An AAVSO Extended File Format report: your observer
code, `#SOFTWARE=Argos v0.5.0`, one row per point of the **target** with its
differential magnitude and uncertainty, `DATE` as JD UTC at mid-exposure
(which is what AAVSO asks for), the band `TG`, `CNAME=ENSEMBLE` and
`TRANS=NO`, an explicit declaration that the magnitudes are untransformed. A
comparison or check curve can never leave through this door as an observation.

- **Left out, and counted in the dialog:** points flagged *saturated*,
  *suspect* or *no detection*, and points with no valid time or magnitude. They
  stay in the CSV.
- **Written, with a warning:** on a run recorded before 0.5.0, the points
  whose tracking was checked on fewer than three stars. Re-run the session
  first: the re-run verifies those frames with a plate solve (S58).
- **One filter per report:** with curves in two filters, the dialog asks which.
- **`KNAME`/`KMAG`:** your check star's AUID (else its name) and its ensemble
  magnitude on the same frame, never from a flagged check point (`na` then).
- **`CHART`:** the VSP chart your comparison stars came from, `na` when the
  ensemble mixes a star picked by hand or two charts, and for a run recorded
  before 0.5.0, which recorded no chart (S68). The dialog's **CHART** field
  takes a chart you type.
- **`AMASS`:** the target's airmass. For a session opened in Review it is
  each frame's header `AIRMASS` (the mount's), and a 0.5.0 re-run writes the
  same value into its CSV; `na` when there is none.
- **`MERR`:** the point's error, including the run-level floor. For bright
  stars it is deliberately on the high side (see {doc}`release_0_5_0`).
- **Refused** without an observer code, or for a curve whose star or role
  ARGOS cannot identify.

```{figure} ../docs/img/aavso-export.webp
:loading: lazy
:alt: The ARGOS AAVSO export dialog: 59 RR Lyr rows with the check star 000-BCG-523, observer code TST, filter TG, the VSP chart X43374ACY, and a preview of the AAVSO Extended File header naming Argos v0.5.0.

**Export AAVSO…** shows what it will write before it writes it: the filter,
the target's rows, the check star, the observer code (here the test code
`TST`), `FILT`, `CHART`, the destination and a preview of the file. Same
replay: the `DATE`, `AMASS` and `MERR` in its preview row are the replay's, not
an observation.
```

**What it is not.** Calibrated. There is no dark, no flat, no bias and no colour
transformation, and the zero point is cross-band (green measured against
catalogue *V*). See {doc}`differential_photometry` for the full list.

```{admonition} The honest answer
:class: important

**Do not submit the live export as your observation of record.** Treat it as
what it is: a field check that the night worked, a preview to see whether the
star did anything, and a well-formed template of your own metadata.

The submission comes from the *reduction*: calibrate and register the raw
frames you kept, re-do the photometry there, and submit that. The raw frames are
the deliverable of an ARGOS night; the curve is the reason you know the night
was worth reducing.

If you do submit an ARGOS-derived measurement, describe how it was obtained:
uncalibrated sub-exposures, untransformed TG against V sequence magnitudes.
ARGOS writes `na` into the `NOTES` column, so you have to add that yourself
before uploading. An observation with an honest note is useful. An uncalibrated
observation presented as a calibrated one is worse than none.
```

Practical submission is through the AAVSO's own
[WebObs](https://www.aavso.org/webobs) upload; the file format is documented
under [Extended File Format](https://www.aavso.org/aavso-extended-file-format).
Neither is part of ARGOS. ARGOS's rows were checked field by field against that
format, offline; they have not yet been through the WebObs validator, and
whether the AAVSO accepts `#OBSTYPE=CCD` for a CMOS camera is unconfirmed.

## 13. Reporting a problem

Start with **Help › Create support bundle…** (also in **Settings › Privacy &
diagnostics**). The dialog says what the ZIP holds. It is created locally, at
your request, and contains redacted logs and, if you choose, the session's
metadata (off by default). It never includes raw FITS frames; site coordinates
are removed unless you ask for them. ARGOS never transmits it: check its
contents before sharing it.

A useful report names the exact version (**Settings › About**, **Copy version
info**), the platform, what you did, what you expected and what happened, with
the log lines around the failure (**L**, then save the log).

```{seealso}
- {doc}`field_identification`: working in a crowded field, catalogue depth,
  and what an unmatched source means.
- {doc}`exoplanet_transits`: what a transit run needs that a variable-star run
  does not.
- {doc}`field_connectivity`: networks, tethering, and observing with no
  internet at all.
- {doc}`glossary`: every term used here, defined once.
- {doc}`references`: every catalogue, standard and formula ARGOS relies on,
  with links.
```
