# Photometry & astrometry workflow — technical plan

> Status: **design / hand-off doc** (2026-06-16). Author intent captured from the
> session brief. This is written to be handed to an implementing agent: it states
> the target UX, the coordinate conventions, the exact files/functions/signals to
> touch, the data shapes, and a phased sequencing. The non-negotiable science
> principle remains `docs/capture_panel.md` §0 (**display pipeline ≠ data
> pipeline**: saved FITS stays raw, linear, 16-bit, CFA `GRBG`).

---

## 0. One-paragraph summary

We have a working acquisition app with a live preview, ASTAP plate-solving, an
RA/Dec grid overlay, star click-to-measure, and a VSX/VSP variable-star catalog
overlay. Today the **catalog + comparison-star workflow only lives in the
floating "Open FITS" analysis window**, the **live page solves only on a manual
button press and never auto-tracks the WCS**, and the **solve/catalog/overlay
logic is duplicated** between the two windows with subtle divergences. This plan
(a) **homogenises** image + astrometry handling behind one shared, tested
pipeline so solving is stable and the two surfaces behave identically, and (b)
adds the **photometry workflow**: a persistent target/comparison set, live
differential-photometry light-curve preview with error bars, and a session
"metrics" panel (temperature / airmass / sky / FWHM vs time).

---

## 1. Coordinate conventions — the single source of truth

Everything downstream depends on getting this right. There are **three** coordinate
spaces; name them precisely and never mix them:

| Space | Definition | Used by |
|---|---|---|
| **raw px** | full-res sensor pixel `(H, W)`, GRBG CFA, what FITS stores | FITS writer, saturation mask |
| **green px** | half-res green plane `(H//2, W//2)`, one sample per 2×2 Bayer tile | star detect/measure, WCS, all overlays, catalog projection |
| **display px** | the rendered view shape (depends on the selected View: super-pixel/channel = `H//2×W//2`; Raw/Interpolated = `H×W`) | mouse clicks, marker drawing |

Rules (already mostly followed — **make them explicit and enforced**):

1. **All science + astrometry lives in green px.** `detect_stars`, `measure_star_at`,
   `FrameWCS`, `wcs_grid`, catalog projection all speak green px.
2. **Display ↔ green is a pure scale** `sx = dw/gw`, `sy = dh/gh`. The viewer scales
   green-px overlays to the active view; clicks scale back. No rotation, no offset.
3. **Markers are children of the PyQtGraph `ViewBox` in data (display-px) space**,
   so **zoom/pan transform image + overlays together** — overlays never drift on
   zoom. (This is why the "zoom breaks astrometry" symptom is *not* an overlay-math
   bug; see §4.)
4. **The "green plane" must have ONE definition.** Today there is a latent
   inconsistency: `metrics._green_plane` uses `raw[0::2, 0::2]` (**G1 only**) while
   `debayer.extract_plane(VIEW_G)` returns **(G1+G2)/2**. Both share the *same pixel
   grid* (top-left of each tile) so coordinates are consistent, but the values
   differ. Unify on a single `green_plane(raw)` helper (recommend **(G1+G2)/2** for
   SNR; keep the G1 grid origin) and have detection, measurement, and solving all
   call it. Document the ≈0.5-green-px (≈1 raw px ≈ 3.7″) green-pair offset as
   accepted.

---

## 2. Current-state audit (what exists, where, and what's wrong)

