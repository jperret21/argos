# Argos 0.5.0 — data-integrity and hardware-safety fixes

> Branch: `release/0.5.0`, cut from the published `release/0.4.2`.
> Last updated: 2026-11-08.

A bug-fix release with no new features. Specifying the web UI meant taking an
inventory of the Qt code, and that inventory turned up defects that affect
0.4.2 users today: frames labelled with the wrong settings, a dark that is a
light frame, AAVSO rows naming the wrong star, a live curve that never gets a
point. The science items of that inventory (`web/spec/README.md` §6.1) that
were approved for this release were each reproduced on 0.4.2 before being fixed
here, with a regression test that fails on 0.4.2. Everything that
needs a redesign is left to the web-UI migration and listed at the end.

The hardware-safety items of the same inventory (§6.2, H1–H17) went through the
same process: fourteen are fixed here, each with a test that fails on the code
before it (H17 only needed the test: its fix was already on the branch), and
three (H1, H5, H16) are left to the web UI.

A review of the branch then found gaps in six of these fixes (S1, S3, S4, S10,
S23, H3) and two defects outside the inventory, both writing wrong values into
files: **X1**, found while verifying H7 (frames keep a disconnected mount's
pointing), and **X2**, found in the review (with no site set, latitude and
longitude 0/0 were used as the site). They are fixed here too, each with a test
that fails on the code before it.

One check was added after the review, **X3**: a site that is set but is not
where the telescope is (the site of an earlier trip, for example) went
unnoticed, and the airmass of the whole run was computed for it. The mount now
gets compared with the Settings site when it connects.

Porting the live photometry to the web UI (its wave 5) found four more defects
in the live measurement, each with a test that fails on the code before it:
**S31** (the first point of a series had its own aperture), **S32** ("Recommend
from pilot" emptied the comparison ensemble when no VSP star was known), **S33**
(a star whose role changed kept one curve for both roles) and **S34** (without a
site, an opened frame's point took the mount's current airmass). Its reviews
found five more, each with a test that fails on the code before it: **S35** (a
frame on which the field had moved since the solve was measured on blank sky,
with no flag), **S32** again (Recommend also emptied the ensemble when VSP stars
existed but none passed the pilot gate), **S36** (sequence frames' `DATE-AVG`
included half the download time), **S37** (offline, no point had a BJD_TDB) and
**S38** (a reader could see a live curve CSV half written).

**Several of these defects affect files you already hold.** The table says
which; *Check your old files* below says how to find them.

---

## Summary

| Item | Defect in 0.4.2 | Effect | Files you hold |
|---|---|---|---|
| S1 | A Dark/Bias **Take shot** never looked at the filter wheel | A light frame saved as `IMAGETYP='Dark Frame'` | **yes** |
| S2 | A Take shot's header was written from the form *after* the exposure | `EXPTIME`, `GAIN`, `IMAGETYP`, `FILTER`, `OBJECT` of the next settings | **yes** |
| S3 | A Take shot's `FILTER` came from the form, never from the wheel | Wrong `FILTER` after a sequence moved the wheel | **yes** |
| S20 | Take-shot QA headers came from the last *displayed* frame | `HFD`, `NSTARS`, `SKYLEVEL` of another frame | **yes** |
| S4 | **Open FITS** kept the previous frame's time and WCS, and wrapped a calibrated frame's pixels | A point dated with another frame's time, in the curve, its CSV and AAVSO; points measured on wrapped pixels | **yes** |
| X1 | The mount's last polled position outlived a disconnect or a lost connection | Frozen `RA`, `DEC`, `ALTITUDE`, `AZIMUTH`, `AIRMASS` in the frames saved meanwhile | **yes** |
| X2 | With no site set, latitude and longitude 0/0 were used as the site (0.4.1, 0.4.2) | Live and batch airmass (CSV `airmass`, AAVSO `AMASS`) for 0/0; `SITELAT`/`SITELONG` 0 | **yes** |
| X3 | Nothing compared the Settings site with where the mount is | A wrong site's airmass (CSV `airmass`, AAVSO `AMASS`), `SITELAT`/`SITELONG` and `MOONALT` | **yes** |
| S22 | Autofocus never applied its gain | Worse or rejected autofocus | no |
| S23 | **Stop AF** could leave the focuser mid-sweep | Defocused frames after "Autofocus complete" | possibly defocused frames |
| S5 | The Plan editor dropped a transit's planning metadata | No `observation.json` for any run started from the UI | **yes** |
| S7 | A Light step could default to the wheel's opaque **Dark** slot | Whole steps of black frames | **yes** |
| S14 | Auto field identification was not armed for a run without a WCS | No live photometry for a run started after a GoTo | **yes** |
| S26 | Plan visibility used latitude 0 without a saved site | Wrong altitude curve (display) | no |
| S15 | Aperture spins stayed live during a sequence | One curve could mix two apertures | **yes** |
| S16 | Relative-flux median included saturated points | Biased normalised curve (display) | no |
| S17 | Comparison vetting ran only once a sequence had saved a frame | No vetting in live preview (display) | no |
| S18 | A ratio-only live point raised `TypeError` | Point missing from both plots; a crash report per point | no |
| S19 | Every point after the 10th re-rendered every curve, O(N²) | UI frozen for seconds per frame late in a night; zoom reset | no |
| S31 | The live series FWHM was frozen on the second measured frame, not the first | The first point of every series (each object, each run) measured with another aperture | **yes** |
| S32 | **Recommend from pilot** removed the VSP ensemble before knowing it had stars to replace it with | Comparisons gone from `targets.json` (unsolved field, catalogue not back, after a GoTo) | **yes** |
| S33 | A star whose role changed kept one live curve for both roles | A `check_*.csv` (or comparison one) starting with the other role's points | **yes** |
| S34 | Without a site, a point measured on an opened frame took the mount's current airmass | CSV `airmass` / AAVSO `AMASS` of replayed frames: tonight's mount altitude | **yes** |
| S35 | A frame on which the field had moved since the solve was measured on blank sky | Unflagged points of every star on such frames; a larger `sigma_syst` on every row of the run | **yes** |
| S36 | Sequence frames were dated with the download inside the exposure | `DATE-AVG` / `MJD-AVG` late by half the download time (seconds); BJD of Open FITS replays | **yes** |
| S37 | BJD_TDB needed the internet (IERS tables) | No `bjd_tdb` in any point, CSV or AAVSO report of a session run offline | **yes** |
| S38 | The live curve CSVs were rewritten in place after every point | A reader saw a partial file; a crash mid-write left the night's curve truncated | **yes** |
| S9 | Review read a check star as a second target | Wrong dock and name in Review | no |
| S10 | **Open curve CSV** exported a per-star file under its file name | AAVSO `NAME` wrong; a comparison exportable as the variable | **yes** |
| S11 | AAVSO export kept saturated/suspect points, accepted `OBSCODE=XXX` | Flagged points submitted unflagged | **yes** |
| S12 | Batch re-run looked only for `*.fits` | Never found an Argos session's `.fit` frames | no |
| S13 | Batch re-run: JD 0 for undated frames, cancelled runs saved | JD 0 rows reaching AAVSO; overwritten CSVs | rarely |
| S24 | An ASTAP database folder replaced the chosen database set | Slower or failed solves | no |
| S29 | Two unvalidated-profile warnings, hard-coded IMX585 hint | Contradictory wording | no |

Hardware safety and responsiveness:

| Item | Defect in 0.4.2 | Effect | Files you hold |
|---|---|---|---|
| H3 | The jog dialog tracked one axis | A diagonal jog, or a key held while the window lost focus, left an axis slewing at up to 5 °/s | no |
| H2 | **Connect equipment** reconnected connected devices | A second mount poller, a camera dropped without disconnect, a crash at quit | no |
| H7 | Disconnect during a run, no confirmation | Run ended, frame being exposed lost | no |
| H8 | Quit during a run, no confirmation | Run ended, frame being exposed lost | no |
| H9 | A refused filter-wheel move never reported back | Wheel stuck "busy"; Filter selector left on a slot the wheel never reached | **yes** |
| H10 | Go to / Move live during autofocus; Go to ignored MaxStep | A manual move could enter the V-curve | no |
| H11 | Offset, binning, site, address committed per keystroke | Intermediate offsets sent to the camera; config rewritten per keystroke | no |
| H4 | Clock error logged as "GoTo and Sync are disabled" | False message (they are refused on use) | no |
| H6 | "Tracking ON" on a disconnected mount card | Misleading display | no |
| H12 | Connection failures silent or cut to 48 characters | No reason on screen | no |
| H13 | Settings offered a telescope change while connected | Silent snap-back | no |
| H14 | Stellarium bind error not shown on its card | "stopped", no reason | no |
| H15 | "Sequence running" hint during a stand-alone autofocus | Misleading display | no |
| H17 | Site-search User-Agent "Argos/0.4.1" (fixed after the tag, untested) | Stale identification | no |

## Check your old files

Most checks below read the files themselves; S14 and S15 use Argos 0.5.0's
batch re-run.

Which frames: those whose `SOFTWARE` header is `Argos v0.4.2` or earlier (the
header exists since 0.3.0). Frames written by 0.5.0 carry `Argos v0.5.0` and
were written with these fixes. CSV and AAVSO files carry no version: date them
against the day you installed 0.5.0.

- **Dark and bias Take shots (S1).** A single dark or bias shot whose `FILTER`
  is not `Dark` was exposed to the sky unless the telescope was covered. Compare
  its median level with a sequence dark of the same `EXPTIME` and `GAIN` (a
  sequence moves the wheel to the Dark slot for darks and biases); do not use
  it as a master dark or bias if it is higher. `FILTER = Dark` is not a full
  guarantee in 0.4.2 (S3: a sequence could have moved the wheel since; and a
  shot taken right after picking Dark started exposing while the wheel still
  turned), so check the level anyway.
- **Take-shot exposure (S2).** `DATE-AVG` is the midpoint of the exposure as
  timed by the worker (start command to image ready), so
  `2 × (DATE-AVG − DATE-OBS)` is the time the exposure really took, plus
  readout and up to 0.1 s of polling. A 10 s frame saved as
  `EXPTIME = 30` shows about 5 s, not 15 s, between the two. Sequence frames are
  not affected.
- **Take-shot filter (S3).** A Take shot taken after a sequence that changed
  filter carries the Camera form's filter. Compare with the last sequence
  frame's `FILTER` (sequence frames read the wheel back). A Take shot pressed
  in Live just after a filter change saved the frame already exposing, partly
  or wholly through the previous filter, with the new `FILTER`; no header
  shows it.
- **Take-shot `HFD`, `NSTARS`, `SKYLEVEL` (S20).** Re-measure them; do not sort
  or reject Take shots on these values.
- **Opened frames (S4).** If you opened archived frames in Observe (**Open
  FITS…**) and solved them, the points they produced carry the time of another
  frame or of the solve. They are in the live curve's CSV (`<sessions>/targets/`,
  or the last run's `photometry/` folder if a sequence had run). Remove them
  before any AAVSO export. A calibrated or stacked frame opened that way was
  also measured on wrapped pixel values (a negative sky pixel became about
  65535, a sum above 65535 lost 65536): discard its points whatever their time.
- **Frozen pointing (X1).** A polled mount reports a changing `ALTITUDE` and
  `AZIMUTH` while it tracks, and a changing `RA` when it does not. Frames
  minutes apart with `RA`, `DEC`, `ALTITUDE` and `AZIMUTH` all identical were
  saved while the mount was disconnected or being reconnected: those values
  and `AIRMASS` are the last poll's. Recompute the airmass from the target's coordinates and `DATE-OBS`
  (or take it from a plate solve) before using it, for example in an
  extinction fit.
- **No site set (X2, 0.4.1 and 0.4.2).** Frames with `SITELAT = 0` and
  `SITELONG = 0` were taken without a site. The live curve's airmass of those
  nights (CSV `airmass` column, AAVSO `AMASS`), and that of a batch re-run made
  without a site, was computed for 0/0 (1.379 instead of about 1.005 for
  SS Cyg seen from Paris at 2026-11-01 19:00 UTC). Replace `AMASS` with `na`,
  or recompute it for your site, before submitting. `MOONALT` of those frames
  is for 0/0 too. The CSVs' `bjd_tdb` column is off by less than 0.03 s.
- **Site set but wrong (X3).** The header `ALTITUDE` and
  `AIRMASS` come from the mount, which knows where it is; `SITELAT`/`SITELONG`
  and the CSV `airmass` come from the Settings site. Recompute the altitude and
  azimuth of the frame's `RA`/`DEC` at `DATE-OBS` from `SITELAT`/`SITELONG`:
  more than 5° from the header's `ALTITUDE`/`AZIMUTH` direction means the site
  was wrong for that run (compare both angles: altitudes alone can agree). In one real case the
  mount gave 75.4° and the stale site 13.8°, so the CSV airmass ran from 4.1
  to 1.5 while the header `AIRMASS` ran from 1.03 to 1.36. Take the airmass
  from the header `AIRMASS` (or recompute it for the real site) before
  submitting; the differential magnitudes do not depend on it, and `bjd_tdb`
  is off by less than 0.03 s.
- **Black Light frames (S7).** Sequence Light frames with `FILTER = Dark` were
  shot through the opaque slot. The header is truthful; the data are lost.
- **Runs with no live curve (S14) or mixed apertures (S15).** Re-run the batch
  measurement on the run's frames (**Re-run subs…**, which now works on an Argos
  session, S12): it measures every frame with one aperture geometry.
