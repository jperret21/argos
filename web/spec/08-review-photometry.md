# Review: photometry window, light curves, comparison stars, session review: Qt inventory and web redesign

Spec 08. Author: review-photometry agent, 2026-11-01. Source of truth: the Qt code on branch
`explore/web-ui` (read in full); the web side follows `web/src/design/BRAND.md` and
`icon-inventory.json`. Every number in section 1 is traced to code; where a behaviour was
only observed on an offscreen render it is marked *(observed)*.

## 0. Scope

### 0.1 Files covered

In scope (read line by line):

| File | Lines | Content |
|---|---|---|
| `argos/ui/panels/photometry_window.py` | 327 | `PhotometrySetupPanel` (aperture / reference criteria), `PhotometryWindow` ("Field photometry") |
| `argos/ui/widgets/lightcurve_panel.py` | 324 | `LightCurvePanel` (target plot + comparison-diagnostic plot) |
| `argos/ui/widgets/comparison_table.py` | 262 | `ComparisonEnsembleTable` (live ensemble), `ComparisonQualityTable` (Review), `_quality_values` |
| `argos/ui/widgets/comparison_curve_panel.py` | 85 | `ComparisonCurvePanel` (selectable comparison plot, Review) |
| `argos/ui/widgets/target_curve_panel.py` | 84 | `TargetCurvePanel` (selectable target plot, Review) |
| `argos/ui/widgets/session_review.py` | 65 | `SessionQualityPlot` (frame-quality trend, Review) |

Hosts and tabs read because the in-scope widgets live inside them (inventoried here so nothing is
lost; the consolidation step should de-duplicate with the Observe / Settings specs):

| File | Lines | Why |
|---|---|---|
| `argos/ui/pages/analyze_page.py` | 780 | `AnalyzeScreen` = the Qt **Review** page that hosts 4 of the 6 in-scope widgets |
| `argos/ui/widgets/metrics_panel.py` | 80 | "Metrics" tab of the Photometry window |
| `argos/ui/widgets/target_table.py` | 94 | "Targets" tab of the Photometry window |
| `argos/ui/widgets/variable_table.py` | 207 | "Variable stars" tab of the Photometry window |
| `argos/ui/pages/imaging_page.py` (lines 197-306, 757-780, 2049-2438, 2863) | 2888 | creates, feeds and wires the Photometry window; live "Differential photometry" dock |
| `argos/ui/shell.py` (lines 185-293, 443-457) | | menu entries that open these windows |

Behaviour followed into: `argos/core/photometry/{lightcurve,differential,uncertainty,quality,params,session,aperture,airmass,tracking}.py`,
`argos/core/catalog/{targets,photometry,aavso}.py`, `argos/core/session/{acquisition_engine,review,types}.py`,
`argos/workers/photometry_batch_worker.py`, `argos/core/config.py:137-162`.

File references below use the basename (`photometry_window.py:240`); the two ambiguous ones are
written `photometry/session.py` and `catalog/photometry.py`.

### 0.2 Every window, panel, dialog and pop-up in scope

| # | Element | Kind | How it is opened today |
|---|---|---|---|
| W1 | `PhotometryWindow` "Field photometry" (`photometry_window.py:200`) | top-level, non-modal window (Qt.Window flag, parent = ImagingPage), 960 x 700, min 780 x 620 | Menu Photometry ▸ "Photometry setup…" (`shell.py:270-277`, opens on the Variable stars tab); Photometry ▸ "Live curves & diagnostics…" (`shell.py:278-281`); automatically after a batch re-run (`imaging_page.py:2367`); a **separate, unwired instance** per CSV from Review "Open curve CSV…" (`analyze_page.py:732-763`) and File ▸ "Open session photometry…" Ctrl+Shift+O (`shell.py:197-201` → `analyze_page.py:601-603`) |
| W1.T1 | Tab "Variable stars" = `VariableTable` | tab | tab bar; forced visible by `show_variable_stars()` (`photometry_window.py:268-270`) |
| W1.T2 | Tab "Light curve" = `LightCurvePanel(view="both")` | tab | tab bar |
| W1.T3 | Tab "Metrics" = `MetricsPanel` | tab | tab bar |
| W1.T4 | Tab "Targets" = `TargetTable` | tab | tab bar |
| W1.T5 | Tab "Comparison stars" = `ComparisonEnsembleTable` | tab | tab bar |
| W1.T6 | Tab "Aperture · references" = `PhotometrySetupPanel` | tab | tab bar |
| D1 | "Export light curve" save dialog | native `QFileDialog`, modal | W1 "Export measurements…" |
| D2 | "Export AAVSO" save dialog | native `QFileDialog`, modal | W1 "Export target (AAVSO)…" |
| D3 | "Folder of saved subs" folder dialog + "Batch photometry" progress dialog + 4 message boxes | native dialogs | Photometry ▸ "Re-run subs…" (`shell.py:282-285` → `imaging_page.py:2248-2318`) |
| P1 | `AnalyzeScreen` "Review" page (`analyze_page.py:59`) | page (rail Analyze/Review, F4) with a nested `QMainWindow` dock workspace in a scroll area | rail, F4 (`shell.py:230-234`) |
| P1.d1 | Dock "Source light curve" = `TargetCurvePanel` + point-info row | dock (movable, closable, floatable) | default layout |
| P1.d1+ | Docks "Target {n}" / "Target — {name}" (one per extra target) | dock | created on session open (`analyze_page.py:490-528`) |
| P1.d2 | Dock "Frame quality — FWHM" = `SessionQualityPlot` | dock | default layout |
| P1.d3 | Dock "Comparison stars" = `ComparisonCurvePanel`, renamed "Comparison — {name}" | dock | default layout |
| P1.d3+ | Docks "Comparison star {n}" / "Comparison — {name}" | dock | session open (one per comparison) or "+ Comparison plot below" |
| P1.d4 | Dock "Comparison quality" = `ComparisonQualityTable` | dock, tabified right | default layout |
| P1.d5 | Dock "Frames" (9-column table) | dock, bottom, hidden by default | panel toggle |
| P1.d6 | Dock "Session metadata" (Field / Value) | dock, right tab, hidden | Panels ▾ menu |
| P1.d7 | Dock "AAVSO export" (observer code, band) | dock, right tab, hidden | Panels ▾ menu |
| P1.m1 | "Panels ▾" menu | `QToolButton` instant pop-up `QMenu` | toolbar |
| P1.m2 | "Arrange ▾" menu (rebuilt on every show) | `QToolButton` instant pop-up `QMenu` | toolbar |
| P1.D4 | "Open Argos session folder" folder dialog | native, modal | "Open session…" (card or toolbar) |
| P1.D5 | "Open session light curve" file dialog | native, modal | "Open curve CSV…", File ▸ Open session photometry… |
| P1.D6 | "Open FITS frame" file dialog | native, modal | "Open FITS…" (opens `AnalysisWindow`, other spec) |
| P1.D7 | "Could not open session" / "Frame unavailable" warnings | `QMessageBox.warning`, modal | errors |
| C1 | pyqtgraph context menu on the Review quality plot (View All, X axis, Y axis, Mouse Mode, Plot Options, Export…) | right-click pop-up | right-click on `SessionQualityPlot` only (menu not disabled, `session_review.py:40`) |
| C2 | Legend entries (click toggles a series) | pyqtgraph legend | every `LightCurvePanel` (`lightcurve_panel.py:108`) |
| X1 | "Differential photometry" dock on the Capture page = a second live `LightCurvePanel` | dock (Observe spec owns the dock; the widget is in scope) | Capture panel strip (`imaging_page.py:244, 301-306, 340`) |

No tooltip-driven popovers exist; tooltips are plain `setToolTip` strings, quoted in the tables.

## 1. Inventory (Qt, as it is today)

### 1.0 Data model and science reference (shared by every plot, table and export)

This is what the numbers on screen are. The web version must display exactly these quantities.

**Measurement** (live: `acquisition_engine.py:1333-1384`; batch: `photometry_batch_worker.py:159-199`; both call
`params.py:80-111` → `photometry/session.py:47-130`):

| Quantity | Definition | Code |
|---|---|---|
| Plane, pixels | Green plane of the raw Bayer sub (`green_plane`); every radius is in **green-plane px** | `acquisition_engine.py:1348`, `aperture.py:1-5` |
| Series FWHM | First measured FWHM of the run, held for the series; re-sampled on object change and after autofocus; 3.0 px default (`DEFAULT_FWHM`) when none measured. Batch: measured once on the first readable frame | `acquisition_engine.py:1341-1343, 665, 736`; `params.py:25`; `photometry_batch_worker.py:201-218` |
| Aperture radius | `r_ap = max(aperture_min_px, aperture_fwhm_mult × FWHM)` | `params.py:70-77` |
| Sky annulus | `r_in = max(annulus_in_px, r_ap + 1)`, `r_out = max(annulus_out_px, r_in + 2)` | `params.py:95-97`, `acquisition_engine.py:1229-1233` |
| Sky | median of annulus pixels (ADU/px) | `aperture.py:73-75` |
| Flux | `sum(aperture) − sky × n_pix` (ADU) | `aperture.py:76-78` |
| Saturated | aperture peak ≥ `camera.linearity_max_adu` (50000) | `aperture.py:80`, `params.py:64` |
| Suspect | peak > 10 σ_sky above sky while its 4 neighbours average < 10 % of the peak excess (hot pixel / cosmic) | `aperture.py:109-136` |
| Noise, SNR | CCD equation in electrons (egain from `camera.egain_table` → driver → sensor model; read noise `photometry.read_noise_e` 1.5 e⁻) | `aperture.py:83-88`, `acquisition_engine.py:1246-1258` |
| Instrumental mag | `−2.5 log10(flux_ADU)`, error `1.0857 σ_e / flux_e` | `aperture.py:90-94` |
| Ensemble zero point | over comparisons with a catalogue mag in `photometry.default_band` (fallback **V**; VSP never supplies TG) that are unsaturated: `ZP = mean(cat − inst)` after a median/MAD clip at `max(2.5 × 1.4826 × MAD, 0.01 mag)` (≥ 3 pairs, ≤ 2 iterations); `zp_rms` = sample std | `photometry/session.py:42-44, 104-113`; `differential.py:59-92` |
| Target / check magnitude ("Differential mag") | `inst + ZP`; formal error `sqrt(inst_err² + (zp_rms/√n)²)`, rounded to 4 decimals. Check stars are calibrated exactly like targets, never part of the ensemble | `differential.py:95-132`; `photometry/session.py:73-76, 143-148` |
| Comparison magnitude | **leave-one-out**: each comparison calibrated against the ensemble minus itself (vetting only) | `photometry/session.py:77-81, 149-153` |
| Relative flux | `F_target / Σ F_comp` over comparisons with flux > 0, SNR > 0, not saturated **and not suspect** (no catalogue mag needed); error `ratio × sqrt((1/SNR_t)² + (sqrt(Σ(F/SNR)²)/ΣF)²)`. Comparisons: leave-one-out ratio | `differential.py:135-162`; `photometry/session.py:114-123` |
| Point kept | when the magnitude **or** the ratio exists; `mag = NaN` when only the ratio exists | `acquisition_engine.py:1375-1383, 1432` |
| Systematic floor | once a curve has ≥ 10 valid points (or a manual `photometry.systematic_floor_mag`): `σ_real` = robust σ of second differences / √6; `σ_syst = sqrt(max(0, σ_real² − median(formal)²))`; every point's `mag_err := hypot(formal_mag_err, σ_syst)`, recomputed after **each** new point, for every role (comparisons included) | `uncertainty.py:38-98`; `acquisition_engine.py:1481-1504`; batch `photometry_batch_worker.py:320-338` |
| Time | `jd_utc` = exposure **midpoint** JD (UTC). `bjd_tdb` via astropy when `site.latitude/longitude` are set, else empty | `acquisition_engine.py:1357, 1418-1422`; `airmass.py:52-98`; batch: DATE-OBS + EXPTIME/2 `photometry_batch_worker.py:358-390` |
| Airmass | the **target's own** altitude at `jd_utc` (Pickering 2002) when the site is known; else the mount's last altitude (live) / none (batch) | `acquisition_engine.py:1423-1429`; `airmass.py:30-49` |
| Magnitude system | instrumental green (band code `TG`), zero-pointed on comparison catalogue mags in the configured band or V; **untransformed** (AAVSO `TRANS=NO`), ensemble (`CNAME=ENSEMBLE`) | `lightcurve.py:204-254`, `config.py:143` |

**`LcPoint` fields** (`lightcurve.py:38-62`) = CSV columns (`lightcurve.py:14-30`):
`jd_utc, bjd_tdb, mag, mag_err (final, with floor), formal_mag_err, sigma_syst, airmass, fwhm (series aperture FWHM, not per-frame seeing), sky_adu, comps_used, relative_flux, relative_flux_err, relative_comps_used, saturated (0/1), suspect (0/1)`.

