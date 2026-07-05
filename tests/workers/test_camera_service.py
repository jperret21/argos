"""Tests for the CameraService ownership state machine (WS3).

Pure QObject logic — no hardware, no event loop. A ``QApplication`` is
required because the service is a ``QObject``; signals are observed through
direct connections into plain lists.
"""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QApplication

from argos.workers.camera_service import CameraService, CameraState


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def service(qapp):
    """A CameraService with recording preview hooks + signal taps."""
    svc = CameraService()
    svc.hook_calls: list[str] = []
    svc.set_preview_hooks(
        lambda: svc.hook_calls.append("start"),
        lambda: svc.hook_calls.append("stop"),
    )
    svc.states: list[CameraState] = []
    svc.refusals: list[str] = []
    svc.preemptions: list[str] = []
    svc.state_changed.connect(svc.states.append)
    svc.acquire_refused.connect(svc.refusals.append)
    svc.preempted.connect(svc.preemptions.append)
    return svc


# ---------------------------------------------------------------------------
# Grant / refuse matrix
# ---------------------------------------------------------------------------


def test_initial_state_is_idle(service) -> None:
    assert service.state is CameraState.IDLE


@pytest.mark.parametrize(
    "requested",
    [CameraState.LIVE, CameraState.SINGLE, CameraState.SEQUENCE, CameraState.AUTOFOCUS],
)
def test_acquire_from_idle_grants(service, requested) -> None:
    assert service.acquire(requested) is True
    assert service.state is requested
    assert service.states == [requested]
    assert service.refusals == []


@pytest.mark.parametrize("requested", [CameraState.LIVE, CameraState.SINGLE])
def test_preview_owners_start_the_preview_loop(service, requested) -> None:
    service.acquire(requested)
    assert service.hook_calls == ["start"]


@pytest.mark.parametrize("requested", [CameraState.SEQUENCE, CameraState.AUTOFOCUS])
def test_exclusive_owners_do_not_touch_the_preview_loop(service, requested) -> None:
    service.acquire(requested)
    assert service.hook_calls == []


@pytest.mark.parametrize(
    ("holder", "requested"),
    [
        # SEQUENCE outranks everything — all requests are refused.
        (CameraState.SEQUENCE, CameraState.LIVE),
        (CameraState.SEQUENCE, CameraState.SINGLE),
        (CameraState.SEQUENCE, CameraState.AUTOFOCUS),
        (CameraState.SEQUENCE, CameraState.SEQUENCE),
        # AUTOFOCUS outranks LIVE/SINGLE — those (and a duplicate AF) refuse.
        (CameraState.AUTOFOCUS, CameraState.LIVE),
        (CameraState.AUTOFOCUS, CameraState.SINGLE),
        (CameraState.AUTOFOCUS, CameraState.AUTOFOCUS),
        # Equal priority never preempts.
        (CameraState.LIVE, CameraState.SINGLE),
        (CameraState.LIVE, CameraState.LIVE),
        (CameraState.SINGLE, CameraState.SINGLE),
    ],
)
def test_refuse_matrix(service, holder, requested) -> None:
    assert service.acquire(holder) is True
    assert service.acquire(requested) is False
    assert service.state is holder  # unchanged
    assert len(service.refusals) == 1
    assert service.refusals[0]  # human-readable, non-empty


def test_refusal_reason_names_the_owner(service) -> None:
    service.acquire(CameraState.SEQUENCE)
    service.acquire(CameraState.LIVE)
    assert "Sequence" in service.refusals[0]
    service.release(CameraState.SEQUENCE)
    service.acquire(CameraState.AUTOFOCUS)
    service.acquire(CameraState.LIVE)
    assert "Autofocus" in service.refusals[1]


def test_acquire_idle_is_a_programming_error(service) -> None:
    with pytest.raises(ValueError):
        service.acquire(CameraState.IDLE)


# ---------------------------------------------------------------------------
# Preemption of LIVE / SINGLE by higher priority
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("holder", [CameraState.LIVE, CameraState.SINGLE])
@pytest.mark.parametrize("requested", [CameraState.SEQUENCE, CameraState.AUTOFOCUS])
def test_higher_priority_preempts_preview(service, holder, requested) -> None:
    service.acquire(holder)
    assert service.acquire(requested) is True
    assert service.state is requested
    assert service.hook_calls == ["start", "stop"]  # preview loop was stopped
    assert len(service.preemptions) == 1
    assert "Live preview stopped" in service.preemptions[0]
    assert service.refusals == []


