"""Display-rotation tests for FitsViewer (WS: landscape-by-default feature).

Rotation is display-only: the viewer's public API keeps speaking un-rotated
frame coordinates, so these tests pin (a) the array actually shown, (b) the
forward/inverse point mapping, and (c) that overlays land where the rotated
pixels went.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from argos.ui.widgets.fits_viewer import ROTATION_MODES, FitsViewer  # noqa: E402
from argos.ui.widgets.histogram_dock import HistogramDock  # noqa: E402


def _reap(app, *widgets) -> None:
    """Destroy widgets NOW — a half-dead pyqtgraph ViewBox left in the global
    ViewBox registry breaks unrelated tests later in the session."""
    for w in widgets:
        w.close()
        w.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


@pytest.fixture(scope="module")
def app():
    app = QApplication.instance() or QApplication(["test"])
    yield app


@pytest.fixture()
def viewer(app):
    v = FitsViewer()
    yield v
    _reap(app, v)


def _portrait() -> np.ndarray:
    # 40 rows × 20 cols, unique values so pixel identity is checkable.
    return np.arange(40 * 20, dtype=np.uint16).reshape(40, 20)


def test_auto_rotates_portrait_to_landscape(viewer):
    viewer.set_rotation("auto")
    viewer.display(_portrait())
    assert viewer._last_arr.shape == (20, 40)  # landscape on screen
    assert viewer._arr0.shape == (40, 20)  # original kept for the API


def test_auto_leaves_landscape_alone(viewer):
    viewer.set_rotation("auto")
    arr = np.zeros((20, 40), dtype=np.uint16)
    viewer.display(arr)
    assert viewer._rot_k == 0
    assert viewer._last_arr is arr


def test_fixed_angles(viewer):
    arr = _portrait()
    for mode, k in (("0", 0), ("90", 1), ("180", 2), ("270", 3)):
        viewer.set_rotation(mode)
        viewer.display(arr)
        assert viewer._rot_k == k
        expected = np.rot90(arr, -k)
        assert viewer._last_arr.shape == expected.shape
        assert np.array_equal(viewer._last_arr, expected)


def test_set_rotation_rerenders_last_frame(viewer):
    viewer.set_rotation("0")
    viewer.display(_portrait())
    assert viewer._last_arr.shape == (40, 20)
    viewer.set_rotation("90")  # no new frame — must re-derive from _arr0
    assert viewer._last_arr.shape == (20, 40)


@pytest.mark.parametrize("mode", ["90", "180", "270"])
def test_point_mapping_round_trip_and_pixel_identity(viewer, mode):
    arr = _portrait()
    viewer.set_rotation(mode)
    viewer.display(arr)
    for x, y in ((0, 0), (19, 39), (7, 31), (12, 5)):
        rx, ry = viewer._rot_pt(x, y)
        # The rotated coordinate must index the same pixel value…
        assert viewer._last_arr[int(ry), int(rx)] == arr[y, x]
        # …and the inverse must return home (public API round-trip).
        ux, uy = viewer._unrot_pt(rx, ry)
        assert (ux, uy) == (x, y)


def test_rot_pt_vectorized_for_grid_polylines(viewer):
    viewer.set_rotation("90")
    viewer.display(_portrait())
    xs = np.array([0.0, 10.0, 19.0])
    ys = np.array([0.0, 20.0, 39.0])
    rx, ry = viewer._rot_pt(xs, ys)
    assert rx.shape == xs.shape and ry.shape == ys.shape
    assert np.allclose(rx, (40 - 1) - ys)
    assert np.allclose(ry, xs)


def test_target_marker_lands_on_rotated_position(viewer):
    viewer.set_rotation("90")
    viewer.display(_portrait())
    viewer.set_target_enabled(True)
    # green shape == display shape here
    viewer.set_target_markers([(5.0, 30.0, "V1", "target")], (40, 20))
    pts = viewer._targets_item.points()
    assert len(pts) == 1
    pos = pts[0].pos()
    assert pos.x() == pytest.approx((40 - 1) - 30.0)
    assert pos.y() == pytest.approx(5.0)


def test_mark_selection_speaks_unrotated_coords(viewer):
    viewer.set_rotation("90")
    viewer.display(_portrait())
    viewer.mark_selection(5.0, 30.0, "x", show_label=False)
    pos = viewer._sel_center.points()[0].pos()
    assert pos.x() == pytest.approx((40 - 1) - 30.0)
    assert pos.y() == pytest.approx(5.0)


def test_reset_clears_rotation_source(viewer):
    viewer.set_rotation("auto")
    viewer.display(_portrait())
    viewer.reset()
    assert viewer._arr0 is None and viewer._last_arr is None


def test_histogram_dock_rotation_tokens(app):
    dock = HistogramDock()
    got: list[str] = []
    dock.rotation_changed.connect(got.append)
    # Start at 1: index 0 is already current so 0→0 emits nothing.
    for i in (1, 2, 3, 4, 0):
        dock._rot_combo.setCurrentIndex(i)
        assert got[-1] == ROTATION_MODES[i]
    # set_rotation_mode must sync silently (no re-emit).
    n = len(got)
    dock.set_rotation_mode("180")
    assert dock._rot_combo.currentIndex() == 3
    assert len(got) == n
    _reap(app, dock)
