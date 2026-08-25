"""Sequencer mode — plan and run the night's capture sequence.

The SequencePanel (pure UI) gets a full page here instead of a Capture
dock: steps table on the left, Plan / Presets / Run cards on the right.
This page owns all panel↔engine wiring; frames, the log and the light
curve stay on the Capture page, and the top status-bar strip keeps the
run's progress visible from every mode.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSlot
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from argos.ui import design
from argos.ui.widgets.sequence_panel import SequencePanel


class SequencerPage(QWidget):
    """Full-page host for the sequence planner, wired to the engine."""

    def __init__(self, config, session, engine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._session = session
        self._engine = engine

        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            design.SPACING_XL, design.SPACING_LG, design.SPACING_XL, design.SPACING_LG
        )
        outer.setSpacing(design.SPACING_MD)
        outer.addWidget(design.HeadingLabel("Sequencer"))
        intro = design.MutedLabel(
            "Plan the night's frames, then start the run — progress stays visible "
            "in the top strip, frames and the live light curve on the Capture page."
        )
        intro.setWordWrap(True)
        outer.addWidget(intro)
        self.panel = SequencePanel()
        outer.addWidget(self.panel, 1)

        # Intents → engine.
        self.panel.start_requested.connect(self._on_start)
        self.panel.pause_requested.connect(engine.pause_sequence)
        self.panel.resume_requested.connect(engine.resume_sequence_run)
        self.panel.stop_requested.connect(engine.stop_sequence)
        # Engine → run feedback.
        engine.sequence_running.connect(self.panel.set_running)
        engine.sequence_paused.connect(self.panel.set_paused)
        engine.sequence_progress.connect(self._on_progress)
        engine.sequence_step.connect(self._on_step)
        # Device-derived vocabulary: spinbox limits from the camera, filter
        # names from the wheel — same sources the Capture forms use.
        session.capabilities_ready.connect(self._on_capabilities)
        session.filterwheel_state.connect(self._on_filterwheel_state)
        session.device_state_changed.connect(self._on_device_state)

    # ------------------------------------------------------------------

    def _on_start(self, plan) -> None:
        if not self._engine.start_sequence(plan):
            # Refused (no camera / already running / AF owns the camera) —
            # the reason is logged; snap the panel button back.
            self.panel.set_running(False)

    @pyqtSlot(str, int, int, float)
    def _on_progress(self, _obj: str, done: int, total: int, eta_s: float) -> None:
        self.panel.set_progress(done, total, eta_s)

    def _on_step(self, index: int, step) -> None:
        self.panel.set_active_step(index)
        self.panel.set_status(
            f"Step {index + 1}: {step.count}× {step.exposure_s:.1f}s {step.filter_name}"
        )

    @pyqtSlot(object)
    def _on_capabilities(self, caps) -> None:
        self.panel.set_camera_limits(
            caps.gain_min, caps.gain_max, caps.exposure_min, caps.exposure_max
        )

    @pyqtSlot(object)
    def _on_filterwheel_state(self, fw) -> None:
        self.panel.set_filter_options(list(fw.names))

    @pyqtSlot(str, str, str)
    def _on_device_state(self, device: str, state: str, _info: str) -> None:
        if device == "camera" and state == "disconnected":
            self.panel.set_camera_limits()  # back to defaults
