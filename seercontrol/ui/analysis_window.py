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
    measure_star_at,
)
from seercontrol.core.imaging.platesolve import (
    SolveSettings,
    format_dec_dms,
    format_ra_hms,
    frame_wcs,
    wcs_grid,
)
from seercontrol.ui import theme
from seercontrol.ui.widgets.fits_viewer import FitsViewer
from seercontrol.ui.widgets.histogram_dock import HistogramDock
from seercontrol.ui.widgets.image_toolbar import ImageToolbar
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

        self._toolbar = ImageToolbar()
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
        self._histogram.saturation_toggled.connect(
            lambda on: self._viewer.set_saturation(on, 60000)
        )
        self._histogram.roi_toggled.connect(self._viewer.set_roi_enabled)
        self._histogram.crosshair_toggled.connect(self._viewer.set_crosshair_enabled)
        self._histogram.stars_overlay_toggled.connect(self._viewer.set_star_overlay_enabled)
        self._histogram.loupe_toggled.connect(self._viewer.set_loupe_enabled)
        self._histogram.astrometry_toggled.connect(self._viewer.set_astrometry_enabled)
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
        self._histogram.set_astrometry_available(False)
        self._histogram.set_astrometry_checked(False)
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

    def _on_solve(self) -> None:
        if self._raw is None or (self._solver is not None and self._solver.isRunning()):
            return
        green = extract_plane(self._raw, VIEW_G)
        gh = green.shape[0]
        use_hint = bool(self._cfg("astrometry.use_scale_hint", True))
        settings = SolveSettings(
            astap_path=str(self._cfg("astrometry.astap_path", "")),
            database=str(self._cfg("astrometry.database", "")),
            search_radius_deg=float(self._cfg("astrometry.search_radius_deg", 30)),
            downsample=int(self._cfg("astrometry.downsample", 2)),
            fov_hint_deg=(gh * ARCSEC_PER_GREEN_PX / 3600.0) if use_hint else None,
        )
        self._solve_btn.setEnabled(False)
        self._set_solve_text("solving… (ASTAP)", theme.WARNING)
        self._solver = SolveWorker(green, settings, parent=self)
        self._solver.solved.connect(self._on_solved)
        self._solver.start()

    def _on_solved(self, result) -> None:
        self._solve_btn.setEnabled(True)
        if not result.solved:
            self._set_solve_text(f"✗ {result.message}", theme.DANGER)
            return
        bits = [f"✓ RA {result.ra_hours:.4f}h", f"Dec {result.dec_deg:+.4f}°"]
        if result.scale_arcsec:  # ASTAP solved the green plane → ÷2 for full-res
            bits.append(f"{result.scale_arcsec / 2:.2f}″/px")
        if result.rotation_deg is not None:
            bits.append(f"rot {result.rotation_deg:.1f}°")
        if result.mirrored:
            bits.append("mirrored")
        self._set_solve_text("   ".join(bits), theme.SUCCESS)

        # Build the WCS → enable the grid overlay + per-star RA/Dec readout.
        self._wcs = frame_wcs(result.fields, self._green_shape)
        if self._wcs is not None:
            self._update_astrometry_overlay()
            self._viewer.set_astrometry_enabled(True)
            self._histogram.set_astrometry_available(True)
            self._histogram.set_astrometry_checked(True)
            self._remeasure_selection()  # refresh the clicked star's RA/Dec

    def _update_astrometry_overlay(self) -> None:
        if self._wcs is None or self._green_shape is None:
            self._viewer.set_astrometry_overlay(None, self._green_shape)
            return
        overlay = wcs_grid(self._wcs, self._green_shape)
        self._viewer.set_astrometry_overlay(overlay, self._green_shape)

    def _set_solve_text(self, text: str, color: str) -> None:
        self._solve_lbl.setText(text)
        self._solve_lbl.setStyleSheet(
            f"color:{color}; font-family:{theme.FONT_MONO}; font-size:11px; background:transparent;"
        )

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if self._solver is not None and self._solver.isRunning():
            self._solver.wait(2000)
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Click-to-measure (§5)
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
            self._raw, self._selected_green[0], self._selected_green[1], self._radius
        )
        if meas is not None:
            self._selected_green = (meas.x, meas.y)
            self._show_selection(meas)

    def _show_selection(self, meas) -> None:
        dp = self._green_to_disp(meas.x, meas.y)
        if dp is None:
            return
        self._viewer.mark_selection(dp[0], dp[1], self._format_star_text(meas))

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
