"""Acquisition mode — the work surface where most session time is spent.

Layout (WS9a — dockable workspace)::

    ┌─ ImageToolbar (View · Open FITS · "display ≠ data") ───────────┐
    ├─ Panel-toggle strip: Camera · Mount · Focuser · Filters · … ───┤
    ├─ OverlayBar: Grid · Stars · Variables · … ────────────────────┤
    │  ┌──────────────────────────────────┬─────────────────────┐   │
    │  │  FitsViewer (hero, central) +    │  Camera dock (right, │   │
    │  │  crosshair + pixel readout       │  Mount/Focuser/Filter│   │
    │  │                                  │  tabbed behind it)   │   │
    │  │  Stats bar: HFD·Stars·Sky·…      │                      │   │
    │  ├──────────────────────────────────┴─────────────────────┤   │
    │  │  Sequence dock (bottom, Log tabbed with it)            │   │
    │  └────────────────────────────────────────────────────────┘   │
    └────────────────────────────────────────────────────────────────┘

Every panel is a real ``QDockWidget`` (movable / resizable / closable /
floatable to a 2nd monitor), hosted in an internal ``QMainWindow`` used as a
plain widget. The central widget is the viewer + the always-visible stats strip.
Layout is persisted via ``QMainWindow.saveState()`` into ``ui.imaging.layout``.

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

import base64
import logging
import time
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QByteArray, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QToolBar,
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
from argos.core.catalog.photometry import separation_arcmin
from argos.core.catalog.targets import TargetStar
from argos.core.imaging.astrometry_session import field_geometry, project_points
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
from argos.ui.widgets.dock_host import make_dock, style_toggle_action
from argos.ui.widgets.fits_viewer import FitsViewer
from argos.ui.widgets.focuser_dock import FocuserDock
from argos.ui.widgets.hfd_history_dock import HfdHistoryDock
from argos.ui.widgets.histogram_dock import HistogramDock
from argos.ui.widgets.image_toolbar import ImageToolbar
from argos.ui.widgets.lightcurve_panel import LightCurvePanel
from argos.ui.widgets.mount_dock import MountDock
from argos.ui.panels.photometry_window import PhotometryWindow
from argos.ui.widgets.overlay_bar import OverlayBar
from argos.ui.widgets.star_info_card import StarInfoCard
from argos.ui.widgets.statistics_dock import StatisticsDock
from argos.workers.camera_service import CameraState
from argos.workers.preview_processor import PreviewProcessor

logger = logging.getLogger(__name__)

#: Live frame stats shown in the always-visible bar under the image.
_STAT_KEYS = ("HFD", "Stars", "Sky", "Min", "Max", "Mean")

#: Config key for the base64-encoded inner QMainWindow.saveState() blob (WS9a).
_CFG_LAYOUT = "ui.imaging.layout"

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
    auto_solve_armed = pyqtSignal(bool)  # → the Shell's checkable menu action
    # Capture visibility for the Shell's persistent strip (WS4).
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
        self._batch_worker = None  # WS7 batch re-run (QThread) + its progress dialog
        self._batch_dialog: QProgressDialog | None = None

        self._build_ui()
        # The engine reads capture parameters through these providers — the
        # page owns the widgets, the engine never touches them.
        self._engine.set_providers(self._camera_dock.params, self._camera_dock.preview_scale)
        self._wire_signals()
        self._processor.ready.connect(self._on_processed)
        self._processor.start()
        # A persisted target set / pre-existing curves must be visible from
        # the first frame, not only after the next selection or solve.
        self._on_targets_changed(self._engine.target_set())
        self._render_curves()

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

        # Build the control surfaces once; wrapped into docks below.
        self._viewer = FitsViewer()
        # On-image star-info card (bottom-left overlay) for click → info + roles.
        self._info_card = StarInfoCard(self._viewer)
        self._camera_dock = CameraDock()
        self._lightcurve_panel = LightCurvePanel()  # live curve, as a dock (WS7)
        self._mount_dock = MountDock()
        self._focuser_dock = FocuserDock()
        self._histogram_dock = HistogramDock()
        self._statistics_dock = StatisticsDock()
        self._hfd_history_dock = HfdHistoryDock()
        self._log_panel = LogPanel()

        # The workspace is an internal QMainWindow used as a plain widget
        # (Qt.WindowType.Widget) so its whole docking machinery — movable,
        # floatable, tabbed docks — works INSIDE the page without it being a
        # top-level window. The Shell owns the real window.
        self._workspace = QMainWindow()
        self._workspace.setWindowFlags(Qt.WindowType.Widget)
        self._workspace.setDockNestingEnabled(True)
        self._workspace.setDockOptions(
            QMainWindow.DockOption.AllowTabbedDocks | QMainWindow.DockOption.AllowNestedDocks
        )

        # Central widget: the viewer (hero) + a thin always-visible stats strip
        # (HFD / Stars / Sky / Min / Max / Mean) — what an astrophotographer
        # glances at constantly while framing and focusing.
        image_col = QWidget()
        col = QVBoxLayout(image_col)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(self._viewer, 1)
        col.addWidget(self._build_stats_bar())
        self._workspace.setCentralWidget(image_col)

        # Every former panel becomes a real dock. Object names are stable —
        # QMainWindow.saveState()/restoreState() key on them.
        self._docks: dict[str, QDockWidget] = {
            "camera": make_dock("Camera", self._camera_dock, object_name="dock.camera"),
            "mount": make_dock("Mount", self._mount_dock, object_name="dock.mount"),
            "focuser": make_dock("Focuser", self._focuser_dock, object_name="dock.focuser"),
            "display": make_dock("Display", self._histogram_dock, object_name="dock.display"),
            # Statistics is a compact key/value card (scrolls if the dock is
            # short); HFD History owns an expanding trend plot, so it manages its
            # own layout (scroll=False) and grows with the dock (WS9b).
            "statistics": make_dock(
                "Statistics", self._statistics_dock, object_name="dock.statistics"
            ),
            "hfd_history": make_dock(
                "HFD History", self._hfd_history_dock, object_name="dock.hfd_history", scroll=False
            ),
            # Log is a wide, self-scrolling panel. (The sequence planner lives
            # in its own Sequencer mode now.)
            "log": make_dock("Log", self._log_panel, object_name="dock.log", scroll=False),
            # Live differential light curve — visible during capture without a
            # floating window (WS7). Owns its own plot layout (scroll=False).
            "lightcurve": make_dock(
                "Light curve", self._lightcurve_panel, object_name="dock.lightcurve", scroll=False
            ),
        }

        # Slim panel-toggle strip (NINA's top strip): one checkable chip per
        # dock, wired to the dock's toggleViewAction() — which keeps the check
        # state in sync with real visibility and, unlike visibilityChanged,
        # does NOT fire on tab switches.
        self._panel_bar = self._build_panel_bar()
        root.addWidget(self._panel_bar)

        # Slim overlay-toggle chips under the panel strip (Grid/Stars/…).
        self._overlay_bar = OverlayBar()
        root.addWidget(self._overlay_bar)

        root.addWidget(self._workspace, 1)

        # Apply the sober default arrangement, then a saved layout if present.
        self._apply_default_layout()
        self._restore_layout()

    #: dock key → (chip label, default-visible). Ordering drives the strip.
    _PANEL_ORDER = (
        ("camera", "Camera"),
        ("mount", "Mount"),
        ("focuser", "Focuser"),
        ("display", "Display"),
        ("statistics", "Statistics"),
        ("hfd_history", "HFD History"),
        ("log", "Log"),
        ("lightcurve", "Light curve"),
    )

    def _build_panel_bar(self) -> QToolBar:
        """A slim strip of checkable dock-toggle chips + a Reset-layout action."""
        bar = QToolBar()
        bar.setMovable(False)
        bar.setStyleSheet(
            f"QToolBar {{ background-color: {theme.SURFACE_3};"
            f" border-bottom: 1px solid {theme.SURFACE_4}; padding: 2px 6px; spacing: 4px; }}"
            f" QToolBar QToolButton {{ color: {theme.FG_MUTED}; font-size: 11px;"
            f" padding: 1px 8px; }}"
            f" QToolBar QToolButton:checked {{ color: {theme.FG}; }}"
        )
        for key, label in self._PANEL_ORDER:
            action = style_toggle_action(self._docks[key].toggleViewAction(), label)
            bar.addAction(action)
        # Reset-layout lives in the strip's overflow / at its end (also on the
        # workspace context menu).
        bar.addSeparator()
        reset = bar.addAction("Reset layout")
        reset.setToolTip("Restore the default panel arrangement")
        reset.triggered.connect(self.reset_layout)
        return bar

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
    # Dockable workspace layout (WS9a)
    # ------------------------------------------------------------------

    def _apply_default_layout(self) -> None:
        """Sober-by-default arrangement (the docks live in fixed home areas).

        Camera right; Mount / Focuser / Filter wheel tabbed behind it; Sequence
        bottom with Log tabbed behind it; Display / Statistics / HFD History
        hidden (right-area homes, summoned on demand). Called on first launch and
        by "Reset layout".
        """
        hidden = ("display", "statistics", "hfd_history", "lightcurve")
        w = self._workspace
        right = Qt.DockWidgetArea.RightDockWidgetArea
        bottom = Qt.DockWidgetArea.BottomDockWidgetArea

        # Detach everything first so a reset is idempotent.
        for dock in self._docks.values():
            w.removeDockWidget(dock)

        w.addDockWidget(right, self._docks["camera"])
        w.addDockWidget(right, self._docks["mount"])
        w.addDockWidget(right, self._docks["focuser"])
        # Mount / Focuser share Camera's stack, tabbed behind it. (The filter
        # wheel has no dock: its slots are driven from the Camera form and the
        # sequence rows — the wheel is capture state, not a device to babysit.)
        for key in ("mount", "focuser"):
            w.tabifyDockWidget(self._docks["camera"], self._docks[key])
        self._docks["camera"].raise_()

        # Log anchors the bottom; the light curve tabs behind it (summoned on
        # demand during a run). The sequence planner has its own mode now.
        w.addDockWidget(bottom, self._docks["log"])
        w.addDockWidget(bottom, self._docks["lightcurve"])
        w.tabifyDockWidget(self._docks["log"], self._docks["lightcurve"])
        self._docks["log"].raise_()

        # Display / Statistics / HFD History have right-area homes but start
        # hidden — docks the user summons on demand from the panel strip.
        for key in hidden:
            w.addDockWidget(right, self._docks[key])

        for key, dock in self._docks.items():
            dock.setVisible(key not in hidden)

    def _restore_layout(self) -> None:
        """Restore a persisted layout over the defaults, if one exists."""
        blob = self._config.get(_CFG_LAYOUT)
        if not blob:
            return
        try:
            self._workspace.restoreState(QByteArray(base64.b64decode(blob)))
        except Exception as exc:  # noqa: BLE001 — a corrupt blob must not crash startup
            logger.warning("Imaging layout restore failed: %s", exc)

    def save_layout(self) -> None:
        """Persist the current dock arrangement (called by the Shell on close)."""
        state = bytes(self._workspace.saveState())
        self._config.set(_CFG_LAYOUT, base64.b64encode(state).decode())

    def reset_layout(self) -> None:
        """Clear the saved layout and restore the sober defaults, live."""
        self._config.set(_CFG_LAYOUT, None)
        self._apply_default_layout()

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
        e.sequence_running.connect(self._on_sequence_running)  # auto-solve arming
        e.frame_saved.connect(self._on_seq_frame_saved)
        e.autofocus_state.connect(self._on_autofocus_state)
        e.autofocus_step.connect(self._on_af_step)
        e.autofocus_best.connect(self._on_af_done)
        e.catalog_ready.connect(self._on_catalog_ready)
        e.targets_changed.connect(self._on_targets_changed)
        e.photometry_measuring.connect(self._on_photometry_measuring)
        e.photometry_point.connect(self._on_photometry_point)
        e.curves_changed.connect(self._render_curves)  # dock + window, one store
        e.apertures_tracked.connect(self._project_catalog)  # markers follow the frame
        # Live plate-solve controller (engine-owned, shared pipeline).
        self._astrometry.solved.connect(self._on_astrometry_solved)

        # Toolbar (view + Open FITS only — solve/photometry actions live in
        # the Shell's Astrometry / Photometry menus).
        self._toolbar.channel_changed.connect(self._on_channel_changed)
        self._toolbar.open_requested.connect(self._on_open_fits)
        # Overlay chips + the on-image star-info card.
        self._overlay_bar.toggled.connect(self._on_overlay_toggled)
        self._info_card.role_selected.connect(self._on_card_role)
        self._info_card.remove_selected.connect(self._on_card_remove)
        self._info_card.cleared.connect(self._on_card_cleared)
        # Display pipeline: the Display tab (histogram/stretch) ↔ the viewer.
        self._histogram_dock.stretch_changed.connect(self._viewer.set_stretch)
        self._histogram_dock.auto_requested.connect(self._viewer.auto_stretch)
        self._histogram_dock.saturation_toggled.connect(self._on_saturation_toggled)
        self._histogram_dock.roi_toggled.connect(self._viewer.set_roi_enabled)
        self._histogram_dock.crosshair_toggled.connect(self._viewer.set_crosshair_enabled)
        self._histogram_dock.loupe_toggled.connect(self._viewer.set_loupe_enabled)
        self._histogram_dock.astrometry_toggled.connect(self._viewer.set_astrometry_enabled)
        self._histogram_dock.star_radius_changed.connect(self._on_star_radius)
        self._histogram_dock.rotation_changed.connect(self._on_rotation_changed)
        # Display rotation: default Auto = portrait sensor shown landscape.
        rotation = str(self._config.get("ui.display.rotation", "auto") or "auto")
        self._viewer.set_rotation(rotation)
        self._histogram_dock.set_rotation_mode(rotation)
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
        # Object edits re-key the target set + curves: every view must follow.
        self._camera_dock.object_changed.connect(self._engine.on_object_changed)

        # Filter wheel dock

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
        # WS8 cockpit: freeze the capture form while the sequence owns the
        # camera (SEQUENCE and its nested AUTOFOCUS pass); any release —
        # complete, stopped or error — transitions state and unfreezes.
        self._camera_dock.set_sequence_lock(state in (CameraState.SEQUENCE, CameraState.AUTOFOCUS))

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
        if caps.offset is not None and caps.offset_min is not None and caps.offset_max is not None:
            self._camera_dock.set_offset_support(caps.offset_min, caps.offset_max, caps.offset)
        if caps.max_bin > 1:
            self._camera_dock.set_binning_support(caps.max_bin, caps.binning)

    @pyqtSlot(object)
    def _on_filterwheel_state(self, fw: FilterWheelState) -> None:
        # The wheel's real slot names become THE filter vocabulary everywhere
        # a filter is picked (camera form here, sequence rows on the Sequencer
        # page) — one source, so a picked name always resolves to a position.
        names = list(fw.names)
        self._camera_dock.set_filter_options(names)
        self._camera_dock.set_current_filter(fw.position_name)

    @pyqtSlot(object)
    def _on_focuser_state(self, foc: FocuserState) -> None:
        self._focuser_dock.set_position(foc.position)

    def _on_filter_move(self, position: int) -> None:
        if not self._session.filterwheel:
            return
        self._camera_dock.set_filter_moving(True)
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
    def _on_filter_moved(self, _position: int, name: str) -> None:
        # Keep the CameraDock combo (single-shot metadata) on the real position.
        self._camera_dock.set_filter_moving(False)
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

    def _on_rotation_changed(self, mode: str) -> None:
        self._viewer.set_rotation(mode)
        self._config.set("ui.display.rotation", mode)  # saved by the Shell on close

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
        self._hfd_history_dock.push_metrics(pf.metrics)  # trend panel (WS9b)
        self._statistics_dock.set_frame(pf)  # full stats grid (WS9b)
        self.hfd_updated.emit(pf.metrics.hfd)  # Shell capture strip
        self._update_stats(pf)
        # Histogram first: sets the slider/data range, then the viewer's
        # auto-stretch emits levels that the dock sliders sync to.
        self._histogram_dock.set_histogram(pf.centers, pf.r, pf.g, pf.b, pf.lo, pf.hi)
        self._viewer.set_frame_geometry(pf.green_shape)
        self._viewer.display(pf.display)
        # Keep a clicked star's FWHM readout live as new frames arrive.
        self._remeasure_selection()
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
        i = (
            self._nearest(self._target_green, gx, gy)
            if self._overlay_bar.is_checked("targets")
            else None
        )
        if i is not None:
            s = self._engine.target_set().stars[i]
            self._present_card(
                self._target_green[i],
                f"Target · {s.display_name}",
                self._target_body(s),
                dict(
                    ra_deg=s.ra_deg,
                    dec_deg=s.dec_deg,
                    auid=s.auid,
                    name=s.name,
                    source=s.source,
                    mags=dict(s.mags),
                ),
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
                dict(
                    ra_deg=v.ra_deg,
                    dec_deg=v.dec_deg,
                    auid=v.auid,
                    name=v.name,
                    source="vsx",
                    mags={},
                ),
            )
            return
        # 3) a VSP comparison (only if its markers are showing)
        i = (
            self._nearest(self._comp_green, gx, gy)
            if self._overlay_bar.is_checked("comparisons")
            else None
        )
        if i is not None:
            c = self._engine.comparisons[i]
            self._present_card(
                self._comp_green[i],
                f"Comparison · {c.label or c.auid}",
                self._comparison_body(c),
                dict(
                    ra_deg=c.ra_deg,
                    dec_deg=c.dec_deg,
                    auid=c.auid,
                    name=c.label,
                    source="vsp",
                    mags={b.band: b.mag for b in c.bands},
                ),
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
        # Remove is offered iff the clicked star is already in the target set —
        # symmetric with adding it from the image.
        key = TargetStar(role="target", **pending).key()
        saved = {s.key() for s in self._engine.target_set().stars}
        self._info_card.show_star(title, body, roles_enabled=True, removable=key in saved)
        self._info_card.reposition()

    def _present_field_card(self, meas) -> None:
        """Ring a measured field star; role buttons need a solve for its RA/Dec."""
        wcs = self._astrometry.wcs
        pending = None
        if wcs is not None:
            ra_h, dec_d = wcs.pixel_to_radec(meas.x, meas.y)
            pending = dict(
                ra_deg=ra_h * 15.0, dec_deg=dec_d, auid=None, name=None, source="manual", mags={}
            )
        self._pending_star = pending
        dp = self._green_to_disp(meas.x, meas.y)
        if dp is not None:
            self._viewer.mark_selection(
                dp[0], dp[1], "", self._green_len_to_disp(meas.radius), show_label=False
            )
        self._info_card.show_star(
            "Field star", self._format_star_text(meas), roles_enabled=pending is not None
        )
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
        """Load a saved FITS into the live pipeline (offline replay).

        The frame lands exactly where a camera frame would, so Solve →
        catalog → target selection → Re-run subs all work telescope-less.
        (The Analyze mode keeps its own single-frame inspector.)
        """
        start = str(self._cfg("sessions_path", str(Path.home())) or Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Open FITS", start, "FITS (*.fits *.fit *.fts);;All files (*)"
        )
        if not path:
            return
        try:
            from astropy.io import fits as _fits

            raw = _fits.getdata(path)
            if raw is None or getattr(raw, "ndim", 0) != 2:
                raise ValueError("expected a single 2-D image HDU")
        except Exception as exc:
            self.log_message.emit("ERROR", f"Open FITS: {exc}")
            return
        # The display/measure pipeline speaks the sensor's raw dtype.
        self._engine.ingest_frame(np.ascontiguousarray(raw, dtype=np.uint16))
        self.log_message.emit(
            "OK", f"Loaded {Path(path).name} — solve to enable catalog & photometry."
        )

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
        self._refresh_variable_table()

    def _project_catalog(self) -> None:
        """Re-project the engine's cached variables/comparisons/targets onto the WCS.

        Uses the engine's *tracked* WCS: during a sequence the live tracker
        follows field rotation/drift between solves, so the markers stay on
        the stars instead of freezing at the solve position.
        """
        variables = self._engine.variables
        comparisons = self._engine.comparisons
        wcs, gs = self._engine.tracked_wcs(), self._green_shape
        self._var_green = project_points(wcs, gs, ((v.ra_deg, v.dec_deg) for v in variables))
        var_pts = [(p[0], p[1], v.is_suspected) for p, v in zip(self._var_green, variables) if p]
        self._viewer.set_catalog_markers(var_pts, gs)
        self._comp_green = project_points(wcs, gs, ((c.ra_deg, c.dec_deg) for c in comparisons))
        comp_pts = [(p[0], p[1], c.label) for p, c in zip(self._comp_green, comparisons) if p]
        self._viewer.set_comparison_markers(comp_pts, gs)
        self._arm_overlay("variables", bool(var_pts), self._viewer.set_catalog_enabled)
        self._arm_overlay("comparisons", bool(comp_pts), self._viewer.set_comparison_enabled)
        self._project_targets()

    def _project_targets(self) -> None:
        tset = self._engine.target_set()
        wcs, gs = self._engine.tracked_wcs(), self._green_shape
        self._target_green = project_points(wcs, gs, ((s.ra_deg, s.dec_deg) for s in tset.stars))
        pts = [
            (p[0], p[1], s.display_name, s.role)
            for p, s in zip(self._target_green, tset.stars)
            if p
        ]
        self._viewer.set_target_markers(pts, gs)
        self._arm_overlay("targets", bool(pts), self._viewer.set_target_enabled)

    # ------------------------------------------------------------------
    # Target roles (the engine owns the persistent target set)
    # ------------------------------------------------------------------

    @pyqtSlot(object)
    def _on_targets_changed(self, _tset) -> None:
        """The engine's target set changed — refresh markers and the tables."""
        self._project_targets()
        self._refresh_target_table()
        self._refresh_variable_table()  # ● markers on the selected rows

    def _on_card_role(self, role: str) -> None:
        if self._pending_star is None:
            return
        star = TargetStar(role=role, **self._pending_star)
        # Before the save, whatever the role: the object name keys targets.json
        # + FITS OBJECT — a first-pick comparison must not orphan the set under
        # the default name.
        self._camera_dock.set_object_name_if_empty(star.display_name)
        self._engine.set_target_role(star)  # → targets_changed refreshes the view
        self.log_message.emit("OK", f"{role.capitalize()}: {star.display_name}")

    def _on_card_remove(self) -> None:
        """Remove the shown star from the target set (image-side pruning)."""
        if self._pending_star is None:
            return
        star = TargetStar(role="target", **self._pending_star)
        self._engine.remove_target(star.key())  # → targets_changed refreshes all
        self.log_message.emit("OK", f"Removed from target set: {star.display_name}")
        self._info_card.hide()
        self._on_card_cleared()

    def _on_card_cleared(self) -> None:
        self._viewer.clear_selection()
        self._selected_green = None
        self._pending_star = None

    # ------------------------------------------------------------------
    # Live photometry preview (§6 P4)
    # ------------------------------------------------------------------

    def open_photometry(self) -> None:
        """Shell menu entry point (Photometry ▸ Light curve…)."""
        self._open_photometry()

    def rerun_subs(self) -> None:
        """Shell menu entry point (Photometry ▸ Re-run subs…)."""
        self._on_rerun_subs()

    def _open_photometry(self) -> None:
        if self._photometry_window is None:
            self._photometry_window = PhotometryWindow(self)
            self._photometry_window.lightcurves = self._engine.lightcurves
            self._photometry_window.set_export_meta(
                str(self._cfg("observer.obscode", "XXX") or "XXX"),
                str(self._cfg("photometry.default_band", "TG") or "TG"),
                self._engine.target_set().object_name,
            )
            self._photometry_window.targets.remove_requested.connect(self._engine.remove_target)
            self._photometry_window.comparisons.remove_requested.connect(self._engine.remove_target)
            self._photometry_window.variables.target_requested.connect(
                self._on_variable_target_requested
            )
        # Backfill the window with the curve so far (points accrue in the dock).
        self._photometry_window.load_curves(
            self._engine.lightcurves,
            obscode=str(self._cfg("observer.obscode", "XXX") or "XXX"),
            filt=str(self._cfg("photometry.default_band", "TG") or "TG"),
        )
        # ``load_curves`` snapshots into a copy; restore the engine's live dict so
        # AAVSO/CSV export reflects points (and targets) added after this open.
        self._photometry_window.lightcurves = self._engine.lightcurves
        self._refresh_target_table()
        self._refresh_variable_table()
        self._photometry_window.show()
        self._photometry_window.raise_()

    def _refresh_target_table(self) -> None:
        if self._photometry_window is not None:
            self._photometry_window.set_targets(self._engine.target_set().stars)

    def _refresh_variable_table(self) -> None:
        """Feed the Variables tab: one row per cached VSX variable, in order."""
        if self._photometry_window is None:
            return
        centre = field_geometry(self._astrometry.wcs, self._green_shape)
        saved = {s.key() for s in self._engine.target_set().stars}
        rows = []
        for v in self._engine.variables:
            sep = (
                separation_arcmin(centre[0], centre[1], v.ra_deg, v.dec_deg)
                if centre is not None
                else None
            )
            mag = " – ".join(m for m in (v.max_mag, v.min_mag) if m)
            key = f"auid:{v.auid}" if v.auid else f"pos:{v.ra_deg:.5f},{v.dec_deg:.5f}"
            rows.append((v.name, v.var_type, mag, v.period, sep, key in saved, v.is_suspected))
        self._photometry_window.variables.set_variables(rows)

    def _on_variable_target_requested(self, row: int) -> None:
        """Variables-tab pick — the same action as the star-card Target button."""
        variables = self._engine.variables
        if not 0 <= row < len(variables):
            return
        v = variables[row]
        star = TargetStar(
            role="target",
            ra_deg=v.ra_deg,
            dec_deg=v.dec_deg,
            auid=v.auid,
            name=v.name,
            source="vsx",
            mags={},
        )
        # Before the save: the object name keys targets.json + FITS OBJECT.
        self._camera_dock.set_object_name_if_empty(star.display_name)
        self._engine.set_target_role(star)  # → targets_changed refreshes the view
        self.log_message.emit("OK", f"Target: {star.display_name}")

    # ------------------------------------------------------------------
    # Batch re-run over saved subs (WS7 — off the UI thread)
    # ------------------------------------------------------------------

    def _on_rerun_subs(self) -> None:
        """Re-run differential photometry over a folder of saved FITS.

        Uses the current live solve as the shared WCS and the engine's target
        set — the same measurement core as the live path — so comps carry their
        catalog magnitudes. Runs in a QThread with a cancellable progress dialog.
        """
        if self._batch_worker is not None:
            return  # one at a time
        from argos.core.photometry.params import PhotometryParams
        from argos.workers.photometry_batch_worker import BatchRequest, PhotometryBatchWorker

        wcs = self._astrometry.wcs
        if wcs is None:
            QMessageBox.information(
                self, "Solve first", "Plate-solve the live frame before a batch re-run."
            )
            return
        tset = self._engine.target_set()
        if not tset.by_role("target"):
            QMessageBox.information(self, "No targets", "Assign at least one target star first.")
            return
        if not tset.by_role("comparison"):
            # Without comps every frame ends "no valid comparisons" → an empty
            # curve; refuse up front with the fix instead of a post-run WARN.
            QMessageBox.information(
                self,
                "No comparison stars",
                "The target set has no comparison stars, so differential\n"
                "photometry cannot produce magnitudes.\n\n"
                "Solve the field and wait for the catalog (comps auto-select\n"
                "once it arrives), or click a comparison marker on the image\n"
                "and assign it the Comp role.",
            )
            return
        start = str(self._engine.last_sequence_dir or self._config.sessions_path)
        folder = QFileDialog.getExistingDirectory(self, "Folder of saved subs", start)
        if not folder:
            return
        paths = sorted(Path(folder).glob("*.fits"), key=lambda p: p.stat().st_mtime)
        if not paths:
            paths = sorted(Path(folder).rglob("*.fits"), key=lambda p: p.stat().st_mtime)
        if not paths:
            QMessageBox.information(self, "No frames", f"No FITS files in {folder}")
            return
        params = PhotometryParams.from_config(self._cfg, egain=self._engine_egain())
        req = BatchRequest(
            fits_paths=paths,
            wcs=wcs,
            target_set=tset,
            params=params,
            out_dir=self._config.sessions_path.parent / "targets",
            object_name=tset.object_name or "untitled",
            site=(
                self._cfg("site.latitude", None),
                self._cfg("site.longitude", None),
                self._cfg("site.elevation", 0.0) or 0.0,
            ),
            diagnostics=bool(self._cfg("diagnostics.enabled", True)),
        )
        dialog = QProgressDialog("Re-running photometry…", "Cancel", 0, len(paths), self)
        dialog.setWindowTitle("Batch photometry")
        dialog.setMinimumDuration(0)
        worker = PhotometryBatchWorker(req, parent=self)
        dialog.canceled.connect(worker.cancel)
        worker.progress.connect(lambda done, total: dialog.setValue(done))
        worker.finished_batch.connect(self._on_batch_done)
        self._batch_worker = worker
        self._batch_dialog = dialog
        dialog.show()
        worker.start()

    def _engine_egain(self) -> float:
        """e-/ADU from the config table (batch has no live driver handle)."""
        table = self._cfg("camera.egain_table", {}) or {}
        gain = str(self._camera_dock.params().gain)
        if isinstance(table, dict) and gain in table:
            try:
                return float(table[gain])
            except (TypeError, ValueError):
                pass
        return 1.0

    @pyqtSlot(object)
    def _on_batch_done(self, result) -> None:
        if self._batch_dialog is not None:
            self._batch_dialog.reset()
            self._batch_dialog = None
        self._batch_worker = None
        if not result.ok:
            QMessageBox.warning(self, "Batch failed", result.error)
            return
        if not result.curves:
            self.log_message.emit(
                "WARN",
                "Batch photometry: no points measured — see the per-frame notes "
                "in targets/*_diagnostics.jsonl.",
            )
            return
        self.log_message.emit(
            "OK",
            f"Batch photometry: {result.frames_done} frame(s), {len(result.curves)} target(s).",
        )
        if abs(result.rotation_deg) > 0.05 or result.shift_px > 1.0:
            self.log_message.emit(
                "INFO",
                f"Apertures tracked the field: {result.rotation_deg:+.2f}° rotation, "
                f"{result.shift_px:.1f} px drift vs the reference solve.",
            )
        # Batch curves land in THE store; curves_changed re-renders the dock
        # and (via the open below) the window from the same dict — the old
        # window-only feed left the Light-curve dock empty after a re-run.
        self._engine.adopt_curves(result.curves)
        self._open_photometry()

    @pyqtSlot()
    def _on_photometry_measuring(self) -> None:
        """A measurement pass starts — sample the CCD temp for the metrics panel."""
        win = self._photometry_window
        if win is not None and win.isVisible():
            win.metrics.add_sample(self._elapsed(), temp=self._ccd_temp())

    def _render_curves(self) -> None:
        """Re-render every curve surface from the engine's store (the ONLY
        rendering path for whole-store changes: batch adopt, object change)."""
        self._lightcurve_panel.set_curves(self._engine.lightcurves)
        win = self._photometry_window
        if win is not None:
            win.load_curves(
                self._engine.lightcurves,
                obscode=str(self._cfg("observer.obscode", "XXX") or "XXX"),
                filt=str(self._cfg("photometry.default_band", "TG") or "TG"),
            )
            # load_curves snapshots into a copy; keep exports on the live store.
            win.lightcurves = self._engine.lightcurves

    @pyqtSlot(object)
    def _on_photometry_point(self, point) -> None:
        """Render one differential point (typed PhotometryPoint) on the curve.

        The live dock always gets the point (it may be hidden but stays in sync);
        the floating window mirrors it only while shown."""
        self._lightcurve_panel.add_point(
            point.name,
            point.jd,
            point.mag,
            point.mag_err,
            saturated=point.saturated,
            role=point.role,
        )
        win = self._photometry_window
        if win is not None and win.isVisible():
            win.feed_point(point)

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
            self._elapsed(),
            sky=m.sky_adu,
            fwhm=pf.stars.mean_fwhm,
            hfd=m.hfd,
            stars=m.star_count,
            airmass=air,
        )

    def _ccd_temp(self) -> float | None:
        """Sensor temperature (read only when the photometry window is open — a
        solved frame is infrequent, so this off-cadence network read is cheap)."""
        return self._session.ccd_temperature()

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
            self.log_message.emit("WARN", f"{owner} running — it owns the camera. Stop it first.")
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
            self.log_message.emit("WARN", f"{owner} running — it owns the camera. Stop it first.")
            self._camera_dock.set_binning_support(cam.max_bin, cam.get_binning())
            return
        self._session.set_camera_binning(value)

    # ------------------------------------------------------------------
    # Sequence — the run is driven from the Sequencer page; Capture only
    # reacts to it (auto-solve arming, per-frame log lines)
    # ------------------------------------------------------------------

    @pyqtSlot(bool)
    def _on_sequence_running(self, running: bool) -> None:
        # Arm the periodic re-solve for the run (and restore the user's choice
        # after): it re-bases the WCS + live tracker so rigid-fit error never
        # accumulates, keeping markers and apertures on the stars all night.
        if running:
            self._auto_solve_before_seq = self._astrometry.auto
            if self._astrometry.wcs is not None and not self._astrometry.auto:
                self.auto_solve_armed.emit(True)  # menu action → set_auto via toggled
                self.log_message.emit("INFO", "Sequence: auto-solve armed for the run.")
        elif not getattr(self, "_auto_solve_before_seq", True):
            self.auto_solve_armed.emit(False)

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
        if self._batch_worker is not None:
            self._batch_worker.cancel()
            self._batch_worker.wait(3000)
            self._batch_worker = None
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
