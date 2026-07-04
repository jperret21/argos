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

The page is a *view* over the session layer (WS5): the DeviceSession owns the
device handles and pollers, the AcquisitionEngine owns the camera-ownership
state machine and the capture/solve/photometry workers. The page builds the
docks, routes their intents into session/engine methods, and renders the
typed signals coming back.

Upward signals the Shell wires into the global status bar + Connection page
(relays of the session/engine signals, kept here so the Shell wiring and the
tests keep one stable surface):

    device_state_changed(device, state, info)
    tracking_changed(bool | None)
    action_changed(text)
    log_message(level, message)
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
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

from argos.core.alpaca.telescope import MountPosition
from argos.core.config import Config
from argos.core.session.acquisition_engine import AcquisitionEngine
from argos.core.session.device_session import DeviceSession
from argos.core.session.types import (
    CameraCapabilities,
    FilterWheelState,
    FocuserState,
    LiveFrame,
)
from argos.core.catalog.targets import TargetStar
from argos.core.imaging.astrometry_session import project_points
from argos.core.imaging.debayer import VIEW_SUPERPIXEL
from argos.core.imaging.metrics import (
    ARCSEC_PER_FULL_PX,
    ARCSEC_PER_GREEN_PX,
    DEFAULT_STAR_RADIUS,
    TRACK_SNAP_SEARCH,
    measure_star_at,
)
from argos.core.imaging.platesolve import format_dec_dms, format_ra_hms
from argos.core.photometry.airmass import airmass_from_altitude
from argos.ui import design, theme
from argos.ui.panels.log_panel import LogPanel
from argos.ui.panels.manual_control_dialog import ManualControlDialog
from argos.ui.widgets.camera_dock import CameraDock
from argos.ui.widgets.filterwheel_dock import FilterWheelDock
from argos.ui.widgets.fits_viewer import FitsViewer
from argos.ui.widgets.focuser_dock import FocuserDock
from argos.ui.widgets.histogram_dock import HistogramDock
from argos.ui.widgets.image_toolbar import ImageToolbar
from argos.ui.widgets.mount_dock import MountDock
from argos.ui.panels.photometry_setup_window import PhotometrySetupWindow
from argos.ui.panels.photometry_window import PhotometryWindow
from argos.ui.widgets.overlay_bar import OverlayBar
from argos.ui.widgets.sequence_panel import SequencePanel
from argos.ui.widgets.star_info_card import StarInfoCard
from argos.workers.camera_service import CameraState
from argos.workers.preview_processor import PreviewProcessor

logger = logging.getLogger(__name__)

#: Live frame stats shown in the always-visible bar under the image.
_STAT_KEYS = ("HFD", "Stars", "Sky", "Min", "Max", "Mean")

#: Camera-ownership state → status-bar action text. The free-text
#: ``action_changed`` strings stay for log/status display only; every
#: enable/disable decision reads :class:`CameraState` from the service.
_STATE_ACTION = {
    CameraState.IDLE: "Idle",
    CameraState.LIVE: "Live preview",
    CameraState.SINGLE: "Taking shot…",
    CameraState.SEQUENCE: "Sequence running",
    CameraState.AUTOFOCUS: "Autofocus running",
}


