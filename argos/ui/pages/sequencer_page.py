"""Sequencer mode — plan and run a capture sequence.

The SequencePanel is a dockable workspace: the table stays central, while
target search, visibility and controls are movable.  This page owns panel↔
engine wiring; frames, the log and live light curve stay on Capture.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from argos.ui import design
from argos.ui.widgets.sequence_panel import SequencePanel
from argos.workers.object_resolver_worker import ObjectResolverWorker


class SequencerPage(QWidget):
    """Full-page host for the sequence planner, wired to the engine."""

    target_resolved = pyqtSignal(object)

    def __init__(self, config, session, engine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._session = session
        self._engine = engine
        self._object_resolver_worker: ObjectResolverWorker | None = None

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
        self.panel.set_config(config)
        outer.addWidget(self.panel, 1)

        # Intents → engine.
        self.panel.start_requested.connect(self._on_start)
        self.panel.pause_requested.connect(engine.pause_sequence)
        self.panel.resume_requested.connect(engine.resume_sequence_run)
        self.panel.stop_requested.connect(engine.stop_sequence)
        self.panel.object_lookup_requested.connect(self._lookup_object)
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

    def set_target_coordinates(self, name: str, ra_hours: float, dec_degrees: float) -> None:
        """Receive the shared Telescope target for the Plan visibility preview."""
        self.panel.set_target_coordinates(
            name,
            ra_hours,
            dec_degrees,
            float(self._config.get("site.latitude", 0.0) or 0.0),
            float(self._config.get("site.longitude", 0.0) or 0.0),
        )

    def _lookup_object(self, query: str) -> None:
        if self._object_resolver_worker is not None:
            return
        self.panel.set_lookup_busy(True)
        worker = ObjectResolverWorker(query, self)
        self._object_resolver_worker = worker
        worker.resolved.connect(self._on_object_resolved)
        worker.failed.connect(self._on_object_lookup_failed)
        worker.finished.connect(self._finish_object_lookup)
        worker.start()

    @pyqtSlot(object)
    def _on_object_resolved(self, result) -> None:
        self.panel.set_lookup_result(result)
        self.set_target_coordinates(result.name, result.ra_hours, result.dec_degrees)
        # Shell routes this to ImagingPage, which makes the same target visible
        # in Capture and arms (but does not execute) the Telescope slew button.
        self.target_resolved.emit(result)

    @pyqtSlot(str)
    def _on_object_lookup_failed(self, message: str) -> None:
        self.panel.set_lookup_error(message)

    def _finish_object_lookup(self) -> None:
        self.panel.set_lookup_busy(False)
        worker = self._object_resolver_worker
        self._object_resolver_worker = None
        if worker is not None:
            worker.deleteLater()

    def save_layout(self) -> None:
        self.panel.save_layout()

    def shutdown(self) -> None:
        if self._object_resolver_worker is not None:
            self._object_resolver_worker.wait(9000)  # resolver request timeout is 8 seconds
            self._object_resolver_worker = None

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
        self.panel.set_device_state(device, state)
        if device == "camera" and state == "disconnected":
            self.panel.set_camera_limits()  # back to defaults
