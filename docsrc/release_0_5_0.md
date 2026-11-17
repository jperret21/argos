# What changed in ARGOS 0.5.0

ARGOS 0.5.0 is the first beta of the new ARGOS: a stable version with the new
interface. ARGOS is now a web interface in a desktop app for macOS and Linux,
driven by an ARGOS server that runs beside it on the same computer. The PyQt6
application is retired; it is not released as 0.5.0. The release also brings a
batch of optimisations and bug fixes, numbered S1 to S85, H1 to H17 and X1 to X3
in the [release notes][notes], the photometry ones checked against references
independent of ARGOS: the Siril reduction of a real night, astropy, the AAVSO
VSP catalogue and the frames' own noise. Quick 0.5.x patch releases are
expected.

This page tells an observer what changed, grouped by task, in plain words. Each
item links to its entry in the release notes, which say what was wrong, who was
affected, what changed and which test proves it.

```{admonition} Tested with the simulator and replays, not yet at the telescope
:class: warning

The 0.5.0 interface was tested with ARGOS's built-in simulator and with
replays of real nights recorded with a Seestar S30 Pro. It has not yet been
used live on a telescope; that test is still to come. Treat your first night
with 0.5.0 as a test night, operate the telescope attended, and keep the
Seestar app at hand.
```

Install it from {doc}`install`.

## Check your old files

Several 0.4.x defects wrote wrong values into files you may already hold. Frames
written by 0.4.2 or earlier say so in their `SOFTWARE` header (`Argos v0.4.2`
or older); frames written by 0.5.0 say `Argos v0.5.0`. CSV and AAVSO files
carry no version: date them against the day you installed 0.5.0. The ones most
observers hold:

- **Every error bar and SNR** of a run at gain 80. 0.4.x used an electron gain
  that is not the camera's (1.9 to 2.7 times off for the stars' photon noise),
  left out scintillation and the sky estimate's own error, and measured the
  sky with a median that sits on the frames' 8-ADU steps
  ([S72], [S73], [S74], [S75], [S76]). The magnitudes barely move; their
  errors do. **Review › Re-run photometry…** gives a session 0.5.0's errors
  without touching its files.
- **AAVSO reports exported before 0.5.0** may hold points that are now left
  out (saturated or suspect, [S11]; no detection, [S67]), an `AMASS` computed
  for a missing or wrong site ([X2], [X3], [S66]) and a `#SOFTWARE` line
  without a version ([S64]). Re-run the photometry (**Review › Re-run
  photometry…**), then export from the re-run: Review alone flags the points
  without a detection only when the run saved per-frame diagnostic records
  (**Settings › Privacy & diagnostics**, off by default), and it writes the
  points whose tracking was checked on fewer than three stars, with a warning,
  until a re-run verifies them ([S56], [S58]). `CHART` stays `na` for a run
  recorded before 0.5.0, since nothing recorded its chart ([S68]): type the
  VSP chart in the export dialog's **CHART** field.