- **The first point of a live curve (S31).** In a curve CSV (`photometry/*.csv`
  of a run, or `<sessions>/targets/*.csv`), compare the `fwhm` column of the
  first row with the second: when they differ, the first point was measured
  with an aperture of `aperture_fwhm_mult × fwhm` of its own (2.5 × 2.16 against
  2.5 × 2.12 green px in one real run of 195 points), while every other point
  used the second value. Drop the first row of every star of that run, or re-run
  the batch measurement (one aperture for all frames).
- **A star that changed role during a run (S33).** If you changed a star's role
  while points were measured (a comparison made the check star, or the
  reverse), its new role's CSV (`check_<object>_<star>.csv`) begins with the
  points measured under the old role: for a former comparison these are
  leave-one-out magnitudes against the other comparisons, not check-star
  magnitudes. Compare the file's first rows with the other role's CSV of the
  same star: the rows they share in time belong to the old role; drop them.
- **Opened frames without a site (S34).** Points measured on frames opened with
  **Open FITS…** while a mount was connected and no site was set have the
  airmass of where the mount pointed at that moment, not of the archived
  frame. Replace their CSV `airmass` (and AAVSO `AMASS`) with `na`, or recompute
  it for your site and the frame's `DATE-OBS`.
- **Comparison ensembles (S32).** If you pressed **Recommend from pilot**, or
  changed the comparison count, before the field was solved and its catalogue
  had arrived (or after a GoTo), or on a field where no VSP star passes the
  pilot gate (SNR ≥ 10, Δmag ≤ 1.5, within 25′: on the RR Lyr field all six are
  27–59′ away), the VSP comparisons were removed from
  `<sessions>/targets/<object>.json` and none were added. Open the set: if it
  has a target and no VSP comparison, solve the field and recommend again (or
  pick the comparisons by hand).
- **Points measured on blank sky (S35).** When the field moved by more than
  the tracker's search radius (15 green px with the default aperture) between
  the solve and the measured frame (a pointing jump, or a sequence frame
  measured through the previous frame's solve), every star of that frame was
  measured where it no longer was, and the points were kept with no flag. In
  the run's `<object>_live_diagnostics.jsonl`, look for frames whose `star`
  records all have `snr` below 5: drop every star's row at that frame's
  `jd_utc` in the run's curve CSVs, and recompute `sigma_syst` without them
  (it is estimated from every point of the run, so those rows raised it on
  every row). One real run (RR Lyr, 2026-09-25, 195 frames) had two such
  frames: the target 7.547 ± 0.757 and 6.257 ± 1.043, about 1.4 mag off its
  neighbours, and `sigma_syst` 0.0166 instead of 0.0150.
- **Sequence frame times (S36).** In a sequence frame's header, `DATE-AVG`
  minus `DATE-OBS` should be `EXPTIME / 2`; it was larger by half the
  download time (+5.2 s median, +16.6 s at most, for 10 s subs over Wi-Fi). The
  live curves used `DATE-OBS + EXPTIME/2` and are right. Points measured from
  these files later with **Open FITS…** (which dates a frame by `DATE-AVG`),
  or by another program reading `DATE-AVG`/`MJD-AVG`, are late by that amount:
  recompute the mid-exposure as `DATE-OBS + EXPTIME/2`. `DATE-OBS` itself was
  early by the gain and filter read-backs (tens of milliseconds).
- **BJD_TDB of offline sessions (S37).** A curve CSV with a site set (an
  `airmass` column filled from the site) but an empty `bjd_tdb` column was
  measured without internet access. Compute the BJD_TDB from `jd_utc`, the
  star's coordinates and the site (astropy's `light_travel_time`, as Argos
  does) before you submit or time anything with it.
- **Truncated curve CSVs (S38).** A curve CSV that ends in the middle of a row,
  or has fewer rows than the run had frames, was being rewritten when the
  program stopped: re-run the batch measurement on the run's frames.
