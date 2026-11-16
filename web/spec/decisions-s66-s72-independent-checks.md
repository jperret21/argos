<!-- Copied 2026-11-15 from the W7 science review of S66-S72 (a scratch folder). Its `evidence/` and `scripts/` paths name that review's scratch files, which are not kept in the repository. How each finding was resolved: `web/spec/progress.md` (Wave 7, section 9, "Fixer round") and `notes/release_0_5_0.md` (S66-S73) on release/0.5.0. -->

# S66-S72 science review: independent checks (level a) and parity (level b)

Run 2026-11-15 on APFS clones of the owner's sessions XX Cyg 2026-08-29 (`20260829T050148Z`),
XX Cyg 2026-09-07 (`20260907T040723Z`) and RR Lyr 2026-09-25 (`20260925T200453Z`).

**The code checked.**
- "Fixed Qt" is the release/0.5.0 worktree: 73ef8fd plus the uncommitted S66-S72 diff, `git diff | shasum` b627bd95, unchanged during the review.
- The server is the main tree's argos (da2c6ac plus the uncommitted port) with the release `argos/core`, `workers` and `ui` overlaid (`trees/final`). Neither tree was edited.
- During the review, wave 8 changed only `argos/server/__main__.py`, `desktop.py` and the W8 part of `protocol.md`. `rerun.py`, `review.py`, `exports.py`, `photometry.py` and `field.py` were byte-identical to the overlay throughout.

**What the references are.** None depends on ARGOS code:
- astropy 6 for times and airmass;
- the star_var_script + Siril reductions in `results/`;
- the live VSP API (reached on 2026-11-15; every catalogue V in the three sets equals VSP);
- the AAVSO Extended File Format rules, checked offline;
- my own Gaussian-fit centroids and aperture photometry on the raw `(G1+G2)/2` plane (numpy only, `scripts/myphot.py`);
- each frame's ASTAP solution (astap_cli output cached by the tracker role, projected with astropy);
- my own photon transfer from frame pairs.

**Privacy.** No site coordinates, observer name or observer code appear here or in `evidence/`. The private configs that held the sites are deleted, and the tests use `TST01`.

Scripts are in `scripts/` and outputs in `evidence/`, both in this folder.

## 0. Summary

| Decision | Level (a) | Level (b) | Regression tests without their hunk | Finding |
|---|---|---|---|---|
| S66 airmass on a wrong site | **pass**: RR Lyr AMASS 1.033 on row 1, 1.033-1.364, ≤ 0.0007 from astropy; re-run takes the header AIRMASS on 195/195 frames (target ≤ 0.0003 from astropy) | = | fail as they should | **F3**: a frozen header pointing (X1) is taken for a wrong site |
| S67 no-detection rows | **pass**: rows left out = my own reading of the recorder (`_00053`, `_00176`; `_00021`); sigma_syst 0.01657 → 0.01497 and 0.2918 → 0.2365 reproduced | = | fail | **F2**: the batch re-run writes the same no-detection target point unflagged |
| S68 header, CHART | **pass**: SOFTWARE `Argos v0.4.2` (version present), OBSTYPE CCD, CHART na on old runs; today's VSP answer passes the band rule for 6/8/5 comparisons | = | fail | none |
| S69 tracker | **pass on the root cause**: `040723Z` apertures ≤ 0.38 px from the stars on 23/24 frames (W7: 4-6 px); the degraded `_00020` is caught | = | fail | **F1**: the centring test flags a faint star beside a brighter one (7 false flags on 000-BJV-173) |
| S70 batch gain | consistent (the S69/S70 counts reproduce) | = | fails | none |
| S71 weighted zero point | **pass** with the role's weighted-median clip centre (re-implemented: check 171 +0.059 ± 0.028); the plain median of the decision text fails its own test (+0.262 ± 0.099), as the role reported | = | fail | confirm the deviation (owner) |
| S72 noise model | the decided model **fails** its test with the frames' EGAIN (−52 % to −66 %); with 0.20 e-/ADU it passes (−1.5 % to +0.3 %). My photon transfer gives **0.23 e-/ADU** and shows 12-bit data × 16 | n/a (off by default) | fail | **F4** (S7x confirmed), **F5** (median sky on 16-ADU steps) |

## 1. Times (astropy, from DATE-OBS + EXPTIME/2)

