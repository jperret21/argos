"""Phase scaffold + launcher screens for the workflow rail.

The redesign (``docs/ui_design.md``) splits an observing night into phase
screens: Connect, Target, Focus, Photometry, Capture, Analyze, Settings.

Connect, Capture (the existing acquisition engine, ``ImagingPage``) and
Settings are already live. Target / Focus / Photometry are built here as
**design scaffolds**: each renders the agreed layout and the controls it will
own, and offers a button that deep-links to the live controls (still hosted on
the Capture page) until the per-phase split lands. This keeps the whole new
information architecture navigable without regressing any functionality.

Analyze is a small launcher for the standalone analysis companion window.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QLabel, QVBoxLayout, QWidget

from argos.ui import design, theme


def _body(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(
        f"color:{theme.FG}; font-size:{design.FONT_SIZE_BODY}px; background:transparent;"
    )
    return label


class PhaseScaffold(QWidget):
    """A designed-but-not-yet-wired workflow phase screen.

    Shows the heading, the screen's single job, an ASCII wireframe of the target
    layout, the controls it will host, and a button that deep-links to the live
    controls on the Capture page.
    """

    open_controls = pyqtSignal()

    def __init__(
        self,
        title: str,
        job: str,
        wireframe: str,
        controls: list[str],
        action_label: str = "Open live controls in Capture",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background:{theme.BG};")

        scroll, content = design.scroll_page()

        content.addWidget(design.HeadingLabel(title))
        content.addWidget(_body(job))

        note = QLabel(
            "Design scaffold. The controls below currently live on the Capture "
            "page; they move onto this screen as the session layer is extracted "
            "(see docs/ui_design.md)."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color:{theme.WARNING}; font-size:{design.FONT_SIZE_LABEL}px;"
            f" background:transparent;"
        )
        content.addWidget(note)

        wf_card = design.Card("Planned layout")
        wf_layout = design.card_layout(wf_card)
        wireframe_label = QLabel(wireframe)
        wireframe_label.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-family:{theme.FONT_MONO};"
            f" font-size:12px; background:transparent;"
        )
        wf_layout.addWidget(wireframe_label)
        content.addWidget(wf_card)

        ctl_card = design.Card("This screen will own")
        ctl_layout = design.card_layout(ctl_card)
        ctl_layout.addWidget(_body("\n".join(f"—  {item}" for item in controls)))
        content.addWidget(ctl_card)

        button = design.PrimaryButton(action_label)
        button.clicked.connect(self.open_controls.emit)
        content.addWidget(button)
        content.addStretch(1)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)


class AnalyzeLauncher(QWidget):
    """The Analyze phase: opens the standalone analysis companion window.

    Analysis is intentionally a separate, second-monitor window so a finished
    (or archived) session can be vetted while a new run continues on Capture.
    """

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


# --------------------------------------------------------------------------- #
# Phase scaffold factories — content lives here, next to the widget.           #
# --------------------------------------------------------------------------- #


def target_scaffold() -> PhaseScaffold:
    """The Target phase: point, plate-solve and centre the field."""
    return PhaseScaffold(
        title="Target",
        job="Put the right star in the centre of the frame, confirmed by a plate "
        "solve, and check the field is worth observing tonight.",
        wireframe=(
            "+-----------------------------+-------------+\n"
            "| [stretch  channel]          | TARGET      |\n"
            "|                             |  Name       |\n"
            "|       IMAGE (live)          |  RA / Dec   |\n"
            "|       + solved overlay      |  Alt 58 deg |\n"
            "|       + centre reticle      |  Airmass    |\n"
            "|                             |  Transit    |\n"
            '|  solved   offset 12"        |  Moon sep   |\n'
            "+-----------------------------+ [ Slew ]    |\n"
            "|  RA/Dec readout             | [ Solve ]   |\n"
            "|                             | [ Center ]  |\n"
            "+-----------------------------+-------------+"
        ),
        controls=[
            "Slew to the Stellarium target",
            "Plate-solve (ASTAP) and centre the field",
            "Altitude / airmass / transit / Moon-separation summary",
            "Live field with RA/Dec grid + star overlay",
        ],
        action_label="Open equipment controls in Capture",
    )


def focus_scaffold() -> PhaseScaffold:
    """The Focus phase: reach and lock best focus."""
    return PhaseScaffold(
        title="Focus",
        job="Reach and lock best focus. After this you do not touch it — "
        "refocusing mid-run would shift FWHM and flux and corrupt the photometry.",
        wireframe=(
            "+-----------------------------+-------------+\n"
            "|                             | FOCUS       |\n"
            "|       IMAGE (live)          |  Pos 4120   |\n"
            "|       HFD on stars          |  HFD 2.04   |\n"
            "|                             |  V-curve    |\n"
            "|                             |   \\     /   |\n"
            "|  HFD 2.04   Stars 240       |    \\___/    |\n"
            "+-----------------------------+ [Auto-focus]|\n"
            "|                             | [ - ] [ + ] |\n"
            "+-----------------------------+-------------+"
        ),
        controls=[
            "Auto-focus V-curve sweep (park at the parabola minimum)",
            "Manual focuser nudge (+/-)",
            "Live HFD on detected stars",
            "Focus-locked confirmation",
        ],
        action_label="Open equipment controls in Capture",
    )


def photometry_scaffold() -> PhaseScaffold:
    """The Photometry phase: define target, comparison and check stars."""
    return PhaseScaffold(
        title="Photometry",
        job="Define the science: which star is the target (T1), which are "
        "comparison (C2..Cn) and which is the check (K), and the aperture for "
        "each. This is what makes Argos a photometer, not a camera app.",
        wireframe=(
            "+-----------------------------+-------------+\n"
            "|      SOLVED FIELD           | PHOTOMETRY  |\n"
            "|      T1 target (green)      |  Target     |\n"
            "|      C2..Cn comps (red)     |  Comps  5   |\n"
            "|      K check                |  Check  1   |\n"
            "|      VSX / VSP overlay      |  Aperture   |\n"
            "|                             | [Pick stars]|\n"
            "|  catalog: VSP chart         | [Auto comp] |\n"
            "+-----------------------------+-------------+"
        ),
        controls=[
            "Click-to-place target (T1, green), comparisons (C2.., red), check (K)",
            "VSX / VSP catalog overlay on the solved frame",
            "Auto-select comparison stars by magnitude / colour / separation",
            "Aperture / annulus settings (k x FWHM)",
            "Opens the Photometry Setup companion window",
        ],
        action_label="Open session controls in Capture",
    )