### 2.1 What already works
- `core/imaging/debayer.py` — CFA split, 3 render modes, channel extract (Qt-free, tested).
- `core/imaging/metrics.py` — robust star detect, `measure_star_at`, FWHM/HFD/ecc/SNR (green px).
- `core/imaging/platesolve.py` — ASTAP glue, `.ini`/`.wcs` parse, `FrameWCS` (astropy TAN), `wcs_grid`, formatting/sep helpers.
- `workers/solve_worker.py` — runs one solve off-thread.
- `workers/catalog_worker.py` + `core/catalog/aavso.py` + `core/catalog/photometry.py` — VSX/VSP fetch + comparison ranking (Qt-free, tested).
- `ui/widgets/fits_viewer.py` — viewer with stretch, measurement, and overlay layers: stars, **WCS grid + target reticle**, **VSX diamonds**, **VSP squares + labels**, selection ring + readout label.
- `ui/analysis_window.py` — the **full** catalog workflow (solve → grid → variables → pick variable → ranked comparison table → markers → settings popup).
- `ui/pages/imaging_page.py` — live preview, manual live solve, grid overlay, click-to-measure.

### 2.2 Divergences / bugs to kill (the "pas clair + bugs")

| # | Problem | Where | Impact |
|---|---|---|---|
| D1 | **Two solve paths.** Live passes mount RA/Dec + FOV hint and retries blind; analysis passes **no position hint** (always whole-sky blind) | `imaging_page._on_solve_live` vs `analysis_window._on_solve` | Different success rates & speed for the *same* frame → "sometimes works" |
| D2 | **Catalog/variables/comparisons exist only in the analysis window** | `analysis_window` only | Live page can't show/select variables — the core ask |
| D3 | **Grid spacing config applied in analysis, ignored live** | `analysis._update_astrometry_overlay` passes `spacing_deg`; `imaging_page._update_astrometry_overlay` doesn't | Inconsistent grid density |
| D4 | **Saturation threshold hardcoded 60000 in analysis**, from config live | `analysis._wire` lambda | Wrong clipping mask on non-default hardware |
| D5 | **`scale/2` full-res convention duplicated** inline in both `_on_*solved` | both | Easy to drift; should be one helper |
| D6 | **Stale WCS persists across frames.** After a solve the grid is redrawn every new frame from the *old* solution; if the mount drifts/you re-frame, grid no longer matches stars | `fits_viewer.display()` → `_refresh_astrometry` | Looks like "astrometry broke when I moved" |
| D7 | **Live solve is manual + one-shot** | `imaging_page` | User wants auto-solve each frame |
| D8 | **Catalog config keys absent from `_DEFAULTS`** (`astrometry.*`, `catalog.*` only read with inline defaults) | `core/config.py` | Settings scattered; no single schema |
| D9 | **Green-plane definition split** G1-only vs (G1+G2)/2 | §1 rule 4 | Latent, low impact, but unify |

### 2.3 Why astrometry is actually flaky (root causes, not zoom)
- **Short live subs are star-poor.** A ~1 s live sub at 3.74″/px has few/faint stars;
  ASTAP intermittently fails. The analysis window solves a *saved* (longer) sub →
  succeeds. Same field, different SNR → the inconsistency the user feels.
- **Blind whole-sky fallback is slow** (`-r 180`, 120 s timeout). Fine for a one-off,
  unacceptable as a per-frame cadence.
- **No "keep last good WCS" policy** — a single failed solve blanks the grid.

---

## 3. Target architecture

