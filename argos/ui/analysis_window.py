"""Analysis window — standalone viewer for inspecting a single FITS frame.

Opened via the "Open FITS" button on the main toolbar. Pure image inspection:
stretch, histogram, channels, star measurement, optional plate-solve for
informational RA/Dec readout. No catalog, no target management, no photometry
setup — those belong in the Photometry Setup window.
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

from argos.core.imaging.debayer import VIEW_G, VIEW_RAW, extract_plane
from argos.core.imaging.metrics import (
    ARCSEC_PER_FULL_PX,
    ARCSEC_PER_GREEN_PX,
    DEFAULT_STAR_RADIUS,
    TRACK_SNAP_SEARCH,
    measure_star_at,
)
from argos.core.imaging.platesolve import format_dec_dms, format_ra_hms
from argos.ui import theme
from argos.ui.widgets.fits_viewer import FitsViewer
from argos.ui.widgets.histogram_dock import HistogramDock
from argos.ui.widgets.image_toolbar import ImageToolbar
from argos.workers.preview_processor import build_processed_frame
from argos.workers.solve_worker import SolveWorker

logger = logging.getLogger(__name__)


def read_fits_2d(path: str) -> np.ndarray | None:
    """Read a FITS file into a 2-D float32 array (NaNs zeroed, cubes collapsed)."""
    from astropy.io import fits

    with fits.open(path) as hdul:
        data = next((h.data for h in hdul if getattr(h, "data", None) is not None), None)
    if data is None:
        return None
    arr = np.nan_to_num(np.asarray(data, dtype=np.float32), nan=0.0)
    if arr.ndim == 3:
        arr = arr.mean(axis=0) if arr.shape[0] <= 4 else arr.mean(axis=2)
    return arr if arr.ndim == 2 else None


def read_fits_meta(path: str) -> dict:
    """Return a dict of useful header keywords from a FITS file."""
    from astropy.io import fits

    keys = ("OBJECT", "DATE-OBS", "EXPTIME", "FILTER", "GAIN",
            "INSTRUME", "OBSERVER", "SITENAME",
            "CRPIX1", "CRPIX2", "CRVAL1", "CRVAL2", "CD1_1", "CD2_2")
    meta = {}
    try:
        with fits.open(path) as hdul:
            for h in hdul:
                if getattr(h, "header", None) is None:
                    continue
                hdr = h.header
                for k in keys:
                    if k in hdr:
                        meta[k] = str(hdr[k]).strip()
                # Also grab ORIGIN / COMMENT / HISTORY as a single text block.
                for k in ("ORIGIN",):
                    if k in hdr:
                        meta[k] = str(hdr[k]).strip()
                break  # primary header only
    except Exception:
        pass
    return meta


class AnalysisWindow(QMainWindow):
    """Floating window to inspect one loaded FITS frame.

    Pure image inspection — no catalog, no target management, no comparison
    stars. Optional plate-solve for informational RA/Dec readout and a WCS
    grid overlay.
    """

    def __init__(self, config=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("Frame Viewer")
        self.setMinimumSize(900, 640)
        self.setWindowFlag(Qt.WindowType.Window, True)

        self._raw: np.ndarray | None = None
        self._channel = VIEW_RAW
        self._radius = DEFAULT_STAR_RADIUS
        self._green_shape: tuple[int, int] | None = None
        self._disp_shape: tuple[int, int] | None = None
        self._selected_green: tuple[float, float] | None = None
        self._solver: SolveWorker | None = None
        self._wcs = None  # platesolve.FrameWCS once solved
        self._meta: dict = {}  # header keywords

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

        self._toolbar = ImageToolbar(show_solve=False)
        root.addWidget(self._toolbar)

        self._viewer = FitsViewer()
        self._histogram = HistogramDock()
        self._histogram.setMinimumWidth(320)
        self._histogram.setMaximumWidth(420)

        # Info panel: shows header metadata + pixel stats for the loaded frame.
        self._info_panel = QWidget()
        self._info_panel.setMinimumWidth(320)
        self._info_panel.setMaximumWidth(420)
        info_layout = QVBoxLayout(self._info_panel)
        info_layout.setContentsMargins(8, 8, 8, 8)
        self._info_label = QLabel("No frame loaded")
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:11px; font-family:{theme.FONT_MONO};"
            f" background:transparent;"
        )
        info_layout.addWidget(self._info_label)
        info_layout.addStretch()

        # Tab widget: Histogram | Info
        self._right_tabs = QWidget()
        tab_layout = QVBoxLayout(self._right_tabs)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)
        from PyQt6.QtWidgets import QTabWidget
        self._tab_widget = QTabWidget()
        self._tab_widget.addTab(self._histogram, "Histogram")
        self._tab_widget.addTab(self._info_panel, "Info")
        tab_layout.addWidget(self._tab_widget)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(self._viewer)
        split.addWidget(self._right_tabs)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        split.setSizes([900, 360])
        root.addWidget(split, 1)

        # Bottom bar: plate-solve + WCS grid + solve status.
        bar = QWidget()
        bar.setStyleSheet(
            f"background:{theme.SURFACE_3}; border-top:1px solid {theme.SURFACE_4};"
        )
        brow = QHBoxLayout(bar)
        brow.setContentsMargins(10, 4, 10, 4)
        brow.setSpacing(10)

        self._solve_btn = QPushButton("Solve (ASTAP)")
        self._solve_btn.setToolTip("Plate-solve the green channel via ASTAP")
        self._solve_btn.clicked.connect(self._on_solve)
        brow.addWidget(self._solve_btn)

        self._grid_btn = QPushButton("Grid")
        self._grid_btn.setCheckable(True)
        self._grid_btn.setEnabled(False)
        self._grid_btn.setToolTip("Show/hide the RA/Dec grid")
        self._grid_btn.toggled.connect(self._viewer.set_astrometry_enabled)
        brow.addWidget(self._grid_btn)

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
        self._histogram.saturation_toggled.connect(self._on_saturation)
        self._histogram.roi_toggled.connect(self._viewer.set_roi_enabled)
        self._histogram.crosshair_toggled.connect(self._viewer.set_crosshair_enabled)
        self._histogram.stars_overlay_toggled.connect(self._viewer.set_star_overlay_enabled)
        self._histogram.loupe_toggled.connect(self._viewer.set_loupe_enabled)
        self._histogram._astro_chk.hide()  # WCS grid is driven by our own Grid button
        self._histogram.star_radius_changed.connect(self._on_radius)
        self._viewer.levels_changed.connect(self._histogram.set_levels)
        self._viewer.region_info.connect(self._histogram.set_region_info)
        self._viewer.star_clicked.connect(self._on_star_clicked)

    # ------------------------------------------------------------------
    # Loading
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
        self._meta = read_fits_meta(path)
        self._selected_green = None
        self._viewer.clear_selection()
        self._wcs = None
        self._viewer.set_astrometry_overlay(None)
        self._grid_btn.setChecked(False)
        self._grid_btn.setEnabled(False)
        self._set_solve_text("not solved", theme.FG_MUTED)
        self._channel = VIEW_RAW
        self._toolbar.set_view(VIEW_RAW)
        name = Path(path).name
        h, w = arr.shape
        self.setWindowTitle(f"Frame Viewer — {name}  ({w}×{h})")
        self._update_info()
        self._reprocess()
        return True

    def _update_info(self) -> None:
        """Refresh the Info tab with header metadata + pixel stats."""
        if self._raw is None:
            self._info_label.setText("No frame loaded")
            return
        lines = []
        # Pixel stats
        lines.append(f"Dimensions:  {self._raw.shape[1]}×{self._raw.shape[0]}")
        lines.append(f"Min / Max:   {self._raw.min():.0f} / {self._raw.max():.0f}")
        lines.append(f"Mean / σ:    {self._raw.mean():.0f} / {self._raw.std():.0f}")
        lines.append("")
        # Header keywords
        for k in ("OBJECT", "DATE-OBS", "EXPTIME", "FILTER", "GAIN",
                  "INSTRUME", "OBSERVER", "SITENAME", "ORIGIN"):
            v = self._meta.get(k)
            if v:
                lines.append(f"{k}:  {v}")
        self._info_label.setText("\n".join(lines))

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
    # Plate solving (optional, for info)
    # ------------------------------------------------------------------

    def _cfg(self, key: str, default):
        if self._config is None:
            return default
        value = self._config.get(key, default)
        return default if value is None else value

    def _on_saturation(self, enabled: bool) -> None:
        threshold = int(self._cfg("camera.full_well_adu", 60000))
        self._viewer.set_saturation(enabled, threshold)

    def _on_solve(self) -> None:
        if self._raw is None or (self._solver is not None and self._solver.isRunning()):
            return
        green = extract_plane(self._raw, VIEW_G)
        from argos.core.imaging.astrometry_session import build_solve_settings

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
        from argos.core.imaging.astrometry_session import (
            full_res_scale,
            overlay_for,
            wcs_from_result,
        )

        bits = [f"RA {result.ra_hours:.4f}h", f"Dec {result.dec_deg:+.4f}°"]
        scale = full_res_scale(result)
        if scale is not None:
            bits.append(f"{scale:.2f}″/px")
        if result.rotation_deg is not None:
            bits.append(f"rot {result.rotation_deg:.1f}°")
        self._set_solve_text("Solved — " + "   ".join(bits), theme.SUCCESS)

        self._wcs = wcs_from_result(result, self._green_shape)
        if self._wcs is not None:
            overlay = overlay_for(self._wcs, self._green_shape, self._cfg)
            self._viewer.set_astrometry_overlay(overlay, self._green_shape)
            self._grid_btn.setEnabled(True)
            self._grid_btn.setChecked(True)
            self._remeasure_selection()

    # ------------------------------------------------------------------
    # Click-to-measure
    # ------------------------------------------------------------------

    def _on_star_clicked(self, x_disp: float, y_disp: float) -> None:
        gp = self._disp_to_green(x_disp, y_disp)
        if gp is None or self._raw is None:
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
        if self._wcs is not None:
            ra_h, dec_d = self._wcs.pixel_to_radec(meas.x, meas.y)
            text += f"\nRA {format_ra_hms(ra_h)}  Dec {format_dec_dms(dec_d)}"
        return text

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

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
        if self._green_shape is None or self._disp_shape is None:
            return None
        gw = self._green_shape[1]
        dw = self._disp_shape[1]
        return length * dw / gw if gw > 0 else None

    def _set_solve_text(self, text: str, color: str) -> None:
        self._solve_lbl.setText(text)
        self._solve_lbl.setStyleSheet(
            f"color:{color}; font-family:{theme.FONT_MONO};"
            f" font-size:11px; background:transparent;"
        )

    def closeEvent(self, event) -> None:
        if self._solver is not None and self._solver.isRunning():
            self._solver.wait(2000)
        super().closeEvent(event)