- **Frames with `SITELAT` and `SITELONG` both 0** were taken with no site set
  (0.4.1 and 0.4.2): their live airmass was computed for 0°, 0° ([X2]). **A
  site that was set but wrong** made the CSV airmass wrong while the header
  `AIRMASS` (the mount's) is right ([X3]).
- **Frames saved while the mount was disconnected** keep its last pointing
  and airmass ([X1]).
- **A single Dark or Bias Take shot** may have been exposed to the sky
  ([S1]); **a Take shot's header** could describe the next settings ([S2]),
  the form's filter ([S3]) or another frame's quality values ([S20]). **Light
  steps on the Dark slot** are black frames ([S7]).
- **Live curve files**: the first point of a series had its own aperture
  ([S31]), a star whose role changed kept one curve for both roles ([S33]),
  frames on which the field had moved were measured on blank sky ([S35],
  [S50]), and points measured after a run could land in its folder ([S45]).
  **Points measured on frames opened with Open FITS** carried another frame's
  time ([S4]).

The notes' [Check your old files][oldfiles] section gives, item by item, how
to find the affected files and what to do with them.

## What changed, by task

### A new interface, in a desktop app

- One window, five screens: **Connection**, **Observe** in four task modes
  (Framing, Focus, Field, Run), **Plan** with its **Preflight**, **Review** and
  **Settings**, whose filter searches every setting at once. See {doc}`guide`.
- For the night: **Watch**, a view you read from two metres; attention items
  with optional sounds, shared by every window; the computer kept awake during
  a run; an end-of-night card that proposes the matching darks and biases.
- **Review** rebuilt: the sessions list, a wall of plots on one time axis, a
  frame inspector, the batch re-run and the CSV and AAVSO exports as dialogs
  that show what they will write before they write it.
- **Night Red**, a strictly red theme for dark-adapted eyes, beside the
  Observatory and Charcoal themes.
- Offline by design: fonts, icons and scripts are bundled; the only network
  traffic is to the ARGOS server on the same computer, plus the catalogue and
  site lookups you start.
- Keys for every frequent action (**F1** to **F5**, **⌘1** to **⌘5** in the
  desktop app, **⌘K** for the command palette, **?** for the list); actions
  that move hardware always ask first.
- Gone with the Qt app: its floating windows and docks, and the separate
  Photometry window, whose parts now live in Observe and Review.

### Capture, the filter wheel and the focuser

- A Dark or Bias Take shot turns the wheel to its Dark slot first and is
  refused while the wheel turns elsewhere ([S1]); a Take shot's header
  describes the settings it was exposed with ([S2]), the filter the wheel
  reports ([S3]) and quality values measured on the saved frame ([S20]).
- A Light step never defaults to the opaque Dark slot ([S7]); a refused wheel
  move reports the slot the wheel is really on ([H9]).
- Autofocus applies its gain ([S22]); **Stop AF** returns the focuser to its
  start ([S23]); no manual Go to during an autofocus, and Go to respects the
  focuser's range ([H10]).
- Typed values (offset, binning, site, address) are applied when the edit is
  done, not at each keystroke ([H11]); the Camera card says when autofocus
  owns the camera ([H15]).

### Times, the site and the airmass

- A sequence frame is dated by its exposure, not its download ([S36]); a
  0.4.x frame opened again is dated from its start, not its late `DATE-AVG`
  ([S39]); BJD_TDB is computed offline ([S37]).
- With no site set, ARGOS never uses 0°, 0° as one ([X2]); the Settings site
  is checked against where the mount points ([X3]); frames do not keep a
  disconnected mount's pointing ([X1]).
- The computed airmass precesses the coordinates to the date ([S51]); Review
  and the re-run take each frame's header `AIRMASS`, the mount's ([S66]), and
  each comparison and check star its own airmass ([S78]); an opened frame never
  takes the mount's current airmass ([S34]).

### Identifying the field and following it

- A star database folder keeps the chosen database ([S24]); a run identifies
  its field even when no solution exists yet ([S14]); identifying the field
  keeps the check star ([S46]).
- A wrong plate solution can no longer replace a good one: off the session's
  scale ([S50], [S55]), not confirmed by the tracked stars ([S54]), built on a
  stale solution ([S52]) or on an opened file's ([S59]).
- A frame on which the stars are not where the tracker puts them gets no point
  ([S35], [S48]); a lock on fewer than three stars counts only near a fresh
  solution ([S56], [S58]).
- The tracker keeps up with a fast-turning alt-az field and checks each
  aperture against its star ([S69]), rejects every inconsistent anchor star
  ([S80]), follows each star's proper motion ([S77]), and no longer measures
  an aperture or sky ring that falls partly off the frame ([S81]).

### The live curve

- One aperture geometry per series ([S15], [S31]); one curve per star and
  filter ([S49], [S57]); a star whose role changes starts a new curve ([S33]).
- **Recommend…** never empties the ensemble ([S32]); the comparisons are
  vetted in live preview too ([S17]).
- Curve files are replaced whole, never half written ([S38]); measuring an
  object again never overwrites its earlier curve ([S40]); a finished run's
  folder receives no more points ([S45]); a run measures its Light subs only
  ([S44]).
- The plots leave saturated points out of their baselines ([S16]), show
  ratio-only points ([S18]) and stay fast late in a night ([S19]).
- A target measured below SNR 3 is flagged *no detection* as soon as it is
  measured ([S85]).

### Error bars and the zero point

- The zero point weighs each comparison star by its error ([S71]); a
  comparison beside a brighter star of the set is named ([S79]).
- The noise model is the green plane's, above the camera's black level
  ([S72]), with the camera's measured electron gain (0.228 e⁻/ADU at gain 80 on
  the S30 Pro), your own photon-transfer file first if you have one ([S73]).
  Each star's error now carries its scintillation ([S74]) and the error of its
  sky estimate ([S75]); the sky is the annulus' 3-sigma-clipped mean, not its
  median ([S76]).
