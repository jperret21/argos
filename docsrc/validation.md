# How the results were checked

This page says how ARGOS 0.5.0's numbers were checked, against what, with what
result, and what was not checked. The method itself is in
{doc}`differential_photometry`; this page is its evidence.

```{admonition} In one paragraph
:class: important

On three nights of one Seestar S30 Pro, ARGOS's times reproduce the frames' headers
to the millisecond (the computer's clock itself was not checked), its targets' airmass within 0.0005, its RR Lyr curve with an
independent Siril reduction of the same frames to 2 mmag with 8 mmag of scatter,
its three check stars with their AAVSO VSP magnitudes within 1.25 σ (VSP's own
errors included), and its noise model with the noise measured on the frames
within 4 % at gains 80 and 100. Its error bars are about right for faint stars
and 1.3-1.6 times too large for bright ones. That is little data: three nights,
one instrument, two targets, and one of them (XX Cyg) has no independent
reduction. The desktop app was tested with its simulator and with replays of
these nights; it has not yet been used live on a telescope.
```

## 1. What was checked, and how

**The criterion.** A result is checked first against a reference that does not
depend on ARGOS. Only then is the 0.5.0 server compared with the reference
implementation it was ported from (the retired Qt app's core, with the same
fixes); that second comparison proves the port, not the science (§9).

**The data.** Copies of the owner's sessions of three nights with one Seestar
S30 Pro: **XX Cyg 2026-08-29**, **XX Cyg 2026-09-07** and **RR Lyr 2026-09-25**,
one main run each at gain 80, re-measured with ARGOS's batch re-run (ASTAP as the
plate solver); the shorter runs of the same nights (two of them at gain 100, one
frame at gain 65) serve the noise and airmass checks. The frames were recorded by ARGOS 0.4.1 and 0.4.2,
so the live path was checked on replays of them, not at the telescope.

**The references**, none of them ARGOS code:

- **astropy**, for the times and the airmass, at a site fitted to the frames'
  own `ALTITUDE` and `AZIMUTH` headers (kept private);
