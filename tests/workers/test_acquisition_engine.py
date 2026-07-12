"""AcquisitionEngine unit tests — no hardware, no event loop.

A ``QApplication`` is required because the engine is a ``QObject``; signals
are observed through direct connections into plain lists.
"""

from __future__ import annotations

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

from argos.core.config import _DEFAULTS, Config
from argos.core.session.acquisition_engine import AcquisitionEngine
from argos.core.session.device_session import DeviceSession


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_ingest_frame_feeds_the_live_pipeline(qapp, tmp_path) -> None:
    """Offline replay: an opened FITS must land exactly where a camera frame
    would — authoritative full-res raw + a frame_ready for the display."""
    cfg = Config(dict(_DEFAULTS, sessions_path=str(tmp_path)))
    engine = AcquisitionEngine(cfg, DeviceSession(cfg))
    frames = []
    engine.frame_ready.connect(frames.append)

    raw = np.arange(64, dtype=np.uint16).reshape(8, 8)
    engine.ingest_frame(raw)

    assert len(frames) == 1
    assert frames[0].full is raw and frames[0].preview is raw
    assert frames[0].decimated is False
    # Solve/photometry read the same authoritative frame.
    assert engine._last_raw is raw and engine._last_raw_decimated is False
