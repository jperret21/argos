# Argos 0.5.0 — data-integrity fixes

> Branch: `release/0.5.0`, cut from the published `release/0.4.2`.
> Last updated: 2026-11-01.

A bug-fix release with no new features. Specifying the web UI meant taking an
inventory of the Qt code, and that inventory turned up defects that affect
0.4.2 users today: frames labelled with the wrong settings, a dark that is a
light frame, AAVSO rows naming the wrong star, a live curve that never gets a
point. The science items of that inventory (`web/spec/README.md` §6.1) that
were approved for this release were each reproduced on 0.4.2 before being fixed
here, with a regression test that fails on 0.4.2. Everything that
needs a redesign is left to the web-UI migration and listed at the end.

This note covers the science-data items. The hardware-safety items of the same
inventory (§6.2, H1–H17) are verified separately; they will be added here when
they are committed on this branch.

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
| S4 | **Open FITS** kept the previous frame's time and WCS | A point dated with another frame's time, in the curve, its CSV and AAVSO | **yes** |
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
| S9 | Review read a check star as a second target | Wrong dock and name in Review | no |
| S10 | **Open curve CSV** exported a per-star file under its file name | AAVSO `NAME` wrong; a comparison exportable as the variable | **yes** |
| S11 | AAVSO export kept saturated/suspect points, accepted `OBSCODE=XXX` | Flagged points submitted unflagged | **yes** |
| S12 | Batch re-run looked only for `*.fits` | Never found an Argos session's `.fit` frames | no |
| S13 | Batch re-run: JD 0 for undated frames, cancelled runs saved | JD 0 rows reaching AAVSO; overwritten CSVs | rarely |
| S24 | An ASTAP database folder replaced the chosen database set | Slower or failed solves | no |
| S29 | Two unvalidated-profile warnings, hard-coded IMX585 hint | Contradictory wording | no |

## Check your old files

Most checks below read the files themselves; S14 and S15 use Argos 0.5.0's
batch re-run.

- **Dark and bias Take shots (S1).** A single dark or bias shot whose `FILTER`
  is not `Dark` was exposed to the sky unless the telescope was covered. Compare
  its median level with a sequence dark of the same `EXPTIME` and `GAIN` (a
  sequence moves the wheel to the Dark slot for darks and biases); do not use
  it as a master dark or bias if it is higher. `FILTER = Dark` is not a full
  guarantee in 0.4.2 (S3: a sequence could have moved the wheel since), so
  check the level anyway.
- **Take-shot exposure (S2).** `DATE-AVG` is the midpoint of the exposure as
  timed by the worker (start command to image ready), so
  `2 × (DATE-AVG − DATE-OBS)` is the time the exposure really took, plus
  readout and up to 0.1 s of polling. A 10 s frame saved as
  `EXPTIME = 30` shows about 5 s, not 15 s, between the two. Sequence frames are
  not affected.
- **Take-shot filter (S3).** A Take shot taken after a sequence that changed
  filter carries the Camera form's filter. Compare with the last sequence
  frame's `FILTER` (sequence frames read the wheel back).
- **Take-shot `HFD`, `NSTARS`, `SKYLEVEL` (S20).** Re-measure them; do not sort
  or reject Take shots on these values.
- **Opened frames (S4).** If you opened archived frames in Observe (**Open
  FITS…**) and solved them, the points they produced carry the time of another
  frame or of the solve. They are in the live curve's CSV (`<sessions>/targets/`,
  or the last run's `photometry/` folder if a sequence had run). Remove them
  before any AAVSO export.
- **Black Light frames (S7).** Sequence Light frames with `FILTER = Dark` were
  shot through the opaque slot. The header is truthful; the data are lost.
- **Runs with no live curve (S14) or mixed apertures (S15).** Re-run the batch
  measurement on the run's frames (**Re-run subs…**, which now works on an Argos
  session, S12): it measures every frame with one aperture geometry.
- **AAVSO files (S10, S11).** Do not submit a file with `#OBSCODE=XXX`, or one
  whose `NAME` starts with `TARGET_`, `COMPARISON_` or `CHECK_` (an exported
  per-star CSV). For any 0.4.2 export, compare its rows with the curve CSV's
  `saturated` and `suspect` columns: those points were submitted without a
  flag.