- **AAVSO files (S10, S11).** Do not submit a file with `#OBSCODE=XXX`, or one
  whose `NAME` starts with `TARGET_`, `COMPARISON_` or `CHECK_` (an exported
  per-star CSV). A `NAME` shaped like a file name, `<OBJECT>_<AUID or star
  name>` (for example `SS_CYG_000-AAA-111`), also came from a per-star CSV,
  one without a role prefix: a live-preview CSV from `<sessions>/targets/`, or
  a batch re-run CSV. It may be a comparison or check star exported as the
  variable: compare the AUID suffix with the stars and roles of the run's
  `targets.json`, or of `<sessions>/targets/<object>.json`, and do not submit
  (or retract) rows that are not the target's. For any 0.4.2 export, compare
  its rows with the curve CSV's `saturated` and `suspect` columns: those
  points were submitted without a flag.
- **Batch CSVs (S13).** A row with `jd_utc = 0` came from a frame without
  `DATE-OBS`. This only happened with frames from other software, and only in
  `*.fits` folders (S12 kept the re-run from finding Argos frames).
- **Take shots after a refused filter change (H9).** When the wheel refused a
  move (an ERROR "Filter move: …" in the Activity log, the Filter selector
  greyed), 0.4.2 left the selector on the slot you had asked for, and the Take
  shots that followed, until the filter was changed again, wrote that slot to
  `FILTER`. The Activity log is not saved to a file, so no header check finds
  them: if you remember such an error, treat those Take shots' `FILTER` as
  unverified.

---

## Capture

### S1 — A Dark/Bias Take shot is refused unless the wheel's Dark slot is selected

**What was wrong.** The Seestar has no shutter: the filter wheel's opaque Dark
slot is the only way to block the light, and sequences use it. Take shot never
looked at the wheel, so a Dark or Bias shot with the Filter left on IR or LP was
a light frame saved as `IMAGETYP = 'Dark Frame'` (or `'Bias Frame'`).
**Who was affected.** Anyone who took single darks or biases from the Camera
form. Used as a master dark or bias in Siril, such a frame corrupts the
calibration of every science frame behind an AAVSO report.
**What changed.** With a wheel that has a Dark slot, a Dark/Bias shot is refused
with a WARN asking for Filter `Dark`, unless the form is on it; this also covers
a shot taken during Live. Without a wheel the shot goes, with a WARN that it is
dark only if the telescope is covered. The wheel is not moved automatically
(that needs a move-then-expose chain, left to the web UI).
**Found in review.** The guard read only the Filter selector, which shows
`Dark` as soon as it is picked, while the wheel still turns: a Dark shot taken
at once exposed through the moving wheel and was saved as a clean dark. The
same after a refused move that could not be read back (H9), and when the wheel
was turned away from Dark before the shot's frame arrived. The session now
tracks the slot the wheel last reported it settled on: a Dark/Bias shot also
needs the wheel settled on Dark (a WARN says it is still turning, or that its
position is unknown and Dark must be selected again), and a pending dark whose
frame arrives with the wheel elsewhere is not saved. Only moves made from the
Camera form are tracked; a sequence moves the wheel itself but owns the camera,
so no Take shot can overlap it.
**How to check.** `tests/workers/test_acquisition_engine.py::test_dark_take_shot_refused_unless_the_wheel_is_on_the_dark_slot`,
`::test_dark_take_shot_waits_for_the_wheel_to_settle_on_dark` and
`::test_dark_shot_is_dropped_if_the_wheel_leaves_the_dark_slot`.
At the telescope: Frame type Dark, Filter IR, Take shot: a WARN, no exposure.
Pick Dark and press Take shot at once: a WARN that the wheel is still turning.

### S2 — A Take shot's header describes the settings it was exposed with

**What was wrong.** The preview worker exposed with its own copy of the
settings, but the engine re-read the Camera form when the frame arrived. A
change made during the exposure (in Live, the usual workflow: tune the exposure,
then Take shot) went into `EXPTIME`, `GAIN` (and `EGAIN`/`RDNOISE`), `IMAGETYP`,
`FILTER`, `OBJECT` and the file name. `DATE-OBS`/`DATE-AVG` were right.
**Who was affected.** Take shots, mostly from Live. Dark and flat matching by
`EXPTIME` breaks downstream.
**What changed.** The worker snapshots its settings once per frame, uses exactly
those for the exposure and emits them with the frame (`FrameSettings`). The save
takes exposure, gain, object, filter and frame type from that snapshot.
**How to check.** `tests/workers/test_acquisition_engine.py::test_live_take_shot_saves_the_in_flight_frame_with_its_own_exposure`
(0.4.2: `EXPTIME 30.0` for a 10 s frame) and
`tests/workers/test_exposure_worker.py::test_frame_carries_the_settings_it_was_exposed_with`.

### S3 — A Take shot reads the wheel for its FILTER

**What was wrong.** A sequence moves the wheel directly, and the Camera form was
told only about moves it made itself. After a run that changed filter, a Take
shot wrote the form's filter to `FILTER` and the file name: a frame shot
through LP was labelled IR.
**Who was affected.** Take shots after a sequence, or after any wheel move made
outside the Camera form.
**What changed.** The save task reads the wheel's position (off the UI thread),
with the sequence's read-back rules: a readable wheel that differs from the form
wins, with a WARN; an unreadable or turning wheel keeps the form's value, with a
WARN. At the end of a sequence the form is resynchronised with the wheel.
**Found in review.** In Live the Filter selector stays usable, so the wheel
could turn during the exposure a Take shot then saved, and `FILTER`, read after
the exposure, named the slot the wheel ended on. A Take shot now never saves a
frame whose exposure started before the last wheel move ended (or while one is
in flight): the loop exposes another frame, which is the one saved (INFO in the
log). `FILTER` is therefore the slot of the whole exposure.
**How to check.** `tests/workers/test_acquisition_engine.py::test_take_shot_after_a_sequence_records_the_filter_the_wheel_is_on`
(0.4.2: `FILTER = 'IR'` with the wheel on LP) and
`::test_take_shot_never_saves_a_frame_exposed_while_the_wheel_turned`.

### S20 — A Take shot's QA headers are measured on the saved frame

**What was wrong.** `HFD`, `NSTARS` and `SKYLEVEL` of a Take shot came from the
last frame the display had processed: the previous frame at best, a half-res
preview otherwise.
**Who was affected.** Any Take-shot file used for quality sorting.
**What changed.** The save task measures them (and now `FWHM`, `ECCENTR`) on the
full-resolution array it writes, as sequences already did. The display side of
S20 (camera-card HFD on a half-res preview, fixed thresholds, nominal plate
scale) is left to the web UI.
**How to check.** `tests/workers/test_acquisition_engine.py::test_take_shot_qa_headers_describe_the_saved_frame`
(0.4.2: `HFD 7.6` for a frame whose HFD is 2.0).

## Autofocus

### S22 — Autofocus applies its gain

**What was wrong.** The worker stored the requested gain and never sent it; the
sweep used whatever gain the camera last had.
**Who was affected.** Every autofocus: stars too faint or saturated give a worse
or rejected V-curve. No file is written by autofocus.
**What changed.** `set_gain` is sent once before the first sample (a driver
without Gain still sweeps, with a warning). Filter and exposure choice for AF,
and drawing the worker's own fit on the plot, are left to the web UI.
**How to check.** `tests/workers/test_autofocus_worker.py::test_sweep_frames_use_the_requested_gain`.

### S23 — Stop AF returns the focuser to its start

**What was wrong.** On Stop AF the worker commanded the return to the start
position and ended at once; Stop AF shares its slot with Halt, which then froze
that return move midway. The panel showed the start position and the log said
"Autofocus complete". A rejected sweep also logged ERROR then "complete".
**Who was affected.** Anyone who stopped an autofocus: the following frames
could be defocused with no warning.
**What changed.** The worker waits for the return move whatever the stop flag
(bounded by its 30 s deadline) and reports the position read back. While
autofocus runs, Halt only stops the autofocus. "Autofocus complete" is logged
only when the sweep produced an HFD. Two more paths were closed while writing
this note: the worker's own stop halted the focuser *after* raising the stop
flag, so a worker waking in between could have its return move halted; and a
Stop during the final move to best focus was reported as "complete" at the
fitted position (25000) with the focuser short of it (25333 in the test). The
halt now comes first, and a stop on the way to best focus returns to the
start. Stop AF blocks the UI for up to 10 s while the worker ends; a
non-blocking stop is left to the web UI.
**Found in review.** When the return outlasted those 10 s (the worker allows
it 30 s), Stop AF dropped the worker and released the camera while the worker
still drove the focuser, and a new Start AF ran a second worker on the same
focuser (reproduced with a simulated 12 s return; the Seestar focuser's real
speed is not known). Stop AF now keeps such a worker and its hold on the
camera, and says the focuser is still returning; the camera is released, and a
paused sequence resumes, only when the focuser is back. A second Stop does not
block again. Not changed: at quit, every worker shares a 5 s budget, so
quitting while a stopped autofocus is still returning can abandon its worker
(the H8 item left to the web UI; not run on the full app).
**How to check.** `tests/workers/test_autofocus_worker.py` (the three Stop
tests), `tests/ui/test_autofocus_feedback.py` and
`tests/workers/test_acquisition_engine.py::test_stop_af_keeps_a_returning_worker_and_refuses_a_second_sweep`.
At the telescope: Stop AF mid-sweep, then read the focuser position: it is the
start.

