"""PreviewProcessor — off-thread display compute so the preview never freezes.

The heavy per-frame work (debayer/render, star-detection metrics, per-channel
histograms) runs here on a QThread instead of the UI thread; the UI applies only
the cheap final stretch (kept on the UI thread so the sliders stay instant).
Latest-frame-wins: if frames arrive faster than they can be processed, stale
ones are dropped. See ``docs/capture_panel.md`` (threading note).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from seercontrol.core.imaging.debayer import render_view
from seercontrol.core.imaging.green import green_shape as _green_shape
from seercontrol.core.imaging.metrics import (
    DEFAULT_STAR_RADIUS,
    FrameMetrics,
    StarField,
    detect_stars,
    frame_metrics,
)
from seercontrol.core.imaging.stretch import channel_histograms

logger = logging.getLogger(__name__)

_HIST_BINS = 128


@dataclass
class ProcessedFrame:
    """Everything the UI needs to refresh, computed off the UI thread."""

    display: np.ndarray  # linear render for the viewer (2-D plane or 3-D RGB)
    metrics: FrameMetrics
    stars: StarField  # detected stars (green-plane coords) for the §5 overlay
    green_shape: tuple[int, int]  # (h, w) of the green plane the stars live in
    centers: np.ndarray
    r: np.ndarray
    g: np.ndarray
    b: np.ndarray
    lo: float
    hi: float
    vmin: float
    vmax: float
    vmean: float


def build_processed_frame(
    raw: np.ndarray, view: str, radius: int = DEFAULT_STAR_RADIUS
) -> ProcessedFrame:
    """Render + analyse one raw frame (Qt-free, reusable).

    Shared by the live :class:`PreviewProcessor` (off-thread) and the standalone
    analysis window (one-shot). Does the heavy work: debayer/render, frame
    metrics, star detection with the chosen aperture ``radius``, and per-channel
    histograms.
    """
    display = render_view(raw, view)
    metrics = frame_metrics(raw)
    stars = detect_stars(raw, radius=radius)
    green_shape = _green_shape(raw)
    lo = float(raw.min())
    hi = float(np.percentile(raw, 99.8))
    if hi <= lo:
        hi = float(raw.max()) if float(raw.max()) > lo else lo + 1.0
    centers, r, g, b = channel_histograms(raw, bins=_HIST_BINS, lo=lo, hi=hi)
    return ProcessedFrame(
        display=display,
        metrics=metrics,
        stars=stars,
        green_shape=green_shape,
        centers=centers,
        r=r,
        g=g,
        b=b,
        lo=lo,
        hi=hi,
        vmin=float(raw.min()),
        vmax=float(raw.max()),
        vmean=float(raw.mean()),
    )


class PreviewProcessor(QThread):
    """Processes the latest submitted (raw, view) and emits a ProcessedFrame."""

    ready = pyqtSignal(object)  # ProcessedFrame

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._lock = threading.Lock()
        self._event = threading.Event()
        self._job: tuple[np.ndarray, str] | None = None
        self._radius = DEFAULT_STAR_RADIUS
        self._stop = False

    def set_radius(self, radius: int) -> None:
        """Set the star-measurement aperture radius for subsequent frames (§5)."""
        self._radius = max(2, int(radius))

    def submit(self, raw: np.ndarray, view: str) -> None:
        """Queue a frame for processing (replaces any pending frame)."""
        with self._lock:
            self._job = (raw, view)
        self._event.set()

    def stop(self) -> None:
        self._stop = True
        self._event.set()

    def run(self) -> None:
        while not self._stop:
            self._event.wait()
            if self._stop:
                break
            with self._lock:
                job = self._job
                self._job = None
                self._event.clear()
            if job is None:
                continue
            try:
                raw, view = job
                self.ready.emit(build_processed_frame(raw, view, self._radius))
            except Exception:  # pragma: no cover - never let a bad frame kill the thread
                logger.exception("Preview processing failed")
