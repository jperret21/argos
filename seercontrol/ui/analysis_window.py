"""Analysis window — a standalone viewer for inspecting a saved FITS frame.

The main Acquisition page is the **live** view (it follows the running camera).
"Open FITS" opens *this* floating window instead, so analysing an old sub never
disturbs the live preview. It carries the full toolset — debayer/channel select,
stretch + per-channel histogram, region stats, saturation, FWHM overlay, loupe,
and click-to-measure a star — on a single static frame.

Processing is one-shot and synchronous (no live stream), via the shared
``build_processed_frame`` so the render/metrics path matches the live worker.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from seercontrol.core.imaging.debayer import VIEW_G, VIEW_RAW, extract_plane
from seercontrol.core.imaging.metrics import (
    ARCSEC_PER_FULL_PX,
    ARCSEC_PER_GREEN_PX,
    DEFAULT_STAR_RADIUS,
    TRACK_SNAP_SEARCH,
    measure_star_at,
)
from seercontrol.core.imaging.astrometry_session import (
    build_solve_settings,
    field_geometry,
    full_res_scale,
    overlay_for,
    project_points,
    wcs_from_result,
)
from seercontrol.core.imaging.platesolve import format_dec_dms, format_ra_hms
from seercontrol.ui import theme
from seercontrol.ui.widgets.fits_viewer import FitsViewer
from seercontrol.ui.widgets.histogram_dock import HistogramDock
from seercontrol.ui.widgets.image_toolbar import ImageToolbar
from seercontrol.workers.catalog_worker import CatalogRequest, CatalogWorker
from seercontrol.workers.preview_processor import build_processed_frame
from seercontrol.workers.solve_worker import SolveWorker

logger = logging.getLogger(__name__)


def read_fits_2d(path: str) -> np.ndarray | None:
    """Read a FITS file into a 2-D float32 array (NaNs zeroed, cubes collapsed)."""
    from astropy.io import fits  # heavy import — only on demand

    with fits.open(path) as hdul:
        data = next((h.data for h in hdul if getattr(h, "data", None) is not None), None)
    if data is None:
        return None
    arr = np.nan_to_num(np.asarray(data, dtype=np.float32), nan=0.0)
    if arr.ndim == 3:  # colour / cube → collapse to a 2-D plane
        arr = arr.mean(axis=0) if arr.shape[0] <= 4 else arr.mean(axis=2)
    return arr if arr.ndim == 2 else None


class AnalysisWindow(QMainWindow):
    """Floating window to analyse one loaded FITS frame (display only)."""

    def __init__(self, config=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("FITS analysis")
        self.setMinimumSize(900, 640)
        # Independent top-level window, not glued to the main window.
        self.setWindowFlag(Qt.WindowType.Window, True)

        self._raw: np.ndarray | None = None
        self._channel = VIEW_RAW
        self._radius = DEFAULT_STAR_RADIUS
        self._green_shape: tuple[int, int] | None = None
        self._disp_shape: tuple[int, int] | None = None
        self._selected_green: tuple[float, float] | None = None
        self._solver: SolveWorker | None = None
        self._wcs = None  # platesolve.FrameWCS once solved
        # §6 catalog: VSX variables + their green-plane positions (for hit-test).
        self._catalog_worker: CatalogWorker | None = None
        self._variables: list = []
        self._var_green: list[tuple[float, float]] = []
        self._comparisons: list = []
        self._comp_rows: list = []  # R5: ranked comparisons for the selected variable
        self._comp_green: list = []  # comparison green-px positions (parallel to _comp_rows)
        self._selected_variable = None  # the variable whose comparisons are listed
        self._comp_dialog = None  # popup table, created lazily on first open

        self._build_ui()
        self._wire()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Open-FITS has its own Solve bar (below), so the toolbar drops the
        # live-page Solve / Auto-solve buttons to avoid two confusing solve paths.
        self._toolbar = ImageToolbar(show_solve=False)
        root.addWidget(self._toolbar)

        self._viewer = FitsViewer()
        self._histogram = HistogramDock()
        self._histogram.setMinimumWidth(320)
        self._histogram.setMaximumWidth(420)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(self._viewer)
        split.addWidget(self._histogram)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        split.setSizes([900, 360])
        root.addWidget(split, 1)

        # Bottom bar: plate-solve this frame (ASTAP) + the WCS result readout.
        bar = QWidget()
        bar.setStyleSheet(f"background:{theme.SURFACE_3}; border-top:1px solid {theme.SURFACE_4};")
        brow = QHBoxLayout(bar)
        brow.setContentsMargins(10, 4, 10, 4)
        brow.setSpacing(10)
        self._solve_btn = QPushButton("Solve (ASTAP)")
        self._solve_btn.setToolTip(
            "Plate-solve the green channel via ASTAP (configure in Settings)"
        )
        self._solve_btn.clicked.connect(self._on_solve)
        brow.addWidget(self._solve_btn)
        # R1: independent show/hide toggles for the RA/Dec grid and the
        # variable-star markers (enabled once a solve provides a WCS).
        self._grid_btn = QPushButton("Grid")
        self._grid_btn.setCheckable(True)
        self._grid_btn.setEnabled(False)
        self._grid_btn.setToolTip("Show/hide the RA/Dec grid")
        self._grid_btn.toggled.connect(self._viewer.set_astrometry_enabled)
        brow.addWidget(self._grid_btn)
        self._var_btn = QPushButton("Variables")
        self._var_btn.setCheckable(True)
        self._var_btn.setEnabled(False)
        self._var_btn.setToolTip("Show/hide the variable-star markers")
        self._var_btn.toggled.connect(self._viewer.set_catalog_enabled)
        brow.addWidget(self._var_btn)
        # R5: show/hide the comparison-star markers (cyan squares + labels) of
        # the selected variable on the image.
        self._comp_markers_btn = QPushButton("Comp. markers")
        self._comp_markers_btn.setCheckable(True)
        self._comp_markers_btn.setEnabled(False)
        self._comp_markers_btn.setToolTip("Show/hide comparison-star markers on the image")
        self._comp_markers_btn.toggled.connect(self._viewer.set_comparison_enabled)
        brow.addWidget(self._comp_markers_btn)
        # R5: opens the comparison-star table for the selected variable.
        self._comp_btn = QPushButton("Comparison stars")
        self._comp_btn.setToolTip("Select a variable star first, then list its comparison stars")
        self._comp_btn.setEnabled(False)
        self._comp_btn.clicked.connect(self._on_comp_btn)
        brow.addWidget(self._comp_btn)
        # R6: astrometry + catalog settings popup (same config as the main page).
        self._settings_btn = QPushButton("Settings…")
        self._settings_btn.setToolTip("Astrometry & catalog parameters")
        self._settings_btn.clicked.connect(self._on_settings)
        brow.addWidget(self._settings_btn)
        self._solve_lbl = QLabel("not solved")
        self._solve_lbl.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-family:{theme.FONT_MONO};"
            f" font-size:11px; background:transparent;"
        )
        brow.addWidget(self._solve_lbl, 1)
        root.addWidget(bar)

        self.setCentralWidget(central)

    def _wire(self) -> None:
        self._toolbar.channel_changed.connect(self._on_channel)
        self._toolbar.open_requested.connect(self._on_open)
        self._histogram.stretch_changed.connect(self._viewer.set_stretch)
        self._histogram.auto_requested.connect(self._viewer.auto_stretch)
        self._histogram.saturation_toggled.connect(self._on_saturation_toggled)
        self._histogram.roi_toggled.connect(self._viewer.set_roi_enabled)
        self._histogram.crosshair_toggled.connect(self._viewer.set_crosshair_enabled)
        self._histogram.stars_overlay_toggled.connect(self._viewer.set_star_overlay_enabled)
        self._histogram.loupe_toggled.connect(self._viewer.set_loupe_enabled)
        # Grid + variable markers are driven by their own bar buttons (R1); hide
        # the histogram's now-redundant "WCS grid overlay" checkbox.
        self._histogram._astro_chk.hide()
        self._histogram.star_radius_changed.connect(self._on_radius)
        self._viewer.levels_changed.connect(self._histogram.set_levels)
        self._viewer.region_info.connect(self._histogram.set_region_info)
        self._viewer.star_clicked.connect(self._on_star_clicked)

    # ------------------------------------------------------------------
    # Loading + processing
    # ------------------------------------------------------------------

    def load(self, path: str) -> bool:
        """Load a FITS file into the window. Returns False on failure."""
        try:
            arr = read_fits_2d(path)
        except Exception as exc:
            logger.warning("Open FITS failed: %s", exc)
            return False
        if arr is None:
            return False
        self._raw = arr
        self._selected_green = None
        self._viewer.clear_selection()
        self._wcs = None  # a new frame invalidates the previous solution
        self._viewer.set_astrometry_overlay(None)
        self._grid_btn.setChecked(False)
        self._grid_btn.setEnabled(False)
        self._clear_catalog()
        self._set_solve_text("not solved", theme.FG_MUTED)
        self._channel = VIEW_RAW
        self._toolbar.set_view(VIEW_RAW)
        self.setWindowTitle(f"FITS analysis — {Path(path).name}  ({arr.shape[1]}×{arr.shape[0]})")
        self._reprocess()
        return True

    def _reprocess(self) -> None:
        if self._raw is None:
            return
        pf = build_processed_frame(self._raw, self._channel, self._radius)
        self._green_shape = pf.green_shape
        self._disp_shape = pf.display.shape[:2]
        self._histogram.set_histogram(pf.centers, pf.r, pf.g, pf.b, pf.lo, pf.hi)
        self._viewer.set_stars(pf.stars, pf.green_shape)
        self._viewer.display(pf.display)
        self._remeasure_selection()

    def _on_channel(self, channel: str) -> None:
        self._channel = channel
        self._reprocess()

    def _on_radius(self, radius: int) -> None:
        self._radius = max(2, int(radius))
        self._reprocess()

    def _on_open(self) -> None:
        from PyQt6.QtWidgets import QFileDialog

        start = str(Path.home() / "Downloads")
        path, _ = QFileDialog.getOpenFileName(
            self, "Open FITS", start, "FITS (*.fits *.fit *.fts);;All files (*)"
        )
        if path:
            self.load(path)

    # ------------------------------------------------------------------
    # Plate solving (§6)
    # ------------------------------------------------------------------

    def _cfg(self, key: str, default):
        if self._config is None:
            return default
        value = self._config.get(key, default)
        return default if value is None else value

    def _on_saturation_toggled(self, enabled: bool) -> None:
        threshold = int(self._cfg("camera.full_well_adu", 60000))
        self._viewer.set_saturation(enabled, threshold)

    def _on_solve(self) -> None:
        if self._raw is None or (self._solver is not None and self._solver.isRunning()):
            return
        green = extract_plane(self._raw, VIEW_G)
        # Static frame, no mount hint → thorough settings via the shared builder.
        settings = build_solve_settings(self._cfg, self._green_shape, live=False)
        self._solve_btn.setEnabled(False)
        self._set_solve_text("solving… (ASTAP)", theme.WARNING)
        self._solver = SolveWorker(green, settings, parent=self)
        self._solver.solved.connect(self._on_solved)
        self._solver.start()

    def _on_solved(self, result) -> None:
        self._solve_btn.setEnabled(True)
        if not result.solved:
            self._set_solve_text(f"not solved — {result.message}", theme.DANGER)
            return
        bits = [f"RA {result.ra_hours:.4f}h", f"Dec {result.dec_deg:+.4f}°"]
        scale = full_res_scale(result)  # green plane → full-res (÷2), once, shared
        if scale is not None:
            bits.append(f"{scale:.2f}″/px")
        if result.rotation_deg is not None:
            bits.append(f"rot {result.rotation_deg:.1f}°")
        if result.mirrored:
            bits.append("mirrored")
        self._set_solve_text("Solved — " + "   ".join(bits), theme.SUCCESS)

        # Build the WCS → enable the grid overlay + per-star RA/Dec readout.
        self._wcs = wcs_from_result(result, self._green_shape)
        if self._wcs is not None:
            self._update_astrometry_overlay()
            self._grid_btn.setEnabled(True)
            self._grid_btn.setChecked(True)  # → shows the grid via toggled
            self._remeasure_selection()  # refresh the clicked star's RA/Dec
            self._fetch_catalog()  # VSX variables (+ VSP comparisons) for the field

    # ------------------------------------------------------------------
    # Catalog overlay (§6): VSX variable stars + VSP comparison stars
    # ------------------------------------------------------------------

    def _fetch_catalog(self) -> None:
        if self._catalog_worker is not None and self._catalog_worker.isRunning():
            return
        geom = field_geometry(self._wcs, self._green_shape)
        if geom is None:
            return
        ra_deg, dec_deg, radius_deg, fov_arcmin = geom
        req = CatalogRequest(
            ra_deg=ra_deg,
            dec_deg=dec_deg,
            radius_deg=radius_deg,
            fov_arcmin=fov_arcmin,
            mag_limit=float(self._cfg("catalog.mag_limit", 15.0)),
            max_results=int(self._cfg("catalog.max_results", 250)),
            include_suspected=bool(self._cfg("catalog.include_suspected", True)),
        )
        self._catalog_worker = CatalogWorker(req, parent=self)
        self._catalog_worker.fetched.connect(self._on_catalog)
        self._catalog_worker.start()

    def _on_catalog(self, result) -> None:
        if not result.ok:
            logger.info("Catalog fetch failed: %s", result.error)
            return
        self._variables = list(result.variables)
        self._comparisons = list(result.comparisons)
        self._project_variables()

    def _project_variables(self) -> None:
        """Project variables to green px, keep those inside the frame, draw them."""
        # ``_var_green`` stays parallel to ``_variables`` (None = off-frame) so the
        # click hit-test can map a marker index back to its variable.
        self._var_green = project_points(
            self._wcs, self._green_shape, ((v.ra_deg, v.dec_deg) for v in self._variables)
        )
        points = [
            (pos[0], pos[1], v.is_suspected)
            for pos, v in zip(self._var_green, self._variables)
            if pos is not None
        ]
        self._viewer.set_catalog_markers(points, self._green_shape)
        has = bool(points)
        self._var_btn.setEnabled(has)
        self._var_btn.setChecked(has)  # → shows markers via toggled
        if has and self._var_btn.isChecked():
            self._viewer.set_catalog_enabled(True)  # refresh if already checked

    def _clear_catalog(self) -> None:
        self._variables = []
        self._var_green = []
        self._comparisons = []
        self._comp_rows = []
        self._selected_variable = None
        self._comp_green = []
        self._viewer.set_catalog_markers((), self._green_shape)
        self._viewer.set_comparison_markers((), self._green_shape)
        self._var_btn.setChecked(False)
        self._var_btn.setEnabled(False)
        self._comp_markers_btn.setChecked(False)
        self._comp_markers_btn.setEnabled(False)
        self._comp_btn.setEnabled(False)
        self._comp_btn.setText("Comparison stars")
        if self._comp_dialog is not None:
            self._comp_dialog.hide()

    # ------------------------------------------------------------------
    # Comparison stars (§6, R5): ranked table for the selected variable
    # ------------------------------------------------------------------

    def _populate_comparisons(self, v) -> None:
        """Rank the field's comparison stars for variable ``v`` and arm the
        'Comparison stars' button (the full table opens on click)."""
        from seercontrol.core.catalog import comparisons_for_variable

        self._selected_variable = v
        self._comp_rows = comparisons_for_variable(v, self._comparisons, max_results=50)
        has = bool(self._comp_rows)
        self._comp_btn.setEnabled(has)
        self._comp_btn.setText(
            f"Comparison stars ({len(self._comp_rows)})" if has else "Comparison stars"
        )
        if has and self._comp_dialog is not None and self._comp_dialog.isVisible():
            self._comp_dialog.set_data(v.name, self._comp_rows)  # live-refresh if open
        self._plot_comparison_markers()

    def _plot_comparison_markers(self) -> None:
        """Project the ranked comparisons onto the frame and draw the markers."""
        # ``_comp_green`` stays parallel to ``_comp_rows`` (None = off-frame).
        self._comp_green = project_points(
            self._wcs, self._green_shape, ((s.star.ra_deg, s.star.dec_deg) for s in self._comp_rows)
        )
        points = [
            (pos[0], pos[1], s.star.label)
            for pos, s in zip(self._comp_green, self._comp_rows)
            if pos is not None
        ]
        self._viewer.set_comparison_markers(points, self._green_shape)
        has = bool(points)
        self._comp_markers_btn.setEnabled(has)
        self._comp_markers_btn.setChecked(has)  # → shows markers via toggled
        if has and self._comp_markers_btn.isChecked():
            self._viewer.set_comparison_enabled(True)  # refresh if already checked

    def _on_comp_btn(self) -> None:
        """Open the comparison-star table for the currently selected variable."""
        if not self._comp_rows or self._selected_variable is None:
            return
        if self._comp_dialog is None:
            from seercontrol.ui.widgets.comparison_table import ComparisonTableDialog

            self._comp_dialog = ComparisonTableDialog(self)
            self._comp_dialog.row_activated.connect(self._on_comp_selected)
        self._comp_dialog.set_data(self._selected_variable.name, self._comp_rows)
        self._comp_dialog.show()
        self._comp_dialog.raise_()

    def _on_settings(self) -> None:
        """R6: open the astrometry + catalog settings popup. If the new limits
        change anything and a solution exists, re-query the catalog."""
        from seercontrol.ui.widgets.astrometry_settings import AstrometrySettingsDialog

        dlg = AstrometrySettingsDialog(self._config, self)
        if dlg.exec() and self._wcs is not None:
            self._update_astrometry_overlay()  # grid spacing may have changed
            self._fetch_catalog()  # mag limit / max may have changed

    def _on_comp_selected(self, scored) -> None:
        """A row in the comparison table was clicked → ring that star on the image."""
        if self._wcs is None:
            return
        c = scored.star
        x, y = self._wcs.world_to_pixel_deg(c.ra_deg, c.dec_deg)
        dp = self._green_to_disp(float(x), float(y))
        if dp is None:
            return
        self._selected_green = None
        self._viewer.mark_selection(dp[0], dp[1], self._format_comparison_text(c, scored))

    def _format_comparison_text(self, c, scored) -> str:
        lines = [f"Comparison  {c.auid}"]
        mags = [f"{b.band} {b.mag:.3f}" for b in c.bands]
        if mags:
            lines.append("   ".join(mags))
        if c.label:
            lines.append(f"chart label {c.label}   sep {scored.separation_arcmin:.1f}'")
        if c.comments:
            lines.append(str(c.comments))
        lines.append(f"RA {format_ra_hms(c.ra_deg / 15.0)}  Dec {format_dec_dms(c.dec_deg)}")
        return "\n".join(lines)

    def _update_astrometry_overlay(self) -> None:
        # Shared builder applies astrometry.grid_spacing_arcmin (0 = adaptive).
        overlay = overlay_for(self._wcs, self._green_shape, self._cfg)
        self._viewer.set_astrometry_overlay(overlay, self._green_shape)

    def _set_solve_text(self, text: str, color: str) -> None:
        self._solve_lbl.setText(text)
        self._solve_lbl.setStyleSheet(
            f"color:{color}; font-family:{theme.FONT_MONO}; font-size:11px; background:transparent;"
        )

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if self._solver is not None and self._solver.isRunning():
            self._solver.wait(2000)
        if self._catalog_worker is not None and self._catalog_worker.isRunning():
            self._catalog_worker.wait(2000)
        if self._comp_dialog is not None:
            self._comp_dialog.close()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Click-to-measure (§5)
    # ------------------------------------------------------------------

    def _on_star_clicked(self, x_disp: float, y_disp: float) -> None:
        gp = self._disp_to_green(x_disp, y_disp)
        if gp is None or self._raw is None:
            return
        vi = self._nearest_variable(gp[0], gp[1])
        if vi is not None:  # a catalog variable takes precedence over star metrics
            self._show_variable(vi)
            return
        ci = self._nearest_comparison(gp[0], gp[1])
        if ci is not None:  # then a comparison marker
            self._on_comp_selected(self._comp_rows[ci])
            return
        meas = measure_star_at(self._raw, gp[0], gp[1], self._radius)
        if meas is None:
            self._viewer.clear_selection()
            self._selected_green = None
            return
        self._selected_green = (meas.x, meas.y)
        self._show_selection(meas)

    def _remeasure_selection(self) -> None:
        if self._selected_green is None or self._raw is None:
            return
        # Tight snap → the centre is stable when the aperture radius changes.
        meas = measure_star_at(
            self._raw,
            self._selected_green[0],
            self._selected_green[1],
            self._radius,
            search=TRACK_SNAP_SEARCH,
        )
        if meas is not None:
            self._selected_green = (meas.x, meas.y)
            self._show_selection(meas)

    def _show_selection(self, meas) -> None:
        dp = self._green_to_disp(meas.x, meas.y)
        if dp is None:
            return
        radius_disp = self._green_len_to_disp(meas.radius)
        self._viewer.mark_selection(dp[0], dp[1], self._format_star_text(meas), radius_disp)

    def _format_star_text(self, meas) -> str:
        parts = ["Selected star"]
        if meas.fwhm is not None:
            parts.append(f"FWHM {meas.fwhm * ARCSEC_PER_GREEN_PX:.1f}″")
        if meas.hfd is not None:
            parts.append(f"HFD {meas.hfd * ARCSEC_PER_GREEN_PX:.1f}″")
        if meas.eccentricity is not None:
            parts.append(f"ecc {meas.eccentricity:.2f}")
        parts.append(f"SNR {meas.snr:.0f}")
        parts.append(f"peak {meas.peak_adu} ADU")
        text = "   ".join(parts) + f"\nscale  {ARCSEC_PER_FULL_PX:.2f}″/px"
        if self._wcs is not None:  # solved → give the star's celestial position
            ra_h, dec_d = self._wcs.pixel_to_radec(meas.x, meas.y)
            text += f"\nRA {format_ra_hms(ra_h)}  Dec {format_dec_dms(dec_d)}"
        return text

    def _nearest_variable(self, gx: float, gy: float) -> int | None:
        """Index of the variable nearest (gx, gy) green px within tolerance."""
        if not self._var_green:
            return None
        tol = 10.0  # green px; widen for a coarse display→green scale
        if self._green_shape and self._disp_shape:
            _gh, gw = self._green_shape
            _dh, dw = self._disp_shape
            if dw > 0:
                tol = max(6.0, 14.0 * gw / dw)
        best_i, best_d = None, tol
        for i, pos in enumerate(self._var_green):
            if pos is None:
                continue
            d = ((pos[0] - gx) ** 2 + (pos[1] - gy) ** 2) ** 0.5
            if d <= best_d:
                best_i, best_d = i, d
        return best_i

    def _nearest_comparison(self, gx: float, gy: float) -> int | None:
        """Index of the comparison nearest (gx, gy), only while its markers show."""
        if not self._comp_green or not self._comp_markers_btn.isChecked():
            return None
        tol = 10.0
        if self._green_shape and self._disp_shape:
            _gh, gw = self._green_shape
            _dh, dw = self._disp_shape
            if dw > 0:
                tol = max(6.0, 14.0 * gw / dw)
        best_i, best_d = None, tol
        for i, pos in enumerate(self._comp_green):
            if pos is None:
                continue
            d = ((pos[0] - gx) ** 2 + (pos[1] - gy) ** 2) ** 0.5
            if d <= best_d:
                best_i, best_d = i, d
        return best_i

    def _show_variable(self, i: int) -> None:
        v = self._variables[i]
        pos = self._var_green[i]
        dp = self._green_to_disp(pos[0], pos[1]) if pos else None
        if dp is None:
            return
        self._selected_green = None  # a catalog pick, not a measured star
        self._viewer.mark_selection(dp[0], dp[1], self._format_variable_text(v))
        self._populate_comparisons(v)  # R5: comparison stars for this variable

    def _format_variable_text(self, v) -> str:
        head = f"Variable  {v.name}" + (f"   [{v.var_type}]" if v.var_type else "")
        if v.is_suspected:
            head += "   (suspected)"
        lines = [head]
        rng = []
        if v.max_mag:
            rng.append(f"max {v.max_mag}")
        if v.min_mag and v.min_mag != "?":
            rng.append(f"min {v.min_mag}")
        if rng:
            lines.append("   ".join(rng))
        if v.period:
            lines.append(f"period {v.period:g} d")
        if v.auid:
            lines.append(f"AUID {v.auid}")
        lines.append(f"RA {format_ra_hms(v.ra_deg / 15.0)}  Dec {format_dec_dms(v.dec_deg)}")
        return "\n".join(lines)

    def _disp_to_green(self, x: float, y: float) -> tuple[float, float] | None:
        if self._green_shape is None or self._disp_shape is None:
            return None
        gh, gw = self._green_shape
        dh, dw = self._disp_shape
        if dw <= 0 or dh <= 0:
            return None
        return x * gw / dw, y * gh / dh

    def _green_to_disp(self, x: float, y: float) -> tuple[float, float] | None:
        if self._green_shape is None or self._disp_shape is None:
            return None
        gh, gw = self._green_shape
        dh, dw = self._disp_shape
        if gw <= 0 or gh <= 0:
            return None
        return x * dw / gw, y * dh / gh

    def _green_len_to_disp(self, length: float) -> float | None:
        """Scale a green-plane length (e.g. the aperture radius) to display px."""
        if self._green_shape is None or self._disp_shape is None:
            return None
        gw = self._green_shape[1]
        dw = self._disp_shape[1]
        return length * dw / gw if gw > 0 else None
