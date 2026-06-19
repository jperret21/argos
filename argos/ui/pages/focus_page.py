"""Focus phase screen — reach and lock best focus.

The canonical autofocus visual: an HFD V-curve. As the sweep samples HFD at a
range of focuser positions this plots the points, the fitted parabola and its
vertex (best focus), and reports the result. The sweep itself runs in the
Capture engine's :class:`AutofocusWorker`; this screen drives it (Run autofocus)
and consumes its live samples, so it stays verifiable headless through its
public ``add_sample`` / ``set_best`` / ``set_samples`` API.

After focus you do not touch it again: refocusing mid-run would shift FWHM and
flux and corrupt the photometry. Full manual focuser control stays one click
away on Capture (the deep-link button).
"""

from __future__ import annotations

import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from argos.core.imaging.focus import FocusResult, fit_v_curve
from argos.ui import design, theme

_NUDGE_PRESETS = (10, 50, 100, 500)


class FocusScreen(QWidget):
    """The Focus phase: drive an autofocus sweep and read its V-curve."""

    autofocus_requested = pyqtSignal()
    nudge_requested = pyqtSignal(int)  # signed step count (+ = inward)
    open_controls = pyqtSignal()  # deep-link to the Capture equipment controls

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._samples: list[tuple[int, float]] = []
        self._running = False

        self.setStyleSheet(f"background:{theme.BG};")
        scroll, content = design.scroll_page()

        content.addWidget(design.HeadingLabel("Focus"))
        intro = QLabel(
            "Reach best focus, then leave it. Run an autofocus sweep; the V-curve "
            "below shows HFD against focuser position and marks the parabola "
            "minimum. Refocusing mid-run would change FWHM and flux and corrupt "
            "the photometry, so this is a once-per-night step."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            f"color:{theme.FG}; font-size:{design.FONT_SIZE_BODY}px; background:transparent;"
        )
        content.addWidget(intro)

        content.addWidget(self._build_curve_card())
        content.addWidget(self._build_summary_card())
        content.addLayout(self._build_actions())

        note = QLabel(
            "The sweep runs in the Capture engine and needs the focuser + camera "
            "connected. Full manual focuser control lives on Capture."
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

        self._redraw()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_curve_card(self) -> design.Card:
        card = design.Card("V-curve")
        layout = design.card_layout(card)

        self._plot = pg.PlotWidget()
        self._plot.setBackground(theme.BG2)
        self._plot.setMinimumHeight(260)
        self._plot.showGrid(x=True, y=True, alpha=0.2)
        self._plot.setLabel("bottom", "Focuser position", units="steps")
        self._plot.setLabel("left", "HFD", units="px")
        self._plot.getAxis("bottom").setTextPen(pg.mkPen(theme.FG_MUTED))
        self._plot.getAxis("left").setTextPen(pg.mkPen(theme.FG_MUTED))

        self._fit_curve = self._plot.plot(pen=pg.mkPen(theme.ACCENT, width=2))
        self._sample_points = pg.ScatterPlotItem(
            size=9, brush=pg.mkBrush(theme.FG), pen=pg.mkPen(theme.BG2)
        )
        self._plot.addItem(self._sample_points)
        self._vertex_line = pg.InfiniteLine(
            angle=90, pen=pg.mkPen(theme.SUCCESS, width=1, style=Qt.PenStyle.DashLine)
        )
        self._vertex_line.hide()
        self._plot.addItem(self._vertex_line)

        layout.addWidget(self._plot)
        return card

    def _build_summary_card(self) -> design.Card:
        card = design.Card("Best focus")
        form = QFormLayout()
        form.setContentsMargins(
            design.SPACING_MD, design.SPACING_LG, design.SPACING_MD, design.SPACING_MD
        )
        form.setHorizontalSpacing(design.SPACING_LG)
        form.setVerticalSpacing(design.SPACING_SM)
        self._values: dict[str, QLabel] = {}
        for key, label in (
            ("position", "Best position"),
            ("hfd", "Best HFD"),
            ("fit", "Fit"),
            ("samples", "Samples"),
        ):
            value = design.MetricLabel("—")
            self._values[key] = value
            form.addRow(design.MutedLabel(label), value)
        card.setLayout(form)
        return card

    def _build_actions(self) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(design.SPACING_SM)

        self._af_btn = design.PrimaryButton("Run autofocus")
        self._af_btn.clicked.connect(self._on_autofocus)

        self._status = QLabel("Not yet focused")
        self._status.setStyleSheet(
            f"color:{theme.FG_MUTED}; font-size:{design.FONT_SIZE_LABEL}px;"
            f" background:transparent;"
        )

        nudge_row = QHBoxLayout()
        nudge_row.setSpacing(design.SPACING_SM)
        self._step_combo = QComboBox()
        for v in _NUDGE_PRESETS:
            self._step_combo.addItem(str(v))
        self._step_combo.setCurrentText("50")
        out_btn = design.SecondaryButton("Nudge out")
        out_btn.setToolTip("Move focuser outward (position decreases)")
        out_btn.clicked.connect(lambda: self._on_nudge(-1))
        in_btn = design.SecondaryButton("Nudge in")
        in_btn.setToolTip("Move focuser inward (position increases)")
        in_btn.clicked.connect(lambda: self._on_nudge(+1))
        nudge_row.addWidget(design.MutedLabel("Step"))
        nudge_row.addWidget(self._step_combo)
        nudge_row.addWidget(out_btn, 1)
        nudge_row.addWidget(in_btn, 1)

        capture_btn = design.SecondaryButton("Open focuser controls in Capture")
        capture_btn.clicked.connect(self.open_controls.emit)

        box.addWidget(self._af_btn)
        box.addWidget(self._status)
        box.addLayout(nudge_row)
        box.addWidget(capture_btn)
        return box

    # ------------------------------------------------------------------
    # Public API (driven by the Capture autofocus worker via the Shell)
    # ------------------------------------------------------------------

    def add_sample(self, step: int, total: int, position: int, hfd: object) -> None:
        """Append one live sweep sample (matches ``AutofocusWorker.step_done``)."""
        if hfd is not None:
            self._samples.append((int(position), float(hfd)))
        self._status.setText(f"Autofocus — step {step}/{total}")
        self._redraw()

    def set_best(self, position: int, hfd: object) -> None:
        """Mark the final best position reported by the sweep."""
        self._redraw()
        hfd_txt = f"{float(hfd):.2f} px" if hfd is not None else "—"
        self._status.setText(f"Focus locked — best HFD {hfd_txt} at {int(position):,}")
        self._status.setStyleSheet(
            f"color:{theme.SUCCESS}; font-size:{design.FONT_SIZE_LABEL}px;"
            f" background:transparent;"
        )

    def set_samples(self, measurements: list[tuple[int, float]]) -> None:
        """Replace all samples at once (e.g. to re-display a finished sweep)."""
        self._samples = [(int(p), float(h)) for p, h in measurements]
        self._redraw()

    def set_running(self, running: bool) -> None:
        """Reflect the sweep state on the button + status, and reset on start."""
        self._running = running
        self._af_btn.setText("Stop autofocus" if running else "Run autofocus")
        if running:
            self._samples.clear()
            self._status.setStyleSheet(
                f"color:{theme.FG_MUTED}; font-size:{design.FONT_SIZE_LABEL}px;"
                f" background:transparent;"
            )
            self._status.setText("Autofocus running…")
            self._redraw()

    def clear(self) -> None:
        self._samples.clear()
        self._redraw()

    def result(self) -> FocusResult:
        """The current fit of the collected samples (for tests / read-back)."""
        return fit_v_curve(self._samples)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _on_autofocus(self) -> None:
        self.autofocus_requested.emit()

    def _on_nudge(self, direction: int) -> None:
        try:
            step = int(self._step_combo.currentText())
        except ValueError:
            step = 50
        self.nudge_requested.emit(direction * step)

    def _redraw(self) -> None:
        if self._samples:
            xs = [p for p, _ in self._samples]
            ys = [h for _, h in self._samples]
            self._sample_points.setData(xs, ys)
        else:
            self._sample_points.setData([], [])

        result = fit_v_curve(self._samples)
        fx, fy = result.fit_curve()
        self._fit_curve.setData(fx, fy)

        if result.method == "none":
            self._vertex_line.hide()
            for v in self._values.values():
                v.setText("—")
            return

        if result.is_reliable:
            self._vertex_line.setValue(result.best_position)
            self._vertex_line.show()
        else:
            self._vertex_line.hide()

        self._values["position"].setText(f"{result.best_position:,}")
        self._values["hfd"].setText(
            f"{result.best_hfd:.2f} px" if result.best_hfd is not None else "—"
        )
        self._values["fit"].setText("parabola" if result.is_reliable else "raw minimum")
        self._values["samples"].setText(str(len(result.samples)))
