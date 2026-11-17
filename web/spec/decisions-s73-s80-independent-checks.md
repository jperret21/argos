# S73-S80 (and S81-S83): independent checks

The owner's decisions of 2026-11-16 (S73-S80) were implemented by a noise role and a
geometry role, then checked by three roles with their own code: a **validation** (level
(a) against references independent of ARGOS, level (b) server against the fixed Qt, the
gates on every study run), a **science review** and a technical review. The owner's calls on
the validation's open items (the same day) were then applied by a **fixer** pass, which
also numbered the three new defects S81-S83. This file keeps the two independent-check
reports as they were written (parts B and C), after part A: what the owner decided and what
the final code measures. Part D, at the end: the owner's next calls of the same day (S76
adopted, S73's order, S84) and that pass's final numbers.

Every number names the script and evidence file that made it; they lived in the roles'
scratch folders (`scratchpad/s73/<role>/scripts`, `evidence`), not in the repository.
No site coordinates or observer data appear here: sites stayed in scratch configs, deleted
after the pass; the observer code in every test and export is `TST`. References used, none
from ARGOS: the frames' own photon transfer and green-plane sky σ, star-pair point-to-point
scatter, the star_var_script + Siril green reduction of RR Lyr 2026-09-25
(`results/RR_Lyr_green_argos_2comps`), astropy (times, airmass at the site fitted to the
headers' ALTITUDE/AZIMUTH), VSP V with its catalogue error, Gaia DR3, the reviewers' own
Gaussian centroids and aperture photometry.

## A. Final state (the fixer, 2026-11-16)

### A.1 The owner's calls, applied

| Item | Call | Done |
|---|---|---|
| F1 (S78) | Without a fitted site, a Settings site that S66 rejects (or a frozen pointing) never gives a comparison its own airmass: the header AIRMASS | Amended S78: the Settings site counts only when it reproduces the mount's pointing within 0.1° (the fitted site's standard; every study run lies 2.0-127° off); Review, the re-run, the live path (and the live fit no longer takes a frozen or slewing poll); server ports |
| F2 (S73) | Keep the 0.1 dB/step scaling; a scaled gain uses the measured 2.6 e- read noise; log every gain but 80 and 100 "scaled, not measured"; document the gain-65 frame | Done; the read noise also follows the frame's e-/ADU on every path (technical review); gain-65 ratio 0.889 |
| F3 (S74) | Keep C_Y = 1.5; record the measured 1.1-1.4 | Notes S74 |
| Anchors (S56/S69, F6) | Keep SNR ≥ 10; record the effect | Notes S56, S69 |
| S8x × 2 | S81 edge apertures, S82 SIMBAD object names | Qt first, failing-before tests, server ports |
| F7 | Correct the S77 and S79 notes figures | Done (5 of 6 XX Cyg 2026-08-29 stars matched; `053540Z`'s 000-BJV-173 and 000-BJV-180 crowded) |
| F8 | Review of an imported re-run folder reads its recorder, if cheap and safe | Not done: it touches Qt Review, the server's Review and the web import path; open (low) |
| S77 expectation | "sigma_syst back near 0.0152" is moot | Notes S77: the criterion is the aperture (0.990 → 0.077 px) |

The technical review's medium findings were applied too: **S83** (live and sequence
e-/ADU at the frame's own gain), the noise model's row on the web Settings page (with a
test that every key of a category whose page lists its keys is shown), the live-path
tests of S74, S77 and S78 (Qt and server), the re-run's Gaia lookup (5 s per cone, cache
after a failure, the cancel), the observer documentation (`docsrc/differential_photometry.md`
§3.3 and §5, `docsrc/fits_headers.md`, the Settings help texts); and, cheap, the low ones:
the opened frame's `EGAIN` comment in the server, the per-star airmass of S74 in re-runs
(never a frozen frame's stale AIRMASS), the separation across RA 0h (S77/S79), the
server's "Comparison crowded" WARN, the release branch's `black` on `hook-astropy.py`, the
asymmetric S73 interval in the notes. Every new regression test fails with its hunk
reverted in a scratch copy (26 of 26, fixer `revert_checks.json`).

### A.2 Level (a), final (Qt batch re-runs, ASTAP, each night's Settings site)

Before = release `3e48d78` (validation `level_a_before.json`); after = every S72-S83
change (fixer `level_a_after.json`, `compare_validation_vs_fixer.json`).

| Check | Before | After |
|---|---|---|
| Pair scatter / formal error, median (robust): RR Lyr 6 comparisons | 1.89 (1.63) | 0.95 (0.80) |
| same, RR Lyr 2 comparisons + check (RR2) | 2.27 (2.06) | 0.89 (0.77) |
| same, XX Cyg `040723Z` (X07) | 1.48 (1.41) | 1.11 (1.01) |
| same, XX Cyg `050148Z` (X29, 3 pairs) | 0.94 (1.03) | 0.71 (0.60) |
| 000-BCG-523 − VSP V (VSP ± 0.100) | +0.0162 ± 0.0016 | +0.0167 ± 0.0016 |
| 000-BJV-169 − VSP V (± 0.051) | −0.0735 ± 0.0090 | −0.0647 ± 0.0091 |
| 000-BJV-171 − VSP V (± 0.030) | +0.0507 ± 0.0227 | +0.0447 ± 0.0223 |
| RR Lyr − Siril green 2 comps: offset / robust σ | +0.0013 / 0.0096 | +0.0013 / 0.0101 |
| RR Lyr 6 comps − Siril: offset / robust σ | −0.0076 / 0.0153 | −0.0110 / 0.0147 |
| Model / measured green-plane sky σ: the three sessions (9 frames) | 0.34-0.48 | 0.959-1.035 |
| same, every gain-80 and gain-100 light (31); the gain-65 light | — | 0.959-1.049; 0.889 |
| RR Lyr aperture − Gaussian centroid, median (90th pct) | 0.990 (1.111) px | 0.077 (0.157) px |
| Comparison airmass − astropy, max: fitted-site runs | 0.0204 | 0.00007 |
| same, `195307Z`; `052943Z`; `053540Z` (no fit, wrong Settings site) | 3.854; 0.0129; 0.0126 (S78 first build) | 0.0017; 0.0012; 0.0012 (header) |
| same, `045156Z`; `045626Z` | 0.0078; 0.0084 (S78 first build) | 0.0069; 0.0069 (header) |
| RR Lyr target `sigma_syst` (RR2) | 0.0182 | 0 |

Against the validation's state (S73-S80 before the fixer): the RR Lyr 6-comparison set
writes 12 fewer comparison rows (S81: the edge rows; 13 → 1 rows within the annulus' reach,
the remaining one wholly on the frame, `edge_rows_summary.txt`) and moves −0.0116 → −0.0110;
RR2's robust σ 0.0099 → 0.0101 and its check +0.0166 → +0.0167 (S74's per-star airmass);
the gain-100 runs' comparisons' median SNR 24.0 → 23.8 and 6.5 → 6.4 (2.6 e-); nothing else.
Review on the cloned sessions: `052943Z`/`053540Z` comparisons within 0.0012 of astropy;
`195307Z`'s points matched to a light within 0.0017, its 2 points per star of no light
within 5 s keep the run's computed airmass for every star, the target included (S66, warned).

### A.3 Gates touched by the fixer's changes

Batch re-runs of all 20 variants: no change of frames done, skipped, re-solved,
unanchored, unverified, off-centre, no-detection, verify solves or flagged target points;
`frames_header_airmass` counts a measured frame without a point now (`034413Z_V`,
`194822Z`: 0 → 1, S74's per-star airmass reads it). Live replays (validation's
`gates_replay.py`, a solve every 20 s and one per run, 8 runs; `s54_repoint.py` the 500 px
jump with and without the anchor-frame rule; fixer `replay_compare.json`): identical points,
flags, skips and solves; RR Lyr's anchor counts 5 → 4 on 19 frames (000-BJW-667/668 at
the edge are no anchors, S81); the 500 px jump unchanged.

### A.4 Level (b), final

The validation's `parity.py` (server `rerun.BatchRun` against the fixed Qt worker, one
process, same frames, ASTAP solver, saved Gaia answer): X07, X29, RR2, the RR Lyr
6-comparison set, `195307Z` and `052943Z` (S78's amendment) **identical** (every CSV,
`targets.json`, every recorder record, counts, solver calls); `034413Z_V` (S82) writes no
CSV on either side (no star above SNR 1) and identical recorders (fixer `parity_*.json`).

### A.5 Open after this pass

The owner decided the first, third and fourth items below on 2026-11-16 and they are
applied (release notes S76 adopted, S73 amended again, S84 new): the 3σ-clipped annulus
mean with S75's factor 1 (RR Lyr − Siril 2 comps +0.0013 / 0.0101 → +0.0021 / 0.0083,
blank apertures' scatter over the code's error 1.42 → 1.16; the other study runs in
part D); the observer's photon-transfer file before the profile; the noise model in the
S15 run lock (Qt, server, web Settings), with the camera's e-/ADU inputs (part D). The
`zp_err` split and a C_Y refit wait for 0.5.x and more nights.