def _stat_key(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color:{theme.FG_MUTED}; font-size:11px; background:transparent;")
    return lbl


class ImagingPage(QWidget):
    """The Imaging-mode workspace."""

    device_state_changed = pyqtSignal(str, str, str)  # device, state, info
    tracking_changed = pyqtSignal(object)  # bool | None
    action_changed = pyqtSignal(str)
    log_message = pyqtSignal(str, str)  # level, message
    autofocus_step = pyqtSignal(int, int, int, object)  # step, total, pos, hfd|None
    autofocus_best = pyqtSignal(int, object)  # best position, best hfd|None
    autofocus_state = pyqtSignal(bool)  # sweep running / stopped
    # Capture visibility for the Shell's persistent strip (WS4).
    sequence_running = pyqtSignal(bool)
    sequence_progress = pyqtSignal(str, int, int, float)  # object, done, total, eta_s
    camera_state_changed = pyqtSignal(object)  # CameraState ownership transitions
    hfd_updated = pyqtSignal(object)  # per-frame HFD, float | None

    def __init__(
        self,
        config: Config,
        session: DeviceSession,
        engine: AcquisitionEngine,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._session = session
        self._engine = engine

        self._processor = PreviewProcessor(self)  # off-thread display compute
        self._jog_dialog: ManualControlDialog | None = None

        self._channel = VIEW_SUPERPIXEL
        self._last_raw: np.ndarray | None = None  # last raw frame, for re-rendering
        self._star_radius = DEFAULT_STAR_RADIUS  # aperture for FWHM (§5)
        self._green_shape: tuple[int, int] | None = None
        self._disp_shape: tuple[int, int] | None = None
        self._selected_green: tuple[float, float] | None = None  # clicked star (green px)
        self._analysis_windows: list = []  # open Open-FITS analysis windows
        # Alias to the engine-owned live plate-solve controller (§6).
        self._astrometry = engine.astrometry
        # Green-px projections of the engine's cached catalog + target set.
        self._var_green: list = []  # parallel to engine.variables (None = off-frame)
        self._comp_green: list = []
        self._target_green: list = []
        self._pending_star: dict | None = None  # the clicked star awaiting a role
        self._armed: set = set()  # overlays auto-shown once when first available
        # §6 P4: live photometry preview (light curve + metrics window).
        self._photometry_window: PhotometryWindow | None = None
        self._metrics_t0: float | None = None

        self._build_ui()
        # The engine reads capture parameters through these providers — the
        # page owns the widgets, the engine never touches them.
        self._engine.set_providers(self._camera_dock.params, self._camera_dock.preview_scale)
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
        # Slim overlay-toggle chips under the toolbar (Grid/Stars/Variables/…).
        self._overlay_bar = OverlayBar()
        root.addWidget(self._overlay_bar)

        # Build the control surfaces once; placed into the layout below.
        self._viewer = FitsViewer()
        # On-image star-info card (bottom-left overlay) for click → info + roles.
        self._info_card = StarInfoCard(self._viewer)
        self._camera_dock = CameraDock()
        self._sequence_panel = SequencePanel()
        self._mount_dock = MountDock()
        self._focuser_dock = FocuserDock()
        self._filterwheel_dock = FilterWheelDock()
        self._histogram_dock = HistogramDock()
        self._log_panel = LogPanel()

        # Right rail grouped by the one-axis rule (docs/ui_design.md):
        #   Camera    — capture params + single shots + live toggle
        #   Equipment — mount / focuser (+ V-curve) / filter wheel
        #   Display   — image appearance (histogram / stretch)
        # The sequencer lives in the WIDE bottom dock, not in this 360px rail —
        # a step table needs width, and the night is planned there.
        self._rail = QTabWidget()
        self._rail.setMinimumWidth(360)
        self._rail.setMaximumWidth(460)
        self._rail.addTab(self._tab_group(self._camera_dock), "Camera")
        self._rail.addTab(
            self._tab_group(self._mount_dock, self._focuser_dock, self._filterwheel_dock),
            "Equipment",
        )
        self._rail.addTab(self._tab_group(self._histogram_dock), "Display")

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

        # Bottom dock (full width under the image): the sequencer — a step
        # table needs width — with the session log one tab away.
        self._bottom = QTabWidget()
        self._bottom.addTab(self._sequence_panel, "Sequence")
        self._bottom.addTab(self._log_panel, "Log")
        self._bottom.setMinimumHeight(180)

        # Vertical split: the image area dominates, the dock is resizable.
        main = QSplitter(Qt.Orientation.Vertical)
        main.setChildrenCollapsible(False)
        main.addWidget(top)
        main.addWidget(self._bottom)
        main.setStretchFactor(0, 1)
        main.setStretchFactor(1, 0)
        main.setSizes([660, 250])
        root.addWidget(main, 1)

    @staticmethod
    def _tab_group(*widgets: QWidget) -> QScrollArea:
        """Wrap one or more control docks in a scrollable, top-aligned tab page.

        Each dock keeps its natural (Fixed) height and the page scrolls if the
        rail is shorter than the stacked content, instead of stretching them.
        """
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(
            design.SPACING_MD, design.SPACING_MD, design.SPACING_MD, design.SPACING_MD
        )
        layout.setSpacing(design.SPACING_MD)
        for widget in widgets:
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

    def select_rail_tab(self, label: str) -> None:
        """Select the right-rail control tab whose text matches ``label``.

        Used by the workflow-rail phase screens (Target/Focus/Photometry) to
        deep-link into the controls that still live on the shared Capture page
        until the per-phase split lands.
        """
        for i in range(self._rail.count()):
            if self._rail.tabText(i) == label:
                self._rail.setCurrentIndex(i)
                return

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _wire_signals(self) -> None:
        # Device session → upward relays (status bar via the Shell), docks
        # and the typed device-state slots.
        s = self._session
        s.device_state_changed.connect(self._on_session_device_state)
        s.tracking_changed.connect(self.tracking_changed)
        s.action_changed.connect(self.action_changed)
        s.log_message.connect(self.log_message)
        s.mount_position.connect(self._on_mount_position)
        s.capabilities_ready.connect(self._on_camera_capabilities)
        s.filterwheel_state.connect(self._on_filterwheel_state)
        s.focuser_state.connect(self._on_focuser_state)
        s.filter_moved.connect(self._on_filter_moved)
        s.camera_temperature.connect(self._camera_dock.set_temperature)
        s.focuser_temperature.connect(self._focuser_dock.set_temperature)
        s.slewed.connect(self._clear_astrometry)  # a goto stales the solve

        # Acquisition engine → upward relays, docks and the frame pipeline.
        e = self._engine
        e.camera_state_changed.connect(self._on_camera_state)
        e.camera_state_changed.connect(self.camera_state_changed)
        e.device_state_changed.connect(self.device_state_changed)  # camera busy/idle
        e.log_message.connect(self.log_message)
        e.action_changed.connect(self.action_changed)
        e.frame_ready.connect(self._on_frame)
        e.sequence_running.connect(self._on_sequence_running)
        e.sequence_paused.connect(self._sequence_panel.set_paused)
        e.sequence_progress.connect(self._on_sequence_progress)
        e.sequence_step.connect(self._on_seq_step)
        e.frame_saved.connect(self._on_seq_frame_saved)
        e.autofocus_state.connect(self._on_autofocus_state)
        e.autofocus_step.connect(self._on_af_step)
        e.autofocus_best.connect(self._on_af_done)
        e.catalog_ready.connect(self._on_catalog_ready)
        e.targets_changed.connect(self._on_targets_changed)
        e.photometry_measuring.connect(self._on_photometry_measuring)
        e.photometry_point.connect(self._on_photometry_point)
        # Live plate-solve controller (engine-owned, shared pipeline).
        self._astrometry.solved.connect(self._on_astrometry_solved)

        # Toolbar
        self._toolbar.channel_changed.connect(self._on_channel_changed)
        self._toolbar.open_requested.connect(self._on_open_fits)
        self._toolbar.solve_requested.connect(self._engine.solve_now)
        self._toolbar.auto_solve_toggled.connect(self._astrometry.set_auto)
        self._toolbar.photometry_requested.connect(self._open_photometry)
        self._toolbar.photometry_setup_requested.connect(self._on_photometry_setup)
        # Overlay chips + the on-image star-info card.
        self._overlay_bar.toggled.connect(self._on_overlay_toggled)
        self._info_card.role_selected.connect(self._on_card_role)
        self._info_card.cleared.connect(self._on_card_cleared)
        # Display pipeline: the Display tab (histogram/stretch) ↔ the viewer.
        self._histogram_dock.stretch_changed.connect(self._viewer.set_stretch)
        self._histogram_dock.auto_requested.connect(self._viewer.auto_stretch)
        self._histogram_dock.saturation_toggled.connect(self._on_saturation_toggled)
        self._histogram_dock.roi_toggled.connect(self._viewer.set_roi_enabled)
        self._histogram_dock.crosshair_toggled.connect(self._viewer.set_crosshair_enabled)
        self._histogram_dock.stars_overlay_toggled.connect(self._viewer.set_star_overlay_enabled)
        self._histogram_dock.loupe_toggled.connect(self._viewer.set_loupe_enabled)
        self._histogram_dock.astrometry_toggled.connect(self._viewer.set_astrometry_enabled)
        self._histogram_dock.star_radius_changed.connect(self._on_star_radius)
        self._viewer.star_clicked.connect(self._on_star_clicked)
        self._viewer.levels_changed.connect(self._histogram_dock.set_levels)
        self._viewer.region_info.connect(self._histogram_dock.set_region_info)

        # Camera dock — capture intents go straight to the engine.
        self._camera_dock.take_shot_clicked.connect(self._engine.take_shot)
        self._camera_dock.live_start_requested.connect(self._engine.start_live)
        self._camera_dock.live_stop_requested.connect(self._engine.stop_live)
        self._camera_dock.offset_changed.connect(self._on_camera_offset)
        self._camera_dock.binning_changed.connect(self._on_camera_binning)
        self._camera_dock.filter_selected.connect(self._on_camera_dock_filter)
        self._sequence_panel.start_requested.connect(self._on_sequence_start)
        self._sequence_panel.pause_requested.connect(self._engine.pause_sequence)
        self._sequence_panel.resume_requested.connect(self._engine.resume_sequence_run)
        self._sequence_panel.stop_requested.connect(self._engine.stop_sequence)

        # Filter wheel dock
        self._filterwheel_dock.move_requested.connect(self._on_filter_move)

        # Mount dock — command intents go straight to the device session.
        self._mount_dock.goto_clicked.connect(self._on_goto)
        self._mount_dock.sync_to_current_clicked.connect(self._session.sync_current)
        self._mount_dock.tracking_toggled.connect(self._session.set_tracking)
        self._mount_dock.tracking_rate_changed.connect(self._session.set_tracking_rate)
        self._mount_dock.abort_clicked.connect(self._session.abort_slew)
        self._mount_dock.park_clicked.connect(self._session.park)
        self._mount_dock.manual_control_requested.connect(self._open_jog)
        self._mount_dock.jog_start.connect(self._session.jog)
        self._mount_dock.jog_stop.connect(self._on_jog_stop)

        # Focuser dock
        self._focuser_dock.step_requested.connect(self._on_focuser_step)
        self._focuser_dock.halt_requested.connect(self._on_focuser_halt)
        self._focuser_dock.autofocus_requested.connect(self._engine.start_autofocus)
        self._focuser_dock.move_to_requested.connect(self._on_focuser_move_to)

        # Logs reach the bottom log panel locally + propagate up to the Shell.
        self.log_message.connect(self._log_panel.append)

    # ------------------------------------------------------------------
    # Camera-ownership state (WS3) — one source of truth for guards
    # ------------------------------------------------------------------

    @property
    def camera_service(self):
        """The engine's ownership state machine (widgets may subscribe)."""
        return self._engine.camera_service

    @property
    def camera_state(self) -> CameraState:
        """Current camera owner — the value widgets base enable/disable on."""
        return self._engine.camera_state

    @pyqtSlot(object)
    def _on_camera_state(self, state: CameraState) -> None:
        """Reflect ownership transitions in the status bar + the Live toggle."""
        self.action_changed.emit(_STATE_ACTION[state])
        self._camera_dock.set_live_running(state is CameraState.LIVE)

    # ------------------------------------------------------------------
    # Device session state → docks (the session owns the device handles)
    # ------------------------------------------------------------------

    @pyqtSlot(str, str, str)
    def _on_session_device_state(self, device: str, state: str, info: str) -> None:
        """Reflect a device transition in the docks, then relay it upward."""
        enabled = state in ("connected", "busy")
        if device == "mount":
            self._mount_dock.set_enabled(enabled)
        elif device == "camera":
            self._camera_dock.set_enabled(enabled)
            if state == "disconnected":
                self._camera_dock.reset_camera_limits()
                self._sequence_panel.set_camera_limits()  # back to defaults
        elif device == "filterwheel":
            self._filterwheel_dock.set_enabled(enabled)
        elif device == "focuser":
            self._focuser_dock.set_enabled(enabled)
            if state == "disconnected":
                self._focuser_dock.set_temperature(None)
        self.device_state_changed.emit(device, state, info)

    @pyqtSlot(object)
    def _on_camera_capabilities(self, caps: CameraCapabilities) -> None:
        """Push driver-derived limits into the capture forms and expose the
        optional parameters (offset / binning) the driver proves it supports."""
        self._camera_dock.set_gain_range(caps.gain_min, caps.gain_max)
        self._camera_dock.set_exposure_range(caps.exposure_min, caps.exposure_max)
        self._sequence_panel.set_camera_limits(
            caps.gain_min, caps.gain_max, caps.exposure_min, caps.exposure_max
        )
        if caps.offset is not None and caps.offset_min is not None and caps.offset_max is not None:
            self._camera_dock.set_offset_support(caps.offset_min, caps.offset_max, caps.offset)
        if caps.max_bin > 1:
            self._camera_dock.set_binning_support(caps.max_bin, caps.binning)

    @pyqtSlot(object)
    def _on_filterwheel_state(self, fw: FilterWheelState) -> None:
        names = list(fw.names)
        self._filterwheel_dock.set_filters(names)
        self._camera_dock.set_filter_options(names)
        self._sequence_panel.set_filter_options(names)
        self._filterwheel_dock.set_position(fw.position, fw.position_name)

    @pyqtSlot(object)
    def _on_focuser_state(self, foc: FocuserState) -> None:
        self._focuser_dock.set_position(foc.position)

    def _on_filter_move(self, position: int) -> None:
        if not self._session.filterwheel:
            return
        self._filterwheel_dock.set_position(-1, "")  # show "Moving…"
        self._session.move_filter(position)

    def _on_camera_dock_filter(self, name: str) -> None:
        """The CameraDock filter combo physically moves the wheel — the FITS
        metadata must describe the filter that was really in front of the sensor."""
        if not self._session.filterwheel:
            self.log_message.emit(
                "WARN", f"Filter wheel not connected — '{name}' is metadata only."
            )
            return
        position = self._session.filter_position_for(name)
        if position is None:
            self.log_message.emit("WARN", f"No wheel position matches filter '{name}'.")
            return
        self._on_filter_move(position)

    @pyqtSlot(int, str)
    def _on_filter_moved(self, position: int, name: str) -> None:
        self._filterwheel_dock.set_position(position, name)
        # Keep the CameraDock combo (single-shot metadata) on the real position.
        self._camera_dock.set_current_filter(name)

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
        if self._green_shape is not None and pf.green_shape != self._green_shape:
            # The green coordinate frame changed size (preview quality toggle,
            # binning) — a click selection from the old frame is stale.
            self._selected_green = None
            self._viewer.clear_selection()
            self._info_card.hide()
        self._green_shape = pf.green_shape
        self._disp_shape = pf.display.shape[:2]
        self._camera_dock.set_hfd(pf.metrics.hfd)
        self._focuser_dock.push_metrics(pf.metrics)
        self.hfd_updated.emit(pf.metrics.hfd)  # Shell capture strip
        self._update_stats(pf)
        # Histogram first: sets the slider/data range, then the viewer's
        # auto-stretch emits levels that the dock sliders sync to.
        self._histogram_dock.set_histogram(pf.centers, pf.r, pf.g, pf.b, pf.lo, pf.hi)
        self._viewer.set_stars(pf.stars, pf.green_shape)
        self._viewer.display(pf.display)
        # Keep a clicked star's FWHM readout live as new frames arrive.
        self._remeasure_selection()
        self._overlay_bar.set_available("stars", True)  # detected-star overlay always usable
        self._feed_metrics(pf)  # session metrics (when the photometry window is open)
        # WCS geometry guard: the grid + catalog markers are projected in the
        # *solved* frame's green px. If the displayed frame no longer matches
        # (preview quality toggle, binning change), they would draw at the
        # wrong positions and clicks would mis-identify stars — drop them,
        # same policy as a slew. Re-solving at full res restores everything.
        if (
            self._astrometry.wcs is not None
            and self._astrometry.green_shape is not None
            and self._astrometry.green_shape != pf.green_shape
        ):
            self._clear_astrometry()
            self.log_message.emit(
                "INFO", "Frame geometry changed — WCS overlays cleared (solve again at full res)."
            )
        # Per-frame engine bookkeeping + the auto-solve policy (the engine
        # skips half-quality previews — their plate scale would poison a solve).
        self._engine.on_processed(pf.green_shape, pf.metrics, pf.stars.mean_fwhm)

    def _update_stats(self, pf) -> None:
        """Refresh the live stats strip under the image."""
        m = pf.metrics
        self._sb["HFD"].setText(f"{m.hfd:.1f} px" if m.hfd is not None else "—")
        self._sb["Stars"].setText(str(m.star_count))
        self._sb["Sky"].setText(f"{m.sky_adu:.0f}")
        self._sb["Min"].setText(f"{int(pf.vmin)}")
        self._sb["Max"].setText(f"{int(pf.vmax)}")
        self._sb["Mean"].setText(f"{pf.vmean:.0f}")

    # ------------------------------------------------------------------
    # Star measurement on click (§5)
    # ------------------------------------------------------------------

    def _on_star_radius(self, radius: int) -> None:
        """User changed the FWHM aperture — re-render overlay + selection."""
        self._star_radius = max(2, int(radius))
        self._processor.set_radius(self._star_radius)
        if self._last_raw is not None:
            self._processor.submit(self._last_raw, self._channel)  # refresh overlay

    def _on_star_clicked(self, x_disp: float, y_disp: float) -> None:
        """Hit-test the click (target → variable → comparison → field star) and
        show the on-image info card with role actions."""
        gp = self._disp_to_green(x_disp, y_disp)
        if gp is None or self._last_raw is None:
            return
        gx, gy = gp
        # 1) a saved target (only if its markers are showing)
        i = self._nearest(self._target_green, gx, gy) if self._overlay_bar.is_checked("targets") else None
        if i is not None:
            s = self._engine.target_set().stars[i]
            self._present_card(
                self._target_green[i],
                f"Target · {s.display_name}",
                self._target_body(s),
                dict(ra_deg=s.ra_deg, dec_deg=s.dec_deg, auid=s.auid, name=s.name,
                     source=s.source, mags=dict(s.mags)),
            )
            return
        # 2) a VSX variable
        i = self._nearest(self._var_green, gx, gy)
        if i is not None:
            v = self._engine.variables[i]
            self._present_card(
                self._var_green[i],
                f"Variable · {v.name}",
                self._variable_body(v),
                dict(ra_deg=v.ra_deg, dec_deg=v.dec_deg, auid=v.auid, name=v.name,
                     source="vsx", mags={}),
            )
            return
        # 3) a VSP comparison (only if its markers are showing)
        i = self._nearest(self._comp_green, gx, gy) if self._overlay_bar.is_checked("comparisons") else None
        if i is not None:
            c = self._engine.comparisons[i]
            self._present_card(
                self._comp_green[i],
                f"Comparison · {c.label or c.auid}",
                self._comparison_body(c),
                dict(ra_deg=c.ra_deg, dec_deg=c.dec_deg, auid=c.auid, name=c.label,
                     source="vsp", mags={b.band: b.mag for b in c.bands}),
            )
            return
        # 4) a measured field star
        meas = measure_star_at(self._last_raw, gx, gy, self._star_radius)
        if meas is None:
            self._viewer.clear_selection()
            self._info_card.hide()
            self._selected_green = None
            self._pending_star = None
            return
        self._selected_green = (meas.x, meas.y)
        self._present_field_card(meas)

    def _nearest(self, positions, gx: float, gy: float) -> int | None:
        """Index of the marker nearest (gx, gy) green px within tolerance."""
        if not positions:
            return None
        tol = 10.0
        if self._green_shape and self._disp_shape and self._disp_shape[1] > 0:
            tol = max(6.0, 14.0 * self._green_shape[1] / self._disp_shape[1])
        best_i, best_d = None, tol
        for i, p in enumerate(positions):
            if p is None:
                continue
            d = ((p[0] - gx) ** 2 + (p[1] - gy) ** 2) ** 0.5
            if d <= best_d:
                best_i, best_d = i, d
        return best_i

    def _present_card(self, green_pos, title: str, body: str, pending: dict) -> None:
        """Ring a catalog/target pick and show its info card (roles enabled)."""
        self._selected_green = None  # a catalog pick, not a measured field star
        self._pending_star = pending
        dp = self._green_to_disp(green_pos[0], green_pos[1])
        if dp is not None:
            self._viewer.mark_selection(dp[0], dp[1], "", show_label=False)
        self._info_card.show_star(title, body, roles_enabled=True)
        self._info_card.reposition()

    def _present_field_card(self, meas) -> None:
        """Ring a measured field star; role buttons need a solve for its RA/Dec."""
        wcs = self._astrometry.wcs
        pending = None
        if wcs is not None:
            ra_h, dec_d = wcs.pixel_to_radec(meas.x, meas.y)
            pending = dict(ra_deg=ra_h * 15.0, dec_deg=dec_d, auid=None, name=None,
                           source="manual", mags={})
        self._pending_star = pending
        dp = self._green_to_disp(meas.x, meas.y)
        if dp is not None:
            self._viewer.mark_selection(
                dp[0], dp[1], "", self._green_len_to_disp(meas.radius), show_label=False
            )
        self._info_card.show_star("Field star", self._format_star_text(meas),
                                  roles_enabled=pending is not None)
        self._info_card.reposition()

    def _variable_body(self, v) -> str:
        lines = []
        if v.var_type:
            lines.append(f"type {v.var_type}" + ("  (suspected)" if v.is_suspected else ""))
        rng = []
        if v.max_mag:
            rng.append(f"max {v.max_mag}")
        if v.min_mag and v.min_mag != "?":
            rng.append(f"min {v.min_mag}")
        if rng:
            lines.append("  ".join(rng))
        if v.period:
            lines.append(f"period {v.period:g} d")
        if v.auid:
            lines.append(f"AUID {v.auid}")
        lines.append(f"RA {format_ra_hms(v.ra_deg / 15.0)}  Dec {format_dec_dms(v.dec_deg)}")
        return "\n".join(lines)

    def _comparison_body(self, c) -> str:
        lines = []
        mags = [f"{b.band} {b.mag:.3f}" for b in c.bands]
        if mags:
            lines.append("  ".join(mags))
        if c.label:
            lines.append(f"chart label {c.label}")
        lines.append(f"RA {format_ra_hms(c.ra_deg / 15.0)}  Dec {format_dec_dms(c.dec_deg)}")
        return "\n".join(lines)

    def _target_body(self, s) -> str:
        lines = [f"role {s.role}  ·  source {s.source}"]
        if s.mags:
            lines.append("  ".join(f"{b} {m:.3f}" for b, m in s.mags.items()))
        lines.append(f"RA {format_ra_hms(s.ra_deg / 15.0)}  Dec {format_dec_dms(s.dec_deg)}")
        return "\n".join(lines)

    def _remeasure_selection(self) -> None:
        """Re-measure the pinned star (new frame / radius change), centre stable."""
        if self._selected_green is None or self._last_raw is None:
            return
        # Tight snap → the centre stays put when the aperture radius changes; it
        # only tracks small frame-to-frame drift.
        meas = measure_star_at(
            self._last_raw,
            self._selected_green[0],
            self._selected_green[1],
            self._star_radius,
            search=TRACK_SNAP_SEARCH,
        )
        if meas is None:
            return
        self._selected_green = (meas.x, meas.y)  # follow small tracking drift
        self._show_selection(meas)

    def _show_selection(self, meas) -> None:
        # Keep the tracked field star's ring following small drift; the info is in
        # the on-image card (drawn once on click), so suppress the viewer label.
        dp = self._green_to_disp(meas.x, meas.y)
        if dp is None:
            return
        radius_disp = self._green_len_to_disp(meas.radius)
        self._viewer.mark_selection(dp[0], dp[1], "", radius_disp, show_label=False)

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
        line1 = "   ".join(parts)
        # Frame astrometry: pointing from the mount + plate scale (no solve yet).
        pos = self._session.last_position
        if pos is not None:
            line2 = (
                f"field  RA {pos.ra:.3f}h  Dec {pos.dec:+.2f}°   ·   {ARCSEC_PER_FULL_PX:.2f}″/px"
            )
        else:
            line2 = f"scale  {ARCSEC_PER_FULL_PX:.2f}″/px   (mount not connected)"
        text = f"{line1}\n{line2}"
        wcs = self._astrometry.wcs
        if wcs is not None:  # plate-solved → the star's true celestial position
            ra_h, dec_d = wcs.pixel_to_radec(meas.x, meas.y)
            text += f"\nstar   RA {format_ra_hms(ra_h)}  Dec {format_dec_dms(dec_d)}"
        return text

    def _disp_to_green(self, x_disp: float, y_disp: float) -> tuple[float, float] | None:
        if self._green_shape is None or self._disp_shape is None:
            return None
        gh, gw = self._green_shape
        dh, dw = self._disp_shape
        if dw <= 0 or dh <= 0:
            return None
        return x_disp * gw / dw, y_disp * gh / dh

    def _green_to_disp(self, x_green: float, y_green: float) -> tuple[float, float] | None:
        if self._green_shape is None or self._disp_shape is None:
            return None
        gh, gw = self._green_shape
        dh, dw = self._disp_shape
        if gw <= 0 or gh <= 0:
            return None
        return x_green * dw / gw, y_green * dh / gh

    def _green_len_to_disp(self, length: float) -> float | None:
        """Scale a green-plane length (e.g. the aperture radius) to display px."""
        if self._green_shape is None or self._disp_shape is None:
            return None
        gw = self._green_shape[1]
        dw = self._disp_shape[1]
        return length * dw / gw if gw > 0 else None

    def _on_open_fits(self) -> None:
        start = str(Path.home() / "Downloads")
        path, _ = QFileDialog.getOpenFileName(
            self, "Open FITS", start, "FITS (*.fits *.fit *.fts);;All files (*)"
        )
        if path:
            self.load_fits(path)

    def load_fits(self, path: str) -> None:
        """Open a saved FITS for analysis (alias kept for external callers)."""
        self.open_analysis(path)

    def open_analysis(self, path: str) -> None:
        """Open a saved FITS in a floating analysis window.

        The main viewer keeps following the live camera; deep inspection of an
        already-captured sub (stretch, channels, FWHM, region stats) happens in
        a separate, independent window so the two never fight over the display.
        """
        from argos.ui.analysis_window import AnalysisWindow

        win = AnalysisWindow(self._config)
        if not win.load(path):
            self.log_message.emit("ERROR", f"Could not open {Path(path).name}")
            win.deleteLater()
            return
        win.show()
        win.raise_()
        # Keep references so the windows aren't GC'd; prune closed ones.
        self._analysis_windows = [w for w in self._analysis_windows if w.isVisible()]
        self._analysis_windows.append(win)
        self.log_message.emit("OK", f"Analysing {Path(path).name} in a separate window")

    # ------------------------------------------------------------------
    # Plate solving the live frame (§6) — ASTAP with the mount as a hint
    # ------------------------------------------------------------------

    def _cfg(self, key: str, default):
        value = self._config.get(key, default)
        return default if value is None else value

    @pyqtSlot(object, object, str)
    def _on_astrometry_solved(self, _wcs, overlay, summary: str) -> None:
        """A fresh solution arrived from the controller — apply grid + catalog."""
        if (
            self._green_shape is not None
            and self._astrometry.green_shape is not None
            and self._green_shape != self._astrometry.green_shape
        ):
            # Solved against a frame geometry we no longer display (the preview
            # scale / binning changed while the solve was in flight) — its pixel
            # frame doesn't match, so applying it would misplace every overlay.
            self._clear_astrometry()
            self.log_message.emit(
                "INFO", "Solve finished for a different frame geometry — discarded."
            )
            return
        self.log_message.emit("OK", summary)
        self._viewer.set_astrometry_overlay(overlay, self._green_shape)
        self._arm_overlay("grid", True, self._viewer.set_astrometry_enabled)
        self._histogram_dock.set_astrometry_available(True)
        self._histogram_dock.set_astrometry_checked(self._overlay_bar.is_checked("grid"))
        self._remeasure_selection()  # refresh the clicked star's RA/Dec
        self._engine.maybe_fetch_catalog()  # VSX/VSP once per field
        self._project_catalog()  # re-project cached catalog + targets onto the new WCS
        self._engine.measure_photometry_if_idle()  # sequences measure per saved sub

    # ------------------------------------------------------------------
    # Overlays, catalog + target set (§6 P1)
    # ------------------------------------------------------------------

    def _on_overlay_toggled(self, name: str, on: bool) -> None:
        {
            "grid": self._viewer.set_astrometry_enabled,
            "stars": self._viewer.set_star_overlay_enabled,
            "variables": self._viewer.set_catalog_enabled,
            "comparisons": self._viewer.set_comparison_enabled,
            "targets": self._viewer.set_target_enabled,
        }[name](on)

    def _arm_overlay(self, name: str, has: bool, setter) -> None:
        """Enable a chip when its data exists; auto-show it the first time only."""
        self._overlay_bar.set_available(name, has)
        if has and name not in self._armed:
            self._armed.add(name)
            self._overlay_bar.set_checked(name, True)
            setter(True)

    @pyqtSlot(object)
    def _on_catalog_ready(self, _result) -> None:
        """The engine fetched a fresh VSX/VSP catalog — project it onto the WCS."""
        self._project_catalog()

    def _project_catalog(self) -> None:
        """Re-project the engine's cached variables/comparisons/targets onto the WCS."""
        variables = self._engine.variables
        comparisons = self._engine.comparisons
        wcs, gs = self._astrometry.wcs, self._green_shape
        self._var_green = project_points(wcs, gs, ((v.ra_deg, v.dec_deg) for v in variables))
        var_pts = [(p[0], p[1], v.is_suspected) for p, v in zip(self._var_green, variables) if p]
        self._viewer.set_catalog_markers(var_pts, gs)
        self._comp_green = project_points(
            wcs, gs, ((c.ra_deg, c.dec_deg) for c in comparisons)
        )
        comp_pts = [(p[0], p[1], c.label) for p, c in zip(self._comp_green, comparisons) if p]
        self._viewer.set_comparison_markers(comp_pts, gs)
        self._arm_overlay("variables", bool(var_pts), self._viewer.set_catalog_enabled)
        self._arm_overlay("comparisons", bool(comp_pts), self._viewer.set_comparison_enabled)
        self._project_targets()

    def _project_targets(self) -> None:
        tset = self._engine.target_set()
        wcs, gs = self._astrometry.wcs, self._green_shape
        self._target_green = project_points(wcs, gs, ((s.ra_deg, s.dec_deg) for s in tset.stars))
        pts = [(p[0], p[1], s.display_name) for p, s in zip(self._target_green, tset.stars) if p]
        self._viewer.set_target_markers(pts, gs)
        self._arm_overlay("targets", bool(pts), self._viewer.set_target_enabled)

    # ------------------------------------------------------------------
    # Target roles (the engine owns the persistent target set)
    # ------------------------------------------------------------------

    @pyqtSlot(object)
    def _on_targets_changed(self, _tset) -> None:
        """The engine's target set changed — refresh markers and the table."""
        self._project_targets()
        self._refresh_target_table()

    def _on_card_role(self, role: str) -> None:
        if self._pending_star is None:
            return
        star = TargetStar(role=role, **self._pending_star)
        self._engine.set_target_role(star)  # → targets_changed refreshes the view
        self.log_message.emit("OK", f"{role.capitalize()}: {star.display_name}")

    def _on_card_cleared(self) -> None:
        self._viewer.clear_selection()
        self._selected_green = None
        self._pending_star = None

    # ------------------------------------------------------------------
    # Live photometry preview (§6 P4)
    # ------------------------------------------------------------------

    def _open_photometry(self) -> None:
        if self._photometry_window is None:
            self._photometry_window = PhotometryWindow(self)
            self._photometry_window.lightcurves = self._engine.lightcurves
            self._photometry_window.obscode = str(self._cfg("observer.obscode", "XXX") or "XXX")
            self._photometry_window.targets.remove_requested.connect(self._engine.remove_target)
        self._refresh_target_table()
        self._photometry_window.show()
        self._photometry_window.raise_()

    def _refresh_target_table(self) -> None:
        if self._photometry_window is not None:
            self._photometry_window.targets.set_targets(self._engine.target_set().stars)

    @pyqtSlot()
    def _on_photometry_measuring(self) -> None:
        """A measurement pass starts — sample the CCD temp for the metrics panel."""
        win = self._photometry_window
        if win is not None and win.isVisible():
            win.metrics.add_sample(self._elapsed(), temp=self._ccd_temp())

    @pyqtSlot(object)
    def _on_photometry_point(self, point) -> None:
        """Render one differential point (typed PhotometryPoint) on the curve."""
        win = self._photometry_window
        if win is not None and win.isVisible():
            win.lightcurve.add_point(
                point.name, point.jd, point.mag, point.mag_err, saturated=point.saturated
            )

    def _elapsed(self) -> float:
        if self._metrics_t0 is None:
            self._metrics_t0 = time.monotonic()
        return time.monotonic() - self._metrics_t0

    def _feed_metrics(self, pf) -> None:
        win = self._photometry_window
        if win is None or not win.isVisible():
            return
        m = pf.metrics
        pos = self._session.last_position
        air = airmass_from_altitude(pos.altitude) if pos else None
        win.metrics.add_sample(
            self._elapsed(), sky=m.sky_adu, fwhm=pf.stars.mean_fwhm, hfd=m.hfd,
            stars=m.star_count, airmass=air,
        )

    def _ccd_temp(self) -> float | None:
        """Sensor temperature (read only when the photometry window is open — a
        solved frame is infrequent, so this off-cadence network read is cheap)."""
        return self._session.ccd_temperature()

    # ------------------------------------------------------------------
    # Photometry setup (opens the standalone window)
    # ------------------------------------------------------------------

    def open_photometry_setup(self) -> None:
        """Public entry point (e.g. the Photometry phase screen) for the companion."""
        self._on_photometry_setup()

    def _on_photometry_setup(self) -> None:
        """Open the Photometry Setup window with the last sequence frame."""
        win = PhotometrySetupWindow(
            config=self._config,
            sequence_dir=self._engine.last_sequence_dir,
            parent=self,
        )
        win.show()
        win.raise_()

    def _clear_astrometry(self) -> None:
        """Drop the WCS + catalog overlays — a slew/goto changes the field."""
        self._engine.invalidate_astrometry()  # WCS + the engine's catalog cache
        self._viewer.set_astrometry_overlay(None)
        self._histogram_dock.set_astrometry_available(False)
        self._histogram_dock.set_astrometry_checked(False)
        # The field changed → drop the projections (re-fetched on the next
        # solve) and re-arm so the overlays auto-show again for the new field.
        self._var_green = []
        self._comp_green = []
        self._target_green = []
        self._armed.clear()
        self._viewer.set_catalog_markers((), self._green_shape)
        self._viewer.set_comparison_markers((), self._green_shape)
        self._viewer.set_target_markers((), self._green_shape)
        for name in ("grid", "variables", "comparisons", "targets"):
            self._overlay_bar.set_available(name, False)

    # ------------------------------------------------------------------
    # Driver-backed camera parameters (offset / binning)
    # ------------------------------------------------------------------

    def _on_camera_offset(self, value: int) -> None:
        cam = self._session.camera
        if not cam:
            return
        owner = self._engine.camera_owner()
        if owner is not None:
            # Offset is device-global — changing it mid-run would shift the
            # bias level of the frames the worker is acquiring.
            self.log_message.emit(
                "WARN", f"{owner} running — it owns the camera. Stop it first."
            )
            offset = cam.get_offset()  # re-sync the spinbox with the device
            if offset is not None and cam.offset_min is not None and cam.offset_max is not None:
                self._camera_dock.set_offset_support(cam.offset_min, cam.offset_max, offset)
            return
        self._session.set_camera_offset(value)

    def _on_camera_binning(self, value: int) -> None:
        cam = self._session.camera
        if not cam:
            return
        owner = self._engine.camera_owner()
        if owner is not None:
            # Binning is device-global — changing it mid-run would change the
            # frame geometry (and plate scale) under the worker.
            self.log_message.emit(
                "WARN", f"{owner} running — it owns the camera. Stop it first."
            )
            self._camera_dock.set_binning_support(cam.max_bin, cam.get_binning())
            return
        self._session.set_camera_binning(value)

    # ------------------------------------------------------------------
    # Sequence — view slots over the engine-owned SequenceWorker
    # ------------------------------------------------------------------

    def _on_sequence_start(self, plan) -> None:
        if not self._engine.start_sequence(plan):
            # Refused (no camera / already running / AF owns the camera) —
            # the reason is logged; snap the panel button back.
            self._sequence_panel.set_running(False)

    @pyqtSlot(bool)
    def _on_sequence_running(self, running: bool) -> None:
        self._sequence_panel.set_running(running)
        self.sequence_running.emit(running)  # → the Shell's capture strip

    @pyqtSlot(str, int, int, float)
    def _on_sequence_progress(self, obj: str, done: int, total: int, eta_s: float) -> None:
        self._sequence_panel.set_progress(done, total, eta_s)
        self.sequence_progress.emit(obj, done, total, eta_s)

    def _on_seq_step(self, index: int, step) -> None:
        self._sequence_panel.set_active_step(index)
        self._sequence_panel.set_status(
            f"Step {index + 1}: {step.count}× {step.exposure_s:.1f}s {step.filter_name}"
        )

    def _on_seq_frame_saved(self, path: str, record) -> None:
        name = Path(path).name
        if record is not None and record.hfd is not None:
            fwhm = f" FWHM={record.fwhm:.1f}" if record.fwhm is not None else ""
            self.log_message.emit(
                "OK", f"Saved {name}  HFD={record.hfd:.1f}{fwhm}  stars={record.star_count}"
            )
        else:
            self.log_message.emit("OK", f"Saved {name}")

    # ------------------------------------------------------------------
    # Frames — every engine frame (live, single, sequence) lands here
    # ------------------------------------------------------------------

    @pyqtSlot(object)
    def _on_frame(self, frame: LiveFrame) -> None:
        """Render an engine frame (the engine already handled saves/settings)."""
        self._show_raw(frame.preview)

    # ------------------------------------------------------------------
    # Mount actions
    # ------------------------------------------------------------------

    def _on_jog_stop(self, axis: int) -> None:
        self._session.jog(axis, 0.0)

    @pyqtSlot(object)
    def _on_mount_position(self, pos: MountPosition) -> None:
        self._mount_dock.set_position(
            pos.ra,
            pos.dec,
            pos.altitude,
            pos.azimuth,
            pos.tracking,
            pos.slewing,
        )

    def _on_goto(self, ra_h: float, dec_d: float) -> None:
        # The session emits ``slewed`` on success → _clear_astrometry.
        self._session.goto(ra_h, dec_d)

    def goto_target(self, ra_h: float, dec_d: float, label: str = "") -> None:
        """Slew to ``(ra, dec)`` from an external source (Stellarium, wizard).

        Pre-fills the mount dock's goto fields so the user can see where the
        request came from, then triggers the same slew code path that the UI
        button uses.
        """
        if not self._session.telescope:
            self.log_message.emit("WARN", "Goto requested but mount not connected")
            return
        self._mount_dock.set_goto_fields(ra_h, dec_d)
        prefix = f"Stellarium {label}" if label else "Goto"
        self.log_message.emit("CMD", f"{prefix} → RA {ra_h:.4f}h Dec {dec_d:+.4f}°")
        self._on_goto(ra_h, dec_d)

    def _open_jog(self) -> None:
        telescope = self._session.telescope
        if not telescope:
            return
        if self._jog_dialog is None:
            self._jog_dialog = ManualControlDialog(telescope, parent=self)
            self._jog_dialog.log_message.connect(self.log_message)
        self._jog_dialog.show()
        self._jog_dialog.raise_()

    # ------------------------------------------------------------------
    # Focuser actions
    # ------------------------------------------------------------------

    def _on_focuser_step(self, delta: int) -> None:
        target = self._session.focuser_step(delta)
        if target is not None:
            self._focuser_dock.set_position(target)

    def _on_focuser_move_to(self, position: int) -> None:
        if self._session.focuser_move_to(position):
            self._focuser_dock.set_position(position)

    def _on_focuser_halt(self) -> None:
        if not self._session.focuser:
            return
        self._engine.stop_autofocus()
        self._session.focuser_halt()

    def request_autofocus(self) -> None:
        """Public entry point (e.g. the Focus screen) to start/stop a sweep."""
        self._engine.request_autofocus()

    def nudge_focuser(self, delta: int) -> None:
        """Public manual focuser nudge (signed steps; + = inward)."""
        self._on_focuser_step(delta)

    @pyqtSlot(bool)
    def _on_autofocus_state(self, running: bool) -> None:
        self._focuser_dock.set_autofocus_running(running)
        self.autofocus_state.emit(running)  # → the Focus screen + sidebar dot

    @pyqtSlot(int, int, int, object)
    def _on_af_step(self, step: int, total: int, pos: int, hfd) -> None:
        self._focuser_dock.set_position(pos)
        hfd_str = f"{hfd:.1f}" if hfd is not None else "—"
        self._focuser_dock.set_autofocus_status(f"Step {step}/{total}  HFD={hfd_str}")
        self._focuser_dock.vcurve.add_sample(pos, hfd)
        self.autofocus_step.emit(step, total, pos, hfd)
        self.log_message.emit("INFO", f"AF {step}/{total}  pos={pos}  HFD={hfd_str}")

    @pyqtSlot(int, object)
    def _on_af_done(self, best_pos: int, best_hfd) -> None:
        self._focuser_dock.set_position(best_pos)
        hfd_str = f"{best_hfd:.1f}" if best_hfd is not None else "—"
        self._focuser_dock.vcurve.set_best(best_pos, best_hfd)
        self.autofocus_best.emit(best_pos, best_hfd)
        self.log_message.emit("OK", f"Autofocus complete — best pos={best_pos}  HFD={hfd_str}")
        self.action_changed.emit(f"Focused  pos={best_pos}")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Close the view's windows, then stop the engine's workers.

        The Shell calls this before ``session.shutdown()`` — the engine's
        workers hold device references, so they must stop first.
        """
        for win in self._analysis_windows:
            win.close()
        self._analysis_windows.clear()
        if self._photometry_window is not None:
            self._photometry_window.close()
            self._photometry_window = None
        self._engine.shutdown()
        self._processor.stop()
        self._processor.wait(2000)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        if self._info_card.isVisible():
            self._info_card.reposition()

    def closeEvent(self, event) -> None:
        self.shutdown()
        super().closeEvent(event)
