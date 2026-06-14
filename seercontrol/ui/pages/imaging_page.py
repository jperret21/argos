"""Acquisition mode — the work surface where most session time is spent.

Layout::

    ┌─ ImageToolbar (View · Open FITS · "display ≠ data") ───────────┐
    ├──────────────────────────────────────────┬───────────────────┤
    │   FitsViewer (hero) + crosshair + pixel  │  Rail tabs:        │
    │   readout overlay                        │  Capture · Sequence│
    ├──────────────────────────────────────────┤  · Mount · Focus   │
    │   Stats bar: HFD·Stars·Sky·Min·Max·Mean  │  · Display         │
    ├──────────────────────────────────────────┴───────────────────┤
    │                     Session log                                │
    └────────────────────────────────────────────────────────────────┘

The page owns the device handles (Telescope, Camera, Focuser) and orchestrates
the workers (Discovery, MountPolling, LivePreview, Autofocus, Sequence). The
Connection page emits connect/disconnect intents that the Shell routes to the
public ``connect_*`` / ``disconnect_*`` / ``start_discovery`` methods here.

Upward signals the Shell wires into the global status bar + Connection page:

    device_state_changed(device, state, info)
    tracking_changed(bool | None)
    action_changed(text)
    log_message(level, message)
    discovered_address(host, port)
    position_updated(ra_h, dec_d, slewing)      # feeds the Stellarium reticle
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QRunnable, Qt, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from seercontrol.core.alpaca.camera import Camera
from seercontrol.core.alpaca.client import AlpacaError
from seercontrol.core.alpaca.focuser import Focuser
from seercontrol.core.alpaca.telescope import MountPosition, Telescope
from seercontrol.core.config import Config
from seercontrol.core.imaging.debayer import VIEW_RAW, VIEW_SUPERPIXEL
from seercontrol.core.imaging.fits_writer import FITSWriter, FrameContext
from seercontrol.ui import design, theme
from seercontrol.ui.panels.log_panel import LogPanel
from seercontrol.ui.panels.manual_control_dialog import ManualControlDialog
from seercontrol.ui.widgets.camera_dock import CameraDock
from seercontrol.ui.widgets.fits_viewer import FitsViewer
from seercontrol.ui.widgets.focuser_dock import FocuserDock
from seercontrol.ui.widgets.histogram_dock import HistogramDock
from seercontrol.ui.widgets.image_toolbar import ImageToolbar
from seercontrol.ui.widgets.mount_dock import MountDock
from seercontrol.ui.widgets.sequence_panel import SequencePanel
from seercontrol.workers.autofocus_worker import AutofocusWorker
from seercontrol.workers.discovery_worker import DiscoveryWorker
from seercontrol.workers.exposure_worker import LivePreviewWorker
from seercontrol.workers.polling_worker import MountPollingWorker
from seercontrol.workers.preview_processor import PreviewProcessor
from seercontrol.workers.sequence_worker import SequenceWorker

logger = logging.getLogger(__name__)

_SOFTWARE = "SeerControl v0.2.0-redesign"

#: Live frame stats shown in the always-visible bar under the image.
_STAT_KEYS = ("HFD", "Stars", "Sky", "Min", "Max", "Mean")


def _stat_key(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color:{theme.FG_MUTED}; font-size:11px; background:transparent;")
    return lbl


class _JogRunnable(QRunnable):
    """One-shot off-thread MoveAxis call.

    The first Alpaca call on a fresh TCP connection takes ~600ms. Running it
    on the main thread would (a) freeze the UI and (b) consume the
    button-released Qt event before returning — causing an instant stop with
    zero visible movement. This QRunnable fixes both problems.
    """

    def __init__(self, telescope, axis: int, rate: float, log_signal) -> None:
        super().__init__()
        self._telescope = telescope
        self._axis = axis
        self._rate = rate
        self._log = log_signal

    def run(self) -> None:
        try:
            self._telescope.move_axis(self._axis, self._rate)
        except AlpacaError as exc:
            action = "Stop jog" if self._rate == 0.0 else "Jog"
            level = "WARN" if self._rate == 0.0 else "ERROR"
            self._log.emit(level, f"{action}: {exc}")


class ImagingPage(QWidget):
    """The Imaging-mode workspace."""

    device_state_changed = pyqtSignal(str, str, str)  # device, state, info
    tracking_changed = pyqtSignal(object)  # bool | None
    action_changed = pyqtSignal(str)
    log_message = pyqtSignal(str, str)  # level, message
    discovered_address = pyqtSignal(str, int)  # host, port
    position_updated = pyqtSignal(float, float, bool)  # ra_h, dec_d, slewing

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config

        self._telescope: Telescope | None = None
        self._camera: Camera | None = None
        self._focuser: Focuser | None = None
        self._discovery: DiscoveryWorker | None = None
        self._polling: MountPollingWorker | None = None
        self._preview: LivePreviewWorker | None = None
        self._autofocus: AutofocusWorker | None = None
        self._sequence: SequenceWorker | None = None
        self._processor = PreviewProcessor(self)  # off-thread display compute
        self._jog_dialog: ManualControlDialog | None = None

        self._channel = VIEW_SUPERPIXEL
        self._last_position: MountPosition | None = None
        self._last_raw: np.ndarray | None = None  # last raw frame, for re-rendering
        self._target_ra: float | None = None
        self._target_dec: float | None = None
        self._last_metrics = None  # last FrameMetrics, for FITS QA headers

        # Single-shot capture: number of upcoming preview frames to save.
        self._capture_pending = 0

        self._build_ui()
        self._wire_signals()
        self._processor.ready.connect(self._on_processed)
        self._processor.start()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Display controls (channel / gamma / auto-stretch) sit above the image.
        self._toolbar = ImageToolbar()
        root.addWidget(self._toolbar)

        # Build the control surfaces once; placed into the layout below.
        self._viewer = FitsViewer()
        self._camera_dock = CameraDock()
        self._sequence_panel = SequencePanel()
        self._mount_dock = MountDock()
        self._focuser_dock = FocuserDock()
        self._histogram_dock = HistogramDock()
        self._log_panel = LogPanel()

        # Right rail = workflow-staged tabs (Capture → Mount → Focus). Tabbing
        # gives every control group the full rail height instead of cramming
        # them into one long scroll. Capture is the home base of the session.
        self._rail = QTabWidget()
        self._rail.setMinimumWidth(360)
        self._rail.setMaximumWidth(460)
        self._rail.addTab(self._tab_page(self._camera_dock), "Capture")
        self._rail.addTab(self._tab_page(self._sequence_panel), "Sequence")
        self._rail.addTab(self._tab_page(self._mount_dock), "Mount")
        self._rail.addTab(self._tab_page(self._focuser_dock), "Focus")
        self._rail.addTab(self._tab_page(self._histogram_dock), "Display")

        # Image column: the viewer (hero) + a thin always-visible stats strip
        # (HFD / Stars / Sky / Min / Max / Mean) — what an astrophotographer
        # glances at constantly while framing and focusing.
        image_col = QWidget()
        col = QVBoxLayout(image_col)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(self._viewer, 1)
        col.addWidget(self._build_stats_bar())

        # Top region: the image is the hero (gets the stretch); the rail is capped.
        top = QSplitter(Qt.Orientation.Horizontal)
        top.setChildrenCollapsible(False)
        top.addWidget(image_col)
        top.addWidget(self._rail)
        top.setStretchFactor(0, 1)
        top.setStretchFactor(1, 0)
        top.setSizes([1000, 400])

        # Bottom strip: the session log (full width under the image). The
        # histogram + stretch controls live in the "Display" rail tab.
        self._log_panel.setMinimumHeight(90)
        self._log_panel.setMaximumHeight(220)

        # Vertical split: the image area dominates, the log is a resizable band.
        main = QSplitter(Qt.Orientation.Vertical)
        main.setChildrenCollapsible(False)
        main.addWidget(top)
        main.addWidget(self._log_panel)
        main.setStretchFactor(0, 1)
        main.setStretchFactor(1, 0)
        main.setSizes([720, 190])
        root.addWidget(main, 1)

    @staticmethod
    def _tab_page(widget: QWidget) -> QScrollArea:
        """Wrap a control dock in a scrollable, top-aligned tab page.

        The dock keeps its natural (Fixed) height and scrolls if the rail is
        shorter than the content, instead of being vertically stretched.
        """
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(
            design.SPACING_MD, design.SPACING_MD, design.SPACING_MD, design.SPACING_MD
        )
        layout.setSpacing(design.SPACING_MD)
        layout.addWidget(widget)
        layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(inner)
        return scroll

    def _build_stats_bar(self) -> QWidget:
        """Thin always-visible strip of live frame stats under the image."""
        bar = QWidget()
        bar.setStyleSheet(f"background:{theme.SURFACE_3}; border-top:1px solid {theme.SURFACE_4};")
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 3, 10, 3)
        row.setSpacing(design.SPACING_LG)
        self._sb: dict[str, QLabel] = {}
        for key in _STAT_KEYS:
            row.addWidget(_stat_key(key))
            value = design.MetricLabel("—")
            self._sb[key] = value
            row.addWidget(value)
        row.addStretch()
        return bar

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _wire_signals(self) -> None:
        # Toolbar
        self._toolbar.channel_changed.connect(self._on_channel_changed)
        self._toolbar.open_requested.connect(self._on_open_fits)
        # Display pipeline: the Display tab (histogram/stretch) ↔ the viewer.
        self._histogram_dock.stretch_changed.connect(self._viewer.set_stretch)
        self._histogram_dock.auto_requested.connect(self._viewer.auto_stretch)
        self._histogram_dock.saturation_toggled.connect(self._on_saturation_toggled)
        self._histogram_dock.roi_toggled.connect(self._viewer.set_roi_enabled)
        self._histogram_dock.crosshair_toggled.connect(self._viewer.set_crosshair_enabled)
        self._viewer.levels_changed.connect(self._histogram_dock.set_levels)
        self._viewer.region_info.connect(self._histogram_dock.set_region_info)

        # Camera dock
        self._camera_dock.take_shot_clicked.connect(self._on_take_shot)
        self._sequence_panel.start_requested.connect(self._on_sequence_start)
        self._sequence_panel.stop_requested.connect(self._on_sequence_stop)

        # Mount dock
        self._mount_dock.goto_clicked.connect(self._on_goto)
        self._mount_dock.sync_to_current_clicked.connect(self._on_sync)
        self._mount_dock.tracking_toggled.connect(self._on_tracking_toggle)
        self._mount_dock.tracking_rate_changed.connect(self._on_tracking_rate)
        self._mount_dock.abort_clicked.connect(self._on_abort)
        self._mount_dock.park_clicked.connect(self._on_park)
        self._mount_dock.manual_control_requested.connect(self._open_jog)
        self._mount_dock.jog_start.connect(self._on_jog_start)
        self._mount_dock.jog_stop.connect(self._on_jog_stop)

        # Focuser dock
        self._focuser_dock.step_requested.connect(self._on_focuser_step)
        self._focuser_dock.halt_requested.connect(self._on_focuser_halt)
        self._focuser_dock.autofocus_requested.connect(self._on_autofocus_requested)
        self._focuser_dock.move_to_requested.connect(self._on_focuser_move_to)

        # Logs reach the bottom log panel locally + propagate up to the Shell.
        self.log_message.connect(self._log_panel.append)

    # ------------------------------------------------------------------
    # Public connection API — driven by EquipmentPage via the Shell
    # ------------------------------------------------------------------

    def start_discovery(self) -> None:
        if self._discovery and self._discovery.isRunning():
            return
        self.log_message.emit("INFO", "Starting Alpaca discovery…")
        self._discovery = DiscoveryWorker(timeout=8.0, parent=self)
        self._discovery.devices_found.connect(self._on_devices_found)
        self._discovery.error_occurred.connect(
            lambda m: self.log_message.emit("ERROR", f"Discovery: {m}")
        )
        self._discovery.start()

    def _on_devices_found(self, devices) -> None:
        if not devices:
            self.log_message.emit("WARN", "No Alpaca devices found.")
            return
        first = devices[0]
        host, port = first.get("address", ""), int(first.get("port", 32323))
        self.log_message.emit("OK", f"Found {host}:{port}")
        self.discovered_address.emit(host, port)

    def connect_mount(self, host: str, port: int) -> None:
        self._config.alpaca_host = host
        self._config.alpaca_port = port
        self.action_changed.emit(f"Connecting mount {host}:{port}…")
        try:
            scope = Telescope(host=host, port=port)
            name = scope.connect()
            self._telescope = scope
            self.log_message.emit("OK", f"Mount connected: {name}")
            self.device_state_changed.emit("mount", "connected", name)
            self._start_polling()
            self._mount_dock.set_enabled(True)
        except AlpacaError as exc:
            self.log_message.emit("ERROR", f"Mount: {exc}")
            self.device_state_changed.emit("mount", "error", str(exc)[:48])

    def connect_camera(self, host: str, port: int) -> None:
        self._config.alpaca_host = host
        self._config.alpaca_port = port
        self.action_changed.emit(f"Connecting camera {host}:{port}…")
        try:
            cam = Camera(host=host, port=port)
            name = cam.connect()
            self._camera = cam
            self._camera_dock.set_enabled(True)
            self.log_message.emit("OK", f"Camera connected: {name}")
            self.device_state_changed.emit("camera", "connected", name)
        except AlpacaError as exc:
            self.log_message.emit("ERROR", f"Camera: {exc}")
            self.device_state_changed.emit("camera", "error", str(exc)[:48])

    def disconnect_mount(self) -> None:
        self._stop_polling()
        if self._telescope:
            try:
                self._telescope.disconnect()
            except AlpacaError:
                pass
            self._telescope = None
        self._mount_dock.set_enabled(False)
        self.device_state_changed.emit("mount", "disconnected", "")
        self.tracking_changed.emit(None)
        self.log_message.emit("INFO", "Mount disconnected.")

    def disconnect_camera(self) -> None:
        self._stop_preview()
        if self._camera:
            try:
                self._camera.disconnect()
            except AlpacaError:
                pass
            self._camera = None
        self._camera_dock.set_enabled(False)
        self.device_state_changed.emit("camera", "disconnected", "")
        self.log_message.emit("INFO", "Camera disconnected.")

    def connect_focuser(self, host: str, port: int) -> None:
        self._config.alpaca_host = host
        self._config.alpaca_port = port
        self.action_changed.emit(f"Connecting focuser {host}:{port}…")
        try:
            foc = Focuser(host=host, port=port)
            name = foc.connect()
            self._focuser = foc
            self._focuser_dock.set_enabled(True)
            pos = foc.get_position()
            self._focuser_dock.set_position(pos)
            temp = foc.get_temperature()
            self._focuser_dock.set_temperature(temp)
            self.log_message.emit("OK", f"Focuser connected: {name}  pos={pos}")
            self.device_state_changed.emit("focuser", "connected", name)
        except AlpacaError as exc:
            self.log_message.emit("ERROR", f"Focuser: {exc}")
            self.device_state_changed.emit("focuser", "error", str(exc)[:48])

    def disconnect_focuser(self) -> None:
        self._stop_autofocus()
        if self._focuser:
            try:
                self._focuser.disconnect()
            except AlpacaError:
                pass
            self._focuser = None
        self._focuser_dock.set_enabled(False)
        self.device_state_changed.emit("focuser", "disconnected", "")
        self.log_message.emit("INFO", "Focuser disconnected.")

    def disconnect_all(self) -> None:
        self.disconnect_camera()
        self.disconnect_mount()
        self.disconnect_focuser()
        self.action_changed.emit("Disconnected")

    # ------------------------------------------------------------------
    # Camera actions
    # ------------------------------------------------------------------

    def _on_channel_changed(self, channel: str) -> None:
        self._channel = channel
        # Re-render the last frame (via the worker) so the view switch is visible
        # even when no live preview is running.
        if self._last_raw is not None:
            self._processor.submit(self._last_raw, channel)

    def _on_saturation_toggled(self, enabled: bool) -> None:
        threshold = int(self._config.get("camera.full_well_adu", 60000))
        self._viewer.set_saturation(enabled, threshold)

    def _show_raw(self, full_arr) -> None:
        """Submit a raw frame to the preview worker (heavy compute off-thread)."""
        self._last_raw = full_arr
        self._processor.submit(full_arr, self._channel)

    @pyqtSlot(object)
    def _on_processed(self, pf) -> None:
        """Apply a worker-processed frame to the UI (cheap work, UI thread)."""
        self._last_metrics = pf.metrics
        self._camera_dock.set_hfd(pf.metrics.hfd)
        self._focuser_dock.push_metrics(pf.metrics)
        self._update_stats(pf)
        # Histogram first: sets the slider/data range, then the viewer's
        # auto-stretch emits levels that the dock sliders sync to.
        self._histogram_dock.set_histogram(pf.centers, pf.r, pf.g, pf.b, pf.lo, pf.hi)
        self._viewer.display(pf.display)

    def _update_stats(self, pf) -> None:
        """Refresh the live stats strip under the image."""
        m = pf.metrics
        self._sb["HFD"].setText(f"{m.hfd:.1f} px" if m.hfd is not None else "—")
        self._sb["Stars"].setText(str(m.star_count))
        self._sb["Sky"].setText(f"{m.sky_adu:.0f}")
        self._sb["Min"].setText(f"{int(pf.vmin)}")
        self._sb["Max"].setText(f"{int(pf.vmax)}")
        self._sb["Mean"].setText(f"{pf.vmean:.0f}")

    def _on_open_fits(self) -> None:
        start = str(Path.home() / "Downloads")
        path, _ = QFileDialog.getOpenFileName(
            self, "Open FITS", start, "FITS (*.fits *.fit *.fts);;All files (*)"
        )
        if path:
            self.load_fits(path)

    def load_fits(self, path: str) -> None:
        """Load a FITS file from disk into the viewer/pipeline (display only).

        The raw array is shown faithfully in the Raw view; switch the View
        selector to exercise the debayer modes / channel split.
        """
        from astropy.io import fits  # heavy import — only on demand

        try:
            with fits.open(path) as hdul:
                data = next((h.data for h in hdul if getattr(h, "data", None) is not None), None)
            if data is None:
                self.log_message.emit("ERROR", f"No image data in {Path(path).name}")
                return
            arr = np.nan_to_num(np.asarray(data, dtype=np.float32), nan=0.0)
            if arr.ndim == 3:  # colour / cube → collapse to a 2-D plane for display
                arr = arr.mean(axis=0) if arr.shape[0] <= 4 else arr.mean(axis=2)
            if arr.ndim != 2:
                self.log_message.emit("ERROR", f"Unsupported FITS shape {arr.shape}")
                return
            self._channel = VIEW_RAW
            self._toolbar.set_view(VIEW_RAW)
            self._show_raw(arr)
            self.log_message.emit("OK", f"Loaded {Path(path).name}  {arr.shape[1]}×{arr.shape[0]}")
        except Exception as exc:
            self.log_message.emit("ERROR", f"Open FITS failed: {exc}")

    def _on_take_shot(self) -> None:
        self._capture_pending = 1
        if not (self._preview and self._preview.isRunning()):
            self._start_preview()
        self.log_message.emit("CMD", "Take shot — saving next frame…")

    # ------------------------------------------------------------------
    # Advanced sequencer (Sequence tab → SequenceWorker)
    # ------------------------------------------------------------------

    def _on_sequence_start(self, plan) -> None:
        if not self._camera:
            self.log_message.emit("WARN", "Connect the camera before running a sequence.")
            self._sequence_panel.set_running(False)
            return
        if self._sequence and self._sequence.isRunning():
            return
        self._stop_preview()  # the sequence owns the camera

        self._sequence = SequenceWorker(
            camera=self._camera,
            telescope=self._telescope,
            filterwheel=None,
            plan=plan,
            frame_context_provider=self._sequence_frame_context,
            base_dir=self._sessions_base(),
            parent=self,
        )
        self._sequence.step_started.connect(self._on_seq_step)
        self._sequence.frame_image.connect(self._on_seq_frame_image)
        self._sequence.frame_saved.connect(self._on_seq_frame_saved)
        self._sequence.progress.connect(self._sequence_panel.set_progress)
        self._sequence.autofocus_due.connect(self._on_seq_autofocus_due)
        self._sequence.error_occurred.connect(
            lambda m: self.log_message.emit("ERROR", f"Sequence: {m}")
        )
        self._sequence.finished.connect(self._on_seq_finished)

        self._sequence_panel.set_running(True)
        self._sequence.start()
        total = sum(s.count for s in plan.steps if s.enabled and s.count > 0) * max(1, plan.repeat)
        self.log_message.emit("CMD", f"Sequence started — {total} frame(s).")
        self.action_changed.emit("Sequence running")

    def _on_sequence_stop(self) -> None:
        if self._sequence and self._sequence.isRunning():
            self._sequence.stop()
            self.log_message.emit("INFO", "Stopping sequence…")

    def _stop_sequence_worker(self) -> None:
        if self._sequence and self._sequence.isRunning():
            self._sequence.stop()
            self._sequence.wait(15000)
        self._sequence = None

    def _on_seq_step(self, index: int, step) -> None:
        self._sequence_panel.set_status(
            f"Step {index + 1}: {step.count}× {step.exposure_s:.1f}s {step.filter_name}"
        )

    @pyqtSlot(object)
    def _on_seq_frame_image(self, full_arr) -> None:
        self._show_raw(full_arr)

    def _on_seq_frame_saved(self, path: str, _hfd) -> None:
        self.log_message.emit("OK", f"Saved {Path(path).name}")

    def _on_seq_autofocus_due(self) -> None:
        """Run an autofocus pass mid-sequence, then resume the worker."""
        af_busy = self._autofocus is not None and self._autofocus.isRunning()
        if not (self._focuser and self._camera) or af_busy:
            self._resume_sequence()
            return
        self.log_message.emit("CMD", "Sequence: autofocus…")
        self._on_autofocus_requested()
        if self._autofocus is not None:
            self._autofocus.finished.connect(self._resume_sequence)

    def _resume_sequence(self) -> None:
        if self._sequence is not None:
            self._sequence.resume_after_autofocus()

    def _on_seq_finished(self, completed: bool) -> None:
        self._sequence_panel.set_running(False)
        self._sequence = None
        self.log_message.emit(
            "OK" if completed else "INFO",
            "Sequence complete." if completed else "Sequence stopped.",
        )
        self.action_changed.emit("Idle")

    def _sequence_frame_context(self, object_name: str, filter_name: str) -> FrameContext:
        """Build a FrameContext for the worker thread from cached state."""
        pos = self._last_position
        cam = self._camera
        return FrameContext(
            ra=pos.ra if pos else None,
            dec=pos.dec if pos else None,
            altitude=pos.altitude if pos else None,
            azimuth=pos.azimuth if pos else None,
            target_ra=self._target_ra,
            target_dec=self._target_dec,
            object_name=object_name,
            filter_name=filter_name,
            observer=(self._config.get("observer.name") or "").strip(),
            site_lat=self._config.get("site.latitude"),
            site_lon=self._config.get("site.longitude"),
            site_elev=self._config.get("site.elevation"),
            software=_SOFTWARE,
            ccd_temp=cam.get_ccd_temperature() if cam else None,
            egain_driver=cam.get_electrons_per_adu() if cam else None,
            offset=cam.get_offset() if cam else None,
            readout_mode=cam.get_readout_mode_name() if cam else None,
        )

    def _sessions_base(self) -> Path:
        try:
            return self._config.sessions_path.parent
        except AttributeError:
            return Path.home() / "SeerControl"

    def _start_preview(self) -> None:
        if not self._camera:
            self.log_message.emit("WARN", "Camera not connected.")
            return
        params = self._camera_dock.params()
        self._preview = LivePreviewWorker(
            camera=self._camera,
            exposure=params.exposure_s,
            gain=params.gain,
        )
        self._preview.frame_ready.connect(self._on_frame)
        self._preview.status_updated.connect(self.action_changed)
        self._preview.error_occurred.connect(
            lambda m: self.log_message.emit("ERROR", f"Preview: {m}")
        )
        self._preview.finished.connect(self._on_preview_finished)
        self._preview.start()
        self.device_state_changed.emit("camera", "busy", "exposing")

    def _stop_preview(self) -> None:
        if self._preview and self._preview.isRunning():
            self._preview.stop()
            self._preview.wait(5000)
        self._preview = None
        if self._camera:
            self.device_state_changed.emit("camera", "connected", "")

    def _on_preview_finished(self) -> None:
        self._stop_preview()

    @pyqtSlot(object, object, object, object)
    def _on_frame(self, preview_arr, full_arr, start_dt, end_dt) -> None:
        # Update worker settings for the next frame from the dock form.
        params = self._camera_dock.params()
        if self._preview:
            self._preview.update_settings(params.exposure_s, params.gain, scale=1)

        self._show_raw(full_arr)

        # Single-shot save: persist the requested number of preview frames.
        if self._capture_pending > 0:
            self._capture_pending -= 1
            self._save_fits_async(full_arr, start_dt, end_dt)
            if self._capture_pending == 0:
                self._stop_preview()

    # ------------------------------------------------------------------
    # Mount actions
    # ------------------------------------------------------------------

    def _start_polling(self) -> None:
        if not self._telescope:
            return
        self._polling = MountPollingWorker(self._telescope, parent=self)
        self._polling.position_updated.connect(self._on_position)
        self._polling.error_occurred.connect(lambda m: self.log_message.emit("WARN", f"Poll: {m}"))
        self._polling.connection_lost.connect(self._on_mount_lost)
        self._polling.start()

    def _stop_polling(self) -> None:
        if self._polling and self._polling.isRunning():
            self._polling.stop()
            self._polling.wait(3000)
        self._polling = None

    @pyqtSlot(object)
    def _on_position(self, pos: MountPosition) -> None:
        self._last_position = pos
        self._mount_dock.set_position(
            pos.ra,
            pos.dec,
            pos.altitude,
            pos.azimuth,
            pos.tracking,
            pos.slewing,
        )
        self.tracking_changed.emit(pos.tracking)
        # Fan out to the Stellarium worker (via the Shell) so the on-screen
        # reticle in Stellarium keeps following the live mount position.
        self.position_updated.emit(pos.ra, pos.dec, pos.slewing)
        if pos.slewing:
            self.device_state_changed.emit("mount", "busy", "slewing")
        else:
            self.device_state_changed.emit("mount", "connected", "")

    def _on_mount_lost(self) -> None:
        self.log_message.emit("ERROR", "Mount connection lost.")
        self._stop_polling()
        self._telescope = None
        self._mount_dock.set_enabled(False)
        self.device_state_changed.emit("mount", "error", "")
        self.tracking_changed.emit(None)

    def _on_goto(self, ra_h: float, dec_d: float) -> None:
        if not self._telescope:
            return
        try:
            self._telescope.set_tracking(True)
            self._telescope.slew_to(ra_h, dec_d)
            self._target_ra, self._target_dec = ra_h, dec_d
            self.log_message.emit("CMD", f"Slewing → RA {ra_h:.4f}h Dec {dec_d:+.4f}°")
        except AlpacaError as exc:
            self.log_message.emit("ERROR", f"Goto: {exc}")

    def goto_target(self, ra_h: float, dec_d: float, label: str = "") -> None:
        """Slew to ``(ra, dec)`` from an external source (Stellarium, wizard).

        Pre-fills the mount dock's goto fields so the user can see where the
        request came from, then triggers the same slew code path that the UI
        button uses.
        """
        if not self._telescope:
            self.log_message.emit("WARN", "Goto requested but mount not connected")
            return
        self._mount_dock.set_goto_fields(ra_h, dec_d)
        prefix = f"Stellarium {label}" if label else "Goto"
        self.log_message.emit("CMD", f"{prefix} → RA {ra_h:.4f}h Dec {dec_d:+.4f}°")
        self._on_goto(ra_h, dec_d)

    def _on_sync(self) -> None:
        if not (self._telescope and self._last_position):
            return
        ra, dec = self._last_position.ra, self._last_position.dec
        try:
            self._telescope.sync_to(ra, dec)
            self.log_message.emit("CMD", f"Sync at RA {ra:.4f}h Dec {dec:+.4f}°")
        except AlpacaError as exc:
            self.log_message.emit("ERROR", f"Sync: {exc}")

    def _on_tracking_toggle(self, enabled: bool) -> None:
        if not self._telescope:
            return
        try:
            self._telescope.set_tracking(enabled)
            self.log_message.emit("CMD", f"Tracking {'ON' if enabled else 'OFF'}")
        except AlpacaError as exc:
            self.log_message.emit("ERROR", f"Tracking: {exc}")

    def _on_tracking_rate(self, idx: int) -> None:
        if not self._telescope:
            return
        names = ("Sidereal", "Lunar", "Solar")
        try:
            self._telescope.set_tracking_rate(idx)
            self.log_message.emit("CMD", f"Tracking rate → {names[idx]}")
        except AlpacaError as exc:
            self.log_message.emit("ERROR", f"Tracking rate: {exc}")

    def _on_abort(self) -> None:
        if not self._telescope:
            return
        try:
            self._telescope.abort_slew()
            self.log_message.emit("CMD", "Slew aborted")
        except AlpacaError as exc:
            self.log_message.emit("ERROR", f"Abort: {exc}")

    def _on_park(self) -> None:
        if not self._telescope:
            return
        try:
            self._telescope.park()
            self.log_message.emit("CMD", "Park — arm closing.")
        except AlpacaError as exc:
            self.log_message.emit("ERROR", f"Park: {exc}")

    def _on_jog_start(self, axis: int, rate: float) -> None:
        if not self._telescope:
            return
        # Off-thread: first MoveAxis on a fresh TCP connection takes ~600ms.
        # Calling it synchronously on the UI thread would freeze the UI and,
        # worse, consume the button-released event before the call returns —
        # resulting in an immediate stop and zero visible movement.
        QThreadPool.globalInstance().start(
            _JogRunnable(self._telescope, axis, rate, self.log_message)
        )

    def _on_jog_stop(self, axis: int) -> None:
        if not self._telescope:
            return
        QThreadPool.globalInstance().start(
            _JogRunnable(self._telescope, axis, 0.0, self.log_message)
        )

    def _open_jog(self) -> None:
        if not self._telescope:
            return
        if self._jog_dialog is None:
            self._jog_dialog = ManualControlDialog(self._telescope, parent=self)
            self._jog_dialog.log_message.connect(self.log_message)
        self._jog_dialog.show()
        self._jog_dialog.raise_()

    # ------------------------------------------------------------------
    # Focuser actions
    # ------------------------------------------------------------------

    def _on_focuser_step(self, delta: int) -> None:
        if not self._focuser:
            return
        try:
            target = self._focuser.step(delta)
            self._focuser_dock.set_position(target)
            self.log_message.emit("CMD", f"Focuser step {delta:+d} → pos {target}")
        except AlpacaError as exc:
            self.log_message.emit("ERROR", f"Focuser step: {exc}")

    def _on_focuser_move_to(self, position: int) -> None:
        if not self._focuser:
            return
        try:
            self._focuser.move_to(position)
            self._focuser_dock.set_position(position)
            self.log_message.emit("CMD", f"Focuser move → {position}")
        except AlpacaError as exc:
            self.log_message.emit("ERROR", f"Focuser move: {exc}")

    def _on_focuser_halt(self) -> None:
        if not self._focuser:
            return
        self._stop_autofocus()
        try:
            self._focuser.halt()
            self.log_message.emit("CMD", "Focuser halted")
        except AlpacaError as exc:
            self.log_message.emit("WARN", f"Focuser halt: {exc}")

    def _on_autofocus_requested(self) -> None:
        if not (self._focuser and self._camera):
            self.log_message.emit("WARN", "Autofocus needs focuser + camera connected")
            return
        if self._autofocus and self._autofocus.isRunning():
            return
        params = self._camera_dock.params()
        self._autofocus = AutofocusWorker(
            focuser=self._focuser,
            camera=self._camera,
            exposure_s=min(params.exposure_s, 10.0),
            gain=params.gain,
            parent=self,
        )
        self._autofocus.step_done.connect(self._on_af_step)
        self._autofocus.best_found.connect(self._on_af_done)
        self._autofocus.error_occurred.connect(lambda m: self.log_message.emit("ERROR", f"AF: {m}"))
        self._autofocus.finished.connect(self._on_af_finished)
        self._focuser_dock.set_autofocus_running(True)
        self._autofocus.start()
        self.log_message.emit("CMD", "Autofocus started…")
        self.action_changed.emit("Autofocus running")

    def _stop_autofocus(self) -> None:
        if self._autofocus and self._autofocus.isRunning():
            self._autofocus.stop()
            self._autofocus.wait(10_000)
        self._autofocus = None
        self._focuser_dock.set_autofocus_running(False)

    @pyqtSlot(int, int, int, object)
    def _on_af_step(self, step: int, total: int, pos: int, hfd) -> None:
        self._focuser_dock.set_position(pos)
        hfd_str = f"{hfd:.1f}" if hfd is not None else "—"
        self._focuser_dock.set_autofocus_status(f"Step {step}/{total}  HFD={hfd_str}")
        self.log_message.emit("INFO", f"AF {step}/{total}  pos={pos}  HFD={hfd_str}")

    @pyqtSlot(int, object)
    def _on_af_done(self, best_pos: int, best_hfd) -> None:
        self._focuser_dock.set_position(best_pos)
        hfd_str = f"{best_hfd:.1f}" if best_hfd is not None else "—"
        self.log_message.emit("OK", f"Autofocus complete — best pos={best_pos}  HFD={hfd_str}")
        self.action_changed.emit(f"Focused  pos={best_pos}")

    def _on_af_finished(self) -> None:
        self._focuser_dock.set_autofocus_running(False)

    # ------------------------------------------------------------------
    # FITS save
    # ------------------------------------------------------------------

    def _save_fits_async(self, arr: np.ndarray, start_dt: datetime, end_dt: datetime) -> None:
        params = self._camera_dock.params()
        frame_idx = 1

        pos = self._last_position
        ctx_kwargs = {
            "ra": pos.ra if pos else None,
            "dec": pos.dec if pos else None,
            "altitude": pos.altitude if pos else None,
            "azimuth": pos.azimuth if pos else None,
            "target_ra": self._target_ra,
            "target_dec": self._target_dec,
            "object_name": params.object_name,
            "filter_name": params.filter_name,
            "observer": (self._config.get("observer.name") or "").strip(),
            "site_lat": self._config.get("site.latitude"),
            "site_lon": self._config.get("site.longitude"),
            "site_elev": self._config.get("site.elevation"),
            "software": _SOFTWARE,
            "hfd": self._last_metrics.hfd if self._last_metrics else None,
            "star_count": self._last_metrics.star_count if self._last_metrics else None,
            "sky_adu": self._last_metrics.sky_adu if self._last_metrics else None,
        }

        camera = self._camera
        try:
            base = self._config.sessions_path.parent
        except AttributeError:
            base = Path.home() / "SeerControl"
        folder = FITSWriter.session_folder(
            base,
            params.object_name,
            start_dt,
            params.frame_type,
            params.filter_name,
        )
        filename = FITSWriter.build_filename(
            params.object_name,
            params.frame_type,
            start_dt,
            params.exposure_s,
            params.filter_name,
            frame_idx,
        )
        path = folder / filename
        log_emit = self.log_message.emit

        gain = params.gain
        exposure = params.exposure_s
        frame_type = params.frame_type

        class _Task(QRunnable):
            def run(self) -> None:
                ccd_temp = camera.get_ccd_temperature() if camera else None
                egain_d = camera.get_electrons_per_adu() if camera else None
                offset_v = camera.get_offset() if camera else None
                readout = camera.get_readout_mode_name() if camera else None

                ctx = FrameContext(
                    ccd_temp=ccd_temp,
                    egain_driver=egain_d,
                    offset=offset_v,
                    readout_mode=readout,
                    **ctx_kwargs,
                )
                try:
                    FITSWriter.write(
                        arr=arr,
                        path=path,
                        exposure_start=start_dt,
                        exposure_end=end_dt,
                        exposure_time=exposure,
                        gain=gain,
                        image_type=frame_type,
                        context=ctx,
                    )
                    log_emit("OK", f"Saved {path.name}")
                except Exception as exc:
                    log_emit("ERROR", f"FITS save failed: {exc}")

        QThreadPool.globalInstance().start(_Task())

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        self._stop_sequence_worker()
        self._stop_preview()
        self._stop_polling()
        self._stop_autofocus()
        self._processor.stop()
        self._processor.wait(2000)

    def closeEvent(self, event) -> None:
        self.shutdown()
        super().closeEvent(event)