**Files written**:

| File | Schema | Code |
|---|---|---|
| `<run>/photometry/<role>_<object>_<auid-or-name>.csv` (live, one per star) | the 15 columns above, no identity columns | `acquisition_engine.py:1260-1269, 1476-1479`; `lightcurve.py:82-90` |
| `~/…/targets/<object>_<tag>.csv` (no run yet, or batch re-run) | same 15 columns, **no role prefix** | `acquisition_engine.py:1267-1269`; `photometry_batch_worker.py:392-402` |
| "Export measurements…" | 19 columns: `star_id, role, name, auid` + the 15 | `lightcurve.py:35, 136-147` |
| "Export target (AAVSO)…" | AAVSO Extended: `#TYPE=EXTENDED`, `#OBSCODE=`, `#SOFTWARE=Argos`, `#DELIM=,`, `#DATE=JD`, `#OBSTYPE=CCD`, header `#NAME,DATE,MAG,MERR,FILT,TRANS,MTYPE,CNAME,CMAG,KNAME,KMAG,AMASS,GROUP,CHART,NOTES`; one row per finite **target** point: `NAME`=upper-cased name, `DATE`=jd_utc 6 dp, `MAG`/`MERR` 4 dp (MERR includes the floor), `FILT`=band, `TRANS=NO`, `MTYPE=STD`, `CNAME=ENSEMBLE`, `CMAG=na`, `KNAME,KMAG` = first check curve with points, matched on identical JD (else `na,na`), `AMASS` 3 dp or `na`, `GROUP=na`, `CHART` = the single VSP chart id of all comparisons (else `na`), `NOTES=na` | `lightcurve.py:204-262`; `targets.py:219-228` |
| `<run>/photometry_quality.json` | leave-one-out report (below), written after every measured frame, **only during a sequence run** | `acquisition_engine.py:1386-1413`; `quality.py:101-107` |

**Comparison quality report** (`quality.py:22-98`), per comparison: `n_valid` (unsaturated finite points),
`scatter_mag` = robust second-difference σ of its leave-one-out mags, `median_formal_error_mag`, `status`:
`insufficient_data` (< `min_points` or no estimate), else `noisy` if median formal > `max_formal_error_mag`,
else `unstable` if scatter > `max_scatter_mag`, else `stable`. Defaults 10 points / 0.10 mag / 0.10 mag
(`config.py:155-157`). Ensemble: `selection_status` = `insufficient_data` | `not_ready` (< 3 stable) |
`live_preview_consistent`, plus `scientific_note`. The Qt UI shows the per-star rows only.

### 1.1 PhotometryWindow "Field photometry" (`PhotometryWindow`, `photometry_window.py:200`, top-level window, non-modal, separate OS window)

- Purpose: second-monitor companion during acquisition: target pick, live curves, metrics, ensemble, aperture; plus the two exports. Display only: the page owns all state (`photometry_window.py:1-7`).

| # | Control | Qt type | Label / tooltip (exact text) | Default / range / units | Enabled / visible when | Shortcut | Action: handler -> effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Preview banner | `QLabel` (WARNING colour, 11 px) | "Preview — raw, uncalibrated subs. BJD_TDB is recorded when the site and exposure time are available. Relative flux is a live diagnostic, not a detrended transit result; publishable reduction remains in Siril." | | always | | none (`photometry_window.py:211-220`) | |
| 2 | Tab bar | `QTabWidget` | "Variable stars", "Light curve", "Metrics", "Targets", "Comparison stars", "Aperture · references" | first tab = Variable stars; "Photometry setup…" forces it (`photometry_window.py:268-270`) | always | none | `photometry_window.py:228-236` | no |
| 3 | Export measurements… | `QPushButton` | tooltip "Export target, check-star and comparison measurements" | | always enabled; silently does nothing when no curve has points (`photometry_window.py:303-305`) | | `_export_csv` (`photometry_window.py:302-310`) -> save dialog "Export light curve", default `~/photometry.csv`, filter "CSV (*.csv)" -> `write_curves_csv` (`lightcurve.py:136-147`), 19 columns, all roles | |
| 4 | Export target (AAVSO)… | `QPushButton` | tooltip "Export science targets only; comparison curves are diagnostics" | | always enabled; silent no-op without a target curve with points (`photometry_window.py:313-315`) | | `_export_aavso` (`photometry_window.py:312-327`) -> dialog "Export AAVSO", `~/aavso.txt`, "Text (*.txt)" -> `write_aavso(obscode, filt, chart=comparison_chart_id(target stars))` | obscode `observer.obscode`, band `photometry.default_band` (read) |
| 5 | Window title | title bar | "Field photometry", then "Field photometry — {object}" | | | | `set_export_meta` (`photometry_window.py:261-266`), called only when the window is first created (`imaging_page.py:2092-2099`) | |
| 6 | Window close | OS close | | | | OS | hides the window (no delete-on-close); `imaging_page.py:2863-2865` closes and drops it on page teardown | |

- Displayed data: the six tabs (1.2-1.7). Points arrive through `feed_point` (`photometry_window.py:272-283`) only while the window is visible (`imaging_page.py:2404-2406`); a full replay happens on every open (`load_curves`, `imaging_page.py:2125-2132`) and on every `curves_changed` (`imaging_page.py:2376-2388`).
- Implicit behaviours: one instance per Capture page, created lazily (`imaging_page.py:2091-2123`); `load_curves` copies the dict, then the page re-points `lightcurves` at the live engine dict so exports include later points (`imaging_page.py:2130-2132`); `set_targets` refreshes Targets + Comparisons tabs (`photometry_window.py:285-289`) on every `targets_changed` (`imaging_page.py:2015-2019`). When opened from Review (CSV), no signal is connected and `set_values` is never called (`analyze_page.py:745-763`).
- Messages: none of its own (exports give no feedback).
- Problems: see P5, P7, P8, P9, P10 in 1.15.

### 1.2 Light curve tab and every live curve: `LightCurvePanel` (`lightcurve_panel.py:25`, widget; view "both" in W1 and in the Capture dock X1, "target" / "comparison" inside 1.11 / 1.12)

- Purpose: science curve (target + check) and comparison diagnostics as two X-linked plots, so a comparison ensemble spanning several magnitudes does not squash the science curve (`lightcurve_panel.py:1-8`).