- **Batch CSVs (S13).** A row with `jd_utc = 0` came from a frame without
  `DATE-OBS`. This only happened with frames from other software, and only in
  `*.fits` folders (S12 kept the re-run from finding Argos frames).

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
**How to check.** `tests/workers/test_acquisition_engine.py::test_dark_take_shot_refused_unless_the_wheel_is_on_the_dark_slot`.
At the telescope: Frame type Dark, Filter IR, Take shot: a WARN, no exposure.

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
**How to check.** `tests/workers/test_acquisition_engine.py::test_take_shot_after_a_sequence_records_the_filter_the_wheel_is_on`
(0.4.2: `FILTER = 'IR'` with the wheel on LP).

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
start. The UI still waits up to 10 s for the stop; a non-blocking stop is left
to the web UI.
**How to check.** `tests/workers/test_autofocus_worker.py` (the three Stop
tests) and `tests/ui/test_autofocus_feedback.py`. At the telescope: Stop AF
mid-sweep, then read the focuser position: it is the start.

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
may differ. Not changed: a floating-point FITS is still cast to 16-bit integers
on open (a separate issue).
**How to check.** `tests/workers/test_acquisition_engine.py::test_opened_fits_is_dated_by_its_header_and_drops_the_previous_wcs`
and `::test_opened_fits_without_a_date_measures_no_point`.

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

### S26 — Plan visibility needs the saved site; transit coverage after midnight

**What was wrong.** Without a saved site the visibility curve used latitude and
longitude 0/0; a transit whose midpoint is after midnight was drawn on the wrong
night; **Find** ignored the Baseline field; a missing duration was reported as
"Observing site required".
**Who was affected.** Planning display only; nothing written to files.
**What changed.** No curve without a saved site (a message says why); the plotted
night is the one containing the midpoint; Find uses Baseline; the real cause is
shown.
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
**How to check.** `tests/core/test_session_review.py::test_single_star_csv_restores_role_and_name`
(the comparison file writes no AAVSO row, the target file writes `NAME SS CYG`).

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

---

## Not in this release

Left to the web-UI migration, where they belong to a redesign rather than a
patch:

- Display parts of fixed items: S20 (preview HFD, thresholds, solved plate
  scale), S22 (AF filter and exposure, V-curve plot), S23 (non-blocking stop),
  S11 (`FILT` check, `KNAME` in Review, preview), S10 (whole-session export),
  S15 (geometry controls in Settings), S19 (append-only points), S26 (Baseline
  edits after Find), S4 (float FITS on open), S5 (`base_dir` in presets).
- Inventory items not approved for 0.5.0: S6 (cadence column and validation),
  S8 (Find makes any object a photometry target), S21 (pixel readout and
  statistics labels), S25 (two sources of sensor limits), S27 (dither
  docstring versus worker), S28 (time axes), S30 (Centre target on the
  reference WCS, unverified).

## State of the branch

- 594 tests pass, 45 skipped (0.4.2: 534 and 45). Every fix carries a test that
  fails on the code before it, checked commit by commit against its parent; one
  guard test (S3, the wheel cannot be read) pins a fallback 0.4.2 already had.
- `ruff` and `black` clean on CI's scope (`argos/`, `tests/`, `main.py`).
- Sphinx builds with `-W` and no warnings. The guide, the photometry reference
  and the install page describe 0.5.0 behaviour.

## Release

- [ ] Hardware-safety items (H1–H17) committed and added to this note.
- [ ] Bump the version to 0.5.0 in `pyproject.toml` and `argos/__init__.py`
      (both still say 0.4.2).
- [ ] Tag `v0.5.0`. The Release workflow builds the DMG and the Debian package
      and attaches them to a **draft** release.
- [ ] At the telescope: a Dark Take shot with Filter IR is refused; **+ Add**
      after the wheel connects gives a Light row on IR; Stop AF mid-sweep leaves
      the focuser at its start; a run started after a GoTo, without Identify
      field, gets live points once its first frame is solved.
- [ ] Download both installers from the draft, then publish it.
- [ ] Update the download names, sizes, date and release-tag links in
      `README.md`, `docsrc/install.md` and the public site.
- [ ] Merge into `main`.