```
core/   (Qt-free, unit-tested)
  imaging/
    green.py            NEW  single green_plane()/green_shape() (§1.4)  ── or fold into debayer
    platesolve.py       (keep) ASTAP + FrameWCS + wcs_grid
    astrometry_session.py NEW  pure helpers: build_solve_settings(), full_res_scale(),
                               wcs_from_result(), field_geometry(), project_points()
  catalog/
    aavso.py            (keep) VSX/VSP clients
    photometry.py       (keep) comparison ranking
    targets.py          NEW  TargetSet / TargetStar model + JSON load/save
  photometry/           NEW package
    aperture.py         NEW  aperture_sum(), sky_annulus(), instrumental_mag(), snr/err
    differential.py     NEW  ensemble zero-point, differential mag + uncertainty
    lightcurve.py       NEW  LightCurve accumulator (per-target time series) + CSV
    airmass.py          NEW  airmass from alt (or RA/Dec+site+time)

workers/  (QThread bridge)
  solve_worker.py       (keep) one solve
  catalog_worker.py     (keep) VSX/VSP fetch
  astrometry_controller.py NEW QObject: owns solve lifecycle + auto-solve policy,
                               emits solved(wcs, overlay, summary) / failed(msg)
  photometry_worker.py  NEW  per-frame: project targets → aperture-measure → emit
                               PhotometryFrame (one point per target, with errors)

ui/
  widgets/
    fits_viewer.py      (keep + extend) one richer star-info popup
    star_info_panel.py  NEW  click-a-star → details + "set role" (target/comp/check)
    astrometry_settings.py (keep)
    comparison_table.py (keep)
    target_table.py     NEW  the saved target/comparison set (roles, mags, RA/Dec)
    lightcurve_panel.py NEW  live differential light curve (pyqtgraph + error bars)
    metrics_panel.py    NEW  temp / airmass / sky / FWHM / HFD vs time
  panels/
    photometry_window.py NEW  dock or floating window hosting LightCurve + Metrics tabs
  pages/
    imaging_page.py     (refactor) use AstrometryController; add catalog + target overlays
  analysis_window.py    (refactor) becomes the "Field setup / target picker";
                               share all astrometry/catalog code with the live page
```

**Layer rules unchanged** (`docs/ARCHITECTURE.md`): `core/` no PyQt; `workers/` bridge;
`ui/` no network/subprocess. New subprocess stays in `core/imaging/platesolve.py`.

---

## 4. Workstream A — homogenise the image + astrometry pipeline (do FIRST)

Goal: one code path, stable solving, identical behaviour on both surfaces. This is
the "clean the code" deliverable and it unblocks everything else.

### A1. Single green-plane definition (§1.4, kills D9)
- Add `core/imaging/green.py` (or a `green_plane`/`green_shape` in `debayer.py`):
  ```python
  def green_plane(raw) -> np.ndarray:   # (H//2, W//2) float32, (G1+G2)/2
  def green_shape(raw) -> tuple[int,int]
  ```
- Repoint `metrics._green_plane`, `compute_hfd`, `preview_processor.build_processed_frame`
  (`green_shape`), and `platesolve.solve_array`'s input extraction to it. One definition.

### A2. Shared astrometry helpers (kills D1, D3, D5)
Add `core/imaging/astrometry_session.py` (Qt-free):
```python
def build_solve_settings(cfg_get, green_shape, mount=None, *, live: bool) -> SolveSettings
    # ONE place that reads astrometry.* config, sets fov_hint from green_shape,
    # sets ra/dec hint from mount when present, and picks the search radius:
    #   live + mount → astrometry.live_search_radius_deg (default 5)
    #   else         → astrometry.search_radius_deg (default 30) ; blind retry handled in solve_array
def full_res_scale(result) -> float | None        # result.scale_arcsec / 2 (the ÷2 convention, once)
def wcs_from_result(result, green_shape) -> FrameWCS | None    # = frame_wcs(...)
def field_geometry(wcs, green_shape) -> (ra_deg, dec_deg, radius_deg, fov_arcmin)  # move from analysis_window
def project_points(wcs, green_shape, radec_iter, margin=2.0) -> list[(x,y)|None]   # in/out-of-frame, reused by variables+comparisons+targets
def overlay_for(wcs, green_shape, cfg_get, target_radec=None) -> WCSOverlay         # applies grid_spacing_arcmin once
```
Both `imaging_page` and `analysis_window` call these; delete their inline copies.

### A3. AstrometryController (kills D6, D7) — `workers/astrometry_controller.py`
A `QObject` (lives on the UI thread, owns a `SolveWorker`) that centralises the
solve lifecycle + **auto-solve policy**:
- API: `solve_once(green, green_shape, mount, *, live)`, `set_auto(bool)`,
  `on_new_frame(green, green_shape, mount)`, `invalidate()` (call on goto/slew).
