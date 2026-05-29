"""Stellarium integration card — TCP server toggle + HTTP "Pull selected" button.

Embedded inside the capture panel as a Siril-style card (QGroupBox). The card
does not own the worker or the HTTP client itself: it emits intents
(``start_server_requested``, ``stop_server_requested``, ``pull_requested``)
and accepts state updates (``set_server_state``, ``set_client_count``).
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from seercontrol.ui import theme

logger = logging.getLogger(__name__)


class StellariumCard(QGroupBox):
    """Compact control panel for Stellarium integration.

    Signals:
        start_server_requested(host, port): user toggled the server ON
        stop_server_requested():            user toggled the server OFF
        pull_requested(host, port):         user clicked "Pull selected"
    """

    start_server_requested = pyqtSignal(str, int)
    stop_server_requested  = pyqtSignal()
    pull_requested         = pyqtSignal(str, int)

    def __init__(
        self,
        host: str = "127.0.0.1",
        tcp_port: int = 10001,
        http_port: int = 8090,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__("Stellarium", parent)
        self._host = host
        self._server_running = False
        self._build_ui(tcp_port, http_port)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self, tcp_port: int, http_port: int) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 12, 8, 8)
        outer.setSpacing(8)

        # --- Server row ----------------------------------------------------
        srv_grid = QGridLayout()
        srv_grid.setSpacing(5)
        srv_grid.setColumnStretch(2, 1)

        srv_grid.addWidget(_muted("TCP port"), 0, 0)
        self._tcp_port_spin = QSpinBox()
        self._tcp_port_spin.setRange(1024, 65535)
        self._tcp_port_spin.setValue(tcp_port)
        srv_grid.addWidget(self._tcp_port_spin, 0, 1)

        self._server_btn = QPushButton("▶  Start server")
        self._server_btn.setProperty("class", "primary")
        self._server_btn.clicked.connect(self._on_server_toggle)
        srv_grid.addWidget(self._server_btn, 0, 2)

        outer.addLayout(srv_grid)

        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        self._status_lbl = QLabel("○  stopped")
        self._status_lbl.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:11px; background:transparent;"
        )
        status_row.addWidget(self._status_lbl, 1)

        self._client_lbl = QLabel("0 clients")
        self._client_lbl.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:11px; background:transparent;"
        )
        self._client_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        status_row.addWidget(self._client_lbl)
        outer.addLayout(status_row)

        # --- Separator ---------------------------------------------------
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{theme.BORDER};")
        outer.addWidget(sep)

        # --- Pull row ----------------------------------------------------
        pull_grid = QGridLayout()
        pull_grid.setSpacing(5)
        pull_grid.setColumnStretch(2, 1)

        pull_grid.addWidget(_muted("HTTP port"), 0, 0)
        self._http_port_spin = QSpinBox()
        self._http_port_spin.setRange(1024, 65535)
        self._http_port_spin.setValue(http_port)
        pull_grid.addWidget(self._http_port_spin, 0, 1)

        self._pull_btn = QPushButton("⇣  Pull selected")
        self._pull_btn.clicked.connect(self._on_pull_clicked)
        pull_grid.addWidget(self._pull_btn, 0, 2)
        outer.addLayout(pull_grid)

        hint = _muted("Enable “Remote Control” plugin in Stellarium first.")
        hint.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:10px;"
            f" background:transparent; padding-top:2px;"
        )
        outer.addWidget(hint)

    # ------------------------------------------------------------------
    # Slot API (called by MainWindow / worker signals)
    # ------------------------------------------------------------------

    def set_server_state(self, running: bool, message: str = "") -> None:
        self._server_running = running
        if running:
            self._server_btn.setText("■  Stop server")
            self._server_btn.setProperty("class", "danger")
            text = message or f"●  listening on :{self._tcp_port_spin.value()}"
            self._status_lbl.setText(text)
            self._status_lbl.setStyleSheet(
                f"color:{theme.SUCCESS}; font-size:11px; background:transparent;"
            )
        else:
            self._server_btn.setText("▶  Start server")
            self._server_btn.setProperty("class", "primary")
            self._status_lbl.setText("○  stopped")
            self._status_lbl.setStyleSheet(
                f"color:{theme.FG_MUTED}; font-size:11px; background:transparent;"
            )
        self._server_btn.style().unpolish(self._server_btn)
        self._server_btn.style().polish(self._server_btn)
        self._tcp_port_spin.setEnabled(not running)

    def set_client_count(self, n: int) -> None:
        self._client_lbl.setText(f"{n} client{'s' if n != 1 else ''}")
        color = theme.SUCCESS if n > 0 else theme.FG_MUTED
        self._client_lbl.setStyleSheet(
            f"color:{color}; font-size:11px; background:transparent;"
        )

    def flash_goto(self, ra_hours: float, dec_degrees: float) -> None:
        """Briefly highlight that a goto was received."""
        self._status_lbl.setText(
            f"↗  goto  RA {ra_hours:.4f}h  Dec {dec_degrees:+.4f}°"
        )

    # ------------------------------------------------------------------
    # Slots → signals
    # ------------------------------------------------------------------

    def _on_server_toggle(self) -> None:
        if self._server_running:
            self.stop_server_requested.emit()
        else:
            self.start_server_requested.emit(self._host, self._tcp_port_spin.value())

    def _on_pull_clicked(self) -> None:
        self.pull_requested.emit(self._host, self._http_port_spin.value())


def _muted(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color:{theme.FG_MUTED}; font-size:11px; background:transparent;"
    )
    return lbl
