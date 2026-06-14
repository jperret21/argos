"""FITS / raw image viewer (PyQtGraph) — display stretch + measurement tools.

Receives a **linear** display array (2-D uint16 plane or 3-D uint16 RGB from
``debayer.render_view``) and maps it to the screen through the stretch
(black/white/midtones + linear/log/asinh). The linear array is kept for
measurement (§4): pixel readout on hover, a region-stats ROI, and a
saturation/clipping overlay. None of this touches the data written to FITS.

Signals:
    levels_changed(black, white): emitted after an auto-stretch so the
        histogram dock can sync its sliders.
    pixel_info(str):   readout under the cursor ("(x,y) … ADU").
    region_info(dict|None): stats of the ROI region (or None when cleared).
"""

from __future__ import annotations

import logging

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from seercontrol.ui import theme
from seercontrol.core.imaging.stretch import (
    STRETCH_LINEAR,
    apply_stretch,
    auto_stf,
    region_stats,
)

logger = logging.getLogger(__name__)


class FitsViewer(QWidget):
    """Image viewer with non-destructive stretch + measurement overlays."""

    levels_changed = pyqtSignal(float, float, float)  # black, white, midtones
    region_info = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._last_arr: np.ndarray | None = None  # linear display array
        self._black: float = 0.0
        self._white: float = 65535.0
        self._mode: str = STRETCH_LINEAR
        self._midtones: float = 0.5
        self._auto_on: bool = True  # auto-level each frame until the user adjusts
        self._sat_enabled: bool = False
        self._sat_threshold: int = 60000
        self._roi: pg.RectROI | None = None
        self._crosshair: bool = True  # on by default so it's immediately visible
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        pg.setConfigOptions(imageAxisOrder="row-major")
        self._view = pg.ImageView()
        self._view.ui.roiBtn.hide()
        self._view.ui.menuBtn.hide()
        self._view.ui.histogram.hide()
        layout.addWidget(self._view)

        # Crosshair (toggleable) tracking the cursor over the image.
        self._vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(theme.WARNING, width=1))
        self._hline = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen(theme.WARNING, width=1))
        for line in (self._vline, self._hline):
            line.setVisible(self._crosshair)
            self._view.getView().addItem(line, ignoreBounds=True)

        # In-image pixel readout — a compact overlay pinned to the top-left,
        # so the value sits where you point instead of in a side column.
        self._readout = QLabel(self)
        self._readout.setStyleSheet(
            f"background: rgba(13,17,23,190); color: {theme.FG};"
            f" font-family: {theme.FONT_MONO}; font-size: 11px;"
            f" padding: 2px 7px; border-radius: 3px;"
        )
        self._readout.move(10, 10)
        self._readout.hide()

        self._view.scene.sigMouseMoved.connect(self._on_mouse_moved)

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def display(self, arr: np.ndarray) -> None:
        """Display a linear array (2-D uint16 plane or 3-D uint16 RGB)."""
        if arr.ndim not in (2, 3):
            return
        self._last_arr = arr
        if self._auto_on:
            self._black, self._white, self._midtones = auto_stf(arr)
            self.levels_changed.emit(self._black, self._white, self._midtones)
        if self._crosshair:  # centre it so it's visible before the mouse moves
            h, w = arr.shape[:2]
            self._vline.setPos(w / 2)
            self._hline.setPos(h / 2)
        self._render()
        if self._roi is not None:
            self._on_roi_changed()

    def _render(self) -> None:
        if self._last_arr is None:
            return
        disp = apply_stretch(self._last_arr, self._black, self._white, self._mode, self._midtones)
        if self._sat_enabled:
            disp = self._overlay_saturation(disp)
        self._view.setImage(
            disp,
            autoRange=False,
            autoLevels=False,
            autoHistogramRange=False,
            levels=(0, 255),
        )

    def _overlay_saturation(self, disp_u8: np.ndarray) -> np.ndarray:
        """Paint pixels at/above the full-well threshold red (display only)."""
        a = self._last_arr
        src = a if a.ndim == 2 else a.max(axis=2)
        mask = src >= self._sat_threshold
        if disp_u8.ndim == 2:
            rgb = np.repeat(disp_u8[:, :, None], 3, axis=2)
        else:
            rgb = disp_u8.copy()
        if mask.any():
            rgb[mask] = (255, 0, 0)
        return rgb

    # ------------------------------------------------------------------
    # Stretch controls (driven by the histogram dock)
    # ------------------------------------------------------------------

    def set_stretch(self, black: float, white: float, midtones: float, mode: str) -> None:
        self._auto_on = False
        self._black, self._white = float(black), float(white)
        self._midtones, self._mode = float(midtones), mode
        self._render()

    def auto_stretch(self) -> None:
        self._auto_on = True
        if self._last_arr is not None:
            self._black, self._white, self._midtones = auto_stf(self._last_arr)
            self.levels_changed.emit(self._black, self._white, self._midtones)
            self._render()

    def set_saturation(self, enabled: bool, threshold: int) -> None:
        self._sat_enabled = bool(enabled)
        self._sat_threshold = int(threshold)
        self._render()

    # ------------------------------------------------------------------
    # Region-stats ROI (§4)
    # ------------------------------------------------------------------

    def set_roi_enabled(self, enabled: bool) -> None:
        if enabled and self._roi is None:
            self._roi = pg.RectROI([10, 10], [80, 80], pen=pg.mkPen("y", width=1))
            self._view.getView().addItem(self._roi)
            self._roi.sigRegionChanged.connect(self._on_roi_changed)
            self._on_roi_changed()
        elif not enabled and self._roi is not None:
            self._view.getView().removeItem(self._roi)
            self._roi = None
            self.region_info.emit(None)

    def _on_roi_changed(self) -> None:
        if self._last_arr is None or self._roi is None:
            return
        pos, size = self._roi.pos(), self._roi.size()
        x0 = int(min(pos.x(), pos.x() + size.x()))
        x1 = int(max(pos.x(), pos.x() + size.x()))
        y0 = int(min(pos.y(), pos.y() + size.y()))
        y1 = int(max(pos.y(), pos.y() + size.y()))
        a = self._last_arr
        h, w = a.shape[:2]
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(w, x1), min(h, y1)
        if x1 <= x0 or y1 <= y0:
            return
        region = a[y0:y1, x0:x1]
        if region.ndim == 3:
            region = region.mean(axis=2)
        self.region_info.emit(region_stats(region))

    # ------------------------------------------------------------------
    # Pixel readout (§4)
    # ------------------------------------------------------------------

    def _on_mouse_moved(self, scene_pos) -> None:
        if self._last_arr is None:
            return
        p = self._view.getImageItem().mapFromScene(scene_pos)
        x, y = int(p.x()), int(p.y())
        a = self._last_arr
        h, w = a.shape[:2]
        if 0 <= x < w and 0 <= y < h:
            if self._crosshair:
                self._vline.setPos(p.x())
                self._hline.setPos(p.y())
            if a.ndim == 2:
                self._readout.setText(f"({x}, {y})   {int(a[y, x])} ADU")
            else:
                r, g, b = (int(v) for v in a[y, x][:3])
                self._readout.setText(f"({x}, {y})   R {r}  G {g}  B {b}")
            self._readout.adjustSize()
            self._readout.show()
            self._readout.raise_()
        else:
            self._readout.hide()

    def set_crosshair_enabled(self, enabled: bool) -> None:
        self._crosshair = bool(enabled)
        self._vline.setVisible(self._crosshair)
        self._hline.setVisible(self._crosshair)

    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset viewer state (call when switching targets)."""
        self._last_arr = None
        self._auto_on = True
        self._black, self._white = 0.0, 65535.0
        self._mode, self._midtones = STRETCH_LINEAR, 0.5
