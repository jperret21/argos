"""Photometry phase screen — define the science: target, comparisons, check.

This is what makes Argos a photometer rather than a camera app. The heavy
interaction — picking T1 / C2..Cn / K on the solved field, VSX/VSP overlay,
apertures — lives in the **Photometry Setup** companion window (second monitor,
reused from the Capture toolbar). This phase screen frames that work and shows a
live read-only summary of the current selection, read from the saved target set.

The summary is rendered from the pure, tested ``TargetSet.summary()`` so it is
verifiable headless; the screen reloads it whenever it becomes visible (after
the companion has been used) and on demand via Refresh.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import QFormLayout, QLabel, QVBoxLayout, QWidget

from argos.core.catalog.targets import TargetSet
from argos.core.config import Config
from argos.ui import design, theme

logger = logging.getLogger(__name__)


class PhotometryScreen(QWidget):
    """The Photometry phase: launch the Setup companion + show the selection."""

    setup_requested = pyqtSignal()  # open the Photometry Setup companion window
    open_controls = pyqtSignal()  # deep-link to the Capture field controls

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config

        self.setStyleSheet(f"background:{theme.BG};")
        scroll, content = design.scroll_page()

        content.addWidget(design.HeadingLabel("Photometry"))
        intro = QLabel(
            "Define the science. Mark the variable as the target (T1), pick "
            "comparison stars (C2..Cn) of known magnitude and a check star (K) to "
            "watch for trouble. Argos measures the target against the comparisons "
            "frame by frame — that differential measurement is the light curve."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            f"color:{theme.FG}; font-size:{design.FONT_SIZE_BODY}px; background:transparent;"
        )
        content.addWidget(intro)

        content.addWidget(self._build_summary_card())

        self._setup_btn = design.PrimaryButton("Open Photometry Setup")
        self._setup_btn.clicked.connect(self.setup_requested.emit)
        refresh_btn = design.SecondaryButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        field_btn = design.SecondaryButton("Open field & solve in Capture")
        field_btn.clicked.connect(self.open_controls.emit)
        content.addLayout(design.button_row(self._setup_btn, refresh_btn, field_btn))

        note = QLabel(
            "Setup opens as a companion window so you can pick stars on one screen "
            "while the field stays on the other. Selection is saved per object and "
            "reused on the next visit to the same field."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:{design.FONT_SIZE_LABEL}px;"
            f" background:transparent;"
        )
        content.addWidget(note)
        content.addStretch(1)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        self.refresh()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_summary_card(self) -> design.Card:
        card = design.Card("Current selection")
        form = QFormLayout()
        form.setContentsMargins(
            design.SPACING_MD, design.SPACING_LG, design.SPACING_MD, design.SPACING_MD
        )
        form.setHorizontalSpacing(design.SPACING_LG)
        form.setVerticalSpacing(design.SPACING_SM)
        self._values: dict[str, QLabel] = {}
        for key, label in (
            ("object", "Object"),
            ("target", "Target (T1)"),
            ("comparison", "Comparisons"),
            ("check", "Check (K)"),
            ("status", "Status"),
        ):
            value = design.MetricLabel("—")
            self._values[key] = value
            form.addRow(design.MutedLabel(label), value)
        card.setLayout(form)
        return card

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_target_set(self, target_set: TargetSet | None) -> None:
        """Render the selection summary (pure path — used by tests + refresh)."""
        if target_set is None:
            for key in ("object", "target", "comparison", "check"):
                self._values[key].setText("—")
            self._set_status(None)
            return

        s = target_set.summary()
        self._values["object"].setText(s["object"] or "—")
        self._values["target"].setText(s["target"] or "— (none yet)")
        self._values["comparison"].setText(str(s["n_comparison"]))
        self._values["check"].setText(str(s["n_check"]))
        self._set_status(s)

    def refresh(self) -> None:
        """Reload the most recently edited target set and re-render the summary."""
        self.set_target_set(self._latest_target_set())

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _set_status(self, summary: dict | None) -> None:
        status = self._values["status"]
        if summary is None:
            status.setText("No selection yet")
            color = theme.FG_MUTED
        elif summary["complete"]:
            missing = "" if summary["n_check"] else "  (add a check star)"
            status.setText(f"Ready{missing}")
            color = theme.SUCCESS if summary["n_check"] else theme.WARNING
        elif summary["n_target"]:
            status.setText("Incomplete — needs a comparison star")
            color = theme.WARNING
        else:
            status.setText("Incomplete — needs a target")
            color = theme.WARNING
        status.setStyleSheet(
            f"color:{color}; font-size:{design.FONT_SIZE_METRIC}px;"
            f" font-weight:bold; background:transparent;"
        )

    def _targets_dir(self) -> Path:
        try:
            base = self._config.sessions_path.parent
        except Exception:
            base = Path.home() / "Argos"
        return base / "targets"

    def _latest_target_set(self) -> TargetSet | None:
        """The most recently modified ``targets/*.json`` selection, if any.

        Keyed on the object name by the Setup companion; the latest file is a
        pragmatic stand-in for "what I am working on" until the active object is
        plumbed through the session layer.
        """
        directory = self._targets_dir()
        try:
            files = sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        except OSError:
            return None
        if not files:
            return None
        return TargetSet.load(files[0])

    def showEvent(self, event: QShowEvent) -> None:
        # Re-read after the companion window may have changed the selection.
        self.refresh()
        super().showEvent(event)
