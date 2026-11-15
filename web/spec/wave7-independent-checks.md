# Wave 7: independent checks (level a) and parity (level b)

The W7 exit criterion (`waves.md` §5, `progress.md` Wave 7): results checked first
against references that do not depend on ARGOS or Qt, then byte for byte against the
fixed Qt. Sections 1-8 are the science review's (copied from its working notes, figures
unchanged); section 9 says what the fixer pass changed and the figures after it.

Run 2026-11-15 on APFS clones of the owner's sessions XX Cyg 2026-08-29 (`20260829T050148Z`),
XX Cyg 2026-09-07 (`20260907T040723Z`) and RR Lyr 2026-09-25 (`20260925T200453Z`). The server
ran on port 8777 from the working tree (base 04ae0cb plus W7). "Fixed Qt" means the
release/0.5.0 worktree (ed8f7e5 plus the uncommitted S60-S63), imported first on `sys.path`
and asserted.

The references do not depend on ARGOS code: astropy 6, numpy, my own aperture photometry
and centroids, the star_var_script + Siril reductions in `results/`, the VSP catalogue
magnitudes, and the AAVSO Extended File Format rules. aavso.org returned 403, so the rules
were checked offline. No site coordinates, observer name or observer code are printed; the
tests use the code `TST01`.

The scripts and their JSON outputs (`siril_compare.py`, `times_airmass.py`,
`aavso_validate.py`, `exports_check.py`, `rerun_centroids.py`, `ensemble_weighting.py`,
`noise_model.py`, …) stayed in the reviewers' scratch folders: they read the owner's
files and are not part of the repository. Every figure below names the script that gives
it.

## 1. Times (astropy, from DATE-OBS + EXPTIME/2)

`times_airmass.py` → `evidence/times_airmass.json`. 0.4.x DATE-AVG is late (S36), so it is
not used.

| Session | Points (target) | jd_utc − mid-exposure, max | bjd_tdb − astropy, Settings site | bjd_tdb − astropy, mount-fitted site |
|---|---|---|---|---|
| XX Cyg 08-29 | 22 | 0.0009 s | 0.0009 s | 0.0007 s |
| XX Cyg 09-07 | 24 | 0.0010 s | 0.0010 s | 0.0011 s |
| RR Lyr 09-25 | 195 | 0.0010 s | 0.0010 s | **0.0154 s** (wrong Settings site) |
| RR Lyr re-run, fitted site in Settings | 195 | 0.0000 s | n/a | 0.0000 s |

Every comparison curve agrees as well, each computed with its own coordinates. The AAVSO
DATE is jd_utc to 6 decimals (0.09 s), the exposure midpoint, as the format asks.

## 2. Airmass (astropy AltAz at mid-exposure, Pickering 2002, at the site fitted to the mount)

The site is fitted to the header ALTITUDE/AZIMUTH of every frame. The median residual is
0.0013-0.0027° and the maximum 0.018°. The Settings (header SITELAT/LONG) site lies
2.3° (08-29), 3.3° (09-07) and **82.8°** (RR Lyr) from the fitted site.