- Every path uses each frame's own gain ([S41], [S42], [S70], [S83]); the
  noise model and the electron gain cannot change during a run ([S84]).

### Review, the batch re-run and the AAVSO export

- Review keeps the check star's role ([S9]); a per-star curve file is
  identified before it can be exported ([S10]).
- The AAVSO export needs an observer code and leaves flagged points out
  ([S11]), points without a detection ([S67]) and undated points ([S60]);
  one filter per report ([S53], and Export CSV likewise, [S61]); `#SOFTWARE`
  names the version ([S64]); in new runs, `CHART` names the VSP chart of older
  comparison sets too ([S68]).
- The batch re-run finds an ARGOS session's `.fit` lights ([S12]), measures
  the target set's object only ([S62]) and the session's own lights, not the
  copies Siril writes beside them ([S63]); it writes no JD 0 point and saves
  no cancelled run ([S13]); it identifies a frame again after a field jump
  ([S43]); it reads an `OBJECT` written in SIMBAD's form ([S82]).
- An opened FITS is dated from its own header ([S4]); a calibrated float frame
  is measured in counts ([S65]).

### Plan

- A prepared transit keeps its planning metadata ([S5]); visibility needs a
  site, and a transit's coverage after midnight is right ([S26]); the editor
  never cuts a value silently ([S47]).

### Hardware safety and wording

- **Connect all** leaves connected devices alone ([H2]); a jog stops every
  axis it moved ([H3]); Disconnect and Quit ask first during a run ([H7]); a
  connection failure says why ([H12]); the telescope profile cannot change
  while connected ([H13]).
- Messages say what they mean: the mount clock error names GoTo, Sync and
  Center ([H4]), tracking reads its real state ([H6]), the Stellarium card
  says why its server is not running ([H14]), the site search names this
  release ([H17]), and an unvalidated profile has one warning ([S29]).

## How the numbers were checked

Every figure below comes from the reviews' checks against references that do
not depend on ARGOS, on copies of three nights recorded with one Seestar
S30 Pro (XX Cyg on 2026-08-29 and 2026-09-07, RR Lyr on 2026-09-25): two
targets, one instrument.

| What | Reference | Result | Source |
|---|---|---|---|
| Point times (`jd_utc`, `bjd_tdb`) of a re-run | astropy, from `DATE-OBS` + `EXPTIME`/2 | 0.0000 s | [checks D.2][d2] |
| Live curve `jd_utc`, the three nights as recorded | astropy, from `DATE-OBS` + `EXPTIME`/2 | within 0.0010 s | [wave 7 checks §1][w7times] |
| AAVSO `DATE` | the frame's mid-exposure | within 0.044 s (JD to 6 decimals) | [checks §1][d1] |
| Airmass, targets; comparisons and checks | astropy at the site fitted to the frames' pointing | within 0.00044; within 0.00007 | [checks D.2][d2] |
| AAVSO `AMASS` | astropy, same site | within 0.0007 | [checks §2][d2am] |
| RR Lyr, re-run with Siril's two comparison stars | Siril + `star_var_script`, green, same comparisons | median offset +0.0021 mag, robust scatter 0.0083 mag, 195 frames | [checks D.2][d2] |
| Check star 000-BCG-523 (RR Lyr) | VSP *V* (± 0.100) | +0.0166 ± 0.0015 mag | [checks D.2][d2] |
| Check stars 000-BJV-169, 000-BJV-171 (XX Cyg) | VSP *V* (± 0.051, ± 0.030) | −0.0645 ± 0.0085, +0.0436 ± 0.0204 mag | [checks D.2][d2] |
| Sky noise model | the frames' measured green-plane sky σ, 31 frames at gains 80 and 100 | model / measured 0.960 to 1.039 | [checks D.2][d2] |
| Formal errors | point-to-point scatter of star pairs, four runs | scatter / formal error: median ratio 0.86 to 1.12; by the robust ratio and the second differences, bright stars' errors are 1.3 to 1.6 times their scatter | [checks D.2][d2], [C.6][c6], [D.8][d8] |
| Electron gain at gain 80 | photon transfer of 14 sessions over three nights | 0.228 ± 0.005 e⁻/ADU (an independent analysis: 0.2253) | [S73] |

