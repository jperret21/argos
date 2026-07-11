# Photometry hardening plan

Findings from the 2026-07-11 expert review: a full scripted session against
the OmniSim (connect → goto → filter → autofocus sweep → sequence → FITS)
plus a code read of the measurement chain. Each item states the defect, the
fix, and how to prove it. Ordered by science impact — work top to bottom.

**Division of roles (project decision, 2026-07-11).** Darks and flats WILL be
taken, and the publishable analysis happens in **post-production** (Siril +
external photometry tools) — not in Argos. Argos therefore owns two things:

1. **The contract with postprod** — FITS that are calibratable and trustworthy:
   truthful headers (filter, gain, timing, pointing, site, airmass), correct
   session tree, dark/flat frame types captured and labelled correctly. Any
   header lie silently corrupts the postprod result → highest priority.
2. **In-field quick-look** — the live/batch curves exist to answer *tonight*:
   "is the target in frame, are the comps clean, is the run worth continuing?"
   They must be honest (check star, clipping, airmass) but they are not the
   publishable product; sub-mmag refinements belong to postprod.

Status legend: `[ ]` open · `[~]` partial · `[x]` done.

---

## P1 — FITS headers must record reality, not the request  `[ ]`

**Defect.** The sequence worker writes the *planned* values into the FITS
headers even when applying them failed. Demonstrated against the simulator:
wheel physically on **IR**, log says `No wheel position matches filter 'LRGB'
— skipping`, header says `FILTER='LRGB'`. Same for `GAIN=80` after
`Camera does not implement Gain — skipping`. A frame measured in one band and
labelled another poisons every downstream product (photometry band, AAVSO
submission, Siril session sort).

**Fix.** After applying each setting in `SequenceWorker._shoot_one`, read the
achieved state back from the device (`filterwheel.position_name()`, camera
gain) and put *that* in the `FrameContext`. When apply was skipped/failed and
the read-back differs from the plan, log WARN and write the read-back.

**Prove it.** Simulator test: plan filter `LRGB` against the sim wheel (which
has no such slot) → header `FILTER` equals the wheel's actual position name,
and a WARN is logged. Same pattern for gain.

**Files.** `argos/workers/sequence_worker.py`, `argos/core/imaging/fits_writer.py`
(context fields), `tests/core/test_simulator_sequence.py`.

---

## P2 — Check-star curve (the standard quality control)  `[ ]`

**Defect.** `ROLE_CHECK` exists in the catalog model, but `measure_targets`
returns results only for `role == "target"` — the check star is never
calibrated, plotted, or exported. Without a K-star curve there is no evidence
a target's variation is real rather than an ensemble/sky artefact.

**Fix.** Calibrate check stars exactly like targets (against the comparison
ensemble, never including the check itself), flag the result as `role=check`,
and carry it through: live points, batch curves, CSV (own file), light-curve
panel (muted trace, per the sober-UI preference), and the K-star RMS in the
batch summary log.

**Prove it.** Unit: a synthetic constant check star yields a flat calibrated
curve with RMS ≈ photon noise. Batch test: `curves` contains the check key;
CSV written.

**Files.** `argos/core/photometry/session.py`, `photometry_batch_worker.py`,
`acquisition_engine.py`, `ui/widgets/lightcurve_panel.py`.

---

## P3 — Ensemble zero-point: reject outlier comparisons  `[ ]`

**Defect.** `ensemble_zero_point` is a plain mean of `cat − inst`. One bad
comparison (blend, cloud edge, bad catalog mag, near-saturation) biases every
point of the night; the RMS is computed but never acted on.

**Fix.** Sigma-clipped zero-point (e.g. 2.5 σ, ≤ 2 iterations, only when
n ≥ 3 so a pair is never silently halved). Report which comps were rejected
(`DiffResult.note`), count them in `comps_used`. Keep the mean path for n < 3.

**Prove it.** Unit: 4 comps, one offset by 0.5 mag → zp within mmag of the
clean-3 answer, note names the rejection. Existing tests unchanged (they use
clean comps).

**Files.** `argos/core/photometry/differential.py`, tests.

---

## P4 — Airmass: one formula, filled everywhere  `[ ]`

**Defect.** Two implementations coexist: Pickering 2002
(`sky_geometry.compute_airmass` — the deliberate, low-altitude-accurate one;
feeds the FITS `AIRMASS` header) and Kasten–Young 1989
(`photometry/airmass.airmass_from_altitude` — feeds the *live* curve points).
The same frame can carry two slightly different airmasses, and **batch points
carry none** (`airmass=None` in `_emit_points`) even though site, DATE-OBS
and star coordinates are all available (we already compute BJD from them).
Airmass is required for AAVSO extended format and for spotting extinction
trends.