def test_single_upgrades_to_live_in_place(service) -> None:
    """Live start during a transient Take-shot loop keeps the worker running."""
    service.acquire(CameraState.SINGLE)
    assert service.acquire(CameraState.LIVE) is True
    assert service.state is CameraState.LIVE
    assert service.hook_calls == ["start"]  # no stop, no second start
    assert service.preemptions == []


# ---------------------------------------------------------------------------
# AF-mid-sequence handshake: SEQUENCE → AUTOFOCUS → SEQUENCE
# ---------------------------------------------------------------------------


def test_sequence_autofocus_handshake_round_trip(service) -> None:
    service.acquire(CameraState.SEQUENCE)
    assert service.begin_sequence_autofocus() is True
    assert service.state is CameraState.AUTOFOCUS
    service.release(CameraState.AUTOFOCUS)
    assert service.state is CameraState.SEQUENCE  # camera handed back
    service.release(CameraState.SEQUENCE)
    assert service.state is CameraState.IDLE
    assert service.states == [
        CameraState.SEQUENCE,
        CameraState.AUTOFOCUS,
        CameraState.SEQUENCE,
        CameraState.IDLE,
    ]


@pytest.mark.parametrize(
    "holder", [None, CameraState.LIVE, CameraState.SINGLE, CameraState.AUTOFOCUS]
)
def test_handshake_refused_unless_sequence_owns_the_camera(service, holder) -> None:
    if holder is not None:
        service.acquire(holder)
    assert service.begin_sequence_autofocus() is False
    assert service.state is (holder or CameraState.IDLE)
    assert len(service.refusals) == 1


def test_sequence_dying_during_handshake_cancels_the_resume(service) -> None:
    """A sequence abort while AF holds the camera must not resurrect SEQUENCE."""
    service.acquire(CameraState.SEQUENCE)
    service.begin_sequence_autofocus()
    service.release(CameraState.SEQUENCE)  # sequence finished/aborted under AF
    assert service.state is CameraState.AUTOFOCUS  # AF still owns the camera
    service.release(CameraState.AUTOFOCUS)
    assert service.state is CameraState.IDLE  # …and releases to IDLE, not SEQUENCE


def test_user_autofocus_releases_to_idle(service) -> None:
    """Outside the handshake, AUTOFOCUS release must not invent a SEQUENCE."""
    service.acquire(CameraState.AUTOFOCUS)
    service.release(CameraState.AUTOFOCUS)
    assert service.state is CameraState.IDLE


# ---------------------------------------------------------------------------
# Release semantics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("holder", [CameraState.LIVE, CameraState.SINGLE])
def test_release_of_preview_owner_stops_the_loop(service, holder) -> None:
    service.acquire(holder)
    service.release(holder)
    assert service.state is CameraState.IDLE
    assert service.hook_calls == ["start", "stop"]


def test_double_release_is_a_safe_noop(service) -> None:
    service.acquire(CameraState.LIVE)
    service.release(CameraState.LIVE)
    service.release(CameraState.LIVE)  # e.g. the worker's queued finished signal
    assert service.state is CameraState.IDLE
    assert service.hook_calls == ["start", "stop"]  # stop hook fired exactly once
    assert service.states == [CameraState.LIVE, CameraState.IDLE]  # one transition each


def test_release_by_non_owner_is_ignored(service) -> None:
    service.acquire(CameraState.SEQUENCE)
    service.release(CameraState.LIVE)  # stale preview release after preemption
    service.release(CameraState.AUTOFOCUS)
    assert service.state is CameraState.SEQUENCE
    assert service.hook_calls == []


def test_release_on_idle_is_ignored(service) -> None:
    service.release(CameraState.SEQUENCE)
    service.release(CameraState.LIVE)
    assert service.state is CameraState.IDLE
    assert service.states == []
    assert service.hook_calls == []


def test_stale_preview_release_after_preemption_is_ignored(service) -> None:
    """LIVE preempted by SEQUENCE; the preview worker's finished signal then
    arrives late — its release must not steal the camera from the sequence."""
    service.acquire(CameraState.LIVE)
    service.acquire(CameraState.SEQUENCE)  # preempts
    service.release(CameraState.LIVE)  # stale
    assert service.state is CameraState.SEQUENCE
    assert service.hook_calls == ["start", "stop"]  # no extra stop
