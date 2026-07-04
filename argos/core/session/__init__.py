"""Session layer — device ownership + acquisition orchestration (WS5).

:class:`DeviceSession` owns the Alpaca device handles, discovery, the
pollers and the Stellarium server; the acquisition engine owns the camera
ownership state machine and the capture/solve/photometry workers. Both are
UI-thread QObjects; the ImagingPage is a view over them.
"""

from argos.core.session.device_session import DeviceSession
from argos.core.session.types import (
    CameraCapabilities,
    FilterWheelState,
    FocuserState,
    LiveFrame,
    PhotometryPoint,
)

__all__ = [
    "CameraCapabilities",
    "DeviceSession",
    "FilterWheelState",
    "FocuserState",
    "LiveFrame",
    "PhotometryPoint",
]