What these numbers do not show:

- **One night, one star** for the comparison with Siril. Both reductions
  measure the same photons, so the noise they share cancels in the
  difference: it checks the method, not the error bars.
- **The check stars.** The RR Lyr check star (000-BCG-523) sits well inside
  VSP's ±0.100 mag; the two XX Cyg checks lie 1.25 and 1.20 combined σ from
  VSP, just outside its ±0.051 and ±0.030. VSP's catalogue errors dominate all
  three, and XX Cyg has no independent reduction.
- **The reference reduction was not calibrated either.** Siril and
  `star_var_script` read the same raw frames as ARGOS, with no dark, flat or
  bias (its log: "No calibration frames — proceeding with raw lights"): the
  comparison checks the photometry, not the calibration.
- **The AAVSO format** was checked offline, field by field: the AAVSO's page
  answered HTTP 403 to the reviews, and the WebObs validator was not run.
  Whether the AAVSO accepts `OBSTYPE=CMOS` (ARGOS writes `CCD`) was not
  checked.

## Known limits

- **Live use on a telescope** with the 0.5.0 interface is still to come.
- **Quick-look photometry.** The live curve and the re-run measure raw,
  uncalibrated sub-exposures in an instrumental band; the calibrated
  measurement comes from Siril and `star_var_script` on the raw frames ARGOS
  keeps ({doc}`differential_photometry`).
- **Attended use.** There is no weather safety and no restart recovery; the
  attention items and the keep-awake are not weather safety.
- **Profiles.** The S30 Pro is the reference; the S30 and S50 profiles are
  selectable but unvalidated.
- **Linux** is a technical preview: the package is built and its server
  smoke-tested by the release workflow, but has not been run on a Linux
  desktop.
- **Plate solving** needs ASTAP and a star database, installed separately
  ({doc}`install`).
- **Deferred to 0.5.x, with more nights:**
  - The formal error is not yet split into a random part and a per-run
    calibration part. Until then bright stars' errors, and their AAVSO `MERR`,
    come out 1.3 to 1.6 times their scatter ([checks C.6][c6], [D.8][d8];
    [S74]).
  - The scintillation coefficient stays at 1.5, a conservative value: the
    bright star pairs of one night measure 1.1 to 1.4 ([S74]).
  - The S30 Pro's electron gain is measured at gain 80; other gains scale it
    in the sensor's 0.1 dB steps, a scaling checked by its own photon transfer
    at gain 100 only. At any other gain the log says "scaled, not measured"
    ([S73]); your own photon-transfer file, if you have one, comes first.

[notes]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md
[oldfiles]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#check-your-old-files
[d2]: https://github.com/jperret21/argos/blob/v0.5.0/web/spec/decisions-s73-s80-independent-checks.md#d2-level-a-final
[c6]: https://github.com/jperret21/argos/blob/v0.5.0/web/spec/decisions-s73-s80-independent-checks.md#6-the-aavso-merr
[d8]: https://github.com/jperret21/argos/blob/v0.5.0/web/spec/decisions-s73-s80-independent-checks.md#d8-open-after-this-pass
[d1]: https://github.com/jperret21/argos/blob/v0.5.0/web/spec/decisions-s66-s72-independent-checks.md#1-times-astropy-from-date-obs--exptime2
[d2am]: https://github.com/jperret21/argos/blob/v0.5.0/web/spec/decisions-s66-s72-independent-checks.md#2-airmass-s66-astropy-altaz-at-mid-exposure-pickering-2002-at-the-site-fitted-to-the-mount
[w7times]: https://github.com/jperret21/argos/blob/v0.5.0/web/spec/wave7-independent-checks.md#1-times-astropy-from-date-obs--exptime2

