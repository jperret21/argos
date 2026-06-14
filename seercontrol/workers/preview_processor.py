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
from seercontrol.core.imaging.metrics import FrameMetrics, frame_metrics
from seercontrol.core.imaging.stretch import channel_histograms

logger = logging.getLogger(__name__)

_HIST_BINS = 128


@dataclass
class ProcessedFrame:
    """Everything the UI needs to refresh, computed off the UI thread."""

    display: np.ndarray  # linear render for the viewer (2-D plane or 3-D RGB)
    metrics: FrameMetrics
    centers: np.ndarray
    r: np.ndarray
    g: np.ndarray
    b: np.ndarray
    lo: float
    hi: float
    vmin: float
    vmax: float
    vmean: float


class PreviewProcessor(QThread):
    """Processes the latest submitted (raw, view) and emits a ProcessedFrame."""

    ready = pyqtSignal(object)  # ProcessedFrame

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._lock = threading.Lock()
        self._event = threading.Event()
        self._job: tuple[np.ndarray, str] | None = None
        self._stop = False

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
                self.ready.emit(self._process(*job))
            except Exception:  # pragma: no cover - never let a bad frame kill the thread
                logger.exception("Preview processing failed")

    def _process(self, raw: np.ndarray, view: str) -> ProcessedFrame:
        display = render_view(raw, view)
        metrics = frame_metrics(raw)
        lo = float(raw.min())
        hi = float(np.percentile(raw, 99.8))
        if hi <= lo:
            hi = float(raw.max()) if float(raw.max()) > lo else lo + 1.0
        centers, r, g, b = channel_histograms(raw, bins=_HIST_BINS, lo=lo, hi=hi)
        return ProcessedFrame(
            display=display,
            metrics=metrics,
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