- Signals: `solved(FrameWCS, WCSOverlay, str summary)`, `failed(str)`, `state(str)`.
- **Policy** (configurable):
  - At most one solve in flight; drop/ignore new requests while busy (latest-wins).
  - **Keep last good WCS on failure** — never blank the grid on a single miss;
    surface a small "WCS aging" indicator instead.
  - Auto mode: re-solve when `invalidate()` was called (slew) **or** every
    `astrometry.live_resolve_s` (default 20 s) **or** mount moved > `astrometry.live_resolve_arcmin`
    (default 2′). Between solves the grid is valid while tracking, so don't thrash.
  - Live solves use a **bounded timeout** (`astrometry.live_timeout_s`, default 25 s)
    and the small search radius from A2; the slow `-r 180` blind retry is **disabled
    in live mode** (only used by an explicit manual "Solve (blind)" action).
- `imaging_page` wires `_on_processed` → `controller.on_new_frame(...)` and
  `controller.solved` → set WCS + overlay + refresh selection + (re)project catalog/targets.

### A4. Stability + security hardening of `solve_array`
- Keep **list-form `subprocess.run`** (no `shell=True`), `check=False`, `capture_output`,
  `timeout` — already correct; just make timeout come from settings and **shorter for
  live**. Validate `astap_path` exists (already via `find_astap`).
- Guard `frame_wcs` against a green shape that doesn't match the solved frame (store
  the green shape used at solve time alongside the WCS; if a later frame differs,
  re-solve rather than reproject onto a wrong CRPIX).
- Add 2–3 unit tests on recorded ASTAP `.wcs` text for `build_solve_settings`,
  `full_res_scale`, and `overlay_for` spacing.

**Acceptance for Workstream A:** the live page and the analysis window produce the
*identical* WCS, grid, and catalog for the same saved FITS; a failed live solve
keeps the previous grid; auto-solve tracks a sequence without freezing the UI;
`uv run --extra dev pytest` green.

---

## 5. Workstream B — live page becomes the photometry cockpit

The main page is where the night is spent. Add to `imaging_page.py`:

> **Confirmed UX (2026-06-16):** click-a-star info lives in an **on-image info card**
> (anchored bottom-left, semi-transparent, with role buttons); overlay toggles live in
> a **slim chip bar directly under the image toolbar**. (Resolves §11 Q2.)

### B1. Catalog + target overlays on the live frame (kills D2)
- After each (auto) solve, fetch VSX/VSP via `CatalogWorker` (same as analysis), then
  `project_points` variables + comparisons + **saved targets** to green px and push to
  the viewer layers (`set_catalog_markers`, `set_comparison_markers`, plus a NEW
  **target layer**, see B4).
- **Overlay toggle bar** — a slim second row under `ImageToolbar`: chips
  **Grid · Stars · Variables · Comparisons · Targets** (a small reusable
  `ui/widgets/overlay_bar.py`, checkable chips, each `…_toggled(bool)`). Chips are
  **disabled until their data exists** (Variables/Comparisons/Targets after
  solve+catalog). This removes the live-page reliance on the far-away Display-tab
  checkboxes for overlays; keep Display-tab toggles for the focus tools (loupe/ROI).
- **Marker visual language** (one colour = one meaning, theme palette, no emoji):
  field stars = thin green rings (∝FWHM, existing); VSX variables = purple diamonds
  (existing); VSP comparisons = cyan squares + label (existing); **tonight's target(s)
  = a NEW bold amber double-ring + name label** so it is unmistakable among the rest
  (new `fits_viewer` target layer: `set_target_markers`/`set_target_enabled`).

### B2. Click-a-star info card (the confirmed on-image card)
New `ui/widgets/star_info_card.py` — a compact, **corner-anchored overlay card** on the
image (bottom-left, semi-transparent, a small `[x]` to dismiss), upgrading today's
`fits_viewer.mark_selection` readout label into an interactive card. It never follows
the cursor (stable under zoom/pan) and barely occludes the field. On `star_clicked`:
- Resolve in priority order (reuse the analysis hit-test): **saved target → VSX variable
  → VSP comparison → measured field star**; ring the star (`mark_selection`).