[H2]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#h2--connect-equipment-leaves-connected-devices-alone
[H3]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#h3--the-jog-dialog-stops-every-axis-it-moves-and-drives-the-current-mount
[H4]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#h4--the-clock-error-message-says-goto-sync-and-center-are-refused
[H6]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#h6--the-tracking-button-reads-tracking-until-a-poll-says-otherwise
[H7]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#h7-h8--disconnect-and-quit-ask-first-during-a-run
[H9]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#h9--a-refused-wheel-move-ends-busy-and-shows-the-slot-the-wheel-is-on
[H10]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#h10--no-manual-go-to-during-autofocus-go-to-follows-maxstep
[H11]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#h11--typed-values-are-applied-when-the-edit-is-done
[H12]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#h12--connection-failures-say-why
[H13]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#h13--the-settings-telescope-picker-is-locked-while-connected
[H14]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#h14--the-stellarium-card-says-why-the-server-is-not-running
[H15]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#h15--the-camera-card-names-autofocus-when-autofocus-owns-the-camera
[H17]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#h17--the-site-search-identifies-this-release
[S1]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s1--a-darkbias-take-shot-is-refused-unless-the-wheels-dark-slot-is-selected
[S2]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s2--a-take-shots-header-describes-the-settings-it-was-exposed-with
[S3]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s3--a-take-shot-reads-the-wheel-for-its-filter
[S4]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s4--an-opened-fits-is-dated-from-its-header-and-drops-the-previous-wcs
[S5]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s5--a-prepared-transit-keeps-its-planning-metadata
[S7]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s7--a-light-step-never-defaults-to-the-wheels-opaque-dark-slot
[S9]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s9--review-keeps-the-check-stars-role
[S10]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s10--a-per-star-curve-csv-is-identified-before-it-can-be-exported
[S11]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s11--the-aavso-export-leaves-flagged-points-out-needs-an-observer-code-and-reports-errors
[S12]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s12--the-batch-re-run-finds-an-argos-sessions-light-frames
[S13]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s13--no-jd-0-point-no-saved-cancelled-run-roles-kept
[S14]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s14--a-sequence-identifies-the-field-even-when-no-wcs-exists-yet
[S15]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s15--the-aperture-geometry-is-locked-while-a-sequence-runs
[S16]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s16--saturated-points-are-left-out-of-the-plot-baselines
[S17]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s17--the-comparison-ensemble-is-vetted-in-live-preview-with-its-verdict
[S18]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s18--ratio-only-live-points-reach-both-plots
[S19]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s19--the-live-curves-re-render-once-per-frame-in-linear-time-keeping-the-zoom
[S20]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s20--a-take-shots-qa-headers-are-measured-on-the-saved-frame
[S22]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s22--autofocus-applies-its-gain
[S23]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s23--stop-af-returns-the-focuser-to-its-start
[S24]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s24--a-database-folder-keeps-the-chosen-star-database
[S26]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s26--plan-visibility-needs-a-site-transit-coverage-after-midnight
[S29]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s29--one-unvalidated-profile-warning-the-camera-hint-names-the-active-sensor
[S31]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s31--the-live-series-fwhm-is-frozen-on-the-first-measured-frame
[S32]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s32--recommend-from-pilot-keeps-the-ensemble-when-there-is-nothing-to-choose-from
[S33]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s33--a-star-whose-role-changes-starts-a-new-live-curve
[S34]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s34--an-opened-frame-never-takes-the-mounts-airmass
[S35]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s35--a-frame-on-which-the-field-moved-since-the-solve-gets-no-point
[S36]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s36--a-sequence-frame-is-dated-by-its-exposure-not-its-download
[S37]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s37--bjd_tdb-is-computed-offline
[S38]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s38--a-live-curve-csv-is-replaced-never-rewritten-in-place
[S39]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s39--a-04x-sequence-frame-is-dated-by-its-start-not-its-late-date-avg
[S40]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s40--measuring-an-object-again-never-overwrites-its-live-curve-csv
[S41]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s41--a-saved-frames-errors-use-its-own-gain
[S42]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s42--the-header-egain-is-the-e-adu-the-photometry-uses
[S43]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s43--a-batch-re-run-re-solves-a-frame-on-which-the-field-jumped
[S44]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s44--a-run-measures-its-light-subs-only
[S45]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s45--a-finished-runs-folder-receives-no-more-points
[S46]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s46--identifying-the-field-keeps-the-check-star
[S47]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s47--the-plan-editor-never-cuts-a-value-silently
[S48]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s48--a-frame-whose-anchors-show-no-star-where-the-tracker-puts-them-gets-no-point
[S49]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s49--one-live-curve-per-star-and-filter
[S50]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s50--a-plate-solution-off-the-sessions-scale-is-refused
[S51]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s51--the-live-and-batch-airmass-precess-j2000-coordinates-to-the-date
[S52]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s52--a-set-change-between-two-solves-never-re-anchors-the-tracker-on-a-stale-solution
[S53]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s53--the-aavso-export-refuses-curves-of-two-filters
[S54]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s54--a-new-solution-that-the-trackers-anchors-do-not-confirm-is-refused
[S55]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s55--s50s-scale-reference-moves-when-three-solves-agree
[S56]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s56--a-lock-on-fewer-than-3-anchors-is-verified-only-near-a-fresh-solution
[S57]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s57--every-vetting-file-names-its-filter
[S58]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s58--a-batch-re-run-verifies-a-lock-on-fewer-than-3-anchors-near-a-fresh-solution
[S59]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s59--a-camera-frame-after-an-opened-fits-drops-the-files-tracker
[S60]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s60--the-aavso-export-leaves-undated-points-out
[S61]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s61--export-measurements-refuses-curves-of-two-filters
[S62]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s62--a-batch-re-run-measures-the-target-sets-object-only
[S63]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s63--a-batch-re-run-of-a-session-measures-its-lights-only
[S64]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s64--the-aavso-report-names-the-softwares-version
[S65]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s65--the-frame-viewer-measures-a-calibrated-float-frame-in-counts
[S66]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s66--review-analyze-and-the-batch-re-run-take-the-mounts-airmass
[S67]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s67--review-the-aavso-export-and-the-batch-re-run-leave-out-the-points-without-a-detection
[S68]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s68--the-aavso-header-and-chart-the-vsp-chart-of-older-comparison-sets
[S69]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s69--the-tracker-keeps-up-with-a-fast-turning-alt-az-field-and-checks-its-apertures
[S70]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s70--a-batch-re-runs-tracker-uses-each-frames-own-gain
[S71]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s71--the-ensemble-zero-point-weighs-each-comparison-by-its-error
[S72]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s72--the-noise-model-is-the-green-planes-above-the-black-level
[S73]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s73--the-e-adu-at-gain-80-is-the-cameras-measured-one
[S74]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s74--each-stars-error-carries-its-scintillation
[S75]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s75--the-sky-estimates-own-error-is-counted
[S76]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s76--the-sky-is-the-annulus-3-sigma-clipped-mean-not-its-median
[S77]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s77--an-aperture-follows-its-stars-proper-motion
[S78]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s78--a-comparison-or-check-star-takes-its-own-airmass
[S79]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s79--a-comparison-beside-a-brighter-star-of-the-set-is-named
[S80]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s80--the-tracker-rejects-every-inconsistent-anchor
[S81]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s81--an-aperture-or-sky-annulus-partly-off-the-frame-is-not-measured
[S82]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s82--a-batch-re-run-reads-an-object-written-in-simbads-form
[S83]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s83--live-and-sequence-photometry-take-the-e-adu-at-the-frames-own-gain
[S84]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s84--the-noise-model-is-locked-while-a-sequence-runs
[S85]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#s85--a-live-target-point-below-snr-3-is-flagged-when-it-is-measured
[X1]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#x1--frames-do-not-keep-a-disconnected-mounts-pointing
[X2]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#x2--the-00-default-is-never-used-as-the-observing-site
[X3]: https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md#x3--the-settings-site-is-checked-against-the-mount