| Session | True airmass | Header AIRMASS − true | CSV airmass − true | AAVSO AMASS (web = fixed Qt) |
|---|---|---|---|---|
| XX Cyg 08-29 | 1.0602-1.0647 | ≤ 0.00009 | ≤ 0.0001 (0.4.1 wrote the mount's) | right (≤ 0.0005) |
| XX Cyg 09-07 | 1.0809-1.0895 | ≤ 0.00044 | ≤ 0.0004 | right (≤ 0.0007) |
| RR Lyr 09-25 | 1.0333-1.3644 | ≤ 0.00035 (at the start: ≤ 0.00012) | **+1.03 median, up to +3.05** (1.514-4.088) | **wrong, up to +3.055** |
| RR Lyr re-run, right site in Settings | 1.0333-1.3645 | n/a | ≤ 0.00008 | right (1.033 on row 1) |

A69 serves `header_airmass` and `airmass_source: header` for RR Lyr, and R1 plots it.
A77/A78 still write the CSV airmass, as the fixed Qt does. The preview warns.

## 3. RR Lyr 2026-09-25 magnitudes against star_var_script + Siril (`siril_compare.py`)

Matching is by time: worst gap 0.043 s, which is Siril's rounding of the JD. The comparison
leaves out the 2 blank-sky frames (_00053, _00176) unless the row says "all points". The
combined error is the quadrature sum of ARGOS mag_err and Siril err, both with their floors.

| ARGOS curve | Reference | n | Median offset | Robust σ | Std | Median combined err | χ²ᵣ (total err) | Drift over run |
|---|---|---|---|---|---|---|---|---|
| Live CSV as written (6 comps) | Siril green, 2 comps | 193 | −0.0114 ± 0.0016 | 0.0176 | 0.0239 | 0.0297 | 0.62 | −0.003 |
| Live CSV, all 195 points | Siril green, 2 comps | 195 | −0.0114 | 0.0181 | **0.106** | 0.0298 | 0.63 | −0.039 |
| 2 comps (665+666), recomputed from the recorder | Siril green, 2 comps | 193 | **+0.0014 ± 0.0009** | 0.0096 | 0.0167 | 0.0263 | 0.35 | +0.007 |
| Same, formal errors only (no floors) | Siril green, 2 comps | 193 | +0.0014 | 0.0096 | 0.0167 | 0.0170 | **0.91** | |
| **A76 re-run, 2 comps + check 523** (= fixed Qt, byte for byte) | Siril green, 2 comps | **195** | **+0.0020 ± 0.0009** | 0.0099 | 0.0168 | 0.0296 | 0.28 | +0.007 |
| 2 comps from the recorder | Siril CFA (no channel split), 2 comps | 189 | −0.0070 | 0.0242 | 0.0245 | | | +0.008 |
| 2 comps from the recorder | Siril CFA, 5 APASS comps | 192 | −0.0338 | 0.0322 | 0.0372 | | | −0.012 |
| Siril CFA 2 comps (VSP) | Siril CFA 5 comps (APASS) | 190 | −0.0301 | 0.0287 | | | | −0.018 |
| Siril CFA 2 comps | Siril green 2 comps | 191 | +0.0051 | 0.0240 | | | | 0.000 |

Validation of the inputs:

- The recorder's 6-comp recomputation, with ARGOS's published rule (mean(cat − inst), median±max(2.5·MAD·1.4826, 10 mmag) clipping), equals the CSV on 194 of 194 points (max |Δ| 0.0000).
- My own aperture photometry of the raw (G1+G2)/2 plane, at the recorder's centres with ARGOS's aperture, equals ARGOS's instrumental magnitudes (Δ = 0.0000, n = 193).
- The re-run equals the recorder's 2-comp recomputation (median +0.0002, σ 0.0012).

**Additive budget of the −0.011 (means over the same 193 frames):**

| Term | Mean | Median | Robust σ | Cause |
|---|---|---|---|---|
| Total: live (6c) − Siril green (2c) | −0.0112 | −0.0114 | 0.0176 | |
| Comparison set: 6c − 2c (665+666) | −0.0103 | −0.0087 | 0.0124 | The comparisons' catalogue residuals (cat − measured, against the 6-star ensemble, median over the run): 665 +0.0025, 666 +0.0153, 667 −0.0048, 523 −0.0026, 668 −0.0140, 953 +0.1615 (almost always clipped). The 2-comp zero point is +0.0089 above the ensemble's. The residuals do not follow B−V (667, at B−V 0.99, sits at −0.005), so the residual set is catalogue noise of about 0.01, not a colour term. |
| Zero point: mean of magnitudes − flux mean (Siril's "flux-mean catalogue V = 7.722") | +0.0010 | +0.0011 | 0.0022 | Second-order difference between the two averaging rules |
| Aperture: ARGOS 2.5 FWHM (annulus 8-12) − Siril-like 2 FWHM (dyn_ratio 4 = radius/half-FWHM; annulus 10-15) | −0.0019 | −0.0013 | 0.0051 | A fixed r = 10 does not reproduce Siril (σ 0.020): Siril's aperture is dynamic |
| Rest: my Siril-like − Siril | −0.0001 | +0.0019 | 0.0075 | Registration and interpolation, PSF centroid, sky estimator |

The terms add up to −0.0113 against −0.0112 measured. The like-for-like pair (ARGOS 2 comps
vs Siril green 2 comps) agrees to +0.0014 ± 0.0009 mag. Its scatter is consistent with the
formal errors alone (χ²ᵣ 0.91). With the floors, χ²ᵣ falls to 0.3: both floors model
scintillation and flat-field noise that the two reductions share, because they measured the
same photons.

The channel term (CFA − green, +0.005, σ 0.024) and the APASS set (−0.030, drift −0.018 over
airmass 1.03 → 1.36) are differences between the reference reductions themselves, not ARGOS
errors.

`rrlyrae_template_fit.json` cannot serve as a reference. The three fits disagree with one
another by 1.2 mag in m_max and 0.18 d in epoch_max, with phase coverage 0.22 and no maximum
observed. The Sesar templates are offline as well.

## 4. Check stars against VSP V (the check is never part of the ensemble)

| Run | Check (VSP V) | Ensemble | n | Mean − V | Std | Median err | χ²ᵣ | Expected from colour |
|---|---|---|---|---|---|---|---|---|
| RR Lyr, recorder, 5 comps (523 removed) | 000-BCG-523 (7.015) | 5 VSP, clipped | 193 | +0.011 ± 0.002 | 0.027 | formal 0.011 | 6.1 (formal) | Within the catalogue residuals of section 3 (±0.01) |
| **RR Lyr A76 re-run** (= fixed Qt) | 000-BCG-523 | 665 + 666 | 194 | **+0.017 ± 0.002** | 0.022 | mag_err 0.0215 | **0.98** | The 2-comp zero point is +0.009 (section 3), plus catalogue noise |
| XX Cyg 09-07, recorder | 000-BJV-169 (10.283) | 7 VSP | 24 | −0.066 ± 0.013 | 0.065 | formal 0.052 | 1.5 | −0.002 (colour): **not explained** |
| **XX Cyg 09-07 A76 re-run** (= fixed Qt) | 000-BJV-169 | 7 VSP | 24 | **−0.061 ± 0.017** | 0.083 | mag_err 0.095 | 0.52 | Comparison apertures 4-6 px off their stars (section 6) |
| XX Cyg 08-29, recorder | 000-BJV-171 (10.606) | 4 (3 at V 12.9-14.2, SNR < 10) | 22 | **+0.28 ± 0.08** | 0.39 | formal 0.29 | 6.2 | Inverse-variance weighting of the same comparisons: +0.07 ± 0.02, p2p scatter 0.13 instead of 0.43 |

Point-to-point scatter of star pairs on the same frames, against the formal errors
(`error_model_pairs.py`): ratio 1.3-3 on every pair. Formal errors alone always
underestimate the scatter; `sigma_syst` closes that gap, which gives χ²ᵣ 0.98 for the RR Lyr
re-run check.

## 5. AAVSO Extended File Format, field by field (`aavso_validate.py`)

Checked on 7 files from A78: the 3 sessions × (session source, import source), plus the
RR Lyr re-run with check star.

| Item | Rule | Found |
|---|---|---|
| `#TYPE=EXTENDED` | first line | ok |
| `#OBSCODE` | the observer's code; never XXX | ok (TST01). An empty code or XXX is refused: 409 `obscode_unset`, preview refusal |
| `#SOFTWARE` | name and version | **`Argos`, no version** (warning). Fixed in release/0.5.0 as **S64** (`Argos v<version>`, the FITS `SOFTWARE_ID`); the web export writes what the core it imports writes, so both stay identical (section 9) |
| `#DELIM` | not # or space | `,`; no field contains a comma |
| `#DATE` | JD / HJD / EXCEL | JD (UTC midpoint), within 0.001 s of astropy |
| `#OBSTYPE` | CCD / DSLR / PEP (CMOS not checked: spec unreachable) | CCD (a CMOS one-shot-colour camera: owner decision already open) |
| NAME | ≤ 30 characters | `RR LYR`, `XX CYG` |
| DATE | ≤ 16 characters, no JD 0 | 14 characters; S60 guard (no undated row) |
| MAG / MERR | numeric, MERR > 0 | ok; MERR = formal ⊕ sigma_syst |
| FILT | AAVSO code | TG (green channel of a colour camera: correct; comparisons on V) |
| TRANS / MTYPE | NO / STD | ok |
| CNAME / CMAG | ENSEMBLE / na | ok |
| KNAME / KMAG | the check's AUID / its ensemble magnitude on the same frame | 195 of 195 equal to the check curve (re-run). No check in the owner's runs: na, with a warning |
| AMASS | the airmass | **RR Lyr session: wrong by up to 3.055**; right elsewhere |
| GROUP | ≤ 5 characters or na | na |
| CHART | VSP sequence ID | **na on every file** (targets.json has `chart_id: null`) |
| NOTES | ≤ 100 characters | na |
| One filter per report (S53) | | Synthetic 2-filter clone: no filter given → `multiple_filters`; `filter=lp` → the lp MAG and KMAG, plus the LP band note; CSV of 2 filters → 409 (S61) |
| Flagged points | saturated or suspect left out and counted | 0 in the owner's files. **The release notes' old-file rules (S35, S56) are not applied to the file**: Review now flags those frames and the preview names them (section 9); leaving them out is an owner decision |

## 6. Re-run (A76) against the fixed Qt worker and the references

The Qt side ran the release worktree's own `discover_light_frames` and its own ASTAP path
(`batch_frame_solver` about the reference header). The site was the mount-fitted one,
written to a private config that is deleted afterwards.

| Run | Frames | Re-solved (S43) | Unanchored / unverified (S58) | Files | Bytes vs fixed Qt |
|---|---|---|---|---|---|
| RR Lyr, 2 comps + check 523 | 195 (390 outside lights/ left out, S63) | 2 / 2 | 0 / 0 | 4 CSV + targets.json | **identical (5/5)** |
| XX Cyg 09-07, 7 comps + check 169 | 24 | 0 / 0 | 0 / 0 | 9 CSV + targets.json | **identical (10/10)** |

- Each re-run writes `photometry_rerun_<UTC>` inside the session clone and nothing else.
- RR Lyr: re-run − live = +0.0097 median (2 comps against 6, section 3). The maximum, 1.45 mag, is on the 2 blank-sky frames, which the re-run re-solved (now 7.482 and 7.704).
- XX Cyg 09-07: re-run − live = −0.026 median, robust σ 0.17, up to 0.50 mag on one point (target SNR about 6).
- Aperture centres against the stars' real centroids, from the re-run's recorder (`rerun_centroids.py`): 000-BKZ-945 median 4.3 px, maximum 5.9 px; 000-BLY-578 4.2 / 5.2 px; 000-BJV-173 4.9 / 5.8 px. The aperture radius is 5.47 px, and the lock check never flagged a frame.

## 7. Level (b): byte identity with the fixed Qt

`exports_check.py` → `evidence/exports_check*.json`.

| Session | A78 session vs Qt (session curves → Photometry window) | A78 session / A78 import vs Qt "Open curve CSV" → Export AAVSO | A79 session vs `write_curves_csv(load_session_curves)` | A79 import vs Qt Export measurements | A69 vs Qt `load_session_curves` (15 fields, every point) |
|---|---|---|---|---|---|
| XX Cyg 08-29 | = | = / = | = | = | = (6 curves; the alias target CSV is dropped as in Qt) |
| XX Cyg 09-07 | = | = / = | = | = | = (9 curves) |
| RR Lyr 09-25 | = | = / = | = | = | = (7 curves) |
| RR Lyr re-run, target + check (multi-curve CSV) | n/a | = | n/a | n/a | n/a |

The only A69 difference: the server's filter token `ir` comes from the session's frames,
where Qt has `""` for these pre-S49 file names. That difference is intended
(`<AUID>@<token>`), and the file bytes are unaffected.

## 8. Frame inspector (A71, A73)

- A71: the frame body equals the FITS pixels as little-endian uint16 (3840 × 2160, 728 header bytes).
- A73, RR Lyr frame 1: the centroid matches mine to 0.01 px, and the peak matches exactly.
- A73 FWHM (moments): 1.69-1.90 green px. A Gaussian fit to the core gives 1.43-1.54, and the frame metric is 2.12-2.16. These are three estimators of an under-sampled PSF; none is wrong.
- A73's "SNR" is peak over sky σ (1090 for RR Lyr). The curve's SNR is the aperture SNR (148). R2 now labels it "Peak/σ" (section 9).

## Not checked

- The RR Lyr template fit (see section 3).
- XX Cyg magnitudes against an independent reduction: none exists, so only the check stars were used.
- The AAVSO spec page live (403), and whether `OBSTYPE=CMOS` is accepted.
- Gaia, SIMBAD and NASA.
- The UI screens, which the integrator covered. I captured no extra screenshots: every finding here is reproducible from the scripts.

## 9. After the fixer pass (2026-11-15)

The fixes below leave every magnitude, error, time and airmass of sections 1-7 as they
were: the writers and the re-run are untouched, so the level (b) identities hold as
measured. What changed:

**Review now says what the release notes' old-file rules find** (A69 flags, R1 readiness,
R0 issues, the AAVSO preview), on the clones of the three sessions (`fixer_checks.py`):

| Session | R1 readiness | R0 issues | Vetting (R0) | Target rows the AAVSO file still writes, flagged |
|---|---|---|---|---|
| XX Cyg 2026-08-29 | `unverified_lock` 22 | 1: 22 frames, fewer than 3 anchors at SNR 10 (S56) | 0/5 stable | 22 (S56 rule, conservative) |
| XX Cyg 2026-09-07 | `flagged_points` 1 | 1: 1 frame flagged by the recorder | 3/8 | 1 (low_snr, JD 2461290.69160) |
| RR Lyr 2026-09-25 | `site_mismatch`, `flagged_points` 2 | 2: the site, 2 frames | 6/6 stable | 2 (_00053, _00176: JD 2461309.37002 and .44327) |

The S56 counts are the notes' own (every frame of `050148Z`; RR Lyr frames 52 and 175,
already flagged as no detection): a server test asserts them on the owner's sessions.
R0's issue count now equals R1's badge on all three. The two blank-sky frames are drawn
hollow, kept out of each cell's y range (a chevron on the edge when off-scale) and their
error bars drawn at half the error ink; they are still written to the AAVSO file, as the
fixed Qt writes them (OWNER DECISION, below).

