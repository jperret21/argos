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
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from seercontrol.ui import theme
from seercontrol.core.imaging.stretch import (
    STRETCH_LINEAR,
    apply_stretch,
    auto_stf,
    region_stats,
)

logger = logging.getLogger(__name__)

#: Loupe: on-screen size (px) and the source window it magnifies (display px).
_LOUPE_PX = 168
_LOUPE_SRC = 42


def _to_qimage(arr: np.ndarray) -> QImage:
    """Build a QImage from a uint8 grayscale (H,W) or RGB (H,W,3) array."""
    arr = np.ascontiguousarray(arr)
    h, w = arr.shape[:2]
    if arr.ndim == 2:
        return QImage(arr.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
    return QImage(arr.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


class FitsViewer(QWidget):
    """Image viewer with non-destructive stretch + measurement overlays."""

    levels_changed = pyqtSignal(float, float, float)  # black, white, midtones
    region_info = pyqtSignal(object)
    star_clicked = pyqtSignal(float, float)  # display-px (x, y) of a click

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
        self._crosshair: bool = False  # off by default; when on, follows the cursor only
        self._disp_u8: np.ndarray | None = None  # last stretched display (for the loupe)
        # §5 focus tools: star/FWHM overlay + 100% loupe.
        self._stars: tuple = ()
        self._green_shape: tuple[int, int] | None = None
        self._star_overlay: bool = False
        self._loupe: bool = False
        # §6 astrometry overlay: RA/Dec grid + field-centre + target reticle.
        self._wcs_overlay = None  # platesolve.WCSOverlay (green-plane coords)
        self._wcs_on: bool = False
        # §6 catalog overlay: VSX variable-star markers (green-plane coords).
        self._catalog: tuple = ()  # (x_green, y_green, suspected) per object
        self._catalog_on: bool = False
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

        # Crosshair (toggleable) — only shown while the cursor is over the image
        # (it never parks in the centre at rest).
        self._vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(theme.WARNING, width=1))
        self._hline = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen(theme.WARNING, width=1))
        for line in (self._vline, self._hline):
            line.setVisible(False)
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

        # §5 star/FWHM overlay — hollow rings on detected stars (size ∝ FWHM).
        self._scatter = pg.ScatterPlotItem(
            pen=pg.mkPen(theme.SUCCESS, width=1), brush=None, pxMode=True, size=14
        )
        self._scatter.setVisible(False)
        self._view.getView().addItem(self._scatter, ignoreBounds=True)

        # §5 selected-star highlight: a ring drawn at the *actual* measurement
        # aperture (data-space, so it grows/shrinks with the radius) around a
        # small fixed centre dot — plus a readout pinned bottom-left.
        self._sel_ring = pg.PlotDataItem(pen=pg.mkPen(theme.ACCENT, width=2))
        self._sel_ring.setVisible(False)
        self._view.getView().addItem(self._sel_ring, ignoreBounds=True)
        self._sel_center = pg.ScatterPlotItem(
            pen=None, brush=pg.mkBrush(theme.ACCENT), pxMode=True, size=6, symbol="o"
        )
        self._sel_center.setVisible(False)
        self._view.getView().addItem(self._sel_center, ignoreBounds=True)

        self._sel_label = QLabel(self)
        self._sel_label.setStyleSheet(
            f"background: rgba(13,17,23,205); color: {theme.FG};"
            f" font-family: {theme.FONT_MONO}; font-size: 11px;"
            f" padding: 4px 8px; border-radius: 3px; border: 1px solid {theme.ACCENT};"
        )
        self._sel_label.hide()

        # §5 loupe — a magnified 1:1 inset following the cursor (top-right).
        self._loupe_label = QLabel(self)
        self._loupe_label.setFixedSize(_LOUPE_PX, _LOUPE_PX)
        self._loupe_label.setStyleSheet(f"background: #000; border: 1px solid {theme.WARNING};")
        self._loupe_label.hide()

        # §6 astrometry overlay — RA/Dec grid (one NaN-broken curve) and an
        # optional target reticle. The solved centre RA/Dec is shown as text (no
        # centre marker). All hidden until a solve provides a WCS and it's on.
        self._grid_item = pg.PlotDataItem(
            pen=pg.mkPen(theme.ACCENT, width=1, style=Qt.PenStyle.DotLine)
        )
        self._grid_item.setVisible(False)
        self._view.getView().addItem(self._grid_item, ignoreBounds=True)
        self._target_item = pg.PlotDataItem(pen=pg.mkPen(theme.SUCCESS, width=2))
        self._target_item.setVisible(False)
        self._view.getView().addItem(self._target_item, ignoreBounds=True)

        # §6 catalog overlay — VSX variable stars as hollow diamonds (purple).
        # Per-spot pen lets suspected variables render dashed/dimmer.
        self._catalog_item = pg.ScatterPlotItem(brush=None, pxMode=True, size=18, symbol="d")
        self._catalog_item.setVisible(False)
        self._view.getView().addItem(self._catalog_item, ignoreBounds=True)
        self._astro_label = QLabel(self)
        self._astro_label.setStyleSheet(
            f"background: rgba(13,17,23,205); color: {theme.FG};"
            f" font-family: {theme.FONT_MONO}; font-size: 11px;"
            f" padding: 3px 7px; border-radius: 3px; border: 1px solid {theme.ACCENT};"
        )
        self._astro_label.hide()

        self._view.scene.sigMouseMoved.connect(self._on_mouse_moved)
        self._view.scene.sigMouseClicked.connect(self._on_mouse_clicked)

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
        self._render()
        self._refresh_overlay()
        self._refresh_astrometry()
        self._refresh_catalog()
        if self._roi is not None:
            self._on_roi_changed()

    def _render(self) -> None:
        if self._last_arr is None:
            return
        disp = apply_stretch(self._last_arr, self._black, self._white, self._mode, self._midtones)
        if self._sat_enabled:
            disp = self._overlay_saturation(disp)
        self._disp_u8 = disp  # kept for the loupe (what the eye sees)
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
                self._vline.setVisible(True)
                self._hline.setVisible(True)
            if a.ndim == 2:
                self._readout.setText(f"({x}, {y})   {int(a[y, x])} ADU")
            else:
                r, g, b = (int(v) for v in a[y, x][:3])
                self._readout.setText(f"({x}, {y})   R {r}  G {g}  B {b}")
            self._readout.adjustSize()
            self._readout.show()
            self._readout.raise_()
            if self._loupe:
                self._update_loupe(x, y)
        else:
            self._readout.hide()
            self._vline.setVisible(False)
            self._hline.setVisible(False)
            if self._loupe:
                self._loupe_label.hide()

    def set_crosshair_enabled(self, enabled: bool) -> None:
        # Only toggles the feature; the lines appear on hover, never at rest.
        self._crosshair = bool(enabled)
        if not self._crosshair:
            self._vline.setVisible(False)
            self._hline.setVisible(False)

    # ------------------------------------------------------------------
    # Focus tools (§5): star/FWHM overlay + 100% loupe
    # ------------------------------------------------------------------

    def set_stars(self, starfield, green_shape: tuple[int, int]) -> None:
        """Receive detected stars (green-plane coords) for the overlay."""
        self._stars = tuple(getattr(starfield, "stars", ()) or ())
        self._green_shape = green_shape
        self._refresh_overlay()

    def set_star_overlay_enabled(self, enabled: bool) -> None:
        self._star_overlay = bool(enabled)
        self._refresh_overlay()

    def _refresh_overlay(self) -> None:
        """Redraw star rings, scaled from green-plane to the active view."""
        if not (self._star_overlay and self._stars and self._last_arr is not None):
            self._scatter.setVisible(False)
            return
        gh, gw = self._green_shape or (0, 0)
        if gh <= 0 or gw <= 0:
            self._scatter.setVisible(False)
            return
        dh, dw = self._last_arr.shape[:2]
        sx, sy = dw / gw, dh / gh  # green-plane → display px (×1 super-pixel, ×2 raw)
        spots = []
        for s in self._stars:
            size = float(np.clip(10.0 + s.fwhm * 2.0, 10.0, 36.0))
            spots.append({"pos": (s.x * sx, s.y * sy), "size": size})
        self._scatter.setData(spots)
        self._scatter.setVisible(True)

    # ------------------------------------------------------------------
    # Astrometry overlay (§6): RA/Dec grid + field centre + target reticle
    # ------------------------------------------------------------------

    def set_astrometry_overlay(self, overlay, green_shape: tuple[int, int] | None = None) -> None:
        """Receive grid/centre/target geometry (green-plane coords) from a solve."""
        self._wcs_overlay = overlay
        if green_shape is not None:
            self._green_shape = green_shape
        self._refresh_astrometry()

    def set_astrometry_enabled(self, enabled: bool) -> None:
        self._wcs_on = bool(enabled)
        self._refresh_astrometry()

    def _refresh_astrometry(self) -> None:
        """Redraw the WCS grid/centre/target, scaled green-plane → active view."""
        ov = self._wcs_overlay
        show = self._wcs_on and ov is not None and self._last_arr is not None
        gh, gw = self._green_shape or (0, 0)
        if not show or gh <= 0 or gw <= 0:
            self._grid_item.setVisible(False)
            self._target_item.setVisible(False)
            self._astro_label.hide()
            return
        dh, dw = self._last_arr.shape[:2]
        sx, sy = dw / gw, dh / gh  # green-plane px → display px

        xs_parts, ys_parts = [], []
        gap = np.array([np.nan])
        for xs, ys in ov.lines:
            xs_parts.extend((np.asarray(xs, dtype=float) * sx, gap))
            ys_parts.extend((np.asarray(ys, dtype=float) * sy, gap))
        if xs_parts:
            self._grid_item.setData(
                np.concatenate(xs_parts), np.concatenate(ys_parts), connect="finite"
            )
            self._grid_item.setVisible(True)
        else:
            self._grid_item.setVisible(False)

        if ov.target is not None:
            tx, ty = ov.target[0] * sx, ov.target[1] * sy
            rr = 0.05 * min(dw, dh)
            th = np.linspace(0.0, 2.0 * np.pi, 49)
            self._target_item.setData(tx + rr * np.cos(th), ty + rr * np.sin(th))
            self._target_item.setVisible(True)
        else:
            self._target_item.setVisible(False)

        if ov.center_label:
            self._astro_label.setText(ov.center_label)
            self._astro_label.adjustSize()
            self._astro_label.move(10, 36)
            self._astro_label.show()
            self._astro_label.raise_()
        else:
            self._astro_label.hide()

    # ------------------------------------------------------------------
    # Catalog overlay (§6): VSX variable-star markers
    # ------------------------------------------------------------------

    def set_catalog_markers(self, points, green_shape: tuple[int, int] | None = None) -> None:
        """Receive variable-star marker positions (green-plane coords).

        ``points`` is an iterable of ``(x_green, y_green, suspected)`` tuples.
        """
        self._catalog = tuple(points or ())
        if green_shape is not None:
            self._green_shape = green_shape
        self._refresh_catalog()

    def set_catalog_enabled(self, enabled: bool) -> None:
        self._catalog_on = bool(enabled)
        self._refresh_catalog()

    def _refresh_catalog(self) -> None:
        """Redraw variable-star diamonds, scaled green-plane → active view."""
        if not (self._catalog_on and self._catalog and self._last_arr is not None):
            self._catalog_item.setVisible(False)
            return
        gh, gw = self._green_shape or (0, 0)
        if gh <= 0 or gw <= 0:
            self._catalog_item.setVisible(False)
            return
        dh, dw = self._last_arr.shape[:2]
        sx, sy = dw / gw, dh / gh  # green-plane px → display px
        confirmed = pg.mkPen(theme.VARIABLE, width=2)
        suspected = pg.mkPen(theme.VARIABLE, width=1, style=Qt.PenStyle.DashLine)
        spots = [
            {"pos": (x * sx, y * sy), "pen": (suspected if s else confirmed)}
            for (x, y, s) in self._catalog
        ]
        self._catalog_item.setData(spots)
        self._catalog_item.setVisible(True)

    def set_loupe_enabled(self, enabled: bool) -> None:
        self._loupe = bool(enabled)
        if not self._loupe:
            self._loupe_label.hide()

    def _on_mouse_clicked(self, ev) -> None:
        """Left-click on the image → emit the display-px position to measure."""
        if self._last_arr is None:
            return
        try:
            if ev.button() != Qt.MouseButton.LeftButton:
                return
        except Exception:  # pragma: no cover - defensive against event shape
            pass
        p = self._view.getImageItem().mapFromScene(ev.scenePos())
        x, y = p.x(), p.y()
        h, w = self._last_arr.shape[:2]
        if 0 <= x < w and 0 <= y < h:
            self.star_clicked.emit(float(x), float(y))

    def mark_selection(
        self, x_disp: float, y_disp: float, text: str, radius_disp: float | None = None
    ) -> None:
        """Mark the selection at display px (x, y) and show its readout.

        ``radius_disp`` (display px) draws the measurement aperture as a ring
        around the centre dot; ``None`` (e.g. a catalog pick) shows the dot only.
        """
        self._sel_center.setData([{"pos": (x_disp, y_disp), "size": 6}])
        self._sel_center.setVisible(True)
        if radius_disp is not None and radius_disp > 0:
            th = np.linspace(0.0, 2.0 * np.pi, 60)
            self._sel_ring.setData(
                x_disp + radius_disp * np.cos(th), y_disp + radius_disp * np.sin(th)
            )
            self._sel_ring.setVisible(True)
        else:
            self._sel_ring.setVisible(False)
        self._sel_label.setText(text)
        self._sel_label.adjustSize()
        self._sel_label.move(10, max(10, self.height() - self._sel_label.height() - 10))
        self._sel_label.show()
        self._sel_label.raise_()

    def clear_selection(self) -> None:
        self._sel_ring.setVisible(False)
        self._sel_center.setVisible(False)
        self._sel_label.hide()

    def _update_loupe(self, cx: int, cy: int) -> None:
        """Refresh the 1:1 magnified inset centred on display pixel (cx, cy)."""
        disp = self._disp_u8
        if disp is None:
            self._loupe_label.hide()
            return
        h, w = disp.shape[:2]
        r = _LOUPE_SRC // 2
        # Fixed-size source window, zero-padded near the edges.
        if disp.ndim == 2:
            crop = np.zeros((_LOUPE_SRC, _LOUPE_SRC), dtype=np.uint8)
        else:
            crop = np.zeros((_LOUPE_SRC, _LOUPE_SRC, 3), dtype=np.uint8)
        sx0, sy0 = max(0, cx - r), max(0, cy - r)
        sx1, sy1 = min(w, cx - r + _LOUPE_SRC), min(h, cy - r + _LOUPE_SRC)
        if sx1 <= sx0 or sy1 <= sy0:
            self._loupe_label.hide()
            return
        dx0, dy0 = sx0 - (cx - r), sy0 - (cy - r)
        crop[dy0 : dy0 + (sy1 - sy0), dx0 : dx0 + (sx1 - sx0)] = disp[sy0:sy1, sx0:sx1]

        pix = QPixmap.fromImage(_to_qimage(crop)).scaled(
            _LOUPE_PX,
            _LOUPE_PX,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,  # nearest-neighbour → real pixels
        )
        self._draw_loupe_crosshair(pix)
        self._loupe_label.setPixmap(pix)
        self._loupe_label.move(self.width() - _LOUPE_PX - 10, 10)
        self._loupe_label.show()
        self._loupe_label.raise_()

    @staticmethod
    def _draw_loupe_crosshair(pix: QPixmap) -> None:
        painter = QPainter(pix)
        painter.setPen(QPen(QColor(theme.WARNING), 1))
        mid = _LOUPE_PX // 2
        painter.drawLine(mid, 0, mid, _LOUPE_PX)
        painter.drawLine(0, mid, _LOUPE_PX, mid)
        painter.end()

    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset viewer state (call when switching targets)."""
        self._last_arr = None
        self._disp_u8 = None
        self._stars = ()
        self._scatter.setVisible(False)
        self._loupe_label.hide()
        self._wcs_overlay = None
        self._refresh_astrometry()
        self._catalog = ()
        self._refresh_catalog()
        self.clear_selection()
        self._auto_on = True
        self._black, self._white = 0.0, 65535.0
        self._mode, self._midtones = STRETCH_LINEAR, 0.5