Sources: `rerun_level_a.py` → `evidence/rerun_level_a.json`, and `aavso_fields.py` → `evidence/aavso_fields.json`.

| Curve set | jd_utc − mid-exposure, max | bjd_tdb − astropy (re-run site, each star's coordinates), max |
|---|---|---|
| Re-runs RR2, RR6, X07, X29 (every CSV, 26 curves) | 0.0000 s | ≤ 0.0001 s |
| AAVSO DATE, three sessions (Review source) | 0.044 s (JD rounded to 6 decimals; half a step is 0.043 s) | n/a |

The 1 ms target holds. No time code changed.

## 2. Airmass (S66): astropy AltAz at mid-exposure, Pickering 2002, at the site fitted to the mount

The site is fitted to the header ALTITUDE/AZIMUTH. The median residual is 0.0013-0.0027° and the maximum 0.018°.

| Source | AMASS / CSV airmass | − astropy, max | − header AIRMASS, max |
|---|---|---|---|
| RR Lyr report (server = Qt, Review and import) | 1.033 on row 1; 1.033-1.364 over 193 rows | 0.0007 | 0.0005 |
| RR Lyr re-run, that night's (wrong) Settings site, target | 1.0333-1.3641 (header AIRMASS on 195/195) | 0.0003 | 0.0000 |
| Same re-run, comparisons | the field-centre header AIRMASS | up to 0.0204 (953, 1° off-centre) | 0.0000 |
| XX Cyg 09-07 report | 1.081-1.090 | 0.0007 | 0.0004 |
| XX Cyg 09-07 re-run (Settings site 2.1°, under the tolerance) | 1.0753-1.0882 | 0.0056 (median −0.0034) | 0.0058 |
| XX Cyg 08-29 report | 1.060-1.065 | 0.0005 | 0.0005 |
| XX Cyg 08-29 re-run (Settings site 2.1°) | 1.0731-1.0795 | **0.0148 (median +0.0138)** | 0.0148 |

The last row confirms the exports role's open OWNER DECISION, the error that stays under the 5° tolerance. I agree with its recommendation (b), provided F3's frozen-pointing guard comes with it.

## 3. RR Lyr against star_var_script + Siril green, 2 comparisons

Matched by time within 20 s (`rerun_level_a.py`).
- The ARGOS errors are the CSV's `mag_err` (total) or `formal_mag_err` (with S71's zero-point error).
- The Siril errors are its `err`. Siril's formal error is `sqrt(err² − 0.0201²)`.

| ARGOS curve (final trees) | n | Median | Robust σ | Std | χ²ᵣ (total ⊕ Siril total) | χ²ᵣ (formal ⊕ Siril formal) | Drift |
|---|---|---|---|---|---|---|---|
| **Re-run, 2 comps (665 + 666) + check 523** | 195 | **+0.0013** | **0.0096** | 0.0171 | 0.25 | **0.81** | +0.007 |
| Same without `_00053` / `_00176` | 193 | +0.0013 | 0.0098 | 0.0172 | 0.25 | 0.82 | +0.007 |
| **Re-run, the live set (6 comps)** | 195 | **−0.0076** | 0.0153 | 0.0237 | 0.66 | 2.54 | −0.007 |
| W7 references | | +0.0020 / −0.0114 (live CSV) | 0.0099 / 0.0176 | | 0.28 | 0.91 | |

