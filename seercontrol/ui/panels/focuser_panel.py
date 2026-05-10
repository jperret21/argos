"""Focuser control panel — manual positioning + autofocus V-curve.

Dockable panel providing:
  - Connect / disconnect focuser (Alpaca device 0)
  - Current position display + manual move (absolute + step nudge)
  - Halt button
  - Autofocus V-curve: configurable exposure, gain, step range
  - Live HFD scatter plot (PyQtGraph)
"""

from __future__ import annotations

import logging

import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from seercontrol.core.alpaca.client import AlpacaError
from seercontrol.core.alpaca.focuser import Focuser
from seercontrol.core.config import Config
from seercontrol.ui import theme
from seercontrol.workers.autofocus_worker import AutofocusWorker

logger = logging.getLogger(__name__)


class FocuserPanel(QWidget):
    """Manual focuser control and autofocus V-curve panel.

    Signals:
        log_message:   (level, message) for the session log.
        status_changed: Short status string for the main window status bar.
    """

    log_message    = pyqtSignal(str, str)
    status_changed = pyqtSignal(str)

    def __init__(
        self,
        config: Config,
        camera=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config  = config
        self._camera  = camera   # may be None until set by main window
        self._focuser: Focuser | None = None
        self._af_worker: AutofocusWorker | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        root.addWidget(self._build_connection_group())
        root.addWidget(self._build_position_group())
        root.addWidget(self._build_manual_group())
        root.addWidget(self._build_af_group())
        root.addWidget(self._build_curve_widget())
        root.addStretch()

    def _build_connection_group(self) -> QGroupBox:
        grp = QGroupBox("Focuser")
        lay = QHBoxLayout(grp)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setFixedHeight(28)
        self._connect_btn.clicked.connect(self._on_connect)

        self._status_lbl = QLabel("Disconnected")
        self._status_lbl.setStyleSheet(f"color:{theme.TEXT_MUTED};")

        lay.addWidget(self._connect_btn)
        lay.addWidget(self._status_lbl)
        lay.addStretch()
        return grp

    def _build_position_group(self) -> QGroupBox:
        grp = QGroupBox("Position")
        lay = QHBoxLayout(grp)

        self._pos_lbl = QLabel("—")
        self._pos_lbl.setStyleSheet(
            f"color:{theme.ACCENT}; font-size:20px; font-weight:bold;"
        )
        self._pos_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pos_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._moving_lbl = QLabel("")
        self._moving_lbl.setStyleSheet(f"color:{theme.WARNING};")

        lay.addWidget(self._pos_lbl)
        lay.addWidget(self._moving_lbl)
        return grp

    def _build_manual_group(self) -> QGroupBox:
        grp = QGroupBox("Manual Control")
        lay = QVBoxLayout(grp)

        # Absolute move row
        abs_row = QHBoxLayout()
        self._abs_spin = QSpinBox()
        self._abs_spin.setRange(0, 20000)
        self._abs_spin.setValue(10000)
        self._abs_spin.setFixedWidth(90)
        self._move_btn = QPushButton("Move To")
        self._move_btn.setFixedHeight(26)
        self._move_btn.clicked.connect(self._on_move_to)
        abs_row.addWidget(QLabel("Position:"))
        abs_row.addWidget(self._abs_spin)
        abs_row.addWidget(self._move_btn)
        abs_row.addStretch()
        lay.addLayout(abs_row)

        # Nudge row
        nudge_row = QHBoxLayout()
        self._step_spin = QSpinBox()
        self._step_spin.setRange(1, 5000)
        self._step_spin.setValue(100)
        self._step_spin.setFixedWidth(80)

        self._in_btn  = QPushButton("◄ In")
        self._out_btn = QPushButton("Out ►")
        for btn in (self._in_btn, self._out_btn):
            btn.setFixedHeight(26)
            btn.setFixedWidth(70)
        self._in_btn.clicked.connect(self._on_nudge_in)
        self._out_btn.clicked.connect(self._on_nudge_out)

        self._halt_btn = QPushButton("Halt")
        self._halt_btn.setFixedHeight(26)
        self._halt_btn.setStyleSheet(f"background-color:{theme.DANGER};")
        self._halt_btn.clicked.connect(self._on_halt)

        nudge_row.addWidget(QLabel("Step:"))
        nudge_row.addWidget(self._step_spin)
        nudge_row.addWidget(self._in_btn)
        nudge_row.addWidget(self._out_btn)
        nudge_row.addSpacing(10)
        nudge_row.addWidget(self._halt_btn)
        nudge_row.addStretch()
        lay.addLayout(nudge_row)

        self._set_manual_enabled(False)
        return grp

    def _build_af_group(self) -> QGroupBox:
        grp = QGroupBox("Autofocus")
        lay = QFormLayout(grp)
        lay.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        self._af_exp_spin = QDoubleSpinBox()
        self._af_exp_spin.setRange(0.5, 30.0)
        self._af_exp_spin.setValue(3.0)
        self._af_exp_spin.setSingleStep(0.5)
        self._af_exp_spin.setSuffix(" s")
        self._af_exp_spin.setFixedWidth(90)

        self._af_gain_spin = QSpinBox()
        self._af_gain_spin.setRange(0, 600)
        self._af_gain_spin.setValue(80)
        self._af_gain_spin.setFixedWidth(80)

        self._af_range_spin = QSpinBox()
        self._af_range_spin.setRange(100, 10000)
        self._af_range_spin.setValue(1000)
        self._af_range_spin.setSingleStep(100)
        self._af_range_spin.setSuffix(" steps")
        self._af_range_spin.setFixedWidth(110)

        self._af_steps_spin = QSpinBox()
        self._af_steps_spin.setRange(3, 21)
        self._af_steps_spin.setValue(9)
        self._af_steps_spin.setFixedWidth(70)

        lay.addRow("Exposure:", self._af_exp_spin)
        lay.addRow("Gain:", self._af_gain_spin)
        lay.addRow("Scan range:", self._af_range_spin)
        lay.addRow("Steps:", self._af_steps_spin)

        btn_row = QHBoxLayout()
        self._af_btn = QPushButton("Start Autofocus")
        self._af_btn.setFixedHeight(28)
        self._af_btn.clicked.connect(self._on_af_start)

        self._af_abort_btn = QPushButton("Abort")
        self._af_abort_btn.setFixedHeight(28)
        self._af_abort_btn.setEnabled(False)
        self._af_abort_btn.clicked.connect(self._on_af_abort)

        self._af_progress_lbl = QLabel("")
        self._af_progress_lbl.setStyleSheet(f"color:{theme.TEXT_MUTED};")

        btn_row.addWidget(self._af_btn)
        btn_row.addWidget(self._af_abort_btn)
        btn_row.addWidget(self._af_progress_lbl)
        btn_row.addStretch()
        lay.addRow(btn_row)

        self._af_btn.setEnabled(False)
        return grp

    def _build_curve_widget(self) -> QWidget:
        container = QGroupBox("V-Curve (HFD vs Position)")
        lay = QVBoxLayout(container)

        self._plot = pg.PlotWidget()
        self._plot.setBackground(theme.SURFACE_2)
        self._plot.setLabel("left", "HFD (px)")
        self._plot.setLabel("bottom", "Focuser position")
        self._plot.showGrid(x=True, y=True, alpha=0.3)
        self._plot.setMinimumHeight(180)

        self._curve = self._plot.plot(
            [], [],
            pen=pg.mkPen(color=theme.ACCENT, width=1, style=Qt.PenStyle.DotLine),
            symbol="o",
            symbolBrush=theme.ACCENT,
            symbolSize=7,
        )
        self._best_line: pg.InfiniteLine | None = None

        lay.addWidget(self._plot)
        return container

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_camera(self, camera) -> None:
        """Inject camera reference (called from main window after camera connects)."""
        self._camera = camera
        self._refresh_af_button()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_connect(self) -> None:
        host = self._config.alpaca_host
        port = self._config.alpaca_port

        if self._focuser is not None:
            self._disconnect_focuser()
            return

        if not host:
            self._log("error", "No host configured — connect the mount first.")
            return

        try:
            foc = Focuser(host, port)
            foc.connect()
            self._focuser = foc
            self._abs_spin.setRange(0, foc.max_step)
            self._abs_spin.setValue(foc.get_position())
            self._connect_btn.setText("Disconnect")
            self._status_lbl.setText(f"Connected  max={foc.max_step}")
            self._status_lbl.setStyleSheet(f"color:{theme.SUCCESS};")
            self._set_manual_enabled(True)
            self._refresh_af_button()
            self._refresh_position()
            self.status_changed.emit("Focuser connected")
            self._log("info", f"Focuser connected  pos={foc.get_position()}  max={foc.max_step}")
        except AlpacaError as exc:
            self._log("error", f"Focuser connect failed: {exc}")

    def _disconnect_focuser(self) -> None:
        if self._focuser:
            self._focuser.disconnect()
            self._focuser = None
        self._connect_btn.setText("Connect")
        self._status_lbl.setText("Disconnected")
        self._status_lbl.setStyleSheet(f"color:{theme.TEXT_MUTED};")
        self._pos_lbl.setText("—")
        self._moving_lbl.setText("")
        self._set_manual_enabled(False)
        self._refresh_af_button()
        self.status_changed.emit("Focuser disconnected")

    def _on_move_to(self) -> None:
        if not self._focuser:
            return
        pos = self._abs_spin.value()
        try:
            self._focuser.move_to(pos)
            self._refresh_position()
        except AlpacaError as exc:
            self._log("error", f"Focuser move error: {exc}")

    def _on_nudge_in(self) -> None:
        if not self._focuser:
            return
        try:
            current = self._focuser.get_position()
            self._focuser.move_to(current - self._step_spin.value())
            self._refresh_position()
        except AlpacaError as exc:
            self._log("error", f"Focuser nudge error: {exc}")

    def _on_nudge_out(self) -> None:
        if not self._focuser:
            return
        try:
            current = self._focuser.get_position()
            self._focuser.move_to(current + self._step_spin.value())
            self._refresh_position()
        except AlpacaError as exc:
            self._log("error", f"Focuser nudge error: {exc}")

    def _on_halt(self) -> None:
        if not self._focuser:
            return
        try:
            self._focuser.halt()
            self._refresh_position()
        except AlpacaError as exc:
            self._log("error", f"Focuser halt error: {exc}")

    def _on_af_start(self) -> None:
        if not self._focuser or not self._camera:
            return

        self._clear_curve()
        self._af_btn.setEnabled(False)
        self._af_abort_btn.setEnabled(True)
        self._set_manual_enabled(False)
        self._af_progress_lbl.setText("Scanning…")

        n_steps = self._af_steps_spin.value()
        worker = AutofocusWorker(
            focuser=self._focuser,
            camera=self._camera,
            exposure=self._af_exp_spin.value(),
            gain=self._af_gain_spin.value(),
            n_steps=n_steps,
            half_range=self._af_range_spin.value(),
        )
        worker.data_point.connect(self._on_af_point)
        worker.progress.connect(lambda cur, tot: self._af_progress_lbl.setText(f"{cur}/{tot}"))
        worker.finished.connect(self._on_af_finished)
        worker.error_occurred.connect(self._on_af_error)
        self._af_worker = worker
        worker.start()

    def _on_af_abort(self) -> None:
        if self._af_worker:
            self._af_worker.abort()
            self._af_progress_lbl.setText("Aborting…")

    def _on_af_point(self, position: int, hfd: float) -> None:
        xs = list(self._curve.getData()[0] or []) + [position]
        ys = list(self._curve.getData()[1] or []) + [hfd]
        self._curve.setData(xs, ys)
        self._refresh_position()

    def _on_af_finished(self, best_pos: int, best_hfd: float) -> None:
        self._af_progress_lbl.setText(f"Done  pos={best_pos}  HFD={best_hfd:.1f}px")
        self._draw_best_line(best_pos)
        self._af_btn.setEnabled(True)
        self._af_abort_btn.setEnabled(False)
        self._set_manual_enabled(True)
        self._abs_spin.setValue(best_pos)
        self._refresh_position()
        self._log("info", f"Autofocus complete  best_pos={best_pos}  HFD={best_hfd:.1f}px")
        self.status_changed.emit(f"AF done  pos={best_pos}")

    def _on_af_error(self, msg: str) -> None:
        self._af_progress_lbl.setText("Error")
        self._af_btn.setEnabled(True)
        self._af_abort_btn.setEnabled(False)
        self._set_manual_enabled(True)
        self._log("error", f"Autofocus error: {msg}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _refresh_position(self) -> None:
        if not self._focuser:
            return
        try:
            pos = self._focuser.get_position()
            moving = self._focuser.is_moving()
            self._pos_lbl.setText(str(pos))
            self._moving_lbl.setText("Moving…" if moving else "")
            self._abs_spin.setValue(pos)
        except AlpacaError:
            pass

    def _set_manual_enabled(self, enabled: bool) -> None:
        for w in (self._abs_spin, self._move_btn, self._step_spin,
                  self._in_btn, self._out_btn, self._halt_btn):
            w.setEnabled(enabled)

    def _refresh_af_button(self) -> None:
        self._af_btn.setEnabled(
            self._focuser is not None and self._camera is not None
        )

    def _clear_curve(self) -> None:
        self._curve.setData([], [])
        if self._best_line is not None:
            self._plot.removeItem(self._best_line)
            self._best_line = None

    def _draw_best_line(self, position: int) -> None:
        if self._best_line is not None:
            self._plot.removeItem(self._best_line)
        self._best_line = pg.InfiniteLine(
            pos=position,
            angle=90,
            pen=pg.mkPen(color=theme.SUCCESS, width=2, style=Qt.PenStyle.DashLine),
            label=f"Best: {position}",
            labelOpts={"color": theme.SUCCESS, "position": 0.9},
        )
        self._plot.addItem(self._best_line)

    def _log(self, level: str, msg: str) -> None:
        logger.log({"info": 20, "warning": 30, "error": 40}.get(level, 20), msg)
        self.log_message.emit(level, msg)

    def shutdown(self) -> None:
        """Call before closing the application."""
        if self._af_worker and self._af_worker.isRunning():
            self._af_worker.abort()
            self._af_worker.wait(5000)
        if self._focuser:
            self._focuser.disconnect()