- OWNER DECISION (S76, science review F1, new evidence): adopt the 3σ-clipped annulus mean
  (S75's factor 1), or add the median's quantisation term to S75. Recommended: the mean.
- OWNER DECISION (S71/S74, science review F2): the ensemble `zp_err`'s rms branch and 0.01
  floor carry the comparisons' constant catalogue disagreement into every frame's error.
  Recommended (science review): a random part without them, a calibration term per run.
- OWNER DECISION (S73, technical review): the observer's own photon-transfer file ranks
  below the profile's measurement (read with the reference curve). Recommended: before the
  profile.
- OWNER DECISION (S72/S15, technical review): `photometry.noise_model` (and `read_noise_e`)
  can change during a run. Recommended: add them to the S15 lock.
- F8 (low): an imported re-run folder in Review reads no recorder (no faint-comparisons
  warning, S67 points described as "suspect").
- The web Settings page shows no `site.min_altitude_deg` (Observer & site; a known gap
  named in the new test).
- The server's S54 re-pointing check and pilot comparison quality take the Camera form's
  gain (no frame gain there; Qt takes the frame in hand's): they differ only for a step at
  another gain.
- S74's site height still comes from the header `SITEELEV` when the header site fails X3
  (about 6 % per 0.5 km on the term; no study run affected).
- The re-run reads each frame's header three times (+8-16 % on 195 frames).
- Not checked: a real capture's `EGAIN`/`RDNOISE`, the live S78 path with a real mount, the
  Qt S79 tab and the web Settings row visually, a frozen sidecar build, the AAVSO WebObs
  validator.

## B. The validation (as written, before the owner's calls)

Run 2026-11-16 by the validation role, with both implementation roles' work in.

**Code checked (neither tree was edited).**
- Release worktree: `3e48d78` plus the uncommitted S72-S80 diff (`git diff | shasum` 12b34f8c, `egain.py` 35199a76).
- Main tree: `fefed37` plus the uncommitted server port (`git diff | shasum` a01daf88).
- The fingerprints were the same at the start and at the end of the run.

**Scratch trees** (`scripts/mk_trees.sh`):
- `after`: the main tree's `argos` with the release worktree's `argos/{core,workers,ui}` overlaid, plus tests, packaging, pyproject and `web/{spec,src,src-tauri}`. Every GUARD is active in it.
- `before`: `git archive` of release `3e48d78` (`argos`), with main `3ba94ce`'s `argos/server`.

**Data and privacy.**
- Every study run is used as an APFS clone (`setup.py`). The three main sessions were also cloned whole, with `results/` and `process/`.
- Configs, HOME, TMPDIR and logs were private and temporary.
- The Settings site of each run is the first light's header SITELAT/SITELONG/SITEELEV (that night's Settings). The fitted site is fitted to the header ALTITUDE/AZIMUTH. Both stayed in scratch and were deleted at the end.
- Observer code: TST.
- A scan of every evidence file for the site values and the observer fields found only digit substrings inside SNR values.

**References used, none from ARGOS:**
- my own photon transfer;
- the measured green-plane sky σ;
- star-pair point-to-point scatter, and star_var_script's second-difference estimator;
- the star_var_script + Siril green 2-comparison reduction (`results/RR_Lyr_green_argos_2comps`);
- astropy 6 for times and airmass (Pickering, no refraction);
- VSP V and its catalogue error (live VSP API of 2026-11-15, `dw7/fixer/evidence/vsp_check.json`);
- my own Gaussian-fit centroids (`myphot.py`);
- the AAVSO Extended format rules;
- Gaia DR3 (live archive, reached today by the server's own lookup; the saved answer `gaia_pm_all.json` for the scripted re-runs).

### 0. Summary

| Check | Result |
|---|---|
| Suites, lint, packaging (§1) | all green: release 756 passed / 47 skipped; main 1721 / 81; server + packaging on the release core 952 / 3; web 0/0, 1167 tests, build OK |
| Level (b) server = fixed Qt (§2) | **7 of 7 identical**: 4 in-process re-runs and 3 HTTP A76 jobs; CSVs, targets.json (with proper motions), recorder records, counts and solver calls |
| S73 e-/ADU (§3.1) | my own photon transfer gives **0.2285** (16-84 %: 0.226-0.237) at gain 80 and 0.183 at gain 100. **Pass** |
| S72 sky σ (§3.2) | model / measured **0.957-1.049 on 31 frames** at gains 80 and 100 (the three sessions 0.957-1.035). It was 0.28-0.52 with the frames' EGAIN. **Fails on the gain-65 frame: 0.79** (F2) |
| Pair scatter / formal (§3.3) | medians **0.89-1.11** (robust 0.77-1.01), was 1.48-2.27; the bright end is now over-estimated (F3) |
| Check stars vs VSP (§3.4) | 000-BCG-523 +0.0166 ± 0.0016 (± 0.100); 000-BJV-169 −0.0647 ± 0.0091 (± 0.051); 000-BJV-171 +0.0447 ± 0.0223 (± 0.030). All within 1.3 σ of VSP; 169 and 171 improved |
| RR Lyr vs Siril (§3.5) | 2 comparisons +0.0013 / 0.0099 (was 0.0096, ± 0.0005). 6 comparisons −0.0116 / 0.0145: offset 4 mmag worse, σ better (F9) |
| Times (§3.6) | jd_utc = mid-exposure (0.0000 s); bjd_tdb = astropy at the moved position (0.0000 s) |
| Per-star airmass (§3.6) | comparisons within **0.00007** of astropy on the long runs (was 0.0204). **Fails on short runs** where no site can be fitted: up to **3.85** off on RR Lyr 195307Z (F1) |
| S77 offsets (§3.7) | RR Lyr aperture − Gaussian centroid 0.990 → **0.077 px** (90th percentile 1.111 → 0.157). **Pass** |
| S79 (§3.8) | the core's list equals my own on every study set; the notes miss 053540Z (F7) |
| S80 / overlay tracker (§3.9) | the web overlay tracker on 040723Z: lag 0.218-0.410° → 0.003-0.075°, fit error 3.85 → 0.21 px |
| Gates (§4) | 20 re-runs and 16 live replays before/after; every changed frame is explained (§4.3); one good live point newly flagged (F6); no blank-sky frame kept |
| S56 10 px (§4.2) | the 500 px jump: subs 44-46 still skipped, 47-48 (0.20 / 0.14 px from their stars) now verified; the RR Lyr set-change case is unchanged |
| AAVSO and Review (§5) | 6 files checked field by field: all pass; Review readiness as expected |
| New defects | F4 (edge apertures, the noise role's S8x) is confirmed; **F5**: S62 drops a "V* XX Cyg" frame |

### 1. Suites, lint, packaging (`scripts/suites.sh`, heavy lock per step)

| Step | Command (temporary HOME and TMPDIR) | Outcome | Evidence |
|---|---|---|---|
| Lint, release | `ruff check` and `black --check -l 100` on `argos tests main.py packaging` | clean | `evidence/suites/lint_release.txt` |
| Lint, main | same | clean | `lint_main.txt` |
| Release suite | `pytest -q` in the worktree | 756 passed, 47 skipped | `release_suite.txt` |
| Main suite (main core: every GUARD on its fallback) | `pytest -q` | 1721 passed, 81 skipped. The 6 `proper_motions` failures of the noise report are gone | `main_suite.txt` |
| Server on the release core (every GUARD active) | `pytest tests/server tests/packaging` on `trees/after` (packaging and src-tauri included) | 952 passed, 3 skipped. The path-loaded `review.py` hidden-import test passes with the release `review.py` | `overlay_server.txt` |
| Web | `npm run check`; `npm test -- --maxWorkers=4`; `npm run build -- --outDir <scratch>` | 0 errors, 0 warnings (796 files); 96 files / 1167 tests passed; build OK | `web_*.txt` |

GUARDs are feature checks only: `hasattr`/`getattr` on core params, tracking, gaia, review rules, `TargetSet`, `inspect` signatures. No version check anywhere in the server diff.

### 2. Level (b): the server against the fixed Qt

**In process** (`scripts/parity.py`, adapted from the geometry role's script):
- the server's `rerun.BatchRun` and the release `PhotometryBatchWorker`;
- same frames, ASTAP reference, params;
- base e-/ADU from the S73 chain (`egain.live`), here 0.228 "S30 Pro PTC";
- that night's Settings site and the same Gaia answer.

**Through HTTP** (`scripts/http_checks.py`):
- the A76 job on the server of `trees/after` (port 8802, simulator devices), using its own `_engine_egain` and its live Gaia lookup;
- against the Qt worker with the same reference solve call, site and e-/ADU, and the server's own Gaia cache read offline.

| Run | Path | Frames | Solver calls (Qt / server) | CSVs identical | targets.json | Recorder records | Counts |
|---|---|---|---|---|---|---|---|
| X07 (`040723Z`, check 000-BJV-169) | in process | 24 | 8 / 8 | 9/9 | = | = | = |
| X29 (`050148Z`, check 000-BJV-171) | in process | 22 | 10 / 10 | 6/6 | = | = | = |
| RR2 (2 comps + check 000-BCG-523) | in process | 195 | 2 / 2 | 4/4 | = | = | = |
| RR Lyr `200453Z`, 6 comparisons | in process | 195 | 2 / 2 | 7/7 | = | = | = |
| `050148Z` | HTTP A76 | 22 | n/a | 6/6 | = (5 proper motions) | = | = |
| `040723Z` | HTTP A76 | 24 | n/a | 9/9 | = (9) | = | = |
| `200453Z` | HTTP A76 | 195 | n/a | 7/7 | = (7) | = | = |

Evidence: `evidence/{X07,X29,RR2,20260925T200453Z_RR_Lyr}.json`, `evidence/http_*.json`.

### 3. Level (a)

#### 3.1 S73: my own photon transfer (`ptc_check.py` → `evidence/ptc_check.json`)

Written for this check, independent of the noise role's scripts:
- 7 gain-80 sessions and 2 gain-100 sessions;
- up to 6 consecutive light pairs each, raw G1 and G2 separately, stars masked;
- 128 px tiles, the 3σ-clipped variance of the difference / 2 against the level;
- one line `var = (level − 1024)/g + c`, bootstrap over sessions.

Iterated 3σ clipping keeps 0.968 of a Gaussian's variance (simulated with 16-ADU steps). The values below are corrected for it.

| Gain | Pair-planes | Level − black (ADU) | g (e-/ADU) | Bootstrap 16-84 % | Read noise from the intercept | Profile |
|---|---|---|---|---|---|---|
| 80 | 58 | 144-923 | **0.2285** (0.2361 raw) | 0.226-0.237 | 2.57 e- | 0.228 ± 0.005, 2.6 e- |
| 100 | 8 | 1191-2309 | **0.183** (0.189 raw) | 0.167-0.184 | 2.9 e- | 0.1811 (scaled), measured 0.183 |

#### 3.2 S72: model sky σ against the measured green-plane σ (`sky_sigma.py` → `evidence/sky_sigma.json`)

**Method.**
- First, middle and last light of every re-run.
- 3σ-clipped std in the 8-12 px annulus of each set star, median over the stars.
- The model is `sky_sigma_adu` with the parameters the after tree applies to that frame: `with_frame(egain=frame_egain(header))`.

**Results.**
- 31 frames at gains 80 and 100: **0.957-1.049**.
- The three main sessions: 0.957-1.035.
- With the frames' EGAIN: 0.281-0.517.
- Measured σ: RR Lyr 19.5-21.8 ADU; XX Cyg 09-07 29.0-29.6; XX Cyg 08-29 28.8-31.0 (the baseline was 20.5 / 29.7 / 31.2).
- 044527Z and 045156Z (60 s): 0.98-0.99. 045626Z (cloud): 0.96-1.00.
- **The exception is gain 65** (`034413Z`, 5.92 s, sky 56 ADU above black): **0.79**. See F2.

#### 3.3 Is the error model honest? Star-pair point-to-point scatter / formal error

Source: `level_a.py` → `evidence/level_a_{before,after}.json`, with `pairs_detail` for every pair. The rule is the noise role's: both stars at SNR ≥ 3, 13 px from the edges, at least 10 frames.

| Run | Pairs | Before: median (min-max) | After: median (p10-p90, min-max) | Robust, before → after |
|---|---|---|---|---|
| RR Lyr `200453Z`, 6 comps | 21 | 1.89 (1.30-2.87) | **0.95** (0.74-1.18; 0.71-1.34) | 1.63 → 0.81 |
| RR2 | 6 | 2.27 (1.71-2.86) | **0.89** (0.77-0.99; 0.75-0.99) | 2.06 → 0.77 |
| XX Cyg `040723Z` (X07 the same) | 36 | 1.48 (0.97-2.04) | **1.11** (0.93-1.25; 0.69-1.37) | 1.41 → 1.01 |
| XX Cyg `050148Z` (X29 the same) | 3 | 0.94 (0.90-1.52) | **0.71** (0.71-1.05) | 1.03 → 0.60 |

By the brightness of the pair (its median min SNR), after (before):

| Run | SNR 3-10 | SNR 10-20 | SNR 20-50 | SNR 50-100 | SNR ≥ 100 |
|---|---|---|---|---|---|
| RR Lyr, 6 comps | n/a | n/a | n/a | 1.11 (1.81), robust 0.85, n=11 | 0.80 (2.28), robust 0.73, n=10 |
| RR2 | n/a | n/a | n/a | n/a | 0.89 (2.55), robust 0.77, n=6 |
| X07 | 1.11 (1.48), n=21 | 1.06 (1.40), n=12 | 1.24 (1.58), n=3 | n/a | n/a |
| X29 | 0.71 (0.92), n=2 | 1.05 (1.52), n=1 | n/a | n/a | n/a |

A second, independent test is star_var_script's second-difference σ over the median formal error, on unflagged rows (`evidence/second_diff_ratio.txt`):
- RR Lyr curves 0.62-1.01 (median about 0.75), was 1.37-2.02;
- XX Cyg 09-07 0.83-1.38, was 0.98-1.83;
- the 08-29 target 0.63, was 1.43.

Verdict: the target "near 1" is met for faint and mid stars. For bright stars the errors are now **over-estimated by 1.2-1.6×** (the RR Lyr target 0.62; the bright pairs, robust, 0.73). That is S74's C_Y = 1.5 (F3).

#### 3.4 Check stars against VSP V, with VSP's own error

Unflagged rows, 5σ outliers removed, mean ± sem (`level_a.py`).

| Check (set) | Before | After | VSP error | Within √(VSP² + sem²) | χ²r with mag_err (before → after) |
|---|---|---|---|---|---|
| 000-BCG-523 (RR2) | +0.0162 ± 0.0016 | +0.0166 ± 0.0016 | ± 0.100 | yes | 0.97 → 0.59 |
| 000-BJV-169 (X07) | −0.0735 ± 0.0090 | **−0.0647 ± 0.0091** | ± 0.051 | 1.25 σ | 0.83 → 0.59 |
| 000-BJV-171 (X29) | +0.0507 ± 0.0227 | **+0.0447 ± 0.0223** | ± 0.030 | 1.2 σ | 0.42 → 0.41 |

The 171 rows flagged go 1 → 2: frame 14 is now flagged by S71 (§4.3).

#### 3.5 RR Lyr against star_var_script + Siril green, 2 comparisons

Matched within 20 s, n = 195.

| Set | Before | After | Notes |
|---|---|---|---|
| RR2 (Siril's own 2 comps) | +0.0013, robust σ 0.0096 | **+0.0013, 0.0099** (median error ± 0.0009) | σ +0.3 mmag, within its own uncertainty (about 0.0005) |
| 6 comparisons (the live set) | −0.0076, 0.0153 | **−0.0116, 0.0145** | offset −4.0 mmag: S71's weights follow the corrected errors (F9) |

- The re-run's frames 52 and 175 (the live run's blank-sky jumps, re-solved here) lie −0.0014 and +0.0006 from Siril (`evidence/rr_jump_frames.txt`).
- χ²r of (ARGOS − Siril) is 0.20-0.47. It is not an error test: both reductions share the frames' photon and scintillation noise, which cancel in the difference.

#### 3.6 Times and per-star airmass (astropy)

Source: `level_a.py`, `review_s78_short.py`, `aavso_check.py`.

**Times.**
- jd_utc − (DATE-OBS + EXPTIME/2): 0.0000 s on every CSV of every re-run, both trees.
- bjd_tdb − astropy at the run's Settings site:
  - at the proper-motion position, 0.0000 s;
  - at J2000, up to 0.0078 s (000-BJW-666; RR Lyr itself 0.0039 s, as S77 says).
- AAVSO DATE: within 0.044 s (6 decimals).

**Airmass, maximum |CSV − astropy at the fitted site|.**

| Run | Target (header AIRMASS) | Comparisons before (header) | Comparisons after (S78) | S78 site |
|---|---|---|---|---|
| RR Lyr `200453Z` (re-run and Review) | 0.00035 / 0.0003 | 0.0204 | **0.00007 / 0.0001** | fitted |
| XX Cyg `040723Z` | 0.00044 | 0.0069 | **0.00005** | fitted |
| XX Cyg `050148Z` | 0.00009 | 0.00058 | **0.00005** | fitted |
| XX Cyg `052943Z` (4 lights, 3.5 min) | 0.00005 | 0.00115 | **0.0129 (worse)** | Settings, 2.1° off |
| XX Cyg `053540Z` (4 lights) | 0.00005 | 0.00117 | **0.0126 (worse)** | Settings |
| XX Cyg `045156Z` / `045626Z` (3 lights) | ≤ 0.0001 | 0.0069 | 0.0078 / 0.0084 (worse) | Settings |
| **RR Lyr `195307Z`** (5 lights, 6 min; the night's wrong Settings site, S66 `frames_site_wrong` 5/5) | 0.00027 | 0.0017 | **3.854** (CSV 4.879 where the true value is 1.025); Review 3.32-3.76 | Settings, though S66 says it is wrong |

This is F1.

#### 3.7 S77: RR Lyr aperture offsets (`offsets.py` + `myphot.py`)

Aperture centre (recorder) minus my Gaussian-fit centroid on the raw green plane, RR2, 195 frames. Values are median (90th percentile), in px.

| Star | Before | After |
|---|---|---|
| RR Lyr 000-BCG-719 | 0.990 (1.111) | **0.077 (0.157)**, target 0.3 px |
| 000-BJW-665 | 0.272 (0.393) | 0.135 (0.260) |
| 000-BJW-666 | 0.432 (0.531) | 0.091 (0.163) |
| 000-BCG-523 | 0.280 (0.449) | 0.140 (0.315) |

The decision's "sigma_syst back near 0.0152" cannot be tested as stated: with S72-S76 the RR Lyr sigma_syst is 0 (0.01824 before). The formal errors carry the scatter, and over-carry it (§3.3).

#### 3.8 S79 crowding (`crowding_check.py` → `evidence/crowding_check.json`)

**Method.** My own list: astropy separations; a brighter set star by V, or one without V, within 2 r_ap. The scale, 7.48"/green px, comes from the IMX585's 2.9 µm pixel and the 160 mm focal length, not from ARGOS. The core's `crowded_stars` was run at the same radius.

**Result.** They agree on all 20 sets.
- `040723Z` (and `044527Z`): 000-BJV-173 (by 000-BJV-169, 1.47 mag, 50.6").
- **`053540Z` (XX Cyg 2026-08-29): 000-BJV-173 and 000-BJV-180** (by 000-BJV-173, 2.40 mag, 59.6"). The notes say "none on XX Cyg 2026-08-29" (F7).
- RR Lyr: none.

#### 3.9 S80 and the web overlay tracker

**Overlay tracker** (`field_track_lag.py` → `evidence/field_track_lag_X07.json`): `040723Z` from frame 0's solve, no re-solve, against each frame's ASTAP solution. Lag 0.218-0.410° → 0.003-0.075°; anchor fit error 3.85 → 0.21 px.

**Core rejections** (S80, `anchors_inconsistent`):
- 2 on the gain-65 no-star frame (anchors on noise);
- 2 on `045626Z`'s cloud sub;
- none on good frames.

### 4. Gates, before and after

#### 4.1 Batch re-runs (fixed Qt worker, ASTAP, every study run)

Sources: `rerun_all.sh`, `gates_diff.py` → `evidence/gates_diff.json`, `evidence/gate_tables.md`.

| Run | Frames | S58 verify solves | Unanchored | S69 rotation re-solves / off-centre | S67 no-detection frames | Flagged target / other rows | Solver calls | Anchors median (min) | Comparisons' median SNR (faint warning) |
|---|---|---|---|---|---|---|---|---|---|
| 08-29 `034413Z_V` (gain 65, LP) | 1 | 0 | 1 | 0 / 0 | 1 | 0 / 2 → 0 | 1 | 6 → 4 | 0 (yes) |
| 08-29 `041508Z` | 1 | 1 | 0 | 0 / 0 | 0 | 0 / 0 | 1 | 2 | 0.9 → 0.7 (yes) |
| 08-29 `050148Z` | 22 | 13 → 9 | 0 | 0 → 1 / 0 | 0 | 0 / 5 | 13 → 10 | 2 (1) → 1 (1) | 1.8 → 1.4 (yes) |
| 08-29 `052943Z` | 4 | 2 | 0 | 0 / 0 → 1 | 0 | 0 / 2 → 3 | 2 | 2.5 (2) → 1.5 (1) | 5.4 → 4.1 (yes) |
| 08-29 `053540Z` | 4 | 4 → 2 | 0 | 0 / 0 → 1 | 0 | 0 / 4 → 5 | 4 → 2 | 2 (2) → 1.5 (1) | 3.2 → 2.0 (yes) |
| 09-07 `040723Z` | 24 | 0 → 1 | 0 | 7 / 0 | 1 (`_00021`) | 1 / 0 | 7 → 8 | 5 (4) → 4 (2) | 20.8 → 15.6 (no) |
| 09-07 `044527Z` (60 s) | 2 | 0 | 0 | 0 / 0 | 0 | 0 / 0 | 0 | 6 | 50.8 → 26.4 (no) |
| 09-07 `045156Z` (gain 100) | 3 | 0 | 0 | 0 / 0 | 0 | 0 / 0 | 0 | 6 | 51.2 → 24.0 (no) |
| 09-07 `045626Z` (gain 100) | 3 | 0 | 0 → 1 | 0 / 0 | 1 | 1 / 1 → 8 | 0 → 1 | 6 (5) → 3 (3) | 14.6 → 6.5 (**no → yes**) |
| 09-07 `051839Z` RR Lyr | 1 | 0 | 0 | 0 / 0 | 0 | 0 / 0 | 0 | 6 | 132 → 99 (no) |
| 09-25 `194741Z` | 1 | the reference did not solve (both trees) | | | | | | | |
| 09-25 `194822Z` | 1 | 0 | 1 | 0 / 0 | 0 | 0 / 0 | 1 | 0 | none (both) |
| 09-25 `195011Z` / `195307Z` / `200100Z` / `200326Z` | 1 / 5 / 1 / 1 | 0 | 0 | 0 / 0 | 0 | 0 / 0 | 0 | 3-6 | +10 to +14 SNR (no) |
| 09-25 `200453Z` (6 comps) / RR2 | 195 | 0 | 0 | 0 / 0 | 0 | 0 / 0 | 2 (S43 jumps at 52 and 175) | 6 (3) / 3 (3) | 101 → 112 / 110 → 119 (no) |
| X07 | 24 | 0 → 1 | 0 | 7 / 0 | 1 | 1 / 1 → 0 | 7 → 8 | 5 (4) → 4 (2) | 18.5 → 13.9 |
| X29 | 22 | 13 → 9 | 0 | 0 → 1 / 0 | 0 | **1 → 2** / 3 → 4 | 13 → 10 | 2 (1) → 1 (1) | 1.7 → 1.4 (yes) |

No frame is skipped in either tree. No S43 re-solve is gained or lost.

#### 4.2 The live path

**Method.** The Qt sequence path (AcquisitionEngine + controller gates) on the 8 runs with cached ASTAP solves, a solve every 20 s and one per run. Sources: `gates_replay.py`, `replay_diff.py` → `evidence/replay_diff.json`, `gate_tables.md`.

| Replay | Schedule | Flagged frames | Skipped (lock lost / field lost) | Solves | Unverified WARNs |
|---|---|---|---|---|---|
| `050148Z` | one solve per run | [0, 13-16] → **[0, 19]** | none | 23 → 16 | 2 |
| `050148Z` | 20 s | [0, 13-16] → [0] | none | 23 | 2 → 1 |
| `052943Z` | both | [0] | none | 4 → 3 / 5 | 1 |
| `053540Z` | both | [0, 1, 2, 3] → [0] | none | 5 | 1 |
| `040723Z` | both | none | none | 8 → 9 / 25 | 0 |
| `044527Z`, `045156Z` | both | unchanged | none | unchanged | 0 |
| `045626Z` | both | none | none → frame 2 lock lost (cloud sub) | 1 → 2 / 4 | 0 |
| RR Lyr `200453Z` | one solve per run | unchanged, 193 points | frames 175 / 52 | 3 | 0 |
| RR Lyr `200453Z` | 20 s | unchanged | frames 52, 175 lock lost → field lost (still skipped) | 196 | 0 |
| RR Lyr 0-39 set change (+000-BCG-653), with and without S52 | | 0 → 0 | none | 7 | 0 |

**The S56 jump case** (`s54_repoint.py`: subs 44-48 moved −500 px, no slew reported).
- Before: subs 44-46 skipped; 47 and 48 measured and flagged (2 anchors; their positions are right, 0.20 / 0.14 px).
- After: 44-46 skipped; 47 and 48 verified (shift 4.86 / 4.14 px < 10 px).
- With the anchor-frame rule off (`NO_ANCHOR_FRAME`, a fallback path):
  - before: sub 44 measured 494 px off and flagged; 45 and 46 skipped;
  - after: subs 44 **and 46** measured 494 px off, both flagged (no unflagged wrong point).
- In no replay is a target point more than 2 px from its star and unflagged.

#### 4.3 Every frame that changes state, and why

| Run, frame | Change | Why | Verdict |
|---|---|---|---|
| `050148Z` / X29, frames 0-21 | anchors 2 → 1-3; S58 verify solves 13 → 9; frame 16 re-solved for rotation | true SNR (0.74×): fewer anchors at SNR ≥ 10, so the S35 fallback anchors at SNR ≥ 5 (the target included); target 0.05-0.84 px from its star (truth: consensus ASTAP) | good |
| X29 frame 14 (`_00015`) | target and check flagged (S71) | the zero point is dominated by 000-BJV-170 (SNR 16), 2.5σ from the others; the check reads 10.856 against 10.61-10.71 on its neighbours, the target 11.80 against 11.45 (the frame's zero point is about +0.25 mag off) | **correct**: it was unflagged before |
| `050148Z` frame 14 | comparison row flagged 170 → 171 | S71 leave-one-out with the new weights | neutral |
| `052943Z` frame 3, `053540Z` frame 1 | 000-BJV-172 off-centre (S69 b) | 1.1 / 1.6 px from its aperture (the geometry role's Gaussian fit: 1.18 / 1.60) | correct |
| `045626Z` frame 2 (`_00003`) | lock lost / unanchored; 8 comparison rows flagged; faint warning on | a cloud sub: every star 2-4× fainter, target SNR 2.9 → 1.1, a no-detection before and after; comparisons' median SNR 6.5 | correct: no point measured on it |
| `040723Z` frame 23 | one more S58 verify solve | 3 anchors at true SNR | neutral |
| `034413Z_V` frame 0 | 2 flagged comparison rows → none written | every set star at SNR < 1 in both trees (a 5.9 s LP frame) | neutral |
| Live `050148Z` (one solve per run), frame 19 | **newly flagged** | 3 anchors; the target-as-anchor was clipped 3.0 px off its consensus, leaving 2 used; the solution was not fresh → S56 | **a good point flagged** (target 0.10 px from its star; F6). Frames 13-16, good, are no longer flagged |
| Live `053540Z`, frames 1-3 | flags → verified | 1-2 anchors, fresh solution, shift < 10 px | correct (target 0.09-0.64 px) |

Blank-sky frames: RR Lyr 52 and 175 stay skipped live. In the re-run they are re-solved and measured right (within 0.006 of Siril). No blank-sky frame is newly kept.

### 5. AAVSO exports and Review of the three sessions

Source: `http_checks.py` → `evidence/http_*.json`; `aavso_check.py` → `evidence/aavso_check.json`.

**Review of the sessions as recorded.**
- RR Lyr: readiness "warnings" (`site_mismatch`; `flagged_points` 2: `_00053`, `_00176`); airmass source header. S78 gives 1090 comparison points their own airmass at the fitted site, within 0.0001 of astropy.
- XX Cyg 09-07: "warnings" (`flagged_points` 1: `_00021`).
- XX Cyg 08-29: "warnings" (`unverified_lock` 22; `faint_comparisons`, median SNR 1.7).

**AAVSO files**, two per session (Review source and the re-run job's output):

| Field | RR Lyr session / re-run | XX Cyg 09-07 session / re-run | XX Cyg 08-29 session / re-run |
|---|---|---|---|
| Header | `#TYPE=EXTENDED`, `#OBSCODE=TST`, `#SOFTWARE=Argos v0.4.2`, `#DELIM=,`, `#DATE=JD`, `#OBSTYPE=CCD`; 15 columns | same | same |
| Rows / CSV rows | 193/195 · 195/195 | 23/24 · 23/24 | 22/22 · 22/22 |
| Left out = flags = my own no-detection rule | `_00053`, `_00176` · none | `_00021` · `_00021` | none · none |
| MAG = CSV | yes | yes | yes |
| MERR | MERR² − formal² = my second-difference sigma_syst (0.01497) · = CSV `mag_err` (sigma_syst 0) | 0.23657 = mine 0.23655 · 0.0469 = mine 0.0468 | 0.1145 = mine · 0 |
| DATE − mid-exposure | ≤ 0.044 s | ≤ 0.044 s | ≤ 0.040 s |
| AMASS − astropy (fitted) / − header | ≤ 0.0007 / ≤ 0.0005 | ≤ 0.0007 / ≤ 0.0004 | ≤ 0.0005 / ≤ 0.0005 |
| FILT / TRANS / MTYPE / CNAME / CMAG / KNAME / KMAG / GROUP / CHART / NOTES | TG / NO / STD / ENSEMBLE / na / na / na / na / na / na | same | same |

Notes on the AAVSO files:
- The preview flags the RR Lyr airmass as `mismatch` (that night's wrong site, X3).
- A re-run's output opens in Review as an import (A70). Its old-file rules are null, so it carries no faint-comparisons warning (F8).

### 6. Findings

**F1 (medium, S78; Qt core and server port alike).** Without a fitted site, a comparison or check star's airmass falls back to the Settings site, even when S66's own check finds that site wrong.
- Affected code: `review.apply_old_file_rules`, `photometry_batch_worker._prepare_star_site` and the server ports.
- Short runs (< 10 min or < 3 pointings) cannot be fitted.
- RR Lyr 2026-09-25 `195307Z` (5 lights, 6 min, `site_mismatch`/`frames_site_wrong` 5 of 5): the comparisons' airmass is 4.0-4.9 where the true value is 1.025-1.034. That is 3.85 off in the re-run and 3.32-3.76 off in Review. Before S78 they had the header AIRMASS, within 0.0017.
- On XX Cyg 08-29 `052943Z` / `053540Z` the Settings site is 2.1° off, under the check's 5°. Comparisons go from 0.0012 to 0.0129 / 0.0126 from astropy: worse than the header value they replace. 09-07 `045156Z` / `045626Z`: 0.0069 → 0.0078 / 0.0084.
- AAVSO AMASS (target) is unaffected. Comparison and check CSVs, Review plots and extinction analyses are.
- Evidence: `evidence/level_a_after.json` (`times_airmass`), `evidence/review_s78_195307Z.json`, `runs` (deleted; reproduce with `rerun_all.sh`).
- Suggested fix (the fixer's, an S78 amendment):
  - without a fitted site, keep the header AIRMASS for every star (pre-S78);
  - or at least never use a Settings site that `site_mismatch` / `frames_site_wrong` rejects.
- Test: a short synthetic run with a wrong Settings site; comparisons must stay within 0.002 of astropy. It fails now.

**F2 (low, S72/S73).** The gain-65 frame (`034413Z`, 5.92 s, sky 56 ADU above black) fails S72's 10 % test: model / measured σ = 0.79.
- At a scaled gain the green model takes `photometry.read_noise_e` (1.5 e-), not the 2.6 e- measured at gain 80. With 2.6 e- the ratio would be 0.89.
- The frame fits either (g 0.271, rn about 3.2 e-) or (g about 0.22, rn 2.6 e-). No measurement verifies gains below 80; the noise role found this frame inconclusive.
- OWNER DECISION. Options:
  - (a) scale only over 80-251 (gain 100 is verified) and log gains below 80 unverified;
  - (b) keep 0-251 but use the measured 2.6 e- as the read noise at scaled gains;
  - (c) keep as is.
- Recommended: (a) + (b).
- Evidence: `evidence/sky_sigma.json`.

**F3 (information for the owner, S74).** With C_Y = 1.5 the bright-star errors are over-estimated.
- RR Lyr pairs at SNR ≥ 100: 0.80 (robust 0.73); RR2: 0.89 (0.77).
- The RR Lyr target's second-difference σ / formal: 0.62-0.75.
- Check 000-BCG-523: χ²r 0.59.
- This agrees with the noise role's implied C_Y of 1.1-1.4.
- Recommended: as the noise role says, keep 1.5 until more nights, then refit (about 1.2).

**F4 (S8x new: the noise role's edge apertures, confirmed; the fixer numbers it from S81).** An aperture partly off the frame is measured with a truncated box, and its comparison row is written unflagged.
- RR Lyr `200453Z` 6-comp re-run, after:
  - 000-BJW-667 frame 130 (edge 1.5 px, +0.10 mag), frame 131 (y = −2.4, +4.98 mag, SNR 3.0);
  - 000-BJW-668 frame 181 (0.6 px, +0.33 mag, SNR 61), frame 182 (+5.24 mag).
- The S71 clip kept them out of the target's ensemble (comps_used 4 and 3), but the comparison curves carry them.
- Evidence: `evidence/edge_scan_after.json`, `edge_scan_before.json` (the same in both trees).

**F5 (S8x new, S62; Qt worker and server port alike).** `_object_key("V* XX Cyg")` is "vxxcyg", not "xxcyg".
- The owner's `20260829T034413Z_V_XX_Cyg` light (OBJECT "V* XX Cyg", SIMBAD form) is left out of a re-run with the "XX Cyg" set: 0 frames; Qt says "No frames".
- Fix: strip SIMBAD identifier prefixes (`V*`, `*`, `NAME`), or match the set's names.
- Test: `discover_light_frames(folder, "XX Cyg")` keeps a frame with OBJECT "V* XX Cyg". It fails now.
- I re-ran that light with the set's object set to "V* XX Cyg" to count its gates.

**F6 (low, live S56, one solve per run).** `050148Z` sub `_00020` (frame 19) is a good point (0.10 px from its star) newly flagged.
- One of its 3 anchors, the target taken by the S35 fallback at SNR ≥ 5, was clipped 3.0 px off its consensus. The fit ran on 2 anchors with no fresh solution.
- On that schedule the flags go 5 → 2, so it is a net improvement.
- It belongs with the geometry role's anchor-threshold OWNER DECISION; no separate action recommended.

**F7 (notes accuracy).**
- S79 says "none on … XX Cyg 2026-08-29". `053540Z`'s set has 000-BJV-173 and 000-BJV-180 crowded; core and my own list agree.
- S77 says "5 of 5 XX Cyg stars matched". The 08-29 set has 6 VSX/VSP stars, and 000-BJV-180 (V 14.15) takes no Gaia motion, in the saved answer and in today's live archive answer alike.

**F8 (minor, pre-existing, both apps).** A re-run output opened in Review is an import, without old-file rules.
- The 050148Z re-run (comparisons' median SNR 1.4) shows no `faint_comparisons` warning, and its AAVSO export writes 22 rows without it.
- The AAVSO preview calls the S67 no-detection point `_00021` "suspect (cosmic ray / hot pixel, or no verified lock)".
- OWNER DECISION, low priority. Recommended: read a `photometry_rerun_*` folder's own recorder when its CSV is imported.

**F9 (explained regression on the "keep or improve" list).** RR Lyr 6 comparisons − Siril: offset −0.0076 → −0.0116 (σ 0.0153 → 0.0145).
- S71's weights now follow the corrected errors, so this ensemble (not Siril's) moves by 4 mmag.
- RR2 against Siril's own comparisons is unchanged (+0.0013).

### 7. Not checked

- New frames' `EGAIN`/`RDNOISE` headers (S73) on a real capture: no camera. The simulator is S50-like. Only the suites cover it.
- The S78 live path with mount polls, and the Qt UI (S79 comparison tab, crowding WARN), except through their suites. The web Field band was not checked visually (vitest only).
- That each new regression test fails without its hunk was not redone. I relied on the roles' evidence (`noise/evidence/revert_checks.json`, `geometry/evidence/fail_before_*.txt`).
- `194741Z`: its reference frame did not solve in either tree. `194822Z` and `034413Z_V` show no set star (SNR < 1). Their only level (a) is the sky σ.
- A frozen sidecar build (`tests/packaging` only); the AAVSO WebObs validator (not fetched); VSP was not re-queried (yesterday's answers).
- S76's sky estimator: not re-evaluated; the median stays, as decided.

### 8. Scripts and evidence

Every script is in `scripts/` and every output in `evidence/`, both in this folder.
- `mk_trees.sh`, `setup.py`, `suites.sh`;
- `qt_rerun.py` + `rerun_all.sh` (20 re-runs × 2 trees);
- `parity.py` + `parity_all.sh`; `server.sh`, `api.py`, `http_checks.py`, `http_all.sh`;
- `gates_replay.py`, `s54_repoint.py`, `replay_all.sh`, `replay_diff.py`;
- `level_a.py`, `gates_diff.py`, `gate_tables.py`;
- `ptc_check.py`, `sky_sigma.py`, `offsets.py` + `myphot.py`, `crowding_check.py`, `edge_scan.py`, `field_track_lag.py`, `review_s78_short.py`, `aavso_check.py`.

The clones, re-run folders, trees, server environment and private site configs were deleted after the numbers were out.

## C. The science review (as written, before the owner's calls)

Adversarial science review of the S72-S80 pass, run on 2026-11-16. I did not edit any repo file.

- **Code reviewed.** The release worktree at 3e48d78 plus its uncommitted S72-S80 changes, read in place (no bytecode written), and the server tree as it stands.
- **How the numbers were made.** Every number below comes from a script in `scripts/` and an evidence file in `evidence/`, both in this folder.
- **Re-runs.** The fixed-Qt batch worker of the release worktree (`scripts/qt_rerun.py`, reused from the validation role), driven by `scripts/rerun.sh` under the heavy lock, on APFS clones (`scripts/setup_sr.py`). The variants:
  - RR2: 200453Z with comparisons 000-BJW-665/666 and check 000-BCG-523.
  - RR6: 200453Z with its 6-comparison set.
  - X07: 040723Z with check 000-BJV-169.
  - X29: 050148Z with check 000-BJV-171.
  - S307: 195307Z, 5 lights over 6 minutes.
- **Site.** Configs are private and set the Settings site to the site fitted to the header ALTITUDE/AZIMUTH. That site stayed in scratch and is deleted. S307 was also run with the header's (wrong) site.
- **My own code** (not the core) made every level (a) measurement:
  - photon transfer;
  - green-plane sky σ;
  - blank apertures;
  - aperture photometry with both sky estimators;
  - centroids;
  - astropy positions and airmass;
  - pair statistics.

### Findings

| ID | Severity | Finding | Kind |
|---|---|---|---|
| F1 | High | The annulus median's 8-ADU quantisation: a sawtooth sky error, missing from the formal errors and invisible to σ_syst. It is the largest identified part of the RR Lyr − Siril residual. | OWNER DECISION (S76): adopt the clipped mean |
| F2 | Medium | For bright stars, the formal errors and the AAVSO MERR are 1.3-1.6× the measured scatter: C_Y 1.5, zp_err's rms branch, the 0.01 floor. | OWNER DECISION (S74 / S71) |
| F3 | Medium | S78's Settings-site fallback: comparison airmass 3.4-3.85 off on 195307Z. | Confirms validation F1 |
| F4 | Medium | An aperture partly off the frame is written unflagged. | Confirms S8x |
| F5 | Low | Gain 65 fails S72's 10 % test; the 0.1 dB per step scaling is verified only between 80 and 100. | Confirms validation F2 |
| F6 | Low | S74's airmass and height inputs come straight from the header, even when S66/X1 or X3 reject it. | |

**Confirmed, no action needed:**
- S73: my own photon transfer gives 0.2253 e-/ADU and 2.54 e- read noise.
- S72: the sky σ test passes at 0.956-0.996.
- S77: proper motion is right to 0.011 mas, and the aperture is 0.04 px from the centroid.
- S78 with a fitted site: within 0.00007 of astropy.
- Faint-star errors are honest: pair ratio 1.07 (0.97).
- Check stars agree with VSP.
- The gates I spot-checked keep their physical meaning.

### 1. S73: the e-/ADU from my own photon transfer

**Method** (`ptc.py` and `ptc_fit.py`; evidence `ptc_pairs.json`, `ptc_fit_review.json`, `ptc_gain100_temp.txt`):
- Data: 115 consecutive light pairs at gain 80 from 7 sessions over the three nights, and 4 pairs at gain 100.
- Per pair: raw G1 and G2 sub-planes, stars masked in either frame, 32×32 tiles.
- Variance of the difference: 5σ-iterative clip, so the clipping bias is below 1e-5. The 3σ clip some estimators use biases g up by 2.7 %.
- Fit: var = (L − B)/g + (R/g)² with B = 1024.

**Gain 80:**
- **One line** over the 115 pairs:
  - g = 0.2253 e-/ADU.
  - Bootstrap 16-84 %: 0.2239-0.2278 over pairs, 0.2214-0.2291 over sessions.
  - R = 2.54 e-, ADC quantisation included.
  - Residual rms 1.1 %.
  - Jackknife by session: 0.2224-0.2276.
- **The profile's 0.228 ± 0.005 and 2.6 e- are confirmed** (my value is −1.2 %, within 1σ). The profile model predicts each session's measured pair variance to within −1 % to +3 % (0.991-1.031).
- **Night-to-night spread.** With a common intercept the three nights give 0.2281 ± 0.0009, 0.2214 ± 0.0008 and 0.2229 ± 0.0020 (formal errors). That 3 % spread is larger than the formal errors. It is the same size as the drift inside one session: in 040723Z the per-pair ratio estimate goes 0.219 → 0.225 as the sky rises 1361 → 1406 ADU and the sensor cools 25.4 → 24.2 °C. A 3-5 ADU black-level difference between nights is enough to explain it, since the sky is only 140-380 ADU above black. **It is a black-level or temperature systematic, not a gain change.** The quoted ±0.005 (2.2 %) is an honest 1σ for it.
- **Noise correlation** between neighbouring pixels in the pair differences:
  - same colour: 0.4-1.2 %;
  - G1 with G2 of one cell: 1.1 %;
  - G1 with R of one cell: 1.3 %.
  
  Aperture sums are therefore within about 2 % of n·σ², and the per-pixel model holds.

**Gain 100:**
- The free fit gives 0.188, but it is driven by the cloud pair of 045626Z.
- The ratio method (B = 1024, R = 2.5 e-) on the clean 045156Z pairs gives 0.178-0.183. Against g80 this is 0.100-0.107 dB per step, so **0.1 dB per step is supported between 80 and 100**.
- Below 80 nothing measures it: the single gain-65 light gives no pair.

### 2. S72: the noise model against the measured green-plane sky σ

Script `skysig.py`; evidence `skysig.json`, `skysig_pooled.txt`. My own (G1+G2)/2 plane; first, middle and last light of 12 runs.

- Model σ (the core's `sky_sigma_adu` with the core's `hardware.egain.of_frame` chain) over measured σ (median over star-free tiles of the 5σ-clipped std):

  | Runs | Model / measured |
  |---|---|
  | RR Lyr 200453Z | 0.974-0.981 |
  | 040723Z | 0.967-0.980 |
  | 050148Z | 0.986-0.995 |
  | All gain-80 and gain-100 frames | 0.956-0.996 |
  | Same frames with their header EGAIN | about 0.34 |

- **The S72 test (within 10 %) passes.** The 1-4 % shortfall is the spatial σ's fixed pattern and faint stars, which the model does not count.
- **Gain 65 fails** (034413Z_V, 5.9 s, sky 55 ADU above black): ratio 0.761. This confirms validation F2. It goes to 0.96 with the gain-80 values unscaled (0.2253, 2.54 e-), so it is the scaled gain together with the 1.5 e- configured read noise.

### 3. S74: scintillation against the bright pairs' excess

**Checks of the formula and its inputs** (`analysis.py`; evidence `honest_*.json`, `honest_summary.txt`):
- **Formula.** Young/Osborn, σ² = 1e-5 C_Y² D^-4/3 t^-1 X³ exp(−2h/8000): checked against the paper's form.
- **Inputs.** It is fed per frame from EXPTIME, AIRMASS and SITEELEV, as `_read_scintillation` does in the batch worker.
- **Numerical check.** The RR Lyr frame-0 record (SNR 153.9, X 1.033, 10 s) reproduces inst_mag_err 0.0190.
- **Independence between stars.** The term is per star and independent between stars, which is physically right: at 30 mm the scintillation decorrelation angle is about 1-2″, and the set stars are arcminutes apart. The ensemble zero-point error therefore carries the comparisons' scintillation divided by √n, with no double counting.

**C_Y from the data.** With the photon term held fixed, solve for the C_Y that makes the pair ratio 1:

| Pairs | C_Y, plain std | C_Y, robust |
|---|---|---|
| RR2, 3 pairs | 1.27 | 1.23 |
| RR6, the 6 bright pairs (SNR ≥ 100) | 1.08 | 1.00 |

- Over all 15 RR6 pairs the robust fit spreads 0.88-1.57. That spread is above the about 8 % statistical error per pair, so some star-specific noise is present, and the lowest values bound the true scintillation from above.
- **Conclusion: C_Y ≈ 1.0-1.25 at 30 mm.** This is physically expected: a 30 mm aperture is below the Fresnel scale (about 7 cm for turbulence at 10 km), where Young's D^-2/3 over-predicts.
- **Site height.** For the 2026-09-25 night the header SITEELEV belongs to the wrong Settings site (X3). A 0.5 km error moves σ_scint by about 6 %: minor.
- **Airmass input.** The scintillation reads the header AIRMASS even for a frame whose pointing S66/X1 rejects as frozen. That is low impact: none of the study runs is affected measurably.

### 4. S75 and S76: the sky-estimate term, and the median against the clipped mean

#### Blank apertures (spatial)

Evidence `skysig_pooled.txt`. Scatter / model, pooled over first, middle and last lights, n = 63-1021 apertures per run:

| Sky estimate and model | Scatter / model |
|---|---|
| Median, no S75 term | 1.47-1.93 |
| Median with S75 (the code) | 1.14-1.54 (RR Lyr 1.54 and 1.45; XX Cyg 08-29 1.17-1.22) |
| Median with S75 plus the median's quantisation n_ap²·8²/12 | 1.01-1.26 |
| 3σ-clipped mean with its own n_ap(1 + n_ap/n_sky) | 1.00-1.31 (RR Lyr 1.09-1.24) |

Bias per blank aperture (sky too low):

| Run | Median | Clipped mean |
|---|---|---|
| RR Lyr | +45 ± 35 ADU | +21 ± 23 ADU |
| 195307Z | +84 ± 28 ADU | +35 ± 22 ADU |

Neither estimator is unbiased. The clipped mean is less biased wherever the bias is significant.

#### The mechanism

Script `siril_sky.py`; evidence `median_quantisation.txt`.
- The annulus median is always on the 4/8-ADU grid of the green plane.
- On RR Lyr, median − clipped mean has an rms of 2.27-2.34 ADU per pixel, against 0.96 ADU for continuous data. The excess is 2.1 ADU, about Δ/√12.
- It follows the sky level's phase on the grid as a sawtooth (bin means −0.8, −2.0, +1.0, +1.0 ADU).
- **Effect on each bright RR Lyr star:** 0.004-0.005 mag rms, range ±0.009-0.012 mag. It scales as 1/flux: about 0.05 mag for a 5000 ADU XX Cyg comparison.
- **It is not in the formal errors.** S75 counts only the median's statistical 1.6 ADU.
- **It is slow**, because it follows the sky level, so σ_syst's second differences do not see it.

#### Against independent references

**RR Lyr minus Siril green 2 comps**, with my own photometry at the code's aperture centres (`siril_sky.json`):

| Sky estimate | Robust σ |
|---|---|
| Annulus median | 0.0108 |
| 3σ-clipped mean | 0.0073 |

- Ratio 0.69, bootstrap 68 % interval 0.63-0.76.
- The code's own CSV gives 0.0099.
- **The median's quantisation is the largest identified part of the ARGOS − Siril residual (about 0.008 mag).**

**Pair scatter** (first differences), clipped mean over median (`sky_estimators.py`; `skyest_*.json`):

| Run | Median ratio | Pairs better (68 %) | Pairs worse (68 %) |
|---|---|---|---|
| X07 | 0.81 | 18 of 28 | 1 marginal: 501/578, 1.11 [1.00-1.22] |
| RR6 | 0.97 | 11 of 15 | none |
| X29 | — | — | 2, both with 000-BJV-176 at SNR 1-2 (non-detections, not meaningful) |

**Conclusion (OWNER DECISION, F1):** the clipped mean is better or equal on every pair whose two stars are detected (one marginal exception), it halves the bias, and it agrees better with the independent reduction.

### 5. Are the formal errors honest now?

Scripts `analysis.py` and `decompose.py`; evidence `honest_*.json`, `decompose_*.json`, `zp_calibration.txt`.

**The pair test.** For each pair of non-target stars, z = first difference of (instA − instB) divided by the quadrature sum of the four inst_mag_err. The ratio is std(z): plain, then robust in brackets.
- **Faint stars, XX Cyg 040723Z** (28 pairs, SNR 5.6-24): 1.07 (0.97). **Honest.** The pairs with the crowded 000-BJV-173 are high (1.18-1.25), as S79 expects.
- **Bright stars, RR Lyr:**
  - RR2: 0.86 (0.85).
  - RR6 bright pairs: 0.77 (0.73).
  - **Errors 15-30 % too large: C_Y.**
- **050148Z:** only the pair 000-BJV-171/170 is meaningful, at 0.86 (0.84). The other comparisons sit at SNR 0.4-2, where the linear magnitude error is meaningless.

**The target and the check.** σ_real is the robust σ of the second differences, divided by √6.

| Star | real / formal | real / random (C_Y 1.5) | real / random (fitted C_Y) |
|---|---|---|---|
| RR2 target | 0.75 | 0.81 | 0.94 (C_Y 1.25) |
| RR6 target | 0.62 | 0.65 | 0.84 (C_Y 1.08); about 1.04 with C_Y 1.0 |
| X07 target (SNR 4-7) | 1.25 (σ_syst picks it up) | | |
| X29 target (n = 20) | 0.63 | | |
| X29 check | 0.73 | | |
| X07 check | 0.91 | | |

Here random = inst ⊕ sqrt(1/Σ 1/err²), with no 0.01 floor and no rms branch.

**Check-star χ²_r about its own mean:**

| Check | χ²_r with the code's formal error | random only | random with C_Y 1.25 |
|---|---|---|---|
| 000-BCG-523 | 0.59 | 0.84 | 1.15 |
| 000-BJV-169 | 0.62 | 0.69 | |
| 000-BJV-171 | 0.70 (0.43 with mag_err) | 0.83 | |

**Why the formal error is too large.** It is:

> formal = inst ⊕ zp_err, with zp_err = max(sqrt(1/Σ w), rms/√n) and w = 1/(err² + 0.01²)

- **The rms branch** is taken on 57 % (RR2) to 100 % (RR6) of frames. It carries the comparisons' constant catalogue disagreement: ±0.013 per comparison in RR2, against a per-frame rms/√n of 0.0120.
- **The 0.01 floor** inflates the photon branch by about 9 %: 0.0174 against 0.0159 on RR2.
- **C_Y = 1.5** is the largest single cause.
- Together they put the per-point error 1.3-1.6× above the measured scatter of bright stars.

**RR Lyr minus Siril.**
- RR2: +0.0013, robust σ 0.0099; RR6: −0.0116, 0.0145. These are the same as the validation role's values.
- The χ² of that difference is not a test of the errors: both reductions measure the same photons and the same scintillation. Naively, with both errors, χ²_r is 0.20 (RR2) and 0.47 (RR6).

**Check stars minus VSP V:**

| Check | Mean ± sem | VSP error | Result |
|---|---|---|---|
| 000-BCG-523 | +0.0160 ± 0.0017 | ±0.100 | within error (0.16 combined σ) |
| 000-BJV-169 | −0.0647 ± 0.0091 | ±0.051 | 1.25 combined σ: outside VSP's error, not significant |
| 000-BJV-171 | +0.0447 ± 0.0223 | ±0.030 | 1.20 combined σ: outside VSP's error, not significant |

### 6. The AAVSO MERR

- MERR equals the CSV mag_err (checked field by field by the validation role).
- **Bright targets.** With σ_syst = 0, MERR over-estimates the target's point-to-point scatter:
  - RR2: 0.0296 against 0.0221 (1.34×);
  - RR6: 0.0252 against 0.0156 (1.62×);
  - 050148Z: 0.186 against 0.120 (1.55×; validation's AAVSO evidence).
- **Faint target.** On the faint XX Cyg target (040723Z), σ_syst makes MERR honest by construction.
- **Verdict.** For bright stars MERR now errs on the safe side, by 1.3-1.6×. It is not honest at the "ratio near 1" level the owner set.
- **What it takes** (F2):
  1. C_Y of about 1.2;
  2. zp_err without the floor and the per-frame rms branch;
  3. the comparisons' catalogue disagreement estimated once per run as a calibration term;
  4. σ_syst computed against the random part.

### 7. S77: proper motion on RR Lyr

Script `pm_check.py`; evidence `pm_check.json`.

- **Source.** Gaia DR3 2125982599343482624: pmra −109.599, pmdec −195.851 mas/yr, at 2016.0.
- **Epoch.** Moved back to J2000 with astropy, it lies 0.037″ from the VSX position, so the epoch and the catalogue are consistent.
- **Sign and units.** The core's `TargetStar.at_jd` minus astropy `apply_space_motion` is at most 0.011 mas over the run. The sign, the units and the cos δ handling are right.
- **Motion.** Since VSX J2000 the star has moved 5.98″, which is 0.80 green px.
- **Aperture placement.** My own centre of light against the aperture centre, on every 10th frame:
  - target: median 0.042 px, 90th percentile 0.083;
  - comparisons and check: 0.07-0.12 px.
  
  The S77 target of 0.3 px is met.

### 8. S78: per-star airmass

Script `airmass_check.py`; evidence `airmass_*.json`, `airmass_summary.txt`.

- **Fitted site.** Comparisons and checks match astropy (Pickering of the geometric altitude) within 0.00007 on RR6, X07, X29 and S307. Targets keep the header AIRMASS, within 0.00043.
- **S307 with the header (wrong) Settings site.** Five lights over 6 minutes, so no site fit is possible. The comparisons get airmass 4.17-4.88 where the truth is 1.024-1.031: errors of 3.42-3.85. The run itself records frames_site_wrong. **Validation F1 is confirmed** (F3 here).
- **What it reaches.** This airmass does not feed the scintillation (the batch worker passes no star_airmass) or the AAVSO AMASS (the target's). It reaches the comparison and check CSVs.

### 9. Gates: is their physical meaning kept?

These are spot checks on my runs. The validation role's 20 re-runs and 16 live replays carry the counts.

- **RR Lyr frames 52 and 175** (the re-pointing jumps that were blank-sky in the live CSVs): in the re-run they are field_lost, then re-solved and re-anchored with 3 anchors. Their points agree with their neighbours (7.4814 between 7.4995 and 7.4601; 7.7036 between 7.6962 and 7.7211). No blank-sky point is kept.
- **X07 frame 20 (S67, no detection):** the sky jumps by +72 ADU, the flux falls to 448 ADU against 1440-2536 on the neighbours, and the target's SNR is 1.19. The flag is genuine.
- **X29 frames 5 and 14 (S71):** the check reads +0.22 and +0.21 mag off its run median. The flags are genuine.
- **The SNR is now the true one.** On faint stars the pair ratio is 1.07 (0.97), so "SNR ≥ 3, 5, 10" means 3, 5 and 10σ on every session. For the anchor-SNR owner decision (keep 10 or 7):
  - at SNR 7 the peak pixel is about 4.2σ, so a noise peak in a 15 px search circle has about a 1 % chance of beating it, and S80 rejects an inconsistent anchor;
  - at SNR 10 that chance is negligible.
  
  A replay of 7 on every study run is the right next step, as the geometry role recommends.

### 10. Edge apertures (S8x, confirmed)

Evidence `edge_rows_RR6.txt`.

- **Off-frame apertures.** These rows are written with suspect = 0:

  | Star | Frame | Aperture position | Magnitude error |
  |---|---|---|---|
  | 000-BJW-667 | 130 | y = 1.5 | +0.082 |
  | 000-BJW-667 | 131 | y = −2.4 | +4.95 |
  | 000-BJW-668 | 181 | y = 0.6 | +0.28 |
  | 000-BJW-668 | 182 | y = −2.7 | +5.20 |

- **Truncated annulus only** (edge 4-11 px): +0.014 to +0.061 mag.
- **Fix:** return None, or flag the row, unless the aperture and the annulus lie wholly on the frame.

### Not checked by me

- The live path (no camera, no replay), and the S56 500 px jump replay. I relied on the geometry and validation roles for both.
- EGAIN and RDNOISE in new frames' headers.
- Server-vs-Qt byte parity (validation: 7 of 7 identical).
- The AAVSO files field by field (validation).
- Frozen-pointing frames.
- Any gain other than 80 and 100.

**Scratch footprint:** 556 KB of scripts and evidence.
- Deleted: the clones, re-run folders, private configs (fitted site), Gaia copies and temporary HOME and TMPDIR.
- No process of mine is running, and the heavy lock is released.
- Neither tree was touched: the release worktree status is unchanged, with no bytecode written.
- 16.8 GB free.

## D. S76 adopted, S73's order, S84 (the owner's calls of 2026-11-16)

The owner's calls on the S73-S80 science and technical reviews were implemented in the
release worktree, then on this branch, by an implementation role; checked by a
**validation** (level (a), level (b), the gates on every study run, the live S84 path) and
an adversarial **review** (science and code, its own photometry); then completed by a
**fixer** pass (their findings). Scripts and evidence lived in `scratchpad/s76/<role>/`
(the fixer copied the figures it cites into `evidence/cited/`). No site coordinates or
observer data appear here.

### D.1 The calls, applied

| Item | Call | Done |
|---|---|---|
| S76 | The sky is the annulus' 3σ-clipped mean; S75's term at factor 1 | `aperture.sky_level` (median centre, standard deviation, bounds inclusive, repeated until nothing is rejected, at most 10 passes): astropy's `sigma_clipped_stats(sigma=3, maxiters=10)`, photutils' `ApertureStats` default; every aperture of the core and the server, both noise models |
| S73 | The observer's photon-transfer file before the profile's measurement | Second in the chain, live, in `EGAIN`, at a re-run and in Open FITS; source "<sensor> PTC file", recorded as every step's |
| S84 | `photometry.noise_model`, `photometry.read_noise_e` in the S15 run lock | Qt, the server (`409 run_active`), the web Settings page |
| Not decided | The formal error split (random, per-run calibration) and a C_Y refit | Deferred to 0.5.x |

The code's sky is astropy's: within 0.01 ADU on 502 of 504 re-run records (validation
`sky_vs_astropy.json`; the two others hold a pixel 1e-5 px from the annulus edge) and
0.0 ADU on 1244 RR Lyr annuli (review). The clip converges in at most 5 passes on 1646
star annuli and 4 on 5838 blank ones, never 10, and keeps at least 95 % of the pixels
(median 99.2 %; review `passes.json`).

### D.2 Level (a), final

Before = release `4e6493d` with this branch's `37a67ac` server (validation
`level_a_before.json`); after = this pass. The fixer's re-run of RR2, RR6 (RR Lyr's own 6
comparisons), X07 and X29 on the final tree equals the validation's after-state key by key
(every count, gate tally, Siril, VSP, pair, time and airmass figure: fixer
`level_a_fixer.json`, `same_as_validation.json`, `level_a_compare.json`).

| Check | Before | After |
|---|---|---|
| RR Lyr − Siril green 2 comps (n = 195): offset / robust σ | +0.0013 / 0.0101 | +0.0021 / 0.0083 |
| RR Lyr 6 comps − Siril: offset / robust σ | −0.0110 / 0.0147 | −0.0098 / 0.0130 |
| 000-BCG-523 − VSP V (VSP ± 0.100), scatter | +0.0167 ± 0.0016, 0.0225 | +0.0166 ± 0.0015, 0.0213 |
| 000-BJV-169 − VSP V (± 0.051) | −0.0647 ± 0.0091 | −0.0645 ± 0.0085 |
| 000-BJV-171 − VSP V (± 0.030) | +0.0447 ± 0.0223 | +0.0436 ± 0.0204 |
| Pair scatter / formal error, median (robust): RR6 (21 pairs) | 0.95 (0.80) | 0.94 (0.77) |
| same, RR2 (6) | 0.89 (0.77) | 0.86 (0.75) |
| same, X07 (36) | 1.11 (1.01) | 1.12 (0.95) |
| same, X29 (3) | 0.71 (0.60) | 0.92 (0.94) |
| Target `sigma_syst`: RR2; X07 | 0; 0.170 | 0; 0 |
| Comparisons' median SNR: RR2; RR6; X07; X29 | 119.1; 111.7; 13.9; 1.4 | 121.7; 114.3; 15.2; 1.5 |
| Blank apertures, bias (ADU): RR Lyr (1560); `040723Z` (960); `050148Z` (880) | +28 ± 8; +44 ± 14; +52 ± 15 | +10 ± 6; +32 ± 12; +25 ± 12 |
| same, scatter / the code's error (validation, S75's selection) | 1.42; 1.31; 1.25 | 1.17; 1.19; 1.14 |
| same, the review's strict mask: RR Lyr (2335); `050148Z`; `040723Z`; `052943Z` | 1.40; 1.20; 1.20; 1.20 | 1.10; 1.07; 1.07; 1.06 |
| Model / measured green-plane sky σ, 31 frames at gains 80 and 100; the gain-65 frame | 0.959-1.049; 0.889 | 0.960-1.039; 0.883 |
| RR Lyr aperture − Gaussian centroid, median (90th pct) | 0.077 (0.157) px | 0.077 (0.157) px, the same centres |
| `jd_utc`, `bjd_tdb` − astropy | 0.0000 s | 0.0000 s |
| Per-star airmass − astropy at the fitted site, max: targets; comparisons and checks | 0.00044; 0.00007 | 0.00044; 0.00007 |

What the blank apertures' remaining excess is (review `*_blank.json`, `rr_sky_factor.json`):
not the estimator, whose factor measured on real annuli (two halves of each, 9340 pairs)
is 1.09 for the clipped mean (2.95 for the median), 1.00-1.09 on a sky quantised as the
plane whatever its phase (the median 0.38-9.5), within 1.2 % of the total error; it is
neighbouring pixels' correlation (0.02-0.04; a k × k box sum's variance 1.02-1.08 times
that of independent pixels) and faint stars in the apertures (the positive bias: the clip
and the median leave out their brightest pixels, which an aperture sums). The release notes
S75 quoted 1.06, 1.06, 1.05 "with a clipped mean": those were against the median's model
(π/2, every pixel); S75 now gives both sets above.

### D.3 The numbers that moved away from 1, and why

- RR2's offset against Siril moves +0.8 mmag (68 %: +0.1 to +1.2), within the offset's own
  error (0.0007-0.0009); the target's magnitudes move −0.4 mmag median, 5.0 mmag rms; the
  robust σ ratio is 0.83 (68 %: 0.74-0.91). The review's own photometry gives 0.70
  (0.64-0.77) and an offset change of +0.5 mmag.
- The bright pairs drift below 1 (RR2 0.89 → 0.86, RR6 0.95 → 0.94): their scatter falls,
  their formal errors (S74's conservative C_Y = 1.5) stay (−0.4 %).
- X29 (`050148Z`, 3 pairs): 0.71 → 0.92. The median sat at 1400 ADU on 17 of 22 frames:
  hardly any noise, a bias no error counted; the clipped mean follows the far sky (residual
  2.11 ADU for 1.85 expected, the median 2.47; review `x29_far.txt`) and adds a noise the
  error counts. Its target's second-difference σ rises 0.122 → 0.163 on n = 22 at SNR 5-17
  (about ±25 %); frame by frame it lies nearer the reference (0.122 against 0.132 mag rms;
  review `x29_target.json`).
- X07's target (SNR about 5): second-difference σ 0.283 → 0.124 mag, `sigma_syst` 0.170 →
  0 (validation `second_diff.json`): the clearest gain.

### D.4 Gates

Every frame that changes state between before and after is explained (validation §4.3,
`gates_diff.json`, `replay_diff.json`): the SNR rises ×1.02 for bright stars and ×1.06-1.08
where the sky dominates (review `snr_*.json`), so faint comparisons of 2026-08-29 cross the
anchors' SNR 5 and 10 (more anchors, fewer verification solves); `050148Z` frame 5 keeps 2
comparisons after the clip, so no S71 flag; `052943Z` frame 3's target is flagged by the
hot-pixel guard (9.9 % against the 10 % threshold); RR Lyr's check on the blank frame
`_00053` falls below SNR 3 (3.33 → 2.71) and the blank frames' target stays below 3 (2.27 →
0.39, 2.84 → 1.56). No unflagged target point lies more than 2 px from its star in the
code. On the live path (one solve every 20 s) the cloudy `045626Z` sub, a lock lost before,
is now measured on its one anchor with the target at SNR 0.8 (12.77 ± 1.28), unflagged in
the live CSV; Review, the AAVSO export and a re-run leave it out (S67). Without S56's
anchor-frame rule (a counterfactual) sub 44 of the 500 px jump would be an unflagged point
494 px off: that rule is its only protection. The fixer's changes touch no gate (the four
re-runs identical key by key).

### D.5 Level (b)

The validation's `parity.py` (the server's `rerun.BatchRun` against the fixed Qt worker,
in one process): X07, X29, RR2, RR6, `195307Z` and X29 with a temporary photon-transfer
file (0.25 e-/ADU, "IMX585 PTC file") **identical** (every CSV, `targets.json`, recorder
record, count and solver call). The fixer's later core changes (a new frame's `RDNOISE`
source, the read noise of a frame whose `EGAIN` the file wrote, a log line) do not touch
those cases' data; parity was not run again.

### D.6 S84 live and the web Settings pages

Validation (simulator, `s84_live.json`): during a run, `PATCH` of `photometry.noise_model`
and `photometry.read_noise_e` → `409 run_active` with the server's sentence; a mixed PATCH
gets both sentences and writes nothing; after the stop, 200; the web Photometry page shows
the six keys unavailable with the sentence in Observatory, Charcoal and Night Red (Night
Red audit PASS). It also found `camera.egain_table` accepted mid-run, the next frames
carrying `EGAIN` 0.3 instead of 0.25 (F1); the review measured +15 % on one star's SNR
from a file written mid-run. The fixer added the e-/ADU's two keys to the lock (D.7) and
checked them live the same way (fixer `s84_live.json`, `web_lock/`; simulator, a gain table
`{"80": 0.3}` and a temporary photon-transfer file `{"80": {"egain": 0.25, "rdnoise": 3.0}}`):
during a run each of the four keys gets `409 run_active` with "The noise model and the
camera's e-/ADU are locked while a sequence runs (one curve, one error model).", a mixed
PATCH both sentences and nothing written, an unlocked key 200; after the stop all four are
accepted; all 10 frames of the run carry `EGAIN` 0.3 "(egain_table)" and `RDNOISE` 3.0
"(IMX585 PTC file)" (D.7's provenance). The web Photometry and Instrument pages show the
locked keys unavailable with the sentence (every control disabled, the unlocked rows
editable) in Observatory, Charcoal and Night Red, and editable after the stop; Night Red
3 of 3 pass (rule A 0 px, rule B 0 px). Screenshots: `web/screenshots/2026-11-16_settings-run-lock/`.

### D.7 The fixer's changes (findings of the validation and the review)

| Finding | Severity | Change | Test that fails before it |
|---|---|---|---|
| F1 / review: the e-/ADU not in the lock | medium | `camera.egain_table`, `data_paths.camera_calibration_directory` join S84 (core `params.NOISE_MODEL_KEYS`, Qt's folder field disabled in a run, server, web Instrument page and `EgainTable`'s `locked`); the sentence "The noise model and the camera's e-/ADU are locked while a sequence runs (one curve, one error model)." | `test_shell_three_mode_walkthrough`, `test_the_noise_model_is_locked_during_a_run_s84`, `test_the_settings_page_locks_what_the_server_locks_during_a_run_s15_s84`, `runlock.test.ts` |
| F2 / review: `RDNOISE` named "IMX585 reference" for the file's value | low | `egain.calibration_read_noise`; the writer names "IMX585 PTC file" | `test_rdnoise_names_the_observers_photon_transfer_file_s73` |
| Review: a frame whose `EGAIN` the file wrote loses its read noise in a re-run without the file | low | `of_frame` keeps the `RDNOISE` the file wrote | `test_the_observers_photon_transfer_file_comes_before_the_profile_s73` |
| Review: a file entry without `rdnoise` takes 1.5 e- silently | low | Kept (the rule for every e-/ADU without a measured read noise; the profile's 2.6 e- is not mixed with another e-/ADU), logged once | same test (the log) |
| Review: the locked keys in three copies | low | GUARD test: the server's keys are the core's | `test_the_server_locks_the_cores_noise_model_keys_s84` (overlay) |
| F3 / review: S75's 1.06 figures | low | S75 and S76 give both sets of figures (D.2) | — |
| Review: docsrc's faint-star sign | low | "bias the sky slightly low" | — |

Every new test fails with its hunk reverted in a scratch copy (fixer `revert_checks.json`,
10 of 10; `vitest_revert.json` for `runlock.test.ts`).

### D.8 Open after this pass

- OWNER DECISION (review medium; validation F4): the live path does not apply S67's
  per-target rule, so the cloudy `045626Z` sub's target at SNR 0.8 is an unflagged live
  point. Options: (a) flag a target point below SNR 3 `suspect` and `no_detection` when
  measured (Qt engine and server live port; the live CSV then equals a re-run's), (b) S48
  asks for 2 anchors at SNR ≥ 5, (c) leave it (Review, the export and a re-run exclude it).
  Recommended (a): no new threshold.
- OWNER DECISION (review medium): an edit of the photon-transfer file itself during a run
  is read from the next frame (no key changes). Options: resolve the e-/ADU (value, source,
  read noise) once per gain at the run's start and keep it (Qt `AcquisitionEngine._egain`,
  the server's `TargetService.egain`), or leave it. Recommended: resolve once per run.
- OWNER DECISION (minor, review): `site.elevation` feeds S74's scintillation every frame
  and is not locked.
- Not decided now: the formal error split (bright stars' `MERR` 1.3-1.6 times their
  scatter; RR2 target and check second-difference σ / formal 0.64, 0.63) and a C_Y refit,
  deferred to 0.5.x with more nights.
- Not checked: a real camera's `EGAIN`/`RDNOISE`; Qt's S84 path live (its suite only); the
  HTTP parity (A76); VSP not queried again.