**Fix.** Standardise on Pickering: make `airmass_from_altitude` delegate to
(or be replaced by) `sky_geometry.compute_airmass`, keep the public name the
photometry layer imports. In the batch worker compute per-frame altitude from
site + DATE-OBS + target coords (astropy AltAz, same machinery as
`compute_target_geometry`) and fill `LcPoint.airmass`.

**Prove it.** Unit: both entry points agree to 1e-4 across 5–90° altitude.
Batch test with a site: every emitted point has `airmass` set and plausible
(≥ 1, monotone with altitude).

**Files.** `argos/core/photometry/airmass.py`, `photometry_batch_worker.py`,
tests.

---

## P5 — JD at exposure midpoint, not start  `[ ]`

**Defect.** Batch does `julian_date(DATE-OBS)` — start of exposure. A 30 s
sub gets a 15 s systematic timing bias on every point (visible on fast
eclipsing binaries; ruinous for exoplanet timing).

**Fix.** `jd_mid = julian_date(DATE-OBS) + EXPTIME / 2 / 86400` in
`_read_frame` (header `EXPTIME` is already written by our FITS writer; fall
back to start + WARN when absent). Audit the live path for the same bias.

**Prove it.** Unit: frame with `EXPTIME=30` → JD is 15 s after DATE-OBS.

**Files.** `argos/workers/photometry_batch_worker.py`,
`argos/core/session/acquisition_engine.py`, tests.

---

## P6 — Autofocus must detect a degenerate V-curve  `[ ]`

**Defect.** On a perfectly flat HFD curve (5 × 3.40 against the simulator —
optically decoupled focuser; on sky: clouds, wrong step size, saturated star)
the worker still announces a confident `best_found` from a parabola fitted to
noise, and the app moves the focuser there.

**Fix.** Before accepting the fit: require a minimum relative HFD span
(e.g. max−min > 15 % of min) and the minimum not at a sweep edge. Otherwise
emit `error_occurred("no V-curve — focus unchanged")` and return to the
start position (the return-to-start machinery already exists in `stop()`).

**Prove it.** Unit with a fake camera/focuser: flat curve → error + position
restored; clean V → best at vertex. Simulator run doubles as the flat case.

**Files.** `argos/workers/autofocus_worker.py`, `tests/workers/`.

---

## P7 — One fixed aperture per series, measured from the frames  `[ ]`

**Defect.** Live adapts the aperture radius to each frame's FWHM (injects
correlated variance into the series); batch floors it to `aperture_min_px`
because saved subs "carry no FWHM" — yet the tracker already centroids the
anchor stars every frame, so a per-frame FWHM is nearly free. Time-series
practice is one radius for the whole series, sized from the median seeing.

**Fix.** Batch: measure FWHM on the anchor stars over the first N frames
(reuse `metrics` moments), set `r_ap = aperture_fwhm_mult × median FWHM` once,
log it. Live: hold the radius for the session once enough FWHM samples exist
(update only on a re-solve/refocus), instead of per frame.

**Prove it.** Batch test: synthetic 3 px-FWHM stars → chosen aperture ≈ 7.5 px
(not the 4 px floor); mags across frames tighter than the floored run.

**Files.** `photometry_batch_worker.py`, `photometry/params.py`,
`acquisition_engine.py`, tests.

---

## P8 — Anchor-fit outlier rejection (tracking robustness)  `[ ]`

**Defect.** `fit_rigid` accepts every matched anchor; with the typical 2–3
comps, one wrong lock (hot pixel, neighbour star) skews the transform for the
frame with no warning.

**Fix.** With n ≥ 3 anchors: fit, compute residuals, drop any anchor beyond
max(2 px, 3×median residual), refit once. Expose `ApertureTracker.residual_px`
and WARN when it stays high (aperture placement suspect).

**Prove it.** Unit: 3 good anchors + 1 displaced by 5 px → recovered rotation
within tolerance of the clean fit.

**Files.** `argos/core/photometry/tracking.py`, tests.

---

## P9 — Hot-pixel flag in the quick-look aperture  `[ ]`  *(downgraded)*

**Defect.** The in-app quick-look measures raw subs, so a hot pixel inside
the aperture adds flux → spurious dips/rises as field rotation carries it in
and out of the aperture.

**Scope note.** Downgraded to nice-to-have: darks/flats are taken and the
publishable analysis runs on calibrated frames in postprod, so this only
affects the in-field curve. Worth a cheap flag, not a calibration pipeline.

**Fix (scoped).** In `measure_aperture`, flag apertures whose peak pixel has
no PSF support (reuse the `_has_psf_support` idea from `metrics`) as
`suspect=True`; grey the point in the panel.

**Prove it.** Unit: single bright pixel in the aperture of a faint star →
`suspect`; clean Gaussian star → not suspect.

**Files.** `argos/core/photometry/aperture.py`, `lightcurve.py`, tests.

---

## P10 — Calibration frames as first-class sequence citizens  `[ ]`

