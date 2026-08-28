"""Sequence panel — dockable multi-step acquisition planning workspace.

The sequence table is the stable centre.  Target search, plan options,
visibility, presets and controls are independent docks which can be moved,
tabbed, resized, or floated.  UI-only: builds a :class:`SequencePlan` from the
editable table and emits ``start/pause/resume/stop`` intents; the
``AcquisitionEngine`` drives the ``SequenceWorker`` and feeds progress back.

Presets: a plan (steps + options) saves/loads as JSON via the sequencer's
``plan_to_dict`` / ``plan_from_dict`` round-trip.
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

import pyqtgraph as pg
from PyQt6.QtCore import QByteArray, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QProgressBar,
    QSpinBox,
    QSizePolicy,
    QTableWidget,
    QMainWindow,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from argos.core.imaging.sequencer import (
    ON_COMPLETE_CHOICES,
    SequencePlan,
    SequenceStep,
    estimated_duration_s,
    plan_from_dict,
    plan_to_dict,
)
from argos.core.imaging.sky_geometry import upcoming_night_altitudes
from argos.ui import design, theme
from argos.ui.widgets.dock_host import make_dock, style_toggle_action

logger = logging.getLogger(__name__)

_FRAME_TYPES = ("Light", "Dark", "Flat", "Bias")
# Seestar wheel slot names (see alpaca.filterwheel.position_names) — "IR-cut"
# never matched a wheel position, so those steps silently kept the old filter.
_DEFAULT_FILTERS = ("IR", "LP", "Dark")
_COLUMNS = ("✓", "Type", "Filter", "Exp (s)", "Gain", "Count", "Interval (s)", "Dither every")

#: Fallback limits when no camera is connected (the historical hardcodes).
_DEFAULT_GAIN_RANGE = (0, 600)
_DEFAULT_EXPOSURE_RANGE = (0.01, 600.0)
_CFG_LAYOUT = "ui.sequencer.layout"


def _format_duration(seconds: float) -> str:
    m, s = divmod(max(0, int(seconds)), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"


class TargetVisibilityPlot(QWidget):
    """Compact, local-time altitude preview for the current sequence target."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(design.SPACING_SM)
        axis = pg.DateAxisItem(orientation="bottom")
        self._plot = pg.PlotWidget(axisItems={"bottom": axis})
        self._plot.setBackground(theme.BG2)
        self._plot.setMinimumHeight(145)
        self._plot.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._plot.showGrid(x=False, y=True, alpha=0.2)
        self._plot.getAxis("left").setLabel("Altitude (°)")
        self._plot.getAxis("bottom").setLabel("Local time")
        self._plot.getAxis("left").setTextPen(pg.mkPen(theme.FG_MUTED))
        self._plot.getAxis("bottom").setTextPen(pg.mkPen(theme.FG_MUTED))
        self._curve = self._plot.plot(pen=pg.mkPen(theme.ACCENT, width=2))
        transit_brush = QColor(theme.WARNING).darker(120)
        transit_brush.setAlpha(55)
        self._transit_region = pg.LinearRegionItem(
            values=(0, 0),
            movable=False,
            brush=pg.mkBrush(transit_brush),
            pen=pg.mkPen(theme.WARNING, width=1),
        )
        self._transit_region.setZValue(-5)
        self._transit_region.hide()
        self._plot.addItem(self._transit_region)
        self._horizon = pg.InfiniteLine(
            pos=30,
            angle=0,
            pen=pg.mkPen(theme.FG_MUTED, width=1, style=Qt.PenStyle.DashLine),
        )
        self._plot.addItem(self._horizon)
        self._plot.setYRange(-15, 90, padding=0)
        layout.addWidget(self._plot)
        self._summary = design.MutedLabel("Resolve a target to preview its altitude.")
        self._summary.setWordWrap(True)
        layout.addWidget(self._summary)

    def set_target(
        self,
        name: str,
        ra_hours: float,
        dec_degrees: float,
        lat: float,
        lon: float,
        *,
        night_date=None,
    ) -> None:
        samples = upcoming_night_altitudes(ra_hours, dec_degrees, lat, lon, now=night_date)
        if not samples:
            self.clear()
            return
        x = [when.timestamp() for when, _altitude in samples]
        y = [altitude for _when, altitude in samples]
        self._curve.setData(x, y)
        self._plot.setXRange(x[0], x[-1], padding=0.02)
        peak = max(range(len(y)), key=y.__getitem__)
        peak_when, peak_alt = samples[peak]
        self._summary.setText(
            f"{name}: highest {peak_alt:.1f}° at {peak_when.strftime('%H:%M')} local time. "
            "Dashed line: 30° altitude."
        )

    def clear(self) -> None:
        self._curve.setData([], [])
        self._transit_region.hide()
        self._summary.setText("Resolve a target to preview its altitude.")

    def set_transit_coverage(self, start, end) -> None:
        """Shade an exoplanet's full requested coverage on the altitude plot."""
        self._transit_region.setRegion((start.timestamp(), end.timestamp()))
        self._transit_region.show()


