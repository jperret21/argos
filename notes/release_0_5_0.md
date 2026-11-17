# Argos 0.5.0 — the first beta of the new ARGOS, and the fixes found on the way

> Branch: `release/0.5.0`, cut from the published `release/0.4.2`.
> Last updated: 2026-11-16.

ARGOS 0.5.0 is the first beta of the new ARGOS: a stable version with the new
interface. The PyQt6 application is retired. ARGOS is now a web interface
(`web/`) in a desktop app for macOS and Linux (`web/src-tauri`), driven by a
headless server (`argos/server`); the Qt code stays in the repository only as
the reference of the parity tests. The release also brings every fix listed
below: data-integrity, hardware-safety and photometry fixes (S1–S85, H1–H17,
X1–X3), the photometry ones checked against references independent of the old
app (the Siril reduction of a real night, astropy, the VSP catalogue, the
frames' own noise). ARGOS does not calibrate its frames (no bias, dark or flat),
and neither did that Siril reduction: the agreement checks the measurement, not
a calibration (see *Not in 0.5.0: calibration* below). Patch releases 0.5.x
will follow. The web interface was
tested with its simulator and with replays of real nights; it has not yet been
used live on a telescope. This file lists the fixes; the interface is described
in the documentation and in `web/spec/progress.md`.

How the fixes were found. Specifying the web UI meant taking an inventory of
the Qt code, and that inventory turned up defects that affected 0.4.2 users: frames labelled with the wrong settings, a dark that is a
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
**S38** (a reader could see a live curve CSV half written). Three defects they
reported for an owner decision are fixed too, each with a test that fails on
the code before it: **S39** (Open FITS dated a 0.4.x sequence frame by its late
`DATE-AVG`), **S40** (measuring an object again outside a run overwrote its
live curve CSV) and **S41** (a saved frame's errors used the Camera form's
gain); and **S42**, found while fixing S41 (the header `EGAIN` skipped the gain
table the photometry uses).

Porting the Plan and the sequences to the web UI (its wave 6a) found five more,
each with a test that fails on the code before it: **S43** (a batch re-run kept
measuring on blank sky after a field jump and said "tracked"), **S44** (a run
measured its Dark, Flat and Bias subs, which also changed the Light points
after them), **S45** (a live point measured after a run went into that run's
CSVs), **S46** (identifying the field turned the check star into a comparison)
and **S47** (the Plan editor cut a count, an interval or a dither to its range
without a word, and a transit of more than 9999 frames lost its end).

Comparing the Qt sequence tracker with the web one on the owner's runs
(`notes/tracker_comparison.md` on the web-UI branch) led to four owner
decisions (2026-11-12), applied in the web UI's wave 6b, each with a test that
fails on the code before it: **S48** (after a field jump the tracker could
follow a neighbour or noise and the frame was measured off its stars), **S49**
(a run through two filters mixed them in one curve per star), **S50** (a wrong
plate solution replaced the good one) and **S51** (the live and batch airmass
left out the precession since J2000). The wave's science review found two more:
**S52** (a target-set change between two solves rebuilt the tracker on the stale
solution, and S48 passed it with 1 anchor of 1) and **S53** (the AAVSO export
wrote a two-filter run under one `FILT`). Four owner decisions of 2026-11-14
close what those reviews left open: **S54** (a new plate solution that the
tracker's anchors do not confirm is refused), **S55** (S50's scale reference
moves when three solves agree), **S56** (a lock on fewer than 3 anchors is
unverified: its points are flagged suspect) and **S57** (every vetting file names
its filter); the owner's decisions of 2026-11-15 refine S54 (a re-pointing the
mount did not report is accepted after three agreeing solutions) and S56 (a lock
near a fresh solution is verified, the anchors are chosen on the solved frame, and
a run's sub verified through the previous solution is solved too), and add
**S58** (the batch re-run gets S56's rule) and **S59** (a camera frame after an
opened FITS drops the file's tracker, and the file's anchors never check a camera
solution).

Porting Review's exports and batch re-run to the web UI (its wave 7) found four
more, each with a test that fails on the code before it: **S60** (the AAVSO export
wrote a pre-0.5.0 batch CSV's undated points as rows dated JD 0), **S61** (Export
measurements of a two-filter run merged a star's two curves when read back),
**S62** (the batch re-run measured another object's frames against the target set)
and **S63** (a batch re-run of a session folder also measured the links and
registered copies Siril had written beside its lights: each epoch three times).
**S64**-**S84** follow from the same wave's checks against references independent of
the app (Siril reductions, astropy, VSP, the frames' own noise) and the owner's
decisions of 2026-11-15 and 2026-11-16: the airmass (S66, S78), the error model
(S71-S76: the measured e-/ADU, the green-plane noise, scintillation, the sky
estimate), the tracker (S69, S80), proper motions (S77), crowded comparisons (S79),
three defects their reviews found (S81-S83), and the noise model and the camera's
e-/ADU locked during a run (S84); each is in the table below.

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
| S39 | Open FITS dated a frame of a 0.4.x sequence by its late `DATE-AVG` | Points of replayed 0.4.x sequence frames: seconds late, BJD with them | **yes** |
| S40 | Outside a run, measuring an object again overwrote its live curve CSV | Earlier points of `<sessions>/targets/<object>_<star>.csv` gone from disk | **yes** |
| S41 | A saved frame's errors used the Camera form's e-/ADU, not the frame's | `mag_err` and SNR of Open FITS and batch re-run points; magnitudes unchanged | **yes** |
| S42 | The header `EGAIN` skipped `camera.egain_table` | With a table entry for the gain: `EGAIN` is not the e-/ADU the errors used | **yes** |
| S9 | Review read a check star as a second target | Wrong dock and name in Review | no |
| S10 | **Open curve CSV** exported a per-star file under its file name | AAVSO `NAME` wrong; a comparison exportable as the variable | **yes** |
| S11 | AAVSO export kept saturated/suspect points, accepted `OBSCODE=XXX` | Flagged points submitted unflagged | **yes** |
| S12 | Batch re-run looked only for `*.fits` | Never found an Argos session's `.fit` frames | no |
| S13 | Batch re-run: JD 0 for undated frames, cancelled runs saved | JD 0 rows reaching AAVSO; overwritten CSVs | rarely |
| S43 | Batch re-run: a field jump left the apertures on blank sky, and the summary said "tracked" | Unflagged blank-sky points; missing points; a run reported tracked | no (none of the owner's runs was re-run) |
| S44 | A run measured its Dark, Flat and Bias subs | Junk points in the run's CSVs; the Light points after a calibration sub measured with a moved tracker | only runs mixing calibration and Light steps (none of the owner's) |
| S45 | A finished run's folder stayed the live photometry's | Live points measured after the run appended to its CSVs; its `photometry_quality.json` rewritten | **yes** (one of the owner's runs) |
| S46 | Identifying the field turned the check star into a comparison | No check-star curve; the check in the ensemble | only with a check star (none in the owner's runs) |
| S47 | The Plan editor clamped count, interval and dither silently; a transit over 9999 frames was cut | Fewer frames than planned; a transit's end not observed while `observation.json` declared it | possibly (a run shorter than its plan) |
| S48 | After a field jump the tracker could follow a neighbour or noise, and the frame was measured | Unflagged points of every star off their stars, in live and sequence runs | no (the owner's runs as shot: only S35's frames) |
| S49 | A star had one live curve whatever the filter | Two bands in one curve, one CSV, one `sigma_syst`, one comparison vetting | only runs through two filters (none of the owner's) |
| S50 | A wrong plate solution replaced the good one | The next frame's points measured off every star, unflagged | **yes** (one of the owner's runs) |
| S51 | The live and batch airmass left out the precession since J2000 | CSV `airmass` / AAVSO `AMASS` off by up to ±0.08 at 10-15° (either sign, by position and hour angle; the owner's runs: low by 0.0008 at 68°, 0.004 at 41°, 0.029 at 12°) | **yes** (0.4.2 live curves, batch re-runs) |
| S52 | A target-set change between two solves rebuilt the tracker on the stale solution | Unflagged points of every star on blank sky until the next solve, in sequence runs | possibly (the VSP backfill after a run's first solve; check below) |
| S53 | The AAVSO export wrote every filter's curves under one `FILT` | A two-filter run reported as one band | only runs through two filters (none of the owner's) |
| S54 | A wrong plate solution at the right scale replaced the good one | The next frames' points measured off every star, unflagged | no (the owner's one wrong solve is S50's) |
| S55 | S50's scale reference was the session's first solve, wrong or not | After a wrong first solve, every later good solve refused until the camera reconnected | no (the owner's first solves were all good) |
| S56 | With 1 or 2 anchors the S48 lock check verified nothing | Points of an unverified lock unflagged (off their stars after a jump or a stale rebuild) | **yes** (XX Cyg 2026-08-29 `050148Z` and `052943Z`; replayed with a solve before every sub: 3 target points now flagged suspect; check below) |
| S57 | `photometry_quality.json` did not say which filter it vets | A two-filter run's vetting file ambiguous (format only) | no (format: an added key) |
| S58 | Batch re-run: with 1 or 2 anchors the S43 lock check verified nothing | Unflagged points of an unverified lock (XX Cyg `050148Z` re-run: 4 target points 2.5-4.5 px off their star) | no (none of the owner's runs was re-run) |
| S59 | A tracker built on an opened FITS survived the return to camera frames (or, in a run, was rebuilt on the file's anchors) | The camera's correct solutions refused by S54 against the file's anchor stars | no (S54 is new in 0.5.0) |
| S60 | The AAVSO export wrote undated points (JD 0, from a pre-0.5.0 batch CSV) | Rows dated `0.000000` (4713 BC) in an AAVSO report | rarely (reports exported from a 0.4.x batch re-run of frames without `DATE-OBS`; none of the owner's) |
| S61 | Export measurements wrote a star's curves of two filters under one `star_id` | Read back, both bands became one curve | only runs through two filters (none of the owner's) |
| S62 | The batch re-run measured every object's lights in the chosen folder | Another field's frames measured against the target set: blank-sky points | no (none of the owner's runs was re-run) |
| S63 | The batch re-run of a session folder measured the FITS other programs wrote beside lights/ | Each epoch measured three times (links to the lights, registered copies) | no (none of the owner's runs was re-run; RR Lyr 2026-09-25 would have been) |
| S64 | The AAVSO report's `#SOFTWARE` line named no version | `#SOFTWARE=Argos` where the format asks for the name and version | **yes** (every AAVSO report: a header line only, no observation) |
| S65 | The Frame Viewer read a calibrated float frame in [0, 1] as is | Measure star: SNR 0, peak 0 ADU; Identify field: a black plane for ASTAP | only frames from other software (Siril's `r_light_*.fit`); display only, nothing written |
| S71 | The ensemble zero point was the plain mean of the comparisons, whatever their SNR | Comparisons at SNR 1-4 pulled the zero point as much as a bright one; the error ignored them | **yes** (XX Cyg 2026-08-29 `050148Z`: check star +0.28 mag off its VSP V; others by a few mmag) |
| S72 | The noise model used one raw pixel's gain and counted the black level as sky photons | SNR and `formal_mag_err` off (sky σ +87 % on RR Lyr, −5 to −8 % on XX Cyg); the green-plane model is now the default | **yes** (every SNR and formal error) |
| S73 | The e-/ADU the S30 Pro writes and uses at gain 80 (driver 0.8, IMX585 reference 1.723) is not its photon transfer's 0.228 ± 0.005 | Poisson errors of stars 1.9-2.7× too small; every SNR gate read another SNR on 0.4.1 and 0.4.2 frames | **yes** (every run at gain 80; re-run for honest errors) |
| S74 | No error term held scintillation | Bright stars' errors 2.2-2.4× below their scatter (RR Lyr 2026-09-25) | **yes** (every run) |
| S75 | The flux error ignored the error of the subtracted sky level | Faint stars' errors too small (the sky variance short by 57 % with a 5.3 px aperture) | **yes** (every run) |
| S76 | The sky under each aperture was the annulus median, which sits on the 8-ADU-stepped green plane's 4-8 ADU grid | A sawtooth of about 2 ADU rms per pixel in no error term: 0.004-0.005 mag rms per bright RR Lyr star, the largest part of the RR Lyr − Siril residual (robust σ 0.0101 → 0.0083 with the clipped mean now used) | **yes** (every run; a re-run changes magnitudes and errors slightly) |
| S77 | Target sets held J2000.0 positions; no aperture followed its star's proper motion | RR Lyr's aperture 0.99 green px from the star in 2026, its comparisons 0.27-0.43 px (magnitudes barely affected) | **yes** (RR Lyr: every run; other stars by their motion) |
| S78 | Since S66 every star took the header `AIRMASS`, the field centre's | A comparison or check curve's airmass up to 0.020 off its own (RR Lyr 2026-09-25); `AMASS` (the target's) unaffected | **yes** (comparison and check curves; Review now computes their own) |
| S79 | Nothing named a comparison with a brighter star of the set within its aperture's reach | XX Cyg 2026-09-07: 000-BJV-173 6.8 px from 000-BJV-169, 1.47 mag brighter, unnoticed | **yes** (the XX Cyg 2026-09-07 set) |
| S80 | The tracker's fit rejected one anchor at most | A second wrong anchor moved every aperture (XX Cyg 2026-09-07 sub `_00020`: no target point) | possibly (frames with two wrong anchors; none with the current anchors) |
| S81 | An aperture or sky annulus partly off the frame was measured, truncated | Unflagged comparison and check rows up to 5 mag faint near the edges (RR Lyr 2026-09-25: 000-BJW-667, 000-BJW-668) | **yes** (rows within 12 green px of an edge) |
| S82 | The batch re-run took an OBJECT in SIMBAD's form ("V* XX Cyg") for another object | "No frames": the run's lights not measured | no (nothing was written) |
| S83 | Live and sequence photometry took the e-/ADU at the Camera form's gain, not the frame's | A step at another gain measured with the form's e-/ADU (since S73 26 % apart between gains 80 and 100) | only steps at another gain than the form's |
| S84 | The noise model, its read noise and the camera's e-/ADU (gain table, photon-transfer folder) could change during a run (web Settings; Qt's photon-transfer folder) | The SNR the gates read and the formal errors changed partway through one curve | no (no released version could) |
| S85 | The live and sequence paths wrote a target measured below SNR 3 (no detection) unflagged; only Review, the AAVSO export and a re-run flagged it (S67) | An unflagged no-detection point in the live CSV and curve, and a larger live `sigma_syst` on every row (XX Cyg 2026-09-07 `040723Z` replayed: 0.077-0.080 → 0) | **yes** (live CSVs of runs with such a frame; Review and the export already leave them out, S67) |
| S66 | Review, Analyze and the batch re-run used the airmass computed for the Settings site, wrong on some runs (X3) | AAVSO `AMASS` 4.088-1.514 where the airmass was 1.033-1.364 (RR Lyr 2026-09-25); 0.013-0.015 high under X3's 5° tolerance (a re-run of XX Cyg 2026-08-29) | **yes** (RR Lyr 2026-09-25; Review now takes each frame's header `AIRMASS`, the files are unchanged) |
| S67 | Review, the AAVSO export and the batch re-run kept the rows S35 now refuses (no detection) | Blank-sky rows submitted; a larger `sigma_syst` and `MERR` on every row of the run | **yes** (RR Lyr 2026-09-25: 2 frames; XX Cyg 2026-09-07 `040723Z`: its target on 1 frame) |
| S68 | Comparisons picked before 0.4.2 never got their VSP chart | `CHART` na on every report of those objects, new runs included | **yes** (every report of the owner's objects; header lines only, no observation) |
| S69 | The tracker's centroid stayed 30-80 % of the way to its search window's centre, so on a fast-turning alt-az field the apertures lagged the stars; nothing checked them against the stars | XX Cyg 2026-09-07 `040723Z`: the field turned 16.49°, the tracker found 15.37°; comparisons 4.4-8.5 px off their stars at the end of a re-run, 0.5-3 px in the live path | **yes** (alt-az runs whose field turns fast: XX Cyg 2026-09-07 and 2026-08-29; RR Lyr 2026-09-25 by 0.5 px) |
| S70 | The batch re-run chose the tracker's anchors and checked its lock with the request's e-/ADU, not the frame's (S41's residue) | Other anchors and lock checks than the frame's own SNR gives (XX Cyg 2026-09-07: 5 anchors at 0.8 e-/ADU, 6 at the frames' 1.723) | no (none of the owner's runs was re-run) |
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
  is off by less than 0.03 s. Since S66, Review and Analyze's **Open curve
  CSV** make this check (a warning) and export each frame's header `AIRMASS`
  themselves, whatever the site.
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
  the run's `<object>_live_diagnostics.jsonl`, look for frames on which the
  target and most comparisons have `snr` below 5, or on which the target's
  `snr` falls more than tenfold from the frames around it (a frame measured
  through a wrong solution can keep a comparison or two above 5): drop every
  star's row at that frame's
  `jd_utc` in the run's curve CSVs, and recompute `sigma_syst` without them
  (it is estimated from every point of the run, so those rows raised it on
  every row). One real run (RR Lyr, 2026-09-25, 195 frames) had two such
  frames: the target 7.547 ± 0.757 and 6.257 ± 1.043, about 1.4 mag off its
  neighbours, and `sigma_syst` 0.0166 instead of 0.0150. Since S67, Review,
  Analyze's **Open curve CSV** and the batch re-run apply this rule (a zero
  point more than 1 mag from the run's: every point of the frame; a target
  below SNR 3: that target's points) and recompute `sigma_syst` themselves.
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
- **Replays of 0.4.x sequence frames (S39).** Points measured with **Open
  FITS…** from those frames are late by the S36 amount; replay them again
  with 0.5.0, which dates them by `DATE-OBS + EXPTIME/2`.
- **Overwritten live curves (S40).** A `<sessions>/targets/<object>_<star>.csv`
  holds only the last sitting with that object (since the last object change
  or restart): earlier points of that object measured outside a run are no
  longer in it. Frames saved with **Take shot** can be measured again.
- **Errors of replayed and re-run points (S41).** When the frames' gain
  setting was not the one on the Camera form at replay time, the `mag_err` and
  SNR of those points used the wrong e-/ADU; the magnitudes are right.
  Re-measure before you use those error bars.
- **`EGAIN` with a gain table (S42).** Only if `camera.egain_table` has an
  entry: the `EGAIN` of frames taken at that gain is the driver's or the
  sensor reference's value, not the table's that the errors used.
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
  `*.fits` folders (S12 kept the re-run from finding Argos frames). An AAVSO
  report exported from such a CSV (S60) has rows with `DATE` `0.000000`:
  retract them.
- **Batch re-runs across a pointing jump (S43).** A re-run's
  `<object>_diagnostics.jsonl` (written when diagnostics are on) has one
  `star` record per star and frame: frames on which every comparison has
  `snr` below 5 were measured on blank sky after the field jumped; drop every
  star's row at those frames' `jd_utc` from the re-run's CSVs, then re-run with
  0.5.0. Without the diagnostics file, re-run the folder with 0.5.0 and compare
  the two CSVs: rows that differ by more than their `mag_err` are the affected
  ones. 0.4.2 could only re-run `*.fits` folders of other software (S12); the
  owner's sessions hold no `photometry_rerun_*` folder.
- **Runs that mixed calibration and Light steps (S44).** A run whose plan had a
  Dark, Flat or Bias step and a target set wrote a row for each calibration
  sub: drop the rows whose `jd_utc` is that of a frame in the run's `darks/`,
  `flats/` or `biases/` folder (`DATE-OBS` plus half `EXPTIME`). The Light rows
  after a calibration sub were measured with an aperture tracker moved by it
  (on one replay, a target 1.2 mag off and comparisons up to 2.2 mag off): re-run
  the batch on the run (0.5.0 leaves calibration frames out) rather than keep
  them. None of the owner's runs holds a calibration folder.
- **Live points written into a finished run (S45).** After a sequence, live
  preview kept writing into the run's `photometry/` CSVs and rewrote its
  `photometry_quality.json`. In a run's CSVs, rows whose `jd_utc` is after the
  last saved sub's `DATE-OBS` plus `EXPTIME` (and a minute of margin) are not
  the run's: drop them, and do not trust the run's `photometry_quality.json`
  (re-run the batch to rebuild it). One of the owner's runs has them:
  `20260925T195307Z_RR_Lyr` (5 lights) has 2 rows per star 1.6 and 4.0 min
  after its last sub, and two comparison CSVs holding only those rows.
- **Check stars (S46).** If you had assigned a check star before the field was
  identified, look in the run's `targets.json`: a check star listed as a
  comparison (same AUID) was used in the ensemble and has no `check_*.csv`.
  Re-assign it and re-run the batch. The owner's runs have no check star.
- **Runs shorter than their plan (S47).** A preset or transit whose count was
  over 9999, interval over 3600 s or dither over 999 ran with those limits
  instead, with no note. For a transit, compare the run's last frame with the
  coverage end in its `observation.json`: a coverage over 9999 frames (for
  example 120 min of baseline at a 1 s cadence) stopped early.
- **Points after a field jump (S48).** On such a frame most anchor comparisons
  have `snr` below 5 in the run's `<object>_live_diagnostics.jsonl`: the S35
  check above finds them too. On the owner's runs as shot (a solve before
  every sub) S48 changes no point; on a replay with one solve for a whole run
  it refuses 74 RR Lyr frames, all measured 21-395 px from the star.
- **A wrong plate solution (S50).** The sub after a solve whose scale is not
  the night's was measured through it. One of the owner's runs has one:
  `20260907T045156Z_XX_Cyg`, its third sub (measured through the second sub's
  7.093″ per green px solve): drop every star's row at that sub's `jd_utc`.
  Elsewhere the S35 check above finds such a sub (the target's `snr` falls more
  than tenfold from the subs around it).
- **Airmass of 0.4.2 curves and of batch re-runs (S51).** The CSV `airmass`
  (and AAVSO `AMASS`) computed from the star's coordinates ignored the
  precession since J2000: on the owner's runs low by 0.0006-0.0008 at 67-69°,
  about 0.004 at 41° and up to 0.029 at 12°; elsewhere off by up to ±0.08 at
  10-15°, either sign, by position and hour angle. Recompute it from `jd_utc`, the
  star's coordinates and the site (astropy, or a 0.5.0 batch re-run) before
  any extinction fit or AAVSO export. Curves written by 0.4.1 live (the
  owner's XX Cyg nights) took the mount's altitude, as the header `AIRMASS`
  does, and are not affected; the header `AIRMASS` never is.
- **Points after a set change during a run (S52).** A target-set change between
  two solves (the VSP comparisons arriving after a run's first solve, a role
  edit, Recommend) rebuilt the tracker on the last solve's positions while the
  field had drifted since. In a run's `photometry/` CSVs, look for target rows
  whose `zero_point` departs by more than 1 mag from the run's median (or whose
  `snr` falls below 3) in the subs that follow a "comparison(s) selected" or a
  role edit in the Activity log, until the next solve: drop every star's row at
  those `jd_utc`. The science review's replay of the owner's RR Lyr 2026-09-25
  frames 0-79 through the server found five such target points (frames 4, 7,
  8, 10, 11; SNR 0-2.6); the owner's Qt runs as shot solved before every sub,
  which limits this to the subs measured before the next solve.
- **Points measured on a lock of 1 or 2 anchors (S56).** A sub on which fewer
  than 3 comparison or check stars reached SNR 10 unsaturated (the tracker's
  anchors) was measured through a lock nothing verified. 0.5.0 still verifies
  such a sub when it is measured within 2 px of a solution of that sub or the one
  before, which old files do not record. In a run's
  `<object>_live_diagnostics.jsonl`, count per `frame` the `star` records of role
  `comparison` or `check` with `snr` ≥ 10 that are not `saturated`: below 3,
  treat that sub's rows as suspect (set `suspect` to 1 in the CSVs before an AAVSO
  export). The rule is conservative: on the owner's files it flags every frame of
  XX Cyg 2026-08-29 `050148Z` (22) and frames 0-3 of `052943Z`, frame 2 of
  2026-09-07 `045156Z`, the frames of the three diagnostics files in the `045626Z`
  folder (2 + 34 + 3; RR Lyr and M 27 runs among them) and RR Lyr 2026-09-25
  `200453Z` frames 52 and 175 (`_00053`, `_00176`, the two blank-sky points S35
  now drops). The replay of the study runs through 0.5.0 (a solve before every
  sub) leaves 3 of them flagged: `050148Z` frames 0 and 13 (its target point
  3.4 px off the star) and `052943Z` frame 0; the other frames the rule flags are
  within 2 px of their star, or degraded or blank-sky subs, harmless to drop.
  Rather than flagging by hand, re-run the batch measurement on the run (S58):
  it verifies each such sub with a plate solve and flags only those it cannot
  verify. Re-running `050148Z` with ASTAP: 22 of 22 subs verified (13 by a fresh
  solve, the others within 2 px of the previous sub's), none flagged. Review
  and the AAVSO export keep these rows (S67 drops only the no-detection ones)
  and say so.
- **Which filter a vetting file vets (S57).** A `photometry_quality.json`
  without a `filter` key was written before 0.5.0. On a one-filter run it vets
  that filter. On a two-filter run it vets both bands' points together (one
  curve per star before S49) and should not be read as either filter's;
  `photometry_quality_<filter>.json` (0.5.0 only) names its filter in the file
  name.
- **Errors of every run at gain 80 (S72-S75).** The `EGAIN` of the owner's frames
  (0.8 from 0.4.2, 1.723 from 0.4.1) is 3.5× and 7.6× the S30 Pro's measured
  0.228 e-/ADU, and the errors held neither scintillation nor the sky estimate's
  error: the `mag_err`, `formal_mag_err` and SNR of every point, live CSV or re-run,
  were too small for bright stars (RR Lyr 2026-09-25: the star pairs scatter 2.3×
  their formal errors) and off by tens of per cent for faint ones. The magnitudes
  are unchanged. Re-run a session (**Re-run subs…**) for honest errors: RR Lyr's
  pairs then scatter 0.9× their formal errors, XX Cyg 2026-09-07's 1.1×; the
  frames' header `EGAIN` stays as written (Argos ignores it for this camera).
- **Zero points of mixed ensembles (S71).** A run whose comparisons mix bright
  and faint stars (Review's `faint_comparisons` warning: their median SNR below
  10; or, in `<object>_live_diagnostics.jsonl`, comparisons at `snr` below 10
  beside one well above) was calibrated by the plain mean of all of them. Re-run
  it (**Re-run subs…**): XX Cyg 2026-08-29 `050148Z`'s check star moves from
  +0.155 ± 0.079 to +0.055 ± 0.027 mag from its VSP V (+0.051 ± 0.023 with
  S69 and S70, one frame flagged by S71's heavy-comparison rule). Ensembles of
  similar stars move by a few mmag (RR Lyr 2026-09-25: 1-3 mmag).
- **Apertures on a fast-turning alt-az field (S69).** A run whose field turned
  fast (Review's re-run summary, or the `rotation_deg` of the `tracking` records
  of a re-run's flight recorder: XX Cyg 2026-09-07 turned 0.7° per sub) was
  measured through apertures that lagged the stars: 4.4-8.5 px off the
  comparison stars at the end of a batch re-run of XX Cyg 2026-09-07
  `040723Z`, 0.5-3 px in the live path with one solve per run, 0.2-1.5 px with a
  solve before every sub (the owner's runs, as shot). Re-run the batch
  measurement (**Re-run subs…**): the apertures then sit within 0.2 px of each
  frame's own plate solution. On `040723Z` the check star 000-BJV-169 moves from
  −0.045 ± 0.017 to −0.074 ± 0.009 mag from its VSP V (VSP gives that V
  ± 0.051) and its point-to-point scatter halves; on XX Cyg 2026-08-29
  `050148Z` it moves from +0.060 ± 0.029 to +0.051 ± 0.023 (with S71); RR Lyr
  2026-09-25 moves by 1 mmag.
- **The sky under every aperture (S76).** The sky was the annulus median, which
  sits on the 4-8 ADU grid of the green plane: about 2 ADU per pixel of error that
  followed the sky level slowly, in no error term (0.004-0.005 mag rms per bright
  RR Lyr star, about 0.05 mag for a faint XX Cyg comparison). Nothing in a file
  shows it. Magnitudes and errors of old runs change slightly when re-run (**Re-run
  subs…**): RR Lyr 2026-09-25's target by 5 mmag rms per point, its scatter against
  the Siril reduction 0.0101 → 0.0083 mag.
- **Rows near the frame's edge (S81).** A comparison or check star (or a target)
  within 12 green px of an edge was measured through a clipped aperture or sky
  annulus: up to 5 mag faint, unflagged (RR Lyr 2026-09-25 `200453Z`'s
  000-BJW-667 frames 130-131 and 000-BJW-668 frames 181-182, 13 such rows). Find
  them by the `x`, `y` of the flight recorder's `star` records; a re-run (**Re-run
  subs…**) leaves them out.
- **Steps at another gain than the Camera form's (S83).** A sequence step (or a
  live frame) at a gain other than the form's was measured with the form's
  e-/ADU: its SNR and errors are off by the ratio (gain 100 with the form at 80:
  0.228 for 0.181 e-/ADU). A re-run uses each frame's own.
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

### S39 — A 0.4.x sequence frame is dated by its start, not its late `DATE-AVG`

**What was wrong.** S36 fixed the writer, not the files: a sequence frame of
0.4.x has a `DATE-AVG` late by half the download (+5.2 s median, +16.6 s at
most on RR Lyr 2026-09-25), and **Open FITS…** dates a frame by `DATE-AVG`
(S4). Its live point had used `DATE-OBS + EXPTIME/2`, so the replay of the same
frame came out seconds later, and its BJD with it.
**Who was affected.** Replays of sequence frames written by 0.4.x.
**What changed.** A frame whose `SOFTWARE` (or `SWCREATE`) is `Argos` or
`Argos v0.x` below 0.5 is dated by `DATE-OBS + EXPTIME/2`. Frames of 0.5.0 and
later, and of other software, keep `DATE-AVG`. A 0.4.x Take shot had a right
`DATE-AVG`; for it the two differ by the exposure-end latency only (well under
a second). Its `DATE-OBS` was early by the read-backs (tens of milliseconds).
**How to check.** `tests/workers/test_acquisition_engine.py::test_a_frame_written_before_0_5_is_dated_by_its_start`
(a 0.4.2 frame dated 20:05:20.4, its `DATE-AVG`, instead of 20:05:12 on the
code before the fix).

### S41 — A saved frame's errors use its own gain

**What was wrong.** The e-/ADU in a point's errors came from the Camera form's
gain and the connected camera's driver, also for a frame opened with **Open
FITS…** or re-measured with **Re-run subs…**, whose `GAIN` may differ. The
formal errors and the SNR of those points were wrong; the magnitudes are not
affected.
**Who was affected.** Replays and batch re-runs of frames taken at another gain
than the form's at that moment, or with another camera connected.
**What changed.** A saved frame uses the `camera.egain_table` entry for its own
`GAIN`, else its `EGAIN`: the value its live measurement used. Only a frame
that records neither falls back to the live order at the form's gain.
**How to check.** `tests/workers/test_acquisition_engine.py::test_an_opened_frame_uses_its_own_gain_for_errors`
(the driver's 2.5 instead of the frame's 0.31 on the code before the fix),
`tests/workers/test_photometry_batch_worker.py::test_batch_errors_use_each_frames_own_gain`
(the form's 1.0 for all three frames instead of 0.29, 0.42 and 1.0) and
`tests/core/test_photometry_core.py::test_frame_egain_is_the_frames_own_gain`.

### S42 — The header `EGAIN` is the e-/ADU the photometry uses

**What was wrong.** The photometry takes the e-/ADU from `camera.egain_table`
for the gain setting, else the driver, else the sensor reference, and the
photometry reference says that value goes into `EGAIN`; the FITS writer skipped
the table.
**Who was affected.** Only setups with a `camera.egain_table` entry (empty by
default).
**What changed.** The writer resolves `EGAIN` in the same order; the comment
names the source (`egain_table`, `driver` or the sensor reference).
**How to check.** `tests/core/test_fits_writer.py::test_egain_header_is_the_value_the_photometry_uses`.

### S65 — The Frame Viewer measures a calibrated float frame in counts

**What was wrong.** The Frame Viewer (**Analyze › Open frame**) read a FITS as
its numbers. A calibrated float frame whose values lie in [0, 1] (the convention
of Siril's `r_light_*.fit`, as in star_var_script's `process/` folder beside a
session's lights) gave **Measure star** an SNR of 0 and a peak of 0 ADU (the sky
σ is floored at one count and the peak truncated to an integer), and
**Identify field** handed ASTAP a black plane. Found by the web UI's wave 7
technical review on the owner's RR Lyr 2026-09-25 folder.
**Who was affected.** Anyone opening such a frame in the Frame Viewer. Display
only: nothing is written, no curve or report uses these numbers.
**What changed.** `read_fits_2d` scales a float frame whose values all lie in
(0, 1] by 65535, as the web viewer does. Integer frames and float frames in
counts are read unchanged.
**How to check.** `tests/ui/test_frame_viewer_fits.py::test_a_float_frame_in_0_1_is_measured_in_counts_s65`
(SNR 0 on the code before the fix) and `::test_a_float_frame_in_counts_is_read_unchanged`.

### S59 — A camera frame after an opened FITS drops the file's tracker

**What was wrong.** An opened FITS is solved and measured, which builds the
aperture tracker on the file's field. Back to camera frames, the engine kept that
tracker: the camera's first solution was checked by S54 against the file's
anchor stars and refused while the camera pointed elsewhere (refused until a
slew, a set change or, since the 2026-11-15 amendment of S54, three agreeing
solutions).
**Who was affected.** Nobody before 0.5.0: S54 is new in it. Found by the
2026-11-14 review.
**What changed.** The first camera frame (live or a run's sub) after an opened
FITS drops the tracker, as the web server does when the frame source changes
(`source_changed`). The file's solution stays until the camera's own solve, as
before. And while that solution is the reference, a camera frame's solution is
not checked against the anchors (`AcquisitionEngine._solution_from_file`): since
S56's second amendment (2026-11-15) the anchors are chosen on the frame the
solution was solved on, so a run's first sub, measured through the file's
solution, rebuilt its tracker on the file's anchors, and the sub's own solution
was refused against them again while the camera pointed elsewhere (until S54
accepted three agreeing solutions as a re-pointing, with no point meanwhile;
found by the review of that amendment). That sub still gets
no point (its lock is lost, or no anchor is found) and a re-solve is due; a
re-solve of the opened file itself is still checked; once the camera's solution
is the reference, its own anchors check the next solutions (S54).
**How to check.** `tests/workers/test_acquisition_engine.py::test_a_camera_frame_after_an_opened_fits_drops_its_tracker_s59`
(the file's tracker kept on the code before the fix) and
`::test_a_run_after_an_opened_fits_accepts_the_camera_solution_s59` (a run's
first sub after the file: its solution refused, 0 of the 4 anchors, on the code
before the second fix).

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

### S51 — The live and batch airmass precess J2000 coordinates to the date

**What was wrong.** `sky_geometry.altitude_at` and `horizontal_at` (fast
spherical trigonometry, so a batch of hundreds of frames does not pay astropy's
50 ms per transform) put the J2000 RA/Dec against the date's sidereal time,
without precession: 26 years of it is 0.36° on the sky, and the directions were
up to 0.51° from astropy's over 2000-2035 (0.3° typical in 2026). The live and
batch airmass of every point (CSV `airmass`, AAVSO `AMASS`) comes from
`altitude_at`; the X3 site check and the Plan visibility curves use the same
functions.
**Who was affected.** Every live point with a site set since 0.4.2 (which
introduced `airmass_at`; 0.4.1 live curves took the mount's altitude) and every
batch re-run, a little. On the owner's runs, at the site their frames record:
the RR Lyr target CSVs of 2026-09-25 (0.4.2; 201 rows, altitude 41° down to 12°
at that night's Settings site, which was not where the telescope was: X3) are
reproduced exactly by the old code and change by +0.004 to +0.029; the XX Cyg
curves of 2026-08-29 and 2026-09-07 (0.4.1) hold the mount's airmass and are not
affected, but a batch re-run of them changes by +0.0006 to +0.0008 (altitude
67-69°). After the change the airmass is within 0.0007 of astropy's on every
one of those 286 rows (before: up to 0.028 low). The FITS header `AIRMASS` is
not affected: it is the mount's own altitude (Pickering), not this
computation. The X3 site check's angles move by 0.35° at most on the owner's
sessions (right site: 2.0–3.3° instead of 1.9–3.1°; the wrong site's 88.5°
unchanged). For other users the old airmass can be high or low: over 4 000
random dates (2000-2040), all-sky positions and sites (latitude −65° to +70°)
the change at 10-40° of altitude in 2026 is −0.067 to +0.081 (the science
review, against astropy).
**What changed.** The coordinates are precessed from J2000 to the mean equator
and equinox of the date (IAU 1976: Lieske et al. 1977, the ζ, z, θ angles)
before the sidereal time (`precess_j2000_to_date`). Nutation, aberration and
refraction are still left out: within 0.008° of astropy (no refraction) over
the 341 directions of the test grid.
**How to check.** `tests/core/test_sky_geometry.py::test_sky_geometry_precesses_j2000_to_the_date_s51`
(5 dates from 2000 to 2035, 30 positions, 4 sites, against astropy within
0.05°; 0.51° on the code before the fix).

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

### S47 — The Plan editor never cuts a value silently

**What was wrong.** S7 made a preset load report a filter, exposure or gain it
had to change. Count (1–9999), interval (0–3600 s) and dither (0–999) were
still cut to the editor's range without a note: a count of 12000 ran 9999
frames. **Prepare transit** ignored the notes altogether and reported the count
before the cut: 120 min of baseline at a 1 s cadence on HD 189733 b needs 20978
frames; the editor held 9999 (about 183 min of coverage lost) while the status
said 20978 and `observation.json` declared the whole coverage.
**Who was affected.** Presets with such values; transit plans at a short
cadence over a long coverage.
**What changed.** Every cut is reported ("adjusted: step 1: count 12000 → 9999
(range 1–9999)"). A transit needing more than 9999 frames is not prepared: the
status says so and gives the shortest cadence that fits; the table is left as
it was. The status counts the frames the table really holds and lists any
adjustment. The web UI keeps a typed value and reports it as an issue instead.
**How to check.** `tests/ui/test_sequence_panel_plan.py::test_count_interval_and_dither_clamps_are_reported`
and `::test_a_transit_longer_than_one_step_is_refused` (no note, and a
9999-frame transit, on the code before the fix).

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

### S84 — The noise model is locked while a sequence runs

**What was wrong.** `photometry.noise_model` and `photometry.read_noise_e` (S72,
S73) are read for every frame. A change during a run applied from the next sub: the
SNR the S35, S56, S58 and S69 gates read and the formal errors changed partway
through one curve, with no record in the files (technical review). The web
Settings page shows both keys; the Qt app has no control for them (config file
only, read at start). The camera's e-/ADU sets the same SNR and errors, and the
observer gives it two inputs, also read for every frame (S73's chain): the
`camera.egain_table` (web Settings › Instrument; config file only in Qt) and the
photon-transfer folder `data_paths.camera_calibration_directory` (Settings in both
apps). In a simulator run, a `PATCH` of `camera.egain_table` `{"80": 0.3}`
mid-run was accepted and the next frames carried `EGAIN` 0.3 instead of 0.25
(validation F1; the review measured +15 % on one star's SNR from a file written
mid-run).
**Who was affected.** Nobody in 0.4.2 (no control, the green-plane model did not
exist; its e-/ADU chain did not read the profile or the file first); the web app
before this fix, which is not released; the Qt app through its photon-transfer
folder field.
**What changed.** The four keys join S15's run lock and are refused the same way
(`params.NOISE_MODEL_KEYS`): Qt refuses a noise-model change that arrives during a
sequence (`_on_photometry_setting_changed`, "The noise model is locked while a
sequence runs — change ignored.", nothing written), and its photon-transfer folder
field is unavailable during a sequence with the reason in its tooltip (the Shell
passes the run state, `ConfigurationPage.set_sequence_running`; a change that still
arrives keeps the folder in use and writes nothing); the web server's
`PATCH /api/config` answers `409 run_active` "The noise model and the camera's
e-/ADU are locked while a sequence runs (one curve, one error model)." with the
keys, and writes nothing of the PATCH; the web Settings pages show these keys
unavailable during a run with the server's sentence: Photometry the noise model and
the read noise, with S15's four, Instrument the photon-transfer folder and the
electron gain table. Not covered, as for S15: another program editing
`config.json` during a run (the web server re-reads the file on
`GET /api/config`).
**Known limits (0.5.x).** An edit of the `camera_calibration*.json` file itself
during a run applies from the next frame (the file is read for every frame);
resolving the e-/ADU once per gain at the run's start is deferred. `site.elevation`
(S74's scintillation) is not run-locked.
**How to check.** `tests/ui/test_photometry_window.py::test_the_noise_model_is_locked_during_a_sequence_s84`
(written mid-run before the fix), `tests/ui/test_shell.py::test_shell_three_mode_walkthrough`
(the folder field enabled, and a change applied, during a run before the fix); web
`tests/server/test_sequence.py::test_the_noise_model_is_locked_during_a_run_s84`
(the e-/ADU's keys written mid-run before the fix),
`::test_the_server_locks_the_cores_noise_model_keys_s84` (GUARD: the server's keys
are the core's), `tests/server/test_settings_wave2.py::test_the_settings_page_locks_what_the_server_locks_during_a_run_s15_s84`,
`web/src/lib/settings/runlock.test.ts`.
**Check your old files.** None: no released version could change the noise model
during a run.

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

### S40 — Measuring an object again never overwrites its live curve CSV

**What was wrong.** Outside a run (live preview, Open FITS), a star's curve was
written to `<sessions>/targets/<object>_<star>.csv`, rewritten after each point
from the curve in memory. That curve starts empty after an object change or a
restart, so measuring the same object again (A → B → A, the next evening)
replaced the file's earlier points with the new ones.
**Who was affected.** Live photometry outside a sequence, and Open FITS replays,
of an object measured more than once.
**What changed.** Each live curve outside a run gets its own file, named after
the time it started: `<object>_<YYYYMMDDTHHMMSSZ>_<star>.csv` (`-2`, `-3`… on
the time when two start in the same second). A new curve (object change,
restart, role change, a batch re-run folded in) starts a new file. Review still
finds the object's set and the star (S10). A run's CSVs keep their names.
**How to check.** `tests/workers/test_acquisition_engine.py::test_measuring_an_object_again_never_overwrites_its_preview_csv`
(on the code before the fix, three points, an object change and one more
point left one file holding that last point only).

### S44 — A run measures its Light subs only

**What was wrong.** `_on_seq_frame_saved` measured every saved sub of a run,
Dark, Flat and Bias included, as soon as the field had a solution. Each
calibration sub wrote a junk row for every star, and its measurement moved the
aperture tracker, so the Light points after it were measured elsewhere too. On
copies of XX Cyg 2026-09-07 frames replayed through a plan of Light IR ×2,
Dark, Flat LP, Bias, Light LP ×2 and Light IR, the run wrote 8 target points for
5 Light subs, and on those 5 the target read 12.1958 where the web server
(which measures Light subs only) read 10.9492, with comparisons up to 2.2 mag
apart.
**Who was affected.** Runs whose plan mixed calibration and Light steps with a
target set and an identified field. None of the owner's runs.
**What changed.** Only a sub whose `IMAGETYP` is `Light Frame` is measured.
With this rule the same replay gives the web server's points exactly (40
points, 760 values, 0 differences; the science review's run).
**How to check.** `tests/workers/test_acquisition_engine.py::test_a_sequence_measures_only_its_light_subs`
(all five subs of a Light, Dark, Flat, Bias, Light run measured on the code
before the fix).

### S45 — A finished run's folder receives no more points

**What was wrong.** The run's folder (`_active_run_root`) was kept after the
sequence ended, until another run or an opened frame. A live point measured
afterwards (live preview of the same object) was appended to the run's CSVs,
and the run's `photometry_quality.json` was rewritten with it.
**Who was affected.** Anyone who kept live preview running with a target set
after a sequence. One of the owner's runs (`20260925T195307Z_RR_Lyr`) has 2
such rows per star.
**What changed.** The run's folder is closed when the run ends (every sub's
point is measured before that). Later points go to the live curve's own CSV
(S40); the flight recorder moves out of the run's `diagnostics/` folder and
the series keeps its aperture. The web server already behaved this way.
**How to check.** `tests/workers/test_acquisition_engine.py::test_a_finished_run_keeps_its_folder_closed`
(the run's folder still active after the run on the code before the fix).

### S46 — Identifying the field keeps the check star

**What was wrong.** When the field is identified, the comparisons are filled
from the VSP proposal. The proposal can hold the check star (a VSP star too);
only the existing comparisons were compared with it, so `set_role` replaced the
check (same AUID) with a comparison. Seen on the web server, which ports the
same code: a check star assigned on RR Lyr lost its role at the first solve.
**Who was affected.** Anyone with a check star and fewer calibrated
comparisons than `photometry.auto_comparisons`. The owner's runs have no check
star.
**What changed.** The target and the check star are never offered as
comparisons (same AUID, or within 1″). The proposal is asked for that many more
stars, so the number of comparisons picked is unchanged. The web server has
the same change.
**How to check.** `tests/workers/test_acquisition_engine.py::test_identifying_the_field_keeps_the_check_star`
(no check star left on the code before the fix).

### S48 — A frame whose anchors show no star where the tracker puts them gets no point

**What was wrong.** After a field jump larger than the tracker's search
radius (15 green px), a tracker window could centroid a neighbour or noise:
the tracker reported that anchor and moved every aperture by its offset. S35
only fires when no anchor at all is found, so such a frame was measured off
its stars, with no flag, and the next frames could follow the wrong star. The
batch re-run has had the independent check since S43; the live and sequence
paths had none.
**Who was affected.** Live and sequence photometry after a jump or a slew
larger than the search radius when a window still found something, and frames
on which clouds hid most anchors. On the owner's runs as shot (a solve before
every sub) S48 changes no point: replaying the Qt sequence path on the 257
frames of the tracker study (8 runs, Argos's live solves) gives 254 frames
with a target point before and after. With one solve for a whole run (a run
whose re-solves fail), the same replay gives 188 frames with a target point
before, 83 of them more than 2 px from the star (RR Lyr 2026-09-25: 67 frames
at 21-395 px), and 114 after: the 74 refused frames are those 67 and 7 frames
between them without a truth solve. No frame within 2 px of its star is
refused. The 16 XX Cyg points 2.1-4.4 px off (the tracker's lag in field
rotation) keep their point: their anchors still show a star.
**What changed.** After the tracker update, at least ceil(n/2) of the
tracker's n anchors must show a star (aperture SNR ≥ 5, S35's threshold) where
the tracked solution puts them (the batch's S43 rule, `anchors_seen`).
Otherwise the frame gets no point: a WARN "Photometry skipped: fewer than half
the anchor stars show a star where the solution places them — the field moved
since the solve, or clouds. Re-solving.", a `frame_skipped` event
(`reason: lock_lost`) in the flight recorder, and a solve is due at once
(`AstrometryController.make_due`): in a run the sub in hand is solved now, its
solution serving the next sub; outside a run the next frame is solved (a live
point follows each solve). S35's skipped frames make the solve due the same
way. On a replay of RR Lyr frames 40-79 through frame 40's solve alone, frame
52 (the 22.8 px jump) was measured 22.6 px from the star and frame 53 skipped;
now frame 52 is refused and, re-solved, frame 53 is measured 0.65 px from it.
S48 does not catch a wrong plate solution: a new solution rebuilds the tracker
from the stars seen where it puts them, so they pass (S50 refuses the observed
one by its scale). The web server's port has the same change and gives the
same points on these frames.
**How to check.** `tests/workers/test_acquisition_engine.py::test_a_frame_whose_anchors_show_no_star_gets_no_point_s48`
(a point written on the code before the fix),
`::test_a_run_re_solves_the_frame_whose_lock_was_lost_s48`,
`::test_the_lock_check_costs_no_good_frame_s48` and
`tests/workers/test_astrometry_controller.py::test_a_lost_lock_makes_a_solve_due_at_once_s48`.

### S49 — One live curve per star and filter

**What was wrong.** A star's live curve was keyed by the star alone. A run
alternating filters (V and B steps, or IR and LP) put both bands' points in one
curve: one series on the plot, one CSV, one systematic floor (`sigma_syst`
from the scatter of both bands together) and one leave-one-out vetting of each
comparison, which a band difference makes look unstable. A batch re-run of
such a folder did the same.
**Who was affected.** Runs and live previews through two filters. None of the
owner's: every run used one filter (IR, or LP for single frames), and so did
their live-preview curves.
**What changed.** One curve per (star, filter). The filter is the frame's: a
sub's read-back `FILTER`, a live frame's settled wheel slot (else the Camera
form's filter), an opened or re-run file's `FILTER` card; spelled as frame
file names spell it (`filter_token`: `ir`, `lp`, `v`, `clear` for none). It sits
in the CSV name, as the start time does (S40): a run's
`photometry/{role}_{object}_{filter}_{star}.csv`, a preview curve's
`<object>_<start>_{filter}_{star}.csv`, a batch re-run's
`{role}_{object}_{filter}_{star}.csv`. The comparisons are vetted per filter:
the run's first filter in `photometry_quality.json`, each other one in
`photometry_quality_<filter>.json`; a re-run's check-star RMS is per filter.
With two filters every series label names its filter ("RR Lyr [v]"). The
sequence editor warns when the enabled Light steps use two filters: "Light
steps use 2 filters (V and B): each star gets one light curve and one CSV per
filter." A one-filter run's files keep their contents byte for byte; only the
names gain the filter (XX Cyg 2026-09-07 `040723Z`, no site set: its 9 sequence
CSVs and 9 batch CSVs, 216 rows each, identical; with a site, S51 changes their
`airmass` column only). Review reads both names: a new name's curve is the
star's in that filter; an old name's is the star's, as before. The AAVSO export
refuses curves of two filters (S53): export one filter's CSV from Analyze.
**How to check.** `tests/workers/test_acquisition_engine.py::test_each_filter_has_its_own_curve_csv_and_vetting_s49`
(one curve for both filters on the code before the fix),
`tests/workers/test_photometry_batch_worker.py::test_a_re_run_keeps_one_curve_per_star_and_filter_s49`,
`tests/core/test_session_review.py::test_review_keeps_one_curve_per_star_and_filter_s49`
and `tests/ui/test_sequence_panel_plan.py::test_light_steps_through_two_filters_warn_one_curve_per_filter_s49`.

### S52 — A set change between two solves never re-anchors the tracker on a stale solution

**What was wrong.** A target-set change (the VSP comparisons auto-selected when
the catalogue answers after a run's first solve, a role change, Remove,
Recommend, a new comparison count) dropped the tracker, and the next sub rebuilt
it on the last raw solve although the field had drifted since. Only the stars
that happened to show at the stale positions qualified as anchors: on the
owner's RR Lyr field, one neighbour 30 px from a comparison. The S48 check
needs ceil(1/2) = 1 anchor, and the anchor that moved the solution is always
"seen", so it passed; every aperture then sat on blank sky until the next solve,
with no flag, no re-solve due, and the points in the CSV and the AAVSO export.
**Who was affected.** Sequence runs in which the set changed between two solves
(live points follow each solve and are not affected). The science review's
replay of RR Lyr 2026-09-25 frames 0-79 (one solve every 20 s) found five
unflagged target points on frames 4, 7, 8, 10 and 11 (SNR 0-2.6, 30-37 px from
an independent ASTAP solve), identical in Qt and the server; without the set
change, none.
**What changed.** A set change freezes the solution as tracked so far (the solve
with the tracker's shift and rotation) and the next tracker is built on it until
the next solve; a slew or a new solve starts from the raw solution as before. In
a run a set change also makes the next sub's solve due at once. The web
server's port (`PhotometryService.on_targets_changed`) has the same change. With
fewer than 3 anchors the S48 check is met by the anchor that moved the solution:
S56 (owner decisions of 2026-11-14 and 2026-11-15) flags such points away from a
fresh solution.
**How to check.** `tests/workers/test_acquisition_engine.py::test_a_set_change_never_re_anchors_on_a_stale_solution_s52`
(the target 26 px off and no re-solve due on the code before the fix).

### S56 — A lock on fewer than 3 anchors is verified only near a fresh solution

**What was wrong.** The S48 check needs ceil(n/2) of the tracker's n anchors to
show a star where the tracked solution puts them. With n = 1 or 2 that is one
anchor, and the anchor whose centroid moved the solution is seen by
construction: a neighbour taken for a comparison after a jump, or a star at a
stale position after a set change (S52), passed, and the frame was measured off
its stars with no flag. The anchors themselves were chosen on the measured sub,
through the solution of an earlier one: after a jump only the stars that
happened to show at the stale positions qualified. Real RR Lyr 2026-09-25 subs
moved 500 green px between two subs without a slew (S54's replay, subs 44-48
of 41-48): the tracker rebuilt on sub 44 through sub 43's solution found a
field star at one of the 6 comparisons' stale positions and kept it as its only
anchor; it moved the apertures 2.16 px and the target was measured 496 px from
the star, flagged only because 2.16 px is 0.16 px over the 2 px threshold below.
**Who was affected.** Runs whose comparisons give fewer than 3 anchors (SNR 10,
unsaturated, at most 6), and any run after a jump between two solves. Replaying
the Qt sequence path on the 257 frames of the tracker study (8 runs, Argos's
live solves, a solve landing before every sub; the solve before the run counts
as one of an older frame): 3 of 255 target points (and every star's point of
those frames) are now flagged, all on XX Cyg 2026-08-29: `050148Z` frames 0 and
13 and `052943Z` frame 0. Those two runs have 1 or 2 anchors on 25 of their 26
frames (only two of `050148Z`'s five comparisons reach SNR 10 in its 15 s subs,
the others 4.3, 1.6 and 0); the other 22 of these are measured through the
previous sub's solution with the tracker moving the apertures 0.26-1.57 px
from it, and their target points lie 0.24-1.83 px from the star (an independent
solve of each frame). Frame 13 is flagged at 2.66 px of tracker motion: its
target point is 3.38 px off the star. No point is lost and the six other runs
do not change (3 to 6 anchors); RR Lyr frames 52 and 175 (the 22.8 px jump and
the blank-sky sub) stay skipped, by the S48 check now (their 5-6 anchors are
chosen on the solved sub) rather than by S35. With one solve per run and
re-solves only when due, the same 3 points are flagged and 35 solves made (14
flagged, 24 solves and 13 WARN episodes when a sub verified through the
previous sub's solution made no solve due: every other sub of these two runs
was then two subs from a solution). The S52 case: replaying RR Lyr 2026-09-25
frames 0-39 with the VSP comparison `000-BCG-653` added after frame 1, the next
solves failing (frames 1-11) and the tracker rebuilt on the raw solve (as before
S52), frames 4, 7, 8, 10 and 11 were measured through 1 anchor, 29.5-35.8 px
from the star, on a solution 3-10 subs old (unflagged before S56, flagged by
its first rule, frames 2 and 3 skipped); the rebuilt tracker now takes its 6
anchors on frame 0, where the solution is exact, and follows the field 6.5-62
px from it: every target point within 1.12 px of the star, none flagged or
skipped. With S52, that replay has no frame below 3 anchors and no change.
**What changed.** After the S48 check, a tracker of 1 or 2 anchors leaves the
lock unverified unless the frame is measured through a solution of this sub or
the previous one (the controller keeps the frame each solution describes,
`AstrometryController.solved_raw`) and the tracker moved no aperture of the set
10 px or more from where that solution puts it: the largest distance, over the
set's stars, between their position through the raw solution and through the
tracked one (a set-change rebase included). It was the tracker's own outlier
floor (`RESIDUAL_FLOOR_PX`, 2 px) until 2026-11-16 (the amendment below). A
verified frame makes no re-solve due. An unverified frame keeps
its points, each flagged `suspect` (the CSV's `suspect` column: kept, left out
of the AAVSO export, as a batch re-run flags a frame measured without the
field, S43), and a solve is due at once (in a run the sub in hand is solved now,
as after S48). A WARN once per episode ("Photometry: only 2 anchor stars steer
the apertures — the lock cannot be verified; points are flagged suspect while
fewer than 3 anchor stars steer the apertures (except within 2 px of a solution
of this sub or the previous one). Re-solving."): a verified frame, a slew or
invalidation, or a set change ends the episode, a solve that lands does not (on
a field that never reaches 3 anchors it was logged on every sub). A
`lock_unverified` event per flagged frame in the flight recorder. The live plot
does not draw suspect points apart (as before); the AAVSO export's summary now
says "suspect (cosmic ray / hot pixel, or no verified lock)". Two more rules
(owner decisions of 2026-11-15, second set): the tracker's anchors are chosen on
the frame the current solution was solved on, through that solution, where it is
exact (`AcquisitionEngine._anchor_frame`; the measured frame only when that frame
is unknown or of another geometry), and the S48 and S56 checks count those on
the measured sub: on the 500 px jump 1 of the 6 shows a star, the lock is lost,
the sub gets no point and a re-solve is due (subs 45 and 46 are skipped the same
way while S54 refuses their solutions, 2 of the 6 anchors seen where they place
them, and accepts the third as a re-pointing; subs 47 and 48, 2 anchors inside
the moved frame and 4.28 and 3.68 px of tracker motion on a field drifting 4.3
px per sub, stay flagged). And in a run a sub of 1 or 2 anchors verified through
the previous sub's solution makes its own solve due at once (the sub in hand is
solved, as after S48), so the next sub is measured through a solution of the
previous one: one solve per sub on such a field, what the owner's runs already
do. This needs the sub's solve to land before the next sub is measured: with
solves slower than one sub interval such subs stay flagged and every other sub
is solved (no loop or stall: at most one solve starts per sub; the review's
replay of `050148Z` with each solve landing one sub late flagged all 22 subs,
before and after this rule). Outside a run a live point follows each solve, of the newest frame or the one
before: nothing more is made due. `050148Z` keeps its 2 anchors on 20 of its 22
subs and every verified frame; subs 9 and 11 have 1 (its first comparison has
SNR 9.9 on the solved subs 8 and 10, under the anchors' SNR 10, and 12.8 and
13.5 on subs 9 and 11), still verified at 0.26 and 0.48 px of tracker motion,
their target points 1.01 and 0.57 px from the star (0.82 and 0.70 with 2
anchors). Elsewhere a few frames gain or lose an anchor at 3 or more
(`052943Z`, `053540Z`, 2026-09-07 `040723Z`, `045626Z`), with no point or flag
changed. The batch re-run (S58) needs neither rule: it builds a tracker after a
re-solve on the frame it has just solved, and re-solves an unverified frame
before measuring it, so a frame two frames from a solution costs a solve, not a
flag. Since the anchors are chosen on the solved frame, a run's first sub after an
opened FITS takes the file's anchors: they never check the camera's solution
(S59). The web server's port has the same changes and gives the same points as
the fixed Qt in one process, with no difference (`050148Z` with a solve before
every sub and with one solve per run: 118 points, 12 suspect each; RR Lyr subs
0-39 above, with and without S52: 318 points, none suspect; the 500 px jump: 27
points, 6 suspect, the same skips and S54 refusals). The batch re-run gets the
fresh-solution rule: S58.
**Amended on 2026-11-16 (the owner's decision, S69's open item 1): 10 px.** The
2 px threshold was tuned on the lagging tracker; the converged one (S69) sees the
field move 4.2-7.5 px between subs on XX Cyg 2026-09-07 `040723Z` and up to 5.1 px
on 2026-08-29 `050148Z` (each frame's own solve), and a neighbour locked after a
jump or a stale rebuild moved the apertures 22-36 px. 10 px lies between. Replays
of the Qt sequence path (Argos's own solves; a solve every 20 s, or one per run;
before = the release at `3e48d78`, after = 10 px with S77-S80 and the noise
role's S72-S76): `050148Z` frames 13-16 (2.5-5.0 px of tracker motion, target
points 0.06-0.14 px from the star) and `053540Z` frames 1-3 (2.1-2.8 px, 0.03-0.18
px) are verified instead of flagged; with one solve per run `050148Z` makes 16
solves instead of 23 and flags frames 0 and 19 (0.10 px from the star, two subs
from its solution) instead of 0 and 13-16. The cases S56 catches: the 500 px jump
(RR Lyr subs 44-48 moved −500 px) and the RR Lyr set change (frames 0-39,
000-BCG-653 added, solves 1-11 failing, with and without S52) give the same points,
skips and flags as before (subs 44-46 skipped by S48: 1-2 of 6 anchors seen; 47
and 48 now verified, 4.86 and 4.14 px of motion, their target points 0.20 and
0.14 px from the star). The threshold alone would not catch every neighbour lock:
with the anchors chosen on the measured sub (before the second amendment) the
500 px jump's sub 44 is a 1-anchor lock that moves the apertures 7.02 px, the target
494 px off, verified at 10 px (flagged only by S71's dominant-comparison rule);
the anchors chosen on the solved frame (second amendment) are what refuses it:
1 of 6 seen, no point (`s56_10px_cases.json`). The anchors keep SNR ≥ 10 with the
true SNR of S72-S75 (the owner, 2026-11-16): fewer anchors on the 15 s XX Cyg subs,
more verifying solves, `050148Z` frame 19 flagged with one solve per run (0.10 px
from its star), no wrong point kept. Gate counts on every study run: S69's *The
tracking gates with the new SNR*.
**How to check.** `tests/workers/test_acquisition_engine.py::test_a_lock_on_fewer_than_three_anchors_flags_its_points_s56`
(the points unflagged on the code before the fix),
`::test_a_run_re_solves_the_sub_whose_lock_is_unverified_s56` (no re-solve
before the fix; a lock on 4 anchors is neither flagged nor re-solved),
`::test_a_few_anchor_lock_near_a_fresh_solution_is_verified_s56` (this sub's or
the previous sub's solution, 1 or 6 px of tracker motion: verified, no re-solve;
two subs after it, or 12 px: flagged and re-solved; every such point flagged on
the code before the 2026-11-15 amendment, the 6 px one before the 2026-11-16
one),
`tests/workers/test_photometry_batch_worker.py::test_a_field_moving_6_px_per_frame_is_verified_on_the_previous_solution_s56`
(S58: 6 solves in 6 frames at 2 px, 3 at 10 px), web
`tests/server/test_photometry.py::test_a_few_anchor_lock_near_a_fresh_solution_is_verified_s56`,
`::test_the_unverified_lock_warns_once_per_episode_s56` (two WARN lines across a
landed solve before the amendment),
`::test_the_lock_check_uses_anchors_chosen_on_the_solved_frame_s56` (a jump: 1
anchor, a field star 1.1 px from a comparison's solved spot, and an unflagged
point off the star on the code before the second amendment; now 4 anchors, 1
seen, no point, a re-solve due) and
`::test_a_run_solves_the_sub_verified_through_the_previous_solution_s56` (no solve
due before the second amendment, and with one solve per run every other sub
flagged; outside a run nothing is due).
**Check your old files.** See *Check your old files* (S56).

### S57 — Every vetting file names its filter

**What was wrong.** Since S49 a run's comparisons are vetted per filter:
`photometry_quality.json` for the run's first filter, `photometry_quality_<filter>.json`
for each other one. The first file did not say which filter it vets.
**Who was affected.** A reader of a two-filter run's vetting file. No data
changes.
**What changed.** Every vetting file gets an additive last key `"filter"`, the
S49 token (`ir`, `lp`, `clear`): `save_comparison_quality_report(path, report,
filter_token=)`. Qt writes these files from the live and sequence path only, in
a run's folder (a batch re-run writes none). Readers ignore unknown keys: Review
(`load_session`) reads the file as before and keeps the key; the web server's
session list (`has_quality`) too. XX Cyg 2026-09-07 `040723Z` (one filter)
replayed through the Qt sequence path: its 9 CSVs byte for byte as before, its
`photometry_quality.json` as before but for `generated_utc` and the added
`"filter": "ir"`. The web server writes the same key.
**How to check.** `tests/workers/test_acquisition_engine.py::test_every_vetting_file_names_its_filter_s57`
(no key on the code before the fix),
`tests/core/test_photometry_quality.py::test_the_vetting_file_names_its_filter_and_is_otherwise_unchanged_s57`
and `tests/core/test_session_review.py::test_review_reads_a_vetting_file_that_names_its_filter_s57`.

### S71 — The ensemble zero point weighs each comparison by its error

**What was wrong.** The zero point was the plain mean of catalogue − instrumental
magnitude over the comparisons (after a median ± max(2.5 × 1.4826 MAD, 10 mmag)
clip), and its error their scatter / √n: a comparison at SNR 1 counted as much
as one at SNR 100. XX Cyg 2026-08-29 `050148Z` has one comparison at SNR 21
(000-BJV-170) and three at SNR 0.6-4 (V 12.9-14.2): its check star 000-BJV-171
came out +0.28 ± 0.08 mag from its VSP V on the recorder values (point-to-point
scatter 0.43 mag), +0.155 ± 0.079 in a re-run.
**Who was affected.** Every differential magnitude, live and re-run; by tenths
of a magnitude when faint comparisons sat beside a bright one, by a few mmag for
an ensemble of similar stars.
**What changed.** Each comparison weighs 1 / (err² + (10 mmag)²), its photon
error with a floor so that one bright star cannot take all the weight
(`ensemble_zero_point`). The clip drops a comparison whose |d − median| exceeds
2.5 × sqrt(err² + floor²), about the *weighted* median: with the plain median
the clip sat among the faint comparisons and dropped the bright one on 13 of
`050148Z`'s 22 frames (check +0.26 ± 0.10). The zero point's error,
max(sqrt(1/Σw), weighted rms / √n), is in `formal_mag_err`, hence in `mag_err`
and the run's `sigma_syst`. Review warns `faint_comparisons` when the
comparisons' median SNR is below 10 (RR Lyr 2026-09-25: 101; XX Cyg 2026-09-07
`040723Z`: 20; `050148Z`: 1.7, warned). Re-runs of the study sessions through
the batch worker, S71 alone (check star − VSP V, mean ± its standard error):

| Run | Before | After |
|---|---|---|
| XX Cyg 08-29 `050148Z`, check 000-BJV-171 | +0.155 ± 0.079 | +0.055 ± 0.027 (χ²ᵣ 1.09 → 0.58) |
| Same, recorder values | +0.28 ± 0.08 | +0.059 ± 0.028; zero-point error 0.054 and 0.088 on frames 15 and 18 |
| XX Cyg 09-07 `040723Z`, check 000-BJV-169 | −0.061 ± 0.017 | −0.036 ± 0.013 |
| RR Lyr, 2 comparisons, check 000-BCG-523 | +0.0174 ± 0.0016 | +0.0166 ± 0.0016 |
| RR Lyr, 2 comparisons − Siril green 2 comparisons (median, robust σ) | +0.0020, 0.0099 | +0.0004, 0.0099 |
| RR Lyr, 6 comparisons − Siril green 2 comparisons | −0.0112, 0.0173 | −0.0083, 0.0157 |

The check stars' remaining offsets are within their VSP errors (000-BJV-171
± 0.030 and 000-BJV-170 ± 0.052, the comparison that carries 97-99 % of the
weight; 000-BJV-169 ± 0.051; 000-BCG-523 ± 0.10). RR Lyr's 000-BCG-953 (B−V
1.67, 0.16 mag off) is clipped on 176 of the 193 frames that measured it
(170 before); on the other 17 the comparisons disagree by 0.05-0.1 mag, far
beyond their photon errors, every one would be clipped, and the clip keeps
them all (as the old rule did on 23 frames). SNR is unchanged, so are the
re-solves, verify solves, anchors and flags of the four re-runs.
**Confirmed by the owner on 2026-11-16.** The clip is centred on the weighted
median, not on the plain median of the decision text (with the plain median the
clip dropped the bright comparison on 13 of `050148Z`'s 22 frames: check +0.26 ±
0.10, independent re-implementation +0.262 ± 0.099; `web/spec/decisions-s66-s72-independent-checks.md`
§10), and the flag below needs at least two other comparisons: both deviations are
accepted.
**A comparison holding more than half the weight (technical review, the owner's
decision).** Centred on the weighted median, the clip never drops such a
comparison: a bright one that is variable, blended or strongly coloured set the
zero point alone (0.30 mag off beside two good faint ones: zero point +0.25,
nothing clipped, nothing said). After the clip, when the heaviest comparison
holds more than half the weight and two others at least remain, its d is
compared with the weighted mean of the others; beyond 2.5 combined σ the point
is flagged `suspect` (left out of the AAVSO export) with the note "the
comparison holding N % of the weight disagrees with the others (z sigma)". The
zero point is kept as computed: the plain median would drop the bright star on
the frames where the faint ones are wrong (above). With one other comparison
there is no majority, only two stars that disagree, which the zero-point error
already carries (RR Lyr's 2-comparison set would flag 27 of 195 frames). On the
recorder values: XX Cyg 2026-08-29 frame 5 is flagged (000-BJV-170 holds 92 %
of the weight and disagrees by 6.2σ), 1 of 22 frames; no frame of `040723Z` or
RR Lyr; the check star over the other 21 frames +0.052 ± 0.029 (1.8σ on its
standard error); zero-point errors on frames 15 and 18 and 000-BCG-953's clip
unchanged. Limit: such a frame is flagged, not corrected (its point leaves the
report). Qt's Review now warns about faint comparisons too (the comparisons'
median SNR in the flight recorder below 10, from `load_session_curves`; the web
server maps the same value).
**With S69 and S70 (final re-runs, ASTAP, that night's Settings site).** Check
000-BJV-171 +0.051 ± 0.023 (1.35σ with VSP's ±0.030 on its V, 2.2σ on its
standard error alone), 000-BJV-169 −0.074 ± 0.009 (1.4σ with VSP's ±0.051),
000-BCG-523 +0.0155 ± 0.0017 (0.15σ with VSP's ±0.10); RR Lyr 2 comparisons −
Siril green 2 comparisons +0.0013, robust σ 0.0096 (χ²ᵣ 0.81 on the formal
errors); 6 comparisons −0.0076, 0.0153.
**How to check.** `tests/core/test_photometry_core.py::test_a_heavy_comparison_its_ensemble_contradicts_flags_the_point_s71`
(no flag on the code before the fix), `::test_the_xx_cyg_frames_keep_their_bright_comparison_unflagged_s71`,
`tests/core/test_session_old_file_rules.py::test_review_warns_about_faint_comparisons_s71`,
`tests/core/test_photometry_core.py::test_zero_point_follows_the_comparisons_errors_s71`
(the plain mean puts frames 15 and 18's zero points 0.029 and 0.052 mag from
the bright comparison's),
`::test_one_bright_comparison_cannot_take_all_the_weight_s71`,
`::test_reddish_comparison_still_clipped_s71`; web
`tests/server/test_review_sessions.py::test_s71_a_faint_ensemble_is_named_in_readiness`.

### S72 — The noise model is the green plane's, above the black level

**Status: the default since S73 (`photometry.noise_model`: `green_plane`; `pixel`,
the 0.4.x formula, stays selectable for comparison).** It was off while the frames'
`EGAIN` made its own test fail (owner's decision of 2026-11-16: S73's measured
e-/ADU first, then this model on, then every gate checked again).
**What was wrong.** The photometry measures the (G1+G2)/2 plane, whose values
hold two pixels' electrons, but `measure_aperture` used one raw pixel's e-/ADU,
one pixel's read noise, and counted the whole sky level, black level included,
as photons. Against the green-plane noise measured on the frames (20.5 ADU RR
Lyr, 29.7 XX Cyg 09-07, 31.2 XX Cyg 08-29), the model said 38.4, 28.2 and 28.5.
**What changed.** Effective gain 2 × the frame's e-/ADU, read noise rn/√2 ADU per
green pixel, and the telescope profile's black level (`black_level_adu`, S30 Pro
1024 ADU) subtracted from the sky before the Poisson term (`aperture.sky_sigma_adu`),
in every aperture the photometry parameters drive: points, anchors, lock checks,
comparison quality (`PhotometryParams.black_adu`, `plane_pixels`); with it, S74's
scintillation and S75's sky-estimate term. The read noise is the profile's,
measured with the e-/ADU at that gain (S73: 2.6 e- at gain 80, ADC quantisation
included), else `photometry.read_noise_e`. `pixel` keeps the 0.4.x formula with the
camera's e-/ADU: it counts the black level as sky photons, 2.5-3.5 times the real
sky noise at the measured e-/ADU; it is not the default and serves comparison only.
**Its test.** Model sky sigma / sky sigma measured in the 8-12 px annuli of every set
star (3-sigma-clipped), on the first, middle and last light of each session:
RR Lyr 2026-09-25 0.97, 1.03, 0.96; XX Cyg 2026-09-07 0.96, 0.98, 0.99; XX Cyg
2026-08-29 0.96, 0.97, 1.03 (with the frames' `EGAIN`: 0.48, 0.34 and 0.34). With
S73's amendment (a scaled gain takes the measured 2.6 e- read noise), every gain-80
and gain-100 light of the study runs lies at 0.96-1.05 (31 frames; gain 100:
0.965-1.006); the single gain-65 light (`034413Z`, 5.9 s, sky 56 ADU above black)
at 0.89 (0.79 with the Settings 1.5 e-): outside the 10 %, one frame where read
noise dominates and no pair measures the gain (fixer `sky_sigma.json`). With 2.6 e-
the gain-100 runs' comparisons' median SNR moves 24.0 → 23.8 (`045156Z`) and
6.5 → 6.4 (`045626Z`): no gate changes.
**The gates, checked again** (Qt batch re-runs of every study run that has a target
set, with ASTAP and the night's Settings site; before: the 0.4.x model with each
frame's `EGAIN`; after: S72-S75 with S73's e-/ADU; the tracking changes of S56 and
S80 left out):

| Run | S43 re-solves | S58 verify solves (unverified) | S69 off-centre / rotation solves | S67 no detection | Anchors, median (min) | Target SNR | Comparisons' median SNR |
|---|---|---|---|---|---|---|---|
| RR Lyr 09-25 `200453Z`, 6 comparisons | 2 → 2 | 0 → 0 (0) | 0 / 0 → 0 / 0 | 0 → 0 | 6 (3) → 6 (3) | 125 → 133 | 101 → 112 |
| same, 2 comparisons + check | 2 → 2 | 0 → 0 (0) | 0 / 0 → 0 / 0 | 0 → 0 | 3 (3) → 3 (3) | 125 → 133 | 110 → 119 |
| RR Lyr 09-25 `195307Z` | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 | 3 (3) → 3 (3) | 149 → 153 | 122 → 131 |
| XX Cyg 09-07 `040723Z` | 0 → 0 | 0 → 1 (0) | 0 / 7 → 0 / 7 | 1 → 1 | 5 (4) → 4 (2) | 6.3 → 4.8 | 20.8 → 15.7 |
| XX Cyg 09-07 `044527Z` (60 s) | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 | 6 (6) → 6 (6) | 17.7 → 9.2 | 50.8 → 26.5 |
| XX Cyg 09-07 `045156Z` (gain 100) | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 | 6 (6) → 6 (6) | 15.0 → 7.0 | 51 → 24 |
| XX Cyg 09-07 `045626Z` (gain 100) | 0 → 0; 1 frame unanchored | 0 → 0 | 0 → 1 | 1 → 1 | 6 (5) → 4 (4) | 11.8 → 4.8 | 14.6 → 6.3 (warned) |
| XX Cyg 08-29 `050148Z` | 0 → 0 | 13 → 7 (0) | 0 / 0 → 0 / 2 | 0 → 0 | 2 (1) → 2 (1) | 8.3 → 6.2 | 1.8 → 1.4 (warned) |
| XX Cyg 08-29 `052943Z` | 0 → 0 | 2 → 2 (0) | 0 → 1 | 0 → 0 | 2.5 (2) → 1.5 (1) | 6.5 → 4.7 | 5.4 → 4.1 (warned) |
| XX Cyg 08-29 `053540Z` | 0 → 0 | 4 → 3 (0) | 0 → 1 | 0 → 0 | 2 (2) → 1.5 (1) | 6.2 → 4.7 | 3.2 → 2.1 (warned) |

No skipped frame; no flagged target point gained or lost on any run; the same 2
RR Lyr field jumps re-solved (frames 52 and 175); the same `040723Z` frame below
SNR 3. The gates keep their physical
meaning; what changed is the SNR they read, now the frames' own: the old SNR was
1.3× too high on the 0.4.1 frames (`EGAIN` 1.723: XX Cyg) and about right on the
0.4.2 ones (0.8: RR Lyr), so "SNR ≥ 10" meant about 7.6 on XX Cyg and 10.6 on
RR Lyr. Fewer faint XX Cyg comparisons now steer the tracker; the S69 test then
finds 000-BJV-172 1.1 px (`052943Z` frame 4) and 1.6 px (`053540Z` frame 2) off its
aperture, at SNR 6.0 and 5.4, left out of those frames' ensembles. `045626Z`'s
third sub (60 s, its zero point 0.8-1.2 mag below the first's: clouds) has its anchors
below SNR 5: the field is lost and its points are flagged (they were measured).
`045626Z`'s comparisons (median SNR 6.3) are now warned `faint_comparisons`.
With the 0.4.x formula and S73's e-/ADU (`pixel`) the SNRs halve and the gates trip
(`040723Z`: 24 verify solves, 20 frames without detection): not to be used for
measurements.
**How to check.** `tests/core/test_photometry_core.py::test_the_model_sky_sigma_is_the_measured_one_s72_s73`
(the three sessions' measured sigma; 0.48-0.34 of it with the frames' `EGAIN`
before the fix), `::test_noise_model_is_the_green_planes_s72` (a synthetic
(G1+G2)/2 plane), `::test_black_level_comes_from_the_profile_s72` (the default);
web `tests/server/test_photometry.py::test_the_pilot_measures_comparisons_with_the_noise_model_s72`
(the server's pilot passed neither black level nor plane pixels),
`tests/server/test_rerun.py::test_server_port_writes_the_qt_workers_bytes[noise_model_s72_s73_s74]`.

### S73 — The e-/ADU at gain 80 is the camera's measured one

**What was wrong.** Frames of the same S30 Pro at gain 80 carry `EGAIN` 0.8
(0.4.2: the driver) or 1.723 (0.4.1: the IMX585 reference curve), and the
photometry used that value (S41, S42, S70). The camera's photon transfer gives
0.228: Poisson errors of stars were 1.9× (0.8) to 2.7× (1.723) too small, and with
S72 the sky noise 2-3× too small.
**The measurement.** Photon transfer of the owner's frames (no ARGOS code): for
each pair of consecutive lights of a session, raw G1 and G2 pixels separately,
stars masked, 32 × 32 px tiles: level and half the clipped variance of the
difference (clipped std, not the MAD: the raw data are 12-bit values × 16, and a
MAD is quantised). Sessions of one light: the variance of G1 − G2 in each 2 × 2
cell, which agrees with the pairs within −2 % to +5 % on the sessions that have
both. One line, variance = (level − black) / g + R², over the 14 gain-80 sessions
of three nights (sky 1099-1940 ADU, 10-60 s, 18-26 °C):
g = 0.228 e-/ADU, bootstrap over sessions ± 0.005 (16-84 %: 0.227-0.238), every
session within 4.2 % of the line in variance (rms 2.1 %). Per night, one black level
and read noise for all three: 0.232 ± 0.005, 0.230 ± 0.005, 0.231 ± 0.006 (χ² 0.11
for 2 degrees of freedom). The bootstrap is skewed: 0.228 sits at the low edge of
its own 16-84 % interval (+0.010 / −0.001) and all three nights lie above it, so the
central value may be nearer 0.231 (a 1.3 % change of the e-/ADU, 0.7 % of σ); an
independent photon transfer of 115 pairs gives 0.2253 (16-84 %: 0.2239-0.2278), the
nights 0.228, 0.221, 0.223, a 3 % spread equal to the drift inside one session as the
sky and temperature change (science review, `ptc_*.txt`): 0.228 ± 0.005 stays the
stated value, its interval asymmetric. The spread of the earlier per-night fits (0.195-0.248)
is that of fits with a free intercept over one night's sky levels, which span
11 ADU on 2026-08-29 and 28 ADU on 2026-09-25 (a free line through the pairs alone
gives 0.12 ± 0.61 and 0.25 ± 0.01): slope and intercept are degenerate there;
the earlier estimates also took the spatial sigma of single frames. Read noise
2.6 e- at the 1024 black level, the 16-ADU quantisation included (2.4 e-
without); the black level and the read noise are degenerate in these data (1.0 e-
at 1000 ADU, 3.2 e- at 1040), the e-/ADU is not (0.2357-0.2362 on `050148Z`).
**Other gains.** The IMX585's gain setting is in 0.1 dB steps: gain 100 measures
0.183 e-/ADU (frame pairs, `045156Z`) and 0.177 (one light, `045626Z`) where
0.228 × 10^(−20/200) gives 0.181; and gain 0 gives 0.573 e-/ADU, 37.6 ke- at the
12-bit full scale against the IMX585's 38 ke- full well. The single gain-65 light
(`034413Z`, sky 55 ADU above black: read noise dominates) is inconclusive (0.221
against 0.271). The profile scales the gain-80 value by 0.1 dB per step over
gains 0-251, below the IMX585's high-conversion-gain switch at 252; above it no
frame measures anything: the chain keeps the driver, then the reference curve,
and logs the value as unverified.
**Amended (the owner's call of 2026-11-16 on the validation's F2).** The scaling is
kept; a scaled gain carries the read noise measured at gain 80 (2.6 e-) instead of
the Settings `photometry.read_noise_e` (1.5 e-), and every gain other than 80
(measured) and 100 (the scaling checked by its own photon transfer:
`gain_scaling_checked`) is logged once "e-/ADU at gain N scaled, not measured". The
gain-65 light fits its scaled 0.271 e-/ADU with about 3.2 e-, or about 0.22 with
2.6 e-: S72's model / measured sky σ there is 0.79 with 1.5 e-, about 0.89 with the
measured 2.6 e- (S72's *Its test*; one frame, no pair to measure the gain). The
read noise also follows the frame's own e-/ADU whatever the path (technical
review): `with_frame` kept the base params' read noise when the frame's e-/ADU had
none, so a frame at gain 300 had 2.6 e- in a re-run with the Camera form at 80 and
1.5 e- with the form at 300; it now takes the measured one, else the Settings one.
**Amended again (the owner's call of 2026-11-16 on the technical review): the
observer's own photon-transfer file first.** The file (`camera_calibration*.json`,
Settings › Photon-transfer calibrations: `camera_calibration.json` for the IMX585,
`camera_calibration_<sensor>.json` otherwise) was read with the sensor reference,
the chain's last step, below the profile's measurement at gains 0-251 and below the
driver. An observer's measurement of their own camera beats one made on another
unit: its entry at the frame's exact gain now comes second, after
`camera.egain_table` and before the profile (`egain.from_calibration`), live and for
a saved frame (`of_frame`: the table, an `EGAIN` the table wrote, the file, an
`EGAIN` the file wrote, the profile, the frame's `EGAIN`), with the file's `rdnoise`
at that gain as the read noise measured with it (else the Settings one, as for any
e-/ADU without a measured read noise). Its source is recorded as every step's is
(the `EGAIN` and `RDNOISE` comments, the recorder's `egain_source`), named
"<sensor> PTC file" ("IMX585 PTC file" on the S30 Pro; before, the file's value was
recorded as the reference's "IMX585 ref"); logged once per gain. The owner's study
runs are unchanged: the default folder (`~/.argos`) holds no such file.
**The file's read noise (validation F2, the review).** With an e-/ADU that carries no
read noise of its own (the gain table's, the driver's), a new frame's `RDNOISE` is
the file's `rdnoise` at that gain named "IMX585 PTC file" (`egain.calibration_read_noise`;
it was the same value named "IMX585 reference"). A saved frame whose `EGAIN` the file
wrote, re-run or opened without the file, keeps the `RDNOISE` the file wrote with it
(the Settings 1.5 e- before), when the `RDNOISE` comment names the file. A file entry
without `rdnoise` keeps the Settings read noise, as every e-/ADU without a measured one
does (the profile's 2.6 e- measured at gain 80 is not mixed with another e-/ADU), and
the log line of that gain says so: give the file both (2.6 e- against 1.5 e- moves the
SNR of a star under RR Lyr's 10 s sky by 2.5 %; the review's `rn_fallback_snr.txt`).
**What changed.** The S30 Pro profile carries the measurement
(`TelescopeProfile.gain_measurements`, `gain_step_db`, `gain_scaling_range`;
`hardware/egain.py`). One order for the photometry, `EGAIN` and the re-run:
`camera.egain_table`, the observer's photon-transfer file (amended above), the
profile's measurement (or its scaling), the driver, the reference curve. New
frames write it to `EGAIN` (comment "S30 Pro PTC" or "S30 Pro PTC scaled") and,
at a measured gain, to `RDNOISE`. An old frame of the camera its `TELESCOP` names
takes the measurement at its `GAIN` instead of its `EGAIN` (an `EGAIN` the
observer's table wrote is kept); the batch re-run (S70:
each frame's own) and Open FITS use it, and the flight recorder's `frame` record
names the value and its source (`egain`, `egain_source`).
**Effect on the study runs** (with S72-S75, the batch re-runs above). Star-pair
point-to-point scatter / formal error (median over the pairs; robust in
brackets): RR Lyr 2 comparisons + check 2.27 → 0.89 (2.06 → 0.80), 6 comparisons
1.89 → 0.96 (1.63 → 0.78), XX Cyg `040723Z` 1.48 → 1.12 (1.41 → 0.99),
`050148Z` 0.94 → 0.72 (1.03 → 0.78); `sigma_syst` of the RR Lyr target 0.018 → 0
(the formal errors now hold the scatter). Check stars − VSP V: 000-BCG-523
+0.0162 ± 0.0016 → +0.0166 ± 0.0016 (VSP ± 0.10), 000-BJV-169 −0.074 ± 0.009 →
−0.064 ± 0.010 (± 0.051), 000-BJV-171 +0.051 ± 0.023 → +0.063 ± 0.020 (± 0.030).
RR Lyr 2 comparisons − Siril green 2 comparisons: +0.0013, robust σ 0.0096 →
+0.0013, 0.0099; 6 comparisons: −0.0076, 0.0153 → −0.0103, 0.0136 (S71's weights
follow the corrected errors; with S73 alone −0.0102: not the same ensemble as
Siril's, so not an error of either).
**Who was affected.** Every SNR and formal error of the S30 Pro at gain 80 (every
run of the owner's), and every gate that reads an SNR (S72's table).
**How to check.** `tests/core/test_photometry_core.py::test_an_s30_pro_frame_at_gain_80_uses_the_measured_egain_s73`
(0.8 and 1.723 before the fix), `::test_other_gains_scale_by_the_sensors_0p1_db_steps_s73`,
`tests/core/test_fits_writer.py::test_egain_header_is_the_measured_one_at_gain_80_s73`
(the driver's 0.8 before the fix),
`tests/workers/test_acquisition_engine.py::test_the_s30_pros_measured_egain_comes_before_the_driver_s73`
(the driver's 2.5, the file's 1.723),
`tests/workers/test_photometry_batch_worker.py::test_batch_uses_the_cameras_measured_egain_and_scintillation_s73_s74`
(0.8 and 1.723), `tests/core/test_photometry_core.py::test_a_scaled_gain_is_logged_scaled_not_measured_except_where_checked_s73`
(no log before the amendment), `::test_the_read_noise_follows_the_frames_egain_whatever_the_path_s73`
(2.6 e- kept for a gain-300 frame before),
`::test_the_observers_photon_transfer_file_comes_before_the_profile_s73` (the
profile's 0.228 and the S50 driver's 0.5 before the second amendment),
`tests/core/test_fits_writer.py::test_egain_header_takes_the_observers_photon_transfer_file_first_s73`
(0.228 and 2.6 e- written whatever the file said),
`::test_rdnoise_names_the_observers_photon_transfer_file_s73` ("IMX585 reference"
before the fix; `test_the_observers_photon_transfer_file_comes_before_the_profile_s73`
also checks the `RDNOISE` the file wrote, None before, and the log); web
`tests/server/test_open_fits.py::test_an_opened_frame_keeps_an_egain_its_table_wrote_s73`
(the server's opened frame lost the `EGAIN` comment: 0.228 where Qt keeps the
table's value), `tests/server/test_config.py::test_the_photon_transfer_help_says_the_cores_order_s73`
(GUARD: the Settings help follows the core's order).

### S74 — Each star's error carries its scintillation

**What was wrong.** No error term held scintillation: the bright RR Lyr star pairs
scattered 2.2-2.4 times their formal errors under every noise model.
**What changed.** Young's (1967) formula with Osborn et al.'s (2015, MNRAS 452,
1707) coefficient C_Y = 1.5: relative sigma² = 1e-5 C_Y² D^(−4/3) t^(−1) X³
exp(−2h / 8000 m), from the profile's aperture (30 mm), the frame's exposure,
the star's airmass and the site's height (the frame's `SITEELEV`, else the Settings
site's, else sea level, logged). The airmass: in a re-run, each star's own as its
row gets it (`measure_frame(star_airmass=...)`: S66's header `AIRMASS` for the
target, computed for a frozen pointing, X1, never the lost mount's stale value;
S78's own for a comparison or check star; amended after the science and technical
reviews, which found the header `AIRMASS` used for every star, frozen frames
included); live and Open FITS, the frame's (the mount's, or the opened frame's
`AIRMASS`): within 1 % of each star's own in a 1.3° field. Without an exposure or an
airmass the term is 0, logged once. It is added
in quadrature to each star's `inst_mag_err`, hence to the zero point's weights
(S71) and to every target's and check star's error; the SNR the gates read is
the CCD equation's alone. 0.017 mag per star in 10 s at airmass 1 (RR Lyr), 0.014
in 20 s at airmass 1.09 (XX Cyg 09-07). Green-plane model only.
**Its check.** The bright RR Lyr pairs' (SNR ≥ 20) scatter over their photon errors
implies C_Y 1.11-1.17 (median over 21 and 6 pairs, robust scatter) to 1.32-1.42
(plain standard deviation); with C_Y = 1.5 their scatter / formal error is 0.89-0.96
(plain) and 0.78-0.80 (robust). A 30 mm aperture is near the Fresnel scale, where
the formula's D^(−4/3) is least certain; one night measures it.
**C_Y stays 1.5 (the owner, 2026-11-16, validation F3).** It is conservative: bright
stars' errors and their AAVSO `MERR` come out larger than their scatter (RR Lyr
pairs at SNR ≥ 100: 0.80, robust 0.73; the RR Lyr target's second-difference σ over
its formal error 0.62-0.75; the check 000-BCG-523's χ²ᵣ 0.59), while faint stars are
near 1 (XX Cyg 2026-09-07: 1.11, robust 1.01). The bright pairs measure C_Y 1.1-1.4
(1.11-1.17 robust, 1.32-1.42 plain; the science review 1.0-1.27); a refit needs
more nights. The science review also names the ensemble's `zp_err` rms branch and
its 0.01 floor as part of the excess (OWNER DECISION, S71, not changed).
**How to check.** `tests/core/test_photometry_core.py::test_scintillation_follows_young_and_osborn_s74`,
`::test_scintillation_is_in_each_stars_error_not_its_snr_s74` (the photon error
alone before the fix), `tests/workers/test_photometry_batch_worker.py::test_a_frozen_frames_scintillation_takes_its_rows_airmass_s74`
(the frozen frame's stale 2.0 for every star before the amendment),
`tests/workers/test_acquisition_engine.py::test_the_live_path_adds_the_subs_scintillation_s74`
(the live hunk had no test); web
`tests/server/test_photometry.py::test_the_live_port_adds_the_frames_scintillation_s74`.

### S75 — The sky estimate's own error is counted

**What was wrong.** The flux error counted the sky noise of the aperture pixels but
not the error of the sky level subtracted from them, the median of the annulus.
**What changed.** The CCD equation's form, n_ap (1 + (π/2) n_ap / n_sky) per-pixel
variances, the π/2 that of a median (green-plane model only). With an 8-12 px
annulus and a 5.3 px aperture (89 and 244 pixels) it adds 57 % to the sky
variance.
**Its check.** 7800 blank apertures on RR Lyr `200453Z`, 960 on XX Cyg `040723Z`,
880 on `050148Z` (40 per frame, 30 px from every set star, no pixel above 6σ): the
scatter of their flux over the model built on each annulus' measured sigma is
1.79, 1.61, 1.60 without the term and 1.43, 1.28, 1.26 with it. Most of the rest
was the annulus median's quantisation (S76). Since S76 the sky is the annulus'
clipped mean and the factor a mean's 1, over the pixels the clip keeps (36 % of the
sky variance with 89 and 244 pixels). That factor is measured: on the real annuli
(the two halves of each, 9340 pairs on RR Lyr) the clipped mean's is 1.09 (the
median's 2.95), within 1.2 % of the total error; on a sky quantised as the plane it
is 1.00-1.09 whatever the level's phase on the 8-ADU grid (the median's 0.38-9.5).
Against the code's own error since S76 the blank apertures scatter 1.17, 1.19, 1.14
times (validation, the selection above, every fifth RR Lyr light; 1.42, 1.31, 1.25
with the median) and 1.10, 1.07, 1.07, 1.06 (the review, RR Lyr, `050148Z`,
`040723Z`, `052943Z`, a stricter star mask; 1.40, 1.20, 1.20, 1.20 with the median);
the 1.06, 1.06, 1.05 first quoted here were against the median's model (π/2, every
pixel). The rest is not the estimator: neighbouring pixels correlate (0.02-0.04; a
k × k box sum's variance is 1.02-1.08 times that of independent pixels, k 2-7, 1-4 %
on σ) and faint stars sit in the apertures (the bias of S76).
**How to check.** `tests/core/test_photometry_core.py::test_the_sky_estimates_own_error_is_counted_s75`
(the error 25 % below the scatter before the fix; with S76's mean, 0.86 without the
term, 1.07 with it, 1.17 with a median's π/2).

### S76 — The sky is the annulus' 3-sigma-clipped mean, not its median

**Status: adopted (the owner's call of 2026-11-16, science review F1).** It was
first evaluated and left out ("not adopted"); the science review's new evidence
decided it.
**What was wrong.** The green plane steps by 8 ADU (12-bit values × 16, averaged
in pairs), so the annulus median sat on a 4-8 ADU grid: its error is a sawtooth with
the sky level's phase on that grid, about 2.1 ADU rms per pixel (median minus
clipped mean 2.27-2.34 ADU rms on RR Lyr against 0.96 on continuous data), more
than the 1.6 ADU S75's π/2 counted, in no error term, and too slow for `sigma_syst`
to see: 0.004-0.005 mag rms per bright RR Lyr star, about 0.05 mag for a 5000 ADU
XX Cyg comparison.
**What changed.** `measure_aperture` takes the annulus' 3-sigma-clipped mean
(`aperture.sky_level`): pixels farther than 3 standard deviations from the median
rejected, median and standard deviation recomputed on what is kept, repeated until
nothing more is rejected, at most 10 passes (bounds inclusive): photutils'
`ApertureStats` default, `astropy.stats.sigma_clipped_stats(sigma=3, maxiters=10)`
(Siril and photutils use a clipped mean too). S75's sky-estimate term takes a mean's
factor 1 instead of the median's π/2, over the `n_sky` pixels the clip keeps. Every
aperture of the core and the server: points, anchors, lock checks, comparison
quality, the pilot; both noise models (the 0.4.x `pixel` model keeps its formula,
which has no S75 term). Non-finite annulus pixels are left out of the estimate.
**The two evaluations that decided it.**
- The noise role (the after re-runs' aperture centres, 8-12 px annulus, numpy
  only). Star pairs, robust point-to-point scatter, clipped mean / median (median
  over pairs; pairs where the mean is worse): RR Lyr 6 comparisons 0.96 (3 of 21),
  2 comparisons + check 0.94 (1 of 6), XX Cyg `040723Z` 0.75 (10 of 36),
  `050148Z` 0.83 (4 of 10). Blank apertures (as S75): flux bias with the median
  +47 ± 4, +61 ± 14, +49 ± 16 ADU per aperture, with the mean +22 ± 3, +36 ± 12,
  +32 ± 13; scatter 335 → 248, 445 → 368, 462 → 385 ADU; the other study runs
  alike. Its verdict by the rule it was given (better or equal everywhere, and
  unbiased): not adopted, the mean being better in every run and less biased in
  all ten re-runs, but worse on 18 of 73 pairs and not unbiased (both estimators
  read the sky low where faint stars sit in the annulus).
- The science review (its own code). Against the independent star_var_script +
  Siril green reduction (2 comparisons), RR Lyr's residual robust σ is 0.0108 with
  the median and 0.0073 with a clipped mean (ratio 0.69, 68 %: 0.63-0.76): the
  median's quantisation was the largest identified part of the ARGOS − Siril
  residual. Pairs, clipped mean / median: `040723Z` 0.81 (18 of 28 better, one
  marginally worse: 1.11 [1.00-1.22]), RR Lyr 6 comparisons 0.97 (11 of 15 better,
  none worse); the two worse `050148Z` pairs hold non-detections (SNR 1-2): the
  "worse" pairs of the first evaluation are noise or non-detections. Blank
  apertures, scatter over the model: median + S75 1.14-1.54; with a quantisation
  term n_ap² Δ²/12 (Δ = 8 ADU) 1.01-1.26; clipped mean 1.00-1.31. Bias on RR Lyr:
  +45 ± 35 ADU (median), +21 ± 23 (mean).
- Why the mean: better or equal on every pair whose two stars are detected (one
  marginal exception), about half the bias, nearer the independent reduction, and
  an error the CCD equation describes; neither estimator is unbiased (faint stars
  in the annulus), the mean less biased wherever the bias is significant. The other
  options were (b) the median with a quantisation term in S75 (honest errors, the
  scatter kept) and (c) no change.
**The code, RR Lyr 2026-09-25 `200453Z`, 2 comparisons + check** (Qt batch
re-runs before and after on the same clone, ASTAP, the night's Settings site; impl
`level_a_{before,after}.json`, `target_shift_rr2.json`, `star_deltas_rr2.json`,
`blank_{before,after}.json`): the same apertures (0.000 px apart), the sky moves by
2.30-2.38 ADU rms per star and frame (the median's sawtooth); RR Lyr − Siril green 2
comparisons +0.0013 / robust σ 0.0101 → +0.0021 / 0.0083 (σ ratio 0.83, 68 %:
0.74-0.91; the offset's change, +0.0008 [+0.0001, +0.0012], is within the offset's
own error, 0.0007-0.0009, while the target's own magnitudes move by −0.0004 median,
0.0050 rms); check 000-BCG-523 − VSP V +0.0167 ± 0.0016 → +0.0166 ± 0.0015 (its
scatter 0.0225 → 0.0213); pair scatter / formal error 0.89 (0.77 robust) → 0.86
(0.75): the scatter is lower, the formal errors the same (−0.4 %; bright stars'
errors are S74's conservative scintillation); `sigma_syst` 0 → 0. 1560 blank
apertures (every fifth light): bias +27 ± 8 → +9 ± 6 ADU, scatter 333 → 255 ADU,
scatter over the code's own error 1.42 → 1.16; the model's sky σ over the annuli's
measured σ 1.008 both (10-90 %: 0.945-1.078).
**The other study runs** (the validation's batch re-runs of every study run, before
and after; the fixer's final re-run of RR2, RR Lyr's 6 comparisons, `040723Z` and
`050148Z` gives the same figures key by key): RR Lyr 6 comparisons − Siril −0.0110
/ robust σ 0.0147 → −0.0098 / 0.0130; checks − VSP V 000-BJV-169 −0.0647 ± 0.0091 →
−0.0645 ± 0.0085 (VSP ± 0.051), 000-BJV-171 +0.0447 ± 0.0223 → +0.0436 ± 0.0204
(± 0.030); pair scatter / formal error RR Lyr 6 comparisons 0.95 (0.80 robust) →
0.94 (0.77), `040723Z` 1.11 (1.01) → 1.12 (0.95), `050148Z` 0.71 (0.60) → 0.92
(0.94) (three pairs: the median sat at 1400 ADU on 17 of 22 frames, a bias no error
counted, where the mean adds a noise the error counts); the `040723Z` target's
`sigma_syst` 0.170 → 0 (its second-difference σ 0.283 → 0.124 mag, SNR about 5);
blank apertures `040723Z`, `050148Z`: bias +44 ± 14 → +32 ± 12, +52 ± 15 → +25 ± 12
ADU, scatter over the code's error 1.31 → 1.19, 1.25 → 1.14; the model's sky σ over
the measured one 0.959-1.049 → 0.960-1.039 (gains 80 and 100, 31 frames; the one
gain-65 frame 0.883); the code's sky equals astropy's `sigma_clipped_stats(sigma=3,
maxiters=10)` within 0.01 ADU on 502 of 504 records (the two others hold a pixel
1e-5 px from the annulus edge); the apertures, times and airmass unchanged. The
higher SNR (×1.02 for bright stars, ×1.06-1.08 where the sky dominates) moves stars
across the gates' thresholds: on the XX Cyg runs anchors, verification solves and
three flags change, each explained by the validation (faint comparisons' anchors
crossing SNR 5 and 10; `050148Z` frame 5 keeps 2 comparisons after the clip, so no
S71 flag; `052943Z` frame 3's target flagged by the hot-pixel guard at 9.9 % against
the 10 % threshold). On the live path the cloudy `045626Z` frame, a lock lost
before, is now measured on its one anchor with the target at SNR 0.8, unflagged in
the live CSV; Review, the AAVSO export and a re-run leave it out (S67). Since S85
the live path flags it too, when it measures it.
**Who was affected.** Every magnitude and error of every run: by a few mmag on
bright stars, more on faint ones (the sawtooth scales as 1/flux).
**How to check.** `tests/core/test_photometry_core.py::test_the_sky_is_no_quantised_median_s76`
(a flat Gaussian sky quantised to the plane's 8 ADU, stepped by 1 ADU through one
grid period: within 0.5 ADU at every step; the median missed it by up to 4 ADU
before the fix), `::test_the_sky_is_the_annulus_3_sigma_clipped_mean_s76`
(astropy's `sigma_clipped_stats` as the reference, a star and a hot pixel in the
annulus, the term over the pixels kept; the median before),
`::test_the_sky_estimates_own_error_is_counted_s75` (1.17 with the median's π/2
kept for a mean).
**Check your old files.** Magnitudes and errors of old runs change slightly when
re-run (**Re-run subs…**): RR Lyr 2026-09-25's target by 5 mmag rms per point
(−0.4 mmag median), its scatter against the Siril reduction down 17 %; faint
stars move more (the median's error scales as 1/flux).

### S69 — The tracker keeps up with a fast-turning alt-az field, and checks its apertures

**What was wrong.** The aperture tracker centroided each anchor star once, in a
15 green px window centred on where the previous frame's transform put it. The
window's background-subtracted flux is clipped at zero, so the sky noise of the
whole window adds a flux centred on the window, and a moved star's wings are cut
by its edge: the centroid kept 30-80 % of the distance between the prediction
and the star (every anchor of every frame of XX Cyg 2026-09-07 `040723Z`, against
each frame's own ASTAP solution). That field turned 0.7° per sub (4.2-7.5 px of
motion between subs at the set's stars), so the fitted transform lagged it by
0.4-1.2° from the second frame on: a batch re-run through frame 1's solution
ended at 15.37° of rotation where ASTAP measured 16.49° (16.02° with the
e-/ADU 0.8: one anchor fewer), comparisons up to 8.5 px (4.5 px) off their stars
(aperture radius 5.45 px). The lock checks only ask whether a
star shows in the aperture (S43, S48), so nothing flagged it. In the live path,
with a solve before every sub, the lag was one sub's: target apertures 0.2-1.5
px off on `040723Z`, 0.2-3.4 px on 2026-08-29 `050148Z` (the 3.4 px sub flagged
by S56), and on RR Lyr 2026-09-25 a 0.5 px bias on every comparison.
**Who was affected.** Every tracked measurement, live, sequence and re-run; by
pixels on alt-az fields turning fast (XX Cyg near the meridian at 67°), by
tenths of a pixel elsewhere.
**What changed.** (root cause, `tracking.py`) Each anchor's centroid is
re-centred on itself until it moves less than 0.01 px, in the search window and
then in a 4 px window (about two FWHM, so the brighter of a close pair is not
dragged by the fainter: 000-BJV-169, 6.9 px from 000-BJV-173, 1.5 mag fainter):
the tracker now follows
`040723Z` within 0.07° of ASTAP on all 24 frames, its anchors within 0.2 px.
Two safety nets follow, in the live and sequence paths and the batch re-run:
(a) a solve is due once the tracked rotation since the solution exceeds 2°
(the re-run solves the frame at once; live, the sub in hand in a run); while
none lands, again only after 2° more, so a failing or slow solver costs one
solve per 2° of rotation, never a loop; (b) every frame, each comparison and
check star seen at SNR ≥ 5 has its centroid measured within its aperture: one
more than 1 px from the aperture centre is left out of the frame's ensemble,
its own point flagged `suspect`, counted (re-run: `stars_off_centre`) and
recorded (`centroid_offset_px`, `off_centre` in the star records); when the
anchors that remain centred are fewer than 3, the frame is S56's (S58's) case:
verified only near a fresh solution, else re-solved, else flagged. A star
fainter than SNR 5 is not tested: its centroid scatters by about 1.6/SNR px per
axis. Re-runs through the Qt batch worker, ASTAP as the solver (before: the
committed release core with S66-S68 and S71, the e-/ADU 0.8 of W7's re-run;
after: S69 and S70):

| Run | Before | After |
|---|---|---|
| XX Cyg 09-07 `040723Z`: field rotation found, frames 1-24 | −16.02° (ASTAP −16.49°) | each frame within 0.07°; 7 re-solves at 2° |
| Same: comparison and check apertures from each frame's solution, frames 1-3 / last | 0.2-2.5 / 0.6-4.5 px | 0.01-0.22 / 0.01-0.12 px |
| Same: check 000-BJV-169 − VSP V; scatter; χ²ᵣ (mag_err) | −0.045 ± 0.017; 0.084; 1.70 | −0.071 ± 0.010; 0.046; 0.65 |
| XX Cyg 08-29 `050148Z`: check 000-BJV-171 − VSP V | +0.060 ± 0.029 | +0.060 ± 0.024 |
| Same: apertures from each frame's solution (median / max) | 0.5 / 2.1 px | 0.1 / 0.8 px |
| RR Lyr, 2 comparisons − Siril green 2 comparisons (median, robust σ) | +0.0004, 0.0099 | +0.0013, 0.0096 |
| RR Lyr: check 000-BCG-523 − VSP V; comparison apertures | +0.0166 ± 0.0016; 0.7-0.8 px | +0.0162 ± 0.0016; 0.13-0.14 px |

The check star on `040723Z` is now 1.4σ from VSP once VSP's own ± 0.051 on its
V is counted; 000-BJV-173 puts 1.0 % of the light in its aperture (−0.011 mag,
its growth curve against isolated stars), and calibrated against each
comparison alone it ranges from −0.008 to −0.148 mag (the comparisons'
catalogue values). Counts on the three re-runs, before → after: S43 re-solves
0 → 0, 0 → 0, 2 → 2; S58 verify solves 0 → 1, 10 → 13, 0 → 0; re-solves for
rotation 7, 0, 0; points flagged 0 → 0 on every target; frames skipped 0;
off-centre measurements 15 (000-BJV-173 beside 000-BJV-169 on 7 frames, and
all 8 stars of the sub `_00020`, S67's no-detection frame, where two of six
anchors locked on 000-BJV-169 and on noise), 1 and 0. A failing solver on
`040723Z`: 7 attempts in 24 frames, the tracker alone ends 0.07° from ASTAP;
3 s per solve: the same result in 27 s. Live and sequence paths, the replay of
the owner's runs (Argos's own solves; one solve per run, or one per sub):
`040723Z` target apertures 0.5-3.0 px (one solve per run) and 0.2-1.5 px (one
per sub) from the star before, 0.01-0.17 px after but subs `_00019` (0.83 px)
and `_00020` (2.1 px, no target point: every comparison off-centre), solves 1 →
9 with one per run; `050148Z` 0.24-3.4 px before, 0.02-0.66 px after, with 3
more frames flagged by S56 (frames 14-16: the field moved 2.5-3.7 px between subs,
which the lagging tracker reported as less than S56's 2 px; their target points
are 0.06-0.14 px from the star; owner decision); RR Lyr frames 40-79 unchanged
(39 points, frame 52 skipped, 2 solves), its target aperture 0.8-1.2 px from
the star as both trackers place it on the J2000 position (RR Lyr's 0.8 px of
proper motion, not applied; `notes/tracker_comparison.md`). The web server's
port gives the same points, CSVs, vetting files and solves on these replays,
and the same CSVs, `targets.json` and flight-recorder records on the three
re-runs.
**How to check.** `tests/core/test_photometry_tracking.py::test_the_tracker_keeps_up_with_a_field_rotating_0_7_deg_per_sub_s69`
(1.7° of lag after 24 subs on the code before the fix),
`::test_refine_centroid_finds_a_star_away_from_the_window_centre_s69`,
`::test_refine_centroid_is_not_dragged_by_a_neighbour_7_px_away_s69`,
`::test_centring_offsets_find_a_star_off_its_aperture_s69`,
`::test_a_re_solve_is_due_past_2_deg_of_rotation_and_retried_per_2_deg_s69`;
`tests/workers/test_photometry_batch_worker.py::test_a_re_run_re_solves_once_the_field_turned_2_deg_s69`
(no re-solve on the code before the fix),
`::test_a_re_run_leaves_an_off_centre_star_out_of_the_ensemble_s69`,
`::test_off_centre_anchors_leaving_fewer_than_3_make_a_re_solve_due_s69`;
`tests/workers/test_acquisition_engine.py::test_a_field_turned_more_than_2_deg_since_the_solution_makes_a_solve_due_s69`,
`::test_an_off_centre_comparison_leaves_the_ensemble_s69`;
`tests/ui/test_batch_rerun.py::test_batch_summary_says_the_re_solves_for_rotation_and_off_centre_stars_s69`
(the end of a re-run: INFO "the field turned more than 2° since its solution on N
frame(s); each was re-solved", WARN "N comparison/check measurement(s) more than 1
px from their aperture centre were left out …"). Every one fails on the code
before the fix.
**A faint star beside a brighter one (both W7 reviews of S69).** Re-centred until
it converges, the window of a fainter star climbs onto a brighter neighbour
within it. Two consequences, both fixed. (1) An anchor 6.9 px from a star 4.9
times brighter (000-BJV-173 beside 000-BJV-169) was measured on its neighbour
every frame (7.0 px off), and the fit spent its one rejection on it, so a second
bad anchor broke the fit (sub `_00020`: 2.8 px, all 8 stars off-centre, no
target point). A candidate with a star of the set (targets included) holding a
quarter of its core flux or more (sky-subtracted, within 2 px) within the search
radius plus 8 px (the largest motion between subs seen, 7.5 px) is no anchor
(`select_tracking_anchors(neighbours=…)`), and the anchor the fit rejects no
longer counts as a verifying one (S56, S58). (2) The centring test of S69 (b)
flagged a faint star whose aperture sits on it: 000-BJV-173 off-centre on 7 of
24 frames while 0.03-0.20 px from its aperture (a two-Gaussian fit, and each
frame's ASTAP solution). Its centroid is now taken within 0.45 × the distance to
the nearest such neighbour (not tested when that is under 2 px), and re-centred
in 3 px rather than the aperture radius, where a star near SNR 5 wandered onto
noise (XX Cyg 2026-08-29 000-BJV-178, frame 5: 2.68 px where a Gaussian fit puts
it 0.08 px from its aperture). Final re-runs (ASTAP, that night's Settings site,
S66-S71 applied): `040723Z` 000-BJV-173 is no anchor, tested on 23 of 24 frames,
at most 0.23 px from its aperture (0.31 px by a Gaussian fit); off-centre
measurements 15 → 0; the fit's rejection spent on 3 of 24 frames instead of
every frame; frames 1-3 within 0.27 px of every star (Gaussian fits); 7
re-solves for rotation; the check star −0.074 ± 0.009 from VSP. `050148Z`:
off-centre 1 → 0 (000-BJV-178 frame 5: 0.41 px), 13 verify solves, 0 flagged by
S58. RR Lyr (2 comparisons): no off-centre measurement; the comparisons'
apertures 0.27-0.43 px (median) from their Gaussian centroids (the 0.13-0.14 px
of the table are from each frame's own plate solution), the target's 1.0 px
(RR Lyr's proper motion, not applied).
**Messages and counts (technical review).** A failed re-solve for rotation no
longer says "the frame did not solve — its points are flagged" (it flags
nothing); it has its own WARN, and a later S43/S58 failure keeps its message.
The re-run counts the failed re-solves for rotation (`frames_rotation_unsolved`:
"the field turned more than 2° since its solution on N frame(s) that did not
re-solve; their apertures followed the tracker") and the frames left without a
target point because every comparison was off-centre (`frames_no_target_point`),
in Qt's end-of-run messages, the flight recorder's `batch_end` and the web
re-run summary.
**The tracking gates with the new SNR (2026-11-16).** S72-S75 make the SNR the
frames' measured noise: against the 0.4.x model it is 0.40-0.77× on the XX Cyg
runs and 1.07-1.6× on RR Lyr (median per run, comparison stars; an old SNR of 10
reads 7.3 now, 4.3-8.7). The gates keep their thresholds, now true σ: the anchors
SNR ≥ 10 (S56), "seen" SNR ≥ 5 (S43, S48), the centring test SNR ≥ 5 (S69 b). Qt
batch re-runs and sequence replays of every study run, before (`3e48d78`) and
after (S56 at 10 px, S72-S80; `gates_counts.json`): anchors per frame drop on XX
Cyg (`040723Z` 4-6 → 2-5; 2026-08-29 runs 1-3); RR Lyr frames 52 and 175 (blank
sky) stay skipped (S35 now, S48 before); XX Cyg 2026-09-07 `045626Z` frame 2, a
cloud frame (every star 2-4× fainter than on frame 0, its target below SNR 3 and
flagged by S67 before and after), loses its lock (comparisons at SNR 2.5-4.5) and
its comparison rows are flagged (1 → 8 suspect comparison rows); 2026-08-29
`052943Z` frame 3 and `053540Z` frame 1 flag 000-BJV-172 off-centre (1.10 and 1.56
px; an independent Gaussian fit puts its aperture 1.18 and 1.60 px from the star:
true, with 1-2 anchors the rotation is barely constrained). No target point of a
good frame is lost, no blank-sky frame measured. **Decided (the owner,
2026-11-16): the anchors keep SNR ≥ 10**, whose meaning is now the same on every
run (an old SNR of 10 meant about 7.6 on the 0.4.1 XX Cyg frames and 10.6 on RR
Lyr). What it costs, measured: the 15 s XX Cyg 2026-08-29 subs keep 1-2 anchors
(2-3 before), so S56 verifies more of their locks with a solve (`050148Z` re-run:
13 → 9 verifying solves, `053540Z` 4 → 2, `040723Z` 0 → 1), a comparison sits
1.1-1.6 px off on 2 of 8 frames of `052943Z`/`053540Z` (flagged by S69 b, left
out of the ensemble), and with one solve per run the live replay of `050148Z`
flags frame 19 (one of its 3 anchors, the target taken at S35's SNR ≥ 5, clipped
3.0 px off its consensus: 2 anchors, no fresh solution; its target point is 0.10
px from the star) while frames 13-16 are no longer flagged (5 → 2 flags). No wrong
point is kept. The alternative, 7 (the old threshold on the XX Cyg scale), was
not taken: it would need a replay of every study run.
**Decided on 2026-11-16 (the owner, all four as recommended).** (1) S56's
threshold is 10 px (S56, amended); (2) proper motion: S77; (3) the warning: S79;
(4) the pair-distance rule in the core tracker: S80, and the web overlay tracker
takes the core's converged centroid (0.315° → 0.074° of lag at most on
`040723Z`, S80). The decision text as it was:
**Open (owner decisions, not implemented).** (1) S56's 2 px freshness
threshold, tuned on the lagging tracker: each frame's own solve shows the field
moving up to 5.1 px between subs on `050148Z` and 4.2-7.5 px on `040723Z`; in
the live path `050148Z` now flags 3 more frames (14-16) whose target points are
0.06-0.14 px from the star. Options: (a) keep 2 px (a batch re-run verifies them
with solves); (b) a threshold between the largest motion between subs (7.5 px)
and a neighbour lock's 22-36 px, about 10 px; (c) verify few-anchor locks by
S69 (b)'s centring instead (weaker against a 1-anchor neighbour lock).
Recommended: (b). (2) Proper motion: target sets hold J2000 positions; RR Lyr's
aperture sits 1.0 px from the star (its 0.8 px of proper motion) and its re-run
`sigma_syst` goes 0.0152 → 0.0182 while its scatter against Siril does not
change. Options: (a) keep; (b) carry pmRA/pmDec in the target set (VSX or Gaia)
and move each position to the frame's epoch; (c) test the target with S69 (b)
too (noisy at minimum). Recommended: (b). (3) `040723Z`'s set pairs the check
star 000-BJV-169 with 000-BJV-173, 6.9 px away, 1.47 mag fainter, inside its
5.45 px aperture: remove 173 from that set, or warn when a VSP comparison has a
brighter set star within about 2 aperture radii. Recommended: the warning.
(4) The pair-distance rule of the web's field tracker (`field_track.consistent_pairs`)
in the core tracker, so that more than one inconsistent anchor can be rejected,
with its own test; and the web overlay tracker (`argos/server/field_track.py`)
still centroids in two passes (0.31-0.44° behind on `040723Z`).
**How to check (the review fixes).** `tests/core/test_photometry_tracking.py::test_a_star_beside_a_brighter_one_is_no_anchor_s69`,
`::test_a_faint_star_beside_a_brighter_one_is_centred_on_its_aperture_s69`,
`::test_an_uncatalogued_star_in_the_aperture_does_not_move_the_centroid_s69`,
`::test_a_neighbour_outside_the_tested_stars_counts_too_s69`,
`::test_tracker_rejects_a_bad_anchor` (each fails on the code before),
`tests/ui/test_batch_rerun.py::test_batch_summary_says_the_re_solves_for_rotation_and_off_centre_stars_s69`.
**Check your old files.** See *Check your old files* (S69).

### S77 — An aperture follows its star's proper motion

**What was wrong.** A target set held each star's catalogue position, J2000.0, and
every path placed the apertures there whatever the date. RR Lyr moves 0.224"/yr:
on 2026-09-25 its aperture sat 0.99 green px (median, 195 frames; 1.11 px at the
90th percentile) from its star, measured by an independent Gaussian fit on each
frame's green plane, and its comparisons 0.27-0.43 px from theirs (000-BJW-666,
174 mas/yr: VSP's position is 3.2" from Gaia DR3's 2016.0 one).
**Who was affected.** Every measurement of a star with a large proper motion; by
tenths of a pixel or less for most comparisons. A 1 px offset in the owner's 5.3 px
aperture (FWHM 2.1 px) loses no measurable flux, so the photometry itself barely
moved (below).
**What changed.** Which catalogues can give proper motions: Gaia DR3 (the field
catalogue's `gaia_cone_search`, now with `pmra`, `pmdec`, at its 2016.0 epoch) and
SIMBAD (its TAP `basic.pmra/pmdec` and Sesame's `pmRA/pmDE`, unused here); AAVSO VSX
and VSP give none. A target set's star carries `pm_ra_mas_yr`, `pm_dec_mas_yr`
(µα·cos δ), the epoch and position they start from (Gaia's 2016.0 one) and their
source (`pm_source`, "Gaia DR3 <source_id>"); its `ra_deg`/`dec_deg` stay the
catalogue's, and a set without motions keeps its bytes. Only VSX/VSP stars with an
AUID take one: a Gaia source is the star's when its J2000.0 or 2016.0 position lies
within 1" of the catalogue one (the brightest of several), or, for a star with a
catalogue V, when it is the one source within 6" whose G is within 1 mag of V and
no other there is within 2.5 mag (a faint variable never takes a brighter
neighbour's motion). The field catalogue's answer gives them (live, Qt
`_on_catalog`, the object's set and the running run's `targets.json`, as S68); a
batch re-run looks them up at its start for the set's stars without one (Gaia DR3,
one cached 30" cone per star, online when Settings' field-star catalogue is; a
failure is a WARN and the catalogue positions) and saves the set it measured, with
the motions, beside its CSVs. Every path that places an aperture measures the set
at the frame's date (`TargetSet.at_jd`: live, sequence, re-run; the anchors, the
lock and centring checks too); BJD_TDB uses the moved position (0.004 s on RR Lyr).
Qt's markers and the web server's overlay draw the star where it is now (its
records carry `proper_motion`); the web server measures the same way.
**Evidence (RR Lyr 2026-09-25, 2 comparisons, check 000-BCG-523, Qt batch re-runs,
ASTAP).** Gaia DR3 2125982599343482624: −109.60, −195.85 mas/yr; moved back to
J2000.0 it lies 0.05" from the VSX position. Aperture centre − Gaussian centroid,
median (90th percentile), before → after: RR Lyr 0.990 (1.111) → 0.077 (0.157) px;
000-BJW-665 0.272 → 0.135 px; 000-BJW-666 0.432 → 0.091 px; 000-BCG-523 0.280 →
0.140 px. With S77 alone on the 0.4.x error model: the target's `sigma_syst`
0.01824 → 0.01728 (not back to the 0.0152 of before S69: the centring does not
explain that change); RR Lyr − Siril green 2 comparisons +0.0013 → +0.0006,
robust σ 0.0096 → 0.0105 (its own uncertainty about 0.0006); the check star
+0.0155 ± 0.0017 → +0.0155 ± 0.0018; counts unchanged (195 frames, 2 re-solves).
On the release tree with S72-S76, `sigma_syst` is 0 with or without S77 (the formal
errors carry the scatter): the expectation that it would return near 0.0152 is moot,
and the criterion is the aperture's (0.990 → 0.077 px, met). The study sets: 7 of 7
RR Lyr stars and 9 of 9 XX Cyg 2026-09-07 stars matched; on XX Cyg 2026-08-29, 5 of
the set's 6 VSX/VSP stars (000-BJV-180, V 14.15, takes none: no Gaia source passes
the rules, in the saved answer and in the archive's live answer of 2026-11-16;
validation F7, `gaia_pm_sets.json`).
**Amended (technical review).** The re-run's lookup (one cone per star, before the
first frame) waited 20 s per star on an archive that did not answer (RR Lyr's set:
up to 140 s at "measuring 0/N", with no cancel, on a laptop on the Seestar's own
Wi-Fi): each cone now gives up after 5 s, after the first failure the other stars are
read from the cache only, and the lookup takes the run's cancel (checked between
stars; a cancelled run measures no frame); the web job shows "proper motions (Gaia
DR3)" meanwhile. The separation behind the Gaia match (and the identity merge, S79's
crowding) took the raw RA difference: two stars 7" apart across RA 0h were 1.3e6"
apart; it is now taken across 0h.
**How to check.** `tests/core/test_targets.py::test_a_vsx_target_takes_its_gaia_proper_motion_and_moves_to_the_frame_date_s77`,
`::test_a_comparison_matches_its_gaia_source_by_brightness_when_vsp_is_off_s77`,
`::test_proper_motion_fields_round_trip_and_stay_out_when_unknown_s77`,
`tests/core/test_gaia.py::test_gaia_rows_carry_proper_motions_and_old_caches_still_serve_offline_s77`,
`tests/workers/test_photometry_batch_worker.py::test_a_re_run_places_a_high_proper_motion_target_at_the_frames_date_s77`
(3.0 px off on the code before),
`tests/workers/test_acquisition_engine.py::test_the_live_path_measures_a_star_at_the_frames_date_s77`
(the live hunk had no test), the amendment's `tests/core/test_gaia.py::test_a_set_lookup_stops_asking_the_archive_after_a_failure_s77`,
`tests/workers/test_photometry_batch_worker.py::test_a_cancel_during_the_proper_motion_lookup_ends_the_run_before_frame_1_s77`,
`tests/core/test_targets.py::test_crowding_and_the_gaia_match_see_across_ra_0h_s77_s79`
(each fails before the amendment); web `tests/server/test_geometry_s77_s80.py`
(`::test_the_re_run_port_moves_the_target_and_gives_each_star_its_airmass_s77_s78`,
the same bytes as Qt's worker; `::test_a_gaia_answer_gives_the_set_its_proper_motions_s77`),
`tests/server/test_photometry.py::test_the_live_port_measures_a_star_at_the_frames_date_s77`,
`tests/server/test_rerun.py::test_a_cancel_during_the_proper_motion_lookup_ends_the_run_s77`.
**Check your old files.** Points measured before: the aperture sat as far from a
star as its motion since 2000 (RR Lyr 1 px); a batch re-run measures them at
their date. The magnitudes barely change (above).

### S79 — A comparison beside a brighter star of the set is named

**What was wrong.** XX Cyg 2026-09-07 `040723Z`'s set paired the check star
000-BJV-169 with the comparison 000-BJV-173, 1.47 mag fainter, 50.6" (6.8 green
px) away, inside 169's 5.45 px aperture and with 1 % of 169's light in its own
(S69): nothing said so.
**Who was affected.** Sets with close pairs; one of the owner's (`040723Z`).
**What changed.** A comparison or check star with a brighter star of the set (by
catalogue V, else the first band both hold), or one of unknown brightness (a
variable), within 2 aperture radii (the series FWHM's aperture, at the profile's
green-plane scale: 81.5" on `040723Z`) is crowded (`crowded_stars`). Qt's
Comparison stars tab names it in the warning colour, with a WARN "Comparison
crowded — 000-BJV-173: 000-BJV-169 (1.47 mag brighter in V) is 50.6" away, within
2 aperture radii (81.5"): its light reaches this star's aperture or sky annulus
(S79)." once per star; the web server's targets record carries `crowded` and
`crowding`, which the Field band shows under its note line, and logs the same WARN
once per newly crowded star (technical review: the server logged none). Nothing is
removed: the observer decides. The study sets: `040723Z` (and the sets sharing its
stars) 000-BJV-173 by 000-BJV-169; XX Cyg 2026-08-29 `053540Z`'s set 000-BJV-173 (by
000-BJV-169) and 000-BJV-180 (by 000-BJV-173, 2.40 mag brighter, 59.6"; validation
F7, the core's list and an independent one agree on all 20 study sets); none on RR
Lyr. Across RA 0h the separation is taken modulo 360° (S77's amendment).
**How to check.** `tests/core/test_targets.py::test_a_comparison_beside_a_brighter_star_of_the_set_is_crowded_s79`,
`::test_a_comparison_beside_the_variable_is_crowded_s79`,
`tests/ui/test_crowding_s79.py::test_the_comparison_tab_and_the_log_name_a_crowded_comparison_s79`;
web `tests/server/test_geometry_s77_s80.py::test_the_target_record_names_a_crowded_comparison_s79`
(and its one WARN), `web/src/lib/imaging/field/field.test.ts` ("S79 crowded comparison").

### S80 — The tracker rejects every inconsistent anchor

**What was wrong.** The tracker's fit dropped one anchor at most (the residual
clip). With two wrong locks a second one moved every aperture: XX Cyg 2026-09-07
`040723Z` sub `_00020` (the live path, one solve per run, the anchors of before
S69's neighbour rule): an anchor on its neighbour (000-BJV-173 on 000-BJV-169) and
one on noise (000-BCK-501); every comparison off-centre, no target point. On a
synthetic field with two wrong anchors of six the fit turned 0.255° where the
field turned 0.7°, the good stars' apertures 1.61 px off.
**What changed.** A rigid motion keeps distances: before the fit, an anchor is
kept only when its separations from at least max(1, (n − 1) // 2) of the other
matched anchors are the solution's within 1.5 green px, and rejected otherwise
(`consistent_pairs`, the web overlay tracker's rule since wave 4, now the core's); two anchors that disagree
are both dropped (nothing tells which one is wrong); the residual clip follows.
Every rejected anchor leaves the S56/S58 count (`rejected_anchors`); the re-run's
recorder counts them (`anchors_inconsistent`). The web overlay tracker
(`field_track.py`) takes the core's rule and its converged centroid (S69), and
S69's neighbour rule for its anchors.
**Evidence.** The replay of `040723Z` with S69's neighbour rule off: sub `_00020`
had no target point before; now 000-BJV-173 and 000-BCK-501 are rejected and the
target point lies 0.07 px from the star (`s80_x07_sub20.json`). With the current
anchors no frame of the study runs has two wrong anchors (the counts below). The
web overlay tracker on `040723Z` from frame 0's solution, no re-solve: 0.315° of
lag at most and 1.29 px of fit error before, 0.074° and 0.18 px after
(`field_track_lag_X07.json`).
**How to check.** `tests/core/test_photometry_tracking.py::test_two_wrong_anchors_are_both_rejected_s80`
(6 anchors used and 0.255° of rotation on the code before),
`::test_consistent_pairs_keeps_a_rigid_constellation_s80`; web
`tests/server/test_geometry_s77_s80.py::test_the_overlay_tracker_keeps_up_with_a_field_rotating_0_7_deg_per_sub`
(two passes on the code before).

### S85 — A live target point below SNR 3 is flagged when it is measured

**What was wrong.** S67 flags a target measured below SNR 3 (no detection: cloud over
it, or a field that moved) in Review, the AAVSO export and a batch re-run, but the
live and sequence paths still wrote that point unflagged when they measured it: in
the live CSV, the live curve and the curve's `sigma_syst` (every row's `mag_err`).
S35 and S48 skip a frame only when the anchors show no star; a target hidden alone,
or a frame whose lock still holds, is measured. Found by S76's validation: replaying
the Qt sequence path on the cloudy XX Cyg 2026-09-07 `045626Z` with a solve every
20 s, its third sub, a lost lock before S76, is measured on one anchor through its
own solution (verified, S56: 0.18 px of tracker motion) with the target at SNR 0.85,
12.767 ± 1.279, unflagged.
**Who was affected.** Live and sequence runs whose target drops below SNR 3 on a
frame the lock survives. Replaying the Qt sequence path on the 8 study runs (Argos's
own solves, a solve every 20 s and one per run, before = the release at `964528d`):
two target points, both now flagged, nothing else changed: `045626Z` sub 3 (above;
with one solve per run that sub's lock is lost, S48, and it has no point, as before) and
XX Cyg 2026-09-07 `040723Z` frame 20 (SNR 1.85, 12.948 ± 0.588 among 11.68-12.55,
S67's frame), whose point had raised the live target's `sigma_syst` to 0.0770 (one
solve per run) and 0.0804 (every 20 s); it is 0 without it, as in the re-run since
S76. RR Lyr 2026-09-25 (193 points, frames 52 and 175 skipped by S35 and S48 as
before), the five other XX Cyg runs and S56's cases (the 500 px jump with and
without the anchor-frame rule, RR Lyr frames 0-39 with the set change, with and
without S52) give the same points and flags.
**What changed.** The owner's option (a) of 2026-11-16, no new threshold: the core
review's `flag_no_detection` applies S67's per-target rule to a point when it is
measured (`review.NO_DETECTION_SNR`, the threshold `no_detection_flags` reads through
`below_detection`): a target below SNR 3 has its point flagged `suspect` and
`no_detection` (kept in the curve and its CSV, the CSV's `suspect` column, left out
of the AAVSO export and named "suspect (no detection)" there); the curve's
`sigma_syst` is estimated without it and still added to its own error; the flight
recorder gets a `no_detection` event naming the targets (`low_snr`), as a re-run
records it. Only that target's own point: a second, bright target, the comparisons
and the check keep theirs (S67's option b). S67's other half, a zero point more
than 1 mag from the run's median, needs the run and stays with Review and the
re-run. `AcquisitionEngine._emit_live_point` and `_apply_systematic_floor` (live
preview and sequence subs alike). The target's flag is now the re-run's (the Qt
batch re-run of the same clone): on `040723Z` every CSV's `suspect` column (9 stars,
24 frames) and the target's `sigma_syst` (0) are the re-run's; on `045626Z` the live
target CSV's column reads 0, 0, 1 like the re-run's (0, 0, 0 before), and the re-run
also flags that sub's comparisons, by S43 (its re-solve of the cloudy sub failed),
where the live path measured it through Argos's own solution of it. The web server's
port is the same code (`photometry.py`, GUARD until the merge) and gives the same
points as the fixed Qt in one process, with no difference: the 16 replays above and
the RR Lyr set change, 3787 points field by field, the CSVs byte for byte, the two
points above flagged on both sides with the same `sigma_syst`.
**How to check.** `tests/workers/test_acquisition_engine.py::test_a_live_target_below_snr_3_is_flagged_no_detection_s85`
(a faint second target at SNR 1.94 and a bright one on one frame: the faint one's
point unflagged on the code before the fix),
`::test_a_point_without_a_detection_sets_no_live_sigma_syst_s85` (the point
unflagged on the code before; with only the floor's hunk reverted, the floor 0.0137
with the point instead of 0.0014 without),
`tests/core/test_session_old_file_rules.py::test_the_live_rule_is_s67s_per_target_rule_s85`
(the live rule and `no_detection_flags` flag the same targets), and
`::test_review_reads_a_live_csv_flagged_at_measurement_unchanged` (Review keeps such
a file's flags and floor; a non-regression test, it passes on the code before); web `tests/server/test_photometry.py::test_a_live_target_below_snr_3_is_flagged_no_detection_s85`
and `::test_live_no_detection_flags_and_floor_are_the_qt_engines_s85` (GUARD: they
run once the release core is merged).
**Check your old files.** As S67: Review, Analyze's **Open curve CSV** and the
export already leave those rows out of a live CSV and recompute its `sigma_syst`
from the run's flight recorder; a re-run flags them.

## Review and AAVSO export

### S53 — The AAVSO export refuses curves of two filters

**What was wrong.** Since S49 a run through two filters keeps one curve per
(star, filter). The AAVSO export took every target curve with points under the
one `FILT` code of Settings (`photometry.default_band`), and `KMAG` from the
first check curve whatever its filter: a two-filter run reported as one band.
**Who was affected.** AAVSO exports of a run or live preview through two
filters. None of the owner's (one filter per run).
**What changed.** When the target and check curves span two filters or more,
the export says so ("These curves are in 2 filters (ir, lp), and an AAVSO
report has one band. Open one filter's target CSV in Analyze
(target_<object>_<filter>_<star>.csv) and export it from there.") and writes
nothing. A one-filter export is unchanged.
**How to check.** `tests/ui/test_photometry_window.py::test_aavso_export_refuses_curves_of_two_filters_s53`
(a two-row file under one `FILT` on the code before the fix).

### S60 — The AAVSO export leaves undated points out

**What was wrong.** Before S13 a batch re-run dated a frame without `DATE-OBS` at
JD 0 (`jd_utc = jd or 0.0`). S13 stopped writing such points, but the CSVs
written before still open in Analyze (**Open curve CSV…**), and **Export AAVSO**
wrote their rows with `DATE` `0.000000`, an observation in 4713 BC; a `nan`
date was written as `nan`.
**Who was affected.** AAVSO reports exported from a 0.4.x batch re-run's CSV
that held a frame without `DATE-OBS` (third-party `*.fits` frames: S12 kept the
0.4.x re-run from finding Argos's own `.fit` frames). None of the owner's.
**What changed.** `write_aavso` leaves out a point whose `jd_utc` is not finite
or is before JD 2 400 000 (1858, `MIN_AAVSO_JD`), whatever its flags, and counts
it (`AavsoExportSummary.undated_excluded`); the export's message lists them
("Left out: 1 undated (JD 0) point(s)."). Dated points are written as before,
byte for byte.
**How to check.** `tests/core/test_photometry_core.py::test_aavso_export_leaves_out_undated_points_s60`
(rows dated `0.000000` and `nan` on the code before the fix) and
`tests/ui/test_photometry_window.py::test_aavso_export_reports_undated_points_left_out_s60`.
In an AAVSO report you sent, look for a `DATE` field `0.000000` or `nan`.

### S64 — The AAVSO report names the software's version

**What was wrong.** Every AAVSO report began with `#SOFTWARE=Argos`. The AAVSO
Extended File Format asks for the name *and version* of the software that wrote
the file (`#SOFTWARE=` "Name and version of software used to create the
format"); a report could not say which Argos, with which fixes, produced it.
Found by the web UI's wave 7 science review, checking the files field by field.
**Who was affected.** Every AAVSO report. The header line only: no observation,
magnitude, date or airmass changes.
**What changed.** `write_aavso` stamps `argos.SOFTWARE_ID` (`Argos v<version>`,
the string already written into the FITS `SWCREATE`/`CREATOR` headers) unless a
caller passes `software=`. Analyze's **Export AAVSO** and the web server's
export call it the same way, so their files stay byte for byte the same.
**How to check.** `tests/core/test_photometry_core.py::test_aavso_header_names_the_software_and_its_version_s64`
(`#SOFTWARE=Argos` on the code before the fix). Old reports: the line is only
informative; nothing to correct.

### S66 — Review, Analyze and the batch re-run take the mount's airmass

**What was wrong.** X3 warns when the Settings site is not where the telescope
is, but a run already recorded with such a site keeps the airmass computed for
it in its curve CSVs, and Review, Analyze's **Open curve CSV** and **Export
AAVSO** wrote it as `AMASS`. A batch re-run computed every point's airmass for
the Settings site of the day without checking it either, and within X3's 5°
tolerance a site still errs: a re-run of XX Cyg 2026-08-29 `050148Z` with that
night's Settings site wrote an airmass 0.013-0.015 too high at 67-71° of
altitude. Found by the web UI's wave 7 science review, checking `AMASS` against
astropy.
**Who was affected.** Reports and plots of runs made with a wrong Settings site,
and batch re-runs. One of the owner's runs: RR Lyr 2026-09-25 (`200453Z`), whose
Settings site lies 86° of direction from where the mount pointed: `AMASS` ran
from 4.088 to 1.514 while the airmass was 1.033 to 1.364 (astropy at
mid-exposure, at the site fitted to the frames' `ALTITUDE`/`AZIMUTH`).
**What changed (the owner's option b).** Every point's airmass is the header
`AIRMASS` (the mount's) of the Argos light whose mid-exposure (`DATE-OBS` +
`EXPTIME`/2) is nearest, within 5 s, whatever the Settings site. A point without
one keeps the airmass the run computed for the Settings site: no light within
5 s, a light without `AIRMASS` or not written by Argos, or a light whose pointing
is frozen. A frozen pointing (X1, 0.3.0-0.4.2: a lost mount's last poll kept in
every later frame) is one whose `RA`, `DEC`, `ALTITUDE`, `AZIMUTH` and `AIRMASS`
are all those of a light a minute or more before: its `AIRMASS` is stale, and
its direction drifts from the computed one by about 0.2° per minute, so half an
hour after the freeze a right site looked wrong (science and technical reviews:
RR Lyr headers frozen from frame 30 gave 165 of 195 points the stale value, up
to 0.33 from astropy). The site check (X3 on the run's non-frozen lights, the median over
5°) stays as a Review warning, which counts the points left with the computed
airmass. Analyze's **Open curve CSV** does the same on a run's own CSV
(`<session>/photometry/`); a batch re-run's CSV and a preview curve are read as
written. The batch re-run takes each frame's header `AIRMASS` the same way,
counts the frames (`frames_header_airmass`) and, when a frame's header says the
Settings site in use is more than 5° off, says so once (`frames_site_wrong`).
Nothing is rewritten in the session. The web server's Review, exports and
re-run call the same code and write the same bytes. The header `AIRMASS` is the
field centre's, the target's: a check or comparison star off-centre takes the
same value (RR Lyr: check 000-BCG-523 within 0.0071 of its own airmass; an owner
decision is open).
**Evidence.** Review's target airmass against astropy at the fitted site: RR
Lyr 2026-09-25 within 0.00035 over 195 points (the CSV as written: 0.15-3.05
off); XX Cyg 2026-09-07 `040723Z` 0.00044 and 2026-08-29 `050148Z` 0.00009
(their CSVs, from the live path: 0.0004 and 0.0001; the header's own accuracy).
The AAVSO report of RR Lyr from Review or from the target CSV: `AMASS` 1.033 on
its first row, 1.033-1.364 over its 193 rows, at most 0.00074 from astropy with
the 3-decimal rounding. Batch re-runs with each night's Settings site: the
header `AIRMASS` on 195 of 195, 24 of 24 and 22 of 22 frames, the target's
airmass within 0.0003, 0.0004 and 0.0001 of astropy (`050148Z`: 0.013-0.015
before); the RR Lyr re-run warns of the wrong site.
**Check your old files.** Reports already exported from such a run: see X3 above
(take the header `AIRMASS`); exporting again from Review or Analyze now does it.
**How to check.** `tests/core/test_session_old_file_rules.py` (the `s66` tests;
`::test_review_takes_the_header_airmass_when_the_site_was_right_too_s66`,
`::test_a_point_without_a_frame_keeps_its_computed_airmass_s66` and
`::test_a_frozen_light_keeps_its_computed_airmass_on_a_wrong_site_s66` fail on
the code before the owner's option; `ARGOS_S66_SESSION=<copy of the RR Lyr
session>` checks `AMASS` 1.033 on row 1, 4.088 before),
`tests/workers/test_photometry_batch_worker.py::test_a_re_run_takes_the_header_airmass_when_the_site_is_wrong_s66`,
`::test_a_re_run_takes_the_header_airmass_when_the_site_is_right_too_s66`,
`::test_a_re_run_computes_the_airmass_of_frozen_frames_at_a_right_site_s66`
and `tests/ui/test_photometry_window.py::test_open_curve_csv_of_an_older_run_applies_the_old_file_rules_s66_s67`.

### S78 — A comparison or check star takes its own airmass

**What was wrong.** Since S66 every point of a run took its frame's header
`AIRMASS`, the mount's: the field centre's, the target's. A comparison or check
star 1-2° away took it too (an owner decision left open by S66): Review's
comparison curves of RR Lyr 2026-09-25 lay up to 0.020 from their own airmass
(astropy at the site fitted to the frames' pointing), XX Cyg 2026-09-07
`040723Z`'s up to 0.0069, 2026-08-29 `050148Z`'s up to 0.0006; the check star
000-BCG-523 up to 0.0071. The live path computed each star's own, but for the
Settings site, wrong on RR Lyr (X3).
**Who was affected.** The `airmass` column of comparison and check curves (CSV,
Review, re-runs); the AAVSO `AMASS` is the target's and does not change.
**What changed.** The target keeps the frame's header `AIRMASS` (S66). Every other
star's airmass is computed (`airmass_at`, its own position, at mid-exposure) for
the site fitted to the mount's pointing: Review and Analyze fit it to the run's
Argos lights' `RA`/`DEC`/`ALTITUDE`/`AZIMUTH` at `DATE-OBS` (frozen pointings, X1,
left out), the batch re-run to its frames' headers, the live path to the mount's
polls of the measured frames (every star, the target included: within 0.0005 of
the header). The fit (`SiteFit`, Gauss-Newton on latitude and longitude from a
10° × 15° grid, the same fast spherical trig as the airmass) needs 3 pointings
over 10 minutes (one direction has two solutions) and an rms under 0.1°; without
one, the Settings site (Review: the one the lights recorded). The core fit lies
0.4-0.8 km from an astropy fit of the same headers; the owner's runs fit with an
rms of 0.0016-0.0046°. Review's site warning says so (S78). The web server calls
the same code.
**Evidence (Review, comparison curves against astropy at the astropy-fitted
site, max |Δ| over all their points).** RR Lyr 2026-09-25 (1090 points): 0.0204
→ 0.00007; XX Cyg 2026-09-07 `040723Z` (190): 0.0069 → 0.00005; 2026-08-29
`050148Z` (93): 0.0006 → 0.00005; the targets unchanged (0.00035, 0.00044,
0.00009) (`s78_review_before.json`, `s78_review_snap2.json`). Qt batch re-runs of
the same runs (each night's Settings site): 0.0204, 0.0069, 0.0006 → 0.00007,
0.00005, 0.00005 over 1095, 192 and 96 comparison points (`s78_rerun_*.json`).
**Amended (the owner's call of 2026-11-16 on the validation's F1).** Without a
fitted site the comparisons fell back to the Settings site even when S66's check
rejects it: RR Lyr 2026-09-25 `195307Z` (5 lights over 6 minutes, the night's
Settings site 89° off) gave them 4.0-4.9 where astropy at the fitted site gives
1.025-1.034, and XX Cyg 2026-08-29 `052943Z`/`053540Z` (the Settings site 2.0° off,
within S66's 5° warning tolerance) 0.0129/0.0126 off where the header `AIRMASS` is
0.0012 off. The Settings site now gives a star its own airmass only when it
reproduces the mount's pointing as closely as a fitted site must: the median S66
offset of the run's lights (frozen ones left out) within 0.1°
(`settings_site_reproduces`, `STAR_SITE_MAX_OFFSET_DEG` = `SITE_FIT_MAX_RMS_DEG`);
else every star keeps its frame's header `AIRMASS`, the field centre's, as before
S78 (a 2° site error moves a comparison's airmass ten times more than its distance
from the centre does). The live path does the same per poll (the mount's airmass
for every star until a site is fitted, when the Settings site is more than 0.1° off
the mount's direction), and no longer adds to the fit a pointing that repeats the
last one (a lost mount's frozen poll, X1: added, it left no site within 0.1° for the
rest of the night; technical review) nor, in the web server, a slewing mount's. Every
study run lies 2.0-2.4° (XX Cyg) or 86-127° (RR Lyr) from its Settings site
(`site_offsets.json`): without a fit, the header. Comparison airmass against astropy
at the fitted site, max |Δ|, batch re-runs before → after (fixer `compare_validation_vs_fixer.json`):
`195307Z` 3.854 → 0.0017; `052943Z` 0.0129 → 0.0012; `053540Z` 0.0126 → 0.0012;
XX Cyg 2026-09-07 `045156Z`/`045626Z` 0.0078/0.0084 → 0.0069 (the header's: their
comparisons lie up to 1° from the centre at airmass 1.5); the runs with a fitted
site unchanged (RR Lyr 0.00007, `040723Z`, `050148Z` 0.00005). Review of the same
runs: the comparisons' points matched to a light within 0.0017 (`195307Z`) and
0.0012 (`052943Z`, `053540Z`); `195307Z`'s CSVs also hold points of no light within
5 s (2 per star), which keep the run's computed airmass for every star, the target
included, as S66 says and warns.
**How to check.** `tests/core/test_session_old_file_rules.py::test_a_comparison_off_the_field_centre_takes_its_own_airmass_s78`,
`::test_without_a_fitted_site_a_wrong_settings_site_gives_no_comparison_its_airmass_s78`
(60° and 2° off: the wrong site's airmass on the code before the amendment),
`tests/workers/test_photometry_batch_worker.py::test_a_short_re_run_at_a_wrong_site_gives_comparisons_the_header_airmass_s78`
(the same, re-run), `::test_a_short_re_run_at_a_right_site_gives_comparisons_their_own_airmass_s78`,
`tests/workers/test_acquisition_engine.py::test_a_frozen_mount_pointing_keeps_the_live_site_fit_s78`
(the Settings site's 1.5 on the code before the amendment), web
`tests/server/test_geometry_s77_s80.py::test_a_short_re_run_at_a_wrong_site_keeps_the_header_airmass_s78`
(the same bytes as Qt), `tests/server/test_photometry.py::test_the_live_port_takes_the_site_fitted_to_the_mount_s78`;
`tests/core/test_session_old_file_rules.py::test_without_a_fitted_site_a_comparison_takes_the_settings_sites_airmass_s78`
(the header AIRMASS on the code before),
`tests/workers/test_photometry_batch_worker.py::test_a_re_run_takes_the_header_airmass_when_the_site_is_wrong_s66`
and `::…_right_too_s66` (the comparisons' own airmass now),
`tests/workers/test_acquisition_engine.py::test_live_points_take_the_airmass_of_the_site_fitted_to_the_mount_s78`
(the Settings site's 1.5 on the code before; the first points, before a fit, the
mount's since the amendment); web
`tests/server/test_geometry_s77_s80.py::test_the_re_run_port_moves_the_target_and_gives_each_star_its_airmass_s77_s78`.
**Check your old files.** A comparison or check curve's airmass: Review now shows
its own; files are never rewritten.

### S81 — An aperture or sky annulus partly off the frame is not measured

**What was wrong.** `measure_aperture` clipped its box at the frame's edge and
measured what was left: a truncated aperture (up to 5 mag faint) or a truncated sky
annulus, and the row was written as a good point. RR Lyr 2026-09-25 `200453Z`, 6
comparisons (found by the noise role, confirmed by the validation and the science
review, each with its own scan): 000-BJW-667 frame 130 (1.5 px from the edge)
+0.08-0.10 mag, frame 131 (y = −2.4) +4.95-4.98 mag at SNR 3; 000-BJW-668 frame 181
(0.6 px) +0.28-0.33 mag at SNR 61, frame 182 +5.2 mag; rows whose annulus alone
ran off (4-11 px from the edge) +0.014 to +0.061 mag, all with `suspect` 0. S71's
clip kept them out of the target's ensemble; the comparison CSVs carried them.
**Who was affected.** Rows of stars within the annulus' outer radius (12 green px)
of an edge: comparison and check curves and their leave-one-out vetting, a target
there, and the anchors and stars-seen counts (S43, S48) that took such stars.
**What changed.** `measure_aperture` measures nothing unless every pixel centre
within the annulus' outer radius lies on the frame (`_annulus_on_frame`); every
caller already reads None as "off the frame": no point, no anchor, not seen. The web
server calls the same code. (Synthetic test scenes with stars 10 px from the edge
of a 60 px plane gained a 4 px margin; their checks are unchanged.)
**Evidence.** RR Lyr `200453Z` 6-comparison re-run: 13 → 1 rows written whose
annulus reaches within 12.6 px of the edge (the one left, 11.9 px, has every annulus
pixel on the frame); the comparison points 1095 → 1083; the target unchanged (195
points); RR Lyr − Siril −0.0116 / 0.0145 → −0.0110 / 0.0147 (fixer `edge_rows_summary.txt`,
`compare_validation_vs_fixer.json`). No other study run had such a row.
**How to check.** `tests/core/test_photometry_core.py::test_an_aperture_or_annulus_off_the_frame_is_not_measured_s81`
(measured, truncated, on the code before).
**Check your old files.** A comparison or check row within 12 green px of the
frame's edge (the flight recorder's `star` records give its x, y) may be truncated;
a batch re-run leaves it out.

### S82 — A batch re-run reads an OBJECT written in SIMBAD's form

**What was wrong.** S62 keeps a frame whose `OBJECT` names the set's object,
compared without case, spaces or underscores. A light whose `OBJECT` is in SIMBAD's
form, "V* XX Cyg" (the owner's `20260829T034413Z_V_XX_Cyg`), was another object for
the "XX Cyg" set: 0 frames, and Qt refused the re-run ("No frames"; validation).
**Who was affected.** Re-runs of lights named from SIMBAD (prefixes `V*`, `*`, `**`,
`NAME`, `Cl*`, `EM*`); pre-existing since S62.
**What changed.** The comparison drops SIMBAD's identifier prefixes
(`_object_key`; the web server's `rerun.object_key`). `034413Z_V`: 0 → 1 frame for
the "XX Cyg" set, in both apps (fixer `s82_after.json`).
**How to check.** `tests/workers/test_photometry_batch_worker.py::test_discover_light_frames_reads_an_object_in_simbad_form_s82`
(no frame on the code before); web
`tests/server/test_rerun.py::test_a_frame_named_in_simbad_form_is_the_sets_object_s82`.
**Check your old files.** None: the re-run refused, nothing was written.

### S83 — Live and sequence photometry take the e-/ADU at the frame's own gain

**What was wrong.** The live and sequence paths took the e-/ADU at the Camera
form's gain, while the frame's `EGAIN` (S42) and a later re-run (S70) take the
frame's own. Since S73 the value depends on the gain (0.228 e-/ADU at 80, 0.181 at
100: 26 % apart), so a sequence step at gain 100 with the form at 80 was measured
with 0.228 (technical review).
**Who was affected.** Live and sequence points of frames taken at another gain
than the Camera form's: their SNR (the gates) and formal errors.
**What changed.** The engine keeps the gain of the frame in hand (a live frame's
settings, a sequence sub's record; an opened frame keeps its own e-/ADU) and the
chain takes it; the web server carries it (`Frame.gain`, `MeasureRequest.gain`;
the sequence passes its step's). The web server's S54 re-pointing check and pilot
comparison quality, which hold no frame gain, keep the form's (Qt's take the frame
in hand's): they differ only when a step's gain differs from the form's.
**How to check.** `tests/workers/test_acquisition_engine.py::test_a_sequence_sub_is_measured_at_its_own_gains_egain_s83`
(0.228 on the code before); web `tests/server/test_sequence.py::test_a_sub_is_measured_at_its_steps_gain_s83`,
`tests/server/test_photometry.py::test_the_live_port_takes_the_egain_at_the_frames_own_gain_s83`.
**Check your old files.** Points of a step at another gain than the form's: their
errors used the form's e-/ADU; a batch re-run uses each frame's own (S70).

### S67 — Review, the AAVSO export and the batch re-run leave out the points without a detection

**What was wrong.** S35 stops new runs measuring blank sky, but the rows written
before keep no flag: Review plotted them, **Export AAVSO** wrote them, and the
run-level `sigma_syst` estimated with them raised `mag_err` (`MERR`) on every row.
"Check your old files" asked the observer to drop them by hand.
**Who was affected.** Reports exported from runs that measured such frames. Two
of the owner's runs: RR Lyr 2026-09-25 (frames `_00053`, `_00176`) and XX Cyg
2026-09-07 `040723Z` (frame 20).
**What changed.** Review reads the run's flight recorder
(`diagnostics/<object>_live_diagnostics.jsonl`, S35's rule on old files): on a
frame where a target's ensemble zero point is more than 1 mag from its median
over the run (the field moved, or cloud), every star's point is flagged
`suspect`; a target measured below SNR 3 has its own points flagged (the owner's
option b: a faint variable at minimum no longer takes out a second, bright
target's points or the comparisons'). The AAVSO export
leaves it out and its message names it apart ("N suspect (no detection)"); a
check star's point there gives no `KMAG`. Each curve's `sigma_syst` (and every
row's `mag_err`) is estimated again without those points, with the same
estimator, when the file's floor is the automatic one of its own points; a manual
floor (`photometry.systematic_floor_mag`) does not depend on them and is kept, as
is the floor of a curve left with fewer than ten points. Analyze's **Open curve
CSV** on a run's own CSV does the same; the files are never rewritten. S56's
old-file rule (fewer than 3 anchors at SNR 10) drops nothing: it over-flags (see
"Check your old files"), and Review and the export preview point to a batch
re-run, which verifies those frames (S58). The batch re-run (science review)
applies the same rule to its own frames at the end of the run: those points are
flagged `suspect`, left out of the run's `sigma_syst` and of the AAVSO export of
its CSVs, counted (`frames_no_detection`) and recorded (a `no_detection` event
naming the targets below SNR 3). Before, a re-run wrote such a row unflagged:
`040723Z` frame `_00021`, target at SNR 1.6, 13.29 ± 0.75 among 11.7-12.2, in its
export. The web server applies the same code.
**Evidence.** RR Lyr 2026-09-25: frames 52 and 175 hold both rules (the target
below SNR 3 and the zero point more than 1 mag off): every point of them is
flagged; the report has 193 rows (2 left out, named); the target's `sigma_syst`
0.01657 → 0.01497, so every row's `MERR` shrinks. XX Cyg 2026-09-07 `040723Z`:
frame 20 has the target at SNR 1.6 and a normal zero point: its target point
only; 23 rows, target `sigma_syst` 0.2918 → 0.2365; a re-run flags the same
frame and its report has 23 rows. XX Cyg 2026-08-29 `050148Z`: no such frame,
22 rows.
**Check your old files.** As S35 above; exporting again from Review or Analyze
now leaves those rows out and recomputes `sigma_syst`.
**How to check.** `tests/core/test_session_old_file_rules.py` (the `s67` tests:
no flag and the larger floor on the code before the fix;
`::test_a_faint_target_flags_its_own_points_only_s67` fails on the frame-wide
rule), `tests/workers/test_photometry_batch_worker.py::test_a_re_run_flags_the_points_of_a_frame_without_a_detection_s67`
(two targets: only the faint one's point),
`tests/ui/test_photometry_window.py::test_aavso_export_names_points_without_a_detection_s67`.

### S68 — The AAVSO header and CHART: the VSP chart of older comparison sets

**What was wrong.** Since 0.4.2 a comparison picked from VSP keeps the answer's
chart, and the report names it in `CHART`; but a comparison picked before (0.4.1)
stays in the object's set (`<sessions>/targets/<object>.json`) without one, Argos
never adds one, and every run copies the set: `CHART` was na on every report of
those objects, new runs included. The owner's RR Lyr and XX Cyg sets are such
sets (no chart in any of the three study runs).
**Who was affected.** Reports of objects whose comparisons were picked before
0.4.2. Header field only: no observation changes.
**What changed.** When a VSP answer arrives, a comparison of VSP origin without a
chart takes the answer's chart if the answer lists its AUID with the same
catalogue magnitude in every band the set holds (a revised sequence keeps none),
in the object's set and in the running run's `targets.json`. New runs then write
`CHART`; runs already recorded keep na (nothing records their chart). The rest
of the header: `#SOFTWARE` names the version since S64, and the web server's
export writes the same bytes as Analyze's; `#OBSTYPE` stays `CCD`, the AAVSO
Extended File Format's code for a CMOS camera too (no change). The web server
names the chart the same way (`TargetService.backfill_chart_ids` since
2026-11-16; it was a function of `field.py` reaching into the service's lock and
save).
**Evidence.** Each of the owner's cached VSP answers for these fields lists all
6 RR Lyr, 8 and 5 XX Cyg comparisons with the magnitudes the sets hold: every
comparison gets that answer's chart.
**Check your old files.** `CHART` na in a report of an older run: the VSP chart
of the same field and sequence can be filled in by hand; the observations are
unaffected.
**How to check.** `tests/core/test_targets.py::test_comparisons_saved_without_a_chart_get_the_vsp_answer_s_s68`
and `tests/workers/test_acquisition_engine.py::test_a_vsp_answer_names_the_chart_of_comparisons_kept_without_one_s68`
(no chart on the code before the fix).

### S61 — Export measurements refuses curves of two filters

**What was wrong.** The multi-curve CSV of **Export measurements…**
(`write_curves_csv`) has no filter column. Since S49 a run through two filters
keeps one curve per (star, filter): both of a star's curves were written under
one `star_id` (its AUID), and read back (Analyze, Review) they became one curve
mixing both bands, the S49 defect again.
**Who was affected.** Exports of a run or live preview through two filters. None
of the owner's (one filter per run).
**What changed.** As the AAVSO export (S53), the export is refused when the
curves span two filters or more ("These curves are in 2 filters (b, v), and the
export has no filter column: …"); the run's `photometry/` folder holds one CSV
per star and filter. A one-filter export is unchanged.
**How to check.** `tests/ui/test_photometry_window.py::test_measurements_export_refuses_curves_of_two_filters_s61`
(one merged curve on reload on the code before the fix).

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
`OBJECT` (S62 adds it).
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

### S43 — A batch re-run re-solves a frame on which the field jumped

**What was wrong.** The batch re-run places every frame's apertures through
one solution (the solve made before the re-run) moved by the aperture tracker,
which re-centroids its anchor stars within 15 green px of where it last saw
them. When the field jumped further than that between two frames, the windows
found no star, or centroided noise or a neighbour and still reported anchors;
the tracker kept its old transform and every later frame was measured where
the stars no longer were. Nothing noticed: no flag on the points, and the
end-of-run message said "Apertures tracked the field". The batch also kept the
fallback S35 removed from the live path (every star of the set as an anchor,
seen or not). Replayed on RR Lyr 2026-09-25, frames 0–79 through frame 0's
solve (the field jumped 22.8 green px at frame 52): of the 28 frames from 52
on, 9 got unflagged target points measured 21–127 px from the star (5.58 to
10.51 mag; the star is at 7.43–7.55 on those frames), 19 got no point, and the
summary reported 309 px of drift "tracked". Which frames fail depends on
sub-pixel details: with another valid solve of frame 0, 0.6 px away, it was 7
points (21–114 px off) and 21 frames without one.
**Who was affected.** A re-run of frames across a pointing jump, a slew or a
meridian flip larger than the tracker's search radius. In 0.4.2 only folders of
`*.fits` frames from other software (S12); the release branch's re-run of an
Argos session before this fix. None of the owner's files: no session holds a
`photometry_rerun_*` folder.
**What changed.** Each frame's lock is checked independently of the tracker:
at least half of its anchor stars must show a star (SNR ≥ 5) where the tracked
solution places them. On a frame where the lock is lost, the re-run plate-solves
that frame with ASTAP (the configured solver, about 0.3 s, near the reference
solve's centre, no whole-sky retry), rebuilds the tracker on the new solution and
measures the frame there. Until a solve re-anchors the apertures (no ASTAP, or
the frame does not solve, clouds), the points are written flagged `suspect`
(left out of the AAVSO export, of the run's `sigma_syst` and of the check-star
RMS), and the end of the run says how many frames were re-solved and how many
were measured without the field, never "tracked" when the field was lost. The
anchor fallback is S35's (stars of the set seen where the solution places
them). On the same replay all 80 frames get a point on the star (0.3–0.8 px from
the star on frames 52–79: each frame's own ASTAP solution, RR Lyr moved by its
proper motion), with one re-solve at frame 52; frames 0–51
keep their magnitudes and apertures, and their `mag_err` shrinks because the
blank-sky points no longer raise the run's `sigma_syst` (target, frame 0:
0.0147 → 0.0140). Over the whole run (195 frames, second jump of 140 px at
frame 175): two re-solves, every target point on the star (median 0.58 px,
1.46 px at most, on the jump frame), against 74 off-star target points
and 62 frames without one before the fix (`notes/tracker_comparison.md` on the
web-UI branch). The XX Cyg runs of 2026-08-29 and 2026-09-07 (7 runs, 62
frames, field rotation up to 16°) lose no frame and re-solve none. The web UI
has no batch re-run yet; its Review re-run must carry the same rule.
**How to check.**
`tests/workers/test_photometry_batch_worker.py::test_batch_re_solves_a_frame_on_which_the_field_jumped`
(a synthetic jump of 28.6 px, a stubbed solver: 7 points, some on blank sky, on
the code before the fix),
`::test_batch_flags_points_until_the_field_is_re_anchored` (unflagged post-jump
points before the fix) and
`tests/ui/test_batch_rerun.py::test_batch_summary_never_says_tracked_when_the_field_was_lost`.
On a copy of the RR Lyr session with ASTAP installed,
`ARGOS_S43_SESSION=<copy> pytest -k real_rr_lyr` checks every target aperture of
frames 48–79 against that frame's own ASTAP solve (skipped otherwise).
With fewer than 3 anchors this check verifies nothing: S58.

### S58 — A batch re-run verifies a lock on fewer than 3 anchors near a fresh solution

**What was wrong.** S43's lock check needs ceil(n/2) of the n anchors to show a
star where the tracked solution puts them. With 1 or 2 anchors the anchor that
moved the apertures is seen by construction (S56 in the live path): a re-run of
such a field measured every frame through the reference solve, never verified.
**Who was affected.** A re-run of a field whose comparisons give fewer than 3
anchors. None of the owner's files (no session holds a `photometry_rerun_*`
folder). Re-running XX Cyg 2026-08-29 `050148Z` (2 anchors) through frame 0's
solve: 22 unflagged target points, 4 of them 2.5-4.5 px off the star (frames 13,
15, 16, 17; an independent solve of each frame).
**What changed.** The live path's rule (S56): a frame steered by 1 or 2 anchors
is verified only when it is measured through a solution of this frame or the
previous one in the series and the tracker moved no aperture of the set 2 px or
more from where that solution puts it. The reference solve given to the re-run
is of no frame of the series. An unverified frame is re-solved at once with the
configured solver (as S43 does on a lost lock), the tracker rebuilt on that
solution, and verified there; without a solver, or when it does not verify, its
points are flagged `suspect` (left out of the AAVSO export, of the run's
`sigma_syst` and of the check-star RMS). The end of the run says how many frames
were re-solved to verify their lock and how many were left unverified (WARN
"Batch photometry: N frame(s) steered by fewer than 3 anchor stars had no
verified lock …"). On `050148Z` with Argos's own solves as the solver: 12
re-solves (every other frame; the one between uses the previous frame's), no
point flagged, every target point within 1.89 px of the star (4.45 px at worst
before). Without a solver: all 22 flagged. `052943Z` (2 anchors, 4 frames): 2
re-solves, none flagged, 0.59 px at worst (0.93 before). The runs with 3 anchors
or more (`053540Z`, 2026-09-07 `040723Z`) give the same points and flags as
before, with or without a solver. The web server has no batch re-run.
**How to check.**
`tests/workers/test_photometry_batch_worker.py::test_a_re_run_flags_a_lock_on_two_anchors_without_a_fresh_solution_s58`
(the points unflagged on the code before the fix) and
`::test_a_re_run_verifies_two_anchors_on_a_fresh_solution_s58` (a solver called
on frames 0, 2 and 4, no point flagged; after a jump onto a neighbour the frame is
re-solved, never measured on blank sky; no re-solve on the code before the fix)
and `tests/ui/test_batch_rerun.py::test_batch_summary_says_how_many_frames_had_no_verified_lock_s58`
("Apertures tracked the field" on the code before the fix).

### S62 — A batch re-run measures the target set's object only

**What was wrong.** S12 left out calibration frames by `IMAGETYP` but kept every
light frame of the chosen folder, searched recursively when it holds no FITS
itself. A folder holding two objects' frames, or the sessions folder, was
measured whole against one target set: another field's frames gave points on
blank sky (or on whatever star sat at those coordinates).
**Who was affected.** Re-runs pointed at a folder above one session. None of the
owner's runs was re-run.
**What changed.** A light frame whose `OBJECT` names another object than the
target set's is left out (compared without case, spaces or underscores: `XX_Cyg`
is `XX Cyg`); a frame without `OBJECT` is kept, as before. "No frames" now names
the object ("No light frames (.fit/.fits/.fts) of XX Cyg in …").
**How to check.** `tests/workers/test_photometry_batch_worker.py::test_discover_light_frames_keeps_the_object_s62`
(the other object's frame listed on the code before the fix).

### S63 — A batch re-run of a session measures its lights only

**What was wrong.** S12 searches the chosen folder's subfolders when it holds no
FITS itself, and took every FITS it found. A session folder in which another
program ran keeps that program's files beside `lights/`: star_var_script's Siril
`process/` holds a link to every light (`light_00001.fit` →
`lights/…_00001.fit`) and a registered copy (`r_light_00001.fit`), both with the
light's `IMAGETYP`, `OBJECT` and `DATE-OBS`. The owner's RR Lyr 2026-09-25
folder gave 585 frames for 195 lights: every epoch measured three times (twice
on the same pixels, once on Siril's resampled copy), three points per date in
each curve.
**Who was affected.** Batch re-runs of a session folder that another program
wrote into. None of the owner's runs was re-run; RR Lyr 2026-09-25 would have
been.
**What changed.** In the subfolder search, the frames of an Argos session folder
(one holding `session.json` and `lights/`) are those of its `lights/`, and a
link to a frame already listed is that frame (each file once, by its resolved
path). A folder that holds FITS itself is read as before; a folder without
`session.json` still gives every FITS below it, each file once.
**How to check.** `tests/workers/test_photometry_batch_worker.py::test_discover_light_frames_measures_a_session_s_lights_only_s63`
(the link and the registered copy listed on the code before the fix). In a
re-run's CSV, look for two or three rows with the same `jd_utc`.

### S70 — A batch re-run's tracker uses each frame's own gain

**What was wrong.** Since S41 each frame's errors use its own e-/ADU (its
`EGAIN`, or the gain table at its `GAIN`), but the batch re-run chose the
tracker's anchors (SNR ≥ 10) and ran the S43 lock check (SNR ≥ 5) with the
request's e-/ADU, the one Settings gives for the Camera form. XX Cyg 2026-09-07
`040723Z` (frames' `EGAIN` 1.723, request 0.8): 5 anchors where the frames'
own SNR gives 6.
**Who was affected.** A re-run of frames whose `EGAIN` differs from the
Camera form's (0.4.1 frames re-run under 0.4.2, or the reverse). None of the
owner's files (no session holds a `photometry_rerun_*` folder).
**What changed.** The frame's params (its own e-/ADU) are built before the
tracker is updated and used for the anchors, both lock checks (S43, S58) and
the measurement. Applied with S69 only: alone it made `040723Z` worse, the
sixth anchor (000-BCK-396, 370 px from the centre) following the lagging fit
(apertures 8.5 px off at the end instead of 4.5 px; tracker −15.37° instead of
−16.02°, ASTAP −16.49°). With S69 (root cause, above): apertures within 0.2 px.
`050148Z` (2 anchors, `EGAIN` 1.723): 2 anchors on most frames instead of 1, 13
verify solves instead of 10, none flagged either way. RR Lyr 2026-09-25 (`EGAIN`
0.8, as the request): unchanged.
**How to check.** `tests/workers/test_photometry_batch_worker.py::test_the_tracker_and_lock_use_the_frames_own_gain_s70`
(the request's 1.0 e-/ADU in the anchor choice and the lock check on the code
before the fix).

## Plate solving

### S24 — A database folder keeps the chosen star database

**What was wrong.** Settings' database folder replaced the chosen set: ASTAP got
`-d <folder>` without `-D D50` and picked a set on its own.
**Who was affected.** Users who set a database folder. Solves could be slower or
fail; a successful solve is still a real ASTAP solution.
**What changed.** ASTAP gets `-D <set> -d <folder>`, the pair it already got when
the folder was auto-detected (`astap_cli -h`: `-d path`, `-D abbreviation`).
**How to check.** `tests/core/test_astrometry_session.py::test_database_folder_keeps_the_database_set`.

### S50 — A plate solution off the session's scale is refused

**What was wrong.** Any solution ASTAP returned replaced the last good one.
On XX Cyg 2026-09-07 (`045156Z`) the auto-solve of the run's second frame
matched at 7.093″ per green pixel where every other solve of the night gave
7.341-7.343: a wrong match (its solves at other downsamples do not agree with
it). The next frame was measured through it: apertures 21-26 px off every
star, and the run's target CSV holds that row, unflagged (SNR 0.91, 26 px from
the star; `notes/tracker_comparison.md` §4.4 on the web-UI branch).
**Who was affected.** Live and sequence photometry after a wrong match; one
frame of the owner's 270 solves. Batch re-runs are not affected (they solve
once, then re-solve only on a lost lock, S43).
**What changed.** A camera frame's solution whose plate scale (from its CD
matrix) is more than 1 % from the session's first good solve is refused: the
previous solution is kept, as after a failed solve, and the log says why
("Solve: solution refused — plate scale 3.547″/px is 3.4 % below this
session's 3.671″/px (a wrong match); the previous solution is kept"). The
reference is the first accepted solve; another camera (a disconnect) or
another frame geometry starts a new one. The profile's nominal scale is not
used: it is 1.8 % above every measured solve. An opened FITS (another
instrument, another night) is neither held to the reference nor sets it. The
S48 lock check does not catch a wrong solution: a new solution rebuilds the
tracker from the stars seen where it puts them (on the wrong solve above it
kept 1 anchor of 6, which passed): S54 is the guard for a wrong solution at the
right scale, and S55 moves the reference when three solves agree.
Over every solve of the owner's sessions (the 257 frames of the tracker study,
Argos's live settings, and the 11 other runs: 15 frames, 13 solved: 270
solves), the good
ones lie within 0.3 % of their night's first solve; the gate refuses the one
wrong solve and no other (0 false rejections). Two frames did not solve at
all (2026-06-18, 2026-09-25 `194741Z`).
**How to check.** `tests/workers/test_astrometry_controller.py::test_a_solution_off_the_session_scale_is_refused_s50`
(the wrong solution replaced the good one on the code before the fix),
`::test_the_scale_reference_restarts_with_the_camera_or_geometry_s50` and
`::test_an_opened_frame_is_not_held_to_the_camera_scale_s50`.

### S54 — A new solution that the tracker's anchors do not confirm is refused

**What was wrong.** A new plate solution rebuilt the tracker from the stars seen
where it put them, so a wrong match passed the S48 check by construction. S50
refuses a wrong match by its scale only: one at the right scale replaced the
good solution, and the next frames were measured off every star, unflagged.
**Who was affected.** Live and sequence photometry after a wrong match at the
session's scale. None in the owner's runs: their one wrong solve (XX Cyg
2026-09-07 `045156Z`, the solve of its second sub) is 3.4 % off the scale and
S50 refuses it.
**What changed.** A camera frame's new solution on which fewer than ceil(k/2) of
the current tracker's k anchors show a star (aperture SNR ≥ 5, S35's threshold)
where it places them, on the frame it solved, is refused as S50 refuses one: the
previous solution and its tracker stay, the frame stays on its stars, and the
Activity log says why ("Solve: solution refused — only 1 of the 6 anchor stars
show a star where it places them (3 needed: a wrong match, or the field is not
there); the previous solution is kept"). No tracker means no check: the first
solve, after a slew (the tracker goes with the solution), after Open FITS or a
set change, for an opened FITS, and for the first camera solve after an opened
FITS (S59). The engine gives the check to the controller
(`AstrometryController.set_solution_check`, `AcquisitionEngine._solution_refusal`).
On the owner's runs (the 257 frames of the tracker study, Argos's live solves
replayed through the gates on the frame each solved): with a solve before every
sub, 265 solves, 257 of them checked against a tracker; 253 of the 265 lie within
1.4 px of an independent solve, 12 have none; refused: the `045156Z` wrong solve (by
S50, which runs first; with S50 off, S54 refuses it alone: 1 of the 6 anchors
seen); no good solve refused. With one solve per run and re-solves only when
due: 34 solves, all good, none refused. A solution of the same RR Lyr frame
moved 25, 10 px (a synthetic wrong match) is refused (0 of 6). The web server's
port has the same change and the same decisions on these frames.
**A re-pointing the mount did not report** (owner decision of 2026-11-15). A
field moved by more than about half the frame without a slew reported (camera
only, another app; the anchors off the frame) had its correct solutions refused
until a slew, a GoTo or a set change. Now 3 consecutive solutions refused by this
check that agree with each other within 20 green px (the largest distance
between where they put the newest one's frame centre) are a re-pointing: the
third is accepted and logged ("Solve: 3 consecutive solutions agree within 9.4
px on a field where the anchor stars are not (0 of 1 seen) — accepted as a
re-pointing the mount did not report"). As S55 moves the scale reference on 3
agreeing solves: failed solves and S50 refusals between them neither count nor
break the count; a solution the check passes, an accepted one, a slew or a set
change restarts it. 20 px is twice the largest span of 3 consecutive good solves
on the owner's runs (10.4 px, RR Lyr 2026-09-25, which drifts 4.3 px per sub;
the subs across its two mount jumps span 22.7 and 145 px). On the owner's runs it
changes nothing (the replays above, both schedules: no re-pointing accepted, the
same refusals; `045156Z` with S50 off: its one S54 refusal stands). On real RR
Lyr subs 41-48, subs 44 on moved 500 green px without a slew: before, every
correct solution was refused and the subs after 43 were skipped or measured off
the star (flagged); now subs 44 and 45 are refused, the solution of sub 46 is
accepted (the three agree within 9.4 px) and sub 48 is measured 0.66 px from the
star (flagged by S56: 2 of its comparisons are inside the moved frame, and RR Lyr
drifts 4.3 px per sub). With S56's anchors chosen on the solved frame (second set
of 2026-11-15) subs 44-46 get no point (1 of the 6 anchors seen on sub 44: before,
it had 1 anchor of 1 and a point 496 px off the star, flagged), and the refusals
of subs 44 and 45 read "only 2 of the 6 anchor stars" ("0 of the 1" before). The web
server's port has the same change.
**How to check.** `tests/workers/test_acquisition_engine.py::test_a_new_solution_the_anchors_do_not_confirm_is_refused_s54`
(the wrong solution replaced the good one on the code before the fix),
`::test_a_good_solution_after_a_jump_or_a_slew_is_accepted_s54`,
`::test_the_anchor_check_needs_half_the_anchors_s54` (1 of 4 seen refuses with
"(2 needed", 2 of 4 accepts: it fails if the threshold is lowered to 1) and
`::test_three_agreeing_refused_solutions_are_a_re_pointing_s54` (refused for ever
before the 2026-11-15 amendment; 3 that disagree stay refused).

### S55 — S50's scale reference moves when three solves agree

**What was wrong.** S50's reference is the session's first good solve. A wrong
first solve would have refused every later good one, until the camera
reconnected.
**Who was affected.** No session of the owner's: their first solves were all
good.
**What changed.** The last 3 camera solves of the reference's geometry (refused
ones included) that agree with each other within 0.3 % (max / min − 1) move the
reference to their mean; a move of more than the 1 % tolerance is logged ("Solve:
the plate-scale reference moves from 3.546″/px to 3.671″/px — 3 solves agree;
the earlier reference was a wrong match"). A wrong solve between good ones
never moves it, nor do two agreeing wrong ones. Over the owner's 270 solves
(272 frames, one controller per night), every accept and refuse decision is
the one S50 made (one refused, `045156Z`); the reference re-centres within the
night's 0.3 % spread. With a wrong first solve (3.4 % below) prepended to each
night: before, every later solve was refused (32 on 2026-08-29, 33 on
2026-09-07, 204 on 2026-09-25); now the third good solve is accepted and only
the two before it are refused (on 2026-09-07 the night's own wrong solve is
still refused). A night of one solve (2026-06-19) cannot recover: 3 are needed.
The web server's port has the same change.
**How to check.** `tests/workers/test_astrometry_controller.py::test_a_wrong_first_solve_cannot_refuse_every_later_good_one_s55`
(the good solves refused for ever on the code before the fix) and
`::test_the_reference_moves_only_on_three_agreeing_solves_s55`.

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

## Not in 0.5.0: calibration

ARGOS measures raw sub-exposures: no bias (offset), dark or flat is applied,
live, in a re-run or in Review, although the sequencer captures all three frame
types into a Siril layout. The reference reduction of RR Lyr 2026-09-25
(`star_var_script` with Siril) ran on the raw lights too ("No calibration frames
— proceeding with raw lights"), so the ARGOS–Siril agreement (S71, S76) checks
the photometry engine on the same data, not the effect of calibration.

What that leaves, term by term, in a differential aperture measurement with a
local sky annulus: the bias and the dark's signal are additive and are
subtracted with the sky (what remains is their fixed pattern between aperture
and annulus, and the dark's shot noise, which no error term counts); hot pixels
are flagged (`_peak_lacks_psf_support`). The flat is multiplicative and stays:
a star on the same pixels all night carries a constant offset, but the alt-az
mount's field rotation moves the comparisons across the sensor during a run, so
vignetting, dust and pixel response can add slow trends, the red noise the
run's `sigma_syst` does not contain. Its size on the S30 Pro has not been
measured. Times, periods and the curve's shape are not affected; magnitude
levels and slow trends may be, and the check star's curve is the guard.

The AAVSO export says so in its dialog (owner's decision, 2026-11-16: a warning,
the file unchanged). Planned for 0.6: measure the effect first (a dark library
and flats taken with the Seestar, the RR Lyr night reduced in Siril with and
without them), then bias, dark and flat masters applied to the green plane
before photometry, live and in a re-run, checked against that calibrated
reduction.

## State of the branch

- 779 tests pass, 47 skipped on 2026-11-16 with S84 (0.4.2: 534 and 45; the skipped
  S43 check needs a copy of a real session and ASTAP). Every fix carries a test that
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
- `sky_geometry.altitude_at` / `horizontal_at` used J2000 coordinates against the
  date's sidereal time (no precession): up to 0.3° off in 2026 against astropy (the
  wave 6a science review). The owner chose to precess to the date (S51).
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
- [x] Bump the version to 0.5.0, on explore/web-ui (`175abf6`: `argos/__init__.py`,
      `pyproject.toml`, `uv.lock`, the desktop shell's `Cargo.toml` and
      `Cargo.lock`, `docsrc/conf.py`); this branch, never released alone, keeps
      0.4.2. Frames written by the release say `SOFTWARE = 'Argos v0.5.0'`, which
      *Check your old files* relies on to tell fixed frames from affected ones.
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
