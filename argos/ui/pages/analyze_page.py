"""Analyze phase — launch the standalone analysis companion window.

Analysis is intentionally a separate, second-monitor window so a finished (or
archived) session can be vetted while a new run continues on Capture. This phase
screen is a thin launcher; the work happens in ``AnalysisWindow``.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFileDialog, QLabel, QVBoxLayout, QWidget

from argos.ui import design, theme


def _body(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(
        f"color:{theme.FG}; font-size:{design.FONT_SIZE_BODY}px; background:transparent;"
    )
    return label


class AnalyzeLauncher(QWidget):
    """The Analyze phase: opens the standalone analysis companion window."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background:{theme.BG};")
        # Hold references so the spawned windows aren't garbage-collected.
        self._windows: list[QWidget] = []

        scroll, content = design.scroll_page()

        content.addWidget(design.HeadingLabel("Analyze"))
        content.addWidget(
            _body(
                "Inspect the light curve, reject bad points and export "
                "AAVSO-format photometry. Opens as a companion window so you can "
                "analyse last night while tonight's run continues."
            )
        )

        card = design.Card("Open data")
        card_layout = design.card_layout(card)
        button = design.PrimaryButton("Open frame or session...")
        button.clicked.connect(self._open)
        card_layout.addWidget(button)
        content.addWidget(card)
        content.addStretch(1)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    def _open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open FITS frame",
            "",
            "FITS (*.fits *.fit *.fts);;All files (*)",
        )
        if not path:
            return
        # Imported lazily so the module stays light and headless-import-safe.
        from argos.ui.analysis_window import AnalysisWindow

        window = AnalysisWindow()
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        window.load(path)
        window.show()
        self._windows.append(window)