- Both W7 figures are kept or improved.
- The live set moves from −0.011 to −0.008 (S71's weights); the rest is the comparison set's catalogue offsets (W7 §3).
- On the re-run, the two `_00053` / `_00176` frames are re-solved and are good points (|dev| ≤ 0.072).

## 4. Check stars against VSP V (live VSP API)

`rerun_level_a.py`, `vsp_check.py`. The check is never part of the ensemble.

| Run (final re-run) | Check (VSP V ± err) | n | Mean − V ± SE | σ, SE only | σ, with VSP err | p2p scatter | χ²ᵣ mag_err | χ²ᵣ formal |
|---|---|---|---|---|---|---|---|---|
| RR Lyr RR2 | 000-BCG-523 (7.015 ± 0.100) | 195 | **+0.0155 ± 0.0017** | 8.9 | 0.15 | 0.023 | 0.98 | 2.36 |
| XX Cyg 09-07 X07 | 000-BJV-169 (10.283 ± 0.051) | 23 | **−0.071 ± 0.010** | 7.4 | 1.37 | 0.049 | 0.65 | 1.21 |
| XX Cyg 08-29 X29 | 000-BJV-171 (10.606 ± 0.030) | 22 | **+0.060 ± 0.024** | 2.55 | 1.57 | 0.130 | 0.50 | 1.37 |
| W7 | 523 / 169 / 171 | | +0.017 ± 0.002 / −0.061 ± 0.017 / +0.28 ± 0.08 | | | | | |

- **000-BJV-169** sits further from VSP than in W7, as the tracker role explained. It is 1.4σ out once VSP's own error is counted.
- **000-BJV-171** goes from +0.28 to +0.06. It is within 2σ only with VSP's error. On the standard error alone it is 2.55σ here, and 2.08σ in my S71 re-implementation on the recorder values (§10).
- **The decision's test for 169** ("within 2σ or the residual explained") is met through the VSP errors and the comparisons' catalogue spread.

## 5. Is the error model honest now?

Star pairs on the same frames (recorder `inst_mag`, so the zero point cancels): point-to-point scatter over the quadrature sum of `inst_mag_err` (`rerun_level_a.py`, `pairs`).

| Run | Pairs | Ratio range | Median | Extra per star needed |
|---|---|---|---|---|
| RR Lyr RR6 | 15 | 1.31-2.87 | 1.91 | 0.010-0.030 |
| RR Lyr RR2 | 3 | 1.88-2.86 | 2.23 | 0.014-0.020 |
| XX Cyg 09-07 | 28 | 1.08-2.98 | 1.61 | 0.025-0.11 (0.22-0.28 with 173, blended) |
| XX Cyg 08-29 | 1 | 1.52 | 1.52 | 0.068 |

**No.** S72 is off and S7x is open, so the instrumental errors are unchanged from W7 (1.33-3.84).
- **RR Lyr's bright pairs:** the excess of 0.014-0.020 mag per star is what Young (1967) with Osborn's ×1.5 predicts for scintillation, 0.015-0.025 for 10 s through 30 mm at X = 1.03-1.36 at sea level. This supports the model role's OWNER DECISION 2.
- **XX Cyg's pairs:** they need 0.03-0.08 mag per star, far above scintillation (0.012-0.013). That fits Poisson errors made too small by the e-/ADU (§9).
- **The total `mag_err`** (with `sigma_syst`) gives χ²ᵣ 0.98 on the RR Lyr check, but 0.50-0.65 on the XX Cyg checks, whose floors come from 22-23 points.
- **The formal errors with S71's zero-point error** give χ²ᵣ 1.21-1.37 on the XX Cyg checks and 2.36 on RR Lyr.

## 6. AAVSO reports field by field (`aavso_fields.py`, W7 `aavso_validate.py`)

Source: Review (session). The server's file equals Qt's (§12).

| Field | RR Lyr | XX Cyg 09-07 | XX Cyg 08-29 |
|---|---|---|---|
| Rows / CSV rows | 193 / 195 | 23 / 24 | 22 / 22 |
| Rows left out | `_00053`, `_00176` | `_00021` | none |
| Same as my own reading of the recorder (target SNR < 3, or a frame zero point more than 1 mag from the run's median, V − inst over the comparisons) | yes | yes | yes |
| Preview / message | "Left out: 2 suspect (no detection) points" | "1 …" | `unverified_lock` 22, `faint_comparisons` (median SNR 1.7) |
| MAG = CSV mag | yes | yes | yes |
| MERR² − formal² → sigma_syst (my second-difference estimator on the kept rows) | 0.01497 (0.01485-0.01508) = mine 0.01497; was 0.01657 | 0.2366 = mine 0.23655; was 0.2918 | 0.1145, unchanged |
| DATE − mid-exposure | ≤ 0.044 s | ≤ 0.044 s | ≤ 0.040 s |
| AMASS − astropy | ≤ 0.0007 | ≤ 0.0007 | ≤ 0.0005 |
| `#SOFTWARE` / `#OBSTYPE` | `Argos v0.4.2` / `CCD` | same | same |
| CHART / KNAME / KMAG / GROUP / NOTES | na / na / na / na / na | same | same |
| W7 validator | 0 errors; warnings: no check star, CHART na | same | same |

- **CHART on old runs:** na is correct, because nothing records their chart.
- **The S68 band rule:** checked against today's VSP answer (`s68_bands.py`), every comparison of the three sets (6, 8, 5) carries exactly the set's magnitudes in every band, so it would get the chart.
- **Re-run exports.** I put the re-run CSVs in the session clones and exported them through the server import.
  - RR2: 195 rows. X29: 22 rows.
  - X07: 23 rows, **including `_00021` at 13.290 ± 0.750 (F2)**.
  - KNAME is na on all three: importing the target CSV alone does not bring the check's CSV from the same folder. This is not part of S66-S72 and I did not investigate it further.

## 7. XX Cyg 2026-09-07 `040723Z`: re-run apertures frame by frame (S69)

Distance (green px) between the final re-run's aperture centres (its flight recorder) and the stars:
- **my fit**: a Gaussian fit on the raw green plane, with set stars within 10 px fitted together;
- **ASTAP**: for 000-BJV-173, its catalogue position projected through that frame's own ASTAP solution. The pixel convention, calibrated on 4 isolated comparisons, is (0.01, 0.03) px.

Aperture radius 5.45 px. Scripts: `offsets.py`, `s69_blend.py`, `s69_astap_173.py`.

| Frame | File | Target | Worst comp/check | 173: my fit / ASTAP | Off-centre (recorder) |
|---|---|---|---|---|---|
| 0 | _00001 | 0.03 | 0.17 (170) | 0.06 / 0.03 | - |
| 1 | _00002 | 0.11 | 0.19 (501) | 0.10 / 0.04 | - |
| 2 | _00003 | 0.27 | 0.17 (501) | 0.11 / 0.04 | - |
| 3 | _00004 | 0.06 | 0.20 (173) | 0.20 / 0.08 | **173** |
| 4 | _00005 | 0.28 | 0.26 (578) | 0.04 / 0.02 | - |
| 5 | _00006 | 0.12 | 0.22 (501) | 0.08 / 0.06 | - |
| 6 | _00007 | 0.09 | 0.31 (173) | 0.31 / 0.18 | - |
| 7 | _00008 | 0.06 | 0.19 (170) | 0.15 / 0.10 | - |
| 8 | _00009 | 0.12 | 0.21 (501) | 0.02 / 0.09 | - |
| 9 | _00010 | 0.14 | 0.23 (501) | 0.04 / 0.12 | - |
| 10 | _00011 | 0.08 | 0.20 (501) | 0.07 / 0.02 | - |
| 11 | _00012 | 0.09 | 0.18 (396) | 0.15 / 0.07 | - |
| 12 | _00013 | 0.13 | 0.26 (501) | 0.04 / 0.18 | **173** |
| 13 | _00014 | 0.06 | 0.38 (501) | 0.13 / 0.07 | **173** |
| 14 | _00015 | 0.14 | 0.28 (501) | 0.20 / 0.08 | **173** |
| 15 | _00016 | 0.12 | 0.23 (501) | 0.13 / 0.06 | - |
| 16 | _00017 | 0.24 | 0.28 (501) | 0.11 / 0.04 | **173** |
| 17 | _00018 | 0.06 | 0.33 (501) | 0.15 / 0.04 | - |
| 18 | _00019 | 0.13 | 0.21 (396) | 0.03 / 0.04 | **173** |
| 19 | _00020 | 2.11 | 4.90 (396) | 1.75 / 1.72 | all 8 (true: degraded sub, no target point) |
| 20 | _00021 | 0.03 | 0.18 (501) | 0.16 / 0.05 | - |
| 21 | _00022 | 0.03 | 0.29 (501) | 0.16 / 0.12 | - |
| 22 | _00023 | 0.14 | 0.24 (501) | 0.10 / 0.13 | - |
| 23 | _00024 | 0.17 | 0.24 (501) | 0.07 / 0.03 | **173** |

- **The S69 test:** frames 1-3 are at most 0.28 px, and the whole run is at most 0.38 px except `_00020`, which is flagged. W7 had 4-6 px.
- **Rotation:** 7 S69 (a) re-solves; the rotation since the last solution is 0.014° at the end of the run.
- **The 7 off-centre flags on 000-BJV-173 are false** (F1). Both references put 173 within 0.03-0.20 px of its aperture.
  - The core's own `refine_centroid` at 173's aperture returns None on those frames: it is dragged into 000-BJV-169, 6.9 px away and 1.5 mag brighter.
  - On the S69 test's own synthetic field (`_noisy_field`, 1600 at 200,200 and 400 at 204.9,204.9), `refine_centroid` on the **faint** star returns None on 8 of 8 seeds.
- **A second false flag:** XX Cyg 08-29 000-BJV-178, frame 5, at SNR 5.0 (the gate). The recorder says 2.68 px; my fit says 0.08 px.

## 8. Flags and skips on the study runs (final re-runs)

`runs/*.json` (deleted after use; numbers in `evidence/`), `offsets_*.json`.

| Run | Frames | Skipped | S43 re-solve | S69 rotation re-solve | S58 verify solve | Unverified | Off-centre (true / false) | Target rows (suspect) |
|---|---|---|---|---|---|---|---|---|
| RR2 | 195 | 0 | 2 | 0 | 0 | 0 | 0 | 195 (0) |
| RR6 | 195 | 0 | 2 | 0 | 0 | 0 | 0 | 195 (0) |
| X07 | 24 | 0 | 0 | 7 | 1 | 0 | 15 (8 on `_00020` / **7 on 173**) | 23 (0) |
| X29 | 22 | 0 | 0 | 0 | **13** | 0 | 1 (**false**, 178 at SNR 5) | 22 (0) |

- **Nothing good was skipped.** The only lost target point is `_00020`, which really is degraded: apertures 1.7-4.9 px off by my fits and ASTAP.
- **Good points newly flagged:** 173 × 7 and 178 × 1 (F1). These are comparison rows, not exported, and those comparisons drop out of their frames' ensembles.
- **No blank-sky point is newly kept.** The RR Lyr frames `_00053` and `_00176` are re-solved in the re-run and are good points.
- **But the re-run keeps the S67 frame's target point** `_00021` (recorder SNR 1.63; mag 13.290 ± 0.750 against 11.7-12.2 around it) unflagged, and its export writes it (F2). On that frame the target is visible:
  - my Gaussian fit: amplitude 621 against 597-726 on nearby frames, 0.03 px from the aperture;
  - the aperture flux is 448 ADU because the annulus median (1448) sits 2.6 ADU above the annulus mean and 8 ADU above the 12-20 px median;
  - with those, the flux would be 679 or 1168 ADU. The point is noise-dominated (F5).
- **The 050148Z re-run asked under S67/S56:** 22 frames, 13 verified by a fresh solve, 0 unverified, 0 flagged. The release notes' S56 bullet says 12 (F6).
- **RR Lyr apertures against the stars' own centroids:** the target is 0.99 px off (proper motion, the tracker's owner decision) and the comparisons 0.27-0.43 px (median). The tracker role's "0.13-0.14 px" is against the ASTAP projection. My centroids agree with the tracker's own `centroids_after_RR2.txt` (0.24-0.41).

## 9. Noise model (S72) and the e-/ADU (S7x)

Source: `noise_check.py` → `evidence/noise_check.json`.

**Raw values.** 99.92 % of the raw pixel values of all three sessions are multiples of 16, and 100 % multiples of 4. These are 12-bit data scaled by 16, so the green plane steps by 8 ADU.

**Measured sky σ.** The robust σ (3σ-clipped std; the MAD is quantised on these frames, at 1.4826 × 16, 24 or 32) of the (G1+G2)/2 plane in the 8-12 px annuli of every set star on frame 1 (median over stars) is compared with the models (read noise 1.5 e-, black 1024):

| Frame 1 | Sky level | Measured σ | 0.4.x pixel model, frame EGAIN | S72 as decided, frame EGAIN | S72, 0.20 e-/ADU | S72, 0.25 |
|---|---|---|---|---|---|---|
| RR Lyr (EGAIN 0.8) | 1176 | **20.5** | 38.4 (+87 %) | 9.8 (−52 %) | **20.2 (−1.5 %)** | 17.9 |
| XX Cyg 09-07 (EGAIN 1.723) | 1368 | **29.7** | 28.2 (−5 %) | 10.0 (−66 %) | **29.8 (+0.3 %)** | 26.6 |
| XX Cyg 08-29 (EGAIN 1.723) | 1400 | **31.2** | 28.5 (−8 %) | 10.5 (−66 %) | **31.1 (−0.1 %)** | 27.8 |

**Photon transfer (independent).**
- Method: raw G1 pixels of two consecutive frames; stars masked in both frames (4σ, dilated 3 px); 32 × 32 tiles; half the clipped variance of the difference against the tiles' mean level. Two pairs per session, 8052 tiles in 20 level bins.
- Result: slope **0.234 e-/ADU** (raw pixel, 16-bit ADU), intercept 115 ADU². Quantisation alone accounts for 21 ADU² of that, which leaves a read noise of about 2.3 e-.
- The slope comes from the step between the RR Lyr sky (about 1190, variance 820) and the XX Cyg skies (about 1365-1400, variance 1600-1700), so it does not depend on the black level.

**Conclusion.** The decided S72 cannot pass its own test with the frames' EGAIN (0.8 or 1.723); it passes with 0.20-0.25 e-/ADU. This confirms the model role's S7x (new) with a different method. Leaving S72 off until the owner decides was the right call.

## 10. S71 re-implemented from the decision text (`s71_check.py`)

XX Cyg 2026-08-29 `050148Z`, live recorder: check 000-BJV-171 against 170, 176, 178 and 180.

| Rule | Mean − V ± SE | σ (SE) | σ (with VSP 0.030) | p2p | χ²ᵣ formal | zp_err, frames 15 / 18 | Median comps kept |
|---|---|---|---|---|---|---|---|
| (A) 0.4.x mean, MAD clip | +0.281 ± 0.084 | 3.35 | 3.16 | 0.432 | 6.2 | 0.411 / 0.052 | 3 |
| (B) decision text (plain-median clip centre) | +0.262 ± 0.099 | 2.65 | 2.53 | 0.417 | 4.5 | 0.054 / 0.088 | 2 |
| (C) weighted-median clip centre (as implemented) | **+0.059 ± 0.028** | 2.08 | **1.43** | 0.145 | 1.68 | **0.054 / 0.088** | 3 |

- **000-BCG-953 on the RR6 re-run recorder:** clipped on 194 of 195 frames under both (B) and (C).
- **With the plain median in `differential.py`:** `test_reddish_comparison_still_clipped_s71` fails (`evidence/s71_plain_median_tests.txt`), so a test covers the deviation.
- **Recommendation:** the owner confirms (C).

## 11. Adversarial checks

**F3: S66 and a frozen header pointing** (`s66_frozen.py` → `evidence/s66_frozen.json`).
- Setup: the RR Lyr headers, with the RIGHT (fitted) site. Frame 0's RA/DEC/ALTITUDE/AZIMUTH/AIRMASS are copied into every later header (X1, a mount dropped under 0.3.0-0.4.x), and DATE-OBS is kept.
- What the release core does: through its own `frame_pointing` / `site_offset_deg`, as the batch worker's `_frame_site_check` uses them, every frame from frame 30 (about 22 min in) is "wrong site". **165 of 195 frames take the frozen AIRMASS, up to 0.331 from astropy.** Without S66 the computed airmass was right.
- Review's median rule fails the same way once more than half the frames are frozen.

**F1: the centring test on blends.** See §7.

**F5: the sky estimator on quantised frames** (`sky_estimator.py` → `evidence/sky_estimator.json`).
- Method: at the re-run apertures, the annulus median (ARGOS's estimator, flux reproduced to 0.0 ADU) against a 3σ-clipped annulus mean.
- `040723Z`: the clipped mean lowers the point-to-point scatter of the star pairs by a median of 11 % (29 of 36 pairs; target pairs 0.79-0.99).
- `050148Z`: 3 pairs, +7 %, inconclusive.
- Each pair has 22-24 points, so this is a lead, not a proof.

## 12. Level (b): server against the fixed Qt

**Exports** (`lb_exports.py`, the exports role's script on my port 8795; `qt_exports.py` drives Analyze and the Photometry window of the release worktree) → `evidence/exports_final.json`.
- Three sessions × {A78 session vs Qt Review → Export AAVSO; A78 import vs Qt Open curve CSV → Export AAVSO; A79 session vs `write_curves_csv(load_session_curves)`; A79 import vs Qt Export measurements}.
- **12 of 12 identical.**

**Re-runs** (`rerun_parity.py`, the tracker role's script) → `evidence/rerun_parity_*.json`: the server's `rerun.BatchRun` and the Qt `PhotometryBatchWorker` in one process, with the same frames, reference solve, params, base e-/ADU 1.723, that night's Settings site and ASTAP.

| Run | Frames | Counts and solver calls | CSVs identical | targets.json | Recorder records |
|---|---|---|---|---|---|
| RR2 | 195 | equal (2 solver calls each) | 4/4 | = | = |
| RR6 | 195 | equal (2) | 7/7 | = | = |
| X07 | 24 | equal (8) | 9/9 | = | = |
| X29 | 22 | equal (13) | 6/6 | = | = |

The HTTP job wrapper was not re-checked; the tracker role did it on `040723Z`.

## 13. Each regression test without its hunk

- **Release** (`fail_without_hunk.py`, scratch copies of the worktree, hunks reverted with `patch -R` from `git diff -U2 HEAD`) → `evidence/fail_without_hunk.json`.
- **Server** (`server_fail_without_port.py`; the server files reset to `git show HEAD:` in a copy of the overlay, with guard-name shims so the tests run against the old logic rather than fail at import) → `evidence/server_fail_without_port.json`.

| Hunk reverted | Tests | Result |
|---|---|---|
| Baseline (nothing reverted, `ARGOS_S66_SESSION` = RR Lyr clone) | 113 S tests and their files | 112 passed, 1 skipped |
| `review.py`, `lightcurve.py`, `analyze_page.py`, `photometry_window.py` (S66, S67) | 8 old-file + 2 UI | 9 fail; the right-site control passes (by design); the real RR Lyr test fails |
| Batch worker H3 + H23 (S66) | 2 | wrong-site test fails; right-site control passes |
| `targets.py` + engine H4 (S68) | 2 | 2 fail |
| `tracking.py` H8 (S69 root cause, tracker) | 1 | fails |
| `tracking.py` H6 (S69, refine) | 3 | 2 fail; `centring_offsets` test passes (it tests H7, not H6) |
| Engine H11-12 (S69 live) | 2 | 2 fail |
| Batch worker H8-11 (S69 batch) | 3 | 3 fail |
| Batch worker H18 (S70) | 1 | fails |
| `differential.py` (S71) | 3 | 3 fail |
| `aperture.py` (S72) | 2 | 2 fail |
| Server baseline (release core overlaid) | old-file, rerun, photometry, review_sessions | 97 passed |
| Server `review/exports/field/rerun.py` at HEAD (S66-S68 port) | `test_old_file_rules.py` | 6 fail |
| Server `rerun.py` at HEAD (S69/S70 port) | rerun | 2 fail (incl. `alt_az_s69` parity) |
| Server `photometry.py` at HEAD (S69 live port) | 2 | 2 fail |
| Server `review.py` at HEAD (S71 readiness) | 1 | fails |

## 14. Whole suites on the final trees (`suites.sh`, shared heavy lock)

See `evidence/suite_*.txt`.

| Suite | Result |
|---|---|
| Release worktree | 718 passed, 47 skipped |
| Main tree (current core, guarded tests skipped or branched) | 1662 passed, 85 skipped |
| `tests/server` with the release core overlaid | 935 passed, 3 skipped, 1 failed |

The one failure, `test_desktop.py::test_waiting_and_paused_runs_are_named_as_such`, is wave 8's. The overlay's copy of `argos/server/desktop.py` was taken before wave 8 edited it during this review, while `tests/` was copied later. It is not related to S66-S72.

## 15. Not checked

- **The live and sequence paths of S69 on real frames.** I did no replay of my own. The tracker role's replays are its own evidence, and S56's 2 px freshness rule on the live path (its OWNER DECISION) is unverified by me.
- **The server's HTTP re-run job**, against the in-process `BatchRun`.
- **A new run writing CHART end to end.** Only the unit tests (which fail without the hunk) and the band rule against today's VSP answer were checked.
- **The AAVSO page itself**, and whether `OBSTYPE=CMOS` is accepted: not fetched. The exports role got 403.
- **XX Cyg magnitudes against an independent reduction:** none exists.
- **An end-to-end run with S72 enabled.** It is off by default and the e-/ADU is undecided.
- **The old live files' aperture offsets with my fitter.** It wandered at SNR 4-10 from off-centre starts, so it is not used. The live-vs-re-run aperture distance on `050148Z` is 0.6-2.9 px (`evidence/live_vs_rerun_X29.json`).

## Findings

**F1 (medium, S69 b).** `tracking.centring_offsets` measures a star's centroid with `refine_centroid` inside its aperture. A brighter set star 6.9 px away drags it out of the aperture, so a correctly placed faint star is flagged off-centre: 000-BJV-173 on 7 of 24 frames, 0.03-0.20 px off by my fit and ASTAP; 8 of 8 seeds on the S69 test's own synthetic field. One more false flag sits at the SNR-5 gate (178, 050148Z frame 5).
- Effect: the star leaves the ensemble and its row turns suspect. For a faint check star beside a bright one, KMAG would be lost.
- Fix: measure the centring centroid in a window that excludes brighter set stars (radius ≤ 0.45 × the distance to the nearest brighter set star), or fit the neighbour jointly. Otherwise do not test such a star, and record it as "blended, not tested".
- Test to add: the faint star of the existing synthetic field.

**F2 (medium, S67 vs S58).** The batch re-run (Qt worker and `rerun.py`) writes a target point measured at SNR < 3 unflagged: `040723Z` `_00021`, 13.290 ± 0.750. S67 drops this row from the old file, yet the re-run that the S56/S67 notes point to puts it back into the AAVSO export. Re-run recorders are off by default, so the import cannot apply S67 either.
- Fix: in the worker and `rerun.py`, flag the frame's points suspect when a target is below `NO_DETECTION_SNR` (3) or its zero point is more than 1 mag from the run median, as S67 does. Test it on that frame.

**F3 (medium, S66).** The per-frame (batch) and median (Review) site checks take a frozen header pointing (X1) for a wrong site: 165 of 195 frames get the frozen AIRMASS, up to 0.331 off, on a run whose site was right.
- Fix: trust the header only when the pointing is live. Pointing keys identical on frames more than 60 s apart, or a site fit over the run with residuals above about 0.5°, mean "compute from the site".
- Apply it in `core/session/review.py`, the batch worker's `_frame_site_check` and `rerun.py`, with a test built from this case.

**F4 (medium, S72 / S7x confirmed).** My independent photon transfer gives 0.234 e-/ADU and shows that the data are 12-bit × 16. The frames' EGAIN (0.8 or 1.723) is 3.4-7.4× too high. As decided, S72 cannot pass its test, and the formal errors stay 1.6-2.2× too small on star pairs.
- OWNER DECISION, already open: recommend the model role's option B (measured 0.20-0.23 e-/ADU at gain 80) together with a scintillation term (§5).

**F5 (low, S7x (new) candidate).** The annulus median of a plane that steps by 8 ADU is quantised and less efficient than a clipped mean. On `040723Z` the clipped mean gives 11 % lower pair scatter.
- OWNER DECISION: (a) keep the median; (b) a 3σ-clipped mean (Siril and photutils offer it); (c) a DAOPHOT-style mode.
- Recommend (b), after a test over more runs; with too few pairs the case is not made.

**F6 (low, notes).** Release notes (S56 old-file bullet, about line 433): a re-run of `050148Z` now gives 13 frames verified by a fresh solve, not 12. Also, the tracker's "RR Lyr comparison offsets 0.13-0.14 px" is measured against the ASTAP projection; against the stars it is 0.24-0.43 px (median).

## Scripts and evidence

All in this folder.

**Scripts** (`scripts/`):
- `make_setup.py`: variants and private configs (deleted after use).
- `rerun_parity.py`: the tracker role's.
- `lb_exports.py`, `qt_exports.py`, `api.py`: the exports role's, on port 8795.
- `rerun_level_a.py`, `aavso_fields.py`, `vsp_check.py`, `s68_bands.py`.
- `offsets.py`, `s69_blend.py`, `s69_astap_173.py`.
- `noise_check.py`, `sky_estimator.py`, `s71_check.py`, `s66_frozen.py`.
- `fail_without_hunk.py`, `revert_hunks.py`, `server_fail_without_port.py`, `suites.sh`.
- `live_vs_rerun.py`, `myphot.py`.

**Evidence** (`evidence/`):
- `exports_final.json`/`.log`, `rerun_parity_*.json`, `rerun_level_a.json`, `aavso_fields.json`, `rerun_aavso_preview.json`.
- `vsp/` (live VSP answers), `vsp_check.json`, `s68_bands.json`.
- `offsets_{X07,X29,RR2,RR6}.json`, `s69_blend.json`, `s69_astap_173.json`.
- `noise_check.json`, `sky_estimator.json`, `s71_check.json`, `s71_plain_median_tests.txt`, `s66_frozen.json`.
- `fail_without_hunk.json`, `server_fail_without_port.json`, `suite_*.txt`, `live_vs_rerun_X29.json`.