## Opened frames

### S4 — An opened FITS is dated from its header and drops the previous WCS

**What was wrong.** **Open FITS** read only the data. The engine kept the
previous frame's exposure midpoint and the previous field's WCS, and photometry
fell back to "now" when no time existed. After a solve, the point measured on
the opened frame carried another frame's time and went into the live curve, its
CSV and the AAVSO export.
**Who was affected.** Offline replay of archived frames in Observe.
**What changed.** The epoch comes from `DATE-AVG`, else `DATE-OBS + EXPTIME/2`,
else none; the WCS, catalogue cache and last run folder are dropped. With no
epoch, photometry is skipped with a WARN instead of stamping "now".
`DATE-OBS` = exposure start is Argos' convention; a file from other software
may differ.
**Found in review.** Open FITS cast any pixel data to 16-bit integers, and that
cast wraps: a negative value (common in a dark-subtracted or calibrated frame)
became about 65535, and 70000 became 4464. Such a frame could still be solved
and measured, with wrong sky and aperture sums, and since the fix above its
points carry the file's real time. Open FITS now accepts integer values from 0
to 65535, whatever the stored type, and refuses anything else with an ERROR,
leaving the live frame, its time and its WCS untouched. Inspect a calibrated
frame with **Review → Open FITS…**.
**How to check.** `tests/workers/test_acquisition_engine.py::test_opened_fits_is_dated_by_its_header_and_drops_the_previous_wcs`,
`::test_opened_fits_without_a_date_measures_no_point` and
`::test_opened_fits_that_is_not_raw_16_bit_data_is_refused`.

## Pointing and site in files

### X1 — Frames do not keep a disconnected mount's pointing