- the **Siril + `star_var_script`** reduction of RR Lyr 2026-09-25, on the green
  channel, with the same two comparison stars. It read the same raw frames as
  ARGOS, registered but not calibrated: no dark, flat or bias (its own log, in
  the session's results folder: "No calibration frames — proceeding with raw
  lights");
- **AAVSO VSP**: the catalogue $V$ magnitudes of the check stars, with VSP's own
  errors;
- **the frames' own noise**: photon transfer from pairs of consecutive frames,
  the sky σ measured in the annuli, blank apertures, and the scatter of pairs of
  stars measured on the same frames;
- **Gaia DR3** positions and proper motions, and the reviewers' own Gaussian
  centroids and aperture photometry on the raw green plane (numpy only);
- the **AAVSO Extended File Format** rules, checked offline.

**Where the figures come from.** Three review passes wrote them down, with their
methods, in the repository; each figure below names its file and section:

- **W7**: [`web/spec/wave7-independent-checks.md`](https://github.com/jperret21/argos/blob/v0.5.0/web/spec/wave7-independent-checks.md)
  (2026-11-15);
- **decisions-s66-s72**: [`web/spec/decisions-s66-s72-independent-checks.md`](https://github.com/jperret21/argos/blob/v0.5.0/web/spec/decisions-s66-s72-independent-checks.md)
  (2026-11-16);
- **S73-S80**: [`web/spec/decisions-s73-s80-independent-checks.md`](https://github.com/jperret21/argos/blob/v0.5.0/web/spec/decisions-s73-s80-independent-checks.md)
  (2026-11-16), parts A to D; part D is the final state;
- **S*nn***: an entry of the release notes,
  [`notes/release_0_5_0.md`](https://github.com/jperret21/argos/blob/v0.5.0/notes/release_0_5_0.md).

The reviewers' scripts read the owner's files and stayed out of the repository.
Unless said otherwise a figure is the final state, after S76 and S85; the observer
code in every export was the placeholder `TST` or `TST01`, and no site appears
anywhere.

Run labels used below: **RR2** and **RR6**, RR Lyr 2026-09-25 re-measured with
Siril's 2 comparisons (000-BJW-665, 000-BJW-666, check 000-BCG-523) or with the
6 comparisons of the live run; **X07**, XX Cyg 2026-09-07; **X29**, XX Cyg
2026-08-29.

## 2. Times

The reference is the exposure midpoint from the frame's header,
`DATE-OBS + EXPTIME/2`, converted by astropy.

| Quantity | Result | Source |
|---|---|---|
| `jd_utc`, every CSV of the four re-runs | 0.0000 s | decisions-s66-s72 §1; S73-S80 D.2 |
| `jd_utc`, the live CSVs of the three nights as recorded | at most 0.0010 s | W7 §1 |
| `bjd_tdb`, re-runs, each star's position at the frame's date | 0.0000 s (at most 0.0001 s before S77) | S73-S80 B.3.6, D.2; decisions-s66-s72 §1 |
| AAVSO `DATE` | at most 0.044 s (the format's 6 decimals) | S73-S80 B.3.6 |

**Limits.** This checks the computation from the header, not the header's clock:
`DATE-OBS` is the computer's clock just before the camera is told to start
(release notes S36), and neither its offset from UTC nor the camera's start
latency was measured. `bjd_tdb` depends on the Settings site and the star's
position: with the RR Lyr run's wrong Settings site (83° from the true one) it was
off by 0.0154 s (W7 §1); at the J2000.0 position instead of the date's, by up to
0.0078 s (S73-S80 B.3.6; fixed by S77). Frames of 0.4.x are timed by
`DATE-OBS + EXPTIME/2`, never by their late `DATE-AVG` (S36, S39).

## 3. Airmass

The reference is astropy's altitude at mid-exposure, through Pickering's formula,
at the site fitted to the mount's pointing (median residual of the fit
0.0013-0.0027°, at most 0.018°: W7 §2).

| Quantity | Result | Source |
|---|---|---|
| Targets: the header `AIRMASS` Review and the re-run take (S66) | at most 0.00044 (RR Lyr 0.00035, X07 0.00044, X29 0.00009) | S73-S80 D.2; release notes S66 |
| Comparison and check stars, their own airmass (S78), runs with a fitted site | at most 0.00007 (0.0204 when they took the header value) | S73-S80 D.2, A.2 |
| Same, short runs without a fitted site (the header value, the field centre's) | at most 0.0012-0.0017; 0.0069 on the two gain-100 runs, whose comparisons lie up to 1° from the centre | S73-S80 A.2; release notes S78 |
| AAVSO `AMASS` | at most 0.0007 from astropy, 0.0005 from the header (3 decimals) | S73-S80 B.5 |

**What it caught.** The RR Lyr run was recorded with a Settings site 83° from the
true one: its CSV airmass and AAVSO `AMASS` were wrong by up to 3.05 (W7 §2).
Review and the export now take the header `AIRMASS` (S66), and a comparison takes
its own airmass only from a site that reproduces the mount's pointing within 0.1°
(S78). An adversarial test copied the first frame's pointing headers into every
later frame of that run, as a lost mount leaves them in 0.3.0-0.4.2 files (X1):
S66 as first written took them for a wrong site, and 165 of 195 frames took the
stale `AIRMASS`, up to 0.331 off (decisions-s66-s72 §11); S66 now recognises a
frozen pointing and computes those frames' airmass instead.

**Limits.** A Settings site wrong by less than 5° raises no warning (X3's
tolerance). The live path's per-star airmass (S78) was checked on replays, not
with a real mount (S73-S80 A.5).

## 4. Magnitudes

### 4.1 RR Lyr against an independent reduction

The reference is the `star_var_script` + Siril reduction of RR Lyr 2026-09-25 on
the green channel, with the comparisons 000-BJW-665 and 000-BJW-666. ARGOS's
re-run minus that reduction, matched in time, $n = 195$:

| ARGOS curve | Median offset | Robust σ | Source |
|---|---|---|---|
| Re-run, the same 2 comparisons (RR2) | **+0.0021 mag** | **0.0083 mag** | S73-S80 D.2 |
| Re-run, the 6 comparisons of the live run (RR6) | −0.0098 mag | 0.0130 mag | S73-S80 D.2 |
| The 0.4.2 live CSV as recorded (6 comparisons), 193 points | −0.0114 mag | 0.0176 mag | W7 §3 |

The like-for-like row (RR2) differs by 2.1 mmag, with an uncertainty of 0.7-0.9
mmag on that offset (S73-S80 D.3; S76's sky estimator moved it by +0.8 mmag): small
against the 8 mmag scatter, and of the size of the terms the W7 budget found
between the two methods (ARGOS's aperture against Siril's, −0.002 mag; the
averaging of the zero point, +0.001 mag: W7 §3). The 6-comparison offset is not
an error of either reduction: it is the comparison set's catalogue residuals (one
comparison, 000-BCG-953, sits 0.16 mag off and is clipped on 194 of 195 frames:
decisions-s66-s72 §10), as an additive budget of the W7 review showed term by
term (W7 §3). Two inputs were checked separately: the reviewers' own aperture
photometry of the raw green plane reproduced ARGOS's instrumental magnitudes
(W7 §3, with the annulus median ARGOS used then), and ARGOS's sky level equals
astropy's `sigma_clipped_stats(sigma=3, maxiters=10)` within 0.01 ADU on 502 of
504 re-run records (S73-S80 D.1).

**Limits.** One night, one star, and both reductions measure the same photons, so
their shared noise (photon noise, scintillation) cancels in the difference: its
χ² is not a test of the error bars (S73-S80 B.3.5). Neither reduction is
calibrated: both read the raw frames without dark, flat or bias, so the
comparison says nothing about flat-field errors. The apertures differ (ARGOS
2.5 × FWHM, Siril's dynamic, about 2 × FWHM). The RR Lyr template fits stored with
that session are not a reference: their three fits disagree by 1.2 mag in the
magnitude at maximum light (W7 §3).

### 4.2 Check stars against their catalogue magnitude

A check star is calibrated like the target and is never in the ensemble. The
reference is its VSP $V$, whose own error is part of the comparison. ARGOS minus
VSP $V$: unflagged rows, 5σ outliers removed, mean ± standard error
(S73-S80 B.3.4, D.2):

| Check star | Run | VSP $V$ | ARGOS − VSP $V$ | Distance in combined σ |
|---|---|---|---|---|
| 000-BCG-523 | RR2 | 7.015 ± 0.100 | +0.0166 ± 0.0015 | 0.17 |
| 000-BJV-169 | X07 | 10.283 ± 0.051 | −0.0645 ± 0.0085 | 1.25 |
| 000-BJV-171 | X29 | 10.606 ± 0.030 | +0.0436 ± 0.0204 | 1.20 |

The last column is the offset over $\sqrt{\sigma_\text{VSP}^2 + \text{s.e.}^2}$.
All three lie within 1.25 combined σ of VSP: 000-BCG-523 well inside VSP's own
error, the two XX Cyg checks just outside it (0.0645 against ± 0.051, 0.0436
against ± 0.030). Before 0.5.0's weighted zero point (S71), 000-BJV-171 came out
+0.28 ± 0.08 mag from its $V$ (W7 §4).

**Limits.** VSP's errors (0.030-0.100 mag) dominate; on its standard error alone
000-BJV-169's offset is significant, and calibrated against each comparison alone
that star ranges from −0.008 to −0.148 mag (the comparisons' catalogue values;
release notes S69). The check is an untransformed green measurement against a $V$
catalogue value, so a colour term is in it. XX Cyg has no independent reduction:
its check stars are its only magnitude test.

## 5. The noise model against the frames

| Quantity | Reference | Result | Source |
|---|---|---|---|
| Data format | raw pixel values | 99.92 % are multiples of 16: 12-bit data scaled by 16 | decisions-s66-s72 §9 |
| e⁻/ADU at gain 80 | photon transfer, 14 sessions over three nights | 0.228 ± 0.005 (the three nights 0.232, 0.230, 0.231) | release notes S73 |
| Same, independent re-measurements | photon transfer by three reviewers | 0.234; 0.2285 (16-84 %: 0.226-0.237); 0.2253 | decisions-s66-s72 §9; S73-S80 B.3.1; release notes S73 |
| e⁻/ADU at gain 100 | photon transfer | 0.183 measured; 0.181 scaled from gain 80 | S73-S80 B.3.1 |
| The frames' own `EGAIN` at gain 80 | the above | 0.8 (0.4.2) and 1.723 (0.4.1): 3.5 and 7.6 times too high | release notes S73 |
| Model sky σ / sky σ measured in the annuli | 3σ-clipped σ of the 8-12 px annuli | 0.960-1.039 on 31 frames at gains 80 and 100; 0.883 on the one gain-65 frame | S73-S80 D.2 |
| Blank apertures: flux scatter / ARGOS's error | apertures on blank sky, 30 px from every set star (40 per frame), or under a stricter star mask | 1.06-1.10 (strict mask); 1.14-1.19 (40 per frame) | S73-S80 D.2; release notes S75 |
| Blank apertures: mean flux | 0 for an unbiased sky | +10 ± 6 ADU (RR Lyr, 1560 apertures), +32 ± 12 and +25 ± 12 (the XX Cyg runs) | S73-S80 D.2 |

The blank apertures' remaining excess is not the sky estimator, whose own
variance was measured on the real annuli (factor 1.09 for the clipped mean, 2.95
for the median it replaced); it is the correlation of neighbouring pixels and the
faint stars inside the apertures, which also bias the sky low (S73-S80 D.2).

**Limits.** One camera, measured at gains 80 and 100; every other gain is scaled
from gain 80 at 0.1 dB per step, and the single gain-65 frame is inconclusive
(read noise dominates it). The black level and the read noise are degenerate in
these data; the e⁻/ADU is not (release notes S73).

## 6. Are the error bars honest?

An honest error bar makes the point-to-point scatter of a quantity about equal to
its error. Two tests, both independent of ARGOS's own error model:

**Pairs of stars.** For two stars on the same frames, the frame-to-frame scatter
of their magnitude difference over the quadrature sum of their errors; median over
the pairs, robust value in brackets (S73-S80 D.2, A.2):

| Run | Pairs | Before S72 (0.4.x model, the frames' `EGAIN`) | 0.5.0 |
|---|---|---|---|
| RR6 | 21 | 1.89 | 0.94 (0.77) |
| RR2 | 6 | 2.27 | 0.86 (0.75) |
| X07 | 36 | 1.48 | 1.12 (0.95) |
| X29 | 3 | 0.94 | 0.92 (0.94) |

**Second differences** (`star_var_script`'s estimator, §5 of the method page): the
RR2 target's and check star's scatter is 0.64 and 0.63 of their formal error
(S73-S80 D.8).

**Reading.** Faint stars (the XX Cyg pairs, SNR about 5-25) are near 1. Bright
stars (RR Lyr, SNR above 50) are over-estimated. By the median pair ratio their
formal errors are 1.06-1.16 times the scatter; by the robust ratio and the second
differences, their formal errors and AAVSO `MERR` are 1.3-1.6 times their measured
scatter (S73-S80 D.2, D.8, C.6). The causes are
known: scintillation's $C_Y = 1.5$, where the bright RR Lyr pairs measure 1.1-1.4,
and the zero point's error, whose scatter branch and 10 mmag floor carry the
comparisons' constant catalogue disagreement into every frame (S73-S80 C.5).
The run-level floor $\sigma_\text{sys}$ is now 0 on the RR2 and X07 targets
(S73-S80 D.2): the formal errors hold the scatter.

**Limits.** Splitting the formal error into a random part and a per-run
calibration part, and refitting $C_Y$ with more nights, were not decided and are
deferred to 0.5.x. Review of an old run reads its CSV's errors as recorded (the
0.4.x model); only a re-run computes 0.5.0's.

**How uncertain the floor's scatter is on a short run.** The run-level floor
starts from $\sigma_\text{real}$ (method §5): 1.4826 times the MAD of the second
differences, over $\sqrt{6}$, computed by `estimate_lightcurve_scatter` in
`argos/core/photometry/uncertainty.py` from 10 points on. That function was called
on simulated white noise of σ = 1, 20 000 runs for each length (NumPy
`default_rng(1)`):

| Points | Mean $\sigma_\text{real}$ | Relative standard deviation | 16th-84th percentile |
|---|---|---|---|
| 10 | 0.994 | 0.47 | 0.54-1.46 |
| 20 | 1.012 | 0.32 | 0.70-1.33 |
| 30 | 1.012 | 0.26 | 0.75-1.27 |

```python
import numpy as np
from argos.core.photometry.uncertainty import estimate_lightcurve_scatter

rng = np.random.default_rng(1)
for n in (10, 20, 30):
    est = np.array([estimate_lightcurve_scatter(enumerate(rng.normal(size=n)))
                    for _ in range(20000)])
    print(n, est.mean(), est.std() / est.mean(), np.percentile(est, [16, 84]))
```

The estimator is unbiased on white noise, but on a run of 10-30 points it is
uncertain by about a quarter to a half of its value. Correlated noise, which real
runs have, makes it worse.

## 7. Geometry: where the apertures sit

| Quantity | Reference | Result | Source |
|---|---|---|---|
| Field rotation tracked on X07 (0.7° per sub) | each frame's own ASTAP solution | within 0.07° on all 24 frames (the tracker before S69 ended 1.1° behind) | release notes S69 |
| Comparison and check apertures on X07 | each frame's own solution | 0.01-0.22 px on the first frames, 0.01-0.12 px on the last (0.2-2.5 and 0.6-4.5 px before) | release notes S69 |
| RR Lyr's aperture (proper motion 0.224″/yr) | Gaussian centroid on each frame | 0.077 green px median, 0.157 at the 90th percentile (0.990 and 1.111 at J2000.0) | S73-S80 D.2; release notes S77 |
| Target points far from their star | the reviewers' centroids | no unflagged target point more than 2 px from its star | S73-S80 D.4 |
| Two wrong anchors on one frame | a replay of X07 sub `_00020` with S69's neighbour rule off, to recreate them | both rejected; the target point 0.07 px from its star (no point before) | release notes S80 |
| Apertures off the frame's edge | a scan of RR6 | 13 rows within reach of the edge before, 1 after (wholly on the frame) | release notes S81 |
| Crowded comparisons named | an independent list | the same stars on all 20 study target sets | release notes S79 |

## 8. The AAVSO report

The reports of the three nights (from Review and from the re-runs) were read field
by field against the AAVSO Extended File Format rules (W7 §5; S73-S80 B.5):

- the header lines, the 15 columns, the field lengths and the delimiter follow
  the format; `#SOFTWARE` names ARGOS and its version (S64);
- `DATE` is the exposure midpoint (§2); `AMASS` is within 0.0007 of astropy (§3);
- `MAG` and `MERR` equal the curve CSV; on Review's reports, $\text{MERR}^2 -
  \text{formal}^2$ equals the reviewers' own second-difference floor (RR Lyr
  0.01497, X07 0.23657 against 0.23655);
- the rows left out are exactly those an independent reading of the flight
  recorder finds without a detection (RR Lyr frames `_00053` and `_00176`, X07
  frame `_00021`);
- `KNAME` and `KMAG` equal the check curve on 195 of 195 rows (RR2, W7 §5); the
  live runs of these nights had no check star, so their reports write `na` and
  the preview warns;
- a synthetic two-filter run is refused (one band per report, S53).

**Limits.** aavso.org returned 403 to the reviewers: the rules were checked
offline, and neither the AAVSO's WebObs validator nor an actual submission was
tried. ARGOS writes `#OBSTYPE=CCD` for its CMOS camera, taking `CCD` as the
format's code for CMOS cameras too (S68); with the AAVSO's page unreachable, that
reading was not confirmed. Review of a target CSV imported on its own writes
`KNAME` `na`: the check star's CSV beside it is not brought in
(decisions-s66-s72 §6). `CHART` is `na` on every report of these
runs (their comparisons were picked before ARGOS recorded charts, S68); a new run
writing `CHART` was checked by its tests only.

## 9. The 0.5.0 server against the reference implementation

The 0.5.0 desktop app runs the headless server (`argos/server`); the retired Qt
app's core, with the same fixes, is kept as the reference it was ported from. Run
in one process on the same frames, the two give **identical** results:

- re-runs of X07, X29, RR2, RR6, a short RR Lyr run (`195307Z`), and X29 with a
  temporary photon-transfer file: every CSV, target set, flight-recorder record,
  count and solver call (S73-S80 D.5, on the final science code; A.4 before
  S76). The last core changes (the source named in a new frame's `RDNOISE`, the
  read noise of a frame whose `EGAIN` the file wrote, a log line) were judged not
  to touch these cases' data, and parity was not run again after them (D.5);
- the exports of the three nights (AAVSO and CSV, from a session and from an
  imported file): 12 of 12 files byte for byte, at the S66-S72 pass
  (decisions-s66-s72 §12);
- the live path, replaying the study runs (16 replays and a target-set change):
  3787 points field by field, the CSVs byte for byte (release notes S85).

This proves the port; it says nothing about correctness, which §2-§8 test. The
re-run as an HTTP job was identical too at the S73-S80 validation (3 of 3 runs,
S73-S80 B.2), but was not checked again after S76 (S73-S80 D.8).

## 10. What was not checked

- **The desktop app live on a telescope.** It was tested with its simulator and
  with replays of real nights; live use on a real Seestar is pending.
- **The clock.** The computer's offset from UTC and the camera's start latency
  (§2).
- **New frames' `EGAIN` and `RDNOISE`** on a real capture (no camera during the
  checks), and the live per-star airmass with a real mount (S73-S80 B.7, A.5).
- **Another camera.** Another S30 Pro unit, gains other than 80 and 100, and the
  S30 and S50 profiles, which are marked unvalidated.
- **XX Cyg against an independent reduction**: none exists (W7, "Not checked").
- **The AAVSO side**: the WebObs validator, a submission, `#OBSTYPE` for CMOS, and
  a new run's `CHART` end to end (§8).
- **VSP** was not queried again after 2026-11-15 (S73-S80 D.8).
- **The re-run as an HTTP job** against the in-process re-run, after S76 (§9).

## 11. Deferred to 0.5.x, and open

These were reviewed and left open on 2026-11-16; until they are decided they are
limits (S73-S80 A.5, D.8):

- the formal error split into a random part and a per-run calibration part, and a
  refit of $C_Y$ with more nights (§6);
- resolving the e⁻/ADU once per gain at a run's start, so that an edit of the
  photon-transfer file during a run cannot change it;
- locking `site.elevation` during a run (it sets the scintillation term);
- Review of an imported re-run folder reads no flight recorder, so it shows no
  faint-comparisons warning (S73-S80 A.5).
