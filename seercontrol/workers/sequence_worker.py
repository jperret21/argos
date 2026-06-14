"""SequenceWorker — executes a multi-step acquisition plan in a QThread.

Consumes a :class:`~seercontrol.core.imaging.sequencer.SequencePlan`, expands it
to frames, drives the camera/filter wheel, and writes science-grade FITS files
into the Siril-compatible session folder. All blocking work (network, disk,
polling) happens here, off the UI thread; the UI subscribes to the signals.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QThread, pyqtSignal

from seercontrol.core.alpaca.camera import Camera
from seercontrol.core.alpaca.client import AlpacaError
from seercontrol.core.alpaca.filterwheel import POSITION_NAMES, FilterWheel
from seercontrol.core.alpaca.telescope import Telescope
from seercontrol.core.imaging.debayer import compute_hfd
from seercontrol.core.imaging.fits_writer import FITSWriter, FrameContext
from seercontrol.core.imaging.sequencer import (
    FrameSpec,
    SequencePlan,
    expand_plan,
    total_frames,
)

logger = logging.getLogger(__name__)

#: Extra time on top of the exposure before a frame is considered timed out.
_DOWNLOAD_MARGIN_S = 15.0
#: Polling interval while waiting for ImageReady.
_POLL_MS = 200

#: Callback that builds a fresh FrameContext for the current frame. Called with
#: keyword args ``object_name`` and ``filter_name``; returns a FrameContext.
FrameContextProvider = Callable[..., FrameContext]


def _resolve_filter_position(filter_name: str) -> int | None:
    """Best-effort map of a filter name to a wheel position index.

    ``POSITION_NAMES`` may be a list (index → name) or a dict (index → name);
    both are handled. Returns ``None`` when no match is found.
    """
    try:
        if isinstance(POSITION_NAMES, dict):
            for idx, name in POSITION_NAMES.items():
                if str(name).lower() == filter_name.lower():
                    return int(idx)
        else:
            for idx, name in enumerate(POSITION_NAMES):
                if str(name).lower() == filter_name.lower():
                    return idx
    except Exception:  # pragma: no cover - defensive against unexpected shapes
        return None
    return None


class SequenceWorker(QThread):
    """Runs a :class:`SequencePlan` to completion (or until stopped).

    Signals:
        step_started(int, object):       step_index, SequenceStep — a new step begins.
        frame_started(int, int, object): frames_done, total, FrameSpec — before exposing.
        frame_saved(str, object):        absolute path, hfd|None — a frame was written.
        progress(int, int, float):       frames_done, total, eta_seconds.
        autofocus_due():                 the controller should run autofocus, then call
                                         :meth:`resume_after_autofocus`.
        error_occurred(str):             a recoverable/terminal error message.
        finished(bool):                  True if the plan completed fully, else False.
    """

    step_started = pyqtSignal(int, object)
    frame_started = pyqtSignal(int, int, object)
    frame_saved = pyqtSignal(str, object)
    progress = pyqtSignal(int, int, float)
    frame_image = pyqtSignal(object)  # full uint16 array, for live display
    autofocus_due = pyqtSignal()
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal(bool)

    def __init__(
        self,
        camera: Camera,
        telescope: Telescope | None,
        filterwheel: FilterWheel | None,
        plan: SequencePlan,
        frame_context_provider: FrameContextProvider,
        base_dir: Path,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._camera = camera
        self._telescope = telescope
        self._filterwheel = filterwheel
        self._plan = plan
        self._make_context = frame_context_provider
        self._base_dir = Path(base_dir)
        self._stop_flag = False
        self._resume = threading.Event()

    # ------------------------------------------------------------------ #
    # Control
    # ------------------------------------------------------------------ #

    def stop(self) -> None:
        """Request a clean stop; also unblocks an autofocus wait."""
        self._stop_flag = True
        self._resume.set()

    def resume_after_autofocus(self) -> None:
        """Resume the loop after the controller has finished autofocus."""
        self._resume.set()

    # ------------------------------------------------------------------ #
    # Thread body
    # ------------------------------------------------------------------ #

    def run(self) -> None:
        completed = False
        try:
            completed = self._run()
        except AlpacaError as exc:
            self.error_occurred.emit(str(exc))
        except Exception as exc:  # pragma: no cover - safety net
            logger.exception("Sequence error")
            self.error_occurred.emit(str(exc))
        finally:
            self.finished.emit(completed)

    def _run(self) -> bool:
        total = total_frames(self._plan)
        done = 0
        started = time.monotonic()
        current_filter: str | None = None
        current_step = -1
        frames_since_af = 0

        logger.info("Sequence start: %d frame(s) → %s", total, self._base_dir)

        for spec in expand_plan(self._plan):
            if self._stop_flag:
                return False

            if spec.step_index != current_step:
                current_step = spec.step_index
                self.step_started.emit(current_step, self._plan.steps[current_step])

            # Filter change (Light/Flat only).
            if (
                spec.needs_filter
                and self._filterwheel is not None
                and spec.filter_name != current_filter
            ):
                self._set_filter(spec.filter_name)
                if current_filter is not None and self._plan.autofocus_on_filter_change:
                    self._await_autofocus()
                    frames_since_af = 0
                    if self._stop_flag:
                        return False
                current_filter = spec.filter_name

            # Periodic autofocus.
            if self._plan.autofocus_every_n > 0 and frames_since_af >= self._plan.autofocus_every_n:
                self._await_autofocus()
                frames_since_af = 0
                if self._stop_flag:
                    return False

            self.frame_started.emit(done, total, spec)
            path, hfd = self._shoot_one(spec)
            if path is None:
                return False  # stop requested or error already emitted

            done += 1
            frames_since_af += 1
            self.frame_saved.emit(path, hfd)

            elapsed = time.monotonic() - started
            avg = elapsed / done
            self.progress.emit(done, total, avg * (total - done))

            if spec.dither_every:
                logger.info("Dithering requested but unsupported on Seestar (no guiding) — skipped")

            if spec.interval_s > 0 and not self._interruptible_sleep(spec.interval_s):
                return False

        return not self._stop_flag

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _set_filter(self, filter_name: str) -> None:
        pos = _resolve_filter_position(filter_name)
        if pos is None:
            logger.warning("No wheel position matches filter '%s' — skipping", filter_name)
            return
        self._filterwheel.set_position(pos)

    def _shoot_one(self, spec: FrameSpec) -> tuple[str | None, float | None]:
        """Expose, wait for ImageReady, write the FITS. Returns (path, hfd)."""
        start_dt = datetime.now(timezone.utc)
        self._camera.set_gain(spec.gain)
        self._camera.start_exposure(spec.exposure_s, light=spec.is_light)

        deadline = time.monotonic() + spec.exposure_s + _DOWNLOAD_MARGIN_S
        while not self._camera.is_image_ready():
            if self._stop_flag:
                self._safe_stop_exposure()
                return None, None
            if time.monotonic() > deadline:
                self.error_occurred.emit(
                    f"Exposure timeout after {spec.exposure_s + _DOWNLOAD_MARGIN_S:.0f}s"
                )
                return None, None
            self.msleep(_POLL_MS)

        arr = self._camera.get_image_array()
        end_dt = datetime.now(timezone.utc)
        self.frame_image.emit(arr)

        ctx = self._make_context(object_name=self._plan.object_name, filter_name=spec.filter_name)
        folder = FITSWriter.session_folder(
            self._base_dir, self._plan.object_name, start_dt, spec.image_type, spec.filter_name
        )
        filename = FITSWriter.build_filename(
            self._plan.object_name,
            spec.image_type,
            start_dt,
            spec.exposure_s,
            spec.filter_name,
            spec.frame_index,
        )
        path = folder / filename
        FITSWriter.write(
            arr, path, start_dt, end_dt, spec.exposure_s, spec.gain, spec.image_type, context=ctx
        )

        hfd: float | None = None
        if spec.is_light:
            try:
                hfd = compute_hfd(arr)
            except Exception:  # pragma: no cover - HFD is best-effort
                hfd = None
        return str(path), hfd

    def _safe_stop_exposure(self) -> None:
        try:
            self._camera.stop_exposure()
        except Exception:  # pragma: no cover - best effort on abort
            pass

    def _await_autofocus(self) -> None:
        """Signal the controller and block until resumed (or stopped)."""
        self._resume.clear()
        self.autofocus_due.emit()
        self._resume.wait()  # set by resume_after_autofocus() or stop()

    def _interruptible_sleep(self, seconds: float) -> bool:
        """Sleep in small slices; return False if a stop was requested."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self._stop_flag:
                return False
            self.msleep(_POLL_MS)
        return True