class SequencePanel(QWidget):
    """Editable, observer-arrangeable sequence planning workspace."""

    start_requested = pyqtSignal(object)  # SequencePlan
    object_name_changed = pyqtSignal(str)
    pause_requested = pyqtSignal()
    resume_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    object_lookup_requested = pyqtSignal(str)
    exoplanet_lookup_requested = pyqtSignal(str)
    transit_plan_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._filters = list(_DEFAULT_FILTERS)
        self._gain_range = _DEFAULT_GAIN_RANGE
        self._exposure_range = _DEFAULT_EXPOSURE_RANGE
        self._running = False
        self._paused = False
        self._active_row = -1
        self._device_states: dict[str, str] = {}
        self._build_ui()
        self._add_row()  # start with one editable row
        self._refresh_estimate()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # The Sequencer is a real dockable workspace rather than a fixed
        # right-hand rail.  The table remains the stable centre; every planning
        # aid can be moved, tabbed, resized or floated to another monitor.
        self._workspace = QMainWindow()
        self._workspace.setWindowFlags(Qt.WindowType.Widget)
        self._workspace.setDockNestingEnabled(True)
        self._workspace.setDockOptions(
            QMainWindow.DockOption.AnimatedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.GroupedDragging
        )

        # ── Stable centre: sequence table + row editing ────────────────
        steps = QWidget()
        left = QVBoxLayout(steps)
        left.setContentsMargins(
            design.SPACING_MD, design.SPACING_MD, design.SPACING_MD, design.SPACING_MD
        )
        left.setSpacing(design.SPACING_SM)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(list(_COLUMNS))
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for col in (1, 2):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        for col in range(3, len(_COLUMNS)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setMinimumHeight(120)
        self._table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        left.addWidget(self._table, 1)

        edit_row = QHBoxLayout()
        edit_row.setSpacing(design.SPACING_SM)
        for label, slot, tip in (
            ("＋ Add", self._add_row, "Add a step"),
            ("⧉ Dup", self._duplicate_row, "Duplicate the selected step"),
            ("－ Remove", self._remove_row, "Remove the selected step"),
            ("↑", self._move_up, "Move step up"),
            ("↓", self._move_down, "Move step down"),
        ):
            btn = design.SecondaryButton(label)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            edit_row.addWidget(btn)
        edit_row.addStretch()
        self._estimate_lbl = design.MutedLabel("")
        self._estimate_lbl.setWordWrap(True)
        self._estimate_lbl.setToolTip(
            "Exposures + intervals + per-frame overhead; autofocus passes not counted"
        )
        edit_row.addWidget(self._estimate_lbl)
        left.addLayout(edit_row)
        self._workspace.setCentralWidget(steps)

        # ── Individually dockable planning panels ──────────────────────
        search_panel = QWidget()
        search_l = QVBoxLayout(search_panel)
        search_l.setContentsMargins(0, 0, 0, 0)
        search_l.setSpacing(design.SPACING_SM)
        search_row = QHBoxLayout()
        search_row.setSpacing(design.SPACING_SM)
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("M 42, NGC 7000, HD 189733…")
        self._search_edit.setToolTip("Search an astronomical catalogue by designation")
        self._search_edit.returnPressed.connect(self._request_object_lookup)
        search_row.addWidget(self._search_edit, 1)
        self._search_btn = design.SecondaryButton("Find")
        self._search_btn.clicked.connect(self._request_object_lookup)
        search_row.addWidget(self._search_btn)
        search_l.addLayout(search_row)
        self._search_result = design.MutedLabel(
            "Select a target for this plan. Telescope pointing stays a separate action."
        )
        self._search_result.setWordWrap(True)
        search_l.addWidget(self._search_result)

        plan_panel = QWidget()
        plan_l = QVBoxLayout(plan_panel)
        plan_l.setContentsMargins(0, 0, 0, 0)
        opts = QGridLayout()
        opts.setHorizontalSpacing(design.SPACING_MD)
        opts.setVerticalSpacing(design.SPACING_SM)
        opts.setColumnStretch(1, 1)
        opts.addWidget(design.MutedLabel("Object"), 0, 0)
        self._object_edit = QLineEdit()
        self._object_edit.setPlaceholderText("M42, T CrB…")
        self._object_edit.editingFinished.connect(self._on_object_edited)
        opts.addWidget(self._object_edit, 0, 1)
        opts.addWidget(design.MutedLabel("Repeat ×"), 1, 0)
        self._repeat_spin = QSpinBox()
        self._repeat_spin.setRange(1, 999)
        self._repeat_spin.valueChanged.connect(self._refresh_estimate)
        opts.addWidget(self._repeat_spin, 1, 1)
        opts.addWidget(design.MutedLabel("AF every"), 2, 0)
        self._af_spin = QSpinBox()
        self._af_spin.setRange(0, 999)
        self._af_spin.setSuffix(" frames (0=off)")
        opts.addWidget(self._af_spin, 2, 1)
        self._af_filter_chk = QCheckBox("AF on filter change")
        opts.addWidget(self._af_filter_chk, 3, 0, 1, 2)
        opts.addWidget(design.MutedLabel("When done"), 4, 0)
        self._on_complete_combo = QComboBox()
        self._on_complete_combo.addItems(ON_COMPLETE_CHOICES)
        self._on_complete_combo.setToolTip(
            "Mount action after FULL completion only — never after a stop or error"
        )
        opts.addWidget(self._on_complete_combo, 4, 1)
        plan_l.addLayout(opts)

        visibility_panel = QWidget()
        visibility_l = QVBoxLayout(visibility_panel)
        visibility_l.setContentsMargins(0, 0, 0, 0)
        self._visibility_plot = TargetVisibilityPlot()
        visibility_l.addWidget(self._visibility_plot)

        # A transit is planned differently from a generic catalogue target:
        # the planet name resolves to its host star, and the observer needs an
        # uninterrupted light-only cadence plus out-of-transit baselines.
        transit_panel = QWidget()
        transit_l = QVBoxLayout(transit_panel)
        transit_l.setContentsMargins(0, 0, 0, 0)
        transit_l.setSpacing(design.SPACING_SM)
        transit_search = QHBoxLayout()
        transit_search.setSpacing(design.SPACING_SM)
        self._transit_edit = QLineEdit()
        self._transit_edit.setPlaceholderText("HD 189733 b, WASP-12 b…")
        self._transit_edit.setToolTip(
            "Search the NASA Exoplanet Archive for a published transit ephemeris"
        )
        self._transit_edit.returnPressed.connect(self._request_exoplanet_lookup)
        transit_search.addWidget(self._transit_edit, 1)
        self._transit_search_btn = design.SecondaryButton("Find planet")
        self._transit_search_btn.clicked.connect(self._request_exoplanet_lookup)
        transit_search.addWidget(self._transit_search_btn)
        transit_l.addLayout(transit_search)
        self._transit_result = design.MutedLabel(
            "Find a confirmed planet to prepare a stable, single-filter transit sequence."
        )
        self._transit_result.setWordWrap(True)
        transit_l.addWidget(self._transit_result)
        transit_opts = QGridLayout()
        transit_opts.setHorizontalSpacing(design.SPACING_MD)
        transit_opts.setVerticalSpacing(design.SPACING_SM)
        transit_opts.setColumnStretch(1, 1)
        transit_opts.addWidget(design.MutedLabel("Baseline"), 0, 0)
        self._transit_baseline_spin = QSpinBox()
        self._transit_baseline_spin.setRange(0, 240)
        self._transit_baseline_spin.setValue(60)
        self._transit_baseline_spin.setSuffix(" min each side")
        self._transit_baseline_spin.setToolTip(
            "Out-of-transit coverage before ingress and after egress"
        )
        transit_opts.addWidget(self._transit_baseline_spin, 0, 1)
        transit_opts.addWidget(design.MutedLabel("Exposure"), 1, 0)
        self._transit_exposure_spin = QDoubleSpinBox()
        self._transit_exposure_spin.setRange(*self._exposure_range)
        self._transit_exposure_spin.setDecimals(2)
        self._transit_exposure_spin.setValue(10.0)
        self._transit_exposure_spin.setSuffix(" s")
        transit_opts.addWidget(self._transit_exposure_spin, 1, 1)
        transit_opts.addWidget(design.MutedLabel("Cadence"), 2, 0)
        self._transit_cadence_spin = QDoubleSpinBox()
        self._transit_cadence_spin.setRange(0.01, 3600.0)
        self._transit_cadence_spin.setDecimals(1)
        self._transit_cadence_spin.setValue(13.0)
        self._transit_cadence_spin.setSuffix(" s")
        self._transit_cadence_spin.setToolTip(
            "Start-to-start cadence; includes the exposure and any idle interval"
        )
        transit_opts.addWidget(self._transit_cadence_spin, 2, 1)
        transit_opts.addWidget(design.MutedLabel("Gain"), 3, 0)
        self._transit_gain_spin = QSpinBox()
        self._transit_gain_spin.setRange(*self._gain_range)
        self._transit_gain_spin.setValue(80)
        transit_opts.addWidget(self._transit_gain_spin, 3, 1)
        transit_opts.addWidget(design.MutedLabel("Filter"), 4, 0)
        self._transit_filter_combo = QComboBox()
        self._transit_filter_combo.addItems(self._filters)
        self._transit_filter_combo.setToolTip(
            "Keep one filter for the entire transit; do not change filters mid-series"
        )
        transit_opts.addWidget(self._transit_filter_combo, 4, 1)
        transit_l.addLayout(transit_opts)
        self._prepare_transit_btn = design.SuccessButton("Prepare transit sequence")
        self._prepare_transit_btn.setEnabled(False)
        self._prepare_transit_btn.setToolTip(
            "Replace the table with one uninterrupted light-only acquisition step"
        )
        self._prepare_transit_btn.clicked.connect(self.transit_plan_requested)
        transit_l.addLayout(design.button_row(self._prepare_transit_btn))

        presets_panel = QWidget()
        presets_l = QVBoxLayout(presets_panel)
        presets_l.setContentsMargins(0, 0, 0, 0)
        preset_row = QHBoxLayout()
        preset_row.setSpacing(design.SPACING_SM)
        save_btn = design.SecondaryButton("Save preset…")
        save_btn.clicked.connect(self._on_save_preset)
        load_btn = design.SecondaryButton("Load preset…")
        load_btn.clicked.connect(self._on_load_preset)
        preset_row.addWidget(save_btn, 1)
        preset_row.addWidget(load_btn, 1)
        presets_l.addLayout(preset_row)

        run_panel = QWidget()
        run_l = QVBoxLayout(run_panel)
        run_l.setContentsMargins(0, 0, 0, 0)
        self._start_btn = design.SuccessButton("▶  Start sequence")
        self._start_btn.clicked.connect(self._on_start)
        self._pause_btn = design.SecondaryButton("⏸  Pause")
        self._pause_btn.setToolTip("Hold after the current frame; Resume releases it")
        self._pause_btn.clicked.connect(self._on_pause_clicked)
        self._pause_btn.setEnabled(False)
        self._stop_btn = design.DangerButton("■  Stop")
        self._stop_btn.clicked.connect(self.stop_requested)
        self._stop_btn.setEnabled(False)
        run_l.addLayout(design.button_row(self._start_btn))
        run_l.addLayout(design.button_row(self._pause_btn, self._stop_btn))

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        run_l.addWidget(self._progress)
        self._status_lbl = design.MutedLabel("")
        self._status_lbl.setWordWrap(True)
        run_l.addWidget(self._status_lbl)
        self._readiness_lbl = design.MutedLabel()
        self._readiness_lbl.setWordWrap(True)
        self._readiness_lbl.setToolTip(
            "A compact pre-flight check. Argos still validates the hardware when you start."
        )
        run_l.addWidget(self._readiness_lbl)

        self._docks = {
            "search": make_dock("Target search", search_panel, object_name="sequencer.search"),
            "transit": make_dock(
                "Exoplanet transit", transit_panel, object_name="sequencer.transit"
            ),
            "plan": make_dock("Plan settings", plan_panel, object_name="sequencer.plan"),
            "visibility": make_dock(
                "Target visibility",
                visibility_panel,
                object_name="sequencer.visibility",
                scroll=False,
            ),
            "presets": make_dock("Presets", presets_panel, object_name="sequencer.presets"),
            "run": make_dock("Sequence control", run_panel, object_name="sequencer.run"),
        }
        self._apply_default_layout()
        self._restore_layout()
        body.addWidget(self._build_panel_bar())
        body.addWidget(self._workspace, 1)
        self._refresh_readiness()

    def _build_panel_bar(self) -> QToolBar:
        """Reveal/recover planning panels after the observer rearranges them."""
        bar = QToolBar()
        bar.setMovable(False)
        bar.setStyleSheet(
            f"QToolBar {{ background-color: {theme.SURFACE_3};"
            f" border-bottom: 1px solid {theme.SURFACE_4}; padding: 2px 6px; spacing: 4px; }}"
            f" QToolBar QToolButton {{ color: {theme.FG_MUTED}; font-size: 11px;"
            f" padding: 1px 8px; }} QToolBar QToolButton:checked {{ color: {theme.FG}; }}"
        )
        for key, label in (
            ("search", "Target search"),
            ("transit", "Exoplanet transit"),
            ("plan", "Plan settings"),
            ("visibility", "Visibility"),
            ("presets", "Presets"),
            ("run", "Sequence control"),
        ):
            action = style_toggle_action(self._docks[key].toggleViewAction(), label)
            action.setToolTip("Drag the panel title to arrange it; double-click to detach it.")
            bar.addAction(action)
        reset = QAction("Reset panels", bar)
        reset.setToolTip("Restore the default Sequencer panel arrangement")
        reset.triggered.connect(self.reset_layout)
        bar.addAction(reset)
        return bar

    def _apply_default_layout(self) -> None:
        workspace = self._workspace
        right = Qt.DockWidgetArea.RightDockWidgetArea
        bottom = Qt.DockWidgetArea.BottomDockWidgetArea
        workspace.addDockWidget(right, self._docks["search"])
        workspace.splitDockWidget(
            self._docks["search"], self._docks["transit"], Qt.Orientation.Vertical
        )
        workspace.splitDockWidget(
            self._docks["transit"], self._docks["visibility"], Qt.Orientation.Vertical
        )
        workspace.splitDockWidget(
            self._docks["visibility"], self._docks["plan"], Qt.Orientation.Vertical
        )
        workspace.addDockWidget(bottom, self._docks["run"])
        workspace.addDockWidget(bottom, self._docks["presets"])
        workspace.tabifyDockWidget(self._docks["run"], self._docks["presets"])
        self._docks["run"].raise_()

    def _restore_layout(self) -> None:
        """Restore the observer's panel arrangement if it was saved previously."""
        blob = self._config.get(_CFG_LAYOUT) if hasattr(self, "_config") else None
        if not blob:
            return
        try:
            self._workspace.restoreState(QByteArray(base64.b64decode(blob)))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sequencer layout restore failed: %s", exc)

    def set_config(self, config) -> None:
        """Attach persistence after construction without coupling this UI to Config."""
        self._config = config
        self._restore_layout()

    def save_layout(self) -> None:
        if hasattr(self, "_config"):
            state = bytes(self._workspace.saveState())
            self._config.set(_CFG_LAYOUT, base64.b64encode(state).decode())

    def reset_layout(self) -> None:
        if hasattr(self, "_config"):
            self._config.set(_CFG_LAYOUT, None)
        self._apply_default_layout()

    def _request_object_lookup(self) -> None:
        self.object_lookup_requested.emit(self._search_edit.text().strip())

    def _request_exoplanet_lookup(self) -> None:
        self.exoplanet_lookup_requested.emit(self._transit_edit.text().strip())

    def set_lookup_busy(self, busy: bool) -> None:
        self._search_edit.setEnabled(not busy)
        self._search_btn.setEnabled(not busy)
        if busy:
            self._search_result.setText("Searching catalogue…")

    def set_lookup_result(self, result) -> None:
        type_suffix = f" · {result.object_type}" if result.object_type else ""
        self._search_result.setText(
            f"{result.name}{type_suffix}\nRA {result.ra_hours:.5f} h · Dec {result.dec_degrees:+.5f}°\n"
            "Selected for the plan; telescope pointing remains manual."
        )

    def set_lookup_error(self, message: str) -> None:
        self._search_result.setText(message)

    def set_exoplanet_lookup_busy(self, busy: bool) -> None:
        self._transit_edit.setEnabled(not busy)
        self._transit_search_btn.setEnabled(not busy)
        if busy:
            self._transit_result.setText("Searching NASA Exoplanet Archive…")

    def set_exoplanet_result(self, target, window=None, local_mid=None) -> None:
        """Show a published ephemeris and its current coverage window."""
        duration = (
            f"{target.duration_hours:.2f} h"
            if target.duration_hours is not None
            else "not published"
        )
        depth = (
            f"{target.depth_percent:.3g}%" if target.depth_percent is not None else "not published"
        )
        text = (
            f"{target.planet_name} — host: {target.host_name}\n"
            f"P {target.period_days:.8f} d · duration {duration} · depth {depth}\n"
            f"Epoch: {target.epoch_bjd_tdb:.6f} ({target.epoch_system})"
        )
        if window is not None:
            text += (
                f"\nNext mid-transit: BJD_TDB {window.mid_bjd_tdb:.6f} "
                f"(E={window.epoch_number}); coverage {window.coverage_hours:.2f} h."
            )
            if local_mid is not None:
                text += f"\nApprox. local midpoint: {local_mid.strftime('%Y-%m-%d %H:%M %Z')}."
        else:
            text += "\nSet the observing site to calculate the next coverage window."
        text += "\nNASA ephemeris: verify close to the observing night."
        self._transit_result.setText(text)
        self._prepare_transit_btn.setEnabled(window is not None)

    def set_exoplanet_error(self, message: str) -> None:
        self._transit_result.setText(message)
        self._prepare_transit_btn.setEnabled(False)

    def transit_settings(self) -> dict[str, float | int | str]:
        """Return the observer-selected, stable cadence settings."""
        return {
            "baseline_minutes": float(self._transit_baseline_spin.value()),
            "exposure_s": float(self._transit_exposure_spin.value()),
            "cadence_s": float(self._transit_cadence_spin.value()),
            "gain": int(self._transit_gain_spin.value()),
            "filter_name": self._transit_filter_combo.currentText(),
        }

    # ------------------------------------------------------------------
    # Row management
    # ------------------------------------------------------------------

    def _add_row(self, step: SequenceStep | None = None) -> None:
        step = step or SequenceStep()
        r = self._table.rowCount()
        self._table.insertRow(r)

        chk = QCheckBox()
        chk.setChecked(step.enabled)
        chk.toggled.connect(self._refresh_estimate)
        wrap = QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(chk)
        self._table.setCellWidget(r, 0, wrap)

        type_combo = QComboBox()
        type_combo.addItems(_FRAME_TYPES)
        type_combo.setCurrentText(step.frame_type)
        self._table.setCellWidget(r, 1, type_combo)

        filter_combo = QComboBox()
        filter_combo.addItems(self._filters)
        idx = filter_combo.findText(step.filter_name)
        if idx >= 0:
            filter_combo.setCurrentIndex(idx)
        self._table.setCellWidget(r, 2, filter_combo)

        exp = QDoubleSpinBox()
        exp.setRange(*self._exposure_range)
        exp.setDecimals(2)
        exp.setValue(step.exposure_s)
        exp.valueChanged.connect(self._refresh_estimate)
        self._table.setCellWidget(r, 3, exp)

        gain = QSpinBox()
        gain.setRange(*self._gain_range)
        gain.setValue(step.gain)
        self._table.setCellWidget(r, 4, gain)

        count = QSpinBox()
        count.setRange(1, 9999)
        count.setValue(step.count)
        count.valueChanged.connect(self._refresh_estimate)
        self._table.setCellWidget(r, 5, count)

        interval = QDoubleSpinBox()
        interval.setRange(0.0, 3600.0)
        interval.setDecimals(1)
        interval.setValue(step.interval_s)
        interval.setToolTip("Idle delay after each frame of this step")
        interval.valueChanged.connect(self._refresh_estimate)
        self._table.setCellWidget(r, 6, interval)

        dither = QSpinBox()
        dither.setRange(0, 999)
        dither.setValue(step.dither_every)
        dither.setSpecialValueText("off")
        dither.setToolTip("Nudge the mount a few arcminutes every N frames (0 = off)")
        self._table.setCellWidget(r, 7, dither)

        self._table.selectRow(r)
        self._refresh_estimate()

    def _selected_row(self) -> int:
        rows = self._table.selectionModel().selectedRows()
        if rows:
            return rows[0].row()
        return self._table.rowCount() - 1

    def _duplicate_row(self) -> None:
        r = self._selected_row()
        if r < 0:
            return
        self._add_row(self._read_step(r))

    def _remove_row(self) -> None:
        r = self._selected_row()
        if r >= 0 and self._table.rowCount() > 1:
            self._table.removeRow(r)
            self._refresh_estimate()

    def _move_up(self) -> None:
        self._swap_rows(self._selected_row(), self._selected_row() - 1)

    def _move_down(self) -> None:
        self._swap_rows(self._selected_row(), self._selected_row() + 1)

    def _swap_rows(self, a: int, b: int) -> None:
        if a < 0 or b < 0 or a >= self._table.rowCount() or b >= self._table.rowCount():
            return
        step_a, step_b = self._read_step(a), self._read_step(b)
        self._write_step(a, step_b)
        self._write_step(b, step_a)
        self._table.selectRow(b)

    # ------------------------------------------------------------------
    # Read / write a row <-> SequenceStep
    # ------------------------------------------------------------------

    def _read_step(self, r: int) -> SequenceStep:
        chk = self._table.cellWidget(r, 0).findChild(QCheckBox)
        return SequenceStep(
            enabled=chk.isChecked() if chk else True,
            frame_type=self._table.cellWidget(r, 1).currentText(),
            filter_name=self._table.cellWidget(r, 2).currentText(),
            exposure_s=float(self._table.cellWidget(r, 3).value()),
            gain=int(self._table.cellWidget(r, 4).value()),
            count=int(self._table.cellWidget(r, 5).value()),
            interval_s=float(self._table.cellWidget(r, 6).value()),
            dither_every=int(self._table.cellWidget(r, 7).value()),
        )

    def _write_step(self, r: int, step: SequenceStep) -> None:
        chk = self._table.cellWidget(r, 0).findChild(QCheckBox)
        if chk:
            chk.setChecked(step.enabled)
        self._table.cellWidget(r, 1).setCurrentText(step.frame_type)
        self._table.cellWidget(r, 2).setCurrentText(step.filter_name)
        self._table.cellWidget(r, 3).setValue(step.exposure_s)
        self._table.cellWidget(r, 4).setValue(step.gain)
        self._table.cellWidget(r, 5).setValue(step.count)
        self._table.cellWidget(r, 6).setValue(step.interval_s)
        self._table.cellWidget(r, 7).setValue(step.dither_every)

    def to_plan(self) -> SequencePlan:
        steps = [self._read_step(r) for r in range(self._table.rowCount())]
        return SequencePlan(
            steps=steps,
            object_name=self._object_edit.text().strip(),
            repeat=int(self._repeat_spin.value()),
            autofocus_every_n=int(self._af_spin.value()),
            autofocus_on_filter_change=self._af_filter_chk.isChecked(),
            on_complete=self._on_complete_combo.currentText(),
        )

    def load_plan(self, plan: SequencePlan) -> None:
        """Replace the whole editor state with ``plan`` (preset load)."""
        self._table.setRowCount(0)
        for step in plan.steps or [SequenceStep()]:
            self._add_row(step)
        self.set_object_name(plan.object_name, emit=True)
        self._repeat_spin.setValue(max(1, plan.repeat))
        self._af_spin.setValue(max(0, plan.autofocus_every_n))
        self._af_filter_chk.setChecked(plan.autofocus_on_filter_change)
        idx = self._on_complete_combo.findText(plan.on_complete)
        self._on_complete_combo.setCurrentIndex(max(0, idx))
        self._refresh_estimate()

    def set_object_name(self, name: str, *, emit: bool = False) -> None:
        """Set the shared observation object without feeding a signal loop."""
        value = (name or "").strip()
        if self._object_edit.text() == value:
            return
        self._object_edit.setText(value)
        self._refresh_readiness()
        if emit:
            self._on_object_edited()

    def set_target_coordinates(
        self, name: str, ra_hours: float, dec_degrees: float, site_lat: float, site_lon: float
    ) -> None:
        """Update the visibility card from a Telescope catalogue resolution."""
        self.set_object_name(name)
        self._visibility_plot.set_target(name, ra_hours, dec_degrees, site_lat, site_lon)

    def set_transit_visibility(
        self,
        name: str,
        ra_hours: float,
        dec_degrees: float,
        site_lat: float,
        site_lon: float,
        coverage_start,
        coverage_end,
    ) -> None:
        """Show the altitude curve for the transit night and shade its coverage."""
        midpoint = coverage_start + (coverage_end - coverage_start) / 2
        self.set_object_name(name)
        self._visibility_plot.set_target(
            name,
            ra_hours,
            dec_degrees,
            site_lat,
            site_lon,
            night_date=midpoint,
        )
        self._visibility_plot.set_transit_coverage(coverage_start, coverage_end)

    def _on_object_edited(self) -> None:
        self._refresh_readiness()
        self.object_name_changed.emit(self._object_edit.text().strip())

    # ------------------------------------------------------------------
    # Presets (JSON on disk)
    # ------------------------------------------------------------------

    def _presets_dir(self) -> str:
        d = Path.home() / "Argos" / "sequences"
        d.mkdir(parents=True, exist_ok=True)
        return str(d)

    def _on_save_preset(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save sequence preset", self._presets_dir(), "Sequence preset (*.json)"
        )
        if not path:
            return
        if not path.endswith(".json"):
            path += ".json"
        try:
            Path(path).write_text(json.dumps(plan_to_dict(self.to_plan()), indent=2))
            self.set_status(f"Preset saved: {Path(path).name}")
        except OSError as exc:
            self.set_status(f"Preset save failed: {exc}")

    def _on_load_preset(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load sequence preset", self._presets_dir(), "Sequence preset (*.json)"
        )
        if not path:
            return
        try:
            plan = plan_from_dict(json.loads(Path(path).read_text()))
        except (OSError, ValueError, TypeError) as exc:
            self.set_status(f"Preset load failed: {exc}")
            return
        self.load_plan(plan)
        self.set_status(f"Preset loaded: {Path(path).name}")

    # ------------------------------------------------------------------
    # Public API (called by ImagingPage)
    # ------------------------------------------------------------------

    def set_camera_limits(
        self,
        gain_min: int | None = None,
        gain_max: int | None = None,
        exposure_min: float | None = None,
        exposure_max: float | None = None,
    ) -> None:
        """Retarget the per-step exposure/gain spinboxes to the connected
        camera's driver-reported limits; ``None``s restore the defaults."""
        if gain_min is not None and gain_max is not None and gain_max > gain_min:
            self._gain_range = (int(gain_min), int(gain_max))
        else:
            self._gain_range = _DEFAULT_GAIN_RANGE
        if exposure_min is not None and exposure_max is not None:
            lo = max(float(exposure_min), _DEFAULT_EXPOSURE_RANGE[0])
            if exposure_max > lo:
                self._exposure_range = (lo, float(exposure_max))
            else:
                self._exposure_range = _DEFAULT_EXPOSURE_RANGE
        else:
            self._exposure_range = _DEFAULT_EXPOSURE_RANGE
        for r in range(self._table.rowCount()):
            self._table.cellWidget(r, 3).setRange(*self._exposure_range)
            self._table.cellWidget(r, 4).setRange(*self._gain_range)
        self._transit_exposure_spin.setRange(*self._exposure_range)
        self._transit_gain_spin.setRange(*self._gain_range)

    def set_filter_options(self, names: list[str]) -> None:
        self._filters = list(names or _DEFAULT_FILTERS)
        for r in range(self._table.rowCount()):
            combo = self._table.cellWidget(r, 2)
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(self._filters)
            idx = combo.findText(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.blockSignals(False)
        current = self._transit_filter_combo.currentText()
        self._transit_filter_combo.blockSignals(True)
        self._transit_filter_combo.clear()
        self._transit_filter_combo.addItems(self._filters)
        idx = self._transit_filter_combo.findText(current)
        if idx >= 0:
            self._transit_filter_combo.setCurrentIndex(idx)
        self._transit_filter_combo.blockSignals(False)

    def set_running(self, running: bool) -> None:
        self._running = running
        self._start_btn.setEnabled(not running)
        self._pause_btn.setEnabled(running)
        self._stop_btn.setEnabled(running)
        self._table.setEnabled(not running)
        self._progress.setVisible(running)
        if not running:
            self._status_lbl.setText("")
            self.set_paused(False)
            self.set_active_step(-1)

    def set_device_state(self, device: str, state: str) -> None:
        """Update the observer-facing pre-flight summary.

        The start action remains available for offline plan editing and for
        calibration-only runs; the engine stays the authority that accepts or
        refuses a run.  This is deliberately guidance, not a second validator.
        """
        self._device_states[device] = state
        self._refresh_readiness()

    def set_paused(self, paused: bool) -> None:
        """Reflect the worker's pause state on the button."""
        self._paused = paused
        self._pause_btn.setText("▶  Resume" if paused else "⏸  Pause")
        if paused:
            self._status_lbl.setText("Paused — the current frame was saved.")

    def set_active_step(self, index: int) -> None:
        """Highlight the running step's row (-1 clears)."""
        self._active_row = index
        for r in range(self._table.rowCount()):
            for col in range(self._table.columnCount()):
                w = self._table.cellWidget(r, col)
                if w is not None:
                    w.setStyleSheet(f"background:{theme.SURFACE_3};" if r == index else "")

    def set_progress(self, done: int, total: int, eta_seconds: float) -> None:
        self._progress.setRange(0, max(1, total))
        self._progress.setValue(done)
        self._progress.setFormat(f"%v / {total}")
        self._status_lbl.setText(f"Frame {done}/{total} — ETA {_format_duration(eta_seconds)}")

    def set_status(self, text: str) -> None:
        self._status_lbl.setText(text)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _refresh_estimate(self, *_args) -> None:
        try:
            est = estimated_duration_s(self.to_plan())
        except (AttributeError, RuntimeError):
            return  # a row is mid-construction
        self._estimate_lbl.setText(f"≈ {_format_duration(est)} total" if est > 0 else "")

    def _refresh_readiness(self) -> None:
        """Explain the next useful action without turning the Run card into a log."""
        camera_state = self._device_states.get("camera")
        object_name = self._object_edit.text().strip()
        if camera_state != "connected":
            message = "Pre-flight: connect the camera before starting."
            color = theme.WARNING
        elif not object_name:
            message = "Pre-flight: add an object name to organise this run."
            color = theme.WARNING
        else:
            mount_state = self._device_states.get("mount")
            suffix = " Telescope is not connected." if mount_state != "connected" else ""
            message = f"Pre-flight: ready to start.{suffix}"
            color = theme.SUCCESS if not suffix else theme.WARNING
        self._readiness_lbl.setText(message)
        self._readiness_lbl.setStyleSheet(
            f"color:{color}; font-size:{design.FONT_SIZE_SMALL}px; background:transparent;"
        )

    def _on_pause_clicked(self) -> None:
        if self._paused:
            self.resume_requested.emit()
        else:
            self.pause_requested.emit()

    def _on_start(self) -> None:
        plan = self.to_plan()
        if not any(s.enabled and s.count > 0 for s in plan.steps):
            self._status_lbl.setText("Add at least one enabled step.")
            self._status_lbl.setStyleSheet(f"color:{theme.WARNING};")
            return
        self._status_lbl.setStyleSheet("")
        self.start_requested.emit(plan)