| # | Control | Qt type | Label / tooltip (exact text) | Default / range / units | Enabled / visible when | Shortcut | Action: handler -> effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Header | `QLabel` | "Source and comparison stars" / "Source light curve" / "Comparison-star diagnostics" (per view) | | always | | `lightcurve_panel.py:45-55` | |
| 2 | Target plot | `pg.PlotWidget` | y "Differential mag" (relative-flux mode "Relative flux (median-normalised)"), x "Time (JD UTC)"; grid α 0.2; **y inverted** (brighter up) in mag mode; legend; context menu disabled | min height 220, splitter share 3 | views both / target | | `_make_plot` `lightcurve_panel.py:57-61, 99-109` | |
| 3 | Comparison plot | `pg.PlotWidget`, X-linked to 2 | y "Δmag from own median" (flux mode "Δ relative flux"), x "Time (JD UTC)"; inverted in mag mode | min height 180, share 2 | views both / comparison | | `lightcurve_panel.py:62-69` | |
| 4 | Plot splitter | vertical `QSplitter`, children not collapsible | | sizes 320 / 220 | view both | | `lightcurve_panel.py:70-81` | no |
| 5 | Show uncertainties | `QCheckBox` | tooltip "Show the per-image photometric uncertainty" | checked | always | | `_apply_error_visibility` (`lightcurve_panel.py:302-304`) -> shows/hides every error bar, mirrored with series visibility (`251-258`) | no (resets per instance) |
| 6 | Relative flux | `QCheckBox` | tooltip "Median-normalised live preview; final normalisation and detrending belong to post-processing" | unchecked | always | | `_set_relative_flux` (`lightcurve_panel.py:306-319`) -> relabels axes, un-inverts y, re-plots every series, auto-ranges | no |
| 7 | Legend entry | pyqtgraph `LegendItem` sample | series name | one per series | 2+ series | mouse click | pyqtgraph toggles the `PlotDataItem`; `visibleChanged` mirrors error bars and saturation marks (`lightcurve_panel.py:186-191, 251-258`) | no |
| 8 | Point click | scatter `sigPointsClicked` | | | always | mouse | emits `point_clicked(name, x, y_displayed, err_displayed)` (`lightcurve_panel.py:181-185, 288-296`); connected only in Review (1.10 #23) | |
| 9 | Point hover | scatter `sigPointsHovered` | | | **never fires**: scatter `hoverable` is False (pyqtgraph 0.13.7 default; verified) | | `point_hovered` (`lightcurve_panel.py:176-180`) | |
| 10 | Plot mouse | pyqtgraph ViewBox | | | always | left-drag pan, wheel zoom, right-drag axis zoom | built-in; X linked between 2 and 3 | |
| 11 | Auto-range button | pyqtgraph "A" button, bottom-left on hover | | | after a manual zoom | | built-in; also `_auto_range()` after every `set_curves` and flux toggle (`lightcurve_panel.py:277, 319, 321-324`) | |

- Displayed data per series (`add_point` `lightcurve_panel.py:115-209`, `_refresh_series` `211-249`):
  - marker `o` 6 px, colour = 6-colour cycle by **insertion order across both plots** (`SUCCESS, CYAN, WARNING, VARIABLE, ACCENT, DANGER`, `lightcurve_panel.py:20-22, 131-132`), not by role;
  - error bar = vertical ±err, no caps (`lightcurve_panel.py:243-247`), err = `mag_err` (with systematic floor) or `relative_flux_err`; negative / non-finite errors drawn as 0 (`194-202`);
  - saturated points: extra red `x` 11 px on top (`lightcurve_panel.py:152-160, 203-208`); `suspect` is **not displayed**;
  - routing: role `comparison` → comparison plot, **everything else (target and check)** → target plot (`lightcurve_panel.py:133-138`);
  - mag mode: target/check y = `mag`; comparison y = `mag − median(mag of that series)`; flux mode: y = `relative_flux / median(relative_flux of that series)`, errors divided by the same median; comparisons additionally `− 1` (`lightcurve_panel.py:231-241`). Medians include saturated points.
  - x = `jd_utc` (full JD; pyqtgraph SI-scales the ticks to "2.46134630 … (x1e+06)" *(observed)*). BJD is never plotted.
- Implicit behaviours: `set_curves` clears and replays (`lightcurve_panel.py:260-277`); points with non-finite jd, or neither finite mag nor flux, are skipped (`127-128`); a series with no finite y is emptied (`224-230`); flux baseline ≤ 0 aborts the refresh, leaving the previous drawing (`233-234`).
- Messages: none.

### 1.3 Metrics tab: `MetricsPanel` (`metrics_panel.py:26`, tab of W1)

| # | Control | Qt type | Label / tooltip | Default / options | Visible | Shortcut | Action | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Metric | label "Metric:" + `QComboBox` | | options in order: "Airmass", "FWHM (green px)", "Sky (ADU)", "HFD (green px)", "Star count", "Sensor temp (°C)"; default Airmass | always | | `_refresh` (`metrics_panel.py:72-76`) | no |
| 2 | Plot | `pg.PlotWidget` | x "elapsed (s)", y = metric label | line + dots | always | mouse pan/zoom | `metrics_panel.py:46-59` | |

- Data source (`imaging_page.py:2419-2433`, `2370-2374`): one sample per processed preview frame **only while W1 is visible**: `sky=metrics.sky_adu`, `fwhm=stars.mean_fwhm`, `hfd`, `stars=star_count`, `airmass` from the **mount** altitude; `temp` read from the driver at each measurement pass. x = seconds since the first sample since page creation (`imaging_page.py:2414-2417`, never reset; `MetricsPanel.clear` is never called).

### 1.4 Targets tab: `TargetTable` (`target_table.py:27`, tab of W1). Cross-reference: Observe spec.

| # | Control | Qt type | Label | Default | Enabled | Shortcut | Action | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Target set table | `QTableWidget`, read-only, single row | columns "Role", "Name", "RA", "Dec", "Mags" (`target_table.py:24`); RA `format_ra_hms`, Dec `format_dec_dms`, mags "V 11.40  B 12.10" | | | | row selection -> `star_selected(key)` -> `imaging_page.py:2049-2077`: marks the star on the image with the photometry aperture and "{Role} · {name}"; WARN "Selected star is outside the solved image." | |
| 2 | Remove selected | `QPushButton` | "Remove selected" | | always (no-op without selection) | | `remove_requested(key)` -> `acquisition_engine.py:1235-1240` (persist targets.json, reset tracker, re-emit); no confirmation | targets.json |
| 3 | Copy TSV | `QPushButton` | "Copy TSV" | | always | | clipboard: header + every row as displayed (`target_table.py:85-94`) | |

### 1.5 Variable stars tab: `VariableTable` (`variable_table.py:58`, tab of W1). Cross-reference: Observe spec.

| # | Control | Qt type | Label / tooltip | Default / range | Enabled | Shortcut | Action | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Filter | `QLineEdit` with clear button | placeholder "Filter by designation or type…"; tooltip "Case- and space-insensitive; for example, XX Cyg or xxcyg" | empty | always | | `_apply_filters` (`variable_table.py:137-186`) | no |
| 2 | Brightest mag ≤ | `QDoubleSpinBox` + label | tooltip "Show variables whose brightest catalogued magnitude is at or brighter than this limit" | 0.0-20.0, step 0.5, 1 dp, 0 = "Any" | always | | same; also emits `visible_rows_changed` -> image markers filtered (`imaging_page.py:1777-1780`) | no |
| 3 | Count | `QLabel` | "0 stars" then "{k} of {n} star(s)" | | | | `variable_table.py:184-185` | |
| 4 | Variables table | `QTableWidget`, read-only, single row | columns "", "Name", "Type", "Mag", "Period (d)", "Sep (′)"; "●" = already in the target set; suspected variables muted | catalogue order (brightest first) | | header click toggles sort asc/desc (`variable_table.py:188-199`) | | |
| 5 | Row double-click | | | | | double-click | = #6 | |
| 6 | Set as target | `QPushButton` | "Set as target"; tooltip "Make this variable a photometry target (comparison stars are\npicked automatically when none are chosen yet). Same action as\nclicking its circle on the image." | | always | | `target_requested(index)` -> `imaging_page.py:2224-2242` -> `engine.set_target_role` (auto comparisons) ; log OK "Target: {name}" | targets.json |

### 1.6 Comparison stars tab: `ComparisonEnsembleTable` (`comparison_table.py:54`, tab of W1)

- Purpose: see and prune the ensemble that forms the differential zero point; live quality columns.

| # | Control | Qt type | Label / tooltip (exact) | Default / range / units | Enabled / visible | Shortcut | Action: handler -> effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Hint | `QLabel` muted | "Comparison ensemble — catalogue magnitudes enable differential magnitudes; relative-flux preview only needs stable, unsaturated comparison stars." | | always | | `comparison_table.py:71-77` | |
| 2 | Automatically propose | label + `QSpinBox` | suffix " calibrated stars"; tooltip "Number of calibrated VSP comparison stars Argos proposes when a target is selected" | 5, range 1-12 (Settings duplicate allows 1-20, `astrometry_settings.py:262-267`) | always | | `auto_count_changed` -> `imaging_page.py:2167-2183`: `config.set` then `engine.reselect_comparison_stars()` (replaces every VSP comparison, pilot re-measure, on **every step**) | `photometry.auto_comparisons` |
| 3 | Ensemble table | `QTableWidget`, read-only, single row, last column stretches | "Name", "AUID", "RA (J2000)", "Dec (J2000)", "Catalogue mags", "Source", "Samples", "Scatter (mag)", "Formal error (mag)", "Live status" (`comparison_table.py:29-30`) | rows = target-set stars with role comparison | | | row selection -> `star_selected(key)` -> image highlight (as 1.4 #1) | |
| 4 | Count | `QLabel` | "No comparison stars — refresh the catalogue after a successful solve." / "{n} calibrated comparison(s) · {m} uncalibrated manual star(s)" / "{n} calibrated comparison star(s)" | | | | `comparison_table.py:162-173` | |
| 5 | Remove selected | `QPushButton` | "Remove selected" (no tooltip) | | always (no-op without selection) | | `remove_requested(key)` -> `acquisition_engine.py:1235-1240`; during a run also rewrites `photometry_selection.json` and appends `photometry_selection_history.jsonl` (`995-1008`); no confirmation | targets.json |
| 6 | Refresh catalogue | `QPushButton` | tooltip "Fetch VSP comparison-star proposals again for the solved field" | | always; silent no-op while unsolved (`acquisition_engine.py:838-840`) | | `engine.refetch_catalog` (`acquisition_engine.py:815-832`) -> clears VSX/VSP/Gaia/SIMBAD caches, network re-query in `CatalogWorker`; `_on_catalog` back-fills comparisons (`904-965`) | catalogue disk cache |
| 7 | Recommend from pilot | `QPushButton` | tooltip "Replace VSP suggestions using SNR, saturation and brightness measured on the solved pilot image" | | always | | `imaging_page.py:2185-2196` -> `engine.reselect_comparison_stars` (`acquisition_engine.py:1053-1075`): drops comparisons with source `vsp`/`vsp_auto`, keeps manual ones, re-picks with `auto_comparison_stars` score `0.5·SNR + 0.4·Δmag + 0.1·distance` (`catalog/photometry.py:88-170`); no confirmation | targets.json |
| 8 | Copy TSV | `QPushButton` | "Copy TSV" | | always | | `_on_copy` (`comparison_table.py:195-205`): header + every row as displayed | |

- Displayed data: Name = `display_name` (AUID for numeric VSP labels, `targets.py:50-63`); Catalogue mags `"{band} {mag:.2f}"` joined by two spaces or "—"; Source `vsp_auto` / `vsp` / `vsx` / `manual`; quality from the last report (`set_quality_report`, `comparison_table.py:175-183`) keyed by AUID or name: Samples = `n_valid`, Scatter / Formal error 4 dp or "—", Live status "Stable" / "Unstable" / "Noisy" / "Waiting for 10 points" (hard-coded 10) / "Waiting for data" (no entry) (`comparison_table.py:33-51`).
- Implicit: refreshed on every `targets_changed` and `comparison_quality_updated` (`imaging_page.py:2409-2412`); cleared to "Waiting for data" on object change or sequence start (`acquisition_engine.py:269-274`).
- Messages (activity log, via `imaging_page.py`): OK "Photometry: selected {n} pilot-qualified comparison(s)."; INFO "Photometry: requested {count} comparison(s); {selected} pilot-qualified VSP star(s) selected."; OK "Photometry: replaced the VSP ensemble with {n} pilot-qualified star(s)."; WARN "Photometry: no pilot-qualified comparison found — solve a full-resolution frame first."; engine OK "Photometry: {n} pilot-qualified comparison(s) selected for {target}"; WARN "Photometry: only {n} of {wanted} requested comparisons pass the pilot quality gate (SNR ≥ {min_snr}, Δmag ≤ {max_delta}, distance ≤ {max_sep}′)." (`acquisition_engine.py:1146-1157`); catalogue OK "Catalog: {n} calibrated VSP comparison star(s) available" / WARN "Catalog: no calibrated VSP comparison stars returned for this field. Refresh the field catalogue or choose calibrated comparisons manually." / WARN "Catalog: {error}" (`acquisition_engine.py:905-952`).

### 1.7 Aperture · references tab: `PhotometrySetupPanel` (`photometry_window.py:36`, tab of W1)

| # | Control | Qt type | Label / tooltip (exact) | Default / range / step / units | Enabled | Shortcut | Action | Persisted (config key) |
|---|---|---|---|---|---|---|---|---|
| 1 | Intro | `QLabel` muted | "Live preview only: Argos measures circular apertures on the raw subs and estimates the local sky in a surrounding annulus. The aperture follows the measured FWHM; final calibrated reduction remains in Siril." | | | | `photometry_window.py:50-57` | |
| 2 | Aperture radius (adaptive) | `QDoubleSpinBox` | tooltip "Photometric aperture radius; 2–3 × FWHM is a typical start." | 2.5; 1.00-6.00, step 0.25, 2 dp, " × FWHM" | always | | every `valueChanged` -> `setting_changed` -> `imaging_page.py:2152-2165`: `config.set` (saves the JSON file), refresh geometry label, redraw the selection ring, log INFO "Photometry measurement geometry updated." | `photometry.aperture_fwhm_mult` |
| 3 | Aperture radius floor | `QDoubleSpinBox` | tooltip "Lower limit for the aperture radius in green-plane pixels." | 4.0; 2.0-30.0, step 0.5, 1 dp, " green px" | always | | same | `photometry.aperture_min_px` |
| 4 | Background annulus — inner radius | `QDoubleSpinBox` | tooltip "Inner radius of the local-sky annulus." | 8.0; 3.0-60.0, step 0.5, " green px" | always | | same | `photometry.annulus_in_px` |
| 5 | Background annulus — outer radius | `QDoubleSpinBox` | tooltip "Outer radius of the local-sky annulus." | 12.0; 5.0-80.0, step 0.5, " green px" | always | | same | `photometry.annulus_out_px` |
| 6 | Reference-star minimum S/N | `QDoubleSpinBox` | tooltip "Automatic comparison candidates below this pilot-frame SNR are rejected." | 10.0; 3.0-100.0, step 1.0, 1 dp, " SNR" | always | | same (applies at the next automatic selection only) | `photometry.comparison_min_snr` |
| 7 | Reference-star brightness difference | `QDoubleSpinBox` | tooltip "Maximum instrumental brightness difference from the target for automatic comparisons." | 1.5; 0.2-5.0, step 0.1, " mag" | always | | same | `photometry.comparison_max_delta_mag` |
| 8 | Reference-star maximum separation | `QDoubleSpinBox` | tooltip "Maximum target-to-comparison separation. Nearby references reduce flat-field and field-rotation systematics; Argos will propose fewer stars rather than fill the ensemble with remote candidates." | 25; 5-120, step 5, 0 dp, " ′" | always | | same | `photometry.comparison_max_separation_arcmin` |
| 9 | Effective geometry | `QLabel` (accent, bold) | "Current live geometry: aperture {a:.1f} px · background annulus {i:.1f}–{o:.1f} px", or "Current live geometry: waiting for a measured FWHM" | | | | `set_geometry` (`photometry_window.py:189-197`) from `engine.photometry_geometry()` (`acquisition_engine.py:1222-1233`); refreshed on open, on each change and on each processed frame while visible (`imaging_page.py:779-780`) | |
| 10 | Note | `QLabel` muted | "All radii are green-plane pixels. Argos constrains the background annulus outside the aperture; the selected-star ring uses the current aperture." | | | | `photometry_window.py:148-154` | |

- Implicit: `set_values` writes the widgets with signals blocked (`photometry_window.py:166-187`). The engine always returns a geometry (default FWHM 3.0 px when none was measured, i.e. 7.5 px with the defaults), so the "waiting" text only appears before `set_values` and the label never says that the default FWHM is being used.

### 1.8 Entry points outside the window (`shell.py`, `imaging_page.py`)

| # | Control | Qt type | Label / tooltip (exact) | Shortcut | Action | Persisted |
|---|---|---|---|---|---|---|
| 1 | Photometry ▸ Photometry setup… | `QAction` | tooltip "Choose a variable-star target and review the comparison-star ensemble in this field" | | `open_photometry(select_variable=True)` (`shell.py:270-277`, `imaging_page.py:2083-2145`) | |
| 2 | Photometry ▸ Live curves & diagnostics… | `QAction` | tooltip "Open live differential light curves, image quality and selected stars" | | `open_photometry()` (`shell.py:278-281`) | |
| 3 | Photometry ▸ Re-run subs… | `QAction` | tooltip "Re-run differential photometry over a folder of saved subs" | | `rerun_subs` -> 1.9 (`shell.py:282-285`) | |
| 4 | File ▸ Open session photometry… | `QAction` | tooltip "Open the saved differential-photometry measurements of a session" | Ctrl+Shift+O | selects Review, then opens a **CSV file** picker (`shell.py:197-201, 291-293` -> `analyze_page.py:601-603, 732-763`) | |
| 5 | View ▸ Analyze/Review | `QAction` | rail label | F4 | `shell.py:230-234` | |
| 6 | View ▸ Reset Window Layout | `QAction` | status "Window layout will reset on next launch." (4 s) | | clears `ui.review.layout` among others (`shell.py:452-457`) | `ui.review.layout` |
| 7 | Capture dock "Differential photometry" | `QDockWidget` holding a `LightCurvePanel` (1.2) | panel chip "Differential photometry" | | fed by `imaging_page.py:2391-2403` **without `relative_flux`**, replayed by `_render_curves` (`2376-2379`); tabified with the log (`imaging_page.py:473-474`) | Capture layout |

### 1.9 Batch re-run flow (`imaging_page.py:2248-2367`, `photometry_batch_worker.py:71`, dialogs, modal)

| # | Control | Qt type | Label (exact) | Default | Enabled | Action |
|---|---|---|---|---|---|---|
| 1 | Folder picker | `QFileDialog.getExistingDirectory` | "Folder of saved subs" | last sequence dir or sessions path | after the 3 pre-checks | `*.fits` sorted by mtime, else recursive (`2283-2292`) |
| 2 | Progress | `QProgressDialog` | title "Batch photometry", text "Re-running photometry…", button "Cancel" | 0..N frames | while running | Cancel -> `worker.cancel` (stops at the next frame boundary, `photometry_batch_worker.py:92-94`) |

- Pre-checks (`QMessageBox.information`): "Solve first" / "Plate-solve the live frame before a batch re-run."; "No targets" / "Assign at least one target star first."; "No comparison stars" / "The target set has no comparison stars, so differential\nphotometry cannot produce magnitudes.\n\nSolve the field and wait for the catalog (comps auto-select\nonce it arrives), or click a comparison marker on the image\nand assign it the Comp role."; "No frames" / "No FITS files in {folder}". One batch at a time (`2255-2256`).
- Result: `QMessageBox.warning` "Batch failed" + error; log WARN "Batch photometry: no points measured — see the per-frame notes in targets/*_diagnostics.jsonl."; OK "Batch photometry: {n} frame(s), {k} target(s)."; INFO "Apertures tracked the field: {rot:+.2f}° rotation, {shift:.1f} px drift vs the reference solve." Then `engine.adopt_curves` (merges into the live store, `acquisition_engine.py:258-267`) and W1 opens.
- Physics: same `measure_frame`; series FWHM from the first frame; apertures follow field rotation/drift with `ApertureTracker` when `photometry.track_apertures` (`tracking.py:235-366`); egain from the config table or the sensor model (`imaging_page.py:2320-2335`).

### 1.10 Review page: `AnalyzeScreen` (`analyze_page.py:59`, page in the main window, rail F4)

- Purpose: open a finished session (folder with `session.json`), see curves, comparison diagnostics, frame quality, frames, metadata and the AAVSO stamp.

| # | Control | Qt type | Label / tooltip (exact) | Default | Enabled / visible | Shortcut | Action: handler -> effect | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Page heading | `HeadingLabel` | "Review" | | always | | `analyze_page.py:77` | |
| 2 | Session title | `MetricLabel` | "No session selected" / "{object} · {folder name}" | | always | | `analyze_page.py:138, 617` | |
| 3 | Open session… (card) | `PrimaryButton` | tooltip "Open the folder containing session.json" | | always | | `_open_session` (`analyze_page.py:605-647`): folder dialog "Open Argos session folder" at `sessions_path` -> `load_session` (`review.py:102-175`) + `load_session_curves` (`review.py:178-212`) -> fills every dock, applies the default layout | |
| 4 | Session summary | `MutedLabel`, hidden until a session opens | "Started {started_utc or 'unknown'} · {n} frames ({counts by type}) · Filters: {name: count, … or '—'} · {software}" | | after open | | `analyze_page.py:618-624` | |
| 5 | Session warnings | `MutedLabel` (WARNING colour) | `readiness_issues()` joined by " · ", or "Session structure looks complete." | | after open | | `analyze_page.py:641-645`; card capped at 112 px (`154`) | |
| 6 | Open session… (toolbar) | toolbar `QAction` | "Open session…" | | always | | duplicate of #3 (`analyze_page.py:257-258`) | |
| 7 | Open curve CSV… | toolbar `QAction` | "Open curve CSV…" | | always | | `_open_lightcurve` (`analyze_page.py:732-763`): dialog "Open session light curve", filter "CSV (*.csv);;All files (*)" -> `read_curves_csv` -> **new W1 instance** (not wired), `set_targets` from a `targets.json` beside the CSV or its parent; no rows -> logger warning only | |
| 8 | Open FITS… | toolbar `QAction` | "Open FITS…" | | always | | `_open_frame` (`analyze_page.py:765-780`): dialog "Open FITS frame", "FITS (*.fits *.fit *.fts);;All files (*)" -> new `AnalysisWindow` (frame-inspector spec) | |
| 9 | + Comparison plot below | toolbar `QAction` | tooltip "Add an independently selectable comparison-star plot below the last comparison plot" | | always | | `_add_comparison_plot` (`analyze_page.py:448-488`): new dock "Comparison star {n}" preselecting the first comparison not yet shown | |
| 10 | Source curve | checkable toggle (dock `toggleViewAction`) | text follows the dock title after a session opens ("Target — {name}") *(observed)*; tooltip "Show or hide Source curve. Drag its title bar to arrange it; double-click to detach it." | on | always | | show/hide dock (`analyze_page.py:269-277`) | via layout |
| 11 | FWHM | toggle | tooltip "Show or hide FWHM. …" | on | always | | show/hide | via layout |
| 12 | Comparison stars | toggle | tooltip "Show or hide Comparison stars. …" | on | always | | show/hide first comparison dock | via layout |
| 13 | Comparison quality | toggle | tooltip "Show or hide Comparison quality. …" | on | always | | show/hide | via layout |
| 14 | Frames | toggle | tooltip "Show or hide Frames. …" | off | always | | show/hide | via layout |
| 15 | Panels ▾ ▸ Metadata | menu toggle | tooltip "Show or hide Metadata. …" | off | always | | show/hide (`analyze_page.py:278-285`) | via layout |
| 16 | Panels ▾ ▸ AAVSO export | menu toggle | tooltip "Show or hide AAVSO export. …" | off | always | | show/hide | via layout |
| 17 | Arrange ▾ ▸ Tile plots — 2 columns | menu item | tooltip on the button "Float, re-dock or reset the Review workspace" | | always | | `_apply_default_layout` (`analyze_page.py:332-407, 427-430`) | |
| 18 | Arrange ▾ ▸ Restore default layout | menu item | | | always | | `reset_layout` (`analyze_page.py:423-425`): clears the saved state, re-tiles | `ui.review.layout` = null |
| 19 | Arrange ▾ ▸ Float / Dock {panel} | menu items, one per panel + extra target docks (extra comparison docks are missing) | "Float Source curve", "Dock FWHM", … | | always | | `_toggle_dock_floating` (`analyze_page.py:434-446, 587-591`) | via layout |
| 20 | Tile plots — 2 columns | toolbar `QAction` | tooltip "Arrange active source, comparison and FWHM plots in a two-column grid" | | always | | `_apply_default_layout` (duplicate of #17) | |
| 21 | Reset layout | toolbar `QAction` | "Reset layout" | | always | | `reset_layout` (duplicate of #18) | `ui.review.layout` |
| 22 | Dock title bars | `QDockWidget` title | dock titles: "Source light curve", "Frame quality — FWHM", "Comparison stars", "Comparison quality", "Frames", "Session metadata", "AAVSO export"; renamed "Target — {name}", "Target light curve", "Target {n}", "Comparison — {name}", "Comparison star", "Comparison star {n}" | | | drag = move / tabify; double-click = float; float and close buttons | `make_dock` (`dock_host.py:48-74`) | via layout |
| 23 | Point info | `MutedLabel` under the source plot | "Hover a point to inspect it; click to select it." then "Hover a point to inspect it; click to select its source frame."; hover text "{name} · JD {jd:.6f} · preview value {mag:.4f} ± {error:.4f}" (never shown, 1.2 #9); click text "{name} · {filename} · {UTC iso or 'unknown UTC'} · FWHM {x.xx} · HFD {x.xx}" or "{name} · no logged light frame matches JD {jd:.6f}" | | | mouse click on any target or comparison point | `_on_curve_point_clicked` (`analyze_page.py:688-701`) -> `review.nearest_light_frame(jd)` (`review.py:88-99`, nearest exposure-start timestamp among light frames) | |
| 24 | Open source frame | `SecondaryButton` | "Open source frame" | disabled | after a click that matched a frame whose FITS exists | | `_open_review_frame` (`analyze_page.py:703-731`) -> one reused `AnalysisWindow`; "Frame unavailable" / "Could not find {filename}." | |
| 25 | Frames table | `QTableWidget` (editable cells, no edit lock) | "UTC", "Type", "Filter", "Exp (s)", "Gain", "FWHM", "HFD", "Temp (°C)", "File"; FWHM/HFD/Temp 2 dp or "—" | | dock visible | | `_populate_frames` (`analyze_page.py:649-666`) | |
| 26 | Frames row double-click | | | | | double-click | `_open_frame_from_table` (`analyze_page.py:707-710`) -> as #24 (also starts a cell edit) | |
| 27 | Metadata table | `QTableWidget` (editable) | "Field", "Value"; rows Session folder, Object, Started UTC, Software, Observer, Frame count, then sorted `observation.json` keys | | dock visible | | `_populate_metadata` (`analyze_page.py:668-681`) | |
| 28 | AAVSO export readouts | form in a card | "Observer code" -> code (accent) or "unset — add it in Settings" (warning colour); "Band / filter" -> `photometry.default_band` | | dock visible | | `_refresh_export_info` on show (`analyze_page.py:306-326, 593-595`); **no export button** | reads `observer.obscode`, `photometry.default_band` |
| 29 | Workspace scroll | `QScrollArea` (vertical only) | | min height `max(660, 280 × rows)` | always | wheel | `analyze_page.py:99-108, 567-585` | |

- Displayed data: see 1.11-1.14. Default layout (`analyze_page.py:332-407`): source plots, comparison plots and FWHM tiled in 2 columns, 280 px rows; Frames bottom; Metadata / AAVSO export / Comparison quality tabified right, Comparison quality raised; one target dock per target and one comparison dock per comparison (`_sync_target_plots` `507-528`, `_sync_comparison_plots` `530-557`).
- Implicit: layout saved to config on application close (`shell.py:450`, `analyze_page.py:418-421`) and restored at start (`409-416`, warning "Review layout restore failed: %s" in the log only); observer code re-read on every show. Selecting a quality-table row re-targets the **first** comparison panel to that star (`analyze_page.py:559-565`).
- Messages: `QMessageBox.warning` "Could not open session" + "No session.json in {root}" / "Could not read session.json: {exc}" / "session.json has no frame list" (`review.py:111-118`); readiness issues: "No light frames were recorded.", "No FITS frames found in this session folder.", "Could not read observation.json.", "Ignored an invalid photometry_quality.json.", "Could not read photometry_quality.json.", "Ignored an invalid frame row in session.json.", "Ignored a malformed frame row in session.json.", "Missing FITS frame: {filename}" (one per frame), "Could not read preview curve: {file}" (`review.py:76-82, 127-175, 210-211`).

### 1.11 `TargetCurvePanel` (`target_curve_panel.py:14`, content of P1.d1 / P1.d1+)

| # | Control | Qt type | Label / tooltip (exact) | Options / default | Visible | Shortcut | Action | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Target selector | label "Target" + `QComboBox` | tooltip "Choose the target shown in this source light curve" | one entry per curve with role `target` (label = name, AUID or key), then "All targets" (last); preferred key from the dock, else first | always | | `_refresh_plot` (`target_curve_panel.py:77-84`) | no |
| 2 | Plot | `LightCurvePanel(view="target")` | header "Source light curve"; 1.2 #2 | | | | `target_curve_panel.py:43-46` | |
| 3 | Show uncertainties | `QCheckBox` (per plot) | as 1.2 #5 | checked | | | as 1.2 #5 | no |
| 4 | Relative flux | `QCheckBox` (per plot) | as 1.2 #6 | unchecked | | | as 1.2 #6 | no |

### 1.12 `ComparisonCurvePanel` (`comparison_curve_panel.py:14`, content of P1.d3 / P1.d3+)

| # | Control | Qt type | Label / tooltip (exact) | Options / default | Visible | Shortcut | Action | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Comparison selector | label "Comparison star" + `QComboBox` | tooltip "Choose the comparison star shown in this diagnostic" | one entry per curve with role `comparison`, then "All comparison stars" | always | | `_refresh_plot` (`comparison_curve_panel.py:78-85`) | no |
| 2 | Plot | `LightCurvePanel(view="comparison")` | header "Comparison-star diagnostics"; 1.2 #3 | | | | | |
| 3 | Show uncertainties | `QCheckBox` | as 1.2 #5 | checked | | | | no |
| 4 | Relative flux | `QCheckBox` | as 1.2 #6 | unchecked | | | | no |

### 1.13 `ComparisonQualityTable` (`comparison_table.py:208`, content of P1.d4)

| # | Control | Qt type | Label (exact) | Default | Visible | Shortcut | Action | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Hint | `QLabel` | "No comparison-quality report in this session." / "Leave-one-out live-preview diagnostic · minimum {min_points} valid points. Select a row to show its curve." | | | | `comparison_table.py:236-246` | |
| 2 | Quality table | `QTableWidget` read-only, single row | "Name", "Samples", "Scatter (mag)", "Formal error (mag)", "Live status" | rows from `photometry_quality.json` | | | row selection -> `star_selected(auid or name)` -> `analyze_page.py:559-565` | |

### 1.14 `SessionQualityPlot` (`session_review.py:21`, content of P1.d2)

| # | Control | Qt type | Label | Options / default | Visible | Shortcut | Action | Persisted |
|---|---|---|---|---|---|---|---|---|
| 1 | Metric | label "Quality trend" + `QComboBox` | | "FWHM (green px)" (default), "HFD (green px)", "Sensor temperature (°C)", "Sky background (ADU)", "Star count", "Eccentricity" (`session_review.py:11-18`) | always | | `_refresh` (`session_review.py:54-65`) | no |
| 2 | Plot | `pg.PlotWidget` | x "Elapsed time (h)", y = metric label; line + dots | | always | mouse | `session_review.py:40-47` | |
| 3 | Context menu | pyqtgraph ViewBox menu (left enabled) | View All, X axis, Y axis, Mouse Mode, Plot Options, Export… | | always | right-click | built-in | |

- Data: x = (frame timestamp − first light-frame timestamp) / 3600; frame timestamp = exposure **start** UTC (`sequence_worker.py:430`); y from `session.json` frame rows, CCD temperature from each FITS header `CCD-TEMP` (`review.py:270-279`); light frames with a timestamp only (`review.py:68-74`).

### 1.15 Problems found

| # | Problem | Where |
|---|---|---|
| P1 | Live dock feed omits `relative_flux`; when a point has only a ratio (`mag = NaN`, e.g. uncalibrated comparisons) `np.isfinite(None)` raises `TypeError` (verified), the slot aborts and the Photometry window misses that point too; the dock's "Relative flux" view stays empty for live points | `imaging_page.py:2396-2406`, `lightcurve_panel.py:127` |
| P2 | Point hover never fires (scatter `hoverable` False, verified) so the Review hover readout is dead | `lightcurve_panel.py:140-149, 176-180`; `analyze_page.py:683-686` |
| P3 | Once a curve has 10 points, every new point changes the systematic floor (new point `sigma_syst` None ≠ float) and triggers `curves_changed`: full re-render of dock and window per star per frame, and `autoRange()` each time, so the observer's zoom is lost on every frame; cost grows as N² over the night | `acquisition_engine.py:1456-1461, 1494-1504`; `lightcurve_panel.py:277` |
| P4 | Review classifies `check_*.csv` as targets (only `comparison_` is recognised): check stars appear as extra "Target" plots named after the file | `review.py:218` |
| P5 | "Open curve CSV…" on a per-star session CSV loses role and name: an AAVSO export then writes a comparison (or check) as a science target with `NAME` = upper-cased file stem, e.g. `COMPARISON_SS_CYG_000-AAA-111` (verified) | `lightcurve.py:164-168`; `analyze_page.py:741-753`; `lightcurve.py:241-254` |
| P6 | AAVSO export includes saturated and suspect target points without any note | `lightcurve.py:245-254` |
| P7 | Exports: silent no-op when nothing to export, no success message, `OSError` not caught, default folder is home instead of the session, unset observer code exported as `XXX` silently | `photometry_window.py:302-327`; `imaging_page.py:2096, 2127` |
| P8 | Stale "canonical 9-column schema" comments: the files have 15 (per star) and 19 (export) columns | `photometry_window.py:310`; `photometry_batch_worker.py:13, 50, 393` |
| P9 | W1 opened from Review is unwired: Remove selected, Refresh catalogue, Recommend from pilot, auto count, Set as target and the aperture spins do nothing; the aperture tab shows the spin minima (1.00 × FWHM, 2.0 px, 3.0, 5.0, 3.0 SNR, 0.2 mag, 5 ′) *(observed)* | `analyze_page.py:745-763` |
| P10 | Window title / export metadata stamped only at creation: the title keeps the first object name | `imaging_page.py:2092-2099` |
| P11 | The auto-count spin replaces the whole VSP ensemble (`reselect`) on every arrow step, with a pilot re-measure on the UI thread; `propose_comparison_stars`, documented for this use, is unused; duplicate control in Settings with another range (1-20 vs 1-12) | `comparison_table.py:81-88`; `imaging_page.py:2167-2183`; `acquisition_engine.py:1033-1051`; `astrometry_settings.py:262-267` |
| P12 | Destructive ensemble edits (Remove selected, Recommend from pilot) have no confirmation or undo, and during a run they change the zero point of all following frames and append to the selection history | `comparison_table.py:110-124`; `acquisition_engine.py:995-1008` |
| P13 | Aperture spins persist and log on every step (log spam); geometry can be changed mid-run, making one light curve inhomogeneous, without warning | `photometry_window.py:70-139`; `imaging_page.py:2152-2165` |
| P14 | "Waiting for 10 points" is hard-coded while the threshold is configurable | `comparison_table.py:42`; `config.py:155` |
| P15 | Report fields `selection_status` and `scientific_note` are never shown | `quality.py:76-91` |
| P16 | The quality report is computed only during a sequence run: in live preview the status column stays "Waiting for data" | `acquisition_engine.py:1393-1394` |
| P17 | `suspect`, `comps_used`, `relative_comps_used`, `sigma_syst`, `formal_mag_err`, `airmass`, `bjd_tdb` are recorded but never displayed | `lightcurve.py:38-62` vs `lightcurve_panel.py:115-209` |
| P18 | Check stars share the target plot and axis, compressing the target; "All targets" / "All comparison stars" overlays break BRAND 10 (max 3 series) | `lightcurve_panel.py:133-138`; `target_curve_panel.py:65-66`; `comparison_curve_panel.py:66-67` |
| P19 | Series colours cycle by insertion order and use semantic WARNING / DANGER; DANGER is also the saturation mark | `lightcurve_panel.py:20-22, 131-132, 152-160` |
| P20 | Time axes disagree: curves in full JD with SI-scaled ticks *(observed)*, Review quality in elapsed hours from the first light frame, live metrics in elapsed seconds since the first sample of the app session, never reset; no plot is time-aligned with the curves | `lightcurve_panel.py:58-66`; `session_review.py:42, 62`; `imaging_page.py:2414-2417` |
| P21 | Live metrics only sampled while W1 is visible (gaps); their airmass uses the mount altitude, the curve points use the target's | `imaging_page.py:2419-2433`; `acquisition_engine.py:1426-1429` |
| P22 | File ▸ "Open session photometry…" opens a CSV picker, not a session folder; Review has two different "open" semantics | `shell.py:197-201`; `analyze_page.py:601-603` |
| P23 | Review shows the AAVSO stamp but has no export action; exporting a reviewed session requires P5's lossy CSV path | `analyze_page.py:118-131, 221` |
| P24 | Duplicated controls: Open session (card + toolbar), Tile (toolbar + menu), Reset/Restore layout, Show uncertainties / Relative flux on every plot with independent states | `analyze_page.py:140, 257, 295, 298, 429, 431`; `lightcurve_panel.py:85-95` |
| P25 | Arrange menu omits extra comparison docks | `analyze_page.py:441-446` |
| P26 | Quality-row selection re-targets the first comparison panel instead of revealing the one already showing the star; no match for comparisons without AUID (quality key = name, curve key = `comparison:pos:…`) | `analyze_page.py:559-565`; `review.py:239`; `comparison_table.py:252` |
| P27 | Frames and Metadata cells are editable; double-click both opens the frame and starts an edit | `analyze_page.py:186-196` |
| P28 | Readiness warnings are one line per missing FITS joined into a paragraph that overflows the 112 px card *(observed)* | `analyze_page.py:154, 641-645`; `review.py:172-173` |
| P29 | "Open curve CSV…" with no valid rows only writes a logger warning; no UI feedback | `analyze_page.py:741-744` |
| P30 | Panel toggles take the dock titles ("Target — SS Cyg") after a session opens *(observed)* | `analyze_page.py:270-277, 522, 551` |
| P31 | Comparison table quality headers truncated at default widths *(observed)* | `comparison_table.py:93-103` |
| P32 | Review quality plot keeps the pyqtgraph context menu, the other plots disable it | `session_review.py:40` vs `lightcurve_panel.py:102` |
| P33 | Batch re-run CSVs go to `sessions_path/../targets` without role prefix, so Review cannot reload them as a session and a CSV reload loses roles; a frame without DATE-OBS is plotted at JD 0 | `imaging_page.py:2299`; `photometry_batch_worker.py:276, 392-402` |
| P34 | Relative-flux medians include saturated points; a non-positive median leaves stale data on screen | `lightcurve_panel.py:224-235` |
| P35 | "Remove selected" always enabled (no-op without a row); "Refresh catalogue" silently does nothing when unsolved | `comparison_table.py:110`; `target_table.py:47`; `acquisition_engine.py:838-840` |
| P36 | The effective-geometry label silently uses the 3.0 px default FWHM before a FWHM is measured | `photometry_window.py:189-197`; `acquisition_engine.py:1229-1233` |
| P37 | `photometry.default_band` (the AAVSO `FILT` and the catalogue band) has no UI anywhere; it is only displayed | `config.py:143`; `analyze_page.py:309-310` |

## 2. Web redesign

### 2.1 Placement in the new information architecture

Principle: one **Review** screen (F4) shows light curves for two sources, chosen by a segmented
control in its toolbar:

- **Live run**: the engine's current store, updating as points arrive. Replaces the Qt "Field
  photometry" window (its Light curve, Metrics and Comparison stars tabs) and is editable
  (ensemble actions). For a second monitor the whole Review screen opens in its own window
  (`panel-float`, Tauri multi-window or a browser tab), which replaces the floating window and the
  floating docks.
- **Session**: a finished session folder (or a CSV), read-only, with frames, metadata and export.
  Replaces `AnalyzeScreen`.

| Qt element | Web placement | Justification |
|---|---|---|
| W1 Field photometry window | **Dissolved**: Review ▸ Live run (curves, metrics, ensemble, exports); Observe ▸ Photometry rail card (target pick, Targets list); Settings ▸ Photometry (aperture and reference criteria) | The Qt window mixed acquisition set-up, science display and settings in six tabs. Each now lives where its task lives; the curves get a full screen instead of a tab |
| W1 #1 banner | Review toolbar chip "Preview" + popover with the exact text | Always visible scientific caveat in one chip instead of a two-line band (BRAND 11.1 "no dead bands") |
| W1 #3, #4 exports | Review toolbar, both sources; AAVSO goes through a modal export dialog | Exports belong to review; the dialog fixes P5-P7, P23 |
| 1.2 `LightCurvePanel` | One `LightCurvePlot` component: Review plot wall (faceted, one plot per star) and the Observe bottom drawer "Light curve" (compact: targets + check) | One plotting contract everywhere; BRAND 10 max 3 series per plot |
| 1.3 Metrics + 1.14 quality plot | One "Quality trend" facet at the bottom of the Review plot wall, on the **same time axis** as the curves | Fixes P20-P21; a seeing or sky spike lines up with the curve feature it explains |
| 1.4 Targets, 1.5 Variable stars | Observe ▸ right rail "Photometry" card (target list + variable picker), next to the image they act on. Cross-reference: Observe spec | Target picking needs the solved image, the markers and the star card; it is not review |
| 1.6 ensemble table + 1.13 quality table | Review right rail card "Ensemble" (compact columns, verdict) + Review bottom drawer tab "Ensemble" (all columns). Editing actions only with source Live run | One table for live and archived ensembles; edits only where they still change the measurement |
| 1.7 aperture and references | Settings ▸ Photometry (form, all 7 fields) + read-only effective geometry in Observe ▸ Photometry card with a link | These are persistent measurement parameters, not review |
| 1.8 #1-#2 menu entries | Observe Photometry card / Review (F4) | Rail sections replace window menus |
| 1.8 #4 Open session photometry… | Review toolbar `open-session` (Ctrl+Shift+O), which opens a **session** | One meaning for "open session" (P22); CSVs get their own `open-file` |
| 1.8 #7 Capture dock | Observe bottom drawer "Light curve" tab (next to Log) | Same live curve while framing; Observe spec owns the drawer |
| 1.9 batch re-run | Review toolbar (source Live run) `rerun-photometry` + modal dialog + inline progress | It produces curves to review; it needs the live solve and target set |
| 1.10 Review page | Review ▸ Session source | |
| 1.10 #2-#5 session card | Review toolbar context group (title, chips, readiness badge with popover) | One 40 px row instead of a 112 px card |
| 1.10 #10-#22 dock machinery | Review "Plots" popover (`panels`) + layout controls; fixed grid, no floating docks | Web panels do not float; the second-monitor need is met by opening Review in its own window |
| 1.10 #23-#24 point info | Review rail card "Point" | Detail of the selected point next to the curve, not under one plot only |
| 1.10 #25-#27 Frames, Metadata | Review bottom drawer tabs "Frames", "Metadata" | Tables are secondary; they keep their room out of the first scan |
| 1.10 #28 AAVSO readouts | AAVSO export dialog + rail card "AAVSO export" summary | The stamp is shown where the export happens |
| 1.11, 1.12 selectors | Removed: one facet per star | See 2.2 |

### 2.2 Control mapping

Shortcuts marked (p) are proposed; single keys only fire outside text fields and never move hardware (BRAND 7).

| Qt ref | Web control | Decision | Icon id | Display | Shortcut |
|---|---|---|---|---|---|
| 1.1 #1 | "Preview" chip, popover with the full banner text | move (toolbar) | none (chip + text) | label | |
| 1.1 #2 | tabs | drop: replaced by sections (2.1) | | | |
| 1.1 #3 | Export measurements… | keep, Review toolbar; disabled with reason when no points; success / error toast | `export` | icon+label | |
| 1.1 #4 | Export AAVSO… -> AAVSO export dialog (2.3 F) | keep + dialog (shows obscode, band, chart, check star, row count, excluded points) | `export-aavso` | icon+label | |
| 1.1 #5 | Review toolbar title "{object} · live run" | keep, always current (fixes P10) | | label | |
| 1.1 #6 | window close | drop: no separate window; Review opened in its own window closes like any window | | | |
| 1.2 #1 | facet header: role glyph + name + AUID + last value | keep, per facet | `target-star` / `comparison-star` / `check-star` (inline 16 px) | icon+label | |
| 1.2 #2 | Target facet(s), one per target | keep; check stars moved out (P18) | | | |
| 1.2 #3 | Comparison facets, one per comparison (small multiples, 2 or 3 columns) | keep, faceted | | | |
| 1.2 #4 | splitter | merge into the plot-wall grid (row heights resizable by a drag handle, remembered per viewer) | | | |
| 1.2 #5 | Show uncertainties: one toggle for the whole screen | merge (one state for every facet, P24) | `error-bars` | icon (aria-pressed) | U (p) |
| 1.2 #6 | Relative flux: one toggle for the whole screen | merge | `relative-flux` | icon (aria-pressed) | R (p) |
| 1.2 #7 | legend click | drop: one series per facet, nothing to hide; facets are shown/hidden in the Plots popover | | | |
| 1.2 #8 | point click -> select point (all facets show a cursor line at that time; Point card fills) | keep, extended to every facet | | | ← / → (p) step through points of the selected series |
| 1.2 #9 | hover tooltip in mono (time in JD, UTC, BJD; value ± err; formal, σ_syst; comps used; airmass; flags) | keep, fixed (P2, P17) | | | |
| 1.2 #10 | wheel = zoom time (all facets linked), drag = pan, Shift+wheel = zoom y of one facet, double-click = fit that facet | keep | | | |
| 1.2 #11 | Fit plots | keep; new points never reset a manual zoom (P3) | `zoom-fit` | icon | F (p) |
| 1.3 #1 | Quality trend metric menu (custom menu, not native select): Airmass, FWHM (green px), HFD (green px), Sky (ADU), Star count, Sensor temperature (°C), Eccentricity | merge with 1.14 #1 (union of both lists; unavailable metrics disabled with reason) | `session-metrics` | icon+label (menu button shows the metric name) | |
| 1.3 #2 | Quality trend facet on the shared time axis | merge with 1.14 #2 | | | |
| 1.4 #1-#3 | Observe ▸ Photometry card: target list, remove, copy | move (Observe spec) | `target-star`, `remove`, `copy` | icon | |
| 1.5 #1-#6 | Observe ▸ Photometry card: variable picker (search, mag limit, sortable list, set as target) | move (Observe spec) | `search`, `variable-star`, `target-star` | icon / icon+label for Set as target | |
| 1.6 #1 | Ensemble card help: info popover on the card title with the exact hint text | keep | none | | |
| 1.6 #2 | "Proposed comparisons" count: Settings ▸ Photometry field (1-12, one range) + field inside the Recommend popover | merge with `astrometry_settings.py:262-267` (one control, one range); changing it no longer re-selects by itself; "Complete ensemble" button in the popover calls `propose` (P11) | | label | |
| 1.6 #3 | Ensemble table: rail (Name, status badge, Scatter, N) + drawer (all 10 columns); row click highlights the star on the Observe image and scrolls to its facet | keep; Name and AUID merged when equal (AUID column hidden by default in the drawer, toggle in column menu) | `comparison-star` (row glyph) | | Ctrl+C copies (p) |
| 1.6 #4 | count line under the table, exact texts | keep | | label | |
| 1.6 #5 | Remove (row action on hover + selected row) -> confirmation while a sequence runs, undo toast otherwise | keep, guarded (P12, P35: disabled without a selection) | `remove` | icon (row), tooltip "Remove from the ensemble" | Delete (p) |
| 1.6 #6 | Refresh catalogue | keep; disabled with reason while the field is unsolved; busy spinner while the catalogue is fetched | `refresh` | icon | |
| 1.6 #7 | Recommend from pilot… -> popover (count, criteria summary, "Replace VSP picks" / "Complete ensemble") with confirmation text | keep, guarded | `recommend-comparisons` | icon+label | |
| 1.6 #8 | Copy TSV | keep (card header) | `copy` | icon | |
| 1.7 #1 | Settings ▸ Photometry help text (exact) | move | | label | |
| 1.7 #2-#8 | Settings ▸ Photometry number fields with units (same ranges, steps, defaults); commit on Enter / blur, not per step; geometry fields read-only while a sequence runs (open question 2) | move (P13) | | label | |
| 1.7 #9 | Effective geometry readout (mono): "Aperture 7.5 px · annulus 8.5–12.0 px · FWHM 3.0 px (default)" in Settings and in the Observe Photometry card | keep + says whether the FWHM is measured or the default (P36) | `photometry` | label | |
| 1.7 #10 | note text in Settings | keep | | label | |
| 1.8 #1 | Observe ▸ Photometry card | move (Observe spec) | `photometry` | icon | |
| 1.8 #2 | Review rail entry, source Live run | move | `nav-analyze` | icon+label | F4 |
| 1.8 #3 | Re-run subs… | move to Review toolbar (Live run) | `rerun-photometry` | icon+label | |
| 1.8 #4 | Open session… | keep, now opens a session (P22) | `open-session` | icon | Ctrl+Shift+O (qt) |
| 1.8 #5 | rail entry | keep | `nav-analyze` | icon+label | F4 (qt) |
| 1.8 #6 | Reset layout | move into the Plots popover (Review layout only) | `layout-reset` | icon+label | |
| 1.8 #7 | Observe bottom drawer "Light curve" tab | move (Observe spec), fixed feed (P1) | `light-curve` | icon+label | |
| 1.9 #1 | Re-run dialog: folder picker (server file browser or Tauri dialog) with the 3 pre-checks shown as blocking reasons before the picker | keep | `open-session` | label buttons | |
| 1.9 #2 | Inline progress in the Review toolbar "Re-running photometry… 12 / 240" + Cancel | keep, non-modal (other screens stay usable) | `stop` | icon+label "Cancel re-run" | |
| 1.10 #1 | page heading | drop: the rail already names the section (BRAND 11.1) | | | |
| 1.10 #2 | toolbar title "{object} · {folder}" (mono folder) | keep | | label | |
| 1.10 #3 | Open session… (card) | merge with #6 into one toolbar button | `open-session` | icon | Ctrl+Shift+O |
| 1.10 #4 | summary chips: started UTC, frames by type, filters, software | keep, chips + full text in title tooltip | | label | |
| 1.10 #5 | readiness badge "{n} warnings" (StatusBadge tone busy) -> popover list grouped ("Missing FITS: 40 frames" with the list folded) | keep, condensed (P28) | | label | |
| 1.10 #6 | toolbar Open session… | merged (#3) | `open-session` | icon | |
| 1.10 #7 | Open curve CSV… -> loads into Review (source "CSV file"), not a new window; roles restored from `targets.json` and file prefixes | keep, fixed (P5, P29) | `open-file` | icon+label "Open CSV…" | |
| 1.10 #8 | Open FITS… -> frame inspector (other spec) | keep | `open-image` | icon | |
| 1.10 #9 | + Comparison plot below | drop: every comparison has its facet by default, and the overlay views it allowed break BRAND 10 | | | |
| 1.10 #10-#16 | Plots popover: checkboxes per facet group (Targets, Check stars, Comparisons, Quality trend) and per drawer tab | merge into one popover (P24, P30) | `panels` | icon | |
| 1.10 #17, #20 | Comparison columns 1 / 2 / 3 (segmented in the Plots popover) | merge (duplicates) | `layout-tile` | icon | |
| 1.10 #18, #21 | Reset layout (in the Plots popover) | merge (duplicates) | `layout-reset` | icon+label | |
| 1.10 #19 | Float / Dock panel | drop: no floating panels on the web; "Open Review in a new window" covers the second monitor | `panel-float` (for the new-window action) | icon | |
| 1.10 #22 | dock title bars | drop: facet headers (1.2 #1) and the Plots popover replace move / close; per-facet hide via the header's `close` icon | `close` | icon | |
| 1.10 #23 | Point card (rail) | keep, extended (2.3 A) | | | |
| 1.10 #24 | Open source frame | keep, in the Point card | `open-image` | icon+label | Enter (p) when a point is selected |
| 1.10 #25 | Frames drawer table, read-only, sortable; selecting a row moves the cursor line to its time | keep, read-only (P27) | `frames` | tab icon+label | |
| 1.10 #26 | row double-click -> frame inspector | keep | | | Enter (p) |
| 1.10 #27 | Metadata drawer table, read-only | keep | `metadata` | tab icon+label | |
| 1.10 #28 | AAVSO export rail card + dialog (obscode with "unset — add it in Settings" link, band, chart) | keep | `export-aavso` | | |
| 1.10 #29 | plot wall scroll (target facets sticky) | keep | | | |
| 1.11 #1 | target selector | drop: one facet per target by default (as Qt already does on open); "All targets" overlay removed (BRAND 10, different magnitudes share no useful axis) | | | |
| 1.11 #2 | target facet | keep | | | |
| 1.11 #3, #4 | per-plot checkboxes | merge into 1.2 #5 / #6 | | | |
| 1.12 #1 | comparison selector | drop: one facet per comparison; "All comparison stars" overlay removed (BRAND 10) | | | |
| 1.12 #2 | comparison facet | keep | | | |
| 1.12 #3, #4 | per-plot checkboxes | merge into 1.2 #5 / #6 | | | |
| 1.13 #1 | Ensemble card help + verdict line | merge into 1.6 #1; the verdict now shows `selection_status` and `scientific_note` (P15) | `comparison-quality` | icon+label | |
| 1.13 #2 | Ensemble table, read-only for Session | merge with 1.6 #3; row click scrolls to the star's own facet (P26) | | | |
| 1.14 #1 | quality metric | merge with 1.3 #1 | `session-metrics` | | |
| 1.14 #2 | Quality trend facet | merge with 1.3 #2, x = shared time axis | | | |
| 1.14 #3 | context menu | drop: View All = Fit plots; axis/mouse options unneeded; plot export can be a later feature | | | |
| new | Time axis segmented "JD" / "UTC" / "BJD" (BJD disabled with reason when any point lacks `bjd_tdb`) | new, replaces the unreadable SI-scaled JD ticks (P20) | | label | |
| new | Source segmented "Live run" / "Session" (Session shows the opened folder name) | new | | label | |
| new | Open Review in a new window | new (second monitor) | `panel-float` | icon | |
| new | Rail toggle | new, as on Observe | | | P |
| new | Bottom drawer toggle (Ensemble / Frames / Metadata / Log) | new | `frames` | icon | D (p) |

### 2.3 Wireframes

Reference 1440 x 900: nav rail 92 px, status bar 32 px, toolbar 40 px, right rail 420 px
(`--rail-min-w`, collapsible with P). Icons are written `[icon-id]`; `⟨a|b⟩` is a segmented control.
Plot markers: `●` target (circle), `■` comparison (square), `▲` check (triangle), `x` saturated,
`○` suspect (hollow); these stand for SVG markers, never text glyphs in the UI. A `●` before a
status word is the StatusBadge dot. `[x]` at the end of a facet header is the `close` icon (hide
that facet); `[x]` before a sentence in a dialog is a checked checkbox.

**A. Review, source Live run (sequence running, drawer closed)**

```
┌──────┬──────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ARGOS│ ⟨Live run|Session⟩ SS Cyg · live run · 212 frames · TG [Preview] [● 0 warnings] │[open-session][open-file]│
│      │ [open-image] │ [error-bars][relative-flux] ⟨JD|UTC|BJD⟩ [zoom-fit] [panels] [panel-float] │                │
│ rail │ [rerun-photometry Re-run subs…] [export Export measurements…] [export-aavso Export AAVSO…]              │
│      ├───────────────────────────────────────────────────────────────────┬──────────────────────────────────────┤
│      │ [target-star] SS Cyg  000-BCP-220       last 11.234 ± 0.012  [x]   │ ENSEMBLE [comparison-quality] (i) [refresh][copy] │
│      │ 11.0 ┤        ● ●●                                                 │ ● Live-preview consistent · 4 of 5   │
│      │      │   ●●●●     ●●●                                              │   stable (min 10 points)             │
│      │ 11.2 ┤ ●●             ●●●        ●●                                │ ─────────────────────────────────────│
│      │      │                   ●●●●●●●  ●●●●  │cursor                    │ ■ Name          N   Scatter Status   │
│      │ 11.4 ┤                                  │                          │ ■ 000-AAA-111  212  0.0101 ● Stable  │
│      │      └────┬────────┬────────┬────────┬──┴─────┬────────  JD−2461346 │ ■ 000-AAA-222  212  0.0110 ● Stable  │
│      │          0.30     0.32     0.34     0.36     0.38  (sticky facet)   │ ■ 000-AAA-444  212  0.0420 ● Noisy   │
│      │ [check-star] 000-AAA-333 (check)   σ 0.009   [x]                   │ ■ 000-AAA-555  212  0.0098 ● Stable  │
│      │      ▲ ▲▲ ▲ ▲▲ ▲ ▲ ▲▲ ▲ ▲▲ ▲ ▲ ▲▲ ▲  ▲ ▲▲ ▲ ▲▲ ▲ ▲ ▲▲ ▲             │ ■ 000-AAA-666  212  0.0102 ● Stable  │
│      │ ■ 000-AAA-111 Δmag  [x] │ ■ 000-AAA-222 Δmag [x] │ ■ 000-AAA-444 [x] │ 5 calibrated comparison star(s)      │
│      │  ■■ ■ ■■ ■ ■■ ■ ■■ ■    │  ■ ■■ ■ ■■ x ■■ ■ ■    │  ■  ■■   ■ ■■  ■ │ [recommend-comparisons Recommend…]   │
│      │ ■ 000-AAA-555 Δmag  [x] │ ■ 000-AAA-666 Δmag [x] │                   │ POINT                                │
│      │  ■■ ■ ■■ ■ ■■ ■ ■■ ■    │  ■ ■■ ■ ■■ ■ ■■ ■ ■    │                   │ ● SS Cyg  JD 2461346.38123           │
│      │ [session-metrics FWHM (green px) ▾]  quality trend, same x          │   UTC 2026-10-30 21:08:58 UTC        │
│      │   ──·──·──·──·──·─·──·──·──·──·──·──·──·──·──·──                   │   11.234 ± 0.012 (formal 0.010,      │
│      │                                                                    │   σ syst 0.006) · 5 comps · X 1.21   │
│      ├───────────────────────────────────────────────────────────────────┤   [open-image Open source frame]     │
│      │                                                                   │ AAVSO EXPORT  ABC · TG · chart X1    │
├──────┴───────────────────────────────────────────────────────────────────┴──────────────────────────────────────┤
│ status bar: connection · sequence 212 / 400 · ETA 1h 05m · theme · Log                                          │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Heights at 900 px with the drawer closed: toolbar 40 (one row in the real layout; wrapped here for
width), target facet 260 (sticky), check facet 110, two comparison rows 2 x 130, quality trend 110:
828 px, so up to 6 comparisons (3 columns) and the quality trend are visible without scrolling.
More comparisons scroll inside the plot wall; the target facet stays pinned.

**B. Review, source Session, drawer "Frames" open (240 px)**

```
┌──────┬──────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ rail │ ⟨Live run|Session⟩ SS Cyg · 2026-10-30_2100 · started 2026-10-30 21:00:00 UTC · 40 light · LP:40 ·      │
│      │ Argos 0.4.2 [Preview] [● 3 warnings ▾] │ [open-session][open-file][open-image] │ [error-bars]…[export…]  │
│      ├───────────────────────────────────────────────────────────────────┬──────────────────────────────────────┤
│      │ target facet (sticky) …                                           │ ENSEMBLE (read-only, from            │
│      │ check facet …                                                     │ photometry_quality.json)             │
│      │ comparison facets …                                               │ POINT                                │
│      │ quality trend …                                                   │ AAVSO EXPORT                         │
│      ├─[frames Frames]─[metadata Metadata]─[comparison-quality Ensemble]─[log Log]──────────────── [close] ───┤
│      │ UTC                 Type  Filter Exp (s) Gain  FWHM   HFD   Temp (°C)  File                            │
│      │ 2026-10-30 21:00:00 Light LP       20.0   80   2.71   3.40  −10.0      Light_0000.fits  ◀ selected      │
│      │ 2026-10-30 21:00:30 Light LP       20.0   80   2.84   3.52  −10.0      Light_0001.fits                  │
└──────┴──────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**C. Empty states (plot-wall centre, EmptySection style)**

```
  Live run, nothing measured                     Session, nothing opened
  [light-curve 48 px]                            [open-session 48 px]
  No live photometry yet                         No session open
  Pick a target in Observe ▸ Photometry, then    Open a session folder (session.json) or a
  solve a full-resolution frame.                 photometry CSV.
  [photometry Go to Observe]                     [open-session Open session…]  [open-file Open CSV…]
```

Sub-states of Live run (one line under the title): "No photometry target." · "Waiting for a solved
full-resolution frame." (`acquisition_engine.py:1336-1340`) · "No comparison stars — refresh the
catalogue after a successful solve." · "Measuring: {n} points, uncertainty floor after 10."

**D. Open session dialog (modal, 640 x 480)**

```
┌ Open session ───────────────────────────────────────────── [close] ┐
│ Sessions folder  /Users/…/Argos/sessions                [browse]   │
│ [search] filter by object or date                                  │
│ ─────────────────────────────────────────────────────────────────  │
│ Object        Started (UTC)          Frames  Photometry  Quality   │
│ SS Cyg        2026-10-30 21:00 UTC     240    yes         yes      │
│ V1405 Cas     2026-10-28 20:12 UTC      96    yes         no       │
│ M 42          2026-10-27 22:40 UTC      30    no          no       │
│ ─────────────────────────────────────────────────────────────────  │
│                                           [ Cancel ]  [ Open ]     │
└────────────────────────────────────────────────────────────────────┘
```

**E. Recommend popover (from the Ensemble card, 340 px)**

```
┌ Recommend comparison stars ───────────────────────┐
│ Proposed comparisons  [ 5 ]  calibrated stars     │
│ Pilot gate: SNR ≥ 10 · Δmag ≤ 1.5 · ≤ 25′         │
│ (edit in Settings ▸ Photometry)                   │
│ Replacing removes every VSP pick and keeps manual │
│ choices. During a run the zero point of all       │
│ following frames changes.                         │
│ [ Complete ensemble ]  [ Replace VSP picks ]      │
└───────────────────────────────────────────────────┘
```

**F. AAVSO export dialog (modal, 560 px)**

```
┌ Export AAVSO extended format ──────────────────────────── [close] ┐
│ Observer code   ABC                      (Settings ▸ Observer)    │
│ Band (FILT)     TG                       untransformed, ensemble  │
│ Chart (CHART)   X1                       from the 5 comparisons   │
│ Check star      000-AAA-333 (KNAME/KMAG)                          │
│ Rows            212 target points (SS Cyg)                        │
│ [x] Exclude saturated points (3)   [x] Exclude suspect points (1) │
│ Times are JD (UTC), exposure midpoint. Preview photometry:        │
│ publishable reduction remains in Siril.                           │
│                                      [ Cancel ]  [ Export… ]      │
└───────────────────────────────────────────────────────────────────┘
```

With an unset observer code the first row reads "unset — add it in Settings" with a link and
Export is disabled (open question 4 decides whether `XXX` stays allowed).

**G. Remove a comparison during a run (modal confirmation, text buttons)**

```
┌ Remove 000-AAA-444 from the ensemble? ─────────────────────────────┐
│ The differential zero point of every following frame changes and  │
│ the selection history records the edit. Points already measured   │
│ are kept.                                                          │
│                                       [ Cancel ]  [ Remove ]       │
└────────────────────────────────────────────────────────────────────┘
```

Outside a run: no dialog; toast "000-AAA-444 removed from the ensemble · Undo".

**H. Re-run subs dialog (modal) and progress (toolbar)**

```
┌ Re-run photometry over saved subs ─────────────────────── [close] ┐
│ Uses the current field solution and target set (1 target,         │
│ 5 comparisons, 1 check). Apertures follow field rotation.         │
│ Folder  /Users/…/sessions/2026-10-30_2100/lights     [browse]     │
│ 240 FITS files found                                              │
│                                     [ Cancel ]  [ Re-run ]        │
└───────────────────────────────────────────────────────────────────┘
toolbar while running:  Re-running photometry… 12 / 240  [stop Cancel re-run]
```

Blocked states replace the folder row with the Qt texts ("Plate-solve the live frame before a batch
re-run.", "Assign at least one target star first.", the "No comparison stars" paragraph).

**I. Settings ▸ Photometry (page section, `--page-max-w` 880 px)**

```
PHOTOMETRY
Live preview only: Argos measures circular apertures on the raw subs and estimates the local sky in a
surrounding annulus. The aperture follows the measured FWHM; final calibrated reduction remains in Siril.
 Aperture radius (adaptive)            [ 2.50 ] × FWHM
 Aperture radius floor                 [  4.0 ] green px
 Background annulus — inner radius     [  8.0 ] green px
 Background annulus — outer radius     [ 12.0 ] green px
 Effective now: aperture 7.5 px · annulus 8.5–12.0 px · FWHM 3.0 px (default, none measured yet)
REFERENCE STARS (automatic selection)
 Proposed comparisons                  [    5 ] calibrated stars
 Minimum S/N on the pilot frame        [ 10.0 ] SNR
 Brightness difference from target     [  1.5 ] mag
 Maximum separation                    [   25 ] ′
 Band for catalogue magnitudes / AAVSO FILT   [ TG ]      (new, P37; open question 8)
All radii are green-plane pixels. Argos constrains the background annulus outside the aperture; the
selected-star ring uses the current aperture.
```

**J. Observe ▸ Light curve drawer (cross-reference, Observe spec decides)**

```
├─[log Log]─[light-curve Light curve]──────────────────────────────── [nav-analyze Open in Review] [close] ┤
│ ● SS Cyg  11.234 ± 0.012   ▲ 000-AAA-333 σ 0.009   Ensemble: 4 of 5 stable                              │
│  ●●●  ●●   ●●●●●●  ●●●●  (target facet, 140 px)  ▲▲▲▲▲▲▲▲ (check facet, 60 px)                         │
```

### 2.4 Interaction and states

- **Plot contract** (keeps the Qt science identical, fixes the display problems):
  - Target facet: y = `mag` (label "Differential mag (TG)", the band taken from the data), inverted;
    error bar ±`mag_err` (with the systematic floor) in the series colour at `--chart-error-opacity`,
    no caps. Relative flux: y = `relative_flux / median(relative_flux)` over **unsaturated** finite
    points of that series (P34: the Qt median included saturated points; open question 9),
    label "Relative flux (median-normalised)", not inverted.
  - Check facet: same as target, own y scale.
  - Comparison facets: y = leave-one-out `mag − median(mag)` "Δmag from own median", inverted;
    flux mode `relative_flux / median − 1` "Δ relative flux". A reference line at 0 (`--chart-reference`).
  - Markers: target circle, comparison square, check triangle (`--role-*`, BRAND 10); saturated =
    `x` overlay in `--danger` plus legend key "Saturated"; suspect = hollow marker plus legend key
    "Suspect (hot pixel?)"; both in the tooltip.
  - X axis: shared and linked across every facet including the quality trend. Modes: JD (default,
    as in Qt; ticks relative to a whole-day offset written in the axis title, e.g. "JD − 2461346
    (UTC, mid-exposure)"), UTC clock ("UTC, 2026-10-30"), BJD_TDB (only when every point has it).
    Tooltips always give all available times with 5 decimals (BRAND 5).
  - Number formats: magnitudes 3 decimals with uncertainty in the UI (BRAND 5: `12.345 ± 0.012`);
    scatter and formal errors 4 decimals as in Qt (open question 10); files keep their own
    precision (CSV full float, AAVSO 6 / 4 / 4 / 3 decimals).
- **Live updates**: a point is appended without re-rendering the rest; when the server sends a new
  `sigma_syst` for a curve, error bars are recomputed client-side as `hypot(formal_mag_err,
  sigma_syst)` (identical to `uncertainty.py:95-98`). A manual zoom is never reset by new data;
  "Fit plots" (F) returns to auto mode, which then follows new points.
- **Selection**: clicking a point selects it in every facet (vertical cursor at its time), fills the
  Point card and highlights the nearest frame row in the Frames tab. ← / → move along the selected
  series. Clicking empty plot area clears the selection. Escape keeps its global meaning (abort a
  slew) except inside an open dialog or popover, which it closes.
- **Ensemble edits** (Live run only; Session shows the same table read-only with a lock note
  "Archived session: read-only"): remove = confirmation during a running sequence (2.3 G), undo toast
  otherwise; Recommend = popover with an explicit button (2.3 E); Refresh catalogue disabled with the
  tooltip "Identify the field first" when unsolved, spinner while fetching; every result is reported
  with the Qt log texts as a toast and a log line.
- **Busy / error**: opening a session shows a spinner on `open-session` and a determinate bar if the
  server reports progress (FITS headers are read for every frame); `SessionReviewError` text appears
  in an error toast and in the empty state ("Could not open session: No session.json in …"). Export
  success: toast "Exported {n} rows to {file}"; failure: error toast with the server message. Re-run:
  inline progress + Cancel; the result texts of 1.9 as toasts.
- **Confirmations** (text buttons, BRAND 7): Remove during a run, Replace VSP picks during a run,
  Re-run (the dialog itself). No confirmation for exports (they never overwrite silently: the save
  dialog or a unique server file name handles collisions).
- **Night Red**: role colours collapse to one hue, so identity is carried by marker shape and the
  facet header label; saturated `x` and suspect hollow markers stay distinguishable by shape; the
  metric menu, time-axis selector and all tooltips are token-drawn (no native select); plot canvas
  colours read from tokens at draw time and redraw on theme change (uPlot is already a dependency).
- **Keyboard (Review)**: F4 section, Ctrl+Shift+O open session (qt), U uncertainties (p), R relative
  flux (p), F fit plots (p), P rail (as Observe), D drawer (p), ← / → step point (p), Enter open
  source frame (p), Delete remove selected comparison (p, Live run, guarded), Ctrl+C copy ensemble
  TSV when the table has focus (p).
- **Persistence**: per viewer (browser storage via `lib/app/prefs.ts`, try/catch): source last used,
  time-axis mode, uncertainties and relative-flux toggles (Qt reset them every time), hidden facets,
  comparison columns, facet row heights, rail open, drawer open / tab / height, quality metric,
  folded rail cards. Server config (Settings): the seven `photometry.*` geometry / criteria keys,
  `photometry.auto_comparisons`, `photometry.default_band`, `observer.obscode`. `ui.review.layout`
  (a QMainWindow state blob) is not reused.
- **Visible without scrolling at 1440 x 900**: toolbar, target facet, check facet, up to 6
  comparison facets, quality trend, the Ensemble card (verdict + up to 8 rows), the Point card and
  the AAVSO summary. With the drawer open (240 px) the comparison rows scroll; the target facet
  stays.

### 2.5 API needs beyond v1

| Name | Kind | Payload sketch | Core / worker code it wraps | Notes |
|---|---|---|---|---|
| Live photometry snapshot | HTTP `GET /api/photometry/live` | `{object_name, run_root\|null, sequence_running, band, obscode, chart_id\|null, targets: TargetStar[], summary, curves: Curve[], quality: Report\|null, geometry: {aperture_px, annulus_in_px, annulus_out_px, fwhm_px, fwhm_source: "measured"\|"default"}, revision}`; `Curve = {key, role, name, auid, sigma_syst\|null, points: LcPoint[]}` with all 15 `LcPoint` fields | `acquisition_engine.py:235-256` (store, report), `980-986` (target set), `1222-1233` (geometry), `targets.py:98-115, 219-228` | Needed on (re)connect and after a reset event |
| Photometry point | WS event `photometry_point` | `{key, role, name, auid, point: LcPoint, sigma_syst\|null, revision}` | `_emit_live_point` `acquisition_engine.py:1415-1479` | Replaces `PhotometryPoint` (`types.py:75-86`, lacks bjd, suspect, airmass, comps, formal error). Sent for **every** point, including the ones that change the floor (no more full re-render, P3) |
| Curves reset | WS event `photometry_reset` | `{reason: "cleared"\|"object_changed"\|"adopted", revision}` | `clear_lightcurves` `acquisition_engine.py:269-274`, `on_object_changed` `1010-1022`, `adopt_curves` `258-267`, sequence start `444-458` | Client refetches the snapshot |
| Target set changed | WS event `photometry_targets` | `{targets: TargetStar[], summary}` | `targets_changed` (`acquisition_engine.py:104`) | Drives the Ensemble table and the Observe card |
| Comparison quality | WS event `comparison_quality` | full report (`quality.py:84-98`) | `comparison_quality_updated` (`acquisition_engine.py:1386-1413`) | Owner decision: also compute it outside a sequence run (P16) |
| Session metrics sample | WS event `session_metrics` | `{t_utc, jd_utc, airmass_target\|null, airmass_mount\|null, fwhm_px, hfd_px, sky_adu, star_count, ccd_temp_c\|null}` per processed frame | `imaging_page.py:2419-2438` (moves server-side), `acquisition_engine.py:750-765` | Always sent, not only while a window is open (P21); history in the snapshot or `GET /api/photometry/metrics` |
| Remove from target set | HTTP `POST /api/photometry/targets/remove` | `{key}` -> `{targets}` | `remove_target` `acquisition_engine.py:1235-1240` | Undo = `POST /api/photometry/targets/set-role {star}` (`set_target_role` `1024-1031`, already needed by Observe) |
| Recommend from pilot | HTTP `POST /api/photometry/comparisons/recommend` | `{mode: "replace"\|"complete", count?}` -> `{added, comparisons}`; 409 `not_solved` | `reselect_comparison_stars` `acquisition_engine.py:1053-1075`; `propose_comparison_stars` `1033-1051`; `_pilot_comparison_quality` `1160-1220` | Pilot measures every VSP candidate: run off the event loop |
| Refresh catalogue | HTTP `POST /api/catalog/refresh` -> 202; WS `catalog {state: "fetching"\|"ready"\|"error", counts, warnings}` | | `refetch_catalog` `acquisition_engine.py:815-832`, `_on_catalog` `904-965` | Network, not cancellable today; 409 `not_solved` instead of a silent no-op (P35). Shared with the Observe / catalogue spec |
| Photometry settings | HTTP `GET` / `PATCH /api/settings/photometry` | `{aperture_fwhm_mult, aperture_min_px, annulus_in_px, annulus_out_px, comparison_min_snr, comparison_max_delta_mag, comparison_max_separation_arcmin, auto_comparisons, default_band}` -> values + effective geometry; 400 on the Qt ranges; optional 409 `run_active` for geometry keys | `config.py:137-162, 240-247`; ranges `photometry_window.py:64-139`; `acquisition_engine.py:1222-1233` | Settings spec owns the page; listed here because Review and Observe read it |
| Export measurements | HTTP `GET /api/photometry/export.csv?source=live\|session&session=` | `text/csv` (19 columns) | `write_curves_csv` `lightcurve.py:136-147` | Needs a stream / string variant of the writer; or `POST {path}` for a server-side write under Tauri (open question 5) |
| AAVSO export preview | HTTP `POST /api/photometry/aavso/preview` | `{source, exclude_saturated, exclude_suspect}` -> `{obscode, band, chart, kname, rows, skipped_nonfinite, saturated, suspect}` | `write_aavso` `lightcurve.py:204-254`; `comparison_chart_id` `targets.py:219-228` | Feeds dialog F |
| AAVSO export | HTTP `GET /api/photometry/aavso.txt?…` | `text/plain` | same | Exclusion flags need a small core change (P6) |
| Session list | HTTP `GET /api/sessions` | `[{path, object, started_utc, n_frames, has_photometry, has_quality}]` | new scan of `Config.sessions_path` (`config.py:269-270`) for `session.json` (`session_log.py:26`) | Browser has no folder picker; Tauri may use its native dialog instead |
| Open session | HTTP `POST /api/review/session` | `{path}` -> `{root, object_name, started_utc, software, observer, frames: ReviewFrame[], metadata, comparison_quality, warnings, readiness_issues, image_type_counts, filter_counts, curves: Curve[]}`; 400 `session_invalid` with the `SessionReviewError` text | `load_session` `review.py:102-175`, `load_session_curves` `178-212`, `readiness_issues` `76-82` | Reads every FITS header for CCD-TEMP: long for big sessions, progress events or a background job (`WS review_progress {done,total}`). Fix P4 (check role) in `review.py:218` |
| Open CSV | HTTP `POST /api/review/csv` | `{path}` -> `{curves, targets\|null}` | `read_curves_csv` `lightcurve.py:150-170`, `TargetSet.load` beside the CSV (`analyze_page.py:754-760`) | Must restore role and name from the file prefix and `targets.json` (P5); 400 `no_rows` (P29) |
| Source frame | HTTP `GET /api/review/frame?session=&filename=` | binary frame in the `/ws/frames` encoding, or `{path}` then the frame-inspector route | `frame_path` `review.py:84-86`; `nearest_light_frame` `88-99` (client-side from `frames`) | Frame inspector spec defines the viewer; v1 `open-fits` must not be reused (it replaces the Observe image) |
| Batch re-run | HTTP `POST /api/photometry/rerun {folder}` -> 202, `POST /api/photometry/rerun/cancel`; WS `rerun_progress {done,total}`, `rerun_done {ok, error, frames_done, n_curves, rotation_deg, shift_px}` | 409 `not_solved` / `no_targets` / `no_comparisons`, 404 `no_frames`, 409 `busy` (one at a time) | `PhotometryBatchWorker` `photometry_batch_worker.py:71-155`; pre-checks `imaging_page.py:2255-2292`; `adopt_curves` `acquisition_engine.py:258-267` | Long-running, cancellable at frame boundaries; should write role-prefixed CSVs into a session folder (P33) |
| File browser | HTTP `GET /api/files?dir=&glob=` | `{entries: [{name, kind, size, mtime}]}` | new | Only if the browser build must pick CSV / FITS / folders; Tauri can use native dialogs (open question 6) |

## 3. Open questions for the owner

1. **Ensemble edits in Review.** Should Review ▸ Live run allow Remove / Recommend / Refresh catalogue
   (as the Qt window did), or should those live only in Observe ▸ Photometry, leaving Review strictly
   read-only?
2. **Aperture changes mid-run.** Lock the four geometry fields while a sequence runs, warn, or allow
   as today? (Today the curve silently mixes apertures.)
3. **Default time axis.** Keep JD (UTC) as in Qt, or default to UTC clock time, or to BJD_TDB when the
   site is set?
4. **AAVSO export guards.** Block export while the observer code is unset (Qt writes `XXX`)? Exclude
   saturated and suspect points by default (Qt includes them)? Put a note in `NOTES`?
5. **Where exports go.** Browser download, a Tauri save dialog, or a server-side write into the
   session folder (`<run>/exports/…`)?
6. **File pickers.** Server-side file browser route for the browser build, or rely on Tauri native
   dialogs only?
7. **Second monitor.** Is "open Review in its own window" (Tauri multi-window, or a second browser
   tab) acceptable as the replacement for the floating Photometry window and the floating docks?
8. **Band setting.** `photometry.default_band` has no UI anywhere; add it to Settings ▸ Photometry
   (it changes both the zero-point catalogue band and AAVSO `FILT`)?
9. **Relative-flux baseline.** Exclude saturated points from the median used for normalisation
   (display only; Qt includes them)?
10. **Precision of scatter and errors.** Keep 4 decimals in mag (Qt) or show mmag (`10.1 mmag`)?
11. **Overlay views.** Confirm dropping "All targets", "All comparison stars" and "+ Comparison plot
    below" in favour of one facet per star (BRAND 10 forbids more than three series per plot).
12. **Auto-count semantics.** When the proposed count changes, should Argos complete the ensemble
    (`propose`) or replace the VSP picks (`reselect`, today's behaviour)?
13. **Quality report outside a sequence.** Compute and show the leave-one-out status during plain
    live preview (today only during a run)?
14. **Check-star facet in Observe.** Show the check star in the Observe light-curve drawer, or the
    target only?

Uncertain points (not guessed): whether `analyze_page.py`, `metrics_panel.py`, `target_table.py` and
`variable_table.py` are also inventoried by another spec (they are covered here because the in-scope
widgets live in them); the offscreen renders (`/private/tmp/claude-502/-Users-jperret-Documents-perso-dev-argos/49afca06-fc52-4dfd-a4bb-6d48cbd3dd5c/scratchpad/webui-spec/review-photometry/*.png`)
showed overlapping Review docks, which may be an offscreen-platform artefact, so it is not listed as
a problem; whether the Seestar writes `EXPTIME` in every sub (the batch midpoint depends on it).
