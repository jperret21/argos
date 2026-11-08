"""Frame metrics and the conditions timeline (rows A26, A37).

- :class:`MetricsWorker`: one thread measures every frame on the **full
  resolution** array (S20 display side, Q-O14): ``frame_metrics`` (HFD of
  the brightest star, star count, sky, peak) and ``detect_stars`` (mean
  FWHM, eccentricity) of ``argos.core.imaging.metrics``, the measurements
  of ``PreviewProcessor`` (``preview_processor.py:58-123``). Latest frame
  wins: a frame still waiting when a newer one arrives is skipped.
- :class:`ConditionsLog`: one row per metered camera frame (live and
  single), with what the Qt HFD history and metrics panel showed
  (``hfd_history_dock.py:107-136``, ``metrics_panel.py:62-80``) plus the
  airmass from the mount and from the target, the temperatures and the
  focuser position; the last 20 000 rows of this server process.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from argos.core.imaging.metrics import detect_stars, frame_metrics
from argos.server.state import utc_iso

logger = logging.getLogger(__name__)

#: Rows kept in memory (``GET /api/session/conditions``).
MAX_ROWS = 20_000


@dataclass
class MetricsJob:
    seq: int
    arr: np.ndarray
    origin: str
    radius: int
    #: Context of a camera frame for its conditions row (``None``: no row).
    row: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def measure(arr: np.ndarray, radius: int) -> dict[str, Any]:
    """The ``FrameMetrics`` record of one frame (green-plane px)."""
    metrics = frame_metrics(arr)
    stars = detect_stars(arr, radius=radius)
    sky = float(metrics.sky_adu)
    return {
        "hfd_px": metrics.hfd,
        "fwhm_px": stars.mean_fwhm,
        "eccentricity": stars.mean_eccentricity,
        "star_count": int(metrics.star_count),
        "n_detected": int(stars.count),
        "sky_adu": round(sky, 2) if np.isfinite(sky) else None,
        "peak_adu": int(metrics.peak_adu),
        "star_radius_px": int(radius),
        "plane": "green",
    }


class MetricsWorker:
    """Latest-frame-wins measurement thread."""

    def __init__(self, on_result: Callable[[MetricsJob, dict[str, Any]], None]) -> None:
        self._on_result = on_result
        self._lock = threading.Lock()
        self._pending: MetricsJob | None = None
        self._wake = threading.Event()
        self._closed = False
        self._thread: threading.Thread | None = None
        #: Frames replaced before they were measured (diagnostics).
        self.skipped = 0

    def submit(self, job: MetricsJob) -> None:
        with self._lock:
            if self._closed:
                return
            if self._pending is not None:
                self.skipped += 1
            self._pending = job
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="argos-metrics", daemon=True)
                self._thread.start()
        self._wake.set()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._pending = None
        self._wake.set()

    def _run(self) -> None:
        while True:
            self._wake.wait(1.0)
            self._wake.clear()
            with self._lock:
                job, self._pending = self._pending, None
                if job is None:
                    if self._closed:
                        return
                    continue
            try:
                result = measure(job.arr, job.radius)
            except Exception:
                logger.warning("Frame metrics failed for frame %d", job.seq, exc_info=True)
                continue
            try:
                self._on_result(job, result)
            except Exception:
                logger.exception("Publishing frame metrics failed")


class ConditionsLog:
    """The conditions rows of this server process (``seq`` increasing)."""

    def __init__(self, capacity: int = MAX_ROWS) -> None:
        self._rows: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._seq = 0
        self._lock = threading.Lock()
        self.boot_id = uuid.uuid4().hex[:16]

    def append(self, row: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._seq += 1
            entry = {"type": "conditions", "seq": self._seq, **row}
            self._rows.append(entry)
            return dict(entry)

    def page(self, since_seq: int = 0, limit: int = 5000) -> dict[str, Any]:
        with self._lock:
            rows = [dict(r) for r in self._rows if r["seq"] > since_seq]
            first = self._rows[0]["seq"] if self._rows else None
            last = self._rows[-1]["seq"] if self._rows else None
        truncated = len(rows) > limit
        return {
            "rows": rows[:limit],
            "first_seq": first,
            "last_seq": last,
            "truncated": truncated,
            "boot_id": self.boot_id,
        }


def now_iso() -> str:
    return utc_iso()