**What was wrong.** The last polled mount position stayed in memory after a
mount disconnect and after a lost connection (three failed polls). Every frame
saved afterwards, Take shot or sequence frame, wrote `RA`, `DEC`, `OBJCTRA`,
`OBJCTDEC`, `ALTITUDE`, `AZIMUTH` and `AIRMASS` from it: while a lost mount
was retried every 10 s, or with the camera still exposing after the mount was
disconnected. A poll in flight during a disconnect could also restore the
position, and a "connected" mount state, afterwards (read from the code: the
poll's result is queued to the UI thread).
**Who was affected.** Since 0.3.0, anyone whose mount dropped or was
disconnected while frames were being saved. Found while verifying H7.
**What changed.** The position is cleared on disconnect and on a lost
connection, and a position arriving once the mount is gone is ignored: the
frames get no pointing keys and no `AIRMASS`, and the live curve's airmass
falls back to the site computation or `na`. Within the poller's own detection
window (three failed polls, 2 s apart) the last position is still used.
**How to check.** `tests/core/test_device_session.py::test_mount_position_is_forgotten_when_the_mount_goes_away`
and `tests/workers/test_acquisition_engine.py::test_frames_saved_after_the_mount_went_away_carry_no_pointing`.
At the telescope: Live, disconnect the mount, Take shot: no `RA`, `ALTITUDE`
or `AIRMASS` in the file.

### X2 — The 0/0 default is never used as the observing site

**What was wrong.** The site defaults are latitude and longitude 0.0, not
"unknown", so with no site set the engine's fallback to the mount altitude
never applied. Each live point's airmass, the CSV `airmass` column and AAVSO
`AMASS`, was computed for 0/0: 1.379 for SS Cyg at 2026-11-01 19:00 UTC, where
the mount (altitude 60°) gave 1.154 and Paris sees 1.005. The batch re-run did
the same. Frames got `SITELAT`/`SITELONG`/`SITEELEV` = 0 and `MOONALT` for 0/0;
`BJD_TDB` was off by less than 0.03 s (the Earth's radius over the speed of
light is 0.021 s; 0.006 s in this example).
**Who was affected.** 0.4.1 and 0.4.2 users who never set a site (earlier
versions had no 0/0 default). Found in the review of this branch.
**What changed.** One rule for live photometry, both FITS paths, the batch
re-run and Plan: a site is set when it has a name or coordinates other than
0/0 (Settings saves typed coordinates without a name, and the pre-0.4
migration moves observer coordinates in without one). Without a site the live
airmass is the mount's (`na` without a mount), the re-run has no airmass, there
is no `BJD_TDB`, and frames have no `SITELAT`/`SITELONG`/`SITEELEV` or
`MOONALT` (`MOONSEP` and `MOONPHAS` need no site and stay). With a site set,
nothing changes.
**How to check.** `tests/workers/test_acquisition_engine.py::test_no_site_set_means_no_site_products_not_latitude_0_longitude_0`
(1.3789 on the code before the fix, the mount's 1.1541 here),
`tests/ui/test_batch_rerun.py::test_rerun_without_a_site_computes_no_airmass_at_latitude_0_longitude_0`
and `tests/core/test_config_migration.py::test_observing_site_is_never_the_0_0_default`.

### X3 — The Settings site is checked against the mount

**What was wrong.** The Seestar takes its site and clock from the phone and
reports where it points (altitude, azimuth); ARGOS computes airmass, BJD_TDB,
the Moon and FITS `SITELAT`/`SITELONG` from the Settings site. Nothing compared
the two, so a site left from an earlier trip went unnoticed for a whole run: in
one session the mount gave RR Lyr at altitude 75.4°, azimuth 258.9° while the
Settings site put it at 13.8°, azimuth 45.9° (88.5° apart), and the CSV airmass
and AAVSO `AMASS` were computed for the wrong site. Over that run the two
directions stayed 83.6–88.5° apart, but the altitudes alone came within 6.2° by
its end, so the check compares the whole direction. In the eleven other
sessions on disk, where the site was right, they agree within 1.9–3.1°.
**Who was affected.** Anyone who observed away from the site saved in
Settings.
**What changed.** Once per mount connection (and again after a reconnect), on
the first poll that is not a slew, ARGOS computes the altitude and azimuth of
the mount's RA/Dec from the Settings site and the computer's clock (fast
spherical trigonometry, within 0.3° of astropy). More than 5° from the
direction the mount reports logs a WARN with both directions and the place to
fix it (Settings › Observer & site); otherwise an INFO line says they agree. With
no site set there is nothing to check (X2). A wrong mount clock also shifts
the comparison; the clock check (H4) reports it separately. Nothing is
blocked: the warning says what is wrong and the observer decides.
**How to check.** `tests/core/test_device_session.py::test_site_that_cannot_be_where_the_mount_is_is_reported`
uses the header values of that session's first frame (88.5° apart, warned
once per connection); `test_site_that_agrees_with_the_mount_is_confirmed`,
`test_site_is_checked_again_after_a_reconnect` and
`test_no_site_set_means_no_site_check`. The first three fail on the code
before the change. `tests/core/test_sky_geometry.py` checks the direction
against astropy.

## Plan

### S5 — A prepared transit keeps its planning metadata

**What was wrong.** The Plan editor loaded a prepared transit's steps but
dropped its metadata, so every run started from the UI skipped
`observation.json` (planet, ephemeris, epoch, period, duration, depth, predicted
ingress, mid-transit, egress, coverage). Review's *Session metadata* card was
always empty for these runs; presets saved `metadata {}`.
**Who was affected.** Every transit run started from the UI. FITS headers,
timing and AAVSO export were not affected.
**What changed.** The editor keeps the loaded plan's metadata for as long as the
object is unchanged (never for another object). A preset load does not restore
it and says so: a transit window belongs to one night.
**How to check.** `tests/workers/test_sequence_worker_observation.py` (the
editor's plan writes `observation.json`; none on 0.4.2) and
`tests/ui/test_sequence_panel_plan.py`.

### S7 — A Light step never defaults to the wheel's opaque Dark slot

**What was wrong.** An unknown filter left the row's combo at index 0, and every
Seestar profile has Dark at slot 0 once the wheel connects. Every Light step
added with **+ Add** after the wheel connected, and every preset step whose
filter was not on the wheel, shot through the opaque slot. Also silent: a preset
frame type `dark` loaded as Light, a 900 s step loaded as 600 s without a
camera, and a camera disconnect clamped 900 s rows to 600 s.
**Who was affected.** Every Seestar user who added a Light row after the wheel
connected, or loaded a preset whose filter is not on the wheel: whole steps of
black frames (`FILTER = Dark`, truthful but useless).
**What changed.** An unknown or vanished filter falls back to the first slot that
passes light. A preset load reports every substitution ("adjusted: …"). Frame
types are matched case-insensitively and an unknown one is refused. A camera
disconnect no longer resets the ranges. Picking Dark by hand on a Light row is
still allowed.
**How to check.** `tests/ui/test_sequence_panel_plan.py::test_add_after_wheel_connect_never_defaults_a_light_step_to_the_opaque_slot`.
At the telescope: connect the wheel, **+ Add**: the new Light row is on IR.

### S26 — Plan visibility needs a site; transit coverage after midnight

**What was wrong.** Without a saved site the visibility curve used latitude and
longitude 0/0; a transit whose midpoint is after midnight was drawn on the wrong
night; **Find** ignored the Baseline field; a missing duration was reported as
"Observing site required".
**Who was affected.** Planning display only; nothing written to files.
**What changed.** No curve without a site (a message says why); the plotted
night is the one containing the midpoint; Find uses Baseline; the real cause is
shown. A site is set when it has a name or coordinates other than 0/0, the rule
X2 applies everywhere: S26 first required the name, which would have ignored
coordinates typed without one.
**How to check.** The four S26 tests in `tests/ui/test_sequence_panel_plan.py`.

## Live photometry

### S14 — A sequence identifies the field even when no WCS exists yet

**What was wrong.** Auto-solve was armed for a run only if a WCS already
existed, and any GoTo clears it. A run started after a GoTo without a manual
**Identify field** measured no differential photometry all night, although the
menu promises auto-solve "during a sequence".
**Who was affected.** Runs started after a GoTo without a manual **Identify
field**. FITS files were saved correctly; the batch re-run recovers the points
(S12).
**What changed.** Auto-solve is armed for any run with Light frames, WCS or not;
not for calibration-only runs; without ASTAP, one WARN says that no live
photometry will be measured. The first frame of an unidentified run still has no
point (its solve is running when it is saved).
**How to check.** `tests/ui/test_sequence_autosolve.py`.

### S15 — The aperture geometry is locked while a sequence runs

**What was wrong.** The four geometry spins (aperture × FWHM, aperture floor,
annulus radii) applied from the next frame, during a run, with no record in the
files.
**Who was affected.** Anyone who touched a spin during a run: one curve, two
apertures.
**What changed.** The spins are disabled during a sequence (tooltip says why);
the comparison-selection controls stay available.
**How to check.** `tests/ui/test_photometry_window.py::test_aperture_geometry_locked_during_sequence`.

### S16 — Saturated points are left out of the plot baselines

**What was wrong.** The **Relative flux** view normalised by the median of every
point, saturated (clipped) ones included, and each comparison's Δmag used the
same kind of median. With no positive median, the previous view's magnitudes
stayed on screen under the flux axis.
**Who was affected.** Display only (live dock, Photometry window, Review).
**What changed.** Both baselines use the unsaturated points (all points if every
one is saturated); a series with nothing to draw is cleared.
**How to check.** `tests/ui/test_photometry_window.py::test_relative_flux_baseline_ignores_saturated_points`
(0.4.2: 0.5 instead of 1.0; Δmag +1.0 instead of 0).

### S17 — The comparison ensemble is vetted in live preview, with its verdict

**What was wrong.** The leave-one-out report was computed only once a sequence
had saved a frame; the tables said "Waiting for 10 points" whatever the
configured minimum; the ensemble verdict and its caveat were never shown.
**Who was affected.** Display only.
**What changed.** The report is computed on every measured frame and written to
`photometry_quality.json` during a sequence only. The wait label uses the
configured minimum; the verdict ("insufficient data", "not ready: fewer than 3
stable comparisons", "consistent in live preview") and the caveat are shown above
the rows.
**How to check.** `tests/workers/test_acquisition_engine.py::test_quality_report_emitted_in_live_preview`
and `tests/ui/test_photometry_window.py::test_quality_wait_label_uses_report_min_points`.

### S18 — Ratio-only live points reach both plots

**What was wrong.** The live dock was fed without the relative flux; a point
with no magnitude (comparisons without a catalogue magnitude, e.g. a transit
run) raised `TypeError`, so neither the dock nor the Photometry window showed it,
and the crash reporter wrote a report for each such point. The CSV was correct.
**Who was affected.** Relative-flux and transit runs.
**What changed.** The dock gets the relative flux; a point with neither product is
skipped quietly.
**How to check.** `tests/ui/test_photometry_window.py::test_live_ratio_only_point_reaches_dock_and_window`.

### S19 — The live curves re-render once per frame, in linear time, keeping the zoom

**What was wrong.** From the 10th point of a curve, the run-level uncertainty
floor changes earlier error bars, and every star of every frame triggered a full
re-render of the dock and of the Photometry window (even closed). Each re-render
redrew a series once per point, O(N²), and ended by resetting the zoom.
**Who was affected.** Long runs with several stars: the verification measured
several seconds of frozen UI per frame after about 200 frames with 10 stars,
during which Stop and the mount controls do not respond. Data were correct.
**What changed.** One re-render per frame; each series drawn once (10 series ×
800 points: 3.63 s before, 0.043 s after, measured here); a closed Photometry
window is reloaded when opened instead. The live view follows new points until
the user zooms or pans; after that the zoom is kept, and the plot's **A**
button restores the automatic range. Review keeps fitting the view as before.
**How to check.** `tests/ui/test_photometry_window.py::test_live_rerender_keeps_user_zoom_and_follows_data_otherwise`
and `tests/workers/test_acquisition_engine.py::test_floor_change_rerenders_once_per_frame`.

The verifier's proposed rule (keep the view unless `ViewBox.autoRangeEnabled()`
is still on) would have frozen the live view: pyqtgraph's `autoRange()`, which
the panel used, turns auto-range off itself, so the flags read `[False, False]`
after the first re-render (checked on 0.4.2). The panel now uses
`enableAutoRange()`.

### S31 — The live series FWHM is frozen on the first measured frame

**What was wrong.** One aperture per series (P7): the FWHM is frozen on the
first measured frame and re-sampled only after an autofocus or a change of
object. The engine froze it, then opened the flight recorder, which resets the
series FWHM for a new object (and for a new run): the first frame was measured
with its own FWHM, and the series was frozen on the **second** frame's. The
owner's RR Lyr run of 2026-09-25 shows it: `fwhm` 2.16 on the first row of every
curve, 2.12 on the 194 others; XX Cyg 2026-09-07: 2.18, then 2.19.
**Who was affected.** Every live curve of 0.4.2 (each object, each sequence
run): its first point had another aperture radius than the rest of the series.
**What changed.** The recorder is opened first; the series FWHM is then frozen
on the frame being measured, as the batch re-run does (its first readable
frame).
**How to check.** `tests/workers/test_acquisition_engine.py::test_series_fwhm_is_frozen_on_the_first_measured_frame`
(`[2.0, 3.0, 3.0]` on the code before the fix, `[2.0, 2.0, 2.0]` now).

### S32 — Recommend from pilot keeps the ensemble when there is nothing to choose from

**What was wrong.** **Recommend from pilot**, and a change of the "Automatically
propose" comparison count, first removed every VSP comparison (`vsp`,
`vsp_auto`) from the set, then picked new ones from the field's VSP catalogue.
With no VSP star known (field not solved, catalogue not back yet or failed, or
any time after a GoTo, which drops the catalogue) nothing was picked, and the
set was saved without its comparisons: no differential magnitude from the next
frame on. The Activity log said "no pilot-qualified comparison found".
**Who was affected.** Anyone who pressed it before the catalogue arrived.
**What changed.** Without VSP stars to choose from, the set is left unchanged
(same message).
**How to check.** `tests/workers/test_acquisition_engine.py::test_recommend_without_vsp_stars_keeps_the_ensemble`
(the set lost both comparisons on the code before the fix).

### S33 — A star whose role changes starts a new live curve

**What was wrong.** Live curves are kept per star (AUID, else name). When a
star changed role (a comparison made the check star, or the reverse), its
measurements kept going into the same curve, still labelled with the first
role: a check star's curve began with its leave-one-out comparison magnitudes,
and in a run its new `check_*.csv` was written with both. The dock drew the
check points in the comparison plot.
**Who was affected.** Runs where a star's role was changed while points were
measured.
**What changed.** A star measured under a new role starts a new curve (the old
role's CSV, inside a run, keeps its points); the display drops the old curve.
**How to check.** `tests/workers/test_acquisition_engine.py::test_a_role_change_starts_a_new_curve`
(three comparison points under one curve on the code before the fix).

### S34 — An opened frame never takes the mount's airmass

**What was wrong.** Without a site set, a live point's airmass is the mount's
(X2: never the 0/0 default). The engine applied that rule to frames opened with
**Open FITS…** too: an archived frame of another night was given the airmass of
wherever the connected mount pointed when it was measured (1.154 for a mount at
60°, whatever the frame saw).
**Who was affected.** Replays of archived frames with a mount connected and no
site set.
**What changed.** A point measured on an opened frame has no mount airmass
(none without a site, as the batch re-run); a site set gives the star's own
airmass at the frame's time, as before.
**How to check.** `tests/workers/test_acquisition_engine.py::test_an_opened_frame_never_takes_the_mount_airmass`
(1.1541 on the code before the fix).

### S35 — A frame on which the field moved since the solve gets no point

**What was wrong.** Live photometry places its apertures through the latest
solve, corrected by the aperture tracker, which re-centroids anchor stars
within 15 green px of where the solve puts them. The tracker is rebuilt on the
first frame after each solve, from the comparisons bright enough to steer it.
When none was found there (the field had moved by more than the search radius
since the solve), it fell back to every star of the set, unseen, then took
noise centroids for stars (positive noise is never empty) and reported every
anchor found. The frame was measured on blank sky: no warning (the "apertures
unguided" message never fired), no flag, and the point kept. It happens to a
sequence frame measured through the previous frame's solve after a pointing
jump, and to a live frame after a solve. One real run (RR Lyr, 2026-09-25) has
two such frames: the field jumped 22.8 px and 140 px, the target was measured at
SNR 1.5–1.9 and written as 7.547 ± 0.757 and 6.257 ± 1.043 (about 1.4 mag off
its neighbours), and those points raised the run-level `sigma_syst` of every
row.
**Who was affected.** Live and sequence photometry after a pointing jump (or a
slew) larger than the search radius between the solve and the measured frame.
**What changed.** The fallback takes only stars of the set seen where the
solution places them (SNR ≥ 5); a tracker built with none is rebuilt on the next
frame. A frame on which no anchor is found gets no point: a WARN says
"Photometry skipped: no star of the set where the solution places it — the
field moved since the solve, or clouds", and the flight recorder logs a
`frame_skipped` event. This also applies to a frame on which clouds hide every
anchor (each below 20 % of its first signal): such a frame used to be measured
"unguided" at the last good position. On the review's replays (92 XX Cyg
frames, the RR Lyr frames around both jumps) only the two frames above lose
their point; every other value is unchanged. The web server's port has the same
change.
**How to check.** `tests/workers/test_acquisition_engine.py::test_a_field_that_moved_since_the_solve_gets_no_point`
(an unflagged second point on the code before the fix).

### S32 (extended) — Recommend keeps the ensemble when no VSP star passes the gate

**What was wrong.** The S32 fix kept the ensemble only when the field had no
VSP star at all. With VSP stars that all fail the pilot gate (SNR ≥ 10,
Δmag ≤ 1.5, within 25′, on the frame), **Recommend from pilot** still removed
every VSP comparison, added none and saved the set without comparisons. On the
RR Lyr field all six VSP comparisons are 27–59′ from the target.
**Who was affected.** Fields whose VSP stars are all far from the target, too
faint or too bright for the filter.
**What changed.** The new ensemble is chosen on a copy of the set; the set is
changed and saved only when at least one comparison was picked (the WARN that
lists the gate still says why none was).
**How to check.** `tests/workers/test_acquisition_engine.py::test_recommend_with_no_vsp_star_passing_the_gate_keeps_the_ensemble`
(the set lost both comparisons on the code before the fix).

### S36 — A sequence frame is dated by its exposure, not its download

**What was wrong.** The sequence worker started its clock before the gain and
filter read-backs and stopped it after downloading the image, so `DATE-AVG`
and `MJD-AVG` (written as the middle of that span) were late by half the
download time: +5.2 s median and +16.6 s at most on 10 s subs over Wi-Fi
(RR Lyr 2026-09-25), +1.8 s and +2.3 s on two XX Cyg runs. The Take shot and
the live preview already stop the clock at ImageReady. The live curve points
of a sequence are timed from `DATE-OBS + EXPTIME/2` and were right; a frame
opened with **Open FITS…** is timed from `DATE-AVG` (S4), so a replay dated
the same frame later, and its BJD with it.
**Who was affected.** Every sequence frame (seconds late in `DATE-AVG`), and
anyone timing those files by `DATE-AVG` (replays, other software).
**What changed.** The clock starts just before StartExposure and stops at
ImageReady, as the live preview's.
**How to check.** `tests/workers/test_sequence_worker_observation.py::test_sequence_frame_times_are_the_exposure_not_the_download`
(`DATE-OBS` 0.3 s early and `DATE-AVG − DATE-OBS` 0.6 s for a 0.2 s exposure
on the code before the fix).

### S37 — BJD_TDB is computed offline

**What was wrong.** `bjd_tdb` let astropy download its IERS tables
(`finals2000A.all`, the leap-second list) from the internet on first use: 2.3 s
on the first point online, about 18 s per point on a network that hangs. Offline,
astropy refused its bundled table (older than 30 days) for the dates of the
session, the error was swallowed, and the point had no BJD_TDB even with a site
set: the CSV `bjd_tdb` column was empty and the AAVSO export had no BJD. Whether
it happened depended on whether a mount with a non-J2000 coordinate system had
been used earlier in the session (telescope.py turns the download off).
**Who was affected.** Sessions observed without internet access (in the field,
or behind a refused connection).
**What changed.** BJD_TDB uses astropy's bundled IERS tables and never
downloads; the value is the same to the bit as with the downloaded tables
(checked on three dates up to 2029).
**How to check.** `tests/core/test_photometry_core.py::test_bjd_tdb_needs_no_network`
(eight download attempts and no BJD on the code before the fix).

### S38 — A live curve CSV is replaced, never rewritten in place

**What was wrong.** The live engine rewrites a star's whole curve CSV after each
point. The file was truncated and written in place, so a program reading it
(Review, a spreadsheet, star_var_script) could see a partial or empty file
(1 778 of 2 097 reads in a concurrent test), and a crash or power loss
mid-write left the night's curve truncated on disk.
**Who was affected.** Anyone reading a curve CSV during a run; a run that
stopped abnormally.
**What changed.** The file (and the session-wide curves export) is written
beside the old one and renamed over it once complete, as the target set and
the quality report already were. The bytes written are the same.
**How to check.** `tests/core/test_photometry_core.py::test_a_failed_csv_rewrite_leaves_the_previous_file`
(the header and one of three rows left on the code before the fix).

## Review and AAVSO export

### S9 — Review keeps the check star's role

**What was wrong.** Review recovered roles from the file-name prefix with a
two-way test, so `check_<obj>_<auid>.csv` became a second science target with its
own dock, named after the file.
**Who was affected.** Review of any session with a check star (display; Review
has no AAVSO export).
**What changed.** Three prefixes, three roles; the check is listed in the target
plot as "<name> (check)".
**How to check.** `tests/core/test_session_review.py::test_review_keeps_check_star_role`.

### S10 — A per-star curve CSV is identified before it can be exported

**What was wrong.** **Open curve CSV…** (the only way to export AAVSO for a
finished night) read a per-star session CSV as a target named after its file:
the comparison file exported as `COMPARISON_SS_CYG_000-AAA-111,…` and the
target file as `TARGET_SS_CYG_000-BCP-095` instead of `SS CYG`.
**Who was affected.** Every AAVSO file exported that way in 0.4.2.
**What changed.** The role comes from the file-name prefix and the star from the
session's `targets.json`; when either stays unknown, a warning is shown and the
AAVSO export is disabled for that window.
**Found in review.** A live-preview CSV (`<sessions>/targets/<object>_<star>.csv`,
where Observe photometry before any sequence and Open FITS replay write) has
its target set in `<sessions>/targets/<object>.json`, not in a `targets.json`,
so it was always "role unknown", even for the real target. That set is now
used for a CSV in a `targets/` folder. It is the object's current set, not a
per-run snapshot: a star whose role changed since keeps its own name but takes
its current role.
**How to check.** `tests/core/test_session_review.py::test_single_star_csv_restores_role_and_name`
(the comparison file writes no AAVSO row, the target file writes `NAME SS CYG`)
and `tests/ui/test_photometry_window.py::test_open_curve_csv_finds_the_target_set_of_a_preview_curve`.

### S11 — The AAVSO export leaves flagged points out, needs an observer code and reports errors

**What was wrong.** Saturated and suspect points were exported with `NOTES na`;
an unset observer code was written as `#OBSCODE=XXX` without a word; a failed
write raised out of the slot (a crash report, nothing on screen); dialogs opened
in the home folder.
**Who was affected.** Every 0.4.2 AAVSO export.
**What changed.** Flagged target points are left out (counts reported after the
write; they stay in the CSV); a flagged check point never provides `KMAG`; no
export without an observer code; write errors are shown; dialogs open in the
curve's folder (Review) or the last run's folder (Observe). Deferred to the web
UI's export dialog: the `FILT` consistency check, `KNAME`/`KMAG` for Review
exports, a preview.
**How to check.** `tests/core/test_photometry_core.py::test_aavso_export_excludes_flagged_points`
and `tests/ui/test_photometry_window.py::test_aavso_export_refuses_unset_obscode`.

## Batch re-run

### S12 — The batch re-run finds an Argos session's light frames

**What was wrong.** **Re-run subs…** looked only for `*.fits`; Argos writes
`.fit`, so it never found a frame of an Argos session. The obvious fix
(`*.fit*`) would have measured darks, flats and biases as light frames.
**Who was affected.** Anyone trying to recover a run's photometry.
**What changed.** `.fit`, `.fits` and `.fts` in any case; calibration frames left
out by `IMAGETYP`; frames ordered by `DATE-OBS`. Frames are not filtered on
`OBJECT`.
**How to check.** `tests/workers/test_photometry_batch_worker.py::test_discover_light_frames_finds_fit_and_skips_calibration`.

### S13 — No JD 0 point, no saved cancelled run, roles kept

**What was wrong.** A frame without `DATE-OBS` got `jd_utc = 0` and reached the
AAVSO export; a cancelled run reported success, overwrote the previous CSVs and
replaced the live curves; an unreadable file counted as measured; CSV names had
no role prefix, so a reloaded comparison came back as a target.
**Who was affected.** Re-runs on folders of third-party `*.fits` frames (S12
kept it from finding Argos frames).
**What changed.** Undated or unreadable frames are skipped and counted; a
cancelled run writes nothing and is reported as cancelled; CSVs are named
`<role>_<object>_<star>.csv` with the run's `targets.json`, in a new
`photometry_rerun_<UTC>/` folder of the session (of the chosen folder when it
is not in a session).
**How to check.** `tests/workers/test_photometry_batch_worker.py` (the S13
tests) and `tests/ui/test_batch_rerun.py`.

## Plate solving

### S24 — A database folder keeps the chosen star database

**What was wrong.** Settings' database folder replaced the chosen set: ASTAP got
`-d <folder>` without `-D D50` and picked a set on its own.
**Who was affected.** Users who set a database folder. Solves could be slower or
fail; a successful solve is still a real ASTAP solution.
**What changed.** ASTAP gets `-D <set> -d <folder>`, the pair it already got when
the folder was auto-detected (`astap_cli -h`: `-d path`, `-D abbreviation`).
**How to check.** `tests/core/test_astrometry_session.py::test_database_folder_keeps_the_database_set`.

## Wording

### S29 — One unvalidated-profile warning; the camera hint names the active sensor

**What was wrong.** Connection said "do not use it for scientific photometry",
Settings said "never run on this hardware"; the picker suffixes differed; the
camera card always said IMX585.
**Who was affected.** S30 and S50 owners (wording only; `INSTRUME` and the other
headers come from the profile).
**What changed.** "Not validated on this hardware: do not use it for scientific
photometry." on both pages, one suffix, and the camera hint from the profile
(IMX462 for the S50).
**How to check.** `tests/ui/test_settings_telescope.py`.

## Hardware safety

### H3 — The jog dialog stops every axis it moves, and drives the current mount

**What was wrong.** The Manual Control dialog (Alpaca `MoveAxis`, 0.5 to
5 °/s) remembered one moving axis. Holding Up then Right and releasing both
stopped azimuth only: altitude kept slewing, and neither ■ nor closing the
dialog could stop it (they called the same one-axis stop). A key held while the
window lost focus was released in another window and nothing was stopped. The
dialog kept the `Telescope` it was first opened with, so after a reconnect it
drove the old handle, and nothing closed it when the mount went away.
**Who was affected.** Anyone jogging from the keyboard. Only the Mount card's
stop, Abort or Park ended such a runaway.
**What changed.** Each axis is tracked on its own; a released key or button
stops its own axis; ■ stops both axes; deactivating, hiding or closing the
dialog stops any axis still moving; a `MoveAxis` that raised keeps its axis
marked (it may have reached the mount). Reopening the dialog uses the current
`Telescope`, and the dialog closes (stopping its axes) when the mount is no
longer connected. `MoveAxis` stays synchronous on the UI thread in 0.5.0:
moving it to the thread pool could reorder a start and its stop.
**Found in review.** A failed `StopAxis` (a network blip) forgot its axis, so
closing, hiding or leaving the dialog did not try again. The axis now stays
marked, with a WARN, and the next close, hide, focus loss or ■ tries again;
after a second failure an ERROR says to use Abort on the Mount card (each try is
a blocking call, and closing the dialog can send close, hide and focus-loss
events in a row).
**How to check.** `tests/ui/test_manual_control_dialog.py`. At the telescope:
hold Up and Right, release Up: altitude stops, azimuth goes on; release Right:
everything stops. Hold Left and click the main window: the mount stops.

### H4 — The clock-error message says GoTo, Sync and Center are refused

**What was wrong.** With the mount clock more than 60 s off, the log said
"GoTo and Sync are disabled" while Slew, Sync and Center stayed enabled. The
`Telescope` guard does refuse them on use: the mount never moved; only the
message was false.
**Who was affected.** Owners of firmware that keeps a stale clock (display).
**What changed.** One message for connect and auto-reconnect: "Mount clock is
N h off — correct the date/time in the Seestar app, then reconnect. GoTo, Sync
and Center will be refused until then."
**How to check.** `tests/core/test_device_session.py::test_mount_clock_error_message_says_what_happens`.

### H6 — The tracking button reads "Tracking" until a poll says otherwise

**What was wrong.** The Mount card's button read "Tracking ON" (green) before
the first position poll and after a disconnect.
**Who was affected.** Display only; tracking is not written to FITS.
**What changed.** Neutral "Tracking" until a poll, and again on disconnect
(without sending a tracking command).
**How to check.** `tests/ui/test_mount_dock.py`.

### H2 — Connect equipment leaves connected devices alone

**What was wrong.** **Connect equipment** stays enabled until all four devices
are connected, and pressing it again reconnected all four: a second mount
poller ran alongside the first (it kept reporting the mount after a
disconnect), the camera was replaced without being disconnected (and its
capabilities re-published under a running sequence), and with two pollers
alive Qt aborted the process at quit (the verifier's probe exited 134; not run
on the full app).
**Who was affected.** Anyone who pressed it again to retry a failed device.
**What changed.** Only devices without a connection are connected; the mount
poller is stopped before a new one starts. A device that misbehaves while
connected is reset with its own Disconnect, then Connect.
**How to check.** The two H2 tests in `tests/core/test_device_session.py`.

### H7, H8 — Disconnect and Quit ask first during a run

**What was wrong.** **Disconnect equipment**, **Disconnect all**, a device
card's **Disconnect** and **Quit** (Cmd+Q) acted at once while a sequence or an
autofocus ran. A camera disconnect makes the sequence worker's next Alpaca call
fail, which ends the run and loses the frame being exposed; quitting stops the
run. Frames already saved are kept.
**Who was affected.** Anyone whose hand slipped during a night.
**What changed.** While a sequence or an autofocus runs, these actions ask a
Yes/No question, No by default; No leaves everything as it was. Idle
disconnects and quits are unchanged.
**How to check.** The H7 and H8 blocks of `tests/ui/test_shell.py`. At the
telescope: Cmd+Q during a sequence, answer No: the run goes on.

### H12 — Connection failures say why

**What was wrong.** Connect with an empty address did nothing; a lost mount
showed a bare "Error" while it was being retried; connect errors were cut to
48 characters ("Cannot connect to 192.168.1.20:3").
**Who was affected.** Display only; the reason was in the Activity log.
**What changed.** An empty address shows "Enter the Seestar IP address or press
Discover." and focuses the field; a lost mount reads "connection lost —
retrying every 10 s"; the device cards show the whole error, wrapped; the
status-bar badge shortens it and shows it whole in its tooltip.
**How to check.** `tests/core/test_device_session.py::test_connection_failures_carry_their_reason`
and `tests/ui/test_settings_telescope.py`.

### H13 — The Settings telescope picker is locked while connected

**What was wrong.** Changing the telescope model in Settings while connected
was refused (the profile was safe) but the picker just snapped back, silently.
**Who was affected.** Display only.
**What changed.** The Settings picker is disabled while any device is connected
or busy, with the Connection page's explanation as its tooltip.
**How to check.** `tests/ui/test_settings_telescope.py` and `tests/ui/test_shell.py`.

## Filter wheel and focuser

### H9 — A refused wheel move ends "busy" and shows the slot the wheel is on

**What was wrong.** When the wheel refused a move, the move task only logged
the error: the wheel stayed "busy" and the Filter selector stayed greyed on the
requested slot until the next camera action. In 0.4.2 the next Take shots
wrote that slot to `FILTER` (see *Check your old files*). In 0.5.0 a Take shot
reads the wheel for `FILTER` (S3), but the S1 Dark/Bias guard reads the
selector: after a refused move to Dark it would have accepted a Dark shot with
the wheel on IR (read from the code, not run at the telescope). Since the
review the guard also needs the wheel to have reported it is on Dark (S1).
**Who was affected.** Rare: it needs the driver to refuse a move.
**What changed.** A refused move reads the wheel back and reports where it is:
the selector is re-enabled on the real slot and the wheel reads "connected"
(or "error — position unknown" when it cannot be read).
**How to check.** `tests/core/test_device_session.py::test_failed_filter_move_ends_busy_and_reports_the_real_slot`.

### H10 — No manual Go to during autofocus; Go to follows MaxStep

**What was wrong.** During autofocus, Go to and Move stayed enabled: a manual
move could be sent mid-sweep, and a sample taken there would enter the V-curve
(wrong best focus). Go to accepted 0 to 200 000 whatever the focuser's
MaxStep, which the driver call clamps silently.
**Who was affected.** Anyone who touched Go to during autofocus.
**What changed.** Out, In, Go to and Move are disabled while autofocus runs
(and stay disabled if the focuser went away meanwhile); Go to's range is
0 to MaxStep from the connected focuser.
**How to check.** `tests/ui/test_capture_cards.py::test_focuser_card_refuses_manual_moves_during_autofocus_and_follows_max_step`.

## Camera card and typed values

### H11 — Typed values are applied when the edit is done

**What was wrong.** Offset and Binning sent each keystroke to the camera
(typing "35" wrote 3, then 35, as a synchronous driver call, also during Live);
the site coordinates rewrote the config file for each keystroke; the IP address
was saved, and probed by the network monitor, one character at a time.
**Who was affected.** Anyone typing in these fields. `OFFSET` in FITS is read
back from the camera, so headers were truthful; a frame exposed during the edit
could have used the intermediate offset (plausible, not run).
**What changed.** These fields commit on Enter or on leaving the field. A
button that uses one (Connect, Save favourite, Take shot, Live) first applies a
value still being typed, because a click does not move the focus on macOS.
**How to check.** `tests/ui/test_capture_cards.py::test_camera_offset_and_binning_reach_the_driver_once_typed`
and `tests/ui/test_settings_telescope.py`.

### H15 — The Camera card names autofocus when autofocus owns the camera

**What was wrong.** A stand-alone autofocus locked the Camera card with
"Sequence running — the sequence owns the camera."
**Who was affected.** Display only.
**What changed.** "Autofocus running — autofocus owns the camera." while
autofocus owns it (also during a sequence's autofocus pass).
**How to check.** `tests/ui/test_capture_cards.py::test_camera_lock_hint_names_the_owner`.

## Planetarium and site search

### H14 — The Stellarium card says why the server is not running

**What was wrong.** When the server's port was taken, the card said "stopped"
with no reason (only the log said "bind … failed — address already in use"),
and Stellarium GoTos never arrived. The running label gave the port without the
host.
**Who was affected.** Display only.
**What changed.** The card shows the error, in red; the running label reads
"listening on host:port".
**How to check.** `tests/ui/test_stellarium_card.py`. At the computer: start the
server on a port already in use: the card names the failure.

### H17 — The site search identifies this release

**What was wrong.** The published 0.4.2 sends "Argos/0.4.1" as its User-Agent to
Nominatim and Open-Meteo. The fix (read `argos.__version__`) landed on
`release/0.4.2` after the tag, untested.
**Who was affected.** Nobody's data; Nominatim's usage policy asks for an
identifying User-Agent.
**What changed.** A test pins the header to `argos.__version__`; it fails on the
v0.4.2 resolver.
**How to check.** `tests/core/test_location_resolver.py::test_search_requests_identify_this_release`.

---

## Deferred to the web UI

Left to the web-UI migration, where they belong to a redesign rather than a
patch:

- Display parts of fixed items: S20 (preview HFD, thresholds, solved plate
  scale), S22 (AF filter and exposure, V-curve plot), S23 (non-blocking stop),
  S11 (`FILT` check, `KNAME` in Review, preview), S10 (whole-session export),
  S15 (geometry controls in Settings), S19 (append-only points), S26 (Baseline
  edits after Find), S4 (calibrated or stacked frames in Observe: refused in
  0.5.0), S5 (`base_dir` in presets).
- Kept as designed in 0.5.0: a Take shot in Live saves the frame already
  exposing with its own settings (S2), so after a Light-to-Dark change that
  frame is saved with its own, truthful `IMAGETYP = 'Light Frame'`. The
  Take-shot wheel checks (S1, S3) know only the moves made from the Camera
  form: a move made from the Seestar app is not seen (the save still reads the
  wheel back for `FILTER`).
- Inventory items not approved for 0.5.0: S6 (cadence column and validation),
  S8 (Find makes any object a photometry target), S21 (pixel readout and
  statistics labels), S25 (two sources of sensor limits), S27 (dither
  docstring versus worker), S28 (time axes), S30 (Centre target on the
  reference WCS, unverified).
- Hardware items not approved for 0.5.0: H1 (every Alpaca connect and command
  runs on the UI thread: an unreachable host freezes the window), H5 (Sync
  syncs the mount to its own polled position), H16 (network probes of
  1.1.1.1 / 8.8.8.8 without opt-in; "no host" and "down" look alike).
- Parts of fixed hardware items: H3 (`MoveAxis` off the UI thread, one jog path
  with a dead-man, arrow keys going to a focused Speed combo, unverified), H4
  (disabling Slew, Sync and Center with the reason), H6 (reading the tracking
  rate back), H8 (bounding the quit time: about 108 s if every worker is
  mid-request, the verifier's sum of the bounded waits in the source, not
  measured; disconnecting the devices at quit; a stopped autofocus still
  returning the focuser can be abandoned by the 5 s quit budget), H9 (a wheel
  still turning after 20 s leaves the selector on the requested slot; a Dark
  shot is refused then, its position being unknown), H10 (polling the focuser
  position and IsMoving, autofocus steps overwriting a typed Go to, Halt during
  autofocus), H11 (holding an arrow on Offset still sends one call per step; a
  site commit still writes the config file five times), H12 (discovery busy
  state, results on the page, choosing among several devices), H14 (editing
  the host, saving the port when edited, reverting the GoTo flash), H17 (the
  search's time budget, up to about 48 s, and cancellation).

## State of the branch

- 623 tests pass, 45 skipped (0.4.2: 534 and 45). Every fix carries a test that
  fails on the code before it, checked commit by commit against its parent; one
  guard test (S3, the wheel cannot be read) pins a fallback 0.4.2 already had.
  Each hardware test was written first and run on the unfixed code (H17
  against the v0.4.2 resolver). H7, H8 and H13 extend the single Shell and
  Settings walkthroughs, so they add assertions rather than tests; so does the
  H3 follow-up (the jog dialog's single test).
- The review re-ran each commit's new tests on its parent tree (71 new tests
  fail there and pass on the commit). The review follow-ups (X1, X2 and the gaps in S1,
  S3, S4, S10, S23 and H3) were checked the same way: each new test fails with
  the commit's source change reverted.
- `ruff` and `black` clean on CI's scope (`argos/`, `tests/`, `main.py`).
- Sphinx builds with `-W` and no warnings. The guide, the photometry reference
  and the install page describe 0.5.0 behaviour (the guide's Connect and
  Observe sections cover the H2, H7, H8, H11 and H12 changes, and the review
  follow-ups: settled wheel for darks, Stop AF return, raw-only Open FITS, the
  site rule, preview-curve export).

## Release

- [x] Hardware-safety items (H1–H17) committed and added to this note (H1, H5,
      H16 deferred).
- [x] Review findings fixed (X1, X2, gaps in S1, S3, S4, S10, S23, H3) and the
      notes corrected (S10 file names, S4, S23, the `SOFTWARE` header).
- [x] Site check against the mount (X3) added, with its tests.
- [ ] Bump the version to 0.5.0 in `pyproject.toml` and `argos/__init__.py`
      (both still say 0.4.2). Until then the branch writes `SOFTWARE = 'Argos
      v0.4.2'` and the site-search User-Agent says 0.4.2; *Check your old
      files* relies on that header to tell fixed frames from affected ones.
- [ ] Tag `v0.5.0`. The Release workflow builds the DMG and the Debian package
      and attaches them to a **draft** release.
- [ ] At the telescope: a Dark Take shot with Filter IR is refused; **+ Add**
      after the wheel connects gives a Light row on IR; Stop AF mid-sweep leaves
      the focuser at its start; connecting the mount with the Settings site
      of another place logs the X3 warning, and with the right site an INFO;
      a run started after a GoTo, without Identify
      field, gets live points once its first frame is solved. Hardware: in
      the jog dialog, hold Up and Right, release Up (altitude stops, azimuth
      goes on), release Right (all stop); hold Left and click the main
      window (the mount stops); Cmd+Q during a sequence asks, and No keeps
      the run; the Stellarium server on a port in use says why on its card.
      Review follow-ups: pick Dark and press Take shot at once (refused: the
      wheel is still turning); in Live, change the filter and press Take shot
      (INFO, the next frame is saved, `FILTER` the new slot); in Live,
      disconnect the mount and press Take shot (no `RA`, `ALTITUDE` or
      `AIRMASS`); time a Stop AF return from the sweep's far end (how close to
      10 s the Seestar focuser comes is not known).
- [ ] Download both installers from the draft, then publish it.
- [ ] Update the download names, sizes, date and release-tag links in
      `README.md`, `docsrc/install.md` and the public site.
- [ ] Merge into `main`.