- Show: catalog id (AUID/name), RA/Dec (if solved), catalog mags per band, var
  type/period (variables), then measured FWHM/HFD (″ via plate scale), ecc, SNR, peak
  ADU, sky. (All already computed by `measure_star_at` / the catalog dataclasses.)
- Actions (the role buttons): **Target · Comparison · Check · Clear** (variables also
  get **Show comparisons**). A role button writes/updates a `TargetStar` in the
  `TargetSet` (B4) and saves. Empty/field-star cards offer **Add as Comparison / Check**.
- This unifies today's `fits_viewer.mark_selection` readout label with the catalog
  click — one info surface, richer.

### B3. RA/Dec grid with edge labels
Today the grid is drawn but the centre RA/Dec is only a text badge. Add **axis-edge
labels**: where each iso-RA / iso-Dec line meets the frame border, draw a small
`pg.TextItem` with the RA (h m) or Dec (° ′) value. Implement in `fits_viewer`
(`_refresh_astrometry`): for each polyline in `WCSOverlay.lines`, compute its
border-crossing in display px and label it. Extend `WCSOverlay` to carry each line's
sky value + axis so the viewer can label without re-deriving. Keep it toggle-bound to
the existing Grid toggle. (This satisfies "coordinates on the x/y borders".)

### B4. Persistent target/comparison set — `core/catalog/targets.py`
```python
@dataclass
class TargetStar:
    role: str            # "target" | "comparison" | "check"
    auid: str | None
    name: str | None
    ra_deg: float
    dec_deg: float
    bands: list[Band]    # known catalog mags (may be empty for a hand-picked field star)
    source: str          # "vsx" | "vsp" | "manual"
    note: str = ""
@dataclass
class TargetSet:
    object_name: str
    stars: list[TargetStar]
    def save(path) / load(path)   # targets.json in the session folder, atomic write (mirror session_log)
```
- The set is **session-scoped**: written to the session folder next to the FITS and
  `session.json`. Loaded when a session resumes.
- During a sequence, after each solve the worker knows which saved targets are
  in-frame → drives B5 photometry and the target overlay.
- UI: `ui/widgets/target_table.py` — a table (role, name/AUID, RA/Dec, mags, in-frame?)
  with remove/role-change, **Copy TSV** (reuse the `comparison_table` pattern), shown
  in a rail tab or the photometry window. This is the "tableau des étoiles
  sélectionnées" the user asked for.

**Acceptance for B:** on the live page, after auto-solve, the user sees variables +
comparisons, clicks any star to get full info, assigns roles, and the set persists to
`targets.json` and reloads.

---

## 6. Workstream C — live differential photometry (light-curve preview)

A **preview** — explicitly *not* the calibrated science product. The README/panel
must state: *"Preview: raw subs, no dark/flat/bias; final light curve is produced in
post-processing."*

### C1. Aperture photometry core — `core/photometry/aperture.py` (Qt-free)
```python
@dataclass
class AperturePhot:
    flux_adu: float        # background-subtracted aperture sum
    flux_e: float          # flux_adu * egain (e-/ADU) when known
    sky_adu: float         # per-pixel sky (annulus median)
    n_pix: int
    peak_adu: int
    snr: float
    saturated: bool        # any pixel >= linearity_max_adu in aperture
    inst_mag: float        # -2.5*log10(flux_adu)  (instrumental)
    inst_mag_err: float    # 1.0857 * flux_err/flux  (CCD equation)

def measure_aperture(green, x, y, r_ap, r_in, r_out, *, egain, read_noise_e, sat_adu) -> AperturePhot
```
- CCD-equation error: `flux_err_e = sqrt(flux_e + n_pix*(sky_e + read_noise_e**2))`,
  `mag_err = 1.0857 * flux_err_e/flux_e`. `egain` from `camera.get_electrons_per_adu()`
  or `camera.egain_table` config; `read_noise_e` from config (default ~1.5 e- IMX585);
  `sat_adu` = `camera.linearity_max_adu`.