**Defect (contract).** Since calibration happens in postprod, Argos's job is
to *capture and label* the calibration frames right. The sequencer already
has Dark/Bias frame types; verify the full contract postprod needs: correct
`IMAGETYP` (`Dark Frame`, `Flat Frame`, `Bias Frame`), matching `EXPTIME`/
`GAIN`/`CCD-TEMP` recorded truthfully (P1), flats with the *actual* filter
(P1 again), and a session tree Siril picks up without manual sorting
(`darks/`, `flats/`, `biases/` alongside `lights/`).

**Fix.** Audit `SequenceStep`/`fits_writer`/session tree against Siril's
expectations; add a `Flat` frame type if missing; simulator test capturing
one of each type and asserting headers + folder layout.

**Prove it.** OmniSim run: a mixed plan (lights + darks + flats) lands each
type in the right folder with truthful headers; Siril loads the tree as-is.

**Files.** `argos/core/imaging/sequencer.py`, `fits_writer.py`,
`session_log.py`, `tests/core/test_simulator_sequence.py`.

---

## P11 — Diagnostics flight recorder (per-frame, machine-readable)  `[ ]`

**Goal (infrastructure — schedule early: it validates every other item).**
Postprod must be able to audit what Argos measured and decided on every
frame: did the apertures stay locked, did a comparison drift or cloud out,
did the zero-point wander, was a header value read back or assumed. Today
that story is scattered across human-oriented log lines and lost at the end
of the night.

**Fix.** A `SessionDiagnostics` writer (core, Qt-free) producing one
**JSON-Lines** file per run — `diagnostics.jsonl` next to `session.json`
(and in the batch `out_dir` for re-runs). One record per frame per subsystem,
`{"t": iso8601, "frame": n, "kind": ..., ...}`; kinds and their variables of
interest:

- `star` — one per measured star per frame (target, **every comparison**,
  check): auid/name, role, predicted vs measured (x, y), `refine_centroid`
  offset, r_ap/r_in/r_out, flux_adu, sky_adu, peak_adu, snr, inst_mag,
  inst_mag_err, saturated. This is what lets postprod watch each comp's
  *individual* behaviour over the night instead of only the calibrated
  target curve.
- `ensemble` — per frame: zp, zp_rms, comps_used, comps_rejected (auids +
  residuals once P3 lands), min_comps satisfied.
- `tracking` — per frame: anchors matched/total, cumulative rotation_deg,
  shift_px, fit residual (P8), frames_lost streak.
- `frame` — DATE-OBS, EXPTIME, jd_mid, airmass, altitude/azimuth, FWHM, HFD,
  star_count, sky_adu, filter *as read back* (P1), gain as read back,
  ccd_temp.
- `event` — sparse: connect/disconnect, goto (target vs arrived), solve
  (ra/dec/rotation/scale), refocus (positions + HFDs + accepted/refused),
  filter change, sequence start/stop, monitor state changes.

Analysis-friendly by construction: `pandas.read_json(..., lines=True)` then
`df[df.kind == "star"].pivot(index="frame", columns="auid", values="inst_mag")`
plots every comp's raw behaviour in three lines of notebook code.

Wiring: `AcquisitionEngine` (live) and `PhotometryBatchWorker` (re-runs) emit
records; `measure_targets` returns the per-star detail it already computes
(today it drops everything but the calibrated targets). Config key
`diagnostics.enabled` (default **true** — a few kB/frame; a night is worth
having the black box on).

**Prove it.** Batch test: rotating synthetic scene → jsonl exists, one `star`
record per star per frame, `tracking.rotation_deg` matches BatchResult,
records parse with `json.loads` line by line. Simulator session: `event`
records for goto/sequence, `frame` records carry read-back filter.

**Files.** New `argos/core/session/diagnostics.py`;
`argos/core/photometry/session.py` (return per-star detail),
`photometry_batch_worker.py`, `acquisition_engine.py`, tests.

---

## Explicitly out of scope (tracked elsewhere)

- Colour transformation coefficients (Tg…) — `ui_redesign_todo.md` §Science.
- Applying darks/flats inside Argos — calibration and the publishable
  analysis are postprod (Siril + external tools) by project decision; Argos
  captures and labels the frames (P10) and keeps the quick-look honest.
- Live-path field-rotation warning / session cap — `ui_redesign_todo.md`.

## Suggested order

P11 first or alongside P1 (the recorder is how the other fixes get audited),
then P1 + P10 (the postprod contract), then P2–P5 (honest quick-look), then
P6–P9.

## Validation once P1–P11 land

Re-run the scripted OmniSim session (headers now truthful, autofocus refuses
the flat curve) and the full suite; then one real-sky session: 30 min on a
known-constant field in alt-az — acceptance is a flat check-star curve with
RMS at the photon limit and airmass filled on every CSV row.
