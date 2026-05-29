"""HTTP "pull selected object" — verify Stellarium response shapes.

We avoid spinning up a real HTTP server here; instead we monkeypatch
``requests.get`` so the test stays hermetic and fast.
"""

from __future__ import annotations

from typing import Any

import pytest
import requests

from seercontrol.core.stellarium import remote_pull
from seercontrol.core.stellarium.remote_pull import pull_selected_object


class _FakeResp:
    def __init__(self, payload: Any, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status
        self.text = str(payload)[:200]

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _patch_get(monkeypatch: pytest.MonkeyPatch, payload: Any, status: int = 200) -> None:
    monkeypatch.setattr(
        remote_pull.requests,
        "get",
        lambda *a, **kw: _FakeResp(payload, status=status),
    )


# --------------------------------------------------------------------------- #
# Success                                                                      #
# --------------------------------------------------------------------------- #

def test_pull_recognises_j2000_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_get(monkeypatch, {
        "name": "Vega",
        "raJ2000": 279.234735,        # decimal degrees
        "decJ2000": 38.78369,
        "vmag": 0.03,
    })
    t = pull_selected_object(host="127.0.0.1", port=8090)
    assert t is not None
    assert t.name == "Vega"
    assert t.ra_hours == pytest.approx(279.234735 / 15.0, abs=1e-4)
    assert t.dec_degrees == pytest.approx(38.78369, abs=1e-4)
    assert t.magnitude == pytest.approx(0.03)


def test_pull_accepts_hyphenated_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Older Stellarium plugin builds use ``ra-J2000`` instead of ``raJ2000``."""
    _patch_get(monkeypatch, {
        "localized-name": "Bételgeuse",
        "ra-J2000": 88.79,
        "dec-J2000": 7.41,
    })
    t = pull_selected_object()
    assert t is not None
    assert t.name == "Bételgeuse"
    assert t.ra_hours == pytest.approx(88.79 / 15.0, abs=1e-4)


def test_pull_falls_back_to_current_epoch_when_j2000_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_get(monkeypatch, {"name": "X", "ra": 12.34, "dec": -45.6})
    t = pull_selected_object()
    assert t is not None
    assert t.ra_hours == pytest.approx(12.34 / 15.0, abs=1e-4)
    assert t.dec_degrees == pytest.approx(-45.6, abs=1e-4)


# --------------------------------------------------------------------------- #
# Failure modes return None (caller shows a friendly UI message)               #
# --------------------------------------------------------------------------- #

def test_pull_returns_none_on_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_kw: Any) -> Any:
        raise requests.ConnectionError("Stellarium not running")
    monkeypatch.setattr(remote_pull.requests, "get", boom)
    assert pull_selected_object() is None


def test_pull_returns_none_on_http_500(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_get(monkeypatch, {"name": "X", "ra": 0, "dec": 0}, status=500)
    assert pull_selected_object() is None


def test_pull_returns_none_on_empty_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stellarium returns ``{}`` when nothing is selected."""
    _patch_get(monkeypatch, {})
    assert pull_selected_object() is None


def test_pull_returns_none_when_coords_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_get(monkeypatch, {"name": "X", "vmag": 1.0})
    assert pull_selected_object() is None