- Aperture radii: adaptive from measured FWHM (`r_ap ≈ 2–3×FWHM`, floor ~3–5 green px
  given undersampling — see `capture_panel.md` §5); annulus `r_in/r_out` configurable.

### C2. Ensemble differential photometry — `core/photometry/differential.py`
```python
def zero_point(comps: list[(AperturePhot, cat_mag)]) -> (zp, zp_err)   # weighted mean of (cat - inst)
def differential_mag(target: AperturePhot, comps, band) -> (mag, mag_err)
```
- ZP from the comparison ensemble in the chosen band (default **TG ≈ green**, per
  `capture_panel.md` §2). Target mag = `inst_mag_target + zp`. Error combines the
  target CCD error and the ensemble scatter (RMS of comps about the ZP) — the latter
  is the realistic field error and what the error bars should show.
- Drop saturated/low-SNR comps automatically; require ≥2 valid comps or flag the point
  "uncalibrated".

### C3. Light-curve accumulator — `core/photometry/lightcurve.py`
```python
@dataclass
class LcPoint:
    jd_utc: float          # exposure-midpoint JD (BJD note below)
    mag: float; mag_err: float
    airmass: float | None; fwhm: float | None; sky_adu: float | None
    comps_used: int; saturated: bool
@dataclass
class LightCurve:           # one per target AUID
    points: list[LcPoint]
    def append(...) / to_csv(path)
```
- Time: use exposure-**midpoint** UTC → JD. Note in the doc that **BJD_TDB** is the
  publishable standard; full barycentric correction is a post-processing step (astropy
  `light_travel_time`); for the live preview JD_UTC midpoint is acceptable and labelled.
- Persist `photometry.csv` (AAVSO-extended-ish columns) per target in the session
  folder, atomic write.

### C4. PhotometryWorker — `workers/photometry_worker.py`
- Input per frame (after solve + when a `TargetSet` exists): the green plane, the WCS,
  the `TargetSet`, egain/read-noise/sat from config, the exposure-midpoint time, and
  airmass (from `MountPosition.altitude` or computed in `core/photometry/airmass.py`).
- Projects each in-frame target/comp via `project_points`, measures apertures (C1),
  computes differential mags (C2), appends to each `LightCurve` (C3), and emits a
  `PhotometryFrame` (list of per-target `LcPoint` + comp diagnostics).
- Runs off the UI thread; latest-frame-wins like `PreviewProcessor`.

### C5. Light-curve panel — `ui/widgets/lightcurve_panel.py` + `panels/photometry_window.py`
- A button on the live toolbar **"Photometry"** opens `photometry_window` (a dock or
  floating window — recommend **floating, like the analysis window**, so it can sit on
  a second monitor during a run). Tabs:
  - **Light curve**: pyqtgraph plot, mag (inverted Y), JD X, **error bars**
    (`pg.ErrorBarItem`), one series per target; markers for saturated/uncalibrated
    points; hover readout; "Copy/Export CSV". Live-updates from `PhotometryFrame`.
  - **Metrics** (C6).
- Scientific-accuracy checklist surfaced in the panel: comps used, ensemble RMS,
  airmass, FWHM, a "uncalibrated/saturated" flag, and the "preview, not final" banner.

### C6. Metrics tab — `ui/widgets/metrics_panel.py`
Time series over the session (X = JD/elapsed): **CCD/heatsink temperature**
(`camera.get_ccd_temperature`), **airmass**, **sky background ADU**, **FWHM**, **HFD**,
**star count**. Source = the same per-frame stream already feeding the stats bar +
`session.json`; just retain a rolling history (or read back `session.json`). This is
"suivre la température si disponible en fct du temps, la masse d'air et autres".