**#SOFTWARE (S64)**: `write_aavso` stamps `argos.SOFTWARE_ID` (`Argos v<version>`) by
default, in release/0.5.0 (`test_aavso_header_names_the_software_and_its_version_s64`,
fails before). The server passes no `software=`, as Analyze does, so the two writers stay
byte-identical in each tree: `#SOFTWARE=Argos` with the main tree's core today, `Argos
v<version>` once release/0.5.0 is merged. No guard is needed.

**Measure star on a calibrated float frame (S65 and A73)**: a frame in [0, 1] (Siril's
`r_light_*.fit`) is measured in counts (× 65535): on a synthetic star, SNR and peak equal
the counts frame's to 1 % (before: SNR 0, peak 0). The answer says `"scale":
"converted"`. R2 labels `snr` "Peak/σ".

**Still open (owner decisions, unchanged figures)**: AMASS of RR Lyr written for the wrong
Settings site (1.514-4.088 against 1.033-1.364, section 2); the flagged target rows above;
the tracker on XX Cyg 2026-09-07 (comparison apertures 4-6 px off, check −0.061, section
6); the unweighted ensemble zero point (XX Cyg 2026-08-29 check +0.28 ± 0.08, section 4);
the noise model (green-plane gain and black level, section 4); `#OBSTYPE=CCD` for a CMOS
camera.