**Acceptance for C:** during a (simulated) sequence on a known field, the light-curve
panel plots the target's differential magnitude with error bars updating per frame,
the metrics tab tracks temp/airmass/FWHM, and `photometry.csv` is written.

---

## 7. The "Open FITS" panel — keep, but re-purpose (resolves the redundancy)

The user's realisation is correct: **as a parallel solving surface it is redundant.**
Re-purpose it as the **field-setup / target-picker** that seeds the live workflow:

- Take one frame (or open a saved sub) → solve → **see variables + comparisons** →
  **pick the night's target(s) + comparison(s)** → they are written to the session
  `TargetSet`. That's its job: *initialise the catalogs and the target set for the
  night*, deeper/at leisure than mid-acquisition.
- It shares **100%** of the astrometry/catalog code with the live page (Workstream A);
  the only difference is "static frame, one-shot solve" vs "live, auto-solve". No
  duplicated solve/catalog/overlay logic remains.
- Everything it can do, the live page can also do; the panel just gives a calm,
  full-screen surface to do the picking without the camera running.

---

## 8. Data model & persistence (session folder)

```
~/SeerControl/sessions/<date>_<target>/.../
  *.fits             raw linear CFA subs (unchanged)
  session.json       per-frame QA roll-up (unchanged, session_log.py)
  targets.json       NEW  TargetSet (roles, RA/Dec, mags, source)   ── core/catalog/targets.py
  photometry.csv     NEW  per-target differential light curve        ── core/photometry/lightcurve.py
```
All writes **atomic** (temp + `os.replace`, mirror `session_log.write`). `targets.json`
and `photometry.csv` are the hand-off to post-processing.

### Config additions (`core/config.py` `_DEFAULTS`, kills D8)
```jsonc
"astrometry": {
  "astap_path": "", "database": "", "downsample": 2,
  "search_radius_deg": 30, "use_scale_hint": true,
  "grid_spacing_arcmin": 0,            // 0 = adaptive
  "live_search_radius_deg": 5,         // small radius w/ mount hint (auto-solve)
  "live_resolve_s": 20, "live_resolve_arcmin": 2, "live_timeout_s": 25
},
"catalog": { "mag_limit": 15.0, "max_results": 250, "include_suspected": true },
"photometry": {
  "aperture_fwhm_mult": 2.5, "aperture_min_px": 4,
  "annulus_in_px": 8, "annulus_out_px": 12,
  "read_noise_e": 1.5, "default_band": "TG",
  "min_comparisons": 2
},
"camera": { /* existing */ "egain_table": {} }
```
(Add the same fields to the Configuration page + the `AstrometrySettingsDialog`, which
already shares config keys with the config page — extend, don't fork.)

---

## 9. Testing strategy (uv-managed — `uv run --extra dev pytest`)

- **Pure core, no network/subprocess/Qt** (the bulk):
  - `green.py`: G1/G2 averaging, shape parity with `extract_plane`.
  - `astrometry_session.py`: settings builder (live vs static), `full_res_scale`,
    `overlay_for` spacing, `project_points` in/out-of-frame, `field_geometry`.
  - `photometry/aperture.py`: synthetic Gaussian star → known flux/mag/SNR; saturation
    flag; sky annulus subtraction.
  - `photometry/differential.py`: synthetic comps with known mags → recovered ZP and
    target mag within tolerance; ensemble RMS error; saturated-comp rejection.
  - `photometry/lightcurve.py`: append + CSV round-trip; `targets.py` JSON round-trip.
  - `airmass.py`: known alt → sec(z); pole/horizon guards.
- **ASTAP parse** stays text-fixture based (recorded `.wcs`), no binary needed.
- **Qt smoke** (offscreen, like `test_shell`): photometry window opens, light-curve
  panel accepts a `PhotometryFrame`, target table round-trips a `TargetSet`. Remember:
  offscreen `isVisible()` is transitively False — assert `not isHidden()`.
- **End-to-end on the simulator**: per the "test, don't ask" rule, replay a saved FITS
  as a live stream (mock Alpaca) → auto-solve → catalog → assign a target + 2 comps →
  verify a light-curve point with finite error bar is produced. See
  `docs/simulator_testing.md`.

---

## 10. Phasing / sequencing for the implementing agent

Each phase ends **green** (`uv run --extra dev pytest`) and is independently shippable.

- **Phase 0 — homogenise (Workstream A). ✅ DONE 2026-06-16.** `core/imaging/green.py`
  (single (G1+G2)/2 plane), `core/imaging/astrometry_session.py` (shared
  settings/scale/wcs/geometry/projection/overlay), `workers/astrometry_controller.py`
  (auto-solve policy + keep-last-WCS + bounded live timeout + no blind retry in live;
  `SolveSettings.allow_blind_retry` added). Both `imaging_page` and `analysis_window`
  repointed; `ImageToolbar(show_solve=…)` + an **Auto-solve** toggle on the live page;
  config `_DEFAULTS` gained `astrometry.*` / `catalog.*` / `photometry.*` /
  `camera.egain_table`. Tests: `test_green.py`, `test_astrometry_session.py`,
  `test_astrometry_controller.py` (194 passed). *No new UX surface; behaviour identical
  & stable.* (Killed D1, D3, D4, D5, D6, D7, D8, D9; D2 deferred to Phase 1.)
- **Phase 1 — live catalog + click-info + target set (Workstream B).** Overlays on the
  live page, `star_info_panel`, `targets.py` + `target_table`, grid edge labels.
  (Kills D2.)
- **Phase 2 — re-purpose Open FITS (§7).** Strip duplicated logic; make it the target
  picker that writes the session `TargetSet`.
- **Phase 3 — photometry core (Workstream C1–C3).** Pure aperture + differential +
  light-curve + airmass, fully unit-tested, no UI.
- **Phase 4 — photometry UI (C4–C6).** `PhotometryWorker`, `photometry_window`,
  light-curve panel with error bars, metrics tab, `photometry.csv`.
- **Phase 5 — polish.** BJD note/option, export formats (AAVSO), per-target aperture
  tuning, persistence of panel layout.

---

## 11. Open decisions (surface to the user before/while building)

1. **Photometry window**: floating (second monitor) vs docked rail tab? (Recommend
   floating, mirrors the analysis window.)
2. **Star-info on click**: ✅ RESOLVED 2026-06-16 → **on-image info card** (corner-
   anchored, with role buttons); overlay toggles in a **slim chip bar under the
   toolbar**. (User picked the card over a rail tab / cursor popup.)
3. **Auto-solve default**: on or off at startup? (Recommend off; user arms it — solving
   every frame costs CPU and only matters once framed.)
4. **Band for differential**: lock to TG (green) for v1, expose B/V later? (Recommend
   TG-only v1.)
5. **Time standard**: JD_UTC midpoint for the live preview, BJD_TDB only in
   post/export? (Recommend yes — keep the live path simple and labelled.)

---

## 12. Definition of done (whole effort)

- One shared, tested astrometry pipeline; live + Open-FITS behave identically; a failed
  live solve never blanks the grid; auto-solve tracks a sequence without UI freeze.
- On the live page: variables + comparisons overlaid after solve; click any star →
  full info + role assignment; RA/Dec grid with edge coordinate labels.
- A persistent `TargetSet` (`targets.json`) drives a live differential light-curve
  preview with scientifically-honest error bars, plus a metrics panel (temp/airmass/
  FWHM/sky vs time), with `photometry.csv` written per target.
- Everything Qt-free in `core/` is unit-tested; the simulator end-to-end passes.
- `docs/capture_panel.md` §0 still holds: saved FITS remain raw, linear, CFA.
```
